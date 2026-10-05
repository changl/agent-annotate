"""Optional category storage for a single review page. No services or CLI state."""
from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .copy_state import _link, _text, load_copy

CATEGORIES = ("review", "library", "findings", "plans")
MAX_PROOF_BYTES = 10 * 1024 * 1024
MAX_PLAN_BYTES = 4 * 1024 * 1024
_PLAN_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_ATTACHMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,180}\Z")


def comment_category(comment: dict) -> str:
    category = comment.get("category")
    if category in CATEGORIES:
        return category
    return "library" if str(comment.get("anchor_id", "")).startswith("copy:") else "review"


def validate_plan_id(plan_id: str) -> str:
    if not isinstance(plan_id, str) or not _PLAN_ID.fullmatch(plan_id):
        raise ValueError("invalid plan_id: use lowercase letters, numbers and hyphens (1-64)")
    return plan_id


def safe_path(page_dir: Path | str, relative: str) -> Path:
    """Refuse traversal and every symlink component, including in the page root."""
    root = Path(page_dir).absolute()
    parts = Path(relative).parts
    if not parts or Path(relative).is_absolute() or any(p in (".", "..") for p in parts) or "\\" in relative:
        raise ValueError("unsafe storage path")
    target = root.joinpath(*parts)
    for path in (target, *target.parents):
        if path.is_symlink():
            raise ValueError("symlink storage paths are refused")
    return target


def _json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    if path.stat().st_size > MAX_PLAN_BYTES:
        raise ValueError("category storage exceeds size limit")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("category storage must be an object")
    return data


def _atomic_bytes(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix="." + path.name, dir=path.parent, delete=False) as out:
            temporary = Path(out.name)
            out.write(body)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
        temporary = None
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def _write(path: Path, value: dict) -> None:
    body = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()
    if len(body) > MAX_PLAN_BYTES:
        raise ValueError("category storage exceeds size limit")
    _atomic_bytes(path, body)


@contextmanager
def _lock(page_dir: Path | str, name: str):
    path = safe_path(page_dir, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def load_categories(page_dir: Path | str) -> dict:
    data = _json(safe_path(page_dir, "categories.json"), {"schema_version": 1, "findings_sets": []})
    if data.get("schema_version", 1) != 1:
        raise ValueError("categories.schema_version must be 1")
    sets = data.get("findings_sets", [])
    if not isinstance(sets, list) or len(sets) > 100:
        raise ValueError("findings_sets must be an array of at most 100 sets")
    normalized, ids = [], set()
    for item in sets:
        if not isinstance(item, dict) or set(item) != {"id", "label"}:
            raise ValueError("a findings set needs id and label")
        identifier = validate_plan_id(item["id"])
        if identifier in ids:
            raise ValueError("findings set ids must be unique")
        ids.add(identifier)
        normalized.append({"id": identifier, "label": _text(item["label"], "set label")})
    return {"schema_version": 1, "findings_sets": normalized}


def save_findings_sets(page_dir: Path | str, findings_sets: list[dict]) -> dict:
    # Use the same validator without writing invalid data to disk.
    data = {"schema_version": 1, "findings_sets": findings_sets}
    if not isinstance(findings_sets, list) or len(findings_sets) > 100:
        raise ValueError("invalid findings sets")
    ids = set()
    for item in findings_sets:
        if not isinstance(item, dict) or set(item) != {"id", "label"}:
            raise ValueError("a findings set needs id and label")
        identifier = validate_plan_id(item["id"])
        _text(item["label"], "set label")
        if identifier in ids:
            raise ValueError("findings set ids must be unique")
        ids.add(identifier)
    with _lock(page_dir, ".categories.json.lock"):
        _write(safe_path(page_dir, "categories.json"), data)
    return data


def _comments(page_dir):
    from .sync_server import _load_v2_store
    return _load_v2_store(safe_path(page_dir, "comments.json"))


def _finding(store: dict, identifier) -> dict:
    matches = [c for items in store["anchors"].values() for c in items
               if c.get("id") == identifier or (str(identifier).isdigit() and str(c.get("number")) == str(identifier))]
    matches = [c for c in matches if comment_category(c) == "findings"]
    if not matches:
        raise KeyError(identifier)
    if len(matches) != 1:
        raise ValueError("ambiguous finding number; use its comment id")
    return matches[0]


def validate_proof(page_dir: Path | str, proof: list[dict]) -> list[dict]:
    if not isinstance(proof, list) or len(proof) > 30:
        raise ValueError("proof must be an array of at most 30 entries")
    result = []
    for item in proof:
        if not isinstance(item, dict) or set(item) not in ({"label", "url"}, {"label", "attachment"}):
            raise ValueError("proof needs label and either url or attachment")
        label = _text(item["label"], "proof label")
        if "url" in item:
            url = _link(item["url"])
            if not url.lower().startswith(("http://", "https://")):
                raise ValueError("proof URLs must use HTTP or HTTPS")
            result.append({"label": label, "url": url})
        else:
            name = item["attachment"]
            if not isinstance(name, str) or not _ATTACHMENT.fullmatch(name) or ".." in name:
                raise ValueError("unsafe attachment name")
            path = safe_path(page_dir, "attachments/" + name)
            if not path.is_file() or path.stat().st_size > MAX_PROOF_BYTES:
                raise ValueError("proof attachment missing or oversized")
            result.append({"label": label, "attachment": name})
    return result


def add_proof_file(page_dir: Path | str, src_path: Path | str) -> dict:
    """Copy a regular file without following any source or destination symlink.

    Caller enforces its cwd boundary. The stored attachment is a basename.
    """
    source = Path(src_path).absolute()
    # openat + O_NOFOLLOW avoids races as well as static symlink components.
    descriptors = []
    try:
        fd = os.open(source.anchor, os.O_RDONLY | os.O_DIRECTORY)
        descriptors.append(fd)
        for part in source.parts[1:-1]:
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            descriptors.append(fd)
        file_fd = os.open(source.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        descriptors.append(file_fd)
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_PROOF_BYTES:
            raise ValueError("proof must be a regular file of at most 10 MB")
        with os.fdopen(os.dup(file_fd), "rb") as stream:
            body = stream.read(MAX_PROOF_BYTES + 1)
        if len(body) > MAX_PROOF_BYTES:
            raise ValueError("proof exceeds 10 MB")
    except OSError as exc:
        raise ValueError("proof path must contain no symlinks and name a readable regular file") from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    basename = re.sub(r"[^A-Za-z0-9_.-]", "-", source.name).replace("..", "-").strip(".-")[:100] or "proof"
    name = uuid.uuid4().hex + "-" + basename
    _atomic_bytes(safe_path(page_dir, "attachments/" + name), body)
    return {"label": source.name[:200], "attachment": name}


def mark_finding_fixed(page_dir: Path | str, number_or_id, *, by: str, note: str, proof: list[dict]) -> dict:
    from .sync_server import _atomic_write_json, _locked_store
    by = _text(by, "fixed by", 500)
    if not isinstance(note, str) or len(note) > 10000:
        raise ValueError("fixed note must be text of at most 10000 characters")
    proof = validate_proof(page_dir, proof)
    with _locked_store(page_dir):
        store = _comments(page_dir)
        comment = _finding(store, number_or_id)
        now = datetime.now(timezone.utc).isoformat()
        if comment.get("fixed"):
            comment.setdefault("fixed_history", []).append(comment["fixed"])
        comment["fixed"] = {"by": by, "ts": now, "note": note, "proof": proof}
        comment["status"] = "addressed_by_agent"
        comment["resolved_in_version"] = _json(safe_path(page_dir, "current.meta.json"), {}).get("current", comment.get("version"))
        comment.pop("round_pending", None)
        if comment.get("decision"):
            comment["decision"].pop("round_pending", None)
        _atomic_write_json(safe_path(page_dir, "comments.json"), store)
        return comment


def reopen_finding(page_dir: Path | str, comment_id: str, *, by: str, text: str) -> dict:
    from .sync_server import _atomic_write_json, _locked_store
    by, text = _text(by, "reopen by", 500), _text(text, "reopen text", 10000)
    with _locked_store(page_dir):
        store = _comments(page_dir)
        comment = _finding(store, comment_id)
        if comment.get("round_pending") and comment.get("reopened", [])[-1].get("by") != by:
            raise PermissionError("another reviewer owns the pending reopen")
        if not comment.get("fixed"):
            raise ValueError("only a fixed finding can be reopened")
        comment.setdefault("fixed_history", []).append(comment.pop("fixed"))
        comment.update(status="open", round_pending=True)
        comment.pop("resolved_in_version", None)
        now = datetime.now(timezone.utc).isoformat()
        comment.setdefault("reopened", []).append({"by": by, "ts": now, "text": text})
        # A stale keep/fix verdict must not answer the newly reopened question.
        if comment.get("decision"):
            comment.setdefault("decision_history", []).append(comment.pop("decision"))
        _atomic_write_json(safe_path(page_dir, "comments.json"), store)
        return comment


def plan_meta(page_dir: Path | str, plan_id: str) -> dict:
    validate_plan_id(plan_id)
    path = safe_path(page_dir, f"plans/{plan_id}/meta.json")
    if not path.is_file():
        raise KeyError(plan_id)
    return _json(path, {})


def list_plans(page_dir: Path | str) -> list[dict]:
    directory = safe_path(page_dir, "plans")
    if not directory.exists():
        return []
    return [{"id": p.name, **plan_meta(page_dir, p.name)} for p in sorted(directory.iterdir())
            if _PLAN_ID.fullmatch(p.name) and p.is_dir()]


def publish_plan_revision(page_dir: Path | str, plan_id: str, html: str, *, title: str | None = None,
                          label: str | None = None) -> dict:
    validate_plan_id(plan_id)
    if not isinstance(html, str) or not html.strip() or len(html.encode()) > MAX_PLAN_BYTES:
        raise ValueError("plan HTML must be nonempty and at most 4 MB")
    if title is not None:
        _text(title, "plan title", 200)
    if label is not None:
        _text(label, "plan label", 200)
    with _lock(page_dir, f"plans/{plan_id}/.meta.json.lock"):
        path = safe_path(page_dir, f"plans/{plan_id}/meta.json")
        meta = _json(path, {"title": title or plan_id, "current": None, "history": []})
        directory = safe_path(page_dir, f"plans/{plan_id}/versions")
        directory.mkdir(parents=True, exist_ok=True)
        numbers = [int(p.stem[1:]) for p in directory.iterdir() if re.fullmatch(r"v[0-9]+\.html", p.name)]
        version = "v" + str(max(numbers, default=0) + 1)
        entry = {"version": version, "ts": datetime.now(timezone.utc).isoformat()}
        if label is not None:
            entry["label"] = label
        _atomic_bytes(safe_path(page_dir, f"plans/{plan_id}/versions/{version}.html"), html.encode())
        meta["current"] = version
        if title is not None:
            meta["title"] = title
        meta.setdefault("history", []).append(entry)
        _write(path, meta)
        return {"id": plan_id, **entry, "title": meta["title"], "current": version, "history": meta["history"]}


def comment_section(comment: dict) -> str | None:
    """Accepted shell sectionOf; Findings keeps agreed work waiting until fixed."""
    status = comment.get("status", "open")
    if status == "archived":
        return None
    decision = comment.get("decision") or {}
    if comment.get("round_pending") or (decision.get("round_pending") and status != "resolved_in_version"):
        return "ready"
    if comment_category(comment) == "findings":
        if comment.get("fixed") or status in {"addressed_by_agent", "resolved_in_version"}:
            return "done"
        if not decision.get("verdict"):
            if comment.get("reopened"):
                return "waiting"
            return "needs_you"
        choice = decision.get("option_id") or decision.get("option")
        if choice is None and decision.get("verdict") == "select":
            choice = decision.get("text")
        options = (comment.get("decision_request") or {}).get("options", [])
        for option in options:
            if isinstance(option, dict) and option.get("label") == choice:
                choice = option.get("id")
        return "done" if choice in {"keep", "no"} or decision.get("verdict") == "reject" else "waiting"
    if comment.get("decision_request") and not decision.get("verdict") and status not in {"addressed_by_agent", "resolved_in_version"}:
        return "needs_you"
    if status != "open":
        return "done"
    replies = comment.get("replies") or []
    if replies and str(replies[-1].get("author", "")).startswith("agent:"):
        return "needs_you"
    from .sync_server import _comment_needs_push
    return "ready" if _comment_needs_push(comment) else "waiting"


def comment_sig(comment: dict) -> str:
    """Mirror shell.js's unsigned djb2 hash over JavaScript UTF-16 code units."""
    value = "\x01".join([comment.get("status") or "", comment.get("response_text") or "",
                         str(len(comment.get("replies") or [])), comment.get("edited_at") or ""])
    hash_value = 5381
    encoded = value.encode("utf-16-le", errors="surrogatepass")
    for index in range(0, len(encoded), 2):
        hash_value = (hash_value * 33 + int.from_bytes(encoded[index:index + 2], "little")) & 0xffffffff
    digits, result = "0123456789abcdefghijklmnopqrstuvwxyz", ""
    while hash_value:
        result = digits[hash_value % 36] + result
        hash_value //= 36
    return result or "0"


def category_counts(page_dir: Path | str, author: str | None = None) -> dict:
    from .sync_server import _author_key
    counts = {c: dict.fromkeys(("needs_you", "ready", "waiting", "done", "unread"), 0) for c in CATEGORIES}
    read = _json(safe_path(page_dir, "read-state.json"), {}).get(_author_key(author), {}) if author else {}
    for items in _comments(page_dir)["anchors"].values():
        for comment in items:
            section = comment_section(comment)
            if section is None:
                continue
            category = comment_category(comment)
            # Copy proposals are counted as their block, never again as a comment.
            if category == "library" and (comment.get("target") or {}).get("copy_revision"):
                continue
            counts[category][section] += 1
            if author and read.get(comment.get("id"), {}).get("sig") != comment_sig(comment):
                counts[category]["unread"] += 1
    for block in load_copy(page_dir)["blocks"]:
        pending = [r for r in block["revisions"] if r.get("round_pending")]
        latest = block["revisions"][-1]
        section = ("ready" if pending else "waiting" if latest["status"] == "proposed" and latest.get("round_pending") is False
                   else block.get("status", "needs_you"))
        if section == "held":
            section = "done"
        counts["library"][section] += 1
    return counts
