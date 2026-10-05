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
      *                            → serve public assets/attachments from the artifact's directory

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
    "status": "open" | "addressed_by_agent" | "resolved_in_version" |
              "user_confirmed" | "archived",
                "response_text": str | null,
                "replies": [ { "author": str, "text": str, "ts": iso } ],
                "decision_request": { "prompt": str, "options": [str, ...] } | null,
                "decision": { "verdict": "accept"|"reject"|"changes"|"comment",
                              # "changes" = Request changes (text required);
                              # "comment" = free-text answer (text required)
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
                                              (accept/reject/changes/comment/select);
                                              pushes to session.
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
      *                                     → serve public assets/attachments from <slug-dir>

    Optional request header X-Annotate-Session: <id> — when present, every bus
    event the request emits carries session_id (agents/CLIs send it, browsers
    never do).

    NDJSON bus: every comment event appends to <bus-dir>/<slug>.ndjson.
    Author extraction reads Cf-Access-Authenticated-User-Email header.

    Auto-migration: a v1 store ({nodeId: [comment]}) is wrapped to v2 shape on
    first write — original is backed up next to comments.json.
"""

import argparse
import difflib
import fcntl
import hashlib
import http.server
import ipaddress
import json
import os
import re
import socket
import sys
import tempfile
import threading
import tomllib
import urllib.parse
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .extract import ExtractionError, build_content_document, has_canvas_sentinels
from .paths import BUS_ROOT, MONITOR_OFFSET_ROOT, MONITOR_ROOT, PROJECTS_TOML, STATE_DIR, WEB_DIR
from .updates import runtime_manifest

RUNTIME_MANIFEST = runtime_manifest()

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
_WEB_ASSETS = frozenset({"shell.js", "shell.css", "content.css", "daisyui.css", "adapter.js", "diagram-plot.js",
                         "copy-editor.js", "copy-editor.css", "quill.js", "quill.snow.css"})
_ASSET_PATH_RE = re.compile(r"^/assets/(\d+)/(" + "|".join(re.escape(name) for name in sorted(_WEB_ASSETS)) + r")$")


def _cache_control_for(suffix: str) -> str:
    if suffix.lower() in (".js", ".css"):
        return _NO_STORE
    return "no-cache"


def _mtime_stamp(path) -> str:
    """Content-derived numeric asset key, stable across installs and copies.
    Falls back to a CONSTANT
    ('0') when the file can't be statted: a clock-based fallback minted a new
    stamp every second, so any document referencing a missing asset came back
    byte-different on every request and HTTP caching was defeated entirely."""
    if path is not None:
        try:
            return str(int(hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16], 16))
        except OSError:
            pass
    return "0"


# ────────────────────────────────────────────────────────────────────────────
# V2 storage helpers (file lock + shape coercion)
# ────────────────────────────────────────────────────────────────────────────
_STORE_LOCK = threading.RLock()
_STORE_LOCAL = threading.local()


@contextmanager
def _locked_store(directory):
    """Serialize HTTP and direct agent storage writes across threads/processes."""
    from .categories import safe_path
    with _STORE_LOCK:
        path = safe_path(directory, ".comments.json.lock")
        held = getattr(_STORE_LOCAL, "held", set())
        if path in held:
            yield
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            _STORE_LOCAL.held = held | {path}
            try:
                yield
            finally:
                _STORE_LOCAL.held = held



class ReviewHTTPServer(http.server.ThreadingHTTPServer):
    # Browsers fetch the locally bundled editor and theme assets concurrently.
    request_queue_size = 64


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
    if comment.get("status") != "open" or comment.get("round_pending") or (comment.get("decision") or {}).get("round_pending"):
        return False
    flagged_at = _iso_timestamp(comment.get("flagged_at"))
    latest = 0.0
    if not str(comment.get("author") or "").startswith("agent:"):
        latest = _iso_timestamp(comment.get("created_at"))
    if not str(comment.get("edited_by") or comment.get("author") or "").startswith("agent:"):
        latest = max(latest, _iso_timestamp(comment.get("edited_at")))
    for reply in comment.get("replies", []):
        if not str(reply.get("author") or "").startswith("agent:"):
            latest = max(latest, _iso_timestamp(reply.get("ts")))
    decision = comment.get("decision") or {}
    if decision and not str(decision.get("by") or "").startswith("agent:"):
        latest = max(latest, _iso_timestamp(decision.get("ts")))
    return bool(latest) and (not comment.get("flagged_for_session") or latest > flagged_at)


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


def _normalize_item_number(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DecisionRequestError("number must be a positive integer")
    return value


def _decision_request_changed(old: Any, new: Any) -> bool:
    """True when two decision_requests pose different questions.

    requested_at is stamped on every `ask`, so it never counts as a change.
    """
    def _question(dr: Any) -> Any:
        if not isinstance(dr, dict):
            return dr
        return {k: v for k, v in dr.items() if k != "requested_at"}
    return _question(old) != _question(new)


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
    "resolved_in_version": "resolved_in_version",
    "user_confirmed": "user_confirmed",
    "confirmed": "user_confirmed",
    "archived": "archived",
    "resolved": "user_confirmed",
}


def _coerce_status(s: str) -> str:
    return _STATUS_MAP.get((s or "").lower(), "open")


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


_VERSION_ID = re.compile(r"v[0-9]{1,10}\Z", re.ASCII)
_AGENT_ID = re.compile(r"agent:[^\x00-\x1f\x7f]{1,128}\Z")


def _contained_path(artifact_dir: Path, relative: str, subtree: str | None = None) -> Path:
    """Resolve within both the artifact and the intended public subtree."""
    try:
        root = artifact_dir.resolve()
        if subtree and (root / subtree).is_symlink():
            raise ValueError("version directory must not be a symlink")
        parent = (root / subtree).resolve() if subtree else root
        parent.relative_to(root)
        target = (parent / relative).resolve()
        target.relative_to(parent)
        return target
    except (ValueError, OSError, RuntimeError) as exc:
        raise PermissionError("artifact path leaves its allowed directory") from exc


def _version_file(artifact_dir: Path, version: str, subtree: str = "versions") -> Path:
    if not isinstance(version, str) or not _VERSION_ID.fullmatch(version):
        raise ValueError("version must have form vNN")
    return _contained_path(artifact_dir, f"{version}.html", subtree)


def _version_has_anchor(artifact_dir: Path, version: str, anchor_id: str) -> bool:
    """True when a disposition points at a real anchor in the named version."""
    try:
        target = _version_file(artifact_dir, version)
        markup = target.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return False
    pattern = re.compile(r"data-anchor-id=(['\"])" + re.escape(anchor_id) + r"\1")
    return bool(pattern.search(markup))


def _anchor_miss(artifact_dir: Path, version: str, anchor_id: str, what: str) -> bytes:
    """The 400 body for a disposition aimed at a missing anchor.

    A bare "not found" was the most common error agents hit on a new version:
    they guessed the anchor, or resolved before generating the version. The
    closest real anchors turn the retry into a copy, not a search.
    """
    body = {"error": f"{what} target anchor not found", "version": version, "anchor": anchor_id}
    try:
        target = _version_file(artifact_dir, version)
        markup = target.read_text(encoding="utf-8")
    except (OSError, ValueError):
        body["error"] = f"{what} target version {version} has no page yet — generate it first"
        return json.dumps(body).encode()
    anchors = re.findall(r"data-anchor-id=['\"]([^'\"]+)['\"]", markup)
    prefixed = [a for a in anchors if a.startswith(anchor_id + ":")][:3]
    body["closest"] = prefixed or difflib.get_close_matches(anchor_id, anchors, n=3, cutoff=0.5)
    return json.dumps(body).encode()


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
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(data, output, indent=2, ensure_ascii=False)
            os.fchmod(output.fileno(), mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


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
        if event.get("event") == "session_push" and event.get("round"):
            fh.flush()
            os.fsync(fh.fileno())


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
    proxy_urls: tuple[str, ...] = ()
    trusted_access_origins: tuple[str, ...] = ()

    @staticmethod
    def _origin(value: str) -> tuple[str, str, int] | None:
        try:
            parsed = urllib.parse.urlsplit(value)
            if (parsed.scheme not in ("http", "https") or not parsed.hostname
                    or parsed.username is not None or parsed.password is not None
                    or parsed.query or parsed.fragment or any(char.isspace() or ord(char) < 32 for char in value)):
                return None
            port = parsed.port
            if port is not None and not 0 < port < 65536:
                return None
            port = port or (443 if parsed.scheme == "https" else 80)
            return parsed.scheme, parsed.hostname.lower(), port
        except ValueError:
            return None

    def _published_proxy_origins(self) -> set[tuple[str, str, int]]:
        urls = list(self.proxy_urls)
        try:
            state = json.loads((STATE_DIR / f"{_monitor_project(self.bus_dir)}.json").read_text())
            slugs = state.get("slugs", {}) if isinstance(state, dict) else {}
            record = slugs.get(self.slug, {}) if isinstance(slugs, dict) else {}
            if not isinstance(record, dict):
                record = {}
            if (Path(record.get("slug_dir", "")).resolve() == self.artifact_dir.resolve()
                    and record.get("port") == self.server.server_address[1]
                    and record.get("transport") != "local"):
                urls.extend(record.get(field) for field in ("url", "public_url"))
        except (OSError, ValueError, TypeError):
            pass
        return {origin for value in urls if isinstance(value, str)
                and (origin := self._origin(value)) is not None and origin[0] == "https"}

    def _access_origins(self) -> set[tuple[str, str, int]]:
        values = list(self.trusted_access_origins)
        try:
            config = tomllib.loads(PROJECTS_TOML.read_text())
            section = config.get(_monitor_project(self.bus_dir), {}) if isinstance(config, dict) else {}
            configured = section.get("trusted_access_origins", []) if isinstance(section, dict) else []
            if isinstance(configured, list):
                values.extend(configured)
        except (OSError, ValueError, TypeError):
            pass
        return {origin for value in values if isinstance(value, str)
                and (origin := self._origin(value)) is not None and origin[0] == "https"
                and urllib.parse.urlsplit(value).path in ("", "/")}

    def _request_origin(self) -> tuple[str, str, int] | None:
        host = self.headers.get("Host") or ""
        if any(char in host for char in ("/", "\\", "?", "#", "@")):
            return None
        direct = self._origin("http://" + host)
        if direct is not None:
            try:
                loopback = direct[1] == "localhost" or ipaddress.ip_address(direct[1]).is_loopback
            except ValueError:
                loopback = False
            legacy_agent = self.headers.get("Cf-Access-Authenticated-User-Email")
            if (loopback and direct[2] == self.server.server_address[1] and not self._has_proxy_markers()
                    and (not legacy_agent or (legacy_agent.startswith("agent:") and not self.headers.get("Origin")
                                              and not self.headers.get("Sec-Fetch-Site")))):
                return direct
        proxy = self._origin("https://" + host)
        return proxy if proxy in self._published_proxy_origins() else None

    def _allow_request(self) -> bool:
        path = urllib.parse.urlsplit(self.path).path
        if self.public_base_path and path != self.public_base_path and not path.startswith(self.public_base_path + "/"):
            self._respond(404, b'{"error":"outside published page mount"}')
            return False
        try:
            if not ipaddress.ip_address(self.client_address[0]).is_loopback:
                raise ValueError
        except ValueError:
            self._respond(403, b'{"error":"loopback listener boundary required"}')
            return False
        origin = self._request_origin()
        supplied = self.headers.get("Origin")
        if (origin is None or (supplied is not None and (self._origin(supplied) != origin
                or urllib.parse.urlsplit(supplied).path not in ("", "/")))):
            self._respond(403, b'{"error":"untrusted host or origin"}')
            return False
        agent = self.headers.get("X-Annotate-Agent") or self.headers.get("Cf-Access-Authenticated-User-Email")
        if origin[0] == "http" and agent is not None and (
                supplied is not None or self.headers.get("Sec-Fetch-Site") is not None or not _AGENT_ID.fullmatch(agent)):
            self._respond(403, b'{"error":"local agent attribution requires a direct non-browser request"}')
            return False
        site = self.headers.get("Sec-Fetch-Site")
        navigation = (self.command == "GET" and self.headers.get("Sec-Fetch-Mode") == "navigate"
                      and self.headers.get("Sec-Fetch-Dest") == "document")
        if site not in (None, "none", "same-origin") and not navigation:
            self._respond(403, b'{"error":"cross-origin request refused"}')
            return False
        if origin[0] == "https" and not self._identity()["authenticated"]:
            route = self._strip_base(path)
            bootstrap_assets = {"shell.js", "shell.css", "content.css", "daisyui.css", "copy-editor.js", "copy-editor.css", "quill.js", "quill.snow.css"}
            bootstrap = (self.command == "GET" and ((route == "/" and self.v2_mode) or route.lstrip("/") in bootstrap_assets
                         or ((match := _ASSET_PATH_RE.fullmatch(route)) and match[2] in bootstrap_assets)))
            session = self.command == "POST" and route == "/api/reviewer/session"
            if self._is_funnel_origin() and (bootstrap or session):
                return True
            self._respond(403, b'{"error":"authenticated proxy boundary required"}')
            return False
        try:
            for name in ("comments.json", "current.meta.json", "project.json", "copy.json", "rounds.ndjson", "seen.json", "read-state.json"):
                _contained_path(self.artifact_dir, name)
        except PermissionError:
            self._respond(403, b'{"error":"runtime path leaves artifact directory"}')
            return False
        return True

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

    # Cloudflare stamps these on every request it forwards. Its connector is
    # itself a tailnet node, so a public request reaching `tailscale serve`
    # through the tunnel would otherwise carry the connector owner's login.
    _CLOUDFLARE_HEADERS = ("Cf-Ray", "Cf-Connecting-Ip", "Cf-Access-Jwt-Assertion")
    _PROXY_MARKERS = (*_CLOUDFLARE_HEADERS, "Cf-Access-Authenticated-User-Name", "Forwarded", "Via", "X-Real-IP",
                      "X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto", "Tailscale-User-Login",
                      "Tailscale-User-Name", "X-Auth-Request-User", "oai-authenticated-user-email",
                      "oai-authenticated-user-full-name", "oai-authenticated-user-full-name-encoding")

    def _has_proxy_markers(self) -> bool:
        return any(self.headers.get(name) is not None for name in self._PROXY_MARKERS)

    def _tailscale_identity(self) -> tuple[str, str]:
        """The tailnet login `tailscale serve` attaches, or ("", "").

        `tailscale serve` drops any Tailscale-User-* header a client sends and
        sets its own from the tailnet login (checked on 2026-09-23 with a
        forged header: it arrived replaced by the real login). Trust it only
        on a loopback peer (serve proxies from this host) with a *.ts.net
        Host, and never on a request Cloudflare forwarded.
        """
        login = (self.headers.get("Tailscale-User-Login") or "").strip()
        if not login:
            return "", ""
        try:
            if not ipaddress.ip_address(self.client_address[0]).is_loopback:
                return "", ""
        except ValueError:
            return "", ""
        if any(self.headers.get(h) for h in self._CLOUDFLARE_HEADERS):
            return "", ""
        host_header = (self.headers.get("Host") or "").strip()
        try:
            hostname = urllib.parse.urlsplit("//" + host_header).hostname or ""
        except ValueError:
            return "", ""
        if (not hostname.lower().endswith(".ts.net")
                or self._origin("https://" + host_header) not in self._published_proxy_origins()):
            return "", ""
        return login, (self.headers.get("Tailscale-User-Name") or "").strip()

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
        if not peer_is_loopback or self._has_proxy_markers():
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
        """Trust recorded TailServe or an explicitly declared Access edge.

        Access JWT validation is delegated to that owner-configured edge; token
        presence here is not cryptographic verification. Local OS callers are
        attributed as agents. Browser identity uses only the local preset or
        trusted proxy, never a client-authored JSON/query/proxy claim.
        """
        email, name = self._tailscale_identity()
        if not email and self._is_funnel_origin():
            from .review_access import identity
            email, name = identity(self.artifact_dir, self.headers.get("Cookie") or "")
        origin = self._origin("https://" + (self.headers.get("Host") or ""))
        if (origin in self._published_proxy_origins() and origin in self._access_origins()
                and not origin[1].endswith(".ts.net") and self.headers.get("Cf-Access-Jwt-Assertion")):
            email = (self.headers.get("Cf-Access-Authenticated-User-Email") or "").strip()
            name = (self.headers.get("Cf-Access-Authenticated-User-Name") or "").strip()
        if self._is_direct_loopback_request() and not self.headers.get("Origin") and not self.headers.get("Sec-Fetch-Site"):
            agent = self.headers.get("X-Annotate-Agent") or self.headers.get("Cf-Access-Authenticated-User-Email") or ""
            if _AGENT_ID.fullmatch(agent):
                email, name = agent, ""
        if not email and self.local_author and self._is_direct_loopback_request():
            email = self.local_author
            name = self.local_author_name or name
        return {
            "email": email or None,
            "name": name or None,
            "authenticated": bool(email) and not email.startswith("agent:"),
        }

    def _author(self, parsed=None) -> str:
        return self._identity()["email"] or "anonymous"

    def _is_funnel_origin(self) -> bool:
        origin = self._origin("https://" + (self.headers.get("Host") or ""))
        if origin not in self._published_proxy_origins():
            return False
        try:
            state = json.loads((STATE_DIR / f"{_monitor_project(self.bus_dir)}.json").read_text())
            record = state.get("slugs", {}).get(self.slug, {})
            return (record.get("transport") == "funnel" and record.get("port") == self.server.server_address[1]
                    and Path(record.get("slug_dir", "")).resolve() == self.artifact_dir.resolve())
        except (OSError, ValueError, TypeError):
            return False

    def _reviewer_session(self):
        from .review_access import cookie_name, issue_cookie
        try:
            length = int(self.headers.get("Content-Length") or "0")
            if not 0 < length <= 4096 or not self._is_funnel_origin():
                raise ValueError("invalid reviewer session request")
            payload = json.loads(self.rfile.read(length))
            cookie = issue_cookie(self.artifact_dir, payload.get("key"), payload.get("name", "Reviewer"), self.headers.get("Cookie") or "")
        except (OSError, ValueError, TypeError, AttributeError):
            return self._respond(403, b'{"error":"invalid review link"}')
        path = (self.public_base_path or "") + "/"
        self._respond(200, b'{"ok":true}', cache_control="no-store", extra_headers={
            "Set-Cookie": f"{cookie_name(self.artifact_dir)}={cookie}; Path={path}; Max-Age=2592000; HttpOnly; Secure; SameSite=Strict"})

    # ── GET ──────────────────────────────────────────────────────────
    def do_GET(self):
        if not self._allow_request():
            return
        parsed = urllib.parse.urlparse(self.path)
        if self.public_base_path and parsed.path == self.public_base_path:
            # Relative shell assets and API URLs require a directory base.
            location = self.public_base_path + "/"
            if parsed.query:
                location += "?" + parsed.query
            self.send_response(308)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
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
            if route_path == "/api/share-link":
                return self._v2_get_share_link()
            if route_path == "/api/session-monitor":
                return self._v2_get_session_monitor(parsed)
            if route_path == "/api/capabilities":
                return self._v2_get_capabilities(parsed)
            if route_path == "/api/delivery":
                from .delivery import delivery_status
                return self._respond(200, json.dumps(delivery_status(_monitor_project(self.bus_dir), self.slug)).encode(), "application/json")
            if route_path == "/api/project":
                try:
                    return self._respond(200, json.dumps(self._project_payload()).encode(), "application/json", cache_control="no-store")
                except (OSError, ValueError) as exc:
                    return self._respond(500, json.dumps({"error": str(exc)}).encode(), "application/json")
            if route_path == "/api/copy":
                from .copy_state import load_copy
                try:
                    return self._respond(200, json.dumps(load_copy(self.artifact_dir), ensure_ascii=False).encode(), cache_control="no-store")
                except (OSError, ValueError) as exc:
                    return self._respond(500, json.dumps({"error": str(exc)}).encode())
            if route_path == "/api/categories":
                return self._get_categories()
            if route_path.startswith("/api/plans/"):
                from .categories import plan_meta
                try:
                    meta = plan_meta(self.artifact_dir, urllib.parse.unquote(route_path[len("/api/plans/"):]))
                    return self._respond(200, json.dumps(meta).encode(), cache_control="no-store")
                except KeyError:
                    return self._respond(404, b'{"error":"plan not found"}')
                except (ValueError, OSError) as exc:
                    return self._respond(400, json.dumps({"error": str(exc)}).encode())
            if route_path.startswith("/plans/"):
                match = re.fullmatch(r"/plans/([^/]+)/(v[0-9]{1,10})\.html", urllib.parse.unquote(route_path))
                if not match:
                    return self._respond(400, b'{"error":"invalid plan path"}')
                return self._v2_serve_content(parsed, plan_id=match[1], plan_version=match[2])
            if route_path == "/api/history":
                from .paths import BUS_ARCHIVE_ROOT
                from .review_history import review_history
                try:
                    with _locked_store(self.artifact_dir):
                        history = review_history(self.artifact_dir, self.bus_dir / f"{self.slug}.ndjson" if self.bus_dir else None, BUS_ARCHIVE_ROOT)
                    return self._respond(200, json.dumps(history, ensure_ascii=False).encode(), cache_control="no-store")
                except (OSError, ValueError) as exc:
                    return self._respond(500, json.dumps({"error": str(exc)}).encode())
            if route_path == "/comments.json":
                return self._v2_get_store()
            if route_path == "/current.meta.json":
                return self._v2_get_meta()
            if route_path.lstrip("/") in _WEB_ASSETS:
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
        if not self._allow_request():
            return
        parsed = urllib.parse.urlparse(self.path)
        route_path = self._strip_base(parsed.path)

        if self.v2_mode:
            if route_path == "/api/reviewer/session":
                return self._reviewer_session()
            if route_path.startswith("/api/copy/"):
                match = re.fullmatch(r"/api/copy/([^/]+)/(proposal|revisions|restore)", route_path)
                if match:
                    return self._post_copy_proposal(urllib.parse.unquote(match[1]), restore=match[2] == "restore")
            if route_path.startswith("/api/comments/") and route_path.endswith("/reopen"):
                cid = urllib.parse.unquote(route_path[len("/api/comments/"):-len("/reopen")])
                return self._post_finding_reopen(cid)
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
        if not self._allow_request():
            return
        parsed = urllib.parse.urlparse(self.path)
        route_path = self._strip_base(parsed.path)
        if self.v2_mode and route_path.startswith("/api/comments/"):
            cid = route_path[len("/api/comments/"):]
            return self._v2_put_comment(cid, parsed)
        self._respond(404, b'{"error":"Not found"}')

    def do_OPTIONS(self):
        if not self._allow_request():
            return
        self.send_response(204)
        self.send_header("Allow", "GET, POST, PUT, OPTIONS")
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
        from . import __version__
        self._respond(200, json.dumps({
            "version": __version__,
            "runtime": RUNTIME_MANIFEST,
            "automatic_round_delivery": True,
            "private_share_links": self._is_funnel_origin(),
            "copy_blocks": True,
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
    def _legacy_comments_path(self, parsed):
        doc = (urllib.parse.parse_qs(parsed.query).get("doc") or [None])[0]
        if (not isinstance(doc, str) or not doc or doc in (".", "..")
                or any(char in doc for char in ("/", "\\"))
                or any(ord(char) < 32 or ord(char) == 127 for char in doc)):
            self._respond(400, b'{"error":"safe doc identifier required"}')
            return None
        try:
            return _contained_path(self.artifact_dir, doc + ".comments.json")
        except PermissionError:
            self._respond(403, b'{"error":"forbidden comment path"}')
            return None

    def _v1_get_comments(self, parsed):
        json_path = self._legacy_comments_path(parsed)
        if json_path is None:
            return
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
        json_path = self._legacy_comments_path(parsed)
        if json_path is None:
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            self._respond(400, f'{{"error":"invalid json: {exc}"}}'.encode())
            return
        try:
            _atomic_write_json(json_path, data)
        except OSError as exc:
            self._respond(500, f'{{"error":"write error: {exc}"}}'.encode())
            return
        total = sum(len(v) for v in data.values() if isinstance(v, list))
        print(f"  POST /api/comments → {total} comment(s)", flush=True)
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
        with _locked_store(self.artifact_dir):
            store = self._v2_load()
        self._respond(200, json.dumps(store, ensure_ascii=False).encode(), "application/json", conditional=True)

    def _v2_get_meta(self):
        p = self._meta_path()
        if p.exists():
            try:
                meta = self._read_meta()
                if isinstance(meta.get("owner"), dict):
                    target = meta["owner"].get("target") or {}
                    if isinstance(target.get("terminal_name"), str):
                        meta["owner"]["terminal_name"] = target["terminal_name"]
                    meta["owner"] = {k: v for k, v in meta["owner"].items() if k != "target"}
                from .delivery import delivery_status
                try:
                    meta["project_info"] = self._project_payload()
                except (OSError, ValueError):
                    meta["project_info"] = {"modules": []}
                meta["delivery_status"] = delivery_status(_monitor_project(self.bus_dir), self.slug)
                data = json.dumps(meta).encode()
            except (OSError, ValueError):
                data = b"{}"
        else:
            data = json.dumps({"current": "v1", "history": []}).encode()
        self._respond(200, data, "application/json", cache_control="no-store" if self._is_funnel_origin() else "no-cache",
                      conditional=not self._is_funnel_origin())

    def _v2_get_comments(self, parsed):
        params = urllib.parse.parse_qs(parsed.query)
        flt_status = (params.get("status") or [None])[0]
        flt_version = (params.get("version") or [None])[0]
        with _locked_store(self.artifact_dir):
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
            return _version_file(self.artifact_dir, version)
        return _contained_path(self.artifact_dir, "current.html")

    def _extractable_version(self, version: str | None) -> bool:
        """True when a baked legacy version can be served through the shell.

        Chrome baked into versions/<v>.html at generation time is why a fix to
        the artifact chrome never reached an already-published page. When the
        canvas sentinels are present the server can recover the author's
        content and serve it through the universal shell instead, so chrome
        comes from the skill dir on every request like it does for every other
        slug. Nothing is written to disk — see _v2_serve_content.
        """
        try:
            target = self._version_path(version)
            if not target.exists() or not target.is_file():
                return False
            return has_canvas_sentinels(target.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
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
        v = (urllib.parse.parse_qs(parsed.query).get("v") or [None])[0]
        try:
            target = self._version_path(v)
        except ValueError:
            return self._respond(400, b'{"error":"invalid version"}')
        except PermissionError:
            return self._respond(403, b'{"error":"forbidden version path"}')
        # Universal-shell slugs serve the shared shell.html at root; the shell
        # reads ?v= client-side and loads the right iframe src. A slug earns
        # that path either by having a content/ dir of chrome-free docs, or by
        # being a baked legacy artifact the server can extract on the fly.
        # Anything else (no sentinels, e.g. hand-written HTML that never went
        # through template.html) still gets the old direct-serve behavior.
        if self._shell_eligible(parsed) or self._is_funnel_origin():
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
                for name in _WEB_ASSETS:
                    if not (self.skill_dir / name).is_file():
                        continue
                    for attribute in ("href", "src"):
                        html = html.replace(f'{attribute}="{name}"',
                            f'{attribute}="{base}/assets/{_mtime_stamp(self.skill_dir / name)}/{name}"')
                self._respond(200, html.encode("utf-8"), "text/html; charset=utf-8",
                              cache_control=_NO_STORE)
                return
            # skill_dir/shell.html missing — fail loudly rather than silently
            # falling back, so a broken deploy is visible instead of masked.
            self._respond(500, b'{"error":"shell.html not found next to sync_server.py"}')
            return

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
        with _locked_store(self.artifact_dir):  # reuse the store lock; meta writes are rare & small
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

    def _v2_serve_content(self, parsed, *, plan_id=None, plan_version=None):
        """GET /content?v=vN — serve the chrome-free extracted content doc
        for version vN, with adapter.js injected before </body>. Falls back
        to 'current' version from current.meta.json when ?v= is omitted.
        """
        params = urllib.parse.parse_qs(parsed.query)
        v = plan_version or (params.get("v") or [None])[0]
        if not v:
            meta = self._read_meta()
            v = meta.get("current")
        if not v:
            self._respond(400, b'{"error":"no version specified and no current.meta.json"}')
            return
        try:
            if plan_id is not None:
                from .categories import plan_meta, safe_path, validate_plan_id
                validate_plan_id(plan_id)
                meta = plan_meta(self.artifact_dir, plan_id)
                if v not in {item.get("version") for item in meta.get("history", [])}:
                    return self._respond(404, b'{"error":"plan version not found"}')
                target = safe_path(self.artifact_dir, f"plans/{plan_id}/versions/{v}.html")
            else:
                target = _version_file(self.artifact_dir, v, "content")
        except ValueError:
            return self._respond(400, b'{"error":"invalid version"}')
        except KeyError:
            return self._respond(404, b'{"error":"plan not found"}')
        except PermissionError:
            return self._respond(403, b'{"error":"forbidden content path"}')
        if target.exists() and target.is_file():
            try:
                html = target.read_text(encoding="utf-8")
            except OSError:
                self._respond(500, b"Read error")
                return
            if plan_id is None:
                self._ensure_content_stamp(v, html, target)
        else:
            if plan_id is not None:
                return self._respond(404, b'{"error":"plan content not found"}')
            # No content/ doc: recover one from the baked legacy artifact.
            # Doing this at request time rather than as a one-off migration is
            # what keeps chrome fixes universal — a legacy page picks up the
            # current adapter.js on its next request exactly like a migrated
            # slug, with no file to re-generate and no stale duplicate on
            # disk. An explicit content/<v>.html always wins, so a hand-tuned
            # extraction is never overridden.
            try:
                baked = self._version_path(v)
            except PermissionError:
                return self._respond(403, b'{"error":"forbidden version path"}')
            if not baked.exists() or not baked.is_file():
                self._respond(404, f'{{"error":"content not found for version {v}"}}'.encode())
                return
            try:
                raw = baked.read_text(encoding="utf-8", errors="replace")
            except OSError:
                self._respond(500, b"Read error")
                return
            try:
                html = build_content_document(raw, title=self.slug or "Annotate content") if has_canvas_sentinels(raw) else raw
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
        if plan_id is not None:
            # A plan version has the same page-local asset root as Review.
            html = re.sub(r"<base\b[^>]*>", "", html, flags=re.IGNORECASE)
            base_tag = f'<base href="{base}/">'
            html = html.replace("<head>", "<head>" + base_tag, 1) if "<head>" in html else base_tag + html
        css = f'<link rel="stylesheet" href="{base}/assets/{_mtime_stamp((self.skill_dir or WEB_DIR) / "daisyui.css")}/daisyui.css">'
        if '<div class="aa">' in html:
            html = re.sub(r'<style(?: data-annotate-style="managed")?>\s*\.aa\{.*?</style>', '', html, count=1, flags=re.DOTALL)
            css += f'<link rel="stylesheet" href="{base}/assets/{_mtime_stamp((self.skill_dir or WEB_DIR) / "content.css")}/content.css">'
        html = html.replace('</head>', css + '</head>', 1) if '</head>' in html else css + html
        adapter_v = _mtime_stamp((self.skill_dir / "adapter.js") if self.skill_dir else None)
        content_meta = json.dumps({"version": v, "publicBasePath": base, "slug": self.slug,
                                   **({"doc": "plan:" + plan_id, "category": "plans"} if plan_id else {})}).replace("<", "\\u003c")
        bootstrap = (
            f'<script>window.__ANNOTATE_CONTENT_META__='
            f'{content_meta};</script>\n'
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
        try:
            dgplot_local = _contained_path(self.artifact_dir, "diagram-plot.js")
            if not self._is_public_static(dgplot_local.relative_to(self.artifact_dir.resolve()).as_posix()):
                dgplot_local = None
        except PermissionError:
            dgplot_local = None
        dgplot_skill = (self.skill_dir / "diagram-plot.js") if self.skill_dir else None
        dgplot = dgplot_local if dgplot_local is not None and dgplot_local.exists() else (
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
            try:
                local = _contained_path(self.artifact_dir, name)
                if self._is_public_static(local.relative_to(self.artifact_dir.resolve()).as_posix()):
                    candidates.append(local)
            except PermissionError:
                pass
        if self.skill_dir:
            try:
                candidates.append(_contained_path(self.skill_dir, name))
            except PermissionError:
                pass
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
            if (not self._is_direct_loopback_request() or self.headers.get("Origin")
                    or self.headers.get("Sec-Fetch-Site")):
                self._respond(403, b'{"error":"whole-store replacement requires a local non-browser caller"}')
                return
            with _locked_store(self.artifact_dir):
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
            with _locked_store(self.artifact_dir):
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
        browser = not (self._is_direct_loopback_request() and not self.headers.get("Origin")
                       and not self.headers.get("Sec-Fetch-Site"))
        if any(key in payload for key in ("fixed", "fixed_history", "reopened", "round_pending")):
            raise DecisionRequestError("finding lifecycle fields require the storage API", 403)
        if browser and "finding" in payload:
            raise DecisionRequestError("finding authoring requires a local caller", 403)
        category_fields = self._comment_category_fields(payload)
        if "doc" in category_fields:
            from .categories import plan_meta
            try:
                plan = plan_meta(self.artifact_dir, category_fields["doc"][5:])
            except (KeyError, ValueError) as exc:
                raise DecisionRequestError("unknown plan document") from exc
            meta = {**meta, "current": plan["current"]}
            version = payload.get("version") or plan["current"]
            if version not in {item.get("version") for item in plan["history"]}:
                raise DecisionRequestError("unknown plan version")
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
            **category_fields,
        }
        number = _normalize_item_number(payload.get("number"))
        if number is not None:
            comment["number"] = number
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
            with _locked_store(self.artifact_dir):
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
                            shared_decision = (
                                author.startswith("agent:") and str(c.get("author") or "").startswith("agent:")
                                and type(fresh.get("number")) is int
                                and c.get("number") == fresh["number"]
                                and aid == f"d:q{fresh['number']}"
                            )
                            if (c.get("status") not in ("archived", "resolved_in_version")
                                    and (c.get("author") == author or shared_decision)
                                    and c.get("decision_request")):
                                existing = c
                                break
                    if existing is not None:
                        # A card carried into a newer version and then asked
                        # a different question is a new question: its old
                        # verdict answered the old one. Keep that verdict in
                        # decision_history and put the card back in front of
                        # the reviewer. Re-running `ask` with the same
                        # question (requested_at aside) leaves verdicts alone.
                        prior = existing.get("decision")
                        reposed = (
                            isinstance(prior, dict)
                            and existing.get("carried_at")
                            and existing["carried_at"] >= (prior.get("ts") or "")
                            and _decision_request_changed(existing.get("decision_request"),
                                                          fresh["decision_request"])
                        )
                        if reposed:
                            existing.setdefault("decision_history", []).append(prior)
                            existing.pop("decision", None)
                            existing["status"] = "open"
                            existing["reposed_at"] = now
                        existing["text"] = fresh["text"]
                        existing["decision_request"] = fresh["decision_request"]
                        for field in ("category", "doc", "finding"):
                            if field in fresh:
                                existing[field] = fresh[field]
                        if fresh.get("number") is not None:
                            existing["number"] = fresh["number"]
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
            if new_status not in (
                "open", "addressed_by_agent", "resolved_in_version",
                "user_confirmed", "archived",
            ):
                self._respond(400, b'{"error":"invalid status"}')
                return
        resolution_version = payload.get("resolved_in_version")
        resolution_anchor = payload.get("resolution_anchor_id")
        if new_status == "resolved_in_version":
            if not isinstance(resolution_version, str) or not resolution_version.strip():
                self._respond(400, b'{"error":"resolved_in_version required"}')
                return
            if not isinstance(resolution_anchor, str) or not resolution_anchor.strip():
                self._respond(400, b'{"error":"resolution_anchor_id required"}')
                return
            resolution_version = resolution_version.strip()
            resolution_anchor = resolution_anchor.strip()
            if not _version_has_anchor(self.artifact_dir, resolution_version, resolution_anchor):
                self._respond(400, _anchor_miss(self.artifact_dir, resolution_version,
                                                resolution_anchor, "resolution"))
                return

        carry_forward = payload.get("carry_forward")
        carry_version = carry_anchor = None
        if carry_forward is not None:
            if not isinstance(carry_forward, dict):
                self._respond(400, b'{"error":"carry_forward must be an object"}')
                return
            carry_version = carry_forward.get("version")
            carry_anchor = carry_forward.get("anchor_id")
            if not isinstance(carry_version, str) or not carry_version.strip():
                self._respond(400, b'{"error":"carry_forward.version required"}')
                return
            if not isinstance(carry_anchor, str) or not carry_anchor.strip():
                self._respond(400, b'{"error":"carry_forward.anchor_id required"}')
                return
            carry_version = carry_version.strip()
            carry_anchor = carry_anchor.strip()
            if not _version_has_anchor(self.artifact_dir, carry_version, carry_anchor):
                self._respond(400, _anchor_miss(self.artifact_dir, carry_version,
                                                carry_anchor, "carry"))
                return
            if new_status is not None:
                self._respond(400, b'{"error":"carry_forward owns the status transition"}')
                return
        try:
            item_number = _normalize_item_number(payload.get("number"))
        except DecisionRequestError as exc:
            self._respond(exc.status, json.dumps({"error": str(exc)}).encode())
            return
        identity = self._identity()
        author = identity["email"] or "anonymous"

        with _locked_store(self.artifact_dir):
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
            local_authoring = (self._is_direct_loopback_request() and not self.headers.get("Origin")
                               and not self.headers.get("Sec-Fetch-Site"))
            if not local_authoring and (
                    any(key in payload for key in ("decision_request", "response_text", "resolved_in_version", "carry_forward", "number",
                                                   "fixed", "fixed_history", "reopened", "round_pending", "category", "doc", "finding"))
                    or new_status in ("addressed_by_agent", "resolved_in_version")
                    or ("text" in payload and c.get("author") != author)):
                self._respond(403, b'{"error":"reviewers can answer questions and edit their own comments; agent authoring requires a local caller"}')
                return
            try:
                c.update(self._comment_category_fields(payload))
            except DecisionRequestError as exc:
                return self._respond(exc.status, json.dumps({"error": str(exc)}).encode())
            old_status = c.get("status")
            if new_status == "addressed_by_agent" and old_status == "user_confirmed":
                self._respond(
                    409,
                    b'{"error":"addressed_by_agent cannot demote user_confirmed"}',
                )
                return
            if carry_forward is not None and old_status == "user_confirmed":
                self._respond(
                    409,
                    b'{"error":"carry_forward cannot demote user_confirmed"}',
                )
                return
            if new_status:
                c["status"] = new_status
            if item_number is not None:
                c["number"] = item_number
            resolved_now = new_status == "resolved_in_version"
            if resolved_now:
                c["resolved_in_version"] = resolution_version
                c["resolution_anchor_id"] = resolution_anchor
                c["resolved_at"] = _now_iso()
                c["resolved_by"] = author
                decision = c.get("decision")
                if isinstance(decision, dict):
                    decision.pop("round_pending", None)
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
            carried_now = carry_forward is not None
            if carried_now:
                carried_at = _now_iso()
                c.setdefault("origin_version", c.get("version"))
                c.setdefault("origin_anchor_id", anchor_id)
                c.setdefault("carry_history", []).append({
                    "from_version": c.get("version"),
                    "from_anchor_id": anchor_id,
                    "to_version": carry_version,
                    "to_anchor_id": carry_anchor,
                    "ts": carried_at,
                    "by": author,
                })
                c["version"] = carry_version
                c["carried_to_version"] = carry_version
                c["carried_to_anchor_id"] = carry_anchor
                c["carried_at"] = carried_at
                c["carried_by"] = author
                c["status"] = "open"
            new_anchor = carry_anchor if carried_now else payload.get("anchor_id")
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
        if resolved_now:
            _bus_append(self.bus_dir, self.slug, {
                "event": "comment_resolved",
                "comment_id": comment_id,
                "anchor_id": anchor_id,
                "resolved_in_version": resolution_version,
                "resolution_anchor_id": resolution_anchor,
                "author": author,
                **session,
            })
        if carried_now:
            _bus_append(self.bus_dir, self.slug, {
                "event": "comment_carried_forward",
                "comment_id": comment_id,
                "from_version": c.get("origin_version"),
                "from_anchor_id": c.get("origin_anchor_id"),
                "to_version": carry_version,
                "to_anchor_id": carry_anchor,
                "author": author,
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

        with _locked_store(self.artifact_dir):
            store = self._v2_load()
            found = None
            auto_reopened = False
            reopened_from = None
            answered_by_reply = None
            for anchor_id, items in store["anchors"].items():
                for c in items:
                    if c.get("id") == comment_id:
                        c.setdefault("replies", []).append(reply)
                        # T9: a USER reply on an agent-addressed comment is
                        # itself the reopen signal — the user shouldn't need
                        # a second action. Agent replies (author "agent:*",
                        # same convention the shell's ball-in-court logic
                        # uses) never auto-reopen.
                        if c.get("status") in ("addressed_by_agent", "resolved_in_version") \
                                and not author.startswith("agent:"):
                            reopened_from = c.get("status")
                            c["status"] = "open"
                            c["reopened_at"] = _now_iso()
                            c["reopened_by"] = author
                            if reopened_from == "resolved_in_version":
                                c["resolution_reopened_at"] = c["reopened_at"]
                                c["resolution_reopened_by"] = author
                            auto_reopened = True
                        # A reviewer's reply on an unanswered question IS the
                        # answer (Chang, 2026-09-23: a reply kept the card in
                        # "Needs my review"). Record it as the free-text verdict
                        # so every readout agrees the ball is with the agent.
                        if (c.get("decision_request") and not author.startswith("agent:")
                                and c.get("status") not in ("archived", "resolved_in_version")
                                and not self._is_answered(c.get("decision"))):
                            prior = c.get("decision")
                            if prior is not None:
                                c.setdefault("decision_history", []).append(prior)
                            c["decision"] = {"verdict": "comment", "text": text,
                                             "ts": reply["ts"], "by": author, "via": "reply"}
                            latency_s = _decision_latency_s(c, reply["ts"])
                            if latency_s is not None:
                                c["decision"]["latency_s"] = latency_s
                            answered_by_reply = c.get("status")
                            c["status"] = "open"
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
            **({"auto_reopened": True, "old_status": reopened_from,
                "new_status": "open"} if auto_reopened else {}),
            **self._session_fields(),
        })
        if answered_by_reply is not None:
            decision = found[1]["decision"]
            _bus_append(self.bus_dir, self.slug, {
                "event": "comment_updated",
                "comment_id": comment_id,
                "anchor_id": found[0],
                "old_status": answered_by_reply,
                "new_status": "open",
                "author": author,
                "decision": "comment",
                "via": "reply",
                **({"latency_s": decision["latency_s"]} if "latency_s" in decision else {}),
                **self._session_fields(),
            })
            print(f"  POST /api/comments/{comment_id}/reply → answered the card (by {author})",
                  flush=True)
        if auto_reopened:
            print(f"  POST /api/comments/{comment_id}/reply → user reply auto-reopened "
                  f"from {reopened_from} (by {author})", flush=True)
        self._respond(200, json.dumps(found[1], ensure_ascii=False).encode(), "application/json")

    def _v2_post_archive(self, comment_id: str, parsed):
        author = self._author(parsed)
        with _locked_store(self.artifact_dir):
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
        with _locked_store(self.artifact_dir):
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
        with _locked_store(self.artifact_dir):
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
        with _locked_store(self.artifact_dir):
            store = self._v2_load()
            flagged_count = 0
            flagged_ids = []
            feedback = []
            now = _now_iso()
            for anchor_id, items in store.get("anchors", {}).items():
                for c in items:
                    if _comment_needs_push(c):
                        feedback.append(dict(c))
                        c["flagged_for_session"] = True
                        c["flagged_at"] = now
                        c["flagged_by"] = author
                        flagged_count += 1
                        flagged_ids.append(c.get("id"))
            delivery = self._compute_delivery()
            if flagged_ids:
                self._queue_feedback_delivery(delivery, feedback, author)
                self._v2_save(store)
            else:
                delivery["delivery"] = "noop"
        if flagged_ids:
            self._wake_feedback_owner()
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
        with _locked_store(self.artifact_dir):
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
            delivery = self._compute_delivery()
            self._queue_feedback_delivery(delivery, [found[1]], author, anchor_id=found[0])
            self._v2_save(store)
        self._wake_feedback_owner()
        print(f"  POST /api/comments/{comment_id}/push → {delivery['delivery']}, monitors={delivery['monitor_count']}, by {author}", flush=True)
        self._respond(200, json.dumps({
            "ok": True,
            **delivery,
            "flagged_count": 1,
            "comment_ids": [comment_id],
        }, ensure_ascii=False).encode(), "application/json")

    def _queue_feedback_delivery(self, delivery, comments, author, **extra):
        """Explicit Send feedback uses the same durable owner outbox as Finish review."""
        from .categories import comment_category
        owner = self._read_meta().get("owner") or {}
        fingerprint = {"comments": [{key: value for key, value in c.items()
                                     if key not in ("flagged_at", "flagged_by", "flagged_for_session")}
                                    for c in comments], "author": author, "owner": owner.get("owner_session")}
        delivery["delivery_id"] = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()[:24]
        comment_ids = [c["id"] for c in comments]
        _bus_append(self.bus_dir, self.slug, {
            "event": "session_push", **delivery, "round": True, "automatic_delivery": True,
            "owner_session": owner.get("owner_session"), "owner_target": owner.get("target"),
            "comment_count": len(comment_ids), "comment_ids": comment_ids, "author": author, **extra,
        })
        answers = []
        for comment in comments:
            decision = comment.get("decision") or {}
            human_replies = [reply for reply in comment.get("replies", [])
                             if not str(reply.get("author", "")).startswith("agent:")]
            reply = max(human_replies, key=lambda r: _iso_timestamp(r.get("ts")), default={})
            if _iso_timestamp(reply.get("ts")) > _iso_timestamp(decision.get("ts")):
                decision = {"verdict": "comment", "text": reply.get("text", ""), "by": reply.get("author")}
            answers.append({"comment_id": comment["id"], "number": comment.get("number"),
                "category": comment_category(comment),
                "prompt": (comment.get("decision_request") or {}).get("prompt", ""),
                "verdict": decision.get("verdict", "comment"),
                "text": decision.get("text") or reply.get("text") or comment.get("text", ""),
                "by": decision.get("by") or reply.get("author") or comment.get("author")})
        from .review_history import save_round
        save_round(self.artifact_dir, {"id": delivery["delivery_id"], "ts": _now_iso(), "by": author,
                                      "version": self._read_meta().get("current"), "note": None,
                                      "answers": answers, "edits": [], "snapshot": True})

    def _wake_feedback_owner(self):
        if record := self._registered_record():
            from .delivery import dispatch_record
            threading.Thread(target=dispatch_record, args=(record, _monitor_project(self.bus_dir), self.slug), daemon=True).start()

    # `comment` is the free-text answer path; a reviewer's reply on an
    # unanswered card is recorded as one (see _v2_post_reply).
    _DECISION_VERDICTS = ("accept", "reject", "changes", "comment", "select")
    # The advertised set: what a current chrome should render as buttons.
    # "select" is not a button — it is what a click on an option with a
    # custom id posts. A chrome that does not find it here posts `comment`
    # for those clicks, as it did before D3.
    _DECISION_VERDICTS_OFFERED = ("accept", "reject", "changes", "comment", "select")
    # Every verdict answers the card. `comment` is the free-text answer.
    _DECISION_ANSWERS = ("accept", "reject", "changes", "comment", "select")
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
    _DECISION_COMMENT_PREFIX = "💬 Answer in words: "
    # D3: the reviewer picked one of the card's own options. `text` is the
    # option's label, plus any note after a blank line.
    _DECISION_SELECT_PREFIX = "☑ Selected: "
    # Prior-verdict label used in revision reply text ("was ✗ Rejected"). Kept
    # distinct from _DECISION_REPLY_TEXT (which has no text-verdict entry)
    # since a revision's PRIOR verdict can be any of the four.
    _DECISION_PRIOR_LABEL = {"accept": "✓ Accepted", "reject": "✗ Rejected",
                             "changes": "↻ Changes requested", "comment": "Answered in words",
                             "select": "☑ Selected"}

    @classmethod
    def _is_answered(cls, decision) -> bool:
        """True when this decision answers its card."""
        return bool(isinstance(decision, dict)
                    and decision.get("verdict") in cls._DECISION_ANSWERS)

    def _v2_post_decision(self, comment_id: str, parsed):
        """Resolve a decision_request: accept / reject / changes, or a
        free-text answer (`comment`).

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

        with _locked_store(self.artifact_dir):
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
            if (isinstance(prior_decision, dict) and prior_decision.get("round_pending")
                    and prior_decision.get("by") not in self._reviewer_authors(author)):
                return self._respond(403, b'{"error":"another reviewer owns the pending answer"}')
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
        """Commit one completed review round before clearing pending answers.

        The fsynced bus is the durable outbox. A retry mints the same delivery
        ID until the pending flags are saved, preventing repeated input.
        """
        from .categories import comment_category
        from .copy_state import load_copy, submit_revisions
        from .review_history import _events
        payload = self._bounded_json_body()
        if payload is None:
            return
        if set(payload) - {"note", "version"} or not isinstance(payload.get("note", ""), (str, type(None))):
            return self._respond(400, b'{"error":"invalid round fields"}')
        note = str(payload.get("note") or "").strip() or None
        author = self._author(parsed)
        reviewer_authors = self._reviewer_authors(author)
        with _locked_store(self.artifact_dir):
            store = self._v2_load()
            now = _now_iso()
            # A persisted round is the receipt if a process died between the
            # copy/comment writes. Clear only its exact activities on retry.
            receipts = list(_events(self.artifact_dir / "rounds.ndjson"))
            submitted_answers = {(a.get("comment_id"), a.get("by"), a.get("ts"), a.get("verdict")): r.get("ts")
                                 for r in receipts for a in r.get("answers", []) if a.get("ts")}
            submitted_edits = {e.get("revision_id") for r in receipts for e in r.get("edits", [])
                               if e.get("by") in reviewer_authors}
            if submitted_edits:
                submit_revisions(self.artifact_dir, submitted_edits, reviewer_authors)
            recovered = False
            for items in store.get("anchors", {}).values():
                for c in items:
                    d = c.get("decision") or {}
                    if (d.get("round_pending") and d.get("by") in reviewer_authors
                            and (c["id"], d.get("by"), d.get("ts"), d.get("verdict")) in submitted_answers):
                        d.pop("round_pending", None)
                        c.update(flagged_for_session=True, flagged_at=submitted_answers[(c["id"], d.get("by"), d.get("ts"), d.get("verdict"))], flagged_by=author)
                        recovered = True
                    reopen = (c.get("reopened") or [{}])[-1]
                    if (c.get("round_pending") and reopen.get("by") in reviewer_authors
                            and (c["id"], reopen.get("by"), reopen.get("ts"), "reopen") in submitted_answers):
                        c.pop("round_pending", None)
                        c.update(flagged_for_session=True, flagged_at=submitted_answers[(c["id"], reopen.get("by"), reopen.get("ts"), "reopen")], flagged_by=author)
                        recovered = True
            if recovered:
                self._v2_save(store)
            pending = []
            reopens = []
            edits = [{"category": "library", "block_id": block["id"], "revision_id": revision["id"],
                      "title": block["title"], "delta": revision["delta"], "base_revision": revision.get("base_revision"),
                      "by": revision["author"]["id"], "ts": revision["created_at"]}
                     for block in load_copy(self.artifact_dir)["blocks"] for revision in block["revisions"]
                     if revision.get("round_pending") and revision["author"]["id"] in reviewer_authors]
            cleared_archived = False
            verdict_counts = {v: 0 for v in self._DECISION_VERDICTS}
            undecided_ids = []
            for items in store.get("anchors", {}).values():
                for c in items:
                    decision = c.get("decision")
                    if c.get("status") in ("archived", "resolved_in_version"):
                        if isinstance(decision, dict) and decision.get("by") in reviewer_authors and decision.get("round_pending"):
                            decision.pop("round_pending", None)
                            cleared_archived = True
                        continue
                    if (c.get("decision_request") and not self._is_answered(decision)
                            and c.get("status") != "addressed_by_agent"):
                        undecided_ids.append(c.get("id"))
                    if isinstance(decision, dict) and decision.get("round_pending") and decision.get("by") in reviewer_authors:
                        pending.append(c)
                        if decision.get("verdict") in verdict_counts:
                            verdict_counts[decision["verdict"]] += 1
                    if c.get("round_pending") and c.get("reopened") and c["reopened"][-1].get("by") in reviewer_authors:
                        reopens.append(c)
            comment_ids = list(dict.fromkeys(c["id"] for c in pending + reopens))
            if not comment_ids and not edits and not note:
                if cleared_archived:
                    self._v2_save(store)
                self._respond(200, json.dumps({"ok": True, "delivery": "noop", "comment_count": 0,
                                              "comment_ids": [], "verdict_counts": verdict_counts,
                                              "undecided_count": len(undecided_ids),
                                              "edits": [], "edit_count": 0,
                                              "undecided_ids": undecided_ids}).encode(), "application/json")
                return
            owner = self._read_meta().get("owner") or {}
            version = payload.get("version") or self._read_meta().get("current")
            if version and (not isinstance(version, str) or not _VERSION_ID.fullmatch(version)
                            or version not in {h.get("version") for h in self._read_meta().get("history", [])}):
                return self._respond(400, b'{"error":"unknown review version"}')
            fingerprint = {"answers": [(c["id"], c["decision"]) for c in pending],
                           "edits": edits, "reopens": [(c["id"], c["reopened"][-1]) for c in reopens],
                           "note": note, "owner": owner.get("owner_session"),
                           "version": version}
            delivery = self._compute_delivery()
            delivery["delivery_id"] = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()[:24]
            event = {"comment_ids": comment_ids, "verdict_counts": verdict_counts,
                     "undecided_ids": undecided_ids, "note": note, "edits": edits, "edit_count": len(edits), **self._session_fields()}
            answers = [{"comment_id": c["id"], "number": c.get("number"),
                        "category": comment_category(c),
                        "prompt": (c.get("decision_request") or {}).get("prompt", c.get("text", "")),
                        "verdict": c["decision"]["verdict"], "text": c["decision"].get("text", ""),
                        "by": c["decision"].get("by"), "ts": c["decision"].get("ts")} for c in pending]
            answers += [{"comment_id": c["id"], "number": c.get("number"), "category": "findings",
                         "prompt": (c.get("finding") or {}).get("title", c.get("text", "")),
                         "verdict": "reopen", "text": c["reopened"][-1]["text"],
                         "by": c["reopened"][-1]["by"], "ts": c["reopened"][-1]["ts"]} for c in reopens]
            _bus_append(self.bus_dir, self.slug, {"event": "round_submitted", "by": author,
                                                "round_id": delivery["delivery_id"], "version": version, "answers": answers, **event})
            _bus_append(self.bus_dir, self.slug, {
                "event": "session_push", **delivery, "round": True, "automatic_delivery": True,
                "owner_session": owner.get("owner_session"), "owner_target": owner.get("target"),
                "comment_count": len(comment_ids), "author": author, **event,
            })
            from .review_history import save_round
            save_round(self.artifact_dir, {"id": delivery["delivery_id"], "ts": now, "by": author,
                                          "version": version, "note": note, "answers": answers, "edits": edits, "snapshot": True})
            for c in pending:
                c["decision"].pop("round_pending", None)
                c.update(flagged_for_session=True, flagged_at=now, flagged_by=author)
            for c in reopens:
                c.pop("round_pending", None)
                c.update(flagged_for_session=True, flagged_at=now, flagged_by=author)
            if edits:
                submit_revisions(self.artifact_dir, {edit["revision_id"] for edit in edits}, reviewer_authors)
            self._v2_save(store)

        def wake_owner():
            from .delivery import dispatch_record
            try:
                state = json.loads((STATE_DIR / f"{_monitor_project(self.bus_dir)}.json").read_text())
                record = state.get("slugs", {}).get(self.slug)
                if record:
                    dispatch_record(record, _monitor_project(self.bus_dir), self.slug)
            except (OSError, ValueError, TimeoutError) as exc:
                print(f"WARN: automatic delivery: {exc}", flush=True)
        threading.Thread(target=wake_owner, daemon=True).start()
        self._respond(200, json.dumps({"ok": True, **delivery,
                                      "comment_count": len(comment_ids), **event,
                                      "undecided_count": len(undecided_ids)},
                                     ensure_ascii=False).encode(), "application/json")

    def _v2_post_rounds_discard(self, parsed):
        """POST /api/rounds/discard — drop the round_pending flags WITHOUT
        pushing. The verdicts themselves stay recorded (reversible via
        "Change verdict"); they simply never go out as a round. Emits
        `round_discarded`, never a session_push."""
        author = self._author(parsed)
        reviewer_authors = self._reviewer_authors(author)
        with _locked_store(self.artifact_dir):
            store = self._v2_load()
            comment_ids = []
            for anchor_id, items in store.get("anchors", {}).items():
                for c in items:
                    d = c.get("decision")
                    if isinstance(d, dict) and d.get("round_pending") and d.get("by") in reviewer_authors:
                        d.pop("round_pending", None)
                        comment_ids.append(c.get("id"))
            if comment_ids:
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
                meta = json.loads(p.read_text(encoding="utf-8"))
                record = self._registered_record()
                if record:
                    from .workspace import owner_data
                    if owner := owner_data(record):
                        meta["owner"] = owner
                return meta
            except Exception:
                return {}
        return {}

    def _registered_record(self) -> dict | None:
        try:
            state = json.loads((STATE_DIR / f"{_monitor_project(self.bus_dir)}.json").read_text())
            record = state.get("slugs", {}).get(self.slug)
            if (isinstance(record, dict) and Path(record.get("slug_dir") or "").resolve() == self.artifact_dir.resolve()
                    and record.get("port") == self.server.server_address[1]):
                return record
        except (OSError, ValueError, TypeError):
            pass
        return None

    def _project_payload(self) -> dict:
        from .project_state import load_project
        data = load_project(self.artifact_dir)
        record = self._registered_record()
        if record and self._identity()["authenticated"]:
            from .urls import page_url, redact_review_key
            from .workspace import workspace_tab_records
            links = {redact_review_key(page_url(child)): page_url(child)
                     for _, _, child in workspace_tab_records(record)}
            for tab in data.get("tabs", []):
                if tab.get("url") in links and links[tab["url"]]:
                    tab["url"] = links[tab["url"]]
        return data

    @staticmethod
    def _comment_category_fields(payload):
        from .categories import CATEGORIES, validate_plan_id
        result = {}
        if "category" in payload:
            if payload["category"] not in CATEGORIES:
                raise DecisionRequestError("invalid comment category")
            result["category"] = payload["category"]
        if "doc" in payload:
            doc = payload["doc"]
            try:
                if not isinstance(doc, str) or not doc.startswith("plan:"):
                    raise ValueError
                validate_plan_id(doc[5:])
            except ValueError as exc:
                raise DecisionRequestError("invalid plan document") from exc
            if result.get("category", "plans") != "plans":
                raise DecisionRequestError("plan documents require category plans")
            result.update(doc=doc, category="plans")
        if "finding" in payload:
            finding = payload["finding"]
            if (not isinstance(finding, dict) or set(finding) != {"set", "title"}
                    or not all(isinstance(v, str) and 0 < len(v) <= 200 for v in finding.values())):
                raise DecisionRequestError("finding needs set and title")
            try:
                validate_plan_id(finding["set"])
            except ValueError as exc:
                raise DecisionRequestError("invalid finding set") from exc
            if result.get("category", "findings") != "findings":
                raise DecisionRequestError("finding metadata requires category findings")
            result.update(finding=finding, category="findings")
        return result

    def _get_categories(self):
        from .categories import CATEGORIES, category_counts, comment_category, list_plans, load_categories
        from .copy_state import load_copy
        from .project_state import linked_pages
        try:
            with _locked_store(self.artifact_dir):
                author = self._author()
                with _READ_LOCK:
                    read = self._reviewer_state(_load_read_state(self.artifact_dir), author)
                counts = category_counts(self.artifact_dir, author, read_state=read)
                plans = list_plans(self.artifact_dir)
                category_data = load_categories(self.artifact_dir)
                library = load_copy(self.artifact_dir)
                store = self._v2_load()
                present = {comment_category(c) for items in store["anchors"].values() for c in items}
                available = {"review": True, "library": bool(library["blocks"]) or "library" in present,
                             "findings": bool(category_data["findings_sets"]) or "findings" in present,
                             "plans": bool(plans) or "plans" in present}
                record = self._registered_record()
                links = linked_pages(record) if record else []
            result = {"categories": [{"id": c, "label": c.title(), "available": available[c], "counts": counts[c]} for c in CATEGORIES],
                      "findings_sets": category_data["findings_sets"], "plans": plans,
                      "library": {"groups": library.get("groups", [])}, "linked_pages": links}
            return self._respond(200, json.dumps(result, ensure_ascii=False).encode(), cache_control="no-store")
        except (ValueError, OSError) as exc:
            return self._respond(400, json.dumps({"error": str(exc)}).encode())

    def _bounded_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._respond(400, b'{"error":"invalid content length"}')
            return None
        if not 0 < length <= 256 * 1024:
            self._respond(413, b'{"error":"body exceeds limit"}')
            return None
        try:
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("expected object")
            return payload
        except (ValueError, UnicodeError) as exc:
            self._respond(400, json.dumps({"error": str(exc)}).encode())
            return None

    def _post_finding_reopen(self, comment_id):
        from .categories import reopen_finding
        payload = self._bounded_json_body()
        if payload is None:
            return
        if set(payload) != {"text"}:
            return self._respond(400, b'{"error":"text required"}')
        author = self._author()
        if not author or author == "anonymous" or author.startswith("agent:"):
            return self._respond(403, b'{"error":"reviewer identity required"}')
        try:
            comment = reopen_finding(self.artifact_dir, comment_id, by=author, text=payload["text"])
            _bus_append(self.bus_dir, self.slug, {"event": "finding_reopened", "comment_id": comment_id,
                                                 "by": author, "deferred": True})
            return self._respond(200, json.dumps(comment).encode())
        except PermissionError as exc:
            return self._respond(403, json.dumps({"error": str(exc)}).encode())
        except KeyError:
            return self._respond(404, b'{"error":"finding not found"}')
        except ValueError as exc:
            return self._respond(400, json.dumps({"error": str(exc)}).encode())

    def _post_copy_proposal(self, block_id: str, *, restore=False):
        from .copy_state import add_browser_revision, restore_revision
        payload = self._bounded_json_body()
        if payload is None:
            return
        try:
            expected = {"revision_id", "request_id"} if restore else {"delta", "base_revision", "request_id"}
            if set(payload) != expected:
                raise ValueError("invalid copy revision fields")
            identity = self._identity()
            if not identity["email"] or identity["email"].startswith("agent:"):
                return self._respond(403, b'{"error":"reviewer identity required"}')
            author = {"id": identity["email"], "name": identity.get("name")}
            with _locked_store(self.artifact_dir):
                if restore:
                    document = restore_revision(self.artifact_dir, block_id, payload["revision_id"], author,
                                                request_id=payload["request_id"])
                else:
                    document = add_browser_revision(self.artifact_dir, block_id, payload["delta"], author,
                                                    base_revision=payload["base_revision"], request_id=payload["request_id"])
            self._respond(200, json.dumps(document, ensure_ascii=False).encode(), cache_control="no-store")
        except (ValueError, TypeError) as exc:
            code = 403 if "different proposal" in str(exc) else 400
            self._respond(code, json.dumps({"error": str(exc)}).encode())
        except KeyError:
            self._respond(404, b'{"error":"copy block or revision not found"}')
        except OSError:
            self._respond(500, b'{"error":"copy proposal could not be saved; retry with the same request id"}')

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
        record = self._reviewer_state(data, author)
        self._respond(200, json.dumps({"author": author, "seen": record}, ensure_ascii=False).encode(), "application/json")

    def _v2_get_identity(self, parsed):
        identity = self._identity()
        identity["reviewer_authors"] = sorted(self._reviewer_authors(identity["email"] or "anonymous"))
        self._respond(200, json.dumps(identity, ensure_ascii=False).encode(), "application/json")

    def _reviewer_authors(self, author: str) -> set[str]:
        """Operator-declared account aliases preserve legacy draft authors."""
        authors = {author}
        try:
            config = tomllib.loads(PROJECTS_TOML.read_text())
            section = {**config.get("defaults", {}), **config.get(_monitor_project(self.bus_dir), {})}
            aliases = section.get("reviewer_aliases", {}).get(author, [])
            if isinstance(aliases, list) and len(aliases) <= 20:
                authors.update(value for value in aliases if isinstance(value, str) and 0 < len(value) <= 320)
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        return authors

    def _reviewer_state(self, data: dict, author: str) -> dict:
        merged = {}
        for alias in sorted(self._reviewer_authors(author)):
            record = data.get(_author_key(alias), {})
            if not isinstance(record, dict):
                continue
            for key, value in record.items():
                if isinstance(value, dict) and str(value.get("ts") or "") >= str(merged.get(key, {}).get("ts") or ""):
                    merged[key] = value
        return merged

    def _v2_get_share_link(self):
        if not self._is_funnel_origin() or not self._identity()["authenticated"]:
            return self._respond(403, b'{"error":"review access required"}')
        from .urls import page_url
        state = json.loads((STATE_DIR / f"{_monitor_project(self.bus_dir)}.json").read_text())
        url = page_url(state["slugs"][self.slug])
        self._respond(200, json.dumps({"url": url}).encode(), cache_control="no-store")

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
        record = self._reviewer_state(data, author)
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
    def _is_public_static(self, relative: str) -> bool:
        parts = relative.split("/")
        if any(not part or part in (".", "..") or part.startswith(".") for part in parts):
            return False
        name = parts[-1].lower()
        if (name in {"comments.json", "current.meta.json", "project.json", "cards.json", "metrics.json",
                     "seen.json", "read-state.json", "weekly-source.md"}
                or name.endswith((".comments.json", ".tmp", ".bak", ".backup", ".lock", ".log", ".ndjson", ".sqlite", ".db", "~"))):
            return False
        if parts[0] in ("assets", "attachments") and len(parts) > 1:
            return True  # These directories are an explicit publication boundary.
        if len(parts) == 1:
            return (relative == self.artifact_file or relative == "current.html"
                    or Path(name).suffix in {".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico",
                                            ".webp", ".avif", ".woff", ".woff2", ".ttf", ".mp4", ".webm", ".ogg", ".mp3", ".wav"})
        return (parts[0] == "versions" and len(parts) == 2 and not self._has_content_dir()
                and Path(name).suffix == ".html" and bool(_VERSION_ID.fullmatch(Path(name).stem)))

    def _serve_static(self, url_path):
        try:
            rel = urllib.parse.unquote(url_path, errors="strict").lstrip("/") or self._default_file()
        except UnicodeError:
            return self._respond(400, b"Invalid path")
        if "\\" in rel or any(ord(char) < 32 for char in rel):
            return self._respond(404, b"Not found")
        try:
            target = _contained_path(self.artifact_dir, rel)
        except PermissionError:
            self._respond(403, b"Forbidden")
            return
        if self.v2_mode and target == self._meta_path().resolve():
            return self._v2_get_meta()  # Preserve normalized aliases through the filtered API, never raw bytes.
        if not self._is_public_static(rel):
            return self._respond(404, b"Not found")
        if not self._is_public_static(target.relative_to(self.artifact_dir.resolve()).as_posix()):
            return self._respond(404, b"Not found")
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
                 cache_control: str = "no-cache", conditional: bool = False, extra_headers: dict | None = None):
        etag = '"' + hashlib.sha256(body).hexdigest() + '"' if conditional else None
        if code == 200 and self.command == "GET" and etag and self.headers.get("If-None-Match") == etag:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "private, no-cache")
            self.end_headers()
            return
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        if etag:
            self.send_header("ETag", etag)
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
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
    proxy_urls: tuple[str, ...] = (),
    trusted_access_origins: tuple[str, ...] = (),
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
    BoundHandler.proxy_urls = proxy_urls
    BoundHandler.trusted_access_origins = trusted_access_origins
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
    parser.add_argument("--strict-port", action="store_true", help="exit if the requested port is unavailable")
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
        if args.strict_port and port != args.port:
            parser.error(f"requested port {args.port} is unavailable; no alternate port selected")
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
        server = ReviewHTTPServer(("localhost", port), handler)
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
        if args.slug_dir:
            def delivery_loop():
                from .delivery import dispatch_record
                while True:
                    try:
                        state_path = STATE_DIR / f"{_monitor_project(bus_dir)}.json"
                        state = json.loads(state_path.read_text())
                        record = state.get("slugs", {}).get(args.slug or Path(args.slug_dir).name)
                        if record:
                            dispatch_record(record, _monitor_project(bus_dir), args.slug or Path(args.slug_dir).name)
                    except (OSError, ValueError, TimeoutError):
                        pass
                    threading.Event().wait(30)
            threading.Thread(target=delivery_loop, daemon=True).start()
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")


if __name__ == "__main__":
    main()
