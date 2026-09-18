import http.client
import http.server
import json
import threading
from pathlib import Path

import pytest

from agent_annotate.sync_server import make_handler


@pytest.fixture
def identity_server(tmp_path):
    slug_dir = tmp_path / "review"
    slug_dir.mkdir()
    (slug_dir / "comments.json").write_text(
        json.dumps({"schema_version": 2, "anchors": {}, "archived": {}}), encoding="utf-8"
    )
    (slug_dir / "current.meta.json").write_text(
        json.dumps({"current": "v2", "history": [{"version": "v2", "label": "current"}]}),
        encoding="utf-8",
    )
    handler = make_handler(
        artifact_dir=slug_dir,
        public_base_path="/review",
        slug="review",
        bus_dir=tmp_path / "bus",
        v2_mode=True,
        local_author="chang@leadory.com",
        local_author_name="Chang Lee",
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, slug_dir
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _request(server, method, path, host, *, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    connection.putrequest(method, path, skip_host=True)
    connection.putheader("Host", host)
    if payload is not None:
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", str(len(payload)))
    for name, value in (headers or {}).items():
        connection.putheader(name, value)
    connection.endheaders(payload)
    response = connection.getresponse()
    data = json.loads(response.read())
    connection.close()
    return response.status, data


def test_local_identity_requires_loopback_peer_and_local_host(identity_server):
    server, _ = identity_server
    port = server.server_address[1]

    status, local = _request(server, "GET", "/review/api/identity", f"localhost:{port}")
    assert status == 200
    assert local == {"email": "chang@leadory.com", "name": "Chang Lee", "authenticated": True}

    status, numeric = _request(server, "GET", "/review/api/identity", f"127.0.0.1:{port}")
    assert status == 200
    assert numeric["email"] == "chang@leadory.com"

    status, public = _request(server, "GET", "/review/api/identity", "connelly.leadory.net")
    assert status == 200
    assert public == {"email": None, "name": None, "authenticated": False}

    status, tailscale = _request(
        server, "GET", "/review/api/identity", "macbook-pro.tail2b8ab9.ts.net:8451"
    )
    assert status == 200
    assert tailscale["authenticated"] is False

    status, deceptive = _request(server, "GET", "/review/api/identity", "localhost.example.com")
    assert status == 200
    assert deceptive["authenticated"] is False


def test_oauth_identity_wins_and_local_comment_uses_fallback(identity_server):
    server, slug_dir = identity_server
    port = server.server_address[1]

    status, oauth = _request(
        server,
        "GET",
        "/review/api/identity",
        "connelly.leadory.net",
        headers={
            "Cf-Access-Authenticated-User-Email": "oauth@example.com",
            "Cf-Access-Authenticated-User-Name": "OAuth User",
        },
    )
    assert status == 200
    assert oauth == {"email": "oauth@example.com", "name": "OAuth User", "authenticated": True}

    status, comment = _request(
        server,
        "POST",
        "/review/api/comments",
        f"localhost:{port}",
        body={"anchor_id": "s:test", "text": "loopback comment", "version": "v2"},
    )
    assert status == 201
    assert comment["author"] == "chang@leadory.com"
    assert comment["author_name"] == "Chang Lee"

    store = json.loads((Path(slug_dir) / "comments.json").read_text(encoding="utf-8"))
    assert store["anchors"]["s:test"][0]["author"] == "chang@leadory.com"
