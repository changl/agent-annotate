"""Fix31 Send (r12 audit27 running 1): a redraw of the open sheet keeps the selection's direction, so Shift-arrows
keep moving the same end."""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "src/agent_annotate/web/proto"


def test_every_focus_restore_keeps_the_direction():
    q = (WEB / "questions.js").read_text()
    assert "d: a.selectionDirection}" in q and "d: fa.selectionDirection}" in q
    # every caret restore after a rebuild that reads a saved range passes its direction
    saved = re.findall(r"\.setSelectionRange\((\w+)\.a, \1\.b(.*?)\)", q)
    assert saved and all(rest == f", {v}.d" for v, rest in saved)
