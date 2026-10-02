import json
import subprocess
from types import SimpleNamespace

import pytest

from agent_annotate import cli, workspace


def test_discovery_reuses_page_across_worktrees_and_blocks_a_second_page(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "remote.origin.url", "https://example.test/team/project.git"], check=True)
    # An alternate checkout with the same project remote has the same scope.
    other = tmp_path / "other"
    subprocess.run(["git", "clone", str(repo), str(other)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(other), "config", "remote.origin.url", "https://example.test/team/project.git"], check=True)
    directory = repo / "reviews" / "workspace"
    record = {"slug_dir": str(directory), "url": "https://review.example/project/", "workspace_key": workspace.project_key(repo)}
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("project", "workspace", record)])
    monkeypatch.chdir(other)
    assert workspace.cmd_workspace(SimpleNamespace(select=None, project=None, json=True)) == 0
    assert json.loads(capsys.readouterr().out)["workspace"]["directory"] == str(directory)
    assert workspace.duplicate_page(other / "reviews" / "new") == record
    assert workspace.duplicate_page(directory) is None


def test_no_page_returns_empty_result_without_creating_state(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_registry_entries", lambda: [])
    assert workspace.cmd_workspace(SimpleNamespace(select=None, project=None, json=True)) == 0
    assert json.loads(capsys.readouterr().out) == {"workspace": None, "pages": []}
    assert list(tmp_path.iterdir()) == []


def _repo(path, remote):
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(path), "config", "remote.origin.url", remote], check=True)
    return path


def test_external_artifact_uses_callers_repository_across_project_aliases(tmp_path, monkeypatch):
    repo = _repo(tmp_path / "repo", "https://example.test/team/project.git")
    successor = _repo(tmp_path / "successor", "git@example.test:team/project.git")
    directory = tmp_path / "reviews" / "main"
    directory.mkdir(parents=True)
    record = {"slug_dir": str(directory), "workspace_key": workspace.project_key(repo),
              "url": "https://reviews.example/project/"}
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("old-alias", "main", record)])
    new = tmp_path / "reviews" / "new"

    assert workspace.duplicate_page(new, "new-alias", caller=successor) == record
    monkeypatch.chdir(successor)
    assert workspace.duplicate_page(new, "new-alias") == record
    assert workspace.workspace_data(successor, "new-alias")["workspace"]["directory"] == str(directory)


def test_generic_reviews_label_does_not_join_unrelated_known_repositories(tmp_path, monkeypatch):
    original = _repo(tmp_path / "original", "https://example.test/team/one.git")
    unrelated = _repo(tmp_path / "unrelated", "https://example.test/team/two.git")
    directory = original / "reviews" / "main"
    record = {"slug_dir": str(directory), "url": "https://reviews.example/one/"}
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("reviews", "main", record)])

    assert workspace.workspace_data(unrelated, "reviews") == {"workspace": None, "pages": []}
    assert workspace.duplicate_page(tmp_path / "external" / "new", "reviews", caller=unrelated) is None


def test_external_non_git_project_can_reuse_an_explicit_project_label(tmp_path, monkeypatch):
    directory = tmp_path / "reviews" / "main"
    directory.mkdir(parents=True)
    record = {"slug_dir": str(directory), "url": "https://reviews.example/project/"}
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("project", "main", record)])

    assert workspace.workspace_data(tmp_path, "project")["workspace"]["slug"] == "project/main"
    assert workspace.duplicate_page(tmp_path / "new", "project", caller=tmp_path) == record


def test_workspace_data_includes_durable_owner_and_no_failed_route_fallback(tmp_path, monkeypatch):
    target = {"handle": "terminal-current", "terminal_name": "Build", "project": "Project", "workspace": "Main"}
    record = {"slug_dir": str(tmp_path / "main"), "transport": "funnel", "url": "http://localhost:8800/",
              "transport_error": "Funnel unavailable", "owner_session": "session-current",
              "owner_agent": "claude-code", "owner_label": "Project > Main > Build [terminal-current]",
              "owner_claimed_at": "2026-10-02T00:00:00Z", "owner_target": target}
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("project", "main", record)])

    data = workspace.workspace_data(tmp_path, "project")

    assert data["workspace"] == data["pages"][0]
    assert data["workspace"]["directory"] == record["slug_dir"]
    assert data["workspace"]["url"] is None
    assert data["workspace"]["owner"] == {"owner_session": "session-current", "owner_agent": "claude-code",
                                          "owner_label": record["owner_label"], "claimed_at": record["owner_claimed_at"],
                                          "target": target}
    assert list(tmp_path.iterdir()) == []


def _root_estate(tmp_path, monkeypatch):
    repo = _repo(tmp_path / "repo", "https://example.test/team/project.git")
    root = tmp_path / "reviews"
    directories = {name: root / name for name in ("main", "content", "worksheet")}
    directories["outside"] = tmp_path / "outside"
    for directory in directories.values():
        directory.mkdir(parents=True)
        (directory / "comments.json").write_text('{"anchors": {"history": [{"text": "keep me"}]}}')
    records = {name: {"slug_dir": str(directory), "url": f"https://reviews.example/{name}/",
                      "workspace_primary": True, "owner_session": "unchanged-owner"}
               for name, directory in directories.items()}
    records["worksheet"]["standalone"] = True
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "reviews.json").write_text(json.dumps({"project": "reviews", "slugs": records}))
    monkeypatch.setattr(cli, "STATE_DIR", state_dir)
    monkeypatch.setattr(cli, "LOCK_DIR", state_dir / "locks")
    monkeypatch.chdir(repo)
    return repo, root, directories, records, state_dir


def test_explicit_root_selects_canonical_page_without_claiming_or_joining_worksheets(tmp_path, monkeypatch, capsys):
    repo, root, directories, records, state_dir = _root_estate(tmp_path, monkeypatch)
    feedback = {name: (directory / "comments.json").read_bytes() for name, directory in directories.items()}

    assert workspace.cmd_workspace(SimpleNamespace(select="reviews/main", project=None, root=str(root), json=True)) == 0
    selected = json.loads(capsys.readouterr().out)["workspace"]
    assert selected["slug"] == "reviews/main"
    saved = json.loads((state_dir / "reviews.json").read_text())["slugs"]
    assert saved["main"]["workspace_root"] == str(root.resolve())
    assert saved["main"]["workspace_key"] == workspace.project_key(repo)
    assert saved["main"]["workspace_primary"] is True
    assert saved["content"]["workspace_primary"] is False
    assert saved["worksheet"]["standalone"] is True
    assert saved["outside"] == records["outside"]
    assert all(record["owner_session"] == "unchanged-owner" for record in saved.values())
    assert feedback == {name: (directory / "comments.json").read_bytes() for name, directory in directories.items()}
    successor = _repo(tmp_path / "successor", "git@example.test:team/project.git")
    data = workspace.workspace_data(successor)
    assert data["workspace"]["slug"] == "reviews/main"
    assert {page["slug"] for page in data["pages"]} == {"reviews/main", "reviews/content"}


@pytest.mark.parametrize("symlink", [False, True])
def test_root_selection_rejects_pages_outside_resolved_root_without_state_changes(tmp_path, monkeypatch, symlink):
    _, root, directories, records, state_dir = _root_estate(tmp_path, monkeypatch)
    if symlink:
        link = root / "linked-outside"
        link.symlink_to(directories["outside"], target_is_directory=True)
        records["outside"]["slug_dir"] = str(link)
        (state_dir / "reviews.json").write_text(json.dumps({"project": "reviews", "slugs": records}))
    before = (state_dir / "reviews.json").read_bytes()

    with pytest.raises(ValueError, match="must contain"):
        workspace.cmd_workspace(SimpleNamespace(select="reviews/outside", project=None, root=str(root), json=True))

    assert (state_dir / "reviews.json").read_bytes() == before
