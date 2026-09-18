"""The `annotate` launcher is written into a sandbox HOME, never over
something this package did not write, and never over a real entry point.
"""

import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from agent_annotate import cli


@pytest.fixture
def home(tmp_path, monkeypatch):
    shim = tmp_path / "home" / ".local" / "bin" / "annotate"
    monkeypatch.setattr(cli, "SHIM_PATH", shim)
    monkeypatch.setattr(cli, "_INV_CACHE", None)
    return shim


def test_install_writes_an_executable_shim_that_runs_this_package(home):
    changed, msg = cli._ensure_shim_installed()
    assert changed and "wrote" in msg
    body = home.read_text()
    assert body.startswith("#!/bin/sh")
    assert cli.SHIM_MARKER in body
    assert "-m agent_annotate.cli" in body
    assert os.access(home, os.X_OK)

    proc = subprocess.run([str(home), "--version"], capture_output=True, text=True,
                          env={**os.environ, "PATH": os.environ.get("PATH", "")})
    assert proc.returncode == 0
    assert proc.stdout.strip().startswith("agent-annotate ")


def test_install_is_idempotent(home):
    cli._ensure_shim_installed()
    changed, msg = cli._ensure_shim_installed()
    assert not changed and "already current" in msg


def test_a_foreign_file_is_left_alone_unless_forced(home):
    home.parent.mkdir(parents=True)
    home.write_text("#!/bin/sh\necho libgd\n")
    changed, msg = cli._ensure_shim_installed()
    assert not changed and "left alone" in msg
    assert home.read_text() == "#!/bin/sh\necho libgd\n"
    changed, _ = cli._ensure_shim_installed(force=True)
    assert changed and cli.SHIM_MARKER in home.read_text()


def test_a_console_script_entry_point_is_never_overwritten(home):
    """`uv tool install` puts its own launcher here; it already runs us."""
    home.parent.mkdir(parents=True)
    entry = "#!/usr/bin/python\nfrom agent_annotate.cli import main\nmain()\n"
    home.write_text(entry)
    changed, msg = cli._ensure_shim_installed(refresh=True)
    assert not changed and "entry point" in msg
    assert home.read_text() == entry


def test_publish_leaves_a_live_shim_of_another_install_but_install_shim_repoints_it(home, tmp_path):
    """The skill-directory shim points at a cli.py that still exists. `publish`
    must not silently redirect every session; the explicit command may."""
    other = tmp_path / "other" / "cli.py"
    other.parent.mkdir(parents=True)
    other.write_text("print('other')\n")
    home.parent.mkdir(parents=True)
    home.write_text(f"#!/bin/sh\n# {cli.SHIM_MARKER}\nexec python3 \"{other}\" \"$@\"\n")

    changed, msg = cli._ensure_shim_installed()
    assert not changed and "different annotate install" in msg

    assert cli.cmd_install_shim(SimpleNamespace(force=False)) == 0
    assert "-m agent_annotate.cli" in home.read_text()


def test_a_shim_whose_target_is_gone_is_rewritten_by_publish(home):
    home.parent.mkdir(parents=True)
    home.write_text(f"#!/bin/sh\n# {cli.SHIM_MARKER}\nexec python3 \"/nonexistent/cli.py\" \"$@\"\n")
    changed, _ = cli._ensure_shim_installed()
    assert changed and "-m agent_annotate.cli" in home.read_text()


def test_invocation_names_annotate_only_when_path_resolves_to_us(home, monkeypatch, tmp_path):
    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir()
    libgd = fake_bin / "annotate"
    libgd.write_text("#!/bin/sh\necho 'Usage: annotate imagein.jpg'\n")
    libgd.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin))
    monkeypatch.setattr(cli, "_INV_CACHE", None)
    assert cli._inv() == f"{sys.executable} -m agent_annotate.cli"

    cli._ensure_shim_installed()
    monkeypatch.setenv("PATH", f"{home.parent}:{fake_bin}")
    monkeypatch.setattr(cli, "_INV_CACHE", None)
    assert cli._inv() == "annotate"


def test_hook_installer_recognises_an_existing_equivalent_entry(tmp_path, monkeypatch):
    settings = tmp_path / "settings.json"
    settings.write_text('{"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", '
                        '"command": "/Users/someone/skills/annotate/hooks/check-comment-bus.sh"}]}]}}')
    monkeypatch.setattr(cli, "SETTINGS_JSON", settings)
    added, msg = cli._ensure_hook_installed()
    assert not added and "already present" in msg

    settings.write_text('{"hooks": {}}')
    added, msg = cli._ensure_hook_installed()
    assert added
    import json
    hooks = json.loads(settings.read_text())["hooks"]["UserPromptSubmit"]
    assert hooks[0]["hooks"][0]["command"] == str(cli.HOOK_SCRIPT)
    assert hooks[0]["hooks"][0]["timeout"] == 30
    added, _ = cli._ensure_hook_installed()
    assert not added
