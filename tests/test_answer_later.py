"""Answer later: the page remembers a set-aside question; agents never track it (Chang, 2026-10-31)."""

import json

from test_decision_api import _call, _card, _events, _store, server  # noqa: F401

from agent_annotate.categories import category_counts
from agent_annotate.cli import _decision_cards, _withdraw_unasked
from agent_annotate.hooks.check_comment_bus import _load_cards as hook_cards
from agent_annotate.hooks.decision_state import is_undecided
from agent_annotate.hooks.session_start import waiting_count

REVIEWER = "chang@example.com"


def _two_cards(httpd):
    later = _call(httpd, "POST", "/api/comments", _card(anchor="s:a", prompt="Later?"))[1]
    now = _call(httpd, "POST", "/api/comments", _card(anchor="s:b", prompt="Now?"))[1]
    return later, now


def _set_aside(httpd, cid, on=True):
    return _call(httpd, "POST", f"/api/comments/{cid}/answer-later", {"on": on}, author=REVIEWER)


def test_set_aside_is_persisted_without_telling_the_agent(server):  # noqa: F811
    httpd, slug_dir, bus = server
    later, _ = _two_cards(httpd)
    before = len(_events(bus))
    status, body = _set_aside(httpd, later["id"])
    assert status == 200 and body["answer_later"]["by"] == REVIEWER
    stored = _store(slug_dir)["anchors"]["s:a"][0]
    assert stored["answer_later"]
    assert "edited_at" not in stored and not stored.get("flagged_for_session")  # nothing for Send
    assert len(_events(bus)) == before  # no bus event: inbox and hooks never hear of it
    # A reload (any device) reads the same store.
    assert _call(httpd, "GET", "/comments.json", author=REVIEWER)[1]["anchors"]["s:a"][0]["answer_later"]
    assert _set_aside(httpd, later["id"], on=False)[0] == 200
    assert "answer_later" not in _store(slug_dir)["anchors"]["s:a"][0]


def test_only_an_unanswered_question_can_be_set_aside(server):  # noqa: F811
    httpd, _, _ = server
    later, now = _two_cards(httpd)
    assert _call(httpd, "POST", f"/api/comments/{now['id']}/decision", {"verdict": "accept"}, author=REVIEWER)[0] == 200
    assert _set_aside(httpd, now["id"])[0] == 409
    assert _set_aside(httpd, "missing")[0] == 404
    assert _call(httpd, "POST", f"/api/comments/{later['id']}/answer-later", {"on": "yes"}, author=REVIEWER)[0] == 400


def test_answering_takes_it_out_of_the_section(server):  # noqa: F811
    httpd, slug_dir, _ = server
    later, _ = _two_cards(httpd)
    _set_aside(httpd, later["id"])
    assert _call(httpd, "POST", f"/api/comments/{later['id']}/decision",
                 {"verdict": "reject", "defer_push": True}, author=REVIEWER)[0] == 200
    assert "answer_later" not in _store(slug_dir)["anchors"]["s:a"][0]


def test_set_aside_is_never_undecided_or_needs_you(server):  # noqa: F811
    httpd, slug_dir, _ = server
    later, now = _two_cards(httpd)
    _set_aside(httpd, later["id"])
    store = _store(slug_dir)

    undecided = _call(httpd, "POST", "/api/rounds/submit", {}, author=REVIEWER)[1]["undecided_ids"]
    assert undecided == [now["id"]]
    cards = {c["id"]: c for c in _decision_cards(store)}
    assert not cards[later["id"]]["answer_later"] and is_undecided(cards[later["id"]])
    assert is_undecided(cards[now["id"]])
    hooked = hook_cards(str(slug_dir))
    assert is_undecided(hooked[later["id"]]) and is_undecided(hooked[now["id"]])
    counts = category_counts(slug_dir, store=store)["review"]
    assert counts["needs_you"] == 1 and counts["later"] == 1
    assert waiting_count(slug_dir) == 2


def test_a_new_version_never_withdraws_a_set_aside_question(server):  # noqa: F811
    httpd, slug_dir, _ = server
    later, now = _two_cards(httpd)
    _set_aside(httpd, later["id"])
    assert _withdraw_unasked(slug_dir, "v2", cards=[]) == [now["id"]]
    store = json.loads((slug_dir / "comments.json").read_text())
    kept = store["anchors"]["s:a"][0]
    assert kept["decision_request"] and not kept.get("withdrawn") and kept["answer_later"]
