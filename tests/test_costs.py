"""`annotate cost`: rows from transcripts, usage read once per message,
failures classified, and the estimate arithmetic.

Every scan here points --root / --codex-root at tmp_path; the live
~/.claude/projects and ~/.codex/sessions are never read.
"""

import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from agent_annotate import costs

ANCHOR_ERR = ("ERROR: PUT /api/comments/abc123def456 → HTTP 400: "
              "{'error': 'resolution target anchor not found'}")
RESOLVED = "resolved abc123def456 in v2 at s:y"


def _write(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(x) + "\n" for x in lines))


def _assistant(mid, ts, blocks, out, cwd="/work/app"):
    return {"type": "assistant", "timestamp": ts, "cwd": cwd, "uuid": f"{mid}-{ts}",
            "message": {"id": mid, "role": "assistant", "content": blocks,
                        "usage": {"output_tokens": out}}}


def _bash(tid, cmd):
    return {"type": "tool_use", "id": tid, "name": "Bash", "input": {"command": cmd}}


def _result(ts, tid, text, is_error=False, cwd="/work/app"):
    return {"type": "user", "timestamp": ts, "cwd": cwd, "uuid": f"u-{tid}",
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tid, "content": text, "is_error": is_error}]}}


SESSION = [
    # One message streamed over two lines, usage repeated and growing: read once, never summed.
    _assistant("msg_1", "2026-09-20T10:00:00Z", [{"type": "text", "text": "Resolving."}], 12),
    _assistant("msg_1", "2026-09-20T10:00:01Z", [_bash(
        "t1", "cd /work && rtk annotate resolve demo abc123def456 --in-version v2 --anchor s:x")], 120),
    _result("2026-09-20T10:00:03Z", "t1", ANCHOR_ERR, is_error=True),
    # The retry, through the module form, shares its message with an unrelated Read.
    _assistant("msg_2", "2026-09-20T10:01:00Z", [
        _bash("t2", "env PYTHONPATH=src python -m agent_annotate.cli resolve demo abc123def456 "
                    "--in-version v2 --anchor s:y"),
        {"type": "tool_use", "id": "t3", "name": "Read", "input": {"file_path": "/work/app/notes.md"}}], 80),
    _result("2026-09-20T10:01:02Z", "t2", RESOLVED),
    _result("2026-09-20T10:01:02Z", "t3", "x" * 999),
    _assistant("msg_3", "2026-09-20T10:02:00Z",
               [_bash("t4", "annotate publish-version reviews/demo v2 2>&1 | tail -3")], 30),
    _result("2026-09-20T10:02:10Z", "t4", "published v2"),
    _assistant("msg_4", "2026-09-20T10:03:00Z", [{"type": "tool_use", "id": "t5", "name": "Read", "input": {
        "file_path": "/home/u/.claude/skills/annotate/references/cli-reference.md"}}], 8),
    _result("2026-09-20T10:03:00Z", "t5", "r" * 400),
]


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "projects"
    _write(r / "-work-app" / "sess-a.jsonl", SESSION)
    _write(r / "-work-app" / "sess-b.jsonl", SESSION[:3])  # a fork repeats its parent's history
    dev = "/work/agent-annotate"
    _write(r / "-work-agent-annotate" / "sess-c.jsonl", [
        _assistant("msg_9", "2026-09-20T11:00:00Z", [_bash("t9", "annotate status")], 5, cwd=dev),
        _result("2026-09-20T11:00:01Z", "t9", "(no active slugs)", cwd=dev)])
    return r


def _args(root, **over):
    base = dict(since="2026-09-01", by="week", include_dev=False, codex=False, root=str(root),
                codex_root=None, json=False, estimate=None)
    base.update(over)
    return SimpleNamespace(**base)


def test_invocations_see_through_launchers_and_chains_but_not_heredocs_or_messages():
    assert costs.invocations("cd x && rtk env A=1 uv run annotate publish reviews/demo 2>&1 | tail -5") == [
        ("publish", "reviews/demo 2>&1")]
    assert costs.invocations("timeout 60 ~/.local/bin/annotate status") == [("status", "")]
    assert costs.invocations("cat > p.md <<'EOF'\nannotate publish x\nEOF\nannotate ask demo --from c.json") == [
        ("ask", "demo --from c.json")]
    assert costs.invocations('orca orchestration send --text "run annotate status"') == []
    assert costs.invocations("echo annotate status") == []


def test_rows_read_usage_once_split_it_and_classify_the_failure(root):
    rows = costs.collect(_args(root))
    assert [(r["kind"], r["sub"]) for r in rows] == [
        ("cli", "resolve"), ("cli", "resolve"), ("cli", "publish-version"), ("doc", "read:cli-reference")]
    failed, retry, publish, doc = rows

    assert failed["out_tokens"] == 120          # max over the message's lines, not 12 + 120
    assert retry["out_tokens"] == 40            # 80 split over the message's two tool calls
    assert failed["failed"] and failed["reasons"] == ["is_error", "ERROR"]
    assert costs.reason_key(failed) == "resolution target anchor not found"
    assert failed["retry_out_tokens"] == 40
    assert failed["secs"] == 2.0
    assert failed["result_tokens"] == len(ANCHOR_ERR) // 4

    assert not retry["failed"] and retry["slug"] == "demo"
    assert publish["slug"] == "demo" and publish["closes_round"]
    assert doc["result_tokens"] == 100 and doc["out_tokens"] == 8

    assert [len(rd) for rd in costs.rounds(rows)] == [3]


def test_dev_sessions_only_with_include_dev(root):
    assert "status" not in [r["sub"] for r in costs.collect(_args(root))]
    assert [r["sub"] for r in costs.collect(_args(root, include_dev=True))].count("status") == 1


def test_estimate_replays_a_smaller_result_and_a_fixed_failure(root):
    rows = costs.collect(_args(root))
    before, after, hits, matched = costs.replay(
        rows, {"resolve": {"result_tokens": 5}, "anchor not found": "fixed"})
    res_failed, res_ok = len(ANCHOR_ERR) // 4, len(RESOLVED) // 4
    assert before["resolve"] == 120 + res_failed + 40 + res_ok
    # fixed: the failed call keeps its own turn, loses its result and the retry's 40;
    # resized: the successful resolve now returns 5 tokens.
    assert after["resolve"] == (120 - 40) + (40 + 5)
    assert after["publish-version"] == before["publish-version"]
    assert hits == {"resolve": 2}
    assert matched == {"resolve": 1, "anchor not found": 1}
    with pytest.raises(ValueError):
        costs.replay(rows, {"resolve": 12})


def test_codex_rows_take_the_issuing_responses_usage(tmp_path):
    sessions = tmp_path / "sessions"
    _write(sessions / "2026" / "09" / "22" / "rollout-x.jsonl", [
        {"timestamp": "2026-09-22T20:25:10Z", "type": "session_meta",
         "payload": {"id": "thread-1", "cwd": "/work/app"}},
        {"timestamp": "2026-09-22T20:25:16Z", "type": "response_item", "payload": {
            "type": "function_call", "name": "exec_command", "call_id": "c1",
            "arguments": json.dumps({"cmd": "rtk annotate status demo"})}},
        {"timestamp": "2026-09-22T20:25:16Z", "type": "token_usage_record",
         "payload": {"usage": {"output_tokens": 50}}},
        {"timestamp": "2026-09-22T20:25:17Z", "type": "response_item", "payload": {
            "type": "function_call_output", "call_id": "c1",
            "output": "Chunk ID: x\nWall time: 0.1 seconds\nProcess exited with code 1\n"
                      "Original token count: 9\nOutput:\nUsage: annotate imagein.jpg imageout.jpg\n"}},
        {"timestamp": "2026-09-22T20:25:17Z", "type": "event_msg", "payload": {
            "type": "token_count", "info": {"last_token_usage": {"output_tokens": 50}}}},
        {"timestamp": "2026-09-22T20:25:20Z", "type": "response_item", "payload": {
            "type": "custom_tool_call", "name": "exec", "call_id": "c2",
            "input": 'const r = await tools.exec_command({"cmd":"annotate cards demo"}); text(r.output);'}},
        {"timestamp": "2026-09-22T20:25:21Z", "type": "response_item", "payload": {
            "type": "custom_tool_call_output", "call_id": "c2", "output": [
                {"type": "input_text", "text": "Script completed\nWall time 0.2 seconds\nOutput:\n"},
                {"type": "input_text", "text": "  demo: 2 cards, 1 accept"}]}},
        {"timestamp": "2026-09-22T20:25:21Z", "type": "event_msg", "payload": {
            "type": "token_count", "info": {"last_token_usage": {"output_tokens": 30}}}},
    ])
    status, cards = costs.collect(_args(tmp_path / "no-claude", codex=True, codex_root=str(sessions)))
    assert (status["source"], status["session"], status["sub"]) == ("codex", "thread-1", "status")
    assert status["reasons"] == ["is_error"]
    assert status["error"] == "Usage: annotate imagein.jpg imageout.jpg"
    assert status["out_tokens"] == 50           # the second record of the same response adds nothing
    assert cards["out_tokens"] == 30 and not cards["failed"]


def test_periods_by_cut_date_and_release():
    cut = costs.period_of("2026-09-18,2026-09-23")
    assert [cut(d) for d in ("2026-09-01", "2026-09-20", "2026-09-25")] == [
        "before 2026-09-18", "from 2026-09-18", "from 2026-09-23"]
    assert costs.period_of("release")("2026-09-20") == "v2.19.0"
    assert costs.period_of("week")("2026-09-20") == "2026-09-14"


def test_report_json_and_estimate_through_the_cli(root, tmp_path, capsys):
    assert costs.run(_args(root)) == 0
    out = capsys.readouterr().out
    assert "3 annotate calls + 1 doc reads in 1 sessions; 1 closed rounds" in out
    assert "resolution target anchor not found ×1" in out

    assert costs.run(_args(root, json=True)) == 0
    assert len(json.loads(capsys.readouterr().out)) == 4

    model = tmp_path / "model.json"
    model.write_text(json.dumps({"anchor not found": "fixed"}))
    proc = subprocess.run([sys.executable, "-m", "agent_annotate.cli", "cost", "--root", str(root),
                           "--since", "2026-09-01", "--estimate", str(model)],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert "/anchor not found/ fixed: 1 failed rows" in proc.stdout
    assert "  all " in proc.stdout
