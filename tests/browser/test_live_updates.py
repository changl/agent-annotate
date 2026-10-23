"""dw4: an open page shows what the agent asks without a reload, and a post is
ready to send at once, on a page the size of FLD's.

Chang had to reload to see new feedback requests: the page stayed on the
version it opened with, a box that kept focus held every render back, and an
idle page polled every 30 s. And a post took seconds to settle: each one read
the whole store again and drew the whole page (History alone walked every
comment once per version). The page here has 1,100 comments over 160
versions. Polls run on Playwright's clock, so two idle minutes take seconds.
"""

import json
import socket
from contextlib import contextmanager

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from single_page import CHROME, feedback, ready  # noqa: E402
from test_keep_drafts import _agent, _start, _stop  # noqa: E402
from test_workspace_intent import _page  # noqa: E402

from agent_annotate.pagegen import generate  # noqa: E402

pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")

VERSIONS = 160
COMMENTS = 1100
STATUSES = ["resolved_in_version", "open", "addressed_by_agent", "user_confirmed"]


def _publish(tmp_path, directory, version):
    source = tmp_path / "review.md"
    text = source.read_text()
    old = text.split("\nversion: ", 1)[1].split("\n", 1)[0]
    text = text.replace("\nversion: " + old + "\n", "\nversion: " + version + "\n", 1)
    # Each version says something new, so its sections are not folded away.
    source.write_text(text.replace("Build passed on both machines", "Build passed on both machines in " + version, 1)
                      if "machines in" not in text else text.replace("machines in " + old, "machines in " + version, 1))
    generate(source, directory)
    from agent_annotate.cli import _write_meta_locked

    def live(meta):
        meta["current"] = version
        meta.setdefault("history", []).append({"version": version, "ts": "2026-10-20T10:00:00Z", "label": version})

    (directory / "current.html").unlink()
    (directory / "current.html").symlink_to(f"versions/{version}.html")
    _write_meta_locked(directory, live)


def _large(tmp_path):
    directory = _page(tmp_path)
    store = json.loads((directory / "comments.json").read_text())
    _publish(tmp_path, directory, f"v{VERSIONS}")
    meta = json.loads((directory / "current.meta.json").read_text())
    meta["history"] = [{"version": f"v{i}", "ts": f"2026-10-{1 + i // 24:02d}T{i % 24:02d}:00:00Z", "label": f"Round {i}"}
                       for i in range(1, VERSIONS + 1)]
    (directory / "current.meta.json").write_text(json.dumps(meta))
    for i in range(COMMENTS):
        anchor = "s:checks:p1" if i % 2 else "s:checks"
        agent = i % 3 == 0
        created = f"2026-10-0{1 + i % 6}T{i % 24:02d}:{i % 60:02d}:00Z"
        store["anchors"].setdefault(anchor, []).append({
            "id": f"c{i}", "anchor_id": anchor, "text": f"Old note {i} on the build.", "version": f"v{1 + i % VERSIONS}",
            "status": STATUSES[i % 4], "author": "agent:fld" if agent else "reviewer@example.com", "created_at": created,
            "flagged_for_session": True, "flagged_at": "2026-10-09T00:00:00Z",
            "response_text": None if agent else "Handled.", "replies": [],
            **({"resolved_in_version": f"v{2 + i % (VERSIONS - 1)}"} if i % 4 == 0 else {}),
        })
    (directory / "comments.json").write_text(json.dumps(store))
    return directory


@contextmanager
def _session(tmp_path, directory, clock=False):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = _start(tmp_path, directory, port)
    base = f"http://127.0.0.1:{port}/"
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.set_default_timeout(15000)
            reads = []
            page.on("request", lambda r: reads.append(r.url.replace(base, "/").split("?")[0]) if r.method == "GET" else None)
            if clock:
                page.clock.install()
            page.goto(base + "#view=review", wait_until="commit")
            if clock:
                # Page timers only run as the clock is moved on.
                assert _advance(page, 30, step=0.25, until=LOADED) is not None
                page.evaluate("() => window.AA.rail.reveal()")
                _advance(page, 1, step=0.25)
            else:
                ready(page)
                feedback(page)
                page.frame_locator("#content-frame").locator('[data-anchor-id="s:checks"]').wait_for(state="attached")
            yield page, base, reads
            browser.close()
    finally:
        _stop(server)


LOADED = """() => document.body.dataset.ready === '1' && !!document.querySelector('#comment-list .citem') &&
  !!document.getElementById('content-frame').contentDocument?.querySelector('[data-anchor-id="s:checks"]')"""


def _advance(page, seconds, step=1.0, until=None):
    """Page time moves on `seconds` in steps (each with a real pause for the
    poll's requests); returns the page seconds it took `until` to hold."""
    t = 0.0
    while t < seconds:
        page.clock.run_for(int(step * 1000))
        page.wait_for_timeout(40)
        t += step
        if until and page.evaluate(until):
            return t
    return None


def _card(number, version, text):
    return {"anchor_id": f"d:q{number}", "text": text, "version": version, "number": number,
            "decision_request": {"prompt": text, "context": "Asked by the agent.", "recommendation": "yes",
                                 "options": [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}],
                                 "evidence": [{"anchor": "s:checks:p1", "label": "Build result"}]}}


def _shows(text):
    return f"() => [...document.querySelectorAll('#comment-list .sec-needs .citem')].some(n => n.textContent.includes({json.dumps(text)}))"


FRAME_VERSION = "() => document.getElementById('content-frame').dataset.version"


def test_agent_requests_reach_an_idle_page_within_one_poll_with_and_without_a_draft(tmp_path):
    directory = _large(tmp_path)
    with _session(tmp_path, directory, clock=True) as (page, base, reads):
        # Two idle minutes: the reads other than the store and the version
        # list have backed off, those two still go every 8 s.
        _advance(page, 130, step=2)
        reads.clear()
        _advance(page, 32, step=2)
        assert reads.count("/comments.json") >= 4 and reads.count("/current.meta.json") >= 4, reads
        assert reads.count("/api/read-state") <= 2, reads

        # A card on the version on screen, nothing open.
        _agent(base, "api/comments/batch", {"items": [_card(12, f"v{VERSIONS}", "Ship the idle-page build?")]})
        took = _advance(page, 12, step=0.5, until=_shows("Ship the idle-page build?"))
        assert took is not None and took <= 8.5, took
        assert page.evaluate("() => Number(document.getElementById('tab-feedback-n').textContent)") >= 2

        # A box keeps focus (no typing): new cards still show; text, focus kept.
        say = page.locator('#comment-list [data-decision-say-ta="question-11"]')
        say.fill("Half an answer")
        say.focus()
        _advance(page, 3, step=1)
        _agent(base, "api/comments/batch", {"items": [_card(13, f"v{VERSIONS}", "Keep the focused box?")]})
        took = _advance(page, 12, step=0.5, until=_shows("Keep the focused box?"))
        assert took is not None and took <= 8.5, took
        assert say.input_value() == "Half an answer"
        assert page.evaluate("() => document.activeElement && document.activeElement.dataset.decisionSayTa") == "question-11"
        page.evaluate("() => document.activeElement.blur()")

        # A new version with a card, nothing open: the page moves to it.
        new = f"v{VERSIONS + 1}"
        _publish(tmp_path, directory, new)
        _agent(base, "api/comments/batch", {"items": [_card(14, new, "Approve the new layout?")]})
        took = _advance(page, 12, step=0.5, until=f"() => ({FRAME_VERSION})() === {json.dumps(new)}")
        assert took is not None and took <= 8.5, took
        _advance(page, 2, step=0.5)
        assert page.evaluate(_shows("Approve the new layout?"))
        assert page.locator("#unified-version-banner").is_hidden()

        # With the composer open: the card shows, the page stays, the banner
        # offers the new version and the text is kept; once it is posted the
        # next poll moves on.
        frame = page.frame_locator("#content-frame")
        frame.locator('[data-anchor-id="s:checks"] h2').click(position={"x": 10, "y": 5})
        _advance(page, 1, step=0.25)
        page.locator("#popover.vis").wait_for()
        page.locator("#pop-ta").fill("A note typed while the agent publishes")
        newer = f"v{VERSIONS + 2}"
        _publish(tmp_path, directory, newer)
        _agent(base, "api/comments/batch", {"items": [_card(15, newer, "And the newer one?")]})
        took = _advance(page, 12, step=0.5, until=_shows("And the newer one?"))
        assert took is not None and took <= 8.5, took
        assert page.evaluate(FRAME_VERSION) == new
        banner = page.locator("#unified-version-banner")
        playwright.expect(banner).to_contain_text(f"Latest is {newer}, new from the agent")
        playwright.expect(banner).to_contain_text("your draft stays")
        assert page.locator("#pop-ta").input_value() == "A note typed while the agent publishes"
        page.locator("#pop-save").click()
        assert _advance(page, 5, step=0.25, until="() => window.AnnotateDocs.comments().some(c => c.text === 'A note typed while the agent publishes' && !c.pending)") is not None
        took = _advance(page, 12, step=0.5, until=f"() => ({FRAME_VERSION})() === {json.dumps(newer)}")
        assert took is not None and took <= 8.5, took


def test_typing_holds_a_render_only_until_the_reviewer_pauses(tmp_path):
    directory = _large(tmp_path)
    with _session(tmp_path, directory, clock=True) as (page, base, reads):
        say = page.locator('#comment-list [data-decision-say-ta="question-11"]')
        say.click()
        _agent(base, "api/comments/batch", {"items": [_card(12, f"v{VERSIONS}", "Seen after typing stops?")]})
        # Typing straight through two polls: nothing is redrawn under the keys.
        for ch in "Typing through two polls":
            say.press(ch if ch != " " else "Space")
            _advance(page, 0.75, step=0.75)
        assert not page.evaluate(_shows("Seen after typing stops?"))
        took = _advance(page, 4, step=0.25, until=_shows("Seen after typing stops?"))
        assert took is not None and took <= 2.5, took
        assert say.input_value() == "Typing through two polls"


# From an action to Send counting it (enabled, at the expected count), in ms;
# right after the action's own instant redraw, another card's node is marked,
# so a later full redraw of the rail shows as a fresh, unmarked node.
TIMED = """([act, want, other]) => new Promise(done => {
  const t0 = performance.now(); let counted = null;
  (new Function('return ' + act))()();
  document.querySelector('#comment-list .citem[data-comment-id="' + other + '"]').__dw4 = 1;
  const look = () => {
    if (counted == null && Number(document.getElementById('send-count').textContent) === want && !document.getElementById('send-btn').disabled) counted = performance.now() - t0;
    if (counted != null && !/Sending…/.test(document.getElementById('comment-list').textContent)) return done(counted);
    if (performance.now() - t0 > 10000) return done(null);
    requestAnimationFrame(look);
  };
  look();
})"""
SAME = """id => !!(document.querySelector('#comment-list .citem[data-comment-id="' + id + '"]') || {}).__dw4"""


def test_a_post_is_ready_to_send_at_once_and_settles_without_a_full_render(tmp_path):
    directory = _large(tmp_path)
    with _session(tmp_path, directory) as (page, base, reads):
        send = lambda: int(page.locator("#send-count").inner_text())  # noqa: E731
        frame = page.frame_locator("#content-frame")
        # A document comment.
        frame.locator('[data-anchor-id="s:checks"] h2').click(position={"x": 10, "y": 5})
        page.locator("#popover.vis").wait_for()
        page.locator("#pop-ta").fill("Ready to send at once")
        reads.clear()
        counted = page.evaluate(TIMED, ["() => document.getElementById('pop-save').click()", send() + 1, "question-11"])
        assert counted is not None and counted < 100, counted
        page.wait_for_timeout(500)
        assert "/comments.json" not in reads, reads
        assert page.evaluate(SAME, "question-11"), "the rail was drawn again on confirmation"
        card = page.locator("#comment-list .citem", has_text="Ready to send at once")
        assert card.count() == 1 and "Sending…" not in card.inner_text()
        cid = page.evaluate("() => window.AnnotateDocs.comments().find(c => c.text === 'Ready to send at once').id")
        assert card.get_attribute("data-comment-id") == cid

        # A reply under the agent's answer.
        _agent(base, f"api/comments/{cid}", {"response_text": "Seen, thanks."}, method="PUT")
        page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        box = page.locator(f'#comment-list [data-reply-for="{cid}"]')
        box.wait_for()
        box.fill("One more thing")
        reads.clear()
        counted = page.evaluate(TIMED, ['() => document.querySelector(`#comment-list [data-action="reply"][data-id="%s"]`).click()' % cid, send(), "question-11"])
        assert counted is not None and counted < 100, counted
        page.wait_for_timeout(500)
        assert "/comments.json" not in reads, reads
        assert page.evaluate(SAME, "question-11"), "the rail was drawn again on confirmation"
        playwright.expect(page.locator("#comment-list .citem", has_text="One more thing")).not_to_contain_text("Sending…")

        # A verdict: counted at once, then settled in place.
        reads.clear()
        counted = page.evaluate(TIMED, ['() => document.querySelector(`#comment-list .decision-btn[data-id="question-11"]`).click()', send() + 1, cid])
        assert counted is not None and counted < 100, counted
        page.wait_for_timeout(500)
        assert "/comments.json" not in reads, reads
        assert page.evaluate(SAME, cid), "the rail was drawn again on confirmation"
        decision = page.evaluate("() => window.AnnotateDocs.comments().find(c => c.id === 'question-11').decision")
        assert decision and decision.get("verdict") and not decision.get("pending")
