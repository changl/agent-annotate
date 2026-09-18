"""Every filesystem location Agent Annotate reads or writes, in one place.

Defaults resolve to the locations the live skill has been using since v2.11,
so a packaged install sees the same registry, buses, cursors and leases as
the skill directory it replaces:

    state    ~/.claude/annotate-state/state      registry, cursors, leases, locks, logs
    bus      ~/.claude/annotate-bus              <project>/<slug>.ndjson
    config   ~/.claude/annotate-state            projects.toml

Relocating state is a deliberate migration, never a side effect of installing
a package. Every root can be overridden:

    ANNOTATE_STATE_DIR    (alias ANNOTATE_STATE_ROOT, the test-only spelling)
    ANNOTATE_BUS_ROOT     the bus root itself
    ANNOTATE_DATA_DIR     bus root becomes <data>/bus when ANNOTATE_BUS_ROOT is unset
    ANNOTATE_CONFIG_DIR   directory holding projects.toml
    ANNOTATE_PROJECTS_TOML
    ANNOTATE_CLAUDE_SETTINGS  the settings.json the hook installer edits
    ANNOTATE_SHIM_PATH        where `install-shim` writes the launcher
    ANNOTATE_BUS_ARCHIVE_ROOT where prune-bus moves quiet buses

The hook and eval scripts are also runnable as bare files; they carry the
same defaults so the two never disagree about where a cursor lives.
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "agent-annotate"
PACKAGE_DIR = Path(__file__).resolve().parent
WEB_DIR = PACKAGE_DIR / "web"
HOOKS_DIR = PACKAGE_DIR / "hooks"

HOME = Path.home()
CLAUDE_HOME = HOME / ".claude"


def _override(names: tuple[str, ...] | str, fallback: Path) -> Path:
    if isinstance(names, str):
        names = (names,)
    for name in names:
        value = os.environ.get(name)
        if value:
            return Path(value).expanduser().resolve()
    return fallback


CONFIG_DIR = _override("ANNOTATE_CONFIG_DIR", CLAUDE_HOME / "annotate-state")
STATE_DIR = _override(("ANNOTATE_STATE_DIR", "ANNOTATE_STATE_ROOT"),
                      CLAUDE_HOME / "annotate-state" / "state")
DATA_DIR = _override("ANNOTATE_DATA_DIR", CLAUDE_HOME)
BUS_ROOT = _override(
    "ANNOTATE_BUS_ROOT",
    (DATA_DIR / "bus") if os.environ.get("ANNOTATE_DATA_DIR") else CLAUDE_HOME / "annotate-bus",
)
BUS_ARCHIVE_ROOT = _override("ANNOTATE_BUS_ARCHIVE_ROOT", CLAUDE_HOME / "annotate-bus-archive")


def _projects_toml() -> Path:
    explicit = os.environ.get("ANNOTATE_PROJECTS_TOML")
    if explicit:
        return Path(explicit).expanduser().resolve()
    candidates = [CONFIG_DIR / "projects.toml"]
    if not os.environ.get("ANNOTATE_CONFIG_DIR"):
        # The live skill kept its machine-local projects.toml beside cli.py,
        # reachable through the ~/.claude/skills/annotate symlink. Keep reading
        # it until it is moved, so a packaged install does not lose transports.
        candidates.append(CLAUDE_HOME / "skills" / "annotate" / "projects.toml")
    for c in candidates:
        if c.is_file():
            return c
    return candidates[0]


PROJECTS_TOML = _projects_toml()

MONITOR_ROOT = STATE_DIR / "monitors"
MONITOR_OFFSET_ROOT = STATE_DIR / "monitor-offsets"
BUS_OFFSET_ROOT = STATE_DIR / "bus-offsets"      # `inbox --unread`, per session
HOOK_OFFSET_ROOT = STATE_DIR / "hook-offsets"    # UserPromptSubmit hook, per session
HOOK_LOCK_ROOT = STATE_DIR / "hook-locks"
LOCK_DIR = STATE_DIR / "locks"
LOG_DIR = STATE_DIR / "logs"

HOOK_SCRIPT = HOOKS_DIR / "check-comment-bus.sh"
SETTINGS_JSON = _override("ANNOTATE_CLAUDE_SETTINGS", CLAUDE_HOME / "settings.json")
SHIM_PATH = _override("ANNOTATE_SHIM_PATH", HOME / ".local" / "bin" / "annotate")
TRANSCRIPT_GLOB = str(CLAUDE_HOME / "projects" / "*" / "*.jsonl")


def ensure_runtime_dirs() -> None:
    """Create the runtime directories the CLI writes into."""

    for path in (CONFIG_DIR, STATE_DIR, BUS_ROOT, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)
