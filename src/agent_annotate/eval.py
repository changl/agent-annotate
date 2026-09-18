#!/usr/bin/env python3
"""
eval.py — quantitative baseline for the agent-annotate review loop.

Read-only. Touches nothing the annotate runtime owns: it never writes to
comments.json, the NDJSON bus, bus-offsets, or the state registry, and it never
shells out to `annotate` / `cli.py` (those mutate read offsets).

Inputs (roots from paths.py; the defaults are the live ones)
------
  <state>/<project>.json                               registry: slug -> slug_dir
  <state>/logs/check-comment-bus.log
  <bus root>/<project>/<slug>.ndjson                   append-only event bus
  <slug_dir>/comments.json                             comment store (anchors + archived)
  <slug_dir>/current.meta.json                         version history
  ~/.claude/projects/*/*.jsonl                         Claude Code transcripts

Outputs (default <state>/logs/, override with --out-dir)
-------
  eval-baseline.json   machine-readable, every table as data
  eval-baseline.md     human-readable tables
  eval-transcript-cache.json   transcript scan cache (--refresh-transcripts)

Sections
--------
  1 per-slug shape          2 reviewer round shape       3 verdict->reaction latency
  4 text-verdict taxonomy                                 5 decision-prompt quality
  6 trace join (bus verdict -> transcript sighting)      7 hook notice owner/bystander

Usage
-----
  python -m agent_annotate.eval                 # --since defaults to 2026-09-01
  python -m agent_annotate.eval --since 2026-08-01
  python -m agent_annotate.eval --refresh-transcripts
  annotate eval --since 2026-08-01              # same run, headline printed
  --state-dir / --bus-dir / --transcript-glob   point it at a fixture estate

Run standalone or through `annotate eval`, which only execs this module. It is
never imported by the runtime and never calls back into the CLI: `inbox`
advances a read cursor, and a measurement that moves what it measures is not a
measurement.

--since is the recency cutoff. Sections 1-5 cover every slug but tag each one
in/out of window and repeat their aggregates for the in-window subset.
Sections 6-7 scan transcripts, which is expensive, so they only cover in-window
slugs.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import glob
import json
import os
import re
import statistics
import sys

HOME = os.path.expanduser("~")
try:
    from .paths import BUS_ROOT as _BUS_ROOT
    from .paths import STATE_DIR as _STATE_DIR
    from .paths import TRANSCRIPT_GLOB as _TG
except ImportError:  # run as a bare script: same defaults, spelled out
    _STATE_DIR = (os.environ.get("ANNOTATE_STATE_DIR") or os.environ.get("ANNOTATE_STATE_ROOT")
                  or os.path.join(HOME, ".claude", "annotate-state", "state"))
    _BUS_ROOT = os.environ.get("ANNOTATE_BUS_ROOT") or os.path.join(HOME, ".claude", "annotate-bus")
    _TG = os.path.join(HOME, ".claude", "projects", "*", "*.jsonl")

# Module globals so every loader reads one setting; main() rebinds them from
# --state-dir / --bus-dir / --transcript-glob before any scan.
STATE_DIR = str(_STATE_DIR)
BUS_DIR = str(_BUS_ROOT)
LOG_DIR = os.path.join(STATE_DIR, "logs")
HOOK_LOG = os.path.join(LOG_DIR, "check-comment-bus.log")
TRANSCRIPT_GLOB = str(_TG)
CACHE_PATH = os.path.join(LOG_DIR, "eval-transcript-cache.json")


def _rebind_roots(state_dir=None, bus_dir=None, transcript_glob=None):
    """Point the module at another estate (fixtures, a copied backup)."""
    global STATE_DIR, BUS_DIR, LOG_DIR, HOOK_LOG, TRANSCRIPT_GLOB, CACHE_PATH
    if state_dir:
        STATE_DIR = str(state_dir)
        LOG_DIR = os.path.join(STATE_DIR, "logs")
        HOOK_LOG = os.path.join(LOG_DIR, "check-comment-bus.log")
        CACHE_PATH = os.path.join(LOG_DIR, "eval-transcript-cache.json")
    if bus_dir:
        BUS_DIR = str(bus_dir)
    if transcript_glob:
        TRANSCRIPT_GLOB = str(transcript_glob)

# D2 replaced the "comment" verdict with "changes" (Request changes). The
# corpus holds both — everything answered before D2 says "comment" — so they
# fold into one column here; splitting them would break every trend line this
# file exists to draw.
VERDICTS = ("accept", "reject", "changes")
VERDICT_ALIAS = {"comment": "changes"}
TEXT_VERDICTS = ("changes", "comment")
AGENT_PREFIX = "agent:"


def verdict_column(v):
    """The counting column for a stored verdict, or None if there is none."""
    if not v:
        return None
    col = VERDICT_ALIAS.get(v, v)
    return col if col in VERDICTS else None


def is_archived(c):
    """True for a comment `annotate close` (or the archive route) retired.

    D7: a closed card was never answered and never will be. Counting it as
    unanswered would keep a retired page's backlog in the numbers forever,
    which is the opposite of what closing it was for.
    """
    return (c.get("status") == "archived") or bool(c.get("archived_at"))

# Events that describe the machinery rather than a person. v2.19 added most of
# them, and every one carries either no author or the agent's; counting them as
# reviewer activity would overstate exactly the number this file exists to
# measure. `round_submitted` is the reviewer pressing "Submit review" once per
# round, not per card, so it is bookkeeping here too.
BOOKKEEPING_EVENTS = frozenset({
    "seen_updated",
    "comments_seeded",
    "decision_requested",
    "page_published",
    "page_publish_failed",
    "page_claimed",
    "version_published",
    "notice_emitted",
    "inbox_read",
    "bulk_overwrite",
    "monitor_armed",
    "monitor_exited",
    "round_submitted",
    "round_discarded",
    "session_push",
    # D7: `annotate close` archived stale unanswered cards. Bookkeeping by
    # definition — the point of the command is that nobody answered.
    "page_closed",
})
ID_RE = re.compile(r"^[0-9a-f]{12}$")
# Two notice formats in the corpus: v2.18's "New comments since last turn — …"
# and v2.19's one-line-per-slug "[annotate] proj/slug: N reviewer event(s) …".
# Both have to parse or the hook's own history disappears from section 7.
NOTICE_RE = re.compile(
    r"\[annotate\]\s*(?:New comments since last turn\s*[—-]\s*)?([^\"\\\n]{0,400})"
)
NOTICE_PAIR_RE = re.compile(
    r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+):\s*(\d+)\s*(?:new|reviewer) event")


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

def parse_ts(s):
    """Parse the ISO-8601 stamps used by the bus, the store and the transcripts."""
    if not s or not isinstance(s, str):
        return None
    t = s.strip().replace("Z", "+00:00")
    try:
        d = dt.datetime.fromisoformat(t)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def mins(a, b):
    """Minutes from a to b, or None if either stamp is missing."""
    if a is None or b is None:
        return None
    return (b - a).total_seconds() / 60.0


def pct(values, q):
    """Nearest-rank percentile over a list of numbers. q in [0,1]."""
    vs = sorted(v for v in values if v is not None)
    if not vs:
        return None
    if q <= 0:
        return vs[0]
    k = max(0, min(len(vs) - 1, int(round(q * len(vs) + 0.5)) - 1))
    return vs[k]


def med(values):
    vs = sorted(v for v in values if v is not None)
    return statistics.median(vs) if vs else None


def r1(x):
    return None if x is None else round(x, 1)


def is_agent(author):
    return bool(author) and str(author).startswith(AGENT_PREFIX)


def is_reviewer_event(e):
    """A person did this. Requires a named non-agent author AND an event type
    that is not machinery; an event with no author at all is something the
    system did to itself."""
    if e.get("event") in BOOKKEEPING_EVENTS:
        return False
    author = e.get("author")
    return bool(author) and not is_agent(author)


def is_agent_event(e):
    """Everything that is not a reviewer event: agent writes and bookkeeping.
    Defined as the complement so the two always sum to the event count."""
    return not is_reviewer_event(e)


def fmt_min(x):
    """Minutes -> compact human string."""
    if x is None:
        return "-"
    if x < 60:
        return f"{x:.0f}m"
    if x < 60 * 48:
        return f"{x / 60:.1f}h"
    return f"{x / 1440:.1f}d"


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #

def load_registry():
    """slug -> {project, slug_dir, url, started_at}. Registry files are per project."""
    out = {}
    for path in sorted(glob.glob(os.path.join(STATE_DIR, "*.json"))):
        try:
            doc = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(doc, dict) or "slugs" not in doc:
            continue
        project = doc.get("project")
        for slug, s in (doc.get("slugs") or {}).items():
            if not isinstance(s, dict):
                continue
            out[slug] = {
                "project": project,
                "slug_dir": s.get("slug_dir"),
                "url": s.get("url"),
                "started_at": s.get("started_at"),
                "transport": s.get("transport"),
            }
    return out


def load_bus(project, slug):
    path = os.path.join(BUS_DIR, project, slug + ".ndjson")
    events = []
    if not os.path.exists(path):
        return path, events
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            e["_ts"] = parse_ts(e.get("ts"))
            events.append(e)
    events.sort(key=lambda e: (e["_ts"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc)))
    return path, events


def iter_comments(store):
    """Yield every comment in a store, live anchors first then the archived map."""
    if not isinstance(store, dict):
        return
    for _aid, lst in (store.get("anchors") or {}).items():
        for c in lst if isinstance(lst, list) else []:
            if isinstance(c, dict):
                yield c, False
    arch = store.get("archived") or {}
    if isinstance(arch, dict):
        for c in arch.values():
            if isinstance(c, dict):
                yield c, True
    elif isinstance(arch, list):
        for c in arch:
            if isinstance(c, dict):
                yield c, True


def collect_slugs():
    """Union of registry slugs and bus slugs, with store + meta loaded where present."""
    reg = load_registry()
    keys = {}
    for slug, meta in reg.items():
        keys[slug] = meta.get("project")
    for path in glob.glob(os.path.join(BUS_DIR, "*", "*.ndjson")):
        slug = os.path.basename(path)[:-len(".ndjson")]
        project = os.path.basename(os.path.dirname(path))
        keys.setdefault(slug, project)

    slugs = {}
    for slug, project in keys.items():
        info = dict(reg.get(slug) or {})
        info.setdefault("project", project)
        info["slug"] = slug
        bus_path, events = load_bus(info["project"], slug)
        info["bus_path"] = bus_path
        info["events"] = events
        sd = info.get("slug_dir")
        store, meta = None, None
        if sd and os.path.isdir(sd):
            cj = os.path.join(sd, "comments.json")
            if os.path.exists(cj):
                try:
                    store = json.load(open(cj, encoding="utf-8"))
                except Exception:
                    store = None
            mj = os.path.join(sd, "current.meta.json")
            if os.path.exists(mj):
                try:
                    meta = json.load(open(mj, encoding="utf-8"))
                except Exception:
                    meta = None
        info["store"] = store
        info["meta"] = meta
        info["comments"] = [c for c, _a in iter_comments(store)] if store else []
        slugs[slug] = info
    return slugs


def created_at(info):
    """Earliest signal that the page existed: bus, version history, or first comment."""
    cands = []
    if info["events"]:
        cands.append(info["events"][0]["_ts"])
    m = info.get("meta") or {}
    for h in (m.get("history") or []):
        t = parse_ts(h.get("ts"))
        if t:
            cands.append(t)
            break
    for c in info["comments"]:
        t = parse_ts(c.get("created_at"))
        if t:
            cands.append(t)
    t = parse_ts((info.get("started_at") or ""))
    if t:
        cands.append(t)
    cands = [c for c in cands if c]
    return min(cands) if cands else None


# --------------------------------------------------------------------------- #
# verdict extraction
# --------------------------------------------------------------------------- #

def verdict_events(info):
    """
    Reviewer verdict events off the bus, newest schema first.

    `comment_updated` carries `decision` as a bare verdict string when a
    reviewer answers a decision request; `session_push` mirrors the same verdict
    when the page hands it to a session. We key on comment_updated and fall back
    to session_push for verdicts that predate it, deduped on (comment_id, ts).
    """
    seen = set()
    out = []
    for e in info["events"]:
        if e.get("event") != "comment_updated":
            continue
        d = e.get("decision")
        if not isinstance(d, str):
            continue
        key = (e.get("comment_id"), e.get("ts"))
        seen.add(key)
        out.append({
            "comment_id": e.get("comment_id"),
            "anchor_id": e.get("anchor_id"),
            "verdict": d,
            "author": e.get("author"),
            "ts": e["_ts"],
            "revised": bool(e.get("revised")),
            "prior_verdict": e.get("prior_verdict"),
            "source": "comment_updated",
        })
    for e in info["events"]:
        if e.get("event") != "session_push":
            continue
        d = e.get("decision")
        if not isinstance(d, str):
            continue
        key = (e.get("comment_id"), e.get("ts"))
        if key in seen:
            continue
        ids = e.get("comment_ids") or []
        cid = ids[0] if ids else e.get("comment_id")
        if (cid, e.get("ts")) in seen:
            continue
        out.append({
            "comment_id": cid,
            "anchor_id": e.get("anchor_id"),
            "verdict": d,
            "author": e.get("author"),
            "ts": e["_ts"],
            "revised": bool(e.get("revised")),
            "prior_verdict": e.get("prior_verdict"),
            "source": "session_push",
        })
    out.sort(key=lambda v: v["ts"] or dt.datetime.min.replace(tzinfo=dt.timezone.utc))
    return out


def agent_event_times(info):
    return sorted(e["_ts"] for e in info["events"] if is_agent(e.get("author")) and e["_ts"])


def agent_reaction_times(info):
    """Agent events that count as a *reaction*: authoring or replying, not seen marks."""
    kinds = {"comment_created", "comment_updated", "comment_reply", "comment_archived"}
    return sorted(e["_ts"] for e in info["events"]
                  if is_agent(e.get("author")) and e.get("event") in kinds and e["_ts"])


def first_after(sorted_times, t):
    for x in sorted_times:
        if t is not None and x > t:
            return x
    return None


# --------------------------------------------------------------------------- #
# section 1 — per-slug shape
# --------------------------------------------------------------------------- #

def section1(slugs, since):
    rows = []
    for slug, info in sorted(slugs.items()):
        created = created_at(info)
        evs = info["events"]
        comments = info["comments"]
        drs = [c for c in comments if c.get("decision_request")]

        vcount = collections.Counter()
        ttv = []
        for c in drs:
            d = c.get("decision") or {}
            v = d.get("verdict")
            # D7: an archived card with no verdict is "closed", not "none" —
            # it is out of the unanswered denominator on purpose.
            vcount[verdict_column(v) or ("closed" if is_archived(c) else "none")] += 1
            t0 = parse_ts(c.get("created_at"))
            t1 = parse_ts(d.get("ts"))
            m = mins(t0, t1)
            if m is not None and m >= 0:
                ttv.append(m)

        n_agent = sum(1 for e in evs if is_agent_event(e))
        n_reviewer = sum(1 for e in evs if is_reviewer_event(e))

        burst = 0
        if evs and created:
            cutoff = created + dt.timedelta(minutes=15)
            burst = sum(1 for e in evs
                        if is_agent(e.get("author")) and e["_ts"] and e["_ts"] <= cutoff)

        pushes = [e for e in evs if e.get("event") == "session_push"]
        delivery = collections.Counter(e.get("delivery", "?") for e in pushes)

        meta = info.get("meta") or {}
        nver = len(meta.get("history") or []) or (1 if meta.get("current") else 0)

        rows.append({
            "slug": slug,
            "project": info.get("project"),
            "created": created.isoformat() if created else None,
            "in_window": bool(created and since and created >= since),
            "comments": len(comments),
            "decision_requests": len(drs),
            "verdicts": {k: vcount.get(k, 0) for k in list(VERDICTS) + ["none", "closed"]},
            "time_to_verdict_min": {"n": len(ttv), "median": r1(med(ttv)), "p90": r1(pct(ttv, 0.9))},
            "agent_events": n_agent,
            "reviewer_events": n_reviewer,
            "authoring_burst_15m": burst,
            "session_push": len(pushes),
            "delivery": dict(delivery),
            "versions": nver,
            "has_store": info.get("store") is not None,
        })
    return rows


# --------------------------------------------------------------------------- #
# section 2 — reviewer round shape
# --------------------------------------------------------------------------- #

def section2(slugs, gap_minutes=10):
    """
    Cluster reviewer verdicts into rounds (a gap larger than `gap_minutes`
    starts a new round), then measure when the agent first reacted relative to
    the round's first verdict and to the round's end.
    """
    rounds = []
    for slug, info in sorted(slugs.items()):
        vs = [v for v in verdict_events(info) if v["ts"] and not is_agent(v["author"])]
        if not vs:
            continue
        reactions = agent_reaction_times(info)
        groups, cur = [], [vs[0]]
        for prev, nxt in zip(vs, vs[1:]):
            if (nxt["ts"] - prev["ts"]).total_seconds() / 60.0 > gap_minutes:
                groups.append(cur)
                cur = [nxt]
            else:
                cur.append(nxt)
        groups.append(cur)

        for i, g in enumerate(groups, 1):
            t_first, t_last = g[0]["ts"], g[-1]["ts"]
            react = first_after(reactions, t_first)
            rounds.append({
                "slug": slug,
                "round": i,
                "verdicts": len(g),
                "start": t_first.isoformat(),
                "duration_min": r1(mins(t_first, t_last)),
                "first_reaction_min": r1(mins(t_first, react)) if react else None,
                "reacted_mid_round": bool(react and len(g) > 1 and react < t_last),
                "verdict_mix": dict(collections.Counter(v["verdict"] for v in g)),
            })
    return rounds


# --------------------------------------------------------------------------- #
# section 3 — verdict -> reaction latency, unanswered ages
# --------------------------------------------------------------------------- #

def section3(slugs, now):
    lat, never = [], 0
    per_slug = collections.defaultdict(list)
    for slug, info in sorted(slugs.items()):
        reactions = agent_reaction_times(info)
        for v in verdict_events(info):
            if not v["ts"] or is_agent(v["author"]):
                continue
            r = first_after(reactions, v["ts"])
            if r is None:
                never += 1
                continue
            m = mins(v["ts"], r)
            lat.append(m)
            per_slug[slug].append(m)

    buckets = collections.Counter()
    unanswered = []
    closed = 0
    for slug, info in sorted(slugs.items()):
        for c in info["comments"]:
            if not c.get("decision_request"):
                continue
            if verdict_column((c.get("decision") or {}).get("verdict")) is not None:
                continue
            # D7: closed cards leave the backlog. They are reported as their
            # own number so the drop in the age buckets is explained, not
            # silent.
            if is_archived(c):
                closed += 1
                continue
            t0 = parse_ts(c.get("created_at"))
            age = mins(t0, now)
            if age is None:
                buckets["unknown"] += 1
                continue
            d = age / 1440.0
            b = "<1d" if d < 1 else "1-7d" if d < 7 else "7-30d" if d < 30 else ">30d"
            buckets[b] += 1
            unanswered.append({
                "slug": slug, "comment_id": c.get("id"), "age_days": round(d, 1),
                "status": c.get("status"),
                "prompt": ((c.get("decision_request") or {}).get("prompt") or "")[:120],
            })
    return {
        "latency": {
            "n": len(lat),
            "median_min": r1(med(lat)),
            "p90_min": r1(pct(lat, 0.9)),
            "no_reaction": never,
            "per_slug_median": {k: r1(med(v)) for k, v in sorted(per_slug.items())},
        },
        "unanswered_by_age": dict(buckets),
        "closed_cards": closed,
        "unanswered": sorted(unanswered, key=lambda r: -r["age_days"]),
    }


# --------------------------------------------------------------------------- #
# section 4 — text-verdict ('changes') taxonomy
# --------------------------------------------------------------------------- #

BOILERPLATE = ("✓ Accepted", "✗ Rejected", "✓ accepted", "✗ rejected")

MALFORMED = re.compile(
    r"(\bneither\b|\bboth options\b|\ball (3|three|of them) (temporarily|for now)\b|"
    r"\bnone of (these|them)\b|not a (real|valid) (choice|option)|"
    r"wrong question|false choice|doesn'?t make sense|misfram|that'?s not the question|"
    r"\bkeep all\b|third option|\bsame as (above|prior|previous)\b|"
    r"premise (is|was|has been) (wrong|falsified))", re.I)
QUESTION = re.compile(
    r"(^|[\s\"'(])(what|where|which|why|how|who|when|is this|are you|are we|have we|"
    r"have you|do you|does (it|this)|can you|could you|should we|did you)\b", re.I)
DISAGREE = re.compile(
    r"\b(absolutely not|not acceptable|exact opposite|no\.|^no\b|^nope\b|not yet|"
    r"disagree|incorrect|that'?s wrong|should not|shouldn'?t|do not|don'?t|"
    r"this is not|we are no[t]? |more effective to|instead of)", re.I)
REDIRECT = re.compile(
    r"\b(first|before|instead|let'?s |i'?d like you to|i want you to|go ahead and|"
    r"proceed with|make a separate|deploy a subagent|inventory|ensure|adapt|"
    r"trace references|review all|be more aggressive|also,? |then )", re.I)


def classify_reviewer_text(prompt, text, has_decision_request=True):
    """
    Keyword taxonomy for reviewer free-text. Deliberately simple and printed
    alongside the text so every label can be audited by eye.
    Priority: malformed > needs-more-context > disagrees > redirects-scope > other.

    A decision request posed with an empty prompt is malformed by construction.
    Free-text on a comment that was never a decision request is classified on
    its text alone.
    """
    t = (text or "").strip()
    p = (prompt or "").strip()
    if not t:
        return "other", "empty"
    if has_decision_request and not p:
        return "question-malformed-or-options-missing", "decision request had an empty prompt"
    if MALFORMED.search(t):
        return "question-malformed-or-options-missing", MALFORMED.search(t).group(0)
    if "?" in t and QUESTION.search(t):
        return "needs-more-context", QUESTION.search(t).group(0).strip()
    if DISAGREE.search(t):
        return "disagrees-with-recommendation", DISAGREE.search(t).group(0).strip()
    if REDIRECT.search(t):
        return "redirects-scope", REDIRECT.search(t).group(0).strip()
    return "other", ""


def section4(slugs):
    items = []
    for slug, info in sorted(slugs.items()):
        for c in info["comments"]:
            has_dr = bool(c.get("decision_request"))
            prompt = (c.get("decision_request") or {}).get("prompt") or ""
            d = c.get("decision") or {}
            if d.get("verdict") in TEXT_VERDICTS and (d.get("text") or "").strip():
                label, ev = classify_reviewer_text(prompt, d["text"], has_dr)
                items.append({
                    "slug": slug, "comment_id": c.get("id"), "kind": "verdict-text",
                    "author": d.get("by"), "label": label, "evidence": ev,
                    "prompt": prompt[:120],
                    "text": " ".join(d["text"].split())[:160],
                })
            for rp in (c.get("replies") or []):
                author = rp.get("author") or ""
                txt = (rp.get("text") or "").strip()
                if is_agent(author) or not txt:
                    continue
                if any(txt.startswith(b) for b in BOILERPLATE):
                    continue
                if d.get("verdict") in TEXT_VERDICTS and txt[:160] == (d.get("text") or "").strip()[:160]:
                    continue  # the auto-mirrored copy of the verdict text
                label, ev = classify_reviewer_text(prompt, txt, has_dr)
                items.append({
                    "slug": slug, "comment_id": c.get("id"), "kind": "reply",
                    "author": author, "label": label, "evidence": ev,
                    "prompt": prompt[:120],
                    "text": " ".join(txt.split())[:160],
                })
    counts = collections.Counter(i["label"] for i in items)
    counts_verdict = collections.Counter(i["label"] for i in items if i["kind"] == "verdict-text")
    return {"items": items, "counts": dict(counts), "counts_verdict_text_only": dict(counts_verdict)}


# --------------------------------------------------------------------------- #
# section 5 — decision prompt quality
# --------------------------------------------------------------------------- #

OPTIONS_RE = re.compile(r"(accept\s*=|reject\s*=|comment\s*=|option\s+[abc1-3]\b)", re.I)
RECO_RE = re.compile(r"\b(recommend|i recommend|suggest|propose|my pick|i'?d |i would|"
                     r"prefer|default to|leaning)\b", re.I)
EVIDENCE_RE = re.compile(r"(\d|/[A-Za-z0-9_.-]+/|\.[a-z]{2,4}\b|`[^`]+`|[sdq]:[A-Za-z0-9_-]+)")


def section5(slugs):
    rows = []
    for slug, info in sorted(slugs.items()):
        for c in info["comments"]:
            dr = c.get("decision_request")
            if not dr:
                continue
            prompt = dr.get("prompt") or ""
            d = c.get("decision") or {}
            v = d.get("verdict")
            rows.append({
                "slug": slug,
                "comment_id": c.get("id"),
                "words": len(prompt.split()),
                "names_options": bool(OPTIONS_RE.search(prompt)),
                "states_recommendation": bool(RECO_RE.search(prompt)),
                "cites_evidence": bool(EVIDENCE_RE.search(prompt)),
                "answered": verdict_column(v) is not None,
                "verdict": verdict_column(v) or "none",
                "prompt": prompt[:120],
            })

    def agg(sel, name):
        sub = [r for r in rows if sel(r)]
        if not sub:
            return {"feature": name, "n": 0}
        return {
            "feature": name,
            "n": len(sub),
            "answered_pct": round(100 * sum(r["answered"] for r in sub) / len(sub), 1),
            "changes_pct": round(100 * sum(r["verdict"] == "changes" for r in sub) / len(sub), 1),
            "accept_pct": round(100 * sum(r["verdict"] == "accept" for r in sub) / len(sub), 1),
            "median_words": round(statistics.median([r["words"] for r in sub]), 1),
        }

    table = [
        agg(lambda r: True, "all decision requests"),
        agg(lambda r: r["names_options"], "names options (Accept = ...)"),
        agg(lambda r: not r["names_options"], "no explicit options"),
        agg(lambda r: r["states_recommendation"], "states a recommendation"),
        agg(lambda r: not r["states_recommendation"], "no recommendation"),
        agg(lambda r: r["cites_evidence"], "cites evidence"),
        agg(lambda r: not r["cites_evidence"], "no evidence"),
        agg(lambda r: r["words"] <= 8, "short prompt (<=8 words)"),
        agg(lambda r: 8 < r["words"] <= 25, "medium prompt (9-25 words)"),
        agg(lambda r: r["words"] > 25, "long prompt (>25 words)"),
    ]
    return {"rows": rows, "table": table}


# --------------------------------------------------------------------------- #
# sections 6 & 7 — transcript scan
# --------------------------------------------------------------------------- #

def _block_text(block):
    if not isinstance(block, dict):
        return ""
    t = block.get("type")
    if t == "text":
        return block.get("text") or ""
    if t == "tool_result":
        c = block.get("content")
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            return " ".join(x.get("text", "") for x in c if isinstance(x, dict))
        return json.dumps(c)[:20000] if c is not None else ""
    if t == "tool_use":
        return json.dumps(block.get("input"))[:20000]
    return ""


def classify_sighting(tool_name, tool_input, text):
    """How did the session lay eyes on this comment id?"""
    blob = (tool_input or "").lower()
    if "new comments since last turn" in (text or "").lower():
        return "hook-notice"
    if tool_name == "Bash":
        if "inbox" in blob:
            return "cli-inbox"
        if "curl" in blob:
            return "curl"
        if "comments.json" in blob:
            return "read-store"
        if "annotate-bus" in blob or ".ndjson" in blob:
            return "read-bus"
        # ad-hoc scripts that hit the page's own HTTP API instead of the CLI
        if ("urllib.request" in blob or "/api/comments" in blob
                or "127.0.0.1:88" in blob or "localhost:88" in blob):
            return "http-api"
        return "bash-other"
    if tool_name in ("Read", "Grep", "Glob"):
        if "comments.json" in blob:
            return "read-store"
        if ".ndjson" in blob:
            return "read-bus"
        return f"{tool_name.lower()}-other"
    if tool_name:
        return f"tool:{tool_name}"
    return "assistant-text"


def scan_transcripts(ids_of_interest, refresh=False):
    """
    One pass over every Claude transcript.

    Returns:
      sightings:  comment_id -> [{ts, file, how, tool}]         (ids_of_interest only)
      file_ids:   file -> set(comment ids seen anywhere in it)  (ids_of_interest only)
      notices:    [{ts, file, slug, project, count}]            (deduped per line)
    """
    files = sorted(glob.glob(TRANSCRIPT_GLOB))
    sig = {f: [os.path.getmtime(f), os.path.getsize(f)] for f in files}
    cache = None
    if os.path.exists(CACHE_PATH) and not refresh:
        try:
            cache = json.load(open(CACHE_PATH, encoding="utf-8"))
        except Exception:
            cache = None
    if (cache and cache.get("sig") == sig
            and set(cache.get("ids") or []) == set(ids_of_interest)):
        return (
            {k: v for k, v in cache["sightings"].items()},
            {k: set(v) for k, v in cache["file_ids"].items()},
            cache["notices"],
        )

    if not ids_of_interest:
        return {}, {}, []
    idpat = re.compile("|".join(sorted(ids_of_interest)))
    sightings = collections.defaultdict(list)
    file_ids = collections.defaultdict(set)
    notices = []
    seen_notice = set()

    for path in files:
        try:
            raw = open(path, "rb").read()
        except OSError:
            continue
        # cheap byte-level gate: skip files that mention neither an id nor a notice
        has_ids = any(i.encode() in raw for i in ids_of_interest)
        has_notice = b"New comments since last turn" in raw
        if not has_ids and not has_notice:
            continue
        del raw

        tools = {}
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                # tool_use lines are parsed even without an id so the tool_use_id
                # -> (name, input) map is complete when the matching tool_result
                # arrives; otherwise every sighting looks like bare assistant text.
                interesting = ("New comments since last turn" in line
                               or '"tool_use"' in line
                               or idpat.search(line))
                if not interesting:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                ts = obj.get("timestamp")
                msg0 = obj.get("message") or {}
                c0 = msg0.get("content")
                if isinstance(c0, list):
                    for b in c0:
                        if isinstance(b, dict) and b.get("type") == "tool_use":
                            tools[b.get("id")] = (b.get("name"),
                                                  json.dumps(b.get("input"))[:4000])
                if ("New comments since last turn" not in line
                        and "reviewer event(s) since your last read" not in line
                        and not idpat.search(line)):
                    continue

                # The hook notice arrives as a type:"attachment" line and is also
                # mirrored into `rendered`, so match against the whole serialised
                # line rather than message.content only.
                sline = json.dumps(obj, ensure_ascii=False)
                line_has_notice = False
                for m in NOTICE_RE.finditer(sline):
                    body = m.group(1)
                    line_has_notice = True
                    key = (path, ts, body[:200])
                    if key in seen_notice:
                        continue
                    seen_notice.add(key)
                    for proj, slug, n in NOTICE_PAIR_RE.findall(body):
                        notices.append({"ts": ts, "file": path, "project": proj,
                                        "slug": slug, "count": int(n),
                                        "line_type": obj.get("type")})

                blocks = c0 if isinstance(c0, list) else (
                    [{"type": "text", "text": c0}] if isinstance(c0, str) else [])
                in_blocks = set()
                for b in blocks:
                    text = _block_text(b)
                    if not text:
                        continue
                    found = set(idpat.findall(text))
                    if not found:
                        continue
                    btype = b.get("type") if isinstance(b, dict) else None
                    if btype == "tool_result":
                        tname, tinput = tools.get(b.get("tool_use_id"), (None, None))
                    elif btype == "tool_use":
                        tname, tinput = b.get("name"), json.dumps(b.get("input"))[:4000]
                    else:
                        tname, tinput = None, None
                    how = classify_sighting(tname, tinput, text)
                    for cid in found:
                        in_blocks.add(cid)
                        file_ids[path].add(cid)
                        sightings[cid].append({"ts": ts, "file": path,
                                               "how": how, "tool": tname})
                # ids that only appear outside message.content (attachments,
                # toolUseResult payloads, queue operations)
                for cid in set(idpat.findall(sline)) - in_blocks:
                    file_ids[path].add(cid)
                    sightings[cid].append({
                        "ts": ts, "file": path, "tool": None,
                        "how": "hook-notice" if line_has_notice
                        else "line:" + str(obj.get("type"))})

    for cid in sightings:
        sightings[cid].sort(key=lambda s: s["ts"] or "")
    payload = {
        "sig": sig, "ids": sorted(ids_of_interest),
        "sightings": {k: v for k, v in sightings.items()},
        "file_ids": {k: sorted(v) for k, v in file_ids.items()},
        "notices": notices,
    }
    try:
        json.dump(payload, open(CACHE_PATH, "w", encoding="utf-8"))
    except OSError:
        pass
    return dict(sightings), dict(file_ids), notices


def section6(slugs, window, sightings):
    rows = []
    detail = []
    for slug in window:
        info = slugs[slug]
        ids = {c.get("id") for c in info["comments"] if c.get("id")}
        ids |= {e.get("comment_id") for e in info["events"] if e.get("comment_id")}
        ids = {i for i in ids if i}
        seen_any = {i for i in ids if sightings.get(i)}
        transcripts = sorted({s["file"] for i in ids for s in sightings.get(i, [])})

        lats, hows = [], collections.Counter()
        for v in verdict_events(info):
            if not v["ts"] or is_agent(v["author"]):
                continue
            cid = v["comment_id"]
            after = [s for s in sightings.get(cid, []) if s["ts"] and parse_ts(s["ts"]) > v["ts"]]
            if not after:
                detail.append({"slug": slug, "comment_id": cid, "verdict": v["verdict"],
                               "verdict_ts": v["ts"].isoformat(), "seen_min": None,
                               "how": "never-seen-after-verdict"})
                hows["never-seen-after-verdict"] += 1
                continue
            s0 = after[0]
            m = mins(v["ts"], parse_ts(s0["ts"]))
            lats.append(m)
            hows[s0["how"]] += 1
            detail.append({"slug": slug, "comment_id": cid, "verdict": v["verdict"],
                           "verdict_ts": v["ts"].isoformat(), "seen_min": r1(m),
                           "how": s0["how"],
                           "file": os.path.basename(s0["file"])})
        rows.append({
            "slug": slug,
            "comment_ids": len(ids),
            "ids_never_in_any_transcript": len(ids - seen_any),
            "transcripts": len(transcripts),
            "verdicts": sum(hows.values()),
            "seen_median_min": r1(med(lats)),
            "seen_p90_min": r1(pct(lats, 0.9)),
            "how": dict(hows),
        })
    return {"rows": rows, "detail": detail}


def section7(slugs, notices, file_ids):
    """
    Owner vs bystander: did the transcript that received the notice belong to
    the session that owns that page?

    Two independent ownership signals, because neither alone is complete:
      strict  the transcript quotes at least one of that slug's comment ids
              (only works for pages that actually have comments)
      loose   strict, or the transcript mentions the page's slug_dir
              (catches owners that only ever published and never read a comment)
    A notice counted as a bystander under BOTH signals is a genuine misroute.
    """
    slug_ids, slug_dirs = {}, {}
    for slug, info in slugs.items():
        s = {c.get("id") for c in info["comments"] if c.get("id")}
        s |= {e.get("comment_id") for e in info["events"] if e.get("comment_id")}
        slug_ids[slug] = {i for i in s if i}
        slug_dirs[slug] = info.get("slug_dir")

    # loose signal: only the handful of transcripts that received a notice
    notice_files = sorted({n["file"] for n in notices})
    dir_hits = {}
    for path in notice_files:
        try:
            raw = open(path, "rb").read()
        except OSError:
            continue
        hit = set()
        for slug, sd in slug_dirs.items():
            if sd and sd.encode() in raw:
                hit.add(slug)
        dir_hits[path] = hit
        del raw

    per_slug = collections.defaultdict(
        lambda: {"owner": 0, "bystander": 0, "owner_loose": 0,
                 "owner_files": set(), "bystander_files": set()})
    owner = bystander = unknown = 0
    owner_loose = 0
    for n in notices:
        slug = n["slug"]
        ids = slug_ids.get(slug)
        if ids is None:
            unknown += 1
            continue
        have = file_ids.get(n["file"], set())
        strict = bool(have & ids)
        loose = strict or slug in dir_hits.get(n["file"], set())
        if loose:
            owner_loose += 1
            per_slug[slug]["owner_loose"] += 1
        if strict:
            owner += 1
            per_slug[slug]["owner"] += 1
            per_slug[slug]["owner_files"].add(n["file"])
        else:
            bystander += 1
            per_slug[slug]["bystander"] += 1
            per_slug[slug]["bystander_files"].add(n["file"])
    return {
        "notices": len(notices),
        "owner": owner, "bystander": bystander, "unknown_slug": unknown,
        "owner_loose": owner_loose,
        "bystander_loose": len(notices) - unknown - owner_loose,
        "per_slug": {k: {"owner": v["owner"], "owner_loose": v["owner_loose"],
                         "bystander": v["bystander"],
                         "owner_transcripts": len(v["owner_files"]),
                         "bystander_transcripts": len(v["bystander_files"])}
                     for k, v in sorted(per_slug.items())},
    }


def hook_log_stats(since):
    """Notices the hook *emitted*, as a denominator for section 7."""
    total = 0
    per_slug = collections.Counter()
    lines = 0
    if not os.path.exists(HOOK_LOG):
        return {"log_lines": 0, "notices": 0, "per_slug": {}}
    pat = NOTICE_PAIR_RE
    tspat = re.compile(r"(\d{4}-\d{2}-\d{2}T[\d:]+Z)")
    for line in open(HOOK_LOG, encoding="utf-8", errors="replace"):
        m = tspat.search(line)
        t = parse_ts(m.group(1)) if m else None
        if since and t and t < since:
            continue
        lines += 1
        for _p, slug, _n in pat.findall(line):
            total += 1
            per_slug[slug] += 1
    return {"log_lines": lines, "notices": total, "per_slug": dict(per_slug)}


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #

def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join("" if x is None else str(x) for x in r) + " |")
    return "\n".join(out)


def render_md(res):
    since = res["meta"]["since"]
    L = []
    A = L.append
    A("# Agent-annotate review loop — quantitative baseline")
    A("")
    A(f"Generated {res['meta']['generated_at']} · cutoff `--since {since}` · "
      f"{res['meta']['slugs_total']} slugs total, {res['meta']['slugs_in_window']} in window.")
    A("")
    A("Read-only over the bus, the comment stores and the Claude transcripts. "
      "No annotate command was run.")
    A("")

    A("## 1. Per-slug shape")
    A("")
    rows = []
    for r in res["s1"]:
        v = r["verdicts"]
        rows.append([
            ("**" if r["in_window"] else "") + r["slug"] + ("**" if r["in_window"] else ""),
            (r["created"] or "")[:10], r["comments"], r["decision_requests"],
            f"{v['accept']}/{v['reject']}/{v['changes']}/{v['none']}/{v['closed']}",
            fmt_min(r["time_to_verdict_min"]["median"]),
            fmt_min(r["time_to_verdict_min"]["p90"]),
            f"{r['agent_events']}/{r['reviewer_events']}",
            r["authoring_burst_15m"], r["session_push"],
            ",".join(f"{k}:{n}" for k, n in sorted(r["delivery"].items())) or "-",
            r["versions"],
        ])
    A(md_table(["slug (bold = in window)", "created", "cmts", "DRs",
                "acc/rej/chg/none/closed", "t→verdict med", "p90", "agent/rev evts",
                "burst 15m", "pushes", "delivery", "vers"], rows))
    A("")
    a = res["s1_aggregate"]
    A(f"In-window totals: {a['comments']} comments, {a['decision_requests']} decision "
      f"requests, verdicts {a['verdicts']}, median time to verdict "
      f"{fmt_min(a['time_to_verdict_median'])} (p90 {fmt_min(a['time_to_verdict_p90'])}), "
      f"{a['agent_events']} agent vs {a['reviewer_events']} reviewer events "
      f"({a['agent_share_pct']}% agent), {a['session_push']} session pushes "
      f"{a['delivery']}.")
    A("")

    A("## 2. Reviewer round shape (gap > 10 min = new round)")
    A("")
    rows = [[r["slug"], r["round"], r["verdicts"], r["start"][:16].replace("T", " "),
             fmt_min(r["duration_min"]), fmt_min(r["first_reaction_min"]),
             "yes" if r["reacted_mid_round"] else "no",
             ",".join(f"{k}:{n}" for k, n in sorted(r["verdict_mix"].items()))]
            for r in res["s2"]]
    A(md_table(["slug", "#", "verdicts", "start (UTC)", "round dur",
                "1st verdict→agent", "mid-round?", "mix"], rows))
    A("")
    b = res["s2_summary"]
    A(f"{b['rounds']} rounds over {b['slugs']} slugs. "
      f"Median round holds {b['median_verdicts_per_round']} verdicts and runs "
      f"{fmt_min(b['median_duration_min'])}. Multi-verdict rounds: {b['multi_rounds']}; "
      f"the agent reacted before the round ended in {b['reacted_mid_round']} of them "
      f"({b['reacted_mid_round_pct']}%). Median first-verdict→agent-reaction "
      f"{fmt_min(b['median_first_reaction_min'])}.")
    A("")

    A("## 3. Verdict → agent reaction, and unanswered decision requests")
    A("")
    lat = res["s3"]["latency"]
    A(md_table(["metric", "value"], [
        ["verdict events measured", lat["n"]],
        ["median verdict→reaction", fmt_min(lat["median_min"])],
        ["p90 verdict→reaction", fmt_min(lat["p90_min"])],
        ["verdicts with no agent reaction after them", lat["no_reaction"]],
    ]))
    A("")
    A("Unanswered decision requests by age:")
    A("")
    A(md_table(["bucket", "count"],
               [[k, v] for k, v in sorted(res["s3"]["unanswered_by_age"].items())]))
    A("")
    A(f"{res['s3']['closed_cards']} card(s) were closed (archived unanswered by "
      f"`annotate close`) and are excluded from the buckets above.")
    A("")
    if res["s3"]["unanswered"][:15]:
        A("Oldest unanswered (top 15):")
        A("")
        A(md_table(["slug", "id", "age d", "status", "prompt"],
                   [[u["slug"], u["comment_id"], u["age_days"], u["status"], u["prompt"]]
                    for u in res["s3"]["unanswered"][:15]]))
        A("")

    A("## 4. Text-verdict taxonomy — 'changes' (pre-D2: 'comment') (auditable)")
    A("")
    A(md_table(["class", "all free-text", "verdict-text only"],
               [[k, res["s4"]["counts"].get(k, 0), res["s4"]["counts_verdict_text_only"].get(k, 0)]
                for k in sorted(set(res["s4"]["counts"]) | set(res["s4"]["counts_verdict_text_only"]))]))
    A("")
    A("Every classified item, text truncated to 160 chars:")
    A("")
    A(md_table(["class", "slug", "id", "kind", "author", "prompt", "reviewer text"],
               [[i["label"], i["slug"], i["comment_id"], i["kind"], i.get("author"),
                 i["prompt"].replace("|", "\\|"), i["text"].replace("|", "\\|")]
                for i in res["s4"]["items"]]))
    A("")

    A("## 5. Decision-prompt quality vs outcome")
    A("")
    A(md_table(["prompt feature", "n", "answered %", "changes %", "accept %", "median words"],
               [[t["feature"], t.get("n"), t.get("answered_pct"), t.get("changes_pct"),
                 t.get("accept_pct"), t.get("median_words")] for t in res["s5"]["table"]]))
    A("")

    A("## 6. Trace join — when did a session actually see the verdict?")
    A("")
    A(md_table(["slug", "ids", "ids never in any transcript", "transcripts",
                "verdicts", "seen med", "seen p90", "how first seen"],
               [[r["slug"], r["comment_ids"], r["ids_never_in_any_transcript"],
                 r["transcripts"], r["verdicts"], fmt_min(r["seen_median_min"]),
                 fmt_min(r["seen_p90_min"]),
                 ", ".join(f"{k}:{n}" for k, n in sorted(r["how"].items()))]
                for r in res["s6"]["rows"]]))
    A("")
    s6 = res["s6_summary"]
    A(f"Across the window: {s6['verdicts']} reviewer verdicts, "
      f"{s6['seen']} were later visible in some transcript "
      f"({s6['seen_pct']}%), median sighting latency {fmt_min(s6['median_min'])} "
      f"(p90 {fmt_min(s6['p90_min'])}). First-sighting channel: {s6['how']}.")
    A("")

    A("## 7. Hook notice — owner or bystander?")
    A("")
    s7 = res["s7"]
    A(md_table(["metric", "value"], [
        ["notice lines found in transcripts", s7["notices"]],
        ["owner, strict (transcript quotes the slug's comment ids)", s7["owner"]],
        ["bystander, strict", s7["bystander"]],
        ["owner, loose (strict, or transcript mentions the slug_dir)", s7["owner_loose"]],
        ["bystander, loose — genuine misroutes", s7["bystander_loose"]],
        ["slug not in registry or bus", s7["unknown_slug"]],
        ["notices the hook logged (since cutoff)", res["hook_log"]["notices"]],
    ]))
    A("")
    A(md_table(["slug", "owner (strict)", "owner (loose)", "bystander (strict)",
                "owner transcripts", "bystander transcripts"],
               [[k, v["owner"], v["owner_loose"], v["bystander"],
                 v["owner_transcripts"], v["bystander_transcripts"]]
                for k, v in s7["per_slug"].items()]))
    A("")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", default="2026-09-01",
                    help="recency cutoff (YYYY-MM-DD). Sections 6-7 only cover slugs "
                         "created on or after it. Default 2026-09-01.")
    ap.add_argument("--round-gap", type=float, default=10.0,
                    help="minutes of silence that start a new reviewer round (default 10)")
    ap.add_argument("--refresh-transcripts", action="store_true",
                    help="ignore the transcript scan cache")
    ap.add_argument("--out-dir", default=None,
                    help="where to write eval-baseline.{md,json} (default <state>/logs)")
    ap.add_argument("--state-dir", default=None, help="registry + logs root (default: paths.STATE_DIR)")
    ap.add_argument("--bus-dir", default=None, help="bus root (default: paths.BUS_ROOT)")
    ap.add_argument("--transcript-glob", default=None,
                    help="Claude transcripts to scan (default: ~/.claude/projects/*/*.jsonl)")
    args = ap.parse_args(argv)
    _rebind_roots(args.state_dir, args.bus_dir, args.transcript_glob)
    if not args.out_dir:
        args.out_dir = LOG_DIR

    since = parse_ts(args.since + "T00:00:00Z")
    slugs = collect_slugs()

    now = dt.datetime.now(dt.timezone.utc)
    latest = max([e["_ts"] for i in slugs.values() for e in i["events"] if e["_ts"]] or [now])
    ref_now = max(now, latest)

    s1 = section1(slugs, since)
    window = [r["slug"] for r in s1 if r["in_window"]]

    inw = [r for r in s1 if r["in_window"]]
    ttv_all = []
    for slug in window:
        for c in slugs[slug]["comments"]:
            d = c.get("decision") or {}
            if not c.get("decision_request") or verdict_column(d.get("verdict")) is None:
                continue
            m = mins(parse_ts(c.get("created_at")), parse_ts(d.get("ts")))
            if m is not None and m >= 0:
                ttv_all.append(m)
    vagg = collections.Counter()
    dagg = collections.Counter()
    for r in inw:
        for k, n in r["verdicts"].items():
            vagg[k] += n
        for k, n in r["delivery"].items():
            dagg[k] += n
    ag = sum(r["agent_events"] for r in inw)
    rv = sum(r["reviewer_events"] for r in inw)
    s1_agg = {
        "slugs": len(inw),
        "comments": sum(r["comments"] for r in inw),
        "decision_requests": sum(r["decision_requests"] for r in inw),
        "verdicts": dict(vagg),
        "time_to_verdict_median": r1(med(ttv_all)),
        "time_to_verdict_p90": r1(pct(ttv_all, 0.9)),
        "agent_events": ag, "reviewer_events": rv,
        "agent_share_pct": round(100 * ag / (ag + rv), 1) if (ag + rv) else None,
        "authoring_burst_15m": sum(r["authoring_burst_15m"] for r in inw),
        "session_push": sum(r["session_push"] for r in inw),
        "delivery": dict(dagg),
        "versions": sum(r["versions"] for r in inw),
    }

    s2 = section2(slugs, args.round_gap)
    multi = [r for r in s2 if r["verdicts"] > 1]
    s2_sum = {
        "rounds": len(s2),
        "slugs": len({r["slug"] for r in s2}),
        "median_verdicts_per_round": med([r["verdicts"] for r in s2]),
        "median_duration_min": r1(med([r["duration_min"] for r in s2])),
        "median_first_reaction_min": r1(med([r["first_reaction_min"] for r in s2
                                             if r["first_reaction_min"] is not None])),
        "multi_rounds": len(multi),
        "reacted_mid_round": sum(1 for r in multi if r["reacted_mid_round"]),
        "reacted_mid_round_pct": round(
            100 * sum(1 for r in multi if r["reacted_mid_round"]) / len(multi), 1) if multi else None,
    }

    s3 = section3(slugs, ref_now)
    s4 = section4(slugs)
    s5 = section5(slugs)

    ids = set()
    for slug in window:
        info = slugs[slug]
        ids |= {c.get("id") for c in info["comments"] if c.get("id")}
        ids |= {e.get("comment_id") for e in info["events"] if e.get("comment_id")}
    ids = {i for i in ids if i and ID_RE.match(str(i))}
    print(f"[eval] scanning transcripts for {len(ids)} comment ids "
          f"across {len(window)} in-window slugs...", file=sys.stderr)
    sightings, file_ids, notices = scan_transcripts(ids, refresh=args.refresh_transcripts)

    s6 = section6(slugs, window, sightings)
    lats = [d["seen_min"] for d in s6["detail"] if d["seen_min"] is not None]
    hows = collections.Counter(d["how"] for d in s6["detail"])
    s6_sum = {
        "verdicts": len(s6["detail"]),
        "seen": len(lats),
        "seen_pct": round(100 * len(lats) / len(s6["detail"]), 1) if s6["detail"] else None,
        "median_min": r1(med(lats)), "p90_min": r1(pct(lats, 0.9)),
        "how": dict(hows),
    }
    s7 = section7(slugs, notices, file_ids)

    res = {
        "meta": {
            "generated_at": now.isoformat(timespec="seconds"),
            "since": args.since,
            "reference_now": ref_now.isoformat(timespec="seconds"),
            "round_gap_min": args.round_gap,
            "slugs_total": len(slugs),
            "slugs_in_window": len(window),
            "window_slugs": window,
            "transcripts_scanned": len(glob.glob(TRANSCRIPT_GLOB)),
        },
        "s1": s1, "s1_aggregate": s1_agg,
        "s2": s2, "s2_summary": s2_sum,
        "s3": s3, "s4": s4, "s5": s5,
        "s6": s6, "s6_summary": s6_sum,
        "s7": s7,
        "hook_log": hook_log_stats(since),
    }

    os.makedirs(args.out_dir, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)
    jp = os.path.join(args.out_dir, "eval-baseline.json")
    mp = os.path.join(args.out_dir, "eval-baseline.md")
    json.dump(res, open(jp, "w", encoding="utf-8"), indent=1, default=str)
    open(mp, "w", encoding="utf-8").write(render_md(res))
    print(f"[eval] wrote {jp}", file=sys.stderr)
    print(f"[eval] wrote {mp}", file=sys.stderr)


if __name__ == "__main__":
    main()
