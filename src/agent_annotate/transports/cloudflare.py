"""Register and remove Cloudflare Tunnel ingress rules.

Configuration comes from explicit options or standard environment variables;
the transport has no project-specific defaults. Every mutation first stores a
private backup under Agent Annotate's state directory.
"""

import base64
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from agent_annotate.paths import STATE_DIR


def _read_env(env_file: str) -> dict:
    vals = {}
    p = Path(env_file)
    if not p.exists():
        raise FileNotFoundError(f"env file not found: {env_file}")
    with p.open("r") as f:
        for line in f:
            line = line.rstrip("\n")
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def _decode_account_id(encoded_credentials: str) -> str:
    pad = (4 - len(encoded_credentials) % 4) % 4
    raw = base64.b64decode(encoded_credentials + "=" * pad).decode()
    return json.loads(raw)["a"]


def _api_request(method: str, url: str, token: str, body: bytes | None = None) -> dict:
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if body is not None:
        req.add_header("Content-Type", "application/json")
        req.data = body
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode()
        except Exception:
            err_body = ""
        raise RuntimeError(f"Cloudflare API {method} {url} → HTTP {e.code}: {err_body}") from e
    if not data.get("success", False):
        raise RuntimeError(f"Cloudflare API success=false: {data.get('errors')}")
    return data


def _auth(opts: dict) -> tuple[str, str, str, str]:
    """Resolve (account_id, tunnel_id, hostname, token) from opts + env file."""
    env_file = opts.get("env_file") or os.environ.get("ANNOTATE_CLOUDFLARE_ENV_FILE")
    env = dict(os.environ)
    if env_file:
        env.update(_read_env(env_file))

    tunnel_id = opts.get("tunnel_id") or env.get("ANNOTATE_CLOUDFLARE_TUNNEL_ID")
    hostname = opts.get("hostname") or env.get("ANNOTATE_CLOUDFLARE_HOSTNAME")
    token = opts.get("token") or env.get("CLOUDFLARE_API_TOKEN")
    if not token:
        raise RuntimeError("CLOUDFLARE_API_TOKEN is required for the cloudflare transport")
    if not tunnel_id:
        raise RuntimeError("ANNOTATE_CLOUDFLARE_TUNNEL_ID is required for the cloudflare transport")
    if not hostname:
        raise RuntimeError("ANNOTATE_CLOUDFLARE_HOSTNAME is required for the cloudflare transport")

    account_id = opts.get("account_id") or env.get("CLOUDFLARE_ACCOUNT_ID")
    encoded_credentials = env.get("CLOUDFLARED_CREDENTIALS")
    if not account_id and encoded_credentials:
        account_id = _decode_account_id(encoded_credentials)
    if not account_id:
        raise RuntimeError("CLOUDFLARE_ACCOUNT_ID is required for the cloudflare transport")
    return account_id, tunnel_id, hostname, token


def _config_url(account_id: str, tunnel_id: str) -> str:
    return f"https://api.cloudflare.com/client/v4/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations"


def _backup(current_full: dict) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = STATE_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    bp = backup_dir / f"cf-tunnel-config.backup-{ts}.json"
    bp.write_text(json.dumps(current_full, indent=2))
    try:
        os.chmod(bp, 0o600)
    except OSError:
        pass
    return bp


def publish(slug: str, port: int, **opts) -> dict:
    """Insert or replace a hostname+path → origin ingress rule.

    The origin defaults to `http://localhost:<port>`, which only works when the
    connector can reach the sync server over loopback. Pass `service=<url>` to
    front the page with something the connector can actually reach — a
    `tailscale serve` HTTPS endpoint, for instance. See the
    `cloudflare_tailscale` transport.

    Returns {"url": str, "details": {...}}.
    """
    slug = slug.strip().lstrip("/")
    if not slug:
        raise ValueError("slug is empty")
    service = (opts.get("service") or "").strip() or f"http://localhost:{port}"
    account_id, tunnel_id, hostname, token = _auth(opts)
    api_url = _config_url(account_id, tunnel_id)

    current = _api_request("GET", api_url, token)
    config = current["result"]["config"]
    ingress = list(config.get("ingress", []))
    backup_path = _backup(current)

    target_path = f"/{slug}/.*"
    new_rule = {
        "path": target_path,
        "service": service,
        "hostname": hostname,
        "originRequest": {},
    }
    replaced = False
    new_ingress = []
    for rule in ingress:
        if rule.get("hostname") == hostname and rule.get("path") == target_path:
            new_ingress.append(new_rule)
            replaced = True
        else:
            new_ingress.append(rule)
    if not replaced:
        new_ingress = [new_rule] + ingress

    payload = {
        "config": {
            "ingress": new_ingress,
            "warp-routing": config.get("warp-routing", {"enabled": False}),
        }
    }
    _api_request("PUT", api_url, token, body=json.dumps(payload).encode())

    return {
        "url": f"https://{hostname}/{slug}/",
        "details": {
            "transport": "cloudflare",
            "hostname": hostname,
            "tunnel_id": tunnel_id,
            "path": target_path,
            "port": port,
            "service": service,
            "action": "replaced" if replaced else "inserted",
            "backup": str(backup_path),
        },
    }


def unpublish(slug: str, **opts) -> dict:
    """Remove the hostname+path rule for `slug`. No-op if absent."""
    slug = slug.strip().lstrip("/")
    if not slug:
        raise ValueError("slug is empty")
    account_id, tunnel_id, hostname, token = _auth(opts)
    api_url = _config_url(account_id, tunnel_id)

    current = _api_request("GET", api_url, token)
    config = current["result"]["config"]
    ingress = list(config.get("ingress", []))
    backup_path = _backup(current)

    target_path = f"/{slug}/.*"
    removed = False
    new_ingress = []
    for rule in ingress:
        if rule.get("hostname") == hostname and rule.get("path") == target_path:
            removed = True
            continue
        new_ingress.append(rule)

    if not removed:
        return {
            "ok": True,
            "details": {
                "transport": "cloudflare",
                "action": "noop",
                "reason": "no matching rule",
                "hostname": hostname,
                "path": target_path,
                "backup": str(backup_path),
            },
        }

    payload = {
        "config": {
            "ingress": new_ingress,
            "warp-routing": config.get("warp-routing", {"enabled": False}),
        }
    }
    _api_request("PUT", api_url, token, body=json.dumps(payload).encode())
    return {
        "ok": True,
        "details": {
            "transport": "cloudflare",
            "action": "removed",
            "hostname": hostname,
            "path": target_path,
            "backup": str(backup_path),
        },
    }


def status(slug: str | None = None, **opts) -> dict:
    """Return ingress matching this slug (or all rules if slug is None)."""
    account_id, tunnel_id, hostname, token = _auth(opts)
    api_url = _config_url(account_id, tunnel_id)
    current = _api_request("GET", api_url, token)
    ingress = current["result"]["config"].get("ingress", [])
    if slug is None:
        return {
            "transport": "cloudflare",
            "hostname": hostname,
            "tunnel_id": tunnel_id,
            "ingress": ingress,
        }
    slug_norm = slug.strip().lstrip("/")
    target_path = f"/{slug_norm}/.*"
    matches = [
        r for r in ingress
        if r.get("hostname") == hostname and r.get("path") == target_path
    ]
    return {
        "transport": "cloudflare",
        "hostname": hostname,
        "slug": slug_norm,
        "matches": matches,
        "url": f"https://{hostname}/{slug_norm}/" if matches else None,
    }
