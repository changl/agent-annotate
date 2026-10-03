"""One exact path on an already-public or unused Tailscale Funnel port."""

from agent_annotate.transports import tailscale as ts


def _handlers(state, host, port):
    return (state.get("Web", {}).get(f"{host}:{port}") or {}).get("Handlers", {})


def _remove_route(binary, host, port, path, target):
    state = ts._serve_state(binary)
    handlers = _handlers(state, host, port)
    handler = handlers.get(path)
    if handler is None:
        return {"action": "noop", "reason": f"no serve mapping for {path} on :{port}"}
    if handler.get("Proxy", "").rstrip("/") != target:
        raise RuntimeError("Funnel path now belongs to another origin; no route changed")
    result = ts._run([binary, "serve", f"--https={port}", f"--set-path={path}", "off"])
    after_state = ts._serve_state(binary)
    after = _handlers(after_state, host, port)
    if result.returncode or path in after:
        raise RuntimeError("Funnel path removal was not verified")
    if any(after.get(other) != value for other, value in handlers.items() if other != path):
        raise RuntimeError("An unrelated Funnel handler changed")
    if after and state.get("AllowFunnel", {}).get(f"{host}:{port}") != after_state.get("AllowFunnel", {}).get(f"{host}:{port}"):
        raise RuntimeError("Remaining Funnel routes changed public visibility")
    return {"action": "removed", "path": path}


def publish(slug: str, port: int, **opts) -> dict:
    path = "/" + slug.strip("/")
    if path == "/" or any(p in ("", ".", "..") for p in path[1:].split("/")):
        raise ValueError("Funnel requires an exact non-root page path")
    binary = ts._binary(opts)
    with ts._Lock():
        state = ts._serve_state(binary)
        host = ts._hostname(state, binary)
        previous = opts.get("previous") or {}
        old_port = previous.get("port")
        old_details = previous.get("details") or {}
        old_https = old_details.get("https_port") if old_details.get("transport") == "funnel" else None
        old_path = old_details.get("path") or path
        old_target = ts._origin(old_port) + old_path if old_port and old_https else None
        old_owned = False
        if old_target:
            old_host = old_details.get("hostname") or host
            old_handler = _handlers(state, old_host, int(old_https)).get(old_path)
            if old_handler:
                if old_host != host or old_handler.get("Proxy", "").rstrip("/") != old_target:
                    raise RuntimeError("Previous Funnel path ownership changed; no route changed")
                if state.get("AllowFunnel", {}).get(f"{host}:{old_https}") is not True:
                    raise RuntimeError("Previous Funnel port is private; refusing to expose other services")
                old_owned = True
        candidates = ([int(opts["funnel_port"])] if opts.get("funnel_port") else
                      ([int(old_https)] if old_owned else []) + [443, 10000, 8443])
        https_port = next((p for p in candidates if p in (443, 8443, 10000) and (
            state.get("AllowFunnel", {}).get(f"{host}:{p}") is True or p not in ts._claimed_ports(state))), None)
        if https_port is None:
            raise RuntimeError("No public/unused Funnel port; refusing to expose existing private services")
        # --set-path strips the prefix; the proxy target restores it for the
        # server's existing mount/Host/origin boundary.
        target = ts._origin(port) + path
        existing = _handlers(state, host, https_port).get(path)
        allowed = {target}
        if old_owned and int(old_https) == https_port and old_path == path:
            allowed.add(old_target)
        if existing and existing.get("Proxy", "").rstrip("/") not in allowed:
            raise RuntimeError("Funnel path belongs to another origin; no route changed")
        if not existing or existing.get("Proxy", "").rstrip("/") != target:
            result = ts._run([binary, "funnel", "--bg", "--yes", f"--https={https_port}", f"--set-path={path}", target])
            if result.returncode:
                raise RuntimeError((result.stderr or result.stdout).strip())
        after = ts._serve_state(binary)
        if (_handlers(after, host, https_port).get(path, {}).get("Proxy", "").rstrip("/") != target
                or after.get("AllowFunnel", {}).get(f"{host}:{https_port}") is not True):
            raise RuntimeError("Funnel path/public access did not register")
        for other_path, handler in _handlers(state, host, https_port).items():
            if other_path != path and _handlers(after, host, https_port).get(other_path) != handler:
                raise RuntimeError("An unrelated Funnel handler changed")
        if old_owned and (int(old_https), old_path) != (https_port, path):
            _remove_route(binary, host, int(old_https), old_path, old_target)
    suffix = "" if https_port == 443 else f":{https_port}"
    url = f"https://{host}{suffix}{path}/"
    return {"url": url, "details": {"transport": "funnel", "hostname": host,
            "https_port": https_port, "local_port": int(port), "path": path,
            "origin": target, "public_url": url}}


def unpublish(slug: str, **opts) -> dict:
    binary = ts._binary(opts)
    path = opts.get("path") or "/" + slug.strip("/")
    port = opts.get("https_port")
    local_port = opts.get("port") or opts.get("local_port")
    if not port or not local_port or path == "/":
        raise RuntimeError("Funnel teardown requires its exact path and both ports")
    with ts._Lock():
        state = ts._serve_state(binary)
        host = ts._hostname(state, binary)
        if opts.get("hostname") and opts["hostname"] != host:
            raise RuntimeError("Funnel hostname changed; no route changed")
        details = _remove_route(binary, host, int(port), path, ts._origin(local_port) + path)
    return {"ok": True, "details": details}
