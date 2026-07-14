import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_scroll_jump_granular_pin_and_reverse_lookup(tmp_path):
    source = Path(__file__).parents[2] / "examples" / "demo"
    slug_dir = tmp_path / "demo"
    shutil.copytree(source, slug_dir)
    port = _free_port()
    bus_dir = tmp_path / "bus"
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
            str(bus_dir),
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}/"
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                import urllib.request

                urllib.request.urlopen(base, timeout=1).close()
                break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError("standalone server did not become ready")

        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(
                viewport={"width": 1280, "height": 800},
                extra_http_headers={
                    "Cf-Access-Authenticated-User-Email": "reviewer@example.com",
                    "Cf-Access-Authenticated-User-Name": "Browser Reviewer",
                },
            )
            page.set_default_timeout(5_000)
            page.goto(base, wait_until="networkidle")
            frame = page.frame_locator("#content-frame")
            canvas = frame.locator("#canvas-area")
            document_root = frame.locator("html")
            canvas.hover()
            before = document_root.evaluate("element => element.scrollTop")
            page.mouse.wheel(0, 700)
            page.wait_for_timeout(300)
            after = document_root.evaluate("element => element.scrollTop")
            assert after > before

            frame.locator("#tab-btn-diagram").click()
            assert frame.locator(".tab-panel:visible").count() == 1
            jump = frame.locator(".er-cluster-jump")
            assert jump.inner_text() == "Jump to diagram ↓"
            jump.click()
            target = frame.locator("#demo-node")
            target.wait_for(state="visible")
            assert target.evaluate("element => element.classList.contains('goto-highlight-svg')")
            er_container = frame.locator("#er-container")
            page.wait_for_timeout(700)
            assert er_container.evaluate("element => element.scrollLeft") > 0
            assert er_container.evaluate("element => element.scrollTop") > 0

            frame.locator("#tab-btn-overview").click()
            anchor = frame.locator('[data-anchor-id="s:overview:introduction"]')
            anchor.locator("p").click(position={"x": 120, "y": 10})
            page.locator("#pop-ta").fill("Pin should return to this exact card")
            page.locator("#pop-save").click()
            pin = frame.locator(".bpin, .bpin-inline").first
            pin.wait_for(state="visible")
            pin.click()
            highlighted = page.locator("#comment-list .citem.hl")
            highlighted.wait_for(state="visible")
            assert "Pin should return to this exact card" in highlighted.inner_text()
            browser.close()

        store = json.loads((slug_dir / "comments.json").read_text(encoding="utf-8"))
        comment = store["anchors"]["s:overview:introduction"][0]
        assert comment["target"]["offset"]["dx"] > 0
        assert comment["target"]["offset"]["dy"] > 0
    finally:
        process.terminate()
        process.wait(timeout=5)
