"""Prototype UI routes, reached only for a page whose meta has "ui": "proto".

    /                         web/proto/shell.html
    /proto/data/<area>.json   proto_data.<area>.build(page_dir), or {} when no module exists yet
    /proto/<file>             a file under web/proto/
"""

from __future__ import annotations

import importlib
import json
import re

_AREA = re.compile(r"/proto/data/([a-z][a-z0-9_]{0,40})\.json")
_FILE = re.compile(r"/proto/([A-Za-z0-9][A-Za-z0-9_.-]{0,80})")

MASK = "member@example.com"
# every address, company mailboxes included; not image names such as icon@2x.png
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?!(?:png|jpe?g|gif|svg|webp)\b)[A-Za-z]{2,}\b")
# a review link credential, or any similar key carried in a link
KEY = re.compile(r"([#?&;](?:review|token|key|access_token|auth|signin|invite)=)[^\s&#;\"'<>)\]\\]+", re.I)


def scrub(s: str) -> str:
    """No real address and no review key leaves the prototype page."""
    return KEY.sub(r"\1redacted", EMAIL.sub(MASK, s))


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
