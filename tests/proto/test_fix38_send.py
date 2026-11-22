"""Fix38 Send (r12 audit33 questions 1-2, reference 1): after a round a row's base is what the round delivered, so a later
change, a change back included, is the next Send's; Remove waits out an editor's Save."""

import json
from pathlib import Path

from test_fix13_send import grab, node

WEB = Path(__file__).resolve().parents[2] / "src/agent_annotate/web/proto"
Q = (WEB / "questions.js").read_text()
RUN = (WEB / "running.js").read_text()


def test_a_picture_pick_changed_after_the_check_stays():
    """Questions 1: the round clears a picture pick only if it still picks the side that went."""
    loop = grab(Q, "for (const [a, p] of abs)", "setAB(a, null); }")
    assert "if ((abPicks()[a] || {}).side === p.side) setAB(a, null)" in loop


def test_a_status_changed_back_after_the_check_is_the_next_sends(tmp_path):
    """Questions 2: In progress -> Open is listed and goes; back to In progress after the check stays as a draft, and
    the sent callback makes Open the base, so the next Send lists In progress."""
    sent = grab(RUN, "sent: (ctx, was, done) => {", "redraw(); }")[len("sent: "):]
    js = f"""
const store = {{tst: {{'FLD-1': 'in progress'}}}};
const ctx = {{prefs: {{get: (k, d) => k in store ? JSON.parse(JSON.stringify(store[k])) : d, set: (k, v) => {{ store[k] = v; }}, keys: () => []}}}};
const D = {{board: {{beads: {{'FLD-1': {{st: 'in progress'}}, 'FLD-2': {{st: 'open'}}}}}}}};
const redraw = () => {{}};
const sent = {sent};
const was = new Map([['tst:FLD-1', 'Task FLD-1: set to open']]);
const now = new Map([['tst:FLD-1', 'Task FLD-1: set to in progress']]);
sent(ctx, was, k => was.has(k) && was.get(k) === now.get(k));
if (store.tstsent['FLD-1'] !== 'open') throw new Error('base ' + JSON.stringify(store));
if (store.tst['FLD-1'] !== 'in progress') throw new Error('draft lost ' + JSON.stringify(store));
// an unchanged row is cleared, and its delivered status is the base
store.tst = {{'FLD-2': 'blocked'}};
const w2 = new Map([['tst:FLD-2', 'Task FLD-2: set to blocked']]);
sent(ctx, w2, k => w2.has(k));
if ('FLD-2' in store.tst || store.tstsent['FLD-2'] !== 'blocked') throw new Error('clear ' + JSON.stringify(store));
"""
    node(tmp_path, js)
    # the panel and the Send rows measure from that base
    assert "function tbase(id, b, c = CTX) { return c.prefs.get('tstsent', {})[id] || (b || {}).st; }" in RUN
    assert "if (!D || st !== tbase(id, B[id], ctx)) out.push(" in RUN
    assert "pend = tst[id] !== base ? tst[id] : undefined" in RUN
    # a click back to the base keeps the draft while a round is out, so the round's clear decides
    assert "if (ds.tst === tbase(id, b) && !document.querySelector('.qsend.sending')) delete all[id]" in RUN


def test_remove_waits_out_an_editors_save():
    """Reference 1: while an editor's Save note is out, its typed row offers no Remove, on every editor that keeps the draft."""
    for f, drop in [("reference.js", "draft:rnote"), ("links.js", "draft:lnote"), ("history.js", "draft:hnote")]:
        src = (WEB / f).read_text()
        assert f"remove: SAVING ? null : () => {{ {'ctx' if f != 'links.js' else 'c'}.prefs.set('{drop}', null);" in src, f
        assert src.count("SAVING = true;") == 1 and ".finally(() => { SAVING = false; })" in src, f
    # Questions closes its editor before its save, so no typed row is listed while it is out
    add = grab(Q, "  async function addNote(text) {", "\n  }")
    assert add.index("ctx.prefs.set('q:newnote', null)") < add.index("await call('api/comments'")
