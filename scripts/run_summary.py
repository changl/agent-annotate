#!/usr/bin/env python3
"""Render an Orca Run, its Beads and leases into a digest of at most 40 lines.

  run_summary.py RUN [--beads-dir DIR]

A coordinator reads this instead of carrying run history in context, and a fresh
session reads it when the old one recycles (docs/orchestration-recycle.md).
Sources: orca orchestration run-show / task-list / worker-list / gate-list,
`bd list --status in_progress` and `bd ready` (run in --beads-dir, default cwd),
leases and status.log under $ORCA_RUNS_DIR/<run> (default ~/.local/state/orca-runs).
"""
import argparse
import collections
import json
import os
import subprocess
import sys
import time
from pathlib import Path

MAX_LINES = 40
LIST = 6  # items listed per section; the rest are counted


def run_json(argv, cwd=None):
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, cwd=cwd, timeout=60)
        data = json.loads(proc.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    if isinstance(data, dict) and "ok" in data:
        return data.get("result") if data.get("ok") else None
    return data


def clip(text, n=70):
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def listed(rows, fmt):
    out = [fmt(r) for r in rows[:LIST]]
    if len(rows) > LIST:
        out.append(f"  … {len(rows) - LIST} more")
    return out


def render(run, orca, beads, leases, status_lines, now):
    lines = []
    show = orca.get("run") or {}
    lines.append(f"Run {run}: {clip(show.get('objective'), 90)}")
    tasks = orca.get("tasks") or []
    titles = {t.get("id"): t.get("title") for t in tasks}
    counts = collections.Counter(t.get("status") for t in tasks)
    lines.append("Tasks: " + (" · ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "none"))
    workers = [w for w in orca.get("workers") or [] if w.get("liveness") == "live" and w.get("state") not in ("succeeded", "failed")]
    lines.append(f"Workers live: {len(workers)}")
    lines += listed(workers, lambda w: f"  {w.get('dispatchId')} {w.get('agent') or ''} {clip(titles.get(w.get('taskId')), 60)}")
    stuck = [w for w in orca.get("workers") or [] if w.get("liveness") == "live" and w.get("state") in ("succeeded", "failed")]
    if stuck:
        lines.append(f"Settled but still live: {' '.join(w.get('dispatchId') for w in stuck[:LIST])}")
    open_tasks = [t for t in tasks if t.get("status") not in ("completed", "dispatched")]
    if open_tasks:
        lines.append(f"Tasks not started or not done: {len(open_tasks)}")
        lines += listed(open_tasks, lambda t: f"  {t.get('id')} {t.get('status')} {clip(t.get('title'), 60)}")
    gates = [g for g in orca.get("gates") or [] if g.get("status") in (None, "pending")]
    if gates:
        lines.append(f"Decision gates pending: {len(gates)}")
    if beads is None:
        lines.append("Beads: bd unavailable here")
    else:
        lines.append(f"Beads in progress: {len(beads['in_progress'])} · ready: {len(beads['ready'])}")
        lines += listed(beads["in_progress"], lambda b: f"  {b.get('id')} P{b.get('priority')} {clip(b.get('title'), 64)}")
        lines += listed(beads["ready"], lambda b: f"  ready {b.get('id')} {clip(b.get('title'), 58)}")
    live = [r for r in leases if r.get("expires", 0) > now]
    lines.append(f"Leases: {len(live)} held" + (f", {len(leases) - len(live)} expired" if len(leases) > len(live) else ""))
    lines += listed(live, lambda r: f"  {r.get('name')} {r.get('owner')} until {time.strftime('%H:%MZ', time.gmtime(r['expires']))}")
    lines.append(f"Status log: {len(status_lines)} line(s)" + (", last:" if status_lines else ""))
    for s in status_lines[-3:]:
        lines.append(f"  {(s.get('t') or '')[11:16]}Z {s.get('dispatch') or s.get('from')}: {clip(s.get('subject'), 60)}")
    if len(lines) > MAX_LINES:
        lines = lines[: MAX_LINES - 1] + [f"(digest cut at {MAX_LINES} lines)"]
    return lines


def collect(run, beads_dir):
    orchestration = ["orca", "orchestration"]
    orca = {
        "run": run_json([*orchestration, "run-show", "--id", run, "--json"]),
        "tasks": (run_json([*orchestration, "task-list", "--run", run, "--json"]) or {}).get("tasks"),
        "workers": (run_json([*orchestration, "worker-list", "--run", run, "--json"]) or {}).get("workers"),
        "gates": (run_json([*orchestration, "gate-list", "--run", run, "--json"]) or {}).get("gates"),
    }
    in_progress = run_json(["bd", "list", "--status", "in_progress", "--json"], cwd=beads_dir)
    ready = run_json(["bd", "ready", "--json"], cwd=beads_dir)
    beads = None if in_progress is None or ready is None else {"in_progress": in_progress, "ready": ready}
    run_dir = Path(os.environ.get("ORCA_RUNS_DIR") or Path.home() / ".local/state/orca-runs") / run
    leases = []
    for p in sorted((run_dir / "leases").glob("*.json")):
        try:
            leases.append(json.loads(p.read_text()))
        except (OSError, ValueError):
            pass
    status_lines = []
    try:
        status_lines = [json.loads(line) for line in (run_dir / "status.log").read_text().splitlines() if line.strip()]
    except (OSError, ValueError):
        pass
    return orca, beads, leases, status_lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run")
    parser.add_argument("--beads-dir", default=None)
    args = parser.parse_args(argv)
    print("\n".join(render(args.run, *collect(args.run, args.beads_dir), now=int(time.time()))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
