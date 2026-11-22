"""Eleventh check: one Send state everywhere, Try again reads afresh, Remove and Undo before a tab's data is in (r12 fix13 send)."""

import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
FRAME = (WEB / "frame.js").read_text()
CSS = (WEB / "frame.css").read_text()
Q = (WEB / "questions.js").read_text()
REF = (WEB / "reference.js").read_text()


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


def test_header_menu_and_fab_share_one_state():
    """Frame 1, questions 1, running 1: every Send reads from sendSt and repaints together."""
    btn = FRAME[FRAME.index("function sendBtn("):FRAME.index("function drawTop(")]
    unk = btn[btn.index("const st = sendSt();"):btn.index("\n", btn.index("if (st)"))]
    assert "aria-disabled" not in unk and "data-send" in unk
    paint = grab(FRAME, "function paintSend() {", "\n  }")
    assert "#p-top [data-send], #p-layer [data-send]" in paint and "drawFab();" in paint
    fab = grab(FRAME, "function drawFab(", "\n  }")
    assert "sendSt()" in fab and "'unk'" in fab
    assert ".fab.unk{" in CSS
    rc = FRAME[FRAME.index("async function readCounts(again)"):FRAME.index("const putCounts")]
    assert "paintSend();" in rc


def test_send_opens_while_counts_are_unknown():
    """Reference 2: a "…" or "?" Send opens the sheet; only a known zero says nothing is ready."""
    assert "if (sendOff(t.classList.contains('hide-ph') ? 'hide-ph' : '')) return toast('Nothing is ready to send yet');\n      return openSend();" in FRAME
    assert "if (t.id === 'p-fab') return openSend();" in FRAME
    sheet = grab(Q, "function openSheet(c, key) {", "\n  }")
    assert "if (!D || stale || qerr()) readFor(c, qerr());" in sheet and "if (onQ() && D) return draw(true);" in sheet
    assert "const savedQs = () => Object.keys(drafts())" in Q
    assert "if (!allRead()) { relist(); return ctx.toast(`Reading ${qIn() ? 'the notes on other tabs' : 'the questions'} first" in Q  # fix28: and the other tabs' notes; fix31: every Questions read
    assert "if (t.hasAttribute('data-sretry')) return readFor(ctx, true);" in Q


def test_try_again_starts_a_fresh_read(tmp_path):
    """Reference 1: with one read hung, load(c, true) issues a new one and never waits on the hung one."""
    load = grab(Q, "  let reading = null;", "\n  };")
    node(tmp_path, f"""
const assert = require('assert');
let D = null, stale = false, ctx = null, n = 0; const S = {{}}, relist = () => {{}}, qerr = () => false, track = (a, p) => p, retry = () => {{}};
const sim = d => d;
const c = {{data: (a, fresh) => {{ n++; return n === 1 ? new Promise(() => {{}}) : Promise.resolve({{v: n, fresh}}); }}}};
{load}
(async () => {{
  load(c);  // hangs
  await new Promise(r => setTimeout(r, 10));
  assert.strictEqual(D, null);
  await load(c, true);
  assert.strictEqual(n, 2, 'one new read');
  assert.deepStrictEqual(D, {{v: 2, fresh: true}});
}})().catch(e => {{ console.error(e); process.exit(1); }});
""")
    data = FRAME[FRAME.index("const p = cache[area] = Promise.race"):]
    assert "if (cache[area] === p) delete cache[area]; throw e;" in data[:400]


def test_remove_and_undo_before_the_tab_has_its_data():
    """Frame 2, reference 3: no draw into missing data; the receipt shows before the re-list."""
    assert "if (!here() || !D) return;" in REF
    rm = Q[Q.index("function sendRemove("):]
    assert "const keep = draft(id), meta = {p: keep.p, n: keep.n, pl: keep.pl};" in rm
    assert "Promise.resolve(draw(true)).then(() => x.note && D && refresh())" in rm  # r12 fix15: drawn at once, re-read after
