"""Immutable reviewed evidence; the comment store owns the catalog transaction."""
from __future__ import annotations

import hashlib
import json
import re
from html import escape, unescape
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

from .categories import MAX_PLAN_BYTES, _atomic_bytes, _json, safe_path, validate_plan_id

_DIGEST = re.compile(r"[a-f0-9]{64}\Z")
_VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def item_id(comment: dict) -> str:
    explicit = (comment.get("decision_request") or {}).get("item_id")
    return validate_plan_id(explicit) if explicit else "decision-" + _digest(
        [comment.get("doc", "review"), comment["anchor_id"]])[:24]


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
    assets, incomplete = {}, []

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
                if path.stat().st_size > 10 * 1024 * 1024:
                    raise ValueError("oversized image")
                body = path.read_bytes()
                digest = hashlib.sha256(body).hexdigest()
                name = "attachments/approval-" + digest + path.suffix.lower()
                if not safe_path(page_dir, name).exists():
                    _atomic_bytes(safe_path(page_dir, name), body)
                assets[name] = digest
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
    return html, assets, incomplete


def _save_bundle(page_dir, bundle):
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
    request = dict(comment.get("decision_request") or {})
    request.pop("requested_at", None)
    anchors = [e.get("anchor") for e in (request.get("evidence") or []) if isinstance(e, dict) and e.get("anchor")]
    spans, styles, registry = document_parts if document_parts is not None else _document_parts(html)
    ranges, missing = [], []
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
    """The response and its evidence bundle share the very same pinned media."""
    cards = [comment for items in store.get("anchors", {}).values() for comment in items
             if comment.get("decision_request") and comment.get("version") == version
             and comment.get("doc", "review") == "review" and not comment.get("withdrawn")]
    if not cards:
        return html, {}
    html, assets, incomplete = _pin_images(page_dir, html, base)
    document_parts = _document_parts(html)
    tokens = {}
    for comment in cards:
        try:
            bundle = _bundle(comment, version, html, assets, incomplete, document_parts)
            tokens[comment["id"]] = {"revision": _save_bundle(page_dir, bundle),
                "predecessor": _current(page_dir, store, item_id(comment))}
        except (OSError, ValueError):
            # Read-only pages remain readable; a later vote can still
            # use the incomplete-card fallback when storage recovers.
            continue
    return html, tokens


def bind_evidence(page_dir, store, comment, token, shown_request=None):
    """A vote always succeeds; older clients get an explicitly incomplete card."""
    if isinstance(token, dict) and isinstance(token.get("revision"), str) and _DIGEST.fullmatch(token["revision"]):
        try:
            bundle = read_bundle(page_dir, token["revision"])
            if bundle["item_id"] == item_id(comment) and bundle["anchor_id"] == comment["anchor_id"]:
                revision = token["revision"]
                if shown_request:
                    shown_request = dict(shown_request)
                    shown_request.pop("requested_at", None)
                    if shown_request != bundle["request"]:
                        # The rail can receive a reposed question while its
                        # iframe stays open. Keep its displayed words together
                        # with the frozen iframe evidence, not latest files.
                        fresh = _bundle({**comment, "decision_request": shown_request}, bundle["version"],
                                        bundle["html"], bundle["assets"], bundle["incomplete"])
                        fresh.update(styles=bundle["styles"], registry=bundle["registry"], item_id=bundle["item_id"])
                        revision = _save_bundle(page_dir, fresh)
                return {"revision": revision, "predecessor": token.get("predecessor")}
        except (OSError, ValueError, KeyError):
            pass
    bundle = _bundle(comment, comment.get("version"), incomplete=["Displayed evidence token unavailable"])
    return {"revision": _save_bundle(page_dir, bundle),
            "predecessor": _current(page_dir, store, item_id(comment))}


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
            or not comment.get("decision_request")
            or (comment.get("decision_request") or {}).get("catalog") is False
            or comment.get("category", "review") != "review"):
        return
    evidence = decision.get("evidence") or bind_evidence(page_dir, store, comment, None)
    try:
        bundle = read_bundle(page_dir, evidence["revision"])
    except (OSError, ValueError):
        evidence = bind_evidence(page_dir, store, comment, None)
        bundle = read_bundle(page_dir, evidence["revision"])
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
    choice = str(decision.get("option_id") or decision.get("text") or "").split("\n", 1)[0]
    option = next((o for o in (request.get("options") or []) if isinstance(o, dict)
                   and choice in (o.get("id"), o.get("label"))), {})
    label = str(option.get("label") or choice)
    kind = "Approved" if decision["verdict"] == "accept" else "Decided"
    key = _digest([evidence["revision"], kind, label if kind == "Decided" else ""])
    prior = next((entry for entry in plan["history"] if entry["key"] == key), None)
    if prior:
        comment["catalog_plan"] = identifier
        return
    if evidence.get("predecessor") != plan["current"]:
        decision["catalog_conflict"] = True  # Record the vote without replacing a newer approval.
        return
    next_number = max((int(entry["version"][1:]) for entry in plan["history"]), default=0) + 1
    entry = {"version": f"v{next_number}", "ts": decision["ts"], "by": decision["by"],
             "key": key, "evidence_revision": evidence["revision"], "kind": kind,
             "label": kind if kind == "Approved" else "Decided: " + label,
             "consequence": option.get("consequence") or (request.get("consequences") or {}).get(option.get("id", choice), ""),
             "source_version": bundle["version"], "source_card": comment["id"],
             "evidence_incomplete": bool(bundle["incomplete"]), "predecessor": plan["current"]}
    plan["history"].append(entry)
    plan.update(current=entry["version"], kind=kind, updated_at=entry["ts"], managed=True)
    plans[identifier] = plan
    comment["catalog_plan"] = identifier


def catalog_meta(plan):
    return {**plan, "history": [{**entry, "decision_label": entry["label"], "label": entry["label"] + (
        " · Current" if entry["version"] == plan["current"] else " · Superseded")} for entry in plan["history"]]}


def render_plan(page_dir, plan, version):
    entry = next(entry for entry in plan["history"] if entry["version"] == version)
    bundle = read_bundle(page_dir, entry["evidence_revision"])
    request = bundle["request"]
    status = "Current" if version == plan["current"] else "Superseded"
    incomplete = "<p><strong>Evidence incomplete</strong>: " + escape("; ".join(bundle["incomplete"])) + "</p>" if bundle["incomplete"] else ""
    source = escape(str(bundle["version"]), quote=True)
    card = escape(entry["source_card"], quote=True)
    options = "".join("<li>" + escape(str(o.get("label", o.get("id", "")) if isinstance(o, dict) else o))
                      + (" — " + escape(str(o["consequence"])) if isinstance(o, dict) and o.get("consequence") else "") + "</li>"
                      for o in (request.get("options") or []))
    return (f'<!doctype html><html><head><meta charset="utf-8">{bundle["styles"]}{bundle["registry"]}</head>'
            f'<body><main class="aa"><header><h1>{escape(request.get("prompt") or plan["title"])}</h1><p><strong>{escape(entry.get("decision_label", entry["label"]))} · {status}</strong></p>'
            f'<p>{escape(entry["by"])} · {escape(entry["ts"])} · <a href="./?v={source}#card={card}" target="_top">Review {source}</a></p>'
            f'{incomplete}<p>{escape(str(entry["consequence"]))}</p></header><section><h2>Decision</h2>'
            f'<p>{escape(str(request.get("context") or ""))}</p><ul>{options}</ul></section>{bundle["html"]}</main></body></html>')
