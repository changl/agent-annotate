"""The composite transport is the only one that produces a working public page.

A Cloudflare ingress rule whose service is `http://localhost:<port>` answers
502 through this tunnel even with cloudflared running on the same host —
verified 2026-07-31 against a live ingress pair that differed only in origin.
The connector needs an origin it can actually dial, which is the `tailscale
serve` endpoint. Publishing the two halves separately is how pages ended up
half-registered, so they are composed and their failure modes are pinned here.
"""

import sys
import types

import pytest

from agent_annotate.transports import cloudflare, cloudflare_tailscale


def _fake_module(name, **fns):
    mod = types.ModuleType(name)
    for k, v in fns.items():
        setattr(mod, k, v)
    return mod


@pytest.fixture
def siblings(monkeypatch):
    calls = {"ts_publish": [], "cf_publish": [], "ts_unpublish": [], "cf_unpublish": []}

    def ts_publish(slug, port, **opts):
        calls["ts_publish"].append((slug, port, opts))
        return {"url": "https://host.ts.net:8456/",
                "details": {"transport": "tailscale", "https_port": 8456,
                            "hostname": "host.ts.net", "local_port": port}}

    def cf_publish(slug, port, **opts):
        calls["cf_publish"].append((slug, port, opts))
        return {"url": f"https://reviews.example.com/{slug}/",
                "details": {"transport": "cloudflare", "service": opts.get("service")}}

    def ts_unpublish(slug, **opts):
        calls["ts_unpublish"].append((slug, opts))
        return {"ok": True, "details": {"action": "removed"}}

    def cf_unpublish(slug, **opts):
        calls["cf_unpublish"].append((slug, opts))
        return {"ok": True, "details": {"action": "removed"}}

    monkeypatch.setitem(sys.modules, "annotate_transport_tailscale",
                        _fake_module("annotate_transport_tailscale",
                                     publish=ts_publish, unpublish=ts_unpublish,
                                     status=lambda s=None, **o: {"transport": "tailscale"}))
    monkeypatch.setitem(sys.modules, "annotate_transport_cloudflare",
                        _fake_module("annotate_transport_cloudflare",
                                     publish=cf_publish, unpublish=cf_unpublish,
                                     status=lambda s=None, **o: {"transport": "cloudflare",
                                                                 "url": "https://x/"}))
    return calls


def test_the_tunnel_origin_is_the_tailscale_endpoint_not_localhost(siblings):
    result = cloudflare_tailscale.publish("demo", 8900, hostname="reviews.example.com")

    service = siblings["cf_publish"][0][2]["service"]
    assert service == "https://host.ts.net:8456"
    assert "localhost" not in service
    assert result["url"] == "https://reviews.example.com/demo/"
    assert result["details"]["https_port"] == 8456
    assert result["details"]["tailscale"]["local_port"] == 8900


def test_the_service_url_carries_no_trailing_slash(siblings):
    """cloudflared appends the request path to the service; a trailing slash
    doubles it on every request."""
    cloudflare_tailscale.publish("demo", 8900)
    assert not siblings["cf_publish"][0][2]["service"].endswith("/")


def test_a_failed_tunnel_write_does_not_leak_the_serve_port(monkeypatch, siblings):
    """Half-registered publishes are how ports leaked: the tailnet endpoint
    survived a tunnel failure and nothing ever reclaimed it."""
    def _boom(slug, port, **opts):
        raise RuntimeError("Cloudflare API 403")

    sys.modules["annotate_transport_cloudflare"].publish = _boom

    with pytest.raises(RuntimeError, match="403"):
        cloudflare_tailscale.publish("demo", 8900)

    assert siblings["ts_unpublish"], "serve port was left behind"
    assert siblings["ts_unpublish"][0][1]["https_port"] == 8456


def test_unpublish_removes_the_tunnel_rule_before_the_origin(siblings):
    """Reverse order would leave the public route pointing at an origin that
    is already gone — a 502 for anyone mid-review."""
    order = []
    sys.modules["annotate_transport_cloudflare"].unpublish = (
        lambda slug, **o: (order.append("cf"), {"ok": True, "details": {}})[1])
    sys.modules["annotate_transport_tailscale"].unpublish = (
        lambda slug, **o: (order.append("ts"), {"ok": True, "details": {}})[1])

    result = cloudflare_tailscale.unpublish("demo", https_port=8456, port=8900)

    assert order == ["cf", "ts"]
    assert result["ok"] is True


# ── the plain cloudflare transport's half of the contract ───────────────────

def test_cloudflare_publish_uses_an_explicit_service_when_given(monkeypatch):
    captured = {}

    def _api(method, url, token, body=None):
        import json as _json
        if method == "GET":
            return {"result": {"config": {"ingress": [{"service": "http_status:404"}]}}}
        captured["payload"] = _json.loads(body)
        return {"success": True}

    monkeypatch.setattr(cloudflare, "_api_request", _api)
    monkeypatch.setattr(cloudflare, "_backup", lambda cur: "/tmp/backup.json")
    monkeypatch.setattr(cloudflare, "_auth",
                        lambda opts: ("acct", "tun", "reviews.example.com", "tok"))

    result = cloudflare.publish("demo", 8900, service="https://host.ts.net:8456")

    rule = captured["payload"]["config"]["ingress"][0]
    assert rule["service"] == "https://host.ts.net:8456"
    assert rule["path"] == "/demo/.*"
    assert result["details"]["service"] == "https://host.ts.net:8456"


def test_cloudflare_publish_still_defaults_to_loopback(monkeypatch):
    """Kept for connectors that CAN reach loopback; the composite never
    relies on it."""
    captured = {}

    def _api(method, url, token, body=None):
        import json as _json
        if method == "GET":
            return {"result": {"config": {"ingress": []}}}
        captured["payload"] = _json.loads(body)
        return {"success": True}

    monkeypatch.setattr(cloudflare, "_api_request", _api)
    monkeypatch.setattr(cloudflare, "_backup", lambda cur: "/tmp/backup.json")
    monkeypatch.setattr(cloudflare, "_auth",
                        lambda opts: ("acct", "tun", "reviews.example.com", "tok"))

    cloudflare.publish("demo", 8900)

    assert captured["payload"]["config"]["ingress"][0]["service"] == "http://localhost:8900"
