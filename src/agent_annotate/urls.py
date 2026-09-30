"""Human page URLs include the served mount; local API origins stay separate."""

from urllib.parse import urlsplit, urlunsplit


def mounted_url(url: str | None, base_path: str | None) -> str | None:
    """Append a mount to an origin URL, preserving already-routed URLs."""
    if not url or not base_path:
        return url
    mount = base_path.strip("/")
    if not mount:
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if parts.path.strip("/"):
        return url
    path = "/" + mount + "/"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def page_url(record: dict) -> str | None:
    return mounted_url(record.get("url") or record.get("local_url"), record.get("public_base_path"))
