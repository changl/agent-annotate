#!/usr/bin/env python3
"""Host queues the Windmill backlog watch cannot see from Docker. Written to the
Windmill variable f/ops/host_backlog as {"at": ISO, "problems": {key: text}};
f/ops/backlog_watch mails them with its own and says so when this check goes quiet.

- a Send on a page that no agent has read for 30 min
- unread mail in an Orca coordinator's mailbox for 30 min
- a question from a still-running worker with no reply in its thread for 30 min
- an active Orca worker whose record asks for action

usage: host_backlog.py [--dry-run]   (launchd, every 10 min, on the M1 Max)"""
import datetime
import json
import os
import pathlib
import subprocess
import sys

WAIT_MIN = 30
VARIABLE = "f/ops/host_backlog"
STATE = pathlib.Path.home() / ".claude/annotate-state/state"
DELIVERIES = STATE / "deliveries"
OPEN = ("pending", "accepted", "started", "uncertain")


def age_min(stamp: str, now: datetime.datetime) -> float:
    return (now - datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))).total_seconds() / 60


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


def collect(now) -> dict:
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
    body = json.dumps({"at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "problems": collect(now)}, sort_keys=True)
    if "--dry-run" in sys.argv:
        print(body)
        return 0
    return subprocess.run(["wmill", "variable", "add", body, VARIABLE, "--yes", "--no-secret",
                           "--description", "scripts/host_backlog.py on the M1 Max; read by f/ops/backlog_watch"],
                          capture_output=True, stdin=subprocess.DEVNULL, timeout=120).returncode


if __name__ == "__main__":
    sys.exit(main())
