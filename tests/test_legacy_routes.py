from types import SimpleNamespace

import pytest

from agent_annotate import legacy_routes


def _record(name="tailscale"):
    ts = {"hostname": "host.ts.net", "https_port": 8447, "local_port": 8800, "slug": "review"}
    cf = {"hostname": "review.example", "tunnel_id": "recorded-tunnel", "path": "/review/.*",
          "port": 8800, "service": "http://localhost:8800"}
    details = ts if name == "tailscale" else cf
    url = "https://host.ts.net:8447/review/" if name == "tailscale" else "https://review.example/review/"
    if name == "cloudflare_tailscale":
        details = {**cf, "public": True, "tailscale": ts, "origin_service": "https://host.ts.net:8447",
                   "service": "https://host.ts.net:8447"}
    return {"port": 8900, "public_base_path": "/review", "legacy_routes": [
        {"transport": name, "transport_details": details, "url": url}]}


def _tail(mappings=None, hostname="host.ts.net"):
    state = {8447: "http://127.0.0.1:8800", 8448: "http://127.0.0.1:9999"} if mappings is None else dict(mappings)
    calls = []

    def status(**opts):
        return {"hostname": hostname, "mappings": dict(state)}

    def unpublish(slug, **opts):
        calls.append((slug, opts))
        del state[opts["https_port"]]
        return {"ok": True, "details": {"action": "removed"}}

    return SimpleNamespace(status=status, unpublish=unpublish, calls=calls, state=state)


def _cf(service="http://localhost:8800"):
    state = [{"hostname": "review.example", "path": "/review/.*", "service": service},
             {"hostname": "other.example", "path": "/review/.*", "service": "http://localhost:9999"}]
    calls = []

    def status(slug, **opts):
        return {"hostname": opts["hostname"], "matches": [dict(rule) for rule in state
                if rule["hostname"] == opts["hostname"] and rule["path"] == f"/{slug}/.*"]}

    def unpublish(slug, **opts):
        calls.append((slug, opts))
        state[:] = [rule for rule in state if rule["hostname"] != opts["hostname"] or rule["path"] != f"/{slug}/.*"]
        return {"ok": True, "details": {"action": "removed"}}

    return SimpleNamespace(status=status, unpublish=unpublish, calls=calls, state=state)


def test_no_legacy_routes_do_nothing(monkeypatch):
    monkeypatch.setattr(legacy_routes.transports, "load", lambda name: pytest.fail("unnecessary route lookup"))
    assert legacy_routes.cleanup({}, {}) == []
    assert legacy_routes.cleanup({"legacy_routes": [{"transport": "local"}]}, {}) == []


def test_cleans_recorded_tailnet_route_on_original_port_and_preserves_other_services(monkeypatch):
    module = _tail()
    monkeypatch.setattr(legacy_routes.transports, "load", lambda name: module if name == "tailscale" else pytest.fail(name))
    outcomes = legacy_routes.cleanup(_record(), {"binary": "inert-tailscale"})
    assert outcomes == [{"transport": "tailscale", "action": "removed"}]
    assert module.calls == [("review", {"binary": "inert-tailscale", "hostname": "host.ts.net", "https_port": 8447, "port": 8800})]
    assert module.state == {8448: "http://127.0.0.1:9999"}


def test_cleans_exact_cloudflare_rule_with_recorded_tunnel_and_config_credentials(monkeypatch):
    module = _cf()
    monkeypatch.setattr(legacy_routes.transports, "load", lambda name: module if name == "cloudflare" else pytest.fail(name))
    config = {"token": "inert-token", "account_id": "inert-account", "hostname": "current.example", "tunnel_id": "current-tunnel"}
    assert legacy_routes.cleanup(_record("cloudflare"), config) == [{"transport": "cloudflare", "action": "removed"}]
    assert module.calls == [("review", {**config, "hostname": "review.example", "tunnel_id": "recorded-tunnel", "expected_service": "http://localhost:8800"})]
    assert module.state == [{"hostname": "other.example", "path": "/review/.*", "service": "http://localhost:9999"}]


def test_combined_route_removes_public_ingress_before_private_origin(monkeypatch):
    cf, ts = _cf("https://host.ts.net:8447"), _tail()
    order = []
    for name, module in (("cloudflare", cf), ("tailscale", ts)):
        original = module.unpublish
        module.unpublish = lambda slug, _name=name, _original=original, **opts: (order.append(_name), _original(slug, **opts))[1]
    monkeypatch.setattr(legacy_routes.transports, "load", lambda name: {"cloudflare": cf, "tailscale": ts}[name])
    assert len(legacy_routes.cleanup(_record("cloudflare_tailscale"), {"env_file": "inert-credentials.env"})) == 2
    assert order == ["cloudflare", "tailscale"]


def test_combined_private_route_does_not_require_cloudflare_credentials(monkeypatch):
    record = _record()
    record["legacy_routes"][0].update(transport="cloudflare_tailscale", transport_details={
        "public": False, "tailscale": record["legacy_routes"][0]["transport_details"]})
    ts = _tail()
    monkeypatch.setattr(legacy_routes.transports, "load", lambda name: ts if name == "tailscale" else pytest.fail("unexpected Cloudflare access"))
    assert legacy_routes.cleanup(record, {}) == [{"transport": "tailscale", "action": "removed"}]


@pytest.mark.parametrize("name", ["tailscale", "cloudflare"])
def test_missing_prior_route_is_proven_absent_without_mutation(monkeypatch, name):
    module = _tail({}) if name == "tailscale" else _cf()
    if name == "cloudflare":
        module.state[:] = [rule for rule in module.state if rule["hostname"] != "review.example"]
    monkeypatch.setattr(legacy_routes.transports, "load", lambda requested: module)
    outcome = legacy_routes.cleanup(_record(name), {})[0]
    assert outcome["action"] == "noop"
    assert module.calls == []


@pytest.mark.parametrize("name", ["tailscale", "cloudflare"])
def test_changed_origin_is_refused_without_teardown(monkeypatch, name):
    module = _tail({8447: "http://127.0.0.1:9999"}) if name == "tailscale" else _cf("http://localhost:9999")
    monkeypatch.setattr(legacy_routes.transports, "load", lambda requested: module)
    with pytest.raises(RuntimeError, match="another origin.*keep the page registered"):
        legacy_routes.cleanup(_record(name), {})
    assert module.calls == []


def test_hostname_drift_is_refused_without_teardown(monkeypatch):
    module = _tail(hostname="renamed.ts.net")
    monkeypatch.setattr(legacy_routes.transports, "load", lambda name: module)
    with pytest.raises(RuntimeError, match="hostname/route table differs"):
        legacy_routes.cleanup(_record(), {})
    assert module.calls == []


def test_missing_cloudflare_credentials_prevent_any_mutation(monkeypatch):
    calls = []

    def status(*args, **opts):
        raise RuntimeError("CLOUDFLARE_API_TOKEN is required")

    module = SimpleNamespace(status=status, unpublish=lambda *args, **opts: calls.append(args))
    monkeypatch.setattr(legacy_routes.transports, "load", lambda name: module)
    with pytest.raises(RuntimeError, match="CLOUDFLARE_API_TOKEN.*Restore recorded credentials"):
        legacy_routes.cleanup(_record("cloudflare"), {})
    assert calls == []


@pytest.mark.parametrize("receipt", [None, {"ok": False}, {"ok": True, "details": {}},
    {"ok": True, "details": {"action": "noop", "reason": "port now belongs to another page"}}])
def test_failed_or_ambiguous_teardown_receipt_is_not_success(monkeypatch, receipt):
    module = _tail()
    module.unpublish = lambda *args, **opts: receipt
    monkeypatch.setattr(legacy_routes.transports, "load", lambda name: module)
    with pytest.raises(RuntimeError, match="cleanup refused.*keep the page registered"):
        legacy_routes.cleanup(_record(), {})


@pytest.mark.parametrize("name", ["tailscale", "cloudflare"])
def test_success_receipt_without_actual_route_removal_is_refused(monkeypatch, name):
    module = _tail() if name == "tailscale" else _cf()
    module.unpublish = lambda *args, **opts: {"ok": True, "details": {"action": "removed"}}
    monkeypatch.setattr(legacy_routes.transports, "load", lambda requested: module)
    with pytest.raises(RuntimeError, match="removal was not verified"):
        legacy_routes.cleanup(_record(name), {})


@pytest.mark.parametrize("change", [
    {"transport": "unknown"},
    {"port": 9999},
    {"url": "https://host.ts.net:8447/other-page/"},
    {"url": "https://foreign.example:8447/review/"},
])
def test_incomplete_or_conflicting_route_receipts_refuse_before_transport_calls(monkeypatch, change):
    record = _record()
    record["legacy_routes"][0].update(change)
    monkeypatch.setattr(legacy_routes.transports, "load", lambda name: pytest.fail("unproven receipt reached transport"))
    with pytest.raises(RuntimeError, match="cleanup refused"):
        legacy_routes.cleanup(record, {})
