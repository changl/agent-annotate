"""A section whose questions are all answered or set aside folds to one line (Chang, 2026-11-02).

Folding only the cards saved him little scrolling: the sections they ask about
stayed full length. The section is the smallest heading block holding the
question and what it cites; a `##` whose `###` blocks all fold folds as one
line. A section with an open question stays open; a tap opens a folded one
until the page reloads; folding never moves the card he acted on, and a poll
never folds or opens anything.
"""

import json
import socket
import urllib.request

import pytest
from single_page import CHROME, ready
from test_keep_drafts import _poll, _start, _stop

from agent_annotate.pagegen import generate

playwright = pytest.importorskip("playwright.sync_api")

FILLER = "\n\n".join(f"Background paragraph {i}: what was built, what was checked and what is left." for i in range(30))
OPTIONS = [{"id": "now", "label": "Ship now"}, {"id": "later", "label": "Ship later"}]
EVIDENCE = {
    1: ["s:blocked-items:firebase-login"],
    2: ["s:blocked-items:twilio-key"],
    3: ["s:email-changes:member-flow", "s:email-changes:hq-flow"],
    4: ["s:book:book-view"],
}
BLOCKED, FIREBASE, EMAIL = "s:blocked-items", "s:blocked-items:firebase-login", "s:email-changes"


def _bar(frame, key):
    return frame.locator(f'.annotate-sfold-bar[data-sfold-key="{key}"]')


def _item(frame, n):
    return frame.locator(f'[data-strip-item="question-{n}"]')


def _directory(tmp_path):
    cards = [{"number": n, "anchor_id": f"d:q{n}", "text": f"Question {n}.", "decision_request": {
        "prompt": f"Question {n}?", "options": OPTIONS,
        "evidence": [{"anchor": a, "label": "What it asks about"} for a in anchors]}} for n, anchors in EVIDENCE.items()]
    source = tmp_path / "review.md"
    source.write_text(
        "---\ntitle: Section folds\nversion: v1\nfull_plan: true\nother_files_required: none\n---\n"
        f"\n## Opening\n\n{FILLER}\n"
        "\n## Blocked items\n\nEvery item here waits on you.\n"
        "\n### Firebase login\n\nSwitch off the leaked login.\n"
        "\n### Twilio key\n\nRevoke the old key.\n"
        "\n## Email changes\n\n### Member flow\n\nThe member picks an email.\n"
        "\n### HQ flow\n\nHQ changes it for a member.\n"
        f"\n## Middle\n\n{FILLER}\n"
        "\n## Book\n\n### Book view\n\nThe booking notice.\n"
        f"\n## Closing\n\n{FILLER}\n"
        "\n## Questions for Chang\n\n```cards\n" + json.dumps(cards) + "\n```\n")
    directory = tmp_path / "review"
    generate(source, directory)
    created = "2026-11-02T10:00:00Z"
    anchors = {}
    for card in cards:
        comment = dict(card, id=f"question-{card['number']}", author="agent:section-fold", created_at=created,
                       version="v1", status="open")
        comment["decision_request"] = dict(card["decision_request"], requested_at=created)
        anchors[card["anchor_id"]] = [comment]
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
            touch = request.param == "ipad-webkit"

            def press(loc):
                loc.tap() if touch else loc.click()
                page.wait_for_timeout(400)  # the post lands and the document is redrawn

            def load():
                if page.url.startswith(base):
                    page.reload(wait_until="networkidle")
                else:
                    page.goto(base + "#view=review", wait_until="networkidle")
                ready(page)
                frame = page.frame_locator("#content-frame")
                _item(frame, 4).wait_for(state="attached")
                return frame

            try:
                yield page, load, press, base
            finally:
                browser.close()
    finally:
        _stop(server)


def _later(press, frame, n):
    press(_item(frame, n).locator('[data-decision-action="later"][data-later="1"]'))


def _answer(press, frame, n):
    press(_item(frame, n).locator(".annotate-opt-row").first)


def test_a_section_whose_questions_are_answered_or_set_aside_folds_to_one_line(session):
    page, load, press, _ = session
    frame = load()
    _later(press, frame, 1)
    _answer(press, frame, 2)
    bar = _bar(frame, BLOCKED)
    bar.wait_for()
    box = bar.bounding_box()
    assert box and box["height"] <= 60, box
    text = bar.inner_text()
    assert "Blocked items" in text and "Answer later" in text and "Ship now" in text, text
    # The whole section goes, its heading, text and cards included; one line stands for it.
    assert frame.get_by_text("Revoke the old key.").is_hidden()
    assert frame.locator('h2:text-is("Blocked items")').is_hidden()
    assert _item(frame, 1).is_hidden() and _item(frame, 2).is_hidden()
    assert _bar(frame, FIREBASE).count() == 0  # inside the folded `##`, not a second line
    # A question citing two `###` blocks folds the `##` that holds both.
    _answer(press, frame, 3)
    _bar(frame, EMAIL).wait_for()
    assert frame.get_by_text("HQ changes it for a member.").is_hidden()
    # A load folds them the same way.
    frame = load()
    _bar(frame, BLOCKED).wait_for()
    _bar(frame, EMAIL).wait_for()
    # Folded sections in a row read as one list, not padded boxes apart.
    gap = frame.locator("body").evaluate(f"""() => {{
      const a = document.querySelector('[data-sfold-key="{BLOCKED}"]').getBoundingClientRect();
      const b = document.querySelector('[data-sfold-key="{EMAIL}"]').getBoundingClientRect();
      return b.top - a.bottom; }}""")
    assert abs(gap) <= 2, gap


def test_a_section_with_one_open_question_stays_open(session):
    page, load, press, _ = session
    frame = load()
    _later(press, frame, 1)
    # Its `###` folds; the `##` stays open, with the open question full size.
    _bar(frame, FIREBASE).wait_for()
    assert "Firebase login" in _bar(frame, FIREBASE).inner_text()
    assert frame.get_by_text("Switch off the leaked login.").is_hidden()
    assert _bar(frame, BLOCKED).count() == 0
    assert frame.get_by_text("Revoke the old key.").is_visible()
    assert _item(frame, 2).locator(".annotate-opt-row").first.is_visible()
    assert frame.locator('h2:text-is("Blocked items")').is_visible()
    # Sections without an answered question are as they were.
    assert _bar(frame, EMAIL).count() == 0 and frame.get_by_text("HQ changes it for a member.").is_visible()


def test_a_tap_opens_the_whole_section_until_the_page_reloads(session):
    page, load, press, _ = session
    frame = load()
    _later(press, frame, 1)
    _later(press, frame, 2)
    press(_bar(frame, BLOCKED).locator("button"))
    frame.get_by_text("Revoke the old key.").wait_for()
    assert _bar(frame, BLOCKED).count() == 0 and _bar(frame, FIREBASE).count() == 0
    assert frame.get_by_text("Switch off the leaked login.").is_visible()
    assert "Answer later" in _item(frame, 1).inner_text()  # its cards, each on one line
    # It stays open through his other actions and a redraw.
    _later(press, frame, 4)
    page.evaluate("() => window.AnnotateDocs.reload()")
    page.wait_for_timeout(500)
    assert _bar(frame, BLOCKED).count() == 0
    # Back to Needs you opens it for good: the question is open again.
    press(_item(frame, 2).locator(".annotate-folded-row"))
    press(_item(frame, 2).locator('[data-decision-action="later"][data-later="0"]'))
    frame = load()
    _bar(frame, FIREBASE).wait_for()  # a reload folds what he opened
    assert _bar(frame, BLOCKED).count() == 0
    assert _item(frame, 2).locator(".annotate-opt-row").first.is_visible()


def test_folding_keeps_the_card_he_acted_on_in_place(session):
    page, load, press, _ = session
    frame = load()
    item = _item(frame, 3)
    item.evaluate("el => scrollTo(0, el.getBoundingClientRect().top + scrollY - 300)")
    page.wait_for_timeout(300)
    before = item.evaluate("el => el.getBoundingClientRect().top")
    assert frame.locator("body").evaluate("() => scrollY") > 300
    _answer(press, frame, 3)
    bar = _bar(frame, EMAIL)
    bar.wait_for()
    # The section's line takes the card's place on screen.
    assert abs(bar.evaluate("el => el.getBoundingClientRect().top") - before) <= 2
    # A section folding above the screen (set aside from the rail) moves nothing on it.
    page.evaluate("() => window.AA.rail.reveal()")
    book = _item(frame, 4)
    book.evaluate("el => scrollTo(0, el.getBoundingClientRect().top + scrollY - 300)")
    page.wait_for_timeout(500)
    before = book.evaluate("el => el.getBoundingClientRect().top")
    for n in (1, 2):
        page.locator(f'#comment-list [data-decision-action="later"][data-later="1"][data-id="question-{n}"]').evaluate("el => el.click()")
        page.wait_for_timeout(500)
    _bar(frame, BLOCKED).wait_for(state="attached")
    assert abs(book.evaluate("el => el.getBoundingClientRect().top") - before) <= 2


def test_a_poll_never_folds_or_opens_a_section(session):
    page, load, press, base = session
    frame = load()
    _later(press, frame, 1)
    _bar(frame, FIREBASE).wait_for()
    # The last open question there is set aside elsewhere; the poll brings it.
    request = urllib.request.Request(base + "api/comments/question-2/answer-later", data=b'{"on": true}', method="POST",
                                     headers={"Content-Type": "application/json"})
    urllib.request.urlopen(request, timeout=5).close()
    # A section he opened stays open through a poll, too.
    press(_bar(frame, FIREBASE).locator("button"))
    _poll(page, 2)
    page.wait_for_timeout(500)
    assert _bar(frame, BLOCKED).count() == 0 and _bar(frame, FIREBASE).count() == 0
    assert _item(frame, 2).locator(".annotate-opt-row").first.is_visible()
    # A load shows it.
    frame = load()
    _bar(frame, BLOCKED).wait_for()
