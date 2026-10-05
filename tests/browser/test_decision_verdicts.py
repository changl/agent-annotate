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

from single_page import feedback, history, ready, section  # noqa: E402

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

# D3 item 2: the labels Chang's cheerticketing round actually carried — far
# longer than the rail is wide.
LONG_LABEL_CARD = dict(
    CARD,
    decision_request={
        "prompt": "Refund button vs the published no-refunds policy — which changes?",
        "requested_at": "2026-09-17T09:00:00Z",
        "recommendation": "accept",
        "options": [
            {
                "id": "accept",
                "label": "Update the policy — refunds are allowed at the client's discretion",
                "consequence": "docs/ROLES.md and the customer-facing terms both change. "
                "The button stays as drawn.",
                "style": "primary",
            },
            {
                "id": "changes",
                "label": "Keep the policy, reframe the button as an audited order correction",
                "consequence": "B4 is redrawn with a required authorization note and a "
                "correction label, not the word refund.",
            },
            {
                "id": "reject",
                "label": "Leave both as they are for now",
                "consequence": "The product and the published policy stay in contradiction; "
                "support absorbs it.",
            },
        ],
    },
)

RESOLVED_PRIOR_CARD = dict(
    CARD,
    status="resolved_in_version",
    resolved_in_version="v2",
    resolution_anchor_id="s:overview",
    resolved_at="2026-09-17T10:30:00Z",
    resolved_by="agent:test",
)

LEGACY_CAPS = json.dumps(
    {"version": "2.19", "batch": True, "rounds": True, "decision_schema": 2, "decision_request_cap": 8192}
)


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _serve(tmp_path, card=None, anchor="s:overview"):
    """The demo page with one unresolved decision card pinned to `anchor`."""
    source = Path(__file__).parents[2] / "examples" / "demo"
    slug_dir = tmp_path / "demo"
    shutil.copytree(source, slug_dir)
    seeded = dict(card or CARD, anchor_id=anchor)
    (slug_dir / "comments.json").write_text(
        json.dumps({"schema_version": 2, "anchors": {anchor: [seeded]}, "archived": {}}), encoding="utf-8"
    )
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
    return process, base, slug_dir


def _open(runner, base, legacy=False):
    browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
    page = browser.new_page(
        viewport={"width": 1280, "height": 800},
    )
    if legacy:
        # Answer the one capabilities probe with a pre-D2 body. Everything
        # else still hits the real server.
        page.route(
            "**/api/capabilities",
            lambda route: route.fulfill(status=200, content_type="application/json", body=LEGACY_CAPS),
        )
    page.set_default_timeout(5_000)
    page.goto(base, wait_until="networkidle")
    ready(page)
    feedback(page)
    return browser, page


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_a_d2_server_shows_request_changes(tmp_path):
    process, base, slug_dir = _serve(tmp_path)
    try:
        with playwright.sync_playwright() as runner:
            browser, page = _open(runner, base, legacy=False)
            btn = page.locator(".decision-btn.decision-changes")
            btn.wait_for(state="visible")
            btn.click()
            assert page.locator(".decision-say-ta").evaluate("el => el === document.activeElement")
            assert (
                "decision"
                not in json.loads((slug_dir / "comments.json").read_text())["anchors"]["s:overview"][0]
            )
            page.locator(".decision-say-ta").fill("name the columns first")
            btn.click()
            section(page, "ready")
            playwright.expect(page.locator(".ans")).to_have_text("name the columns first")
            decision = json.loads((slug_dir / "comments.json").read_text())["anchors"]["s:overview"][0][
                "decision"
            ]
            assert decision["verdict"] == "changes" and decision["text"] == "name the columns first"
            assert decision["round_pending"]
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_a_pre_d2_server_still_shows_free_text_answer(tmp_path):
    process, base, slug_dir = _serve(tmp_path)
    try:
        with playwright.sync_playwright() as runner:
            browser, page = _open(runner, base, legacy=True)
            btn = page.locator(".decision-btn.decision-comment")
            btn.wait_for(state="visible")
            btn.click()
            assert page.locator(".decision-say-ta").evaluate("el => el === document.activeElement")
            assert (
                "decision"
                not in json.loads((slug_dir / "comments.json").read_text())["anchors"]["s:overview"][0]
            )
            page.locator(".decision-say-ta").fill("just a remark")
            btn.click()
            section(page, "ready")
            playwright.expect(page.locator(".ans")).to_have_text("just a remark")
            decision = json.loads((slug_dir / "comments.json").read_text())["anchors"]["s:overview"][0][
                "decision"
            ]
            assert decision["verdict"] == "comment" and decision["text"] == "just a remark"
            assert decision["round_pending"]
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_resolved_prior_round_card_is_history_not_v2_outstanding_work(tmp_path):
    process, base, slug_dir = _serve(tmp_path, card=RESOLVED_PRIOR_CARD)
    try:
        shutil.copyfile(slug_dir / "versions/v1.html", slug_dir / "versions/v2.html")
        (slug_dir / "current.html").unlink()
        (slug_dir / "current.html").symlink_to(Path("versions/v2.html"))
        (slug_dir / "current.meta.json").write_text(
            json.dumps({"current": "v2", "history": [{"version": "v1"}, {"version": "v2"}]})
        )
        with playwright.sync_playwright() as runner:
            browser, page = _open(runner, base)
            assert page.evaluate("() => AA.counts().review.needs") == 0
            assert page.locator('#comment-list [data-section="needs"]').count() == 0
            history(page)
            page.locator('#vrail-body-review .vrow[data-version="v1"]').click()
            feedback(page)
            section(page, "done")
            assert page.locator(".ans").inner_text() == "Resolved in v2"
            assert page.locator(".decision-btn").count() == 0
            page.reload(wait_until="networkidle")
            ready(page)
            section(page, "done")
            assert page.locator(".ans").inner_text() == "Resolved in v2"
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_explicit_item_numbers_control_rail_order(tmp_path):
    process, base, slug_dir = _serve(tmp_path)
    try:
        newer_14 = dict(
            CARD,
            id="card-number-14",
            number=14,
            anchor_id="s:overview",
            text="Fourteen",
            created_at="2026-09-17T11:00:00Z",
        )
        older_15 = dict(
            CARD,
            id="card-number-15",
            number=15,
            anchor_id="s:overview:bottom",
            text="Fifteen",
            created_at="2026-09-17T09:00:00Z",
        )
        (slug_dir / "comments.json").write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "anchors": {
                        "s:overview": [newer_14],
                        "s:overview:bottom": [older_15],
                    },
                    "archived": {},
                }
            ),
            encoding="utf-8",
        )

        with playwright.sync_playwright() as runner:
            browser, page = _open(runner, base)
            cards = page.locator("#comment-list .citem")
            assert cards.count() == 2
            assert cards.nth(0).locator(".citem-num").inner_text() == "#14"
            assert cards.nth(0).locator(".citem-txt").inner_text() == "Fourteen"
            assert cards.nth(1).locator(".citem-num").inner_text() == "#15"
            assert cards.nth(1).locator(".citem-txt").inner_text() == "Fifteen"
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_one_number_per_item_and_withdrawn_cards_are_done(tmp_path):
    process, base, slug_dir = _serve(tmp_path)
    try:
        legacy = dict(
            CARD, id="legacy-10", anchor_id="d:q10", decision_request={"prompt": "Q10 Build the inbox?"}
        )
        withdrawn = dict(
            CARD,
            id="withdrawn-19",
            number=19,
            anchor_id="d:q19",
            status="addressed_by_agent",
            response_text="Withdrawn.",
        )
        (slug_dir / "comments.json").write_text(
            json.dumps(
                {"schema_version": 2, "anchors": {"d:q10": [legacy], "d:q19": [withdrawn]}, "archived": {}}
            )
        )
        with playwright.sync_playwright() as runner:
            browser, page = _open(runner, base)
            section(page, "done")
            assert page.locator('.citem[data-comment-id="legacy-10"] .citem-num').inner_text() == "#10"
            assert page.locator('.citem[data-comment-id="withdrawn-19"] .citem-num').inner_text() == "#19"
            rail = page.locator("#comment-list").inner_text()
            assert "d:q" not in rail and "v1" not in rail and "Q10" not in rail
            assert "Build the inbox?" in rail
            assert page.locator('.citem[data-comment-id="withdrawn-19"] .decision-btn').count() == 0
            assert page.locator('#comment-list [data-section="needs"] .badge').inner_text() == "1"
            assert page.locator('#comment-list [data-section="done"] .badge').inner_text() == "1"
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_an_answer_in_words_stops_nagging_the_reviewer(tmp_path):
    process, base, slug_dir = _serve(tmp_path)
    try:
        with playwright.sync_playwright() as runner:
            browser, page = _open(runner, base)
            page.locator(".decision-say-ta").fill("what does legal say?")
            playwright.expect(page.locator("#send-count")).to_have_text("1")
            page.locator("#send-btn:visible, #round-finish-btn:visible").first.click()
            page.locator("#round-submit-btn").click()
            page.locator("#round-confirm-backdrop").wait_for(state="hidden")
            section(page, "waiting")
            stored = json.loads((slug_dir / "comments.json").read_text())["anchors"]["s:overview"][0]
            assert (
                stored["decision"]["verdict"] == "comment"
                and stored["decision"]["text"] == "what does legal say?"
            )
            assert stored["replies"][-1]["text"] == "💬 Answer in words: what does legal say?"
            assert page.locator(".decision-btn").count() == 0
            assert page.evaluate("() => AA.counts().review.needs") == 0
            assert page.locator("#send-count").inner_text() == "0"
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_a_long_option_label_stays_inside_the_rail(tmp_path):
    """D3 item 2 (user-reported: "the decision options in the feedback rail
    don't wrap and extend beyond the screen, making them unreadable")."""
    process, base, slug_dir = _serve(tmp_path, card=LONG_LABEL_CARD)
    try:
        with playwright.sync_playwright() as runner:
            browser, page = _open(runner, base)
            page.locator(".decision-btn").first.wait_for(state="visible")
            drawer = page.locator("#drawer").bounding_box()
            limit = drawer["x"] + drawer["width"]
            for name in (".decision-btn", ".decision-consequence", ".decision-say"):
                boxes = page.locator(name)
                for i in range(boxes.count()):
                    box = boxes.nth(i).bounding_box()
                    assert box["x"] + box["width"] <= limit + 1, name
            # Wrapping, not truncation: the tall button proves the label is
            # on more than one line.
            assert page.locator(".decision-btn.decision-accept").bounding_box()["height"] > 30
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_clicking_a_feedback_card_focuses_its_reply_and_keeps_the_draft(tmp_path):
    process, base, slug_dir = _serve(tmp_path, anchor="s:overview:bottom")
    try:
        with playwright.sync_playwright() as runner:
            browser, page = _open(runner, base)
            card = page.locator(".citem").first
            card.locator(".decision-prompt").click()
            frame = page.frame_locator("#content-frame")
            playwright.expect(frame.locator('[data-anchor-id="s:overview:bottom"]')).to_have_class(
                __import__("re").compile(".*goto-highlight.*")
            )
            box = card.locator(".decision-say-ta")
            box.fill("here")
            assert box.evaluate("el => el === document.activeElement")
            assert page.locator("#content-frame").is_visible()
            page.wait_for_function("() => Object.values(localStorage).some(v => v.includes('here'))")
            page.reload(wait_until="networkidle")
            ready(page)
            feedback(page)
            assert box.input_value() == "here"
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
