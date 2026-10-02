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

from agent_annotate.pagegen import generate  # noqa: E402

EXAMPLE = (Path(__file__).parents[1] / "fixtures" / "full_review.md").read_text()

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def _card(cid, anchor, number, **extra):
    return {"id": cid, "anchor_id": anchor, "number": number, "text": f"Card {number}",
            "author": "agent:test", "created_at": "2026-09-23T09:00:00Z", "version": "v1",
            "status": "open",
            "decision_request": {"prompt": f"Question {number}?",
                                 "requested_at": "2026-09-23T09:00:00Z"},
            **extra}


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_questions_have_one_current_status_and_no_competing_reference_surface(tmp_path):
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
         "--port", str(port), "--local-author", "reviewer@example.com", "--local-author-name", "Browser Reviewer"],
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
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.set_default_timeout(5_000)
            page.goto(base, wait_until="networkidle")
            page.locator('.citem[data-comment-id="open-3"]').wait_for()
            assert page.locator('.citem').count() == 1, 'Only the unanswered question asks for review'
            assert page.locator('.chip-review .chip-n').inner_text() == '1'
            assert page.locator('.chip-done .chip-n').inner_text() == '2'
            page.locator('[data-filter="all"]').click()
            expected = {'withdrawn-1':('done','Addressed'), 'accepted-2':('done','Done'),
                        'open-3':('needs-review','Needs my review')}
            for cid, (state, label) in expected.items():
                item = page.locator(f'.citem[data-comment-id="{cid}"]')
                assert state in item.get_attribute('class')
                assert item.locator('.citem-status').inner_text().strip().lower() == label.lower()
            assert page.locator('.citem[data-comment-id="withdrawn-1"] .decision-btn').count() == 0
            assert 'Accepted' in page.locator('.citem[data-comment-id="accepted-2"] .decision-verdict-chip').inner_text()
            assert page.locator('.citem[data-comment-id="open-3"] .citem-num').inner_text() == '#3'
            page.locator('[data-workspace-tab="details"]').click()
            frame = page.frame_locator('#content-frame')
            frame.locator('.card[data-anchor-id="d:q3"]').wait_for(state='attached')
            for anchor in ('d:q1','d:q2','d:q3'):
                assert frame.locator(f'.card[data-anchor-id="{anchor}"]').is_hidden()
            assert frame.locator('.annotate-decision-strip').count() == 0, 'Reference history never repeats live feedback'
            page.locator('[data-workspace-tab="feedback"]').click()
            assert page.locator('.citem[data-comment-id="open-3"]').is_visible()
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
