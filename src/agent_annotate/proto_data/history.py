"""History tab data: every answer sent on this page, by version, plus withdrawn questions and Reference changes.

Read-only, from the page's own record: rounds.ndjson, comments.json, current.meta.json and plans/*/meta.json.
Emails never leave this module: no "by" fields are sent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# The agent's words for "your answer no longer stands"; all show under one "overruled" tag (#117).
_SYN = re.compile(r"\b(overrul\w*|supersed\w*|supercede\w*|overridden|overrides?)\b|(?:^|[.!?]\s+)(replaced) by", re.I)
_WORD = (("overrul", "overruled"), ("supersed", "superseded"), ("superced", "superseded"),
         ("overrid", "overridden"), ("replac", "replaced"))


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _plain(text, n=200) -> str:
    text = _EMAIL.sub("member@example.com", re.sub(r"<[^>]+>", "", str(text or "")))
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _lines(path: Path):
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    out = []
    for line in raw.splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:  # a line mid-write or cut short
            continue
    return [x for x in out if isinstance(x, dict)]


def _comments(page_dir: Path) -> list[dict]:
    try:
        store = json.loads((page_dir / "comments.json").read_bytes())
    except (OSError, ValueError):
        return []
    out = []
    for bucket in ("anchors", "archived"):
        groups = store.get(bucket) or {}
        for items in (groups.values() if isinstance(groups, dict) else [groups]):
            out.extend(c for c in items if isinstance(c, dict) and c.get("id"))
    return out


def overruled(comment: dict):
    """[word, what the agent wrote] when the agent said the answer no longer stands, else None."""
    if (comment.get("decision") or {}).get("catalog_conflict"):
        return ["overruled", "A newer plan decision is current."]
    agent = lambda a: str(a or "").startswith("agent")
    texts = [comment.get("response_text") or ""]
    texts += [r.get("text") or "" for r in comment.get("replies") or [] if isinstance(r, dict) and agent(r.get("author"))]
    if agent(comment.get("author")):
        texts.append(comment.get("text") or "")
    for text in texts:
        m = _SYN.search(text)
        if m:
            w = (m.group(1) or m.group(2)).lower()
            word = next(v for k, v in _WORD if w.startswith(k))
            return [word, _plain(text[max(0, m.start() - 90): m.end() + 90], 240)]
    return None


def build(page_dir: Path) -> dict:
    page_dir = Path(page_dir)
    meta = json.loads((page_dir / "current.meta.json").read_bytes())
    comments = _comments(page_dir)
    by_id = {c["id"]: c for c in comments}
    ovr = {cid: o for cid, c in by_id.items() if (o := overruled(c))}
    # the same question asked again on a later version carries the agent's word back to the earlier answer
    ovr_q = {_plain((by_id[cid].get("decision_request") or {}).get("prompt") or by_id[cid].get("text"), 220): o
             for cid, o in ovr.items()}

    rounds = sorted(_lines(page_dir / "rounds.ndjson"), key=lambda r: str(r.get("ts") or ""))
    answers, count, seen = [], 0, set()
    for r in rounds:
        for a in r.get("answers") or []:
            if not isinstance(a, dict):
                continue
            count += 1
            q = _plain(a.get("prompt") or "General feedback", 220)
            text = _plain(str(a.get("text") or a.get("verdict") or "").split("\n")[0], 220)
            key = (r.get("id"), q, text)
            if key in seen:  # the same answer twice in one Send is listed once
                continue
            seen.add(key)
            answers.append({"n": a.get("number") or 0, "q": q, "a": text, "v": r.get("version") or "",
                            "t": str(a.get("ts") or r.get("ts") or "")[:10], "ovr": ovr.get(a.get("comment_id")) or ovr_q.get(q)})
    answers.reverse()  # newest first

    items, open_items = {}, {}
    for c in comments:
        v = c.get("version") or ""
        items[v] = items.get(v, 0) + 1
        open_items[v] = open_items.get(v, 0) + (c.get("status") == "open")
    hist = [h for h in meta.get("history") or [] if isinstance(h, dict) and h.get("version")]
    versions = {h["version"]: {"t": str(h.get("ts") or "")[:10], "note": _plain(h.get("label"), 200),
                               "items": items.get(h["version"], 0), "open": open_items.get(h["version"], 0)}
                for h in hist}

    withdrawn = []
    for c in sorted(comments, key=lambda c: str((c.get("withdrawn") or {}).get("ts") or ""), reverse=True):
        w = c.get("withdrawn")
        if not isinstance(w, dict):
            continue
        dr = w.get("decision_request") or c.get("decision_request") or {}
        withdrawn.append({"n": c.get("number") or 0, "v": c.get("version") or "", "t": str(w.get("ts") or "")[:10],
                          "q": _plain(dr.get("prompt") or c.get("text"), 220), "why": _plain(w.get("reason"), 220)})

    plans = []
    for m in sorted((page_dir / "plans").glob("*/meta.json")):
        if m.parent.name.startswith("archive-"):
            continue
        try:
            pm = json.loads(m.read_bytes())
        except (OSError, ValueError):
            continue
        revs = [[h.get("version"), str(h.get("ts") or "")[:10], _plain(h.get("label"), 120)]
                for h in pm.get("history") or [] if isinstance(h, dict) and h.get("version")]
        if revs:
            plans.append({"id": m.parent.name, "t": _plain(pm.get("title") or m.parent.name, 100), "revs": revs})

    return {"current": meta.get("current") or "", "count": count, "sends": len(rounds), "answers": answers,
            "versions": versions, "withdrawn": withdrawn, "plans": plans}
