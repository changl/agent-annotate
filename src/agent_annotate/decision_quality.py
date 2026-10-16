"""Pre-write card refusals and actionable authoring warnings."""

import re
from difflib import get_close_matches
from html.parser import HTMLParser


def page_anchors(markup: str) -> set[str]:
    anchors = set()

    class Walk(HTMLParser):
        def handle_starttag(self, tag, attrs):
            anchor = dict(attrs).get("data-anchor-id")
            if anchor:
                anchors.add(anchor)

    Walk().feed(markup)
    return anchors


def card_refusal(card: dict, anchors: set[str]) -> str | None:
    """Reject bulk approvals and missing or nonexistent evidence targets."""
    request = card.get("decision_request")
    if not isinstance(request, dict):
        return None
    texts = [str(request.get("prompt") or "")]
    for option in request.get("options") or []:
        if isinstance(option, dict):
            texts.extend(str(option.get(key) or "") for key in ("id", "label"))
        else:
            texts.append(str(option))
    # ponytail: explicit approval language only; extend from real missed examples.
    if any(re.search(r"\b(?:accept|approve|confirm)[\s_-]+(?:(?:these|those|them)\s+)?(?:all|both)\b", text, re.I)
           for text in texts):
        return "ask for one decision instead of approving several items at once"
    action = r"\b(?:accept|approve|confirm)\b"
    counted = r"(?:[2-9]|[1-9][0-9]+)\s+(?:items|recommendations|rows)\b"
    if (any(re.search(action + r"\s+(?:(?:the|these|those|following|remaining|proposed)\s+){0,2}" + counted, text, re.I)
            for text in texts)
            or (re.search(action, texts[0], re.I) and any(
                re.fullmatch(r"\s*(?:all\s+)?" + counted + r"[.?!]?\s*", text, re.I) for text in texts[1:]))):
        return "ask for one decision instead of approving several items at once"
    evidence = request.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return "cite at least one evidence anchor from the target version"
    for item in evidence:
        anchor = item.get("anchor") if isinstance(item, dict) else None
        if (not isinstance(anchor, str) or anchor not in anchors
                or (anchor == card.get("anchor_id") and anchor.startswith("d:"))):
            candidates = sorted(a for a in anchors if not a.startswith("d:"))
            closest = get_close_matches(str(anchor or ""), candidates, n=3, cutoff=0.2)
            hint = "; closest: " + ", ".join(closest) if closest else ""
            return f"evidence anchor {anchor!r} must identify visible content in the target version{hint}"

    return None


def decision_warnings(request: dict) -> list[str]:
    options = request.get("options") or []
    ids = [o.get("id") if isinstance(o, dict) else o for o in options]
    prompt = str(request.get("prompt") or "")
    warnings = []
    if re.search(r"(?:answer|reply|comment|type|write).{0,45}(?:option\s*(?:letter|number)|[123]\s*,\s*[123]|[ABC]\s*[/,]\s*[ABC])", prompt, re.I):
        warnings.append("Offer each choice in decision_request.options; the reviewer clicks a choice, then Finish review")
    if ids and all(i in ("comment", "changes") for i in ids) and re.search(r"\b(?:option|choose|which)\b", prompt, re.I):
        warnings.append("This choice card exposes only text input; put its actual choices in structured options")
    return warnings
