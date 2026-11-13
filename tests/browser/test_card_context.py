"""FLD v811, cards 38884–38887: each ask stays with its own text and pictures."""

import json
from pathlib import Path

import pytest
from review_fixtures import complete
from single_page import browser_page, feedback
from test_pagegen_images import png

from agent_annotate.pagegen import generate

playwright = pytest.importorskip("playwright.sync_api")
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
FIXTURE = Path(__file__).parents[1] / "fixtures" / "fld-v811-card-context.md"


def test_inline_asks_keep_their_context_and_screenshots(tmp_path):
    # Exact source from the reported live round; only image pixels are synthetic.
    source = tmp_path / "page.md"
    source.write_text(FIXTURE.read_text())
    images = ["8cf7f4b0bb96-e5ii-ios.png", "e84c0a2c30de-e5ii-and.png", "a6ab35d8be15-2yji.png",
              "6203a40a1ad0-gzab-ios-before-after.png", "fe3d0d851d95-gzab-android-before-after.png",
              "51dc2a85f921-xv40o-lock-before-after.png"]
    (tmp_path / "assets").mkdir()
    for image in images:
        (tmp_path / "assets" / image).write_bytes(png(320, 160))
    directory = tmp_path / "items-model"
    generate(source, directory)
    complete(directory)
    cards = json.loads((directory / "versions" / "v1.cards.json").read_text())
    (directory / "comments.json").write_text(json.dumps({"schema_version": 2, "archived": {}, "anchors": {
        c["anchor_id"]: [dict(c, id=str(c["number"]), author="agent:test", version="v1", status="open",
                              created_at="2026-11-12T19:03:00Z")] for c in cards}}))

    with browser_page(tmp_path, directory) as (page, _):
        frame = page.frame_locator("#content-frame")
        feedback(page)
        topics = ["1. Messaging with the least in the way.", "2. The new phone, when it isn't confirmed.",
                  "3. Past events on the phones.", "4. iPhone: the lock in the chat list."]
        captions = ["Android: today vs proposed, with both options", "New phone, not confirmed: A and B on both phones",
                    "Android event page, before and after", "iPhone chat list lock, before and after"]
        for index, c in enumerate(cards):
            cid = str(c["number"])
            card = frame.locator(f'[data-strip-item="{cid}"]')
            quote = card.locator(".annotate-excerpt-text").first
            playwright.expect(card.locator(".annotate-decision-context")).to_have_text(c["decision_request"]["context"])
            playwright.expect(quote).to_contain_text(topics[index])
            for other in topics[:index] + topics[index + 1:]:
                playwright.expect(quote).not_to_contain_text(other)
            for other in cards:
                playwright.expect(quote).not_to_contain_text(other["decision_request"]["prompt"])
            # The preceding screenshot belongs to this question, in the same section.
            assert card.evaluate("el => !!el.closest('section[data-anchor-id]')")
            assert card.evaluate("el => el.closest('[data-annotate-strip]').previousElementSibling.previousElementSibling.querySelector('figcaption').textContent.trim()") == captions[index]
            rail = page.locator(f'.citem[data-comment-id="{cid}"]')
            playwright.expect(rail.locator(".decision-excerpt-text")).to_have_text(quote.text_content())
            card.locator('[data-decision-action="evidence-toggle"]').click()
            card.locator('[data-decision-action="evidence-preview"]').click()
            playwright.expect(card.locator(".annotate-decision-evidence-preview .annotate-excerpt-text")).to_have_text(quote.text_content())

        # A data-driven redraw must not quote the strips it inserted previously.
        page.reload(wait_until="networkidle")
        playwright.expect(frame.locator('[data-strip-item="38887"] .annotate-excerpt-text')).not_to_contain_text(topics[0])


def test_adjacent_asks_share_local_evidence_and_explicit_citations_still_move(tmp_path):
    source = tmp_path / "page.md"
    source.write_text("""---
title: Local evidence
other_files_required: none
---
## Work
An older unrelated update.
### First
Evidence for the first pair.
```ask
#1 First choice?
Own first context.
+ Yes: Proceed.
- No: Wait.
```
```ask
#2 Second choice?
Own second context.
+ Yes: Proceed.
- No: Wait.
```
### Last
Evidence for the last choice.
```ask
#3 Last choice?
+ Yes: Proceed.
- No: Wait.
```
## Questions
```ask
#4 Explicit citation?
+ Yes: Proceed.
- No: Wait.
see: s:work:p2
```
""")
    directory = tmp_path / "items-model"
    generate(source, directory)
    complete(directory)
    cards = json.loads((directory / "versions" / "v1.cards.json").read_text())
    (directory / "comments.json").write_text(json.dumps({"schema_version": 2, "archived": {}, "anchors": {
        c["anchor_id"]: [dict(c, id=str(c["number"]), author="agent:test", version="v1", status="open",
                              created_at="2026-11-12T19:03:00Z")] for c in cards}}))
    with browser_page(tmp_path, directory) as (page, _):
        frame = page.frame_locator("#content-frame")
        for number, expected in [(1, "Evidence for the first pair."), (2, "Evidence for the first pair."),
                                 (3, "Evidence for the last choice."), (4, "Evidence for the first pair.")]:
            quote = frame.locator(f'[data-strip-item="{number}"] .annotate-excerpt-text')
            playwright.expect(quote).to_have_text(expected)
        explicit = frame.locator('[data-strip-item="4"]')
        assert explicit.evaluate("el => el.closest('[data-annotate-strip]').previousElementSibling.dataset.anchorId") == "s:work:p2"
