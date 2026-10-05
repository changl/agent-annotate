"""Contract extensions for parity with the accepted single-page prototype (final/)."""
import json

import pytest
from test_copy_state import document
from test_decision_api import server as server

from agent_annotate.categories import (
    block_can_be_unread,
    category_counts,
    comment_can_be_unread,
    comment_sig,
    load_categories,
    mark_finding_fixed,
    save_findings_sets,
    validate_proof,
)
from agent_annotate.copy_state import save_copy


def write_comments(directory, *comments):
    directory.mkdir(parents=True, exist_ok=True)
    anchors = {}
    for comment in comments:
        anchors.setdefault(comment["anchor_id"], []).append(comment)
    (directory / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": anchors, "archived": {}}))
    (directory / "current.meta.json").write_text('{"current":"v1"}')


def test_findings_sets_keep_optional_item_label_intro_and_posted_time(tmp_path):
    design = {"id": "design", "label": "Design review", "item_label": "Gap",
              "intro": "Seven pages, read-only.", "created_at": "2026-10-01T03:16:02Z"}
    saved = save_findings_sets(tmp_path, [design, {"id": "motion", "label": "Motion choices"}])
    assert saved["findings_sets"][0] == design
    assert load_categories(tmp_path) == saved
    # A set written before the extension still loads unchanged.
    (tmp_path / "categories.json").write_text(json.dumps({"schema_version": 1, "findings_sets": [{"id": "a", "label": "A"}]}))
    assert load_categories(tmp_path)["findings_sets"] == [{"id": "a", "label": "A"}]


@pytest.mark.parametrize("extra", [{"color": "red"}, {"item_label": ""}, {"item_label": "x" * 41},
                                   {"created_at": "yesterday"}, {"intro": "bad\x00text"}])
def test_findings_sets_refuse_unknown_or_invalid_fields_without_writing(tmp_path, extra):
    with pytest.raises(ValueError):
        save_findings_sets(tmp_path, [{"id": "design", "label": "Design", **extra}])
    assert not (tmp_path / "categories.json").exists()


def test_proof_link_keeps_optional_detail_line(tmp_path):
    proof = validate_proof(tmp_path, [{"label": "The change that fixed it", "url": "https://example.com/pull/1",
                                       "detail": "An agent links the merged change here."}])
    assert proof == [{"label": "The change that fixed it", "url": "https://example.com/pull/1",
                      "detail": "An agent links the merged change here."}]
    with pytest.raises(ValueError):
        validate_proof(tmp_path, [{"label": "x", "url": "https://example.com", "detail": ""}])
    with pytest.raises(ValueError):
        validate_proof(tmp_path, [{"label": "x", "url": "https://example.com", "extra": "no"}])


def test_unread_counts_follow_final(tmp_path):
    question = {"id": "q", "number": 1, "anchor_id": "finding:gap-1", "category": "findings", "status": "open",
                "author": "agent:claude", "finding": {"set": "design", "title": "Fix?"},
                "decision_request": {"prompt": "Fix?", "options": [{"id": "fix", "label": "Fix it"}]}}
    library_q = {"id": "q9", "anchor_id": "copy:held-question", "category": "library", "status": "open",
                 "author": "agent:claude", "decision_request": {"prompt": "Fix the wording?"}}
    reply = {"id": "c1", "anchor_id": "copy:hero", "category": "library", "status": "open", "author": "chang",
             "created_at": "2026-10-01T00:00:00Z", "replies": [{"author": "agent:claude", "ts": "2026-10-02T00:00:00Z", "text": "Done"}]}
    review = {"id": "r1", "anchor_id": "s:intro", "status": "open", "author": "agent:claude",
              "decision_request": {"prompt": "Ship?"}}
    write_comments(tmp_path, question, library_q, reply, review)
    data = document()
    data["blocks"][0].update(status="held", held_note="Not true yet")
    plain = json.loads(json.dumps(data["blocks"][0]))
    plain.update(id="footer", status="done")
    plain.pop("held_note")
    data["blocks"].append(plain)
    save_copy(tmp_path, data)

    counts = category_counts(tmp_path, "chang")
    # An unanswered finding needs you; it is not unread until it is marked fixed.
    assert counts["findings"]["unread"] == 0 and counts["findings"]["needs_you"] == 1
    # Library: the held item's agent note and the agent reply; not #9, not first text.
    # (#9 and the reply both need you.)
    assert counts["library"]["unread"] == 2 and counts["library"]["needs_you"] == 2
    assert counts["review"]["unread"] == 1
    assert not comment_can_be_unread(library_q) and comment_can_be_unread(reply)
    assert block_can_be_unread(data["blocks"][0]) and not block_can_be_unread(plain)
    assert block_can_be_unread({"revisions": [{"author": {"id": "chang"}}, {"author": {"id": "agent:claude"}}]})

    fixed = mark_finding_fixed(tmp_path, "q", by="agent:claude", note="Fixed",
                               proof=[{"label": "Change", "url": "https://example.com/c"}])
    assert category_counts(tmp_path, "chang")["findings"]["unread"] == 1
    (tmp_path / "read-state.json").write_text(json.dumps({"chang": {"q": {"sig": comment_sig(fixed)}}}))
    assert category_counts(tmp_path, "chang")["findings"]["unread"] == 0


def test_api_linked_page_carries_optional_declaration(server):
    from test_categories_api import _call

    from agent_annotate.paths import STATE_DIR
    httpd, directory, _ = server
    primary = {"slug_dir": str(directory), "port": httpd.server_address[1], "url": "http://127.0.0.1:8980/", "workspace_primary": True}
    exception = {"reason": "Interactive worksheet", "parent_slug": "review", "declared_by": "Chang",
                 "declared_at": "2026-10-04T12:00:00Z", "told_to": "the project's orchestrator"}
    child = {"slug_dir": str(directory.parent / "lab"), "title": "Motion lab", "url": "http://127.0.0.1:8981/", "exception": exception}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    registry = STATE_DIR / "bus.json"
    registry.write_text(json.dumps({"project": "Rebex", "slugs": {"review": primary, "motion-lab": child}}))
    try:
        page = _call(httpd, "GET", "/api/categories")[1]["linked_pages"][0]
        assert {k: page[k] for k in ("declared_by", "declared_at", "told_to")} == {
            "declared_by": "Chang", "declared_at": "2026-10-04T12:00:00Z", "told_to": "the project's orchestrator"}
    finally:
        registry.unlink()


def test_api_findings_unread_is_an_unopened_fix_under_aliases(server, monkeypatch):
    from test_categories_api import _call, finding
    httpd, directory, _ = server
    monkeypatch.setattr(httpd.RequestHandlerClass, "_reviewer_authors", lambda self, author: {author, "old@example.com"})
    card = finding(httpd)
    unread = lambda: next(c for c in _call(httpd, "GET", "/api/categories", author="new@example.com")[1]["categories"]  # noqa: E731
                          if c["id"] == "findings")["counts"]["unread"]
    assert unread() == 0
    fixed = mark_finding_fixed(directory, card["id"], by="agent:claude", note="Fixed",
                               proof=[{"label": "Change", "url": "https://example.com/c"}])
    assert unread() == 1
    assert _call(httpd, "POST", "/api/read-state", {"items": [{"id": card["id"], "sig": comment_sig(fixed)}]}, author="old@example.com")[0] == 200
    assert unread() == 0


def test_one_send_keeps_its_summary_lines_for_history(server):
    from test_decision_api import _call, _card
    httpd, directory, _ = server
    card = _call(httpd, "POST", "/api/comments", _card("s:a"))[1]
    _call(httpd, "POST", f"/api/comments/{card['id']}/decision", {"verdict": "select", "text": "Yes", "defer_push": True}, author="chang@example.com")
    assert _call(httpd, "POST", "/api/comments", {"anchor_id": "s:b", "text": "Typo here"}, author="chang@example.com")[0] == 201
    receipt = [{"cat": "review", "label": "#1 · Rename?", "answer": "Yes"}, {"cat": "review", "label": "#2 · Typo here"},
               {"cat": "library", "label": "#9 Footer", "answer": "Edited"}]
    send = {"send_id": "send-0123456789", "receipt": receipt}
    assert _call(httpd, "POST", "/api/rounds/submit", {**send, "version": "v1"}, author="chang@example.com")[0] == 200
    status, pushed = _call(httpd, "POST", "/api/push-session", send, author="chang@example.com")
    assert status == 200 and pushed["flagged_count"] == 1
    rounds = _call(httpd, "GET", "/api/history", author="chang@example.com")[1]["rounds"]
    # The round (answers, edits) and the push (comments) are one Send.
    assert len(rounds) == 2, rounds
    assert all(r.get("send_id") == "send-0123456789" and r.get("receipt") == receipt for r in rounds)
    # A Send without the optional fields still works, with an empty body too.
    assert _call(httpd, "POST", "/api/push-session", author="chang@example.com")[0] == 200


@pytest.mark.parametrize("bad", [{"send_id": "x"}, {"receipt": [{"cat": "other", "label": "x"}]},
                                 {"receipt": [{"cat": "review", "label": ""}]},
                                 {"receipt": [{"cat": "review", "label": "x", "extra": 1}]},
                                 {"receipt": [{"cat": "review", "label": "x"}] * 201}])
def test_send_receipt_is_validated(server, bad):
    from test_decision_api import _call
    httpd, _, _ = server
    assert _call(httpd, "POST", "/api/rounds/submit", bad, author="chang@example.com")[0] == 400
    assert _call(httpd, "POST", "/api/push-session", bad, author="chang@example.com")[0] == 400
