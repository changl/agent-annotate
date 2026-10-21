#!/usr/bin/env python3
"""Local-only SessionStart notice shared by Claude Code and Codex."""

from __future__ import annotations

import json
import select
import sys
from pathlib import Path

# The shell hook can run the packaged file without relying on `annotate` on PATH.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from agent_annotate import paths
from agent_annotate.page_names import page_name
from agent_annotate.urls import page_url
from agent_annotate.workspace import candidates, selected_page


def notice(cwd: Path) -> str | None:
    entries = []
    for state_file in paths.STATE_DIR.glob("*.json"):
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            entries.extend((state.get("project") or state_file.stem, slug, record)
                           for slug, record in state["slugs"].items() if isinstance(record, dict))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    selected = selected_page(candidates(cwd, entries=entries))
    if not selected:
        return None
    record = selected[2]
    url = page_url(record)
    if not url:
        return None
    waiting = waiting_count(Path(record["slug_dir"]))
    return f"annotate: this project's page {page_name(record)} {url} · {waiting} waiting on you"


def waiting_count(directory: Path) -> int:
    """Read without the server's normalizing/writing store loader."""
    from agent_annotate.categories import comment_category, comment_needs_reviewer
    from agent_annotate.copy_state import load_copy
    try:
        store = json.loads((directory / "comments.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        store = {}
    count = 0
    for comments in (store.get("anchors") or {}).values():
        for comment in comments:
            if not isinstance(comment, dict):
                continue
            if comment_category(comment) == "library" and (comment.get("target") or {}).get("copy_revision"):
                continue
            count += comment_needs_reviewer(comment)
    try:
        count += sum(block.get("status") == "needs_you" and
                     not any(revision.get("round_pending") for revision in block["revisions"])
                     for block in load_copy(directory)["blocks"])
    except (OSError, ValueError):
        pass
    return count


def main() -> int:
    """A visible line and the same context for the agent; never block a session."""
    try:
        payload = {}
        if not sys.stdin.isatty() and select.select([sys.stdin], [], [], 0.01)[0]:
            payload = json.load(sys.stdin)
        cwd = payload.get("cwd") if isinstance(payload, dict) else None
        line = notice(Path(cwd) if cwd else Path.cwd())
        if line:
            print(json.dumps({"systemMessage": line, "hookSpecificOutput": {
                "hookEventName": "SessionStart", "additionalContext": line}}, ensure_ascii=False))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
