"""r12 audit42 running 3: a kept draft whose Save stored it is that saved note; Send never lists the same words twice."""
from test_fix13_send import Q, WEB, grab, node

LINKS = (WEB / "links.js").read_text()
REF = (WEB / "reference.js").read_text()
HIST = (WEB / "history.js").read_text()


def test_a_saved_draft_is_pruned_once_and_other_drafts_stay(tmp_path):
    kit = grab(Q, "    pruned: new Set(),", "return hit(t) ? t : null; },")
    node(tmp_path, f"""
const assert = require('assert');
const store = {{}}, c = {{prefs: {{get: (k, d) => k in store ? store[k] : d, set: (k, v) => {{ store[k] = v; }}}}, refreshTop: () => {{}}}};
const NK = {{backs: {{all: (c, k) => c.prefs.get(k, null) || []}},
{kit}
}};
const w = {{quote: 'held words', at: 0}}, saved = [{{anchor_id: 'p1', target: {{quote: 'held words', at: 0, offset: null}}, text: 'Second note continued'}}];
store['draft:lnote'] = {{a: 'p1', tgt: w, text: 'Second note continued'}};
store['draft:lback'] = [{{a: 'p1', tgt: {{quote: 'other words', at: 0}}, text: 'First note'}},   // a failed Save: not in the store
                        {{a: 'p1', tgt: w, text: 'Different words'}},                           // different words at the same spot
                        {{a: 'p1', tgt: w, text: ' Second note continued '}}];                  // the saved note again
const t = NK.prune(c, saved, 'draft:lnote', 'draft:lback');
assert.strictEqual(t.text, 'Second note continued');
assert.strictEqual(store['draft:lnote'], null);
assert.deepStrictEqual(store['draft:lback'].map(d => d.text), ['First note', 'Different words']);
// once a visit: words typed again after the feed landed are never wiped
store['draft:lnote'] = {{a: 'p1', tgt: w, text: 'Second note continued'}};
assert.strictEqual(NK.prune(c, saved, 'draft:lnote', 'draft:lback'), null);
assert.ok(store['draft:lnote']);
// no feed yet: nothing pruned and the visit's one prune is still to come
assert.strictEqual(NK.prune(c, null, 'q:newnote', 'draft:qback'), null);
assert.ok(!NK.pruned.has('q:newnote'));
// a paragraph spot (no quote) matches a saved paragraph note; a point matches only the same offset
assert.ok(NK.dup([{{anchor: 'h2', target: {{schema: 1, tag: 'P'}}, text: 'x'}}], 'h2', null, 'x'));
assert.ok(!NK.dup([{{anchor: 'f', target: {{offset: {{dx: .1, dy: .2}}}}, text: 'x'}}], 'f', {{offset: {{dx: .3, dy: .2}}}}, 'x'));
""")


def test_every_reader_prunes_as_its_feed_lands():
    assert "NK.prune(ctx, D.notes, 'q:newnote', QB" in Q and Q.count("pruneQ();") == 2
    assert "P.notes.prune(c, [...LD.notes || [], ...mine], 'draft:lnote', BK)" in LINKS and LINKS.count("prune(c") >= 2
    assert "NK().prune(ctx, allNotes(), 'draft:rnote', BK)" in REF and REF.count("prune();") == 2
    assert "P.notes.prune(ctx, (QD && QD.notes) || null, 'draft:hnote', HB" in HIST and HIST.count("pruneC(ctx);") == 2
