"""Sixth check, Running and Pages & links: one test per fixed item."""

from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
HIST, RUN, LINKS, FRAME = ((WEB / n).read_text() for n in ("history.js", "running.js", "links.js", "frame.js"))


def test_go_to_it_from_running_opens_the_task():
    """Finding 1: from Running the hash is unchanged, so Go to it opens the task itself."""
    assert "location.hash === '#running' && tabNow === 'running' && EL && EL.isConnected) openTask(id)" in RUN


def test_failed_publish_reply_is_a_draft_pref():
    """Finding 2: the reply lives under a draft key, so it survives a reload when drafts are remembered."""
    assert "'draft:tell'" in HIST and "draft:.*" in FRAME
    assert "new Map(), LIVE" not in HIST


def test_document_note_is_named_by_its_line_and_go_to_it_lands_on_it():
    """Finding 3 and reference 1: Send names the line; Go to it opens the document and scrolls to the outlined note."""
    assert "|| n.line || n.l ||" in LINKS
    assert "go: () => goNote(c, n)" in LINKS
    assert "S.hl === n.id ? ' l-hl' : ''" in LINKS
    assert "h.scrollIntoView({block: 'center'})" in LINKS


def test_kept_document_approve_goes_with_send():
    """Reference 3: Approve beside Write a note, listed under Reference in Send, with Undo."""
    assert "${apprBtn(ctx, d.id)}" in LINKS
    assert "'✓ Approved · Undo' : 'Approve'" in LINKS
    assert "group: 'Reference', html: `${c.esc(d ? d.t : tl[id] || id)} → <b>approved</b>`" in LINKS
