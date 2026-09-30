import http.server
import json
import os
import stat
import threading
from contextlib import contextmanager
from datetime import datetime

import pytest

from agent_annotate.transports import cloudflare
from agent_annotate.transports.cloudflare import _api_request, _auth


def test_cloudflare_auth_uses_portable_environment(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account")
    monkeypatch.setenv("ANNOTATE_CLOUDFLARE_TUNNEL_ID", "tunnel")
    monkeypatch.setenv("ANNOTATE_CLOUDFLARE_HOSTNAME", "reviews.example.com")

    assert _auth({}) == ("account", "tunnel", "reviews.example.com", "token")


def test_cloudflare_auth_has_no_embedded_project_defaults(monkeypatch):
    for name in (
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "ANNOTATE_CLOUDFLARE_TUNNEL_ID",
        "ANNOTATE_CLOUDFLARE_HOSTNAME",
        "ANNOTATE_CLOUDFLARE_ENV_FILE",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="CLOUDFLARE_API_TOKEN"):
        _auth({})


@contextmanager
def _server(handler):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_api_redirect_never_forwards_bearer_to_another_origin(status):
    received = []

    class Foreign(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            received.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"success":true}')

        def log_message(self, *args):
            pass

    with _server(Foreign) as destination:
        class Redirect(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                assert self.headers.get("Authorization") == "Bearer synthetic-fixture"
                self.send_response(status)
                self.send_header("Location", destination)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        with _server(Redirect) as origin:
            with pytest.raises(RuntimeError, match="redirect refused"):
                _api_request("GET", origin, "synthetic-fixture")
        assert received == []


def test_authenticated_nonredirect_api_response_still_works():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.headers.get("Authorization") == "Bearer synthetic-fixture"
            body = json.dumps({"success": True, "result": {"ok": True}}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    with _server(Handler) as origin:
        assert _api_request("GET", origin, "synthetic-fixture") == {"success": True, "result": {"ok": True}}


def test_backup_is_private_before_any_bytes_are_written(tmp_path, monkeypatch):
    monkeypatch.setattr(cloudflare, "STATE_DIR", tmp_path)
    original_dump = cloudflare.json.dump
    observed = []

    def inspect_before_write(data, stream, **kwargs):
        metadata = os.fstat(stream.fileno())
        observed.append((stat.S_IMODE(metadata.st_mode), metadata.st_size))
        return original_dump(data, stream, **kwargs)

    monkeypatch.setattr(cloudflare.json, "dump", inspect_before_write)
    old_mask = os.umask(0)
    try:
        path = cloudflare._backup({"result": "private configuration"})
    finally:
        os.umask(old_mask)
    assert observed == [(0o600, 0)]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text()) == {"result": "private configuration"}
    assert path.parent == tmp_path / "backups"


def test_same_second_backups_have_unique_paths_and_preserve_both_snapshots(tmp_path, monkeypatch):
    class FrozenClock:
        @staticmethod
        def now(tz):
            return datetime(2026, 9, 30, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr(cloudflare, "STATE_DIR", tmp_path)
    monkeypatch.setattr(cloudflare, "datetime", FrozenClock)
    first = cloudflare._backup({"snapshot": 1})
    second = cloudflare._backup({"snapshot": 2})
    assert first != second
    assert json.loads(first.read_text()) == {"snapshot": 1}
    assert json.loads(second.read_text()) == {"snapshot": 2}


def test_failed_backup_write_removes_partial_private_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cloudflare, "STATE_DIR", tmp_path)

    def fail(data, output, **kwargs):
        output.write("partial")
        raise OSError("synthetic write failure")

    monkeypatch.setattr(cloudflare.json, "dump", fail)
    with pytest.raises(OSError, match="synthetic write failure"):
        cloudflare._backup({"snapshot": 1})
    assert list((tmp_path / "backups").iterdir()) == []
