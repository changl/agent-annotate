"""Read-only copies follow their real page (audit5 questions #02), and the fifth check's Questions fixes stay."""

import json
from pathlib import Path

from agent_annotate.proto_data import copies

WEB = Path(copies.__file__).resolve().parents[1] / "web/proto"


def _real(d: Path, version: str, mail: str) -> Path:
    (d / "versions").mkdir(parents=True, exist_ok=True)
    (d / "versions" / f"{version}.html").write_text(f"<p>{version} by {mail}</p>")
    (d / "comments.json").write_text(json.dumps({"anchors": {"a": [{"id": "c1", "text": f"ask {mail}"}]}}))
    (d / "current.meta.json").write_text(json.dumps({"current": version, "owner": {"agent": "x"}}))
    return d


def test_copy_follows_its_real_page(tmp_path):
    real = _real(tmp_path / "real", "v1", "someone@gmail.com")
    root = tmp_path / "root"
    copy = copies.refresh(root, "rebex", "Rebex", real)
    meta = json.loads((copy / "current.meta.json").read_text())
    assert meta["current"] == "v1" and meta["proto_copy_of"] == "rebex" and "owner" not in meta
    assert "someone@gmail.com" not in (copy / "comments.json").read_text()  # masked
    assert not copies.fresh(copy)  # same version: nothing to do
    (copy / "versions" / "v1.html").write_text("<p>kept scrubbed v1</p>")
    _real(real, "v2", "someone@gmail.com")
    assert copies.fresh(copy)  # the real page moved on: the copy is taken again
    assert json.loads((copy / "current.meta.json").read_text())["current"] == "v2"
    assert (copy / "versions" / "v1.html").read_text() == "<p>kept scrubbed v1</p>"  # a published version is reused, not scrubbed again
    assert "someone@gmail.com" not in (copy / "versions" / "v2.html").read_text()
    assert json.loads((real / "current.meta.json").read_text()).get("owner")  # the real page is never written
    assert any(p.name.startswith("proto-rebex-") for p in (root / "trash").iterdir())  # the old copy went to trash


def test_copy_meta_route_refreshes_first():
    s = (WEB.parent.parent / "proto_data/__init__.py").read_text()
    assert "_COPY_META" in s and "fresh(" in s and "_bound.pop" in s


def test_fifth_check_questions_fixes():
    s, c = (WEB / "questions.js").read_text(), (WEB / "questions.css").read_text()
    assert "el.onmouseover = onHover" in s and ".evh" in c  # #06: a card lights its evidence on hover
    assert "t.closest('.qevb')" in s and "S.note.inq" in s  # #03: Cards only evidence takes a note under its line
    assert "topSecs(DOC).find(s => s.contains(at))" in s  # #04: Go to it opens the note's folded section
