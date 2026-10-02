"""Persistent project modules, independent of review versions and feedback."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

MAX_PAYLOAD_BYTES = 64 * 1024
MAX_MODULES = 12
MAX_ITEMS = 50
MAX_TEXT_LENGTH = 2000
MAX_LABEL_LENGTH = 160
_SAFE_ID = re.compile(r"[a-zA-Z0-9_-]+\Z")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _object(value: Any, allowed: set[str], required: set[str], location: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{location} must be an object")
    if any(key not in allowed for key in value):
        raise ValueError(f"{location} contains unsupported fields")
    if not required.issubset(value):
        raise ValueError(f"{location} is missing required fields")
    return value


def _string(value: Any, location: str, maximum: int = MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{location} must be a string")
    if len(value) > maximum:
        raise ValueError(f"{location} exceeds {maximum} characters")
    return value


def _url(value: Any, location: str) -> str:
    value = _string(value, location)
    # Browsers and urllib disagree on backslashes and stripped whitespace.
    # Reject those spellings rather than checking one URL and rendering another.
    if any(ord(char) <= 32 or ord(char) == 127 for char in value) or "\\" in value:
        raise ValueError(f"{location} must be an unambiguous HTTP or HTTPS URL")
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            raise ValueError
        if parsed.username is not None or parsed.password is not None:
            raise ValueError
        parsed.port  # Reject malformed ports as well as malformed IPv6 hosts.
    except ValueError as exc:
        raise ValueError(f"{location} must be an HTTP or HTTPS URL without userinfo") from exc
    return value


def _serialize(data: dict) -> bytes:
    try:
        encoded = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ValueError("project must contain valid JSON text") from exc
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise ValueError(f"project exceeds {MAX_PAYLOAD_BYTES} bytes")
    return encoded


def validate_project(data: Any) -> dict:
    """Validate and copy project data; absent timestamps are generated in UTC."""
    data = _object(data, {"schema_version", "title", "updated_at", "modules", "tabs"}, {"modules"}, "project")
    version = data.get("schema_version", 1)
    if type(version) is not int or version != 1:
        raise ValueError("project.schema_version must be 1")
    modules = data["modules"]
    if not isinstance(modules, list) or len(modules) > MAX_MODULES:
        raise ValueError(f"project.modules must be an array of at most {MAX_MODULES} modules")

    normalized: dict[str, Any] = {"schema_version": 1}
    if "title" in data:
        normalized["title"] = _string(data["title"], "project.title", MAX_LABEL_LENGTH)
    if "updated_at" in data:
        timestamp = _string(data["updated_at"], "project.updated_at")
        try:
            parsed_timestamp = datetime.fromisoformat(timestamp)
            if parsed_timestamp.tzinfo is None:
                raise ValueError
        except ValueError as exc:
            raise ValueError("project.updated_at must be an ISO timestamp with a timezone") from exc
        normalized["updated_at"] = timestamp
    else:
        normalized["updated_at"] = _timestamp()

    if "tabs" in data:
        tabs = data["tabs"]
        if not isinstance(tabs, list) or len(tabs) > 8:
            raise ValueError("project.tabs must be an array of at most 8 tabs")
        normalized["tabs"] = []
        ids = {"progress", "feedback"}
        for tab in tabs:
            tab = _object(tab, {"id", "label", "url"}, {"id", "label", "url"}, "project.tabs")
            tab_id = _string(tab["id"], "tab.id", 80)
            if not _SAFE_ID.fullmatch(tab_id) or tab_id in ids:
                raise ValueError("tab ids must be unique; progress and feedback are reserved")
            ids.add(tab_id)
            normalized["tabs"].append({"id": tab_id, "label": _string(tab["label"], "tab.label", 24),
                                       "url": _url(tab["url"], "tab.url")})
    normalized["modules"] = []
    ids: set[str] = set()
    for index, module in enumerate(modules):
        location = f"project.modules[{index}]"
        module = _object(module, {"id", "title", "kind", "items"}, {"id", "title", "kind", "items"}, location)
        module_id = _string(module["id"], f"{location}.id")
        if not _SAFE_ID.fullmatch(module_id):
            raise ValueError(f"{location}.id must contain only letters, numbers, underscores, or hyphens")
        if module_id in ids:
            raise ValueError("project module ids must be unique")
        ids.add(module_id)
        kind = module["kind"]
        if not isinstance(kind, str) or kind not in {"links", "progress", "notes"}:
            raise ValueError(f"{location}.kind must be links, progress, or notes")
        items = module["items"]
        if not isinstance(items, list) or len(items) > MAX_ITEMS:
            raise ValueError(f"{location}.items must be an array of at most {MAX_ITEMS} items")
        normalized_module = {
            "id": module_id,
            "title": _string(module["title"], f"{location}.title", MAX_LABEL_LENGTH),
            "kind": kind,
            "items": [],
        }
        for item_index, item in enumerate(items):
            item_location = f"{location}.items[{item_index}]"
            if kind == "notes":
                item = _object(item, {"text"}, {"text"}, item_location)
                normalized_item = {"text": _string(item["text"], f"{item_location}.text")}
            else:
                optional = "description" if kind == "links" else "detail"
                field = "url" if kind == "links" else "status"
                item = _object(item, {"label", field, optional, "url", "failed_count"}, {"label", field}, item_location)
                normalized_item = {"label": _string(item["label"], f"{item_location}.label", MAX_LABEL_LENGTH)}
                if kind == "links":
                    normalized_item["url"] = _url(item["url"], f"{item_location}.url")
                else:
                    status = item["status"]
                    if not isinstance(status, str) or status not in {"todo", "in_progress", "done", "blocked"}:
                        raise ValueError(f"{item_location}.status must be todo, in_progress, done, or blocked")
                    normalized_item["status"] = status
                if optional in item:
                    normalized_item[optional] = _string(item[optional], f"{item_location}.{optional}")
                if kind == "progress" and "url" in item:
                    normalized_item["url"] = _url(item["url"], f"{item_location}.url")
                if "failed_count" in item:
                    count = item["failed_count"]
                    if kind != "progress" or type(count) is not int or not 1 <= count <= 999:
                        raise ValueError("failed_count must be a positive integer on a progress item")
                    normalized_item["failed_count"] = count
            normalized_module["items"].append(normalized_item)
        normalized["modules"].append(normalized_module)

    _serialize(normalized)
    return normalized


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("project.json contains duplicate fields")
        result[key] = value
    return result


def load_project(slug_dir: Path | str) -> dict:
    """Load project.json, returning empty modules when no project was saved."""
    path = Path(slug_dir) / "project.json"
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_PAYLOAD_BYTES + 1)
    except FileNotFoundError:
        return {"schema_version": 1, "modules": []}
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise ValueError(f"project exceeds {MAX_PAYLOAD_BYTES} bytes")
    try:
        data = json.loads(raw, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
        raise ValueError("project.json is invalid JSON") from exc
    return validate_project(data)


def save_project(slug_dir: Path | str, data: Any) -> dict:
    """Validate then atomically replace project.json with a fresh update timestamp."""
    normalized = validate_project(data)
    previous = load_project(slug_dir)
    if {k: v for k, v in previous.items() if k != "updated_at"} == {k: v for k, v in normalized.items() if k != "updated_at"}:
        return previous
    normalized["updated_at"] = _timestamp()
    encoded = _serialize(normalized)
    slug_dir = Path(slug_dir)
    slug_dir.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".project.", suffix=".tmp", dir=slug_dir, delete=False) as target:
            temporary = Path(target.name)
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, slug_dir / "project.json")
        temporary = None
        directory_fd = os.open(slug_dir, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return normalized
