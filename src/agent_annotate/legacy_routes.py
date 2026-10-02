"""Remove only corroborated routes retained by a page's transport migration."""

from urllib.parse import urlsplit

from . import transports


def _receipt(result):
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise RuntimeError("transport teardown failed")
    details = result.get("details")
    if not isinstance(details, dict):
        raise RuntimeError("transport teardown receipt is missing")
    action, reason = details.get("action"), details.get("reason", "")
    if action != "removed" and not (action == "noop" and isinstance(reason, str)
            and (reason == "no matching rule" or reason.startswith("no serve mapping"))):
        raise RuntimeError("transport teardown ownership was not proven")
    return details


def _mount(route, record, details):
    paths = []
    ts = details.get("tailscale") or details
    hosts = set()
    if route.get("transport") in {"cloudflare", "cloudflare_tailscale"} and details.get("hostname"):
        hosts.add((details["hostname"].lower(), 443))
    if route.get("transport") in {"tailscale", "cloudflare_tailscale", "funnel"} and ts.get("hostname") and ts.get("https_port"):
        hosts.add((ts["hostname"].lower(), int(ts["https_port"])))
    for value in (route.get("public_base_path"), details.get("path")):
        if value:
            paths.append(value.removesuffix("/.*").rstrip("/") or "/")
    slug = ts.get("slug")
    if slug is not None:
        paths.append("/" + slug.strip("/"))
    for field in ("url", "public_url"):
        value = route.get(field)
        if not value:
            continue
        parsed = urlsplit(value)
        if parsed.scheme != "https" or (parsed.hostname, parsed.port or 443) not in hosts:
            raise RuntimeError("recorded URL and route hostname/port disagree")
        path = parsed.path.rstrip("/")
        if path:
            paths.append(path)
    if len(set(paths)) > 1:
        raise RuntimeError("recorded route mounts disagree")
    path = paths[0] if paths else (record.get("public_base_path") or "/")
    if (not isinstance(path, str) or not path.startswith("/") or any(char.isspace() or char in "\\?#" for char in path)
            or (path != "/" and any(part in ("", ".", "..") for part in path[1:].split("/")))):
        raise RuntimeError("recorded route mount is invalid")
    return path


def _tailscale(mount, details, local_port, config):
    host, https_port = details.get("hostname"), details.get("https_port")
    if not host or not https_port:
        raise RuntimeError("recorded Tailscale hostname and HTTPS port are required")
    opts = {**config, "hostname": host, "https_port": int(https_port), "port": local_port}
    module = transports.load("tailscale")
    current = module.status(**opts)
    if current.get("hostname") != host or not isinstance(current.get("mappings"), dict):
        raise RuntimeError("live Tailscale hostname/route table differs from the receipt")
    target = current["mappings"].get(int(https_port))
    if target is None:
        return {"action": "noop", "reason": f"no serve mapping on :{https_port}"}
    origins = {f"http://127.0.0.1:{local_port}", f"http://localhost:{local_port}", f"http://[::1]:{local_port}"}
    if not isinstance(target, str) or target.rstrip("/") not in origins:
        raise RuntimeError("legacy Tailscale port now belongs to another origin")
    result = _receipt(module.unpublish(mount.lstrip("/"), **opts))
    after = module.status(**opts)
    if (after.get("hostname") != host or not isinstance(after.get("mappings"), dict)
            or int(https_port) in after["mappings"]):
        raise RuntimeError("legacy Tailscale route removal was not verified")
    return result


def _cloudflare(mount, details, config):
    host, tunnel = details.get("hostname"), details.get("tunnel_id")
    service = details.get("service") or details.get("origin_service")
    if mount == "/" or not host or not tunnel or not service:
        raise RuntimeError("recorded Cloudflare mount, hostname, tunnel and origin service are required")
    if details.get("service") and details.get("origin_service") and details["service"] != details["origin_service"]:
        raise RuntimeError("recorded Cloudflare origin services disagree")
    opts = {**config, "hostname": host, "tunnel_id": tunnel}
    module = transports.load("cloudflare")
    slug = mount.lstrip("/")
    current = module.status(slug, **opts)  # Auth/config must resolve even when the rule is absent.
    matches = current.get("matches")
    if current.get("hostname") != host or not isinstance(matches, list):
        raise RuntimeError("Cloudflare route lookup was not corroborated")
    expected_path = mount + "/.*"
    if any(not isinstance(rule, dict) or rule.get("hostname") != host
           or rule.get("path") != expected_path or rule.get("service") != service for rule in matches):
        raise RuntimeError("legacy Cloudflare path now belongs to another origin")
    if not matches:
        return {"action": "noop", "reason": "no matching rule"}
    result = _receipt(module.unpublish(slug, expected_service=service, **opts))
    after = module.status(slug, **opts)
    if after.get("hostname") != host or after.get("matches") != []:
        raise RuntimeError("legacy Cloudflare rule removal was not verified")
    return result


def cleanup(record: dict, project_config: dict) -> list[dict]:
    """Caller holds the tunnel lock and retains page registration on failure."""
    routes = record.get("legacy_routes", [])
    if not isinstance(routes, list):
        raise RuntimeError("legacy route receipts must be a list; keep this page registered")
    outcomes = []
    for route in routes:
        name = route.get("transport") if isinstance(route, dict) else "unknown"
        if name == "local":
            continue
        try:
            if name not in {"tailscale", "cloudflare", "cloudflare_tailscale", "funnel"}:
                raise RuntimeError("unknown legacy transport")
            details = route.get("transport_details") or {}
            ts = details.get("tailscale") or details
            ports = {int(value) for value in (route.get("port"), ts.get("local_port"), details.get("port")) if value}
            if len(ports) > 1:
                raise RuntimeError("recorded local ports disagree")
            local_port = next(iter(ports), int(record.get("port") or 0))
            if not 0 < local_port < 65536:
                raise RuntimeError("recorded local port is required")
            mount = _mount(route, record, details)
            if name == "cloudflare_tailscale" and details.get("public") is False and any(
                    details.get(key) for key in ("service", "origin_service", "public_url", "tunnel_id")):
                raise RuntimeError("recorded Cloudflare public flag disagrees with its route receipt")
            if name == "funnel":
                if transports.load("tailscale").status(**project_config).get("hostname") != details.get("hostname"):
                    raise RuntimeError("live Funnel hostname differs from the receipt")
                opts = {**project_config, **{key: details.get(key) for key in ("hostname", "https_port", "path")}, "port": local_port}
                outcomes.append({"transport": name, **_receipt(transports.load(name).unpublish(mount.lstrip("/"), **opts))})
                continue
            if name in {"cloudflare", "cloudflare_tailscale"} and not (
                    name == "cloudflare_tailscale" and details.get("public") is False):
                outcomes.append({"transport": "cloudflare", **_cloudflare(mount, details, project_config)})
            if name in {"tailscale", "cloudflare_tailscale"}:
                outcomes.append({"transport": "tailscale", **_tailscale(mount, ts, local_port, project_config)})
        except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError) as exc:
            raise RuntimeError(f"Legacy {name} route cleanup refused: {exc}. Restore recorded credentials/ownership and retry; keep the page registered.") from exc
    return outcomes
