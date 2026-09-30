"""Local metrics count recorded activity without consuming or exposing feedback."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agent_annotate.metrics import collect_metrics

_SINCE = datetime(2026, 9, 22, tzinfo=UTC)
_UNTIL = datetime(2026, 9, 29, tzinfo=UTC)


@pytest.fixture
def estate(tmp_path):
    return {"state": tmp_path / "state", "bus": tmp_path / "bus", "pages": tmp_path / "pages"}


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def _add_page(estate, project="proj", slug="demo", comments=None):
    registry_path = estate["state"] / f"{project}.json"
    registry = json.loads(registry_path.read_text()) if registry_path.exists() else {"project": project, "slugs": {}}
    slug_dir = estate["pages"] / project / slug
    registry["slugs"][slug] = {"slug_dir": str(slug_dir)}
    _write(registry_path, registry)
    if comments is not None:
        _write(slug_dir / "comments.json", comments)
    return estate["bus"] / project / f"{slug}.ndjson"


def _event(kind, seconds=60, **fields):
    return {"event": kind, "ts": (_SINCE + timedelta(seconds=seconds)).isoformat(), **fields}


def _bus(path, *events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(event) + "\n" for event in events))


def _collect(estate, since=_SINCE, until=_UNTIL):
    return collect_metrics(since, until, state_dir=estate["state"], bus_root=estate["bus"])


def _journal(estate, rows, project="proj", slug="demo"):
    _write(estate["state"] / "deliveries" / project / f"{slug}.json", {"offset": 27, "deliveries": rows})


def _snapshot(root):
    return {str(path.relative_to(root)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in root.rglob("*") if path.is_file()}


def test_missing_estate_returns_zero_metrics_without_creating_roots(estate):
    result = _collect(estate)
    assert result["global"]["active_pages"] == 0
    assert result["global"]["submitted_rounds"] == 0
    assert result["global"]["submission_to_attempt_seconds"] == {"samples": 0, "p50": None, "p95": None}
    assert result["by_project"] == {}
    assert not estate["state"].exists()
    assert not estate["bus"].exists()


@pytest.mark.parametrize("since, until", [(_UNTIL, _SINCE), (_SINCE, _SINCE), ("2026-09-22", _UNTIL)])
def test_invalid_window_raises(estate, since, until):
    with pytest.raises(ValueError):
        _collect(estate, since, until)


def test_window_is_start_inclusive_end_exclusive_and_normalizes_timezones(estate):
    bus = _add_page(estate)
    _bus(bus,
         _event("decision_requested", -1), _event("decision_requested", 0),
         {"event": "decision_requested", "ts": "2026-09-22T02:00:00+02:00"},
         {"event": "decision_requested", "ts": _UNTIL.isoformat()},
         {"event": "decision_requested", "ts": "invalid"})
    result = _collect(estate, _SINCE.replace(tzinfo=None), _UNTIL)
    assert result["global"]["decision_requests"] == 2
    assert result["global"]["events"] == 2
    assert result["window"] == {"since": _SINCE.isoformat(), "until": _UNTIL.isoformat()}


def test_reviewer_decisions_and_recorded_publish_outcomes(estate):
    bus = _add_page(estate)
    _bus(bus,
         _event("comment_updated", author="reviewer@example.com", decision="select"),
         _event("comment_updated", author="reviewer@example.com", decision={"verdict": "accept"}),
         _event("comment_updated", author="agent:codex", decision="accept"),
         _event("comment_updated", decision="accept"),
         _event("comment_updated", author="reviewer@example.com", decision=""),
         _event("comment_reply", author="reviewer@example.com", decision="accept"),
         _event("session_push", author="reviewer@example.com", decision="accept"),
         _event("page_published"), _event("version_published"), _event("page_publish_failed"))
    metrics = _collect(estate)["global"]
    assert metrics["reviewer_decisions"] == 2
    assert metrics["publish_successes"] == 2
    assert metrics["publish_failures"] == 1
    assert metrics["submitted_rounds"] == 0


def test_round_ids_and_delivery_ids_deduplicate_across_event_types(estate):
    bus = _add_page(estate)
    _bus(bus,
         _event("round_submitted", round_id="round-A", delivery_id="delivery-A"),
         _event("session_push", round=True, delivery_id="delivery-A"),
         _event("round_submitted", round_id="round-A", seconds=120),
         _event("round_submitted", round_id="same-id"),
         _event("session_push", round=True, delivery_id="same-id"),
         _event("session_push", round=True, delivery_id="push-only"),
         _event("session_push", round=False, delivery_id="individual"),
         _event("session_push", round="true", delivery_id="not-a-round"))
    metrics = _collect(estate)["global"]
    assert metrics["submitted_rounds"] == 3
    assert metrics["legacy_rounds_without_id"] == 0


def test_round_retry_does_not_count_again_in_later_window(estate):
    bus = _add_page(estate)
    _bus(bus, _event("round_submitted", seconds=-60, round_id="round-A"),
         _event("session_push", round=True, delivery_id="round-A"))
    assert _collect(estate)["global"]["submitted_rounds"] == 0


def test_old_unidentified_submissions_count_each_record_with_explicit_limitation(estate):
    bus = _add_page(estate)
    _bus(bus, _event("round_submitted"), _event("round_submitted"))
    result = _collect(estate)
    assert result["global"]["submitted_rounds"] == 2
    assert result["global"]["legacy_rounds_without_id"] == 2
    assert any("without an ID" in limitation for limitation in result["limitations"])


def test_delivery_states_and_prompt_latencies_have_finite_nonnegative_samples(estate):
    _add_page(estate)
    submitted = (_SINCE + timedelta(seconds=60)).isoformat()
    rows = {}
    for index, state in enumerate(("started", "accepted", "pending", "uncertain", "superseded")):
        row = {"state": state, "created_at": submitted}
        if state in ("started", "accepted"):
            row["attempted_at"] = (_SINCE + timedelta(seconds=70 + index * 20)).isoformat()
            row["updated_at"] = (_SINCE + timedelta(seconds=80 + index * 20)).isoformat()
        rows[f"delivery-{index}"] = row
    rows["negative"] = {"state": "accepted", "created_at": submitted, "attempted_at": _SINCE.isoformat(),
                        "updated_at": _SINCE.isoformat()}
    rows["invalid"] = {"state": "accepted", "created_at": "invalid", "attempted_at": "invalid"}
    rows["unknown"] = {"state": "unexpected", "created_at": submitted}
    _journal(estate, rows)
    metrics = _collect(estate)["global"]
    assert metrics["deliveries"] == {
        "started": 1, "accepted": 2, "pending": 1, "uncertain": 1, "superseded": 1, "acknowledged": 0,
    }
    assert metrics["submission_to_attempt_seconds"] == {"samples": 2, "p50": 20.0, "p95": 29.0}
    assert metrics["submission_to_acceptance_seconds"] == {"samples": 2, "p50": 30.0, "p95": 39.0}


def test_explicit_submission_join_and_acceptance_timestamp_take_precedence(estate):
    bus = _add_page(estate)
    _bus(bus, _event("round_submitted", round_id="round-A"))
    _journal(estate, {"round-A": {
        "state": "accepted", "created_at": "invalid",
        "attempted_at": (_SINCE + timedelta(seconds=65)).isoformat(),
        "accepted_at": (_SINCE + timedelta(seconds=70)).isoformat(),
        "updated_at": (_SINCE + timedelta(seconds=100)).isoformat(),
    }})
    metrics = _collect(estate)["global"]
    assert metrics["submission_to_attempt_seconds"]["p50"] == 5.0
    assert metrics["submission_to_acceptance_seconds"]["p50"] == 10.0


def test_manual_acknowledgment_does_not_infer_prompt_attempt_or_acceptance(estate):
    bus = _add_page(estate)
    _bus(bus, _event("round_submitted", seconds=0, round_id="round-A"),
         _event("round_received", seconds=30, round_id="round-A", owner_session="private-owner"))
    _journal(estate, {"round-A": {
        "state": "acknowledged", "created_at": _SINCE.isoformat(),
        "updated_at": (_SINCE - timedelta(seconds=10)).isoformat(),
        "acknowledged_at": (_SINCE + timedelta(seconds=30)).isoformat(),
    }})
    result = _collect(estate)
    metrics = result["global"]
    assert metrics["submitted_rounds"] == 1
    assert metrics["deliveries"]["acknowledged"] == 1
    assert metrics["submission_to_attempt_seconds"]["samples"] == 0
    assert metrics["submission_to_acceptance_seconds"]["samples"] == 0
    assert metrics["submission_to_acknowledgment_seconds"] == {"samples": 1, "p50": 30.0, "p95": 30.0}
    assert result["by_project"]["proj"]["submission_to_acknowledgment_seconds"] == metrics["submission_to_acknowledgment_seconds"]
    assert "private-owner" not in json.dumps(result)


def test_accepted_then_acknowledged_preserves_explicit_acceptance_latency(estate):
    _add_page(estate)
    _journal(estate, {"round-A": {
        "state": "acknowledged", "created_at": _SINCE.isoformat(),
        "attempted_at": (_SINCE + timedelta(seconds=5)).isoformat(),
        "accepted_at": (_SINCE + timedelta(seconds=10)).isoformat(),
        "acknowledged_at": (_SINCE + timedelta(seconds=30)).isoformat(),
        "updated_at": (_SINCE + timedelta(seconds=40)).isoformat(),
    }})
    metrics = _collect(estate)["global"]
    assert metrics["deliveries"]["acknowledged"] == 1
    assert metrics["deliveries"]["accepted"] == 0
    assert metrics["submission_to_attempt_seconds"] == {"samples": 1, "p50": 5.0, "p95": 5.0}
    assert metrics["submission_to_acceptance_seconds"] == {"samples": 1, "p50": 10.0, "p95": 10.0}
    assert metrics["submission_to_acknowledgment_seconds"] == {"samples": 1, "p50": 30.0, "p95": 30.0}


@pytest.mark.parametrize("acknowledged_at", ["invalid", (_SINCE - timedelta(seconds=10)).isoformat(), _UNTIL.isoformat()])
def test_acknowledgment_latency_requires_valid_nonnegative_in_window_endpoint(estate, acknowledged_at):
    _add_page(estate)
    _journal(estate, {"round-A": {
        "state": "acknowledged", "created_at": _SINCE.isoformat(), "acknowledged_at": acknowledged_at,
    }})
    metrics = _collect(estate)["global"]
    assert metrics["submission_to_acknowledgment_seconds"]["samples"] == 0
    assert metrics["submission_to_acceptance_seconds"]["samples"] == 0


def test_latency_endpoints_are_windowed_and_do_not_claim_action_completion(estate):
    _add_page(estate)
    _journal(estate, {
        "old-pending": {"state": "pending", "created_at": (_SINCE - timedelta(seconds=60)).isoformat()},
        "later-accepted": {"state": "accepted", "created_at": (_SINCE - timedelta(seconds=30)).isoformat(),
                           "attempted_at": (_SINCE + timedelta(seconds=30)).isoformat(), "updated_at": _UNTIL.isoformat()},
        "uncertain": {"state": "uncertain", "created_at": _SINCE.isoformat(),
                      "attempted_at": (_SINCE + timedelta(seconds=10)).isoformat(),
                      "updated_at": (_SINCE + timedelta(seconds=20)).isoformat()},
    })
    result = _collect(estate)
    assert result["global"]["deliveries"]["accepted"] == 0
    assert result["global"]["deliveries"]["pending"] == 0
    assert result["global"]["deliveries"]["uncertain"] == 1
    assert result["global"]["submission_to_attempt_seconds"]["samples"] == 2
    assert result["global"]["submission_to_acceptance_seconds"]["samples"] == 0
    assert any("do not prove agent action completion" in text for text in result["limitations"])


def test_quality_uses_packaged_warnings_without_returning_prompt_text(estate):
    bad_request = {"prompt": "Which option should we choose? Reply with option letter A/B.",
                   "options": [{"id": "comment"}]}
    bad = {"id": "bad", "status": "open", "decision_request": bad_request}
    good = {"id": "good", "decision_request": {"prompt": "Choose one", "options": [{"id": "A"}, {"id": "B"}]}}
    comments = {"anchors": {"s:one": [bad, good], "s:two": [bad, {**bad, "id": "closed", "status": "archived"}]},
                "archived": {"s:old": [{**bad, "id": "old"}]}}
    _add_page(estate, comments=comments)
    result = _collect(estate)
    assert result["global"]["decision_quality"] == {"cards": 2, "cards_with_warnings": 1, "warnings": 2}
    assert bad_request["prompt"] not in json.dumps(result)


def test_project_and_slug_isolation_and_global_percentiles_use_all_samples(estate):
    for project, seconds in (("alpha", 10), ("beta", 30)):
        bus = _add_page(estate, project=project)
        _bus(bus, _event("round_submitted", seconds=0, round_id="same-local-id"))
        _journal(estate, {"same-local-id": {"state": "accepted", "created_at": _SINCE.isoformat(),
                                          "attempted_at": (_SINCE + timedelta(seconds=seconds)).isoformat(),
                                          "updated_at": (_SINCE + timedelta(seconds=seconds)).isoformat()}}, project=project)
    result = _collect(estate)
    assert result["global"]["active_pages"] == 2
    assert result["global"]["submitted_rounds"] == 2
    assert result["global"]["submission_to_attempt_seconds"] == {"samples": 2, "p50": 20.0, "p95": 29.0}
    assert result["by_project"]["alpha"]["submission_to_attempt_seconds"]["p50"] == 10.0
    assert result["by_project"]["beta"]["submission_to_attempt_seconds"]["p50"] == 30.0


def test_only_active_top_level_registries_are_scanned(estate):
    _add_page(estate)
    _write(estate["state"] / "retired" / "retired.json", {"slugs": {"old": {}}})
    _bus(estate["bus"] / "retired" / "old.ndjson", _event("decision_requested"))
    _write(estate["state"] / "config.json", {"private": "not a registry"})
    result = _collect(estate)
    assert result["global"]["active_pages"] == 1
    assert result["global"]["decision_requests"] == 0
    assert set(result["by_project"]) == {"proj"}


def test_malformed_and_incomplete_inputs_are_ignored(estate):
    bus = _add_page(estate, comments={"anchors": {"s:a": [None, {"decision_request": {"options": 3}}]}})
    bus.parent.mkdir(parents=True)
    bus.write_bytes(b"{bad}\nnull\n42\n\xff\n" + json.dumps(_event("decision_requested")).encode() + b"\n"
                    + json.dumps(_event("round_submitted")).encode())
    (estate["state"] / "broken.json").write_text("{bad")
    _write(estate["state"] / "wrong.json", {"slugs": []})
    _journal(estate, {"bad": None, "malformed": {"state": ["pending"]}})
    result = _collect(estate)
    assert result["global"]["decision_requests"] == 1
    assert result["global"]["submitted_rounds"] == 0
    assert result["global"]["active_pages"] == 1


def test_metrics_never_write_consume_cursors_read_transcripts_or_expose_private_data(estate, tmp_path, monkeypatch):
    secret = "private reviewer text reviewer@example.com session-private /private/path"
    bus = _add_page(estate, comments={"anchors": {"s:a": [{"id": "card", "text": secret,
                "decision_request": {"prompt": secret, "options": [{"id": "comment"}]}}]}})
    _bus(bus, _event("comment_updated", author="reviewer@example.com", decision="comment", text=secret),
         _event("round_submitted", round_id="round", note=secret))
    _journal(estate, {"round": {"state": "pending", "created_at": _SINCE.isoformat(), "detail": secret,
                               "target": {"session": "session-private"}, "receipt": {"text": secret}}})
    cursors = [estate["state"] / "bus-offsets" / "demo.offset", estate["state"] / "hook-offsets" / "demo.offset",
               estate["state"] / "monitors" / "proj" / "demo" / "owner.json", tmp_path / "transcripts" / "session.jsonl"]
    for cursor in cursors:
        _write(cursor, {"private": secret, "offset": 99})
    before = _snapshot(tmp_path)
    opened = []
    original_open = Path.open

    def track_open(path, *args, **kwargs):
        opened.append(path)
        return original_open(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", track_open)
        result = _collect(estate)
        assert _collect(estate) == result
    assert all(cursor not in opened for cursor in cursors)
    assert _snapshot(tmp_path) == before
    serialized = json.dumps(result)
    assert secret not in serialized
    assert "reviewer@example.com" not in serialized
    assert "session-private" not in serialized
    assert "/private/path" not in serialized
