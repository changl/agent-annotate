"""Operator-only reconciliation of local approvals; inspection never writes."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from .approval_catalog import _bundle, _digest, _pin_images, item_id, promote, read_bundle
from .categories import _atomic_bytes, safe_path
from .consolidate import inactive, refuse_if_moved
from .sync_server import _locked_store


def _hash(body):
    return hashlib.sha256(body).hexdigest()


def _candidate(decision):
    return {k: decision.get(k) for k in ("verdict", "by", "ts", "text")} | {
        "version": (decision.get("evidence") or {}).get("version")}


def _prepared_bundle(bundle):
    prepared = dict(bundle)
    styles = prepared.pop("styles", "")
    writes = {}
    if styles:
        stamp = _hash(styles.encode())
        writes[f"approval-evidence/styles/{stamp}.css"] = styles.encode()
        prepared["styles_revision"] = stamp
    revision = _digest(prepared)
    writes[f"approval-evidence/{revision}/bundle.json"] = json.dumps(prepared, ensure_ascii=False).encode()
    return revision, writes


def _cards(store):
    for section in ("anchors", "archived"):
        rows = store.get(section) or {}
        for items in ([rows] if isinstance(rows, list) else rows.values()):
            yield from items


def _excluded(comment, decision):
    return (str(decision.get("by", "")).startswith("agent:")
            or decision.get("catalog_eligible") is False or decision.get("legacy")
            or not isinstance(comment.get("decision_request"), dict)
            or comment["decision_request"].get("catalog") is False
            or comment.get("category", "review") != "review")


def _browser(comment, decision):
    if decision.get("catalog_eligible") is True:
        return bool(decision.get("by")) and decision["by"] != "anonymous"
    by = decision.get("by")
    if not isinstance(by, str) or not re.fullmatch(r"[^\s@]+@[^\s@]+", by):
        return False
    prefix = "☑ Selected: " if decision["verdict"] == "select" else "✓ Accepted"
    revised_prefix = "↺ Changed to " + prefix
    return any(r.get("author") == by and r.get("author_email") == by
               and r.get("ts") == decision.get("ts") and str(r.get("text", "")).startswith((prefix, revised_prefix))
               for r in comment.get("replies", []))


def _rounds(directory):
    path = directory / "rounds.ndjson"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def _sent(rounds, comment, decision):
    return [r for r in rounds if r.get("snapshot") is True and r.get("id") and r.get("by") == decision.get("by")
            and any(a.get("comment_id") == comment["id"]
                    and all(a.get(k) == decision.get(k) for k in ("by", "ts", "verdict", "text"))
                    and (not decision.get("id") or a.get("decision_id") == decision["id"])
                    for a in r.get("answers", []))]


def _evidence(directory, comment, decision, rounds):
    evidence = decision.get("evidence") or {}
    if evidence.get("committed"):
        bundle = read_bundle(directory, evidence["revision"])
        if bundle["item_id"] != item_id(comment) or bundle.get("incomplete"):
            raise ValueError("sealed evidence incomplete or belongs to another item")
        for name, digest in bundle.get("assets", {}).items():
            if _hash(safe_path(directory, name).read_bytes()) != digest:
                raise ValueError("sealed image changed")
        if bundle.get("styles_revision"):
            stamp = bundle["styles_revision"]
            if _hash(safe_path(directory, f"approval-evidence/styles/{stamp}.css").read_bytes()) != stamp:
                raise ValueError("sealed stylesheet changed")
        return bundle, evidence
    versions = {r.get("version") for r in rounds}
    if len(versions) != 1:
        raise ValueError("sent rounds disagree about the approved page version")
    version = versions.pop()
    if not isinstance(version, str) or not re.fullmatch(r"v[1-9][0-9]*", version):
        raise ValueError("approved version missing")
    html_path = safe_path(directory, f"versions/{version}.html")
    cards_path = safe_path(directory, f"versions/{version}.cards.json")
    # Files rewritten after the vote cannot establish what the reviewer saw.
    voted = datetime.fromisoformat(decision["ts"].replace("Z", "+00:00")).timestamp()
    if any(p.stat().st_mtime > voted for p in (html_path, cards_path)):
        raise ValueError("version snapshot modified after approval")
    candidates = [c for c in json.loads(cards_path.read_text()) if c.get("number") == comment.get("number")
                  and c.get("anchor_id") == comment.get("anchor_id")]
    if len(candidates) != 1:
        raise ValueError("exact versioned card missing or ambiguous")
    frozen = {**comment, **candidates[0], "id": comment["id"]}
    request = frozen.get("decision_request") or {}
    if request.get("catalog") is False:
        raise ValueError("historical card opted out of Plans")
    if any(a.get("prompt") != request.get("prompt") for r in rounds for a in r.get("answers", [])
           if a.get("comment_id") == comment["id"] and a.get("ts") == decision.get("ts")):
        raise ValueError("sent prompt differs from versioned card")
    bundle = _bundle(frozen, version, html_path.read_text())
    _, assets, incomplete, _ = _pin_images(directory, bundle["html"], "")
    if bundle["incomplete"] or assets or incomplete:
        raise ValueError("evidence missing or historical media has no vote-time hash")
    if bundle["item_id"] != item_id(comment):
        raise ValueError("historical and current item identities differ")
    return bundle, {"version": version, "request": bundle["request"], "committed": True}


def inspect_page(directory, store):
    """Return a JSON report and safe operations, without preparing any files."""
    from .cli import _item_numbers
    numbers = _item_numbers(store)
    rounds = _rounds(directory)
    rows, groups, branches = [], defaultdict(list), Counter()
    for comment in _cards(store):
        decisions = [*(comment.get("decision_history") or []), comment.get("decision") or {}]
        seen = set()
        for decision in decisions:
            if decision.get("verdict") not in {"accept", "select"}:
                continue
            key = _digest([comment["id"], decision.get("id") or decision])
            if key in seen:
                continue
            seen.add(key)
            if _excluded(comment, decision):
                branches["excluded_agent_legacy_opt_out"] += 1
                continue
            browser, sent = _browser(comment, decision), _sent(rounds, comment, decision)
            branch = "browser_and_sent" if browser and sent else "browser_only" if browser else "sent_only" if sent else "neither"
            branches[branch] += 1
            row = {"card": numbers.get(comment["id"]), "comment_id": comment["id"], "item_id": item_id(comment),
                   "branch": branch, "status": "conflict", "candidates": [
                       _candidate(decision),
                       {"sent_rounds": [r["id"] for r in sent], "browser_identity": browser}]}
            rows.append(row)
            groups[row["item_id"]].append((row, comment, decision, sent))
    operations = []
    for identifier, group in groups.items():
        for row, comment, decision, sent in group:
            try:
                if row["branch"] != "browser_and_sent":
                    raise ValueError("browser reviewer provenance and matching sent round both required")
                if decision.get("round_pending"):
                    raise ValueError("approval still pending")
                if comment.get("decision") != decision or (comment.get("reopened") or comment.get("reopen_history")):
                    row["candidates"][1] = {"current_decision": _candidate(comment.get("decision") or {}),
                                             "reopened": bool(comment.get("reopened") or comment.get("reopen_history"))}
                    raise ValueError("approval later reversed, revised or reopened")
                plan = store.get("approved_plans", {}).get(identifier)
                key = _digest([comment["id"], decision.get("id") or [decision["by"], decision["ts"]]])
                prior = next((e for e in (plan or {}).get("history", []) if e.get("key") == key), None)
                if prior and comment.get("catalog_plan") == identifier:
                    row.update(status="already_linked", plan=identifier)
                    continue
                if len(group) > 1:
                    row["candidates"][1] = {"other_approvals": [r[0]["candidates"][0] for r in group if r[0] is not row]}
                    raise ValueError("multiple approvals for one item")
                # A recorded catalog revision is itself frozen evidence for an
                # exact matching decision, including a lost card-side link.
                supplied = decision
                if prior and not (decision.get("evidence") or {}).get("revision"):
                    supplied = {**decision, "evidence": {"committed": True,
                                                        "revision": prior.get("evidence_revision")}}
                versions = sorted({r.get("version") or "unknown" for r in sent})
                row["candidates"][0]["version"] = (supplied.get("evidence") or {}).get("version") or versions
                row["candidates"][1] = {"required_snapshots": [f"versions/{v}.cards.json + {v}.html" for v in versions],
                                         "sealed_revision": (supplied.get("evidence") or {}).get("revision")}
                bundle, evidence = _evidence(directory, comment, supplied, sent)
                row["candidates"][0]["version"] = bundle["version"]
                if plan:
                    current = next((e for e in plan["history"] if e["version"] == plan["current"]), {})
                    same = prior and prior.get("evidence_revision") == evidence.get("revision")
                    if not same:
                        row["candidates"][1] = {"plan": identifier, "current": plan["current"],
                                                "evidence_revision": current.get("evidence_revision")}
                        raise ValueError("item already approved with different content or provenance")
                    status = "would_link"
                elif safe_path(directory, f"plans/{identifier}/meta.json").exists():
                    row["candidates"][1] = {"manual_plan": identifier}
                    raise ValueError("manual Plan exists without exact approval provenance")
                else:
                    status = "would_file"
                row.update(status=status, plan=identifier)
                operations.append((status, comment, decision, bundle, evidence))
            except (OSError, ValueError, TypeError, KeyError) as exc:
                row["reason"] = str(exc)
    counts = Counter(row["status"] for row in rows)
    return {"counts": {k: counts[k] for k in ("already_linked", "would_link", "would_file", "conflict")},
            "branches": dict(branches), "items": rows}, operations


def backfill_page(directory, *, apply=False):
    directory = Path(directory).resolve()
    # Read mode never creates the server's lock file. Apply needs its existing
    # lock so a separate inode cannot race a running server.
    if apply and not (directory / ".comments.json.lock").is_file():
        raise ValueError("apply requires the page server's existing .comments.json.lock")
    with _locked_store(directory, write=False):
        refuse_if_moved(directory)
        path = safe_path(directory, "comments.json")
        before = path.read_bytes()
        store = json.loads(before)
        report, operations = inspect_page(directory, store)
        if not apply or not operations:
            return report
        updated = deepcopy(store)
        writes, prepared_cards = {}, []
        # Prepare on a private copy: promotion receives only verified bundles.
        for status, comment, decision, bundle, evidence in operations:
            target = next(c for c in _cards(updated) if c["id"] == comment["id"])
            if status == "would_link":
                target["catalog_plan"] = item_id(comment)
                continue
            frozen = deepcopy(target)
            frozen["decision"] = {**decision, "catalog_eligible": True, "evidence": dict(evidence)}
            if not evidence.get("revision"):
                revision, prepared_writes = _prepared_bundle(bundle)
                writes.update(prepared_writes)
                frozen["decision"]["evidence"]["revision"] = revision
            target["catalog_plan"] = item_id(comment)
            # Keep historical votes intact; provenance is on the new Plan entry.
            prepared_cards.append(frozen)
        backup = directory / ".plans-backfill-backups" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ-") + uuid.uuid4().hex[:8])
        backup.mkdir(parents=True, mode=0o700)
        touched = {"comments.json": None, **writes}
        manifest = {"page": str(directory), "files": {}}
        for name in touched:
            original = safe_path(directory, name)
            saved = backup / name
            if original.exists():
                saved.parent.mkdir(parents=True, exist_ok=True)
                _atomic_bytes(saved, original.read_bytes())
                shutil.copystat(original, saved)
                manifest["files"][name] = {"before": _hash(original.read_bytes())}
            else:
                manifest["files"][name] = {"before": None}
        # Complete the durable restore manifest before the first page write.
        for name, body in writes.items():
            manifest["files"][name]["after"] = _hash(body)
        _atomic_bytes(backup / "manifest.json", json.dumps(manifest, indent=2).encode())
        for name, body in writes.items():
            _atomic_bytes(safe_path(directory, name), body)
        for frozen in prepared_cards:
            promote(directory, updated, frozen)
            if frozen.get("decision", {}).get("catalog_conflict") or not frozen.get("catalog_plan"):
                raise ValueError("catalog changed during preparation; restore backup before retry")
        after = (json.dumps(updated, ensure_ascii=False, indent=2) + "\n").encode()
        manifest["files"]["comments.json"]["after"] = _hash(after)
        _atomic_bytes(backup / "manifest.json", json.dumps(manifest, indent=2).encode())
        _atomic_bytes(path, after)
        report["backup"] = str(backup)
        report["applied"] = len(operations)
        return report


def restore_page(directory, backup):
    directory, backup = Path(directory).resolve(), Path(backup).resolve()
    if backup.parent != directory / ".plans-backfill-backups":
        raise ValueError("backup must belong to this page")
    manifest = json.loads((backup / "manifest.json").read_text())
    if manifest["page"] != str(directory) or not (directory / ".comments.json.lock").is_file():
        raise ValueError("backup page mismatch or page lock missing")
    with _locked_store(directory, write=False):
        refuse_if_moved(directory)
        for name, info in manifest["files"].items():
            path = safe_path(directory, name)
            digest = _hash(path.read_bytes()) if path.exists() else None
            if digest not in {info["before"], info.get("after")}:
                raise ValueError("file changed since backfill; refusing restore: " + name)
            if info["before"] is not None and _hash(safe_path(backup, name).read_bytes()) != info["before"]:
                raise ValueError("backup changed: " + name)
        for name, info in manifest["files"].items():
            path = safe_path(directory, name)
            if info["before"] is None:
                path.unlink(missing_ok=True)
            else:
                _atomic_bytes(path, safe_path(backup, name).read_bytes())


def cmd_plans(args):
    from .cli import _is_process_alive, _registry_entries, _resolve_scoped_slug
    if args.plans_action == "restore":
        entry = _resolve_scoped_slug(args.slug)
        if not entry:
            return 2
        try:
            restore_page(entry[2]["slug_dir"], args.backup)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            print("ERROR: " + str(exc))
            return 2
        print("Restored " + args.slug)
        return 0
    entries = _registry_entries()
    if args.slugs:
        selected = [_resolve_scoped_slug(s) for s in args.slugs]
        if any(e is None for e in selected):
            return 2
        entries = selected
    pages, skipped, seen = [], [], set()
    for project, slug, record in entries:
        name = project + "/" + slug
        try:
            live = _is_process_alive(int(record.get("pid") or 0))
        except (ValueError, TypeError):
            live = False
        if inactive(record) or not record.get("slug_dir") or not live:
            skipped.append(name)
            continue
        directory = Path(record["slug_dir"]).resolve()
        if directory in seen:
            continue
        seen.add(directory)
        try:
            result = backfill_page(directory, apply=args.apply)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            result = {"error": str(exc)}
        pages.append({"page": name, "directory": str(directory), **result})
    report = {"dry_run": not args.apply, "pages": pages, "skipped_inactive": skipped}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for page in pages:
            print(page["page"] + ": " + json.dumps(page.get("counts", page.get("error"))))
            for item in page.get("items", []):
                print(f"  #{item['card']} {item['status']}: {item.get('reason', item['item_id'])}")
            if page.get("backup"):
                print("  backup: " + page["backup"])
    return 2 if any("error" in page for page in pages) else 0
