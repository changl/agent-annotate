"""Durable, round-only wake-ups through an already-owned Orca terminal.

The bus is the outbox source of truth. A send is journaled before input; an
ambiguous send is never repeated automatically. No terminal is created or
rebound, and no reviewer text is interpolated into the wake-up prompt.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import ExitStack, nullcontext
from datetime import UTC, datetime
from pathlib import Path

from .paths import STATE_DIR


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(name).unlink(missing_ok=True)


def _orca(*args: str) -> dict:
    executable = os.environ.get("ORCA_CLI_COMMAND") or shutil.which("orca")
    if not executable:
        raise RuntimeError("Orca CLI unavailable")
    result = subprocess.run([executable, *args, "--json"], capture_output=True, text=True, timeout=15)
    data = json.loads(result.stdout)
    if result.returncode or not data.get("ok"):
        raise RuntimeError(str(data.get("error") or "Orca command failed"))
    return data["result"]


def _process(pid: int) -> tuple[str, str] | None:
    result = subprocess.run(["ps", "-p", str(pid), "-o", "lstart=,comm="],
                            capture_output=True, text=True, timeout=3)
    line = result.stdout.strip()
    if result.returncode or not line:
        return None
    parts = line.split(None, 5)
    return (" ".join(parts[:5]), parts[5]) if len(parts) == 6 else None


def _parent_handle(expected: str) -> str | None:
    """Codex can strip Orca variables from exec children; inspect only its provider ancestor."""
    pid = os.getppid()
    try:
        for _ in range(12):
            proc = _process(pid)
            if proc and re.search(rf"(?:^|/){expected}(?:$|[.-])", proc[1]):
                result = subprocess.run(["ps", "eww", "-p", str(pid), "-o", "command="],
                                        capture_output=True, text=True, timeout=3)
                match = re.search(r"(?:^|\s)ORCA_TERMINAL_HANDLE=(term_[A-Za-z0-9_-]+)(?:\s|$)", result.stdout)
                return match[1] if match else None
            parent = subprocess.run(["ps", "-p", str(pid), "-o", "ppid="], capture_output=True, text=True, timeout=3)
            pid = int(parent.stdout.strip())
            if pid < 2:
                break
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return None


def _group_name(group_id: str | None) -> str | None:
    """Read the name absent from Orca's public repo response; omit ambiguous profiles."""
    if not group_id:
        return None
    root = (Path.home() / "Library/Application Support/Orca" if sys.platform == "darwin"
            else Path(os.environ.get("APPDATA") or Path.home() / ".config") / "Orca")
    names = set()
    for path in (root / "profiles").glob("*/orca-data.json"):
        try:
            names.update(g["name"] for g in json.loads(path.read_text()).get("projectGroups", [])
                         if g.get("id") == group_id and isinstance(g.get("name"), str))
        except (OSError, ValueError, TypeError, KeyError):
            continue
    return names.pop() if len(names) == 1 else None


def describe_terminal(terminal: dict) -> dict:
    display = {}
    if not terminal.get("title"):
        return display
    display["terminal_name"] = terminal["title"]
    try:
        worktree = _orca("worktree", "show", "--worktree", "id:" + terminal["worktreeId"])["worktree"]
        repo = _orca("repo", "show", "--repo", "id:" + worktree["repoId"])["repo"]
        display.update(group=repo.get("projectGroupName") or _group_name(repo.get("projectGroupId")),
                       project=repo.get("displayName"), workspace=worktree.get("displayName"))
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired):
        display["workspace"] = Path(terminal.get("worktreePath") or ".").name
    names = [display.get(k) for k in ("group", "project", "workspace", "terminal_name")]
    display["label"] = " > ".join(str(n) for n in names if n) + f" [{terminal['handle']}]"
    return display


def capture_target(session: str, agent: str) -> dict | None:
    """Bind only the caller's current terminal and provider process."""
    if session == "unknown":
        return None
    expected = "codex" if agent == "codex" else "claude"
    handle = os.environ.get("ORCA_TERMINAL_HANDLE") or _parent_handle(expected)
    if not handle:
        return None
    try:
        terminal = _orca("terminal", "show", "--terminal", handle)["terminal"]
        if terminal.get("agentIdentity") != expected or not terminal.get("connected"):
            return None
        display = describe_terminal({**terminal, "handle": handle})
        pid = os.getppid()
        for _ in range(12):
            proc = _process(pid)
            if proc and re.search(rf"(?:^|/){expected}(?:$|[.-])", proc[1]):
                return {"session": session, "handle": handle,
                        "incarnation": terminal["incarnationId"],
                        "worktree": terminal["worktreeId"], "agent": expected,
                        "pid": pid, "process_start": proc[0], **display}
            parent = subprocess.run(["ps", "-p", str(pid), "-o", "ppid="],
                                    capture_output=True, text=True, timeout=3)
            pid = int(parent.stdout.strip())
            if pid < 2:
                break
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired):
        pass
    return None


def _target_ready(target: dict) -> tuple[bool, str]:
    try:
        process = _process(int(target["pid"]))
        if (not process or process[0] != target["process_start"]
                or not re.search(rf"(?:^|/){re.escape(target['agent'])}(?:$|[.-])", process[1])):
            return False, "Owner process ended; owner must claim the page in a live session"
        terminal = _orca("terminal", "show", "--terminal", target["handle"])["terminal"]
        if (terminal.get("incarnationId") != target["incarnation"]
                or terminal.get("worktreeId") != target["worktree"]
                or terminal.get("agentIdentity") != target["agent"]
                or not terminal.get("connected") or not terminal.get("writable")):
            return False, "Owner terminal changed or disconnected; no input sent"
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)[:300]
    return True, ""


def dispatch_record(record: dict, project: str, slug: str, *, dry_run: bool = False) -> dict:
    """Discover submitted rounds and attempt each new delivery once.

    A private cursor does not consume the agent's inbox or monitor cursor.
    Called immediately after submission and by the existing revive watchdog.
    """
    bus = Path(record.get("bus_file") or "")
    if not bus.is_file():
        return {"deliveries": []}
    journal = STATE_DIR / "deliveries" / project / f"{slug}.json"
    if not dry_run:
        journal.parent.mkdir(parents=True, exist_ok=True)
    with (nullcontext(None) if dry_run else journal.with_suffix(".lock").open("a")) as lock:
        if lock is not None:
            fcntl.flock(lock, fcntl.LOCK_EX)
        state = json.loads(journal.read_text()) if journal.exists() else {"offset": 0, "deliveries": {}}
        original_offset = state["offset"]
        rows = state["deliveries"]
        with bus.open("rb") as stream:
            stream.seek(min(state["offset"], bus.stat().st_size))
            while line := stream.readline():
                if not line.endswith(b"\n"):
                    break
                state["offset"] = stream.tell()
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                if (event.get("event") != "session_push" or event.get("round") is not True
                        or event.get("automatic_delivery") is not True):
                    continue
                key = event.get("delivery_id")
                if not isinstance(key, str) or not re.fullmatch(r"[a-f0-9]{12,32}", key):
                    continue
                rows.setdefault(key, {"id": key, "state": "pending", "created_at": event.get("ts"),
                                      "target": event.get("owner_target"),
                                      "owner_session": event.get("owner_session"),
                                      "comment_count": event.get("comment_count", 0),
                                      "bus_offset": stream.tell()})
        if dry_run:
            return {"deliveries": list(rows.values())}
        if not any(row["state"] in ("pending", "attempting") for row in rows.values()):
            if state["offset"] != original_offset:
                _atomic(journal, state)
            return {"deliveries": list(rows.values())}
        _atomic(journal, state)
        from .cli import _flock, _load_state_for_project, _state_lock_path
        from .workspace import workspace_owner_record
        current = _load_state_for_project(project).get("slugs", {}).get(slug) or {}
        effective = workspace_owner_record(current)
        owner_project = (effective.get("workspace_owner") or {}).get("project", project)
        projects = {project, owner_project}
        # Canonical claims use the same sorted locks for their bounded tabs.
        with ExitStack() as stack:
            for name in sorted(projects):
                stack.enter_context(_flock(_state_lock_path(name)))
            current = _load_state_for_project(project).get("slugs", {}).get(slug)
            # A removed page must never wake the former owner.
            if current is None:
                current = {}
            effective = workspace_owner_record(current)
            fresh_project = (effective.get("workspace_owner") or {}).get("project", project)
            if fresh_project in projects:
                _send_pending(rows, effective, project, slug, journal, state)
            else:
                for row in rows.values():
                    if row["state"] == "pending":
                        row["detail"] = "Workspace ownership changed during delivery; remains pending"
        _atomic(journal, state)
        return {"deliveries": list(rows.values())}


def _send_pending(rows: dict, record: dict, project: str, slug: str, journal: Path, state: dict) -> None:
    for row in rows.values():
        if row["state"] == "attempting":
            row.update(state="uncertain", detail="Previous send interrupted; automatic resend suppressed")
        if row["state"] != "pending":
            continue
        if row.get("owner_session") != record.get("owner_session"):
            row.update(state="superseded", detail="Page ownership changed before delivery")
            continue
        from .cli import _offset_file
        cursor = _offset_file(project, slug, row["owner_session"])
        try:
            already_read = int(cursor.read_text()) >= row.get("bus_offset", 1 << 60)
        except (OSError, ValueError):
            already_read = False
        if already_read:
            row.update(state="acknowledged", acknowledged_at=_now(), detail="Owner already read this submitted round")
            continue
        target = record.get("owner_target") if "owner_target" in record else row.get("target")
        row["target"] = target
        if not target:
            row["detail"] = "No Orca owner binding; owner must claim the page from an Orca session"
            continue
        ready, detail = _target_ready(target)
        if not ready:
            row["detail"] = detail
            continue
        # No reviewer text in this prompt: the owner reads trusted routing
        # metadata here, then treats inbox content as reviewer data.
        from .urls import page_url, redact_review_key
        url = redact_review_key((record.get("workspace_owner") or {}).get("url") or page_url(record))
        page = f"Page: {url}. " if url else ""
        prompt = (f"[annotate] ROUND SUBMITTED: {project}/{slug}; "
                  f"{row['comment_count']} answer(s), delivery {row['id']}. "
                  f"{page}"
                  f"Read annotate inbox {project}/{slug} --unread and annotate cards {project}/{slug}. "
                  "Handle this completed feedback round, preserve prior decisions and history, "
                  "and continue authorized project work. Update the existing workspace only for a meaningful result or needed decision. "
                  "Report concisely with the full share URL from your workspace lookup; if missing, run annotate workspace --json once. "
                  "Do not create another page or wait for a monitor.")
        row.update(state="attempting", attempted_at=_now())
        _atomic(journal, state)
        try:
            result = _orca("terminal", "send", "--terminal", target["handle"],
                           "--text", prompt, "--enter", "--wait-submit", "1")
            receipt = result.get("send", {})
            row["receipt"] = receipt
            stages = receipt.get("prompt", {}).get("stages", [])
            if receipt.get("accepted"):
                row.update(state="started" if "turn_started" in stages else "accepted",
                           accepted_at=_now(),
                           detail="Orca accepted owner prompt; action completion is not yet proven")
            else:
                row.update(state="uncertain", detail="Input acceptance unproven; automatic resend suppressed")
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as exc:
            row.update(state="uncertain", detail=f"Send outcome unproven: {str(exc)[:250]}")
        row["updated_at"] = _now()
        _atomic(journal, state)

def delivery_status(project: str, slug: str) -> dict:
    path = STATE_DIR / "deliveries" / project / f"{slug}.json"
    try:
        rows = list(json.loads(path.read_text()).get("deliveries", {}).values())
        if not rows:
            return {"latest": None}
        latest = {k: v for k, v in rows[-1].items()
                  if k in ("id", "state", "detail", "created_at", "updated_at")}
        target = rows[-1].get("target") or {}
        if latest.get("state") in ("accepted", "started") and target.get("pid"):
            process = _process(int(target["pid"]))
            if not process or process[0] != target.get("process_start"):
                latest.update(state="pending", detail="Current agent must claim the workspace")
        return {"latest": latest}
    except (OSError, ValueError):
        return {"latest": None}


def acknowledge(project: str, slug: str, session: str, ids: list[str]) -> list[str]:
    """Owner inbox reads acknowledge receipt, never completion of requested work."""
    path = STATE_DIR / "deliveries" / project / f"{slug}.json"
    if not path.exists():
        return []
    acknowledged = []
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = json.loads(path.read_text())
        for key in ids:
            row = state.get("deliveries", {}).get(key)
            if row and row.get("owner_session") == session and row["state"] != "acknowledged":
                row.update(state="acknowledged", acknowledged_at=_now(),
                           detail="Owner read submitted feedback; requested work completion remains separate")
                acknowledged.append(key)
        if acknowledged:
            _atomic(path, state)
    return acknowledged
