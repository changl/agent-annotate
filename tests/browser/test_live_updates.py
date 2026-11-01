"""The page never changes under the reviewer (agent-annotate-dw4).

Chang (2026-11-01): "i don't want things constantly shifting and updating while
i'm trying to answer a question or type in feedback. the page should only
refresh when i press refresh or select a new version that's available. if there
is a new version that becomes available while i'm typing, then it should give
me a notification at the top where it states back to latest."

The reviewer types in a question's box. The agent publishes v2, which withdraws
that question, and asks a new one. Polls must leave the cards, the document,
the typed text and the scroll alone, and say in the banner at the top what is
waiting. A tap on the banner shows it all: the new question, and the typed
text still on its (now withdrawn) card. Desktop Chrome and iPad (Playwright
WebKit, the engine of iPad Chrome), and an iPad tab brought back from the
background.

A confirmed post (agent-annotate-kbv) puts the server's answer in place with
one render, instead of rereading the whole store and rendering three times.
"""

import socket
from contextlib import contextmanager

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from single_page import CHROME  # noqa: E402
from test_keep_drafts import _agent, _directory, _loaded, _poll, _publish_v2, _start, _stop  # noqa: E402

TYPED = "Half a thought about the release"
MORE = ", and the rest of it"


@contextmanager
def _open(tmp_path, directory, engine):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = _start(tmp_path, directory, port)
    base = f"http://127.0.0.1:{port}/"
    try:
        with playwright.sync_playwright() as runner:
            if engine == "ipad":
                try:
                    browser = runner.webkit.launch()
                except Exception:
                    pytest.skip("Playwright WebKit is not installed")
                context = browser.new_context(**runner.devices["iPad Pro 11 landscape"])
            else:
                if not CHROME.exists():
                    pytest.skip("Google Chrome is not installed")
                browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
                context = browser.new_context(viewport={"width": 1440, "height": 960})
            page = context.new_page()
            page.set_default_timeout(10000)
            page.goto(base + "#view=review", wait_until="networkidle")
            _loaded(page)
            yield page, base
            browser.close()
    finally:
        _stop(server)


def _agent_moves_on(tmp_path, directory, base):
    """v2 goes live, withdraws question 11, and asks question 12 on v2."""
    _publish_v2(tmp_path, directory)
    _agent(base, "api/comments/question-11", {"decision_request": None, "withdraw_reason": "replaced by #12"}, method="PUT")
    _agent(base, "api/comments/batch", {"items": [{
        "anchor_id": "s:checks", "text": "Question 12", "version": "v2",
        "decision_request": {"prompt": "New question 12?", "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]},
    }]})


def _screen(page):
    return page.evaluate("""() => {
        const frame = document.getElementById('content-frame');
        const doc = frame.contentDocument;
        return {
            rail: document.getElementById('comment-list').innerHTML,
            railScroll: document.getElementById('drawer-body').scrollTop,
            version: frame.dataset.version,
            strips: [...doc.querySelectorAll('[data-annotate-strip]')].map(s => s.textContent),
            docScroll: doc.defaultView.scrollY,
        };
    }""")


def _box(page, where):
    return (page.locator('#comment-list [data-decision-say-ta="question-11"]') if where == "rail"
            else page.frame_locator("#content-frame").locator('textarea[data-strip-say="question-11"]'))


@pytest.mark.parametrize("engine", ["chrome", "ipad"])
@pytest.mark.parametrize("where", ["rail", "document"])
def test_a_new_version_waits_in_the_banner_while_the_reviewer_types(tmp_path, engine, where):
    directory = _directory(tmp_path)
    with _open(tmp_path, directory, engine) as (page, base):
        box = _box(page, where)
        box.click()
        page.keyboard.type(TYPED)
        page.wait_for_timeout(300)
        before = _screen(page)
        _agent_moves_on(tmp_path, directory, base)
        _poll(page, 2)
        page.keyboard.type(MORE)
        _poll(page)
        assert _screen(page) == before
        assert box.input_value() == TYPED + MORE
        assert box.evaluate("el => el === el.ownerDocument.activeElement")
        banner = page.locator("#unified-version-banner")
        assert banner.is_visible()
        assert "Latest is v2 · 1 new question · 1 card changed" in banner.inner_text()

        banner.locator("button").click()
        page.wait_for_function("() => document.getElementById('content-frame').dataset.version === 'v2'")
        page.locator("#comment-list", has_text="New question 12?").wait_for()
        assert banner.is_hidden()
        shown = page.evaluate("() => [...document.querySelectorAll('#comment-list textarea')].map(t => t.value)")
        assert TYPED + MORE in shown


def test_a_question_asked_on_the_version_on_screen_waits_too(tmp_path):
    directory = _directory(tmp_path)
    with _open(tmp_path, directory, "chrome") as (page, base):
        before = _screen(page)
        _agent(base, "api/comments/batch", {"items": [{
            "anchor_id": "s:checks", "text": "Question 12", "version": "v1",
            "decision_request": {"prompt": "New question 12?", "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]},
        }]})
        _poll(page)
        assert _screen(page) == before
        banner = page.locator("#unified-version-banner")
        assert banner.inner_text().startswith("1 new question — show")
        banner.locator("button").click()
        page.locator("#comment-list", has_text="New question 12?").wait_for()
        page.frame_locator("#content-frame").locator("[data-annotate-strip]", has_text="New question 12?").wait_for()
        assert banner.is_hidden()


def test_a_backgrounded_ipad_tab_comes_back_to_the_same_page_and_the_banner(tmp_path):
    directory = _directory(tmp_path)
    with _open(tmp_path, directory, "ipad") as (page, base):
        hide = """hidden => {
            Object.defineProperty(document, 'hidden', {configurable: true, get: () => hidden});
            Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => hidden ? 'hidden' : 'visible'});
            document.dispatchEvent(new Event('visibilitychange'));
        }"""
        _box(page, "rail").fill(TYPED)
        before = _screen(page)
        page.evaluate(hide, True)
        _agent_moves_on(tmp_path, directory, base)
        page.wait_for_timeout(9000)  # a hidden page makes no requests
        page.evaluate(hide, False)
        page.locator("#unified-version-banner", has_text="Latest is v2").wait_for()
        assert _screen(page) == before
        assert _box(page, "rail").input_value() == TYPED


WATCH = """() => {
    window.__stats = { storeReads: 0, railRenders: 0, frameRenders: 0 };
    const real = window.__realFetch || (window.__realFetch = window.fetch);
    window.fetch = (url, opts) => {
        if (String(url).includes('comments.json')) window.__stats.storeReads++;
        const post = opts && opts.method === 'POST' && /api\\/comments(\\/[^/?]+\\/reply)?(\\?|$)/.test(String(url));
        return real(url, opts).then(r => post ? new Promise(res => setTimeout(() => {
            window.__stats = { storeReads: 0, railRenders: 0, frameRenders: 0, answered: true }; res(r); }, 600)) : r);
    };
    new MutationObserver(ms => { window.__stats.railRenders += ms.filter(m => m.target.id === 'comment-list').length; })
        .observe(document.getElementById('comment-list'), { childList: true });
    document.getElementById('content-frame').contentWindow.addEventListener('message', e => {
        if (e.data && e.data.type === 'annotate:comment-counts') window.__stats.frameRenders++;
    });
}"""


@pytest.mark.parametrize("kind", ["comment", "reply"])
def test_a_confirmed_post_renders_once_without_rereading_the_store(tmp_path, kind):
    directory = _directory(tmp_path)
    with _open(tmp_path, directory, "chrome") as (page, base):
        page.evaluate(WATCH)
        if kind == "comment":
            page.frame_locator("#content-frame").locator('[data-anchor-id="s:checks"] h2').click(position={"x": 10, "y": 5})
            page.locator("#pop-ta").fill("A new note")
            page.locator("#pop-save").click()
            settled = "#comment-list .citem.is-pending"
        else:
            page.locator('#comment-list [data-reply-for="reply-card"]').fill("A reply")
            page.locator('[data-action="reply"][data-id="reply-card"]').click()
            settled = "#comment-list .thread-reply.is-pending"
        page.wait_for_function("() => window.__stats.answered")
        page.wait_for_function(f"() => !document.querySelector('{settled}')")
        page.wait_for_timeout(500)
        stats = page.evaluate("() => window.__stats")
        assert stats["storeReads"] == 0, stats
        assert stats["railRenders"] == 1 and stats["frameRenders"] == 1, stats
        # What a refresh brings is what is on screen.
        page.evaluate("() => window.AnnotateDocs.reload()")
        page.wait_for_timeout(300)
        shown = page.locator("#comment-list .citem" if kind == "comment" else "#comment-list .thread-reply",
                             has_text="A new note" if kind == "comment" else "A reply")
        assert shown.count() == 1
        assert page.locator("#unified-version-banner").is_hidden()
