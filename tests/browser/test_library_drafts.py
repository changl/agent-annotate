"""agent-annotate-b0f: Library keeps the reviewer's unsaved work.

The PR #48 review found Restore throwing away unsaved editor changes without a
word, and a comment started on a selected phrase keeping its text across a
reload but losing the phrase it quoted.
"""

import json

import pytest
from single_page import browser_page, go, history
from test_card_layout import CHROME
from test_copy_editor import copy_site, editor  # noqa: F401

from agent_annotate.copy_state import load_copy

playwright = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")


def test_restore_asks_before_discarding_unsaved_edits(tmp_path, copy_site):  # noqa: F811
    with browser_page(tmp_path, copy_site) as (page, _):
        go(page, "library", item="hero")
        editor(page).fill("Saved headline")
        page.locator("#sp-save").click()
        page.locator("#sp-edit-status").filter(has_text="Saved").wait_for()
        editor(page).fill("Unsaved headline")
        page.locator("#sp-edit-status").filter(has_text="Draft kept").wait_for()
        history(page)
        asked = []
        page.once("dialog", lambda d: (asked.append(d.message), d.dismiss()))
        page.locator("#hist-library [data-restore]").first.click()
        page.wait_for_timeout(500)
        assert asked, "Restore discarded unsaved edits without asking"
        assert editor(page).inner_text().strip() == "Unsaved headline"
        assert len(load_copy(copy_site)["blocks"][0]["revisions"]) == 3
        page.reload(wait_until="networkidle")
        go(page, "library", item="hero")
        assert editor(page).inner_text().strip() == "Unsaved headline"
        # Accepting restores.
        history(page)
        page.once("dialog", lambda d: d.accept())
        page.locator("#hist-library [data-restore]").first.click()
        page.locator("#sp-edit-status").filter(has_text="Saved").wait_for()
        assert len(load_copy(copy_site)["blocks"][0]["revisions"]) == 4
        assert "Unsaved headline" not in editor(page).inner_text()


def test_restore_without_unsaved_edits_does_not_ask(tmp_path, copy_site):  # noqa: F811
    with browser_page(tmp_path, copy_site) as (page, _):
        go(page, "library", item="hero")
        editor(page).fill("Saved headline")
        page.locator("#sp-save").click()
        page.locator("#sp-edit-status").filter(has_text="Saved").wait_for()
        history(page)
        asked = []
        page.on("dialog", lambda d: (asked.append(d.message), d.dismiss()))
        page.locator("#hist-library [data-restore]").first.click()
        page.wait_for_function("() => !document.querySelector('#sp-editor').innerText.includes('Saved headline')")
        assert not asked
        assert len(load_copy(copy_site)["blocks"][0]["revisions"]) == 4


def test_phrase_comment_keeps_its_quote_across_reload(tmp_path, copy_site):  # noqa: F811
    with browser_page(tmp_path, copy_site) as (page, _):
        go(page, "library", item="hero")
        editor(page).wait_for()
        page.evaluate("() => Quill.find(document.querySelector('#sp-editor')).setSelection(0, 8, 'user')")
        page.locator("#sp-comment-sel").click()
        playwright.expect(page.locator("#sp-compose-quote")).to_have_text("“Everyday”")
        page.locator("#sp-compose-ta").fill("Too generic")
        page.reload(wait_until="networkidle")
        go(page, "library", item="hero")
        playwright.expect(page.locator("#sp-compose-ta")).to_have_value("Too generic")
        playwright.expect(page.locator("#sp-compose-quote")).to_have_text("“Everyday”")
        page.locator("#sp-compose-save").click()
        page.locator('#rail-library [data-cid] .unified-selected-quote').filter(has_text="Everyday").wait_for()
        store = json.loads((copy_site / "comments.json").read_text())
        saved = [c for items in store["anchors"].values() for c in items if c.get("text") == "Too generic"]
        assert saved and saved[0]["target"]["selected_quote"] == "Everyday"
        # Saved: the next comment starts without a quote, after a reload too.
        page.reload(wait_until="networkidle")
        go(page, "library", item="hero")
        assert page.locator("#sp-compose-quote").is_hidden()
