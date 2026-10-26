"""Plans opens on what the reviewer asked to track; agent reference comes last.

Chang, 2026-10-25, on FLD: the Plans tab opened on a one-off decision and listed
70 filed answers before his Tester tracking plan.
"""

import json

import pytest
from test_card_layout import CHROME, _page, _serve

from agent_annotate.categories import publish_plan_revision

playwright = pytest.importorskip("playwright.sync_api")


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_plans_picker_sections_and_default(tmp_path):
    slug_dir = _page(tmp_path)
    publish_plan_revision(slug_dir, "dns-records", "<h1>DNS records</h1>", title="DNS records")
    publish_plan_revision(slug_dir, "tester-tracking", "<h1>Tester tracking</h1>", title="Tester tracking", section="tracking")
    publish_plan_revision(slug_dir, "route-central", "<h1>Route central</h1>", title="Route central", section="approved")
    store = json.loads((slug_dir / "comments.json").read_text())
    store["approved_plans"] = {"rally-email": {"title": "Send the rally email?", "current": "v1", "section": "hidden",
                                               "history": [{"version": "v1", "label": "Approved"}]}}
    (slug_dir / "comments.json").write_text(json.dumps(store))
    process, base = _serve(tmp_path, slug_dir)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.set_default_timeout(5000)
            page.goto(base + "#view=plans", wait_until="networkidle")
            pick = page.locator("#view-hd-plan")
            playwright.expect(pick).to_be_visible()
            assert pick.locator("optgroup").evaluate_all("els => els.map(e => e.label)") == ["Tracking", "Approved plans", "Agent reference"]
            assert pick.locator("option").evaluate_all("els => els.map(e => e.value)") == ["tester-tracking", "route-central", "dns-records"]
            assert pick.input_value() == "tester-tracking"
            playwright.expect(page.frame_locator("#content-frame").locator("h1")).to_have_text("Tester tracking")
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
