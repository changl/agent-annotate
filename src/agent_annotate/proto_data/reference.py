"""Reference tab data: the page's plans by topic, the go-live checklist, Windmill workflows and the project's files and findings.
(The project's documents are listed in Pages & links only; documents() serves it.)

Reads the page dir; reads the page's own project's board (bd --readonly), FastLane Drive's project folder and the round-9 Windmill
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
from . import running, scrub
from .questions import _mine

FLD_DIR = Path("/Users/changlee/projects/FastLane Drive")
# shortcut: the round-9 snapshot of `wmill flow get` / `job get` (build/r9_wmflows.py); read Windmill live when the prototype graduates
WM_FLOWS = Path("/Users/changlee/projects/agent-annotate/shared/agents/uiux-lead-20261116/round9/final/build/wm-flows.json")

BEAD = re.compile(r"\b(?:FLD|RBX|agent-annotate)-[a-z0-9]{3,6}(?:\.\d+)*\b")  # each copied project's bead ids
PHONE = re.compile(r"(?<!\d)(?:\+\d{1,3}[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}(?!\d)")


def hide(s: str) -> str:
    """No email address, review key or phone number leaves this module."""
    return PHONE.sub("a phone number", scrub(s))


def plain(s: str, n: int = 200) -> str:
    t = hide(re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip())
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + "…"


_boards: dict = {}  # project tag -> {"at", "beads"}
_board_lock = threading.Lock()


def board(code: str = "fld") -> dict:
    """{id: [title, state]} from this project's own board (Running's lookup: `bd where` in its checkout), read only,
    cached a minute. A project with no board it can reach gets none: never another project's titles.
    The list takes 2-14 s, so only the first read waits; past a minute the last list answers and a new one runs in the background."""
    c = _boards.get(code)
    if c is None or not c["at"]:  # never read yet, or the first read is on its way
        with _board_lock:  # one read at a time: overlapping requests wait and share it
            return _board_read(code)
    if time.time() - c["at"] > 60 and _board_lock.acquire(blocking=False):
        def again():
            try:
                _board_read(code)
            finally:
                _board_lock.release()
        threading.Thread(target=again, daemon=True).start()
    return c["beads"]


def _board_read(code: str) -> dict:
    c = _boards.setdefault(code, {"at": 0.0, "beads": {}})
    if time.time() - c["at"] > 60:
        where = running.board_dir(code)
        try:
            if where is None:
                raise ValueError("no board")
            out = subprocess.run(["bd", "-C", str(where), "--readonly", "list", "--all", "--limit", "0", "--brief", "--flat", "--json"],
                                 capture_output=True, text=True, timeout=20, check=True).stdout
            c["beads"] = {b["id"]: [hide(b.get("title") or ""), (b.get("status") or "").replace("_", " ")] for b in json.loads(out)}
        except (OSError, subprocess.SubprocessError, ValueError):
            pass  # no board: task lines show the id alone
        c["at"] = time.time()
    return c["beads"]


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


DOC_PIC = "proto/doc/"  # where the page serves a document's picture (proto_data.serve)
_PIC_LINE = re.compile(r"^(\s*!\[[^\]\n]*\]\(\s*)([^)\s]+)(\s*\)\s*)$", re.M)  # a picture on its own line, as pagegen._IMAGE
_TABLE_LINE = re.compile(r"^\s*\|.*$", re.M)
_PIC_CELL = re.compile(r"(!\[[^\]\n]*\]\(\s*)([^)\s]+)(\s*\))")  # each picture in a table cell, as pagegen._CELL_IMAGE


def doc_picture(rel: str, root: Path = FLD_DIR) -> Path | None:
    """The picture file at rel under the project's document folders (planning, design, analysis, outputs), or None:
    an image of at most 10 MB, as today's release takes, inside the folder, never a hidden one."""
    from ..images import IMAGE_SUFFIXES, MAX_IMAGE_BYTES
    parts = Path(rel).parts
    if not parts or parts[0] not in ("planning", "design", "analysis", "outputs") or any(p.startswith(".") or p == ".." for p in parts):
        return None
    p = root / rel
    try:
        real, top = p.resolve(), root.resolve()
        ok = real.is_relative_to(top) and real.suffix.lower() in IMAGE_SUFFIXES and real.is_file() and real.stat().st_size <= MAX_IMAGE_BYTES
    except OSError:
        return None
    return p if ok else None


def doc_pictures(text: str, md: Path, root: Path = FLD_DIR) -> str:
    """Each picture line's file found as today's release finds it (pagegen.ImageStore: relative to the Markdown file's folder,
    or an absolute path), linked to where the page serves it; a URL or a file not found keeps its description only."""
    import urllib.parse

    def one(m: re.Match) -> str:
        ref, url = m[2], ""
        if not re.match(r"^(?:[A-Za-z][A-Za-z0-9+.-]*:|//)", ref):
            p = Path(urllib.parse.unquote(ref)).expanduser()
            p = p if p.is_absolute() else md.parent / p
            try:
                rel = Path(os.path.normpath(p)).relative_to(root).as_posix()
            except ValueError:
                rel = ""
            if rel and doc_picture(rel, root):
                url = DOC_PIC + urllib.parse.quote(rel)
        return m[1] + url + m[3]
    return _TABLE_LINE.sub(lambda t: _PIC_CELL.sub(one, t[0]), _PIC_LINE.sub(one, text))


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
                row["md"] = hide(doc_pictures(p.read_text(errors="ignore"), p, root))
            files.append(row)
    groups = {g: DOC_GROUPS.get(g) or g.split("/")[-1].replace("-", " ").capitalize() for g in {f["g"] for f in files}}
    return {"files": files, "groups": groups}


# project files the approved mock files under Reference (round9/final/build/build.py setref, round5/project/build/ref.py):
# id, title, kind, state, path. As in the mock, the trader guide's text (a home address) and the sheets' rows (member data)
# stay out; the guide keeps its place in the title and the sheet is listed without its contents.
EXTRAS = [
    ("delivery-roadmap", "Delivery roadmap, car-first revision", "plan", "ref", "planning/05-roadmap.md"),
    ("delivery-scope", "Delivery scope", "plan", "ref", "planning/04-delivery-scope.md"),
    ("stack-choice", "Stack choice: Railway, Matrix or Payload", "plan", "ok", "planning/02-stack-decision.md"),
    ("legal-review-list", "Legal review list", "check", "ref", "planning/10-legal-review-list.csv"),
    ("store-review-notes", "App store review notes and trader guide", "check", "ref",
     "planning/operations/orchestration/run_c9d587c967ba/reports/store-review-cards/src/droid-review-store-review-droid.md"),
    ("email-designs", "Email change messages, alternate designs", "design", "prop", "design/alt-emails-v1/app/m3-confirm.html"),
    ("drive-screens", "Drive screens, before and after", "design", "ref", "design/page-v135/shots/390-screen-47-compare.png"),
    ("design-tokens", "Design tokens and platform mapping", "design", "ref", "design/tokens.json"),
    # the approved "finding the way back" thinking animation (card 4909); its file names it, the recordings are not on this Mac
    ("route-animation", "Route thinking animation; app store drive video", "design", "ref",
     "planning/operations/orchestration/run_c9d587c967ba/reports/ui-lead/approved.md"),
    ("chapter-owner-list", "Chapter owner list; tester sheet", "data", "ref", "FLD Chapter Owner List.xlsx"),
    ("ask-nicole-word", "Ask Nicole, edited Word file", "data", "ref", "Ask-Nicole (edited).docx"),
]
NOTE = {"store-review-notes": "Google Play review notes · the trader guide is left out: it holds a home address",
        "email-designs": "the “confirm your new email” message as the member sees it, 1 of 10 screens · addresses and links masked",
        "drive-screens": "Screen 47 on a phone: before and after, round 135",
        "route-animation": "Opens here: a video player that takes a note at a moment. Not in this copy: the approved thinking animation's "
                           "recordings are not on this Mac, and the only videos here are members' own uploads, private to them.",
        "chapter-owner-list": "a sheet of member names and contacts · its rows stay out of this copy"}
NOTE_ONLY = {"route-animation"}  # listed with its note; the file is a record of approvals, not the item itself
KIT_CSS = "design/apps-v2/kit/fld.css"


def _flat(o, p=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _flat(v, f"{p}.{k}" if p else k)
    else:
        yield [p, o if isinstance(o, str) else json.dumps(o)]


def extras(root: Path = FLD_DIR) -> list:
    """The project files above as Reference items: Markdown as text, the CSV as one table per section, tokens as one table."""
    import csv
    out = []
    for iid, title, kind, st, rel in EXTRAS:
        p = root / rel
        if not p.is_file():
            continue
        item = {"id": iid, "t": title, "kind": kind, "st": st, "from": rel, "d": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")}
        if iid in NOTE:
            item["note"] = NOTE[iid]
        if p.suffix == ".xlsx" or iid in NOTE_ONLY:  # member data: listed, never read
            item["md"] = ""
        elif p.suffix == ".png":
            import base64
            item["img"] = "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()
        elif p.suffix == ".html":  # shown sandboxed with its design kit inlined: no scripts, links go nowhere, addresses masked
            try:
                kit = (root / KIT_CSS).read_text(errors="ignore")
            except OSError:
                kit = ""
            page = re.sub(r"<script\b.*?</script>", "", p.read_text(errors="ignore"), flags=re.S | re.I)
            page = re.sub(r"<link\b[^>]*>", "", page)
            page = re.sub(r"(https?:)?//[^\s\"'<>)]+", "#", page)
            item["html"] = hide(page.replace("</head>", f"<style>{re.sub(r'url[(][^)]*[)]', 'none', kit)}</style></head>", 1))
        elif p.suffix == ".md":
            item["md"] = hide(doc_pictures(p.read_text(errors="ignore"), p, root))
        elif p.suffix == ".csv":  # one table per section: a change in the first column starts one, and its first row is the header
            parts = []
            for r in csv.reader(p.open(errors="ignore")):
                if not r:
                    continue
                if not parts or parts[-1][0] != hide(r[0]):
                    parts.append([hide(r[0]), [hide(c) for c in r[1:]], []])
                else:
                    parts[-1][2].append([plain(c, 400) for c in r[1:]])
            item["parts"] = parts
        elif p.suffix == ".docx":  # its paragraphs, headings marked, as the mock reads it
            import zipfile
            xml = zipfile.ZipFile(p).read("word/document.xml").decode(errors="ignore")
            lines = []
            for para in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
                t = hide(html.unescape("".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", para)))).strip()
                if t:
                    lines.append(("# " if re.search(r'w:val="(Heading|Title)', para) else "") + t)
            item["md"] = "\n\n".join(lines)
        else:
            item["parts"] = [["Tokens", ["Token", "Value"], [[a, plain(b, 300)] for a, b in _flat(json.loads(p.read_text()))]]]
        out.append(item)
    return out


# the mock's names for the audits it lists (round9/final/build/build.py); any other audit keeps its folder name
FIND_TITLES = {"burnt-damascus-etching-audit-2026-10-27": "Etching audit: Burnt Damascus knives"}


def findings(meta: dict) -> list:
    """A copied project's audits (outputs/<audit>/findings.json in its own folder, read only) as findings registers,
    the way the mock shows Rebex's etching audit: what was screened, the conclusion, each finding with its proof picture."""
    import base64
    src = meta.get("proto_source")
    root = Path(src).parents[1] if src and len(Path(src).parents) > 1 else None  # <project>/reviews/<slug>
    out = []
    for fj in sorted(root.glob("outputs/*/findings.json")) if root and root.is_dir() else []:
        try:
            j = json.loads(fj.read_text())
        except (OSError, ValueError):
            continue
        items = []
        for r in j.get("references") or []:
            pic = root / (r.get("preview") or "")
            items.append({"label": plain(r.get("label") or "", 120), "text": plain(r.get("finding") or "", 600), "file": hide(r.get("original") or ""),
                          "sha": (r.get("original_sha256") or "")[:12], "state": "Rebex mark seen" if r.get("rebex_etching_visible") else "No Rebex mark",
                          "src": "data:image/jpeg;base64," + base64.b64encode(pic.read_bytes()).decode() if pic.is_file() and pic.suffix.lower() in (".jpg", ".jpeg") else ""})
        when = (j.get("audited_at") or "")[:10]
        out.append({"id": "find:" + fj.parent.name, "t": FIND_TITLES.get(fj.parent.name, fj.parent.name.replace("-", " ").capitalize()), "kind": "data", "st": "ref",
                    "from": f"outputs/{fj.parent.name}/findings.json", "d": when, "find": {
                        "when": when, "conclusion": plain(j.get("conclusion") or "", 600), "limits": [plain(x, 300) for x in j.get("limitations") or []],
                        "untouched": not j.get("originals_changed") and not j.get("catalog_selections_changed"),
                        "screened": [[j[k], w] for k, w in (("photoshoot_originals_screened", "photoshoot originals"), ("owner_supplied_originals_screened", "owner originals"),
                                                            ("burnt_family_manufacturer_sources_screened", "manufacturer pictures")) if isinstance(j.get(k), int)],
                        "items": items}})
    return out


COPY_ST = {"needs_you": "Needs you", "held": "Held back", "done": "Done"}


def _delta_text(rev: dict | None) -> str:
    return plain("".join(o["insert"] for o in ((rev or {}).get("delta") or {}).get("ops", []) if isinstance(o.get("insert"), str)), 600)


def copy_library(page_dir: Path) -> dict | None:
    """The page's Copy library (copy.json), as the mock reads it: each piece of text with its state, its current wording
    and the wording before it. Every line, Needs you first."""
    try:
        blocks = json.loads((page_dir / "copy.json").read_text()).get("blocks") or []
    except (OSError, ValueError):
        return None
    if not blocks:
        return None
    lines = []
    for b in sorted(blocks, key=lambda b: list(COPY_ST).index(b["status"]) if b.get("status") in COPY_ST else 3):
        rv = b.get("revisions") or []
        ci = next((i for i, r in enumerate(rv) if r.get("id") == b.get("current")), len(rv) - 1)
        lines.append([plain(b.get("title") or b.get("id") or "", 80), _delta_text(rv[ci] if rv else None),
                      COPY_ST.get(b.get("status"), "Done"), _delta_text(rv[ci - 1]) if ci > 0 else "",
                      list(dict.fromkeys(t for j, r in enumerate(rv) if j != ci and (t := _delta_text(r))))[-5:]])  # its other wordings, earlier and proposed
    n = {s: sum(1 for x in lines if x[2] == s) for s in COPY_ST.values()}
    return {"id": "copy-library", "t": "Copy library", "kind": "text", "st": "prop", "from": "copy.json",
            "d": datetime.fromtimestamp((page_dir / "copy.json").stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            "m": f"{len(lines)} pieces of text · " + " · ".join(f"{v} {k.lower()}" for k, v in n.items() if v), "copy": lines}


STORE = "assets/preview-store"  # under assets/, so the page server serves it: sandboxed, scripts allowed
# The server refuses the sandboxed store's own requests for styles, scripts and pictures (cross-site), so each page is
# staged whole: its styles, the two scripts and the pictures inlined. The sandbox has no storage either, so the demo cart
# and colour choice live in the frame's name, which lasts while he browses the store's pages in the frame.
STORE_SHIM = ("var rbxStore=(function(){try{window.localStorage.length;return window.localStorage}catch(e){}"
              "var all=function(){try{return JSON.parse(window.name)||{}}catch(e){return {}}};"
              "return {getItem:function(k){var a=all();return k in a?a[k]:null},"
              "setItem:function(k,v){var a=all();a[k]=String(v);window.name=JSON.stringify(a)}}})();\n"
              "window.addEventListener('click',function(e){var a=e.target.closest&&e.target.closest('a[href]'),h=a&&a.getAttribute('href');"
              "if(h&&!e.defaultPrevented&&/^[\\w-]+\\.html/.test(h)&&window.parent!==window){e.preventDefault();window.parent.postMessage({rbxStore:h},'*')}});\n")
STORE_IMG = 'CDN + p + "&width=" + (w || 600)'  # site.js: how it names a shop picture
PIC = re.compile(r"cdn/((?:products|files)/[^\"'?&\s)]+)[^\"'\s)]*")


def stage_store(copy_dir: Path) -> int:
    """Rebex's prototype store into a copy's assets/preview-store/, as the mock builds it (round9/final/build/build.py):
    its pages, working, the shop's pictures swapped for this Mac's downloaded copies (600 px), fonts and outside links
    dropped. Reads the project folder only; returns how many pictures were not on this Mac."""
    import base64
    import io
    src = (json.loads((copy_dir / "current.meta.json").read_text()).get("proto_source") or "")
    root = Path(src).parents[1] if src else None
    site, out = (root / "prototype" / "site" if root else None), copy_dir / STORE
    if not site or not (site / "index.html").is_file():
        return 0
    try:
        log = json.loads((root / "catalog" / "download-log.json").read_text())["results"]
    except (OSError, ValueError, KeyError):
        log = []
    local = {Path(r["path"]).name.split("-", 1)[1]: root / "catalog" / r["path"] for r in log if r.get("ok") and "-" in Path(r.get("path") or "").name}
    pics, miss = {}, set()

    def pic(p: str) -> str:
        if p not in pics:
            try:
                from PIL import Image
                im = Image.open(local[Path(p).name]).convert("RGB")
                im.thumbnail((600, 600))
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=70)
                pics[p] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
            except (KeyError, ImportError, OSError):
                pics[p] = ""
                miss.add(p)
        return pics[p]

    def read(rel: str) -> str:
        t = (site / rel).read_text(errors="ignore") if (site / rel).is_file() else ""
        t = re.sub(r"<link[^>]+fonts\.googleapis\.com[^>]*>", "", t)
        return hide(re.sub(r"https?://[^\s\"'<>)]+", "#", t.replace("https://rebexcutlery.com/cdn/shop/", "cdn/")))

    logo = site / "img" / "logo-mono.png"
    css = read("css/site.css").replace("../img/logo-mono.png", "data:image/png;base64," + base64.b64encode(logo.read_bytes()).decode() if logo.is_file() else "")
    products, js = read("js/products.js"), read("js/site.js").replace("localStorage", "rbxStore")
    names = {p: pic(p) for p in re.findall(r"\"((?:products|files)/[^\"?]+)\?v=", products)}
    js = STORE_SHIM + f"var RBX_PICS={json.dumps(names)};\n" + js.replace(STORE_IMG, '(RBX_PICS[p.split("?")[0]] || "")')
    inline = lambda s: s.replace("</script", "<\\/script")
    out.mkdir(parents=True, exist_ok=True)
    for f in site.glob("*.html"):
        t = read(f.name).replace('<link rel="stylesheet" href="css/site.css">', f"<style>{css}</style>")
        t = t.replace('<script src="js/products.js"></script>', f"<script>{inline(products)}</script>")
        t = t.replace('<script src="js/site.js"></script>', f"<script>{inline(js)}</script>")
        (out / f.name).write_text(PIC.sub(lambda m: pic(m[1]) or m[0], t))
    return len(miss)


def _blocks_html(t: str) -> list:
    """Headings, paragraphs and list lines of an HTML page, in order, as Reference blocks."""
    t = re.sub(r"<(script|style|nav|header|footer)\b.*?</\1>", "", t, flags=re.S | re.I)
    return [["h" if tag[0] == "h" else "li" if tag == "li" else "p", plain(body, 2000)]
            for tag, body in re.findall(r"<(h[1-4]|p|li)\b[^>]*>(.*?)</\1>", t, re.S | re.I) if plain(body, 2000)]


def _md_tables(f: Path, keep) -> list:
    """Markdown tables under their headings, as [heading, header, rows]; keep(header) picks which (round 9 build.py)."""
    out, sec, cur = [], f.stem, None
    for line in f.read_text(errors="ignore").splitlines():
        if line.startswith("#"):
            sec, cur = plain(line.lstrip("# "), 90), None
        elif re.fullmatch(r"\|[|\s:-]+", line.strip()):
            continue
        elif line.startswith("|"):
            if cur is False:
                continue  # a table not kept: its rows are never cleaned (Rebex has hundreds; r12 fix10 slowread)
            cells = [plain(re.sub(r"\*\*|`", "", c.strip()), 220) for c in line.strip().strip("|").split("|")]
            if cur is None:
                cur = [sec, cells, []] if keep(cells) else False
                if cur:
                    out.append(cur)
            elif cur:
                cur[2].append(cells)
        else:
            cur = None
    return out


_isopt = lambda h: h and h[0].lower().split(" ")[0] in ("option", "options", "choice", "approach", "path")
_opt_cache: dict = {}  # (file, mtime) -> its compared-option tables: Rebex has 600+ source files, each read once (r12 fix10 slowread)


def _opt_tables(f: Path) -> list:
    key = (str(f), f.stat().st_mtime_ns)
    if key not in _opt_cache:
        _opt_cache[key] = _md_tables(f, _isopt)
    return [list(t) for t in _opt_cache[key]]  # copied() renames each table: the cached ones stay as read


ANSWERS_SHOWN = 200  # the newest answers; the page record holds thousands


def copied(page_dir: Path, meta: dict) -> list:
    """A copied project's own Reference material, read only, from its page and its project folder, as the mock lists it
    for Rebex: App text (Copy library, policies), designs (action images, preview store), sheets and findings."""
    import csv
    src = meta.get("proto_source")
    root = Path(src).parents[1] if src and len(Path(src).parents) > 1 else None
    out = []
    lib = copy_library(page_dir)
    if lib:
        out.append(lib)
    pol = root / "reviews" / "rebex-policies" / "current.html" if root else None
    if pol and pol.is_file():
        out.append({"id": "policies", "t": "Privacy, terms and shipping", "kind": "text", "st": "ref", "from": "reviews/rebex-policies/current.html",
                    "d": datetime.fromtimestamp(pol.stat().st_mtime).strftime("%Y-%m-%d %H:%M"), "blocks": _blocks_html(pol.read_text(errors="ignore"))})
    act = page_dir / "active-action-image-review.md"
    if act.is_file():
        bl, n = [], 0
        for line in act.read_text(errors="ignore").splitlines():
            n += line.startswith("### ")  # one product each
            if m := re.match(r"!\[([^\]]*)\]\((assets/[^)\s]+)\)", line.strip()):
                bl.append(["img", m.group(2), hide(m.group(1))])  # served from the copy's own assets
            elif line.startswith("#"):
                bl.append(["h", plain(line.lstrip("# "), 200)])
            elif line.strip() and not line.startswith(("```", "---", "title:", "see:", "- ", "#")) and not re.match(r"#\d+ ", line):
                bl.append(["p", plain(re.sub(r"\*\*", "", line), 600)])
        out.append({"id": "action-images", "t": "Action images", "kind": "design", "st": "ref", "from": "active-action-image-review.md",
                    "d": datetime.fromtimestamp(act.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "m": f"{n} products in review · actual, before and after · from Rebex's page", "blocks": bl})
    staged = page_dir / STORE / "index.html"
    if staged.is_file():  # the working store copy.sh staged (stage_store): pages, scripts and this Mac's pictures
        out.append({"id": "preview-store", "t": "Preview store", "kind": "design", "st": "ref", "from": "prototype/site", "wide": True,
                    "d": datetime.fromtimestamp(staged.stat().st_mtime).strftime("%Y-%m-%d %H:%M"), "src": f"{STORE}/index.html",
                    "note": "Rebex's prototype store, working: browse lines, open a product, add to the demo cart. "
                            "Pictures are this Mac's downloaded copies; fonts and outside links are dropped."})
    rounds = page_dir / "rounds.ndjson"
    if rounds.is_file():
        ra = []
        for line in rounds.read_text(errors="ignore").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            for a in r.get("answers") or []:
                ra.append([(a.get("ts") or r.get("ts") or "")[:10] + " · version " + str(r.get("version") or "").lstrip("v"),
                           plain(a.get("prompt") or "General feedback", 160), plain((a.get("text") or a.get("verdict") or "").split("\n")[0], 200)])
        ra.reverse()
        if ra:
            out.append({"id": "cutover-decisions", "t": "Cutover owner decisions", "kind": "data", "st": "ref", "from": "rounds.ndjson",
                        "d": datetime.fromtimestamp(rounds.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                        "m": f"{len(ra):,} answers · from Rebex's page record" + (f" · the newest {ANSWERS_SHOWN} shown" if len(ra) > ANSWERS_SHOWN else ""),
                        "parts": [["Your answers, newest first", ["When", "Question", "Your answer"], ra[:ANSWERS_SHOWN]]]})
    if root:
        ct, seen = [], set()
        for f in sorted(root.glob("reviews/*/source/v*.md"), key=lambda p: -p.stat().st_mtime):
            for t in _opt_tables(f):
                k = json.dumps([t[1], t[2]])
                if t[2] and k not in seen:
                    seen.add(k)
                    t[0] = f"{t[0]} · {f.parent.parent.name.replace('rebex-', '').replace('rebex', 'main page')}, version {f.stem[1:]}"
                    ct.append(t)
        if ct:
            out.append({"id": "compared-options", "t": "Compared options", "kind": "data", "st": "ref", "from": "reviews/*/source",
                        "d": datetime.fromtimestamp(max(p.stat().st_mtime for p in root.glob("reviews/*/source/v*.md"))).strftime("%Y-%m-%d %H:%M"),
                        "m": f"{len(ct)} compared tables · from Rebex's pages", "parts": ct})
    cat = root / "catalog" / "catalog.csv" if root else None
    if cat and cat.is_file():
        rows = list(csv.DictReader(cat.open(errors="ignore")))
        out.append({"id": "product-catalog", "t": "Product catalog", "kind": "data", "st": "ref", "from": "catalog/catalog.csv",
                    "d": datetime.fromtimestamp(cat.stat().st_mtime).strftime("%Y-%m-%d %H:%M"), "m": f"{len(rows)} products · Rebex's catalog sheet",
                    "parts": [["Products", ["Product", "Steel", "Price", "Pictures", "Description"],
                               [[plain(c.get("title") or "", 80), c.get("product_type") or "—", f"${c['price']}" if c.get("price") else "—",
                                 c.get("image_count") or "0", plain(c.get("description_text") or "", 160) or "—"] for c in rows]]]})
    return out + finding_sets(page_dir)


def _finding_status(c: dict) -> str:
    """findings.js statusOf: Needs you, Ready to send, Waiting on agent (agreed, not done yet) or Done."""
    d = c.get("decision") or {}
    if c.get("round_pending") or d.get("round_pending"):
        return "ready"
    if c.get("fixed"):
        return "done"
    if not d.get("verdict"):
        return "waiting" if c.get("reopened") or c.get("response_text") else "needs"
    choice = d.get("option_id") or d.get("option") or (d.get("text") if d.get("verdict") == "select" else None)
    opts = [o for o in (c.get("decision_request") or {}).get("options") or [] if isinstance(o, dict)]
    o = next((o for o in opts if o.get("id") == choice), None) or next((o for o in opts if o.get("label") == choice), None)
    choice = o["id"] if o else choice
    return "done" if choice in ("keep", "no") or d.get("verdict") == "reject" else "waiting"


def _finding_answer(c: dict) -> str:
    d = c.get("decision") or {}
    if d.get("verdict"):
        return plain(d.get("text") or d.get("verdict") or "", 120)
    if c.get("response_text"):
        opts = {o.get("id"): o.get("label") for o in (c.get("decision_request") or {}).get("options") or [] if isinstance(o, dict)}
        return plain(opts.get("yes") or opts.get("fix") or "Agreed", 120)
    return ""


def finding_sets(page_dir: Path) -> list:
    """The page's own findings groups (categories.json sets, their findings from the comments), as the live Findings view
    reads them: each finding's number, title, the answer given and its state."""
    from ..categories import _comments, comment_category, load_categories
    try:
        sets = load_categories(page_dir)["findings_sets"]
        anchors = _comments(page_dir).get("anchors") or {}
    except (OSError, ValueError):
        return []
    found = [c for items in anchors.values() for c in items if comment_category(c) == "findings" and c.get("status") != "deleted"]
    out = []
    for s in sets:
        fs = sorted((c for c in found if (c.get("finding") or {}).get("set") == s["id"]), key=lambda c: c.get("number") or 0)
        if not fs:
            continue
        items = [{"n": c.get("number") or i + 1, "t": plain((c.get("finding") or {}).get("title") or c.get("text") or "", 300),
                  "why": plain(((c.get("decision_request") or {}).get("context") or ""), 600), "a": _finding_answer(c), "st": _finding_status(c),
                  "note": plain(c.get("response_text") or "", 400)} for i, c in enumerate(fs)]
        when = (s.get("created_at") or min((c.get("created_at") or "") for c in fs))[:16].replace("T", " ")
        out.append({"id": "set:" + s["id"], "t": hide(s["label"]), "kind": "data", "st": "ref", "from": "Findings", "d": when,
                    "m": f"{pl_(len(items), 'finding')} · " + " · ".join(f"{sum(1 for x in items if x['st'] == k)} {w}" for k, w in
                                                                    (("needs", "need you"), ("waiting", "waiting on the agent"), ("done", "done")) if any(x["st"] == k for x in items)),
                    "fset": {"intro": plain(s.get("intro") or "", 600), "items": items}})
    return out


def pl_(n: int, w: str) -> str:
    return f"{n} {w}" + ("" if n == 1 else "s")


_built: dict = {}  # page dir -> (its own files' stamps, when built, the build): 0.25-0.6 s a build, on every open (r12 fix12 perf)
_again = threading.Lock()


def _own(page_dir: Path) -> tuple:
    from .history import _stamp
    return tuple(_stamp(page_dir / n) for n in ("current.meta.json", "comments.json", "project.json", "copy.json")) + tuple(
        (m.parent.name, _stamp(m)) for m in sorted((page_dir / "plans").glob("*/meta.json")))


def _cached(page_dir: Path) -> tuple:
    """_build, again at once when this page's own files change (a note, a plan revision); the project's files, workflows and
    audits it also reads are read again behind the answer once it is a minute old, as Pages & links does."""
    page_dir, now = Path(page_dir), time.time()
    stamps, hit = _own(page_dir), _built.get(str(page_dir))
    if not hit or hit[0] != stamps:
        hit = _built[str(page_dir)] = (stamps, now, _build(page_dir))
    elif now - hit[1] > 60 and _again.acquire(blocking=False):
        def again():
            try:
                _built[str(page_dir)] = (stamps, time.time(), _build(page_dir))
            finally:
                _again.release()
        threading.Thread(target=again, daemon=True).start()
    return hit


def build(page_dir: Path) -> dict:
    return _cached(page_dir)[2]


def stamp(page_dir: Path) -> tuple:
    """Which build the next answer is: the same one goes out as the same bytes (proto_data.prepared)."""
    hit = _cached(page_dir)
    return hit[0], hit[1]


def _build(page_dir: Path) -> dict:
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
    beads = board(running.project(page_dir))
    try:
        meta = json.loads((page_dir / "current.meta.json").read_text())
    except (OSError, ValueError):
        meta = {}
    fld = not meta.get("proto_copy_of")  # a copy of another project gets its own audits, never FastLane Drive's files and workflows
    return {"plans": out, "topics": topics, "checklist": cl, "flows": flows() if fld else [],  # documents are listed in Pages & links only, as in the mock

            "extras": (extras() if fld else copied(page_dir, meta)) + findings(meta),
            "beads": {i: beads[i] for i in sorted(ids) if i in beads}, "notes": notes(page_dir)}


NOTE_ANCHORS = ("ref:", "doc:", "chk:")


def notes(page_dir: Path) -> list:
    """The notes written in Reference (anchors ref:, doc:, chk:), oldest first, so each shows at its line."""
    from ..categories import _comments
    out, store = [], _comments(page_dir)
    # Close (today's archive) moves a note into "archived": it stays at its line, closed, with Re-open (r12 fix17)
    for anchor, items in [kv for part in ("anchors", "archived") for kv in (store.get(part) or {}).items()]:
        if not anchor.startswith(NOTE_ANCHORS):
            continue
        for c in items:
            if c.get("status") in ("deleted",):
                continue
            out.append({"id": c.get("id"), "a": anchor, "l": hide(c.get("anchor_label") or ""), "text": hide(c.get("text") or ""), "who": c.get("author_name") or "You",
                        "at": (c.get("created_at") or "")[:16], "v": c.get("version"), "st": c.get("status"),
                        # Close, Re-open and View resolution, as on Questions' notes (r12 fix17)
                        "closed": c.get("status") == "archived", "rv": c.get("resolved_in_version"), "ra": c.get("resolution_anchor_id"),
                        "target": c.get("target"),  # selected words ({quote}) or a spot on a picture ({tag: img, offset})
                        # a Send flags every open note (sync_server rounds/submit), so an unsent one stays in the next Send after a reload
                        "sent": bool(c.get("flagged_for_session") or c.get("delivery_id")) or not _mine(c.get("author"))})
    return sorted(out, key=lambda n: n["at"])


if __name__ == "__main__":  # copy.sh: python3 -m agent_annotate.proto_data.reference <copy dir>  (stages Rebex's preview store)
    import sys
    print(f"preview store staged; {stage_store(Path(sys.argv[1]))} pictures not on this Mac")
