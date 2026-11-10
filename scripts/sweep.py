#!/usr/bin/env python3
"""Hourly housekeeping without an agent: one summary line per check, judgment items to a file.

  sweep.py beads [--beads-dir DIR]     open, ready, stale in-progress, closed without proof
  sweep.py boards                      every owned page's board; guarded fixes and durable follow-ups
  sweep.py disk                        free space, bus size, buses quiet for 30+ days
  sweep.py sessions [--apply]          finished Orca worktrees; --apply removes them
  sweep.py all [--apply]               all checks (--apply affects sessions only)

Writes the summary lines, a blank line, then the items that need a coordinator's
judgment to $ANNOTATE_SWEEP_DIR/latest.txt (default ~/.local/share/annotate-sweeps);
`scripts/run_summary.py` shows the summary lines. No AI runs here. A worktree is
removed only with --apply, only when its PR is merged, its bead is closed and its
tree is clean, and never when it is a main worktree or on DENY.
Board writes require the board's exact path in $ANNOTATE_SWEEP_DIR/apply-boards.txt;
otherwise actions are dry-run. ANNOTATE_BOARD_FOLLOWUPS_ROOT redirects page output
to ROOT/PROJECT/SLUG for read-only rehearsals. No model is woken.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DENY = ("/Users/changlee/orca/workspaces/codex/rebex-library-performance",)
OUT = Path(os.environ.get("ANNOTATE_SWEEP_DIR") or Path.home() / ".local/share/annotate-sweeps")
BUS_ROOT = Path(os.environ.get("ANNOTATE_BUS_ROOT") or Path.home() / ".claude/annotate-bus")
QUIET_DAYS = 30
STALE_HOURS = 24
PROOF_DAYS = 7


def run_json(argv, cwd=None):
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, cwd=cwd, timeout=120)
        data = json.loads(proc.stdout) if proc.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    if isinstance(data, dict) and "ok" in data:
        return data.get("result") if data.get("ok") else None
    return data


def age_hours(stamp, now):
    try:
        then = datetime.datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0
    return (now - then) / 3600


def beads(beads_dir, now):
    bd = ["bd", "list", "--json", "--limit", "0"]
    opened = run_json([*bd, "--status", "open", "--brief"], beads_dir)
    working = run_json([*bd, "--status", "in_progress", "--brief"], beads_dir)
    ready = run_json(["bd", "ready", "--json", "--limit", "0", "--brief"], beads_dir)
    since = time.strftime("%Y-%m-%d", time.gmtime(now - PROOF_DAYS * 86400))
    closed = run_json([*bd, "--status", "closed", "--closed-after", since], beads_dir)
    if None in (opened, working, ready, closed):
        return "beads: bd unavailable here", []
    stale = [b for b in working if age_hours(b.get("updated_at"), now) > STALE_HOURS]
    unproven = [b for b in closed if len((b.get("close_reason") or "").strip()) < 20]
    items = [f"bead {b['id']} in progress, untouched {age_hours(b.get('updated_at'), now):.0f} h: {b.get('title', '')}"
             for b in stale]
    items += [f"bead {b['id']} closed without proof ({(b.get('close_reason') or 'no reason').strip()!r}): "
              f"{b.get('title', '')}" for b in unproven]
    line = (f"beads: {len(opened)} open · {len(ready)} ready · {len(stale)} in progress over {STALE_HOURS} h · "
            f"{len(unproven)} closed without proof")
    return line, items


def disk(now):
    free = shutil.disk_usage(Path.home()).free / 1024 ** 3
    buses = sorted(BUS_ROOT.glob("*/*.ndjson")) if BUS_ROOT.is_dir() else []
    size = sum(p.stat().st_size for p in BUS_ROOT.rglob("*") if p.is_file()) if BUS_ROOT.is_dir() else 0
    quiet = [p for p in buses if now - p.stat().st_mtime > QUIET_DAYS * 86400]
    items = [f"bus {p.parent.name}/{p.stem} quiet {(now - p.stat().st_mtime) / 86400:.0f} days "
             f"(annotate prune-bus --apply archives it)" for p in quiet]
    line = f"disk: {free:.0f} GiB free · buses {size / 1024 ** 3:.1f} GiB · {len(quiet)} quiet buses over {QUIET_DAYS} days"
    return line, items


def bead_ids(texts):
    """Every hyphenated prefix ending in a 3-4 character segment: fld-13hb-auth -> fld-13hb, fld-13hb-auth."""
    found = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9.-]*", " ".join(texts)):
        parts = token.split("-")
        found += ["-".join(parts[:i + 1]) for i in range(1, len(parts))
                  if re.fullmatch(r"[a-z0-9]{3,4}(?:\.[0-9]+)*", parts[i])]
    return list(dict.fromkeys(found))


def bead_closed(worktree, texts):
    """True when the bead named in the PR or branch exists and is closed; None when none is named."""
    found = None
    for bead in bead_ids(texts)[:8]:
        record = run_json(["bd", "show", bead, "--json"], worktree)
        record = record[0] if isinstance(record, list) and record else record
        if isinstance(record, dict) and record.get("id") == bead:
            if record.get("status") != "closed":
                return False
            found = True
    return found


def sessions(apply):
    listing = run_json(["orca", "worktree", "list", "--json", "--limit", "1000"])
    if listing is None:
        return "sessions: orca unavailable here", []
    finished, items, removed = [], [], 0
    for tree in listing.get("worktrees") or []:
        path = tree.get("path") or ""
        if tree.get("hostId") != "local" or tree.get("isMainWorktree"):
            continue
        if any(os.path.realpath(path) == os.path.realpath(d) for d in DENY):
            items.append(f"worktree {path}: on the deny list; not inspected")
            continue
        if not os.path.isdir(path):
            continue
        status = subprocess.run(["git", "--no-optional-locks", "-C", path, "status", "--porcelain"],
                                capture_output=True, text=True)
        if status.returncode or status.stdout.strip():
            continue
        branch = re.sub(r"^refs/heads/", "", tree.get("branch") or "")
        prs = run_json(["gh", "pr", "list", "--head", branch, "--state", "merged", "--json", "number,title,body",
                        "--limit", "1"], path) if branch else None
        if not prs:
            continue
        pr = prs[0]
        closed = bead_closed(path, [os.path.basename(path), branch, pr.get("title") or "", pr.get("body") or ""])
        if closed is None:
            items.append(f"worktree {path}: PR #{pr['number']} merged, tree clean, no bead named; your call")
            continue
        if not closed:
            continue
        finished.append(tree)
        if apply:
            done = run_json(["orca", "worktree", "rm", "--worktree", f"id:{tree['id']}", "--json"])
            removed += done is not None
            items.append(f"worktree {path}: " + ("removed" if done is not None else "removal failed"))
        else:
            items.append(f"worktree {path}: finished (PR #{pr['number']}); sweep.py sessions --apply removes it")
    line = f"sessions: {len(finished)} finished worktrees (PR merged, bead closed, clean tree) · {removed} removed"
    return line, items


def atomic_write(path, output):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix="." + path.name + "-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(output)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


WORKER_CAP = 8  # E2
RESET_GRACE_MIN = 55  # flagged on 2 consecutive hourly runs
REPOS = ("fld-main", "fld-web", "fld-ios", "fld-android")
ISO = r"(\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d)?Z)"
DATED = re.compile(r"\b([A-Z][A-Z0-9]+(?:-[A-Z0-9]+)+)\b[^\n]{0,80}?\bat(?: or |/)after " + ISO)
MERGED = re.compile(r"\bmerged\b[^|\n]{0,40}?\b[0-9a-f]{7,40}\b|\bmerge receipt\b", re.I)
SHA = re.compile(r"\b[0-9a-f]{7,40}\b")
CTX = re.compile(r"\bctx_[0-9a-f]{12}\b")
TERM = re.compile(r"\bterm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
BLOCKED_HEAD = re.compile(r"^\s*BLOCKED BY(?:\s*\([^)]*\))?\s*:\s*")
JOINERS = re.compile(r"(?:[\s,;+&/]|\band\b)*")
SKIP_ASSIGNEES = {"changlee", "m1e"}
LEAD = re.compile(r"LEAD|^m1[a-z]$")  # leads and orchestrators (m1d, m1e, ...)
SORTS = [("ui_freeze", r"UI freeze|UI-LEAD"),
         ("device", r"phone session|phone window|iPhone|Pixel|CarPlay|\bdevices?\b|\badb\b|SMS code|sitting at|\bphones\b"),
         ("outside_party", r"legal|\bApple\b|Mapbox|\bGio\b|external|Cloudflare|Shopify|management|Firebase|signer|Google|vendor"),
         ("owner", r"\bChang\b|\bowner\b|\bcards?")]
CARD = re.compile(r"\bcards?\s*#?(\d{3,6})(?:\s*-\s*(\d{3,6}))?|#(\d{3,6})\b|\bd:q(\d{3,6})\b", re.I)
JUDGED = re.compile(r"AUDIT-\d{4}Z|BOARD-AUDIT|SWEEP-AUTO|\bkeep blocked\b", re.I)
UNSETTLED = ("card-answered", "merge-proof-found", "sort-other", "due")


def sh(*argv, cwd=None):
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=240, cwd=cwd)
    if proc.returncode:
        raise RuntimeError("%s exited %d: %s" % (argv[:3], proc.returncode, proc.stderr[-400:]))
    return proc.stdout


def bd(board, *argv):
    return sh("bd", "--readonly", "-C", board["repo"], *argv)


def first_line(text):
    return (text or "").strip().split("\n", 1)[0]


def parse_ts(s):
    s = s if s.count(":") == 2 else s.replace("Z", ":00Z")
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def blocked_by(b):
    """The BLOCKED BY text of the bead's newest (first) note line, before the first ' | '; None if absent."""
    line = first_line(b.get("notes"))
    m = BLOCKED_HEAD.match(line)
    return line[m.end():].split(" | ", 1)[0].strip() if m else None


def bead_only(seg, prefix):
    """Bead ids when the BLOCKED BY text names nothing but beads, else None."""
    bead_id = re.compile(r"\b" + re.escape(prefix) + r"-[0-9a-z]+(?:\.[0-9]+)*\b")
    ids = bead_id.findall(seg or "")
    return ids if ids and JOINERS.fullmatch(bead_id.sub("", seg)) else None


def card_numbers(text):
    nums = []
    for a, b, c, d in CARD.findall(text or ""):
        if a and b and 0 < int(b) - int(a) <= 20:
            nums += [str(n) for n in range(int(a), int(b) + 1)]
        else:
            nums.append(a or c or d)
    return sorted(set(nums), key=int)


def check_board(beads, ready_count, live, cards, sweep_md, now, prefix, skip_assignees=()):
    """live: {"names", "ctxs", "terms"} sets. cards: {number(str): answered(bool)} for this board's page."""
    by_id = {b["id"]: b for b in beads}
    status = {}
    for b in beads:
        status[b["status"]] = status.get(b["status"], 0) + 1
    counts = dict(status, ready=ready_count, total=len(beads))
    active = [b for b in beads if b["status"] != "closed"]
    live_ids = live["ctxs"] | live["terms"]

    no_owner, guarded = [], []
    for b in active:
        if b["status"] != "in_progress":
            continue
        who = (b.get("assignee") or "").strip()
        notes = b.get("notes") or ""
        if who in live["names"] or set(CTX.findall(notes) + TERM.findall(notes)) & live_ids:
            continue
        row = {"id": b["id"], "assignee": who or None, "note": first_line(notes)[:160]}
        if who in SKIP_ASSIGNEES or who in skip_assignees or LEAD.search(who):
            guarded.append(dict(row, guard="human/orchestrator/lead assignee"))
        else:
            no_owner.append(row)

    reopen, sort, owner_cards, owner_no_card = [], {}, [], []
    for b in active:
        if b["status"] != "blocked":
            continue
        seg = blocked_by(b)
        deps = [d["depends_on_id"] for d in b.get("dependencies") or [] if d.get("type") == "blocks"]
        ids = bead_only(seg, prefix)
        cats = [name for name, pat in SORTS if seg and re.search(pat, seg, re.I)]
        if ids is not None:
            cats.append("beads_only")
            blockers = sorted(set(i for i in ids + deps if i != b["id"]))
            if blockers and all(i in by_id and by_id[i]["status"] == "closed" for i in blockers):
                reopen.append({"id": b["id"], "source": "BLOCKED BY note + dependencies", "blockers": blockers})
        if seg is None:
            cats.append("no_blocked_by_note")
        elif not cats:
            cats.append("other")
        for c in cats:
            sort.setdefault(c, []).append(b["id"])
        nums = card_numbers(seg)
        if nums:
            owner_cards.append({"id": b["id"], "cards": {n: ("answered" if cards.get(n) else "unanswered" if n in cards
                                                             else "not_on_page") for n in nums}})
        elif "owner" in cats and re.search(r"\bChang\b|\bowner\b", seg, re.I):
            owner_no_card.append(b["id"])

    merged_open = []
    for b in active:
        note = first_line(b.get("notes"))
        m = MERGED.search(note)
        if m:
            merged_open.append({"id": b["id"], "status": b["status"], "evidence": m.group(0)[:80], "note": note[:160]})

    dated = {}
    for b in active:
        for field in ("due_at", "defer_until"):
            if b.get(field):
                dated[(b["id"], field)] = {"item": b["id"], "source": field, "at": b[field]}
        for name, at in DATED.findall(first_line(b.get("notes"))):
            dated[(name, at)] = {"item": name, "source": b["id"] + " note", "at": at}
    for name, at in DATED.findall(sweep_md):
        dated.setdefault((name, at), {"item": name, "source": "latest sweep", "at": at})
    due, upcoming = [], []
    for d in sorted(dated.values(), key=lambda d: d["at"]):
        try:
            (due if parse_ts(d["at"]) <= now else upcoming).append(d)
        except ValueError:
            upcoming.append(dict(d, unparsed=True))

    return {"counts": counts, "in_progress_without_live_worker": no_owner, "in_progress_guarded": guarded,
            "blocked_with_closed_blocker": reopen, "blocked_sort": sort, "owner_cards": owner_cards,
            "owner_without_card": owner_no_card, "merge_proof_but_open": merged_open,
            "dated_due": due, "dated_upcoming": upcoming,
            "judged": sorted(b["id"] for b in active if JUDGED.search(b.get("notes") or ""))}


def fp(row):
    return hashlib.sha1(json.dumps(row, sort_keys=True).encode()).hexdigest()[:12]


def flags_of(f):
    flags = {}
    for x in f["blocked_with_closed_blocker"]:
        flags["reopen:" + x["id"]] = fp(x)
    for x in f["in_progress_without_live_worker"]:
        flags["reset:" + x["id"]] = fp([x["id"], x["assignee"]])
    for x in f["in_progress_guarded"]:
        flags["reset-guarded:" + x["id"]] = fp([x["id"], x["assignee"]])
    for x in f["merge_proof_but_open"]:
        kind = "merge-proof-found" if x.get("proof") == "proof found" else "merge-proof-not-found"
        flags["%s:%s" % (kind, x["id"])] = fp([x["status"], x["evidence"]])
    for x in f["owner_cards"]:
        kind = "card-answered" if "answered" in x["cards"].values() else "card-waiting"
        flags["%s:%s" % (kind, x["id"])] = fp(x["cards"])
    for i in f["owner_without_card"]:
        flags["owner-no-card:" + i] = "1"
    for cat, ids in f["blocked_sort"].items():
        for i in ids:
            flags["sort-%s:%s" % (cat.replace("_", "-"), i)] = "1"
    for x in f["dated_due"]:
        flags["due:%s@%s" % (x["item"], x["at"])] = "1"
    return flags


def plan(f, prev, ready_ids, live_board, now):
    """Pure: actions, delta and needs-a-model list from findings f and the previous state (None on the first run)."""
    flags = flags_of(f)
    old = (prev or {}).get("flags", {})
    since = {k: (prev or {}).get("since", {}).get(k, iso(now)) if old.get(k) == flags[k] else iso(now) for k in flags}
    actions = [{"bead": x["id"], "before": "blocked", "after": "open", "rule": "reopen-beads-closed",
                "reason": "BLOCKED BY names only beads and all are closed: " + ", ".join(x["blockers"])}
               for x in f["blocked_with_closed_blocker"]]
    for x in f["in_progress_without_live_worker"]:
        k = "reset:" + x["id"]
        if k in old and (now - parse_ts(since[k])).total_seconds() >= RESET_GRACE_MIN * 60:
            actions.append({"bead": x["id"], "before": "in_progress", "after": "open", "rule": "reset-no-live-worker",
                            "reason": "no live ctx/term id in any note line and assignee %s not live, flagged since %s"
                                      % (x["assignee"], since[k])})
    new = sorted(k for k in flags if old.get(k) != flags[k])
    cleared = sorted(k for k in old if k not in flags)
    judged = set(f["judged"])
    unsettled = [k for k in new if k.split(":", 1)[0] in UNSETTLED
                 and not (prev is None and k.split(":", 1)[1] in judged)]
    new_ready = sorted(set(ready_ids) - set(prev["ready"])) if prev else []
    needs = {"unsettled": unsettled, "new_ready": new_ready if live_board < WORKER_CAP else [],
             "live_board_workers": live_board, "worker_cap": WORKER_CAP}
    state = {"at": iso(now), "flags": flags, "since": since, "ready": sorted(ready_ids)}
    return {"baseline": prev is None, "actions": actions, "new_flags": new, "cleared_flags": cleared,
            "needs_model": needs}, state


def apply_actions(board, actions, stamp, apply):
    for a in actions:
        a["note"] = "SWEEP-AUTO %s %s: %s" % (stamp, a["rule"], a["reason"])
        a["mode"] = "apply" if apply else "dry-run"
        if not apply:
            continue
        cur = json.loads(bd(board, "show", a["bead"], "--json"))[0]
        if cur["status"] != a["before"]:
            a["readback"] = {"skipped": "status is now %s" % cur["status"]}
            continue
        sh("bd", "-C", board["repo"], "update", a["bead"], "--status", a["after"])
        sh("bd", "-C", board["repo"], "note", a["bead"], a["note"])
        back = json.loads(bd(board, "show", a["bead"], "--json"))[0]
        a["readback"] = {"status": back["status"], "note_ok": (back.get("notes") or "").rstrip().endswith(a["note"]),
                         "ok": back["status"] == a["after"] and (back.get("notes") or "").rstrip().endswith(a["note"])}
    return actions


def merge_proof(board, row):
    """git ls-remote + merge-base for the sha in the merge evidence. Never closes anything."""
    shas = SHA.findall(row["evidence"])
    if not shas:
        return "not found (no sha in note)"
    repos = [str(Path(board["repo"]) / r) for r in REPOS] if board["prefix"] == "FLD" else [board["repo"]]
    named = [p for p in repos if Path(p).name in row["note"]] or repos
    for path in named:
        try:
            head = sh("git", "-C", path, "ls-remote", "origin", "refs/heads/main").split()[0]
        except (RuntimeError, IndexError, subprocess.TimeoutExpired):
            continue
        rc = subprocess.run(["git", "-C", path, "merge-base", "--is-ancestor", shas[-1], head],
                            capture_output=True, timeout=60).returncode
        if rc == 0:
            return "proof found"
    return "not found"


def orca_json(*argv):
    return json.loads(sh("orca", *argv))["result"]


def live_workers():
    """FLD's cross-Mac liveness collection, with task names grouped by run for every board."""
    rows, cur, unchecked = [], None, []
    try:
        while True:
            page = orca_json("orchestration", "worker-list", "--include-remote", "--json", "--full", "--limit", "100",
                             *(["--cursor", cur] if cur else []))
            rows += page["workers"]
            cur = page["page"].get("nextCursor")
            if not page["page"].get("hasMore"):
                break
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        unchecked.append({"source": "worker-list", "reason": str(exc)[:200]})
    live = [r for r in rows if ((r.get("projection") or {}).get("liveness") or {}).get("verdict") == "live"]
    ctxs = {r["dispatchId"] for r in live}
    terms = {r["agentTerminalHandle"] for r in live if r.get("agentTerminalHandle")}
    for env in ([], ["--environment", "M5Max"], ["--environment", "M1Max16"]):
        try:
            res = orca_json("terminal", "list", "--json", "--limit", "1000", *env)
            terms |= {t["handle"] for t in res["terminals"] if t.get("connected")}
        except (RuntimeError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
            unchecked.append({"source": "terminal list " + " ".join(env), "reason": str(exc)[:200]})
    names_by_run = {}
    for run in sorted({r["runId"] for r in live if r.get("runId")}):
        try:
            out = orca_json("orchestration", "task-list", "--run", run, "--status", "dispatched", "--json")
            names_by_run[run] = {t["title"].split()[0] for t in out["tasks"] if t.get("title")}
        except (RuntimeError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
            unchecked.append({"source": "task-list " + run, "reason": str(exc)[:200]})
    return {"ctxs": ctxs, "terms": terms, "rows": rows, "live": live, "names_by_run": names_by_run}, unchecked


def board_workers(board, workers):
    roots = {board["repo"], str(Path(board["record"]["slug_dir"]).parent)}
    owner_workspace = (board["record"].get("owner_target") or {}).get("worktree")
    runs = {"run_c9d587c967ba", "run_3822be7d9cd9"} if board["prefix"] == "FLD" else set()
    for row in workers["rows"]:
        workspace = ((row.get("projection") or {}).get("workspace") or {}).get("id") or ""
        if (owner_workspace and workspace == owner_workspace) or any(root in workspace for root in roots):
            runs.add(row.get("runId"))
    names = set().union(*(workers["names_by_run"].get(run, set()) for run in runs))
    names |= {n.replace("GATE-RUNNER-", "GR-") for n in names}
    return {"ctxs": workers["ctxs"], "terms": workers["terms"], "names": names}, sum(
        row.get("runId") in runs for row in workers["live"])


def discover_boards():
    """Newest owned page per board; owner worktree first, page repository second."""
    state_dir = Path(os.environ.get("ANNOTATE_STATE_DIR") or os.environ.get("ANNOTATE_STATE_ROOT")
                     or Path.home() / ".claude/annotate-state/state")
    found, unchecked, cache = {}, [], {}
    for state_file in sorted(state_dir.glob("*.json")):
        try:
            state = json.loads(state_file.read_text())
            entries = state["slugs"].items()
        except (OSError, ValueError, KeyError, TypeError):
            continue
        for slug, record in entries:
            if (not isinstance(record, dict) or not record.get("owner_session") or not record.get("slug_dir")
                    or record.get("archived") or record.get("consolidated_into")):
                continue
            directory = Path(record["slug_dir"])
            if not directory.is_dir() or any((directory / marker).exists()
                                             for marker in ("archived.json", "consolidated.json")):
                continue
            worktree = (record.get("owner_target") or {}).get("worktree") or ""
            owner_path = worktree.split("::", 1)[1] if "::" in worktree else None
            candidates = [owner_path, record.get("repo_dir"), record.get("workspace_root"), str(directory)]
            for repo in dict.fromkeys(p for p in candidates if p and Path(p).is_dir()):
                if repo not in cache:
                    cache[repo] = run_json(["bd", "--readonly", "where", "--json"], repo)
                where = cache[repo]
                if not isinstance(where, dict) or not where.get("path"):
                    continue
                board_path = str(Path(where["path"]).resolve())
                try:
                    prefix = sh("bd", "--readonly", "-C", repo, "config", "get", "issue_prefix").strip()
                    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", prefix):
                        raise ValueError("invalid board prefix")
                    # For folder-owned pages, use the enclosing repository for proof and git user.name.
                    top = subprocess.run(["git", "-C", repo, "rev-parse", "--show-toplevel"],
                                         capture_output=True, text=True, timeout=10)
                    if top.returncode == 0:
                        repo = top.stdout.strip()
                    else:
                        repo = next((str(parent) for parent in (Path(repo), *Path(repo).parents)
                                     if (parent / ".beads").exists()), repo)
                    stamps = [record.get(k) for k in ("workspace_selected_at", "started_at", "owner_claimed_at")]
                    activity = []
                    for stamp in stamps:
                        try:
                            activity.append(float(stamp) if isinstance(stamp, (float, int)) else
                                            datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp())
                        except (ValueError, TypeError, AttributeError):
                            pass
                    for name in ("current.meta.json", "comments.json", "rounds.ndjson"):
                        if (directory / name).is_file():
                            activity.append((directory / name).stat().st_mtime)
                    board = {"path": board_path, "repo": repo, "prefix": prefix,
                             "project": state.get("project") or state_file.stem, "slug": slug, "record": record,
                             "activity": max(activity, default=0)}
                    if board_path not in found or board["activity"] > found[board_path]["activity"]:
                        found[board_path] = board
                except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
                    unchecked.append(f"{slug}: {exc}")
                break
    return sorted(found.values(), key=lambda b: b["path"]), unchecked


def followups_dir(board):
    root = os.environ.get("ANNOTATE_BOARD_FOLLOWUPS_ROOT")
    return Path(root) / board["project"] / board["slug"] if root else Path(board["record"]["slug_dir"])


def verdict_pairs(directory, sources):
    settled = set()
    for path in [directory / "board-verdicts.ndjson", *map(Path, sources)]:
        try:
            for line in path.read_text().splitlines():
                try:
                    verdict = json.loads(line)
                    settled.add((verdict["key"], verdict["fingerprint"]))
                except (ValueError, KeyError, TypeError):
                    continue
        except FileNotFoundError:
            pass
    return settled


def save_followups(board, findings, planned, state, now, previous_dir=None):
    """Carry every judgement until a verdict; changed evidence reopens the same key."""
    directory = followups_dir(board)
    directory.mkdir(parents=True, exist_ok=True)
    items, verdict_sources = {}, set()
    # A new canonical page inherits the pending work and verdicts of its predecessor.
    sources = [Path(previous_dir)] if previous_dir and Path(previous_dir) != directory else []
    sources.append(directory)
    for source in sources:
        if (source / "board-followups.json").exists():
            inherited = json.loads((source / "board-followups.json").read_text())
            verdict_sources.update(inherited.get("verdict_sources", []))
            if source != directory:
                verdict_sources.add(str(source / "board-verdicts.ndjson"))
            items.update({item["key"]: item for item in inherited["items"]})
    keys = set(planned["needs_model"]["unsettled"])
    # Once flagged, changes must be compared even when the item was already judged.
    keys |= {key for key in items if key in state["flags"]}
    keys |= {key for key in items if key.startswith("ready:") and key[6:] in state["ready"]}
    for key in planned["needs_model"]["new_ready"]:
        keys.add("ready:" + key)
    page = shlex.quote(board["project"] + "/" + board["slug"])
    meanings = {"card-answered": "owner card answered; judge unblock", "merge-proof-found": "merge proof found; judge completion",
                "sort-other": "free-text blocker needs judgement", "due": "dated item is due; judge next action",
                "ready": "new ready work; judge dispatch"}
    for key in sorted(keys):
        kind, bead = key.split(":", 1)
        record = next((b for b in findings["beads"] if b["id"] == bead.split("@", 1)[0]), {})
        evidence = {k: record.get(k) for k in ("title", "status", "assignee", "notes", "description",
                                               "dependencies", "due_at", "defer_until")}
        if kind == "card-answered":
            nums = card_numbers(blocked_by(record))
            evidence["cards"] = [c for c in findings.get("cards", []) if str(c["number"]) in nums and not c.get("pending")]
        fingerprint = fp([state["flags"].get(key), evidence])
        old = items.get(key)
        items[key] = {"key": key, "fingerprint": fingerprint,
                      "line": f"{bead}: {meanings.get(kind, kind)}",
                      "since": old["since"] if old and old["fingerprint"] == fingerprint else iso(now),
                      "settle": f'annotate board {page} --settle {shlex.quote(key)} "verdict"'}
    # Update commands on page selection changes without altering evidence fingerprints.
    for key, item in items.items():
        item["settle"] = f'annotate board {page} --settle {shlex.quote(key)} "verdict"'
    payload = {"board": board["path"], "at": iso(now), "items": list(items.values()),
               "verdict_sources": sorted(verdict_sources)}
    atomic_write(directory / "board-followups.json", json.dumps(payload, indent=2) + "\n")
    settled = verdict_pairs(directory, verdict_sources)
    return [item for item in payload["items"] if (item["key"], item["fingerprint"]) not in settled]


def latest_board_sweep(board):
    if board["prefix"] != "FLD":
        return None, ""
    reports = Path(board["repo"]) / "planning/operations/orchestration/run_c9d587c967ba/reports"
    files = sorted(reports.glob("bead-sweep/sweep-*.md"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0))
    return (str(files[-1]), files[-1].read_text()) if files else (None, "")


def board_summary(board, findings, planned, followups):
    counts = findings["counts"]
    line = (f"boards: {board['prefix']} ({board['project']}/{board['slug']}) · "
            + " · ".join(f"{counts.get(k, 0)} {k}" for k in ("open", "ready", "in_progress", "blocked", "closed"))
            + f" · {len(planned['actions'])} actions ({findings['mode']}) · {len(followups)} follow-ups")
    lines = [line, f"Board: {board['path']}", f"Repo: {board['repo']}"]
    lines += [f"{a['mode']}: {a['bead']} {a['before']} -> {a['after']} [{a['rule']}] {a['reason']}"
              + (f" | readback {a['readback']}" if a.get("readback") else "") for a in planned["actions"]]
    lines += [f"{item['line']} ({item['settle']})" for item in followups]
    lines += [f"Not checked: {row}" for row in findings["unchecked"]]
    return line, lines


def boards(now):
    found, unchecked = discover_boards()
    lines, items = [], list(unchecked)
    if not found:
        return "boards: 0 boards", items
    workers, live_unchecked = live_workers()
    allow_file = OUT / "apply-boards.txt"
    allow = {str(Path(line.strip()).expanduser().resolve()) for line in allow_file.read_text().splitlines()
             if line.strip()} if allow_file.exists() else set()
    stamp = datetime.datetime.fromtimestamp(now, datetime.timezone.utc).replace(microsecond=0)
    run_dir = OUT / "boards" / datetime.datetime.fromtimestamp(now, datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    # Serialize hourly and manual invocations so a late run cannot replace newer evidence.
    import fcntl
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "boards.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for board in found:
            dest = run_dir / fp(board["path"])
            dest.mkdir(parents=True, exist_ok=True)
            findings, planned = {}, {"actions": []}
            try:
                records = [json.loads(line) for line in bd(board, "export").splitlines() if line.strip()]
                ready = [b["id"] for b in json.loads(bd(board, "ready", "--json", "--limit", "1000"))]
                live, live_count = board_workers(board, workers)
                not_checked = list(live_unchecked)
                try:
                    card_rows = json.loads(sh("annotate", "cards", board["project"] + "/" + board["slug"],
                                          "--json", cwd=board["repo"]))
                    cards = {str(c["number"]): bool(c.get("verdict")) and not c.get("pending") for c in card_rows}
                except (RuntimeError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
                    cards, card_rows = {}, []
                    not_checked.append({"source": "annotate cards", "reason": str(exc)[:200]})
                user = subprocess.run(["git", "-C", board["repo"], "config", "user.name"],
                                      capture_output=True, text=True, timeout=10).stdout.strip()
                sweep_name, sweep_md = latest_board_sweep(board)
                findings = check_board(records, len(ready), live, cards, sweep_md, stamp, board["prefix"], {user} if user else set())
                for row in findings["merge_proof_but_open"]:
                    row["proof"] = merge_proof(board, row)
                state_file = OUT / "boards" / (fp(board["path"]) + "-state.json")
                prev = json.loads(state_file.read_text()) if state_file.exists() else None
                planned, state = plan(findings, prev, ready, live_count, stamp)
                # Missing liveness sources cannot prove the absence of a worker.
                if live_unchecked:
                    planned["actions"] = [a for a in planned["actions"] if a["rule"] != "reset-no-live-worker"]
                    state["flags"] = {k: v for k, v in state["flags"].items() if not k.startswith("reset:")}
                    state["since"] = {k: v for k, v in state["since"].items() if not k.startswith("reset:")}
                apply = board["path"] in allow
                findings.update(at=iso(stamp), board=board["path"], page=board["project"] + "/" + board["slug"],
                                mode="apply" if apply else "dry-run", unchecked=not_checked, beads=records,
                                needs_model=planned["needs_model"], live_workers=live_count, cards=card_rows,
                                latest_sweep=sweep_name)
                apply_actions(board, planned["actions"], stamp.strftime("%Y-%m-%dT%H:%MZ"), apply)
                followups = save_followups(board, findings, planned, state, stamp,
                                          (prev or {}).get("followups_dir"))
                state["followups_dir"] = str(followups_dir(board))
                line, detail = board_summary(board, findings, planned, followups)
                lines.append(line)
                items.extend(detail[1:])
                atomic_write(dest / "findings.json", json.dumps(findings, indent=2) + "\n")
                atomic_write(dest / "actions.json", json.dumps(planned["actions"], indent=2) + "\n")
                atomic_write(dest / "summary.md", "\n".join(detail) + "\n")
                atomic_write(state_file, json.dumps(state, indent=2) + "\n")
            except (RuntimeError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
                line = f"boards: {board['prefix']} ({board['project']}/{board['slug']}) · error: {exc}"
                lines.append(line)
                atomic_write(dest / "findings.json", json.dumps(dict(findings, board=board["path"], error=str(exc))) + "\n")
                atomic_write(dest / "actions.json", json.dumps(planned["actions"]) + "\n")
                atomic_write(dest / "summary.md", line + "\n")
    return "\n".join(lines), items


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("check", choices=("beads", "boards", "disk", "sessions", "all"))
    parser.add_argument("--beads-dir")
    parser.add_argument("--apply", action="store_true", help="sessions: remove finished worktrees")
    args = parser.parse_args(argv)
    now = time.time()
    results = []
    if args.check in ("beads", "all"):
        results.append(beads(args.beads_dir, now))
    if args.check in ("boards", "all"):
        results.append(boards(now))
    if args.check in ("disk", "all"):
        results.append(disk(now))
    if args.check in ("sessions", "all"):
        results.append(sessions(args.apply))
    lines = [line for line, _ in results]
    items = [item for _, found in results for item in found]
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(now))
    (OUT / "latest.txt").write_text("\n".join([f"sweep {stamp}", *lines, "", *items]) + "\n")
    exit_code = 0
    if args.check == "all" and os.environ.get("ANNOTATE_OWNERSHIP_MANIFEST"):
        ownership_status = "ok"
        try:
            subprocess.run([sys.executable, "-I", os.environ["ANNOTATE_OWNERSHIP_MANIFEST"],
                            "--out", str(OUT / "ownership-latest.json")], check=True, timeout=300)
        except (OSError, subprocess.SubprocessError) as exc:
            exit_code = 1
            ownership_status = "error"
            try:
                atomic_write(OUT / "ownership-latest.json", json.dumps({"schema": "ownership-manifest/1",
                             "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                             "status": "error", "error": str(exc), "macs": {}, "held": True}) + "\n")
            except OSError as write_error:
                print(f"ownership error artifact failed: {write_error}", file=sys.stderr)
            print(f"ownership manifest failed: {exc}", file=sys.stderr)
        lines.append(f"ownership: {ownership_status} {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
        try:
            atomic_write(OUT / "latest.txt", "\n".join([f"sweep {stamp}", *lines, "", *items]) + "\n")
        except OSError as write_error:
            print(f"ownership summary update failed: {write_error}", file=sys.stderr)
    print("\n".join(lines))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
