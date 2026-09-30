"""Stored and displayed page links reach the mount used by the publisher."""

import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from agent_annotate import cli, fleet, mcp_server, transports
from agent_annotate.urls import mounted_url, page_url


@pytest.mark.parametrize("url,base,expected", [
    ("https://page.example:8447/", "/canary", "https://page.example:8447/canary/"),
    ("https://page.example:8447/", "", "https://page.example:8447/"),
    ("https://page.example:8447/", "/", "https://page.example:8447/"),
    ("https://public.example/canary/", "/canary", "https://public.example/canary/"),
    ("https://public.example/prefix/canary/", "/canary", "https://public.example/prefix/canary/"),
    ("https://page.example/?mode=review#item", "/canary", "https://page.example/canary/?mode=review#item"),
])
def test_origin_mount_is_applied_once_and_existing_url_components_preserved(url, base, expected):
    assert mounted_url(url, base) == expected
    assert mounted_url(expected, base) == expected


@pytest.fixture
def published(tmp_path, monkeypatch):
    for name, value in {"STATE_DIR": tmp_path / "state", "LOCK_DIR": tmp_path / "locks",
                        "BUS_ROOT": tmp_path / "bus", "CONFIG_DIR": tmp_path / "config"}.items():
        monkeypatch.setattr(cli, name, value)
    page = tmp_path / "pages" / "canary"
    (page / "versions").mkdir(parents=True)
    (page / "versions" / "v1.html").write_text('<html><body><h1 data-anchor-id="title">Canary</h1></body></html>')
    (page / "current.html").symlink_to("versions/v1.html")
    monkeypatch.setattr(cli, "_project_config", lambda project: {})
    monkeypatch.setattr(cli, "_ensure_shim_installed", lambda: (False, "inert"))
    monkeypatch.setattr(cli, "_ensure_hook_installed", lambda: (False, "inert"))
    monkeypatch.setattr(cli, "_is_process_alive", lambda pid: False)
    monkeypatch.setattr(cli, "_owner_fields", lambda: {"owner_session": "inert", "owner_agent": "codex",
                                                       "owner_label": "Inert", "owner_claimed_at": "2026-09-30T00:00:00Z"})
    monkeypatch.setattr(cli, "_write_owner_meta", lambda *args: None)
    starts = []
    def start(*args):
        starts.append(args)
        return 999999
    monkeypatch.setattr(cli, "_start_server", start)
    return SimpleNamespace(page=page, starts=starts)


@pytest.mark.parametrize("transport,mount,already_mounted", [("tailscale", "/canary", False),
                                                            ("tailscale", "/", False),
                                                            ("cloudflare", "/canary", True)])
def test_fresh_publish_stored_and_printed_url_reaches_exact_served_mount(published, monkeypatch, capsys,
                                                                       transport, mount, already_mounted):
    served_path = mount.rstrip("/") + "/"
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200 if self.path == served_path else 404)
            self.end_headers()
            self.wfile.write(b"inert mounted page")
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}/"
    transport_url = origin.rstrip("/") + served_path if already_mounted else origin
    monkeypatch.setattr(transports, "load", lambda name: SimpleNamespace(
        publish=lambda *args, **opts: {"url": transport_url, "details": {"transport": transport}}))
    args = SimpleNamespace(slug_dir=str(published.page), project="reviews", port=server.server_port,
                           transport=transport, hostname=None, path_prefix=mount, skip_js_lint=True,
                           no_verify=True, public=False)
    try:
        assert cli.cmd_publish(args) == 0
        state = json.loads((cli.STATE_DIR / "reviews.json").read_text())
        record = state["slugs"]["canary"]
        expected = origin.rstrip("/") + served_path
        assert record["url"] == expected
        assert record["local_url"] == f"http://localhost:{server.server_port}/"
        assert record["public_base_path"] == (mount.rstrip("/") or None)
        assert published.starts[0][-1] == mount.rstrip("/")
        assert f"URL:           {expected}" in capsys.readouterr().out
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(record["url"], timeout=2) as response:
            assert response.status == 200
            assert response.read() == b"inert mounted page"
        assert page_url(record) == expected
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_legacy_root_url_is_correct_in_status_handoff_inventory_and_mcp(published, monkeypatch, capsys):
    record = {"project": "reviews", "slug": "canary", "slug_dir": str(published.page), "pid": 999999,
              "port": 8900, "url": "https://page.example:8447/", "local_url": "http://localhost:8900/",
              "public_url": "https://public.example/canary/", "public_base_path": "/canary"}
    cli._save_state_for_project("reviews", {"project": "reviews", "slugs": {"canary": record}})
    monkeypatch.setattr(cli, "_running_servers", lambda: {})
    monkeypatch.setattr(cli, "_ps_command_snapshot", lambda: "")
    assert cli.cmd_status(SimpleNamespace(slug=None, retired=False)) == 0
    assert "https://page.example:8447/canary/" in capsys.readouterr().out
    from agent_annotate.providers import codex_app_server
    messages = []
    def deliver(thread, message):
        messages.append(message)
        return SimpleNamespace(accepted=True)
    monkeypatch.setattr(codex_app_server, "CodexAppServerAdapter", lambda: SimpleNamespace(deliver=deliver))
    cli._deliver_to_codex("inert", record, "reviews", "canary", {"comment_count": 1})
    assert "Page: https://page.example:8447/canary/." in messages[0]
    assert "inbox reviews/canary --unread" in messages[0]
    captured = []
    def collect(config):
        captured.extend(config["targets"])
        return {"limitations": []}
    monkeypatch.setattr(fleet, "collect_fleet", collect)
    cli._fleet_snapshot()
    assert captured[0]["url"] == "https://page.example:8447/canary/"
    pytest.importorskip("mcp")
    server = mcp_server.build_server()
    rows = server._tool_manager._tools["list_pages"].fn()
    assert rows[0]["url"] == "https://page.example:8447/canary/"
    assert rows[0]["public_url"] == "https://public.example/canary/"
    assert rows[0]["local_url"] == "http://localhost:8900/"
    assert json.loads((cli.STATE_DIR / "reviews.json").read_text())["slugs"]["canary"] == record


@pytest.mark.parametrize("mount,expected_slug", [(None, ""), ("/canary", "canary")])
def test_reroute_keeps_root_or_mounted_route_and_normalizes_origin_url(published, monkeypatch, mount, expected_slug):
    calls = []
    def publish(slug, port, **opts):
        calls.append((slug, port))
        return {"url": "https://new.example:8447/", "details": {"https_port": 8447}}
    monkeypatch.setattr(transports, "load", lambda name: SimpleNamespace(publish=publish))
    record = {"url": "https://old.example:8447/", "transport": "tailscale", "public_base_path": mount}
    url, _, base, error = cli._reroute("reviews", "canary", record, 8802)
    assert calls == [(expected_slug, 8802)]
    assert url == f"https://new.example:8447/{expected_slug + '/' if expected_slug else ''}"
    assert base == (mount or "") and error is None
