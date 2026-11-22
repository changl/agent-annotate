"""Seventeenth check: a picture is keyed by its document and place, not its file (reference 2, 6), a published plan's
table draws its pictures (reference 5), and a cell picture leaves short words whole (questions 4)."""

import re
from pathlib import Path

from test_fix14_frame import grab, node
from test_fix17_media import LNK, MEDIA, REF, STUB

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
LCSS, RCSS = ((WEB / f).read_text() for f in ("links.css", "reference.css"))
ROW = "| Step | Picture |\\n| --- | --- |\\n| First | before ![One](a.png) between ![Two](a.png) after |\\n| Second | ![Three](a.png) |\\n"


def test_two_pictures_of_one_file_in_a_row_get_their_own_keys(tmp_path):
    node(tmp_path, STUB + MEDIA + f"""
const B = M.blocks("{ROW}"), cp = B[0][4], got = [];
M.cell(cp, 1, 1, '', s => s, (p, j) => (got.push([p[2], M.pk('ref:x~0~r1', j)]), ''));
M.cell(cp, 2, 1, '', s => s, (p, j) => (got.push([p[2], M.pk('ref:x~0~r2', j)]), ''));
assert.deepStrictEqual(got, [['One', 'ref:x~0~r1~p1'], ['Two', 'ref:x~0~r1~p2'], ['Three', 'ref:x~0~r2~p1']]);
assert.strictEqual(M.pk('ref:x~3'), 'ref:x~3');  // a picture on its own line: its block's anchor
// a row's first picture still shows the point notes saved on the row before; the second does not
assert.strictEqual(M.was('ref:x~0~r1~p1'), 'ref:x~0~r1');
assert.strictEqual(M.was('ref:x~0~r1~p2'), '');
assert.strictEqual(M.was('ref:x~3'), '');
""")


def test_each_picture_remembers_its_own_size(tmp_path):
    bh = grab(LNK, "  const rowsOf", "+ after; };\n")
    node(tmp_path, STUB + MEDIA + f"""
const store = {{zoomDef: 75}};
P.ctx.prefs = {{get: (k, d) => k in store ? store[k] : d, set: (k, v) => {{ store[k] = v; }}}};
{bh}
docK = 'doc:Audit/Sample.md';
M.setZoom('doc:Audit/Sample.md~0~r1~p2', 100);
assert.strictEqual(M.zoom('doc:Audit/Sample.md~0~r1~p2'), 100);
assert.strictEqual(M.zoom('doc:Audit/Sample.md~0~r1~p1'), 75);  // its neighbour of the same file keeps the default
const t = blockHtml(M.blocks("{ROW}")[0], 0, esc, i => '');
assert.ok(t.includes('data-pk="doc:Audit/Sample.md~0~r1~p1"') && t.includes('data-pk="doc:Audit/Sample.md~0~r1~p2"'));
assert.match(t, /data-zoom="100" data-lzoom data-pk="doc:Audit\\/Sample.md~0~r1~p2" aria-pressed="true"/);
assert.match(t, /data-zoom="75" data-lzoom data-pk="doc:Audit\\/Sample.md~0~r1~p1" aria-pressed="true"/);
""")
    # Pages & links opens Full size at the picture's remembered size, and its viewer remembers the size picked there
    assert "z = +(zb.dataset.zoom || P.media.zoom(k))" in LNK and "P.media.view(im.getAttribute('src'), im.dataset.zcap, z, from, k)" in LNK
    assert "M.view(x.src, x.cap, +b.dataset.mz, x.from, x.k, x.nk)" in MEDIA and "if (k) { M.setZoom(k, z);" in MEDIA


def test_reference_finds_the_picture_by_its_key_not_its_file():
    assert "el.querySelector(`[data-pk=\"${CSS.escape(k)}\"] img`)" in REF and "data-zsrc" not in REF
    assert "P.media.setZoom(k, +d.zoom)" in REF and "ctx.prefs.set('ref-zoom'" not in REF
    assert "notesAt(k, true)" in REF and "notesAt(k, dlg)" in REF  # old row-keyed point notes still load in the viewer


def test_published_plan_table_keeps_its_cell_pictures():
    p = grab(REF, "  function parse(html) {", "    return out;\n  }\n")
    assert "const cellParts = c =>" in p and "cp = rs.map(row => [...row.cells].map(cellParts))" in p
    assert "...cp.flat().some(Boolean) ? [cp] : []" in p  # the same block shape Proto.media.blocks gives a Markdown table
    assert "c.querySelector('img')" in p  # a row with only a picture is kept


QDOC = """<article class="aa"><section data-anchor-id="s:a"><h2>A</h2><table><tr data-anchor-id="r:1"><td>Step</td>
<td><img src="assets/a.png" alt="First copy"> <img src="assets/a.png" alt="Second copy"></td></tr></table>
<figure data-anchor-id="fig:a"><img src="assets/a.png" alt="Third copy"></figure></section></article>"""


def test_questions_keys_each_picture_by_its_place(tmp_path):
    from test_fix16_media import QS, run
    out = run(tmp_path, QDOC, """
ctx.prefs.get = (k, d) => k === 'ref-zoom' ? {'r:1~p2': 25} : k === 'q:zoomPer' ? {'assets/a.png': 50} : d;
const o2 = document.createElement('div'); o2.innerHTML = doc.body.innerHTML; zoomBars(o2);
out.dataset.sizes = [...o2.querySelectorAll('.qzm')].map(q => q.querySelector('[aria-pressed="true"]').textContent).join();
const row = o2.querySelector('[data-anchor-id="r:1"]');
out.dataset.noteimg = [noteImg(row, {pk: 'r:1~p2', image_src: 'assets/a.png'}), noteImg(row, {image_src: 'assets/a.png'})].map(i => i.dataset.pk).join();
""")
    assert re.findall(r'data-zfull="assets/a.png" data-pk="([^"]+)"', out) == ["r:1~p1", "r:1~p2", "fig:a~p1"]
    assert 'data-zcap="Picture 2 · Second copy"' in out
    assert 'data-sizes="75%,25%,75%"' in out  # its own size only; one kept by file no longer reaches every copy (fix20)
    assert 'data-noteimg="r:1~p2,r:1~p1"' in out  # a note saved before keys stays on the first of its file
    assert "pinPk(n) === pk" in QS and "image_src: S.zoom.src, pk: S.zoom.pk" in QS and "M.setZoom(S.zoom.pk, +ds.zoomto)" in QS


def test_cell_picture_leaves_short_words_whole():
    rule = ".l-tw{container-type:inline-size}.l-tw th,.l-tw td{min-width:min(6.5em,calc(100cqi / var(--c,1) - 2px))}"
    assert rule in LCSS and 'class="l-tw" style="--c:' in LNK
    assert "@media (min-width:701px){.tab-reference .tblw{container-type" not in RCSS
