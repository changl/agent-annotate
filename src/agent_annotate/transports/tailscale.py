"""tailscale transport — front a local sync_server port with a tailnet HTTPS endpoint.

    tailscale serve --bg --https=<serve_port> http://127.0.0.1:<local_port>

The whole port is proxied at `/`, never `--set-path`. The Cloudflare tunnel in
front of this does not strip the slug prefix from the request path, so the path
that arrives here has to reach the sync server intact for its
`--public-base-path` handling to strip it. A `--set-path` mapping would rewrite
that path and break the mount.

Idempotency keys off the ORIGIN (`http://127.0.0.1:<local_port>`), not the slug:
tailscale's serve table has no concept of a slug, and re-publishing a slug that
kept its port must reuse the mapping rather than burn a second serve port.

Every mutation is followed by a re-read of `tailscale serve status --json` —
the exit code alone is not evidence that the mapping landed.
"""

import json
import os
import subprocess

from agent_annotate.paths import STATE_DIR

# 443 is the Funnel port and is deliberately outside this range: allocating it
# would silently take over the machine's public Funnel endpoint.
DEFAULT_PORT_RANGE = (8443, 8500)
_LOCK_NAME = "tailscale-serve.lock"


class _Lock:
    """Advisory lock around allocate-then-create.

    Two concurrent publishes both read the serve table, both see the same
    lowest free port, and the second `tailscale serve` overwrites the first —
    two slugs pointing at one origin. The transport owns the serve table, so
    the lock belongs here rather than in whichever caller happens to be
    careful.
    """

    def __init__(self) -> None:
        self._fh = None

    def __enter__(self):
        import fcntl

        lock_dir = STATE_DIR / "locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        self._fh = open(lock_dir / _LOCK_NAME, "a+")
        fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        import fcntl

        if self._fh is not None:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None
        return False


def _binary(opts: dict) -> str:
    return opts.get("binary") or os.environ.get("ANNOTATE_TAILSCALE_BIN") or "tailscale"


def _run(argv: list[str], timeout: int = 45) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as e:
        raise RuntimeError(
            f"tailscale binary not found: {argv[0]!r} — install Tailscale or set "
            "ANNOTATE_TAILSCALE_BIN"
        ) from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"`{' '.join(argv)}` timed out after {timeout}s") from e


def _serve_state(binary: str) -> dict:
    """Parsed `tailscale serve status --json`.

    An empty serve table prints `{}` on some versions and nothing at all on
    others; both mean "no mappings", not "failure".
    """
    proc = _run([binary, "serve", "status", "--json"])
    if proc.returncode != 0:
        raise RuntimeError(
            f"`tailscale serve status --json` failed (exit {proc.returncode}): "
            f"{(proc.stderr or proc.stdout).strip()}"
        )
    raw = (proc.stdout or "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"could not parse `tailscale serve status --json`: {e}") from e


def _origin(local_port: int) -> str:
    return f"http://127.0.0.1:{int(local_port)}"


def _equivalent_origins(local_port: int) -> set[str]:
    """Forms tailscale may have stored for the same origin."""
    p = int(local_port)
    return {f"http://127.0.0.1:{p}", f"http://localhost:{p}", f"http://[::1]:{p}"}


def _mappings(state: dict) -> dict[int, str]:
    """serve_port -> proxy target, for root-path handlers only."""
    out: dict[int, str] = {}
    for key, entry in (state.get("Web") or {}).items():
        _, _, port_str = str(key).rpartition(":")
        try:
            serve_port = int(port_str)
        except ValueError:
            continue
        handler = (entry.get("Handlers") or {}).get("/") or {}
        proxy = handler.get("Proxy")
        if proxy:
            out[serve_port] = proxy
    return out


def _claimed_ports(state: dict) -> set[int]:
    """Every port the serve table has any opinion about.

    A port can appear in TCP without a Web handler (raw TCP forward); reusing
    it would fail or, worse, silently shadow the existing forward.
    """
    ports = set(_mappings(state))
    for port_str in (state.get("TCP") or {}):
        try:
            ports.add(int(port_str))
        except (TypeError, ValueError):
            continue
    return ports


def _hostname(state: dict, binary: str) -> str:
    for key in (state.get("Web") or {}):
        host, _, _ = str(key).rpartition(":")
        if host:
            return host
    proc = _run([binary, "status", "--json"])
    if proc.returncode == 0 and (proc.stdout or "").strip():
        try:
            name = (json.loads(proc.stdout).get("Self") or {}).get("DNSName") or ""
        except json.JSONDecodeError:
            name = ""
        if name:
            return name.rstrip(".")
    raise RuntimeError(
        "could not determine this machine's tailnet DNS name — is tailscaled running "
        "and MagicDNS enabled?"
    )


def _port_range(opts: dict) -> tuple[int, int]:
    lo = int(opts.get("port_range_start") or DEFAULT_PORT_RANGE[0])
    hi = int(opts.get("port_range_end") or DEFAULT_PORT_RANGE[1])
    if hi <= lo:
        raise ValueError(f"invalid serve port range [{lo}, {hi})")
    return lo, hi


def _allocate(state: dict, opts: dict) -> int:
    lo, hi = _port_range(opts)
    claimed = _claimed_ports(state)
    for candidate in range(lo, hi):
        if candidate not in claimed:
            return candidate
    raise RuntimeError(
        f"no free tailscale serve port in [{lo}, {hi}) — {len(claimed)} in use; "
        "run `annotate unpublish` on finished slugs or widen port_range_end"
    )


def _find_existing(state: dict, local_port: int) -> int | None:
    wanted = _equivalent_origins(local_port)
    for serve_port, proxy in sorted(_mappings(state).items()):
        if proxy.rstrip("/") in wanted:
            return serve_port
    return None


def _previous(opts: dict) -> tuple[int | None, int | None]:
    """(serve_port, local_port) recorded by an earlier publish of this slug.

    The caller passes `previous={"port": ..., "details": {...}}`; transports
    that key their route on something stable (Cloudflare keys on the slug path
    and replaces in place) ignore it.
    """
    prev = opts.get("previous") or {}
    details = prev.get("details") or {}
    serve_port = details.get("https_port") or (details.get("tailscale") or {}).get("https_port")
    try:
        return (int(serve_port) if serve_port else None,
                int(prev["port"]) if prev.get("port") else None)
    except (TypeError, ValueError):
        return None, None


def _remove_mapping(binary: str, serve_port: int, local_port: int | None) -> bool:
    """Turn off one serve port. Caller must already hold the lock.

    Refuses when the port has been recycled onto a different origin: the
    recorded serve port is only evidence of what WAS there.
    """
    mappings = _mappings(_serve_state(binary))
    if serve_port not in mappings:
        return False
    if local_port is not None and \
            mappings[serve_port].rstrip("/") not in _equivalent_origins(local_port):
        return False
    proc = _run([binary, "serve", f"--https={serve_port}", "off"])
    if proc.returncode != 0:
        raise RuntimeError(
            f"`tailscale serve --https={serve_port} off` failed (exit "
            f"{proc.returncode}): {(proc.stderr or proc.stdout).strip()}"
        )
    if serve_port in _mappings(_serve_state(binary)):
        raise RuntimeError(f"tailscale serve :{serve_port} is still mapped after `off`")
    return True


def publish(slug: str, port: int, **opts) -> dict:
    """Expose http://127.0.0.1:<port> at https://<tailnet-host>:<serve_port>/.

    `slug` is accepted for interface symmetry and recorded in the details; the
    serve table itself is addressed by port.
    """
    binary = _binary(opts)
    prev_serve_port, prev_local_port = _previous(opts)
    reclaimed = None
    with _Lock():
        state = _serve_state(binary)
        serve_port = _find_existing(state, port)
        action = "existing"
        if serve_port is None:
            serve_port = _allocate(state, opts)
            proc = _run([binary, "serve", "--bg", f"--https={serve_port}", _origin(port)])
            if proc.returncode != 0:
                raise RuntimeError(
                    f"`tailscale serve --bg --https={serve_port} {_origin(port)}` failed "
                    f"(exit {proc.returncode}): {(proc.stderr or proc.stdout).strip()}"
                )
            action = "created"
        # Re-read rather than trust the exit code: a serve that reports success
        # but leaves no mapping is exactly the silent failure this transport
        # exists to stop.
        state = _serve_state(binary)
        landed = _mappings(state).get(serve_port)
        if not landed or landed.rstrip("/") not in _equivalent_origins(port):
            raise RuntimeError(
                f"tailscale serve did not register :{serve_port} -> {_origin(port)} "
                f"(serve table now says {landed!r})"
            )
        host = _hostname(state, binary)

        # The slug's local port can move between publishes (the old one sits
        # in TIME_WAIT, or something else grabbed it). Its previous serve port
        # now fronts a dead origin and nothing else will ever reclaim it, so
        # every re-publish would leak one. _remove_mapping no-ops if the port
        # has since been recycled onto a live page.
        # Both halves are required: without the old local port there is no way
        # to tell "our orphan" from "a port someone else has since taken", and
        # removing the latter takes down a live page.
        if prev_serve_port and prev_local_port and prev_serve_port != serve_port:
            if _remove_mapping(binary, prev_serve_port, prev_local_port):
                reclaimed = prev_serve_port

    details = {
        "transport": "tailscale",
        "slug": slug,
        "hostname": host,
        "https_port": serve_port,
        "local_port": int(port),
        "origin": _origin(port),
        "action": action,
    }
    if reclaimed:
        details["reclaimed_https_port"] = reclaimed
    return {"url": f"https://{host}:{serve_port}/", "details": details}


def unpublish(slug: str, **opts) -> dict:
    """Tear down the serve mapping for this slug's port.

    Only ever acts on a mapping identified by an explicit `https_port` or by an
    exact origin match on `port`. A slug name alone is not enough to identify a
    serve port, and guessing would tear down someone else's page.
    """
    binary = _binary(opts)
    https_port = opts.get("https_port")
    local_port = opts.get("port") or opts.get("local_port")

    with _Lock():
        state = _serve_state(binary)
        mappings = _mappings(state)

        if https_port is not None:
            serve_port = int(https_port)
            if serve_port not in mappings:
                return {
                    "ok": True,
                    "details": {"transport": "tailscale", "action": "noop",
                                "reason": f"no serve mapping on :{serve_port}",
                                "https_port": serve_port},
                }
            if local_port is not None and \
                    mappings[serve_port].rstrip("/") not in _equivalent_origins(local_port):
                # The port was recycled by another publish. Removing it would
                # take down a page that is not ours.
                return {
                    "ok": True,
                    "details": {"transport": "tailscale", "action": "noop",
                                "reason": f":{serve_port} now proxies "
                                          f"{mappings[serve_port]}, not {_origin(local_port)}",
                                "https_port": serve_port},
                }
        elif local_port is not None:
            found = _find_existing(state, local_port)
            if found is None:
                return {
                    "ok": True,
                    "details": {"transport": "tailscale", "action": "noop",
                                "reason": f"no serve mapping for {_origin(local_port)}"},
                }
            serve_port = found
        else:
            return {
                "ok": True,
                "details": {"transport": "tailscale", "action": "noop",
                            "reason": "neither https_port nor port given; refusing to "
                                      "guess which serve port belongs to "
                                      f"{slug!r}"},
            }

        removed = _remove_mapping(binary, serve_port, local_port)

    return {
        "ok": True,
        "details": {"transport": "tailscale",
                    "action": "removed" if removed else "noop",
                    "https_port": serve_port, "slug": slug},
    }


def status(slug: str | None = None, **opts) -> dict:
    binary = _binary(opts)
    state = _serve_state(binary)
    mappings = _mappings(state)
    try:
        host = _hostname(state, binary)
    except RuntimeError:
        host = None

    out: dict = {
        "transport": "tailscale",
        "hostname": host,
        "slug": slug,
        "mappings": mappings,
        "url": None,
    }
    local_port = opts.get("port") or opts.get("local_port")
    https_port = opts.get("https_port")
    serve_port = None
    if https_port is not None and int(https_port) in mappings:
        serve_port = int(https_port)
    elif local_port is not None:
        serve_port = _find_existing(state, local_port)
    if serve_port is not None and host:
        out["url"] = f"https://{host}:{serve_port}/"
        out["https_port"] = serve_port
    return out
