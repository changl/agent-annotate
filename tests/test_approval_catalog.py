import copy
import json

import pytest

from agent_annotate.approval_catalog import (
    bind_evidence,
    catalog_meta,
    item_id,
    promote,
    read_bundle,
    render_plan,
    seal_review,
)
from agent_annotate.categories import publish_plan_revision


def card():
    return {"id": "card-one", "anchor_id": "d:q1", "version": "v1", "number": 1,
            "decision_request": {"prompt": "Ship the design?", "context": "Review both screens",
                                 "evidence": [{"anchor": "s:design"}, {"anchor": "p:detail"}],
                                 "options": [{"id": "blue", "label": "Blue", "consequence": "Use blue"}]}}


def decide(directory, store, comment, token, verdict="accept", text=None, ts="2026-10-16T10:00:00Z"):
    comment["decision"] = {"verdict": verdict, "text": text, "ts": ts, "by": "chang@example.com",
                           "evidence": bind_evidence(directory, store, comment, token)}
    promote(directory, store, comment)
    return store.get("approved_plans", {}).get(item_id(comment))


HTML = '<html><head><style>.design{color:blue}</style></head><body><section data-anchor-id="s:design"><h2>Design one</h2><p data-anchor-id="p:detail">Full details</p><svg><path d="M0 0 L1 1"/></svg></section><p>Unrelated</p></body></html>'


def test_capture_preserves_full_section_deduplicates_and_hashes(tmp_path):
    comment = card()
    store = {"anchors": {"d:q1": [comment]}}
    _, tokens = seal_review(tmp_path, HTML, "v1", store)
    revision = tokens[comment["id"]]["revision"]
    bundle = read_bundle(tmp_path, revision)
    assert bundle["html"].count("Full details") == 1
    assert "Unrelated" not in bundle["html"]
    assert '<path d="M0 0 L1 1"/>' in bundle["html"]
    assert bundle["incomplete"] == []
    assert seal_review(tmp_path, HTML, "v1", store)[1] == tokens
    assert seal_review(tmp_path, HTML.replace("one", "two"), "v1", store)[1] != tokens


def test_images_are_pinned_in_review_and_plan_before_original_changes(tmp_path):
    (tmp_path / "assets").mkdir()
    original = tmp_path / "assets/screen.png"
    original.write_bytes(b"first-image")
    comment = card()
    store = {"anchors": {"d:q1": [comment]}}
    html = HTML.replace("Full details", 'Full details<img src="assets/screen.png">')
    shown, tokens = seal_review(tmp_path, html, "v1", store, "/annotate/review")
    plan = decide(tmp_path, store, comment, tokens[comment["id"]])
    original.write_bytes(b"second-image")
    bundle = read_bundle(tmp_path, plan["history"][0]["evidence_revision"])
    pinned = next(iter(bundle["assets"]))
    assert (tmp_path / pinned).read_bytes() == b"first-image"
    assert './' + pinned in shown
    assert './' + pinned in render_plan(tmp_path, plan, "v1")


def test_stable_identity_survives_comment_recreation_and_carry():
    a = card()
    b = {**a, "id": "new-thread", "version": "v99", "origin_version": "v1"}
    b["decision_request"] = {**a["decision_request"], "prompt": "Different wording"}
    assert item_id(a) == item_id(b)
    assert item_id({**b, "doc": "plan:other"}) != item_id(a)
    b["decision_request"]["item_id"] = "existing-plan"
    assert item_id(b) == "existing-plan"


def test_supersession_changes_rejection_and_duplicate_retries(tmp_path):
    comment = card()
    store = {"anchors": {"d:q1": [comment]}}
    token = seal_review(tmp_path, HTML, "v1", store)[1][comment["id"]]
    plan = decide(tmp_path, store, comment, token)
    for _ in range(3):
        assert decide(tmp_path, store, comment, token) == plan
    comment["version"] = "v2"
    token2 = seal_review(tmp_path, HTML.replace("one", "two"), "v2", store)[1][comment["id"]]
    for verdict in ("changes", "reject", "comment"):
        assert decide(tmp_path, store, comment, token2, verdict, "needs work")["current"] == "v1"
    decide(tmp_path, store, comment, token2)
    assert plan["current"] == "v2" and len(plan["history"]) == 2
    assert "Superseded" in catalog_meta(plan)["history"][0]["label"]
    assert "Design one" in render_plan(tmp_path, plan, "v1")
    assert "Design two" in render_plan(tmp_path, plan, "v2")


def test_selection_files_label_consequence_without_effect_declaration(tmp_path):
    comment = card()
    store = {"anchors": {"d:q1": [comment]}}
    token = seal_review(tmp_path, HTML, "v1", store)[1][comment["id"]]
    plan = decide(tmp_path, store, comment, token, "select", "Blue\n\nPlease ship")
    assert plan["kind"] == "Decided"
    assert plan["history"][0]["label"] == "Decided: Blue"
    assert plan["history"][0]["consequence"] == "Use blue"


@pytest.mark.parametrize("evidence", [None, {"revision": "../../secret"}, {"revision": "a" * 64}])
def test_missing_or_invalid_tokens_still_file_incomplete_card(tmp_path, evidence):
    comment = card()
    plan = decide(tmp_path, {}, comment, evidence)
    assert plan["history"][0]["evidence_incomplete"] is True
    assert "Evidence incomplete" in render_plan(tmp_path, plan, "v1")


def test_external_and_missing_images_never_prevent_vote(tmp_path):
    comment = card()
    store = {"anchors": {"d:q1": [comment]}}
    html = HTML.replace("Full details", '<img src="https://example.test/x.png"><img src="missing.png">')
    _, tokens = seal_review(tmp_path, html, "v1", store)
    plan = decide(tmp_path, store, comment, tokens[comment["id"]])
    assert plan["history"][0]["evidence_incomplete"] is True
    assert "Image not sealed" in render_plan(tmp_path, plan, "v1")


def test_opt_out_and_pending_votes_do_not_file(tmp_path):
    comment = card()
    comment["decision_request"]["catalog"] = False
    assert decide(tmp_path, {}, comment, None) is None
    del comment["decision_request"]["catalog"]
    comment["decision"]["round_pending"] = True
    store = {}
    promote(tmp_path, store, comment)
    assert "approved_plans" not in store


def test_competing_approval_cannot_replace_newer_current(tmp_path):
    comment = card()
    store = {"anchors": {"d:q1": [comment]}}
    old = seal_review(tmp_path, HTML, "v1", store)[1][comment["id"]]
    new = seal_review(tmp_path, HTML.replace("one", "two"), "v1", store)[1][comment["id"]]
    plan = decide(tmp_path, store, comment, new)
    current = copy.deepcopy(plan)
    decide(tmp_path, store, comment, old)
    assert comment["decision"]["catalog_conflict"] is True
    assert plan == current


def test_manual_publish_cannot_replace_managed_current(tmp_path):
    comment = card()
    store = {"schema_version": 2, "anchors": {"d:q1": [comment]}}
    decide(tmp_path, store, comment, None)
    (tmp_path / "comments.json").write_text(json.dumps(store))
    with pytest.raises(ValueError, match="reviewer decisions"):
        publish_plan_revision(tmp_path, item_id(comment), "<p>unapproved</p>")


def test_explicit_legacy_plan_identity_preserves_its_history(tmp_path):
    publish_plan_revision(tmp_path, "existing", "<p>Legacy approved design</p>")
    comment = card()
    comment["decision_request"]["item_id"] = "existing"
    plan = decide(tmp_path, {}, comment, None)
    assert plan["current"] == "v2"
    assert plan["history"][0]["legacy"] is True
    assert plan["history"][1]["predecessor"] == "v1"


def test_reposed_card_words_and_frozen_iframe_stay_together(tmp_path):
    comment = card()
    store = {"anchors": {"d:q1": [comment]}}
    token = seal_review(tmp_path, HTML, "v1", store)[1][comment["id"]]
    shown_request = {**comment["decision_request"], "prompt": "Approve this revised wording?"}
    bound = bind_evidence(tmp_path, store, comment, token, shown_request)
    bundle = read_bundle(tmp_path, bound["revision"])
    assert bundle["request"]["prompt"] == shown_request["prompt"]
    assert "Design one" in bundle["html"] and bound["revision"] != token["revision"]


def test_adapter_null_optional_fields_can_be_filed(tmp_path):
    comment = card()
    comment["decision_request"].update(evidence=None, options=None, consequences=None)
    plan = decide(tmp_path, {}, comment, None)
    assert plan["current"] == "v1"
    assert "Card only" in render_plan(tmp_path, plan, "v1")


def test_row_evidence_remains_a_valid_standalone_table(tmp_path):
    comment = card()
    comment["decision_request"]["evidence"] = [{"anchor": "row:one"}]
    store = {"anchors": {"d:q1": [comment]}}
    _, tokens = seal_review(tmp_path, '<table><tr data-anchor-id="row:one"><td>Exact row</td></tr></table>', "v1", store)
    plan = decide(tmp_path, store, comment, tokens[comment["id"]])
    assert '<table><tbody><tr data-anchor-id="row:one"><td>Exact row</td></tr></tbody></table>' in render_plan(tmp_path, plan, "v1")


def test_lost_bundle_before_send_files_incomplete_card_instead(tmp_path):
    comment = card()
    store = {"anchors": {"d:q1": [comment]}}
    token = seal_review(tmp_path, HTML, "v1", store)[1][comment["id"]]
    comment["decision"] = {"verdict": "accept", "ts": "2026-10-16T10:00:00Z", "by": "reviewer", "evidence": token}
    (tmp_path / "approval-evidence" / token["revision"] / "bundle.json").unlink()
    promote(tmp_path, store, comment)
    assert store["approved_plans"][item_id(comment)]["history"][0]["evidence_incomplete"]
