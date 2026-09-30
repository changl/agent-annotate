"""Read-only, estate-local review metrics without reviewer content or transcripts."""

from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from .decision_quality import decision_warnings
from .paths import BUS_ROOT, STATE_DIR

_SAFE_NAME = re.compile(r"[A-Za-z0-9_.-]+\Z")
_DELIVERY_STATES = ("started", "accepted", "pending", "uncertain", "superseded", "acknowledged")
_COUNT_KEYS = (
    "active_pages", "events", "decision_requests", "reviewer_decisions", "submitted_rounds",
    "legacy_rounds_without_id", "publish_successes", "publish_failures",
)
_LIMITATIONS = (
    "Estate-local: only pages in the current top-level project registries are included; retired pages are excluded.",
    "Active pages and decision quality are current snapshots, not historical window snapshots.",
    "Delivery states are latest journal rows timestamped in the window, not historical transitions.",
    "Prompt attempt, acceptance, and acknowledgment do not prove agent action completion.",
    "Browser timing and resource opens are not measured.",
    "Old round events without an ID have no deduplication guarantee.",
    "Only recorded events are counted; missing instrumentation is not evidence of no activity.",
)


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return timestamp.astimezone(UTC)
    except (ValueError, OverflowError):
        return None


def _read_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RecursionError):
        return {}
    return value if isinstance(value, dict) else {}


def _events(path: Path) -> Iterator[tuple[dict, datetime]]:
    try:
        with path.open("rb") as stream:
            for line in stream:
                if not line.endswith(b"\n"):
                    continue
                try:
                    event = json.loads(line)
                except (ValueError, RecursionError):
                    continue
                if not isinstance(event, dict):
                    continue
                timestamp = _parse_timestamp(event.get("ts"))
                if timestamp is not None:
                    yield event, timestamp
    except OSError:
        return


def _empty() -> dict:
    return {
        **dict.fromkeys(_COUNT_KEYS, 0),
        "deliveries": dict.fromkeys(_DELIVERY_STATES, 0),
        "decision_quality": {"cards": 0, "cards_with_warnings": 0, "warnings": 0},
        "_attempt_seconds": [],
        "_acceptance_seconds": [],
        "_acknowledgment_seconds": [],
    }


def _quality(slug_dir: object, aggregate: dict) -> None:
    if not isinstance(slug_dir, str) or not slug_dir:
        return
    anchors = _read_object(Path(slug_dir) / "comments.json").get("anchors")
    if not isinstance(anchors, dict):
        return
    seen = set()
    for items in anchors.values():
        for comment in items if isinstance(items, list) else []:
            if not isinstance(comment, dict) or comment.get("status") in ("archived", "resolved_in_version"):
                continue
            request = comment.get("decision_request")
            if not isinstance(request, dict):
                continue
            comment_id = comment.get("id")
            if isinstance(comment_id, str):
                if comment_id in seen:
                    continue
                seen.add(comment_id)
            quality = aggregate["decision_quality"]
            quality["cards"] += 1
            try:
                warnings = decision_warnings(request)
            except (TypeError, ValueError, AttributeError):
                continue
            quality["cards_with_warnings"] += bool(warnings)
            quality["warnings"] += len(warnings)


def _rounds(path: Path, aggregate: dict, since: datetime, until: datetime) -> dict[str, datetime]:
    parents: dict[str, str] = {}
    times: dict[str, datetime] = {}

    def root(key: str) -> str:
        while parents[key] != key:
            parents[key] = parents[parents[key]]
            key = parents[key]
        return key

    for event, timestamp in _events(path):
        in_window = since <= timestamp < until
        kind = event.get("event")
        if in_window:
            aggregate["events"] += 1
            if kind == "decision_requested":
                aggregate["decision_requests"] += 1
            elif kind == "comment_updated":
                author = event.get("author")
                decision = event.get("decision")
                if isinstance(decision, dict):
                    decision = decision.get("verdict")
                if (isinstance(author, str) and author and not author.startswith("agent:")
                        and isinstance(decision, str) and decision):
                    aggregate["reviewer_decisions"] += 1
            elif kind in ("page_published", "version_published"):
                aggregate["publish_successes"] += 1
            elif kind == "page_publish_failed":
                aggregate["publish_failures"] += 1

        if kind != "round_submitted" and not (kind == "session_push" and event.get("round") is True):
            continue
        ids = [event[field] for field in ("round_id", "delivery_id")
               if isinstance(event.get(field), str) and event[field]]
        if not ids:
            if kind == "round_submitted" and in_window:
                aggregate["submitted_rounds"] += 1
                aggregate["legacy_rounds_without_id"] += 1
            continue
        for key in ids:
            if key not in parents:
                parents[key] = key
                times[key] = timestamp
        first = root(ids[0])
        times[first] = min(times[first], timestamp)
        for key in ids[1:]:
            other = root(key)
            if other != first:
                parents[other] = first
                times[first] = min(times[first], times[other])
    roots = {root(key) for key in parents}
    aggregate["submitted_rounds"] += sum(since <= times[key] < until for key in roots)
    return {key: times[root(key)] for key in parents}


def _sample(samples: list[float], submitted: datetime | None, endpoint: datetime | None,
            since: datetime, until: datetime) -> None:
    if submitted is None or endpoint is None or not since <= endpoint < until:
        return
    seconds = (endpoint - submitted).total_seconds()
    if math.isfinite(seconds) and seconds >= 0:
        samples.append(seconds)


def _deliveries(path: Path, aggregate: dict, round_times: dict[str, datetime],
                since: datetime, until: datetime) -> None:
    rows = _read_object(path).get("deliveries")
    if not isinstance(rows, dict):
        return
    for key, row in rows.items():
        if not isinstance(row, dict):
            continue
        state = row.get("state")
        if not isinstance(state, str) or state not in _DELIVERY_STATES:
            continue
        submitted = round_times.get(key) or _parse_timestamp(row.get("created_at"))
        attempted = _parse_timestamp(row.get("attempted_at"))
        accepted = None
        if state in ("started", "accepted", "acknowledged"):
            accepted = _parse_timestamp(row.get("accepted_at"))
            if accepted is None and state in ("started", "accepted"):
                accepted = _parse_timestamp(row.get("updated_at"))
        acknowledged = _parse_timestamp(row.get("acknowledged_at")) if state == "acknowledged" else None
        changed = acknowledged or _parse_timestamp(row.get("updated_at")) or accepted or attempted or submitted
        if changed is not None and since <= changed < until:
            aggregate["deliveries"][state] += 1
        _sample(aggregate["_attempt_seconds"], submitted, attempted, since, until)
        _sample(aggregate["_acceptance_seconds"], submitted, accepted, since, until)
        _sample(aggregate["_acknowledgment_seconds"], submitted, acknowledged, since, until)


def _distribution(values: list[float]) -> dict:
    ordered = sorted(values)

    def percentile(quantile: float) -> float | None:
        if not ordered:
            return None
        position = (len(ordered) - 1) * quantile
        low = int(position)
        high = min(low + 1, len(ordered) - 1)
        return round(ordered[low] + (ordered[high] - ordered[low]) * (position - low), 3)

    return {"samples": len(ordered), "p50": percentile(0.5), "p95": percentile(0.95)}


def _finish(aggregate: dict) -> dict:
    return {
        **{key: aggregate[key] for key in _COUNT_KEYS},
        "deliveries": dict(aggregate["deliveries"]),
        "decision_quality": dict(aggregate["decision_quality"]),
        "submission_to_attempt_seconds": _distribution(aggregate["_attempt_seconds"]),
        "submission_to_acceptance_seconds": _distribution(aggregate["_acceptance_seconds"]),
        "submission_to_acknowledgment_seconds": _distribution(aggregate["_acknowledgment_seconds"]),
    }


def collect_metrics(since: datetime, until: datetime, state_dir: Path | str = STATE_DIR,
                    bus_root: Path | str = BUS_ROOT) -> dict:
    """Collect [since, until) UTC metrics without writing or advancing cursors.

    Naive input datetimes and legacy naive event timestamps mean UTC. Round IDs
    are associated across both submitted and push events, using the earliest
    timestamp so retries cannot count a round in a later window. Latency samples
    use endpoints inside the window and explicit submission timestamps. Accepted
    or started rows use accepted_at, or updated_at when acceptance was recorded.
    Acknowledged rows retain explicit accepted_at samples, but a manual inbox
    read never implies prompt acceptance. Acknowledgment uses acknowledged_at.
    """
    if not isinstance(since, datetime) or not isinstance(until, datetime):
        raise ValueError("since and until must be datetimes")
    since = (since if since.tzinfo else since.replace(tzinfo=UTC)).astimezone(UTC)
    until = (until if until.tzinfo else until.replace(tzinfo=UTC)).astimezone(UTC)
    if since >= until:
        raise ValueError("since must precede until")
    state_dir, bus_root = Path(state_dir), Path(bus_root)
    by_project = {}
    total = _empty()
    for registry_path in sorted(state_dir.glob("*.json")):
        project = registry_path.stem
        if not _SAFE_NAME.fullmatch(project) or project in (".", ".."):
            continue
        slugs = _read_object(registry_path).get("slugs")
        if not isinstance(slugs, dict):
            continue
        aggregate = _empty()
        for slug, record in slugs.items():
            if (not isinstance(slug, str) or not _SAFE_NAME.fullmatch(slug) or slug in (".", "..")
                    or not isinstance(record, dict)):
                continue
            aggregate["active_pages"] += 1
            round_times = _rounds(bus_root / project / f"{slug}.ndjson", aggregate, since, until)
            _deliveries(state_dir / "deliveries" / project / f"{slug}.json", aggregate, round_times, since, until)
            _quality(record.get("slug_dir"), aggregate)
        for key in _COUNT_KEYS:
            total[key] += aggregate[key]
        for section in ("deliveries", "decision_quality"):
            for key, value in aggregate[section].items():
                total[section][key] += value
        for key in ("_attempt_seconds", "_acceptance_seconds", "_acknowledgment_seconds"):
            total[key].extend(aggregate[key])
        by_project[project] = _finish(aggregate)
    return {
        "schema_version": 1,
        "window": {"since": since.isoformat(), "until": until.isoformat()},
        "global": _finish(total),
        "by_project": by_project,
        "limitations": list(_LIMITATIONS),
    }
