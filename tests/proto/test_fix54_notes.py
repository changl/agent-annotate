"""Fix54 (r12 audit46 running 1-2, frame 1-3): notices leave every control reachable; a reply posted on a copy keeps its
thread and author after a reload; a note closed in this visit never lists in Send from its saved record."""

from test_fix15_send import FRAME, HIST, Q
from test_fix17_notes import KIT, STUBS, grab, node
from test_frame import _src


def test_notices_keep_room_to_scroll_any_control_clear(tmp_path):
    """Running 1: while notices show, the page has room at its end as tall as their band; only a notice's box takes the pointer."""
    css = _src("frame.css")
    assert "pointer-events:none" in grab(css, ".p-toastwrap{", "}") and "pointer-events:auto" in grab(css, ".p-toast{", "}")
    fn = grab(FRAME, "  const CTRL = ", "\n  }")
    node(tmp_path, """
const assert = require('assert');
const R = (top, h, left = 0, w = 1440) => ({top, bottom: top + h, left, right: left + w, width: w, height: h});
let ctrls = [], scrolled = 0, pad = '', shown = true;
const toastEl = {get children() { return shown ? [1] : []; }, getBoundingClientRect: () => R(900, 80, 640, 160), contains: () => false};
const body = {className: '', style: {set paddingBottom(v) { pad = v; }, get paddingBottom() { return pad; }}};
const document = {body, documentElement: {scrollHeight: 3000}, getElementById: () => toastEl,
  querySelectorAll: () => ctrls.map(r => ({getBoundingClientRect: () => r, parentElement: null}))};
const getComputedStyle = () => ({position: 'static'}); let scrollY = 0; const innerHeight = 1000;
const scrollBy = o => { scrolled = o.top; };
""" + fn + """
clearUnder();
assert.strictEqual(pad, '106px', 'room below the page: the band from the stack top (less 6 px) to the viewport bottom');
assert.strictEqual(scrolled, 0, 'nothing under it at rest: nothing moves');
shown = false; clearUnder();
assert.strictEqual(pad, '', 'no notice: no room added');
""")


def test_a_copy_reply_comes_back_once_with_its_author(tmp_path):
    """Running 2, frame 1: the copy's store keeps a note's reply in its feed's shape; every read puts it back once."""
    js = "\n".join([grab(Q, "  function fakeWrite(", "\n  }\n"), grab(Q, "  const noteSim =", "))];"),
                    grab(Q, "  const NOTEP =", "];"), grab(Q, "  function simNotes(d) {", "\n  }\n")])
    node(tmp_path, """
const assert = require('assert');
const P = {ctx: {me: 'Audit reviewer', taken: () => false}}; let D = {questions: [{id: 'q1', replies: []}]};
const SIM = {}, NOTES = {add: [], gone: new Set(), text: {}, sent: new Set()}; const simLoad = () => {};
""" + js + """
const r = fakeWrite('api/comments/n1/reply', {text: 'Please check again'});
assert.ok(r.reply_ts, 'its stamp, so the warm thread and a read agree');
const d = {notes: [{id: 'n1', resp: 'Done', status: 'addressed', sent: true, replies: [{agent: true, text: 'Done', ts: 't0'}]}]};
simNotes(d); simNotes(d);  // a cached read has been through here already
const n = d.notes[0], mine = n.replies.filter(x => !x.agent);
assert.strictEqual(mine.length, 1); assert.strictEqual(mine[0].who, 'Audit reviewer'); assert.strictEqual(mine[0].unsent, true);
assert.strictEqual(n.status, 'open', 're-opened, as the server does');
fakeWrite('api/comments/q1/reply', {text: 'a question reply'});
assert.strictEqual(SIM.q1.replies[0].you, true, "a question's reply keeps Questions' shape");
""")
    assert "get me() { return COPY ? 'You' : myName(); }" in FRAME, "a copy names his reply as it names his notes"


def test_a_note_closed_this_visit_never_lists_from_its_record(tmp_path):
    """Frame 2: Send's saved record of a note closed in this visit is not sent; History lists records through the kit."""
    node(tmp_path, STUBS + KIT + """
NK.life.x = {closed: true};
assert.strictEqual(NK.out({id: 'x', sent: false}), false, 'closed in this visit');
assert.strictEqual(NK.out({id: 'y', sent: false}), true);
""")
    saved = grab(HIST, "  const savedC = ctx =>", "return l; };")
    assert "[...m.filter(P.notes.out)," in saved and "!ctx.taken(r.id) && P.notes.out(r))]" in saved
