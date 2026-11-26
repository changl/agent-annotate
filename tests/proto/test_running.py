"""Running and Analytics data module: parsing, masking and the minute cache. No live system is touched."""
import json
import os
import time

from agent_annotate.proto_data import running as R


def test_waits_on_him_reads_the_board_notes():
    assert R.waits_on_him("BLOCKED BY: Chang merge approval", "Land the fix") == ("waits for your yes to merge it", True)
    assert R.waits_on_him("BLOCKED BY Chang - phone session needed")[0] == "needs your phone for a short test session"
    # r13 running 6: a row waiting on his phone, a sign-in or a choice carries no merge mark, even when "merge" is in its notes
    assert R.waits_on_him("BLOCKED BY: Chang card (merge both phones), then the phone session") == ("needs your phone for a short test session", False)
    assert R.waits_on_him("BLOCKED BY: Chang picks the plan before merge")[1] is False
    assert R.waits_on_him("BLOCKED BY: another task") is None
    assert R.waits_on_him("") is None


def test_mask_hides_email_addresses_everywhere():
    out = R.mask({"a": ["run by someone.real@gmail.com today"], "b": {"c": "x@y.io"}, "n": 3})
    assert out == {"a": ["run by member@example.com today"], "b": {"c": "member@example.com"}, "n": 3}


def test_only_orcas_read_only_lists_may_run():
    import pytest
    for argv in (["orca", "orchestration", "send", "--type", "worker_done"], ["orca", "terminal", "send"], ["orca", "worktree", "list"]):
        with pytest.raises(PermissionError):
            R.run_json(argv)


def test_every_worker_draws_as_a_full_tile():
    # the mock shows model, run time, last sign of life, report and Open terminal on every tile; no squares past 12 (finding 3)
    from pathlib import Path
    js = (Path(R.__file__).parents[1] / "web" / "proto" / "running.js").read_text()
    assert "square(" not in js and "wsqi" not in js and "${g.map(tile).join('')}" in js


def test_worker_title_prefers_words_over_codes():
    assert R.wtitle("BD-B5", "## Task: the prototype's Running tab\nmore") == "the prototype's Running tab"
    assert R.wtitle("r10-frame", "Prototype frame") == "Prototype frame"
    assert R.wtitle("Landing fix", "BD-B5") == "Landing fix"


def _page(tmp_path):
    d = tmp_path / "page"
    d.mkdir()
    card = lambda i, v, at: {"id": i, "origin_version": v, "created_at": at,
                              "decision_request": {"requested_at": at, "recommendation": "a",
                                                   "options": [{"id": "a", "label": "Keep it"}, {"id": "b", "label": "Drop it"}]}}
    (d / "comments.json").write_text(json.dumps({"anchors": {"x": [card("c1", "v1", "2026-11-02T10:00:00Z"), card("c2", "v2", "2026-11-02T10:00:00Z")]}}))
    rounds = [{"ts": "2026-11-02T10:20:00Z", "answers": [{"comment_id": "c1", "number": "1", "verdict": "select", "text": "Keep it", "prompt": "Keep?"},
                                                         {"comment_id": "c2", "number": "2", "verdict": "select", "text": "Drop it", "prompt": "Drop?"}]},
              {"ts": "2026-11-03T10:00:00Z", "answers": [{"comment_id": "c2", "number": "2", "verdict": "comment", "text": "why", "prompt": "Drop?"}]}]
    (d / "rounds.ndjson").write_text("\n".join(map(json.dumps, rounds)) + "\n{half a line")
    return d


def test_page_record_counts_picks_time_and_comebacks(tmp_path):
    q, weeks, cb, qpv = R.page_record(_page(tmp_path))
    assert (q["sel"], q["rec"], q["sends"], q["words"]) == (2, 1, 2, 1)
    assert q["ttvMed"] == 20
    assert weeks == [["2026-W45", 2, 1]]
    assert (cb["questions"], cb["oneSend"], cb["sendsHist"]) == (2, 1, [[1, 1], [2, 1]])
    assert qpv == [[1, 1], [2, 1]]


def test_usage_parses_the_daily_reports(tmp_path, monkeypatch):
    (tmp_path / "2026-11-19.md").write_text("Total $617.40 across 12,345 requests\nPeak concurrent workers (any time): 9\nMerged app commits: 14\n"
                                            "Cache writes: x (1.5M / 2.0M tokens)\nBy role: orchestrator $300, design-ui $40\n")
    (tmp_path / "2026-11-18.md").write_text("no totals here")
    monkeypatch.setattr(R, "USAGE", {"fld": tmp_path})
    assert R.usage("fld") == [{"d": "2026-11-19", "usd": 617.4, "req": 12345, "peak": 9, "commits": 14, "cacheM": 3.5,
                               "roles": [["orchestrator", 300], ["design-ui", 40]]}]
    # another project's copy never shows FastLane Drive's reports as its own
    assert R.usage("rebex") == R.usage("annotate") == []


def test_build_serves_the_snapshot_and_refreshes_once_in_the_background(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(R, "_compute", lambda d: calls.append(d) or {"workers": {}, "built": "now"})
    monkeypatch.setattr(R, "_mem", {})
    (tmp_path / R.SNAP).write_text(json.dumps({"workers": {}, "built": "earlier", "proj": "other", "v": R.SNAPV}))
    old = time.time() - 600
    os.utime(tmp_path / R.SNAP, (old, old))
    first = R.build(tmp_path)
    assert first["built"] == "earlier" and first["age"] >= 600
    for _ in range(50):
        if not R._busy:
            break
        time.sleep(0.02)
    assert len(calls) == 1
    assert R.build(tmp_path)["built"] == "now"
    assert json.loads((tmp_path / R.SNAP).read_text())["built"] == "now"


def test_build_computes_on_a_cold_start(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "_compute", lambda d: {"built": "cold"})
    monkeypatch.setattr(R, "_mem", {})
    assert R.build(tmp_path) == {"built": "cold", "age": 0}


def _copy(tmp_path, name, meta, board=None):
    d = tmp_path / name
    d.mkdir()
    (d / "current.meta.json").write_text(json.dumps({"ui": "proto", **meta}))
    if board:
        (d / "project.json").write_text(json.dumps({"board": board}))
    return d


def test_each_copy_is_its_own_project(tmp_path):
    # needs running (fix2/frame): Rebex's copy listed FastLane Drive's beads because the board was hard-coded
    assert R.project(_copy(tmp_path, "proto-rebex", {"name": "Rebex", "proto_copy_of": "rebex"})) == "rebex"
    assert R.project(_copy(tmp_path, "proto-agent-annotate", {"name": "Agent Annotate", "proto_copy_of": "agent-annotate"},
                           {"project": "agent-annotate"})) == "annotate"
    assert R.project(_copy(tmp_path, "fld-proto", {"name": "FastLane Drive (prototype)"}, {"project": "fld"})) == "fld"


def test_board_reads_only_the_board_bd_where_found(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(R, "CHECKOUTS", {"rebex": tmp_path})
    monkeypatch.setattr(R, "run_json", lambda argv, timeout=30: calls.append(argv) or {"path": "/boards/rebex/.beads"})
    where = R.board_dir("rebex")
    assert str(where) == "/boards/rebex" and calls[0] == ["bd", "-C", str(tmp_path), "where", "--json"]
    calls.clear()
    monkeypatch.setattr(R, "run_json", lambda argv, timeout=30: calls.append(argv) or ({"count": 3} if "count" in argv else []))
    R.board("rebex", where)
    assert calls and all(a[:4] == ["bd", "-C", "/boards/rebex", "--readonly"] for a in calls)


def test_no_board_means_empty_sections_and_a_line_never_another_board(tmp_path, monkeypatch):
    def never(*a, **k):
        raise AssertionError("no board may be read")
    monkeypatch.setattr(R, "run_json", never)
    assert R.board_dir("leadory") is None
    monkeypatch.setattr(R, "CHECKOUTS", {"rebex": tmp_path / "gone"})
    assert R.board_dir("rebex") is None
    b = R.board("leadory", None)
    assert (b["tasks"], b["beads"], b["waiting"], b["groups"]) == ([], {}, [], [])
    assert b["none"].startswith("Leadory has no task board")


def test_a_snapshot_of_another_project_is_not_served(tmp_path, monkeypatch):
    d = _copy(tmp_path, "proto-rebex", {"name": "Rebex", "proto_copy_of": "rebex"})
    (d / R.SNAP).write_text(json.dumps({"board": {"tasks": [{"id": "FLD-1"}]}, "built": "old"}))  # written before boards were per project
    monkeypatch.setattr(R, "_compute", lambda p: {"board": {"tasks": []}, "proj": "rebex", "built": "fresh"})
    monkeypatch.setattr(R, "_mem", {})
    assert R.build(d)["built"] == "fresh"
    (d / R.SNAP).write_text(json.dumps({"proj": "rebex", "prs": [{"id": "fld-main #1"}], "built": "old"}))  # before pull requests were per project
    monkeypatch.setattr(R, "_mem", {})
    assert R.build(d)["built"] == "fresh"


def test_jobs_are_tagged_with_their_project():
    assert [R.job_proj(p) for p in ("f/fld_ops/bill_alerts_schedule", "f/sweep/board_checks", "f/test/qlty_version_check",
                                    "u/chang/mac_daily_update", "f/rebex/catalog_sync", "f/misc/thing")] == ["fld", "fld", "annotate", "multimac", "rebex", "other"]


def test_pull_requests_come_from_the_projects_own_repository(monkeypatch):
    calls = []
    monkeypatch.setattr(R, "run_json", lambda argv, timeout=30: calls.append(argv) or [
        {"number": 7, "title": "T", "repository": {"name": "shopify-rebex"}, "state": "open", "updatedAt": "2026-11-20T00:00:00Z", "url": "u"}])
    assert R.prs("rebex")[0]["id"] == "shopify-rebex #7" and calls[0][3:5] == ["--repo", "changl/shopify-rebex"]
    assert R.prs("annotate") and calls[1][3:5] == ["--repo", "changl/agent-annotate"]
    assert R.prs("fld") and calls[2][3:5] == ["--owner", "Fast-Lane-Drive"]
    calls.clear()
    assert R.prs("leadory") == [] and calls == []  # no repository listed: none, never another project's
