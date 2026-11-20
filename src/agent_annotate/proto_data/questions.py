"""Questions tab data: this version's questions, your notes on it, earlier answers and the tasks they name.

Reads the page dir only, plus the FastLane Drive bead board read-only. Saving goes through today's API.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from .. import store
from . import scrub

BEAD = re.compile(r"\bFLD-[a-z0-9]+(?:\.\d+)*\b")
# shortcut: the board path is fixed to FastLane Drive's checkout; take it from the project record when other pages use this UI
BOARD = os.environ.get("ANNOTATE_PROTO_BOARD", "/Users/changlee/projects/FastLane Drive/fld-main")
STATE = {"closed": "done", "in_progress": "progress", "blocked": "blocked", "deferred": "none", "open": "waiting"}
_board: dict = {"at": 0.0, "ids": None, "beads": {}}
_board_lock = threading.Lock()


def _mine(author) -> bool:
    return bool(author) and not str(author).startswith("agent")


def _mask(s):
    """Every address, company mailboxes included, and every review key."""
    return scrub(s) if isinstance(s, str) else s


def _beads(ids: set[str]) -> dict:
    """The named tasks, read only; cached a minute, one board read at a time (as Reference does)."""
    if not ids or not Path(BOARD).is_dir():
        return {}
    key = tuple(sorted(ids))
    with _board_lock:
        if _board["ids"] == key and time.time() - _board["at"] <= 60:
            return _board["beads"]
        try:
            out = subprocess.run(["bd", "-C", BOARD, "--readonly", "show", *key, "--json"],
                                 capture_output=True, text=True, timeout=20)
            rows = json.loads(out.stdout or "[]")
        except (OSError, subprocess.TimeoutExpired, ValueError):
            rows = []
        beads = {r["id"]: {"title": _mask(r.get("title", "")), "status": r.get("status", ""),
                           "state": STATE.get(r.get("status"), "none")}
                 for r in rows if isinstance(rows, list) and isinstance(r, dict) and r.get("id")}
        _board.update(at=time.time(), ids=key, beads=beads)
        return beads


def _decision(d):
    if not isinstance(d, dict) or d.get("discarded"):
        return None
    return {k: d.get(k) for k in ("verdict", "text", "option_id", "ts", "round_pending")}


def _all(page_dir: Path) -> list:
    comments = store.read_comments(page_dir)
    # Close (today's archive) moves a card into "archived": it stays in place on the page, closed
    return [c for part in ("anchors", "archived") for cs in (comments.get(part) or {}).values() for c in cs]


def _asked(c, v) -> bool:
    """A question on the Questions tab: this version's, top level, not withdrawn by the agent."""
    return bool(c.get("version") == v and not c.get("parent_id") and c.get("decision_request")
                and not (c.get("status") == "archived" and not _mine(c.get("archived_by"))))


def _flags(c) -> dict:
    d = _decision(c.get("decision"))
    return {"closed": c.get("status") == "archived" and _mine(c.get("archived_by")),
            "later": bool(c.get("answer_later")), "sent": bool(d and not d.get("round_pending"))}


def waiting(page_dir: Path) -> int:
    """Questions waiting on him: the one count the top bar, the tab, Home and every project row use."""
    v = store.read_meta(page_dir).get("current")
    return sum(1 for c in _all(page_dir) if _asked(c, v) and not any(_flags(c).values()))


def build(page_dir: Path) -> dict:
    meta = store.read_meta(page_dir)
    v = meta.get("current")
    allc = _all(page_dir)
    # earlier answers, by the question's words (today's b15 match) and by the agent's item id
    past: dict[str, list] = {}
    for c in allc:
        dr, d = c.get("decision_request"), _decision(c.get("decision"))
        if not dr or not d or c.get("version") == v or d.get("round_pending"):
            continue
        row = {"v": c.get("version"), "t": (d.get("ts") or "")[:10], "q": _mask(dr.get("prompt", "")), "a": _mask((d.get("text") or "").split("\n\n")[0])}
        for key in {"p:" + dr.get("prompt", ""), "o:" + str(c.get("origin_item_id") or "")} - {"o:"}:
            past.setdefault(key, []).append(row)
    qs, notes, ids = [], [], set()
    for c in allc:
        if c.get("version") != v or c.get("parent_id"):
            continue
        dr = c.get("decision_request")
        if not dr:
            if _mine(c.get("author")) and c.get("status") != "archived":
                notes.append({"id": c["id"], "anchor": c.get("anchor_id"), "label": c.get("anchor_label"), "text": c.get("text"),
                              "target": c.get("target"), "sent": bool(c.get("flagged_for_session") or c.get("delivery_id"))})
            continue
        if not _asked(c, v):
            continue  # withdrawn by the agent
        d, f = _decision(c.get("decision")), _flags(c)
        text = json.dumps(dr, ensure_ascii=False)
        named = BEAD.findall(text)
        ids.update(named)
        replies = [{"you": _mine(r.get("author")), "text": _mask(r.get("text", "")), "ts": r.get("ts"),
                    "sent": bool(r.get("sent_at")) or not _mine(r.get("author"))} for r in c.get("replies") or []]
        sent = f["sent"]
        seen, earlier = set(), []
        for key in ("p:" + dr.get("prompt", ""), "o:" + str(c.get("origin_item_id") or "")):
            for row in past.get(key, []):
                if (row["v"], row["q"]) not in seen:
                    seen.add((row["v"], row["q"]))
                    earlier.append(row)
        qs.append({
            "id": c["id"], "n": c.get("number"), "anchor": c.get("anchor_id"), "status": c.get("status"),
            "closed": f["closed"],
            "prompt": _mask(dr.get("prompt") or c.get("text")), "context": _mask(dr.get("context") or ""),
            "options": [{"id": o.get("id"), "label": _mask(o.get("label")), "c": _mask(o.get("consequence") or "")} for o in dr.get("options") or []],
            "rec": dr.get("recommendation"), "impact": dr.get("impact"), "blocking": bool(dr.get("blocking")),
            "evidence": dr.get("evidence") or [], "later": f["later"], "decision": d, "replies": replies,
            "sent": sent, "read": sent and c.get("status") in ("addressed_by_agent", "resolved_in_version"),
            "bead": named[0] if named else None,
            "earlier": sorted(earlier, key=lambda r: r["t"], reverse=True)[:8],
        })
    qs.sort(key=lambda q: q["n"] or 0)
    closed = sum(1 for c in allc if c.get("decision_request") and c.get("status") == "archived")
    return {"version": v, "questions": qs, "notes": notes, "closed": closed,
            "beads": _beads(ids | set(BEAD.findall(_page_text(page_dir, v))))}


def _page_text(page_dir: Path, v) -> str:
    try:
        return (page_dir / "versions" / f"{v}.html").read_text(encoding="utf-8", errors="replace")
    except (OSError, TypeError):
        return ""
