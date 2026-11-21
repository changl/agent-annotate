"""Twelfth check: Reload never says "Up to date" behind its copy, and an unread board shows no Waiting counts (r12 fix14 frame)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from agent_annotate.proto_data import copies

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
FRAME = (WEB / "frame.js").read_text()
RUN = (WEB / "running.js").read_text()


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


def test_copy_status_names_the_copys_own_version(tmp_path):
    d = tmp_path / "proto-rebex"
    d.mkdir()
    (d / "current.meta.json").write_text(json.dumps({"current": "v438"}))
    assert copies.build(d) == {"copying": "", "current": "v438"}


def test_reload_never_says_up_to_date_behind_its_copy(tmp_path):
    """Frame 2: the status read lands after the metadata read, and a background copy finishes; both go to blue, never "Up to date"."""
    check = grab(FRAME, "  let copyWatch = 0", "    return true;\n  }\n")
    node(tmp_path, f"""
const assert = require('assert');
const COPY = 'rebex', S = {{loadedV: 'v438', menu: ''}};
const hhmm = () => '12:00', drawTop = () => {{}};
let metas, status;
const meta = v => ({{current: v, history: [{{version: 'v438'}}, {{version: v}}]}});
const api = p => Promise.resolve(status.shift());
api.meta = () => Promise.resolve(metas.shift());
api.comments = () => Promise.resolve({{anchors: {{}}}});
const setTimeout = () => 1;
{check}
(async () => {{
  // the copy swapped in between: metadata 438, status "done at 450", the re-read finds 450
  metas = [meta('v438'), meta('v450')]; status = [{{copying: '', current: 'v450'}}];
  assert.strictEqual(await checkNewer(), true); assert.strictEqual(S.checked, ''); assert.strictEqual(S.newer.v, 'v450');
  // the re-read is still behind: it stays "Copying 450", not "Up to date"
  S.newer = null; copyWatch = 0;
  metas = [meta('v438'), meta('v438')]; status = [{{copying: '', current: 'v450'}}];
  assert.strictEqual(await checkNewer(), false); assert.strictEqual(S.checked, ''); assert.strictEqual(S.copying, 'v450');
  // copying, then done: Copying, then blue
  copyWatch = 0;
  metas = [meta('v438')]; status = [{{copying: 'v450', current: 'v438'}}];
  assert.strictEqual(await checkNewer(), false); assert.strictEqual(S.copying, 'v450'); assert.strictEqual(S.checked, '');
  metas = [meta('v450')]; status = [{{copying: '', current: 'v450'}}];
  assert.strictEqual(await checkNewer(), true); assert.strictEqual(S.copying, ''); assert.strictEqual(S.checked, '');
  // a status read before the swap and metadata after: blue, never "Copying" an older version
  metas = [meta('v450')]; status = [{{copying: '', current: 'v438'}}];
  assert.strictEqual(await checkNewer(), true); assert.strictEqual(S.copying, '');
  // really up to date
  S.loadedV = 'v450'; metas = [meta('v450')]; status = [{{copying: '', current: 'v450'}}];
  assert.strictEqual(await checkNewer(), false); assert.strictEqual(S.checked, '12:00');
}})().catch(e => {{ console.error(e); process.exit(1); }});
""")


def test_unread_board_has_no_beads_counts(tmp_path):
    """The header's Beads card and the phone menu's Beads say the board was not read: no "Nothing ready", no "0 tasks"."""
    ctl = grab(FRAME, "  const board = () =>", "\n  }\n")
    node(tmp_path, f"""
const assert = require('assert');
const esc = s => String(s), pl = (n, a, b) => `${{n}} ${{n === 1 ? a : b}}`, I = n => `<i>${{n}}</i>`;
const S = {{run: {{board: {{error: 'RuntimeError: no'}}}}, other: null, boardUrl: ''}}, readyHere = () => null;
{ctl}
for (const h of [beadsCtl(), beadsCtl(true)]) {{
  assert(!/Nothing ready|0 tasks|0 ready/.test(h), h);
}}
assert(beadsCtl().includes('could not be read just now') && beadsCtl().includes('data-go="running/tasks"'));
assert(beadsCtl(true).includes('not read'));
// the whole Running read failed, an earlier board still in memory: no stale count (r12 audit13 questions 4)
S.run.board = {{tasks: [], waiting: [['b-1']], ready: 0}}; S.runErr = true;
for (const h of [beadsCtl(), beadsCtl(true)]) assert(!/Nothing ready|tasks not closed|0 ready|1 waiting/.test(h) && h.includes('could not be read just now'), h);
// not read yet, Questions holding the first read back: unknown, no count (r12 audit13 frame 2)
S.runErr = false; S.run = null; S.boardUrl = 'https://board.example';
for (const h of [beadsCtl(), beadsCtl(true)]) assert(!/Nothing ready|tasks not closed|0 ready|could not be read/.test(h) && h.includes('has not been read yet') && h.includes('…'), h);
S.run = {{}};
S.run.board = {{tasks: [], waiting: [], ready: 0}};
assert(beadsCtl().includes('Nothing ready') && beadsCtl().includes('0 tasks not closed'));
""")


def test_unread_board_has_no_waiting_counts(tmp_path):
    """Frame 3: an unread board shows no "0" and no "no merge waiting", with the line and Try again Tasks has."""
    body = grab(RUN, "    const wy = new Set", "</section>`;")
    node(tmp_path, f"""
const assert = require('assert');
const ic = n => `<i>${{n}}</i>`, esc = s => s, pl = (n, a, b) => `${{n}} ${{n === 1 ? a : b}}`, tref = (i, t) => t, PNAME = 'FastLane Drive';
const S = {{open: new Set()}};
function band(d) {{
  const b = d.board && !d.board.error ? d.board : {{tasks: [], beads: {{}}, waiting: [], groups: []}}, B = b.beads || {{}};
  {body}
  return waits;
}}
const bad = band({{board: {{error: 'RuntimeError: no'}}}});
assert(!bad.includes('class="cnt"'), bad); assert(!bad.includes('no merge waiting'), bad);
assert(bad.includes('could not be read just now') && bad.includes('data-reread'), bad);
const ok = band({{board: {{tasks: [], beads: {{}}, waiting: [], groups: []}}}});
assert(ok.includes('<span class="cnt">0</span>') && ok.includes('no merge waiting') && ok.includes('Nothing waits on you.'), ok);
""")
