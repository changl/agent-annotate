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
import tempfile
from contextlib import nullcontext
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


def capture_target(session: str, agent: str) -> dict | None:
    """Bind only the caller's current terminal and provider process."""
    handle = os.environ.get("ORCA_TERMINAL_HANDLE")
    if not handle or session == "unknown":
        return None
    try:
        terminal = _orca("terminal", "show", "--terminal", handle)["terminal"]
        expected = "codex" if agent == "codex" else "claude"
        if terminal.get("agentIdentity") != expected or not terminal.get("connected"):
            return None
        pid = os.getppid()
        for _ in range(12):
            proc = _process(pid)
            if proc and re.search(rf"(?:^|/){expected}(?:$|[.-])", proc[1]):
                return {"session": session, "handle": handle,
                        "incarnation": terminal["incarnationId"],
                        "worktree": terminal["worktreeId"], "agent": expected,
                        "pid": pid, "process_start": proc[0]}
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
        # Claim uses this same lock: ownership cannot change between the
        # fresh registry read and terminal input acceptance.
        with _flock(_state_lock_path(project)):
            current = _load_state_for_project(project).get("slugs", {}).get(slug)
            # A removed page must never wake the former owner.
            if current is None:
                current = {}
            _send_pending(rows, current, project, slug, journal, state)
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
        prompt = (f"[annotate] ROUND SUBMITTED: {project}/{slug}; "
                  f"{row['comment_count']} answer(s), delivery {row['id']}. "
                  f"Read annotate inbox {project}/{slug} --unread and annotate cards {project}/{slug}. "
                  "Handle this completed feedback round, preserve prior decisions and history, "
                  "and update the project page. Do not wait for a monitor or another user prompt.")
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
        return {"latest": {k: v for k, v in rows[-1].items()
                           if k in ("id", "state", "detail", "created_at", "updated_at")} if rows else None}
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
