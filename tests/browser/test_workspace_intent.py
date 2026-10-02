"""Reviewer outcomes: one workspace, quiet updates and reversible answers."""

import http.server
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from contextlib import contextmanager
from urllib.parse import urlsplit

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from test_card_layout import CHROME, _serve  # noqa: E402

from agent_annotate.pagegen import generate  # noqa: E402
from agent_annotate.project_state import save_project  # noqa: E402

OWNER = "Projects > Rebex > Campaign > Content agent [term-review]"


def _page(tmp_path, custom=True, title="Campaign review"):
    directory = tmp_path / "review"
    options = ([{"id": "now", "label": "Ship now"}, {"id": "later", "label": "Ship later"}]
               if custom else [{"id": "accept", "label": "Approve"}, {"id": "reject", "label": "Revise"}])
    card = {"number": 11, "anchor_id": "d:q11", "text": "Choose the release time.",
            "decision_request": {"prompt": "When should we release?", "context": "Both builds passed.",
                                 "recommendation": options[0]["id"], "options": options,
                                 "evidence": [{"anchor": "s:checks:p1", "label": "Build result"}]}}
    source = tmp_path / "review.md"
    source.write_text(f"---\ntitle: {title}\nversion: v1\nfull_plan: true\nother_files_required: none\n---\n"
                      "\n## Checks\n\nBuild passed on both machines.\n\n## Questions for Chang\n\n```cards\n"
                      + json.dumps([card]) + "\n```\n")
    generate(source, directory)
    created = "2026-10-02T10:00:00Z"
    comment = dict(card, id="question-11", author="agent:review-test", created_at=created,
                   version="v1", status="open")
    comment["decision_request"] = dict(card["decision_request"], requested_at=created)
    (directory / "comments.json").write_text(json.dumps({"schema_version": 2,
        "anchors": {"d:q11": [comment]}, "archived": {}}))
    meta = json.loads((directory / "current.meta.json").read_text())
    meta["owner"] = {"owner_label": OWNER, "owner_session": "session-review", "owner_agent": "codex",
                     "target": {"terminal_name": "Content agent", "terminal_handle": "term-review"}}
    (directory / "current.meta.json").write_text(json.dumps(meta))
    return directory


def _project(resource_url=None):
    result = {"title": "Campaign", "modules": [
        {"id": "progress", "title": "Status", "kind": "progress", "items": [
            {"label": "Home speed check: #11 [CHA-182]", "status": "blocked",
             "detail": "Rehearsal passed but stopped on a test script bug.", "failed_count": 3,
             "url": "https://linear.app/test/issue/CHA-182"}]},
        {"id": "resources", "title": "Links", "kind": "links", "items": [
            {"label": "Independent image worksheet", "url": "https://example.test/images"}]},
    ]}
    if resource_url:
        result["tabs"] = [{"id": "content", "label": "Content", "url": resource_url}]
    return result


def _stored(directory):
    return json.loads((directory / "comments.json").read_text())["anchors"]["d:q11"][0]


def _contrast(locator):
    return locator.evaluate("""el => {
        const ctx = document.createElement('canvas').getContext('2d');
        const rgb = color => {
            ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = color; ctx.fillRect(0, 0, 1, 1);
            return [...ctx.getImageData(0, 0, 1, 1).data];
        };
        const over = (front, back) => {
            const alpha = front[3] / 255;
            return [...front.slice(0, 3).map((v, i) => alpha*v + (1-alpha)*back[i]), 255];
        };
        const parents = [];
        for (let p = el; p; p = p.parentElement) parents.unshift(p);
        let background = [255, 255, 255, 255];
        for (const p of parents) background = over(rgb(getComputedStyle(p).backgroundColor), background);
        const foreground = over(rgb(getComputedStyle(el).color), background);
        const lum = channels => channels.slice(0, 3).map(v => {
            v /= 255; return v <= .04045 ? v/12.92 : ((v+.055)/1.055)**2.4;
        }).reduce((sum, v, i) => sum + v*[.2126, .7152, .0722][i], 0);
        const values = [lum(foreground), lum(background)].sort((a, b) => b-a);
        return (values[0]+.05)/(values[1]+.05);
    }""")


@contextmanager
def _browser(tmp_path, directory, width=1440):
    process, base = _serve(tmp_path, directory)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": width, "height": 960})
            page.set_default_timeout(5000)
            page.goto(base, wait_until="networkidle")
            page.frame_locator("#content-frame").locator('[data-strip-item="question-11"]').wait_for()
            try:
                yield page, base
            finally:
                page.unroute_all(behavior='wait')
                browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


def _wait_decision(page, directory, verdict, text=None):
    # This waits on the actual stored result, rather than a temporary UI success label.
    for _ in range(50):
        decision = _stored(directory).get("decision", {})
        if decision.get("verdict") == verdict and (text is None or decision.get("text") == text):
            return
        page.wait_for_timeout(100)
    raise AssertionError(f"Expected {verdict} with {text!r}; stored {_stored(directory).get('decision')}")


def _serve_prefixed(tmp_path, directory, prefix):
    # Public annotation tabs share the Funnel origin, with one route per page.
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, ANNOTATE_STATE_DIR=str(tmp_path / 'state'))
    process = subprocess.Popen([sys.executable, '-m', 'agent_annotate.sync_server',
        '--slug-dir', str(directory), '--slug', 'content', '--bus-dir', str(tmp_path / 'bus'),
        '--port', str(port), '--public-base-path', prefix,
        '--local-author', 'reviewer@example.com', '--local-author-name', 'Browser Reviewer'],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    base = f'http://127.0.0.1:{port}{prefix}/'
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(base, timeout=1).close()
            return process, base
        except OSError:
            time.sleep(.05)
    process.terminate()
    process.wait(timeout=5)
    raise AssertionError('prefixed content server did not become ready')


@contextmanager
def _public_funnel_browser(tmp_path):
    from agent_annotate import cli, review_access, sync_server
    from agent_annotate.urls import page_url

    directory = _page(tmp_path)
    save_project(directory, _project())
    bus = tmp_path / 'sharing-browser'
    bus.mkdir()
    handler = sync_server.make_handler(directory, bus_dir=bus, slug='review',
        public_base_path='/page', v2_mode=True, skill_dir=sync_server.WEB_DIR)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
    public = 'https://review-ui.ts.net/page/'
    record = {'slug_dir': str(directory), 'port': server.server_port, 'transport': 'funnel', 'url': public}
    cli._save_state_for_project(bus.name, {'project': bus.name, 'slugs': {'review': record}})
    key = review_access.ensure_key(directory)
    private = page_url(record)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={'width': 1440, 'height': 960})
            page.set_default_timeout(15000)

            def forward(route):
                requested = urlsplit(route.request.url)
                headers = dict(route.request.all_headers(), Host=requested.netloc)
                target = f'http://127.0.0.1:{server.server_port}{requested.path}'
                if requested.query:
                    target += '?' + requested.query
                route.fulfill(response=route.fetch(url=target, headers=headers))

            page.route('https://review-ui.ts.net/**', forward)
            # Exercise the real authenticated endpoint and clipboard call while
            # keeping this test off the user's system clipboard.
            page.add_init_script("if (navigator.clipboard) navigator.clipboard.writeText = async value => { window.__copiedLink = value; };")
            try:
                yield page, public, private, key
            finally:
                page.unroute_all(behavior='wait')
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("surface", ["body", "rail"])
@pytest.mark.parametrize("custom", [True, False], ids=["custom", "built-in"])
def test_reverse_answer_with_explanation_and_then_answer_in_words(tmp_path, width, surface, custom):
    directory = _page(tmp_path, custom)
    with _browser(tmp_path, directory, width) as (page, _):
        if surface == "body":
            page.locator('[data-workspace-tab="progress"]').click()
            card = page.frame_locator("#content-frame").locator('[data-strip-item="question-11"]')
            choices = card.locator('.annotate-decision-btns button')
            change = card.locator('.annotate-decision-change')
            note_toggle = card.locator('.annotate-decision-note-toggle')
            note = card.locator('.annotate-decision-note-form textarea')
            say = card.locator('.annotate-decision-say')
            say_text = card.locator('textarea[placeholder="Answer in your own words…"]')
            say_submit = card.get_by_role('button', name='Send answer', exact=True)
        else:
            page.locator('[data-workspace-tab="feedback"]').click()
            card = page.locator('.citem[data-comment-id="question-11"]')
            choices = card.locator('.decision-btns button')
            change = card.locator('[data-decision-action="change"]')
            note_toggle = card.locator('[data-decision-action="note-toggle"]')
            note = card.locator('.decision-note-ta')
            say = card.locator('[data-decision-action="say"]')
            say_text = card.locator('.decision-say-ta')
            say_submit = card.locator('[data-decision-action="say-submit"]')
        choices.nth(0).click()
        _wait_decision(page, directory, 'select' if custom else 'accept')
        change.click()
        assert say.is_visible(), "Changing a choice must preserve Answer in words"
        if note_toggle.get_attribute('aria-expanded') != 'true':
            note_toggle.click()
        explanation = "Wait until both reviewers have confirmed the wording."
        note.fill(explanation)
        choices.nth(1).click()
        _wait_decision(page, directory, 'select' if custom else 'reject',
                       "Ship later\n\n" + explanation if custom else explanation)
        change.click()
        say.click()
        words = "Release after the copy review; exact time is flexible."
        say_text.fill(words)
        say_submit.click()
        _wait_decision(page, directory, 'comment', words)
        page.reload(wait_until="networkidle")
        assert words in _stored(directory)["decision"]["text"]


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width", [1440, 390])
def test_whole_card_comment_and_optional_evidence_previews(tmp_path, width):
    directory = _page(tmp_path)
    with _browser(tmp_path, directory, width) as (page, _):
        page.locator('[data-workspace-tab="progress"]').click()
        body = page.frame_locator("#content-frame").locator('[data-strip-item="question-11"]')
        body.locator('.annotate-decision-prompt').click()
        page.locator('#pop-ta').wait_for(state='visible')
        note = "Please also check the tablet layout."
        page.locator('#pop-ta').fill(note)
        page.locator('#pop-save').click()
        page.locator('#popover').wait_for(state='hidden')
        assert any(c['text'] == note for c in json.loads((directory / 'comments.json').read_text())['anchors']['d:q11'])
        page.locator('[data-workspace-tab="progress"]').click()
        body.locator('.annotate-decision-evidence-toggle').click()
        body.locator('.annotate-decision-evidence-link').first.click()
        assert 'Build passed on both machines.' in body.locator('.annotate-decision-evidence-preview').inner_text()
        page.locator('[data-workspace-tab="feedback"]').click()
        rail = page.locator('.citem[data-comment-id="question-11"]')
        rail.locator('.decision-evidence-toggle').click()
        rail.locator('.decision-evidence-link').first.click()
        assert 'Build passed on both machines.' in rail.locator('.decision-evidence-preview').inner_text()
        rail.locator('.decision-prompt').click()
        assert rail.locator('.reply-ta').evaluate('el => document.activeElement === el')


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width", [1440, 390])
def test_tabs_theme_and_noop_progress_are_persistent(tmp_path, width):
    directory = _page(tmp_path)
    save_project(directory, _project())
    with _browser(tmp_path, directory, width) as (page, _):
        def assert_legible_components():
            frame = page.frame_locator('#content-frame')
            for locator in (frame.locator('.failed-pill'), frame.locator('.annotate-decision-rec').first,
                            page.locator('#workspace-tabs [aria-selected="false"]').first,
                            page.locator('.reply-submit').first):
                assert _contrast(locator) >= 4.5, f'Low contrast text: {locator}'

        assert page.locator('html').get_attribute('data-theme') == 'dark'
        assert_legible_components()
        shell_dark = page.locator('html').evaluate('el => getComputedStyle(el).getPropertyValue("--color-base-100").trim()')
        frame_html = page.frame_locator('#content-frame').locator('html')
        assert frame_html.get_attribute('data-theme') == 'dark'
        assert shell_dark == frame_html.evaluate('el => getComputedStyle(el).getPropertyValue("--color-base-100").trim()')
        page.locator('#theme-toggle').click()
        page.reload(wait_until='networkidle')
        assert page.locator('html').get_attribute('data-theme') == 'light'
        assert frame_html.get_attribute('data-theme') == 'light'
        assert_legible_components()
        assert shell_dark != page.locator('html').evaluate('el => getComputedStyle(el).getPropertyValue("--color-base-100").trim()')
        page.locator('[data-workspace-tab="progress"]').focus()
        page.keyboard.press('Enter')
        assert page.locator('body').get_attribute('data-workspace-view') == 'progress'
        assert page.locator('[data-workspace-tab="progress"]').evaluate("""el => {
            const line = getComputedStyle(el, '::before');
            return line.content !== 'none' && parseFloat(line.width) > 0
                && parseFloat(line.borderTopWidth) > 0;
        }"""), 'The active tab must have the visible daisyUI underline'
        assert page.locator('#progress-new').is_hidden()
        page.keyboard.press('ArrowRight')
        assert page.locator('body').get_attribute('data-workspace-view') == 'feedback'
        before = (directory / 'project.json').read_bytes()
        save_project(directory, _project())
        assert (directory / 'project.json').read_bytes() == before
        page.reload(wait_until='networkidle')
        assert page.locator('#progress-new').is_hidden(), 'Reposting unchanged progress must not create new activity'
        page.locator('[data-workspace-tab="progress"]').click()
        panel = page.frame_locator('#content-frame').locator('#project-panel')
        playwright.expect(panel.locator('.failed-pill')).to_be_visible()
        assert panel.locator('.failed-pill').inner_text() == 'failed 3x'
        assert panel.locator('a[href="https://linear.app/test/issue/CHA-182"]').is_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=f'/tmp/annotate-workspace-intent-{width}.png', full_page=True)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_extra_page_is_an_embedded_tab_with_the_same_theme(tmp_path):
    directory = _page(tmp_path)
    extra_root = tmp_path / 'content'
    extra_root.mkdir()
    extra_directory = _page(extra_root, title='Content review')
    process, extra_base = _serve_prefixed(extra_root, extra_directory, '/content-tab')
    try:
        with _browser(tmp_path, directory) as (page, base):
            def forward_tab(route):
                headers = dict(route.request.headers)
                if 'origin' in headers:
                    parsed = urlsplit(extra_base)
                    headers['origin'] = f'{parsed.scheme}://{parsed.netloc}'
                response = route.fetch(url=extra_base + route.request.url.split('/content-tab/', 1)[1],
                                       headers=headers)
                route.fulfill(response=response)
            page.route('**/content-tab/**', forward_tab)
            save_project(directory, _project(base + 'content-tab/'))
            page.reload(wait_until='networkidle')
            page.locator('.citem[data-comment-id="question-11"] .decision-btn').first.click()
            _wait_decision(page, directory, 'select')
            playwright.expect(page.locator('#round-bar')).to_be_visible()
            page.locator('#theme-toggle').click()
            page.locator('[data-workspace-tab="content"]').click()
            extra = page.frame_locator('#workspace-extra-frame')
            extra.locator('#hdr-title').wait_for(state='attached')
            playwright.expect(extra.locator('#hdr-title')).to_have_text('Content review')
            assert extra.locator('.hdr-left').is_hidden()
            assert extra.locator('#owner-chip').is_hidden()
            assert extra.locator('#theme-toggle').is_hidden()
            assert extra.locator('#push-session-btn').is_visible(), 'Embedded page needs its own scoped Send feedback control'
            assert page.locator('#push-session-btn').is_hidden(), 'Primary Send feedback must not target another visible tab'
            assert page.locator('#mobile-fab').is_hidden()
            assert page.locator('#round-bar').is_hidden()
            assert extra.locator('#workspace-tabs').is_hidden()
            playwright.expect(extra.locator('html')).to_have_attribute('data-theme', 'light')
            extra.locator('.citem[data-comment-id="question-11"] .reply-ta').fill('Keep this content note while checking progress.')
            assert page.url == base
            page.locator('[data-workspace-tab="progress"]').click()
            assert page.locator('#workspace-extra').is_hidden()
            assert page.locator('#push-session-btn').is_visible()
            page.locator('[data-workspace-tab="content"]').click()
            assert extra.locator('.reply-ta').input_value() == 'Keep this content note while checking progress.'
            playwright.expect(page.locator('[data-workspace-tab="content"]')).to_be_focused()
            page.keyboard.press('Home')
            assert page.locator('body').get_attribute('data-workspace-view') == 'progress'
            page.set_viewport_size({'width': 390, 'height': 960})
            page.locator('[data-workspace-tab="progress"]').click()
            playwright.expect(page.locator('#mobile-fab')).to_be_visible()
            playwright.expect(page.locator('#round-bar')).to_be_visible()
            page.locator('[data-workspace-tab="content"]').click()
            assert page.locator('#mobile-fab').is_hidden()
            assert page.locator('#round-bar').is_hidden()
            assert extra.locator('#push-session-btn').is_visible()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_new_badges_count_changed_progress_and_unread_feedback(tmp_path):
    directory = _page(tmp_path)
    save_project(directory, _project())
    with _browser(tmp_path, directory) as (page, _):
        assert page.locator('#progress-new').inner_text() == '1', 'Static resource links are not progress updates'
        assert page.locator('#feedback-new').inner_text() == '1'
        page.locator('[data-workspace-tab="feedback"]').click()
        page.locator('#markallread-btn').click()
        page.locator('#feedback-new').wait_for(state='hidden')
        assert page.locator('.decision-btn').count() == 2, 'Reading feedback must not decide its question'
        page.locator('[data-workspace-tab="progress"]').click()
        page.locator('[data-workspace-tab="feedback"]').click()
        changed = _project()
        changed['modules'][0]['items'][0]['status'] = 'done'
        changed['modules'][0]['items'][0]['detail'] = 'Test script fixed; rehearsal passed.'
        del changed['modules'][0]['items'][0]['failed_count']
        save_project(directory, changed)
        page.reload(wait_until='networkidle')
        assert page.locator('#progress-new').inner_text() == '1'
        assert page.locator('#feedback-new').is_hidden()
        page.locator('[data-workspace-tab="progress"]').click()
        assert page.locator('#progress-new').is_hidden()


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize('width', [1440, 390])
def test_owner_breadcrumb_is_readable_in_compact_and_desktop_views(tmp_path, width):
    directory = _page(tmp_path)
    with _browser(tmp_path, directory, width) as (page, _):
        owner = page.locator('#owner-chip')
        assert owner.is_visible(), 'Reviewer must be able to identify the owning terminal on compact screens'
        disclosure = owner.locator(':scope > summary')
        if disclosure.count():
            assert disclosure.inner_text() == 'Owner: Content agent', 'Compact owner pill must show the terminal name'
            disclosure.focus()
            page.keyboard.press('Enter')
            if width <= 1160:
                page.wait_for_timeout(300)
            assert owner.locator('.owner-chip-path').evaluate("""el => {
                const r = el.getBoundingClientRect();
                const hit = document.elementFromPoint(r.left + 20, r.bottom - 12);
                return !!hit && hit.closest('.owner-chip-path') === el;
            }"""), 'The full owner breadcrumb must remain readable above the Feedback sheet'
        assert OWNER in owner.inner_text()
        if owner.evaluate('el => el.scrollWidth > el.clientWidth'):
            assert OWNER in owner.get_attribute('title'), 'Truncated owner labels must retain the full breadcrumb'
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.skipif(not CHROME.exists(), reason='Google Chrome is not installed')
def test_copy_link_preserves_private_sharing_after_address_bar_key_is_removed(tmp_path):
    with _public_funnel_browser(tmp_path) as (page, public, private, key):
        page.goto(public, wait_until='networkidle')
        assert page.locator('#copy-link-btn').is_hidden()
        assert 'private review link' in page.locator('#delivery-status').inner_text().lower()
        assert page.evaluate("async () => (await fetch('./api/share-link')).status") == 403
        page.goto(private, wait_until='domcontentloaded')
        frame = page.frame_locator('#content-frame')
        frame.locator('[data-strip-item="question-11"]').wait_for()
        playwright.expect(page).to_have_url(public)
        button = page.locator('#copy-link-btn')
        playwright.expect(button).to_be_visible()
        assert key not in page.content()
        identity = page.evaluate("async () => (await fetch('./api/identity')).json()")
        assert identity['authenticated'] is True
        page.reload(wait_until='domcontentloaded')
        playwright.expect(button).to_be_visible()
        assert page.evaluate("async () => (await fetch('./api/identity')).json()")['email'] == identity['email']
        page.locator('[data-workspace-tab="progress"]').click()
        for width in (1440, 390):
            page.set_viewport_size({'width': width, 'height': 960})
            for theme in ('dark', 'light'):
                if page.locator('html').get_attribute('data-theme') != theme:
                    page.locator('#theme-toggle').click()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                for selector in ('#copy-link-btn', '#theme-toggle', '#push-session-btn'):
                    assert page.locator(selector).evaluate("""el => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.left >= 0 && r.right <= innerWidth;
                    }"""), f'{selector} must fit in the {width}px header'
                page.mouse.move(10, 100)
                page.wait_for_timeout(250)
                page.screenshot(path=f'/tmp/annotate-sharing-{width}-{theme}.png', full_page=True)
                page.evaluate('window.__copiedLink = null')
                button.click()
                playwright.expect(button).to_have_text('Copied')
                assert page.evaluate('window.__copiedLink') == private
                assert page.url == public and key not in page.content()
                playwright.expect(button).to_have_text('Copy link', timeout=3500)
