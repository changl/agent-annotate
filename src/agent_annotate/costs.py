"""annotate cost — what agents spend, in tokens and seconds, driving annotate.

Measured from the transcripts agents already leave behind, so the numbers
are continuous and free to collect, and a proposed change can be priced
against past sessions (--estimate) before it ships instead of after a week of
new usage.

Read-only: reads transcripts, never runs annotate or a model, writes nothing.
Claude Code transcripts (~/.claude/projects, subagents included) by default;
--codex adds ~/.codex/sessions.

One row per tool call that ran the annotate CLI, and one per read of the
annotate skill or its references (kind "doc"):

  result_tokens     what the call put into context: result chars / 4
  out_tokens        output tokens of the assistant message that issued it.
                    Claude repeats a message's usage on every streamed line,
                    so it is read once per message.id (the max), then split
                    evenly over that message's tool calls: a sum never counts
                    one message twice.
  secs              tool_use -> tool_result wall time, the CLI's own speed
  failed, reasons   is_error, or an error pattern in the result text
  retry_out_tokens  on a failed row, out_tokens of the next call of the same
                    subcommand in that transcript: the turn a fix would save

Sessions whose cwd is annotate's own development (parrotfish, agent-annotate,
skills-org) are left out unless --include-dev: building annotate is not
using it, and its test runs would swamp the failure rate.
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import os
import re
import statistics
import sys
from pathlib import Path

from .paths import PACKAGE_DIR, TRANSCRIPT_GLOB

# Retired names stay so older transcripts still parse.
SUBS = ("new publish publish-version unpublish status claim ask cards open-cards inbox monitor "
        "addressed resolve carry close retire revive doctor eval cost watch install-shim "
        "install-skill archive-comment migrate prune-bus sessions connect disconnect send "
        "hook-check mcp").split()
_SUB = "|".join(sorted(map(re.escape, SUBS), key=len, reverse=True))
SEG_CLI = re.compile(rf"^(?:\S*/)?annotate\s+({_SUB})(?=\s|$)(.*)$", re.S)
SEG_PY = re.compile(rf"^\S*python[0-9.]*\s+(?:-u\s+)?(?:-m\s+agent_annotate\.cli|\S*annotate/cli\.py)"
                    rf"\s+({_SUB})(?=\s|$)(.*)$", re.S)
# Launchers agents put in front of the CLI: rtk, env, VAR=value, timeout N, uv run, ...
WRAP = re.compile(r"^(?:[A-Z_][A-Z0-9_]*=\S*\s+|rtk\s+proxy\s+|rtk\s+|nohup\s+|timeout\s+\d+\s+"
                  r"|env\s+|exec\s+|uv\s+run\s+(?:--\S+\s+)*|command\s+)+")
SPLIT = re.compile(r"&&|\|\||;|\||\n|\$\(|`|\(")
HEREDOC = re.compile(r"<<-?\s*['\"]?([A-Za-z_]+)['\"]?")
# A message to another agent quotes commands; it does not run them.
MESSAGE = re.compile(r"\s*(?:rtk\s+)?orca\s+(?:orchestration|terminal)\s+(?:send|ask|reply|dispatch)")
SKILL_DOC = re.compile(r"skills/(?:annotate|claude|codex)/(?:SKILL\.md|references/([a-z-]+)\.md)")
DOC_READER = re.compile(r"\b(?:cat|sed|head|tail|less|grep|rg|wc)\b")
SKILL_HEADER = "Base directory for this skill:"
DEV = re.compile(r"parrotfish|agent-annotate|skills-org")

FAIL_PATTERNS = [
    ("ERROR", re.compile(r"\bERROR\b")),
    ("FAIL", re.compile(r"\bFAIL(?:ED|S)?\b")),
    ("NOT PUBLISHED", re.compile(r"NOT PUBLISHED")),
    ("Traceback", re.compile(r"Traceback \(most recent")),
    ("fails closed", re.compile(r"fails? closed", re.I)),
    ("refused", re.compile(r"\brefus(?:ed|es|ing)\b", re.I)),
    ("lint-fail", re.compile(r"lint[^\n]*(?:error|fail|FAIL|✗)", re.I)),
    ("usage-error", re.compile(r"^usage: .*\n.*error:", re.M)),
]
# These print reviewer text or measurements, where "ERROR" is content, not an outcome.
QUOTING_SUBS = {"inbox", "cards", "open-cards", "eval", "cost", "watch", "monitor", "sessions"}
ROUND_CLOSERS = {"publish", "publish-version", "ask"}
FOLLOW_THROUGH = {"ask", "status", "cards", "open-cards"}
EXIT_CODE = re.compile(r"(?:Process exited with code|Exit code:)\s*(\d+)")


# --------------------------------------------------------------------------- #
# what a tool call ran
# --------------------------------------------------------------------------- #

def _segments(cmd: str):
    """Each simple command in a shell line, launchers stripped.

    Heredoc bodies are dropped: they are file content, and page markdown
    routinely mentions `annotate publish`.
    """
    lines, kept, i = cmd.split("\n"), [], 0
    while i < len(lines):
        kept.append(lines[i])
        m = HEREDOC.search(lines[i])
        i += 1
        if m:
            while i < len(lines) and lines[i].strip() != m.group(1):
                i += 1
            i += 1
    for part in SPLIT.split("\n".join(kept)):
        seg = WRAP.sub("", part.strip())
        if seg:
            yield seg


def invocations(cmd: str) -> list[tuple[str, str]]:
    """(subcommand, argument text) for every annotate CLI call in a shell command."""
    if MESSAGE.match(cmd):
        return []
    found = []
    for seg in _segments(cmd):
        m = SEG_CLI.match(seg) or SEG_PY.match(seg)
        if m:
            found.append((m.group(1), m.group(2).strip()))
    return found


def closes_round(sub: str, args: str) -> bool:
    return sub in ROUND_CLOSERS or (sub == "new" and bool(re.search(r"--(?:publish|ask)\b", args)))


def classify_command(cmd: str):
    """(kind, sub, args) for a shell command that ran annotate or read its docs.

    A chain is one tool call with one result, so it is one row, named after
    the call that publishes when there is one.
    """
    calls = invocations(cmd or "")
    if calls:
        sub, args = next(((s, a) for s, a in calls if closes_round(s, a)), calls[0])
        words = args.split()
        if "--help" in words or words[:1] == ["-h"]:
            return "doc", "help", args
        if sub == "new" and "--example" in words:
            return "doc", "example", args
        return "cli", sub, args
    m = SKILL_DOC.search(cmd or "")
    if m and DOC_READER.search(cmd):
        return "doc", "read:" + (m.group(1) or "SKILL"), ""
    return None


def _classify_claude_tool(name: str, inp: dict):
    if name == "Skill":
        return ("doc", "skill", "") if str(inp.get("skill", "")).split(":")[-1] == "annotate" else None
    if name == "Read":
        m = SKILL_DOC.search(inp.get("file_path") or "")
        return ("doc", "read:" + (m.group(1) or "SKILL"), "") if m else None
    if name in ("Bash", "Monitor"):
        return classify_command(inp.get("command") or "")
    return None


def _slug(args: str):
    words = args.split()
    tok = (words[0] if words else "").strip("'\"").rstrip("/")
    if not tok or tok.startswith("-"):
        return None
    tok = tok.rsplit("/", 1)[-1]
    return tok if re.fullmatch(r"[A-Za-z0-9._-]+", tok) else None


def _text(content) -> str:
    """Tool-result text from a string or a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text") or "" for b in content if isinstance(b, dict))
    return "" if content is None else str(content)


def failure(sub: str, text: str, is_error: bool, patterns: bool = True):
    """(reasons, error line) for a result; ([], None) when it succeeded.

    A doc read passes patterns=False: reference text is full of "ERROR" and
    "FAIL" examples, so only the tool's own error flag counts.
    """
    reasons = ["is_error"] if is_error else []
    if patterns and sub not in QUOTING_SUBS:
        reasons += [name for name, rx in FAIL_PATTERNS if rx.search(text)]
    if not reasons:
        return [], None
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("Exit code")]
    line = next((ln for ln in lines if "rror" in ln or any(rx.search(ln) for _, rx in FAIL_PATTERNS)),
                lines[0] if lines else "")
    return reasons, line[:200]


def reason_key(row: dict) -> str:
    """The error line with ids, slugs and counts blanked, so repeats group."""
    line = row.get("error") or ",".join(row.get("reasons") or [])
    m = re.search(r"['\"]error['\"]:\s*['\"]([^'\"]+)", line)
    if m:  # a server's JSON error: its message is the reason
        line = m.group(1)
    line = re.split(r"\bERROR:\s*", line)[-1]  # the message, not the progress line before it
    line = re.sub(r"[0-9a-f]{8,}", "…", line)
    line = re.sub(r"'[^'\s]+'", "'…'", line)
    return re.sub(r"\s+", " ", re.sub(r"\d+", "N", line)).strip()


def _when(ts):
    try:
        return dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def _row(base: dict, line: dict, kind: str, sub: str, args: str) -> dict:
    when = _when(line.get("timestamp"))
    return {**base, "ts": line.get("timestamp"),
            "date": when.astimezone().date().isoformat() if when else None,
            "cwd": line.get("cwd") or base.get("cwd") or "",
            "kind": kind, "sub": sub, "slug": _slug(args) if kind == "cli" else None,
            "closes_round": kind == "cli" and closes_round(sub, args),
            "args": args[:160], "result_tokens": 0, "out_tokens": 0.0, "secs": None,
            "failed": False, "reasons": [], "error": None, "retry_out_tokens": None}


def _finish(row: dict, text: str, is_error: bool, end_ts) -> None:
    row["result_tokens"] = len(text) // 4
    start, end = _when(row["ts"]), _when(end_ts)
    if start and end:
        row["secs"] = round((end - start).total_seconds(), 1)
    row["reasons"], row["error"] = failure(row["sub"], text, is_error, patterns=row["kind"] == "cli")
    row["failed"] = bool(row["reasons"])


# --------------------------------------------------------------------------- #
# transcripts
# --------------------------------------------------------------------------- #

def _recent(path: Path, since: dt.date) -> bool:
    try:
        return dt.date.fromtimestamp(path.stat().st_mtime) >= since
    except OSError:
        return False


def _claude_rows(raw: bytes, base: dict, seen: set) -> list[dict]:
    msgs = {}      # message.id -> [max output_tokens, {tool_use ids}]
    pending = {}   # tool_use id -> (row, message.id)
    rows, mids, skill = [], [], None
    header = SKILL_HEADER.encode()
    for line in raw.splitlines():
        # Parsing is the whole cost of a scan: only assistant lines, and user
        # lines that answer a call we kept or load the skill text, matter.
        if b'"assistant"' not in line and not (b'"user"' in line and (
                header in line or any(t.encode() in line for t in pending))):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        msg = d.get("message") if isinstance(d.get("message"), dict) else {}
        content = msg.get("content")
        if d.get("type") == "assistant":
            mid = msg.get("id") or d.get("uuid")
            rec = msgs.setdefault(mid, [0, set()])
            rec[0] = max(rec[0], (msg.get("usage") or {}).get("output_tokens") or 0)
            for b in content if isinstance(content, list) else []:
                if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                    continue
                rec[1].add(b.get("id"))
                hit = _classify_claude_tool(b.get("name"), b.get("input") or {})
                if hit and b.get("id") not in seen:  # a forked transcript repeats its parent
                    seen.add(b.get("id"))
                    pending[b["id"]] = (_row(base, d, *hit), mid)
        elif d.get("type") == "user":
            blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_result" and b.get("tool_use_id") in pending:
                    row, mid = pending.pop(b["tool_use_id"])
                    _finish(row, _text(b.get("content")), bool(b.get("is_error")), d.get("timestamp"))
                    rows.append(row)
                    mids.append(mid)
                    skill = row if row["sub"] == "skill" else skill
                elif b.get("type") == "text" and str(b.get("text") or "").startswith(SKILL_HEADER):
                    text = b["text"]
                    if "/annotate" not in text.split("\n", 1)[0] or d.get("uuid") in seen:
                        continue
                    seen.add(d.get("uuid"))
                    if skill is not None:  # the Skill call's result is one line; this is the load
                        skill["result_tokens"] += len(text) // 4
                        skill = None
                    else:                  # typed as /annotate: no call, no issuing turn
                        row = _row(base, d, "doc", "skill", "")
                        _finish(row, text, False, d.get("timestamp"))
                        rows.append(row)
                        mids.append(None)
    for row, mid in zip(rows, mids):
        out, calls = msgs.get(mid, (0, ()))
        row["out_tokens"] = round(out / max(len(calls), 1), 1)
    return rows


def scan_claude(root: Path, since: dt.date, seen: set) -> list[dict]:
    """Rows from <root>/<project>/<session>.jsonl and every subagent file beneath."""
    rows = []
    for path in sorted(root.rglob("*.jsonl")):
        parts = path.relative_to(root).parts
        if len(parts) < 2 or not _recent(path, since):
            continue
        base = {"source": "claude", "project": parts[0], "session": Path(parts[1]).stem,
                "subagent": len(parts) > 2, "file": str(path)}
        rows += _claude_rows(path.read_bytes(), base, seen)
    return rows


def _codex_command(p: dict) -> str:
    """The shell text a Codex tool call ran: exec_command/shell arguments, or
    the exec_command calls inside a JS `exec` cell."""
    if p.get("type") == "custom_tool_call":
        cmds = []
        for lit in re.findall(r'"cmd"\s*:\s*("(?:[^"\\]|\\.)*")', p.get("input") or ""):
            try:
                cmds.append(json.loads(lit))
            except ValueError:
                pass
        return "\n".join(cmds)
    try:
        args = json.loads(p.get("arguments") or "{}")
    except ValueError:
        return ""
    if not isinstance(args, dict):
        return ""
    cmd = args.get("cmd") or args.get("command") or ""
    if isinstance(cmd, list):
        cmd = cmd[-1] if len(cmd) >= 3 and cmd[-2] in ("-c", "-lc") else " ".join(map(str, cmd))
    return cmd if isinstance(cmd, str) else ""


def _codex_rows(raw: bytes, base: dict, seen: set) -> list[dict]:
    rows, pending, out_of, issued = [], {}, {}, []
    for line in raw.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        p = d.get("payload") if isinstance(d.get("payload"), dict) else {}
        kind = p.get("type")
        if d.get("type") in ("session_meta", "turn_context") and p.get("cwd"):
            base = {**base, "cwd": p["cwd"], "project": p["cwd"].replace("/", "-")}
            if d["type"] == "session_meta":
                base["session"] = p.get("id") or base["session"]
        elif kind in ("function_call", "custom_tool_call"):
            cid = p.get("call_id")
            issued.append(cid)
            hit = classify_command(_codex_command(p))
            if hit and cid not in seen:
                seen.add(cid)
                pending[cid] = _row(base, d, *hit)
        elif kind in ("function_call_output", "custom_tool_call_output") and p.get("call_id") in pending:
            row = pending.pop(p["call_id"])
            text = _text(p.get("output"))
            code = EXIT_CODE.search(text[:400])
            if "\nOutput:\n" in text[:400]:  # drop the exec header (chunk id, wall time, exit code)
                text = text.split("\nOutput:\n", 1)[1]
            _finish(row, text, bool(code and code.group(1) != "0"), d.get("timestamp"))
            row["call_id"] = p["call_id"]
            rows.append(row)
        elif issued and (d.get("type") == "token_usage_record" or kind == "token_count"):
            # The first usage after a call is the response that issued it;
            # a second record of the same response finds nothing issued.
            usage = p.get("usage") or (p.get("info") or {}).get("last_token_usage") or {}
            if "output_tokens" in usage:
                for cid in issued:
                    out_of[cid] = usage["output_tokens"] / len(issued)
                issued = []
    for row in rows:
        row["out_tokens"] = round(out_of.get(row.pop("call_id"), 0), 1)
    return rows


def scan_codex(root: Path, since: dt.date, seen: set) -> list[dict]:
    rows = []
    for path in sorted(root.rglob("*.jsonl")):
        if not _recent(path, since):
            continue
        raw = path.read_bytes()
        if b"annotate" in raw:  # Codex sessions carry no skill listing, so this skips most
            base = {"source": "codex", "project": "", "session": path.stem, "subagent": False,
                    "file": str(path)}
            rows += _codex_rows(raw, base, seen)
    return rows


def link_retries(rows: list[dict]) -> None:
    """Give each failed CLI row the out_tokens of the next call of the same
    subcommand (and slug, when both name one) in its transcript: the turn a
    fix would have saved. 0 when the agent never retried."""
    by_file = collections.defaultdict(list)
    for r in rows:
        if r["kind"] == "cli":
            by_file[r["file"]].append(r)
    for rs in by_file.values():
        for i, r in enumerate(rs):
            if r["failed"]:
                nxt = next((x for x in rs[i + 1:] if x["sub"] == r["sub"]
                            and (not r["slug"] or not x["slug"] or x["slug"] == r["slug"])), None)
                r["retry_out_tokens"] = nxt["out_tokens"] if nxt else 0.0


def rounds(rows: list[dict]) -> list[list[dict]]:
    """Closed rounds: per transcript and slug, the CLI calls up to and
    including a successful publish, publish-version, ask or new --publish.

    A call that names no slug joins the transcript's last one. An ask, status
    or cards within five minutes of a close is the same round's follow-through
    (publish, then post its cards), not a round of its own. A round that never
    closed is left out, so an abandoned page does not read as a slow one.
    """
    done, open_, closed, last = [], {}, {}, {}
    for r in rows:
        if r["kind"] != "cli":
            continue
        slug = r["slug"] or last.get(r["file"])
        last[r["file"]] = slug
        key = (r["file"], slug)
        prev = closed.get(key)
        if key not in open_ and prev and r["sub"] in FOLLOW_THROUGH and _gap(prev[-1], r) < 300:
            prev.append(r)
            continue
        open_.setdefault(key, []).append(r)
        if r["closes_round"] and not r["failed"]:
            closed[key] = open_.pop(key)
            done.append(closed[key])
    return done


def _gap(a: dict, b: dict) -> float:
    start, end = _when(a["ts"]), _when(b["ts"])
    return (end - start).total_seconds() if start and end else float("inf")


def collect(args) -> list[dict]:
    """Every row in the window, in transcript order, dev sessions filtered."""
    since = dt.date.fromisoformat(args.since)
    root = Path(args.root).expanduser() if args.root else Path(TRANSCRIPT_GLOB.split("*", 1)[0])
    seen: set = set()
    rows = scan_claude(root, since, seen) if root.is_dir() else []
    if args.codex:
        codex = (Path(args.codex_root).expanduser() if args.codex_root
                 else Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex") / "sessions")
        rows += scan_codex(codex, since, seen) if codex.is_dir() else []
    link_retries(rows)
    for r in rows:
        r["dev"] = bool(DEV.search(r["cwd"]) or DEV.search(r["project"]))
    return [r for r in rows if r["date"] and r["date"] >= args.since and (args.include_dev or not r["dev"])]


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #

def _pct(values, q):
    """Linear-interpolated percentile, so a p90 over a few calls is not just the max."""
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    k = (len(v) - 1) * q
    f = int(k)
    c = min(f + 1, len(v) - 1)
    return v[f] + (v[c] - v[f]) * (k - f)


def _k(n) -> str:
    if n is None:
        return "—"
    n = float(n)
    if abs(n) >= 1e6:
        return f"{n / 1e6:.1f}M"
    if abs(n) >= 1e3:
        return f"{n / 1e3:.1f}k"
    return f"{n:.0f}"


def _release_cuts() -> list[tuple[str, str]]:
    """(date, version) from the dated CHANGELOG headings; the newest heading wins a shared date."""
    changelog = PACKAGE_DIR.parents[1] / "CHANGELOG.md"
    if not changelog.is_file():
        raise ValueError(f"--by release reads {changelog}, which this install lacks; pass --by D1,D2")
    cuts = {}
    for m in re.finditer(r"^## (v[\d.]+)\b[^\n]*?\((\d{4}-\d{2}-\d{2})", changelog.read_text(), re.M):
        cuts.setdefault(m.group(2), m.group(1))
    return sorted(cuts.items())


def period_of(by: str):
    """date string -> period label: Monday of the week, the release in force, or a cut date."""
    if by == "week":
        def week(d):
            day = dt.date.fromisoformat(d)
            return (day - dt.timedelta(days=day.weekday())).isoformat()
        return week
    cuts = _release_cuts() if by == "release" else [(c, "from " + c) for c in sorted(by.split(","))]
    for c, _ in cuts:
        dt.date.fromisoformat(c)

    def label(d):
        return next((name for c, name in reversed(cuts) if d >= c), "before " + cuts[0][1].removeprefix("from "))
    return label


def report(rows: list[dict], by: str) -> list[str]:
    cli = [r for r in rows if r["kind"] == "cli"]
    closed = rounds(rows)
    label = period_of(by)
    per = collections.OrderedDict()
    for r in sorted(rows, key=lambda r: r["ts"] or ""):
        per.setdefault(label(r["date"]), ([], []))[0].append(r)
    for rd in closed:
        per[label(rd[-1]["date"])][1].append(rd)

    failed = [r for r in cli if r["failed"]]
    sessions = {(r["source"], r["session"]) for r in rows}
    out = [f"  {len(cli):,} annotate calls + {len(rows) - len(cli):,} doc reads in {len(sessions)} "
           f"sessions; {len(closed)} closed rounds",
           f"  output {_k(sum(r['out_tokens'] for r in rows))} tok, results "
           f"{_k(sum(r['result_tokens'] for r in rows))} tok; "
           f"{100 * len(failed) / max(len(cli), 1):.1f}% of calls failed, the retries after them "
           f"{_k(sum(r['retry_out_tokens'] or 0 for r in failed))} output tok", ""]

    def med(xs):
        return statistics.median(xs) if xs else None

    head = "week of" if by == "week" else "period"
    out.append(f"  {head:<16} {'calls':>6} {'docs':>5} {'fail%':>6} {'out':>7} {'result':>7} "
               f"{'rounds':>6} {'calls/rd':>8} {'out/rd':>7} {'min/rd':>6}")
    for name, (rs, rds) in per.items():
        c = [r for r in rs if r["kind"] == "cli"]
        m_min = med([(_when(rd[-1]["ts"]) - _when(rd[0]["ts"])).total_seconds() / 60 for rd in rds])
        out.append(
            f"  {name:<16} {len(c):>6} {len(rs) - len(c):>5} "
            f"{100 * sum(r['failed'] for r in c) / max(len(c), 1):>5.1f}% "
            f"{_k(sum(r['out_tokens'] for r in rs)):>7} {_k(sum(r['result_tokens'] for r in rs)):>7} "
            f"{len(rds):>6} {_k(med([len(rd) for rd in rds])):>8} "
            f"{_k(med([sum(r['out_tokens'] for r in rd) for rd in rds])):>7} "
            f"{'—' if m_min is None else f'{m_min:.1f}':>6}")

    by_sub = collections.defaultdict(list)
    for r in rows:
        by_sub[r["sub"]].append(r)
    ranked = sorted(by_sub.items(), key=lambda kv: -sum(r["out_tokens"] + r["result_tokens"] for r in kv[1]))
    out += ["", f"  {'subcommand':<22} {'calls':>5} {'result p50':>10} {'p90':>6} {'secs p50':>8} "
                f"{'fail':>4}  top failures"]
    for sub, rs in ranked[:15]:
        reasons = collections.Counter(reason_key(r) for r in rs if r["failed"]).most_common(3)
        secs = _pct([r["secs"] for r in rs], .5)
        out.append(f"  {sub:<22} {len(rs):>5} {_k(_pct([r['result_tokens'] for r in rs], .5)):>10} "
                   f"{_k(_pct([r['result_tokens'] for r in rs], .9)):>6} "
                   f"{'—' if secs is None else f'{secs:.1f}':>8} {sum(r['failed'] for r in rs):>4}  "
                   + " · ".join(f"{k[:40]} ×{n}" for k, n in reasons))
    if len(ranked) > 15:
        out.append(f"  … {len(ranked) - 15} more (--json)")
    return out


# --------------------------------------------------------------------------- #
# estimate
# --------------------------------------------------------------------------- #

def replay(rows: list[dict], model: dict):
    """Per-subcommand tokens before and after a change, and what it touched.

    model: {"<sub>": {"result_tokens": N}} — every successful result of that
    subcommand (or doc row: "skill", "read:SKILL", "help") becomes N tokens;
    {"<regex>": "fixed"} — failures whose error line matches never happen, so
    their result and their retry turn's output are saved.

    Returns (before, after, rows changed per sub, rows matched per model key).
    """
    sizes = {k: v["result_tokens"] for k, v in model.items() if isinstance(v, dict) and "result_tokens" in v}
    fixed = {k: re.compile(k, re.I) for k, v in model.items() if v == "fixed"}
    bad = sorted(set(model) - set(sizes) - set(fixed))
    if bad:
        raise ValueError(f'unrecognised model entries {bad}: use {{"<sub>": {{"result_tokens": N}}}} '
                         f'or {{"<error regex>": "fixed"}}')
    before, after = collections.Counter(), collections.Counter()
    hits, matched = collections.Counter(), collections.Counter({k: 0 for k in model})
    for r in rows:
        tokens = r["out_tokens"] + r["result_tokens"]
        before[r["sub"]] += tokens
        text = f"{r['error'] or ''} {' '.join(r['reasons'])}"
        key = next((k for k, x in fixed.items() if r["failed"] and x.search(text)), None)
        if key:
            tokens -= r["result_tokens"] + (r["retry_out_tokens"] or 0)
        elif not r["failed"] and r["sub"] in sizes:
            key = r["sub"]
            tokens += sizes[key] - r["result_tokens"]
        if key:
            hits[r["sub"]] += 1
            matched[key] += 1
        after[r["sub"]] += tokens
    return before, after, hits, matched


def estimate(rows: list[dict], model: dict) -> list[str]:
    """Replay the window under a change and print before/after tokens."""
    before, after, hits, matched = replay(rows, model)
    sizes = {k: v["result_tokens"] for k, v in model.items() if isinstance(v, dict)}
    fixed = [k for k, v in model.items() if v == "fixed"]
    out = []
    for sub, n in sizes.items():
        now = _pct([r["result_tokens"] for r in rows if r["sub"] == sub and not r["failed"]], .5)
        out.append(f"  assume  {sub}: each successful result becomes {n} tok "
                   f"({matched[sub]} rows, median now {_k(now)})")
    for k in fixed:
        out.append(f"  assume  /{k}/ fixed: {matched[k]} failed rows lose their result and their "
                   f"retry turn's output")
    out += ["  assume  tokens = issuing turn's output + result chars/4, each counted once",
            "  ignore  cache re-reads, turns spent diagnosing before a retry, turns with no tool call",
            "", f"  {'scope':<22} {'rows':>5} {'before':>8} {'after':>8} {'delta':>8}"]

    def line(name, n, b, a):
        pct = f" ({100 * (a - b) / b:+.1f}%)" if b else ""
        return f"  {name:<22} {n:>5} {_k(b):>8} {_k(a):>8} {_k(a - b):>8}{pct}"

    out.append(line("all", sum(hits.values()), sum(before.values()), sum(after.values())))
    for sub in sorted(hits, key=lambda s: after[s] - before[s]):
        out.append(line(sub, hits[sub], before[sub], after[sub]))
    return out


def run(args) -> int:
    if not args.since:
        args.since = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    try:
        dt.date.fromisoformat(args.since)
        model = json.loads(Path(args.estimate).expanduser().read_text()) if args.estimate else None
        if model is not None and not isinstance(model, dict):
            raise ValueError("the estimate model must be a JSON object")
        rows = collect(args)
        if args.json:
            print("[" + ",\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "]")
            return 0
        body = estimate(rows, model) if model is not None else report(rows, args.by)
    except (OSError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    sources = "claude + codex" if args.codex else "claude"
    dev = "dev sessions kept" if args.include_dev else "dev sessions excluded (--include-dev)"
    what = f"estimate from {args.estimate}" if model is not None else "annotate cost"
    print(f"{what} — {sources} transcripts since {args.since}, {dev}")
    print("\n".join(body))
    return 0
