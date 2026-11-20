"""A question asked again in the same words under a new number shows the earlier answer (agent-annotate-b15).

Rebex re-asked "Approve the new … image?" as #367 after Chang answered #352
"Changes needed", so the new card read as a duplicate. The new card now says
what he answered and when, in the rail and in the document.
"""

import json
import socket

import pytest
from single_page import CHROME, ready
from test_keep_drafts import _directory, _start, _stop

playwright = pytest.importorskip("playwright.sync_api")

LINE = "You answered this on Oct 1: Ship later — Wait for the store review"


def _earlier(number, **decision):
    return {
        "id": f"question-{number}", "number": number, "anchor_id": f"d:q{number}", "version": "v1",
        "author": "agent:review-test", "created_at": "2026-10-01T08:00:00Z", "status": "addressed_by_agent",
        "text": "When should we release?",
        "decision_request": {"prompt": "  when SHOULD we\nrelease? ", "options": [{"id": "now", "label": "Ship now"}, {"id": "later", "label": "Ship later"}],
                             "requested_at": "2026-10-01T08:00:00Z"},
        "decision": {"id": f"d{number}", "verdict": "select", "option_id": "later", "text": "Ship later\n\nWait for the store review",
                     "by": "reviewer@example.com", "ts": "2026-10-01T09:00:00Z", **decision},
    }


def test_a_reasked_question_shows_the_earlier_sent_answer_in_rail_and_document(tmp_path):
    directory = _directory(tmp_path)
    path = directory / "comments.json"
    store = json.loads(path.read_text())
    store["anchors"]["d:q5"] = [_earlier(5, delivery_id="del-5")]
    # A draft and a discarded pick are not answers the agent has: never shown.
    store["anchors"]["d:q6"] = [_earlier(6, round_pending=True, ts="2026-10-01T09:30:00Z", text="Draft only")]
    store["anchors"]["d:q7"] = [_earlier(7, discarded=True, delivery_id="del-7", ts="2026-10-01T09:45:00Z", text="Discarded")]
    path.write_text(json.dumps(store))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = _start(tmp_path, directory, port)
    try:
        with playwright.sync_playwright() as runner:
            if not CHROME.exists():
                pytest.skip("Google Chrome is not installed")
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 960}, locale="en-US", timezone_id="UTC")
                page.set_default_timeout(8000)
                page.goto(f"http://127.0.0.1:{port}/#view=review", wait_until="networkidle")
                ready(page)
                rail = page.locator('#comment-list [data-comment-id="question-11"] .decision-prior')
                rail.wait_for()
                assert rail.inner_text() == LINE
                doc = page.frame_locator("#content-frame").locator('[data-strip-item="question-11"] .annotate-decision-prior')
                doc.wait_for()
                assert doc.inner_text() == LINE
                # The earlier cards themselves are not re-asks of anything.
                assert page.locator(".decision-prior").count() == 1
            finally:
                browser.close()
    finally:
        _stop(server)
