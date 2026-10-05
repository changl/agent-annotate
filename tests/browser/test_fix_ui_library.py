"""Library fixes from the UI review: UI-3, UI-4, UI-6, UI-7, UI-11, UI-12, UI-16, UI-23 and UI-28."""

import json
import uuid

import pytest
from single_page import browser_page, feedback, go, history, ready
from test_card_layout import CHROME
from test_workspace_intent import _page

from agent_annotate.copy_state import add_browser_revision, load_copy, save_copy

playwright = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")

STALE = (
    "A newer version was saved while you were editing. "
    "Save replaces it with your text; Cancel loads the newer version."
)
TOO_BIG = "Too long to save — shorten the text and try again."
SAVED = "Saved · goes out with Send"


def _revision(text):
    return {
        "id": "seed-1",
        "created_at": "2026-10-01T10:00:00Z",
        "author": {"id": "agent:copy"},
        "status": "draft",
        "delta": {"ops": [{"insert": text + "\n"}]},
    }


def _block(block_id, title, where, group, text, number=None):
    block = {
        "id": block_id,
        "title": title,
        "where": where,
        "group": group,
        "current": "seed-1",
        "revisions": [_revision(text)],
    }
    if number is not None:
        block["number"] = number
    return block


@pytest.fixture
def lib_site(tmp_path):
    directory = _page(tmp_path)
    save_copy(
        directory,
        {
            "blocks": [
                _block("row-14", "home.hero.body", "Home · hero body", "copy", "Start text.", number=14),
                _block("article-1", "What is VG-10 steel?", "Blog · Know your steel", "articles", "Article one."),
                _block(
                    "article-2",
                    "1.4116 vs VG-10: which is right for you?",
                    "Blog · Know your steel",
                    "articles",
                    "Article two.",
                ),
                _block("policy-terms", "policy.terms", "Store page · Terms", "policies", "Terms text."),
            ],
            "groups": [
                {"id": "copy", "label": "Copy"},
                {"id": "articles", "label": "Know your steel articles"},
                {"id": "policies", "label": "Policies"},
            ],
        },
    )
    return directory


def editor(page):
    return page.locator("#sp-editor .ql-editor")


def status(page):
    return page.locator("#sp-edit-status")


def revisions(directory, block_id="row-14"):
    return next(b for b in load_copy(directory)["blocks"] if b["id"] == block_id)["revisions"]


def save_elsewhere(directory, text, block_id="row-14"):
    """Another browser saves a newer revision (the real server-side write path)."""
    add_browser_revision(
        directory,
        block_id,
        {"ops": [{"insert": text + "\n"}]},
        {"id": "other@example.com", "name": "Other Reviewer"},
        base_revision="seed-1",
        request_id=str(uuid.uuid4()),
    )


def comment(page, text):
    feedback(page)
    if page.locator("#sp-compose-box").is_hidden():
        page.locator("#sp-compose-toggle").click()
    page.locator("#sp-compose-ta").fill(text)


# ── UI-4 ──────────────────────────────────────────────────────────────────
def test_toolbar_formats_the_current_selection_after_typing(tmp_path, lib_site):
    with browser_page(tmp_path, lib_site) as (page, _):
        go(page, "library", item="row-14")
        bold = page.locator('#sp-toolbar [data-fmt="bold"]')
        # End of a line: type, click B, type.
        editor(page).click()
        editor(page).press("ControlOrMeta+End")
        editor(page).press("End")
        page.keyboard.type(" one two")
        bold.click()
        page.keyboard.type("THREE")
        assert editor(page).inner_text().strip() == "Start text. one twoTHREE"
        assert editor(page).locator("strong").all_inner_texts() == ["THREE"]
        page.locator("#sp-discard").click()
        playwright.expect(editor(page)).to_have_text("Start text.")
        # Select all, type, click B, type: the typed text is kept.
        editor(page).click()
        editor(page).press("ControlOrMeta+A")
        page.keyboard.type("New line ")
        bold.click()
        page.keyboard.type("bold")
        assert editor(page).inner_text().strip() == "New line bold"
        assert editor(page).locator("strong").all_inner_texts() == ["bold"]
        page.locator("#sp-save").click()
        playwright.expect(status(page)).to_have_text(SAVED)
        assert revisions(lib_site)[-1]["delta"]["ops"] == [
            {"insert": "New line "},
            {"insert": "bold", "attributes": {"bold": True}},
            {"insert": "\n"},
        ]


# ── UI-6 ──────────────────────────────────────────────────────────────────
def test_items_without_a_row_number_show_their_title_and_key(tmp_path, lib_site):
    with browser_page(tmp_path, lib_site) as (page, _):
        go(page, "library", item="article-2")
        names = page.locator('#sp-list-body .sp-row[data-item^="article-"] .citem-node-name').all_text_contents()
        assert names == ["What is VG-10 steel?", "1.4116 vs VG-10: which is right for you?"]
        assert page.locator("#sp-item h2").inner_text().startswith("1.4116 vs VG-10: which is right for you?")
        assert page.locator("#sp-item section > p.muted").inner_text() == "article-2 · Blog · Know your steel"
        go(page, "library", item="policy-terms")
        row = page.locator('#sp-list-body .sp-row[data-item="policy-terms"] .citem-node-name')
        assert row.text_content() == "Terms"
        assert page.locator("#sp-item h2").inner_text().startswith("Terms")
        assert page.locator("#sp-item section > p.muted").inner_text() == "policy.terms · Store page · Terms"
        # Numbered rows keep "#N place" and their key.
        go(page, "library", item="row-14")
        assert page.locator("#sp-item section > p.muted").inner_text() == "home.hero.body · Home · hero body"


# ── UI-7 ──────────────────────────────────────────────────────────────────
def test_reviewer_records_show_the_display_name_not_the_login(tmp_path, lib_site):
    with browser_page(tmp_path, lib_site) as (page, _):
        go(page, "library", item="row-14")
        editor(page).fill("Changed copy.")
        page.locator("#sp-save").click()
        playwright.expect(status(page)).to_have_text(SAVED)
        comment(page, "Please check the tone.")
        page.locator("#sp-compose-save").click()
        page.locator('#rail-library [data-cid] .citem-txt', has_text="Please check the tone.").first.wait_for()
        authors = page.locator("#rail-library .citem-author").all_text_contents()
        assert authors and set(authors) == {"Browser Reviewer"}, authors
        history(page)
        heads = page.locator("#hist-library .hist-head").all_text_contents()
        assert any(h.startswith("Browser Reviewer · edited") for h in heads), heads
        assert any(h.startswith("Browser Reviewer · comment") for h in heads), heads
        assert "reviewer@example.com" not in page.locator("#hist-library").inner_text()


# ── UI-11 ─────────────────────────────────────────────────────────────────
def test_ctrl_enter_in_the_library_comment_box_saves_the_comment(tmp_path, lib_site):
    with browser_page(tmp_path, lib_site) as (page, _):
        go(page, "library", item="row-14")
        comment(page, "Saved from the keyboard")
        page.locator("#sp-compose-ta").press("ControlOrMeta+Enter")
        page.locator('#rail-library [data-cid] .citem-txt', has_text="Saved from the keyboard").first.wait_for()
        assert page.locator("#round-confirm-backdrop").is_hidden()
        assert page.locator("#sp-compose-ta").input_value() == ""
        store = json.loads((lib_site / "comments.json").read_text())
        saved = [c for c in store["anchors"].get("copy:row-14", []) if c["text"] == "Saved from the keyboard"]
        assert len(saved) == 1 and saved[0]["category"] == "library"


# ── UI-12 ─────────────────────────────────────────────────────────────────
def test_unsaved_library_comment_survives_reload_on_its_own_item(tmp_path, lib_site):
    with browser_page(tmp_path, lib_site) as (page, _):
        go(page, "library", item="row-14")
        comment(page, "Half-typed thought")
        page.reload(wait_until="networkidle")
        ready(page)
        go(page, "library", item="row-14")
        feedback(page)
        assert page.locator("#sp-compose-box").is_visible()
        assert page.locator("#sp-compose-ta").input_value() == "Half-typed thought"
        # The draft belongs to its item: another item's box is empty.
        go(page, "library", item="article-1")
        feedback(page)
        assert page.locator("#sp-compose-ta").input_value() == ""
        go(page, "library", item="row-14")
        feedback(page)
        assert page.locator("#sp-compose-ta").input_value() == "Half-typed thought"
        # Save clears the draft.
        page.locator("#sp-compose-save").click()
        page.locator('#rail-library [data-cid] .citem-txt', has_text="Half-typed thought").first.wait_for()
        page.reload(wait_until="networkidle")
        ready(page)
        go(page, "library", item="row-14")
        feedback(page)
        assert page.locator("#sp-compose-ta").input_value() == ""


# ── UI-16 ─────────────────────────────────────────────────────────────────
def test_an_unsent_comment_is_listed_once_in_the_rail(tmp_path, lib_site):
    with browser_page(tmp_path, lib_site) as (page, _):
        go(page, "library", item="row-14")
        comment(page, "Only once")
        page.locator("#sp-compose-save").click()
        page.locator('#rail-library [data-section="ready"] [data-cid]').first.wait_for(state="attached")
        assert page.locator("#rail-library [data-cid]").count() == 1
        assert "No comments on this item yet." in page.locator('#rail-library [data-section="comments"]').inner_text()


# ── UI-23 ─────────────────────────────────────────────────────────────────
def test_a_save_refused_for_size_gives_a_size_hint(tmp_path, lib_site):
    with browser_page(tmp_path, lib_site) as (page, _):
        go(page, "library", item="row-14")
        set_text = "t => { const q = Quill.find(document.querySelector('#sp-editor')); q.setText(t, 'user'); }"
        # Over the copy limit (50,000 characters): the server answers 400.
        page.evaluate(set_text, "word " * 12_000 + "\n")
        page.locator("#sp-save").click()
        playwright.expect(status(page)).to_have_text(TOO_BIG)
        # Over the request limit (256 KB): not sent at all.
        posts = []
        page.on("request", lambda r: posts.append(r.url) if r.method == "POST" and "/api/copy/" in r.url else None)
        page.evaluate("() => { document.querySelector('#sp-edit-status').textContent = ''; }")
        page.evaluate(set_text, "word " * 60_000 + "\n")
        page.locator("#sp-save").click()
        playwright.expect(status(page)).to_have_text(TOO_BIG)
        page.wait_for_timeout(300)
        assert posts == []
        # HTTP 413 from the server says the same.
        page.route(
            "**/api/copy/row-14/revisions",
            lambda route: route.fulfill(status=413, content_type="application/json", body='{"error":"body exceeds limit"}'),
        )
        page.evaluate(set_text, "Short again.\n")
        page.locator("#sp-save").click()
        playwright.expect(status(page)).to_have_text(TOO_BIG)
        assert len(revisions(lib_site)) == 1


# ── UI-3 ──────────────────────────────────────────────────────────────────
def test_open_editor_without_changes_shows_a_revision_saved_elsewhere(tmp_path, lib_site):
    with browser_page(tmp_path, lib_site) as (page, _):
        go(page, "library", item="row-14")
        playwright.expect(editor(page)).to_have_text("Start text.")
        editor(page).click()  # focus in the editor: the shell's own refresh stays quiet
        save_elsewhere(lib_site, "Saved elsewhere.")
        playwright.expect(editor(page)).to_have_text("Saved elsewhere.", timeout=15_000)
        assert page.locator("#sp-save").is_disabled()
        # The next edit is based on the revision now shown.
        editor(page).fill("Mine on top.")
        with page.expect_request("**/api/copy/row-14/revisions") as sent:
            page.locator("#sp-save").click()
        playwright.expect(status(page)).to_have_text(SAVED)
        assert sent.value.post_data_json["base_revision"] == revisions(lib_site)[1]["id"]


def test_unsaved_edit_and_a_newer_revision_show_a_notice_before_any_save(tmp_path, lib_site):
    with browser_page(tmp_path, lib_site) as (page, _):
        go(page, "library", item="row-14")
        editor(page).fill("My text.")
        save_elsewhere(lib_site, "Agent text.")
        posts = []
        page.on(
            "request",
            lambda r: posts.append(r.post_data_json)
            if r.method == "POST" and r.url.endswith("/api/copy/row-14/revisions")
            else None,
        )
        notice_before = status(page).inner_text() == STALE
        page.locator("#sp-save").click()
        if not notice_before:
            # Save meets the newer revision: it shows the notice and posts nothing.
            playwright.expect(status(page)).to_have_text(STALE)
            page.wait_for_timeout(300)
            assert posts == [] and len(revisions(lib_site)) == 2
            assert editor(page).inner_text().strip() == "My text."
            page.locator("#sp-save").click()
        playwright.expect(status(page)).to_have_text(SAVED)
        newer = revisions(lib_site)[1]["id"]
        assert len(posts) == 1 and posts[0]["base_revision"] == newer
        assert [op["insert"] for op in revisions(lib_site)[-1]["delta"]["ops"]] == ["My text.\n"]


def test_unsaved_edit_shows_the_notice_when_the_poll_finds_a_newer_revision(tmp_path, lib_site):
    with browser_page(tmp_path, lib_site) as (page, _):
        go(page, "library", item="row-14")
        editor(page).fill("My text.")
        save_elsewhere(lib_site, "Agent text.")
        playwright.expect(status(page)).to_have_text(STALE, timeout=15_000)
        assert editor(page).inner_text().strip() == "My text."
        # Typing keeps the notice; Cancel loads the newer revision.
        editor(page).press("End")
        page.keyboard.type(" More")
        playwright.expect(status(page)).to_have_text(STALE)
        page.locator("#sp-discard").click()
        playwright.expect(editor(page)).to_have_text("Agent text.")


def test_unsaved_draft_from_an_older_revision_shows_the_notice_after_reload(tmp_path, lib_site):
    with browser_page(tmp_path, lib_site) as (page, _):
        go(page, "library", item="row-14")
        editor(page).fill("My text.")
        save_elsewhere(lib_site, "Agent text.")
        page.reload(wait_until="networkidle")
        ready(page)
        go(page, "library", item="row-14")
        assert editor(page).inner_text().strip() == "My text."
        playwright.expect(status(page)).to_have_text(STALE)


def test_save_refused_with_409_shows_the_notice(tmp_path, lib_site):
    with browser_page(tmp_path, lib_site) as (page, _):
        go(page, "library", item="row-14")
        page.route(
            "**/api/copy/row-14/revisions",
            lambda route: route.fulfill(
                status=409, content_type="application/json", body='{"error":"copy base_revision is not the latest"}'
            ),
        )
        editor(page).fill("My text.")
        page.locator("#sp-save").click()
        playwright.expect(status(page)).to_have_text(STALE)
        assert editor(page).inner_text().strip() == "My text."
        assert page.locator("#sp-save").is_enabled()


# ── UI-28 ─────────────────────────────────────────────────────────────────
def test_restore_says_saved_as_final_does(tmp_path, lib_site):
    with browser_page(tmp_path, lib_site) as (page, _):
        go(page, "library", item="row-14")
        editor(page).fill("Changed.")
        page.locator("#sp-save").click()
        playwright.expect(status(page)).to_have_text(SAVED)
        sent = []

        def without_base(route):
            # The restore route takes base_revision after the backend merge;
            # this worktree's server still takes only revision_id + request_id.
            body = route.request.post_data_json
            sent.append(body)
            body = {k: v for k, v in body.items() if k != "base_revision"}
            route.continue_(post_data=json.dumps(body))

        page.route("**/api/copy/row-14/restore", without_base)
        history(page)
        page.get_by_role("button", name="Restore the earlier text").click()
        playwright.expect(editor(page)).to_have_text("Start text.")
        playwright.expect(status(page)).to_have_text(SAVED)
        assert len(revisions(lib_site)) == 3
        assert sent[0]["revision_id"] == "seed-1" and sent[0]["base_revision"] == revisions(lib_site)[1]["id"]


def test_restore_refused_with_409_shows_the_notice_and_keeps_unsaved_text(tmp_path, lib_site):
    with browser_page(tmp_path, lib_site) as (page, _):
        go(page, "library", item="row-14")
        editor(page).fill("Changed.")
        page.locator("#sp-save").click()
        playwright.expect(status(page)).to_have_text(SAVED)
        editor(page).fill("Unsaved words.")
        page.route(
            "**/api/copy/row-14/restore",
            lambda route: route.fulfill(
                status=409,
                content_type="application/json",
                body='{"error":"copy has a newer revision; reload it before saving"}',
            ),
        )
        history(page)
        page.get_by_role("button", name="Restore the earlier text").click()
        playwright.expect(status(page)).to_have_text(STALE)
        assert editor(page).inner_text().strip() == "Unsaved words."
        assert len(revisions(lib_site)) == 2


def test_first_visit_opens_the_declared_start_item(tmp_path, lib_site):
    with browser_page(tmp_path, lib_site) as (page, base):
        # Simulated: the copy contract has no start_item yet; final/ reads one from its data.
        def with_start(route):
            if route.request.method != "GET":
                return route.continue_()
            response = route.fetch()
            data = response.json()
            data["start_item"] = "article-2"
            route.fulfill(response=response, json=data)

        page.route("**/api/copy", with_start)
        page.reload(wait_until="networkidle")
        ready(page)
        go(page, "library")
        assert page.locator("#sp-list-body .sp-row.hl").get_attribute("data-item") == "article-2"
