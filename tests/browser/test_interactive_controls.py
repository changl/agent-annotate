"""Conformance tests for interaction-contract item 13.

Click-to-comment runs as a capture-phase listener that calls stopPropagation(),
so anything it claims never receives its own click. These tests pin the
boundary: interactive elements keep native behavior, everything else stays
annotatable, and Alt/Option-click is the deliberate override.
"""

import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _serve(tmp_path):
    source = Path(__file__).parents[2] / "examples" / "demo"
    slug_dir = tmp_path / "demo"
    shutil.copytree(source, slug_dir)
    port = _free_port()
    env = os.environ.copy()
    env["ANNOTATE_STATE_DIR"] = str(tmp_path / "state")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "agent_annotate.sync_server",
            "--slug-dir",
            str(slug_dir),
            "--slug",
            "demo",
            "--bus-dir",
            str(tmp_path / "bus"),
            "--port",
            str(port),
            "--local-author",
            "reviewer@example.com",
            "--local-author-name",
            "Browser Reviewer",
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
        raise AssertionError("standalone server did not become ready")
    return process, base


def _details_page(browser, base):
    """Optional anchored comments share the native workspace's canonical store."""
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.set_default_timeout(5_000)
    page.goto(base + "#view=review", wait_until="networkidle")
    page.locator('body[data-ready="1"]').wait_for(state="attached")
    page.frame_locator("#content-frame").locator("#plain-para").wait_for()
    return page


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_interactive_controls_keep_native_click_behavior(tmp_path):
    process, base = _serve(tmp_path)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = _details_page(browser, base)
            frame = page.frame_locator("#content-frame")
            popover = page.locator("#pop-ta")

            # Baseline: plain prose inside an anchored section still comments.
            frame.locator("#plain-para").click()
            popover.wait_for(state="visible")
            assert (
                page.locator("#pop-node-name").get_attribute("title")
                == page.locator("#pop-node-name").inner_text()
            )
            page.keyboard.press("Escape")
            popover.wait_for(state="hidden")

            # Controls must not be hijacked. Each of these sits inside
            # [data-anchor-id="s:overview:controls"], so a regression here is a
            # real one, not a vacuous pass.
            for selector in (
                "#demo-input",
                "#demo-role-checkbox",
                "#demo-summary",
                "#demo-optout",
            ):
                frame.locator(selector).click()
                page.wait_for_timeout(200)
                assert not popover.is_visible(), f"{selector} requested a comment"

            # A native <select> must still change value.
            frame.locator("#demo-select").select_option("b")
            assert frame.locator("#demo-select").input_value() == "b"
            assert not popover.is_visible()

            # <details> actually toggled rather than being swallowed.
            assert frame.locator("details").evaluate("el => el.open") is True

            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_alt_click_overrides_the_interactive_bail_out(tmp_path):
    process, base = _serve(tmp_path)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = _details_page(browser, base)
            frame = page.frame_locator("#content-frame")
            popover = page.locator("#pop-ta")

            # Without the override an interactive element is un-commentable;
            # Alt/Option-click is the documented way to annotate one anyway.
            frame.locator("#demo-input").click(modifiers=["Alt"])
            popover.wait_for(state="visible")

            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
