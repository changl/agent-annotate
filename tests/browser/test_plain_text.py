"""The page's own words stay plain (Chang, 2026-11-01: the page reads as cryptic).

Quoted excerpts carry the text, not the image controls beside a picture; a baked
question card never points at a button that is gone; delivery says in plain words
where the reviewer's last Send is.
"""

import json
import sys
from pathlib import Path

import pytest
from single_page import browser_page, ready

from agent_annotate import long_pages
from agent_annotate.pagegen import generate

sys.path.insert(0, str(Path(__file__).parents[1]))
from test_pagegen_images import png, write  # noqa: E402

playwright = pytest.importorskip("playwright.sync_api")

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
EXAMPLE = (Path(__file__).parents[1] / "fixtures" / "full_review.md").read_text()


def _question(cid, anchor, number, **extra):
    return {"id": cid, "anchor_id": anchor, "number": number, "text": f"Question {number}?", "author": "agent:test",
            "created_at": "2026-11-01T09:00:00Z", "version": "v1", "status": "open",
            "decision_request": {"prompt": f"Question {number}?", "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                                 "requested_at": "2026-11-01T09:00:00Z", **extra.pop("request", {})}, **extra}


def test_a_quoted_excerpt_leaves_out_the_image_controls(tmp_path, monkeypatch):
    real = long_pages.subprocess.run

    def sips(command, **kwargs):  # the 1,200 px preview, without macOS sips
        if command[0] != "/usr/bin/sips":
            return real(command, **kwargs)
        Path(command[-1]).write_bytes(png(600, 400))
        return type("Done", (), {"returncode": 0})()
    monkeypatch.setattr(long_pages.shutil, "which", lambda name: "/usr/bin/sips")
    monkeypatch.setattr(long_pages.subprocess, "run", sips)
    write(tmp_path / "shots" / "wide.png", png(2400, 1600, (40, 120, 200)))
    source = tmp_path / "page.md"
    source.write_text("---\ntitle: Shots\nother_files_required: none\n---\n\n## Alpha\n\nThe board before the change.\n\n"
                      "![Board](shots/wide.png)\n\n## Beta\n\nWhat we ask.\n", encoding="utf-8")
    directory = tmp_path / "items-model"
    generate(source, directory)
    (directory / "comments.json").write_text(json.dumps({"schema_version": 2, "archived": {}, "anchors": {
        "s:beta": [_question("q-1", "s:beta", 1, request={"evidence": [{"label": "Board", "anchor": "s:alpha"}]})]}}))
    with browser_page(tmp_path, directory) as (page, _):
        frame = page.frame_locator("#content-frame")
        frame.locator(".aa-img-bar .aa-img-id").wait_for()  # the picture has its IMG label and zoom
        assert frame.locator("a.aa-full").count() == 1
        quote = frame.locator('[data-strip-item="q-1"] .annotate-excerpt-text')
        playwright.expect(quote).to_contain_text("The board before the change.")
        text = quote.text_content()
        assert "IMG" not in text and "Full size" not in text and "25%" not in text, text


def test_a_baked_card_never_asks_to_press_finish_review(tmp_path):
    source = tmp_path / "page.md"
    source.write_text(EXAMPLE, encoding="utf-8")
    directory = tmp_path / "items-model"
    generate(source, directory)
    html = (directory / "versions" / "v1.html").read_text()
    assert "Answer it on the card" not in html and 'class="q"' not in html
    # A page published before this still carries the line; with no live card it stays hidden.
    old = html.replace('<div class="card" data-anchor-id="d:q1">', '<div class="card" data-anchor-id="d:q1">'
                       '<p class="q">Answer it on the card, then press Finish review.</p>', 1)
    assert old != html
    for path in (directory / "versions" / "v1.html", directory / "current.html"):
        path.write_text(old)
    with browser_page(tmp_path, directory) as (page, _):
        frame = page.frame_locator("#content-frame")
        line = frame.locator(".card > p.q")
        line.wait_for(state="attached")
        frame.locator("#annotate-card-state-style").wait_for(state="attached")
        assert line.is_hidden()


STATES = [
    ({"state": "acknowledged"}, "The agent has read your last Send", "Sent"),
    ({"state": "started"}, "The agent is working on your last Send", "Sent"),
    ({"state": "accepted", "receipt": {"prompt": {"stages": ["input_accepted"]}}}, "Delivered; waiting for the agent to start", "Sent"),
    ({"state": "accepted"}, "Saved; not yet confirmed that the agent got it", "Waiting for the agent"),
    ({"state": "pending", "detail": "Owner process ended"}, "Saved; the agent has not been told yet", "Waiting for the agent"),
    ({"state": "uncertain"}, "Saved; not yet confirmed that the agent got it", "Waiting for the agent"),
    ({"state": "superseded"}, "This page changed agents before your Send was delivered", "Waiting for the agent"),
]


def test_delivery_says_where_the_last_send_is_in_plain_words(tmp_path):
    source = tmp_path / "page.md"
    source.write_text(EXAMPLE, encoding="utf-8")
    directory = tmp_path / "items-model"
    generate(source, directory)
    key = "0123456789abcdef01234567"
    answered = _question("q-1", "d:q1", 1, decision={"verdict": "a", "text": "A", "ts": "2026-11-01T10:00:00Z",
                                                     "by": "reviewer@example.com", "delivery_id": key})
    (directory / "comments.json").write_text(json.dumps({"schema_version": 2, "archived": {}, "anchors": {"d:q1": [answered]}}))
    journal = tmp_path / "state" / "deliveries" / "bus" / "items-model.json"
    journal.parent.mkdir(parents=True)
    journal.write_text(json.dumps({"offset": 0, "deliveries": {key: {"id": key, **STATES[0][0]}}}))
    with browser_page(tmp_path, directory) as (page, _):
        frame = page.frame_locator("#content-frame")
        for row, banner, card in STATES:
            journal.write_text(json.dumps({"offset": 0, "deliveries": {key: {"id": key, **row}}}))
            page.reload(wait_until="networkidle")
            ready(page)
            status = page.locator("#delivery-status")
            playwright.expect(status).to_have_text(banner)
            assert status.get_attribute("title") == (row.get("detail") or "")
            playwright.expect(frame.locator('[data-strip-item="q-1"] .annotate-send-state')).to_have_text(card)
