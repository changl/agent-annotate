"""Fourteenth check: Beads after Try again (r12 audit14 frame 1), Beads on a failed read (running 3), one fold per table (frame 3)."""

from test_fix14_frame import FRAME, grab, node


def test_beads_follows_the_retried_board_in_the_same_paint(tmp_path):
    """Frame 1: Try again's fresh read sets the frame's board and repaints Beads before Running draws, with Questions still held."""
    reads = grab(FRAME, "  const cache = {};", "  let runSeq = 0;\n")
    run = grab(FRAME, "  function putRun", "const readRun = () => data('running').then(() => {}, () => {});")
    node(tmp_path, f"""
const assert = require('assert');
const COPY = '', P = {{}}, unTaken = d => d, S = {{}}, started = true, refreshSend = () => {{}};
const prefs = {{v: {{}}, get(k, d) {{ return k in this.v ? this.v[k] : d; }}, set(k, v) {{ this.v[k] = v; }}}};
let answers = [{{board: {{error: 'no'}}}}, {{board: {{ready: 4, tasks: []}}}}], paints = [];
const api = () => Promise.resolve(answers.shift());
const drawTop = () => paints.push(S.run && S.run.board && S.run.board.error ? 'unread' : 'read'), drawLayer = () => {{}};
const setTimeout = () => 1;
{reads}
{run}
(async () => {{
  await readRun();
  assert.deepStrictEqual(paints, ['unread']);
  // Running's Try again: the frame has painted the readable board by the time Running's own code goes on
  const d = await data('running', true);
  assert.deepStrictEqual(paints, ['unread', 'read']);
  assert.strictEqual(S.ready, 4); assert.strictEqual(S.runErr, false); assert.strictEqual(prefs.v.hadBoard, true);
  // a stale read answering after a newer one never paints over it
  let late; answers = [new Promise(r => late = r), {{board: {{ready: 5}}}}];
  const a = data('running', true).catch(() => {{}}), b = data('running', true);
  await b; late({{board: {{error: 'old'}}}}); await a;
  assert.strictEqual(S.ready, 5);
}})().catch(e => {{ console.error(e); process.exit(1); }});
""")


def test_a_board_once_read_keeps_beads_on_a_failed_read(tmp_path):
    """Running 3: Rebex has no board link; once its board was read, a whole failed read keeps Beads, saying it was not read."""
    ctl = grab(FRAME, "  const board = () =>", "\n  }\n")
    node(tmp_path, f"""
const assert = require('assert');
const esc = s => String(s), pl = (n, a, b) => `${{n}} ${{n === 1 ? a : b}}`, I = n => `<i>${{n}}</i>`;
const S = {{run: null, runErr: true, other: null, boardUrl: ''}}, readyHere = () => null;
let had = false;
const prefs = {{get: (k, d) => k === 'hadBoard' ? had : d}};
{ctl}
assert.strictEqual(beadsCtl(), '');  // a project with no board shows no Beads
had = true;
for (const h of [beadsCtl(), beadsCtl(true)]) {{
  assert.match(h, /could not be read|not read/);
  assert.doesNotMatch(h, /\\d+ ready|Nothing ready|not closed/);
}}
""")


def test_each_alike_fold_keeps_its_own(tmp_path):
    """Frame 3: every Analytics "Table" is remembered on its own; Reference's folds belong to the item on screen."""
    folds = grab(FRAME, "  // Reference draws one item", "  const secDone = new Set();\n")
    node(tmp_path, f"""
const assert = require('assert');
class HTMLDetailsElement {{ constructor(t) {{ this.t = t; this.open = false; this.dataset = {{}}; this.className = 'tview'; this.id = ''; }}
  querySelector() {{ return {{textContent: this.t}}; }} closest() {{ return true; }} }}
const ds = [new HTMLDetailsElement('Table'), new HTMLDetailsElement('Table'), new HTMLDetailsElement('Table')];
const document = {{querySelectorAll: () => ds}}, location = {{hash: '#analytics'}};
const S = {{tab: 'analytics'}}, remember = () => true;
const prefs = {{v: {{}}, get(k, d) {{ return k in this.v ? this.v[k] : d; }}, set(k, v) {{ this.v[k] = v; }}}};
const main = {{querySelectorAll: s => s.startsWith('details') ? ds.filter(d => !d.dataset.pf) : []}};
{folds}
ds[1].open = true; saveFold({{target: ds[1]}});
// a reload: fresh tables, only the second opens
ds.forEach(d => {{ d.open = false; d.dataset = {{}}; }});
restoreFolds(main);
assert.deepStrictEqual(ds.map(d => d.open), [false, true, false]);
// Reference: two items with the same summary keep separate folds
S.tab = 'reference'; location.hash = '#reference/a';
const k1 = foldBase(ds[0]); location.hash = '#reference/b';
assert.notStrictEqual(k1, foldBase(ds[0]));
""")
