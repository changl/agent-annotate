"""The prototype's note store for published pages: a note on a kept document (Admin team meeting, Usage audit) or on a
copy's Reference policies page lives in that publication's own comments.json, in 2.32.8's shape (keyed by the page's
data-anchor-id; a point on a cell picture is on its row, with the picture's css), so it shows in both whichever saved it.

merge() puts the publication's notes into the prototype's store under the readers' keys; split() takes them back out and
writes each publication's own, leaving any note 2.32.8 added meanwhile. The server calls both around every store read
and write (sync_server._v2_load, _v2_save), so Edit, Reply, Close, Remove and Send act on the publication's record.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .reference import POLICIES, _kept_src, html_blocks

KEY = "_published"  # the merged store's {publication folder: its note ids when read}; split() drops it
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

    def key_of(self, a, t: dict) -> str:
        """The reader's key for a 2.32.8 note on anchor `a` with target `t`; the whole document's when its words are gone."""
        at = [u for u in self.units if u["a"] == a]
        pics, rest = [u for u in at if u["css"]], [u for u in at if not u["css"] or u["css"] == "img:nth-of-type(1)"]
        if t.get("tag") == "img" and pics:
            return next((u for u in pics if u["css"] == t.get("css")), pics[0])["k"]
        q = re.sub(r"\s+", " ", str(t.get("selected_quote") or t.get("quote") or "")).strip()
        hit = next((u for u in rest if q and q in re.sub(r"\s+", " ", u["t"])), None) or (rest or at or [None])[0]
        return hit["k"] if hit else self.whole

    def place(self, k: str, t) -> tuple:
        """(anchor, target) in 2.32.8's shape for a note at reader key `k`, or None when the page has no such place."""
        u = self.by_key.get(k)
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
        last = None  # the meeting's notes go on its newest revision (links.meeting)
        for h in links._json(links.MEETING / "current.meta.json").get("history") or []:
            f = links.MEETING / "versions" / f"{(h or {}).get('version') if isinstance(h, dict) else ''}.html"
            last = f if f.is_file() else last
        if last:
            out.append(_home(links.MEETING, last, "admin-meeting", "doc:kept-admin-meeting~p", "doc:kept-admin-meeting", False))
        out.append(_home(links.USAGE_AUDIT.parent, links.USAGE_AUDIT, "usage-audit", "doc:kept-usage-audit~p", "doc:kept-usage-audit", False))
    elif root:
        out.append(_home(root / POLICIES, root / POLICIES / "current.html", "policies", "ref:policies~x", "ref:policies", True))
    return [h for h in out if h]


def _read(folder: Path) -> dict:
    from ..store import read_comments
    return read_comments(folder) if (folder / "comments.json").is_file() else {"schema_version": 2, "anchors": {}, "archived": {}}


def signature(page_dir) -> tuple:
    """Each publication's store and page, so a note 2.32.8 saves there is read at once."""
    out = []
    for h in homes(page_dir):
        try:
            s = (h.folder / "comments.json").stat()
            out.append((str(h.folder), s.st_ino, s.st_size, s.st_mtime_ns))
        except OSError:
            out.append((str(h.folder),))
    return tuple(out)


def merge(page_dir, store: dict) -> dict:
    """The prototype's store with each publication's notes in it, under the readers' keys; its own notes win on an id."""
    store = {**store, "anchors": {a: list(v) for a, v in (store.get("anchors") or {}).items()},
             "archived": {a: list(v) for a, v in (store.get("archived") or {}).items()}}
    have = {c.get("id") for part in ("anchors", "archived") for v in store[part].values() for c in v}
    known = store[KEY] = {}
    for h in homes(page_dir):
        ids = known[str(h.folder)] = []
        pub = _read(h.folder)
        for part in ("anchors", "archived"):
            for a, items in (pub.get(part) or {}).items():
                for c in items:
                    if not isinstance(c, dict) or c.get("id") in have:
                        continue
                    t = c.get("target") if isinstance(c.get("target"), dict) else {}
                    k = h.key_of(c.get("anchor_id") or a, t)
                    n = {**c, "anchor_id": k}
                    if t.get("selected_quote") and not t.get("quote"):
                        n["target"] = {**t, "quote": t["selected_quote"]}
                    store[part].setdefault(k, []).append(n)
                    ids.append(c.get("id"))
    return store


def split(page_dir, store: dict) -> dict:
    """The prototype's own store from a merged one; each publication's notes are written to its own comments.json, in
    2.32.8's shape, only when they changed. A note 2.32.8 saved since merge() read it is kept."""
    from ..store import transaction, write_bytes
    known = store.get(KEY) or {}
    own = {k: v for k, v in store.items() if k != KEY}
    own["anchors"], own["archived"] = {}, {}
    hs = homes(page_dir)
    mine = {str(h.folder): [] for h in hs}
    for part in ("anchors", "archived"):
        for k, items in (store.get(part) or {}).items():
            for c in items:
                h = next((h for h in hs if c.get("id") in known.get(str(h.folder), ())), None) or next((h for h in hs if k in h.by_key), None)
                if h:
                    mine[str(h.folder)].append((part, k, c))
                else:
                    own[part].setdefault(k, []).append(c)
    for h in hs:
        with transaction(h.folder):
            fresh = _read(h.folder)
            was = {c.get("id"): (part, a, c) for part in ("anchors", "archived") for a, v in (fresh.get(part) or {}).items() for c in v if isinstance(c, dict)}
            ours = {c.get("id") for _, _, c in mine[str(h.folder)]}
            out = {"anchors": {}, "archived": {}}
            for i, (part, a, c) in was.items():  # 2.32.8's own since the read, untouched
                if i not in ours and i not in known.get(str(h.folder), ()):
                    out[part].setdefault(a, []).append(c)
            for part, k, c in mine[str(h.folder)]:
                old = was.get(c.get("id"))
                oa = old and (old[2].get("anchor_id") or old[1])
                ot = old and (old[2].get("target") if isinstance(old[2].get("target"), dict) else {})
                if old and h.key_of(oa, ot) == k:  # not moved: its own anchor and target, as 2.32.8 saved them
                    a, t = oa, old[2].get("target")
                else:  # saved or moved in the prototype: the page's anchor for that place; a place it lacks keeps its old anchor
                    a, t = h.place(k, c.get("target")) or (oa, c.get("target"))
                if not a:  # shortcut: a note on a place the page has no anchor for stays in the prototype's store
                    own[part].setdefault(k, []).append(c)
                    continue
                n = {**c, "anchor_id": a}
                if t is None:
                    n.pop("target", None)
                else:
                    n["target"] = t
                out[part].setdefault(a, []).append(n)
            flat = lambda s: sorted(json.dumps([p, a, c], sort_keys=True) for p in ("anchors", "archived") for a, v in (s.get(p) or {}).items() for c in v)
            if flat(out) == flat(fresh):  # nothing of this page's changed: its file is left as it is
                continue
            new = {**fresh, **out}
            write_bytes(h.folder / "comments.json", json.dumps(new, ensure_ascii=False, separators=(",", ":")).encode(), value=new)
    return own
