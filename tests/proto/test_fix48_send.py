"""r12 audit41: a closed note never goes with Send (the sheet, the count and the copy's round agree); pictures open at 50%."""
from test_fix13_send import Q, grab, node  # noqa: F401
from test_fix16_notes import HIST
from test_fix13_send import WEB

FRAME = (WEB / "frame.js").read_text()


def test_a_closed_unsent_note_is_not_in_the_copys_round(tmp_path):
    out = grab(Q, "    out: n => {", "},\n")
    sim = grab(Q, "  async function submitSim() {", "\n  }")
    node(tmp_path, f"""
const assert = require('assert');
const NK = {{settle: () => {{}}, life1: () => {{}}, reoQ: () => false, loc: () => ({{}}), mine: () => true, reo: () => ({{}}), rmd: new Set(),
{out}
}};
const open = {{id: 'a', sent: false}}, shut = {{id: 'b', sent: false, closed: true}}, ref = {{id: 'c', sent: false, closed: true}};
const D = {{notes: [open, shut]}}, P = {{ctx: {{data: () => Promise.resolve({{notes: [ref]}})}}}};
const NOTES = {{add: [{{id: 'd'}}, {{id: 'e'}}], sent: new Set()}}, SIM = {{e: {{closed: true}}, f: {{edited: true, closed: true}}, g: {{edited: true}}}};
const simSave = () => {{}};
{sim}
assert.strictEqual(NK.out(shut), false); assert.strictEqual(NK.out(open), true);
submitSim().then(r => {{
  assert.deepStrictEqual(r.comment_ids.sort(), ['a', 'd', 'g']);
  assert.strictEqual(SIM.f.edited, true);  // a closed note's edit waits for its Re-open
}});
""")


def test_pictures_open_at_50_by_default():
    assert "z = prefs.get('zoomDef', 50);" in FRAME
    assert "(p && p.get('zoomDef', 50)) || 50;" in Q
    assert "def = () => ctx.prefs.get('zoomDef', 50);" in HIST
    for src in (FRAME, Q, HIST):
        assert "'zoomDef', 75" not in src
