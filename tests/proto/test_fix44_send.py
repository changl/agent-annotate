"""r12 audit37 frame 1-3, the class: every way a stored card reply or pending answer can be undelivered is its own Send row."""
import json

from agent_annotate.proto_data import questions as qd
from test_fix13_send import Q, grab, node

T0, T1, T2 = "2026-11-20T00:00:00Z", "2026-11-21T00:00:00Z", "2026-11-22T00:00:00Z"
LONG1, LONG2 = "First long reply " + "a" * 150, "Second reply with its own words " + "b" * 150


def _q(cid, n, **extra):
    return {"id": cid, "number": n, "version": "v2", "anchor_id": f"d:q{n}", "author": "agent:x", "status": "open", "text": f"Q{n}?",
            "decision_request": {"prompt": f"Q{n}?", "context": "", "options": [{"id": "a", "label": "A"}]}, **extra}


def _r(text, ts=T1, sent=None, author="member"):
    return {"author": author, "text": text, "ts": ts, "sent_at": sent}


def _page(tmp_path, monkeypatch):
    monkeypatch.setattr(qd, "BOARD", str(tmp_path / "no-board"))
    page = tmp_path / "page"
    (page / "versions").mkdir(parents=True)
    (page / "versions" / "v2.html").write_text("<div>Doc</div>")
    sent = {"verdict": "select", "option_id": "a", "text": "A", "ts": T0, "by": "member"}
    pend = {"verdict": "select", "option_id": "a", "text": "A", "ts": T2, "by": "member", "round_pending": True}
    anchors = {
        "d:q1": [_q("c1", 1, replies=[_r("✓ plain words")])],  # open, any opening characters
        "d:q2": [_q("c2", 2, decision=sent, flagged_at=T0, replies=[_r("☑ Selected: A", T0, T0), _r("after the answer")])],  # answered
        "d:q4": [_q("c4", 4, answer_later={"ts": T0, "by": "member"}, replies=[_r("set aside reply")])],  # set aside
        "d:q5": [_q("c5", 5, replies=[_r(LONG1), _r(LONG2, T2), _r("agent says", T2, None, "agent:x")])],  # several per card
        # mixed with a decision: its own generated line (same ts and author) is no reply; his typed lines are, whatever they open with
        "d:q6": [_q("c6", 6, decision=pend, replies=[_r("☑ Selected: A", T2), _r("☑ Selected: my own words", T1), _r("↺ my words", T2)])],
        "d:q8": [_q("c8", 8, decision=pend, answer_later={"ts": T0, "by": "member"})],  # set aside, answer pending
    }
    archived = {
        "d:q3": [_q("c3", 3, status="archived", archived_by="member", replies=[_r("reply on a closed card")])],  # archived
        "d:q7": [_q("c7", 7, status="archived", archived_by="member", decision=pend, replies=[_r("☑ Selected: A", T2)])],  # archived, answer pending
    }
    (page / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": anchors, "archived": archived}))
    (page / "current.meta.json").write_text(json.dumps({"current": "v2", "history": []}))
    return page


def test_every_undelivered_reply_and_answer_is_its_own_row(tmp_path, monkeypatch):
    qs = qd.build(_page(tmp_path, monkeypatch))["questions"]
    assert [q["n"] for q in qs] == [1, 2, 3, 4, 5, 6, 7, 8]
    items = grab(Q, "function sendItems() {", "\n    return it;\n  }")
    pend = grab(Q, "const pendA = ", "in words: “${esc(cut(String(pd.text || ''), 120))}”`; };")
    js = """
const esc = s => String(s), cut = (s, n) => String(s).slice(0, n), optLabel = (q, id) => (q.options.find(o => o.id === id) || {}).label;
const drafts = {c3: {close: true}}, draft = id => drafts[id] || {}, isDraft = q => false;
const isClosing = q => !q.closed && !!draft(q.id).close, hasReply = q => false, abPicks = () => ({}), Q = () => [], notesNow = () => [];
const typingNote = () => null, mk = s => s, NK = {}, P = {};
const D = {questions: %s, notes: []};
""" % json.dumps(qs) + pend + "\n" + items + r"""
const rows = sendItems(), keys = rows.map(r => r[2]), html = rows.map(r => r[1]);
const want = ['qr0:c1', 'qr1:c2', 'qr0:c3', 'c:c3', 'qr0:c4', 'qr0:c5', 'qr1:c5', 'qp:c6', 'qr1:c6', 'qr2:c6', 'qp:c7', 'qp:c8'];
if (JSON.stringify(keys) !== JSON.stringify(want)) throw new Error('rows ' + JSON.stringify(keys));
const has = (k, w) => { const h = html[keys.indexOf(k)]; if (!h.includes(w)) throw new Error(k + ' lacks ' + w + ': ' + h); };
has('qr0:c1', '✓ plain words'); has('qr0:c3', 'reply on a closed card'); has('qr0:c4', 'set aside reply');
has('qr0:c5', 'First long reply'); has('qr1:c5', 'Second reply with its own words');
if (html[keys.indexOf('qr0:c5')].includes('Second')) throw new Error('two replies merged');
has('qr1:c6', '☑ Selected: my own words'); has('qr2:c6', '↺ my words');
"""
    node(tmp_path, js)
    # the card's thread hides only the decision's own line, by the store, never by words
    assert "q.replies.filter(r => !r.dec)" in Q and "SYS" not in Q
    # the round: a closed card with pending rows opens before the submit and closes after it; a Close archives only after
    # the round is in, so the server's round (which skips archived cards) carries the card's reply and answer
    post = grab(Q, "async function post(", "\n  // Discard all")
    sub, fail = post.index("api/rounds/submit"), post.index("} catch (e) {")
    assert post.index("/restore`") < sub < post.index("for (const q of new Set([...closes, ...shut2])) if (!q.closed)") < fail
    assert "/archive`" not in post[:sub]
    assert "for (const q of shut2) if (!q.closed)" in post[fail:]  # a failed round leaves the card closed as it was
    assert "if (listed.keys.has(`qr${j}:${q.id}`)) r.sent = true" in post  # each delivered reply by its own row
    # Go to it on a pending row opens its card
    assert "if (at) k = 'q:' + k.slice(k.indexOf(':') + 1);" in Q
