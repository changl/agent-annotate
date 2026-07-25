#!/usr/bin/env python3
"""
annotate sync_server.py — stdlib-only HTTP server for annotatable HTML artifacts.

Supports BOTH the v1 single-file mode (backwards-compat with running v4-2/v4-3
servers) and the v2 directory-layout slug mode.

────────────────────────────────────────────────────────────────────────────
V1 USAGE (single HTML file; backward compatible)
────────────────────────────────────────────────────────────────────────────

    python sync_server.py <artifact.html> [--port N] [--public-base-path /slug]

    Routes:
      GET  /api/comments?doc=<id>  → return <dir>/<id>.comments.json or {}
      POST /api/comments?doc=<id>  → write JSON body to <dir>/<id>.comments.json
      *                            → serve static files from the artifact's directory

────────────────────────────────────────────────────────────────────────────
V2 USAGE (directory layout, version-pivot, comment lifecycle)
────────────────────────────────────────────────────────────────────────────

    python sync_server.py --slug-dir <slug-dir>/ [--port N] [--public-base-path /slug] \\
        [--bus-dir <platform data dir>/agent-annotate/bus/<project>]

    Expected layout under <slug-dir>:
        current.html         (symlink → versions/vN.html)
        current.meta.json    { current: "vN", history: [{version, ts, label}] }
        comments.json        v2 shape (see below)
        versions/vN.html     frozen per-version HTML
        archive/             archived comments snapshots

    v2 comment store shape:
        {
          "schema_version": 2,
          "anchors": {
            "<anchor_id>": [
              { "id": str, "anchor_id": str, "text": str, "author": str,
                "created_at": iso, "version": "vN",
                "status": "open" | "addressed_by_agent" | "user_confirmed" | "archived",
                "response_text": str | null,
                "replies": [ { "author": str, "text": str, "ts": iso } ]
              },
              ...
            ]
          },
          "archived": { "<anchor_id>": [ ... ] }
        }

    Routes:
      GET  /                                → current.html (?v=vN → versions/vN.html)
      GET  /current.meta.json               → current meta JSON
      GET  /comments.json                   → entire v2 comment store
      GET  /api/comments?status=&version=   → filtered comments
      PUT  /api/comments/<id>               → set status / response_text
      POST /api/comments/<id>/reply         → append a thread reply
      POST /api/comments/<id>/archive       → move comment to archived
      POST /api/comments                    → v1-compatible whole-store POST OR
                                              v2-compatible single-comment create
      *                                     → serve static files from <slug-dir>

    NDJSON bus: every comment event appends to <bus-dir>/<slug>.ndjson.
    Author extraction reads Cf-Access-Authenticated-User-Email header.

    Auto-migration: a v1 store ({nodeId: [comment]}) is wrapped to v2 shape on
    first write — original is backed up next to comments.json.
"""

import argparse
import hashlib
import http.server
import json
import os
import re
import socket
import sys
import threading
import time
import urllib.parse
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .extract import ExtractionError, build_content_document, has_canvas_sentinels
from .paths import BUS_ROOT, MONITOR_OFFSET_ROOT, MONITOR_ROOT, STATE_DIR, WEB_DIR

SKILL_STATE_DIR = STATE_DIR  # compatibility name retained for the v2.11 server code


# ────────────────────────────────────────────────────────────────────────────
# Free port discovery
# ────────────────────────────────────────────────────────────────────────────
def find_free_port(start: int) -> int:
    """Try ports starting at `start`, return the first free one."""
    port = start
    while port < start + 20:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", port))
                return port
            except OSError:
                port += 1
    raise RuntimeError(f"No free port found starting at {start}")


# ────────────────────────────────────────────────────────────────────────────
# Mime
# ────────────────────────────────────────────────────────────────────────────
def _mime(suffix: str) -> str:
    return {
        ".html": "text/html; charset=utf-8",
        ".htm":  "text/html; charset=utf-8",
        ".css":  "text/css",
        ".js":   "application/javascript",
        ".json": "application/json",
        ".svg":  "image/svg+xml",
        ".png":  "image/png",
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif":  "image/gif",
        ".ico":  "image/x-icon",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".ttf":  "font/ttf",
    }.get(suffix.lower(), "application/octet-stream")


# ────────────────────────────────────────────────────────────────────────────
# Edge-cache discipline
#
# Cloudflare edge-caches .js/.css by default when the origin sends no cache
# headers (the pre-2026-07-13 server sent none), and the shell referenced
# its assets with bare unversioned URLs — so users behind the tunnel kept
# receiving stale shell.js/shell.css even after hard refresh. Two layers of
# defense, both required:
#   1. Asset URLs are stamped with the source file's mtime (?v=<int>) at
#      serve time — a changed file mints a NEW edge cache key instantly,
#      no purge needed.
#   2. .js/.css responses carry Cache-Control: no-store so the edge never
#      caches them again.
# ────────────────────────────────────────────────────────────────────────────
_NO_STORE = "no-store, max-age=0, must-revalidate"

# /assets/<digits>/<known asset name> — the digits are a cache-key stamp only.
_ASSET_PATH_RE = re.compile(r"^/assets/(\d+)/(shell\.js|shell\.css|adapter\.js|diagram-plot\.js)$")


def _cache_control_for(suffix: str) -> str:
    if suffix.lower() in (".js", ".css"):
        return _NO_STORE
    return "no-cache"


def _mtime_stamp(path) -> str:
    """Integer-mtime cache-buster for an asset URL. Falls back to 'now' if
    the file can't be statted — the bypass still works, just never caches."""
    if path is not None:
        try:
            return str(int(Path(path).stat().st_mtime))
        except OSError:
            pass
    return str(int(time.time()))


# ────────────────────────────────────────────────────────────────────────────
# V2 storage helpers (file lock + shape coercion)
# ────────────────────────────────────────────────────────────────────────────
_STORE_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _iso_timestamp(value: Any) -> float:
    if not isinstance(value, str) or not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def _comment_needs_push(comment: dict) -> bool:
    """Server-side mirror of shell.js needsPush().

    The toolbar badge promises to send only open comments with activity newer
    than their last push. Keep the write route on the same contract so an
    active session is not repeatedly notified about every older open comment.
    """
    if comment.get("status") != "open":
        return False
    if not comment.get("flagged_for_session"):
        return True
    flagged_at = _iso_timestamp(comment.get("flagged_at"))
    latest = _iso_timestamp(comment.get("edited_at"))
    for reply in comment.get("replies", []):
        if not str(reply.get("author") or "").startswith("agent:"):
            latest = max(latest, _iso_timestamp(reply.get("ts")))
    return latest > flagged_at


def _coerce_v2(raw: Any) -> dict:
    """Coerce any prior comment-store shape into v2.

    Recognized inputs:
      - v2: {"schema_version": 2, "anchors": {...}, "archived": {...}}
      - v1 nodeId map: {nodeId: [comment]}
      - prem-fin list: [{id, sectionId, sectionLabel, text, author, timestamp, status}]
      - empty / unknown: returns empty v2 store
    """
    if isinstance(raw, dict) and raw.get("schema_version") == 2:
        raw.setdefault("anchors", {})
        raw.setdefault("archived", {})
        return raw

    # prem-fin list shape
    if isinstance(raw, list):
        store = {"schema_version": 2, "anchors": {}, "archived": {}}
        for c in raw:
            anchor = c.get("sectionId") or c.get("anchor_id") or "unknown"
            new = {
                "id": c.get("id") or _new_id(),
                "anchor_id": anchor,
                "anchor_label": c.get("sectionLabel") or c.get("anchor_label"),
                "text": c.get("text", ""),
                "author": c.get("author", "anonymous"),
                "created_at": c.get("created_at") or c.get("timestamp") or _now_iso(),
                "version": c.get("version", "v1"),
                "status": _coerce_status(c.get("status", "open")),
                "response_text": c.get("response_text"),
                "replies": c.get("replies", []),
            }
            store["anchors"].setdefault(anchor, []).append(new)
        return store

    # v1 nodeId map
    if isinstance(raw, dict):
        store = {"schema_version": 2, "anchors": {}, "archived": {}}
        for node_id, items in raw.items():
            if not isinstance(items, list):
                continue
            for c in items:
                new = {
                    "id": c.get("id") or _new_id(),
                    "anchor_id": node_id,
                    "anchor_label": c.get("nodeLabel"),
                    "text": c.get("text", ""),
                    "author": c.get("author", "anonymous"),
                    "created_at": c.get("createdAt") or c.get("created_at") or _now_iso(),
                    "version": c.get("version", "v1"),
                    "status": _coerce_status(c.get("status", "open")),
                    "response_text": c.get("response_text"),
                    "replies": c.get("replies", []),
                }
                store["anchors"].setdefault(node_id, []).append(new)
        return store

    return {"schema_version": 2, "anchors": {}, "archived": {}}


_STATUS_MAP = {
    "open": "open",
    "addressed": "addressed_by_agent",
    "addressed_by_agent": "addressed_by_agent",
    "user_confirmed": "user_confirmed",
    "confirmed": "user_confirmed",
    "archived": "archived",
    "resolved": "user_confirmed",
}


def _coerce_status(s: str) -> str:
    return _STATUS_MAP.get((s or "").lower(), "open")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _load_v2_store(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 2, "anchors": {}, "archived": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": 2, "anchors": {}, "archived": {}}
    coerced = _coerce_v2(raw)
    # Auto-write back if shape changed and original wasn't already v2.
    if not (isinstance(raw, dict) and raw.get("schema_version") == 2):
        backup = path.with_suffix(path.suffix + ".v1.bak")
        if not backup.exists():
            try:
                backup.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
        try:
            _atomic_write_json(path, coerced)
        except OSError:
            pass
    return coerced


def _atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


# ────────────────────────────────────────────────────────────────────────────
# Seen/last-visit tracking (sidecar file, never touches comments.json)
# ────────────────────────────────────────────────────────────────────────────
_SEEN_LOCK = threading.Lock()


def _seen_path(artifact_dir: Path) -> Path:
    return artifact_dir / "seen.json"


def _load_seen(artifact_dir: Path) -> dict:
    p = _seen_path(artifact_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_seen(artifact_dir: Path, data: dict) -> None:
    _atomic_write_json(_seen_path(artifact_dir), data)


def _author_key(author: str) -> str:
    """Sidecar dict key for an author identity. Empty/anonymous authors get
    a stable bucket so localStorage-only clients still get *something*
    server-side, but the real per-user signal is the identified email/agent
    id — 'anonymous' visits are intentionally pooled and low-value."""
    return author or "anonymous"


# ────────────────────────────────────────────────────────────────────────────
# Per-comment read-state tracking (sidecar file, never touches comments.json)
#
# Shape: { "<author_key>": { "<comment_id>": {"ts": iso, "sig": str} } }
# `sig` is a client-computed digest of the comment's activity-relevant fields
# (status, response_text, reply count, edited_at). A comment is "read" for a
# viewer only while its stored sig matches the live comment — any later agent
# response/status change makes the sigs diverge, which the shell renders as
# "NEW reply". Read-state is viewer bookkeeping, not comment data, so it
# lives in its own sidecar exactly like seen.json.
# ────────────────────────────────────────────────────────────────────────────
_READ_LOCK = threading.Lock()


def _read_state_path(artifact_dir: Path) -> Path:
    return artifact_dir / "read-state.json"


def _load_read_state(artifact_dir: Path) -> dict:
    p = _read_state_path(artifact_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_read_state(artifact_dir: Path, data: dict) -> None:
    _atomic_write_json(_read_state_path(artifact_dir), data)


# ────────────────────────────────────────────────────────────────────────────
# Content hashing (per-version + per-anchor-group stamps for ↑NEW detection)
# ────────────────────────────────────────────────────────────────────────────
def _sha256_short(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


_SECTION_RE = re.compile(
    r'<section\b[^>]*\bid="([^"]+)"[^>]*>(.*?)</section>|'
    r'<div\b[^>]*\bdata-anchor-id="([^"]+)"[^>]*>(.*?)</div>',
    re.DOTALL,
)


def compute_content_stamps(content_html: str) -> dict:
    """Compute a whole-doc hash plus best-effort per-section hashes for a
    chrome-free content document. Per-section hashes key off the same
    id="..." / data-anchor-id="..." scheme adapter.js uses to resolve
    anchors, so a shell can diff 'has this section's content changed since
    my last visit' without re-fetching the full comment thread state.
    Best-effort: nested tags of the same kind will just take the first
    (outermost-ish) match per regex scan; good enough for a coarse
    'something changed here' signal, not a structural diff.
    """
    whole = _sha256_short(content_html)
    sections: dict[str, str] = {}
    for m in _SECTION_RE.finditer(content_html):
        anchor_id = m.group(1) or m.group(3)
        body = m.group(2) or m.group(4) or ""
        if anchor_id:
            # keep the first occurrence; don't overwrite on nested/duplicate ids
            sections.setdefault(anchor_id, _sha256_short(body))
    return {"whole": whole, "sections": sections}


# ────────────────────────────────────────────────────────────────────────────
# NDJSON bus
# ────────────────────────────────────────────────────────────────────────────
def _bus_append(bus_dir: Path | None, slug: str, event: dict) -> None:
    if not bus_dir:
        return
    bus_dir.mkdir(parents=True, exist_ok=True)
    f = bus_dir / f"{slug}.ndjson"
    event = dict(event)
    event.setdefault("ts", _now_iso())
    event.setdefault("slug", slug)
    line = json.dumps(event, ensure_ascii=False) + "\n"
    with f.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _monitor_project(bus_dir: Path | None) -> str:
    return bus_dir.name if bus_dir else "default"


def _monitor_offset_path(bus_dir: Path | None, slug: str) -> Path:
    return MONITOR_OFFSET_ROOT / _monitor_project(bus_dir) / f"{slug}.offset"


def _ensure_monitor_offset_baseline(bus_dir: Path | None, slug: str) -> None:
    """Create the shared delivery cursor before the first post-upgrade push.

    A monitor armed later can then replay the push without flooding the active
    session with the slug's entire historical bus.
    """
    if not bus_dir:
        return
    offset_path = _monitor_offset_path(bus_dir, slug)
    if offset_path.exists():
        return
    offset_path.parent.mkdir(parents=True, exist_ok=True)
    bus_file = bus_dir / f"{slug}.ndjson"
    size = bus_file.stat().st_size if bus_file.exists() else 0
    tmp = offset_path.with_suffix(".offset.tmp")
    tmp.write_text(str(size), encoding="utf-8")
    os.replace(tmp, offset_path)


def _active_monitor_leases(bus_dir: Path | None, slug: str) -> list[dict]:
    """Return live monitor leases for this exact project/slug bus.

    Dead leases are removed opportunistically. A lease is valid only while its
    process exists and its recorded bus path matches the server's bus.
    """
    if not bus_dir:
        return []
    lease_dir = MONITOR_ROOT / _monitor_project(bus_dir) / slug
    if not lease_dir.exists():
        return []
    expected_bus = str((bus_dir / f"{slug}.ndjson").resolve())
    leases = []
    for lease_path in lease_dir.glob("*.json"):
        try:
            lease = json.loads(lease_path.read_text(encoding="utf-8"))
            pid = int(lease.get("pid", 0))
            if str(Path(lease.get("bus_file", "")).resolve()) != expected_bus:
                raise ValueError("bus mismatch")
            os.kill(pid, 0)
            leases.append(lease)
        except Exception:
            try:
                lease_path.unlink()
            except OSError:
                pass
    return leases


def _active_monitor_count(bus_dir: Path | None, slug: str) -> int:
    return len(_active_monitor_leases(bus_dir, slug))


def _public_monitor_owner(lease: dict | None) -> dict | None:
    if not lease:
        return None
    return {
        "owner_session": lease.get("owner_session"),
        "owner_agent": lease.get("owner_agent"),
        "host": lease.get("host"),
        "started_at": lease.get("started_at"),
    }


# ────────────────────────────────────────────────────────────────────────────
# Handler
# ────────────────────────────────────────────────────────────────────────────
class AnnotateHandler(http.server.BaseHTTPRequestHandler):
    # Set per-instance via make_handler():
    artifact_dir: Path
    artifact_file: str = "current.html"
    doc_id: str = ""
    slug: str = ""
    public_base_path: str = ""
    bus_dir: Path | None = None
    v2_mode: bool = False
    skill_dir: Path | None = None  # packaged web asset directory

    # ── Path normalization ──────────────────────────────────────────
    def _strip_base(self, path: str) -> str:
        prefix = self.public_base_path
        if not prefix:
            return path
        if path == prefix:
            return "/"
        if path.startswith(prefix + "/"):
            stripped = path[len(prefix):]
            return stripped or "/"
        return path

    def _identity(self) -> dict:
        """Return identity supplied by the trusted OAuth/access proxy.

        Client query parameters and JSON bodies are deliberately excluded:
        they are display input, not authentication evidence.
        """
        email = (
            self.headers.get("Cf-Access-Authenticated-User-Email")
            or self.headers.get("oai-authenticated-user-email")
            or ""
        ).strip()
        name = (
            self.headers.get("Cf-Access-Authenticated-User-Name")
            or self.headers.get("X-Auth-Request-User")
            or ""
        ).strip()
        oai_name = self.headers.get("oai-authenticated-user-full-name")
        if not name and oai_name:
            encoding = self.headers.get("oai-authenticated-user-full-name-encoding", "")
            name = urllib.parse.unquote(oai_name) if encoding == "percent-encoded-utf-8" else oai_name
            name = name.strip()
        return {
            "email": email or None,
            "name": name or None,
            "authenticated": bool(email),
        }

    def _author(self, parsed=None) -> str:
        return self._identity()["email"] or "anonymous"

    # ── GET ──────────────────────────────────────────────────────────
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        route_path = self._strip_base(parsed.path)

        if self.v2_mode:
            if route_path == "/api/comments":
                return self._v2_get_comments(parsed)
            if route_path == "/api/seen":
                return self._v2_get_seen(parsed)
            if route_path == "/api/read-state":
                return self._v2_get_read_state(parsed)
            if route_path == "/api/identity":
                return self._v2_get_identity(parsed)
            if route_path == "/api/session-monitor":
                return self._v2_get_session_monitor(parsed)
            if route_path == "/comments.json":
                return self._v2_get_store()
            if route_path == "/current.meta.json":
                return self._v2_get_meta()
            if route_path in ("/shell.js", "/shell.css", "/adapter.js"):
                return self._serve_skill_asset(route_path.lstrip("/"))
            # PATH-versioned assets: /assets/<stamp>/<name>. The stamp segment
            # exists purely as an edge cache key — some CDN configurations
            # strip query strings from cache keys, which made ?v= busting a
            # no-op; a distinct PATH always misses stale cache entries. The
            # stamp is ignored for file resolution.
            m = _ASSET_PATH_RE.match(route_path)
            if m:
                return self._serve_versioned_asset(m.group(2))
            if route_path == "/content":
                return self._v2_serve_content(parsed)
            if route_path == "/" or route_path == "":
                return self._v2_serve_root(parsed)
            return self._serve_static(route_path)
        else:
            if route_path == "/api/comments":
                return self._v1_get_comments(parsed)
            return self._serve_static(route_path)

    # ── POST ─────────────────────────────────────────────────────────
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        route_path = self._strip_base(parsed.path)

        if self.v2_mode:
            if route_path == "/api/comments":
                return self._v2_post_comments(parsed)
            if route_path == "/api/push-session":
                return self._v2_post_push_session(parsed)
            if route_path == "/api/seen":
                return self._v2_post_seen(parsed)
            if route_path == "/api/read-state":
                return self._v2_post_read_state(parsed)
            if route_path.startswith("/api/comments/") and route_path.endswith("/reply"):
                cid = route_path[len("/api/comments/"):-len("/reply")]
                return self._v2_post_reply(cid, parsed)
            if route_path.startswith("/api/comments/") and route_path.endswith("/archive"):
                cid = route_path[len("/api/comments/"):-len("/archive")]
                return self._v2_post_archive(cid, parsed)
            if route_path.startswith("/api/comments/") and route_path.endswith("/accept"):
                cid = route_path[len("/api/comments/"):-len("/accept")]
                return self._v2_post_accept(cid, parsed)
            if route_path.startswith("/api/comments/") and route_path.endswith("/restore"):
                cid = route_path[len("/api/comments/"):-len("/restore")]
                return self._v2_post_restore(cid, parsed)
            if route_path.startswith("/api/comments/") and route_path.endswith("/push"):
                cid = route_path[len("/api/comments/"):-len("/push")]
                return self._v2_post_push_single(cid, parsed)
            self._respond(404, b'{"error":"Not found"}')
            return
        else:
            if route_path == "/api/comments":
                return self._v1_post_comments(parsed)
            self._respond(404, b"Not found")

    def do_PUT(self):
        parsed = urllib.parse.urlparse(self.path)
        route_path = self._strip_base(parsed.path)
        if self.v2_mode and route_path.startswith("/api/comments/"):
            cid = route_path[len("/api/comments/"):]
            return self._v2_put_comment(cid, parsed)
        self._respond(404, b'{"error":"Not found"}')

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept, Cf-Access-Authenticated-User-Email")
        self.end_headers()

    # ── V1 routes (backward compat) ─────────────────────────────────
    def _v1_get_comments(self, parsed):
        params = urllib.parse.parse_qs(parsed.query)
        doc = (params.get("doc") or [None])[0]
        if not doc:
            self._respond(400, b'{"error":"missing doc param"}')
            return
        json_path = self.artifact_dir / (doc + ".comments.json")
        if json_path.exists():
            try:
                data = json_path.read_bytes()
            except OSError:
                self._respond(500, b'{"error":"read error"}')
                return
        else:
            data = b"{}"
        self._respond(200, data, content_type="application/json")

    def _v1_post_comments(self, parsed):
        params = urllib.parse.parse_qs(parsed.query)
        doc = (params.get("doc") or [None])[0]
        if not doc:
            self._respond(400, b'{"error":"missing doc param"}')
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            self._respond(400, f'{{"error":"invalid json: {exc}"}}'.encode())
            return
        json_path = self.artifact_dir / (doc + ".comments.json")
        try:
            _atomic_write_json(json_path, data)
        except OSError as exc:
            self._respond(500, f'{{"error":"write error: {exc}"}}'.encode())
            return
        total = sum(len(v) for v in data.values() if isinstance(v, list))
        print(f"  POST /api/comments?doc={doc} → {total} comment(s) → {json_path}", flush=True)
        self._respond(200, b'{"ok":true}', content_type="application/json")

    # ── V2 routes ────────────────────────────────────────────────────
    def _store_path(self) -> Path:
        return self.artifact_dir / "comments.json"

    def _meta_path(self) -> Path:
        return self.artifact_dir / "current.meta.json"

    def _v2_load(self) -> dict:
        return _load_v2_store(self._store_path())

    def _v2_save(self, store: dict) -> None:
        _atomic_write_json(self._store_path(), store)

    def _v2_get_store(self):
        with _STORE_LOCK:
            store = self._v2_load()
        self._respond(200, json.dumps(store, ensure_ascii=False).encode(), "application/json")

    def _v2_get_meta(self):
        p = self._meta_path()
        if p.exists():
            try:
                data = p.read_bytes()
            except OSError:
                data = b"{}"
        else:
            data = json.dumps({"current": "v1", "history": []}).encode()
        self._respond(200, data, "application/json")

    def _v2_get_comments(self, parsed):
        params = urllib.parse.parse_qs(parsed.query)
        flt_status = (params.get("status") or [None])[0]
        flt_version = (params.get("version") or [None])[0]
        with _STORE_LOCK:
            store = self._v2_load()
        out = []
        for anchor_id, items in store.get("anchors", {}).items():
            for c in items:
                if flt_status and c.get("status") != flt_status:
                    continue
                if flt_version and c.get("version") != flt_version:
                    continue
                out.append(c)
        self._respond(200, json.dumps(out, ensure_ascii=False).encode(), "application/json")

    def _has_content_dir(self) -> bool:
        return (self.artifact_dir / "content").is_dir()

    def _version_path(self, version: str | None):
        if version:
            return self.artifact_dir / "versions" / f"{version}.html"
        return self.artifact_dir / "current.html"

    def _extractable_version(self, version: str | None) -> bool:
        """True when a baked legacy version can be served through the shell.

        Chrome baked into versions/<v>.html at generation time is why a fix to
        the artifact chrome never reached an already-published page. When the
        canvas sentinels are present the server can recover the author's
        content and serve it through the universal shell instead, so chrome
        comes from the skill dir on every request like it does for every other
        slug. Nothing is written to disk — see _v2_serve_content.
        """
        target = self._version_path(version)
        if not target.exists() or not target.is_file():
            return False
        try:
            return has_canvas_sentinels(target.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            return False

    def _shell_eligible(self, parsed=None) -> bool:
        if self._has_content_dir():
            return True
        version = None
        if parsed is not None:
            params = urllib.parse.parse_qs(parsed.query)
            version = (params.get("v") or [None])[0]
        if version is None:
            version = self._read_meta().get("current")
        return self._extractable_version(version)

    def _v2_serve_root(self, parsed):
        # Universal-shell slugs serve the shared shell.html at root; the shell
        # reads ?v= client-side and loads the right iframe src. A slug earns
        # that path either by having a content/ dir of chrome-free docs, or by
        # being a baked legacy artifact the server can extract on the fly.
        # Anything else (no sentinels, e.g. hand-written HTML that never went
        # through template.html) still gets the old direct-serve behavior.
        if self._shell_eligible(parsed):
            shell_path = (self.skill_dir / "shell.html") if self.skill_dir else None
            if shell_path and shell_path.exists():
                try:
                    html = shell_path.read_text(encoding="utf-8")
                except OSError:
                    self._respond(500, b"Read error")
                    return
                # PATH-versioned chrome asset refs: new file mtime -> new URL
                # PATH -> guaranteed edge cache miss. (?v= query stamps proved
                # insufficient: some CDN configs strip query strings from the
                # cache key, so the stamped URL still hit the stale entry.)
                base = self.public_base_path or ""
                html = html.replace(
                    'href="shell.css"',
                    'href="%s/assets/%s/shell.css"' % (base, _mtime_stamp(self.skill_dir / "shell.css")), 1)
                html = html.replace(
                    'src="shell.js"',
                    'src="%s/assets/%s/shell.js"' % (base, _mtime_stamp(self.skill_dir / "shell.js")), 1)
                self._respond(200, html.encode("utf-8"), "text/html; charset=utf-8",
                              cache_control=_NO_STORE)
                return
            # skill_dir/shell.html missing — fail loudly rather than silently
            # falling back, so a broken deploy is visible instead of masked.
            self._respond(500, b'{"error":"shell.html not found next to sync_server.py"}')
            return

        params = urllib.parse.parse_qs(parsed.query)
        v = (params.get("v") or [None])[0]
        if v:
            target = self.artifact_dir / "versions" / f"{v}.html"
        else:
            target = self.artifact_dir / "current.html"
        if not target.exists() or not target.is_file():
            self._respond(404, b"Not found")
            return
        try:
            data = target.read_bytes()
        except OSError:
            self._respond(500, b"Read error")
            return
        self._respond(200, data, "text/html; charset=utf-8")

    def _ensure_content_stamp(self, version: str, html: str, content_path: Path) -> None:
        """Compute-and-cache content_stamps[version] into current.meta.json
        the first time this version is served (or whenever the content
        file's mtime moves past what's recorded). Cheap enough to check on
        every request; the hash recompute itself only runs on a stale/
        missing stamp, not on every GET.
        """
        with _STORE_LOCK:  # reuse the store lock; meta writes are rare & small
            meta = self._read_meta()
            stamps = meta.setdefault("content_stamps", {})
            existing = stamps.get(version)
            mtime = content_path.stat().st_mtime
            if existing and existing.get("_mtime") == mtime:
                return  # up to date
            computed = compute_content_stamps(html)
            computed["_mtime"] = mtime
            stamps[version] = computed
            try:
                self._v2_save_meta(meta)
            except OSError:
                pass  # best-effort; ↑NEW detection degrades gracefully, not fatal

    def _v2_save_meta(self, meta: dict) -> None:
        _atomic_write_json(self._meta_path(), meta)

    def _v2_serve_content(self, parsed):
        """GET /content?v=vN — serve the chrome-free extracted content doc
        for version vN, with adapter.js injected before </body>. Falls back
        to 'current' version from current.meta.json when ?v= is omitted.
        """
        params = urllib.parse.parse_qs(parsed.query)
        v = (params.get("v") or [None])[0]
        if not v:
            meta = self._read_meta()
            v = meta.get("current")
        if not v:
            self._respond(400, b'{"error":"no version specified and no current.meta.json"}')
            return
        target = self.artifact_dir / "content" / f"{v}.html"
        if target.exists() and target.is_file():
            try:
                html = target.read_text(encoding="utf-8")
            except OSError:
                self._respond(500, b"Read error")
                return
            self._ensure_content_stamp(v, html, target)
        else:
            # No content/ doc: recover one from the baked legacy artifact.
            # Doing this at request time rather than as a one-off migration is
            # what keeps chrome fixes universal — a legacy page picks up the
            # current adapter.js on its next request exactly like a migrated
            # slug, with no file to re-generate and no stale duplicate on
            # disk. An explicit content/<v>.html always wins, so a hand-tuned
            # extraction is never overridden.
            baked = self._version_path(v)
            if not baked.exists() or not baked.is_file():
                self._respond(404, f'{{"error":"content not found for version {v}"}}'.encode())
                return
            try:
                raw = baked.read_text(encoding="utf-8", errors="replace")
            except OSError:
                self._respond(500, b"Read error")
                return
            try:
                html = build_content_document(raw, title=self.slug or "Annotate content")
            except ExtractionError as exc:
                self._respond(
                    500,
                    json.dumps({"error": f"could not extract content for {v}: {exc}"}).encode(),
                    "application/json",
                )
                return
            self._ensure_content_stamp(v, html, baked)

        # Inject adapter.js (served from /adapter.js, which _strip_base +
        # do_GET route to the skill dir) plus a small bootstrap so the
        # adapter knows which version/base-path it's running under.
        # Both injected refs carry mtime stamps (edge-cache bypass, see
        # _cache_control_for).
        base = self.public_base_path or ""
        adapter_v = _mtime_stamp((self.skill_dir / "adapter.js") if self.skill_dir else None)
        bootstrap = (
            f'<script>window.__ANNOTATE_CONTENT_META__='
            f'{json.dumps({"version": v, "publicBasePath": base, "slug": self.slug})};</script>\n'
            f'<script src="{base}/assets/{adapter_v}/adapter.js"></script>\n'
        )
        if "</body>" in html:
            html = html.replace("</body>", bootstrap + "</body>", 1)
        else:
            html = html + bootstrap

        # Fix relative asset refs (e.g. src="../diagram-plot.js" from the
        # old versions/ layout) so they resolve correctly when served from
        # the /content route rather than a versions/ sibling path.
        # diagram-plot.js is slug-local (served by _serve_static from the
        # artifact dir), so the stamp comes from that copy.
        dgplot_v = _mtime_stamp(self.artifact_dir / "diagram-plot.js")
        html = html.replace('src="../diagram-plot.js"', f'src="{base}/assets/{dgplot_v}/diagram-plot.js"')

        self._respond(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def _serve_skill_asset(self, rel: str):
        """Serve shell.js / shell.css / adapter.js — shared, version-stable
        chrome assets that live once in the skill dir, not per-slug."""
        if not self.skill_dir:
            self._respond(404, b"Not found")
            return
        target = (self.skill_dir / rel).resolve()
        try:
            target.relative_to(self.skill_dir.resolve())
        except ValueError:
            self._respond(403, b"Forbidden")
            return
        if not target.exists() or not target.is_file():
            self._respond(404, b"Not found")
            return
        try:
            data = target.read_bytes()
        except OSError:
            self._respond(500, b"Read error")
            return
        self._respond(200, data, _mime(target.suffix),
                      cache_control=_cache_control_for(target.suffix))

    def _serve_versioned_asset(self, name: str):
        """Serve a whitelisted asset from a /assets/<stamp>/<name> URL.

        The stamp segment is a cache key only, never used for resolution.
        diagram-plot.js prefers the slug-local copy (that fork is what the
        live content renders with today; _serve_static serves it for the
        legacy bare path), falling back to the skill-dir copy. The other
        assets are skill-dir chrome.
        """
        candidates = []
        if name == "diagram-plot.js":
            candidates.append(self.artifact_dir / name)
        if self.skill_dir:
            candidates.append(self.skill_dir / name)
        for target in candidates:
            if target.exists() and target.is_file():
                try:
                    data = target.read_bytes()
                except OSError:
                    continue
                self._respond(200, data, _mime(target.suffix),
                              cache_control=_cache_control_for(target.suffix))
                return
        self._respond(404, b"Not found")

    def _v2_post_comments(self, parsed):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            self._respond(400, f'{{"error":"invalid json: {exc}"}}'.encode())
            return

        # V1-compat: whole-store POST (dict with anchors-like values OR v2 shape).
        if isinstance(payload, dict) and (
            "schema_version" in payload or all(isinstance(v, list) for v in payload.values())
        ):
            with _STORE_LOCK:
                store = _coerce_v2(payload)
                self._v2_save(store)
            _bus_append(self.bus_dir, self.slug, {
                "event": "bulk_overwrite",
                "comment_count": sum(len(v) for v in store["anchors"].values()),
            })
            self._respond(200, b'{"ok":true,"mode":"bulk"}', "application/json")
            return

        # V2 single-comment create
        if not isinstance(payload, dict):
            self._respond(400, b'{"error":"expected object"}')
            return
        anchor_id = payload.get("anchor_id") or payload.get("sectionId") or payload.get("nodeId")
        text = (payload.get("text") or "").strip()
        if not anchor_id or not text:
            self._respond(400, b'{"error":"anchor_id and text required"}')
            return

        identity = self._identity()
        author = identity["email"] or "anonymous"
        author_name = identity["name"] or (payload.get("author_name") if identity["authenticated"] else None)

        version = payload.get("version", "v1")
        try:
            with _STORE_LOCK:
                meta = self._read_meta()
                if meta.get("current"):
                    version = payload.get("version") or meta["current"]
                store = self._v2_load()
                comment = {
                    "id": payload.get("id") or _new_id(),
                    "anchor_id": anchor_id,
                    "anchor_label": payload.get("anchor_label") or payload.get("sectionLabel"),
                    "text": text,
                    "author": author,
                    "author_email": identity["email"],
                    "author_name": author_name,
                    "created_at": _now_iso(),
                    "version": version,
                    "status": "open",
                    "response_text": None,
                    "replies": [],
                }
                # Granular sub-anchor selector captured client-side at click
                # time (inner element id / relative CSS path / text quote /
                # click offset). Stored verbatim; size-capped defensively.
                target = payload.get("target")
                if isinstance(target, dict) and len(json.dumps(target)) <= 4096:
                    comment["target"] = target
                store["anchors"].setdefault(anchor_id, []).append(comment)
                self._v2_save(store)
        except OSError as exc:
            self._respond(500, f'{{"error":"write error: {exc}"}}'.encode())
            return

        _bus_append(self.bus_dir, self.slug, {
            "event": "comment_created",
            "comment_id": comment["id"],
            "anchor_id": anchor_id,
            "author": author,
            "version": version,
            "target": comment.get("target"),
        })
        print(f"  POST /api/comments → {comment['id']} by {author} on {anchor_id} ({version})", flush=True)
        self._respond(201, json.dumps(comment, ensure_ascii=False).encode(), "application/json")

    def _v2_put_comment(self, comment_id: str, parsed):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            self._respond(400, f'{{"error":"invalid json: {exc}"}}'.encode())
            return
        if not isinstance(payload, dict):
            self._respond(400, b'{"error":"expected object"}')
            return

        new_status = payload.get("status")
        if new_status is not None:
            new_status = _coerce_status(new_status)
            if new_status not in ("open", "addressed_by_agent", "user_confirmed", "archived"):
                self._respond(400, b'{"error":"invalid status"}')
                return
        identity = self._identity()
        author = identity["email"] or "anonymous"

        with _STORE_LOCK:
            store = self._v2_load()
            found = None
            for anchor_id, items in store["anchors"].items():
                for c in items:
                    if c.get("id") == comment_id:
                        found = (anchor_id, c)
                        break
                if found:
                    break
            if not found:
                self._respond(404, b'{"error":"not found"}')
                return
            anchor_id, c = found
            old_status = c.get("status")
            if new_status:
                c["status"] = new_status
            if "response_text" in payload:
                c["response_text"] = payload["response_text"]
            if "text" in payload:
                c["text"] = (payload["text"] or "").strip()
            # Re-anchoring (manual re-pin or agent migration): a NEW granular
            # target and its provenance. The creation-time record fields are
            # never rewritten; these are additive facts with their own
            # strategy/confidence trail.
            repinned = False
            if isinstance(payload.get("target"), (dict, type(None))) and "target" in payload:
                if payload["target"] is None or len(json.dumps(payload["target"])) <= 4096:
                    c["target"] = payload["target"]
                    repinned = True
            if isinstance(payload.get("reanchor"), dict) and len(json.dumps(payload["reanchor"])) <= 2048:
                c["reanchor"] = payload["reanchor"]
            new_anchor = payload.get("anchor_id")
            if isinstance(new_anchor, str) and new_anchor and new_anchor != anchor_id:
                store["anchors"][anchor_id].remove(c)
                if not store["anchors"][anchor_id]:
                    del store["anchors"][anchor_id]
                store["anchors"].setdefault(new_anchor, []).append(c)
                c["anchor_id"] = new_anchor
                if payload.get("anchor_label"):
                    c["anchor_label"] = payload["anchor_label"]
                anchor_id = new_anchor
                repinned = True
            c["edited_at"] = _now_iso()
            c["edited_by"] = author
            c["edited_by_email"] = identity["email"]
            c["edited_by_name"] = identity["name"] or (payload.get("author_name") if identity["authenticated"] else None)
            self._v2_save(store)

        _bus_append(self.bus_dir, self.slug, {
            "event": "comment_updated",
            "comment_id": comment_id,
            "anchor_id": anchor_id,
            "old_status": old_status,
            "new_status": c.get("status"),
            "author": author,
            **({"repinned": True, "target": c.get("target")} if repinned else {}),
        })
        print(f"  PUT /api/comments/{comment_id} → status={c.get('status')} by {author}", flush=True)
        self._respond(200, json.dumps(c, ensure_ascii=False).encode(), "application/json")

    def _v2_post_reply(self, comment_id: str, parsed):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            self._respond(400, f'{{"error":"invalid json: {exc}"}}'.encode())
            return
        text = (payload.get("text") or "").strip()
        if not text:
            self._respond(400, b'{"error":"text required"}')
            return
        identity = self._identity()
        author = identity["email"] or "anonymous"
        reply = {
            "author": author,
            "author_email": identity["email"],
            "author_name": identity["name"] or (payload.get("author_name") if identity["authenticated"] else None),
            "text": text,
            "ts": _now_iso(),
        }

        with _STORE_LOCK:
            store = self._v2_load()
            found = None
            auto_reopened = False
            for anchor_id, items in store["anchors"].items():
                for c in items:
                    if c.get("id") == comment_id:
                        c.setdefault("replies", []).append(reply)
                        # T9: a USER reply on an agent-addressed comment is
                        # itself the reopen signal — the user shouldn't need
                        # a second action. Agent replies (author "agent:*",
                        # same convention the shell's ball-in-court logic
                        # uses) never auto-reopen.
                        if c.get("status") == "addressed_by_agent" and not author.startswith("agent:"):
                            c["status"] = "open"
                            c["reopened_at"] = _now_iso()
                            c["reopened_by"] = author
                            auto_reopened = True
                        found = (anchor_id, c)
                        break
                if found:
                    break
            if not found:
                self._respond(404, b'{"error":"not found"}')
                return
            self._v2_save(store)

        _bus_append(self.bus_dir, self.slug, {
            "event": "comment_reply",
            "comment_id": comment_id,
            "anchor_id": found[0],
            "author": author,
            **({"auto_reopened": True, "old_status": "addressed_by_agent",
                "new_status": "open"} if auto_reopened else {}),
        })
        if auto_reopened:
            print(f"  POST /api/comments/{comment_id}/reply → user reply auto-reopened (by {author})", flush=True)
        self._respond(200, json.dumps(found[1], ensure_ascii=False).encode(), "application/json")

    def _v2_post_archive(self, comment_id: str, parsed):
        author = self._author(parsed)
        with _STORE_LOCK:
            store = self._v2_load()
            archived = store.setdefault("archived", {})
            moved = None
            for anchor_id, items in list(store["anchors"].items()):
                for c in list(items):
                    if c.get("id") == comment_id:
                        c["status"] = "archived"
                        c["archived_at"] = _now_iso()
                        c["archived_by"] = author
                        archived.setdefault(anchor_id, []).append(c)
                        items.remove(c)
                        if not items:
                            del store["anchors"][anchor_id]
                        moved = (anchor_id, c)
                        break
                if moved:
                    break
            if not moved:
                self._respond(404, b'{"error":"not found"}')
                return
            self._v2_save(store)
        _bus_append(self.bus_dir, self.slug, {
            "event": "comment_archived",
            "comment_id": comment_id,
            "anchor_id": moved[0],
            "author": author,
        })
        self._respond(200, json.dumps(moved[1], ensure_ascii=False).encode(), "application/json")

    def _v2_post_accept(self, comment_id: str, parsed):
        """Accept & archive in one call: status -> user_confirmed, then
        immediately archived. Distinguishes 'user reviewed and accepted'
        from a raw archive of a still-open comment by recording
        accepted_at/accepted_by in addition to archived_at/archived_by.
        """
        author = self._author(parsed)
        with _STORE_LOCK:
            store = self._v2_load()
            archived = store.setdefault("archived", {})
            moved = None
            now = _now_iso()
            for anchor_id, items in list(store["anchors"].items()):
                for c in list(items):
                    if c.get("id") == comment_id:
                        c["status"] = "archived"
                        c["accepted_at"] = now
                        c["accepted_by"] = author
                        c["archived_at"] = now
                        c["archived_by"] = author
                        archived.setdefault(anchor_id, []).append(c)
                        items.remove(c)
                        if not items:
                            del store["anchors"][anchor_id]
                        moved = (anchor_id, c)
                        break
                if moved:
                    break
            if not moved:
                self._respond(404, b'{"error":"not found"}')
                return
            self._v2_save(store)
        _bus_append(self.bus_dir, self.slug, {
            "event": "comment_accepted",
            "comment_id": comment_id,
            "anchor_id": moved[0],
            "author": author,
        })
        print(f"  POST /api/comments/{comment_id}/accept → archived by {author}", flush=True)
        self._respond(200, json.dumps(moved[1], ensure_ascii=False).encode(), "application/json")

    def _v2_post_restore(self, comment_id: str, parsed):
        author = self._author(parsed)
        with _STORE_LOCK:
            store = self._v2_load()
            archived = store.setdefault("archived", {})
            anchors = store.setdefault("anchors", {})
            moved = None
            for anchor_id, items in list(archived.items()):
                for c in list(items):
                    if c.get("id") == comment_id:
                        c["status"] = "open"
                        c.pop("archived_at", None)
                        c.pop("archived_by", None)
                        c["restored_at"] = _now_iso()
                        c["restored_by"] = author
                        anchors.setdefault(anchor_id, []).append(c)
                        items.remove(c)
                        if not items:
                            del archived[anchor_id]
                        moved = (anchor_id, c)
                        break
                if moved:
                    break
            if not moved:
                self._respond(404, b'{"error":"not found"}')
                return
            self._v2_save(store)
        _bus_append(self.bus_dir, self.slug, {
            "event": "comment_restored",
            "comment_id": comment_id,
            "anchor_id": moved[0],
            "author": author,
        })
        self._respond(200, json.dumps(moved[1], ensure_ascii=False).encode(), "application/json")

    # ── F1: Push-to-session routes ───────────────────────────────────
    def _v2_post_push_session(self, parsed):
        """Flag open comments with new activity and emit one session_push.

        This deliberately matches the shell badge's needsPush() contract.
        Returns the exact count and IDs delivered or queued for the session.
        """
        author = self._author(parsed)
        with _STORE_LOCK:
            store = self._v2_load()
            flagged_count = 0
            flagged_ids = []
            now = _now_iso()
            for anchor_id, items in store.get("anchors", {}).items():
                for c in items:
                    if _comment_needs_push(c):
                        c["flagged_for_session"] = True
                        c["flagged_at"] = now
                        c["flagged_by"] = author
                        flagged_count += 1
                        flagged_ids.append(c.get("id"))
            self._v2_save(store)

        _ensure_monitor_offset_baseline(self.bus_dir, self.slug)
        monitors = _active_monitor_leases(self.bus_dir, self.slug)
        monitor_count = len(monitors)
        monitor_owner = _public_monitor_owner(monitors[0] if monitors else None)
        delivery = "active_monitor" if monitor_count else "queued"
        delivery_id = uuid.uuid4().hex[:12]
        _bus_append(self.bus_dir, self.slug, {
            "event": "session_push",
            "delivery_id": delivery_id,
            "delivery": delivery,
            "monitor_count": monitor_count,
            "monitor_owner": monitor_owner,
            "comment_count": flagged_count,
            "comment_ids": flagged_ids,
            "author": author,
        })
        print(f"  POST /api/push-session → {flagged_count} comment(s), {delivery}, monitors={monitor_count}, by {author}", flush=True)
        self._respond(200, json.dumps({
            "ok": True,
            "delivery_id": delivery_id,
            "delivery": delivery,
            "monitor_count": monitor_count,
            "monitor_owner": monitor_owner,
            "flagged_count": flagged_count,
            "comment_ids": flagged_ids,
        }, ensure_ascii=False).encode(), "application/json")

    def _v2_post_push_single(self, comment_id: str, parsed):
        """Flag a single comment with flagged_for_session=true."""
        author = self._author(parsed)
        with _STORE_LOCK:
            store = self._v2_load()
            found = None
            for anchor_id, items in store.get("anchors", {}).items():
                for c in items:
                    if c.get("id") == comment_id:
                        c["flagged_for_session"] = True
                        c["flagged_at"] = _now_iso()
                        c["flagged_by"] = author
                        found = (anchor_id, c)
                        break
                if found:
                    break
            if not found:
                self._respond(404, b'{"error":"not found"}')
                return
            self._v2_save(store)
        _ensure_monitor_offset_baseline(self.bus_dir, self.slug)
        monitors = _active_monitor_leases(self.bus_dir, self.slug)
        monitor_count = len(monitors)
        monitor_owner = _public_monitor_owner(monitors[0] if monitors else None)
        delivery = "active_monitor" if monitor_count else "queued"
        delivery_id = uuid.uuid4().hex[:12]
        _bus_append(self.bus_dir, self.slug, {
            "event": "session_push",
            "delivery_id": delivery_id,
            "delivery": delivery,
            "monitor_count": monitor_count,
            "monitor_owner": monitor_owner,
            "comment_count": 1,
            "comment_ids": [comment_id],
            "anchor_id": found[0],
            "author": author,
        })
        print(f"  POST /api/comments/{comment_id}/push → {delivery}, monitors={monitor_count}, by {author}", flush=True)
        self._respond(200, json.dumps({
            "ok": True,
            "delivery_id": delivery_id,
            "delivery": delivery,
            "monitor_count": monitor_count,
            "monitor_owner": monitor_owner,
            "flagged_count": 1,
            "comment_ids": [comment_id],
        }, ensure_ascii=False).encode(), "application/json")

    def _read_meta(self) -> dict:
        p = self._meta_path()
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    # ── Seen / last-visit tracking ────────────────────────────────────
    def _v2_get_seen(self, parsed):
        """Return the requesting author's last_seen record: per-version
        {ts, whole_hash, section_hashes}. Shell diffs this against the
        current content stamps (from current.meta.json content_stamps) to
        decide which tabs get an ↑NEW indicator.
        """
        author = self._author(parsed)
        with _SEEN_LOCK:
            data = _load_seen(self.artifact_dir)
        record = data.get(_author_key(author), {})
        self._respond(200, json.dumps({"author": author, "seen": record}, ensure_ascii=False).encode(), "application/json")

    def _v2_get_identity(self, parsed):
        identity = self._identity()
        self._respond(200, json.dumps(identity, ensure_ascii=False).encode(), "application/json")

    def _v2_get_session_monitor(self, parsed):
        monitors = _active_monitor_leases(self.bus_dir, self.slug)
        monitor_count = len(monitors)
        self._respond(200, json.dumps({
            "active": monitor_count > 0,
            "monitor_count": monitor_count,
            "delivery": "active_monitor" if monitor_count else "queued",
            "owner": _public_monitor_owner(monitors[0] if monitors else None),
        }, ensure_ascii=False).encode(), "application/json")

    def _v2_get_read_state(self, parsed):
        """Return the requesting author's per-comment read records:
        {comment_id: {ts, sig}}. The shell compares each stored sig against
        the live comment's activity sig to derive unread / NEW-reply state.
        """
        author = self._author(parsed)
        with _READ_LOCK:
            data = _load_read_state(self.artifact_dir)
        record = data.get(_author_key(author), {})
        self._respond(200, json.dumps({"author": author, "read": record}, ensure_ascii=False).encode(), "application/json")

    def _v2_post_read_state(self, parsed):
        """Record that `author` has read the given comments at the given
        activity sigs. Body: {"items": [{"id": "<comment_id>", "sig": "<s>"}]}.
        Idempotent merge; no bus event (viewer bookkeeping, not comment data).
        """
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = {}
        items = payload.get("items")
        if not isinstance(items, list):
            self._respond(400, b'{"error":"items list required"}')
            return
        author = self._author(parsed)
        now = _now_iso()
        count = 0
        with _READ_LOCK:
            data = _load_read_state(self.artifact_dir)
            record = data.setdefault(_author_key(author), {})
            for it in items:
                if not isinstance(it, dict):
                    continue
                cid = it.get("id")
                if not cid:
                    continue
                record[str(cid)] = {"ts": now, "sig": str(it.get("sig") or "")}
                count += 1
            _save_read_state(self.artifact_dir, data)
        self._respond(200, json.dumps({"ok": True, "author": author, "count": count}, ensure_ascii=False).encode(), "application/json")

    def _v2_post_seen(self, parsed):
        """Record that `author` has now seen `version` at the current
        content stamps. Body: {"version": "v4-6"}. Stamps are read live
        from current.meta.json.content_stamps (server-computed at publish
        time) rather than trusted from the client, so a stale/malicious
        client can't fake 'caught up' state.
        """
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = {}
        author = self._author(parsed)
        version = payload.get("version")
        if not version:
            self._respond(400, b'{"error":"version required"}')
            return

        meta = self._read_meta()
        stamps = (meta.get("content_stamps") or {}).get(version, {})

        with _SEEN_LOCK:
            data = _load_seen(self.artifact_dir)
            key = _author_key(author)
            data.setdefault(key, {})
            data[key][version] = {
                "ts": _now_iso(),
                "whole_hash": stamps.get("whole"),
                "section_hashes": stamps.get("sections", {}),
            }
            _save_seen(self.artifact_dir, data)

        _bus_append(self.bus_dir, self.slug, {
            "event": "seen_updated",
            "author": author,
            "version": version,
        })
        self._respond(200, json.dumps({"ok": True, "author": author, "version": version}, ensure_ascii=False).encode(), "application/json")

    # ── Static fallthrough ──────────────────────────────────────────
    def _serve_static(self, url_path):
        rel = url_path.lstrip("/") or self._default_file()
        target = (self.artifact_dir / rel).resolve()
        try:
            target.relative_to(self.artifact_dir.resolve())
        except ValueError:
            self._respond(403, b"Forbidden")
            return
        # Public-exposure gate: for v2-mode slugs that have been migrated to
        # the universal-shell layout (content/ dir present), the old
        # versions/ tree — including archive-baked/ — holds chrome-
        # contaminated baked HTML that nothing in the new shell UI links to.
        # Deny it outright rather than let the generic static fallthrough
        # serve it to anyone hitting the URL directly. Checked against the
        # *resolved* target (post ../ normalization) so this can't be routed
        # around by traversal tricks. Legacy slugs without content/ (e.g.
        # prem-fin) are untouched — _v2_serve_root still reads versions/
        # directly for them via ?v=, and there's no /content alternative yet.
        if self.v2_mode and self._has_content_dir():
            versions_dir = (self.artifact_dir / "versions").resolve()
            try:
                target.relative_to(versions_dir)
                self._respond(404, b"Not found")
                return
            except ValueError:
                pass
        if not target.exists() or not target.is_file():
            self._respond(404, b"Not found")
            return
        mime = _mime(target.suffix)
        try:
            data = target.read_bytes()
        except OSError:
            self._respond(500, b"Read error")
            return
        self._respond(200, data, content_type=mime,
                      cache_control=_cache_control_for(target.suffix))

    def _default_file(self):
        return self.artifact_file

    # ── Helpers ───────────────────────────────────────────────────────
    def _respond(self, code: int, body: bytes, content_type: str = "application/json",
                 cache_control: str = "no-cache"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        # Suppress default access log for static files to reduce noise
        pass


# ────────────────────────────────────────────────────────────────────────────
# Handler factory
# ────────────────────────────────────────────────────────────────────────────
def make_handler(
    artifact_dir: Path,
    artifact_file: str = "current.html",
    public_base_path: str = "",
    slug: str = "",
    bus_dir: Path | None = None,
    v2_mode: bool = False,
    skill_dir: Path | None = None,
) -> type:
    class BoundHandler(AnnotateHandler):
        pass
    BoundHandler.artifact_dir = artifact_dir
    BoundHandler.artifact_file = artifact_file
    BoundHandler.public_base_path = public_base_path
    BoundHandler.slug = slug
    BoundHandler.bus_dir = bus_dir
    BoundHandler.v2_mode = v2_mode
    BoundHandler.skill_dir = skill_dir
    return BoundHandler


def main():
    parser = argparse.ArgumentParser(
        description="annotate sync server — serve HTML artifact and persist comments to disk"
    )
    parser.add_argument(
        "artifact",
        nargs="?",
        help="Path to the annotatable .html file (v1 mode) OR omitted when --slug-dir is set",
    )
    parser.add_argument(
        "--slug-dir",
        type=str,
        default="",
        help="V2 mode: path to <slug>/ directory containing current.html, comments.json, versions/, etc.",
    )
    parser.add_argument(
        "--slug",
        type=str,
        default="",
        help="V2 mode: slug name (used for NDJSON bus filename). Defaults to dirname.",
    )
    parser.add_argument(
        "--bus-dir",
        type=str,
        default="",
        help="V2 mode: directory for the NDJSON event bus",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port to listen on (default: 8765, auto-increments if busy)",
    )
    parser.add_argument(
        "--public-base-path",
        type=str,
        default="",
        help='Public URL prefix to strip from incoming requests (e.g. "/schema-v4-2"). '
             "Default: empty (no stripping).",
    )
    args = parser.parse_args()

    # Normalize public_base_path: ensure leading slash, no trailing slash
    public_base_path = (args.public_base_path or "").strip()
    if public_base_path:
        if not public_base_path.startswith("/"):
            public_base_path = "/" + public_base_path
        public_base_path = public_base_path.rstrip("/")

    if args.slug_dir:
        # V2 mode
        slug_dir = Path(args.slug_dir).resolve()
        if not slug_dir.exists() or not slug_dir.is_dir():
            print(f"Error: --slug-dir not found or not a directory: {slug_dir}", file=sys.stderr)
            sys.exit(1)
        slug = args.slug or slug_dir.name
        bus_dir = Path(args.bus_dir).resolve() if args.bus_dir else BUS_ROOT / "default"
        skill_dir = WEB_DIR
        port = find_free_port(args.port)
        handler = make_handler(
            artifact_dir=slug_dir,
            artifact_file="current.html",
            public_base_path=public_base_path,
            slug=slug,
            bus_dir=bus_dir,
            v2_mode=True,
            skill_dir=skill_dir,
        )
        server = http.server.ThreadingHTTPServer(("localhost", port), handler)
        if public_base_path:
            url = f"http://localhost:{port}{public_base_path}/"
        else:
            url = f"http://localhost:{port}/"
        print()
        print("  annotate sync server (V2)")
        print("  ─────────────────────────────────────────────")
        print(f"  Open in browser:   {url}")
        print(f"  Slug dir:          {slug_dir}")
        print(f"  Slug:              {slug}")
        print(f"  Comments file:     {slug_dir / 'comments.json'}")
        print(f"  Meta file:         {slug_dir / 'current.meta.json'}")
        print(f"  NDJSON bus:        {bus_dir / (slug + '.ndjson')}")
        if public_base_path:
            print(f"  Public base path:  {public_base_path}")
        print("  ─────────────────────────────────────────────")
        print()
        print("  Ctrl-C to stop. POST/PUT log appears below:")
        print()
    else:
        # V1 mode (backward compat)
        if not args.artifact:
            print("Error: must pass <artifact.html> in v1 mode or --slug-dir <dir> in v2 mode", file=sys.stderr)
            sys.exit(1)
        artifact_path = Path(args.artifact).resolve()
        if not artifact_path.exists():
            print(f"Error: artifact not found: {artifact_path}", file=sys.stderr)
            sys.exit(1)
        if not artifact_path.is_file():
            print(f"Error: artifact is not a file: {artifact_path}", file=sys.stderr)
            sys.exit(1)
        artifact_dir = artifact_path.parent
        artifact_file = artifact_path.name
        doc_id = artifact_path.stem
        comments_path = artifact_dir / (doc_id + ".comments.json")
        port = find_free_port(args.port)
        handler = make_handler(
            artifact_dir=artifact_dir,
            artifact_file=artifact_file,
            public_base_path=public_base_path,
            v2_mode=False,
        )
        server = http.server.HTTPServer(("localhost", port), handler)
        if public_base_path:
            url = f"http://localhost:{port}{public_base_path}/{artifact_file}"
        else:
            url = f"http://localhost:{port}/{artifact_file}"
        print()
        print("  annotate sync server (V1 compat)")
        print("  ─────────────────────────────────────────────")
        print(f"  Open in browser:  {url}")
        print(f"  Comments file:    {comments_path}")
        print(f"  Serving dir:      {artifact_dir}")
        print(f"  Doc ID:           {doc_id}")
        if public_base_path:
            print(f"  Public base path: {public_base_path}")
        print("  ─────────────────────────────────────────────")
        print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")


if __name__ == "__main__":
    main()
