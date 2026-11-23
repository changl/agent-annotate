"""Fix40 Send (r12 audit35 running 1-7, frame, questions, reference): every toast Undo goes through the one P.going gate in
the shared toast handler; the api() wrapper refuses any write, other than the round's own, that changes or re-writes a row
the held round carries; emptying a carried editor by typing is refused; a failed round leaves a status back at its base no draft.

Why fix39's test passed on 7445e86: it whitelisted put(was), put(from, CTX.prefs.set(k, old) and ctx.prefs.set('q:general', g)
as "restores", and it took the status Undo's `if (!prev && P.going(...))` as gated though the check only ran with no
earlier pick. Here the gate is in frame.js's toast itself, so a toast can only opt out with going: false."""

import json
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


# Every toast with an Undo, by its words, in one of two groups. A new Undo toast in neither group fails the test below.
NAMES_ROWS = {
    "questions.js": ["Note closed: it is under Closed", "Note moved", "Note changed · goes with Send", "Set aside for later",
                     "Closed: no answer needed · goes with Send", "Restored to waiting", "Answer removed", "Correction saved · goes with Send",
                     "Note removed", "Discarded ${pl(total, 'draft', 'drafts')}", "Close removed", "Reply removed", "Pick removed",
                     "Removed from Send", "Asked the agent to file a task · goes with Send", "General feedback removed", "Picked · goes with Send"],
    "history.js": ["Note removed", "Note saved"],
    "links.js": ["Note saved", "Note removed"],
    "reference.js": ["Finding reopened", "Approved; goes with your next Send", "Reopen taken back", "Text approved", "Text restored",
                     "Edit saved", "Note saved", "Note removed"],
    "running.js": ["Status ${ds.tst === tbase(id, b) ? 'back to ' + ds.tst : 'set to ' + ds.tst}: goes with your next Send", "Comment removed"],
}
CHANGES_NO_ROW = {
    "links.js": ["${list[i].name}: ${ROLE[b.dataset.r].toLowerCase()}", "${x.name} removed", "${name} added: ${ROLE[role].toLowerCase()}"],
    "reference.js": ["msg", "Filed “${cutq(p.t)}” as ${SN[d.plansec][0]}", "${pl(ps.length, 'plan', 'plans')} filed under “${topic}”", "Moved back to “Unsorted”"],
    "running.js": ["Rerun started"],
}


def _undo_calls(src):
    """(words, call text) for every toast(...) or inert(...) call that has an Undo."""
    for m in re.finditer(r"\b(toast|inert)\(", src):
        i, depth, q = m.end(), 1, None
        while depth and i < len(src):
            ch = src[i]
            if q:
                if ch == "\\": i += 1
                elif ch == q: q = None
            elif ch in "'\"`": q = ch
            elif ch in "([{": depth += 1
            elif ch in ")]}": depth -= 1
            i += 1
        call = src[m.start():i]
        if m.group(1) == "toast" and not re.search(r"\bundo\b", call):
            continue
        if m.group(1) == "inert" and "=>" not in call:
            continue  # a notice with no Undo
        arg = call[call.index("(") + 1:]
        yield arg[:arg.find("=>")], call  # the words: everything before the Undo's arrow


def test_every_undo_toast_names_its_rows_or_changes_no_send_row():
    seen = 0
    for f in FILES[1:]:
        for words, call in _undo_calls(SRC[f]):
            seen += 1
            off = "going: false" in call or re.search(r",\s*false\)$", call)
            group = CHANGES_NO_ROW if off else NAMES_ROWS
            assert any(w in words for w in group.get(f, [])),(f, "no-row" if off else "names-rows", words, call[:160])
            if not off:  # inert's third argument or the toast's going key
                assert "going:" in call or re.search(r",\s*(?:'[a-z]+:' \+ [a-z.]+|[a-z]+)\)$", call), (f, words, call[-80:])
    assert seen >= 40, seen


def test_bypass_enumeration_every_undo_and_every_store_write():
    """Every toast with an Undo, by file: none opts out (going: false) and none draws its own Undo button; every server
    write goes through api() (no other fetch); the take-backs audit35 found name their rows."""
    undos = {}
    for f, src in SRC.items():
        undos[f] = len(re.findall(r"undo: (?:async )?\(|\{undo\b|[,{] ?undo\}|\.inert\([^;]*?\(\) =>", src))
        if f != "frame.js":
            assert "data-undo>" not in src and "#p-toast [data-undo]" not in src, f  # only the shared toast draws and wires its Undo
            assert not re.search(r"fetch\([^;]*(method|POST|PUT|DELETE)", src), f  # every store write passes the api() wrapper; fetch only reads
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


def _failed_round(tmp_path, kind, delivered, now):
    """A row of one kind went with a round as delivered; it is picked again as now and the next round fails after its check."""
    fail = grab(FRAME, '    queueFailed: () => {', 'refreshSend(); },')
    went = grab(FRAME, '    queueWent: was => {', "prefs.set('sentSig', went); },")
    node(tmp_path, f"""
const assert = require('assert');
const store = {{}}, prefs = {{get: (k, d) => k in store ? store[k] : d, set: (k, v) => {{ store[k] = v; }}}}, refreshSend = () => {{}};
let draft = {json.dumps(delivered)};
const row = () => draft == null ? [] : [{{key: {json.dumps(kind)}, say: draft, remove: () => {{ draft = null; return () => {{}}; }}}}];
const SRC = [{{items: row}}];
const ctx = {{{fail}
{went}
sig: x => x.say || x.html}};
ctx.queueWent(new Map(row().map(x => [x.key, x.say])));  // the round delivered it
draft = {json.dumps(now)};  // picked again past the next round's check
ctx.queueFailed();  // that round fails
assert.strictEqual(draft, {json.dumps(now)} === {json.dumps(delivered)} ? null : {json.dumps(now)});
""")


def test_failed_round_copy_library_choice(tmp_path):
    _failed_round(tmp_path, 'cp:ref:p1~c~0', 'Line 1 → approved', 'Line 1 → approved')
    _failed_round(tmp_path, 'cp:ref:p1~c~0', 'Line 1 → approved', 'Line 1 → held back')


def test_failed_round_approval(tmp_path):
    _failed_round(tmp_path, 'ap:ref:p1', 'Plan → approved', 'Plan → approved')
    _failed_round(tmp_path, 'lappr:k1', 'Kept page → approved', 'Kept page → approved')


def test_failed_round_recovery_request(tmp_path):
    _failed_round(tmp_path, 'tell:src1', 'About the page that could not load: retry it', 'About the page that could not load: retry it')


def test_failed_round_task_status_row(tmp_path):
    _failed_round(tmp_path, 'tst:b1', 'Task b1: set to open', 'Task b1: set to open')
    _failed_round(tmp_path, 'tst:b1', 'Task b1: set to open', 'Task b1: set to blocked')


def _q_failed(tmp_path, body):
    fn = grab(Q, '  const ansSig = d =>', "if (w['ab:' + a] === p.side) setAB(a, null); }")
    node(tmp_path, f"""
const assert = require('assert');
const store = {{}}, ctx = {{prefs: {{get: (k, d) => k in store ? store[k] : d, set: (k, v) => {{ store[k] = v; }}}}}};
let drafts = {{}}, picks = {{}}; const D = {{questions: [{{id: 'q1'}}, {{id: 'q2'}}]}};
const draft = id => drafts[id] || {{}}, setDraft = (id, p) => {{ drafts[id] = {{...draft(id), ...p}}; }};
const abPicks = () => picks, setAB = (a, p) => {{ if (p) picks[a] = p; else delete picks[a]; }};
{fn}
{body}
""")


def test_failed_round_question_answer(tmp_path):
    _q_failed(tmp_path, """
qWent([['q1', {pick: 'o2', words: ' why '}], ['q2', {pick: 'o1'}]], []);
drafts = {q1: {pick: 'o2', words: 'why'}, q2: {pick: 'o3'}};  // q1 picked back at what went; q2 changed
qFailed();
assert.strictEqual(drafts.q1.pick, null); assert.strictEqual(drafts.q2.pick, 'o3');
""")


def test_failed_round_picture_pick(tmp_path):
    _q_failed(tmp_path, """
qWent([], [['fig1', {side: 'proposed'}], ['fig2', {side: 'current'}]]);
picks = {fig1: {side: 'proposed'}, fig2: {side: 'proposed'}};
qFailed();
assert.deepStrictEqual(Object.keys(picks), ['fig2']);
""")
