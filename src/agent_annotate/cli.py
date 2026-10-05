#!/usr/bin/env python3
"""annotate — single CLI entry point for Agent Annotate.

Invocation:

    annotate <cmd> ...                       the `annotate` entry point / shim
    python -m agent_annotate.cli <cmd> ...   always works once the package imports

`publish` and `install-shim` write ~/.local/bin/annotate when no entry point is
there yet. A bare `annotate` that resolves to something else (on at least one
machine the name belongs to libgd's image tool) is the single most expensive
line this CLI has ever printed, so every message uses the module form unless
`command -v annotate` really is this package.

Subcommands:
    publish <slug-dir>                    start sync_server, route, claim ownership
    unpublish <slug>                      tear down route + stop server
    claim <slug>                          take ownership of a page for this session
    install-shim [--force]                (re)write ~/.local/bin/annotate
    install-skill --provider P --dest D   write a skill directory from the packaged text
    status [<slug>] [--retired]           list active slugs / health / retired rows
    close <slug> [--older-than 30d]       archive decision cards nobody answered
    retire <slug>|--dead                  move dead registry rows to state/retired/
    revive [--install|--uninstall]        restart dead pages on their port, owner kept
    doctor                                validate the installation
    migrate <legacy.html>                 one-shot v1→v2 migration
    inbox <slug> [--unread] [--json]      read this session's unseen bus events
    cards <slug>                          list decision cards and their verdicts
    ask <slug> --from cards.json          create/refresh decision cards in one call
    eval [--since DATE]                   read-only baseline of the review loop
    cost [--since DATE] [--estimate M]    read-only token/speed cost from agent transcripts
    prune-bus [--days N] [--apply]        archive quiet buses and their cursors
    watch <slug>                          tail comments to stdout (sidecar)
    monitor <slug> [--owner ID]           exclusive session monitor + live lease
    sessions [--cwd DIR]                  list Codex threads available for ownership
    connect <slug> --thread ID            detached Codex delivery monitor
    disconnect <slug>                     release a monitor, keep the server
    send --thread ID <message>            one message to a Codex thread
    publish-version <slug-dir> <vN>       add new version + swap symlink
    archive-comment <slug> <comment-id>
    addressed <slug> <comment-id> [--response "<text>"]
    resolve <slug> <comment-id> --in-version <vN> --anchor <id>
    carry <slug> <comment-id> --to-version <vN> --anchor <id>
    hook-check                            the UserPromptSubmit hook, in-process
    mcp                                   MCP server over stdio

Every slug argument accepts `<slug>` or `<project>/<slug>`, and `--project`
is honoured wherever a slug is taken.

Every location comes from paths.py: the registry at <state>/<project>.json,
buses at <bus root>/<project>/<slug>.ndjson. Both default to the roots the
skill-directory install used (~/.claude/annotate-state/state and
~/.claude/annotate-bus); ANNOTATE_STATE_DIR and ANNOTATE_BUS_ROOT relocate them.
"""

import argparse
import contextlib
import fcntl
import hashlib
import ipaddress
import json
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from http.client import HTTPException
from pathlib import Path

from . import __version__
from .categories import CATEGORIES as CATEGORY_IDS
from .categories import comment_category as _comment_category
from .pagegen import add_parser as _add_new_parser
from .paths import (
    BUS_OFFSET_ROOT,
    BUS_ROOT,
    CONFIG_DIR,
    HOOK_SCRIPT,
    LOCK_DIR,
    LOG_DIR,
    MONITOR_OFFSET_ROOT,
    MONITOR_ROOT,
    PACKAGE_DIR,
    PROJECTS_TOML,
    SETTINGS_JSON,
    SHIM_PATH,
    STATE_DIR,
    WEB_DIR,
    ensure_runtime_dirs,
)
from .urls import mounted_url, page_url, redact_review_key, redact_share_links

SHIM_MARKER = "agent-annotate shim"

def _env_heartbeat_interval() -> float:
    """Seconds between quiet-branch heartbeats. Default 0: disabled.

    Claude Code's Monitor tool expires only at its timeout (<= 30 min); arm
    `annotate monitor <slug>` inside the Monitor tool with timeout_ms 1800000
    and re-arm on expiry; the 2026-07 idle-reap no longer occurs (verified
    2026-09-17, 150 s silent stream delivered).

    The heartbeat existed only to keep that reaper away, and it cost a wakeup
    every 30 s — about 120 lines an hour of nothing happening — on a stream
    whose whole value is that a line means something. Set
    ANNOTATE_MONITOR_HEARTBEAT_INTERVAL to a positive number of seconds to opt
    back in under a supervisor that really does need liveness output.
    """
    raw = os.environ.get("ANNOTATE_MONITOR_HEARTBEAT_INTERVAL")
    if raw is None or raw == "":
        return 0.0
    try:
        return float(raw)
    except ValueError:
        print(f"WARN: invalid ANNOTATE_MONITOR_HEARTBEAT_INTERVAL={raw!r}, disabling", file=sys.stderr)
        return 0.0

MONITOR_HEARTBEAT_INTERVAL = _env_heartbeat_interval()

MONITOR_EVENTS = {
    "comment_created",
    "comment_updated",
    "comment_reply",
    "comment_accepted",
    "comment_archived",
    "comment_reanchored",
    "comment_restored",
    "session_push",
    "round_submitted",
    "round_discarded",
}

# What the monitor actually prints. Everything else in MONITOR_EVENTS is
# advertised in the lease but stays off stdout: a monitored stream is read by
# an agent one line at a time, so a line has to be worth a turn. A verdict now
# arrives as part of a round, and the round is the actionable unit.
MONITOR_PRINT_EVENTS = {"session_push", "round_submitted"}


# ────────────────────────────────────────────────────────────────────────────
# Session identity
# ────────────────────────────────────────────────────────────────────────────
def _session_id() -> str:
    """This agent session's id, in the order the harnesses actually set it.

    CLAUDE_SESSION_ID is empty under Claude Code — the variable carrying the id
    is CLAUDE_CODE_SESSION_ID. Reading the wrong one is why every monitor lease
    was labelled `interactive-ppid-<n>` and why no page could be attributed to
    the session that published it.
    """
    for var in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "CLAUDE_SESSION_ID"):
        val = os.environ.get(var)
        if val and val.strip():
            return val.strip()
    return "unknown"


def _session_agent() -> str:
    if (os.environ.get("CLAUDE_CODE_SESSION_ID")
            or os.environ.get("CLAUDE_SESSION_ID")
            or os.environ.get("CLAUDE_AGENT_ID")):
        return "claude-code"
    if os.environ.get("CODEX_THREAD_ID") or os.environ.get("CODEX_HOME"):
        return "codex"
    return "coding-agent"


def _session_label(session_id: str | None = None) -> str:
    """Owner label a human can read at a glance: working dir + short id."""
    sid = session_id or _session_id()
    try:
        cwd = Path.cwd().name or "session"
    except OSError:
        cwd = "session"
    return f"{cwd}:{sid[:8] if sid != 'unknown' else 'unknown'}"


def _safe_component(value: str) -> str:
    """One path segment that cannot escape its parent, whatever the id holds."""
    out = "".join(ch if (ch.isalnum() or ch in "._-") else "-" for ch in (value or ""))
    return out.strip("-") or "unknown"


def _offset_file(project: str, slug: str, session_id: str | None = None) -> Path:
    """This session's read cursor for one slug's bus.

    v2.18 kept a single cursor per slug, shared with the hook, so whichever
    session was asked first consumed everybody's delta — 22 of 22 observed
    `inbox --unread` calls answered "(no new events)". Only a session with no
    discoverable id falls back to that shared path.
    """
    sid = session_id or _session_id()
    if sid == "unknown":
        return BUS_OFFSET_ROOT / project / f"{slug}.offset"
    return BUS_OFFSET_ROOT / _safe_component(sid) / project / f"{slug}.offset"


def _legacy_offset(project: str, slug: str) -> int:
    """The v2.18 shared cursor for a slug, or 0.

    It was advanced by the old hook on every prompt from any session, so for
    every page that exists today its value is effectively "now". That makes it
    the right seed for a per-session cursor that does not exist yet: seeding at
    0 would replay every page's whole history into every live session at once.
    """
    path = BUS_OFFSET_ROOT / project / f"{slug}.offset"
    if not path.exists():
        return 0
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def _bus_emit(bus_file, event: dict) -> None:
    """Append one NDJSON event to a slug's bus. Never raises: telemetry must
    not be able to fail a publish."""
    if not bus_file:
        return
    try:
        path = Path(bus_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"ts": _now_iso()}
        payload.update(event)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(redact_share_links(payload), ensure_ascii=False,
                                separators=(",", ":")) + "\n")
    except Exception:
        pass


def _clip(text: str, n: int = 80) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "\u2026"


# ────────────────────────────────────────────────────────────────────────────
# CLI shim — ~/.local/bin/annotate
# ────────────────────────────────────────────────────────────────────────────
def _module_invocation() -> str:
    """The interpreter-module form, which works wherever the package imports."""
    return f"{sys.executable} -m agent_annotate.cli"


def _shim_body() -> str:
    return (
        "#!/bin/sh\n"
        "# agent-annotate shim — written by `annotate install-shim`, and by\n"
        "# `annotate publish`. Safe to delete; re-create with:\n"
        f"#   {_module_invocation()} install-shim\n"
        f'exec "{sys.executable}" -m agent_annotate.cli "$@"\n'
    )


def _is_ours(body: str) -> bool:
    """True for anything that runs this package: the shim written here, a
    `uv tool install` / pip entry point (which imports agent_annotate), or the
    skill-directory shim that predates packaging."""
    return SHIM_MARKER in body or "agent_annotate" in body


def _shim_state() -> tuple[str, str]:
    """('absent'|'shim'|'entrypoint'|'foreign', body).

    `shim` is a launcher this function's sibling wrote (any version);
    `entrypoint` is a console script that already runs this package and is
    never overwritten without --force.
    """
    if not SHIM_PATH.exists() and not SHIM_PATH.is_symlink():
        return "absent", ""
    try:
        body = SHIM_PATH.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return "foreign", str(e)
    if SHIM_MARKER in body:
        return "shim", body
    if "agent_annotate" in body:
        return "entrypoint", body
    return "foreign", body


def _shim_target_alive(body: str) -> bool:
    """Does the interpreter/script a shim execs still exist?"""
    for line in body.splitlines():
        if line.startswith("exec "):
            try:
                argv = shlex.split(line[len("exec "):])
            except ValueError:
                return False
            paths = [a for a in argv if a.startswith("/")]
            return all(Path(p).exists() for p in paths) if paths else True
    return False


def _ensure_shim_installed(force: bool = False, refresh: bool = False) -> tuple[bool, str]:
    """Idempotently write the `annotate` launcher. Returns (changed, message).

    Writes only when the path is absent or holds a shim of ours whose target is
    gone. `refresh` (install-shim) also rewrites a shim of ours that points
    somewhere else, e.g. at the pre-package skill directory; `force` overwrites
    a file this package did not write. A console-script entry point is never
    touched without `force`: it already runs this package.
    """
    state, body = _shim_state()
    wanted = _shim_body()
    if state == "foreign" and not force:
        return False, (f"{SHIM_PATH} exists and was not written by this package — "
                       f"left alone (`install-shim --force` overwrites it)")
    if state == "entrypoint" and not force:
        return False, f"entry point already at {SHIM_PATH}"
    if state == "shim" and body == wanted and os.access(SHIM_PATH, os.X_OK):
        return False, f"already current at {SHIM_PATH}"
    if state == "shim" and not (force or refresh) and _shim_target_alive(body):
        return False, (f"{SHIM_PATH} runs a different annotate install — left alone "
                       f"(`install-shim` repoints it here)")
    try:
        SHIM_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SHIM_PATH.with_name(SHIM_PATH.name + ".tmp")
        tmp.write_text(wanted, encoding="utf-8")
        os.chmod(tmp, 0o755)
        os.replace(tmp, SHIM_PATH)
    except OSError as e:
        return False, f"could not write {SHIM_PATH}: {e}"
    return True, f"wrote {SHIM_PATH} → {_module_invocation()}"


_INV_CACHE: str | None = None


def _inv() -> str:
    """The invocation to print in messages.

    The shim name when typing it actually reaches this CLI, the absolute
    python3 form otherwise. A printed `annotate …` that resolves to libgd is
    the single most expensive line this CLI has ever emitted.
    """
    global _INV_CACHE
    if _INV_CACHE is None:
        _INV_CACHE = _module_invocation()
        try:
            found = shutil.which("annotate")
            if found and _is_ours(Path(found).read_text(encoding="utf-8", errors="replace")):
                _INV_CACHE = "annotate"
        except (OSError, ValueError):
            pass
    return _INV_CACHE


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_state_for_project(project: str) -> dict:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    p = STATE_DIR / f"{project}.json"
    if not p.exists():
        return {"project": project, "slugs": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"project": project, "slugs": {}}


def _save_state_for_project(project: str, state: dict) -> None:
    _save_private_json(STATE_DIR / f"{project}.json", state)


def _save_private_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(redact_share_links(data), output, indent=2, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _all_state_files() -> list[Path]:
    if not STATE_DIR.exists():
        return []
    return sorted(STATE_DIR.glob("*.json"))


@contextlib.contextmanager
def _flock(lock_path: Path):
    """Advisory exclusive lock spanning a read-modify-write cycle.

    Only coordinates with other processes going through this same helper.
    Tries non-blocking first; if held, polls for up to 30s before failing
    loudly rather than blocking forever on a peer that crashed mid-write.
    """
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+")
    try:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            deadline = time.monotonic() + 30
            acquired = False
            while time.monotonic() < deadline:
                time.sleep(0.5)
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except OSError:
                    continue
            if not acquired:
                raise TimeoutError(
                    f"timed out after 30s waiting for lock {lock_path} — "
                    "check for a stuck annotate process holding it"
                )
        yield
    finally:
        fh.close()


def _state_lock_path(project: str) -> Path:
    return LOCK_DIR / f"{project}.json.lock"


def _tunnel_lock_path() -> Path:
    return LOCK_DIR / "tunnel.lock"


def _load_projects_toml() -> dict:
    """Return parsed projects.toml — or empty dict if missing.

    Uses tomllib (3.11+) or tomli fallback.
    """
    if not PROJECTS_TOML.exists():
        return {}
    try:
        import tomllib  # type: ignore[import]
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            print("WARN: no tomllib/tomli available — projects.toml ignored", file=sys.stderr)
            return {}
    return tomllib.loads(PROJECTS_TOML.read_text(encoding="utf-8"))


def _slug_project(slug_dir: Path, explicit_project: str | None = None) -> tuple[str, str]:
    """An existing directory keeps its registered scope across aliases and sessions."""
    existing = {(p, s) for p, s, r in _registry_entries() if r.get("slug_dir")
                and Path(r["slug_dir"]).resolve() == slug_dir.resolve()}
    if len(existing) > 1:
        raise ValueError("page directory has ambiguous registrations; no new scope created")
    if existing:
        return existing.pop()
    slug = slug_dir.name
    project = explicit_project or slug_dir.parent.name or "default"
    return project, slug


def _project_config(project: str) -> dict:
    config = _load_projects_toml()
    cfg = {**config.get("defaults", {}), **config.get(project, {})}
    cfg.setdefault("transport", "funnel")
    cfg.setdefault("hostname", None)
    cfg.setdefault("port_base", 8800)
    cfg.setdefault("path_prefix", None)
    return cfg


_PROJECT_CORE_KEYS = frozenset({"transport", "hostname", "port_base", "path_prefix", "public", "trusted_access_origins",
                               "local_author", "local_author_name", "reviewer_aliases"})


def _transport_opts(cfg: dict) -> dict:
    """Every projects.toml key the CLI does not consume itself goes to the
    transport as an option (`env_file`, `tunnel_id`, `binary`, …), so a
    machine's credentials live in its config, not in the transport source."""
    return {k: v for k, v in (cfg or {}).items() if k not in _PROJECT_CORE_KEYS}


def _port_listen_pid(port: int) -> int | None:
    """Return the PID of the first process LISTENing on TCP `port`, or None.

    Raises on lsof failure/absence — callers must catch and fall back rather
    than trusting an unchecked port as free.
    """
    result = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fp"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    for line in result.stdout.splitlines():
        if line.startswith("p"):
            try:
                return int(line[1:])
            except ValueError:
                continue
    return None


def _find_free_port_after(start: int, registered_pid: int | None = None) -> int:
    """Lowest usable port at or after `start`.

    The probe must bind EXACTLY what the sync server binds — ("localhost", p)
    with allow_reuse_address — or it answers a different question than the one
    asked.

    Both halves matter, and getting either wrong is dangerous:

    * The old probe bound ("", p) with no option. A loopback socket left in
      TIME_WAIT refuses a 0.0.0.0 bind, so re-publishing a slug whose port had
      just served traffic always skipped to the next port. A moving local port
      makes every port-keyed route (a `tailscale serve` mapping) leak a new
      entry on every publish.
    * Adding SO_REUSEADDR while still binding ("", p) is WORSE: on BSD/macOS
      that option lets a wildcard bind sit on top of a DIFFERENT local address,
      so 0.0.0.0:8813 binds cleanly while a live server is listening on
      127.0.0.1:8813 — allocation would hand out a port already in use and two
      servers would fight over one slug. Verified 2026-07-31 against the live
      8800/8812/8813 servers.

    Binding the same address the server does makes SO_REUSEADDR safe: it
    reuses TIME_WAIT but is still refused by an active LISTEN on that exact
    address. The lsof cross-check below stays as the second opinion.
    """
    import socket
    p = start
    lsof_ok = True
    conflicting_pids: set[int] = set()
    while p < start + 50:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("localhost", p))
            except OSError:
                p += 1
                continue
        if lsof_ok:
            try:
                listen_pid = _port_listen_pid(p)
            except (OSError, subprocess.SubprocessError) as e:
                print(
                    f"WARN: port-liveness check unavailable ({e}); trusting OS bind test only",
                    file=sys.stderr,
                )
                lsof_ok = False
                listen_pid = None
            if (
                listen_pid is not None
                and listen_pid != registered_pid
                and registered_pid is not None
                and not _is_process_alive(registered_pid)
                and _is_process_alive(listen_pid)
            ):
                conflicting_pids.add(listen_pid)
                p += 1
                continue
        return p
    if conflicting_pids:
        raise RuntimeError(
            f"No free port found in [{start}, {start+50}) — "
            f"held by other process(es): {', '.join(str(pid) for pid in sorted(conflicting_pids))}"
        )
    raise RuntimeError(f"No free port found in [{start}, {start+50})")


def _is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _resolve_author(cli_value: str | None) -> str:
    """Resolve author identity in priority order:
    1. CLI --author flag
    2. $ANNOTATE_AUTHOR env var
    3. $CLAUDE_AGENT_ID env var
    4. Default 'agent:claude'
    """
    if cli_value:
        return cli_value
    env_val = os.environ.get("ANNOTATE_AUTHOR")
    if env_val:
        return env_val
    env_val = os.environ.get("CLAUDE_AGENT_ID")
    if env_val:
        return env_val
    return "agent:claude"


# ────────────────────────────────────────────────────────────────────────────
# Hook installer (UserPromptSubmit → check-comment-bus.sh)
# ────────────────────────────────────────────────────────────────────────────
HOOK_COMMAND = str(HOOK_SCRIPT)


def _is_our_hook_command(command: str) -> bool:
    """Any registered command that runs this hook — the packaged script, the
    skill-directory copy it replaces, or `annotate hook-check`. Registering a
    second spelling would fire the hook twice per prompt."""
    cmd = (command or "").strip()
    if not cmd:
        return False
    if cmd == HOOK_COMMAND or cmd.endswith("/check-comment-bus.sh"):
        return True
    return cmd.endswith(" hook-check") and "annotate" in cmd


def _ensure_hook_installed() -> tuple[bool, str]:
    """Idempotently merge the check-comment-bus.sh hook into settings.json.

    Returns (was_added, message).
    """
    if not SETTINGS_JSON.exists():
        return False, f"settings.json not found at {SETTINGS_JSON}"
    try:
        raw = SETTINGS_JSON.read_text(encoding="utf-8")
        settings = json.loads(raw)
    except Exception as e:
        return False, f"could not parse settings.json: {e}"

    # A wheel does not always preserve the execute bit; the hook is registered
    # as a bare path, so make sure the shell can run it.
    try:
        if not os.access(HOOK_SCRIPT, os.X_OK):
            os.chmod(HOOK_SCRIPT, 0o755)
    except OSError:
        pass

    settings.setdefault("hooks", {})
    ups = settings["hooks"].setdefault("UserPromptSubmit", [])
    # Look for an existing entry matching our command
    for group in ups:
        if not isinstance(group, dict):
            continue
        for h in group.get("hooks", []) or []:
            if isinstance(h, dict) and _is_our_hook_command(h.get("command", "")):
                return False, "hook already present in settings.json (no change)"

    ups.append({
        "hooks": [
            {
                "command": HOOK_COMMAND,
                "type": "command",
                # Claude Code's own default for a UserPromptSubmit command hook.
                # The previous explicit 5 bought nothing and cost notices: on a
                # loaded machine the hook was killed mid-scan, discarding that
                # turn's reminder and stranding the lock for other sessions.
                "timeout": 30,
            }
        ]
    })

    # Preserve private settings permissions and never follow a predictable temp symlink.
    mode = SETTINGS_JSON.stat().st_mode & 0o777
    descriptor, temporary = tempfile.mkstemp(prefix=".annotate-settings-", dir=SETTINGS_JSON.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(settings, output, indent=2, ensure_ascii=False)
            os.fchmod(output.fileno(), mode)
        os.replace(temporary, SETTINGS_JSON)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return True, f"added UserPromptSubmit hook → {HOOK_COMMAND}"


# ────────────────────────────────────────────────────────────────────────────
# Server lifecycle
# ────────────────────────────────────────────────────────────────────────────
def _start_server(slug_dir: Path, port: int, bus_dir: Path, public_base_path: str | None) -> int:
    """Spawn sync_server.py in v2 mode. Returns PID."""
    from .paths import PACKAGE_DIR
    isolated = "site-packages" in PACKAGE_DIR.parts
    cmd = [
        sys.executable,
        *(["-I"] if isolated else []),
        "-m",
        "agent_annotate.sync_server",
        "--slug-dir", str(slug_dir),
        "--slug", slug_dir.name,
        "--bus-dir", str(bus_dir),
        "--port", str(port),
        "--strict-port",
    ]
    if public_base_path:
        cmd += ["--public-base-path", public_base_path]
    local = _project_config(bus_dir.name)
    for key in ("local_author", "local_author_name"):
        value = local.get(key)
        if value is not None:
            if (not isinstance(value, str) or not value.strip() or len(value) > 256
                    or any(ord(char) < 32 or ord(char) == 127 for char in value)):
                raise ValueError(f"project {key} must be a nonempty identity without control characters")
            if key == "local_author_name" and not local.get("local_author"):
                raise ValueError("project local_author_name requires local_author")
            cmd += ["--" + key.replace("_", "-"), value.strip()]
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{slug_dir.name}.log"
    fh = open(log_path, "ab", buffering=0)
    environment = os.environ.copy()
    if isolated:
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
    proc = subprocess.Popen(
        cmd,
        stdout=fh,
        stderr=fh,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        env=environment,
    )
    # Give it a moment to bind
    time.sleep(0.5)
    return proc.pid


def _stop_server(pid: int) -> bool:
    if not _is_process_alive(pid):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    for _ in range(20):
        time.sleep(0.1)
        if not _is_process_alive(pid):
            return True
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    return True


# ────────────────────────────────────────────────────────────────────────────
# Task 4 — Build-time JS lint
# ────────────────────────────────────────────────────────────────────────────
# Matches a full <script ...>...</script> block, capturing the opening tag and body.
# Group 1 = opening tag (e.g. `<script type="text/javascript">`),
# Group 2 = body content.
_SCRIPT_BLOCK_RE = re.compile(
    r'(<script(?:\s[^>]*)?/>|<script(?:\s[^>]*)?>)(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
# Matches src= in a script opening tag → external file, not inline JS.
_SCRIPT_SRC_RE = re.compile(r'\bsrc\s*=', re.IGNORECASE)
# Matches type= values that are NOT JavaScript (e.g. application/json, text/template).
# We skip any type that isn't absent, "text/javascript", or "module".
_SCRIPT_NON_JS_TYPE_RE = re.compile(
    r'\btype\s*=\s*["\'](?!(?:text/javascript|module)["\'])([^"\']*)["\']',
    re.IGNORECASE,
)


def _check_js_lint(html_path: Path, skip: bool = False) -> tuple[bool, list[str]]:
    """Extract inline JavaScript <script> blocks and run `node --check` on each.

    Skips:
      - <script src="..."> external references
      - <script type="application/json"> and other non-JS type values
      - <script /> self-closing tags (no body)

    Returns (all_ok, list_of_error_strings).
    If skip=True, returns (True, []) without running node at all.
    Exits with code 3 if `node` is not found on PATH (unless skip=True).
    """
    if skip:
        return True, []

    # Verify node is available
    node_bin = None
    for candidate in ["node", "nodejs"]:
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                node_bin = candidate
                break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    if node_bin is None:
        print(
            "ERROR: `node` not found on PATH — cannot run JS lint.\n"
            "  Install Node.js or pass --skip-js-lint to bypass (emergency only).",
            file=sys.stderr,
        )
        sys.exit(3)

    html = html_path.read_text(encoding="utf-8", errors="replace")
    errors = []
    block_num = 0

    for m in _SCRIPT_BLOCK_RE.finditer(html):
        open_tag = m.group(1)
        js_src = m.group(2)

        # Skip self-closing <script /> (no executable body)
        if open_tag.rstrip().endswith('/>'):
            continue

        # Skip external script refs (<script src="...">)
        if _SCRIPT_SRC_RE.search(open_tag):
            continue

        # Skip non-JS types (application/json, text/template, text/x-handlebars, etc.)
        if _SCRIPT_NON_JS_TYPE_RE.search(open_tag):
            continue

        # Skip empty bodies
        if not js_src.strip():
            continue

        block_num += 1
        html_line_start = html[:m.start()].count('\n') + 1

        with tempfile.NamedTemporaryFile(
            suffix=".js",
            prefix=f"annotate_lint_block{block_num}_",
            mode="w",
            encoding="utf-8",
            delete=False,
        ) as tf:
            tf.write(js_src)
            tf_path = tf.name

        try:
            result = subprocess.run(
                [node_bin, "--check", tf_path],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                err_raw = (result.stderr or result.stdout or "").strip()
                err_display = err_raw.replace(
                    tf_path,
                    f"{html_path} (inline script block #{block_num}, HTML line ~{html_line_start})",
                )
                errors.append(
                    f"  Block #{block_num} (HTML line ~{html_line_start}):\n"
                    + "\n".join("    " + ln for ln in err_display.splitlines())
                )
        except subprocess.TimeoutExpired:
            errors.append(f"  Block #{block_num}: node --check timed out")
        finally:
            try:
                os.unlink(tf_path)
            except OSError:
                pass

    return (len(errors) == 0), errors


# ────────────────────────────────────────────────────────────────────────────
# Slug-directory preflight
# ────────────────────────────────────────────────────────────────────────────
def _available_versions(slug_dir: Path) -> list[str]:
    versions_dir = slug_dir / "versions"
    if not versions_dir.is_dir():
        return []
    return sorted(p.stem for p in versions_dir.glob("*.html"))


def _read_meta(slug_dir: Path) -> dict:
    path = slug_dir / "current.meta.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_meta_locked(slug_dir: Path, mutate) -> None:
    """Re-read + mutate + write current.meta.json under the server's own lock.

    The sync server caches content stamps into this file while it runs, so a
    read-modify-write here would silently drop whatever it wrote in between.
    It takes `current.meta.json.lock`; so must we.
    """
    path = slug_dir / "current.meta.json"
    lock_path = path.with_suffix(".json.lock")
    with open(lock_path, "a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            meta = _read_meta(slug_dir)
            mutate(meta)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _ensure_current_symlink(slug_dir: Path) -> tuple[str | None, list[str]]:
    """Guarantee current.html resolves to a real versions/<v>.html.

    `ln -sf v1.html ../current.html` run from inside versions/ produces a link
    whose target resolves against the SLUG dir, not versions/ — it dangles, the
    page 404s, and the only symptom publish ever showed was
    "JS lint: skipped (no current.html found yet)". Repair it here rather than
    serve a broken page: the correct target is always `versions/<v>.html`.

    Returns (current_version, notes).
    """
    notes: list[str] = []
    versions = _available_versions(slug_dir)
    if not versions:
        return None, ["no versions/*.html — nothing to publish"]

    current = slug_dir / "current.html"
    is_link = current.is_symlink()
    resolves = current.exists()  # follows symlinks; False for a dangling link

    if resolves and not is_link:
        # A real file, not a link. Legal layout; leave it alone.
        return (_read_meta(slug_dir).get("current") or versions[-1]), notes

    if resolves and is_link:
        target = os.readlink(current)
        if target == f"versions/{Path(target).stem}.html":
            return Path(target).stem, notes
        notes.append(f"current.html pointed at {target!r}; rewrote it as "
                     f"versions/{Path(target).stem}.html")

    # Missing, dangling, or pointing somewhere odd. Pick the intended version.
    wanted = None
    reasons = []
    if is_link:
        stem = Path(os.readlink(current)).stem
        if stem in versions:
            wanted = stem
            reasons.append(f"recovered from the dangling link target {stem!r}")
    if wanted is None:
        meta_current = _read_meta(slug_dir).get("current")
        if meta_current in versions:
            wanted = meta_current
            reasons.append("taken from current.meta.json")
    if wanted is None and len(versions) == 1:
        wanted = versions[0]
        reasons.append("the only version present")
    if wanted is None:
        return None, [
            "current.html is missing or dangling and the intended version is "
            f"ambiguous — versions/ holds {', '.join(versions)}. Run "
            f"`{_inv()} publish-version {slug_dir} <vN>` to choose one."
        ]

    if current.exists() or current.is_symlink():
        current.unlink()
    current.symlink_to(Path("versions") / f"{wanted}.html")
    notes.append(f"current.html → versions/{wanted}.html ({'; '.join(reasons)})")
    return wanted, notes


def _ensure_meta_history(slug_dir: Path, version: str) -> list[str]:
    """Make sure current.meta.json names a current version AND has history.

    Without a history entry the version rail renders "No versions found" —
    a page that looks broken to the reviewer while every byte of content is
    served correctly. Publish registers the initial version itself rather than
    leaving that to a `publish-version` call nobody knew was required.
    """
    meta = _read_meta(slug_dir)
    history = meta.get("history") or []
    has_entry = any(h.get("version") == version for h in history if isinstance(h, dict))
    if meta.get("current") == version and has_entry:
        return []

    def _mutate(m: dict) -> None:
        m["current"] = version
        entries = m.setdefault("history", [])
        if not any(isinstance(h, dict) and h.get("version") == version for h in entries):
            entries.append({"version": version, "ts": _now_iso(), "label": "initial"})

    _write_meta_locked(slug_dir, _mutate)
    return [f"current.meta.json: registered {version} (current + history entry)"]


# ────────────────────────────────────────────────────────────────────────────
# Page ownership
# ────────────────────────────────────────────────────────────────────────────
def _owner_fields(session_id: str | None = None) -> dict:
    """The four keys that say which session a page belongs to.

    The hook reads the registry copy to decide whose comments these are; the
    shell reads the current.meta.json copy to draw the owner chip. Both are
    written, because a page can outlive the state file it was registered in.
    """
    sid = session_id or _session_id()
    from .delivery import capture_target
    target = capture_target(sid, _session_agent())
    return {
        "owner_session": sid,
        "owner_agent": _session_agent(),
        "owner_label": (target or {}).get("label") or _session_label(sid),
        "owner_claimed_at": _now_iso(),
        "owner_target": target,
    }


def _write_owner_meta(slug_dir: Path, fields: dict) -> str | None:
    """Stamp `owner` into current.meta.json under the server's own lock.

    Returns an error string rather than raising: losing the chip must not fail
    a publish that otherwise worked.
    """
    def _mutate(meta: dict) -> None:
        # Key names are L1's contract for the owner chip: owner_label is shown,
        # owner_session is the tooltip, claimed_at drives "claimed <ago>".
        meta["owner"] = {
            "owner_session": fields["owner_session"],
            "owner_agent": fields["owner_agent"],
            "owner_label": fields["owner_label"],
            "claimed_at": fields["owner_claimed_at"],
            "target": fields.get("owner_target"),
        }

    try:
        _write_meta_locked(slug_dir, _mutate)
    except OSError as e:
        return str(e)
    return None


def _stamp_owner_in_registry(project: str, slug: str, fields: dict) -> str | None:
    try:
        with _flock(_state_lock_path(project)):
            state = _load_state_for_project(project)
            if slug not in state.get("slugs", {}):
                return f"{project}/{slug} is not registered"
            state["slugs"][slug].update(fields)
            _save_state_for_project(project, state)
    except TimeoutError as e:
        return str(e)
    return None


# ────────────────────────────────────────────────────────────────────────────
# Publish verification gate
# ────────────────────────────────────────────────────────────────────────────
def _verify_published(record: dict, transport_details: dict, base_path: str,
                      timeout: float):
    """Walk origin → tailscale → public, stopping at the first broken hop.

    Continuing past a failure only buys another timeout and a second, noisier
    error for the same cause.
    """
    from .verify import VerifyReport, probe_browser, probe_http

    report = VerifyReport()
    base = base_path or ""
    hop_timeout = min(timeout, 30.0)

    report.stages.append(
        probe_http("origin", f"http://127.0.0.1:{record['port']}{base}/", timeout=hop_timeout)
    )
    if report.failed:
        return report

    details = transport_details or {}
    ts = details.get("tailscale") if isinstance(details.get("tailscale"), dict) else None
    if ts is None and details.get("transport") in {"tailscale", "funnel"}:
        ts = details
    if ts and ts.get("hostname") and ts.get("https_port"):
        report.stages.append(
            probe_http("tailscale",
                       f"https://{ts['hostname']}:{ts['https_port']}{base}/",
                       timeout=hop_timeout)
        )
        if report.failed:
            return report

    public = (page_url(record) if record.get("transport") == "funnel" else mounted_url(record.get("public_url"), base)) or (
        page_url(record) if record.get("transport") == "cloudflare" else None) or ""
    if public.startswith("https://"):
        report.stages.append(probe_browser("public", public, timeout=timeout))
    return report


def _had_public_route(record: dict) -> bool:
    """True when a page was published with a Cloudflare route.

    Pages published before Tailscale became the default carry the route but
    no `public_url`; their details name the tunnel's origin service instead.
    """
    details = record.get("transport_details") or {}
    return bool(record.get("public_url") or details.get("public_url")
                or details.get("origin_service"))


class _AlreadyRunning(Exception):
    """A live server for this slug was found while holding the state lock.

    Raised rather than returned so the slow verification below happens OUTSIDE
    the lock — the flock helper gives up after 30s and a browser stage can take
    longer than that, so holding it would fail an unrelated concurrent publish.
    """

    def __init__(self, record: dict):
        super().__init__("already running")
        self.record = record


def _run_gate(record: dict, args):
    """Verify `record` in place. Returns the report, or None when skipped."""
    if getattr(args, "no_verify", False):
        return None
    report = _verify_published(
        record,
        record.get("transport_details") or {},
        record.get("public_base_path") or "",
        timeout=getattr(args, "verify_timeout", 45.0),
    )
    record["verified"] = report.fully_verified
    record["verify_stages"] = [
        {"name": s.name, "status": s.status, "url": redact_review_key(s.url),
         "detail": redact_share_links(s.detail)}
        for s in report.stages
    ]
    return report


def _print_publish(project: str, slug: str, slug_dir: Path, record: dict,
                   report, skip_verify: bool, headline: str | None = None,
                   hook_msg: str | None = None, hook_added: bool = False,
                   shim_msg: str | None = None,
                   publish_ms: float | None = None) -> int:
    """Render the publish result. Returns the process exit code.

    Both the fresh-publish and already-running paths come through here so that
    neither can print a URL the gate has not cleared.
    """
    from .verify import format_report

    if record.get("transport_error"):
        print(f"ERROR: transport failed: {record['transport_error']}", file=sys.stderr)
        return 1

    print()
    print(f"  annotate publish — {project}/{slug}")
    print("  ─────────────────────────────────────────────")

    # The tailnet URL is the page's URL. A broken Cloudflare route only
    # affects outside reviewers, so it warns instead of withholding the URL.
    blocking = [st for st in (report.failed if report is not None else [])
                if st.name != "public" or record.get("transport") == "funnel"]
    if blocking:
        stage = blocking[0]
        _bus_emit(record.get("bus_file"), {
            "event": "page_publish_failed",
            "slug": slug,
            "stage": stage.name,
            "detail": stage.detail,
            "url": redact_review_key(stage.url),
            "owner_session": record.get("owner_session") or _session_id(),
        })
        print("  NOT PUBLISHED — the page does not render.")
        print()
        for line in format_report(report):
            print(line)
        print()
        print(f"  Local URL:     {mounted_url(record['local_url'], record.get('public_base_path'))}   (server is still running)")
        print(f"  PID:           {record['pid']}")
        print(f"  Port:          {record['port']}")
        print(f"  Transport:     {record.get('transport')}")
        if record.get("transport_error"):
            print(f"  Transport err: {record['transport_error']}")
        print(f"  Slug dir:      {slug_dir}")
        print("  ─────────────────────────────────────────────")
        print(f"  No URL is printed for {slug!r}: the {stage.name} stage failed.")
        print(f"  Fix that stage and re-run `{_inv()} publish {slug_dir}`, or")
        print(f"  `{_inv()} unpublish {slug}` to tear the whole thing down.")
        print()
        return 1

    if headline:
        print(f"  {headline}")
    for st in (report.failed if report is not None else []):
        print(f"  WARN           public URL failed ({st.detail[:120]}); the URL below works")
    if skip_verify:
        print("  UNVERIFIED     --no-verify was passed; nothing below has been checked")
    elif report is not None and report.unavailable:
        # A Cloudflare Access login page is not a broken page. It is this
        # session failing to prove anything about a page that is very probably
        # fine — five sessions burned 5-10 tool calls each re-checking a live
        # page that publish had called NOT PUBLISHED.
        access = [s for s in report.unavailable
                  if getattr(s, "reason", None) == "access_login"]
        passed = ", ".join(s.name for s in report.stages if s.status == "pass")
        if access:
            for s in access:
                print(f"  UNVERIFIED     {s.name}: not verified from this session "
                      f"(Access login)"
                      + (f"; {passed} stage(s) PASS" if passed else ""))
            print("                 The public URL below is live for an authenticated")
            print("                 reviewer; the tailnet URL is verified.")
        if len(access) < len(report.unavailable):
            print("  UNVERIFIED     could not reach the authenticated browser — the public")
            print("                 URL below is UNCONFIRMED, not known-good")

    # The one URL to hand over. Pid, port, bus and state paths used to follow
    # it; `status` has them, and no round needed them from here.
    print(f"  URL:           {page_url(record)}")
    if record.get("public_url") and record.get("transport") != "funnel":
        print(f"  Public URL:    {mounted_url(record['public_url'], record.get('public_base_path'))}   (outside reviewers only)")
    if record.get("transport_error"):
        print(f"  Transport err: {record['transport_error']}")
    if report is not None:
        print("  ─────────────────────────────────────────────")
        if record.get("transport") == "funnel":
            for stage in report.stages:
                print(f"  {stage.status.upper():<5} {stage.name:<10} {redact_share_links(stage.detail)}")
        else:
            for line in format_report(report):
                print(line)
    print("  ─────────────────────────────────────────────")
    if record.get("owner_label"):
        print(f"  Owner:         {record['owner_label']}")
    if hook_msg:
        print(f"  Hook install:  {hook_msg}")
        if hook_added:
            print(f"  (NEW: added UserPromptSubmit hook → {HOOK_COMMAND})")
    if shim_msg:
        print(f"  CLI shim:      {shim_msg}")
    print(f"  Invocation:    {_inv()} inbox {slug} --unread")
    print()

    _bus_emit(record.get("bus_file"), {
        "event": "page_published",
        "slug": slug,
        "owner_session": record.get("owner_session") or _session_id(),
        "owner_agent": record.get("owner_agent") or _session_agent(),
        "version": _read_meta(slug_dir).get("current"),
        "url": redact_review_key(page_url(record)),
        "transport": record.get("transport"),
        "verified": bool(record.get("verified")),
        "verify_stages": [
            {"name": s["name"], "status": s["status"]}
            for s in (record.get("verify_stages") or [])
        ],
        "transport_error": record.get("transport_error"),
        "publish_ms": int(publish_ms) if publish_ms is not None else None,
    })
    return 0


def _publish_already_running(project: str, slug: str, slug_dir: Path,
                             record: dict, args) -> int:
    """Re-verify a slug that is already serving, then report it.

    A live process is not proof the page renders. This path used to print the
    recorded URL and exit 0, so re-running publish on a page that had just
    failed the gate reported it as fine one command later.
    """
    wanted = getattr(args, "transport", None) or _project_config(project).get("transport")
    if wanted == "funnel" and record.get("transport") != "funnel":
        previous = dict(record)
        mount = f"/annotate/{project}/{slug}"
        needs_mount = mount != record.get("public_base_path")
        remounted = False
        from .review_access import ensure_key
        from .transports import load
        ensure_key(slug_dir)
        try:
            from . import __version__
            code, capabilities = _api(record, "GET", "/api/capabilities", None, "publish")
            if needs_mount or code != 200 or capabilities.get("version") != __version__:
                from .deployment import restart_record
                restart_record(project, slug, Path(sys.executable), **({"mount": mount} if needs_mount else {}))
                remounted = needs_mount
                record = _load_state_for_project(project)["slugs"][slug]
            with _flock(_tunnel_lock_path()):
                result = load("funnel").publish(mount.lstrip("/"), int(record["port"]),
                                                **_transport_opts(_project_config(project)))
            with _flock(_state_lock_path(project)):
                state = _load_state_for_project(project)
                current = state["slugs"].get(slug)
                if not current or current.get("pid") != record.get("pid"):
                    raise RuntimeError("page changed during transport migration")
                current.setdefault("legacy_routes", []).append({k: previous.get(k) for k in ("transport", "transport_details", "url", "public_url", "port", "public_base_path")})
                current.update(transport="funnel", url=result["url"], public_url=result["url"],
                               transport_details=result["details"], transport_error=None)
                _save_state_for_project(project, state)
                record = current
        except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
            if remounted:
                try:
                    restart_record(project, slug, Path(sys.executable), mount=previous.get("public_base_path") or "")
                except Exception as rollback:
                    print(f"ERROR: previous mount could not be restored: {rollback}", file=sys.stderr)
            print(f"ERROR: Funnel migration failed: {exc}", file=sys.stderr)
            return 1
    if record.get("owner_session") == _session_id():
        from .delivery import capture_target
        target = capture_target(_session_id(), _session_agent())
        if target and target != record.get("owner_target"):
            fields = {key: record.get(key) for key in ("owner_session", "owner_agent", "owner_label", "owner_claimed_at")}
            fields["owner_target"] = target
            error = _stamp_owner_in_registry(project, slug, fields)
            if not error:
                record.update(fields)
                _write_owner_meta(slug_dir, fields)
    report = _run_gate(record, args)
    if report is not None:
        try:
            with _flock(_state_lock_path(project)):
                state = _load_state_for_project(project)
                if slug in state.get("slugs", {}):
                    # Re-read and merge only our own keys: a peer may have
                    # rewritten this record while the gate was running.
                    state["slugs"][slug]["verified"] = record["verified"]
                    state["slugs"][slug]["verify_stages"] = record["verify_stages"]
                    _save_state_for_project(project, state)
        except TimeoutError as e:
            print(f"WARN: verification result not recorded: {e}", file=sys.stderr)
    return _print_publish(
        project, slug, slug_dir, record, report, getattr(args, "no_verify", False),
        headline=f"Already running (pid {record['pid']}); re-verified in place. "
                 f"`{_inv()} unpublish {slug}` to re-publish from scratch.",
    )


# ────────────────────────────────────────────────────────────────────────────
# Commands
# ────────────────────────────────────────────────────────────────────────────
def cmd_publish(args) -> int:
    from .workspace import exception_reason, project_key
    try:
        exception_reason(args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    key = project_key(Path(args.slug_dir)) or project_key(Path.cwd()) or getattr(args, "project", None)
    if key:
        lock = LOCK_DIR / ("workspace-" + hashlib.sha256(key.encode()).hexdigest()[:20] + ".lock")
        try:
            with _flock(lock):
                return _publish(args)
        except TimeoutError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 4
    return _publish(args)


def _publish(args) -> int:
    started_at = time.monotonic()
    slug_dir = Path(args.slug_dir).resolve()
    if not slug_dir.exists() or not slug_dir.is_dir():
        print(f"ERROR: slug-dir not found or not a directory: {slug_dir}", file=sys.stderr)
        return 2
    project, slug = _slug_project(slug_dir, args.project)
    cfg = _project_config(project)
    from .workspace import candidates, duplicate_message, duplicate_page, exception_reason, project_key
    saved_exception = (_load_state_for_project(project)["slugs"].get(slug) or {}).get("exception")
    flagged = exception_reason(args)
    duplicate = duplicate_page(slug_dir, getattr(args, "project", None))
    if flagged:
        # The project's own main page is never its own exception: the flag
        # would demote it and leave the project with no main page.
        found = candidates(slug_dir, getattr(args, "project", None), caller=Path.cwd())
        own = [r for _, _, r in found if Path(r["slug_dir"]).resolve() == slug_dir]
        if own and (own[0].get("workspace_primary") or len(found) == 1):
            print(f"ERROR: {project}/{slug} is this project's main page; --exception and --standalone are only "
                  f"for a second page.\n  To make another page the main page: "
                  f"{_inv()} workspace --select PROJECT/SLUG", file=sys.stderr)
            return 2
    # A saved reason applies only while another page is the main page; with
    # none left, this page is the main page again.
    reason = flagged or ((saved_exception or {}).get("reason") if duplicate else None)
    if duplicate and not reason:
        print(duplicate_message(duplicate), file=sys.stderr)
        return 2
    parent_slug = next((f"{p}/{s}" for p, s, r in _registry_entries()
                        if duplicate and Path(r["slug_dir"]).resolve() == Path(duplicate["slug_dir"]).resolve()), None)
    exception = ({"reason": reason,
                  "parent_slug": parent_slug or (saved_exception or {}).get("parent_slug")}
                 if reason else None)
    if (args.transport or cfg.get("transport")) == "funnel":
        from .review_access import ensure_key
        ensure_key(slug_dir)

    # ── Slug-dir preflight: a resolvable current.html + registered history ──
    current_version, notes = _ensure_current_symlink(slug_dir)
    if current_version is None:
        print(f"ERROR: {slug_dir} is not publishable:", file=sys.stderr)
        for n in notes:
            print(f"  {n}", file=sys.stderr)
        return 2
    notes += _ensure_meta_history(slug_dir, current_version)
    for n in notes:
        print(f"  Repaired:      {n}")

    # Install the shim before anything can print an `annotate …` line.
    shim_changed, shim_msg = _ensure_shim_installed()
    if shim_changed:
        globals()["_INV_CACHE"] = None

    # ── Task 4: Build-time JS lint ──────────────────────────────────
    skip_lint = getattr(args, "skip_js_lint", False)
    current_html = slug_dir / "current.html"
    if current_html.exists():
        # Resolve symlink so we lint the actual file content
        try:
            lint_target = current_html.resolve()
        except OSError:
            lint_target = current_html
        print(f"  JS lint:       checking {lint_target.name} …", end=" ", flush=True)
        lint_ok, lint_errors = _check_js_lint(lint_target, skip=skip_lint)
        if lint_ok:
            if skip_lint:
                print("SKIPPED (--skip-js-lint)")
            else:
                print("OK")
        else:
            print("FAILED")
            print(f"\nERROR: inline JS syntax errors in {lint_target}", file=sys.stderr)
            for e in lint_errors:
                print(e, file=sys.stderr)
            print(
                f"\nFix the JS errors above and re-run `{_inv()} publish`.\n"
                "  Use --skip-js-lint ONLY for emergency deploys (not recommended).",
                file=sys.stderr,
            )
            return 1
    else:
        print("  JS lint:       skipped (no current.html found yet)")

    # Cheap unlocked liveness read first: the gate below can take tens of
    # seconds and must not run while holding the project state lock.
    pre_existing = _load_state_for_project(project)["slugs"].get(slug)
    if pre_existing and _is_process_alive(pre_existing.get("pid", 0)):
        if _route_host(pre_existing):
            with _flock(_state_lock_path(project)):
                state = _load_state_for_project(project)
                rec = state["slugs"].get(slug) or pre_existing
                moved = _rerouted_if_renamed(project, slug, rec, _live_tailnet_host(), False)
                if moved and moved[0] == "rerouted":
                    _save_state_for_project(project, state)
                    print(f"  Rerouted:      {moved[1]}")
                pre_existing = rec
        return _publish_already_running(project, slug, slug_dir, pre_existing, args)

    try:
        with _flock(_state_lock_path(project)):
            state = _load_state_for_project(project)
            existing = state["slugs"].get(slug)
            if existing and _is_process_alive(existing.get("pid", 0)):
                # A peer published this slug between the read above and this
                # lock. Verify it too — never return an unchecked URL.
                raise _AlreadyRunning(existing)

            # Pick port (use config base; auto-bump; allow override)
            if args.port:
                port = args.port
            else:
                port_base = existing.get("port") if existing else cfg.get("port_base", 8800)
                registered_pid = existing.get("pid") if existing else None
                # A dead page still owns its port: `revive` brings it back
                # there, and its routes point at it.
                reserved = {int(r["port"]) for p, s, r in _registry_entries()
                            if (p, s) != (project, slug) and r.get("port")}
                port = _find_free_port_after(int(port_base), registered_pid=registered_pid)
                while port in reserved:
                    nxt = _find_free_port_after(port + 1, registered_pid=registered_pid)
                    if nxt <= port:
                        break
                    port = nxt

            bus_dir = BUS_ROOT / project
            bus_dir.mkdir(parents=True, exist_ok=True)

            # Transport: publish (insert public route)
            transport_name = args.transport or cfg.get("transport", "local")
            hostname = args.hostname or cfg.get("hostname")
            path_prefix = args.path_prefix or cfg.get("path_prefix") or (f"/annotate/{project}/{slug}" if transport_name == "funnel" else f"/{slug}")
            if path_prefix and not path_prefix.startswith("/"):
                path_prefix = "/" + path_prefix
            path_prefix = path_prefix.rstrip("/")

            transport_url = None
            transport_details: dict = {}
            transport_error: str | None = None
            if transport_name != "local":
                try:
                    from .transports import load as _load_transport
                    tmod = _load_transport(transport_name)
                    opts = _transport_opts(cfg)
                    if hostname:
                        opts["hostname"] = hostname
                    if transport_name == "cloudflare_tailscale":
                        # A page that already had a public route keeps it.
                        opts["public"] = bool(getattr(args, "public", False) or cfg.get("public")) or bool(
                            existing and _had_public_route(existing))
                    if existing:
                        # What this slug was routed through last time. A
                        # transport whose route key can move between publishes
                        # (a `tailscale serve` mapping is keyed on the local
                        # port) needs this to reclaim the entry it is about to
                        # orphan. Transports that replace in place ignore it.
                        opts["previous"] = {
                            "port": existing.get("port"),
                            "details": existing.get("transport_details") or {},
                        }
                    slug_for_route = path_prefix.lstrip("/")
                    with _flock(_tunnel_lock_path()):
                        result = tmod.publish(slug_for_route, port, **opts)
                    transport_url = result.get("url")
                    transport_details = result.get("details", {})
                except NotImplementedError as e:
                    transport_error = str(e)
                    print(f"WARN: transport {transport_name!r}: {e}", file=sys.stderr)
                except Exception as e:
                    transport_error = str(e)
                    print(f"ERROR: transport {transport_name!r} publish failed: {e}", file=sys.stderr)

            # Start server (with public_base_path if transport set a sub-path mount)
            pbp = path_prefix if transport_name != "local" and transport_url else ""
            pid = _start_server(slug_dir, port, bus_dir, pbp)

            # Record state
            from .updates import runtime_manifest
            record = {
                "slug": slug,
                "slug_dir": str(slug_dir),
                "project": project,
                "pid": pid,
                "port": port,
                "transport": transport_name,
                "public_base_path": pbp or None,
                "url": mounted_url(transport_url or f"http://localhost:{port}/", pbp),
                "public_url": mounted_url(transport_details.get("public_url"), pbp),
                "local_url": f"http://localhost:{port}/",
                "bus_file": str(bus_dir / f"{slug}.ndjson"),
                "started_at": _now_iso(),
                "transport_details": transport_details,
                "transport_error": transport_error,
                "workspace_key": project_key(slug_dir) or project_key(Path.cwd()),
                "workspace_primary": not bool(reason),
                "standalone": bool(reason),
                **({"exception": exception} if exception else {}),
                **_owner_fields(),
                "runtime_python": sys.executable,
                "runtime_manifest": runtime_manifest(),
            }
            state["slugs"][slug] = record
            _save_state_for_project(project, state)
    except _AlreadyRunning as e:
        return _publish_already_running(project, slug, slug_dir, e.record, args)
    except TimeoutError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 4

    # Hook install (idempotent)
    hook_added, hook_msg = _ensure_hook_installed()
    owner_err = _write_owner_meta(slug_dir, record)
    if owner_err:
        print(f"WARN: owner not written to current.meta.json: {owner_err}", file=sys.stderr)

    # ── Verification gate ────────────────────────────────────────────
    # No URL is printed until the page has been proven to render. Being told
    # "it's fixed" over a broken page is the failure this gate exists to stop.
    skip_verify = getattr(args, "no_verify", False)
    report = _run_gate(record, args)
    if report is not None:
        try:
            with _flock(_state_lock_path(project)):
                st = _load_state_for_project(project)
                if slug in st.get("slugs", {}):
                    st["slugs"][slug]["verified"] = record["verified"]
                    st["slugs"][slug]["verify_stages"] = record["verify_stages"]
                    _save_state_for_project(project, st)
        except TimeoutError as e:
            print(f"WARN: verification result not recorded: {e}", file=sys.stderr)

    return _print_publish(project, slug, slug_dir, record, report, skip_verify,
                          hook_msg=hook_msg, hook_added=hook_added,
                          shim_msg=shim_msg,
                          publish_ms=(time.monotonic() - started_at) * 1000.0)


def cmd_unpublish(args) -> int:
    resolved = _resolve_scoped_slug(args.slug, getattr(args, "project", None))
    if not resolved:
        return 2
    project, slug, selected = resolved
    try:
        with _flock(_state_lock_path(project)):
            state = _load_state_for_project(project)
            record = state.get("slugs", {}).get(slug)
            if record != selected:
                raise RuntimeError("page registration changed during selection; no teardown attempted")
            directory = Path(record["slug_dir"]).resolve()
            for other_project, other_slug, other in _registry_entries():
                if (other_project, other_slug) == (project, slug):
                    continue
                if (str(other.get("port")) == str(record.get("port"))
                        or (other.get("slug_dir") and Path(other["slug_dir"]).resolve() == directory)):
                    raise RuntimeError("page directory or port is also registered to another scope; no teardown attempted")
            from .deployment import _identity
            owned = {**record, "project": project}
            before = _identity(owned)
            from .legacy_routes import cleanup
            with _flock(_tunnel_lock_path()):
                cleanup(record, _project_config(project))

            # Remove only this recorded route. A root mount is still a route;
            # the transport's origin/port ownership guard decides whether it
            # belongs to this page. Failed removal leaves the receipt intact.
            transport_name = record.get("transport", "local")
            if transport_name != "local":
                from .transports import load as _load_transport
                tmod = _load_transport(transport_name)
                details = record.get("transport_details") or {}
                opts = _transport_opts(_project_config(project))
                if details.get("hostname"):
                    opts["hostname"] = details["hostname"]
                opts["port"] = record["port"]
                https_port = details.get("https_port") or (details.get("tailscale") or {}).get("https_port")
                if https_port:
                    opts["https_port"] = https_port
                with _flock(_tunnel_lock_path()):
                    result = tmod.unpublish((record.get("public_base_path") or "").lstrip("/"), **opts)
                if not isinstance(result, dict) or result.get("ok") is not True:
                    raise RuntimeError(f"transport {transport_name} teardown failed or was refused")
                transport_details = result.get("details") or {}
                outcomes = [transport_details.get(name) for name in ("tailscale", "cloudflare")
                            if isinstance(transport_details.get(name), dict)] or [transport_details]
                for outcome in outcomes:
                    reason = outcome.get("reason")
                    if (outcome.get("action") == "noop"
                            and not (isinstance(reason, str) and
                                     (reason.startswith("no serve mapping") or reason == "no matching rule"))):
                        raise RuntimeError(f"transport {transport_name} ownership not proven; inspect its recorded route")
                print(f"  Transport {transport_name}: {transport_details.get('action', 'ok')}")

            fresh = _identity(owned)
            if fresh != before:
                raise RuntimeError("server identity changed during teardown; no signal sent")
            pid = before["pid"]
            if pid is not None:
                # Avoid _stop_server's unguarded SIGKILL escalation: a reused
                # PID during its wait must never authorize another signal.
                os.kill(pid, signal.SIGTERM)
                for _ in range(20):
                    if not _is_process_alive(pid):
                        break
                    time.sleep(0.1)
                if _is_process_alive(pid):
                    raise RuntimeError("server stop unproven after SIGTERM; inspect it before retrying; no hard kill sent")
            if _identity({**owned, "pid": pid})["pid"] is not None:
                raise RuntimeError("a page server appeared during teardown; registration retained")
            print(f"  Server pid={pid if pid is not None else record.get('pid', 0)} {'stopped' if pid is not None else 'already stopped'}")
            state["slugs"].pop(slug, None)
            _save_state_for_project(project, state)
    except TimeoutError as e:
        print(f"ERROR: {e}; registration retained for retry", file=sys.stderr)
        return 4
    except Exception as e:
        print(f"ERROR: unpublish {project}/{slug}: {e}; registration retained for retry", file=sys.stderr)
        return 1
    print(f"  Removed from state file: {STATE_DIR / (project + '.json')}")
    return 0


def _running_servers() -> dict:
    """Map resolved slug_dir -> [{pid, port}] for every live page server.

    The recorded pid is not authoritative: a server restarted outside the CLI
    (a supervisor, a manual relaunch, a peer session) keeps the ORIGINAL pid in
    the state file forever, so a live page reads as dead everywhere slugs are
    enumerated. slug_dir is the stable identity — pid and port both move.
    """
    try:
        out = subprocess.run(
            ["ps", "-ww", "-eo", "pid=,args="], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        return {}
    found: dict[str, list[dict]] = {}
    for line in out.splitlines():
        if "sync_server" not in line or "--slug-dir" not in line:
            continue
        pid_str, _, rest = line.strip().partition(" ")
        try:
            argv = shlex.split(rest)
            pid = int(pid_str)
        except ValueError:
            continue

        def _arg(flag, argv=argv):
            return argv[argv.index(flag) + 1] if flag in argv else None

        slug_dir = _arg("--slug-dir")
        if not slug_dir:
            continue
        try:
            key = str(Path(slug_dir).resolve())
        except OSError:
            continue
        port = _arg("--port")
        found.setdefault(key, []).append({"pid": pid, "port": int(port) if port else None})
    return found


def _ps_command_snapshot() -> str:
    """One `ps` read, reused for every owner check in a `status` run.

    Cheap and deliberately loose: an agent session id appears in its own
    process's command line, so finding the id anywhere in the table is enough
    to say the owner is still around. An empty snapshot (ps refused, or a
    sandbox without process visibility) means "cannot tell" — never "gone".
    """
    try:
        return subprocess.run(["ps", "-ww", "-eo", "command="],
                              capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return ""


OWNER_COL = 38


def _owner_note(record: dict, ps_snapshot: str, width: int = OWNER_COL) -> str:
    """"<label> claimed 3h", plus "(gone)" when nothing is running for it.

    "(gone)" is the successor's cue: the page is serving, the hook is
    notifying a session that no longer exists, and someone has to run
    `annotate claim` before a verdict reaches anybody. The LABEL absorbs the
    truncation, never the marker — a column narrow enough to hide the alarm
    would be worse than no column.
    """
    session = record.get("owner_session")
    label = str(record.get("owner_label") or session or "")
    if not label:
        return "unclaimed"
    age = _age_seconds(record.get("owner_claimed_at"))
    suffix = f" claimed {_fmt_age(age)}" if age is not None else ""
    absent = bool(session and session != "unknown" and ps_snapshot and session not in ps_snapshot)
    target = record.get("owner_target")
    if isinstance(target, dict) and target.get("pid") and target.get("process_start"):
        from .delivery import _process
        try:
            process = _process(int(target["pid"]))
            if process:
                absent = (process[0] != target["process_start"]
                          or not re.search(rf"(?:^|/){re.escape(target.get('agent', ''))}(?:$|[.-])", process[1]))
            elif ps_snapshot:
                absent = True
        except (OSError, ValueError, subprocess.SubprocessError):
            absent = False
    if absent:
        suffix += " (gone)"
    return label[:max(1, width - len(suffix))] + suffix


def cmd_status(args) -> int:
    if getattr(args, "retired", False):
        retired = _retired_entries()
        if not retired:
            print("(no retired entries)")
            return 0
        print(f"  {'PROJECT':<15} {'SLUG':<24} {'RETIRED':<21} URL")
        print(f"  {'-' * 15} {'-' * 24} {'-' * 21} {'-' * 40}")
        for project, slug, record in retired:
            print(f"  {project[:15]:<15} {slug[:24]:<24} "
                  f"{str(record.get('retired_at'))[:21]:<21} {page_url(record)}")
        return 0
    rows = []
    live = _running_servers()
    ps_snapshot = _ps_command_snapshot()
    for sf in _all_state_files():
        st = json.loads(sf.read_text(encoding="utf-8"))
        project = st.get("project")
        for slug, rec in st.get("slugs", {}).items():
            if args.slug and slug != args.slug:
                continue
            pid = rec.get("pid", 0)
            port = rec.get("port")
            if _is_process_alive(pid):
                state = "alive"
            else:
                # Recorded pid is gone. Before calling it dead, look for the
                # process by slug_dir — reporting a serving page as dead is
                # the more damaging error, and it sends people chasing an
                # ingress problem that does not exist.
                slug_dir = rec.get("slug_dir")
                procs = live.get(str(Path(slug_dir).resolve())) if slug_dir else None
                if procs and len(procs) == 1:
                    pid = procs[0]["pid"]
                    port = procs[0]["port"] or port
                    state = "alive*"
                elif procs:
                    state = "dup"
                else:
                    state = "dead"
            # An owner only matters while the page is serving: a dead row's
            # owner is a fact about history, not about who should act.
            owner = _owner_note(rec, ps_snapshot) if state != "dead" else ""
            rows.append((project, slug, pid, port, page_url(rec), state, owner))
    if not rows:
        print("(no active slugs)")
        _print_retired_count()
        return 0
    print(f"  {'PROJECT':<12} {'SLUG':<22} {'PID':<8} {'PORT':<6} {'STATE':<7} "
          f"{'OWNER':<{OWNER_COL}} URL")
    print(f"  {'-'*12} {'-'*22} {'-'*8} {'-'*6} {'-'*7} {'-'*OWNER_COL} {'-'*40}")
    for project, slug, pid, port, url, state, owner in rows:
        print(f"  {project[:12]:<12} {slug[:22]:<22} {pid!s:<8} {port!s:<6} {state:<7} "
              f"{owner:<{OWNER_COL}} {url}")
    if any("(gone)" in r[6] for r in rows):
        print("\n  (gone) = the page is serving but the session that claimed it is no "
              f"longer running. Take it over with `{_inv()} claim <slug>`.")
    if any(r[5] == "alive*" for r in rows):
        print("\n  alive* = serving, but the state file's pid is stale (restarted "
              "outside the CLI). Re-publish to refresh the registry.")
    if any(r[5] == "dup" for r in rows):
        print("\n  dup    = several live servers share this slug_dir. They will fight "
              "over comments.json; stop the ones you did not intend.")
    _print_retired_count()
    return 0


def _print_retired_count() -> None:
    """The last line of `status`, so retired rows are discoverable.

    Silent when there are none: a line saying zero on every run is the kind of
    noise that gets a command stopped being read.
    """
    n = len(_retired_entries())
    if n:
        print(f"\n  {n} retired entries (`{_inv()} status --retired` to list)")


def cmd_migrate(args) -> int:
    """One-shot legacy-HTML → v2 directory layout.

    Steps:
      1. Resolve <legacy.html> path.
      2. Create <slug>/ in the same parent directory.
      3. Move HTML to versions/v1.html; symlink current.html → versions/v1.html.
      4. Write current.meta.json.
      5. Migrate any sibling *.comments.json into <slug>/comments.json (v2).
    """
    legacy_path = Path(args.legacy_html).resolve()
    if not legacy_path.exists() or not legacy_path.is_file():
        print(f"ERROR: legacy HTML not found: {legacy_path}", file=sys.stderr)
        return 2

    slug = args.slug or legacy_path.stem
    parent = legacy_path.parent
    slug_dir = parent / slug
    versions_dir = slug_dir / "versions"
    archive_dir = slug_dir / "archive"
    slug_dir.mkdir(exist_ok=True)
    versions_dir.mkdir(exist_ok=True)
    archive_dir.mkdir(exist_ok=True)

    initial_version = args.version or "v1"
    target_html = versions_dir / f"{initial_version}.html"

    if args.copy:
        target_html.write_bytes(legacy_path.read_bytes())
        action = "copied"
    else:
        os.replace(legacy_path, target_html)
        action = "moved"

    current_symlink = slug_dir / "current.html"
    if current_symlink.exists() or current_symlink.is_symlink():
        current_symlink.unlink()
    current_symlink.symlink_to(Path("versions") / f"{initial_version}.html")

    meta = {
        "current": initial_version,
        "history": [
            {"version": initial_version, "ts": _now_iso(), "label": args.label or "initial"}
        ],
    }
    (slug_dir / "current.meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Migrate comments
    legacy_stem = legacy_path.stem
    legacy_comments_candidates = [
        parent / f"{legacy_stem}.comments.json",
        parent / "comments.json",
    ]
    src_comments = None
    for cand in legacy_comments_candidates:
        if cand.exists():
            src_comments = cand
            break

    if src_comments:
        try:
            raw = json.loads(src_comments.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"WARN: could not parse {src_comments}: {e}", file=sys.stderr)
            raw = []

        # Reuse _coerce_v2 from sync_server
        from .sync_server import _coerce_v2
        store = _coerce_v2(raw)
        # Stamp version on every comment
        for items in store["anchors"].values():
            for c in items:
                c.setdefault("version", initial_version)
        (slug_dir / "comments.json").write_text(
            json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        # Back up original comments
        if args.copy:
            backup = slug_dir / f"comments.{legacy_stem}.v1.bak.json"
            backup.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            os.replace(src_comments, slug_dir / f"comments.{legacy_stem}.v1.bak.json")
    else:
        (slug_dir / "comments.json").write_text(
            json.dumps({"schema_version": 2, "anchors": {}, "archived": {}}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    print(f"  Migrated {legacy_path} → {slug_dir}/")
    print(f"    HTML:          {action} → versions/{initial_version}.html")
    print(f"    current.html:  symlink → versions/{initial_version}.html")
    print("    meta:          current.meta.json")
    print(f"    comments:      comments.json (from {src_comments or 'fresh'})")
    print()
    print(f"  Next: {_inv()} publish {slug_dir}")
    return 0


def _carryover_blockers(slug_dir: Path, new_version: str) -> list[dict]:
    """Return prior-round comments that lack a complete disposition.

    Open/addressed comments must either be resolved (which changes their
    status) or carried (which moves their version). A malformed resolution is
    also a blocker: a status label without a real version/anchor pointer is
    still limbo.
    """
    comments_path = slug_dir / "comments.json"
    if not comments_path.exists():
        return []
    try:
        raw = json.loads(comments_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [{
            "id": "comments.json",
            "version": "?",
            "anchor_id": "?",
            "status": "invalid_store",
            "reason": str(exc),
        }]

    from .sync_server import _coerce_v2, _version_has_anchor

    store = _coerce_v2(raw)
    meta = _read_meta(slug_dir)
    history = [
        item.get("version")
        for item in (meta.get("history") or [])
        if isinstance(item, dict) and item.get("version")
    ]
    if new_version in history:
        prior_versions = set(history[:history.index(new_version)])
    else:
        # A version being published for the first time follows every version
        # already in the history. Taking prior versions only from the
        # comments misses a version whose cards were all carried forward
        # (it has no comments left), and then rejects a resolution into it.
        prior_versions = set(history) | {
            c.get("version")
            for _anchor_id, c in _iter_comments(store)
            if c.get("version") and c.get("version") != new_version
        }
    allowed_resolution_versions = prior_versions | {new_version}

    blockers = []
    for anchor_id, comment in _iter_comments(store):
        version = comment.get("version")
        is_prior = not version or version in prior_versions
        if not is_prior:
            continue
        status = comment.get("status") or "open"
        reason = None
        if status in ("open", "addressed_by_agent"):
            reason = "no resolution or carry-forward"
        elif status == "resolved_in_version":
            resolved_version = comment.get("resolved_in_version")
            resolved_anchor = comment.get("resolution_anchor_id")
            if not resolved_version or not resolved_anchor:
                reason = "resolution pointer incomplete"
            elif resolved_version not in allowed_resolution_versions:
                reason = "resolution points past the version being published"
            elif not _version_has_anchor(slug_dir, resolved_version, resolved_anchor):
                reason = "resolution target anchor missing"
        if reason:
            blockers.append({
                "id": comment.get("id") or "?",
                "version": version or "?",
                "anchor_id": comment.get("anchor_id") or anchor_id,
                "status": status,
                "reason": reason,
            })
    return blockers


def _mentions_by_anchor(html: str) -> dict[int, str]:
    """{item number: the innermost anchor whose own text first says #N}.

    Deepest anchor wins so a mention inside a list item resolves to that item,
    not to the whole section around it.
    """
    from html.parser import HTMLParser

    found: dict[int, str] = {}

    class _Walk(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack: list[tuple[str, str | None]] = []

        def handle_starttag(self, tag, attrs):
            if tag in ("br", "img", "hr", "input", "meta", "link", "col", "wbr"):
                return
            self.stack.append((tag, dict(attrs).get("data-anchor-id")))

        def handle_endtag(self, tag):
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    del self.stack[i:]
                    return

        def handle_data(self, data):
            if any(t in ("script", "style") for t, _ in self.stack):
                return
            anchor = next((a for _, a in reversed(self.stack) if a), None)
            if not anchor:
                return
            for m in re.finditer(r"(?<![\w#&])#(\d{1,4})\b", data):
                found.setdefault(int(m.group(1)), anchor)

    _Walk().feed(html)
    return found


def _auto_dispose(slug_dir: Path, new_version: str, project_hint: str | None) -> list[str]:
    """Record where each earlier item went, from the new version itself.

    Resolving and carrying by hand cost a call per item per round, and had to
    happen in a narrow window: after the version was generated, before it was
    published. Agents in the bench resolved too early and hit the publish gate.
    The version already says where each item went: a card with the same
    number keeps it open (carry), and the first element that names it as #N
    answers it (resolve). Items it does not mention stay blockers.
    """
    blockers = [b for b in _carryover_blockers(slug_dir, new_version)
                if b["reason"] == "no resolution or carry-forward"]
    if not blockers:
        return []
    try:
        html = (slug_dir / "versions" / f"{new_version}.html").read_text(encoding="utf-8")
        store = _coerce_store_file(slug_dir)
    except OSError:
        return []
    numbers = {c.get("id"): c.get("number") for _a, c in _iter_comments(store)}
    cards = {}
    try:
        for card in json.loads((slug_dir / "cards.json").read_text(encoding="utf-8")):
            if isinstance(card, dict) and card.get("number") and card.get("anchor_id"):
                cards[int(card["number"])] = card["anchor_id"]
    except (OSError, ValueError, TypeError):
        pass
    mentions = _mentions_by_anchor(html)
    resolved = _resolve_scoped_slug(slug_dir.name, project_hint)
    if not resolved:
        return []
    record = resolved[2]
    done = []
    for b in blockers:
        number = numbers.get(b["id"])
        if not number:
            continue
        number = int(number)
        if number in cards and f'data-anchor-id="{cards[number]}"' in html:
            body = {"carry_forward": {"version": new_version, "anchor_id": cards[number]}}
            verb = "carried"
        elif number in mentions:
            body = {"status": "resolved_in_version", "resolved_in_version": new_version,
                    "resolution_anchor_id": mentions[number],
                    "response_text": f"Answered in {new_version}."}
            verb = "resolved"
        else:
            continue
        code, _payload = _api(record, "PUT", f"/api/comments/{b['id']}", body,
                              _resolve_author(None))
        if 200 <= code < 300:
            done.append(f"{verb} #{number}")
    return done


def _coerce_store_file(slug_dir: Path) -> dict:
    from .sync_server import _coerce_v2
    return _coerce_v2(json.loads((slug_dir / "comments.json").read_text(encoding="utf-8")))


def cmd_publish_version(args) -> int:
    slug_dir = Path(args.slug_dir).resolve()
    if not slug_dir.exists() or not slug_dir.is_dir():
        print(f"ERROR: slug-dir not found: {slug_dir}", file=sys.stderr)
        return 2
    new_version = args.version
    versions_dir = slug_dir / "versions"
    target = versions_dir / f"{new_version}.html"
    if not target.exists():
        print(f"ERROR: versions/{new_version}.html not found — drop it in first", file=sys.stderr)
        return 2
    auto = _auto_dispose(slug_dir, new_version, getattr(args, "project", None))
    if auto:
        print(f"  earlier items: {', '.join(auto)}")
    blockers = _carryover_blockers(slug_dir, new_version)
    if blockers:
        print(
            f"ERROR: cannot publish {new_version}: {len(blockers)} prior-round comment(s) "
            f"lack an explicit disposition. Name each as #N where {new_version} answers "
            "it, or give it a card with the same number to keep it open.",
            file=sys.stderr,
        )
        for blocker in blockers:
            print(
                f"  {blocker['id']}  {blocker['version']}  {blocker['status']}  "
                f"{blocker['anchor_id']}  ({blocker['reason']})",
                file=sys.stderr,
            )
        print(
            f"  Resolve: {_inv()} resolve {slug_dir.name} <id> --in-version {new_version} "
            "--anchor <vN-anchor> --response \"where it was applied\"",
            file=sys.stderr,
        )
        print(
            f"  Carry:   {_inv()} carry {slug_dir.name} <id> --to-version {new_version} "
            "--anchor <vN-anchor>",
            file=sys.stderr,
        )
        return 2
    current_symlink = slug_dir / "current.html"
    if current_symlink.exists() or current_symlink.is_symlink():
        current_symlink.unlink()
    current_symlink.symlink_to(Path("versions") / f"{new_version}.html")

    # History is a set keyed on version, not a log of calls. Appending
    # unconditionally is what listed every version of every observed page
    # twice: `publish` registers the version through _ensure_meta_history and
    # a later `publish-version` for the same vN appended a second entry, as did
    # any re-run of this command. The raw read-modify-write also dropped
    # whatever the running server had cached into the file in between, so this
    # now goes through the same lock the server takes.
    added = []

    def _mutate(meta: dict) -> None:
        meta["current"] = new_version
        history = meta.setdefault("history", [])
        for h in history:
            if isinstance(h, dict) and h.get("version") == new_version:
                if args.label:
                    h["label"] = args.label
                h["ts"] = _now_iso()
                added.append(False)
                return
        history.append({
            "version": new_version,
            "ts": _now_iso(),
            "label": args.label or "",
        })
        added.append(True)

    _write_meta_locked(slug_dir, _mutate)
    entries = len((_read_meta(slug_dir).get("history") or []))
    print(f"  Swapped current.html → versions/{new_version}.html")
    print(f"  meta:current = {new_version}")
    print(f"  history:       {'added' if added and added[0] else 'updated in place'} "
          f"{new_version} ({entries} entr{'y' if entries == 1 else 'ies'} total)")

    resolved = _resolve_scoped_slug(slug_dir.name, getattr(args, "project", None))
    if resolved:
        _project, _slug, record = resolved
        bus_file = record.get("bus_file")
    else:
        _project, _slug = _slug_project(slug_dir)
        bus_file = BUS_ROOT / _project / f"{_slug}.ndjson"
        record = {}
    _bus_emit(bus_file, {
        "event": "version_published",
        "slug": _slug,
        "version": new_version,
        "label": args.label or "",
        "owner_session": record.get("owner_session") or _session_id(),
    })
    return 0


# Machinery, not something a reviewer said. Shown only with --all-events.
_INBOX_HIDDEN = {"seen_updated", "notice_emitted", "inbox_read"}
# The session's own publishing steps, which it already saw in its own output.
_INBOX_SELF = {"page_published", "page_publish_fail", "page_revived", "version_published",
               "comments_seeded", "decision_requested"}


def _inbox_visible(ev: dict, session_id: str) -> bool:
    """Reviewer activity and other sessions' work, not this session's echo.

    Reading a round back used to replay every card this session had just
    posed and every item it had just resolved, ahead of the verdicts it was
    waiting for.
    """
    if ev.get("event") in _INBOX_HIDDEN:
        return False
    # A reopen click is a draft until the reviewer's Send, whose round carries
    # the reopen's words; the bare click invited a re-fix before them.
    if ev.get("event") == "finding_reopened" and ev.get("deferred"):
        return False
    if ev.get("session_id") == session_id and session_id != "unknown":
        return False
    return not (ev.get("event") in _INBOX_SELF and ev.get("owner_session", session_id) == session_id)


def _comment_texts(store: dict) -> dict:
    """{comment_id: (body, verdict_note)} — bus events carry ids, not words.

    Without this the compact listing shows that a reviewer said something but
    not what, and the session has to go and read comments.json anyway. The two
    are kept apart so a verdict line shows the note attached to the verdict and
    a create line shows the card, not a sentence written minutes later.
    """
    out = {}
    for _anchor, c in _iter_comments(store):
        cid = c.get("id")
        if not cid:
            continue
        d = c.get("decision") if isinstance(c.get("decision"), dict) else {}
        out[cid] = (c.get("text") or "", d.get("text") or "")
    return out


def _inbox_line(ev: dict, texts: dict | None = None) -> str:
    """ts  event  comment_id  anchor  author  verdict/status  text[:120]"""
    verdict = (ev.get("decision") or ev.get("new_status")
               or ev.get("delivery") or "")
    body, note = (texts or {}).get(ev.get("comment_id")) or ("", "")
    text = (ev.get("text") or ev.get("response_text") or ev.get("note")
            or ev.get("detail") or (note if ev.get("decision") else "") or body)
    author = str(ev.get("author") or ev.get("by") or "")
    # A reviewer's words are the instruction, so they print whole; clipping
    # them sent the agent to comments.json for the rest.
    full_reviewer_text = ((note and ev.get("decision")) or
                          (ev.get("event") == "round_submitted" and ev.get("note")))
    shown = text if full_reviewer_text and not author.startswith("agent:") \
        else _clip(text, 120)
    return "  %-20s %-17s %-10s %-18s %-24s %-9s %s" % (
        ev.get("ts") or "",
        (ev.get("event") or "")[:17],
        (ev.get("comment_id") or "")[:10],
        (ev.get("anchor_id") or "")[:18],
        author[:24],
        str(verdict)[:9],
        shown,
    )


def _delta_excerpt(delta, limit: int = 120) -> str:
    """Plain text of a Library revision's delta, on one line."""
    ops = delta.get("ops") if isinstance(delta, dict) else None
    text = "".join(op["insert"] for op in ops or [] if isinstance(op, dict) and isinstance(op.get("insert"), str))
    return _clip(" ".join(text.split()), limit)


def _round_lines(ev: dict) -> list[str]:
    """One line per answer and Library edit of a submitted round.

    The round's own line carries only its note; these carry what to act on:
    reopen and verdict words (whole) and each edit's block and new text.
    """
    if ev.get("event") != "round_submitted":
        return []
    lines = []
    row = "  %-20s %-17s %-10s %-18s %-24s %-9s %s"
    for answer in ev.get("answers") or []:
        if not isinstance(answer, dict):
            continue
        number = answer.get("number")
        prompt = _clip(str(answer.get("prompt") or ""), 60)
        words = str(answer.get("text") or "")
        lines.append(row % ("", "  answer", str(answer.get("comment_id") or "")[:10],
                            f"#{number}" if isinstance(number, int) else "", str(answer.get("by") or "")[:24],
                            str(answer.get("verdict") or "")[:9], f"{prompt} → {words}" if words else prompt))
    for edit in ev.get("edits") or []:
        if not isinstance(edit, dict):
            continue
        lines.append(row % ("", "  library edit", "", str(edit.get("block_id") or "")[:18],
                            str(edit.get("by") or "")[:24], "edit",
                            f"{_clip(str(edit.get('title') or ''), 60)}: {_delta_excerpt(edit.get('delta'))}"))
    return lines


def _category(value: str | None) -> str | None:
    if value is not None and value not in CATEGORY_IDS:
        raise ValueError(f"category must be one of {', '.join(CATEGORY_IDS)}")
    return value


def _category_events(events: list[dict], store: dict, category: str) -> list[dict]:
    """Filter mixed submitted rounds as well as legacy per-comment events."""
    comments = {c.get("id"): {"anchor_id": anchor, **c} for anchor, c in _iter_comments(store)}
    result = []
    for event in events:
        row = dict(event)
        collections = [field for field in ("answers", "edits", "comments") if isinstance(row.get(field), list)]
        has_ids = isinstance(row.get("comment_ids"), list)
        if collections or has_ids:
            for field in collections:
                row[field] = [item for item in row[field] if isinstance(item, dict) and
                              _comment_category({**comments.get(item.get("comment_id") or item.get("id"), {}),
                                                 **item, **({"category": "library"} if field == "edits" else {})}) == category]
            if has_ids:
                row["comment_ids"] = [identifier for identifier in row["comment_ids"]
                                      if _comment_category(comments.get(identifier, {})) == category]
                if "comment_count" in row:
                    row["comment_count"] = len(row["comment_ids"])
            if "edit_count" in row and "edits" in collections:
                row["edit_count"] = len(row["edits"])
            if "verdict_counts" in row and "answers" in collections:
                row["verdict_counts"] = {verdict: sum(item.get("verdict") == verdict for item in row["answers"])
                                         for verdict in row["verdict_counts"]}
            elif "verdict_counts" in row:
                row.pop("verdict_counts")  # no category-tagged snapshot to recompute it from
            if isinstance(row.get("undecided_ids"), list):
                row["undecided_ids"] = [identifier for identifier in row["undecided_ids"]
                                        if _comment_category(comments.get(identifier, {})) == category]
                if "undecided_count" in row:
                    row["undecided_count"] = len(row["undecided_ids"])
            if any(row[field] for field in collections) or row.get("comment_ids") or (category == "review" and row.get("note")):
                result.append(row)
        else:
            inferred = {"category": "library"} if str(row.get("event", "")).startswith(("copy_", "library_")) else {}
            if _comment_category({**comments.get(row.get("comment_id"), {}), **inferred, **row}) == category:
                result.append(row)
    return result


def cmd_inbox(args) -> int:
    try:
        category = _category(getattr(args, "category", None))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    resolved = _resolve_slug(args.slug, getattr(args, "project", None))
    if not resolved:
        return 2
    project, slug, record = resolved
    from .workspace import workspace_owner_record
    record = workspace_owner_record(record)
    session_id = _session_id()
    bus_file = Path(record.get("bus_file") or (BUS_ROOT / project / f"{slug}.ndjson"))
    offset_file = _offset_file(project, slug, session_id)
    if category:
        offset_file = offset_file.with_name(f"{offset_file.stem}.{category}{offset_file.suffix}")
    offset_file.parent.mkdir(parents=True, exist_ok=True)

    offset = 0
    if args.unread:
        if offset_file.exists():
            try:
                offset = int(offset_file.read_text(encoding="utf-8").strip())
            except Exception:
                offset = 0
        elif offset_file != BUS_OFFSET_ROOT / project / f"{slug}.offset":
            # First read of this slug by this session. The session that owns
            # the page starts at 0 and gets the whole backlog once — it asked
            # for it. Anyone else starts where the old shared cursor had
            # reached, so a takeover or a bystander does not replay months.
            if record.get("owner_session") == session_id:
                offset = 0
            else:
                offset = _legacy_offset(project, slug)

    events: list[dict] = []
    new_offset = offset
    if bus_file.exists():
        size = bus_file.stat().st_size
        with bus_file.open("r", encoding="utf-8") as f:
            f.seek(min(offset, size))
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                if isinstance(ev, dict):
                    events.append(ev)
            new_offset = f.tell()

    shown = events if getattr(args, "all_events", False) else [
        e for e in events if _inbox_visible(e, session_id)]
    store = _load_store(record)
    if category:
        shown = _category_events(shown, store, category)
    texts = _comment_texts(store)
    for ev in shown:
        note = (texts.get(ev.get("comment_id")) or ("", ""))[1]
        if ev.get("decision") and note and "decision_text" not in ev:
            ev["decision_text"] = note
    cards = _decision_cards(store)
    if category:
        cards = [card for card in cards if card["category"] == category]
    counts = _verdict_counts(cards)
    undecided = [c["anchor_id"] or c["id"] for c in cards if _is_undecided(c)]

    if getattr(args, "json", False):
        print(json.dumps({
            "project": project,
            "slug": slug,
            "session_id": session_id,
            "offset_from": offset,
            "offset_to": new_offset,
            "event_count": len(shown),
            "events": shown,
            "decisions": counts,
            "card_count": len(cards),
            "undecided": undecided,
            **({"category": category} if category else {}),
        }, ensure_ascii=False, indent=2))
    else:
        if not shown:
            print("(no new events)" if args.unread else "(no events)")
        for ev in shown:
            print(_inbox_line(ev, texts))
            for line in _round_lines(ev):
                print(line)
        if cards:
            print(_decision_line(cards))

    if args.unread and new_offset > offset:
        if record.get("owner_session") == session_id and not category:
            from .delivery import acknowledge
            delivery_ids = [e.get("delivery_id") for e in events if e.get("automatic_delivery")]
            for delivery_id in acknowledge(project, slug, session_id, delivery_ids):
                _bus_emit(bus_file, {"event": "round_received", "round_id": delivery_id,
                                     "owner_session": session_id, "slug": slug})
        _bus_emit(bus_file, {
            "event": "inbox_read",
            "slug": slug,
            "session_id": session_id,
            "offset_from": offset,
            "offset_to": new_offset,
            "event_count": len(shown),
            **({"category": category} if category else {}),
        })
        # Commit only bytes actually read. A round appended while reporting
        # this inbox must remain unread and must not become acknowledged.
        tmp = offset_file.with_name(offset_file.name + ".tmp")
        tmp.write_text(str(new_offset), encoding="utf-8")
        os.replace(tmp, offset_file)
    return 0


def cmd_cards(args) -> int:
    """List decision cards and their verdicts straight from comments.json."""
    resolved = _resolve_slug(args.slug, getattr(args, "project", None))
    if not resolved:
        return 2
    project, slug, record = resolved
    try:
        category = _category(getattr(args, "category", None))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    cards = _decision_cards(_load_store(record))
    if category:
        cards = [card for card in cards if card["category"] == category]
    if getattr(args, "json", False):
        print(json.dumps(cards, ensure_ascii=False, indent=2))
        return 0
    if not cards:
        print(f"  {project}/{slug}: no decision cards "
              f"(create some with `{_inv()} ask {slug} --from cards.json`)")
        return 0
    print(f"  {project}/{slug} — {len(cards)} decision card(s)")
    print("  %-6s %-12s %-20s %-6s %-9s %s" % (
        "item", "id", "anchor", "ver", "verdict", "prompt"))
    for c in cards:
        verdict = c["verdict"] or ("pending" if c["pending"] else "—")
        item_number = f"#{c['number']}" if isinstance(c.get("number"), int) else "—"
        line = "  %-6s %-12s %-20s %-6s %-9s %s" % (
            item_number, c["id"][:12], (c["anchor_id"] or "")[:20], c["version"][:6],
            verdict, _clip(c["prompt"], 64))
        # The reviewer's words are the instruction, so they print whole.
        if c["verdict_text"]:
            line += f'  “{c["verdict_text"]}”'
        reopen = (c.get("reopened") or [None])[-1]
        if isinstance(reopen, dict) and str(reopen.get("ts") or "") > str((c.get("fixed") or {}).get("ts") or ""):
            line += f'  reopened: “{reopen.get("text") or ""}”'
        print(line)
    print(_decision_line(cards))
    return 0


def _ask_fallback(record: dict, slug: str, items: list, author: str) -> tuple[list, int, int]:
    """Create the cards one at a time on a server without the batch route.

    Keeps the same anchor-idempotency contract: an existing non-archived card
    by this author on the same anchor is updated, not duplicated.
    """
    author = author if author.startswith("agent:") else f"agent:{author}"
    code, existing = _api(record, "GET", "/api/comments", None, author)
    if code != 200 or not isinstance(existing, list):
        raise RuntimeError(f"cannot read existing cards before legacy fallback (HTTP {code}); inspect existing page/history before retrying; fallback stopped before any per-card write")
    by_anchor: dict = {}
    if code == 200 and isinstance(existing, list):
        for c in existing:
            if not isinstance(c, dict) or c.get("status") in (
                "archived", "resolved_in_version",
            ):
                continue
            if c.get("author") != author or not c.get("decision_request"):
                continue
            by_anchor.setdefault(c.get("anchor_id"), c)

    ids, created, updated = [], 0, 0
    for item in items:
        prior = by_anchor.get(item["anchor_id"])
        if prior:
            body = {"text": item["text"]}
            if item.get("number") is not None:
                body["number"] = item["number"]
            if "decision_request" in item:
                body["decision_request"] = item["decision_request"]
            body.update({field: item[field] for field in ("category", "finding", "doc") if field in item})
            code, payload = _api(record, "PUT", f"/api/comments/{prior['id']}",
                                 body, author)
            if code >= 300 or code == 0:
                raise RuntimeError(f"PUT {prior['id']} → HTTP {code}: {payload}")
            ids.append(prior["id"])
            updated += 1
            continue
        code, payload = _api(record, "POST", "/api/comments", item, author)
        if code >= 300 or code == 0 or not isinstance(payload, dict):
            raise RuntimeError(f"POST {item['anchor_id']} → HTTP {code}: {payload}")
        cid = payload.get("id")
        ids.append(cid)
        created += 1
        # A 2.19 server stores decision_request on create; an older one ignores
        # it, so the card needs the PUT that used to be mandatory.
        if item.get("decision_request") and not payload.get("decision_request"):
            code, payload = _api(record, "PUT", f"/api/comments/{cid}",
                                 {"decision_request": item["decision_request"]}, author)
            if code >= 300 or code == 0:
                raise RuntimeError(f"PUT {cid} (decision_request) → HTTP {code}: {payload}")
    return ids, created, updated


def cmd_ask(args) -> int:
    """Post a whole round of decision cards from one cards.json."""
    resolved = _resolve_scoped_slug(args.slug, getattr(args, "project", None))
    if not resolved:
        return 2
    project, slug, record = resolved
    src = Path(args.from_file).expanduser()
    try:
        raw = json.loads(src.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: could not read cards file {src}: {e}", file=sys.stderr)
        return 2
    cards = raw.get("cards") if isinstance(raw, dict) else raw
    if not isinstance(cards, list) or not cards:
        print("ERROR: cards file must be a JSON array (or {\"cards\": [...]}) of "
              "{anchor_id, text, decision_request} objects", file=sys.stderr)
        return 2

    version = args.version
    if not version and record.get("slug_dir"):
        version = _read_meta(Path(record["slug_dir"])).get("current")

    items = []
    numbered_round = bool(
        isinstance(version, str)
        and re.fullmatch(r"v\d+", version)
        and int(version[1:]) >= 3
    )
    seen_numbers: set[int] = set()
    previous_number = 0
    for i, c in enumerate(cards):
        if not isinstance(c, dict) or not c.get("anchor_id"):
            print(f"ERROR: card #{i} has no anchor_id", file=sys.stderr)
            return 2
        dr = c.get("decision_request") if isinstance(c.get("decision_request"), dict) else None
        item = {
            "anchor_id": c["anchor_id"],
            "text": (c.get("text") or (dr or {}).get("prompt") or "").strip(),
        }
        if not item["text"]:
            print(f"ERROR: card #{i} ({c['anchor_id']}) has neither text nor a "
                  f"decision_request.prompt", file=sys.stderr)
            return 2
        if version:
            item["version"] = version
        try:
            category = _category(c.get("category", getattr(args, "category", None)))
            if category:
                item["category"] = category
            finding = c.get("finding")
            set_id = c.get("set", getattr(args, "set", None))
            if finding is not None:
                if not isinstance(finding, dict):
                    raise ValueError("finding must be an object")
                if set(finding) != {"set", "title"} or not all(isinstance(v, str) and 0 < len(v) <= 200 for v in finding.values()):
                    raise ValueError("finding needs set and title (at most 200 characters each)")
                from .categories import validate_plan_id
                validate_plan_id(finding["set"])
                if category not in (None, "findings"):
                    raise ValueError("finding metadata requires category findings")
                item.update(finding=finding, category="findings")
            elif set_id is not None:
                if category != "findings":
                    raise ValueError("--set/card set requires category findings")
                if not isinstance(set_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", set_id):
                    raise ValueError("finding set must be a safe lowercase ID")
                title = c.get("title") or item["text"]
                if not isinstance(title, str) or len(title) > 200:
                    raise ValueError("finding title must be text of at most 200 characters")
                item["finding"] = {"set": set_id, "title": title}
            if c.get("doc") is not None:
                item["doc"] = c["doc"]
        except ValueError as exc:
            print(f"ERROR: card #{i}: {exc}", file=sys.stderr)
            return 2
        if c.get("anchor_label"):
            item["anchor_label"] = c["anchor_label"]
        number = c.get("number")
        if numbered_round:
            if isinstance(number, bool) or not isinstance(number, int) or number < 1:
                print(f"ERROR: card #{i} needs a positive integer `number` for {version}",
                      file=sys.stderr)
                return 2
            if number in seen_numbers:
                print(f"ERROR: duplicate card number {number}", file=sys.stderr)
                return 2
            if number <= previous_number:
                print("ERROR: card numbers must be strictly increasing", file=sys.stderr)
                return 2
            seen_numbers.add(number)
            previous_number = number
            expected_anchor = f"d:q{number}"
            if c["anchor_id"] != expected_anchor:
                print(f"ERROR: card #{number} must use anchor_id {expected_anchor!r}",
                      file=sys.stderr)
                return 2
            prompt = str((dr or {}).get("prompt") or "")
            if re.match(r"^\s*(?:Q(?:uestion)?\s*\d+|#\s*\d+)", prompt,
                        re.IGNORECASE):
                print(f"ERROR: card #{number} prompt repeats a number", file=sys.stderr)
                return 2
            evidence = (dr or {}).get("evidence")
            if not isinstance(evidence, list) or not evidence:
                print(f"ERROR: card #{number} needs decision_request.evidence",
                      file=sys.stderr)
                return 2
        if number is not None:
            item["number"] = number
        if dr:
            item["decision_request"] = dr
            from .decision_quality import decision_warnings
            for warning in decision_warnings(dr):
                print(f"WARN: {item['anchor_id']}: {warning}", file=sys.stderr)
        items.append(item)

    author = _resolve_author(getattr(args, "author", None))
    route = "batch"
    code, payload = _api(record, "POST", "/api/comments/batch",
                         {"items": items, "idempotency": "anchor"}, author)
    if code in (404, 405, 501):
        print(f"  batch route absent (HTTP {code}) — falling back to per-card POST + PUT",
              file=sys.stderr if getattr(args, "json", False) else sys.stdout)
        route = "fallback"
        try:
            ids, created, updated = _ask_fallback(record, slug, items, author)
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
    elif code == 0:
        print(f"ERROR: API response unavailable or unusable for {project}/{slug}: {payload}\n"
              "  Inspect the server and page state before retrying; this write may already have completed.",
              file=sys.stderr)
        return 2
    elif code >= 300 or not isinstance(payload, dict):
        print(f"ERROR: batch create failed (HTTP {code}): {payload}", file=sys.stderr)
        return 2
    else:
        ids = payload.get("ids") or []
        created = int(payload.get("created") or 0)
        updated = int(payload.get("updated") or 0)

    finding_sets = {item["finding"]["set"] for item in items if item.get("finding")}
    if finding_sets:
        from .categories import load_categories, save_findings_sets
        try:
            sets = load_categories(record["slug_dir"])["findings_sets"]
            known = {entry["id"] for entry in sets}
            additions = [{"id": identifier, "label": identifier} for identifier in sorted(finding_sets - known)]
            if additions:
                save_findings_sets(record["slug_dir"], sets + additions)
        except (OSError, ValueError) as exc:
            print(f"ERROR: cards posted, but findings sets could not be saved: {exc}", file=sys.stderr)
            return 2

    if getattr(args, "json", False):
        print(json.dumps({"slug": slug, "route": route, "ids": ids,
                          "created": created, "updated": updated,
                          "version": version}, ensure_ascii=False))
        return 0
    print(f"  {project}/{slug}: {created} created, {updated} updated "
          f"({route} route, version {version or 'default'})")
    for cid, item in zip(ids, items):
        print(f"    {cid}  {item['anchor_id']}  {_clip(item['text'], 70)}")
    print(f"  Read verdicts with: {_inv()} cards {slug}")
    return 0


def _eval_headline(payload: dict) -> list[str]:
    """Sections 1-3 in the fewest lines that still decide something."""
    meta = payload.get("meta") or {}
    s1 = payload.get("s1_aggregate") or {}
    s2 = payload.get("s2_summary") or {}
    s3 = (payload.get("s3") or {}).get("latency") or {}
    v = s1.get("verdicts") or {}

    def num(x, suffix=""):
        return "—" if x is None else f"{x}{suffix}"

    return [
        f"  window            since {meta.get('since')} — "
        f"{meta.get('slugs_in_window')} of {meta.get('slugs_total')} slugs",
        f"  cards             {s1.get('decision_requests')} decision requests "
        f"over {s1.get('comments')} comments, {s1.get('versions')} versions",
        f"  verdicts          {v.get('accept', 0)} accept, {v.get('reject', 0)} reject, "
        f"{v.get('changes', 0)} changes, {v.get('none', 0)} undecided, "
        f"{v.get('closed', 0)} closed",
        f"  time to verdict   median {num(s1.get('time_to_verdict_median'), 'm')}, "
        f"p90 {num(s1.get('time_to_verdict_p90'), 'm')}",
        f"  event mix         agent {s1.get('agent_events')} "
        f"({num(s1.get('agent_share_pct'), '%')}), reviewer {s1.get('reviewer_events')}",
        f"  rounds            {s2.get('rounds')} over {s2.get('slugs')} slugs, "
        f"median {num(s2.get('median_verdicts_per_round'))} verdicts / "
        f"{num(s2.get('median_duration_min'), 'm')}; "
        f"acted mid-round {s2.get('reacted_mid_round')} of {s2.get('multi_rounds')} "
        f"({num(s2.get('reacted_mid_round_pct'), '%')})",
        f"  verdict→reaction  n={s3.get('n')}, median {num(s3.get('median_min'), 'm')}, "
        f"p90 {num(s3.get('p90_min'), 'm')}, no reaction {s3.get('no_reaction')}",
    ]


def cmd_eval(args) -> int:
    """Run the read-only baseline in a subprocess and print its headline.

    eval.py is exec'd, never imported, and never calls back into this CLI:
    `inbox` advances a read cursor, so a measurement that ran through it would
    change the thing it measures.
    """
    script = PACKAGE_DIR / "eval.py"
    if not script.exists():
        print(f"ERROR: {script} is missing", file=sys.stderr)
        return 2
    out_dir = (Path(args.out_dir).expanduser() if args.out_dir else LOG_DIR.resolve())
    argv = [sys.executable, "-m", "agent_annotate.eval", "--out-dir", str(out_dir)]
    if args.since:
        argv += ["--since", args.since]
    if getattr(args, "refresh_transcripts", False):
        argv.append("--refresh-transcripts")
    try:
        proc = subprocess.run(argv)
    except OSError as e:
        print(f"ERROR: could not run {script}: {e}", file=sys.stderr)
        return 2
    if proc.returncode != 0:
        return proc.returncode

    md = out_dir / "eval-baseline.md"
    js = out_dir / "eval-baseline.json"
    try:
        payload = json.loads(js.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  report: {md}")
        print(f"WARN: could not read {js}: {e}", file=sys.stderr)
        return 0
    print()
    print(f"  annotate eval — {md}")
    print("  ─────────────────────────────────────────────")
    for line in _eval_headline(payload):
        print(line)
    print()
    return 0


def cmd_cost(args) -> int:
    """What agents spend driving annotate, read from their transcripts (costs.py)."""
    from .costs import run
    return run(args)


def cmd_claim(args) -> int:
    """Take ownership of a page for this session, without a monitor.

    The hook only notifies the owning session; a handoff (or a page published
    before ownership existed) needs a way to say "this one is mine now".
    """
    resolved = _resolve_scoped_slug(args.slug, getattr(args, "project", None))
    if not resolved:
        return 2
    project, slug, record = resolved
    from .workspace import workspace_owner_record, workspace_tab_records
    effective = workspace_owner_record(record)
    canonical = effective.get("workspace_owner")
    if canonical:
        resolved = _resolve_scoped_slug(f"{canonical['project']}/{canonical['slug']}")
        if not resolved:
            return 2
        project, slug, record = resolved
    prior = record.get("owner_session")
    fields = _owner_fields()
    target = fields.get("owner_target")
    tabs = ([item for item in workspace_tab_records(record) if not item[2].get("exception")]
            if isinstance(target, dict) and target.get("session") == fields["owner_session"] else [])
    entries = [(project, slug, record), *tabs]
    try:
        with contextlib.ExitStack() as stack:
            for name in sorted({p for p, _, _ in entries}):
                stack.enter_context(_flock(_state_lock_path(name)))
            states = {p: _load_state_for_project(p) for p, _, _ in entries}
            for p, s, selected in entries:
                current = states[p]["slugs"].get(s)
                if not current or current.get("slug_dir") != selected.get("slug_dir"):
                    raise ValueError("workspace registration changed before claim; no ownership written")
            for p, s, selected in entries:
                states[p]["slugs"][s].update(fields)
                if selected.get("slug_dir"):
                    meta_err = _write_owner_meta(Path(selected["slug_dir"]), fields)
                    if meta_err:
                        print(f"WARN: owner chip not updated: {meta_err}", file=sys.stderr)
            for p, state in states.items():
                _save_state_for_project(p, state)
    except (OSError, ValueError, TimeoutError) as exc:
        print(f"ERROR: could not claim {project}/{slug}: {exc}", file=sys.stderr)
        return 2
    print(f"  URL: {page_url(record)}")
    print(f"  {project}/{slug} claimed by {fields['owner_label']} "
          f"(session {fields['owner_session']})")
    if tabs:
        print("  Shared tabs: " + ", ".join(f"{p}/{s}" for p, s, _ in tabs))
    if prior and prior != fields["owner_session"]:
        print(f"  previous owner: {prior}")
    _bus_emit(record.get("bus_file"), {
        "event": "page_claimed",
        "slug": slug,
        "owner_session": fields["owner_session"],
        "owner_agent": fields["owner_agent"],
        "previous_owner": prior,
    })
    return 0


# ────────────────────────────────────────────────────────────────────────────
# D7 — closing stale work, retiring dead registry entries
#
# Two different kinds of rot, deliberately kept apart. `close` retires the
# QUESTIONS on a page nobody ever answered; `retire` retires the REGISTRY ROW
# of a page whose server is long gone. Neither ever deletes anything: close
# archives (the comment keeps every field and moves to `archived`), retire
# moves the row to state/retired/<project>.json with a `retired_at` stamp.
# ────────────────────────────────────────────────────────────────────────────
_AGE_UNITS = {"m": 60, "h": 3600, "d": 86400, "w": 604800}


def _parse_age(text: str) -> int:
    """`30d`, `12h`, `90m`, `2w` → seconds. A bare number means days."""
    raw = (text or "").strip().lower()
    if not raw:
        raise ValueError("empty age")
    unit = raw[-1]
    if unit.isdigit():
        number, seconds = raw, _AGE_UNITS["d"]
    else:
        number, seconds = raw[:-1], _AGE_UNITS.get(unit)
    if seconds is None or not number.isdigit():
        raise ValueError(f"cannot read {text!r} as an age — use 30d, 12h, 90m or 2w")
    return int(number) * seconds


def _fmt_age(seconds) -> str:
    """A width-stable age a human reads without converting anything."""
    if seconds is None:
        return "?"
    s = max(0, int(seconds))
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h"
    return f"{s // 86400}d"


def _age_seconds(iso: str | None, now: datetime | None = None) -> float | None:
    if not iso or not isinstance(iso, str):
        return None
    try:
        parsed = datetime.fromisoformat(iso.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return ((now or datetime.now(UTC)) - parsed).total_seconds()


def _store_file(record: dict) -> Path | None:
    slug_dir = record.get("slug_dir")
    return Path(slug_dir) / "comments.json" if slug_dir else None


def _store_lock_path(project: str, slug: str) -> Path:
    return LOCK_DIR / f"{_safe_component(project)}.{_safe_component(slug)}.store.lock"


def _read_store_file(path: Path) -> dict:
    """The store exactly as written, not the flattened view `_load_store` gives.

    `close` has to write this back, so it may not lose `schema_version` or
    turn the `archived` map into a list on the way through.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema_version": 2, "anchors": {}, "archived": {}}
    if not isinstance(data, dict) or not isinstance(data.get("anchors"), dict):
        # v1 store: {anchor_id: [comment, …]} at the top level.
        anchors = {k: v for k, v in (data or {}).items() if isinstance(v, list)}
        return {"schema_version": 2, "anchors": anchors, "archived": {}}
    data.setdefault("anchors", {})
    if not isinstance(data.get("archived"), (dict, list)):
        data["archived"] = {}
    return data


def _unanswered_cards(store: dict) -> list[tuple[str, dict]]:
    """(anchor_id, comment) for every live card nobody has decided.

    A plain reviewer comment has no `decision_request` and is never in scope:
    `close` retires questions the agent asked, not things the reviewer said.
    """
    out = []
    for anchor_id, items in (store.get("anchors") or {}).items():
        if not isinstance(items, list):
            continue
        for c in items:
            if not isinstance(c, dict):
                continue
            if not isinstance(c.get("decision_request"), dict):
                continue
            if c.get("status") in ("archived", "resolved_in_version") \
                    or isinstance(c.get("decision"), dict):
                continue
            out.append((c.get("anchor_id") or anchor_id, c))
    return out


def _archive_comment_in_store(store: dict, comment_id: str, author: str, now: str) -> bool:
    """Move one comment to `archived`, in the shape the server's route writes.

    Only used when no server is holding the store; a live page is closed
    through its own API so the two never write the same file.
    """
    archived = store.setdefault("archived", {})
    if isinstance(archived, list):  # v1 shape: keep it a list
        append = archived.append
    else:
        append = None
    for anchor_id, items in list((store.get("anchors") or {}).items()):
        if not isinstance(items, list):
            continue
        for c in list(items):
            if not isinstance(c, dict) or c.get("id") != comment_id:
                continue
            c["status"] = "archived"
            c["archived_at"] = now
            c["archived_by"] = author
            items.remove(c)
            if not items:
                del store["anchors"][anchor_id]
            if append is not None:
                append(c)
            else:
                archived.setdefault(anchor_id, []).append(c)
            return True
    return False


def _live_server_for(record: dict) -> dict | None:
    """The live server serving THIS slug_dir, with the port `ps` reports.

    Identity is the slug_dir, never the port: ports are reused across the
    registry (a dead row and a live one routinely share 8801), so "something
    answers on that URL" would happily point `close` at another page's server.
    The recorded pid is equally unreliable after a restart outside the CLI,
    which is why `status` locates servers the same way.
    """
    slug_dir = record.get("slug_dir")
    if not slug_dir:
        return None
    try:
        key = str(Path(slug_dir).resolve())
    except OSError:
        return None
    procs = _running_servers().get(key) or []
    return procs[0] if procs else None


def cmd_close(args) -> int:
    """Archive the decision cards on a page that nobody ever answered.

    Only cards: a card with a verdict is left alone (it was answered), and an
    ordinary reviewer comment is never touched. The page keeps serving; this
    closes the questions, not the page.
    """
    resolved = _resolve_scoped_slug(args.slug, getattr(args, "project", None))
    if not resolved:
        return 2
    project, slug, record = resolved
    try:
        threshold = _parse_age(args.older_than)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    store_path = _store_file(record)
    if not store_path or not store_path.exists():
        print(f"ERROR: {project}/{slug} has no comment store at {store_path}", file=sys.stderr)
        return 2

    now = datetime.now(UTC)
    store = _read_store_file(store_path)
    stale, young = [], 0
    for anchor_id, c in _unanswered_cards(store):
        age = _age_seconds(c.get("created_at"), now)
        if age is None or age < threshold:
            young += 1
            continue
        stale.append({
            "id": c.get("id") or "?",
            "anchor_id": anchor_id,
            "age_s": age,
            "prompt": (c.get("decision_request") or {}).get("prompt") or c.get("text") or "",
        })
    stale.sort(key=lambda r: -r["age_s"])

    label = "would archive" if args.dry_run else "archiving"
    print(f"  {project}/{slug} — {len(stale)} unanswered card(s) older than "
          f"{args.older_than}, {young} younger")
    if stale:
        print("  %-12s %-22s %-6s %s" % ("ID", "ANCHOR", "AGE", "PROMPT"))
        print("  %-12s %-22s %-6s %s" % ("-" * 12, "-" * 22, "-" * 6, "-" * 40))
        for row in stale:
            print("  %-12s %-22s %-6s %s" % (
                row["id"][:12], row["anchor_id"][:22], _fmt_age(row["age_s"]),
                _clip(row["prompt"], 48)))
    if not stale:
        print("  nothing to close.")
        return 0
    if args.dry_run:
        print(f"  (dry run) {label} {len(stale)}; nothing was written.")
        return 0

    author = _resolve_author(getattr(args, "author", None))
    ids = [row["id"] for row in stale]
    archived_ids, failures = [], []
    live = _live_server_for(record)
    if live:
        # The page is serving: its server owns comments.json, so go through
        # the route it already has rather than writing the file underneath it.
        # The port comes from the running process, not the registry, which may
        # still name the port this page had two restarts ago.
        target = dict(record)
        if live.get("port"):
            target["local_url"] = f"http://localhost:{live['port']}/"
        for cid in ids:
            code, payload = _api(target, "POST", f"/api/comments/{cid}/archive", {}, author)
            if code == 200:
                archived_ids.append(cid)
            else:
                failures.append((cid, code, payload))
    else:
        stamp = _now_iso()
        try:
            with _flock(_store_lock_path(project, slug)):
                store = _read_store_file(store_path)
                for cid in ids:
                    if _archive_comment_in_store(store, cid, author, stamp):
                        archived_ids.append(cid)
                    else:
                        failures.append((cid, 0, "not found in store"))
                tmp = store_path.with_name(store_path.name + ".tmp")
                tmp.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")
                os.replace(tmp, store_path)
        except TimeoutError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 4

    remaining = len(_unanswered_cards(_read_store_file(store_path)))
    _bus_emit(record.get("bus_file"), {
        "event": "page_closed",
        "slug": slug,
        "archived_ids": archived_ids,
        "archived_count": len(archived_ids),
        "remaining_open": remaining,
        "by": author,
        "session_id": _session_id(),
        "older_than": args.older_than,
    })
    print(f"  archived {len(archived_ids)} card(s); {remaining} unanswered card(s) remain.")
    for cid, code, payload in failures:
        print(f"  FAILED {cid}: HTTP {code} {payload}", file=sys.stderr)
    return 2 if failures else 0


def _retired_file(project: str) -> Path:
    return STATE_DIR / "retired" / f"{project}.json"


def _load_retired_for_project(project: str) -> dict:
    path = _retired_file(project)
    if not path.exists():
        return {"project": project, "slugs": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"project": project, "slugs": {}}
    data.setdefault("project", project)
    if not isinstance(data.get("slugs"), dict):
        data["slugs"] = {}
    return data


def _save_retired_for_project(project: str, data: dict) -> None:
    _save_private_json(_retired_file(project), data)


def _retired_entries() -> list[tuple[str, str, dict]]:
    root = STATE_DIR / "retired"
    out: list[tuple[str, str, dict]] = []
    if not root.exists():
        return out
    for path in sorted(root.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        project = data.get("project") or path.stem
        for slug, record in (data.get("slugs") or {}).items():
            if isinstance(record, dict):
                out.append((project, slug, record))
    return sorted(out, key=lambda e: (e[0], e[1]))


def _entry_is_dead(record: dict, live: dict) -> bool:
    """A registry row with no process behind it.

    Two conditions, because either one alone gets it wrong: the recorded pid
    is stale the moment a server is restarted outside the CLI, and a slug_dir
    match is the only way to tell "this page is served by a different pid now"
    from "this page is gone".
    """
    try:
        pid = int(record.get("pid") or 0)
    except (TypeError, ValueError):
        pid = 0
    if pid and _is_process_alive(pid):
        return False
    slug_dir = record.get("slug_dir")
    if not slug_dir:
        return True
    try:
        key = str(Path(slug_dir).resolve())
    except OSError:
        return True
    return not live.get(key)


def cmd_retire(args) -> int:
    """Move dead registry rows to state/retired/<project>.json.

    Touches the registry and nothing else: the slug directory, its bus and the
    transport config are all left exactly as they are, so a retired page can
    be re-published later and pick its history straight back up.
    """
    live = _running_servers()
    if getattr(args, "dead", False):
        targets = [(p, s, r) for p, s, r in _registry_entries() if _entry_is_dead(r, live)]
        skipped = [(p, s) for p, s, r in _registry_entries() if not _entry_is_dead(r, live)]
    else:
        if not getattr(args, "slug", None):
            print("ERROR: name a slug or pass --dead", file=sys.stderr)
            return 2
        resolved = _resolve_scoped_slug(args.slug, getattr(args, "project", None))
        if not resolved:
            return 2
        project, slug, record = resolved
        if not _entry_is_dead(record, live):
            print(f"ERROR: {project}/{slug} is still alive — stop it with "
                  f"`{_inv()} unpublish {slug}` first.", file=sys.stderr)
            return 2
        targets, skipped = [(project, slug, record)], []

    if not targets:
        print("  (nothing to retire — every registered page still has a live server)")
        return 0

    print(f"  {'PROJECT':<15} {'SLUG':<24} {'PID':<8} {'PORT':<6} URL")
    print(f"  {'-' * 15} {'-' * 24} {'-' * 8} {'-' * 6} {'-' * 40}")
    for project, slug, record in targets:
        print(f"  {project[:15]:<15} {slug[:24]:<24} {str(record.get('pid')):<8} "
              f"{str(record.get('port')):<6} {page_url(record)}")
    if args.dry_run:
        print(f"  (dry run) would retire {len(targets)} entr(ies); nothing was written.")
        return 0

    stamp = _now_iso()
    moved = 0
    for project, slug, _record in targets:
        try:
            with _flock(_state_lock_path(project)):
                state = _load_state_for_project(project)
                record = (state.get("slugs") or {}).get(slug)
                if not isinstance(record, dict):
                    continue
                # Written to `retired` BEFORE it leaves the registry: a crash
                # between the two writes must leave a duplicate, never a row
                # that exists nowhere.
                retired = _load_retired_for_project(project)
                retired["slugs"][slug] = {**record, "retired_at": stamp}
                _save_retired_for_project(project, retired)
                state["slugs"].pop(slug, None)
                _save_state_for_project(project, state)
                moved += 1
        except TimeoutError as exc:
            print(f"ERROR: {project}/{slug}: {exc}", file=sys.stderr)
            return 4
    print(f"  retired {moved} entr(ies) → {STATE_DIR / 'retired'}")
    if skipped:
        print(f"  left alone ({len(skipped)} still alive): "
              + ", ".join(f"{p}/{s}" for p, s in skipped))
    return 0


# ────────────────────────────────────────────────────────────────────────────
# revive — bring dead registry rows back after a reboot or crash
# ────────────────────────────────────────────────────────────────────────────
REVIVE_LABEL = "com.agent-annotate.revive"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"


def _wait_listening(port: int, pid: int, seconds: float = 8.0) -> bool:
    """True once `pid` is alive and something LISTENs on `port`."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _is_process_alive(pid):
            return False
        try:
            if _port_listen_pid(port) is not None:
                return True
        except (OSError, subprocess.SubprocessError):
            return _is_process_alive(pid)
        time.sleep(0.25)
    return False


def _reroute(project: str, slug: str, record: dict, port: int):
    """Re-run a page's route on `port`. Returns (url, details, base_path, error)."""
    details = record.get("transport_details") or {}
    pbp = record.get("public_base_path") or ""
    base_path = pbp if "public_base_path" in record else f"/{slug}"
    transport_name = record.get("transport") or "local"
    try:
        from .transports import load as _load_transport
        cfg = _project_config(project)
        opts = _transport_opts(cfg)
        if cfg.get("hostname"):
            opts["hostname"] = cfg["hostname"]
        opts["previous"] = {"port": record.get("port"), "details": details}
        if transport_name == "cloudflare_tailscale":
            opts["public"] = _had_public_route(record)
        with _flock(_tunnel_lock_path()):
            result = _load_transport(transport_name).publish(
                base_path.lstrip("/"), port, **opts)
        return (mounted_url(result.get("url") or record.get("url"), base_path), result.get("details", details),
                base_path, None)
    except Exception as e:
        return page_url(record), details, pbp, str(e)


def _route_host(record: dict) -> str | None:
    """The tailnet name a page's route was made under, if it has one."""
    details = record.get("transport_details") or {}
    ts = details.get("tailscale") if isinstance(details.get("tailscale"), dict) else None
    if ts is None and details.get("transport") in {"tailscale", "funnel"}:
        ts = details
    return (ts or {}).get("hostname")


def _live_tailnet_host() -> str | None:
    """This machine's tailnet name now, or None when tailscale cannot say."""
    try:
        proc = subprocess.run(["tailscale", "status", "--json"], capture_output=True,
                              text=True, timeout=15)
        name = (json.loads(proc.stdout).get("Self") or {}).get("DNSName") or ""
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return name.rstrip(".") or None


def _rerouted_if_renamed(project: str, slug: str, record: dict, live_host: str | None,
                         dry_run: bool) -> tuple[str, str] | None:
    """Move a live page's route onto the machine's current tailnet name.

    The server survives a rename but its route does not: on 2026-09-27 the
    Mac went macbook-pro -> m1max -> macbook-pro within hours, and every page
    kept a URL on whichever name it was published under.
    """
    old = _route_host(record)
    if not live_host or not old or old == live_host:
        return None
    if dry_run:
        return "would-reroute", f"{old} → {live_host}"
    url, details, _pbp, error = _reroute(project, slug, record, int(record.get("port") or 0))
    if error:
        return "failed", f"reroute: {error}"
    record.update({"url": url, "transport_details": details,
                   "public_url": mounted_url(details.get("public_url") or record.get("public_url"), _pbp)})
    return "rerouted", f"{old} → {live_host}"


def _revive_one(project: str, slug: str, live: dict, dry_run: bool,
                live_host: str | None = None) -> tuple[str, str]:
    """Restart one dead page on its recorded port, keeping its owner.

    `publish` is the wrong tool for this: it makes the caller the owner, so a
    page revived by whoever happened to run it stops notifying the session
    that asked the questions. Returns (outcome, detail).
    """
    with _flock(_state_lock_path(project)):
        state = _load_state_for_project(project)
        record = (state.get("slugs") or {}).get(slug)
        if not isinstance(record, dict):
            return "gone", "no longer registered"
        if (_project_config(project).get("transport") == "funnel"
                and record.get("transport") != "funnel"):
            return "skipped", "non-Funnel page needs explicit publication; no legacy route created"
        if _entry_is_dead(record, live):
            live = _running_servers()
        if not _entry_is_dead(record, live):
            procs = live.get(str(Path(record.get("slug_dir", "")).resolve())) or []
            if len(procs) == 1 and procs[0]["pid"] != record.get("pid"):
                # The fleet snapshot can predate a concurrent runtime restart.
                # Reconcile again while holding the page state lock.
                procs = _running_servers().get(str(Path(record.get("slug_dir", "")).resolve())) or []
                if len(procs) != 1:
                    return "skipped", "server changed during revive; no stale process adopted"
                if procs[0]["pid"] == record.get("pid"):
                    return "alive", ""
                # Serving under a pid the registry never saw: adopt it.
                if not dry_run:
                    record["pid"] = procs[0]["pid"]
                    record["port"] = procs[0]["port"] or record.get("port")
                    _save_state_for_project(project, state)
                return "adopted", f"pid {procs[0]['pid']}"
            moved = _rerouted_if_renamed(project, slug, record, live_host, dry_run)
            if moved and moved[0] == "rerouted":
                _save_state_for_project(project, state)
            return moved or ("alive", "")
        slug_dir = Path(record.get("slug_dir") or "")
        if not (slug_dir / "current.html").exists():
            return "skipped", f"no current.html in {slug_dir}"
        port = int(record.get("port") or 0)
        if not port:
            return "skipped", "no recorded port"
        try:
            free = _find_free_port_after(port, registered_pid=record.get("pid"))
        except RuntimeError as e:
            free = None
            detail = str(e)
        transport_name = record.get("transport") or "local"
        if free and free != port and transport_name == "local":
            # No route points at a local page's port, so it may move, but not
            # onto a port another registered page will come back to.
            reserved = {int(r["port"]) for p, s, r in _registry_entries()
                        if (p, s) != (project, slug) and r.get("port")}
            while free in reserved:
                nxt = _find_free_port_after(free + 1)
                if nxt <= free:
                    break
                free = nxt
            port = free
        elif free != port:
            # Every route points at this port. Moving it would strand them.
            return "skipped", f"port {port} is in use" if free else detail
        if dry_run:
            return "would-revive", f"port {port}"

        if transport_name == "local":
            url, details, pbp, error = (f"http://localhost:{port}/",
                                        record.get("transport_details") or {}, "", None)
        else:
            # Re-run the route every time: it is idempotent, and it is what
            # moves a page onto the machine's current tailnet name.
            url, details, pbp, error = _reroute(project, slug, record, port)
        bus_dir = BUS_ROOT / project
        bus_dir.mkdir(parents=True, exist_ok=True)
        pid = _start_server(slug_dir, port, bus_dir, pbp)
        if not _wait_listening(port, pid):
            return "failed", f"server exited; see {LOG_DIR / (slug_dir.name + '.log')}"
        record.update({
            "pid": pid,
            "port": port,
            "local_url": f"http://localhost:{port}/",
            "url": url,
            "public_url": mounted_url(details.get("public_url") or record.get("public_url"), pbp),
            "public_base_path": pbp or None,
            "transport_details": details,
            "transport_error": error,
            "revived_at": _now_iso(),
        })
        _save_state_for_project(project, state)
    _bus_emit(record.get("bus_file") or str(bus_dir / f"{slug}.ndjson"),
              {"event": "page_revived", "slug": slug, "pid": pid, "port": port,
               "url": redact_review_key(url), "transport_error": redact_share_links(error), "ts": _now_iso()})
    return "revived", f"port {port}" + (f" (route: {error})" if error else "")


def _revive_plist(interval: int) -> str:
    exe = shutil.which("annotate") or str(Path.home() / ".local" / "bin" / "annotate")
    log = LOG_DIR / "revive.log"
    path = os.environ.get("PATH", "/usr/bin:/bin")
    for extra in ("/opt/homebrew/bin", "/usr/local/bin", str(Path.home() / ".local" / "bin")):
        if extra not in path.split(":"):
            path += ":" + extra
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{REVIVE_LABEL}</string>
  <key>ProgramArguments</key>
  <array><string>{exe}</string><string>revive</string><string>--quiet</string></array>
  <key>RunAtLoad</key><true/>
  <key>StartInterval</key><integer>{interval}</integer>
  <key>AbandonProcessGroup</key><true/>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>{path}</string></dict>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict>
</plist>
"""


def _launchctl(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *argv], capture_output=True, text=True, timeout=15)


def cmd_revive(args) -> int:
    """Restart every registered page whose server is gone.

    Safe to run any time and from launchd: live pages are left alone, retired
    rows are never touched, and each revived page keeps its port, route and
    owner.
    """
    plist = LAUNCH_AGENTS_DIR / f"{REVIVE_LABEL}.plist"
    domain = f"gui/{os.getuid()}"
    if args.install:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
        plist.write_text(_revive_plist(args.interval), encoding="utf-8")
        _launchctl("bootout", f"{domain}/{REVIVE_LABEL}")
        proc = _launchctl("bootstrap", domain, str(plist))
        if proc.returncode != 0:
            print(f"ERROR: launchctl bootstrap failed: {(proc.stderr or proc.stdout).strip()}",
                  file=sys.stderr)
            return 1
        print(f"  installed {plist} (at login + every {args.interval}s)")
        return 0
    if args.uninstall:
        _launchctl("bootout", f"{domain}/{REVIVE_LABEL}")
        plist.unlink(missing_ok=True)
        print(f"  removed {plist}")
        return 0

    if not args.dry_run:
        _maybe_update()
    live = _running_servers()
    live_host = _live_tailnet_host()
    failed = 0
    for project, slug, _record in _registry_entries():
        try:
            outcome, detail = _revive_one(project, slug, live, args.dry_run, live_host)
        except TimeoutError as e:
            outcome, detail = "failed", str(e)
        if not args.dry_run:
            from .delivery import dispatch_record
            try:
                dispatch_record(_record, project, slug)
            except (OSError, ValueError) as exc:
                print(f"WARN: delivery {project}/{slug}: {exc}", file=sys.stderr)
        if outcome == "failed":
            failed += 1
        if outcome == "alive" or (args.quiet and outcome in ("gone",)):
            continue
        stamp = f"{_now_iso()} " if args.quiet else "  "
        print(f"{stamp}{outcome:<12} {project}/{slug}" + (f"  {detail}" if detail else ""))
    return 1 if failed else 0


def _maybe_update() -> None:
    from .updates import read_enrollment, write_enrollment
    try:
        config = read_enrollment()
        if not config["enabled"]:
            return
        age = _age_seconds(config.get("last_check"))
        if age is not None and age < 86400:
            return
        write_enrollment({"last_check": _now_iso()})
        cmd_update(argparse.Namespace(check=False, apply=True, enable=False, disable=False))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"WARN: stable update: {exc}", file=sys.stderr)


def cmd_update(args) -> int:
    from .updates import latest_release, read_enrollment, stage_release, version_tuple, write_enrollment
    try:
        if args.enable or args.disable:
            write_enrollment({"enabled": bool(args.enable)})
            print("Stable updates enabled; the revive watchdog checks daily" if args.enable else "Stable updates disabled")
            return 0
        release = latest_release()
        print(f"Installed {__version__}; stable {release['version']} ({release['html_url']})")
        if not args.apply or version_tuple(release["version"]) < version_tuple(__version__):
            return 0
        enrollment = read_enrollment()
        records = _registry_entries()
        if (enrollment.get("active_version") == release["version"] and enrollment.get("active_manifest")
                and all(record.get("runtime_manifest") == enrollment.get("active_manifest")
                        and record.get("runtime_python") == enrollment.get("active_python")
                        for _project, _slug, record in records)):
            return 0
        from .deployment import activate_runtime
        python = stage_release(release)
        result = activate_runtime(python)
        write_enrollment({"active_version": release["version"], "active_build_id": result["runtime"]["build_id"],
                          "active_manifest": result["runtime"], "active_python": str(python), "last_check": _now_iso()})
        print(json.dumps(result, ensure_ascii=False))
        print("Skills are user-managed; reload or synchronize them only when explicitly requested.")
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"ERROR: stable update: {exc}", file=sys.stderr)
        return 1


def cmd_deliver(args) -> int:
    from .delivery import dispatch_record
    resolved = _resolve_scoped_slug(args.slug, getattr(args, "project", None))
    if not resolved:
        return 2
    project, slug, record = resolved
    result = dispatch_record(record, project, slug, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def cmd_project(args) -> int:
    from .project_state import load_project, save_project
    resolver = _resolve_scoped_slug if args.from_file else _resolve_slug
    resolved = resolver(args.slug, getattr(args, "project", None))
    if not resolved:
        return 2

    _project, _slug, record = resolved
    try:
        directory = Path(record["slug_dir"])
        if args.from_file:
            data = json.loads(Path(args.from_file).read_text())
            saved = save_project(directory, data)
            print(f"  project saved: {len(saved['modules'])} persistent modules")
        else:
            print(json.dumps(load_project(directory), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: project: {exc}", file=sys.stderr)
        return 2


def fix_finding(record: dict, identifier, proofs: list[str], note: str, author: str) -> dict:
    """Shared CLI/MCP proof boundary, before trusted storage writes."""
    from .categories import (
        MAX_PROOF_BYTES,
        add_proof_file,
        check_proof_type,
        mark_finding_fixed,
        validate_proof,
    )
    if not proofs or len(proofs) > 30:
        raise ValueError("marking a finding fixed requires 1-30 proof URLs or files")
    directory = Path(record["slug_dir"])
    author = author if author.startswith("agent:") else f"agent:{author}"
    prepared = []
    for value in proofs:
        if value.lower().startswith(("http://", "https://")):
            prepared.append(validate_proof(directory, [{"label": value[:200], "url": value}])[0])
        elif re.match(r"\s|[A-Za-z][A-Za-z0-9+.-]*:", value):
            raise ValueError(f"proof URLs must start with http:// or https:// (got {value[:60]!r})")
        else:
            check_proof_type(value)
            source = Path(value).expanduser().absolute()
            try:
                source.resolve(strict=True).relative_to(Path.cwd().resolve())
                source.relative_to(Path.cwd().absolute())
            except (OSError, ValueError) as exc:
                raise ValueError("proof file must be inside the current working directory") from exc
            if not source.is_file() or source.stat().st_size > MAX_PROOF_BYTES:
                raise ValueError("proof must be a regular file of at most 10 MiB")
            prepared.append(source)
    # Validate the target and all ordinary inputs before copying attachments.
    # A number is the one `cards` shows, allocated or stored.
    store = _load_store(record)
    matches = [c.get("id") for anchor, c in _iter_comments(store)
               if _comment_category({"anchor_id": anchor, **c}) == "findings" and
               (c.get("id") == identifier or (str(identifier).isdigit() and str(c.get("number")) == str(identifier)))]
    if str(identifier).isdigit():
        matches = list(dict.fromkeys(matches + [
            card["id"] for card in _decision_cards(store)
            if card["category"] == "findings" and str(card.get("number")) == str(identifier)]))
    if not matches:
        raise LookupError(f"finding {identifier} not found")
    if len(matches) != 1:
        raise ValueError("ambiguous finding number; use its comment id")
    identifier = matches[0]
    if not isinstance(note, str) or len(note) > 10000:
        raise ValueError("fixed note must be text of at most 10000 characters")
    proof = []
    try:
        for item in prepared:
            proof.append(add_proof_file(directory, item) if isinstance(item, Path) else item)
        validate_proof(directory, proof)
        comment = mark_finding_fixed(directory, identifier, by=author, note=note, proof=proof)
    except (OSError, ValueError, KeyError):
        for item in proof:
            if "attachment" in item:
                (directory / "attachments" / item["attachment"]).unlink(missing_ok=True)
        raise
    _bus_emit(record.get("bus_file"), {"event": "finding_fixed", "slug": record.get("slug"),
              "comment_id": comment["id"], "category": "findings", "author": author,
              "note": note, "fixed": comment["fixed"]})
    return comment


def cmd_finding(args) -> int:
    resolved = _resolve_scoped_slug(args.slug, getattr(args, "project", None))
    if not resolved:
        return 2
    project, slug, record = resolved
    try:
        comment = fix_finding(record, args.fixed, args.proof or [], args.note or "",
                              _resolve_author(getattr(args, "author", None)))
        if getattr(args, "json", False):
            print(json.dumps(comment, ensure_ascii=False, indent=2))
        else:
            print(f"  {project}/{slug}: finding #{comment.get('number', args.fixed)} fixed with proof\n  URL: {page_url(record)}")
        return 0
    except (OSError, ValueError, LookupError) as exc:
        # KeyError's str() quotes its message; print the words.
        print(f"ERROR: finding: {exc.args[0] if isinstance(exc, LookupError) and exc.args else exc}", file=sys.stderr)
        return 2


def cmd_plan(args) -> int:
    from .categories import MAX_PLAN_BYTES, publish_plan_revision, validate_plan_id
    from .pagegen import PageGenError, render_plan
    resolved = _resolve_scoped_slug(args.slug, getattr(args, "project", None))
    if not resolved:
        return 2
    project, slug, record = resolved
    try:
        validate_plan_id(args.plan_id)
        source = Path(args.from_file).expanduser()
        if source.suffix.lower() not in (".md", ".html"):
            raise ValueError("plan source must be .md or .html")
        with source.open("rb") as stream:
            body = stream.read(MAX_PLAN_BYTES + 1)
        if len(body) > MAX_PLAN_BYTES:
            raise ValueError("plan source exceeds 4 MiB")
        content = body.decode("utf-8")
        title = args.title
        if source.suffix.lower() == ".md":
            content, title = render_plan(content, args.plan_id, title=title)
        result = publish_plan_revision(record["slug_dir"], args.plan_id, content,
                                       title=title, label=args.label)
        _bus_emit(record.get("bus_file"), {"event": "plan_published", "slug": slug,
                  "category": "plans", "doc": f"plan:{args.plan_id}", "version": result["version"]})
        if getattr(args, "json", False):
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"  {project}/{slug}: plan {args.plan_id} published as {result['version']}\n  URL: {page_url(record)}")
        return 0
    except (OSError, ValueError, KeyError, PageGenError) as exc:
        print(f"ERROR: plan: {exc}", file=sys.stderr)
        return 2


def cmd_copy(args) -> int:
    from .copy_state import load_copy, save_copy
    resolved = _resolve_scoped_slug(args.slug, getattr(args, "project", None))
    if not resolved:
        return 2
    project, slug, record = resolved
    try:
        directory = Path(record["slug_dir"])
        block_id = getattr(args, "block", None)
        if args.from_file:
            if block_id:
                raise ValueError("--block is for reading; import the complete copy document")
            before = load_copy(directory)
            document = save_copy(directory, json.loads(Path(args.from_file).read_text()))
            if before != document:
                _bus_emit(record.get("bus_file"), {"event": "copy_updated", "slug": slug, "category": "library",
                          "owner_session": record.get("owner_session"), "block_count": len(document["blocks"])})
            if getattr(args, "json", False):
                print(json.dumps(document, ensure_ascii=False, indent=2))
            else:
                print(f"  copy saved: {len(document['blocks'])} blocks\n  URL: {page_url(record)}")
        else:
            document = load_copy(directory)
            if block_id:
                blocks = [block for block in document["blocks"] if block["id"] == block_id]
                if not blocks:
                    raise ValueError("copy block not found")
                document = {**document, "blocks": blocks}
            print(json.dumps(document, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: copy: {exc}", file=sys.stderr)
        return 2


def _fleet_snapshot(from_file=None) -> dict:
    from .fleet import collect_fleet, validate_config

    path = Path(from_file).expanduser() if from_file else CONFIG_DIR / "fleet.json"
    config = validate_config(redact_share_links(json.loads(path.read_text()) if from_file or path.exists()
                                               else {"schema_version": 1, "targets": []}))
    machine = socket.gethostname().split(".")[0]
    if not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,127}", machine):
        machine = "local"
    identities = {(target["machine"], target["project"], target["slug"]): target["url"] for target in config["targets"]}
    urls = {url: identity for identity, url in identities.items()}
    excluded = 0
    for project, slug, record in _registry_entries():
        try:
            target = validate_config({"schema_version": 1, "targets": [{"machine": machine, "project": project,
                                      "slug": slug, "url": redact_review_key(page_url(record))}]})["targets"][0]
        except ValueError:
            excluded += 1
            continue
        identity = (machine, project, slug)
        if target["url"] in urls or identity in identities:
            if identities.get(identity) == target["url"] and urls.get(target["url"]) == identity:
                continue
            raise ValueError("fleet inventory conflicts with a local registered page")
        config["targets"].append(target)
        urls[target["url"]] = identity
        identities[identity] = target["url"]
    snapshot = redact_share_links(collect_fleet(config))
    snapshot["observed_at"] = _now_iso()
    snapshot["excluded_local_records"] = excluded
    if excluded:
        snapshot["limitations"].append(f"{excluded} local registry entries had no usable safe page URL and were excluded.")
    return snapshot


def cmd_fleet(args) -> int:
    try:
        snapshot = _fleet_snapshot(args.from_file)
        if args.snapshot:
            path = Path(args.snapshot).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(prefix=".fleet-", dir=path.parent)
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                    json.dump(snapshot, output, ensure_ascii=False, indent=2)
                    output.write("\n")
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
        if args.json:
            print(json.dumps(snapshot, ensure_ascii=False))
        else:
            summary = snapshot["summary"]
            print(f"Fleet: {summary['total']} configured pages; {summary['healthy']} healthy, "
                  f"{summary['degraded']} degraded, {summary['unreachable']} unreachable")
            print("Versions: " + ", ".join(f"{name}: {count}" for name, count in summary["by_version"].items()))
            print("Machine labels and owner presence are inventory observations, not attested live ownership.")
        return 0
    except (OSError, ValueError):
        print("ERROR: fleet inventory could not be read or validated; no configuration or page state changed", file=sys.stderr)
        return 2


def cmd_install_shim(args) -> int:
    changed, msg = _ensure_shim_installed(force=getattr(args, "force", False), refresh=True)
    print(f"  {msg}")
    globals()["_INV_CACHE"] = None
    found = shutil.which("annotate")
    if found:
        try:
            ours = _is_ours(Path(found).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            ours = False
        print(f"  `annotate` on PATH → {found}" + ("" if ours else "   (NOT this package)"))
        if not ours:
            print(f"  Put {SHIM_PATH.parent} ahead of {Path(found).parent} on PATH, "
                  f"or call `{_module_invocation()}` directly.")
    else:
        print(f"  `annotate` is not on PATH — add {SHIM_PATH.parent} to it, or call "
              f"`{_module_invocation()}`.")
    return 0 if (changed or "already" in msg) else 1


def cmd_install_skill(args) -> int:
    """Write a provider skill directory (SKILL.md, references/, hook shim)
    from the packaged skill text. Idempotent; never deletes."""
    from .skillgen import install_skill

    for line in install_skill(args.provider, Path(args.dest)):
        print(line)
    return 0


def cmd_sync_skills(args) -> int:
    from .skillgen import sync_skills
    results = sync_skills()
    for line in results:
        print(line)
    return 1 if any(line.startswith("conflict") for line in results) else 0


def cmd_watch(args) -> int:
    slug = args.slug
    record = None
    for sf in _all_state_files():
        st = json.loads(sf.read_text(encoding="utf-8"))
        if slug in st.get("slugs", {}):
            record = st["slugs"][slug]
            break
    if not record:
        print(f"ERROR: no state record for slug {slug!r}", file=sys.stderr)
        return 2
    bus_file = Path(record["bus_file"])
    print(f"  Tailing {bus_file} (Ctrl-C to stop)")
    bus_file.parent.mkdir(parents=True, exist_ok=True)
    if not bus_file.exists():
        bus_file.touch()
    with bus_file.open("r", encoding="utf-8") as f:
        f.seek(0, os.SEEK_END)
        try:
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                print(line.rstrip())
        except KeyboardInterrupt:
            print()
            return 0


def _live_monitor_leases(lease_dir: Path, expected_bus: Path) -> list[tuple[Path, dict]]:
    live = []
    expected = str(expected_bus.resolve())
    for path in lease_dir.glob("*.json"):
        try:
            lease = json.loads(path.read_text(encoding="utf-8"))
            pid = int(lease.get("pid", 0))
            if str(Path(lease.get("bus_file", "")).resolve()) != expected:
                raise ValueError("bus mismatch")
            if not _is_process_alive(pid):
                raise ValueError("dead process")
            live.append((path, lease))
        except Exception:
            path.unlink(missing_ok=True)
    return live


def _stop_monitor_leases(leases: list[tuple[Path, dict]]) -> bool:
    pids = {int(lease.get("pid", 0)) for _, lease in leases if int(lease.get("pid", 0)) > 0}
    for pid in pids:
        if pid == os.getpid():
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.time() + 3
    while time.time() < deadline and any(_is_process_alive(pid) for pid in pids if pid != os.getpid()):
        time.sleep(0.1)
    if any(_is_process_alive(pid) for pid in pids if pid != os.getpid()):
        return False
    for path, _ in leases:
        path.unlink(missing_ok=True)
    return True


def _monitor_owner_label(explicit: str | None) -> tuple[str, str, str]:
    """(session, agent, label) for the lease.

    v2.18 read CLAUDE_SESSION_ID, which Claude Code leaves empty, so every
    lease on this machine was labelled `interactive-ppid-<n>` and no lease
    could be matched to the session that took it.
    """
    owner = explicit or os.environ.get("ANNOTATE_SESSION_ID") or _session_id()
    if owner == "unknown":
        owner = f"interactive-ppid-{os.getppid()}"
    return owner, _session_agent(), _session_label(owner)


def _monitor_line(ev: dict) -> str:
    """One actionable event, compact: ts, event, ids, verdict counts."""
    ids = ev.get("comment_ids")
    if not isinstance(ids, list) or not ids:
        ids = [ev["comment_id"]] if ev.get("comment_id") else []
    counts = ev.get("verdict_counts")
    if not isinstance(counts, dict):
        counts = {ev["decision"]: 1} if ev.get("decision") else {}

    bits = [ev.get("ts") or "", ev.get("event") or ""]
    if ids:
        head = [str(i) for i in ids[:12]]
        bits.append("ids=" + ",".join(head)
                    + (f"+{len(ids) - 12}" if len(ids) > 12 else ""))
    tally = " ".join(f"{k}={v}" for k, v in sorted(counts.items()) if v)
    if tally:
        bits.append(tally)
    undecided = ev.get("undecided_ids")
    if isinstance(undecided, list) and undecided:
        bits.append("undecided=%d" % len(undecided))
    if ev.get("delivery"):
        bits.append("delivery=%s" % ev["delivery"])
    author = ev.get("author") or ev.get("by")
    if author:
        bits.append("by=%s" % author)
    if ev.get("note"):
        bits.append('note="%s"' % _clip(ev["note"], 80))
    return "ANNOTATE_EVENT " + " ".join(b for b in bits if b)


def cmd_monitor(args) -> int:
    """Tail actionable events while advertising a live session monitor.

    This command is designed to run inside Claude Code's persistent Monitor
    tool. The lease lets the web UI distinguish an interactive handoff from a
    queued event; the shared byte offset lets a newly armed monitor replay any
    events that arrived while no session monitor was active.
    """
    resolved = _resolve_scoped_slug(args.slug, getattr(args, "project", None))
    if not resolved:
        return 2
    project, slug, record = resolved

    bus_file = Path(record["bus_file"])
    bus_file.parent.mkdir(parents=True, exist_ok=True)
    if not bus_file.exists():
        bus_file.touch()

    lease_dir = MONITOR_ROOT / project / slug
    lease_dir.mkdir(parents=True, exist_ok=True)
    existing = _live_monitor_leases(lease_dir, bus_file)
    if existing:
        current_owner = existing[0][1].get("owner_session") or f"pid {existing[0][1].get('pid')}"
        if not args.takeover:
            print(
                f"ERROR: monitor for {project}/{slug} is already owned by {current_owner}.\n"
                f"  Use --takeover only during an explicit session handoff.",
                file=sys.stderr,
            )
            return 3
        if not _stop_monitor_leases(existing):
            print(f"ERROR: could not stop the current monitor for {project}/{slug}", file=sys.stderr)
            return 3

    # Capture the starting cursor before advertising the lease; feedback can arrive as soon as it exists.
    offset_file = MONITOR_OFFSET_ROOT / project / f"{slug}.offset"
    offset_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        offset = int(offset_file.read_text(encoding="utf-8").strip()) if offset_file.exists() else bus_file.stat().st_size
    except Exception:
        offset = bus_file.stat().st_size

    lease_path = lease_dir / "owner.json"
    owner_session, owner_agent, owner_label = _monitor_owner_label(args.owner)
    provider_name = getattr(args, "provider", None) or "stdout"
    provider_session = getattr(args, "session_id", None) or owner_session
    lease = {
        "schema_version": 2,
        "pid": os.getpid(),
        "project": project,
        "slug": slug,
        "bus_file": str(bus_file),
        "owner_session": owner_session,
        "owner_agent": owner_agent,
        "owner_label": owner_label,
        "provider": provider_name,
        "provider_session": provider_session,
        "host": socket.gethostname(),
        "started_at": _now_iso(),
        "events": sorted(MONITOR_EVENTS),
    }
    try:
        fd = os.open(lease_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # Another session won the claim race after the live-lease check.
        print(f"ERROR: monitor ownership changed while claiming {project}/{slug}; retry the handoff", file=sys.stderr)
        return 3
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(lease, fh, indent=2)

    # A SIGTERM must run the finally block below. Claude Code's Monitor tool
    # reaps a stream that has been quiet for ~60s, and the default disposition
    # kills the process outright: all eight leases found on this machine were
    # left behind pointing at dead pids, and every one of them made the web UI
    # believe a session was listening when none was.
    def _on_term(signum, frame):
        raise KeyboardInterrupt

    for _sig in (signal.SIGTERM, signal.SIGHUP):
        try:
            signal.signal(_sig, _on_term)
        except (ValueError, OSError):
            pass

    print("ANNOTATE_MONITOR_ARMED " + json.dumps({
        "project": project,
        "slug": slug,
        "owner_session": owner_session,
        "owner_agent": owner_agent,
        "owner_label": owner_label,
        "provider": provider_name,
        "pid": os.getpid(),
    }, ensure_ascii=False, separators=(",", ":")), flush=True)
    _bus_emit(bus_file, {
        "event": "monitor_armed",
        "slug": slug,
        "owner_session": owner_session,
        "owner_agent": owner_agent,
        "pid": os.getpid(),
    })

    next_heartbeat_at = (
        time.monotonic() + MONITOR_HEARTBEAT_INTERVAL
        if MONITOR_HEARTBEAT_INTERVAL > 0
        else float("inf")
    )
    try:
        with bus_file.open("r", encoding="utf-8") as f:
            f.seek(min(offset, bus_file.stat().st_size))
            while True:
                line_start = f.tell()
                line = f.readline()
                if not line:
                    now = time.monotonic()
                    if now >= next_heartbeat_at:
                        print("ANNOTATE_MONITOR_HEARTBEAT " + json.dumps({
                            "ts": _now_iso(),
                            "pid": os.getpid(),
                            "slug": slug,
                            "project": project,
                        }, ensure_ascii=False, separators=(",", ":")), flush=True)
                        next_heartbeat_at = now + MONITOR_HEARTBEAT_INTERVAL
                    time.sleep(0.25)
                    continue
                next_offset = f.tell()
                try:
                    ev = json.loads(line)
                except Exception:
                    offset_file.write_text(str(next_offset), encoding="utf-8")
                    continue
                if ev.get("event") in MONITOR_PRINT_EVENTS:
                    print(_monitor_line(ev), flush=True)
                if (provider_name == "codex-app-server" and ev.get("event") == "session_push"
                        and not ev.get("automatic_delivery")):
                    # Deliver before advancing the cursor: a failed turn leaves
                    # the event unread so it is retried from the durable bus.
                    try:
                        _deliver_to_codex(provider_session, record, project, slug, ev)
                    except Exception as exc:
                        print(f"ANNOTATE_DELIVERY_ERROR {exc}", file=sys.stderr, flush=True)
                        f.seek(line_start)
                        time.sleep(2)
                        continue
                offset_file.write_text(str(next_offset), encoding="utf-8")
    except KeyboardInterrupt:
        return 0
    finally:
        released = False
        try:
            current = json.loads(lease_path.read_text(encoding="utf-8"))
            if int(current.get("pid", 0)) == os.getpid():
                lease_path.unlink(missing_ok=True)
                released = True
        except Exception:
            pass
        _bus_emit(bus_file, {
            "event": "monitor_exited",
            "slug": slug,
            "owner_session": owner_session,
            "pid": os.getpid(),
            "lease_released": released,
        })


def _comment_call(args, method: str, path: str, body: dict, done: str | None = None,
                  target: str = "") -> int:
    """One comment mutation, reported in one line.

    These run once per earlier item on every new version. Echoing the whole
    comment back cost about 530 tokens a call and told the agent nothing it
    had not just sent; `--json` still prints it.
    """
    resolved = _resolve_scoped_slug(args.slug, getattr(args, "project", None))
    if not resolved:
        return 2
    _project, _slug, record = resolved
    author = _resolve_author(getattr(args, "author", None))
    code, payload = _api(record, method, path, body, author)
    err = payload.get("error") if isinstance(payload, dict) else payload
    if code == 409 and "cannot demote user_confirmed" in str(err):
        # The reviewer already closed it; there is nothing left to mark.
        print(f"noop {args.comment_id}: already confirmed by the reviewer")
        return 0
    if code == 0 or code >= 300:
        print(f"ERROR: {method} {path} → HTTP {code}: {err}", file=sys.stderr)
        closest = payload.get("closest") if isinstance(payload, dict) else None
        if closest:
            print(f"  closest anchors in {payload.get('version')}: {', '.join(closest)}",
                  file=sys.stderr)
        return 2
    if getattr(args, "json", False) or not done or not isinstance(payload, dict):
        print(json.dumps(payload, ensure_ascii=False) if payload is not None else "ok")
    else:
        number = f" #{payload['number']}" if payload.get("number") else ""
        print(f"{done} {args.comment_id}{number}{target}")
    return 0


def cmd_archive_comment(args) -> int:
    return _comment_call(args, "POST", f"/api/comments/{args.comment_id}/archive", {},
                         done="archived")


def cmd_resolve(args) -> int:
    body = {
        "status": "resolved_in_version",
        "resolved_in_version": args.in_version,
        "resolution_anchor_id": args.anchor,
    }
    if args.response:
        body["response_text"] = args.response
    return _comment_call(args, "PUT", f"/api/comments/{args.comment_id}", body,
                         done="resolved", target=f" → {args.in_version} {args.anchor}")


def cmd_carry(args) -> int:
    body = {"carry_forward": {"version": args.to_version, "anchor_id": args.anchor}}
    return _comment_call(args, "PUT", f"/api/comments/{args.comment_id}", body,
                         done="carried", target=f" → {args.to_version} {args.anchor}")


def cmd_addressed(args) -> int:
    body = {"status": "addressed_by_agent"}
    if args.response:
        body["response_text"] = args.response
    return _comment_call(args, "PUT", f"/api/comments/{args.comment_id}", body,
                         done="addressed")


def _registry_entries() -> list[tuple[str, str, dict]]:
    """Every registered (project, slug, record), newest state file last."""
    out: list[tuple[str, str, dict]] = []
    for sf in _all_state_files():
        try:
            st = json.loads(sf.read_text(encoding="utf-8"))
        except Exception:
            continue
        project = st.get("project") or sf.stem
        for slug, record in (st.get("slugs") or {}).items():
            if isinstance(record, dict):
                out.append((project, slug, record))
    return sorted(out, key=lambda e: (e[0], e[1]))


def _registered_listing() -> str:
    entries = _registry_entries()
    if not entries:
        return f"    (nothing registered — run `{_inv()} publish <slug-dir>` first)"
    lines = []
    for project, slug, record in entries:
        try:
            live = "live" if _is_process_alive(int(record.get("pid") or 0)) else "stopped"
        except (TypeError, ValueError):
            live = "stopped"
        lines.append(f"    {project}/{slug}  ({live})")
    return "\n".join(lines)


def _resolve_slug(raw: str, project_hint: str | None = None):
    """(project, slug, record) for `slug`, `project/slug`, or `--project p slug`.

    Also survives the two being swapped, which is what sessions actually typed,
    and names the registered slugs on a miss instead of answering with a bare
    "no state record for slug".
    """
    entries = _registry_entries()
    project = project_hint
    slug = (raw or "").strip().strip("/")
    if "/" in slug:
        head, tail = slug.split("/", 1)
        if tail:
            project, slug = head, tail

    def _by_slug(name):
        return [e for e in entries if e[1] == name]

    candidates = []
    if project:
        candidates = [e for e in _by_slug(slug)
                      if e[0] == project or e[0].endswith(project)]
        if not candidates:
            # The hint named no project. It was probably the slug, or noise.
            candidates = _by_slug(slug) or _by_slug(project)
    else:
        candidates = _by_slug(slug)

    if len(candidates) > 1:
        # The same slug under two projects is usually one live page and one
        # leftover. Pick the page this session owns, else the only live one.
        mine = [e for e in candidates if e[2].get("owner_session") == _session_id()]
        live = [e for e in candidates if _is_process_alive(int(e[2].get("pid") or 0))]
        candidates = mine if len(mine) == 1 else live if len(live) == 1 else candidates
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        print(f"ERROR: {slug!r} is registered under more than one project — "
              f"pass <project>/<slug>:", file=sys.stderr)
        for p, s, _ in candidates:
            print(f"    {p}/{s}", file=sys.stderr)
        return None
    print(f"ERROR: no page registered as {raw!r}. Registered slugs:", file=sys.stderr)
    print(_registered_listing(), file=sys.stderr)
    return None


def _resolve_scoped_slug(raw: str, project_hint: str | None = None):
    """Exact scope for destructive and MCP calls; no convenience fallback."""
    slug = (raw or "").strip().strip("/")
    project = project_hint
    if "/" in slug:
        head, slug = slug.split("/", 1)
        if project is not None and project != head:
            print("ERROR: conflicting project qualification", file=sys.stderr)
            return None
        project = head
    matches = [(p, s, r) for p, s, r in _registry_entries() if s == slug and (project is None or p == project)]
    if len(matches) != 1:
        print(f"ERROR: no unique exact page for {raw!r}; use PROJECT/SLUG or --project PROJECT", file=sys.stderr)
        return None
    return matches[0]


# ────────────────────────────────────────────────────────────────────────────
# comments.json — the one place its shape is decoded
# ────────────────────────────────────────────────────────────────────────────
def _load_store(record: dict) -> dict:
    """Read a slug's comment store.

    The shape is {"schema_version":…, "anchors": {anchor_id: [comment, …]},
    "archived": {anchor_id: [comment, …]} (or a legacy list)}. Every observed first-attempt parse reached for
    store["comments"], which does not exist and never has.
    """
    slug_dir = record.get("slug_dir")
    if not slug_dir:
        return {"anchors": {}, "archived": []}
    try:
        data = json.loads((Path(slug_dir) / "comments.json").read_text(encoding="utf-8"))
    except Exception:
        return {"anchors": {}, "archived": []}
    if not isinstance(data, dict):
        return {"anchors": {}, "archived": []}
    anchors = data.get("anchors")
    if not isinstance(anchors, dict):
        # v1 store: {anchor_id: [comment, …]} at the top level.
        anchors = {k: v for k, v in data.items() if isinstance(v, list)}
    archived = data.get("archived")
    return {"anchors": anchors, "archived": archived if isinstance(archived, (dict, list)) else []}


def _iter_comments(store: dict):
    for anchor_id, items in (store.get("anchors") or {}).items():
        if isinstance(items, list):
            for c in items:
                if isinstance(c, dict):
                    yield anchor_id, c


def _decision_cards(store: dict) -> list[dict]:
    """Every live decision card, flattened for printing."""
    comments = list(_iter_comments(store))
    historical = []
    archived = store.get("archived") or {}
    values = archived.values() if isinstance(archived, dict) else archived if isinstance(archived, list) else []
    for value in values:
        historical.extend([value] if isinstance(value, dict) else value if isinstance(value, list) else [])
    allocation = comments + [(c.get("anchor_id"), c) for c in historical if isinstance(c, dict)]
    numbers: dict[str, int] = {}
    used: set[int] = set()
    for _anchor_id, comment in allocation:
        number = comment.get("number")
        cid = comment.get("id")
        if (cid and isinstance(number, int) and not isinstance(number, bool)
                and number > 0 and cid not in numbers):
            numbers[cid] = number
            used.add(number)
    for _anchor_id, comment in allocation:
        cid = comment.get("id")
        if not cid or cid in numbers:
            continue
        prompt = str((comment.get("decision_request") or {}).get("prompt") or "")
        match = re.match(r"^Q(\d+)(?![0-9A-Za-z])", prompt, re.IGNORECASE)
        number = int(match.group(1)) if match else 0
        if number > 0:
            numbers[cid] = number
            used.add(number)
    next_number = max(used, default=0) + 1
    for _anchor_id, comment in sorted(
            allocation,
            key=lambda item: (
                item[1].get("created_at") or "",
                item[1].get("id") or "",
            )):
        cid = comment.get("id")
        if not cid or cid in numbers:
            continue
        while next_number in used:
            next_number += 1
        numbers[cid] = next_number
        used.add(next_number)
        next_number += 1

    cards = []
    for anchor_id, c in comments:
        dr = c.get("decision_request")
        if not isinstance(dr, dict) or c.get("status") in (
            "archived", "resolved_in_version",
        ):
            continue
        d = c.get("decision") if isinstance(c.get("decision"), dict) else {}
        cards.append({
            "id": c.get("id") or "?",
            "number": numbers.get(c.get("id")),
            "anchor_id": c.get("anchor_id") or anchor_id,
            "prompt": dr.get("prompt") or c.get("text") or "",
            "verdict": d.get("verdict"),
            "verdict_text": d.get("text") or "",
            "pending": bool(d.get("round_pending")),
            "by": d.get("by") or "",
            "decided_at": d.get("ts") or "",
            "version": c.get("version") or "",
            "status": c.get("status") or "",
            "category": _comment_category({"anchor_id": anchor_id, **c}),
            **{field: c[field] for field in ("doc", "finding", "fixed", "fixed_history", "reopened") if field in c},
        })
    return sorted(cards, key=lambda c: (
        c["number"] if isinstance(c.get("number"), int) else 10**9,
        c["anchor_id"],
        c["id"],
    ))


# Every verdict answers a card, including `comment` (Answer in words, or a
# reviewer's reply on an unanswered card, which the server records as one).
VERDICT_COLUMNS = ("accept", "reject", "changes", "comment", "select")
ANSWER_VERDICTS = ("accept", "reject", "changes", "comment", "select")


def _verdict_column(verdict) -> str | None:
    """The counting column for a stored verdict, or None if it has no verdict."""
    if not verdict:
        return None
    return verdict if verdict in VERDICT_COLUMNS else None


def _is_undecided(card: dict) -> bool:
    """True when nothing has answered this card and the agent has not
    addressed or withdrawn it."""
    return (card.get("verdict") not in ANSWER_VERDICTS
            and card.get("status") != "addressed_by_agent")


def _decision_line(cards: list[dict]) -> str:
    """The one-line decision summary `cards` and `inbox` both print."""
    counts = _verdict_counts(cards)
    undecided = [c["anchor_id"] or c["id"] for c in cards if _is_undecided(c)]
    return ("  decisions: %d accept, %d reject, %d changes, %d select, "
            "%d comment; undecided: %s"
            % (counts["accept"], counts["reject"], counts["changes"],
               counts["select"], counts["comment"],
               ", ".join(undecided) if undecided else "none"))


def _verdict_counts(cards: list[dict]) -> dict:
    counts = {k: 0 for k in VERDICT_COLUMNS}
    for c in cards:
        col = _verdict_column(c["verdict"])
        if col:
            counts[col] += 1
    return counts


_LOCAL_API_MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class _LocalAPINoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _local_api_url(record: dict, path: str) -> str:
    base = record.get("local_url")
    message = "local_url must be direct loopback HTTP on the recorded port without credentials, query, fragment, or a route; republish the page if its record is stale"
    try:
        if (not isinstance(base, str) or len(base) > 2048
                or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in base)
                or any(char in base for char in ("\\", "?", "#"))):
            raise ValueError
        parsed = urllib.parse.urlsplit(base)
        host = parsed.hostname
        if (parsed.scheme != "http" or not host or parsed.username is not None or parsed.password is not None
                or parsed.path not in ("", "/") or (parsed.port is not None and not 0 < parsed.port < 65536)):
            raise ValueError
        expected_port = record.get("port")
        if type(expected_port) is not int or not 0 < expected_port < 65536 or expected_port != (parsed.port or 80):
            raise ValueError
        if host != "localhost" and ("%" in host or not ipaddress.ip_address(host).is_loopback):
            raise ValueError
        authority = f"[{host}]" if ":" in host else host
        if not re.fullmatch(re.escape(authority) + r"(?::[0-9]{1,5})?", parsed.netloc, re.I):
            raise ValueError
    except ValueError:
        raise ValueError(message) from None

    prefix = record.get("public_base_path")
    if prefix is None:
        prefix = ""
    for value, allow_empty in ((prefix, True), (path, False)):
        try:
            if (not isinstance(value, str) or len(value) > 4096
                    or (not value and not allow_empty) or (value and not value.startswith("/"))
                    or value.startswith("//") or any(char in value for char in ("\\", "?", "#"))
                    or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)):
                raise ValueError
            route = urllib.parse.urlsplit(value)
            decoded = urllib.parse.unquote(route.path, errors="strict")
            if (route.scheme or route.netloc or route.query or route.fragment or "\\" in decoded
                    or any(ord(char) < 32 or ord(char) == 127 for char in decoded)
                    or any(segment in (".", "..") for segment in decoded.split("/"))):
                raise ValueError
        except ValueError:
            raise ValueError("local API prefix and route must be root-relative paths without authority, query, fragment, controls, or traversal") from None
    return base.rstrip("/") + prefix.rstrip("/") + path


def _api(record: dict, method: str, path: str, body, author: str,
         timeout: float = 15.0) -> tuple[int, object]:
    """One local API call against a running server. Returns (status, parsed).

    Status 0 means no usable response, not proof that a write never happened.
    The timeout is per socket operation, not a total wall deadline; only the
    explicitly recorded loopback server is trusted. Reads are byte-bounded.
    """
    try:
        url = _local_api_url(record, path)
    except ValueError as exc:
        return 0, str(exc)
    try:
        data = json.dumps(body).encode() if body is not None else None
        agent = author if author.startswith("agent:") else f"agent:{author}"
        req = urllib.request.Request(url, method=method, data=data, headers={
            "Content-Type": "application/json",
            "X-Annotate-Agent": agent,
            # Older runtimes read only this header. A mandatory agent: tag
            # preserves attribution; direct-loopback/no-proxy/no-redirect
            # validation prevents sending a human proxy claim or remote leak.
            "Cf-Access-Authenticated-User-Email": agent,
            "X-Annotate-Session": _session_id(),
        })
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _LocalAPINoRedirect())
        try:
            response = opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            code = response.status
            if 300 <= code < 400:
                return code, {"error": "local API redirect refused; inspect the recorded server before retrying"}
            raw = response.read(_LOCAL_API_MAX_RESPONSE_BYTES + 1)
    except (OSError, TypeError, ValueError, HTTPException) as exc:
        return 0, f"local API request failed ({type(exc).__name__}); check the recorded server and inspect page state before retrying a write"
    if len(raw) > _LOCAL_API_MAX_RESPONSE_BYTES:
        error = f"local API response exceeds {_LOCAL_API_MAX_RESPONSE_BYTES} bytes; inspect server logs and page state before retrying a write"
        return (code, {"error": error}) if code >= 400 else (0, error)
    if not raw.strip():
        return code, None
    try:
        return code, json.loads(raw)
    except (ValueError, RecursionError):
        error = "local API returned invalid JSON; inspect server logs and page state before retrying a write"
        return (code, {"error": error}) if code >= 400 else (0, error)


def _find_record(slug: str) -> dict | None:
    for sf in _all_state_files():
        st = json.loads(sf.read_text(encoding="utf-8"))
        if slug in st.get("slugs", {}):
            return st["slugs"][slug]
    return None


# ────────────────────────────────────────────────────────────────────────────
# Installation, providers, hook and MCP
# ────────────────────────────────────────────────────────────────────────────
def _deliver_to_codex(thread_id: str, record: dict, project: str, slug: str, ev: dict) -> None:
    """Push one session_push into a Codex thread through the app-server."""
    from .providers.codex_app_server import CodexAppServerAdapter

    comment_ids = ev.get("comment_ids") or ev.get("comments") or []
    count = ev.get("comment_count") or ev.get("count") or len(comment_ids)
    url = page_url(record)
    counts = ev.get("verdict_counts") if isinstance(ev.get("verdict_counts"), dict) else None
    tally = (" Verdicts: " + ", ".join(f"{k} {v}" for k, v in counts.items() if v) + "."
             if counts else "")
    message = (
        f"[Agent Annotate] The reviewer pushed {count} feedback item(s) from "
        f"{project}/{slug} to this session. Page: {url}. "
        f"Comment IDs: {comment_ids}.{tally} Run `{_inv()} inbox {project}/{slug} --unread`, "
        "review the exact comments and anchors, then reply through the annotation API."
    )
    result = CodexAppServerAdapter().deliver(thread_id, message)
    print("ANNOTATE_DELIVERED " + json.dumps(result.__dict__, separators=(",", ":")), flush=True)


def cmd_doctor(args) -> int:
    """Validate the installation without changing provider config."""
    ensure_runtime_dirs()
    found = shutil.which("annotate")
    ours = False
    if found:
        try:
            ours = _is_ours(Path(found).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            ours = False
    node = shutil.which("node")
    codex = shutil.which("codex")
    lsof = shutil.which("lsof")
    checks = [
        ("version", True, __version__),
        ("invocation", True, _inv()),
        ("annotate", ours,
         (found + ("" if ours else "   (NOT this package — run install-shim)"))
         if found else f"not on PATH; run `{_module_invocation()} install-shim`"),
        ("config_dir", CONFIG_DIR.is_dir(), str(CONFIG_DIR)),
        ("projects_toml", True, str(PROJECTS_TOML) + ("" if PROJECTS_TOML.is_file() else "   (absent; Tailscale Funnel default)")),
        ("state_dir", STATE_DIR.is_dir(), str(STATE_DIR)),
        ("bus_root", BUS_ROOT.is_dir(), str(BUS_ROOT)),
        ("web_assets", all((WEB_DIR / n).is_file() for n in
                           ("shell.html", "shell.js", "shell.css", "adapter.js", "template.html")),
         str(WEB_DIR)),
        ("hook_script", HOOK_SCRIPT.is_file(),
         str(HOOK_SCRIPT) + ("" if os.access(HOOK_SCRIPT, os.X_OK) else "   (not executable; publish fixes the mode)")),
        ("hook_installed", _hook_registered(), str(SETTINGS_JSON)),
        ("node", node is not None, node or "not found; inline JS lint unavailable"),
        ("lsof", lsof is not None, lsof or "not found; port liveness falls back to the bind test"),
        ("codex", codex is not None, codex or "not found; Codex adapter unavailable"),
        ("session", _session_id() != "unknown", _session_id()),
    ]
    from .updates import read_enrollment, runtime_manifest
    manifest = runtime_manifest()
    checks.append(("build", True, manifest["build_id"]))
    checks.append(("stable_updates", True, "enabled" if read_enrollment()["enabled"] else "disabled; annotate update --enable"))
    failed = False
    for name, ok, detail in checks:
        hard = name in ("state_dir", "bus_root", "web_assets", "hook_script")
        failed = failed or (hard and not ok)
        print(f"{'PASS' if ok else ('FAIL' if hard else 'WARN')}  {name:<15} {detail}")
    return 1 if failed else 0


def _hook_registered() -> bool:
    try:
        settings = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
    except Exception:
        return False
    for group in (settings.get("hooks") or {}).get("UserPromptSubmit") or []:
        for h in (group.get("hooks") if isinstance(group, dict) else None) or []:
            if isinstance(h, dict) and _is_our_hook_command(h.get("command", "")):
                return True
    return False


def cmd_sessions(args) -> int:
    """List Codex sessions that can be assigned to an annotation page."""
    from .providers.codex_app_server import CodexAppServerAdapter

    try:
        sessions = CodexAppServerAdapter().list_sessions(cwd=args.cwd)
    except Exception as exc:
        print(f"ERROR: could not list Codex sessions: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(sessions, indent=2, ensure_ascii=False))
        return 0
    if not sessions:
        print("(no matching Codex sessions)")
        return 0
    current = os.environ.get("CODEX_THREAD_ID")
    print(f"  {'CURRENT':<7} {'THREAD':<38} {'STATUS':<10} {'CWD':<36} PREVIEW")
    for session in sessions:
        status = session.get("status", {}).get("type", "unknown")
        preview = " ".join(session.get("preview", "").split())[:72]
        cwd = session.get("cwd", "")
        marker = "yes" if session.get("id") == current else ""
        print(f"  {marker:<7} {session.get('id', ''):<38} {status:<10} {cwd[-36:]:<36} {preview}")
    return 0


def cmd_send(args) -> int:
    """Deliver a coordination message to one existing Codex thread."""
    from .providers.codex_app_server import CodexAppServerAdapter

    try:
        result = CodexAppServerAdapter().deliver(args.thread, args.message)
    except Exception as exc:
        print(f"ERROR: Codex delivery failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.__dict__, indent=2))
    return 0


def cmd_connect(args) -> int:
    """Run the Codex page monitor as a detached delivery worker."""
    resolved = _resolve_scoped_slug(args.slug, getattr(args, "project", None))
    if not resolved:
        return 2
    project, slug, _record = resolved
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{slug}-codex-monitor.log"
    cmd = [
        sys.executable, "-m", "agent_annotate.cli",
        "monitor", f"{project}/{slug}",
        "--owner", args.thread,
        "--provider", "codex-app-server",
        "--session-id", args.thread,
    ]
    if args.takeover:
        cmd.append("--takeover")
    with log_path.open("ab", buffering=0) as log:
        proc = subprocess.Popen(
            cmd, stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True,
        )
    deadline = time.time() + 4
    lease = MONITOR_ROOT / project / slug / "owner.json"
    while time.time() < deadline:
        if proc.poll() is not None:
            print(f"ERROR: monitor stopped; inspect {log_path}", file=sys.stderr)
            return 2
        if lease.exists():
            print(f"Connected {project}/{slug} to Codex thread {args.thread}")
            print(f"Monitor PID: {proc.pid}")
            print(f"Log: {log_path}")
            return 0
        time.sleep(0.1)
    proc.terminate()
    print(f"ERROR: monitor did not acquire its lease; inspect {log_path}", file=sys.stderr)
    return 2


def cmd_disconnect(args) -> int:
    resolved = _resolve_scoped_slug(args.slug, getattr(args, "project", None))
    if not resolved:
        return 2
    project, slug, rec = resolved
    lease_dir = MONITOR_ROOT / project / slug
    leases = _live_monitor_leases(lease_dir, Path(rec["bus_file"])) if lease_dir.is_dir() else []
    if not leases:
        print(f"No live monitor owns {project}/{slug}")
        return 0
    if not _stop_monitor_leases(leases):
        print(f"ERROR: could not stop monitor for {project}/{slug}", file=sys.stderr)
        return 2
    print(f"Disconnected monitor for {project}/{slug}; server remains running")
    return 0


def cmd_hook_check(args) -> int:
    """The UserPromptSubmit hook, in-process: same code as check-comment-bus.sh
    execs, reading Claude Code's payload from stdin. Always exits 0."""
    from .hooks.check_comment_bus import main as hook_main

    try:
        hook_main()
    except SystemExit:
        pass
    except Exception:
        pass
    return 0


def cmd_prune_bus(args) -> int:
    from .prune_bus import main as prune_main

    argv = ["--days", str(args.days)]
    if args.apply:
        argv.append("--apply")
    return int(prune_main(argv) or 0)


def cmd_mcp(args) -> int:
    from .mcp_server import main as mcp_main

    mcp_main()
    return 0


# ────────────────────────────────────────────────────────────────────────────
# Argparse
# ────────────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(prog="annotate", description="Agent Annotate CLI")
    p.add_argument("--version", action="version", version=f"agent-annotate {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_doc = sub.add_parser("doctor", help="validate the installation and local integrations")
    from .workspace import cmd_workspace
    sp_workspace = sub.add_parser("workspace", help="find/select the one project page across sessions")
    sp_workspace.add_argument("--project", default=None)
    sp_workspace.add_argument("--select", default=None, metavar="PROJECT/SLUG")
    sp_workspace.add_argument("--root", default=None, help="project folder containing existing review pages")
    sp_workspace.add_argument("--json", action="store_true")
    sp_workspace.set_defaults(func=cmd_workspace)
    sp_doc.set_defaults(func=cmd_doctor)
    sp_update = sub.add_parser("update", help="check/apply tested stable releases; opt into daily checks")
    update_mode = sp_update.add_mutually_exclusive_group()
    update_mode.add_argument("--check", action="store_true")
    update_mode.add_argument("--apply", action="store_true")
    update_mode.add_argument("--enable", action="store_true")
    update_mode.add_argument("--disable", action="store_true")
    sp_update.set_defaults(func=cmd_update)
    from .reports import cmd_report
    sp_report = sub.add_parser("report", help="generate/schedule the short weekly usage page without a model run")
    sp_report.add_argument("slug_dir")
    sp_report.add_argument("--project", default="reviews")
    sp_report.add_argument("--publish", action="store_true")
    sp_report.add_argument("--install", action="store_true", help="schedule weekly on macOS")
    sp_report.add_argument("--uninstall", action="store_true", help="remove the weekly job; preserve report history")
    sp_report.set_defaults(func=cmd_report)
    sub.add_parser("sync-skills", help="refresh registered generated skills; preserve custom edits").set_defaults(func=cmd_sync_skills)

    sp_delivery = sub.add_parser("deliver", help="inspect/retry pending completed-round delivery to the page owner")
    sp_delivery.add_argument("slug")
    sp_delivery.add_argument("--project", default=None)
    sp_delivery.add_argument("--dry-run", action="store_true")
    sp_delivery.set_defaults(func=cmd_deliver)

    sp_fleet = sub.add_parser("fleet", help="collect safe runtime/delivery observations from configured page URLs")
    sp_fleet.add_argument("--from", dest="from_file", default=None, help="remote inventory; defaults to config_dir/fleet.json")
    sp_fleet.add_argument("--json", action="store_true")
    sp_fleet.add_argument("--snapshot", default=None, help="write a private redacted snapshot")
    sp_fleet.set_defaults(func=cmd_fleet)

    sp_project = sub.add_parser("project", help="read/update persistent project links, progress and notes")
    sp_project.add_argument("slug")
    sp_project.add_argument("--project", default=None)
    sp_project.add_argument("--from", dest="from_file", default=None)
    sp_project.set_defaults(func=cmd_project)
    sp_copy = sub.add_parser("copy", aliases=["library"], help="read/import formatted copy blocks and immutable revision history")
    sp_copy.add_argument("slug")
    sp_copy.add_argument("--project", default=None)
    sp_copy.add_argument("--from", dest="from_file", default=None)
    sp_copy.add_argument("--block", default=None, help="read one copy block and its history")
    sp_copy.add_argument("--json", action="store_true")
    sp_copy.set_defaults(func=cmd_copy)
    sp_finding = sub.add_parser("finding", help="mark a finding fixed with proof")
    sp_finding.add_argument("slug")
    sp_finding.add_argument("--fixed", required=True, metavar="N", help="finding number or exact comment ID")
    sp_finding.add_argument("--proof", action="append", default=[], metavar="URL|FILE")
    sp_finding.add_argument("--note", default="")
    sp_finding.add_argument("--author", default=None)
    sp_finding.add_argument("--project", default=None)
    sp_finding.add_argument("--json", action="store_true")
    sp_finding.set_defaults(func=cmd_finding)
    sp_plan = sub.add_parser("plan", help="publish an independent plan revision")
    sp_plan.add_argument("slug")
    sp_plan.add_argument("plan_id")
    sp_plan.add_argument("--from", dest="from_file", required=True, metavar="plan.md|.html")
    sp_plan.add_argument("--title", default=None)
    sp_plan.add_argument("--label", default=None)
    sp_plan.add_argument("--project", default=None)
    sp_plan.add_argument("--json", action="store_true")
    sp_plan.set_defaults(func=cmd_plan)

    _add_new_parser(sub)   # `new` — markdown → versions/vN.html + cards.json

    sp_pub = sub.add_parser("publish", help="start server + register transport route")
    sp_pub.add_argument("slug_dir")
    sp_pub.add_argument("--exception", metavar="REASON", help="explicit reason for a second project page")
    sp_pub.add_argument("--standalone", action="store_true", help="alias for --exception standalone")
    sp_pub.add_argument("--project", default=None)
    sp_pub.add_argument("--port", type=int, default=None)
    sp_pub.add_argument(
        "--transport", default=None,
        choices=["funnel", "local", "tailscale", "cloudflare", "cloudflare_tailscale"],
    )
    sp_pub.add_argument("--hostname", default=None)
    sp_pub.add_argument("--public", action="store_true",
                        help="also add a Cloudflare route, for a reviewer outside the tailnet")
    sp_pub.add_argument("--path-prefix", default=None)
    sp_pub.add_argument(
        "--skip-js-lint",
        dest="skip_js_lint",
        action="store_true",
        default=False,
        help="EMERGENCY ONLY: skip inline JS syntax check (not recommended)",
    )
    sp_pub.add_argument(
        "--no-verify",
        dest="no_verify",
        action="store_true",
        default=False,
        help="EMERGENCY ONLY: print the URL without proving the page renders",
    )
    sp_pub.add_argument(
        "--verify-timeout",
        dest="verify_timeout",
        type=float,
        default=45.0,
        help="seconds to wait for each verification stage (default 45)",
    )
    sp_pub.set_defaults(func=cmd_publish)

    sp_unpub = sub.add_parser("unpublish", help="tear down route + stop server")
    sp_unpub.add_argument("slug", help="<slug> or exact <project>/<slug>")
    sp_unpub.add_argument("--project", default=None)
    sp_unpub.set_defaults(func=cmd_unpublish)

    sp_st = sub.add_parser("status", help="list active slugs")
    sp_st.add_argument("slug", nargs="?", default=None)
    sp_st.add_argument("--retired", action="store_true",
                       help="list retired registry entries instead")
    sp_st.set_defaults(func=cmd_status)

    sp_mig = sub.add_parser("migrate", help="legacy HTML → v2 layout")
    sp_mig.add_argument("legacy_html")
    sp_mig.add_argument("--slug", default=None)
    sp_mig.add_argument("--version", default="v1")
    sp_mig.add_argument("--label", default=None)
    sp_mig.add_argument("--copy", action="store_true", help="copy instead of move")
    sp_mig.set_defaults(func=cmd_migrate)

    sp_pv = sub.add_parser("publish-version", help="add new version + swap symlink")
    sp_pv.add_argument("slug_dir")
    sp_pv.add_argument("version")
    sp_pv.add_argument("--label", default=None)
    sp_pv.add_argument("--project", default=None)
    sp_pv.set_defaults(func=cmd_publish_version)

    sp_in = sub.add_parser("inbox", help="read this session's unseen bus events")
    sp_in.add_argument("slug", help="<slug> or <project>/<slug>")
    sp_in.add_argument("--project", default=None)
    sp_in.add_argument("--unread", action="store_true",
                       help="only events this session has not read, and advance its cursor")
    sp_in.add_argument("--json", action="store_true", help="raw events as one JSON object")
    sp_in.add_argument("--all-events", dest="all_events", action="store_true",
                       help="include bookkeeping events (seen_updated, notice_emitted, …)")
    sp_in.add_argument("--category", choices=CATEGORY_IDS)
    sp_in.set_defaults(func=cmd_inbox)

    sp_cards = sub.add_parser("cards", aliases=["open-cards"],
                              help="list decision cards and their verdicts")
    sp_cards.add_argument("slug", help="<slug> or <project>/<slug>")
    sp_cards.add_argument("--project", default=None)
    sp_cards.add_argument("--json", action="store_true")
    sp_cards.add_argument("--category", choices=CATEGORY_IDS)
    sp_cards.set_defaults(func=cmd_cards)

    sp_ask = sub.add_parser("ask", help="create/refresh decision cards from a cards.json")
    sp_ask.add_argument("slug", help="<slug> or <project>/<slug>")
    sp_ask.add_argument("--from", dest="from_file", required=True,
                        metavar="cards.json",
                        help="JSON array of {anchor_id, text, decision_request}")
    sp_ask.add_argument("--version", default=None,
                        help="bind the cards to this version (default: meta current)")
    sp_ask.add_argument("--project", default=None)
    sp_ask.add_argument("--author", default=None)
    sp_ask.add_argument("--json", action="store_true")
    sp_ask.add_argument("--category", choices=CATEGORY_IDS)
    sp_ask.add_argument("--set", metavar="ID", help="findings set (requires --category findings)")
    sp_ask.set_defaults(func=cmd_ask)

    sp_claim = sub.add_parser("claim", help="take ownership of a page for this session")
    sp_claim.add_argument("slug", help="<slug> or <project>/<slug>")
    sp_claim.add_argument("--project", default=None)
    sp_claim.set_defaults(func=cmd_claim)

    sp_close = sub.add_parser("close", help="archive decision cards nobody answered")
    sp_close.add_argument("slug", help="<slug> or <project>/<slug>")
    sp_close.add_argument("--project", default=None)
    sp_close.add_argument("--older-than", default="30d",
                          help="age threshold: 30d (default), 12h, 90m, 2w")
    sp_close.add_argument("--dry-run", action="store_true",
                          help="print the table and write nothing")
    sp_close.add_argument("--author", default=None)
    sp_close.set_defaults(func=cmd_close)

    sp_retire = sub.add_parser("retire", help="move dead registry entries to state/retired/")
    sp_retire.add_argument("slug", nargs="?", default=None,
                           help="<slug> or <project>/<slug>; omit with --dead")
    sp_retire.add_argument("--project", default=None)
    sp_retire.add_argument("--dead", action="store_true",
                           help="retire every entry whose server is gone")
    sp_retire.add_argument("--dry-run", action="store_true",
                           help="print the table and write nothing")
    sp_retire.set_defaults(func=cmd_retire)

    sp_revive = sub.add_parser(
        "revive", help="restart dead pages on their recorded port, keeping owner and route")
    sp_revive.add_argument("--dry-run", action="store_true", help="report, start nothing")
    sp_revive.add_argument("--quiet", action="store_true",
                           help="timestamped lines for changes only (launchd log)")
    sp_revive.add_argument("--install", action="store_true",
                           help="install the launchd watchdog: at login and every --interval")
    sp_revive.add_argument("--uninstall", action="store_true", help="remove the watchdog")
    sp_revive.add_argument("--interval", type=int, default=60)
    sp_revive.set_defaults(func=cmd_revive)

    sp_eval = sub.add_parser("eval", help="read-only baseline of the review loop")
    sp_eval.add_argument("--since", default=None,
                         help="recency cutoff YYYY-MM-DD (eval.py default: 2026-09-01)")
    sp_eval.add_argument("--out-dir", dest="out_dir", default=None,
                         help="where to write eval-baseline.{md,json} "
                              "(default: <state>/logs)")
    sp_eval.add_argument("--refresh-transcripts", dest="refresh_transcripts",
                         action="store_true", help="ignore the transcript scan cache")
    sp_eval.set_defaults(func=cmd_eval)

    sp_cost = sub.add_parser("cost", help="read-only token and speed cost of annotate, from transcripts")
    sp_cost.add_argument("--since", default=None, help="YYYY-MM-DD (default: 30 days ago)")
    sp_cost.add_argument("--by", default="week", help="periods: week, release, or cut dates D1,D2")
    sp_cost.add_argument("--include-dev", dest="include_dev", action="store_true",
                         help="keep sessions developing annotate itself")
    sp_cost.add_argument("--codex", action="store_true", help="also scan Codex sessions")
    sp_cost.add_argument("--root", default=None, help="Claude transcript root (default ~/.claude/projects)")
    sp_cost.add_argument("--codex-root", dest="codex_root", default=None,
                         help="Codex session root (default $CODEX_HOME/sessions)")
    sp_cost.add_argument("--json", action="store_true", help="print the per-call rows")
    sp_cost.add_argument("--estimate", default=None, metavar="model.json",
                         help='price a change: {"<sub>": {"result_tokens": N}, "<error regex>": "fixed"}')
    sp_cost.set_defaults(func=cmd_cost)

    sp_shim = sub.add_parser("install-shim", help="(re)write ~/.local/bin/annotate")
    sp_shim.add_argument("--force", action="store_true",
                         help="overwrite a file this skill did not write")
    sp_shim.set_defaults(func=cmd_install_shim)

    sp_skill = sub.add_parser("install-skill",
                              help="write a provider skill directory from the packaged skill text")
    sp_skill.add_argument("--provider", choices=["claude", "codex"], required=True)
    sp_skill.add_argument("--dest", required=True, help="the skill directory to write into")
    sp_skill.set_defaults(func=cmd_install_skill)

    sp_w = sub.add_parser("watch", help="tail comments to stdout")
    sp_w.add_argument("slug")
    sp_w.set_defaults(func=cmd_watch)

    sp_mon = sub.add_parser("monitor", help="tail actionable events and advertise an active session monitor")
    sp_mon.add_argument("slug", help="<slug> or <project>/<slug>")
    sp_mon.add_argument("--project", default=None)
    sp_mon.add_argument("--owner", default=None,
                        help="interactive session/thread label stored in the ownership lease")
    sp_mon.add_argument("--takeover", action="store_true",
                        help="explicit handoff: stop the existing monitor for this slug and claim ownership")
    sp_mon.add_argument("--provider", choices=["stdout", "codex-app-server"], default="stdout",
                        help="delivery backend; stdout is for an attached agent monitor")
    sp_mon.add_argument("--session-id", default=None,
                        help="provider session/thread id used by an automatic delivery backend")
    sp_mon.set_defaults(func=cmd_monitor)

    sp_sessions = sub.add_parser("sessions", help="list Codex sessions available for page ownership")
    sp_sessions.add_argument("--cwd", default=None, help="only list sessions with this exact working directory")
    sp_sessions.add_argument("--json", action="store_true")
    sp_sessions.set_defaults(func=cmd_sessions)

    sp_send = sub.add_parser("send", help="send one coordination message to a Codex thread")
    sp_send.add_argument("--thread", required=True)
    sp_send.add_argument("message")
    sp_send.set_defaults(func=cmd_send)

    sp_connect = sub.add_parser("connect", help="connect one page to a Codex thread in the background")
    sp_connect.add_argument("slug", help="<slug> or <project>/<slug>")
    sp_connect.add_argument("--project", default=None)
    sp_connect.add_argument("--thread", required=True)
    sp_connect.add_argument("--takeover", action="store_true")
    sp_connect.set_defaults(func=cmd_connect)

    sp_disconnect = sub.add_parser("disconnect", help="release a page monitor without stopping its server")
    sp_disconnect.add_argument("slug", help="<slug> or <project>/<slug>")
    sp_disconnect.add_argument("--project", default=None)
    sp_disconnect.set_defaults(func=cmd_disconnect)

    sp_hook = sub.add_parser("hook-check",
                             help="run the UserPromptSubmit hook in-process (reads the Claude Code payload on stdin)")
    sp_hook.set_defaults(func=cmd_hook_check)

    sp_prune = sub.add_parser("prune-bus", help="archive buses quiet for N days, with their cursors")
    sp_prune.add_argument("--days", type=int, default=30)
    sp_prune.add_argument("--apply", action="store_true", help="actually move files (default: dry run)")
    sp_prune.set_defaults(func=cmd_prune_bus)

    sp_mcp = sub.add_parser("mcp", help="run the Agent Annotate MCP server over stdio")
    sp_mcp.set_defaults(func=cmd_mcp)

    sp_arc = sub.add_parser("archive-comment", help="archive a comment")
    sp_arc.add_argument("slug")
    sp_arc.add_argument("comment_id")
    sp_arc.add_argument("--project", default=None)
    sp_arc.add_argument("--author", default=None,
                        help="author identity (overrides $ANNOTATE_AUTHOR, $CLAUDE_AGENT_ID; default agent:claude)")
    sp_arc.set_defaults(func=cmd_archive_comment)

    sp_addr = sub.add_parser("addressed", help="mark comment as addressed_by_agent")
    sp_addr.add_argument("slug")
    sp_addr.add_argument("comment_id")
    sp_addr.add_argument("--response", default=None)
    sp_addr.add_argument("--project", default=None)
    sp_addr.add_argument("--author", default=None,
                         help="author identity (overrides $ANNOTATE_AUTHOR, $CLAUDE_AGENT_ID; default agent:claude)")
    sp_addr.add_argument("--json", action="store_true", help="print the updated comment")
    sp_addr.set_defaults(func=cmd_addressed)

    sp_resolve = sub.add_parser(
        "resolve",
        help="resolve a prior-round comment in a named version and anchor",
    )
    sp_resolve.add_argument("slug", help="<slug> or <project>/<slug>")
    sp_resolve.add_argument("comment_id")
    sp_resolve.add_argument("--in-version", required=True)
    sp_resolve.add_argument("--anchor", required=True)
    sp_resolve.add_argument("--response", default=None)
    sp_resolve.add_argument("--project", default=None)
    sp_resolve.add_argument("--author", default=None)
    sp_resolve.add_argument("--json", action="store_true", help="print the updated comment")
    sp_resolve.set_defaults(func=cmd_resolve)

    sp_carry = sub.add_parser(
        "carry",
        help="carry a prior-round comment onto an anchor in a newer version",
    )
    sp_carry.add_argument("slug", help="<slug> or <project>/<slug>")
    sp_carry.add_argument("comment_id")
    sp_carry.add_argument("--to-version", required=True)
    sp_carry.add_argument("--anchor", required=True)
    sp_carry.add_argument("--project", default=None)
    sp_carry.add_argument("--author", default=None)
    sp_carry.add_argument("--json", action="store_true", help="print the updated comment")
    sp_carry.set_defaults(func=cmd_carry)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
