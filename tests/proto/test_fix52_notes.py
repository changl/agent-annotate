"""Fix52 (r12 audit44 reference 1-2): Remove takes a note's Re-open row out of Send with the note, and its Undo puts it back;
a plain notice never takes a pending Undo away."""

from test_fix15_send import FRAME
from test_fix17_notes import KIT, STUBS, grab, node


def test_remove_takes_the_reopen_row_and_undo_puts_it_back(tmp_path):
    take = grab(FRAME, "  const TAKEN = new Map()", "!gone(n.id))} : d;")
    node(tmp_path, STUBS + KIT + "\nconst ctx = c, prefs = c.prefs, sendP = null, toast = () => {}; let sends = 0; const refreshSend = () => { sends++; };\n"
         + take + """
P.notes = NK; P.ctx = c;
const n = {id: 's1', sent: true, st: 'open', text: 'w', anchor: 'doc:x~1'};
NK.put(c, n.id, NK.rec(n));
assert(NK.reoQ(n), 'his Re-open is a Send row');
const undo = take('s1', 'api/comments/s1');
assert(!NK.reoQ(n) && !('s1' in store['draft:reopen']), 'Remove: the row is gone from Send at once, and from the store a reload reads');
assert(sends === 1, 'Send repaints');
undo();
assert(NK.reoQ(n) && store['draft:reopen'].s1.text === 'w', 'Undo puts the very row back');
// a note with no Re-open row: Remove and Undo leave the record as it was
const u2 = take('d1', 'api/comments/d1'); u2();
assert(!('d1' in store['draft:reopen']));
// a copy a reader read before Remove (edited: the Re-open's status PUT) never lists while taken, nor once its DELETE went
P.ctx = {...c, taken: id => TAKEN.has(id)};
const e = {id: 'e1', sent: true, edited: true, st: 'open', text: 'x'};
assert(NK.out(e));
const u3 = take('e1', 'api/comments/e1');
assert(!NK.out(e), 'taken: not a Send row'); u3(); assert(NK.out(e), 'Undo: back');
NK.rmd.add('e1'); assert(!NK.out(e), 'deleted: never a Send row');
""")


def test_history_undo_puts_back_the_very_note():
    """Running 2: Undo of a History Remove puts back the note itself, so a re-opened sent one keeps its label."""
    from test_fix15_send import HIST
    t = grab(HIST, "  async function takeC(ctx, n) {", "\n  }")
    assert "CN.push(n);" in t and "sent: false" not in t


def test_questions_lists_a_saving_note_once():
    """Running 3: while a new note's Save is out its words are a draft at their spot, dropped once the note is listed or the Save fails;
    Questions' own drafts yield only to the notes it lists."""
    from test_fix15_send import Q
    a = grab(Q, "  async function addNote(text, from) {", "\n  }")
    assert a.index("NK.backs.put(ctx, QB, sp)") < a.index("await call('api/comments'") < a.index("D.notes.push") < a.rindex("unhold();")
    assert "catch (e) { unhold();" in a
    assert "NK.hit(D && D.notes, {a: n.anchor, tgt: n.target || null, text: n.text}, undefined, true)" in Q
    assert "!NK.hit(D && D.notes, b, undefined, true)" in Q


def test_a_plain_notice_keeps_a_pending_undo():
    t = grab(FRAME, "  function toast(msg, opts = {}) {", "\n  }")
    assert t.index("el.querySelector('[data-undo]')") < t.index("clearTimeout(toastTimer)"), "checked before the Undo's timer is cleared"
    assert "el.prepend(x)" in t


def test_an_edit_reaches_the_reopen_row(tmp_path):
    """Questions 3, frame 2: the Re-open row carries the latest saved words, from the record a reload reads."""
    node(tmp_path, STUBS + KIT + """
P.ctx = c; c.toast = () => {};
const n = {id: 's1', sent: true, st: 'open', text: 'old', anchor: 'q1'};
NK.put(c, n.id, NK.rec(n));
NK.fix(c, n, 'new words', async () => ({}), async () => {}).then(ok => {
  assert(ok && store['draft:reopen'].s1.text === 'new words');
});
""")


def test_the_copy_feed_keeps_an_edit_unflagged():
    """Frame 4: a re-read of the copy's Questions feed keeps his edit since Send, so Remove shows as in the ordinary reader."""
    from test_fix15_send import Q
    assert "if (s.edited && o.sent) Object.assign(o, {edited: true, flagged: false});" in grab(Q, "  function simNotes(d) {", "\n  }")
