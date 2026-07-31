"""The tailscale transport owns a shared, machine-wide serve table.

Getting it wrong does not fail loudly — it silently steals another page's port
or leaks a new one on every re-publish. These tests pin the parts that make
that impossible: idempotency keyed on the origin, allocation that respects
ports claimed by anything at all, verification after every mutation, and a
teardown that refuses to act on a guess.
"""

import subprocess

import pytest

from agent_annotate.transports import tailscale

HOST = "macbook-pro.tail2b8ab9.ts.net"


def _state(mappings: dict[int, int], extra_tcp: tuple[int, ...] = ()) -> dict:
    """Build a `tailscale serve status --json` document."""
    return {
        "TCP": {str(p): {"HTTPS": True} for p in list(mappings) + list(extra_tcp)},
        "Web": {
            f"{HOST}:{serve}": {"Handlers": {"/": {"Proxy": f"http://127.0.0.1:{local}"}}}
            for serve, local in mappings.items()
        },
    }


class _Tailscale:
    """Records argv and answers `serve status --json` from a mutable table."""

    def __init__(self, mappings=None, extra_tcp=(), fail_on=None):
        self.mappings = dict(mappings or {})
        self.extra_tcp = extra_tcp
        self.calls: list[list[str]] = []
        self.fail_on = fail_on
        self.apply_mutations = True

    def __call__(self, argv, timeout=45):
        import json as _json

        self.calls.append(argv)
        if self.fail_on and self.fail_on in " ".join(argv):
            return subprocess.CompletedProcess(argv, 1, "", "boom")
        if argv[1:3] == ["serve", "status"]:
            return subprocess.CompletedProcess(
                argv, 0, _json.dumps(_state(self.mappings, self.extra_tcp)), "")
        if argv[1] == "serve" and argv[-1] == "off":
            port = int(argv[-2].split("=")[1])
            if self.apply_mutations:
                self.mappings.pop(port, None)
            return subprocess.CompletedProcess(argv, 0, "", "")
        if argv[1] == "serve":
            port = int([a for a in argv if a.startswith("--https=")][0].split("=")[1])
            local = int(argv[-1].rsplit(":", 1)[1])
            if self.apply_mutations:
                self.mappings[port] = local
            return subprocess.CompletedProcess(argv, 0, "", "")
        if argv[1] == "status":
            return subprocess.CompletedProcess(
                argv, 0, _json.dumps({"Self": {"DNSName": HOST + "."}}), "")
        raise AssertionError(f"unexpected argv: {argv}")


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setattr(tailscale, "STATE_DIR", tmp_path)

    def _install(ts):
        monkeypatch.setattr(tailscale, "_run", ts)
        return ts

    return _install


def test_publish_creates_the_lowest_free_serve_port(fake):
    ts = fake(_Tailscale({8443: 8807, 8444: 8810}))
    result = tailscale.publish("demo", 8900)

    assert result["url"] == f"https://{HOST}:8445/"
    assert result["details"]["https_port"] == 8445
    assert result["details"]["action"] == "created"
    assert ["tailscale", "serve", "--bg", "--https=8445",
            "http://127.0.0.1:8900"] in ts.calls


def test_republishing_the_same_port_reuses_the_mapping(fake):
    """Re-publish must not leak a second serve port for a page that already
    has one — the serve table has no slug to deduplicate on, so the origin is
    the identity."""
    ts = fake(_Tailscale({8443: 8807, 8444: 8900}))
    result = tailscale.publish("demo", 8900)

    assert result["details"]["https_port"] == 8444
    assert result["details"]["action"] == "existing"
    assert not any(c[1] == "serve" and "--bg" in c for c in ts.calls)


def test_localhost_and_loopback_forms_are_the_same_origin(fake):
    """tailscale may echo back http://localhost:<p>; treating that as a
    different origin would allocate a duplicate port on every publish."""
    ts = _Tailscale()
    ts.mappings = {}
    state = _state({})
    state["Web"][f"{HOST}:8443"] = {
        "Handlers": {"/": {"Proxy": "http://localhost:8900"}}
    }
    assert tailscale._find_existing(state, 8900) == 8443


def test_ports_claimed_by_a_raw_tcp_forward_are_not_reused(fake):
    """A TCP entry without a Web handler still owns the port."""
    fake(_Tailscale({8443: 8807}, extra_tcp=(8444, 8445)))
    result = tailscale.publish("demo", 8900)
    assert result["details"]["https_port"] == 8446


def test_the_funnel_port_is_never_allocated(fake):
    fake(_Tailscale({}))
    result = tailscale.publish("demo", 8900)
    assert result["details"]["https_port"] == 8443
    assert tailscale.DEFAULT_PORT_RANGE[0] > 443


def test_a_serve_that_reports_success_but_leaves_no_mapping_raises(fake):
    """Exit code 0 is not evidence. Silent no-ops are what made publish print
    a URL for a route that was never registered."""
    ts = _Tailscale({})
    ts.apply_mutations = False
    fake(ts)
    with pytest.raises(RuntimeError, match="did not register"):
        tailscale.publish("demo", 8900)


def test_serve_failure_is_reported_with_the_command(fake):
    fake(_Tailscale({}, fail_on="--bg"))
    with pytest.raises(RuntimeError, match="tailscale serve --bg"):
        tailscale.publish("demo", 8900)


def test_exhausted_port_range_names_the_fix(fake):
    fake(_Tailscale({p: 9000 + i for i, p in enumerate(range(8443, 8500))}))
    with pytest.raises(RuntimeError, match="no free tailscale serve port"):
        tailscale.publish("demo", 8900)


def test_a_moved_local_port_reclaims_the_orphaned_serve_port(fake):
    """Caught in a live re-publish, not by a unit test: the slug's local port
    moved 8890 -> 8891, so no existing mapping matched, a second serve port
    was allocated, and 8456 was left fronting a dead origin forever."""
    ts = fake(_Tailscale({8456: 8890}))
    result = tailscale.publish(
        "demo", 8891, previous={"port": 8890, "details": {"https_port": 8456}})

    assert result["details"]["reclaimed_https_port"] == 8456
    # The invariant that matters: one slug, one serve port, whatever its number.
    assert ts.mappings == {result["details"]["https_port"]: 8891}


def test_reclaim_leaves_a_serve_port_that_was_recycled(fake):
    """If the old serve port now fronts someone else's live page, removing it
    would take that page down."""
    ts = fake(_Tailscale({8456: 7777}))
    result = tailscale.publish(
        "demo", 8891, previous={"port": 8890, "details": {"https_port": 8456}})

    assert "reclaimed_https_port" not in result["details"]
    assert ts.mappings[8456] == 7777
    assert result["details"]["https_port"] != 8456


def test_reclaim_reads_a_composite_transports_recorded_details(fake):
    """cloudflare_tailscale nests the serve port under `tailscale`."""
    fake(_Tailscale({8456: 8890}))
    result = tailscale.publish(
        "demo", 8891,
        previous={"port": 8890, "details": {"transport": "cloudflare_tailscale",
                                            "tailscale": {"https_port": 8456}}})
    assert result["details"]["reclaimed_https_port"] == 8456


def test_reclaim_needs_the_old_local_port_to_prove_ownership(fake):
    """A serve port with no recorded origin cannot be shown to be ours."""
    ts = fake(_Tailscale({8456: 8890}))
    result = tailscale.publish("demo", 8891, previous={"details": {"https_port": 8456}})

    assert "reclaimed_https_port" not in result["details"]
    assert ts.mappings[8456] == 8890


def test_republish_on_an_unchanged_port_reclaims_nothing(fake):
    ts = fake(_Tailscale({8456: 8890}))
    result = tailscale.publish(
        "demo", 8890, previous={"port": 8890, "details": {"https_port": 8456}})

    assert result["details"]["action"] == "existing"
    assert "reclaimed_https_port" not in result["details"]
    assert ts.mappings == {8456: 8890}


def test_unpublish_removes_the_recorded_serve_port(fake):
    ts = fake(_Tailscale({8443: 8807, 8455: 8813}))
    result = tailscale.unpublish("demo", https_port=8455, port=8813)

    assert result["ok"] is True
    assert result["details"]["action"] == "removed"
    assert ["tailscale", "serve", "--https=8455", "off"] in ts.calls
    assert 8443 in ts.mappings  # the neighbour is untouched


def test_unpublish_without_a_port_refuses_to_guess(fake):
    """A slug name cannot identify a serve port. Guessing would tear down
    someone else's live page."""
    ts = fake(_Tailscale({8443: 8807}))
    result = tailscale.unpublish("demo")

    assert result["details"]["action"] == "noop"
    assert "refusing to guess" in result["details"]["reason"]
    assert ts.mappings == {8443: 8807}


def test_unpublish_skips_a_serve_port_that_was_recycled(fake):
    """The recorded port now fronts a different origin — another publish took
    it. Removing it would break that page instead of ours."""
    ts = fake(_Tailscale({8455: 9999}))
    result = tailscale.unpublish("demo", https_port=8455, port=8813)

    assert result["details"]["action"] == "noop"
    assert "now proxies" in result["details"]["reason"]
    assert ts.mappings == {8455: 9999}


def test_unpublish_finds_the_mapping_by_local_port(fake):
    ts = fake(_Tailscale({8443: 8807, 8455: 8813}))
    result = tailscale.unpublish("demo", port=8813)
    assert result["details"]["https_port"] == 8455
    assert ts.mappings == {8443: 8807}


def test_unpublish_of_an_absent_mapping_is_a_noop(fake):
    fake(_Tailscale({8443: 8807}))
    result = tailscale.unpublish("demo", https_port=8499)
    assert result["ok"] is True
    assert result["details"]["action"] == "noop"


def test_status_maps_a_local_port_to_its_public_url(fake):
    fake(_Tailscale({8443: 8807, 8455: 8813}))
    out = tailscale.status("demo", port=8813)
    assert out["url"] == f"https://{HOST}:8455/"
    assert out["mappings"] == {8443: "http://127.0.0.1:8807",
                               8455: "http://127.0.0.1:8813"}


def test_hostname_falls_back_to_tailscale_status_when_serve_is_empty(fake):
    fake(_Tailscale({}))
    assert tailscale._hostname({}, "tailscale") == HOST


def test_missing_binary_names_the_override(monkeypatch, tmp_path):
    monkeypatch.setattr(tailscale, "STATE_DIR", tmp_path)

    def _missing(argv, **kw):
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(subprocess, "run", _missing)
    with pytest.raises(RuntimeError, match="ANNOTATE_TAILSCALE_BIN"):
        tailscale.publish("demo", 8900)
