import http.client
import http.server
import json
import threading
from pathlib import Path

import pytest

from agent_annotate import cli, mcp_server, sync_server
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
        proxy_urls=("https://connelly.leadory.net/review/", "https://macbook-pro.tail2b8ab9.ts.net:8454/review/",
                    "https://macbook-pro.tail2b8ab9.ts.net:8451/review/"),
        trusted_access_origins=("https://connelly.leadory.net",),
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
    assert local == {"email": "chang@leadory.com", "name": "Chang Lee", "authenticated": True, "reviewer_authors": ["chang@leadory.com"]}

    status, numeric = _request(server, "GET", "/review/api/identity", f"127.0.0.1:{port}")
    assert status == 200
    assert numeric["email"] == "chang@leadory.com"

    status, public = _request(server, "GET", "/review/api/identity", "connelly.leadory.net")
    assert status == 403

    status, tailscale = _request(
        server, "GET", "/review/api/identity", "macbook-pro.tail2b8ab9.ts.net:8451"
    )
    assert status == 403

    status, deceptive = _request(server, "GET", "/review/api/identity", "localhost.example.com")
    assert status == 403


TAILNET_HOST = "macbook-pro.tail2b8ab9.ts.net:8454"
TAILNET_LOGIN = {"Tailscale-User-Login": "changl@gmail.com", "Tailscale-User-Name": "Chang Lee"}


def test_tailnet_login_identifies_the_reviewer_and_section_comments_work(identity_server):
    server, slug_dir = identity_server

    status, ident = _request(server, "GET", "/review/api/identity", TAILNET_HOST,
                             headers=TAILNET_LOGIN)
    assert status == 200
    assert ident == {"email": "changl@gmail.com", "name": "Chang Lee", "authenticated": True, "reviewer_authors": ["changl@gmail.com"]}

    status, comment = _request(
        server, "POST", "/review/api/comments", TAILNET_HOST, headers=TAILNET_LOGIN,
        body={"anchor_id": "s:plan", "text": "section comment over the tailnet", "version": "v2"},
    )
    assert status == 201
    assert comment["author"] == "changl@gmail.com"


def test_tailnet_login_is_ignored_on_cloudflare_forwarded_requests(identity_server):
    server, _ = identity_server
    status, ident = _request(server, "GET", "/review/api/identity", TAILNET_HOST,
                             headers={**TAILNET_LOGIN, "Cf-Ray": "8c1f0e2d3a4b5c6d-SJC"})
    assert status == 403


def test_tailnet_login_is_ignored_off_a_tailnet_host(identity_server):
    server, _ = identity_server
    status, ident = _request(server, "GET", "/review/api/identity", "connelly.leadory.net",
                             headers=TAILNET_LOGIN)
    assert status == 403


def test_forged_access_email_never_overrides_tailnet_login(identity_server):
    server, _ = identity_server
    status, ident = _request(
        server, "GET", "/review/api/identity", TAILNET_HOST,
        headers={**TAILNET_LOGIN, "Cf-Access-Authenticated-User-Email": "chang@leadory.com"},
    )
    assert status == 200
    assert ident["email"] == "changl@gmail.com"


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
            "Cf-Access-Jwt-Assertion": "inert-proxy-validated-assertion",
        },
    )
    assert status == 200
    assert oauth == {"email": "oauth@example.com", "name": "OAuth User", "authenticated": True, "reviewer_authors": ["oauth@example.com"]}

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


def test_loopback_human_proxy_claim_and_unknown_proxy_host_fail_closed(identity_server):
    server, _ = identity_server
    for host in (f"localhost:{server.server_address[1]}", "unregistered.example.com"):
        status, _ = _request(server, "GET", "/review/api/identity", host,
                             headers={"Cf-Access-Authenticated-User-Email": "forged@example.com"})
        assert status == 403


def test_local_agent_and_same_origin_browser_keep_distinct_identity(identity_server):
    server, _ = identity_server
    host = f"localhost:{server.server_address[1]}"
    for agent_header in ("X-Annotate-Agent", "Cf-Access-Authenticated-User-Email"):
        status, identity = _request(server, "GET", "/review/api/identity", host,
                                    headers={agent_header: "agent:codex"})
        assert status == 200 and identity["email"] == "agent:codex" and identity["authenticated"] is False
        status, data = _request(server, "POST", "/review/api/comments", host,
                               headers={agent_header: "agent:codex"}, body={"anchor_id": "s:agent", "text": "inert agent reply"})
        assert status == 201 and data["author"] == "agent:codex"
    status, data = _request(server, "POST", "/review/api/comments", host,
                           headers={"Origin": "http://" + host, "Sec-Fetch-Site": "same-origin"},
                           body={"anchor_id": "s:human", "text": "inert browser reply"})
    assert status == 201 and data["author"] == "chang@leadory.com"


@pytest.mark.parametrize("marker", ["Cf-Ray", "Cf-Connecting-Ip", "Cf-Access-Jwt-Assertion", "Forwarded",
    "X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto", "Tailscale-User-Login", "oai-authenticated-user-email"])
def test_spoofed_local_host_cannot_turn_forwarded_request_into_local_agent(identity_server, marker):
    server, _ = identity_server
    status, _ = _request(server, "GET", "/review/api/identity", f"localhost:{server.server_address[1]}",
                         headers={"X-Annotate-Agent": "agent:codex", marker: "inert-proxy-marker"})
    assert status == 403


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "OPTIONS"])
def test_cross_origin_read_write_and_preflight_are_denied_without_cors(identity_server, method):
    server, directory = identity_server
    before = (directory / "comments.json").read_bytes()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=2)
    connection.request(method, "/review/api/comments", body="{}" if method in ("POST", "PUT") else None,
                       headers={"Origin": "https://untrusted.example", "Content-Type": "application/json"})
    response = connection.getresponse()
    assert response.status == 403
    assert response.getheader("Access-Control-Allow-Origin") is None
    response.read()
    connection.close()
    assert (directory / "comments.json").read_bytes() == before


def test_public_access_host_is_rejected_without_explicit_edge_trust(identity_server):
    server, _ = identity_server
    server.RequestHandlerClass.trusted_access_origins = ()
    status, _ = _request(server, "GET", "/review/api/identity", "connelly.leadory.net",
                         headers={"Cf-Access-Authenticated-User-Email": "reviewer@example.com",
                                  "Cf-Access-Jwt-Assertion": "inert-proxy-validated-assertion"})
    assert status == 403


def test_published_registry_proxy_binding_requires_matching_directory_and_port(identity_server, tmp_path, monkeypatch):
    server, directory = identity_server
    server.RequestHandlerClass.proxy_urls = ()
    monkeypatch.setattr(sync_server, "STATE_DIR", tmp_path)
    record = {"slug_dir": str(directory), "port": server.server_address[1], "transport": "tailscale",
              "url": "https://" + TAILNET_HOST + "/review/"}
    (tmp_path / "bus.json").write_text(json.dumps({"slugs": {"review": record}}))
    status, identity = _request(server, "GET", "/review/api/identity", TAILNET_HOST, headers=TAILNET_LOGIN)
    assert status == 200 and identity["email"] == "changl@gmail.com"
    record["slug_dir"] = str(tmp_path / "another-project")
    (tmp_path / "bus.json").write_text(json.dumps({"slugs": {"review": record}}))
    assert _request(server, "GET", "/review/api/identity", TAILNET_HOST, headers=TAILNET_LOGIN)[0] == 403


def test_access_trust_comes_only_from_explicit_project_origin_list(identity_server, tmp_path, monkeypatch):
    server, _ = identity_server
    server.RequestHandlerClass.trusted_access_origins = ()
    config = tmp_path / "projects.toml"
    monkeypatch.setattr(sync_server, "PROJECTS_TOML", config)
    headers = {"Cf-Access-Authenticated-User-Email": "reviewer@example.com",
               "Cf-Access-Jwt-Assertion": "inert-proxy-validated-assertion"}
    config.write_text('[bus]\ntrusted_access_origins = ["https://connelly.leadory.net"]\n')
    assert _request(server, "GET", "/review/api/identity", "connelly.leadory.net", headers=headers)[0] == 200
    config.write_text('[bus]\ntrusted_access_origins = "https://connelly.leadory.net"\n')
    assert _request(server, "GET", "/review/api/identity", "connelly.leadory.net", headers=headers)[0] == 403


def test_cli_and_mcp_local_calls_are_agent_attribution_not_human_proxy_claims(identity_server, monkeypatch):
    server, _ = identity_server
    record = {"local_url": f"http://127.0.0.1:{server.server_address[1]}", "port": server.server_address[1], "public_base_path": "/review"}
    status, result = cli._api(record, "POST", "/api/comments", {"anchor_id": "s:cli", "text": "inert CLI reply"}, "reviewer alias")
    assert status == 201 and result["author"] == "agent:reviewer alias"
    monkeypatch.setattr(mcp_server, "_record", lambda slug: record)
    result = mcp_server._api_request("review", "POST", "/api/comments", {"anchor_id": "s:mcp", "text": "inert MCP reply"}, "reviewer@example.com")
    assert result["author"] == "agent:reviewer@example.com"


@pytest.mark.parametrize("headers", [
    {"X-Annotate-Agent": "reviewer@example.com"},
    {"X-Annotate-Agent": "agent:"},
    {"X-Annotate-Agent": "agent:codex", "Sec-Fetch-Site": "same-origin"},
])
def test_invalid_or_browser_agent_claims_never_fall_back_to_human_identity(identity_server, headers):
    server, _ = identity_server
    assert _request(server, "GET", "/review/api/identity", f"localhost:{server.server_address[1]}", headers=headers)[0] == 403


def test_proxy_identity_cannot_bypass_its_published_mount(identity_server):
    server, _ = identity_server
    status, _ = _request(server, "GET", "/api/identity", TAILNET_HOST, headers=TAILNET_LOGIN)
    assert status == 404
