"""r12 audit40: one second-spot rule in the notes kit, used by every reader (Questions, Reference, Pages & links, History)."""
from test_fix13_send import Q, REF, grab, node  # noqa: F401
from test_fix43_send import LINKS
from test_fix16_notes import HIST


def test_the_kits_second_spot_rule(tmp_path):
    body = Q[Q.index("    same: (d, a, tgt) =>"):Q.index("    // a redraw (an earlier note's Save landing)")]  # same, keep, backs, failed, cancel
    node(tmp_path, f"""
const assert = require('assert');
const store = {{}}, c = {{prefs: {{get: (k, d) => k in store ? store[k] : d, set: (k, v) => {{ store[k] = v; }}}}, refreshTop: () => {{}}}};
const NK = {{
{body}
}};
let slot = null; const set = d => {{ slot = d; }};
const A = {{a: 'L1', tgt: {{quote: 'x', at: 0}}, text: 'first'}}, B = {{a: 'L1', tgt: {{quote: 'x', at: 9}}, text: 'second'}};
// nothing typed, its own composer open: back in the typed slot
NK.failed(c, 'bk', A, null, {{a: A.a, tgt: A.tgt}}, set); assert.strictEqual(slot, A); assert.deepStrictEqual(NK.backs.all(c, 'bk'), []);
// nothing typed, another spot's composer open (blank): a draft at its own spot, the composer stays blank (audit40 reference 2)
slot = null; NK.failed(c, 'bk', A, null, {{a: B.a, tgt: B.tgt}}, set); assert.strictEqual(slot, null); assert.deepStrictEqual(NK.backs.all(c, 'bk'), [A]);
// another spot typed: a draft at its own spot, once
store.bk = []; NK.failed(c, 'bk', A, B, {{a: B.a, tgt: B.tgt}}, set); NK.failed(c, 'bk', A, B, null, set); assert.deepStrictEqual(NK.backs.all(c, 'bk'), [A]);
// the same spot typed since: its newer words stay, nothing doubled
store.bk = []; NK.failed(c, 'bk', A, {{...A, text: 'newer'}}, null, set); assert.deepStrictEqual(NK.backs.all(c, 'bk'), []);
// Cancel on the recovered draft drops only it: the other spot's typed words stay (audit40 frame)
store.bk = [A]; let cleared = false; NK.cancel(c, 'bk', {{a: A.a, tgt: A.tgt}}, B, () => {{ cleared = true; }});
assert.deepStrictEqual(NK.backs.all(c, 'bk'), []); assert.strictEqual(cleared, false);
NK.cancel(c, 'bk', {{a: B.a, tgt: B.tgt}}, B, () => {{ cleared = true; }}); assert.strictEqual(cleared, true);
""")


def test_every_reader_uses_the_rule():
    assert "const putBack = (c, d) => P.notes.failed(c, BK, d, typed(c), S.note ? {a: S.note, tgt: S.tgt} : null," in LINKS
    assert "const putBack = d => NK().failed(ctx, BK, d, rnote(), S.note ? {a: S.note, tgt: S.tgt} : null, setR);" in REF
    assert "const qBack = n => NK.failed(ctx, QB, qSpot(n)," in Q
    assert "const putC = (c, d) => P.notes.failed(c, HB," in HIST
    for src, kit in ((LINKS, "P.notes.cancel("), (REF, "NK().cancel("), (HIST, "P.notes.cancel(")):
        assert kit in src  # Cancel drops only its own spot's draft
    # finding 1: History's Save no longer closes or wipes another point's composer; a failed one is a draft at its point
    save = grab(HIST, "  async function saveC(el, ctx) {", "\n  }")
    assert "S.cn = ''; ctx.prefs.set('draft:hnote', null)" not in save and "if (!now || now.v === v) setC(ctx, null);" in save
    assert "} catch (er) { putC(ctx, {a: v, text});" in save
    # finding 2: another point keeps the typed note (the kit's keep), and its typing never overwrites another point's words
    assert "if (S.cn !== v && !keepC(ctx, v)) return focusC(el);" in HIST and "if (!keepC(ctx, ds.spotadd)) return focusC(el);" in HIST
    assert "if (was && was.v !== S.cn) P.notes.backs.put(ctx, HB, was);" in HIST and "key: 'hnb:' + b.a, spot: 'chart:' + b.a" in HIST
    # finding 3: a failed Questions Save goes through the rule; a spot opening takes its kept words; its drafts are Send rows
    assert "catch (e) { if (!P.carried(e)) qBack({...n, text});" in Q and "S.note = next = fromBack(next);" in Q and "key: 'qnb:' + b.a" in Q
    # finding 4 (and History's): a redraw keeps the composer's focus through the kit's hold
    assert "NK.hold(root)" in Q and "P.notes.hold(box)" in HIST and "P.notes.hold(w)" in LINKS
    # a failed Send puts back every typed note it carried and had not written, at its own spot (audit40 questions)
    assert "for (const x of left) if (x.put) x.put();" in Q and "if (tnLeft) qBack(tnLeft);" in Q
    for src in (LINKS, REF, HIST):
        assert src.count("put: () => putBack(") + src.count("put: () => { putC(") >= 2
