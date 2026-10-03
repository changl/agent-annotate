"""Page-scoped private share links and signed reviewer cookies for Funnel."""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import time
from http.cookies import CookieError, SimpleCookie
from pathlib import Path

from .paths import STATE_DIR


def _key_path(directory: Path) -> Path:
    scope = hashlib.sha256(str(directory.resolve()).encode()).hexdigest()
    return STATE_DIR / "review-keys" / (scope + ".key")


def read_key(directory: Path) -> str:
    path = _key_path(directory)
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("review key must not be a symlink")
    value = path.read_text().strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", value):
        raise ValueError("invalid review key")
    return value


def ensure_key(directory: Path) -> str:
    path = _key_path(directory)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink():
        raise ValueError("review key directory must not be a symlink")
    if path.exists() or path.is_symlink():
        return read_key(directory)
    # Publish complete bytes atomically; simultaneous sessions share one key.
    with tempfile.NamedTemporaryFile("w", dir=path.parent) as stream:
        stream.write(secrets.token_urlsafe(32))
        stream.flush()
        os.fsync(stream.fileno())
        try:
            os.link(stream.name, path)
        except FileExistsError:
            pass
    return read_key(directory)


def cookie_name(directory: Path) -> str:
    return "annotate_review_" + hashlib.sha256(str(directory.resolve()).encode()).hexdigest()[:12]


def _valid_name(name) -> bool:
    return (isinstance(name, str) and bool(name.strip()) and len(name) <= 80
            and not any(ord(c) < 32 or ord(c) == 127 for c in name))


def issue_cookie(directory: Path, key: str, name: str = "Reviewer", existing_cookie: str | None = None) -> str:
    if not isinstance(key, str) or not hmac.compare_digest(key, read_key(directory)):
        raise ValueError("invalid review link")
    if not _valid_name(name):
        raise ValueError("reviewer name must be 1-80 characters")
    reviewer, previous_name = identity(directory, existing_cookie or "")
    payload = {"id": reviewer.removeprefix("reviewer:") if reviewer else secrets.token_hex(8),
               "name": previous_name if reviewer and name == "Reviewer" else name.strip(),
               "expires": int(time.time()) + 30 * 86400}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return body + "." + hmac.new(key.encode(), body.encode(), hashlib.sha256).hexdigest()


def identity(directory: Path, header: str) -> tuple[str, str]:
    try:
        cookies = SimpleCookie()
        cookies.load(header)
        value = cookies[cookie_name(directory)].value
        if len(value) > 2048:
            return "", ""
        body, signature = value.split(".", 1)
        expected = hmac.new(read_key(directory).encode(), body.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return "", ""
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if (not isinstance(payload, dict)
                or type(payload.get("expires")) is not int or payload["expires"] < time.time()
                or not re.fullmatch(r"[a-f0-9]{16}", payload.get("id", ""))
                or not _valid_name(payload.get("name"))):
            return "", ""
        return "reviewer:" + payload["id"], payload["name"]
    except (OSError, ValueError, KeyError, TypeError, CookieError):
        return "", ""
