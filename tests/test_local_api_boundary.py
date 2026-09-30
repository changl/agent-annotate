"""CLI and MCP share direct-loopback, no-redirect, bounded-response semantics."""

import http.server
import json
import threading
from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from agent_annotate import cli, mcp_server


@contextmanager
def _server(status=200, body=b'{"ok":true}', location=None):
    received = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            received.append({"path": self.path, "agent": self.headers.get("X-Annotate-Agent"),
                             "legacy_agent": self.headers.get("Cf-Access-Authenticated-User-Email"),
                             "session": self.headers.get("X-Annotate-Session"),
                             "body": self.rfile.read(int(self.headers.get("Content-Length") or 0))})
            self.send_response(status)
            if location:
                self.send_header("Location", location)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_POST = do_GET

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {"local_url": f"http://127.0.0.1:{server.server_port}/", "port": server.server_port}, received
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_real_cli_and_mcp_requests_keep_mounted_route_body_and_agent_attribution(monkeypatch, host):
    monkeypatch.setattr(cli, "_session_id", lambda: "synthetic-session")
    with _server() as (record, received):
        record["local_url"] = f'http://{host}:{record["port"]}/'
        record["public_base_path"] = "/mounted"
        assert cli._api(record, "POST", "/api/comments", {"text": "Review"}, "cli") == (200, {"ok": True})
        monkeypatch.setattr(mcp_server, "_record", lambda slug: record)
        assert mcp_server._api_request("demo", "POST", "/api/comments", {"text": "Review"}, "mcp") == {"ok": True}
        assert [item["path"] for item in received] == ["/mounted/api/comments"] * 2
        assert [item["agent"] for item in received] == ["agent:cli", "agent:mcp"]
        assert [item["legacy_agent"] for item in received] == ["agent:cli", "agent:mcp"]
        assert [item["session"] for item in received] == ["synthetic-session"] * 2
        assert all(json.loads(item["body"]) == {"text": "Review"} for item in received)


@pytest.mark.parametrize("url", [
    "https://127.0.0.1:8802/", "http://example.com:8802/", "http://10.0.0.1:8802/",
    "http://0.0.0.0:8802/", "http://2130706433:8802/", "http://localhost.example.com:8802/",
    "file:///etc/passwd", "ftp://127.0.0.1/file", "http://user:secret@127.0.0.1:8802/",
    "http://127.0.0.1:8802/?secret=1", "http://127.0.0.1:8802/#secret", "http://127.0.0.1:8802/prefix",
    "http://127.0.0.1:8802/\n", "http://127.0.0.1\\@evil.example:8802/", "http://[::1%25lo0]:8802/",
    "http://[::1]other.example:8802/",
])
def test_invalid_recorded_origin_is_rejected_before_building_a_client(monkeypatch, url):
    monkeypatch.setattr(cli.urllib.request, "build_opener", lambda *args: pytest.fail("invalid origin requested"))
    record = {"local_url": url, "port": 8802}
    code, error = cli._api(record, "POST", "/api/comments", {}, "test")
    assert code == 0 and "loopback HTTP" in error
    assert "secret" not in error
    monkeypatch.setattr(mcp_server, "_record", lambda slug: record)
    with pytest.raises(RuntimeError, match="loopback HTTP"):
        mcp_server._api_request("demo", "POST", "/api/comments", {}, "test")


@pytest.mark.parametrize("port", [None, True, "8802", 8803, 0, 65536])
def test_recorded_port_must_match_origin(monkeypatch, port):
    monkeypatch.setattr(cli.urllib.request, "build_opener", lambda *args: pytest.fail("mismatched port requested"))
    code, error = cli._api({"local_url": "http://localhost:8802/", "port": port}, "GET", "/api/comments", None, "test")
    assert code == 0 and "recorded port" in error


@pytest.mark.parametrize("field, value", [
    ("prefix", "//other.example"), ("prefix", "/mounted?secret=1"), ("prefix", "/mounted#secret"),
    ("prefix", "../mounted"), ("prefix", "/%2e%2e/mounted"), ("prefix", []),
    ("route", "http://other.example/api"), ("route", "//other.example/api"),
    ("route", "/api/comments?secret=1"), ("route", "/api/comments#secret"),
    ("route", "/api/%2e%2e/private"), ("route", "/api/%0a/comments"), ("route", "/api/%5c/comments"),
])
def test_prefix_and_route_cannot_change_authority_or_request_target(monkeypatch, field, value):
    monkeypatch.setattr(cli.urllib.request, "build_opener", lambda *args: pytest.fail("unsafe path requested"))
    record = {"local_url": "http://localhost:8802/", "port": 8802, "public_base_path": value if field == "prefix" else ""}
    path = value if field == "route" else "/api/comments"
    code, error = cli._api(record, "GET", path, None, "test")
    assert code == 0 and "root-relative paths" in error
    assert "secret" not in error


def test_ipv6_loopback_is_validated_without_dns_lookup():
    assert cli._local_api_url({"local_url": "http://[::1]:8802/", "port": 8802}, "/api/comments") == "http://[::1]:8802/api/comments"


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_redirects_do_not_forward_agent_session_or_body_to_another_origin(monkeypatch, status):
    monkeypatch.setattr(cli, "_session_id", lambda: "synthetic-session")
    with _server() as (foreign, leaked):
        with _server(status=status, body=b"untrusted redirect body", location=foreign["local_url"]) as (record, source):
            code, payload = cli._api(record, "POST", "/api/comments", {"text": "private fixture"}, "test")
            assert code == status and "redirect refused" in payload["error"]
            monkeypatch.setattr(mcp_server, "_record", lambda slug: record)
            with pytest.raises(RuntimeError, match="redirect refused"):
                mcp_server._api_request("demo", "POST", "/api/comments", {"text": "private fixture"}, "test")
            assert len(source) == 2
            assert "untrusted redirect body" not in str(payload)
        assert leaked == []


def test_environment_proxy_cannot_receive_local_request_or_headers(monkeypatch):
    with _server() as (proxy, intercepted), _server() as (record, received):
        for key in ("http_proxy", "HTTP_PROXY", "all_proxy", "ALL_PROXY"):
            monkeypatch.setenv(key, proxy["local_url"])
        for key in ("no_proxy", "NO_PROXY"):
            monkeypatch.delenv(key, raising=False)
        assert cli._api(record, "POST", "/api/comments", {}, "test") == (200, {"ok": True})
        monkeypatch.setattr(mcp_server, "_record", lambda slug: record)
        assert mcp_server._api_request("demo", "POST", "/api/comments", {}, "test") == {"ok": True}
        assert len(received) == 2 and intercepted == []


@pytest.mark.parametrize("status", [200, 400, 500])
def test_success_and_http_error_responses_are_byte_bounded_with_actionable_errors(monkeypatch, status):
    monkeypatch.setattr(cli, "_LOCAL_API_MAX_RESPONSE_BYTES", 16)
    with _server(status=status, body=b"private response content beyond bound") as (record, _received):
        code, error = cli._api(record, "POST", "/api/comments", {}, "test")
        message = error["error"] if isinstance(error, dict) else error
        assert code == (status if status >= 400 else 0)
        assert "exceeds 16 bytes" in message and "before retrying a write" in message
        assert "private response" not in message
        monkeypatch.setattr(mcp_server, "_record", lambda slug: record)
        with pytest.raises(RuntimeError, match="exceeds 16 bytes"):
            mcp_server._api_request("demo", "POST", "/api/comments", {}, "test")


@pytest.mark.parametrize("error_response", [False, True])
def test_bounded_read_failure_closes_normal_or_http_error_response(monkeypatch, error_response):
    class BrokenBody(BytesIO):
        def read(self, maximum):
            assert maximum == cli._LOCAL_API_MAX_RESPONSE_BYTES + 1
            raise OSError("private transport detail")

    body = BrokenBody()
    response = HTTPError("http://localhost:8802/api", 400, "private error", {}, body) if error_response else body
    if not error_response:
        response.status = 200

    class Opener:
        def open(self, request, timeout):
            if error_response:
                raise response
            return response

    monkeypatch.setattr(cli.urllib.request, "build_opener", lambda *args: Opener())
    code, error = cli._api({"local_url": "http://localhost:8802/", "port": 8802}, "POST", "/api/comments", {}, "test")
    assert code == 0 and "check the recorded server" in error
    assert "private" not in error and body.closed


def test_mcp_retains_five_second_socket_timeout_and_validated_cli_attribution(monkeypatch):
    calls = []
    record = {"local_url": "http://localhost:8802/", "port": 8802}
    monkeypatch.setattr(mcp_server, "_record", lambda slug: record)

    def api(*args, **kwargs):
        calls.append((args, kwargs))
        return 200, {"ok": True}

    monkeypatch.setattr(cli, "_api", api)
    assert mcp_server._api_request("demo", "POST", "/api/comments", {}, "default") == {"ok": True}
    assert calls == [((record, "POST", "/api/comments", {}, "default"), {"timeout": 5})]


@pytest.mark.parametrize("status", [404, 405, 501])
@pytest.mark.parametrize("oversized", [False, True])
def test_plain_or_oversized_legacy_error_keeps_status_and_real_cmd_ask_fallback(tmp_path, monkeypatch, capsys, status, oversized):
    monkeypatch.setattr(cli, "_LOCAL_API_MAX_RESPONSE_BYTES", 32)
    body = b"<html>legacy route absent</html>" if not oversized else b"x" * 33
    cards = tmp_path / "cards.json"
    cards.write_text(json.dumps([{"anchor_id": "s:coverage", "text": "Review coverage"}]))
    fallback_calls = []
    with _server(status=status, body=body) as (record, _received):
        monkeypatch.setattr(cli, "_resolve_scoped_slug", lambda *args: ("proj", "demo", record))

        def fallback(*args):
            fallback_calls.append(args)
            return ["fallback-id"], 1, 0

        monkeypatch.setattr(cli, "_ask_fallback", fallback)
        args = SimpleNamespace(slug="demo", project="proj", from_file=str(cards), version="v1", author="agent:test", json=True)
        assert cli.cmd_ask(args) == 0
        assert len(fallback_calls) == 1
        output = capsys.readouterr().out
        assert f"batch route absent (HTTP {status})" in output
        assert '"route": "fallback"' in output


def test_cmd_ask_unusable_success_does_not_claim_server_is_dead_or_retry_write(tmp_path, monkeypatch, capsys):
    cards = tmp_path / "cards.json"
    cards.write_text(json.dumps([{"anchor_id": "s:coverage", "text": "Review coverage"}]))
    with _server(body=b"not JSON") as (record, received):
        monkeypatch.setattr(cli, "_resolve_scoped_slug", lambda *args: ("proj", "demo", record))
        monkeypatch.setattr(cli, "_ask_fallback", lambda *args: pytest.fail("unproven write retried"))
        args = SimpleNamespace(slug="demo", project="proj", from_file=str(cards), version="v1", author="agent:test", json=True)
        assert cli.cmd_ask(args) == 2
        error = capsys.readouterr().err
        assert "response unavailable or unusable" in error and "write may already have completed" in error
        assert "no server answering" not in error and "Start it" not in error
        assert len(received) == 1


def test_cmd_ask_refused_redirect_cannot_report_batch_success(tmp_path, monkeypatch, capsys):
    cards = tmp_path / "cards.json"
    cards.write_text(json.dumps([{"anchor_id": "s:coverage", "text": "Review coverage"}]))
    with _server(status=302, location="http://127.0.0.1:9/") as (record, received):
        monkeypatch.setattr(cli, "_resolve_scoped_slug", lambda *args: ("proj", "demo", record))
        args = SimpleNamespace(slug="demo", project="proj", from_file=str(cards), version="v1", author="agent:test", json=True)
        assert cli.cmd_ask(args) == 2
        assert "redirect refused" in capsys.readouterr().err
        assert len(received) == 1


@contextmanager
def _legacy_server(oversized_history=False):
    # Match the previous package's CF-header-only identity contract. This
    # stand-in has no batch route and ignores decision_request on POST, as
    # the supported older fallback protocol did.
    rows = [{"id": "prior", "anchor_id": "s:coverage", "author": "agent:test", "status": "open",
             "decision_request": {"prompt": "Prior question?"}}] if oversized_history else []
    counts = {"created": 0, "updated": 0}

    class Handler(http.server.BaseHTTPRequestHandler):
        def response(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.response(200, rows)

        def do_POST(self):
            item = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            if self.path == "/api/comments/batch":
                self.send_error(404, "Batch route absent")
                return
            assert self.path == "/api/comments"
            row = {key: value for key, value in item.items() if key != "decision_request"}
            row.update(id=f"legacy-{len(rows)}", author=self.headers.get("Cf-Access-Authenticated-User-Email") or "anonymous")
            rows.append(row)
            counts["created"] += 1
            self.response(201, row)

        def do_PUT(self):
            item = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            row = next(row for row in rows if self.path == "/api/comments/" + row["id"])
            row.update(item)
            counts["updated"] += 1
            self.response(200, row)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield {"local_url": f"http://127.0.0.1:{server.server_port}/", "port": server.server_port}, rows, counts
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("author", ["agent:test", "test"])
def test_real_legacy_fallback_preserves_agent_attribution_and_same_card_on_second_round(tmp_path, monkeypatch, capsys, author):
    cards = tmp_path / "cards.json"
    cards.write_text(json.dumps([{"anchor_id": "s:coverage", "text": "Review coverage", "decision_request": {"prompt": "Continue?"}}]))
    with _legacy_server() as (record, rows, counts):
        monkeypatch.setattr(cli, "_resolve_scoped_slug", lambda *args: ("proj", "demo", record))
        args = SimpleNamespace(slug="demo", project="proj", from_file=str(cards), version="v1", author=author, json=True)
        assert cli.cmd_ask(args) == 0
        capsys.readouterr()
        original_id = rows[0]["id"]
        assert cli.cmd_ask(args) == 0
        assert len(rows) == 1 and rows[0]["id"] == original_id
        assert rows[0]["author"] == "agent:test" and rows[0]["decision_request"]["prompt"] == "Continue?"
        assert counts == {"created": 1, "updated": 2}


def test_legacy_fallback_unusable_history_stops_before_any_card_write(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_LOCAL_API_MAX_RESPONSE_BYTES", 32)
    cards = tmp_path / "cards.json"
    cards.write_text(json.dumps([{"anchor_id": "s:coverage", "text": "Review coverage", "decision_request": {"prompt": "Continue?"}}]))
    with _legacy_server(oversized_history=True) as (record, rows, counts):
        before = json.dumps(rows)
        monkeypatch.setattr(cli, "_resolve_scoped_slug", lambda *args: ("proj", "demo", record))
        args = SimpleNamespace(slug="demo", project="proj", from_file=str(cards), version="v1", author="agent:test", json=True)
        assert cli.cmd_ask(args) == 2
        assert "cannot read existing cards before legacy fallback" in capsys.readouterr().err
        assert json.dumps(rows) == before and counts == {"created": 0, "updated": 0}


def test_legacy_fallback_wrong_history_shape_never_dumps_payload_or_writes(monkeypatch):
    calls = []

    def api(*args, **kwargs):
        calls.append(args)
        return 200, {"private unexpected content": "x" * 100000}

    monkeypatch.setattr(cli, "_api", api)
    with pytest.raises(RuntimeError, match="stopped before any per-card write") as caught:
        cli._ask_fallback({}, "demo", [{"anchor_id": "s:coverage"}], "agent:test")
    assert "private unexpected content" not in str(caught.value) and len(str(caught.value)) < 250
    assert len(calls) == 1 and calls[0][1] == "GET"
