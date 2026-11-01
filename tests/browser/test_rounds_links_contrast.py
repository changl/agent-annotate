"""Past reviews stay intact, ticket links are real, and dark surfaces are distinct."""

import json
import urllib.request

import pytest
from single_page import ROUNDS, feedback, go, history, ready, section, sent
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
            page.on("request", lambda r: requests.append(r.url.split("/api/history")[1]) if "/api/history" in r.url else None)
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
            assert requests == ["?latest=1"], "One bootstrap fetch of the latest round, without history polling"
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
            sent(page)
            page.locator(ROUNDS).wait_for()
            assert requests == ["?latest=1", ""], "The full list loads once, when History opens"
            receipt = page.locator(ROUNDS).first
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
            assert requests == ["?latest=1", ""]
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
            sent(page)
            receipt = page.locator(ROUNDS).first
            receipt.wait_for()
            assert "Keep the original wording for CHA-160." in receipt.inner_text()
            assert "When should we release?" in receipt.inner_text()
            assert "Ship CHA-160?" not in receipt.inner_text()
            # A removed original does not erase its immutable receipt.
            (directory / "versions/v1.html").unlink()
            page.reload(wait_until="networkidle")
            ready(page)
            history(page)
            receipt.wait_for()
            assert "Keep the original wording for CHA-160." in receipt.inner_text()
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_history_is_one_version_list_each_opening_to_what_was_sent_and_done(tmp_path):
    directory, process, base = _fixture(tmp_path)
    try:
        # The round on v1 went out before v2 was published (2026-10-02).
        rounds = directory / "rounds.ndjson"
        records = [json.loads(line) for line in rounds.read_text().splitlines()]
        rounds.write_text("".join(json.dumps(dict(r, ts="2026-10-01T12:00:00Z")) + "\n" for r in records))
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            for width, height in ((390, 844), (1440, 900)):
                page = browser.new_page(viewport={"width": width, "height": height})
                page.set_default_timeout(5000)
                page.goto(base + "#view=review", wait_until="networkidle")
                ready(page)
                history(page)
                body = page.locator("#history-body")
                # One list: no separate Sent rounds section or heading.
                assert page.locator("#hist-sent").count() == 0
                playwright.expect(body).not_to_contain_text("Sent rounds")
                rows = page.locator("#vrail-body-review .vitem")
                playwright.expect(rows).to_have_count(2)
                assert [r.get_attribute("data-version") for r in rows.all()] == ["v2", "v1"]
                assert page.locator("#vrail-body-review").get_attribute("role") == "list"
                # v1 had a round sent on it; v2 has no activity, so no chevron.
                v1, v2 = rows.nth(1), rows.nth(0)
                assert v2.locator(".vrow-toggle").count() == 0
                toggle = v1.locator(".vrow-toggle")
                panel = page.locator("#" + toggle.get_attribute("aria-controls"))
                # Collapsed by default: v1 is not the version on screen.
                playwright.expect(toggle).to_have_attribute("aria-expanded", "false")
                playwright.expect(panel).to_be_hidden()
                toggle.click()
                playwright.expect(toggle).to_have_attribute("aria-expanded", "true")
                playwright.expect(panel).to_be_visible()
                round_ = panel.locator(".vact-block:not(.vact-agent)")
                playwright.expect(round_).to_have_count(1)
                assert round_.locator(".vact-head").inner_text().startswith("Feedback · In inbox · owner delivery pending (1) · ")
                assert "Keep the original wording for CHA-160." in round_.inner_text()
                # Then what the agent did: it published v2.
                playwright.expect(panel.locator(".vact-agent .vact-head")).to_contain_text("Agent · Published v2 · Current layout")
                # Open or closed is remembered for the page.
                page.reload(wait_until="networkidle")
                ready(page)
                history(page)
                playwright.expect(toggle).to_have_attribute("aria-expanded", "true")
                toggle.click()
                playwright.expect(panel).to_be_hidden()
                # Arrow keys move between the versions; the row opens the version.
                # Only the focused version's chevron is in the Tab order.
                assert toggle.get_attribute("tabindex") == "-1"
                v2.locator(".vrow").focus()
                page.keyboard.press("ArrowDown")
                playwright.expect(v1.locator(".vrow")).to_be_focused()
                assert toggle.get_attribute("tabindex") == "0"
                page.keyboard.press("Tab")
                playwright.expect(toggle).to_be_focused()
                if width > 800:
                    v1.locator(".vrow").click()
                    page.wait_for_function("() => document.querySelector('#content-frame').src.includes('v=v1')")
                    playwright.expect(v1.locator(".vrow")).to_have_attribute("aria-current", "page")
                    playwright.expect(toggle).to_have_attribute("aria-expanded", "false")
                page.evaluate("() => localStorage.clear()")
                page.close()
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_each_sent_round_sits_under_the_version_it_was_sent_on(tmp_path):
    directory, process, base = _fixture(tmp_path)
    try:
        # A later round with no recorded version goes under the version that
        # was current at its time (v2, published 2026-10-02).
        rounds = directory / "rounds.ndjson"
        first = json.loads(rounds.read_text().splitlines()[0])
        assert first["version"] == "v1"
        bare = dict(first, id="bare", send_id="bare", ts="2026-10-03T09:00:00Z")
        bare.pop("version")
        with rounds.open("a") as out:
            out.write(json.dumps(bare) + "\n")
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            for width, height in ((390, 844), (1440, 900)):
                page = browser.new_page(viewport={"width": width, "height": height})
                page.set_default_timeout(5000)
                page.goto(base + "#view=review", wait_until="networkidle")
                ready(page)
                history(page)
                # v2 is on screen, so its activity is open by default.
                v2 = page.locator('#vrail-body-review .vitem[data-version="v2"]')
                playwright.expect(v2.locator(".vrow-toggle")).to_have_attribute("aria-expanded", "true")
                sent(page)
                playwright.expect(page.locator(ROUNDS)).to_have_count(2)
                for version in ("v1", "v2"):
                    item = page.locator(f'#vrail-body-review .vitem[data-version="{version}"]')
                    playwright.expect(item.locator(".vact-block:not(.vact-agent)")).to_have_count(1)
                    assert item.locator(".vact-head").first.inner_text().startswith(("Feedback · In inbox · owner delivery pending (", "Feedback · Sent ("))
                page.evaluate("() => localStorage.clear()")
                page.close()
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_agent_response_and_republished_versions_follow_publish_time(tmp_path):
    directory, process, base = _fixture(tmp_path)
    try:
        rounds = directory / "rounds.ndjson"
        first = json.loads(rounds.read_text().splitlines()[0])
        # The fixture's round on v1 went out after v2 was published: v2 is
        # not what the agent did in response to it.
        assert first["version"] == "v1" and first["ts"] > "2026-10-02T09:00:00Z"
        # v1 republished on 2026-10-04 (its time updates in place, so it is
        # still listed first); a round with no version on 2026-10-05 was sent
        # while v1 was live again.
        meta_path = directory / "current.meta.json"
        meta = json.loads(meta_path.read_text())
        meta["history"][0]["ts"] = "2026-10-04T09:00:00Z"
        meta_path.write_text(json.dumps(meta))
        bare = dict(first, id="bare", send_id="bare-republished", ts="2026-10-05T09:00:00Z")
        bare.pop("version")
        with rounds.open("a") as out:
            out.write(json.dumps(bare) + "\n")
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.set_default_timeout(5000)
            page.goto(base + "#view=review", wait_until="networkidle")
            ready(page)
            history(page)
            sent(page)
            v1 = page.locator('#vrail-body-review .vitem[data-version="v1"]')
            playwright.expect(v1.locator(".vact-block:not(.vact-agent)")).to_have_count(2)
            playwright.expect(v1.locator(".vact-agent")).to_have_count(0)
            assert page.locator('#vrail-body-review .vitem[data-version="v2"] .vrow-toggle').count() == 0
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_a_send_shows_under_its_version_before_the_server_record_arrives(tmp_path):
    directory, process, base = _fixture(tmp_path)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page()
            page.set_default_timeout(5000)
            page.goto(base + "#view=review&v=v1", wait_until="networkidle")
            ready(page)
            page.wait_for_function("() => document.querySelector('#content-frame').src.includes('v=v1')")
            # The full list loads when History is first opened.
            with page.expect_response(lambda r: r.url.endswith("/api/history")):
                history(page)
            feedback(page)
            page.locator('.citem[data-comment-id="question-11"] .decision-accept').click()
            section(page, "ready")
            # History cannot refetch: only this visit's Send is known.
            page.route("**/api/history*", lambda route: route.abort())
            page.locator("#send-btn:visible, #round-finish-btn:visible").first.click()
            page.locator("#round-submit-btn").click()
            page.locator("#round-confirm-backdrop").wait_for(state="hidden")
            history(page)
            sent(page)
            v1 = page.locator('#vrail-body-review .vitem[data-version="v1"]')
            playwright.expect(v1.locator(".vact-block:not(.vact-agent)")).to_have_count(2)
            assert page.locator('#vrail-body-review .vitem[data-version="v2"] .vrow-toggle').count() == 0
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
            sent(page)
            page.locator(ROUNDS).wait_for()
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
            playwright.expect(page.locator(ROUNDS)).to_have_count(2)
            recorded = [json.loads(line) for line in (directory / "rounds.ndjson").read_text().splitlines()]
            assert recorded[-1]["version"] == "v1"
            assert recorded[-1]["answers"][0]["prompt"] == "Ship CHA-160?"
            assert len(requests) == 2
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
