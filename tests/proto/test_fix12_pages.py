"""Tenth check: History's saved point note keeps its controls, Pages & links re-reads its list on return,
and Send quotes a note's selected words."""

from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
HIST, HCSS, LINKS, REF = ((WEB / n).read_text() for n in ("history.js", "history.css", "links.js", "reference.js"))


def test_saved_history_note_has_edit_undo_copy_and_link():
    """Running 3: the saved note carries the mock's four controls; Edit opens its own wording; a marked point opens it."""
    for attr in ("data-ccopy", "data-clink"):
        assert f"'{attr}')" in HIST
    # Edit and Remove come from the notes kit's one list, its Remove on History's own handler (r12 audit19)
    assert "K.acts(ctx, x, S.cmove === x.id, '', 'cdel')" in HIST and "if (ds.cned || ds.nedit)" in HIST
    # its own wording, or the words typed before a reload (r12 fix36)
    assert '<textarea id="h-et" rows="3" aria-label="${what}">${esc(typed != null ? typed : x.text)}</textarea>' in HIST
    assert "P.notes.fix(ctx, n, text, ctx.api," in HIST
    assert "if (cnotes(v).length) { S.cn = ''; S.cspot = S.cspot === v ? '' : v;" in HIST  # a marked point lists its notes (fix18)
    assert "'#history/hn-' + ds.clink" in HIST and "if (/^hn-/.test(anchor || ''))" in HIST


def test_history_note_sits_beside_the_strip_at_desk_widths():
    """Running 3: at desk widths the note is a flex item beside the strip; on a phone it takes the full width."""
    assert ".h-cnotes{flex:0 1 600px;min-width:280px}" in HCSS
    assert ".h-cnotes{flex:1 1 100%;min-width:0}" in HCSS.split("@media (max-width:600px)")[1]


def test_links_rereads_its_list_on_return():
    """Running 5, audit11 running 4: every return reads links.json fresh behind the list on screen, with no throttle."""
    assert "readAt" not in LINKS
    assert "ctx.data('links', true).then(F =>" in LINKS
    assert "let D = LD = await ctx.data('links');" in LINKS


def test_send_quotes_selected_words():
    """Reference 4: a note on selected words is named in Send by those words, not its paragraph."""
    assert "cutq((n.target && n.target.quote) || n.l || 'Reference')" in REF
    assert "cut((n.target && n.target.quote) || n.line || n.l || 'Pages & links', 50)" in LINKS
    assert "cut((d.tgt && d.tgt.quote) || d.line || d.l || 'Pages & links', 50)" in LINKS
