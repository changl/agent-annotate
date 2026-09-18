"""`annotate eval` runs read-only over a fixture estate and reports a headline.

It is exec'd, never imported by the CLI, so a measurement cannot advance the
cursor it is measuring; the fixture must come out byte-identical.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from agent_annotate import cli


def _estate(tmp_path):
    state = tmp_path / "state"
    bus_root = tmp_path / "bus"
    slug_dir = tmp_path / "pages" / "demo"
    (bus_root / "proj").mkdir(parents=True)
    slug_dir.mkdir(parents=True)
    (state / "logs").mkdir(parents=True)
    (state / "proj.json").write_text(json.dumps({"project": "proj", "slugs": {"demo": {
        "slug": "demo", "slug_dir": str(slug_dir), "project": "proj", "url": "http://localhost:8899/",
        "started_at": "2026-09-10T00:00:00Z", "transport": "local",
        "bus_file": str(bus_root / "proj" / "demo.ndjson")}}}))
    (slug_dir / "current.meta.json").write_text(json.dumps({
        "current": "v1", "history": [{"version": "v1", "ts": "2026-09-10T00:00:00Z", "label": "initial"}]}))
    (slug_dir / "comments.json").write_text(json.dumps({
        "schema_version": 2,
        "anchors": {
            "s:a": [{"id": "aaaaaaaaaaaa", "anchor_id": "s:a", "text": "A?", "status": "user_confirmed",
                     "author": "agent:test", "created_at": "2026-09-10T00:00:00Z", "version": "v1",
                     "decision_request": {"prompt": "A?", "recommendation": "accept",
                                          "requested_at": "2026-09-10T00:00:00Z"},
                     "decision": {"verdict": "accept", "text": None, "ts": "2026-09-10T00:10:00Z",
                                  "by": "r@x", "latency_s": 600.0}}],
            "s:b": [{"id": "bbbbbbbbbbbb", "anchor_id": "s:b", "text": "B?", "status": "open",
                     "author": "agent:test", "created_at": "2026-09-10T00:00:00Z", "version": "v1",
                     "decision_request": {"prompt": "B?"}}],
        },
        "archived": {},
    }))
    events = [
        {"ts": "2026-09-10T00:00:00Z", "event": "comment_created", "slug": "demo",
         "comment_id": "aaaaaaaaaaaa", "anchor_id": "s:a", "author": "agent:test", "version": "v1"},
        {"ts": "2026-09-10T00:00:00Z", "event": "comment_created", "slug": "demo",
         "comment_id": "bbbbbbbbbbbb", "anchor_id": "s:b", "author": "agent:test", "version": "v1"},
        {"ts": "2026-09-10T00:10:00Z", "event": "comment_updated", "slug": "demo",
         "comment_id": "aaaaaaaaaaaa", "anchor_id": "s:a", "author": "r@x", "decision": "accept"},
        {"ts": "2026-09-10T00:10:00Z", "event": "session_push", "slug": "demo",
         "comment_ids": ["aaaaaaaaaaaa"], "author": "r@x", "delivery": "queued"},
        {"ts": "2026-09-10T00:20:00Z", "event": "comment_reply", "slug": "demo",
         "comment_id": "aaaaaaaaaaaa", "anchor_id": "s:a", "author": "agent:test"},
    ]
    (bus_root / "proj" / "demo.ndjson").write_text("".join(json.dumps(e) + "\n" for e in events))
    return state, bus_root


def _digest(root: Path) -> dict:
    """Every runtime file: registry, buses, stores. The transcript scan cache
    under <state>/logs is eval's own and is excluded."""
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and "logs" not in p.parts:
            out[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def test_eval_module_reports_the_fixture_and_writes_nothing_into_it(tmp_path):
    state, bus_root = _estate(tmp_path)
    before = {**_digest(bus_root), **_digest(tmp_path / "pages"), **_digest(state)}
    out_dir = tmp_path / "out"
    proc = subprocess.run(
        [sys.executable, "-m", "agent_annotate.eval", "--since", "2026-09-01",
         "--state-dir", str(state), "--bus-dir", str(bus_root),
         "--transcript-glob", str(tmp_path / "no-transcripts" / "*.jsonl"),
         "--out-dir", str(out_dir)],
        capture_output=True, text=True, timeout=60, env=os.environ.copy())
    assert proc.returncode == 0, proc.stderr

    report = json.loads((out_dir / "eval-baseline.json").read_text())
    agg = report["s1_aggregate"]
    assert report["meta"]["slugs_total"] == 1 and report["meta"]["slugs_in_window"] == 1
    assert agg["decision_requests"] == 2
    assert agg["verdicts"]["accept"] == 1 and agg["verdicts"]["none"] == 1
    assert agg["reviewer_events"] == 1          # session_push is machinery
    assert agg["agent_events"] == 4
    assert agg["time_to_verdict_median"] == 10.0
    assert (out_dir / "eval-baseline.md").read_text().startswith("#")
    assert {**_digest(bus_root), **_digest(tmp_path / "pages"), **_digest(state)} == before


def test_cli_eval_prints_a_headline(tmp_path, monkeypatch, capsys):
    state, bus_root = _estate(tmp_path)
    monkeypatch.setenv("ANNOTATE_STATE_DIR", str(state))
    monkeypatch.setenv("ANNOTATE_BUS_ROOT", str(bus_root))
    out_dir = tmp_path / "out"
    rc = cli.cmd_eval(SimpleNamespace(since="2026-09-01", out_dir=str(out_dir), refresh_transcripts=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert "annotate eval" in out
    assert "2 decision requests" in out
    assert "1 accept, 0 reject, 0 changes, 1 undecided, 0 closed" in out
