"""Twenty-fourth check: a kept document keeps its pictures, tables and code (r12 audit20 running 1, reference 1 and 2)."""

import json
from pathlib import Path

from test_fix14_frame import node
from test_fix17_media import MEDIA, STUB
from test_fix23_media import png

from agent_annotate.proto_data import links, reference

LNK = (Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto" / "links.js").read_text()
MD = """Intro.

![Wide](wide.png)

Below the picture.

| Step | Pictures |
| --- | --- |
| First | before ![First copy](a.png) between ![Second copy](a.png) after |
| Second | Resolution destination |

```sh
printf released
  printf next
```
"""


# MD as release 2.32.8 publishes it (the auditors' picture-fixture/audit18-release, with this picture and code added)
FIG = '<figure class="aa-figure" data-orient="landscape"><img src="assets/{f}" data-img="7C4C" alt="{a}" width="{w}" height="{h}" loading="lazy" decoding="async"><figcaption>{a}</figcaption></figure>'
HTML = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Kept</title><style>p{{}}</style></head><body>
<div id="canvas-wrapper"><div class="aa"><h1 class="aa-page-title">Kept</h1><section data-anchor-id="s:kept"><h2>Kept</h2>
<p class="lede" data-anchor-id="s:kept:p1">Intro.</p>
{FIG.format(f='1-wide.png', a='Wide', w=1440, h=760).replace('<figure ', '<figure data-anchor-id="fig:wide" ')}
<p data-anchor-id="s:kept:p2">Below the picture.</p>
<table data-anchor-id="tbl:kept"><thead><tr><th>Step</th><th>Pictures</th></tr></thead><tbody><tr data-anchor-id="tbl:kept:row:first"><td>First</td><td>before {FIG.format(f='2-a.png', a='First copy', w=480, h=300)} between {FIG.format(f='2-a.png', a='Second copy', w=480, h=300)} after</td></tr><tr><td>Second</td><td>Resolution destination</td></tr></tbody></table>
<pre data-anchor-id="s:kept:code1"><code>printf released
  printf next</code></pre>
</section></div></div><script>window.x = 1;</script></body></html>"""


def published(tmp_path):
    page = tmp_path / "page"
    (page / "assets").mkdir(parents=True)
    (page / "assets" / "1-wide.png").write_bytes(png(1440, 760))
    (page / "assets" / "2-a.png").write_bytes(png(480, 300))
    return HTML, page


def test_kept_feed_gives_the_markdown_readers_blocks(tmp_path):
    html, page = published(tmp_path)
    b = links.html_blocks(html, links._kept_src("admin-meeting", page))
    pics = [x for x in b if x[0] == "img"]
    assert len(pics) == 1 and pics[0][2:] == ["Wide", 1] and pics[0][1].startswith("proto/kept/admin-meeting/assets/") and pics[0][1].endswith("#wh=1440x760")
    (tbl,) = [x for x in b if x[0] == "tbl"]
    assert tbl[2] == [["Step", "Pictures"], ["First", "before First copy between Second copy after"], ["Second", "Resolution destination"]] and tbl[3] is True
    cell = tbl[4][1][1]
    assert [p[0] for p in cell] == ["t", "img", "t", "img", "t"] and [p[2:] for p in cell if p[0] == "img"] == [["First copy", 2], ["Second copy", 3]]
    assert cell[1][1].endswith("#wh=480x300") and tbl[4][0] == [None, None] and tbl[4][2] == [None, None]
    assert ["pre", "printf released\n  printf next"] in b  # its line breaks and indentation, so Copy copies both lines
    # the same blocks Proto.media.blocks gives the Markdown, but for the pictures' addresses and the page title
    want = [x for x in b if x[0] != "h"]
    node(tmp_path, STUB + MEDIA + f"""
const md = {json.dumps(MD)}, want = {json.dumps(want)};
const addr = x => JSON.parse(JSON.stringify(x, (k, v) => typeof v !== 'string' ? v : /\\.png/.test(v) ? '*' : v.trim()));  // a cell's text parts keep their spaces in Markdown
assert.deepStrictEqual(addr(M.blocks(md)), addr(want));
""")


def test_a_picture_with_no_file_keeps_its_description_and_only_assets_are_served(tmp_path):
    page = tmp_path / "page"
    (page / "assets").mkdir(parents=True)
    (page / "assets" / "x.png").write_bytes(png(4, 4))
    (page / "secret.png").write_bytes(png(4, 4))
    (page / "assets" / "notes.txt").write_text("x")
    src = links._kept_src("usage-audit", page)
    b = links.html_blocks('<body><p>a<br>b</p><img src="assets/gone.png" alt="Gone"><table><tr><td><img src="assets/x.png" alt="X"></td></tr></table>'
                          '<pre>one<br>  two</pre><nav><p>menu</p></nav><script>x()</script></body>', src)
    assert b[:3] == [["p", "a"], ["p", "b"], ["p", "Gone (picture not found)"]]
    assert b[3][4] == [[[["img", "proto/kept/usage-audit/assets/x.png#wh=4x4", "X", 1]]]] and b[4] == ["pre", "one\n  two"] and len(b) == 5
    assert links.kept_picture(page, "assets/x.png") == page / "assets" / "x.png"
    for bad in ("secret.png", "assets/../secret.png", "assets/notes.txt", "assets/.x.png", "assets/missing.png"):
        assert links.kept_picture(page, bad) is None
    assert links.kept_picture(None, "assets/x.png") is None
    # the published page's own addresses: root-relative (the frame check's input) and under its review path
    for a in ("/assets/x.png", "/annotate/reviews/p/assets/x.png", "./assets/x.png?v=1"):
        assert src(a, {"width": "1440", "height": "760"}) == "proto/kept/usage-audit/assets/x.png#wh=1440x760"


def test_kept_meeting_revision_carries_its_pictures(tmp_path, monkeypatch):
    html, page = published(tmp_path)
    (page / "versions").mkdir()
    (page / "versions" / "v1.html").write_text(html)
    (page / "current.meta.json").write_text(json.dumps({"history": [{"version": "v1", "ts": "2026-11-20T00:00:00Z"}]}))
    monkeypatch.setattr(links, "MEETING", page)
    monkeypatch.setattr(links, "USAGE_AUDIT", tmp_path / "missing.html")
    monkeypatch.setattr(links, "LOAD_TEST", tmp_path / "missing")
    (d,) = links.kept()
    assert [x[0] for x in d["blocks"] if x[0] in ("img", "tbl", "pre")] == ["img", "tbl", "pre"]
    assert links._kept_dir("admin-meeting") == page
    # a removed picture or table is named by its words in the revision marks, not its address
    assert "<del>${esc(blockText(R[last - 1].blocks[x.a]))}</del>" in LNK


def test_a_copied_projects_policies_page_reads_through_the_same_reader(tmp_path):
    html, page = published(tmp_path)
    root = tmp_path / "rebex"
    (root / "reviews").mkdir(parents=True)
    page.rename(root / "reviews" / "rebex-policies")
    (root / "reviews" / "rebex-policies" / "current.html").write_text(html)
    meta = {"proto_copy_of": "rebex", "proto_source": str(root / "reviews" / "rebex")}
    (pol,) = [d for d in reference.copied(tmp_path / "copy", meta) if d["id"] == "policies"]
    assert pol["blocks"] == links.html_blocks(html, reference._kept_src("policies", root / "reviews" / "rebex-policies"))
    assert [x[0] for x in pol["blocks"] if x[0] in ("img", "tbl", "pre")] == ["img", "tbl", "pre"]
    assert [p[0] for p in next(x for x in pol["blocks"] if x[0] == "tbl")[4][1][1]] == ["t", "img", "t", "img", "t"]
    # its pictures are served from that page's assets only; a copy never reaches FastLane Drive's kept documents
    assert links._kept_dir("policies", meta) == root / "reviews" / "rebex-policies"
    assert links._kept_dir("admin-meeting", meta) is None and links._kept_dir("policies") is None
