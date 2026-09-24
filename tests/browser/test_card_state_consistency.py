"""The page body and the rail must never disagree about a question.

Chang, 2026-09-23: the rail said "Addressed" while the question card baked
into the page body still read "Answer it on the card". Every baked card now
shows the rail's own status for that item.
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

from agent_annotate.pagegen import EXAMPLE, generate  # noqa: E402

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def _card(cid, anchor, number, **extra):
    return {"id": cid, "anchor_id": anchor, "number": number, "text": f"Card {number}",
            "author": "agent:test", "created_at": "2026-09-23T09:00:00Z", "version": "v1",
            "status": "open",
            "decision_request": {"prompt": f"Question {number}?",
                                 "requested_at": "2026-09-23T09:00:00Z"},
            **extra}


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_body_cards_show_the_same_status_as_the_rail(tmp_path):
    source = tmp_path / "page.md"
    source.write_text(EXAMPLE, encoding="utf-8")
    slug_dir = tmp_path / "items-model-review"
    generate(source, slug_dir)
    (slug_dir / "comments.json").write_text(json.dumps({
        "schema_version": 2,
        "anchors": {
            "d:q1": [_card("withdrawn-1", "d:q1", 1, status="addressed_by_agent",
                           response_text="Withdrawn.")],
            "d:q2": [_card("accepted-2", "d:q2", 2, status="user_confirmed",
                           decision={"verdict": "accept", "ts": "2026-09-23T10:00:00Z",
                                     "by": "reviewer@example.com"})],
            "d:q3": [_card("open-3", "d:q3", 3)],
        },
        "archived": {},
    }), encoding="utf-8")

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env["ANNOTATE_STATE_DIR"] = str(tmp_path / "state")
    process = subprocess.Popen(
        [sys.executable, "-m", "agent_annotate.sync_server", "--slug-dir", str(slug_dir),
         "--slug", "items-model-review", "--bus-dir", str(tmp_path / "bus"),
         "--port", str(port)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    base = f"http://127.0.0.1:{port}/"
    try:
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                urllib.request.urlopen(base, timeout=1).close()
                break
            except OSError:
                time.sleep(0.05)
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900}, extra_http_headers={
                "Cf-Access-Authenticated-User-Email": "reviewer@example.com"})
            page.set_default_timeout(5_000)
            page.goto(base, wait_until="networkidle")
            frame = page.frame_locator("#content-frame")
            frame.locator('.card[data-anchor-id="d:q3"] .annotate-card-state').wait_for()

            expected = {"d:q1": ("done", "Addressed"), "d:q2": ("done", "Done"),
                        "d:q3": ("review", "Needs my review")}
            for anchor, (state, label) in expected.items():
                card = frame.locator(f'.card[data-anchor-id="{anchor}"]')
                assert card.get_attribute("data-annotate-state") == state
                assert card.locator(".annotate-card-state").inner_text().strip() == label
                prompt_visible = card.locator("p.q").is_visible()
                assert prompt_visible is (state == "review"), anchor

            # Same words on both sides, item by item.
            for cid, anchor in (("withdrawn-1", "d:q1"), ("accepted-2", "d:q2"),
                                ("open-3", "d:q3")):
                rail = page.locator(f'.citem[data-comment-id="{cid}"] .citem-status')
                body = frame.locator(f'.card[data-anchor-id="{anchor}"] .annotate-card-state')
                assert rail.inner_text().strip().lower() == body.inner_text().strip().lower()
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
