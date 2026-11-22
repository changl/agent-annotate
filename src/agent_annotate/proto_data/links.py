"""Pages & links tab data: this project's pages, archived snapshots, repos and folders, and the People list.

Read-only. Each page shows only its own project's material: the FastLane Drive prototype reads FastLane Drive's
folder; a copy of another project (meta proto_copy_of / proto_source) reads that project's folder, and never falls
back to FastLane Drive's. The project's other pages come from the live page registry (read only). Emails are always masked.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import re
from html.parser import HTMLParser

from .history import _comments, _plain, _stamp
from .reference import FLD_DIR, copy_library, documents, hide, notes, sized

PROJECT = Path.home() / "projects" / "fastlane-drive"  # where the dummy page was copied from
FLD_SOURCE = PROJECT / "reviews" / "fld-stack-round8"
REGISTRY = Path.home() / ".claude" / "annotate-state" / "state"  # live page records, read only
MASK = "member@example.com"
# documents kept on this page (mock round 9): the usage audit page and the go-live load test's k6 summary
USAGE_AUDIT = FLD_DIR / "planning/operations/usage-audit-2026-11-06/page/current.html"
LOAD_TEST = FLD_DIR / "planning/operations/orchestration/run_d169910aea33/reports/go-live-backend-2"
ROADMAP = FLD_DIR / "planning/05-roadmap.md"
# the admin team meeting: kept under Documents with its revisions, as in the mock, not listed as a page (r12 reference 7)
MEETING = FLD_SOURCE.parent / "fld-admin-meeting"


def meeting(folder: Path = MEETING) -> dict | None:
    """The meeting's published versions as revisions, oldest first, read only; None when its folder is missing."""
    revs = []
    for h in _json(folder / "current.meta.json").get("history") or []:
        v = str((h or {}).get("version") or "") if isinstance(h, dict) else ""
        try:
            b = html_blocks((folder / "versions" / f"{v}.html").read_text(errors="ignore"), _kept_src("admin-meeting", folder))
        except OSError:
            continue
        revs.append({"v": v, "ts": str(h.get("ts") or "")[:10], "blocks": b[:800]})  # whole versions, so the added and removed counts are true
    if not revs:
        return None
    return {"id": "admin-meeting", "t": "Admin team meeting", "sub": f"the meeting of {datetime.fromisoformat(revs[-1]['ts']).strftime('%-d %b')} · {len(revs)} revisions",
            "revs": revs, "blocks": revs[-1]["blocks"]}


_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
_CHROME = {"script", "style", "aside", "nav", "button", "select", "textarea", "input", "noscript", "svg", "head"}  # a <template> stays: it holds "Earlier updates"
_BLOCK = {"p", "div", "section", "article", "main", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "table", "pre", "figure",
          "img", "blockquote", "details", "summary", "dl", "dt", "dd", "hr", "header", "footer"}


class _Tree(HTMLParser):
    """Published HTML as nested [tag, attrs, children], text as strings and a <br> as \\x01 (a new line)."""

    def __init__(self):
        super().__init__()
        self.root = ["body", {}, []]
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.stack[-1][2].append("\x01")
            return
        e = [tag, {k: v or "" for k, v in attrs}, []]
        self.stack[-1][2].append(e)
        if tag not in _VOID:
            self.stack.append(e)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID and tag != "br":
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):  # an end tag with no open match is ignored
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1][2].append(data)


def _chrome(e: list) -> bool:  # the page's own controls, as Reference's parse drops them (reference.js CHROME)
    a = e[1]
    return e[0] in _CHROME or a.get("id") in ("popover", "legend") or (e[0] == "header" and "hdr" in a.get("class", "").split())


def _text(n) -> str:
    return n if isinstance(n, str) else "" if _chrome(n) else "".join(_text(c) for c in n[2])


def _kids(e: list) -> list:
    return [c for c in e[2] if isinstance(c, list) and not _chrome(c)]


def _find(e: list, tags: set) -> list:
    out = []
    for c in _kids(e):
        out += ([c] if c[0] in tags else []) + _find(c, tags)
    return out


def _rows(tb: list) -> list:
    trs = [r for y in _kids(tb) for r in ([y] if y[0] == "tr" else _kids(y) if y[0] in ("thead", "tbody", "tfoot") else []) if r[0] == "tr"]
    return [[c for c in _kids(r) if c[0] in ("td", "th")] for r in trs]


def _clean(s: str) -> str:
    return re.sub(r"[\s\x01]+", " ", s).strip()


def html_blocks(html: str, pic=None) -> list:
    """A published page's text as the blocks Proto.media.blocks gives Markdown, so every reader draws it the same:
    ['h'|'p'|'li', text], ['pre', text with its line breaks], ['img', address, description, its number from 1] and
    ['tbl', its text, rows, has a header, cells with pictures as ['t', text] and ['img', ...]], as reference.js parse
    reads a plan revision. `pic(src, attrs)` gives a picture's address or '' (then its description says it was not found)."""
    t = _Tree()
    t.feed(html)
    t.close()
    body = next(iter(_find(t.root, {"body"})), t.root)
    out, n = [], 0
    cut = lambda s, k=900: hide(s)[:k]

    def one(e, cap=""):  # ['img', ...] or, with no file, its description
        nonlocal n
        alt = cut(e[1].get("alt") or cap, 300)
        u = pic(e[1].get("src") or "", e[1]) if pic else ""
        if not u:
            return ["t", f"{alt or 'Picture'} (picture not found)"]
        n += 1
        return ["img", u, alt, n]

    def parts(c):  # a cell's parts when it holds a picture; its figure captions are its pictures'
        if not _find(c, {"img"}):
            return None
        ps = []

        def each(x):
            for y in x[2]:
                if isinstance(y, str):
                    if s := _clean(y):
                        ps.append(["t", cut(s)])
                elif _chrome(y) or y[0] == "figcaption":
                    continue
                elif y[0] == "img":
                    ps.append(one(y))
                elif _find(y, {"img"}):
                    each(y)
                elif s := _clean(_text(y)):
                    ps.append(["t", cut(s)])
        each(c)
        return ps

    def walk(e):
        for x in _kids(e):
            tg = x[0]
            if re.fullmatch(r"h[1-6]", tg):
                if s := _clean(_text(x)):
                    out.append(["h", cut(s)])
            elif tg == "table":
                rows = [r for r in _rows(x) if any(_clean(_text(c)) or _find(c, {"img"}) for c in r)]
                r = [[cut(_clean(_text(c))) for c in row] for row in rows]
                cp = [[parts(c) for c in row] for row in rows]
                if r:
                    out.append(["tbl", " ".join(sum(r, [])), r, bool(_find(x, {"th"})), *([cp] if any(p for row in cp for p in row) else [])])
            elif tg == "pre":
                out.append(["pre", hide(_text(x).replace("\x01", "\n")).rstrip("\n")[:20000]])
            elif tg in ("img", "figure"):  # a figure is its pictures, captioned by their description or its caption
                cap = _clean("".join(_text(c) for c in _kids(x) if c[0] == "figcaption"))
                for i in [x] if tg == "img" else _find(x, {"img"}):
                    b = one(i, cap)
                    out.append(b if b[0] == "img" else ["p", b[1]])
            elif tg == "li":
                if s := _clean(_text(["li", {}, [y for y in x[2] if isinstance(y, str) or y[0] not in ("ul", "ol", "table", "pre")]])):
                    out.append(["li", cut(s)])
                for y in _kids(x):
                    if y[0] in ("ul", "ol"):
                        walk(y)
            elif any(y[0] in _BLOCK for y in _kids(x)):
                walk(x)
            else:
                for i in _find(x, {"img"}):
                    b = one(i)
                    out.append(b if b[0] == "img" else ["p", b[1]])
                for s in _text(x).split("\x01"):
                    if s := _clean(s):
                        out.append(["h" if tg in ("dt", "summary") else "p", cut(s)])
    walk(body)
    return out


def _kept_dir(doc: str) -> Path | None:  # read at call time: tests and fixtures point MEETING and USAGE_AUDIT elsewhere
    return {"admin-meeting": MEETING, "usage-audit": USAGE_AUDIT.parent}.get(doc)


def kept_picture(folder: Path | None, rel: str) -> Path | None:
    """A kept document's picture file: under its page's assets/, an image of at most 10 MB as today's release takes, or None."""
    from ..images import IMAGE_SUFFIXES, MAX_IMAGE_BYTES
    parts = Path(rel).parts
    if not folder or len(parts) < 2 or parts[0] != "assets" or any(p.startswith(".") or p == ".." for p in parts):
        return None
    p = folder / rel
    try:
        ok = p.resolve().is_relative_to(folder.resolve()) and p.suffix.lower() in IMAGE_SUFFIXES and p.is_file() and p.stat().st_size <= MAX_IMAGE_BYTES
    except OSError:
        return None
    return p if ok else None


def _kept_src(doc: str, folder: Path):
    """A kept document's picture addresses: its page's own assets, served at proto/kept/<doc>/ (proto_data.serve), with the
    published width and height (#wh=, Proto.media.sized) so its space is kept while it loads; a web or data address as written."""
    import urllib.parse

    def pic(src: str, a: dict) -> str:
        if src.startswith("data:image/") or re.match(r"^https?://", src):
            return src
        rel = urllib.parse.unquote(re.sub(r"^(?:/annotate/reviews/[^/]+/|(?:\.\./)+|\./|/)", "", src.split("#")[0].split("?")[0]))
        f = kept_picture(folder, rel)
        if not f:
            return ""
        url, w, h = f"proto/kept/{doc}/{urllib.parse.quote(rel)}", a.get("width", ""), a.get("height", "")
        return f"{url}#wh={w}x{h}" if w.isdigit() and h.isdigit() and int(w) and int(h) else sized(url, f)
    return pic


def kept() -> list[dict]:
    """The admin meeting, the usage audit's text and the load test's request times; each is left out when its file is missing."""
    m = meeting(MEETING)
    out = [m] if m else []
    try:
        b = html_blocks(USAGE_AUDIT.read_text(errors="ignore"), _kept_src("usage-audit", USAGE_AUDIT.parent))
        if b:
            out.append({"id": "usage-audit", "t": "Usage audit", "sub": "the usage audit page of 6 Nov · from FastLane Drive planning", "blocks": b[:60]})
    except OSError:
        pass
    try:
        km = json.loads((LOAD_TEST / "tiny-summary.json").read_bytes())["metrics"]
        pts = [[f"{w} {s}", round(km[f"http_req_duration{{kind:{k}}}"][p])] for k, w in (("api", "API"), ("web", "Web"))
               for s, p in (("median", "med"), ("p90", "p(90)"), ("p95", "p(95)"))]
        said = [hide(re.sub(r"\*\*", "", ln.strip().lstrip("- ")))[:900] for ln in (LOAD_TEST / "report.md").read_text(errors="ignore").splitlines() if "p95" in ln][:1]
        out.append({"id": "load-test", "t": "Load-test graph", "sub": "k6, eight members · from FastLane Drive planning",
                    "chart": {"t": "Request time in the eight-member sample, in milliseconds", "pts": pts, "gate": 1000,
                              "axis": "k6 summary; it keeps the median, p90 and p95"}, "blocks": [["p", s] for s in said]})
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return out


def _json(path: Path) -> dict:
    try:
        data = json.loads(path.read_bytes())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _home(p: Path) -> str:
    return "~/" + str(p.relative_to(Path.home())) if p.is_relative_to(Path.home()) else str(p)


def _scope(meta: dict) -> tuple[Path | None, Path | None, bool]:
    """(project folder, live page folder, is FastLane Drive). A copy with no recorded source gets no folder at all."""
    if not meta.get("proto_copy_of"):
        return PROJECT, FLD_SOURCE, True
    src = Path(str(meta.get("proto_source") or ""))
    return (src.parents[1], src, False) if meta.get("proto_source") and len(src.parents) > 1 else (None, None, False)


def _why(name: str, folder: Path, source: Path | None = FLD_SOURCE) -> str:
    """Why a page is its own page, so he can choose between them (mock: 'its own page because it is long')."""
    if folder == source:
        return "the live review page this copy was taken from; answers there reach the agents"
    if re.search(r"meeting", name, re.I):
        return "its own page: one meeting's notes, kept apart from the review rounds"
    if re.search(r"roadmap", name, re.I):
        return "its own page because it is long"
    return "its own page, so its rounds stay apart from this one's"


def _page(folder: Path, name: str, url: str, why: str) -> dict:
    hist = _json(folder / "current.meta.json").get("history") or []
    return {"name": name, "url": url, "why": why, "versions": len(hist), "last": str((hist[-1] if hist else {}).get("ts") or "")[:10]}


def _earlier(root: Path | None, modules: list | None) -> list[dict]:
    """Pages this one replaced, as its own "Earlier pages" links name them ("reviews/<slug> → <tab>"): archived, read-only."""
    out = []
    for m in modules or [] if root else []:
        if not (isinstance(m, dict) and m.get("kind") == "links" and re.match(r"earlier pages", str(m.get("title") or ""), re.I)):
            continue
        for it in m.get("items") or []:
            hit = re.search(r"/reviews/([\w.-]+)/", str((it or {}).get("url") or "")) if isinstance(it, dict) else None
            if hit and str(it["url"]).startswith("https://"):
                tab = str(it.get("label") or "").partition("→")[2].strip()
                p = _page(root / "reviews" / hit.group(1), hit.group(1).replace("-", " ").capitalize(), hide(it["url"]),
                          f"read-only: its work moved into this page's {tab or 'tabs'}")
                out.append({"id": hit.group(1), "t": p["name"], "url": p["url"], "why": p["why"], "when": p["last"]})
    return out


def _pages(root: Path | None = PROJECT, source: Path | None = FLD_SOURCE, fld: bool = True, page_dir: Path | None = None) -> list[dict]:
    if root is None:
        return []
    # a copy's Copy library (Rebex's App text) is one of its pages, as in the mock: the row opens it in Reference
    cl = copy_library(page_dir) if page_dir and not fld else None
    lib = [{"name": "Copy library", "ref": cl["id"], "why": f"the app's text, in Reference · {cl['m'].split(' · ')[0]}", "last": cl["d"][:10]}] if cl else []
    pages = {}
    for rec_file in sorted(REGISTRY.glob("*.json")):
        for slug, rec in (_json(rec_file).get("slugs") or {}).items():
            folder = Path(str((rec or {}).get("slug_dir") or ""))
            url = (rec or {}).get("public_url") or (rec or {}).get("url")
            if not url or not folder.is_relative_to(root) or slug in pages or (fld and folder == MEETING):
                continue
            name = _plain(_json(folder / "current.meta.json").get("name") or slug, 80)
            pages[slug] = _page(folder, name, url, _why(name, folder, source))
    out = list(pages.values())
    if not fld:
        return out + lib
    # the delivery roadmap is long, so the mock lists it as its own page; here it opens as Reference's roadmap item
    try:
        when = datetime.fromtimestamp(ROADMAP.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d")
        out.append({"name": "Delivery roadmap", "ref": "delivery-roadmap", "why": _why("roadmap", ROADMAP.parent), "versions": 1, "last": when})
    except OSError:
        pass
    return out


_built: dict = {}  # page dir -> [its own files' stamps, when built, the build]: 0.7-5.5 s a build, and every reload asked (r12 fix10 slowread)
_again = threading.Lock()


def _stamps(page_dir: Path) -> tuple:
    return tuple(_stamp(page_dir / n) for n in ("current.meta.json", "comments.json", "project.json")) + tuple(
        _stamp(m) + (m.parent.name,) for m in sorted((page_dir / "plans").glob("archive-*/meta.json")) if _stamp(m))


def build(page_dir: Path) -> dict:
    """_build, again at once when this page's own files change; the other pages, registry and kept documents it reads
    are read again behind the answer once it is a minute old (up to a minute behind)."""
    page_dir, now = Path(page_dir), time.time()
    stamps, hit = _stamps(page_dir), _built.get(str(page_dir))
    if not hit or hit[0] != stamps:
        hit = _built[str(page_dir)] = [stamps, now, _build(page_dir)]
    elif now - hit[1] > 60 and _again.acquire(blocking=False):
        def again():
            try:
                _built[str(page_dir)] = [stamps, time.time(), _build(page_dir)]
            finally:
                _again.release()
        threading.Thread(target=again, daemon=True).start()
    return hit[2]


def _build(page_dir: Path) -> dict:
    meta = _json(page_dir / "current.meta.json")
    archived = []
    for m in sorted((page_dir / "plans").glob("archive-*/meta.json"), reverse=True):
        pm = _json(m)
        hist = [h for h in pm.get("history") or [] if isinstance(h, dict) and h.get("version")]
        if hist and (m.parent / "versions" / f"{hist[-1]['version']}.html").exists():
            archived.append({"id": m.parent.name, "v": hist[-1]["version"], "t": _plain(pm.get("title") or m.parent.name, 90),
                             "when": str(hist[-1].get("ts") or "")[:10]})

    people = {}
    for c in _comments(page_dir):
        author = str(c.get("author") or "")
        if author.startswith("agent") or not c.get("author_name"):
            continue
        name = _plain(c["author_name"], 60)
        p = people.setdefault(name, {"name": name, "email": MASK, "role": "owner", "seen": ""})
        p["seen"] = max(p["seen"], str(c.get("created_at") or "")[:10])

    proj = _json(page_dir / "project.json")
    root, source, fld = _scope(meta)
    archived += _earlier(root, proj.get("modules"))
    archived.sort(key=lambda a: a["when"], reverse=True)
    board = proj.get("board") or {}
    copy = {"name": "annotate-proto/reviews/" + page_dir.name, "what": "this prototype copy", "path": _home(page_dir)}
    if fld:
        folders = [{"name": "fastlane-drive", "what": "the app's code, on the M1 Max", "path": "~/projects/fastlane-drive"},
                   {"name": "reviews/fld-stack-round8", "what": "the live page's record", "path": "~/projects/fastlane-drive/reviews/fld-stack-round8"}, copy]
    else:  # the project's own git checkouts (one level down) and the live page's record; none when its folder is unknown
        repos = sorted(d for d in root.iterdir() if (d / ".git").exists()) if root and root.is_dir() else []
        folders = [{"name": f"{root.name}/{d.name}", "what": "the project's code, on the M1 Max", "path": _home(d)} for d in repos]
        folders += [{"name": f"reviews/{source.name}", "what": "the live page's record", "path": _home(source)}] if source and source.is_dir() else []
        folders += [copy] if folders else []
    links = [{"name": board.get("label") or "Beads", "what": "the project's task board", "url": board["url"]}] if board.get("url") else []
    # the page's own named links, with their descriptions, as its Documents sidebar shows them; FastLane Drive's Admin and Linear ones
    seen = set()
    for m in proj.get("modules") or []:
        if not (isinstance(m, dict) and m.get("kind") == "links") or re.match(r"earlier pages", str(m.get("title") or ""), re.I):
            continue
        for it in m.get("items") or []:
            url = str((it or {}).get("url") or "") if isinstance(it, dict) else ""
            if url.startswith("https://") and url not in seen and (not fld or re.search(r"^Admin\b|\bLinear\b", str(it.get("label") or ""))):
                seen.add(url)
                links.append({"name": _plain(it.get("label") or url, 90), "what": _plain(it.get("description") or "", 400), "url": hide(url), "ic": "ext"})
    if fld:  # the tester server's address is in no record the prototype reads, so its row says so instead of linking (mock #82)
        links.append({"name": "Tester server", "what": "its address is not in this project's record yet", "url": ""})
    hist = meta.get("history") or []
    return {"name": _plain(meta.get("name") or "This page", 80), "current": meta.get("current") or "",
            "current_t": str((hist[-1] if hist else {}).get("ts") or "")[:16].replace("T", " "),
            "versions": len(hist), "pages": _pages(root, source, fld, page_dir), "archived": archived,
            "folders": folders, "links": links, "people": list(people.values()),
            # kept documents and the folder index are FastLane Drive's files; a copy has none kept on its page
            "kept": kept() if fld else [], "docs": documents() if fld else {"files": [], "groups": {}}, "notes": _kept_notes(page_dir)}


def _kept_notes(page_dir: Path) -> list:
    """Notes on the kept documents and their chart bars; an unreadable comment store shows none rather than breaking the tab."""
    try:
        return [n for n in notes(page_dir) if str(n["a"]).startswith("doc:")]
    except (OSError, ValueError):
        return []
