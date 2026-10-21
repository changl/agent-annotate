import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from agent_annotate.approval_catalog import item_id, read_bundle
from agent_annotate.cli import build_parser, run_command
from agent_annotate.plans_backfill import backfill_page, restore_page


def snapshot(directory):
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob("*") if p.is_file()}


def page(directory, *, verdict="accept"):
    directory.mkdir(exist_ok=True)
    request = {"prompt": "Ship this design?", "evidence": [{"anchor": "design"}],
               "options": [{"id": "blue", "label": "Blue", "consequence": "Use blue"}]}
    decision = {"verdict": verdict, "text": "Blue" if verdict == "select" else None,
                "by": "reviewer@example.com", "ts": "2026-10-01T12:00:00Z"}
    comment = {"id": "card-one", "number": 1, "anchor_id": "d:q1", "version": "v1",
               "decision_request": request, "decision": decision,
               "replies": [{"author": decision["by"], "author_email": decision["by"], "ts": decision["ts"],
                            "text": "☑ Selected: Blue" if verdict == "select" else "✓ Accepted"}]}
    store = {"schema_version": 2, "anchors": {"d:q1": [comment]}}
    (directory / "comments.json").write_text(json.dumps(store))
    (directory / ".comments.json.lock").touch()
    (directory / "versions").mkdir()
    (directory / "versions/v1.html").write_text('<section id="design"><p>The original design</p></section>')
    (directory / "versions/v1.cards.json").write_text(json.dumps([{
        "number": 1, "anchor_id": "d:q1", "decision_request": request}]))
    for p in (directory / "versions").iterdir():
        os.utime(p, (1, 1))
    answer = {"comment_id": comment["id"], "prompt": request["prompt"], **decision}
    (directory / "rounds.ndjson").write_text(json.dumps({"id": "round-one", "snapshot": True,
        "by": decision["by"], "version": "v1", "answers": [answer]}) + "\n")
    return store, comment


def save(directory, store):
    (directory / "comments.json").write_text(json.dumps(store))


@pytest.mark.parametrize("verdict", ["accept", "select"])
def test_dry_run_apply_exact_version_idempotence_and_restore(tmp_path, verdict):
    store, comment = page(tmp_path, verdict=verdict)
    before = snapshot(tmp_path)
    dry = backfill_page(tmp_path)
    assert snapshot(tmp_path) == before
    assert dry["counts"]["would_file"] == 1
    assert dry["branches"] == {"browser_and_sent": 1}
    (tmp_path / "comments.json").chmod(0o640)
    applied = backfill_page(tmp_path, apply=True)
    backup = Path(applied["backup"])
    updated = json.loads((tmp_path / "comments.json").read_text())
    plan = updated["approved_plans"][item_id(comment)]
    assert plan["kind"] == ("Approved" if verdict == "accept" else "Decided")
    entry = plan["history"][0]
    assert "original design" in read_bundle(tmp_path, entry["evidence_revision"])["html"]
    assert entry["source_version"] == "v1"
    assert updated["anchors"]["d:q1"][0]["decision"] == comment["decision"]
    assert (tmp_path / "comments.json").stat().st_mode & 0o777 == 0o640
    second_before = snapshot(tmp_path)
    second = backfill_page(tmp_path, apply=True)
    assert second["counts"]["already_linked"] == 1
    assert "backup" not in second
    assert snapshot(tmp_path) == second_before
    assert (backup / "comments.json").read_bytes() == json.dumps(store).encode()
    restore_page(tmp_path, backup)
    assert (tmp_path / "comments.json").read_bytes() == json.dumps(store).encode()
    assert (tmp_path / "comments.json").stat().st_mode & 0o777 == 0o640
    assert not list((tmp_path / "approval-evidence").glob("*/bundle.json"))
    restore_page(tmp_path, backup)


def test_existing_plan_links_without_refiling(tmp_path):
    _, comment = page(tmp_path)
    backfill_page(tmp_path, apply=True)
    store = json.loads((tmp_path / "comments.json").read_text())
    del store["anchors"]["d:q1"][0]["catalog_plan"]
    # Existing catalog provides evidence even when both card-side links were lost.
    plan = store["approved_plans"][item_id(comment)]
    save(tmp_path, store)
    assert backfill_page(tmp_path)["counts"]["would_link"] == 1
    backfill_page(tmp_path, apply=True)
    updated = json.loads((tmp_path / "comments.json").read_text())
    assert updated["approved_plans"][item_id(comment)] == plan
    assert updated["anchors"]["d:q1"][0]["catalog_plan"] == item_id(comment)


@pytest.mark.parametrize("change", ["agent", "legacy", "opt_out", "ineligible"])
def test_agent_legacy_and_opt_out_excluded(tmp_path, change):
    store, comment = page(tmp_path)
    if change == "agent":
        comment["decision"]["by"] = "agent:codex"
    elif change == "legacy":
        comment["decision"]["legacy"] = True
    elif change == "ineligible":
        comment["decision"]["catalog_eligible"] = False
    else:
        comment["decision_request"]["catalog"] = False
    save(tmp_path, store)
    before = snapshot(tmp_path)
    report = backfill_page(tmp_path, apply=True)
    assert report["items"] == []
    assert report["branches"] == {"excluded_agent_legacy_opt_out": 1}
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("problem,reason", [
    ("missing", "No such file"), ("media", "historical media"), ("changed", "modified after"),
    ("reversed", "later reversed"), ("two", "multiple approvals"), ("different", "different content"),
    ("browser", "provenance"), ("sent", "provenance"), ("pending", "still pending"),
    ("prompt", "prompt differs"), ("manual", "manual Plan"),
])
def test_conflicts_never_write(tmp_path, problem, reason):
    store, comment = page(tmp_path)
    if problem == "missing":
        (tmp_path / "versions/v1.html").unlink()
    elif problem == "media":
        (tmp_path / "versions/v1.html").write_text('<section id="design"><img src="screen.png"></section>')
        (tmp_path / "screen.png").write_bytes(b"image")
        os.utime(tmp_path / "versions/v1.html", (1, 1))
    elif problem == "changed":
        (tmp_path / "versions/v1.html").touch()
    elif problem == "reversed":
        comment["decision_history"] = [copy.deepcopy(comment["decision"])]
        comment["decision"] = {"verdict": "reject", "by": "reviewer@example.com", "ts": "2026-10-02T12:00:00Z"}
    elif problem == "two":
        other = copy.deepcopy(comment)
        other["id"] = "card-two"
        store["anchors"]["d:q1"].append(other)
        r = json.loads((tmp_path / "rounds.ndjson").read_text())
        r["answers"].append({**r["answers"][0], "comment_id": other["id"]})
        (tmp_path / "rounds.ndjson").write_text(json.dumps(r))
    elif problem == "different":
        store["approved_plans"] = {item_id(comment): {"current": "v1", "history": [
            {"version": "v1", "key": "other", "evidence_revision": "a" * 64}]}}
    elif problem == "browser":
        comment["replies"] = []
    elif problem == "sent":
        (tmp_path / "rounds.ndjson").unlink()
    elif problem == "pending":
        comment["decision"]["round_pending"] = True
    elif problem == "prompt":
        r = json.loads((tmp_path / "rounds.ndjson").read_text())
        r["answers"][0]["prompt"] = "Different prompt"
        (tmp_path / "rounds.ndjson").write_text(json.dumps(r))
    else:
        p = tmp_path / "plans" / item_id(comment)
        p.mkdir(parents=True)
        (p / "meta.json").write_text('{}')
    save(tmp_path, store)
    before = snapshot(tmp_path)
    report = backfill_page(tmp_path, apply=True)
    assert report["counts"]["conflict"] >= 1
    assert all(reason in row["reason"] for row in report["items"])
    assert snapshot(tmp_path) == before


def test_restore_refuses_later_edits_or_corrupt_backup(tmp_path):
    page(tmp_path)
    report = backfill_page(tmp_path, apply=True)
    path = tmp_path / "comments.json"
    body = path.read_bytes()
    path.write_bytes(body + b" ")
    with pytest.raises(ValueError, match="changed since"):
        restore_page(tmp_path, report["backup"])
    path.write_bytes(body)
    (Path(report["backup"]) / "comments.json").write_text("corrupt")
    with pytest.raises(ValueError, match="backup changed"):
        restore_page(tmp_path, report["backup"])


@pytest.mark.parametrize("browser,sent,branch", [(False, True, "sent_only"), (False, False, "neither")])
def test_provenance_requires_both_independent_records(tmp_path, browser, sent, branch):
    store, comment = page(tmp_path)
    if not browser:
        comment["replies"] = []
    if not sent:
        (tmp_path / "rounds.ndjson").unlink()
    save(tmp_path, store)
    report = backfill_page(tmp_path)
    assert report["branches"] == {branch: 1}
    assert report["counts"]["conflict"] == 1


def test_dry_run_does_not_create_lock_and_apply_requires_existing_lock(tmp_path):
    page(tmp_path)
    (tmp_path / ".comments.json.lock").unlink()
    before = snapshot(tmp_path)
    assert backfill_page(tmp_path)["counts"]["would_file"] == 1
    assert snapshot(tmp_path) == before
    with pytest.raises(ValueError, match="existing .comments.json.lock"):
        backfill_page(tmp_path, apply=True)
    assert snapshot(tmp_path) == before


def test_legacy_cards_report_the_same_number_as_the_page(tmp_path):
    store, comment = page(tmp_path)
    del comment["number"]
    save(tmp_path, store)
    report = backfill_page(tmp_path)
    assert report["items"][0]["card"] == 1


def test_archived_cards_and_corrupt_sealed_evidence(tmp_path):
    store, comment = page(tmp_path)
    store["archived"] = store.pop("anchors")
    save(tmp_path, store)
    backfill_page(tmp_path, apply=True)
    updated = json.loads((tmp_path / "comments.json").read_text())
    target = updated["archived"]["d:q1"][0]
    del target["catalog_plan"]
    plan = updated["approved_plans"][item_id(comment)]
    revision = plan["history"][0]["evidence_revision"]
    (tmp_path / "approval-evidence" / revision / "bundle.json").write_text("{}")
    save(tmp_path, updated)
    before = snapshot(tmp_path)
    report = backfill_page(tmp_path, apply=True)
    assert report["counts"]["conflict"] == 1
    assert "changed" in report["items"][0]["reason"]
    assert snapshot(tmp_path) == before


def test_cli_local_live_registry_scope_and_json(tmp_path, monkeypatch, capsys):
    from agent_annotate import cli
    page(tmp_path)
    monkeypatch.setattr(cli, "_registry_entries", lambda: [
        ("project", "live", {"slug_dir": str(tmp_path), "pid": 123}),
        ("project", "stopped", {"slug_dir": "/missing", "pid": 0}),
        ("project", "archived", {"slug_dir": "/missing", "pid": 123, "archived": True})])
    monkeypatch.setattr(cli, "_is_process_alive", lambda pid: pid == 123)
    before = snapshot(tmp_path)
    args = build_parser().parse_args(["plans", "backfill", "--dry-run", "--json"])
    assert run_command(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["dry_run"] is True
    assert len(report["pages"]) == 1
    assert len(report["skipped_inactive"]) == 2
    assert snapshot(tmp_path) == before
    assert "plans" not in build_parser().format_help().split("positional arguments:")[-1]
