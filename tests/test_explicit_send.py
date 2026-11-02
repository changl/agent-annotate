"""Reviewer drafts are private until the explicit Send transaction."""

import json
import uuid
from types import SimpleNamespace

import pytest
from test_decision_api import _call, _card, _events, server  # noqa: F401

from agent_annotate import cli, mcp_server
from agent_annotate.categories import mark_finding_fixed
from agent_annotate.copy_state import save_copy
from agent_annotate.hooks import check_comment_bus as hook
from agent_annotate.hooks.session_start import waiting_count


@pytest.mark.parametrize("action", ["comment", "reply", "decision", "note-edit", "comment-edit"])
def test_saved_drafts_are_private_on_every_agent_surface(server, monkeypatch, capsys, tmp_path, action):  # noqa: F811
    httpd, directory, bus = server
    _, card = _call(httpd, "POST", "/api/comments", _card())
    cid = card["id"]
    if action in ("note-edit", "comment-edit"):
        if action == "comment-edit":
            _, card = _call(httpd, "POST", "/api/comments", {"anchor_id": "s:a", "text": "Original"}, author="r@x")
            cid = card["id"]
        else:
            _call(httpd, "POST", f"/api/comments/{cid}/reply", {"text": "Original"}, author="r@x")
        _call(httpd, "POST", "/api/rounds/submit", {}, author="r@x")
    record = {"slug_dir": str(directory), "bus_file": str(bus), "slug": "review", "project": "test", "owner_session": "owner"}
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("test", "review", record)])
    monkeypatch.setattr(cli, "BUS_OFFSET_ROOT", tmp_path / "offsets")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "owner")
    _call(httpd, "PUT", f"/api/comments/{cid}", {"response_text": "Agent context before drafting"})
    before_view = _call(httpd, "GET", "/api/comments")[1]
    before = waiting_count(directory)
    start = bus.stat().st_size
    if action == "comment":
        _call(httpd, "POST", "/api/comments", {"anchor_id": "s:a", "text": "PRIVATE WORDS"}, author="r@x")
    elif action == "reply":
        _call(httpd, "POST", f"/api/comments/{cid}/reply", {"text": "PRIVATE WORDS"}, author="r@x")
    elif action == "decision":
        _call(httpd, "POST", f"/api/comments/{cid}/decision", {"verdict": "accept", "text": "PRIVATE WORDS"}, author="r@x")
    elif action == "note-edit":
        note = json.loads((directory / "comments.json").read_text())["anchors"]["s:a"][0]["replies"][0]
        _call(httpd, "PUT", f"/api/comments/{cid}/replies/0", {"ts": note["ts"], "text": "PRIVATE WORDS"}, author="r@x")
    else:
        _call(httpd, "PUT", f"/api/comments/{cid}", {"text": "PRIVATE WORDS"}, author="r@x")
    assert waiting_count(directory) == before
    assert _call(httpd, "GET", "/api/comments")[1] == before_view
    events = [e for e in _events(bus) if e not in _events_before(bus, start)]
    assert not any(hook._is_reviewer_event(e) for e in events)
    for unread in (False, True):
        assert cli.cmd_inbox(SimpleNamespace(slug="review", project="test", unread=unread, json=True, all_events=False)) == 0
        assert "PRIVATE WORDS" not in capsys.readouterr().out
    assert "PRIVATE WORDS" not in json.dumps(mcp_server._comment_rows("review"))
    assert "PRIVATE WORDS" not in json.dumps(cli._decision_cards(cli._load_store(record)))
    for endpoint in ("/api/comments", "/comments.json"):
        _, data = _call(httpd, "GET", endpoint)
        assert "PRIVATE WORDS" not in json.dumps(data)
    if action != "comment":
        _, response = _call(httpd, "POST", f"/api/comments/{cid}/reply", {"text": "Agent reply while drafting"})
        assert "PRIVATE WORDS" not in json.dumps(response)
    if action == "decision":
        status, response = _call(httpd, "PUT", f"/api/comments/{cid}", {"status": "addressed_by_agent"})
        assert status == 200 and "PRIVATE WORDS" not in json.dumps(response)
    assert not any(e.get("event") == "session_push" for e in events)
    _call(httpd, "POST", "/api/rounds/submit", {}, author="r@x")
    assert cli.cmd_inbox(SimpleNamespace(slug="review", project="test", unread=True, json=True, all_events=False)) == 0
    assert "PRIVATE WORDS" in capsys.readouterr().out
    if action == "reply":
        assert _events(bus, "round_submitted")[-1]["answers"][0]["text"].count("PRIVATE WORDS") == 1


def _events_before(bus, size):
    return [json.loads(line) for line in bus.read_bytes()[:size].splitlines()]


def test_note_on_an_accepted_card_waits_for_send_and_is_not_stranded(server):  # noqa: F811
    httpd, directory, bus = server
    _, card = _call(httpd, "POST", "/api/comments", _card())
    route = f"/api/comments/{card['id']}"
    _call(httpd, "POST", route + "/decision", {"verdict": "accept"}, author="r@x")
    _call(httpd, "POST", "/api/rounds/submit", {}, author="r@x")
    count = len(_events(bus, "session_push"))
    _call(httpd, "POST", route + "/reply", {"text": "A note after acceptance"}, author="r@x")
    assert len(_events(bus, "session_push")) == count
    assert "A note after acceptance" not in json.dumps(_call(httpd, "GET", "/api/comments")[1])
    _, result = _call(httpd, "POST", "/api/rounds/submit", {}, author="r@x")
    assert result["comment_count"] == 1
    assert "A note after acceptance" in json.dumps(_events(bus, "round_submitted")[-1])


def test_one_reviewers_send_does_not_submit_another_reviewers_drafts(server):  # noqa: F811
    httpd, _, bus = server
    comments = {}
    for author in ("r@x", "other@x"):
        _, comments[author] = _call(httpd, "POST", "/api/comments", {"anchor_id": "s:a", "text": author + " PRIVATE"}, author=author)
    assert _call(httpd, "POST", f"/api/comments/{comments['other@x']['id']}/push", {}, author="r@x")[0] == 403
    _call(httpd, "POST", "/api/rounds/submit", {}, author="r@x")
    assert "other@x PRIVATE" not in json.dumps(_events(bus, "round_submitted"))
    assert "other@x PRIVATE" not in json.dumps(_call(httpd, "GET", "/api/comments")[1])
    _call(httpd, "POST", "/api/rounds/submit", {}, author="other@x")
    assert "other@x PRIVATE" in json.dumps(_events(bus, "round_submitted")[-1])


def test_library_edits_and_finding_reopens_are_private_until_send(server):  # noqa: F811
    httpd, directory, bus = server
    save_copy(directory, {"blocks": [{"id": "hero", "title": "Hero", "current": "r1", "status": "needs_you",
        "revisions": [{"id": "r1", "created_at": "2026-10-02T00:00:00Z", "author": {"id": "agent:builder"},
                       "status": "draft", "delta": {"ops": [{"insert": "Current\n"}]}}]}]})
    _, finding = _call(httpd, "POST", "/api/comments", {**_card(), "category": "findings",
                      "finding": {"set": "design", "title": "Contrast"}})
    mark_finding_fixed(directory, finding["id"], by="agent:builder", note="Fixed", proof=[{"label": "Proof", "url": "https://example.test/proof"}])
    before_comments = _call(httpd, "GET", "/api/comments")[1]
    before_counts = _call(httpd, "GET", "/api/categories")[1]["categories"]
    _call(httpd, "POST", "/api/copy/hero/proposal", {"delta": {"ops": [{"insert": "PRIVATE LIBRARY\n"}]},
          "base_revision": "r1", "request_id": str(uuid.uuid4())}, author="r@x")
    _call(httpd, "POST", f"/api/comments/{finding['id']}/reopen", {"text": "PRIVATE REOPEN"}, author="r@x")
    assert _call(httpd, "GET", "/api/comments")[1] == before_comments
    assert _call(httpd, "GET", "/api/categories")[1]["categories"] == before_counts
    assert "PRIVATE LIBRARY" not in json.dumps(_call(httpd, "GET", "/api/copy")[1])
    assert _events(bus, "session_push") == []
    _call(httpd, "POST", "/api/rounds/submit", {}, author="r@x")
    round_text = json.dumps(_events(bus, "round_submitted")[-1])
    assert "PRIVATE LIBRARY" in round_text and "PRIVATE REOPEN" in round_text


def test_watch_never_prints_saved_draft_events(tmp_path, monkeypatch, capsys):
    bus = tmp_path / "events.ndjson"
    bus.write_text("")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"slugs": {"review": {"bus_file": str(bus)}}}))
    monkeypatch.setattr(cli, "_all_state_files", lambda: [state])
    calls = []
    def wait(_):
        if calls:
            raise KeyboardInterrupt
        calls.append(True)
        bus.write_text(json.dumps({"event": "comment_reply", "author": "r@x", "text": "PRIVATE DRAFT"}) + "\n"
                       + json.dumps({"event": "round_submitted", "by": "r@x", "note": "EXPLICIT SEND"}) + "\n")
    monkeypatch.setattr(cli.time, "sleep", wait)
    assert cli.cmd_watch(SimpleNamespace(slug="review")) == 0
    output = capsys.readouterr().out
    assert "PRIVATE DRAFT" not in output and "EXPLICIT SEND" in output


def test_eval_and_publish_blockers_do_not_reveal_drafts(server, monkeypatch):  # noqa: F811
    from agent_annotate import eval as evaluation

    httpd, directory, bus = server
    _call(httpd, "POST", "/api/comments", {"anchor_id": "s:a", "text": "PRIVATE DIAGNOSTIC"}, author="r@x")
    assert cli._carryover_blockers(directory, "v2") == []
    record = {"slug_dir": str(directory), "project": "sandbox", "slug": "review"}
    monkeypatch.setattr(evaluation, "BUS_DIR", str(bus.parent.parent))
    monkeypatch.setattr(evaluation, "load_registry", lambda: {"sandbox/review": record})
    assert evaluation.load_bus(bus.parent.name, "review")[1] == []
    monkeypatch.setattr(evaluation, "load_bus", lambda project, slug: (str(bus), []))
    assert "PRIVATE DIAGNOSTIC" not in json.dumps(evaluation.collect_slugs(), default=str)


@pytest.mark.parametrize("route", ["archive", "accept"])
def test_reviewer_page_disposal_does_not_automatically_change_agent_state(server, route):  # noqa: F811
    httpd, _, bus = server
    _, card = _call(httpd, "POST", "/api/comments", _card())
    before = _call(httpd, "GET", "/api/comments")[1]
    _call(httpd, "POST", f"/api/comments/{card['id']}/{route}", {}, author="r@x")
    assert _call(httpd, "GET", "/api/comments")[1] == before
    assert not any(hook._is_reviewer_event(e) for e in _events(bus))
    assert _events(bus, "session_push") == []
