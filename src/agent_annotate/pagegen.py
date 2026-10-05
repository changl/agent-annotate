"""`annotate new` — one markdown file becomes a whole review page.

The baseline this replaces: a bespoke `build.py` written next to every slug dir
(one slug accumulated fifteen of them), a median of six minutes and thirty-one
tool calls before a URL existed, and a separate `cards.json` hand-written for
the decision round. Everything those scripts encoded — the template
placeholders, the anchor grammar, the KPI tiles, the table row keys, the
scroll wrapper, the CSS that must never leak out of `<style>` — is encoded once
here instead, and the input is a markdown file the agent can write in one pass.

The parser is deliberately small and deliberately dependency-free. It reads
line by line, it never backtracks, and the only markdown it knows is the
markdown a review page actually uses: headings, paragraphs, bullet and numbered
lists, pipe tables, fenced code, KPI lines, and a fenced ```cards block that
carries the decision round in the same document as the prose it is about.

Nothing here talks to a server. `--publish` and `--ask` hand off to the real
`cmd_publish` / `cmd_ask` so there is exactly one publish code path.
"""

from __future__ import annotations

import argparse
import datetime
import html
import json
import os
import re
import sys
from pathlib import Path

from .paths import WEB_DIR

# ────────────────────────────────────────────────────────────────────────────
# Stylesheet
#
# One <style>, first thing in the canvas, nothing CSS-shaped anywhere else.
# `publish` runs `node --check` over every inline <script>, and a stray rule
# that lands outside a <style> is the single most common reason a publish stops
# before printing a URL. The lint below refuses to write a page that does it.
# ────────────────────────────────────────────────────────────────────────────
CSS = '<style data-annotate-style="managed">\n' + (WEB_DIR / "content.css").read_text(encoding="utf-8") + "</style>"

E = html.escape

FRONT_MATTER_KEYS = (
    "title", "subtitle", "date", "slug", "legend", "version", "label",
    "full_plan", "other_files_required",
)
_UNSAFE_URL = re.compile(r"^\s*(?:javascript|data|vbscript)\s*:", re.IGNORECASE)


class PageGenError(Exception):
    """A document the generator refuses to turn into a page."""


# ────────────────────────────────────────────────────────────────────────────
# Small helpers
# ────────────────────────────────────────────────────────────────────────────
def slugify(text: str, maxlen: int = 48) -> str:
    """Anchor-safe key. Lowercase, ASCII, hyphen-joined, never empty."""
    s = re.sub(r"[^a-z0-9]+", "-", str(text).strip().lower()).strip("-")
    if len(s) > maxlen:
        s = s[:maxlen].rstrip("-")
    return s or "x"


def clip(text: str, n: int = 64) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def first_sentence(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    m = re.match(r"^(.{3,}?[.!?])(?:\s|$)", text)
    return (m.group(1) if m else text).strip()


_INLINE = re.compile(
    r"`([^`]+)`"                                   # `code`
    r"|\[([^\]]+)\]\(([^)\s]+)\)"                  # [text](url)
    r"|\*\*([^*]+)\*\*"                            # **bold**
    r"|__([^_]+)__"                                # __bold__
    r"|\*([^*]+)\*"                                # *italic*
)


def inline(text: str) -> str:
    """Escape, then re-introduce exactly the five inline forms we support.

    One pass, so a `**literal**` inside a code span stays literal and a stray
    asterisk in prose stays an asterisk.
    """
    out: list[str] = []
    pos = 0
    for m in _INLINE.finditer(text):
        out.append(E(text[pos:m.start()]))
        code, label, url, bold, bold2, italic = m.groups()
        if code is not None:
            out.append(f"<code>{E(code)}</code>")
        elif label is not None:
            href = "#" if _UNSAFE_URL.match(url) else url
            out.append(f'<a href="{E(href, quote=True)}">{E(label)}</a>')
        elif bold is not None or bold2 is not None:
            out.append(f"<strong>{E(bold if bold is not None else bold2)}</strong>")
        else:
            out.append(f"<em>{E(italic)}</em>")
        pos = m.end()
    out.append(E(text[pos:]))
    return "".join(out)


# ────────────────────────────────────────────────────────────────────────────
# Parsing
# ────────────────────────────────────────────────────────────────────────────
def parse_front_matter(text: str) -> tuple[dict, str]:
    """`---` delimited `key: value` header. Absent header is not an error."""
    meta: dict = {}
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or lines[i].strip() != "---":
        return meta, "\n".join(lines)
    i += 1
    start = i
    while i < len(lines) and lines[i].strip() != "---":
        i += 1
    if i >= len(lines):
        raise PageGenError("front matter opened with `---` but never closed")
    for raw in lines[start:i]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if ":" not in raw:
            raise PageGenError(f"front matter line is not `key: value`: {raw.strip()!r}")
        key, _, value = raw.partition(":")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        meta[key.strip().lower()] = value
    return meta, "\n".join(lines[i + 1:])


_FENCE = re.compile(r"^(?:```|~~~)\s*([A-Za-z0-9_+-]*)\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_BULLET = re.compile(r"^[-*+]\s+(.*)$")
_ORDERED = re.compile(r"^\d+[.)]\s+(.*)$")
_KPI = re.compile(r"^kpi:\s*(.*)$", re.IGNORECASE)


def _is_table_sep(line: str) -> bool:
    s = line.strip()
    if not s.startswith("|"):
        return False
    cells = [c.strip() for c in s.strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{1,}:?", c) for c in cells)


def _starts_block(s: str) -> bool:
    return bool(
        _FENCE.match(s) or _HEADING.match(s) or _BULLET.match(s)
        or _ORDERED.match(s) or _KPI.match(s) or s.startswith("|")
    )


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def parse_blocks(body: str) -> list[dict]:
    """Markdown → a flat list of block dicts, in document order."""
    lines = body.split("\n")
    blocks: list[dict] = []
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if not s:
            i += 1
            continue

        fence = _FENCE.match(s)
        if fence:
            lang = fence.group(1).lower()
            buf: list[str] = []
            i += 1
            while i < n and not _FENCE.match(lines[i].strip()):
                buf.append(lines[i])
                i += 1
            if i >= n:
                raise PageGenError(f"fenced block opened with ```{lang} was never closed")
            i += 1
            text = "\n".join(buf)
            blocks.append({"kind": lang, "raw": text} if lang in ("cards", "details", "project")
                          else {"kind": "code", "lang": lang, "text": text})
            continue

        heading = _HEADING.match(s)
        if heading:
            blocks.append({"kind": "heading", "level": len(heading.group(1)),
                           "text": heading.group(2).strip()})
            i += 1
            continue

        if _KPI.match(s):
            tiles = []
            while i < n and _KPI.match(lines[i].strip()):
                tiles.append(_KPI.match(lines[i].strip()).group(1).strip())
                i += 1
            blocks.append({"kind": "kpis", "tiles": tiles})
            continue

        if s.startswith("|") and i + 1 < n and _is_table_sep(lines[i + 1]):
            header = _cells(s)
            rows = []
            i += 2
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_cells(lines[i]))
                i += 1
            blocks.append({"kind": "table", "header": header, "rows": rows})
            continue

        for pattern, ordered in ((_BULLET, False), (_ORDERED, True)):
            m = pattern.match(s)
            if m:
                items = []
                while i < n:
                    hit = pattern.match(lines[i].strip())
                    if not hit:
                        break
                    items.append(hit.group(1).strip())
                    i += 1
                blocks.append({"kind": "list", "ordered": ordered, "items": items})
                break
        else:
            buf = [s]
            i += 1
            while i < n and lines[i].strip() and not _starts_block(lines[i].strip()):
                buf.append(lines[i].strip())
                i += 1
            blocks.append({"kind": "para", "text": " ".join(buf)})
    return blocks


# ────────────────────────────────────────────────────────────────────────────
# Rendering
# ────────────────────────────────────────────────────────────────────────────
class Renderer:
    """Blocks → (canvas HTML, ANCHOR_REGISTRY, normalized cards).

    Anchor grammar, verbatim from SKILL.md §4:

        s:<section>               a `##` heading and everything under it
        s:<section>:<sub>         a `###` heading
        s:<section>:p<n>          the n-th paragraph of that section
        s:<section>:li<n>         the n-th list item of that section
        s:<section>:code<n>       the n-th fenced block of that section
        tbl:<section>             a pipe table
        tbl:<section>:col:<slug>  one column, keyed on its header
        tbl:<section>:row:<slug>  one row, keyed on its first cell
        kpi:<slug>                one KPI tile
        d:<n>                     a decision card that owns its own anchor
    """

    def __init__(self, title: str, skip_cards: bool = False,
                 structural: set[str] | None = None) -> None:
        self.title = title
        self.skip_cards = skip_cards
        # Anchors the prose owns, collected by a first pass. A card may name one
        # (that is how a card is pinned to a table row); it must never mint a
        # second element carrying the same id, and a card that runs before the
        # row it points at must not steal the row's anchor either.
        self.structural: set[str] = structural or set()
        self.registry: dict[str, dict] = {}
        self.cards: list[dict] = []
        self.parts: list[str] = []
        self.used: set[str] = set()
        self.section: str | None = None       # anchor id of the open <section>
        self.section_slug = ""
        self.section_title = ""
        self.sub: str | None = None           # anchor id of the open subsection
        self.counters: dict[str, int] = {}
        self.card_n = 0
        self._open = False

    # ── anchors ────────────────────────────────────────────────────────────
    def _unique(self, base: str) -> str:
        if base not in self.used:
            self.used.add(base)
            return base
        k = 2
        while f"{base}-{k}" in self.used:
            k += 1
        self.used.add(f"{base}-{k}")
        return f"{base}-{k}"

    def reg(self, aid: str, name: str, kind: str, parent: str | None = None,
            grp: str | None = None) -> str:
        entry: dict = {"name": clip(name), "grp": grp if grp is not None else self.section_title}
        if parent:
            entry["parent"] = parent
        if kind:
            entry["kind"] = kind
        self.registry[aid] = entry
        return aid

    def _next(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    @property
    def parent(self) -> str:
        """Nearest enclosing anchor: the subsection if one is open."""
        return self.sub or self.section or ""

    # ── sections ───────────────────────────────────────────────────────────
    def ensure_section(self) -> None:
        if self.section is None:
            # Content before the first `##`. It still needs a section to hang
            # off, but not a second copy of the title: the page header already
            # carries it.
            self.open_section(self.title or "Overview", slug_hint="overview", h2=False)

    def open_section(self, heading: str, slug_hint: str | None = None,
                     h2: bool = True) -> None:
        self.close_section()
        self.section_slug = slug_hint or slugify(heading)
        self.section_title = heading
        self.section = self._unique(f"s:{self.section_slug}")
        # A section's own anchor is its own group: shift-click from a paragraph
        # lands here, and the drawer groups the whole section under its title.
        self.reg(self.section, heading, "section", grp=heading)
        self.sub = None
        head = f"<h2>{inline(heading)}</h2>" if h2 else ""
        self.parts.append(f'<section data-anchor-id="{self.section}">{head}')
        self._open = True

    def close_section(self) -> None:
        if self._open:
            self.parts.append("</section>")
            self._open = False

    def open_sub(self, heading: str) -> None:
        self.ensure_section()
        self.sub = self._unique(f"s:{self.section_slug}:{slugify(heading)}")
        self.reg(self.sub, heading, "section", parent=self.section)
        self.parts.append(f'<h3 data-anchor-id="{self.sub}">{inline(heading)}</h3>')

    # ── blocks ─────────────────────────────────────────────────────────────
    def para(self, text: str) -> None:
        self.ensure_section()
        aid = self._unique(f"s:{self.section_slug}:p{self._next('p:' + self.section_slug)}")
        self.reg(aid, text, "para", parent=self.parent)
        cls = ' class="lede"' if self.counters["p:" + self.section_slug] == 1 else ""
        self.parts.append(f'<p{cls} data-anchor-id="{aid}">{inline(text)}</p>')

    def lst(self, items: list[str], ordered: bool) -> None:
        self.ensure_section()
        tag = "ol" if ordered else "ul"
        rows = []
        for item in items:
            aid = self._unique(
                f"s:{self.section_slug}:li{self._next('li:' + self.section_slug)}")
            self.reg(aid, item, "item", parent=self.parent)
            rows.append(f'<li data-anchor-id="{aid}">{inline(item)}</li>')
        self.parts.append(f"<{tag}>{''.join(rows)}</{tag}>")

    def code(self, text: str, lang: str) -> None:
        self.ensure_section()
        aid = self._unique(
            f"s:{self.section_slug}:code{self._next('code:' + self.section_slug)}")
        self.reg(aid, f"{lang or 'code'} block", "code", parent=self.parent)
        self.parts.append(f'<pre data-anchor-id="{aid}"><code>{E(text)}</code></pre>')

    def details(self, raw: str) -> None:
        self.ensure_section()
        summary, _, body = raw.strip().partition("\n")
        if not summary.strip():
            raise PageGenError("a details fence needs a summary on its first line")
        blocks = parse_blocks(body)
        if any(b["kind"] in ("cards", "project", "details", "heading") for b in blocks):
            raise PageGenError("details holds paragraphs, lists, tables or KPIs; keep headings and cards outside")
        aid = self._unique(f"s:{self.section_slug}:details{self._next('details:' + self.section_slug)}")
        self.reg(aid, summary, "details", parent=self.parent)
        self.parts.append(f'<details class="aa-details" data-anchor-id="{aid}"><summary>{inline(summary)}</summary>')
        prior_sub = self.sub
        self.sub = aid
        for block in blocks:
            self.block(block)
        self.sub = prior_sub
        self.parts.append("</details>")

    def kpis(self, tiles: list[str]) -> None:
        self.ensure_section()
        cells = []
        for tile in tiles:
            fields = [f.strip() for f in tile.split("|")]
            value = fields[0] if fields else ""
            label = fields[1] if len(fields) > 1 else ""
            cls = fields[2].lower() if len(fields) > 2 and fields[2] else ""
            if cls not in ("bad", "warn", "ok", ""):
                raise PageGenError(
                    f"kpi tone must be bad, warn or ok (got {cls!r} in {tile!r})")
            aid = self._unique(f"kpi:{slugify(label or value, 40)}")
            self.reg(aid, f"{value} {label}", "kpi", parent=self.parent)
            cells.append(
                f'<div class="kpi{" " + cls if cls else ""}" data-anchor-id="{aid}">'
                f"<b>{inline(value)}</b><span>{inline(label)}</span></div>")
        self.parts.append(f'<div class="kpis">{"".join(cells)}</div>')

    def table(self, header: list[str], rows: list[list[str]]) -> None:
        self.ensure_section()
        tid = self._unique(f"tbl:{self.section_slug}")
        self.reg(tid, f"{self.section_title} table", "table", parent=self.parent)
        cols = []
        seen_col: dict[str, int] = {}
        for head in header:
            key = slugify(head, 32)
            seen_col[key] = seen_col.get(key, 0) + 1
            if seen_col[key] > 1:
                key = f"{key}-{seen_col[key]}"
            aid = self._unique(f"{tid}:col:{key}")
            self.reg(aid, head, "col", parent=tid)
            cols.append(f'<th data-anchor-id="{aid}">{inline(head)}</th>')
        body = []
        seen_row: dict[str, int] = {}
        for cells in rows:
            key = slugify(cells[0] if cells else "", 40)
            seen_row[key] = seen_row.get(key, 0) + 1
            if seen_row[key] > 1:
                key = f"{key}-{seen_row[key]}"
            aid = self._unique(f"{tid}:row:{key}")
            self.reg(aid, cells[0] if cells else key, "row", parent=tid)
            padded = list(cells) + [""] * (len(header) - len(cells))
            tds = "".join(f"<td>{inline(c)}</td>" for c in padded[: len(header)])
            body.append(f'<tr data-anchor-id="{aid}">{tds}</tr>')
        self.parts.append(
            f'<div class="wrap"><table data-anchor-id="{tid}">'
            f'<thead><tr>{"".join(cols)}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')

    # ── decision cards ─────────────────────────────────────────────────────
    def cards_block(self, raw: str) -> None:
        self.ensure_section()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PageGenError(f"```cards block is not valid JSON: {exc}") from exc
        if isinstance(data, dict):
            data = data.get("cards")
        if not isinstance(data, list) or not data:
            raise PageGenError(
                '```cards block must hold a JSON array of '
                '{anchor_id, text, decision_request} objects')
        rendered = []
        for card in data:
            if not isinstance(card, dict):
                raise PageGenError("each entry in a ```cards block must be an object")
            rendered.append(self._card(card))
        self.parts.append(f'<div class="cards">{"".join(rendered)}</div>')

    def _card(self, card: dict) -> str:
        dr = card.get("decision_request") if isinstance(card.get("decision_request"), dict) else {}
        text = re.sub(r"\s+", " ", (card.get("text") or dr.get("prompt") or "")).strip()
        if not text:
            raise PageGenError("a card has neither `text` nor `decision_request.prompt`")
        self.card_n += 1
        wanted = (card.get("anchor_id") or "").strip()
        bound_to = None
        if not wanted:
            aid = self._unique(f"d:{self.card_n}")
        elif wanted in self.used or wanted in self.structural:
            # The card points at something already on the page (a row, a KPI,
            # a column). Do not mint a second element with that id — a
            # duplicate anchor breaks pin-to-card both ways. Show the card next
            # to the prose and link it to the element it belongs to.
            bound_to, aid = wanted, None
        else:
            aid = wanted
            self.used.add(aid)
        if aid:
            self.reg(aid, first_sentence(text), "decision", parent=self.section)

        normalized = dict(card)
        normalized["anchor_id"] = bound_to or aid
        normalized["text"] = text
        if dr:
            normalized["decision_request"] = dr
        self.cards.append(normalized)

        chips = ""
        if dr.get("impact"):
            chips += f'<span class="chip">impact {E(str(dr["impact"]))}</span>'
        if dr.get("blocking"):
            chips += '<span class="chip blocking">blocking</span>'
        title = first_sentence(text)
        number = card.get("number")
        number_badge = (f'<span class="item-num">#{number}</span>'
                        if isinstance(number, int) and not isinstance(number, bool)
                        and number > 0 else "")
        parts = [f"<h4>{number_badge}{inline(title)}{chips}</h4>"]
        rest = text[len(title):].strip()
        if rest:
            parts.append(f'<p class="ctx">{inline(rest)}</p>')
        if dr.get("context"):
            parts.append(f'<p class="ctx">{inline(str(dr["context"]))}</p>')
        reco = dr.get("recommendation")
        options = dr.get("options") or []
        opts = []
        for opt in options:
            if isinstance(opt, dict):
                oid, label = str(opt.get("id") or ""), str(opt.get("label") or opt.get("id") or "")
                consequence = opt.get("consequence") or ""
            else:
                oid = label = str(opt)
                consequence = (dr.get("consequences") or {}).get(oid, "")
            badge = ' <span class="reco" title="Recommended">rec</span>' if reco and oid == str(reco) else ""
            tail = f" — {inline(str(consequence))}" if consequence else ""
            opts.append(f"<li><b>{inline(label)}</b>{badge}{tail}</li>")
        if opts:
            parts.append(f'<ul class="opts">{"".join(opts)}</ul>')
        elif reco:
            parts.append(f'<p class="ctx"><span class="reco" title="Recommended">rec</span> '
                         f'{inline(str(reco))}</p>')
        if bound_to:
            name = (self.registry.get(bound_to) or {}).get("name", bound_to)
            parts.append(f'<p class="card-ref muted">Anchored to '
                         f'<a href="#{E(bound_to, quote=True)}">{E(str(name))}</a> '
                         f'(<code>{E(bound_to)}</code>)</p>')
        parts.append('<p class="q">Answer it on the card, then press Finish review.</p>')
        attr = f' data-anchor-id="{aid}"' if aid else ""
        cls = "card" if aid else "card card-bound"
        return f'<div class="{cls}"{attr}>{"".join(parts)}</div>'

    # ── drive ──────────────────────────────────────────────────────────────
    def run(self, blocks: list[dict]) -> None:
        self.parts.append('<div class="aa">')
        if self.title:
            self.parts.append(f'<h1 class="aa-page-title">{E(self.title)}</h1>')
        for block in blocks:
            self.block(block)
        self.close_section()
        self.parts.append("</div>")

    def block(self, block: dict) -> None:
        kind = block["kind"]
        if kind == "heading":
            text = block["text"]
            if block["level"] == 1 and text.strip() == (self.title or "").strip():
                return             # run() renders the document title once inside the canvas
            if block["level"] <= 2:
                self.open_section(text)
            else:
                self.open_sub(text)
        elif kind == "para":
            self.para(block["text"])
        elif kind == "list":
            self.lst(block["items"], block["ordered"])
        elif kind == "code":
            self.code(block["text"], block["lang"])
        elif kind == "kpis":
            self.kpis(block["tiles"])
        elif kind == "table":
            self.table(block["header"], block["rows"])
        elif kind == "cards" and not self.skip_cards:
            self.cards_block(block["raw"])
        elif kind == "details":
            self.details(block["raw"])

    @property
    def canvas(self) -> str:
        return CSS + "\n" + "\n".join(self.parts)


def render(meta: dict, blocks: list[dict]) -> tuple[str, dict, list[dict]]:
    """Two passes: one to learn which anchors the prose owns, one to render.

    Without the first pass a card that names `tbl:columns:row:tier` before the
    table is parsed would claim the id, and the row would silently slide to
    `…:tier-2` — the card would point at nothing and the evidence link would
    scroll nowhere.
    """
    title = meta.get("title", "")
    prepass = Renderer(title, skip_cards=True)
    prepass.run(blocks)
    renderer = Renderer(title, structural=set(prepass.used))
    renderer.run(blocks)
    return renderer.canvas, renderer.registry, renderer.cards


# ────────────────────────────────────────────────────────────────────────────
# Lint
# ────────────────────────────────────────────────────────────────────────────
_ANCHOR_ATTR = re.compile(r'data-anchor-id="([^"]*)"')


def lint(canvas: str, registry: dict) -> list[str]:
    """Refuse a page that would publish broken. Returns a list of problems."""
    problems: list[str] = []

    # Nine published versions shipped with CSS outside <style>; the symptom is
    # a rule printed as body text above the content.
    for m in re.finditer(r"</style>", canvas):
        tail = canvas[m.end():]
        stray = tail.split("<", 1)[0]
        if stray.strip():
            problems.append(
                f"text between </style> and the first element: {clip(stray, 80)!r} "
                "— CSS and anything else must live inside the <style> block")

    anchors = _ANCHOR_ATTR.findall(canvas)
    seen: set[str] = set()
    for aid in anchors:
        if aid in seen:
            problems.append(f"duplicate anchor id: {aid!r}")
        seen.add(aid)
    if not anchors:
        problems.append("no anchors — nothing on this page can be commented on")
    for aid in sorted(seen - set(registry)):
        problems.append(f"anchor {aid!r} is rendered but missing from ANCHOR_REGISTRY")
    for aid in sorted(set(registry) - seen):
        problems.append(f"anchor {aid!r} is registered but not rendered")
    return problems


def _is_later_version(version: str) -> bool:
    return bool(re.fullmatch(r"v\d+", version) and int(version[1:]) > 1)


def _round_contract_problems(meta: dict, blocks: list[dict], cards: list[dict],
                             registry: dict, version: str) -> list[str]:
    """Authoring contract for cumulative rounds after v1."""
    if not _is_later_version(version) or "full_plan" not in meta:
        return []
    problems = []
    if str(meta.get("full_plan") or "").strip().lower() != "true":
        problems.append("later versions require front matter `full_plan: true`")
    if not str(meta.get("other_files_required") or "").strip():
        problems.append(
            "later versions require `other_files_required: none` or an explicit file list")

    card_blocks = [i for i, block in enumerate(blocks) if block.get("kind") == "cards"]
    if cards:
        if len(card_blocks) != 1:
            problems.append("later versions require exactly one ```cards block")
        elif card_blocks:
            prior_h2 = next((
                block for block in reversed(blocks[:card_blocks[0]])
                if block.get("kind") == "heading" and block.get("level") <= 2
            ), None)
            if not prior_h2 or slugify(prior_h2.get("text", "")) != "questions-for-chang":
                problems.append(
                    "the ```cards block must be in one final `## Questions for Chang` section")

        seen: set[int] = set()
        previous = 0
        for card in cards:
            number = card.get("number")
            if isinstance(number, bool) or not isinstance(number, int) or number < 1:
                problems.append("every later-version card needs a positive integer `number`")
                continue
            if number in seen:
                problems.append(f"duplicate card number {number}")
            if number <= previous:
                problems.append("card numbers must be strictly increasing")
            seen.add(number)
            previous = number

            expected_anchor = f"d:q{number}"
            if card.get("anchor_id") != expected_anchor:
                problems.append(
                    f"card #{number} must use anchor_id {expected_anchor!r}; "
                    "link plan locations through decision_request.evidence")
            prompt = str((card.get("decision_request") or {}).get("prompt") or "")
            if re.match(r"^\s*(?:Q(?:uestion)?\s*\d+|#\s*\d+)", prompt, re.IGNORECASE):
                problems.append(
                    f"card #{number} prompt repeats a number; the `number` badge is canonical")
            evidence = (card.get("decision_request") or {}).get("evidence")
            if not isinstance(evidence, list) or not evidence:
                problems.append(
                    f"card #{number} needs decision_request.evidence linking to the plan")
            else:
                for item in evidence:
                    anchor = item.get("anchor") if isinstance(item, dict) else None
                    if not anchor or anchor not in registry:
                        problems.append(
                            f"card #{number} evidence anchor {anchor!r} is not on this page")
    return problems


def _full_plan_warnings(slug_dir: Path, version: str, blocks: list[dict]) -> list[str]:
    """Warn when a claimed full plan drops most prior top-level sections."""
    if not _is_later_version(version):
        return []
    try:
        from .cli import _read_meta
        prior_version = _read_meta(slug_dir).get("current")
        prior_path = slug_dir / "source" / f"{prior_version}.md"
        _prior_meta, prior_body = parse_front_matter(prior_path.read_text(encoding="utf-8"))
    except (OSError, AttributeError, TypeError):
        return []
    prior_sections = {
        slugify(block["text"])
        for block in parse_blocks(prior_body)
        if block.get("kind") == "heading" and block.get("level") == 2
        and slugify(block["text"]) != "questions-for-chang"
    }
    current_sections = {
        slugify(block["text"])
        for block in blocks
        if block.get("kind") == "heading" and block.get("level") == 2
        and slugify(block["text"]) != "questions-for-chang"
    }
    if not prior_sections:
        return []
    retained = len(prior_sections & current_sections)
    if retained * 2 >= len(prior_sections):
        return []
    missing = sorted(prior_sections - current_sections)
    return [
        f"full-plan warning: {version} retains {retained}/{len(prior_sections)} "
        f"prior sections; verify renamed/dropped sections: {', '.join(missing)}"
    ]


# ────────────────────────────────────────────────────────────────────────────
# Unchanged sections (v2+)
#
# Every later version is the whole plan, so a reviewer re-reads every section
# that did not move. The generator compares each `##` section with the same
# section of the previous version and marks the unchanged ones; the chrome
# (adapter.js) collapses them behind a one-line "Unchanged since vN" header.
# No author input: the comparison is on the rendered section, so anything that
# changes the HTML — a word, a link target, a table cell — counts as a change.
# ────────────────────────────────────────────────────────────────────────────
_SECTION_RE = re.compile(
    r'<section data-anchor-id="([^"]+)"(?: [a-z-]+="[^"]*")*>(.*?)</section>', re.DOTALL)


def section_bodies(canvas: str) -> dict[str, str]:
    """{section anchor: whitespace-normalized HTML} for every `##` section.

    Generated sections never nest and every piece of text is escaped, so a
    literal `</section>` only ever closes one. The implicit overview (prose
    before the first `##`) has no heading to match on and is left out.
    """
    out: dict[str, str] = {}
    for m in _SECTION_RE.finditer(canvas):
        body = re.sub(r"\s+", " ", m.group(2)).strip()
        if body.startswith("<h2>"):
            out[m.group(1)] = body
    return out


def _previous_sections(slug_dir: Path, version: str, title: str) -> tuple[str, dict] | None:
    """The previous version's sections, from its markdown or its rendered page.

    None when there is nothing trustworthy to compare with: v1, no previous
    version on disk, or a previous page that was not generated from markdown
    (a hand-built page's sections mean nothing to this comparison).
    """
    if not _is_later_version(version):
        return None
    prev = f"v{int(version[1:]) - 1}"
    try:
        source = slug_dir / "source" / f"{prev}.md"
        if source.is_file():
            prev_meta, prev_body = parse_front_matter(source.read_text(encoding="utf-8"))
            prev_meta.setdefault("title", title)
            canvas, _registry, _cards = render(prev_meta, parse_blocks(prev_body))
            return prev, section_bodies(canvas)
        page = slug_dir / "versions" / f"{prev}.html"
        if page.is_file():
            from .extract import ExtractionError, extract_canvas
            try:
                canvas = extract_canvas(page.read_text(encoding="utf-8"))
            except ExtractionError:
                return None
            if '<div class="aa">' not in canvas:
                return None
            return prev, section_bodies(canvas)
    except (OSError, UnicodeDecodeError, PageGenError, ValueError):
        return None
    return None


def mark_unchanged_sections(canvas: str, prev_version: str,
                            prev_sections: dict[str, str]) -> tuple[str, list[str]]:
    """Stamp `data-unchanged-since` on every section identical to the previous one."""
    unchanged = [aid for aid, body in section_bodies(canvas).items()
                 if prev_sections.get(aid) == body]
    for aid in unchanged:
        canvas = canvas.replace(
            f'<section data-anchor-id="{aid}">',
            f'<section data-anchor-id="{aid}" data-unchanged-since="{E(prev_version, quote=True)}">',
            1)
    return canvas, unchanged


def _scope_banner(meta: dict, version: str) -> str:
    if not _is_later_version(version) or str(meta.get("full_plan", "")).lower() != "true":
        return ""
    other = str(meta.get("other_files_required") or "").strip()
    if other.lower() == "none":
        detail = "No other files required"
    else:
        detail = f"Other files required: {other}"
    return (
        '<div class="plan-scope"><strong>Complete plan</strong> · '
        f'{inline(detail)}</div>'
    )


# ────────────────────────────────────────────────────────────────────────────
# Build
# ────────────────────────────────────────────────────────────────────────────
def build_html(meta: dict, canvas: str, registry: dict, version: str) -> str:
    """Fill every `{{NAME}}` in the packaged template. Never one occurrence."""
    template = (WEB_DIR / "template.html").read_text(encoding="utf-8")
    # Escape all '<' so neither script-end tags nor HTML double-escaped
    # script states can alter parsing. JSON decoding restores exact labels.
    registry_js = json.dumps(registry, indent=1, ensure_ascii=False).replace("<", "\\u003c")
    values = {
        "{{TITLE}}": E(meta["title"]),
        "{{SUBTITLE}}": E(meta.get("subtitle", "")),
        "{{DATE}}": E(meta.get("date", "")),
        # DOC_ID is the localStorage key and sits in a JS string literal.
        "{{DOC_ID}}": re.sub(r"[^A-Za-z0-9._:-]", "-", meta["slug"]),
        "{{VERSION}}": version,
        "{{ANCHOR_REGISTRY}}": registry_js,
        "{{LEGEND}}": (f'<div class="muted">{inline(meta["legend"])}</div>'
                       if meta.get("legend") else ""),
    }
    for token, value in values.items():
        template = template.replace(token, value)
    leftover = sorted(set(re.findall(r"\{\{([A-Z_]+)\}\}", template)) - {"CANVAS"})
    if leftover:
        raise PageGenError(f"template placeholders left unfilled: {', '.join(leftover)}")
    # Last, so a `{{TOKEN}}` the author typed in their markdown stays text.
    return template.replace("{{CANVAS}}", canvas)


def render_plan(text: str, plan_id: str, *, title: str | None = None) -> tuple[str, str]:
    """Render an independent Markdown plan without writing Review/page metadata."""
    meta, body = parse_front_matter(text)
    for key in meta:
        if key not in FRONT_MATTER_KEYS:
            raise PageGenError(f"unknown front-matter key {key!r}")
    meta["title"] = title or meta.get("title") or plan_id.replace("-", " ").capitalize()
    meta["slug"] = f"plan:{plan_id}"
    meta.setdefault("date", datetime.date.today().isoformat())
    blocks = parse_blocks(body)
    canvas, registry, _cards = render(meta, blocks)
    problems = lint(canvas, registry)
    if problems:
        raise PageGenError("plan rejected by lint: " + "; ".join(problems))
    # The HTTP plan route supplies the actual version; no Review version is embedded.
    return build_html(meta, canvas, registry, ""), meta["title"]


def generate(source: Path, slug_dir: Path, version: str | None = None,
             label: str | None = None) -> dict:
    """Parse, render, lint and write every file a publishable page needs."""
    text = source.read_text(encoding="utf-8")
    meta, body = parse_front_matter(text)
    for key in meta:
        if key not in FRONT_MATTER_KEYS:
            raise PageGenError(
                f"unknown front-matter key {key!r} — known keys: "
                f"{', '.join(FRONT_MATTER_KEYS)}")
    meta.setdefault("title", slug_dir.name.replace("-", " ").strip().capitalize())
    meta.setdefault("slug", slug_dir.name)
    meta.setdefault("date", datetime.date.today().isoformat())
    meta.setdefault("subtitle", "")
    version = version or meta.get("version") or "v1"
    if not re.fullmatch(r"v\d+", version):
        raise PageGenError(f"version must look like v1, v2, v3 (got {version!r})")
    label = label or meta.get("label") or f"generated from {source.name}"

    blocks = parse_blocks(body)
    project_blocks = [b for b in blocks if b["kind"] == "project"]
    project_data = None
    if project_blocks:
        from .project_state import validate_project
        if len(project_blocks) > 1:
            raise PageGenError("use one project fence for persistent project modules")
        try:
            project_data = validate_project(json.loads(project_blocks[0]["raw"]))
        except ValueError as exc:
            raise PageGenError(f"project fence: {exc}") from exc
    canvas, registry, cards = render(meta, blocks)
    problems = lint(canvas, registry)
    problems += _round_contract_problems(meta, blocks, cards, registry, version)
    if problems:
        raise PageGenError("page rejected by lint:\n  " + "\n  ".join(problems))

    unchanged: list[str] = []
    previous = _previous_sections(slug_dir, version, meta["title"])
    if previous:
        canvas, unchanged = mark_unchanged_sections(canvas, *previous)

    banner = _scope_banner(meta, version)
    if banner:
        canvas = canvas.replace('<div class="aa">', f'<div class="aa">{banner}', 1)
    warnings = _full_plan_warnings(slug_dir, version, blocks) if "full_plan" in meta else []
    from .decision_quality import decision_warnings
    for card in cards:
        warnings += [f"{card['anchor_id']}: {warning}" for warning in decision_warnings(card.get("decision_request") or {})]

    html_out = build_html(meta, canvas, registry, version)
    prior = _write_files(slug_dir, version, label, source, text, html_out, cards)
    if project_data is not None:
        from .project_state import save_project
        save_project(slug_dir, project_data)
    return {
        "slug_dir": slug_dir,
        "slug": slug_dir.name,
        "doc_id": meta["slug"],
        "title": meta["title"],
        "version": version,
        "label": label,
        "anchors": len(registry),
        "cards": len(cards),
        "warnings": warnings,
        "unchanged_sections": unchanged,
        "prior_versions": prior,
        "html": slug_dir / "versions" / f"{version}.html",
        "cards_json": slug_dir / "cards.json",
        "source_copy": slug_dir / "source" / f"{version}.md",
    }


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)          # servers read versions/<vN>.html live


def _write_files(slug_dir: Path, version: str, label: str, source: Path,
                 source_text: str, html_out: str, cards: list[dict]) -> list[str]:
    # Lazy: cli.py imports this module, and the server takes the same lock on
    # current.meta.json that _write_meta_locked does.
    from .cli import _read_meta, _write_meta_locked

    slug_dir.mkdir(parents=True, exist_ok=True)
    existing_meta = _read_meta(slug_dir)
    prior = sorted(h.get("version") for h in (existing_meta.get("history") or [])
                   if isinstance(h, dict) and h.get("version"))
    activate = not prior or existing_meta.get("current") == version

    _atomic_write(slug_dir / "versions" / f"{version}.html", html_out)
    _atomic_write(slug_dir / "source" / f"{version}.md", source_text)
    if cards:
        _atomic_write(slug_dir / "cards.json",
                      json.dumps(cards, indent=2, ensure_ascii=False) + "\n")

    if activate:
        current = slug_dir / "current.html"
        tmp_link = slug_dir / ".current.html.tmp"
        if tmp_link.is_symlink() or tmp_link.exists():
            tmp_link.unlink()
        tmp_link.symlink_to(Path("versions") / f"{version}.html")
        os.replace(tmp_link, current)

        def _mutate(meta: dict) -> None:
            meta["current"] = version
            history = meta.setdefault("history", [])
            for entry in history:
                if isinstance(entry, dict) and entry.get("version") == version:
                    entry["label"] = label
                    return                  # idempotent by version, never appended twice
            history.append({"version": version, "ts": _now_iso(), "label": label})

        _write_meta_locked(slug_dir, _mutate)
    # Reports can have no decision cards, so the server may never write this
    # store before the next publish gate reads it. Initialize valid JSON while
    # leaving any existing feedback (including a damaged store) untouched.
    try:
        with (slug_dir / "comments.json").open("x", encoding="utf-8") as store:
            json.dump({"schema_version": 2, "anchors": {}, "archived": {}}, store)
            store.write("\n")
    except FileExistsError:
        pass
    return [v for v in prior if v != version]


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ────────────────────────────────────────────────────────────────────────────
# The example document
# ────────────────────────────────────────────────────────────────────────────
EXAMPLE = '''---
title: Project workspace
---

## Progress

Build passed. Preview is ready for review.

```project
{"title":"Project","modules":[{"id":"status","title":"Progress","kind":"progress","items":[{"label":"Preview build","status":"done","detail":"Checks passed; preview ready."}]}]}
```

## Feedback

```cards
[{"number":1,"anchor_id":"d:q1","decision_request":{"prompt":"Publish the preview?","context":"Checks passed.","recommendation":"publish","options":[{"id":"publish","label":"Publish","consequence":"Preview becomes public."},{"id":"hold","label":"Hold","consequence":"Keep it private."}],"evidence":[{"label":"Build result","anchor":"s:progress:p1"}]}}]
```
'''

def cmd_new(args) -> int:
    from .cli import _inv

    if getattr(args, "example", False):
        sys.stdout.write(EXAMPLE)
        return 0
    if not args.slug_dir or not args.from_file:
        print("ERROR: `new` needs a <slug-dir> and --from <page.md> "
              "(or --example on its own)", file=sys.stderr)
        return 2

    source = Path(args.from_file).expanduser()
    if not source.is_file():
        print(f"ERROR: markdown source not found: {source}", file=sys.stderr)
        return 2
    slug_dir = Path(args.slug_dir).expanduser().resolve()
    from .cli import _moved_page, _slug_project
    if _moved_page(slug_dir):
        return 2
    args.project, _ = _slug_project(slug_dir, getattr(args, "project", None))
    from .workspace import duplicate_message, duplicate_page, exception_reason
    try:
        reason = exception_reason(args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if not reason:
        duplicate = duplicate_page(slug_dir, getattr(args, "project", None))
        if duplicate:
            print(duplicate_message(duplicate), file=sys.stderr)
            return 2
    try:
        result = generate(source, slug_dir, args.version, args.label)
    except PageGenError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: could not write the page: {exc}", file=sys.stderr)
        return 1

    slug, version = result["slug"], result["version"]
    print(f"  wrote          {result['html']}")
    print(f"  anchors        {result['anchors']}")
    print(f"  cards          {result['cards']}"
          + (f" → {result['cards_json']}" if result["cards"] else ""))
    print(f"  source copy    {result['source_copy']}")
    print(f"  version        {version} ({result['label']})"
          + (f"; earlier: {', '.join(result['prior_versions'])}"
             if result["prior_versions"] else ""))
    for warning in result.get("warnings") or []:
        print(f"  WARN           {warning}")

    new_version = bool(result["prior_versions"])
    rc = 0
    if args.publish:
        if new_version:
            rc = _call_publish_version(slug_dir, version, result["label"], args)
        if rc == 0:
            rc = _call_publish(slug_dir, args)
        if rc != 0:
            return rc
    else:
        print("  next:")
        if new_version:
            print(f"    {_inv()} publish-version {slug_dir} {version} "
                  f"--label {result['label']!r}")
        from shlex import quote
        exception_flag = f" --exception {quote(reason)}" if reason else ""
        print(f"    {_inv()} publish {slug_dir}{exception_flag}")

    if result["cards"]:
        ask_cmd = (f"{_inv()} ask {slug} --from {result['cards_json']} "
                   f"--version {version}")
        if args.ask and args.publish:
            rc = _call_ask(slug, result["cards_json"], version, args)
        elif args.ask:
            print(f"  --ask needs a published page; run:\n    {ask_cmd}")
        else:
            print(f"    {ask_cmd}")
    return rc


def _publish_namespace(slug_dir: Path, args) -> argparse.Namespace:
    return argparse.Namespace(
        slug_dir=str(slug_dir),
        project=getattr(args, "project", None),
        port=getattr(args, "port", None),
        transport=getattr(args, "transport", None),
        hostname=getattr(args, "hostname", None),
        public=getattr(args, "public", False),
        standalone=getattr(args, "standalone", False),
        exception=getattr(args, "exception", None),
        path_prefix=None,
        skip_js_lint=False,
        no_verify=False,
        verify_timeout=45.0,
    )


def _call_publish(slug_dir: Path, args) -> int:
    from .cli import cmd_publish
    return cmd_publish(_publish_namespace(slug_dir, args))


def _call_publish_version(slug_dir: Path, version: str, label: str, args) -> int:
    from .cli import cmd_publish_version
    return cmd_publish_version(argparse.Namespace(
        slug_dir=str(slug_dir), version=version, label=label,
        project=getattr(args, "project", None)))


def _call_ask(slug: str, cards_json: Path, version: str, args) -> int:
    from .cli import cmd_ask
    return cmd_ask(argparse.Namespace(
        slug=slug, from_file=str(cards_json), version=version,
        project=getattr(args, "project", None), author=None, json=False))


def add_parser(sub) -> None:
    """`annotate new` — the one subparser cli.py adds for this module."""
    sp = sub.add_parser(
        "new", help="markdown → a publishable review page (versions/vN.html + cards.json)")
    sp.add_argument("slug_dir", nargs="?", default=None)
    sp.add_argument("--from", dest="from_file", default=None, metavar="page.md",
                    help="the markdown document (front matter + prose + ```cards)")
    sp.add_argument("--version", default=None, help="vN (default: front matter, else v1)")
    sp.add_argument("--label", default=None, help="version label for the rail")
    sp.add_argument("--publish", action="store_true", help="run `publish` on the result")
    sp.add_argument("--ask", action="store_true",
                    help="pose the ```cards round after publishing")
    sp.add_argument("--example", action="store_true",
                    help="print a complete example document and exit")
    sp.add_argument("--project", default=None)
    sp.add_argument("--exception", metavar="REASON", help="explicit reason for a second project page")
    sp.add_argument("--standalone", action="store_true", help="alias for --exception standalone")
    sp.add_argument("--port", type=int, default=None)
    sp.add_argument("--transport", default=None,
                    choices=["funnel", "local", "tailscale", "cloudflare", "cloudflare_tailscale"])
    sp.add_argument("--hostname", default=None)
    sp.add_argument("--public", action="store_true",
                    help="legacy Cloudflare option; Funnel is public by default")
    sp.set_defaults(func=cmd_new)
