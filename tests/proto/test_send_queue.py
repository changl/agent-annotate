"""Round 12 fix6: one Send that collects what every tab says "goes with your next Send" (no JS runner here;
the browser replays are in round12/fix6/send/drive.mjs)."""

from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "src/agent_annotate/web/proto"


def _js(name):
    return (WEB / f"{name}.js").read_text()


def test_frame_owns_one_queue_and_repaints_send():
    f = _js("frame")
    assert "P.queue = src => { SRC.push(src); refreshSend(); };" in f
    assert "queued, queueSent:" in f
    # writes from any tab tell Questions and repaint Send; clicks and typing do too, so the count follows on every tab
    assert "if (write) wrote(path);" in f and "wrote(path); return r; }" in f
    assert "document.addEventListener('click', refreshSend); document.addEventListener('input', refreshSend);" in f
    assert "#p-top [data-send], #p-layer [data-send]" in f and "drawFab();" in f[f.index("function refreshSend"):]


def test_questions_lists_counts_removes_and_clears_the_queue():
    s = _js("questions")
    assert "+ myNotes(q).length + q.length +" in s  # the count includes every queued item, each note once
    assert "for (const x of q) it.push([x.group, x.html, 'x:' + x.key, 'x:' + x.key]);" in s
    assert "const back = await x.remove(); await again();" in s  # Remove takes it out of its tab, with Undo
    assert "(await Promise.all(q.map(x => x.remove()))).filter(Boolean)" in s  # Discard all too
    assert "if (ctx.queueSent) ctx.queueSent();" in s  # a Send clears every tab's items
    assert "if (k.startsWith('x:'))" in s  # Go to it opens the item's own tab
    assert "wrote: path =>" in s  # notes written on other tabs reach Questions' list without a visit


def test_each_tab_queues_its_next_send_items():
    run, hist, ref, links = _js("running"), _js("history"), _js("reference"), _js("links")
    # running 1: status changes and task comments under Tasks
    assert "key: 'tst:' + id, group: 'Tasks'" in run and "key: k, group: 'Tasks'" in run
    assert "sent: ctx => { ctx.prefs.set('tst', {});" in run
    # running 2: Tell the agent on a failed publish under Replies to the agent
    assert "group: 'Replies to the agent', html: `About the page that could not load:" in hist
    assert "TELL.set(o.src" in hist and "let told" not in hist
    # reference 4 and 5: notes, reopen reasons and copy-library choices
    assert "Finding “${c.esc(f.label || fk)}” → <b>reopened</b>" in ref and "if (!why.trim()) continue;" in ref
    assert "group: 'Notes', note: n.id" in ref and "for (const [ck, s] of S.cp)" in ref
    # running 4: notes on kept documents
    assert "group: 'Notes', note: n.id" in links and "mine.includes(n) && !n.sent" in links


def test_general_feedback_in_the_sheet_updates_its_count():
    """questions 02: typing General feedback inside Send repaints the heading and buttons in place."""
    s = _js("questions")
    assert "if (was !== !!t.value.trim()) S.armed ? sheetCount() : updateBar();" in s
    body = s[s.index("function sheetCount()"):s.index("function updateBar()")]
    assert "Send to the agent · ${pl(n, 'item', 'items')}" in body and "[data-send]" in body and "[data-discard]" in body


def test_marker_on_edit_back_to_waiting_and_restore():
    """questions 03, frame 4: each of these toasts with Undo, so a copy shows 'prototype: not sent'."""
    s = _js("questions")
    assert "ctx.toast(on ? 'Set aside for later' : 'Back to waiting', {undo: () => later(q, !on)});" in s
    assert "ctx.toast('Restored to waiting', {undo:" in s
    assert "ctx.toast('Note changed · goes with Send'" in s
