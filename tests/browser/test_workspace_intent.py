"""Reviewer outcomes: one workspace, quiet updates and reversible answers."""

import json
import threading
from contextlib import contextmanager
from urllib.parse import urlsplit

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from single_page import feedback, history, ready, section  # noqa: E402
from test_card_layout import CHROME, _serve  # noqa: E402

from agent_annotate.pagegen import generate  # noqa: E402
from agent_annotate.project_state import save_project  # noqa: E402

OWNER = "Projects > Rebex > Campaign > Content agent [term-review]"


def _page(tmp_path, custom=True, title="Campaign review"):
    directory = tmp_path / "review"
    options = (
        [{"id": "now", "label": "Ship now"}, {"id": "later", "label": "Ship later"}]
        if custom
        else [{"id": "accept", "label": "Approve"}, {"id": "reject", "label": "Revise"}]
    )
    card = {
        "number": 11,
        "anchor_id": "d:q11",
        "text": "Choose the release time.",
        "decision_request": {
            "prompt": "When should we release?",
            "context": "Both builds passed.",
            "recommendation": options[0]["id"],
            "options": options,
            "evidence": [{"anchor": "s:checks:p1", "label": "Build result"}],
        },
    }
    source = tmp_path / "review.md"
    source.write_text(
        f"---\ntitle: {title}\nversion: v1\nfull_plan: true\nother_files_required: none\n---\n"
        "\n## Checks\n\nBuild passed on both machines.\n\n## Questions for Chang\n\n```cards\n"
        + json.dumps([card])
        + "\n```\n"
    )
    generate(source, directory)
    created = "2026-10-02T10:00:00Z"
    comment = dict(
        card, id="question-11", author="agent:review-test", created_at=created, version="v1", status="open"
    )
    comment["decision_request"] = dict(card["decision_request"], requested_at=created)
    (directory / "comments.json").write_text(
        json.dumps({"schema_version": 2, "anchors": {"d:q11": [comment]}, "archived": {}})
    )
    meta = json.loads((directory / "current.meta.json").read_text())
    meta["owner"] = {
        "owner_label": OWNER,
        "owner_session": "session-review",
        "owner_agent": "codex",
        "target": {"terminal_name": "Content agent", "terminal_handle": "term-review"},
    }
    (directory / "current.meta.json").write_text(json.dumps(meta))
    return directory


def _project(resource_url=None):
    result = {
        "title": "Campaign",
        "modules": [
            {
                "id": "progress",
                "title": "Status",
                "kind": "progress",
                "items": [
                    {
                        "label": "Home speed check: #11 [CHA-182]",
                        "status": "blocked",
                        "detail": "Rehearsal passed but stopped on a test script bug.",
                        "failed_count": 3,
                        "url": "https://linear.app/test/issue/CHA-182",
                    }
                ],
            },
            {
                "id": "resources",
                "title": "Links",
                "kind": "links",
                "items": [{"label": "Independent image worksheet", "url": "https://example.test/images"}],
            },
        ],
    }
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
            ready(page)
            feedback(page)
            page.frame_locator("#content-frame").locator('[data-anchor-id="s:checks"]').wait_for(
                state="attached"
            )
            try:
                yield page, base
            finally:
                page.unroute_all(behavior="wait")
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


@contextmanager
def _public_funnel_browser(tmp_path):
    from agent_annotate import cli, review_access, sync_server
    from agent_annotate.urls import page_url

    directory = _page(tmp_path)
    save_project(directory, _project())
    bus = tmp_path / "sharing-browser"
    bus.mkdir()
    handler = sync_server.make_handler(
        directory,
        bus_dir=bus,
        slug="review",
        public_base_path="/page",
        v2_mode=True,
        skill_dir=sync_server.WEB_DIR,
    )
    server = sync_server.ReviewHTTPServer(("127.0.0.1", 0), handler)
    public = "https://review-ui.ts.net/page/"
    record = {"slug_dir": str(directory), "port": server.server_port, "transport": "funnel", "url": public}
    cli._save_state_for_project(bus.name, {"project": bus.name, "slugs": {"review": record}})
    key = review_access.ensure_key(directory)
    private = page_url(record)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.set_default_timeout(15000)

            def forward(route):
                requested = urlsplit(route.request.url)
                headers = dict(route.request.all_headers(), Host=requested.netloc)
                target = f"http://127.0.0.1:{server.server_port}{requested.path}"
                if requested.query:
                    target += "?" + requested.query
                route.fulfill(response=route.fetch(url=target, headers=headers))

            page.route("https://review-ui.ts.net/**", forward)
            # Exercise the real authenticated endpoint and clipboard call while
            # keeping this test off the user's system clipboard.
            page.add_init_script(
                "if (navigator.clipboard) navigator.clipboard.writeText = async value => { window.__copiedLink = value; };"
            )
            try:
                yield page, public, private, key
            finally:
                page.unroute_all(behavior="wait")
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("entry", ["tab", "direct_link"])
@pytest.mark.parametrize("custom", [True, False], ids=["custom", "built-in"])
def test_reverse_answer_with_explanation_and_then_answer_in_words(tmp_path, width, entry, custom):
    directory = _page(tmp_path, custom)
    with _browser(tmp_path, directory, width) as (page, base):
        if entry == "direct_link":
            page.goto(base + "#view=review", wait_until="networkidle")
            ready(page)
            feedback(page)
        card = page.locator('.citem[data-comment-id="question-11"]')
        choices = card.locator(".decision-btns button")
        change = card.locator('[data-decision-action="change"]')
        note = card.locator(".decision-say-ta")
        choices.nth(0).click()
        _wait_decision(page, directory, "select" if custom else "accept")
        section(page, "ready")
        if custom:
            playwright.expect(card.locator(".ans")).to_have_text("Ship now")
        change.click()
        if custom:
            assert "Ship now" in card.locator(".decision-changing-note").inner_text()
        explanation = "Wait until both reviewers have confirmed the wording."
        note.fill(explanation)
        choices.nth(1).click()
        _wait_decision(
            page,
            directory,
            "select" if custom else "reject",
            "Ship later\n\n" + explanation if custom else explanation,
        )
        section(page, "ready")
        assert explanation in _stored(directory)["decision"]["text"]
        change.click()
        words = "Release after the copy review; exact time is flexible."
        note.fill(words)
        page.locator("#send-btn:visible, #round-finish-btn:visible").first.click()
        page.locator("#round-submit-btn").click()
        _wait_decision(page, directory, "comment", words)
        page.reload(wait_until="networkidle")
        ready(page)
        section(page, "waiting")
        playwright.expect(card.locator(".ans")).to_have_text(words)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width", [1440, 390])
def test_whole_card_comment_and_optional_evidence_previews(tmp_path, width):
    directory = _page(tmp_path)
    with _browser(tmp_path, directory, width) as (page, _):
        card = page.locator('.citem[data-comment-id="question-11"]')
        card.locator(".decision-evidence-toggle").click()
        card.locator(".decision-evidence-link").first.click()
        assert "Build passed on both machines." in card.locator(".decision-evidence-preview").inner_text()
        card.locator(".decision-evidence-goto").click()
        frame = page.frame_locator("#content-frame")
        back = frame.locator(".annotate-back-pill")
        back.wait_for()
        assert frame.locator('[data-anchor-id="s:checks:p1"]').is_visible()
        back.click()
        card.locator(".decision-prompt").click()
        feedback(page)
        note = "Please also check the tablet layout."
        card.locator(".decision-say-ta").fill(note)
        page.locator("#send-btn:visible, #round-finish-btn:visible").first.click()
        page.locator("#round-submit-btn").click()
        _wait_decision(page, directory, "comment", note)
        assert any(item["text"].endswith(note) for item in _stored(directory)["replies"])


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width", [1440, 390])
def test_tabs_theme_and_noop_progress_are_persistent(tmp_path, width):
    directory = _page(tmp_path)
    save_project(directory, _project())
    with _browser(tmp_path, directory, width) as (page, _):
        page.evaluate("() => AnnotateDocs.setMobileSheetOpen(false)")
        frame_html = page.frame_locator("#content-frame").locator("html")
        for theme in ("dark", "light"):
            page.evaluate("() => AnnotateDocs.setMobileSheetOpen(false)")
            if page.locator("html").get_attribute("data-theme") != theme:
                page.locator("#theme-toggle").click()
            page.reload(wait_until="networkidle")
            ready(page)
            playwright.expect(frame_html).to_have_attribute("data-theme", theme)
            shell_color = page.locator("html").evaluate(
                'el => getComputedStyle(el).getPropertyValue("--color-base-100").trim()'
            )
            assert shell_color == frame_html.evaluate(
                'el => getComputedStyle(el).getPropertyValue("--color-base-100").trim()'
            )
            feedback(page)
            assert _contrast(page.locator(".decision-rec-badge").first) >= 4.5
            history(page)
            panel = page.locator("#project-panel-review")
            module = panel.locator('[data-module="progress"]')
            if module.get_attribute("open") is None:
                module.locator("summary").click()
            assert panel.locator(".failed-pill").inner_text() == "failed 3x"
            assert _contrast(panel.locator(".failed-pill")) >= 4.5
            assert panel.locator('a[href="https://linear.app/test/issue/CHA-182"]').is_visible()
        before = (directory / "project.json").read_bytes()
        save_project(directory, _project())
        assert (directory / "project.json").read_bytes() == before
        feedback(page)
        page.locator("#tab-feedback").focus()
        page.keyboard.press("ArrowRight")
        assert page.locator("#tab-documents").get_attribute("aria-selected") == "true"
        page.keyboard.press("ArrowRight")
        assert page.locator("#tab-history").get_attribute("aria-selected") == "true"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_extra_page_is_listed_in_documents(tmp_path):
    directory = _page(tmp_path)
    resource = "https://example.test/content/"
    save_project(directory, _project(resource))
    with _browser(tmp_path, directory) as (page, _):
        card = page.locator('.citem[data-comment-id="question-11"]')
        card.locator(".decision-say-ta").fill("Keep this note while checking reference content.")
        page.locator("#tab-documents").click()
        link = page.locator("#documents-body a").filter(has_text="Content")
        assert link.get_attribute("href") == resource
        assert link.get_attribute("target") == "_blank"
        assert link.get_attribute("rel") == "noopener noreferrer"
        page.context.route(
            resource, lambda route: route.fulfill(body="<p>Reference content</p>", content_type="text/html")
        )
        with page.expect_popup() as popup_info:
            link.click()
        popup_info.value.close()
        feedback(page)
        assert (
            card.locator(".decision-say-ta").input_value()
            == "Keep this note while checking reference content."
        )


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width", [1440, 390])
def test_owner_breadcrumb_is_readable_in_compact_and_desktop_views(tmp_path, width):
    directory = _page(tmp_path)
    with _browser(tmp_path, directory, width) as (page, _):
        page.evaluate("() => AnnotateDocs.setMobileSheetOpen(false)")
        page.locator("#who-btn").click()
        owner = page.locator("#owner-chip")
        assert owner.is_visible()
        assert OWNER in owner.inner_text()
        if owner.evaluate("el => el.scrollWidth > el.clientWidth"):
            assert OWNER in owner.get_attribute("title")
        assert owner.evaluate(
            "el => { const r=el.getBoundingClientRect(); return r.left >= 0 && r.right <= innerWidth; }"
        )
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_copy_link_preserves_private_sharing_after_address_bar_key_is_removed(tmp_path):
    with _public_funnel_browser(tmp_path) as (page, public, private, key):
        page.goto(public, wait_until="networkidle")
        assert page.locator("#copy-link-btn").is_hidden()
        assert "private review link" in page.locator("#delivery-status").inner_text().lower()
        assert page.evaluate("async () => (await fetch('./api/share-link')).status") == 403
        page.goto(private, wait_until="networkidle")
        ready(page)
        assert key not in page.content()
        identity = page.evaluate("async () => (await fetch('./api/identity')).json()")
        assert identity["authenticated"] is True
        page.reload(wait_until="networkidle")
        ready(page)
        assert (
            page.evaluate("async () => (await fetch('./api/identity')).json()")["email"] == identity["email"]
        )
        button = page.locator("#copy-link-btn")
        for width in (1440, 390):
            page.set_viewport_size({"width": width, "height": 960})
            for theme in ("dark", "light"):
                if page.locator("html").get_attribute("data-theme") != theme:
                    page.locator("#theme-toggle").click()
                if page.locator("#who-panel").is_hidden():
                    page.locator("#who-btn").click()
                assert button.is_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.evaluate("window.__copiedLink = null")
                button.click()
                playwright.expect(button).to_have_text("Copied")
                assert page.evaluate("window.__copiedLink") == private
                assert key not in page.content()
                playwright.expect(button).to_have_text("Copy link", timeout=3500)
