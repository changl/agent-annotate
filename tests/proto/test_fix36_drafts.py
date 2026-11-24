"""Fix36 drafts (r12 audit31 running 5, questions 4-5, frame 4, reference 1): every editor's typed words go to the draft store
as typed and come back on reload; an open Reply, an open Edit on a sent note and the Reference note being typed are Send rows
that Send delivers as its own write, and clear only once delivered as listed."""

from pathlib import Path

from test_fix17_notes import KIT, Q, STUBS, grab, node

WEB = Path(__file__).resolve().parents[2] / "src/agent_annotate/web/proto"
REF = (WEB / "reference.js").read_text()
HIST = (WEB / "history.js").read_text()
ROWS = grab(Q, "  const TABN = ", "\n  // every re-opened note")

HARNESS = """
c.refreshTop = () => {}; c.api = async (u, b, m, own) => { calls.push([u, b, m, own]); return {}; };
P.ctx = c;
"""


def test_edit_and_reply_drafts_are_stored_listed_and_delivered(tmp_path):
    node(tmp_path, STUBS + KIT + HARNESS + ROWS + """
(async () => {
  const n = {id: 'n1', sent: true, st: 'addressed_by_agent', text: 'old', anchor: 'doc:kept-m~p~3', label: 'Para', resp: 'done', replies: []};
  // typed in Reply and Edit: in the draft store (a reload reads it back from there), and the editor shows it
  NK.th.set('n1', n); NK.eds.set('n1', n);
  NK.typed.set('n1', 'reply words');
  NK.tySet('edit:n1', {...NK.rec(n), id: 'n1', text: 'new words', was: 'old', sent: true});
  assert.strictEqual(store['draft:nktyped']['reply:n1'].text, 'reply words');
  assert(/>reply words<\\/textarea>/.test(NK.thread(c, n)));
  assert(/>new words<\\/textarea>/.test(NK.sentBody(c, n, false, null)), 'an Edit left open reopens with its words');
  // one Send row each, by full words
  let rows = P.tyRows(c);
  assert.deepStrictEqual(rows.map(x => [x.key, x.say]), [['ty:reply:n1', 'Reply: reply words'], ['ty:edit:n1', 'Edited: new words']]);
  // an edit back to the note's own words, or on a never-sent note, has no row (the note's own row goes); the words stay stored
  NK.tySet('edit:n2', {id: 'n2', text: 'x', was: 'w', sent: false});
  assert.strictEqual(P.tyRows(c).length, 2);
  // Send delivers each as its own write and clears it, as listed
  for (const x of rows) assert.strictEqual((await x.save()).id, 'n1');
  assert.deepStrictEqual(calls.map(x => [x[0], x[2], x[3]]), [['api/comments/n1/reply', undefined, true], ['api/comments/n1', 'PUT', true]]);
  assert.deepStrictEqual(calls[1][1], {text: 'new words', status: 'open'});
  assert(!('reply:n1' in NK.ty()) && !('edit:n1' in NK.ty()) && 'edit:n2' in NK.ty());
  assert(n.text === 'new words' && n.edited && n.replies.at(-1).unsent);
  // a draft changed after the check stays for the next Send
  NK.typed.set('n1', 'first');
  const [r] = P.tyRows(c); NK.typed.set('n1', 'second'); await r.save();
  assert.strictEqual(NK.typed.get('n1'), 'second');
  // Remove discards with Undo
  const back = P.tyRows(c).find(x => x.key === 'ty:reply:n1').remove(); assert(!NK.typed.has('n1')); back(); assert(NK.typed.has('n1'));
})().catch(e => { console.error(e); process.exit(1); });
""")


def test_reference_note_and_copy_wording_are_drafts_with_a_send_row():
    # the note being typed: stored as typed, back after reload, and a Send row that Send saves (r12 audit31 reference 1, questions 4)
    assert "ctx.prefs.set('draft:rnote', d)" in REF and "${esc(typedR(k))}</textarea>" in REF
    assert "if (r && !S.note) { S.note = r.a; S.tgt = r.tgt || null; if (!S.reach) S.reach = r.a; }" in REF
    row = grab(REF, "      if (tr && !one(tr)) it.push({key: 'rnn:'", "\n      // a document's note")
    assert "save: async () =>" in row and "c.api('api/comments'" in row and "undefined, true)" in row
    assert "now.text === tr.text" in row, "cleared only when delivered as listed"
    # Copy library wording as typed, shown again after a redraw or reload, cleared on Save or Cancel
    assert "ctx.prefs.set('draft:rcped', {ck: S.cpEd, html: e.target.innerHTML})" in REF
    assert "cpTyped(ck) != null ? cpTyped(ck) : esc(y)" in REF
    # History's chart Edit reads and reopens from the kit's draft store
    assert "typed != null && (S.ce = x.id)" in HIST and "unedit: id => { if (S.ce === id) S.ce = ''; }" in HIST
