"""Send dialog (Chang, 2026-10-31): general feedback open at the top, Not in this Send newest first,
and every part still present. WebKit with the iPad Pro 11 profile."""

import json

import pytest
from test_keep_drafts import _directory
from test_lighter_browser import _ipad

from agent_annotate.categories import publish_plan_revision

playwright = pytest.importorskip("playwright.sync_api")

ME = "reviewer@example.com"
DIALOG = "#round-confirm-backdrop"


def _cards(tmp_path):
    """question-11 (unanswered) plus: 12 pending, 13 answered early and sent last, 14 answered and sent
    between, 16 unanswered; and one unsent reviewer comment."""
    directory = _directory(tmp_path)
    path = directory / "comments.json"
    store = json.loads(path.read_text())
    base = store["anchors"]["d:q11"][0]

    def card(n, **extra):
        return dict(base, id=f"question-{n}", number=n, **extra)

    store["anchors"]["d:q11"] += [
        card(12, decision={"verdict": "now", "text": None, "ts": "2026-10-02T10:50:00Z", "by": ME, "round_pending": True}),
        card(13, decision={"verdict": "now", "text": None, "ts": "2026-10-02T10:05:00Z", "by": ME},
             flagged_for_session=True, flagged_at="2026-10-02T10:40:00Z"),
        card(14, decision={"verdict": "later", "text": None, "ts": "2026-10-02T10:20:00Z", "by": ME},
             flagged_for_session=True, flagged_at="2026-10-02T10:21:00Z"),
        card(16),
    ]
    store["anchors"]["s:checks"] = [{
        "id": "note-card", "anchor_id": "s:checks", "anchor_label": "Checks", "text": "Say which machines ran it.",
        "author": ME, "created_at": "2026-10-02T10:45:00Z", "version": "v1", "status": "open",
        "flagged_for_session": False, "replies": [],
    }]
    path.write_text(json.dumps(store))
    publish_plan_revision(directory, "tester-tracking", "<h1>Tester tracking</h1>", title="Tester tracking")
    return directory


def _open(page):
    page.evaluate("window.AA.send.open()")
    page.locator(f"{DIALOG} #sum-gf-ta").wait_for()


def test_general_feedback_box_is_open_at_the_top_and_saves_the_draft(tmp_path):
    with _ipad(tmp_path, _cards(tmp_path)) as (page, _, _history, _fonts):
        _open(page)
        box = page.locator(f"{DIALOG} #sum-gf-ta")
        # Open with no button, between the summary line and the lists, and not focused (no iPad keyboard).
        assert page.locator(f'{DIALOG} [data-sum-edit="gf"]').count() == 0
        order = page.evaluate("""() => [...document.querySelectorAll('#round-confirm > *')].map(e => e.id)""")
        assert order.index("round-confirm-sub") < order.index("sum-gf-host") < order.index("sum-list")
        assert page.evaluate("() => document.activeElement.id") != "sum-gf-ta"
        assert "General feedback" in page.locator(f"{DIALOG} .rl-gf").inner_text()

        sent_n = page.locator("#sum-send-n").inner_text()
        box.fill("Overall this reads well")
        page.wait_for_function(f"() => document.getElementById('sum-send-n').textContent === '{int(sent_n) + 1}'")
        # Saved as the draft: the page's own box has it, and it survives Back and a reopen.
        assert page.evaluate("() => document.getElementById('gf-ta').value") == "Overall this reads well"
        page.locator("#round-cancel-btn").tap()
        page.locator(DIALOG).wait_for(state="hidden")
        _open(page)
        assert page.locator(f"{DIALOG} #sum-gf-ta").input_value() == "Overall this reads well"
        assert page.locator("#round-confirm-sub").inner_text().endswith("and general feedback.")


def test_not_in_this_send_is_newest_first(tmp_path):
    with _ipad(tmp_path, _cards(tmp_path)) as (page, _, _history, _fonts):
        _open(page)
        head = page.locator(f"{DIALOG} .sum-rest-hdr")
        assert head.get_attribute("aria-expanded") == "false"
        assert page.locator(f'{DIALOG} [data-sum-id="question-13"]').count() == 0
        head.tap()
        page.locator(f'{DIALOG} [data-sum-id="question-13"]').wait_for()
        rows = page.evaluate("""() => {
          const out = [];
          let el = document.querySelector('#round-confirm-backdrop .sum-rest-hdr').nextElementSibling;
          for (; el && el.matches('.sum-row'); el = el.nextElementSibling) out.push(el.dataset.sumId);
          return out;
        }""")
        # 13 was sent last (though answered first), then 14; the two with no time by card number, newest first.
        assert rows == ["question-13", "question-14", "question-16", "question-11"]


def test_every_part_of_the_send_dialog_is_present(tmp_path):
    with _ipad(tmp_path, _cards(tmp_path)) as (page, _, _history, _fonts):
        _open(page)
        d = page.locator(DIALOG)
        sub = page.locator("#round-confirm-sub").inner_text()
        assert sub.startswith("Going to the agent:") and "1 answer" in sub and "1 comment" in sub
        assert d.locator('[data-sum-tab="review"] .sp-sum-cat').inner_text().startswith("Review")
        assert d.locator('[data-sum-tab="plans"] .sp-sum-cat').inner_text().startswith("Plans")
        assert d.locator('[data-sum-open="plans"]').inner_text() == "Open Plans"
        groups = d.locator("#sum-body-review .sum-group").all_inner_texts()
        assert any(g.startswith("Answers") and g.endswith("1") for g in groups), groups
        assert any(g.startswith("Comments") and g.endswith("1") for g in groups), groups
        assert d.locator('[data-sum-id="question-12"]').is_visible()
        assert "Say which machines ran it." in d.locator('[data-sum-id="note-card"]').inner_text()
        warn = d.locator("#sum-body-review .sum-warn")
        assert warn.inner_text() == "2 questions are still unanswered; the agent will see them as open."
        # The unanswered line sits just above Not in this Send.
        assert warn.evaluate("el => el.nextElementSibling.matches('.sum-rest-hdr')")
        assert "Not in this Send" in d.locator(".sum-rest-hdr").inner_text()
        change = d.locator('[data-sum-id="question-12"] [data-sum-edit="question-12"]')
        assert change.get_attribute("aria-label") == "Change #12"
        change.tap()
        d.locator('[data-sum-id="question-12"] .decision-btn-sum').first.wait_for()
        assert d.locator("#round-discard-btn").is_enabled()
        assert d.locator("#round-submit-btn").is_enabled()
        assert d.locator("#round-submit-btn").inner_text().startswith("Send")
        d.locator("#round-cancel-btn").tap()
        d.wait_for(state="hidden")
