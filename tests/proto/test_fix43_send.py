"""r12 audit36 class A, every kind; questions 5 (picture change); reference (dedup by the full spot)."""
import json

from agent_annotate.proto_data import questions as qd
from test_fix13_send import FRAME, Q, REF, grab, node, WEB

LINKS = (WEB / "links.js").read_text()

# each kind a round writes before its submit, the store it lands in, and the Send row that reads that store after a reload
KINDS = {
    "answer": "decision.round_pending",
    "written answer": "decision.round_pending",
    "card reply": "reply sent_at none",
    "task-filing request": "reply sent_at none",
    "Close": "draft close",
    "Re-open": "draft:reopen",
    "Move": "draft:nkput moved",
    "sent-note edit": "draft:nkput",
    "sent-note reply": "draft:nkput",
    "task status": "tst",
    "task comment": "tcm:",
}


def test_every_kind_stays_in_send_after_a_failed_round(tmp_path):
    pend = grab(Q, "const pendA = ", "in words: “${esc(cut(String(pd.text || ''), 120))}”`; };")
    js = """
const esc = s => String(s), cut = (s, n) => String(s).slice(0, n), optLabel = (q, id) => (q.options.find(o => o.id === id) || {}).label;
""" + pend + r"""
const base = {n: 11, options: [{id: 'approve', label: 'Approve'}], replies: [], sent: false, closed: false};
const pick = {...base, decision: {verdict: 'select', option_id: 'approve', text: 'Approve', round_pending: true, mine: true},
  replies: [{you: true, sent: false, dec: true, text: '☑ Selected: Approve'}]};
const words = {...base, decision: {verdict: 'comment', text: 'Run it first', round_pending: true, mine: true}};
const reply = {...base, decision: {verdict: 'comment', text: 'Why?', via: 'reply', round_pending: true, mine: true}, replies: [{you: true, sent: false, text: 'Why?'}]};
const file = {...base, sent: true, decision: {verdict: 'select', option_id: 'approve'}, replies: [{you: true, sent: false, text: 'Please file a task'}]};
const sent = {...base, sent: true, decision: {verdict: 'select', option_id: 'approve'}, replies: [{you: true, sent: true, text: 'old'}]};
const peer = {...base, decision: {verdict: 'select', option_id: 'approve', round_pending: true, mine: false}};
const ok = (c, m) => { if (!c) throw new Error(m); };
ok(pendA(pick) && /Approve/.test(pendW(pick, pendA(pick))) && !pendR(pick).length, 'a pending pick is an answer row, its thread line no reply');
ok(pendA(words) && /Run it first/.test(pendW(words, pendA(words))), 'a pending written answer is an answer row');
ok(!pendA(reply) && pendR(reply).length === 1, 'a card reply that answered the card is one reply row');
ok(!pendA(file) && pendR(file).length === 1, 'an Ask to file on an answered card is a reply row');
ok(!pendA(sent) && !pendR(sent).length, 'delivered: no row');
ok(!pendA(peer), "a peer's pending answer is not his row");
ok(pendA({...pick, closed: true}) && pendR({...reply, closed: true}).length === 1, 'a closed card keeps its pending rows (r12 audit37 frame 1)');
"""
    node(tmp_path, js)
    items = grab(Q, "function sendItems() {", "\n    return it;")
    assert "pendA(q)" in items and "pendR(q)" in items and "`qr${j}:${q.id}`" in items
    # Close keeps its draft through a failed round, and its row reads the draft on a closed card
    assert "if (q.closed) { if (d.close)" in items
    # the store kinds without a write before submit: their drafts clear only on a delivered round
    post = grab(Q, "async function post(", "\n  // Discard all")
    went, fail = post[post.index("api/rounds/submit"):post.index("} catch (e) {")], post[post.index("} catch (e) {"):]
    for k in ("ctx.prefs.set('draft:reopen', {})", "NK.L = Object.fromEntries(L1)", "for (const q of closes) if (q.closed) setDraft(q.id, {close: null});"):
        assert k in went, k
    assert "draft:reopen" not in fail and "draft:nkput" not in fail and "setDraft" not in fail
    # every reader's Send count and sheet are Questions' one list
    assert "count: async (c, again) => { await load(c, again); return sendCount(); }" in Q and "open: openSheet" in Q
    assert "sendP.count" in FRAME and "sendP.open" in FRAME
    # the card says a pending answer goes with Send, and the thread marks his unsent replies
    assert "const pd = pendA(q); if (pd) return" in Q and "r.you && !r.sent ? ' · not sent' : ''" in Q
    assert len(KINDS) == 11


def test_feed_reply_sent_follows_the_server_rule():
    flagged = {"flagged_at": "2026-11-20T00:00:00Z"}
    mine = lambda r: qd._reply_unsent(flagged, r)
    orig = qd._mine
    qd._mine = lambda a: a == "me"
    try:
        assert mine({"author": "me", "sent_at": None, "ts": "2026-11-19T00:00:00Z"})
        assert not mine({"author": "me", "sent_at": "2026-11-21T00:00:00Z"})
        assert not mine({"author": "me", "ts": "2026-11-19T00:00:00Z"})  # an older reply, before sent_at: by the last Send
        assert mine({"author": "me", "ts": "2026-11-21T00:00:00Z"})
        assert not mine({"author": "agent:x", "sent_at": None})
    finally:
        qd._mine = orig
    src = (WEB.parents[1] / "proto_data/questions.py").read_text()
    assert '"sent": not _reply_unsent(c, r)' in src and '"round_pending", "via"' in src


def test_failed_picture_change_leaves_no_note():
    post = grab(Q, "async function post(", "\n  // Discard all")
    assert "abW.push([a, p, w.id])" in post
    fail = post[post.index("} catch (e) {"):]
    d, s, f = fail.index("'DELETE'"), fail.index("if (!abPicks()[a]) setAB(a, p);"), fail.index("qFailed()")
    assert d < s < f  # the note goes, the pick is a draft again, then a pick back at its delivered side drops off
    assert "if (w['ab:' + a] === p.side) setAB(a, null)" in Q


def test_dedup_keys_the_full_spot(tmp_path):
    made = grab(Q, "const made = b => ", ";")
    node(tmp_path, made + r"""
const a = made({anchor_id: 'img1', text: 'same', target: {schema: 1, tag: 'img', offset: {dx: 0.1, dy: 0.2}}});
const b = made({anchor_id: 'img1', text: 'same', target: {schema: 1, tag: 'img', offset: {dx: 0.7, dy: 0.2}}});
const c = made({anchor_id: 'img1', text: ' same ', target: {schema: 1, tag: 'img', offset: {dx: 0.1, dy: 0.2}}});
const r1 = made({anchor_id: 'p1', text: 'x', target: {quote: 'alpha'}}), r2 = made({anchor_id: 'p1', text: 'x', target: {quote: 'beta'}});
if (a === b || a !== c || r1 === r2) throw new Error('the spot is the anchor and its full target');
""")
    # every reader's typed note marks its target at the check, and a landed save clears only its own spot's draft
    assert "target: tn.target" in Q and "target: x.tgt" in Q
    assert "{key: 'rnn:' + tr.a, tgt: tr.tgt || undefined" in REF and "{key: 'lnn:' + d.a, group: 'Notes', tgt: d.tgt || undefined" in LINKS
    for src in (REF, LINKS):
        assert src.count("JSON.stringify(now0.tgt || null) === JSON.stringify(") == 1
    assert "JSON.stringify(n.target || null) === CARRY.tt" in Q
    assert "JSON.stringify(e.target || null) === JSON.stringify(tn.target || null)" in Q
