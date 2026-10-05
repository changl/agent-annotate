"""Library Quill formatting, safe paste, retry, history, and browser drafts."""

import pytest
from single_page import browser_page, go, history
from test_card_layout import CHROME
from test_workspace_intent import _page

from agent_annotate.copy_state import load_copy, save_copy

playwright = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")


@pytest.fixture
def copy_site(tmp_path):
    directory = _page(tmp_path)
    revisions = [
        {
            "id": "old-1",
            "created_at": "2026-10-01T10:00:00Z",
            "author": {"id": "agent:copy"},
            "status": "draft",
            "delta": {"ops": [{"insert": "Old headline\n"}]},
        },
        {
            "id": "draft-2",
            "created_at": "2026-10-02T10:00:00Z",
            "author": {"id": "agent:copy"},
            "status": "draft",
            "delta": {
                "ops": [
                    {"insert": "Everyday essentials", "attributes": {"bold": True}},
                    {"insert": "\n"},
                    {"insert": "Shop the collection.\n"},
                ]
            },
        },
    ]
    save_copy(
        directory,
        {
            "blocks": [
                {
                    "id": "hero",
                    "title": "Home hero",
                    "where": "Home hero",
                    "current": "draft-2",
                    "revisions": revisions,
                }
            ]
        },
    )
    return directory


def editor(page):
    return page.locator("#sp-editor .ql-editor")


@pytest.mark.parametrize("width,theme", [(1440, "dark"), (1440, "light"), (390, "dark"), (390, "light")])
def test_copy_format_save_retry_history_and_reopen(tmp_path, copy_site, width, theme):
    with browser_page(tmp_path, copy_site, width=width) as (page, _):
        go(page, "library", item="hero")
        if theme == "light":
            page.locator("#theme-toggle").click()
        assert editor(page).locator("strong").inner_text() == "Everyday essentials"
        editor(page).fill("Made for your day")
        editor(page).press("ControlOrMeta+A")
        if editor(page).locator("strong").count():
            page.get_by_role("button", name="Bold", exact=True).click()
        page.get_by_role("button", name="Bold", exact=True).click()
        page.get_by_role("combobox", name="Text style", exact=True).select_option("2")
        page.get_by_role("button", name="Link", exact=True).click()
        page.get_by_role("textbox", name="Link URL", exact=True).fill("https://example.com/shop")
        assert page.get_by_role("textbox", name="Link URL", exact=True).evaluate(
            "el => el === document.activeElement"
        )
        page.get_by_role("button", name="Apply", exact=True).click()
        assert editor(page).locator("h2 strong").inner_text() == "Made for your day"
        assert editor(page).locator("a").get_attribute("href") == "https://example.com/shop"
        # Simulate one pre-commit transport failure; all successful writes use the real server.
        calls = []

        def fail_once(route):
            calls.append(route.request.post_data_json)
            if len(calls) == 1:
                route.fulfill(
                    status=503, content_type="application/json", body='{"error":"Connection interrupted"}'
                )
            else:
                route.continue_()

        page.route("**/api/copy/hero/revisions", fail_once)
        page.locator("#sp-save").click()
        page.locator("#sp-edit-status").filter(has_text="Could not save").wait_for()
        assert editor(page).locator("h2 strong").inner_text() == "Made for your day"
        page.reload(wait_until="networkidle")
        go(page, "library", item="hero")
        assert editor(page).locator("h2 strong").inner_text() == "Made for your day"
        page.locator("#sp-save").click()
        page.locator("#sp-edit-status").filter(has_text="Saved").wait_for()
        block = load_copy(copy_site)["blocks"][0]
        assert block["current"] == "draft-2" and len(block["revisions"]) == 3
        assert len(calls) == 2
        revision = block["revisions"][-1]
        assert revision["author"] == {"id": "reviewer@example.com", "name": "Browser Reviewer"}
        assert revision["status"] == "proposed" and revision["round_pending"]
        assert {"bold", "link"}.issubset(revision["delta"]["ops"][0]["attributes"])
        assert revision["delta"]["ops"][-1]["attributes"]["header"] == 2
        history(page)
        assert (
            "".join(page.locator("#hist-library del").all_text_contents()).replace(" ", "").strip()
            == "Everydayessentials\nShopthecollection."
        )
        assert (
            "".join(page.locator("#hist-library ins").all_text_contents()).replace(" ", "").strip()
            == "Madeforyourday"
        )
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.reload(wait_until="networkidle")
        go(page, "library", item="hero")
        assert editor(page).locator("h2 strong").inner_text() == "Made for your day"
        assert page.locator("#history-body").is_hidden()


@pytest.mark.xfail(
    strict=True, reason="A3b-P2: Library paste retains about:blank href; server refuses Save with HTTP 400"
)
def test_editor_paste_undo_and_attack_text_stays_safe(tmp_path, copy_site):
    with browser_page(tmp_path, copy_site) as (page, _):
        go(page, "library", item="hero")
        page.evaluate("""() => {
            window.attackExecuted=false;
            const q=Quill.find(document.querySelector('#sp-editor'));
            q.setSelection(0,q.getLength());
            q.clipboard.dangerouslyPasteHTML('<p><strong>Safe bold</strong> <a href="javascript:alert(1)">unsafe link</a><img src=x onerror="window.attackExecuted=true"><iframe src="javascript:alert(1)"></iframe></p>', 'user');
        }""")
        assert editor(page).locator("strong").inner_text() == "Safe bold"
        assert editor(page).locator('img,iframe,script,[href^="javascript:"]').count() == 0
        assert not page.evaluate("window.attackExecuted")
        page.get_by_role("button", name="Undo", exact=True).click()
        assert [line for line in editor(page).inner_text().splitlines() if line] == [
            "Everyday essentials",
            "Shop the collection.",
        ]
        page.get_by_role("button", name="Redo", exact=True).click()
        assert editor(page).locator("strong").inner_text() == "Safe bold"
        with page.expect_response("**/api/copy/hero/revisions") as saved:
            page.locator("#sp-save").click()
        assert saved.value.ok, (saved.value.status, saved.value.text())
        page.locator("#sp-edit-status").filter(has_text="Saved").wait_for()
        delta = load_copy(copy_site)["blocks"][0]["revisions"][-1]["delta"]
        assert all(isinstance(op["insert"], str) for op in delta["ops"])
        assert not any("link" in op.get("attributes", {}) for op in delta["ops"])
        assert not page.evaluate("window.attackExecuted")


@pytest.mark.parametrize("width", [1440, 390])
def test_many_copy_blocks_are_searchable_and_switching_keeps_drafts(tmp_path, copy_site, width):
    data = load_copy(copy_site)
    for index in range(132):
        data["blocks"].append(
            {
                "id": f"field-{index}",
                "title": f"Product field {index:03}",
                "where": f"Product field {index:03}",
                "current": "draft-1",
                "revisions": [
                    {
                        "id": "draft-1",
                        "created_at": "2026-10-02T10:00:00Z",
                        "author": {"id": "agent:copy"},
                        "status": "draft",
                        "delta": {"ops": [{"insert": f"Current field {index}\n"}]},
                    }
                ],
            }
        )
    save_copy(copy_site, data)
    with browser_page(tmp_path, copy_site, width=width) as (page, _):
        go(page, "library", item="hero")
        assert page.locator("#sp-list-body .sp-row").count() == 133
        editor(page).press("ControlOrMeta+End")
        editor(page).press("End")
        editor(page).press_sequentially(" Local draft")
        # Phone uses All copy to return to the same searchable list.
        if width == 390:
            page.locator("#sp-back").click()
        page.locator("#sp-search").fill("Product field 129")
        assert page.locator("#sp-list-body .sp-row").count() == 1
        page.locator('[data-item="field-129"]').click()
        assert editor(page).inner_text().strip() == "Current field 129"
        if width == 390:
            page.locator("#sp-back").click()
        page.locator("#sp-search").fill("")
        page.locator('[data-item="hero"]').click()
        assert "Local draft" in editor(page).inner_text()
        page.reload(wait_until="networkidle")
        go(page, "library", item="hero")
        assert "Local draft" in editor(page).inner_text()
        assert len(load_copy(copy_site)["blocks"][0]["revisions"]) == 2
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="A3b-P4: Library Save retry generates a new request_id and creates a duplicate revision after lost response",
)
def test_retry_after_committed_response_is_lost_creates_one_revision(tmp_path, copy_site):
    with browser_page(tmp_path, copy_site) as (page, _):
        go(page, "library", item="hero")
        calls = []

        def lose_response(route):
            calls.append(route.request.post_data_json)
            if len(calls) == 1:
                response = route.fetch()
                assert response.ok
                route.fulfill(
                    status=503, content_type="application/json", body='{"error":"response lost after commit"}'
                )
            else:
                route.continue_()

        page.route("**/api/copy/hero/revisions", lose_response)
        editor(page).fill("Retry-safe copy.")
        page.locator("#sp-save").click()
        page.locator("#sp-edit-status").filter(has_text="Could not save").wait_for()
        assert len(load_copy(copy_site)["blocks"][0]["revisions"]) == 3
        page.locator("#sp-save").click()
        page.locator("#sp-edit-status").filter(has_text="Saved").wait_for()
        assert len(calls) == 2
        assert len(load_copy(copy_site)["blocks"][0]["revisions"]) == 3
        assert calls[0]["request_id"] == calls[1]["request_id"]
