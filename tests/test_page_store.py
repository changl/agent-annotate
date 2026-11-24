"""uzd: the first read (view=page) carries the latest version, the open cards and what a Send needs."""
from agent_annotate.sync_server import _card_anchors, _page_store


def _q(cid, aid, version, prompt, **extra):
    return {"id": cid, "anchor_id": aid, "version": version, "author": "agent:t", "status": "open",
            "text": prompt, "replies": [], "decision_request": {"prompt": prompt, "options": [{"id": "a", "label": "A"}]},
            **extra}


def _store():
    answered = {"verdict": "accept", "by": "reviewer@example.test"}
    return {"schema_version": 2, "current_version": "v3", "anchors": {
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
                    "status": "addressed_by_agent", "text": "Plans come whole", "replies": []}],
    }, "archived": {"d:gone": [_q("gone", "d:gone", "v1", "Archived?", status="archived", decision=answered)]}}


def test_page_view_keeps_what_the_latest_version_shows_and_counts_the_rest():
    numbers = {"now": 2, "open-old": 1, "peer": 3, "settled": 4, "body-old": 5, "body-new": 6, "gone": 7}
    page = _page_store(_store(), numbers, ["v1", "v2", "v3"], card_anchors={"d:now", "d:body"})
    kept = {c["id"] for area in ("anchors", "archived") for cs in page[area].values() for c in cs}
    # current, open from an older version, an earlier answer to the same prompt, the body card's
    # first live question, an unsent reply, and every non-review comment
    assert kept == {"now", "open-old", "peer", "body-old", "unsent", "plan"}
    assert page["partial"] is True
    assert page["omitted"] == {"earlier": 4, "rest": 2, "rest_missing": 0}  # settled, body-new, old-note, gone
    assert page["numbers"] == {"now": 2, "open-old": 1, "peer": 3, "body-old": 5}
    assert page["number_max"] == 7


def test_unreadable_body_keeps_every_anchor_card(tmp_path):
    assert _card_anchors(tmp_path, "v9") is None
    page = _page_store(_store(), {}, ["v1", "v2", "v3"], card_anchors=None)
    kept = {c["id"] for area in ("anchors", "archived") for cs in page[area].values() for c in cs}
    assert {"settled", "body-old", "gone"} <= kept and "body-new" not in kept
