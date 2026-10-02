"""Native Progress is compact, scrollable, persistent, and separate from Feedback."""

import json
import urllib.request

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from test_card_layout import CHROME, _serve  # noqa: E402

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
            page.locator('[data-workspace-tab="progress"]').click()
            panel = page.locator("#project-panel")
            panel.wait_for(state="visible")
            assert page.locator("#project-toggle").count() == 0
            assert panel.get_attribute("open") is not None
            assert page.locator('#content-frame').is_hidden()
            assert page.locator('#drawer').is_hidden()
            links = panel.locator('details[data-module="resources"]')
            assert links.get_attribute("open") is None
            links.locator("summary").click()
            assert links.locator("a").count() == 12
            assert page.evaluate("localStorage.getItem('annotate:project:/:resources')") == 'open'
            assert panel.evaluate("el => getComputedStyle(el).overflowY") == "visible"
            page.reload(wait_until="networkidle")
            panel.wait_for(state="visible")
            assert panel.count() == 1
            assert links.get_attribute("open") is not None
            assert links.locator("a").first.is_visible()
            assert links.locator("a").first.get_attribute("href") == "https://example.test/0"
            # Progress remains independent of document versions and iframe adoption.
            page.goto(base + '?v=v1', wait_until='networkidle')
            panel.wait_for(state='visible')
            assert panel.count() == 1 and links.get_attribute('open') is not None
            assert page.locator('#hdr-title').inner_text() == 'Review workspace'
            page.evaluate("""() => {
                const frame = document.getElementById('content-frame');
                frame.srcdoc = frame.contentDocument.documentElement.outerHTML;
            }""")
            assert panel.count() == 1
            page.goto(base + '?v=v2', wait_until='networkidle')
            panel.wait_for(state='visible')
            assert page.locator('#content-frame').get_attribute('srcdoc') is None
            assert panel.count() == 1 and links.get_attribute('open') is not None
            # A large progress module scrolls inside the content area, while tabs remain visible.
            changed = dict(project, modules=project['modules'] + [{
                'id':'notes','title':'Evidence notes','kind':'notes',
                'items':[{'text':f'Confirmed observation {number}: '+ 'detail ' * 30} for number in range(40)]
            }])
            save_project(directory, changed)
            page.reload(wait_until='networkidle')
            panel.wait_for(state='visible')
            notes = panel.locator('[data-module="notes"]')
            if notes.get_attribute('open') is None:
                notes.locator('summary').click()
            area = page.locator('#frame-area')
            assert area.evaluate('el => el.scrollHeight > el.clientHeight')
            area.evaluate('el => { el.scrollTop = el.scrollHeight; }')
            assert area.evaluate('el => el.scrollTop') > 0
            assert page.locator('#workspace-tabs').is_visible()
            page.locator('[data-workspace-tab="feedback"]').click()
            page.locator('[data-filter="waiting"]').click()
            assert page.locator(f'.citem[data-comment-id="{cid}"]').is_visible()
            assert panel.is_hidden(), 'Progress never duplicates feedback content'
            page.screenshot(path=f"/tmp/annotate-project-summary-{width}.png", full_page=True)
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
