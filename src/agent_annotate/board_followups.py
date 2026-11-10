"""Board judgement carried by page turns, independent of the page's record store."""

from __future__ import annotations

import json
import os
import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path


def directory(record: dict, project: str, slug: str) -> Path | None:
    root = os.environ.get("ANNOTATE_BOARD_FOLLOWUPS_ROOT")
    if root:
        return Path(root) / project / slug
    return Path(record["slug_dir"]) if record.get("slug_dir") else None


def open_items(record: dict, project: str, slug: str) -> list[dict]:
    dest = directory(record, project, slug)
    if dest is None:
        return []
    try:
        data = json.loads((dest / "board-followups.json").read_text())
        items = data["items"]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    settled = set()
    for source in [dest / "board-verdicts.ndjson", *map(Path, data.get("verdict_sources", []))]:
        try:
            with source.open() as stream:
                for line in stream:
                    try:
                        verdict = json.loads(line)
                        settled.add((verdict["key"], verdict["fingerprint"]))
                    except (ValueError, KeyError, TypeError):
                        continue
        except OSError:
            pass
    return [item for item in items if (item["key"], item["fingerprint"]) not in settled]


def clause(record: dict, project: str, slug: str) -> str:
    items = open_items(record, project, slug)
    if not items:
        return ""
    lines = [f"{item['line']} ({item['settle']})" for item in items[:3]]
    if len(items) > 3:
        lines.append(f"+{len(items) - 3} more: annotate board {shlex.quote(project + '/' + slug)}")
    return "; board follow-ups: " + "; ".join(lines)


def cmd_board(args) -> int:
    from .cli import _flock, _resolve_slug, _session_id
    found = _resolve_slug(args.slug, args.project)
    if not found:
        return 1
    project, slug, record = found
    dest = directory(record, project, slug)
    if dest is None:
        print("ERROR: page has no directory", file=sys.stderr)
        return 1
    if args.settle:
        key, verdict = args.settle
        if not verdict.strip():
            print("ERROR: verdict must not be empty", file=sys.stderr)
            return 1
        with _flock(dest / "board-followups.lock"):
            item = next((item for item in open_items(record, project, slug) if item["key"] == key), None)
            if item is None:
                print(f"ERROR: no open follow-up {key!r}", file=sys.stderr)
                return 1
            row = {"key": key, "fingerprint": item["fingerprint"], "verdict": verdict.strip(),
                   "session": _session_id(), "at": datetime.now(UTC).isoformat()}
            from .store import append_line
            append_line(dest / "board-verdicts.ndjson", json.dumps(row, ensure_ascii=False) + "\n", fsync=True)
        print(json.dumps(row, ensure_ascii=False) if args.json else f"settled {key}")
    else:
        items = open_items(record, project, slug)
        print(json.dumps(items, ensure_ascii=False) if args.json else
              "; ".join(f"{item['line']} ({item['settle']})" for item in items) or "board: no open follow-ups")
    return 0
