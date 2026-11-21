"""Fifth check, Pages & links Undo and History: one test per fixed item."""

import json
from pathlib import Path

from agent_annotate.proto_data import links

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
HIST, RUN, LINKS = ((WEB / n).read_text() for n in ("history.js", "running.js", "links.js"))


def test_send_remove_and_undo_redraw_the_open_failure():
    """Finding 1 and reference 4: Remove in Send and its Undo redraw the failure on screen, not a closed one."""
    assert "LIVE.set(o.src, again)" in HIST
    assert "return () => { TELL.set(src, t); again(src); }" in HIST


def test_picture_viewer_one_set_of_controls_and_the_original():
    """Finding 2: our size bar stands in for the page's own, and Full size loads the original picture."""
    assert "img.pp-sized~.aa-img-bar .aa-img-zoom,figure:has(img.pp-sized)>a.aa-full{display:none!important}" in HIST
    assert "img.dataset.full" in HIST and "new URL(u, doc.baseURI)" in HIST


def test_section_link_opens_a_folded_section():
    """Finding 3: a folded section is opened before the jump lands on it."""
    assert "annotate-sfold-bar > .annotate-unchanged-toggle[aria-expanded=false]" in HIST
    assert "annotate-unchanged-bar > .annotate-unchanged-toggle[aria-expanded=false]" in HIST


def test_older_document_follows_the_theme():
    """Finding 4: the opened version follows a theme change at once."""
    assert "attributeFilter: ['data-theme']" in HIST


def test_task_panel_beside_questions_redraws_on_undo():
    """Questions 8: the side panel has no tab class, so Send's Undo must still redraw it."""
    assert "tabNow === 'side' || EL.classList.contains('tab-' + tabNow)" in RUN


def test_admin_meeting_is_kept_with_its_revisions(tmp_path, monkeypatch):
    """Reference 7: the meeting sits under Documents with every revision, and its whole text, not a page row."""
    m = tmp_path / "meeting"
    (m / "versions").mkdir(parents=True)
    hist = [{"version": f"v{i}", "ts": f"2026-11-1{i}T00:00:00Z"} for i in (1, 2)]
    (m / "current.meta.json").write_text(json.dumps({"history": hist + [{"version": "v9"}]}))  # v9 has no file: skipped
    (m / "versions" / "v1.html").write_text("".join(f"<p>line {i}</p>" for i in range(120)))
    (m / "versions" / "v2.html").write_text("<h1>Moved</h1><p>line 0</p>")
    monkeypatch.setattr(links, "MEETING", m)
    monkeypatch.setattr(links, "USAGE_AUDIT", tmp_path / "missing.html")
    monkeypatch.setattr(links, "LOAD_TEST", tmp_path / "missing")
    (d,) = links.kept()
    assert d["id"] == "admin-meeting" and [r["v"] for r in d["revs"]] == ["v1", "v2"]
    assert len(d["revs"][0]["blocks"]) == 120  # not cut short, so the removed count is true
    assert d["blocks"] == d["revs"][-1]["blocks"] and "2 revisions" in d["sub"]
    assert links.meeting(tmp_path / "missing") is None
    assert "revDoc(ctx, D, d, line)" in LINKS and "data-marks" in LINKS and 'class="l-vlist"' in LINKS
