"""Sixteenth check: one Markdown reader draws pictures (frame 4, reference 5, running 2), table rows take their own note
(reference 6), and a caption that says "Picture N" is not numbered twice (running 5)."""

from pathlib import Path

from test_fix14_frame import grab, node
from test_fix17_media import LNK, MEDIA, REF, STUB

from agent_annotate.proto_data import reference

ROOT = Path(__file__).resolve().parents[2]
REFCSS = (ROOT / "src/agent_annotate/web/proto/reference.css").read_text()
FIXTURE = "---\\ntitle: Audit\\n---\\n\\n## Evidence\\n\\nThe first line.\\n\\n![Audit PNG](proto/doc/design/a.png)\\n\\n![Gone]()\\n\\n```sh\\nprintf 'audit fixture\\\\n'\\n```\\n\\n| A | B |\\n| --- | --- |\\n| First | 1 |\\n| Second | 2 |\\n"


def test_one_reader_shared_by_reference_and_links():
    for src in (REF, LNK):
        assert "function mdBlocks" not in src and "const mdBlocks = t => P.media.blocks(t);" in src


def test_reader_draws_pictures_code_and_tables(tmp_path):
    node(tmp_path, STUB + MEDIA + f"""
const B = M.blocks("{FIXTURE}");
assert.deepStrictEqual(B.map(b => b[0]), ['h', 'p', 'img', 'p', 'pre', 'tbl']);
assert.deepStrictEqual(B[2], ['img', 'proto/doc/design/a.png', 'Audit PNG', 1]);
assert.strictEqual(B[3][1], 'Gone (picture not found)');  // the feed found no file: its description stays
assert.strictEqual(B[4][1], "printf 'audit fixture\\\\n'");
assert.deepStrictEqual(B[5][2], [['A', 'B'], ['First', '1'], ['Second', '2']]);
assert.strictEqual(M.title(1, 'Picture 1 — rendered receipt'), 'Picture 1 — rendered receipt');
assert.strictEqual(M.title(2, 'Board'), 'Picture 2 · Board');
assert.strictEqual(M.bare(1, 'Picture 1 — rendered receipt'), 'rendered receipt');
assert.strictEqual(M.bare(1, 'Picture 12 is other'), 'Picture 12 is other');
""")


def test_links_picture_line_and_row_anchors(tmp_path):
    bh = grab(LNK, "  const rowsOf", "+ after; };\n")
    node(tmp_path, STUB + MEDIA + f"""
P.ctx.prefs = {{get: (k, d) => d}};
{bh}
const B = M.blocks("{FIXTURE}"), line = i => `<n:${{i}}>`;
const fig = blockHtml(B[2], 2, esc, line);
assert.match(fig, /<b class="qpicn">Picture 1<\\/b>/);
assert.strictEqual((fig.match(/data-zoom="(25|50|75|100)" data-lzoom/g) || []).length, 4);
assert.match(fig, /<a class="aa-full" href="proto\\/doc\\/design\\/a.png"[^>]* data-lzoom="75">⤢ Full size<\\/a>/);
assert.match(fig, /data-zcap="Picture 1 · Audit PNG"/);
const t = blockHtml(B[5], 5, esc, line);
assert.match(t, /<tr><th>A/);  // the header row notes the whole table
assert.match(t, /<tr data-line="5~r1" tabindex="0"><td>First/);
assert.match(t, /<tr data-line="5~r2" tabindex="0"><td>Second/);
assert.ok(t.includes('<n:5><n:5~r1><n:5~r2>'));  // each row's notes follow the table
assert.strictEqual(blockHtml(['tbl', [['h'], ['x']]], 0, esc).includes('data-line'), false);  // a kept table, read-only
""")


def test_full_size_toolbar_never_covers_the_picture():
    assert ".tab-reference .zoomv .zbar{position:sticky;top:0;" in REFCSS
    assert "padding:52px" not in REFCSS


def test_feed_resolves_pictures_as_the_release_does(tmp_path):
    (tmp_path / "design" / "out" / "assets").mkdir(parents=True)
    (tmp_path / "design" / "out" / "assets" / "a b.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    (tmp_path / "design" / "notes.txt").write_text("x")
    (tmp_path / "secret.png").write_bytes(b"x")
    md = tmp_path / "design" / "out" / "page.md"
    text = "\n".join(["![Ok](assets/a%20b.png)", "![Ok2](assets/a b.png)", "![Web](https://example.com/x.png)", "![Up](../../secret.png)",
                      "![Txt](../notes.txt)", "![Missing](assets/none.png)", "inline ![x](assets/a%20b.png) stays"])
    out = reference.doc_pictures(text, md, tmp_path).split("\n")
    assert out[0] == "![Ok](proto/doc/design/out/assets/a%20b.png)"
    assert out[1] == "![Ok2](assets/a b.png)"  # not a picture line to the release either (a space ends the path)
    assert out[2:6] == ["![Web]()", "![Up]()", "![Txt]()", "![Missing]()"]
    assert out[6] == "inline ![x](assets/a%20b.png) stays"
    assert reference.doc_picture("design/out/assets/a b.png", tmp_path)
    for bad in ("secret.png", "design/../secret.png", "design/notes.txt", "design/.hidden/a.png", ""):
        assert reference.doc_picture(bad, tmp_path) is None


def test_route_serves_only_a_document_picture(tmp_path, monkeypatch):
    from agent_annotate import proto_data
    (tmp_path / "proj" / "design").mkdir(parents=True)
    (tmp_path / "proj" / "design" / "a.png").write_bytes(b"\x89PNG")
    page = tmp_path / "page"
    page.mkdir()
    monkeypatch.setattr(reference, "FLD_DIR", tmp_path / "proj")
    monkeypatch.setattr(reference.doc_picture, "__defaults__", (tmp_path / "proj",))
    got = []

    class H:
        artifact_dir, skill_dir, headers = str(page), None, {}

        def _respond(self, code, body, *a, **k):
            got.append((code, body, a))

    proto_data.serve(H(), "/proto/doc/design/a.png")
    proto_data.serve(H(), "/proto/doc/design/..%2F..%2Fpage%2Fx.png")
    (page / "current.meta.json").write_text('{"proto_copy_of": "x"}')  # another project's copy: no FastLane Drive files
    proto_data.serve(H(), "/proto/doc/design/a.png")
    assert got[0] == (200, b"\x89PNG", ("image/png",))
    assert [g[0] for g in got[1:]] == [404, 404]
