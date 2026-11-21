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
    monkeypatch.setattr(reference, "board", lambda code="fld": {"FLD-abc1": ["Sign in", "open"], "FLD-xyz9": ["UAT", "closed"]})
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
    assert d["flows"] == [] and "docs" not in d  # documents are listed in Pages & links only
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
    assert d["flows"] == [] and "docs" not in d
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


def test_task_titles_come_from_the_pages_own_board(page, monkeypatch):
    """A Rebex copy names RBX tasks from Rebex's board only; a project with no board gets no titles, never FastLane Drive's."""
    asked = []
    monkeypatch.setattr(reference, "board", lambda code="fld": asked.append(code) or {"RBX-gaw": ["Rebuild sets", "open"]} if code == "rebex" else {})
    publish_plan_revision(page, "uat-plan", "<p>Draft three RBX-gaw FLD-xyz9</p>")
    (page / "current.meta.json").write_text(json.dumps({"proto_copy_of": "rebex"}))
    assert reference.build(page)["beads"] == {"RBX-gaw": ["Rebuild sets", "open"]} and asked == ["rebex"]
    (page / "current.meta.json").write_text(json.dumps({"proto_copy_of": "leadory"}))
    assert reference.build(page)["beads"] == {}


def test_board_reads_only_the_projects_own_board(monkeypatch):
    calls = []
    monkeypatch.setattr(reference, "_boards", {})
    monkeypatch.setattr(reference.running, "board_dir", lambda code: None if code == "leadory" else f"/boards/{code}")
    monkeypatch.setattr(reference.subprocess, "run", lambda argv, **k: calls.append(argv) or type("R", (), {"stdout": '[{"id": "RBX-1", "title": "T"}]'})())
    assert reference.board("rebex") == {"RBX-1": ["T", ""]} and calls[0][:4] == ["bd", "-C", "/boards/rebex", "--readonly"]
    calls.clear()
    assert reference.board("leadory") == {} and calls == []


def _rev(i, t):
    return {"id": i, "delta": {"ops": [{"insert": t}]}}


def test_copy_library_lists_every_line_needs_you_first(tmp_path):
    """Rebex's App text (audit3 finding 2): each piece of text, its state, the wording before it, Needs you first."""
    (tmp_path / "copy.json").write_text(json.dumps({"blocks": [
        {"id": "a", "title": "Footer", "status": "done", "current": "r1", "revisions": [_rev("r1", "Ship fast")]},
        {"id": "b", "title": "Hero", "status": "needs_you", "current": "r2", "revisions": [_rev("r1", "Old hero"), _rev("r2", "New hero for a@b.com")]},
        {"id": "c", "title": "Terms", "status": "held", "current": "r1", "revisions": [_rev("r1", "Terms text"), _rev("r2", "Terms proposed")]}]}))
    x = reference.copy_library(tmp_path)
    assert [c[:4] for c in x["copy"]] == [["Hero", "New hero for member@example.com", "Needs you", "Old hero"],
                                         ["Terms", "Terms text", "Held back", ""], ["Footer", "Ship fast", "Done", ""]]
    assert x["copy"][0][4] == ["Old hero"] and x["copy"][1][4] == ["Terms proposed"] and x["m"] == "3 pieces of text · 1 needs you · 1 held back · 1 done"
    assert reference.copy_library(tmp_path / "none") is None


def test_finding_status_follows_the_live_findings_view():
    """The live register's rule (findings.js statusOf): agreed-to-fix waits on the agent, keep is done, fixed is done."""
    fs = reference._finding_status
    assert fs({}) == "needs" and fs({"response_text": "On it"}) == "waiting" and fs({"fixed": True}) == "done"
    assert fs({"decision": {"verdict": "select", "option_id": "fix"}}) == "waiting"
    assert fs({"decision": {"verdict": "select", "option_id": "keep"}}) == "done"
    assert fs({"decision": {"verdict": "select", "text": "Keep it"}, "decision_request": {"options": [{"id": "keep", "label": "Keep it"}]}}) == "done"


def test_route_animation_is_listed_with_its_note_only(tmp_path):
    """FastLane Drive's approved route animation (audit3 finding 8) is named by the UI lead's approvals; that record is not shown as the item."""
    p = tmp_path / "planning/operations/orchestration/run_c9d587c967ba/reports/ui-lead"
    p.mkdir(parents=True)
    (p / "approved.md").write_text("# Approved\n\nthinking animation")
    x = {i["id"]: i for i in reference.extras(tmp_path)}["route-animation"]
    assert x["md"] == "" and "recordings are not on this Mac" in x["note"]


def test_preview_store_is_staged_working(tmp_path):
    """Audit4 finding 1: the store runs (Shop Damascus opens, Quick add fills the demo cart) with this Mac's pictures."""
    from PIL import Image
    proj, page = tmp_path / "rebex", tmp_path / "proto-rebex"
    site = proj / "prototype" / "site"
    (site / "js").mkdir(parents=True)
    (proj / "catalog" / "site-images" / "chef").mkdir(parents=True)
    page.mkdir()
    (page / "current.meta.json").write_text(json.dumps({"proto_copy_of": "rebex", "proto_source": str(proj / "reviews" / "rebex")}))
    (site / "css").mkdir()
    (site / "css" / "site.css").write_text(".hero{color:red}")
    page_html = ('<head><link href="https://fonts.googleapis.com/x" rel="stylesheet"><link rel="stylesheet" href="css/site.css"></head>'
                 '<a href="collection-damascus.html">Shop Damascus</a><img src="https://rebexcutlery.com/cdn/shop/files/DSC_1.jpg?v=2&width=800"> help@rebex.com'
                 '<script src="js/products.js"></script>\n<script src="js/site.js"></script>')
    (site / "index.html").write_text(page_html)
    (site / "collection-damascus.html").write_text(page_html.replace("help@rebex.com", '<a href="https://elsewhere.com/x">out</a>'))
    (site / "js" / "site.js").write_text('const CDN = "https://rebexcutlery.com/cdn/shop/";\nconst img = (p, w) => CDN + p + "&width=" + (w || 600);\n'
                                         'const save = () => localStorage.setItem(KEY, "[]"); const t = "</script>";')
    (site / "js" / "products.js").write_text('window.P = {a: {img: "files/DSC_1.jpg?v=9"}, b: {img: "products/1.jpg?v=9"}};')
    Image.new("RGB", (2000, 1000)).save(proj / "catalog" / "site-images" / "chef" / "01-DSC_1.jpg")
    (proj / "catalog" / "download-log.json").write_text(json.dumps({"results": [
        {"ok": True, "path": "site-images/chef/01-DSC_1.jpg"}, {"ok": False, "path": "site-images/chef/02-1.jpg"}]}))
    assert reference.stage_store(page) == 1  # products/1.jpg was never downloaded
    out = page / reference.STORE
    assert sorted(p.name for p in out.iterdir()) == ["collection-damascus.html", "index.html"]  # each page whole: nothing else to request
    idx = (out / "index.html").read_text()
    assert 'href="collection-damascus.html"' in idx and "fonts.googleapis" not in idx and "<style>.hero{color:red}</style>" in idx
    assert '<img src="data:image/jpeg;base64,' in idx and "cdn/" not in idx.split("<script>")[0]  # the picture travels with the page
    assert "help@rebex.com" not in idx and "elsewhere.com" not in (out / "collection-damascus.html").read_text()
    js = idx.split("<script>")[2]
    assert js.startswith("var rbxStore=") and "rbxStore.setItem(KEY" in js  # the sandboxed store keeps its cart without storage
    assert '(RBX_PICS[p.split("?")[0]] || "")' in js and '"files/DSC_1.jpg": "data:image/jpeg;base64,' in js and '"products/1.jpg": ""' in js
    assert "<\\/script>" in js and js.count("</script>") == 1
    [x] = [x for x in reference.copied(page, json.loads((page / "current.meta.json").read_text())) if x["id"] == "preview-store"]
    assert x["src"] == "assets/preview-store/index.html" and "html" not in x
    s = (WEB / "reference.js").read_text()
    assert 'sandbox="allow-scripts" src="${esc(new URL(x.src' in s
    # its links are refused from inside the sandbox: the store asks the page to open the next one, unless the click was a Quick add
    assert "!e.defaultPrevented" in js and "window.parent.postMessage({rbxStore:h},'*')" in js
    assert "e.source === f.contentWindow" in s and "/^[\\w-]+\\.html(\\?[\\w=&%.-]*)?$/.test(h)) f.src = new URL(h, f.src).href" in s


WEB = reference.Path(reference.__file__).resolve().parents[1] / "web" / "proto"


def test_copy_library_save_keeps_formatting():
    """Audit4 finding 2: Save keeps Bold and the other editor formatting, cleaned to the editor's own tags."""
    s = (WEB / "reference.js").read_text()
    assert "S.cp.set(ck, {st: 'edit', html: t ? rich(t.innerHTML) : ''})" in s and "s.st === 'edit' ? s.html" in s
    assert "innerText.trim()" not in s


def test_renamed_topic_keeps_its_controls_on_a_copy():
    """Audit4 finding 3: a copy's simulated write returns no topics, so rename, combine and new topics change the list here."""
    s = (WEB / "reference.js").read_text()
    assert "else if (b.rename) D.topics = D.topics.map(t => t === b.rename ? b.to : t);" in s
    assert s.count("topics(await ctx.api(") == 1  # every topic write goes through topicApi


def test_copy_library_actions_fit_a_phone():
    """Audit4 finding 7: at 390 each action stays on one line instead of breaking a letter at a time."""
    css = (WEB / "reference.css").read_text()
    assert ".tab-reference .rf-copy td.rf-cact .lk{white-space:nowrap" in css
