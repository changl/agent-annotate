"""Real command paths preserve one page across providers, aliases, and updates."""

import http.client
import http.server
import json
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_annotate import cli, delivery, pagegen, review_access, transports, workspace
from agent_annotate.sync_server import make_handler
from agent_annotate.urls import page_url


def _publish_args(directory, project=None):
    return SimpleNamespace(slug_dir=str(directory), project=project, port=None, transport=None,
                           hostname=None, path_prefix=None, standalone=False, public=False,
                           skip_js_lint=False, no_verify=False, verify_timeout=1)


def _new_args(directory, source, project, version="v2", ask=True):
    return SimpleNamespace(slug_dir=str(directory), from_file=str(source), project=project,
                           version=version, label=None, publish=True, ask=ask, example=False,
                           standalone=False, port=None, transport=None, hostname=None, public=False)


def _provider(monkeypatch, provider, session):
    for name in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID", "CLAUDE_AGENT_ID", "CODEX_THREAD_ID", "ANNOTATE_AUTHOR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID" if provider == "claude" else "CODEX_THREAD_ID", session)


@pytest.fixture
def estate(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "remote.origin.url",
                    "https://example.test/team/project.git"], check=True)
    monkeypatch.chdir(repo)
    for name, path in {"STATE_DIR": tmp_path / "state", "LOCK_DIR": tmp_path / "locks",
                       "BUS_ROOT": tmp_path / "bus", "CONFIG_DIR": tmp_path / "config",
                       "PROJECTS_TOML": tmp_path / "config" / "projects.toml"}.items():
        monkeypatch.setattr(cli, name, path)
    monkeypatch.setattr(review_access, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(cli, "_ensure_shim_installed", lambda: (False, "inert"))
    monkeypatch.setattr(cli, "_ensure_hook_installed", lambda: (False, "inert"))
    monkeypatch.setattr(cli, "_check_js_lint", lambda *args, **kwargs: (True, []))
    monkeypatch.setattr(cli, "_run_gate", lambda *args: None)
    monkeypatch.setattr(cli, "_route_host", lambda record: None)
    monkeypatch.setattr(cli, "_inv", lambda: "annotate")
    monkeypatch.setattr(cli, "_api", lambda *args, **kwargs: pytest.fail("Unexpected HTTP write"))
    live = set()
    routes, starts = [], []
    counter = iter(range(18000, 19000))
    mutex = threading.Lock()

    def port(*args, **kwargs):
        with mutex:
            return next(counter)

    def route(slug, port, **kwargs):
        with mutex:
            routes.append((slug, port))
        url = f"https://reviews.example/{slug}/"
        return {"url": url, "details": {"transport": "funnel", "public_url": url}}

    def start(directory, port, bus_dir, mount):
        with mutex:
            pid = 100000 + len(starts)
            starts.append((str(directory), port, str(bus_dir), mount))
            live.add(pid)
        return pid

    def target(session, agent):
        return {"session": session, "handle": "test-terminal", "incarnation": "test-incarnation",
                "agent": "claude" if agent == "claude-code" else "codex", "terminal_name": "Build",
                "project": "Project", "workspace": "Main", "label": "Project > Main > Build [test-terminal]"}

    monkeypatch.setattr(cli, "_find_free_port_after", port)
    monkeypatch.setattr(cli, "_start_server", start)
    monkeypatch.setattr(cli, "_is_process_alive", lambda pid: pid in live)
    monkeypatch.setattr(delivery, "capture_target", target)
    monkeypatch.setattr(transports, "load", lambda name: SimpleNamespace(publish=route))
    _provider(monkeypatch, "codex", "original-owner")
    directory = tmp_path / "reviews" / "workspace"
    source = tmp_path / "initial.md"
    source.write_text("---\ntitle: Project\n---\n\n# Project\n\n## Progress\n\nBuild passed.\n")
    pagegen.generate(source, directory, version="v1")
    return SimpleNamespace(root=tmp_path, repo=repo, directory=directory, routes=routes, starts=starts,
                           route=route, mutex=mutex)


def _initial(estate):
    assert cli.cmd_publish(_publish_args(estate.directory, "canonical")) == 0
    record = cli._load_state_for_project("canonical")["slugs"]["workspace"]
    assert record["workspace_key"] == workspace.project_key(estate.repo)
    assert record["transport"] == "funnel"
    assert len(estate.routes) == len(estate.starts) == 1
    return record


@pytest.mark.parametrize("provider", ["claude", "codex"])
@pytest.mark.parametrize("alias", [None, "new-project-alias"])
def test_reused_directory_keeps_canonical_scope_through_publish_version_and_ask(estate, monkeypatch, capsys,
                                                                              provider, alias):
    record = _initial(estate)
    full_url = page_url(record)
    before_meta = json.loads((estate.directory / "current.meta.json").read_text())
    confirmed = {"schema_version": 2, "anchors": {"s:progress:p1": [
        {"id": "aaaaaaaaaaaa", "anchor_id": "s:progress:p1", "version": "v1", "number": 1,
         "text": "Prior decision", "author": "agent:codex", "status": "user_confirmed",
         "decision": {"verdict": "accept", "by": "reviewer", "text": "Keep this explanation"},
         "decision_history": [{"verdict": "comment", "text": "Earlier explanation"}]}]}, "archived": {}}
    comments = estate.directory / "comments.json"
    comments.write_text(json.dumps(confirmed))
    before_comments = comments.read_bytes()
    _provider(monkeypatch, provider, f"successor-{provider}")

    assert cli.cmd_publish(_publish_args(estate.directory, alias)) == 0
    source = estate.root / "review.md"
    source.write_text('---\ntitle: Project\n---\n\n# Project\n\n## Progress\n\nPreview passed.\n\n'
                      '```cards\n[{"number":2,"anchor_id":"d:q2","decision_request":'
                      '{"prompt":"Publish the preview?","context":"Preview passed.","recommendation":"publish",'
                      '"options":[{"id":"publish","label":"Publish","consequence":"Public preview."},'
                      '{"id":"hold","label":"Hold","consequence":"Keep it private."}],'
                      '"evidence":[{"label":"Preview","anchor":"s:progress:p1"}]}}]\n```\n')
    asks = []

    def api(record, method, path, body, author, **kwargs):
        assert method == "POST" and path == "/api/comments/batch"
        asks.append((record["project"], record["slug"], body, author))
        return 200, {"ids": ["bbbbbbbbbbbb"], "created": 1, "updated": 0}

    monkeypatch.setattr(cli, "_api", api)
    assert pagegen.cmd_new(_new_args(estate.directory, source, alias)) == 0

    entries = cli._registry_entries()
    assert [(project, slug) for project, slug, _ in entries] == [("canonical", "workspace")]
    assert entries[0][2]["owner_session"] == record["owner_session"] == "original-owner"
    assert entries[0][2]["owner_target"] == record["owner_target"]
    assert page_url(entries[0][2]) == full_url
    assert len(estate.routes) == len(estate.starts) == 1
    assert comments.read_bytes() == before_comments
    meta = json.loads((estate.directory / "current.meta.json").read_text())
    assert meta["owner"] == before_meta["owner"]
    assert meta["history"][0] == before_meta["history"][0]
    assert [entry["version"] for entry in meta["history"]] == ["v1", "v2"]
    assert meta["current"] == "v2"
    assert (estate.directory / "current.html").resolve().name == "v2.html"
    assert len(asks) == 1 and asks[0][:2] == ("canonical", "workspace")
    assert asks[0][2]["items"][0]["version"] == "v2"
    assert asks[0][3].startswith("agent:")
    events = [json.loads(line) for line in Path(record["bus_file"]).read_text().splitlines()]
    assert any(event["event"] == "version_published" and event["version"] == "v2" for event in events)
    assert all(event["event"] not in {"round_submitted", "session_push"} for event in events)
    assert full_url in capsys.readouterr().out


@pytest.mark.parametrize("provider", ["claude", "codex"])
def test_progress_updates_keep_feedback_history_owner_and_url_without_rounds_or_identical_writes(estate, monkeypatch,
                                                                                              provider):
    record = _initial(estate)
    before_meta = (estate.directory / "current.meta.json").read_bytes()
    before_feedback = (estate.directory / "comments.json").read_bytes()
    bus = Path(record["bus_file"])
    before_bus = bus.read_bytes()
    before_registry = (cli.STATE_DIR / "canonical.json").read_bytes()
    _provider(monkeypatch, provider, f"successor-{provider}")
    progress = estate.root / "progress.json"
    progress.write_text(json.dumps({"modules": [{"id": "progress", "title": "Progress", "kind": "progress",
                                                 "items": [{"label": "Build", "status": "done",
                                                            "detail": "Checks passed."}]}]}))
    args = SimpleNamespace(slug="canonical/workspace", project=None, from_file=str(progress))
    assert cli.cmd_project(args) == 0
    project_file = estate.directory / "project.json"
    saved_bytes, saved_mtime = project_file.read_bytes(), project_file.stat().st_mtime_ns
    assert cli.cmd_project(args) == 0

    assert project_file.read_bytes() == saved_bytes
    assert project_file.stat().st_mtime_ns == saved_mtime
    assert bus.read_bytes() == before_bus
    assert (estate.directory / "current.meta.json").read_bytes() == before_meta
    assert (estate.directory / "comments.json").read_bytes() == before_feedback
    assert (cli.STATE_DIR / "canonical.json").read_bytes() == before_registry
    assert page_url(cli._load_state_for_project("canonical")["slugs"]["workspace"]) == page_url(record)
    assert len(estate.routes) == len(estate.starts) == 1


def test_concurrent_first_pages_with_provider_aliases_publish_only_one_route_and_registration(estate, monkeypatch):
    other = estate.root / "reviews" / "second"
    source = estate.root / "second.md"
    source.write_text("---\ntitle: Project\n---\n\n# Project\n\nBuild passed.\n")
    pagegen.generate(source, other, version="v1")
    caller = threading.local()
    key_barrier = threading.Barrier(2)
    both_routed = threading.Event()
    real_key = workspace.project_key

    def synchronized_key(path):
        key = real_key(path)
        if not getattr(caller, "key_checked", False):
            caller.key_checked = True
            key_barrier.wait(timeout=5)
        return key

    def route(*args, **kwargs):
        result = estate.route(*args, **kwargs)
        with estate.mutex:
            if len(estate.routes) > 1:
                both_routed.set()
        # If alias locks were independent, both would pass the empty-registry
        # check and route before either registration is committed.
        both_routed.wait(timeout=0.5)
        return result

    monkeypatch.setattr(workspace, "project_key", synchronized_key)
    monkeypatch.setattr(cli, "_session_id", lambda: caller.session)
    monkeypatch.setattr(cli, "_session_agent", lambda: caller.agent)
    monkeypatch.setattr(transports, "load", lambda name: SimpleNamespace(publish=route))

    def publish(provider, directory):
        caller.session = f"session-{provider}"
        caller.agent = "claude-code" if provider == "claude" else "codex"
        return cli.cmd_publish(_publish_args(directory, f"project-{provider}"))

    with ThreadPoolExecutor(max_workers=2) as workers:
        jobs = [workers.submit(publish, "claude", estate.directory), workers.submit(publish, "codex", other)]
        results = [job.result(timeout=10) for job in jobs]

    assert sorted(results) == [0, 2]
    entries = cli._registry_entries()
    assert len(entries) == len(estate.routes) == len(estate.starts) == 1
    record = entries[0][2]
    assert record["workspace_key"] == real_key(estate.repo)
    assert record["owner_agent"] in {"claude-code", "codex"}
    assert "#review=" in page_url(record)


@pytest.mark.parametrize("canonical", [True, False], ids=["numbered-decision", "legacy-anchor"])
def test_provider_author_change_preserves_canonical_decision_and_keeps_legacy_questions_separate(tmp_path, canonical):
    directory = tmp_path / "page"
    directory.mkdir()
    (directory / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {}, "archived": {}}))
    (directory / "current.meta.json").write_text(json.dumps({"current": "v1", "history": [{"version": "v1"}]}))
    handler = make_handler(artifact_dir=directory, public_base_path="", slug="test", bus_dir=tmp_path / "bus",
                           v2_mode=True, local_author="reviewer@example.test", local_author_name="Reviewer")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(path, body, agent=None):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=2)
        try:
            headers = {"Content-Type": "application/json"}
            if agent:
                headers["X-Annotate-Agent"] = agent
            connection.request("POST", path, json.dumps(body), headers)
            response = connection.getresponse()
            result = json.loads(response.read())
            assert 200 <= response.status < 300, result
            return result
        finally:
            connection.close()

    try:
        anchor = "d:q1" if canonical else "legacy:choice"
        item = {"anchor_id": anchor, "number": 1, "text": "Use SQLite?", "version": "v1",
                "decision_request": {"prompt": "Use SQLite?", "context": "Local storage.",
                                     "recommendation": "sqlite", "options": ["sqlite", "postgres"]}}
        first = request("/api/comments/batch", {"items": [item], "idempotency": "anchor"}, "agent:claude")
        comment_id = first["ids"][0]
        request(f"/api/comments/{comment_id}/decision",
                {"verdict": "comment", "text": "Explain the storage choice.", "defer_push": True})
        request(f"/api/comments/{comment_id}/decision",
                {"verdict": "select", "text": "sqlite\n\nUse the simplest option.", "defer_push": True})
        request(f"/api/comments/{comment_id}/reply", {"text": "Keep this explanation during handoff."})
        before = json.loads((directory / "comments.json").read_text())["anchors"][anchor][0]
        second_item = json.loads(json.dumps(item))
        if not canonical:
            second_item["text"] = second_item["decision_request"]["prompt"] = "A different legacy question?"
        second = request("/api/comments/batch", {"items": [second_item], "idempotency": "anchor"}, "agent:codex")
        cards = json.loads((directory / "comments.json").read_text())["anchors"][anchor]

        if canonical:
            assert len(cards) == 1, {"second_response": second,
                                     "cards": [(card["id"], card["author"], bool(card.get("decision"))) for card in cards]}
            assert second == {"ids": [comment_id], "created": 0, "updated": 1}
            assert cards[0]["edited_by"] == "agent:codex"
        else:
            assert len(cards) == 2
            assert second["created"] == 1 and second["updated"] == 0
            assert cards[1]["id"] != comment_id and cards[1]["author"] == "agent:codex"
            assert not cards[1].get("decision")
        for field in ("id", "created_at", "author", "version", "decision", "decision_history", "replies"):
            assert cards[0][field] == before[field]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
