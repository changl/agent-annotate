"""Writes commit before slow delivery; poll validators preserve auth and state."""
import gzip
import hashlib
import http.client
import json
import mmap
import os
import threading
import time

import pytest

from agent_annotate import delivery, sync_server
from agent_annotate.categories import publish_plan_revision


def request(server, path, method="GET", payload=None, headers=None):
    connection = http.client.HTTPConnection(*server.server_address, timeout=3)
    try:
        connection.request(method, path, json.dumps(payload) if payload is not None else None, headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


@pytest.fixture
def server(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    comment = {"id": "card", "anchor_id": "s:test", "version": "v1", "number": 1,
               "author": "agent:test", "status": "open", "text": "Choose", "replies": [],
               "decision_request": {"prompt": "Choose", "options": [{"id": "a", "label": "A"}]}}
    (root / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {"s:test": [comment]}, "archived": {}}))
    (root / "current.meta.json").write_text('{"current":"v1","history":[{"version":"v1"}]}')
    publish_plan_revision(root, "test", "<html><body>Plan</body></html>", title="Test")
    handler = sync_server.make_handler(root, slug="page", bus_dir=root / "project", local_author="reviewer@example.test")
    httpd = sync_server.ReviewHTTPServer(("127.0.0.1", 0), handler)
    record = {"slug_dir": str(root), "port": httpd.server_port, "owner_session": "test-owner",
              "owner_target": {"handle": "term_fake"}, "workspace_primary": True,
              "bus_file": str(root / "project/page.ndjson")}
    state_dir = root / "state"
    state_dir.mkdir()
    (state_dir / "project.json").write_text(json.dumps({"slugs": {"page": record}}))
    monkeypatch.setattr(sync_server, "STATE_DIR", state_dir)
    monkeypatch.setattr(delivery, "STATE_DIR", state_dir)
    from agent_annotate import cli
    monkeypatch.setattr(cli, "STATE_DIR", state_dir)
    started, release = threading.Event(), threading.Event()

    def slow_orca(*args):
        started.set()
        assert release.wait(3), "test must release fake Orca"
        return {"send": {"accepted": True}}

    monkeypatch.setattr(delivery, "_target_ready", lambda _: (True, ""))
    monkeypatch.setattr(delivery, "_orca", slow_orca)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd, root, started, release
    release.set()
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=2)


def test_every_write_returns_while_orca_delivery_is_blocked(server):
    httpd, root, started, release = server
    status, _, body = request(httpd, "/api/comments", "POST", {"anchor_id": "s:test", "text": "First"})
    assert status == 201
    cid = json.loads(body)["id"]
    delivery_ids = set()
    for path in ("/api/push-session", "/api/rounds/submit", f"/api/comments/{cid}/push"):
        # First push starts a deliberately blocked delivery. All subsequent
        # writes, including another Send, must still return after durable save.
        begin = time.monotonic()
        status, _, body = request(httpd, path, "POST", {"note": "Round"})
        assert status == 200 and time.monotonic() - begin < .5
        delivery_ids.add(json.loads(body)["delivery_id"])
        assert started.wait(1)
        assert not release.is_set()
    calls = [("/api/comments", "POST", {"anchor_id": "s:test", "text": "Second"}),
             (f"/api/comments/{cid}/reply", "POST", {"text": "Reply"}),
             (f"/api/comments/{cid}", "PUT", {"text": "Edit"}),
             ("/api/read-state", "POST", {"items": [{"id": cid, "sig": "x"}]}),
             ("/api/seen", "POST", {"version": "v1"})]
    calls += [("/api/comments/card/decision", "POST", {"verdict": verdict, "text": "Note", "defer_push": True})
              for verdict in ("accept", "select", "reject", "comment")]
    for path, method, payload in calls:
        begin = time.monotonic()
        status, _, _ = request(httpd, path, method, payload)
        assert status in (200, 201) and time.monotonic() - begin < .5
    # Responses were not premature acknowledgements: actual records are on disk.
    rounds = [json.loads(line) for line in (root / "rounds.ndjson").read_text().splitlines()]
    assert delivery_ids == {r["id"] for r in rounds}
    assert '"event": "session_push"' in (root / "project/page.ndjson").read_text()
    assert json.loads((root / "comments.json").read_text())["anchors"]["s:test"][0]["decision"]["text"] == "Note"


@pytest.mark.parametrize("encoding", ["identity", "gzip"])
def test_all_poll_routes_revalidate_and_invalidate_on_change(server, encoding):
    httpd, root, _, _ = server
    for path in ("/comments.json", "/api/read-state", "/api/categories", "/api/session-monitor", "/api/board", "/api/plans/test",
                 "/current.meta.json", "/api/delivery", "/api/history", "/api/project"):
        status, headers, body = request(httpd, path, headers={"Accept-Encoding": encoding})
        assert status == 200 and len(headers["ETag"]) == 66 and not headers["ETag"].startswith("W/")
        assert headers["ETag"] == '"' + hashlib.sha256(body).hexdigest() + '"'
        assert headers["Cache-Control"] == "private, no-cache"
        assert "Cookie" in headers["Vary"] and "Tailscale-User-Login" in headers["Vary"]
        status, cached, body = request(httpd, path, headers={"Accept-Encoding": encoding, "If-None-Match": headers["ETag"]})
        assert status == 304 and body == b""
        assert cached["ETag"] == headers["ETag"]
        assert cached["Cache-Control"] == headers["Cache-Control"]
        assert cached["X-Content-Type-Options"] == "nosniff"
    before = {path: request(httpd, path)[1]["ETag"] for path in ("/comments.json", "/api/categories", "/api/read-state", "/api/plans/test")}
    request(httpd, "/api/comments", "POST", {"anchor_id": "s:test", "text": "New activity"})
    request(httpd, "/api/read-state", "POST", {"items": [{"id": "card", "sig": "new"}]})
    publish_plan_revision(root, "test", "<html><body>Changed plan</body></html>")
    for path, etag in before.items():
        status, headers, _ = request(httpd, path, headers={"If-None-Match": etag})
        assert status == 200 and headers["ETag"] != etag


def test_categories_loads_the_comment_store_once_even_with_many_plans(server, monkeypatch):
    httpd, root, _, _ = server
    for n in range(15):
        publish_plan_revision(root, f"manual-{n}", "<html><body>Plan</body></html>", title="Manual")
    loads = []
    original = sync_server._load_v2_store

    def load(*args, **kwargs):
        loads.append(True)
        return original(*args, **kwargs)
    monkeypatch.setattr(sync_server, "_load_v2_store", load)
    status, _, body = request(httpd, "/api/categories")
    assert status == 200 and len(json.loads(body)["plans"]) == 16
    assert len(loads) == 1


def test_poll_projection_preserves_history_on_disk_and_reuses_encoded_bodies(server, monkeypatch):
    httpd, root, _, _ = server
    path = root / "comments.json"
    store = json.loads(path.read_text())
    store["anchors"]["s:test"][0]["carry_history"] = [{"version": "v0", "text": "History " * 5000}]
    store["anchors"]["s:test"][0]["decision_history"] = [{"verdict": "reject"}]
    path.write_text(json.dumps(store))
    full = json.loads(request(httpd, "/comments.json")[2])
    status, headers, body = request(httpd, "/comments.json?view=poll")
    card = json.loads(body)["anchors"]["s:test"][0]
    assert status == 200 and "carry_history" not in card
    assert card["decision_history"] == [{"verdict": "reject"}]
    assert full["anchors"]["s:test"][0]["carry_history"]
    gzip_headers = {"Accept-Encoding": "gzip"}
    zipped = request(httpd, "/comments.json?view=poll", headers=gzip_headers)[1]
    with monkeypatch.context() as context:
        def unexpected(*args, **kwargs):
            raise AssertionError("unchanged poll must reuse the encoded representation")
        context.setattr(sync_server, "_load_v2_store", unexpected)
        context.setattr(sync_server.gzip, "compress", unexpected)
        assert request(httpd, "/comments.json?view=poll", headers={"If-None-Match": headers["ETag"]})[0] == 304
        assert request(httpd, "/comments.json?view=poll", headers={**gzip_headers, "If-None-Match": zipped["ETag"]})[0] == 304
    assert request(httpd, "/api/comments/card", "PUT", {"text": "Edited"})[0] == 200
    assert json.loads(path.read_text())["anchors"]["s:test"][0]["carry_history"]
    assert request(httpd, "/comments.json?view=poll", headers={"If-None-Match": headers["ETag"]})[0] == 200


def test_failed_write_cannot_poison_cached_snapshot(server, monkeypatch):
    httpd, root, _, _ = server
    path = root / "comments.json"
    before = path.read_bytes()
    status, headers, _ = request(httpd, "/comments.json")
    assert status == 200
    with monkeypatch.context() as context:
        def fail(*args, **kwargs):
            raise OSError("injected durable save failure")
        context.setattr(httpd.RequestHandlerClass, "_v2_save", fail)
        assert request(httpd, "/api/comments", "POST", {"anchor_id": "s:test", "text": "Uncommitted"})[0] == 500
    assert path.read_bytes() == before
    status, _, body = request(httpd, "/comments.json", headers={"If-None-Match": headers["ETag"]})
    assert status == 304 and body == b""
    assert "Uncommitted" not in request(httpd, "/comments.json")[2].decode()


def test_round_recovery_save_cannot_publish_later_uncommitted_mutations(server):
    httpd, root, _, _ = server
    path = root / "comments.json"
    store = json.loads(path.read_text())
    card = store["anchors"]["s:test"][0]
    decision = {"id": "recovered-vote", "verdict": "accept", "by": "reviewer@example.test",
                "ts": "2026-10-22T08:00:00Z", "round_pending": True}
    card["decision"] = decision
    store["anchors"]["s:test"] += [
        {**card, "id": "archived", "status": "archived", "decision": {**decision, "id": "archived-vote"}},
        {**card, "id": "pending", "decision": {**decision, "id": "pending-vote"}},
    ]
    path.write_text(json.dumps(store))
    (root / "rounds.ndjson").write_text(json.dumps({"id": "receipt", "ts": decision["ts"], "answers": [
        {"comment_id": card["id"], "decision_id": decision["id"], "by": decision["by"],
         "ts": decision["ts"], "verdict": decision["verdict"]}]}) + "\n")
    assert request(httpd, "/api/rounds/submit", "POST", {"version": "unknown"})[0] == 400
    saved = json.loads(path.read_text())
    assert not saved["anchors"]["s:test"][0]["decision"].get("round_pending")
    assert saved["anchors"]["s:test"][1]["decision"]["round_pending"] is True
    # Recovery was durable, but the rejected round's later edits were not.
    assert json.loads(request(httpd, "/comments.json")[2]) == saved


@pytest.mark.parametrize("replacement", ["in-place", "atomic", "recreated"])
def test_external_same_size_store_edits_invalidate_all_representations(server, replacement):
    httpd, root, _, _ = server
    path = root / "comments.json"
    variants = [(route, encoding) for route in ("/comments.json", "/comments.json?view=poll")
                for encoding in ("identity", "gzip")]
    before = {(route, encoding): request(httpd, route, headers={"Accept-Encoding": encoding})[1]["ETag"]
              for route, encoding in variants}
    previous = path.stat()
    body = path.read_bytes().replace(b'"Choose"', b'"Newest"')
    assert len(body) == previous.st_size
    if replacement == "atomic":
        temporary = path.with_suffix(".new")
        temporary.write_bytes(body)
        os.utime(temporary, ns=(previous.st_atime_ns, previous.st_mtime_ns))
        temporary.replace(path)
    else:
        if replacement == "recreated":
            path.unlink()
        path.write_bytes(body)
        os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    for route, encoding in variants:
        status, headers, _ = request(httpd, route, headers={"Accept-Encoding": encoding,
                                                         "If-None-Match": before[route, encoding]})
        assert status == 200 and headers["ETag"] != before[route, encoding]
    assert json.loads(request(httpd, "/comments.json")[2])["anchors"]["s:test"][0]["text"] == "Newest"


def test_encoded_store_cache_retains_only_four_current_representations(server):
    httpd, root, _, _ = server
    for index in range(8):
        assert request(httpd, "/api/comments/card", "PUT", {"text": f"Revision {index}"})[0] == 200
        for route in ("/comments.json", "/comments.json?view=poll"):
            for encoding in ("identity", "gzip"):
                assert request(httpd, route, headers={"Accept-Encoding": encoding})[0] == 200
        cache = httpd.RequestHandlerClass._store_responses
        assert set(cache) == {"signature", (False, False, False), (False, True, False), (True, False, False), (True, True, False)}
        assert httpd.RequestHandlerClass._store_snapshot[0] == cache["signature"]


def test_poll_validators_never_bypass_review_key_authentication(server, monkeypatch):
    from agent_annotate import review_access

    httpd, root, _, _ = server
    state = root / "state/project.json"
    registry = json.loads(state.read_text())
    registry["slugs"]["page"].update(transport="funnel", url="https://review.example.ts.net/")
    state.write_text(json.dumps(registry))
    key = review_access.ensure_key(root)
    first = review_access.issue_cookie(root, key, "First reviewer")
    second = review_access.issue_cookie(root, key, "Second reviewer")
    headers = {"Host": "review.example.ts.net", "Cookie": review_access.cookie_name(root) + "=" + first}
    for route in ("/comments.json", "/comments.json?view=poll", "/api/categories", "/api/read-state",
                  "/api/session-monitor", "/api/board", "/api/plans/test", "/current.meta.json",
                  "/api/delivery", "/api/history", "/api/project"):
        status, cached, _ = request(httpd, route, headers=headers)
        assert status == 200
        anonymous = {"Host": headers["Host"], "If-None-Match": cached["ETag"]}
        assert request(httpd, route, headers=anonymous)[0] == 403
        assert request(httpd, route, headers={**headers, "If-None-Match": cached["ETag"]})[0] == 304
    cached = request(httpd, "/api/read-state", headers=headers)[1]
    status, changed, body = request(httpd, "/api/read-state", headers={
        **headers, "Cookie": review_access.cookie_name(root) + "=" + second, "If-None-Match": cached["ETag"]})
    assert status == 200 and changed["ETag"] != cached["ETag"]
    assert json.loads(body)["author"] == review_access.identity(root, review_access.cookie_name(root) + "=" + second)[0]
    monkeypatch.setattr(httpd.RequestHandlerClass, "_project_payload", lambda self: {
        "name": self._identity()["name"], "modules": []})
    cached = request(httpd, "/current.meta.json", headers=headers)[1]
    status, changed, body = request(httpd, "/current.meta.json", headers={
        **headers, "Cookie": review_access.cookie_name(root) + "=" + second, "If-None-Match": cached["ETag"]})
    assert status == 200 and changed["ETag"] != cached["ETag"]
    assert json.loads(body)["project_info"]["name"] == "Second reviewer"
    assert request(httpd, "/current.meta.json", headers={**headers, "If-None-Match": cached["ETag"]})[0] == 304
    review_access._key_path(root).unlink()
    review_access.ensure_key(root)
    assert request(httpd, "/current.meta.json", headers={**headers, "If-None-Match": cached["ETag"]})[0] == 403


@pytest.mark.parametrize("encoding", ["identity", "gzip"])
def test_meta_cache_tracks_file_and_all_injected_inputs(server, monkeypatch, encoding):
    httpd, root, _, _ = server
    handler = httpd.RequestHandlerClass
    # Keep name resolution out of this probe so re-reading/re-encoding the large
    # metadata itself can fail loudly while small live inputs are still read.
    project = {"name": "Page", "modules": []}
    monkeypatch.setattr(handler, "_project_payload", lambda self: dict(project))
    latest = {"latest": None}
    monkeypatch.setattr(delivery, "delivery_status", lambda *args: dict(latest))
    path = root / "current.meta.json"
    meta = json.loads(path.read_text())
    meta["padding"] = "Large history " * 10000
    path.write_text(json.dumps(meta))
    headers = {"Accept-Encoding": encoding}
    status, first, body = request(httpd, "/current.meta.json", headers=headers)
    assert status == 200
    assert first["ETag"] == '"' + hashlib.sha256(body).hexdigest() + '"'
    with monkeypatch.context() as context:
        original_dumps = json.dumps
        original_read = type(path).read_text

        def dumps(value, *args, **kwargs):
            assert not isinstance(value, dict) or "padding" not in value, "must reuse encoded meta body"
            return original_dumps(value, *args, **kwargs)

        def read(self, *args, **kwargs):
            assert self != path, "must reuse parsed meta"
            return original_read(self, *args, **kwargs)

        context.setattr(sync_server.json, "dumps", dumps)
        context.setattr(type(path), "read_text", read)
        context.setattr(sync_server.gzip, "compress", lambda *args, **kwargs: pytest.fail("must reuse compressed meta"))
        assert request(httpd, "/current.meta.json", headers={**headers, "If-None-Match": first["ETag"]})[::2] == (304, b"")
    etag = first["ETag"]

    def changed():
        nonlocal etag
        status, response, body = request(httpd, "/current.meta.json", headers={**headers, "If-None-Match": etag})
        assert status == 200 and response["ETag"] != etag
        assert response["ETag"] == '"' + hashlib.sha256(body).hexdigest() + '"'
        etag = response["ETag"]
        return json.loads(gzip.decompress(body) if response.get("Content-Encoding") == "gzip" else body)

    latest["latest"] = {"id": "round", "state": "acknowledged"}
    assert changed()["delivery_status"] == latest
    project["modules"] = ["library"]
    assert changed()["project_info"] == project
    state_path = root / "state/project.json"
    registry = json.loads(state_path.read_text())
    registry["slugs"]["page"]["owner_target"]["terminal_name"] = "Renamed terminal"
    state_path.write_text(json.dumps(registry))
    owner = changed()["owner"]
    assert owner["terminal_name"] == "Renamed terminal" and "target" not in owner
    # An atomic replacement, even preserving mtime and size, invalidates by inode/ctime.
    original_stat = path.stat()
    replacement = path.with_suffix(".replacement")
    replacement.write_text(path.read_text().replace('"v1"', '"v2"'))
    os.utime(replacement, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    replacement.replace(path)
    assert changed()["current"] == "v2"
    for i in range(10):
        latest["latest"]["id"] = str(i)
        changed()
        assert len(handler._meta_responses) <= 4
    assert "target" not in request(httpd, "/current.meta.json")[2].decode().split('"owner":', 1)[1]
    path.write_text("{broken json")
    fallback = changed()
    assert fallback["project_info"] == project and fallback["delivery_status"] == latest
    path.unlink()
    assert changed()["current"] == "v1"


@pytest.mark.parametrize("encoding", ["identity", "gzip"])
def test_meta_cache_detects_mapped_edits_without_stat_changes(server, encoding):
    httpd, root, _, _ = server
    path = root / "current.meta.json"
    path.write_text(json.dumps({"current": "v1", "history": [], "padding": "metadata " * 1000}))
    headers = {"Accept-Encoding": encoding}
    with path.open("r+b") as source, mmap.mmap(source.fileno(), 0) as mapped:
        offset = mapped.find(b"v1")
        mapped[offset:offset + 2] = b"v2"
        first = request(httpd, "/current.meta.json", headers=headers)[1]
        before = path.stat()
        mapped[offset:offset + 2] = b"v3"
        after = path.stat()
        assert (before.st_mtime_ns, before.st_ctime_ns) == (after.st_mtime_ns, after.st_ctime_ns)
        status, response, body = request(httpd, "/current.meta.json", headers={**headers, "If-None-Match": first["ETag"]})
        assert status == 200 and response["ETag"] != first["ETag"]
        assert json.loads(gzip.decompress(body) if response.get("Content-Encoding") == "gzip" else body)["current"] == "v3"


@pytest.mark.parametrize("raw", ["[]", "null", '"metadata"', "42"])
def test_non_object_meta_keeps_live_summaries(server, raw):
    httpd, root, _, _ = server
    (root / "current.meta.json").write_text(raw)
    status, headers, body = request(httpd, "/current.meta.json")
    meta = json.loads(body)
    assert status == 200 and meta["project_info"]["name"] == meta["name"]
    assert meta["delivery_status"] == {"latest": None}
    assert meta["owner"]["owner_session"] == "test-owner"
    assert request(httpd, "/current.meta.json", headers={"If-None-Match": headers["ETag"]})[0] == 304


@pytest.mark.parametrize("raw", [{"s:test": [{"text": "Old map"}]}, [{"sectionId": "s:test", "text": "Old list"}]])
def test_removed_store_formats_are_refused_without_changing_the_file(tmp_path, raw):
    path = tmp_path / "comments.json"
    path.write_text(json.dumps(raw))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="schema_version 2"):
        sync_server._load_v2_store(path)
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]
