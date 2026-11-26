"""Round 13 frame 11: one Dolt timeout no longer drops the board, and a failed refresh keeps the Waiting count."""
import time

from agent_annotate.proto_data import running as R


def test_a_bd_read_that_times_out_once_is_tried_again(monkeypatch):
    monkeypatch.setattr(R, "BD_TRIES", (0, 0, 0))
    calls = []

    def flaky(argv, timeout=30):
        calls.append(argv)
        if len(calls) < 3:
            raise RuntimeError("[mysql] packets.go:58 read tcp: i/o timeout")
        return {"count": 1}
    monkeypatch.setattr(R, "run_json", flaky)
    assert R.bd_json(["bd", "count"]) == {"count": 1} and len(calls) == 3


def test_the_board_location_survives_a_bd_where_that_does_not_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "BD_TRIES", (0,))
    monkeypatch.setattr(R, "CHECKOUTS", {"rebex": tmp_path})
    monkeypatch.setattr(R, "_where", {})
    monkeypatch.setattr(R, "run_json", lambda argv, timeout=30: {"path": "/boards/rebex/.beads"})
    assert str(R.board_dir("rebex")) == "/boards/rebex"

    def down(*a, **k):
        raise RuntimeError("i/o timeout")
    monkeypatch.setattr(R, "run_json", down)
    assert str(R.board_dir("rebex")) == "/boards/rebex"


def test_a_failed_refresh_keeps_the_last_board_marked_stale_and_reads_again(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "_mem", {})
    good = {"board": {"waiting": [["b-1", "waits", False]], "ready": 4, "tasks": []}, "built": "2026-11-25T22:30:00Z"}
    bad = {"board": {"error": "RuntimeError: i/o timeout"}, "built": "2026-11-25T22:41:00Z"}
    answers = [good, bad]
    monkeypatch.setattr(R, "_compute", lambda p: answers.pop(0))
    R._refresh(tmp_path)
    R._refresh(tmp_path)
    b = R._mem[str(tmp_path)][1]["board"]
    assert b["waiting"] == [["b-1", "waits", False]] and b["ready"] == 4 and "error" not in b
    assert b["stale"] == "RuntimeError: i/o timeout" and b["read"] == "2026-11-25T22:30:00Z"
    started = []
    monkeypatch.setattr(R.threading, "Thread", lambda target, args, daemon: type("T", (), {"start": lambda s: started.append(args)})())
    R._behind(tmp_path, (time.time(), {"board": b}))
    R._busy.discard(str(tmp_path))
    assert started == [(tmp_path,)]


def test_a_board_never_read_still_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "_mem", {})
    monkeypatch.setattr(R, "_compute", lambda p: {"board": {"error": "RuntimeError: x"}, "built": "t"})
    R._refresh(tmp_path)
    assert R._mem[str(tmp_path)][1]["board"] == {"error": "RuntimeError: x"}
