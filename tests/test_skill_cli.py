"""The short workflow must stay executable as the CLI evolves."""

import argparse
import json
import re
import shlex
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_annotate import cli
from agent_annotate.urls import deep_link

ROOT = Path(__file__).resolve().parents[1]


def test_default_help_lists_only_workflow_commands_and_full_help_keeps_legacy(capsys):
    parser = cli.build_parser()
    text = parser.format_help()
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    assert {a.dest for a in action._choices_actions} == {*cli.AGENT_COMMANDS, "help"}
    assert "monitor" not in text and "resolve" not in text and "doctor" not in text
    cli.cmd_help(SimpleNamespace(all=True, markdown=False, command=None))
    full = capsys.readouterr().out
    for name in ("monitor", "resolve", "carry", "doctor", "eval", "cost"):
        assert name in full
        assert name in cli.command_parsers(parser)
    assert "monitor" not in cli.command_parsers(parser)["help"].format_help()
    # Hidden commands still parse with all their old flags.
    args = parser.parse_args(["monitor", "demo", "--takeover", "--provider", "stdout"])
    assert args.func is cli.cmd_monitor and args.takeover


def test_command_reference_is_generated_from_the_execution_parser():
    assert (ROOT / "docs/skill-commands.md").read_text() == cli.command_reference()
    commands = cli.command_parsers(cli.build_parser())
    for name in cli.AGENT_COMMANDS:
        assert commands[name].format_help().rstrip() in cli.command_reference()


def test_every_command_and_flag_mentioned_in_the_skill_exists():
    commands = cli.command_parsers(cli.build_parser())
    source = ROOT / "src/agent_annotate/skills/claude"
    texts = [(source / "SKILL.md").read_text(), (source / "references/page.md").read_text()]
    mentioned = set()
    for text in texts:
        for snippet in re.findall(r"`(annotate [^`]+)`", text):
            tokens = shlex.split(snippet)
            command = tokens[1]
            assert command in commands, snippet
            mentioned.add(command)
            options = {flag for action in commands[command]._actions for flag in action.option_strings}
            for token in tokens[2:]:
                if token.startswith("--"):
                    assert token.partition("=")[0] in options, snippet
    assert set(cli.AGENT_COMMANDS) <= mentioned
    all_flags = {flag for parser in commands.values() for action in parser._actions for flag in action.option_strings}
    for text in texts:
        assert set(re.findall(r"(?<![\w-])--[a-z][a-z-]*", text)) <= all_flags


def test_write_receipt_is_one_line_and_json_preserves_full_output(monkeypatch, capsys):
    record = {"slug_dir": "/tmp/demo", "url": "https://example.test/demo/"}
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("p", "demo", record)])
    def write(args):
        print("saved item 1")
        print("saved item 2")
        return 0
    args = SimpleNamespace(cmd="withdraw", slug="p/demo", comment_id="card-1", json=False, func=write)
    assert cli.run_command(args) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert "https://example.test/demo/#view=review&feedback=card-1" in lines[0]
    args.json = True
    assert cli.run_command(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["output"] == "saved item 1\nsaved item 2\n"
    assert result["url"].endswith("feedback=card-1")


def test_failed_write_keeps_diagnostics(monkeypatch, capsys):
    def fail(args):
        print("verification failed")
        print("page remains running")
        return 2
    args = SimpleNamespace(cmd="new", func=fail)
    assert cli.run_command(args) == 2
    assert capsys.readouterr().out == "verification failed\npage remains running\n"


@pytest.mark.parametrize("view,comment,version", [("library", None, None), ("review", "id 1", "v2"), ("plan:rollout", None, None)])
def test_deep_link_preserves_share_key(view, comment, version):
    from urllib.parse import parse_qs, urlsplit
    link = deep_link({"url": "https://example.test/page/#review=secret"}, view=view, comment=comment, version=version)
    fragment = parse_qs(urlsplit(link).fragment)
    assert fragment["review"] == ["secret"] and fragment["view"] == [view]
    if comment:
        assert fragment["feedback"] == [comment]
    if version:
        assert fragment["v"] == [version]


def test_round_answers_include_the_complete_prompt_and_note():
    prompt = "A long but essential question about the actual migration " * 4
    note = "The full explanation matters. " * 20
    lines = cli._round_lines({"event": "round_submitted", "answers": [{"number": 1, "prompt": prompt, "text": note, "verdict": "select"}]})
    assert prompt in lines[0] and note in lines[0]
