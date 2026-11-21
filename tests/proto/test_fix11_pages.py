"""Ninth check: History point notes in Send, task chips from Running's records, and the Load-test graph's columns."""

from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
HIST, LINKS, LCSS, QS = ((WEB / n).read_text() for n in ("history.js", "links.js", "links.css", "questions.js"))


def test_saved_history_note_is_historys_send_item():
    """Running 1: a saved chart note is listed by History (so Questions does not), Go to it opens History at it, Remove clears the chart."""
    assert "...savedC(ctx).map(n => ({key: 'hcn:' + n.id, group: 'Notes', note: n.id" in HIST
    assert "S.hl = n.id; if (onH()) { draw(HE.el, HE.ctx); litC(HE.el); } else ctx.go('history')" in HIST
    assert "remove: () => takeC(ctx, n)" in HIST and "const keep = ctx.take(n.id, 'api/comments/' + encodeURIComponent(n.id));\n    dropC(n.id);" in HIST
    assert "HE.el.isConnected" in HIST  # a box left behind by another tab is not History on screen


def test_go_to_it_routes_other_tabs_notes_to_their_tab():
    """Running 1: a note Questions lists but another tab owns opens that tab, never Questions."""
    assert "/^chart:/.test(a) ? ['history'] : /^ref:/.test(a) ? ['reference'" in QS
    assert "/^doc:/.test(a) ? ['links'] : null" in QS
    assert "if (own) { host ? drawHost() : draw(true); return ctx.go(...own); }" in QS


def test_task_chip_falls_back_to_runnings_records():
    """Questions 1: a task the Questions board read missed takes its title and state from Running's board records."""
    assert "ctx.data('running').then(r => { RB = ((r || {}).board || {}).beads || {}" in QS
    assert "if (!d.beads[id]) d.beads[id] = {title: b.t || '', status: b.st || '', state: RST[b.st] || 'none'}" in QS
    assert "readRun(); runBeads(d);" in QS


def test_load_test_graph_is_columns_with_a_labelled_horizontal_limit():
    """Reference 3: six columns in one row; the limit a horizontal dashed line labelled at its end; bars still take notes."""
    assert "grid-template-columns:repeat(var(--n),minmax(0,1fr)) auto" in LCSS
    assert "border-top:2px dashed var(--color-error)" in LCSS
    assert 'class="l-glab"' in LINKS and "limit ${c.gate.toLocaleString()} ms" in LINKS
    assert "<i style=\"height:${(v / max * 100).toFixed(1)}%\">" in LINKS and 'data-bnote="${esc(k)}"' in LINKS
