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
lists, pipe tables, fenced code, KPI lines, images, a ```compare block, and a
fenced ```cards block that carries the decision round in the same document as
the prose it is about.

Nothing here talks to a server. `--publish` and `--ask` hand off to the real
`cmd_publish` / `cmd_ask` so there is exactly one publish code path.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import html
import json
import os
import re
import sys
from pathlib import Path

from .images import IMAGE_SUFFIXES, MAX_IMAGE_BYTES, image_size, layout_for
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
            out.append(f'<a href="{E(href, quote=True)}">{E(html.unescape(label))}</a>')
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
        raise PageGenError("front matter opened with `---` but never closed · fix: end it with a `---` line")
    for raw in lines[start:i]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if ":" not in raw:
            raise PageGenError(f"front matter line {raw.strip()!r} is not `key: value` · fix: write `key: value` or remove the line")
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
_IMAGE = re.compile(r"^!\[([^\]]*)\]\(\s*([^)\s]+)\s*\)$")
_INLINE_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def _is_table_sep(line: str) -> bool:
    s = line.strip()
    if not s.startswith("|"):
        return False
    cells = [c.strip() for c in s.strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{1,}:?", c) for c in cells)


def _starts_block(s: str) -> bool:
    return bool(
        _FENCE.match(s) or _HEADING.match(s) or _BULLET.match(s)
        or _ORDERED.match(s) or _KPI.match(s) or _IMAGE.match(s) or s.startswith("|")
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
                raise PageGenError(f"fenced block opened with ```{lang} was never closed · fix: close it with a ``` line")
            i += 1
            text = "\n".join(buf)
            blocks.append({"kind": lang, "raw": text} if lang in ("cards", "ask", "details", "project", "compare")
                          else {"kind": "code", "lang": lang, "text": text})
            continue

        image = _IMAGE.match(s)
        if image:
            blocks.append({"kind": "image", "caption": image.group(1).strip(), "path": image.group(2)})
            i += 1
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
# Plain-text decision cards
#
#     ```ask
#     Use one-step payment?                 prompt; `#19012 Use…` keeps question #19012
#     The receipt remains visible.          context (any plain lines before the options)
#     + One step: Payment and receipt …     the recommended option (at most one `+`)
#     - Keep current: Payment stays …       another option; id = slugify(label)
#     see: cmp:checkout, s:plan             evidence (default: the enclosing section)
#     impact: high                          also blocking: yes, catalog: yes
#     ```
# ────────────────────────────────────────────────────────────────────────────
_ASK_NUMBER = re.compile(r"^#(\d+)\s+(.*\S)$")
_ASK_OPTION = re.compile(r"^([+-])\s+(.*\S)$")
_ASK_KEY = re.compile(r"^(see|impact|blocking|catalog):\s*(.*)$", re.IGNORECASE)
_ASK_YES = {"yes": True, "true": True, "no": False, "false": False}


def parse_ask(raw: str) -> dict:
    """An ```ask fence → today's card dict (`decision_request` and, with `#N`, its number)."""
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    if not lines:
        raise PageGenError("an ask card is empty · fix: put the question on the fence's first line")
    prompt, rest = lines[0], lines[1:]
    card: dict = {"source_kind": "ask"}
    numbered = _ASK_NUMBER.match(prompt)
    if numbered:
        card["number"], prompt = int(numbered.group(1)), numbered.group(2)
        if card["number"] < 1:
            raise PageGenError(f"ask card {prompt!r}: #0 is not a question number · fix: use the number the page shows")
    if _ASK_OPTION.match(prompt) or _ASK_KEY.match(prompt):
        raise PageGenError(f"ask card starts with {prompt!r} · fix: put the question on the fence's first line")
    dr: dict = {"prompt": prompt}
    context, options, recommended, keys = [], [], [], False
    for line in rest:
        option = _ASK_OPTION.match(line)
        key = _ASK_KEY.match(line) if options else None
        if option and not keys:
            # The first colon followed by a space ends the label, so "10:30 start" stays whole.
            split = re.match(r"(.*?):(?:\s+|$)(.*)", option.group(2))
            label, consequence = (split.group(1).strip(), split.group(2)) if split else (option.group(2), "")
            oid = slugify(label)
            if not label:
                raise PageGenError(f"ask card {prompt!r}: an option has no label · fix: write {option.group(1)} Label: consequence")
            if any(o["id"] == oid for o in options):
                raise PageGenError(f"ask card {prompt!r}: two options are named {label!r} · fix: give each option its own label")
            options.append({"id": oid, "label": label, "consequence": consequence.strip()})
            if option.group(1) == "+":
                recommended.append(oid)
        elif key:
            keys = True
            name, value = key.group(1).lower(), key.group(2).strip()
            if name == "see":
                anchors = [a for a in re.split(r"[\s,]+", value) if a]
                if not anchors:
                    raise PageGenError(f"ask card {prompt!r}: see: names no anchor · fix: see: s:<section> or another anchor on this page")
                dr["evidence"] = [{"label": a, "anchor": a} for a in anchors]
            elif name == "impact":
                if value.lower() not in ("low", "medium", "high"):
                    raise PageGenError(f"ask card {prompt!r}: impact {value!r} · fix: impact: low, medium or high")
                dr["impact"] = value.lower()
            elif value.lower() not in _ASK_YES:
                raise PageGenError(f"ask card {prompt!r}: {name} {value!r} · fix: {name}: yes or no")
            else:
                dr[name] = _ASK_YES[value.lower()]
        elif options:
            raise PageGenError(f"ask card {prompt!r}: {clip(line, 60)!r} comes after the options · fix: "
                               "context goes before the options; after them only see:, impact:, blocking:, catalog:")
        else:
            context.append(line)
    if len(recommended) > 1:
        raise PageGenError(f"ask card {prompt!r} recommends {len(recommended)} options · fix: mark one option with +")
    if context:
        dr["context"] = " ".join(context)
    if recommended:
        dr["recommendation"] = recommended[0]
    if options:
        dr["options"] = options
    card["decision_request"] = dr
    return card


class _Regenerate(Exception):
    """Another publish took a reserved number, or the picked version, before the locked write."""


class VersionTaken(PageGenError):
    """The picked version was taken while a merged (`--section`) source was built on the version before it."""


def _taken_numbers(slug_dir: Path, version: str) -> set[int]:
    """Every number the page shows (archived and legacy included) or another draft reserved."""
    from .cli import _item_numbers
    try:
        store = json.loads((slug_dir / "comments.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        store = {}
    taken = {n for n in _item_numbers(store if isinstance(store, dict) else {}).values() if type(n) is int}
    for path in (slug_dir / ".review-drafts").glob("v*.json"):
        if path.stem == version:
            continue  # the draft this generation replaces
        try:
            taken.update(n for n in json.loads(path.read_text(encoding="utf-8")).get("reserved") or [] if type(n) is int)
        except (OSError, ValueError, AttributeError):
            pass
    return taken


def _reserve_numbers(slug_dir: Path, version: str, blocks: list[dict]) -> list[int]:
    """Numbers for the page's unnumbered ask cards: one past everything taken or on this page."""
    explicit, count = set(), 0
    for block in blocks:
        if block["kind"] == "ask":
            number = parse_ask(block["raw"]).get("number")
            if number:
                explicit.add(number)
            else:
                count += 1
        elif block["kind"] == "cards":
            try:
                data = json.loads(block["raw"])
            except ValueError:
                continue  # render names the broken fence
            data = data.get("cards") if isinstance(data, dict) else data
            explicit.update(c["number"] for c in data or [] if isinstance(c, dict) and type(c.get("number")) is int)
    if not count:
        return []
    start = max(_taken_numbers(slug_dir, version) | explicit, default=0) + 1
    return list(range(start, start + count))


def _number_ask_fences(text: str, numbers: list[int]) -> str:
    """Write each allocated number into its fence, so the stored source re-poses the same question."""
    lines, todo, i = text.split("\n"), iter(numbers), 0
    while i < len(lines):
        fence = _FENCE.match(lines[i].strip())
        i += 1
        if not fence:
            continue
        first = None
        while i < len(lines) and not _FENCE.match(lines[i].strip()):
            if fence.group(1).lower() == "ask" and first is None and lines[i].strip():
                first = i
            i += 1
        i += 1
        if first is not None and not _ASK_NUMBER.match(lines[first].strip()):
            indent = lines[first][:len(lines[first]) - len(lines[first].lstrip())]
            lines[first] = f"{indent}#{next(todo)} {lines[first].lstrip()}"
    return "\n".join(lines)


_COMPARE_IMAGE = re.compile(r"^(\s*(?:current|proposed):\s*)([^|\s]+)(.*)$", re.IGNORECASE)


def _image_refs(text: str, refs: dict[str, str]) -> str:
    """Replace image paths (image lines and compare lines) by the page's own copies, so the stored source
    renders again without the author's files."""
    lines, fenced = text.split("\n"), None
    for i, line in enumerate(lines):
        fence = _FENCE.match(line.strip())
        if fence:
            fenced = None if fenced is not None else fence.group(1).lower()
            continue
        image = _IMAGE.match(line.strip()) if fenced is None else None
        if image and image.group(2) in refs:
            at = line.rfind(image.group(2))  # the path, not alt text that repeats it
            lines[i] = line[:at] + refs[image.group(2)] + line[at + len(image.group(2)):]
        pair = _COMPARE_IMAGE.match(line) if fenced == "compare" else None
        if pair and pair.group(2) in refs:
            lines[i] = pair.group(1) + refs[pair.group(2)] + pair.group(3)
    return "\n".join(lines)


_COPY = r'assets/[0-9a-f]{12}-[^"]+'


def _shown_images(slug_dir: Path, base: str, sections: list[tuple[str, str]]) -> dict[str, str]:
    """{image path: page copy} for kept sections of a page whose stored source still names the author's files.

    Each section is matched with its rendered copy in the base version or the archive page that holds
    it; a path maps when exactly one copy in that section carries its file name.
    """
    rendered: dict[str, str] = {}
    for page in [slug_dir / "versions" / f"{base}.html",
                 *sorted((slug_dir / "plans").glob("archive-*/versions/v*.html"), reverse=True)]:
        try:
            for m in _SECTION_RE.finditer(page.read_text(encoding="utf-8")):
                rendered.setdefault(m.group(1), m.group(2))
        except OSError:
            continue
    refs: dict[str, str] = {}
    unclear: set[str] = set()
    for anchor, block in sections:
        html_section = rendered.get(anchor, "")
        copies = {None: set(re.findall(_COPY, html_section))}  # a compare cell also matches on its role
        for role, cell in re.findall(r'<figure class="aa-cmp-cell" data-role="(current|proposed)">(.*?)</figure>',
                                     html_section, re.DOTALL):
            copies.setdefault(role, set()).update(re.findall(_COPY, cell))
        for b in parse_blocks(block):
            paths = [(b["path"], None)] if b["kind"] == "image" else []
            if b["kind"] == "compare":
                paths = [(item[0], role) for pair in parse_compare(b["raw"])[1] for item, role in zip(pair, ROLES)]
            for path, role in paths:
                if path.startswith(("assets/", "attachments/")):
                    continue  # already the page's own copy
                found = {c for c in copies.get(role, copies[None]) if c.endswith("-" + _asset_stem(Path(path).name))}
                copy = found.pop() if len(found) == 1 else None
                if copy is None or refs.setdefault(path, copy) != copy:
                    unclear.add(path)
    return {path: copy for path, copy in refs.items() if path not in unclear}


# ────────────────────────────────────────────────────────────────────────────
# `--section NAME`: replace one `##` block of the newest source
# ────────────────────────────────────────────────────────────────────────────
def _h2_blocks(lines: list[str]) -> list[tuple[int, int, str]]:
    """(first line, line after the block, heading text) for each `##` outside fences."""
    starts, fenced = [], False
    for i, line in enumerate(lines):
        if _FENCE.match(line.strip()):
            fenced = not fenced
            continue
        heading = None if fenced else _HEADING.match(line.strip())
        if heading and len(heading.group(1)) == 2:
            starts.append((i, heading.group(2).strip()))
    ends = [i for i, _ in starts[1:]] + [len(lines)]
    return [(start, end, text) for (start, text), end in zip(starts, ends)]


def _closed_numbers(slug_dir: Path) -> set[int]:
    """Numbers of questions the page holds that are answered or closed (none of their rows is still open)."""
    from .cli import _iter_comments
    from .sync_server import _can_withdraw
    try:
        store = json.loads((slug_dir / "comments.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    seen, open_ = set(), set()
    for _, comment in _iter_comments(store if isinstance(store, dict) else {}, include_archived=True):
        number = comment.get("number")
        if type(number) is int:
            seen.add(number)
            if _can_withdraw(comment):
                open_.add(number)
    return seen - open_


def _keep_open_cards(lines: list[str], closed: set[int]) -> tuple[list[str], list[int]]:
    """Drop answered questions from kept sections; return the lines and the numbers still asked."""
    out, kept, i = [], [], 0
    while i < len(lines):
        fence = _FENCE.match(lines[i].strip())
        if not fence or fence.group(1).lower() not in ("ask", "cards"):
            out.append(lines[i])
            i += 1
            continue
        end = i + 1
        while end < len(lines) and not _FENCE.match(lines[end].strip()):
            end += 1
        inner = lines[i + 1:end]
        if fence.group(1).lower() == "ask":
            number = parse_ask("\n".join(inner)).get("number")
            if number not in closed:
                out += lines[i:end + 1]
                kept += [number] if number else []
        else:
            try:
                data = json.loads("\n".join(inner))
            except ValueError:
                data = None  # left as it is; generation names the broken fence
            cards = data.get("cards") if isinstance(data, dict) else data
            if not isinstance(cards, list):
                out += lines[i:end + 1]
            else:
                still = [c for c in cards if not (isinstance(c, dict) and c.get("number") in closed)]
                kept += [c["number"] for c in still if isinstance(c, dict) and type(c.get("number")) is int]
                if still == cards:
                    out += lines[i:end + 1]
                elif still:
                    out += [lines[i], json.dumps(still, ensure_ascii=False), lines[end] if end < len(lines) else "```"]
        i = end + 1
    return out, kept


def _front_matter(meta: dict) -> str:
    return "---\n" + "".join(f"{key}: {value}\n" for key, value in meta.items()) + "---\n" if meta else ""


def section_source(slug_dir: Path, text: str, name: str) -> dict:
    """The newest source with one `##` block replaced by `text`.

    The base is `source/<current>.md`, or the newest staged draft when it is newer.
    A file without its own `##` keeps the original heading. Other sections keep
    their open questions (carried with the same number) and drop answered ones.
    """
    from .cli import _read_meta
    from .review_versions import draft_path
    current = _read_meta(slug_dir).get("current")
    candidates = [v for v in [current, *(p.stem for p in (slug_dir / ".review-drafts").glob("v*.json"))]
                  if isinstance(v, str) and re.fullmatch(r"v\d+", v) and (slug_dir / "source" / f"{v}.md").is_file()
                  and (v == current or draft_path(slug_dir, v).is_file())]
    if not candidates:
        raise PageGenError("--section needs an earlier version from markdown · fix: publish the whole page with --from first")
    base = max(candidates, key=lambda v: int(v[1:]))
    base_meta, base_body = parse_front_matter((slug_dir / "source" / f"{base}.md").read_text(encoding="utf-8"))
    part_meta, part_body = parse_front_matter(text)
    lines = base_body.split("\n")
    blocks = _h2_blocks(lines)
    used: set[str] = set()
    anchors = []
    for _, _, heading in blocks:  # the renderer's `s:<slug>` anchors, `-2` for a repeated heading
        anchor, k = f"s:{slugify(heading)}", 2
        while anchor in used:
            anchor, k = f"s:{slugify(heading)}-{k}", k + 1
        used.add(anchor)
        anchors.append(anchor)
    hits = [(b, anchor) for b, anchor in zip(blocks, anchors) if name.strip().lower() in (b[2].lower(), anchor)]
    if not hits:
        from difflib import get_close_matches
        names = [b[2] for b in blocks]  # a long page names the closest few, not its 80 headings
        shown = names if len(names) <= 8 else get_close_matches(name, names, n=5, cutoff=0.3) or names[:5]
        more = f" (+{len(names) - len(shown)} more)" if len(names) > len(shown) else ""
        raise PageGenError(f'no section "{name}" on {base} · fix: --section one of '
                           + (", ".join(shown) + more or "none; publish the whole page"))
    if len(hits) > 1:
        raise PageGenError(f'{len(hits)} sections are named "{name}" on {base} · fix: --section one of '
                           + ", ".join(anchor for _, anchor in hits))
    (start, end, heading), _ = hits[0]
    part = part_body.strip("\n").split("\n")
    if not _h2_blocks(part):
        part = [lines[start], ""] + part
    closed = _closed_numbers(slug_dir)
    before, kept_before = _keep_open_cards(lines[:start], closed)
    after, kept_after = _keep_open_cards(lines[end:], closed)
    shown = _shown_images(slug_dir, base, [(anchor, "\n".join(lines[s:e])) for (s, e, _), anchor in zip(blocks, anchors)
                                           if s != start])
    if shown:  # kept sections render from the page's own image copies, not the author's files
        before = _image_refs("\n".join(before), shown).split("\n")
        after = _image_refs("\n".join(after), shown).split("\n")
    meta = {k: v for k, v in base_meta.items() if k not in ("version", "label")}
    meta.update(part_meta)
    body = "\n".join(before + part + [""] + after)
    return {"text": _front_matter(meta) + body, "base": base, "current": current,
            "section": heading, "kept": kept_before + kept_after}


# ────────────────────────────────────────────────────────────────────────────
# Images and the current-vs-proposed block
#
# Decision #16: the reviewer judges pictures inline, without clicking.
# Portrait (phone) shots sit side by side, sized so a pair or a flow row fits
# the viewport height; landscape (desktop) shots stack full width, current
# above proposed. Orientation comes from the file header at build time.
#
#     ![Checkout today](shots/checkout.png)
#
#     ```compare
#     title: Checkout flow            (optional)
#     current: shots/a1.png | Cart
#     proposed: shots/b1.png | Cart
#     current: shots/a2.png | Pay     (several pairs make a flow)
#     proposed: shots/b2.png | Pay
#     layout: side                    (optional: side or stack)
#     ```
# ────────────────────────────────────────────────────────────────────────────
ROLES = {"current": "Current", "proposed": "Proposed"}


def parse_compare(raw: str) -> tuple[str, list[tuple[tuple[str, str], tuple[str, str]]], str | None]:
    """A ```compare fence → (title, [((path, caption), (path, caption))], layout)."""
    title, layout, pairs = "", None, []
    pending: tuple[str, str] | None = None
    for line in raw.split("\n"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        key, sep, value = s.partition(":")
        key, value = key.strip().lower(), value.strip()
        if not sep or key not in ("title", "layout", "current", "proposed"):
            raise PageGenError(f"compare line must be `current:`, `proposed:`, `title:` or `layout:`: {s!r} · fix: start it with one of them")
        if key == "title":
            title = value
        elif key == "layout":
            if value.lower() not in ("side", "stack", "auto"):
                raise PageGenError(f"compare layout must be side, stack or auto (got {value!r}) · fix: layout: side")
            layout = None if value.lower() == "auto" else value.lower()
        else:
            path, _, caption = value.partition("|")
            item = (path.strip(), caption.strip())
            if not item[0]:
                raise PageGenError(f"compare `{key}:` needs an image path: {s!r} · fix: {key}: shots/name.png | Caption")
            if key == "current":
                if pending:
                    raise PageGenError(f"compare `current: {pending[0]}` has no `proposed:` line after it · fix: add `proposed: <image>` after it")
                pending = item
            else:
                if not pending:
                    raise PageGenError(f"compare `proposed: {item[0]}` needs a `current:` line before it · fix: add `current: <image>` before it")
                pairs.append((pending, item))
                pending = None
    if pending:
        raise PageGenError(f"compare `current: {pending[0]}` has no `proposed:` line after it · fix: add `proposed: <image>` after it")
    if not pairs:
        raise PageGenError("a compare fence needs at least one `current:` / `proposed:` pair · fix: add both lines")
    return title, pairs, layout


class ImageStore:
    """Resolves image paths for one build and stages the copies it needs.

    A relative path is read from the markdown's folder first, then (for
    `assets/…` and `attachments/…`) from the page folder. A file outside the
    page is staged under `assets/<content hash>-<name>` and written by
    `copy_into()` only after the page passes lint.
    """

    def __init__(self, base_dir: Path | None, page_dir: Path | None) -> None:
        self.base_dir, self.page_dir = base_dir, page_dir
        self.cache: dict[str, tuple[str, tuple[int, int] | None]] = {}
        self.staged: dict[str, bytes] = {}

    def resolve(self, ref: str) -> tuple[str, tuple[int, int] | None]:
        if ref in self.cache:
            return self.cache[ref]
        if re.match(r"^(?:[A-Za-z][A-Za-z0-9+.-]*:|//)", ref):
            raise PageGenError(f"image must be a local file, not a URL: {ref} · fix: save it and use its local path")
        if Path(ref).suffix.lower() not in IMAGE_SUFFIXES:
            raise PageGenError(f"image must be a .png, .jpg, .gif or .webp file: {ref} · fix: convert it to PNG or JPEG")
        path = Path(ref).expanduser()
        candidates = [path] if path.is_absolute() else []
        if not path.is_absolute() and self.base_dir:
            candidates.append(self.base_dir / path)
        if not path.is_absolute() and self.page_dir and path.parts[0] in ("assets", "attachments"):
            candidates.append(self.page_dir / path)
        found = next((c for c in candidates if c.is_file()), None)
        if found is None:
            raise PageGenError(f"image not found: {ref} · fix: use a path relative to the markdown file")
        if found.stat().st_size > MAX_IMAGE_BYTES:
            raise PageGenError(f"image is over 10 MB: {ref} · fix: shrink it below 10 MB")
        data = found.read_bytes()
        size = image_size(data)
        if size is None:
            raise PageGenError(f"not a readable PNG, JPEG, GIF or WebP image: {ref} · fix: export it again as PNG or JPEG")
        src = None
        if self.page_dir:
            try:
                rel = found.resolve().relative_to(self.page_dir.resolve()).as_posix()
                if rel.split("/", 1)[0] in ("assets", "attachments"):
                    src = rel
            except ValueError:
                pass
        if src is None:
            name = hashlib.sha256(data).hexdigest()[:12] + "-" + _asset_stem(found.name)
            self.staged[name] = data
            src = "assets/" + name
        self.cache[ref] = (src, size)
        return self.cache[ref]

    def copy_into(self, page_dir: Path) -> None:
        for name, data in self.staged.items():
            target = page_dir / "assets" / name
            if not target.is_file() or target.read_bytes() != data:
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(target.name + ".tmp")
                tmp.write_bytes(data)
                os.replace(tmp, target)


def _asset_stem(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "-", name).replace("..", "-").strip(".-")[:80] or "image"


def _img(src: str, size: tuple[int, int] | None, alt: str) -> str:
    dims = f' width="{size[0]}" height="{size[1]}"' if size else ""
    return f'<img src="{E(src, quote=True)}" alt="{E(alt, quote=True)}"{dims}>'


def compare_html(pairs: list, layout: str, title: str = "", attrs: str = "") -> str:
    """The current-vs-proposed block. findings.js `compareHtml` builds the same markup.

    `pairs` is [((src, size, caption), (src, size, caption))]; `layout` is
    `side` (portrait) or `stack` (landscape).
    """
    def cell(role: str, item: tuple, label: bool = True) -> str:
        src, size, caption = item
        # The space keeps "Current Today" apart in a card's evidence excerpt.
        tag = f'<span class="aa-cmp-label" data-role="{role}">{ROLES[role]}</span> ' if label else ""
        alt = f"{ROLES[role]}: {caption}" if caption else ROLES[role]
        return (f'<figure class="aa-cmp-cell" data-role="{role}"><figcaption title="{E(caption, quote=True)}">'
                f'{tag}{inline(caption)}</figcaption>{_img(src, size, alt)}</figure>')

    head = f'<figcaption class="aa-cmp-title">{inline(title)}</figcaption>' if title else ""
    if layout == "side" and len(pairs) > 1:
        body = "".join(
            f'<div class="aa-cmp-row-head"><span class="aa-cmp-label" data-role="{role}">{ROLES[role]}</span></div>'
            f'<div class="aa-cmp-row">{"".join(cell(role, pair[k], label=False) for pair in pairs)}</div>'
            for k, role in enumerate(ROLES))
    elif layout == "side":
        body = f'<div class="aa-cmp-row">{cell("current", pairs[0][0])}{cell("proposed", pairs[0][1])}</div>'
    else:
        body = "".join(f'<div class="aa-cmp-pair">{cell("current", c)}{cell("proposed", p)}</div>'
                       for c, p in pairs)
    return (f'<figure class="aa-compare" data-layout="{layout}" data-pairs="{len(pairs)}"{attrs}>'
            f"{head}{body}</figure>")


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
        fig:<slug>                an image, keyed on its caption (else file name)
        cmp:<slug>                a compare block, keyed on its title (else section)
        d:<n>                     a decision card that owns its own anchor
    """

    def __init__(self, title: str, skip_cards: bool = False,
                 structural: set[str] | None = None,
                 images: ImageStore | None = None, ask_numbers: list[int] | None = None) -> None:
        self.title = title
        self.skip_cards = skip_cards
        self.ask_numbers = iter(ask_numbers or ())
        self.images = images or ImageStore(None, None)
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
        if _INLINE_IMAGE.search(text):
            raise PageGenError(f"put each image on its own line: {clip(text, 80)!r} · fix: move the image out of the sentence")
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

    def figure(self, caption: str, ref: str) -> None:
        self.ensure_section()
        src, size = self.images.resolve(ref)
        aid = self._unique(f"fig:{slugify(caption or Path(ref).stem, 40)}")
        self.reg(aid, caption or Path(ref).name, "figure", parent=self.parent)
        orient = "portrait" if size and size[1] > size[0] else "landscape"
        cap = f"<figcaption>{inline(caption)}</figcaption>" if caption else ""
        self.parts.append(f'<figure class="aa-figure" data-orient="{orient}" data-anchor-id="{aid}">'
                          f"{_img(src, size, caption or Path(ref).name)}{cap}</figure>")

    def compare(self, raw: str) -> None:
        self.ensure_section()
        title, pairs, layout = parse_compare(raw)
        resolved = [tuple((*self.images.resolve(path), caption) for path, caption in pair) for pair in pairs]
        layout = layout or layout_for([item[1] for pair in resolved for item in pair])
        aid = self._unique(f"cmp:{slugify(title, 40) if title else self.section_slug}")
        self.reg(aid, title or "Current vs proposed", "compare", parent=self.parent)
        self.parts.append(compare_html(resolved, layout, title, f' data-anchor-id="{aid}"'))

    def details(self, raw: str) -> None:
        self.ensure_section()
        summary, _, body = raw.strip().partition("\n")
        if not summary.strip():
            raise PageGenError("a details fence has no summary · fix: put the summary on its first line")
        blocks = parse_blocks(body)
        if any(b["kind"] in ("cards", "ask", "project", "details", "heading") for b in blocks):
            raise PageGenError("a details fence holds a heading, card or project · fix: move headings and cards outside it")
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
                    f"kpi tone must be bad, warn or ok (got {cls!r} in {tile!r}) · fix: end the tile with | bad, | warn or | ok")
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
            raise PageGenError(f"```cards block is not valid JSON ({exc}) · fix: correct the JSON or write ```ask cards") from exc
        if isinstance(data, dict):
            data = data.get("cards")
        if not isinstance(data, list) or not data:
            raise PageGenError(
                '```cards block is not a list of cards · fix: a JSON array of '
                '{anchor_id, text, decision_request} objects, or ```ask cards')
        rendered = []
        for card in data:
            if not isinstance(card, dict):
                raise PageGenError("a ```cards entry is not an object · fix: make each entry {anchor_id, text, decision_request}")
            rendered.append(self._card(card))
        self.parts.append(f'<div class="cards">{"".join(rendered)}</div>')

    def ask_block(self, raw: str) -> None:
        self.ensure_section()
        card = parse_ask(raw)
        dr = card["decision_request"]
        dr.setdefault("evidence", [{"label": self.section_title, "anchor": self.section}])
        # Without reserved numbers (a comparison render) an unnumbered card keeps a d:<n> anchor.
        number = card.get("number") or next(self.ask_numbers, None)
        if number:
            card["number"], card["anchor_id"] = number, f"d:q{number}"
        self.parts.append(f'<div class="cards">{self._card(card)}</div>')

    def _card(self, card: dict) -> str:
        dr = card.get("decision_request") if isinstance(card.get("decision_request"), dict) else {}
        text = re.sub(r"\s+", " ", (card.get("text") or dr.get("prompt") or "")).strip()
        if not text:
            raise PageGenError("a card has neither `text` nor `decision_request.prompt` · fix: give it a prompt")
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
        elif kind == "ask" and not self.skip_cards:
            self.ask_block(block["raw"])
        elif kind == "details":
            self.details(block["raw"])
        elif kind == "image":
            self.figure(block["caption"], block["path"])
        elif kind == "compare":
            self.compare(block["raw"])

    @property
    def canvas(self) -> str:
        return CSS + "\n" + "\n".join(self.parts)


def render(meta: dict, blocks: list[dict],
           images: ImageStore | None = None, ask_numbers: list[int] | None = None) -> tuple[str, dict, list[dict]]:
    """Two passes: one to learn which anchors the prose owns, one to render.

    Without the first pass a card that names `tbl:columns:row:tier` before the
    table is parsed would claim the id, and the row would silently slide to
    `…:tier-2` — the card would point at nothing and the evidence link would
    scroll nowhere.
    """
    title = meta.get("title", "")
    images = images or ImageStore(None, None)
    prepass = Renderer(title, skip_cards=True, images=images)
    prepass.run(blocks)
    renderer = Renderer(title, structural=set(prepass.used), images=images, ask_numbers=ask_numbers)
    renderer.run(blocks)
    for card in renderer.cards:  # `see:` may name content further down; label it from the whole page
        if card.get("source_kind") == "ask":
            for item in card["decision_request"]["evidence"]:
                item["label"] = (renderer.registry.get(item["anchor"]) or {}).get("name") or item["label"]
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
                "· fix: keep CSS inside the <style> block")

    anchors = _ANCHOR_ATTR.findall(canvas)
    seen: set[str] = set()
    for aid in anchors:
        if aid in seen:
            problems.append(f"duplicate anchor id: {aid!r} · fix: rename one of the two headings, rows or captions")
        seen.add(aid)
    if not anchors:
        problems.append("no anchors — nothing on this page can be commented on · fix: add a ## section with text")
    for aid in sorted(seen - set(registry)):
        problems.append(f"anchor {aid!r} is rendered but missing from ANCHOR_REGISTRY · fix: report this annotate bug with the page.md")
    for aid in sorted(set(registry) - seen):
        problems.append(f"anchor {aid!r} is registered but not rendered · fix: report this annotate bug with the page.md")
    return problems


def _first_problem(problems: list[str]) -> str:
    """One line: the first problem, how many follow, then its fix."""
    head, _, fix = problems[0].partition(" · fix: ")
    more = f" (+{len(problems) - 1} more)" if len(problems) > 1 else ""
    return f"{head}{more} · fix: {fix}"


def _is_later_version(version: str) -> bool:
    return bool(re.fullmatch(r"v\d+", version) and int(version[1:]) > 1)


def _round_contract_problems(meta: dict, blocks: list[dict], cards: list[dict],
                             registry: dict, version: str) -> list[str]:
    """Authoring contract for cumulative rounds after v1."""
    if not _is_later_version(version) or "full_plan" not in meta:
        return []
    problems = []
    if str(meta.get("full_plan") or "").strip().lower() != "true":
        problems.append("a full plan needs `full_plan: true` · fix: set `full_plan: true` in the front matter")
    if not str(meta.get("other_files_required") or "").strip():
        problems.append(
            "a full plan names no other files · fix: add `other_files_required: none` or the file list")

    card_blocks = [i for i, block in enumerate(blocks) if block.get("kind") == "cards"]
    # Numbered by annotate and citing their own section, ask cards may sit anywhere; JSON cards keep every rule.
    cards = [card for card in cards if card.get("source_kind") != "ask"]
    if cards:
        if len(card_blocks) != 1:
            problems.append("a full plan has several ```cards blocks · fix: merge them into one, or write ```ask cards")
        elif card_blocks:
            prior_h2 = next((
                block for block in reversed(blocks[:card_blocks[0]])
                if block.get("kind") == "heading" and block.get("level") <= 2
            ), None)
            if not prior_h2 or slugify(prior_h2.get("text", "")) not in {"questions-for-reviewer", "questions-for-chang"}:
                problems.append(
                    "the ```cards block is outside `## Questions for reviewer` · fix: move it into that final section, or write ```ask cards")

        seen: set[int] = set()
        previous = 0
        for card in cards:
            number = card.get("number")
            if isinstance(number, bool) or not isinstance(number, int) or number < 1:
                problems.append("a JSON card has no `number` · fix: add a positive `number`, or write ```ask cards (annotate numbers them)")
                continue
            if number in seen:
                problems.append(f"duplicate card number {number} · fix: give each card its own number")
            if number <= previous:
                problems.append("card numbers must be strictly increasing · fix: order the cards by number")
            seen.add(number)
            previous = number

            expected_anchor = f"d:q{number}"
            if card.get("anchor_id") != expected_anchor:
                problems.append(
                    f"card #{number} has anchor_id {card.get('anchor_id')!r} · fix: use {expected_anchor!r}; "
                    "cite plan locations in decision_request.evidence")
            prompt = str((card.get("decision_request") or {}).get("prompt") or "")
            if re.match(r"^\s*(?:Q(?:uestion)?\s*\d+|#\s*\d+)", prompt, re.IGNORECASE):
                problems.append(
                    f"card #{number} prompt repeats a number · fix: drop the number from the prompt")
            evidence = (card.get("decision_request") or {}).get("evidence")
            if not isinstance(evidence, list) or not evidence:
                problems.append(
                    f"card #{number} cites no evidence · fix: add decision_request.evidence with an anchor on this page")
            else:
                for item in evidence:
                    anchor = item.get("anchor") if isinstance(item, dict) else None
                    if not anchor or anchor not in registry:
                        problems.append(
                            f"card #{number} cites {anchor!r}, not on this page · fix: cite an anchor on this page")
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
        and slugify(block["text"]) not in {"questions-for-reviewer", "questions-for-chang"}
    }
    current_sections = {
        slugify(block["text"])
        for block in blocks
        if block.get("kind") == "heading" and block.get("level") == 2
        and slugify(block["text"]) not in {"questions-for-reviewer", "questions-for-chang"}
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
_HAS_IMAGES = re.compile(r"^\s*(?:!\[|(?:```|~~~)\s*compare\s*$)", re.MULTILINE | re.IGNORECASE)
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

    A previous markdown with images is compared through its rendered page: its
    image paths may now name newer screenshots, which would hide a change.
    None when there is nothing trustworthy to compare with: v1, no previous
    version on disk, or a previous page that was not generated from markdown
    (a hand-built page's sections mean nothing to this comparison).
    """
    if not _is_later_version(version):
        return None
    prev = f"v{int(version[1:]) - 1}"
    try:
        source = slug_dir / "source" / f"{prev}.md"
        prev_text = source.read_text(encoding="utf-8") if source.is_file() else None
        if prev_text is not None and not _HAS_IMAGES.search(prev_text):
            prev_meta, prev_body = parse_front_matter(prev_text)
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
            from .long_pages import plain_images
            return prev, section_bodies(plain_images(canvas))
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
def build_html(meta: dict, canvas: str, registry: dict) -> str:
    """Keep the document wrapper the server extracts; chrome comes from the shell."""
    # Escape all '<' so neither script-end tags nor HTML double-escaped
    # script states can alter parsing. JSON decoding restores exact labels.
    registry_js = json.dumps(registry, indent=1, ensure_ascii=False).replace("<", "\\u003c")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{E(meta["title"])}</title>
<script src="diagram-plot.js"></script>
</head>
<body>
<div id="canvas-wrapper">
<!-- CANVAS CONTENT — injected by Claude ── -->
{canvas}
<!-- END CANVAS CONTENT ──────────────────── -->
</div>
<script>const ANCHOR_REGISTRY = {registry_js};
</script>
</body>
</html>
"""


def render_plan(text: str, plan_id: str, *, title: str | None = None,
                base_dir: Path | None = None, page_dir: Path | None = None) -> tuple[str, str]:
    """Render an independent Markdown plan without writing Review/page metadata.

    Images resolve from `base_dir` (the plan file's folder) and are copied into
    `page_dir`/assets, which a plan shares with Review (its <base> is the page).
    """
    meta, body = parse_front_matter(text)
    for key in meta:
        if key not in FRONT_MATTER_KEYS:
            raise PageGenError(f"unknown front-matter key {key!r} · fix: use one of {', '.join(FRONT_MATTER_KEYS)}")
    meta["title"] = title or meta.get("title") or plan_id.replace("-", " ").capitalize()
    meta["slug"] = f"plan:{plan_id}"
    meta.setdefault("date", datetime.date.today().isoformat())
    blocks = parse_blocks(body)
    images = ImageStore(base_dir, page_dir)
    canvas, registry, _cards = render(meta, blocks, images)
    problems = lint(canvas, registry)
    if problems:
        raise PageGenError("plan: " + _first_problem(problems))  # fix: passes through
    if page_dir is not None:
        images.copy_into(page_dir)
    # The HTTP plan route supplies the actual version; no Review version is embedded.
    return build_html(meta, canvas, registry), meta["title"]


def generate(source: Path, slug_dir: Path, version: str | None = None,
             label: str | None = None, *, title: str | None = None,
             fixes: str | None = None, text: str | None = None, _attempt: int = 0) -> dict:
    """Parse, render, lint and write every file a publishable page needs (`text` replaces the file's)."""
    merged = text is not None
    text = source.read_text(encoding="utf-8") if text is None else text
    meta, body = parse_front_matter(text)
    for key in meta:
        if key not in FRONT_MATTER_KEYS:
            raise PageGenError(
                f"unknown front-matter key {key!r} · fix: use one of "
                f"{', '.join(FRONT_MATTER_KEYS)}")
    meta.setdefault("title", slug_dir.name.replace("-", " ").strip().capitalize())
    meta.setdefault("slug", slug_dir.name)
    meta.setdefault("date", datetime.date.today().isoformat())
    meta.setdefault("subtitle", "")
    from .page_names import validate_name
    if title is not None:
        try:
            title = validate_name(title)
        except ValueError as exc:
            raise PageGenError(str(exc)) from exc  # fix: passes through
    from .review_versions import next_version
    picked = not (version or meta.get("version"))  # picked here, so a concurrent publish may take it first
    version = version or meta.get("version") or next_version(slug_dir)
    if not re.fullmatch(r"v\d+", version):
        raise PageGenError(f"version must look like v1, v2, v3 (got {version!r}) · fix: --version v2, or leave it out for the next one")
    from .cli import _read_meta
    from .review_versions import require_draft
    try:
        require_draft(_read_meta(slug_dir), version)
    except ValueError as exc:
        raise PageGenError(str(exc)) from exc  # fix: passes through
    label = label or meta.get("label") or f"generated from {source.name}"

    blocks = parse_blocks(body)
    project_blocks = [b for b in blocks if b["kind"] == "project"]
    project_data = None
    if project_blocks:
        from .project_state import validate_project
        if len(project_blocks) > 1:
            raise PageGenError("the page has several project fences · fix: merge them into one")
        try:
            project_data = validate_project(json.loads(project_blocks[0]["raw"]))
        except ValueError as exc:
            raise PageGenError(f"project fence: {exc} · fix: correct the project JSON") from exc
    images = ImageStore(source.parent, slug_dir)
    reserved = _reserve_numbers(slug_dir, version, blocks)
    canvas, registry, cards = render(meta, blocks, images, reserved)
    from .decision_quality import card_refusal, page_anchors
    anchors = page_anchors(canvas)
    for card in cards:
        refusal = card_refusal(card, anchors)
        if refusal:
            raise PageGenError(f'card "{first_sentence(card["text"])}" {refusal}')  # fix: passes through
    problems = lint(canvas, registry)
    problems += _round_contract_problems(meta, blocks, cards, registry, version)
    if problems:
        raise PageGenError(_first_problem(problems))  # fix: passes through

    unchanged: list[str] = []
    previous = _previous_sections(slug_dir, version, meta["title"])
    if previous:
        canvas, unchanged = mark_unchanged_sections(canvas, *previous)
    # Long pages: finished topics fold or move to an archive page; big screenshots get previews.
    from .long_pages import arrange, light_images
    images.copy_into(slug_dir)
    canvas, cards, registry, layout = arrange(canvas, cards, registry, unchanged, slug_dir, meta, version)
    canvas = light_images(canvas, slug_dir)
    warnings_layout = layout.pop("warnings")

    banner = _scope_banner(meta, version)
    if banner:
        canvas = canvas.replace('<div class="aa">', f'<div class="aa">{banner}', 1)
    warnings = _full_plan_warnings(slug_dir, version, blocks) if "full_plan" in meta else []
    warnings += warnings_layout
    from .decision_quality import decision_warnings
    for card in cards:
        warnings += [f"{card['anchor_id']}: {warning}" for warning in decision_warnings(card.get("decision_request") or {})]

    html_out = build_html(meta, canvas, registry)
    from .page_names import page_name, set_page_name
    # Resolve legacy titles before an in-place regeneration replaces their HTML.
    initial_name = page_name(slug_dir, fallback=meta["title"])
    stats = {"sections": layout["sections"], "screenshots": layout["screenshots"]}
    if reserved:
        stats["reserved"] = reserved
    try:
        stored = _image_refs(_number_ask_fences(text, reserved), {ref: src for ref, (src, _) in images.cache.items()})
        prior = _write_files(slug_dir, version, label, source, stored, html_out, cards, stats, fixes, picked)
    except ValueError as exc:
        raise PageGenError(str(exc)) from exc  # fix: passes through
    except _Regenerate as moved:
        if moved.args and merged:  # rebuild on the newer source, or the other publish's section is lost
            raise VersionTaken(f"{version} was taken · fix: rerun the same command") from None
        if _attempt >= 2:
            raise PageGenError("numbers kept colliding with another publish · fix: rerun the same command") from None
        return generate(source, slug_dir, None if picked else version, label, title=title, fixes=fixes, text=text,
                        _attempt=_attempt + 1)
    name = set_page_name(slug_dir, title, initial_name=initial_name)
    if project_data is not None:
        from .project_state import save_project
        save_project(slug_dir, project_data)
    return {
        "slug_dir": slug_dir,
        "slug": slug_dir.name,
        "doc_id": meta["slug"],
        "title": meta["title"],
        "name": name,
        "version": version,
        "label": label,
        "fixes": fixes,
        "anchors": len(registry),
        "cards": len(cards),
        "reserved": reserved,
        "picked": picked,
        "warnings": warnings,
        "unchanged_sections": unchanged,
        "layout": layout,
        "prior_versions": prior,
        "html": slug_dir / "versions" / f"{version}.html",
        "cards_json": slug_dir / "versions" / f"{version}.cards.json",
        "source_copy": slug_dir / "source" / f"{version}.md",
    }


def _atomic_write(path: Path, text: str) -> None:
    from .store import write_text
    write_text(path, text)          # servers read versions/<vN>.html live


def _write_files(slug_dir: Path, version: str, label: str, source: Path,
                 source_text: str, html_out: str, cards: list[dict], stats: dict | None = None, fixes: str | None = None,
                 picked: bool = False) -> list[str]:
    from .store import transaction as _locked_store
    slug_dir.mkdir(parents=True, exist_ok=True)
    with _locked_store(slug_dir):
        return _write_files_locked(slug_dir, version, label, source, source_text, html_out, cards, stats, fixes, picked)


def _write_files_locked(slug_dir: Path, version: str, label: str, source: Path,
                 source_text: str, html_out: str, cards: list[dict], stats: dict | None = None, fixes: str | None = None,
                 picked: bool = False) -> list[str]:
    from .cli import _read_meta

    slug_dir.mkdir(parents=True, exist_ok=True)
    existing_meta = _read_meta(slug_dir)
    prior = sorted(h.get("version") for h in (existing_meta.get("history") or [])
                   if isinstance(h, dict) and h.get("version"))
    from .review_versions import draft_path, shown, stage
    if set((stats or {}).get("reserved") or ()) & _taken_numbers(slug_dir, version):
        raise _Regenerate
    if picked and (shown(existing_meta, version) or draft_path(slug_dir, version).exists()):
        raise _Regenerate(version)  # another publish staged or showed this version since it was picked
    stage(slug_dir, version, label, fixes, stats or {})

    _atomic_write(slug_dir / "versions" / f"{version}.html", html_out)
    _atomic_write(slug_dir / "source" / f"{version}.md", source_text)
    cards_text = json.dumps(cards, indent=2, ensure_ascii=False) + "\n"
    _atomic_write(slug_dir / "cards.json", cards_text)
    _atomic_write(slug_dir / "versions" / f"{version}.cards.json", cards_text)

    # Reports can have no decision cards, so the server may never write this
    # store before the next publish gate reads it. Initialize valid JSON while
    # leaving any existing feedback (including a damaged store) untouched.
    from .store import transaction as _locked_store
    from .store import write_json as _atomic_write_json
    with _locked_store(slug_dir):
        if not (slug_dir / "comments.json").exists():
            _atomic_write_json(slug_dir / "comments.json", {"schema_version": 2, "anchors": {}, "archived": {}})
    return [v for v in prior if v != version]


# ────────────────────────────────────────────────────────────────────────────
# The example document
# ────────────────────────────────────────────────────────────────────────────
EXAMPLE = '''---
title: Project workspace
---

## Checkout

The open question comes first; its card renders after the comparison. Screenshots are local files, copied into the page. Phone shots sit side by side; desktop shots stack.

```compare
title: Checkout
current: shots/checkout-current.png | Today
proposed: shots/checkout-proposed.png | One-step pay
```

```ask
Ship the one-step checkout?
Checks passed; the preview matches the proposed screen.
+ Ship: Preview becomes public.
- Hold: Keep the current checkout.
see: cmp:checkout
```

## Progress

Build passed. Preview is ready for review.

```project
{"title":"Project","modules":[{"id":"status","title":"Progress","kind":"progress","items":[{"label":"Preview build","status":"done","detail":"Checks passed; preview ready."}]}]}
```
'''

def cmd_new(args) -> int:
    from .cli import _inv

    if getattr(args, "example", False):
        sys.stdout.write(EXAMPLE)
        return 0
    if not args.slug_dir or not args.from_file:
        print("ERROR: `new` has no page or markdown · fix: annotate new <slug-dir> --from <page.md> "
              "(or --example on its own)", file=sys.stderr)
        return 2

    source = Path(args.from_file).expanduser()
    if not source.is_file():
        print(f"ERROR: markdown {source} not found · fix: check the --from path", file=sys.stderr)
        return 2
    slug_dir = Path(args.slug_dir).expanduser().resolve()
    from .cli import _moved_page, _slug_project
    if _moved_page(slug_dir):
        return 2
    args.project, page_slug = _slug_project(slug_dir, getattr(args, "project", None))
    from .workspace import duplicate_message, duplicate_page, exception_reason
    try:
        reason = exception_reason(args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)  # fix: passes through
        return 2
    if not reason:
        duplicate = duplicate_page(slug_dir, getattr(args, "project", None))
        if duplicate:
            print(duplicate_message(duplicate), file=sys.stderr)
            return 2
    from .cli import NUMBERS_TAKEN, VERSION_TAKEN
    version, auto = args.version, None
    for _attempt in range(3):  # a number or version another publish took first regenerates the draft
        text = None
        if getattr(args, "section", None):  # (again) on the newest source: another publish may have landed
            try:
                merged = section_source(slug_dir, source.read_text(encoding="utf-8"), args.section)
            except PageGenError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)  # fix: passes through
                return 1
            text = merged["text"]
            args.section_title, args.kept = merged["section"], merged["kept"]
            args.section_base = merged["base"] if merged["base"] != merged["current"] else None
        try:
            result = generate(source, slug_dir, version, args.label, title=getattr(args, "title", None),
                              fixes=getattr(args, "fixes", None), text=text)
        except VersionTaken:
            continue  # merge again on the version that was staged first
        except PageGenError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)  # fix: passes through
            return 1
        except OSError as exc:
            print(f"ERROR: could not write the page ({exc}) · fix: check the page folder is writable and rerun", file=sys.stderr)
            return 1

        slug, version = page_slug, result["version"]
        print(f"  wrote          {result['html']}")
        print(f"  anchors        {result['anchors']}")
        print(f"  cards          {result['cards']}"
              + (f" → {result['cards_json']}" if result["cards"] else ""))
        print(f"  source copy    {result['source_copy']}")
        print(f"  version        {version} ({result['label']})"
              + (f"; earlier: {', '.join(result['prior_versions'])}"
                 if result["prior_versions"] else ""))
        layout = result.get("layout") or {}
        if layout.get("folded"):
            print(f"  earlier        {len(layout['folded'])} finished topics folded into Earlier updates")
        for archive in layout.get("archived") or []:
            print(f"  archived       {archive['topics']} finished topics → {archive['id']} ({archive['title']})")
        if layout.get("already_archived"):
            print(f"  archived       {len(layout['already_archived'])} topics already in an archive page left out")
        if layout.get("returned"):
            print(f"  returned       {len(layout['returned'])} archived topics changed and are back on the page")
        for warning in result.get("warnings") or []:
            print(f"  WARN           {warning}")

        args.candidate_version = version
        args.ready = True
        args.ask = bool(result["cards"])  # a page with cards is always published as its whole round
        if not args.publish:
            from shlex import quote
            print("  staged; publish the complete round:")
            print(f"    {_inv()} publish {quote(str(slug_dir))} --version {version}")
            return 0
        rc = _call_publish(slug_dir, args)
        if rc:
            return rc
        if result["cards"]:
            rc = _call_ask(slug, result["cards_json"], version, args, bool(result["reserved"]))
        else:
            rc = _call_publish_version(slug_dir, version, result["label"], args)
        auto = result["picked"] if auto is None else auto
        if rc == VERSION_TAKEN and auto:
            version = None  # the next version, on top of the one that landed
        elif rc == VERSION_TAKEN:
            print(f"not live: {version} is not newer than the version shown now · fix: leave out --version",
                  file=sys.stderr)
            return 2
        elif rc != NUMBERS_TAKEN:
            return rc
    print("not live: numbers kept colliding with another publish · fix: rerun the same command", file=sys.stderr)
    return 2


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
        candidate_version=getattr(args, "candidate_version", None),
    )


def _call_publish(slug_dir: Path, args) -> int:
    from .cli import cmd_publish
    return cmd_publish(_publish_namespace(slug_dir, args))


def _call_publish_version(slug_dir: Path, version: str, label: str, args) -> int:
    from .cli import cmd_publish_version
    return cmd_publish_version(argparse.Namespace(
        slug_dir=str(slug_dir), version=version, label=label,
        project=getattr(args, "project", None), prepared=True, newest=True))


def _call_ask(slug: str, cards_json: Path, version: str, args, renumber: bool = False) -> int:
    from .cli import cmd_ask
    return cmd_ask(argparse.Namespace(
        slug=slug, from_file=str(cards_json), version=version,
        project=getattr(args, "project", None), author=None, json=False,
        ready=getattr(args, "ready", False), renumber=renumber, newest=True))


def add_parser(sub) -> None:
    """`annotate new` — the one subparser cli.py adds for this module."""
    sp = sub.add_parser(
        "new", help="markdown → a publishable review page (versions/vN.html + cards.json)")
    sp.add_argument("slug_dir", nargs="?", default=None)
    sp.add_argument("--from", dest="from_file", default=None, metavar="page.md",
                    help="the markdown document (front matter + prose + ```cards)")
    sp.add_argument("--version", default=None, help="vN (default: front matter, else the next version)")
    sp.add_argument("--fixes", default=None, metavar="vN", help="this new version fixes an earlier visible version")
    sp.add_argument("--label", default=None, help="version label for the rail")
    sp.add_argument("--title", default=None, help="stable page name; version titles stay in Markdown")
    sp.add_argument("--publish", action="store_true", help="run `publish` on the result")
    sp.add_argument("--ask", action="store_true",
                    help="accepted for old commands; a page with cards always publishes its round")
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
    sp.add_argument("--json", action="store_true", help="print full generation and publication output")
    sp.add_argument("--verbose", action="store_true", help="receipt with the page link")
    sp.set_defaults(func=cmd_new)
