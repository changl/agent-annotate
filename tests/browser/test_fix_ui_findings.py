"""Findings fixes from the UI review (UI-1, 7, 8, 9, 11, 12, 22, 28) on small sandboxed fixtures."""

import json
import re

import pytest
from single_page import browser_page, go, history, ready
from test_card_layout import CHROME
from test_single_page_acceptance import workspace  # noqa: F401

from agent_annotate.categories import mark_finding_fixed

playwright = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")

ME = "Browser Reviewer"
LOGIN = "reviewer@example.com"


@pytest.fixture
def findings(workspace):  # noqa: F811
    """The acceptance workspace plus a non-image proof and a second finding.

    finding-21 (Gap-like "Border contrast") is fixed with an image, an HTML
    attachment and a link. finding-22 ("Focus ring") was answered, sent, then
    changed to an answer that is not sent yet.
    """
    attachments = workspace / "attachments"
    (attachments / "report.html").write_text("<!doctype html><title>Report</title><p>Report</p>")
    mark_finding_fixed(
        workspace,
        21,
        by="agent:builder",
        note="Contrast repaired",
        proof=[
            {"label": "Contrast image", "attachment": "proof.svg"},
            {"label": "Full report", "attachment": "report.html"},
            {"label": "Verification report", "url": "https://example.test/proof"},
        ],
    )
    path = workspace / "comments.json"
    store = json.loads(path.read_text())
    base = dict(store["anchors"]["finding:contrast"][0])
    for key in ("fixed", "fixed_history", "resolved_in_version", "round_pending", "reopened"):
        base.pop(key, None)
    second = dict(
        base,
        id="finding-22",
        number=22,
        anchor_id="finding:focus",
        status="open",
        finding={"set": "design", "title": "Focus ring"},
        decision_request={
            "prompt": "Fix the focus ring?",
            "options": [{"id": "fix", "label": "Fix it"}, {"id": "keep", "label": "Keep it"}],
        },
        decision_history=[
            {"verdict": "select", "option_id": "fix", "text": "Fix it", "by": LOGIN, "ts": "2026-10-02T11:00:00Z"}
        ],
        decision={
            "verdict": "select",
            "option_id": "keep",
            "text": "Keep it",
            "by": LOGIN,
            "ts": "2026-10-02T12:00:00Z",
            "round_pending": True,
        },
    )
    store["anchors"]["finding:focus"] = [second]
    path.write_text(json.dumps(store))
    return workspace


def flat(text):
    return re.sub(r"\s+", " ", text).strip()


def open_finding(page, finding_id):
    page.locator(f'#find-register [data-f="{finding_id}"]').click()
    page.locator(f'#rail-findings .citem.hl[data-card="{finding_id}"]').wait_for(state="visible")


def card(directory, anchor):
    return json.loads((directory / "comments.json").read_text())["anchors"][anchor]


def refresh_in_background(page):
    """What the 8 s poll does after a store change while no box has focus."""
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.evaluate("() => document.dispatchEvent(new CustomEvent('annotate:store'))")


def test_ui1_proofs_show_images_inline_and_never_open_attachments_as_pages(tmp_path, findings):
    with browser_page(tmp_path, findings) as (page, _):
        go(page, "findings")
        open_finding(page, "finding-21")
        proof = page.locator("#rail-findings .fix-proof")
        # The image is an <img> only: no click-through to the attachment.
        assert proof.locator(".fix-proof-img a").count() == 0
        assert proof.locator(".fix-proof-img img").get_attribute("src") == "./attachments/proof.svg"
        # A non-image attachment downloads; it never opens as a same-origin page.
        report = proof.locator(".fix-proof-links a", has_text="Full report")
        assert report.get_attribute("href") == "./attachments/report.html"
        assert report.get_attribute("download") is not None
        assert report.get_attribute("target") is None
        # A proof URL stays a plain link to the other site.
        link = proof.locator(".fix-proof-links a", has_text="Verification report")
        assert link.get_attribute("href") == "https://example.test/proof"
        assert link.get_attribute("download") is None
        # No same-origin attachment is reachable through target=_blank.
        assert proof.locator('a[target="_blank"][href^="./attachments/"]').count() == 0


def test_ui7_reviewer_records_show_the_display_name_not_the_login(tmp_path, findings):
    with browser_page(tmp_path, findings) as (page, _):
        go(page, "findings")
        open_finding(page, "finding-21")
        page.locator("#f-compose").fill("Check the hover state too")
        page.locator("#f-save").click()
        page.locator("#rail-findings .citem-txt", has_text="Check the hover state too").wait_for()
        page.locator("#f-reopen").click()
        page.locator("#f-reopen-ta").fill("Still wrong on mobile")
        page.locator("#f-reopen-save").click()
        page.locator("#rail-findings .fix-block.is-reopened").wait_for()
        rail = page.locator("#rail-findings .citem.hl").inner_text()
        assert f"{ME} reopened it" in rail
        assert "agent:builder" in rail  # the agent keeps its id
        assert LOGIN not in rail
        authors = page.locator("#rail-findings .citem.hl .citem-author").all_inner_texts()
        assert ME in authors
        history(page)
        hist = page.locator('.hist-cat[data-cat="findings"] .hist-cat-body')
        hist.locator(".hist-item").first.wait_for()
        text = flat(hist.inner_text())
        assert f"{ME} · reopened" in text and f"{ME} · comment" in text
        assert LOGIN not in text


def test_ui8_a_comment_draft_stays_on_its_own_finding(tmp_path, findings):
    with browser_page(tmp_path, findings) as (page, _):
        go(page, "findings")
        open_finding(page, "finding-21")
        page.locator("#f-compose").fill("Only about contrast")
        open_finding(page, "finding-22")
        assert page.locator("#f-compose").input_value() == ""
        assert page.locator("#f-compose").get_attribute("aria-label").endswith("22")
        open_finding(page, "finding-21")
        assert page.locator("#f-compose").input_value() == "Only about contrast"


def test_ui9_reopen_note_and_form_survive_the_background_refresh(tmp_path, findings):
    with browser_page(tmp_path, findings) as (page, _):
        go(page, "findings")
        open_finding(page, "finding-21")
        page.locator("#f-reopen").click()
        page.locator("#f-reopen-ta").fill("Half-typed reopen note")
        refresh_in_background(page)
        page.wait_for_function("() => !document.activeElement || document.activeElement.id !== 'f-reopen-ta'")
        assert page.locator("#f-reopen-ta").is_visible()
        assert page.locator("#f-reopen-ta").input_value() == "Half-typed reopen note"
        # The comment box keeps its text too.
        page.locator("#f-compose").fill("Half-typed comment")
        refresh_in_background(page)
        assert page.locator("#f-compose").input_value() == "Half-typed comment"


def test_ui11_ctrl_enter_saves_the_comment_and_the_reopen_note(tmp_path, findings):
    with browser_page(tmp_path, findings) as (page, _):
        go(page, "findings")
        open_finding(page, "finding-21")
        assert page.locator("#f-compose").get_attribute("data-submit") == "#f-save"
        page.locator("#f-compose").fill("Saved with the keyboard")
        page.locator("#f-compose").press("Control+Enter")
        page.locator("#rail-findings .citem-txt", has_text="Saved with the keyboard").wait_for()
        assert not page.locator("#round-confirm").is_visible()
        assert any(c.get("text") == "Saved with the keyboard" for c in card(findings, "finding:contrast"))
        page.locator("#f-reopen").click()
        assert page.locator("#f-reopen-ta").get_attribute("data-submit") == "#f-reopen-save"
        page.locator("#f-reopen-ta").fill("Reopened with the keyboard")
        page.locator("#f-reopen-ta").press("Meta+Enter")
        page.locator("#rail-findings .fix-block.is-reopened").wait_for()
        assert not page.locator("#round-confirm").is_visible()
        finding = next(c for c in card(findings, "finding:contrast") if c["id"] == "finding-21")
        assert finding["reopened"][-1]["text"] == "Reopened with the keyboard"


def test_ui12_unsaved_comment_and_reopen_note_survive_reload_and_clear_on_save(tmp_path, findings):
    with browser_page(tmp_path, findings) as (page, _):
        go(page, "findings")
        open_finding(page, "finding-21")
        page.locator("#f-compose").fill("Typed before reload")
        page.locator("#f-reopen").click()
        page.locator("#f-reopen-ta").fill("Reopen note before reload")
        page.reload(wait_until="networkidle")
        ready(page)
        go(page, "findings", f="finding-21")
        page.locator('#rail-findings .citem.hl[data-card="finding-21"]').wait_for()
        assert page.locator("#f-compose").input_value() == "Typed before reload"
        assert page.locator("#f-reopen-ta").input_value() == "Reopen note before reload"
        page.locator("#f-save").click()
        page.locator("#rail-findings .citem-txt", has_text="Typed before reload").wait_for()
        page.locator("#f-reopen-save").click()
        page.locator("#rail-findings .fix-block.is-reopened").wait_for()
        page.reload(wait_until="networkidle")
        ready(page)
        go(page, "findings", f="finding-21")
        page.locator('#rail-findings .citem.hl[data-card="finding-21"]').wait_for()
        assert page.locator("#f-compose").input_value() == ""
        drafts = page.evaluate(
            "() => Object.keys(localStorage).filter(k => k.includes(':find:'))"
            ".map(k => localStorage.getItem(k)).join(' ')"
        )
        assert "Typed before reload" not in drafts and "Reopen note before reload" not in drafts


def test_ui22_history_shows_a_changed_answer_and_whether_it_was_sent(tmp_path, findings):
    with browser_page(tmp_path, findings) as (page, _):
        go(page, "findings")
        open_finding(page, "finding-22")
        history(page)
        hist = page.locator('.hist-cat[data-cat="findings"] .hist-cat-body')
        hist.locator(".hist-item").first.wait_for()
        heads = [flat(h) for h in hist.locator(".hist-head").all_inner_texts()]
        assert any(h.startswith(f"{ME} · answered") for h in heads), heads
        assert any(h.startswith(f"{ME} · changed the answer · not sent yet") for h in heads), heads


@pytest.mark.parametrize("width", [390])
def test_ui28_phone_comment_save_target_is_at_least_44px(tmp_path, findings, width):
    with browser_page(tmp_path, findings, width=width, height=844) as (page, _):
        go(page, "findings", f="finding-21", sheet="open")
        page.locator("#f-save").wait_for(state="visible")
        box = page.locator("#f-save").bounding_box()
        assert box["height"] >= 44 and box["width"] >= 44, box
        page.locator("#f-reopen").click()
        for sel in ("#f-reopen-save", "#f-reopen-cancel"):
            box = page.locator(sel).bounding_box()
            assert box["height"] >= 44 and box["width"] >= 44, (sel, box)
