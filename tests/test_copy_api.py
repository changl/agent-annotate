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


def _seed_draft(directory):
    save_copy(directory, {"schema_version": 1, "blocks": [{"id": "hero", "title": "Hero", "current": "r1", "status": "needs_you",
        "revisions": [{"id": "r1", "created_at": "2026-10-02T00:00:00+00:00", "author": {"id": "agent:builder"},
                       "status": "approved", "delta": {"ops": [{"insert": "Approved headline\n"}]}},
                      {"id": "r2", "created_at": "2026-10-03T00:00:00+00:00", "author": {"id": "agent:builder"},
                       "status": "draft", "delta": {"ops": [{"insert": "Draft headline\n"}]}}]}]})


def test_approve_a_draft_in_one_action_goes_out_with_send_as_an_approval(server):
    httpd, directory, bus = server
    _seed_draft(directory)
    body = {"revision_id": "r2", "request_id": str(uuid.uuid4())}
    assert _call(httpd, "POST", "/api/copy/hero/approve", body, author="agent:builder")[0] == 403
    assert _call(httpd, "POST", "/api/copy/hero/approve", {"revision_id": "r1", "request_id": str(uuid.uuid4())},
                 author="reviewer@example.com")[0] == 409
    assert _call(httpd, "POST", "/api/copy/hero/approve", dict(body, delta={"ops": []}), author="reviewer@example.com")[0] == 400
    for _ in range(2):
        status, result = _call(httpd, "POST", "/api/copy/hero/approve", body, author="reviewer@example.com")
        assert status == 200
    block = result["blocks"][0]
    assert block["current"] == "r_" + body["request_id"] and block["status"] == "done" and len(block["revisions"]) == 3
    assert _events(bus, "session_push") == []
    status, result = _call(httpd, "POST", "/api/rounds/submit", {}, author="reviewer@example.com")
    assert status == 200 and result["edit_count"] == 1
    edit = _events(bus, "session_push")[0]["edits"][0]
    assert edit["status"] == "approved" and edit["base_revision"] == "r2" and edit["delta"] == {"ops": [{"insert": "Draft headline\n"}]}
    assert load_copy(directory)["blocks"][0]["revisions"][-1]["round_pending"] is False


def test_edit_approved_copy_then_approve_and_discard_restores_the_block(server):
    httpd, directory, _ = server
    _seed_draft(directory)
    before = load_copy(directory)
    approval = {"revision_id": "r2", "request_id": str(uuid.uuid4())}
    assert _call(httpd, "POST", "/api/copy/hero/approve", approval, author="reviewer@example.com")[0] == 200
    edit = {"delta": {"ops": [{"insert": "Edited headline\n"}]}, "base_revision": "r_" + approval["request_id"],
            "request_id": str(uuid.uuid4())}
    assert _call(httpd, "POST", "/api/copy/hero/revisions", edit, author="reviewer@example.com")[0] == 200
    status, result = _call(httpd, "POST", "/api/copy/hero/approve", {"revision_id": "r_" + edit["request_id"],
                                                                      "request_id": str(uuid.uuid4())}, author="reviewer@example.com")
    assert status == 200
    block = result["blocks"][0]
    assert [r["status"] for r in block["revisions"]] == ["approved", "draft", "approved", "proposed", "approved"]
    assert block["current"] == block["revisions"][-1]["id"]
    status, result = _call(httpd, "POST", "/api/rounds/discard", {}, author="reviewer@example.com")
    assert status == 200 and result["edit_count"] == 3
    assert load_copy(directory) == before


def test_two_reviewers_discard_never_sends_the_discarded_approval(server):
    # Review P1-2 over HTTP: A's discarded approval stays only as the revision
    # B's approval replaced, and A's next Send does not deliver it.
    httpd, directory, bus = server
    _seed_draft(directory)
    a = {"revision_id": "r2", "request_id": str(uuid.uuid4())}
    assert _call(httpd, "POST", "/api/copy/hero/approve", a, author="a@example.com")[0] == 200
    document = load_copy(directory)
    document["blocks"][0]["revisions"].append({"id": "r3", "created_at": "2026-10-04T00:00:00+00:00", "author": {"id": "agent:builder"},
                                               "status": "draft", "delta": {"ops": [{"insert": "Newer headline\n"}]}})
    document["blocks"][0]["status"] = "needs_you"
    save_copy(directory, document)
    assert _call(httpd, "POST", "/api/copy/hero/approve", {"revision_id": "r3", "request_id": str(uuid.uuid4())},
                 author="b@example.com")[0] == 200
    status, result = _call(httpd, "POST", "/api/rounds/discard", {}, author="a@example.com")
    assert status == 200 and result["edit_count"] == 0
    assert not any(r.get("round_pending") and r["author"]["id"] == "a@example.com" for r in load_copy(directory)["blocks"][0]["revisions"])
    assert _call(httpd, "POST", "/api/rounds/submit", {"note": "Unrelated feedback"}, author="a@example.com")[0] == 200
    sent = [edit for event in _events(bus, "session_push") for edit in event.get("edits", [])]
    assert not any(edit["revision_id"] == "r_" + a["request_id"] for edit in sent)


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
