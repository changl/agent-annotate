#!/usr/bin/env python3
"""Before/after benchmark: real `claude -p` runs against agent-annotate builds.

    python scripts/bench.py --ref main --ref HEAD [--scenario v1-page] [--runs 3]

Each --ref (a git ref, or a checkout directory used as-is) is exported once.
Every run then gets a fresh sandbox under $TMPDIR: its own state, bus and
config roots, a bin/annotate launcher for that build, the build's skill at
<cwd>/.claude/skills/annotate, and a `claude -p` that loads project settings
only. Setup and outcome checks never call a model. Every process the sandbox
started is stopped afterwards. Nothing reads or writes ~/.claude/annotate-*,
~/.claude/settings.json, ~/.local/bin/annotate or a live page server.

Scenarios are bench/fixtures/<name>/scenario.json. See bench/README.md.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import queue
import re
import shutil
import signal
import statistics
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import traceback
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "bench" / "fixtures"
PORT_BASE = 9400            # sandbox pages never share the live 88xx range
PORT_STRIDE = 20            # per concurrent job
ALLOWED_TOOLS = ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "Skill"]
# The harness usually runs inside an agent session; none of that may leak in.
STRIP_ENV = ("CLAUDECODE", "CLAUDE_CODE_", "CLAUDE_PID", "CLAUDE_EFFORT", "CLAUDE_PLUGIN_",
             "CODEX_", "ANNOTATE_", "ORCA_", "AI_AGENT", "PYTHONPATH", "VIRTUAL_ENV")
STOP = threading.Event()

LAUNCHER = """#!__PY__
# agent-annotate bench launcher: runs the build under test from __SRC__.
# Before new/publish/publish-version it pins the slug dir's project to
# transport=local, port __PORT__+, so no sandbox page takes a live page's port.
import json, os, sys, tomllib
from pathlib import Path

argv = sys.argv[1:]
if argv[:1] and argv[0] in ("new", "publish", "publish-version"):
    toml = Path("__TOML__")
    names = {Path(a).expanduser().resolve().parent.name for a in argv[1:] if not a.startswith("-")}
    names |= {b for a, b in zip(argv, argv[1:]) if a == "--project"}
    have = tomllib.loads(toml.read_text()) if toml.exists() else {}
    with toml.open("a") as fh:
        for name in sorted(names - set(have) - {""}):
            fh.write(f'\\n[{json.dumps(name)}]\\ntransport = "local"\\nport_base = __PORT__\\nlocal_author = "chang@example.com"\\nlocal_author_name = "Benchmark reviewer"\\n')
os.environ["PYTHONPATH"] = "__SRC__"
os.execv("__PY__", ["__PY__", "-m", "agent_annotate.cli", *argv])
"""


# ────────────────────────────────────────────────────────────────────────────
# Pure parts: transcript parsing, failure counting, card checks, table math
# ────────────────────────────────────────────────────────────────────────────
_SEGMENTS = re.compile(r"&&|\|\||[;|\n]|\$\(|`|\(")
_ENV_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_PREFIXES = {"time", "exec", "command", "env", "nohup"}
FAIL_RE = re.compile(r"\bERROR\b|\bFAIL(?:ED)?\b|NOT PUBLISHED|Traceback \(most recent call last\)")


def annotate_subcommands(cmd: str) -> list[str]:
    """The annotate subcommands one shell command runs, in order.

    Counts `annotate …`, `/any/bin/annotate …` and `python -m agent_annotate.cli …`
    in command position; `annotate-state` paths and the skill directory do not.
    """
    subs = []
    for seg in _SEGMENTS.split(cmd or ""):
        toks = seg.split()
        while toks and (_ENV_ASSIGN.match(toks[0]) or toks[0] in _PREFIXES):
            toks.pop(0)
        if not toks:
            continue
        if toks[0].strip("'\"").rsplit("/", 1)[-1] == "annotate":
            rest = toks[1:]
        elif "agent_annotate.cli" in toks:
            rest = toks[toks.index("agent_annotate.cli") + 1:]
        else:
            continue
        sub = next((t for t in rest if not t.startswith("-")), "")
        subs.append(sub.strip(")'\"") or "?")
    return subs


def output_failed(text: str, is_error: bool) -> bool:
    """A tool result that failed: non-zero exit, ERROR, FAIL, NOT PUBLISHED, Traceback."""
    return bool(is_error) or bool(FAIL_RE.search(text or ""))


def _clip(text, n: int) -> str:
    text = str(text or "")
    return text if len(text) <= n else text[: n - 1] + "…"


def _result_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
    return ""


def parse_stream(lines) -> dict:
    """Metrics from `claude -p --output-format stream-json --verbose` output."""
    calls: dict = {}
    out = {"tool_calls": 0, "tool_errors": 0, "annotate_calls": 0, "annotate_failures": 0,
           "skill_used": False, "failures": []}
    subcommands: Counter = Counter()
    result = None
    for raw in lines:
        try:
            ev = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        content = (ev.get("message") or {}).get("content")
        if ev.get("type") == "assistant" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                out["tool_calls"] += 1
                inp = block.get("input") or {}
                cmd = inp.get("command") if block.get("name") == "Bash" else None
                subs = annotate_subcommands(cmd) if isinstance(cmd, str) else []
                if subs:
                    out["annotate_calls"] += 1
                    subcommands.update(subs)
                if block.get("name") == "Skill" and "annotate" in json.dumps(inp):
                    out["skill_used"] = True
                calls[block.get("id")] = (cmd, bool(subs))
        elif ev.get("type") == "user" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                text, is_error = _result_text(block.get("content")), bool(block.get("is_error"))
                out["tool_errors"] += is_error
                cmd, is_annotate = calls.get(block.get("tool_use_id"), (None, False))
                if is_annotate and output_failed(text, is_error):
                    out["annotate_failures"] += 1
                    out["failures"].append({"cmd": _clip(cmd, 240), "out": _clip(text, 400)})
        elif ev.get("type") == "result":
            result = ev
    res = result or {}
    usage = res.get("usage") or {}
    duration_ms = res.get("duration_ms")
    out.update(
        annotate_subcommands=dict(subcommands),
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        thinking_tokens=(usage.get("output_tokens_details") or {}).get("thinking_tokens"),
        cache_read=usage.get("cache_read_input_tokens"),
        cache_creation=usage.get("cache_creation_input_tokens"),
        cost_usd=res.get("total_cost_usd"),
        duration_s=duration_ms / 1000 if isinstance(duration_ms, (int, float)) else None,
        num_turns=res.get("num_turns"),
        is_error=bool(res.get("is_error")) if result else True,
        subtype=res.get("subtype"),
        result_text=_clip(res.get("result"), 2000),
    )
    return out


def card_problems(card: dict, anchors: set) -> list[str]:
    """What a decision card lacks: context, recommendation, a consequence per
    option (free-text answers excepted), evidence anchors that are on the page."""
    dr = card.get("decision_request") if isinstance(card, dict) else None
    if not isinstance(dr, dict):
        return ["no decision_request"]
    problems = [f for f in ("context", "recommendation") if not str(dr.get(f) or "").strip()]
    options = dr.get("options") or []
    consequences = dr.get("consequences") if isinstance(dr.get("consequences"), dict) else {}
    if not options:
        problems.append("options")
    for opt in options:
        oid = opt.get("id") if isinstance(opt, dict) else opt
        if oid in ("comment", "changes"):
            continue
        said = (opt.get("consequence") if isinstance(opt, dict) else None) or consequences.get(oid)
        if not str(said or "").strip():
            problems.append(f"consequence:{oid}")
    evidence = dr.get("evidence") or []
    if not evidence:
        problems.append("evidence")
    for item in evidence:
        anchor = item.get("anchor") if isinstance(item, dict) else None
        if not anchor or anchor not in anchors:
            problems.append(f"evidence:{anchor}")
    return problems


def summarize(values) -> dict | None:
    vals = sorted(v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool))
    if not vals:
        return None
    return {"median": statistics.median(vals), "min": vals[0], "max": vals[-1], "n": len(vals)}


def fmt_cell(s: dict | None, digits: int, spread: bool) -> str:
    if s is None:
        return "-"
    text = f"{s['median']:,.{digits}f}"
    if spread and s["n"] > 1:
        text += f" [{s['min']:,.{digits}f}–{s['max']:,.{digits}f}]"
    return text


def fmt_delta(base: dict | None, cand: dict | None, digits: int) -> str:
    if base is None or cand is None:
        return "-"
    d = cand["median"] - base["median"]
    text = f"{d:+,.{digits}f}"
    if base["median"]:
        text += f" ({d / base['median'] * 100:+.0f}%)"
    return text


METRICS = (("output_tokens", "output tokens", 0), ("thinking_tokens", "thinking tokens", 0),
           ("cache_read", "cache read", 0), ("cache_creation", "cache creation", 0),
           ("cost_usd", "cost $", 2), ("duration_s", "duration s", 0), ("num_turns", "turns", 0),
           ("annotate_calls", "annotate calls", 0), ("annotate_failures", "annotate failures", 0))


def render_table(title: str, labels: list[str], rows: dict[str, list[dict]]) -> str:
    """Median [min–max] per ref, then each later ref's delta against the first."""
    spread = any(len(rows.get(label, [])) > 1 for label in labels)
    header = ["metric", *labels, *[f"Δ {label}" for label in labels[1:]]]
    body = []
    for key, name, digits in METRICS:
        s = [summarize(r.get(key) for r in rows.get(label, [])) for label in labels]
        body.append([name, *[fmt_cell(x, digits, spread) for x in s],
                     *[fmt_delta(s[0], x, digits) for x in s[1:]]])
    passed = [sum(1 for r in rows.get(label, []) if r.get("outcome")) for label in labels]
    body.append(["outcome pass", *[f"{p}/{len(rows.get(label, []))}" for p, label in zip(passed, labels)],
                 *[f"{p - passed[0]:+d}" for p in passed[1:]]])
    widths = [max(len(r[i]) for r in [header, *body]) for i in range(len(header))]
    lines = [title]
    for r in [header, *body]:
        lines.append("  ".join(c.ljust(w) if i == 0 else c.rjust(w)
                               for i, (c, w) in enumerate(zip(r, widths))).rstrip())
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────────────
# Builds and sandboxes
# ────────────────────────────────────────────────────────────────────────────
def _git(*argv: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *argv], capture_output=True, text=True,
                          check=True).stdout.strip()


def export_ref(ref: str, dest_root: Path) -> dict:
    """{label, sha, src} for a git ref (exported with git archive) or a directory."""
    path = Path(ref).expanduser()
    if path.is_dir():
        src = path / "src" if (path / "src" / "agent_annotate").is_dir() else path
        if not (src / "agent_annotate").is_dir():
            sys.exit(f"bench: {ref} holds no agent_annotate package")
        return {"ref": ref, "label": path.resolve().name, "sha": "worktree", "src": src.resolve()}
    sha = _git("rev-parse", "--short", f"{ref}^{{commit}}")
    dest = dest_root / f"{re.sub(r'[^A-Za-z0-9._-]', '-', ref)}-{sha}"
    tar = subprocess.run(["git", "-C", str(REPO), "archive", "--format=tar", sha, "src"],
                         capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tar)) as tf:
        try:
            tf.extractall(dest, filter="data")
        except TypeError as exc:
            raise RuntimeError("Benchmark export requires Python tarfile data extraction filters; upgrade Python") from exc
    if not (dest / "src" / "agent_annotate").is_dir():
        sys.exit(f"bench: {ref} ({sha}) has no src/agent_annotate")
    return {"ref": ref, "label": f"{ref}@{sha}", "sha": sha, "src": dest / "src"}


def _toml_section(name: str, port_base: int) -> str:
    return (f'\n[{json.dumps(name)}]\ntransport = "local"\nport_base = {port_base}\n'
            'local_author = "chang@example.com"\nlocal_author_name = "Benchmark reviewer"\n')


def make_sandbox(build: dict, scenario: dict, port_base: int, python: str) -> dict:
    root = Path(tempfile.mkdtemp(prefix=f"annotate-bench-{scenario['name']}-")).resolve()
    home, bin_dir, cwd = root / "home", root / "bin", root / scenario.get("cwd", "work")
    for d in ("state", "bus", "config", "data", "bus-archive"):
        (home / d).mkdir(parents=True)
    bin_dir.mkdir()
    (cwd / ".claude").mkdir(parents=True)
    toml = home / "config" / "projects.toml"
    toml.write_text("".join(_toml_section(n, port_base) for n in (cwd.name, "reviews")))
    launcher = bin_dir / "annotate"
    launcher.write_text(LAUNCHER.replace("__PY__", python).replace("__SRC__", str(build["src"]))
                        .replace("__TOML__", str(toml)).replace("__PORT__", str(port_base)))
    launcher.chmod(0o755)
    for rel, fixture in (scenario.get("files") or {}).items():
        (cwd / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(scenario["dir"] / fixture, cwd / rel)

    # One settings file, two readers: claude loads it with --settings
    # (permissions for dontAsk, the UserPromptSubmit hook; a project
    # .claude/settings.json in an untrusted temp dir has its permissions
    # ignored), and ANNOTATE_CLAUDE_SETTINGS points the hook installer at it,
    # so publish finds the hook already present, as on a real machine.
    settings = home / "claude-settings.json"
    hook = build["src"] / "agent_annotate" / "hooks" / "check-comment-bus.sh"
    settings.write_text(json.dumps({
        "permissions": {"allow": ALLOWED_TOOLS},
        "hooks": {"UserPromptSubmit": [{"hooks": [
            {"type": "command", "command": str(hook), "timeout": 30}]}]},
    }, indent=2))

    env = {k: v for k, v in os.environ.items() if not k.startswith(STRIP_ENV)}
    env.update({
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "PYTHONPATH": str(build["src"]),
        "ANNOTATE_STATE_DIR": str(home / "state"),
        "ANNOTATE_BUS_ROOT": str(home / "bus"),
        "ANNOTATE_CONFIG_DIR": str(home / "config"),
        "ANNOTATE_DATA_DIR": str(home / "data"),
        "ANNOTATE_BUS_ARCHIVE_ROOT": str(home / "bus-archive"),
        "ANNOTATE_CLAUDE_SETTINGS": str(settings),
        "ANNOTATE_SHIM_PATH": str(launcher),
        "ANNOTATE_TRANSCRIPT_GLOB": str(home / "no-transcripts" / "*.jsonl"),
    })
    skill = cwd / ".claude" / "skills" / "annotate"
    done = subprocess.run([str(launcher), "install-skill", "--provider", "claude", "--dest", str(skill)],
                          env=env, cwd=cwd, capture_output=True, text=True)
    if done.returncode:     # a build older than install-skill: its text as-is
        shutil.copytree(build["src"] / "agent_annotate" / "skills" / "claude", skill, dirs_exist_ok=True)
    return {"root": root, "home": home, "cwd": cwd, "bin": bin_dir, "env": env,
            "settings": settings, "port_base": port_base}


def registry(home: Path) -> list[dict]:
    rows = []
    for sf in sorted((home / "state").glob("*.json")):
        try:
            state = json.loads(sf.read_text())
        except (OSError, ValueError):
            continue
        rows += [r for r in (state.get("slugs") or {}).values() if isinstance(r, dict)]
    return rows


def page_record(home: Path, slug: str | None = None) -> dict | None:
    rows = [r for r in registry(home) if slug is None or r.get("slug") == slug]
    return max(rows, key=lambda r: r.get("started_at") or "") if rows else None


def _http(method: str, url: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    parts = urllib.parse.urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", "Origin": origin})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
    return json.loads(raw) if raw.strip() else None


class SetupError(RuntimeError):
    pass


def run_setup(sb: dict, scenario: dict, session_id: str) -> str | None:
    """Publish the scenario's page as this session, then answer and submit the
    round through the page's own API exactly as the reviewer's browser does."""
    setup = scenario.get("setup")
    if not setup:
        return None
    slug_dir = sb["cwd"] / setup["slug_dir"]
    done = subprocess.run(
        [str(sb["bin"] / "annotate"), "new", str(slug_dir), "--from", str(sb["cwd"] / setup["source"]),
         "--publish", "--ask"],
        cwd=sb["cwd"], env={**sb["env"], "CLAUDE_CODE_SESSION_ID": session_id},
        capture_output=True, text=True, timeout=300)
    if done.returncode:
        raise SetupError(f"new --publish --ask exited {done.returncode}: "
                         f"{_clip(done.stdout + done.stderr, 800)}")
    rec = page_record(sb["home"], slug_dir.name)
    if not rec:
        raise SetupError("setup page is not registered")
    base = f"http://127.0.0.1:{rec['port']}"
    ids = {c.get("anchor_id"): c.get("id") for c in _http("GET", f"{base}/api/comments") or []
           if c.get("decision_request")}
    for v in setup.get("verdicts") or []:
        if v["anchor"] not in ids:
            raise SetupError(f"no posed card on {v['anchor']}")
        body = {"verdict": v["verdict"], "defer_push": True, **({"text": v["text"]} if v.get("text") else {})}
        _http("POST", f"{base}/api/comments/{urllib.parse.quote(ids[v['anchor']], safe='')}/decision", body)
    if setup.get("submit"):
        _http("POST", f"{base}/api/rounds/submit", {})
    return slug_dir.name


def run_claude(sb: dict, prompt: str, session_id: str, args) -> tuple[int | None, bool]:
    cmd = [args.claude, "-p", prompt, "--setting-sources", "project", "--no-session-persistence",
           "--strict-mcp-config", "--output-format", "stream-json", "--verbose",
           "--settings", str(sb["settings"]), "--model", args.model, "--effort", args.effort,
           "--permission-mode", "dontAsk", "--session-id", session_id]
    if args.max_budget_usd:
        cmd += ["--max-budget-usd", str(args.max_budget_usd)]
    deadline = time.monotonic() + args.timeout
    with (sb["root"] / "transcript.ndjson").open("w") as out, (sb["root"] / "claude.stderr").open("w") as err:
        proc = subprocess.Popen(cmd, cwd=sb["cwd"], env=sb["env"], stdin=subprocess.DEVNULL,
                                stdout=out, stderr=err, start_new_session=True)
        while True:
            try:
                return proc.wait(timeout=1), False
            except subprocess.TimeoutExpired:
                if STOP.is_set() or time.monotonic() > deadline:
                    break
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, sig)
            except OSError:
                pass
            try:
                return proc.wait(timeout=10), True
            except subprocess.TimeoutExpired:
                continue
        return None, True


def teardown(sb: dict, keep: bool) -> None:
    """Stop every process whose command line or environment names this
    sandbox — the page servers publish started, and anything else it ran."""
    root = str(sb["root"])
    ps = subprocess.run(["ps", "-axeww", "-o", "pid=,command="], capture_output=True, text=True).stdout
    pids = {int(line.split(None, 1)[0]) for line in ps.splitlines() if root in line} - {os.getpid()}
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in list(pids):
            try:
                os.kill(pid, sig)
            except OSError:
                pids.discard(pid)
        for _ in range(30):
            pids = {p for p in pids if _alive(p)}
            if not pids:
                break
            time.sleep(0.1)
    if not keep:
        shutil.rmtree(sb["root"], ignore_errors=True)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# ────────────────────────────────────────────────────────────────────────────
# Outcome checks (no model)
# ────────────────────────────────────────────────────────────────────────────
def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _comments(slug_dir: Path) -> list[dict]:
    store = _read_json(slug_dir / "comments.json", {})
    anchors = store.get("anchors") if isinstance(store, dict) else None
    if not isinstance(anchors, dict):
        anchors = {k: v for k, v in (store or {}).items() if isinstance(v, list)}
    return [c for items in anchors.values() if isinstance(items, list) for c in items if isinstance(c, dict)]


def _anchors(html: Path) -> set:
    try:
        return set(re.findall(r'data-anchor-id="([^"]+)"', html.read_text(errors="replace")))
    except OSError:
        return set()


def _cards_problems(cards, anchors: set, count: int | None) -> list[str]:
    if not isinstance(cards, list):
        return ["cards are not a list"]
    problems = [f"{len(cards)} cards, want {count}"] if count is not None and len(cards) != count else []
    return problems + [f"#{c.get('number', i + 1) if isinstance(c, dict) else i + 1} {p}"
                       for i, c in enumerate(cards) for p in card_problems(c, anchors)]


def _cards_block(text: str):
    m = re.search(r"^```cards[ \t]*\n(.*?)^```", text, re.S | re.M)
    return json.loads(m.group(1)) if m else []


def chk_live(spec, rec, slug_dir):
    pid = int(rec.get("pid") or 0)
    if not _alive(pid):
        return False, f"pid {pid} not running"
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{rec['port']}/", timeout=10) as resp:
            return resp.status == 200, f"HTTP {resp.status}"
    except Exception as e:
        return False, _clip(e, 120)


def chk_version_html(spec, rec, slug_dir):
    return (slug_dir / "versions" / f"{spec['version']}.html").is_file(), ""


def chk_current(spec, rec, slug_dir):
    v = spec["version"]
    meta = _read_json(slug_dir / "current.meta.json", {}).get("current")
    link = (slug_dir / "current.html").resolve().name
    ok = meta == v and link == f"{v}.html" and (slug_dir / "versions" / f"{v}.html").is_file()
    return ok, f"current={meta}, current.html→{link}"


def chk_cards_json(spec, rec, slug_dir):
    cards = _read_json(slug_dir / "cards.json", None)
    cards = cards.get("cards") if isinstance(cards, dict) else cards
    problems = _cards_problems(cards, _anchors(slug_dir / "current.html"), spec.get("count"))
    return not problems, "; ".join(problems)


def chk_source_cards(spec, rec, slug_dir):
    """The cards authored for a version, if any, conform."""
    v = spec["version"]
    src = slug_dir / "source" / f"{v}.md"
    cards = _cards_block(src.read_text()) if src.is_file() else []
    problems = _cards_problems(cards, _anchors(slug_dir / "versions" / f"{v}.html"), spec.get("count"))
    return not problems, "; ".join(problems) or f"{len(cards)} card(s)"


def chk_posed(spec, rec, slug_dir):
    n = sum(1 for c in _comments(slug_dir) if c.get("decision_request")
            and c.get("version") == spec["version"] and c.get("status") != "archived")
    return n >= spec.get("count", 1), f"{n} posed"


def chk_disposed(spec, rec, slug_dir):
    left = [c.get("anchor_id") or c.get("id") for c in _comments(slug_dir)
            if c.get("version") == spec["version"]
            and (c.get("status") or "open") in ("open", "addressed_by_agent")]
    return not left, f"still open: {', '.join(map(str, left))}" if left else ""


def chk_keywords(spec, rec, slug_dir):
    v = spec["version"]
    src = slug_dir / "source" / f"{v}.md"
    path = src if src.is_file() else slug_dir / "versions" / f"{v}.html"
    text = path.read_text(errors="replace").lower() if path.is_file() else ""
    hits = [k for k in spec["any"] if k.lower() in text]
    return bool(hits), f"{path.name}: " + (f"has {hits[0]!r}" if hits else f"none of {spec['any']}")


CHECKS = {"live": chk_live, "version_html": chk_version_html, "current": chk_current,
          "cards_json": chk_cards_json, "source_cards": chk_source_cards, "posed": chk_posed,
          "disposed": chk_disposed, "keywords": chk_keywords}


def run_checks(sb: dict, scenario: dict, slug: str | None) -> dict:
    rec = page_record(sb["home"], slug)
    slug_dir = Path(rec["slug_dir"]) if rec and rec.get("slug_dir") else None
    out = {}
    for spec in scenario["checks"]:
        key = spec["check"] + (f":{spec['version']}" if "version" in spec else "")
        if slug_dir is None:
            ok, detail = False, "no registered page"
        else:
            try:
                ok, detail = CHECKS[spec["check"]](spec, rec, slug_dir)
            except Exception as e:
                ok, detail = False, f"{type(e).__name__}: {_clip(e, 160)}"
        out[key] = {"ok": bool(ok), "detail": detail}
    return out


# ────────────────────────────────────────────────────────────────────────────
# Runs
# ────────────────────────────────────────────────────────────────────────────
def load_scenarios(names: list[str] | None) -> list[dict]:
    available = sorted(p.parent.name for p in FIXTURES.glob("*/scenario.json"))
    unknown = sorted(set(names or []) - set(available))
    if unknown:
        sys.exit(f"bench: unknown scenario(s) {', '.join(unknown)}; have {', '.join(available)}")
    out = []
    for name in names or available:
        spec = json.loads((FIXTURES / name / "scenario.json").read_text())
        out.append({**spec, "name": name, "dir": FIXTURES / name})
    return out


def run_one(build: dict, scenario: dict, run: int, slots: queue.Queue, args) -> dict:
    slot = slots.get()
    session_id = str(uuid.uuid4())
    row = {"ref": build["label"], "sha": build["sha"], "scenario": scenario["name"], "run": run,
           "session_id": session_id, "outcome": False}
    sb = None
    try:
        sb = make_sandbox(build, scenario, PORT_BASE + PORT_STRIDE * slot, args.python)
        row["sandbox"] = str(sb["root"])
        slug = run_setup(sb, scenario, session_id)
        if not args.no_model:
            prompt = scenario["prompt"].replace("{slug}", slug or "")
            started = time.monotonic()
            row["exit_code"], row["timed_out"] = run_claude(sb, prompt, session_id, args)
            row["wall_s"] = round(time.monotonic() - started, 1)
            with (sb["root"] / "transcript.ndjson").open() as fh:
                row.update(parse_stream(fh))
        row["checks"] = run_checks(sb, scenario, slug)
        row["outcome"] = all(c["ok"] for c in row["checks"].values())
        rec = page_record(sb["home"], slug)
        bus = [line for p in (sb["home"] / "bus").rglob("*.ndjson")
               for line in p.read_text(errors="replace").splitlines()]
        row["diag"] = {
            "owner_is_session": bool(rec) and rec.get("owner_session") == session_id,
            "hook_notices": sum(1 for line in bus if "notice_emitted" in line and session_id in line),
            "port_leak": [r.get("port") for r in registry(sb["home"])
                          if int(r.get("port") or 0) < sb["port_base"]],
        }
    except Exception as e:      # one broken run must not sink the rest
        row["error"] = f"{type(e).__name__}: {_clip(e, 600)}"
        row["traceback"] = traceback.format_exc()[-2000:]
    finally:
        if sb:
            teardown(sb, args.keep)
            if not args.keep:
                row.pop("sandbox", None)
        slots.put(slot)
    return row


def _progress(row: dict, done: int, total: int) -> None:
    bits = [f"[{done}/{total}] {row['ref']} {row['scenario']} run {row['run']}"]
    if row.get("cost_usd") is not None:
        bits.append(f"{row.get('duration_s') or 0:.0f}s ${row['cost_usd']:.2f}")
    bits.append("PASS" if row["outcome"] else "FAIL " + ", ".join(
        k for k, c in (row.get("checks") or {}).items() if not c["ok"]))
    if row.get("error"):
        bits.append(row["error"])
    if (row.get("diag") or {}).get("port_leak"):
        bits.append(f"WARNING: port(s) below {PORT_BASE}: {row['diag']['port_leak']}")
    if row.get("sandbox"):
        bits.append(f"kept {row['sandbox']}")
    print("  ".join(bits), file=sys.stderr, flush=True)


def _details(rows: list[dict]) -> list[str]:
    lines = []
    for r in rows:
        bad = [f"{k} ({c['detail']})" if c["detail"] else k
               for k, c in (r.get("checks") or {}).items() if not c["ok"]]
        if r.get("error"):
            bad.insert(0, r["error"])
        for f in r.get("failures") or []:
            cmd = " ".join((f["cmd"] or "").split())
            cmd = cmd[max(cmd.find("annotate "), 0):]       # drop a leading `cd <sandbox>`
            bad.append(f"`{_clip(cmd, 80)}` → {_clip(' '.join(f['out'].split()), 120)}")
        if bad:
            lines.append(f"  {r['ref']} run {r['run']}: " + " | ".join(bad))
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--ref", action="append", required=True,
                    help="git ref or checkout directory; repeat. The first is the baseline.")
    ap.add_argument("--scenario", action="append", help="default: every bench/fixtures/*/scenario.json")
    ap.add_argument("--runs", type=int, default=3, help="runs per ref per scenario (default 3)")
    ap.add_argument("--model", default="opus")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--max-budget-usd", type=float, help="passed to claude -p, per run")
    ap.add_argument("--timeout", type=int, default=1200, help="seconds per claude run (default 1200)")
    ap.add_argument("--jobs", type=int, default=1, help="concurrent runs (default 1)")
    ap.add_argument("--json", dest="json_out", help="write every raw row here")
    ap.add_argument("--keep", action="store_true", help="keep sandboxes and exported builds")
    ap.add_argument("--no-model", action="store_true",
                    help="setup and checks only, no claude call: validates fixtures against a build")
    ap.add_argument("--python", default=sys.executable,
                    help="interpreter that runs each build (needs its deps; default: this one)")
    ap.add_argument("--claude", default=shutil.which("claude") or "claude")
    args = ap.parse_args(argv)

    scenarios = load_scenarios(args.scenario)
    export_root = Path(tempfile.mkdtemp(prefix="annotate-bench-builds-")).resolve()
    builds, seen = [], Counter()
    for ref in args.ref:
        b = export_ref(ref, export_root)
        seen[b["label"]] += 1
        if seen[b["label"]] > 1:      # the same ref twice measures the noise floor
            b["label"] += f"#{seen[b['label']]}"
        builds.append(b)
    # Interleaved, so drift over the session (cache warmth, load) hits every ref alike.
    jobs = [(b, s, run) for run in range(1, args.runs + 1) for s in scenarios for b in builds]
    slots: queue.Queue = queue.Queue()
    for i in range(max(1, args.jobs)):
        slots.put(i)
    rows: list[dict] = []
    try:
        with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
            futures = [pool.submit(run_one, b, s, run, slots, args) for b, s, run in jobs]
            try:
                for fut in futures:
                    rows.append(fut.result())
                    _progress(rows[-1], len(rows), len(jobs))
            except KeyboardInterrupt:
                STOP.set()      # running claudes are killed and torn down within ~1 s
                for fut in futures:
                    fut.cancel()
                print("bench: interrupted; tearing down", file=sys.stderr)
                raise
    finally:
        if not args.keep:
            shutil.rmtree(export_root, ignore_errors=True)

    labels = [b["label"] for b in builds]
    for s in scenarios:
        mine = [r for r in rows if r["scenario"] == s["name"]]
        title = f"\n{s['name']}  ({args.model}/{args.effort}, {args.runs} run(s) per ref)"
        print(render_table(title, labels, {label: [r for r in mine if r["ref"] == label] for label in labels}))
        for line in _details(mine):
            print(line)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps({
            "meta": {"refs": [{k: str(v) for k, v in b.items()} for b in builds],
                     "scenarios": [s["name"] for s in scenarios], "runs": args.runs,
                     "model": args.model, "effort": args.effort,
                     "date": time.strftime("%Y-%m-%dT%H:%M:%S%z")},
            "rows": rows}, indent=2, default=str))
    return 0 if all(r["outcome"] for r in rows) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
