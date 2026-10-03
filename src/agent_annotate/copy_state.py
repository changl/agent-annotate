"""Formatted copy drafts and immutable proposals, separate from review rounds.

Delta documents accept text inserts with bold/italic/underline/strike/code/link,
newline header (1-3), list (ordered/bullet), blockquote, and indent (1-4).
No embeds, HTML, colors, fonts, arbitrary attributes, or change operations.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

MAX_PAYLOAD_BYTES = 4 * 1024 * 1024
MAX_DELTA_CHARS = 50_000
_ID = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")
_INLINE = {"bold", "italic", "underline", "strike", "code"}


def _object(value: Any, fields: set[str], required: set[str], label: str) -> dict:
    if not isinstance(value, dict) or not required.issubset(value) or set(value) - fields:
        raise ValueError(f"{label} has invalid fields")
    return value


def _text(value: Any, label: str, maximum: int = 200) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"{label} must be nonempty text of at most {maximum} characters")
    if any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise ValueError(f"{label} contains control characters")
    return value


def _id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{label} must be a short identifier")
    return value


def _link(value: Any) -> str:
    value = _text(value, "copy link", 2000)
    if any(ord(char) <= 32 or ord(char) == 127 for char in value) or "\\" in value:
        raise ValueError("copy links must be unambiguous HTTP, HTTPS, or mailto URLs")
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() == "mailto":
            if not parsed.path or parsed.netloc:
                raise ValueError
        elif (parsed.scheme.lower() not in {"https", "http"} or not parsed.hostname
              or parsed.username is not None or parsed.password is not None):
            raise ValueError
        parsed.port
    except ValueError as exc:
        raise ValueError("copy links must use HTTP, HTTPS, or mailto without credentials") from exc
    return value


def validate_delta(value: Any) -> dict:
    """Accept Quill documents, never operations, arbitrary HTML, or embeds."""
    value = _object(value, {"ops"}, {"ops"}, "copy delta")
    ops = value["ops"]
    if not isinstance(ops, list) or not 1 <= len(ops) <= 5000:
        raise ValueError("copy delta.ops must contain 1 to 5000 text inserts")
    normalized, size = [], 0
    for op in ops:
        op = _object(op, {"insert", "attributes"}, {"insert"}, "copy delta operation")
        text = _text(op["insert"], "copy text", MAX_DELTA_CHARS)
        size += len(text)
        attrs = op.get("attributes", {})
        attrs = _object(attrs, _INLINE | {"header", "list", "blockquote", "link", "indent"}, set(), "copy formatting")
        clean = {}
        for key, item in attrs.items():
            if key in _INLINE | {"blockquote"}:
                if item is not True:
                    raise ValueError(f"copy formatting.{key} must be true")
            elif key == "header":
                if type(item) is not int or item not in {1, 2, 3}:
                    raise ValueError("copy headings must be level 1, 2, or 3")
            elif key == "list":
                if not isinstance(item, str) or item not in {"ordered", "bullet"}:
                    raise ValueError("copy lists must be ordered or bullet")
            elif key == "indent":
                if type(item) is not int or not 1 <= item <= 4:
                    raise ValueError("copy indentation must be between 1 and 4")
            elif key == "link":
                item = _link(item)
            clean[key] = item
        if len({"header", "list", "blockquote"} & set(clean)) > 1:
            raise ValueError("copy line formats cannot be combined")
        normalized.append({"insert": text, **({"attributes": clean} if clean else {})})
    if size > MAX_DELTA_CHARS or not normalized[-1]["insert"].endswith("\n"):
        raise ValueError(f"copy document must end with a newline and be at most {MAX_DELTA_CHARS} characters")
    return {"ops": normalized}


def _author(value: Any) -> dict:
    value = _object(value, {"id", "name"}, {"id"}, "copy author")
    return {"id": _text(value["id"], "copy author.id", 500),
            **({"name": _text(value["name"], "copy author.name", 200)} if value.get("name") else {})}


def _serialize(data: dict) -> bytes:
    try:
        encoded = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    except (ValueError, TypeError, UnicodeEncodeError) as exc:
        raise ValueError("copy must contain valid JSON text") from exc
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise ValueError("copy document exceeds 4 MB")
    return encoded


def validate_copy(value: Any) -> dict:
    value = _object(value, {"schema_version", "blocks"}, {"blocks"}, "copy")
    if type(value.get("schema_version", 1)) is not int or value.get("schema_version", 1) != 1:
        raise ValueError("copy.schema_version must be 1")
    if not isinstance(value["blocks"], list) or len(value["blocks"]) > 500:
        raise ValueError("copy.blocks must be an array of at most 500 blocks")
    result, ids = {"schema_version": 1, "blocks": []}, set()
    for block in value["blocks"]:
        block = _object(block, {"id", "title", "current", "revisions"}, {"id", "title", "current", "revisions"}, "copy block")
        block_id = _id(block["id"], "copy block.id")
        if block_id in ids:
            raise ValueError("copy block ids must be unique")
        ids.add(block_id)
        revisions = block["revisions"]
        if not isinstance(revisions, list) or not 1 <= len(revisions) <= 1000:
            raise ValueError("copy block.revisions must contain 1 to 1000 revisions")
        clean_revisions, revision_ids = [], set()
        for revision in revisions:
            revision = _object(revision, {"id", "created_at", "author", "status", "delta", "base_revision"},
                               {"id", "created_at", "author", "status", "delta"}, "copy revision")
            revision_id = _id(revision["id"], "copy revision.id")
            if revision_id in revision_ids:
                raise ValueError("copy revision ids must be unique within a block")
            timestamp = _text(revision["created_at"], "copy revision.created_at", 80)
            try:
                if datetime.fromisoformat(timestamp).tzinfo is None:
                    raise ValueError
            except ValueError as exc:
                raise ValueError("copy revision.created_at must include a timezone") from exc
            if not isinstance(revision["status"], str) or revision["status"] not in {"draft", "approved", "proposed"}:
                raise ValueError("copy revision.status must be draft, approved, or proposed")
            clean = {"id": revision_id, "created_at": timestamp, "author": _author(revision["author"]),
                     "status": revision["status"], "delta": validate_delta(revision["delta"])}
            if "base_revision" in revision:
                base = _id(revision["base_revision"], "copy revision.base_revision")
                if base not in revision_ids:
                    raise ValueError("copy revision must reference an earlier base revision")
                clean["base_revision"] = base
            revision_ids.add(revision_id)
            clean_revisions.append(clean)
        current = _id(block["current"], "copy block.current")
        if current not in revision_ids:
            raise ValueError("copy block.current must reference an existing revision")
        result["blocks"].append({"id": block_id, "title": _text(block["title"], "copy block.title"),
                                 "current": current, "revisions": clean_revisions})
    _serialize(result)
    return result


def _unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("copy.json contains duplicate fields")
        result[key] = value
    return result


def load_copy(slug_dir: Path | str) -> dict:
    path = Path(slug_dir) / "copy.json"
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_PAYLOAD_BYTES + 1)
    except FileNotFoundError:
        return {"schema_version": 1, "blocks": []}
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise ValueError("copy document exceeds 4 MB")
    try:
        data = json.loads(raw, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
        raise ValueError("copy.json is invalid JSON") from exc
    return validate_copy(data)


def _write(directory: Path, data: dict) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".copy.", suffix=".tmp", dir=directory, delete=False) as target:
            temporary = Path(target.name)
            target.write(_serialize(data))
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, directory / "copy.json")
        temporary = None
        directory_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_copy(slug_dir: Path | str, data: Any) -> dict:
    """Trusted import/current-pointer updates; existing authored revisions are immutable."""
    directory = Path(slug_dir)
    normalized = validate_copy(data)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".copy.json.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        previous = load_copy(directory)
        new_blocks = {block["id"]: block for block in normalized["blocks"]}
        for old in previous["blocks"]:
            if old["id"] not in new_blocks:
                raise ValueError("existing copy blocks cannot be removed")
            new_revisions = {revision["id"]: revision for revision in new_blocks[old["id"]]["revisions"]}
            if any(new_revisions.get(revision["id"]) != revision for revision in old["revisions"]):
                raise ValueError("existing copy revisions cannot be changed or removed")
        if previous != normalized:
            _write(directory, normalized)
    return normalized


def propose_copy(slug_dir: Path | str, block_id: str, delta: Any, author: Any,
                 *, base_revision: str, request_id: str) -> dict:
    """Append a proposal once; retries preserve its author, time, and revision id."""
    _id(block_id, "copy block.id")
    _id(base_revision, "copy base_revision")
    delta, author = validate_delta(delta), _author(author)
    try:
        if not isinstance(request_id, str) or str(uuid.UUID(request_id)) != request_id:
            raise ValueError
    except (ValueError, AttributeError) as exc:
        raise ValueError("copy request_id must be a UUID") from exc
    directory = Path(slug_dir)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".copy.json.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        data = load_copy(directory)
        block = next((block for block in data["blocks"] if block["id"] == block_id), None)
        if block is None:
            raise KeyError(block_id)
        revision_id = "r_" + request_id
        existing = next((revision for revision in block["revisions"] if revision["id"] == revision_id), None)
        if existing is not None:
            if (existing["author"]["id"] != author["id"] or existing["delta"] != delta
                    or existing.get("base_revision") != base_revision):
                raise ValueError("copy request_id was already used for a different proposal")
            return data
        if base_revision not in {revision["id"] for revision in block["revisions"]}:
            raise ValueError("copy base_revision no longer exists")
        block["revisions"].append({"id": revision_id, "created_at": datetime.now(timezone.utc).isoformat(),
                                   "author": author, "status": "proposed", "base_revision": base_revision,
                                   "delta": delta})
        normalized = validate_copy(data)
        _write(directory, normalized)
        return normalized
