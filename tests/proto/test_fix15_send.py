"""Thirteenth check: Send's number is the sheet's row count after a failed read; Undo keeps the very stored note (r12 fix15 send)."""

import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
FRAME = (WEB / "frame.js").read_text()
Q = (WEB / "questions.js").read_text()
REF = (WEB / "reference.js").read_text()
HIST = (WEB / "history.js").read_text()
LINKS = (WEB / "links.js").read_text()


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


def test_send_state_after_a_failed_read(tmp_path):
    """Frame 1, questions 1, reference 1: a saved draft shows its number, "?" only with nothing saved."""
    fn = grab(FRAME, "  const sendNum = ", "'?' : '…';")
    node(tmp_path, f"""
const assert = require('assert');
let saved = 4; const S = {{countsIn: false, sendN: 0, stall: new Map([['counts', 'HTTP 503']])}};
const sendable = () => true, sendP = {{saved: () => saved}}, savedN = () => sendP.saved();
{fn}
assert.strictEqual(sendSt(), ''); assert.strictEqual(sendNum(), 4);
saved = 3; assert.strictEqual(sendNum(), 3);  // a Remove: read at the next paint, no timer
saved = 0; assert.strictEqual(sendSt(), '?');
S.stall.clear(); assert.strictEqual(sendSt(), '…');
S.countsIn = true; saved = 2; assert.strictEqual(sendNum(), 2);  // once read too: the sheet's rows, never a count a timer leaves behind
""")
    assert "if (started) paintSend();" in FRAME  # every tab's change repaints Send in the same task
    assert "Promise.resolve(draw(true)).then(() => x.note && D && refresh())" in Q  # the sheet redraws in that task too
    assert "D.notes.forEach(x => { x.sent = true; });" in Q  # Send reads 0 with the receipt
    assert "const sendCount = () => sendItems().length + (gen().trim() ? 1 : 0);" in Q


def test_taken_note_stays_until_undo_is_gone(tmp_path):
    """Frame 4, questions 2: Remove hides the note; Undo cancels the DELETE, so the record never changes; later the DELETE goes."""
    fn = grab(FRAME, "  const TAKEN = new Map()", "TAKEN.has(n.id))} : d;")
    node(tmp_path, f"""
const assert = require('assert');
const store = {{}}, calls = [], P = {{}};
const prefs = {{get: (k, d) => k in store ? store[k] : d, set: (k, v) => {{ store[k] = v; }}}};
const api = (p, b, m) => {{ calls.push([m, p]); return Promise.resolve({{}}); }}, toast = () => {{}};
{fn}
const d = {{notes: [{{id: 'a', number: 7}}, {{id: 'b'}}]}};
const keep = take('a', 'api/comments/a');
assert.deepStrictEqual(unTaken(d).notes.map(n => n.id), ['b']);
assert.deepStrictEqual(store.taken, {{a: 'api/comments/a'}});
keep();  // Undo
assert.strictEqual(unTaken(d), d); assert.deepStrictEqual(calls, []);
take('b', 'api/comments/b');
finishTake('b').then(() => {{ assert.deepStrictEqual(calls, [['DELETE', 'api/comments/b']]); assert.deepStrictEqual(store.taken, {{}}); process.exit(0); }});
assert.deepStrictEqual(P.putBack([{{id: 'x'}}], [{{id: 'a'}}, {{id: 'x'}}], 'a').map(n => n.id), ['a', 'x']);
""")


def test_every_tab_undo_keeps_the_record():
    """Frame 4, questions 2, running 2: no tab re-creates a removed note; History puts its saved record back for the next first Send."""
    for src in (Q, REF, HIST):
        assert "ctx.take(" in src
    assert "const keep = c.take(n.id, 'api/comments/' + encodeURIComponent(n.id))" in LINKS
    assert "c.api('api/comments', {anchor_id: n.a, anchor_label: n.l, text: n.text, target: n.target})" not in LINKS
    assert "if (!LD.notes.some(x => x.id === n.id)) LD.notes.push(n);" in LINKS  # a feed read while it was hidden gets it back
    assert "await call('api/comments', {anchor_id: n.anchor, anchor_label: n.label, text: n.text, version: v" not in Q
    assert "ctx.api('api/comments', {anchor_id: n.anchor, anchor_label: n.label, text: n.text})" not in HIST
    assert "ctx.prefs.set('draft:hcnotes', l); CN.push" in HIST
    assert "await ctx.takeNow();" in Q  # a Send never carries a note removed with Undo still open
    assert "[...TAKEN.keys()].forEach(finishTake);" in FRAME and "prefs.get('taken', {})" in FRAME
