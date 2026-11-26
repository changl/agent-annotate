"""r13 speed: each heavy tab's first screen, cut from its whole area read. The tab draws this, then reads the whole area behind
it and draws again, so nothing is dropped: the notes, document texts, older versions and task details arrive a moment later.
What a slice keeps does not grow with the page's versions or notes."""

import hashlib
import json
import threading

AREAS = {"reference", "running", "history", "links"}
NV = 20  # History's first screen: its newest versions, as S.nv shows them
NA = 200  # and at most this many of their answers
NW = 80  # withdrawn questions, as the list shows them
_EXTRA = ("id", "t", "m", "kind", "st", "d", "from", "note")  # a Copy library row, without its text
_BEAD = ("t", "st", "type", "pri", "own", "made", "upd", "labels", "ncm")  # a task's list line, without its details


def _reference(d: dict) -> dict:
    ex = []
    for x in d.get("extras") or []:
        row = {k: x[k] for k in _EXTRA if k in x}
        if isinstance(x.get("find"), dict):  # the row's line counts its findings
            row["find"] = {"items": [{} for _ in x["find"].get("items") or []], "conclusion": ""}
        ex.append(row)
    return {**d, "extras": ex, "notes": []}


def _running(d: dict) -> dict:
    b = d.get("board")
    if not isinstance(b, dict) or not isinstance(b.get("beads"), dict):
        return d
    beads = {k: {f: v[f] for f in _BEAD if f in v} for k, v in b["beads"].items()}
    return {**d, "board": {**b, "beads": beads}}


def _num(v: str) -> int:
    try:
        return int(str(v).lstrip("v").split(".")[0])
    except ValueError:
        return -1


def _history(d: dict) -> dict:
    vers = d.get("versions") or {}
    keep = set(sorted(vers, key=_num, reverse=True)[:NV])
    if d.get("current"):
        keep.add(d["current"])
    answers = [a for a in d.get("answers") or [] if a.get("v") in keep][:NA]
    return {**d, "versions": {k: v for k, v in vers.items() if k in keep}, "answers": answers,
            "withdrawn": (d.get("withdrawn") or [])[:NW]}


def _links(d: dict) -> dict:
    docs = d.get("docs") or {}
    files = [{**{k: v for k, v in f.items() if k != "md"}, **({"md": 1} if f.get("md") else {})} for f in docs.get("files") or []]
    kept = [{k: v for k, v in x.items() if k in ("id", "t", "sub")} for x in d.get("kept") or []]
    return {**d, "docs": {**docs, "files": files}, "kept": kept, "notes": []}


_CUT = {"reference": _reference, "running": _running, "history": _history, "links": _links}
_made: dict = {}  # area -> (the whole body's digest, the slice's bytes)
_lock = threading.Lock()


def cut(area: str, body: bytes) -> bytes:
    """The first screen of one area's whole JSON body (as this reader sees it), marked part: true; cut once per body."""
    h = hashlib.blake2b(body, digest_size=16).digest()
    with _lock:
        hit = _made.get(area)
    if hit and hit[0] == h:
        return hit[1]
    d = json.loads(body)
    out = json.dumps({**_CUT[area](d), "part": True}, ensure_ascii=False).encode() if isinstance(d, dict) else body
    with _lock:
        _made[area] = (h, out)
    return out
