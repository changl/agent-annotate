"""Past reviews stay intact, ticket links are real, and dark surfaces are distinct."""

import json
import urllib.request

import pytest
from single_page import feedback, go, history, ready, section
from test_card_layout import CHROME, _serve
from test_workspace_intent import _contrast, _page

from agent_annotate.copy_state import save_copy
from agent_annotate.pagegen import generate
from agent_annotate.project_state import save_project

playwright = pytest.importorskip("playwright.sync_api")

ISSUE = "https://linear.app/chang/issue/CHA-160/home-speed-check"


def _request(base, path, payload, *, reviewer=False):
    headers = {"Content-Type": "application/json"}
    if reviewer:
        headers["Origin"] = base.rstrip("/")
    else:
        headers["X-Annotate-Agent"] = "agent:rounds-test"
    request = urllib.request.Request(base + path, data=json.dumps(payload).encode(), headers=headers)
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def _fixture(tmp_path):
    directory = _page(tmp_path, title="Original campaign")
    meta = json.loads((directory / "current.meta.json").read_text())
    meta.pop("owner", None)
    meta["history"][0].update(ts="2026-10-01T09:00:00Z", label="Original layout")
    (directory / "current.meta.json").write_text(json.dumps(meta))
    project = {
        "title": "Rebex",
        "issue_links": {"CHA-160": ISSUE},
        "tabs": [
            {"id": "copy", "label": "Copy", "kind": "copy"},
            {"id": "details", "label": "Details", "kind": "document"},
        ],
        "modules": [
            {
                "id": "status",
                "title": "Status",
                "kind": "progress",
                "items": [
                    {
                        "label": "Home speed CHA-160",
                        "status": "done",
                        "detail": "CHA-160 checked on both machines.",
                    },
                    {
                        "label": "Inspect CHA-160",
                        "status": "in_progress",
                        "url": "https://example.test/report",
                    },
                ],
            },
            {
                "id": "notes",
                "title": "Notes",
                "kind": "notes",
                "items": [{"text": "CHA-160 is ready; CHA-999 has no supplied link."}],
            },
        ],
    }
    save_project(directory, project)
    revision = {
        "id": "old",
        "created_at": "2026-10-01T09:00:00Z",
        "status": "draft",
        "author": {"id": "agent:copy"},
        "delta": {"ops": [{"insert": "Earlier copy.\n"}]},
    }
    current = dict(
        revision, id="current", status="approved", delta={"ops": [{"insert": "Ready for the next trip.\n"}]}
    )
    save_copy(
        directory,
        {
            "blocks": [
                {"id": "hero", "title": "Home hero", "current": "current", "revisions": [revision, current]},
                {"id": "footer", "title": "Footer", "current": "current", "revisions": [current]},
            ]
        },
    )
    process, base = _serve(tmp_path, directory)
    _request(
        base,
        "api/comments/question-11/decision",
        {"verdict": "comment", "text": "Keep the original wording for CHA-160.", "defer_push": True},
        reviewer=True,
    )
    _request(
        base,
        "api/rounds/submit",
        {"version": "v1", "note": "Original layout approved; CHA-160."},
        reviewer=True,
    )
    source = tmp_path / "v2.md"
    source.write_text(
        "---\ntitle: Current campaign\nversion: v2\nfull_plan: true\nother_files_required: none\n---\n"
        "\n## Checks\n\nCurrent layout has changed.\n\n| Item | State |\n|---|---|\n| Header | Checked |\n| Footer | Ready |\n"
    )
    generate(source, directory)
    meta = json.loads((directory / "current.meta.json").read_text())
    meta.update(
        current="v2",
        history=[
            dict(meta["history"][0], ts="2026-10-01T09:00:00Z", label="Original layout"),
            {"version": "v2", "ts": "2026-10-02T09:00:00Z", "label": "Current layout"},
        ],
    )
    (directory / "current.meta.json").write_text(json.dumps(meta))
    store = json.loads((directory / "comments.json").read_text())
    card = store["anchors"]["d:q11"][0]
    card.update(
        version="v2",
        status="open",
        text="Decide CHA-160; unknown CHA-999 stays text.",
        decision_request={
            "prompt": "Ship CHA-160?",
            "context": "Compare CHA-160 with CHA-999. CHA-160X and XCHA-160 stay literal. <img src=x onerror=alert(1)>",
            "options": [{"id": "accept", "label": "Approve"}, {"id": "reject", "label": "Revise"}],
            "recommendation": "accept",
        },
    )
    card.pop("decision", None)
    card.pop("replies", None)
    extra = dict(
        card,
        id="question-12",
        number=12,
        anchor_id="d:q12",
        text="Second open question",
        decision_request={"prompt": "Confirm the footer?", "options": ["accept", "reject"]},
    )
    store["anchors"]["d:q12"] = [extra]
    (directory / "comments.json").write_text(json.dumps(store))
    historical = directory / "versions" / "v1.html"
    historical.write_text(
        historical.read_text().replace(
            '<div class="aa">',
            '<div class="aa"><p>Recorded work for CHA-160.</p><pre>CHA-160 code remains literal.</pre><script id="archive-script">parent.__archiveRan=true; fetch("./api/comments",{method:"POST",body:"{}"});</script>',
            1,
        )
    )
    return directory, process, base


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_rounds_are_readonly_and_ticket_links_preserve_current_drafts(tmp_path, width, theme):
    directory, process, base = _fixture(tmp_path)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": width, "height": 960})
            page.set_default_timeout(5000)
            requests, errors = [], []
            page.on("request", lambda r: requests.append(r) if r.url.endswith("/api/history") else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(base + "#view=review", wait_until="networkidle")
            ready(page)
            feedback(page)
            if theme == "light":
                page.evaluate("() => AnnotateDocs.setMobileSheetOpen(false)")
                page.locator("#theme-toggle").click()
                feedback(page)
            card = page.locator('.citem[data-comment-id="question-11"]')
            draft = "Keep this explanation while reviewing past rounds."
            card.locator(".decision-say-ta").fill(draft)
            assert len(requests) == 1, "One bootstrap receipt fetch, without history polling"
            link = card.locator(".decision-prompt .ticket-link")
            assert link.get_attribute("href") == ISSUE and link.get_attribute("rel") == "noopener noreferrer"
            assert card.locator(".decision-context .ticket-link").count() == 1
            assert card.locator(".decision-context img").count() == 0
            assert "CHA-999" in card.locator(".decision-context").inner_text()
            assert "CHA-160X" in card.locator(".decision-context").inner_text()
            page.context.route(
                "https://linear.app/**",
                lambda r: r.fulfill(body="<title>Linear</title>", content_type="text/html"),
            )
            with page.expect_popup() as info:
                link.click()
            popup = info.value
            popup.wait_for_load_state()
            assert popup.url == ISSUE
            popup.close()
            assert card.locator(".decision-say-ta").input_value() == draft
            assert _contrast(card.locator(".decision-prompt")) >= 4.5
            saved = (directory / "comments.json").read_bytes()
            history(page)
            page.locator("#hist-sent-body .unified-receipt").wait_for()
            assert len(requests) == 1
            receipt = page.locator("#hist-sent-body .unified-receipt").first
            receipt.locator("summary").click()
            assert "Keep the original wording for CHA-160." in receipt.inner_text()
            assert receipt.locator(".decision-btn,textarea").count() == 0
            assert (directory / "comments.json").read_bytes() == saved
            assert page.evaluate("window.__archiveRan") is None
            status = page.locator('[data-module="status"]')
            status.locator("summary").click()
            assert status.locator("li").first.locator(".ticket-link").count() == 2
            assert (
                status.locator("li").nth(1).locator("a").get_attribute("href")
                == "https://example.test/report"
            )
            assert page.locator("#project-panel-review a a").count() == 0
            notes = page.locator('[data-module="notes"]')
            notes.locator("summary").click()
            assert notes.locator(".ticket-link").count() == 1
            feedback(page)
            assert card.locator(".decision-say-ta").input_value() == draft
            history(page)
            assert len(requests) == 1
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_recorded_version_answers_and_missing_originals_are_honest(tmp_path):
    directory, process, base = _fixture(tmp_path)
    try:
        # A receipt retains the old answer and prompt even after the current request changes.
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page()
            page.set_default_timeout(5000)
            page.goto(base + "#view=review", wait_until="networkidle")
            ready(page)
            history(page)
            receipt = page.locator("#hist-sent-body .unified-receipt").first
            receipt.wait_for()
            receipt.locator("summary").click()
            assert "Keep the original wording for CHA-160." in receipt.inner_text()
            assert "When should we release?" in receipt.inner_text()
            assert "Ship CHA-160?" not in receipt.inner_text()
            # A removed original does not erase its immutable receipt.
            (directory / "versions/v1.html").unlink()
            page.reload(wait_until="networkidle")
            ready(page)
            history(page)
            receipt.locator("summary").click()
            assert "Keep the original wording for CHA-160." in receipt.inner_text()
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_open_waiting_history_counts_match_cards_with_pending_drafts(tmp_path):
    directory, process, base = _fixture(tmp_path)
    try:
        path = directory / "comments.json"
        store = json.loads(path.read_text())
        pending = store["anchors"]["d:q12"][0]
        pending.update(
            status="user_confirmed",
            decision={
                "verdict": "accept",
                "text": "Saved footer draft",
                "by": "reviewer@example.com",
                "round_pending": True,
                "ts": "2026-10-02T10:00:00Z",
            },
        )
        waiting = dict(
            pending,
            id="waiting",
            number=13,
            anchor_id="d:q13",
            status="open",
            author="reviewer@example.com",
            decision=None,
            decision_request=None,
            flagged_for_session=True,
            flagged_at="2026-10-02T11:00:00Z",
        )
        done = dict(
            pending,
            id="done",
            number=14,
            anchor_id="d:q14",
            decision=dict(pending["decision"], round_pending=False),
        )
        store["anchors"]["d:q13"] = [waiting]
        store["anchors"]["d:q14"] = [done]
        path.write_text(json.dumps(store))
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 960})
            page.goto(base, wait_until="networkidle")
            ready(page)
            for kind, cid in [
                ("needs", "question-11"),
                ("ready", "question-12"),
                ("waiting", "waiting"),
                ("done", "done"),
            ]:
                group = section(page, kind)
                assert group.locator(".sec-hdr .badge").inner_text() == "1"
                assert group.locator(".citem").count() == 1
                assert group.locator(".citem").get_attribute("data-comment-id") == cid
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_a_new_review_refreshes_history_only_when_opened_and_records_viewed_version(tmp_path):
    directory, process, base = _fixture(tmp_path)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page()
            page.set_default_timeout(5000)
            requests = []
            page.on("request", lambda r: requests.append(r.url) if r.url.endswith("/api/history") else None)
            page.goto(base, wait_until="networkidle")
            ready(page)
            history(page)
            page.locator("#hist-sent-body .unified-receipt").wait_for()
            assert len(requests) == 1
            go(page, "review", v="v1")
            page.wait_for_function("() => document.querySelector('#content-frame').src.includes('v=v1')")
            feedback(page)
            page.locator('.citem[data-comment-id="question-11"] .decision-accept').click()
            section(page, "ready")
            page.locator("#send-btn:visible, #round-finish-btn:visible").first.click()
            page.locator("#round-submit-btn").click()
            page.locator("#round-confirm-backdrop").wait_for(state="hidden")
            history(page)
            playwright.expect(page.locator("#hist-sent-body .unified-receipt")).to_have_count(2)
            recorded = [json.loads(line) for line in (directory / "rounds.ndjson").read_text().splitlines()]
            assert recorded[-1]["version"] == "v1"
            assert recorded[-1]["answers"][0]["prompt"] == "Ship CHA-160?"
            assert len(requests) == 2
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
