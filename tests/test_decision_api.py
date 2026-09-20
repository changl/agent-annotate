"""The v2.19 decision API: cards created in one call, oversize rejected loudly,
batches idempotent by anchor, and a review round that emits exactly one push.

Each of these replaced a measured failure: a create that silently dropped
decision_request, a 2048-byte cap that dropped the request and still answered
200, hand-rolled curl loops for rounds, and one session_push per click so a
session reacted to the first verdict of a ten-card round.
"""

import http.client
import http.server
import json
import threading
from pathlib import Path

import pytest

from agent_annotate.sync_server import make_handler


@pytest.fixture
def server(tmp_path):
    slug_dir = tmp_path / "review"
    slug_dir.mkdir()
    (slug_dir / "comments.json").write_text(
        json.dumps({"schema_version": 2, "anchors": {}, "archived": {}}), encoding="utf-8")
    (slug_dir / "current.meta.json").write_text(
        json.dumps({"current": "v1", "history": [{"version": "v1", "label": "initial"}]}),
        encoding="utf-8")
    bus_dir = tmp_path / "bus"
    handler = make_handler(artifact_dir=slug_dir, public_base_path="", slug="review",
                           bus_dir=bus_dir, v2_mode=True)
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, slug_dir, bus_dir / "review.ndjson"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def _call(httpd, method, path, body=None, author="agent:test", session=None):
    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=3)
    headers = {"Cf-Access-Authenticated-User-Email": author}
    if session:
        headers["X-Annotate-Session"] = session
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=payload, headers=headers)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    try:
        return resp.status, json.loads(raw)
    except ValueError:
        return resp.status, raw


def _events(bus_file: Path, name=None):
    if not bus_file.exists():
        return []
    out = [json.loads(line) for line in bus_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [e for e in out if name is None or e.get("event") == name]


def _store(slug_dir: Path) -> dict:
    return json.loads((slug_dir / "comments.json").read_text(encoding="utf-8"))


def _card(anchor="s:a", prompt="Rename?", **extra):
    dr = {"prompt": prompt, "context": "because", "recommendation": "accept",
          "options": [{"id": "accept", "label": "Yes", "consequence": "one week"},
                      {"id": "reject", "label": "No", "consequence": "stays"}],
          "impact": "medium", "blocking": True}
    dr.update(extra)
    return {"anchor_id": anchor, "text": prompt, "decision_request": dr}


# ── capabilities ──────────────────────────────────────────────────────────

def test_capabilities_advertise_batch_and_rounds(server):
    httpd, _, _ = server
    status, caps = _call(httpd, "GET", "/api/capabilities")
    assert status == 200
    assert caps["batch"] is True and caps["rounds"] is True
    assert caps["decision_schema"] == 2
    assert caps["decision_request_cap"] == 8192
    # D2/D3: the chrome renders exactly the verdicts the server names here.
    assert caps["verdicts"] == ["accept", "reject", "changes", "comment", "select"]


# ── create with decision_request ──────────────────────────────────────────

def test_create_accepts_decision_request_in_one_call(server):
    httpd, slug_dir, bus = server
    status, comment = _call(httpd, "POST", "/api/comments", _card(), session="sess-1")

    assert status == 201
    assert comment["decision_request"]["prompt"] == "Rename?"
    assert comment["decision_request"]["requested_at"]  # server-set
    stored = _store(slug_dir)["anchors"]["s:a"][0]
    assert stored["decision_request"]["context"] == "because"

    created = _events(bus, "comment_created")
    assert created and created[0]["decision_requested"] is True
    assert created[0]["session_id"] == "sess-1"
    requested = _events(bus, "decision_requested")
    assert requested and requested[0]["comment_id"] == comment["id"]
    assert requested[0]["has_context"] is True and requested[0]["options_n"] == 2


def test_create_without_prompt_is_a_400(server):
    httpd, slug_dir, _ = server
    status, err = _call(httpd, "POST", "/api/comments",
                        {"anchor_id": "s:a", "text": "x", "decision_request": {"context": "c"}})
    assert status == 400
    assert "prompt" in err["error"]
    assert _store(slug_dir)["anchors"] == {}


def test_oversize_decision_request_is_413_and_writes_nothing(server):
    httpd, slug_dir, bus = server
    status, err = _call(httpd, "POST", "/api/comments", _card(context="x" * 9000))
    assert status == 413
    assert "8192" in err["error"]
    assert _store(slug_dir)["anchors"] == {}
    assert _events(bus) == []


def test_put_oversize_decision_request_is_413_and_keeps_the_old_card(server):
    httpd, slug_dir, _ = server
    _, comment = _call(httpd, "POST", "/api/comments", _card())
    status, _ = _call(httpd, "PUT", f"/api/comments/{comment['id']}",
                      {"decision_request": {"prompt": "p", "context": "y" * 9000}})
    assert status == 413
    assert _store(slug_dir)["anchors"]["s:a"][0]["decision_request"]["prompt"] == "Rename?"


def test_put_null_clears_the_card(server):
    httpd, slug_dir, _ = server
    _, comment = _call(httpd, "POST", "/api/comments", _card())
    status, _ = _call(httpd, "PUT", f"/api/comments/{comment['id']}", {"decision_request": None})
    assert status == 200
    assert "decision_request" not in _store(slug_dir)["anchors"]["s:a"][0]


# ── batch ─────────────────────────────────────────────────────────────────

def test_batch_is_idempotent_by_anchor(server):
    httpd, slug_dir, bus = server
    items = [_card("s:a", "A?"), _card("s:b", "B?")]

    status, first = _call(httpd, "POST", "/api/comments/batch",
                          {"items": items, "idempotency": "anchor"})
    assert status == 200
    assert first["created"] == 2 and first["updated"] == 0

    items[0]["text"] = "A, revised?"
    items[0]["decision_request"]["prompt"] = "A, revised?"
    status, second = _call(httpd, "POST", "/api/comments/batch",
                           {"items": items, "idempotency": "anchor"})
    assert status == 200
    assert second["created"] == 0 and second["updated"] == 2
    assert second["ids"] == first["ids"]

    anchors = _store(slug_dir)["anchors"]
    assert len(anchors["s:a"]) == 1 and len(anchors["s:b"]) == 1
    assert anchors["s:a"][0]["decision_request"]["prompt"] == "A, revised?"

    seeded = _events(bus, "comments_seeded")
    assert [(e["created"], e["updated"]) for e in seeded] == [(2, 0), (0, 2)]
    assert len(_events(bus, "decision_requested")) == 4


def test_batch_without_idempotency_duplicates(server):
    httpd, slug_dir, _ = server
    _call(httpd, "POST", "/api/comments/batch", {"items": [_card()]})
    _call(httpd, "POST", "/api/comments/batch", {"items": [_card()]})
    assert len(_store(slug_dir)["anchors"]["s:a"]) == 2


def test_batch_is_all_or_nothing(server):
    httpd, slug_dir, bus = server
    items = [_card("s:a"), _card("s:b", context="z" * 9000)]
    status, err = _call(httpd, "POST", "/api/comments/batch", {"items": items, "idempotency": "anchor"})
    assert status == 413
    assert _store(slug_dir)["anchors"] == {}
    assert _events(bus) == []


def test_batch_rejects_a_bad_item_with_its_index(server):
    httpd, _, _ = server
    status, err = _call(httpd, "POST", "/api/comments/batch",
                        {"items": [_card(), {"text": "no anchor"}]})
    assert status == 400
    assert "items[1]" in err["error"]


# ── rounds ────────────────────────────────────────────────────────────────

def test_deferred_verdicts_then_submit_emit_exactly_one_session_push(server):
    httpd, slug_dir, bus = server
    _, batch = _call(httpd, "POST", "/api/comments/batch",
                     {"items": [_card("s:a"), _card("s:b"), _card("s:c")], "idempotency": "anchor"})
    a, b, c = batch["ids"]

    status, resp = _call(httpd, "POST", f"/api/comments/{a}/decision",
                         {"verdict": "accept", "defer_push": True}, author="reviewer@example.com")
    assert status == 200
    assert resp["delivery"] == "deferred"
    assert resp["decision"]["round_pending"] is True
    assert resp["decision"]["latency_s"] is not None
    _call(httpd, "POST", f"/api/comments/{b}/decision",
          {"verdict": "reject", "defer_push": True, "text": "not yet"}, author="reviewer@example.com")

    assert _events(bus, "session_push") == []
    updated = [e for e in _events(bus, "comment_updated") if e.get("decision")]
    assert all(e["deferred"] is True for e in updated)
    assert {e["decision"] for e in updated} == {"accept", "reject"}

    status, submitted = _call(httpd, "POST", "/api/rounds/submit", {"note": "round 1"},
                              author="reviewer@example.com")
    assert status == 200
    assert submitted["comment_count"] == 2
    assert submitted["verdict_counts"] == {
        "accept": 1, "reject": 1, "changes": 0, "comment": 0, "select": 0}
    assert submitted["undecided_ids"] == [c]

    pushes = _events(bus, "session_push")
    assert len(pushes) == 1
    assert pushes[0]["round"] is True
    assert sorted(pushes[0]["comment_ids"]) == sorted([a, b])
    assert pushes[0]["note"] == "round 1"
    rounds = _events(bus, "round_submitted")
    assert len(rounds) == 1 and rounds[0]["by"] == "reviewer@example.com"

    for cid in (a, b):
        stored = next(x for items in _store(slug_dir)["anchors"].values() for x in items if x["id"] == cid)
        assert "round_pending" not in stored["decision"]
        assert stored["flagged_for_session"] is True


def test_discard_clears_pending_without_a_push(server):
    httpd, slug_dir, bus = server
    _, comment = _call(httpd, "POST", "/api/comments", _card())
    _call(httpd, "POST", f"/api/comments/{comment['id']}/decision",
          {"verdict": "accept", "defer_push": True}, author="reviewer@example.com")

    status, resp = _call(httpd, "POST", "/api/rounds/discard", {}, author="reviewer@example.com")
    assert status == 200
    assert resp["comment_ids"] == [comment["id"]]
    assert _events(bus, "session_push") == []
    assert len(_events(bus, "round_discarded")) == 1
    stored = _store(slug_dir)["anchors"]["s:a"][0]
    assert stored["decision"]["verdict"] == "accept"
    assert "round_pending" not in stored["decision"]


def test_an_immediate_verdict_still_pushes_as_before(server):
    """Legacy chrome never sends defer_push; its behaviour is unchanged."""
    httpd, _, bus = server
    _, comment = _call(httpd, "POST", "/api/comments", _card())
    status, resp = _call(httpd, "POST", f"/api/comments/{comment['id']}/decision",
                         {"verdict": "accept"}, author="reviewer@example.com")
    assert status == 200
    assert resp["delivery"] == "queued"
    pushes = _events(bus, "session_push")
    assert len(pushes) == 1 and pushes[0]["comment_ids"] == [comment["id"]]


def test_send_now_leaves_the_round(server):
    httpd, slug_dir, bus = server
    _, comment = _call(httpd, "POST", "/api/comments", _card())
    _call(httpd, "POST", f"/api/comments/{comment['id']}/decision",
          {"verdict": "accept", "defer_push": True}, author="reviewer@example.com")
    status, _ = _call(httpd, "POST", f"/api/comments/{comment['id']}/push", {},
                      author="reviewer@example.com")
    assert status == 200
    assert "round_pending" not in _store(slug_dir)["anchors"]["s:a"][0]["decision"]
    assert len(_events(bus, "session_push")) == 1
    _, submitted = _call(httpd, "POST", "/api/rounds/submit", {}, author="reviewer@example.com")
    assert submitted["comment_count"] == 0


# ── D2: the "changes" verdict ─────────────────────────────────────────────

def test_request_changes_records_the_verdict_and_keeps_the_card_open(server):
    """D2 replaced "Comment" with "Request changes": the note is mandatory,
    the card stays open, and the auto reply names the verdict so a session
    reading the thread sees an instruction, not an anonymous remark."""
    httpd, slug_dir, bus = server
    _, comment = _call(httpd, "POST", "/api/comments", _card())
    status, resp = _call(httpd, "POST", f"/api/comments/{comment['id']}/decision",
                         {"verdict": "changes", "text": "split step 3 in two"},
                         author="reviewer@example.com")

    assert status == 200
    assert resp["decision"]["verdict"] == "changes"
    assert resp["decision"]["text"] == "split step 3 in two"
    assert resp["status"] == "open"
    assert resp["replies"][-1]["text"] == "↻ Changes requested: split step 3 in two"

    stored = _store(slug_dir)["anchors"]["s:a"][0]
    assert stored["decision"]["verdict"] == "changes"

    updated = _events(bus, "comment_updated")
    assert updated[-1]["decision"] == "changes"
    assert updated[-1]["new_status"] == "open"
    assert _events(bus, "session_push")[-1]["decision"] == "changes"


def test_request_changes_without_text_is_a_400_and_writes_nothing(server):
    httpd, slug_dir, bus = server
    _, comment = _call(httpd, "POST", "/api/comments", _card())
    before = len(_events(bus))
    status, err = _call(httpd, "POST", f"/api/comments/{comment['id']}/decision",
                        {"verdict": "changes", "text": "   "})
    assert status == 400
    assert "text required for changes verdict" in err["error"]
    assert "decision" not in _store(slug_dir)["anchors"]["s:a"][0]
    assert len(_events(bus)) == before


def test_a_comment_verdict_is_labelled_in_the_thread(server):
    """D3: `comment` is a remark, not an answer. Its reply is prefixed, so it
    reads as a comment in the thread instead of an anonymous reply — the very
    thing that made these remarks easy to miss."""
    httpd, slug_dir, _ = server
    _, comment = _call(httpd, "POST", "/api/comments", _card())
    status, resp = _call(httpd, "POST", f"/api/comments/{comment['id']}/decision",
                         {"verdict": "comment", "text": "old chrome"})
    assert status == 200
    assert resp["decision"]["verdict"] == "comment"
    assert resp["replies"][-1]["text"] == "💬 Comment: old chrome"
    assert _store(slug_dir)["anchors"]["s:a"][0]["status"] == "open"


def test_a_comment_rides_the_round_but_stays_undecided(server):
    """D3: a commented card is pushed with the round AND reported undecided."""
    httpd, slug_dir, bus = server
    _, batch = _call(httpd, "POST", "/api/comments/batch",
                     {"items": [_card("s:a"), _card("s:b")], "idempotency": "anchor"})
    a, b = batch["ids"]
    _call(httpd, "POST", f"/api/comments/{a}/decision",
          {"verdict": "comment", "text": "needs the client's read first", "defer_push": True},
          author="reviewer@example.com")
    _call(httpd, "POST", f"/api/comments/{b}/decision",
          {"verdict": "accept", "defer_push": True}, author="reviewer@example.com")

    status, submitted = _call(httpd, "POST", "/api/rounds/submit", {},
                              author="reviewer@example.com")
    assert status == 200
    assert submitted["verdict_counts"] == {
        "accept": 1, "reject": 0, "changes": 0, "comment": 1, "select": 0}
    assert sorted(submitted["comment_ids"]) == sorted([a, b])
    assert submitted["undecided_ids"] == [a]
    pushes = _events(bus, "session_push")
    assert len(pushes) == 1 and pushes[0]["undecided_ids"] == [a]
    stored = next(x for items in _store(slug_dir)["anchors"].values() for x in items if x["id"] == a)
    assert "round_pending" not in stored["decision"]


def test_a_comment_without_text_is_a_400(server):
    httpd, _, _ = server
    _, comment = _call(httpd, "POST", "/api/comments", _card())
    status, err = _call(httpd, "POST", f"/api/comments/{comment['id']}/decision",
                        {"verdict": "comment"})
    assert status == 400
    assert err["error"] == "text required for comment verdict"


def test_revising_into_changes_keeps_the_prior_verdict_in_the_reply(server):
    httpd, _, bus = server
    _, comment = _call(httpd, "POST", "/api/comments", _card())
    _call(httpd, "POST", f"/api/comments/{comment['id']}/decision", {"verdict": "accept"})
    status, resp = _call(httpd, "POST", f"/api/comments/{comment['id']}/decision",
                         {"verdict": "changes", "text": "on reflection, narrow it"})
    assert status == 200
    assert resp["replies"][-1]["text"] == (
        "↻ Changes requested: on reflection, narrow it\n\n(revised verdict; was ✓ Accepted)")
    assert resp["decision_history"][0]["verdict"] == "accept"
    assert _events(bus, "comment_updated")[-1]["prior_verdict"] == "accept"


def test_an_unknown_verdict_is_still_rejected(server):
    httpd, _, _ = server
    _, comment = _call(httpd, "POST", "/api/comments", _card())
    status, err = _call(httpd, "POST", f"/api/comments/{comment['id']}/decision",
                        {"verdict": "maybe", "text": "x"})
    assert status == 400
    assert err["error"] == "invalid verdict"


def test_a_selected_custom_option_answers_the_card(server):
    """D3: a click on an option with a custom id is a CHOICE. It answers the
    card (so a round does not report it undecided) while leaving it open,
    because the agent still has to act on the choice."""
    httpd, slug_dir, _ = server
    _, comment = _call(httpd, "POST", "/api/comments", _card())
    status, resp = _call(httpd, "POST", f"/api/comments/{comment['id']}/decision",
                         {"verdict": "select", "text": "Draw both and decide later"})
    assert status == 200
    assert resp["decision"]["verdict"] == "select"
    assert resp["replies"][-1]["text"] == "☑ Selected: Draw both and decide later"
    assert _store(slug_dir)["anchors"]["s:a"][0]["status"] == "open"

    status, submitted = _call(httpd, "POST", "/api/rounds/submit", {})
    assert submitted["undecided_ids"] == []
