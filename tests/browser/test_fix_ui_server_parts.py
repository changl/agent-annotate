"""Fix-UI server parts: a Send's delivery result survives a reload (UI-13)."""

import json

import pytest
from single_page import browser_page, feedback, history, ready, section
from test_card_layout import CHROME
from test_single_page_acceptance import workspace  # noqa: F401

playwright = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")

QUEUED = "⏳ Queued — no session listening (1)"


def test_ui13_a_queued_send_still_reads_queued_after_a_reload(tmp_path, workspace):  # noqa: F811
    with browser_page(tmp_path, workspace) as (page, base):
        feedback(page)
        page.locator('.citem[data-comment-id="question-11"] .decision-btn').first.click()
        section(page, "ready")
        page.locator("#send-btn").click()
        page.locator("#round-submit-btn").click()
        page.locator("#round-confirm-backdrop").wait_for(state="hidden")
        playwright.expect(page.locator("#send-note")).to_contain_text(QUEUED)
        rounds = [json.loads(line) for line in (workspace / "rounds.ndjson").read_text().splitlines()]
        assert [r["delivery"] for r in rounds] == ["queued"]
        page.goto(base + "#view=review", wait_until="networkidle")
        ready(page)
        history(page)
        page.locator('[data-hist-filter="all"]').click()
        summary = page.locator("#hist-sent-body .unified-receipt summary")
        summary.wait_for()
        assert summary.inner_text().startswith(QUEUED), summary.inner_text()
        playwright.expect(page.locator("#send-note")).to_contain_text(QUEUED)
