"""Past reviews stay intact, ticket links are real, and dark surfaces are distinct."""

import json
import urllib.request

import pytest
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
    project = {"title": "Rebex", "issue_links": {"CHA-160": ISSUE}, "tabs": [
        {"id": "copy", "label": "Copy", "kind": "copy"},
        {"id": "details", "label": "Details", "kind": "document"}],
        "modules": [{"id": "status", "title": "Status", "kind": "progress", "items": [
            {"label": "Home speed CHA-160", "status": "done", "detail": "CHA-160 checked on both machines."},
            {"label": "Inspect CHA-160", "status": "in_progress", "url": "https://example.test/report"}]},
            {"id": "notes", "title": "Notes", "kind": "notes", "items": [{"text": "CHA-160 is ready; CHA-999 has no supplied link."}]}]}
    save_project(directory, project)
    revision = {"id": "old", "created_at": "2026-10-01T09:00:00Z", "status": "draft",
                "author": {"id": "agent:copy"}, "delta": {"ops": [{"insert": "Earlier copy.\n"}]}}
    current = dict(revision, id="current", status="approved", delta={"ops": [{"insert": "Ready for the next trip.\n"}]})
    save_copy(directory, {"blocks": [{"id": "hero", "title": "Home hero", "current": "current", "revisions": [revision, current]},
                                      {"id": "footer", "title": "Footer", "current": "current", "revisions": [current]}]})
    process, base = _serve(tmp_path, directory)
    _request(base, "api/comments/question-11/decision", {"verdict": "comment", "text": "Keep the original wording for CHA-160.", "defer_push": True}, reviewer=True)
    _request(base, "api/rounds/submit", {"version": "v1", "note": "Original layout approved; CHA-160."}, reviewer=True)
    source = tmp_path / "v2.md"
    source.write_text("---\ntitle: Current campaign\nversion: v2\nfull_plan: true\nother_files_required: none\n---\n"
                      "\n## Checks\n\nCurrent layout has changed.\n\n| Item | State |\n|---|---|\n| Header | Checked |\n| Footer | Ready |\n")
    generate(source, directory)
    meta = json.loads((directory / "current.meta.json").read_text())
    meta.update(current="v2", history=[dict(meta["history"][0], ts="2026-10-01T09:00:00Z", label="Original layout"),
                                       {"version": "v2", "ts": "2026-10-02T09:00:00Z", "label": "Current layout"}])
    (directory / "current.meta.json").write_text(json.dumps(meta))
    store = json.loads((directory / "comments.json").read_text())
    card = store["anchors"]["d:q11"][0]
    card.update(version="v2", status="open", text="Decide CHA-160; unknown CHA-999 stays text.",
                decision_request={"prompt": "Ship CHA-160?", "context": "Compare CHA-160 with CHA-999. CHA-160X and XCHA-160 stay literal. <img src=x onerror=alert(1)>",
                                  "options": [{"id": "accept", "label": "Approve"}, {"id": "reject", "label": "Revise"}], "recommendation": "accept"})
    card.pop("decision", None)
    card.pop("replies", None)
    extra = dict(card, id="question-12", number=12, anchor_id="d:q12", text="Second open question", decision_request={"prompt": "Confirm the footer?", "options": ["accept", "reject"]})
    store["anchors"]["d:q12"] = [extra]
    (directory / "comments.json").write_text(json.dumps(store))
    historical = directory / "versions" / "v1.html"
    historical.write_text(historical.read_text().replace('<div class="aa">', '<div class="aa"><p>Recorded work for CHA-160.</p><pre>CHA-160 code remains literal.</pre><script id="archive-script">parent.__archiveRan=true; fetch("./api/comments",{method:"POST",body:"{}"});</script>', 1))
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
            page.set_default_timeout(10000)
            history_requests, posts, errors = [], [], []
            page.on("request", lambda request: history_requests.append(request.url) if request.url.endswith("/api/history") else None)
            page.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base, wait_until="networkidle")
            playwright.expect(page.locator("#hdr-title")).to_have_text("Rebex")
            if theme == "light":
                page.locator("#theme-toggle").click()
            page.frame_locator("#content-frame").locator('[data-anchor-id="s:checks"]').wait_for(state="attached")
            card = page.locator('.citem[data-comment-id="question-11"]')
            card.locator(".decision-prompt").click()
            reply = card.locator(".reply-ta")
            draft = "Keep this explanation while reviewing past rounds."
            reply.fill(draft)
            page.wait_for_timeout(500)
            assert not history_requests, "History has no background fetches"
            prompt_link = card.locator(".decision-prompt .ticket-link")
            assert prompt_link.get_attribute("href") == ISSUE
            assert prompt_link.get_attribute("rel") == "noopener noreferrer"
            assert card.locator(".decision-context .ticket-link").count() == 1
            assert card.locator(".decision-context img").count() == 0
            assert "CHA-999" in card.locator(".decision-context").inner_text()
            page.context.route("https://linear.app/**", lambda route: route.fulfill(status=200, content_type="text/html", body="<title>Linear issue</title>"))
            with page.expect_popup() as popup_info:
                prompt_link.click()
            popup = popup_info.value
            popup.wait_for_load_state()
            assert popup.url == ISSUE
            popup.close()
            assert reply.input_value() == draft
            assert page.locator("body").get_attribute("data-workspace-view") == "feedback"
            page.mouse.move(2, 2)
            page.wait_for_timeout(200)
            page.screenshot(path=f"/tmp/annotate-rounds-feedback-{width}-{theme}.png", full_page=True)
            if theme == "dark":
                assert card.evaluate("el => getComputedStyle(el).backgroundColor") != page.locator("#drawer-body").evaluate("el => getComputedStyle(el).backgroundColor")
            assert _contrast(card.locator(".decision-prompt")) >= 4.5

            page.locator('[data-workspace-tab="progress"]').click()
            status = page.locator('[data-module="status"]')
            assert status.locator("li").first.locator(".ticket-link").count() == 2
            assert status.locator("li").first.locator(".ticket-link").first.get_attribute("href") == ISSUE
            assert status.locator("li").first.locator(".project-detail .ticket-link").get_attribute("href") == ISSUE
            assert status.locator("li").nth(1).locator("a").get_attribute("href") == "https://example.test/report"
            assert page.locator("#project-panel a a").count() == 0
            if page.locator('[data-module="notes"]').get_attribute('open') is None:
                page.locator('[data-module="notes"] > summary').click()
            assert page.locator('[data-module="notes"] .ticket-link').count() == 1
            page.wait_for_timeout(200)
            page.screenshot(path=f"/tmp/annotate-rounds-progress-{width}-{theme}.png", full_page=True)
            page.locator('[data-workspace-tab="copy"]').click()
            page.locator(".copy-block").wait_for()
            page.locator(".copy-history > summary").click()
            page.locator(".copy-history-entry > summary").click()
            page.wait_for_timeout(200)
            page.screenshot(path=f"/tmp/annotate-rounds-copy-{width}-{theme}.png", full_page=True)
            page.locator('[data-workspace-tab="details"]').click()
            current_frame = page.frame_locator("#content-frame")
            current_frame.locator("table").wait_for()
            page.wait_for_timeout(200)
            page.screenshot(path=f"/tmp/annotate-rounds-details-{width}-{theme}.png", full_page=True)
            current_src = page.locator("#content-frame").get_attribute("src")
            saved = (directory / "comments.json").read_bytes()
            seen = (directory / "seen.json").read_bytes()
            read_state = (directory / "read-state.json").read_bytes()
            before_posts = len(posts)

            page.locator('[data-workspace-tab="rounds"]').click()
            chooser = page.locator("#rounds-select")
            chooser.locator("option").first.wait_for(state="attached")
            assert len(history_requests) == 1
            assert "Keep the original wording for CHA-160." in page.locator("#rounds-review").inner_text()
            assert "Original layout approved" in page.locator("#rounds-review").inner_text()
            assert page.locator("#rounds-review .decision-btn").count() == 0
            page.get_by_role("button", name="Document as recorded").click()
            historical_frame = page.frame_locator("#rounds-frame")
            historical_frame.locator(".aa-page-title").wait_for()
            assert historical_frame.locator(".aa-page-title").inner_text() == "Original campaign"
            assert "Read-only snapshot" in page.locator("#rounds-selection-meta").inner_text()
            assert historical_frame.locator("html").get_attribute("data-theme") == theme
            archive_link = historical_frame.locator('p .ticket-link').first
            assert archive_link.get_attribute('href') == ISSUE
            assert historical_frame.locator('pre .ticket-link').count() == 0
            with page.expect_popup() as archive_popup_info:
                archive_link.click()
            archive_popup = archive_popup_info.value
            archive_popup.wait_for_load_state()
            assert archive_popup.url == ISSUE
            archive_popup.close()
            assert page.evaluate("window.__archiveRan") is None
            page.evaluate("""() => window.dispatchEvent(new MessageEvent('message', {
                origin: location.origin, source: document.getElementById('rounds-frame').contentWindow,
                data: {type:'annotate:pin-click',anchorId:'s:checks',anchorLabel:'Archive spoof'}
            }))""")
            assert page.locator("#popover").is_hidden()
            assert len(posts) == before_posts
            assert (directory / "comments.json").read_bytes() == saved
            assert (directory / "seen.json").read_bytes() == seen
            assert (directory / "read-state.json").read_bytes() == read_state
            assert page.locator("#content-frame").get_attribute("src") == current_src
            page.wait_for_timeout(200)
            page.screenshot(path=f"/tmp/annotate-rounds-history-{width}-{theme}.png", full_page=True)
            current_option = chooser.locator('optgroup[label="Documents"] option').filter(has_text="v2")
            chooser.select_option(current_option.get_attribute("value"))
            playwright.expect(historical_frame.locator(".aa-page-title")).to_have_text("Current campaign")
            assert "No answers recorded" in page.locator("#rounds-review").inner_text()
            assert page.locator("#rounds-review .history-answer").count() == 0
            page.locator('[data-workspace-tab="feedback"]').click()
            assert reply.input_value() == draft
            page.locator('[data-workspace-tab="rounds"]').click()
            assert len(history_requests) == 1, "Opening the same history again makes no maintenance loop"
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
        meta_path = directory / "current.meta.json"
        meta = json.loads(meta_path.read_text())
        for version in meta["history"]:
            version.update(source_page="rebex-build", source_version="v39" if version["version"] == "v1" else "v40")
        meta["history"].append({"version":"v3", "ts":"2026-10-03T09:00:00Z", "label":"Missing legacy snapshot"})
        meta_path.write_text(json.dumps(meta))
        store_path = directory / "comments.json"
        store = json.loads(store_path.read_text())
        card = store["anchors"]["d:q12"][0]
        card["target"] = {"source_page":"rebex-build", "source_number":12}
        card["decision_history"] = [{"verdict":"accept", "by":"reviewer@example.com",
                                     "ts":"2026-10-01T11:00:00Z", "text":"Keep the original footer."}]
        store_path.write_text(json.dumps(store))
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width":1440,"height":960})
            page.goto(base, wait_until="networkidle")
            page.locator('[data-workspace-tab="rounds"]').click()
            chooser = page.locator("#rounds-select")
            old = chooser.locator('optgroup[label="Documents"] option').filter(has_text="v39")
            old.wait_for(state="attached")
            chooser.select_option(old.get_attribute("value"))
            assert "Recorded answers during this version" in page.locator("#rounds-review").inner_text()
            assert "Keep the original footer." in page.locator("#rounds-review").inner_text()
            assert page.locator("#rounds-review .history-answer").count() == 1
            assert page.locator("#rounds-review .history-answer .citem-num").inner_text() == "#12"
            assert page.locator("#rounds-review .history-answer-heading strong").count() == 0, "Old question text is not guessed from the new request"
            page.frame_locator("#rounds-frame").locator(".aa-page-title").wait_for()
            before = page.locator("#rounds-frame").get_attribute("src")
            missing = chooser.locator('optgroup[label="Documents"] option').filter(has_text="unavailable")
            chooser.select_option(missing.get_attribute("value"))
            assert page.locator("#rounds-document").is_hidden()
            assert "not retained" in page.locator("#rounds-status").inner_text()
            assert page.locator("#rounds-frame").get_attribute("src") == before
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
        pending.update(status="user_confirmed", decision={"verdict":"accept", "text":"Saved footer draft", "by":"reviewer@example.com", "round_pending":True, "ts":"2026-10-02T10:00:00Z"})
        waiting = dict(pending, id="waiting", number=13, anchor_id="d:q13", status="open",
                       author="reviewer@example.com", decision=None, decision_request=None)
        done = dict(pending, id="done", number=14, anchor_id="d:q14", decision=dict(pending["decision"], round_pending=False))
        store["anchors"]["d:q13"] = [waiting]
        store["anchors"]["d:q14"] = [done]
        path.write_text(json.dumps(store))
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width":390,"height":960})
            page.goto(base, wait_until="networkidle")
            for kind, expected in (("review",2),("waiting",1),("done",1)):
                chip = page.locator(f'[data-filter="{kind}"]')
                chip.click()
                assert int(chip.locator(".chip-n").inner_text()) == expected
                assert page.locator("#comment-list .citem").count() == expected
                if kind != "review":
                    assert page.locator('.citem[data-comment-id="question-12"]').count() == 0
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
            page = browser.new_page(viewport={"width":1440,"height":960})
            requests = []
            page.on("request", lambda request: requests.append(request.url) if request.url.endswith("/api/history") else None)
            page.goto(base, wait_until="networkidle")
            page.locator('[data-workspace-tab="rounds"]').click()
            page.locator('#rounds-select option').first.wait_for(state="attached")
            assert len(requests) == 1
            page.locator('[data-workspace-tab="details"]').click()
            page.locator('#mobile-version-select').select_option("v1")
            playwright.expect(page.frame_locator('#content-frame').locator('.aa-page-title')).to_have_text("Original campaign")
            page.locator('[data-workspace-tab="feedback"]').click()
            page.locator('.citem[data-comment-id="question-11"] .decision-accept').click()
            page.locator('#round-finish-btn').click()
            page.locator('#round-submit-btn').click()
            page.locator('#round-confirm-backdrop').wait_for(state="hidden")
            assert len(requests) == 1, "Submitting a review does not start history polling"
            page.locator('[data-workspace-tab="rounds"]').click()
            playwright.expect(page.locator('#rounds-select optgroup[label="Submitted reviews"] option')).to_have_count(2)
            assert len(requests) == 2
            recorded = [json.loads(line) for line in (directory / 'rounds.ndjson').read_text().splitlines()]
            assert recorded[-1]['version'] == 'v1'
            assert recorded[-1]['answers'][0]['prompt'] == 'Ship CHA-160?'
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
