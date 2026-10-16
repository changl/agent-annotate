"""Pre-write card refusals and actionable authoring warnings."""

import re
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
    """Reject only explicit bulk approvals and questions with no location."""
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
    targets = [card.get("anchor_id")]
    targets += [item.get("anchor") for item in request.get("evidence") or [] if isinstance(item, dict)]
    if not any(isinstance(target, str) and target in anchors for target in targets):
        return "anchor_id and every evidence anchor are absent from the target version"
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
