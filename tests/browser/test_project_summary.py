"""Project information is compact, expandable and part of document scrolling."""

import json
import urllib.request

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from test_card_layout import CHROME, _serve, _wait  # noqa: E402

from agent_annotate.pagegen import generate  # noqa: E402
from agent_annotate.project_state import save_project  # noqa: E402


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width", [1440, 390])
def test_summary_scrolls_with_document_and_keeps_expansion_across_versions(tmp_path, width):
    directory = tmp_path / "review"
    source = tmp_path / "page.md"
    body = "## Progress\n\n" + "\n\n".join(f"Update {n}: details available for review." for n in range(60))
    for version in ("v1", "v2"):
        source.write_text(f"---\ntitle: Review progress\nversion: {version}\nfull_plan: true\nother_files_required: none\n---\n\n" + body.replace("Update", version + " update"))
        generate(source, directory)
    meta = json.loads((directory / "current.meta.json").read_text())
    meta["current"] = "v2"
    meta["history"].append({"version": "v2", "label": "Second version"})
    (directory / "current.meta.json").write_text(json.dumps(meta))
    project = {"title": "Review workspace", "modules": [
        {"id": "resources", "title": "Links", "kind": "links", "items": [
            {"label": f"Evidence {n}", "url": f"https://example.test/{n}"} for n in range(12)]},
        {"id": "progress", "title": "Status", "kind": "progress", "items": [
            {"label": "UI repair", "status": "done"}]},
    ]}
    save_project(directory, project)
    process, base = _serve(tmp_path, directory)
    try:
        request = urllib.request.Request(base + "api/comments", method="POST",
            data=json.dumps({"anchor_id": "s:progress:p1", "text": "Pin geometry", "version": "v2"}).encode(),
            headers={"Content-Type": "application/json", "X-Annotate-Agent": "agent:summary-test"})
        with urllib.request.urlopen(request) as response:
            cid = json.load(response)["id"]
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.goto(base, wait_until="networkidle")
            frame = page.frame_locator("#content-frame")
            panel = frame.locator("#project-panel")
            panel.wait_for(state="visible")
            assert page.locator("#project-toggle").count() == 0
            page.locator('[data-workspace-tab="progress"]').click()
            assert panel.get_attribute("open") is not None
            assert frame.locator('body').evaluate("el => el.classList.contains('annotate-progress-only')")
            page.locator('[data-workspace-tab="feedback"]').click()
            if width <= 1160:
                page.locator('#drawer-collapse').click()
            pin = frame.locator(f'[data-pin-comments="{cid}"]').first
            pin.wait_for(state="visible")
            def pin_offset():
                return pin.evaluate("el => el.getBoundingClientRect().y - document.querySelector('[data-anchor-id=\"s:progress:p1\"]').getBoundingClientRect().y")
            offset = pin_offset()
            links = panel.locator('details[data-module="resources"]')
            assert links.get_attribute("open") is None
            links.locator("summary").click()
            _wait(lambda: abs(pin_offset() - offset) < 2, page)
            assert links.locator("a").count() == 12
            assert page.evaluate("localStorage.getItem('annotate:project:/:resources')") == 'open'
            assert panel.evaluate("el => getComputedStyle(el).overflowY") == "visible"
            page.reload(wait_until="networkidle")
            if width <= 1160:
                page.locator('#drawer-collapse').click()
            assert panel.get_attribute("open") is not None
            assert links.get_attribute("open") is not None, page.evaluate('JSON.stringify(localStorage)')
            assert links.locator("a").first.is_visible()
            panel.evaluate("el => window.scrollTo({top: el.offsetHeight + 160, behavior: 'instant'})")
            assert panel.evaluate("el => el.getBoundingClientRect().bottom < 0")
            assert page.locator("#content-frame").bounding_box()["height"] > 700
            if width > 1160:
                page.locator('[data-workspace-tab="feedback"]').click()
                page.locator('button[data-version="v1"]').click()
                page.locator('[data-workspace-tab="progress"]').click()
            else:
                page.locator(".mobile-version-select").select_option("v1")
            panel.wait_for(state="visible")
            assert frame.locator("#project-panel").count() == 1
            assert panel.get_attribute("open") is not None
            assert links.get_attribute("open") is not None
            assert panel.locator("a").first.get_attribute("href") == "https://example.test/0"
            page.locator('[data-workspace-tab="progress"]').click()
            page.evaluate("""() => {
                const frame = document.getElementById('content-frame');
                frame.srcdoc = frame.contentDocument.documentElement.outerHTML;
            }""")
            panel.wait_for(state="visible")
            assert panel.count() == 1
            panel.locator(":scope > summary").click()
            assert panel.get_attribute("open") is None
            if width > 1160:
                page.locator('[data-workspace-tab="feedback"]').click()
                page.locator('button[data-version="v2"]').click()
                page.locator('[data-workspace-tab="progress"]').click()
            else:
                page.locator(".mobile-version-select").select_option("v2")
            panel.wait_for(state="visible")
            assert panel.count() == 1
            assert page.locator("#content-frame").get_attribute("srcdoc") is None
            page.screenshot(path=f"/tmp/annotate-project-summary-{width}.png", full_page=True)
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
