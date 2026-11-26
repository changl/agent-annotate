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
import re
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
MAC_ADMIT = pathlib.Path.home() / ".local/bin/mac-admit"
PRESSURE = pathlib.Path.home() / ".local/state/annotate-host-backlog/pressure.json"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
PS = {"M1Max": [], "M5Max": SSH + ["m5max"], "M1Max16": SSH + ["m1max16"]}  # this script runs on the M1 Max
ADMIT_LINE = re.compile(r"^(admit|room|wait|stop) (\S+): (.*)$")


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


def reading(text: str):
    """One `mac-admit --no-reserve --mac X` output -> {"idle", "memory", "hot"}, idle None when the Mac answers
    too slowly to sample, or None when it is off, asleep or refuses SSH (that is not load)."""
    for line in text.splitlines():
        match = ADMIT_LINE.match(line.strip())
        if not match:
            continue
        rest = match.group(3)
        if rest.startswith("ssh_host_or_probe_timeout") or rest.startswith("its load sample failed"):
            return {"idle": None, "memory": None, "hot": False}
        # The first idle-and-memory pair is the sample; a wait reason before it and the figures after recent
        # starts both count reservations, which are not load.
        figures = re.search(r"cpu idle ([\d.]+)%, memory free ([\d.]+)%", rest)
        if match.group(1) != "stop" and figures:
            return {"idle": float(figures.group(1)), "memory": float(figures.group(2)), "hot": "too hot" in rest}
    return None


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
    """readings: {mac: reading() or None}. state: {mac: {"since", "last"}} from the previous run.
    census(mac) -> families() text, asked only for a Mac being reported. Returns (problems, next state)."""
    out, following = {}, {}
    floor = 100 - BUSY_PERCENT
    for mac, r in readings.items():
        if r is None or (r["idle"] is not None and r["idle"] > floor and r["memory"] > floor):
            continue  # off, asleep or fine: its clock restarts
        before = state.get(mac) or {}
        since = before.get("since") if before.get("last") and age_min(before["last"], now) <= GAP_MIN else None
        following[mac] = {"since": since or stamp(now), "last": stamp(now)}
        minutes = age_min(following[mac]["since"], now)
        if minutes < BUSY_MIN:
            continue
        if r["idle"] is None:
            now_text = "too busy to answer its load check"
        else:
            now_text = f"CPU {100 - r['idle']:.0f}% busy, memory {100 - r['memory']:.0f}% used"
        now_text += ", running hot so macOS switched cores off" if r["hot"] else ""
        using = census(mac)
        out[f"mac:{mac}"] = (f"The {mac} has been over {BUSY_PERCENT}% busy for {int(minutes)} min ({now_text})"
                             + (f"; using the most CPU: {using}" if using else ""))
    return out, following


def _run(command: list, timeout: int) -> str:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def mac_pressure(now, save: bool) -> dict:
    # mac-admit runs on its own python3 (it needs 3.11); launchd's PATH puts Homebrew's first.
    macs = list(PS)
    with ThreadPoolExecutor(len(macs)) as pool:
        outputs = pool.map(lambda mac: _run([str(MAC_ADMIT), "--no-reserve", "--mac", mac], 120), macs)
    readings = {mac: reading(text) for mac, text in zip(macs, outputs)}
    try:
        state = json.loads(PRESSURE.read_text())
    except (OSError, ValueError):
        state = {}
    problems, following = pressure(readings, state, now,
                                   lambda mac: families(_run(PS[mac] + ["ps", "-axo", "pcpu=,comm="], 60)))
    if save:
        PRESSURE.parent.mkdir(parents=True, exist_ok=True)
        PRESSURE.write_text(json.dumps(following, sort_keys=True))
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
    try:
        problems |= mac_pressure(now, save)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        problems["macs:unreadable"] = f"The host check could not sample the Macs: {type(error).__name__}"
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
