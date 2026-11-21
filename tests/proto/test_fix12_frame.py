"""Tenth check: stalled first reads offer Try again, Reload says "Up to date" only once confirmed,
Remove then Esc keeps its Undo, and C keeps the answer field through a late redraw (r12 fix12 frame)."""

from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
FRAME = (WEB / "frame.js").read_text()
Q = (WEB / "questions.js").read_text()


def test_every_read_gives_up_at_20_seconds_but_no_write_does():
    """Frame 1: the version and metadata read at startup can no longer hold the frame blank for ever."""
    api = FRAME[FRAME.index("async function api("):FRAME.index("const wrote =")]
    assert "return write ? go : Promise.race([go, late()]);" in api
    start = FRAME[FRAME.index("async function start()"):]
    assert "api.meta().catch(e => { why = e.message; return null; })" in start
    assert start.index("if (!meta) S.stall.set('version'") < start.index("route();")


def test_a_stalled_count_offers_try_again_and_send_never_looks_empty():
    """Frame 1, running 2: a Questions read held on another tab marks the counts stalled; Send reads "…" then "?"."""
    rc = FRAME[FRAME.index("async function readCounts(again)"):FRAME.index("const putCounts")]
    assert "if (!S.countsIn) { S.stall.set('counts', e.message); drawStall(); paintSend(); }" in rc
    assert "S.countsIn = true; if (S.stall.delete('counts')) drawStall();" in FRAME
    assert "const sendSt = () => !sendable() || S.countsIn || (S.warm && !S.stall.has('counts')) ? '' : S.stall.has('counts') ? '?' : '…';" in FRAME
    assert "data-stallagain" in FRAME and "if (d.stallagain !== undefined) { again(); return; }" in FRAME
    assert "#p-stall button" in FRAME  # the frame's click handler takes the notice's button
    assert "onclick = () => { again(); route(); }" in FRAME  # a tab's own Try again re-reads the frame's stalled reads too


def test_reload_says_up_to_date_only_once_confirmed():
    """Frame 5: with the copy status unknown, no "Up to date" in the title or the label."""
    rb = FRAME[FRAME.index("function reloadBtn()"):FRAME.index("// the projects, as rows")]
    neutral = rb[rb.index("if (!S.checked)"):rb.index("\n", rb.index("if (!S.checked)"))]
    assert "Up to date" not in neutral
    cn = FRAME[FRAME.index("async function checkNewer()"):FRAME.index("/* ---------- theme")]
    assert "S.checked = m && S.loadedV && m.current === S.loadedV && (cp || !COPY) && !S.copying ? hhmm() : '';" in cn
    assert "if (meta && !COPY) S.checked = hhmm();" in FRAME


def test_remove_then_esc_keeps_its_undo():
    """Frame 2: Questions never drew on this visit, so the Remove's re-read must not draw into nothing."""
    draw = Q[Q.index("async function draw(keepScroll)"):Q.index("function listView()")]
    assert draw.index("if (host) return drawHost();") < draw.index("if (!root || !D) return;") < draw.index("root.innerHTML")


def test_a_late_redraw_keeps_the_answer_field_focused():
    """Frame 3: C focuses the answer; a document or Reference read that redraws afterwards gives it back."""
    draw = Q[Q.index("async function draw(keepScroll)"):Q.index("function listView()")]
    assert "['words', 'replytext'].find(k => fa.dataset[k] != null)" in draw
    assert "if (back && (!document.activeElement || document.activeElement === document.body))" in draw
