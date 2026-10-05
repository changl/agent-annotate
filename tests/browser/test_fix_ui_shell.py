"""Shell fixes from the UI review (UI-10 … UI-28, shell parts): version links,
the older-version banner, theme before paint, outside links, long comments,
card links, the review key in the address bar and one-tab pages.

Every outside request is aborted: no test loads a real external site."""

import json
from contextlib import contextmanager
from urllib.parse import urlsplit

import pytest
from single_page import go, history, ready
from test_card_layout import CHROME, _serve
from test_single_page_acceptance import workspace  # noqa: F401
from test_workspace_intent import _page

from agent_annotate import review_access
from agent_annotate.pagegen import generate

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect

pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")

LONG = ("Long comment " + "x" * 7) * 1000  # 20,000 characters
OUTSIDE = "https://example.test/outside"


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
def opened(tmp_path, directory, address="#view=review", width=1440, height=900, init=None, wait=True):
    """The page at base + address, with every non-local request aborted."""
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
            for script in init or []:
                context.add_init_script(script)
            page = context.new_page()
            page.set_default_timeout(5000)
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


# ── UI-10: ?v=vN opens that version with the older-version banner ──────────
@pytest.mark.parametrize("address", ["?v=v1#view=review", "?v=v1"])
def test_query_version_link_opens_that_version_with_banner(tmp_path, versions, address):
    with opened(tmp_path, versions, address) as (page, base, _):
        page.wait_for_function("() => document.getElementById('content-frame').dataset.version === 'v1'")
        banner = page.locator("#unified-version-banner")
        expect(banner).to_be_visible()
        expect(banner).to_contain_text("Viewing v1 (older) · Latest is v2")
        expect(page.locator("#view-hd-sub-doc")).to_contain_text("v1")
        assert page.evaluate("location.search") == ""
        assert "v=v1" in page.evaluate("location.hash")
        banner.locator("button").click()
        page.wait_for_function("() => document.getElementById('content-frame').dataset.version === 'v2'")
        expect(banner).to_be_hidden()
        page.reload(wait_until="networkidle")
        ready(page)
        assert frame_version(page) == "v2"


def test_hash_version_wins_over_query_version(tmp_path, versions):
    with opened(tmp_path, versions, "?v=v1#view=review&v=v2") as (page, _, _b):
        assert frame_version(page) == "v2"
        expect(page.locator("#unified-version-banner")).to_be_hidden()


# ── UI-20: the banner sits above the content title, as in final/ ───────────
@pytest.mark.parametrize("width", [1440, 390])
def test_older_version_banner_sits_above_the_content_title(tmp_path, versions, width):
    with opened(tmp_path, versions, "#view=review&v=v1", width=width, height=844) as (page, _, _b):
        banner = page.locator("#unified-version-banner")
        expect(banner).to_be_visible()
        order = page.evaluate(
            "() => [...document.getElementById('frame-area').children].filter(e => !e.hidden && e.offsetHeight).map(e => e.id || e.className)"
        )
        assert order.index("unified-version-banner") < order.index("view-hd")
        assert banner.bounding_box()["y"] < page.locator("#frame-area .view-hd").bounding_box()["y"]


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
        with page.context.expect_page() as popup:
            link.click()
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
        assert card.bounding_box()["height"] < 400
        more = card.locator(".citem-txt-more")
        expect(more).to_have_text("Show more")
        expect(more).to_have_attribute("aria-expanded", "false")
        more.click()
        expect(more).to_have_text("Show less")
        assert card.bounding_box()["height"] > 1500
        more.click()
        expect(more).to_have_text("Show more")
        assert card.bounding_box()["height"] < 400
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


# ── UI-27: the review key leaves the address bar before any request ────────
RECORD_FETCH = """(() => {
  window.__sessions = [];
  const real = window.fetch;
  window.fetch = function (input, init) {
    const url = String(input && input.url || input);
    if (url.includes('api/reviewer/session')) window.__sessions.push({href: location.href, frame: document.getElementById('content-frame')?.getAttribute('src') || null});
    return real.apply(this, arguments);
  };
})();"""


def test_review_key_leaves_the_address_before_the_session_exchange(tmp_path, versions, monkeypatch):
    monkeypatch.setattr(review_access, "STATE_DIR", tmp_path / "state")
    key = review_access.ensure_key(versions)
    with opened(tmp_path, versions, f"#review={key}&view=review", init=[RECORD_FETCH]) as (page, _, _b):
        sessions = page.evaluate("window.__sessions")
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


# ── UI-28: the version hint, and pages with one tab ────────────────────────
def test_version_hint_shows_only_for_the_document_on_screen(tmp_path, workspace):  # noqa: F811
    with opened(tmp_path, workspace) as (page, _, _b):
        history(page)
        page.locator('[data-hist-filter="all"]').click()
        expect(page.locator('.hist-cat[data-cat="plans"]')).to_be_visible()
        expect(page.locator('.hist-cat[data-cat="review"] .unified-history-hint')).to_be_visible()
        expect(page.locator('.hist-cat[data-cat="plans"] .unified-history-hint')).to_be_hidden()
        go(page, "plans")
        history(page)
        page.locator('[data-hist-filter="all"]').click()
        expect(page.locator('.hist-cat[data-cat="plans"] .unified-history-hint')).to_be_visible()
        expect(page.locator('.hist-cat[data-cat="review"] .unified-history-hint')).to_be_hidden()


def test_one_tab_page_has_no_filter_no_menu_and_a_clean_address(tmp_path, versions):
    with opened(tmp_path, versions, "#view=library") as (page, _, _b):
        assert page.evaluate("document.body.dataset.view") == "review"
        assert page.evaluate("new URLSearchParams(location.hash.slice(1)).get('view')") == "review"
        history(page)
        expect(page.locator("#hist-filter")).to_be_hidden()
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
