"""Fix30 Send (r12 audit26): the open sheet keeps General feedback's focus through every redraw, never shows a false
"Nothing ready yet", names only the reads that failed, and a release note's pending edit (words, Move, Re-open) is its
editor's, not its author's."""

import json
from pathlib import Path

from agent_annotate import proto_data
from agent_annotate.proto_data import published
from agent_annotate.proto_data.questions import note_thread, own

WEB = Path(__file__).resolve().parents[2] / "src/agent_annotate/web/proto"
ME, PEER = "you@example.com", "peer@example.com"
SENT = {"id": "n", "status": "open", "flagged_for_session": True, "flagged_at": "2026-11-21T10:00:00Z", "created_at": "2026-11-21T09:00:00Z",
        "edited_at": "2026-11-21T12:00:00Z"}


def feed(c):
    """A release note as this reader's feed gives it: named by _who, then the note fields, then own()."""
    published._here.h = published._hash(ME)
    try:
        n = note_thread(published._who(c))
    finally:
        del published._here.h
    return json.loads(own(json.dumps(n).encode(), {proto_data.MASK}))


def test_a_release_edit_is_its_editors():
    """Questions check 3, frame check 2: a peer's Move or words edit on his sent note is the peer's; his edit on a
    peer's note is his. 2.32.8 records the editor in edited_by on every PUT (words, Move, Re-open)."""
    assert feed({**SENT, "author": ME, "edited_by": PEER, "edited_by_email": PEER})["ed"]["by"] is not True
    assert feed({**SENT, "author": PEER, "edited_by": ME, "edited_by_email": ME})["ed"]["by"] is True
    assert feed({**SENT, "author": ME, "edited_by": ME})["ed"]["by"] is True
    assert {"edited_by", "edited_by_email"} <= set(published.WHO)


def test_every_redraw_keeps_general_feedback_focus():
    """Running 1: draw (any reason: a read landing, a relist) and drawHost give the field its focus and selection back
    at once, right after the rebuild, before the next keystroke."""
    q = (WEB / "questions.js").read_text()
    d = q[q.index("  async function draw(keepScroll) {"):q.index("  function listView() {")]
    assert d.count("typeOn(k);") == 2 and "k = typingIn();" in d
    h = q[q.index("  function drawHost() {"):q.index("  /* ---------- draw ---------- */")]
    assert "const k = typingIn();" in h and "typeOn(k);" in h
    assert "e.setSelectionRange(k.a, k.b)" in q


def test_nothing_ready_only_when_every_read_is_in():
    """Running 2: Questions' own read counts, held or failed, as Reference's and Pages & links' do."""
    q = (WEB / "questions.js").read_text()
    assert "const allRead = () => !!(S.oin && D && !S.qerr);" in q
    assert q.count("Nothing ready yet.</p>") == 1 and "(allRead() ? `<p class=\"small mut\" data-snone" in q


def test_a_failed_read_names_only_itself():
    """Questions check 4: a Pages & links failure alone says Pages & links, not Reference."""
    q = (WEB / "questions.js").read_text()
    assert "[['reference', 'Reference'], ['links', 'Pages &amp; links']]" in q
    assert "The notes on ${S.oerr} could not be read" in q


def test_the_shortcut_callout_only_while_send_is_on():
    """Reference check 2: "Press ⌘↵ again" shows only while Send is enabled (every read in, something to send)."""
    q = (WEB / "questions.js").read_text()
    assert "${S.sendKey && ok ? `<div class=\"qsendkey\"" in q and "const ok = n && D && S.oin," in q


def test_phone_home_shows_the_page_count():
    """Frame check 3: the mock's phone Home names each project's page count on its first line."""
    css = (WEB / "frame.css").read_text()
    assert ".hpg{display:none}" not in css and ".wbar,.hpg{display:none}" not in css
