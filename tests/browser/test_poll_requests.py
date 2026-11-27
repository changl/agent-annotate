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
