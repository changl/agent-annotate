"""Questions tab data: this version's questions, your notes on it, earlier answers and the tasks they name.

Reads the page dir only, plus the FastLane Drive bead board read-only. Saving goes through today's API.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from .. import store
from . import scrub

BEAD = re.compile(r"\bFLD-[a-z0-9]+(?:\.\d+)*\b")
# shortcut: the board path is fixed to FastLane Drive's checkout; take it from the project record when other pages use this UI
BOARD = os.environ.get("ANNOTATE_PROTO_BOARD", "/Users/changlee/projects/FastLane Drive/fld-main")
STATE = {"closed": "done", "in_progress": "progress", "blocked": "blocked", "deferred": "none", "open": "waiting"}
_board: dict = {"at": 0.0, "asked": set(), "beads": {}, "busy": False}
_board_lock = threading.Lock()  # guards _board
_read_lock = threading.Lock()  # one board read at a time
SNAP = "proto-qbeads.json"  # the last board read, so a restarted server answers at once too


def _mine(author) -> bool:
    return bool(author) and not str(author).startswith("agent")


def _mask(s):
    """Every address, company mailboxes included, and every review key."""
    return scrub(s) if isinstance(s, str) else s


def author_key(author) -> str:
    """Who wrote a note, as a token: every address is masked on the page, so each read swaps the reader's own tokens
    for `true` (proto_data.own), and the kit offers Edit and Remove on his own notes alone (shell.js isMine)."""
    return "u" + hashlib.sha256(("proto-author\0" + str(author or "")).encode()).hexdigest()[:12]


def own(body: bytes, authors) -> bytes:
    """A feed as one reader sees it: his notes' `by` is true. The feed is built once for every reader."""
    if b'"by": "u' not in body:
        return body
    for a in authors:
        body = body.replace(b'"by": "' + author_key(a).encode() + b'"', b'"by": true')
    return body


def was_sent(c: dict) -> bool:
    """A Send took it once. Today's edit clears flagged_for_session (it goes with the next Send) but keeps flagged_at."""
    return bool(c.get("flagged_for_session") or c.get("delivery_id") or c.get("flagged_at"))


def _reply_unsent(c: dict, r: dict) -> bool:
    """His reply not yet delivered: the server's _note_unsent (sent_at, else after the last Send)."""
    if not _mine(r.get("author")):
        return False
    if "sent_at" in r:
        return not r["sent_at"]
    stamp = lambda v: datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp() if v else 0.0
    try:
        return stamp(r.get("ts")) > stamp(c.get("flagged_at"))
    except ValueError:
        return False


def note_thread(c: dict) -> dict:
    """A note's fields for today's Edit, Post reply and Resolve (shell.js canEditComment, showReply, cardMenuItems):
    edited after its last Send (it goes with the next one, as _comment_needs_push counts edited_at), the agent's
    response and the replies under it."""
    stamp = lambda v: datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp() if v else 0.0
    sent = was_sent(c)
    try:
        edited = sent and _mine(c.get("edited_by") or c.get("author")) and stamp(c.get("edited_at")) > stamp(c.get("flagged_at"))
    except ValueError:
        edited = False

    unsent = lambda r: _reply_unsent(c, r)
    # by: who wrote it (author_key); ag: the agent did, so the reply box shows from the start (showReply's agentResponded);
    # flagged and rp: today's canDeleteComment, which an edit re-opens by clearing flagged_for_session
    # ed.by and each reply's by: who made the edit (any PUT: words, Re-open, Move) and who wrote the reply, since the
    # server's round takes each by its own author, not the note's (_comment_needs_push) (r12 audit25 running 1)
    return {"edited": edited, "mine": _mine(c.get("author")), "by": author_key(c.get("author")), "ag": str(c.get("author") or "").startswith("agent:"),
            "ed": {"by": author_key(c.get("edited_by") or c.get("author"))},
            "flagged": bool(c.get("flagged_for_session")), "rp": bool(c.get("round_pending")), "resp": _mask(c.get("response_text") or ""),
            "replies": [{"agent": not _mine(r.get("author")), "who": r.get("author_name") or ("Agent" if not _mine(r.get("author")) else "You"),
                         "text": _mask(r.get("text") or ""), "ts": r.get("ts"), "unsent": unsent(r), "by": author_key(r.get("author"))}
                        for r in c.get("replies") or [] if isinstance(r, dict)]}


def _read(ids: set[str]) -> dict | None:
    """One `bd show` of the named tasks, read only. It takes 2-10 s, so no request waits on it after the first (r12 fix10 slowread)."""
    try:
        out = subprocess.run(["bd", "-C", BOARD, "--readonly", "show", *sorted(ids), "--json"],
                             capture_output=True, text=True, timeout=20)
        rows = json.loads(out.stdout or "[]")
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    return {r["id"]: {"title": _mask(r.get("title", "")), "status": r.get("status", ""),
                      "state": STATE.get(r.get("status"), "none")}
            for r in rows if isinstance(rows, list) and isinstance(r, dict) and r.get("id")}


def _store(page_dir: Path, ids: set[str], got: dict | None) -> None:
    with _board_lock:
        if got is not None:
            if any(_board["beads"].get(k) != v for k, v in got.items()):
                _board["n"] = _board.get("n", 0) + 1  # the tasks changed: stamp() reads this
            _board["beads"] = {**_board["beads"], **got}
        _board["asked"] = _board["asked"] | ids
        _board["at"] = time.time()
        snap = json.dumps({"asked": sorted(_board["asked"]), "beads": _board["beads"]}, ensure_ascii=False)
    try:
        tmp = page_dir / (SNAP + ".tmp")
        tmp.write_text(snap)
        tmp.replace(page_dir / SNAP)
    except OSError:
        pass


def _refresh(page_dir: Path, ids: set[str]) -> None:
    try:
        with _read_lock:
            _store(page_dir, ids, _read(ids))
    finally:
        with _board_lock:
            _board["busy"] = False


def _beads(ids: set[str], page_dir: Path) -> dict:
    """The named tasks, read only. The last read answers at once; past a minute a new one runs in the background and
    the next read shows it (as Running does). Only tasks no read has asked about yet wait for the board."""
    if not ids or not Path(BOARD).is_dir():
        return {}
    if not _board["asked"]:  # a restarted server starts from the last read it saved
        try:
            snap, at = json.loads((page_dir / SNAP).read_text()), (page_dir / SNAP).stat().st_mtime
            with _board_lock:
                if not _board["asked"]:
                    _board.update(asked=set(snap["asked"]), beads=dict(snap["beads"]), at=at)
        except (OSError, ValueError, KeyError, TypeError):
            pass
    with _board_lock:
        missing = ids - _board["asked"]
        start = not missing and not _board["busy"] and time.time() - _board["at"] > 60
        if start:
            _board["busy"] = True
    if missing:  # the first read, or a version naming new tasks
        with _read_lock:
            if ids - _board["asked"]:
                _store(page_dir, missing, _read(missing))
    elif start:
        threading.Thread(target=_refresh, args=(page_dir, ids), daemon=True).start()
    with _board_lock:
        return {i: _board["beads"][i] for i in ids if i in _board["beads"]}


def _decision(d):
    if not isinstance(d, dict) or d.get("discarded"):
        return None
    # via and mine: a pending answer or card reply written by a round that then failed is his Send row on any reload (r12 audit36)
    return {**{k: d.get(k) for k in ("verdict", "text", "option_id", "ts", "round_pending", "via")}, "mine": _mine(d.get("by"))}


_all_cache: dict = {}  # page dir -> (comments.json's stamp, its cards): FastLane Drive's is 17 MB, 0.6 s to parse each read


def _all(page_dir: Path) -> list:
    try:
        st = (page_dir / "comments.json").stat()
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        stamp = None
    got = _all_cache.get(str(page_dir))
    if stamp and got and got[0] == stamp:
        return got[1]
    comments = store.read_comments(page_dir)
    # Close (today's archive) moves a card into "archived": it stays in place on the page, closed
    cards = [c for part in ("anchors", "archived") for cs in (comments.get(part) or {}).values() for c in cs]
    if stamp:
        _all_cache[str(page_dir)] = (stamp, cards)
    return cards


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
    # his answer pending in the store (a failed round wrote it) is answered, as Questions' groups count it (r12 audit37 questions 5)
    pend = lambda c: (d := _decision(c.get("decision"))) and d.get("round_pending") and d["mine"]
    return sum(1 for c in _all(page_dir) if _asked(c, v) and not any(_flags(c).values()) and not pend(c))


STOP = set("the a an to of and or for on in is be it this that with as at by from what who how should do does run".split())


def _words(s) -> set:
    return {w for w in re.findall(r"[a-z]{3,}", str(s or "").lower()) if w not in STOP}


TAG = re.compile(r"<[^>]+>")
SEC = re.compile(r'<section data-anchor-id="([^"]+)">(.*?)</section>', re.S)
_secs_cache: dict = {}


def _sections(page_dir: Path, v) -> dict:
    """{top section anchor: its words}, for one version; cached by file."""
    f = page_dir / "versions" / f"{v}.html"
    try:
        key = (str(f), f.stat().st_mtime)
    except OSError:
        return {}
    if key not in _secs_cache:
        h = f.read_text(encoding="utf-8", errors="replace")
        _secs_cache[key] = {a: " ".join(TAG.sub(" ", b).split()) for a, b in SEC.findall(h)}
    return _secs_cache[key]


def _since(page_dir: Path, meta: dict, v) -> dict:
    """Each top section: "" when new or changed in this version, else the oldest version it is unchanged since (40 back at most)."""
    vs = [h.get("version") for h in meta.get("history") or [] if h.get("version")]
    if v not in vs:
        return {}
    i, now, out = vs.index(v), _sections(page_dir, v), {}
    for a, t in now.items():
        since = ""
        for pv in reversed(vs[max(0, i - 40):i]):
            if _sections(page_dir, pv).get(a) != t:
                break
            since = pv
        out[a] = since
    return out


def _table_beads(html: str) -> dict:
    """The page's tracking tables: a row linking question N and naming FLD ids gives N its task."""
    out: dict = {}
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        ns, ids = re.findall(r'href="#d:q(\d+)"', row), BEAD.findall(row)
        for n in ns if ids else []:
            out.setdefault(int(n), ids[0])
    return out


_named: dict = {}  # page dir -> the task ids its last build named


def stamp(page_dir: Path) -> tuple:
    """What build() reads: when none of it changed, the last answer is sent again as it was (proto_data.prepared, r12 fix12 perf).
    Earlier versions' files never change once published; the board's minute read still starts behind, as in build()."""
    page_dir = Path(page_dir)
    if _named.get(str(page_dir)):
        _beads(_named[str(page_dir)], page_dir)
    out = []
    for f in ("current.meta.json", "comments.json", "rounds.ndjson", CARRIED):
        try:
            st = (page_dir / f).stat()
            out.append((st.st_mtime_ns, st.st_size))
        except OSError:
            out.append(None)
    return (*out, _board.get("n", 0))


def build(page_dir: Path) -> dict:
    meta = store.read_meta(page_dir)
    v = meta.get("current")
    allc = _all(page_dir)
    # earlier answers, by the question's words (today's b15 match) and by the agent's item id
    past: dict[str, list] = {}
    rows: list = []
    for c in allc:
        dr, d = c.get("decision_request"), _decision(c.get("decision"))
        if not dr or not d or c.get("version") == v or d.get("round_pending"):
            continue
        row = {"v": c.get("version"), "t": (d.get("ts") or "")[:10], "q": _mask(dr.get("prompt", "")), "a": _mask((d.get("text") or "").split("\n\n")[0])}
        rows.append((row, _words(dr.get("prompt"))))
        for key in {"p:" + dr.get("prompt", ""), "o:" + str(c.get("origin_item_id") or "")} - {"o:"}:
            past.setdefault(key, []).append(row)
    page = _page_text(page_dir, v)
    tbeads = _table_beads(page)
    qs, notes, ids = [], [], set()
    for c in allc:
        if c.get("version") != v or c.get("parent_id"):
            continue
        dr = c.get("decision_request")
        if not dr:
            # every note, the agent's own and other reviewers' too, as today's page lists them (r12 audit19 questions 8);
            # closed (today's archive) notes come too, for Closed and Re-open; a resolved one names where the agent addressed it
            notes.append({"id": c["id"], "anchor": c.get("anchor_id"), "label": c.get("anchor_label"), "text": c.get("text"),
                          "target": c.get("target"), "sent": was_sent(c) or not _mine(c.get("author")),
                          "at": c.get("created_at"), "status": c.get("status"), "closed": c.get("status") == "archived",
                          "rv": c.get("resolved_in_version"), "ra": c.get("resolution_anchor_id"), **note_thread(c)})
            continue
        if not _asked(c, v):
            continue  # withdrawn by the agent
        d, f = _decision(c.get("decision")), _flags(c)
        text = json.dumps(dr, ensure_ascii=False)
        named = BEAD.findall(text)
        ids.update(named)
        # dec: the decision route's own thread line, written at one of the card's decisions (same ts and author) in that
        # route's form; a reply he typed is never told by its opening characters (r12 audit37 frame 2)
        from ..sync_server import _GENERATED_REPLY
        made = {(h.get("ts"), h.get("by")) for h in [c.get("decision"), *(c.get("decision_history") or [])] if isinstance(h, dict)}
        replies = [{"you": _mine(r.get("author")), "text": _mask(r.get("text", "")), "ts": r.get("ts"),
                    "dec": (r.get("ts"), r.get("author")) in made and bool(_GENERATED_REPLY.match(str(r.get("text", "")))),
                    "sent": not _reply_unsent(c, r)} for r in c.get("replies") or [] if isinstance(r, dict)]
        sent = f["sent"]
        seen, earlier = set(), []
        w = _words(dr.get("prompt"))
        # the same topic: three words in common (two for a short question), closest first, four at most
        hits = [(len(rw & w), r["t"], i) for i, (r, rw) in enumerate(rows) if len(rw & w) >= min(3, max(2, len(w) // 2))]
        topic = [rows[i][0] for _, _, i in sorted(hits, reverse=True)[:4]]
        for row in [r for key in ("p:" + dr.get("prompt", ""), "o:" + str(c.get("origin_item_id") or "")) for r in past.get(key, [])] + topic:
            if (row["v"], row["q"]) not in seen:
                seen.add((row["v"], row["q"]))
                earlier.append(row)
        ev = dr.get("evidence") or []
        bead = (named[0] if named else None) or tbeads.get(c.get("number"))
        if bead:
            ids.add(bead)
        # a question in "Blocked items" or holding a task on the board blocks work (the mock's mark, by section)
        blocking = bool(dr.get("blocking")) or any(str(e.get("anchor", "")).startswith("s:blocked") for e in ev if isinstance(e, dict))
        qs.append({
            "id": c["id"], "n": c.get("number"), "anchor": c.get("anchor_id"), "status": c.get("status"),
            "closed": f["closed"],
            "prompt": _mask(dr.get("prompt") or c.get("text")), "context": _mask(dr.get("context") or ""),
            "options": [{"id": o.get("id"), "label": _mask(o.get("label")), "c": _mask(o.get("consequence") or "")} for o in dr.get("options") or []],
            "rec": dr.get("recommendation"), "impact": dr.get("impact"), "blocking": blocking,
            "evidence": ev, "later": f["later"], "decision": d, "replies": replies,
            "sent": sent, "read": sent and c.get("status") in ("addressed_by_agent", "resolved_in_version"),
            "bead": bead,
            # his own earlier picks on this card, a sent answer he changed (decision_history), first
            "earlier": [{"v": c.get("version"), "t": str(h.get("ts") or "")[:10], "q": _mask(dr.get("prompt", "")),
                         "a": _mask((h.get("text") or "").split("\n\n")[0]), "own": True}
                        for h in reversed(c.get("decision_history") or []) if isinstance(h, dict) and not h.get("discarded") and h.get("text")][:4]
                       + sorted(earlier, key=lambda r: r["t"], reverse=True)[:8],
            # the agent's last word on it: new activity until he opens the card
            "act": max((r.get("ts") or "" for r in c.get("replies") or [] if not _mine(r.get("author"))), default=None),
        })
    qs.sort(key=lambda q: q["n"] or 0)
    closed = sum(1 for c in allc if c.get("decision_request") and c.get("status") == "archived")
    _named[str(page_dir)] = ids = ids | set(BEAD.findall(page))
    beads = _beads(ids, page_dir)
    for q in qs:  # a task the board says is blocked waits on this answer too
        q["blocking"] = q["blocking"] or (beads.get(q["bead"]) or {}).get("state") == "blocked"
    notes_all = [c for c in allc if not c.get("decision_request") and not c.get("parent_id") and _mine(c.get("author"))]
    tiles = {"versions": len(meta.get("history") or []),
             "open": sum(1 for c in notes_all if c.get("status") == "open"),
             "addressed": sum(1 for c in notes_all if c.get("status") in ("addressed_by_agent", "resolved_in_version", "user_confirmed")),
             "sends": _count_lines(page_dir / "rounds.ndjson")}
    # when this answer was read: a saved note newer than it is kept though this answer lacks it (r12 audit14 questions 1, running 1)
    at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"version": v, "at": at, "questions": qs, "notes": notes, "closed": closed, "beads": beads,
            "done": len(rows), "tiles": tiles, "since": _since(page_dir, meta, v), "carried": _carried(page_dir, notes_all, v, page),
            "pics": carried_pictures(page_dir)}


def _count_lines(f: Path) -> int:
    try:
        with f.open(encoding="utf-8", errors="replace") as fh:
            return sum(1 for line in fh if line.strip())
    except OSError:
        return 0


def _anchor_text(html: str, anchor) -> str | None:
    m = re.search(r'<(\w+)[^>]*data-anchor-id="%s"[^>]*>(.*?)</\1>' % re.escape(str(anchor)), html, re.S)
    return " ".join(TAG.sub(" ", m.group(2)).split()) if m else None


def _carried(page_dir: Path, notes_all: list, v, page: str) -> list:
    """His open notes from earlier versions whose line is still in this one; changed when the line's text differs."""
    out = []
    for c in notes_all:
        if c.get("status") != "open" or c.get("version") == v:
            continue
        anchor = c.get("carried_to_anchor_id") or c.get("anchor_id")
        now = _anchor_text(page, anchor)
        if now is None:
            continue
        was = _anchor_text(_page_text(page_dir, c.get("version")), c.get("anchor_id"))
        out.append({"id": c["id"], "anchor": anchor, "v": c.get("version"), "text": _mask(c.get("text") or ""),
                    "changed": was is not None and was != now})
    return out[-20:]


def _page_text(page_dir: Path, v) -> str:
    try:
        return (page_dir / "versions" / f"{v}.html").read_text(encoding="utf-8", errors="replace")
    except (OSError, TypeError):
        return ""


# Pictures the agent named in a table cell: today's page leaves `![](../x.png)` as text and never copies the file.
LOOSE = re.compile(r"!\[[^\]]*\]\(((?:\.\./)+[^)\s]+\.(?:png|jpe?g|gif|webp))\)", re.I)
CARRIED = "assets/carried"
# shortcut: FastLane Drive's run folders only; take the agent's source folder from the page when other projects use this UI
PICTURE_ROOTS = [r for r in os.environ.get("ANNOTATE_PROTO_PICTURE_ROOTS", os.pathsep.join([
    "/Users/changlee/projects/FastLane Drive/planning/operations/orchestration",
    "/Volumes/fattie/projects/FastLane Drive/planning/operations/orchestration"])).split(os.pathsep) if r]


def carried_pictures(page_dir: Path) -> list:
    """The loose pictures copied into this copy, by path without the leading ../ (what the Questions tab shows)."""
    base = page_dir / CARRIED
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()) if base.is_dir() else []


def carry_pictures(page_dir: Path, roots=None) -> dict:
    """Copy each loose picture any version names into assets/carried/<path without ../>; read-only on the sources."""
    import glob
    import shutil
    tails = {re.sub(r"^(?:\.\./)+", "", m) for f in (page_dir / "versions").glob("v*.html")
             for m in LOOSE.findall(f.read_text(encoding="utf-8", errors="replace"))}
    out = {}
    for tail in sorted(tails):
        dest = (page_dir / CARRIED / tail).resolve()
        if not dest.is_relative_to((page_dir / CARRIED).resolve()):
            continue
        found = next((Path(p) for r in (roots or PICTURE_ROOTS) for p in sorted(glob.glob(os.path.join(glob.escape(r), "*", glob.escape(tail))))
                      if Path(p).is_file()), None)
        if found:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(found, dest)
        out[tail] = str(found) if found else None
    return out


if __name__ == "__main__":  # copy.sh: python3 -m agent_annotate.proto_data.questions <page dir>
    import sys
    got = carry_pictures(Path(sys.argv[1]))
    print(f"carried {sum(1 for v in got.values() if v)} of {len(got)} loose pictures",
          *[f"  not found: {t}" for t, v in got.items() if not v], sep="\n")
