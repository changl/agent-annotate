"""r12 fix12 perf: on a busy host the first reading must not wait on work the server does per request. Answers are
prepared when the page changes, the frame's 40-page re-read runs behind, and the page paints the last reading at once."""

import json
import threading
import time
from pathlib import Path

import agent_annotate.proto_data as P
from agent_annotate.proto_data import frame, questions, running


def _page(tmp_path):
    d = tmp_path / "page"
    (d / "versions").mkdir(parents=True)
    (d / "current.meta.json").write_text(json.dumps({"current": "v1", "history": [{"version": "v1", "ts": "2026-11-20T10:00:00Z"}]}))
    (d / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {}}))
    (d / "versions" / "v1.html").write_text("<p>v1</p>")
    return d


def test_questions_answer_is_prepared_once_until_the_page_changes(tmp_path, monkeypatch):
    d = _page(tmp_path)
    built = []
    real = questions.build
    monkeypatch.setattr(questions, "build", lambda p: built.append(1) or real(p))
    first = P.prepared("questions", d)
    assert P.prepared("questions", d) == first and len(built) == 1  # the same bytes, not built again
    (d / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {"d:q1": [
        {"id": "c1", "number": 1, "version": "v1", "anchor_id": "d:q1", "author": "agent:x", "status": "open", "text": "Q?",
         "decision_request": {"prompt": "Q?", "options": [{"id": "a", "label": "A"}]}}]}}))
    assert json.loads(P.prepared("questions", d))["questions"][0]["prompt"] == "Q?" and len(built) == 2  # a new question: built again


def test_questions_stamp_moves_only_when_the_tasks_change(tmp_path, monkeypatch):
    d = _page(tmp_path)
    monkeypatch.setattr(questions, "_board", {"at": 0.0, "asked": set(), "beads": {}, "busy": False})
    s = questions.stamp(d)
    questions._store(d, {"FLD-a"}, {"FLD-a": {"title": "T", "status": "open", "state": "waiting"}})
    s2 = questions.stamp(d)
    assert s2 != s
    questions._store(d, {"FLD-a"}, {"FLD-a": {"title": "T", "status": "open", "state": "waiting"}})  # the minute's read, unchanged
    assert questions.stamp(d) == s2


def test_running_sends_the_same_bytes_until_a_new_build(tmp_path, monkeypatch):
    monkeypatch.setattr(running, "_mem", {str(tmp_path): (time.time(), {"built": "now", "big": "x" * 1000})})
    monkeypatch.setattr(running, "project", lambda d: "fld")
    dumps = []
    real = P.json.dumps
    monkeypatch.setattr(P.json, "dumps", lambda *a, **k: dumps.append(1) or real(*a, **k))
    assert P.prepared("running", tmp_path) == P.prepared("running", tmp_path) and len(dumps) == 1


def test_reference_is_built_once_until_a_note_or_plan_changes(tmp_path, monkeypatch):
    from agent_annotate.proto_data import reference
    d = _page(tmp_path)
    built = []
    monkeypatch.setattr(reference, "_build", lambda p: built.append(1) or {"n": len(built)})
    assert reference.build(d) == reference.build(d) == {"n": 1} and reference.stamp(d) == reference.stamp(d)
    (d / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {"ref:x": []}}))
    assert reference.build(d) == {"n": 2}  # a Reference note shows at once
    (d / "plans" / "p1").mkdir(parents=True)
    (d / "plans" / "p1" / "meta.json").write_text("{}")
    assert reference.build(d) == {"n": 3}  # so does a new plan


def test_frame_never_waits_on_the_other_pages_re_read(tmp_path, monkeypatch):
    d = _page(tmp_path)
    gate = threading.Event()
    calls = []
    monkeypatch.setattr(frame, "_root", lambda: tmp_path / "none")
    monkeypatch.setattr(frame, "_projects", lambda now: calls.append(1) or (gate.wait(5), [])[1])
    monkeypatch.setitem(frame._cache, str(tmp_path / "none"), (time.time() - 120, []))
    t = time.monotonic()
    assert frame.build(d)["waiting"] == 0 and time.monotonic() - t < 0.5  # a minute old: answered at once
    frame.build(d)
    assert calls == [1]  # one re-read behind at a time
    gate.set()


def test_frame_day_columns_follow_the_clock_without_reading_again(tmp_path, monkeypatch):
    d = _page(tmp_path)
    reads = []
    real = frame._page_read
    monkeypatch.setattr(frame, "_page_read", lambda p: reads.append(1) or real(p))
    at = frame._ts("2026-11-20T10:00:00Z")
    assert frame._page(d, at + 3600)["vday"][-1] == 1
    assert frame._page(d, at + 86400 + 3600)["vday"][-2] == 1 and len(reads) == 1  # a day later: one column on, same files


def test_scrub_checks_a_body_once():
    body = json.dumps({"a": "nothing to hide " * 50})
    P.scrub_json(body)
    seen = []
    real = P.scrub
    P.scrub = lambda *a, **k: seen.append(1) or real(*a, **k)
    try:
        assert P.scrub_json(body) == body and not seen
        assert "member@example.com" in P.scrub_json(json.dumps({"a": "x@real-mail.com"}))
    finally:
        P.scrub = real


def test_area_reads_carry_the_servers_own_time(tmp_path):
    d = _page(tmp_path)
    got = {}

    class H:
        artifact_dir, skill_dir = d, None
        _identity, _reviewer_authors = (lambda self: {"email": None}), (lambda self, a: {a})

        def _respond(self, code, body, *a, **k):
            got.update(code=code, headers=k.get("extra_headers") or {})
    P.serve(H(), "/proto/data/questions.json")
    assert got["code"] == 200 and got["headers"]["Server-Timing"].startswith("build;dur=")


def test_first_reading_paints_the_last_reading_and_starts_questions_early():
    js = (Path(frame.__file__).parents[1] / "web" / "proto" / "frame.js").read_text()
    start = js[js.index("async function start()"):]
    # Questions' read and the tab scripts start before the frame's five reads are awaited
    assert start.index("pre.questions = api('proto/data/questions.json')") < start.index("await Promise.all([api.meta()")
    assert start.index("const scripts = Promise.all(") < start.index("await Promise.all([api.meta()")
    # the same version's last reading paints with its counts, only while drafts are kept
    assert "remember('drafts') && meta && prefs.get('firstPaint', null)" in start and "was.v === meta.current" in start
    assert start.index("if (S.loadedV || S.warm) { drawTop(); drawFab(); }") < start.index("putCounts(await readCounts());")
    assert "prefs.set('firstPaint'" in js
