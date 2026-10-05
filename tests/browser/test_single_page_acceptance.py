"""Accepted single-page behavior on small fixtures built inside pytest's sandbox."""

import json

import pytest
from single_page import browser_page, feedback, go, history, section
from test_card_layout import CHROME
from test_workspace_intent import _page

from agent_annotate.categories import mark_finding_fixed, publish_plan_revision, save_findings_sets
from agent_annotate.copy_state import load_copy, save_copy
from agent_annotate.project_state import save_project

playwright = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")


@pytest.fixture
def workspace(tmp_path):
    directory = _page(tmp_path)
    save_project(directory, {"title": "Acceptance", "modules": []})
    save_copy(
        directory,
        {
            "blocks": [
                {
                    "id": "hero",
                    "title": "Home hero",
                    "where": "Home hero",
                    "group": "copy",
                    "question_comment_id": "library-9",
                    "current": "r1",
                    "revisions": [
                        {
                            "id": "r1",
                            "created_at": "2026-10-01T10:00:00Z",
                            "author": {"id": "agent:copy"},
                            "status": "draft",
                            "delta": {"ops": [{"insert": "Current copy.\n"}]},
                        }
                    ],
                }
            ],
            "groups": [{"id": "copy", "label": "Copy"}],
        },
    )
    path = directory / "comments.json"
    store = json.loads(path.read_text())
    question = store["anchors"]["d:q11"][0]
    library = dict(
        question,
        id="library-9",
        number=9,
        category="library",
        anchor_id="copy:hero",
        status="user_confirmed",
        decision={
            "verdict": "comment",
            "text": "Use the approved wording.",
            "by": "reviewer@example.com",
            "ts": "2026-10-02T10:00:00Z",
        },
    )
    library["decision_request"] = {"prompt": "Which library wording?", "options": ["accept", "reject"]}
    finding = dict(
        question,
        id="finding-21",
        number=21,
        category="findings",
        anchor_id="finding:contrast",
        finding={"set": "design", "title": "Border contrast"},
        decision_request={
            "prompt": "Fix border contrast?",
            "options": [{"id": "fix", "label": "Fix it"}, {"id": "keep", "label": "Keep it"}],
        },
    )
    plan = dict(question, id="plan-31", number=31, category="plans", doc="plan:launch", anchor_id="s:launch")
    plan["decision_request"] = {"prompt": "Approve launch plan?", "options": ["accept", "reject"]}
    for item in (library, finding, plan):
        store["anchors"][item["anchor_id"]] = [item]
    path.write_text(json.dumps(store))
    save_findings_sets(directory, [{"id": "design", "label": "Design audit"}])
    publish_plan_revision(
        directory,
        "launch",
        '<!doctype html><html><head><title>Launch plan</title></head><body><div class="aa"><section data-anchor-id="s:launch"><h2>Launch</h2><p>Verify all tabs before launch.</p></section></div></body></html>',
        title="Launch plan",
    )
    attachments = directory / "attachments"
    attachments.mkdir(exist_ok=True)
    (attachments / "proof.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><rect width="20" height="20" fill="green"/></svg>'
    )
    mark_finding_fixed(
        directory,
        21,
        by="agent:builder",
        note="Contrast repaired",
        proof=[
            {"label": "Contrast image", "attachment": "proof.svg"},
            {"label": "Verification report", "url": "https://example.test/proof"},
        ],
    )
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    (state / "bus.json").write_text(
        json.dumps(
            {
                "project": "Acceptance",
                "slugs": {
                    "items-model": {
                        "slug_dir": str(directory),
                        "workspace_primary": True,
                        "url": "http://127.0.0.1/",
                    },
                    "motion-lab": {
                        "slug_dir": str(tmp_path / "lab"),
                        "title": "Motion lab",
                        "url": "https://example.test/lab",
                        "exception": {"reason": "Interactive worksheet", "parent_slug": "items-model"},
                    },
                },
            }
        )
    )
    return directory


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_tab_positions_are_identical_across_all_tabs(tmp_path, workspace, theme):
    with browser_page(tmp_path, workspace) as (page, _):
        if theme == "light":
            page.locator("#theme-toggle").click()
        positions = []
        for view in ("review", "library", "findings", "plans", "linked"):
            go(page, view)
            page.evaluate(
                "async () => {await document.fonts.ready; await new Promise(requestAnimationFrame)}"
            )
            positions.append(
                page.locator("#aa-tabs [data-view]").evaluate_all(
                    "els => els.map(e => ({tab:e.dataset.view,x:e.getBoundingClientRect().x}))"
                )
            )
        assert len(positions[0]) == 5
        assert all(p == positions[0] for p in positions)


def test_dark_borders_are_lighter_than_surfaces_in_three_places(tmp_path, workspace):
    with browser_page(tmp_path, workspace) as (page, _):
        feedback(page)
        script = """el => {
            const ctx=document.createElement('canvas').getContext('2d');
            const rgb=color => {ctx.clearRect(0,0,1,1);ctx.fillStyle=color;ctx.fillRect(0,0,1,1);
                return [...ctx.getImageData(0,0,1,1).data];};
            const over=(front,back) => {const a=front[3]/255;
                return [...front.slice(0,3).map((v,i)=>a*v+(1-a)*back[i]),255];};
            const lum=channels => channels.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;})
                .reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
            const parents=[];for(let p=el;p;p=p.parentElement) parents.unshift(p);
            let surface=[255,255,255,255];
            for(const p of parents) surface=over(rgb(getComputedStyle(p).backgroundColor),surface);
            const s=getComputedStyle(el);
            return {border:lum(over(rgb(s.borderBottomColor),surface)),surface:lum(surface),width:parseFloat(s.borderBottomWidth)};
        }"""
        for selector in (".hdr", ".drawer-hdr", ".citem[data-comment-id='question-11']"):
            values = page.locator(selector).evaluate(script)
            assert values["width"] > 0, (selector, values)
            assert values["border"] > values["surface"], (selector, values)


def test_answered_library_question_is_only_in_library(tmp_path, workspace):
    with browser_page(tmp_path, workspace) as (page, _):
        feedback(page)
        assert page.locator('#comment-list [data-comment-id="library-9"]').count() == 0
        assert "Which library wording?" not in page.locator("#comment-list").inner_text()
        go(page, "library", item="hero")
        history(page)
        assert "Use the approved wording." in page.locator("#hist-library").inner_text()
        go(page, "review")
        feedback(page)
        assert "Use the approved wording." not in page.locator("#comment-list").inner_text()


def reopen(page):
    go(page, "findings")
    page.locator('[data-f="finding-21"]').click()
    page.locator("#f-reopen").click()
    page.locator("#f-reopen-ta").fill("Still wrong on mobile")
    page.locator("#f-reopen-save").click()
    page.locator('#rail-findings [data-section="ready"]').wait_for(state="visible")


def test_fixed_finding_shows_image_and_link_and_reopen_becomes_ready(tmp_path, workspace):
    with browser_page(tmp_path, workspace) as (page, _):
        go(page, "findings")
        page.locator('[data-f="finding-21"]').click()
        image = page.locator(".fix-proof-img img")
        assert image.get_attribute("alt") == "Contrast image"
        page.wait_for_function("() => document.querySelector('.fix-proof-img img')?.naturalWidth > 0")
        assert page.locator(".fix-proof-links a").get_attribute("href") == "https://example.test/proof"
        reopen(page)
        assert "ready to send" in page.locator('#rail-findings [data-section="ready"]').inner_text().lower()
        card = json.loads((workspace / "comments.json").read_text())["anchors"]["finding:contrast"][0]
        assert card["status"] == "open" and card["round_pending"] is True
        assert "fixed" not in card and len(card["fixed_history"]) == 1


def test_exception_page_is_listed_under_linked_pages(tmp_path, workspace):
    with browser_page(tmp_path, workspace) as (page, _):
        go(page, "linked")
        link = page.locator('#linked-list a[href="https://example.test/lab"]')
        assert link.is_visible() and "Motion lab" in link.inner_text()
        assert "Interactive worksheet" in page.locator("#linked-list").inner_text()


def test_one_send_covers_every_pending_tab_and_records_one_round(tmp_path, workspace):
    with browser_page(tmp_path, workspace) as (page, base):
        feedback(page)
        page.locator('.citem[data-comment-id="question-11"] .decision-btn').first.click()
        section(page, "ready")
        go(page, "library", item="hero")
        page.locator("#sp-editor .ql-editor").fill("Changed copy.")
        page.locator("#sp-save").click()
        page.locator("#sp-edit-status").filter(has_text="Saved").wait_for()
        reopen(page)
        go(page, "plans", plan="launch")
        feedback(page)
        page.locator('.citem[data-comment-id="plan-31"] .decision-accept').click()
        section(page, "ready")
        page.locator("#send-btn:visible, #round-finish-btn:visible").first.click()
        for view in ("review", "library", "findings", "plans"):
            tab = page.locator(f'[data-sum-tab="{view}"]')
            assert tab.is_visible()
            assert tab.locator(".sp-sum-cat .badge").inner_text() == "1"
            assert tab.locator(".sum-row").count() >= 1
        assert page.locator("#sum-send-n").inner_text() == "4"
        page.locator("#round-submit-btn").click()
        page.locator("#round-confirm-backdrop").wait_for(state="hidden")
        playwright.expect(page.locator("#send-count")).to_have_text("0")
        assert all(v["pending"] == 0 for v in page.evaluate("() => AA.counts()").values())
        records = [json.loads(line) for line in (workspace / "rounds.ndjson").read_text().splitlines()]
        assert len(records) == 1
        assert {a["category"] for a in records[0]["answers"]} == {"review", "findings", "plans"}
        assert len(records[0]["edits"]) == 1 and records[0]["edits"][0]["category"] == "library"
        assert not load_copy(workspace)["blocks"][0]["revisions"][-1]["round_pending"]
        history(page)
        page.locator('[data-hist-filter="all"]').click()
        page.locator("#hist-sent-body .unified-receipt").wait_for()
        assert page.locator("#hist-sent-body .unified-receipt").count() == 1
        receipt = page.locator("#hist-sent-body .unified-receipt")
        assert receipt.get_attribute("open") is None
        receipt.locator("summary").click()
        assert all(page.locator("#hist-sent-body .hist-tag").nth(i).is_visible() for i in range(4))
        assert set(page.locator("#hist-sent-body .hist-tag").all_inner_texts()) == {
            "Review",
            "Library",
            "Findings",
            "Plans",
        }
        # A second submit has no pending work and cannot create a second round.
        result = page.evaluate(
            "async () => (await fetch('./api/rounds/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).json()"
        )
        assert result["delivery"] == "noop"
        assert len((workspace / "rounds.ndjson").read_text().splitlines()) == 1
        events = [
            json.loads(line) for line in (tmp_path / "bus" / "items-model.ndjson").read_text().splitlines()
        ]
        assert len([e for e in events if e.get("event") == "round_submitted"]) == 1
        assert len([e for e in events if e.get("event") == "session_push"]) == 1


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("width", [1440, 390])
def test_all_tabs_have_no_horizontal_scroll_or_console_errors(tmp_path, workspace, width, theme):
    with browser_page(tmp_path, workspace, width=width, height=844) as (page, base):
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        # Include initial bootstrap errors, not only errors after routing.
        page.goto(base + "#view=review", wait_until="networkidle")
        page.locator('body[data-ready="1"]').wait_for(state="attached")
        if theme == "light":
            page.locator("#theme-toggle").click()
        for view in ("review", "library", "findings", "plans", "linked"):
            go(page, view)
            if view in ("review", "plans"):
                anchor = "s:checks" if view == "review" else "s:launch"
                frame = page.frame_locator("#content-frame")
                frame.locator(f'[data-anchor-id="{anchor}"]').wait_for(state="attached")
                frame.locator("body").evaluate("() => document.fonts.ready")
            page.evaluate(
                "async () => {await document.fonts.ready; await new Promise(requestAnimationFrame)}"
            )
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), view
            feedback(page)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), view
        assert errors == []


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_phone_document_has_no_horizontal_scroll(tmp_path, workspace, theme):
    with browser_page(tmp_path, workspace, width=390, height=844) as (page, _):
        if theme == "light":
            page.locator("#theme-toggle").click()
        for view in ("review", "plans"):
            go(page, view)
            assert (
                page.frame_locator("#content-frame")
                .locator("html")
                .evaluate("el => el.scrollWidth <= innerWidth")
            ), view
