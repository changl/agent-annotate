"""Conformance tests for the legacy single-file artifact (template.html).

Legacy slugs have no content/ directory, so sync_server serves
versions/<v>.html directly with the chrome baked in — a completely separate
front-end from the universal shell + adapter.js. It had no coverage at all,
which is how its click-to-comment bail-out drifted behind adapter.js and
started swallowing clicks on native <select> dropdowns.

Covers interaction-contract items 13 (native controls) and 14 (rail collapse).
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
TEMPLATE = Path(__file__).parents[2] / "src" / "agent_annotate" / "web" / "template.html"

CANVAS = """
<div class="no" id="s:demo:prose">
  <h2>Prose</h2>
  <p id="plain-para">Plain prose stays annotatable.</p>
</div>
<div class="no" id="s:demo:controls">
  <h2>Controls</h2>
  <select id="demo-select"><option value="a">Alpha</option><option value="b">Bravo</option></select>
  <input id="demo-input" type="text" value="typed">
  <button id="demo-button" type="button">Real button</button>
  <div id="demo-role-checkbox" role="checkbox" aria-checked="false">Role checkbox</div>
  <details><summary id="demo-summary">Disclosure</summary><p>Body</p></details>
  <div id="demo-optout" data-annotate-interactive>Custom widget opted out</div>
</div>
"""

REGISTRY = {
    "s:demo:prose": {"name": "Prose"},
    "s:demo:controls": {"name": "Controls"},
}


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _render_legacy_slug(tmp_path):
    """Substitute template.html's placeholders into a legacy slug layout."""
    html = TEMPLATE.read_text(encoding="utf-8")
    for token, value in {
        "{{CANVAS}}": CANVAS,
        "{{ANCHOR_REGISTRY}}": json.dumps(REGISTRY),
        "{{DOC_ID}}": "legacy-demo",
        "{{VERSION}}": "v1",
        "{{TITLE}}": "Legacy demo",
        "{{SUBTITLE}}": "template.html conformance fixture",
        "{{DATE}}": "2026-07-24",
        "{{LEGEND}}": "",
    }.items():
        html = html.replace(token, value)
    assert "{{" not in html, "unsubstituted placeholder left in rendered template"

    slug_dir = tmp_path / "legacy"
    (slug_dir / "versions").mkdir(parents=True)
    (slug_dir / "versions" / "v1.html").write_text(html, encoding="utf-8")
    (slug_dir / "current.html").write_text(html, encoding="utf-8")
    (slug_dir / "current.meta.json").write_text(
        json.dumps({"current": "v1", "history": [{"version": "v1", "ts": "", "label": ""}]}),
        encoding="utf-8",
    )
    (slug_dir / "comments.json").write_text(
        json.dumps({"schema_version": 2, "anchors": {}, "archived": {}}), encoding="utf-8"
    )
    # No content/ dir on purpose — that is what makes this the legacy path.
    assert not (slug_dir / "content").exists()
    return slug_dir


def _serve(tmp_path):
    slug_dir = _render_legacy_slug(tmp_path)
    port = _free_port()
    env = os.environ.copy()
    env["ANNOTATE_STATE_DIR"] = str(tmp_path / "state")
    process = subprocess.Popen(
        [
            sys.executable, "-m", "agent_annotate.sync_server",
            "--slug-dir", str(slug_dir),
            "--slug", "legacy",
            "--bus-dir", str(tmp_path / "bus"),
            "--port", str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    base = f"http://127.0.0.1:{port}/"
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            urllib.request.urlopen(base, timeout=1).close()
            break
        except OSError:
            time.sleep(0.05)
    else:
        process.terminate()
        raise AssertionError("legacy server did not become ready")
    return process, base


def _page(browser):
    return browser.new_page(
        viewport={"width": 1280, "height": 800},
        extra_http_headers={
            "Cf-Access-Authenticated-User-Email": "reviewer@example.com",
            "Cf-Access-Authenticated-User-Name": "Browser Reviewer",
        },
    )


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_legacy_controls_keep_native_click_behavior(tmp_path):
    process, base = _serve(tmp_path)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = _page(browser)
            page.set_default_timeout(5_000)
            page.goto(base, wait_until="networkidle")
            popover = page.locator("#popover")

            # Baseline: plain prose inside an anchored section still comments.
            page.locator("#plain-para").click()
            page.wait_for_selector("#popover.vis")
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)

            for selector in (
                "#demo-input",
                "#demo-button",
                "#demo-role-checkbox",
                "#demo-summary",
                "#demo-optout",
            ):
                page.locator(selector).click()
                page.wait_for_timeout(200)
                assert "vis" not in (popover.get_attribute("class") or ""), (
                    f"{selector} opened the comment popover"
                )

            # The originally reported bug: a native <select> must still work.
            page.locator("#demo-select").select_option("b")
            assert page.locator("#demo-select").input_value() == "b"
            assert "vis" not in (popover.get_attribute("class") or "")
            assert page.locator("details").evaluate("el => el.open") is True

            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_legacy_alt_click_overrides_the_bail_out(tmp_path):
    process, base = _serve(tmp_path)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = _page(browser)
            page.set_default_timeout(5_000)
            page.goto(base, wait_until="networkidle")

            # Deliberately a <button>: it was excluded by the OLD bail-out
            # too, so this asserts the Alt override itself rather than
            # passing merely because the element used to be annotatable.
            page.locator("#demo-button").click(modifiers=["Alt"])
            page.wait_for_selector("#popover.vis")

            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_feedback_rail_collapses_expands_and_persists(tmp_path):
    process, base = _serve(tmp_path)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = _page(browser)
            page.set_default_timeout(5_000)
            page.goto(base, wait_until="networkidle")

            panel = page.locator("#panel")
            toggle = page.locator("#panel-toggle")

            # Disclosure semantics live on the button, not the panel.
            assert toggle.get_attribute("aria-expanded") == "true"
            assert toggle.get_attribute("aria-controls") == "panel-body"
            assert toggle.get_attribute("aria-label") == "Collapse feedback panel"
            # WCAG 2.2 SC 2.5.8 target size.
            box = toggle.bounding_box()
            assert box["width"] >= 24 and box["height"] >= 24

            # Expanded: collapse glyph visible, expand glyph hidden.
            assert page.locator("#panel-toggle .i-collapse").is_visible()
            assert not page.locator("#panel-toggle .i-expand").is_visible()

            expanded_width = panel.bounding_box()["width"]
            toggle.click()
            page.wait_for_timeout(300)

            assert "collapsed" in (panel.get_attribute("class") or "")
            assert toggle.get_attribute("aria-expanded") == "false"
            assert toggle.get_attribute("aria-label") == "Expand feedback panel"
            # Glyph flipped with state.
            assert page.locator("#panel-toggle .i-expand").is_visible()
            assert not page.locator("#panel-toggle .i-collapse").is_visible()
            collapsed_width = panel.bounding_box()["width"]
            assert collapsed_width < expanded_width

            # Contract item 14: the collapsed rail still reports its count,
            # and the toggle survives the collapse.
            assert page.locator("#cnt-badge").is_visible()
            assert toggle.is_visible()
            # Collapsed content is out of the tab order.
            assert not page.locator("#panel-body").is_visible()

            assert page.evaluate("localStorage.getItem('annotate:panelCollapsed')") == "1"

            # Expand again.
            toggle.click()
            page.wait_for_timeout(300)
            assert "collapsed" not in (panel.get_attribute("class") or "")
            assert toggle.get_attribute("aria-expanded") == "true"
            assert page.evaluate("localStorage.getItem('annotate:panelCollapsed')") == "0"

            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_collapsed_rail_state_survives_reload(tmp_path):
    process, base = _serve(tmp_path)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = _page(browser)
            page.set_default_timeout(5_000)
            page.goto(base, wait_until="networkidle")

            page.locator("#panel-toggle").click()
            page.wait_for_timeout(200)
            page.reload(wait_until="networkidle")
            page.wait_for_timeout(400)

            assert "collapsed" in (page.locator("#panel").get_attribute("class") or "")
            assert page.locator("#panel-toggle").get_attribute("aria-expanded") == "false"

            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
