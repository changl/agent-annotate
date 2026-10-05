"""History project modules scroll and retain expansion across document versions."""

import json

import pytest
from single_page import browser_page, feedback, go, history
from test_card_layout import CHROME
from test_workspace_intent import _page

from agent_annotate.pagegen import generate
from agent_annotate.project_state import save_project


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width", [1440, 390])
def test_summary_scrolls_with_document_and_keeps_expansion_across_versions(tmp_path, width):
    directory = _page(tmp_path)
    source = tmp_path / "v2.md"
    source.write_text(
        "---\ntitle: Second review\nversion: v2\nfull_plan: true\nother_files_required: none\n---\n\n## Checks\n\nSecond document.\n"
    )
    generate(source, directory)
    meta = json.loads((directory / "current.meta.json").read_text())
    meta.update(current="v2", history=[{"version": "v1"}, {"version": "v2"}])
    (directory / "current.meta.json").write_text(json.dumps(meta))
    project = {
        "title": "Review workspace",
        "modules": [
            {
                "id": "resources",
                "title": "Links",
                "kind": "links",
                "items": [{"label": f"Evidence {n}", "url": f"https://example.test/{n}"} for n in range(12)],
            },
            {
                "id": "progress",
                "title": "Status",
                "kind": "progress",
                "items": [{"label": "UI repair", "status": "done"}],
            },
            {
                "id": "notes",
                "title": "Evidence notes",
                "kind": "notes",
                "items": [{"text": f"Confirmed observation {n}: " + "detail " * 30} for n in range(40)],
            },
        ],
    }
    save_project(directory, project)
    with browser_page(tmp_path, directory, width=width, height=900) as (page, base):
        history(page)
        panel = page.locator("#project-panel-review")
        assert panel.count() == 1 and panel.is_visible()
        progress = panel.locator('[data-module="progress"]')
        assert progress.get_attribute("open") is None
        progress.locator("summary").click()
        page.locator("#tab-documents").click()
        assert page.locator("#documents-body a").count() == 12
        assert page.locator("#documents-body a").first.get_attribute("href") == "https://example.test/0"
        for version in ("v1", "v2"):
            go(page, "review", v=version)
            history(page)
            assert progress.get_attribute("open") is not None
            assert panel.count() == 1
            assert page.locator("#hdr-title").inner_text() == "Review workspace"
        page.reload(wait_until="networkidle")
        history(page)
        assert progress.get_attribute("open") is not None
        notes = panel.locator('[data-module="notes"]')
        notes.locator("summary").click()
        area = page.locator("#history-body")
        assert area.evaluate("el => el.scrollHeight > el.clientHeight")
        area.evaluate("el => {el.scrollTop=el.scrollHeight}")
        assert area.evaluate("el => el.scrollTop") > 0
        assert page.locator("#drawer-tabs").is_visible()
        feedback(page)
        assert panel.is_hidden()
        assert page.locator('.citem[data-comment-id="question-11"]').is_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
