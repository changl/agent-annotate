"""Fix51 (r12 audit43 reference 1, running 1 and 3, questions 1 and 2, frame 1-2): Re-open on a closed note the agent already
has goes with the next Send once, as the kit's Re-open row; Close's Undo puts back only what it was; a draft whose Save the
store has is that saved note's row."""

from test_fix17_notes import KIT, STUBS, node

FIX_STUBS = STUBS.replace("const P = {};", "const P = {ctx: null};")

def test_reopen_of_a_sent_closed_note_goes_with_send_once(tmp_path):
    node(tmp_path, FIX_STUBS + KIT + """
P.ctx = c;
(async () => {
  const n = {id: 's1', sent: true, st: 'open', text: 'sent words', anchor: 'doc:x~1'};
  await NK.set(c, n, 'close', api, async () => {}, true);
  assert(n.closed && !NK.out(n) && !NK.reoQ(n), 'a closed note is never listed');
  calls.length = 0;
  const undo = await NK.set(c, n, 'restore', api, async () => {});
  assert(!n.closed && NK.reoQ(n) && !NK.out(n), 'his Re-open: listed once, as the Re-open row');
  assert(calls.some(([u, b, m]) => u === 'api/comments/s1' && m === 'PUT' && b.status === 'open' && b.text === 'sent words'), 'stored open with his words: an edit the round takes, even in the same second as the last Send');
  assert(/re-opened · goes with Send/.test(NK.words(c, n)), 'the label says it goes');
  await undo();
  assert(n.closed && !NK.reoQ(n), 'its Undo closes it and nothing goes');
  // Close's own Undo (quiet) only puts back what it was: no Re-open row
  const m = {id: 's2', sent: true, st: 'open', text: 'x'};
  const u2 = await NK.set(c, m, 'close', api, async () => {});
  await u2();
  assert(!m.closed && !NK.reoQ(m) && !NK.out(m), 'Close then Undo: still sent, nothing goes');
  // an unsent note re-opened is listed as itself
  const d = {id: 'd1', sent: false, st: 'open', text: 'y'};
  await NK.set(c, d, 'close', api, async () => {}, true);
  await NK.set(c, d, 'restore', api, async () => {});
  assert(!NK.reoQ(d) && NK.out(d), 'an unsent note goes as itself');
  // an edited, closed, re-opened one is still one row
  const e = {id: 'e1', sent: true, edited: true, st: 'open', text: 'z'};
  await NK.set(c, e, 'close', api, async () => {}, true);
  await NK.set(c, e, 'restore', api, async () => {});
  assert(NK.reoQ(e) && !NK.out(e), 'listed once, as the Re-open row');
})().catch(e => { console.error(e); process.exit(1); });
""")


def test_a_saved_draft_is_that_note(tmp_path):
    node(tmp_path, FIX_STUBS + KIT + """
const tgt = {schema: 1, tag: 'p', quote: 'words', at: 3};
const ns = [{id: 'n1', a: 'ref:p~1', target: tgt, text: 'Second note'}];
assert(NK.hit(ns, {a: 'ref:p~1', tgt, text: ' Second note '}), 'same words at the same spot: one row');
assert(!NK.hit(ns, {a: 'ref:p~1', tgt, text: 'Other words'}), 'other words stay a draft');
assert(!NK.hit(ns, {a: 'ref:p~2', tgt, text: 'Second note'}), 'another spot stays a draft');
assert(!NK.hit(null, {a: 'ref:p~1', tgt, text: 'Second note'}), 'no feed yet: the draft is listed');
// the plan's Save landed in another feed held (Questions) first: still one row (r12 audit43 questions 3)
NK.feeds.push({notes: [{id: 'n2', anchor: 'ref:plan~v2~2', target: tgt, text: 'Held words'}]});
assert(NK.hit([], {a: 'ref:plan~v2~2', tgt, text: 'Held words'}), 'a saved note in any feed held is that draft');
assert(NK.hit(null, {a: 'ref:plan~v2~2', tgt, text: 'Held words'}), 'even before the reader\\'s own feed');
""")
