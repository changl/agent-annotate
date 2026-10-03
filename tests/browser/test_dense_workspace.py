"""Feedback is the usable first surface; reference material stays readable."""

import json

import pytest
from test_card_layout import CHROME, _serve
from test_workspace_intent import _page, _project, _serve_prefixed, _wait_decision

from agent_annotate.project_state import save_project

playwright = pytest.importorskip("playwright.sync_api")


def _workspace(tmp_path):
    directory = _page(tmp_path, title="Rebex decisions")
    project = _project()
    project["title"] = "Rebex"
    save_project(directory, project)
    store = json.loads((directory / "comments.json").read_text())
    answered = dict(store["anchors"]["d:q11"][0], id="answered-old", number=1,
                    anchor_id="d:q1", text="Previously approved.", status="user_confirmed",
                    decision={"verdict": "accept", "by": "reviewer@example.com", "ts": "2026-10-01T09:00:00Z"})
    answered["decision_request"] = dict(answered["decision_request"], prompt="Earlier decision")
    store["anchors"]["d:q1"] = [answered]
    # Open questions from previous versions remain actionable in this workspace.
    store["anchors"]["d:q11"][0]["version"] = "v0"
    (directory / "comments.json").write_text(json.dumps(store))
    return directory


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_feedback_first_dense_workspace(tmp_path, width, theme):
    directory = _workspace(tmp_path)
    process, base = _serve(tmp_path, directory)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": width, "height": 960})
            page.set_default_timeout(5000)
            page.goto(base, wait_until="networkidle")
            if theme == "light":
                page.locator("#theme-toggle").click()
            playwright.expect(page.locator("#hdr-title")).to_have_text("Rebex")
            assert page.locator("body").get_attribute("data-workspace-view") == "feedback"
            assert page.locator("#content-frame").is_hidden()
            assert page.locator("#vrail").is_hidden()
            assert page.locator("#drawer").bounding_box()["width"] >= width - 2
            card = page.locator('.citem[data-comment-id="question-11"]')
            assert card.is_visible()
            assert card.bounding_box()["y"] < 150, "The open decision must be immediately visible"
            assert page.locator(".citem").count() == 1, "Prior decisions belong in History"
            assert page.locator("#push-session-counter").inner_text() == "0"
            assert page.locator("#push-session-btn").is_disabled(), "An unanswered agent question is not reviewer feedback"
            card.locator('[data-feedback-id="question-11"]').click()
            playwright.expect(page).to_have_url(base + "#feedback=question-11")
            page.locator('.citem.hl[data-comment-id="question-11"]').wait_for()
            rec = card.locator(".decision-btn.is-recommended")
            assert rec.evaluate("el => getComputedStyle(el).borderLeftColor") == rec.evaluate("""el => {
                const x = document.createElement('span'); x.style.color = 'var(--color-success)';
                document.body.appendChild(x); const color = getComputedStyle(x).color; x.remove(); return color;
            }""")
            say = card.locator(".decision-say")
            before = say.evaluate("el => getComputedStyle(el).backgroundColor")
            say.hover()
            assert say.evaluate("el => getComputedStyle(el).backgroundColor") != before
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.mouse.move(2, 2)
            page.screenshot(path=f"/tmp/annotate-dense-feedback-{width}-{theme}.png", full_page=True)

            # Changing an answer still allows a text explanation and preserves it.
            rec.click()
            _wait_decision(page, directory, "select")
            # A saved draft belongs only in Open, and each chip matches its cards.
            assert page.locator('.chip-review .chip-n').inner_text() == '1'
            page.locator('[data-filter="waiting"]').click()
            assert page.locator('.chip-waiting .chip-n').inner_text() == '0'
            assert page.locator('.citem').count() == 0
            page.locator('[data-filter="done"]').click()
            assert page.locator('.chip-done .chip-n').inner_text() == '1'
            assert page.locator('.citem').count() == 1
            assert page.locator('.citem').first.get_attribute('data-comment-id') == 'answered-old'
            page.locator('[data-filter="review"]').click()
            assert page.locator('.citem').count() == 1
            card.locator('[data-decision-action="change"]').click()
            card.locator(".decision-note-ta").fill("Wait for the copy review.")
            card.locator(".decision-btn").nth(1).click()
            _wait_decision(page, directory, "select", "Ship later\n\nWait for the copy review.")
            card.locator('[data-decision-action="change"]').click()
            say.click()
            card.locator(".decision-say-ta").fill("Ship after the final wording is approved.")
            card.locator('[data-decision-action="say-submit"]').click()
            _wait_decision(page, directory, "comment", "Ship after the final wording is approved.")
            card.locator(".decision-prompt").click()
            reply = card.locator(".reply-ta")
            assert reply.evaluate("el => document.activeElement === el")
            reply.fill("Please also check the tablet layout.")
            page.wait_for_timeout(500)  # The existing draft debounce is 400ms.
            page.reload(wait_until="networkidle")
            card.locator(".feedback-reply > summary").click()
            assert reply.input_value() == "Please also check the tablet layout."
            card.locator('[data-action="reply"]').click()
            playwright.expect(reply).to_have_value("")
            store = json.loads((directory / "comments.json").read_text())
            assert any(item["text"] == "Please also check the tablet layout." for item in store["anchors"]["d:q11"][0]["replies"])

            page.locator('[data-workspace-tab="progress"]').click()
            assert page.locator("#project-panel").is_visible()
            assert page.locator("#content-frame").is_hidden()
            assert page.locator("#drawer").is_hidden()
            assert page.locator("#project-panel .failed-pill").inner_text() == "failed 3x"
            assert page.locator("#hdr-title").inner_text() == "Rebex"
            page.screenshot(path=f"/tmp/annotate-dense-progress-{width}-{theme}.png", full_page=True)
            page.locator('[data-workspace-tab="feedback"]').click()
            page.locator('[data-filter="done"]').click()
            assert page.locator('.citem[data-comment-id="answered-old"]').is_visible()
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width", [1440, 390])
def test_reference_tab_scrolls_tables_and_has_no_duplicate_feedback(tmp_path, width):
    directory = _workspace(tmp_path)
    extra_root = tmp_path / "reference"
    extra_root.mkdir()
    reference = _page(extra_root, title="Reference")
    content = reference / "versions" / "v1.html"
    table = "<table><tr>" + "".join(f"<th>Reference column {i}</th>" for i in range(8)) + "</tr><tr>" + "".join(f"<td>Readable complete value {i}</td>" for i in range(8)) + "</tr></table>"
    content.write_text(content.read_text().replace('<div class="aa">', '<div class="aa"><a href="#d:q11">Open decision #11</a>' + table, 1))
    reference_process, reference_base = _serve_prefixed(extra_root, reference, "/reference")
    process, base = _serve(tmp_path, directory)
    project = _project(base + "reference/")
    project["title"] = "Rebex"
    save_project(directory, project)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": width, "height": 960})
            page.set_default_timeout(5000)
            def forward(route):
                response = route.fetch(url=reference_base + route.request.url.split("/reference/", 1)[1])
                route.fulfill(response=response)
            page.route("**/reference/**", forward)
            page.goto(base, wait_until="networkidle")
            playwright.expect(page.locator("#hdr-title")).to_have_text("Rebex")
            page.locator('[data-workspace-tab="content"]').click()
            shell = page.frame_locator("#workspace-extra-frame")
            frame = shell.frame_locator("#content-frame")
            frame.locator("table").wait_for()
            assert shell.locator("#drawer").is_hidden()
            assert shell.locator(".hdr").is_hidden()
            assert frame.locator('[data-anchor-id="d:q11"]').is_hidden()
            assert frame.locator(".annotate-decision-strip").count() == 0
            wrap = frame.locator(".annotate-table-scroll").first
            assert wrap.is_visible()
            assert frame.locator("td").first.evaluate("el => parseFloat(getComputedStyle(el).paddingTop)") <= 4
            if width == 390:
                assert wrap.evaluate("el => el.scrollWidth > el.clientWidth")
                wrap.evaluate("el => { el.scrollLeft = el.scrollWidth; }")
                assert wrap.evaluate("el => el.scrollLeft") > 0
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            frame.locator("td").first.click()
            assert shell.locator("#popover").is_hidden()
            page.screenshot(path=f"/tmp/annotate-dense-reference-{width}.png", full_page=True)
            frame.get_by_role("link", name="Open decision #11").click()
            playwright.expect(page.locator("body")).to_have_attribute("data-workspace-view", "feedback")
            assert page.locator('.citem.hl[data-comment-id="question-11"]').is_visible()
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
        reference_process.terminate()
        reference_process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width", [1440, 390])
def test_copy_is_native_formatted_and_keeps_revision_history(tmp_path, width):
    from agent_annotate.copy_state import load_copy, save_copy

    directory = _workspace(tmp_path)
    project = _project()
    project["title"] = "Rebex"
    project["tabs"] = [{"id": "copy", "label": "Copy", "kind": "copy"}]
    save_project(directory, project)
    save_copy(directory, {"blocks": [{"id": "home-hero", "title": "Home hero", "current": "current",
        "revisions": [
            {"id": "previous", "created_at": "2026-10-01T10:00:00Z", "author": {"id": "agent:copy"},
             "status": "draft", "delta": {"ops": [{"insert": "Previous copy.\n"}]}},
            {"id": "current", "created_at": "2026-10-02T10:00:00Z", "author": {"id": "agent:copy"},
             "status": "approved", "delta": {"ops": [{"insert": "Current copy.", "attributes": {"bold": True}}, {"insert": "\n"}]}}
        ]}]})
    process, base = _serve(tmp_path, directory)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": width, "height": 960})
            page.set_default_timeout(5000)
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base, wait_until="networkidle")
            playwright.expect(page.locator("#hdr-title")).to_have_text("Rebex")
            page.locator('[data-workspace-tab="copy"]').click()
            root = page.locator("#copy-workspace")
            playwright.expect(root.locator(".copy-document strong")).to_have_text("Current copy.")
            assert page.locator("#main-workspace").is_hidden()
            assert page.locator("#workspace-extra").is_hidden()
            assert root.locator(".copy-history").get_attribute("open") is None
            for theme in ("dark", "light"):
                if page.locator("html").get_attribute("data-theme") != theme:
                    page.locator("#theme-toggle").click()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                page.screenshot(path=f"/tmp/annotate-dense-copy-{width}-{theme}.png", full_page=True)
            root.get_by_role("button", name="Revise", exact=True).click()
            editor = root.get_by_role("textbox", name="Edit Home hero")
            editor.fill("A clearer proposal.")
            editor.press("ControlOrMeta+a")
            root.get_by_role("button", name="Italic", exact=True).click()
            root.get_by_role("button", name="Propose change", exact=True).click()
            root.locator(".copy-proposal[open]").wait_for()
            data = load_copy(directory)["blocks"][0]
            assert data["current"] == "current"
            assert len(data["revisions"]) == 3
            assert any(op.get("attributes", {}).get("italic") for op in data["revisions"][-1]["delta"]["ops"])
            page.reload(wait_until="networkidle")
            playwright.expect(root.locator(".copy-document strong")).to_have_text("Current copy.")
            assert root.locator(".copy-history").get_attribute("open") is None
            assert not errors
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
