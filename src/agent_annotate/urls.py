"""Human page URLs include the served mount; local API origins stay separate."""

import re
from urllib.parse import unquote_plus, urlsplit, urlunsplit


def redact_review_key(url: str | None) -> str | None:
    """Keep an operational URL's normal anchors, excluding its bearer key."""
    if not url:
        return url
    base, separator, original = url.partition("#")
    fragment = "&".join(part for part in original.split("&")
                        if not ("=" in part and unquote_plus(part.partition("=")[0]) == "review"))
    if not separator or fragment == original:
        return url
    return base + ("#" + fragment if fragment else "")


def redact_share_links(value):
    """Copy an operational payload without share keys, including URLs in errors."""
    if isinstance(value, dict):
        return {key: redact_share_links(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_share_links(item) for item in value]
    if isinstance(value, str):
        def redact(match):
            url = match.group()
            bare = url.rstrip(".,;)]}")
            return redact_review_key(bare) + url[len(bare):]
        return re.sub(r"https?://[^\s<>\"'`]+", redact, value, flags=re.IGNORECASE)
    return value


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
    if record.get("transport_error"):
        return None
    url = mounted_url(record.get("public_url") or record.get("url") or record.get("local_url"), record.get("public_base_path"))
    if url and record.get("transport") == "funnel":
        from pathlib import Path

        from .review_access import read_key
        try:
            key = read_key(Path(record["slug_dir"]))
        except (OSError, ValueError, KeyError):
            return None
        parts = urlsplit(url)
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, "review=" + key))
    return url
