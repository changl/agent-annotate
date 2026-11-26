"""Read-only document history and immutable submitted-review snapshots."""
from __future__ import annotations

import json
import re
from bisect import bisect_right
from datetime import datetime
from pathlib import Path

_BUS_CACHE_BYTES = 16 * 1024 * 1024
_BUS_CACHE_FILES = 32


def _time(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return 0


def _events(path):
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as source:
        for line in source:
            try:
                event = json.loads(line)
            except ValueError:
                continue  # A concurrent append may leave an incomplete last line.
            if isinstance(event, dict):
                yield event


def _plain_files(directory) -> set[str]:
    """Names of the regular files (no symlinks) in directory/content and /versions, whose
    _available check needs no path resolution (FLD: 1,134 versions took ~0.5 s to resolve)."""
    import os
    names = set()
    for kind in ("content", "versions"):
        path = directory / kind
        if path.is_symlink():
            continue
        try:
            with os.scandir(path) as entries:
                names |= {entry.name for entry in entries if entry.is_file(follow_symlinks=False)}
        except OSError:
            continue
    return names


def _available(directory, version, plain=()):
    if version + ".html" in plain:
        return True
    for kind in ("content", "versions"):
        path = directory / kind / (version + ".html")
        try:
            if path.resolve().is_relative_to(directory.resolve()) and path.is_file():
                return True
        except RuntimeError:
            continue
    return False


def save_round(directory: Path, event: dict) -> None:
    """A page copy carries its review history even after its bus is pruned."""
    from .store import append_round
    append_round(directory, event)


def history_buses(bus: Path | None, archive: Path | None) -> list[Path]:
    paths = [bus] if bus else []
    if bus and archive:
        paths += sorted(archive.glob("*/" + bus.parent.name + "/" + bus.name))
    return paths


def _bus_rounds(path, cache, keep=lambda event: event.get("event") == "round_submitted"):
    """Reuse complete lines only after checking the exact previously read prefix.

    Unlike an inode/offset cursor, this also handles in-place rewrites and
    replacement files that grow. A partial trailing line is retried next time.
    """
    data = path.read_bytes() if path.is_file() else b""
    prefix, rounds = cache.get(path, (b"", []))
    if not data.startswith(prefix):
        prefix, rounds = b"", []
    tail = data[len(prefix):]
    boundary = tail.rfind(b"\n") + 1

    def parse(chunk):
        for line in chunk.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if isinstance(event, dict) and keep(event):
                yield event

    rounds = rounds + list(parse(tail[:boundary]))
    cache[path] = (data[:len(prefix) + boundary], rounds)
    # Bound retained prefixes across both the current bus and all archives.
    while (len(cache) > _BUS_CACHE_FILES
           or sum(len(value[0]) for value in cache.values()) > _BUS_CACHE_BYTES):
        del cache[next(iter(cache))]
    return [*rounds, *parse(tail[boundary:])]


def _versions(directory, meta_bytes, *, check_availability):
    meta = json.loads(meta_bytes if meta_bytes is not None else (directory / "current.meta.json").read_bytes())
    versions = []
    plain = _plain_files(directory) if check_availability else ()
    for item in meta.get("history", []):
        version = item.get("version", "")
        if not isinstance(version, str) or not re.fullmatch(r"v[0-9]{1,10}", version):
            continue
        if check_availability:
            item = {**item, "current": version == meta.get("current"), "available": _available(directory, version, plain)}
        versions.append(item)
    versions.sort(key=lambda item: _time(item.get("ts")), reverse=True)
    return versions


def _records(directory, store_bytes):
    store = json.loads(store_bytes) if store_bytes is not None else (
        json.loads((directory / "comments.json").read_bytes()) if (directory / "comments.json").exists() else {})
    if isinstance(store, dict):
        from .cold import merged
        store = merged(directory, store)
    records = {}
    for bucket in ("anchors", "archived"):
        groups = store.get(bucket) or {}
        for items in (groups.values() if isinstance(groups, dict) else [groups]):
            for comment in items:
                if isinstance(comment, dict) and comment.get("id"):
                    records[comment["id"]] = comment
    return records


def _add_version_answers(versions, records):
    from .categories import comment_category

    # Index each source's publication intervals once. Previously every version
    # rescanned every decision and reparsed its timestamp while holding up writes.
    intervals = {}
    for item in versions:
        item["answers"] = []
        intervals.setdefault(item.get("source_page"), {}).setdefault(_time(item.get("ts")), []).append(item)
    starts = {source: sorted(items) for source, items in intervals.items()}
    wildcards = [source for source in intervals if not source]
    for comment in records.values():
        target = comment.get("target") if isinstance(comment.get("target"), dict) else {}
        history = comment.get("decision_history") if isinstance(comment.get("decision_history"), list) else []
        for decision in history + [comment.get("decision")]:
            if (not isinstance(decision, dict) or not decision.get("verdict")
                    or decision.get("round_pending") or decision.get("discarded") or decision.get("inherited")):
                continue
            timestamp = _time(decision.get("ts"))
            for source in wildcards + ([target["source_page"]] if target.get("source_page") else []):
                times = starts.get(source, [])
                index = bisect_right(times, timestamp) - 1
                if index < 0 or not times[index]:
                    continue
                for item in intervals[source][times[index]]:
                    item["answers"].append({"comment_id": comment["id"],
                        "category": comment_category(comment),
                        "number": target.get("source_number", comment.get("number")),
                        "prompt": "", "verdict": decision["verdict"], "text": decision.get("text", ""),
                        "by": decision.get("by"), "ts": decision.get("ts")})


def _submitted_rounds(directory, bus, archive, bus_cache):
    from .store import backend, events_after

    saved = directory / "rounds.ndjson"
    buses = history_buses(bus, archive)
    if bus_cache is not None:
        for path in list(bus_cache):
            if path not in buses and path != saved:
                del bus_cache[path]
    found = _bus_rounds(saved, bus_cache, lambda event: True) if bus_cache is not None else _events(saved)
    rounds = {event["id"]: (event, True) for event in found if event.get("id")}
    indexed = bus is not None and backend(directory) == "sqlite"
    for path in buses:
        if indexed and path == bus:
            found = [row["event"] for row in events_after(directory, bus, types=("round_submitted",))]
        else:
            found = _bus_rounds(path, bus_cache) if bus_cache is not None else _events(path)
        for event in found:
            if event.get("event") != "round_submitted":
                continue
            identifier = event.get("round_id") or str(event.get("ts")) + ":" + str(event.get("by"))
            rounds.setdefault(identifier, (event, False))
    return sorted(rounds.items(), key=lambda item: _time(item[1][0].get("ts")), reverse=True)


def _restore_legacy_round(identifier, event, versions, records):
    from .categories import comment_category

    version = event.get("version")
    if not version:
        version = next((item["version"] for item in versions
                        if _time(item.get("ts")) and _time(item.get("ts")) <= _time(event.get("ts"))), None)
    answers = event.get("answers")
    if not isinstance(answers, list):
        answers = []
        for cid in event.get("comment_ids", []):
            comment = records.get(cid, {})
            decisions = list(comment.get("decision_history") or []) + [comment.get("decision") or {}]
            choices = [d for d in decisions if d.get("verdict") and not d.get("round_pending")
                       and not d.get("discarded") and _time(d.get("ts")) <= _time(event.get("ts"))]
            if choices:
                decision = max(choices, key=lambda d: _time(d.get("ts")))
                answers.append({"comment_id": cid, "number": comment.get("number"),
                                "category": comment_category(comment),
                                "verdict": decision["verdict"], "text": decision.get("text", ""),
                                "prompt": "", "by": decision.get("by")})
    return {"id": identifier, "ts": event.get("ts"), "by": event.get("by"),
            "note": event.get("note"), "version": version, "answers": answers,
            "edits": event.get("edits", []), "snapshot": isinstance(event.get("answers"), list)}


def review_history(directory: Path, bus: Path | None = None, archive: Path | None = None,
                   *, meta_bytes: bytes | None = None, store_bytes: bytes | None = None,
                   bus_cache: dict | None = None, latest: bool = False) -> dict:
    versions = records = None
    if not latest:
        versions = _versions(directory, meta_bytes, check_availability=True)
        records = _records(directory, store_bytes)
        _add_version_answers(versions, records)
    rounds = []
    for identifier, (event, local) in _submitted_rounds(directory, bus, archive, bus_cache):
        if not local:
            # Only saved snapshots can carry the send_id that pairs two records.
            if latest and rounds:
                continue
            if versions is None and not event.get("version"):
                versions = _versions(directory, meta_bytes, check_availability=False)
            if records is None and not isinstance(event.get("answers"), list) and event.get("comment_ids"):
                records = _records(directory, store_bytes)
            event = _restore_legacy_round(identifier, event, versions or [], records or {})
        if latest and not _round_has_content(event):
            continue
        rounds.append(event)
        if latest and not rounds[0].get("send_id"):
            break
    return latest_round({"rounds": rounds}) if latest else {"versions": versions, "rounds": rounds}


def _round_has_content(round_):
    return round_.get("receipt") or round_.get("answers") or round_.get("edits") or round_.get("note")


def latest_round(history: dict) -> dict:
    """The newest Send only (its round and push records share a send_id): all the header and Send read on load."""
    rounds = [r for r in history["rounds"] if _round_has_content(r)]
    if not rounds:
        return {"rounds": []}
    send_id = rounds[0].get("send_id")
    return {"rounds": [r for r in rounds if r is rounds[0] or (send_id and r.get("send_id") == send_id)]}
