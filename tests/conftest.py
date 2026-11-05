"""Keep the suite off the machine's live annotate estate.

paths.py defaults to the live roots on purpose (~/.claude/annotate-state,
~/.claude/annotate-bus, ~/.claude/settings.json, ~/.local/bin/annotate). A test
that publishes, arms a monitor or answers a decision would otherwise write a
cursor, a lease or a shim into the same tree eighteen live pages depend on.
The overrides are exported before the package is imported so every module
that binds a root at import time sees the sandbox.
"""

import os
import subprocess
import tempfile
from pathlib import Path

_SANDBOX = Path(tempfile.mkdtemp(prefix="agent-annotate-tests-"))
_SANDBOX_ENV = {
    "ANNOTATE_STATE_DIR": _SANDBOX / "state",
    "ANNOTATE_BUS_ROOT": _SANDBOX / "bus",
    "ANNOTATE_CONFIG_DIR": _SANDBOX / "config",
    "ANNOTATE_DATA_DIR": _SANDBOX / "data",
    "ANNOTATE_CLAUDE_SETTINGS": _SANDBOX / "claude" / "settings.json",
    "ANNOTATE_CODEX_HOOKS": _SANDBOX / "codex" / "hooks.json",
    "ANNOTATE_SHIM_PATH": _SANDBOX / "bin" / "annotate",
    "ANNOTATE_BUS_ARCHIVE_ROOT": _SANDBOX / "bus-archive",
    "ANNOTATE_TRANSCRIPT_GLOB": _SANDBOX / "no-transcripts" / "*.jsonl",
    "ANNOTATE_SKILL_DIRS": _SANDBOX / "skills" / "annotate",
    "ANNOTATE_CODEX_PLUGIN_CACHE": _SANDBOX / "codex" / "plugins" / "cache",
}
for _name, _path in _SANDBOX_ENV.items():
    os.environ[_name] = str(_path)
# `annotate` on PATH is machine estate; the version-guard tests turn this back on.
os.environ["ANNOTATE_VERSION_GUARD"] = "0"
# The live board (Bead Me Up Scotty, bd) is machine estate too; board tests use a fake bd.
os.environ["ANNOTATE_BOARD_API"] = "http://127.0.0.1:9"
os.environ.pop("ANNOTATE_BD", None)
(_SANDBOX / "config").mkdir(parents=True)
(_SANDBOX / "config" / "projects.toml").write_text('[defaults]\ntransport = "local"\nport_base = 18700\n')
os.environ.pop("ANNOTATE_STATE_ROOT", None)
os.environ.pop("ANNOTATE_PROJECTS_TOML", None)
# A real session id would make the CLI stamp this developer's session into
# sandbox records; the tests set their own where it matters.
for _name in ("CLAUDE_CODE_SESSION_ID", "CODEX_THREAD_ID", "CLAUDE_SESSION_ID",
              "ANNOTATE_SESSION_ID", "ANNOTATE_HOOK_ALL", "ANNOTATE_HOOK_DRY_RUN"):
    os.environ.pop(_name, None)
os.environ.pop("ORCA_TERMINAL_HANDLE", None)

import pytest  # noqa: E402

from agent_annotate import paths  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _stop_test_servers(tmp_path_factory):
    """Publish integration tests may detach servers; reap only this suite's estate."""
    roots = (tmp_path_factory.getbasetemp().resolve(), _SANDBOX.resolve())
    yield
    from agent_annotate import cli
    for directory, servers in cli._running_servers(strict=True).items():
        if any(Path(directory).resolve().is_relative_to(root) for root in roots):
            for server in servers:
                cli._stop_server(server["pid"])


@pytest.fixture(autouse=True)
def _assert_sandboxed(monkeypatch):
    """Fail loudly if a reload or a test ever points the package at $HOME."""
    from agent_annotate import delivery
    monkeypatch.setattr(delivery, "_parent_handle", lambda expected: None)
    original_run = subprocess.run
    original_popen = subprocess.Popen
    def safe_popen(command, *args, **kwargs):
        if (isinstance(command, (list, tuple)) and "agent_annotate.sync_server" in command
                and "--port" in command):
            port = int(command[command.index("--port") + 1])
            assert not 8800 <= port < 8900, f"test server port is in the live range: {port}"
        return original_popen(command, *args, **kwargs)
    def safe_run(command, *args, **kwargs):
        if isinstance(command, (list, tuple)) and command and Path(str(command[0])).name.lower() == "tailscale":
            raise FileNotFoundError("Tests must mock Tailscale; live routes are off limits")
        return original_run(command, *args, **kwargs)
    monkeypatch.setattr(subprocess, "run", safe_run)
    monkeypatch.setattr(subprocess, "Popen", safe_popen)
    yield
    for name in ("STATE_DIR", "BUS_ROOT", "SETTINGS_JSON", "SHIM_PATH"):
        value = str(getattr(paths, name))
        assert str(_SANDBOX) in value, f"paths.{name} escaped the test sandbox: {value}"


if os.environ.get("ANNOTATE_TEST_SQLITE"):
    # Stage 5c check (tests/test_store_sqlite.py runs it): every page a test
    # touches is imported into page.db first, so the suite runs on SQLite.
    from agent_annotate import store as _store

    _plain_backend = _store.backend

    def _forced_backend(slug_dir):
        directory = Path(slug_dir)
        if (_plain_backend(directory) == "json" and (directory / "comments.json").is_file()
                and os.access(directory, os.W_OK) and not any(directory.glob("page.db*"))):
            try:
                _store.import_page(directory)
            except (OSError, ValueError):
                return "json"
        return _plain_backend(directory)

    _store.backend = _forced_backend
