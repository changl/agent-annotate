#!/usr/bin/env python3
"""Host queues the Windmill backlog watch cannot see from Docker. Written to the
Windmill variable f/ops/host_backlog as {"at": ISO, "problems": {key: text}};
f/ops/backlog_watch mails them with its own and says so when this check goes quiet.

- a Send on a page that no agent has read for 30 min
- unread mail in an Orca coordinator's mailbox for 30 min
- a question from a still-running worker with no reply in its thread for 30 min
- an active Orca worker whose record asks for action
- a Mac over 80% busy (CPU or memory) for 30 min, sampled by mac-admit, with what uses its CPU

usage: host_backlog.py [--dry-run]   (launchd, every 10 min, on the M1 Max)"""
import collections
import datetime
import json
import os
import pathlib
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

WAIT_MIN = 30
VARIABLE = "f/ops/host_backlog"
STATE = pathlib.Path.home() / ".claude/annotate-state/state"
DELIVERIES = STATE / "deliveries"
OPEN = ("pending", "accepted", "started", "uncertain")
BUSY_PERCENT = 80  # Chang 2026-11-26: no new work on a Mac at 80% or more
BUSY_MIN = 30
GAP_MIN = 25  # a gap longer than two runs (asleep, off) restarts a Mac's busy clock
SAMPLE_S = 90  # mac-admit samples every Mac at once and each probe stops at 50 s
CENSUS_S = 30
MAC_ADMIT = pathlib.Path.home() / ".local/bin/mac-admit"
PRESSURE = pathlib.Path.home() / ".local/state/annotate-host-backlog/pressure.json"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
PS = {"M1Max": [], "M5Max": SSH + ["m5max"], "M1Max16": SSH + ["m1max16"]}  # this script runs on the M1 Max
ASLEEP = "ssh_host_offline_or_asleep"
SLOW = ("ssh_host_or_probe_timeout", "host_probe_failed")  # wm-test probe_host: connected, no sample in time
REACH = {"ssh_login_refused": "its SSH login was refused", "host_probe_identity": "another Mac answered for it",
         "not_configured": "it is not in the wm-test config"}


def age_min(stamp: str, now: datetime.datetime) -> float:
    return (now - datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))).total_seconds() / 60


def stamp(now: datetime.datetime) -> str:
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def sends(journals: dict, now) -> dict:
    """journals: {page: [delivery rows, oldest first]}. A Send read after an open one settles it."""
    out = {}
    for page, rows in journals.items():
        last_read = max((i for i, r in enumerate(rows) if r.get("state") == "acknowledged"), default=-1)
        waiting = [r for r in rows[last_read + 1:] if r.get("state") in OPEN and r.get("created_at")]
        if waiting and (age := age_min(waiting[0]["created_at"], now)) >= WAIT_MIN:
            out[f"send:{page}"] = f"Your Send on the {page} page has waited {int(age)} min for its agent to read it"
    return out


def orca_mail(mail: list, active: dict, objectives: dict, now) -> dict:
    """mail: full inbox records, newest first. active: {dispatch id: run id} of running workers."""
    # Only mail to a worker answers its question; the worker's own follow-ups in the thread go to the run.
    out, replied = {}, {m.get("thread_id") for m in mail
                        if m.get("thread_id") and m.get("thread_id") != m["id"] and m.get("to_handle", "").startswith("dispatch:")}
    for m in mail:
        age = age_min(m["created_at"], now)
        if age < WAIT_MIN:
            continue
        run = objectives.get(m.get("run_id"), m.get("run_id") or "?")
        if m.get("to_handle", "").startswith("run:") and not m.get("read"):
            out[f"unread:{m['id']}"] = f"Orca mail to the coordinator of \"{run}\" unread for {int(age)} min"
        elif m.get("type") == "question" and m["id"] not in replied:
            try:
                dispatch = json.loads(m.get("payload") or "{}").get("dispatchId")
            except ValueError:
                dispatch = None
            if dispatch in active:
                out[f"question:{m['id']}"] = f"A worker in \"{run}\" has waited {int(age)} min for an answer"
    return out


def orca_workers(workers: list, objectives: dict) -> dict:
    out = {}
    for w in workers:
        attention = (w.get("projection") or {}).get("attention") or {}
        if attention.get("requiresAction"):
            run = objectives.get(w.get("runId"), w.get("runId") or "?")
            why = ", ".join(attention.get("categories") or []) or "needs action"
            out[f"worker:{w['dispatchId']}"] = f"An Orca worker in \"{run}\" is stuck: {why}"
    return out


def moment(text: str) -> datetime.datetime:
    """An ISO time with its zone; raises ValueError, TypeError or AttributeError for anything else."""
    parsed = datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("time without a zone")
    return parsed


def reading(observed: dict) -> dict:
    """One Mac from `mac-admit --json` -> {"kind": measured | slow | asleep | unreachable, ...}.
    slow: it answers SSH but not the load check in time; asleep: off or asleep, which is not load."""
    error = observed.get("error")
    if error:
        if error.startswith(ASLEEP):
            return {"kind": "asleep"}
        return {"kind": "slow" if error.startswith(SLOW) else "unreachable", "why": error}
    sample = observed.get("sample") or {}
    idle, memory = sample.get("cpu_idle_percent"), sample.get("memory_free_percent")
    if not all(isinstance(v, (int, float)) and 0 <= v <= 100 for v in (idle, memory)):  # NaN fails the range
        return {"kind": "slow", "why": "sample unreadable"}
    hot = isinstance(observed.get("cores"), int) and observed.get("all_cores", 0) > observed["cores"]
    return {"kind": "measured", "idle": float(idle), "memory": float(memory), "hot": hot,
            "at": sample.get("observed_at")}


def load_state(path: pathlib.Path) -> dict:
    """The busy clocks from the last run; an unusable file or entry restarts only what it held."""
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    kept = {}
    for mac, entry in (raw.items() if isinstance(raw, dict) else ()):
        try:
            moment(entry["since"]), moment(entry["last"])
            checks, busy = int(entry["checks"]), int(entry["busy"])
            if checks >= 1 and 0 <= busy <= checks:
                kept[mac] = {"since": entry["since"], "last": entry["last"], "checks": checks, "busy": busy}
        except (TypeError, KeyError, ValueError, AttributeError):
            continue
    return kept


def families(ps_text: str, top: int = 3) -> str:
    """`ps -axo pcpu=,comm=` -> the commands using the most CPU, simulators counted as one."""
    cpu, count = collections.Counter(), collections.Counter()
    for line in ps_text.splitlines():
        parts = line.split(None, 1)
        try:
            percent = float(parts[0])
        except (IndexError, ValueError):
            continue
        path = parts[1].strip() if len(parts) > 1 else "?"
        name = "iOS simulators" if "CoreSimulator" in path else path.rsplit("/", 1)[-1]
        cpu[name] += percent
        count[name] += 1
    return ", ".join(f"{name} about {used / 100:.1f} cores ({count[name]:,} process{'' if count[name] == 1 else 'es'})"
                     for name, used in cpu.most_common(top) if used >= 50)


def pressure(readings: dict, state: dict, now, census) -> tuple:
    """readings: {mac: reading()}. state: load_state(). census(macs) -> {mac: families() text}, asked only for
    Macs reported as measured busy. Returns (problems, next state).
    A run of checks that were busy or too slow to answer, each within GAP_MIN of the last, is reported once it
    spans BUSY_MIN by the Macs' own sample times; the text says how many checks measured it busy."""
    out, following, due = {}, {}, {}
    floor = 100 - BUSY_PERCENT
    for mac, r in readings.items():
        before = state.get(mac)
        if r["kind"] == "unreachable":
            out[f"mac:{mac}"] = f"The host check cannot sample the {mac}: {REACH.get(r['why'].split(':')[0], r['why'])}"
            if before:
                following[mac] = before  # nothing known: its clock neither runs nor restarts
            continue
        busy = r["kind"] == "measured" and (r["idle"] <= floor or r["memory"] <= floor)
        if r["kind"] == "asleep" or (r["kind"] == "measured" and not busy):
            continue  # off, asleep or fine: its clock restarts
        try:
            at = moment(r.get("at"))
        except (TypeError, ValueError, AttributeError):
            at = now  # a slow Mac has no sample time
        gap = (at - moment(before["last"])).total_seconds() / 60 if before else None
        if gap is not None and 0 <= gap <= GAP_MIN:
            run = {**before, "last": at.isoformat(), "checks": before["checks"] + 1, "busy": before["busy"] + busy}
        else:
            run = {"since": at.isoformat(), "last": at.isoformat(), "checks": 1, "busy": int(busy)}
        following[mac] = run
        if (minutes := (at - moment(run["since"])).total_seconds() / 60) >= BUSY_MIN:
            due[mac] = (r, run, int(minutes))
    using = census([mac for mac, (r, _, _) in due.items() if r["kind"] == "measured"]) if due else {}
    for mac, (r, run, minutes) in due.items():
        if r["kind"] == "measured":
            now_text = f"now CPU {100 - r['idle']:.0f}% busy, memory {100 - r['memory']:.0f}% used"
            now_text += ", running hot so macOS switched cores off" if r["hot"] else ""
        else:
            now_text = "now too busy to answer"
        if not run["busy"]:
            text = f"The {mac} has not answered its load check for {minutes} min"
        elif run["busy"] == run["checks"]:
            text = f"The {mac} has been over {BUSY_PERCENT}% busy for {minutes} min ({now_text})"
        else:
            text = (f"The {mac} has been over {BUSY_PERCENT}% busy or too busy to answer for {minutes} min "
                    f"(measured busy in {run['busy']} of {run['checks']} checks; {now_text})")
        out[f"mac:{mac}"] = text + (f"; using the most CPU: {using[mac]}" if using.get(mac) else "")
    return out, following


def _run(command: list, timeout: int) -> str:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def census(macs: list) -> dict:
    """What uses each Mac's CPU, all Macs at once; an empty text when ps does not answer in time."""
    macs = [mac for mac in macs if mac in PS]
    if not macs:
        return {}
    with ThreadPoolExecutor(len(macs)) as pool:
        texts = pool.map(lambda mac: families(_run(PS[mac] + ["ps", "-axo", "pcpu=,comm="], CENSUS_S)), macs)
    return dict(zip(macs, texts))


def sample_macs() -> list:
    # mac-admit needs Python 3.11 and runs on its own python3; launchd's PATH puts Homebrew's first.
    proc = subprocess.run([str(MAC_ADMIT), "--json"], capture_output=True, text=True, timeout=SAMPLE_S,
                          stdin=subprocess.DEVNULL)
    try:
        observed = json.loads(proc.stdout)
    except ValueError:
        observed = None
    if proc.returncode or not isinstance(observed, list) or not all(
            isinstance(o, dict) and isinstance(o.get("target"), str) for o in observed):
        raise RuntimeError(f"mac-admit exited {proc.returncode}: {(proc.stderr.strip() or proc.stdout.strip())[-160:]}")
    return observed


def mac_pressure(now, save: bool) -> dict:
    """Raises when the Macs cannot be sampled; the clocks on disk are then kept for the next run."""
    problems, following = pressure({o["target"]: reading(o) for o in sample_macs()}, load_state(PRESSURE), now, census)
    if save:
        PRESSURE.parent.mkdir(parents=True, exist_ok=True)
        partial = PRESSURE.with_suffix(".partial")
        partial.write_text(json.dumps(following, sort_keys=True))
        os.replace(partial, PRESSURE)  # a run stopped mid-write keeps the previous clocks
    return problems


def _orca(*args) -> dict:
    # Without a terminal binding Orca answers for every Run; from an agent's terminal it would scope to that Run.
    env = {k: v for k, v in os.environ.items() if not k.startswith("ORCA_")}
    proc = subprocess.run(["orca", "orchestration", *args, "--json", "--full"],
                          capture_output=True, text=True, timeout=60, env=env)
    return json.loads(proc.stdout)["result"]


def registered(project: str) -> set:
    try:
        return set(json.loads((STATE / f"{project}.json").read_text()).get("slugs") or {})
    except (OSError, ValueError, AttributeError):
        return set()


def collect(now, save: bool = True) -> dict:
    with ThreadPoolExecutor(1) as pool:
        macs = pool.submit(mac_pressure, now, save)  # sampling the Macs over SSH overlaps the queue reads
        problems = queues(now)
        try:
            problems |= macs.result()
        except Exception as error:  # noqa: BLE001 - the Mac check is extra and must never cost the queue report
            problems["macs:unreadable"] = f"The host check could not sample the Macs: {str(error)[:200] or type(error).__name__}"
    return problems


def queues(now) -> dict:
    journals = {}
    for path in sorted(DELIVERIES.glob("*/*.json")):
        if path.stem not in registered(path.parent.name):  # an unpublished page keeps its journal
            continue
        try:
            journals[f"{path.parent.name}/{path.stem}"] = list(json.loads(path.read_text()).get("deliveries", {}).values())
        except (OSError, ValueError, AttributeError):
            continue
    problems = sends(journals, now)
    try:
        objectives = {r["id"]: r["objective"].splitlines()[0][:70] for r in _orca("run-list")["runs"]}
        workers, cursor = [], []
        for _ in range(10):  # Orca pages at 100; follow nextCursor
            page = _orca("worker-list", "--terminal-state", "active", "--limit", "100", *cursor)
            workers += page["workers"]
            following = (page.get("page") or {}).get("nextCursor")
            if not following:
                break
            cursor = ["--cursor", following]
        active = {w["dispatchId"]: w.get("runId") for w in workers}
        # shortcut: the newest 500 messages reach back about 39 h (2026-11-26); mail older than that is not seen.
        problems |= orca_mail(_orca("inbox", "--limit", "500")["messages"], active, objectives, now)
        problems |= orca_workers(workers, objectives)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        problems["orca:unreadable"] = f"The host check could not read Orca: {type(error).__name__}"
    return problems


def main() -> int:
    now = datetime.datetime.now(datetime.timezone.utc)  # timezone.utc: launchd runs the system Python 3.9
    body = json.dumps({"at": stamp(now), "problems": collect(now, "--dry-run" not in sys.argv)}, sort_keys=True)
    if "--dry-run" in sys.argv:
        print(body)
        return 0
    return subprocess.run(["wmill", "variable", "add", body, VARIABLE, "--yes", "--no-secret",
                           "--description", "scripts/host_backlog.py on the M1 Max; read by f/ops/backlog_watch"],
                          capture_output=True, stdin=subprocess.DEVNULL, timeout=120).returncode


if __name__ == "__main__":
    sys.exit(main())
