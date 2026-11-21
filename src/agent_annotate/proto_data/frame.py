"""The prototype frame's data: this page's waiting count and every project's read-only home counts.

Projects are the review folders under ANNOTATE_PROTO_PROJECTS_ROOT (default ~/projects/*/reviews/*), read only.
Prototype pages beside this one (the FastLane Drive copy, and read-only copies of other projects' pages made by
copy_other.py as reviews/proto-<project>) stand in for their project's row, and serve_other() serves them.
"""
from __future__ import annotations

import calendar
import json
import os
import re
import threading
import time
import urllib.parse
from datetime import datetime
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


def _registry() -> Path:
    return Path(os.environ.get("ANNOTATE_PROTO_REGISTRY") or Path.home() / ".claude/annotate-state/state")


_url_cache: dict = {}  # registry dir -> (when read, the addresses)


def _urls() -> dict[str, str]:
    """Each live page's address by its folder, read only from the live registry; never a key (fragment and query cut).
    Read at most once a minute: a page's address hardly ever moves (r12 fix12 perf)."""
    key, hit = str(_registry()), _url_cache.get(str(_registry()))
    if not hit or time.time() - hit[0] >= TTL:
        hit = _url_cache[key] = (time.time(), _urls_read())
    return hit[1]


def _urls_read() -> dict[str, str]:
    out = {}
    for f in _registry().glob("*.json"):
        try:
            slugs = json.loads(f.read_text(encoding="utf-8")).get("slugs") or {}
        except (OSError, ValueError, AttributeError):
            continue
        for r in slugs.values() if isinstance(slugs, dict) else ():
            url = isinstance(r, dict) and (r.get("public_url") or r.get("url"))
            if isinstance(url, str) and url.startswith("https://") and r.get("slug_dir"):
                out[str(r["slug_dir"])] = url.split("#")[0].split("?")[0]
    return out


_metas: dict = {}  # meta file -> (its stamp, the fields read here): FastLane Drive's meta is 3.5 MB, read on every frame read
KEEP = ("ui", "proto_copy_of", "proto_source", "name", "current", "owner")


def _meta(d: Path) -> dict:
    """The page meta's fields this module reads, and its history's times; parsed again only when the file changes. Read only."""
    f = d / "current.meta.json"
    try:
        st = f.stat()
        hit = _metas.get(str(f))
        if hit and hit[0] == (st.st_mtime_ns, st.st_size):
            return hit[1]
        m = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(m, dict):
        return {}
    slim = {k: m[k] for k in KEEP if k in m}
    slim["history"] = [{"ts": h.get("ts")} for h in m.get("history") or [] if isinstance(h, dict)]
    _metas[str(f)] = ((st.st_mtime_ns, st.st_size), slim)
    return slim


def _copies(page_dir: Path) -> list[dict]:
    """The prototype pages beside this one: the writable FastLane Drive copy (href "") and read-only copies (proto/p/<key>/)."""
    out = []
    for d in sorted(page_dir.parent.iterdir()):
        m = _meta(d)
        if m.get("ui") != "proto":
            continue
        of = m.get("proto_copy_of")
        if of and d.name != f"proto-{of}":
            continue  # serve_other finds a copy by this name only
        try:
            board = json.loads((d / "project.json").read_text(encoding="utf-8")).get("board") or {}
        except (OSError, ValueError, AttributeError):
            board = {}
        out.append({"dir": d, "of": of, "name": m.get("name") or d.name, "this": d.resolve() == page_dir.resolve(), "src": m.get("proto_source"),
                    "code": proj_of(of or board.get("project") or m.get("name") or ""), "href": f"proto/p/{of}/" if of else ""})
    return out


def _day(ts: float, now: float) -> int | None:
    age = int((now - ts) // 86400)
    return DAYS - 1 - age if 0 <= age < DAYS else None


def _ts(s) -> float | None:
    try:
        s = str(s)[:19]
        if len(s) != 19 or s[10] != "T":
            raise ValueError(s)
        return calendar.timegm(datetime.fromisoformat(s).timetuple())  # strptime took 0.45 s over 2,000 stamps
    except ValueError:
        return None


_rows: dict = {}  # page dir -> (its files' stamps, its facts): the frame read waits on this at every reload (r12 fix10 slowread)


def _stamps(d: Path) -> tuple:
    out = []
    for n in ("current.meta.json", "rounds.ndjson", "comments.json"):
        try:
            st = (d / n).stat()
            out.append((st.st_mtime_ns, st.st_size))
        except OSError:
            out.append(None)
    return tuple(out)


def _page(d: Path, now: float) -> dict:
    """A page's Home row. Its files are read again only once its meta, Sends or notes change; the day columns move with the
    clock, so they are counted from the kept times on every read (r12 fix12 perf)."""
    stamps, hit = _stamps(d), _rows.get(str(d))
    if not hit or hit[0] != stamps:
        hit = _rows[str(d)] = (stamps, _page_read(d))
    vts, ats, waiting = hit[1]
    vday, aday = [0] * DAYS, [0] * DAYS
    for ts, days in ((vts, vday), (ats, aday)):
        for t in ts:
            if (i := _day(t, now)) is not None:
                days[i] += 1
    return {"waiting": waiting, "vday": vday, "aday": aday, "last": max(vts, default=0.0), "owner": _owner(d)}


def _page_read(d: Path) -> tuple:
    """(when each version was published, when each Send went, questions waiting)."""
    # the meta's history, since a copied page's files all carry the copy's time
    vts = [t for h in _meta(d).get("history") or [] if isinstance(h, dict) and (t := _ts(h.get("ts")))]
    vts = vts or [v.stat().st_mtime for v in (d / "versions").glob("*.html")]
    ats = []
    rounds = d / "rounds.ndjson"
    if rounds.is_file():
        for line in rounds.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                ts = _ts(json.loads(line)["ts"])
            except (ValueError, KeyError, TypeError):
                continue
            if ts:
                ats.append(ts)
    try:
        waiting = waiting_count(d)
    except Exception:  # a page another agent is mid-write on must not break Home
        waiting = 0
    return vts, ats, waiting


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
    o = _meta(d).get("owner")
    if not isinstance(o, dict) or not (o.get("owner_agent") or o.get("owner_session")):
        return None
    t = o.get("target") if isinstance(o.get("target"), dict) else {}
    return {"agent": o.get("owner_agent") or t.get("agent") or "", "at": o.get("claimed_at") or "", "alive": _alive(t.get("pid"))}


def _newest(a: dict | None, b: dict | None) -> dict | None:
    return b if a is None or (b is not None and (b.get("at") or "") > (a.get("at") or "")) else a


def _projects(now: float) -> list[dict]:
    out: dict[str, dict] = {}
    urls, newest = _urls(), {}
    for d in sorted(_root().glob("*/reviews/*")):
        if not (d / "current.meta.json").is_file():
            continue
        key = d.parent.parent.name
        p = out.setdefault(key, {"key": key, "name": NAMES.get(key, key.replace("-", " ").capitalize()), "code": proj_of(key),
                                 "pages": 0, "waiting": 0, "vday": [0] * DAYS, "aday": [0] * DAYS, "last": 0.0, "owner": None, "url": None})
        one = _page(d, now)
        if str(d) in urls and one["last"] >= newest.get(key, -1.0):  # its newest page with an address: where its tabs link
            p["url"], newest[key] = urls[str(d)], one["last"]
        p["owner"] = _newest(p["owner"], one["owner"])
        p["pages"] += 1
        p["waiting"] += one["waiting"]
        p["vday"] = [a + b for a, b in zip(p["vday"], one["vday"])]
        p["aday"] = [a + b for a, b in zip(p["aday"], one["aday"])]
        p["last"] = max(p["last"], one["last"])
    return list(out.values())


_busy: set = set()
_busy_lock = threading.Lock()


def _behind(root: str) -> None:
    """One background read of every project's pages at a time; the next frame read shows it."""
    with _busy_lock:
        if root in _busy:
            return
        _busy.add(root)

    def run():
        try:
            now = time.time()
            _cache[root] = (now, _projects(now))
        finally:
            with _busy_lock:
                _busy.discard(root)
    threading.Thread(target=run, daemon=True).start()


def _ago(last: float, now: float) -> float | None:
    return round((now - last) / 3600, 1) if last else None


def build(page_dir: Path) -> dict:
    now = time.time()
    page_dir = Path(page_dir)
    meta = _meta(page_dir)
    try:
        board = json.loads((page_dir / "project.json").read_text(encoding="utf-8")).get("board") or {}
    except (OSError, ValueError):
        board = {}
    this = _page(page_dir, now)
    # code: the project tag Running's workers carry (running.proj_of), so Home and the top bar can match them
    this.update(key="this", name=meta.get("name") or page_dir.name, pages=1, this=True,
                code=proj_of(meta.get("proto_copy_of") or board.get("project") or meta.get("name") or ""), href="",
                src=meta.get("proto_source"))
    hit = _cache.get(str(_root()))
    if not hit:
        hit = _cache[str(_root())] = (now, _projects(now))
    elif now - hit[0] > TTL:  # the ~40 other pages are read again behind this answer: it took seconds on a busy host (r12 fix12 perf)
        _behind(str(_root()))
    real = [dict(p) for p in hit[1]]
    # one row a project: a prototype page stands in for its project's own row (#2, #11)
    rows = [this]
    for c in _copies(page_dir):
        if c["this"]:
            continue
        row = _page(c["dir"], now)
        row.update(key=c["of"] or "fld-proto", name=c["name"], pages=1, code=c["code"], href=c["href"], src=c["src"])
        rows.append(row)
    urls = _urls()
    for row in rows:
        mine = next((p for p in real if p["code"] == row["code"]), None)
        if mine:
            row["owner"] = row["owner"] or mine["owner"]  # a copy has no owner of its own: the project's session stands in
        row["url"] = urls.get(row.pop("src", None) or "") or (mine or {}).get("url")
    took = {r["code"] for r in rows}
    projects = rows + [p for p in real if p["code"] == "other" or p["code"] not in took]
    for p in projects:
        p["lastAgoH"] = _ago(p.pop("last"), now)
    return {"days": DAYS, "asOf": time.strftime("%-d %b %H:%M", time.localtime(hit[0])), "copyOf": meta.get("proto_copy_of"),
            "waiting": this["waiting"], "projects": projects, "lastSend": _last_send(page_dir)}


_OTHER = re.compile(r"/proto/p/([a-z0-9][a-z0-9-]{0,40})(/.*)?")
_bound: dict = {}
_bound_lock = threading.Lock()


def serve_other(handler, route_path: str):
    """GET /proto/p/<key>/... : the read-only copy reviews/proto-<key> beside this page, on this server.
    Only GETs reach here; every write route matches /api/... at the root, so writes to a copy 404."""
    m = _OTHER.fullmatch(route_path)
    copy = Path(handler.artifact_dir).parent / f"proto-{m[1]}" if m else None
    meta = _meta(copy) if copy else {}
    if not m or meta.get("ui") != "proto" or meta.get("proto_copy_of") != m[1]:
        return handler._respond(404, b"Not found")
    if not m[2]:
        q = urllib.parse.urlparse(handler.path).query
        return handler._respond(308, b"", extra_headers={"Location": urllib.parse.urlparse(handler.path).path + "/" + (f"?{q}" if q else "")})
    base = type(handler)
    with _bound_lock:
        cls = _bound.get((base, m[1]))
        if cls is None:
            # its own folder, bus name and caches: nothing of this page (its store, last Send) shows on the copy
            cls = _bound[(base, m[1])] = type(f"Copy_{m[1]}", (base,), {
                "_published_proxy_origins": lambda self: self._page_origins,
                "artifact_dir": copy.resolve(), "slug": copy.name, "_store_responses": {}, "_store_snapshot": None,
                "_meta_snapshot": None, "_meta_responses": {}, "_meta_response_lock": threading.Lock(),
                "_history_responses": {}, "_history_response_lock": threading.Lock(), "_history_bus_cache": {}})
    path = handler.path
    # the copy has no publish record of its own: it is trusted on this page's published origins
    handler._page_origins = handler._published_proxy_origins()
    handler.__class__, handler.path = cls, path.replace(f"/proto/p/{m[1]}", "", 1)
    try:
        return handler.do_GET()
    finally:
        handler.__class__, handler.path = base, path


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
