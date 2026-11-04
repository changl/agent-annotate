"""scripts/orch_cost.py on a tiny synthetic transcript: dedupe, cost, wakes and annotate actions."""

import importlib.util
import json
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "orch_cost.py"
_SPEC = importlib.util.spec_from_file_location("orch_cost", _PATH)
oc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(oc)


def _call(mid, ts, tools=(), ctx=100_000, out=100):
    return {"type": "assistant", "timestamp": ts, "message": {
        "id": mid, "model": "claude-opus-5-5",
        "usage": {"input_tokens": 0, "output_tokens": out, "cache_read_input_tokens": ctx, "cache_creation_input_tokens": 0},
        "content": [{"type": "tool_use", "id": tid, "name": "Bash", "input": {"command": cmd}} for tid, cmd in tools]}}


def _result(tid, text, ts):
    return {"type": "user", "timestamp": ts, "message": {"content": [
        {"type": "tool_result", "tool_use_id": tid, "content": text}]}}


def _wake(text, ts):
    return {"type": "user", "timestamp": ts, "message": {"content": text}}


def _transcript(tmp_path):
    rows = [
        _wake("<task-notification>worker done</task-notification>", "2026-11-01T10:00:00Z"),
        _call("m1", "2026-11-01T10:00:05Z", [("t1", "orca-quiet-wait --run r1")]),
        _call("m1", "2026-11-01T10:00:05Z", [("t1", "orca-quiet-wait --run r1")]),  # streamed twice: one call
        _result("t1", "mail", "2026-11-01T10:00:06Z"),
        _wake("[annotate] Round submitted on the page", "2026-11-01T10:01:00Z"),
        _call("m2", "2026-11-01T10:01:05Z", [("t2", "annotate inbox p/s --unread")]),
        _result("t2", "#1 select \"Ship?\" → yes", "2026-11-01T10:01:06Z"),
        _call("m3", "2026-11-01T10:02:00Z", [("t3", "annotate resolve p/s 1")]),
        _result("t3", "ERROR: item 1 not found or number is ambiguous", "2026-11-01T10:02:01Z"),
        _call("m4", "2026-11-01T10:03:00Z", [("t4", "orchestration worker-start --run r1")]),
        _result("t4", "{}", "2026-11-01T10:03:01Z"),
        {"type": "cost-state", "modelUsage": {"claude-opus-5-5": {
            "inputTokens": 0, "outputTokens": 400, "cacheReadInputTokens": 400_000,
            "cacheCreationEphemeral5mInputTokens": 0, "cacheCreationEphemeral1hInputTokens": 0, "costUSD": 0.84}}},
    ]
    path = tmp_path / "session.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def test_meter_reproduces_cost_wakes_and_annotate_actions(tmp_path, capsys):
    path = _transcript(tmp_path)
    rep = oc.report("session", oc.read(str(path)))
    assert rep["api_calls"] == 4 and rep["rate_source"] == "session cost-state"
    assert abs(rep["est_usd"] - 0.84) < 1e-6                     # 4 calls × (10k + 500) units at the fitted rate
    assert rep["wakes"]["background_exit"] == 1 and rep["rounds_delivered"] == 1 and rep["workers_started"] == 1
    a = rep["annotate"]
    assert a["total"]["commands"] == 2 and a["total"]["failed"] == 1
    assert a["resolve"] == {"commands": 1, "items": 1, "failed": 1, "tokens_per_command": a["resolve"]["tokens_per_command"],
                            "usd_total": 0.21}
    assert a["read_one_round"]["commands_median"] == 1              # the inbox; resolving is not reading
    assert abs(a["share_of_cost"] - 0.5) < 1e-6
    assert rep["category_groups"]["waiting on workers and mail"] == 0.25
    assert oc.main([str(path), "--json", str(tmp_path / "r.json")]) == 0
    assert "annotate share" in capsys.readouterr().out
    assert json.loads((tmp_path / "r.json").read_text())["api_calls"] == 4


def test_since_drops_earlier_records(tmp_path):
    path = _transcript(tmp_path)
    rep = oc.report("session", oc.read(str(path), oc.ts("2026-11-01T10:01:30Z")))
    assert rep["api_calls"] == 2 and rep["rounds_delivered"] == 0
