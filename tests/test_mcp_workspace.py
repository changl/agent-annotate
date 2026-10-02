"""MCP reuses the project workspace and reports durable ownership read-only."""

import asyncio
import json
import subprocess

import pytest

pytest.importorskip("mcp")

from agent_annotate import cli, mcp_server, review_access, workspace  # noqa: E402


def _tool(name):
    return mcp_server.build_server()._tool_manager._tools[name].fn


def _snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def test_list_pages_uses_durable_owner_instead_of_legacy_monitor(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    target = {"handle": "terminal-current", "terminal_name": "Build", "group": "Apps",
              "project": "Project", "workspace": "Main", "label": "Apps > Project > Main > Build [terminal-current]"}
    record = {"slug_dir": str(tmp_path / "page"), "url": "https://review.example/project/",
              "owner_session": "session-current", "owner_agent": "codex",
              "owner_label": target["label"], "owner_claimed_at": "2026-10-02T00:00:00Z",
              "owner_target": target}
    (state / "project.json").write_text(json.dumps({"project": "project", "slugs": {"main": record}}))
    lease = tmp_path / "monitors" / "project" / "main" / "owner.json"
    lease.parent.mkdir(parents=True)
    legacy = {"owner_session": "session-stale", "owner_label": "Old monitor"}
    lease.write_text(json.dumps(legacy))
    monkeypatch.setattr(cli, "STATE_DIR", state)
    monkeypatch.setattr(mcp_server, "MONITOR_ROOT", tmp_path / "monitors")
    before = _snapshot(tmp_path)

    page = _tool("list_pages")()[0]

    assert page["owner"] == {"owner_session": "session-current", "owner_agent": "codex",
                             "owner_label": target["label"], "claimed_at": "2026-10-02T00:00:00Z",
                             "target": target}
    assert page["legacy_monitor"] == legacy
    assert _snapshot(tmp_path) == before


def test_ownerless_page_does_not_inherit_monitor_ownership(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    record = {"slug_dir": str(tmp_path / "page"), "url": "https://review.example/project/"}
    (state / "project.json").write_text(json.dumps({"project": "project", "slugs": {"main": record}}))
    lease = tmp_path / "monitors" / "project" / "main" / "owner.json"
    lease.parent.mkdir(parents=True)
    lease.write_text(json.dumps({"owner_session": "old-monitor"}))
    monkeypatch.setattr(cli, "STATE_DIR", state)
    monkeypatch.setattr(mcp_server, "MONITOR_ROOT", tmp_path / "monitors")

    page = _tool("list_pages")()[0]

    assert page["owner"] is None
    assert page["legacy_monitor"]["owner_session"] == "old-monitor"


@pytest.mark.parametrize("failed", [False, True])
def test_funnel_inventory_exposes_only_the_complete_share_link(tmp_path, monkeypatch, failed):
    directory = tmp_path / "page"
    directory.mkdir()
    monkeypatch.setattr(review_access, "STATE_DIR", tmp_path / "state")
    key = review_access.ensure_key(directory)
    record = {"slug_dir": str(directory), "transport": "funnel",
              "public_url": "https://reviews.example/annotate/project/main/",
              "url": "http://localhost:8800/", "local_url": "http://localhost:8800/"}
    if failed:
        record["transport_error"] = "Funnel unavailable"
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("project", "main", record)])
    monkeypatch.setattr(mcp_server, "MONITOR_ROOT", tmp_path / "monitors")
    before = _snapshot(tmp_path)

    page = _tool("list_pages")()[0]
    result = _tool("find_workspace")(cwd=str(tmp_path), project="project")

    expected = None if failed else record["public_url"] + "#review=" + key
    assert page["url"] == page["public_url"] == result["workspace"]["url"] == expected
    assert _snapshot(tmp_path) == before


def test_discovery_reuses_canonical_page_from_another_checkout_without_cli_or_writes(tmp_path, monkeypatch):
    checkout = tmp_path / "checkout"
    other = tmp_path / "other"
    for path in (checkout, other):
        subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(path), "config", "remote.origin.url",
                        "https://example.test/team/project.git"], check=True)
    directory = tmp_path / "external-reviews" / "main"
    directory.mkdir(parents=True)
    record = {"slug_dir": str(directory), "url": "https://review.example/project/",
              "workspace_key": workspace.project_key(checkout), "workspace_primary": True,
              "owner_session": "session-current", "owner_label": "Main > Build"}
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("project", "main", record)])
    monkeypatch.setattr(cli, "cmd_publish", lambda *args: pytest.fail("Discovery must not publish"))
    monkeypatch.setattr(cli, "cmd_claim", lambda *args: pytest.fail("Discovery must not take ownership"))
    before = _snapshot(tmp_path)
    run = subprocess.run
    calls = []

    def only_git(args, **kwargs):
        calls.append(args)
        assert args[0] == "git", "Discovery must not invoke an independently installed CLI"
        return run(args, **kwargs)

    monkeypatch.setattr(workspace.subprocess, "run", only_git)
    result = _tool("find_workspace")(cwd=str(other))

    assert result["workspace"]["slug"] == "project/main"
    assert result["workspace"]["directory"] == str(directory)
    assert result["workspace"]["url"] == record["url"]
    assert result["workspace"]["owner"]["owner_session"] == "session-current"
    assert _snapshot(tmp_path) == before
    assert calls


def test_discovery_requires_selection_when_multiple_project_pages_have_no_primary(tmp_path, monkeypatch):
    entries = [("project", name, {"slug_dir": str(tmp_path / name),
                                  "url": f"https://review.example/{name}/"}) for name in ("main", "content")]
    monkeypatch.setattr(cli, "_registry_entries", lambda: entries)
    result = _tool("find_workspace")(cwd=str(tmp_path), project="project")
    assert result["workspace"] is None
    assert {page["slug"] for page in result["pages"]} == {"project/main", "project/content"}
    assert list(tmp_path.iterdir()) == []


def test_mcp_descriptions_distinguish_workspace_and_legacy_monitor(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_registry_entries", lambda: [])
    tools = {tool.name: tool for tool in asyncio.run(mcp_server.build_server().list_tools())}
    discovery = tools["find_workspace"].description
    assert "Funnel" in discovery and "reuse" in discovery.lower()
    assert "round" in discovery.lower() and "progress" in discovery.lower()
    assert "legacy" in tools["connect_codex_page"].description.lower()
    assert "non-Orca" in tools["connect_codex_page"].description
    assert "monitor" in tools["disconnect_page"].description.lower()
    assert "ownership" in tools["disconnect_page"].description.lower()
    assert "owner lease" not in tools["list_pages"].description.lower()
    assert _tool("find_workspace")(cwd=str(tmp_path)) == {"workspace": None, "pages": []}
