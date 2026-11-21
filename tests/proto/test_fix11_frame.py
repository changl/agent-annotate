"""Ninth check: Send's Undo works or is gone; saved task comments stay in Send when the board read fails (r12 fix11)."""

from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
FRAME = (WEB / "frame.js").read_text()
RUN = (WEB / "running.js").read_text()
Q = (WEB / "questions.js").read_text()


def test_undo_goes_when_the_countdown_ends():
    """Frame 1: once the posts start, Undo leaves the page and a stray tap does nothing; the receipt comes before the re-read."""
    post = Q[Q.index("async function post("):Q.index("async function discardAll()")]
    assert post.index("S.pending.going = true; document.querySelectorAll('[data-sendundo]').forEach(b => b.remove());") < post.index("try {")
    ok = post[:post.index("} catch (e) {")]
    assert ok.index("S.pending = null;") < ok.index(".qsend.sending').forEach(x => x.remove())") < ok.index("ctx.toast(`Sent ") < ok.index("await refresh();")
    assert "if (t.hasAttribute('data-sendundo')) { if (!S.pending || S.pending.going) return;" in Q
    assert "S.sentPaint = true; S.sendN = 0;" in FRAME


def test_task_comments_list_from_what_was_saved():
    """Running 2: with running.json in but no board, the saved comment ids still come from the drafts."""
    items = RUN[RUN.index("P.queue && P.queue({"):RUN.index("sent: ctx =>")]
    assert "const ids = ctx.prefs.keys(/^tcm:/).map(k => k.slice(4));" in items
    assert "Object.keys(B)" not in items
    assert "ctx.prefs.keys(/^tcm:/).forEach(k => ctx.prefs.set(k, ''))" in RUN


def test_version_never_paints_before_its_counts():
    """Eighth-check frame 1: no timeout lets the version show with Send 0."""
    start = FRAME[FRAME.index("async function start()"):]
    assert "Promise.race" not in start
    assert start.index("putCounts(await readCounts());") < start.index("S.loadedV = meta && meta.current;")
