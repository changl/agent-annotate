"""uzd.10: each request a Send, Discard, answer or poll no longer repeats stays gone.

Over Funnel each request in a chain is a round trip Chang waits for, and every
open tab's poll is load on the M1.
"""

from urllib.parse import urlsplit

import pytest
from test_fix_ui_shell import MANUAL_REVIEW_POLL
from test_keep_drafts import _agent, _directory, _loaded, _poll, _session

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect

POLL_READS = {"/comments.json", "/api/read-state", "/api/categories", "/api/session-monitor", "/current.meta.json"}


def _manual(page):
    page.add_init_script(MANUAL_REVIEW_POLL)  # only _poll polls, so a count is not a timer's
    page.reload(wait_until="networkidle")
    _loaded(page)


def _record(page):
    seen = []
    page.on("request", lambda r: seen.append((r.method, urlsplit(r.url).path, urlsplit(r.url).query)))
    return seen


def _paths(seen, method="GET"):
    return [path for m, path, _ in seen if m == method]


def _at(seen, path):
    return [p for _, p, _ in seen].index(path)


def _answer(page):
    page.locator('#comment-list [data-comment-id="question-11"] .decision-btn').first.click()
    page.wait_for_timeout(800)  # past the 250 ms counts refresh a read mark used to schedule


def test_an_unchanged_poll_is_one_request_and_a_change_reads_only_what_moved(tmp_path):
    directory = _directory(tmp_path)
    with _session(tmp_path, directory) as (page, base, _):
        _manual(page)
        _poll(page)  # the first poll makes every read and remembers them
        seen = _record(page)
        _poll(page, 2)
        assert seen == [("GET", "/api/poll", seen[0][2])] * 2, seen
        seen.clear()
        _agent(base, "api/comments/batch", {"items": [{"anchor_id": "s:checks", "text": "New card.", "version": "v1"}]})
        _poll(page)
        reads = _paths(seen)
        assert reads[0] == "/api/poll" and "/comments.json" in reads and "/api/session-monitor" not in reads, reads


def test_an_older_server_without_the_one_poll_gets_every_read(tmp_path):
    directory = _directory(tmp_path)
    with _session(tmp_path, directory) as (page, _, _):
        _manual(page)
        page.route("**/api/poll?*", lambda route: route.fulfill(status=404, content_type="application/json", body="{}"))
        _poll(page)
        seen = _record(page)
        _poll(page)  # asks once, gets a 404, and reads as before
        assert _paths(seen).count("/api/poll") == 1 and POLL_READS <= set(_paths(seen)), seen
        seen.clear()
        _poll(page)  # and does not ask that server again
        assert "/api/poll" not in _paths(seen) and POLL_READS <= set(_paths(seen)), seen


def test_an_answer_takes_the_counts_from_its_read_mark(tmp_path):
    directory = _directory(tmp_path)
    with _session(tmp_path, directory) as (page, _, _):
        _manual(page)
        seen = _record(page)
        _answer(page)
        marks = [n for n, (m, path, _) in enumerate(seen) if (m, path) == ("POST", "/api/read-state")]
        assert marks and "counts=1" in seen[marks[-1]][2], seen
        assert "/api/categories" not in _paths(seen[marks[0]:]), seen


def test_a_send_with_no_draft_reads_the_store_once_before_it_submits(tmp_path):
    directory = _directory(tmp_path)
    with _session(tmp_path, directory) as (page, _, _):
        _manual(page)
        _answer(page)
        seen = _record(page)
        page.locator("#send-btn").click()
        page.locator("#round-submit-btn").click()
        expect(page.locator("#round-confirm-backdrop")).to_be_hidden()
        assert _paths(seen[:_at(seen, "/api/rounds/submit")]).count("/comments.json") == 1, seen


def test_a_discard_reads_the_page_back_once(tmp_path):
    directory = _directory(tmp_path)
    with _session(tmp_path, directory) as (page, _, _):
        _manual(page)
        _answer(page)
        page.locator("#send-btn").click()
        seen = _record(page)
        page.locator("#round-discard-btn").click()
        expect(page.locator("#round-confirm-backdrop")).to_be_hidden()
        page.wait_for_timeout(500)
        assert _paths(seen[_at(seen, "/api/rounds/discard"):]).count("/comments.json") == 1, seen


def _pending(page):
    return page.evaluate("() => AnnotateDocs.pageRoundPending()")


def _unread(page):
    return page.evaluate("() => AnnotateDocs.categories().categories.find(c => c.id === 'review').counts.unread")


@pytest.mark.parametrize("action, fails", [("submit", 1), ("discard", 1), ("submit", 2)])
def test_a_failed_read_back_after_a_send_or_discard_is_read_again(tmp_path, action, fails):
    # Review of b82ca42: the tab showed the cleared verdict as pending after one 500. Review of
    # eeb804b: after two, the retry failed too, and the next healthy poll must show the store.
    directory = _directory(tmp_path)
    with _session(tmp_path, directory) as (page, base, _):
        _manual(page)
        _answer(page)
        assert _pending(page) == 1
        posted, fault = [], []
        page.on("response", lambda r: posted.append(1) if urlsplit(r.url).path == f"/api/rounds/{action}" and r.ok else None)

        def read_back(route):
            if posted and len(fault) < fails:
                fault.append(route.request.url)
                route.fulfill(status=500, content_type="application/json", body='{"error":"transient"}')
            else:
                route.continue_()

        page.route("**/comments.json?*", read_back)
        page.locator("#send-btn").click()
        page.locator(f"#round-{action}-btn").click()
        expect(page.locator("#round-confirm-backdrop")).to_be_hidden()
        page.wait_for_timeout(350)
        assert posted and len(fault) == fails
        second = page.context.new_page()
        second.goto(base + "#view=review", wait_until="networkidle")
        _loaded(second)
        assert _pending(second) == 0, "the server cleared it"
        page.bring_to_front()
        _poll(page)
        assert _pending(page) == 0


def test_a_read_mark_overtaken_by_a_counts_read_still_shows_its_counts(tmp_path):
    # Review of b82ca42: a categories GET asked after the mark but sampled before it kept the old count.
    directory = _directory(tmp_path)
    with _session(tmp_path, directory) as (page, base, _):
        _manual(page)
        before = _unread(page)
        assert before > 0
        page.evaluate("""() => {
            const original = window.fetch;
            window.fetch = (resource, options) => {
                if (options?.method === 'POST' && String(resource).includes('/api/read-state')) {
                    return new Promise((resolve, reject) => {
                        window.releaseMark = () => original(resource, options).then(resolve, reject);
                    });
                }
                return original(resource, options);
            };
            window.pendingMark = AnnotateDocs.markRead([AnnotateDocs.findComment('question-11')]);
        }""")
        page.wait_for_function("() => !!window.releaseMark")
        page.evaluate("() => AnnotateDocs.refreshStore()")
        assert _unread(page) == before
        page.evaluate("async () => { window.releaseMark(); await window.pendingMark; }")
        server = next(c["counts"]["unread"] for c in page.request.get(base + "api/categories").json()["categories"] if c["id"] == "review")
        assert server == before - 1
        page.wait_for_function("n => AnnotateDocs.categories().categories.find(c => c.id === 'review').counts.unread === n", arg=server)


HOLD_ONE_GET = """path => {
    const real = window.fetch;
    let hold = true;
    window.fetch = (resource, options) => {
        if (hold && new URL(resource, location.href).pathname === path && (!options?.method || options.method === 'GET')) {
            hold = false;
            return real(resource, options).then(answer => new Promise(resolve => {
                window.oldStatus = answer.status;
                window.releaseOld = () => resolve(answer);
            }));
        }
        return real(resource, options);
    };
}"""


@pytest.mark.parametrize("held, action", [("/comments.json", "discard"), ("/api/poll", "discard"), ("/api/poll", "submit")],
                         ids=["legacy-discard", "batch-discard", "batch-send"])
def test_a_poll_asked_before_a_failed_read_back_cannot_clear_its_recovery(tmp_path, held, action):
    # Review of 02d2881: a poll asked before the Send or Discard and answered after it cleared the stale mark.
    directory = _directory(tmp_path)
    with _session(tmp_path, directory) as (page, _, _):
        _manual(page)
        if held == "/comments.json":
            page.route("**/api/poll?*", lambda route: route.fulfill(status=404, body="{}"))
        _answer(page)
        assert _pending(page) == 1
        _poll(page, 2)  # the poll's ETags are known, or the tab is back on the old reads
        page.evaluate(HOLD_ONE_GET, held)
        page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        page.wait_for_function("() => !!window.releaseOld")
        assert page.evaluate("window.oldStatus") in (200, 304)
        posted, fault = [], []
        page.on("response", lambda r: posted.append(1) if urlsplit(r.url).path == f"/api/rounds/{action}" and r.ok else None)

        def read_back(route):
            if posted and len(fault) < 2:
                fault.append(route.request.url)
                route.fulfill(status=500, content_type="application/json", body='{"error":"transient"}')
            else:
                route.continue_()

        page.route("**/comments.json?*", read_back)
        page.locator("#send-btn").click()
        page.locator(f"#round-{action}-btn").click()
        expect(page.locator("#round-confirm-backdrop")).to_be_hidden()
        page.wait_for_timeout(350)
        assert posted and len(fault) == 2 and _pending(page) == 1
        page.evaluate("() => window.releaseOld()")
        page.wait_for_timeout(350)
        with page.expect_response(lambda r: urlsplit(r.url).path == "/comments.json" and r.status in (200, 304), timeout=4500):
            _poll(page)
        assert _pending(page) == 0
