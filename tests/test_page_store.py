"""uzd: the first read (view=page) carries the latest version, the open cards and what a Send needs."""
import os

from agent_annotate.sync_server import _card_anchors, _page_store, _plan_docs, _plan_stamps


def _q(cid, aid, version, prompt, **extra):
    return {"id": cid, "anchor_id": aid, "version": version, "author": "agent:t", "status": "open",
            "text": prompt, "replies": [], "decision_request": {"prompt": prompt, "options": [{"id": "a", "label": "A"}]},
            **extra}


def _store():
    answered = {"verdict": "accept", "by": "reviewer@example.test"}
    return {"schema_version": 2, "current_version": "v3", "approved_plans": {"x": {"current": "r1"}}, "anchors": {
        "d:now": [_q("now", "d:now", "v3", "Q2: Ship it?")],
        "d:open-old": [_q("open-old", "d:open-old", "v1", "Still open from v1?")],
        "d:peer": [_q("peer", "d:peer", "v1", "Ship it?", status="addressed_by_agent", decision=answered)],
        "d:settled": [_q("settled", "d:settled", "v1", "Old and done?", status="addressed_by_agent", decision=answered)],
        "d:body": [_q("body-old", "d:body", "v2", "Baked in the body?", status="addressed_by_agent", decision=answered),
                   _q("body-new", "d:body", "v2", "Asked again?", status="addressed_by_agent", decision=answered)],
        "s:note": [{"id": "unsent", "anchor_id": "s:note", "version": "v1", "author": "reviewer@example.test",
                    "status": "addressed_by_agent", "text": "Old",
                    "replies": [{"author": "reviewer@example.test", "text": "Not sent yet", "sent_at": None}]},
                   {"id": "old-note", "anchor_id": "s:note", "version": "v2", "author": "reviewer@example.test",
                    "status": "addressed_by_agent", "text": "Done", "replies": []}],
        "plan:x": [{"id": "plan", "anchor_id": "plan:x", "category": "plans", "version": "v1", "author": "agent:t",
                    "status": "addressed_by_agent", "text": "No plan meta: kept", "replies": []}],
        "plan:p": [{"id": f"plan-{v}", "anchor_id": "plan:p", "category": "plans", "doc": "plan:p", "version": v,
                    "author": "agent:t", "status": "resolved_in_version", "text": "Plan note", "replies": []}
                   for v in ("v1", "v2", "v3")]
                  + [_q("plan-q", "plan:p", "v1", "Plan question?", category="plans", doc="plan:p",
                        status="addressed_by_agent", decision=answered)],
    }, "archived": {"d:gone": [_q("gone", "d:gone", "v1", "Archived?", status="archived", decision=answered)]}}


REVIEW = ("v3", ["v1", "v2", "v3"], {"d:now", "d:body"})
# v3 is newer than the plan's current: neither shown nor counted. Its body shows a question card on plan:p.
PLAN = ("v2", ["v1", "v2", "v3"], {"plan:p"})


def _kept(page):
    return {c["id"] for area in ("anchors", "archived") for cs in page[area].values() for c in cs}


def test_page_view_keeps_what_the_latest_version_shows_and_counts_the_rest():
    numbers = {"now": 2, "open-old": 1, "peer": 3, "settled": 4, "body-old": 5, "body-new": 6, "gone": 7}
    page = _page_store(_store(), numbers, {"review": REVIEW, "plan:p": PLAN})
    # current, open from an older version, an earlier answer to the same prompt, the body card's
    # first live question, an unsent reply, a plan's current version and its body card, a plan without meta
    assert _kept(page) == {"now", "open-old", "peer", "body-old", "unsent", "plan", "plan-v2", "plan-q"}
    assert page["partial"] is True and "approved_plans" not in page
    assert page["omitted"] == {"review": {"earlier": 4, "rest": 2, "rest_missing": 0},  # settled, body-new, old-note, gone
                               "plan:p": {"earlier": 1, "rest": 0, "rest_missing": 0}}  # plan-v1
    assert page["numbers"] == {"now": 2, "open-old": 1, "peer": 3, "body-old": 5}
    assert page["number_max"] == 7
    # A plan question no longer in its body is left out and counted for Not in this Send.
    page = _page_store(_store(), numbers, {"review": REVIEW, "plan:p": PLAN[:2] + (set(),)})
    assert "plan-q" not in _kept(page) and page["omitted"]["plan:p"] == {"earlier": 2, "rest": 1, "rest_missing": 0}


def test_plan_docs_come_from_each_plans_meta(tmp_path):
    (tmp_path / "plans/p/versions").mkdir(parents=True)
    (tmp_path / "plans/p/meta.json").write_text('{"current": "v2", "history": [{"version": "v1"}, {"version": "v2"}]}')
    (tmp_path / "plans/p/versions/v2.html").write_text('<div class="card" data-anchor-id="plan:q1">Q</div>')
    store = {"anchors": {"a": [{"id": "1", "doc": "plan:p"}, {"id": "2", "doc": "plan:../x"}, {"id": "3", "doc": "plan:none"}]}}
    assert _plan_docs(tmp_path, store) == {"plan:p": ("v2", ["v1", "v2"], {"plan:q1"})}
    before = _plan_stamps(tmp_path)
    (tmp_path / "plans/p/meta.json").write_text('{"current": "v3", "history": [{"version": "v3"}]}')
    os.utime(tmp_path / "plans/p/meta.json", ns=(1, 1))
    assert _plan_stamps(tmp_path) != before


def test_unreadable_body_keeps_every_anchor_card(tmp_path):
    assert _card_anchors(lambda: tmp_path / "v9.html") is None
    page = _page_store(_store(), {}, {"review": REVIEW[:2] + (None,)})
    assert {"settled", "body-old", "gone"} <= _kept(page) and "body-new" not in _kept(page)
