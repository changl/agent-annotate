"""Filesystem locations are owned by paths.py and default to the live roots.

The 18 slugs published by the skill-directory install live under
~/.claude/annotate-state/state and ~/.claude/annotate-bus. A packaged install
must see exactly those unless an ANNOTATE_* override says otherwise; moving
state is a migration, not a side effect of `uv tool install`.
"""

import importlib
import sys
from pathlib import Path

import pytest

from agent_annotate import paths
from agent_annotate.cli import _slug_project

_OVERRIDES = (
    "ANNOTATE_CONFIG_DIR", "ANNOTATE_DATA_DIR", "ANNOTATE_STATE_DIR",
    "ANNOTATE_STATE_ROOT", "ANNOTATE_BUS_ROOT", "ANNOTATE_PROJECTS_TOML",
    "ANNOTATE_CLAUDE_SETTINGS", "ANNOTATE_SHIM_PATH", "ANNOTATE_BUS_ARCHIVE_ROOT",
)


@pytest.fixture
def reload_paths(monkeypatch):
    """Reload paths.py under a chosen environment, then put it back."""

    def _reload(**env):
        for name in _OVERRIDES:
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, str(value))
        return importlib.reload(sys.modules["agent_annotate.paths"])

    try:
        yield _reload
    finally:
        monkeypatch.undo()
        importlib.reload(sys.modules["agent_annotate.paths"])


def test_web_assets_are_packaged():
    for filename in ("shell.html", "shell.js", "shell.css", "adapter.js", "template.html",
                     "diagram-plot.js"):
        assert (paths.WEB_DIR / filename).is_file()


def test_hook_scripts_are_packaged():
    assert (paths.HOOKS_DIR / "check-comment-bus.sh").is_file()
    assert (paths.HOOKS_DIR / "check_comment_bus.py").is_file()


def test_defaults_resolve_to_the_live_roots(reload_paths):
    p = reload_paths()
    home = Path.home()
    assert p.STATE_DIR == home / ".claude" / "annotate-state" / "state"
    assert p.BUS_ROOT == home / ".claude" / "annotate-bus"
    assert p.BUS_OFFSET_ROOT == p.STATE_DIR / "bus-offsets"
    assert p.HOOK_OFFSET_ROOT == p.STATE_DIR / "hook-offsets"
    assert p.MONITOR_ROOT == p.STATE_DIR / "monitors"
    assert p.SETTINGS_JSON == home / ".claude" / "settings.json"
    assert p.SHIM_PATH == home / ".local" / "bin" / "annotate"


def test_every_root_honours_its_override(reload_paths, tmp_path):
    p = reload_paths(
        ANNOTATE_STATE_DIR=tmp_path / "st",
        ANNOTATE_BUS_ROOT=tmp_path / "bus",
        ANNOTATE_CONFIG_DIR=tmp_path / "cfg",
        ANNOTATE_CLAUDE_SETTINGS=tmp_path / "settings.json",
        ANNOTATE_SHIM_PATH=tmp_path / "bin" / "annotate",
    )
    assert p.STATE_DIR == (tmp_path / "st").resolve()
    assert p.BUS_ROOT == (tmp_path / "bus").resolve()
    assert p.PROJECTS_TOML == (tmp_path / "cfg" / "projects.toml").resolve()
    assert p.SETTINGS_JSON == (tmp_path / "settings.json").resolve()
    assert p.SHIM_PATH == (tmp_path / "bin" / "annotate").resolve()
    assert p.LOCK_DIR == p.STATE_DIR / "locks"


def test_state_root_is_the_test_spelling_of_state_dir(reload_paths, tmp_path):
    """The live hook and QA scripts use ANNOTATE_STATE_ROOT; both must work."""
    p = reload_paths(ANNOTATE_STATE_ROOT=tmp_path / "root")
    assert p.STATE_DIR == (tmp_path / "root").resolve()


def test_data_dir_relocates_the_bus_when_no_bus_root_is_given(reload_paths, tmp_path):
    p = reload_paths(ANNOTATE_DATA_DIR=tmp_path / "data")
    assert p.BUS_ROOT == (tmp_path / "data" / "bus").resolve()


def test_explicit_project_does_not_rename_slug(tmp_path):
    project, slug = _slug_project(tmp_path / "review-page", "portfolio")
    assert project == "portfolio"
    assert slug == "review-page"
