"""Keep the suite off the machine's live annotate estate.

paths.py defaults to the live roots on purpose (~/.claude/annotate-state,
~/.claude/annotate-bus, ~/.claude/settings.json, ~/.local/bin/annotate). A test
that publishes, arms a monitor or answers a decision would otherwise write a
cursor, a lease or a shim into the same tree eighteen live pages depend on.
The overrides are exported before the package is imported so every module
that binds a root at import time sees the sandbox.
"""

import os
import tempfile
from pathlib import Path

_SANDBOX = Path(tempfile.mkdtemp(prefix="agent-annotate-tests-"))
_SANDBOX_ENV = {
    "ANNOTATE_STATE_DIR": _SANDBOX / "state",
    "ANNOTATE_BUS_ROOT": _SANDBOX / "bus",
    "ANNOTATE_CONFIG_DIR": _SANDBOX / "config",
    "ANNOTATE_DATA_DIR": _SANDBOX / "data",
    "ANNOTATE_CLAUDE_SETTINGS": _SANDBOX / "claude" / "settings.json",
    "ANNOTATE_SHIM_PATH": _SANDBOX / "bin" / "annotate",
    "ANNOTATE_BUS_ARCHIVE_ROOT": _SANDBOX / "bus-archive",
    "ANNOTATE_TRANSCRIPT_GLOB": _SANDBOX / "no-transcripts" / "*.jsonl",
}
for _name, _path in _SANDBOX_ENV.items():
    os.environ[_name] = str(_path)
os.environ.pop("ANNOTATE_STATE_ROOT", None)
os.environ.pop("ANNOTATE_PROJECTS_TOML", None)
# A real session id would make the CLI stamp this developer's session into
# sandbox records; the tests set their own where it matters.
for _name in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "CLAUDE_SESSION_ID",
              "ANNOTATE_SESSION_ID", "ANNOTATE_HOOK_ALL", "ANNOTATE_HOOK_DRY_RUN"):
    os.environ.pop(_name, None)

import pytest  # noqa: E402

from agent_annotate import paths  # noqa: E402


@pytest.fixture(autouse=True)
def _assert_sandboxed():
    """Fail loudly if a reload or a test ever points the package at $HOME."""
    yield
    for name in ("STATE_DIR", "BUS_ROOT", "SETTINGS_JSON", "SHIM_PATH"):
        value = str(getattr(paths, name))
        assert str(_SANDBOX) in value, f"paths.{name} escaped the test sandbox: {value}"
