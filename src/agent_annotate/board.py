"""The project's issue board link and its ready count, for the page header.

The count is `bd ready --json` without epics, as the board's Ready column
shows it, in the board's directory: `board.dir` when the agent set one, else
the path Bead Me Up Scotty lists for the board project
(GET <ANNOTATE_BOARD_API>/api/projects). `bd` can take seconds, so a request
never waits for it: it gets the cached count (None until the first one lands)
and a stale entry is refreshed on a background thread.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CACHE_SECONDS = 60
_cache: dict[tuple[str, str], dict] = {}
_refreshing: set[tuple[str, str]] = set()
_lock = threading.Lock()


def _board_api() -> str:
    return os.environ.get("ANNOTATE_BOARD_API", "http://127.0.0.1:3737").rstrip("/")


def _listed_dir(project: str) -> str | None:
    with urllib.request.urlopen(_board_api() + "/api/projects", timeout=5) as response:
        data = json.load(response)
    for entry in data.get("projects", []):
        if entry.get("id") == project and isinstance(entry.get("path"), str):
            return entry["path"]
    return None


def ready_count(board: dict) -> int | None:
    directory = board.get("dir") or _listed_dir(board["project"])
    executable = os.environ.get("ANNOTATE_BD") or shutil.which("bd")
    if not directory or not executable or not os.path.isdir(directory):
        return None
    result = subprocess.run(
        [executable, "-C", directory, "ready", "--json", "--brief", "-n", "0", "--exclude-type", "epic", "--readonly"],
        capture_output=True, text=True, timeout=60, cwd=Path.home(),
    )
    if result.returncode != 0:
        return None
    rows = json.loads(result.stdout)
    return len(rows) if isinstance(rows, list) else None


def _refresh(key: tuple[str, str], board: dict) -> None:
    try:
        ready = ready_count(board)
    except (OSError, ValueError, subprocess.SubprocessError):
        ready = None
    with _lock:
        _cache[key] = {"ready": ready, "at": time.monotonic(),
                       "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}
        _refreshing.discard(key)


def board_status(board: dict | None) -> dict:
    """{board: {url, project, label, prefix} | None, ready, checked_at}; never blocks on bd."""
    if not board:
        return {"board": None, "ready": None, "checked_at": None}
    key = (board["project"], board.get("dir") or "")
    with _lock:
        entry = _cache.get(key)
        if (not entry or time.monotonic() - entry["at"] > CACHE_SECONDS) and key not in _refreshing:
            _refreshing.add(key)
            threading.Thread(target=_refresh, args=(key, dict(board)), daemon=True).start()
    public = {k: board[k] for k in ("url", "project", "label", "prefix") if k in board}
    return {"board": public, "ready": entry["ready"] if entry else None,
            "checked_at": entry["checked_at"] if entry else None}
