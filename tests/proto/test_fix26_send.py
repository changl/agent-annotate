"""Fix26 Send: Remove on his own new drafts follows the latest read on every tab, a copy's note included; the receipt counts
only what his round carries; a re-opened note is one row (r12 audit22 reference 3, 4, frame 2, running 2)."""

from pathlib import Path

from test_fix17_notes import KIT, node
from test_fix22_notes import FIX_STUBS

WEB = Path(__file__).resolve().parents[2] / "src/agent_annotate/web/proto"
STORE = "const kept = {}; P.ctx = {prefs: {get: (k, d) => k in kept ? kept[k] : d, set: (k, v) => { kept[k] = v; }}};"


def test_saved_rows_keep_remove_for_his_copy_note_and_not_a_peers(tmp_path):
    node(tmp_path, FIX_STUBS + KIT.replace("const NK = P.notes = {", STORE + "\nconst NK = P.notes = {", 1) + """
// a note written on a read-only copy (Rebex's Policies, Copy library) has no `by`: his own, so its saved row keeps Remove
const copy = {id: 'copy-1', a: 'ref:pol~p~1', text: 'mine', sent: false};
const row = {id: copy.id, text: copy.text, ...NK.state(copy)};
assert.strictEqual(row.by, true); assert.strictEqual(row.rm, true); assert(NK.rowRm(row));
// another reviewer's draft: listed, never Remove, from the read or its saved row
const peer = {id: 'p1', st: 'open', text: 'theirs', sent: false, by: 'u9'};
assert(!NK.rowRm(peer)); assert(!NK.rowRm({id: 'p1', text: 'theirs', ...NK.state(peer)}));
// an earlier build's row (no by, no rm) still waits for a read
assert(!NK.rowRm({id: 'old', text: 'x', sent: false, edited: false, replies: []}));
// a Send takes his note, not the peer's
const own = {id: 'o1', st: 'open', text: 'x', sent: false, by: true};
NK.gone(own); NK.gone(peer);
assert(own.sent && !NK.out(own)); assert(!peer.sent && NK.out(peer));
// a re-opened note is the kit's one Re-open row: never also an ordinary pending row, and its marker stays purple
const reo = {id: 'r1', st: 'open', edited: true, sent: true, anchor: 'chart:v3', text: 'again', by: true};
assert(NK.out(reo));
NK.put(P.ctx, 'r1', NK.rec(reo));
assert(!NK.out(reo) && !NK.sent([reo]));
NK.put(P.ctx, 'r1', null);
assert(NK.out(reo));
""")


def test_open_sheet_follows_rows_and_receipt_counts_his_round():
    f = (WEB / "frame.js").read_text()
    q = (WEB / "questions.js").read_text()
    assert "p.then(() => refreshSend(), () => {});" in f  # every read landing reaches the open sheet
    assert "&& sg === S.sendSig) return;" in f  # the rows, not only the count
    assert "sig: () => JSON.stringify(sendItems().map(x => [x[2], x[3]]))," in q
    assert "const n = sentCount();" in q  # the receipt and the last Send count his round only
    assert "!NK.own(n)]);" in q and "peer(x.note)]);" in q
