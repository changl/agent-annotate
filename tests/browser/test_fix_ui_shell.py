"""Shell fixes from the UI review (UI-10 … UI-28, shell parts): version links,
the older-version banner, theme before paint, outside links, long comments,
card links, the review key in the address bar and one-tab pages.

Every outside request is aborted: no test loads a real external site."""

import json
from contextlib import contextmanager
from urllib.parse import urlsplit

import pytest
from review_fixtures import complete
from single_page import go, history, ready
from test_card_layout import CHROME, _serve
from test_single_page_acceptance import workspace  # noqa: F401
from test_workspace_intent import _page

from agent_annotate.categories import publish_plan_revision
from agent_annotate.pagegen import generate
from agent_annotate.review_versions import activate
from agent_annotate.store import transaction, write_json
from agent_annotate.sync_server import _withdraw_decision

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect

pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")

LONG = ("Long comment " + "x" * 7) * 1000  # 20,000 characters
OUTSIDE = "https://example.test/outside"
# Drive the poll explicitly so a slow Chrome run cannot heal startup first.
MANUAL_REVIEW_POLL = """(() => {
    const timeout = window.setTimeout;
    window.setTimeout = (fn, ms, ...args) => timeout(fn, fn.name === 'refresh' ? 120000 : ms, ...args);
})();"""


@pytest.fixture
def versions(tmp_path):
    """Review at v1 and v2: question-11 (open, v1), ready-12 (answered and
    not sent, v2, so a one-line card that follows the viewer), long-13 (a
    20,000-character comment on v2) and an outside link in v2."""
    directory = _page(tmp_path)
    source = tmp_path / "v2.md"
    source.write_text(
        "---\ntitle: Second review\nversion: v2\nfull_plan: true\nother_files_required: none\n---\n\n"
        f"## Checks\n\nSecond document with an [outside link]({OUTSIDE}).\n"
    )
    generate(source, directory)
    complete(directory)
    meta = json.loads((directory / "current.meta.json").read_text())
    meta.update(current="v2", history=[{"version": "v1"}, {"version": "v2"}])
    (directory / "current.meta.json").write_text(json.dumps(meta))
    path = directory / "comments.json"
    store = json.loads(path.read_text())
    question = store["anchors"]["d:q11"][0]
    ready_card = dict(
        question,
        id="ready-12",
        number=12,
        anchor_id="s:checks:p1",
        version="v2",
        decision={"verdict": "accept", "by": "reviewer@example.com", "ts": "2026-10-02T11:00:00Z", "round_pending": True},
    )
    ready_card["decision_request"] = {"prompt": "Keep the second check?", "options": ["accept", "reject"]}
    long_comment = {
        "id": "long-13",
        "number": 13,
        "anchor_id": "s:checks",
        "text": LONG,
        "author": "agent:review-test",
        "created_at": "2026-10-02T11:30:00Z",
        "version": "v2",
        "status": "open",
    }
    store["anchors"]["s:checks:p1"] = [ready_card]
    store["anchors"]["s:checks"] = [long_comment]
    path.write_text(json.dumps(store))
    return directory


@contextmanager
def opened(tmp_path, directory, address="#view=review", width=1440, height=900, init=None, routes=(), wait=True):
    """The page at base + address, with every non-local request aborted."""
    try:
        process, base = _serve(tmp_path, directory)
    except AssertionError:  # a cold first start on a slow disk; try once more
        process, base = _serve(tmp_path, directory)
    registry = tmp_path / "state" / "bus.json"
    if registry.exists():
        data = json.loads(registry.read_text())
        data["slugs"]["items-model"].update(port=urlsplit(base).port, url=base)
        registry.write_text(json.dumps(data))
    blocked = []
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            context = browser.new_context(viewport={"width": width, "height": height})

            def outside(route):
                blocked.append(route.request.url)
                route.abort()

            context.route(lambda url: not url.startswith(base), outside)
            for pattern, handler in routes:
                context.route(pattern, handler)
            for script in init or []:
                context.add_init_script(script)
            page = context.new_page()
            page.set_default_timeout(10_000)
            page.set_default_navigation_timeout(30_000)
            page.goto(base + address, wait_until="domcontentloaded" if not wait else "networkidle")
            if wait:
                ready(page)
            try:
                yield page, base, blocked
            finally:
                context.unroute_all(behavior="wait")
                browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


def frame_version(page):
    return page.locator("#content-frame").get_attribute("data-version")


def open_sections(page):
    page.evaluate("() => window.AA.rail.reveal()")
    for head in page.locator('#comment-list [data-section-toggle][aria-expanded="false"]').all():
        head.click()


# ── UI-10: ?v=vN opens that version; the tab and the refresh button say so (av1, #136)
@pytest.mark.parametrize("address", ["?v=v1#view=review", "?v=v1"])
def test_query_version_link_opens_that_version_with_banner(tmp_path, versions, address):
    with opened(tmp_path, versions, address) as (page, base, _):
        page.wait_for_function("() => document.getElementById('content-frame').dataset.version === 'v1'")
        fresh = page.locator("#aa-fresh")
        expect(fresh.locator(".aa-fresh-v")).to_have_text("v2")
        expect(page.locator("#aa-tabs .aa-tab-ver")).to_have_text("v1 · older")
        assert page.evaluate("location.search") == ""
        assert "v=v1" in page.evaluate("location.hash")
        fresh.click()
        page.wait_for_function("() => document.getElementById('content-frame').dataset.version === 'v2'")
        expect(fresh.locator(".aa-fresh-v")).to_be_hidden()
        page.reload(wait_until="networkidle")
        ready(page)
        assert frame_version(page) == "v2"


def test_hash_version_wins_over_query_version(tmp_path, versions):
    with opened(tmp_path, versions, "?v=v1#view=review&v=v2") as (page, _, _b):
        assert frame_version(page) == "v2"
        expect(page.locator("#aa-fresh .aa-fresh-v")).to_be_hidden()


# ── UI-20 → av1: an older version is named in the Review tab (no banner row);
# the refresh button names the latest in plain text, never in a red pill (#136).
@pytest.mark.parametrize("width", [1440, 390])
def test_older_version_shows_in_the_tab_and_the_refresh_button(tmp_path, versions, width):
    with opened(tmp_path, versions, "#view=review&v=v1", width=width, height=844) as (page, _, _b):
        label = page.locator("#aa-tabs .aa-tab-ver" if width > 768 else "#aa-tabs-menu summary .aa-tab-ver")
        expect(label).to_have_text("v1 · older")
        assert label.evaluate("el => !el.closest('.badge')")
        fresh = page.locator("#aa-fresh")
        expect(fresh.locator(".aa-fresh-v")).to_have_text("v2")
        assert fresh.locator(".badge:visible").count() == 0
        assert page.locator("#frame-area .view-hd").is_hidden()


# ── UI-19: a collapsed card from a newer version keeps its way back ────────
def test_collapsed_ready_card_on_older_version_links_to_its_version(tmp_path, versions):
    with opened(tmp_path, versions, "#view=review&v=v1") as (page, _, _b):
        open_sections(page)
        card = page.locator('#comment-list .citem.is-line[data-comment-id="ready-12"]')
        expect(card).to_be_visible()
        line = card.locator(".unified-newer-location")
        expect(line).to_have_text("Not in v1 — open v2")
        line.locator("button").click()
        page.wait_for_function("() => document.getElementById('content-frame').dataset.version === 'v2'")


# ── UI-18: the saved theme is applied before shell.js runs ─────────────────
def test_saved_light_theme_applies_before_the_shell_script(tmp_path, versions):
    process, base = _serve(tmp_path, versions)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            context = browser.new_context()
            context.route(lambda url: not url.startswith(base), lambda route: route.abort())
            context.add_init_script("try{localStorage.setItem('annotate:theme','light')}catch(e){}")
            # shell.js never arrives: only the page's <head> can set the theme.
            context.route("**/shell.js", lambda route: route.abort())
            page = context.new_page()
            page.goto(base + "#view=review", wait_until="domcontentloaded")
            assert page.evaluate("document.documentElement.getAttribute('data-theme')") == "light"
            assert page.evaluate("typeof window.AnnotateDocs") == "undefined"
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


# ── UI-21: an outside link opens in a new tab, not in the content frame ────
def test_outside_link_opens_in_a_new_tab_not_in_the_frame(tmp_path, versions):
    with opened(tmp_path, versions) as (page, base, blocked):
        frame = page.frame_locator("#content-frame")
        link = frame.locator(f'a[href="{OUTSIDE}"]')
        expect(link).to_be_visible()
        src = page.locator("#content-frame").get_attribute("src")
        link.click(trial=True)
        link.focus()
        with page.context.expect_page() as popup:
            # A new tab can throttle the old tab before Playwright receives its click ack.
            link.evaluate("a => setTimeout(() => a.click())")
        tab = popup.value
        assert link.get_attribute("target") == "_blank"
        assert "noopener" in (link.get_attribute("rel") or "").split()
        tab.close()
        # The document is still the page's own, in place.
        assert page.locator("#content-frame").get_attribute("src") == src
        content = page.frame(url=lambda u: u.startswith(base))
        assert content is not None
        assert all(f.url.startswith(base) or f.url == "about:blank" for f in page.frames)
        assert blocked and all(not u.startswith(base) for u in blocked)


# ── UI-23: a long comment is clamped, with final/'s Show more / Show less ──
def test_long_comment_is_clamped_with_show_more(tmp_path, versions):
    with opened(tmp_path, versions) as (page, _, _b):
        open_sections(page)
        card = page.locator('#comment-list .citem[data-comment-id="long-13"]')
        card.scroll_into_view_if_needed()
        expect(card).to_be_visible()
        assert card.bounding_box()["height"] < 600
        more = card.locator(".citem-txt-more")
        expect(more).to_have_text("Show more")
        expect(more).to_have_attribute("aria-expanded", "false")
        more.click()
        expect(more).to_have_text("Show less")
        assert card.bounding_box()["height"] > 1500
        more.click()
        expect(more).to_have_text("Show more")
        assert card.bounding_box()["height"] < 600
        # A short comment gets no button.
        assert page.locator('#comment-list .citem[data-comment-id="question-11"] .citem-txt-more').count() == 0


# ── UI-24: #feedback=<id> opens and highlights the card ────────────────────
def test_feedback_link_opens_and_highlights_the_card(tmp_path, versions):
    with opened(tmp_path, versions, "#feedback=ready-12") as (page, _, _b):
        card = page.locator('#comment-list .citem[data-comment-id="ready-12"]')
        expect(card).to_be_visible()
        assert "hl" in card.get_attribute("class").split()
        # The one-line answered card opens in full.
        assert "is-line" not in card.get_attribute("class").split()
        assert page.evaluate("new URLSearchParams(location.hash.slice(1)).get('view')") == "review"
        # A link typed while the page is open works too, and #c= is accepted.
        page.evaluate("() => { location.hash = '#c=question-11' }")
        page.wait_for_function(
            "() => document.querySelector('#comment-list .citem[data-comment-id=\"question-11\"]')?.classList.contains('hl')"
        )


def test_feedback_link_opens_the_cards_own_tab(tmp_path, workspace):  # noqa: F811
    with opened(tmp_path, workspace, "#view=library&feedback=plan-31") as (page, _, _b):
        page.wait_for_function("() => document.body.dataset.view === 'plans'")
        page.wait_for_function(
            "() => document.querySelector('#comment-list .citem[data-comment-id=\"plan-31\"]')?.classList.contains('hl')"
        )


# ── UI-25: after "Skip to document", Tab reaches the first option of the
# document's decision strip; Enter answers it (kept), so its focus must show.
def test_focused_document_option_shows_a_clear_focus_ring(tmp_path, versions):
    with opened(tmp_path, versions, "#view=review&v=v1") as (page, _, _b):
        page.keyboard.press("Tab")
        expect(page.locator(":focus")).to_have_text("Skip to document")
        page.keyboard.press("Enter")
        page.keyboard.press("Tab")
        frame = page.frame_locator("#content-frame")
        focused = frame.locator(".annotate-decision-btn:focus-visible")
        expect(focused).to_have_count(1)
        ring = focused.evaluate("e => { const s = getComputedStyle(e); return [s.outlineStyle, s.outlineWidth, s.outlineOffset]; }")
        assert ring == ["solid", "2px", "2px"], ring


# ── UI-27: the review key leaves the address bar before any request ────────
RECORD_FETCH = """(() => {
  window.__sessions = [];
  const real = window.fetch;
  window.fetch = function (input, init) {
    const url = String(input && input.url || input);
    if (!url.includes('api/reviewer/session')) return real.apply(this, arguments);
    const entry = {href: location.href, frame: document.getElementById('content-frame')?.getAttribute('src') || null, status: null};
    window.__sessions.push(entry);
    return real.apply(this, arguments).then(r => { entry.status = r.status; return r; });
  };
})();"""


def test_review_key_leaves_the_address_before_the_session_exchange(tmp_path, versions):
    # The server grants sessions only on its Funnel origin (tests/test_review_access.py
    # covers that exchange). On loopback this test answers the browser's one
    # session call itself (simulated), so the page then loads as a reviewer's would.
    key = "PrivateReviewKey0123456789abcdefghijklmnopq"
    seen = []

    def session(route):
        seen.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json", body='{"ok":true}')

    address = f"#review={key}&view=review"
    routes = [("**/api/reviewer/session", session)]
    with opened(tmp_path, versions, address, init=[RECORD_FETCH], routes=routes, wait=False) as (page, _, _b):
        page.wait_for_function("() => window.__sessions.length && window.__sessions[0].status")
        assert seen and seen[-1]["key"] == key
        sessions = page.evaluate("window.__sessions")
        assert sessions[0]["status"] == 200, (sessions, page.locator("#delivery-status").text_content())
        ready(page)
        assert len(sessions) == 1
        assert key not in sessions[0]["href"] and "review=" not in sessions[0]["href"]
        assert sessions[0]["frame"] is None
        assert key not in page.url
        assert page.evaluate("new URLSearchParams(location.hash.slice(1)).get('view')") == "review"
        # The session exchange still worked: the page loaded its document.
        expect(page.locator("#delivery-status")).not_to_contain_text("invalid or expired")
        assert frame_version(page) == "v2"


def test_wrong_review_key_still_leaves_the_address(tmp_path, versions):
    with opened(tmp_path, versions, "#review=wrong-key", init=[RECORD_FETCH], wait=False) as (page, _, _b):
        expect(page.locator("#delivery-status")).to_have_text("This review link is invalid or expired.")
        assert "wrong-key" not in page.url
        assert "wrong-key" not in page.evaluate("window.__sessions")[0]["href"]


def test_first_review_open_refreshes_meta_when_store_shows_a_new_publish(tmp_path, versions):
    reads = []

    def meta(route):
        reads.append(route.request.url)
        if len(reads) == 1:
            route.fulfill(json={"current": "v1", "history": [{"version": "v1"}]})
        else:
            route.continue_()

    # The early meta response is from before the publish, the real store and
    # later meta responses come from the v2 already published in this fixture.
    with opened(tmp_path, versions, routes=[("**/current.meta.json", meta)]) as (page, _, _):
        assert frame_version(page) == "v2"
        assert len(reads) >= 2


def test_first_review_open_refreshes_store_when_meta_shows_a_new_publish(tmp_path, versions):
    reads = []

    def store(route):
        reads.append(route.request.url)
        if len(reads) == 1:
            snapshot = route.fetch().json()
            snapshot["current_version"] = "v1"
            for anchor, cards in snapshot["anchors"].items():
                snapshot["anchors"][anchor] = [card for card in cards if card["id"] != "ready-12"]
            route.fulfill(json=snapshot)
        else:
            route.continue_()

    with opened(tmp_path, versions, routes=[("**/comments.json?view=page", store)]) as (page, _, _):
        assert frame_version(page) == "v2"
        open_sections(page)
        assert page.locator('#comment-list [data-comment-id="ready-12"]').count() == 1
        assert len(reads) >= 2


@pytest.mark.parametrize("later_meta", [False, True], ids=["matched", "metadata-ahead"])
def test_startup_publish_keeps_draft_and_refresh_on_the_reissued_version(tmp_path, versions, later_meta):
    source = tmp_path / "v3.md"
    source.write_text("---\ntitle: Third review\nversion: v3\nfull_plan: true\nother_files_required: none\n---\n\n## Checks\n\nThird document.\n")
    generate(source, versions)
    path = versions / "comments.json"
    snapshot = json.loads(path.read_text())
    question = {
        "number": 31, "anchor_id": "d:q31", "text": "Keep the check?",
        "author": "agent:review-test", "status": "open", "replies": [],
        "decision_request": {"prompt": "Keep the check?", "options": ["accept", "reject"]},
    }
    snapshot["anchors"]["d:q31"] = [dict(question, id=f"reissued-v{i}", version=f"v{i}") for i in (2, 3)]
    path.write_text(json.dumps(snapshot))
    reads = []

    def store(route):
        reads.append(route.request.url)
        if len(reads) == 1:
            # Startup already read an older store before it saw v2 metadata.
            older = route.fetch().json()
            older["current_version"] = "v1"
            route.fulfill(json=older)
        else:
            if len(reads) == 2:
                with transaction(versions):
                    complete(versions)
            route.continue_()

    def meta(route):
        if len(reads) == 2:
            ahead = route.fetch().json()
            ahead["current"] = "v4"
            ahead["history"].append({"version": "v4"})
            route.fulfill(json=ahead)
        else:
            route.continue_()

    routes = [("**/comments.json?view=page", store)]
    if later_meta:
        routes.append(("**/current.meta.json", meta))
    with opened(tmp_path, versions, routes=routes, init=[MANUAL_REVIEW_POLL]) as (page, _, _):
        assert frame_version(page) == "v3"
        assert len(reads) >= 2
        urls = page.evaluate("performance.getEntriesByType('resource').map(e => e.name)")
        assert not any("view=poll" in url for url in urls)
        page.evaluate("() => window.AA.rail.reveal()")
        text = "Draft from the reissued v3 question"
        page.locator('#comment-list [data-decision-say-ta="reissued-v3"]').fill(text)
        page.locator("#send-btn").click()
        page.locator("#round-submit-btn").click()
        expect(page.locator("#round-confirm-backdrop")).to_be_hidden()
        older, current = json.loads(path.read_text())["anchors"]["d:q31"]
        assert (current.get("decision") or {}).get("text") == text
        assert not older.get("decision")

        # An in-flight poll leaves the Refresh click using the installed metadata.
        paused = []
        pattern = "**/current.meta.json"
        page.route(pattern, lambda route: paused.append(route))
        try:
            with page.expect_request(pattern):
                page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
            with page.expect_request("**/content?v=v3"):
                page.locator("#aa-fresh").click()
            assert frame_version(page) == "v3"
        finally:
            for route in paused:
                route.continue_()
            page.unroute(pattern)


def _stage_review(tmp_path, directory, version):
    source = tmp_path / f"{version}.md"
    source.write_text(f"---\ntitle: Review {version}\nversion: {version}\nfull_plan: true\nother_files_required: none\n---\n\n## Checks\n\nPublished {version}.\n")
    generate(source, directory)


def _reissued_card(version):
    return {"id": f"reissued-{version}", "number": 31, "anchor_id": "d:q31", "version": version,
            "text": "Keep the check?", "author": "agent:review-test", "status": "open", "replies": [],
            "decision_request": {"prompt": "Keep the check?", "options": ["accept", "reject"]}}


def _try_send(page):
    page.locator("#send-btn").click()
    page.locator("#round-submit-btn").click()
    page.wait_for_function("""() => !document.getElementById('round-confirm-backdrop').classList.contains('vis')
        || !document.getElementById('round-submit-btn').disabled""")


def test_full_store_startup_publish_keeps_new_questions_behind_refresh(tmp_path, versions):
    _stage_review(tmp_path, versions, "v3")
    path = versions / "comments.json"
    store = json.loads(path.read_text())
    store["anchors"]["s:old"] = [{"id": "old-draft", "anchor_id": "s:old", "version": "v1",
                                   "status": "addressed_by_agent", "author": "agent:test", "text": "Settled earlier."}]
    store["anchors"]["d:q31"] = [_reissued_card("v2"), _reissued_card("v3")]
    write_json(path, store)
    published = []

    def full_store(route):
        if not published:
            with transaction(versions):
                activate(versions, "v3")
            published.append(True)
        route.continue_()

    draft = """localStorage.setItem('annotate:drafts:' + location.pathname + ':review',
                                    JSON.stringify({'say:old-draft': 'A saved older draft'}));"""
    routes = [("**/comments.json?view=poll", full_store)]
    with opened(tmp_path, versions, routes=routes, init=[draft, MANUAL_REVIEW_POLL]) as (page, _, _):
        assert published and frame_version(page) == "v2"
        page.evaluate("() => window.AA.rail.reveal()")
        new_question = page.locator('#comment-list [data-decision-say-ta="reissued-v3"]')
        visible = new_question.is_visible()
        box = new_question if visible else page.locator('#comment-list [data-decision-say-ta="reissued-v2"]')
        box.fill("Draft typed on the shown question")
        _try_send(page)
        cards = json.loads(path.read_text())["anchors"]["d:q31"]
        decisions = {card["id"]: (card.get("decision") or {}).get("text") for card in cards}
        assert not visible and all(text is None for text in decisions.values()), (visible, decisions)
        expect(page.locator("#round-confirm-backdrop")).to_be_visible()
        expect(page.locator("#round-confirm-sub")).to_contain_text("Refresh")
        expect(page.locator("#aa-fresh .aa-fresh-v")).to_have_text("v3")


def test_startup_withdrawal_pauses_send_and_keeps_the_shown_draft(tmp_path, versions):
    for version in ("v3", "v4"):
        _stage_review(tmp_path, versions, version)
    path = versions / "comments.json"
    snapshot = json.loads(path.read_text())
    snapshot["anchors"]["d:q31"] = [_reissued_card("v3")]
    write_json(path, snapshot)
    reads, published = [], []

    def store(route):
        reads.append(route.request.url)
        if len(reads) == 1:
            older = route.fetch().json()
            older["current_version"] = "v1"
            route.fulfill(json=older)
            return
        if len(reads) == 2:
            with transaction(versions):
                activate(versions, "v3")
            published.append("v3")
        route.continue_()

    def meta(route):
        if published == ["v3"]:
            with transaction(versions):
                latest = json.loads(path.read_text())
                _withdraw_decision(latest["anchors"]["d:q31"][0], "not asked again in v4", "agent:review-test")
                write_json(path, latest)
                activate(versions, "v4")
            published.append("v4")
        route.continue_()

    routes = [("**/comments.json?view=page", store), ("**/current.meta.json", meta)]
    with opened(tmp_path, versions, routes=routes, init=[MANUAL_REVIEW_POLL]) as (page, _, _):
        assert published == ["v3", "v4"] and frame_version(page) == "v3", (published, frame_version(page))
        page.evaluate("() => window.AA.rail.reveal()")
        text = "Unsaved text from the displayed v3 question"
        page.locator('#comment-list [data-decision-say-ta="reissued-v3"]').fill(text)
        posts = []
        page.on("request", lambda req: posts.append(urlsplit(req.url).path) if req.method == "POST" else None)
        _try_send(page)
        assert "/api/rounds/submit" not in posts, posts
        expect(page.locator("#round-confirm-backdrop")).to_be_visible()
        expect(page.locator("#round-confirm-sub")).to_contain_text("Refresh")
        expect(page.locator("#aa-fresh .aa-fresh-v")).to_have_text("v4")
        assert page.evaluate("JSON.parse(localStorage.getItem('annotate:drafts:/:review'))['say:reissued-v3']") == text
        page.locator("#round-cancel-btn").click()
        page.locator("#aa-fresh").click()
        expect(page.locator("#content-frame")).to_have_attribute("data-version", "v4")
        saved = page.locator('#comment-list .decision-stranded [data-decision-say-ta="reissued-v3"]')
        expect(saved).to_have_value(text)
        _try_send(page)
        expect(page.locator("#round-confirm-backdrop")).to_be_hidden()
        card = json.loads(path.read_text())["anchors"]["d:q31"][0]
        assert any(reply["text"] == text for reply in card["replies"])


def test_stale_review_send_from_plans_points_to_review_refresh(tmp_path, versions):
    publish_plan_revision(versions, "launch", '<html><body><h1>Launch</h1></body></html>', title="Launch")
    _stage_review(tmp_path, versions, "v3")
    with opened(tmp_path, versions, init=[MANUAL_REVIEW_POLL]) as (page, _, _):
        go(page, "plans", plan="launch")
        with transaction(versions):
            activate(versions, "v3")
        _try_send(page)

        modal = page.locator("#round-confirm-backdrop")
        expect(modal).to_be_visible()
        expect(page.locator("#round-confirm-sub")).to_contain_text("Open Review")
        modal.locator('[data-sum-open="review"]').click()
        expect(page.locator("#content-frame")).to_have_attribute("data-doc", "review")
        expect(page.locator("#aa-fresh .aa-fresh-v")).to_have_text("v3")
        page.locator("#aa-fresh").click()
        expect(page.locator("#content-frame")).to_have_attribute("data-version", "v3")

        go(page, "plans", plan="launch")
        _try_send(page)
        expect(modal).to_be_hidden()
        store = json.loads((versions / "comments.json").read_text())
        assert not store["anchors"]["s:checks:p1"][0]["decision"].get("round_pending")


# ── UI-28: the version hint, and pages with one tab ────────────────────────
def test_version_hint_shows_only_for_the_document_on_screen(tmp_path, workspace):  # noqa: F811
    with opened(tmp_path, workspace) as (page, _, _b):
        history(page)
        page.locator('[data-hist-filter="all"]').click()
        expect(page.locator('.hist-cat[data-cat="plans"]')).to_be_visible()
        # mme: the hint shows while the list has keyboard focus.
        page.locator('#vrail-body-review .vrow').first.focus()
        page.keyboard.press("Home")
        expect(page.locator('.hist-cat[data-cat="review"] .unified-history-hint')).to_be_visible()
        expect(page.locator('.hist-cat[data-cat="plans"] .unified-history-hint')).to_be_hidden()
        go(page, "plans")
        history(page)
        page.locator('[data-hist-filter="all"]').click()
        page.locator('#vrail-body-plans .vrow').first.focus()
        page.keyboard.press("Home")
        expect(page.locator('.hist-cat[data-cat="plans"] .unified-history-hint')).to_be_visible()
        expect(page.locator('.hist-cat[data-cat="review"] .unified-history-hint')).to_be_hidden()


def test_review_versions_come_first_and_collapse_like_a_sent_round(tmp_path, versions):
    with opened(tmp_path, versions) as (page, _, _b):
        history(page)
        sections = page.locator("#history-body > .hist-section")
        expect(sections.first).to_have_attribute("data-cat", "review")
        fold = page.locator('.hist-cat[data-cat="review"] > details.hist-collapse')
        summary = fold.locator("> summary")
        # Open by default: the versions need no click.
        expect(fold).to_have_attribute("open", "")
        expect(page.locator("#vrail-body-review")).to_be_visible()
        summary.click()
        expect(fold).not_to_have_attribute("open", "")
        expect(page.locator("#vrail-body-review")).to_be_hidden()
        # The same native keyboard as a sent round's summary.
        summary.focus()
        page.keyboard.press("Enter")
        expect(page.locator("#vrail-body-review")).to_be_visible()
        page.keyboard.press("Space")
        expect(page.locator("#vrail-body-review")).to_be_hidden()
        # Nothing is remembered: a reload opens it again.
        page.reload(wait_until="networkidle")
        ready(page)
        history(page)
        expect(fold).to_have_attribute("open", "")
        expect(page.locator("#vrail-body-review")).to_be_visible()


def test_plans_revisions_come_first_and_collapse_like_review(tmp_path, workspace):  # noqa: F811
    with opened(tmp_path, workspace) as (page, _, _b):
        go(page, "plans")
        history(page)
        first = page.locator("#history-body > .hist-section:visible").first
        expect(first).to_have_attribute("data-cat", "plans")
        fold = page.locator('.hist-cat[data-cat="plans"] > details.hist-collapse')
        expect(fold).to_have_attribute("open", "")
        expect(page.locator("#vrail-body-plans")).to_be_visible()
        fold.locator("> summary").click()
        expect(page.locator("#vrail-body-plans")).to_be_hidden()
        fold.locator("> summary").press("Enter")
        expect(page.locator("#vrail-body-plans")).to_be_visible()


def test_one_tab_page_has_no_filter_no_menu_and_a_clean_address(tmp_path, versions):
    with opened(tmp_path, versions, "#view=library") as (page, _, _b):
        assert page.evaluate("document.body.dataset.view") == "review"
        assert page.evaluate("new URLSearchParams(location.hash.slice(1)).get('view')") == "review"
        history(page)
        expect(page.locator("#hist-filter")).to_be_hidden()
        page.locator(".vrow").first.focus()
        page.keyboard.press("Home")
        expect(page.locator(".unified-history-hint").first).to_be_visible()
    with opened(tmp_path, versions, width=390, height=844) as (page, _, _b):
        expect(page.locator("#aa-tabs-menu")).to_be_hidden()


def test_tab_menu_and_filter_stay_on_a_page_with_several_tabs(tmp_path, workspace):  # noqa: F811
    with opened(tmp_path, workspace, width=390, height=844) as (page, _, _b):
        expect(page.locator("#aa-tabs-menu")).to_be_visible()
        history(page)
        expect(page.locator("#hist-filter")).to_be_visible()


# ── UI-17: the selected History filter is final/'s pale chip ───────────────
PRESSED = """() => {
  const pressed = document.querySelector('[data-hist-filter][aria-pressed="true"]');
  const probe = document.createElement('button');
  probe.className = 'btn btn-xs btn-soft btn-primary';
  document.getElementById('hist-filter').append(probe);
  const a = getComputedStyle(pressed), b = getComputedStyle(probe);
  const primary = getComputedStyle(document.documentElement).getPropertyValue('--color-primary');
  const out = {pressed: [a.backgroundColor, a.color, a.borderTopColor], soft: [b.backgroundColor, b.color, b.borderTopColor]};
  const ref = document.createElement('span'); ref.style.color = primary; document.body.append(ref);
  out.primary = getComputedStyle(ref).color;
  ref.remove(); probe.remove();
  return out;
}"""


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_selected_history_filter_is_a_pale_chip(tmp_path, workspace, theme):  # noqa: F811
    with opened(tmp_path, workspace, f"#view=review&theme={theme}") as (page, _, _b):
        history(page)
        page.mouse.move(0, 0)
        colors = page.evaluate(PRESSED)
        assert colors["pressed"] == colors["soft"], colors
        assert colors["pressed"][1] == colors["primary"], colors
