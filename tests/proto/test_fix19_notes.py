"""Fix19 notes (r12 audit17): every draft write goes through the one Re-open store. Close drops a pending Re-open and
its Undo brings it back; an earlier build's status-only records count as the store loads; ⌘↵ opens Send from any focus;
resolutions reach table rows; a checklist Go to it waits for the data; the picture viewer closes for View resolution;
Escape, the viewer closing and leaving a tab cancel Move; + Comment in Cards only and heading clicks open composers."""

from test_fix18_notes import KIT, L, Q, REF, STUBS, WEB, node

FRAME = (WEB / "frame.js").read_text()
HIST = (WEB / "history.js").read_text()


def test_close_drops_a_reopen_and_undo_brings_it_back(tmp_path):
    """Frame 1: Close a re-opened note: Send lists nothing; Undo: the Re-opened row is back."""
    node(tmp_path, STUBS + KIT + """
(async () => {
  const n = {id: 'r1', sent: true, st: 'resolved_in_version', a: 'ref:plan~v1~2', text: 'x'};
  await NK.set(c, n, 'reopen', api, async () => {});
  assert.strictEqual(src[0].items(c).length, 1);
  const undo = await NK.set(c, n, 'close', api, async () => {});
  assert.strictEqual(src[0].items(c).length, 0); assert(n.closed);
  await undo();
  assert.strictEqual(src[0].items(c).length, 1); assert(!n.closed);
  // a Close an earlier build left queued is dropped when the note is seen closed
  assert(!NK.isReo(c, {...n, closed: true})); assert.strictEqual(src[0].items(c).length, 0);
})().catch(e => { console.error(e); process.exit(1); });
""")


def test_legacy_status_record_counts_at_load_and_finds_its_note(tmp_path):
    """Frame 5: id → status from the previous build is a record as soon as the store loads, then learns its spot."""
    node(tmp_path, STUBS + KIT + """
(async () => {
  store['draft:reopen'] = {old: 'resolved_in_version'};
  c.data = async a => a === 'reference' ? {notes: [{id: 'old', anchor: 'chk:1', text: 'Check it', label: 'Second row'}]} : {notes: []};
  const items = src[0].items(c);
  assert.strictEqual(items.length, 1); assert(/A note the agent addressed/.test(items[0].html));
  await new Promise(r => setTimeout(r, 10));
  const r = store['draft:reopen'].old;
  assert.strictEqual(r.st, 'resolved_in_version'); assert.strictEqual(r.a, 'chk:1'); assert.strictEqual(r.tab, 'reference');
})().catch(e => { console.error(e); process.exit(1); });
""")


def test_move_carries_a_reopen_to_its_new_spot(tmp_path):
    """Root cause: Move rewrites the stored record, so Send's row and Go to it follow the note."""
    node(tmp_path, STUBS + KIT + """
(async () => {
  const n = {id: 'm1', sent: true, st: 'resolved_in_version', a: 'doc:a.md~1', text: 'x'};
  await NK.set(c, n, 'reopen', api, async () => {});
  await NK.move(c, 'm1', {anchor_id: 'doc:a.md~1'}, {anchor_id: 'doc:a.md~4', anchor_label: 'Line four'}, api, async () => {});
  const r = store['draft:reopen'].m1;
  assert.strictEqual(r.a, 'doc:a.md~4'); assert.strictEqual(r.on, 'Line four'); assert.strictEqual(r.st, 'resolved_in_version');
})().catch(e => { console.error(e); process.exit(1); });
""")


def test_cmd_enter_from_a_note_button_opens_send():
    """Frame 2: only a note's own editor saves on ⌘↵; a saved note's Copy button falls through to Send."""
    assert "e.target.tagName === 'TEXTAREA' && e.target.closest('.qnote')" in Q


def test_resolution_reaches_table_rows_in_links():
    """Frame 3: a resolution key with a row (~1~r2) finds the row's line."""
    assert r"/^(.*?)~(\d+(?:~r\d+)?)$/" in L and L.count("lineKey(") >= 2  # a kept page's line is its anchor (fix25), a file's its number


def test_checklist_go_to_it_waits_for_the_data():
    """Frame 4: a checklist anchor names no Reference item; Go to it opens the checklist once the read answers."""
    assert "a.startsWith('chk:') ? (D && D.checklist ? D.checklist.plan : '')" in REF
    assert "/^chk:/.test(S.reach) && D.checklist && !anchor" in REF


def test_viewer_closes_for_view_resolution():
    """Reference 3: View resolution inside the picture viewer closes it first, in every viewer."""
    assert "if (n && S.full) { S.full = null; S.spot = S.pin = ''; NK().endMove(false); }" in REF
    assert "S.zoom = null; S.spot = null; S.move = null;" in Q


def test_escape_viewer_close_and_leaving_cancel_move():
    """Reference 4: Escape anywhere, the viewer closing and leaving the tab each cancel Move, on every surface."""
    assert "data-nmove][aria-pressed=\"true\"]" in FRAME
    assert "S.full = null; draw(); }" in REF and "if (!!S.full !== !!S.fWas)" in REF  # fix20: the viewer's open or close ends it
    assert "NK().slot(S, 'reference'); restoreDrafts();" in REF  # fix20: a render never clears its own tab's Move
    assert "render: async (main, c" in REF and "P.notes.slot(S, 'links');  //" in L and "P.notes.slot(S, 'history', 'cmove');  //" in HIST
    assert "if (S.move) { const all = [...w.querySelectorAll('.l-doc [data-lzoom]')]" in L  # the shared viewer ends a Move
    assert "ctx = c; root = el; S.move = null;" in Q


def test_cards_only_comment_and_heading_notes():
    """Questions 1 and 3: + Comment in Cards only keeps the card's question; a heading click notes its section."""
    assert "const inq = card ? card.dataset.q : undefined;" in Q
    assert "e.target.closest('h1,h2,h3,h4,h5,h6')" in Q
