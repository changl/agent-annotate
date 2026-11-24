#!/usr/bin/env python3
"""Hourly housekeeping without an agent: one summary line per check, judgment items to a file.

  sweep.py beads [--beads-dir DIR]     open, ready, stale in-progress, closed without proof
  sweep.py disk                        free space, bus size, buses quiet for 30+ days
  sweep.py sessions [--apply]          finished Orca worktrees; --apply removes them
  sweep.py owners                      pages used this week whose owning agent is not running
  sweep.py all [--apply]               the four lines

Writes the summary lines, a blank line, then the items that need a coordinator's
judgment to $ANNOTATE_SWEEP_DIR/latest.txt (default ~/.local/share/annotate-sweeps);
`scripts/run_summary.py` shows the summary lines. No AI runs here. A worktree is
removed only with --apply, only when its PR is merged, its bead is closed and its
tree is clean, and never when it is a main worktree or on DENY.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tempfile
from pathlib import Path

DENY = ("/Users/changlee/orca/workspaces/codex/rebex-library-performance",)
OUT = Path(os.environ.get("ANNOTATE_SWEEP_DIR") or Path.home() / ".local/share/annotate-sweeps")
BUS_ROOT = Path(os.environ.get("ANNOTATE_BUS_ROOT") or Path.home() / ".claude/annotate-bus")
STATE_DIR = Path(os.environ.get("ANNOTATE_STATE_DIR") or Path.home() / ".claude/annotate-state/state")
ACTIVE_DAYS = 7
QUIET_DAYS = 30
STALE_HOURS = 24
PROOF_DAYS = 7


def run_json(argv, cwd=None):
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, cwd=cwd, timeout=120)
        data = json.loads(proc.stdout) if proc.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    if isinstance(data, dict) and "ok" in data:
        return data.get("result") if data.get("ok") else None
    return data


def age_hours(stamp, now):
    try:
        then = datetime.datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0
    return (now - then) / 3600


def beads(beads_dir, now):
    bd = ["bd", "list", "--json", "--limit", "0"]
    opened = run_json([*bd, "--status", "open", "--brief"], beads_dir)
    working = run_json([*bd, "--status", "in_progress", "--brief"], beads_dir)
    ready = run_json(["bd", "ready", "--json", "--limit", "0", "--brief"], beads_dir)
    since = time.strftime("%Y-%m-%d", time.gmtime(now - PROOF_DAYS * 86400))
    closed = run_json([*bd, "--status", "closed", "--closed-after", since], beads_dir)
    if None in (opened, working, ready, closed):
        return "beads: bd unavailable here", []
    stale = [b for b in working if age_hours(b.get("updated_at"), now) > STALE_HOURS]
    unproven = [b for b in closed if len((b.get("close_reason") or "").strip()) < 20]
    items = [f"bead {b['id']} in progress, untouched {age_hours(b.get('updated_at'), now):.0f} h: {b.get('title', '')}"
             for b in stale]
    items += [f"bead {b['id']} closed without proof ({(b.get('close_reason') or 'no reason').strip()!r}): "
              f"{b.get('title', '')}" for b in unproven]
    line = (f"beads: {len(opened)} open · {len(ready)} ready · {len(stale)} in progress over {STALE_HOURS} h · "
            f"{len(unproven)} closed without proof")
    return line, items


def disk(now):
    free = shutil.disk_usage(Path.home()).free / 1024 ** 3
    buses = sorted(BUS_ROOT.glob("*/*.ndjson")) if BUS_ROOT.is_dir() else []
    size = sum(p.stat().st_size for p in BUS_ROOT.rglob("*") if p.is_file()) if BUS_ROOT.is_dir() else 0
    quiet = [p for p in buses if now - p.stat().st_mtime > QUIET_DAYS * 86400]
    items = [f"bus {p.parent.name}/{p.stem} quiet {(now - p.stat().st_mtime) / 86400:.0f} days "
             f"(annotate prune-bus --apply archives it)" for p in quiet]
    line = f"disk: {free:.0f} GiB free · buses {size / 1024 ** 3:.1f} GiB · {len(quiet)} quiet buses over {QUIET_DAYS} days"
    return line, items


def bead_ids(texts):
    """Every hyphenated prefix ending in a 3-4 character segment: fld-13hb-auth -> fld-13hb, fld-13hb-auth."""
    found = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9.-]*", " ".join(texts)):
        parts = token.split("-")
        found += ["-".join(parts[:i + 1]) for i in range(1, len(parts))
                  if re.fullmatch(r"[a-z0-9]{3,4}(?:\.[0-9]+)*", parts[i])]
    return list(dict.fromkeys(found))


def bead_closed(worktree, texts):
    """True when the bead named in the PR or branch exists and is closed; None when none is named."""
    found = None
    for bead in bead_ids(texts)[:8]:
        record = run_json(["bd", "show", bead, "--json"], worktree)
        record = record[0] if isinstance(record, list) and record else record
        if isinstance(record, dict) and record.get("id") == bead:
            if record.get("status") != "closed":
                return False
            found = True
    return found


def sessions(apply):
    listing = run_json(["orca", "worktree", "list", "--json", "--limit", "1000"])
    if listing is None:
        return "sessions: orca unavailable here", []
    finished, items, removed = [], [], 0
    for tree in listing.get("worktrees") or []:
        path = tree.get("path") or ""
        if tree.get("hostId") != "local" or tree.get("isMainWorktree"):
            continue
        if any(os.path.realpath(path) == os.path.realpath(d) for d in DENY):
            items.append(f"worktree {path}: on the deny list; not inspected")
            continue
        if not os.path.isdir(path):
            continue
        status = subprocess.run(["git", "--no-optional-locks", "-C", path, "status", "--porcelain"],
                                capture_output=True, text=True)
        if status.returncode or status.stdout.strip():
            continue
        branch = re.sub(r"^refs/heads/", "", tree.get("branch") or "")
        prs = run_json(["gh", "pr", "list", "--head", branch, "--state", "merged", "--json", "number,title,body",
                        "--limit", "1"], path) if branch else None
        if not prs:
            continue
        pr = prs[0]
        closed = bead_closed(path, [os.path.basename(path), branch, pr.get("title") or "", pr.get("body") or ""])
        if closed is None:
            items.append(f"worktree {path}: PR #{pr['number']} merged, tree clean, no bead named; your call")
            continue
        if not closed:
            continue
        finished.append(tree)
        if apply:
            done = run_json(["orca", "worktree", "rm", "--worktree", f"id:{tree['id']}", "--json"])
            removed += done is not None
            items.append(f"worktree {path}: " + ("removed" if done is not None else "removal failed"))
        else:
            items.append(f"worktree {path}: finished (PR #{pr['number']}); sweep.py sessions --apply removes it")
    line = f"sessions: {len(finished)} finished worktrees (PR merged, bead closed, clean tree) · {removed} removed"
    return line, items


def owner_running(target):
    """The recorded owner process still runs (same pid and start time)."""
    try:
        os.kill(int(target["pid"]), 0)
        start = subprocess.run(["ps", "-p", str(target["pid"]), "-o", "lstart="],
                               capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, KeyError, TypeError, ValueError, subprocess.SubprocessError):
        return False
    return not target.get("process_start") or start == target["process_start"]


def last_activity(bus):
    """Newest bus event a person or agent made; restarts (page_revived) do not count."""
    try:
        with open(bus, "rb") as stream:
            stream.seek(max(0, os.path.getsize(bus) - 65536))  # shortcut: last 64 KB; pages idle that long are not "recent"
            tail = stream.read().splitlines()
    except (OSError, TypeError):
        return None
    for line in reversed(tail):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("ts") and event.get("event") not in ("page_revived", "notice_emitted"):
            return event["ts"]
    return None


def owners(now):
    """Pages used this week whose owning agent is not running: Sends there wait for nobody."""
    items, waiting = [], 0
    for path in sorted(STATE_DIR.glob("*.json")):
        try:
            state = json.loads(path.read_text())
            slugs = state.get("slugs") or {}
        except (OSError, ValueError, AttributeError):
            continue
        for slug, record in slugs.items():
            if not isinstance(record, dict) or record.get("archived") or record.get("consolidated_into"):
                continue
            stamp = last_activity(record.get("bus_file"))
            if not stamp or age_hours(stamp, now) > ACTIVE_DAYS * 24:
                continue
            target = record.get("owner_target")
            if isinstance(target, dict) and owner_running(target):
                continue
            project = state.get("project") or path.stem
            try:
                rows = json.loads((STATE_DIR / "deliveries" / project / f"{slug}.json").read_text())["deliveries"].values()
                queued = sum(row.get("state") == "pending" for row in rows)
            except (OSError, ValueError, KeyError, AttributeError):
                queued = 0
            waiting += queued
            try:
                meta = json.loads((Path(record["slug_dir"]) / "current.meta.json").read_text())
            except (OSError, ValueError, KeyError, TypeError):
                meta = {}
            name = (meta.get("name") if isinstance(meta, dict) else None) or record.get("title") or slug
            why = ("no agent has claimed it from an Orca terminal" if not isinstance(target, dict)
                   else "the agent that owns it has stopped and has not come back")
            sends = f"; {queued} Send{'s' if queued != 1 else ''} waiting" if queued else ""
            items.append(f"page {name} ({project}/{slug}), used {age_hours(stamp, now):.0f} h ago: {why}{sends}. "
                         f"Resume that session or run `annotate claim {slug}` in the agent that should own it")
    line = (f"owners: {len(items)} page{'s' if len(items) != 1 else ''} used in the last {ACTIVE_DAYS} days "
            f"with no running owner · {waiting} Send{'s' if waiting != 1 else ''} waiting")
    return line, items


def atomic_write(path, output):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix="." + path.name + "-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(output)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("check", choices=("beads", "disk", "sessions", "owners", "all"))
    parser.add_argument("--beads-dir")
    parser.add_argument("--apply", action="store_true", help="sessions: remove finished worktrees")
    args = parser.parse_args(argv)
    now = time.time()
    results = []
    if args.check in ("beads", "all"):
        results.append(beads(args.beads_dir, now))
    if args.check in ("disk", "all"):
        results.append(disk(now))
    if args.check in ("sessions", "all"):
        results.append(sessions(args.apply))
    if args.check in ("owners", "all"):
        results.append(owners(now))
    lines = [line for line, _ in results]
    items = [item for _, found in results for item in found]
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(now))
    (OUT / "latest.txt").write_text("\n".join([f"sweep {stamp}", *lines, "", *items]) + "\n")
    exit_code = 0
    if args.check == "all" and os.environ.get("ANNOTATE_OWNERSHIP_MANIFEST"):
        ownership_status = "ok"
        try:
            subprocess.run([sys.executable, "-I", os.environ["ANNOTATE_OWNERSHIP_MANIFEST"],
                            "--out", str(OUT / "ownership-latest.json")], check=True, timeout=300)
        except (OSError, subprocess.SubprocessError) as exc:
            exit_code = 1
            ownership_status = "error"
            try:
                atomic_write(OUT / "ownership-latest.json", json.dumps({"schema": "ownership-manifest/1",
                             "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                             "status": "error", "error": str(exc), "macs": {}, "held": True}) + "\n")
            except OSError as write_error:
                print(f"ownership error artifact failed: {write_error}", file=sys.stderr)
            print(f"ownership manifest failed: {exc}", file=sys.stderr)
        lines.append(f"ownership: {ownership_status} {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
        try:
            atomic_write(OUT / "latest.txt", "\n".join([f"sweep {stamp}", *lines, "", *items]) + "\n")
        except OSError as write_error:
            print(f"ownership summary update failed: {write_error}", file=sys.stderr)
    print("\n".join(lines))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
