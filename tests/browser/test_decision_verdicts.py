"""D2: the third verdict button follows the server's advertised capabilities.

A server that advertises `verdicts: [..., "changes"]` gets "Request changes",
whose note is mandatory. A server that does not — anything older, including a
baked archive copy still being served — gets the pre-D2 "Comment" button
untouched. Both are checked in a real Chrome because the branch lives in the
chrome's render path, not in anything Python can assert.
"""

import json
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

CARD = {
    "id": "cccccccccccc",
    "anchor_id": "s:overview",
    "text": "Ship the rename?",
    "author": "agent:test",
    "created_at": "2026-09-17T09:00:00Z",
    "status": "open",
    "version": "v1",
    "decision_request": {"prompt": "Ship the rename?", "requested_at": "2026-09-17T09:00:00Z"},
}

LEGACY_CAPS = json.dumps({"version": "2.19", "batch": True, "rounds": True,
                          "decision_schema": 2, "decision_request_cap": 8192})


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _serve(tmp_path):
    """The demo page with one unresolved decision card pinned to s:overview."""
    source = Path(__file__).parents[2] / "examples" / "demo"
    slug_dir = tmp_path / "demo"
    shutil.copytree(source, slug_dir)
    (slug_dir / "comments.json").write_text(json.dumps(
        {"schema_version": 2, "anchors": {"s:overview": [CARD]}, "archived": {}}),
        encoding="utf-8")
    port = _free_port()
    env = os.environ.copy()
    env["ANNOTATE_STATE_DIR"] = str(tmp_path / "state")
    process = subprocess.Popen(
        [sys.executable, "-m", "agent_annotate.sync_server",
         "--slug-dir", str(slug_dir), "--slug", "demo",
         "--bus-dir", str(tmp_path / "bus"), "--port", str(port)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
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
    return process, base, slug_dir


def _open(runner, base, legacy=False):
    browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
    page = browser.new_page(
        viewport={"width": 1280, "height": 800},
        extra_http_headers={
            "Cf-Access-Authenticated-User-Email": "reviewer@example.com",
            "Cf-Access-Authenticated-User-Name": "Browser Reviewer",
        },
    )
    if legacy:
        # Answer the one capabilities probe with a pre-D2 body. Everything
        # else still hits the real server.
        page.route("**/api/capabilities", lambda route: route.fulfill(
            status=200, content_type="application/json", body=LEGACY_CAPS))
    page.set_default_timeout(5_000)
    page.goto(base, wait_until="networkidle")
    return browser, page


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_a_d2_server_shows_request_changes(tmp_path):
    process, base, slug_dir = _serve(tmp_path)
    try:
        with playwright.sync_playwright() as runner:
            browser, page = _open(runner, base)
            btn = page.locator(".decision-btn.decision-changes")
            btn.wait_for(state="visible")
            assert btn.inner_text().strip() == "↻ Request changes"
            assert page.locator(".decision-btn.decision-comment").count() == 0

            # The note is mandatory: an empty box submits nothing.
            btn.click()
            page.locator(".decision-comment-ta").wait_for(state="visible")
            page.locator(".decision-comment-submit").click()
            page.wait_for_timeout(300)
            stored = json.loads((slug_dir / "comments.json").read_text(encoding="utf-8"))
            assert "decision" not in stored["anchors"]["s:overview"][0]

            page.locator(".decision-comment-ta").fill("name the columns first")
            page.locator(".decision-comment-submit").click()
            page.locator(".decision-verdict-chip").wait_for(state="visible")
            assert "Changes requested" in page.locator(".decision-verdict-chip").inner_text()

            stored = json.loads((slug_dir / "comments.json").read_text(encoding="utf-8"))
            decision = stored["anchors"]["s:overview"][0]["decision"]
            assert decision["verdict"] == "changes"
            assert decision["text"] == "name the columns first"
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_a_pre_d2_server_still_shows_comment(tmp_path):
    process, base, slug_dir = _serve(tmp_path)
    try:
        with playwright.sync_playwright() as runner:
            browser, page = _open(runner, base, legacy=True)
            btn = page.locator(".decision-btn.decision-comment")
            btn.wait_for(state="visible")
            assert btn.inner_text().strip() == "💬 Comment"
            assert page.locator(".decision-btn.decision-changes").count() == 0

            btn.click()
            page.locator(".decision-comment-ta").fill("just a remark")
            page.locator(".decision-comment-submit").click()
            page.locator(".decision-verdict-chip").wait_for(state="visible")

            stored = json.loads((slug_dir / "comments.json").read_text(encoding="utf-8"))
            assert stored["anchors"]["s:overview"][0]["decision"]["verdict"] == "comment"
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
