#!/usr/bin/env python3
"""Model-free overhead budget for annotate actions (simplification plan, Goal 1).

    python scripts/bench.py --budget [--ref REF] [--answers 3] [--json OUT]
    python scripts/bench_budget.py [--src DIR] [--answers 3] [--json OUT]

One sandbox per run: its own state, bus and config roots, local transport and
a blocked `orca`, on a port in 18700-18799. A synthetic reviewer answers
through localhost HTTP. Each action's commands and printed tokens are compared
with its budget; exit 1 when any action is over. No model, no live page.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PORT_BASE = 18700  # sandbox range 18700-18799; never the registered 88xx pages

try:  # the plan's numbers use o200k; chars/4 is the offline proxy
    import tiktoken
    _ENC = tiktoken.get_encoding("o200k_base")
    TOKENIZER = "o200k_base"

    def tokens(text: str) -> int:
        return len(_ENC.encode(text))
except Exception:  # noqa: BLE001 - any import failure falls back
    TOKENIZER = "chars/4"

    def tokens(text: str) -> int:
        return math.ceil(len(text) / 4)


def budgets(n: int) -> dict:
    """Goal 1 budgets: commands, printed tokens, retries (stage 3: markup and input size too)."""
    return {
        "session_start": {"commands": 0, "tokens": 700},
        "ask_markup": {"commands": 0, "tokens": 10},
        "read_one_round": {"commands": 1, "tokens": 40 + 60 * n},
        "resolve_a_round": {"commands": 1, "tokens": 15 * n},
        "publish_small_update": {"commands": 1, "tokens": 25, "input_ratio": 1.2},
        "ask": {"commands": 1, "tokens": 25},
        "claim": {"commands": 1, "tokens": 25},
        "small_round": {"commands": 3, "tokens": 1000},
    }


def _sandbox_env(root: Path, src: Path) -> dict:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("ANNOTATE_", "ORCA_", "CODEX_", "CLAUDE_"))}
    for key, rel in {"STATE_DIR": "state", "BUS_ROOT": "bus", "CONFIG_DIR": "config",
                     "DATA_DIR": "data", "BUS_ARCHIVE_ROOT": "archive",
                     "TRANSCRIPT_GLOB": "no-transcripts/*.jsonl",
                     "CLAUDE_SETTINGS": "config/settings.json", "CODEX_HOOKS": "config/hooks.json",
                     "SHIM_PATH": "bin/annotate", "SKILL_DIRS": "skills",
                     "CODEX_PLUGIN_CACHE": "plugins"}.items():
        env["ANNOTATE_" + key] = str(root / rel)
    blocked = root / "bin" / "orca"
    blocked.write_text("#!/bin/sh\necho '{\"ok\":false,\"error\":\"budget: Orca blocked\"}'\nexit 1\n")
    blocked.chmod(0o755)
    env.update(PYTHONPATH=str(src), ANNOTATE_VERSION_GUARD="0", ANNOTATE_BOARD_API="http://127.0.0.1:9",
               CLAUDE_CODE_SESSION_ID="budget-fixture", ORCA_CLI_COMMAND=str(blocked),
               PATH=str(root / "bin") + os.pathsep + env.get("PATH", ""), TMPDIR=str(root / "tmp"))
    return env


CARD = ("Use layout {i}?", "The evidence shows the proposed layout.",
        "Use it", "The proposed layout ships.", "Keep current", "The layout stays unchanged.")


def _ask(i: int) -> str:
    prompt, context, label, consequence, other, other_consequence = CARD
    return (f"```ask\n{prompt.format(i=i)}\n{context}\n+ {label}: {consequence}\n"
            f"- {other}: {other_consequence}\n```\n")


def markup_tokens() -> int:
    """Tokens one plain card adds beyond its words (the plan measured 8; the JSON fence 76)."""
    return tokens(_ask(1)) - sum(tokens(part.format(i=1)) for part in CARD)


PLAN = ("## Plan\n\n" + "The checkout keeps the receipt visible while the reviewer pays. "
        "Each layout below was measured on a phone and a desktop screen. " * 3 + "\n\n")


def run_budget(src: Path, answers: int = 3, port: int | None = None, python: str = sys.executable,
               keep: bool = False) -> dict:
    """Run one small round in a sandbox; return per-action measurements and budgets."""
    port = port or PORT_BASE + 40 + answers
    if not PORT_BASE <= port < PORT_BASE + 100:
        raise ValueError(f"port {port} is outside the sandbox range 18700-18799")
    root = Path(tempfile.mkdtemp(prefix="annotate-budget-")).resolve()
    for d in ("bin", "config", "tmp", "state", "bus"):
        (root / d).mkdir()
    env = _sandbox_env(root, src)
    (root / "config/projects.toml").write_text(
        f'[defaults]\ntransport="local"\nport_base={port}\nlocal_author="reviewer@example.test"\n')
    cmds: list[dict] = []

    def cli(action: str, *args: str, ok=(0,)) -> subprocess.CompletedProcess:
        p = subprocess.run([python, "-m", "agent_annotate.cli", *args], env=env, cwd=root,
                           capture_output=True, text=True, timeout=120)
        out = p.stdout + p.stderr
        cmds.append({"action": action, "command": "annotate " + " ".join(args), "exit": p.returncode,
                     "output": out, "tokens": tokens(out), "command_tokens": tokens("annotate " + " ".join(args))})
        if p.returncode not in ok:
            raise RuntimeError(f"{action}: exit {p.returncode}\n{out}")
        return p

    def post(route: str, body: dict) -> dict:
        req = urllib.request.Request(f"http://127.0.0.1:{port}{route}", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp)

    page, source = root / "review", root / "page.md"
    source.write_text("---\ntitle: Round measurement\n---\n\n" + PLAN + "## Evidence\n\n"
                      "The proposed layout keeps the receipt visible.\n\n" + "\n".join(_ask(i) for i in range(1, answers + 1)))
    pid = None
    try:
        cli("ask", "publish", "review", "--from", "page.md", "--project", "fixture")
        rec = json.loads((root / "state/fixture.json").read_text())["slugs"]["review"]
        pid = rec["pid"]
        port = rec["port"]  # the first free port from port_base; other sandboxes share the range
        if not PORT_BASE <= port < PORT_BASE + 100:
            raise RuntimeError(f"sandbox page bound {port}, outside 18700-18799")
        cli("claim", "claim", "fixture/review")
        store = json.loads((page / "comments.json").read_text())
        for c in [c for cs in store["anchors"].values() for c in cs]:
            post(f"/api/comments/{c['id']}/decision",
                 {"verdict": "select", "option_id": "use-it", "text": "Use it. Keep the receipt visible."})
        post("/api/rounds/submit", {"note": "Please proceed with these layouts."})
        cli("read_one_round", "inbox", "fixture/review", "--unread")
        part = root / "result.md"
        part.write_text("## Result\n\nThe layouts now keep the receipt visible.\n")
        cli("publish_small_update", "publish", "fixture/review", "--from", "result.md", "--section", "Evidence")
        stored = (page / "source/v2.md").read_text()
        section = stored[stored.index("## Result"):]
        input_ratio = tokens(part.read_text()) / tokens(section)
        assert stored.count(PLAN.strip()) == 1, "the untouched section must stay byte-identical"
        nums = [str(i) for i in range(1, answers + 1)]
        # One command per round; a build without batch resolve exits 2 (usage) and is measured per item.
        p = cli("resolve_a_round", "resolve", "fixture/review", *nums, "--anchor", "s:result", ok=(0, 2))
        if p.returncode == 2:
            cmds.pop()
            for n in nums:
                cli("resolve_a_round", "resolve", "fixture/review", n, "--anchor", "s:result")
        result = json.loads((page / "comments.json").read_text())
        assert all(c.get("resolved_in_version") == "v2" for cs in result["anchors"].values() for c in cs), \
            "every answered item must resolve into v2"
        assert json.loads((page / "current.meta.json").read_text())["current"] == "v2"
    finally:
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        if not keep:
            shutil.rmtree(root, ignore_errors=True)

    skill = (src / "agent_annotate/skills/claude/SKILL.md").read_text()
    ref = (src / "agent_annotate/skills/claude/references/page.md").read_text()
    # The reference counts at start when the skill sends every author to it, as the 2.28.2 skill did.
    always_ref = "references/page.md) when authoring" in skill
    measured = {"session_start": {"commands": 0, "tokens": tokens(skill) + (tokens(ref) if always_ref else 0),
                                  "skill_tokens": tokens(skill), "reference_tokens": tokens(ref),
                                  "reference_loaded_at_start": always_ref},
                "ask_markup": {"commands": 0, "tokens": markup_tokens()}}
    for action in ("read_one_round", "resolve_a_round", "publish_small_update", "ask", "claim"):
        rows = [c for c in cmds if c["action"] == action]
        measured[action] = {"commands": len(rows), "tokens": sum(c["tokens"] for c in rows),
                            "retries": sum(1 for c in rows if c["exit"] != 0)}
    measured["publish_small_update"]["input_ratio"] = round(input_ratio, 2)
    rnd = [c for c in cmds if c["action"] in ("read_one_round", "publish_small_update", "resolve_a_round")]
    measured["small_round"] = {"commands": len(rnd), "tokens": sum(c["tokens"] + c["command_tokens"] for c in rnd),
                               "retries": 0}
    limit = budgets(answers)
    return {"answers": answers, "tokenizer": TOKENIZER, "budget": limit, "measured": measured,
            "over": over_budget(measured, limit),
            "outputs": {c["action"] + ":" + c["command"]: c["output"] for c in cmds}}


def over_budget(measured: dict, limit: dict) -> list[str]:
    """Actions over their command or token budget, or that needed a retry."""
    return [a for a, b in limit.items()
            if measured[a]["commands"] > b["commands"] or measured[a]["tokens"] > b["tokens"]
            or measured[a].get("retries") or measured[a].get("input_ratio", 0) > b.get("input_ratio", 1e9)]


def render(result: dict) -> str:
    lines = [f"budget ({result['answers']} answers, {result['tokenizer']})",
             f"{'action':22} {'cmds':>9} {'tokens':>11}  ok"]
    for a, b in result["budget"].items():
        m = result["measured"][a]
        ok = "over" if a in result["over"] else "ok"
        lines.append(f"{a:22} {m['commands']:>4}/{b['commands']:<4} {m['tokens']:>5}/{b['tokens']:<5}  {ok}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", default=str(REPO / "src"), help="package source dir (default: this checkout)")
    ap.add_argument("--ref", help="git ref to export and measure instead of --src")
    ap.add_argument("--answers", type=int, action="append", help="answers per round (default 3 and 5)")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--keep", action="store_true", help="keep the sandbox")
    args = ap.parse_args(argv)
    src = Path(args.src)
    if args.ref:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from bench import export_ref
        src = export_ref(args.ref, Path(tempfile.mkdtemp(prefix="annotate-budget-build-")))["src"]
    results = [run_budget(src, n, python=args.python, keep=args.keep) for n in args.answers or (3, 5)]
    print("\n\n".join(render(r) for r in results))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(results, indent=2) + "\n")
    return 1 if any(r["over"] for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
