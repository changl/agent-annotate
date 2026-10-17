"""Standalone archives keep their documents and history, but no active work."""
import argparse
import json
from datetime import UTC, datetime

import pytest
from test_consolidate import _card, _page, _request, _serve, _store, _tree

from agent_annotate import categories, cli, consolidate, project_state, sync_server, version_guard, workspace
from agent_annotate.hooks import check_comment_bus as hook


@pytest.fixture
def page(tmp_path, monkeypatch):
    directory = _page(tmp_path, "old", versions=2)
    _store(directory, [_card("q1", 1), _card("q2", 2)], [_card("q0", 3, status="archived")])
    state = tmp_path / "state"
    state.mkdir()
    bus = tmp_path / "bus" / "shop"
    bus.mkdir(parents=True)
    (bus / "old.ndjson").write_text(json.dumps({"event": "round_submitted", "by": "chang@example.test",
                                               "comment_ids": ["q1"]}) + "\n")
    record = {"project": "shop", "slug": "old", "slug_dir": str(directory), "port": 8984,
              "local_url": "http://localhost:8984/", "url": "http://localhost:8984/",
              "bus_file": str(bus / "old.ndjson"), "owner_session": "owner"}
    (state / "shop.json").write_text(json.dumps({"project": "shop", "slugs": {"old": record}}))
    monkeypatch.setattr(cli, "STATE_DIR", state)
    monkeypatch.setattr(sync_server, "STATE_DIR", state)
    monkeypatch.setattr(version_guard, "_registry", cli._registry_entries)
    monkeypatch.setattr(cli, "_running_servers", lambda **kw: {})
    monkeypatch.setattr(cli, "_is_process_alive", lambda pid: False)
    monkeypatch.setattr(hook, "STATE", str(state))
    monkeypatch.setattr(hook, "BUS_ROOT", str(bus.parent))
    monkeypatch.setattr(hook, "DRY_RUN", True)
    return directory, state, record


def run(command="archive", **extra):
    return cli.cmd_archive(argparse.Namespace(cmd=command, slug="shop/old", project=None,
                                             why="Superseded", dry_run=False, json=True, **extra))


@pytest.mark.parametrize("command", ["archive", "unarchive"])
def test_dry_run_is_read_only_and_reports_counts(page, capsys, command):
    directory, state, _ = page
    if command == "unarchive":
        assert run() == 0
        capsys.readouterr()
    before = _tree(directory.parent.parent)
    args = argparse.Namespace(cmd=command, slug="shop/old", project=None,
                              why="Superseded", dry_run=True, json=True)
    assert cli.cmd_archive(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["dry_run"] and report["counts"]["cards"] == 3
    assert report["active_counts_before"]["review"]["needs_you"] == (2 if command == "archive" else 0)
    assert _tree(directory.parent.parent) == before


def test_archive_and_unarchive_restore_everything(page, capsys):
    directory, state, record = page
    original = _tree(directory)
    assert run() == 0
    capsys.readouterr()
    after = _tree(directory)
    assert after.pop("archived.json")
    assert after == original
    assert consolidate.marker(directory)["why"] == "Superseded"
    assert json.loads((state / "shop.json").read_text())["slugs"]["old"]["archived"]["why"] == "Superseded"
    assert run() == 0  # idempotent
    assert run("unarchive") == 0
    assert _tree(directory) == original
    assert cli._load_state_for_project("shop")["slugs"]["old"] == record
    assert categories.category_counts(directory)["review"]["needs_you"] == 2
    sync_server._atomic_write_json(directory / "read-state.json", {})


@pytest.mark.parametrize("command", ["archive", "unarchive", "withdraw"])
def test_cli_dry_run_receipt_and_files_are_unchanged(page, capsys, monkeypatch, command):
    directory, state, _ = page
    if command == "unarchive":
        assert run() == 0
        capsys.readouterr()
    monkeypatch.setattr(cli, "_api", lambda *a, **kw: pytest.fail("dry run must not write through HTTP"))
    before = _tree(directory.parent.parent)
    arguments = [command, "shop/old", "--dry-run"]
    if command == "withdraw":
        arguments += ["1", "--why", "Superseded"]
    elif command == "archive":
        arguments += ["--why", "Superseded"]
    assert cli.run_command(cli.build_parser().parse_args(arguments)) == 0
    assert capsys.readouterr().out.startswith(f"dry run: would {command} shop/old")
    assert _tree(directory.parent.parent) == before


def test_archive_leaves_inboxes_counts_hook_workspace_and_version_checks(page, capsys, monkeypatch):
    directory, state, record = page
    assert workspace.candidates(directory, "shop")
    assert hook._scan("owner")
    assert run() == 0
    capsys.readouterr()
    assert workspace.candidates(directory, "shop") == []
    assert cli._decision_cards(cli._load_store(record)) == []
    assert all(not any(counts.values()) for counts in categories.category_counts(directory).values())
    for all_events in (False, True):
        assert cli.cmd_inbox(argparse.Namespace(slug="shop/old", project=None, category=None,
                                                unread=True, json=True, all_events=all_events)) == 0
        result = json.loads(capsys.readouterr().out)
        assert result["events"] == [] and result["card_count"] == 0
    monkeypatch.setenv("ANNOTATE_HOOK_ALL", "1")
    assert hook._scan("owner") == []
    monkeypatch.setattr(version_guard, "_unregistered_servers", lambda records: [])
    monkeypatch.setattr(cli, "_api", lambda *a, **kw: pytest.fail("archived pages must not be probed"))
    assert version_guard._page_rows({}, False) == []
    # The file is authoritative even when a stale registry row lacks the flag.
    cli._save_state_for_project("shop", {"project": "shop", "slugs": {"old": record}})
    assert not workspace.candidates(directory, "shop")
    assert hook._scan("owner") == []


def test_archived_url_stays_readable_but_all_writes_are_refused(page, capsys):
    directory, _, _ = page
    server = _serve(directory, "/annotate/shop/old", "old")
    url = f"http://localhost:{server.server_port}/annotate/shop/old/"
    try:
        assert run() == 0
        capsys.readouterr()
        for suffix in ("", "?archived=1", "?v=v1", "comments.json", "api/comments"):
            assert _request(url + suffix)[0] == 200
        caps = json.loads(_request(url + "api/capabilities")[2])
        assert caps["archive"] and caps["read_only"] and caps["version_guard"] is None
        assert _request(url + "api/comments", "POST", {"anchor_id": "s:scope", "text": "late"})[0] == 410
        assert _request(url + "api/comments/q1", "PUT", {"status": "open"})[0] == 410
        for write in (lambda: sync_server._atomic_write_json(directory / "comments.json", {}),
                      lambda: project_state.save_project(directory, {"modules": []})):
            with pytest.raises(PermissionError, match="read-only"):
                write()
        assert run("unarchive") == 0
        assert not json.loads(_request(url + "api/capabilities")[2])["read_only"]
    finally:
        server.shutdown()
        server.server_close()


def test_old_server_refused_and_reason_required(page, capsys, monkeypatch):
    directory, _, _ = page
    monkeypatch.setattr(cli, "_running_servers", lambda **kw: {str(directory): [{"pid": 1, "port": 8984}]})
    monkeypatch.setattr(cli, "_api", lambda *a, **kw: (200, {"consolidation": True}))
    assert run() == 2
    assert "restart" in capsys.readouterr().err
    assert not (directory / "archived.json").exists()
    args = argparse.Namespace(cmd="archive", slug="shop/old", project=None, why="  ", dry_run=True, json=True)
    assert cli.cmd_archive(args) == 2
    assert "nonempty" in capsys.readouterr().err


def test_archiving_consolidated_page_does_not_undo_consolidation(page, capsys):
    directory, _, _ = page
    (directory / "consolidated.json").write_text(json.dumps({"target": {"project": "shop", "slug": "new"}}))
    assert run() == 0
    assert consolidate.marker(directory)["archived"]
    assert run("unarchive") == 0
    assert consolidate.marker(directory)["target"]["slug"] == "new"
    assert run("unarchive") == 2
    assert "cannot undo consolidation" in capsys.readouterr().err


def test_archive_leaves_metric_totals_and_mcp_inbox(page, capsys):
    from agent_annotate.metrics import collect_metrics
    directory, state, record = page
    since, until = datetime(2026, 1, 1, tzinfo=UTC), datetime(2027, 1, 1, tzinfo=UTC)
    bus = directory.parent.parent / "bus"
    assert collect_metrics(since, until, state, bus)["global"]["active_pages"] == 1
    assert run() == 0
    capsys.readouterr()
    counts = collect_metrics(since, until, state, bus)["global"]
    assert counts["active_pages"] == counts["submitted_rounds"] == 0
    pytest.importorskip("mcp")
    from agent_annotate.mcp_server import build_server
    tools = build_server()._tool_manager._tools
    assert tools["list_pages"].fn() == []
    assert tools["list_cards"].fn("shop/old") == []
    inbox = tools["read_inbox"].fn("shop/old")
    assert inbox["events"] == [] and inbox["card_count"] == 0
