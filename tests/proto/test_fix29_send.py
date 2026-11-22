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


def test_every_send_row_uses_the_row_owner():
    q = (WEB / "questions.js").read_text()
    assert "NK.rowRm(n) ? 'note:' + n.id : '', !NK.mine(n), n.id]" in q and "return !!n && !NK.mine(n); };" in q
    assert "if (NK.out(n) && NK.mine(n)) ids.add(n.id);" in q  # a copy's simulated round
    for f, s in [("links.js", "peer: !P.notes.mine(n)"), ("history.js", "peer: !P.notes.mine(n)"), ("reference.js", "peer: !NK().mine(n)")]:
        assert s in (WEB / f).read_text(), f
