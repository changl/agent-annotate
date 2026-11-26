"""Running and Analytics data for the prototype page: live and read only.

Sources, each read at most once a minute (the whole result is cached; a stale copy is served while a fresh one is built):
- workers: this Mac's Orca record (orchestration.db, read only) and `orca orchestration worker-list --environment` for the other Macs;
- scheduled jobs and runs: `wmill schedule list` and `wmill job list` with the stored login (no token is read or passed here);
- tasks: this page's own project's board (found by `bd where` from its checkout) through `bd --readonly`; none when it has no board;
- pull requests: `gh search prs`, read only;
- daily usage: the page's own project's usage reports (only FastLane Drive keeps any); Analytics: the page's own record and the other review pages' records;
- machine load: the launchd recorder's file (~/.local/share/machine-load/load.tsv) on this Mac, and on the others through `ssh`, read only.
Nothing here writes outside the page dir; the only write is the snapshot file proto-running.json in it.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import statistics
import subprocess
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
FLD_BOARD = HOME / "projects/FastLane Drive/fld-main"
# each project's daily usage reports, by project tag; a project not listed keeps none (only FastLane Drive does on this Mac)
USAGE = {"fld": HOME / "projects/FastLane Drive/planning/operations/usage-reports"}
ORCA_DB = HOME / "Library/Application Support/Orca/orchestration.db"
LOAD_TSV = HOME / ".local/share/machine-load/load.tsv"
PROJECTS = HOME / "projects"
GH_OWNER = "Fast-Lane-Drive"
# each project's pull requests, as `gh search prs` arguments: FastLane Drive's apps span its organisation's repositories
REPOS = {"fld": ["--owner", GH_OWNER], "rebex": ["--repo", "changl/shopify-rebex"], "annotate": ["--repo", "changl/agent-annotate"]}
# a scheduled job's project by its Windmill folder, as frame.js's JOBP reads it; any other job falls back to its path's words (proj_of)
JOBP = [(r"^f/(fld_ops|sweep|uat|usage|ops)/", "fld"), (r"^f/test/", "annotate"), (r"^u/[^/]+/mac_daily_update$", "multimac"), (r"^u/[^/]+/windmill_", "windmill")]
TTL = 60  # seconds a read stays fresh: the page never asks a source more than once a minute
SNAP = "proto-running.json"
SNAPV = 3  # a saved snapshot of an older shape (jobs without proj, pull requests or usage not per project) is not served
MACS = [("M1 Max", None), ("M5 Max", "M5Max"), ("M1 Max 16", "M1Max16")]
# each project's checkout, by project tag; `bd where` run there finds its own board. A project not listed has none.
CHECKOUTS = {"fld": FLD_BOARD, "rebex": PROJECTS / "rebex/repo", "annotate": PROJECTS / "agent-annotate/codex"}
NAMES = {"fld": "FastLane Drive", "rebex": "Rebex", "annotate": "Agent Annotate", "leadory": "Leadory", "windmill": "Windmill",
         "cheer": "Cheer ticketing", "multimac": "Three Macs", "other": "Other"}

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]*\w")
_lock = threading.Lock()
_cold = threading.Lock()
_mem: dict = {}  # page dir -> (built epoch, result)
_busy: set = set()


# ---------------------------------------------------------------- helpers

def mask(x):
    """Every string with an email address in it reads member@example.com instead, all the way down."""
    if isinstance(x, str):
        return _EMAIL.sub("member@example.com", x)
    if isinstance(x, list):
        return [mask(y) for y in x]
    if isinstance(x, dict):
        return {k: mask(v) for k, v in x.items()}
    return x


_ORCA_READS = (["orchestration", "worker-list"], ["terminal", "list"])


def run_json(argv, timeout=30):
    env = None
    if argv[0] == "orca":
        # the prototype server points ORCA_CLI_COMMAND at a refusing stand-in; only these two read-only lists bypass it
        if argv[1:3] not in _ORCA_READS:
            raise PermissionError("the prototype only reads Orca's worker and terminal lists")
        env = {k: v for k, v in os.environ.items() if k != "ORCA_CLI_COMMAND"}
    out = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env)
    if out.returncode:
        raise RuntimeError((out.stderr or out.stdout)[:200])
    t = out.stdout.strip()
    i = min([k for k in (t.find("{"), t.find("[")) if k >= 0] or [0])
    return json.loads(t[i:])


def safe(fn, default):
    try:
        return fn()
    except Exception as exc:  # one source down must not take the tab down
        return {"error": f"{type(exc).__name__}: {str(exc)[:160]}"} if default is None else default


def proj_of(s):
    s = (s or "").lower()
    for k, ws in (("fld", ("fld", "fastlane", "fast-lane")), ("rebex", ("rebex",)), ("annotate", ("annotate", "ui/ux", "uiux")),
                  ("leadory", ("leadory", "lea-")), ("windmill", ("windmill",)), ("cheer", ("cheer",)), ("multimac", ("multimac", "mmo-"))):
        if any(w in s for w in ws):
            return k
    return "other"


def project(page_dir: Path) -> str:
    """The page's project tag, read as the frame reads it: a copy's source project, else its board's, else its name."""
    def read(name):
        try:
            x = json.loads((Path(page_dir) / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return x if isinstance(x, dict) else {}
    meta, b = read("current.meta.json"), read("project.json").get("board") or {}
    return proj_of(meta.get("proto_copy_of") or (b.get("project") if isinstance(b, dict) else "") or meta.get("name") or "")


BD_TRIES = (0, 2, 5)  # seconds before each try of one bd read


def bd_json(argv, timeout=30):
    """One bd read, tried again after a pause: on a loaded Mac one Dolt connection in many times out (mysql "i/o timeout")
    while the next one answers, and one such miss among a board's six reads used to drop the whole board (r13 frame 11)."""
    for i, wait in enumerate(BD_TRIES):
        time.sleep(wait)
        try:
            return run_json(argv, timeout=timeout)
        except Exception:
            if i == len(BD_TRIES) - 1:
                raise


_where: dict = {}  # project tag -> the board location `bd where` last gave: it never moves while the page runs


def board_dir(code: str) -> Path | None:
    """Where the project's own board lives, from `bd where` in its checkout; None when it has no reachable board."""
    co = CHECKOUTS.get(code)
    if not co or not Path(co).is_dir():
        return None
    try:
        _where[code] = Path(bd_json(["bd", "-C", str(co), "where", "--json"], timeout=20)["path"]).parent
    except Exception:
        pass
    return _where.get(code)


def mins_since(s, now=None):
    if not s:
        return None
    t = datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T"))
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return max(0, round(((now or datetime.now(timezone.utc)) - t).total_seconds() / 60))


def clean(t, n=80):
    t = re.sub(r"^[#\s]*(Task:|Role:)?\s*", "", t or "")
    return re.sub(r"\s+", " ", t)[:n]


_CODE = re.compile(r"^[A-Za-z0-9]+([-_][A-Za-z0-9]+)*$")


def wtitle(dn, tt):
    """A worker in words: its task's first line, unless that is only a code like "BD-B5"; else its display name."""
    first = clean(next((ln for ln in (tt or "").splitlines() if ln.strip()), ""))
    return first if first and not _CODE.match(first) else clean(dn) or first


# ---------------------------------------------------------------- workers

def _orca_db():
    return sqlite3.connect(f"file:{ORCA_DB}?mode=ro", uri=True, timeout=5)


def _record(db, task_id):
    """(run objective, last report) for a task in this Mac's Orca record."""
    r = db.execute("select r.objective from tasks t join runs r on r.id = t.run_id where t.id = ?", (task_id,)).fetchone()
    m = db.execute("select subject from messages where payload like ? and type in ('status', 'worker_done', 'escalation', 'question') "
                   "order by created_at desc limit 1", (f"%{task_id}%",)).fetchone()
    rep = (m[0] if m else "") or ""
    return clean(re.sub(r"\s*\(.*", "", (r[0] if r else "") or ""), 60), ("" if rep in ("Question", "Status") else rep[:140])


_BEAD = re.compile(r"\b(?:FLD|RBX|agent-annotate)-[a-z0-9]+(?:\.\d+)*\b")


def _bead(db, task_id):
    """The first task on the board a worker's brief names, or None."""
    r = db.execute("select coalesce(task_title, '') || ' ' || coalesce(spec, '') from tasks where id = ?", (task_id,)).fetchone()
    m = _BEAD.search(r[0]) if r else None
    return m.group(0) if m else None


def group_work(out, code="fld", where=None):
    """Workers grouped by the real work: the board epic (else the task) their brief names, read from this page's own board
    (where) for this project's workers only. Every FLD worker shares one run, so the run's objective said the same thing on every Mac."""
    ws = [w for m in (out.get("workers") or {}).values() if isinstance(m, dict) for w in m.get("workers") or []]
    beads = (out.get("board") or {}).get("beads") or {}
    roots = {w["bead"].split(".")[0] for w in ws if w.get("bead") and w.get("proj") == code}
    titles = {k: beads[k]["t"] for k in roots if k in beads}
    missing = sorted(roots - titles.keys())
    if missing and where:  # closed epics are not on Running's open list
        rows = safe(lambda: bd_json(["bd", "-C", str(where), "--readonly", "show", *missing, "--json"], timeout=60), [])
        titles.update({r["id"]: r.get("title") or "" for r in rows if isinstance(r, dict) and r.get("id")})
    for w in ws:
        b = w.pop("bead", None)
        t = titles.get(b.split(".")[0]) if b else None
        w["work"] = _cut(t, 70) if t else "Other work"
    return out


def workers():
    """{machine: {ok, why?, workers: [...]}}. The M1 Max record coordinates every Mac's work, so run and report come from it."""
    db = _orca_db()
    res, remote_ids = {}, set()
    for name, env in MACS[1:]:
        try:
            rows = run_json(["orca", "orchestration", "worker-list", "--terminal-state", "active", "--full", "--limit", "100",
                             "--environment", env, "--json"], timeout=25)["result"]["workers"]
        except Exception as exc:
            res[name] = {"ok": False, "why": str(exc)[:120], "workers": []}
            continue
        out = []
        for w in rows:
            p = w.get("projection") or {}
            remote_ids.add(w.get("dispatchId"))
            ws = (p.get("workspace") or {}).get("id") or ""
            live = p.get("liveness") or {}
            obs = live.get("observedAt")
            t = db.execute("select display_name, created_at, task_title from tasks where id = ?", (w.get("taskId"),)).fetchone()
            t = (wtitle(t[0], t[2]), t[1]) if t else None
            work, rep = _record(db, w.get("taskId"))
            prov = p.get("provider") or {}
            heard = round((time.time() * 1000 - obs) / 60000) if isinstance(obs, (int, float)) else mins_since(obs) if obs else None
            state = "working" if live.get("verdict") == "live" or (heard is not None and heard < 30) else "stuck"
            if w.get("workerState") == "starting":
                state = "working"
            out.append({"name": clean(t[0] if t else "") or "a worker", "s": state, "agent": prov.get("id") or "", "model": prov.get("model") or "",
                        "work": work, "proj": proj_of(ws + " " + (t[0] if t else "") + " " + work), "heard": heard,
                        "mins": mins_since(t[1]) if t else None, "report": rep, "bead": _bead(db, w.get("taskId"))})
        res[name] = {"ok": True, "workers": out}
    # this Mac: dispatched workers whose terminal is still open (Orca's terminal list), plus those that failed in the last two hours;
    # the terminal's last output is the last sign of life
    terms = run_json(["orca", "terminal", "list", "--limit", "500", "--json"], timeout=25)["result"]
    terms = {t.get("handle"): t for t in (terms.get("terminals") if isinstance(terms, dict) else terms) or []}
    m1 = []
    for did, tid, st, hb, at, done, dn, tt, so, th in db.execute(
            """select d.id, d.task_id, d.status, d.last_heartbeat_at, d.dispatched_at, d.completed_at, t.display_name, t.task_title, w.start_options,
                      coalesce(w.agent_terminal_handle, d.assignee_handle)
               from dispatch_contexts d join tasks t on t.id = d.task_id left join worker_dispatches w on w.dispatch_id = d.id
               where (d.status = 'dispatched' and d.dispatched_at > datetime('now', '-7 day'))
                  or (d.status in ('failed', 'circuit_broken') and d.completed_at > datetime('now', '-2 hours'))"""):
        if did in remote_ids or (st == "dispatched" and th not in terms):
            continue
        so, dn = json.loads(so or "{}"), wtitle(dn, tt)
        la = (so.get("launch") or {}).get("effective") or {}
        out_at = (terms.get(th) or {}).get("lastOutputAt")
        heard = round((time.time() * 1000 - out_at) / 60000) if isinstance(out_at, (int, float)) else mins_since(out_at or hb or at)
        state = "failed" if st != "dispatched" else "working" if heard is not None and heard < 30 else "stuck"
        work, rep = _record(db, tid)
        m1.append({"name": clean(dn), "s": state, "agent": la.get("agent") or so.get("agent") or "", "model": la.get("model") or "",
                   "effort": la.get("effort") or "", "work": work, "proj": proj_of(work + " " + (dn or "")), "heard": heard,
                   "mins": mins_since(at) if st == "dispatched" else (mins_since(at) or 0) - (mins_since(done) or 0), "report": rep,
                   "bead": _bead(db, tid)})
    res["M1 Max"] = {"ok": True, "workers": m1}
    db.close()
    return res


_SYSCTL = "sysctl -n vm.loadavg hw.ncpu hw.memsize hw.pagesize"
_TAIL = 1500 * 70  # the last day only: about 1,440 lines of ~60 bytes


def load_entry(sysctl_out: str, tsv: str) -> dict:
    """One Mac's load now and its recorder's last 24 hours, from sysctl's output and the tail of its load.tsv."""
    la = sysctl_out.split()
    cpus, mem, page = int(la[5]), int(la[6]), int(la[7])
    cut, hist = time.time() - 86400, []
    for ln in tsv.splitlines()[1:]:  # the first line may be cut in half by the tail
        c = ln.split("\t")
        if len(c) >= 8 and c[0].isdigit() and int(c[0]) >= cut:
            hist.append([int(c[0]), float(c[1]), round(int(c[4] or 0) * page / mem * 100, 1), int(c[6].rstrip("%") or 0)])
    return {"recorded": bool(hist), "load": [float(x) for x in la[1:4]], "cpus": cpus, "hist": hist, "since": hist[0][0] if hist else None}


def _remote_load(env: str) -> dict:
    # the ssh shortcuts are the Orca environment names in lower case: m5max, m1max16
    out = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", env.lower(),
                          f"{_SYSCTL}; echo ---; tail -c {_TAIL} ~/.local/share/machine-load/load.tsv"],
                         capture_output=True, text=True, timeout=20).stdout
    sc, _, tsv = out.partition("\n---\n")
    return load_entry(sc, tsv)


def machine_load():
    """Per Mac: load now and the recorder's last 24 hours; the other Macs are read over ssh, one call each."""
    tsv = ""
    if LOAD_TSV.exists():
        with LOAD_TSV.open("rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - _TAIL))
            tsv = f.read().decode(errors="ignore")
    here = subprocess.run(_SYSCTL.split(), capture_output=True, text=True, timeout=5).stdout
    out = {"M1 Max": load_entry(here, tsv)}
    for name, env in MACS[1:]:
        out[name] = safe(lambda: _remote_load(env), {"recorded": False})
    return out


# ---------------------------------------------------------------- board

_WHY = [(r"aside", "you set it aside; it stops after its current step"), (r"UI freeze", "held while screen changes wait for your review"),
        (r"phone session|CarPlay|passcode|phones? not reachable|iPhone|Pixel", "needs your phone for a short test session"),
        (r"SMS", "needs you ready for one text-message code"), (r"root sitting|password", "needs you at a Mac for one password step"),
        (r"login|sign in", "needs you to sign in once"), (r"picks|choice|decid", "waits for your choice"), (r"in chat", "waits for your answer in chat")]


def waits_on_him(notes, title=""):
    """(why, merge) when the board's own notes say the task is blocked by him, else None."""
    m = re.search(r"BLOCKED BY:?\s*([^|]*)", notes or "")
    if not m or not re.search(r"\bchang\b", m.group(1), re.I):
        return None
    why = next((t for r, t in _WHY if re.search(r, m.group(1), re.I)), None)
    # a merge mark only on a row whose reason is the merge: one waiting on his phone, a sign-in or a choice is not a merge (r13 running 6)
    mg = why is None and bool(re.search(r"merge", (title or "") + m.group(1), re.I))
    return why or ("waits for your yes to merge it" if mg else "waits for your answer on its question"), mg


def _cut(s, n=2500):
    s = re.sub(r"https?://\S+", "a link", s or "").strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + " …"


GROUPS = [("ready", "Ready to start"), ("in_progress", "In progress"), ("waiting", "Waiting on another task"), ("blocked", "Blocked"), ("deferred", "Deferred")]


def board(code="fld", where=None):
    """This project's own board, read only; when it has none, empty sections and a plain line why. Never another project's board."""
    if where is None and CHECKOUTS.get(code) and Path(CHECKOUTS[code]).is_dir():
        # its checkout is here but `bd where` did not answer (a busy host): an unread board, never zero tasks (audit11 running 2)
        raise RuntimeError("the board's location could not be read")
    if where is None:
        return {"tasks": [], "beads": {}, "waiting": [], "closed": None, "groups": [], "ready": 0,
                "none": f"{NAMES.get(code, 'This project')} has no task board this page can read, so no tasks are listed."}
    bd = ["bd", "-C", str(where), "--readonly"]
    rows = bd_json([*bd, "list", "--status", "open,in_progress,blocked,deferred", "--flat", "--limit", "0", "--json"], timeout=60)
    ready = {b["id"] for b in bd_json([*bd, "ready", "--limit", "0", "--json"], timeout=60)}
    closed = safe(lambda: bd_json([*bd, "count", "--status", "closed", "--json"]).get("count"), None)
    full = {}
    ids = [b["id"] for b in rows]
    for i in range(0, len(ids), 60):  # bd show takes many ids at once; 60 a call keeps argv short
        for b in bd_json([*bd, "show", *ids[i:i + 60], "--json"], timeout=90):
            full[b["id"]] = b
    st = {b["id"]: b["status"] for b in rows}
    dl = lambda xs: [[x.get("id"), _cut(x.get("title"), 160), (x.get("status") or "").replace("_", " ")] for x in xs or []
                     if isinstance(x, dict) and x.get("dependency_type", "blocks") == "blocks"]
    tasks, beads, waiting = [], {}, []
    for b in rows:
        f = full.get(b["id"], b)
        g = "ready" if b["id"] in ready else "waiting" if b["status"] == "open" else b["status"]
        on = dl(f.get("dependencies"))
        tasks.append({"id": b["id"], "title": _cut(b.get("title"), 200), "st": b["status"].replace("_", " "), "g": g, "pri": b.get("priority"),
                      "type": b.get("issue_type") or "task", "since": (b.get("created_at") or "")[:10],
                      "on": [x for x in on if x[2] != "closed"], "chore": (b.get("title") or "").startswith("Stuck: checkout_unsaved")})
        beads[b["id"]] = {"t": _cut(b.get("title"), 300), "st": b["status"].replace("_", " "), "type": b.get("issue_type") or "task", "pri": b.get("priority"),
                          "desc": _cut(f.get("description")), "design": _cut(f.get("design")), "acc": _cut(f.get("acceptance_criteria")),
                          "notes": _cut(f.get("notes")), "on": on, "by": dl(f.get("dependents")), "own": f.get("assignee") or "",
                          "made": (b.get("created_at") or "")[:10], "upd": (b.get("updated_at") or "")[:10], "labels": f.get("labels") or [],
                          "cm": [[(c.get("created_at") or "")[:10], _cut(c.get("text") or c.get("body"), 800)] for c in f.get("comments") or []],
                          "ncm": b.get("comment_count") or 0}
        w = waits_on_him(b.get("notes"), b.get("title"))
        if w:
            waiting.append([b["id"], *w])
    order = [g for g, _ in GROUPS]
    tasks.sort(key=lambda t: (order.index(t["g"]) if t["g"] in order else 9, t["chore"], t["pri"] if t["pri"] is not None else 9, t["since"]))
    cnt = Counter(t["g"] for t in tasks)
    return {"tasks": tasks, "beads": beads, "waiting": waiting, "closed": closed if isinstance(closed, int) else None,
            "groups": [[g, label, cnt[g]] for g, label in GROUPS if cnt[g]], "ready": cnt["ready"]}


# ---------------------------------------------------------------- jobs and pull requests

def job_proj(path):
    """The project a scheduled job belongs to, by its Windmill path, else by the words in its path and name."""
    return next((c for r, c in JOBP if re.match(r, path or "")), None) or proj_of((path or "").replace("_", " "))


def jobs():
    """Every enabled Windmill schedule with its newest 12 runs, failing ones first, each tagged with its project (proj).
    Home counts every project's jobs from this list, so Running shows only the page's own (running.js filters on proj)."""
    sch = [s for s in run_json(["wmill", "schedule", "list", "--json"]) if s.get("enabled")]

    def runs(s):
        js = run_json(["wmill", "job", "list", "--script-path", s["script_path"], "--limit", "12", "--json"])
        return [{"t": j.get("completed_at") or j.get("started_at") or j.get("created_at"), "ok": j.get("success") if j.get("type") == "CompletedJob" else None,
                 "ms": j.get("duration_ms")} for j in js if j.get("type") == "CompletedJob" or j.get("running")]

    with ThreadPoolExecutor(6) as ex:
        rs = list(ex.map(lambda s: safe(lambda: runs(s), []), sch))
    out = []
    for s, r in zip(sch, rs):
        name = s["path"].rsplit("/", 1)[-1].replace("_schedule", "").replace("_", " ")
        done = [x for x in r if x["ok"] is not None]
        out.append({"name": name[:1].upper() + name[1:], "path": s["path"], "proj": job_proj(s["path"]), "cron": s.get("schedule"), "tz": s.get("timezone"),
                    "runs": r, "failing": bool(done and done[0]["ok"] is False),
                    "since": next((x["t"] for x in done if x["ok"] is not False), None) if done and done[0]["ok"] is False else None})
    out.sort(key=lambda j: (not j["failing"], j["name"]))
    return out


def prs(code="fld"):
    """This project's own pull requests, read only; none (never another project's) when it has no repository listed."""
    if code not in REPOS:
        return []
    rows = run_json(["gh", "search", "prs", *REPOS[code], "--sort", "updated", "--limit", "15",
                     "--json", "number,title,repository,state,updatedAt,url,isDraft"], timeout=30)
    rows.sort(key=lambda p: (p["state"] != "open", ""))  # open first, then the newest closed and merged
    return [{"id": f"{p['repository']['name']} #{p['number']}", "title": p["title"][:160], "state": p["state"], "upd": p["updatedAt"][:10],
             "url": p["url"], "draft": p.get("isDraft")} for p in rows]


# ---------------------------------------------------------------- analytics

def _ok(line):
    try:
        return json.loads(line)
    except ValueError:  # a live file may be mid-write on its last line
        return None


def page_record(d: Path):
    """One review page's Send record: picks, recommended picks, minutes to answer, sends, word answers, per-week picks, comebacks."""
    rec, asked = {}, {}
    try:
        store = json.loads((d / "comments.json").read_text())
    except (OSError, ValueError):
        store = {}
    per_version = Counter()
    for items in (store.get("anchors") or {}).values():
        for c in items:
            dr = c.get("decision_request") or {}
            if not dr:
                continue
            if not c.get("parent_id"):
                per_version[c.get("origin_version") or c.get("version")] += 1
            o = next((o for o in dr.get("options") or [] if isinstance(o, dict) and o.get("id") == dr.get("recommendation")), None)
            if o:
                rec[c["id"]] = (o.get("label") or "").strip().lower()
            asked[c["id"]] = dr.get("requested_at") or c.get("created_at")
    q = {"sel": 0, "rec": 0, "sends": 0, "words": 0, "ttv": []}
    weeks = defaultdict(lambda: [0, 0])
    per, prompt_nums = defaultdict(set), defaultdict(set)
    try:
        lines = (d / "rounds.ndjson").read_text(errors="ignore").splitlines()
    except OSError:
        lines = []
    for ri, r in enumerate(filter(None, map(_ok, lines))):
        q["sends"] += 1
        for a in r.get("answers") or []:
            cid, ts = a.get("comment_id"), a.get("ts") or r.get("ts")
            n = str(a.get("number") or "")
            if n:
                per[n].add(ri)
                pr = re.sub(r"\s+", " ", (a.get("prompt") or "").strip().lower())
                if pr:
                    prompt_nums[pr].add(n)
            if cid in asked and ts and asked[cid]:
                m = (datetime.fromisoformat(ts.replace("Z", "+00:00")) - datetime.fromisoformat(asked[cid].replace("Z", "+00:00"))).total_seconds() / 60
                if 0 <= m < 60 * 24 * 30:
                    q["ttv"].append(m)
            if a.get("verdict") == "select" and cid in rec:
                hit = (a.get("text") or "").split("\n")[0].strip().lower() == rec[cid]
                q["sel"] += 1
                q["rec"] += hit
                if ts:
                    wk = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%G-W%V")
                    weeks[wk][0] += 1
                    weeks[wk][1] += hit
            elif a.get("verdict") == "comment":
                q["words"] += 1
    t = sorted(q.pop("ttv"))
    q["ttvMed"] = round(statistics.median(t)) if t else None
    q["ttvP90"] = round(t[int(len(t) * 0.9)]) if t else None
    q["ttvN"] = len(t)
    again = sorted(((len(ns), pr) for pr, ns in prompt_nums.items() if len(ns) > 1), reverse=True)
    hist = Counter(min(len(v), 5) for v in per.values())
    comeback = {"questions": len(per), "oneSend": hist[1], "sendsHist": [[k, hist[k]] for k in sorted(hist)], "reasked": len(again),
                "top": [[n, pr[:120]] for n, pr in again[:6]]}
    qpv = sorted(([int(v[1:]), n] for v, n in per_version.items() if re.fullmatch(r"v\d+", v or "")))[-40:]
    return q, sorted([w, *v] for w, v in weeks.items())[-12:], comeback, qpv


def usage(code="fld"):
    """This project's own daily usage reports, newest 30; none when it keeps none."""
    use = []
    for f in sorted(USAGE[code].glob("2026-*.md")) if code in USAGE else []:
        t = f.read_text(errors="ignore")
        g = lambda r, d=None: (lambda m: m.groups() if m else d)(re.search(r, t))
        tot = g(r"Total \$([\d,.]+) across ([\d,]+) requests")
        if not tot:
            continue
        cw = g(r"Cache writes:.*?\(([\d.]+)M / ([\d.]+)M tokens\)", (0, 0))
        use.append({"d": f.stem, "usd": float(tot[0].replace(",", "")), "req": int(tot[1].replace(",", "")),
                    "peak": int((g(r"Peak concurrent workers[^:]*: (\d+)") or [0])[0]), "commits": int((g(r"Merged app commits: (\d+)") or [0])[0]),
                    "cacheM": round(float(cw[0]) + float(cw[1]), 1),
                    "roles": [[a, int(b)] for a, b in re.findall(r"([\w-]+) \$(\d+)", (g(r"By role: (.*)") or [""])[0])]})
    return use[-30:]


def orca_history():
    db = _orca_db()
    runs = {i: proj_of(o) for i, o in db.execute("select id, objective from runs")}
    orc = defaultdict(lambda: {"workers": 0, "ok": 0, "failed": 0, "stopped": 0, "codex": 0, "claude": 0, "weeks": Counter()})
    for run, st, at, wst, so in db.execute("select d.run_id, d.status, d.dispatched_at, w.state, w.start_options from dispatch_contexts d "
                                          "left join worker_dispatches w on w.dispatch_id = d.id"):
        o = orc[runs.get(run, "other")]
        o["workers"] += 1
        o["ok"] += st == "completed"
        o["failed"] += st in ("failed", "circuit_broken")
        o["stopped"] += wst == "stopped"
        ag = json.loads(so or "{}").get("agent") or ""
        if ag in ("codex", "claude"):
            o[ag] += 1
        if at:
            o["weeks"][datetime.fromisoformat(at).strftime("%G-W%V")] += 1
    since = (db.execute("select min(created_at) from dispatch_contexts").fetchone()[0] or "")[:10]
    db.close()
    return {p: {**o, "weeks": sorted(o["weeks"].items())[-10:]} for p, o in orc.items()}, since


def hours(now=None, code="fld"):
    """This project's workers at once, hour by hour over the last 24 hours, oldest first, from the same Orca record."""
    db = _orca_db()
    fld = {i for i, o in db.execute("select id, objective from runs") if proj_of(o) == code}
    rows = [(r, a, c) for r, a, c in db.execute("select run_id, dispatched_at, completed_at from dispatch_contexts "
                                                "where dispatched_at > datetime('now', '-7 day')") if r in fld]
    db.close()
    end = int((now or time.time()) // 3600 + 1) * 3600
    ts = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp() if s else None
    spans = [(ts(a), ts(c)) for _, a, c in rows]
    return [sum(1 for a, c in spans if a and a < end - (23 - h) * 3600 and (c is None or c >= end - (24 - h) * 3600)) for h in range(24)]


def sessions():
    ses = Counter()
    for d in (HOME / ".claude/projects").glob("*"):
        ses[proj_of(d.name.replace("-", " "))] += sum(1 for _ in d.glob("*.jsonl"))
    return dict(ses)


def analytics(page_dir: Path, code="fld"):
    pages = {}
    for f in sorted(PROJECTS.glob("*/reviews/*/rounds.ndjson")):
        p = proj_of(f.parts[len(PROJECTS.parts)])
        if p != code:  # this project's numbers come from the page's own record below
            pages.setdefault(p, []).append(f.parent)
    qa = {}
    own, weeks, comeback, qpv = page_record(page_dir)
    qa[code] = own
    for p, ds in pages.items():
        agg = {"sel": 0, "rec": 0, "sends": 0, "words": 0, "meds": []}
        for d in ds:
            q = page_record(d)[0]
            for k in ("sel", "rec", "sends", "words"):
                agg[k] += q[k]
            if q["ttvMed"] is not None:
                agg["meds"] += [q["ttvMed"]] * q["ttvN"]
        m = agg.pop("meds")
        agg["ttvMed"] = round(statistics.median(m)) if m else None
        qa[p] = agg
    orca, since = safe(orca_history, ({}, ""))
    return {"names": NAMES, "qa": qa, "qaWeeks": weeks, "comeback": comeback, "qpv": qpv, "usage": safe(lambda: usage(code), []),
            "orca": orca, "orcaSince": since, "sessions": safe(sessions, {})}


# ---------------------------------------------------------------- build, cached

def _compute(page_dir: Path) -> dict:
    code = project(page_dir)
    where = board_dir(code)
    with ThreadPoolExecutor(6) as ex:
        f = {k: ex.submit(safe, fn, None) for k, fn in
             (("workers", workers), ("board", lambda: board(code, where)), ("jobs", jobs), ("prs", lambda: prs(code)), ("load", machine_load),
              ("hours", lambda: hours(code=code)), ("an", lambda: analytics(page_dir, code)))}
        out = {k: v.result() for k, v in f.items()}
    safe(lambda: group_work(out, code, where), {})
    out.update(v=SNAPV, proj=code, pname=NAMES.get(code, code), built=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    return mask(out)


def _refresh(page_dir: Path):
    key = str(page_dir)
    try:
        res = _compute(page_dir)
        with _lock:
            b, old = res.get("board") or {}, (_mem.get(key) or (0, {}))[1]
            ob = old.get("board") or {}
            if "error" not in b:
                b["read"] = res["built"]
            elif ob and "error" not in ob:
                # a failed read keeps the last board read, marked stale: Waiting and its count stay until a read answers (r13 frame 11)
                res["board"] = {**ob, "stale": b["error"], "read": ob.get("read") or old.get("built")}
            _mem[key] = (time.time(), res)
        tmp = page_dir / (SNAP + ".tmp")
        tmp.write_text(json.dumps(res, ensure_ascii=False))
        tmp.replace(page_dir / SNAP)
    finally:
        with _lock:
            _busy.discard(key)


def build(page_dir: Path) -> dict:
    """The newest result; when it is over a minute old, a fresh one is built in the background and served on the next read."""
    page_dir = Path(page_dir)
    key = str(page_dir)
    with _lock:
        got = _mem.get(key)
    if got is None and (page_dir / SNAP).exists():
        try:
            got = ((page_dir / SNAP).stat().st_mtime, json.loads((page_dir / SNAP).read_text()))
            if got[1].get("proj") != project(page_dir) or got[1].get("v") != SNAPV:
                raise ValueError("a snapshot from before jobs and pull requests were per project, or of another project")
            with _lock:
                _mem[key] = got
        except (OSError, ValueError):
            got = None
    if got is None:
        with _cold:  # cold start: one request builds, overlapping ones wait for it
            got = _mem.get(key)
            if got is None:
                with _lock:
                    _busy.add(key)
                _refresh(page_dir)
                got = _mem[key]
        return {**got[1], "age": round(time.time() - got[0])}
    _behind(page_dir, got)
    return {**got[1], "age": round(time.time() - got[0])}


def prime(page_dir: Path) -> None:
    """At the server's start: a page with no result kept (a new copy) is built behind it, so its first open joins that build."""
    if not (Path(page_dir) / SNAP).exists():
        threading.Thread(target=build, args=(Path(page_dir),), daemon=True).start()


def _behind(page_dir: Path, got) -> None:
    # an unread or stale board is read again at once, so it recovers by itself and Try again gets a fresh answer (audit11 running 2)
    b = got[1].get("board") or {}
    if time.time() - got[0] > TTL or "error" in b or "stale" in b:
        with _lock:
            start = str(page_dir) not in _busy
            _busy.add(str(page_dir))
        if start:
            threading.Thread(target=_refresh, args=(page_dir,), daemon=True).start()


def stamp(page_dir: Path):
    """When the result in memory was built: the same one is sent as the same bytes, not dumped and checked again (1 MB on
    FastLane Drive; r12 fix12 perf). Its "age" then stays as first sent; the page reads "built". None: build() reads it first."""
    page_dir = Path(page_dir)
    with _lock:
        got = _mem.get(str(page_dir))
    if got is None:
        return None
    _behind(page_dir, got)
    return got[0]
