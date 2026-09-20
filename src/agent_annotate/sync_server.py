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
        [--bus-dir ~/.claude/annotate-bus/<project>]

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
                "replies": [ { "author": str, "text": str, "ts": iso } ],
                "decision_request": { "prompt": str, "options": [str, ...] } | null,
                "decision": { "verdict": "accept"|"reject"|"changes"|"comment",
                              # "changes" = Request changes (text required);
                              # "comment" = a remark that does NOT answer the
                              # card (text required); the card stays undecided
                              "text": str | null, "ts": iso, "by": str } | null,
                "decision_history": [ { "verdict": ..., "text": ..., "ts": ..., "by": ... }, ... ]
                                     # prior decisions, oldest first; a comment
                                     # gains an entry here each time a NEW
                                     # decision overwrites an existing one
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
      PUT  /api/comments/<id>               → set status / response_text / decision_request
      POST /api/comments/<id>/reply         → append a thread reply
      POST /api/comments/<id>/archive       → move comment to archived
      POST /api/comments/<id>/decision      → answer a posed decision_request
                                              (accept/reject/changes), or remark on
                                              it (comment); pushes to session.
                                              Re-posting on an already-decided
                                              comment REVISES it: the prior
                                              decision moves to decision_history,
                                              and the reply + both bus events
                                              carry the reversal explicitly.
      POST /api/comments                    → v1-compatible whole-store POST OR
                                              v2-compatible single-comment create
                                              (may carry decision_request; v2.19)
      GET  /api/capabilities                → {"version","batch","rounds","decision_schema",
                                               "verdicts"}
                                              (v2.19; 404 on older servers → legacy chrome)
      POST /api/comments/batch              → {"items":[...], "idempotency":"anchor"|null}
                                              creates/updates many decision cards at once
      POST /api/rounds/submit               → close a review round: clears
                                              decision.round_pending on every deferred
                                              verdict and emits ONE session_push{round:true}
      POST /api/rounds/discard              → clear round_pending flags without pushing
      *                                     → serve static files from <slug-dir>

    Optional request header X-Annotate-Session: <id> — when present, every bus
    event the request emits carries session_id (agents/CLIs send it, browsers
    never do).

    NDJSON bus: every comment event appends to <bus-dir>/<slug>.ndjson.
    Author extraction reads Cf-Access-Authenticated-User-Email header.

    Auto-migration: a v1 store ({nodeId: [comment]}) is wrapped to v2 shape on
    first write — original is backed up next to comments.json.
"""

import argparse
import fcntl
import hashlib
import http.server
import ipaddress
import json
import os
import re
import socket
import sys
import threading
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
            # Match HTTPServer.allow_reuse_address so a coordinated same-port
            # restart is not mistaken for a collision while old connections
            # remain in TIME_WAIT. An active listener still makes bind fail.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
    """Integer-mtime cache-buster for an asset URL. Falls back to a CONSTANT
    ('0') when the file can't be statted: a clock-based fallback minted a new
    stamp every second, so any document referencing a missing asset came back
    byte-different on every request and HTTP caching was defeated entirely."""
    if path is not None:
        try:
            return str(int(Path(path).stat().st_mtime))
        except OSError:
            pass
    return "0"


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


# ── decision_request validation (shared by POST create, PUT, batch) ──────
# v2.19 schema (all optional except prompt):
#   prompt, context, recommendation, options (strings or {id,label,
#   consequence,style}), consequences {accept,reject}, evidence [{label,
#   anchor}], impact low|medium|high, blocking bool, requested_at (server-set).
# The serialized cap is enforced HERE and surfaced as HTTP 413 — the old
# 2048-byte check silently dropped an oversized request and still returned
# 200, which left agents believing a card had been posed when it had not.
_DECISION_REQUEST_CAP = 8192
_DECISION_IMPACTS = ("low", "medium", "high")


class DecisionRequestError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _normalize_decision_request(dr: Any) -> dict:
    """Validate an incoming decision_request and stamp requested_at.

    Raises DecisionRequestError(status=400) on a malformed shape and
    (status=413) when the serialized form exceeds _DECISION_REQUEST_CAP.
    Returns a fresh dict (never the caller's object).
    """
    if not isinstance(dr, dict):
        raise DecisionRequestError("decision_request must be an object")
    out = dict(dr)
    prompt = out.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise DecisionRequestError("decision_request.prompt is required")
    out["prompt"] = prompt.strip()
    if "context" in out and out["context"] is not None and not isinstance(out["context"], str):
        raise DecisionRequestError("decision_request.context must be a string")
    if "options" in out and out["options"] is not None:
        opts = out["options"]
        if not isinstance(opts, list):
            raise DecisionRequestError("decision_request.options must be a list")
        for o in opts:
            if isinstance(o, str):
                continue
            if isinstance(o, dict) and isinstance(o.get("id"), str) and o["id"]:
                continue
            raise DecisionRequestError("decision_request.options entries must be strings or {id,...} objects")
    if "consequences" in out and out["consequences"] is not None and not isinstance(out["consequences"], dict):
        raise DecisionRequestError("decision_request.consequences must be an object")
    if "evidence" in out and out["evidence"] is not None:
        ev = out["evidence"]
        if not isinstance(ev, list) or any(not isinstance(e, dict) for e in ev):
            raise DecisionRequestError("decision_request.evidence must be a list of {label, anchor}")
    if "impact" in out and out["impact"] is not None and out["impact"] not in _DECISION_IMPACTS:
        raise DecisionRequestError("decision_request.impact must be low|medium|high")
    if "blocking" in out and out["blocking"] is not None and not isinstance(out["blocking"], bool):
        raise DecisionRequestError("decision_request.blocking must be a boolean")
    out["requested_at"] = _now_iso()
    try:
        size = len(json.dumps(out, ensure_ascii=False).encode("utf-8"))
    except (TypeError, ValueError):
        raise DecisionRequestError("decision_request is not JSON-serializable")
    if size > _DECISION_REQUEST_CAP:
        raise DecisionRequestError(
            f"decision_request too large: {size} bytes > {_DECISION_REQUEST_CAP}", status=413)
    return out


def _decision_requested_event(comment: dict, author: str) -> dict:
    dr = comment.get("decision_request") or {}
    opts = dr.get("options")
    return {
        "event": "decision_requested",
        "comment_id": comment.get("id"),
        "anchor_id": comment.get("anchor_id"),
        "has_context": bool(dr.get("context")),
        "options_n": len(opts) if isinstance(opts, list) else 3,
        "prompt_len": len(dr.get("prompt") or ""),
        "by": author,
    }


def _decision_latency_s(comment: dict, now_iso: str) -> float | None:
    """Seconds between decision_request.requested_at and the verdict; None
    when the request predates v2.19 and carries no requested_at."""
    requested = _iso_timestamp((comment.get("decision_request") or {}).get("requested_at"))
    if not requested:
        return None
    return round(max(0.0, _iso_timestamp(now_iso) - requested), 1)


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
    skill_dir: Path | None = None  # packaged web asset directory (shell.*, adapter.js)
    local_author: str | None = None
    local_author_name: str | None = None

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

    def _is_direct_loopback_request(self) -> bool:
        """Accept local identity only on a direct loopback URL.

        Reverse proxies on this host can also connect from loopback, so the
        peer address alone is insufficient. Requiring a localhost/loopback
        Host keeps Cloudflare and Tailscale routes on their normal auth path.
        """
        try:
            peer_is_loopback = ipaddress.ip_address(self.client_address[0]).is_loopback
        except ValueError:
            return False
        if not peer_is_loopback:
            return False

        host_header = (self.headers.get("Host") or "").strip()
        try:
            hostname = urllib.parse.urlsplit("//" + host_header).hostname
        except ValueError:
            return False
        if not hostname:
            return False
        if hostname.lower() == "localhost":
            return True
        try:
            return ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            return False

    def _identity(self) -> dict:
        """Return identity supplied by OAuth or the configured local fallback.

        Client query parameters and JSON bodies are deliberately excluded:
        they are display input, not authentication evidence. The fallback is
        available only to direct loopback URLs and never to public/proxy Hosts.
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
        if not email and self.local_author and self._is_direct_loopback_request():
            email = self.local_author
            name = self.local_author_name or name
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
            if route_path == "/api/capabilities":
                return self._v2_get_capabilities(parsed)
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
            if route_path == "/api/comments/batch":
                return self._v2_post_comments_batch(parsed)
            if route_path == "/api/rounds/submit":
                return self._v2_post_rounds_submit(parsed)
            if route_path == "/api/rounds/discard":
                return self._v2_post_rounds_discard(parsed)
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
            if route_path.startswith("/api/comments/") and route_path.endswith("/decision"):
                cid = route_path[len("/api/comments/"):-len("/decision")]
                return self._v2_post_decision(cid, parsed)
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
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept, Cf-Access-Authenticated-User-Email, X-Annotate-Session")
        self.end_headers()

    # ── v2.19: agent session attribution ─────────────────────────────
    def _session_fields(self) -> dict:
        """{"session_id": ...} when the caller sent X-Annotate-Session, else {}.
        Spread into every bus event a request emits so agent-authored events
        can be attributed to the session that produced them. Browsers never
        send the header, so reviewer events are unaffected."""
        sid = (self.headers.get("X-Annotate-Session") or "").strip()
        return {"session_id": sid} if sid else {}

    def _read_json_body(self):
        """Parse the request body as JSON. Returns (payload, None) or
        (None, error_bytes) after having ALREADY responded 400."""
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(body) if body else {}, None
        except json.JSONDecodeError as exc:
            self._respond(400, json.dumps({"error": f"invalid json: {exc}"}).encode())
            return None, b"bad"

    def _v2_get_capabilities(self, parsed):
        self._respond(200, json.dumps({
            "version": "2.19",
            "batch": True,
            "rounds": True,
            "decision_schema": 2,
            "decision_request_cap": _DECISION_REQUEST_CAP,
            # D2: the verdicts a current chrome should OFFER. A chrome that
            # does not find "changes" here renders the pre-D2 "Comment"
            # button; the server still accepts that verdict either way.
            "verdicts": list(self._DECISION_VERDICTS_OFFERED),
        }).encode(), "application/json")

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
            existing = (meta.get("content_stamps") or {}).get(version)
            mtime = content_path.stat().st_mtime
            if existing and existing.get("_mtime") == mtime:
                return  # up to date
            computed = compute_content_stamps(html)
            computed["_mtime"] = mtime
            try:
                self._merge_content_stamp(version, computed)
            except OSError:
                pass  # best-effort; ↑NEW detection degrades gracefully, not fatal

    def _merge_content_stamp(self, version: str, computed: dict) -> None:
        """Persist one content stamp without clobbering a concurrent writer.

        current.meta.json is not owned by this server: the CLI rewrites it too
        (`publish-version` swaps `current`). Reading the whole document,
        mutating it, and writing it back would race that — a request that read
        the meta before a version swap would write back the OLD `current`,
        silently reverting the page and making it appear to change on every
        reload. Re-read and write inside an exclusive file lock, and touch only
        our own key, so nothing this server does can revert someone else's
        edit. The window still needs the CLI to take the same lock to close
        completely; this removes the long read-to-write gap that made it easy
        to hit.
        """
        path = self._meta_path()
        lock_path = path.with_suffix(".json.lock")
        with open(lock_path, "a+") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                fresh = self._read_meta()
                fresh.setdefault("content_stamps", {})[version] = computed
                _atomic_write_json(path, fresh)
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

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

        # Resolve the relative diagram-plot.js ref (src="../diagram-plot.js"
        # from the old versions/ layout). It is served by
        # _serve_versioned_asset, which prefers the slug-local copy and falls
        # back to the skill dir. When NEITHER dir has the file the tag can only
        # 404, and re-stamping a missing asset used to pull the stamp from the
        # clock — making the whole document byte-different on every request.
        # Strip the tag in that case; otherwise stamp it from the copy that
        # will actually be served.
        dgplot_local = self.artifact_dir / "diagram-plot.js"
        dgplot_skill = (self.skill_dir / "diagram-plot.js") if self.skill_dir else None
        dgplot = dgplot_local if dgplot_local.exists() else (
            dgplot_skill if (dgplot_skill and dgplot_skill.exists()) else None)
        if dgplot is not None:
            html = html.replace(
                'src="../diagram-plot.js"',
                f'src="{base}/assets/{_mtime_stamp(dgplot)}/diagram-plot.js"')
        else:
            html = html.replace('<script src="../diagram-plot.js"></script>', "")

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

        try:
            with _STORE_LOCK:
                meta = self._read_meta()
                store = self._v2_load()
                comment = self._new_comment_from_payload(payload, identity, meta)
                store["anchors"].setdefault(anchor_id, []).append(comment)
                self._v2_save(store)
        except DecisionRequestError as exc:
            self._respond(exc.status, json.dumps({"error": str(exc)}).encode())
            return
        except OSError as exc:
            self._respond(500, f'{{"error":"write error: {exc}"}}'.encode())
            return

        version = comment["version"]
        session = self._session_fields()
        _bus_append(self.bus_dir, self.slug, {
            "event": "comment_created",
            "comment_id": comment["id"],
            "anchor_id": anchor_id,
            "author": author,
            "version": version,
            "target": comment.get("target"),
            **({"decision_requested": True} if comment.get("decision_request") else {}),
            **session,
        })
        if comment.get("decision_request"):
            _bus_append(self.bus_dir, self.slug, {**_decision_requested_event(comment, author), **session})
        print(f"  POST /api/comments → {comment['id']} by {author} on {anchor_id} ({version})"
              + (" [decision card]" if comment.get("decision_request") else ""), flush=True)
        self._respond(201, json.dumps(comment, ensure_ascii=False).encode(), "application/json")

    def _new_comment_from_payload(self, payload: dict, identity: dict, meta: dict) -> dict:
        """Build a fresh v2 comment from a create payload (single or batch).

        Caller validates anchor_id/text and holds _STORE_LOCK. Raises
        DecisionRequestError (400/413) when the payload's decision_request is
        malformed or oversized — nothing is written in that case.
        """
        anchor_id = payload.get("anchor_id") or payload.get("sectionId") or payload.get("nodeId")
        author = identity["email"] or "anonymous"
        author_name = identity["name"] or (payload.get("author_name") if identity["authenticated"] else None)
        version = payload.get("version", "v1")
        if meta.get("current"):
            version = payload.get("version") or meta["current"]
        comment = {
            "id": payload.get("id") or _new_id(),
            "anchor_id": anchor_id,
            "anchor_label": payload.get("anchor_label") or payload.get("sectionLabel"),
            "text": (payload.get("text") or "").strip(),
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
        # v2.19: a card can be posed in the same call that creates the
        # comment (previously a mandatory second PUT). Same validation as PUT.
        if payload.get("decision_request") is not None:
            comment["decision_request"] = _normalize_decision_request(payload["decision_request"])
        return comment

    def _v2_post_comments_batch(self, parsed):
        """POST /api/comments/batch — create (or idempotently update) many
        comments under ONE store lock.

        Body: {"items": [{anchor_id, text, version?, decision_request?,
                          anchor_label?, target?}, ...],
               "idempotency": "anchor" | null}
        With idempotency == "anchor", an existing non-archived comment by the
        SAME author on the SAME anchor_id that already carries a
        decision_request is updated in place (text + decision_request) rather
        than duplicated — so an agent can re-run `cli.py ask` safely.
        Validation is all-or-nothing: a bad item (400/413) rejects the whole
        batch before anything is written.
        """
        payload, err = self._read_json_body()
        if err:
            return
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            self._respond(400, b'{"error":"items list required"}')
            return
        items = payload["items"]
        if not items:
            self._respond(400, b'{"error":"items must not be empty"}')
            return
        if len(items) > 200:
            self._respond(413, b'{"error":"too many items (max 200)"}')
            return
        idempotency = payload.get("idempotency")
        if idempotency not in (None, "anchor"):
            self._respond(400, b'{"error":"idempotency must be \\"anchor\\" or null"}')
            return
        for i, it in enumerate(items):
            if not isinstance(it, dict):
                self._respond(400, json.dumps({"error": f"items[{i}] must be an object"}).encode())
                return
            aid = it.get("anchor_id") or it.get("sectionId") or it.get("nodeId")
            if not aid or not (it.get("text") or "").strip():
                self._respond(400, json.dumps({"error": f"items[{i}]: anchor_id and text required"}).encode())
                return

        identity = self._identity()
        author = identity["email"] or "anonymous"
        created_events = []
        ids = []
        created = 0
        updated = 0
        try:
            with _STORE_LOCK:
                meta = self._read_meta()
                store = self._v2_load()
                # Validate everything first so a 413 on item 3 never leaves
                # items 1-2 half-committed.
                built = []
                for it in items:
                    built.append(self._new_comment_from_payload(it, identity, meta))
                now = _now_iso()
                for it, fresh in zip(items, built):
                    aid = fresh["anchor_id"]
                    existing = None
                    if idempotency == "anchor" and fresh.get("decision_request"):
                        for c in store["anchors"].get(aid, []):
                            if (c.get("status") != "archived" and c.get("author") == author
                                    and c.get("decision_request")):
                                existing = c
                                break
                    if existing is not None:
                        existing["text"] = fresh["text"]
                        existing["decision_request"] = fresh["decision_request"]
                        if fresh.get("anchor_label"):
                            existing["anchor_label"] = fresh["anchor_label"]
                        existing["edited_at"] = now
                        existing["edited_by"] = author
                        existing["edited_by_email"] = identity["email"]
                        existing["edited_by_name"] = fresh.get("author_name")
                        updated += 1
                        ids.append(existing["id"])
                        created_events.append(("comment_updated", existing))
                    else:
                        store["anchors"].setdefault(aid, []).append(fresh)
                        created += 1
                        ids.append(fresh["id"])
                        created_events.append(("comment_created", fresh))
                self._v2_save(store)
        except DecisionRequestError as exc:
            self._respond(exc.status, json.dumps({"error": str(exc)}).encode())
            return
        except OSError as exc:
            self._respond(500, f'{{"error":"write error: {exc}"}}'.encode())
            return

        session = self._session_fields()
        for kind, c in created_events:
            ev = {
                "event": kind,
                "comment_id": c["id"],
                "anchor_id": c["anchor_id"],
                "author": author,
                "version": c.get("version"),
                "batch": True,
                **session,
            }
            if kind == "comment_created":
                ev["target"] = c.get("target")
            else:
                ev["old_status"] = c.get("status")
                ev["new_status"] = c.get("status")
            if c.get("decision_request"):
                ev["decision_requested"] = True
            _bus_append(self.bus_dir, self.slug, ev)
            if c.get("decision_request"):
                _bus_append(self.bus_dir, self.slug, {**_decision_requested_event(c, author), **session})
        _bus_append(self.bus_dir, self.slug, {
            "event": "comments_seeded",
            "comment_ids": ids,
            "created": created,
            "updated": updated,
            "by": author,
            **session,
        })
        print(f"  POST /api/comments/batch → created={created} updated={updated} by {author}", flush=True)
        self._respond(200, json.dumps({
            "ids": ids, "created": created, "updated": updated,
        }, ensure_ascii=False).encode(), "application/json")

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
            # decision_request: an agent posing a one-click accept/reject/
            # comment question on this card. Explicit null clears it (e.g.
            # the agent withdraws the question). v2.19: validated by the
            # shared normalizer (same as POST create/batch); an oversized
            # or malformed request is REJECTED (413/400) instead of being
            # silently dropped with a 200.
            decision_posed = False
            if "decision_request" in payload:
                dr = payload["decision_request"]
                if dr is None:
                    c.pop("decision_request", None)
                else:
                    try:
                        c["decision_request"] = _normalize_decision_request(dr)
                    except DecisionRequestError as exc:
                        self._respond(exc.status, json.dumps({"error": str(exc)}).encode())
                        return
                    decision_posed = True
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

        session = self._session_fields()
        _bus_append(self.bus_dir, self.slug, {
            "event": "comment_updated",
            "comment_id": comment_id,
            "anchor_id": anchor_id,
            "old_status": old_status,
            "new_status": c.get("status"),
            "author": author,
            **({"repinned": True, "target": c.get("target")} if repinned else {}),
            **({"decision_requested": True} if decision_posed else {}),
            **session,
        })
        if decision_posed:
            _bus_append(self.bus_dir, self.slug, {**_decision_requested_event(c, author), **session})
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
            **self._session_fields(),
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
            **self._session_fields(),
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
            **self._session_fields(),
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
            **self._session_fields(),
        })
        self._respond(200, json.dumps(moved[1], ensure_ascii=False).encode(), "application/json")

    # ── F1: Push-to-session routes ───────────────────────────────────
    def _compute_delivery(self) -> dict:
        """Monitor-lease/delivery mechanics shared by every push path (bulk,
        single, and decision). Callers append their own bus event with these
        fields spread in, then return the same dict (spread again) as the
        delivery portion of their HTTP response — keeps the wire contract
        (delivery/monitor_count/monitor_owner/delivery_id) identical across
        all three routes without duplicating the lease lookup three times.
        """
        _ensure_monitor_offset_baseline(self.bus_dir, self.slug)
        monitors = _active_monitor_leases(self.bus_dir, self.slug)
        monitor_count = len(monitors)
        monitor_owner = _public_monitor_owner(monitors[0] if monitors else None)
        delivery = "active_monitor" if monitor_count else "queued"
        return {
            "delivery": delivery,
            "monitor_count": monitor_count,
            "monitor_owner": monitor_owner,
            "delivery_id": uuid.uuid4().hex[:12],
        }

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

        delivery = self._compute_delivery()
        _bus_append(self.bus_dir, self.slug, {
            "event": "session_push",
            **delivery,
            "comment_count": flagged_count,
            "comment_ids": flagged_ids,
            "author": author,
        })
        print(f"  POST /api/push-session → {flagged_count} comment(s), {delivery['delivery']}, monitors={delivery['monitor_count']}, by {author}", flush=True)
        self._respond(200, json.dumps({
            "ok": True,
            **delivery,
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
                        # v2.19 "Send now": a deferred verdict pushed on its
                        # own leaves the pending round.
                        if isinstance(c.get("decision"), dict):
                            c["decision"].pop("round_pending", None)
                        found = (anchor_id, c)
                        break
                if found:
                    break
            if not found:
                self._respond(404, b'{"error":"not found"}')
                return
            self._v2_save(store)
        delivery = self._compute_delivery()
        _bus_append(self.bus_dir, self.slug, {
            "event": "session_push",
            **delivery,
            "comment_count": 1,
            "comment_ids": [comment_id],
            "anchor_id": found[0],
            "author": author,
        })
        print(f"  POST /api/comments/{comment_id}/push → {delivery['delivery']}, monitors={delivery['monitor_count']}, by {author}", flush=True)
        self._respond(200, json.dumps({
            "ok": True,
            **delivery,
            "flagged_count": 1,
            "comment_ids": [comment_id],
        }, ensure_ascii=False).encode(), "application/json")

    # D2 made "changes" (Request changes) the third verdict. D3 brings
    # "comment" back beside it as a fourth, because the two are not the same
    # act: "changes" answers the card and instructs, "comment" only remarks
    # on it and leaves it open. A reviewer with no Comment button posted
    # remarks as thread replies, where they were easy to miss.
    _DECISION_VERDICTS = ("accept", "reject", "changes", "comment", "select")
    # The advertised set: what a current chrome should render as buttons.
    # "select" is not a button — it is what a click on an option with a
    # custom id posts. A chrome that does not find it here posts `comment`
    # for those clicks, as it did before D3.
    _DECISION_VERDICTS_OFFERED = ("accept", "reject", "changes", "comment", "select")
    # Verdicts that ANSWER a card. A card whose only verdict is "comment" is
    # still undecided: it keeps its buttons in the chrome, and a round
    # reports it in undecided_ids.
    _DECISION_ANSWERS = ("accept", "reject", "changes", "select")
    # Both text verdicts leave the card open: the agent still owes an answer.
    _DECISION_STATUS_MAP = {"accept": "user_confirmed", "reject": "open",
                            "changes": "open", "comment": "open",
                            "select": "open"}
    _DECISION_REPLY_TEXT = {"accept": "✓ Accepted", "reject": "✗ Rejected"}
    # Verdicts whose reply text IS the reviewer's note (so the note is
    # mandatory). "changes" prefixes it; "comment" never did.
    _DECISION_TEXT_VERDICTS = ("changes", "comment", "select")
    _DECISION_CHANGES_PREFIX = "↻ Changes requested: "
    # D3: the in-thread reply a comment verdict writes. Pre-D3 it was the
    # bare note, indistinguishable from an ordinary reply — the very thing
    # that made these remarks easy to miss.
    _DECISION_COMMENT_PREFIX = "💬 Comment: "
    # D3: the reviewer picked one of the card's own options. `text` is the
    # option's label, plus any note after a blank line.
    _DECISION_SELECT_PREFIX = "☑ Selected: "
    # Prior-verdict label used in revision reply text ("was ✗ Rejected"). Kept
    # distinct from _DECISION_REPLY_TEXT (which has no text-verdict entry)
    # since a revision's PRIOR verdict can be any of the four.
    _DECISION_PRIOR_LABEL = {"accept": "✓ Accepted", "reject": "✗ Rejected",
                             "changes": "↻ Changes requested", "comment": "Commented",
                             "select": "☑ Selected"}

    @classmethod
    def _is_answered(cls, decision) -> bool:
        """True when this decision actually answers its card (not a comment)."""
        return bool(isinstance(decision, dict)
                    and decision.get("verdict") in cls._DECISION_ANSWERS)

    def _v2_post_decision(self, comment_id: str, parsed):
        """Resolve a one-click decision_request: accept / reject / changes,
        or remark on it without answering: comment.

        Sets c["decision"], appends a thread reply so the agent sees the
        verdict in-thread, transitions status, and performs the same
        monitor-lease/push mechanics as a single-comment push (the reviewer
        never has to hit a separate "Push to session" button for this).

        REVISION (user-reported incident: clicked Reject by mistake with no
        way to reverse it): if the comment already carries a c["decision"]
        when this fires, that prior decision is archived to
        c["decision_history"] before being overwritten, and the reply text
        plus both bus events explicitly mark the correction (revised=True,
        prior_verdict=<old verdict>) so an agent watching the bus sees an
        explicit reversal, not an ordinary first vote. A comment's FIRST
        decision (the common case) is completely unaffected by this branch —
        behavior there is byte-identical to before.
        """
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

        verdict = payload.get("verdict")
        if verdict not in self._DECISION_VERDICTS:
            self._respond(400, b'{"error":"invalid verdict"}')
            return
        text = (payload.get("text") or "").strip() or None
        if verdict in self._DECISION_TEXT_VERDICTS and not text:
            self._respond(
                400,
                json.dumps({"error": f"text required for {verdict} verdict"}).encode())
            return
        # v2.19 round mode: the chrome batches verdicts into a review round.
        # Everything below is identical except that NO session_push fires;
        # the verdict is parked with decision.round_pending=true until
        # POST /api/rounds/submit (one push for the whole round) or a
        # per-card POST /api/comments/<id>/push ("Send now").
        defer_push = bool(payload.get("defer_push"))

        identity = self._identity()
        author = identity["email"] or "anonymous"

        with _STORE_LOCK:
            store = self._v2_load()
            found = None
            for anchor_id, items in store.get("anchors", {}).items():
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
            now = _now_iso()
            old_status = c.get("status")

            prior_decision = c.get("decision")
            is_revision = prior_decision is not None
            if is_revision:
                c.setdefault("decision_history", []).append(prior_decision)

            latency_s = _decision_latency_s(c, now)
            c["decision"] = {"verdict": verdict, "text": text, "ts": now, "by": author}
            if latency_s is not None:
                c["decision"]["latency_s"] = latency_s
            if defer_push:
                c["decision"]["round_pending"] = True

            if verdict == "changes":
                reply_text = self._DECISION_CHANGES_PREFIX + text
            elif verdict == "comment":
                reply_text = self._DECISION_COMMENT_PREFIX + text
            elif verdict == "select":
                reply_text = self._DECISION_SELECT_PREFIX + text
            else:
                reply_text = self._DECISION_REPLY_TEXT[verdict]
                if text:
                    reply_text = reply_text + "\n\n" + text
            if is_revision:
                prior_label = self._DECISION_PRIOR_LABEL.get(
                    prior_decision.get("verdict"), prior_decision.get("verdict"))
                if verdict in self._DECISION_TEXT_VERDICTS:
                    reply_text = reply_text + "\n\n(revised verdict; was " + prior_label + ")"
                else:
                    reply_text = "↺ Changed to " + reply_text + " (was " + prior_label + ")"
            c.setdefault("replies", []).append({
                "author": author,
                "author_email": identity["email"],
                "author_name": identity["name"] or (payload.get("author_name") if identity["authenticated"] else None),
                "text": reply_text,
                "ts": now,
            })

            c["status"] = self._DECISION_STATUS_MAP[verdict]
            c["flagged_for_session"] = True
            c["flagged_at"] = now
            c["flagged_by"] = author
            self._v2_save(store)

        revision_bus_fields = (
            {"revised": True, "prior_verdict": prior_decision.get("verdict")}
            if is_revision else {}
        )
        _bus_append(self.bus_dir, self.slug, {
            "event": "comment_updated",
            "comment_id": comment_id,
            "anchor_id": anchor_id,
            "old_status": old_status,
            "new_status": c.get("status"),
            "author": author,
            "decision": verdict,
            **({"latency_s": latency_s} if latency_s is not None else {}),
            **({"deferred": True} if defer_push else {}),
            **revision_bus_fields,
        })
        if defer_push:
            delivery = {"delivery": "deferred", "monitor_count": 0, "monitor_owner": None, "delivery_id": None}
        else:
            delivery = self._compute_delivery()
            _bus_append(self.bus_dir, self.slug, {
                "event": "session_push",
                **delivery,
                "comment_count": 1,
                "comment_ids": [comment_id],
                "anchor_id": anchor_id,
                "author": author,
                "decision": verdict,
                **revision_bus_fields,
            })
        revision_log_suffix = f" (revised, was {prior_decision.get('verdict')})" if is_revision else ""
        deferred_suffix = " [deferred: round pending]" if defer_push else ""
        print(f"  POST /api/comments/{comment_id}/decision → verdict={verdict} by {author}{revision_log_suffix}{deferred_suffix}", flush=True)
        resp = dict(c)
        resp.update(delivery)
        self._respond(200, json.dumps(resp, ensure_ascii=False).encode(), "application/json")

    # ── v2.19: review rounds ─────────────────────────────────────────
    def _v2_post_rounds_submit(self, parsed):
        """POST /api/rounds/submit {"note": str?} — close the reviewer's round.

        Collects every comment whose decision is round_pending, clears the
        flag, and emits `round_submitted` plus exactly ONE session_push
        {round: true, ...} so the agent sees the whole set of verdicts at
        once instead of reacting to the first click.
        """
        payload, err = self._read_json_body()
        if err:
            return
        if not isinstance(payload, dict):
            payload = {}
        note = (payload.get("note") or "").strip() or None
        author = self._author(parsed)
        with _STORE_LOCK:
            store = self._v2_load()
            now = _now_iso()
            comment_ids = []
            verdict_counts = {v: 0 for v in self._DECISION_VERDICTS}
            undecided_ids = []
            for anchor_id, items in store.get("anchors", {}).items():
                for c in items:
                    if c.get("status") == "archived":
                        continue
                    d = c.get("decision")
                    # D3: "comment" is a remark, not an answer — the card
                    # stays in undecided_ids. It still rides out with the
                    # round below (it may well be the only thing the
                    # reviewer said about this card).
                    if c.get("decision_request") and not self._is_answered(d):
                        undecided_ids.append(c.get("id"))
                    if isinstance(d, dict) and d.get("round_pending"):
                        d.pop("round_pending", None)
                        c["flagged_for_session"] = True
                        c["flagged_at"] = now
                        c["flagged_by"] = author
                        comment_ids.append(c.get("id"))
                        v = d.get("verdict")
                        if v in verdict_counts:
                            verdict_counts[v] += 1
            self._v2_save(store)

        session = self._session_fields()
        _bus_append(self.bus_dir, self.slug, {
            "event": "round_submitted",
            "comment_ids": comment_ids,
            "verdict_counts": verdict_counts,
            "undecided_ids": undecided_ids,
            "note": note,
            "by": author,
            **session,
        })
        delivery = self._compute_delivery()
        _bus_append(self.bus_dir, self.slug, {
            "event": "session_push",
            **delivery,
            "round": True,
            "comment_count": len(comment_ids),
            "comment_ids": comment_ids,
            "verdict_counts": verdict_counts,
            "undecided_ids": undecided_ids,
            "note": note,
            "author": author,
            **session,
        })
        print(f"  POST /api/rounds/submit → {len(comment_ids)} verdict(s) {verdict_counts}, "
              f"{len(undecided_ids)} undecided, {delivery['delivery']}, by {author}", flush=True)
        self._respond(200, json.dumps({
            "ok": True,
            **delivery,
            "comment_count": len(comment_ids),
            "comment_ids": comment_ids,
            "verdict_counts": verdict_counts,
            "undecided_count": len(undecided_ids),
            "undecided_ids": undecided_ids,
        }, ensure_ascii=False).encode(), "application/json")

    def _v2_post_rounds_discard(self, parsed):
        """POST /api/rounds/discard — drop the round_pending flags WITHOUT
        pushing. The verdicts themselves stay recorded (reversible via
        "Change verdict"); they simply never go out as a round. Emits
        `round_discarded`, never a session_push."""
        author = self._author(parsed)
        with _STORE_LOCK:
            store = self._v2_load()
            comment_ids = []
            for anchor_id, items in store.get("anchors", {}).items():
                for c in items:
                    d = c.get("decision")
                    if isinstance(d, dict) and d.get("round_pending"):
                        d.pop("round_pending", None)
                        comment_ids.append(c.get("id"))
            self._v2_save(store)
        _bus_append(self.bus_dir, self.slug, {
            "event": "round_discarded",
            "comment_ids": comment_ids,
            "by": author,
            **self._session_fields(),
        })
        print(f"  POST /api/rounds/discard → {len(comment_ids)} pending flag(s) cleared by {author}", flush=True)
        self._respond(200, json.dumps({
            "ok": True, "comment_count": len(comment_ids), "comment_ids": comment_ids,
        }).encode(), "application/json")

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
    local_author: str | None = None,
    local_author_name: str | None = None,
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
    BoundHandler.local_author = local_author
    BoundHandler.local_author_name = local_author_name
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
        help="V2 mode: directory for the NDJSON event bus (default: <bus root>/default/)",
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
    parser.add_argument(
        "--local-author",
        default="",
        help="Identity fallback for direct localhost/loopback URLs only.",
    )
    parser.add_argument(
        "--local-author-name",
        default="",
        help="Optional display name paired with --local-author.",
    )
    args = parser.parse_args()

    # Normalize public_base_path: ensure leading slash, no trailing slash
    public_base_path = (args.public_base_path or "").strip()
    if public_base_path:
        if not public_base_path.startswith("/"):
            public_base_path = "/" + public_base_path
        public_base_path = public_base_path.rstrip("/")

    local_author = (args.local_author or "").strip() or None
    local_author_name = (args.local_author_name or "").strip() or None
    for label, value in (("--local-author", local_author), ("--local-author-name", local_author_name)):
        if value and ("\r" in value or "\n" in value):
            parser.error(f"{label} must be a single-line value")
    if local_author_name and not local_author:
        parser.error("--local-author-name requires --local-author")

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
            local_author=local_author,
            local_author_name=local_author_name,
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
        if local_author:
            print(f"  Local identity:    {local_author} (direct loopback Host only)")
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
            local_author=local_author,
            local_author_name=local_author_name,
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
