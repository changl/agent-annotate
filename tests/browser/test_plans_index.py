"""Plans opens on the topic index (cards #8 and #9, 2026-10-31), on the iPad:
sections open and close (rows built only when open), search, Move to… and the
dropdown kept beside it."""

import json

import pytest
from test_card_layout import _page, _serve

from agent_annotate.categories import publish_plan_revision

playwright = pytest.importorskip("playwright.sync_api")


def _plans(slug_dir):
    publish_plan_revision(slug_dir, "tester-tracking", "<h1>Tester tracking</h1>", title="Tester tracking", section="tracking")
    publish_plan_revision(slug_dir, "route-central", "<h1>Route central</h1>", title="Route central plan", section="approved")
    publish_plan_revision(slug_dir, "dns-records", "<h1>DNS records</h1>", title="DNS records")
    publish_plan_revision(slug_dir, "rally-archive", "<h1>Archive</h1>", title="Rally archive 2026-10")
    meta = slug_dir / "plans" / "rally-archive" / "meta.json"
    meta.write_text(json.dumps({**json.loads(meta.read_text()), "section": "archive"}))
    store = json.loads((slug_dir / "comments.json").read_text())
    store["approved_plans"] = {
        "decision-route-row": {"title": "Add a Route planner row?", "current": "v1", "managed": True,
                               "history": [{"version": "v1", "label": "Decided"}]},
        "rally-email": {"title": "Send the rally email?", "current": "v1", "section": "hidden", "managed": True,
                        "history": [{"version": "v1", "label": "Approved"}]}}
    (slug_dir / "comments.json").write_text(json.dumps(store))
    (slug_dir / "plan-topics.json").write_text(json.dumps({"topics": [
        {"name": "Rally & navigation", "words": ["route", "rally"]}, {"name": "Release & testing", "words": ["uat"]}]}))


def test_plans_index_on_the_ipad(tmp_path):
    slug_dir = _page(tmp_path)
    _plans(slug_dir)
    process, base = _serve(tmp_path, slug_dir)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.webkit.launch()
            page = browser.new_context(**dict(runner.devices["iPad Pro 11"])).new_page()
            page.set_default_timeout(8000)
            expect = playwright.expect
            page.goto(base + "#view=plans", wait_until="networkidle")
            page.locator('body[data-ready="1"]').wait_for(state="attached")
            index = page.locator("#plans-index")
            expect(index).to_be_visible()
            expect(page.locator("#content-frame")).to_be_hidden()
            assert page.locator("#view-hd-plan option").first.text_content() == "Go to a plan…"
            expect(page.locator("#view-hd-plan")).to_be_visible()

            # Tracking pinned, Unsorted next, then topics; hidden and archive out.
            assert index.locator(".pi-sec").evaluate_all("els => els.map(e => e.dataset.key)") == \
                ["tracking", "Unsorted", "Rally & navigation"]
            expect(index).not_to_contain_text("Send the rally email?")
            expect(index).not_to_contain_text("Rally archive")
            rally = index.locator(".pi-sec[data-key='Rally & navigation']")
            expect(rally.locator(".pi-hd .badge")).to_have_text("2")
            assert rally.locator(".pi-body").inner_html() == ""  # built only when opened

            rally.locator(".pi-toggle").first.tap()
            expect(rally.locator(".pi-toggle").first).to_have_attribute("aria-expanded", "true")
            expect(rally.locator(".pi-row", has_text="Route central plan").locator(".pi-tag")).to_have_text("Approved")
            decisions = rally.locator(".pi-sub")
            expect(decisions).to_contain_text("1")
            expect(rally).not_to_contain_text("Add a Route planner row?")
            decisions.tap()
            expect(rally).to_contain_text("Add a Route planner row?")
            rally.locator(".pi-toggle").first.tap()
            expect(rally.locator(".pi-body")).to_be_hidden()
            assert rally.locator(".pi-body").inner_html() == ""

            page.locator("#pi-search").fill("dns")
            expect(index.locator(".pi-row")).to_have_count(1)
            expect(index.locator(".pi-row")).to_contain_text("DNS records")
            page.locator("#pi-search").fill("")

            # Move to… a new topic: pinned, remembered as a rule, Unsorted gone.
            page.once("dialog", lambda d: d.accept("Operations"))
            index.locator(".pi-unsorted .pi-row", has_text="DNS records").locator("select.pi-move").select_option("+new")
            expect(page.locator("#pi-note")).to_contain_text("Moved “DNS records” to Operations")
            expect(index.locator(".pi-sec[data-key='Unsorted']")).to_have_count(0)
            expect(index.locator(".pi-sec[data-key='Operations']")).to_contain_text("DNS records")
            stored = json.loads((slug_dir / "plan-topics.json").read_text())
            assert stored["placed"] == {"dns-records": "Operations"}
            assert stored["learned"] == [{"words": "dns records", "topic": "Operations"}]

            # A row opens its plan; All plans comes back to the index.
            index.locator(".pi-open", has_text="DNS records").tap()
            expect(page.frame_locator("#content-frame").locator("h1")).to_have_text("DNS records")
            expect(index).to_be_hidden()
            expect(page.locator("#view-hd-plan")).to_have_value("dns-records")
            page.locator("#view-hd-index").tap()
            expect(index).to_be_visible()
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
