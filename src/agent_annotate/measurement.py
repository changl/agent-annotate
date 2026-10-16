"""Read-only measurement helpers; exports keep each machine's observations separate."""
from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
import re
import socket
from html.parser import HTMLParser
from pathlib import Path


def host():
    return socket.gethostname()


def sources(kind, local, files, settings):
    """Merge compatible exports, replacing an older observation of this host.

    A merged export can itself be merged again without double counting.
    """
    found = {}
    for filename in files:
        data = json.loads(Path(filename).expanduser().read_text())
        if not isinstance(data, dict) or data.get("measurement") != kind or data.get("schema_version") != 1:
            raise ValueError(f"{filename}: expected a {kind} measurement export (schema 1)")
        if data.get("settings") != settings:
            raise ValueError(f"{filename}: measurement settings differ; use the same cutoff and options")
        required = {"host", "rows"} if kind == "cost" else {
            "host", "slugs", "sightings", "file_ids", "notices", "dir_hits",
            "transcripts_scanned", "hook_log", "pages", "corrections"}
        if not isinstance(data.get("sources"), list) or any(
                not isinstance(s, dict) or not required <= s.keys() or not isinstance(s["host"], str)
                for s in data["sources"]):
            raise ValueError(f"{filename}: invalid {kind} source observations")
        for source in data["sources"]:
            found[source["host"]] = source
    found[local["host"]] = local
    return [found[key] for key in sorted(found)]


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.anchors, self.images, self.text = set(), 0, []
        self.hidden = 0
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        if self.hidden:
            return
        attrs = dict(attrs)
        self.anchors.update(v for k, v in attrs.items() if k in ("id", "data-anchor-id") and v)
        self.images += tag == "img"

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)


BULK = re.compile(r"\b(?:accept|approve|confirm)\s+(?:(?:them|these)\s+)?(?:all|every)\b|\ball at once\b", re.I)
VISUAL = re.compile(r"\b(?:visual|photos?|images?|screenshots?|mockups?|button placement|motion design|animations?|layout|typography|colou?rs?)\b", re.I)


def page_metrics(info, since, process_snapshot):
    """Snapshot backlog; visual and bulk candidates are auditable heuristics."""
    directory = Path(info["slug_dir"])
    current = directory / "current.html"
    try:
        document = Document(current.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        document = None
    meta = info.get("meta") or {}
    owner = meta.get("owner") or {}
    session = owner.get("owner_session") or info.get("owner_session")
    # Absence in a nonempty process snapshot is an observation, not a liveness attestation.
    presence = ("unknown" if not session or session == "unknown" or not process_snapshot
                else "present" if session in process_snapshot else "absent")
    moved = (directory / "consolidated.json").exists()
    superseded = bool(info.get("superseded_by") or meta.get("superseded_by"))
    documents = {"review": document}
    plan_metas = []
    for plan_path in sorted((directory / "plans").glob("*/meta.json")):
        plan = read_json(plan_path, {})
        plan_metas.append((plan_path.parent, plan))
        version = plan.get("current") or ""
        if re.fullmatch(r"v[0-9]+", version):
            try:
                documents["plan:" + plan_path.parent.name] = Document(
                    (plan_path.parent / "versions" / (version + ".html")).read_text(encoding="utf-8"))
            except OSError:
                documents["plan:" + plan_path.parent.name] = None
    cards = []
    for comment in info["comments"]:
        dr = comment.get("decision_request")
        if not dr:
            continue
        target_document = documents.get(comment.get("doc") or "review")
        anchor = comment.get("anchor_id")
        evidence = [e.get("anchor") for e in dr.get("evidence", []) if isinstance(e, dict)]
        text = " ".join([dr.get("prompt") or "", *map(str, dr.get("options") or [])])
        cards.append({"id": comment.get("id"), "number": comment.get("number"),
                      "category": comment.get("category") or ("library" if str(anchor).startswith("copy:") else "review"),
                      "open": comment.get("status") == "open" and not comment.get("archived_at"),
                      "in_window": str(comment.get("created_at") or "")[:10] >= since,
                      "bulk_approval_candidate": bool(BULK.search(text)),
                      "rail_only": (not ({anchor, *evidence} & target_document.anchors)) if target_document else None})
    versions = []
    for item in meta.get("history") or []:
        version = item.get("version") or ""
        if not re.fullmatch(r"v[0-9]+", version) or str(item.get("ts") or "")[:10] < since:
            continue
        path = next((p for p in (directory / "content" / (version + ".html"),
                                directory / "versions" / (version + ".html")) if p.is_file()), None)
        if path is None and version == meta.get("current") and current.is_file():
            path = current
        if path:
            doc = Document(path.read_text(encoding="utf-8", errors="replace"))
            candidate = bool(VISUAL.search(" ".join(doc.text)))
            versions.append({"version": version, "images": doc.images,
                             "visual_change_candidate": candidate, "no_image": candidate and doc.images == 0})
    for plan_dir, plan in plan_metas:
        for item in plan.get("history") or []:
            version = item.get("version") or ""
            if not re.fullmatch(r"v[0-9]+", version) or str(item.get("ts") or "")[:10] < since:
                continue
            path = plan_dir / "versions" / (version + ".html")
            if path.is_file():
                doc = Document(path.read_text(encoding="utf-8", errors="replace"))
                candidate = bool(VISUAL.search(" ".join(doc.text)))
                versions.append({"doc": "plan:" + plan_dir.name, "version": version, "images": doc.images,
                                 "visual_change_candidate": candidate, "no_image": candidate and doc.images == 0})
    return {"page": f"{info['project']}/{info['slug']}", "owner_presence": presence,
            "moved": moved, "superseded": superseded, "cards": cards, "versions": versions,
            "categories": info.get("categories"), "submitted_rounds": len(info.get("rounds") or [])}


TOPIC = re.compile(r"annotat|review page|right rail|decision card|\bcards?\b.*(?:page|open|stale)", re.I)
CORRECTION = re.compile(r"\b(?:why|where|missing|still|again|instead|please|should|must|stop|do not|don'?t|didn'?t|can'?t|not|make sure|use|using|show|present|too many|confus)\b", re.I)
RELAY = re.compile(r"^(?:<|# |You are |Another Claude session|\[annotate\]|From term_|Reroute|Chang asked|Takeover|Your carry-over|Base directory for this skill|This session is being continued|TASK|Task:|COORDINATOR)", re.I)


def corrections(claude_files, codex_files, since):
    """Count candidate reviewer corrections, never tool output or agent text.

    Candidate counts require human interpretation; message hashes allow audit
    and cross-file deduplication without exporting private transcript text.
    """
    rows, seen = [], set()
    for kind, paths in (("claude", claude_files), ("codex", codex_files)):
        for path in paths:
            try:
                if dt.date.fromtimestamp(Path(path).stat().st_mtime).isoformat() < since:
                    continue
                stream = Path(path).open(encoding="utf-8", errors="replace")
            except OSError:
                continue
            with stream:
                for line in stream:
                    if not any(word in line.lower() for word in ("annotat", "rail", "card", "review page")):
                        continue
                    try:
                        item = json.loads(line)
                    except ValueError:
                        continue
                    if not isinstance(item, dict):
                        continue
                    ts = str(item.get("timestamp") or "")
                    if ts[:10] < since:
                        continue
                    if kind == "claude":
                        if item.get("type") != "user" or item.get("isMeta") or item.get("isSidechain"):
                            continue
                        content = (item.get("message") or {}).get("content")
                    else:
                        p = item.get("payload") or {}
                        if item.get("type") != "response_item" or p.get("type") != "message" or p.get("role") != "user":
                            continue
                        content = p.get("content")
                    blocks = [content] if isinstance(content, str) else [
                        b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") in ("text", "input_text")]
                    text = " ".join(" ".join(blocks).split())
                    if RELAY.search(text) or not TOPIC.search(text) or not CORRECTION.search(text):
                        continue
                    digest = hashlib.sha256(text.encode()).hexdigest()
                    if digest in seen:
                        continue
                    try:
                        day = dt.date.fromisoformat(ts[:10])
                    except ValueError:
                        continue
                    seen.add(digest)
                    rows.append({"week": (day - dt.timedelta(days=day.weekday())).isoformat(),
                                 "ts": ts, "sha256": digest, "file": str(path), "source": kind})
    return rows


def scorecard(source_list):
    pages = [{"host": source["host"], **p} for source in source_list for p in source["pages"]]
    candidates = {r["sha256"]: r for s in source_list for r in s["corrections"]}
    cards = [c for p in pages for c in p["cards"]]
    versions = [v for p in pages for v in p["versions"]]
    return {"reviewer_correction_candidates_per_week": dict(sorted(collections.Counter(
                r["week"] for r in candidates.values()).items())),
            "open_cards": sum(c["open"] for c in cards),
            "open_cards_owner_absent_or_moved_or_superseded": sum(c["open"] for p in pages
                if p["owner_presence"] == "absent" or p["moved"] or p["superseded"] for c in p["cards"]),
            "open_cards_owner_unknown": sum(c["open"] for p in pages if p["owner_presence"] == "unknown" for c in p["cards"]),
            "rail_only_open_cards": sum(c["open"] and c["rail_only"] is True for c in cards),
            "open_cards_document_unavailable": sum(c["open"] and c["rail_only"] is None for c in cards),
            "bulk_approval_candidate_cards": sum(c["bulk_approval_candidate"] and c["in_window"] for c in cards),
            "visual_change_candidate_versions": sum(v["visual_change_candidate"] for v in versions),
            "visual_change_candidate_versions_no_image": sum(v["no_image"] for v in versions),
            "submitted_rounds": sum(p["submitted_rounds"] for p in pages), "pages": pages}
