"""Round 13 frame: state colours as the mock (3), questions-waiting wording (5, 11), empty History dimmed (7),
no floating Send while the first read is in (14), and a board read that survives a Dolt timeout (11)."""
import re
import time

from agent_annotate.proto_data import running as R
from test_fix14_frame import FRAME, RUN, WEB, grab, node

TOKENS = (WEB / "tokens.css").read_text()
HIST = (WEB / "history.js").read_text()


def test_state_colours_are_the_mocks():
    assert "--st-done:var(--ok-text);--st-progress:#6250d6;--st-waiting:var(--color-primary);" in TOKENS
    assert "--st-none:var(--muted);" in TOKENS and "--color-info" not in TOKENS.split("--st-done", 1)[1].split("}", 1)[0]
    assert re.search(r"\[data-theme=dark\]\{[^}]*--st-progress:#9085e9", TOKENS)


def test_waiting_counts_say_questions_and_the_merge_note_stays():
    assert FRAME.count("pl(x.waiting, 'question waiting', 'questions waiting')") == 1
    assert "pl(w, 'question waiting', 'questions waiting')" in FRAME and "${w} waiting" not in FRAME
    assert "<b class=\"err-t\">${pl(r.waiting, 'question', 'questions')}</b>" in FRAME
    assert "; the orchestrator merges every other change itself" in RUN


def test_history_with_nothing_sent_is_dimmed_nothing_yet(tmp_path):
    chip = grab(HIST, "chip: async ctx =>", "}});")[len("chip: "):-3]
    node(tmp_path, f"""
const assert = require('assert');
const chip = {chip};
(async () => {{
  assert.deepStrictEqual(await chip({{data: async () => ({{count: 0}})}}), {{empty: true}});
  assert.strictEqual((await chip({{data: async () => ({{count: 1560}})}})).text, (1560).toLocaleString());
}})().catch(e => {{ console.error(e); process.exit(1); }});
""")


def test_phone_send_floats_only_once_something_is_ready(tmp_path):
    fab = grab(FRAME, "  function drawFab() {", "\n  }\n")
    node(tmp_path, f"""
const assert = require('assert');
const I = n => '', pl = (n, a, b) => n + ' ' + (n === 1 ? a : b), SENDTIP = {{'…': 'reading', '?': 'not read'}};
const el = {{hidden: false, innerHTML: '', classList: {{toggle() {{}}}}, setAttribute() {{}}, removeAttribute() {{}}}};
const document = {{getElementById: () => el}};
let st = '…', n = 0; const sendSt = () => st, sendNum = () => n; const S = {{home: false, other: null, menu: null}};
{fab}
drawFab(); assert.strictEqual(el.hidden, true);   // the first read is in: nothing floats
st = ''; drawFab(); assert.strictEqual(el.hidden, true);  // nothing ready
n = 1; drawFab(); assert.strictEqual(el.hidden, false);   // a draft: Send 1 floats
st = '?'; n = 0; drawFab(); assert.strictEqual(el.hidden, false);  // the read failed: it still opens
""")


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
