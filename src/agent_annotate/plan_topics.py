"""Plans topics (Chang, cards #8 and #9, 2026-10-31). Annotate files every plan
and decision into a topic by fixed keyword rules, never an agent. Move to…
pins the item and is remembered as a rule for the same kind of item; what no
rule matches is Unsorted. The first topic list comes from the page's own
titles; topics can be renamed or merged. Stored per page in plan-topics.json:
{"topics": [{"name", "words": ["app store", …]}], "learned": [{"words", "topic"}],
 "placed": {plan_id: topic}}. A rule's words must all start words of the title."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .categories import _json, _lock, _text, _write, safe_path, validate_plan_id

FILE = "plan-topics.json"
UNSORTED = "Unsorted"
MAX_TOPICS = 100
MAX_LEARNED = 500
_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
# Words that never make a topic or a learned rule: grammar and the verbs every
# decision question shares ("Approve the proposed screen?").
_STOP = frozenset("""
a an the and or of for to in on at by with from as into about over under per via vs is are be been was were it its
this these that those our your you we he she they them his her their i me my do does did done can could should would
will shall may might must not no yes so if then than now new one two three four five what which who whom how when
where why all any each every more most only same other another use using keep show add make get set let go back
approve approved proposed propose drawn shown plan plans draft after before still just here there up down out off
v1 v2 v3 v4 v5 v6 v7 v8 v9
""".split())
# Words too generic to name a first topic ("Screen", "App"); rules may still use them.
_GENERIC = frozenset("screen app page list reference results version design flow sheet row button menu link".split())


def is_archive_plan(plan: dict) -> bool:
    # shortcut: mirrors categories.is_archive_plan from the long-pages branch; import it once that lands.
    return plan.get("section") == "archive"


def _filed(plan: dict) -> bool:
    """Hidden items and archive pages stay out of topics and the index."""
    return plan.get("section") != "hidden" and not is_archive_plan(plan)


def _words(text) -> list[str]:
    return _WORD.findall(str(text).lower())


def _significant(text) -> list[str]:
    return [w for w in _words(text) if w not in _STOP and not w.isdigit()]


def _starts(word: str, rule: str) -> bool:
    # "shop" files "shopping"; a short word only takes a plural ("app" never "apple").
    return word == rule or word == rule + "s" or (len(rule) >= 4 and word.startswith(rule))


def _position(rule: str, title_words: list[str]) -> int | None:
    """Where the rule matches (its earliest word), or None when a word is missing."""
    found = []
    for rule_word in _words(rule):
        at = next((i for i, word in enumerate(title_words) if _starts(word, rule_word)), None)
        if at is None:
            return None
        found.append(at)
    return min(found) if found else None


def learned_words(title: str) -> str:
    """The rule a move remembers: the title's lead (before ':' or a dash), its
    first two meaningful words, so "UAT results — Monday …" files "uat results"."""
    lead = re.split(r"\s*[:—–?]\s*|\s+-\s+", str(title), maxsplit=1)[0]
    return " ".join((_significant(lead) or _significant(title))[:2])


def topic_for(plan: dict, config: dict) -> str:
    """Pinned by a move, else the newest learned rule that matches, else the
    keyword that appears earliest in the title (topic order breaks a tie)."""
    names = {t["name"] for t in config["topics"]}
    placed = config["placed"].get(plan.get("id"))
    if placed in names:
        return placed
    words = _words(plan.get("title") or plan.get("id", ""))
    for rule in config["learned"]:
        if rule["topic"] in names and _position(rule["words"], words) is not None:
            return rule["topic"]
    best = None
    for order, topic in enumerate(config["topics"]):
        for rule in topic["words"]:
            at = _position(rule, words)
            if at is not None and (best is None or (at, order) < best[:2]):
                best = (at, order, topic["name"])
    return best[2] if best else UNSORTED


def seed(titles: list[str], *, min_items: int = 2, limit: int = 12) -> dict:
    """The first topic list, from the page's own titles: the leads that recur
    ("Ask Nicole …") and the words most titles share, most-used first; one
    that would file fewer than `min_items` items is dropped."""
    leads = Counter(learned_words(t) for t in titles if learned_words(t))
    words = Counter(w for t in titles for w in set(_significant(t)) if w.rstrip("s") not in _GENERIC)
    shown = {}
    for title in titles:  # the word as the page writes it ("iPhone", "FLD"), not shouted ("CHAT")
        for token in re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?", title):
            if token.lower() not in shown or (shown[token.lower()].isupper() and not token.isupper()):
                shown[token.lower()] = token
    candidates = [lead for lead, n in leads.items() if n >= min_items and " " in lead]
    candidates += [w for w, n in words.most_common() if n >= max(min_items, 3)]
    topics = []
    for rule in candidates:
        if len(topics) >= limit:
            break
        if any(rule in t["words"] or set(_words(rule)) & set(_words(" ".join(t["words"]))) for t in topics):
            continue
        name = " ".join(shown.get(w, w) for w in _words(rule))
        topics.append({"name": name[:1].upper() + name[1:], "words": [rule]})
    config = {"topics": topics, "learned": [], "placed": {}}
    # Keep only topics that still file enough items once all compete.
    filed = Counter(topic_for({"title": t}, config) for t in titles)
    config["topics"] = [t for t in topics if filed[t["name"]] >= min_items]
    return config


def _clean(raw: dict) -> dict | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("topics"), list):
        return None
    topics = [{"name": t["name"], "words": [w for w in t.get("words", []) if isinstance(w, str) and _words(w)]}
              for t in raw["topics"] if isinstance(t, dict) and isinstance(t.get("name"), str)]
    learned = [r for r in raw.get("learned", []) if isinstance(r, dict)
               and isinstance(r.get("words"), str) and isinstance(r.get("topic"), str)]
    placed = {k: v for k, v in (raw.get("placed") or {}).items() if isinstance(v, str)}
    return {"topics": topics, "learned": learned, "placed": placed}


def load(page_dir: Path | str, plans: list[dict]) -> dict:
    """The page's topics; until the reviewer changes one, seeded from its titles."""
    stored = _clean(_json(safe_path(page_dir, FILE), {}))
    return stored if stored is not None else seed([p.get("title") or p["id"] for p in plans if _filed(p)])


def file_plans(page_dir: Path | str, plans: list[dict]) -> list[str]:
    """Adds `topic` to each filed plan; returns the topic names in index order,
    Unsorted first when anything is in it."""
    config = load(page_dir, plans)
    for plan in plans:
        if _filed(plan):
            plan["topic"] = topic_for(plan, config)
    names = [t["name"] for t in config["topics"]]
    return ([UNSORTED] if any(p.get("topic") == UNSORTED for p in plans) else []) + names


def _name(value, config: dict, *, new: bool) -> str:
    name = " ".join(_text(value, "topic name", 60).split())
    if not name or name.lower() == UNSORTED.lower():
        raise ValueError("topic name must be a nonempty name other than Unsorted")
    taken = {t["name"].lower() for t in config["topics"]}
    if new and name.lower() in taken:
        raise ValueError("a topic with that name exists; move the item there or merge the topics")
    return name


def change(page_dir: Path | str, plans: list[dict], payload: dict) -> dict:
    """One reviewer change, written atomically under the page's topics lock:
    {"move": plan_id, "topic": name, "new": bool} · {"rename": name, "to": name}
    · {"merge": name, "into": name}. Returns the stored topics."""
    if not isinstance(payload, dict) or len({"move", "rename", "merge"} & set(payload)) != 1:
        raise ValueError("send one of move, rename or merge")
    with _lock(page_dir, ".plan-topics.json.lock"):
        config = load(page_dir, plans)
        topics = {t["name"]: t for t in config["topics"]}
        if "move" in payload:
            plan_id = validate_plan_id(payload["move"])
            plan = next((p for p in plans if p["id"] == plan_id and _filed(p)), None)
            if plan is None:
                raise KeyError(plan_id)
            if payload.get("new"):
                name = _name(payload.get("topic"), config, new=True)
                if len(config["topics"]) >= MAX_TOPICS:
                    raise ValueError(f"a page has at most {MAX_TOPICS} topics; merge some first")
                config["topics"].append({"name": name, "words": []})
            elif payload.get("topic") in topics:
                name = payload["topic"]
            else:
                raise KeyError(str(payload.get("topic")))
            config["placed"][plan_id] = name
            rule = learned_words(plan.get("title") or plan_id)
            if rule:
                config["learned"] = [{"words": rule, "topic": name}] + [
                    r for r in config["learned"] if r["words"] != rule][:MAX_LEARNED - 1]
        else:
            old = payload.get("rename", payload.get("merge"))
            if old not in topics:
                raise KeyError(str(old))
            if "rename" in payload:
                new = _name(payload.get("to"), config, new=str(payload.get("to") or "").lower() != old.lower())
                topics[old]["name"] = new
            else:
                new = payload.get("into")
                if new not in topics or new == old:
                    raise KeyError(str(new))
                topics[new]["words"] += [w for w in topics[old]["words"] if w not in topics[new]["words"]]
                config["topics"].remove(topics[old])
            config["placed"] = {k: (new if v == old else v) for k, v in config["placed"].items()}
            for rule in config["learned"]:
                if rule["topic"] == old:
                    rule["topic"] = new
        _write(safe_path(page_dir, FILE), config)
        return config
