"""Portable filesystem locations for Agent Annotate.

Every directory can be overridden for tests, portable installs, or managed
deployments. Runtime state deliberately lives outside any agent provider's
configuration tree.
"""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_config_path, user_data_path, user_state_path

APP_NAME = "agent-annotate"
PACKAGE_DIR = Path(__file__).resolve().parent
WEB_DIR = PACKAGE_DIR / "web"
HOOKS_DIR = PACKAGE_DIR / "hooks"


def _override(name: str, fallback: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else fallback


CONFIG_DIR = _override("ANNOTATE_CONFIG_DIR", Path(user_config_path(APP_NAME)))
DATA_DIR = _override("ANNOTATE_DATA_DIR", Path(user_data_path(APP_NAME)))
STATE_DIR = _override("ANNOTATE_STATE_DIR", Path(user_state_path(APP_NAME)))

PROJECTS_TOML = CONFIG_DIR / "projects.toml"
BUS_ROOT = DATA_DIR / "bus"
MONITOR_ROOT = STATE_DIR / "monitors"
MONITOR_OFFSET_ROOT = STATE_DIR / "monitor-offsets"
LOG_DIR = STATE_DIR / "logs"
HOOK_SCRIPT = HOOKS_DIR / "check-comment-bus.sh"


def ensure_runtime_dirs() -> None:
    """Create the provider-neutral runtime directories."""

    for path in (CONFIG_DIR, DATA_DIR, STATE_DIR, BUS_ROOT, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)

