"""Answer later on an iPad: one tap sets a question aside, one tap answers it there (Chang, 2026-10-31)."""

import json
import socket

import pytest
from test_keep_drafts import _agent, _directory, _loaded, _start, _stop

playwright = pytest.importorskip("playwright.sync_api")

CARD = '#comment-list .citem[data-comment-id="question-11"]'


def _open_rail(page):
    _loaded(page)
    opener = page.locator('[data-rail-open="feedback"]')
    if opener.is_visible() and opener.get_attribute("aria-expanded") != "true":
        opener.tap()
    page.locator("#comment-list .sec-hdr").first.wait_for()


def _needs(page):
    badge = page.locator("#tab-feedback-n")
    return 0 if badge.is_hidden() else int(badge.text_content())


def test_one_tap_sets_aside_and_one_tap_answers(tmp_path):
    directory = _directory(tmp_path)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = _start(tmp_path, directory, port)
    base = f"http://127.0.0.1:{port}/"
    try:
        _agent(base, "api/comments/batch", {"items": [{
            "anchor_id": "s:checks", "text": "Second", "version": "v1",
            "decision_request": {"prompt": "Second question?", "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]},
        }]})
        with playwright.sync_playwright() as runner:
            try:
                browser = runner.webkit.launch()
            except Exception:
                pytest.skip("Playwright WebKit is not installed")
            page = browser.new_context(**dict(runner.devices["iPad Pro 11"])).new_page()
            page.set_default_timeout(8000)
            page.goto(base + "#view=review", wait_until="networkidle")
            _open_rail(page)
            assert _needs(page) == 2
            # Every redraw after the tap: the card must never come back under Needs you.
            page.evaluate("""() => { window.__bounced = 0;
                new MutationObserver(() => { if (document.querySelector('#comment-list .sec-needs [data-comment-id="question-11"]')) window.__bounced++; })
                  .observe(document.getElementById('comment-list'), { subtree: true, childList: true, attributes: true, attributeFilter: ['class'] }); }""")
            page.locator(CARD + ' [data-decision-action="later"]').tap()
            page.locator('[data-section-toggle="later"]').wait_for()
            page.wait_for_timeout(1500)  # the post, its refresh and a poll
            assert page.evaluate("() => window.__bounced") == 0
            assert page.locator('[data-section-toggle="later"]').get_attribute("aria-expanded") == "false"
            assert page.locator('.sec-later .badge').text_content() == "1"
            assert _needs(page) == 1
            assert json.loads((directory / "comments.json").read_text())["anchors"]["d:q11"][0]["answer_later"]

            page.reload(wait_until="networkidle")
            _open_rail(page)
            assert page.locator('.sec-later .badge').text_content() == "1"
            assert _needs(page) == 1

            page.locator('[data-section-toggle="later"]').tap()
            page.locator(CARD + " .decision-btn").first.tap()
            page.locator('[data-section-toggle="later"]').wait_for(state="detached")
            # The rail moves the card at once; the server's write can land a moment later under load.
            for _ in range(50):
                stored = json.loads((directory / "comments.json").read_text())["anchors"]["d:q11"][0]
                if stored.get("decision"):
                    break
                page.wait_for_timeout(100)
            assert stored["decision"]["verdict"] and "answer_later" not in stored
            browser.close()
    finally:
        _stop(server)
