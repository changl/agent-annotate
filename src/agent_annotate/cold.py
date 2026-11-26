"""The cold store: settled feedback from older versions, kept out of comments.json.

On a long-lived page most of the store is feedback on older versions that no
Save, Refresh or Send touches (FLD: 9,374 of 10,118 items, 16 of 20 MB).
Those items live in comments.cold.json; comments.json keeps the rest plus a
"cold" summary. Merged, the two are exactly the one store every reader saw
before: the same items, list order and key order.

Summary: {"gen", "docs", "keys": {area: [anchor, ...]}, "lists": {area: {anchor: tokens}}}.
`keys` is the merged key order. In `tokens`, [i, j] stands for cold items
i..j-1 of that list and a string for the next hot item (its id). `docs` is the
fingerprint of the documents the split was made for (sync_server._docs_sig).

What may go cold (split): an item the page view would leave out
(sync_server._page_keep), with an id and a number, on a Review or plan
document, not newer than that document's current version. While cold an item
never changes; a write that needs it moves it back first (`_insert`).

Crash safety: each single write leaves a complete store. A re-split only
appends to the cold file (positions comments.json points at never change),
then writes comments.json; a fresh cold file is written only while
comments.json holds every item (no summary). Moving an item back is one write
of comments.json: the item joins its list and leaves its range; the cold file
keeps a copy nobody reads (a fresh file drops them once they outnumber the rest).
"""

from __future__ import annotations

import copy
import json
import os
import secrets
import threading
from pathlib import Path

NAME = "comments.cold.json"
KEY = "cold"
AREAS = ("anchors", "archived")
# Below this many cold items a page keeps one file.
MIN_ITEMS = 200


class Hot(dict):
    """comments.json as the server holds it. `index` is its cold file (None without one);
    `checkouts` are cold items a write handed out ({(area, anchor, i): (copy, its JSON)})."""

    def __init__(self, *args, index=None):
        super().__init__(*args)
        self.index = index
        self.checkouts = {}


class Index:
    """One parsed cold file, read-only, with what readers derive from it."""

    def __init__(self, data: dict):
        self.gen = data.get("gen")
        self.lists = {area: data.get(area) if isinstance(data.get(area), dict) else {} for area in AREAS}
        self._ids = None
        self._stamps = None
        self._derived: dict = {}

    def ids(self) -> dict:
        """{id: [(area, anchor, i), ...]}: a moved-back item can sit in the file twice (see rebalance)."""
        if self._ids is None:
            self._ids = {}
            for area in AREAS:
                for aid, items in self.lists[area].items():
                    for i, c in enumerate(items):
                        self._ids.setdefault(c["id"], []).append((area, aid, i))
        return self._ids

    def stamp(self, area, aid, i):
        if self._stamps is None:
            self._stamps = {}
        key = (area, aid, i)
        if key not in self._stamps:
            from .sync_server import _item_stamp
            # As the browser's copy is stamped (sync_server._v2_get_store drops carry_history).
            item = {k: v for k, v in self.lists[area][aid][i].items() if k != "carry_history"}
            self._stamps[key] = _item_stamp(area, aid, item)
        return self._stamps[key]

    def plan_docs(self) -> set:
        if "plan_docs" not in self._derived:
            self._derived["plan_docs"] = {c.get("doc") for area in AREAS for items in self.lists[area].values()
                                          for c in items if str(c.get("doc") or "").startswith("plan:")}
        return self._derived["plan_docs"]

    def derived(self, sig, rules) -> dict:
        """Per cold item: its omitted-count row, body-card key and prompt keys, for one set of documents."""
        hit = self._derived.get("rules")
        if hit and hit[0] == sig:
            return hit[1]
        from .sync_server import _answered_question, _prompt_keys
        rows, cards, prompts = {}, {}, {}
        for area in AREAS:
            for aid, items in self.lists[area].items():
                for i, c in enumerate(items):
                    key = (area, aid, i)
                    if not rules.newer(c) and not (area == "anchors" and c.get("withdrawn")):
                        rest = area == "anchors" and bool(c.get("decision_request")) and c.get("status") not in ("archived", "resolved_in_version")
                        rows[key] = (rules.doc_of(c), int(rest), int(rest and not (c.get("decision") or {}).get("verdict")))
                    if (doc := rules.card(c, aid)) is not None:
                        cards.setdefault((area, aid), set()).add(i)
                    if _answered_question(c):
                        for prompt in _prompt_keys(c):
                            prompts.setdefault(prompt, []).append(key)
        value = {"rows": rows, "cards": cards, "prompts": prompts}
        self._derived["rules"] = (sig, value)
        return value


_FILES: dict[str, tuple] = {}
_FILES_LOCK = threading.Lock()


def _stat(path: Path):
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def signature(slug_dir):
    return _stat(Path(slug_dir) / NAME)


def load_index(slug_dir) -> Index | None:
    path = Path(slug_dir) / NAME
    stat = _stat(path)
    if stat is None:
        return None
    with _FILES_LOCK:
        hit = _FILES.get(str(path))
    if hit and hit[0] == stat:
        return hit[1]
    data = json.loads(path.read_text(encoding="utf-8"))
    index = Index(data if isinstance(data, dict) else {})
    with _FILES_LOCK:
        _FILES[str(path)] = (stat, index)
    return index


def attach(slug_dir, raw: dict) -> Hot:
    """comments.json's parsed content as a Hot store with its cold file."""
    hot = raw if isinstance(raw, Hot) else Hot(raw)
    summary = hot.get(KEY)
    if summary is not None:
        index = load_index(slug_dir) if isinstance(summary, dict) else None
        if index is None or index.gen != summary.get("gen"):
            raise ValueError(f"{NAME} does not match comments.json")
        hot.index = index
    return hot


def merged(slug_dir, raw: dict) -> dict:
    """The whole store, for a reader of comments.json."""
    return merge(attach(slug_dir, raw)) if isinstance(raw, dict) and KEY in raw else raw


def _keys(hot, area) -> list:
    summary = hot[KEY]
    hot_area, lists = hot.get(area) or {}, summary["lists"][area]
    order = [k for k in dict.fromkeys(summary["keys"][area]) if k in hot_area or k in lists]
    seen = set(order)
    return order + [k for k in hot_area if k not in seen]


def _merge_list(tokens, cold_items, hot_items, take=None) -> list:
    out, h = [], 0
    for t in tokens:
        if isinstance(t, list):
            out.extend(cold_items[t[0]:t[1]] if take is None else (take(i) for i in range(t[0], min(t[1], len(cold_items)))))
        elif h < len(hot_items):
            out.append(hot_items[h])
            h += 1
    return out + hot_items[h:]


def merge(hot: Hot) -> dict:
    """A new store dict over the same item objects (read them, never mutate)."""
    out = {k: v for k, v in hot.items() if k != KEY}
    if KEY not in hot or hot.index is None:
        return out
    for area in AREAS:
        hot_area, lists, cold = hot.get(area) or {}, hot[KEY]["lists"][area], hot.index.lists[area]
        merged_area = {}
        for aid in _keys(hot, area):
            items = hot_area.get(aid)
            if aid in lists:
                both = _merge_list(lists[aid], cold.get(aid) or [], items if isinstance(items, list) else [])
                if both or aid in hot_area:
                    merged_area[aid] = both
            else:
                merged_area[aid] = items
        out[area] = merged_area
    return out


def ordered(hot: Hot) -> dict:
    """The hot store without its summary, keys in merged order (what the page view projects)."""
    out = {k: v for k, v in hot.items() if k != KEY}
    if KEY in hot and hot.index is not None:
        for area in AREAS:
            hot_area = hot.get(area) or {}
            out[area] = {aid: hot_area[aid] for aid in _keys(hot, area) if aid in hot_area}
    return out


def live(hot: Hot):
    """(area, anchor, i, item) for each cold item the summary still points at."""
    if KEY not in hot or hot.index is None:
        return
    for area in AREAS:
        cold = hot.index.lists[area]
        for aid, tokens in hot[KEY]["lists"][area].items():
            items = cold.get(aid) or []
            for t in tokens:
                if isinstance(t, list):
                    for i in range(t[0], min(t[1], len(items))):
                        yield area, aid, i, items[i]


def _normalize_list(summary, area, aid, items) -> None:
    """Re-sync one list's tokens after the writer removed or appended hot items.

    Writers only remove items and append them at the end, so hot items still in
    token order keep their places; from the first one out of order on, all are
    appended (re-added items go to the end, as they did in the one-file store)."""
    lists = summary["lists"][area]
    tokens = lists[aid]
    ids = [c.get("id") if isinstance(c, dict) else None for c in items] if isinstance(items, list) else []
    where = {t: n for n, t in enumerate(tokens) if isinstance(t, str) and t}
    kept, tail, last = set(), [], -1
    for cid in ids:
        n = where.get(cid) if not tail and isinstance(cid, str) and cid not in kept else None
        if n is not None and n > last:
            kept.add(cid)
            last = n
        else:
            tail.append(cid if isinstance(cid, str) else "")
    tokens = [t for t in tokens if (t[0] < t[1] if isinstance(t, list) else t in kept)] + tail
    if any(isinstance(t, list) for t in tokens):
        lists[aid] = tokens
    else:
        del lists[aid]


def normalize(hot: dict) -> None:
    """Bring the summary in line with the hot lists, before each write of comments.json."""
    summary = hot.get(KEY)
    if not isinstance(summary, dict):
        return
    for area in AREAS:
        hot_area = hot.get(area) or {}
        lists = summary["lists"][area]
        for aid in list(lists):
            _normalize_list(summary, area, aid, hot_area.get(aid))
        # A key with cold items stays where it is; the others follow the same rule as items.
        order = summary["keys"][area]
        where = {k: n for n, k in enumerate(order)}
        kept, tail, last = set(), [], -1
        for k in hot_area:
            if k in lists:
                continue
            n = where.get(k) if not tail else None
            if n is not None and n > last:
                kept.add(k)
                last = n
            else:
                tail.append(k)
        summary["keys"][area] = [k for k in order if k in lists or k in kept] + tail


def _insert(hot: Hot, area, aid, i, obj) -> bool:
    """Move cold item i of (area, aid) back into its hot list at its merged place; tokens are normalized."""
    tokens = hot[KEY]["lists"][area].get(aid)
    if tokens is None:
        return False
    slot = 0
    for n, t in enumerate(tokens):
        if isinstance(t, list):
            if t[0] <= i < t[1]:
                tokens[n:n + 1] = [r for r in ([t[0], i], obj["id"], [i + 1, t[1]]) if not isinstance(r, list) or r[0] < r[1]]
                break
        else:
            slot += 1
    else:
        return False
    hot_area = hot.setdefault(area, {})
    if aid not in hot_area:
        hot_area[aid] = []
        order = {k: n for n, k in enumerate(_keys(hot, area))}
        moved = sorted(hot_area.items(), key=lambda kv: order.get(kv[0], len(order)))
        hot_area.clear()
        hot_area.update(moved)
    hot_area[aid].insert(slot, obj)
    if not any(isinstance(t, list) for t in tokens):
        del hot[KEY]["lists"][area][aid]
    return True


def live_id(hot, cid):
    """(area, anchor, i) when `cid` is a live cold item, else None."""
    if not isinstance(hot, Hot) or KEY not in hot or hot.index is None or not isinstance(cid, str):
        return None
    for where in hot.index.ids().get(cid, ()):
        area, aid, i = where
        tokens = hot[KEY]["lists"][area].get(aid) or ()
        if any(isinstance(t, list) and t[0] <= i < t[1] for t in tokens):
            return where
    return None


def promote_id(hot: Hot, cid) -> bool:
    """Move the item `cid` back before a write that targets it."""
    where = live_id(hot, cid)
    if where is None:
        return False
    normalize(hot)
    area, aid, i = where
    return _insert(hot, area, aid, i, copy.deepcopy(hot.index.lists[area][aid][i]))


def has_id(hot, cid) -> bool:
    return isinstance(hot, Hot) and hot.index is not None and KEY in hot and cid in hot.index.ids()


def checkout(hot: Hot, area, aid, i):
    key = (area, aid, i)
    if key not in hot.checkouts:
        original = hot.index.lists[area][aid][i]
        hot.checkouts[key] = (copy.deepcopy(original), json.dumps(original, ensure_ascii=False))
    return hot.checkouts[key][0]


def anchor_items(store, aid, match, area="anchors") -> list:
    """One list's items that `match`, in merged order. Cold ones come checked out:
    a write may change them, and the save moves changed ones back."""
    items = (store.get(area) or {}).get(aid) or []
    if not isinstance(store, Hot) or store.index is None or KEY not in store or aid not in store[KEY]["lists"][area]:
        return [c for c in items if match(c)]
    _normalize_list(store[KEY], area, aid, items)
    if aid not in store[KEY]["lists"][area]:
        return [c for c in items if match(c)]
    out = []
    for c in _merge_list(store[KEY]["lists"][area][aid], store.index.lists[area].get(aid) or [], items,
                         take=lambda i: (area, aid, i)):
        if isinstance(c, tuple):
            held = store.checkouts.get(c)
            if match(held[0] if held else store.index.lists[area][aid][c[2]]):
                out.append(checkout(store, *c))
        elif match(c):
            out.append(c)
    return out


def numbered(hot, number) -> list:
    """(area, anchor, item) for live cold items carrying `number`."""
    if not isinstance(hot, Hot):
        return []
    return [(area, aid, c) for area, aid, _, c in live(hot) if c.get("number") == number]


def phantoms(hot, also=()) -> list:
    """The cold items cli._item_numbers needs to label every hot item as in the merged store:
    those sharing a number a hot item claims, and the highest."""
    if not isinstance(hot, Hot) or hot.index is None or KEY not in hot:
        return []
    from .cli import _claimed_number, _iter_comments
    wanted = {_claimed_number(c) for _, c in _iter_comments(hot, include_archived=True)} | set(also)
    out, top = [], None
    for _, _, _, c in live(hot):
        n = c.get("number")
        if n in wanted:
            out.append(c)
        if top is None or n > top.get("number"):
            top = c
    if top is not None and top.get("number") not in wanted:
        out.append(top)
    return out


def strays(hot: Hot, rules, sig) -> list:
    """Live cold items the page view would show (sync_server._page_keep): moved back on save."""
    derived = hot.index.derived(sig, rules)
    found = set()
    # "You answered this on …": earlier answers to a prompt a shown card asks.
    asked = set()
    from .cli import _iter_comments
    from .sync_server import _prompt_keys
    for _, c in _iter_comments(hot, include_archived=True):
        if c.get("decision_request") and rules.visible(c) and rules.hot(c):
            asked |= _prompt_keys(c)
    alive = None
    for prompt in asked & derived["prompts"].keys():
        if alive is None:
            alive = {(a, d, i) for a, d, i, _ in live(hot)}
        found |= {key for key in derived["prompts"][prompt] if key in alive}
    # A body card shows the first live (else the last archived) question on its anchor.
    lists = hot[KEY]["lists"]
    cold = hot.index.lists
    anchors = {aid for (area, aid) in derived["cards"] if aid in lists[area]}
    for aid in anchors:
        firsts = {}
        for area in AREAS:
            items = (hot.get(area) or {}).get(aid) or []
            tokens = lists[area].get(aid)
            if tokens is not None:
                _normalize_list(hot[KEY], area, aid, items)
                tokens = lists[area].get(aid)
            seq = _merge_list(tokens, cold[area].get(aid) or [], items, take=lambda i, a=area: (a, aid, i)) if tokens else items
            chosen = {}
            for c in seq:
                key = c if isinstance(c, tuple) else None
                if key is None and not (isinstance(c, dict) and rules.visible(c)):
                    continue
                doc = rules.card(cold[area][aid][key[2]] if key else c, aid)
                if doc is not None and (area == "archived" or doc not in chosen):
                    chosen[doc] = key
            if area == "anchors":
                firsts = chosen
            found |= {key for doc, key in chosen.items() if key and (area == "anchors" or doc not in firsts)}
    return sorted(found)


def settle(hot: Hot, rules, sig) -> None:
    """Before a write of comments.json: re-sync the summary and move back what must be hot."""
    if KEY not in hot or hot.index is None:
        return
    normalize(hot)
    changed = [(key, obj) for key, (obj, text) in hot.checkouts.items()
               if json.dumps(obj, ensure_ascii=False) != text]
    hot.checkouts.clear()
    for (area, aid, i), obj in changed:
        _insert(hot, area, aid, i, obj)
    if hot[KEY].get("docs") != sig:
        # Saved without the stray check: these documents may show a cold item. Only a new split trusts it again.
        hot[KEY]["docs"] = None
    else:
        for area, aid, i in strays(hot, rules, sig):
            _insert(hot, area, aid, i, copy.deepcopy(hot.index.lists[area][aid][i]))
    normalize(hot)


def split(store: dict, rules, keep: set, sig, gen):
    """(hot with summary, cold file content, cold count) for a whole store."""
    summary = {"gen": gen, "docs": sig, "keys": {}, "lists": {}}
    hot = Hot({k: v for k, v in store.items() if k != KEY})
    cold = {"gen": gen}
    count = 0

    def eligible(c):
        number = c.get("number")
        return (isinstance(c, dict) and id(c) not in keep and rules.doc_of(c) is not None and rules.listed(c)
                and not rules.newer(c) and type(number) is int and number > 0)

    for area in AREAS:
        source = store.get(area) or {}
        hot_area, cold_area, lists = {}, {}, {}
        for aid, items in source.items():
            ids = [c.get("id") if isinstance(c, dict) else None for c in items] if isinstance(items, list) else [None]
            flags = ([eligible(c) for c in items]
                     if all(isinstance(i, str) for i in ids) and len(set(ids)) == len(ids) else [])
            if not any(flags):
                hot_area[aid] = items
                continue
            tokens, hot_items, cold_items = [], [], []
            for c, flag in zip(items, flags):
                if flag:
                    if tokens and isinstance(tokens[-1], list):
                        tokens[-1][1] += 1
                    else:
                        tokens.append([len(cold_items), len(cold_items) + 1])
                    cold_items.append(c)
                else:
                    tokens.append(c["id"])
                    hot_items.append(c)
            count += len(cold_items)
            cold_area[aid], lists[aid] = cold_items, tokens
            if hot_items:
                hot_area[aid] = hot_items
        hot[area], cold[area] = hot_area, cold_area
        summary["keys"][area], summary["lists"][area] = list(source), lists
    hot[KEY] = summary
    return hot, cold, count


def _extend(store: Hot, hot: Hot, cold: dict, count):
    """Re-express a new split against the current cold file, appending only newly cold items.

    Returns (file content, whether anything was appended), or None when stale copies would
    outnumber live items (then the caller writes a fresh file). Item objects still cold are
    the file's own (merge hands them out), so identity finds their old position."""
    old = store.index
    where = {id(c): (area, aid, i) for area in AREAS for aid, items in old.lists[area].items()
             for i, c in enumerate(items)}
    files = {area: dict(old.lists[area]) for area in AREAS}
    grown, remapped = set(), []
    for area in AREAS:
        for aid, tokens in hot[KEY]["lists"][area].items():
            items, out = cold[area][aid], []
            for t in tokens:
                if not isinstance(t, list):
                    out.append(t)
                    continue
                for c in items[t[0]:t[1]]:
                    pos = where.get(id(c))
                    if pos is None or pos[:2] != (area, aid):
                        if (area, aid) not in grown:
                            grown.add((area, aid))
                            files[area][aid] = list(files[area].get(aid) or [])
                        files[area][aid].append(c)
                        p = len(files[area][aid]) - 1
                    else:
                        p = pos[2]
                    if out and isinstance(out[-1], list) and out[-1][1] == p:
                        out[-1][1] += 1
                    else:
                        out.append([p, p + 1])
            remapped.append((tokens, out))
    if sum(len(items) for area in AREAS for items in files[area].values()) > 2 * count:
        return None
    for tokens, out in remapped:
        tokens[:] = out
    hot[KEY]["gen"] = old.gen
    return {"gen": old.gen, **files}, bool(grown)


def rebalance(slug_dir, store: Hot, rules, keep_of, sig, write_hot) -> Hot:
    """Split the whole store again for these documents; returns what comments.json now holds.

    The cold file only grows in place, or is replaced while comments.json holds every item."""
    from .store import write_bytes
    whole = merge(store) if KEY in store else {k: v for k, v in store.items() if k != KEY}
    hot, cold, count = split(whole, rules, keep_of(whole), sig, secrets.token_hex(8))
    if count < MIN_ITEMS:
        if KEY not in store:
            return store
        whole = Hot(whole)
        write_hot(whole)
        return whole
    path = Path(slug_dir) / NAME
    kept = _extend(store, hot, cold, count) if KEY in store and store.index is not None else None
    if kept is not None:
        # Old positions stay valid, so comments.json may point at either file version: no whole-store write.
        cold, appended = kept
        if not appended:
            hot.index = store.index
            write_hot(hot)
            return hot
    elif KEY in store:
        write_hot(Hot(whole))
    write_bytes(path, json.dumps(cold, ensure_ascii=False, separators=(",", ":")).encode())
    index = Index(cold)
    with _FILES_LOCK:
        _FILES[str(path)] = (_stat(path), index)
    hot.index = index
    write_hot(hot)
    return hot


def count_items(store) -> int:
    return sum(len(items) for area in AREAS for items in (store.get(area) or {}).values() if isinstance(items, list))


def exists(slug_dir) -> bool:
    return os.path.exists(Path(slug_dir) / NAME)
