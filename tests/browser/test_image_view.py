"""Image ids and scales (Chang, 2026-10-31). WebKit with the iPad Pro 11 profile.

Every image shows its IMG id and 25/50/75/100%. A tap on the image still
comments, as before. A scale opens the image at exactly that share of its real
pixels, from the original file when the preview lacks them, scrolling when it is
bigger than the screen; a tap there places one comment on that spot, carrying
the id to the rail and the store; closing returns to the same place.
"""

import json

import pytest
from test_card_layout import _serve
from test_images_compare import shots_page  # noqa: F401

playwright = pytest.importorskip("playwright.sync_api")

FIG = '[data-anchor-id="fig:home-on-a-phone"]'
BOARD = '[data-anchor-id="cmp:board"] .aa-cmp-cell'
VIEW = """() => { const f = document.querySelector('.aa-viewer-frame'), s = document.querySelector('.aa-viewer-stage');
  return {w: f.offsetWidth, h: f.offsetHeight, src: f.querySelector('img').getAttribute('src'),
          scrolls: s.scrollWidth > s.clientWidth,
          pressed: [...document.querySelectorAll('.aa-viewer-bar [aria-pressed="true"]')].map(b => b.textContent)}; }"""


def _comments(slug_dir):
    store = json.loads((slug_dir / "comments.json").read_text())
    return [c for items in store["anchors"].values() for c in items]


def test_image_ids_scales_and_one_comment_on_a_spot(tmp_path, shots_page):  # noqa: F811
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
            fig = frame.locator(FIG)
            fig.locator(".aa-img-bar").wait_for()
            content = next(f for f in page.frames if f.url.startswith(base) and f != page.main_frame)

            # Every image shows its id, the one publish wrote, and the four scales.
            bars = content.evaluate("""() => [...document.querySelectorAll('[data-anchor-id] img')].map(i => {
                const bar = i.nextElementSibling;
                return [i.dataset.img, bar.querySelector('.aa-img-id').textContent,
                        [...bar.querySelectorAll('[data-aa-scale]')].map(b => b.textContent).join(' ')]; })""")
            assert bars and all(text == "IMG " + image and scales == "25% 50% 75% 100%" for image, text, scales in bars)
            image = fig.locator("img").get_attribute("data-img")

            # A click on the image itself comments, as before: no viewer.
            fig.locator("img").click()
            page.wait_for_selector("#popover.vis")
            assert frame.locator(".aa-viewer").count() == 0
            page.locator("#pop-cancel").click()

            # Each scale is exactly that share of the original's pixels.
            fig.scroll_into_view_if_needed()
            before = content.evaluate("() => scrollY")
            fig.locator('[data-aa-scale="25"]').tap()
            frame.locator(".aa-viewer").wait_for()
            assert not page.locator("#popover").evaluate("p => p.classList.contains('vis')")
            assert frame.locator(".aa-viewer-title").inner_text().startswith("IMG " + image)
            view = content.evaluate(VIEW)
            assert (view["w"], view["h"], view["pressed"]) == (round(390 * 0.25), round(844 * 0.25), ["25%"])
            frame.locator('.aa-viewer-bar [data-aa-scale="50"]').tap()
            view = content.evaluate(VIEW)
            assert (view["w"], view["h"], view["pressed"]) == (195, 422, ["50%"])

            # At 50%, one tap on the image, then Save: exactly one comment, on that spot, carrying the id.
            box = frame.locator(".aa-viewer-frame img").bounding_box()
            page.touchscreen.tap(box["x"] + box["width"] * 0.25, box["y"] + box["height"] * 0.75)
            page.wait_for_selector("#popover.vis")
            assert page.locator("#pop-node-name").inner_text().startswith("IMG " + image)
            page.fill("#pop-ta", "This button is too small.")
            page.click("#pop-save")
            page.wait_for_function("() => document.querySelectorAll('.citem-img-id').length === 1")
            assert page.locator(".citem-img-id").inner_text() == "IMG " + image
            made = [c for c in _comments(shots_page) if c["text"] == "This button is too small."]
            assert len(made) == 1
            target = made[0]["target"]
            assert made[0]["anchor_id"] == "fig:home-on-a-phone" and target["image"] == image
            assert target["css"] == "img:nth-of-type(1)" and target["image_src"].startswith("assets/")
            assert target["offset"]["dx"] == pytest.approx(0.25, abs=0.02)
            assert target["offset"]["dy"] == pytest.approx(0.75, abs=0.02)
            frame.locator(".aa-viewer-pins .bpin").wait_for()

            # Closing returns to the same place, and the page pin sits on the image.
            if page.locator("#unified-sheet-close").is_visible():
                page.locator("#unified-sheet-close").click()
            frame.locator(".aa-viewer-close").tap()
            frame.locator(".aa-viewer").wait_for(state="detached")
            assert content.evaluate("() => scrollY") == before
            inside = content.evaluate("""sel => { const i = document.querySelector(sel + ' img').getBoundingClientRect();
                const p = document.querySelector('#badge-layer .bpin').getBoundingClientRect();
                const x = p.left + p.width / 2, y = p.top + p.height / 2;
                return x > i.left && x < i.right && y > i.top && y < i.bottom; }""", FIG)
            assert inside

            # A wide screenshot in a compare pane: at 100% it is 1,440 px and scrolls, from the original file.
            cell = frame.locator(BOARD).first
            cell.locator('[data-aa-scale="25"]').tap()
            frame.locator(".aa-viewer").wait_for()
            full = cell.locator("img").get_attribute("data-full")
            small = content.evaluate(VIEW)
            frame.locator('.aa-viewer-bar [data-aa-scale="100"]').tap()
            view = content.evaluate(VIEW)
            assert (view["w"], view["h"], view["scrolls"]) == (1440, 900, True)
            if full:   # a preview was made: 25% shows it, 100% needs the original
                assert small["src"] != full and view["src"] == full
            page.keyboard.press("Escape")
            frame.locator(".aa-viewer").wait_for(state="detached")
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=10)
