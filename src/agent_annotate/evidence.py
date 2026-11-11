"""Reviewer-accessibility checks for decision-card evidence.

Decision cards are remote review surfaces. A path that exists only on the
authoring machine, or prose that asks the reviewer to inspect a screenshot
without linking one, makes the card unanswerable even when its JSON shape is
valid. These checks intentionally warn rather than reject: the text heuristic
cannot know every time a word such as "image" names evidence versus the thing
being discussed.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

_LOCAL_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:file://)?(?:"
    r"/(?:Users|home|tmp|private|var|Volumes|opt)/[^\s<>\"']+"
    r"|[A-Za-z]:\\[^\s<>\"']+)"
)
_VISUAL_REFERENCE_RE = re.compile(
    r"\b(?:screen[ -]?shot|image|photo|png|jpe?g)\b", re.IGNORECASE
)


def is_safe_evidence_url(value: Any) -> bool:
    """Allow reviewer-reachable HTTP(S) or page-relative links only."""
    if not isinstance(value, str) or not value.strip():
        return False
    value = value.strip()
    if value.startswith("//"):
        return False
    if _LOCAL_PATH_RE.fullmatch(value):
        return False
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme:
        return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)
    # A colon before the first slash is a scheme-shaped value such as file: or
    # javascript:. Plain relative and root-relative page URLs are accepted.
    head = value.split("/", 1)[0]
    return ":" not in head


def _card_text(card: dict) -> str:
    dr = card.get("decision_request")
    dr = dr if isinstance(dr, dict) else {}
    parts = [card.get("text"), dr.get("prompt"), dr.get("context")]
    options = dr.get("options")
    if isinstance(options, list):
        for option in options:
            if isinstance(option, dict):
                parts.extend((option.get("label"), option.get("consequence")))
            elif isinstance(option, str):
                parts.append(option)
    consequences = dr.get("consequences")
    if isinstance(consequences, dict):
        parts.extend(consequences.values())
    evidence = dr.get("evidence")
    if isinstance(evidence, list):
        for item in evidence:
            if isinstance(item, dict):
                parts.extend((item.get("label"), item.get("anchor"), item.get("url")))
    return "\n".join(str(part) for part in parts if part is not None)


def card_evidence_warnings(cards: list[dict]) -> list[str]:
    """Return warnings for evidence a remote reviewer cannot actually open."""
    warnings: list[str] = []
    for index, card in enumerate(cards, start=1):
        if not isinstance(card, dict):
            continue
        number = card.get("number")
        label = f"card #{number}" if isinstance(number, int) and not isinstance(number, bool) else f"card {index}"
        text = _card_text(card)
        local_path = _LOCAL_PATH_RE.search(text)
        if local_path:
            path = local_path.group(0).rstrip(".,;:)]}`")
            warnings.append(
                f"{label} cites local path {path!r}; put the needed evidence inline "
                "or replace it with a reviewer-accessible link"
            )

        dr = card.get("decision_request")
        dr = dr if isinstance(dr, dict) else {}
        evidence = dr.get("evidence")
        evidence = evidence if isinstance(evidence, list) else []
        has_url = any(
            isinstance(item, dict) and is_safe_evidence_url(item.get("url"))
            for item in evidence
        )
        has_visual_anchor = any(
            isinstance(item, dict)
            and isinstance(item.get("anchor"), str)
            and bool(item.get("anchor"))
            and bool(_VISUAL_REFERENCE_RE.search(str(item.get("label") or "")))
            for item in evidence
        )
        if _VISUAL_REFERENCE_RE.search(text) and not (has_url or has_visual_anchor):
            warnings.append(
                f"{label} mentions a screenshot/image but provides no clickable URL "
                "or image-labelled evidence anchor"
            )
    return warnings
