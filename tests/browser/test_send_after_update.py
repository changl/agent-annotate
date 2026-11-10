"""A new publication cannot strand feedback typed on the preceding version."""

import json
import urllib.request
from copy import deepcopy

import pytest
from single_page import CHROME, feedback, ready, section
from test_explicit_send_browser import sandbox_page
from test_workspace_intent import _page

from agent_annotate.pagegen import generate
from agent_annotate.review_versions import fingerprint, read_draft
from agent_annotate.store import write_json

playwright = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
TEXT = "Feedback typed before the page update; the reviewer never retypes it."


def publish_next(tmp_path, directory, base, keep):
    source = tmp_path / "review.md"
    text = source.read_text().replace("version: v1", "version: v2")
    if not keep:
        text = text[:text.index("```cards")]
    source.write_text(text)
    generate(source, directory)
    draft = read_draft(directory, "v2")
    draft.update(verified=True, fingerprint=fingerprint(directory, "v2"))
    write_json(directory / ".review-drafts/v2.json", draft)
    cards = json.loads((directory / "versions/v2.cards.json").read_text())
    body = {"items": [dict(c, version="v2") for c in cards], "idempotency": "anchor",
            "publish_version": {"version": "v2", "preview": draft["preview"]}}
    request = urllib.request.Request(base + "api/comments/batch", data=json.dumps(body).encode(),
                                    headers={"X-Annotate-Agent": "agent:review-test", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 200


def cards(directory):
    return [c for items in json.loads((directory / "comments.json").read_text())["anchors"].values() for c in items]


def open_send(page, width):
    if width == 390:
        page.evaluate("() => window.AnnotateDocs.setMobileSheetOpen(false)")
        page.locator("#round-finish-btn").click()
    else:
        page.locator("#send-btn").click()


@pytest.mark.parametrize("width", [1440, 390], ids=["desktop", "phone"])
@pytest.mark.parametrize("keep", [True, False], ids=["same-number", "card-gone"])
@pytest.mark.parametrize("draft", ["composer", "saved-note", "saved-answer", "reply"])
def test_feedback_survives_publication_and_reaches_owner(tmp_path, monkeypatch, width, keep, draft):
    directory = _page(tmp_path)
    if draft == "reply":
        store = json.loads((directory / "comments.json").read_text())
        store["anchors"]["d:q11"][0].update(status="addressed_by_agent", response_text="The agent answered; the reviewer is following up.")
        (directory / "comments.json").write_text(json.dumps(store))
    with sandbox_page(tmp_path, monkeypatch, ["input_accepted"], directory=directory) as (page, directory, _, sends):
        page.set_viewport_size({"width": width, "height": 960})
        feedback(page)
        card = page.locator('#comment-list [data-comment-id="question-11"]')
        # Follow-up notes are saved on a previously sent choice (as on Rebex).
        if draft in ("composer", "saved-note"):
            card.locator(".decision-btn").first.click()
            open_send(page, width)
            page.locator("#round-submit-btn").click()
            page.locator("#round-confirm-backdrop").wait_for(state="hidden")
            section(page, "waiting")
            card.locator('[data-action="open-card"]').click()
        if draft == "reply":
            section(page, "done")
            card.locator(".citem-line-q").click()
            box = card.locator('[data-reply-for="question-11"]')
        else:
            box = card.locator('[data-decision-say-ta="question-11"]')
        box.fill(TEXT)
        if draft == "saved-note":
            card.locator('[data-note-action="add"]').click()
            playwright.expect(box).to_have_value("")
        elif draft == "saved-answer":
            card.locator('[data-note-action="add"]').click()
            page.wait_for_function("() => window.AnnotateDocs.comments().find(c => c.id === 'question-11').decision?.round_pending")
        base = page.url.split("#")[0]
        publish_next(tmp_path, directory, base, keep)
        # Agent resolution commonly accompanies the publication. Do it through
        # the real route, without exposing the saved draft to the agent.
        request = urllib.request.Request(base + "api/comments/question-11", method="PUT",
            data=json.dumps({"status": "resolved_in_version", "resolved_in_version": "v2",
                             "resolution_anchor_id": "s:checks"}).encode(),
            headers={"X-Annotate-Agent": "agent:review-test", "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 200
        page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        playwright.expect(page.locator("#aa-fresh .aa-fresh-v")).to_have_text("v2")
        if width == 390:
            page.evaluate("() => window.AnnotateDocs.setMobileSheetOpen(false)")
        page.locator("#aa-fresh").click()
        page.wait_for_function("() => document.querySelector('#content-frame').dataset.version === 'v2'")
        # A reload must keep local drafts as well as server-saved ones.
        page.reload(wait_until="networkidle")
        ready(page)
        playwright.expect(page.locator("#send-count")).to_have_text("1")
        playwright.expect(page.locator("#send-btn")).to_be_enabled()
        playwright.expect(page.locator("#round-finish-btn")).to_be_enabled()
        open_send(page, width)
        playwright.expect(page.locator("#round-confirm-backdrop")).to_contain_text(TEXT)
        before = len(sends)
        page.locator("#round-submit-btn").click()
        page.locator("#round-confirm-backdrop").wait_for(state="hidden")
        assert len(sends) == before + 1
        all_cards = cards(directory)
        target = next(c for c in all_cards if c["version"] == ("v2" if keep else "v1") and c.get("number") == 11)
        assert any(TEXT in r["text"] and r.get("sent_at") for r in target.get("replies", []))
        rounds = [json.loads(line) for line in (directory / "rounds.ndjson").read_text().splitlines()]
        assert TEXT in json.dumps(rounds[-1]["answers"])
        assert target["id"] in [a["comment_id"] for a in rounds[-1]["answers"]]
        playwright.expect(page.locator("#send-count")).to_have_text("0")
        # A second manual Send cannot redeliver the carried draft.
        page.reload(wait_until="networkidle")
        ready(page)
        playwright.expect(page.locator("#send-btn")).to_be_disabled()


def test_carried_text_answer_does_not_leave_its_superseded_choice_pending(tmp_path, monkeypatch):
    directory = _page(tmp_path)
    store = json.loads((directory / "comments.json").read_text())
    card = store["anchors"]["d:q11"][0]
    card["agent_snapshot"] = deepcopy(card)
    author, ts = "reviewer@example.com", "2026-11-10T01:00:00Z"
    card["decision_history"] = [{"verdict": "select", "text": "Ship now", "by": author, "ts": ts, "round_pending": True}]
    card["decision"] = {"verdict": "comment", "text": TEXT, "by": author, "ts": ts, "round_pending": True}
    card["replies"] = [{"author": author, "ts": ts, "text": text, "sent_at": None}
                       for text in ["☑ Selected: Ship now", "💬 Answer in words: " + TEXT]]
    (directory / "comments.json").write_text(json.dumps(store))
    with sandbox_page(tmp_path, monkeypatch, ["input_accepted"], directory=directory) as (page, _, _, sends):
        publish_next(tmp_path, directory, page.url.split("#")[0], True)
        page.reload(wait_until="networkidle")
        ready(page)
        playwright.expect(page.locator("#send-count")).to_have_text("1")
        open_send(page, 1440)
        page.locator("#round-submit-btn").click()
        page.locator("#round-confirm-backdrop").wait_for(state="hidden")
        assert len(sends) == 1
        playwright.expect(page.locator("#send-count")).to_have_text("0")
