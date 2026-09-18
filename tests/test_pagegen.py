"""`annotate new`: the markdown document is the page.

Every assertion here stands in for a hand-written build.py that used to encode
the same rule once per page — the anchor grammar, the table row keys, the KPI
tones, the CSS that must stay inside <style>, and the cards.json that used to
be a second file written by hand.
"""

import json
import subprocess
import sys

import pytest

from agent_annotate import pagegen
from agent_annotate.pagegen import (
    EXAMPLE,
    PageGenError,
    generate,
    inline,
    lint,
    parse_blocks,
    parse_front_matter,
    render,
    slugify,
)


def _doc(body: str, **front) -> str:
    front.setdefault("title", "Doc")
    head = "\n".join(f"{k}: {v}" for k, v in front.items())
    return f"---\n{head}\n---\n\n{body}\n"


def _render(body: str, **front):
    meta, rest = parse_front_matter(_doc(body, **front))
    meta.setdefault("slug", "doc")
    return render(meta, parse_blocks(rest))


def _anchors(canvas: str) -> list[str]:
    return pagegen._ANCHOR_ATTR.findall(canvas)


# ── front matter ────────────────────────────────────────────────────────────
def test_front_matter_parses_known_keys_and_survives_quotes():
    meta, body = parse_front_matter(
        '---\ntitle: "Items model"\nsubtitle: Round 1\nversion: v3\n---\n\nHello\n')
    assert meta == {"title": "Items model", "subtitle": "Round 1", "version": "v3"}
    assert body.strip() == "Hello"


def test_document_without_front_matter_is_still_a_document():
    meta, body = parse_front_matter("Just prose.\n")
    assert meta == {}
    assert body.strip() == "Just prose."


def test_unclosed_front_matter_is_rejected():
    with pytest.raises(PageGenError, match="never closed"):
        parse_front_matter("---\ntitle: x\n\nbody\n")


def test_unknown_front_matter_key_is_rejected(tmp_path):
    src = tmp_path / "page.md"
    src.write_text("---\ntitle: x\nauthor: nobody\n---\n\n## S\n\ntext\n", encoding="utf-8")
    with pytest.raises(PageGenError, match="unknown front-matter key 'author'"):
        generate(src, tmp_path / "slug")


def test_version_must_look_like_a_version(tmp_path):
    src = tmp_path / "page.md"
    src.write_text("---\ntitle: x\n---\n\n## S\n\ntext\n", encoding="utf-8")
    with pytest.raises(PageGenError, match="version must look like"):
        generate(src, tmp_path / "slug", version="round-2")


# ── block parser ────────────────────────────────────────────────────────────
def test_parse_blocks_recognises_every_construct():
    blocks = parse_blocks(
        "# Title\n\npara one\nstill para one\n\n- a\n- b\n\n1. first\n2. second\n\n"
        "kpi: 64% | unanswered | bad\nkpi: 12 | fine | ok\n\n"
        "| H1 | H2 |\n|---|---|\n| a | b |\n\n```sql\nSELECT 1;\n```\n\n"
        "```cards\n[]\n```\n")
    assert [b["kind"] for b in blocks] == [
        "heading", "para", "list", "list", "kpis", "table", "code", "cards"]
    assert blocks[1]["text"] == "para one still para one"
    assert blocks[2]["ordered"] is False and blocks[2]["items"] == ["a", "b"]
    assert blocks[3]["ordered"] is True and blocks[3]["items"] == ["first", "second"]
    assert blocks[4]["tiles"] == ["64% | unanswered | bad", "12 | fine | ok"]
    assert blocks[5]["header"] == ["H1", "H2"] and blocks[5]["rows"] == [["a", "b"]]
    assert blocks[6]["lang"] == "sql" and blocks[6]["text"] == "SELECT 1;"


def test_a_paragraph_never_swallows_the_block_that_follows_it():
    blocks = parse_blocks("some prose\n- a bullet\n")
    assert [b["kind"] for b in blocks] == ["para", "list"]


def test_unclosed_fence_is_rejected():
    with pytest.raises(PageGenError, match="never closed"):
        parse_blocks("```sql\nSELECT 1;\n")


# ── inline ──────────────────────────────────────────────────────────────────
def test_inline_forms_render_and_everything_else_is_escaped():
    out = inline("a `<b>` and **bold** and *it* and [x](https://e.com/a?b=1) <s>")
    assert "<code>&lt;b&gt;</code>" in out
    assert "<strong>bold</strong>" in out
    assert "<em>it</em>" in out
    assert '<a href="https://e.com/a?b=1">x</a>' in out
    assert "&lt;s&gt;" in out
    assert "<s>" not in out


def test_inline_does_not_reformat_inside_a_code_span():
    assert inline("`**not bold**`") == "<code>**not bold**</code>"


def test_inline_refuses_a_javascript_url():
    assert '<a href="#">click</a>' in inline("[click](javascript:alert(1))")


def test_slugify_is_ascii_hyphenated_and_never_empty():
    assert slugify("Out of Scope!") == "out-of-scope"
    assert slugify("   ") == "x"
    assert len(slugify("x" * 200)) <= 48


# ── sections, paragraphs, lists ─────────────────────────────────────────────
def test_headings_open_sections_and_subsections():
    canvas, registry, _ = _render("## Scope\n\ntext\n\n### Out of scope\n\nmore\n")
    assert '<section data-anchor-id="s:scope"><h2>Scope</h2>' in canvas
    assert '<h3 data-anchor-id="s:scope:out-of-scope">Out of scope</h3>' in canvas
    assert registry["s:scope"]["kind"] == "section"
    assert registry["s:scope:out-of-scope"]["parent"] == "s:scope"


def test_h1_equal_to_the_title_is_dropped_and_loose_content_opens_an_overview():
    canvas, registry, _ = _render("# Doc\n\nlede text\n", title="Doc")
    assert "<h2>Doc</h2>" not in canvas
    assert "s:overview:p1" in registry
    assert registry["s:overview:p1"]["parent"] == "s:overview"


def test_paragraphs_and_list_items_number_within_their_section():
    canvas, registry, _ = _render(
        "## One\n\na\n\nb\n\n- x\n- y\n\n## Two\n\nc\n\n1. z\n")
    assert _anchors(canvas) == [
        "s:one", "s:one:p1", "s:one:p2", "s:one:li1", "s:one:li2",
        "s:two", "s:two:p1", "s:two:li1"]
    assert registry["s:two:li1"]["grp"] == "Two"


def test_an_element_under_a_subsection_parents_to_the_subsection():
    _, registry, _ = _render("## Scope\n\na\n\n### Detail\n\nb\n")
    assert registry["s:scope:p1"]["parent"] == "s:scope"
    assert registry["s:scope:p2"]["parent"] == "s:scope:detail"
    # grp stays the section title so the drawer groups the whole section.
    assert registry["s:scope:p2"]["grp"] == "Scope"


def test_two_sections_with_the_same_heading_do_not_collide():
    canvas, _, _ = _render("## Scope\n\na\n\n## Scope\n\nb\n")
    assert "s:scope-2" in _anchors(canvas)


# ── tables ──────────────────────────────────────────────────────────────────
def test_table_registers_columns_and_rows_keyed_on_the_first_cell():
    canvas, registry, _ = _render(
        "## Columns\n\n| Column | Type |\n|---|---|\n| status | text |\n| tier | text |\n")
    assert '<div class="wrap"><table data-anchor-id="tbl:columns">' in canvas
    assert '<th data-anchor-id="tbl:columns:col:column">Column</th>' in canvas
    assert '<tr data-anchor-id="tbl:columns:row:status">' in canvas
    assert registry["tbl:columns:row:tier"]["parent"] == "tbl:columns"
    assert registry["tbl:columns:col:type"]["kind"] == "col"


def test_repeated_row_keys_are_deduped_with_a_numeric_suffix():
    canvas, _, _ = _render(
        "## T\n\n| K | V |\n|---|---|\n| status | a |\n| status | b |\n| status | c |\n")
    anchors = _anchors(canvas)
    assert "tbl:t:row:status" in anchors
    assert "tbl:t:row:status-2" in anchors
    assert "tbl:t:row:status-3" in anchors


def test_a_short_row_is_padded_to_the_header_width():
    canvas, _, _ = _render("## T\n\n| A | B | C |\n|---|---|---|\n| only |\n")
    assert canvas.count("<td>") == 3


def test_two_tables_in_one_section_get_distinct_anchors():
    canvas, _, _ = _render(
        "## T\n\n| A |\n|---|\n| x |\n\ntext\n\n| A |\n|---|\n| y |\n")
    assert "tbl:t" in _anchors(canvas) and "tbl:t-2" in _anchors(canvas)


# ── kpis and code ───────────────────────────────────────────────────────────
def test_consecutive_kpi_lines_become_one_grid_with_tone_classes():
    canvas, registry, _ = _render(
        "## Scorecard\n\nkpi: 64% | of 201 cards unanswered | bad\n"
        "kpi: 6.0 m | median build | warn\nkpi: 147 | tests green | ok\n")
    assert canvas.count('<div class="kpis">') == 1
    assert '<div class="kpi bad" data-anchor-id="kpi:of-201-cards-unanswered">' in canvas
    assert '<div class="kpi warn"' in canvas and '<div class="kpi ok"' in canvas
    assert registry["kpi:of-201-cards-unanswered"]["kind"] == "kpi"
    assert registry["kpi:tests-green"]["parent"] == "s:scorecard"


def test_an_unknown_kpi_tone_is_rejected():
    with pytest.raises(PageGenError, match="kpi tone must be"):
        _render("## S\n\nkpi: 1 | x | purple\n")


def test_fenced_code_passes_through_escaped_inside_pre():
    canvas, registry, _ = _render("## M\n\n```sql\nSELECT '<a>' FROM t;\n```\n")
    assert "<pre data-anchor-id=\"s:m:code1\"><code>SELECT &#x27;&lt;a&gt;&#x27; FROM t;</code></pre>" in canvas
    assert registry["s:m:code1"]["kind"] == "code"


# ── cards ───────────────────────────────────────────────────────────────────
CARDS_DOC = """## Columns

| Column | Type |
|---|---|
| status | text |
| tier | text |

## Decisions

```cards
[
  {"anchor_id": "d:rename",
   "text": "Rename status. Three services read it.",
   "decision_request": {"prompt": "Rename status?", "context": "Ambiguous today.",
     "recommendation": "accept",
     "options": [{"id": "accept", "label": "Rename", "consequence": "A dual-write week."},
                 {"id": "reject", "label": "Keep it"}],
     "impact": "medium", "blocking": true}},
  {"anchor_id": "tbl:columns:row:tier",
   "text": "Catalog owns tier.",
   "decision_request": {"prompt": "Catalog owns tier?", "recommendation": "reject",
     "options": ["accept", "reject"],
     "consequences": {"accept": "Billing reads the API."}}},
  {"text": "Drop the shadow column.",
   "decision_request": {"prompt": "Drop it?"}}
]
```
"""


def test_a_cards_block_renders_visible_cards_and_keeps_the_round_in_cards_json(tmp_path):
    src = tmp_path / "page.md"
    src.write_text(_doc(CARDS_DOC, title="T"), encoding="utf-8")
    slug_dir = tmp_path / "review"
    result = generate(src, slug_dir)

    assert result["cards"] == 3
    cards = json.loads((slug_dir / "cards.json").read_text(encoding="utf-8"))
    assert [c["anchor_id"] for c in cards] == [
        "d:rename", "tbl:columns:row:tier", "d:3"]
    # `ask` reads this file as-is, so the schema must survive untouched.
    assert cards[0]["decision_request"]["options"][0]["consequence"] == "A dual-write week."

    html = (slug_dir / "versions" / "v1.html").read_text(encoding="utf-8")
    assert '<div class="card" data-anchor-id="d:rename">' in html
    assert "<h4>Rename status.<span class=\"chip\">impact medium</span>" in html
    assert '<span class="chip blocking">blocking</span>' in html
    # Recommendation is a badge on the option the author recommends.
    assert '<b>Rename</b> <span class="reco">Recommended</span>' in html
    assert '<b>reject</b> <span class="reco">Recommended</span>' in html


def test_a_card_pinned_to_an_existing_anchor_does_not_mint_a_second_element(tmp_path):
    src = tmp_path / "page.md"
    src.write_text(_doc(CARDS_DOC, title="T"), encoding="utf-8")
    slug_dir = tmp_path / "review"
    generate(src, slug_dir)
    html = (slug_dir / "versions" / "v1.html").read_text(encoding="utf-8")
    assert html.count('data-anchor-id="tbl:columns:row:tier"') == 1
    assert '<div class="card card-bound">' in html
    assert '<a href="#tbl:columns:row:tier">tier</a>' in html


def test_a_card_that_points_forward_still_leaves_the_anchor_to_the_prose():
    body = ("## Decisions\n\n```cards\n"
            '[{"anchor_id": "tbl:columns:row:status", "text": "Later."}]\n```\n\n'
            "## Columns\n\n| Column |\n|---|\n| status |\n")
    canvas, _, cards = _render(body)
    assert _anchors(canvas).count("tbl:columns:row:status") == 1
    assert "tbl:columns:row:status-2" not in _anchors(canvas)
    assert cards[0]["anchor_id"] == "tbl:columns:row:status"


def test_a_card_without_text_or_prompt_is_rejected():
    with pytest.raises(PageGenError, match="neither `text` nor"):
        _render('## D\n\n```cards\n[{"anchor_id": "d:1"}]\n```\n')


def test_a_cards_block_that_is_not_json_is_rejected():
    with pytest.raises(PageGenError, match="not valid JSON"):
        _render("## D\n\n```cards\n{not json}\n```\n")


# ── lint ────────────────────────────────────────────────────────────────────
def test_lint_rejects_text_between_the_stylesheet_and_the_first_element():
    canvas = '<style>.a{color:red}</style>\n.b{color:blue}\n<p data-anchor-id="s:a">x</p>'
    problems = lint(canvas, {"s:a": {"name": "x", "grp": "A"}})
    assert any("text between </style>" in p for p in problems)


def test_lint_rejects_duplicate_anchor_ids():
    canvas = '<style></style><p data-anchor-id="s:a">x</p><p data-anchor-id="s:a">y</p>'
    problems = lint(canvas, {"s:a": {"name": "x", "grp": "A"}})
    assert any("duplicate anchor id: 's:a'" in p for p in problems)


def test_lint_rejects_a_page_with_no_anchors():
    assert any("no anchors" in p for p in lint("<style></style><p>x</p>", {}))


def test_lint_rejects_a_registry_that_disagrees_with_the_page():
    canvas = '<style></style><p data-anchor-id="s:a">x</p>'
    problems = lint(canvas, {"s:b": {"name": "b", "grp": "B"}})
    assert any("rendered but missing from ANCHOR_REGISTRY" in p for p in problems)
    assert any("registered but not rendered" in p for p in problems)


def test_an_empty_document_is_refused_rather_than_published(tmp_path):
    src = tmp_path / "page.md"
    src.write_text("---\ntitle: Empty\n---\n\n", encoding="utf-8")
    with pytest.raises(PageGenError, match="no anchors"):
        generate(src, tmp_path / "slug")


# ── writing ─────────────────────────────────────────────────────────────────
def test_generate_writes_every_file_a_publish_needs(tmp_path):
    src = tmp_path / "page.md"
    src.write_text(EXAMPLE, encoding="utf-8")
    slug_dir = tmp_path / "items-model-review"
    result = generate(src, slug_dir)

    assert (slug_dir / "versions" / "v1.html").is_file()
    assert (slug_dir / "current.html").is_symlink()
    import os
    assert os.readlink(slug_dir / "current.html") == "versions/v1.html"
    assert (slug_dir / "source" / "v1.md").read_text(encoding="utf-8") == EXAMPLE
    assert (slug_dir / "comments.json").exists()
    meta = json.loads((slug_dir / "current.meta.json").read_text(encoding="utf-8"))
    assert meta["current"] == "v1"
    assert [h["version"] for h in meta["history"]] == ["v1"]
    assert meta["history"][0]["label"] == "round 1"
    assert result["prior_versions"] == []


def test_rerunning_the_same_version_is_idempotent(tmp_path):
    src = tmp_path / "page.md"
    src.write_text(EXAMPLE, encoding="utf-8")
    slug_dir = tmp_path / "items-model-review"
    first = generate(src, slug_dir)
    before = (slug_dir / "versions" / "v1.html").read_text(encoding="utf-8")
    second = generate(src, slug_dir)
    meta = json.loads((slug_dir / "current.meta.json").read_text(encoding="utf-8"))

    assert [h["version"] for h in meta["history"]] == ["v1"]     # never appended twice
    assert second["anchors"] == first["anchors"]
    assert (slug_dir / "versions" / "v1.html").read_text(encoding="utf-8") == before
    assert second["prior_versions"] == []


def test_a_second_version_keeps_the_first_and_points_current_at_the_new_one(tmp_path):
    src = tmp_path / "page.md"
    src.write_text(EXAMPLE, encoding="utf-8")
    slug_dir = tmp_path / "items-model-review"
    generate(src, slug_dir)
    result = generate(src, slug_dir, version="v2", label="round 2")

    import os
    assert os.readlink(slug_dir / "current.html") == "versions/v2.html"
    assert (slug_dir / "versions" / "v1.html").is_file()
    assert (slug_dir / "source" / "v2.md").is_file()
    meta = json.loads((slug_dir / "current.meta.json").read_text(encoding="utf-8"))
    assert [h["version"] for h in meta["history"]] == ["v1", "v2"]
    assert result["prior_versions"] == ["v1"]


def test_the_template_is_fully_filled_and_the_sentinels_survive(tmp_path):
    src = tmp_path / "page.md"
    src.write_text(EXAMPLE, encoding="utf-8")
    slug_dir = tmp_path / "items-model-review"
    generate(src, slug_dir)
    html = (slug_dir / "versions" / "v1.html").read_text(encoding="utf-8")

    assert "<!-- CANVAS CONTENT — injected by Claude ── -->" in html
    assert "<!-- END CANVAS CONTENT ──────────────────── -->" in html
    assert "{{" not in html.split("<!-- CANVAS CONTENT")[0]
    assert html.count("<title>Items model review</title>") == 1
    assert "Round 1 — column semantics" in html
    assert "const DOC_ID = 'items-model-review';" in html
    # The stylesheet is the first thing in the canvas and the only CSS on it.
    canvas = html.split("<!-- CANVAS CONTENT", 1)[1].split("-->", 1)[1]
    assert canvas.lstrip().startswith("<style>")
    assert canvas.count("<style>") == 1


def test_the_example_document_round_trips_with_more_than_twenty_anchors(tmp_path):
    src = tmp_path / "page.md"
    src.write_text(EXAMPLE, encoding="utf-8")
    slug_dir = tmp_path / "items-model-review"
    result = generate(src, slug_dir)

    assert result["anchors"] > 20
    assert result["cards"] == 3
    html = (slug_dir / "versions" / "v1.html").read_text(encoding="utf-8")
    canvas = html.split("<!-- CANVAS CONTENT", 1)[1].split("END CANVAS CONTENT", 1)[0]
    anchors = pagegen._ANCHOR_ATTR.findall(canvas)
    assert len(anchors) == len(set(anchors))        # uniqueness, end to end
    registry = json.loads(
        html.split("const ANCHOR_REGISTRY = ", 1)[1].split(";\n", 1)[0])
    assert set(registry) == set(anchors)
    assert result["anchors"] == len(anchors)
    for entry in registry.values():
        assert entry["name"] and entry["grp"]


# ── CLI ─────────────────────────────────────────────────────────────────────
def _cli(*argv, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "agent_annotate.cli", *argv],
        capture_output=True, text=True, cwd=cwd,
        env={**__import__("os").environ,
             "PYTHONPATH": str(__import__("pathlib").Path(pagegen.__file__).parents[1])},
    )


def test_new_example_prints_a_document_that_generate_accepts(tmp_path):
    proc = _cli("new", "--example")
    assert proc.returncode == 0, proc.stderr
    src = tmp_path / "page.md"
    src.write_text(proc.stdout, encoding="utf-8")
    assert generate(src, tmp_path / "slug")["anchors"] > 20


def test_new_prints_the_anchor_count_and_the_next_commands(tmp_path):
    src = tmp_path / "page.md"
    src.write_text(EXAMPLE, encoding="utf-8")
    proc = _cli("new", str(tmp_path / "items-model-review"), "--from", str(src))
    assert proc.returncode == 0, proc.stderr
    assert "anchors        3" in proc.stdout
    assert "publish " in proc.stdout
    assert "ask items-model-review --from" in proc.stdout
    assert "--version v1" in proc.stdout


def test_new_without_a_source_explains_itself():
    proc = _cli("new", "/tmp/nowhere")
    assert proc.returncode == 2
    assert "--from" in proc.stderr


def test_new_reports_a_lint_failure_on_stderr_with_a_nonzero_exit(tmp_path):
    src = tmp_path / "page.md"
    src.write_text("---\ntitle: Empty\n---\n", encoding="utf-8")
    proc = _cli("new", str(tmp_path / "slug"), "--from", str(src))
    assert proc.returncode == 1
    assert "no anchors" in proc.stderr
    assert not (tmp_path / "slug" / "versions").exists()
