"""Twelfth check: Send lists saved notes during a stall, its count follows a cleared draft, Go to it on one click, exact Undo (r12 fix14 send)."""

import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
FRAME = (WEB / "frame.js").read_text()
Q = (WEB / "questions.js").read_text()
REF = (WEB / "reference.js").read_text()
HIST = (WEB / "history.js").read_text()


def grab(src, start, end):
    i = src.index(start)
    return src[i:src.index(end, i) + len(end)]


def node(tmp_path, js):
    exe = shutil.which("node")
    if not exe:
        pytest.skip("node not installed")
    f = tmp_path / "t.js"
    f.write_text(js)
    r = subprocess.run([exe, str(f)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr + r.stdout


def test_saved_notes_list_before_the_read_and_follow_it(tmp_path):
    """Questions 1, running 1: with no read in, the saved notes are the rows; once read, the read replaces them."""
    fn = grab(Q, "  const savedNotes = ", "\n  }")
    node(tmp_path, f"""
const assert = require('assert');
const store = {{}};
const ctx = {{prefs: {{get: (k, d) => k in store ? store[k] : d, set: (k, v) => {{ store[k] = v; }}}}}};
let D = {{version: 'v9', notes: [{{id: 'a', anchor: 'p1', label: 'L', text: 'line', sent: false}}, {{id: 'b', anchor: 'chart:v3', label: 'C', text: 'point', sent: false}}, {{id: 'c', anchor: 'x', text: 'old', sent: true}}]}};
const myNotes = q => D.notes.filter(n => !n.sent);
{fn}
assert.deepStrictEqual(notesNow([]).map(n => n.id), ['a', 'b']);
assert.deepStrictEqual(store['draft:qnotes'].map(n => [n.id, n.i, n.v]), [['a', 1, 'v9'], ['b', 2, 'v9']]);
D = null;  // a reload with the read held
assert.deepStrictEqual(notesNow([]).map(n => n.text), ['line', 'point']);
assert.deepStrictEqual(notesNow([{{note: 'b'}}]).map(n => n.id), ['a']);  // another tab lists it: once
""")


def test_history_lists_saved_chart_notes_while_questions_is_held(tmp_path):
    """Running 1: History's chart notes come from Questions' feed; held, they come from what was saved."""
    fn = grab(HIST, "  const savedC = ctx => {", "return l; };")
    node(tmp_path, f"""
const assert = require('assert');
const store = {{}};
const ctx = {{prefs: {{get: (k, d) => k in store ? store[k] : d, set: (k, v) => {{ store[k] = v; }}}}, data: () => new Promise(() => {{}})}};
let QR = null, QD = {{notes: [{{id: 'c1', anchor: 'chart:v5', label: 'P', text: 'point', sent: false}}]}}, CN = [];
const allC = () => QD.notes;
{fn}
assert.deepStrictEqual(savedC(ctx).map(n => n.id), ['c1']);
QD = null; QR = null;  // a reload with Questions' read held
assert.deepStrictEqual(savedC(ctx).map(n => n.text), ['point']);
""")


def test_send_count_and_rows_share_the_saved_notes():
    assert "+ notesNow(q).length + q.length +" in Q
    items = grab(Q, "function sendItems() {", "\n  }")
    assert "for (const n of notesNow(q))" in items and "n.i" in items
    assert "saved: c => { ctx = ctx || c; return sendCount(); }" in Q
    assert "(D ? D.notes : savedNotes()).find(x => x.id === k.slice(2))" in Q


def test_frame_counts_saved_drafts_until_the_counts_are_in():
    """Reference 1: a cleared draft moves Send at once during a held read; "…" only when nothing is saved."""
    rs = grab(FRAME, "function refreshSend() {", "\n  }")
    assert "const pre = !S.countsIn && sendP.saved;" in rs and "if (S.settling && !pre) return;" in rs
    assert "if (pre) S.warm = n > 0;" in rs and "paintSend();" in rs
    start = FRAME[FRAME.index("async function start()"):]
    assert start.index("S.sendN = savedN(); S.warm = S.sendN > 0;") < start.index("putCounts(await readCounts());")
    assert "'draft:qnotes'" in Q and "draft:.*" in FRAME  # a draft key: follows "Unsent answers and notes"


def test_questions_listens_before_its_reads():
    """Questions 2: Send can open on Questions while render still reads; its Go to it must work on the first click."""
    render = grab(Q, "render: async (el, c, anchor) => {", "await draw();")
    assert render.index("el.onclick = onClick;") < render.index("await c.data('questions'")


def test_undo_puts_back_the_saved_plan_record():
    """Frame 1: the note's plan revision, document and category are kept with it and re-sent by Undo."""
    assert "m: {...noteMeta(n.a), ...(n.v ? {version: n.v} : {})}" in REF
    assert "...(n.m || (D ? noteMeta(n.a) : {}))" in REF
