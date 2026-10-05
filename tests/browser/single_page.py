"""Navigation helpers for the accepted shell; no product behavior is stubbed."""

import json
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import pytest

playwright = pytest.importorskip("playwright.sync_api")

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def ready(page):
    page.locator('body[data-ready="1"]').wait_for(state="attached")


def go(page, view="review", **params):
    # The shell sets this completion flag at the end of every async route,
    # but leaves the previous value in place while a new route is loading.
    # Clear only the inert readiness marker, then await the shell setting it.
    page.evaluate("p => {document.body.dataset.ready='0'; window.AA.go(p)}", {"view": view, **params})
    ready(page)
    playwright.expect(page.locator("body")).to_have_attribute("data-view", view)
    page.wait_for_function(
        "view => document.querySelector('#aa-tabs [aria-current=page]')?.dataset.view === view", arg=view
    )


def feedback(page):
    page.evaluate("() => window.AA.rail.reveal()")


def history(page):
    feedback(page)
    page.locator("#tab-history").click()
    page.locator("#history-body").wait_for(state="visible")


def section(page, key, root="#comment-list"):
    feedback(page)
    head = page.locator(f'{root} [data-section-toggle="{key}"], {root} [data-sec-toggle="{key}"]')
    head.wait_for(state="visible")
    if head.get_attribute("aria-expanded") != "true":
        head.click()
    return page.locator(f'{root} .sec[data-section="{key}"]')


@contextmanager
def browser_page(tmp_path, directory, width=1440, height=960):
    from test_card_layout import _serve

    process, base = _serve(tmp_path, directory)
    registry = tmp_path / "state" / "bus.json"
    if registry.exists():
        data = json.loads(registry.read_text())
        record = data["slugs"]["items-model"]
        record.update(port=urlsplit(base).port, url=base)
        registry.write_text(json.dumps(data))
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            page.set_default_timeout(5000)
            page.set_default_navigation_timeout(15_000)
            page.goto(base + "#view=review", wait_until="networkidle")
            ready(page)
            try:
                yield page, base
            finally:
                page.unroute_all(behavior="wait")
                browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
