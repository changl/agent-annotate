"""Running and Analytics data module: parsing, masking and the minute cache. No live system is touched."""
import json
import os
import time

from agent_annotate.proto_data import running as R


def test_waits_on_him_reads_the_board_notes():
    assert R.waits_on_him("BLOCKED BY: Chang merge approval", "Land the fix") == ("waits for your yes to merge it", True)
    assert R.waits_on_him("BLOCKED BY Chang - phone session needed")[0] == "needs your phone for a short test session"
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
    monkeypatch.setattr(R, "USAGE", tmp_path)
    assert R.usage() == [{"d": "2026-11-19", "usd": 617.4, "req": 12345, "peak": 9, "commits": 14, "cacheM": 3.5,
                          "roles": [["orchestrator", 300], ["design-ui", 40]]}]


def test_build_serves_the_snapshot_and_refreshes_once_in_the_background(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(R, "_compute", lambda d: calls.append(d) or {"workers": {}, "built": "now"})
    monkeypatch.setattr(R, "_mem", {})
    (tmp_path / R.SNAP).write_text(json.dumps({"workers": {}, "built": "earlier"}))
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
