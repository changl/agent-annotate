"""Images and the current-vs-proposed block (decision #16): parsing, orientation, copies."""

import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import pytest

from agent_annotate import pagegen
from agent_annotate.images import image_size, layout_for
from agent_annotate.pagegen import PageGenError, generate, parse_blocks, parse_compare


def png(width: int, height: int, rgb=(200, 210, 230)) -> bytes:
    """A real, decodable solid-colour PNG."""
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    row = b"\x00" + bytes(rgb) * width
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * height)) + chunk(b"IEND", b""))


def write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def page(tmp_path, body: str, name="page.md"):
    src = tmp_path / name
    src.write_text(f"---\ntitle: Shots\n---\n\n{body}\n", encoding="utf-8")
    return src


def canvas_of(slug_dir: Path, version="v1") -> str:
    html = (slug_dir / "versions" / f"{version}.html").read_text(encoding="utf-8")
    return html.split("<!-- CANVAS CONTENT", 1)[1].split("END CANVAS CONTENT", 1)[0]


# ── orientation from headers ────────────────────────────────────────────────
def test_image_size_reads_png_gif_jpeg_and_webp_headers():
    assert image_size(png(390, 844)) == (390, 844)
    assert image_size(b"GIF89a" + struct.pack("<HH", 30, 20) + b"\x00" * 8) == (30, 20)
    jpeg = (b"\xff\xd8" + b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
            + b"\xff\xc0" + struct.pack(">HBHH", 17, 8, 900, 1440) + b"\x00" * 12)
    assert image_size(jpeg) == (1440, 900)
    vp8x = b"RIFF" + b"\x00" * 4 + b"WEBPVP8X" + b"\x00" * 8 + (389).to_bytes(3, "little") + (843).to_bytes(3, "little")
    assert image_size(vp8x) == (390, 844)
    vp8l_bits = (1440 - 1) | ((900 - 1) << 14)
    vp8l = b"RIFF" + b"\x00" * 4 + b"WEBPVP8L" + b"\x00" * 4 + b"\x2f" + vp8l_bits.to_bytes(4, "little") + b"\x00" * 8
    assert image_size(vp8l) == (1440, 900)
    vp8 = (b"RIFF" + b"\x00" * 4 + b"WEBPVP8 " + b"\x00" * 7 + b"\x9d\x01\x2a"
           + struct.pack("<HH", 640, 480) + b"\x00" * 4)
    assert image_size(vp8) == (640, 480)
    assert image_size(b"<html>not an image</html>") is None


def test_layout_is_side_only_when_every_image_is_portrait():
    assert layout_for([(390, 844), (390, 844)]) == "side"
    assert layout_for([(390, 844), (1440, 900)]) == "stack"
    assert layout_for([(1440, 900), (1440, 900)]) == "stack"
    assert layout_for([(500, 500)]) == "stack"
    assert layout_for([None]) == "stack"


# ── parsing ─────────────────────────────────────────────────────────────────
def test_an_image_on_its_own_line_is_a_block_and_ends_a_paragraph():
    blocks = parse_blocks("Intro line\n![Checkout today](shots/a.png)\nAfter")
    assert [b["kind"] for b in blocks] == ["para", "image", "para"]
    assert blocks[1] == {"kind": "image", "caption": "Checkout today", "path": "shots/a.png"}


def test_compare_fence_parses_pairs_title_and_layout():
    title, pairs, layout = parse_compare(
        "title: Sign-in flow\n"
        "current: a1.png | Step 1\nproposed: b1.png | Step 1\n"
        "# a comment\n"
        "current: a2.png\nproposed: b2.png | Step 2\n"
        "layout: stack\n")
    assert title == "Sign-in flow" and layout == "stack"
    assert pairs == [(("a1.png", "Step 1"), ("b1.png", "Step 1")), (("a2.png", ""), ("b2.png", "Step 2"))]
    assert parse_compare("current: a.png\nproposed: b.png\nlayout: auto")[2] is None


@pytest.mark.parametrize("raw, message", [
    ("proposed: b.png", "needs a `current:` line before it"),
    ("current: a.png", "has no `proposed:` line after it"),
    ("current: a.png\ncurrent: c.png\nproposed: b.png", "has no `proposed:` line after it"),
    ("", "at least one"),
    ("before: a.png", "compare line must be"),
    ("current: a.png\nproposed: b.png\nlayout: grid", "layout must be side, stack or auto"),
    ("current: | x\nproposed: b.png", "needs an image path"),
])
def test_compare_fence_refuses_malformed_input(raw, message):
    with pytest.raises(PageGenError, match=message.replace("`", ".").replace("(", ".").replace(")", ".")):
        parse_compare(raw)


# ── build ───────────────────────────────────────────────────────────────────
def test_a_figure_is_copied_into_assets_and_carries_a_stable_anchor(tmp_path):
    shot = write(tmp_path / "shots" / "checkout.png", png(390, 844))
    src = page(tmp_path, "## Status\n\n![Checkout today](shots/checkout.png)")
    slug_dir = tmp_path / "slug"
    result = generate(src, slug_dir)
    canvas = canvas_of(slug_dir)
    copies = list((slug_dir / "assets").iterdir())
    assert len(copies) == 1 and copies[0].read_bytes() == shot.read_bytes()
    assert copies[0].name.endswith("-checkout.png")
    assert (f'<figure class="aa-figure" data-orient="portrait" data-anchor-id="fig:checkout-today">'
            f'<img src="assets/{copies[0].name}" alt="Checkout today" width="390" height="844" loading="lazy" decoding="async">'
            "<figcaption>Checkout today</figcaption></figure>") in canvas
    registry = json.loads((slug_dir / "versions" / "v1.html").read_text()
                          .split("const ANCHOR_REGISTRY = ", 1)[1].split(";\n", 1)[0])
    assert registry["fig:checkout-today"]["kind"] == "figure"
    assert result["anchors"] == len(registry)


def test_an_image_already_in_the_page_assets_is_used_in_place(tmp_path):
    slug_dir = tmp_path / "slug"
    write(slug_dir / "assets" / "wide.png", png(1440, 900))
    src = page(tmp_path, "![](assets/wide.png)")
    generate(src, slug_dir)
    assert sorted(p.name for p in (slug_dir / "assets").iterdir()) == ["wide.png"]
    assert ('data-orient="landscape" data-anchor-id="fig:wide"><img src="assets/wide.png" alt="wide.png"'
            in canvas_of(slug_dir))


@pytest.mark.parametrize("line, message", [
    ("![x](shots/missing.png)", "image not found: shots/missing.png"),
    ("![x](https://example.com/a.png)", "image must be a local file, not a URL"),
    ("![x](notes.txt)", "image must be a .png, .jpg, .gif or .webp file"),
    ("![x](fake.png)", "not a readable PNG, JPEG, GIF or WebP image"),
    ("See ![x](a.png) inline", "put each image on its own line"),
])
def test_bad_images_are_refused_in_one_line_and_nothing_is_written(tmp_path, line, message):
    write(tmp_path / "fake.png", b"<script>alert(1)</script>")
    write(tmp_path / "notes.txt", b"text")
    slug_dir = tmp_path / "slug"
    with pytest.raises(PageGenError) as exc:
        generate(page(tmp_path, line), slug_dir)
    assert message in str(exc.value) and "\n" not in str(exc.value)
    assert not slug_dir.exists()


def test_portrait_pair_renders_side_by_side_and_landscape_pair_stacks(tmp_path):
    write(tmp_path / "p1.png", png(390, 844))
    write(tmp_path / "p2.png", png(390, 844, (120, 180, 120)))
    write(tmp_path / "d1.png", png(1440, 900))
    write(tmp_path / "d2.png", png(1440, 900, (120, 180, 120)))
    src = page(tmp_path, "## Phone\n\n```compare\ncurrent: p1.png | Today\nproposed: p2.png | New\n```\n\n"
                         "## Desktop\n\n```compare\ntitle: Board\ncurrent: d1.png\nproposed: d2.png\n```\n\n"
                         "## Forced\n\n```compare\ncurrent: d1.png\nproposed: d2.png\nlayout: side\n```")
    slug_dir = tmp_path / "slug"
    generate(src, slug_dir)
    canvas = canvas_of(slug_dir)
    assert '<figure class="aa-compare" data-layout="side" data-pairs="1" data-anchor-id="cmp:phone">' in canvas
    assert '<figure class="aa-compare" data-layout="stack" data-pairs="1" data-anchor-id="cmp:board">' in canvas
    assert '<figcaption class="aa-cmp-title">Board</figcaption>' in canvas
    assert 'data-layout="side" data-pairs="1" data-anchor-id="cmp:forced"' in canvas
    phone = canvas.split('data-anchor-id="cmp:phone">', 1)[1].split("</section>", 1)[0]
    assert phone.index('data-role="current">Current</span> Today') < phone.index('data-role="proposed">Proposed</span> New')
    assert 'alt="Current: Today" width="390" height="844" loading="lazy" decoding="async"' in phone
    # Same file twice is copied once; four distinct files, four copies.
    assert len(list((slug_dir / "assets").iterdir())) == 4


def test_a_portrait_flow_renders_a_current_row_and_a_proposed_row(tmp_path):
    lines = []
    for n in (1, 2, 3):
        write(tmp_path / f"a{n}.png", png(390, 844, (200, 200, 20 * n)))
        write(tmp_path / f"b{n}.png", png(390, 844, (20 * n, 200, 200)))
        lines += [f"current: a{n}.png | Step {n}", f"proposed: b{n}.png | Step {n}"]
    src = page(tmp_path, "## Flow\n\n```compare\n" + "\n".join(lines) + "\n```")
    slug_dir = tmp_path / "slug"
    generate(src, slug_dir)
    flow = canvas_of(slug_dir).split('data-anchor-id="cmp:flow">', 1)[1]
    assert 'data-layout="side" data-pairs="3"' in canvas_of(slug_dir)
    rows = flow.split('<div class="aa-cmp-row-head">')[1:]
    assert len(rows) == 2
    assert rows[0].startswith('<span class="aa-cmp-label" data-role="current">Current</span>')
    assert rows[0].count('class="aa-cmp-cell" data-role="current"') == 3
    assert rows[1].count('class="aa-cmp-cell" data-role="proposed"') == 3


def test_a_card_cites_a_compare_block_as_evidence(tmp_path):
    write(tmp_path / "a.png", png(390, 844))
    write(tmp_path / "b.png", png(390, 844))
    cards = [{"anchor_id": "d:q1", "decision_request": {
        "prompt": "Ship it?", "evidence": [{"label": "Pair", "anchor": "cmp:checkout"}]}}]
    src = page(tmp_path, "## Checkout\n\n```compare\ncurrent: a.png\nproposed: b.png\n```\n\n"
                         f"## Questions\n\n```cards\n{json.dumps(cards)}\n```")
    slug_dir = tmp_path / "slug"
    result = generate(src, slug_dir)
    assert result["cards"] == 1
    assert json.loads((slug_dir / "cards.json").read_text())[0]["decision_request"]["evidence"][0]["anchor"] == "cmp:checkout"


def test_a_later_version_with_a_changed_screenshot_is_not_marked_unchanged(tmp_path):
    shot = write(tmp_path / "a.png", png(390, 844))
    src = page(tmp_path, "## Shot\n\n![Home](a.png)\n\n## Text\n\nSame words.")
    slug_dir = tmp_path / "slug"
    generate(src, slug_dir)
    shot.write_bytes(png(390, 844, (10, 10, 10)))       # same path, new picture
    result = generate(src, slug_dir, version="v2")
    assert result["unchanged_sections"] == ["s:text"]
    assert len(list((slug_dir / "assets").iterdir())) == 2


def test_a_plan_copies_its_images_into_the_page(tmp_path):
    write(tmp_path / "plan" / "shot.png", png(1440, 900))
    page_dir = tmp_path / "slug"
    html, title = pagegen.render_plan("## Look\n\n![Board](shot.png)\n", "p1",
                                      base_dir=tmp_path / "plan", page_dir=page_dir)
    name = next((page_dir / "assets").iterdir()).name
    assert f'<img src="assets/{name}" alt="Board" width="1440" height="900">' in html


def test_new_example_shows_a_compare_and_a_card_citing_it(tmp_path):
    proc = subprocess.run([sys.executable, "-m", "agent_annotate.cli", "new", "--example"],
                          capture_output=True, text=True,
                          env={**__import__("os").environ, "PYTHONPATH": str(Path(pagegen.__file__).parents[1])})
    assert proc.returncode == 0, proc.stderr
    assert "```compare" in proc.stdout and '"anchor":"cmp:checkout"' in proc.stdout
