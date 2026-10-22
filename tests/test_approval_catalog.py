import copy
import json
import os
from datetime import datetime, timezone

import pytest

from agent_annotate.approval_catalog import (
    bind_evidence,
    catalog_meta,
    item_id,
    persist_evidence,
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


def decide(directory, store, comment, token, verdict="accept", text=None, ts=None):
    ts = ts or datetime.now(timezone.utc).isoformat()
    comment["decision"] = {"verdict": verdict, "text": text, "ts": ts, "by": "chang@example.com",
                           "catalog_eligible": True,
                           "evidence": bind_evidence(directory, store, comment, token)}
    if verdict in {"accept", "select"} and comment["decision_request"].get("catalog") is not False:
        persist_evidence(directory, comment, comment["decision"]["evidence"])
    promote(directory, store, comment)
    return store.get("approved_plans", {}).get(item_id(comment))


HTML = '<html><head><style>.design{color:blue}</style></head><body><section data-anchor-id="s:design"><h2>Design one</h2><p data-anchor-id="p:detail">Full details</p><svg><path d="M0 0 L1 1"/></svg></section><p>Unrelated</p></body></html>'


def test_capture_preserves_full_section_deduplicates_and_hashes(tmp_path):
    comment = card()
    store = {"anchors": {"d:q1": [comment]}}
    _, tokens = seal_review(tmp_path, HTML, "v1", store)
    assert not (tmp_path / "approval-evidence").exists()
    plan = decide(tmp_path, store, comment, tokens[comment["id"]])
    revision = plan["history"][0]["evidence_revision"]
    bundle = read_bundle(tmp_path, revision)
    assert bundle["html"].count("Full details") == 1
    assert "Unrelated" not in bundle["html"]
    assert '<path d="M0 0 L1 1"/>' in bundle["html"]
    assert bundle["incomplete"] == []
    assert seal_review(tmp_path, HTML, "v1", store)[1][comment["id"]]["revision"] == tokens[comment["id"]]["revision"]
    assert seal_review(tmp_path, HTML.replace("one", "two"), "v1", store)[1][comment["id"]]["revision"] != tokens[comment["id"]]["revision"]


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
    assert shown == html
    assert 'src="assets/screen.png"' in shown
    assert './' + pinned in render_plan(tmp_path, plan, "v1")


def test_unchanged_images_reuse_hashes_but_edits_and_tampering_are_detected(tmp_path, monkeypatch):
    from pathlib import Path

    from agent_annotate.approval_catalog import _cached_image_hash
    _cached_image_hash.cache_clear()
    original = tmp_path / "screen.png"
    original.write_bytes(b"first-image")
    comment = card()
    store = {"anchors": {"d:q1": [comment]}}
    html = HTML.replace("Full details", '<img src="screen.png">')
    token = seal_review(tmp_path, html, "v1", store)[1][comment["id"]]
    decide(tmp_path, store, comment, token)
    # Warm the frozen target's hash, then no image bytes need reading on a vote.
    decide(tmp_path, store, comment, token)
    reads = []
    original_read = Path.read_bytes

    def read(path):
        reads.append(path)
        return original_read(path)
    monkeypatch.setattr(Path, "read_bytes", read)
    decide(tmp_path, store, comment, token)
    assert reads == []
    pinned = next((tmp_path / "attachments").glob("approval-*.png"))
    pinned.write_bytes(b"corrupted copy")
    decide(tmp_path, store, comment, token)
    assert original in reads and original_read(pinned) == b"first-image"
    reads.clear()
    saved_stat = original.stat()
    original.write_bytes(b"other-image")  # same length, deliberately restored mtime
    os.utime(original, ns=(saved_stat.st_atime_ns, saved_stat.st_mtime_ns))
    plan = decide(tmp_path, store, comment, token)
    assert reads == [original]
    assert "changed since view" in render_plan(tmp_path, plan, plan["current"])


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
        promote(tmp_path, store, comment)
        assert len(plan["history"]) == 1
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
    other = {**comment, "id": "another-card", "number": 2, "decision_request": {**comment["decision_request"], "item_id": item_id(comment)}}
    store["anchors"]["d:q1"].append(other)
    new = seal_review(tmp_path, HTML.replace("one", "two"), "v1", store)[1][other["id"]]
    plan = decide(tmp_path, store, other, new)
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


def test_client_card_words_cannot_replace_the_server_snapshot(tmp_path):
    comment = card()
    store = {"anchors": {"d:q1": [comment]}}
    token = seal_review(tmp_path, HTML, "v1", store)[1][comment["id"]]
    shown_request = {**comment["decision_request"], "prompt": "Approve this revised wording?"}
    bound = bind_evidence(tmp_path, store, comment, token, shown_request)
    assert bound["request"]["prompt"] == comment["decision_request"]["prompt"]
    assert bound["revision"] == token["revision"]


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


def test_persisted_vote_survives_expired_view_before_send(tmp_path):
    from agent_annotate.approval_catalog import _VIEWS
    comment = card()
    store = {"anchors": {"d:q1": [comment]}}
    token = seal_review(tmp_path, HTML, "v1", store)[1][comment["id"]]
    comment["decision"] = {"verdict": "accept", "ts": "2026-10-16T10:00:00Z", "by": "reviewer", "catalog_eligible": True,
                           "evidence": bind_evidence(tmp_path, store, comment, token)}
    persist_evidence(tmp_path, comment, comment["decision"]["evidence"])
    _VIEWS.clear()
    promote(tmp_path, store, comment)
    plan = store["approved_plans"][item_id(comment)]
    assert not plan["history"][0]["evidence_incomplete"]
    assert "Design one" in render_plan(tmp_path, plan, "v1")


def test_changed_image_at_vote_is_flagged_and_never_pinned_as_reviewed(tmp_path):
    (tmp_path / "assets").mkdir()
    original = tmp_path / "assets/screen.png"
    original.write_bytes(b"shown-image")
    comment = card()
    store = {"anchors": {"d:q1": [comment]}}
    html = HTML.replace("Full details", 'Full details<img src="assets/screen.png">')
    shown, tokens = seal_review(tmp_path, html, "v1", store)
    original.write_bytes(b"changed-before-vote")
    plan = decide(tmp_path, store, comment, tokens[comment["id"]])
    assert shown == html
    assert plan["history"][0]["evidence_incomplete"]
    assert "changed since view" in render_plan(tmp_path, plan, "v1")
    assert "data-evidence-image-unavailable" in render_plan(tmp_path, plan, "v1")
    assert not (tmp_path / "attachments").exists()


def test_same_card_new_decisions_always_supersede_even_with_one_view(tmp_path):
    comment = card()
    store = {"anchors": {"d:q1": [comment]}}
    token = seal_review(tmp_path, HTML, "v1", store)[1][comment["id"]]
    for verdict, choice in [("accept", None), ("select", "Blue"), ("accept", None)]:
        plan = decide(tmp_path, store, comment, token, verdict, choice)
        assert not comment["decision"].get("catalog_conflict")
    assert plan["current"] == "v3" and len(plan["history"]) == 3
    assert plan["history"][-1]["kind"] == "Approved"


def test_identity_distinguishes_shared_anchors_and_survives_anchor_moves():
    one = card()
    assert item_id(one) != item_id({**one, "id": "two", "number": 2})
    assert item_id(one) == item_id({**one, "anchor_id": "new:location"})
    del one["number"]
    assert item_id(one) != item_id({**one, "id": "two"})
    assert item_id(one) == item_id({**one, "anchor_id": "new:location"})


def test_only_cited_images_persist_and_styles_are_shared_once(tmp_path):
    (tmp_path / "assets").mkdir()
    for name in ("cited", "unrelated"):
        (tmp_path / f"assets/{name}.png").write_bytes(name.encode())
    one = card()
    two = {**one, "id": "card-two", "number": 2}
    store = {"anchors": {"d:q1": [one, two]}}
    html = HTML.replace("Full details", 'Full details<img src="assets/cited.png">').replace("Unrelated", '<img src="assets/unrelated.png">')
    _, tokens = seal_review(tmp_path, html, "v1", store)
    assert not (tmp_path / "attachments").exists()
    for comment in (one, two):
        decide(tmp_path, store, comment, tokens[comment["id"]])
    assert len(list((tmp_path / "attachments").iterdir())) == 1
    assert len(list((tmp_path / "approval-evidence/styles").iterdir())) == 1
    for path in (tmp_path / "approval-evidence").glob("*/bundle.json"):
        bundle = json.loads(path.read_text())
        assert "styles" not in bundle and bundle["styles_revision"]


def test_malformed_evidence_anchor_degrades_to_incomplete_card(tmp_path):
    comment = card()
    comment["decision_request"]["evidence"] = [{"anchor": []}]
    store = {"anchors": {"d:q1": [comment]}}
    _, tokens = seal_review(tmp_path, HTML, "v1", store)
    plan = decide(tmp_path, store, comment, tokens[comment["id"]])
    assert plan["history"][0]["evidence_incomplete"]
    assert "Invalid evidence anchor" in render_plan(tmp_path, plan, "v1")


def test_missing_bundle_renders_incomplete_and_approved_names_the_choice(tmp_path):
    comment = card()
    comment["decision_request"]["options"] = [{"id": "accept", "label": "Ship blue"}, {"id": "reject", "label": "Keep red"}]
    store = {}
    plan = decide(tmp_path, store, comment, None)
    html = render_plan(tmp_path, plan, "v1")
    assert "Chosen: <strong>Ship blue</strong>" in html and "Keep red" not in html
    assert '<time data-decided-time datetime="' in html
    path = tmp_path / "approval-evidence" / plan["history"][0]["evidence_revision"] / "bundle.json"
    path.unlink()
    assert "Evidence incomplete" in render_plan(tmp_path, plan, "v1")
