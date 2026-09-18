"""`annotate install-skill` turns a skill directory into a deployment of the
package: skill text, references and a hook shim, nothing else, idempotently.
"""

import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from agent_annotate import cli, skillgen
from agent_annotate.paths import HOOK_SCRIPT


def test_skill_text_ships_as_package_data():
    for provider in skillgen.PROVIDERS:
        assert (skillgen.skill_source(provider) / "SKILL.md").is_file()
    refs = skillgen.SKILLS_DIR / "claude" / "references"
    assert (refs / "cli-reference.md").is_file()
    assert (skillgen.SKILLS_DIR / "codex" / "agents" / "openai.yaml").is_file()


@pytest.mark.parametrize("provider", skillgen.PROVIDERS)
def test_invocation_section_names_the_entry_point_and_the_module_fallback(provider):
    text = (skillgen.skill_source(provider) / "SKILL.md").read_text()
    out = skillgen.render_skill_md(provider, text)
    assert out.startswith("---\n"), "frontmatter must stay first for the skill loader"
    assert skillgen.GENERATED_MARK in out
    assert "annotate <cmd>" in out
    assert "python3 -m agent_annotate.cli <cmd>" in out
    assert "/cli.py" not in out.split("## 2.")[0], "no file path in the invocation section"
    assert out.count("## 1. Invocation") == 1


def test_render_refuses_text_without_an_invocation_block():
    with pytest.raises(ValueError):
        skillgen.render_skill_md("claude", "---\nname: x\n---\n# no invocation\n")


def test_install_writes_skill_references_and_hook_shim(tmp_path):
    dest = tmp_path / "annotate"
    lines = skillgen.install_skill("claude", dest)
    assert all(line.startswith("wrote") for line in lines), lines
    assert (dest / "SKILL.md").is_file()
    assert (dest / "references" / "cli-reference.md").read_text() == (
        skillgen.SKILLS_DIR / "claude" / "references" / "cli-reference.md").read_text()
    assert (dest / "references" / "interaction-contract.md").is_file()
    shim = dest / "hooks" / "check-comment-bus.sh"
    assert os.access(shim, os.X_OK)
    assert str(HOOK_SCRIPT) in shim.read_text()
    assert not (dest / "agents").exists()
    assert not (dest / "cli.py").exists()


def test_codex_install_adds_the_agent_manifest(tmp_path):
    dest = tmp_path / "annotate"
    skillgen.install_skill("codex", dest)
    assert (dest / "agents" / "openai.yaml").is_file()
    assert "Codex" in (dest / "SKILL.md").read_text()


def test_install_is_idempotent_and_repairs_a_drifted_file(tmp_path):
    dest = tmp_path / "annotate"
    skillgen.install_skill("claude", dest)
    second = skillgen.install_skill("claude", dest)
    assert all(line.startswith("unchanged") for line in second), second

    (dest / "SKILL.md").write_text("edited by hand\n")
    os.chmod(dest / "hooks" / "check-comment-bus.sh", 0o644)
    third = skillgen.install_skill("claude", dest)
    assert "updated    SKILL.md" in third
    assert "mode       hooks/check-comment-bus.sh" in third
    assert skillgen.GENERATED_MARK in (dest / "SKILL.md").read_text()


def test_install_never_deletes_what_it_did_not_write(tmp_path):
    dest = tmp_path / "annotate"
    dest.mkdir()
    (dest / "projects.toml").write_text("[docs]\ntransport = 'local'\n")
    skillgen.install_skill("claude", dest)
    assert (dest / "projects.toml").read_text() == "[docs]\ntransport = 'local'\n"


def test_unknown_provider_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        skillgen.install_skill("gemini", tmp_path)


def test_the_generated_hook_shim_runs_the_packaged_hook(tmp_path):
    """The shim in the skill directory must produce the same notice as the
    packaged hook, with the payload on stdin, and never block a prompt."""
    dest = tmp_path / "annotate"
    skillgen.install_skill("claude", dest)
    bus_root = tmp_path / "bus"
    state = tmp_path / "state"
    slug_dir = tmp_path / "pages" / "demo"
    slug_dir.mkdir(parents=True)
    (bus_root / "proj").mkdir(parents=True)
    state.mkdir()
    (state / "proj.json").write_text(json.dumps({"project": "proj", "slugs": {"demo": {
        "slug": "demo", "slug_dir": str(slug_dir), "project": "proj",
        "bus_file": str(bus_root / "proj" / "demo.ndjson")}}}))
    (slug_dir / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {
        "s:a": [{"id": "aaaaaaaaaaaa", "anchor_id": "s:a", "text": "A?", "status": "open",
                 "decision_request": {"prompt": "A?"},
                 "decision": {"verdict": "accept", "ts": "2026-09-17T10:00:00Z", "by": "r@x"}}]},
        "archived": {}}))
    (bus_root / "proj" / "demo.ndjson").write_text(json.dumps(
        {"ts": "2026-09-17T10:00:00Z", "event": "comment_updated", "slug": "demo",
         "comment_id": "aaaaaaaaaaaa", "anchor_id": "s:a", "author": "r@x", "decision": "accept"}) + "\n")
    env = os.environ.copy()
    env["ANNOTATE_BUS_ROOT"] = str(bus_root)
    env["ANNOTATE_STATE_DIR"] = str(state)
    env["ANNOTATE_HOOK_DRY_RUN"] = "1"
    proc = subprocess.run([str(dest / "hooks" / "check-comment-bus.sh")],
                          input=json.dumps({"session_id": "sess-skill", "cwd": "/tmp"}),
                          capture_output=True, text=True, env=env, timeout=20)
    assert proc.returncode == 0, proc.stderr
    assert "[annotate] proj/demo: 1 reviewer event(s)" in proc.stdout, proc.stdout


def test_cli_subcommand_prints_the_report(tmp_path, capsys):
    rc = cli.cmd_install_skill(SimpleNamespace(provider="claude", dest=str(tmp_path / "sk")))
    assert rc == 0
    out = capsys.readouterr().out
    assert "wrote      SKILL.md" in out
    assert "wrote      hooks/check-comment-bus.sh" in out


def test_cli_registers_install_skill():
    proc = subprocess.run([sys.executable, "-m", "agent_annotate.cli", "install-skill", "--help"],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0
    assert "--provider" in proc.stdout and "--dest" in proc.stdout
