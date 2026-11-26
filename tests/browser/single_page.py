"""Navigation helpers for the accepted shell; no product behavior is stubbed."""

import json
import os
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import pytest

playwright = pytest.importorskip("playwright.sync_api")

SYSTEM_CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def _browser():
    """The test browser: ANNOTATE_TEST_BROWSER, else Playwright's headless shell for this Playwright, else Chrome.

    Each Google Chrome launch on macOS makes secd scan every key Chrome ever left in the keychain
    (10,499 on the M1) and CoreSpotlight index the throwaway profile; the shell does neither and starts ~7x faster.
    """
    if os.environ.get("ANNOTATE_TEST_BROWSER"):
        return Path(os.environ["ANNOTATE_TEST_BROWSER"])
    try:
        listing = json.loads((Path(playwright.__file__).parents[1] / "driver/package/browsers.json").read_text())
        revision = next(b["revision"] for b in listing["browsers"] if b["name"] == "chromium-headless-shell")
    except (OSError, ValueError, KeyError, StopIteration):
        return SYSTEM_CHROME
    root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or Path.home() / "Library/Caches/ms-playwright")
    shells = sorted(root.glob(f"chromium_headless_shell-{revision}/chrome-headless-shell-*/chrome-headless-shell"))
    return shells[0] if shells else SYSTEM_CHROME


CHROME = _browser()


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


def project_notes(page):
    """mme: the agent's progress notes sit in one folded row under the versions."""
    fold = page.locator("#project-panel-review > details.project-notes")
    if fold.get_attribute("open") is None:
        fold.locator("> summary").click()


# A round sent, nested under the version it was sent on (yvj).
ROUNDS = "#history-body .vact-block:not(.vact-agent)"


def sent(page):
    # Each version opens to what was sent and done on it; open every one shown.
    page.locator("#history-body .vrow-toggle:visible").first.wait_for()
    for toggle in page.locator('#history-body .vrow-toggle[aria-expanded="false"]:visible').all():
        toggle.click()


def section(page, key, root="#comment-list"):
    feedback(page)
    head = page.locator(f'{root} [data-section-toggle="{key}"], {root} [data-sec-toggle="{key}"]')
    head.wait_for(state="visible")
    if head.get_attribute("aria-expanded") != "true":
        head.click()
    return page.locator(f'{root} .sec[data-section="{key}"]')


@contextmanager
def browser_page(tmp_path, directory, width=1440, height=960, ipad=False):
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
            if ipad:
                try:
                    browser = runner.webkit.launch()
                except playwright.Error:
                    pytest.skip("Playwright WebKit is not installed")
                device = ipad if isinstance(ipad, str) else "iPad Pro 11 landscape"
                page = browser.new_context(**runner.devices[device]).new_page()
            else:
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
