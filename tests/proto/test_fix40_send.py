"""Fix40 Send (r12 audit35 running 1-7, frame, questions, reference): every toast Undo goes through the one P.going gate in
the shared toast handler; the api() wrapper refuses any write, other than the round's own, that changes or re-writes a row
the held round carries; emptying a carried editor by typing is refused; a failed round leaves a status back at its base no draft.

Why fix39's test passed on 7445e86: it whitelisted put(was), put(from, CTX.prefs.set(k, old) and ctx.prefs.set('q:general', g)
as "restores", and it took the status Undo's `if (!prev && P.going(...))` as gated though the check only ran with no
earlier pick. Here the gate is in frame.js's toast itself, so a toast can only opt out with going: false."""

import re
from pathlib import Path

from test_fix13_send import grab, node

WEB = Path(__file__).resolve().parents[2] / "src/agent_annotate/web/proto"
FILES = ("frame.js", "questions.js", "history.js", "links.js", "reference.js", "running.js")
SRC = {f: (WEB / f).read_text() for f in FILES}
FRAME, Q, RUN = SRC["frame.js"], SRC["questions.js"], SRC["running.js"]


def test_the_shared_toast_undo_asks_the_gate():
    toast = grab(FRAME, "  function toast(msg, opts = {}) {", "\n  }")
    assert "const keys = opts.going === undefined ? [true] : [].concat(opts.going);" in toast
    assert "if (undo) undo.onclick = () => { if (P.going && keys.some(k => P.going(typeof k === 'function' ? k() : k))) return; el.innerHTML = ''; opts.undo(); };" in toast
    assert "const inert = (msg, undo, going) => toast(msg, {inert: true, undo: undo || (() => {}), going: undo ? going : false});" in FRAME
    # true: any Undo naming no row is refused while the round is held; a note id the round carries counts too
    assert "key === false || !(key === true || GOING.has(key) || GOING.has('x:' + key) || CARRY.has(key))" in Q


def test_bypass_enumeration_every_undo_and_every_store_write():
    """Every toast with an Undo, by file: none opts out (going: false) and none draws its own Undo button; every server
    write goes through api() (no other fetch); the take-backs audit35 found name their rows."""
    undos = {}
    for f, src in SRC.items():
        undos[f] = len(re.findall(r"undo: (?:async )?\(|\{undo\b|[,{] ?undo\}|\.inert\([^;]*?\(\) =>", src))
        assert "going: false" not in src.replace("going: undo ? going : false", ""), f
        if f != "frame.js":
            assert "data-undo>" not in src and "#p-toast [data-undo]" not in src, f  # only the shared toast draws and wires its Undo
            assert not re.search(r"fetch\([^;]*(method|POST|PUT|DELETE)", src), f  # every store write passes the api() wrapper; fetch only reads
    assert sum(undos.values()) >= 40, undos
    for f, pin in [
        ("running.js", "draw(); }, 'tst:' + id); }"),  # status toast (running 1)
        ("questions.js", "c.toast('Note changed · goes with Send', {going: [n.id, 'n:' + n.id, 'ty:edit:' + n.id], undo: () => put(was)});"),  # running 2
        ("questions.js", "c.toast('Note moved', {going: [id, 'n:' + id, 'reo:' + id], undo: () => put(from, false)});"),  # running 3
        ("running.js", "CTX.toast('Comment removed', {going: k, undo:"),  # running 5
        ("questions.js", "ctx.toast('General feedback removed', {going: 'gen', undo:"),  # running 6
        ("questions.js", "can ? {undo, going: [n.id, 'n:' + n.id, 'reo:' + n.id]} : {}"),  # Re-open / Close toasts
    ]:
        assert pin in SRC[f], (f, pin)
    # Note saved, Send it again and Restored to waiting name no row: the shared gate refuses them while the round is held,
    # and the wrapper refuses their DELETE or archive (frame 1, 3, 4)
    for msg in ("Note saved", "Send it again", "Restored to waiting"):
        assert any(msg in s for s in SRC.values()), msg


def test_close_on_a_carried_reopen_is_refused():
    assert "if ((how === 'close' || how === 'unreopen') && P.going && [n.id, 'n:' + n.id, 'reo:' + n.id].some(k => P.going(k))) return null;" in Q


def test_the_wrapper_refuses_a_write_on_a_carried_row(tmp_path):
    cp = grab(Q, "    carriesPath: (path, body) => {", "(made(body)); },")
    api = grab(FRAME, "  async function api(path, body, method, own) {", "if (hold) await hold;")
    node(tmp_path, f"""
const assert = require('assert');
let CARRY = new Set(['n1']), GOING = new Set(['r:q1', 'x:ty:edit:n2', 'q:q3', 'nn:']), toasts = 0, sent = [];
const made = b => `${{b.anchor_id}}|${{String(b.text || '').trim()}}`;
const sendP = {{{cp.strip().rstrip(',')}, hold: () => null}};
const toast = () => {{ toasts++; }}, P = {{}}, COPY = '';
const fetch = (p, o) => {{ sent.push([o.method, p]); return Promise.resolve({{ok: true, json: async () => ({{}})}}); }};
{api} return 'went'; }}
(async () => {{
  const no = async (p, b, m) => {{ await assert.rejects(api(p, b, m), e => e.carried); }};
  await no('api/comments/n1', {{text: 'old'}}, 'PUT');           // Note changed / Note moved Undo on a carried note
  await no('api/comments/n1', undefined, 'DELETE');             // Note saved Undo, Send it again Undo
  await no('api/comments/n1/archive', {{}});                     // Close on a carried Re-open
  await no('api/comments/q3/archive', {{}});                     // Restored to waiting Undo on a delivered Approve
  await no('api/comments/q1/reply', {{text: 'again'}});          // Post reply the round is posting
  await no('api/comments/n2', {{text: 'x'}}, 'PUT');             // Save on an open Edit the round carries
  await api('api/comments', {{anchor_id: 'p1', text: 'hi'}}, undefined, true);  // the round's own new note
  await no('api/comments', {{anchor_id: 'p1', text: 'hi '}});     // the editor's Save of that same note
  assert.strictEqual(await api('api/comments', {{anchor_id: 'p2', text: 'other'}}), 'went');
  assert.strictEqual(await api('api/comments/n9/reply', {{text: 'r'}}), 'went');
  assert.strictEqual(toasts, 7);
  CARRY = null;  // after the round every write goes
  assert.strictEqual(await api('api/comments/n1', {{text: 'old'}}, 'PUT'), 'went');
}})().catch(e => {{ console.error(e); process.exit(1); }});
""")


def test_emptying_a_carried_editor_and_escape():
    assert "if (k && P.going(k)) { t.value = was; e.stopImmediatePropagation(); return; }" in Q
    assert Q.index("const WAS = new WeakMap();") < Q.index("// every keystroke in a Reply or an Edit, on any tab")
    assert 'data-tcm data-edkey="tcm:${esc(id)}"' in RUN
    assert "if (e.key === 'Escape' && (S.trn || S.tmerge || S.move || S.spot))" in SRC["reference.js"]


def test_a_failed_round_drops_a_status_back_at_its_base():
    assert "if (ctx.queueFailed) ctx.queueFailed();" in Q
    assert "for (const id of Object.keys(t)) if (t[id] === tbase(id, B[id], ctx)) delete t[id];" in RUN
    assert "P.queue && P.queue({items: () => [], failed});" in RUN
