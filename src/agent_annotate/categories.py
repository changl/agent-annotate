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
# Proof files are served from the review origin, so only inert types are taken.
PROOF_SUFFIXES = ("png", "jpg", "jpeg", "gif", "webp", "pdf", "txt", "md", "log", "json", "csv")
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
    """Refuse traversal and every symlink component below the page dir.

    The page dir's own location may go through symlinks (/tmp and /var on
    macOS, an unresolved registry path); what is stored under it may not.
    """
    root = Path(page_dir).absolute()
    parts = Path(relative).parts
    if not parts or Path(relative).is_absolute() or any(p in (".", "..") for p in parts) or "\\" in relative:
        raise ValueError("unsafe storage path")
    target = root.joinpath(*parts)
    path = target
    while path != root:
        if path.is_symlink():
            raise ValueError("symlink storage paths are refused")
        path = path.parent
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


# Optional set fields: the short name of each finding ("Gap" → "Gap 1"), the
# set's introduction and when it was posted.
_SET_OPTIONAL = {"item_label": 40, "intro": 10000, "created_at": 64}


def _findings_sets(sets) -> list[dict]:
    if not isinstance(sets, list) or len(sets) > 100:
        raise ValueError("findings_sets must be an array of at most 100 sets")
    normalized, ids = [], set()
    for item in sets:
        if not isinstance(item, dict) or not {"id", "label"} <= set(item) <= {"id", "label", *_SET_OPTIONAL}:
            raise ValueError("a findings set needs id and label (optional: item_label, intro, created_at)")
        identifier = validate_plan_id(item["id"])
        if identifier in ids:
            raise ValueError("findings set ids must be unique")
        ids.add(identifier)
        entry = {"id": identifier, "label": _text(item["label"], "set label")}
        for key, maximum in _SET_OPTIONAL.items():
            if key in item:
                entry[key] = _text(item[key], "set " + key.replace("_", " "), maximum)
        if "created_at" in entry:
            try:
                datetime.fromisoformat(entry["created_at"].replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("set created_at must be an ISO 8601 time") from exc
        normalized.append(entry)
    return normalized


def load_categories(page_dir: Path | str) -> dict:
    data = _json(safe_path(page_dir, "categories.json"), {"schema_version": 1, "findings_sets": []})
    if data.get("schema_version", 1) != 1:
        raise ValueError("categories.schema_version must be 1")
    return {"schema_version": 1, "findings_sets": _findings_sets(data.get("findings_sets", []))}


def save_findings_sets(page_dir: Path | str, findings_sets: list[dict]) -> dict:
    # Use the same validator without writing invalid data to disk.
    data = {"schema_version": 1, "findings_sets": _findings_sets(findings_sets)}
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
        keys = set(item) - {"detail"} if isinstance(item, dict) else None
        if keys not in ({"label", "url"}, {"label", "attachment"}):
            raise ValueError("proof needs label and either url or attachment (optional: detail)")
        label = _text(item["label"], "proof label")
        # An optional line under a link, e.g. "An agent links the merged change here."
        detail = {"detail": _text(item["detail"], "proof detail", 500)} if "detail" in item else {}
        if "url" in item:
            url = _link(item["url"])
            if not url.lower().startswith(("http://", "https://")):
                raise ValueError("proof URLs must use HTTP or HTTPS")
            result.append({"label": label, "url": url, **detail})
        else:
            name = item["attachment"]
            if not isinstance(name, str) or not _ATTACHMENT.fullmatch(name) or ".." in name:
                raise ValueError("unsafe attachment name")
            path = safe_path(page_dir, "attachments/" + name)
            if not path.is_file() or path.stat().st_size > MAX_PROOF_BYTES:
                raise ValueError("proof attachment missing or oversized")
            result.append({"label": label, "attachment": name, **detail})
    return result


def check_proof_type(path: Path | str) -> None:
    if Path(path).suffix.lower().lstrip(".") not in PROOF_SUFFIXES:
        raise ValueError(f"proof files must be one of: {', '.join(PROOF_SUFFIXES)} "
                         f"(got {Path(path).name!r}); link other evidence by HTTPS URL")


def add_proof_file(page_dir: Path | str, src_path: Path | str) -> dict:
    """Copy a regular file without following any source or destination symlink.

    Caller enforces its cwd boundary. The stored attachment is a basename.
    """
    check_proof_type(src_path)
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
        if info.st_nlink > 1:
            # A hard link can name a file outside the caller's boundary.
            raise ValueError("proof file has another hard link; copy it to a new file first")
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
        # A reopen or verdict the reviewer has not sent yet stays round-pending:
        # it still goes out with the next Send, after this fix.
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
    # A folder without meta.json (notes, a half-copied plan) is not a plan.
    return [{"id": p.name, **plan_meta(page_dir, p.name)} for p in sorted(directory.iterdir())
            if _PLAN_ID.fullmatch(p.name) and p.is_dir() and (p / "meta.json").is_file()]


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


_SEND_ID = re.compile(r"[A-Za-z0-9-]{8,64}\Z")
MAX_RECEIPT_ITEMS = 200


def validate_send(payload: dict) -> dict:
    """The optional `send_id` and `receipt` one Send passes to rounds/submit
    and push-session: the lines the reviewer saw in the Send summary, tagged
    by tab, kept for History · Sent rounds. Display only; never delivered."""
    result = {}
    if payload.get("send_id") is not None:
        if not isinstance(payload["send_id"], str) or not _SEND_ID.fullmatch(payload["send_id"]):
            raise ValueError("send_id must be 8-64 letters, digits or hyphens")
        result["send_id"] = payload["send_id"]
    if payload.get("receipt") is not None:
        receipt = payload["receipt"]
        if not isinstance(receipt, list) or len(receipt) > MAX_RECEIPT_ITEMS:
            raise ValueError(f"receipt must be an array of at most {MAX_RECEIPT_ITEMS} lines")
        lines = []
        for item in receipt:
            if not isinstance(item, dict) or not {"cat", "label"} <= set(item) <= {"cat", "label", "answer"}:
                raise ValueError("a receipt line needs cat and label (optional: answer)")
            if item["cat"] not in CATEGORIES:
                raise ValueError("receipt cat must be a category")
            line = {"cat": item["cat"], "label": _text(item["label"], "receipt label", 300)}
            if item.get("answer"):
                line["answer"] = _text(item["answer"], "receipt answer", 600)
            lines.append(line)
        result["receipt"] = lines
    return result


def _mapping(value) -> dict:
    """Older or hand-edited comments may hold a string or null where a
    newer one holds an object; read those as empty."""
    return value if isinstance(value, dict) else {}


def _replies(comment: dict) -> list[dict]:
    replies = comment.get("replies")
    return [reply for reply in replies if isinstance(reply, dict)] if isinstance(replies, list) else []


def comment_section(comment: dict) -> str | None:
    """Accepted shell sectionOf; Findings keeps agreed work waiting until fixed."""
    status = comment.get("status", "open")
    if status == "archived":
        return None
    decision = _mapping(comment.get("decision"))
    if comment.get("round_pending") or (decision.get("round_pending") and status != "resolved_in_version"):
        return "ready"
    # A finding (not a reviewer's comment on one) keeps agreed work waiting.
    if comment_category(comment) == "findings" and (comment.get("finding") or comment.get("decision_request")):
        if comment.get("fixed"):
            return "done"
        if not decision.get("verdict"):
            if comment.get("reopened") or comment.get("response_text"):
                return "waiting"
            return "needs_you"
        choice = decision.get("option_id") or decision.get("option")
        if choice is None and decision.get("verdict") == "select":
            choice = decision.get("text")
        options = _mapping(comment.get("decision_request")).get("options") or []
        for option in options if isinstance(options, list) else []:
            if isinstance(option, dict) and option.get("label") == choice:
                choice = option.get("id")
        return "done" if choice in {"keep", "no"} or decision.get("verdict") == "reject" else "waiting"
    if comment.get("decision_request") and not decision.get("verdict") and status not in {"addressed_by_agent", "resolved_in_version"}:
        return "needs_you"
    if status != "open":
        return "done"
    replies = _replies(comment)
    if replies and str(replies[-1].get("author", "")).startswith("agent:"):
        return "needs_you"
    from .sync_server import _comment_needs_push
    return "ready" if _comment_needs_push(comment) else "waiting"


def comment_sig(comment: dict) -> str:
    """Mirror shell.js's unsigned djb2 hash over JavaScript UTF-16 code units."""
    replies = comment.get("replies")
    value = "\x01".join([_js_text(comment.get("status")), _js_text(comment.get("response_text")),
                         str(len(replies) if isinstance(replies, (list, str)) else 0),
                         _js_text(comment.get("edited_at"))])
    hash_value = 5381
    encoded = value.encode("utf-16-le", errors="surrogatepass")
    for index in range(0, len(encoded), 2):
        hash_value = (hash_value * 33 + int.from_bytes(encoded[index:index + 2], "little")) & 0xffffffff
    digits, result = "0123456789abcdefghijklmnopqrstuvwxyz", ""
    while hash_value:
        result = digits[hash_value % 36] + result
        hash_value //= 36
    return result or "0"


def _js_text(value) -> str:
    """JavaScript's `value || ''` inside a string join, for the sig."""
    if not value:
        return ""
    if isinstance(value, bool):
        return "true"
    if isinstance(value, dict):
        return "[object Object]"
    if isinstance(value, list):
        return ",".join(_js_text(item) for item in value)
    return str(value)


def _agent(author) -> bool:
    return str(author or "").startswith("agent:")


def comment_can_be_unread(comment: dict) -> bool:
    """Whether a comment counts toward its tab's unread count.

    Review and Plans: every card (the shell's read model). Findings: a fix not
    opened yet; the finding's question itself is counted as needs-you, not
    unread. Other Library and Findings comments: an agent reply not opened yet.
    """
    category = comment_category(comment)
    if category in ("review", "plans"):
        return True
    if category == "findings" and (comment.get("finding") or comment.get("decision_request")):
        return bool(comment.get("fixed"))
    replies = _replies(comment)
    return bool(replies) and _agent(replies[-1].get("author"))


def _follows_viewer(comment: dict) -> bool:
    """shell.js followsViewer: an unanswered or round-pending card is shown on
    every version of its document."""
    decision = _mapping(comment.get("decision"))
    if decision.get("round_pending"):
        return True
    return bool(comment.get("decision_request") and not decision.get("verdict")
                and comment.get("status") not in ("archived", "resolved_in_version", "addressed_by_agent"))


def _current_versions(page_dir: Path | str) -> dict:
    """The current version of each document: "review" and "plan:<id>"."""
    versions = {"review": _json(safe_path(page_dir, "current.meta.json"), {}).get("current")}
    for plan in list_plans(page_dir):
        versions["plan:" + plan["id"]] = plan.get("current")
    return versions


def block_can_be_unread(block: dict) -> bool:
    """A Library item is unread while its agent note (held_note) or a later
    agent revision has not been opened; its first text alone is not news."""
    revisions = block.get("revisions") or []
    later_agent = len(revisions) > 1 and _agent((revisions[-1].get("author") or {}).get("id"))
    return bool(block.get("held_note")) or later_agent


def category_counts(page_dir: Path | str, author: str | None = None, *, read_state: dict | None = None) -> dict:
    from .sync_server import _author_key
    counts = {c: dict.fromkeys(("needs_you", "ready", "waiting", "done", "unread"), 0) for c in CATEGORIES}
    read = (read_state if read_state is not None else
            _json(safe_path(page_dir, "read-state.json"), {}).get(_author_key(author), {}) if author else {})
    versions = _current_versions(page_dir) if author else {}
    for items in _comments(page_dir)["anchors"].values():
        for comment in items:
            section = comment_section(comment)
            if section is None:
                continue
            category = comment_category(comment)
            # Copy proposals are counted as their block, never again as a comment.
            if category == "library" and _mapping(comment.get("target")).get("copy_revision"):
                continue
            counts[category][section] += 1
            if (author and comment_can_be_unread(comment)
                    and read.get(comment.get("id"), {}).get("sig") != comment_sig(comment)):
                # Review and Plans: unread on the document's current version (the
                # rail's scope), plus cards that follow the viewer to it.
                if category in ("review", "plans"):
                    doc = comment.get("doc") if category == "plans" else "review"
                    current = versions.get(doc)
                    if current and comment.get("version") != current and not _follows_viewer(comment):
                        continue
                counts[category]["unread"] += 1
    try:
        blocks = load_copy(page_dir)["blocks"]
    except ValueError:
        blocks = []  # an invalid copy.json is reported by /api/categories
    for block in blocks:
        pending = [r for r in block["revisions"] if r.get("round_pending")]
        latest = block["revisions"][-1]
        # A proposal without round_pending is from before the shared Send: it
        # was pushed at once, so it waits on the agent (library.js shows it as
        # sent). A block without a status asks nothing of the reviewer.
        section = ("ready" if pending else "waiting" if latest["status"] == "proposed" and not latest.get("round_pending")
                   else block.get("status") or "done")
        if section == "held":
            section = "done"
        counts["library"][section] += 1
        # Library uses the existing per-item read sidecar too. Revisions have
        # immutable ids, so the latest id is its activity signature.
        if (author and block_can_be_unread(block)
                and read.get("copy:" + block["id"], {}).get("sig") != latest["id"]):
            counts["library"]["unread"] += 1
    return counts
