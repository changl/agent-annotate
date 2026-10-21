"""Stable page names across readers and a zero-write migration preview."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_decision_api import _call
from test_decision_api import server as server

from agent_annotate import cli, page_names, paths, project_state, workspace
from agent_annotate.hooks import session_start
from agent_annotate.pagegen import PageGenError, generate


def snapshot(directory):
    return {str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob("*") if p.is_file()}


def test_resolution_is_read_only_and_has_no_slug_display_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_registry_entries", lambda: [])
    record = {"slug_dir": str(tmp_path), "title": "Legacy title"}
    assert page_names.page_name(record) == "Legacy title"
    assert page_names.page_name(tmp_path) == "Untitled page"
    (tmp_path / "versions").mkdir()
    (tmp_path / "versions/v10.html").write_text("<title>New revision</title>")
    (tmp_path / "versions/v2.html").write_text("<title>First &amp; stable</title>")
    assert page_names.page_name(tmp_path) == "First & stable"
    (tmp_path / "current.meta.json").write_text('{"name":"Canonical name"}')
    before = snapshot(tmp_path)
    assert page_names.page_name(record) == "Canonical name"
    assert snapshot(tmp_path) == before
    (tmp_path / "current.meta.json").write_text("[]")
    assert page_names.page_name(tmp_path) == "First & stable"


def test_revision_titles_do_not_rename_page_and_explicit_title_does(tmp_path):
    source = tmp_path / "page.md"
    directory = tmp_path / "assessment"
    source.write_text("---\ntitle: Original assessment\n---\n## Scope\nInitial text.\n")
    first = generate(source, directory, title="Assessment")
    source.write_text("---\ntitle: Assessment round 2 results\n---\n## Scope\nRevised text.\n")
    second = generate(source, directory, "v2")
    assert first["name"] == second["name"] == page_names.page_name(directory) == "Assessment"
    assert second["title"] == "Assessment round 2 results"
    assert "<title>Assessment round 2 results</title>" in second["html"].read_text()
    generate(source, directory, "v3", title="Assessment and evidence")
    assert page_names.page_name(directory) == "Assessment and evidence"


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_legacy_name_is_frozen_before_replacing_its_document(tmp_path, version):
    source, directory = tmp_path / "page.md", tmp_path / "page"
    source.write_text("---\ntitle: Original assessment\n---\n## Scope\nInitial text.\n")
    generate(source, directory)
    meta = cli._read_meta(directory)
    del meta["name"]
    (directory / "current.meta.json").write_text(json.dumps(meta))
    source.write_text("---\ntitle: Revised assessment\n---\n## Scope\nRevised text.\n")
    result = generate(source, directory, version)
    assert result["name"] == page_names.page_name(directory) == "Original assessment"
    assert result["title"] == "Revised assessment"


@pytest.mark.parametrize("name", ["", " ", "x" * 161, "Name\nInjected", "<b>Name</b>", "hidden\u202ename"])
def test_bad_names_are_rejected_before_generation_writes(tmp_path, name):
    source = tmp_path / "page.md"
    source.write_text("## Scope\nText.\n")
    directory = tmp_path / "page"
    with pytest.raises(PageGenError):
        generate(source, directory, title=name)
    assert not directory.exists()


@pytest.fixture
def estate(tmp_path, monkeypatch):
    entries = []
    for slug, name in (("main", "Agent Annotate"), ("assessment", "Assessment"),
                       ("ownership", "Ownership"), ("operations", "Operations")):
        directory = tmp_path / slug
        directory.mkdir()
        (directory / "current.meta.json").write_text(json.dumps({"name": name, "current": "v1", "history": []}))
        record = {"slug_dir": str(directory), "url": f"https://reviews.test/{slug}/", "slug": slug,
                  "workspace_root": str(tmp_path), "workspace_primary": slug == "main"}
        entries.append(("reviews", slug, record))
    main = Path(entries[0][2]["slug_dir"])
    project_state.save_project(main, {"title": "Agent Annotate", "modules": [], "tabs": [
        {"id": s, "label": "Parent's stale label", "url": r["url"]} for _, s, r in entries[1:]]})
    monkeypatch.setattr(cli, "_registry_entries", lambda: entries)
    return entries


def test_workspace_and_project_tabs_use_the_targets_own_name(estate, tmp_path):
    data = workspace.workspace_data(tmp_path)
    project = page_names.project_payload(estate[0][2]["slug_dir"])
    links = project_state.linked_pages(estate[0][2])
    names = {p["slug"].split("/")[-1]: p["name"] for p in data["pages"]}
    assert data["workspace"]["name"] == project["name"] == "Agent Annotate"
    assert len(project["tabs"]) == len(links) == len(project["related_pages"]) == 3
    linked_by_slug = {p["slug"]: p for p in links}
    for tab in project["tabs"]:
        linked = linked_by_slug[tab["slug"]]
        assert tab["label"] == tab["name"] == names[tab["slug"]] == linked["name"] == linked["title"]
    assert all(set(p) <= {"slug", "name", "url", "reason"} for p in project["related_pages"])


def test_migration_dry_run_backups_apply_and_idempotence(estate, tmp_path, capsys):
    mapping = {f"{p}/{s}": page_names.page_name(r) for p, s, r in estate}
    for _, _, record in estate:
        path = Path(record["slug_dir"]) / "current.meta.json"
        path.write_text('{"current":"v1","history":[],"owner":{"owner_session":"keep"}}\n')
    source = tmp_path / "names.json"
    source.write_text(json.dumps(mapping))
    args = SimpleNamespace(from_file=str(source), apply=False, dry_run=True, json=True)
    before = snapshot(tmp_path)
    mtimes = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")}
    assert page_names.cmd_names(args) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["dry_run"] and preview["changed_files"] == 5 and preview["backups"] == []
    assert snapshot(tmp_path) == before
    assert {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")} == mtimes
    args.apply, args.dry_run = True, False
    assert page_names.cmd_names(args) == 0
    applied = json.loads(capsys.readouterr().out)
    assert len(applied["backups"]) == 4
    for backup in map(Path, applied["backups"]):
        assert not backup.is_relative_to(tmp_path)
        for original in backup.glob("*.json"):
            if original.name != "manifest.json":
                assert original.read_bytes() in before.values()
    meta = json.loads((tmp_path / "main/current.meta.json").read_text())
    assert meta["owner"] == {"owner_session": "keep"} and meta["name"] == "Agent Annotate"
    assert all("label" not in tab for tab in project_state.load_project(tmp_path / "main")["tabs"])
    assert [t["name"] for t in page_names.project_payload(tmp_path / "main")["tabs"]] == ["Assessment", "Ownership", "Operations"]
    assert page_names.cmd_names(args) == 0
    repeated = json.loads(capsys.readouterr().out)
    assert repeated["changed_files"] == 0 and repeated["backups"] == []


@pytest.mark.parametrize("existed", [False, True])
def test_migration_manifest_can_restore_exact_original_bytes(estate, tmp_path, capsys, existed):
    import hashlib

    directory = Path(estate[0][2]["slug_dir"])
    meta = directory / "current.meta.json"
    if existed:
        meta.write_bytes(b'{\r\n "current": "v1", "owner": {"label": "caf\\u00e9"}\r\n}\r\n')
    else:
        meta.unlink()
    before = snapshot(directory)
    source = tmp_path / "names.json"
    source.write_text('{"reviews/main":"团队 🐳"}')
    assert page_names.cmd_names(SimpleNamespace(from_file=str(source), apply=True, json=True)) == 0
    result = json.loads(capsys.readouterr().out)
    for backup in map(Path, result["backups"]):
        for entry in json.loads((backup / "manifest.json").read_text()):
            path = Path(entry["path"])
            if entry["existed"]:
                original = (backup / entry["file"]).read_bytes()
                assert hashlib.sha256(original).hexdigest() == entry["sha256"]
                path.write_bytes(original)
            else:
                path.unlink()
    assert meta.exists() == existed
    assert all((directory / path).read_bytes() == original for path, original in before.items())


def test_migration_waits_for_server_metadata_lock_and_keeps_its_fields(estate, tmp_path, monkeypatch):
    import contextlib
    import fcntl
    import threading
    from concurrent.futures import ThreadPoolExecutor

    directory = Path(estate[0][2]["slug_dir"])
    meta = directory / "current.meta.json"
    source = tmp_path / "names.json"
    source.write_text('{"reviews/main":"Assessment"}')
    attempted = threading.Event()
    original_flock = cli._flock

    @contextlib.contextmanager
    def observe_lock(lock_path):
        if lock_path == directory / "current.meta.json.lock":
            attempted.set()
        with original_flock(lock_path):
            yield

    monkeypatch.setattr(cli, "_flock", observe_lock)
    with ThreadPoolExecutor(max_workers=1) as worker:
        with (directory / "current.meta.json.lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            future = worker.submit(page_names.cmd_names, SimpleNamespace(from_file=str(source), apply=True, json=True))
            assert attempted.wait(3)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.1)
            fresh = json.loads(meta.read_bytes())
            fresh.update(owner={"owner_session": "keep"}, content_stamps={"v1": {"whole": "server-stamp"}})
            meta.write_text(json.dumps(fresh))
        assert future.result(timeout=3) == 0
    renamed = json.loads(meta.read_bytes())
    assert renamed["name"] == "Assessment"
    assert renamed["owner"] == fresh["owner"] and renamed["content_stamps"] == fresh["content_stamps"]


def test_invalid_migration_does_not_partially_update_pages(estate, tmp_path, capsys):
    source = tmp_path / "names.json"
    source.write_text(json.dumps({"reviews/main": "Renamed", "reviews/missing": "No page"}))
    before = snapshot(tmp_path)
    assert page_names.cmd_names(SimpleNamespace(from_file=str(source), apply=True, json=True)) == 2
    assert "no unique registered page" in capsys.readouterr().out
    assert snapshot(tmp_path) == before
    estate[0][2]["slug_dir"] = str(tmp_path / "missing-page")
    source.write_text('{"reviews/main":"Renamed"}')
    before = snapshot(tmp_path)
    assert page_names.cmd_names(SimpleNamespace(from_file=str(source), apply=True, json=True)) == 2
    assert "directory must exist and be absolute" in capsys.readouterr().out
    assert snapshot(tmp_path) == before


def test_duplicate_migration_identity_is_rejected_without_writes(estate, tmp_path, capsys):
    source = tmp_path / "names.json"
    source.write_text('{"reviews/main":"One","reviews/main":"Two"}')
    before = snapshot(tmp_path)
    assert page_names.cmd_names(SimpleNamespace(from_file=str(source), apply=True, json=True)) == 2
    assert "duplicate migration field" in capsys.readouterr().out
    assert snapshot(tmp_path) == before


def test_migration_rechecks_archive_state_after_taking_locks(estate, tmp_path, monkeypatch, capsys):
    import contextlib

    directory = Path(estate[0][2]["slug_dir"])
    path = directory / "current.meta.json"
    before = path.read_bytes()
    source = tmp_path / "names.json"
    source.write_text('{"reviews/main":"Renamed"}')
    original_flock = cli._flock

    @contextlib.contextmanager
    def archive_before_lock(lock_path):
        if lock_path == directory / "current.meta.json.lock":
            (directory / "archived.json").write_text('{"why":"Archived concurrently"}')
        with original_flock(lock_path):
            yield

    monkeypatch.setattr(cli, "_flock", archive_before_lock)
    assert page_names.cmd_names(SimpleNamespace(from_file=str(source), apply=True, json=True)) == 2
    assert "read-only" in capsys.readouterr().out
    assert path.read_bytes() == before


def test_names_are_operator_only():
    assert "names" not in cli.AGENT_COMMANDS
    assert "names" not in cli.build_parser().format_help()
    assert "names" in cli.build_parser(all_commands=True).format_help()


def test_legacy_meta_and_broken_project_fallback_keep_the_page_name(server):
    httpd, directory, _ = server
    (directory / "current.meta.json").unlink()
    (directory / "current.html").write_text("<title>Legacy assessment</title>")
    assert _call(httpd, "GET", "/current.meta.json")[1]["name"] == "Legacy assessment"
    (directory / "project.json").write_text("broken json")
    meta = _call(httpd, "GET", "/current.meta.json")[1]
    assert meta["name"] == meta["project_info"]["name"] == "Legacy assessment"
    assert not (directory / "current.meta.json").exists()


def test_project_meta_categories_workspace_and_notice_agree(server, monkeypatch, capsys):
    httpd, directory, _ = server
    cli._write_meta_locked(directory, lambda meta: meta.update(name="Agent Annotate"))
    main = {"slug_dir": str(directory), "url": "https://reviews.test/main/", "workspace_primary": True,
            "workspace_root": str(directory.parent), "port": httpd.server_address[1]}
    entries = [("reviews", "review", main)]
    expected = {"assessment": "Assessment", "ownership": "Ownership", "operations": "Operations"}
    for slug, name in expected.items():
        child = directory.parent / slug
        child.mkdir()
        (child / "current.meta.json").write_text(json.dumps({"name": name}))
        entries.append(("reviews", slug, {"slug_dir": str(child), "url": f"https://reviews.test/{slug}/",
                                          "workspace_root": str(directory.parent)}))
    monkeypatch.setattr(cli, "_registry_entries", lambda: entries)
    monkeypatch.setattr(httpd.RequestHandlerClass, "_registered_record", lambda self: main)
    state_dir = paths.STATE_DIR / directory.parent.name
    state_dir.mkdir(parents=True)
    (state_dir / "reviews.json").write_text(json.dumps({"project": "reviews", "slugs": {s: r for _, s, r in entries}}))
    monkeypatch.setattr(paths, "STATE_DIR", state_dir)
    project_state.save_project(directory, {"modules": [], "tabs": [{"id": s, "url": r["url"]} for _, s, r in entries[1:]]})
    project = _call(httpd, "GET", "/api/project")[1]
    meta = _call(httpd, "GET", "/current.meta.json")[1]
    categories = _call(httpd, "GET", "/api/categories")[1]
    assert project["name"] == meta["name"] == workspace.workspace_data(directory.parent)["workspace"]["name"] == "Agent Annotate"
    assert {t["slug"]: t["label"] for t in project["tabs"]} == expected
    assert {p["slug"]: p["name"] for p in categories["linked_pages"]} == expected
    monkeypatch.chdir(directory.parent)
    assert cli.run_command(cli.build_parser().parse_args(["workspace", "--json"])) == 0
    data = json.loads(capsys.readouterr().out)
    assert {p["slug"].split("/")[-1]: p["name"] for p in data["pages"] if p["slug"] != "reviews/review"} == expected
    assert "Agent Annotate https://reviews.test/main/" in session_start.notice(directory.parent)
