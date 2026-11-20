"""Pages & links tab data: this project's pages, archived snapshots, repos and folders, and the People list.

Read-only. The dummy page is a copy of FastLane Drive's page, so the project's other pages come from the
live page registry (read only) for pages kept under the FastLane Drive folder. Emails are always masked.
"""

from __future__ import annotations

import json
from pathlib import Path

from .history import _comments, _plain

PROJECT = Path.home() / "projects" / "fastlane-drive"  # where the dummy page was copied from
REGISTRY = Path.home() / ".claude" / "annotate-state" / "state"  # live page records, read only
MASK = "member@example.com"


def _json(path: Path) -> dict:
    try:
        data = json.loads(path.read_bytes())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


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
            pages[slug] = {"name": _plain(meta.get("name") or slug, 80), "url": url,
                           "versions": len(hist), "last": str((hist[-1] if hist else {}).get("ts") or "")[:10]}
    return list(pages.values())


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
    return {"name": _plain(meta.get("name") or "This page", 80), "current": meta.get("current") or "",
            "versions": len(meta.get("history") or []), "pages": _pages(), "archived": archived,
            "folders": folders, "links": links, "people": list(people.values())}
