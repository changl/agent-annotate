"""tailscale transport — STUB.

Planned implementation (NOT YET WIRED — deferred per user 2026-06-28):

    # Publish a slug behind Tailscale Funnel:
    tailscale serve --bg --https=443 --set-path /<slug>/ http://localhost:<port>

    # Tear down:
    tailscale serve --https=443 --set-path /<slug>/ off

URL format: https://<tailnet-magic-dns>/<slug>/

🚨 STUB: tailscale transport — interface stub only — raises NotImplementedError.
Implementation deferred until the first project needs Tailscale-Funnel publishing
(no current project uses it; cloudflare transport covers all live deployments).
"""


def publish(slug: str, port: int, **opts) -> dict:
    raise NotImplementedError(
        "tailscale transport not yet implemented — "
        "use transport='cloudflare' or transport='local'. "
        "Wire `tailscale serve --bg --https=443 --set-path /<slug>/ http://localhost:<port>` here."
    )


def unpublish(slug: str, **opts) -> dict:
    raise NotImplementedError(
        "tailscale transport not yet implemented — "
        "wire `tailscale serve --https=443 --set-path /<slug>/ off` here."
    )


def status(slug: str | None = None, **opts) -> dict:
    raise NotImplementedError(
        "tailscale transport not yet implemented — "
        "wire `tailscale serve status --json` parsing here."
    )
