"""Fix35 Send (r12 audit31 running 1-4, 6; questions 1-3, 6; reference 2-3, 5; frame 1-3, 5): every listed row kind has a
delivery route; what a round delivers is fixed at the round check, so a row changed during Undo stops it and a row changed
after it stays; the clear compares full words; the same lone words are not submitted twice; the receipt stays readable."""

from pathlib import Path

from test_fix13_send import grab, node

WEB = Path(__file__).resolve().parents[2] / "src/agent_annotate/web/proto"
Q = (WEB / "questions.js").read_text()
FRAME = (WEB / "frame.js").read_text()

HARNESS = """
const assert = require('assert');
let toast = '', ROUND = null, handed, calls = [], stops = 0, stale = false, prefs = {};
const WRITING = new Set(), S = {pending: {n: 1}}, D = {notes: [], questions: [], version: 'v'}, NK = {reo: () => ({}), gone: () => {}, loc: () => ({}), L: {}};
const waitMsg = () => 'Reading first', allRead = () => true, settled = () => allRead() && !WRITING.size;
let QI = [];
const Q = () => QI, sendItems = () => QI.map(x => ['G', x.html, 'x:' + x.key, '', false, x.note]);
const draw = async () => {}, relist = () => { stops++; }, refresh = async () => {};
const gen = () => '', typingNote = () => null, abPicks = () => ({}), pl = (n, a, b) => n + ' ' + (n === 1 ? a : b), updateBar = () => {};
const draft = () => ({}), setDraft = () => {}, optLabel = () => '', setAB = () => {}, cut = s => s, fullSig = () => '';
const document = {querySelectorAll: () => []};
const ctx = {takeNow: async () => {}, sig: x => x.say || x.html, prefs: {get: (k, d) => k in prefs ? prefs[k] : d, set: (k, v) => { prefs[k] = v; }},
  toast: (t, o) => { toast = t; }, queueSent: (n, was) => { handed = was; }};
const call = async (p, b) => { calls.push([p, b]); return p === 'api/rounds/submit' ? {comment_ids: [], delivery: 'queued', delivery_id: 'r-' + calls.length} : {}; };
"""


def test_round_check_fixes_what_goes_and_every_row_kind_is_delivered(tmp_path):
    post = grab(Q, "  async function post(", "\n  // Discard all")
    deliv = grab(Q, "  const deliverable = ", ";\n") + ";"
    node(tmp_path, HARNESS + deliv + "\n" + post + """
(async () => {
  // 1: a task comment changed during Undo (past the preview too): the round stops, nothing is sent
  QI = [{key: 'tcm:a', html: 'c', say: 'Task a, comment: long words, new ending'}];
  await post([], [], [], 1, {all: 1, notes: [], keys: new Set(['x:tcm:a']), q: new Map([['tcm:a', 'Task a, comment: long words']]), sig: ''});
  assert.strictEqual(calls.length, 0, 'changed during Undo: no submit'); assert.ok(/Nothing was sent/.test(toast), toast);
  // 3: a lone recovery request and an approval (no say) go in the round's words, so the round stores them
  S.pending = {n: 2};
  QI = [{key: 'tell:x', html: 'About the page that could not load: “Republish it”'}, {key: 'lappr:k', html: 'Kept &amp; doc → <b>approved</b>'}];
  const q = new Map(QI.map(x => [x.key, ctx.sig(x)]));
  await post([], [], [], 2, {all: 2, notes: [], keys: new Set(['x:tell:x', 'x:lappr:k']), q, sig: ''});
  const sub = calls.find(c => c[0] === 'api/rounds/submit');
  assert.ok(sub && /Republish it/.test(sub[1].note) && /Kept & doc → approved/.test(sub[1].note), JSON.stringify(calls));
  assert.ok(/^Sent 2 items/.test(toast), toast); assert.strictEqual(handed, q);
  // frame 3: the same lone words again on the same version are not submitted a second time, and the receipt says so
  S.pending = {n: 2}; calls = [];
  await post([], [], [], 2, {all: 2, notes: [], keys: new Set(['x:tell:x', 'x:lappr:k']), q, sig: ''});
  assert.strictEqual(calls.length, 0, 'no second round'); assert.ok(/^Nothing new was sent/.test(toast), toast);
})().catch(e => { console.error(e); process.exit(1); });
""")


def test_the_clear_keeps_a_row_changed_after_the_check(tmp_path):
    """Running 4, reference 3: the frame hands each tab done(key); a row added or changed after the round check stays."""
    qs = grab(FRAME, "    queued, queueSent: ", "paintSend(); refreshSend(); },").replace("queued, ", "queued: null, ", 1)
    node(tmp_path, """
const assert = require('assert');
let rows = [{key: 'tell:a', html: 'A'}, {key: 'tell:b', html: 'B2'}, {key: 'lappr:c', html: 'C'}], got;
const SRC = [{items: () => rows, sent: (c, was, done) => { got = rows.map(x => done(x.key)); }}];
const prefs = {set: () => {}}, S = {}, sendP = null, paintSend = () => {}, refreshSend = () => {};
const ctx = {sig: x => x.say || x.html};
const o = {""" + qs + """};
o.queueSent(1, new Map([['tell:a', 'A'], ['tell:b', 'B']]));
assert.deepStrictEqual(got, [true, false, false]);
""")
    for f in ["links.js", "history.js", "reference.js", "running.js"]:
        assert "was, done) =>" in (WEB / f).read_text(), f


def test_a_receipt_stays_readable():
    """Running 6: a plain toast after the receipt waits until it has shown."""
    t = grab(FRAME, "  function toast(msg, opts = {}) {", "\n  }")
    assert "if (!opts.undo && !opts.hold && wait > 0) { setTimeout(() => toast(msg, opts), wait); return; }" in t
    assert "{inert: true, hold: 4000}" in Q
    # frame 2: an open Edit goes only when the sheet listed its row
    assert "listed.keys.has('n:' + ed.edit)" in Q
