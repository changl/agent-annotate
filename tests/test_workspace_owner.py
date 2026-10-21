"""Explicit claims and submitted rounds share only bounded workspace tabs."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_annotate import cli, delivery, project_state, review_access, workspace
from agent_annotate.urls import page_url


@pytest.fixture
def linked(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(cli, "STATE_DIR", state)
    monkeypatch.setattr(cli, "LOCK_DIR", tmp_path / "locks")
    monkeypatch.setattr(delivery, "STATE_DIR", state)
    monkeypatch.setattr(review_access, "STATE_DIR", state)
    root = tmp_path / "project"
    records = {}
    for name in ("main", "tab", "sheet", "other", "foreign", "independent"):
        directory = root / name if name != "other" else tmp_path / "other" / name
        directory.mkdir(parents=True)
        (directory / "current.meta.json").write_text(json.dumps({"current": "v1", "history": [{"version": "v1"}]}))
        (directory / "comments.json").write_text(json.dumps({"anchors": {"d:q1": [
            {"id": "aaaaaaaaaaaa", "decision": {"verdict": "comment", "text": "Keep my note", "round_pending": True},
             "decision_history": [{"verdict": "select", "text": "Prior choice"}]}]}}))
        review_access.ensure_key(directory)
        records[name] = {"slug_dir": str(directory), "url": f"https://reviews.example/{name}/", "transport": "funnel",
                         "workspace_key": "git:example/project", "owner_session": "old-" + name,
                         "owner_target": {"session": "old-" + name, "handle": "old-terminal"},
                         "bus_file": str(tmp_path / "bus" / name / (name + ".ndjson"))}
    records["main"].update(workspace_primary=True, workspace_root=str(root))
    records["sheet"]["standalone"] = True
    records["other"]["workspace_key"] = "git:example/unrelated"
    records["foreign"]["url"] = "https://foreign.example/foreign/"
    records["independent"]["workspace_primary"] = True
    tabs = [{"id": name, "label": name, "url": record["url"]} for name, record in records.items() if name != "main"]
    tabs.append({"id": "unknown", "label": "Missing", "url": "https://reviews.example/missing/"})
    project_state.save_project(records["main"]["slug_dir"], {"modules": [], "tabs": tabs})
    for name, record in records.items():
        cli._save_state_for_project(name, {"project": name, "slugs": {name: {**record, "project": name, "slug": name}}})
    monkeypatch.setattr(workspace, "project_key", lambda *args: pytest.fail("Owner polls must not launch Git"))
    target = {"session": "new-session", "handle": "new-terminal", "agent": "codex", "incarnation": "current",
              "worktree": "worktree", "pid": 4242, "process_start": "start", "label": "Project > Main > Build"}
    fields = {"owner_session": "new-session", "owner_agent": "codex", "owner_label": target["label"],
              "owner_claimed_at": "2026-10-02T00:00:00Z", "owner_target": target}
    monkeypatch.setattr(cli, "_owner_fields", lambda: copy.deepcopy(fields))
    return SimpleNamespace(records=records, root=root, state=state, fields=fields, target=target)


def test_membership_is_exact_same_origin_and_bounded_without_subprocesses_or_key_links(linked):
    primary = linked.records["main"]
    assert [(p, s) for p, s, _ in workspace.workspace_tab_records(primary)] == [("tab", "tab")]
    # Ambiguous registration cannot grant a second page's key or ownership.
    duplicate = {**linked.records["tab"], "slug_dir": str(linked.root / "duplicate")}
    cli._save_state_for_project("duplicate", {"project": "duplicate", "slugs": {"duplicate": duplicate}})
    assert workspace.workspace_tab_records(primary) == []


def test_declared_root_supports_legacy_tabs_without_cached_keys(linked):
    primary = {**linked.records["main"], "workspace_key": None}
    tab = cli._load_state_for_project("tab")
    tab["slugs"]["tab"].pop("workspace_key")
    cli._save_state_for_project("tab", tab)
    assert [(p, s) for p, s, _ in workspace.workspace_tab_records(primary)] == [("tab", "tab")]


def test_raw_tab_does_not_control_effective_workspace_owner(linked):
    primary = cli._load_state_for_project("main")["slugs"]["main"]
    child = cli._load_state_for_project("tab")["slugs"]["tab"]
    before = (linked.state / "tab.json").read_bytes()
    assert workspace.owner_data(child)["owner_session"] == primary["owner_session"]
    assert workspace.workspace_owner_record(child)["workspace_owner"]["slug"] == "main"
    assert (linked.state / "tab.json").read_bytes() == before
    assert workspace.owner_data(linked.records["other"])["owner_session"] == "old-other"


@pytest.mark.parametrize("claim", ["main/main", "tab/tab"])
def test_explicit_claim_binds_active_tab_preserving_drafts_history_and_bare_project_json(linked, claim):
    before_comments = {name: (directory / "comments.json").read_bytes()
                       for name, record in linked.records.items() for directory in [Path(record["slug_dir"])]}
    main_project = Path(linked.records["main"]["slug_dir"]) / "project.json"
    before_project = main_project.read_bytes()
    assert cli.cmd_claim(SimpleNamespace(slug=claim, project=None)) == 0
    for name in ("main", "tab"):
        record = cli._load_state_for_project(name)["slugs"][name]
        assert record["owner_session"] == "new-session"
        assert record["owner_target"] == linked.target
        meta = json.loads((Path(record["slug_dir"]) / "current.meta.json").read_text())
        assert meta["owner"]["owner_session"] == "new-session"
        assert meta["history"] == [{"version": "v1"}]
    for name in ("sheet", "other", "foreign", "independent"):
        assert cli._load_state_for_project(name)["slugs"][name]["owner_session"] == "old-" + name
    assert main_project.read_bytes() == before_project
    assert before_comments == {name: (Path(record["slug_dir"]) / "comments.json").read_bytes()
                               for name, record in linked.records.items()}


def test_tab_round_routes_to_canonical_current_owner_once_without_disclosing_share_key(linked, monkeypatch):
    cli._write_meta_locked(Path(linked.records["main"]["slug_dir"]), lambda meta: meta.update(name="Main workspace"))
    cli._write_meta_locked(Path(linked.records["tab"]["slug_dir"]), lambda meta: meta.update(name="Child worksheet"))
    assert cli.cmd_claim(SimpleNamespace(slug="main/main", project=None)) == 0
    child = cli._load_state_for_project("tab")["slugs"]["tab"]
    # A contributor's stale/raw owner field cannot steal the shared workspace.
    child.update(owner_session="contributor", owner_target={"session": "contributor", "handle": "wrong-terminal"})
    cli._save_state_for_project("tab", {"project": "tab", "slugs": {"tab": child}})
    bus = Path(child["bus_file"])
    bus.parent.mkdir(parents=True)
    bus.write_text(json.dumps({"event": "session_push", "round": True, "automatic_delivery": True,
                               "delivery_id": "a" * 12, "owner_session": "new-session",
                               "owner_target": linked.target, "comment_count": 1}) + "\n")
    sends = []
    monkeypatch.setattr(delivery, "_target_ready", lambda target: (target == linked.target, "wrong target"))

    def orca(*args):
        sends.append(args)
        return {"send": {"accepted": True, "prompt": {"stages": []}}}

    monkeypatch.setattr(delivery, "_orca", orca)
    assert delivery.dispatch_record(child, "tab", "tab")["deliveries"][0]["state"] == "accepted"
    assert delivery.dispatch_record(child, "tab", "tab")["deliveries"][0]["state"] == "accepted"
    assert len(sends) == 1 and sends[0][3] == "new-terminal"
    prompt = sends[0][sends[0].index("--text") + 1]
    assert "Round submitted on Main workspace https://reviews.example/main/" in prompt
    assert "Child worksheet" not in prompt
    assert "annotate inbox tab/tab --unread" in prompt
    assert "#review=" not in prompt and review_access.read_key(linked.root / "main") not in prompt
    assert page_url(child).startswith("https://reviews.example/tab/#review=")


@pytest.mark.parametrize("claim", ["main/main", "tab/tab"])
def test_claim_inherits_effective_owner_reads_for_page_and_shared_tab(linked, monkeypatch, capsys, claim):
    from agent_annotate.hooks import check_comment_bus as hook

    monkeypatch.setattr(cli, "BUS_OFFSET_ROOT", linked.state / "bus-offsets")
    monkeypatch.setattr(cli, "HOOK_OFFSET_ROOT", linked.state / "hook-offsets")
    monkeypatch.setattr(cli, "BUS_ROOT", linked.state.parent / "bus")
    monkeypatch.setattr(hook, "STATE", str(linked.state))
    monkeypatch.setattr(hook, "BUS_ROOT", str(cli.BUS_ROOT))
    monkeypatch.setattr(hook, "INBOX_OFFSET_ROOT", str(cli.BUS_OFFSET_ROOT))
    monkeypatch.setattr(hook, "HOOK_OFFSET_ROOT", str(cli.HOOK_OFFSET_ROOT))
    monkeypatch.setattr(hook, "DRY_RUN", True)
    monkeypatch.setattr(cli, "_session_id", lambda: "new-session")
    positions = {}
    for name in ("main", "tab"):
        bus = Path(linked.records[name]["bus_file"])
        bus.parent.mkdir(parents=True)
        old = json.dumps({"event": "round_submitted", "by": "reviewer", "round_id": "old"}) + "\n"
        new = json.dumps({"event": "round_submitted", "by": "reviewer", "round_id": "new"}) + "\n"
        bus.write_text(old + new)
        offset = cli._offset_file(name, name, "old-main")
        offset.parent.mkdir(parents=True)
        offset.write_text(str(len(old)))
        cli._category_offset_file(offset, "plans").write_text("0")
        notified = cli.HOOK_OFFSET_ROOT / "old-main" / name / f"{name}.offset"
        notified.parent.mkdir(parents=True)
        notified.write_text(str(len(old + new)))
        # A pre-existing bystander cursor must not suppress the owner's unread round.
        destination = cli._offset_file(name, name, "new-session")
        destination.parent.mkdir(parents=True)
        destination.write_text(str(len(old + new)))
        positions[name] = len(old)

    assert cli.cmd_claim(SimpleNamespace(slug=claim, project=None)) == 0
    capsys.readouterr()
    notices = hook._scan("new-session")
    assert len(notices) == 2
    assert all("1 reviewer event(s)" in line and "ROUND SUBMITTED" in line for line in notices)
    for name in ("main", "tab"):
        offset = cli._offset_file(name, name, "new-session")
        assert int(offset.read_text()) == positions[name]
        assert cli._category_offset_file(offset, "plans").read_text() == "0"
        assert int(cli._category_offset_file(offset, "review").read_text()) == positions[name]
        assert cli.cmd_inbox(SimpleNamespace(slug=f"{name}/{name}", project=None, unread=True,
                                             json=True, all_events=False)) == 0
        result = json.loads(capsys.readouterr().out)
        assert [event["round_id"] for event in result["events"] if event["event"] == "round_submitted"] == ["new"]
    assert hook._scan("new-session") == []
    # Claiming again as the same owner must not rewind the just-read inbox.
    before = cli._offset_file("main", "main", "new-session").read_text()
    assert cli.cmd_claim(SimpleNamespace(slug=claim, project=None)) == 0
    assert cli._offset_file("main", "main", "new-session").read_text() == before


def test_claim_without_previous_session_cursor_uses_legacy_read_position(linked, monkeypatch):
    monkeypatch.setattr(cli, "BUS_OFFSET_ROOT", linked.state / "bus-offsets")
    monkeypatch.setattr(cli, "HOOK_OFFSET_ROOT", linked.state / "hook-offsets")
    legacy = cli.BUS_OFFSET_ROOT / "main" / "main.offset"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("123")
    assert cli.cmd_claim(SimpleNamespace(slug="main/main", project=None)) == 0
    assert cli._offset_file("main", "main", "new-session").read_text() == "123"
    assert (cli.HOOK_OFFSET_ROOT / "new-session" / "main" / "main.offset").read_text() == "123"
    # No prior read of the tab: its unread backlog remains intact.
    assert cli._offset_file("tab", "tab", "new-session").read_text() == "0"
