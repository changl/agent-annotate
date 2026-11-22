"""Fix27 Send: the receipt and Last Send count what the server's round took, a noop says nothing new went, and the toolbar
count follows at once; a copy's simulated Send takes a note Discard's Undo put back (r12 audit23 frame 2, 3)."""

from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "src/agent_annotate/web/proto"


def test_receipt_counts_what_the_round_took():
    q = (WEB / "questions.js").read_text()
    # his listed unsent notes, kept for the receipt; another client's earlier Send leaves them out of this round
    assert "mine = D.notes.filter(x => listed.has(x.id) && !x.sent).map(x => x.id);" in q
    assert "const r = await call('api/rounds/submit'" in q
    assert "const got = r && r.delivery === 'noop' ? 0 : Math.max(0, n - (ids ? mine.filter(id => !ids.has(id)).length : 0));" in q
    assert "ctx.queueSent(got);" in q and "ctx.queueSent(n);" not in q  # Last Send: none on a noop
    assert "'Nothing new was sent: these items had already gone in an earlier Send'" in q
    # the toolbar's count is redrawn with the receipt, not after the re-read
    post = q[q.index("async function post("):q.index("async function discardAll(")]
    assert post.index("updateBar();") < post.index("ctx.toast(got ?")


def test_top_count_follows_a_noop_and_go_to_it_waits_for_its_target():
    f = (WEB / "frame.js").read_text()
    q = (WEB / "questions.js").read_text()
    assert "if (s.sent) s.sent(ctx); } catch (e) { console.warn('queue sent', e); } }); if (sendP && sendP.saved) S.sendN = savedN(); paintSend(); refreshSend(); }," in f
    # Go to it on a card or note waits for it (a cold read), then scrolls and outlines it: one path for every Send row
    assert "if (live() && anchor && /^[qn]-/.test(anchor)) goTarget(anchor, live);" in f
    assert "goTo: id => goTarget(id, () => true)," in f
    assert ".then(() => ctx.goTo('n-' + k.slice(2))); }" in q


def test_copy_send_takes_every_saved_copy_note():
    q = (WEB / "questions.js").read_text()
    sub = q[q.index("path === 'api/rounds/submit' && D"):q.index("P.copyWrite = fake;")]
    assert "for (const n of NOTES.add) NOTES.sent.add(n.id);" in sub
    # Discard's Undo re-reads, so the feed every Send count reads has the note again
    assert "if (D) await refresh();  // another tab's note put back" in q
