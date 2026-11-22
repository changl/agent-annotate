"""Fix39 Send (r12 audit34 running 1-3, frame 1-5): P.going is the one gate for every control that clears a draft or reverts
a state; an Edit changed back after the cutoff measures from the delivered edit; a status back to its base during Undo is no draft."""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "src/agent_annotate/web/proto"
SRC = {f: (WEB / f).read_text() for f in ("questions.js", "history.js", "links.js", "reference.js", "running.js")}
Q, RUN = SRC["questions.js"], SRC["running.js"]


def test_every_editor_cancel_names_its_send_row_for_the_gate():
    """Running 1, frame 5: every editor Cancel button carries data-going, which the one capture listener checks with
    P.going before any tab's own handler clears the draft."""
    found = 0
    for f, src in SRC.items():
        for m in re.finditer(r"<button[^>]*data-(?:n|c|ned)cancel[^>]*>", src):
            found += 1
            assert "data-going=" in m.group(0), (f, m.group(0))
    assert found == 7, found
    assert ("const g = e.target.closest && e.target.closest('[data-going]');\n"
            "    if (g && P.going(g.dataset.going)) { e.preventDefault(); e.stopImmediatePropagation(); } }, true);") in Q
    # registered before the listener that drops an Edit's typed words, so a refused Cancel keeps them
    assert Q.index("closest('[data-going]')") < Q.index("closest('[data-nedcancel],[data-ccancel]')")
    for f, key in [("questions.js", 'data-going="ty:edit:${esc(n.id)}"'), ("questions.js", 'data-going="n:${n.id}"'),
                   ("questions.js", 'data-going="nn:"'), ("history.js", 'data-going="ty:edit:${id}"'),
                   ("history.js", 'data-going="hnn:${esc(S.cn)}"'), ("links.js", 'data-going="lnn:${esc(k)}"'),
                   ("reference.js", 'data-going="rnn:${esc(k)}"')]:
        assert key in SRC[f], (f, key)


def test_every_other_take_back_calls_the_gate():
    """Frame 1-4 and the Send sheet: re-tap, Undo beside Asked to file, its toast Undo, General feedback Remove, a Re-open's
    toast Undo and Remove of the note being typed all ask P.going first."""
    for pin in [
        "if (was === opt && P.going('q:' + q.id)) return;",
        'data-askfile="${q.id}" data-going="r:${q.id}"',
        "undo: () => { if (P.going('r:' + id)) return; setDraft(id, {reply: was, askWas: null});",
        "if (t.hasAttribute('data-ungen')) { if (P.going('gen')) return;",
        "if (how === 'reopen' && P.going && P.going('reo:' + n.id)) return null;",
        "{ans: 'q:', close: 'c:', reply: 'r:', ab: 'ab:', newnote: 'nn:'}[kind] + id",
    ]:
        assert pin in Q, pin


# Every toast or inert Undo that is no take-back: it puts back what a Remove or Discard took, undoes a note write the round
# already holds back (ROUND), or touches no Send row. Any other Undo must call P.going, or this test fails.
RESTORES = {
    "questions.js": ["put(from", "put(was)", "later(q", "await call(`api/comments/${encodeURIComponent(q.id)}/archive`",
                     "setDraft(q.id, {pick: keep.pick", "delNote(c.id", "ctx.prefs.set('q:drafts', keep)", "setDraft(id, {...meta, pick: keep.pick",
                     "setDraft(id, {...meta, close: true", "setDraft(id, {...meta, reply: keep.reply", "S.note = n; ctx.prefs.set('q:newnote', n)",
                     "setAB(id, p)", "await back(); again();", "ctx.prefs.set('q:general', g)"],
    "reference.js": ["await undo(); draw();", "const g = filed();", "S.reopen.set(fk, t)", "S.cp.set(ck, was); draw(); }); }", "undoNote(c.id)",
                     "keep(); mine = P.putBack", "setUnsort(ids, true)", "setUnsort([p.id], false)"],
    "running.js": ["S.rerun.delete(p)", "CTX.prefs.set(k, old)"],
    "history.js": ["await ctx.api('api/comments/' + encodeURIComponent(c.id), undefined, 'DELETE')"],
    "links.js": ["undoNote(c.id", "save(list.map(", "save(before)"],
}


def test_every_toast_undo_is_gated_or_a_known_restore():
    """Toast Undos (the Asked-to-file toast included) and inert Undos: each calls P.going, or is listed above."""
    for f, src in SRC.items():
        for m in re.finditer(r"undo: (?:async )?\(\) =>|\.inert\(", src):
            body = src[m.end():m.end() + 260]
            if m.group(0) == ".inert(":
                cut = body.split(");")[0]
                if "() =>" not in cut:
                    continue  # a notice with no Undo
                body = body[body.find("() =>"):]
            if "P.going" in body[:120]:
                continue
            assert any(r in body[:120] for r in RESTORES.get(f, [])), (f, src[:m.start()].count("\n") + 1, body[:120])


def test_reference_reason_and_in_flight_remove():
    """Reference 2: emptying a carried reason is refused, and the timeline records the delivered reason. Reference 3: a row
    with a write on its note in flight (Edit save, Post reply) offers no Remove."""
    R = SRC["reference.js"]
    assert "if (!e.target.value.trim() && was.trim() && P.going('ro:' + fk)) { e.target.value = was; return; }" in R
    assert "s = m && /→ reopened: “([\\s\\S]*)”$/.exec(sig || ''); if (s) S.rsent.set(m[1], [t, s[1]]);" in R
    assert "P.inflight = id => [...WRITING.values()]" in Q and "WRITING.set(p, path)" in Q
    assert "NK.rowRm(n) && !P.inflight(n.id) ? 'note:' + n.id" in Q
    assert "x.remove && !P.inflight(x.note || (/^ty:/.test(x.key) ? x.key.replace(/^ty:(edit|reply):/, '') : ''))" in Q


def test_an_edit_changed_after_the_check_measures_from_the_delivered_edit():
    """Running 2: when the open Edit's words changed while the round was out, the draft stays with the delivered edit as its
    base, so typing the earlier wording back is a row for the next Send (tyRows lists text != was)."""
    assert "else if (now && !rep) NK.tySet(k, {...now, was: w});" in Q
    assert "(r.sent && r.text.trim() !== (r.was || '').trim())" in Q


def test_a_status_back_to_its_base_during_undo_is_no_draft():
    """Running 3: only past the round check (P.past) is a pick of the base status kept as a draft."""
    assert "P.past = () => !!CARRY;" in Q
    assert "if (ds.tst === tbase(id, b) && !(P.past && P.past())) delete all[id]; else all[id] = ds.tst;" in RUN
    assert "document.querySelector('.qsend.sending')) delete all[id]" not in RUN
