"""A reviewer deletes their own comment before it is sent; nothing else goes."""

from test_decision_api import _call, _events, _store, server  # noqa: F401

ME, OTHER = "chang@example.com", "someone@example.com"


def _post(httpd, author, text="Typed by accident"):
    status, body = _call(httpd, "POST", "/api/comments", {"anchor_id": "s:a", "text": text, "version": "v1"}, author=author)
    assert status in (200, 201), body
    return body["id"]


def test_own_unsent_comment_is_deleted(server):  # noqa: F811
    httpd, slug_dir, bus = server
    cid = _post(httpd, ME)
    assert _call(httpd, "DELETE", f"/api/comments/{cid}", author=OTHER)[0] == 403
    status, body = _call(httpd, "DELETE", f"/api/comments/{cid}", author=ME)
    assert status == 200 and body == {"deleted": cid}
    assert not any(c["id"] == cid for items in _store(slug_dir)["anchors"].values() for c in items)
    assert _events(bus, "comment_deleted")[-1]["comment_id"] == cid
    assert _call(httpd, "DELETE", f"/api/comments/{cid}", author=ME)[0] == 404


def test_sent_or_answered_comments_are_kept(server):  # noqa: F811
    httpd, slug_dir, bus = server
    sent, answered = _post(httpd, ME, "Sent"), _post(httpd, ME, "Answered")
    assert _call(httpd, "POST", "/api/push-session", {}, author=ME)[0] == 200
    _call(httpd, "PUT", f"/api/comments/{answered}", {"response_text": "Done."})
    for cid in (sent, answered):
        assert _call(httpd, "DELETE", f"/api/comments/{cid}", author=ME)[0] == 409


def test_editing_a_sent_comment_makes_it_unsent(server):  # noqa: F811
    httpd, slug_dir, bus = server
    cid = _post(httpd, ME, "First")
    assert _call(httpd, "POST", "/api/push-session", {}, author=ME)[0] == 200
    assert _call(httpd, "PUT", f"/api/comments/{cid}", {"text": "Second"}, author=ME)[0] == 200
    stored = next(c for items in _store(slug_dir)["anchors"].values() for c in items if c["id"] == cid)
    assert stored["text"] == "Second" and not stored["flagged_for_session"]


def test_notes_are_edited_and_deleted_by_their_author_until_sent(server):  # noqa: F811
    httpd, slug_dir, bus = server
    cid = _post(httpd, ME, "Card")
    for text in ("First note", "Second note"):
        assert _call(httpd, "POST", f"/api/comments/{cid}/reply", {"text": text}, author=ME)[0] == 200
    replies = lambda: next(c for items in _store(slug_dir)["anchors"].values() for c in items if c["id"] == cid)["replies"]  # noqa: E731
    first, second = replies()
    assert first["sent_at"] is None
    assert _call(httpd, "PUT", f"/api/comments/{cid}/replies/0", {"ts": first["ts"], "text": "x"}, author=OTHER)[0] == 403
    assert _call(httpd, "PUT", f"/api/comments/{cid}/replies/0", {"ts": "1999-01-01T00:00:00Z", "text": "x"}, author=ME)[0] == 404
    assert _call(httpd, "DELETE", f"/api/comments/{cid}/replies/1?ts={second['ts']}", author=ME)[0] == 200
    assert [r["text"] for r in replies()] == ["First note"]
    # Both notes went out: Send carries every unsent one, then they are sent.
    assert _call(httpd, "POST", "/api/push-session", {}, author=ME)[0] == 200
    assert replies()[0]["sent_at"]
    assert _call(httpd, "DELETE", f"/api/comments/{cid}/replies/0?ts={first['ts']}", author=ME)[0] == 409
    assert _call(httpd, "PUT", f"/api/comments/{cid}/replies/0", {"ts": first["ts"], "text": "First note, fixed"}, author=ME)[0] == 200
    assert replies()[0]["sent_at"] is None and replies()[0]["text"] == "First note, fixed"
