"""Library approval: see what needs you, approve a draft in one action, turn
approved copy into a new draft and approve it, and Discard an approval."""

import pytest
from single_page import browser_page, go, history
from test_card_layout import CHROME
from test_workspace_intent import _page

from agent_annotate.copy_state import load_copy, save_copy

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect
pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")


def _revision(rid, status, text, author="agent:copy", day=1):
    return {"id": rid, "created_at": f"2026-10-0{day}T10:00:00Z", "author": {"id": author},
            "status": status, "delta": {"ops": [{"insert": text + "\n"}]}}


@pytest.fixture
def library(tmp_path):
    directory = _page(tmp_path)
    save_copy(directory, {"groups": [{"id": "home", "label": "Home"}], "blocks": [
        {"id": "tagline", "title": "home.tagline", "where": "Home tagline", "group": "home", "status": "needs_you",
         "current": "r1", "revisions": [_revision("r1", "approved", "Knives for every kitchen"),
                                        _revision("r2", "draft", "Knives for every cook", day=2)]},
        {"id": "footer", "title": "home.footer", "where": "Home footer", "group": "home", "status": "done",
         "current": "r1", "revisions": [_revision("r1", "approved", "Made in Iowa")]},
        {"id": "held", "title": "home.held", "where": "Home held line", "group": "home", "status": "held",
         "held_note": "held by an earlier answer", "current": "r1", "revisions": [_revision("r1", "approved", "Held line")]},
    ]})
    return directory


def needs(page):
    return page.locator('#sp-list-body .sec[data-section="needs"] .sp-row')


@pytest.mark.parametrize("width", [1440, 390])
def test_needs_you_approve_edit_approved_and_discard(tmp_path, library, width):
    before = load_copy(library)
    with browser_page(tmp_path, library, width=width) as (page, _):
        go(page, "library", list="1")
        # See what needs you: only the draft, not approved or held copy.
        expect(needs(page)).to_have_count(1)
        assert needs(page).first.get_attribute("data-item") == "tagline"
        go(page, "library", item="tagline")
        card = page.locator("#sp-approve")
        expect(card).to_contain_text("not approved yet")
        expect(card.locator("ins")).to_have_text("cook")
        expect(card.locator("del")).to_have_text("kitchen")
        # Unsaved typing holds the approval back until it is saved.
        editor = page.locator("#sp-editor .ql-editor")
        editor.click()
        editor.press("End")
        editor.type("!")
        expect(page.locator("#sp-approve-btn")).to_be_disabled()
        expect(page.locator("#sp-approve-hint")).to_have_text("Save your edit first, then approve it.")
        page.locator("#sp-discard").click()
        # Approve as is: one action.
        page.get_by_role("button", name="Approve this draft").click()
        expect(page.locator("#sp-approve.is-approved")).to_be_visible()
        block = load_copy(library)["blocks"][0]
        assert block["status"] == "done" and block["current"] == block["revisions"][-1]["id"]
        assert block["revisions"][-1]["status"] == "approved" and block["revisions"][:2] == before["blocks"][0]["revisions"]
        expect(page.locator("#sp-item h2 .chip")).to_have_text("Approved")
        go(page, "library", list="1")
        expect(needs(page)).to_have_count(0)
        # Edit approved copy into a new draft, save it, approve it.
        go(page, "library", item="footer")
        expect(page.locator("#sp-approve.is-approved")).to_contain_text("starts a new draft")
        editor.click()
        editor.press("End")
        editor.type(" since 2019")
        page.locator("#sp-save").click()
        expect(page.locator("#sp-approve")).to_contain_text("not approved yet")
        expect(page.locator("#sp-approve ins")).to_have_text("since 2019")
        go(page, "library", list="1")
        expect(needs(page)).to_have_count(1)
        go(page, "library", item="footer")
        page.get_by_role("button", name="Approve this draft").click()
        expect(page.locator("#sp-approve.is-approved")).to_be_visible()
        footer = load_copy(library)["blocks"][1]
        assert [r["status"] for r in footer["revisions"]] == ["approved", "proposed", "approved"]
        assert footer["current"] == footer["revisions"][-1]["id"] and footer["status"] == "done"
        # History lists the agent draft and the approvals.
        go(page, "library", item="tagline")
        history(page)
        hist = page.locator("#hist-library")
        expect(hist).to_contain_text("draft")
        expect(hist).to_contain_text("approved · not sent yet")
        # Held copy stays held; Discard undoes the unsent approvals.
        assert load_copy(library)["blocks"][2] == before["blocks"][2]
        status = page.evaluate("() => fetch('./api/rounds/discard', {method: 'POST'}).then(r => r.status)")
        assert status == 200
        assert load_copy(library) == before
