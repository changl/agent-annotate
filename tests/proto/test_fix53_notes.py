"""Fix53 (r12 audit45 frame 1-3, questions 2, reference 2-3): a held second Save in Pages & links is listed once; a deleted
note never comes back from a late read; the notices match the mock and never sit over a page control."""

from test_fix15_send import FRAME, LINKS
from test_fix17_notes import KIT, STUBS, grab, node
from test_frame import _src


def test_links_drafts_match_only_the_notes_links_lists():
    """Frame 1: another feed (a copy's Questions feed) holding the saving note never hides the draft links still lists."""
    one = grab(LINKS, "  const one = (c, d) =>", "? d : null;")
    assert "...mine], d, undefined, true)" in one


def test_a_read_answered_before_the_delete_never_shows_the_note(tmp_path):
    """Questions 2: a reload with a Remove pending: a read the store answered before its DELETE drops the note."""
    take = grab(FRAME, "  const TAKEN = new Map()", "!gone(n.id))} : d;")
    node(tmp_path, STUBS + KIT + "\n{ const ctx = c, prefs = c.prefs, sendP = null; let msg = ''; const toast = m => { msg = m; }, refreshSend = () => {};\n"
         + "let fail = null; const api = () => fail ? Promise.reject(new Error(fail)) : Promise.resolve({});\n" + take + """
P.notes = NK; P.ctx = c;
take('r1', 'api/comments/r1');
finishTake('r1').then(() => {
  assert(!TAKEN.has('r1') && NK.rmd.has('r1'), 'its DELETE went');
  const late = {notes: [{id: 'r1'}, {id: 'k'}]};
  assert(JSON.stringify(unTaken(late).notes.map(n => n.id)) === '["k"]', 'a late read drops it');
  fail = 'not found'; take('r2', 'api/comments/r2');
  return finishTake('r2');
}).then(() => {
  assert(NK.rmd.has('r2') && !msg, 'an earlier visit deleted it: gone, nothing said');
  assert(unTaken({notes: [{id: 'r2'}]}).notes.length === 0);
  const d = {notes: [{id: 'k'}]}; assert(unTaken(d) === d, 'nothing removed: the same feed');
}).catch(e => { console.error(e); process.exit(1); }); }
""")


def test_notice_style_matches_the_mock():
    """Frame 3, reference 3: field corners, no shadow, 4 px between wrapped rows, at every width."""
    css = _src("frame.css")
    rule = grab(css, ".p-toast{", "}")
    assert "box-shadow" not in rule and "border-radius:var(--radius-field)" in rule
    assert rule.index("gap:12px") < rule.index("row-gap:4px"), "row-gap after the gap shorthand, which resets it"
    assert ".p-toast{border-radius" not in css and "bottom:18px" in grab(css, ".p-toastwrap{", "}")


def test_notices_never_sit_over_a_page_control(tmp_path):
    """Frame 2, reference 2: a control under the stack scrolls the least distance that clears it, with room added on a short page."""
    fn = grab(FRAME, "  const CTRL = ", "\n  }")
    node(tmp_path, """
const assert = require('assert');
const R = (top, h, left = 0, w = 1440) => ({top, bottom: top + h, left, right: left + w, width: w, height: h});
let ctrls, scrolled = 0, pad = '';
const toastEl = {children: [1], getBoundingClientRect: () => R(900, 80, 640, 160), contains: () => false};
const body = {className: '', style: {set paddingBottom(v) { pad = v; }, get paddingBottom() { return pad; }}};
const document = {body, documentElement: {scrollHeight: 1000}, getElementById: () => toastEl,
  querySelectorAll: () => ctrls.map(r => ({getBoundingClientRect: () => r, parentElement: null}))};
const getComputedStyle = () => ({position: 'static'}); let scrollY = 0; const innerHeight = 1000;
const scrollBy = o => { scrolled = o.top; };
""" + fn + """
ctrls = [R(920, 34)]; clearUnder();  // the full-width Planning row under the stack, on a page too short to scroll
assert.ok(scrolled > 0 && pad, 'scrolls it clear above, with room added');
assert.strictEqual(920 + 34 - scrolled <= 900 - 6, true);
scrolled = 0; pad = ''; ctrls = [R(500, 34)]; clearUnder();
assert.strictEqual(scrolled, 0, 'nothing under it: nothing moves');
ctrls = [R(920, 34, 0, 100)]; clearUnder();
assert.strictEqual(scrolled, 0, 'beside it, not under it');
""")
