"""Twenty-third check: Move and View resolution in every picture viewer, one edit box, pictures keep their space (r12 audit19)."""

import struct
import zlib
from pathlib import Path

from test_fix14_frame import grab, node
from test_fix17_media import LNK, MEDIA, QS, REF, STUB

from agent_annotate.proto_data import reference

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
HIS = (WEB / "history.js").read_text()


def png(w, h):
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))


def test_picture_size_rides_on_its_address_and_reserves_its_space(tmp_path):
    node(tmp_path, STUB + MEDIA + """
assert.strictEqual(M.sized('/a.png', 480, 300), '/a.png#wh=480x300');
for (const [s, w, h] of [['/a.png', 0, 300], ['/a.png', NaN, 1], ['data:image/png;base64,x', 4, 4], ['/a.png#wh=1x1', 4, 4], ['', 4, 4]])
  assert.strictEqual(M.sized(s, w, h), s);
assert.strictEqual(M.wh('/a.png#wh=480x300'), ' width="480" height="300"');
assert.strictEqual(M.wh('/a.png'), '');
assert.match(M.fig('/a.png#wh=480x300', 'Cap', 1, 50), /<img src="\\/a.png#wh=480x300" width="480" height="300" alt="Cap"/);
""")
    assert "P.media.sized(u, +e.getAttribute('width'), +e.getAttribute('height'))" in REF  # the published HTML's size is kept
    assert '<img src="${esc(t)}"${P.media.wh(t)}' in REF


def test_feed_puts_each_found_pictures_size_on_its_address(tmp_path):
    (tmp_path / "design").mkdir()
    (tmp_path / "design" / "a.png").write_bytes(png(480, 300))
    (tmp_path / "design" / "bad.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    md = tmp_path / "design" / "p.md"
    out = reference.doc_pictures("![A](a.png)\n![B](bad.png)\n| ![C](a.png) |", md, tmp_path).split("\n")
    assert out == ["![A](proto/doc/design/a.png#wh=480x300)", "![B](proto/doc/design/bad.png)", "| ![C](proto/doc/design/a.png#wh=480x300) |"]
    assert reference.sized("assets/x.png", tmp_path / "none.png") == "assets/x.png"


def test_history_sizes_are_per_version():
    assert "return doc.location.pathname + doc.location.search + '|' + P.media.pk(" in HIS


def test_move_in_every_viewer_repins_and_view_resolution_closes_it():
    zimg = grab(QS, "    if (t.hasAttribute('data-zimg') && S.zoom && S.zoom.anchor)", "return openNote(next, true); }")
    assert "inq: S.zoom.inq};" in zimg and zimg.index("if (S.move) return moveNote(S.move, next);") < zimg.index("S.zoom = null;")
    assert "inq: S.view === 'list' ? ((a.closest('.qcard[data-q]') || {}).dataset || {}).q : undefined" in QS  # Cards only: its card
    assert "tap: tgt => { if (S.move) return moveTo(w, ctx, D, nk, document.querySelector('#p-mview .pic img'), tgt);" in LNK
    assert "goRes: (c, n) => { if (document.getElementById('p-mview')) P.media.closeView();" in QS


def test_remove_or_close_ends_its_move_and_a_tab_ending_move_clears_its_hint(tmp_path):
    slot = grab(QS, "    slot(S, tab, key = 'move') {", "    endMove(redraw = true) {")
    node(tmp_path, f"""
const assert = require('assert');
const toast = {{textContent: 'Tap the new spot · Esc cancels', innerHTML: 'x'}};
global.document = {{getElementById: () => toast, querySelectorAll: () => []}};
const NK = {{mv: null, {slot.replace('    endMove(redraw = true) {', '')}
  endMove() {{ NK.mv = null; }}}};
const S = {{}}; NK.slot(S, 'links');
S.move = 'n1'; assert.deepStrictEqual(NK.mv, {{tab: 'links', id: 'n1'}});
S.move = ''; assert.strictEqual(NK.mv, null); assert.strictEqual(toast.innerHTML, '');
""")
    assert ("closest('[data-ndel],[data-nundo],[data-nclose]');\n    if (b && NK.mv && NK.mv.id === (b.dataset.ndel || b.dataset.nundo || b.dataset.nclose)) NK.endMove(false); }, true);") in QS


def test_one_edit_box_where_he_sees_it():
    assert "const ed = S.edit === n.id && !S.full === !dlg ? n.id : '';" in REF and "noteLine(k, n, dlg)" in REF
    assert REF.count("S.edit === n.id") == 1
    assert "const ed = n => S.edit === n.id && viewing(k) === !!dlg;" in LNK
    box = grab(LNK, "  function noteBox(", "  }\n")
    assert "S.edit === n.id ?" not in box and "ed(n) ? K.editBox(" in box
