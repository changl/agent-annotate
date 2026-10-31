"""Long pages stay light: previews, Earlier updates, archive pages.

Fixed rules, applied by every publish (approved v27 #3 and #4); no agent step,
never a refusal:

- A topic is a `##` section. A page's size is its `##` + `###` headings and its
  screenshots, the fold included.
- An open topic holds, or is evidence for, an unanswered card, or has a reviewer
  comment not yet closed. Open topics and the intro never move.
- A finished topic is not open and renders the same as in the previous version.
- Finished topics fold into one Earlier updates bar at the bottom, inside a
  <template> the page builds only when opened.
- Over 40 sections or 60 screenshots, every finished topic moves to a new dated
  archive document (plans storage, section "archive"). archive/index.json keeps
  each archived topic's content hash, so republishing a full page.md neither
  duplicates a topic nor loses one: the same content is dropped, a changed (or
  reopened) topic comes back to the working page and leaves its archive.
- Each large screenshot gets a reduced preview, made once per content hash with
  macOS `sips`; elsewhere the original is used.
"""

from __future__ import annotations

import datetime
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from .images import image_size

MAX_SECTIONS = 40
MAX_SCREENSHOTS = 60
PREVIEW_EDGE = 1200
PREVIEW_MIN_BYTES = 300 * 1024

E = html.escape
_SECTION = re.compile(r'<section data-anchor-id="([^"]+)"(?: [a-z-]+="[^"]*")*>(.*?)</section>', re.DOTALL)
_ANCHOR = re.compile(r'data-anchor-id="([^"]*)"')
_IMG = re.compile(r'<img src="([^"]*)"([^>]*)>')
_LAZY = ' loading="lazy" decoding="async"'
_PNG = b"\x89PNG\r\n\x1a\n"


# ── previews ─────────────────────────────────────────────────────────────
def _preview(page_dir: Path, src: str) -> str | None:
    """assets/preview/<hash>.jpg for a large page image, made once; None keeps the original."""
    if not src.startswith(("assets/", "attachments/")) or src.startswith("assets/preview/") or ".." in src:
        return None
    try:
        data = (page_dir / src).read_bytes()
    except OSError:
        return None
    size = image_size(data)
    if not size or data[:4] == b"GIF8" or (max(size) <= PREVIEW_EDGE and len(data) <= PREVIEW_MIN_BYTES):
        return None
    alpha = data[:8] == _PNG and len(data) > 25 and (data[25] in (4, 6) or b"tRNS" in data[:65536])
    name = f"assets/preview/{hashlib.sha256(data).hexdigest()[:16]}.{'png' if alpha else 'jpg'}"
    target = page_dir / name
    if target.is_file():
        return name
    sips = shutil.which("sips")
    if not sips:
        return None
    tmp = (page_dir / src).with_name(f".{os.getpid()}-{target.name}")
    options = [] if alpha else ["-s", "formatOptions", "70"]
    try:
        done = subprocess.run([sips, "-Z", str(min(PREVIEW_EDGE, max(size))), "-s", "format",
                               "png" if alpha else "jpeg", *options, str(page_dir / src), "--out", str(tmp)],
                              capture_output=True, timeout=60, check=False)
        if done.returncode == 0 and tmp.is_file() and 0 < tmp.stat().st_size < len(data):
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(tmp, target)
            return name
    except (OSError, subprocess.SubprocessError):
        pass
    finally:
        tmp.unlink(missing_ok=True)
    return None


def light_images(markup: str, page_dir: Path | None) -> str:
    """Lazy images; a large one shows its preview and links ⤢ Full size to the original."""
    cache: dict[str, str | None] = {}

    def swap(match: re.Match) -> str:
        src, rest = match.group(1), match.group(2)
        if "data-full=" in rest or "loading=" in rest:
            return match.group(0)
        raw = html.unescape(src)
        if raw not in cache:
            cache[raw] = _preview(page_dir, raw) if page_dir else None
        if not cache[raw]:
            return f'<img src="{src}"{rest}{_LAZY}>'
        return (f'<img src="{E(cache[raw], quote=True)}" data-full="{src}"{rest}{_LAZY}>'
                f'<a class="aa-full" href="{src}" target="_blank" rel="noopener">⤢ Full size</a>')
    return _IMG.sub(swap, markup)


def plain_images(markup: str) -> str:
    """Undo light_images, so a section compares equal across the change."""
    markup = re.sub(r'<a class="aa-full" [^>]*>[^<]*</a>', "", markup)
    markup = re.sub(r'<img src="[^"]*" data-full="([^"]*)"', r'<img src="\1"', markup)
    return markup.replace(_LAZY, "")


# ── sizes ────────────────────────────────────────────────────────────────
def size_of(markup: str) -> tuple[int, int]:
    """(sections, screenshots): `##` + `###` headings and images."""
    return len(re.findall(r"<h[23][ >]", markup)), len(re.findall(r"<img ", markup))


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _size_text(sections: int, shots: int) -> str:
    return _plural(sections, "section") + (f", {_plural(shots, 'screenshot')}" if shots else "")


def body_hash(body: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", plain_images(body)).strip().encode()).hexdigest()[:16]


def _title(body: str) -> str:
    match = re.search(r"<h2>(.*?)</h2>", body, re.DOTALL)
    return html.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip() if match else ""


# ── open topics ──────────────────────────────────────────────────────────
def _open_anchors(page_dir: Path, cards: list[dict]) -> set[str] | None:
    """Anchors an open item holds or points at; None when the store cannot be read."""
    from .categories import comment_category
    path = page_dir / "comments.json"
    try:
        store = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"anchors": {}}
    except (OSError, ValueError):
        return None
    anchors = store.get("anchors") if isinstance(store, dict) else None
    if not isinstance(anchors, dict):
        return None
    result: set[str] = set()
    answered: set = set()

    def evidence(request) -> set[str]:
        items = request.get("evidence") if isinstance(request, dict) else None
        return {e["anchor"] for e in items or [] if isinstance(e, dict) and isinstance(e.get("anchor"), str)}

    for anchor, items in anchors.items():
        for c in items if isinstance(items, list) else []:
            if not isinstance(c, dict) or comment_category({"anchor_id": anchor, **c}) != "review":
                continue
            status = c.get("status") or "open"
            request = c.get("decision_request")
            verdict = (c.get("decision") or {}).get("verdict") if isinstance(c.get("decision"), dict) else None
            # As the rail classifies (shell.js classify): an unresolved question,
            # or any other comment still open, needs someone; addressed is done.
            if isinstance(request, dict):
                if verdict:
                    answered.update({anchor, c.get("number")} - {None})
                elif status not in ("archived", "resolved_in_version", "addressed_by_agent"):
                    result |= {anchor} | evidence(request)
            elif status == "open":
                result.add(anchor)
    for card in cards:
        request = card.get("decision_request")
        if isinstance(request, dict) and card.get("anchor_id") not in answered and card.get("number") not in answered:
            result |= {card.get("anchor_id")} | evidence(request)
    return result


# ── archive index ────────────────────────────────────────────────────────
def _index_path(page_dir: Path) -> Path:
    return page_dir / "archive" / "index.json"


def load_index(page_dir: Path) -> dict:
    try:
        data = json.loads(_index_path(page_dir).read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("archives"), list):
            return data
    except (OSError, ValueError):
        pass
    return {"archives": []}


def _save_index(page_dir: Path, index: dict) -> None:
    path = _index_path(page_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _local_day(ts: str) -> str:
    """The publisher's own calendar day for a UTC timestamp (an 01:06Z publish is the evening before in PDT)."""
    try:
        return datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00")).astimezone().date().isoformat()
    except ValueError:
        return str(ts)[:10]


def _since_dates(page_dir: Path, hashes: dict[str, str], version: str, today: str,
                 limit: int = 300) -> dict[str, str]:
    """{anchor: day its current content first went live}. Walks back through
    versions/vN.html (newest first, once for all topics, at most `limit` files):
    a topic's day moves back while an earlier version shows the same content, and
    stops at the first version where it differs. A version without the topic is
    skipped, so a topic that left and came back unchanged keeps its first day."""
    from .cli import _read_meta
    days = {aid: today for aid in hashes}
    open_ = set(hashes)
    number = int(version[1:]) if re.fullmatch(r"v\d+", version) else None
    entries = [h for h in _read_meta(page_dir).get("history") or [] if isinstance(h, dict)
               and re.fullmatch(r"v\d+", str(h.get("version"))) and h.get("ts")
               and (number is None or int(h["version"][1:]) < number)]
    entries.sort(key=lambda h: int(h["version"][1:]), reverse=True)
    for entry in entries[:limit]:
        if not open_:
            break
        try:
            markup = (page_dir / "versions" / f"{entry['version']}.html").read_text(encoding="utf-8")
        except OSError:
            continue
        for aid in [a for a in open_ if f'data-anchor-id="{a}"' in markup]:
            match = re.search(r'<section data-anchor-id="' + re.escape(aid) + r'"(?: [a-z-]+="[^"]*")*>(.*?)</section>',
                              markup, re.DOTALL)
            if match and body_hash(match.group(1)) == hashes[aid]:
                days[aid] = min(days[aid], _local_day(entry["ts"]))
            elif match:
                open_.discard(aid)
    return days


def _short(title: str, limit: int = 40) -> str:
    """A topic title for an archive's name, cut at a word with an ellipsis."""
    if len(title) <= limit:
        return title
    return title[:limit + 1].rsplit(" ", 1)[0].rstrip(" ,:;·–-") + "…"


def _span(start: str, end: str) -> str:
    a, b = datetime.date.fromisoformat(start), datetime.date.fromisoformat(end)
    if a == b:
        return f"{a:%b} {a.day}"
    if (a.year, a.month) == (b.year, b.month):
        return f"{a:%b} {a.day}–{b.day}"
    return f"{a:%b} {a.day}–{b:%b} {b.day}"


def _archive_html(meta: dict, title: str, bodies: list[str], registry: dict, page_dir: Path) -> str:
    from .pagegen import CSS, build_html
    sections = "".join(bodies)
    keep = set(_ANCHOR.findall(sections))
    canvas = (CSS + "\n" + f'<div class="aa"><h1 class="aa-page-title">{E(title)}</h1>'
              + light_images(sections, page_dir) + "</div>")
    return build_html({**meta, "title": title}, canvas, {k: v for k, v in registry.items() if k in keep}, "v1")


def _publish_archive(page_dir: Path, plan_id: str, title: str, label: str, markup: str, extra: dict) -> None:
    from .categories import _json, _write, publish_plan_revision, safe_path
    publish_plan_revision(page_dir, plan_id, markup, title=title, label=label, section="archive")
    path = safe_path(page_dir, f"plans/{plan_id}/meta.json")
    meta = _json(path, {})
    meta["archive"] = extra
    _write(path, meta)


def _withdraw_topics(page_dir: Path, index: dict, anchors: set[str], version: str) -> None:
    """Changed or reopened topics leave their archive: a new revision without them."""
    from .categories import _json, _write, plan_meta, safe_path
    for archive in index["archives"]:
        leaving = [t for t in archive["topics"] if t["anchor"] in anchors]
        if not leaving:
            continue
        archive["topics"] = [t for t in archive["topics"] if t["anchor"] not in anchors]
        try:
            meta = plan_meta(page_dir, archive["id"])
            if not archive["topics"]:
                # Every topic went back: the empty archive leaves Open project.
                path = safe_path(page_dir, f"plans/{archive['id']}/meta.json")
                _write(path, {**_json(path, {}), "section": "hidden"})
                continue
            markup = safe_path(page_dir, f"plans/{archive['id']}/versions/{meta['current']}.html").read_text(encoding="utf-8")
        except (KeyError, OSError, ValueError):
            continue
        markup = _SECTION.sub(lambda m: "" if m.group(1) in anchors else m.group(0), markup)
        sections, shots = size_of(markup)
        extra = {**(meta.get("archive") or {}), "sections": sections, "screenshots": shots,
                 "topics": [t["title"] for t in archive["topics"]]}
        _publish_archive(page_dir, archive["id"], meta.get("title") or archive["id"],
                         f"{len(leaving)} back on the page in {version}", markup, extra)


# ── the arrangement ──────────────────────────────────────────────────────
def arrange(canvas: str, cards: list[dict], registry: dict, unchanged: list[str], page_dir: Path,
            meta: dict, version: str, *, write: bool = True) -> tuple[str, list[dict], dict, dict]:
    """Fold or archive finished topics. Returns (canvas, cards, registry, report)."""
    report: dict = {"folded": [], "archived": [], "already_archived": [], "returned": [], "warnings": []}
    open_anchors = _open_anchors(page_dir, cards)
    sections = [(m.group(1), m.group(0), m.group(2)) for m in _SECTION.finditer(canvas)
                if m.group(2).lstrip().startswith("<h2>")]
    open_topics = set()
    for aid, whole, body in sections:
        inside = {aid, *_ANCHOR.findall(body)}
        holds = any(f'href="#{E(a, quote=True)}"' in body for a in open_anchors or ())
        if open_anchors is None or inside & open_anchors or holds:
            open_topics.add(aid)

    index = load_index(page_dir)
    archived = {t["anchor"]: t for a in index["archives"] for t in a.get("topics", [])}
    removed: list[tuple[str, str, str]] = []
    for aid, whole, body in sections:
        if aid not in archived:
            continue
        if aid not in open_topics and body_hash(body) == archived[aid].get("hash"):
            removed.append((aid, whole, body))
            report["already_archived"].append(aid)
        else:
            report["returned"].append(aid)
    finished = [s for s in sections if s[0] in set(unchanged) - open_topics
                and s[0] not in report["already_archived"]]

    def without(markup: str, parts) -> str:
        for _, whole, _ in parts:
            markup = markup.replace(whole, "", 1)
        return markup

    canvas = without(canvas, removed)
    sections_n, shots_n = size_of(canvas)
    archive = None
    if finished and (sections_n > MAX_SECTIONS or shots_n > MAX_SCREENSHOTS):
        archive = finished
        canvas = without(canvas, finished)
        removed += finished
    elif finished:
        folded = "".join(whole for _, whole, _ in finished)
        canvas = without(canvas, finished)
        n, shots = size_of(folded)
        fold = (f'<details class="aa-earlier" data-sections="{n}" data-shots="{shots}"><summary>'
                f'<strong>Earlier updates</strong> · {_size_text(n, shots)}'
                f'<small>Answered and finished topics. Not loaded until you open them.</small></summary>'
                f'<template class="aa-earlier-body">{folded}</template></details>')
        end = canvas.rfind("</div>")
        canvas = canvas[:end] + fold + canvas[end:]
        report["folded"] = [aid for aid, _, _ in finished]
    sections_n, shots_n = size_of(canvas)
    if sections_n > MAX_SECTIONS or shots_n > MAX_SCREENSHOTS:
        report["warnings"].append(
            f"page is over the size limit ({sections_n} sections, {shots_n} screenshots; limit "
            f"{MAX_SECTIONS} / {MAX_SCREENSHOTS}); every topic left on it is open or changed this round, "
            "and each moves to an archive page once it is answered and unchanged")

    full_registry = registry
    if removed:
        gone = set()
        for _, _, body in removed:
            gone |= set(_ANCHOR.findall(body))
        gone |= {aid for aid, _, _ in removed}
        cards = [c for c in cards if c.get("anchor_id") not in gone]
        registry = {k: v for k, v in registry.items() if k not in gone}

    if write and report["returned"]:
        _withdraw_topics(page_dir, index, set(report["returned"]), version)
    if write and archive:
        today = datetime.date.today().isoformat()
        taken = {a["id"] for a in index["archives"]}
        from .categories import list_plans
        taken |= {p["id"] for p in list_plans(page_dir)}
        plan_id, k = f"archive-{today}", 2
        while plan_id in taken:
            plan_id, k = f"archive-{today}-{k}", k + 1
        topics = [{"anchor": aid, "title": _title(body), "hash": body_hash(body)} for aid, _, body in archive]
        # Computed once, here; kept in archive/index.json only.
        since = _since_dates(page_dir, {t["anchor"]: t["hash"] for t in topics}, version, today)
        for topic in topics:
            topic["since"] = since[topic["anchor"]]
        start, end = min(since.values()), max(since.values())
        names = [_short(t["title"]) for t in topics]
        title = f"Archive {_span(start, end)} · {', '.join(names[:2])}" + (
            f" +{len(names) - 2}" if len(names) > 2 else "")
        markup = _archive_html(meta, title[:200], [whole for _, whole, _ in archive], full_registry, page_dir)
        n, shots = size_of(markup)
        _publish_archive(page_dir, plan_id, title[:200], f"{len(topics)} finished topics from {version}", markup,
                         {"from": start, "to": end, "sections": n, "screenshots": shots,
                          "topics": [t["title"] for t in topics], "version": version})
        index["archives"].append({"id": plan_id, "created": today, "version": version, "topics": topics})
        report["archived"] = [{"id": plan_id, "title": title[:200], "topics": len(topics)}]
    if write and (archive or report["returned"]):
        index["archives"] = [a for a in index["archives"] if a["topics"]]
        _save_index(page_dir, index)
    report["sections"], report["screenshots"] = sections_n, shots_n
    return canvas, cards, registry, report

