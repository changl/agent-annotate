"""Reference tab data: the page's plans by topic, the go-live checklist, Windmill workflows and the project's documents.

Reads the page dir; reads the FastLane Drive board (bd --readonly), its project folder and the round-9 Windmill
snapshot, all read only. Writes nothing.
"""
from __future__ import annotations

import html
import json
import os
import re
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from ..categories import is_archive_plan, list_plans
from ..plan_topics import file_plans
from . import scrub

FLD_MAIN = Path("/Users/changlee/projects/FastLane Drive/fld-main")
FLD_DIR = Path("/Users/changlee/projects/FastLane Drive")
# shortcut: the round-9 snapshot of `wmill flow get` / `job get` (build/r9_wmflows.py); read Windmill live when the prototype graduates
WM_FLOWS = Path("/Users/changlee/projects/agent-annotate/shared/agents/uiux-lead-20261116/round9/final/build/wm-flows.json")

BEAD = re.compile(r"\bFLD-[a-z0-9]{3,6}(?:\.\d+)*\b")
PHONE = re.compile(r"(?<!\d)(?:\+\d{1,3}[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}(?!\d)")


def hide(s: str) -> str:
    """No email address, review key or phone number leaves this module."""
    return PHONE.sub("a phone number", scrub(s))


def plain(s: str, n: int = 200) -> str:
    t = hide(re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip())
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


_board: dict = {"at": 0.0, "beads": {}}
_board_lock = threading.Lock()


def board() -> dict:
    """{id: [title, state]} from the FastLane Drive board, read only, cached a minute."""
    with _board_lock:  # one read at a time: overlapping requests wait and share it
        return _board_read()


def _board_read() -> dict:
    if time.time() - _board["at"] > 60:
        try:
            out = subprocess.run(["bd", "-C", str(FLD_MAIN), "--readonly", "list", "--all", "--limit", "0", "--brief", "--flat", "--json"],
                                 capture_output=True, text=True, timeout=20, check=True).stdout
            _board["beads"] = {b["id"]: [hide(b.get("title") or ""), (b.get("status") or "").replace("_", " ")] for b in json.loads(out)}
        except (OSError, subprocess.SubprocessError, ValueError):
            pass  # no board: task lines show the id alone
        _board["at"] = time.time()
    return _board["beads"]


def state_of(plan: dict) -> str:
    """Proposed waits on him, Approved was decided, the rest stand for reference."""
    if plan.get("section") == "approved":
        return "ok"
    return "prop" if re.search(r"\b(draft|proposal|proposed)\b", plan.get("title") or "", re.I) else "ref"


def checklist(page_dir: Path) -> dict | None:
    """The go-live checklist plan's status table, one row per item: [platform, item, state, who, bead]."""
    vd = page_dir / "plans" / "go-live-checklist" / "versions"
    files = sorted(vd.glob("v*.html"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0)) if vd.is_dir() else []
    if not files:
        return None
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", files[-1].read_text(errors="ignore"), re.S):
        td = [plain(c, 120) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(td) >= 5 and td[2] in ("done", "in progress", "not started", "blocked"):
            bead = (BEAD.findall(tr) or [""])[0]
            rows.append([td[0], re.sub(r"\s+A\d\d\b.*$", "", td[1]), td[2], td[3], bead])
    return {"plan": "go-live-checklist", "version": files[-1].stem,
            "when": datetime.fromtimestamp(files[-1].stat().st_mtime).strftime("%Y-%m-%d"), "items": rows}


# Windmill's step summaries said plainly (from round 9's build.py): [name, when, what it does, {step id: plain name}]
FLOWS = {
    "f/sweep/board_checks": ["Hourly board checks", "every hour", "Checks the FastLane Drive bead board for stuck or wrongly settled tasks. It changes nothing unless its apply switch is on. No AI.",
                             {"prepare": "Pick a dated folder for this run", "checks": "Run the board checks on the M1 Max", "result": "Return the findings", "failure": "Write one line to the error log"}],
    "f/sweep/member_sheet_check": ["Members sheet check", "every 2 hours", "Reads the members sheet and the open invitations, and tells the coordinator once about each new problem. It writes no member data. No AI.",
                                   {"prepare": "Pick a dated folder for this run", "checks": "Run the read-only sheet check on the Mac", "result": "Return the counts and new problems"}],
    "f/sweep/sweep_trigger": ["Six-hourly board sweep", "every 6 hours", "A lighter read-only pass over the bead board between the hourly checks. No AI.",
                              {"prepare": "Pick a folder for this run", "checks": "Run the read-only board checks on the Mac", "result": "Return the result", "failure": "Write one line to the error log"}],
    "f/sweep/admin_todo_check": ["Admin to-do sheet check", "every day", "Reads the admin team's to-do sheet and reports what changed. Report only. No AI.",
                                 {"prepare": "Pick a dated folder for this run", "checks": "Run the read-only to-do check on the Mac", "result": "Return the findings", "failure": "Write one line to the error log"}],
    "f/test/change": ["Test one app change", "on each pushed change", "Tests one change to an app: checks the test Mac, lets rules pick the tests, runs them, reruns failures once, and sorts the results. An AI agent looks only at a new kind of failure.",
                      {"validate": "Check the request", "setup": "Check the test Mac: simulator, disk, checkout", "setup_out": "Read the Mac check", "gate": "Skip if the Mac is not ready or this change already passed",
                       "tests": "Pick, run, rerun once, sort", "pick": "Check out the change and plan which tests to run", "pick_out": "Read the plan", "plan": "Log the plan",
                       "run": "Run the tests on the ready test Mac", "first": "Read the run and pick failures for one rerun", "rerun": "Rerun the failures once", "rerun_out": "Read the rerun",
                       "classify": "Sort the failures by rules, no AI", "not_run": "Record why nothing ran", "make_report": "Write the receipt", "report": "Save the receipt on the M1 Max",
                       "report_out": "Read where it was saved", "commit_status": "Post a pass or fail mark on GitHub (off unless asked)", "agent": "New kind of failure only: an AI agent names the cause and files one task",
                       "agent_out": "Read the agent's finding", "result": "Give the verdict and the receipt"}],
    "f/uat/suite": ["Acceptance test suite", "on request", "Runs the chosen acceptance tests on the M5 Max, in order where one needs another, and brings back the results with pictures.",
                    {"host": "Run the tests on the M5 Max and wait, holding no worker", "result": "Bring back the results and pictures"}],
    "f/build/item": ["Build one work item", "on request", "From a written spec to working software: tests first, then rounds of build, check and review until both pass, then your sign-off.",
                     {"prep": "Check the code folder and the spec", "tests": "An AI agent writes the acceptance tests first", "tests_done": "Read the test writer's result", "freeze": "Lock the tests; they must fail before anything is built",
                      "freeze_done": "Check they fail", "rounds": "Build, check and review, up to 3 rounds", "build": "An AI agent builds and deploys", "build_done": "Read the build result",
                      "amend": "Only if the builder found problems in the tests", "amend_tests": "The test writer rules on them and fixes the tests", "amend_done": "Read the fix", "refreeze": "Lock the fixed tests again",
                      "refreeze_done": "Read the lock", "verify": "Check: tests unchanged, unit and acceptance tests pass", "verify_done": "Read the check", "review": "A second AI agent checks it does what was meant",
                      "judge": "Decide: done, or another round", "outcome": "Sum up the rounds", "signoff": "Waits for your sign-off", "finish": "Close it, or start a rework run with your note"}],
}
AGENT_STEPS = {"tests", "build", "amend_tests", "review", "agent"}


def _steps(path: str, modules: list, last: dict) -> list:
    out = []
    for m in modules or []:
        s = last.get(m["id"]) or {}
        step = {"id": m["id"], "n": FLOWS[path][3].get(m["id"]) or plain(m.get("summary") or m["id"], 80), "t": m.get("type", ""),
                "wait": bool(m.get("suspend")), "stop": bool(m.get("stop_if")),
                "ai": m["id"] in AGENT_STEPS and m.get("type") == "script" and not (path == "f/test/change" and m["id"] == "tests"),
                "st": "" if not s else "skipped" if s.get("skipped") else {"Success": "ok", "Failure": "fail"}.get(s.get("type"), "")}
        if m.get("modules") is not None:
            step["sub"] = _steps(path, m["modules"], {})
        if m.get("branches") is not None:
            chosen = s.get("branch_chosen") or {}
            step["br"] = [[plain(b.get("summary") or "", 60) or "If", _steps(path, b.get("modules"), {}),
                           bool(s) and chosen.get("type") == "branch" and chosen.get("branch") == i] for i, b in enumerate(m["branches"])]
            step["br"].append(["Otherwise", _steps(path, m.get("default"), {}), bool(s) and chosen.get("type") == "default"])
        out.append(step)
    return out


def flows() -> list:
    try:
        raw = json.loads(WM_FLOWS.read_text())
    except (OSError, ValueError):
        return []
    out = []
    for path, f in raw.items():
        if path not in FLOWS:
            continue
        last = f.get("last") or {}
        steps = {s["id"]: s for s in last.get("steps") or []}
        out.append({"id": "flow:" + path.split("/")[-1], "t": FLOWS[path][0], "when": FLOWS[path][1], "what": FLOWS[path][2],
                    "edited": (f.get("edited_at") or "")[:10], "steps": _steps(path, f.get("modules"), steps),
                    "fail": _steps(path, f.get("failure") or [], {}), "queued": f.get("queued") or 0,
                    "last": {"at": (last.get("started_at") or "")[:16].replace("T", " "), "ok": last.get("success"),
                             "s": round((last.get("duration_ms") or 0) / 1000)} if last else None})
    return out


DOC_EXT = {".md": "md", ".pdf": "pdf", ".docx": "word", ".doc": "word", ".csv": "sheet", ".xlsx": "sheet", ".mov": "video", ".mp4": "video"}
DOC_SKIP = {"orchestration", "evidence", "node_modules", ".git", "archive", "tools", "usage-reports"}
DOC_GROUPS = {"": "Project folder", "planning": "Planning", "design": "Design", "analysis": "Analysis", "outputs": "Audits and outputs"}
MD_INLINE = 120_000  # a longer Markdown file is listed but opens nowhere


def documents(root: Path = FLD_DIR) -> dict:
    """This project's own document files (his #111): planning, design, analysis and outputs, two folders deep.
    Markdown carries its text (emails and phone numbers masked) so it opens in place."""
    files = []
    if not root.is_dir():
        return {"files": files, "groups": {}}
    for d, ds, fs in os.walk(root):
        rel = Path(d).relative_to(root)
        top = rel.parts[0] if rel.parts else ""
        if rel.parts and top not in ("planning", "design", "analysis", "outputs"):  # app checkouts, keys, member data, agent notes
            ds[:] = []
            continue
        ds[:] = sorted(x for x in ds if x not in DOC_SKIP and not x.startswith(("run_", ".")))
        if len(rel.parts) >= 3:
            ds[:] = []
        for name in sorted(fs):
            p, kind = Path(d) / name, DOC_EXT.get(Path(name).suffix.lower())
            if not kind or name in ("AGENTS.md", "CLAUDE.md") or ".bak" in name:
                continue
            st = p.stat()
            group = "/".join(rel.parts[:2]) if top == "planning" and len(rel.parts) > 1 else top
            row = {"n": hide(name), "g": group, "sub": "/".join(rel.parts[(2 if top == "planning" else 1):]), "k": kind,
                   "kb": max(1, round(st.st_size / 1024)), "d": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d")}
            if kind == "md" and st.st_size <= MD_INLINE:
                row["md"] = hide(p.read_text(errors="ignore"))
            files.append(row)
    groups = {g: DOC_GROUPS.get(g) or g.split("/")[-1].replace("-", " ").capitalize() for g in {f["g"] for f in files}}
    return {"files": files, "groups": groups}


def build(page_dir: Path) -> dict:
    page_dir = Path(page_dir)
    plans = list_plans(page_dir)
    topics = file_plans(page_dir, plans)
    out, ids = [], set()
    for p in plans:
        if p.get("section") == "hidden" or is_archive_plan(p):
            continue
        hist = [h for h in p.get("history") or [] if h.get("version")]
        if not hist:
            continue
        title = hide(p.get("title") or p["id"])
        for h in hist[-2:]:  # the bead ids the two newest revisions name
            f = page_dir / "plans" / p["id"] / "versions" / f"{h['version']}.html"
            if f.is_file():
                ids.update(BEAD.findall(f.read_text(errors="ignore")))
        out.append({"id": p["id"], "t": title, "topic": p.get("topic") or "Unsorted", "st": state_of(p),
                    "kind": "check" if re.search(r"checklist", title, re.I) else "plan", "current": p.get("current") or hist[-1]["version"],
                    "revs": [[h["version"], (h.get("ts") or "")[:16], plain(h.get("label") or "", 120)] for h in hist]})
    cl = checklist(page_dir)
    if cl:
        ids.update(r[4] for r in cl["items"] if r[4])
    beads = board()
    return {"plans": out, "topics": topics, "checklist": cl, "flows": flows(), "docs": documents(),
            "beads": {i: beads[i] for i in sorted(ids) if i in beads}, "notes": notes(page_dir)}


NOTE_ANCHORS = ("ref:", "doc:", "chk:")


def notes(page_dir: Path) -> list:
    """The notes written in Reference (anchors ref:, doc:, chk:), oldest first, so each shows at its line."""
    from ..categories import _comments
    out = []
    for anchor, items in (_comments(page_dir).get("anchors") or {}).items():
        if not anchor.startswith(NOTE_ANCHORS):
            continue
        for c in items:
            if c.get("status") in ("deleted",):
                continue
            out.append({"id": c.get("id"), "a": anchor, "text": hide(c.get("text") or ""), "who": c.get("author_name") or "You",
                        "at": (c.get("created_at") or "")[:16], "v": c.get("version"), "st": c.get("status")})
    return sorted(out, key=lambda n: n["at"])
