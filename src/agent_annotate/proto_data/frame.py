"""The prototype frame's data: this page's waiting count and every project's read-only home counts.

Projects are the review folders under ANNOTATE_PROTO_PROJECTS_ROOT (default ~/projects/*/reviews/*), read only.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .questions import waiting as waiting_count  # one count everywhere: the Questions tab's waiting
from .running import proj_of  # one project tag everywhere: the one Running's workers carry

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
    return {"waiting": waiting, "vday": vday, "aday": aday, "last": last, "owner": _owner(d)}


def _alive(pid) -> bool | None:
    # shortcut: a live pid only; a reused pid reads as alive. Compare process_start if that ever misleads.
    if not isinstance(pid, int) or pid <= 0:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True  # exists, owned by someone else
    return True


def _owner(d: Path) -> dict | None:
    """The agent session that owns the page: what it is, when it claimed the page, and whether it runs now."""
    try:
        o = json.loads((d / "current.meta.json").read_text(encoding="utf-8")).get("owner")
    except (OSError, ValueError):
        return None
    if not isinstance(o, dict) or not (o.get("owner_agent") or o.get("owner_session")):
        return None
    t = o.get("target") if isinstance(o.get("target"), dict) else {}
    return {"agent": o.get("owner_agent") or t.get("agent") or "", "at": o.get("claimed_at") or "", "alive": _alive(t.get("pid"))}


def _newest(a: dict | None, b: dict | None) -> dict | None:
    return b if a is None or (b is not None and (b.get("at") or "") > (a.get("at") or "")) else a


def _projects(now: float) -> list[dict]:
    out: dict[str, dict] = {}
    for d in sorted(_root().glob("*/reviews/*")):
        if not (d / "current.meta.json").is_file():
            continue
        key = d.parent.parent.name
        p = out.setdefault(key, {"key": key, "name": NAMES.get(key, key.replace("-", " ").capitalize()), "code": proj_of(key),
                                 "pages": 0, "waiting": 0, "vday": [0] * DAYS, "aday": [0] * DAYS, "last": 0.0, "owner": None})
        one = _page(d, now)
        p["owner"] = _newest(p["owner"], one["owner"])
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
    try:
        board = json.loads((page_dir / "project.json").read_text(encoding="utf-8")).get("board") or {}
    except (OSError, ValueError):
        board = {}
    this = _page(page_dir, now)
    # code: the project tag Running's workers carry (running.proj_of), so Home and the top bar can match them
    this.update(key="this", name=meta.get("name") or page_dir.name, pages=1, this=True,
                code=proj_of(board.get("project") or meta.get("name") or ""))
    hit = _cache.get(str(_root()))
    if not hit or now - hit[0] > TTL:
        hit = _cache[str(_root())] = (now, _projects(now))
    projects = [this] + [dict(p) for p in hit[1]]
    if not this["owner"]:  # a copy has no owner of its own: the project's own session stands in
        this["owner"] = next((p["owner"] for p in projects[1:] if p["code"] == this["code"] and p["owner"]), None)
    for p in projects:
        p["lastAgoH"] = _ago(p.pop("last"), now)
    return {"days": DAYS, "asOf": time.strftime("%-d %b %H:%M", time.localtime(hit[0])),
            "waiting": this["waiting"], "projects": projects, "lastSend": _last_send(page_dir)}


def _last_send(d: Path) -> dict | None:
    """The newest Send on this page, for the header: when, and how far it got."""
    try:
        lines = (d / "rounds.ndjson").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("ts"):
            return {"ts": r["ts"], "delivery": r.get("delivery") or "", "n": len(r.get("answers") or [])}
    return None
