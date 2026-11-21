"""Prototype UI routes, reached only for a page whose meta has "ui": "proto".

    /                         web/proto/shell.html
    /proto/data/<area>.json   proto_data.<area>.build(page_dir), or {} when no module exists yet
    /proto/<file>             a file under web/proto/
"""

from __future__ import annotations

import hashlib
import html
import importlib
import json
import re
import threading
import urllib.parse
from pathlib import Path

_AREA = re.compile(r"/proto/data/([a-z][a-z0-9_]{0,40})\.json")
_FILE = re.compile(r"/proto/([A-Za-z0-9][A-Za-z0-9_.-]{0,80})")
_COPY_META = re.compile(r"/proto/p/([a-z0-9][a-z0-9-]{0,40})/current\.meta\.json")

MASK = "member@example.com"
# every address, company mailboxes included; not image names such as icon@2x.png.
# A leading escape (\n, é) is kept, so escaped text (JSON in HTML) stays valid.
_ADDR = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?!(?:png|jpe?g|gif|svg|webp)\b)[A-Za-z]{2,}\b"
EMAIL = re.compile(_ADDR)
EMAIL_ESCAPED = re.compile(r"(\\u[0-9A-Fa-f]{4}|\\.)?" + _ADDR)
# a review link credential, or any similar key carried in a link
KEY = re.compile(r"([#?&;](?:review|token|key|access_token|auth|signin|invite)=)[^\s&#;\"'<>)\]\\]+", re.I)
# a run of link text holding %XX or &entity; (member%40x.com, #%72eview=k): checked again once decoded.
# The lookbehind pins each run to its start, so long runs (data URIs) stay linear.
_ENCODED = re.compile(r"(?<![^\s\"'<>()\[\]\\])[^\s\"'<>()\[\]\\%&]*[%&][^\s\"'<>()\[\]\\]*")
_UNSAFE = re.compile(r"[\s\x00-\x1f\x7f\"'<>()\[\]\\%]")


def _plain(s: str, escaped: bool) -> str:
    s = EMAIL_ESCAPED.sub(lambda m: (m[1] or "") + MASK, s) if escaped else EMAIL.sub(MASK, s)
    return KEY.sub(r"\1redacted", s)


def _decoded(m: re.Match) -> str:
    run = m[0]
    text = run
    for _ in range(4):  # URLSearchParams decodes once; nested encodings are decoded too, to be safe
        nxt = html.unescape(urllib.parse.unquote(text))
        if nxt == text:
            break
        text = nxt
    if text == run or _plain(text, False) == text:
        return run  # nothing hidden in it: left byte for byte
    # re-encode what would end the run, so a Markdown link stays one link
    return _UNSAFE.sub(lambda c: "%%%02X" % ord(c[0]), _plain(text, False))


def scrub(s: str, escaped: bool = False) -> str:
    """No real address and no review key leaves the prototype page, in plain or encoded form.
    escaped: s is raw JSON/HTML source text."""
    return _plain(_ENCODED.sub(_decoded, s), escaped)


def _walk(x):
    if isinstance(x, str):
        return scrub(x)
    if isinstance(x, list):
        return [_walk(v) for v in x]
    if isinstance(x, dict):
        return {scrub(k): _walk(v) for k, v in x.items()}
    return x


_done: dict = {}  # the last few scrubbed bodies by hash: polls re-send the same big store
_done_lock = threading.Lock()


def scrub_json(text: str) -> str:
    """Scrub JSON by its string values and keys, so escapes stay intact; one value per line (ndjson) works too."""
    if scrub(text, escaped=True) == text:
        return text  # nothing to hide: the body goes out byte for byte
    key = hashlib.sha256(text.encode("utf-8", "surrogateescape")).digest()
    if key in _done:
        return _done[key]
    try:
        out = json.dumps(_walk(json.loads(text)), ensure_ascii=False, separators=(",", ":"))
    except ValueError:
        try:
            out = "\n".join(json.dumps(_walk(json.loads(line)), ensure_ascii=False) if line.strip() else line
                            for line in text.split("\n"))
        except ValueError:
            out = scrub(text, escaped=True)
    with _done_lock:
        if len(_done) >= 8:
            _done.pop(next(iter(_done)))
        _done[key] = out
    return out


def build(area: str, page_dir) -> dict:
    try:
        module = importlib.import_module(f"{__name__}.{area}")
    except ModuleNotFoundError as exc:
        if exc.name != f"{__name__}.{area}":
            raise  # a real import error inside an area module must show
        return {}
    return module.build(page_dir)


def serve(handler, route_path: str):
    from .. import sync_server

    web = (handler.skill_dir or sync_server.WEB_DIR) / "proto"
    if route_path in ("", "/"):
        try:
            html = (web / "shell.html").read_bytes()
        except OSError:
            return handler._respond(500, b'{"error":"proto shell.html missing"}')
        return handler._respond(200, html, "text/html; charset=utf-8", cache_control=sync_server._NO_STORE)
    if route_path.startswith("/proto/p/"):  # a read-only copy of another project's page (frame.serve_other)
        from .frame import serve_other
        if m := _COPY_META.fullmatch(route_path):  # a copy follows its real page: a newer version starts copying behind this read
            from .copies import fresh
            fresh(Path(handler.artifact_dir).parent / f"proto-{m[1]}")
        return serve_other(handler, route_path)
    if match := _AREA.fullmatch(route_path):
        try:
            body = json.dumps(build(match[1], handler.artifact_dir), ensure_ascii=False).encode()
        except Exception as exc:  # an area's bug must not take the page down
            return handler._respond(500, json.dumps({"error": f"{type(exc).__name__}: {exc}"}).encode())
        return handler._respond(200, body, "application/json", cache_control="no-store")
    match = _FILE.fullmatch(route_path)
    if not match or match[1].startswith(".") or ".." in match[1] or not (web / match[1]).is_file():
        return handler._respond(404, b"Not found")
    target = web / match[1]
    return handler._respond(200, target.read_bytes(), sync_server._mime(target.suffix))
