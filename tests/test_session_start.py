"""Project membership and native SessionStart hooks, entirely off live state."""

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_annotate import cli, paths, workspace
from agent_annotate.hooks import session_start


def repo(path, remote="https://example.test/team/one.git"):
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "remote.origin.url", remote], check=True)
    return path


@pytest.fixture
def estate(tmp_path, monkeypatch):
    root = Path(os.environ["ANNOTATE_STATE_DIR"]).parent / "session-start" / tmp_path.name
    root.mkdir(parents=True)
    state_dir = root / "state"
    state_dir.mkdir()
    monkeypatch.setattr(cli, "STATE_DIR", state_dir)
    monkeypatch.setattr(cli, "LOCK_DIR", state_dir / "locks")
    monkeypatch.setattr(paths, "STATE_DIR", state_dir)
    from agent_annotate import review_access
    monkeypatch.setattr(review_access, "STATE_DIR", state_dir)
    first = repo(root / "repo")
    directory = root / "page"
    directory.mkdir()
    (directory / "comments.json").write_text(json.dumps({"anchors": {"d:q1": [
        {"status": "open", "decision_request": {"prompt": "Ship?"}},
        {"status": "open", "decision_request": {"prompt": "Answered?"},
         "decision": {"verdict": "select", "round_pending": True}},
        {"status": "archived", "decision_request": {"prompt": "Old?"}},
    ]}}))
    record = {"slug_dir": str(directory), "workspace_key": workspace.project_key(first),
              "workspace_primary": True, "url": "https://reviews.example/project/"}
    (state_dir / "project.json").write_text(json.dumps({"project": "project", "slugs": {"main": record}}))
    monkeypatch.chdir(first)
    return SimpleNamespace(root=root, repo=first, page=directory, state=state_dir, record=record)


def test_clone_worktree_orca_and_nested_repo_paths_match(estate):
    clone = estate.root / "clone"
    subprocess.run(["git", "clone", str(estate.repo), str(clone)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(clone), "config", "remote.origin.url",
                    "git@example.test:team/one.git"], check=True)
    subprocess.run(["git", "-C", str(estate.repo), "-c", "user.name=Test", "-c", "user.email=test@example.test",
                    "commit", "--allow-empty", "-m", "fixture"], check=True, capture_output=True)
    worktree = estate.root / "orca" / "workspaces" / "codex" / "task"
    subprocess.run(["git", "-C", str(estate.repo), "worktree", "add", "-b", "task", str(worktree)],
                   check=True, capture_output=True)
    nested = worktree / "src" / "deep"
    nested.mkdir(parents=True)
    for directory in (estate.repo, clone, worktree, nested):
        assert workspace.workspace_data(directory)["workspace"]["slug"] == "project/main"
        assert "1 waiting on you" in session_start.notice(directory)


def test_select_adds_second_repo_and_folder_without_losing_legacy_membership(estate, monkeypatch, capsys):
    state_file = estate.state / "project.json"
    old_root = estate.root / "legacy-folder"
    old_root.mkdir()
    data = json.loads(state_file.read_text())
    data["slugs"]["main"]["workspace_root"] = str(old_root)
    state_file.write_text(json.dumps(data))
    second = repo(estate.root / "second", "https://example.test/team/two.git")
    folder = estate.root / "folder"
    folder.mkdir()
    for directory in (second, folder):
        monkeypatch.chdir(directory)
        assert workspace.cmd_workspace(SimpleNamespace(select="project/main", project=None, json=True)) == 0
        assert json.loads(capsys.readouterr().out)["workspace"]["slug"] == "project/main"
    record = json.loads(state_file.read_text())["slugs"]["main"]
    assert record["workspace_repos"] == [workspace.project_key(estate.repo), workspace.project_key(second)]
    assert str(old_root) in record["workspace_folders"] and str(folder.resolve()) in record["workspace_folders"]
    nested = repo(folder / "nested", "https://example.test/team/nested.git")
    for directory in (estate.repo, second, old_root / "deep", folder / "deep", nested):
        assert workspace.workspace_data(directory)["workspace"]["slug"] == "project/main"


def test_unlisted_repo_is_silent_even_with_a_matching_project_label(estate):
    other = repo(estate.root / "unlisted", "https://example.test/team/unlisted.git")
    assert workspace.workspace_data(other, "project") == {"workspace": None, "pages": []}
    assert session_start.notice(other) is None


@pytest.mark.parametrize("marker", [False, True])
def test_archived_page_is_silent_and_does_not_win_recent_activity(estate, marker):
    data = json.loads((estate.state / "project.json").read_text())
    if marker:
        (estate.page / "archived.json").write_text('{"why": "Retired"}')
    else:
        data["slugs"]["main"]["archived"] = {"why": "Retired"}
        (estate.state / "project.json").write_text(json.dumps(data))
    assert session_start.notice(estate.repo) is None
    assert workspace.workspace_data(estate.repo)["workspace"] is None


def test_withdrawn_cards_do_not_count_as_waiting(estate):
    path = estate.page / "comments.json"
    store = json.loads(path.read_text())
    store["anchors"]["d:q1"].append({"status": "open", "decision_request": {"prompt": "Withdrawn?"},
                                      "withdrawn": {"why": "No longer asked"}})
    path.write_text(json.dumps(store))
    assert session_start.notice(estate.repo).endswith(" · 1 waiting on you")


def test_two_pages_use_most_recent_activity_not_registry_order(estate):
    other = {**estate.record, "slug_dir": str(estate.root / "other-page"), "workspace_selected_at": 4102444800}
    state_file = estate.state / "project.json"
    data = json.loads(state_file.read_text())
    data["slugs"]["other"] = other
    state_file.write_text(json.dumps(data))
    assert workspace.workspace_data(estate.repo)["workspace"]["slug"] == "project/other"
    assert workspace.duplicate_page(estate.root / "new-page") == other
    data["slugs"]["main"].update(workspace_selected_at=4102444801, workspace_primary=False)
    state_file.write_text(json.dumps(data))
    assert workspace.workspace_data(estate.repo)["workspace"]["slug"] == "project/main"


def test_publishing_a_plan_counts_as_page_activity(estate):
    directory = estate.root / "other-page"
    meta = directory / "plans" / "launch" / "meta.json"
    meta.parent.mkdir(parents=True)
    data = json.loads((estate.state / "project.json").read_text())
    data["slugs"]["other"] = {**estate.record, "slug_dir": str(directory)}
    (estate.state / "project.json").write_text(json.dumps(data))
    assert workspace.workspace_data(estate.repo)["workspace"]["slug"] == "project/main"
    meta.write_text('{"current": "v1"}')
    timestamp = (estate.page / "comments.json").stat().st_mtime + 10
    os.utime(meta, (timestamp, timestamp))
    assert workspace.workspace_data(estate.repo)["workspace"]["slug"] == "project/other"


@pytest.mark.parametrize("invocation", ["module", "script", "shell"])
def test_hook_outputs_one_visible_line_with_full_share_url_and_silence_elsewhere(estate, invocation):
    (estate.page / "current.meta.json").write_text('{"name":"Project workspace"}')
    from agent_annotate.review_access import ensure_key
    data = json.loads((estate.state / "project.json").read_text())
    data["slugs"]["main"].update(transport="funnel", public_base_path="/project/")
    (estate.state / "project.json").write_text(json.dumps(data))
    key = ensure_key(estate.page)
    command = {"module": [sys.executable, "-m", "agent_annotate.hooks.session_start"],
               "script": [sys.executable, str(Path(session_start.__file__))],
               "shell": ["bash", str(paths.SESSION_START_SCRIPT)]}[invocation]
    env = {**os.environ, "ANNOTATE_STATE_DIR": str(estate.state)}
    def run(directory, payload=None):
        result = subprocess.run(command, input=payload or json.dumps({"session_id": "test", "cwd": str(directory)}),
                                cwd=estate.root, env=env, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0 and result.stderr == ""
        return result.stdout
    output = run(estate.repo)
    assert len(output.splitlines()) == 1
    result = json.loads(output)
    line = result["systemMessage"]
    assert line == f"annotate: this project's page Project workspace https://reviews.example/project/#review={key} · 1 waiting on you"
    assert result["hookSpecificOutput"] == {"hookEventName": "SessionStart", "additionalContext": line}
    assert run(estate.root / "unlisted") == ""
    assert run(estate.root, "malformed") == ""


@pytest.mark.parametrize("provider", ["claude", "codex"])
def test_native_hook_installation_preserves_unrelated_settings_and_is_idempotent(tmp_path, monkeypatch, provider):
    target = tmp_path / "settings.json"
    original = {"permissions": {"allow": ["safe"]}, "hooks": {"SessionStart": [
        {"hooks": [{"type": "command", "command": "echo user-hook"}]}]}}
    target.write_text(json.dumps(original))
    target.chmod(0o600)
    monkeypatch.setattr(cli, "SETTINGS_JSON" if provider == "claude" else "CODEX_HOOKS_JSON", target)
    added, _ = cli._ensure_hook_installed(provider=provider)
    assert added
    result = json.loads(target.read_text())
    assert result["permissions"] == original["permissions"]
    assert result["hooks"]["SessionStart"][0] == original["hooks"]["SessionStart"][0]
    assert len(result["hooks"]["SessionStart"]) == 2
    assert cli._hook_registered("SessionStart", provider=provider)
    before = target.read_bytes()
    assert not cli._ensure_hook_installed(provider=provider)[0]
    assert target.read_bytes() == before and target.stat().st_mode & 0o777 == 0o600
    assert ("UserPromptSubmit" in result["hooks"]) == (provider == "claude")


def test_hook_never_uses_network_or_writes_state(estate, monkeypatch):
    import socket
    monkeypatch.setattr(socket, "socket", lambda *a, **kw: pytest.fail("network on session start"))
    before = {file: file.read_bytes() for file in estate.root.rglob("*") if file.is_file()}
    assert session_start.notice(estate.repo)
    assert before == {file: file.read_bytes() for file in estate.root.rglob("*") if file.is_file()}
