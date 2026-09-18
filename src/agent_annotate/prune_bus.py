#!/usr/bin/env python3
"""prune-bus — archive annotate comment buses that have gone quiet.

Every published review leaves a bus at <bus root>/<project>/<slug>.ndjson
forever. The UserPromptSubmit hook walks all of them on every prompt, so finished
reviews cost latency on every turn of every session, indefinitely.

Archives, never deletes: the .ndjson and EVERY cursor pointing at it move together
into <archive root>/<stamp>/. Moving them together matters — an
archived bus whose offset was left behind would, if that slug were ever republished,
start life with a non-zero offset and silently swallow the first events.

Since v2.19 there are three kinds of cursor per slug: the legacy shared one at
bus-offsets/<project>/<slug>.offset, one per session at
bus-offsets/<session>/<project>/<slug>.offset (written by `inbox --unread`), and one
per session at hook-offsets/<session>/<project>/<slug>.offset (written by the
UserPromptSubmit hook). All of them are collected here.

Dry-run by default. Pass --apply to move anything.

  annotate prune-bus           # show what 30+ days quiet would archive
  annotate prune-bus --days 60 # more conservative
  annotate prune-bus --apply   # do it
"""
import argparse
import os
import shutil
import sys
import time

HOME = os.path.expanduser("~")
try:
    from .paths import BUS_ARCHIVE_ROOT as _ARCH
    from .paths import BUS_ROOT as _BUS
    from .paths import STATE_DIR as _STATE
except ImportError:  # run as a bare script: same defaults, spelled out
    _BUS = os.environ.get("ANNOTATE_BUS_ROOT") or os.path.join(HOME, ".claude", "annotate-bus")
    _STATE = (os.environ.get("ANNOTATE_STATE_DIR") or os.environ.get("ANNOTATE_STATE_ROOT")
              or os.path.join(HOME, ".claude", "annotate-state", "state"))
    _ARCH = os.environ.get("ANNOTATE_BUS_ARCHIVE_ROOT") or os.path.join(HOME, ".claude", "annotate-bus-archive")
BUS_ROOT = str(_BUS)
STATE_ROOT = str(_STATE)
OFFSET_ROOT = os.path.join(STATE_ROOT, "bus-offsets")
HOOK_OFFSET_ROOT = os.path.join(STATE_ROOT, "hook-offsets")
ARCHIVE_ROOT = str(_ARCH)


def _offsets_for(project, slug):
    """Every cursor file that points at <project>/<slug>, as (path, label).

    The label becomes the archived filename, so two sessions' cursors for the
    same slug cannot overwrite each other inside the archive.
    """
    found = []
    legacy = os.path.join(OFFSET_ROOT, project, slug + ".offset")
    if os.path.exists(legacy):
        found.append((legacy, slug + ".offset"))
    for root, kind in ((OFFSET_ROOT, "inbox"), (HOOK_OFFSET_ROOT, "hook")):
        try:
            sessions = sorted(os.listdir(root))
        except OSError:
            continue
        for session in sessions:
            path = os.path.join(root, session, project, slug + ".offset")
            if os.path.exists(path):
                found.append((path, f"{slug}.{kind}.{session}.offset"))
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(prog="annotate prune-bus")
    ap.add_argument("--days", type=int, default=30,
                    help="archive buses with no activity for this many days (default 30)")
    ap.add_argument("--apply", action="store_true", help="actually move files")
    args = ap.parse_args(argv)

    if not os.path.isdir(BUS_ROOT):
        print(f"no bus root at {BUS_ROOT}")
        return 0

    cutoff = time.time() - args.days * 86400
    stamp = time.strftime("%Y%m%dT%H%M%S")
    dest_root = os.path.join(ARCHIVE_ROOT, stamp)

    stale, keep = [], []
    for project in sorted(os.listdir(BUS_ROOT)):
        pdir = os.path.join(BUS_ROOT, project)
        if not os.path.isdir(pdir):
            continue
        for name in sorted(os.listdir(pdir)):
            if not name.endswith(".ndjson"):
                continue
            path = os.path.join(pdir, name)
            try:
                st = os.stat(path)
            except OSError:
                continue
            slug = name[: -len(".ndjson")]
            off = _offsets_for(project, slug)
            rec = (project, slug, path, off, st.st_mtime, st.st_size)
            (stale if st.st_mtime < cutoff else keep).append(rec)

    verb = "archiving" if args.apply else "would archive"
    print(f"annotate bus: {len(stale) + len(keep)} buses, "
          f"{verb} {len(stale)} quiet for {args.days}+ days, keeping {len(keep)}\n")

    moved = 0
    for project, slug, path, off, mt, size in stale:
        age = int((time.time() - mt) / 86400)
        note = f"   ({len(off)} cursor(s))" if off else "   (no cursor)"
        print(f"  {time.strftime('%Y-%m-%d', time.localtime(mt))}  {age:>3}d  "
              f"{size:>7}B  {project}/{slug}{note}")
        if not args.apply:
            continue
        d = os.path.join(dest_root, project)
        os.makedirs(d, exist_ok=True)
        shutil.move(path, os.path.join(d, os.path.basename(path)))
        for src, label in off:
            shutil.move(src, os.path.join(d, label))
        moved += 1

    print("\n  keeping:")
    for project, slug, path, off, mt, size in keep:
        age = int((time.time() - mt) / 86400)
        print(f"  {time.strftime('%Y-%m-%d', time.localtime(mt))}  {age:>3}d  "
              f"{size:>7}B  {project}/{slug}")

    if args.apply:
        print(f"\n  archived {moved} bus(es) -> {dest_root}")
        print(f"  restore with: mv <archive>/<project>/* {BUS_ROOT}/<project>/")
    else:
        print("\n  dry run — nothing moved. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
