"""The rail stays at every width (agent-annotate-lh1).

From 1024px the rail sits inline beside the document; narrower it is a
right-side overlay, full width under 600px. Closed, at every width, it leaves
an edge strip with one button per rail tab and the tabs' counts. Open as the
overlay it is a modal dialog (APG): focus moves in, Tab stays inside, Escape
closes and focus returns to the button that opened it.
"""

import pytest
from single_page import browser_page
from test_card_jump import page_dir  # noqa: F401  (fixture)
from test_card_layout import CHROME, _wait

from agent_annotate.project_state import save_project

playwright = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")

WIDTHS = (1440, 1160, 1024, 768, 390)
FOCUS_IN = "sel => document.querySelector(sel).contains(document.activeElement)"


@pytest.fixture
def rail_page(page_dir):  # noqa: F811
    save_project(page_dir, {"title": "Jump", "modules": [{
        "id": "resources", "title": "Links", "kind": "links",
        "items": [{"label": "Worksheet", "url": "https://example.test/worksheet"}]}]})
    return page_dir


def _strip(page, tab):
    return page.locator(f'#rail-strip [data-rail-open="{tab}"]')


def _open(page):
    return page.evaluate("() => getComputedStyle(document.getElementById('drawer')).visibility === 'visible'"
                         " && document.getElementById('drawer').getBoundingClientRect().width > 0"
                         " && document.getElementById('drawer').getBoundingClientRect().left < innerWidth")


def _set_width(page, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.wait_for_timeout(350)  # the overlay's slide


def test_rail_is_reachable_at_every_width_without_a_floating_button(tmp_path, rail_page):
    with browser_page(tmp_path, rail_page) as (page, _):
        assert page.locator("#mobile-fab").count() == 0
        for width in WIDTHS:
            _set_width(page, width)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width
            compact = page.evaluate("() => AnnotateDocs.isMobileLayout()")
            assert compact == (width < 1024), width
            drawer = page.locator("#drawer")
            if not compact:
                # Inline: a labelled complementary landmark beside the document.
                assert _open(page) and drawer.get_attribute("role") == "complementary"
                assert drawer.get_attribute("aria-label") == "Feedback"
                box = drawer.bounding_box()
                assert box["width"] == 440 and box["x"] + box["width"] == width
                assert page.locator("#drawer-collapse").get_attribute("aria-expanded") == "true"
                assert page.locator("#rail-strip").is_hidden()
                page.locator("#drawer-collapse").click()
                assert page.locator("#rail-strip").is_visible() and not _open(page)
                assert page.evaluate("() => document.activeElement.id") == "drawer-strip"
                page.locator("#drawer-strip").click()
                assert _open(page)
                continue
            # Compact: the strip at the edge, the rail closed until asked for.
            assert page.locator("#rail-strip").is_visible() and not _open(page)
            strip = page.locator("#rail-strip").bounding_box()
            assert strip["x"] + strip["width"] == width
            assert page.evaluate("() => [...document.querySelectorAll('#drawer button, #drawer textarea')]"
                                 ".every(el => getComputedStyle(el).visibility === 'hidden')"), "closed rail is out of Tab order"
            _strip(page, "feedback").click()
            page.wait_for_timeout(350)
            assert _open(page)
            box = drawer.bounding_box()
            assert box["x"] + box["width"] == width
            assert box["width"] == (width if width < 600 else 440), width
            close = page.locator("#unified-sheet-close").bounding_box()
            assert close["width"] >= 44 and close["height"] >= 44
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), width
            page.locator("#unified-sheet-close").click()
            page.wait_for_timeout(350)
            assert not _open(page)


def test_strip_buttons_open_their_tab_and_show_the_tab_counts(tmp_path, rail_page):
    with browser_page(tmp_path, rail_page) as (page, _):
        for width in (1440, 768):
            _set_width(page, width)
            if width == 1440:
                page.locator("#drawer-collapse").click()
            _wait(lambda: page.locator("#tab-feedback-n").get_attribute("hidden") is None, page)
            needs = page.locator("#tab-feedback-n").text_content()
            badge = _strip(page, "feedback").locator(".rail-strip-n")
            assert badge.is_visible() and badge.inner_text() == needs == "2"
            assert _strip(page, "feedback").get_attribute("aria-label") == "Feedback — 2 need you"
            # Documents shows when the tab does, under the tab's own name.
            assert _strip(page, "documents").is_visible()
            assert _strip(page, "documents").get_attribute("aria-label") == "Links"
            for tab in ("history", "documents", "feedback"):
                _strip(page, tab).click()
                page.wait_for_timeout(350)
                assert _open(page)
                assert page.locator(f"#tab-{tab}").get_attribute("aria-selected") == "true", (width, tab)
                assert page.evaluate("() => document.activeElement.id") == f"tab-{tab}", (width, tab)
                page.locator("#unified-sheet-close:visible, #drawer-collapse:visible").first.click()
                page.wait_for_timeout(350)
                assert not _open(page)
        # A count change reaches the strip too.
        page.evaluate("() => { const n = document.getElementById('tab-feedback-n'); n.textContent = '5'; }")
        _wait(lambda: _strip(page, "feedback").locator(".rail-strip-n").inner_text() == "5", page)


def test_open_overlay_is_a_modal_dialog(tmp_path, rail_page):
    with browser_page(tmp_path, rail_page, width=768, height=900) as (page, _):
        drawer = page.locator("#drawer")
        assert drawer.get_attribute("role") == "complementary"
        trigger = _strip(page, "history")
        trigger.focus()
        page.keyboard.press("Enter")
        page.wait_for_timeout(350)
        assert drawer.get_attribute("role") == "dialog" and drawer.get_attribute("aria-modal") == "true"
        assert page.locator("#" + drawer.get_attribute("aria-labelledby")).text_content() == "Feedback"
        assert trigger.get_attribute("aria-expanded") == "true"
        assert page.evaluate("() => document.activeElement.id") == "tab-history"
        # Tab and Shift+Tab stay inside the rail and the Send bar it owns.
        inside = "() => ['#drawer', '#round-bar'].some(s => document.querySelector(s).contains(document.activeElement))"
        for _ in range(12):
            page.keyboard.press("Tab")
            assert page.evaluate(inside)
        for _ in range(12):
            page.keyboard.press("Shift+Tab")
            assert page.evaluate(inside)
        page.locator("#tab-history").focus()
        page.keyboard.press("Shift+Tab")
        assert page.evaluate(inside), "Shift+Tab from the first control wraps to the last"
        # Escape closes and focus goes back to the strip button that opened it.
        page.keyboard.press("Escape")
        page.wait_for_timeout(350)
        assert not _open(page)
        assert drawer.get_attribute("role") == "complementary" and drawer.get_attribute("aria-modal") is None
        assert page.evaluate("() => document.activeElement.dataset.railOpen") == "history"
        assert trigger.get_attribute("aria-expanded") == "false"
        # Escape with the Send summary on top closes only the summary.
        trigger.click()
        page.wait_for_timeout(350)
        page.evaluate("() => document.getElementById('round-finish-btn').disabled = false")
        page.locator("#round-finish-btn").click()
        page.locator("#round-confirm-backdrop.vis").wait_for()
        page.keyboard.press("Escape")
        assert page.locator("#round-confirm-backdrop.vis").count() == 0
        assert _open(page)
        page.keyboard.press("Escape")
        page.wait_for_timeout(350)
        assert not _open(page)
        # Widening with the overlay open leaves the rail inline, not a dialog.
        trigger.click()
        page.wait_for_timeout(350)
        _set_width(page, 1440)
        assert _open(page) and drawer.get_attribute("role") == "complementary"
        assert page.evaluate("() => document.body.classList.contains('is-mobile-sheet-open')") is False


def test_crossing_the_breakpoint_keeps_the_open_rail_and_focus(tmp_path, rail_page):
    with browser_page(tmp_path, rail_page) as (page, _):
        drawer = page.locator("#drawer")
        page.locator("#drawer-collapse").click()
        # Opened as the overlay, then widened: the rail stays open, inline,
        # even though it was collapsed there before, and keeps focus.
        _set_width(page, 768)
        _strip(page, "feedback").click()
        page.wait_for_timeout(350)
        _set_width(page, 1440)
        assert _open(page) and drawer.get_attribute("role") == "complementary"
        assert page.locator("#drawer-collapse").get_attribute("aria-expanded") == "true"
        assert page.evaluate("() => document.activeElement.id") == "tab-feedback"
        # Inline with focus inside, then narrowed: the rail closes to the
        # strip and focus goes to the strip, not lost to the page.
        page.locator("#tab-history").focus()
        _set_width(page, 768)
        assert not _open(page)
        assert page.evaluate("() => document.activeElement.id") == "drawer-strip"


def test_a_pin_opens_the_overlay_with_focus_on_the_feedback_tab(tmp_path, rail_page):
    with browser_page(tmp_path, rail_page, width=768, height=900) as (page, _):
        _strip(page, "history").click()
        page.wait_for_timeout(350)
        page.keyboard.press("Escape")
        page.wait_for_timeout(350)
        frame = page.locator("#content-frame").element_handle().content_frame()
        frame.evaluate("() => parent.postMessage({type: 'annotate:pin-open', anchorId: 'd:q1', commentIds: ['card-1']}, '*')")
        _wait(lambda: _open(page), page)
        assert page.locator("#tab-feedback").get_attribute("aria-selected") == "true"
        assert page.evaluate("() => document.activeElement.id") == "tab-feedback"
