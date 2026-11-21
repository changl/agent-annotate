"""Sixth check: every unsent draft survives a browser reload (questions 1, running 2, reference 1-2, frame 4)."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
FILES = ("frame.js", "questions.js", "reference.js", "links.js", "history.js")
FRAME, Q, REF, LINKS, HIST = ((WEB / n).read_text() for n in FILES)
DRAFT = re.compile(re.search(r"const DRAFT = /(.+)/;", FRAME)[1])


@pytest.mark.parametrize("name", FILES)
def test_draft_files_parse(name):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    r = subprocess.run([node, "--check", str(WEB / name)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_new_draft_keys_follow_the_unsent_switch():
    """The copy's simulation, Reference's choices and the failed-publish reply use keys the switch governs."""
    for k in ("draft:copy", "draft:ref", "draft:tell"):
        assert DRAFT.match(k), k
    assert "prefs.set('draft:copy'" in Q and "prefs.set('draft:ref'" in REF and "'draft:tell'" in HIST


def test_copy_simulation_is_kept_and_fed_back():
    """Questions 1 and reference 2: a copy's simulated notes are kept, and Reference and Links get theirs back."""
    assert "simLoad();\n    const r = fakeWrite(full, body, method);\n    simSave();" in Q
    assert "P.copyData = (area, d)" in Q
    assert "COPY && P.copyData ? P.copyData(area, d) : d" in FRAME


def test_reference_drafts_are_kept_and_restored():
    """Reference 2: copy edits, approvals and reopen reasons are restored before the tab draws."""
    assert "S.cp = new Map(s.cp || [])" in REF and "S.appr = new Set(s.appr || [])" in REF and "S.reopen = new Map(s.reopen || [])" in REF
    assert "keepDrafts();  // every change" in REF
    assert "chip: async c => { ctx = c; restoreDrafts();" in REF


def test_each_note_returns_to_its_own_tab():
    """Reference 1: after a reload a document note is listed by Pages & links, not Reference or Questions."""
    assert "!n.sent && !/^doc:/.test(n.a)).map(" in REF
    assert "...unsent(c).map(n => ({key: 'ln:'" in LINKS


def test_last_send_is_kept():
    """Frame 4: the last simulated Send survives a reload."""
    assert "sent: prefs.get('lastSend', null)" in FRAME
    assert "prefs.set('lastSend', S.sent = " in FRAME
