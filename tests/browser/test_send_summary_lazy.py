"""Send review: 'Not in this Send' starts collapsed and builds its rows only when opened (Chang, 2026-10-31)."""

import socket

import pytest
from test_keep_drafts import _directory, _loaded, _start, _stop

playwright = pytest.importorskip("playwright.sync_api")


def test_not_in_this_send_is_collapsed_and_built_on_open(tmp_path):
    directory = _directory(tmp_path)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = _start(tmp_path, directory, port)
    try:
        with playwright.sync_playwright() as runner:
            try:
                browser = runner.webkit.launch()
            except Exception:
                pytest.skip("Playwright WebKit is not installed")
            page = browser.new_context(**dict(runner.devices["iPad Pro 11"])).new_page()
            page.set_default_timeout(8000)
            page.goto(f"http://127.0.0.1:{port}/#view=review", wait_until="networkidle")
            _loaded(page)
            page.evaluate("window.AA.send.open()")
            head = page.locator(".sum-rest-hdr")
            head.wait_for()
            assert head.get_attribute("aria-expanded") == "false"
            assert "1 not answered" in head.inner_text()
            assert page.locator('#round-confirm-backdrop [data-sum-id="question-11"]').count() == 0

            head.tap()
            row = page.locator('#round-confirm-backdrop [data-sum-id="question-11"]')
            row.wait_for()
            assert page.locator(".sum-rest-hdr").get_attribute("aria-expanded") == "true"

            row.locator('[data-sum-edit="question-11"]').tap()
            row.locator(".decision-btn-sum").first.tap()
            # Answered now: it moves into this Send's verdicts and the group empties.
            page.wait_for_function("() => !document.querySelector('.sum-rest-hdr')")
            moved = page.locator('#round-confirm-backdrop [data-sum-id="question-11"]')
            assert moved.locator(".rl-sent").count() == 0 and "is-sent" not in moved.get_attribute("class")
            browser.close()
    finally:
        _stop(server)
