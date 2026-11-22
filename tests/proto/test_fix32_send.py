"""Fix32 Send (r12 audit28 running 1, frame 1): a note read in during Send's Undo window that the sheet never listed
stops the round and relists; a round that still carries an id Send never listed (another client's save) counts it."""

from pathlib import Path

from test_fix13_send import grab, node

WEB = Path(__file__).resolve().parents[2] / "src/agent_annotate/web/proto"
Q = (WEB / "questions.js").read_text()


def test_typing_in_the_sheet_uses_the_redraws_gate(tmp_path):
    sc = grab(Q, "  function sheetCount() {", "\n  }")
    node(tmp_path, f"""
const assert = require('assert');
const btn = () => ({{disabled: true, innerHTML: '', textContent: ''}}), el = {{'[data-send]': btn(), '[data-discard]': btn(), h2: btn()}};
const s = {{querySelector: x => el[x] || null}}, host = {{querySelector: () => s}}, root = null, ctx = {{}};
let read = false; const sendCount = () => 1, sendOn = n => !!n && read, gen = () => 'typed', pl = n => n, ic = () => '', updateBar = () => {{}};
{sc}
sheetCount(); assert.ok(el['[data-send]'].disabled && el['[data-discard]'].disabled, 'held or failed read: both stay off');
read = true; sheetCount(); assert.ok(!el['[data-send]'].disabled && !el['[data-discard]'].disabled, 'read in: both on');
""")
    assert sc.count("sendOn(n)") == 2


def test_round_stops_on_an_unlisted_note_and_counts_what_it_carried(tmp_path):
    post = grab(Q, "  async function post(", "\n  // Discard all")
    node(tmp_path, f"""
const assert = require('assert');
let rows = [], round = null, toast = '', posted = 0;
const S = {{pending: {{}}}}, D = {{notes: [], version: 'v'}}, NK = {{reo: () => ({{}}), gone: () => {{}}, L: {{}}}};
const allRead = () => true, sendItems = () => rows, draw = async () => {{}}, relist = () => {{}}, refresh = async () => {{}};
const gen = () => '', typingNote = () => null, abPicks = () => ({{}}), pl = (n, a, b) => n + ' ' + (n === 1 ? a : b), updateBar = () => {{}};
const draft = () => ({{reply: 'r'}}), setDraft = () => {{}}, optLabel = () => '';
const document ={{querySelectorAll: () => []}};
const ctx = {{takeNow: async () => {{}}, prefs: {{get: () => null, set: () => {{}}}}, toast: t => {{ toast = t; }}}};
const call = async p => {{ if (p === 'api/rounds/submit') {{ posted++; return round; }} return {{}}; }};
{post}
(async () => {{
  const listed = {{all: 1, notes: ['a']}};
  // same page: a read during the countdown brought in note b, which Send never listed
  rows = [['Notes', '', 'n:a', 'note:a', false, 'a'], ['Notes', '', 'n:b', 'note:b', false, 'b']];
  await post([], [], [], 1, listed);
  assert.strictEqual(posted, 0, 'nothing goes'); assert.ok(S.armed && /Nothing was sent/.test(toast), 'the sheet relists');
  // a peer's note read in is not his to send: it does not stop the round
  rows = [['Notes', '', 'n:a', 'note:a', false, 'a'], ['Notes', '', 'n:p', '', true, 'p']]; S.pending = {{}};
  round = {{comment_ids: ['a']}}; await post([], [], [], 1, listed);
  assert.strictEqual(posted, 1); assert.ok(/Sent 1 item:/.test(toast), toast);
  // another client saved c during the countdown: the round carried it, and the receipt says so
  rows = [['Notes', '', 'n:a', 'note:a', false, 'a']]; S.pending = {{}};
  round = {{comment_ids: ['a', 'c']}}; await post([], [], [], 1, listed);
  assert.ok(/Sent 2 items:/.test(toast), toast);
  // an answer and a reply on one question are two rows, one id
  rows = []; S.pending = {{}}; round = {{comment_ids: ['q1']}};
  await post([{{id: 'q1'}}], [{{id: 'q1'}}], [], 2, {{all: 2, notes: []}});
  assert.ok(/Sent 2 items:/.test(toast), toast);
}})().catch(e => {{ console.error(e); process.exit(1); }});
""")
