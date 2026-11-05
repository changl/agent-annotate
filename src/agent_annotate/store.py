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
    """'sqlite' when the page has a page.db (`db off` sets it aside), else 'json'."""
    return "sqlite" if (Path(slug_dir) / DB_NAME).is_file() else "json"


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


# ── the SQLite page store (docs/validation/stages-3-5-specs-20261104.md §5) ──
DB_NAME = "page.db"
SCHEMA_VERSION = "1"
SCHEMA = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE page(
  id INTEGER PRIMARY KEY CHECK (id = 1),
  name TEXT, current_version TEXT,
  owner_json TEXT,
  meta_json TEXT NOT NULL);
CREATE TABLE versions(
  n INTEGER NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('draft','live')),
  label TEXT, fixes TEXT, ts TEXT,
  preview_token TEXT, verified INTEGER, reserved_json TEXT,
  position INTEGER NOT NULL,
  entry_json TEXT NOT NULL,
  PRIMARY KEY (n, state));
CREATE TABLE items(
  id TEXT PRIMARY KEY,
  area TEXT NOT NULL CHECK (area IN ('anchors','archived')),
  anchor_id TEXT NOT NULL, doc TEXT, number INTEGER, version TEXT, status TEXT,
  category TEXT, origin_id TEXT, created_at TEXT, resolved_in_version TEXT,
  round_pending INTEGER NOT NULL DEFAULT 0,
  position INTEGER NOT NULL,
  body_json TEXT NOT NULL);
CREATE INDEX items_anchor ON items(anchor_id, position);
CREATE INDEX items_number ON items(number);
CREATE INDEX items_status ON items(status);
CREATE TABLE numbers(        -- one row per question lineage; legacy pages reuse a number on other anchors
  number INTEGER NOT NULL, anchor_id TEXT NOT NULL, doc TEXT, first_item TEXT NOT NULL,
  PRIMARY KEY (number, anchor_id));
CREATE TABLE approved_plans(id TEXT PRIMARY KEY, position INTEGER NOT NULL, body_json TEXT NOT NULL);
CREATE TABLE events(
  seq INTEGER PRIMARY KEY, ts TEXT, type TEXT,
  item TEXT, session TEXT, round TEXT,
  bus_offset INTEGER,
  data_json TEXT NOT NULL);
CREATE INDEX events_type ON events(type, seq);
CREATE INDEX events_item ON events(item, seq);
CREATE TABLE cursors(
  kind TEXT NOT NULL CHECK (kind IN ('inbox','hook','monitor','delivery')),
  reader TEXT NOT NULL, seq INTEGER NOT NULL, bus_offset INTEGER NOT NULL,
  PRIMARY KEY (kind, reader));
CREATE TABLE deliveries(id TEXT PRIMARY KEY, round TEXT, state TEXT, position INTEGER NOT NULL, row_json TEXT NOT NULL);
CREATE TABLE rounds(seq INTEGER PRIMARY KEY, round TEXT, ts TEXT, body_json TEXT NOT NULL);
CREATE INDEX rounds_round ON rounds(round);
CREATE TABLE sidecars(
  name TEXT PRIMARY KEY CHECK (name IN ('project','read-state','seen','categories','plan-topics','cards')),
  body_json TEXT NOT NULL, updated_at TEXT NOT NULL);
"""
_HISTORY, _OWNER = "\x00history", "\x00owner"   # where meta_json keeps the two promoted keys
_VERSION = __import__("re").compile(r"v([0-9]+)")


class Refused(ValueError):
    """Import refused; `rows` lists what to fix."""

    def __init__(self, message: str, rows: list[str]):
        super().__init__(message)
        self.rows = rows


def connect(path):
    import sqlite3
    conn = sqlite3.connect(str(path), timeout=5, isolation_level=None, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


# JSON layouts the writers use; a file is exported in the layout it was read in.
def _layout_guess(text: str) -> dict:
    head = text[:64]
    if head.startswith("{\n  ") or head.startswith("[\n  "):
        layout = {"indent": 2}
    elif head.startswith("{\n ") or head.startswith("[\n "):
        layout = {"indent": 1}
    elif head.startswith(('{"', '["')) and ('":' in head and '": ' not in head.split(",")[0]):
        layout = {"separators": [",", ":"]}
    else:
        layout = {}
    layout["ascii"] = text.isascii()
    layout["nl"] = text.endswith("\n")
    return layout


def _dump(value, layout: dict) -> str:
    separators = layout.get("separators")
    return json.dumps(value, ensure_ascii=layout.get("ascii", False), indent=layout.get("indent"),
                      separators=tuple(separators) if separators else None) + ("\n" if layout.get("nl") else "")


def _layout(text: str, value) -> tuple[dict, bool]:
    """The layout that reproduces `text` from `value`, and whether it does byte for byte."""
    guess = _layout_guess(text)
    if _dump(value, guess) == text:
        return guess, True
    if guess["ascii"] and _dump(value, {**guess, "ascii": False}) == text:
        return {**guess, "ascii": False}, True
    return guess, False


class Sources:
    """The page's record files, raw, as `db import` reads them."""

    def __init__(self, slug_dir, *, project=None, slug=None, bus_file=None, state_dir=None):
        from . import paths
        self.dir = Path(slug_dir)
        self.slug = slug or self.dir.name
        self.project = project
        self.bus = Path(bus_file) if bus_file else (paths.BUS_ROOT / project / f"{self.slug}.ndjson" if project else None)
        self.state = Path(state_dir) if state_dir else paths.STATE_DIR
        self.files: dict[str, str] = {}
        for name in ("comments.json", "current.meta.json", "rounds.ndjson", *SIDECARS.values()):
            self._read(name)
        for draft in sorted((self.dir / ".review-drafts").glob("v*.json")):
            self._read(f".review-drafts/{draft.name}")
        self.journal_path = self.state / "deliveries" / (project or "") / f"{self.slug}.json"
        self.journal = self.journal_path.read_text(encoding="utf-8") if project and self.journal_path.is_file() else None
        self.bus_bytes = self.bus.read_bytes() if self.bus and self.bus.is_file() else b""

    def _read(self, name: str) -> None:
        path = self.dir / name
        if path.is_file():
            self.files[name] = path.read_text(encoding="utf-8")

    def cursors(self) -> dict[tuple[str, str], int]:
        """Every byte-offset cursor on this page's bus, by (kind, reader)."""
        found = {}
        if not self.project:
            return found
        name = f"{self.slug}.offset"
        roots = (("inbox", self.state / "bus-offsets"), ("hook", self.state / "hook-offsets"))
        for kind, root in roots:
            candidates = list(root.glob(f"{self.project}/{name}*")) + list(root.glob(f"*/{self.project}/{name}*"))
            for path in candidates:
                if path.name != name and not path.name.startswith(name + "."):
                    continue
                reader = str(path.relative_to(root))
                try:
                    found[(kind, reader)] = int(path.read_text(encoding="utf-8").strip() or 0)
                except (OSError, ValueError):
                    continue
        monitor = self.state / "monitor-offsets" / self.project / name
        try:
            found[("monitor", "monitor")] = int(monitor.read_text(encoding="utf-8").strip() or 0)
        except (OSError, ValueError):
            pass
        if self.journal is not None:
            try:
                found[("delivery", "journal")] = int(json.loads(self.journal).get("offset") or 0)
            except (ValueError, AttributeError, TypeError):
                pass
        return found


def _bus_lines(data: bytes):
    """(end offset, parsed event or None, text) per line; an unterminated tail is skipped."""
    offset = 0
    for raw in data.splitlines(keepends=True):
        offset += len(raw)
        if not raw.endswith(b"\n"):
            yield offset, None, None
            return
        text = raw[:-1].decode("utf-8", errors="replace")
        try:
            event = json.loads(text)
        except ValueError:
            event = None
        yield offset, event if isinstance(event, dict) else None, text


def _item_row(comment: dict, area: str, anchor: str, position: int) -> tuple:
    from .categories import comment_category
    number = comment.get("number")
    return (comment["id"], area, anchor, comment.get("doc"), number if isinstance(number, int) else None,
            comment.get("version"), comment.get("status"), comment_category(comment), comment.get("origin_id"),
            comment.get("created_at"), comment.get("resolved_in_version"),
            1 if comment.get("flagged_for_session") else 0, position, _compact(comment))


def _event_row(seq: int, offset: int | None, event: dict, text: str) -> tuple:
    return (seq, event.get("ts"), event.get("event"), event.get("comment_id"),
            event.get("session") or event.get("session_id"), event.get("round") or event.get("round_id"),
            offset, text)


def _comment_rows(store: dict, refusals: list[str]):
    frame, items, plans = {}, [], []
    seen: dict[str, str] = {}
    for key, value in store.items():
        if key in ("anchors", "archived") and isinstance(value, dict):
            frame[key] = list(value)
            for anchor, comments in value.items():
                for position, comment in enumerate(comments if isinstance(comments, list) else []):
                    if not isinstance(comment, dict) or not isinstance(comment.get("id"), str):
                        refusals.append(f"{key}/{anchor}[{position}]: an item without an id")
                        continue
                    if comment["id"] in seen:
                        refusals.append(f"item {comment['id']}: stored twice ({seen[comment['id']]} and {key}/{anchor})")
                        continue
                    seen[comment["id"]] = f"{key}/{anchor}"
                    items.append(_item_row(comment, key, anchor, position))
        elif key == "approved_plans" and isinstance(value, dict):
            frame[key] = list(value)
            plans = [(plan_id, position, _compact(body)) for position, (plan_id, body) in enumerate(value.items())]
        else:
            frame[key] = {"\x00value": value}
    return frame, items, plans


def _number_rows(items, shared: list[str]):
    """The first item of each (number, anchor); a number on two anchors is listed in `shared`."""
    numbers: dict[tuple, tuple] = {}
    first: dict[int, tuple] = {}
    for row in items:
        number, anchor = row[4], row[2]
        if number is None or (number, anchor) in numbers:
            continue
        numbers[(number, anchor)] = (number, anchor, row[3], row[0])
        if number not in first:
            first[number] = numbers[(number, anchor)]
        else:
            shared.append(f"#{number}: anchor {first[number][1]} (item {first[number][3]}) and anchor {anchor} (item {row[0]})")
    return list(numbers.values())


def _meta_rows(meta: dict, refusals: list[str]):
    entries, versions = [], []
    shape = {}
    for key, value in meta.items():
        if key == "history" and isinstance(value, list):
            shape[key] = _HISTORY
            entries = value
        elif key == "owner":
            shape[key] = _OWNER
        else:
            shape[key] = value
    seen = set()
    for position, entry in enumerate(entries):
        match = _VERSION.fullmatch(str(entry.get("version"))) if isinstance(entry, dict) else None
        if not match:
            refusals.append(f"history[{position}]: not a vN entry: {_compact(entry)[:80]}")
            continue
        n = int(match[1])
        if n in seen:
            refusals.append(f"history[{position}]: {entry['version']} listed twice")
            continue
        seen.add(n)
        versions.append((n, "live", entry.get("label"), entry.get("fixes"), entry.get("ts"), None, None, None,
                         position, _compact(entry)))
    page = (1, meta.get("name"), meta.get("current"), _compact(meta["owner"]) if "owner" in meta else None, _compact(shape))
    return page, versions


def _draft_row(name: str, text: str, refusals: list[str]):
    match = _VERSION.fullmatch(Path(name).stem)
    try:
        draft = json.loads(text)
    except ValueError:
        draft = None
    if not match or not isinstance(draft, dict):
        refusals.append(f"{name}: not a readable draft")
        return None
    reserved = draft.get("reserved")
    return (int(match[1]), "draft", draft.get("label"), draft.get("fixes"), None, draft.get("preview"),
            1 if draft.get("verified") else 0, _compact(reserved) if reserved is not None else None, 0, text)


def build(conn, sources: Sources) -> dict:
    """Fill an empty page.db from the page's files. Raises Refused with every problem found."""
    refusals: list[str] = []
    counts = {"skipped_lines": 0}
    files = sources.files
    layouts = {}

    def parsed(name, default):
        text = files.get(name)
        if text is None:
            return default
        try:
            value = json.loads(text)
        except ValueError:
            refusals.append(f"{name}: not valid JSON")
            return default
        layouts[name] = _layout(text, value)[0]
        return value

    store = parsed("comments.json", None)
    meta = parsed("current.meta.json", None)
    if store is not None and not isinstance(store, dict):
        refusals.append("comments.json: not an object")
        store = None
    if meta is not None and not isinstance(meta, dict):
        refusals.append("current.meta.json: not an object")
        meta = None
    frame, items, plans = _comment_rows(store, refusals) if store is not None else (None, [], [])
    shared: list[str] = []
    numbers = _number_rows(items, shared)
    if shared:
        counts["shared_numbers"] = shared
    page, versions = _meta_rows(meta, refusals) if meta is not None else (None, [])
    for name, text in files.items():
        if name.startswith(".review-drafts/"):
            row = _draft_row(name, text, refusals)
            if row:
                versions.append(row)
    events, ends = [], {0: 0}
    for offset, event, text in _bus_lines(sources.bus_bytes):
        if event is None:
            counts["skipped_lines"] += 1
        else:
            events.append(_event_row(len(events) + 1, offset, event, text))
        if text is not None:
            ends[offset] = len(events)
    cursors = []
    for (kind, reader), offset in sorted(sources.cursors().items()):
        if offset in ends:
            cursors.append((kind, reader, ends[offset], offset))
        elif offset > len(sources.bus_bytes):
            cursors.append((kind, reader, len(events), offset))
            counts.setdefault("cursors_past_end", []).append(f"{kind} {reader} at {offset}")
        else:
            refusals.append(f"cursor {kind} {reader}: byte {offset} is inside a bus line")
    deliveries, journal_shape = [], None
    if sources.journal is not None:
        try:
            journal = json.loads(sources.journal)
            layouts["journal"] = _layout(sources.journal, journal)[0]
            rows = journal.get("deliveries") if isinstance(journal, dict) else None
            journal_shape = {k: (list(v) if k == "deliveries" else v) for k, v in journal.items()}
            for position, (delivery_id, row) in enumerate((rows or {}).items()):
                deliveries.append((delivery_id, (row or {}).get("round_id") if isinstance(row, dict) else None,
                                   row.get("state") if isinstance(row, dict) else None, position, _compact(row)))
        except (ValueError, AttributeError) as exc:
            refusals.append(f"delivery journal: unreadable ({exc})")
    rounds = []
    for line in (files.get("rounds.ndjson") or "").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            row = None
        row = row if isinstance(row, dict) else {}
        rounds.append((len(rounds) + 1, row.get("id"), row.get("ts"), line))
    if refusals:
        raise Refused(f"{sources.slug}: import refused, {len(refusals)} problem(s)", refusals)

    now = _now()
    conn.executescript(SCHEMA)
    conn.execute("BEGIN IMMEDIATE")
    conn.executemany("INSERT INTO meta VALUES (?, ?)", [
        ("schema_version", SCHEMA_VERSION), ("imported_at", now), ("backend", "sqlite"),
        ("project", sources.project), ("slug", sources.slug),
        ("bus_file", str(sources.bus) if sources.bus else None),
        ("journal_file", str(sources.journal_path) if sources.journal is not None else None),
        ("comments_frame", _compact(frame) if frame is not None else None),
        ("journal_frame", _compact(journal_shape) if journal_shape is not None else None),
        ("rounds_nl", "1" if (files.get("rounds.ndjson") or "\n").endswith("\n") else "0"),
        *((f"layout:{name}", _compact(layout)) for name, layout in layouts.items()),
    ])
    if page:
        conn.execute("INSERT INTO page VALUES (?, ?, ?, ?, ?)", page)
    conn.executemany("INSERT INTO versions VALUES (?,?,?,?,?,?,?,?,?,?)", versions)
    conn.executemany("INSERT INTO items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", items)
    conn.executemany("INSERT INTO numbers VALUES (?,?,?,?)", numbers)
    conn.executemany("INSERT INTO approved_plans VALUES (?,?,?)", plans)
    conn.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?,?)", events)
    conn.executemany("INSERT INTO cursors VALUES (?,?,?,?)", cursors)
    conn.executemany("INSERT INTO deliveries VALUES (?,?,?,?,?)", deliveries)
    conn.executemany("INSERT INTO rounds VALUES (?,?,?,?)", rounds)
    conn.executemany("INSERT INTO sidecars VALUES (?,?,?)",
                     [(key, files[name], now) for key, name in SIDECARS.items() if name in files])
    conn.execute("COMMIT")
    counts.update(items=len(items), versions=sum(1 for v in versions if v[1] == "live"),
                  drafts=sum(1 for v in versions if v[1] == "draft"), events=len(events),
                  numbers=len(numbers), cursors=len(cursors), deliveries=len(deliveries), rounds=len(rounds))
    return counts


def _now() -> str:
    from datetime import UTC, datetime
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _meta_value(conn, key: str):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def export_texts(conn) -> dict[str, str]:
    """Every page record file the DB holds, as the text the JSON backend keeps."""
    layout = {key[len("layout:"):]: json.loads(value)
              for key, value in conn.execute("SELECT key, value FROM meta WHERE key LIKE 'layout:%'")}
    out: dict[str, str] = {}
    frame = _meta_value(conn, "comments_frame")
    if frame is not None:
        grouped: dict[tuple, list] = {}
        for area, anchor, body in conn.execute(
                "SELECT area, anchor_id, body_json FROM items ORDER BY area, anchor_id, position"):
            grouped.setdefault((area, anchor), []).append(json.loads(body))
        plans = {plan_id: json.loads(body) for plan_id, body in
                 conn.execute("SELECT id, body_json FROM approved_plans ORDER BY position")}
        store = {}
        for key, value in json.loads(frame).items():
            if key in ("anchors", "archived"):
                store[key] = {anchor: grouped.get((key, anchor), []) for anchor in value}
            elif key == "approved_plans":
                store[key] = {plan_id: plans[plan_id] for plan_id in value}
            else:
                store[key] = value["\x00value"]
        out["comments.json"] = _dump(store, layout.get("comments.json", {"separators": [",", ":"]}))
    page = conn.execute("SELECT owner_json, meta_json FROM page").fetchone()
    if page:
        history = [json.loads(entry) for (entry,) in
                   conn.execute("SELECT entry_json FROM versions WHERE state = 'live' ORDER BY position")]
        meta = {}
        for key, value in json.loads(page[1]).items():
            meta[key] = history if value == _HISTORY else json.loads(page[0]) if value == _OWNER else value
        out["current.meta.json"] = _dump(meta, layout.get("current.meta.json", {"indent": 2}))
    for n, entry in conn.execute("SELECT n, entry_json FROM versions WHERE state = 'draft' ORDER BY n"):
        out[f".review-drafts/v{n}.json"] = entry
    for name, body in conn.execute("SELECT name, body_json FROM sidecars"):
        out[SIDECARS[name]] = body
    lines = [body for (body,) in conn.execute("SELECT body_json FROM rounds ORDER BY seq")]
    if lines:
        out["rounds.ndjson"] = "\n".join(lines) + ("\n" if _meta_value(conn, "rounds_nl") == "1" else "")
    return out


def export_journal(conn) -> str | None:
    shape = _meta_value(conn, "journal_frame")
    if shape is None:
        return None
    rows = {delivery_id: json.loads(row) for delivery_id, row in
            conn.execute("SELECT id, row_json FROM deliveries ORDER BY position")}
    journal = {k: ({i: rows[i] for i in v} if k == "deliveries" else v) for k, v in json.loads(shape).items()}
    layout = _meta_value(conn, "layout:journal")
    return _dump(journal, json.loads(layout) if layout else {})


def diff(conn, sources: Sources) -> tuple[list[str], int]:
    """Differences between the DB and the page's files, and how many files match byte for byte."""
    differences, identical = [], 0
    texts = export_texts(conn)
    for name in sorted(set(texts) | set(sources.files)):
        mine, theirs = texts.get(name), sources.files.get(name)
        if mine == theirs:
            identical += 1
            continue
        if mine is None or theirs is None:
            differences.append(f"{name}: only in the {'files' if mine is None else 'db'}")
            continue
        if name.endswith(".ndjson"):
            if mine.splitlines() != theirs.splitlines():
                differences.append(f"{name}: lines differ")
            continue
        try:
            same = json.loads(mine) == json.loads(theirs)
        except ValueError:
            same = False
        if not same:
            differences.append(f"{name}: content differs")
        elif name in ("comments.json", "current.meta.json"):
            differences.append(f"{name}: same content, different layout")
    journal = export_journal(conn)
    if (journal is None) != (sources.journal is None) or (
            journal is not None and json.loads(journal) != json.loads(sources.journal)):
        differences.append("delivery journal differs")
    elif journal is not None:
        identical += journal == sources.journal
    stored = conn.execute("SELECT seq, bus_offset, data_json FROM events ORDER BY seq").fetchall()
    on_bus = [(offset, text) for offset, event, text in _bus_lines(sources.bus_bytes) if event is not None]
    known = {offset for _, offset, _ in stored}
    tail = [line for line in on_bus if line[0] not in known]
    if [(o, t) for _, o, t in stored] != on_bus[:len(stored)]:
        differences.append(f"bus: {len(stored)} events in the db, {len(on_bus)} on the bus, first {len(stored)} differ")
    elif tail:
        differences.append(f"bus: {len(tail)} newer events not in the db yet")
    ends = {offset: seq for seq, offset, _ in stored} | {0: 0}
    cursors = {(k, r): (s, o) for k, r, s, o in conn.execute("SELECT kind, reader, seq, bus_offset FROM cursors")}
    for key, offset in sources.cursors().items():
        if key not in cursors:
            differences.append(f"cursor {key[0]} {key[1]}: not in the db")
        elif cursors[key][1] != offset:
            differences.append(f"cursor {key[0]} {key[1]}: db {cursors[key][1]}, file {offset}")
        elif offset in ends and cursors[key][0] != ends[offset]:
            differences.append(f"cursor {key[0]} {key[1]}: maps to seq {cursors[key][0]}, bus says {ends[offset]}")
    return differences, identical


def _remove_db(path: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(str(path) + suffix).unlink(missing_ok=True)


def import_page(slug_dir, *, project=None, slug=None, bus_file=None, state_dir=None, dry_run=False) -> dict:
    """page.db from the page's files: build page.db.tmp, diff it, rename. The files are never modified."""
    import time
    started = time.monotonic()
    slug_dir = Path(slug_dir)
    target = slug_dir / DB_NAME
    if target.exists():
        raise ValueError(f"{slug_dir.name}: {DB_NAME} exists · fix: annotate db diff {slug or slug_dir.name}")
    _refuse_network_volume(slug_dir)
    sources = Sources(slug_dir, project=project, slug=slug, bus_file=bus_file, state_dir=state_dir)
    temporary = slug_dir / (DB_NAME + ".tmp")
    _remove_db(temporary)
    conn = connect(temporary)
    try:
        counts = build(conn, sources)
        differences, identical = diff(conn, sources)
        _record_fingerprints(conn, slug_dir, sources)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except BaseException:
        conn.close()
        _remove_db(temporary)
        raise
    conn.close()
    if differences:
        _remove_db(temporary)
        raise Refused(f"{sources.slug}: diff {len(differences)} after import", differences)
    if dry_run:
        _remove_db(temporary)
    else:
        os.replace(temporary, target)
        _remove_db(temporary)
    return {**counts, "slug": sources.slug, "diff": 0, "identical": identical, "files": len(sources.files),
            "seconds": time.monotonic() - started, "bytes": 0 if dry_run else target.stat().st_size}


def _fingerprint(path: Path, body: bytes | None = None) -> list | None:
    import hashlib
    try:
        stat = path.stat()
        body = path.read_bytes() if body is None else body
    except OSError:
        return None
    return [stat.st_size, stat.st_mtime_ns, hashlib.sha256(body).hexdigest()]


def _record_fingerprints(conn, slug_dir: Path, sources: Sources) -> None:
    rows = [(f"fp:{name}", _compact(_fingerprint(slug_dir / name))) for name in sources.files]
    conn.execute("BEGIN IMMEDIATE")
    conn.executemany("INSERT OR REPLACE INTO meta VALUES (?, ?)", rows)
    conn.execute("COMMIT")


def _refuse_network_volume(slug_dir: Path) -> None:
    """WAL needs shared memory that network shares do not give."""
    import subprocess
    try:
        out = subprocess.run(["df", "-P", str(slug_dir)], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return
    device = out.splitlines()[-1].split()[0] if out.strip() else ""
    if device.startswith("//") or ":/" in device:
        raise ValueError(f"{slug_dir.name}: {DB_NAME} refused on a network volume ({device}); the page stays on JSON")


def export_page(slug_dir) -> list[str]:
    """Write every record file from page.db; returns the names written."""
    slug_dir = Path(slug_dir)
    conn = connect(slug_dir / DB_NAME)
    try:
        texts = export_texts(conn)
    finally:
        conn.close()
    for name, text in texts.items():
        if (slug_dir / name).is_file() and (slug_dir / name).read_text(encoding="utf-8") == text:
            continue
        (slug_dir / name).parent.mkdir(parents=True, exist_ok=True)
        write_bytes(slug_dir / name, text.encode())
    return sorted(texts)


def db_off(slug_dir) -> Path:
    """Back to JSON: the files are current, so page.db is only set aside."""
    from datetime import UTC, datetime
    slug_dir = Path(slug_dir)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%MZ")
    kept = slug_dir / f"{DB_NAME}.off-{stamp}"
    with transaction(slug_dir):
        export_page(slug_dir)
        conn = connect(slug_dir / DB_NAME)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        os.replace(slug_dir / DB_NAME, kept)
        _remove_db(slug_dir / DB_NAME)
    return kept


def catch_up_bus(slug_dir, conn=None) -> int:
    """Bring the events table and the bus file level; returns the events moved.

    The bus stays a file hooks read by byte offset: lines another process
    appended are copied in, and events the DB holds without a bus line (a
    crash between commit and append) are appended."""
    own = conn is None
    conn = conn or connect(Path(slug_dir) / DB_NAME)
    try:
        bus = _meta_value(conn, "bus_file")
        if not bus:
            return 0
        began = not conn.in_transaction
        if began:
            conn.execute("BEGIN IMMEDIATE")
        try:
            moved = _catch_up(conn, bus)
        except BaseException:
            if began:
                conn.execute("ROLLBACK")
            raise
        if began:
            conn.execute("COMMIT")
        return moved
    finally:
        if own:
            conn.close()


def _catch_up(conn, bus: str) -> int:
    moved = 0
    pending = conn.execute("SELECT seq, data_json FROM events WHERE bus_offset IS NULL ORDER BY seq").fetchall()
    for seq, text in pending:
        append_line(bus, text + "\n")
        conn.execute("UPDATE events SET bus_offset = ? WHERE seq = ?", (Path(bus).stat().st_size, seq))
        moved += 1
    reset = int(_meta_value(conn, "bus_reset_seq") or 0)
    seq = conn.execute("SELECT coalesce(max(seq), 0) FROM events").fetchone()[0]
    start = conn.execute("SELECT coalesce(max(bus_offset), 0) FROM events WHERE seq > ?", (reset,)).fetchone()[0]
    rows = []
    try:
        with open(bus, "rb") as stream:
            if stream.seek(0, 2) < start:  # the bus was pruned or replaced: follow the new file
                conn.execute("INSERT OR REPLACE INTO meta VALUES ('bus_reset_seq', ?)", (str(seq),))
                start = 0
            stream.seek(start)
            tail = stream.read()
        for offset, event, text in _bus_lines(tail):
            if event is not None:
                seq += 1
                rows.append(_event_row(seq, start + offset, event, text))
        conn.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?,?)", rows)
    except OSError:
        pass
    return moved + len(rows)


def refresh_cursors(conn, sources: Sources) -> list[str]:
    """Mirror the cursor files (still written by hooks, inbox and monitors) into the DB;
    returns the cursors that point inside a bus line."""
    known = dict(conn.execute("SELECT bus_offset, seq FROM events WHERE bus_offset IS NOT NULL"))
    ends, last = {0: 0}, 0
    for offset, _, text in _bus_lines(sources.bus_bytes):
        if text is not None:
            last = known.get(offset, last)
            ends[offset] = last
    rows, bad = [], []
    size = len(sources.bus_bytes)
    for (kind, reader), offset in sorted(sources.cursors().items()):
        if offset in ends or offset > size:
            rows.append((kind, reader, ends.get(offset, last), offset))
        else:
            bad.append(f"cursor {kind} {reader}: byte {offset} is inside a bus line")
    began = not conn.in_transaction
    if began:
        conn.execute("BEGIN IMMEDIATE")
    conn.execute("DELETE FROM cursors")
    conn.executemany("INSERT INTO cursors VALUES (?,?,?,?)", rows)
    if began:
        conn.execute("COMMIT")
    return bad
