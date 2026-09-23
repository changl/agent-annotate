"""The generated page, served by the real sync server, in a real browser.

The unit tests assert what `annotate new` writes. This asserts what a reviewer
sees: the shell mounts the generated canvas, every anchor survives the
content round-trip through the server, and a decision card from the ```cards
block renders in the body with its Recommended badge — the one thing that
doubles a card's answer rate (74% vs 34%).
"""

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from agent_annotate.pagegen import EXAMPLE, generate  # noqa: E402

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
PORT = 8898


def _port_is_free(port: int) -> bool:
    with socket.socket() as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_generated_page_renders_its_anchors_and_a_recommended_card(tmp_path):
    if not _port_is_free(PORT):
        pytest.skip(f"port {PORT} is already in use on this machine")

    source = tmp_path / "page.md"
    source.write_text(EXAMPLE, encoding="utf-8")
    slug_dir = tmp_path / "items-model-review"
    result = generate(source, slug_dir)
    assert result["anchors"] > 20

    # Sandbox every root the server could otherwise write into: the live
    # estate keeps eighteen pages under these names.
    sandbox = Path(tempfile.mkdtemp(prefix="pagegen-browser-", dir=tmp_path))
    env = os.environ.copy()
    env.update({
        "ANNOTATE_STATE_DIR": str(sandbox / "state"),
        "ANNOTATE_BUS_ROOT": str(sandbox / "bus"),
        "ANNOTATE_CONFIG_DIR": str(sandbox / "config"),
        "ANNOTATE_DATA_DIR": str(sandbox / "data"),
        "ANNOTATE_CLAUDE_SETTINGS": str(sandbox / "claude" / "settings.json"),
        "ANNOTATE_SHIM_PATH": str(sandbox / "bin" / "annotate"),
        "ANNOTATE_BUS_ARCHIVE_ROOT": str(sandbox / "bus-archive"),
    })
    process = subprocess.Popen(
        [sys.executable, "-m", "agent_annotate.sync_server",
         "--slug-dir", str(slug_dir), "--slug", "items-model-review",
         "--bus-dir", str(sandbox / "bus"), "--port", str(PORT)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
    )
    try:
        base = f"http://127.0.0.1:{PORT}/"
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                urllib.request.urlopen(base, timeout=1).close()
                break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError(f"sync server never came up on {PORT}")

        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(
                viewport={"width": 1280, "height": 900},
                extra_http_headers={
                    "Cf-Access-Authenticated-User-Email": "reviewer@example.com",
                    "Cf-Access-Authenticated-User-Name": "Browser Reviewer",
                },
            )
            page.set_default_timeout(10_000)
            page.goto(base, wait_until="networkidle")
            frame = page.frame_locator("#content-frame")

            # The iframe loads asynchronously; an immediate read sees zero
            # anchors on a perfectly healthy page.
            anchors = frame.locator("[data-anchor-id]")
            anchors.first.wait_for(state="attached")
            page.wait_for_timeout(300)
            assert anchors.count() == result["anchors"]

            # Prose, table, KPI tile and code block all survived the round-trip.
            assert frame.locator('[data-anchor-id="s:columns"]').count() == 1
            assert frame.locator('table[data-anchor-id="tbl:columns"]').count() == 1
            assert frame.locator('tr[data-anchor-id="tbl:columns:row:status"]').count() == 1
            assert frame.locator('th[data-anchor-id="tbl:columns:col:type"]').count() == 1
            assert frame.locator(".kpi.bad").count() == 1
            assert frame.locator('pre[data-anchor-id="s:migration-sketch:code1"]').count() == 1

            # The decision card is visible in the body with its recommendation.
            card = frame.locator('.card[data-anchor-id="d:q1"]')
            card.wait_for(state="visible")
            assert card.locator(".item-num").inner_text() == "#1"
            assert "Rename status to lifecycle_state." in card.inner_text()
            badge = card.locator(".reco")
            assert badge.count() == 1
            assert badge.inner_text().strip() == "Recommended"
            assert "Rename with a dual-write week" in badge.locator("xpath=..").inner_text()
            assert "blocking" in card.locator(".chip.blocking").inner_text()

            # A generated anchor is commentable: the whole point of the page.
            frame.locator('[data-anchor-id="s:scope:li1"]').click()
            page.locator("#pop-ta").fill("This row is the one to decide first")
            page.locator("#pop-save").click()
            page.locator("#comment-list .citem").first.wait_for(state="visible")
            assert "This row is the one to decide first" in page.locator("#comment-list").inner_text()
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
