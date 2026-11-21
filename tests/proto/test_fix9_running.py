"""Seventh check, Running, History and Pages & links: one test per fixed item (the History data ones are in test_history.py)."""

from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
HIST, RUN, LINKS, QS = ((WEB / n).read_text() for n in ("history.js", "running.js", "links.js", "questions.js"))


def test_questions_leaves_document_notes_to_pages_and_links():
    """Reference 3: a Load-test bar note is Pages & links' Send entry only, so Remove/Undo leaves no stray Questions entry."""
    assert "!own.has(x.id) && !/^doc:/.test(x.anchor || '')" in QS


def test_first_approval_names_the_kept_document():
    """Reference 5: the first Send after approving names the document even before Pages & links has drawn."""
    assert "(KEPT || (LD || {}).kept || (ON ? ON.D.kept : null) || [])" in LINKS


def test_history_dates_sends_in_local_time_with_delivery():
    """Finding 2: the Send's own time in the browser's local time, and its delivery state beside it."""
    assert "sent ${esc(when(hs[0].at, hs[0].t))}" in HIST and "DELIV[hs[0].dl]" in HIST
    assert "acknowledged: 'read by the agent'" in HIST


def test_history_reference_lists_audits_and_copy_library():
    """Finding 4: a copy's findings audits and Copy library head History → Reference, each with its eye into Reference."""
    assert "x.find || x.id === 'copy-library'" in HIST
    assert "ctx.go('reference', b.dataset.href)" in HIST


def test_reloaded_note_keeps_its_line():
    """Finding 5: a note read back after a reload takes its line from its document."""
    assert "map(n => Object.assign(n, {line: lineOf(n)}))" in LINKS
    assert "doc:kept-([^~]+)~p~(\\d+)$" in LINKS


def test_phone_terminal_opens_the_worker_recap():
    """Finding 6: on a phone the terminal icon opens the worker's last report with Bring it forward on the Mac."""
    assert "if (innerWidth < 900) { S.peek = ds.term; return draw(); }" in RUN
    assert "Bring it forward on the Mac" in RUN and "${termSheet(ws)}" in RUN
