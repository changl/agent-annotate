"""projects.toml keys the CLI does not consume reach the transport.

The live transport hard-coded the env file and tunnel id; the packaged one
takes them as options. Without this passthrough a `cloudflare_tailscale`
section could name them and still publish nothing.
"""

import json
from types import SimpleNamespace

from agent_annotate import cli

SECTION = {"transport": "cloudflare_tailscale", "hostname": "reviews.example.com",
           "port_base": 8800, "path_prefix": None,
           "env_file": "/private/.env.local", "tunnel_id": "tun-1"}


def test_core_keys_stay_with_the_cli_and_the_rest_go_to_the_transport():
    opts = cli._transport_opts(SECTION)
    assert opts == {"env_file": "/private/.env.local", "tunnel_id": "tun-1"}
    assert cli._transport_opts({}) == {}
    assert cli._transport_opts(None) == {}


def test_publish_and_unpublish_hand_the_section_to_the_transport(tmp_path, monkeypatch):
    slug_dir = tmp_path / "reviews" / "demo"
    (slug_dir / "versions").mkdir(parents=True)
    (slug_dir / "versions" / "v1.html").write_text(
        "<html><body><p data-anchor-id='s:a'>a</p></body></html>", encoding="utf-8")

    state = {"project": "reviews", "slugs": {}}
    monkeypatch.setattr(cli, "_load_projects_toml", lambda: {"reviews": dict(SECTION)})
    monkeypatch.setattr(cli, "_check_js_lint", lambda p, skip=False: (True, []))
    monkeypatch.setattr(cli, "_load_state_for_project", lambda project: state)
    monkeypatch.setattr(cli, "_save_state_for_project",
                        lambda project, st: state.update(st))
    monkeypatch.setattr(cli, "_all_state_files", lambda: [tmp_path / "reviews.json"])
    monkeypatch.setattr(cli, "_find_free_port_after", lambda start, registered_pid=None: 8900)
    monkeypatch.setattr(cli, "_start_server", lambda *a, **k: 4242)
    monkeypatch.setattr(cli, "_stop_server", lambda pid: True)
    monkeypatch.setattr(cli, "_verify_published", lambda *a, **k: None)
    monkeypatch.setattr(cli, "_ensure_hook_installed", lambda: (False, "stub"))
    monkeypatch.setattr(cli, "_ensure_shim_installed", lambda *a, **k: (False, "stub"))
    monkeypatch.setattr(cli, "BUS_ROOT", tmp_path / "bus")

    seen = {}
    transport = SimpleNamespace(
        publish=lambda slug, port, **opts: seen.update(publish=opts) or {
            "url": "https://reviews.example.com/demo/",
            "details": {"transport": "cloudflare_tailscale", "hostname": "reviews.example.com",
                        "https_port": 8456, "tailscale": {"https_port": 8456}}},
        unpublish=lambda slug, **opts: seen.update(unpublish=opts) or {"ok": True, "details": {}},
    )
    monkeypatch.setattr("agent_annotate.transports.load", lambda name: transport)

    args = SimpleNamespace(slug_dir=str(slug_dir), project=None, port=None, transport=None,
                           hostname=None, path_prefix=None, skip_js_lint=True, no_verify=True,
                           verify_timeout=1.0)
    assert cli.cmd_publish(args) == 0
    assert seen["publish"]["env_file"] == "/private/.env.local"
    assert seen["publish"]["tunnel_id"] == "tun-1"
    assert seen["publish"]["hostname"] == "reviews.example.com"
    assert "port_base" not in seen["publish"]

    (tmp_path / "reviews.json").write_text(json.dumps(state))
    assert cli.cmd_unpublish(SimpleNamespace(slug="demo")) == 0
    assert seen["unpublish"]["env_file"] == "/private/.env.local"
    assert seen["unpublish"]["tunnel_id"] == "tun-1"
    assert seen["unpublish"]["https_port"] == 8456
