"""Generated anchors remain readable in Details; requests and comments share Feedback."""

import json
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

from agent_annotate.pagegen import generate  # noqa: E402

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
    source.write_text((Path(__file__).parents[1] / "fixtures/full_review.md").read_text(), encoding="utf-8")
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
         "--bus-dir", str(sandbox / "bus"), "--port", str(PORT),
         "--local-author", "reviewer@example.com", "--local-author-name", "Browser Reviewer"],
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

        # Publish the generated requests through the same batch endpoint as annotate new --ask.
        cards = json.loads((slug_dir / 'cards.json').read_text())
        request = urllib.request.Request(base + 'api/comments/batch', method='POST',
            data=json.dumps({'items':[dict(card,version='v1') for card in cards]}).encode(),
            headers={'Content-Type':'application/json','X-Annotate-Agent':'agent:generated-browser'})
        with urllib.request.urlopen(request) as response:
            question_ids = json.load(response)['ids']

        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(
                viewport={"width": 1280, "height": 900},
            )
            page.set_default_timeout(10_000)
            page.goto(base, wait_until="networkidle")
            card = page.locator(f'.citem[data-comment-id="{question_ids[0]}"]')
            card.wait_for()
            assert card.locator('.citem-num').inner_text() == '#1'
            assert 'Rename status to lifecycle_state.' in card.inner_text()
            badge = card.locator('.decision-rec-badge')
            assert badge.count() == 1 and badge.inner_text().strip() == 'rec'
            assert 'Rename with a dual-write week' in badge.locator('xpath=..').inner_text()
            assert 'blocking' in card.locator('.decision-chip-blocking').inner_text().lower()
            page.locator('[data-workspace-tab="details"]').click()
            frame = page.frame_locator('#content-frame')
            anchors = frame.locator('[data-anchor-id]')
            anchors.first.wait_for(state='attached')
            assert anchors.count() == result['anchors']
            assert frame.locator('[data-anchor-id="s:columns"]').count() == 1
            assert frame.locator('table[data-anchor-id="tbl:columns"]').count() == 1
            assert frame.locator('tr[data-anchor-id="tbl:columns:row:status"]').count() == 1
            assert frame.locator('th[data-anchor-id="tbl:columns:col:type"]').count() == 1
            assert frame.locator('.kpi.bad').count() == 1
            assert frame.locator('pre[data-anchor-id="s:migration-sketch:code1"]').count() == 1
            assert frame.locator('.card[data-anchor-id="d:q1"]').is_hidden()
            assert frame.locator('.annotate-decision-strip').count() == 0
            frame.locator('[data-anchor-id="s:scope:li1"]').click()
            page.locator('#pop-ta').fill('This row is the one to decide first')
            label = page.locator('#pop-node-name')
            assert label.get_attribute('title') == label.inner_text(), 'Truncated labels retain their full tooltip'
            page.locator('#pop-save').click()
            page.locator('#popover').wait_for(state='hidden')
            page.locator('[data-workspace-tab="feedback"]').click()
            page.locator('[data-filter="waiting"]').click()
            comment = page.locator('.citem').filter(has_text='This row is the one to decide first')
            comment.wait_for()
            store = json.loads((slug_dir / 'comments.json').read_text())
            assert any(item['text'] == 'This row is the one to decide first' for item in store['anchors']['s:scope:li1'])
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
