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
    status [<slug>]                       list active slugs / health
    doctor                                validate the installation
    migrate <legacy.html>                 one-shot v1→v2 migration
    inbox <slug> [--unread] [--json]      read this session's unseen bus events
    cards <slug>                          list decision cards and their verdicts
    ask <slug> --from cards.json          create/refresh decision cards in one call
    eval [--since DATE]                   read-only baseline of the review loop
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
from pathlib import Path

from . import __version__
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
            fh.write(json.dumps(payload, ensure_ascii=False,
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
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    p = STATE_DIR / f"{project}.json"
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


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
    """Return (project, slug). Project defaults to slug_dir.parent.name."""
    slug = slug_dir.name
    project = explicit_project or slug_dir.parent.name or "default"
    return project, slug


def _project_config(project: str) -> dict:
    cfg = _load_projects_toml().get(project, {})
    cfg.setdefault("transport", "local")
    cfg.setdefault("hostname", None)
    cfg.setdefault("port_base", 8800)
    cfg.setdefault("path_prefix", None)
    return cfg


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

    # Atomic write
    tmp = SETTINGS_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, SETTINGS_JSON)
    return True, f"added UserPromptSubmit hook → {HOOK_COMMAND}"


# ────────────────────────────────────────────────────────────────────────────
# Server lifecycle
# ────────────────────────────────────────────────────────────────────────────
def _start_server(slug_dir: Path, port: int, bus_dir: Path, public_base_path: str | None) -> int:
    """Spawn sync_server.py in v2 mode. Returns PID."""
    cmd = [
        sys.executable,
        "-m",
        "agent_annotate.sync_server",
        "--slug-dir", str(slug_dir),
        "--slug", slug_dir.name,
        "--bus-dir", str(bus_dir),
        "--port", str(port),
    ]
    if public_base_path:
        cmd += ["--public-base-path", public_base_path]
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{slug_dir.name}.log"
    fh = open(log_path, "ab", buffering=0)
    proc = subprocess.Popen(
        cmd,
        stdout=fh,
        stderr=fh,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
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
    return {
        "owner_session": sid,
        "owner_agent": _session_agent(),
        "owner_label": _session_label(sid),
        "owner_claimed_at": _now_iso(),
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
    if ts is None and details.get("transport") == "tailscale":
        ts = details
    if ts and ts.get("hostname") and ts.get("https_port"):
        report.stages.append(
            probe_http("tailscale",
                       f"https://{ts['hostname']}:{ts['https_port']}{base}/",
                       timeout=hop_timeout)
        )
        if report.failed:
            return report

    url = record.get("url") or ""
    if record.get("transport") != "local" and url.startswith("https://"):
        report.stages.append(probe_browser("public", url, timeout=timeout))
    return report


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
        {"name": s.name, "status": s.status, "url": s.url, "detail": s.detail}
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

    print()
    print(f"  annotate publish — {project}/{slug}")
    print("  ─────────────────────────────────────────────")

    if report is not None and report.failed:
        stage = report.failed[0]
        _bus_emit(record.get("bus_file"), {
            "event": "page_publish_failed",
            "slug": slug,
            "stage": stage.name,
            "detail": stage.detail,
            "url": stage.url,
            "owner_session": record.get("owner_session") or _session_id(),
        })
        print("  NOT PUBLISHED — the page does not render.")
        print()
        for line in format_report(report):
            print(line)
        print()
        print(f"  Local URL:     {record['local_url']}   (server is still running)")
        print(f"  PID:           {record['pid']}")
        print(f"  Port:          {record['port']}")
        print(f"  Transport:     {record.get('transport')}")
        if record.get("transport_error"):
            print(f"  Transport err: {record['transport_error']}")
        print(f"  Slug dir:      {slug_dir}")
        print("  ─────────────────────────────────────────────")
        print(f"  No URL is printed for {slug!r}: the {report.failed[0].name} stage failed.")
        print(f"  Fix that stage and re-run `{_inv()} publish {slug_dir}`, or")
        print(f"  `{_inv()} unpublish {slug}` to tear the whole thing down.")
        print()
        return 1

    if headline:
        print(f"  {headline}")
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
            print("                 The URL below is live for an authenticated reviewer;")
            print("                 open it in the authenticated browser to confirm.")
        if len(access) < len(report.unavailable):
            print("  UNVERIFIED     could not reach the authenticated browser — the public")
            print("                 URL below is UNCONFIRMED, not known-good")

    print(f"  URL:           {record['url']}")
    print(f"  Local URL:     {record['local_url']}")
    print(f"  PID:           {record['pid']}")
    print(f"  Port:          {record['port']}")
    print(f"  Transport:     {record.get('transport')}")
    if record.get("transport_error"):
        print(f"  Transport err: {record['transport_error']}")
    print(f"  Slug dir:      {slug_dir}")
    print(f"  NDJSON bus:    {record.get('bus_file')}")
    print(f"  State file:    {STATE_DIR / (project + '.json')}")
    if report is not None:
        print("  ─────────────────────────────────────────────")
        for line in format_report(report):
            print(line)
    print("  ─────────────────────────────────────────────")
    if record.get("owner_label"):
        print(f"  Owner:         {record['owner_label']}  "
              f"(session {record.get('owner_session')})")
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
        "url": record.get("url"),
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
    started_at = time.monotonic()
    slug_dir = Path(args.slug_dir).resolve()
    if not slug_dir.exists() or not slug_dir.is_dir():
        print(f"ERROR: slug-dir not found or not a directory: {slug_dir}", file=sys.stderr)
        return 2
    project, slug = _slug_project(slug_dir, args.project)
    cfg = _project_config(project)

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
                port = _find_free_port_after(int(port_base), registered_pid=registered_pid)

            bus_dir = BUS_ROOT / project
            bus_dir.mkdir(parents=True, exist_ok=True)

            # Transport: publish (insert public route)
            transport_name = args.transport or cfg.get("transport", "local")
            hostname = args.hostname or cfg.get("hostname")
            path_prefix = args.path_prefix or cfg.get("path_prefix") or f"/{slug}"
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
                    opts = {}
                    if hostname:
                        opts["hostname"] = hostname
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
            record = {
                "slug": slug,
                "slug_dir": str(slug_dir),
                "project": project,
                "pid": pid,
                "port": port,
                "transport": transport_name,
                "public_base_path": pbp or None,
                "url": transport_url or f"http://localhost:{port}/",
                "local_url": f"http://localhost:{port}/",
                "bus_file": str(bus_dir / f"{slug}.ndjson"),
                "started_at": _now_iso(),
                "transport_details": transport_details,
                "transport_error": transport_error,
                **_owner_fields(),
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
    slug = args.slug
    # Locate the state file that owns this slug
    record = None
    project = None
    for sf in _all_state_files():
        st = json.loads(sf.read_text(encoding="utf-8"))
        if slug in st.get("slugs", {}):
            record = st["slugs"][slug]
            project = st["project"]
            break
    if not record:
        print(f"ERROR: no state record for slug {slug!r}", file=sys.stderr)
        return 2

    # Stop server
    pid = record.get("pid", 0)
    stopped = _stop_server(pid)
    print(f"  Server pid={pid} {'stopped' if stopped else 'not running'}")

    # Transport teardown
    transport_name = record.get("transport", "local")
    pbp = (record.get("public_base_path") or "").lstrip("/")
    if transport_name != "local" and pbp:
        try:
            from .transports import load as _load_transport
            tmod = _load_transport(transport_name)
            details = record.get("transport_details", {}) or {}
            opts = {}
            host = details.get("hostname")
            if host:
                opts["hostname"] = host
            # A tailscale serve mapping is addressed by port, not by slug: pass
            # both the recorded serve port and the local port so teardown can
            # identify the mapping and refuse to remove a recycled one.
            if record.get("port"):
                opts["port"] = record["port"]
            https_port = details.get("https_port") or \
                (details.get("tailscale") or {}).get("https_port")
            if https_port:
                opts["https_port"] = https_port
            with _flock(_tunnel_lock_path()):
                r = tmod.unpublish(pbp, **opts)
            print(f"  Transport {transport_name}: {r.get('details', {}).get('action', 'ok')}")
        except NotImplementedError as e:
            print(f"WARN: transport {transport_name}: {e}", file=sys.stderr)
        except TimeoutError as e:
            print(f"WARN: transport {transport_name} unpublish skipped: {e}", file=sys.stderr)
        except Exception as e:
            print(f"WARN: transport {transport_name} unpublish failed: {e}", file=sys.stderr)

    # Remove from state
    try:
        with _flock(_state_lock_path(project)):
            state = _load_state_for_project(project)
            state["slugs"].pop(slug, None)
            _save_state_for_project(project, state)
    except TimeoutError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 4
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


def cmd_status(args) -> int:
    rows = []
    live = _running_servers()
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
            rows.append((project, slug, pid, port, rec.get("url"), state))
    if not rows:
        print("(no active slugs)")
        return 0
    print(f"  {'PROJECT':<15} {'SLUG':<24} {'PID':<8} {'PORT':<6} {'STATE':<7} URL")
    print(f"  {'-'*15} {'-'*24} {'-'*8} {'-'*6} {'-'*7} {'-'*40}")
    for project, slug, pid, port, url, state in rows:
        print(f"  {project[:15]:<15} {slug[:24]:<24} {pid!s:<8} {port!s:<6} {state:<7} {url}")
    if any(r[5] == "alive*" for r in rows):
        print("\n  alive* = serving, but the state file's pid is stale (restarted "
              "outside the CLI). Re-publish to refresh the registry.")
    if any(r[5] == "dup" for r in rows):
        print("\n  dup    = several live servers share this slug_dir. They will fight "
              "over comments.json; stop the ones you did not intend.")
    return 0


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

    resolved = _resolve_slug(slug_dir.name, getattr(args, "project", None))
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
    return "  %-20s %-17s %-10s %-18s %-24s %-9s %s" % (
        ev.get("ts") or "",
        (ev.get("event") or "")[:17],
        (ev.get("comment_id") or "")[:10],
        (ev.get("anchor_id") or "")[:18],
        (str(ev.get("author") or ev.get("by") or ""))[:24],
        str(verdict)[:9],
        _clip(text, 120),
    )


def cmd_inbox(args) -> int:
    resolved = _resolve_slug(args.slug, getattr(args, "project", None))
    if not resolved:
        return 2
    project, slug, record = resolved
    session_id = _session_id()
    bus_file = Path(record.get("bus_file") or (BUS_ROOT / project / f"{slug}.ndjson"))
    offset_file = _offset_file(project, slug, session_id)
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
        e for e in events if e.get("event") not in _INBOX_HIDDEN]
    store = _load_store(record)
    texts = _comment_texts(store)
    cards = _decision_cards(store)
    counts = _verdict_counts(cards)
    undecided = [c["anchor_id"] or c["id"] for c in cards if not c["verdict"]]

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
        }, ensure_ascii=False, indent=2))
    else:
        if not shown:
            print("(no new events)" if args.unread else "(no events)")
        for ev in shown:
            print(_inbox_line(ev, texts))
        if cards:
            print("  decisions: %d accept, %d reject, %d comment; undecided: %s"
                  % (counts["accept"], counts["reject"], counts["comment"],
                     ", ".join(undecided) if undecided else "none"))

    if args.unread and new_offset > offset:
        _bus_emit(bus_file, {
            "event": "inbox_read",
            "slug": slug,
            "session_id": session_id,
            "offset_from": offset,
            "offset_to": new_offset,
            "event_count": len(shown),
        })
        try:
            new_offset = bus_file.stat().st_size
        except OSError:
            pass
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
    cards = _decision_cards(_load_store(record))
    if getattr(args, "json", False):
        print(json.dumps(cards, ensure_ascii=False, indent=2))
        return 0
    if not cards:
        print(f"  {project}/{slug}: no decision cards "
              f"(create some with `{_inv()} ask {slug} --from cards.json`)")
        return 0
    print(f"  {project}/{slug} — {len(cards)} decision card(s)")
    print("  %-12s %-20s %-6s %-9s %s" % ("id", "anchor", "ver", "verdict", "prompt"))
    for c in cards:
        verdict = c["verdict"] or ("pending" if c["pending"] else "—")
        line = "  %-12s %-20s %-6s %-9s %s" % (
            c["id"][:12], (c["anchor_id"] or "")[:20], c["version"][:6],
            verdict, _clip(c["prompt"], 64))
        if c["verdict_text"]:
            line += f'  “{_clip(c["verdict_text"], 48)}”'
        print(line)
    counts = _verdict_counts(cards)
    undecided = [c["anchor_id"] or c["id"] for c in cards if not c["verdict"]]
    print("  decisions: %d accept, %d reject, %d comment; undecided: %s"
          % (counts["accept"], counts["reject"], counts["comment"],
             ", ".join(undecided) if undecided else "none"))
    return 0


def _ask_fallback(record: dict, slug: str, items: list, author: str) -> tuple[list, int, int]:
    """Create the cards one at a time on a server without the batch route.

    Keeps the same anchor-idempotency contract: an existing non-archived card
    by this author on the same anchor is updated, not duplicated.
    """
    code, existing = _api(record, "GET", "/api/comments", None, author)
    by_anchor: dict = {}
    if code == 200 and isinstance(existing, list):
        for c in existing:
            if not isinstance(c, dict) or c.get("status") == "archived":
                continue
            if c.get("author") != author or not c.get("decision_request"):
                continue
            by_anchor.setdefault(c.get("anchor_id"), c)

    ids, created, updated = [], 0, 0
    for item in items:
        prior = by_anchor.get(item["anchor_id"])
        if prior:
            body = {"text": item["text"]}
            if "decision_request" in item:
                body["decision_request"] = item["decision_request"]
            code, payload = _api(record, "PUT", f"/api/comments/{prior['id']}",
                                 body, author)
            if code >= 400 or code == 0:
                raise RuntimeError(f"PUT {prior['id']} → HTTP {code}: {payload}")
            ids.append(prior["id"])
            updated += 1
            continue
        code, payload = _api(record, "POST", "/api/comments", item, author)
        if code >= 400 or code == 0 or not isinstance(payload, dict):
            raise RuntimeError(f"POST {item['anchor_id']} → HTTP {code}: {payload}")
        cid = payload.get("id")
        ids.append(cid)
        created += 1
        # A 2.19 server stores decision_request on create; an older one ignores
        # it, so the card needs the PUT that used to be mandatory.
        if item.get("decision_request") and not payload.get("decision_request"):
            code, payload = _api(record, "PUT", f"/api/comments/{cid}",
                                 {"decision_request": item["decision_request"]}, author)
            if code >= 400 or code == 0:
                raise RuntimeError(f"PUT {cid} (decision_request) → HTTP {code}: {payload}")
    return ids, created, updated


def cmd_ask(args) -> int:
    """Post a whole round of decision cards from one cards.json."""
    resolved = _resolve_slug(args.slug, getattr(args, "project", None))
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
        if c.get("anchor_label"):
            item["anchor_label"] = c["anchor_label"]
        if dr:
            item["decision_request"] = dr
        items.append(item)

    author = _resolve_author(getattr(args, "author", None))
    route = "batch"
    code, payload = _api(record, "POST", "/api/comments/batch",
                         {"items": items, "idempotency": "anchor"}, author)
    if code in (404, 405, 501):
        print(f"  batch route absent (HTTP {code}) — falling back to per-card POST + PUT")
        route = "fallback"
        try:
            ids, created, updated = _ask_fallback(record, slug, items, author)
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
    elif code == 0:
        print(f"ERROR: no server answering for {project}/{slug}: {payload}\n"
              f"  Start it with `{_inv()} publish {record.get('slug_dir', '<slug-dir>')}`",
              file=sys.stderr)
        return 2
    elif code >= 400 or not isinstance(payload, dict):
        print(f"ERROR: batch create failed (HTTP {code}): {payload}", file=sys.stderr)
        return 2
    else:
        ids = payload.get("ids") or []
        created = int(payload.get("created") or 0)
        updated = int(payload.get("updated") or 0)

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
        f"{v.get('comment', 0)} comment, {v.get('none', 0)} undecided",
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


def cmd_claim(args) -> int:
    """Take ownership of a page for this session, without a monitor.

    The hook only notifies the owning session; a handoff (or a page published
    before ownership existed) needs a way to say "this one is mine now".
    """
    resolved = _resolve_slug(args.slug, getattr(args, "project", None))
    if not resolved:
        return 2
    project, slug, record = resolved
    prior = record.get("owner_session")
    fields = _owner_fields()
    err = _stamp_owner_in_registry(project, slug, fields)
    if err:
        print(f"ERROR: could not claim {project}/{slug}: {err}", file=sys.stderr)
        return 2
    if record.get("slug_dir"):
        meta_err = _write_owner_meta(Path(record["slug_dir"]), fields)
        if meta_err:
            print(f"WARN: owner chip not updated: {meta_err}", file=sys.stderr)
    print(f"  {project}/{slug} claimed by {fields['owner_label']} "
          f"(session {fields['owner_session']})")
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
    resolved = _resolve_slug(args.slug, getattr(args, "project", None))
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

    offset_file = MONITOR_OFFSET_ROOT / project / f"{slug}.offset"
    offset_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        offset = int(offset_file.read_text(encoding="utf-8").strip()) if offset_file.exists() else bus_file.stat().st_size
    except Exception:
        offset = bus_file.stat().st_size

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
                if provider_name == "codex-app-server" and ev.get("event") == "session_push":
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


def _comment_call(args, method: str, path: str, body: dict) -> int:
    resolved = _resolve_slug(args.slug, getattr(args, "project", None))
    if not resolved:
        return 2
    _project, _slug, record = resolved
    author = _resolve_author(getattr(args, "author", None))
    code, payload = _api(record, method, path, body, author)
    if code == 0 or code >= 400:
        print(f"ERROR: {method} {path} → HTTP {code}: {payload}", file=sys.stderr)
        return 2
    print(json.dumps(payload, ensure_ascii=False) if payload is not None else "ok")
    return 0


def cmd_archive_comment(args) -> int:
    return _comment_call(args, "POST", f"/api/comments/{args.comment_id}/archive", {})


def cmd_addressed(args) -> int:
    body = {"status": "addressed_by_agent"}
    if args.response:
        body["response_text"] = args.response
    return _comment_call(args, "PUT", f"/api/comments/{args.comment_id}", body)


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


# ────────────────────────────────────────────────────────────────────────────
# comments.json — the one place its shape is decoded
# ────────────────────────────────────────────────────────────────────────────
def _load_store(record: dict) -> dict:
    """Read a slug's comment store.

    The shape is {"schema_version":…, "anchors": {anchor_id: [comment, …]},
    "archived": […]}. Every observed first-attempt parse reached for
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
    return {"anchors": anchors, "archived": archived if isinstance(archived, list) else []}


def _iter_comments(store: dict):
    for anchor_id, items in (store.get("anchors") or {}).items():
        if isinstance(items, list):
            for c in items:
                if isinstance(c, dict):
                    yield anchor_id, c


def _decision_cards(store: dict) -> list[dict]:
    """Every live decision card, flattened for printing."""
    cards = []
    for anchor_id, c in _iter_comments(store):
        dr = c.get("decision_request")
        if not isinstance(dr, dict) or c.get("status") == "archived":
            continue
        d = c.get("decision") if isinstance(c.get("decision"), dict) else {}
        cards.append({
            "id": c.get("id") or "?",
            "anchor_id": c.get("anchor_id") or anchor_id,
            "prompt": dr.get("prompt") or c.get("text") or "",
            "verdict": d.get("verdict"),
            "verdict_text": d.get("text") or "",
            "pending": bool(d.get("round_pending")),
            "by": d.get("by") or "",
            "decided_at": d.get("ts") or "",
            "version": c.get("version") or "",
            "status": c.get("status") or "",
        })
    return sorted(cards, key=lambda c: (c["anchor_id"], c["id"]))


def _verdict_counts(cards: list[dict]) -> dict:
    counts = {"accept": 0, "reject": 0, "comment": 0}
    for c in cards:
        if c["verdict"] in counts:
            counts[c["verdict"]] += 1
    return counts


def _api(record: dict, method: str, path: str, body, author: str,
         timeout: float = 15.0) -> tuple[int, object]:
    """One local API call against a running server. Returns (status, parsed).

    Status 0 means the request never reached a server; the payload is then the
    error string.
    """
    base = (record.get("local_url") or "").rstrip("/")
    pbp = record.get("public_base_path") or ""
    url = f"{base}{pbp}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, method=method, data=data, headers={
        "Content-Type": "application/json",
        "Cf-Access-Authenticated-User-Email": author,
        "X-Annotate-Session": _session_id(),
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            code = resp.status
    except urllib.error.HTTPError as e:
        code = e.code
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"
    if not raw.strip():
        return code, None
    try:
        return code, json.loads(raw)
    except ValueError:
        return code, raw


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
    page_url = record.get("url") or record.get("local_url")
    counts = ev.get("verdict_counts") if isinstance(ev.get("verdict_counts"), dict) else None
    tally = (" Verdicts: " + ", ".join(f"{k} {v}" for k, v in counts.items() if v) + "."
             if counts else "")
    message = (
        f"[Agent Annotate] The reviewer pushed {count} feedback item(s) from "
        f"{project}/{slug} to this session. Page: {page_url}. "
        f"Comment IDs: {comment_ids}.{tally} Run `{_inv()} inbox {slug} --unread`, "
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
        ("projects_toml", True, str(PROJECTS_TOML) + ("" if PROJECTS_TOML.is_file() else "   (absent; local transport only)")),
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
    resolved = _resolve_slug(args.slug, getattr(args, "project", None))
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
    resolved = _resolve_slug(args.slug, getattr(args, "project", None))
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
    sp_doc.set_defaults(func=cmd_doctor)

    sp_pub = sub.add_parser("publish", help="start server + register transport route")
    sp_pub.add_argument("slug_dir")
    sp_pub.add_argument("--project", default=None)
    sp_pub.add_argument("--port", type=int, default=None)
    sp_pub.add_argument(
        "--transport", default=None,
        choices=["local", "cloudflare", "tailscale", "cloudflare_tailscale"],
    )
    sp_pub.add_argument("--hostname", default=None)
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
    sp_unpub.add_argument("slug")
    sp_unpub.set_defaults(func=cmd_unpublish)

    sp_st = sub.add_parser("status", help="list active slugs")
    sp_st.add_argument("slug", nargs="?", default=None)
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
    sp_in.set_defaults(func=cmd_inbox)

    sp_cards = sub.add_parser("cards", aliases=["open-cards"],
                              help="list decision cards and their verdicts")
    sp_cards.add_argument("slug", help="<slug> or <project>/<slug>")
    sp_cards.add_argument("--project", default=None)
    sp_cards.add_argument("--json", action="store_true")
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
    sp_ask.set_defaults(func=cmd_ask)

    sp_claim = sub.add_parser("claim", help="take ownership of a page for this session")
    sp_claim.add_argument("slug", help="<slug> or <project>/<slug>")
    sp_claim.add_argument("--project", default=None)
    sp_claim.set_defaults(func=cmd_claim)

    sp_eval = sub.add_parser("eval", help="read-only baseline of the review loop")
    sp_eval.add_argument("--since", default=None,
                         help="recency cutoff YYYY-MM-DD (eval.py default: 2026-09-01)")
    sp_eval.add_argument("--out-dir", dest="out_dir", default=None,
                         help="where to write eval-baseline.{md,json} "
                              "(default: <state>/logs)")
    sp_eval.add_argument("--refresh-transcripts", dest="refresh_transcripts",
                         action="store_true", help="ignore the transcript scan cache")
    sp_eval.set_defaults(func=cmd_eval)

    sp_shim = sub.add_parser("install-shim", help="(re)write ~/.local/bin/annotate")
    sp_shim.add_argument("--force", action="store_true",
                         help="overwrite a file this skill did not write")
    sp_shim.set_defaults(func=cmd_install_shim)

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
    sp_addr.set_defaults(func=cmd_addressed)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
