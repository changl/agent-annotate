"""Fix29 Send: a Send row's owner is the author of what is pending on it (a reply's, an edit's), as the server's round
takes it, not the note's author, so the counts, the peer label and Remove agree with the round (r12 audit25 running 1)."""

import json
from pathlib import Path

from agent_annotate.sync_server import _comment_needs_push
from test_fix17_notes import KIT, STUBS, node
from test_fix23_actions import BASE, ME, proto

WEB = Path(__file__).resolve().parents[2] / "src/agent_annotate/web/proto"
PEER = "peer@example.com"
T2 = "2026-11-21T12:00:00Z"
reply = lambda who, text: {"replies": [{"author": who, "text": text, "ts": T2, "sent_at": None}]}
BASE = {**BASE, "created_at": "2026-11-21T09:00:00Z"}
CASES = {
    "peer-reply-on-own-note": {**BASE, **reply(PEER, "peer's reply")},
    "own-reply-on-peer-note": {**BASE, "author": PEER, **reply(ME, "my reply")},
    "peer-reply-on-peer-note": {**BASE, "author": PEER, **reply(PEER, "peer's reply")},
    "own-draft": {**BASE, "flagged_for_session": False, "flagged_at": None},
    "peer-draft": {**BASE, "author": PEER, "flagged_for_session": False, "flagged_at": None},
    "peer-edit-on-own-note": {**BASE, "flagged_for_session": False, "edited_at": T2, "edited_by": PEER},
    "own-edit-on-peer-note": {**BASE, "author": PEER, "flagged_for_session": False, "edited_at": T2, "edited_by": ME},
    # a status or anchor PUT (Re-open, Move) keeps the flag: the edit is its editor's alone
    "own-reopen-on-peer-note": {**BASE, "author": PEER, "edited_at": T2, "edited_by": ME},
    "peer-reopen-on-own-note": {**BASE, "edited_at": T2, "edited_by": PEER},
    "both-on-own-note":{**BASE, "flagged_for_session": False, "edited_at": T2, "edited_by": ME, **reply(PEER, "peer's reply")},
}


def test_row_owner_is_the_round_owner(tmp_path):
    want = {k: _comment_needs_push(c, {ME}) for k, c in CASES.items()}
    assert want["own-reply-on-peer-note"] and not want["peer-reply-on-own-note"] and not want["peer-reply-on-peer-note"]
    feed = {k: proto(c) for k, c in CASES.items()}
    node(tmp_path, STUBS.replace("const P = {};", "const P = {ctx: null};") + KIT + f"""
const feed = {json.dumps(feed)}, want = {json.dumps(want)};
for (const [k, n] of Object.entries(feed)) {{
  if (!NK.out(n)) {{ assert(!want[k], k + ' not listed'); continue; }}
  assert.strictEqual(NK.mine(n), want[k], k);
  assert.strictEqual(NK.mine({{id: n.id, text: 'x', ...NK.state(n)}}), want[k], k + ' saved row');  // before a read, after a reload
  if (n.replies.length) assert(!NK.rowRm(n), k + ' no Remove on a note with replies');
}}
// his row names his own reply alone; a peer's row names the peer's
assert.strictEqual(NK.say({{...feed['both-on-own-note'], text: 'my edit'}}), 'my edit');
assert.strictEqual(NK.say(feed['own-reply-on-peer-note']), 'Reply: my reply');
assert.strictEqual(NK.say(feed['peer-reply-on-own-note']), "Reply: peer's reply");
// a Send takes his part only: a peer's pending reply stays pending
const both = feed['both-on-own-note']; NK.gone(both);
assert(!both.edited && both.replies[0].unsent && !NK.mine(both));
const theirs = feed['peer-reply-on-own-note']; NK.gone(theirs); assert(theirs.replies[0].unsent);
""")


def test_open_sheet_reads_and_relists_whatever_opened_it():
    """Questions 1, 2: the sheet starts its own reads on every open path, and relists once they land even while General
    feedback has the focus, keeping the words and the cursor."""
    q = (WEB / "questions.js").read_text()
    panel = q[q.index("  function sendPanel(n) {"):q.index("  function sendPanel(n) {") + 400]
    assert "if (!S.oin && !S.oerr) readOthers(ctx);" in panel
    rel = q[q.index("  async function relist() {"):q.index("  // copyOf is the project's key")]
    assert "/^(TEXTAREA|INPUT)$/" not in rel and "if (!S.armed || !s) return;" in rel
    assert "a.matches('[data-general]') && [a.selectionStart, a.selectionEnd]" in rel and "g.focus(); g.setSelectionRange(...t);" in rel


def test_a_failed_read_says_so_with_try_again():
    """Frame 1: a failed Reference or Pages & links read leaves Send waiting, says what failed with Try again, never
    "Nothing ready yet"; Try again reads again; typing in the sheet never enables Send before the reads are in."""
    q = (WEB / "questions.js").read_text()
    assert ".then(() => true, () => false)))" in q and "S.oerr = ok.includes(false); if (S.oerr) others = null; else S.oin = true; relist();" in q
    assert "could not be read: Send waits for them.</span> <button class=\"lk small\" data-sothersretry>Try again</button>" in q
    assert "if (t.hasAttribute('data-sothersretry')) { S.oerr = false; readOthers(ctx); return draw(true); }" in q
    assert "(S.oin ? `<p class=\"small mut\" data-snone" in q  # Nothing ready yet only once the reads are in
    assert "$('[data-send]').disabled = !n || !D || !S.oin;" in q and "$('[data-discard]').disabled = !n || !D || !S.oin;" in q


def test_a_reopen_row_is_the_reopeners():
    """Questions 3: his Re-open on a peer's note is his row; a row naming its owner keeps it."""
    q = (WEB / "questions.js").read_text()
    assert "({key: 'reo:' + id, group: 'Notes', note: id, peer: false," in q
    assert "x.peer != null ? !!x.peer : peer(x.note), x.note]" in q


def test_every_send_row_uses_the_row_owner():
    q = (WEB / "questions.js").read_text()
    assert "NK.rowRm(n) ? 'note:' + n.id : '', !NK.mine(n), n.id]" in q and "return !!n && !NK.mine(n); };" in q
    assert "if (NK.out(n) && NK.mine(n)) ids.add(n.id);" in q  # a copy's simulated round
    for f, s in [("links.js", "peer: !P.notes.mine(n)"), ("history.js", "peer: !P.notes.mine(n)"), ("reference.js", "peer: !NK().mine(n)")]:
        assert s in (WEB / f).read_text(), f
