#!/usr/bin/env python3
"""Coordinator cost meter for a Claude Code session transcript (simplification plan, Stage 0).

    python3 -I scripts/orch_cost.py SESSION.jsonl [--since 2026-10-31T00:00] [--json OUT]

Read-only. Main thread only; usage de-duplicated by API message id. Cost applies
the session's own Claude Code costUSD rate (its `cost-state` record) to weighted
tokens: input 1, output 5, cache read 0.1, cache write 1.25 (2 for 1-hour).
Prints one compact table; --json writes the aggregate receipt (no message text).
These are the analyzers behind docs/validation/simplification-plan-20261104.md.
"""

from __future__ import annotations

import argparse
import base64
import collections
import json
import re
import statistics
import struct
import sys
from datetime import datetime, timezone

FALLBACK_USD_PER_UNIT = 2.93e-6  # no cost-state record: the plan's Opus rate

ANN = re.compile(r"(^|[\s;&|(\"'\[,])annotate[\"']?[\s,]")
ANNO = {"page_draft", "annotate_publish", "annotate_read", "annotate_resolve", "annotate_other", "annotate_store_read"}
CTX_ERR = re.compile(r"NOT PUBLISHED|Traceback \(most recent|HTTP 409|number is ambiguous|unknown command|"
                     r"invalid choice|No such file|command not found")
ACT_ERR = re.compile(r"NOT PUBLISHED|Traceback \(most|HTTP 409|ambiguous|ERROR|error:|refus", re.I)
CARDS = re.compile(r"```cards.*?```", re.S)
WAITY = {"wait_mail", "orch_notes"}
GROUPS = {  # the plan's "cost by what the coordinator was doing" rows
    "wait_mail": "waiting on workers and mail", "reply_no_tool": "closing message of a turn",
    "read_search": "shell reads/search", "read_search_shell": "shell reads/search",
    "orca_msg_lifecycle": "Orca messaging and lifecycle", "beads": "Beads", "orch_notes": "coordinator notes",
    "worker_brief": "worker briefs", "page_draft": "page drafts", "git_gh": "Git/GitHub",
    "annotate_read": "annotate commands", "annotate_publish": "annotate commands",
    "annotate_resolve": "annotate commands", "annotate_other": "annotate commands",
    "annotate_store_read": "raw page store reads", "dispatch": "dispatch", "screens_pages": "screenshots and pages",
    "release_rollout": "release and rollout", "tests": "test runs"}


def ts(s: str) -> float:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def classify(name: str, inp: dict) -> str:
    if name == "Monitor":
        return "wait_mail"
    if name in ("Agent", "SendMessage", "TaskStop"):
        return "subagents"
    if name == "Skill":
        return "annotate_other" if "annotate" in json.dumps(inp) else "skills_tools"
    if name in ("Write", "Edit", "NotebookEdit"):
        p = inp.get("file_path", "")
        if re.search(r"/page/v\d+|draft|/source/|/shots/|cards[^/]*\.(json|md)$|reviews/", p):
            return "page_draft"
        if re.search(r"/specs/|brief|prompt", p, re.I):
            return "worker_brief"
        if re.search(r"pending|/memory/|handoff|DECISIONS|STATE|mail\.txt", p):
            return "orch_notes"
        return "code_edit"
    if name == "Read":
        p = inp.get("file_path", "")
        if re.search(r"\.(png|jpe?g|gif|webp)$", p, re.I):
            return "screens_pages"
        if re.search(r"comments\.json|current\.(html|meta)|/versions/v|/content/", p):
            return "annotate_store_read"
        if re.search(r"/page/v\d+|draft|/source/", p):
            return "page_draft"
        if re.search(r"pending|/memory/|handoff|DECISIONS|STATE|mail\.txt", p):
            return "orch_notes"
        return "read_search"
    if name in ("Grep", "Glob"):
        return "read_search"
    if name != "Bash":
        return "skills_tools"
    c = inp.get("command", "")
    if re.search(r"orca-quiet-wait|drain_mail|drain-all|watch-terminal|orchestration (check|inbox|worker-list|"
                 r"worker-show|worker-read)|terminal (read|wait)|terminal list", c):
        return "wait_mail"
    if re.search(r"orchestration (worker-start|task-create|dispatch|run-use|run-create)|terminal create|"
                 r"tab create|worktree create", c):
        return "dispatch"
    if re.search(r"orchestration (send|reply|ask|worker-release|worker-stop|task-update)|terminal (send|close)|"
                 r"worktree rm|tab close", c):
        return "orca_msg_lifecycle"
    if ANN.search(c) or re.search(r"\['annotate'|pubfix|m\dd?-resolve", c):
        if re.search(r"pubfix|annotate[\"\']?[\s,]+[\"\']?(publish|new|ask|draft)", c):
            return "annotate_publish"
        if re.search(r"m\dd?-resolve|annotate[\"\']?[\s,]+[\"\']?(resolve|addressed|withdraw|ack)", c):
            return "annotate_resolve"
        if re.search(r"annotate[\"\']?[\s,]+[\"\']?(inbox|open-cards|workspace|status|show)", c):
            return "annotate_read"
        return "annotate_other"
    if re.search(r"comments\.json|current\.(html|meta)|/versions/v\d+\.html|/content/", c):
        return "annotate_store_read"
    if re.search(r"/page/v\d+|m\dd?-(v\d+|build-v)|-sec\.md|/shots/draft|cards-\d+", c):
        return "page_draft"
    if re.search(r"pending\.txt|/memory/|handoff|mail\.txt", c):
        return "orch_notes"
    if re.search(r"/specs/|brief", c):
        return "worker_brief"
    if re.search(r"(^|[\s;&|(])bd\s|\'bd\'|BEADS_ACTOR", c):
        return "beads"
    if re.search(r"\buv (build|tool|pip)|sync-skills|restart_record|(^|\s)ssh\s|--environment|launchctl|tailscale|"
                 r"gh release|git tag|\.whl|pip install|update --apply|sudo ", c):
        return "release_rollout"
    if re.search(r"screenshot|orca browser|curl |\.png|\.jpe?g", c):
        return "screens_pages"
    if re.search(r"pytest|gradle|xcodebuild|npm (run )?test|swift test|bench\.py|run_full", c):
        return "tests"
    if re.search(r"^\s*(cd \S+ && )?(git|gh)\s|gitleaks", c):
        return "git_gh"
    return "read_search_shell"


def image_tokens(b64: str) -> int:
    try:
        raw = base64.b64decode(b64[:40000] + "=" * (-len(b64[:40000]) % 4))
    except Exception:  # noqa: BLE001 - a broken image still costs a default
        return 1600
    w = h = None
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", raw[16:24])
    elif raw[:2] == b"\xff\xd8":
        i = 2
        while i < len(raw) - 9:
            if raw[i] != 0xFF:
                i += 1
                continue
            if raw[i + 1] in (0xC0, 0xC1, 0xC2):
                h, w = struct.unpack(">HH", raw[i + 5:i + 9])
                break
            i += 2 + struct.unpack(">H", raw[i + 2:i + 4])[0]
    if not w:
        return 1600
    s = min(1.0, 1568 / max(w, h))  # the API downscales the long side
    return int(w * s * h * s / 750)


def content_size(content) -> tuple[int, int]:
    """(text chars, image tokens) of a tool result or message."""
    if isinstance(content, str):
        return len(content), 0
    ch = im = 0
    for b in content or []:
        if b.get("type") == "text":
            ch += len(b.get("text", ""))
        elif b.get("type") == "image":
            im += image_tokens(b.get("source", {}).get("data", ""))
        elif b.get("type") in ("tool_reference", "document"):
            ch += len(json.dumps(b))
    return ch, im


def result_text(content) -> str:
    return content if isinstance(content, str) else " ".join(
        x.get("text", "") for x in content or [] if x.get("type") == "text")


def trigger_kind(text: str) -> str:
    t = text.lstrip()
    if t.startswith("<task-notification"):
        return "wake:background-task-exit"
    if t.startswith("<system-reminder"):
        return "wake:system-reminder"
    if t.startswith("<command-") or t.startswith("<local-command"):
        return "user:slash-command"
    if "orca" in t[:200].lower() and ("worker" in t[:400].lower() or "orchestration" in t[:400].lower()):
        return "wake:orca-message"
    return "user:typed"


def units(c: dict) -> float:
    return c["inp"] + c["out"] * 5 + c["cr"] * 0.1 + (c["cw"] - c["cw1h"]) * 1.25 + c["cw1h"] * 2


def q(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))] if xs else 0


def read(path: str, since: float | None = None) -> dict:
    """One pass: API calls, context additions, wakes and annotate actions."""
    calls, by_mid, ann_mid = [], {}, {}
    tool_cat, items, ev, pend_ev = {}, [], [], {}
    triggers, errors, per_cat = collections.Counter(), collections.Counter(), collections.Counter()
    turns, round_marks, outcomes = [], [], collections.Counter()
    shape = collections.Counter()
    versions: set[str] = set()  # page versions drafted: vN.md / draft-vN.md named in tool input
    cost_state = None
    api_error_continuations = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            t = d.get("type")
            if t == "cost-state":
                cost_state = d
                continue
            if d.get("isSidechain"):
                continue
            if since and d.get("timestamp") and ts(d["timestamp"]) < since:
                continue
            if t == "assistant":
                m = d["message"]
                mid = m.get("id")
                u = m.get("usage") or {}
                if mid not in ann_mid:  # the per-action analyzer keeps every message, synthetic too
                    a = dict(inp=u.get("input_tokens", 0), out=u.get("output_tokens", 0),
                             cr=u.get("cache_read_input_tokens", 0), cw=u.get("cache_creation_input_tokens", 0),
                             cw1h=(u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens", 0), ntools=0)
                    a["ctx"] = a["inp"] + a["cr"] + a["cw"]
                    ann_mid[mid] = a
                a = ann_mid[mid]
                if mid not in by_mid:
                    c = dict(idx=len(calls), ts=ts(d["timestamp"]), inp=u.get("input_tokens", 0),
                             out=u.get("output_tokens", 0),
                             think=(u.get("output_tokens_details") or {}).get("thinking_tokens", 0),
                             cr=u.get("cache_read_input_tokens", 0), cw=u.get("cache_creation_input_tokens", 0),
                             cw1h=(u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens", 0), tools=[])
                    c["ctx"] = c["inp"] + c["cr"] + c["cw"]
                    if m.get("model") == "<synthetic>" or c["ctx"] == 0:
                        by_mid[mid] = None
                    else:
                        by_mid[mid] = c
                        calls.append(c)
                        if not turns:
                            turns.append(dict(kind="start", calls=[], cats=collections.Counter()))
                        turns[-1]["calls"].append(c)
                c = by_mid[mid]
                for b in m.get("content") or []:
                    if b.get("type") != "tool_use":
                        continue
                    inp = b.get("input") or {}
                    cat = classify(b["name"], inp)
                    a["ntools"] += 1
                    if c is not None:
                        tool_cat[b["id"]] = cat
                        c["tools"].append((cat, len(json.dumps(inp))))
                        per_cat[cat] += 1
                        turns[-1]["cats"][cat] += 1
                        cmd = inp.get("command", "") if b["name"] == "Bash" else ""
                        if re.search(r"orchestration worker-start", cmd):
                            outcomes["worker_start"] += 1
                    # annotate actions, with throwaway page builders counted as drafting
                    acat = cat
                    if acat not in ANNO and re.search(r"/tmp/m\dd?-|-sec\.md|cards[-.]", inp.get("file_path", "")):
                        acat = "page_draft"
                    blob = json.dumps(inp)
                    versions.update(re.findall(r"(?:/page/v|draft-v)(\d+)\.md", blob))
                    if acat not in ANNO and ("```cards" in blob or re.search(
                            r'\\"number\\":\s*\d+.{0,200}\\"(prompt|options|kind)\\"', blob)):
                        acat = "page_draft"
                    if acat not in ANNO:
                        continue
                    txt = inp.get("command") or inp.get("content") or inp.get("new_string") or ""
                    cards = sum(len(x) for x in CARDS.findall(txt)) + (
                        len(txt) if re.search(r"cards[^/]*\.json$", inp.get("file_path", "")) else 0)
                    if not cards:
                        cards = sum(len(x) for x in re.findall(r'\[\{"number":.*?\}\]', txt, re.S))
                    e = dict(cat=acat, call=a, in_chars=len(blob), cards_chars=cards, res_chars=0, err=False, items=0,
                             cmd=inp.get("command", "")[:300])
                    if acat == "annotate_resolve":
                        m2 = re.search(r"(resolve|addressed|withdraw)\s+\S+\s+(.*?)(\s--|$)", e["cmd"])
                        e["items"] = len(m2.group(2).split()) if m2 else 1
                    ev.append(e)
                    pend_ev[b["id"]] = e
                if c is not None:
                    c["text_chars"] = c.get("text_chars", 0) + sum(
                        len(b.get("text", "")) for b in m.get("content") or [] if b.get("type") == "text")
            elif t == "user":
                cont = d.get("message", {}).get("content")
                texts = [cont] if isinstance(cont, str) else [
                    b.get("text", "") for b in cont or [] if b.get("type") == "text"]
                for tx in texts:
                    if tx.lstrip().startswith("[annotate] Round submitted"):
                        round_marks.append(len(ev))
                    if "cut off by an API error" in tx[:120]:
                        api_error_continuations += 1
                    if not tx.startswith("Base directory for this skill"):
                        turns.append(dict(kind=trigger_kind(tx), calls=[], cats=collections.Counter()))
                nxt = len(calls)
                if isinstance(cont, str):
                    k = trigger_kind(cont)
                    triggers[k] += 1
                    items.append((nxt, k, len(cont) / 4))
                    continue
                for b in cont or []:
                    if b.get("type") == "tool_result":
                        cat = tool_cat.get(b.get("tool_use_id"), "unknown")
                        ch, im = content_size(b.get("content"))
                        items.append((nxt, cat, ch / 4 + im))
                        txt = result_text(b.get("content"))
                        if b.get("is_error") or CTX_ERR.search(txt[:4000] or ""):
                            errors[cat] += 1
                        e = pend_ev.pop(b.get("tool_use_id"), None)
                        if e:
                            e["res_chars"] = len(txt)
                            e["err"] = bool(b.get("is_error")) or bool(ACT_ERR.search(txt[:3000]))
                            if e["cat"] == "annotate_read":
                                shape["inbox_chars"] += len(txt)
                                shape["inbox_padding_chars"] += sum(len(x) - 1 for x in re.findall(r" {2,}", txt))
                                shape["inbox_publish_event_lines"] += len(re.findall(
                                    r"plan_published|version_published|page_published", txt))
                            if e["cat"] == "annotate_resolve":
                                shape["resolve_chars"] += len(txt)
                                shape["resolve_url_chars"] += sum(len(x) for x in re.findall(r"https?://\S+", txt))
                    elif b.get("type") == "text":
                        text = b.get("text", "")
                        skill = text.startswith("Base directory")
                        k = trigger_kind(text)
                        if not skill:
                            triggers[k] += 1
                        items.append((nxt, "skills_tools" if skill else k, len(text) / 4))
            elif t == "attachment":
                att = d.get("attachment") or {}
                if att.get("type") != "hook_success":
                    items.append((len(calls), "harness_attachments", len(json.dumps(att)) / 4))
    return dict(calls=calls, items=items, triggers=triggers, errors=errors, per_cat=per_cat, turns=turns,
                round_marks=round_marks, outcomes=outcomes, ev=ev, shape=shape, cost_state=cost_state,
                api_error_continuations=api_error_continuations, versions=len(versions))


def usd_per_unit(cost_state: dict | None) -> tuple[float, str]:
    if not cost_state:
        return FALLBACK_USD_PER_UNIT, "assumed"
    usage = cost_state.get("modelUsage") or {}
    mu = usage.get("claude-opus-5-5") or next(iter(usage.values()), None)
    if not mu:
        return FALLBACK_USD_PER_UNIT, "assumed"
    u = (mu["inputTokens"] + 5 * mu["outputTokens"] + 0.1 * mu["cacheReadInputTokens"]
         + 1.25 * mu["cacheCreationEphemeral5mInputTokens"] + 2 * mu["cacheCreationEphemeral1hInputTokens"])
    return (mu["costUSD"] / u, "session cost-state") if u else (FALLBACK_USD_PER_UNIT, "assumed")


def actions(r: dict, k: float) -> dict:
    """Goal 1: what each annotate action cost in commands, tokens and dollars."""
    ev = r["ev"]
    for e in ev:
        c = e["call"]
        e["usd"] = units(c) / max(1, c["ntools"]) * k
        e["reread"] = c["ctx"] / max(1, c["ntools"])
        e["tok"] = (e["in_chars"] + e["res_chars"]) / 4

    def summarize(eps):
        return dict(n=len(eps), commands_median=q([len(x) for x in eps], .5), commands_p90=q([len(x) for x in eps], .9),
                    written_tokens_median=round(q([sum(e["in_chars"] for e in x) / 4 for x in eps], .5)),
                    card_json_tokens_median=round(q([sum(e["cards_chars"] for e in x) / 4 for x in eps], .5)),
                    result_tokens_median=round(q([sum(e["res_chars"] for e in x) / 4 for x in eps], .5)),
                    failed_attempts_total=sum(sum(1 for e in x if e["err"]) for x in eps),
                    usd_median=round(q([sum(e["usd"] for e in x) for x in eps], .5), 2),
                    usd_p90=round(q([sum(e["usd"] for e in x) for x in eps], .9), 2))
    pubs, acc = [], []
    for e in ev:
        if e["cat"] in ("page_draft", "annotate_store_read", "annotate_other", "annotate_publish"):
            acc.append(e)
            if e["cat"] == "annotate_publish" and not e["err"]:
                pubs.append(acc)
                acc = []
    rounds = []
    marks = r["round_marks"]
    for i, start in enumerate(marks):
        x = []
        for e in ev[start:marks[i + 1] if i + 1 < len(marks) else len(ev)]:
            if e["cat"] == "annotate_publish":
                break
            if e["cat"] in ("annotate_read", "annotate_store_read", "annotate_other"):
                x.append(e)
        if x:
            rounds.append(x)
    res = [e for e in ev if e["cat"] == "annotate_resolve"]
    publish = [e for e in ev if e["cat"] == "annotate_publish"]
    drafting = [e for e in ev if e["cat"] in ("page_draft", "annotate_store_read", "annotate_other", "annotate_publish")]
    by = collections.defaultdict(lambda: dict(commands=0, tokens=0.0, usd=0.0, failed=0))
    for e in ev:
        b = by[e["cat"]]
        b["commands"] += 1
        b["tokens"] += e["tok"]
        b["usd"] += e["usd"]
        b["failed"] += e["err"]
    return {
        "read_one_round": summarize(rounds),
        "publish_one_update": {**summarize(pubs), "attempts": len(publish),
                               "attempts_failed": sum(e["err"] for e in publish),
                               "versions_drafted": r["versions"],
                               "commands_per_version": round(len(drafting) / r["versions"], 1) if r["versions"] else None,
                               "tokens_per_version": round(sum(e["tok"] for e in drafting) / r["versions"])
                               if r["versions"] else None},
        "resolve": dict(commands=len(res), items=sum(max(1, e["items"]) for e in res), failed=sum(e["err"] for e in res),
                        tokens_per_command=round(statistics.median([e["tok"] for e in res])) if res else 0,
                        usd_total=round(sum(e["usd"] for e in res), 2)),
        "by_category": {c: dict(v, tokens=round(v["tokens"]), usd=round(v["usd"], 2)) for c, v in sorted(by.items())},
        "total": dict(commands=len(ev), tokens=round(sum(e["tok"] for e in ev)), usd=round(sum(e["usd"] for e in ev), 2),
                      failed=sum(e["err"] for e in ev), failed_usd=round(sum(e["usd"] for e in ev if e["err"]), 2),
                      card_json_tokens=round(sum(e["cards_chars"] for e in ev) / 4),
                      result_tokens=round(sum(e["res_chars"] for e in ev) / 4),
                      result_p90_tokens=round(q([e["res_chars"] / 4 for e in ev], .9)),
                      result_max_tokens=round(max([e["res_chars"] / 4 for e in ev] or [0]))),
        "output_shape": dict(r["shape"]),
    }


def report(name: str, r: dict) -> dict:
    calls = r["calls"]
    n = len(calls)
    if not n:
        raise SystemExit("orch_cost: no API calls in the window")
    k, rate_source = usd_per_unit(r["cost_state"])
    U = sum(units(c) for c in calls)
    tot = collections.Counter()
    for c in calls:
        for f in ("inp", "out", "cr", "cw"):
            tot[f] += c[f]
    active = sum(b["ts"] - a["ts"] for a, b in zip(calls, calls[1:]) if b["ts"] - a["ts"] < 1800) / 3600
    ctxs = sorted(c["ctx"] for c in calls)
    resets = [i for i in range(1, n) if calls[i]["ctx"] < 0.6 * calls[i - 1]["ctx"]]
    reset_set = set(resets)
    growth = sum(max(0, calls[i]["ctx"] - calls[i - 1]["ctx"]) for i in range(1, n) if i not in reset_set)
    # tokens each source adds to the conversation, scaled to the measured growth
    est = collections.Counter()
    for after, cat, tok in r["items"]:
        if after < n:
            est[cat] += tok
    for c in calls:
        tin = sum(s for _, s in c["tools"]) / 4
        for cat, s in c["tools"]:
            est[cat] += s / 4
        est["assistant_reasoning_text"] += max(0, c["out"] - c["think"] - tin) + c["think"]
    E = sum(est.values())
    calib = growth / E if E else 1
    callcost = collections.Counter()
    for c in calls:
        cats = [t for t, _ in c["tools"]] or ["reply_no_tool"]
        for cat in cats:
            callcost[cat] += units(c) / len(cats)
    by_category = {cat: dict(tool_calls=r["per_cat"].get(cat, 0), cost_share=round(callcost.get(cat, 0) / U, 4),
                             usd=round(callcost.get(cat, 0) * k, 2),
                             context_added_tokens=round(est.get(cat, 0) * calib),
                             context_added_share=round(est.get(cat, 0) / E, 4) if E else 0,
                             errors=r["errors"].get(cat, 0))
                   for cat in sorted(set(est) | set(callcost), key=lambda x: -callcost.get(x, 0))}
    groups = collections.Counter()
    for cat, v in by_category.items():
        groups[GROUPS.get(cat, "other")] += v["cost_share"]
    miss = [c for c in calls if c["cw"] > 0.5 * c["ctx"] and c["ctx"] > 50000]
    turn_kinds = collections.defaultdict(lambda: dict(n=0, usd=0.0, only_waited=0))
    for tr in r["turns"]:
        if tr["calls"]:
            s = turn_kinds[tr["kind"]]
            s["n"] += 1
            s["usd"] += sum(units(c) for c in tr["calls"]) * k
            s["only_waited"] += set(tr["cats"]) <= WAITY
    hours = collections.Counter(int(c["ts"] // 3600) for c in calls)
    est_usd = U * k
    rounds = len(r["round_marks"])
    workers = r["outcomes"]["worker_start"]
    bg = turn_kinds.get("wake:background-task-exit", {"n": 0, "usd": 0})
    act = actions(r, k)
    return {
        "name": name, "rate_source": rate_source, "usd_per_weighted_token": k,
        "span_utc": [datetime.fromtimestamp(calls[0]["ts"], timezone.utc).strftime("%Y-%m-%d %H:%M"),
                     datetime.fromtimestamp(calls[-1]["ts"], timezone.utc).strftime("%Y-%m-%d %H:%M")],
        "wall_hours": round((calls[-1]["ts"] - calls[0]["ts"]) / 3600, 1), "active_hours": round(active, 1),
        "api_calls": n, "median_calls_per_hour": sorted(hours.values())[len(hours) // 2],
        "context": dict(median=ctxs[n // 2], p90=ctxs[int(n * .9)], max=ctxs[-1]),
        "growth_tokens_per_active_hour": round(growth / active) if active else 0, "compactions": len(resets),
        "cost_share": dict(cache_read=round(tot["cr"] * .1 / U, 3),
                           cache_write=round(sum((c["cw"] - c["cw1h"]) * 1.25 + c["cw1h"] * 2 for c in calls) / U, 3),
                           output=round(tot["out"] * 5 / U, 3)),
        "cache_expiry_calls": dict(calls=len(miss), cost_share=round(sum(units(c) for c in miss) / U, 3)),
        "est_usd": round(est_usd, 2), "usd_per_wall_hour": round(est_usd / max(1e-9, (calls[-1]["ts"] - calls[0]["ts"]) / 3600), 2),
        "wakes": dict(background_exit=bg["n"], orca_nudge=r["triggers"].get("wake:orca-message", 0),
                      typed_or_delivered=r["triggers"].get("user:typed", 0)),
        "usd_per_background_wake": round(bg["usd"] / bg["n"], 2) if bg["n"] else None,
        "turns": {kind: dict(v, usd=round(v["usd"], 2)) for kind, v in turn_kinds.items()},
        "rounds_delivered": rounds, "workers_started": workers,
        "usd_per_round": round(est_usd / rounds, 2) if rounds else None,
        "usd_per_worker_started": round(est_usd / workers, 2) if workers else None,
        "api_error_continuations": r["api_error_continuations"],
        "category_groups": {g: round(v, 4) for g, v in groups.most_common()},
        "by_category": by_category,
        "errors_total": sum(r["errors"].values()),
        "annotate": {**act, "share_of_cost": round(act["total"]["usd"] / est_usd, 4) if est_usd else 0},
    }


def table(rep: dict) -> str:
    a = rep["annotate"]
    rnd, pub, res = a["read_one_round"], a["publish_one_update"], a["resolve"]
    w = rep["wakes"]
    rows = [
        ("session", f"{rep['name']}  {rep['span_utc'][0]} – {rep['span_utc'][1]} UTC"),
        ("cost", f"${rep['est_usd']:,.2f} ({rep['rate_source']}); ${rep['usd_per_wall_hour']}/wall h"),
        ("hours wall / active", f"{rep['wall_hours']} / {rep['active_hours']}"),
        ("API calls; median per hour", f"{rep['api_calls']:,}; {rep['median_calls_per_hour']}"),
        ("context median / p90 / max", "{median:,} / {p90:,} / {max:,}".format(**rep["context"])),
        ("growth per active h; compactions", f"{rep['growth_tokens_per_active_hour']:,}; {rep['compactions']}"),
        ("share read / write / output", "{cache_read:.0%} / {cache_write:.0%} / {output:.0%}".format(**rep["cost_share"])),
        ("calls after cache expiry", f"{rep['cache_expiry_calls']['calls']} = {rep['cache_expiry_calls']['cost_share']:.0%} of cost"),
        ("wakes bg exit / Orca / typed", f"{w['background_exit']} / {w['orca_nudge']} / {w['typed_or_delivered']}"
                                         + (f"; ${rep['usd_per_background_wake']} per bg wake" if rep["usd_per_background_wake"] else "")),
        ("rounds; workers started", f"{rep['rounds_delivered']}; {rep['workers_started']}"
                                    + (f"  (${rep['usd_per_round']}/round" if rep["usd_per_round"] else "")
                                    + (f", ${rep['usd_per_worker_started']}/worker)" if rep["usd_per_worker_started"] else (")" if rep["usd_per_round"] else ""))),
        ("top cost groups", ", ".join(f"{g} {v:.1%}" for g, v in list(rep["category_groups"].items())[:5])),
        ("annotate share", f"{a['share_of_cost']:.1%} (${a['total']['usd']}); {a['total']['commands']} commands, "
                           f"{a['total']['failed']} printed an error"),
        ("read one round", f"median {rnd['commands_median']} commands (p90 {rnd['commands_p90']}), "
                           f"{rnd['result_tokens_median']} tokens, ${rnd['usd_median']}"),
        ("resolve", f"{res['commands']} commands for {res['items']} items, {res['tokens_per_command']} tokens each, "
                    f"{res['failed']} failed"),
        ("publish one update", f"{pub['commands_per_version']} commands, {pub['tokens_per_version']} tokens per version "
                               f"drafted ({pub['versions_drafted']}); {pub['attempts_failed']} of {pub['attempts']} "
                               "attempts printed an error"),
        ("API-error continuations", str(rep["api_error_continuations"])),
    ]
    wid = max(len(r[0]) for r in rows)
    return "\n".join(f"{label:<{wid}}  {value}" for label, value in rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("session", help="a Claude Code session transcript (.jsonl); use a copy")
    ap.add_argument("--since", help="ISO time; ignore records before it")
    ap.add_argument("--json", dest="json_out", help="write the aggregate receipt here")
    args = ap.parse_args(argv)
    since = ts(args.since if "T" in args.since or "+" in args.since else args.since + "T00:00:00Z") if args.since else None
    rep = report(args.session.rsplit("/", 1)[-1][:8], read(args.session, since))
    rep["since"] = args.since
    print(table(rep))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(rep, fh, indent=1)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
