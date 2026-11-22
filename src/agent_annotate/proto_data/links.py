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

from .history import _comments, _plain, _stamp
from . import reference
from .reference import FLD_DIR, _kept_src, copy_library, documents, hide, html_blocks, kept_picture, notes, old_lines, sized

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
    revs, html, ids = [], "", []
    for h in _json(folder / "current.meta.json").get("history") or []:
        v = str((h or {}).get("version") or "") if isinstance(h, dict) else ""
        try:
            t, i = (folder / "versions" / f"{v}.html").read_text(errors="ignore"), []
            b = html_blocks(t, _kept_src("admin-meeting", folder), i)
        except OSError:
            continue
        # whole versions, so the added and removed counts are true; each with its anchors, so a note whose words left the
        # newest revision shows on the newest one that has them, as 2.32.8 opens it (published.Home.older)
        revs.append({"v": v, "ts": str(h.get("ts") or "")[:10], "blocks": b, "ids": i})
        html, ids = t, i
    if not revs:
        return None
    # notes go on the newest revision, so its anchors are the document's; one whose anchor it lacks, on its own revision
    # shortcut: an old line number is read against the newest revision, so a note saved before a later revision lands by its words there
    return {"id": "admin-meeting", "t": "Admin team meeting", "sub": f"the meeting of {datetime.fromisoformat(revs[-1]['ts']).strftime('%-d %b')} · {len(revs)} revisions",
            "revs": revs, "blocks": revs[-1]["blocks"], "ids": ids, "was": old_lines(html, revs[-1]["blocks"], ids)}


def _kept_dir(doc: str, meta: dict | None = None) -> Path | None:
    """The page folder whose assets/ a document's pictures come from: FastLane Drive's kept documents, or a copied project's
    Reference policies page (reference.copied). Read at call time: tests and fixtures point MEETING and USAGE_AUDIT elsewhere."""
    root, _, fld = _scope(meta or {})
    if not fld:
        return root / reference.POLICIES if doc == "policies" and root else None
    return {"admin-meeting": MEETING, "usage-audit": USAGE_AUDIT.parent}.get(doc)


def kept() -> list[dict]:
    """The admin meeting, the usage audit's text and the load test's request times; each is left out when its file is missing."""
    m = meeting(MEETING)
    out = [m] if m else []
    try:
        t, ids = USAGE_AUDIT.read_text(errors="ignore"), []
        b = html_blocks(t, _kept_src("usage-audit", USAGE_AUDIT.parent), ids)
        if b:
            out.append({"id": "usage-audit", "t": "Usage audit", "sub": "the usage audit page of 6 Nov · from FastLane Drive planning", "blocks": b,
                        "ids": ids, "was": old_lines(t, b, ids)})
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
    from .published import signature  # the kept documents' own stores, so a note 2.32.8 saves there shows at once
    return tuple(_stamp(page_dir / n) for n in ("current.meta.json", "comments.json", "project.json")) + tuple(
        _stamp(m) + (m.parent.name,) for m in sorted((page_dir / "plans").glob("archive-*/meta.json")) if _stamp(m)) + signature(page_dir)


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
    kd = kept() if fld else []
    was = {d["id"]: d.pop("was") for d in kd if "was" in d}  # only the published pages: the load test's lines keep their numbers
    return {"name": _plain(meta.get("name") or "This page", 80), "current": meta.get("current") or "",
            "current_t": str((hist[-1] if hist else {}).get("ts") or "")[:16].replace("T", " "),
            "versions": len(hist), "pages": _pages(root, source, fld, page_dir), "archived": archived,
            "folders": folders, "links": links, "people": list(people.values()),
            # kept documents and the folder index are FastLane Drive's files; a copy has none kept on its page
            "kept": kd, "docs": documents() if fld else {"files": [], "groups": {}}, "notes": _kept_notes(page_dir, was)}


def moved(a, was: dict):
    """A kept document's anchor by the twentieth check's line number (doc:kept-<id>~p~<n>) as its words' anchor now
    (doc:kept-<id>~p~<anchor>); one whose words are gone, the whole document's; any other anchor as it is."""
    m = re.fullmatch(r"(doc:kept-([^~]+))~p~(\d+)", str(a or ""))
    if not m or m.group(2) not in was:
        return a
    to = was[m.group(2)].get(m.group(3))
    return f"{m.group(1)}~p~{to}" if to else m.group(1)


def _kept_notes(page_dir: Path, was: dict | None = None) -> list:
    """Notes on the kept documents and their chart bars; an unreadable comment store shows none rather than breaking the tab.
    A note saved on an old line number shows on the same words now; its store record keeps its anchor until it is moved."""
    try:
        out = [n for n in notes(page_dir) if str(n["a"]).startswith("doc:")]
    except (OSError, ValueError):
        return []
    for n in out:
        n["a"], n["ra"] = moved(n["a"], was or {}), moved(n.get("ra"), was or {})
    return out
