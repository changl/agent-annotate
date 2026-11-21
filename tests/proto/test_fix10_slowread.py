"""r12 fix10 slowread: no read the page waits on at a reload runs the slow bead board (2-14 s) after its first read,
and Rebex's compared-option tables, FastLane Drive's notes and the frame's rows are not parsed again unchanged."""

import calendar
import json
import threading
import time

from agent_annotate.proto_data import frame, questions, reference


class _Slow:
    """A stand-in for `bd`: counts its calls; each takes `wait` seconds and names every asked id 'open'."""

    def __init__(self, wait=0.0):
        self.calls, self.wait = [], wait

    def __call__(self, argv, **k):
        self.calls.append(argv)
        time.sleep(self.wait)
        ids = [a for a in argv if a.startswith("FLD-")]
        return type("R", (), {"stdout": json.dumps([{"id": i, "title": "T " + i, "status": "open"} for i in ids])})()


def _fresh_board(monkeypatch, tmp_path, run):
    monkeypatch.setattr(questions, "BOARD", str(tmp_path))
    monkeypatch.setattr(questions, "_board", {"at": 0.0, "asked": set(), "beads": {}, "busy": False})
    monkeypatch.setattr(questions.subprocess, "run", run)


def test_question_tasks_wait_only_for_ids_never_asked(tmp_path, monkeypatch):
    run = _Slow()
    _fresh_board(monkeypatch, tmp_path, run)
    assert questions._beads({"FLD-a"}, tmp_path) == {"FLD-a": {"title": "T FLD-a", "status": "open", "state": "waiting"}}
    assert questions._beads({"FLD-a"}, tmp_path)["FLD-a"]["title"] == "T FLD-a" and len(run.calls) == 1  # fresh: no read
    questions._beads({"FLD-a", "FLD-b"}, tmp_path)  # a new id waits for its own read, of it alone
    assert len(run.calls) == 2 and "FLD-a" not in run.calls[1] and "FLD-b" in run.calls[1]


def test_a_stale_board_answers_at_once_and_reads_again_behind(tmp_path, monkeypatch):
    run = _Slow()
    _fresh_board(monkeypatch, tmp_path, run)
    questions._beads({"FLD-a"}, tmp_path)
    questions._board["at"] -= 120  # over a minute old
    run.wait = 1.0
    t = time.monotonic()
    got = questions._beads({"FLD-a"}, tmp_path)
    assert time.monotonic() - t < 0.5 and got["FLD-a"]["title"] == "T FLD-a"  # the last read, at once
    for _ in range(40):
        if not questions._board["busy"]:
            break
        time.sleep(0.05)
    assert len(run.calls) == 2 and time.time() - questions._board["at"] < 5  # read again in the background


def test_a_restarted_server_starts_from_the_saved_read(tmp_path, monkeypatch):
    run = _Slow()
    _fresh_board(monkeypatch, tmp_path, run)
    questions._beads({"FLD-a"}, tmp_path)
    _fresh_board(monkeypatch, tmp_path, run)  # as after a restart: nothing in memory
    assert questions._beads({"FLD-a"}, tmp_path)["FLD-a"]["title"] == "T FLD-a" and len(run.calls) == 1


def test_reference_board_reads_once_then_never_waits(monkeypatch):
    lists = []
    gate = threading.Event()

    def run(argv, **k):
        lists.append(argv)
        if len(lists) > 1:
            gate.wait(5)
        return type("R", (), {"stdout": json.dumps([{"id": "RBX-1", "title": f"T{len(lists)}", "status": "open"}])})()
    monkeypatch.setattr(reference, "_boards", {})
    monkeypatch.setattr(reference.running, "board_dir", lambda code: "/boards/" + code)
    monkeypatch.setattr(reference.subprocess, "run", run)
    assert reference.board("rebex") == {"RBX-1": ["T1", "open"]}
    reference._boards["rebex"]["at"] -= 120
    t = time.monotonic()
    assert reference.board("rebex") == {"RBX-1": ["T1", "open"]} and time.monotonic() - t < 0.5  # the background read is held
    gate.set()
    for _ in range(40):
        if reference.board("rebex") == {"RBX-1": ["T2", "open"]}:
            break
        time.sleep(0.05)
    assert reference.board("rebex") == {"RBX-1": ["T2", "open"]} and len(lists) == 2


def test_compared_options_skip_other_tables_and_read_each_file_once(tmp_path, monkeypatch):
    f = tmp_path / "v1.md"
    f.write_text("# Pick\n| Option | Cost |\n|---|---|\n| A | 1 |\n\n# Other\n| Name | Size |\n|---|---|\n| x | 2 |\n")
    cleaned = []
    monkeypatch.setattr(reference, "plain", lambda s, n=200: cleaned.append(s) or s)
    assert reference._opt_tables(f) == [["Pick", ["Option", "Cost"], [["A", "1"]]]]
    assert "x" not in cleaned  # the other table's rows are never cleaned
    n = len(cleaned)
    got = reference._opt_tables(f)
    got[0][0] = "renamed"
    assert len(cleaned) == n and reference._opt_tables(f)[0][0] == "Pick"  # cached, and a caller's rename stays its own


def test_first_reading_waits_on_questions_alone():
    """Only Questions' read runs before the first reading; the version waits for its counts with no cap (audit9 frame 2)."""
    from pathlib import Path
    js = (Path(frame.__file__).parents[1] / "web" / "proto" / "frame.js").read_text()
    assert "(t.key === 'questions' ? Promise.resolve() : firstIn).then(() => t.chip(ctx))" in js
    start = js[js.index("async function start()"):]
    assert start.index("putCounts(await readCounts());") < start.index("firstRead();") and "Promise.race([readCounts()" not in js
    # a stuck read fails at 20 s and the tab offers Try again (audit9 reference)
    assert "Promise.race([api(`proto/data/${area}.json`), late()])" in js and "data-again>Try again" in js


def test_frame_row_follows_its_files(tmp_path):
    d = tmp_path / "page"
    (d / "versions").mkdir(parents=True)
    (d / "current.meta.json").write_text(json.dumps({"current": "v1", "history": [{"version": "v1", "ts": "2026-11-20T10:00:00Z"}]}))
    (d / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {}}))
    now = time.time()
    assert frame._page(d, now)["waiting"] == 0
    (d / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {"d:q1": [
        {"id": "c1", "number": 1, "version": "v1", "anchor_id": "d:q1", "author": "agent:x", "status": "open", "text": "Q?",
         "decision_request": {"prompt": "Q?", "options": [{"id": "a", "label": "A"}]}}]}}))
    assert frame._page(d, now)["waiting"] == 1  # a new question shows at the next read
    was = calendar.timegm(time.strptime("2026-11-20T10:00:00", "%Y-%m-%dT%H:%M:%S"))  # the reading it replaces
    assert frame._ts("2026-11-20T10:00:00Z") == frame._ts("2026-11-20T10:00:00") == was and frame._ts("bad") is None
