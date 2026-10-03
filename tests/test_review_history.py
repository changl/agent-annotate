"""Round history keeps actual answers across corrections, copies and bus pruning."""
import json

from test_decision_api import _call, _card, _events, _store
from test_decision_api import server as server

from agent_annotate.review_history import review_history, save_round


def test_submitted_snapshot_is_immutable_and_drafts_stay_unsubmitted(server):
    httpd, directory, bus = server
    _, card = _call(httpd, "POST", "/api/comments", _card(prompt="CHA-1: ship?"))
    _call(httpd, "POST", f"/api/comments/{card['id']}/decision", {"verdict": "accept", "text": "Only the tested change", "defer_push": True}, author="r@example.com")
    assert _call(httpd, "GET", "/api/history")[1]["rounds"] == []
    _, submitted = _call(httpd, "POST", "/api/rounds/submit", {"version": "v1"}, author="r@example.com")
    status, first = _call(httpd, "GET", "/api/history")
    assert status == 200 and len(first["rounds"]) == 1
    answer = first["rounds"][0]["answers"][0]
    assert answer["verdict"] == "accept" and answer["text"] == "Only the tested change"
    assert answer["prompt"] == "CHA-1: ship?"
    assert first["rounds"][0]["version"] == "v1"
    _call(httpd, "POST", f"/api/comments/{card['id']}/decision", {"verdict": "comment", "text": "Hold it instead", "defer_push": True}, author="r@example.com")
    assert _call(httpd, "GET", "/api/history")[1] == first
    bus.unlink()  # The page-local snapshot survives moving the bus away.
    assert _call(httpd, "GET", "/api/history")[1] == first
    store = _store(directory)
    assert store["anchors"]["s:a"][0]["decision"]["round_pending"] is True
    assert submitted["comment_count"] == 1


def test_history_read_does_not_mutate_comments_meta_or_pending_answers(server):
    httpd, directory, _ = server
    originals = {name: (directory / name).read_bytes() for name in ("comments.json", "current.meta.json")}
    assert _call(httpd, "GET", "/api/history")[0] == 200
    assert originals == {name: (directory / name).read_bytes() for name in originals}


def test_unknown_review_document_is_rejected_without_submitting(server):
    httpd, directory, bus = server
    _, card = _call(httpd, "POST", "/api/comments", _card())
    _call(httpd, "POST", f"/api/comments/{card['id']}/decision", {"verdict": "accept", "defer_push": True}, author="r@example.com")
    assert _call(httpd, "POST", "/api/rounds/submit", {"version": "v999"}, author="r@example.com")[0] == 400
    assert _events(bus, "round_submitted") == []
    assert not (directory / "rounds.ndjson").exists()
    assert _store(directory)["anchors"]["s:a"][0]["decision"]["round_pending"] is True


def test_legacy_round_uses_historical_choice_not_latest_or_pending(tmp_path):
    (tmp_path / "current.meta.json").write_text(json.dumps({"current": "v2", "history": [
        {"version": "v1", "ts": "2026-09-01T00:00:00Z"}, {"version": "v2", "ts": "2026-09-03T00:00:00Z"}]}))
    (tmp_path / "comments.json").write_text(json.dumps({"anchors": {"d:q1": [{"id": "q", "number": 1,
        "decision_history": [{"verdict": "reject", "text": "Earlier answer", "ts": "2026-09-02T00:00:00Z"}],
        "decision": {"verdict": "accept", "text": "Later draft", "round_pending": True, "ts": "2026-09-04T00:00:00Z"}}]}}))
    bus = tmp_path / "project/page.ndjson"
    bus.parent.mkdir()
    bus.write_text(json.dumps({"event": "round_submitted", "round_id": "one", "ts": "2026-09-02T00:01:00Z", "comment_ids": ["q"]}) + "\n")
    history = review_history(tmp_path, bus)
    assert history["rounds"][0]["version"] == "v1"
    assert history["rounds"][0]["answers"][0]["text"] == "Earlier answer"
    assert history["rounds"][0]["answers"][0]["prompt"] == ""  # Never invent an old prompt from the current question.
    archive = tmp_path / "archive/20261002/project"
    archive.mkdir(parents=True)
    bus.rename(archive / bus.name)
    assert review_history(tmp_path, bus, tmp_path / "archive") == history


def test_round_copy_and_retry_preserve_first_snapshot(tmp_path):
    (tmp_path / "current.meta.json").write_text('{"history": []}')
    first = {"id": "one", "ts": "2026-09-02T00:01:00Z", "answers": [{"text": "Original"}]}
    save_round(tmp_path, first)
    save_round(tmp_path, {**first, "answers": [{"text": "Changed"}]})
    assert review_history(tmp_path)["rounds"] == [first]


def test_versions_use_saved_files_and_ignore_path_injection(tmp_path):
    (tmp_path / "current.meta.json").write_text(json.dumps({"current": "v1", "history": [
        {"version": "v1", "label": "Original"}, {"version": "v2"}, {"version": "../outside"}]}))
    (tmp_path / "versions").mkdir()
    (tmp_path / "versions/v1.html").write_text('Original document')
    versions = review_history(tmp_path)["versions"]
    assert len(versions) == 2 and versions[0]["available"] and not versions[1]["available"]
    outside = tmp_path.parent / "outside.html"
    outside.write_text("Outside the review")
    (tmp_path / "versions/v2.html").symlink_to(outside)
    assert review_history(tmp_path)["versions"][1]["available"] is False


def test_sent_plain_feedback_has_a_stable_historical_snapshot(server):
    httpd, directory, _ = server
    _, comment = _call(httpd, "POST", "/api/comments", {"anchor_id": "s:home", "text": "Tighten the spacing"}, author="r@example.com")
    assert _call(httpd, "POST", "/api/push-session", {}, author="r@example.com")[0] == 200
    history = _call(httpd, "GET", "/api/history")[1]
    assert history["rounds"][0]["answers"][0]["text"] == "Tighten the spacing"
    assert history["rounds"][0]["answers"][0]["verdict"] == "comment"
    _call(httpd, "PUT", f"/api/comments/{comment['id']}", {"text": "Changed later"}, author="r@example.com")
    assert _call(httpd, "GET", "/api/history")[1] == history
