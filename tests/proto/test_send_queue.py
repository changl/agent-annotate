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
    assert "if (write) wrote(path, own);" in f and "wrote(path, own); return r; }" in f
    assert "document.addEventListener('click', refreshSend); document.addEventListener('input', refreshSend);" in f
    assert "#p-top [data-send], #p-layer [data-send]" in f and "drawFab();" in f[f.index("function refreshSend"):]


def test_questions_lists_counts_removes_and_clears_the_queue():
    s = _js("questions")
    assert "const sendCount = () => sendItems().filter(x => !x[4]).length + (gen().trim() ? 1 : 0);" in s  # the count is the sheet's rows: every queued item, each note once
    assert "for (const x of q) it.push([x.group, x.html, 'x:' + x.key, x.remove && !P.inflight(x.note || (/^ty:/.test(x.key) ? x.key.replace(/^ty:(edit|reply):/, '') : '')) ? 'x:' + x.key : '', x.peer != null ? !!x.peer : peer(x.note), x.note]);" in s
    assert "try { back = await x.remove(); }" in s  # Remove takes it out of its tab, with Undo
    assert "(await Promise.all(q.map(x => x.remove && x.remove()))).filter(Boolean)" in s  # Discard all too
    assert "if (ctx.queueSent) ctx.queueSent(got, listed.q);" in s  # a Send clears every tab's items
    assert "if (k.startsWith('x:'))" in s  # Go to it opens the item's own tab
    assert "wrote: (path, own) =>" in s  # notes written on other tabs reach Questions' list without a visit


def test_each_tab_queues_its_next_send_items():
    run, hist, ref, links = _js("running"), _js("history"), _js("reference"), _js("links")
    # running 1: status changes and task comments under Tasks
    assert "key: 'tst:' + id, group: 'Tasks'" in run and "key: k, group: 'Tasks'" in run
    assert "P.queue && P.queue({items, sent: (ctx, was, done) => {" in run
    # running 2: Tell the agent on a failed publish under Replies to the agent
    assert "group: 'Replies to the agent', html: `About the page that could not load:" in hist
    assert "TELL.set(o.src" in hist and "let told" not in hist
    # reference 4 and 5: notes, reopen reasons and copy-library choices
    assert "Finding “${c.esc(nm)}” → <b>reopened</b>" in ref and "if (!why.trim()) continue;" in ref
    assert "group: 'Notes', note: n.id" in ref and "for (const [ck, s] of S.cp)" in ref
    # running 4: notes on kept documents
    assert "group: 'Notes', note: n.id" in links and "K.draftActs(n, S.move === n.id)" in links


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
    assert "c.toast('Note changed · goes with Send'" in s


def test_send_opens_over_any_tab_at_any_count():
    """r12 fix7 frame 1, 2, 5: ⌘↵ from any tab, Send at zero on the desk, the sheet over the tab on screen."""
    f, s = _js("frame"), _js("questions")
    key = f[f.index("// ⌘↵ from any other tab"):f.index("if (e.key === 'Enter' && e.target.dataset")]
    assert "!onQuestions()" in key and "e.stopPropagation()" in key and "openSend(true)" in key
    assert "off = sendOff(cls)" in f and "!sendNum() && cls !== 'hide-ph')" in f  # the desk Send is never disabled
    assert "sendOff(t.classList.contains('hide-ph') ? 'hide-ph' : '')" in f
    op = s[s.index("function openSheet(c, key) {"):]
    assert "if (key && S.armed) return arm();" in op and "c.go('questions')" not in op  # never switches tab
    assert "className: 'area-questions tab-questions qhost'" in op
    assert "if (host) return drawHost();" in s and "(host || root).contains(t)" in s
    assert "if (host && e.key === 'Escape' && S.armed)" in s


def test_last_send_follows_a_new_send_and_skip_opens_the_phone_menu():
    """r12 fix7 frame 3 and 4."""
    f = _js("frame")
    assert "queueSent: (n, was) => { if (n) { prefs.set('lastSend', S.sent = {ts: new Date().toISOString(), n}); S.sentPaint = true; S.sendN = 0; }" in f
    chip = f[f.index("function lastSendChip"):f.index("function settingsBody")]
    assert "if (s && (COPY ||" in chip and "prototype: not sent" in chip and "delivered" not in chip[:chip.index("if (!r && !l)")]
    assert "if (kind === 'tabs' && phoneQ.matches && !S.home) { S.menu = 'nav';" in f and "#p-layer .pm-tab" in f


def test_discard_all_counts_items_as_send_lists_them():
    """r12 fix7, questions 5: an answer and a reply on one question are two drafts."""
    s = _js("questions")
    body = s[s.index("async function discardAll()"):s.index("async function sendRemove")]
    assert "total = sendItems().filter(x => x[3]).length + (gen().trim() ? 1 : 0);" in body and "Discarded ${pl(total, 'draft', 'drafts')}" in body
