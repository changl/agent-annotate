"""Writes commit before slow delivery; poll validators preserve auth and state."""
import http.client
import json
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
    handler = sync_server.make_handler(root, v2_mode=True, slug="page", bus_dir=root / "project", local_author="reviewer@example.test")
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
def test_six_poll_routes_revalidate_and_invalidate_on_change(server, encoding):
    httpd, root, _, _ = server
    for path in ("/comments.json", "/api/read-state", "/api/categories", "/api/session-monitor", "/api/board", "/api/plans/test"):
        status, headers, _ = request(httpd, path, headers={"Accept-Encoding": encoding})
        assert status == 200 and len(headers["ETag"]) == 66 and not headers["ETag"].startswith("W/")
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
