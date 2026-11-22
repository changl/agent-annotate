"""Fix24 notes: Send's Remove follows the kit's one rule (today's canDeleteComment), Re-open on a review note before its
first Send, and the Questions viewer holds the only edit box (r12 audit20 questions 1-3, running 2)."""

import json
from pathlib import Path

from test_fix17_notes import KIT, Q, STUBS, node
from test_fix23_actions import BASE, ME, STATES, proto, today

WEB = Path(__file__).resolve().parents[2] / "src/agent_annotate/web/proto"
MORE = {
    **STATES,
    "other-draft": {"author": "other@example.com", "flagged_for_session": False, "flagged_at": None},
    "agent-replied-draft": {"flagged_for_session": False, "flagged_at": None, "replies": STATES["agent-latest-reply"]["replies"]},
}


def test_send_rows_and_cards_follow_one_rule(tmp_path):
    cases = {k: (proto({**BASE, **v}), today({**BASE, **v})) for k, v in MORE.items()}
    node(tmp_path, STUBS.replace("const P = {};", "const P = {ctx: null};") + KIT + f"""
const cases = {json.dumps(cases)};
const words = h => [...h.matchAll(/>([^<]+)<\\/button>/g)].map(m => m[1]);
for (const [k, [n, [acts]]] of Object.entries(cases)) {{
  assert.deepStrictEqual(words(NK.acts(c, n, false)), acts, k);
  if (n.closed) continue;  // a closed note never lists in Send
  // Send's row: Remove only where the card has it and the note is not yet kept, from the loaded note and from its saved row
  const want = acts.includes('Remove') && !NK.kept(n);
  assert.strictEqual(NK.rowRm(n), want, k);
  assert.strictEqual(NK.rowRm({{id: n.id, text: 'x', ...NK.state(n)}}), want, k + ' saved row');
}}
assert(!NK.rowRm(cases['other-draft'][0]) && NK.rowRm(cases.draft[0]));
""")


def test_every_tab_send_row_and_discard_use_the_rule():
    for f, s in [("history.js", "remove: P.notes.rowRm(n) ? () => takeC(ctx, n) : null"), ("links.js", "remove: P.notes.rowRm(n) ? () => takeNote(c, n) : null"),
                 ("reference.js", "remove: !NK().rowRm(n) ? null :"), ("questions.js", "NK.rowRm(n) && !P.inflight(n.id) ? 'note:' + n.id : ''")]:
        assert s in (WEB / f).read_text(), f
    assert "if (NK.rowRm(n)) backs.push(await delNote(n.id, true))" in Q


def test_questions_viewer_holds_the_only_edit_box():
    assert "S.note.edit === n.id && !S.zoom === !dlg" in Q and "noteBox(n, no, true)" in Q
    o = Q[Q.index("  async function openNote(next, scroll) {"):Q.index("  async function saveNote(id, text) {")]
    assert '`[data-note="${CSS.escape(e)}"] textarea`' in o.split("const focus")[1].split("\n")[0]


def test_a_kept_edit_yields_to_the_store_after_a_reload(tmp_path):
    """Frame 1: an edit kept from an earlier visit drops once this visit's feed shows the note sent with nothing pending
    (another client's Send); one from this visit, or one the store still holds as edited, stays."""
    node(tmp_path, STUBS.replace("const P = {};", "const P = {ctx: null}; global.location = {pathname: '/'};") + KIT + """
P.ctx = c;
NK.L = null; store['draft:nkput'] = {old: {text: 'edit', replies: [], vis: 'earlier'}, still: {text: 'e2', replies: [], vis: 'earlier'}};
assert(!NK.out({id: 'old', sent: true, edited: false, status: 'open', replies: []}));   // the store says sent: gone from Send
assert(!('old' in store['draft:nkput']));
assert(NK.out({id: 'still', sent: true, edited: true, status: 'open'}) && 'still' in NK.loc());  // still pending in the store
assert(NK.out({id: 'still', text: 'e2', sent: true, edited: false, replies: []}));  // a saved row (no status) never settles
NK.put1('now', {text: 'mine'});
assert(NK.out({id: 'now', sent: true, edited: false, status: 'open'}));  // made in this visit: a stale read can't drop it
""")


def test_reopen_stores_open_at_once_and_keeps_its_send_row(tmp_path):
    """Frame 4: Re-open PUTs status open now, as 2.32.8, and its Send row stays; Undo puts back a status he may set."""
    node(tmp_path, STUBS.replace("const P = {};", "const P = {ctx: null};") + KIT + """
(async () => {
  const n = {id: 'r', sent: true, status: 'resolved_in_version', rv: 'v2', ra: 's:b', text: 't', anchor: 's:a'};
  const undo = await NK.set(c, n, 'reopen', api, async () => {});
  assert.deepStrictEqual(calls.at(-1), ['api/comments/r', {status: 'open'}, 'PUT']);
  assert(n.status === 'open' && NK.reo(c).r && NK.reo(c).r.st === 'resolved_in_version' && NK.isReo(c, n));
  assert(!toasts.at(-1)[1].undo && (await undo()) === null);  // the server lets only the agent resolve it again
  const k = {id: 'k', sent: true, status: 'user_confirmed', text: 't', anchor: 's:a'};
  const u2 = await NK.set(c, k, 'reopen', api, async () => {});
  assert(toasts.at(-1)[1].undo && k.status === 'open');
  await u2();
  assert.deepStrictEqual(calls.at(-1), ['api/comments/k', {status: 'user_confirmed'}, 'PUT']);
  assert(k.status === 'user_confirmed' && !NK.reo(c).k);
})().catch(e => { console.error(e); process.exit(1); });
""")
