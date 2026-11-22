"""Fix33 Send (r12 audit29 running 1, 2; questions 1): one read state for every feed read, one round check against every
source, and a receipt that counts only listed rows and the extra ids the round carried."""

from pathlib import Path

from test_fix13_send import grab, node

WEB = Path(__file__).resolve().parents[2] / "src/agent_annotate/web/proto"
Q = (WEB / "questions.js").read_text()
FRAME = (WEB / "frame.js").read_text()


def test_every_feed_read_goes_through_the_one_read_state(tmp_path):
    """Running 2: a warm Pages & links refresh, held then failed, turns Send off with its warning; Try again recovers."""
    assert "if (sendP && sendP.read) sendP.read(area, p);" in grab(FRAME, "  const data = (area, fresh) => {", "\n  };")
    assert "read: track," in Q
    state = grab(Q, "  const RS = {}", "  const allRead = () => !!(oin() && qIn());")
    node(tmp_path, f"""
const assert = require('assert');
let D = {{v: 0}}, stale = false, reading = null, redraws = 0; const relist = () => {{ redraws++; }};
{state}
const tick = () => new Promise(r => setTimeout(r, 0));
(async () => {{
  for (const a of ['questions', 'reference', 'links']) track(a, Promise.resolve());
  await tick(); assert.ok(allRead(), 'first reads in');
  for (const a of ['links', 'reference', 'questions']) {{
    let fail; const p = new Promise((_, no) => {{ fail = no; }});
    track(a, p); track(a, p);  // the frame's hook and the tab's own call: one read
    await tick(); assert.ok(!allRead(), a + ' held: Send off');
    fail(Error('503')); await tick();
    assert.ok(!allRead(), a + ' failed: Send off');
    assert.ok(a === 'questions' ? qerr() : oerr() === (a === 'links' ? 'Pages &amp; links' : 'Reference'), a + ' named');
    const before = redraws; track(a, Promise.reject(Error('503'))); await tick();
    assert.strictEqual(redraws, before, a + ': a redraw re-reading a failed feed never loops'); assert.ok(!allRead());
    retry(a); track(a, new Promise(() => {{}})); await tick(); assert.ok(!allRead() && rs(a) === 'held', a + ' Try again: held');
    track(a, Promise.resolve()); await tick(); assert.ok(allRead(), a + ' Try again: on');
  }}
  track('running', new Promise(() => {{}})); await tick(); assert.ok(allRead(), 'other areas are not Send feeds');
}})().catch(e => {{ console.error(e); process.exit(1); }});
""")


def test_round_stops_on_a_typed_note_or_a_write_on_its_way(tmp_path):
    """Running 1, Questions 1: an editor typed into during Undo, or a save still in flight, stops the round; a listed typed
    note's id counts as its own row, so the receipt says what the round carried."""
    assert "if (write && sendP && sendP.writing) sendP.writing(path, go);" in FRAME
    post = grab(Q, "  async function post(", "\n  // Discard all")
    deliv = grab(Q, "  const deliverable = ", ";\n")
    node(tmp_path, f"""
const assert = require('assert');
let rows = [], round = null, toast = '', posted = 0, tn = null;
const WRITING = new Set(), S = {{pending: {{}}}}, D = {{notes: [], version: 'v'}}, NK = {{reo: () => ({{}}), gone: () => {{}}, L: {{}}}};
const allRead = () => true, sendItems = () => rows, draw = async () => {{}}, relist = () => {{}}, refresh = async () => {{}};
const gen = () => '', typingNote = () => tn, abPicks = () => ({{}}), pl = (n, a, b) => n + ' ' + (n === 1 ? a : b), updateBar = () => {{}};
const draft = () => ({{reply: 'r'}}), setDraft = () => {{}}, optLabel = () => '';
const document = {{querySelectorAll: () => []}};
const ctx = {{takeNow: async () => {{}}, prefs: {{get: () => null, set: () => {{}}}}, toast: t => {{ toast = t; }}}};
const call = async p => {{ if (p === 'api/rounds/submit') {{ posted++; return round; }} return p === 'api/comments' ? {{id: 't'}} : {{}}; }};
{deliv};
{post}
(async () => {{
  const listed = {{all: 1, notes: ['a'], keys: new Set(['n:a'])}};
  // the editor opened and typed in during Undo: its row is unlisted
  rows = [['Notes', '', 'n:a', 'note:a', false, 'a'], ['Notes', '', 'nn:', 'newnote:']];
  await post([], [], [], 1, listed);
  assert.strictEqual(posted, 0, 'typed note: nothing goes'); assert.ok(S.armed && /Nothing was sent/.test(toast));
  // a save still in flight at the deadline
  rows = [['Notes', '', 'n:a', 'note:a', false, 'a']]; S.pending = {{}}; WRITING.add(1);
  await post([], [], [], 1, listed);
  assert.strictEqual(posted, 0, 'write on its way: nothing goes'); WRITING.clear();
  // relisted: the typed note is a listed row, and its id is that row, not an extra
  rows = [['Notes', '', 'n:a', 'note:a', false, 'a'], ['Notes', '', 'nn:', 'newnote:']]; tn = {{text: 'x', anchor: 'p'}}; S.pending = {{}};
  round = {{comment_ids: ['a', 't']}}; await post([], [], [], 2, {{all: 2, notes: ['a'], keys: new Set(['n:a', 'nn:'])}});
  assert.strictEqual(posted, 1); assert.ok(/Sent 2 items:/.test(toast), toast);
}})().catch(e => {{ console.error(e); process.exit(1); }});
""")


def test_discard_and_typing_share_the_gate():
    assert "if (t.hasAttribute('data-discard')) return sendOn(sendCount()) && discardAll();" in Q
    assert "const qIn = () => !!(D && !stale && !reading && !['held', 'failed'].includes(rs('questions')));" in Q
