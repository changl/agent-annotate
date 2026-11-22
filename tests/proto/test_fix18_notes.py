"""Fix18 notes (r12 audit16): every note surface runs on P.notes and the one Re-open store. A re-open is listed by the kit
from its stored record (no feed needed, so the first Send after a reload lists it); Pages & links lines Move, list several
notes and land View resolution on the line; the History chart lists a point's notes with the full lifecycle; Reference
picture pins are buttons."""

import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
Q = (WEB / "questions.js").read_text()
HIST = (WEB / "history.js").read_text()
REF = (WEB / "reference.js").read_text()
L = (WEB / "links.js").read_text()


def grab(src, start, end):
    i = src.index(start)
    return src[i:src.index(end, i) + len(end)]


def node(tmp_path, js):
    exe = shutil.which("node")
    if not exe:
        pytest.skip("node not installed")
    f = tmp_path / "t.js"
    f.write_text(js)
    r = subprocess.run([exe, str(f)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr + r.stdout


# the kit plus its one queue source
KIT = grab(Q, "  const stOf = ", "\n  };") + grab(Q, "  const TABN = ", "}}))});")
STUBS = """const assert = require('assert'); const src = []; const P = {queue: s => src.push(s)};
const esc = s => String(s), ic = k => '', cut = (s, n) => s, pl = (n, a, b) => n + ' ' + (n === 1 ? a : b);
const mk = n => `[${n}]`, ibw = (k, label, t, attrs) => `<button ${attrs}>${label}</button>`;
const store = {}, calls = [];
const c = {prefs: {get: (k, d) => k in store ? JSON.parse(JSON.stringify(store[k])) : d, set: (k, v) => { store[k] = v; }},
  toast: () => {}, go: (t, a) => calls.push(['go', t, a])};
const api = async (u, body, m) => { calls.push([u, body, m]); return {}; };
"""


def test_reopen_is_listed_from_the_store_without_any_feed(tmp_path):
    """Frame 1: Re-open in Reference or Pages & links stays in the first Send after a reload, whatever the reads do."""
    node(tmp_path, STUBS + KIT + """
(async () => {
  const seen = {};
  P.noteHooks.links = {go: r => seen.go = r, redo: () => seen.redo = (seen.redo || 0) + 1, res: n => seen.res = n.ra};
  const n = {id: 'l1', sent: true, st: 'resolved_in_version', a: 'doc:plan.md~1', ra: 'doc:plan.md~3', line: 'Ship it', text: 'x'};
  await NK.set(c, n, 'reopen', api, async () => {});
  // a reload: only the store is left, no tab has read anything
  const items = src[0].items(c);
  assert.strictEqual(items.length, 1);
  assert.strictEqual(items[0].key, 'reo:l1'); assert(/Ship it/.test(items[0].html) && /Re-opened/.test(items[0].html));
  items[0].go(); assert.strictEqual(seen.go.id, 'l1');
  const undo = items[0].remove(); assert.strictEqual(src[0].items(c).length, 0); assert.strictEqual(seen.redo, 1);
  undo(); assert.strictEqual(src[0].items(c).length, 1);
  // a status saved before records is upgraded, not dropped
  store['draft:reopen'] = {old: 'resolved_in_version'};
  assert(NK.isReo(c, {id: 'old', sent: true, st: 'resolved_in_version', a: 'ref:plan~v1~2', text: 'y'}));
  assert.strictEqual(src[0].items(c)[0].key, 'reo:old');
  // View resolution goes to the tab that owns the destination
  NK.goRes(c, n); assert.strictEqual(seen.res, 'doc:plan.md~3');
  NK.goRes(c, {rv: 'v2', ra: 's:p2'}); assert.deepStrictEqual(calls.at(-1), ['go', 'history', 'v2~s:p2']);
})().catch(e => { console.error(e); process.exit(1); });
""")
    assert "lreo:" not in L and "key: 'reo:' + n.id" not in REF and "isRo" not in Q


def test_links_lines_move_list_and_outline_their_resolution():
    """Frame 2, 3, 5: View resolution outlines the destination line; Move then a line moves the note; a spot lists its notes."""
    assert "if (S.move) return moveTo(w, ctx, D, k, ln, tgt)" in L and "function moveTo(" in L
    assert "P.notes.lit(rs)" in L and "S.resGo = true" in L
    assert "K.spot(ctx, sl.map(n => [n, spotNo(n) || ns.indexOf(n) + 1])" in L and "b.dataset.spotadd" in L and "b.dataset.spotgo" in L


def test_history_chart_point_lists_notes_with_the_lifecycle():
    """Frame 6: a marked point lists its notes; resolved ones get Close, Re-open, Move and View resolution."""
    assert "P.notes.spot(ctx, cnotes(v)" in HIST and "if (S.cmove) return moveC(el, ctx, v)" in HIST
    assert "K.acts(ctx, x, S.cmove === x.id)" in HIST and "K.closedActs(x)" in HIST
    assert "P.notes.set(ctx, x, how, ctx.api" in HIST and "P.notes.goRes(ctx," in HIST
    assert "P.noteHooks" in HIST


def test_reference_picture_pin_is_a_control():
    """Reference 1: the viewer's numbered pin takes clicks, so it lists notes with + Comment instead of a blank composer."""
    assert "button.pinm{pointer-events:auto" in (WEB / "reference.css").read_text()


def test_cards_only_sent_line_wraps_on_a_phone():
    """Questions 7: the Cards only right side (Sent, read by the agent, Change) shrinks and wraps instead of running off a 390 px screen."""
    css = (WEB / "questions.css").read_text()
    rule = css[css.index(".qright{"):].split("}", 1)[0]
    assert "flex:none" not in rule and "min-width:0" in rule and "flex-wrap:wrap" in rule and "max-width:100%" in rule
