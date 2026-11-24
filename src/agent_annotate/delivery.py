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
from contextlib import ExitStack, contextmanager, nullcontext
from datetime import UTC, datetime
from pathlib import Path

from .paths import STATE_DIR


def _now() -> str:
    return datetime.now(UTC).isoformat()


from .store import write_journal as _atomic  # noqa: E402


def _orca(*args: str) -> dict:
    executable = os.environ.get("ORCA_CLI_COMMAND") or shutil.which("orca")
    if not executable:
        raise RuntimeError("Orca CLI unavailable")
    # Servers outlive their launch directory. A disconnected network mount
    # can hang the Orca shell launcher in getcwd, even after timeout/kill.
    result = subprocess.run([executable, *args, "--json"], capture_output=True, text=True,
                            timeout=15, cwd=Path.home())
    data = json.loads(result.stdout)
    if result.returncode or not data.get("ok"):
        raise RuntimeError(str(data.get("error") or "Orca command failed"))
    return data["result"]


def _process(pid: int) -> tuple[str, str] | None:
    result = subprocess.run(["ps", "-p", str(pid), "-o", "lstart=,comm="],
                            capture_output=True, text=True, timeout=3, cwd=Path.home())
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
                                        capture_output=True, text=True, timeout=3, cwd=Path.home())
                match = re.search(r"(?:^|\s)ORCA_TERMINAL_HANDLE=(term_[A-Za-z0-9_-]+)(?:\s|$)", result.stdout)
                return match[1] if match else None
            parent = subprocess.run(["ps", "-p", str(pid), "-o", "ppid="], capture_output=True, text=True, timeout=3, cwd=Path.home())
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
        pid = os.getppid()
        for _ in range(12):
            proc = _process(pid)
            if proc and re.search(rf"(?:^|/){expected}(?:$|[.-])", proc[1]):
                return _bind(session, expected, handle, pid, proc)
            parent = subprocess.run(["ps", "-p", str(pid), "-o", "ppid="],
                                    capture_output=True, text=True, timeout=3, cwd=Path.home())
            pid = int(parent.stdout.strip())
            if pid < 2:
                break
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired):
        pass
    return None


def _bind(session: str, expected: str, handle: str, pid: int, proc: tuple[str, str]) -> dict | None:
    terminal = _orca("terminal", "show", "--terminal", handle)["terminal"]
    if terminal.get("agentIdentity") != expected or not terminal.get("connected"):
        return None
    return {"session": session, "handle": handle, "incarnation": terminal["incarnationId"],
            "worktree": terminal["worktreeId"], "agent": expected, "pid": pid, "process_start": proc[0],
            **describe_terminal({**terminal, "handle": handle})}


def _claude_session(pid: int) -> dict | None:
    """Claude's own record of the session a live process runs: sessionId, procStart (UTC), status."""
    root = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    try:
        data = json.loads((root / "sessions" / f"{pid}.json").read_text())
        start = subprocess.run(["ps", "-p", str(pid), "-o", "lstart="], capture_output=True, text=True,
                               timeout=3, cwd=Path.home(), env={**os.environ, "TZ": "UTC"}).stdout.strip()
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    # A leftover file from an exited process can name a reused pid.
    return data if isinstance(data, dict) and start and data.get("procStart") == start else None


def _resumed_pids(session: str, expected: str) -> list[int]:
    if expected == "claude":
        # `claude --resume ID --fork-session` carries ID in argv but runs another session.
        root = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "sessions"
        found = []
        for path in root.glob("*.json"):
            try:
                if path.stem.isdigit() and json.loads(path.read_text()).get("sessionId") == session:
                    found.append(int(path.stem))
            except (OSError, ValueError, AttributeError):
                continue
        return [pid for pid in found if (_claude_session(pid) or {}).get("sessionId") == session]
    # A full `ps` listing took over 10 s on the busy M1Max; pgrep returns only candidates.
    found = subprocess.run(["pgrep", "-f", session], capture_output=True, text=True,
                           timeout=10, cwd=Path.home()).stdout.split()
    pids = []
    for pid in found:
        # Exact argv, not `ps` text: a prompt argument can mention the id or the word resume.
        argv = _argv(int(pid)) or []
        if argv and re.search(r"(?:^|/)codex(?:$|[.-])", argv[0]) and _codex_resumes(argv[1:], session):
            pids.append(int(pid))
    return pids


# `codex resume --help` (Codex CLI, 2026-11): options that take one value, and plain flags.
_CODEX_VALUE = {"-c", "--config", "-m", "--model", "-p", "--profile", "-s", "--sandbox", "-a",
                "--ask-for-approval", "-C", "--cd", "--add-dir", "--enable", "--disable", "--remote",
                "--remote-auth-token-env", "--local-provider"}
_CODEX_FLAG = {"--oss", "--search", "--no-alt-screen", "--no-daemon", "--strict-config", "--approve-for-me",
               "--dangerously-bypass-approvals-and-sandbox", "--dangerously-bypass-hook-trust", "--worktree"}


def _codex_resumes(args: list[str], session: str) -> bool:
    """`codex [options] resume [options] ID ...`, parsed the way Codex does.

    shortcut: Codex keeps no per-process session file, so the argv decides. Any option not
    listed above (including -i, --last and fork) fails closed; extend the lists when Codex
    adds options, or switch to the live thread id once Codex exposes it."""
    i, positionals = 0, []
    while i < len(args):
        arg = args[i]
        if arg.startswith("-"):
            name = arg.split("=", 1)[0]
            if name in _CODEX_VALUE:
                i += 1 if "=" in arg else 2  # the value is never the subcommand or the id
                continue
            if arg not in _CODEX_FLAG:
                return False
        else:
            positionals.append(arg)
        i += 1
    # `resume`, then its first positional is the session id; anything else is a fresh session.
    return positionals[:2] == ["resume", session] and i == len(args)


def _argv(pid: int) -> list[str] | None:
    """A process's exact argument vector (macOS KERN_PROCARGS2, Linux /proc)."""
    if sys.platform != "darwin":
        try:
            return Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace").split("\0")[:-1]
        except OSError:
            return None
    import ctypes
    import ctypes.util
    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        argmax, size = ctypes.c_int(0), ctypes.c_size_t(ctypes.sizeof(ctypes.c_int))
        if libc.sysctl((ctypes.c_int * 2)(1, 8), 2, ctypes.byref(argmax), ctypes.byref(size), None, 0):
            return None  # CTL_KERN, KERN_ARGMAX
        buffer, size = ctypes.create_string_buffer(argmax.value), ctypes.c_size_t(argmax.value)
        if libc.sysctl((ctypes.c_int * 3)(1, 49, pid), 3, buffer, ctypes.byref(size), None, 0):
            return None  # CTL_KERN, KERN_PROCARGS2
        raw = buffer.raw[:size.value]
        argc = int.from_bytes(raw[:4], sys.byteorder)
        rest = raw[4:]
        rest = rest[rest.index(b"\0"):].lstrip(b"\0")  # skip the exec path and its padding
        args = rest.split(b"\0")[:argc]
        return [arg.decode(errors="replace") for arg in args] if len(args) == argc else None
    except (OSError, ValueError, AttributeError):
        return None


def resumed_target(session: str, agent: str) -> dict | None:
    """From outside: the one live provider process running this session id, in its Orca terminal."""
    if not re.fullmatch(r"[A-Za-z0-9-]{8,}", session or ""):
        return None
    expected = "codex" if agent == "codex" else "claude"
    try:
        pids = _resumed_pids(session, expected)
        if len(pids) != 1:  # none, or two copies of one session: nothing provable
            return None
        proc = _process(pids[0])
        if not proc or not re.search(rf"(?:^|/){expected}(?:$|[.-])", proc[1]):
            return None
        env = subprocess.run(["ps", "eww", "-p", str(pids[0]), "-o", "command="],
                             capture_output=True, text=True, timeout=3, cwd=Path.home()).stdout
        match = re.search(r"(?:^|\s)ORCA_TERMINAL_HANDLE=(term_[A-Za-z0-9_-]+)(?:\s|$)", env)
        return _bind(session, expected, match[1], pids[0], proc) if match else None
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired):
        return None


def _target_exited(target: dict | None) -> bool:
    """Only positive process-exit evidence authorizes automatic ownership transfer."""
    if not isinstance(target, dict):
        return False
    try:
        pid = int(target.get("pid", 0))
        if pid <= 0:
            return False
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        return False
    try:
        process = _process(pid)
        return bool(process and target.get("process_start") and process[0] != target["process_start"])
    except (OSError, subprocess.SubprocessError):
        return False


def refresh_session_owners(session: str, records: dict, *, via: str = "prompt") -> bool:
    """Rebind a resumed session only after its recorded process provably ended.

    Return whether a matching live target was found, even if another writer won
    the rebind. The watchdog and publish look up the target from outside the
    session. Rebinds outside a prompt are eligible for one watchdog wake-up.
    """
    if not session or session == "unknown":
        return False
    if via == "prompt":  # this prompt is the turn a pending wake-up was for
        def settle(row):
            if row and row.get("state") == "pending" and row["target"].get("session") == session:
                row.update(state="skipped", detail="The owner took a turn before its wake-up")
        for marker in _markers():
            try:  # lock only this session's own pending marker, and never wait for it
                row = json.loads(marker.read_text())
                if row.get("state") == "pending" and row["target"].get("session") == session:
                    _update_marker(marker, settle, block=False)
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                continue
    exited, targets, refreshed = {}, {}, []
    find_target = resumed_target if via in ("watchdog", "publish") else capture_target
    resumed = False
    for (project, slug), record in records.items():
        old = record.get("owner_target")
        if (record.get("owner_session") != session or not isinstance(old, dict)
                or old.get("session", session) != session or record.get("archived")
                or record.get("consolidated_into")):
            continue
        try:
            key = (old.get("pid"), old.get("process_start"))
            if key not in exited:
                exited[key] = _target_exited(old)
            if not exited[key]:
                continue
            agent = old.get("agent")
            if agent not in ("claude", "codex"):
                continue
            if agent not in targets:
                targets[agent] = find_target(session, agent)
            target = targets[agent]
            # Orca gives a relaunched pane a new handle; its worktree id survives a restart.
            if not target or (old.get("worktree") and old["worktree"] != target.get("worktree")):
                continue
            resumed = True
            from .cli import (
                _flock,
                _load_state_for_project,
                _save_state_for_project,
                _state_lock_path,
                _write_owner_meta,
            )
            with _flock(_state_lock_path(project)):
                state = _load_state_for_project(project)
                current = state.get("slugs", {}).get(slug)
                # A concurrent claim or a PID reused since the scan must win.
                if (not current or current.get("owner_session") != session
                        or current.get("owner_target") != old or not _target_exited(old)):
                    continue
                current["owner_target"] = target
                _save_state_for_project(project, state)
                if current.get("slug_dir"):
                    _write_owner_meta(Path(current["slug_dir"]), current)
                record.update(current)
            refreshed.append((project, slug, current))
        except (OSError, ValueError, TypeError, KeyError, RuntimeError, subprocess.SubprocessError):
            continue  # Hooks must not prevent a session or prompt from starting.
    for target in filter(None, targets.values()) if via != "prompt" else ():
        pages = [[p, s] for p, s, c in refreshed if c["owner_target"] == target]
        marker = STATE_DIR / "resumes" / f"{target['pid']}-{re.sub(r'[^0-9A-Za-z]', '', target['process_start'])}.json"

        def merge(row, pages=pages, target=target):
            # SessionStart and the watchdog can each re-bind a page: merge them, and
            # never reopen a wake-up that was already consumed.
            if not row:
                return {"state": "pending", "rebound_at": _now(), "via": via, "target": target, "pages": pages}
            if row.get("state") == "pending":
                row["pages"] += [page for page in pages if page not in row["pages"]]
            return None
        if pages:
            _update_marker(marker, merge)
    # Shared tabs route through their canonical page, which must be refreshed first.
    for project, slug, current in refreshed:
        try:
            dispatch_record(current, project, slug)
        except (OSError, ValueError, TypeError, KeyError, RuntimeError, subprocess.SubprocessError):
            continue
    return resumed


WAKE_CAP = 3  # wake-ups per watchdog pass: after a reboot every resumed owner is eligible at once
GRACE = 300  # seconds a queued, unconfirmed Send may still give the owner its turn


def _markers() -> list[Path]:
    return sorted((STATE_DIR / "resumes").glob("*.json"))


def _update_marker(marker: Path, change, *, block: bool = True) -> dict | None:
    """Read-modify-write one resume marker under its lock; `change` edits the row or returns a new one.

    block=False gives up when the watchdog holds the lock (it settles the marker itself)."""
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        with marker.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | (0 if block else fcntl.LOCK_NB))
            row = json.loads(marker.read_text()) if marker.exists() else None
            before = json.dumps(row)
            row = change(row) or row
            if row is not None and json.dumps(row) != before:
                row["updated_at"] = _now()
                _atomic(marker, row)
            return row
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def _same_process(a: dict, b: dict) -> bool:
    return all(a.get(k) == b.get(k) for k in ("session", "pid", "process_start", "handle", "incarnation"))


def _age(stamp: str) -> float:
    try:
        return (datetime.now(UTC) - datetime.fromisoformat(stamp)).total_seconds()
    except (TypeError, ValueError):
        return float("inf")


def _turn_since(row: dict) -> tuple[str | None, str]:
    """("proven", why) when a Send or inbox read shows the owner had a turn since the re-bind;
    ("unresolved", why) while a Send to it may still start one; (None, "") otherwise."""
    target, unresolved = row["target"], ""
    for project, slug in row["pages"]:
        for r in _journal_rows(project, slug):
            if r.get("owner_session") != target["session"]:
                continue
            receipt = (r.get("receipt") or {}).get("prompt") or {}
            request = receipt.get("requestId") or r.get("id")
            if r.get("state") == "acknowledged" and (r.get("acknowledged_at") or "") >= row["rebound_at"]:
                return "proven", f"The owner read its inbox for {project}/{slug} after the re-bind"
            if r.get("state") == "pending" and _age(r.get("created_at") or "") < GRACE:
                unresolved = f"Send {request} is about to be delivered; wake-up deferred"
                continue
            if not _same_process(r.get("target") or {}, target):
                continue
            if r.get("state") == "started" or "turn_started" in receipt.get("stages", []):
                return "proven", f"Send {request} started the owner's turn"
            if r.get("state") in ("attempting", "accepted", "uncertain"):
                if "turn_started" in _replay(r, target):
                    return "proven", f"Send {request} started the owner's turn (Orca request replayed)"
                if _age(r.get("attempted_at") or "") < GRACE:
                    unresolved = f"Send {request} is queued without a confirmed turn; wake-up deferred"
    return ("unresolved", unresolved) if unresolved else (None, "")


def _replay(row: dict, target: dict) -> list[str]:
    """Ask Orca what became of a Send by its request ID; Orca replays the result and never repeats it."""
    request = ((row.get("receipt") or {}).get("prompt") or {}).get("requestId")
    if not request or not row.get("prompt"):
        return []
    try:
        receipt = _orca("terminal", "send", "--terminal", target["handle"], "--text", row["prompt"], "--enter",
                        "--retry-request", request, "--wait-submit", "1").get("send", {})
        return (receipt.get("prompt") or {}).get("stages", []) if receipt.get("accepted") else []
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired):
        return []


def _provider_idle(target: dict) -> bool:
    """Only the provider's own idle signal: a user or a Send may have started a turn meanwhile."""
    if target.get("agent") == "claude":
        session = _claude_session(int(target["pid"])) or {}
        return session.get("sessionId") == target["session"] and session.get("status") == "idle"
    try:
        _orca("terminal", "wait", "--terminal", target["handle"], "--for", "tui-idle", "--timeout-ms", "1000")
        return True
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired):
        return False


def wake_resumed() -> list[dict]:
    """Give each owner rebound without a prompt one turn, so it re-arms its waits; at most once."""
    woken, attempts = [], 0
    for marker in _markers():
        try:
            with marker.with_suffix(".lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                row = json.loads(marker.read_text())
                if row.get("state") != "pending":
                    continue
                before = json.dumps(row)
                attempts += _wake_one(row, marker, capped=attempts >= WAKE_CAP)
                if row["state"] == "pending":
                    if json.dumps(row) != before:
                        row["updated_at"] = _now()
                        _atomic(marker, row)
                    continue
                row["updated_at"] = _now()
                _atomic(marker, row)
                woken.append(row)
        except (OSError, ValueError, TypeError, KeyError):
            continue
    return woken


def _wake_one(row: dict, marker: Path, *, capped: bool) -> int:
    """Settle or defer one pending marker; returns 1 when input was sent."""
    target = row["target"]
    if _target_exited(target):
        row.update(state="stale", detail="Owner process ended before its wake-up")
        return 0
    ready, detail = _target_ready(target)
    if not ready:
        row["detail"] = detail
        return 0
    from .cli import _flock, _load_state_for_project, _state_lock_path
    from .workspace import workspace_owner_record

    def owner_project(project, slug):
        current = _load_state_for_project(project).get("slugs", {}).get(slug) or {}
        return (workspace_owner_record(current).get("workspace_owner") or {}).get("project", project)
    projects = {p for page in row["pages"] for p in (page[0], owner_project(*page))}
    with ExitStack() as stack:
        # The locks dispatch_record holds while it sends a Send, in its order: each page's
        # journal, then the tab and canonical projects' claim locks. Under them no Send or
        # claim can land between these checks and the input.
        for project, slug in sorted(row["pages"]):
            stack.enter_context(journal_lock(project, slug))
        for project in sorted(projects):
            stack.enter_context(_flock(_state_lock_path(project)))
        owned = []
        for project, slug in row["pages"]:
            current = _load_state_for_project(project).get("slugs", {}).get(slug) or {}
            # A linked tab follows its canonical page's owner, as delivery does.
            effective = workspace_owner_record(current)
            fresh = (effective.get("workspace_owner") or {}).get("project", project)
            if (fresh in projects and effective.get("owner_session") == target["session"]
                    and not current.get("archived")
                    and _same_process(effective.get("owner_target") or {}, target)):
                owned.append([project, slug])
        if not owned:
            row.update(state="superseded", detail="Every page moved to another owner before the wake-up")
            return 0
        row["pages"] = owned
        turn, why = _turn_since(row)
        if turn == "proven":
            row.update(state="skipped", detail=why)
            return 0
        if turn == "unresolved":
            row["detail"] = why
            return 0
        if capped:
            row["detail"] = f"Waiting: at most {WAKE_CAP} wake-ups per watchdog pass"
            return 0
        if not _provider_idle(target):
            row["detail"] = "Owner is busy; wake-up deferred until it is idle"
            return 0
        with ExitStack() as outbox:
            # The page server appends a Send under this lock, never held across an Orca call:
            # a Send durable before the reservation defers the wake-up; one after it is newer.
            for project, slug in sorted(owned):
                outbox.enter_context(outbox_lock(project, slug))
            for project, slug in owned:
                current = _load_state_for_project(project).get("slugs", {}).get(slug) or {}
                if _outbox_waiting(current, project, slug, target["session"]):
                    row["detail"] = f"A Send on {project}/{slug} is in the outbox; wake-up deferred"
                    return 0
            row.update(state="attempting", attempted_at=_now())
            _atomic(marker, row)  # journaled before input, so a crash never sends twice
        pages = ", ".join(f"{project}/{slug}" for project, slug in owned)
        prompt = (f"[annotate] This session was resumed after a restart and owns {pages} again. "
                  "Re-arm any wait loop or monitor you were running, then read "
                  "annotate inbox <page> --unread for each page.")
        try:
            receipt = _orca("terminal", "send", "--terminal", target["handle"], "--text", prompt,
                            "--enter", "--wait-submit", "1").get("send", {})
            row.update(state="sent" if receipt.get("accepted") else "uncertain", receipt=receipt)
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as exc:
            row.update(state="uncertain", detail=f"Send outcome unproven: {str(exc)[:250]}")
    return 1


@contextmanager
def _page_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield path


def journal_lock(project: str, slug: str):
    """The page journal lock: dispatch_record holds it, Orca send included."""
    return _page_lock((STATE_DIR / "deliveries" / project / f"{slug}.json").with_suffix(".lock"))


def outbox_lock(project: str, slug: str):
    """A short leaf lock: Send enqueue, and the wake-up's outbox check plus reservation.

    Its own tree: under deliveries/, page `x.outbox`'s journal lock would be this file."""
    return _page_lock(STATE_DIR / "outbox-locks" / project / f"{slug}.lock")


def _outbox_waiting(record: dict, project: str, slug: str, session: str) -> bool:
    """A round for this owner is durable in the bus but not yet journaled by dispatch_record."""
    try:
        journal = STATE_DIR / "deliveries" / project / f"{slug}.json"
        offset = json.loads(journal.read_text())["offset"] if journal.exists() else 0
        with Path(record.get("bus_file") or "").open("rb") as stream:
            stream.seek(offset)
            for line in stream:
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                if (event.get("event") == "session_push" and event.get("round") is True
                        and event.get("automatic_delivery") is True and event.get("owner_session") == session):
                    return True
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return False


def _journal_rows(project: str, slug: str) -> list[dict]:
    try:
        return list(json.loads((STATE_DIR / "deliveries" / project / f"{slug}.json").read_text())
                    .get("deliveries", {}).values())
    except (OSError, ValueError):
        return []


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
        from .page_names import page_name
        from .urls import page_url, redact_review_key
        workspace_owner = record.get("workspace_owner") or {}
        url = redact_review_key(workspace_owner.get("url") or page_url(record))
        name = workspace_owner.get("name") or page_name(record)
        prompt = (f"[annotate] Round submitted on {name}{f' {url}' if url else ''}. "
                  f"Read annotate inbox {project}/{slug} --unread. "
                  "Act on every answer and note; show results on the page; "
                  "withdraw questions that no longer apply; "
                  "reply in chat with one line and the URL.")
        from .board_followups import check_clause
        prompt += check_clause(record, project, slug)
        # The prompt is kept so its Orca request ID can be replayed (never repeated) later.
        row.update(state="attempting", attempted_at=_now(), prompt=prompt)
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
        deliveries = []
        for row in rows:
            public = {k: v for k, v in row.items()
                      if k in ("id", "state", "detail", "created_at", "updated_at")}
            stages = (row.get("receipt") or {}).get("prompt", {}).get("stages", [])
            public["delivered"] = row.get("state") in ("started", "acknowledged") or (
                row.get("state") == "accepted" and "input_accepted" in stages)
            deliveries.append(public)
        latest = deliveries[-1]
        target = rows[-1].get("target") or {}
        if latest.get("state") in ("pending", "accepted", "started") and _target_exited(target):
            latest.update(state="pending", delivered=False, owner_running=False,
                          detail="Owner process ended; waiting for the session to resume")
        return {"latest": latest, "deliveries": deliveries}
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
