"""Read-only document history and immutable submitted-review snapshots."""
from __future__ import annotations

import fcntl
import json
import os
import re
from bisect import bisect_right
from datetime import datetime
from pathlib import Path


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


def _available(directory, version):
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
    from .consolidate import refuse_if_moved
    refuse_if_moved(directory)
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


def history_buses(bus: Path | None, archive: Path | None) -> list[Path]:
    paths = [bus] if bus else []
    if bus and archive:
        paths += sorted(archive.glob("*/" + bus.parent.name + "/" + bus.name))
    return paths


def _bus_rounds(path, cache):
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
            if isinstance(event, dict) and event.get("event") == "round_submitted":
                yield event

    rounds = rounds + list(parse(tail[:boundary]))
    cache[path] = (data[:len(prefix) + boundary], rounds)
    return [*rounds, *parse(tail[boundary:])]


def review_history(directory: Path, bus: Path | None = None, archive: Path | None = None,
                   *, meta_bytes: bytes | None = None, store_bytes: bytes | None = None,
                   bus_cache: dict | None = None) -> dict:
    from .categories import comment_category
    meta = json.loads(meta_bytes if meta_bytes is not None else (directory / "current.meta.json").read_bytes())
    store = json.loads(store_bytes) if store_bytes is not None else (
        json.loads((directory / "comments.json").read_bytes()) if (directory / "comments.json").exists() else {})
    versions = []
    for item in meta.get("history", []):
        version = item.get("version", "")
        if not isinstance(version, str) or not re.fullmatch(r"v[0-9]{1,10}", version):
            continue
        available = _available(directory, version)
        versions.append({**item, "current": version == meta.get("current"), "available": available})
    versions.sort(key=lambda item: _time(item.get("ts")), reverse=True)
    records = {}
    for bucket in ("anchors", "archived"):
        groups = store.get(bucket) or {}
        for items in (groups.values() if isinstance(groups, dict) else [groups]):
            for comment in items:
                if isinstance(comment, dict) and comment.get("id"):
                    records[comment["id"]] = comment
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
                    or decision.get("round_pending") or decision.get("discarded")):
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
    rounds = {event["id"]: event for event in _events(directory / "rounds.ndjson") if event.get("id")}
    buses = history_buses(bus, archive)
    if bus_cache is not None:
        for path in list(bus_cache):
            if path not in buses:
                del bus_cache[path]
    for path in buses:
        for event in _bus_rounds(path, bus_cache) if bus_cache is not None else _events(path):
            if event.get("event") != "round_submitted":
                continue
            identifier = event.get("round_id") or str(event.get("ts")) + ":" + str(event.get("by"))
            if identifier in rounds:
                continue
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
            rounds[identifier] = {"id": identifier, "ts": event.get("ts"), "by": event.get("by"),
                                  "note": event.get("note"), "version": version, "answers": answers,
                                  "edits": event.get("edits", []),
                                  "snapshot": isinstance(event.get("answers"), list)}
    return {"versions": versions, "rounds": sorted(rounds.values(), key=lambda r: _time(r.get("ts")), reverse=True)}
