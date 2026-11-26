"""The pooled areas' (Reference, Pages & links, History) last builds, kept on disk, so the first open after a restart or a copy
never waits on a build: Reference's took 17-56 s cold on a loaded host (r13 speed).

- A server starts building every page's pooled areas in the background (warm), one at a time, for each reader it kept a build for;
  so does a copy swapped in.
- A read starts its area's build (or joins the one running) and gets the last build at once, from this server or kept from the
  last: the slice always, the whole read when the page's own files and its publications' stores are still the ones it was built
  from (a new note waits for its build, warm and quick). Only a page's first build ever, with nothing kept, is waited for.
- The pooled worker keeps each build it makes (made), masked as it is sent: no address or review key in the file.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from concurrent.futures import Future
from pathlib import Path

# the page's own files a pooled build reads (reference._own, links._stamps, history.build), plus its database when it has one
OWN = ("current.meta.json", "comments.json", "project.json", "copy.json", "rounds.ndjson", "seen.json", "page.db", "page.db-wal")
_sums: dict = {}  # (file, size, mtime) -> its digest: a copy's fresh clone has new times but often the same bytes
_runs: dict = {}  # (area, page dir, reader) -> its build in flight
_last: dict = {}  # the same key -> (source, body) of the newest build this server got
_kept: dict = {}  # the same key -> its record on disk, read once
_saved: dict = {}  # in the worker: the same key -> (source, bytes) last kept
_lock = threading.Lock()


def _sum(f: Path) -> str | None:
    try:
        st = f.stat()
    except OSError:
        return None
    k = (str(f), st.st_size, st.st_mtime_ns)
    if k not in _sums:
        h = hashlib.blake2b(digest_size=16)
        try:
            with open(f, "rb") as fh:
                for b in iter(lambda: fh.read(1 << 20), b""):
                    h.update(b)
        except OSError:
            return None
        if len(_sums) > 4096:
            _sums.clear()
        _sums[k] = h.hexdigest()
    return _sums[k]


def _pub(folders) -> list:
    out = []
    for folder in folders:
        try:
            s = (Path(folder) / "comments.json").stat()
            out.append([str(folder), s.st_size, s.st_mtime_ns])
        except OSError:
            out.append([str(folder)])
    return out


def source(page_dir, folders=None) -> dict:
    """What a build of this page reads: its own files by content, and its publications' note stores (published.signature) by
    stat. folders: the stores to look at (a kept record's); None reads them from the page."""
    d = Path(page_dir)
    if folders is None:
        from .published import signature
        folders = [s[0] for s in signature(d)[1:]]
    own = [[str(f.relative_to(d)), s] for f in [d / n for n in OWN] + sorted(d.glob("plans/*/meta.json")) if (s := _sum(f))]
    return {"own": own, "pub": _pub(folders)}


def _file(key) -> Path | None:
    """ROOT/built/<page>-<its path's digest>/<area>-<reader's digest>.json, beside ROOT/reviews/ and outside the page: a copy
    swapped in whole keeps it. Only under the prototype's root (published.guard); elsewhere nothing is kept."""
    from .published import guard
    area, d, viewer = key
    p = Path(d)
    dig = lambda s: hashlib.blake2b(s.encode(), digest_size=5).hexdigest()
    try:
        return guard(p.parent.parent / "built" / f"{p.name}-{dig(str(p.resolve()))}" / f"{area}-{dig(viewer or '')}.json")
    except PermissionError:
        return None


def _load(key) -> dict | None:
    if key not in _kept:
        f, rec = _file(key), None
        try:
            rec = json.loads(f.read_text(encoding="utf-8")) if f and f.is_file() else None
        except (OSError, ValueError):
            rec = None
        ok = isinstance(rec, dict) and rec.get("viewer") == key[2] and isinstance(rec.get("body"), str) and isinstance(rec.get("src"), dict)
        _kept[key] = rec if ok else None
    return _kept[key]


def _save(key, src: dict, body: bytes) -> None:
    from . import _walk, scrub
    f = _file(key)
    if f is None:
        return
    text = body.decode("utf-8", "surrogateescape")
    if scrub(text, escaped=True) != text:  # dumped as prepared dumps it, so questions.own still finds his notes
        text = json.dumps(_walk(json.loads(text)), ensure_ascii=False)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"viewer": key[2], "src": src, "body": text}, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, f)


def made(area: str, page_dir: str, viewer) -> bytes:
    """In the pooled worker: proto_data.prepared, kept on disk when it or its source changed. The source is read first, so a
    file changed during the build makes the kept one older, never newer."""
    from . import prepared
    key = (area, str(page_dir), viewer)
    src = source(page_dir) if _file(key) else None
    body = prepared(area, page_dir, viewer)
    if src is not None and _saved.get(key) != (src, body):
        try:
            _save(key, src, body)
            _saved[key] = (src, body)
        except (OSError, ValueError) as exc:  # nothing kept: the next restart builds again, as before
            print(f"proto {area} build not kept: {exc}", file=sys.stderr, flush=True)
    return body


def _known(key) -> tuple | None:
    """(source, body): the newest build this server got, else the one kept on disk."""
    if key not in _last and (rec := _load(key)) is not None:
        _last.setdefault(key, (rec["src"], rec["body"].encode()))
    return _last.get(key)


def _folders(last) -> list | None:
    return [p[0] for p in last[0].get("pub") or []] if last else None


def _start(key, build) -> Future:
    """One build per key in flight; its source is read before it starts, so a file changed during it makes it older, never newer."""
    with _lock:
        if (f := _runs.get(key)) is not None:
            return f
        f = _runs[key] = Future()

    def run():
        try:
            src = source(key[1], _folders(_known(key)))
            body = build(*key)
            _last[key] = (src, body)
            f.set_result(body)
        except BaseException as exc:
            f.set_exception(exc)
        finally:
            with _lock:
                _runs.pop(key, None)
    threading.Thread(target=run, daemon=True).start()
    return f


def get(area: str, page_dir, viewer, whole: bool, build) -> bytes:
    """An area's body for one read: its build starts (or the one running is joined), and the last build goes at once when it
    may: for the slice, any; for the whole read, one built from the page as it is now (a new note waits for its build)."""
    key = (area, str(page_dir), viewer)
    f = _start(key, build)
    last = _known(key)
    if last is not None and not f.done() and (not whole or source(page_dir, _folders(last)) == last[0]):
        return last[1]
    return f.result(timeout=60)


def _viewers(page_dir: Path, area: str) -> list:
    f = _file((area, str(page_dir), None))
    out = []
    for p in sorted(f.parent.glob(f"{area}-*.json")) if f else ():
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")).get("viewer"))
        except (OSError, ValueError, AttributeError):
            continue
    return out or [None]


def pages(page_dir) -> list[Path]:
    """This page and the read-only copies served beside it (frame.serve_other: reviews/proto-<key>, of <key>)."""
    from .frame import _meta
    d = Path(page_dir).resolve()
    out = [d]
    for c in sorted(d.parent.glob("proto-*")):
        m = _meta(c)
        if c != d and m.get("ui") == "proto" and c.name == f"proto-{m.get('proto_copy_of')}":
            out.append(c.resolve())
    return out


def warm(dirs, areas, build) -> None:
    """Each area of each page, for each reader a build was kept for (or nobody's), one at a time behind the server."""
    def run():
        for d in dirs:
            for area in sorted(areas):
                for viewer in _viewers(d, area):
                    try:
                        _start((area, str(d), viewer), build).result(timeout=300)
                    except Exception as exc:  # a page that cannot build now is built on its first read, as before
                        print(f"proto {area} of {Path(d).name} not built ahead: {exc}", file=sys.stderr, flush=True)
    threading.Thread(target=run, daemon=True).start()
