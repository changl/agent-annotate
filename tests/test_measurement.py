"""Portable measurements use sandbox stores and transcripts on both simulated hosts."""
import json
from types import SimpleNamespace

from agent_annotate import costs, measurement
from agent_annotate import eval as evaluation


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def estate(tmp_path):
    state = tmp_path / "state"
    for project in ("alpha", "beta"):
        page = tmp_path / project
        write(state / (project + ".json"), {"project": project, "slugs": {"workspace": {
            "slug_dir": str(page), "owner_session": "gone-session"}}})
        write(page / "comments.json", {"schema_version": 2, "anchors": {"d:q1": [{
            "id": "abcdef012345", "created_at": "2026-10-02T01:00:00Z", "category": "findings",
            "status": "open", "version": "v1", "decision_request": {
                "prompt": "Accept all 16 layouts?", "evidence": [{"anchor": "s:layout"}]}}]}, "archived": {}})
        write(page / "categories.json", {"schema_version": 1, "findings_sets": [{"id": "layout", "label": "Layout"}]})
        write(page / "current.meta.json", {"current": "v2", "history": [
            {"version": "v1", "ts": "2026-09-01T00:00:00Z"},
            {"version": "v2", "ts": "2026-10-03T00:00:00Z"}]})
        (page / "current.html").write_text('<h1 id="s:other">Proposed layout</h1><script>"<img>"</script>')
        (page / "rounds.ndjson").write_text(json.dumps({"id": "r1", "ts": "2026-10-04T00:00:00Z",
            "by": "Chang", "answers": [{"comment_id": "abcdef012345", "verdict": "changes"}]}) + '\n{"partial":')
    return state


def run_eval(tmp_path, state, capsys, *extra):
    evaluation.main(["--json", "--since", "2026-10-01", "--state-dir", str(state),
                     "--bus-dir", str(tmp_path / "no-bus"), "--transcript-glob", str(tmp_path / "none/*.jsonl"), *extra])
    return json.loads(capsys.readouterr().out)


def test_modern_pages_identity_rounds_categories_and_merge(tmp_path, monkeypatch, capsys):
    state = estate(tmp_path)
    monkeypatch.setattr(evaluation.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout="other process"))
    monkeypatch.setattr(measurement, "host", lambda: "M5")
    first = run_eval(tmp_path, state, capsys)
    assert first["meta"]["slugs_total"] == 2
    assert first["s1_aggregate"]["decision_requests"] == 2
    assert first["s2_summary"]["rounds"] == 2
    assert first["measures"]["submitted_rounds"] == 2
    assert first["measures"]["rail_only_open_cards"] == 2
    assert first["measures"]["open_cards_owner_absent_or_moved_or_superseded"] == 2
    assert first["measures"]["bulk_approval_candidate_cards"] == 2
    assert first["measures"]["visual_change_candidate_versions_no_image"] == 2
    assert first["measures"]["pages"][0]["categories"]["findings_sets"][0]["id"] == "layout"
    assert not (state / "logs").exists()  # --json has no output/cache side effects
    export = tmp_path / "m5.json"
    write(export, first)
    monkeypatch.setattr(measurement, "host", lambda: "M1")
    merged = run_eval(tmp_path, state, capsys, "--merge", str(export))
    assert merged["meta"]["slugs_total"] == 4
    assert merged["s1_aggregate"]["decision_requests"] == 4
    assert merged["s2_summary"]["rounds"] == 4
    write(export, merged)
    repeated = run_eval(tmp_path, state, capsys, "--merge", str(export))
    assert repeated["meta"]["slugs_total"] == 4


def test_backlog_unknowns_anchors_and_moved(tmp_path):
    state = estate(tmp_path)
    evaluation._rebind_roots(state, tmp_path / "no-bus", tmp_path / "none/*.jsonl")
    info = evaluation.collect_slugs()["alpha/workspace"]
    page = tmp_path / "alpha"
    (page / "current.html").write_text("<h1 data-anchor-id='s:layout'>Layout</h1><img src='shot.png'>")
    (page / "consolidated.json").write_text('{}')
    metrics = measurement.page_metrics(info, "2026-10-01", "")
    assert metrics["moved"] is True
    assert metrics["owner_presence"] == "unknown"
    assert metrics["cards"][0]["rail_only"] is False
    assert metrics["versions"][0]["no_image"] is False
    (page / "current.html").unlink()
    assert measurement.page_metrics(info, "2026-10-01", "")["cards"][0]["rail_only"] is None


def test_archived_pages_leave_measurement_counts_even_with_retained_buses(tmp_path, monkeypatch, capsys):
    state = estate(tmp_path)
    (tmp_path / "alpha" / "archived.json").write_text('{"why":"Superseded"}')
    path = state / "beta.json"
    record = json.loads(path.read_text())
    record["slugs"]["workspace"]["archived"] = {"why": "Superseded"}
    path.write_text(json.dumps(record))
    for project in ("alpha", "beta"):
        write(tmp_path / "no-bus" / project / "workspace.ndjson", {"event": "round_submitted"})
    monkeypatch.setattr(evaluation.subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout="other process"))
    result = run_eval(tmp_path, state, capsys)
    assert result["meta"]["slugs_total"] == 0
    assert result["measures"]["open_cards"] == 0
    assert result["measures"]["pages"] == []


def test_corrections_only_user_messages_by_monday_week(tmp_path):
    path = tmp_path / "claude.jsonl"
    rows = [{"type": "user", "timestamp": "2026-10-08T00:00:00Z", "message": {"content": "Why are annotate cards still open?"}},
            {"type": "assistant", "timestamp": "2026-10-08T00:00:00Z", "message": {"content": "Why are annotate cards still open?"}},
            {"type": "user", "timestamp": "2026-10-08T00:00:00Z", "message": {"content": [
                {"type": "tool_result", "content": "Please use annotate"}]}},
            {"type": "user", "timestamp": "2026-10-08T00:00:00Z", "message": {"content": "You are a dispatched worker, use annotate"}}]
    path.write_text("\n".join(json.dumps(r) for r in rows + rows[:1]))
    codex = tmp_path / "codex.jsonl"
    codex.write_text(json.dumps({"type": "response_item", "timestamp": "2026-10-12T00:00:00Z", "payload": {
        "type": "message", "role": "user", "content": [{"type": "input_text", "text": "Please show pictures on the annotate page"}]}}))
    found = measurement.corrections([path], [codex], "2026-10-01")
    assert [r["week"] for r in found] == ["2026-10-05", "2026-10-12"]
    assert not measurement.corrections([path], [codex], "2026-10-15")


def test_cost_merge_keeps_hosts_separate_and_recomputes_rounds(tmp_path, monkeypatch, capsys):
    row = dict(source="claude", session="same", file="/same/path", kind="cli", slug="workspace", sub="new",
               ts="2026-10-02T00:00:00Z", date="2026-10-02", out_tokens=100, result_tokens=20,
               closes_round=True, failed=False, reasons=[], retry_out_tokens=None, secs=1, error=None)
    monkeypatch.setattr(costs, "collect", lambda args: [row])
    args = SimpleNamespace(since="2026-10-01", codex=True, include_dev=False, json=True, estimate=None, merge=[])
    monkeypatch.setattr(measurement, "host", lambda: "M5")
    assert costs.run(args) == 0
    export = tmp_path / "m5.json"
    write(export, json.loads(capsys.readouterr().out))
    monkeypatch.setattr(measurement, "host", lambda: "M1")
    args.merge = [str(export)]
    assert costs.run(args) == 0
    merged = json.loads(capsys.readouterr().out)
    assert len(merged["rows"]) == 2
    assert merged["measures"]["closed_rounds"] == 2
    assert merged["measures"]["median_agent_output_tokens_per_round"] == 100
    write(export, merged)
    assert costs.run(args) == 0
    assert len(json.loads(capsys.readouterr().out)["rows"]) == 2
    args.since = "2026-10-02"
    assert costs.run(args) == 2
    assert "settings differ" in capsys.readouterr().err


def test_codex_javascript_command_literals():
    assert costs._codex_command({"type": "custom_tool_call", "input":
        'await tools.exec_command({cmd: "annotate workspace --json"})'}) == "annotate workspace --json"
    assert costs._codex_command({"type": "custom_tool_call", "input":
        "await tools.exec_command({cmd: 'annotate plan alpha/workspace main'})"}) == "annotate plan alpha/workspace main"
    assert costs.invocations("annotate plan alpha/workspace main") == [("plan", "alpha/workspace main")]


def test_plan_cards_use_their_current_document(tmp_path):
    state = estate(tmp_path)
    evaluation._rebind_roots(state, tmp_path / "no-bus", tmp_path / "none/*.jsonl")
    info = evaluation.collect_slugs()["alpha/workspace"]
    info["comments"][0]["doc"] = "plan:design"
    root = tmp_path / "alpha" / "plans" / "design"
    write(root / "meta.json", {"current": "v1", "history": [{"version": "v1", "ts": "2026-10-02T00:00:00Z"}]})
    (root / "versions").mkdir()
    (root / "versions" / "v1.html").write_text('<h2 id="s:layout">Visual change</h2><img src="proof.png">')
    result = measurement.page_metrics(info, "2026-10-01", "other process")
    assert result["cards"][0]["rail_only"] is False
    assert result["versions"][-1] == {"doc": "plan:design", "version": "v1", "images": 1,
                                      "visual_change_candidate": True, "no_image": False}


def test_transcript_scan_keeps_only_requested_ids_and_new_notices(tmp_path, monkeypatch):
    path = tmp_path / "session.jsonl"
    path.write_text(json.dumps({"type": "assistant", "timestamp": "2026-10-02T00:00:00Z", "message": {
        "content": "abcdef012345 and fedcba987654"}}) + "\n" + json.dumps({"type": "attachment", "timestamp": "2026-10-02T00:01:00Z",
        "rendered": "[annotate] alpha/workspace: 1 reviewer event(s) since your last read"}) + "\n")
    monkeypatch.setattr(evaluation, "TRANSCRIPT_GLOB", str(tmp_path / "*.jsonl"))
    monkeypatch.setattr(evaluation, "CACHE_PATH", str(tmp_path / "no-cache"))
    sightings, file_ids, notices = evaluation.scan_transcripts({"abcdef012345"}, refresh=True)
    assert set(sightings) == {"abcdef012345"}
    assert file_ids[str(path)] == {"abcdef012345"}
    assert len(notices) == 1 and notices[0]["project"] == "alpha"
    assert not (tmp_path / "no-cache").exists()


def test_cli_eval_json_routes_fixture_roots_without_reports(tmp_path):
    import os
    import subprocess
    import sys
    state = estate(tmp_path)
    proc = subprocess.run([sys.executable, "-m", "agent_annotate.cli", "eval", "--json",
        "--since", "2026-10-01", "--state-dir", str(state), "--bus-dir", str(tmp_path / "no-bus"),
        "--transcript-glob", str(tmp_path / "none/*.jsonl"), "--out-dir", str(tmp_path / "unused")],
        capture_output=True, text=True, env=os.environ.copy(), timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["s1_aggregate"]["decision_requests"] == 2
    assert not (tmp_path / "unused").exists()


def test_round_snapshot_without_answer_timestamp_does_not_repeat_store_verdict():
    info = {"events": [], "comments": [{"id": "cid", "decision": {
        "verdict": "accept", "by": "Chang", "ts": "2026-10-02T00:00:00Z"}}], "rounds": [{
            "id": "r1", "by": "Chang", "ts": "2026-10-02T00:01:00Z", "answers": [
                {"comment_id": "cid", "verdict": "accept"}]}]}
    assert len(evaluation.verdict_events(info)) == 1
    assert len(evaluation.section2({"alpha/page": info})) == 1
