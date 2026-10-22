"""Immutable reviewed evidence; the comment store owns the catalog transaction."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import threading
import uuid
from collections import OrderedDict
from copy import deepcopy
from functools import lru_cache
from html import escape, unescape
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

from .categories import MAX_PLAN_BYTES, _atomic_bytes, _json, safe_path, validate_plan_id

_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
_VIEWS = OrderedDict()
_VIEW_LOCK = threading.RLock()
# ponytail: bounded process-local views until a vote; accept/select POSTs
# persist their evidence so Send never depends on this cache.
_MAX_VIEWS = 16
_MAX_VIEW_BYTES = 128 * 1024 * 1024


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _retained_size(value, seen=None):
    seen = set() if seen is None else seen
    if id(value) in seen:
        return 0
    seen.add(id(value))
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        size += sum(_retained_size(k, seen) + _retained_size(v, seen) for k, v in value.items())
    elif isinstance(value, (list, tuple)):
        size += sum(_retained_size(v, seen) for v in value)
    return size


def _image_hash(path):
    stat = path.stat()
    if stat.st_size > 10 * 1024 * 1024:
        raise ValueError("oversized image")
    return _cached_image_hash(path, (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))


@lru_cache(maxsize=512)
def _cached_image_hash(path, signature):
    # Cache digests only, never image bytes. ctime catches edits with restored
    # mtime; inode catches atomic replacements. Changed images are rehashed.
    return hashlib.sha256(path.read_bytes()).hexdigest()


def item_id(comment: dict) -> str:
    request = comment.get("decision_request")
    explicit = request.get("item_id") if isinstance(request, dict) else None
    number = comment.get("number")
    identity = f"d:q{number}" if type(number) is int and number > 0 else comment.get("origin_id") or comment["id"]
    if explicit:
        try:
            return validate_plan_id(explicit)
        except ValueError:
            pass
    return "decision-" + _digest([comment.get("doc", "review"), identity])[:24]


def _current(page_dir, store, identifier):
    plan = store.get("approved_plans", {}).get(identifier)
    return (plan or _json(safe_path(page_dir, f"plans/{identifier}/meta.json"), {})).get("current")


class _Anchors(HTMLParser):
    """Source spans preserve markup, SVG and whitespace without reserializing."""
    def __init__(self, html):
        super().__init__(convert_charrefs=False)
        self.html, self.stack, self.spans = html, [], {}
        self.lines = [0]
        self.lines.extend(match.end() for match in re.finditer("\n", html))
        self.feed(html)

    def source_offset(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        entry = (tag, self.source_offset(), attrs.get("data-anchor-id") or attrs.get("id"))
        if tag in _VOID:
            self.record(entry, self.source_offset() + len(self.get_starttag_text()))
        else:
            self.stack.append(entry)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.record(self.stack.pop(), self.source_offset() + len(self.get_starttag_text()))

    def record(self, entry, end):
        if entry[2]:
            self.spans.setdefault(entry[2], (entry[1], end))

    def handle_endtag(self, tag):
        index = next((i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i][0] == tag), None)
        if index is not None:
            end = self.html.find(">", self.source_offset()) + 1
            for entry in self.stack[index:]:
                self.record(entry, end)
            del self.stack[index:]


def _pin_images(page_dir, html, base):
    assets, incomplete, sources = {}, [], {}

    def pin(match):
        tag = match.group(0)
        # Alternate/responsive sources and CSS resources are preserved, but
        # cannot be claimed as sealed by the basic image-src capture.
        if re.search(r"\bsrcset\s*=", tag, re.I):
            incomplete.append("Responsive image sources")
        if re.search(r'\b(?:src|href)\s*=\s*[^\s\"\']', tag, re.I):
            incomplete.append("Unquoted image source not sealed")

        def replace(attribute):
            url = unescape(attribute[3])
            if url.startswith("data:image/") or url.startswith("#"):
                return attribute[0]
            try:
                parts = urlsplit(url)
                if parts.scheme or parts.netloc or not parts.path:
                    raise ValueError("external image")
                relative = unquote(parts.path)
                if relative.startswith("/"):
                    prefix = base.rstrip("/") + "/"
                    if not relative.startswith(prefix):
                        raise ValueError("image outside page")
                    relative = relative[len(prefix):]
                relative = relative.removeprefix("./")
                path = safe_path(page_dir, relative)
                if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif"}:
                    raise ValueError("unsupported image")
                digest = _image_hash(path)
                name = "attachments/approval-" + digest + path.suffix.lower()
                assets[name] = digest
                sources[name] = relative
                return attribute[1] + attribute[2] + "./" + name + attribute[2]
            except (OSError, ValueError):
                incomplete.append("Image not sealed: " + url[:200])
                return attribute[0]

        return re.sub(r'((?:\bsrc|\bhref|\bxlink:href)\s*=\s*)([\"\'])(.*?)(?:\2)', replace, tag, flags=re.I)

    html = re.sub(r"<(?:img|image|source)\b[^>]*>", pin, html, flags=re.I)
    if re.search(r"url\s*\(|<canvas\b|<iframe\b|<video\b", html, re.I):
        incomplete.append("Dynamic or CSS media not sealed")
    if re.search(r'<link\b[^>]*\brel=[\"\']stylesheet[\"\']', html, re.I):
        incomplete.append("Linked stylesheet not sealed")
    return html, assets, incomplete, sources


def _save_bundle(page_dir, bundle):
    bundle = dict(bundle)
    styles = bundle.pop("styles", "")
    if styles:
        stamp = hashlib.sha256(styles.encode()).hexdigest()
        style_path = safe_path(page_dir, f"approval-evidence/styles/{stamp}.css")
        if not style_path.exists():
            _atomic_bytes(style_path, styles.encode())
        bundle["styles_revision"] = stamp
    digest = _digest(bundle)
    path = safe_path(page_dir, f"approval-evidence/{digest}/bundle.json")
    if not path.exists():
        _atomic_bytes(path, json.dumps(bundle, ensure_ascii=False).encode())
    return digest


def _document_parts(html):
    styles = "\n".join(re.findall(r"<style\b[^>]*>.*?</style>", html, re.I | re.S))
    registry = re.search(r'<script\b[^>]*id=[\"\']anchor-registry-data[\"\'][^>]*>.*?</script>', html, re.I | re.S)
    return _Anchors(html).spans, styles, registry[0] if registry else ""


def _bundle(comment, version, html="", assets=None, incomplete=None, document_parts=None):
    request = deepcopy(comment.get("decision_request") or {})
    if not isinstance(request, dict):
        request = {"prompt": comment.get("text", "Decision")}
    request.pop("requested_at", None)
    raw = request.get("evidence") or []
    anchors = [e["anchor"] for e in raw if isinstance(e, dict) and isinstance(e.get("anchor"), str) and e["anchor"]] if isinstance(raw, list) else []
    invalid = not isinstance(raw, list) or any(not isinstance(e, dict) or not isinstance(e.get("anchor"), str) for e in raw)
    spans, styles, registry = document_parts if document_parts is not None else _document_parts(html)
    ranges, missing = [], ["Invalid evidence anchor"] if invalid else []
    for anchor in anchors:
        if anchor in spans:
            ranges.append(spans[anchor])
        else:
            missing.append("Missing anchor: " + str(anchor))
    if not anchors and comment["anchor_id"] in spans:
        ranges.append(spans[comment["anchor_id"]])
    selected = []
    for start, end in sorted(set(ranges), key=lambda pair: (pair[0], -pair[1])):
        if not any(a <= start and end <= b for a, b in selected):
            selected.append((start, end))
    fragments = []
    for start, end in selected:
        fragment = html[start:end]
        # Table/row anchors must remain valid HTML when filed on their own.
        if re.match(r"<tr\b", fragment, re.I):
            fragment = "<table><tbody>" + fragment + "</tbody></table>"
        elif re.match(r"<t[dh]\b", fragment, re.I):
            fragment = "<table><tbody><tr>" + fragment + "</tr></tbody></table>"
        elif re.match(r"<li\b", fragment, re.I):
            fragment = "<ul>" + fragment + "</ul>"
        fragments.append(fragment)
    content = "\n".join(fragments)
    return {"item_id": item_id(comment), "anchor_id": comment["anchor_id"], "doc": comment.get("doc", "review"),
            "version": version, "request": request, "anchors": anchors, "html": content,
            "styles": styles, "registry": registry, "assets": assets or {},
            "incomplete": list(dict.fromkeys([*(incomplete or []), *missing,
                                               *([] if anchors and content else ["Card only"])]))}


def seal_review(page_dir, html, version, store, base=""):
    """Capture server-owned HTML and image hashes without altering Review."""
    cards = [comment for items in store.get("anchors", {}).values() for comment in items
             if comment.get("decision_request") and comment.get("version") == version
             and comment.get("doc", "review") == "review" and not comment.get("withdrawn")]
    if not cards:
        return html, {}
    document_parts = _document_parts(html)
    tokens, snapshots = {}, {}
    view = uuid.uuid4().hex
    for comment in cards:
        try:
            bundle = _bundle(comment, version, html, document_parts=document_parts)
            fragment, assets, incomplete, sources = _pin_images(page_dir, bundle["html"], base)
            bundle.update(html=fragment, assets=assets, image_sources=sources, incomplete=bundle["incomplete"] + incomplete)
            snapshots[comment["id"]] = bundle
            tokens[comment["id"]] = {"view": view, "revision": _digest(bundle),
                "predecessor": _current(page_dir, store, item_id(comment))}
        except (OSError, ValueError, TypeError, KeyError):
            continue
    key = (str(page_dir), view)
    entry = {"cards": snapshots, "predecessors": {cid: token["predecessor"] for cid, token in tokens.items()}}
    entry["size"] = _retained_size(entry)
    with _VIEW_LOCK:
        _VIEWS[key] = entry
        while len(_VIEWS) > _MAX_VIEWS or sum(v["size"] for v in _VIEWS.values()) > _MAX_VIEW_BYTES:
            _VIEWS.popitem(last=False)
        if key not in _VIEWS:
            return html, {}
    return html, tokens


def bind_evidence(page_dir, store, comment, token, shown_request=None):
    """Bind server-owned words; the browser can select a view, never rewrite it."""
    if isinstance(token, dict) and isinstance(token.get("view"), str):
        with _VIEW_LOCK:
            view = _VIEWS.get((str(page_dir), token["view"]), {})
            cached = view.get("cards", {}).get(comment["id"])
        if cached and cached["item_id"] == item_id(comment) and _digest(cached) == token.get("revision"):
            return {"view": token["view"], "revision": token["revision"], "view_revision": token["revision"], "request": cached["request"],
                    "version": cached["version"], "predecessor": view.get("predecessors", {}).get(comment["id"])}
    bundle = _bundle(comment, comment.get("version"), incomplete=["Displayed evidence token unavailable"])
    return {"request": bundle["request"], "version": bundle["version"],
            "predecessor": _current(page_dir, store, item_id(comment))}


def persist_evidence(page_dir, comment, evidence):
    """Accept/select POST verifies and pins cited images before saving the vote."""
    if evidence.get("committed"):
        return read_bundle(page_dir, evidence["revision"])
    with _VIEW_LOCK:
        cached = _VIEWS.get((str(page_dir), evidence.get("view")), {})
        bundle = deepcopy(cached.get("cards", {}).get(comment["id"]))
    if not bundle or _digest(bundle) != evidence.get("revision"):
        frozen = {**comment, "decision_request": evidence.get("request") or comment.get("decision_request")}
        bundle = _bundle(frozen, evidence.get("version") or comment.get("version"), incomplete=["Displayed evidence unavailable"])
    for name in bundle["assets"]:
        try:
            source = safe_path(page_dir, bundle["image_sources"][name])
            digest = bundle["assets"][name]
            if _image_hash(source) != digest:
                raise ValueError("image changed since view")
            target = safe_path(page_dir, name)
            if not target.exists() or _image_hash(target) != digest:
                body = source.read_bytes()
                if hashlib.sha256(body).hexdigest() != digest:
                    raise ValueError("image changed while freezing")
                _atomic_bytes(target, body)
        except (OSError, ValueError, KeyError):
            bundle["incomplete"].append("Image unavailable or changed since view: " + name)
            bundle["html"] = re.sub(r'(?:src|href|xlink:href)\s*=\s*([\"\'])\./' + re.escape(name) + r'\1',
                                    'data-evidence-image-unavailable=""', bundle["html"], flags=re.I)
    evidence.update(revision=_save_bundle(page_dir, bundle), committed=True)
    return read_bundle(page_dir, evidence["revision"])


def read_bundle(page_dir, digest):
    if not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
        raise ValueError("invalid evidence revision")
    path = safe_path(page_dir, f"approval-evidence/{digest}/bundle.json")
    if path.stat().st_size > MAX_PLAN_BYTES:
        raise ValueError("oversized evidence revision")
    value = json.loads(path.read_text())
    if _digest(value) != digest:
        raise ValueError("evidence revision changed")
    return value


def promote(page_dir, store, comment):
    """Mutate only the caller's locked store: verdict and index commit together."""
    decision = comment.get("decision") or {}
    if (decision.get("verdict") not in {"accept", "select"} or decision.get("round_pending")
            or not decision.get("catalog_eligible") or str(decision.get("by", "")).startswith("agent:")
            or not comment.get("decision_request")
            or (comment.get("decision_request") or {}).get("catalog") is False
            or comment.get("category", "review") != "review"):
        return
    evidence = decision.get("evidence") or bind_evidence(page_dir, store, comment, None)
    try:
        bundle = read_bundle(page_dir, evidence["revision"])
    except (OSError, ValueError, TypeError, KeyError):
        frozen = {**comment, "decision_request": evidence.get("request") or comment.get("decision_request")}
        bundle = _bundle(frozen, evidence.get("version"), incomplete=["Evidence could not be sealed"])
        evidence.update(revision=_save_bundle(page_dir, bundle), committed=True)
    decision["evidence"] = evidence
    request = bundle["request"]
    if request.get("catalog") is False:
        return
    identifier = bundle["item_id"]
    plans = store.setdefault("approved_plans", {})
    plan = plans.get(identifier)
    if plan is None:
        manual = _json(safe_path(page_dir, f"plans/{identifier}/meta.json"), {})
        plan = {"title": request.get("prompt") or comment.get("text", "Decision"),
                "current": manual.get("current"), "history": [
                    {**entry, "key": "legacy:" + entry["version"], "legacy": True,
                     "label": entry.get("label", "Legacy / unlinked")} for entry in manual.get("history", [])]}
    choice = str(decision.get("option_id") or ("accept" if decision["verdict"] == "accept" else decision.get("text")) or "").split("\n", 1)[0]
    option = next((o for o in (request.get("options") or []) if isinstance(o, dict)
                   and choice in (o.get("id"), o.get("label"))), {})
    label = str(option.get("label") or choice)
    kind = "Approved" if decision["verdict"] == "accept" else "Decided"
    key = _digest([comment["id"], decision.get("id") or [decision["by"], decision["ts"]]])
    prior = next((entry for entry in plan["history"] if entry["key"] == key), None)
    if prior:
        comment["catalog_plan"] = identifier
        return
    current = next((entry for entry in plan["history"] if entry["version"] == plan["current"]), {})
    if evidence.get("predecessor") != plan["current"] and current.get("source_card") != comment["id"]:
        decision["catalog_conflict"] = True  # Record the vote without replacing a newer approval.
        return
    next_number = max((int(entry["version"][1:]) for entry in plan["history"]), default=0) + 1
    entry = {"version": f"v{next_number}", "ts": decision["ts"], "by": decision["by"],
             "key": key, "evidence_revision": evidence["revision"], "kind": kind,
             "label": kind if kind == "Approved" else "Decided: " + label,
             "chosen_option": label or "Accepted",
             "consequence": option.get("consequence") or (request.get("consequences") or {}).get(option.get("id", choice), ""),
             "source_version": bundle["version"], "source_card": comment["id"],
             "evidence_incomplete": bool(bundle["incomplete"]), "predecessor": plan["current"]}
    plan["history"].append(entry)
    plan.update(current=entry["version"], kind=kind, updated_at=entry["ts"], managed=True)
    plans[identifier] = plan
    comment["catalog_plan"] = identifier
    decision.pop("catalog_conflict", None)


def catalog_meta(plan):
    return {**plan, "history": [{**entry, "decision_label": entry["label"], "label": entry["label"] + (
        " · Current" if entry["version"] == plan["current"] else " · Superseded")} for entry in plan["history"]]}


def render_plan(page_dir, plan, version):
    entry = next(entry for entry in plan["history"] if entry["version"] == version)
    try:
        bundle = read_bundle(page_dir, entry["evidence_revision"])
    except (OSError, ValueError, KeyError):
        bundle = {"request": {"prompt": plan["title"]}, "version": entry.get("source_version"),
                  "styles": "", "registry": "", "html": "", "incomplete": ["Sealed evidence unavailable"]}
    styles = bundle.get("styles", "")
    if bundle.get("styles_revision"):
        try:
            stamp = bundle["styles_revision"]
            if not _DIGEST.fullmatch(stamp):
                raise ValueError("invalid stylesheet")
            styles = safe_path(page_dir, f"approval-evidence/styles/{stamp}.css").read_text()
        except (OSError, ValueError):
            bundle["incomplete"].append("Sealed stylesheet unavailable")
    request = bundle["request"]
    status = "Current" if version == plan["current"] else "Superseded"
    incomplete = "<p><strong>Evidence incomplete</strong>: " + escape("; ".join(bundle["incomplete"])) + "</p>" if bundle["incomplete"] else ""
    source = escape(str(bundle["version"]), quote=True)
    card = escape(entry["source_card"], quote=True)
    chosen = entry.get("chosen_option") or ("Accepted" if entry.get("kind") == "Approved" else entry.get("decision_label", entry["label"]))
    return (f'<!doctype html><html><head><meta charset="utf-8">{styles}{bundle["registry"]}</head>'
            f'<body><main class="aa"><header><h1>{escape(request.get("prompt") or plan["title"])}</h1><p><strong>{escape(entry.get("decision_label", entry["label"]))} · {status}</strong></p>'
            f'<p>{escape(entry["by"])} · <time data-decided-time datetime="{escape(entry["ts"], quote=True)}">Decided</time> · <a href="./?v={source}#card={card}" target="_top">Review {source}</a></p>'
            f'{incomplete}<p>{escape(str(entry["consequence"]))}</p></header><section><h2>Decision</h2>'
            f'<p>{escape(str(request.get("context") or ""))}</p><p>Chosen: <strong>{escape(chosen)}</strong></p></section>{bundle["html"]}</main></body></html>')
