"""Bounded, read-only runtime coverage for explicitly configured page URLs."""

from __future__ import annotations

import ipaddress
import json
import math
import re
import ssl
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPException
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

MAX_TARGETS = 64
MAX_RESPONSE_BYTES = 64 * 1024
_NAME = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,127}\Z")
_VERSION = re.compile(r"[0-9]+(?:\.[0-9]+){1,3}(?:[A-Za-z][A-Za-z0-9.+-]*)?\Z")
_BUILD = re.compile(r"(?:assets:)?[a-fA-F0-9]{7,64}\Z")
_CAPABILITIES = ("automatic_round_delivery", "batch", "rounds")
_DELIVERY_STATES = (
    "pending", "attempting", "accepted", "started", "uncertain", "superseded", "acknowledged", "none", "unknown",
)
_ERROR_CODES = {
    "missing", "redirect_refused", "timeout", "unreachable", "tls_error", "too_large", "malformed_json", "http_error",
}
_LIMITATIONS = (
    "Configured targets only; remote canonical page coverage may be incomplete and is not discovered automatically.",
    "Configured machine labels are inventory labels, not attested host identity.",
    "Owner presence reports metadata, not a validated live owner or agent session.",
    "Delivery state counts are latest observed rows per target, not total feedback rounds.",
    "Endpoint health does not verify rendered UI or feature conformity; capability gaps are reported separately.",
    "Loopback HTTP refers to the collector's machine; a machine label cannot make loopback address a remote host.",
)
Fetch = Callable[..., tuple[int, bytes]]


class FleetFetchError(Exception):
    """Transport error containing only a bounded public status code."""

    def __init__(self, code: str):
        self.code = code if code in _ERROR_CODES else "unreachable"
        super().__init__(self.code)


def _base_url(value: object) -> str:
    if (not isinstance(value, str) or not value or len(value) > 2048
            or any(char.isspace() or ord(char) < 32 or 127 <= ord(char) <= 159 for char in value)
            or any(char in value for char in ("\\", "?", "#"))):
        raise ValueError("target url must be a base HTTP or HTTPS URL without credentials, query, or fragment")
    try:
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username is not None or parts.password is not None:
            raise ValueError
        host = parts.hostname.rstrip(".").lower()
        port = parts.port
        if port is not None and not 0 < port < 65536:
            raise ValueError
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
            host = host.encode("idna").decode("ascii")
            if len(host) > 253 or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                                          for label in host.split(".")):
                raise ValueError
        if parts.scheme == "http" and host != "localhost" and not (address and address.is_loopback):
            raise ValueError
        if address is not None:
            if "%" in host:
                raise ValueError
            host = f"[{address.compressed}]" if address.version == 6 else address.compressed
        decoded_path = unquote(parts.path, errors="strict")
        if ("\\" in decoded_path or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in decoded_path)
                or any(segment in (".", "..") for segment in decoded_path.split("/"))
                or re.search(r"%(?![a-fA-F0-9]{2})", parts.path)):
            raise ValueError
        authority = host if port is None or port == (443 if parts.scheme == "https" else 80) else f"{host}:{port}"
        return urlunsplit((parts.scheme, authority, parts.path.rstrip("/") + "/", "", ""))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("target url requires HTTPS or loopback HTTP with a valid host and base path") from exc


def validate_config(data: object) -> dict:
    """Copy strict configuration; duplicate identities or canonical URLs fail closed."""
    if (not isinstance(data, dict) or set(data) != {"schema_version", "targets"}
            or type(data["schema_version"]) is not int or data["schema_version"] != 1
            or not isinstance(data["targets"], list) or len(data["targets"]) > MAX_TARGETS):
        raise ValueError("fleet config requires schema_version 1 and at most 64 targets")
    targets, identities, urls = [], set(), set()
    for target in data["targets"]:
        if not isinstance(target, dict) or set(target) != {"machine", "project", "slug", "url"}:
            raise ValueError("fleet targets require only machine, project, slug, and url")
        normalized = {}
        for field in ("machine", "project", "slug"):
            value = target[field]
            if not isinstance(value, str) or not _NAME.fullmatch(value):
                raise ValueError("fleet target identifiers must be safe names of at most 128 characters")
            normalized[field] = value
        normalized["url"] = _base_url(target["url"])
        identity = tuple(normalized[field] for field in ("machine", "project", "slug"))
        if identity in identities or normalized["url"] in urls:
            raise ValueError("fleet target identities and URLs must be unique")
        identities.add(identity)
        urls.add(normalized["url"])
        targets.append(normalized)
    return {"schema_version": 1, "targets": targets}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def _blocking_fetch(url: str, *, timeout: float, max_bytes: int) -> tuple[int, bytes]:
    """Blocking urllib work; public fetch_json supervises its total lifetime."""
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), _NoRedirect())
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "agent-annotate-fleet"}, method="GET")
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.geturl() != url:
                raise FleetFetchError("redirect_refused")
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise FleetFetchError("too_large")
            return response.status, body
    except HTTPError as exc:
        status = exc.code
        exc.close()
        return status, b""  # Error bodies and redirect destinations are never retained.
    except HTTPException:
        raise FleetFetchError("http_error") from None
    except (TimeoutError, ssl.SSLError, URLError, OSError) as exc:
        reason = exc.reason if isinstance(exc, URLError) else exc
        code = "timeout" if isinstance(reason, TimeoutError) else "tls_error" if isinstance(reason, ssl.SSLError) else "unreachable"
        raise FleetFetchError(code) from None


def _request_limits(timeout: float, maximum: int) -> None:
    if (type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 15
            or type(maximum) is not int or not 0 < maximum <= MAX_RESPONSE_BYTES):
        raise ValueError("fleet requests require timeout in (0, 15] and response bounds in [1, 65536]")


def fetch_json(url: str, *, timeout: float, max_bytes: int) -> tuple[int, bytes]:
    """Bound the entire TLS/open/headers/body operation, killing and reaping on timeout."""
    _request_limits(timeout, max_bytes)
    payload = json.dumps({"url": url, "timeout": timeout, "max_bytes": max_bytes}, ensure_ascii=False).encode()
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-B", __file__, "--fetch-worker"], input=payload,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, shell=False, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        # run() kills and waits for this worker before raising; no stranded
        # network thread can outlive the deadline or block the fleet executor.
        raise FleetFetchError("timeout") from None
    except OSError:
        raise FleetFetchError("unreachable") from None
    if result.returncode:
        raise FleetFetchError("unreachable")
    if len(result.stdout) > max_bytes + 64:
        raise FleetFetchError("too_large")
    try:
        kind, value, body = result.stdout.split(b"\n", 2)
        if kind == b"error":
            raise FleetFetchError(value.decode("ascii"))
        status = int(value)
        if kind != b"ok" or not 100 <= status <= 599:
            raise ValueError
    except (ValueError, UnicodeError):
        raise FleetFetchError("http_error") from None
    if len(body) > max_bytes:
        raise FleetFetchError("too_large")
    return status, body


def _fetch_worker() -> None:
    """Private bounded pipe protocol; only the parent captures raw response bytes."""
    try:
        payload = json.loads(sys.stdin.buffer.read(16385))
        _request_limits(payload["timeout"], payload["max_bytes"])
        status, body = _blocking_fetch(**payload)
        output = b"ok\n" + str(status).encode("ascii") + b"\n" + body
    except FleetFetchError as exc:
        output = b"error\n" + exc.code.encode("ascii") + b"\n"
    except (ValueError, TypeError, KeyError, RecursionError):
        output = b"error\nhttp_error\n"
    sys.stdout.buffer.write(output)


def _endpoint(fetch: Fetch, url: str, timeout: float, maximum: int) -> tuple[dict | None, str]:
    try:
        status, body = fetch(url, timeout=timeout, max_bytes=maximum)
        if type(status) is not int:
            return None, "http_error"
        if 300 <= status < 400:
            return None, "redirect_refused"
        if status == 404:
            return None, "missing"
        if status != 200:
            return None, "http_error"
        if not isinstance(body, bytes):
            return None, "malformed_json"
        if len(body) > maximum:
            return None, "too_large"
        data = json.loads(body)
        return (data, "ok") if isinstance(data, dict) else (None, "malformed_json")
    except FleetFetchError as exc:
        return None, exc.code
    except TimeoutError:
        return None, "timeout"
    except ssl.SSLError:
        return None, "tls_error"
    except HTTPException:
        return None, "http_error"
    except (URLError, OSError):
        return None, "unreachable"
    except (ValueError, TypeError, RecursionError):
        return None, "malformed_json"


def _safe_value(value: object, pattern: re.Pattern, maximum: int = 80) -> str | None:
    return value if isinstance(value, str) and len(value) <= maximum and pattern.fullmatch(value) else None


def _collect_target(target: dict, fetch: Fetch, timeout: float, maximum: int) -> dict:
    documents, statuses = {}, {}
    for endpoint, path in (("meta", "current.meta.json"), ("capabilities", "api/capabilities"), ("delivery", "api/delivery")):
        documents[endpoint], statuses[endpoint] = _endpoint(fetch, target["url"] + path, timeout, maximum)
    meta, caps, delivery = documents["meta"], documents["capabilities"], documents["delivery"]
    owner_present = None
    if meta is not None:
        owner = meta.get("owner")
        if owner is None:
            owner_present = False
        elif isinstance(owner, dict):
            session = owner.get("owner_session")
            owner_present = isinstance(session, str) and bool(session) and session != "unknown"
    runtime = caps.get("runtime") if caps is not None else None
    runtime = runtime if isinstance(runtime, dict) else {}
    package = _safe_value(runtime.get("package_version"), _VERSION)
    if package is None and caps is not None:
        package = _safe_value(caps.get("version"), _VERSION)
    latest_state = "unknown"
    if delivery is not None and "latest" in delivery:
        latest = delivery["latest"]
        if latest is None:
            latest_state = "none"
        elif isinstance(latest, dict) and isinstance(latest.get("state"), str) and latest["state"] in _DELIVERY_STATES:
            latest_state = latest["state"]
    capabilities = {field: caps.get(field) if caps is not None and type(caps.get(field)) is bool else None
                    for field in _CAPABILITIES}
    schema = caps.get("decision_schema") if caps is not None else None
    capabilities["decision_schema"] = schema if type(schema) is int and 0 <= schema <= 100 else None
    health = "healthy" if all(status == "ok" for status in statuses.values()) else "degraded"
    if all(status in ("unreachable", "timeout", "tls_error") for status in statuses.values()):
        health = "unreachable"
    return {
        **target,
        "current_version": _safe_value(meta.get("current"), re.compile(r"v[0-9]{1,10}\Z")) if meta else None,
        "package_version": package,
        "build_id": _safe_value(runtime.get("build_id"), _BUILD),
        "owner_present": owner_present,
        "latest_delivery_state": latest_state,
        "capabilities": capabilities,
        "health": health,
        "endpoint_status": statuses,
        "errors": [{"endpoint": endpoint, "code": status} for endpoint, status in statuses.items() if status != "ok"],
    }


def collect_fleet(config: object, *, fetch: Fetch | None = None, timeout: float = 3.0,
                  max_response_bytes: int = MAX_RESPONSE_BYTES) -> dict:
    """Collect configured targets only; injectable fetch returns (HTTP status, bytes).

    Null capabilities mean unknown, false means explicitly unsupported. No
    delivery means a successfully read ``latest: null``; unknown means no valid
    delivery observation. A configured owner is not proof that its agent is live.
    """
    validated = validate_config(config)
    _request_limits(timeout, max_response_bytes)
    with ThreadPoolExecutor(max_workers=4) as workers:
        rows = list(workers.map(lambda target: _collect_target(target, fetch or fetch_json, timeout, max_response_bytes),
                                validated["targets"]))
    gaps = {field: {"unknown": 0, "unsupported": 0} for field in (*_CAPABILITIES, "decision_schema")}
    gaps.update({"package_version": {"unknown": 0}, "build_id": {"unknown": 0}})
    for row in rows:
        for field in _CAPABILITIES:
            value = row["capabilities"][field]
            gaps[field]["unknown"] += value is None
            gaps[field]["unsupported"] += value is False
        schema = row["capabilities"]["decision_schema"]
        gaps["decision_schema"]["unknown"] += schema is None
        gaps["decision_schema"]["unsupported"] += schema is not None and schema < 2
        for field in ("package_version", "build_id"):
            gaps[field]["unknown"] += row[field] is None
    health = Counter(row["health"] for row in rows)
    return {
        "schema_version": 1,
        "targets": rows,
        "summary": {
            "total": len(rows),
            **{state: health[state] for state in ("healthy", "degraded", "unreachable")},
            "by_machine": dict(sorted(Counter(row["machine"] for row in rows).items())),
            "by_version": dict(sorted(Counter(row["package_version"] or "unknown" for row in rows).items())),
            "owner_present": {"present": sum(row["owner_present"] is True for row in rows),
                              "absent": sum(row["owner_present"] is False for row in rows),
                              "unknown": sum(row["owner_present"] is None for row in rows)},
            "delivery_states": {state: sum(row["latest_delivery_state"] == state for row in rows) for state in _DELIVERY_STATES},
            "capability_gaps": gaps,
        },
        "limitations": list(_LIMITATIONS),
    }


if __name__ == "__main__" and sys.argv[1:] == ["--fetch-worker"]:
    _fetch_worker()
