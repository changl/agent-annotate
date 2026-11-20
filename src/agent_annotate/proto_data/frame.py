"""The prototype frame's data: this page's waiting count and every project's read-only home counts.

Projects are the review folders under ANNOTATE_PROTO_PROJECTS_ROOT (default ~/projects/*/reviews/*), read only.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from agent_annotate.hooks.session_start import waiting_count

DAYS = 14
TTL = 60  # seconds; Home reads ~40 pages, so one read a minute at most
NAMES = {"fastlane-drive": "FastLane Drive", "agent-annotate": "Agent Annotate", "claude-config": "Claude config",
         "multimac-orch": "Multi-Mac orchestration", "windmill": "Windmill plans", "rebex": "Rebex", "leadory": "Leadory",
         "artifacts": "Artifacts"}
_cache: dict = {}


def _root() -> Path:
    return Path(os.environ.get("ANNOTATE_PROTO_PROJECTS_ROOT") or Path.home() / "projects")


def _day(ts: float, now: float) -> int | None:
    age = int((now - ts) // 86400)
    return DAYS - 1 - age if 0 <= age < DAYS else None


def _page(d: Path, now: float) -> dict:
    vday, aday, last = [0] * DAYS, [0] * DAYS, 0.0
    for v in (d / "versions").glob("*.html"):
        m = v.stat().st_mtime
        last = max(last, m)
        if (i := _day(m, now)) is not None:
            vday[i] += 1
    rounds = d / "rounds.ndjson"
    if rounds.is_file():
        for line in rounds.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                ts = time.mktime(time.strptime(json.loads(line)["ts"][:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
            except (ValueError, KeyError, TypeError):
                continue
            if (i := _day(ts, now)) is not None:
                aday[i] += 1
    try:
        waiting = waiting_count(d)
    except Exception:  # a page another agent is mid-write on must not break Home
        waiting = 0
    return {"waiting": waiting, "vday": vday, "aday": aday, "last": last}


def _projects(now: float) -> list[dict]:
    out: dict[str, dict] = {}
    for d in sorted(_root().glob("*/reviews/*")):
        if not (d / "current.meta.json").is_file():
            continue
        key = d.parent.parent.name
        p = out.setdefault(key, {"key": key, "name": NAMES.get(key, key.replace("-", " ").capitalize()), "pages": 0,
                                 "waiting": 0, "vday": [0] * DAYS, "aday": [0] * DAYS, "last": 0.0})
        one = _page(d, now)
        p["pages"] += 1
        p["waiting"] += one["waiting"]
        p["vday"] = [a + b for a, b in zip(p["vday"], one["vday"])]
        p["aday"] = [a + b for a, b in zip(p["aday"], one["aday"])]
        p["last"] = max(p["last"], one["last"])
    return list(out.values())


def _ago(last: float, now: float) -> float | None:
    return round((now - last) / 3600, 1) if last else None


def build(page_dir: Path) -> dict:
    now = time.time()
    page_dir = Path(page_dir)
    meta = json.loads((page_dir / "current.meta.json").read_text(encoding="utf-8"))
    this = _page(page_dir, now)
    this.update(key="this", name=meta.get("name") or page_dir.name, pages=1, this=True)
    hit = _cache.get(str(_root()))
    if not hit or now - hit[0] > TTL:
        hit = _cache[str(_root())] = (now, _projects(now))
    projects = [this] + [dict(p) for p in hit[1]]
    for p in projects:
        p["lastAgoH"] = _ago(p.pop("last"), now)
    return {"days": DAYS, "asOf": time.strftime("%-d %b %H:%M", time.localtime(hit[0])),
            "waiting": this["waiting"], "projects": projects}
