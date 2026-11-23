"""r12 audit36 frame 1-6 and questions 2-4, 6-7: one test per class."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
Q = (ROOT / "src/agent_annotate/web/proto/questions.js").read_text()
F = (ROOT / "src/agent_annotate/web/proto/frame.js").read_text()
PY = (ROOT / "src/agent_annotate/proto_data/questions.py").read_text()


def test_a_landed_write_stays_in_send_after_reload():
    # the feed carries the pending marker and who sent it by which path
    assert '"round_pending", "via"' in PY
    # a pending decision with no draft is its own Send row, answer or card reply
    assert "q.decision.round_pending && q.decision.mine !== false" in Q
    assert "'qp:' + q.id, '', false, q.id]" in Q and "`qr${j}:${q.id}`, '', false, q.id]" in Q
    # a Close archived by a failed round stays a row and goes again without a second archive
    assert "if (q.closed) { if (d.close)" in Q
    assert "(q.closed && !!draft(q.id).close)" in Q
    assert "for (const q of new Set([...closes, ...shut2])) if (!q.closed)" in Q
    # its draft clears only once the round lands
    assert Q.count("for (const q of closes) if (q.closed) setDraft(q.id, {close: null});") == 1
    assert "listed.keys.has('qp:' + q.id)) { q.decision.round_pending = false" in Q


def test_b_refusal_leaves_the_screen_as_it_was():
    # every take-back asks P.going before it changes anything
    assert "refused: id => !!P.going" in Q
    assert "if (NK.refused(was.edit)) return focus();" in Q
    # words typed since the check stay in the round's composer; untouched, the next spot opens (r12 audit38 questions)
    assert "if (newRefused(was)) { if (text.trim() !== CARRY.tw) return focus(); }" in Q
    assert "async function addNote(text, from) {\n    const n = from || S.note; if (!n || newRefused(n)) return;" in Q
    # Send it again Undo refuses before the cache changes, and restores on a wrapper refusal
    undo = Q.index("if (NK.refused(cid)) return;")
    assert undo < Q.index("draft:qnotes", undo)
    # Later refuses and catches, so no unhandled rejection; its Undo re-reads the live question
    assert "async function later(q, on) {\n    if (qRefused(q.id)) return;" in Q
    assert "if (!P.carried(e)) ctx.toast('Not changed: ' + e.message); return; }" in Q
    assert "undo: () => later(cur, !on)" in Q
    # a failed save puts the editor's words back
    assert "if (ed && !S.note) { S.note = ed; ctx.prefs.set('q:newnote', ed); }" in Q


def test_c_duplicate_and_equal_value_checks():
    # the dedup matches the path without its query string (Questions posts ?author=)
    assert "path.split('?')[0] === 'api/comments' && sendP && sendP.made" in F
    assert "path.split('?')[0] === 'api/comments'" in Q
    # creates the round holds are counted at the check, before their POST is sent
    assert "const mark = b => (CARRY.made = CARRY.made || new Set()).add(made(b));" in Q
    assert "CARRY.tn = tn.anchor" in Q
    # General feedback equal to the delivered words clears after a failed round
    assert "if (gen().trim() && w.gen === gen().trim()) ctx.prefs.set('q:general', '');" in Q
    # an answer the round already wrote is not mistaken for an unchanged draft
    assert "!WROTEQ.has(q.id)" in Q
    assert "WROTEQ.add(q.id)" in Q
