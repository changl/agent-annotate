"""Pages & links tab data: this project's pages, archived snapshots, repos and folders, and the People list.

Read-only. The dummy page is a copy of FastLane Drive's page, so the project's other pages come from the
live page registry (read only) for pages kept under the FastLane Drive folder. Emails are always masked.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import re
from html.parser import HTMLParser

from .history import _comments, _plain
from .reference import FLD_DIR, documents, hide, notes

PROJECT = Path.home() / "projects" / "fastlane-drive"  # where the dummy page was copied from
REGISTRY = Path.home() / ".claude" / "annotate-state" / "state"  # live page records, read only
MASK = "member@example.com"
# documents kept on this page (mock round 9): the usage audit page and the go-live load test's k6 summary
USAGE_AUDIT = FLD_DIR / "planning/operations/usage-audit-2026-11-06/page/current.html"
LOAD_TEST = FLD_DIR / "planning/operations/orchestration/run_d169910aea33/reports/go-live-backend-2"
ROADMAP = FLD_DIR / "planning/05-roadmap.md"


class _Blocks(HTMLParser):
    """Headings, paragraphs, list items and table cells of an HTML page, as [kind, text]; scripts and styles skipped."""
    KEEP = {"h1": "h", "h2": "h", "h3": "h", "h4": "h", "p": "p", "li": "li", "td": "p", "pre": "pre"}

    def __init__(self):
        super().__init__()
        self.out, self.kind, self.buf, self.skip = [], None, [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in self.KEEP:
            self._flush()
            self.kind = self.KEEP[tag]

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.KEEP:
            self._flush()

    def handle_data(self, data):
        if self.kind and not self.skip:
            self.buf.append(data)

    def _flush(self):
        t = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if self.kind and t:
            self.out.append([self.kind, hide(t)[:900]])
        self.kind, self.buf = None, []


def kept() -> list[dict]:
    """The usage audit's text and the load test's request times; each is left out when its file is missing."""
    out = []
    try:
        b = _Blocks()
        b.feed(USAGE_AUDIT.read_text(errors="ignore"))
        if b.out:
            out.append({"id": "usage-audit", "t": "Usage audit", "sub": "the usage audit page of 6 Nov · from FastLane Drive planning", "blocks": b.out[:60]})
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


def _why(name: str, folder: Path) -> str:
    """Why a page is its own page, so he can choose between them (mock: 'its own page because it is long')."""
    if folder.name == "fld-stack-round8":
        return "the live review page this copy was taken from; answers there reach the agents"
    if re.search(r"meeting", name, re.I):
        return "its own page: one meeting's notes, kept apart from the review rounds"
    if re.search(r"roadmap", name, re.I):
        return "its own page because it is long"
    return "its own page, so its rounds stay apart from this one's"


def _pages() -> list[dict]:
    pages = {}
    for rec_file in sorted(REGISTRY.glob("*.json")):
        for slug, rec in (_json(rec_file).get("slugs") or {}).items():
            folder = Path(str((rec or {}).get("slug_dir") or ""))
            url = (rec or {}).get("public_url") or (rec or {}).get("url")
            if not url or not folder.is_relative_to(PROJECT) or slug in pages:
                continue
            meta = _json(folder / "current.meta.json")
            hist = meta.get("history") or []
            name = _plain(meta.get("name") or slug, 80)
            pages[slug] = {"name": name, "url": url, "why": _why(name, folder),
                           "versions": len(hist), "last": str((hist[-1] if hist else {}).get("ts") or "")[:10]}
    out = list(pages.values())
    # the delivery roadmap is long, so the mock lists it as its own page; here it opens as Reference's roadmap item
    try:
        when = datetime.fromtimestamp(ROADMAP.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d")
        out.append({"name": "Delivery roadmap", "ref": "delivery-roadmap", "why": _why("roadmap", ROADMAP.parent), "versions": 1, "last": when})
    except OSError:
        pass
    return out


def build(page_dir: Path) -> dict:
    page_dir = Path(page_dir)
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

    archived.sort(key=lambda a: a["when"], reverse=True)
    board = _json(page_dir / "project.json").get("board") or {}
    folders = [{"name": "fastlane-drive", "what": "the app's code, on the M1 Max", "path": "~/projects/fastlane-drive"},
               {"name": "reviews/fld-stack-round8", "what": "the live page's record", "path": "~/projects/fastlane-drive/reviews/fld-stack-round8"},
               {"name": "annotate-proto/reviews/fld-proto", "what": "this prototype copy", "path": "~/" + str(page_dir.relative_to(Path.home())) if page_dir.is_relative_to(Path.home()) else str(page_dir)}]
    links = [{"name": board.get("label") or "Beads", "what": "the project's task board", "url": board["url"]}] if board.get("url") else []
    # the live page's named Admin and Linear links, with their descriptions, as its Documents sidebar shows them
    for m in _json(page_dir / "project.json").get("modules") or []:
        for it in (m.get("items") or []) if isinstance(m, dict) and m.get("kind") == "links" else []:
            if isinstance(it, dict) and str(it.get("url") or "").startswith("https://") and re.search(r"^Admin\b|\bLinear\b", str(it.get("label") or "")):
                links.append({"name": _plain(it["label"], 90), "what": _plain(it.get("description") or "", 400), "url": hide(it["url"]), "ic": "ext"})
    # the tester server's address is in no record the prototype reads, so its row says so instead of linking (mock #82)
    links.append({"name": "Tester server", "what": "its address is not in this project's record yet", "url": ""})
    hist = meta.get("history") or []
    return {"name": _plain(meta.get("name") or "This page", 80), "current": meta.get("current") or "",
            "current_t": str((hist[-1] if hist else {}).get("ts") or "")[:16].replace("T", " "),
            "versions": len(hist), "pages": _pages(), "archived": archived,
            "folders": folders, "links": links, "people": list(people.values()),
            "kept": kept(), "docs": documents(), "notes": _kept_notes(page_dir)}


def _kept_notes(page_dir: Path) -> list:
    """Notes on the kept documents and their chart bars; an unreadable comment store shows none rather than breaking the tab."""
    try:
        return [n for n in notes(page_dir) if str(n["a"]).startswith("doc:")]
    except (OSError, ValueError):
        return []
