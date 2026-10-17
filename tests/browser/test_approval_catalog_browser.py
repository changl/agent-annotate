"""FLD-like sandbox only: real clicks, real Send, and the existing Plans UI."""
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urljoin

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from single_page import CHROME, feedback, go, history, ready, section  # noqa: E402
from test_decision_verdicts import _serve  # noqa: E402


def _card(version):
    return {"id": "design-" + version, "anchor_id": "d:q1", "number": 1, "version": version,
            "author": "agent:test", "created_at": "2026-10-16T10:00:00Z", "status": "open",
            "text": "Approve the FLD routing design?",
            "decision_request": {"prompt": "Approve the FLD routing design?", "context": "The proposed screen and routing contract are shown together.",
                "options": [{"id": "accept", "label": "Approve design"}, {"id": "changes", "label": "Request changes"}],
                "evidence": [{"anchor": "s:design", "label": "Routing design"}]}}


def _publish(directory, version, name):
    (directory / "assets").mkdir(exist_ok=True)
    (directory / "assets/routing.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="220" viewBox="0 0 900 220">'
        '<rect width="900" height="220" rx="18" fill="#e8efff"/><rect x="35" y="65" width="200" height="85" rx="12" fill="#284bb8"/>'
        '<rect x="350" y="65" width="200" height="85" rx="12" fill="#284bb8"/><rect x="665" y="65" width="200" height="85" rx="12" fill="#284bb8"/>'
        f'<g fill="white" font-family="sans-serif" font-size="22" text-anchor="middle"><text x="135" y="115">Review</text>'
        f'<text x="450" y="115">{name}</text><text x="765" y="115">Plans</text></g>'
        '<path d="M245 108 H330 M560 108 H645" stroke="#284bb8" stroke-width="5"/></svg>')
    html = (f'<!doctype html><html><head><title>FLD sandbox</title></head><body><main class="aa"><h1>FLD routing — sandbox</h1>'
            f'<section data-anchor-id="s:design"><h2>{name}</h2><p>The exact reviewed design includes this screen, routing rules and evidence.</p>'
            '<img src="assets/routing.svg" alt="Routing design" style="width:100%;max-width:900px">'
            '<ul><li>Review the complete proposal.</li><li>Send the decision once.</li><li>Keep the previous approved design in history.</li></ul></section>'
            '<div data-anchor-id="d:q1"></div></main><script type="application/json" id="anchor-registry-data">'
            '{"s:design":{"name":"Routing design","grp":"Design"},"d:q1":{"name":"Approval","grp":"Decision"}}</script></body></html>')
    (directory / f"content/{version}.html").write_text(html)
    meta = json.loads((directory / "current.meta.json").read_text())
    meta["current"] = version
    if not any(h["version"] == version for h in meta["history"]):
        meta["history"].append({"version": version})
    (directory / "current.meta.json").write_text(json.dumps(meta))
    store = json.loads((directory / "comments.json").read_text())
    for c in store["anchors"].get("d:q1", []):
        c["status"] = "resolved_in_version"
        c["resolved_in_version"] = version
    store["anchors"].setdefault("d:q1", []).append(_card(version))
    (directory / "comments.json").write_text(json.dumps(store))


def _send(page):
    page.locator("#send-btn").click()
    page.locator("#round-submit-btn").click()
    try:
        page.locator("#round-confirm-backdrop").wait_for(state="hidden")
    except playwright.TimeoutError as exc:
        raise AssertionError(page.locator("#round-confirm-backdrop").inner_text()) from exc


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_sandbox_approval_selection_history_changes_and_retry(tmp_path):
    process, base, directory = _serve(tmp_path, card=_card("v0"), anchor="d:q1")
    output = Path(os.environ.get("ANNOTATE_APPROVAL_SCREENSHOTS", tmp_path / "screenshots"))
    output.mkdir(parents=True, exist_ok=True)
    try:
        _publish(directory, "v1", "Initial routing")
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(8000)
            page.goto(base, wait_until="networkidle")
            ready(page)
            feedback(page)
            page.locator('.citem[data-comment-id="design-v1"] .decision-accept').click()
            _send(page)
            catalog = page.request.get(base + "api/categories").json()["plans"]
            assert len(catalog) == 1
            identifier = catalog[0]["id"]
            _publish(directory, "v2", "One-step routing")
            page.goto(base + "#view=review", wait_until="networkidle")
            page.reload(wait_until="networkidle")
            ready(page)
            feedback(page)
            page.screenshot(path=str(output / "review-before.png"), full_page=True)
            go(page, "plans", plan=identifier)
            frame = page.frame_locator("#content-frame")
            playwright.expect(frame.locator("h2", has_text="Initial routing")).to_be_visible()
            page.screenshot(path=str(output / "plans-before.png"), full_page=True)
            go(page, "review")
            # The in-document card uses the same evidence token as the rail.
            frame.locator('.annotate-decision-btn', has_text="Approve design").click()
            _send(page)
            page.screenshot(path=str(output / "review-after.png"), full_page=True)
            go(page, "plans", plan=identifier)
            playwright.expect(frame.locator("h2", has_text="One-step routing")).to_be_visible()
            playwright.expect(page.locator("#unified-version-banner")).to_be_hidden()
            playwright.expect(frame.locator("main")).to_contain_text("Chosen: Approve design")
            assert frame.locator("time[data-decided-time]").inner_text() != "Decided"
            assert "T" not in frame.locator("time[data-decided-time]").inner_text()
            page.screenshot(path=str(output / "plans-after.png"), full_page=True)
            current = page.request.get(base + "api/plans/" + identifier).json()
            assert current["current"] == "v2" and len(current["history"]) == 2
            assert not current["history"][-1]["evidence_incomplete"]
            history(page)
            page.locator('#vrail-body-plans .vrow[data-version="v1"]').click()
            playwright.expect(frame.locator("h2", has_text="Initial routing")).to_be_visible()
            assert "Superseded" in frame.locator("header").inner_text()
            old_image = frame.locator("img").get_attribute("src")
            assert "Initial routing" in page.request.get(urljoin(base, old_image)).text()
            page.screenshot(path=str(output / "plans-history.png"), full_page=True)
            _publish(directory, "v3", "Experimental routing")
            page.goto(base + "#view=review", wait_until="networkidle")
            page.reload(wait_until="networkidle")
            ready(page)
            feedback(page)
            section(page, "needs")
            target = page.locator('.citem[data-comment-id="design-v3"]')
            target.locator(".decision-say-ta").fill("Keep the approved one-step design")
            target.locator(".decision-changes").click()
            _send(page)
            for _ in range(2):
                assert page.request.post(base + "api/rounds/submit", data={}).ok
            go(page, "plans", plan=identifier)
            playwright.expect(frame.locator("h2", has_text="One-step routing")).to_be_visible()
            assert len(page.request.get(base + "api/plans/" + identifier).json()["history"]) == 2
            page.screenshot(path=str(output / "plans-after-changes.png"), full_page=True)
            selection = _card("v3")
            selection.update(id="rollout-v3", anchor_id="d:q2", number=2, text="When should routing roll out?")
            selection["decision_request"] = {"prompt": "When should routing roll out?", "evidence": [{"anchor": "s:design"}],
                "options": [{"id": "later", "label": "Next month", "consequence": "Defer the rollout"}]}
            response = page.request.post(base + "api/comments", data=selection, headers={"X-Annotate-Agent": "agent:test"})
            assert response.status == 201
            selected_id = response.json()["id"]
            page.goto(base + "#view=review", wait_until="networkidle")
            page.reload(wait_until="networkidle")
            ready(page)
            feedback(page)
            section(page, "needs")
            page.locator(f'.citem[data-comment-id="{selected_id}"] [data-option-id="later"]').click()
            _send(page)
            catalog = page.request.get(base + "api/categories").json()["plans"]
            decided = next(item for item in catalog if item.get("kind") == "Decided")
            go(page, "plans", plan=decided["id"])
            playwright.expect(frame.locator("header")).to_contain_text("Decided: Next month")
            playwright.expect(frame.locator("header")).to_contain_text("Defer the rollout")
            assert page.locator("#view-hd-plan optgroup").evaluate_all("els => els.map(e => e.label)") == ["Approved", "Decided"]
            page.screenshot(path=str(output / "plans-decided.png"), full_page=True)
            browser.close()
        if "ANNOTATE_APPROVAL_SCREENSHOTS" in os.environ:
            shutil.copytree(directory, output / "sandbox-page", dirs_exist_ok=True)
    finally:
        process.terminate()
        process.wait(timeout=5)
        if process.stderr:
            errors = process.stderr.read()
            (output / "sandbox-server.log").write_text(errors)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("reload", [False, True])
def test_same_card_can_be_accepted_selected_and_accepted_again(tmp_path, reload):
    process, base, directory = _serve(tmp_path, card=_card("v0"), anchor="d:q1")
    try:
        _publish(directory, "v1", "Routing correction")
        path = directory / "comments.json"
        store = json.loads(path.read_text())
        comment = store["anchors"]["d:q1"][-1]
        comment["decision_request"]["options"].insert(1, {"id": "keep-current", "label": "No", "consequence": "Keep current routing"})
        path.write_text(json.dumps(store))
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(8000)
            page.goto(base, wait_until="networkidle")
            ready(page)
            for index, selector in enumerate([".decision-accept", '[data-option-id="keep-current"]', ".decision-accept"], 1):
                if index > 1 and reload:
                    page.reload(wait_until="networkidle")
                    ready(page)
                feedback(page)
                if index > 1:
                    section(page, "done" if index == 2 else "waiting")
                    page.locator('.citem[data-comment-id="design-v1"] .change-btn').click()
                page.locator('.citem[data-comment-id="design-v1"] ' + selector).click()
                _send(page)
                plan = page.request.get(base + "api/categories").json()["plans"][0]
                assert len(plan["history"]) == index and plan["current"] == f"v{index}"
                assert plan["kind"] == ("Decided" if index == 2 else "Approved")
            go(page, "plans", plan=plan["id"])
            frame = page.frame_locator("#content-frame")
            playwright.expect(frame.locator("main")).to_contain_text("Chosen: Approve design")
            playwright.expect(frame.locator("header")).to_contain_text("Approved · Current")
            if "ANNOTATE_APPROVAL_SCREENSHOTS" in os.environ:
                output = Path(os.environ["ANNOTATE_APPROVAL_SCREENSHOTS"])
                page.screenshot(path=str(output / ("plans-corrected-reload.png" if reload else "plans-corrected-same-tab.png")), full_page=True)
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
