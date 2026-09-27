"""The pure parts of scripts/bench.py: transcript parsing, failure counting,
card checks and table math. Nothing here calls claude or starts a server."""

import importlib.util
import json
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "bench.py"
_SPEC = importlib.util.spec_from_file_location("annotate_bench", _PATH)
bench = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bench)


def test_annotate_subcommands_counts_command_position_only():
    cases = {
        "annotate new reviews/x --from x.md --publish --ask": ["new"],
        "cd reviews && annotate cards orders-status-rename": ["cards"],
        "/tmp/sb/bin/annotate status": ["status"],
        "python3 -m agent_annotate.cli inbox x --unread": ["inbox"],
        "ANNOTATE_AUTHOR=me annotate resolve x c1 --in-version v2 --anchor s:plan": ["resolve"],
        "annotate resolve x c1 --in-version v2 --anchor s:a; annotate carry x c2 --to-version v2 --anchor d:q4":
            ["resolve", "carry"],
        "echo $(annotate status)": ["status"],
        "ls ~/.claude/annotate-state && cat .claude/skills/annotate/SKILL.md": [],
        "echo annotate new": [],
        "grep -rn annotate .": [],
    }
    for cmd, want in cases.items():
        assert bench.annotate_subcommands(cmd) == want, cmd


def test_output_failed():
    assert bench.output_failed("Exit code 1\nsomething", True)
    assert bench.output_failed("  NOT PUBLISHED — the page does not render.", False)
    assert bench.output_failed("Traceback (most recent call last):\n  File ...", False)
    assert bench.output_failed("ERROR: cannot publish v2", False)
    assert bench.output_failed("  origin     FAIL  http://127.0.0.1:9400/", False)
    assert not bench.output_failed("  URL:           http://localhost:9400/", False)
    assert not bench.output_failed("  WARN           full-plan warning: v2 retains 2/3", False)
    assert not bench.output_failed("no errors, nothing failed", False)


def _stream(*events) -> list[str]:
    return [json.dumps(e) for e in events]


def _tool_use(tid, name, **inp):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": tid, "name": name, "input": inp}]}}


def _tool_result(tid, content, is_error=False):
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": tid, "content": content, "is_error": is_error}]}}


def test_parse_stream_metrics_and_failures():
    lines = _stream(
        {"type": "system", "subtype": "init"},
        _tool_use("t0", "Skill", skill="annotate"),
        _tool_result("t0", "Launching skill: annotate"),
        _tool_use("t1", "Bash", command="annotate new reviews/x --from x.md --publish --ask"),
        _tool_result("t1", "  wrote  reviews/x/versions/v1.html\n  URL:  http://localhost:9400/"),
        _tool_use("t2", "Bash", command="ls reviews"),
        _tool_result("t2", "x"),
        _tool_use("t3", "Bash", command="annotate publish-version reviews/x v2"),
        _tool_result("t3", [{"type": "text", "text": "Exit code 2\nERROR: cannot publish v2"}], True),
        {"type": "result", "subtype": "success", "is_error": False, "duration_ms": 61000,
         "num_turns": 7, "total_cost_usd": 0.42, "result": "URL: http://localhost:9400/",
         "usage": {"input_tokens": 12, "output_tokens": 3400, "cache_read_input_tokens": 200000,
                   "cache_creation_input_tokens": 30000,
                   "output_tokens_details": {"thinking_tokens": 900}}},
    )
    m = bench.parse_stream(["not json", *lines])
    assert (m["tool_calls"], m["tool_errors"]) == (4, 1)
    assert (m["annotate_calls"], m["annotate_failures"]) == (2, 1)
    assert m["annotate_subcommands"] == {"new": 1, "publish-version": 1}
    assert m["failures"][0]["cmd"].startswith("annotate publish-version")
    assert "ERROR" in m["failures"][0]["out"]
    assert m["skill_used"] is True
    assert (m["output_tokens"], m["thinking_tokens"]) == (3400, 900)
    assert (m["cache_read"], m["cache_creation"], m["input_tokens"]) == (200000, 30000, 12)
    assert (m["cost_usd"], m["duration_s"], m["num_turns"], m["is_error"]) == (0.42, 61.0, 7, False)


def test_parse_stream_without_a_result_is_an_error():
    m = bench.parse_stream(_stream(_tool_use("t1", "Bash", command="annotate status")))
    assert m["annotate_calls"] == 1 and m["annotate_failures"] == 0
    assert m["is_error"] is True
    assert m["cost_usd"] is None and m["duration_s"] is None


def test_card_problems():
    anchors = {"d:q1", "s:plan", "tbl:cols:row:status"}
    good = {"anchor_id": "d:q1", "decision_request": {
        "prompt": "Rename?", "context": "Three readers.", "recommendation": "accept",
        "options": [{"id": "accept", "label": "Rename", "consequence": "One dual-write week."},
                    {"id": "reject", "label": "Keep", "consequence": "Ambiguous through v3."}],
        "evidence": [{"label": "plan", "anchor": "s:plan"}]}}
    assert bench.card_problems(good, anchors) == []

    string_options = {"decision_request": {
        "context": "c", "recommendation": "accept", "options": ["accept", "reject", "comment"],
        "consequences": {"accept": "a", "reject": "r"},
        "evidence": [{"anchor": "tbl:cols:row:status"}]}}
    assert bench.card_problems(string_options, anchors) == []

    bare = {"decision_request": {"prompt": "Rename?", "options": [{"id": "accept"}],
                                 "evidence": [{"anchor": "s:gone"}]}}
    assert bench.card_problems(bare, anchors) == [
        "context", "recommendation", "consequence:accept", "evidence:s:gone"]
    assert bench.card_problems({"text": "no request"}, anchors) == ["no decision_request"]


def test_summarize_and_format():
    s = bench.summarize([3, None, 1, 2])
    assert s == {"median": 2, "min": 1, "max": 3, "n": 3}
    assert bench.summarize([None]) is None
    assert bench.fmt_cell(s, 0, spread=True) == "2 [1–3]"
    assert bench.fmt_cell(s, 0, spread=False) == "2"
    assert bench.fmt_cell(None, 0, spread=True) == "-"
    assert bench.fmt_delta({"median": 100}, {"median": 80}, 0) == "-20 (-20%)"
    assert bench.fmt_delta({"median": 0}, {"median": 3}, 0) == "+3"
    assert bench.fmt_delta({"median": 1.5}, {"median": 1.2}, 2) == "-0.30 (-20%)"
    assert bench.fmt_delta(None, s, 0) == "-"


def test_render_table():
    rows = {
        "main@aaa": [{"output_tokens": 1000, "cost_usd": 1.0, "annotate_failures": 2, "outcome": True},
                     {"output_tokens": 1200, "cost_usd": 1.2, "annotate_failures": 0, "outcome": False}],
        "cand@bbb": [{"output_tokens": 800, "cost_usd": 0.9, "annotate_failures": 0, "outcome": True},
                     {"output_tokens": 900, "cost_usd": 0.7, "annotate_failures": 0, "outcome": True}],
    }
    text = bench.render_table("v1-page", ["main@aaa", "cand@bbb"], rows)
    lines = text.splitlines()
    assert lines[0] == "v1-page"
    assert lines[1].split() == ["metric", "main@aaa", "cand@bbb", "Δ", "cand@bbb"]
    by_name = {line[:18].strip(): line for line in lines[2:]}
    assert "1,100 [1,000–1,200]" in by_name["output tokens"]
    assert "850 [800–900]" in by_name["output tokens"]
    assert by_name["output tokens"].endswith("-250 (-23%)")
    assert by_name["cost $"].endswith("-0.30 (-27%)")
    assert by_name["thinking tokens"].split()[2:] == ["-", "-", "-"]
    assert by_name["outcome pass"].split()[2:] == ["1/2", "2/2", "+1"]
