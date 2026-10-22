"""v9o: typed text is never lost, and posting feels instant.

Chang lost comments while typing: the page re-rendered or switched under a
half-typed box. Each composer here is typed in, left (blurred), then the page
goes through what happens around a reviewer: polls, the agent answering and
resolving, a new version, a server restart and a reload. The text must still
be there after each one, and only a successful post clears it.
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import contextmanager

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from single_page import CHROME, feedback, ready  # noqa: E402
from test_workspace_intent import _page  # noqa: E402

from agent_annotate.pagegen import generate  # noqa: E402

pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")

REPLY = "Reply typed while the agent was still working"
SAY = "Comment on the release choice, not sent yet"
GF = "General feedback typed before a new version"
POP = "A note on the build result, half written"


def _start(tmp_path, directory, port):
    env = os.environ.copy()
    env["ANNOTATE_STATE_DIR"] = str(tmp_path / "state")
    process = subprocess.Popen(
        [sys.executable, "-m", "agent_annotate.sync_server", "--slug-dir", str(directory), "--slug", "items-model",
         "--bus-dir", str(tmp_path / "bus"), "--port", str(port), "--strict-port",
         "--local-author", "reviewer@example.com", "--local-author-name", "Browser Reviewer"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}/"
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            urllib.request.urlopen(base, timeout=1).close()
            return process
        except OSError:
            if process.poll() is not None:
                break
            time.sleep(0.05)
    process.kill()
    raise AssertionError(f"sync server did not come up on port {port}")


def _stop(process):
    process.terminate()
    process.wait(timeout=5)


def _agent(base, path, body, method="POST"):
    request = urllib.request.Request(base + path, data=json.dumps(body).encode(), method=method,
                                     headers={"Content-Type": "application/json", "X-Annotate-Agent": "agent:keep-drafts"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def _directory(tmp_path):
    directory = _page(tmp_path)
    path = directory / "comments.json"
    store = json.loads(path.read_text())
    store["anchors"]["s:checks:p1"] = [{
        "id": "reply-card", "anchor_id": "s:checks:p1", "anchor_label": "Build result", "text": "Did both builds pass?",
        "author": "reviewer@example.com", "created_at": "2026-10-02T10:01:00Z", "version": "v1", "status": "open",
        "flagged_for_session": True, "flagged_at": "2026-10-02T10:02:00Z",
        "response_text": "Yes, on both machines.", "replies": [],
    }]
    path.write_text(json.dumps(store))
    return directory


@contextmanager
def _session(tmp_path, directory):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = [_start(tmp_path, directory, port)]
    base = f"http://127.0.0.1:{port}/"
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.set_default_timeout(8000)
            page.goto(base + "#view=review", wait_until="networkidle")
            _loaded(page)

            def restart():
                _stop(server[0])
                server[0] = _start(tmp_path, directory, port)

            yield page, base, restart
            browser.close()
    finally:
        _stop(server[0])


def _loaded(page):
    ready(page)
    feedback(page)
    page.frame_locator("#content-frame").locator('[data-anchor-id="s:checks"]').wait_for(state="attached")


def _poll(page, times=1):
    # A return to the tab polls at once (the same refresh the 8 s timer runs).
    for _ in range(times):
        page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        page.wait_for_timeout(400)


def _blur(page):
    page.wait_for_timeout(300)  # the document's own click handling settles first
    page.evaluate("() => { document.activeElement && document.activeElement.blur(); }")
    page.frame_locator("#content-frame").locator("body").evaluate("() => document.activeElement && document.activeElement.blur()")


def _publish_v2(tmp_path, directory):
    source = tmp_path / "review.md"
    source.write_text(source.read_text().replace("version: v1", "version: v2")
                      .replace("Build passed on both machines.", "Build passed on both machines, twice."))
    generate(source, directory)
    # generate() writes a later version without making it current; going live
    # is the publish step, done here the way the CLI does it.
    from agent_annotate.cli import _write_meta_locked

    def live(meta):
        meta["current"] = "v2"
        meta.setdefault("history", []).append({"version": "v2", "ts": "2026-10-03T10:00:00Z", "label": "v2"})

    (directory / "current.html").unlink()
    (directory / "current.html").symlink_to("versions/v2.html")
    _write_meta_locked(directory, live)


def _say(page):
    return page.locator('#comment-list [data-decision-say-ta="question-11"]')


def _reply(page):
    return page.locator('#comment-list [data-reply-for="reply-card"]')


def _rail_texts(page):
    # Every composer's text as the page holds it (box value, or its draft when
    # the box is not on screen).
    return page.evaluate("""() => ({
        say: document.querySelector('#comment-list [data-decision-say-ta="question-11"]')?.value ?? null,
        reply: document.querySelector('#comment-list [data-reply-for="reply-card"]')?.value ?? null,
        gf: document.getElementById('gf-ta').value,
        pop: document.getElementById('popover').classList.contains('vis') ? document.getElementById('pop-ta').value : null,
    })""")


def _expect_all(page, step):
    page.wait_for_function("() => document.querySelector('#comment-list [data-reply-for=\"reply-card\"]')")
    texts = _rail_texts(page)
    assert texts == {"say": SAY, "reply": REPLY, "gf": GF, "pop": POP}, step


def test_rail_composers_keep_text_through_polls_changes_versions_restarts_and_reloads(tmp_path):
    directory = _directory(tmp_path)
    with _session(tmp_path, directory) as (page, base, restart):
        frame = page.frame_locator("#content-frame")
        _say(page).fill(SAY)
        _reply(page).fill(REPLY)
        page.locator("#general-feedback-toggle").click()
        page.locator("#gf-ta").fill(GF)
        frame.locator('[data-anchor-id="s:checks"] h2').click(position={"x": 10, "y": 5})
        page.locator("#popover.vis").wait_for()
        page.locator("#pop-ta").fill(POP)
        # A second click in the document (to look at something) used to open
        # an empty composer in place of the typed one.
        frame.locator('[data-anchor-id="s:checks:p1"]').first.click(position={"x": 10, "y": 5})
        assert page.locator("#pop-ta").input_value() == POP
        _blur(page)
        _expect_all(page, "after blur")

        _poll(page, 3)
        _expect_all(page, "after three polls")

        before = page.evaluate("() => window.AnnotateDocs.comments().length")
        _agent(base, "api/comments/batch", {"items": [{"anchor_id": "s:checks", "text": "Another note from the agent.", "version": "v1"}]})
        _agent(base, "api/comments/reply-card", {"status": "addressed_by_agent", "response_text": "Fixed in the next build."}, method="PUT")
        _poll(page)
        page.wait_for_function("n => window.AnnotateDocs.comments().length > n", arg=before)
        page.wait_for_timeout(300)
        _expect_all(page, "after the agent commented and resolved the card")

        _publish_v2(tmp_path, directory)
        _poll(page)
        page.locator("#unified-version-banner").wait_for(state="visible")
        assert page.locator("#content-frame").get_attribute("data-version") == "v1"
        _expect_all(page, "after a new version")

        restart()
        _poll(page)
        _expect_all(page, "after a server restart")

        page.reload(wait_until="networkidle")
        _loaded(page)
        page.locator("#popover.vis").wait_for()
        _expect_all(page, "after a reload")

        # Posting clears each one, and only then.
        _reply(page).locator("xpath=following-sibling::button").click()
        page.wait_for_function("() => !document.querySelector('#comment-list .thread-reply.is-pending')")
        page.locator("#pop-save").click()
        page.locator("#popover.vis").wait_for(state="hidden")
        page.wait_for_function("t => window.AnnotateDocs.comments().some(c => c.text === t && !c.pending)", arg=POP)
        page.reload(wait_until="networkidle")
        _loaded(page)
        texts = _rail_texts(page)
        assert texts["reply"] in ("", None) and texts["pop"] is None
        assert texts["say"] == SAY and texts["gf"] == GF  # these go with Send
    store = json.loads((directory / "comments.json").read_text())
    assert [r["text"] for r in store["anchors"]["s:checks:p1"][0]["replies"]][-1] == REPLY
    assert any(c["text"] == POP and c["version"] == "v1" for c in store["anchors"]["s:checks"])


def test_body_strip_comment_keeps_text_and_answer_clears_it(tmp_path):
    directory = _directory(tmp_path)
    with _session(tmp_path, directory) as (page, base, restart):
        frame = page.frame_locator("#content-frame")
        strip = frame.locator('textarea[data-strip-say="question-11"]')
        strip.fill(SAY)
        _blur(page)
        for step, act in [("three polls", lambda: _poll(page, 3)),
                          ("an agent comment", lambda: (_agent(base, "api/comments/batch", {"items": [{"anchor_id": "s:checks", "text": "Agent note.", "version": "v1"}]}), _poll(page))),
                          ("a new version", lambda: (_publish_v2(tmp_path, directory), _poll(page))),
                          ("a restart", lambda: (restart(), _poll(page)))]:
            act()
            assert strip.input_value() == SAY, step
            assert _say(page).input_value() == SAY, step
        page.reload(wait_until="networkidle")
        _loaded(page)
        strip = page.frame_locator("#content-frame").locator('textarea[data-strip-say="question-11"]')
        assert strip.input_value() == SAY, "after a reload"
        page.frame_locator("#content-frame").locator('[data-strip-item="question-11"] .annotate-decision-btns button').first.click()
        for _ in range(50):
            decision = json.loads((directory / "comments.json").read_text())["anchors"]["d:q11"][0].get("decision") or {}
            if SAY in (decision.get("text") or ""):
                break
            page.wait_for_timeout(100)
        assert SAY in (decision.get("text") or "")
        page.wait_for_function("() => !document.querySelector('#comment-list [data-decision-say-ta=\"question-11\"]')?.value")
        page.reload(wait_until="networkidle")
        _loaded(page)
        assert page.evaluate("() => Object.keys(JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k => k.startsWith('annotate:drafts:'))) || '{}'))") == []


def test_posts_show_at_once_and_a_failed_post_gives_the_text_back(tmp_path):
    directory = _directory(tmp_path)
    with _session(tmp_path, directory) as (page, base, restart):
        frame = page.frame_locator("#content-frame")
        frame.locator('[data-anchor-id="s:checks"] h2').click(position={"x": 10, "y": 5})
        page.locator("#pop-ta").fill(POP)
        # Time from the click to the card in the rail, before the server answers.
        shown_ms = page.evaluate("""() => new Promise(done => {
            const t0 = performance.now();
            document.getElementById('pop-save').click();
            const look = () => document.querySelector('#comment-list .citem.is-pending') ? done(performance.now() - t0) : requestAnimationFrame(look);
            look();
        })""")
        print(f"optimistic comment shown after {shown_ms:.1f} ms")
        assert shown_ms < 100
        page.wait_for_function("() => !document.querySelector('#comment-list .citem.is-pending')")

        page.route("**/api/comments/reply-card/reply*", lambda route: route.abort())
        _reply(page).fill(REPLY)
        reply_ms = page.evaluate("""() => new Promise(done => {
            const t0 = performance.now();
            document.querySelector('[data-action="reply"][data-id="reply-card"]').click();
            const look = () => document.querySelector('#comment-list .thread-reply.is-pending') ? done(performance.now() - t0) : requestAnimationFrame(look);
            look();
        })""")
        print(f"optimistic reply shown after {reply_ms:.1f} ms")
        assert reply_ms < 100
        page.wait_for_function("() => !document.querySelector('#comment-list .thread-reply.is-pending')")
        assert _reply(page).input_value() == REPLY
        assert "Reply not sent" in page.locator('#comment-list [data-comment-id="reply-card"]').inner_text()

        page.route("**/api/comments?*", lambda route: route.abort() if route.request.method == "POST" else route.continue_())
        frame.locator('[data-anchor-id="s:checks:p1"]').first.click(position={"x": 10, "y": 5})
        page.locator("#pop-ta").fill(POP + " again")
        page.locator("#pop-save").click()
        page.locator("#pop-err").wait_for(state="visible")
        assert page.locator("#popover.vis").count() == 1
        assert page.locator("#pop-ta").input_value() == POP + " again"
        assert page.locator("#comment-list .citem.is-pending").count() == 0
