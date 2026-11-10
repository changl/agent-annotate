"""The page never changes under the reviewer (agent-annotate-dw4).

Chang (2026-11-01): "i don't want things constantly shifting and updating while
i'm trying to answer a question or type in feedback. the page should only
refresh when i press refresh or select a new version that's available. if there
is a new version that becomes available while i'm typing, then it should give
me a notification at the top where it states back to latest."

The reviewer types in a question's box. The agent publishes v2, which withdraws
that question, and asks a new one. Polls must leave the cards, the document,
the typed text and the scroll alone, and say on the header's refresh button
what is waiting (av1, #136). A tap on it shows it all: the new question, and
the typed text still on its (now withdrawn) card. Desktop Chrome and iPad (Playwright
WebKit, the engine of iPad Chrome), and an iPad tab brought back from the
background.

A confirmed post (agent-annotate-kbv) puts the server's answer in place with
one render, instead of rereading the whole store and rendering three times.
"""

import re
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
def test_a_new_version_waits_on_the_refresh_button_while_the_reviewer_types(tmp_path, engine, where):
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
        fresh = page.locator("#aa-fresh")
        assert fresh.get_attribute("aria-label") == "Latest is v2 · 1 new item. Tap to show."
        assert fresh.inner_text().split() == ["1", "v2"]

        fresh.click()
        page.wait_for_function("() => document.getElementById('content-frame').dataset.version === 'v2'")
        page.locator("#comment-list", has_text="New question 12?").wait_for()
        page.wait_for_function("() => document.getElementById('aa-fresh').dataset.state === 'idle'")
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
        fresh = page.locator("#aa-fresh")
        assert fresh.get_attribute("aria-label") == "1 new item. Tap to show."
        fresh.click()
        page.locator("#comment-list", has_text="New question 12?").wait_for()
        page.frame_locator("#content-frame").locator("[data-annotate-strip]", has_text="New question 12?").wait_for()
        page.wait_for_function("() => document.getElementById('aa-fresh').dataset.state === 'idle'")


def test_a_backgrounded_ipad_tab_comes_back_to_the_same_page_and_the_refresh_button(tmp_path):
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
        page.wait_for_function("() => document.querySelector('#aa-fresh .aa-fresh-v').textContent === 'v2'")
        assert _screen(page) == before
        assert _box(page, "rail").input_value() == TYPED


WATCH = """kind => {
    window.__stats = { storeReads: 0, railRenders: 0, frameRenders: 0 };
    const real = window.__realFetch || (window.__realFetch = window.fetch);
    window.fetch = (url, opts) => {
        if (String(url).includes('comments.json')) window.__stats.storeReads++;
        const post = opts && opts.method === 'POST' && /api\\/comments(\\/[^/?]+\\/reply)?(\\?|$)/.test(String(url));
        return real(url, opts).then(r => post ? new Promise(res => setTimeout(() => {
            const frame = document.getElementById('content-frame').contentDocument;
            window.__posted = document.querySelector('#comment-list .citem.is-pending') || document.querySelector('#comment-list [data-comment-id="reply-card"]');
            const ownId = window.__posted.dataset.commentId;
            const ownAnchor = kind === 'comment' ? 's:checks' : 's:checks:p1';
            window.__kept = [
                ...[...document.querySelectorAll('#comment-list .citem')].filter(el => el.dataset.commentId !== ownId),
                ...[...frame.querySelectorAll('[data-strip-item]')].filter(el => el.dataset.stripItem !== ownId),
                ...[...frame.querySelectorAll('[data-pin-anchor]')].filter(el => el.dataset.pinAnchor !== ownAnchor),
            ];
            window.__stats = { storeReads: 0, railRenders: 0, frameRenders: 0, answered: true }; res(r); }, 600)) : r);
    };
    new MutationObserver(ms => { window.__stats.railRenders += ms.filter(m => m.target.id === 'comment-list').length; })
        .observe(document.getElementById('comment-list'), { childList: true });
    document.getElementById('content-frame').contentWindow.addEventListener('message', e => {
        if (e.data && e.data.type === 'annotate:comment-counts') window.__stats.frameRenders++;
    });
}"""


@pytest.mark.parametrize("kind", ["comment", "reply"])
def test_a_confirmed_post_updates_only_its_own_card_without_rereading_the_store(tmp_path, kind):
    directory = _directory(tmp_path)
    with _open(tmp_path, directory, "chrome") as (page, base):
        page.evaluate(WATCH, kind)
        if kind == "comment":
            page.frame_locator("#content-frame").locator('[data-anchor-id="s:checks"] h2').click(position={"x": 10, "y": 5})
            page.locator("#pop-ta").fill("A new note " + "Some details. " * 100)
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
        assert stats["railRenders"] == 0 and stats["frameRenders"] == 1, stats
        assert page.evaluate("() => window.__kept.length > 0 && window.__kept.every(el => el.isConnected)")
        assert page.locator("#comment-list .citem" if kind == "comment" else "#comment-list .thread-reply",
                            has_text="A new note" if kind == "comment" else "A reply").count() == 1
        assert page.evaluate("() => !window.__posted.isConnected")
        # Actions on the replacement must still find their live card and editor.
        if kind == "reply":
            page.locator('#comment-list [data-reply-for="reply-card"]').fill("Another reply")
            page.locator('[data-action="reply"][data-id="reply-card"]').click()
            page.locator('#comment-list .thread-reply:not(.is-pending)', has_text="Another reply").wait_for()
        else:
            card = page.locator('#comment-list .citem', has_text="A new note")
            assert card.locator('.citem-txt-more').is_visible()
            card.locator('[data-action="menu"]').click()
            assert card.locator('.citem-menu').is_visible()
            card.locator('[data-action="menu"]').click()
        # What a refresh brings is what is on screen.
        page.evaluate("() => window.AnnotateDocs.reload()")
        page.wait_for_timeout(300)
        shown = page.locator("#comment-list .citem" if kind == "comment" else "#comment-list .thread-reply",
                             has_text="A new note" if kind == "comment" else "A reply")
        assert shown.count() == 1
        assert page.evaluate("() => document.getElementById('aa-fresh').dataset.state") == "idle"


def test_posts_confirming_out_of_order_keep_numbers_unique_and_existing_labels_stable(tmp_path):
    directory = _directory(tmp_path)
    with _open(tmp_path, directory, "chrome") as (page, base):
        labels = page.evaluate("() => Object.fromEntries(AnnotateDocs.comments().map(c => [c.id, AnnotateDocs.number(c.id)]))")
        page.evaluate(r"""() => {
            const real = window.fetch;
            window.fetch = async (url, opts) => {
                if (opts?.method === 'POST' && /api\/comments(\?|$)/.test(String(url)) &&
                    JSON.parse(opts.body).text === 'First post') await new Promise(resolve => window.__first = resolve);
                return real(url, opts);
            };
        }""")
        for anchor, text in [("s:checks", "First post"), ("s:checks:p1", "Second post")]:
            page.frame_locator("#content-frame").locator(f'[data-anchor-id="{anchor}"]').first.click(position={"x": 10, "y": 5})
            page.locator("#pop-ta").fill(text)
            page.locator("#pop-save").click()
        page.wait_for_function("() => AnnotateDocs.comments().some(c => c.text === 'Second post' && !c.pending)")
        cards = page.locator('#comment-list .citem').filter(
            has=page.locator('.citem-txt', has_text=re.compile(r"^(First|Second) post$")))
        numbers = cards.locator('[data-num-for]').all_text_contents()
        assert len(numbers) == len(set(numbers)) == 2
        page.evaluate("window.__first()")
        page.wait_for_function("() => !document.querySelector('#comment-list .citem.is-pending')")
        assert page.evaluate("""labels => Object.entries(labels).every(([id, n]) => AnnotateDocs.number(id) === n) &&
            AnnotateDocs.comments().filter(c => /^(First|Second) post$/.test(c.text)).every(c => AnnotateDocs.number(c.id) === c.number)
        """, labels)
        numbers = cards.locator('[data-num-for]').all_text_contents()
        assert len(numbers) == len(set(numbers)) == 2
