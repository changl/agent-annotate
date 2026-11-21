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
        "ref:uat-plan~v2~0": [{"id": "c1", "text": "call 555-123-4567 or a@b.com", "created_at": "2026-11-19T10:00:00", "version": "v2",
                               "target": {"schema": 1, "tag": "img", "offset": {"dx": 0.25, "dy": 0.5}}}],
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
    monkeypatch.setattr(reference.extras, "__defaults__", (tmp_path / "nofld",))
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
    assert d["notes"][0]["target"]["offset"] == {"dx": 0.25, "dy": 0.5}  # a spot note keeps its spot
    assert d["extras"] == []
    assert "555" not in json.dumps(d) and "a@b.com" not in json.dumps(d)


def test_copy_gets_its_findings_register_not_fld_files(page, tmp_path, monkeypatch):
    """A copy of Rebex lists Rebex's audit as a findings register (the mock's 97-99), and none of FastLane Drive's files."""
    proj = tmp_path / "rebex"
    audit = proj / "outputs" / "burnt-damascus-etching-audit-2026-10-27"
    (proj / "catalog").mkdir(parents=True)
    audit.mkdir(parents=True)
    (proj / "catalog" / "a.jpg").write_bytes(b"\xff\xd8jpeg")
    (audit / "findings.json").write_text(json.dumps({
        "audited_at": "2026-10-27T16:53:32+00:00", "conclusion": "No mark found; ask a@b.com", "limitations": ["Small knives"],
        "photoshoot_originals_screened": 259, "owner_supplied_originals_screened": 21, "burnt_family_manufacturer_sources_screened": 109,
        "originals_changed": False, "catalog_selections_changed": False,
        "references": [{"label": "Chef", "original": "assets/1.jpg", "preview": "catalog/a.jpg", "finding": "No mark", "rebex_etching_visible": False, "original_sha256": "1ca5579343e04043ee"},
                       {"label": "Cleaver", "original": "assets/2.jpg", "preview": "catalog/missing.jpg", "finding": "Mark seen", "rebex_etching_visible": True, "original_sha256": "ab"}]}))
    (page / "current.meta.json").write_text(json.dumps({"proto_copy_of": "rebex", "proto_source": str(proj / "reviews" / "rebex")}))
    monkeypatch.setattr(reference, "extras", lambda: [{"id": "chapter-owner-list"}])
    monkeypatch.setattr(reference, "flows", lambda: [{"id": "flow:x"}])
    d = reference.build(page)
    assert d["flows"] == [] and d["docs"]["files"] == []
    [x] = d["extras"]
    assert x["id"] == "find:burnt-damascus-etching-audit-2026-10-27" and x["t"] == "Etching audit: Burnt Damascus knives" and x["kind"] == "data"
    f = x["find"]
    assert f["screened"] == [[259, "photoshoot originals"], [21, "owner originals"], [109, "manufacturer pictures"]] and f["untouched"]
    assert [i["state"] for i in f["items"]] == ["No Rebex mark", "Rebex mark seen"]
    assert f["items"][0]["src"].startswith("data:image/jpeg;base64,") and f["items"][1]["src"] == ""  # a missing proof picture is left out
    assert f["items"][0]["sha"] == "1ca5579343e0" and "a@b.com" not in json.dumps(d)
    (page / "current.meta.json").write_text("{}")  # the FastLane Drive page itself: its files, no register
    assert reference.build(page)["extras"] == [{"id": "chapter-owner-list"}]


def test_hide_and_state():
    assert reference.hide("mail x.y@z.co or (555) 123-4567") == "mail member@example.com or a phone number"
    assert reference.state_of({"section": "approved", "title": "Draft"}) == "ok"
    assert reference.state_of({"title": "Old notes"}) == "ref"


def test_extras(tmp_path):
    import zipfile
    (tmp_path / "planning").mkdir()
    (tmp_path / "design").mkdir()
    (tmp_path / "planning" / "04-delivery-scope.md").write_text("# Scope\n\nask a@b.com")
    (tmp_path / "planning" / "10-legal-review-list.csv").write_text("A,Item,Owner\nA,Terms,Ops\nB,Topic,Who\nB,Privacy,Legal\n")
    (tmp_path / "design" / "tokens.json").write_text('{"color": {"bg": "#000", "gap": 4}}')
    with zipfile.ZipFile(tmp_path / "Ask-Nicole (edited).docx", "w") as z:
        z.writestr("word/document.xml", '<w:p ><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:t>Intro</w:t></w:p><w:p ><w:t>Body &amp; more</w:t></w:p>')
    x = {i["id"]: i for i in reference.extras(tmp_path)}
    assert set(x) == {"delivery-scope", "legal-review-list", "design-tokens", "ask-nicole-word"}  # missing files skipped
    assert x["delivery-scope"]["md"] == "# Scope\n\nask member@example.com"
    assert x["legal-review-list"]["parts"] == [["A", ["Item", "Owner"], [["Terms", "Ops"]]], ["B", ["Topic", "Who"], [["Privacy", "Legal"]]]]
    assert x["design-tokens"]["parts"][0][2] == [["color.bg", "#000"], ["color.gap", "4"]]
    assert x["ask-nicole-word"]["md"] == "# Intro\n\nBody & more"


def test_extras_carry_the_mocks_entries(tmp_path):
    """The roadmap, the email designs, the drive screens and the chapter sheet, each masked or left without member data."""
    for d in ("planning", "design/alt-emails-v1/app", "design/apps-v2/kit", "design/page-v135/shots"):
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "planning" / "05-roadmap.md").write_text("# Roadmap\n\ncar first")
    (tmp_path / "design/apps-v2/kit/fld.css").write_text("body{color:red;background:url(img/x.png)}")
    (tmp_path / "design/alt-emails-v1/app/m3-confirm.html").write_text(
        '<html><head><link rel="stylesheet" href="../kit.css"></head><body><script>alert(1)</script><a href="https://x.y/z">pat@gmail.com</a></body></html>')
    (tmp_path / "design/page-v135/shots/390-screen-47-compare.png").write_bytes(b"\x89PNG")
    (tmp_path / "FLD Chapter Owner List.xlsx").write_bytes(b"PK member rows")
    x = {i["id"]: i for i in reference.extras(tmp_path)}
    assert x["delivery-roadmap"]["t"] == "Delivery roadmap, car-first revision" and x["delivery-roadmap"]["kind"] == "plan"
    h = x["email-designs"]["html"]
    assert "color:red" in h and "url(" not in h and "<script" not in h and "<link" not in h and "x.y" not in h and "gmail" not in h
    assert x["drive-screens"]["img"].startswith("data:image/png;base64,") and "Screen 47" in x["drive-screens"]["note"]
    assert x["chapter-owner-list"]["md"] == "" and "member rows" not in str(x["chapter-owner-list"])
    assert [e[1] for e in reference.EXTRAS if e[0] == "store-review-notes"] == ["App store review notes and trader guide"]


def test_documents(tmp_path):
    (tmp_path / "planning" / "go-live").mkdir(parents=True)
    (tmp_path / "planning" / "go-live" / "plan.md").write_text("ring a@b.com")
    (tmp_path / "planning" / "spec.docx").write_bytes(b"x")
    (tmp_path / "secrets").mkdir()
    (tmp_path / "secrets" / "keys.md").write_text("no")
    files = {f["n"]: f for f in reference.documents(tmp_path)["files"]}
    assert set(files) == {"plan.md", "spec.docx"}
    assert files["plan.md"]["md"] == "ring member@example.com" and files["spec.docx"]["k"] == "word"
