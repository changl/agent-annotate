"""Category storage preserves old pages and immutable authored history."""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_copy_state import document

from agent_annotate.categories import (
    MAX_PROOF_BYTES,
    add_proof_file,
    category_counts,
    comment_category,
    comment_section,
    comment_sig,
    list_plans,
    load_categories,
    mark_finding_fixed,
    plan_meta,
    publish_plan_revision,
    reopen_finding,
    save_findings_sets,
)
from agent_annotate.copy_state import add_browser_revision, load_copy, restore_revision, save_copy


def seed_finding(directory):
    directory.mkdir(parents=True, exist_ok=True)
    finding = {"id": "gap", "number": 1, "anchor_id": "d:gap", "category": "findings", "version": "v1",
               "author": "agent:builder", "status": "open", "decision_request": {"prompt": "Fix?"}}
    (directory / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {"d:gap": [finding]}, "archived": {}}))
    (directory / "current.meta.json").write_text('{"current":"v2"}')
    return finding


def test_fix_proof_reopen_preserves_history(tmp_path):
    page = tmp_path / "page"
    seed_finding(page)
    image = tmp_path / "proof image.png"
    image.write_bytes(b"image proof")
    proof = add_proof_file(page, image)
    fixed = mark_finding_fixed(page, 1, by="agent:builder", note="Repaired", proof=[
        {"label": "Change", "url": "https://example.com/change"}, proof])
    assert fixed["status"] == "addressed_by_agent" and fixed["resolved_in_version"] == "v2"
    assert (page / "attachments" / proof["attachment"]).read_bytes() == image.read_bytes()
    assert category_counts(page)["findings"]["done"] == 1
    reopened = reopen_finding(page, "gap", by="chang@example.com", text="Still broken")
    assert "fixed" not in reopened and reopened["fixed_history"] == [fixed["fixed"]]
    assert reopened["round_pending"] and reopened["status"] == "open"
    assert category_counts(page)["findings"]["ready"] == 1
    with pytest.raises(PermissionError):
        reopen_finding(page, "gap", by="other@example.com", text="Replace their note")


def test_proof_refuses_symlinks_traversal_and_oversize(tmp_path):
    page = tmp_path / "page"
    seed_finding(page)
    source = tmp_path / "source.png"
    source.write_bytes(b"proof")
    link = tmp_path / "link.png"
    link.symlink_to(source)
    with pytest.raises(ValueError, match="symlink"):
        add_proof_file(page, link)
    directory_link = tmp_path / "linked"
    directory_link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        add_proof_file(page, directory_link / "source.png")
    with source.open("wb") as out:
        out.truncate(MAX_PROOF_BYTES + 1)
    with pytest.raises(ValueError, match="10 MB"):
        add_proof_file(page, source)
    for attachment in ("../source.png", "/source.png", "foo/../../x", "..", "bad\\x"):
        with pytest.raises(ValueError, match="attachment"):
            mark_finding_fixed(page, "gap", by="agent:a", note="", proof=[{"label": "x", "attachment": attachment}])


@pytest.mark.parametrize("identifier", ["../escape", "A", "a/b", "a%2fb", "a" * 65, "", "a\\b"])
def test_plan_id_validation_before_io(tmp_path, identifier):
    with pytest.raises(ValueError, match="plan_id"):
        publish_plan_revision(tmp_path, identifier, "<p>Hello</p>")
    assert not list(tmp_path.iterdir())


def test_parallel_plan_publication_preserves_each_version(tmp_path):
    def publish(index):
        return publish_plan_revision(tmp_path, "shopify-plan", f"<p>{index}</p>", title="Shopify", label=str(index))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(publish, range(8)))
    assert {r["version"] for r in results} == {f"v{i}" for i in range(1, 9)}
    assert len(plan_meta(tmp_path, "shopify-plan")["history"]) == 8
    assert list_plans(tmp_path)[0]["title"] == "Shopify"
    assert len({p.read_text() for p in (tmp_path / "plans/shopify-plan/versions").iterdir()}) == 8


def test_library_metadata_and_restore_append_without_changing_revision(tmp_path):
    data = document()
    data["groups"] = [{"id": "home", "label": "Home"}]
    data["blocks"][0].update(group="home", where="Hero", number=1, status="held", held_note="Awaiting launch",
                              alternatives=[{"label": "Alternative", "delta": {"ops": [{"insert": "Alternative\n"}]}}],
                              question_comment_id="question")
    original = save_copy(tmp_path, data)
    assert load_copy(tmp_path) == original
    result = add_browser_revision(tmp_path, "home-hero", {"ops": [{"insert": "New\n"}]}, {"id": "chang@example.com"},
                                  base_revision="draft-1", request_id=str(uuid.uuid4()))
    assert result["blocks"][0]["revisions"][-1]["round_pending"]
    restored = restore_revision(tmp_path, "home-hero", "draft-1", {"id": "chang@example.com"}, request_id=str(uuid.uuid4()))
    block = restored["blocks"][0]
    assert block["current"] == "draft-1" and len(block["revisions"]) == 3
    assert block["revisions"][0] == original["blocks"][0]["revisions"][0]
    assert block["revisions"][-1]["delta"] == block["revisions"][0]["delta"]
    assert category_counts(tmp_path)["library"]["ready"] == 1


def test_defaults_section_rules_and_read_state(tmp_path):
    assert comment_category({"anchor_id": "copy:hero"}) == "library"
    assert comment_category({}) == "review"
    assert comment_section({"status": "open", "decision_request": {"prompt": "?"}}) == "needs_you"
    assert comment_section({"status": "open", "replies": [{"author": "agent:a"}]}) == "needs_you"
    assert comment_section({"status": "open", "created_at": "2026-10-03T00:00:00Z", "author": "chang"}) == "ready"
    assert comment_section({"status": "open", "flagged_for_session": True}) == "waiting"
    assert comment_section({"status": "user_confirmed"}) == "done"
    assert comment_section({"status": "archived"}) is None
    finding = seed_finding(tmp_path)
    assert category_counts(tmp_path, "chang")["findings"]["unread"] == 1
    (tmp_path / "read-state.json").write_text(json.dumps({"chang": {"gap": {"sig": comment_sig(finding)}}}))
    assert category_counts(tmp_path, "chang")["findings"]["unread"] == 0
    for option, section in (("fix", "waiting"), ("keep", "done"), ("no", "done")):
        assert comment_section({**finding, "decision": {"verdict": "select", "option_id": option}}) == section
    assert load_categories(tmp_path) == {"schema_version": 1, "findings_sets": []}
    assert save_findings_sets(tmp_path, [{"id": "design", "label": "Design"}]) == load_categories(tmp_path)
