"""Questions tab data: this version's questions, your notes on it, earlier answers and the tasks they name.

Reads the page dir only, plus the FastLane Drive bead board read-only. Saving goes through today's API.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from .. import store

BEAD = re.compile(r"\bFLD-[a-z0-9]+(?:\.\d+)*\b")
# shortcut: the board path is fixed to FastLane Drive's checkout; take it from the project record when other pages use this UI
BOARD = os.environ.get("ANNOTATE_PROTO_BOARD", "/Users/changlee/projects/FastLane Drive/fld-main")
STATE = {"closed": "done", "in_progress": "progress", "blocked": "blocked", "deferred": "none", "open": "waiting"}
# personal addresses only: the company's own (support@fastlanedrive.com) are what a question is about
EMAIL = re.compile(r"[\w.+-]+@(?!fastlanedrive\.com\b)[a-z][\w-]*(?:\.[\w-]+)*\.[a-z]{2,}\b", re.I)


def _mine(author) -> bool:
    return bool(author) and not str(author).startswith("agent")


def _mask(s):
    return EMAIL.sub("member@example.com", s) if isinstance(s, str) else s


def _beads(ids: set[str]) -> dict:
    if not ids or not Path(BOARD).is_dir():
        return {}
    try:
        out = subprocess.run(["bd", "-C", BOARD, "--readonly", "show", *sorted(ids), "--json"],
                             capture_output=True, text=True, timeout=20)
        rows = json.loads(out.stdout or "[]")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {}
    if not isinstance(rows, list):
        return {}
    return {r["id"]: {"title": _mask(r.get("title", "")), "status": r.get("status", ""),
                      "state": STATE.get(r.get("status"), "none")} for r in rows if isinstance(r, dict) and r.get("id")}


def _decision(d):
    if not isinstance(d, dict) or d.get("discarded"):
        return None
    return {k: d.get(k) for k in ("verdict", "text", "option_id", "ts", "round_pending")}


def build(page_dir: Path) -> dict:
    meta = store.read_meta(page_dir)
    v = meta.get("current")
    comments = store.read_comments(page_dir)
    # Close (today's archive) moves a card into "archived": it stays in place on the page, closed
    allc = [c for part in ("anchors", "archived") for cs in (comments.get(part) or {}).values() for c in cs]
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
        if c.get("status") == "archived" and not _mine(c.get("archived_by")):
            continue  # withdrawn by the agent
        d = _decision(c.get("decision"))
        text = json.dumps(dr, ensure_ascii=False)
        named = BEAD.findall(text)
        ids.update(named)
        replies = [{"you": _mine(r.get("author")), "text": _mask(r.get("text", "")), "ts": r.get("ts"),
                    "sent": bool(r.get("sent_at")) or not _mine(r.get("author"))} for r in c.get("replies") or []]
        sent = bool(d and not d.get("round_pending"))
        seen, earlier = set(), []
        for key in ("p:" + dr.get("prompt", ""), "o:" + str(c.get("origin_item_id") or "")):
            for row in past.get(key, []):
                if (row["v"], row["q"]) not in seen:
                    seen.add((row["v"], row["q"]))
                    earlier.append(row)
        qs.append({
            "id": c["id"], "n": c.get("number"), "anchor": c.get("anchor_id"), "status": c.get("status"),
            "closed": c.get("status") == "archived" and _mine(c.get("archived_by")),
            "prompt": _mask(dr.get("prompt") or c.get("text")), "context": _mask(dr.get("context") or ""),
            "options": [{"id": o.get("id"), "label": _mask(o.get("label")), "c": _mask(o.get("consequence") or "")} for o in dr.get("options") or []],
            "rec": dr.get("recommendation"), "impact": dr.get("impact"), "blocking": bool(dr.get("blocking")),
            "evidence": dr.get("evidence") or [], "later": bool(c.get("answer_later")), "decision": d, "replies": replies,
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
