"""Image ids and the large viewer (Chang, 2026-10-31). WebKit with the iPad Pro 11 profile.

Every image shows its IMG id; a tap opens it large instead of starting a comment;
pinch zooms; a tap on the image there places one comment on that spot, carrying
the id to the rail and the store; closing returns to the same place.
"""

import json

import pytest
from test_card_layout import _serve
from test_images_compare import shots_page  # noqa: F401

playwright = pytest.importorskip("playwright.sync_api")

PINCH = """() => {
  const stage = document.querySelector('.aa-viewer-stage');
  const r = stage.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
  const ev = (type, id, px) => stage.dispatchEvent(new PointerEvent(type, {pointerId: id, pointerType: 'touch',
    clientX: px, clientY: y, bubbles: true, isPrimary: id === 11}));
  ev('pointerdown', 11, x - 30); ev('pointerdown', 12, x + 30);
  for (let k = 1; k <= 8; k++) { ev('pointermove', 11, x - 30 - 10 * k); ev('pointermove', 12, x + 30 + 10 * k); }
  ev('pointerup', 11, x - 110); ev('pointerup', 12, x + 110);
  return new DOMMatrix(getComputedStyle(document.querySelector('.aa-viewer-frame')).transform).a;
}"""


def _comments(slug_dir):
    store = json.loads((slug_dir / "comments.json").read_text())
    return [c for items in store["anchors"].values() for c in items]


def test_image_ids_viewer_zoom_and_one_comment_on_a_spot(tmp_path, shots_page):  # noqa: F811
    process, base = _serve(tmp_path, shots_page)
    try:
        with playwright.sync_playwright() as runner:
            try:
                browser = runner.webkit.launch()
            except Exception:
                pytest.skip("Playwright WebKit is not installed")
            page = browser.new_context(**dict(runner.devices["iPad Pro 11"])).new_page()
            page.set_default_timeout(10_000)
            page.goto(base + "#view=review", wait_until="networkidle")
            page.wait_for_selector("#content-frame")
            if page.locator("#unified-sheet-backdrop").is_visible():
                page.keyboard.press("Escape")
            frame = page.frame_locator("#content-frame")
            fig = frame.locator('[data-anchor-id="fig:home-on-a-phone"]')
            fig.locator(".aa-img-id").wait_for()
            content = next(f for f in page.frames if f.url.startswith(base) and f != page.main_frame)

            # Every image shows its id, the same one publish wrote.
            labels = content.evaluate("""() => [...document.querySelectorAll('[data-anchor-id] img')].map(i =>
                [i.dataset.img, (i.parentElement.querySelector('.aa-img-id') || {}).textContent])""")
            assert labels and all(text == "IMG " + image for image, text in labels)
            image = fig.locator("img").get_attribute("data-img")

            # A plain tap opens the viewer, not the composer.
            fig.scroll_into_view_if_needed()
            before = content.evaluate("() => scrollY")
            fig.locator("img").tap()
            frame.locator(".aa-viewer").wait_for()
            assert not page.locator("#popover").evaluate("p => p.classList.contains('vis')")
            assert frame.locator(".aa-viewer-title").inner_text().startswith("IMG " + image)
            assert content.evaluate(PINCH) > 1.5

            # One tap on the image there, then Save: exactly one comment, on that spot, carrying the id.
            box = frame.locator(".aa-viewer-frame img").bounding_box()
            stage = frame.locator(".aa-viewer-stage").bounding_box()
            left, top = max(box["x"], stage["x"]), max(box["y"], stage["y"])
            right = min(box["x"] + box["width"], stage["x"] + stage["width"])
            bottom = min(box["y"] + box["height"], stage["y"] + stage["height"])
            page.touchscreen.tap((left + right) / 2, (top + bottom) / 2)
            page.wait_for_selector("#popover.vis")
            assert page.locator("#pop-node-name").inner_text().startswith("IMG " + image)
            page.fill("#pop-ta", "This button is too small.")
            page.click("#pop-save")
            page.wait_for_function("() => [...document.querySelectorAll('.citem-img-id')].length === 1")
            assert page.locator(".citem-img-id").inner_text() == "IMG " + image
            made = [c for c in _comments(shots_page) if c["text"] == "This button is too small."]
            assert len(made) == 1
            target = made[0]["target"]
            assert made[0]["anchor_id"] == "fig:home-on-a-phone" and target["image"] == image
            assert target["css"] == "img:nth-of-type(1)" and 0 < target["offset"]["dx"] < 1
            frame.locator(".aa-viewer-pins .bpin").wait_for()
            if page.locator("#unified-sheet-close").is_visible():
                page.locator("#unified-sheet-close").click()
            frame.locator(".aa-viewer-pins .bpin").tap()       # the viewer pin opens its card
            page.locator('.citem[data-comment-id="' + made[0]['id'] + '"]').wait_for()

            # Closing returns to the same place, and the page pin sits on the image.
            if page.locator("#unified-sheet-close").is_visible():
                page.locator("#unified-sheet-close").click()
            frame.locator(".aa-viewer-close").tap()
            frame.locator(".aa-viewer").wait_for(state="detached")
            assert content.evaluate("() => scrollY") == before
            inside = content.evaluate("""() => { const i = document.querySelector('[data-anchor-id="fig:home-on-a-phone"] img').getBoundingClientRect();
                const p = document.querySelector('#badge-layer .bpin').getBoundingClientRect();
                const x = p.left + p.width / 2, y = p.top + p.height / 2;
                return x > i.left && x < i.right && y > i.top && y < i.bottom; }""")
            assert inside

            # A compare pane opens the same way.
            frame.locator('[data-anchor-id="cmp:checkout"] .aa-cmp-cell img').first.tap()
            frame.locator(".aa-viewer").wait_for()
            page.keyboard.press("Escape")
            frame.locator(".aa-viewer").wait_for(state="detached")
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=10)
