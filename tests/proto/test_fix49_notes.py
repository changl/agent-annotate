"""Fix49 (r12 audit42 reference 1, frame 1, running 1-2, questions 1): a note's Close, Re-open and their Undo reach every copy
of it (the reader's and the feed Send lists from), a Send never clears a closed note's edit, and the feed's `edited` matches
the round's rule for an edit in the second of its Send."""

from agent_annotate.proto_data.questions import note_thread
from test_fix17_notes import KIT, STUBS, node

FIX_STUBS = STUBS.replace("const P = {};", "const P = {ctx: null};")


def test_close_reopen_and_undo_reach_every_copy(tmp_path):
    node(tmp_path, FIX_STUBS + KIT + """
(async () => {
  // the reader's note and the feed's copy of it are separate objects; Send lists from the feed
  const shown = {id: 'e1', sent: true, edited: true, st: 'open', text: 'edited'}, feed = {notes: [{...shown}]};
  NK.lc(feed);
  const undo = await NK.set(c, shown, 'close', api, async () => {}, true);
  assert(feed.notes[0].closed && !NK.out(feed.notes[0]), 'a closed edit is neither listed nor sent');
  await undo();
  assert(!feed.notes[0].closed && NK.out(feed.notes[0]), 'Undo lists it again');
  // a read answering late takes the visit's state too
  await NK.set(c, shown, 'close', api, async () => {}, true);
  const late = NK.lc({notes: [{id: 'e1', sent: true, edited: true, st: 'open'}]});
  assert(late.notes[0].closed);
  // a Send while closed leaves its edit for the Re-open
  NK.gone(late.notes[0]);
  assert(late.notes[0].edited);
  await NK.set(c, late.notes[0], 'restore', api, async () => {}, true);
  assert(!shown.closed && NK.out(shown) && NK.out(feed.notes[0]), 'Re-open lists the edit once more everywhere');
})().catch(e => { console.error(e); process.exit(1); });
""")


def test_feed_edited_in_the_second_of_its_send():
    # whole-second stamps: an edit in its Send's second un-flags it, and the round takes it (_comment_needs_push)
    c = {"author": "you@example.com", "flagged_for_session": False, "flagged_at": "2026-11-24T11:47:21Z", "edited_at": "2026-11-24T11:47:21Z"}
    assert note_thread(c)["edited"]
    assert not note_thread({**c, "flagged_for_session": True})["edited"]
    assert not note_thread({**c, "edited_at": None})["edited"]
