"""Images and the current-vs-proposed block in a real browser (decision #16).

Portrait pairs and flow rows sit side by side and fit the viewport height;
landscape pairs stack full width, current above proposed. Nothing needs a click.
"""

import json
import sys
import urllib.request
from pathlib import Path

import pytest
from single_page import CHROME, browser_page, go, ready
from test_card_layout import _serve
from test_single_page_acceptance import workspace  # noqa: F401

from agent_annotate.categories import mark_finding_fixed
from agent_annotate.pagegen import generate

sys.path.insert(0, str(Path(__file__).parents[1]))
from test_pagegen_images import png  # noqa: E402

playwright = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")

CARD = {"number": 1, "anchor_id": "d:q1", "decision_request": {
    "prompt": "Ship the one-step checkout?", "recommendation": "ship",
    "options": [{"id": "ship", "label": "Ship"}, {"id": "hold", "label": "Hold"}],
    "evidence": [{"label": "Checkout pair", "anchor": "cmp:checkout"}]}}


@pytest.fixture
def shots_page(tmp_path):
    shots = tmp_path / "shots"
    shots.mkdir()
    for name, size, rgb in (("phone-a", (390, 844), (230, 200, 200)), ("phone-b", (390, 844), (200, 230, 200)),
                            ("desk-a", (1440, 900), (230, 200, 200)), ("desk-b", (1440, 900), (200, 230, 200))):
        (shots / f"{name}.png").write_bytes(png(*size, rgb))
    for n in (1, 2, 3):
        (shots / f"flow-a{n}.png").write_bytes(png(390, 844, (230, 200, 60 * n)))
        (shots / f"flow-b{n}.png").write_bytes(png(390, 844, (60 * n, 230, 200)))
    flow = "\n".join(f"current: shots/flow-a{n}.png | Step {n}\nproposed: shots/flow-b{n}.png | Step {n}"
                     for n in (1, 2, 3))
    source = tmp_path / "page.md"
    source.write_text(
        "---\ntitle: Shots\n---\n\n"
        "## Checkout\n\n```compare\ncurrent: shots/phone-a.png | Today\nproposed: shots/phone-b.png | One-step pay\n```\n\n"
        "## Board\n\n```compare\ncurrent: shots/desk-a.png | Today\nproposed: shots/desk-b.png | Grouped\n```\n\n"
        f"## Sign-in\n\n```compare\n{flow}\n```\n\n"
        "## Single\n\n![Home on a phone](shots/phone-a.png)\n\n"
        f"## Questions for Chang\n\n```cards\n{json.dumps([CARD])}\n```\n",
        encoding="utf-8")
    slug_dir = tmp_path / "items-model"
    generate(source, slug_dir)
    return slug_dir


def _content(page):
    ready(page)
    frame = page.locator("#content-frame").element_handle().content_frame()
    frame.wait_for_selector('[data-anchor-id="cmp:checkout"]')
    frame.wait_for_function("() => [...document.images].every(i => i.complete && i.naturalWidth > 0)")
    return frame


GEOMETRY = """() => {
  const box = el => el.getBoundingClientRect();
  const cells = sel => [...document.querySelectorAll(sel + ' .aa-cmp-cell img')].map(i => box(i));
  const fig = id => document.querySelector(`[data-anchor-id="${id}"]`);
  return {
    vh: innerHeight,
    overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    layouts: Object.fromEntries(['cmp:checkout', 'cmp:board', 'cmp:sign-in'].map(id => [id, fig(id).dataset.layout])),
    phone: cells('[data-anchor-id="cmp:checkout"]').map(r => ({top: r.top, left: r.left, right: r.right, h: r.height})),
    desk: cells('[data-anchor-id="cmp:board"]').map(r => ({top: r.top, bottom: r.bottom, w: r.width})),
    deskWidth: box(fig('cmp:board')).width,
    flow: cells('[data-anchor-id="cmp:sign-in"]').map(r => ({top: r.top, h: r.height})),
    single: box(document.querySelector('[data-anchor-id="fig:home-on-a-phone"] img')).height,
    labels: [...fig('cmp:board').querySelectorAll('.aa-cmp-label')].map(l => l.textContent),
    stripAfterCompare: !!fig('cmp:checkout').nextElementSibling?.matches('.annotate-decision-strip, .annotate-strip-block'),
  };
}"""


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_pairs_flows_and_figures_are_judged_inline(tmp_path, shots_page, width, height):
    process, base = _serve(tmp_path, shots_page)
    try:
        cards = json.loads((shots_page / "cards.json").read_text())
        request = urllib.request.Request(
            base + "api/comments/batch", method="POST",
            data=json.dumps({"items": [dict(card, version="v1") for card in cards]}).encode(),
            headers={"Content-Type": "application/json", "X-Annotate-Agent": "agent:images-browser"})
        urllib.request.urlopen(request).close()
        asset = next((shots_page / "assets").iterdir()).name
        with urllib.request.urlopen(base + "assets/" + asset) as response:
            assert response.headers["Content-Security-Policy"] == "sandbox"
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert response.headers["Content-Type"] == "image/png"

        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            page.set_default_timeout(10_000)
            page.goto(base + "#view=review", wait_until="networkidle")
            frame = _content(page)
            frame.wait_for_selector(".annotate-decision-strip")
            g = frame.evaluate(GEOMETRY)
            assert g["overflow"] <= 0
            assert g["layouts"] == {"cmp:checkout": "side", "cmp:board": "stack", "cmp:sign-in": "side"}
            # Phone pair: side by side, current first, the whole pair fits the viewport height.
            cur, pro = g["phone"]
            assert abs(cur["top"] - pro["top"]) < 1 and cur["right"] <= pro["left"]
            assert cur["h"] <= g["vh"] and pro["h"] <= g["vh"]
            # Desktop pair: stacked, current above proposed, each nearly full width, labelled.
            cur, pro = g["desk"]
            assert cur["bottom"] <= pro["top"] and min(cur["w"], pro["w"]) >= 0.9 * g["deskWidth"]
            assert g["labels"] == ["Current", "Proposed"]
            # Three-screen flow: a current row of three and a proposed row of three, each row within the viewport.
            rows = g["flow"]
            assert len({round(r["top"]) for r in rows[:3]}) == 1 and len({round(r["top"]) for r in rows[3:]}) == 1
            assert rows[3]["top"] > rows[0]["top"] and all(r["h"] <= g["vh"] for r in rows)
            assert 0 < g["single"] <= g["vh"]
            # The card citing the pair renders right after it.
            assert g["stripAfterCompare"]

            # Light and dark: labels keep contrast with their chip.
            for theme in ("dark", "light"):
                frame.evaluate("t => document.documentElement.dataset.theme = t", theme)
                colors = frame.evaluate("""() => { const l = document.querySelector('.aa-cmp-label[data-role="proposed"]');
                    const s = getComputedStyle(l); return [s.color, s.backgroundColor]; }""")
                assert colors[0] != colors[1]
            # The Aa text-size control scales captions.
            before = frame.evaluate("() => parseFloat(getComputedStyle(document.querySelector('.aa-cmp-cell figcaption')).fontSize)")
            frame.evaluate("() => document.documentElement.style.setProperty('--aa-text', '1.5')")
            after = frame.evaluate("() => parseFloat(getComputedStyle(document.querySelector('.aa-cmp-cell figcaption')).fontSize)")
            assert after == pytest.approx(before * 1.5, rel=0.02)
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_finding_proof_uses_the_same_compare_block(tmp_path, workspace):  # noqa: F811
    attachments = workspace / "attachments"
    (attachments / "before.png").write_bytes(png(390, 844, (230, 200, 200)))
    (attachments / "after.png").write_bytes(png(390, 844, (200, 230, 200)))
    mark_finding_fixed(workspace, 21, by="agent:builder", note="Contrast repaired", proof=[
        {"label": "Border today", "attachment": "before.png", "role": "current", "w": 390, "h": 844},
        {"label": "Border fixed", "attachment": "after.png", "role": "proposed", "w": 390, "h": 844},
        {"label": "Verification report", "url": "https://example.test/proof"},
    ])
    with browser_page(tmp_path, workspace) as (page, _):
        go(page, "findings")
        page.locator('#find-register [data-f="finding-21"]').click()
        block = page.locator('#rail-findings .citem.hl[data-card="finding-21"] .fix-proof .aa-compare')
        block.wait_for(state="visible")
        assert block.get_attribute("data-layout") == "side"
        page.wait_for_function("() => [...document.querySelectorAll('.aa-compare img')].every(i => i.complete && i.naturalWidth > 0)")
        cells = block.locator(".aa-cmp-cell")
        assert [cells.nth(i).get_attribute("data-role") for i in range(2)] == ["current", "proposed"]
        assert cells.nth(0).locator("img").get_attribute("src") == "./attachments/before.png"
        a, b = (cells.nth(i).locator("img").bounding_box() for i in range(2))
        assert abs(a["y"] - b["y"]) < 1 and a["x"] + a["width"] <= b["x"]
        assert block.locator(".aa-cmp-label").all_inner_texts() == ["Current", "Proposed"]
        assert page.locator("#rail-findings .fix-proof-links a", has_text="Verification report").count() == 1
