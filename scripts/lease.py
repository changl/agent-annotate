#!/usr/bin/env python3
"""Leases for shared resources (ports, CI slots, disk budget) so workers need no "GO" reply.

  lease.py take NAME [--ttl-min 120] [--note TEXT]   grant if free, expired, or already yours
  lease.py release [NAME ...]                        yours only; no NAME releases all of yours
  lease.py list

One JSON file per lease under $ORCA_RUNS_DIR/<run>/leases (default ~/.local/state/orca-runs).
--run defaults to $ORCA_RUN; --owner to $ORCA_TERMINAL_HANDLE. Exit 0 granted/released, 1 refused.
Ask the coordinator only when a take is refused.
"""
import argparse
import fcntl
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def lease_dir(run):
    root = Path(os.environ.get("ORCA_RUNS_DIR") or Path.home() / ".local/state/orca-runs")
    path = root / run / "leases"
    path.mkdir(parents=True, exist_ok=True)
    return path


def stamp(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def take(d, name, owner, ttl_min, note, now):
    path = d / f"{name}.json"
    held = read(path)
    if held and held["owner"] != owner and held["expires"] > now:
        print(f"refused {name}: held by {held['owner']} until {stamp(held['expires'])}"
              + (f" ({held['note']})" if held.get("note") else "") + "; ask the coordinator")
        return 1
    lease = {"name": name, "owner": owner, "taken": now, "expires": now + ttl_min * 60, "note": note or ""}
    tmp = d / f".{name}.tmp"
    tmp.write_text(json.dumps(lease))
    os.replace(tmp, path)
    print(f"granted {name} to {owner} until {stamp(lease['expires'])}")
    return 0


def release(d, names, owner, now):
    paths = [d / f"{n}.json" for n in names] or sorted(d.glob("*.json"))
    refused = 0
    for path in paths:
        held = read(path)
        if held is None:
            if names:
                print(f"not held: {path.stem}")
            continue
        if held["owner"] != owner and held["expires"] > now:
            if names:
                print(f"refused {path.stem}: held by {held['owner']}")
                refused = 1
            continue
        if held["owner"] == owner or names:
            path.unlink()
            print(f"released {path.stem}")
    return refused


def list_leases(d, now):
    rows = [read(p) for p in sorted(d.glob("*.json"))]
    rows = [r for r in rows if r]
    if not rows:
        print("no leases")
    for r in rows:
        state = "expired" if r["expires"] <= now else f"until {stamp(r['expires'])}"
        print(f"{r['name']} {r['owner']} {state}" + (f" · {r['note']}" if r.get("note") else ""))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["take", "release", "list"])
    parser.add_argument("names", nargs="*")
    parser.add_argument("--run", default=os.environ.get("ORCA_RUN"))
    parser.add_argument("--owner", default=os.environ.get("ORCA_TERMINAL_HANDLE"))
    parser.add_argument("--ttl-min", type=int, default=120)
    parser.add_argument("--note")
    args = parser.parse_args(argv)
    if not args.run or not NAME.match(args.run):
        parser.error("--run RUN (or $ORCA_RUN) is required")
    bad = [n for n in args.names if not NAME.match(n)]
    if bad:
        parser.error(f"bad lease name {bad[0]!r}: letters, digits, . _ - only")
    if args.action != "list" and not args.owner:
        parser.error("--owner (or $ORCA_TERMINAL_HANDLE) is required")
    if args.action == "take" and len(args.names) != 1:
        parser.error("take needs exactly one NAME")
    d = lease_dir(args.run)
    with open(d / ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # one take/release at a time, so expiry checks cannot race
        now = int(time.time())
        if args.action == "take":
            return take(d, args.names[0], args.owner, max(1, args.ttl_min), args.note, now)
        if args.action == "release":
            return release(d, args.names, args.owner, now)
        return list_leases(d, now)


if __name__ == "__main__":
    sys.exit(main())
