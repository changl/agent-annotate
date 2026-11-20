"""Running and Analytics data for the prototype page: live and read only.

Sources, each read at most once a minute (the whole result is cached; a stale copy is served while a fresh one is built):
- workers: this Mac's Orca record (orchestration.db, read only) and `orca orchestration worker-list --environment` for the other Macs;
- scheduled jobs and runs: `wmill schedule list` and `wmill job list` with the stored login (no token is read or passed here);
- tasks: the FastLane Drive board through `bd --readonly`;
- pull requests: `gh search prs`, read only;
- daily usage: FastLane Drive's usage reports; Analytics: the page's own record and the other review pages' records;
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
USAGE = HOME / "projects/FastLane Drive/planning/operations/usage-reports"
ORCA_DB = HOME / "Library/Application Support/Orca/orchestration.db"
LOAD_TSV = HOME / ".local/share/machine-load/load.tsv"
PROJECTS = HOME / "projects"
GH_OWNER = "Fast-Lane-Drive"
TTL = 60  # seconds a read stays fresh: the page never asks a source more than once a minute
SNAP = "proto-running.json"
MACS = [("M1 Max", None), ("M5 Max", "M5Max"), ("M1 Max 16", "M1Max16")]
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


_BEAD = re.compile(r"\bFLD-[a-z0-9]+(?:\.\d+)*\b")


def _bead(db, task_id):
    """The first task on the board a worker's brief names, or None."""
    r = db.execute("select coalesce(task_title, '') || ' ' || coalesce(spec, '') from tasks where id = ?", (task_id,)).fetchone()
    m = _BEAD.search(r[0]) if r else None
    return m.group(0) if m else None


def group_work(out):
    """Workers grouped by the real work: the board epic (else the task) their brief names. Every FLD worker shares one run,
    so the run's objective said the same thing on every Mac."""
    ws = [w for m in (out.get("workers") or {}).values() if isinstance(m, dict) for w in m.get("workers") or []]
    beads = (out.get("board") or {}).get("beads") or {}
    roots = {w["bead"].split(".")[0] for w in ws if w.get("bead")}
    titles = {k: beads[k]["t"] for k in roots if k in beads}
    missing = sorted(roots - titles.keys())
    if missing:  # closed epics are not on Running's open list
        rows = safe(lambda: run_json(["bd", "-C", str(FLD_BOARD), "--readonly", "show", *missing, "--json"], timeout=60), [])
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
    mg = bool(re.search(r"merge", (title or "") + m.group(1), re.I))
    why = next((t for r, t in _WHY if re.search(r, m.group(1), re.I)), "waits for your yes to merge it" if mg else "waits for your answer on its question")
    return why, mg


def _cut(s, n=2500):
    s = re.sub(r"https?://\S+", "a link", s or "").strip()
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + " …"


GROUPS = [("ready", "Ready to start"), ("in_progress", "In progress"), ("waiting", "Waiting on another task"), ("blocked", "Blocked"), ("deferred", "Deferred")]


def board():
    bd = ["bd", "-C", str(FLD_BOARD), "--readonly"]
    rows = run_json([*bd, "list", "--status", "open,in_progress,blocked,deferred", "--flat", "--limit", "0", "--json"], timeout=60)
    ready = {b["id"] for b in run_json([*bd, "ready", "--limit", "0", "--json"], timeout=60)}
    closed = safe(lambda: run_json([*bd, "count", "--status", "closed", "--json"]).get("count"), None)
    full = {}
    ids = [b["id"] for b in rows]
    for i in range(0, len(ids), 60):  # bd show takes many ids at once; 60 a call keeps argv short
        for b in run_json([*bd, "show", *ids[i:i + 60], "--json"], timeout=90):
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

def jobs():
    """Enabled Windmill schedules with their newest 12 runs, failing ones first."""
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
        out.append({"name": name[:1].upper() + name[1:], "path": s["path"], "cron": s.get("schedule"), "tz": s.get("timezone"),
                    "runs": r, "failing": bool(done and done[0]["ok"] is False),
                    "since": next((x["t"] for x in done if x["ok"] is not False), None) if done and done[0]["ok"] is False else None})
    out.sort(key=lambda j: (not j["failing"], j["name"]))
    return out


def prs():
    rows = run_json(["gh", "search", "prs", "--owner", GH_OWNER, "--sort", "updated", "--limit", "15",
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


def usage():
    use = []
    for f in sorted(USAGE.glob("2026-*.md")):
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
    orc = defaultdict(lambda: {"workers": 0, "ok": 0, "failed": 0, "stopped": 0, "codex": 0, "claude": 0, "weeks": Counter(), "days": Counter()})
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
            o["days"][at[:10]] += 1
    since = (db.execute("select min(created_at) from dispatch_contexts").fetchone()[0] or "")[:10]
    db.close()
    return {p: {**{k: v for k, v in o.items() if k not in ("weeks", "days")}, "weeks": sorted(o["weeks"].items())[-10:],
                "days": sorted(o["days"].items())[-30:]} for p, o in orc.items()}, since


def sessions():
    ses = Counter()
    for d in (HOME / ".claude/projects").glob("*"):
        ses[proj_of(d.name.replace("-", " "))] += sum(1 for _ in d.glob("*.jsonl"))
    return dict(ses)


def analytics(page_dir: Path):
    pages = {}
    for f in sorted(PROJECTS.glob("*/reviews/*/rounds.ndjson")):
        p = proj_of(f.parts[len(PROJECTS.parts)])
        if p != "fld":  # this project's numbers come from the page's own record below
            pages.setdefault(p, []).append(f.parent)
    qa = {}
    own, weeks, comeback, qpv = page_record(page_dir)
    qa["fld"] = own
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
    return {"names": NAMES, "qa": qa, "qaWeeks": weeks, "comeback": comeback, "qpv": qpv, "usage": safe(usage, []),
            "orca": orca, "orcaSince": since, "sessions": safe(sessions, {})}


# ---------------------------------------------------------------- build, cached

def _compute(page_dir: Path) -> dict:
    with ThreadPoolExecutor(6) as ex:
        f = {k: ex.submit(safe, fn, None) for k, fn in
             (("workers", workers), ("board", board), ("jobs", jobs), ("prs", prs), ("load", machine_load), ("an", lambda: analytics(page_dir)))}
        out = {k: v.result() for k, v in f.items()}
    safe(lambda: group_work(out), {})
    out["built"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return mask(out)


def _refresh(page_dir: Path):
    key = str(page_dir)
    try:
        res = _compute(page_dir)
        with _lock:
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
    if time.time() - got[0] > TTL:
        with _lock:
            start = key not in _busy
            _busy.add(key)
        if start:
            threading.Thread(target=_refresh, args=(page_dir,), daemon=True).start()
    return {**got[1], "age": round(time.time() - got[0])}
