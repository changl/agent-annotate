"""Real HTTP copy persistence, identity and owner-outbox behavior."""
import uuid

from test_decision_api import _call, _card, _events, _store
from test_decision_api import server as server

from agent_annotate.copy_state import load_copy, save_copy


def _seed(directory):
    save_copy(directory, {"schema_version": 1, "blocks": [{"id": "hero", "title": "Hero", "current": "r1",
        "revisions": [{"id": "r1", "created_at": "2026-10-02T00:00:00+00:00", "author": {"id": "agent:builder", "name": "Builder"},
        "status": "draft", "delta": {"ops": [{"insert": "Current headline\n"}]}}]}]})


def test_copy_proposal_retry_preserves_current_and_waits_for_shared_send(server):
    httpd, directory, bus = server
    _seed(directory)
    body = {"delta": {"ops": [{"insert": "Proposed headline\n", "attributes": {"bold": True}}]},
            "base_revision": "r1", "request_id": str(uuid.uuid4())}
    for _ in range(2):
        status, result = _call(httpd, "POST", "/api/copy/hero/proposal", body, author="reviewer@example.com")
        assert status == 200
        assert result["blocks"][0]["current"] == "r1"
        assert len(result["blocks"][0]["revisions"]) == 2
    revision = load_copy(directory)["blocks"][0]["revisions"][-1]
    assert revision["author"]["id"] == "reviewer@example.com"
    assert revision["round_pending"] is True
    assert _events(bus, "session_push") == []
    assert _store(directory)["anchors"] == {}
    status, result = _call(httpd, "POST", "/api/rounds/submit", {}, author="reviewer@example.com")
    assert status == 200 and result["edit_count"] == 1
    pushes = _events(bus, "session_push")
    assert len(pushes) == 1 and pushes[0]["automatic_delivery"] is True
    assert pushes[0]["comment_count"] == 0 and len(pushes[0]["edits"]) == 1
    assert load_copy(directory)["blocks"][0]["revisions"][-1]["round_pending"] is False
    status, result = _call(httpd, "POST", "/api/push-session", {}, author="reviewer@example.com")
    assert status == 200 and result["flagged_count"] == 0
    assert len(_events(bus, "session_push")) == 1


def test_copy_api_rejects_html_embeds_and_identity_spoof(server):
    httpd, directory, _ = server
    _seed(directory)
    body = {"delta": {"ops": [{"insert": {"image": "https://example.com/x"}}]},
            "base_revision": "r1", "request_id": str(uuid.uuid4())}
    assert _call(httpd, "POST", "/api/copy/hero/proposal", body, author="reviewer@example.com")[0] == 400
    body["delta"] = {"ops": [{"insert": "Safe\n"}]}
    body["author"] = {"id": "someone-else@example.com"}
    assert _call(httpd, "POST", "/api/copy/hero/proposal", body, author="reviewer@example.com")[0] == 400
    assert len(load_copy(directory)["blocks"][0]["revisions"]) == 1


def test_send_feedback_skips_unanswered_questions_and_other_reviewer_drafts(server):
    httpd, _, bus = server
    status, question = _call(httpd, "POST", "/api/comments", _card())
    assert status == 201
    _call(httpd, "POST", f"/api/comments/{question['id']}/decision", {"verdict": "comment", "reason": "Pending", "defer_push": True}, author="other@example.com")
    status, result = _call(httpd, "POST", "/api/push-session", {}, author="reviewer@example.com")
    assert status == 200 and result["flagged_count"] == 0
    assert _events(bus, "session_push") == []
    status, feedback = _call(httpd, "POST", "/api/comments", {"anchor_id": "s:home", "text": "Tighten spacing"}, author="reviewer@example.com")
    assert status == 201
    status, result = _call(httpd, "POST", "/api/push-session", {}, author="reviewer@example.com")
    assert status == 200 and result["comment_ids"] == [feedback["id"]]
    pushes = _events(bus, "session_push")
    assert len(pushes) == 1 and pushes[0]["automatic_delivery"] is True
    assert pushes[0]["round"] is True
    assert _call(httpd, "POST", "/api/push-session", {}, author="reviewer@example.com")[1]["flagged_count"] == 0
    assert len(_events(bus, "session_push")) == 1


def test_ui3_edit_or_restore_on_an_older_revision_is_a_409(server):
    httpd, directory, _ = server
    _seed(directory)
    first = {"delta": {"ops": [{"insert": "A\n"}]}, "base_revision": "r1", "request_id": str(uuid.uuid4())}
    assert _call(httpd, "POST", "/api/copy/hero/revisions", first, author="reviewer@example.com")[0] == 200
    stale = {"delta": {"ops": [{"insert": "B\n"}]}, "base_revision": "r1", "request_id": str(uuid.uuid4())}
    status, result = _call(httpd, "POST", "/api/copy/hero/revisions", stale, author="other@example.com")
    assert status == 409 and "newer revision" in result["error"]
    restore = {"revision_id": "r1", "request_id": str(uuid.uuid4()), "base_revision": "r1"}
    assert _call(httpd, "POST", "/api/copy/hero/restore", restore, author="other@example.com")[0] == 409
    assert len(load_copy(directory)["blocks"][0]["revisions"]) == 2
    # Clients that send the latest base, or an old Restore without one, are unaffected.
    restore["base_revision"] = "r_" + first["request_id"]
    assert _call(httpd, "POST", "/api/copy/hero/restore", restore, author="other@example.com")[0] == 200
    old = {"revision_id": "r1", "request_id": str(uuid.uuid4())}
    assert _call(httpd, "POST", "/api/copy/hero/restore", old, author="other@example.com")[0] == 200
    assert len(load_copy(directory)["blocks"][0]["revisions"]) == 4
