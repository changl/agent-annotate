"""Fix21 notes (r12 audit18 reference 3, 4, 6; running 2): every surface edits a saved, unsent note in place through the
notes kit; Pages & links Full size takes and shows point notes; one marker colour rule; History's waiting questions wrap
under their question on a phone."""

import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
Q = (WEB / "questions.js").read_text()
QCSS = (WEB / "questions.css").read_text()
REF = (WEB / "reference.js").read_text()
LNK = (WEB / "links.js").read_text()
HIST = (WEB / "history.js").read_text()
HCSS = (WEB / "history.css").read_text()


def grab(src, start, end):
    i = src.index(start)
    return src[i:src.index(end, i) + len(end)]


def node(tmp_path, js):
    exe = shutil.which("node")
    if not exe:
        pytest.skip("node not installed")
    f = tmp_path / "t.js"
    f.write_text(js)
    r = subprocess.run([exe, str(f)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr + r.stdout


KIT = grab(Q, "  const stOf = ", "\n  };")
STUBS = """const assert = require('assert'); const P = {};
const esc = s => String(s), ic = k => '', cut = (s, n) => s, pl = (n, a, b) => n + ' ' + (n === 1 ? a : b);
const mk = n => `[${n}]`, ibw = (k, label, t, attrs) => `<button ${attrs}>${label}</button>`;
const store = {}, calls = [], toasts = [];
const c = {prefs: {get: (k, d) => k in store ? JSON.parse(JSON.stringify(store[k])) : d, set: (k, v) => { store[k] = v; }},
  toast: (m, o) => toasts.push([m, o]), go: (t, a) => calls.push(['go', t, a])};
const api = async (u, body, m) => { calls.push([u, body, m]); return {}; };
"""


def test_edit_changes_the_note_in_place_and_undo_restores_it(tmp_path):
    """Reference 4: Edit opens with the saved words; Save is a PUT on the same id (record, number and time kept); Undo puts the old words back."""
    node(tmp_path, STUBS + KIT + """
(async () => {
  const n = {id: 'n9', text: 'old words', at: 't0'};
  assert(/data-nedit="n9"/.test(NK.draftActs(n)) && /data-nundo="n9"/.test(NK.draftActs(n)) && /Edit/.test(NK.draftActs(n)));
  assert(/<textarea data-nedtext[^>]*>old words<\\/textarea>/.test(NK.editBox(n)) && /data-nedsave="n9"/.test(NK.editBox(n)));
  let seen = '';
  assert(await NK.fix(c, n, '  new words ', api, w => { seen = w; n.text = w; }));
  assert.deepStrictEqual(calls[0], ['api/comments/n9', {text: 'new words'}, 'PUT']);
  assert(seen === 'new words' && n.id === 'n9' && n.at === 't0');
  await toasts[0][1].undo();
  assert.deepStrictEqual(calls[1], ['api/comments/n9', {text: 'old words'}, 'PUT']);
  assert(seen === 'old words');
  assert(!(await NK.fix(c, n, '   ', api, () => {})) && calls.length === 2);  // blank: nothing written
})().catch(e => { console.error(e); process.exit(1); });
""")


def test_one_marker_colour_rule(tmp_path):
    """Reference 6: purple while any note there goes with Send; muted once all are sent or closed, on every surface."""
    node(tmp_path, STUBS + KIT + """
assert(!NK.sent([]) && !NK.sent([{sent: true}, {}]) && NK.sent([{sent: true}, {closed: true}]));
const off = {offset: {dx: .5, dy: .5}}, h = NK.pins([{id: 'a', target: off}, {id: 'b', sent: true, target: off}], '', off);
assert(/class="qpin pinm" data-pin="a"/.test(h) && /class="qpin pinm sent" data-pin="b"/.test(h) && /qpin pinm new/.test(h));
""")
    assert ".qpin.sent,body .pinm.sent,body .rf-pin.sent{background:var(--faint)}" in QCSS
    assert "rf-pin${NK().sent(ns) ? ' sent' : ''}" in REF and "pinm${NK().sent([n]) ? ' sent' : ''}" in REF
    assert "qmk qmkb${K.sent(ns) ? ' sent' : ''}" in LNK
    assert "P.notes.sent(cnotes(v))" in HIST and ".h-cpt.on.sent" in HCSS


def test_every_surface_uses_the_kits_edit():
    """Reference 4: Reference plans, revisions, Copy library and Pages & links all draw the kit's Edit and save through it."""
    for src in (REF, LNK):
        assert "K.draftActs(n, S.move === n.id)" in src and "K.editBox(" in src and ("P.notes.fix(" in src or "NK().fix(" in src)
        assert all(a in src for a in ("nedit", "nedcancel", "nedsave"))


def test_links_full_size_takes_and_shows_point_notes():
    """Reference 3: Full size in Pages & links opens a point composer on a tap and shows saved points; an inline tap keeps its spot."""
    v = grab(Q, "    view(src, cap, z, from, k, nk)", "\n    },")
    assert "nk.tap(NK.pointAt(e, im))" in v and "nk.pins()" in v and "nk.list()" in v
    assert "v.querySelector('[data-nsave]')" in v and "e.stopPropagation(); s.click()" in v  # ⌘↵ saves from the viewer's composer, and opens no Send
    assert ".mview .zn{" in QCSS and "background:var(--color-base-100)" in QCSS[QCSS.index(".mview .zn{"):][:200]
    assert "\n          S.tgt = tgt; S.note = nk;" in LNK and "pins: () => P.notes.pins(notesAt(D, nk, true)" in LNK
    assert "const tgt = P.notes.pointAt(e, im);" in LNK and "S.note = pk;" in LNK  # inline: a point on the picture's own key
    assert "if (S.full) P.media.redrawView();" in LNK
    # a kept revision's picture keeps its size per revision but its notes by place, the key its note line uses
    assert "nk = k.replace(/~rev\\d+(?=~)/, '')" in LNK and "const nk = zb.dataset.nk || k;" in LNK
    assert "querySelector('[data-nk]') || {}).dataset || {}).nk" in LNK and "noteBox(ctx, D, `doc:kept-${d.id}~p~${i}`)" in LNK


def test_history_waiting_questions_wrap_on_a_phone():
    """Running 2: at phone widths a waiting question keeps the line; its version facts go under it."""
    ph = HCSS[HCSS.index("@media (max-width:600px)"):]
    assert ".h-wnl li .small{flex:1 1 100%;white-space:normal}" in ph
