"""cloudflare_tailscale transport — a Cloudflare Tunnel route whose origin is a
`tailscale serve` endpoint rather than loopback.

Why this exists: a Cloudflare ingress rule pointing at `http://localhost:<port>`
returns 502 even when the connector runs on the same host as the sync server.
Fronting the same port with `tailscale serve` gives the connector an origin it
can reach, and that is what every route that has ever worked on this setup does.
Publishing the two halves separately is how pages ended up half-registered, so
they are composed here: publish creates the tailnet endpoint first and hands its
URL to the tunnel as `service`; unpublish removes the tunnel rule first so no
request can arrive at an origin that is already gone.
"""

import importlib.util
import sys
from pathlib import Path


def _sibling(name: str):
    """Load a sibling transport without assuming a package context.

    `transports.load()` imports modules by file path, so a plain relative
    import would fail with "attempted relative import with no known parent
    package". Reuse the same module cache key so a sibling loaded either way is
    the same object.
    """
    spec_name = f"annotate_transport_{name}"
    if spec_name in sys.modules:
        return sys.modules[spec_name]
    file = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(spec_name, file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec_name] = mod
    spec.loader.exec_module(mod)
    return mod


def publish(slug: str, port: int, **opts) -> dict:
    tailscale = _sibling("tailscale")
    cloudflare = _sibling("cloudflare")

    ts = tailscale.publish(slug, port, **opts)
    ts_details = ts.get("details", {})
    # Strip the trailing slash: cloudflared treats the service as an origin
    # base, and "https://host:8455/" would double the slash on every path.
    service = ts["url"].rstrip("/")

    try:
        cf = cloudflare.publish(slug, port, service=service, **opts)
    except Exception:
        # Leave no orphan serve port behind a tunnel rule that never landed.
        try:
            tailscale.unpublish(slug, https_port=ts_details.get("https_port"), port=port, **opts)
        except Exception:
            pass
        raise

    details = dict(cf.get("details", {}))
    details["transport"] = "cloudflare_tailscale"
    details["origin_service"] = service
    details["tailscale"] = ts_details
    details["https_port"] = ts_details.get("https_port")
    return {"url": cf["url"], "details": details}


def unpublish(slug: str, **opts) -> dict:
    tailscale = _sibling("tailscale")
    cloudflare = _sibling("cloudflare")

    cf = cloudflare.unpublish(slug, **opts)
    ts = tailscale.unpublish(slug, **opts)
    return {
        "ok": bool(cf.get("ok")) and bool(ts.get("ok")),
        "details": {
            "transport": "cloudflare_tailscale",
            "action": cf.get("details", {}).get("action", "ok"),
            "cloudflare": cf.get("details", {}),
            "tailscale": ts.get("details", {}),
        },
    }


def status(slug: str | None = None, **opts) -> dict:
    tailscale = _sibling("tailscale")
    cloudflare = _sibling("cloudflare")

    cf = cloudflare.status(slug, **opts)
    ts = tailscale.status(slug, **opts)
    return {
        "transport": "cloudflare_tailscale",
        "slug": slug,
        "url": cf.get("url"),
        "cloudflare": cf,
        "tailscale": ts,
    }
