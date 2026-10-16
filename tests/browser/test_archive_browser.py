"""An archived page is readable, with no Needs-you badge or answer controls."""
import json
import threading

import pytest
from single_page import CHROME, feedback, playwright, ready, section
from test_workspace_intent import _page

from agent_annotate import sync_server

pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")


def test_archived_page_has_no_active_counts_or_answer_controls(tmp_path):
    directory = _page(tmp_path)
    (directory / "archived.json").write_text(json.dumps({"at": "2026-10-16T00:00:00Z", "why": "Superseded"}))
    handler = sync_server.make_handler(artifact_dir=directory, slug="old", bus_dir=tmp_path / "bus",
                                       v2_mode=True, skill_dir=sync_server.WEB_DIR,
                                       local_author="reviewer@example.com", local_author_name="Reviewer")
    server = sync_server.ReviewHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("requestfailed", lambda request: errors.append(request.url + ": " + str(request.failure)))
            page.set_default_timeout(5000)
            page.goto(f"http://127.0.0.1:{server.server_port}/", wait_until="domcontentloaded")
            try:
                ready(page)
            except Exception:
                print(errors)
                print(page.locator("body").inner_text()[:3000])
                raise
            assert page.locator("body").evaluate("el => el.classList.contains('page-read-only')")
            assert page.evaluate("window.AnnotateDocs.counts('review')") == {
                "needs": 0, "unread": 0, "waiting": 0, "total": 0, "pending": 0,
            }
            assert page.locator("#send-btn").is_hidden()
            feedback(page)
            assert page.locator('[data-section="needs"]').count() == 0
            archived = section(page, "archived")
            assert archived.locator(".decision-prompt").count() > 0
            assert archived.locator("textarea").count() == 0
            assert page.locator("#general-feedback-toggle").is_hidden()
            assert not errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
