"""A page's record storage: the only code that writes its record files.

Record files of a page directory: comments.json, current.meta.json,
.review-drafts/vN.json, project.json, read-state.json, seen.json,
categories.json, plan-topics.json, cards.json and rounds.ndjson. Outside it:
the page's bus <bus root>/<project>/<slug>.ndjson and its delivery journal
<state>/deliveries/<project>/<slug>.json.

Every writer goes through this module, so the storage behind a page can
change in one place. This is the JSON backend: each function does exactly
what the code it replaced did, byte for byte and lock for lock.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path

RECORD_NAMES = frozenset({
    "comments.json", "current.meta.json", "project.json", "read-state.json", "seen.json",
    "categories.json", "plan-topics.json", "cards.json", "rounds.ndjson",
})
SIDECARS = {"project": "project.json", "read-state": "read-state.json", "seen": "seen.json",
            "categories": "categories.json", "plan-topics": "plan-topics.json", "cards": "cards.json"}
_EMPTY_STORE = {"schema_version": 2, "anchors": {}, "archived": {}}

_STORE_LOCK = threading.RLock()
_STORE_LOCAL = threading.local()


def backend(slug_dir) -> str:
    """'sqlite' when the page has an enabled page.db, else 'json'."""
    return "json"


# ── reading ──────────────────────────────────────────────────────────────
def read_json(path, default=None):
    """A record file's parsed content; `default` when it is missing or unreadable."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def read_comments(slug_dir) -> dict:
    from .sync_server import _validate_store
    data = read_json(Path(slug_dir) / "comments.json")
    return _validate_store(data) if data is not None else json.loads(json.dumps(_EMPTY_STORE))


def read_meta(slug_dir) -> dict:
    data = read_json(Path(slug_dir) / "current.meta.json", {})
    return data if isinstance(data, dict) else {}


class Snapshot:
    """A read-only view of one page's records."""

    def __init__(self, slug_dir):
        self.dir = Path(slug_dir)

    @property
    def comments(self) -> dict:
        return read_comments(self.dir)

    @property
    def meta(self) -> dict:
        return read_meta(self.dir)

    def sidecar(self, name: str, default=None):
        return read_json(self.dir / SIDECARS[name], default)

    def rounds(self) -> list[dict]:
        return list(read_lines(self.dir / "rounds.ndjson"))


def snapshot(slug_dir) -> Snapshot:
    return Snapshot(slug_dir)


def read_lines(path):
    """Each parsable JSON object line of an NDJSON file, in order."""
    try:
        with open(path, encoding="utf-8") as stream:
            for line in stream:
                try:
                    value = json.loads(line)
                except ValueError:
                    continue
                if isinstance(value, dict):
                    yield value
    except OSError:
        return


def events_after(bus_file, seq: int = 0, *, types=None, exclude=None) -> list[dict]:
    """Bus events after line `seq` (1-based line numbers count every line)."""
    out = []
    try:
        with open(bus_file, encoding="utf-8") as stream:
            for number, line in enumerate(stream, 1):
                if number <= seq:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(event, dict):
                    continue
                name = event.get("event")
                if (types and name not in types) or (exclude and name in exclude):
                    continue
                out.append({**event, "seq": number})
    except OSError:
        pass
    return out


# ── the transaction ──────────────────────────────────────────────────────
class Tx:
    """One locked read-modify-write of a page. Loads lazily and, on a clean
    exit, writes back only the records whose serialized text changed."""

    def __init__(self, slug_dir):
        self.dir = Path(slug_dir)
        self._loaded: dict[str, tuple[object, str]] = {}
        self._events: list[tuple] = []

    def _load(self, key, reader):
        if key not in self._loaded:
            value = reader()
            self._loaded[key] = (value, json.dumps(value, ensure_ascii=False, sort_keys=True))
        return self._loaded[key][0]

    @property
    def comments(self) -> dict:
        return self._load("comments", lambda: read_comments(self.dir))

    @property
    def meta(self) -> dict:
        return self._load("meta", lambda: read_meta(self.dir))

    def sidecar(self, name: str, default=None):
        return self._load(name, lambda: read_json(self.dir / SIDECARS[name], default))

    def set_sidecar(self, name: str, value) -> None:
        self.sidecar(name)
        self._loaded[name] = (value, self._loaded[name][1])

    def event(self, bus_dir, slug: str, event: dict) -> None:
        self._events.append((bus_dir, slug, event))

    def _flush(self) -> None:
        for key, (value, text) in self._loaded.items():
            if json.dumps(value, ensure_ascii=False, sort_keys=True) == text:
                continue
            if key == "comments":
                write_json(self.dir / "comments.json", value)
            elif key == "meta":
                update_meta(self.dir, lambda meta, value=value: (meta.clear(), meta.update(value)))
            else:
                write_bytes(self.dir / SIDECARS[key], (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode())
        for bus_dir, slug, event in self._events:
            bus_append(bus_dir, slug, event)


@contextmanager
def transaction(directory, *, write=True):
    """Serialize HTTP and direct agent storage writes across threads/processes.

    Nested on the same thread it joins the outer transaction."""
    from .categories import safe_path
    with _STORE_LOCK:
        path = safe_path(directory, ".comments.json.lock")
        held = getattr(_STORE_LOCAL, "held", {})
        if path in held:
            yield held[path]
            return
        try:
            if write:
                path.parent.mkdir(parents=True, exist_ok=True)
            lock = path.open("a+" if write else "r")
        except FileNotFoundError:
            if write:
                raise
            lock = None
        except OSError:
            # A read-only page dir (an archive or snapshot served for viewing)
            # has no writer to serialize against: reads go ahead unlocked and
            # any write fails on its own.
            if os.access(path.parent, os.W_OK):
                raise
            lock = None
        tx = Tx(directory)
        if lock is None:
            yield tx
            tx._flush()
            return
        with lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            _STORE_LOCAL.held = {**held, path: tx}
            try:
                yield tx
                tx._flush()
            finally:
                _STORE_LOCAL.held = held


def put_items(tx: Tx, items) -> None:
    """Replace stored comments by id (hot paths: batch resolve, decision clicks)."""
    by_id = {item["id"]: item for item in items}
    for area in ("anchors", "archived"):
        for anchor in tx.comments.get(area, {}).values():
            for index, comment in enumerate(anchor):
                if comment.get("id") in by_id:
                    anchor[index] = by_id.pop(comment["id"])
    if by_id:
        raise KeyError(f"not in the store: {', '.join(sorted(by_id))}")


# ── writing ──────────────────────────────────────────────────────────────
def _refuse_if_moved(*directories) -> None:
    from .consolidate import refuse_if_moved
    for directory in directories:
        refuse_if_moved(directory)


def write_json(path, data) -> None:
    """Pretty JSON, atomically, keeping the file's mode (0600 when new)."""
    path = Path(path)
    _refuse_if_moved(path.parent)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(data, output, indent=2, ensure_ascii=False)
            os.fchmod(output.fileno(), mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def write_bytes(path, body: bytes) -> None:
    """Durable atomic replace: fsync the file and its directory."""
    path = Path(path)
    _refuse_if_moved(*list(path.parents)[:4])  # page/, attachments/, plans/<id>/versions/
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix="." + path.name, dir=path.parent, delete=False) as out:
            temporary = Path(out.name)
            out.write(body)
            os.fchmod(out.fileno(), mode)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
        temporary = None
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def write_text(path, text: str) -> None:
    """Replace through a fixed .tmp sibling; servers read the result live."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_journal(path, value: dict) -> None:
    """Compact JSON, fsynced: the delivery journal."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)


def update_meta(slug_dir, mutate, *, read=None, durable=False) -> dict:
    """Re-read, mutate and write current.meta.json under current.meta.json.lock.

    The server caches content stamps into this file while the CLI swaps
    versions and stamps owners, so every writer takes this lock. `read`
    replaces the plain reader (the server injects the registry owner);
    `durable` writes through write_json (mode kept, moved pages refused).
    """
    path = Path(slug_dir) / "current.meta.json"
    with open(path.with_suffix(".json.lock"), "a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            meta = (read or (lambda: read_meta(slug_dir)))()
            mutate(meta)
            if durable:
                write_json(path, meta)
            else:
                tmp = path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
                os.replace(tmp, path)
            return meta
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def append_line(path, line: str, *, fsync: bool = False) -> None:
    """Append one NDJSON line."""
    path = Path(path)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)
        if fsync:
            fh.flush()
            os.fsync(fh.fileno())


def bus_append(bus_dir, slug: str, event: dict) -> None:
    """Append one event to the page's bus, timestamped and slugged."""
    if not bus_dir:
        return
    from datetime import UTC, datetime

    from .submitted import draft_event
    bus_dir = Path(bus_dir)
    bus_dir.mkdir(parents=True, exist_ok=True)
    event = dict(event)
    if draft_event(event):
        event["deferred"] = True
    event.setdefault("ts", datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    event.setdefault("slug", slug)
    append_line(bus_dir / f"{slug}.ndjson", json.dumps(event, ensure_ascii=False) + "\n",
                fsync=event.get("event") == "session_push" and bool(event.get("round")))


def append_round(directory, event: dict) -> None:
    """Add one round to rounds.ndjson once, by id, under the file's own lock."""
    directory = Path(directory)
    _refuse_if_moved(directory)
    path = directory / "rounds.ndjson"
    with path.open("a+", encoding="utf-8") as source:
        fcntl.flock(source.fileno(), fcntl.LOCK_EX)
        source.seek(0)
        for line in source:
            try:
                old = json.loads(line)
            except ValueError:
                continue
            if isinstance(old, dict) and old.get("id") == event["id"]:
                return
        source.seek(0, 2)
        source.write(json.dumps(event, ensure_ascii=False) + "\n")
        source.flush()
        os.fsync(source.fileno())


def write_lines(path, rows) -> None:
    """Rewrite a whole NDJSON file (page consolidation builds rounds this way)."""
    with Path(path).open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
