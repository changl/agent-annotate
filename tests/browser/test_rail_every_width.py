"""The rail stays at every width (agent-annotate-lh1).

From 1024px the rail sits inline beside the document; narrower it is a
right-side overlay, full width under 600px. Closed, at every width, it leaves
an edge strip with one button per rail tab and the tabs' counts. Open as the
overlay it is a modal dialog (APG): focus moves in, Tab stays inside, Escape
closes and focus returns to the button that opened it.

Closed, the document is exactly the viewport minus the strip: nothing in it
runs under the strip, and nothing scrolls sideways at any width (Chang on
#38). Tables wrap with whole words; a table scrolls inside itself only when a
single word or image cannot fit, and then the side with more columns fades so
it reads as that box, not the page (Chang on #35).
"""

import struct
import zlib

import pytest
from single_page import browser_page
from test_card_jump import page_dir  # noqa: F401  (fixture)
from test_card_layout import CHROME, _wait

from agent_annotate.pagegen import generate
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


def _png(width, height):
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress((b"\x00" + b"\x80" * 3 * width) * height)) + chunk(b"IEND", b""))


WIDE = """---
title: Wide review
version: v1
full_plan: true
other_files_required: none
---

## Coverage

A read-only dry run over the 10 M1 pages changed no files.

| Result | Count | Which |
| --- | --- | --- |
| Safe to file | 6 | This page's #24 roll out 2.26.1, #26 approving files into Plans, #28 the one-line rule, #29 the wake-up hook, #30 install #34 on the M1, #32 keep the three M5 changes |
| Already filed | 1 | #33 |
| Not filed: no saved card snapshot | 49 | Approvals from before Sept 30, when the exact card shown was not yet saved |
| Not filed: not cast in the browser | 13 | Windmill CheerTicketing plan votes |

| Gate | Owner | Status | Evidence | Next step |
| --- | --- | --- | --- | --- |
| Rail at every width | Chang | Approved | Browser suite at nine sizes, focus review fixed three bugs | Ship on the M1 with the other approved changes |
| One name per page | Agent | Waiting | Five metadata files with backups, URLs unchanged | Rename the four pages after the answer |

## Shots

![The whole page](shots/wide.png)

```compare
title: Header
current: shots/wide.png | Today
proposed: shots/wide.png | Proposed
```
"""

# Inside the document: no sideways scroll, no table scrolls inside itself, and
# every image, compare block and table box ends inside the visible width.
DOCUMENT_FITS = """() => {
  const de = document.documentElement, w = de.clientWidth;
  const over = [...document.querySelectorAll('img, figure, .unified-table-frame')]
    .filter(el => el.getBoundingClientRect().right > w + 0.5).map(el => el.tagName + '.' + el.className);
  const tables = [...document.querySelectorAll('.unified-table-scroll')]
    .filter(s => s.scrollWidth > s.clientWidth).map(s => s.scrollWidth + '>' + s.clientWidth);
  const hints = [...document.querySelectorAll('.unified-table-hint')].filter(h => h.offsetParent).length;
  return {scrolls: de.scrollWidth > w, over, tables, hints};
}"""


def _wide_page(tmp_path, text):
    source = tmp_path / "wide.md"
    source.write_text(text)
    (tmp_path / "shots").mkdir()
    (tmp_path / "shots" / "wide.png").write_bytes(_png(1600, 900))
    directory = tmp_path / "items-model"
    generate(source, directory)
    return directory


@pytest.fixture
def wide_page(tmp_path):
    return _wide_page(tmp_path, WIDE)


SIZES = [(1440, 900), (1160, 800), (1024, 768), (1023, 768), (768, 1024),
         (600, 900), (599, 900), (390, 844), (844, 390)]


def _closed(page, size):
    width, _ = size
    if page.locator("#drawer-collapse").is_visible():
        page.locator("#drawer-collapse").click()
    assert not _open(page)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), size
    frame_box = page.locator("#content-frame").bounding_box()
    strip = page.locator("#rail-strip").bounding_box()
    assert strip["x"] + strip["width"] == width
    assert frame_box["x"] + frame_box["width"] <= strip["x"], "the document runs under the strip"
    page.frame_locator("#content-frame").locator(".unified-table-frame").first.wait_for()
    doc = page.locator("#content-frame").element_handle().content_frame()
    _wait(lambda: doc.evaluate("() => [...document.images].every(i => i.complete)"), page)
    return doc


@pytest.mark.parametrize("size", SIZES)
def test_closed_rail_never_scrolls_sideways_and_tables_wrap(tmp_path, wide_page, size):
    width, height = size
    with browser_page(tmp_path, wide_page, width=width, height=height) as (page, _):
        doc = _closed(page, size)
        assert doc.evaluate(DOCUMENT_FITS) == {"scrolls": False, "over": [], "tables": [], "hints": 0}, size
        # Whole words: no cell breaks inside a word.
        assert doc.evaluate("() => [...document.querySelectorAll('.unified-table-scroll td, .unified-table-scroll th')]"
                            ".every(c => getComputedStyle(c).wordBreak === 'normal'"
                            " && getComputedStyle(c).overflowWrap === 'normal')")


UNBREAKABLE = WIDE.replace("| Already filed | 1 | #33 |", "| Already filed | 1 | " + "x" * 300 + " |")


@pytest.mark.parametrize("size", [(1440, 900), (390, 844)])
def test_a_word_that_cannot_fit_scrolls_inside_its_table_with_a_fade(tmp_path, size):
    width, height = size
    with browser_page(tmp_path, _wide_page(tmp_path, UNBREAKABLE), width=width, height=height) as (page, _):
        doc = _closed(page, size)
        fits = doc.evaluate(DOCUMENT_FITS)
        assert fits["scrolls"] is False and fits["over"] == [] and len(fits["tables"]) == 1, size
        assert fits["hints"] == 1, "the hint shows only on the table that scrolls"
        table = page.frame_locator("#content-frame").locator(".unified-table-frame").first
        classes = lambda: table.get_attribute("class").split()  # noqa: E731
        assert "is-more-right" in classes() and "is-more-left" not in classes(), size
        doc.evaluate("() => { const s = document.querySelector('.unified-table-scroll'); s.scrollLeft = s.scrollWidth; }")
        _wait(lambda: "is-more-left" in classes() and "is-more-right" not in classes(), page)
