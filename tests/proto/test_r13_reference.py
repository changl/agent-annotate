"""Round 13: Reference and Pages & links match the mock (decision rows 2, 7, 8, 9, 12, 14, 19)."""

import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).parents[2] / "src" / "agent_annotate" / "web" / "proto"
REF, REFCSS = (WEB / "reference.js").read_text(), (WEB / "reference.css").read_text()
LINKS, LINKSCSS = (WEB / "links.js").read_text(), (WEB / "links.css").read_text()


def test_changed_is_an_orange_dot_without_mark_all():
    """Row 2: a small orange dot, as the mock; no "Mark all as seen" (not in the mock)."""
    assert 'class="rf-chd" role="img" aria-label="Changed since you last looked"' in REF
    assert ".rf-chd{" in REFCSS and "background:var(--orange)" in REFCSS
    assert "Mark all as seen" not in REF and "data-allseen" not in REF and "rf-new" not in REF


def test_checklist_task_reads_title_id_state():
    """Row 7: the checklist's task reads title · bead id · state, as plans do."""
    crow = REF[REF.index("const crow ="):REF.index("const COL =")]
    assert crow.index("'not on the board')} · <button class=\"pl9 bid9\"") < crow.index("${esc(bead)}</button> · ${esc(b0 ? b0[1]")


def test_proposed_pill_is_orange():
    """Row 8: Proposed is the mock's orange, not the blue of other tags."""
    rule = REFCSS[REFCSS.index(".tab-reference .rf-st.prop{"):].split("}")[0]
    assert "--color-warning" in rule and "--st-waiting" not in rule


def test_removed_text_full_size_and_width():
    """Row 9: removed paragraphs keep full size, and the text runs to the box's edge."""
    assert "<p class=\"small\"><del>" not in REF and ": `<p><del>${esc(A[x.a][0]" in REF
    assert "max-width:110ch" not in REFCSS


def test_document_kinds_are_coloured_badges_and_folders_count_kinds():
    """Row 12: MD/PDF/DOC/XLS badges in colour, Markdown unlike Word; a folder row counts its kinds."""
    assert "md: ['MD', 'Markdown']" in LINKS and "word: ['DOC', 'Word']" in LINKS
    assert ">${DK[k][0]}</span>" in LINKS
    md = LINKSCSS[LINKSCSS.index(".l-dk.k-md{"):].split("}")[0]
    word = LINKSCSS[LINKSCSS.index(".l-dk.k-word{"):].split("}")[0]
    assert md.split("background:")[1] != word.split("background:")[1]
    assert "`${l.filter(f => f.k === k).length} ${DK[k][1]}`).join(', ')" in LINKS


def test_checklist_chips_platform_first_and_blocked_has_a_mark():
    """Row 14: chip groups run Platform, State, Who, Its task; a blocked mark carries the mock's slash."""
    g = REF[REF.index("const G = [["):].split("\n")[0]
    assert g.index("'Platform'") < g.index("'State'") < g.index("'Who'") < g.index("'Its task'")
    assert "c === 'blocked' ? '<svg class=\"pi\" viewBox=\"0 0 16 16\" aria-hidden=\"true\"><path d=\"M4.5 11.5l7-7\"/>" in REF
    assert ".sm9.blocked{background:var(--st-blocked);color:#fff}" in REFCSS


def test_slow_first_read_reads_again_by_itself():
    """Row 19: a first read with no answer in 20 s reads afresh, twice, before the tab shows Try again."""
    assert "for (let n = 0; !D; n++) try { D = await c.data('reference', n > 0); if (n) c.refreshChips();" in REF
    assert "catch (e) { if (n >= 2) throw e;" in REF


RETRY_JS = r"""
const tabs = {}, noop = () => {};
global.window = global; global.addEventListener = noop;
global.document = {addEventListener: noop, querySelector: () => null, activeElement: null};
global.history = {replaceState: noop}; global.location = {hash: '#reference'};
global.Proto = {tab: s => tabs[s.key] = s, queue: noop, notes: {slot: noop, prune: () => null}};
require(process.argv[2]);
const fails = +process.argv[3]; let calls = [];
const ctx = {data: (a, fresh) => { calls.push(!!fresh); return calls.length <= fails ? Promise.reject(new Error('no answer in 20 seconds'))
  : Promise.resolve({plans: [], flows: [], extras: [], topics: [], notes: [], beads: {}}); },
  prefs: {get: (k, d) => d, set: noop}, refreshChips: () => calls.push('chips'), refreshTop: noop};
const main = {innerHTML: '', isConnected: false, classList: {contains: () => false}, addEventListener: noop};
tabs.reference.render(main, ctx, '').then(() => console.log('ok ' + JSON.stringify(calls)), e => console.log('fail ' + JSON.stringify(calls) + ' ' + main.innerHTML));
"""


@pytest.mark.parametrize("fails,want", [(0, "ok [false]"), (2, "ok [false,true,true,\"chips\"]"),(3, "fail [false,true,true] <p class=\"mut\">Still reading Reference…</p>")])
def test_slow_first_read_retry_runs(tmp_path, fails, want):
    """Row 19, run: two slow reads still draw the tab; a third failure goes to the frame's Try again."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    s = tmp_path / "retry.js"
    s.write_text(RETRY_JS)
    r = subprocess.run([node, str(s), str(WEB / "reference.js"), str(fails)], capture_output=True, text=True, timeout=30)
    assert r.stdout.strip() == want, r.stderr


def test_scripts_parse():
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    for f in ("reference.js", "links.js"):
        r = subprocess.run([node, "--check", str(WEB / f)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
