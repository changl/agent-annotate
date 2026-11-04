"""Every refusal on the publish/ask path ends in exactly one `· fix:` clause (stage 3e)."""
import argparse
import ast
import json
from pathlib import Path

import pytest

from agent_annotate import cli, pagegen

SRC = Path(pagegen.__file__).parent
# The publish/ask path: markdown → page → staged draft → batch commit.
PATH = {
    "pagegen.py": None,  # every refusal in the module
    "decision_quality.py": {"card_refusal"},
    "review_versions.py": {"require_draft", "stage"},
    "cli.py": {"_page_dir", "_publish_page", "cmd_publish_version", "_commit_review", "cmd_ask", "_moved_page"},
    "workspace.py": {"exception_reason", "duplicate_message"},
    "page_names.py": {"validate_name"},
}
PASSES = "# fix: passes through"  # the message is an inner refusal that carries its own fix


def _text(node) -> str | None:
    """The literal text of a message expression; formatted values become `{}`."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _text(node.left), _text(node.right)
        return (left or "{}") + (right or "{}") if left is not None or right is not None else None
    if isinstance(node, ast.IfExp):
        return _text(node.body) or _text(node.orelse)
    return None


def _refusals():
    found = []
    for name, functions in PATH.items():
        source = (SRC / name).read_text()
        tree, lines = ast.parse(source), source.splitlines()
        scopes = [tree] if functions is None else [
            n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in functions]
        assert functions is None or len(scopes) == len(functions), name
        for scope in scopes:
            for node in ast.walk(scope):
                message = None
                if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and node.exc.args:
                    if getattr(node.exc.func, "id", "") in ("PageGenError", "ValueError", "DecisionRequestError"):
                        message = _text(node.exc.args[0])
                elif (isinstance(node, ast.Call) and getattr(node.func, "id", "") == "print" and node.args
                      and any(k.arg == "file" for k in node.keywords)):
                    message = _text(node.args[0])
                    message = message if message and message.startswith(("ERROR", "not live")) else None
                elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "append"
                      and getattr(node.func.value, "id", "") == "problems" and node.args):
                    message = _text(node.args[0])
                elif isinstance(node, ast.Return) and name in ("decision_quality.py", "workspace.py") and node.value is not None:
                    message = _text(node.value)
                    message = None if message in ("standalone", "{}") else message
                if message is not None and PASSES not in lines[node.lineno - 1]:
                    found.append((f"{name}:{node.lineno}", message))
    return found


def test_the_list_covers_the_publish_path():
    assert len(_refusals()) > 60


@pytest.mark.parametrize("where, message", _refusals())
def test_each_refusal_names_exactly_one_fix(where, message):
    assert message.count(" · fix: ") == 1, f"{where}: {message}"


def test_a_failed_publish_prints_one_not_live_line(tmp_path, monkeypatch, capsys):
    source = tmp_path / "page.md"
    source.write_text("## Plan\n\n```ask\nShip it?\n+ Ship: Goes.\n- Hold: Waits.\nsee: cmp:chekout\n```\n\n"
                      "```compare\ntitle: Checkout\ncurrent: a.png | A\nproposed: b.png | B\n```\n")
    png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6a4b20000000049454e44ae426082")
    (tmp_path / "a.png").write_bytes(png)
    (tmp_path / "b.png").write_bytes(png)
    args = cli.build_parser().parse_args(["publish", str(tmp_path / "review"), "--from", str(source)])
    monkeypatch.setattr("agent_annotate.workspace.duplicate_page", lambda *a: None)
    assert cli.run_command(args) == 1
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err == ('not live: card "Ship it?" cites cmp:chekout, not on this page'
                       " · fix: cite one of cmp:checkout\n")


def test_lint_problems_are_one_line_with_a_count(tmp_path):
    source = tmp_path / "page.md"
    source.write_text("---\ntitle: Plan\nfull_plan: yes\n---\n\n## Plan\n\nText.\n")
    with pytest.raises(pagegen.PageGenError) as caught:
        pagegen.generate(source, tmp_path / "page", "v2")
    message = str(caught.value)
    assert "\n" not in message and "(+1 more)" in message and message.count(" · fix: ") == 1


def test_ask_refusals_from_json_cards_keep_one_fix(tmp_path, monkeypatch, capsys):
    record = {"slug_dir": str(tmp_path)}
    monkeypatch.setattr(cli, "_resolve_scoped_slug", lambda *a: ("p", "s", record))
    cards = tmp_path / "cards.json"
    cards.write_text(json.dumps([{"text": "No anchor"}]))
    assert cli.cmd_ask(argparse.Namespace(slug="s", project="p", from_file=str(cards), version="v1",
                                          author="agent:t", json=False)) == 2
    assert capsys.readouterr().err.count(" · fix: ") == 1
