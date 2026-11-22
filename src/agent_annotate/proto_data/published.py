"""Published pages' notes in the prototype: a kept document (Admin team meeting, Usage audit) or a copy's Reference
policies page keeps 2.32.8's notes in its own comments.json (keyed by the page's data-anchor-id; a point on a cell picture
is on its row, with the picture's css). Those folders are read only: the prototype is a dummy copy.

merge() reads each publication's notes into the prototype's store under the readers' keys; split() takes them back out
and never writes them: a new note, and the prototype's copy of an edited, closed, re-opened or deleted release note, stay
in the prototype's own store, keyed by id, so they win on the next read. The server calls both around every store read
and write (sync_server._v2_load, _v2_save), and guard() refuses a save outside the prototype's root.
export() gives a publication's store in 2.32.8's shape with the prototype's notes in it, for a sandbox copy's shape check.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from pathlib import Path

from .reference import POLICIES, _kept_src, html_blocks

KEY = "_published"  # the merged store's {pub: release notes as read, gone: tombstones}; split() drops it
_homes: dict = {}  # (folder, html file, its mtime) -> its Home


class Home:
    """One publication: its folder, the reader's key prefix and its places: [{k: reader key, a: anchor, t: words, css}]."""

    def __init__(self, folder: Path, prefix: str, whole: str, blocks: list, ids: list, raw: dict, by_index: bool):
        self.folder, self.prefix, self.whole, self.units = folder, prefix, whole, []
        add = lambda **u: self.units.append(u)
        for i, (b, x) in enumerate(zip(blocks, ids)):
            own = x[0] if isinstance(x, list) else x
            k = f"{prefix}~{i}" if by_index else f"{prefix}~{own}"
            if b[0] != "tbl":
                add(k=k, a=raw.get(own), t=str(b[2] if b[0] == "img" else b[1]), css="img:nth-of-type(1)" if b[0] == "img" else None)
                continue
            add(k=k, a=raw.get(own), t=str(b[1]), css=None)
            cp = b[4] if len(b) > 4 else None
            for ri, row in enumerate(b[2]):
                if ri == 0 and (b[3] or not by_index):  # the header row is the table's (Reference keys a headless first row ~r0)
                    continue
                rt = x[ri] if ri < len(x) else f"{own}~r{ri}"
                rk = f"{k}~r{ri}" if by_index else f"{prefix}~{rt}"
                ra = raw.get(rt) or raw.get(own)
                add(k=rk, a=ra, t=" ".join(map(str, row)), css=None)
                j = 0
                for ci, parts in enumerate(cp[ri] if cp and ri < len(cp) else []):
                    f = 0
                    for p in parts or []:
                        if p and p[0] == "img":
                            j, f = j + 1, f + 1
                            add(k=f"{rk}~p{j}", a=ra, t=str(p[2]), css=f"td:nth-of-type({ci + 1}) > figure:nth-of-type({f}) > img:nth-of-type(1)")
        self.by_key = {u["k"]: u for u in self.units if u["a"]}
        self.older = []  # the earlier revisions' Homes, newest first: a note whose anchor left the page stays on its own revision

    def key_of(self, a, t: dict) -> str:
        """The reader's key for a 2.32.8 note on anchor `a` with target `t`: on the newest revision that has `a`, as
        2.32.8 opens it; the whole document's when its words are gone from every revision."""
        at = [u for u in self.units if u["a"] == a]
        if not at and (o := next((o for o in self.older if any(u["a"] == a for u in o.units)), None)):
            return o.key_of(a, t)
        pics, rest = [u for u in at if u["css"]], [u for u in at if not u["css"] or u["css"] == "img:nth-of-type(1)"]
        if t.get("tag") == "img" and pics:
            return next((u for u in pics if u["css"] == t.get("css")), pics[0])["k"]
        q = re.sub(r"\s+", " ", str(t.get("selected_quote") or t.get("quote") or "")).strip()
        hit = next((u for u in rest if q and q in re.sub(r"\s+", " ", u["t"])), None) or (rest or at or [None])[0]
        return hit["k"] if hit else self.whole

    def place(self, k: str, t) -> tuple:
        """(anchor, target) in 2.32.8's shape for a note at reader key `k`, or None when the page has no such place."""
        u = self.by_key.get(k) or next((o.by_key[k] for o in self.older if k in o.by_key), None)
        if not u:
            return None
        t = dict(t) if isinstance(t, dict) else None
        if t and t.get("quote") and not t.get("selected_quote"):
            t["selected_quote"] = t["quote"]
        if t and t.get("tag") == "img" and u["css"]:
            t["css"] = u["css"]
        return u["a"], t


def _home(folder: Path, html: Path, doc: str, prefix: str, whole: str, by_index: bool) -> Home | None:
    try:
        key = (str(folder), str(html), html.stat().st_mtime_ns)
        if key not in _homes:
            ids, raw = [], {}
            b = html_blocks(html.read_text(errors="ignore"), _kept_src(doc, folder), ids, raw)
            _homes[key] = Home(folder, prefix, whole, b, ids, raw, by_index)
        return _homes[key]
    except OSError:
        return None


def homes(page_dir) -> list[Home]:
    """This page's publications: FastLane Drive's kept documents, or a copy's Reference policies page (links._kept_dir)."""
    from . import links
    meta = links._json(Path(page_dir) / "current.meta.json")
    root, _, fld = links._scope(meta)
    out = []
    if fld:
        revs = []  # the meeting's revisions (links.meeting); its notes go on the newest that has their anchor
        for h in links._json(links.MEETING / "current.meta.json").get("history") or []:
            f = links.MEETING / "versions" / f"{(h or {}).get('version') if isinstance(h, dict) else ''}.html"
            if f.is_file() and (r := _home(links.MEETING, f, "admin-meeting", "doc:kept-admin-meeting~p", "doc:kept-admin-meeting", False)):
                revs.append(r)
        if revs:
            revs[-1].older = revs[-2::-1]
            out.append(revs[-1])
        out.append(_home(links.USAGE_AUDIT.parent, links.USAGE_AUDIT, "usage-audit", "doc:kept-usage-audit~p", "doc:kept-usage-audit", False))
    elif root:
        out.append(_home(root / POLICIES, root / POLICIES / "current.html", "policies", "ref:policies~x", "ref:policies", True))
    return [h for h in out if h]


def _read(folder: Path) -> dict:
    from ..store import read_comments
    return read_comments(folder) if (folder / "comments.json").is_file() else {"schema_version": 2, "anchors": {}, "archived": {}}


def signature(page_dir) -> tuple:
    """Each publication's store and page, so a note 2.32.8 saves there is read at once, and whose notes are his own."""
    out = [("viewer", reader())]
    for h in homes(page_dir):
        try:
            s = (h.folder / "comments.json").stat()
            out.append((str(h.folder), s.st_ino, s.st_size, s.st_mtime_ns))
        except OSError:
            out.append((str(h.folder),))
    return tuple(out)


PARTS = ("anchors", "archived")
_print = lambda c: hashlib.sha1(json.dumps(c, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _items(store: dict):
    for part in PARTS:
        for a, v in (store.get(part) or {}).items():
            for c in v if isinstance(v, list) else []:
                if isinstance(c, dict):
                    yield part, a, c


_viewer = {"h": None}  # the signed-in reviewer's real address, hashed: release notes' ownership is decided on it, before masking
# the fields that name a reviewer, in a note, its replies and decisions; edited_by is whoever made its last PUT (words,
# Move, Re-open), so a peer's edit stays the peer's in the feed and the round (r12 audit26 questions 3)
WHO = ("author", "author_email", "by", "flagged_by", "edited_by", "edited_by_email")
_hash = lambda s: hashlib.sha256(("proto-viewer\0" + s.strip().lower()).encode()).hexdigest()


def viewer(email):
    """sync_server._identity, before it masks: whose release notes are his own; his hash, or None for an agent or an
    anonymous read. Area reads pass it into the build (proto_data.prepared), the pooled worker's too, and cache per reader;
    other paths read the last reviewer's from this module (agents and anonymous reads leave it)."""
    if email and not str(email).startswith("agent:"):
        _viewer["h"] = _hash(str(email))
        return _viewer["h"]
    return None


_here = threading.local()  # the reader of the build on this thread (proto_data.prepared, and the rebuild it starts behind the answer)


def reader():
    """Whose release notes are his own in this thread's build: its reader's hash (None: nobody's), else the last reviewer's."""
    return getattr(_here, "h", _viewer["h"])


def behind(fn) -> None:
    """fn on a daemon thread, for this thread's reader: a rebuild behind the answer keeps his notes his own (r12 fix29)."""
    h = reader()

    def run():
        _here.h = h
        fn()
    threading.Thread(target=run, daemon=True).start()


def _who(x):
    """A release note with each reviewer named as the prototype names him: the signed-in reviewer as the prototype masks
    him (MASK), so his own note passes the own-note checks for edit and remove as in 2.32.8; another reviewer as his own
    stable token, never an address, so his drafts are a peer's (no Edit, no Remove, never in this reviewer's Send)."""
    from . import EMAIL, MASK
    if isinstance(x, list):
        return [_who(v) for v in x]
    if not isinstance(x, dict):
        return x
    out = {}
    for k, v in x.items():
        if k in WHO and isinstance(v, str) and (m := EMAIL.search(v)):
            h = _hash(m[0])
            v = MASK if h == reader() else "reviewer-" + h[:12]
        out[k] = _who(v)
    return out


def merge(page_dir, store: dict) -> dict:
    """The prototype's store with each publication's notes in it, under the readers' keys, read only. The prototype's
    own record of a note (keyed by its id: a new one, or its copy of an edited, closed, re-opened or deleted release
    note) wins; a deleted one's tombstone hides every copy and stays out of the merged store. An own record of a release
    note held under another anchor (a copy's `copy:policies` mirror of its policies page) is the same note: it joins the
    release record on the reader's key, and split() puts it back where it was."""
    from . import scrub_json
    out = {**store, "anchors": {}, "archived": {}}
    gone, dead = [], {c.get("id") for _, _, c in _items(store) if c.get("status") == "deleted"}
    rel, cur = {}, {}  # {id: [home, part, anchor, record]} of each release note; cur: {id: its publication's current version}
    from .links import _json
    hs = homes(page_dir)
    for h in hs:
        v = _json(h.folder / "current.meta.json").get("current")
        for part, a, c in _items(_read(h.folder)):
            rel.setdefault(c.get("id"), [h, part, a, c])
            cur.setdefault(c.get("id"), v)
    keys = {u["k"] for h in hs for r in [h, *h.older] for u in r.units} | {h.whole for h in hs}
    have, mirror = set(), {}  # mirror: {id: [part, anchor, own record]}
    for part, a, c in _items(store):
        i = c.get("id")
        if c.get("status") == "deleted":
            gone.append([a, c])
        elif i in dead:
            continue  # removed: the removal wins over the prototype's own copy, whatever happened to it before
        elif i in rel and a not in keys:
            mirror[i] = [part, a, c]
        else:
            have.add(i)
            out[part].setdefault(a, []).append(c)
    pub = {}  # {id: [[part, key, print], ...]} of each release note as read (one per reader sharing its folder), so split() can tell an unchanged one
    for h in hs:
        for part, a, c in _items(_read(h.folder)):
            i = c.get("id")
            if i in have or i in dead:
                continue
            # no address leaves: the reviewers are named by _who first, then scrubbed as every prototype body is
            c = json.loads(scrub_json(json.dumps(_who(c), ensure_ascii=False)))
            t = c.get("target") if isinstance(c.get("target"), dict) else {}
            k = h.key_of(c.get("anchor_id") or a, t)
            n = {**c, "anchor_id": k}
            if t.get("selected_quote") and not t.get("quote"):
                n["target"] = {**t, "quote": t["selected_quote"]}
            if i in mirror:  # the mirror's fields the release record lacks, and its replies, join it; the release record's own win
                m = mirror[i][2]
                ids = {r.get("id") for r in n.get("replies") or [] if isinstance(r, dict)}
                n = {**m, **n, "replies": [*(n.get("replies") or []), *[r for r in m.get("replies") or [] if not isinstance(r, dict) or r.get("id") not in ids]]}
                if not n["replies"] and "replies" not in c and "replies" not in m:
                    del n["replies"]
            out[part].setdefault(k, []).append(n)
            pub.setdefault(i, []).append([part, k, _print(n)])
    # the prototype's own copy of a release note: its removal leaves a tombstone (split), so the release record stays hidden
    shadow = {i: [p, a] for p, a, c in _items(out) if (i := c.get("id")) in rel and i not in pub}
    out[KEY] = {"pub": pub, "gone": gone, "shadow": shadow, "mirror": mirror, "cur": cur}
    return out


def split(page_dir, store: dict) -> dict:
    """The prototype's own store from a merged one. A publication's store is never written: a release note unchanged
    since merge() read it is left out (it is read again from there); an edited, closed, re-opened or moved one is kept
    here under its id, so this copy wins on the next read; a deleted one leaves a tombstone here."""
    meta = store.get(KEY) or {}
    pub, gone, shadow, mirror = (meta.get(x) or {} for x in ("pub", "gone", "shadow", "mirror"))
    own = {k: v for k, v in store.items() if k != KEY}
    own["anchors"], own["archived"] = {}, {}
    seen = {}
    tomb = lambda i, k: own["archived"].setdefault(k, []).append({"id": i, "anchor_id": k, "status": "deleted"})
    for part, k, c in _items(store):
        i = c.get("id")
        seen[i] = seen.get(i, 0) + 1
        if [part, k, _print(c)] in pub.get(i, []):
            continue
        own[part].setdefault(k, []).append(c)
    for i, copies in pub.items():
        if seen.get(i, 0) < len(copies):  # a copy was removed (two readers can share one publication's folder)
            tomb(i, copies[0][1])
    for i, (part, k) in shadow.items():
        if not seen.get(i):  # the prototype's own copy of a release note was removed: the removal wins over the release record
            tomb(i, k)
    for i, (part, a, c) in mirror.items():
        if seen.get(i) or i not in pub:  # a mirror (copy:policies) stays where it was; a removed note's goes with it
            own[part].setdefault(a, []).append(c)
    for a, c in gone:
        own["archived"].setdefault(a, []).append(c)
    return own


def guard(path) -> Path:
    """The prototype saves only under its own root (replaced.PROTO_ROOT, or ANNOTATE_PROTO_ROOT in tests and sandboxes):
    a publication's folder, another project or a live page is refused, in code."""
    from .replaced import ENV, PROTO_ROOT
    p, root = Path(path).resolve(), Path(os.environ.get(ENV) or PROTO_ROOT).resolve()
    if root not in p.parents:
        raise PermissionError(f"refused: the prototype saves only under {root}, not {path}")
    return p


def export(page_dir, folder, store: dict) -> dict:
    """The publication at `folder`'s store as 2.32.8 would hold it with the prototype's notes (a merged `store`) in it:
    for the sandbox shape check only, written into a copy of that folder, never into the folder itself."""
    h = next(h for h in homes(page_dir) if h.folder == Path(folder))
    out = _read(h.folder)
    out = {**out, **{p: {a: list(v) for a, v in (out.get(p) or {}).items()} for p in PARTS}}
    pub = (store.get(KEY) or {}).get("pub") or {}
    meta = json.loads((h.folder / "current.meta.json").read_text()) if (h.folder / "current.meta.json").is_file() else {}
    meta["current"] = meta.get("current") or next((x.get("version") for x in reversed(meta.get("history") or []) if isinstance(x, dict)), None)
    for part, k, c in _items(store):
        if c.get("id") in pub or c.get("status") == "deleted" or not (placed := h.place(k, c.get("target"))):
            continue
        for p in PARTS:  # the prototype's copy of a release note replaces it
            out[p] = {a: [x for x in v if x.get("id") != c.get("id")] for a, v in out[p].items()}
        n = {**c, "anchor_id": placed[0], **({"version": meta["current"]} if meta.get("current") else {})}  # as 2.32.8 saves on that page
        if placed[1] is not None:
            n["target"] = placed[1]
        out[part].setdefault(placed[0], []).append(n)
    return out
