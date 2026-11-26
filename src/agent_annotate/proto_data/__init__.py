"""Prototype UI routes, reached only for a page whose meta has "ui": "proto".

    /                         web/proto/shell.html
    /proto/data/<area>.json   proto_data.<area>.build(page_dir), or {} when no module exists yet
    /proto/<file>             a file under web/proto/
"""

from __future__ import annotations

import hashlib
import html
import importlib
import json
import os
import re
import sys
import threading
import time
import urllib.parse
from pathlib import Path

_AREA = re.compile(r"/proto/data/([a-z][a-z0-9_]{0,40})\.json")
_FIRST = re.compile(r"/proto/data/(reference|running|history|links)\.first\.json")
_FILE = re.compile(r"/proto/([A-Za-z0-9][A-Za-z0-9_.-]{0,80})")
_COPY_META = re.compile(r"/proto/p/([a-z0-9][a-z0-9-]{0,40})/current\.meta\.json")

MASK = "member@example.com"
# every address, company mailboxes included; not image names such as icon@2x.png.
# A leading escape (\n, é) is kept, so escaped text (JSON in HTML) stays valid.
_ADDR = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?!(?:png|jpe?g|gif|svg|webp)\b)[A-Za-z]{2,}\b"
EMAIL = re.compile(_ADDR)
EMAIL_ESCAPED = re.compile(r"(\\u[0-9A-Fa-f]{4}|\\.)?" + _ADDR)
# a review link credential, or any similar key carried in a link
KEY = re.compile(r"([#?&;](?:review|token|key|access_token|auth|signin|invite)=)[^\s&#;\"'<>)\]\\]+", re.I)
# a run of link text holding %XX or &entity; (member%40x.com, #%72eview=k): checked again once decoded.
# The lookbehind pins each run to its start, so long runs (data URIs) stay linear.
_ENCODED = re.compile(r"(?<![^\s\"'<>()\[\]\\])[^\s\"'<>()\[\]\\%&]*[%&][^\s\"'<>()\[\]\\]*")
_UNSAFE = re.compile(r"[\s\x00-\x1f\x7f\"'<>()\[\]\\%]")


def _plain(s: str, escaped: bool) -> str:
    s = EMAIL_ESCAPED.sub(lambda m: (m[1] or "") + MASK, s) if escaped else EMAIL.sub(MASK, s)
    return KEY.sub(r"\1redacted", s)


def _decoded(m: re.Match) -> str:
    run = m[0]
    text = run
    for _ in range(4):  # URLSearchParams decodes once; nested encodings are decoded too, to be safe
        nxt = html.unescape(urllib.parse.unquote(text))
        if nxt == text:
            break
        text = nxt
    if text == run or _plain(text, False) == text:
        return run  # nothing hidden in it: left byte for byte
    # re-encode what would end the run, so a Markdown link stays one link
    return _UNSAFE.sub(lambda c: "%%%02X" % ord(c[0]), _plain(text, False))


def scrub(s: str, escaped: bool = False) -> str:
    """No real address and no review key leaves the prototype page, in plain or encoded form.
    escaped: s is raw JSON/HTML source text."""
    return _plain(_ENCODED.sub(_decoded, s), escaped)


def _walk(x):
    if isinstance(x, str):
        return scrub(x)
    if isinstance(x, list):
        return [_walk(v) for v in x]
    if isinstance(x, dict):
        return {scrub(k): _walk(v) for k, v in x.items()}
    return x


_done: dict = {}  # the last few scrubbed bodies by hash: polls re-send the same big store
_done_lock = threading.Lock()


def scrub_json(text: str) -> str:
    """Scrub JSON by its string values and keys, so escapes stay intact; one value per line (ndjson) works too."""
    key = hashlib.sha256(text.encode("utf-8", "surrogateescape")).digest()
    if key in _done:  # a body already checked: polls and reloads re-send the same one (r12 fix12 perf)
        return _done[key] if _done[key] is not None else text
    if scrub(text, escaped=True) == text:
        out = None  # nothing to hide: the body goes out byte for byte
    else:
        out = _scrubbed(text)
    with _done_lock:
        if len(_done) >= 16:
            _done.pop(next(iter(_done)))
        _done[key] = out
    return text if out is None else out


_packed: dict = {}  # (sha256 of the body as given, given gzipped, want gzip, scrub) -> the reply bytes and whether gzipped
_packed_lock = threading.Lock()
_PACKED_BYTES = 64 << 20


def packed(raw: bytes, raw_gz: bool, want_gz: bool, scrubbed: bool = True) -> tuple[bytes, bool]:
    """A reply as sent: masked (JSON) and gzipped once per body, not on every request. On a loaded host each request's CPU
    holds the GIL every other request waits on, the version's included: 1 MB running.json and the scripts were gzipped,
    and the meta un-gzipped and gzipped again, per read (r12 fix13 perf)."""
    key = (hashlib.sha256(raw).digest(), raw_gz, want_gz, scrubbed)
    if (hit := _packed.get(key)) is not None:
        return hit
    import gzip
    body = gzip.decompress(raw) if raw_gz else raw
    if scrubbed:
        body = scrub_json(body.decode("utf-8", "surrogateescape")).encode("utf-8", "surrogateescape")
    out = (body, False)
    if want_gz and body:
        gz = gzip.compress(body, compresslevel=6, mtime=0)
        if len(gz) < len(body):
            out = (gz, True)
    with _packed_lock:
        _packed[key] = out
        while sum(len(v[0]) for v in _packed.values()) > _PACKED_BYTES and len(_packed) > 1:
            _packed.pop(next(iter(_packed)))  # the oldest first
    return out


def _scrubbed(text: str) -> str:
    try:
        out = json.dumps(_walk(json.loads(text)), ensure_ascii=False, separators=(",", ":"))
    except ValueError:
        try:
            out = "\n".join(json.dumps(_walk(json.loads(line)), ensure_ascii=False) if line.strip() else line
                            for line in text.split("\n"))
        except ValueError:
            out = scrub(text, escaped=True)
    return out


def build(area: str, page_dir) -> dict:
    try:
        module = importlib.import_module(f"{__name__}.{area}")
    except ModuleNotFoundError as exc:
        if exc.name != f"{__name__}.{area}":
            raise  # a real import error inside an area module must show
        return {}
    return module.build(page_dir)


_ready: dict = {}  # (area, page dir) -> (its stamp, the JSON bytes): built when the page changed, not on every read


_KEEP = object()


def prepared(area: str, page_dir, viewer=_KEEP) -> bytes:
    """An area's JSON. An area with stamp(page_dir) is built again only when the stamp changes (r12 fix12 perf).
    `viewer`: the reader's hash (published.viewer), passed in because the pooled worker is another process; whose release
    notes are his own is built for it, and cached per reader (r12 fix28)."""
    from . import published
    if viewer is not _KEEP:  # this thread's reader, and the rebuild it starts behind the answer (published.behind): r12 fix29
        was, published._here.h = getattr(published._here, "h", _KEEP), viewer
        try:
            return prepared(area, page_dir)
        finally:
            if was is _KEEP:
                del published._here.h  # the server's own state stays the last reviewer's (other paths read it)
            else:
                published._here.h = was
    try:
        stamp = getattr(importlib.import_module(f"{__name__}.{area}"), "stamp", None)
    except ModuleNotFoundError:
        stamp = None
    key, now = (area, str(page_dir), published.reader()), stamp(page_dir) if stamp else None
    hit = _ready.get(key)
    if now is not None and hit and hit[0] == now:
        return hit[1]
    body = json.dumps(build(area, page_dir), ensure_ascii=False).encode()
    if now is not None:
        _ready[key] = (now, body)
    return body


# Areas whose builds and minute-old rebuilds take 0.3-1 s of CPU (Copy library, Pages & links, History): built in one worker
# process with its own warm caches. In this server they held the GIL that the version and counts reads wait on, and on a
# loaded host that turned a second of CPU into 5-25 s for every read in flight (r12 fix13 perf).
POOLED = {"reference", "links", "history"}
_pool = None
_pool_lock = threading.Lock()


def _orphan_guard(parent: int) -> None:
    def watch():
        while os.getppid() == parent:
            time.sleep(5)
        os._exit(0)  # the server is gone: so is its worker
    threading.Thread(target=watch, daemon=True).start()


def _pooled(area: str, page_dir, viewer=_KEEP) -> bytes:
    global _pool
    from concurrent.futures import ProcessPoolExecutor
    from concurrent.futures.process import BrokenProcessPool
    with _pool_lock:
        if _pool is None:
            import multiprocessing
            _pool = ProcessPoolExecutor(1, mp_context=multiprocessing.get_context("spawn"),
                                        initializer=_orphan_guard, initargs=(os.getpid(),))
        pool = _pool
    try:
        return pool.submit(prepared, area, str(page_dir), viewer).result(timeout=60)
    except BrokenProcessPool:  # the worker died: start another next time; this read is built here
        with _pool_lock:
            if _pool is pool:
                _pool = None
        return prepared(area, page_dir, viewer)


_heads: dict = {}  # meta path -> (its stamp, its current version)


def head(handler) -> dict:
    """What the frame's first paint needs of current.meta.json: the page's name, as the meta route injects it, and its current
    version. The meta grows with every version (270 KB at 1,064); the frame reads it whole after the tab on screen has drawn (r13 speed)."""
    p = handler._meta_path()
    try:
        st = p.stat()
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    hit = _heads.get(str(p))
    if not hit or hit[0] != key:
        try:
            current = json.loads(p.read_text(encoding="utf-8")).get("current")
        except (OSError, ValueError, AttributeError):
            current = None
        hit = _heads[str(p)] = (key, current)
    try:
        name = handler._project_payload()["name"]
    except (OSError, ValueError, KeyError):
        from ..page_names import page_name
        name = page_name(handler.artifact_dir)
    return {"name": name, "current": hit[1]} if hit[1] else {"name": name}


def serve(handler, route_path: str):
    from .. import sync_server

    web = (handler.skill_dir or sync_server.WEB_DIR) / "proto"
    if route_path in ("", "/"):
        try:
            html = (web / "shell.html").read_bytes()
        except OSError:
            return handler._respond(500, b'{"error":"proto shell.html missing"}')
        gz = sync_server._accepts_gzip(handler.headers.get("Accept-Encoding", ""))
        return handler._respond(200, b"", "text/html; charset=utf-8", cache_control=sync_server._NO_STORE,
                                representation=packed(html, False, gz, scrubbed=False))
    if route_path.startswith("/proto/p/"):  # a read-only copy of another project's page (frame.serve_other)
        from .frame import serve_other
        if m := _COPY_META.fullmatch(route_path):  # a copy follows its real page: a newer version starts copying behind this read
            from .copies import fresh
            fresh(Path(handler.artifact_dir).parent / f"proto-{m[1]}")
        return serve_other(handler, route_path)
    if route_path.startswith("/proto/doc/"):  # a picture a FastLane Drive Markdown document shows (reference.doc_pictures)
        from .links import _json, _scope
        from .reference import doc_picture
        fld = _scope(_json(Path(handler.artifact_dir) / "current.meta.json"))[2]
        pic = fld and doc_picture(urllib.parse.unquote(route_path[len("/proto/doc/"):]))
        if not pic:
            return handler._respond(404, b"Not found")
        return handler._respond(200, pic.read_bytes(), sync_server._mime(pic.suffix.lower()), cache_control="private, max-age=300")
    if route_path.startswith("/proto/kept/"):  # a picture a kept document or Reference's policies page shows (reference._kept_src)
        from .links import _json, _kept_dir, kept_picture
        doc, _, rel = route_path[len("/proto/kept/"):].partition("/")
        pic = kept_picture(_kept_dir(doc, _json(Path(handler.artifact_dir) / "current.meta.json")), urllib.parse.unquote(rel))
        if not pic:
            return handler._respond(404, b"Not found")
        return handler._respond(200, pic.read_bytes(), sync_server._mime(pic.suffix.lower()), cache_control="private, max-age=300")
    if route_path == "/proto/data/head.json":
        return handler._respond(200, json.dumps(head(handler)).encode(), "application/json", cache_control="no-store")
    part = _FIRST.fullmatch(route_path)  # a heavy tab's first screen, cut from the same read (proto_data/first.py, r13 speed)
    if match := part or _AREA.fullmatch(route_path):
        t0 = time.perf_counter()
        try:
            who = handler._identity()  # first: this read's reader (his hash), before the build decides whose release notes are his
            body = (_pooled if match[1] in POOLED else prepared)(match[1], handler.artifact_dir, getattr(handler, "proto_viewer", None))
            from .questions import own  # his own notes, for Edit and Remove (r12 audit19)
            body = own(body, handler._reviewer_authors(who["email"] or "anonymous"))
            if part:
                from .first import cut
                body = cut(match[1], body)
        except Exception as exc:  # an area's bug must not take the page down
            return handler._respond(500, json.dumps({"error": f"{type(exc).__name__}: {exc}"}).encode())
        # the server's own time, so a slow reading on a busy host can be told from slow code (r12 fix12 perf)
        ms = (time.perf_counter() - t0) * 1000
        if ms >= 250:  # the access log is off; a slow build is worth a line
            print(f"{time.strftime('%H:%M:%S')} proto {match[1]}.json took {ms:.0f} ms (load {os.getloadavg()[0]:.0f})", file=sys.stderr, flush=True)
        return handler._respond(200, body, "application/json", cache_control="no-store",
                                extra_headers={"Server-Timing": f"build;dur={ms:.1f}"})
    match = _FILE.fullmatch(route_path)
    if not match or match[1].startswith(".") or ".." in match[1] or not (web / match[1]).is_file():
        return handler._respond(404, b"Not found")
    target = web / match[1]
    mime = sync_server._mime(target.suffix)
    gz = mime.split(";")[0] in ("text/html", "text/css", "application/javascript", "image/svg+xml") and \
        sync_server._accepts_gzip(handler.headers.get("Accept-Encoding", ""))
    # gzipped once per file content, not on each of the dozen reads a reload makes (r12 fix13 perf)
    return handler._respond(200, b"", mime, representation=packed(target.read_bytes(), False, gz, scrubbed=False))
