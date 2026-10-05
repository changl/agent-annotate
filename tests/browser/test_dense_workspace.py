"""Feedback is the usable first surface; reference material stays readable."""

import json

import pytest
from single_page import browser_page, feedback, go, history, section
from test_card_layout import CHROME
from test_workspace_intent import _page, _project, _wait_decision

from agent_annotate.project_state import save_project

playwright = pytest.importorskip("playwright.sync_api")


def _workspace(tmp_path):
    directory = _page(tmp_path, title="Rebex decisions")
    project = _project()
    project["title"] = "Rebex"
    save_project(directory, project)
    store = json.loads((directory / "comments.json").read_text())
    answered = dict(
        store["anchors"]["d:q11"][0],
        id="answered-old",
        number=1,
        anchor_id="d:q1",
        text="Previously approved.",
        status="user_confirmed",
        decision={"verdict": "accept", "by": "reviewer@example.com", "ts": "2026-10-01T09:00:00Z"},
    )
    answered["decision_request"] = dict(answered["decision_request"], prompt="Earlier decision")
    store["anchors"]["d:q1"] = [answered]
    # Open questions from previous versions remain actionable in this workspace.
    store["anchors"]["d:q11"][0]["version"] = "v0"
    (directory / "comments.json").write_text(json.dumps(store))
    return directory


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_feedback_first_dense_workspace(tmp_path, width, theme):
    directory = _workspace(tmp_path)
    with browser_page(tmp_path, directory, width=width) as (page, base):
        if theme == "light":
            page.locator("#theme-toggle").click()
        assert page.locator("#hdr-title").inner_text() == "Rebex"
        assert page.locator("body").get_attribute("data-view") == "review"
        assert page.locator("#content-frame").is_visible()
        feedback(page)
        card = page.locator('.citem[data-comment-id="question-11"]')
        assert card.is_visible(), "Unanswered questions from earlier versions remain actionable"
        assert page.locator("#send-count").inner_text() == "0"
        assert page.locator("#send-btn").is_disabled()
        rec = card.locator(".decision-btn.is-recommended")
        assert rec.locator(".decision-rec-badge").text_content() == "Recommended"
        rec.click()
        _wait_decision(page, directory, "select")
        section(page, "ready")
        assert page.locator('#comment-list [data-section="ready"] .badge').inner_text() == "1"
        done = section(page, "done")
        assert done.locator(".citem").count() == 1
        assert done.locator(".citem").get_attribute("data-comment-id") == "answered-old"
        card.locator('[data-decision-action="change"]').click()
        card.locator(".decision-say-ta").fill("Wait for the copy review.")
        card.locator(".decision-btn").nth(1).click()
        _wait_decision(page, directory, "select", "Ship later\n\nWait for the copy review.")
        section(page, "ready")
        card.locator('[data-decision-action="change"]').click()
        draft = "Please also check the tablet layout."
        card.locator(".decision-say-ta").fill(draft)
        page.wait_for_function(
            "() => Object.values(localStorage).some(v => v.includes('Please also check the tablet layout.'))"
        )
        page.reload(wait_until="networkidle")
        section(page, "ready")
        card.locator('[data-decision-action="change"]').click()
        assert card.locator(".decision-say-ta").input_value() == draft
        history(page)
        module = page.locator('#project-panel-review [data-module="progress"]')
        if module.get_attribute("open") is None:
            module.locator("summary").click()
        assert module.locator(".failed-pill").inner_text() == "failed 3x"
        assert page.locator("#hdr-title").inner_text() == "Rebex"
        feedback(page)
        assert card.locator(".decision-say-ta").input_value() == draft
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width", [1440, 390])
def test_copy_is_native_formatted_and_keeps_revision_history(tmp_path, width):
    from agent_annotate.copy_state import load_copy, save_copy

    directory = _workspace(tmp_path)
    save_copy(
        directory,
        {
            "blocks": [
                {
                    "id": "home-hero",
                    "title": "Home hero",
                    "where": "Home hero",
                    "current": "current",
                    "revisions": [
                        {
                            "id": "previous",
                            "created_at": "2026-10-01T10:00:00Z",
                            "author": {"id": "agent:copy"},
                            "status": "draft",
                            "delta": {"ops": [{"insert": "Previous copy.\n"}]},
                        },
                        {
                            "id": "current",
                            "created_at": "2026-10-02T10:00:00Z",
                            "author": {"id": "agent:copy"},
                            "status": "approved",
                            "delta": {
                                "ops": [
                                    {"insert": "Current copy.", "attributes": {"bold": True}},
                                    {"insert": "\n"},
                                ]
                            },
                        },
                    ],
                }
            ]
        },
    )
    with browser_page(tmp_path, directory, width=width) as (page, _):
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        go(page, "library", item="home-hero")
        editor = page.locator("#sp-editor .ql-editor")
        assert editor.locator("strong").inner_text() == "Current copy."
        assert page.locator("#frame-area").is_hidden()
        for theme in ("dark", "light"):
            if page.locator("html").get_attribute("data-theme") != theme:
                page.locator("#theme-toggle").click()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        editor.fill("A clearer proposal.")
        editor.press("ControlOrMeta+A")
        page.get_by_role("button", name="Italic", exact=True).click()
        page.locator("#sp-save").click()
        page.locator("#sp-edit-status").filter(has_text="Saved").wait_for()
        block = load_copy(directory)["blocks"][0]
        assert block["current"] == "current" and len(block["revisions"]) == 3
        assert any(op.get("attributes", {}).get("italic") for op in block["revisions"][-1]["delta"]["ops"])
        assert block["revisions"][-1]["round_pending"]
        history(page)
        assert "Current" in page.locator("#hist-library del").first.inner_text()
        page.reload(wait_until="networkidle")
        go(page, "library", item="home-hero")
        assert editor.locator("em").inner_text() == "A clearer proposal."
        assert not errors
