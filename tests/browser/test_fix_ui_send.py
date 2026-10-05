"""Fix-UI S1: Send reports the truth, sends what it lists, and answers keep their comments."""

import json

import pytest
from single_page import browser_page, feedback, go, history, section
from test_card_layout import CHROME
from test_single_page_acceptance import workspace  # noqa: F401
from test_workspace_intent import _page

from agent_annotate.categories import publish_plan_revision

playwright = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")

REVIEWER = "reviewer@example.com"


def _store(directory):
    return json.loads((directory / "comments.json").read_text())


def _comment(directory, cid):
    for items in _store(directory)["anchors"].values():
        for c in items:
            if c["id"] == cid:
                return c
    raise AssertionError(f"{cid} not in the store")


def _add(directory, *items):
    path = directory / "comments.json"
    store = json.loads(path.read_text())
    for item in items:
        store["anchors"].setdefault(item["anchor_id"], []).append(item)
    path.write_text(json.dumps(store))


def _rounds(directory):
    path = directory / "rounds.ndjson"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def _pushes(tmp_path):
    path = tmp_path / "bus" / "items-model.ndjson"
    events = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    return [e for e in events if e.get("event") == "session_push"]


def _review_note(directory):
    # A reviewer's own open comment, never pushed: it goes with Send's push.
    _add(
        directory,
        {
            "id": "note-1",
            "anchor_id": "s:checks",
            "text": "Check the build date.",
            "author": REVIEWER,
            "created_at": "2026-10-03T10:00:00Z",
            "version": "v1",
            "status": "open",
        },
    )


def _answer_and_open_send(page):
    feedback(page)
    page.locator('.citem[data-comment-id="question-11"] .decision-btn').first.click()
    section(page, "ready")
    playwright.expect(page.locator("#send-count")).to_have_text("2")
    page.locator("#send-btn").click()
    playwright.expect(page.locator("#sum-send-n")).to_have_text("2")


# ── UI-2: a Send that partly fails ────────────────────────────────────────
def test_ui2_push_failure_keeps_the_comment_pending_and_receipt_lists_only_the_round(tmp_path, workspace):  # noqa: F811
    _review_note(workspace)
    with browser_page(tmp_path, workspace) as (page, _):
        _answer_and_open_send(page)
        page.route("**/api/push-session*", lambda route: route.abort())
        page.locator("#round-submit-btn").click()
        playwright.expect(page.locator("#round-confirm-sub")).to_have_text("Failed to send 1 item — try again.")
        assert page.locator("#round-confirm-backdrop").is_visible()
        # The failed comment is still pending and still listed; the verdict went.
        playwright.expect(page.locator("#send-count")).to_have_text("1")
        playwright.expect(page.locator("#sum-send-n")).to_have_text("1")
        assert "Check the build date." in page.locator('[data-sum-tab="review"]').inner_text()
        assert not _comment(workspace, "note-1").get("flagged_for_session")
        assert not _comment(workspace, "question-11")["decision"].get("round_pending")
        rounds = _rounds(workspace)
        assert len(rounds) == 1
        assert [line["label"] for line in rounds[0]["receipt"]] == ["#11 · When should we release?"]
        playwright.expect(page.locator("#send-note")).to_have_text("⏳ Queued — no session listening (1)")
        receipt = page.evaluate("() => AA.send.receipts()[0]")
        assert receipt["result"] == "⏳ Queued — no session listening (1)"
        assert [it["label"] for it in receipt["items"]] == ["#11 · When should we release?"]
        # Trying again sends the rest, as a second receipt.
        page.unroute("**/api/push-session*")
        page.locator("#round-submit-btn").click()
        page.locator("#round-confirm-backdrop").wait_for(state="hidden")
        playwright.expect(page.locator("#send-count")).to_have_text("0")
        assert _comment(workspace, "note-1").get("flagged_for_session") is True
        rounds = _rounds(workspace)
        assert len(rounds) == 2
        assert "Check the build date." in rounds[1]["receipt"][0]["label"]
        history(page)
        page.locator("#hist-sent-body .unified-receipt").first.wait_for()
        texts = page.locator("#hist-sent-body .unified-receipt summary").all_inner_texts()
        # Two Sends, one line each; both were queued, and the server-side
        # record keeps that (UI-13).
        assert [t.split(" · ")[0] for t in texts] == ["⏳ Queued — no session listening (1)"] * 2


def test_ui2_round_failure_keeps_the_verdict_pending_and_receipt_lists_only_the_push(tmp_path, workspace):  # noqa: F811
    _review_note(workspace)
    with browser_page(tmp_path, workspace) as (page, _):
        _answer_and_open_send(page)
        page.route("**/api/rounds/submit*", lambda route: route.abort())
        page.locator("#round-submit-btn").click()
        playwright.expect(page.locator("#round-confirm-sub")).to_have_text("Failed to send 1 item — try again.")
        playwright.expect(page.locator("#send-count")).to_have_text("1")
        assert _comment(workspace, "question-11")["decision"]["round_pending"] is True
        assert _comment(workspace, "note-1")["flagged_for_session"] is True
        rounds = _rounds(workspace)
        assert len(rounds) == 1
        assert len(rounds[0]["receipt"]) == 1 and "Check the build date." in rounds[0]["receipt"][0]["label"]
        receipt = page.evaluate("() => AA.send.receipts()[0]")
        assert receipt["result"] == "⏳ Queued — no session listening (1)"
        assert len(receipt["items"]) == 1 and "Check the build date." in receipt["items"][0]["label"]


def test_ui2_nothing_sent_says_failed_and_records_nothing(tmp_path, workspace):  # noqa: F811
    _review_note(workspace)
    with browser_page(tmp_path, workspace) as (page, _):
        _answer_and_open_send(page)
        page.route("**/api/rounds/submit*", lambda route: route.abort())
        page.route("**/api/push-session*", lambda route: route.abort())
        page.locator("#round-submit-btn").click()
        playwright.expect(page.locator("#round-confirm-sub")).to_have_text("Failed to submit — try again.")
        playwright.expect(page.locator("#send-count")).to_have_text("2")
        assert page.locator("#round-submit-btn").is_enabled()
        assert _rounds(workspace) == []
        assert page.evaluate("() => AA.send.receipts().length") == 0


# ── UI-5: Send sends exactly what its summary lists ───────────────────────
def test_ui5_finding_answered_outside_a_send_is_listed_counted_and_pushed(tmp_path, workspace):  # noqa: F811
    _add(
        workspace,
        {
            "id": "finding-22",
            "number": 22,
            "category": "findings",
            "anchor_id": "finding:focus",
            "text": "Focus ring is missing.",
            "author": "agent:review-test",
            "created_at": "2026-10-02T10:00:00Z",
            "version": "v1",
            "status": "open",
            "finding": {"set": "design", "title": "Focus ring"},
            "decision_request": {
                "prompt": "Add a focus ring?",
                "options": [{"id": "fix", "label": "Fix it"}, {"id": "keep", "label": "Keep it"}],
                "requested_at": "2026-10-02T10:00:00Z",
            },
            "decision": {"verdict": "select", "text": "Fix it", "by": REVIEWER, "ts": "2026-10-02T11:00:00Z"},
        },
    )
    with browser_page(tmp_path, workspace) as (page, _):
        playwright.expect(page.locator("#send-count")).to_have_text("1")
        page.locator("#send-btn").click()
        tab = page.locator('[data-sum-tab="findings"]')
        assert tab.locator(".sp-sum-cat .badge").inner_text() == "1"
        assert "Focus ring" in tab.inner_text() and "Fix it" in tab.inner_text()
        assert page.locator("#sum-send-n").inner_text() == "1"
        page.locator("#round-submit-btn").click()
        page.locator("#round-confirm-backdrop").wait_for(state="hidden")
        playwright.expect(page.locator("#send-count")).to_have_text("0")
        pushes = _pushes(tmp_path)
        assert len(pushes) == 1 and pushes[0]["comment_ids"] == ["finding-22"]
        receipt = _rounds(workspace)[-1]["receipt"]
        assert len(receipt) == 1 and receipt[0]["cat"] == "findings"
        assert "Focus ring" in receipt[0]["label"] and receipt[0]["answer"] == "Fix it"


# ── UI-14: Discard pending shows the answer the agent has ─────────────────
def test_ui14_discard_shows_the_sent_answer_again(tmp_path):
    directory = _page(tmp_path)
    with browser_page(tmp_path, directory) as (page, _):
        feedback(page)
        card = page.locator('.citem[data-comment-id="question-11"]')
        card.locator(".decision-btn").first.click()
        section(page, "ready")
        page.locator("#send-btn").click()
        page.locator("#round-submit-btn").click()
        page.locator("#round-confirm-backdrop").wait_for(state="hidden")
        card.locator('[data-decision-action="change"]').click()
        card.locator(".decision-btn").nth(1).click()
        section(page, "ready")
        playwright.expect(card.locator(".ans")).to_have_text("Ship later")
        page.locator("#send-btn").click()
        page.locator("#round-discard-btn").click()
        page.locator("#round-confirm-backdrop").wait_for(state="hidden")
        assert _comment(directory, "question-11")["decision"]["text"] == "Ship now"
        playwright.expect(card.locator(".ans")).to_have_text("Ship now")


# ── UI-15: changing an option keeps the comment sent with it ──────────────
def test_ui15_changing_the_option_keeps_the_earlier_comment(tmp_path):
    directory = _page(tmp_path)
    with browser_page(tmp_path, directory) as (page, _):
        feedback(page)
        card = page.locator('.citem[data-comment-id="question-11"]')
        card.locator(".decision-say-ta").fill("Both builds passed.")
        card.locator(".decision-btn").first.click()
        section(page, "ready")
        assert _comment(directory, "question-11")["decision"]["text"] == "Ship now\n\nBoth builds passed."
        card.locator('[data-decision-action="change"]').click()
        assert card.locator(".decision-say-ta").input_value() == ""
        card.locator(".decision-btn").nth(1).click()
        section(page, "ready")
        playwright.expect(card.locator(".ans")).to_contain_text("Ship later")
        assert _comment(directory, "question-11")["decision"]["text"] == "Ship later\n\nBoth builds passed."
        # A new comment replaces the earlier one.
        card.locator('[data-decision-action="change"]').click()
        card.locator(".decision-say-ta").fill("Wait for the copy review.")
        card.locator(".decision-btn").first.click()
        section(page, "ready")
        assert _comment(directory, "question-11")["decision"]["text"] == "Ship now\n\nWait for the copy review."


# ── UI-26: the Plans tab counts the revision on screen (final/) ───────────
def test_ui26_plans_tab_counts_follow_an_older_revision(tmp_path, workspace):  # noqa: F811
    publish_plan_revision(
        workspace,
        "launch",
        '<!doctype html><html><head><title>Launch plan</title></head><body><div class="aa"><section data-anchor-id="s:launch"><h2>Launch</h2><p>Verify all tabs before launch, twice.</p></section></div></body></html>',
        title="Launch plan",
    )
    for n in (1, 2):
        _add(
            workspace,
            {
                "id": f"plan-note-{n}",
                "category": "plans",
                "doc": "plan:launch",
                "anchor_id": "s:launch",
                "text": f"Plan note {n}.",
                "author": "agent:planner",
                "created_at": "2026-10-02T10:00:00Z",
                "version": "v1",
                "status": "open",
            },
        )
    with browser_page(tmp_path, workspace) as (page, _):
        tab = page.locator('#aa-tabs [data-view="plans"]')
        go(page, "plans", plan="launch")
        latest = tab.get_attribute("aria-label")
        go(page, "plans", plan="launch", v="v1")
        playwright.expect(page.locator("#view-hd-sub-doc")).to_contain_text("v1")
        own = page.evaluate("() => AnnotateDocs.counts('plans')")
        assert own["unread"] == 3 and own["needs"] == 1
        playwright.expect(tab).to_have_attribute("aria-label", "Plans, 1 needs you · 3 unread")
        assert latest != "Plans, 1 needs you · 3 unread"
        go(page, "plans", plan="launch", v="v2")
        playwright.expect(tab).to_have_attribute("aria-label", latest)
