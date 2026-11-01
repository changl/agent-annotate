"""Answered and Answer later questions fold to one line at their place in the document (Chang, 2026-11-01).

He scrolled past full-size cards he had already answered or set aside to reach
the ones he could answer now. Each folds to its number, prompt and state; a tap
opens the full card. Folding follows his own actions and a load, never a poll.
"""

import json
import socket

import pytest
from single_page import CHROME, ready
from test_keep_drafts import _agent, _directory, _poll, _start, _stop

playwright = pytest.importorskip("playwright.sync_api")

Q11 = '[data-strip-item="question-11"]'


@pytest.fixture(params=["ipad-webkit", "desktop-chrome"])
def session(request, tmp_path):
    directory = _directory(tmp_path)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = _start(tmp_path, directory, port)
    base = f"http://127.0.0.1:{port}/"
    _agent(base, "api/comments/batch", {"items": [{
        "anchor_id": "s:checks", "text": "Second", "version": "v1",
        "decision_request": {"prompt": "Second question?", "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]},
    }]})
    try:
        with playwright.sync_playwright() as runner:
            if request.param == "ipad-webkit":
                try:
                    browser = runner.webkit.launch()
                except Exception:
                    pytest.skip("Playwright WebKit is not installed")
                page = browser.new_context(**dict(runner.devices["iPad Pro 11"])).new_page()
            else:
                if not CHROME.exists():
                    pytest.skip("Google Chrome is not installed")
                browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.set_default_timeout(8000)
            touch = request.param == "ipad-webkit"
            press = (lambda loc: loc.tap()) if touch else (lambda loc: loc.click())

            def load():
                if page.url.startswith(base):
                    page.reload(wait_until="networkidle")
                else:
                    page.goto(base + "#view=review", wait_until="networkidle")
                ready(page)
                frame = page.frame_locator("#content-frame")
                frame.locator(Q11).wait_for()
                return frame

            try:
                yield page, load, press, directory
            finally:
                browser.close()
    finally:
        _stop(server)


def _one_line(item):
    item.page.wait_for_timeout(500)  # the post lands and the card is redrawn
    item.wait_for(state="visible")
    box = item.bounding_box()
    assert box and box["height"] <= 60, box
    assert item.locator(".annotate-decision-btns, textarea").count() == 0


def test_an_answered_question_folds_at_its_place_and_a_tap_opens_it(session):
    page, load, press, directory = session
    frame = load()
    item = frame.locator(Q11)
    anchor = item.evaluate("el => el.closest('[data-annotate-strip]').dataset.stripAnchor")
    press(item.locator(".annotate-opt-row").first)
    frame.locator(Q11 + ".annotate-folded").wait_for()
    _one_line(item)
    assert item.evaluate("el => el.closest('[data-annotate-strip]').dataset.stripAnchor") == anchor
    assert "Ship now" in item.inner_text() and "Pending" in item.inner_text()
    # The question still open stays full size.
    assert frame.locator(".annotate-decision-item:not(.annotate-folded)").count() == 1
    press(item.locator(".annotate-folded-row"))
    item.locator(".annotate-answer-change").wait_for()
    item.locator(".annotate-add-note textarea").wait_for()
    # A poll never folds it under him.
    _poll(page, 2)
    page.evaluate("() => window.AnnotateDocs.reload()")
    page.wait_for_timeout(500)
    assert frame.locator(Q11 + " .annotate-answer-change").count() == 1
    # A load folds it again.
    frame = load()
    frame.locator(Q11 + ".annotate-folded").wait_for()
    assert json.loads((directory / "comments.json").read_text())["anchors"]["d:q11"][0]["decision"]["verdict"]


def test_an_answer_later_question_folds_at_its_place_and_opens_to_bring_it_back(session):
    page, load, press, directory = session
    frame = load()
    item = frame.locator(Q11)
    anchor = item.evaluate("el => el.closest('[data-annotate-strip]').dataset.stripAnchor")
    press(item.locator('[data-decision-action="later"]'))
    frame.locator(Q11 + ".annotate-folded").wait_for()
    _one_line(item)
    assert "Answer later" in item.inner_text()
    assert item.evaluate("el => el.closest('[data-annotate-strip]').dataset.stripAnchor") == anchor
    frame = load()
    item = frame.locator(Q11)
    frame.locator(Q11 + ".annotate-folded").wait_for()
    press(item.locator(".annotate-folded-row"))
    press(item.locator('[data-decision-action="later"][data-later="0"]'))  # Back to Needs you
    item.locator('[data-decision-action="later"][data-later="1"]').wait_for()
    assert frame.locator(Q11 + ".annotate-folded").count() == 0
    page.wait_for_timeout(500)
    assert "answer_later" not in json.loads((directory / "comments.json").read_text())["anchors"]["d:q11"][0]
