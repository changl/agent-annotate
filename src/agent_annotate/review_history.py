"""Read-only document history and immutable submitted-review snapshots."""
from __future__ import annotations

import fcntl
import json
import os
import re
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


def review_history(directory: Path, bus: Path | None = None, archive: Path | None = None) -> dict:
    from .categories import comment_category
    meta = json.loads((directory / "current.meta.json").read_text())
    store = json.loads((directory / "comments.json").read_text()) if (directory / "comments.json").exists() else {}
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
    for item in versions:
        start = _time(item.get("ts"))
        next_times = [_time(other.get("ts")) for other in versions
                      if other.get("source_page") == item.get("source_page") and _time(other.get("ts")) > start]
        end = min(next_times) if next_times else float("inf")
        item["answers"] = []
        if not start:
            continue
        for comment in records.values():
            target = comment.get("target") if isinstance(comment.get("target"), dict) else {}
            if item.get("source_page") and target.get("source_page") != item["source_page"]:
                continue
            history = comment.get("decision_history") if isinstance(comment.get("decision_history"), list) else []
            for decision in history + [comment.get("decision")]:
                if not isinstance(decision, dict):
                    continue  # older or hand-edited data
                if (decision.get("verdict") and not decision.get("round_pending") and not decision.get("discarded")
                        and start <= _time(decision.get("ts")) < end):
                    item["answers"].append({"comment_id": comment["id"],
                        "category": comment_category(comment),
                        "number": target.get("source_number", comment.get("number")),
                        "prompt": "", "verdict": decision["verdict"], "text": decision.get("text", ""),
                        "by": decision.get("by"), "ts": decision.get("ts")})
    rounds = {event["id"]: event for event in _events(directory / "rounds.ndjson") if event.get("id")}
    paths = [bus] if bus else []
    if bus and archive:
        paths += sorted(archive.glob("*/" + bus.parent.name + "/" + bus.name))
    for path in paths:
        for event in _events(path):
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
