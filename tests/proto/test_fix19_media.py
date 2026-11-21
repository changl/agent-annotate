"""Seventeenth check: a picture is keyed by its document and place, not its file (reference 2, 6), a published plan's
table draws its pictures (reference 5), and a cell picture leaves short words whole (questions 4)."""

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
    assert "M.view(M._v.src, M._v.cap, +b.dataset.mz, M._v.from, M._v.k)" in MEDIA and "if (k) { M.setZoom(k, z);" in MEDIA


def test_reference_finds_the_picture_by_its_key_not_its_file():
    assert "el.querySelector(`[data-pk=\"${CSS.escape(k)}\"] img`)" in REF and "data-zsrc" not in REF
    assert "P.media.setZoom(k, +d.zoom)" in REF and "ctx.prefs.set('ref-zoom'" not in REF
    assert "notesAt(k, true)" in REF and "notesAt(k, dlg)" in REF  # old row-keyed point notes still load in the viewer


def test_published_plan_table_keeps_its_cell_pictures():
    p = grab(REF, "  function parse(html) {", "    return out;\n  }\n")
    assert "const cellParts = c =>" in p and "cp = rs.map(row => [...row.cells].map(cellParts))" in p
    assert "...cp.flat().some(Boolean) ? [cp] : []" in p  # the same block shape Proto.media.blocks gives a Markdown table
    assert "c.querySelector('img')" in p  # a row with only a picture is kept


def test_cell_picture_leaves_short_words_whole():
    rule = ".l-tw{container-type:inline-size}.l-tw th,.l-tw td{min-width:min(6.5em,calc(100cqi / var(--c,1) - 2px))}"
    assert rule in LCSS and 'class="l-tw" style="--c:' in LNK
    assert "@media (min-width:701px){.tab-reference .tblw{container-type" not in RCSS
