"""A card jumps to where it sits in the document, and always offers Answer in words.

Chang, 2026-10-16 (#14): clicking a card said "Location unavailable in this
version" although the question was right there in the page. A page with no
"Questions for Chang" section has no element for the card's own d:qN anchor;
its only location is the in-flow card at its evidence. (#15): the "Answer in
words" choice was gone from the options the skill promises on every card.
"""

import json
import re

import pytest
from single_page import browser_page, feedback, go
from test_card_layout import CHROME, _in_view, _wait

from agent_annotate.categories import publish_plan_revision, save_findings_sets
from agent_annotate.pagegen import generate

playwright = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")

SOURCE = """---
title: Jump review
version: v1
full_plan: true
other_files_required: none
---

Intro.

## Mockup

FIGURE

What the header would look like.

## Pages

| Page | Open cards |
|---|---|
| audit | 470 |
| rebex | 26 |

## Tail

The end.
"""

FIGURE = ('<figure data-anchor-id="s:mockup:p1" style="margin:16px 0 24px">'
          '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="120"><rect width="320" height="120" fill="teal"/></svg>'
          '<figcaption>Header mockup</figcaption></figure>')

PLAN = ('<!doctype html><html><head><title>Launch plan</title></head><body><div class="aa">'
        '<section data-anchor-id="s:launch"><h2>Launch</h2><p data-anchor-id="s:launch:p1">Verify all tabs.</p>'
        '<figure data-anchor-id="s:launch:fig"><svg xmlns="http://www.w3.org/2000/svg" width="200" height="80">'
        '<rect width="200" height="80" fill="olive"/></svg><figcaption>Rollout</figcaption></figure></section>'
        '</div></body></html>')


def _card(cid, number, anchor, prompt, options, evidence, **extra):
    created = "2026-10-16T10:00:00Z"
    return dict({
        "id": cid, "number": number, "anchor_id": anchor, "text": prompt, "author": "agent:test",
        "created_at": created, "version": "v1", "status": "open",
        "decision_request": {"prompt": prompt, "options": options, "evidence": evidence, "requested_at": created},
    }, **extra)


@pytest.fixture
def page_dir(tmp_path):
    source = tmp_path / "jump.md"
    source.write_text(SOURCE)
    directory = tmp_path / "jump"
    generate(source, directory)
    html = directory / "versions" / "v1.html"
    text = html.read_text()
    text, n = re.subn(r'<p[^>]*data-anchor-id="s:mockup:p1"[^>]*>FIGURE</p>', FIGURE, text)
    assert n == 1
    html.write_text(text)
    rows = re.findall(r'data-anchor-id="(tbl:pages:row:[^"]+)"', text)
    cards = [
        _card("card-1", 1, "d:q1", "Put the Beads link in the header?",
              [{"id": "header", "label": "Header link"}, {"id": "docs", "label": "Documents tab only"}],
              [{"label": "Mockup", "anchor": "s:mockup:p1"}]),
        _card("card-2", 2, "d:q2", "Archive the audit page?", ["accept", "reject"],
              [{"label": "Pages", "anchor": rows[0]}]),
        _card("plan-3", 3, "d:q3", "Approve the rollout?", [{"id": "go", "label": "Go"}, {"id": "wait", "label": "Wait"}],
              [{"label": "Rollout", "anchor": "s:launch:fig"}], category="plans", doc="plan:launch"),
        _card("finding-4", 4, "finding:contrast", "Fix border contrast?",
              [{"id": "fix", "label": "Fix it"}, {"id": "keep", "label": "Keep it"}], [],
              category="findings", finding={"set": "design", "title": "Border contrast"}),
    ]
    (directory / "comments.json").write_text(json.dumps(
        {"schema_version": 2, "anchors": {c["anchor_id"]: [c] for c in cards}, "archived": {}}))
    save_findings_sets(directory, [{"id": "design", "label": "Design audit"}])
    publish_plan_revision(directory, "launch", PLAN, title="Launch plan")
    return directory


def _stored(directory, cid):
    anchors = json.loads((directory / "comments.json").read_text())["anchors"]
    return next(c for items in anchors.values() for c in items if c["id"] == cid)


def _jumped(page, cid):
    """The rail card reports no missing location and its in-flow card is in view, highlighted."""
    frame = page.frame_locator("#content-frame")
    strip = frame.locator(f'[data-strip-item="{cid}"]')
    wrap = strip.locator("xpath=ancestor::*[@data-strip-anchor][1]")
    _wait(lambda: _in_view(strip) and "goto-highlight" in (wrap.get_attribute("class") or ""), page)
    assert page.locator(f'.citem[data-comment-id="{cid}"] .citem-loc.unavailable').count() == 0


def test_a_card_and_its_evidence_jump_to_the_document(tmp_path, page_dir):
    with browser_page(tmp_path, page_dir) as (page, _):
        frame = page.frame_locator("#content-frame")
        # Neither question has a "Questions" card in the HTML: d:q1 and d:q2 exist only as in-flow cards.
        assert frame.locator('[data-anchor-id="d:q1"], [data-anchor-id="d:q2"]').count() == 0
        frame.locator('[data-strip-item="card-2"]').wait_for()
        feedback(page)
        for cid in ("card-1", "card-2"):
            frame.locator("body").evaluate("() => window.scrollTo(0, 0)")
            page.locator(f'.citem[data-comment-id="{cid}"] .decision-prompt').click()
            _jumped(page, cid)
        # Open in document, on the card's quoted excerpt.
        frame.locator("body").evaluate("() => window.scrollTo(0, 0)")
        page.locator('.citem[data-comment-id="card-1"] [data-action="goto"]').first.click()
        _jumped(page, "card-1")
        # Evidence: a figure and a table row, each highlighted in view.
        for cid, anchor in (("card-1", "s:mockup:p1"), ("card-2", None)):
            card = page.locator(f'.citem[data-comment-id="{cid}"]')
            card.locator(".decision-evidence-toggle").click()
            card.locator(".decision-evidence-link").first.click()
            frame.locator("body").evaluate("() => window.scrollTo(0, 0)")
            card.locator(".decision-evidence-goto").first.click()
            target = frame.locator(f'[data-anchor-id="{anchor}"]') if anchor else frame.locator("tr.goto-highlight")
            _wait(lambda: _in_view(target) and "goto-highlight" in (target.get_attribute("class") or ""), page)
            assert card.locator(".citem-loc.unavailable").count() == 0
        page.screenshot(path=str(tmp_path / "jump-review.png"))

        go(page, "plans", plan="launch")
        frame.locator('[data-strip-item="plan-3"]').wait_for()
        feedback(page)
        page.locator('.citem[data-comment-id="plan-3"] .decision-prompt').click()
        _jumped(page, "plan-3")

        go(page, "findings")
        feedback(page)
        page.locator('#find-rail .citem[data-card="finding-4"], .citem[data-card="finding-4"]').first.click()
        row = page.locator('#find-register tr[data-f="finding-4"]')
        _wait(lambda: "sp-sel" in (row.get_attribute("class") or "") and _in_view(row), page)


def test_every_decision_card_offers_answer_in_words(tmp_path, page_dir):
    with browser_page(tmp_path, page_dir) as (page, _):
        frame = page.frame_locator("#content-frame")
        frame.locator('[data-strip-item="card-1"]').wait_for()
        feedback(page)
        for cid in ("card-1", "card-2"):
            rail = page.locator(f'.citem[data-comment-id="{cid}"] .decision-btns > .decision-btn')
            assert "Answer in words" in rail.last.inner_text()
            assert rail.filter(has_text="Answer in words").count() == 1
            strip = frame.locator(f'[data-strip-item="{cid}"] .annotate-decision-btns > .annotate-decision-btn')
            assert "Answer in words" in strip.last.inner_text()
        # In the page flow: an empty box asks for the words, then the words are the answer.
        item = frame.locator('[data-strip-item="card-1"]')
        words = item.locator(".annotate-decision-comment")
        words.click()
        box = item.locator(".annotate-decision-cmt")
        assert box.get_attribute("placeholder") == "Answer in your own words…"
        assert box.evaluate("el => el === document.activeElement")
        box.fill("Put it next to the tabs.")
        words.click()
        _wait(lambda: (_stored(page_dir, "card-1").get("decision") or {}).get("verdict") == "comment", page)
        assert _stored(page_dir, "card-1")["decision"]["text"] == "Put it next to the tabs."
        # In the rail.
        card = page.locator('.citem[data-comment-id="card-2"]')
        card.locator(".decision-btn.decision-comment").click()
        ta = card.locator(".decision-say-ta")
        assert ta.get_attribute("placeholder") == "Answer in your own words…"
        ta.fill("Archive it after the audit closes.")
        card.locator(".decision-btn.decision-comment").click()
        _wait(lambda: (_stored(page_dir, "card-2").get("decision") or {}).get("verdict") == "comment", page)
        # Findings cards offer it too.
        go(page, "findings")
        feedback(page)
        page.locator('.citem[data-card="finding-4"]').first.click()
        found = page.locator('.citem[data-card="finding-4"] .decision-btns > .decision-btn')
        assert "Answer in words" in found.last.inner_text()
