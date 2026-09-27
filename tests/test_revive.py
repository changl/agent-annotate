"""`annotate revive`: bring dead pages back after a reboot or crash.

On 2026-09-27 a macOS update rebooted the Mac and every page server died.
Nothing restarted them, and re-running `publish` would have made whoever ran
it the owner, so each page would have stopped notifying the session that
asked its questions. These tests pin what revive may change (pid, route,
revived_at) and what it must keep (port and owner).
"""

import json
from types import SimpleNamespace

import pytest

from agent_annotate import cli


@pytest.fixture
def estate(tmp_path, monkeypatch):
    slug_dir = tmp_path / "reviews" / "demo"
    (slug_dir / "versions").mkdir(parents=True)
    (slug_dir / "versions" / "v1.html").write_text("<html></html>", encoding="utf-8")
    (slug_dir / "current.html").symlink_to("versions/v1.html")
    state_dir = tmp_path / "state"
    monkeypatch.setattr(cli, "STATE_DIR", state_dir)
    monkeypatch.setattr(cli, "LOCK_DIR", tmp_path / "locks")
    monkeypatch.setattr(cli, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(cli, "BUS_ROOT", tmp_path / "bus")
    record = {"slug": "demo", "slug_dir": str(slug_dir), "project": "reviews",
              "pid": 999999, "port": 8899, "transport": "local", "url": "http://localhost:8899/",
              "bus_file": str(tmp_path / "bus" / "reviews" / "demo.ndjson"),
              "owner_session": "owner-session-1", "owner_label": "other:owner"}
    cli._save_state_for_project("reviews", {"project": "reviews", "slugs": {"demo": record}})

    started = []

    def _start(slug_dir, port, bus_dir, pbp):
        started.append((str(slug_dir), port, pbp))
        return 4242

    monkeypatch.setattr(cli, "_start_server", _start)
    monkeypatch.setattr(cli, "_wait_listening", lambda port, pid, seconds=8.0: True)
    monkeypatch.setattr(cli, "_find_free_port_after", lambda p, registered_pid=None: p)
    monkeypatch.setattr(cli, "_running_servers", lambda: {})
    return SimpleNamespace(slug_dir=slug_dir, started=started, tmp=tmp_path)


def _args(**over):
    base = dict(dry_run=False, quiet=False, install=False, uninstall=False, interval=60)
    base.update(over)
    return SimpleNamespace(**base)


def _record():
    return cli._load_state_for_project("reviews")["slugs"]["demo"]


def test_a_dead_page_restarts_on_its_port_with_its_owner(estate, capsys):
    assert cli.cmd_revive(_args()) == 0

    assert estate.started == [(str(estate.slug_dir), 8899, "")]
    rec = _record()
    assert rec["pid"] == 4242
    assert rec["port"] == 8899
    assert rec["owner_session"] == "owner-session-1"
    assert rec["owner_label"] == "other:owner"
    assert rec["revived_at"]
    assert "revived" in capsys.readouterr().out


def test_dry_run_starts_nothing(estate, capsys):
    assert cli.cmd_revive(_args(dry_run=True)) == 0
    assert estate.started == []
    assert _record()["pid"] == 999999
    assert "would-revive" in capsys.readouterr().out


def test_a_routed_page_on_a_busy_port_is_skipped_not_moved(estate, monkeypatch, capsys):
    """Every route points at the recorded port; moving it strands them."""
    state = cli._load_state_for_project("reviews")
    state["slugs"]["demo"]["transport"] = "cloudflare_tailscale"
    cli._save_state_for_project("reviews", state)
    monkeypatch.setattr(cli, "_find_free_port_after", lambda p, registered_pid=None: p + 1)
    assert cli.cmd_revive(_args()) == 0
    assert estate.started == []
    assert "port 8899 is in use" in capsys.readouterr().out


def test_a_local_page_on_a_busy_port_moves(estate, monkeypatch):
    """Nothing routes to a local page, so its port may change."""
    monkeypatch.setattr(cli, "_find_free_port_after", lambda p, registered_pid=None: p + 1)
    assert cli.cmd_revive(_args()) == 0
    assert estate.started == [(str(estate.slug_dir), 8900, "")]
    assert _record()["port"] == 8900
    assert _record()["url"] == "http://localhost:8900/"


def test_a_page_served_by_an_unrecorded_pid_is_adopted(estate, monkeypatch):
    live = {str(estate.slug_dir.resolve()): [{"pid": 5555, "port": 8899}]}
    monkeypatch.setattr(cli, "_running_servers", lambda: live)
    monkeypatch.setattr(cli, "_is_process_alive", lambda pid: pid == 5555)
    assert cli.cmd_revive(_args()) == 0
    assert estate.started == []
    assert _record()["pid"] == 5555


def test_a_non_local_page_reroutes_before_it_starts(estate, monkeypatch):
    """The route is re-run on every revive: it is how a page moves onto the
    machine's current tailnet name after a rename."""
    state = cli._load_state_for_project("reviews")
    state["slugs"]["demo"].update({"transport": "fake", "public_base_path": "/demo",
                                   "transport_details": {"https_port": 8447}})
    cli._save_state_for_project("reviews", state)
    calls = []

    class _Fake:
        @staticmethod
        def publish(slug, port, **opts):
            calls.append((slug, port, opts.get("previous")))
            return {"url": "https://m1max.example.ts.net:8460/", "details": {"https_port": 8460}}

    import agent_annotate.transports as transports
    monkeypatch.setattr(transports, "load", lambda name: _Fake)
    monkeypatch.setattr(cli, "_project_config", lambda project: {"transport": "fake"})

    assert cli.cmd_revive(_args()) == 0
    assert calls == [("demo", 8899, {"port": 8899, "details": {"https_port": 8447}})]
    rec = _record()
    assert rec["url"] == "https://m1max.example.ts.net:8460/"
    assert rec["transport_details"] == {"https_port": 8460}
    assert estate.started == [(str(estate.slug_dir), 8899, "/demo")]


def test_a_server_that_dies_on_start_is_reported(estate, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_wait_listening", lambda port, pid, seconds=8.0: False)
    assert cli.cmd_revive(_args()) == 1
    assert _record()["pid"] == 999999
    assert "failed" in capsys.readouterr().out


def test_the_plist_runs_revive_at_login_and_on_an_interval(estate):
    body = cli._revive_plist(60)
    assert "<string>revive</string>" in body
    assert "<key>RunAtLoad</key><true/>" in body
    assert "<integer>60</integer>" in body
    assert json.dumps(cli.REVIVE_LABEL).strip('"') in body
