"""Fleet collection never discovers hosts, follows redirects, or emits private payloads."""

import copy
import json
import os
import ssl
import subprocess
import sys
import time
from http.client import BadStatusLine, IncompleteRead, RemoteDisconnected
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from agent_annotate import fleet


def _target(**changes):
    return {"machine": "mbp", "project": "proj", "slug": "demo", "url": "https://example.test/demo/", **changes}


def _config(*targets):
    return {"schema_version": 1, "targets": list(targets) if targets else [_target()]}


def _responses(**changes):
    responses = {
        "current.meta.json": {"current": "v2", "owner": {"owner_session": "private-owner"}},
        "api/capabilities": {"version": "2.21.0", "runtime": {"package_version": "2.21.0", "build_id": "a" * 40},
                             "automatic_round_delivery": True, "rounds": True, "batch": True, "decision_schema": 2},
        "api/delivery": {"latest": {"state": "uncertain", "detail": "private transport error"}},
    }
    responses.update(changes)
    return responses


def _fetch(responses, calls=None):
    def fetch(url, *, timeout, max_bytes):
        if calls is not None:
            calls.append((url, timeout, max_bytes))
        path = url.removeprefix("https://example.test/demo/")
        value = responses[path]
        if isinstance(value, BaseException):
            raise value
        if isinstance(value, tuple):
            return value
        return 200, json.dumps(value).encode()
    return fetch


def test_collection_whitelists_runtime_owner_delivery_and_aggregates():
    calls = []
    result = fleet.collect_fleet(_config(), fetch=_fetch(_responses(), calls))
    row = result["targets"][0]
    assert row["current_version"] == "v2"
    assert row["package_version"] == "2.21.0" and row["build_id"] == "a" * 40
    assert row["owner_present"] is True
    assert row["latest_delivery_state"] == "uncertain"
    assert row["health"] == "healthy" and row["errors"] == []
    assert result["summary"]["by_machine"] == {"mbp": 1}
    assert result["summary"]["by_version"] == {"2.21.0": 1}
    assert result["summary"]["delivery_states"]["uncertain"] == 1
    assert len(calls) == 3
    assert all(timeout == 3.0 and maximum == 65536 for _, timeout, maximum in calls)


@pytest.mark.parametrize("url, expected", [
    ("http://localhost:8802/demo", "http://localhost:8802/demo/"),
    ("http://127.0.0.1:8802/", "http://127.0.0.1:8802/"),
    ("http://127.1.2.3:8802/", "http://127.1.2.3:8802/"),
    ("http://[::1]:8802/demo/", "http://[::1]:8802/demo/"),
    ("https://EXAMPLE.test:443/demo", "https://example.test/demo/"),
    ("https://example.test:8447/base/demo/", "https://example.test:8447/base/demo/"),
])
def test_explicit_https_hosts_and_loopback_http_are_normalized(url, expected):
    assert fleet.validate_config(_config(_target(url=url)))["targets"][0]["url"] == expected


@pytest.mark.parametrize("url", [
    "http://example.test/demo/", "http://192.168.1.2/demo/", "http://2130706433/", "http://localhost.example.test/",
    "https://user:secret@example.test/demo/", "https://@example.test/demo/", "https://example.test/demo/?token=secret",
    "https://example.test/demo/?", "https://example.test/demo/#", "https://example.test/demo/#secret",
    "https://example.test/demo/\n", "https://example.test\\@evil.test/", "file:///etc/passwd", "//example.test/demo/",
    "https:///demo/", "https://example.test:0/", "https://example.test:65536/", "https://[broken/",
    "https://example.test/../demo/", "https://example.test/%2e%2e/demo/", "https://example.test/%0a/demo/",
    "https://example.test/%5c/demo/", "https://example.test/%xx/demo/",
])
def test_unsafe_base_urls_are_rejected_before_any_fetch(url):
    with pytest.raises(ValueError):
        fleet.collect_fleet(_config(_target(url=url)), fetch=lambda *args, **kwargs: pytest.fail("unsafe target fetched"))


@pytest.mark.parametrize("config", [None, [], {}, {"schema_version": True, "targets": []},
    {"schema_version": 2, "targets": []}, {"schema_version": 1, "targets": {}, "extra": True},
    {"schema_version": 1, "targets": [{"machine": "mbp"}]},
    _config(_target(machine="reviewer@example.com")), _config(_target(project="../secret")),
    _config(_target(slug=".")), _config(_target(machine="x" * 129)), _config({**_target(), "session": "secret"}),
])
def test_config_is_strict_and_errors_do_not_echo_private_input(config):
    with pytest.raises(ValueError) as error:
        fleet.validate_config(config)
    assert "reviewer@example.com" not in str(error.value)
    assert "secret" not in str(error.value)


def test_duplicate_identity_or_canonical_url_is_rejected():
    for second in (_target(url="https://other.test/demo/"), _target(slug="another", url="https://EXAMPLE.test:443/demo")):
        with pytest.raises(ValueError, match="unique"):
            fleet.validate_config(_config(_target(), second))


def test_target_bounds_and_validation_does_not_mutate_config():
    config = _config(*[_target(slug=f"p{i}", url=f"https://example.test/p{i}/") for i in range(64)])
    before = copy.deepcopy(config)
    assert len(fleet.validate_config(config)["targets"]) == 64
    assert config == before
    config["targets"].append(_target(slug="p64", url="https://example.test/p64/"))
    with pytest.raises(ValueError, match="64"):
        fleet.validate_config(config)


def test_legacy_404_capabilities_and_delivery_stay_unknown():
    result = fleet.collect_fleet(_config(), fetch=_fetch(_responses(**{
        "current.meta.json": {"current": "v1"}, "api/capabilities": (404, b"private error"), "api/delivery": (404, b"private error"),
    })))
    row = result["targets"][0]
    assert row["owner_present"] is False
    assert row["latest_delivery_state"] == "unknown"
    assert row["capabilities"]["automatic_round_delivery"] is None
    assert row["package_version"] is None and row["build_id"] is None
    assert row["health"] == "degraded"
    assert result["summary"]["capability_gaps"]["automatic_round_delivery"] == {"unknown": 1, "unsupported": 0}


def test_missing_legacy_capability_fields_are_distinct_from_explicit_false_and_zero():
    result = fleet.collect_fleet(_config(), fetch=_fetch(_responses(**{
        "api/capabilities": {"version": "2.19.0", "batch": False, "decision_schema": 0},
        "api/delivery": {"latest": None},
    })))
    row = result["targets"][0]
    assert row["package_version"] == "2.19.0" and row["build_id"] is None
    assert row["capabilities"] == {"automatic_round_delivery": None, "batch": False, "rounds": None, "decision_schema": 0}
    assert row["latest_delivery_state"] == "none"
    assert result["summary"]["capability_gaps"]["batch"] == {"unknown": 0, "unsupported": 1}
    assert result["summary"]["capability_gaps"]["decision_schema"] == {"unknown": 0, "unsupported": 1}


@pytest.mark.parametrize("error, code", [(TimeoutError("private timeout"), "timeout"),
    (URLError("private connection error"), "unreachable"), (ssl.SSLCertVerificationError("private TLS error"), "tls_error")])
def test_unreachable_pages_redact_errors_and_owner_remains_unknown(error, code):
    result = fleet.collect_fleet(_config(), fetch=lambda *args, **kwargs: (_ for _ in ()).throw(error))
    row = result["targets"][0]
    assert row["health"] == "unreachable"
    assert row["owner_present"] is None
    assert all(item["code"] == code for item in row["errors"])
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("body", [b"{", b"[]", b"null", b"\xff", b"[" * 1000 + b"]" * 1000])
def test_malformed_json_is_classified_without_payload(body):
    result = fleet.collect_fleet(_config(), fetch=lambda *args, **kwargs: (200, body))
    assert all(code == "malformed_json" for code in result["targets"][0]["endpoint_status"].values())
    assert result["summary"]["owner_present"]["unknown"] == 1


def test_sensitive_nested_fields_and_invalid_runtime_values_are_never_emitted():
    secret = "reviewer@example.com private-owner /private/path shell command"
    result = fleet.collect_fleet(_config(), fetch=_fetch({
        "current.meta.json": {"current": secret, "owner": {"owner_session": "private-owner", "target": secret},
                              "project_info": {"modules": [{"text": secret}]}, "history": [{"label": secret}]},
        "api/capabilities": {"version": secret, "runtime": {"package_version": secret, "build_id": secret, "assets": {secret: secret}},
                             "rounds": secret, "verdicts": [secret], "decision_schema": True},
        "api/delivery": {"latest": {"state": "uncertain", "detail": secret, "owner_target": secret, "receipt": {"text": secret}}},
    }))
    row = result["targets"][0]
    assert row["current_version"] is None and row["package_version"] is None and row["build_id"] is None
    assert row["capabilities"]["rounds"] is None and row["capabilities"]["decision_schema"] is None
    assert row["latest_delivery_state"] == "uncertain"
    assert secret not in json.dumps(result) and "private-owner" not in json.dumps(result)


@pytest.mark.parametrize("status, code", [(301, "redirect_refused"), (302, "redirect_refused"),
    (307, "redirect_refused"), (308, "redirect_refused"), (401, "http_error"), (500, "http_error")])
def test_http_failures_and_redirects_never_emit_response_bodies(status, code):
    result = fleet.collect_fleet(_config(), fetch=lambda *args, **kwargs: (status, b"private secret"))
    assert all(value == code for value in result["targets"][0]["endpoint_status"].values())
    assert "private secret" not in json.dumps(result)


def test_bounded_responses_are_enforced_even_for_injected_fetch():
    result = fleet.collect_fleet(_config(), max_response_bytes=8, fetch=lambda *args, **kwargs: (200, b"x" * 9))
    assert all(value == "too_large" for value in result["targets"][0]["endpoint_status"].values())


@pytest.mark.parametrize("options", [{"timeout": 0}, {"timeout": 16}, {"timeout": float("inf")},
    {"timeout": True}, {"max_response_bytes": 0}, {"max_response_bytes": 65537}, {"max_response_bytes": True}])
def test_request_bounds_are_checked_before_fetch(options):
    with pytest.raises(ValueError):
        fleet.collect_fleet(_config(), fetch=lambda *args, **kwargs: pytest.fail("unbounded fetch"), **options)


def test_empty_explicit_inventory_does_not_discover_or_fetch():
    result = fleet.collect_fleet({"schema_version": 1, "targets": []}, fetch=lambda *args, **kwargs: pytest.fail("discovery"))
    assert result["summary"]["total"] == 0
    assert result["targets"] == []


def test_inventory_labels_owner_presence_and_latest_states_have_explicit_limits():
    result = fleet.collect_fleet(_config(), fetch=_fetch(_responses()))
    text = " ".join(result["limitations"])
    assert "not attested host identity" in text
    assert "not a validated live owner" in text
    assert "not total feedback rounds" in text
    assert "coverage may be incomplete" in text
    assert "cannot make loopback address a remote host" in text


def test_machine_version_and_delivery_aggregates_preserve_unknown_observations():
    def fetch(url, **kwargs):
        if url.startswith("https://m5.test/"):
            raise TimeoutError("private remote error")
        return _fetch(_responses())(url, **kwargs)

    result = fleet.collect_fleet(_config(_target(), _target(machine="m5", url="https://m5.test/demo/")), fetch=fetch)
    summary = result["summary"]
    assert summary["by_machine"] == {"m5": 1, "mbp": 1}
    assert summary["by_version"] == {"2.21.0": 1, "unknown": 1}
    assert summary["owner_present"] == {"present": 1, "absent": 0, "unknown": 1}
    assert summary["delivery_states"]["uncertain"] == 1
    assert summary["delivery_states"]["unknown"] == 1
    assert summary["capability_gaps"]["automatic_round_delivery"] == {"unknown": 1, "unsupported": 0}


def test_default_fetch_refuses_redirects_uses_tls_verification_and_bounded_get(monkeypatch):
    captured = {}

    class Response(BytesIO):
        status = 200

        def geturl(self):
            return "https://example.test/demo/api/capabilities"

    class Opener:
        def open(self, request, timeout):
            captured["request"], captured["timeout"] = request, timeout
            return Response(b"{}")

    def opener(*handlers):
        captured["handlers"] = handlers
        return Opener()

    monkeypatch.setattr(fleet, "build_opener", opener)
    assert fleet._blocking_fetch("https://example.test/demo/api/capabilities", timeout=2, max_bytes=100) == (200, b"{}")
    tls = next(handler for handler in captured["handlers"] if isinstance(handler, fleet.HTTPSHandler))
    assert tls._context.verify_mode == ssl.CERT_REQUIRED and tls._context.check_hostname is True
    redirect = next(handler for handler in captured["handlers"] if isinstance(handler, fleet._NoRedirect))
    assert redirect.redirect_request(None, None, 302, "private", {}, "https://unconfigured.test/") is None
    assert next(handler for handler in captured["handlers"] if isinstance(handler, fleet.ProxyHandler)).proxies == {}
    assert captured["request"].get_method() == "GET" and captured["timeout"] == 2
    assert "Authorization" not in captured["request"].headers


def test_default_fetch_does_not_read_redirect_body_or_destination(monkeypatch):
    class Opener:
        def open(self, request, timeout):
            raise HTTPError(request.full_url, 302, "private body", {"Location": "https://unconfigured.test/"}, None)

    monkeypatch.setattr(fleet, "build_opener", lambda *args: Opener())
    assert fleet._blocking_fetch("https://example.test/demo/api/delivery", timeout=2, max_bytes=100) == (302, b"")


def test_default_fetch_enforces_response_byte_limit(monkeypatch):
    class Response(BytesIO):
        status = 200

        def geturl(self):
            return "https://example.test/demo/api/delivery"

    class Opener:
        def open(self, request, timeout):
            return Response(b"x" * 10)

    monkeypatch.setattr(fleet, "build_opener", lambda *args: Opener())
    with pytest.raises(fleet.FleetFetchError, match="too_large"):
        fleet._blocking_fetch("https://example.test/demo/api/delivery", timeout=2, max_bytes=4)


@pytest.mark.parametrize("script", [
    "import time; time.sleep(60)",
    "import socket,time\na,b=socket.socketpair()\na.settimeout(.1)\nb.settimeout(.1)\n"
    "while True:\n a.sendall(b'x'); b.recv(1); time.sleep(.025)",
])
def test_public_fetch_total_deadline_kills_and_reaps_worker_even_with_continuous_progress(monkeypatch, script):
    original_run, original_popen = subprocess.run, subprocess.Popen
    children = []

    def record_popen(*args, **kwargs):
        child = original_popen(*args, **kwargs)
        children.append(child)
        return child

    def inert_run(command, **kwargs):
        assert command == [sys.executable, "-I", "-B", fleet.__file__, "--fetch-worker"]
        assert kwargs["shell"] is False and kwargs["stderr"] == subprocess.DEVNULL
        return original_run([sys.executable, "-I", "-B", "-c", script], **kwargs)

    monkeypatch.setattr(fleet.subprocess, "Popen", record_popen)
    monkeypatch.setattr(fleet.subprocess, "run", inert_run)
    started = time.monotonic()
    with pytest.raises(fleet.FleetFetchError, match="^timeout$"):
        fleet.fetch_json("https://example.test/demo/api/delivery", timeout=0.3, max_bytes=100)
    assert time.monotonic() - started < 2
    assert len(children) == 1 and children[0].returncode is not None
    with pytest.raises(ChildProcessError):
        os.waitpid(children[0].pid, os.WNOHANG)


@pytest.mark.parametrize("error", [IncompleteRead(b"private response body", 100),
    BadStatusLine("private response header"), RemoteDisconnected("private connection error")])
@pytest.mark.parametrize("stage", ["headers", "body"])
def test_blocking_http_protocol_errors_are_safe_codes(monkeypatch, error, stage):
    class Response(BytesIO):
        status = 200

        def geturl(self):
            return "https://example.test/demo/api/delivery"

        def read(self, maximum):
            raise error

    class Opener:
        def open(self, request, timeout):
            if stage == "headers":
                raise error
            return Response()

    monkeypatch.setattr(fleet, "build_opener", lambda *args: Opener())
    with pytest.raises(fleet.FleetFetchError, match="^http_error$") as caught:
        fleet._blocking_fetch("https://example.test/demo/api/delivery", timeout=2, max_bytes=100)
    assert "private" not in str(caught.value) and caught.value.__suppress_context__


@pytest.mark.parametrize("error", [IncompleteRead(b"private response body", 100), BadStatusLine("private header")])
def test_injected_http_protocol_errors_do_not_abort_collection_or_leak(error):
    result = fleet.collect_fleet(_config(), fetch=lambda *args, **kwargs: (_ for _ in ()).throw(error))
    assert result["summary"]["total"] == 1
    assert all(code == "http_error" for code in result["targets"][0]["endpoint_status"].values())
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("stdout, returncode, expected", [
    (b"error\nhttp_error\n", 0, "http_error"),
    (b"private stdout payload", 0, "http_error"),
    (b"private stdout payload", 1, "unreachable"),
])
def test_public_fetch_discards_raw_worker_output_and_stderr(monkeypatch, stdout, returncode, expected):
    def run(command, **kwargs):
        assert kwargs["stdout"] == subprocess.PIPE and kwargs["stderr"] == subprocess.DEVNULL
        return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr=b"private stderr payload")

    monkeypatch.setattr(fleet.subprocess, "run", run)
    with pytest.raises(fleet.FleetFetchError, match=f"^{expected}$") as caught:
        fleet.fetch_json("https://example.test/demo/api/delivery", timeout=2, max_bytes=100)
    assert "private" not in str(caught.value)


def test_public_fetch_decodes_private_bounded_worker_protocol(monkeypatch):
    def run(command, **kwargs):
        assert json.loads(kwargs["input"]) == {
            "url": "https://example.test/demo/api/delivery", "timeout": 2, "max_bytes": 100,
        }
        return subprocess.CompletedProcess(command, 0, stdout=b"ok\n200\n{\"latest\":null}")

    monkeypatch.setattr(fleet.subprocess, "run", run)
    assert fleet.fetch_json("https://example.test/demo/api/delivery", timeout=2, max_bytes=100) == (200, b'{"latest":null}')


def test_real_isolated_worker_returns_safe_failure_without_network_protocol():
    # An unsupported inert scheme exercises the actual worker entry point and
    # private pipe protocol without contacting any server or provider.
    with pytest.raises(fleet.FleetFetchError, match="^unreachable$"):
        fleet.fetch_json("fleet-inert://not-a-network-host/", timeout=2, max_bytes=100)
