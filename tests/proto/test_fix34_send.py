"""Fix34 Send (r12 audit30 frame 1-4, 6; questions 1-4; reference): every note write goes through the frame's one
wrapper; the round check runs after pending removals settle, right before the submit; once a round is going, a note write
of this tab's waits for it; Undo never comes back; a listed typed draft on another tab is saved by Send before the round."""

from pathlib import Path

from test_fix13_send import grab, node

WEB = Path(__file__).resolve().parents[2] / "src/agent_annotate/web/proto"
Q = (WEB / "questions.js").read_text()
FRAME = (WEB / "frame.js").read_text()


def test_every_note_write_is_tracked_and_held_at_the_wrapper(tmp_path):
    """Frame 1, 3: a reply is a note write like a save; a note write made while a round is going waits for the round."""
    api = grab(FRAME, "  async function api(path, body, method, own) {", "\n  }")
    assert "const hold = write && !own && sendP && sendP.hold ? sendP.hold(path) : null;" in api
    assert api.index("if (hold) await hold;") < api.index("P.copyWrite(path, body, method)") < api.index("const go = fetch(")
    regex = grab(Q, "  const NOTEW = ", ", WRITING")
    node(tmp_path, f"""
const assert = require('assert');
{regex} = new Set();
for (const p of ['api/comments', 'api/comments?author=x', 'api/comments/a', 'api/comments/a?author=x', 'api/comments/a/reply',
  'api/comments/a/reply?author=x', 'api/comments/a/decision', 'api/comments/a/archive', 'api/comments/a/accept',
  'api/comments/a/restore', 'api/comments/a/answer-later']) assert.ok(NOTEW.test(p), p);
for (const p of ['api/rounds/submit', 'api/commentsx', 'api/plan-topics', 'comments.json']) assert.ok(!NOTEW.test(p), p);
""")
    assert "hold: path => NOTEW.test(path) ? ROUND : null," in Q
    assert "writing: (path, p, own) => { if (own || !NOTEW.test(path)) return;" in Q


def test_round_waits_for_removals_then_checks_and_holds_later_writes(tmp_path):
    """Frame 1, Questions 2: a save made after the countdown, while a removal or the round request is held, waits for
    the round: the round carries only what was listed, and the save goes after it."""
    post = grab(Q, "  async function post(", "\n  // Discard all")
    deliv = grab(Q, "  const deliverable = ", ";\n") + ";"
    node(tmp_path, f"""
const assert = require('assert');
let rows = [['Notes', '', 'n:a', 'note:a', false, 'a']], toast = '', log = [], ROUND = null, freeTake, freeRound;
const WRITING = new Set(), S = {{pending: {{n: 1}}}}, D = {{notes: [], version: 'v'}}, NK = {{reo: () => ({{}}), gone: () => {{}}, L: {{}}}};
let stale = false; const waitMsg = () => "Reading first";
const allRead = () => true, settled = () => allRead() && !WRITING.size, Q = () => [];
const sendItems = () => rows, draw = async () => {{}}, relist = () => {{}}, refresh = async () => {{}};
const gen = () => 'fb', typingNote = () => null, abPicks = () => ({{}}), pl = (n, a, b) => n + ' ' + (n === 1 ? a : b), updateBar = () => {{}};
const draft = () => ({{}}), setDraft = () => {{}}, optLabel = () => '';
const document = {{querySelectorAll: () => []}}; let WROTEQ = new Set(), CARRY = null, GOING = null; const made = b => b.anchor_id + '|' + String(b.text || '').trim();
const ctx = {{takeNow: () => new Promise(r => {{ freeTake = r; }}), prefs: {{get: () => null, set: () => {{}}}}, toast: t => {{ toast = t; }}}};
// the frame's wrapper, as far as the round sees it: a write not the round's own waits for ROUND
const api = async (p, own) => {{ if (!own && ROUND) await ROUND; log.push(p);
  if (p === 'api/rounds/submit') return new Promise(r => {{ freeRound = () => r({{comment_ids: ['a']}}); }}); return {{id: 'new'}}; }};
const call = (p, body, method, own) => api(p, own);
{deliv}
const fullSig = () => ''; if (typeof D === 'object' && D && !D.questions) D.questions = []; if (typeof NK === 'object' && !NK.loc) NK.loc = () => ({{}}); if (!ctx.sig) ctx.sig = x => x.say || x.html;
{post}
const tick = () => new Promise(r => setTimeout(r, 0));
(async () => {{
  const listed = {{all: 2, notes: ['a'], keys: new Set(['n:a', 'gen'])}};
  const going = post([], [], [], 2, listed); await tick();
  assert.ok(S.pending.going, 'Undo is gone');
  const save = api('api/comments'); await tick();  // saved after the countdown, the removal held
  assert.deepStrictEqual(log, [], 'the save waits');
  freeTake(); await tick(); await tick();
  assert.deepStrictEqual(log, ['api/rounds/submit'], 'the round goes alone');
  const save2 = api('api/comments/a/reply'); await tick();  // the round request held: a reply waits too
  freeRound(); await going; await save; await save2;
  assert.deepStrictEqual(log, ['api/rounds/submit', 'api/comments', 'api/comments/a/reply'], 'they go after the round');
  assert.ok(/Sent 2 items/.test(toast), toast);
  assert.strictEqual(ROUND, null);
}})().catch(e => {{ console.error(e); process.exit(1); }});
""")


def test_undo_never_comes_back_after_the_countdown():
    """Frame 2: a redraw after the deadline draws "Sending…" with no Undo."""
    panel = grab(Q, "  function sendPanel(n) {", "\n    if (!S.armed)")
    assert "${S.pending.going ? '' : '<button class=\"lk\" data-sendundo>Undo</button> '}" in panel


def test_typed_drafts_on_other_tabs_are_saved_by_send(tmp_path):
    """Questions 3: a listed typed draft (Pages & links documents and folders, History's chart) is saved as Send's own
    write before the submit, its id is a listed row, and a failed save sends nothing and keeps the words."""
    post = grab(Q, "  async function post(", "\n  // Discard all")
    deliv = grab(Q, "  const deliverable = ", ";\n") + ";"
    links, hist = (WEB / "links.js").read_text(), (WEB / "history.js").read_text()
    assert "save: async () => { const r = await c.api('api/comments'," in links and ", undefined, true);" in links
    assert "save: async () => { const r = await ctx.api('api/comments'," in hist
    assert "c.prefs.set('draft:lnote', null); }\n      redo(); }," not in links  # sent() no longer clears a typed draft
    node(tmp_path, f"""
const assert = require('assert');
let toast = '', posted = 0, ROUND = null, fail = false, kept = 'words';
const x = {{key: 'lnn:doc:a', save: async () => {{ if (fail) throw Error('503'); kept = null; return {{id: 'L'}}; }}}};
let rows = [['Notes', '', 'x:lnn:doc:a', 'x:lnn:doc:a', false, undefined]];
const WRITING = new Set(), S = {{pending: {{n: 2}}}}, D = {{notes: [], version: 'v'}}, NK = {{reo: () => ({{}}), gone: () => {{}}, L: {{}}}};
let stale = false; const waitMsg = () => "Reading first";
const allRead = () => true, settled = () => allRead() && !WRITING.size, Q = () => [x];
const sendItems = () => rows, draw = async () => {{}}, relist = () => {{}}, refresh = async () => {{}};
const gen = () => 'fb', typingNote = () => null, abPicks = () => ({{}}), pl = (n, a, b) => n + ' ' + (n === 1 ? a : b), updateBar = () => {{}};
const draft = () => ({{}}), setDraft = () => {{}}, optLabel = () => '';
const document = {{querySelectorAll: () => []}}; let WROTEQ = new Set(), CARRY = null, GOING = null; const made = b => b.anchor_id + '|' + String(b.text || '').trim();
const ctx = {{takeNow: async () => {{}}, prefs: {{get: () => null, set: () => {{}}}}, toast: t => {{ toast = t; }}}};
let ids = ['L'];
const call = async p => {{ if (p === 'api/rounds/submit') {{ posted++; return {{comment_ids: ids}}; }} return {{}}; }};
{deliv}
const fullSig = () => ''; if (typeof D === 'object' && D && !D.questions) D.questions = []; if (typeof NK === 'object' && !NK.loc) NK.loc = () => ({{}}); if (!ctx.sig) ctx.sig = x => x.say || x.html;
{post}
(async () => {{
  const listed = () => ({{all: 2, notes: [], keys: new Set(['x:lnn:doc:a', 'gen'])}});
  fail = true; await post([], [], [], 2, listed());
  assert.strictEqual(posted, 0, 'a failed save: nothing goes'); assert.strictEqual(kept, 'words'); assert.ok(/Send failed/.test(toast), toast);
  fail = false; S.pending = {{n: 2}}; await post([], [], [], 2, listed());
  assert.strictEqual(posted, 1); assert.strictEqual(kept, null); assert.ok(/Sent 2 items/.test(toast), toast);
  ids = []; S.pending = {{n: 2}}; kept = 'words'; await post([], [], [], 2, listed());
  assert.ok(/Sent 1 item:/.test(toast), 'a saved draft the round left out is not counted: ' + toast);
}})().catch(e => {{ console.error(e); process.exit(1); }});
""")


def test_a_lone_task_comment_is_sent_and_a_newer_draft_stays(tmp_path):
    """Running 1, 4: a lone listed task comment is Sent 1 on a noop round; a draft typed after the countdown neither stops
    the round nor is cleared by it: the round hands the tabs only the rows it listed."""
    post = grab(Q, "  async function post(", "\n  // Discard all")
    deliv = grab(Q, "  const deliverable = ", ";\n") + ";"
    node(tmp_path, f"""
const assert = require('assert');
let toast = '', ROUND = null, handed;
const late = {{key: 'hnn:v2', html: 'typed later', save: async () => {{ throw Error('not listed: never saved'); }}}};
let rows = [['Tasks', '', 'x:tcm:a', 'x:tcm:a', false, undefined], ['Notes', '', 'x:hnn:v2', 'x:hnn:v2', false, undefined]];
const WRITING = new Set(), S = {{pending: {{n: 1}}}}, D = {{notes: [], version: 'v'}}, NK = {{reo: () => ({{}}), gone: () => {{}}, L: {{}}}};
let stale = false; const waitMsg = () => "Reading first";
const allRead = () => true, settled = () => allRead() && !WRITING.size, Q = () => [{{key: 'tcm:a', html: 'c'}}, late];
const sendItems = () => rows, draw = async () => {{}}, relist = () => {{}}, refresh = async () => {{}};
const gen = () => '', typingNote = () => null, abPicks = () => ({{}}), pl = (n, a, b) => n + ' ' + (n === 1 ? a : b), updateBar = () => {{}};
const draft = () => ({{}}), setDraft = () => {{}}, optLabel = () => '';
const document = {{querySelectorAll: () => []}}; let WROTEQ = new Set(), CARRY = null, GOING = null; const made = b => b.anchor_id + '|' + String(b.text || '').trim();
const ctx = {{takeNow: async () => {{}}, prefs: {{get: () => null, set: () => {{}}}}, toast: t => {{ toast = t; }}, queueSent: (n, was) => {{ handed = was; }}}};
const call = async p => p === 'api/rounds/submit' ? {{comment_ids: [], delivery: 'noop'}} : {{}};
{deliv}
const fullSig = () => ''; if (typeof D === 'object' && D && !D.questions) D.questions = []; if (typeof NK === 'object' && !NK.loc) NK.loc = () => ({{}}); if (!ctx.sig) ctx.sig = x => x.say || x.html;
{post}
(async () => {{
  const q = new Map([['tcm:a', 'c']]);
  await post([], [], [], 1, {{all: 1, notes: [], keys: new Set(['x:tcm:a']), q}});
  assert.ok(/^Sent 1 item:/.test(toast), toast);
  assert.strictEqual(handed, q, 'only the listed rows go to the tabs');
}})().catch(e => {{ console.error(e); process.exit(1); }});
""")
    run, fr = (WEB / "running.js").read_text(), (WEB / "frame.js").read_text()
    assert "sent: (ctx, was, done) =>" in run and "k => !was || (was.has(k) && was.get(k) === now.get(k))" in fr  # fix35: the frame's done, by full words


def test_a_failed_read_waits_for_try_again(tmp_path):
    """Questions 4: a failed read stays failed for every later ask from any tab; only Try again (reread or fresh) reads again."""
    reads = grab(FRAME, "  const cache = {}, failed = new Set();", "  let runSeq = 0;\n")
    node(tmp_path, f"""
const assert = require('assert');
const COPY = '', P = {{}}, unTaken = d => d, refreshSend = () => {{}}, sendP = null, putRun = () => {{}};
let n = 0, down = true;
const api = () => {{ n++; return down ? Promise.reject(Error('503')) : Promise.resolve({{ok: n}}); }};
const setTimeout = () => 1;
{reads}
(async () => {{
  await data('questions').catch(() => {{}});
  for (let i = 0; i < 5; i++) await data('questions').catch(() => {{}});
  assert.strictEqual(n, 1, 'no automatic re-read');
  down = false; reread();
  assert.deepStrictEqual(await data('questions'), {{ok: 2}});
  down = true; await data('links').catch(() => {{}}); down = false;
  assert.deepStrictEqual(await data('links', true), {{ok: 4}}, 'a fresh read is Try again too');
  assert.deepStrictEqual(await data('links'), {{ok: 4}});
  assert.strictEqual(n, 4);
}})().catch(e => {{ console.error(e); process.exit(1); }});
""")
    assert "if (!D || stale) readFor(c);" in Q and "readOthers(ctx, true)" in Q


def test_the_toast_and_the_empty_state_read_the_one_state():
    """Frame 4, 6: after a failed read ⌘↵'s toast points to Try again; "Nothing ready yet" waits for a write."""
    assert "if (!sendOn(sendCount() || 1)) { relist(); return ctx.toast(waitMsg()); }" in Q
    msg = grab(Q, "  const waitMsg = () =>", ";\n")
    assert "could not be read: press Try again in Send" in msg and "Saving your note first" in msg
    assert "(settled() ? `<p class=\"small mut\" data-snone" in Q
