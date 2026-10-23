"""History revalidation, append reuse, and CLI writes against an open server."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from test_fast_writes import request
from test_fast_writes import server as server

from agent_annotate import cli, pagegen, paths, review_history


@pytest.mark.parametrize("encoding", ["identity", "gzip"])
def test_unchanged_history_reuses_the_encoded_response(server, monkeypatch, encoding):
    httpd, _, _, _ = server
    headers = {"Accept-Encoding": encoding}
    status, response, _ = request(httpd, "/api/history", headers=headers)
    assert status == 200

    def unexpected(*args, **kwargs):
        raise AssertionError("unchanged history must not rebuild or recompress")
    monkeypatch.setattr(review_history, "review_history", unexpected)
    monkeypatch.setattr(httpd.RequestHandlerClass, "_v2_load", unexpected)
    monkeypatch.setattr("agent_annotate.sync_server.gzip.compress", unexpected)
    status, cached, body = request(httpd, "/api/history", headers={**headers, "If-None-Match": response["ETag"]})
    assert status == 304 and body == b"" and cached["ETag"] == response["ETag"]


@pytest.mark.parametrize("change", ["meta", "store", "rounds", "bus", "archive", "availability"])
def test_history_invalidates_all_disk_dependencies(server, monkeypatch, change):
    httpd, root, _, _ = server
    (root / "current.meta.json").write_text(json.dumps({"current": "v1", "history": [
        {"version": "v1", "ts": "2026-10-01T00:00:00Z"}]}))
    archive = root / "archive"
    monkeypatch.setattr(paths, "BUS_ARCHIVE_ROOT", archive)
    before = request(httpd, "/api/history")[1]["ETag"]
    event = {"event": "round_submitted", "round_id": "new-round", "id": "new-round", "answers": []}
    if change == "meta":
        meta = root / "current.meta.json"
        meta.write_text(meta.read_text().replace('"v1"', '"v2"'))
    elif change == "store":
        path = root / "comments.json"
        data = json.loads(path.read_text())
        data["anchors"]["s:test"][0]["decision"] = {
            "verdict": "comment", "text": "New answer", "ts": "2026-10-02T00:00:00Z"}
        path.write_text(json.dumps(data))
    elif change == "availability":
        (root / "versions").mkdir()
        (root / "versions/v1.html").write_text("Saved version")
    else:
        path = {"rounds": root / "rounds.ndjson", "bus": root / "project/page.ndjson",
                "archive": archive / "20261001/project/page.ndjson"}[change]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(event) + "\n")
    status, headers, body = request(httpd, "/api/history", headers={"If-None-Match": before})
    assert status == 200 and headers["ETag"] != before
    assert json.loads(body) == review_history.review_history(root, root / "project/page.ndjson", archive)
    if change in {"rounds", "bus", "archive", "availability"}:
        (root / "versions/v1.html" if change == "availability" else path).unlink()
        assert request(httpd, "/api/history", headers={"If-None-Match": headers["ETag"]})[0] == 200


def test_cold_history_does_not_hold_the_comment_transaction_lock(server, monkeypatch):
    httpd, _, _, _ = server
    started, release = threading.Event(), threading.Event()
    original = review_history.review_history

    def blocked(*args, **kwargs):
        started.set()
        assert release.wait(3)
        return original(*args, **kwargs)
    monkeypatch.setattr(review_history, "review_history", blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(request, httpd, "/api/history")
        try:
            assert started.wait(1)
            assert request(httpd, "/api/comments", "POST", {"anchor_id": "s:test", "text": "During history"})[0] == 201
            assert not release.is_set()
        finally:
            release.set()
        assert pending.result()[0] == 200


def test_history_retries_when_a_round_is_submitted_during_reconstruction(server, monkeypatch):
    httpd, root, _, release = server
    release.set()
    (root / "current.meta.json").write_text(json.dumps({"current": "v1", "history": [
        {"version": "v1", "ts": "2026-01-01T00:00:00Z"}]}))
    assert request(httpd, "/api/comments/card/decision", "POST", {
        "verdict": "accept", "defer_push": True})[0] == 200
    original = review_history.review_history
    calls = []

    def submit(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            assert request(httpd, "/api/rounds/submit", "POST", {"version": "v1"})[0] == 200
        return original(*args, **kwargs)

    monkeypatch.setattr(review_history, "review_history", submit)
    status, headers, body = request(httpd, "/api/history")
    expected = original(root, root / "project/page.ndjson", paths.BUS_ARCHIVE_ROOT)
    assert status == 200 and json.loads(body) == expected
    assert len(calls) == 2
    assert request(httpd, "/api/history", headers={"If-None-Match": headers["ETag"]})[0] == 304


def test_history_bus_cache_has_a_total_prefix_and_source_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(review_history, "_BUS_CACHE_BYTES", 180)
    monkeypatch.setattr(review_history, "_BUS_CACHE_FILES", 2)
    cache = {}
    for index in range(5):
        path = tmp_path / f"{index}.ndjson"
        path.write_text(json.dumps({"event": "round_submitted", "round_id": str(index)}) + "\n")
        assert review_history._bus_rounds(path, cache)[0]["round_id"] == str(index)
        assert len(cache) <= 2
        assert sum(len(prefix) for prefix, _ in cache.values()) <= 180
    path.write_text(path.read_text() + '{"event":"noop"}\n' * 100)
    assert review_history._bus_rounds(path, cache)[0]["round_id"] == "4"
    assert sum(len(prefix) for prefix, _ in cache.values()) <= 180


@pytest.mark.parametrize("change", ["append", "rewrite_longer", "truncate", "rotate", "archive", "rounds_rewrite"])
def test_cached_history_matches_uncached_builder_after_bus_changes(server, monkeypatch, change):
    httpd, root, _, _ = server
    bus = root / "project/page.ndjson"
    archive = root / "archive"
    monkeypatch.setattr(paths, "BUS_ARCHIVE_ROOT", archive)
    bus.parent.mkdir(exist_ok=True)

    def event(identifier):
        return json.dumps({"event": "round_submitted", "round_id": identifier, "id": identifier,
                           "ts": "2026-10-01T00:00:00Z", "answers": [{"text": identifier}]}) + "\n"

    bus.write_text(event("old"))
    rounds = root / "rounds.ndjson"
    rounds.write_text(event("receipt"))
    before = request(httpd, "/api/history")[1]["ETag"]
    if change == "append":
        with bus.open("a") as output:
            output.write(event("new"))
    elif change == "rewrite_longer":
        bus.write_text(event("replacement") + '{"event":"noop"}\n' * 100)
    elif change == "truncate":
        bus.write_text("")
    elif change == "rotate":
        bus.rename(bus.with_suffix(".old"))
        bus.write_text(event("new"))
    elif change == "archive":
        archived = archive / "20261001/project/page.ndjson"
        archived.parent.mkdir(parents=True)
        bus.rename(archived)
        bus.write_text(event("new"))
    else:
        rounds.write_text(event("rewritten-receipt"))
    expected = review_history.review_history(root, bus, archive)
    status, headers, body = request(httpd, "/api/history", headers={"If-None-Match": before})
    assert status == 200 and json.loads(body) == expected
    assert request(httpd, "/api/history", headers={"If-None-Match": headers["ETag"]})[0] == 304


def test_history_does_not_return_a_mixed_revision_under_continuous_writes(server, monkeypatch):
    httpd, root, _, _ = server
    original = review_history.review_history

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        with (root / "rounds.ndjson").open("a") as output:
            output.write('{"id":"another round"}\n')
        return result

    monkeypatch.setattr(review_history, "review_history", changed)
    assert request(httpd, "/api/history")[0] == 503
    assert httpd.RequestHandlerClass._history_responses == {}


def test_bus_cache_checks_exact_prefix_and_retries_partial_lines(tmp_path, monkeypatch):
    (tmp_path / "current.meta.json").write_text('{"history":[]}')
    bus = tmp_path / "page.ndjson"
    bus.write_text('{"event":"noop"}\n' * 1000)
    cache = {}
    assert review_history.review_history(tmp_path, bus, bus_cache=cache)["rounds"] == []
    loads = []
    original = json.loads

    def counted(data, *args, **kwargs):
        loads.append(True)
        return original(data, *args, **kwargs)
    monkeypatch.setattr(review_history.json, "loads", counted)
    with bus.open("a") as output:
        output.write('{"event":"round_submitted","round_id":"one","answers":[]}\n')
    assert review_history.review_history(tmp_path, bus, bus_cache=cache)["rounds"][0]["id"] == "one"
    assert len(loads) == 2  # metadata plus the appended line; no prefix replay
    with bus.open("a") as output:
        output.write('{"event":"round_submitted","round_id":"two"')
    assert len(review_history.review_history(tmp_path, bus, bus_cache=cache)["rounds"]) == 1
    with bus.open("a") as output:
        output.write(',"answers":[]}')  # complete JSON without a final newline
    assert len(review_history.review_history(tmp_path, bus, bus_cache=cache)["rounds"]) == 2
    with bus.open("a") as output:
        output.write('\n')
    assert len(review_history.review_history(tmp_path, bus, bus_cache=cache)["rounds"]) == 2
    # Same inode and a longer file are insufficient: rewritten prefixes reset.
    bus.write_text('{"event":"noop"}\n' * 1100 + '{"event":"round_submitted","round_id":"replacement","answers":[]}\n')
    assert [r["id"] for r in review_history.review_history(tmp_path, bus, bus_cache=cache)["rounds"]] == ["replacement"]


def test_cli_writes_are_visible_on_the_next_conditional_get(server, monkeypatch):
    httpd, root, _, _ = server
    record = {"slug_dir": str(root), "port": httpd.server_port, "project": "project", "slug": "page",
              "local_url": f"http://127.0.0.1:{httpd.server_port}/", "bus_file": str(root / "project/page.ndjson")}
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("project", "page", record)])
    (root / "versions").mkdir()
    (root / "versions/v1.html").write_text('<p data-anchor-id="s:test">Evidence</p>')
    source = root / "cards.json"
    source.write_text(json.dumps([{"anchor_id": "d:q2", "number": 2, "decision_request": {
        "prompt": "New CLI question?", "evidence": [{"anchor": "s:test"}]}}]))

    def validators(*routes):
        return {route: request(httpd, route)[1]["ETag"] for route in routes}

    def changed(before):
        bodies = {}
        for route, etag in before.items():
            status, headers, body = request(httpd, route, headers={"If-None-Match": etag})
            assert status == 200 and headers["ETag"] != etag, route
            bodies[route] = json.loads(body)
        return bodies

    before = validators("/comments.json?view=poll", "/api/categories")
    assert cli.cmd_ask(SimpleNamespace(slug="project/page", from_file=str(source), version="v1",
                                       project=None, author="agent:test", json=True)) == 0
    data = changed(before)
    card = data["/comments.json?view=poll"]["anchors"]["d:q2"][0]
    assert card["decision_request"]["prompt"] == "New CLI question?"
    before = validators("/comments.json?view=poll", "/api/categories")
    assert cli.cmd_withdraw(SimpleNamespace(slug="project/page", comment_id=card["id"], why="Superseded",
                                            project=None, author="agent:test", json=True)) == 0
    assert changed(before)["/comments.json?view=poll"]["anchors"]["d:q2"][0]["withdrawn"]
    before = validators("/comments.json?view=poll", "/api/categories")
    assert cli.cmd_resolve(SimpleNamespace(slug="project/page", comment_id="card", in_version="v1", anchor="s:test",
                                           project=None, author="agent:test", json=True)) == 0
    assert changed(before)["/comments.json?view=poll"]["anchors"]["s:test"][0]["resolved_in_version"] == "v1"
    before = validators("/current.meta.json", "/api/history")
    markdown = root / "next.md"
    markdown.write_text("---\ntitle: Next version\n---\n\n## Evidence\n\nUpdated via CLI.\n")
    monkeypatch.setattr(pagegen, "_call_publish", lambda *args: 0)  # no transport/installation changes
    assert pagegen.cmd_new(SimpleNamespace(slug_dir=str(root), from_file=str(markdown), version="v2", label=None,
                                          project="project", publish=True, ask=False)) == 0
    assert changed(before)["/current.meta.json"]["current"] == "v2"
    before = validators("/current.meta.json", "/api/history")
    assert cli.cmd_publish_version(SimpleNamespace(slug_dir=str(root), version="v1", label="CLI republish", project=None)) == 0
    assert changed(before)["/current.meta.json"]["current"] == "v1"
