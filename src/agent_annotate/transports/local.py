"""local transport — no-op. Just returns http://localhost:<port>/.

Use for development or when no public URL is needed.
"""


def publish(slug: str, port: int, **opts) -> dict:
    url = f"http://localhost:{port}/"
    return {"url": url, "details": {"transport": "local", "port": port}}


def unpublish(slug: str, **opts) -> dict:
    # Nothing to tear down.
    return {"ok": True, "details": {"transport": "local"}}


def status(slug: str | None = None, **opts) -> dict:
    return {"transport": "local", "slug": slug, "url": None}
