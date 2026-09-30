"""Actionable warnings for prose choices that never become UI controls."""

import re


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
