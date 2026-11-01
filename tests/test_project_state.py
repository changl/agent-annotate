"""Project modules are bounded plain data and survive review-version changes."""

import copy
import json
from datetime import datetime, timezone

import pytest

from agent_annotate import project_state


def _project():
    return {
        "title": "Fastlane Drive",
        "modules": [
            {
                "id": "hosted-pages",
                "title": "Project links",
                "kind": "links",
                "items": [{"label": "Payload CMS", "url": "http://127.0.0.1:3000/admin", "description": "Local CMS"}],
            },
            {
                "id": "progress",
                "title": "Progress",
                "kind": "progress",
                "items": [{"label": "CMS setup", "status": "done", "detail": "Ready to review"}],
            },
            {"id": "notes", "title": "Notes", "kind": "notes", "items": [{"text": "Next review pending"}]},
        ],
    }


def test_validation_copies_input_and_generates_schema_and_timestamp():
    data = _project()
    before = copy.deepcopy(data)
    normalized = project_state.validate_project(data)
    assert data == before
    assert normalized["schema_version"] == 1
    assert datetime.fromisoformat(normalized["updated_at"]).tzinfo == timezone.utc
    assert normalized["modules"] == data["modules"]
    normalized["modules"][0]["items"][0]["label"] = "Changed"
    assert data == before


@pytest.mark.parametrize("url", [
    "http://localhost:3000/admin",
    "http://127.0.0.1:8802/",
    "http://[::1]:3000/",
    "https://macbook-pro.tail2b8ab9.ts.net:8447/demo/",
    "https://example.com/path?view=preview#section",
])
def test_local_and_remote_http_links_are_allowed(url):
    data = _project()
    data["modules"][0]["items"][0]["url"] = url
    assert project_state.validate_project(data)["modules"][0]["items"][0]["url"] == url


@pytest.mark.parametrize("url", [
    "javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "file:///etc/passwd",
    "ftp://example.com/",
    "//example.com/",
    "/admin",
    "https:///missing-host",
    "https://user:secret@example.com/",
    "https://user@example.com/",
    "https://@example.com/",
    "http://user%40name:secret@localhost/",
    "https://example.com:invalid/",
    "https://[broken/",
    "\nhttps://example.com/",
    "https://exam\tple.com/",
    "https://example.com/has space",
    "https://example.com\\@evil.example/",
])
def test_unsafe_or_ambiguous_urls_are_rejected(url):
    data = _project()
    data["modules"][0]["items"][0]["url"] = url
    with pytest.raises(ValueError):
        project_state.validate_project(data)


@pytest.mark.parametrize("data", [
    None,
    [],
    {},
    {"modules": None},
    {"modules": {}},
    {"modules": [], "schema_version": True},
    {"modules": [], "schema_version": "1"},
    {"modules": [], "schema_version": 2},
    {"modules": [], "title": None},
    {"modules": [], "updated_at": "yesterday"},
    {"modules": [], "updated_at": "2026-09-29T12:00:00"},
    {"modules": [], "unexpected": "value"},
    {"modules": [None]},
    {"modules": [{"id": "test"}]},
    {"modules": [{"id": "test", "title": "Test", "kind": "unknown", "items": []}]},
    {"modules": [{"id": "test", "title": "Test", "kind": "notes", "items": {}}]},
    {"modules": [{"id": "test", "title": "Test", "kind": "notes", "items": [{"text": 1}]}]},
    {"modules": [{"id": "test", "title": "Test", "kind": "notes", "items": [{"text": "ok", "html": True}]}]},
    {"modules": [{"id": "test", "title": "Test", "kind": "links", "items": [{"label": "Link"}]}]},
    {"modules": [{"id": "test", "title": "Test", "kind": "progress", "items": [{"label": "Step", "status": "ready"}]}]},
])
def test_malformed_schema_is_rejected(data):
    with pytest.raises(ValueError):
        project_state.validate_project(data)


@pytest.mark.parametrize("module_id", ["", "../links", "a b", "a.b", "<script>", "中文", "valid\n"])
def test_module_ids_must_be_safe(module_id):
    data = _project()
    data["modules"][0]["id"] = module_id
    with pytest.raises(ValueError):
        project_state.validate_project(data)


def test_duplicate_module_ids_are_rejected():
    data = _project()
    data["modules"][1]["id"] = data["modules"][0]["id"]
    with pytest.raises(ValueError, match="unique"):
        project_state.validate_project(data)


@pytest.mark.parametrize("status", ["todo", "in_progress", "done", "blocked"])
def test_supported_progress_statuses(status):
    data = _project()
    data["modules"][1]["items"][0]["status"] = status
    assert project_state.validate_project(data)["modules"][1]["items"][0]["status"] == status


def test_module_and_item_count_boundaries():
    data = {"modules": [
        {"id": f"m{i}", "title": "Notes", "kind": "notes", "items": [{"text": "x"}] * 50}
        for i in range(12)
    ]}
    assert len(project_state.validate_project(data)["modules"]) == 12
    data["modules"].append({"id": "m12", "title": "Notes", "kind": "notes", "items": []})
    with pytest.raises(ValueError, match="12 modules"):
        project_state.validate_project(data)
    data = _project()
    data["modules"][2]["items"] = [{"text": "x"}] * 51
    with pytest.raises(ValueError, match="50 items"):
        project_state.validate_project(data)


@pytest.mark.parametrize("location, limit", [
    (("title",), 160),
    (("modules", 0, "title"), 160),
    (("modules", 0, "items", 0, "label"), 160),
    (("modules", 0, "items", 0, "description"), 2000),
    (("modules", 1, "items", 0, "detail"), 2000),
    (("modules", 2, "items", 0, "text"), 2000),
])
def test_string_length_boundaries(location, limit):
    data = _project()
    target = data
    for key in location[:-1]:
        target = target[key]
    target[location[-1]] = "x" * limit
    project_state.validate_project(data)
    target[location[-1]] += "x"
    with pytest.raises(ValueError, match="characters"):
        project_state.validate_project(data)


def test_size_bound_counts_utf8_bytes():
    data = {"modules": [{
        "id": "notes", "title": "Notes", "kind": "notes", "items": [{"text": "界" * 1000}] * 30,
    }]}
    with pytest.raises(ValueError, match="65536 bytes"):
        project_state.validate_project(data)


def test_html_remains_plain_data(tmp_path):
    text = '<img src="x" onerror="alert(1)"> <script>alert(2)</script> & "quotes"'
    data = _project()
    data["modules"][0]["items"][0]["description"] = text
    data["modules"][2]["items"][0]["text"] = text
    saved = project_state.save_project(tmp_path, data)
    assert saved["modules"][2]["items"][0]["text"] == text
    assert project_state.load_project(tmp_path) == saved


def test_absent_project_is_empty_without_writes(tmp_path):
    assert project_state.load_project(tmp_path) == {"schema_version": 1, "modules": []}
    assert list(tmp_path.iterdir()) == []


def test_project_persists_independently_of_version_files(tmp_path):
    versions = tmp_path / "versions"
    versions.mkdir()
    (versions / "v1.html").write_text("First review")
    (tmp_path / "cards.json").write_text("[]")
    (tmp_path / "comments.json").write_text("[]")
    (tmp_path / "current.meta.json").write_text('{"current":"v1"}')
    saved = project_state.save_project(tmp_path, _project())
    (versions / "v2.html").write_text("Next review")
    (tmp_path / "current.meta.json").write_text('{"current":"v2"}')
    assert project_state.load_project(tmp_path) == saved
    assert (versions / "v1.html").read_text() == "First review"
    assert (tmp_path / "cards.json").read_text() == "[]"
    assert (tmp_path / "comments.json").read_text() == "[]"
    assert {module["id"] for module in saved["modules"]} == {"hosted-pages", "progress", "notes"}


@pytest.mark.parametrize("raw", [
    b"{",
    b"null",
    b'"text"',
    b'{"modules":[],"schema_version":2}',
    b'{"modules":[],"modules":[]}',
    b'{"modules":[{"id":"notes","title":"N","kind":"notes","items":[{"text":"a","text":"b"}]}]}',
    b"\xff",
    b"[" * 1000 + b"]" * 1000,
    b" " * (64 * 1024 + 1),
])
def test_loading_malformed_or_oversized_file_raises(tmp_path, raw):
    (tmp_path / "project.json").write_bytes(raw)
    with pytest.raises(ValueError):
        project_state.load_project(tmp_path)


def test_save_refreshes_timestamp_and_creates_directory(tmp_path):
    data = _project()
    data["updated_at"] = "2020-01-01T00:00:00Z"
    slug_dir = tmp_path / "new" / "project"
    saved = project_state.save_project(slug_dir, data)
    assert saved["updated_at"] != data["updated_at"]
    assert project_state.load_project(slug_dir) == saved
    assert json.loads((slug_dir / "project.json").read_text()) == saved


@pytest.mark.parametrize("failure", ["replace", "fsync"])
def test_atomic_failure_preserves_previous_project_and_cleans_tempfile(tmp_path, monkeypatch, failure):
    saved = project_state.save_project(tmp_path, _project())
    original = (tmp_path / "project.json").read_bytes()
    data = _project()
    data["title"] = "New title"

    def fail(*args):
        raise OSError("Simulated storage failure")

    monkeypatch.setattr(project_state.os, failure, fail)
    with pytest.raises(OSError, match="Simulated"):
        project_state.save_project(tmp_path, data)
    assert (tmp_path / "project.json").read_bytes() == original
    assert project_state.load_project(tmp_path) == saved
    assert list(tmp_path.glob(".project.*.tmp")) == []


def test_validation_failure_never_changes_existing_project(tmp_path):
    project_state.save_project(tmp_path, _project())
    original = (tmp_path / "project.json").read_bytes()
    with pytest.raises(ValueError):
        project_state.save_project(tmp_path, {"modules": [], "html": "unrecognized"})
    assert (tmp_path / "project.json").read_bytes() == original


def test_atomic_writes_use_unique_same_directory_temporary_files_and_fsync(tmp_path, monkeypatch):
    replacements = []
    syncs = []
    original_replace = project_state.os.replace
    original_fsync = project_state.os.fsync

    def record_replace(source, destination):
        replacements.append((source, destination))
        return original_replace(source, destination)

    def record_fsync(fd):
        syncs.append(fd)
        return original_fsync(fd)

    monkeypatch.setattr(project_state.os, "replace", record_replace)
    monkeypatch.setattr(project_state.os, "fsync", record_fsync)
    project_state.save_project(tmp_path, _project())
    changed = _project()
    changed["title"] = "Meaningful change"
    project_state.save_project(tmp_path, changed)
    assert len(replacements) == 2
    assert replacements[0][0] != replacements[1][0]
    assert all(source.parent == tmp_path for source, _ in replacements)
    assert all(destination == tmp_path / "project.json" for _, destination in replacements)
    assert len(syncs) == 4  # Each write syncs both file contents and directory entry.


def test_native_copy_is_one_tab_without_an_external_review_url():
    data = _project()
    data["tabs"] = [{"id": "copy", "label": "Copy", "kind": "copy"}]
    assert project_state.validate_project(data)["tabs"] == data["tabs"]
    for tab in ({"id": "copy", "label": "Copy", "kind": "copy", "url": "https://example.com/review"},
                {"id": "other", "label": "Copy", "kind": "copy"},
                {"id": "plan", "label": "Plan", "kind": "reference"}):
        data["tabs"] = [tab]
        with pytest.raises(ValueError):
            project_state.validate_project(data)


def test_issue_links_are_tracker_neutral_and_survive_noop(tmp_path):
    data = _project()
    data["issue_links"] = {
        "CHA-182": "https://linear.app/leadory/issue/CHA-182/home-speed",
        "agent-annotate-w6e.4": "https://board.example:8473/p/agent-annotate?bead=agent-annotate-w6e.4",
    }
    saved = project_state.save_project(tmp_path, data)
    assert project_state.load_project(tmp_path)["issue_links"] == data["issue_links"]
    original_mtime = (tmp_path / "project.json").stat().st_mtime_ns
    assert project_state.save_project(tmp_path, data) == saved
    assert (tmp_path / "project.json").stat().st_mtime_ns == original_mtime
    del data["issue_links"]
    data["modules"][1]["items"][0]["detail"] = "New progress"
    project_state.save_project(tmp_path, data)
    assert project_state.load_project(tmp_path)["issue_links"] == saved["issue_links"]


@pytest.mark.parametrize("links", [
    [], {"<script>": "https://tracker.example/CHA-1"}, {"CHA": "https://tracker.example/CHA"},
    {"CHA-1": "javascript:alert(1)"}, {"CHA-1": "https://user:secret@tracker.example/CHA-1"},
    {"CHA-1": "https://tracker.example/a b"},
])
def test_issue_links_reject_unsafe_targets(links):
    with pytest.raises(ValueError):
        project_state.validate_project({"modules": [], "issue_links": links})


def test_board_is_tracker_neutral_and_its_directory_stays_off_the_page(tmp_path):
    data = _project()
    data["board"] = {"url": "https://host.example:8473/p/agent-annotate", "project": "agent-annotate",
                     "label": "Beads", "dir": "/srv/beads/agent-annotate"}
    saved = project_state.save_project(tmp_path, data)
    assert saved["board"] == dict(data["board"], prefix="agent-annotate")
    del data["board"]
    project_state.save_project(tmp_path, data)
    assert project_state.load_project(tmp_path)["board"]["project"] == "agent-annotate"
    for bad in ({"url": "javascript:x", "project": "a"}, {"url": "https://h/p", "project": "../x"},
                {"url": "https://h/p", "project": "a", "dir": "relative/dir"},
                {"url": "https://h/p", "project": "a", "tracker": "linear"}):
        with pytest.raises(ValueError):
            project_state.validate_project({"modules": [], "board": bad})


def test_board_ready_count_is_cached_and_never_waits_for_bd(tmp_path, monkeypatch):
    import threading

    from agent_annotate import board as board_module
    release = threading.Event()
    calls = []

    def slow(board):
        calls.append(board["project"])
        release.wait(5)
        return 7

    monkeypatch.setattr(board_module, "ready_count", slow)
    monkeypatch.setattr(board_module, "_cache", {})
    monkeypatch.setattr(board_module, "_refreshing", set())
    info = {"url": "https://h.example/p/x", "project": "x", "label": "Beads", "prefix": "x", "dir": "/srv/x"}
    first = board_module.board_status(info)
    assert first["ready"] is None and "dir" not in first["board"]
    assert board_module.board_status(info)["ready"] is None and calls == ["x"]
    release.set()
    for _ in range(50):
        if board_module.board_status(info)["ready"] == 7:
            break
        threading.Event().wait(0.05)
    assert board_module.board_status(info)["ready"] == 7 and calls == ["x"]
    assert board_module.board_status(None) == {"board": None, "ready": None, "checked_at": None}


def test_board_ready_count_runs_bd_ready_in_the_board_directory(tmp_path, monkeypatch):
    from agent_annotate import board as board_module
    fake = tmp_path / "bd"
    fake.write_text('#!/bin/sh\nprintf \'%s\\n\' "$@" > "$(dirname "$0")/args"\necho \'[{"id":"x-1"},{"id":"x-2"}]\'\n')
    fake.chmod(0o755)
    monkeypatch.setenv("ANNOTATE_BD", str(fake))
    assert board_module.ready_count({"project": "x", "dir": str(tmp_path)}) == 2
    assert (tmp_path / "args").read_text().splitlines() == ["-C", str(tmp_path), "ready", "--json", "--brief", "-n", "0", "--exclude-type", "epic", "--readonly"]
    # No directory and no reachable board API: no count, no error.
    assert board_module.board_status({"url": "https://h/p", "project": "nowhere", "prefix": "nowhere"})["ready"] is None
