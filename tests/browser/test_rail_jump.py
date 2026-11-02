"""One click on a rail card lands its place at the top of the page and keeps it there (Chang, 2026-11-02).

"I have to click it typically 2+ times in order to actually go to the correct
place on the page." A smooth scroll was aimed once, then the pictures above the
place loaded (side-by-side pictures have no size until they load) and pushed it
down. The jump now lands at once and holds the place while the page settles,
including when the place is in a folded section.
"""

import json
import socket
import sys
from pathlib import Path

import pytest
from single_page import CHROME, ready, section
from test_keep_drafts import _start, _stop

from agent_annotate.pagegen import generate

sys.path.insert(0, str(Path(__file__).parents[1]))
from test_pagegen_images import png  # noqa: E402

playwright = pytest.importorskip("playwright.sync_api")

PICTURES = 8
OPTIONS = [{"id": "now", "label": "Ship now"}, {"id": "later", "label": "Ship later"}]


def _directory(tmp_path):
    shots = tmp_path / "shots"
    shots.mkdir()
    blocks = []
    for n in range(PICTURES):
        (shots / f"a{n}.png").write_bytes(png(390, 844, (230, 200, 20 * n)))
        (shots / f"b{n}.png").write_bytes(png(390, 844, (20 * n, 230, 200)))
        blocks.append(f"## Screen {n}\n\n```compare\ncurrent: shots/a{n}.png | Today\nproposed: shots/b{n}.png | Proposed\n```\n")
    cards = [
        {"number": 1, "anchor_id": "d:q1", "decision_request": {"prompt": "Approve the far screen?", "options": OPTIONS,
                                                                  "evidence": [{"anchor": "s:far:p1", "label": "Far"}]}},
        {"number": 2, "anchor_id": "d:q2", "decision_request": {"prompt": "Set aside one?", "options": OPTIONS,
                                                                  "evidence": [{"anchor": "s:set-aside:p1", "label": "Aside"}]}},
    ]
    tail = "\n\n".join(f"Closing note {i}." for i in range(40))
    source = tmp_path / "review.md"
    source.write_text(
        "---\ntitle: Rail jump\nversion: v1\nfull_plan: true\nother_files_required: none\n---\n\nIntro.\n\n"
        + "\n".join(blocks)
        + "\n## Far\n\nThe place the first card asks about.\n"
        + "\n## Set aside\n\nThe place the second card asks about.\n"
        + f"\n## Tail\n\n{tail}\n"
        + "\n## Questions for Chang\n\n```cards\n" + json.dumps(cards) + "\n```\n")
    directory = tmp_path / "review"
    generate(source, directory)
    created = "2026-11-02T10:00:00Z"
    anchors = {}
    for card in cards:
        comment = dict(card, id=f"question-{card['number']}", text=card["decision_request"]["prompt"],
                       author="agent:rail-jump", created_at=created, version="v1", status="open")
        comment["decision_request"] = dict(card["decision_request"], requested_at=created)
        anchors[card["anchor_id"]] = [comment]
    anchors["d:q2"][0]["answer_later"] = {"ts": created}  # its section folds on load
    (directory / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": anchors, "archived": {}}))
    return directory


@pytest.fixture(params=["ipad-webkit", "desktop-chrome"])
def session(request, tmp_path):
    directory = _directory(tmp_path)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = _start(tmp_path, directory, port)
    base = f"http://127.0.0.1:{port}/"
    try:
        with playwright.sync_playwright() as runner:
            if request.param == "ipad-webkit":
                try:
                    browser = runner.webkit.launch()
                except Exception:
                    pytest.skip("Playwright WebKit is not installed")
                page = browser.new_context(**dict(runner.devices["iPad Pro 11"])).new_page()
            else:
                if not CHROME.exists():
                    pytest.skip("Google Chrome is not installed")
                browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.set_default_timeout(8000)
            page.goto(base + "#view=review", wait_until="networkidle")
            ready(page)
            frame = page.frame_locator("#content-frame")
            frame.locator('[data-strip-item="question-1"]').wait_for(state="attached")
            touch = request.param == "ipad-webkit"
            try:
                yield page, frame, touch
            finally:
                browser.close()
    finally:
        _stop(server)


def _click_rail_card(page, touch, n, rail_section=None):
    page.evaluate("() => window.AA.rail.reveal()")
    page.wait_for_timeout(400)
    if rail_section:
        section(page, rail_section)
    card = page.locator(f'#comment-list .citem[data-comment-id="question-{n}"]').first
    card.scroll_into_view_if_needed()
    box = card.bounding_box()
    # The card's body, not a button on it: one click, as he does.
    if touch:
        page.touchscreen.tap(box["x"] + 12, box["y"] + 10)
    else:
        page.mouse.click(box["x"] + 12, box["y"] + 10)


def _place_top(frame, n):
    # Where the question's place is, once every picture near it has loaded.
    return frame.locator("body").evaluate(f"""async () => {{
      const item = () => document.querySelector('[data-strip-item="question-{n}"]');
      for (let i = 0; i < 40; i++) {{
        await new Promise(r => setTimeout(r, 100));
        const near = [...document.images].filter(img => {{ const r = img.getBoundingClientRect(); return r.bottom > -2000 && r.top < innerHeight + 2000; }});
        if (near.every(img => img.complete)) break;
      }}
      await new Promise(r => setTimeout(r, 1000));
      const it = item();
      return it && it.getClientRects().length ? it.closest('[data-annotate-strip]').getBoundingClientRect().top : null;
    }}""")


def test_one_click_lands_the_card_at_the_top_after_the_pictures_load(session):
    page, frame, touch = session
    _click_rail_card(page, touch, 1)
    top = _place_top(frame, 1)
    assert top is not None and abs(top - 12) <= 4, top


def test_one_click_from_mid_page_lands_too(session):
    page, frame, touch = session
    frame.locator("body").evaluate("() => scrollTo(0, document.documentElement.scrollHeight / 3)")
    page.wait_for_timeout(500)
    _click_rail_card(page, touch, 1)
    top = _place_top(frame, 1)
    assert top is not None and abs(top - 12) <= 4, top


def test_one_click_opens_a_folded_section_and_lands_there(session):
    page, frame, touch = session
    assert frame.locator('[data-strip-item="question-2"]').is_hidden()  # set aside: its section is folded
    _click_rail_card(page, touch, 2, "later")
    top = _place_top(frame, 2)
    assert top is not None and abs(top - 12) <= 4, top
