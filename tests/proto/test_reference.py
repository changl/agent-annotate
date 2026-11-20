"""Reference tab data: plans by topic, the go-live checklist rows, notes at their anchors, no email or phone leaks."""

import json

import pytest

from agent_annotate.categories import publish_plan_revision
from agent_annotate.proto_data import reference

ROW = "<tr><td>iOS</td><td>Sign-in works A12 extra</td><td>{}</td><td>Ops</td><td>FLD-abc1 see member@x.org</td></tr>"


@pytest.fixture
def page(tmp_path, monkeypatch):
    page = tmp_path / "page"
    page.mkdir()
    store = {"schema_version": 2, "archived": {}, "anchors": {
        "ref:uat-plan~v2~0": [{"id": "c1", "text": "call 555-123-4567 or a@b.com", "created_at": "2026-11-19T10:00:00", "version": "v2"}],
        "chk:chart": [{"id": "c2", "text": "gone", "status": "deleted", "created_at": "2026-11-19T11:00:00"}],
        "review:x": [{"id": "c3", "text": "elsewhere", "created_at": "2026-11-19T12:00:00"}]}}
    (page / "comments.json").write_text(json.dumps(store))
    publish_plan_revision(page, "uat-plan", "<p>Draft one</p>", title="UAT plan proposal")
    publish_plan_revision(page, "uat-plan", "<p>Draft two FLD-xyz9</p>")
    publish_plan_revision(page, "go-live-checklist", "<table>" + ROW.format("done") + ROW.format("waiting") + "</table>",
                          title="Go-live checklist")
    monkeypatch.setattr(reference, "board", lambda: {"FLD-abc1": ["Sign in", "open"], "FLD-xyz9": ["UAT", "closed"]})
    monkeypatch.setattr(reference, "WM_FLOWS", tmp_path / "missing.json")
    monkeypatch.setattr(reference, "FLD_DIR", tmp_path / "nofld")
    monkeypatch.setattr(reference.documents, "__defaults__", (tmp_path / "nofld",))
    return page


def test_build(page):
    d = reference.build(page)
    plans = {p["id"]: p for p in d["plans"]}
    assert plans["uat-plan"]["st"] == "prop" and plans["uat-plan"]["kind"] == "plan"
    assert [r[0] for r in plans["uat-plan"]["revs"]] == ["v1", "v2"]
    assert plans["go-live-checklist"]["kind"] == "check"
    assert d["checklist"]["items"] == [["iOS", "Sign-in works", "done", "Ops", "FLD-abc1"]]  # unknown state row dropped
    assert d["beads"] == {"FLD-abc1": ["Sign in", "open"], "FLD-xyz9": ["UAT", "closed"]}
    assert d["flows"] == [] and d["docs"] == {"files": [], "groups": {}}
    assert [n["id"] for n in d["notes"]] == ["c1"]  # deleted and non-Reference notes left out
    assert "555" not in json.dumps(d) and "a@b.com" not in json.dumps(d)


def test_hide_and_state():
    assert reference.hide("mail x.y@z.co or (555) 123-4567") == "mail member@example.com or a phone number"
    assert reference.state_of({"section": "approved", "title": "Draft"}) == "ok"
    assert reference.state_of({"title": "Old notes"}) == "ref"


def test_documents(tmp_path):
    (tmp_path / "planning" / "go-live").mkdir(parents=True)
    (tmp_path / "planning" / "go-live" / "plan.md").write_text("ring a@b.com")
    (tmp_path / "planning" / "spec.docx").write_bytes(b"x")
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "keys.md").write_text("no")
    files = {f["n"]: f for f in reference.documents(tmp_path)["files"]}
    assert set(files) == {"plan.md", "spec.docx"}
    assert files["plan.md"]["md"] == "ring member@example.com" and files["spec.docx"]["k"] == "word"
