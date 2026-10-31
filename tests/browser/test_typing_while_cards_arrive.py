"""Typing is never lost while the agent adds cards (Chang, 2026-10-30).

test_keep_drafts blurs each box before the page changes. Here the reviewer is
still typing: the box keeps focus while the agent posts a new question card
and the page polls, then typing continues. Every keystroke must survive.
"""

import json

import pytest
from test_keep_drafts import _agent, _directory, _poll, _session

playwright = pytest.importorskip("playwright.sync_api")

FIRST, MORE = "Half a thought about the release", " and the rest of it"


def _new_card(base, n):
    _agent(base, "api/comments/batch", {"items": [{
        "anchor_id": "s:checks", "text": f"Question {n}", "version": "v1",
        "decision_request": {"prompt": f"New question {n}?", "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]},
    }]})


def _type_through_new_cards(page, base, box, frame=None):
    box.click()
    page.keyboard.type(FIRST)
    for n in (1, 2):
        _new_card(base, n)
        _poll(page)
        page.wait_for_timeout(500)
    page.keyboard.type(MORE)
    page.wait_for_timeout(300)
    return box.input_value()


def test_rail_answer_box(tmp_path):
    with _session(tmp_path, _directory(tmp_path)) as (page, base, _):
        box = page.locator('#comment-list [data-decision-say-ta="question-11"]')
        assert _type_through_new_cards(page, base, box) == FIRST + MORE


def test_document_answer_box(tmp_path):
    with _session(tmp_path, _directory(tmp_path)) as (page, base, _):
        box = page.frame_locator("#content-frame").locator('textarea[data-strip-say="question-11"]')
        assert _type_through_new_cards(page, base, box) == FIRST + MORE


def test_new_comment_popover(tmp_path):
    with _session(tmp_path, _directory(tmp_path)) as (page, base, _):
        page.frame_locator("#content-frame").locator('[data-anchor-id="s:checks"] h2').click(position={"x": 10, "y": 5})
        page.locator("#popover.vis").wait_for()
        assert _type_through_new_cards(page, base, page.locator("#pop-ta")) == FIRST + MORE


def test_general_feedback(tmp_path):
    with _session(tmp_path, _directory(tmp_path)) as (page, base, _):
        page.locator("#general-feedback-toggle").click()
        assert _type_through_new_cards(page, base, page.locator("#gf-ta")) == FIRST + MORE


def _type_through(page, box, change):
    box.click()
    page.keyboard.type(FIRST)
    change()
    _poll(page)
    page.wait_for_timeout(800)
    page.keyboard.type(MORE)
    page.wait_for_timeout(300)
    return box.input_value()


@pytest.mark.parametrize("where", ["rail", "document", "popover"])
def test_a_new_version_while_typing(tmp_path, where):
    from test_keep_drafts import _publish_v2
    directory = _directory(tmp_path)
    with _session(tmp_path, directory) as (page, base, _):
        frame = page.frame_locator("#content-frame")
        if where == "popover":
            frame.locator('[data-anchor-id="s:checks"] h2').click(position={"x": 10, "y": 5})
            page.locator("#popover.vis").wait_for()
        box = {"rail": page.locator('#comment-list [data-decision-say-ta="question-11"]'),
               "document": frame.locator('textarea[data-strip-say="question-11"]'),
               "popover": page.locator("#pop-ta")}[where]
        assert _type_through(page, box, lambda: _publish_v2(tmp_path, directory)) == FIRST + MORE


@pytest.mark.parametrize("where", ["rail", "document"])
def test_the_agent_rewords_the_card_being_answered(tmp_path, where):
    with _session(tmp_path, _directory(tmp_path)) as (page, base, _):
        frame = page.frame_locator("#content-frame")
        box = {"rail": page.locator('#comment-list [data-decision-say-ta="question-11"]'),
               "document": frame.locator('textarea[data-strip-say="question-11"]')}[where]
        def reword():
            return _agent(base, "api/comments/question-11", {"decision_request": {
                "prompt": "When should we release, given the new build?",
                "options": [{"id": "now", "label": "Ship now"}, {"id": "later", "label": "Ship later"}]}}, method="PUT")
        assert _type_through(page, box, reword) == FIRST + MORE


@pytest.mark.parametrize("how", ["withdrawn", "resolved"])
def test_the_agent_replaces_the_card_being_answered(tmp_path, how):
    with _session(tmp_path, _directory(tmp_path)) as (page, base, _):
        box = page.locator('#comment-list [data-decision-say-ta="question-11"]')
        body = ({"decision_request": None, "withdraw_reason": "replaced by #12"} if how == "withdrawn"
                else {"status": "resolved_in_version", "resolved_in_version": "v1", "resolution_anchor_id": "s:checks", "resolve_own_anchor": False})
        box.click()
        page.keyboard.type(FIRST)
        _agent(base, "api/comments/question-11", body, method="PUT")
        _new_card(base, 12)
        _poll(page)
        page.wait_for_timeout(800)
        page.keyboard.type(MORE)
        page.wait_for_timeout(300)
        shown = page.evaluate("""() => [...document.querySelectorAll('textarea')].map(t => t.value).concat(
            [...document.querySelector('#content-frame').contentDocument.querySelectorAll('textarea')].map(t => t.value))""")
        assert any(FIRST in v for v in shown), shown


@pytest.mark.parametrize("how", ["withdrawn", "resolved", "answered_elsewhere"])
def test_text_typed_on_a_replaced_card_stays_in_view_and_goes_with_send(tmp_path, how):
    from test_keep_drafts import _blur
    directory = _directory(tmp_path)
    with _session(tmp_path, directory) as (page, base, _):
        box = page.locator('#comment-list [data-decision-say-ta="question-11"]')
        box.click()
        page.keyboard.type(FIRST)
        if how == "withdrawn":
            _agent(base, "api/comments/question-11", {"decision_request": None, "withdraw_reason": "replaced by #12"}, method="PUT")
        elif how == "resolved":
            _agent(base, "api/comments/question-11", {"status": "resolved_in_version", "resolved_in_version": "v1",
                                                      "resolution_anchor_id": "s:checks"}, method="PUT")
        else:
            _agent(base, "api/comments/question-11", {"status": "addressed_by_agent", "response_text": "Shipped now."}, method="PUT")
        _new_card(base, 12)
        _blur(page)
        _poll(page, 2)
        page.wait_for_timeout(800)
        shown = page.evaluate("""() => [...document.querySelectorAll('textarea')].map(t => t.value).concat(
            [...document.querySelector('#content-frame').contentDocument.querySelectorAll('textarea')].map(t => t.value))""")
        assert any(FIRST in v for v in shown), shown
        # Send posts it as a reply on that card.
        page.locator("#send-btn").click()
        page.locator("#round-submit-btn").click()
        page.wait_for_function("() => !document.querySelector('#round-confirm-backdrop.vis')")
        for _ in range(50):
            card = next(c for items in json.loads((directory / "comments.json").read_text())["anchors"].values()
                        for c in items if c["id"] == "question-11")
            if any(r["text"] == FIRST for r in card.get("replies") or []):
                break
            page.wait_for_timeout(100)
        assert any(r["text"] == FIRST for r in card.get("replies") or [])
        page.wait_for_function("() => !document.querySelector('#comment-list .decision-stranded')")
