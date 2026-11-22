"""r12 audit22 reference 1-2: a published page's notes live in its own store, in 2.32.8's shape, whichever saved them;
Go to it on an earlier plan revision keeps that revision for a row or a cell picture's point."""
import json
import re
from pathlib import Path

from test_fix24_kept import published

from agent_annotate.proto_data import links, published as pub, reference

REF = (Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto" / "reference.js").read_text()
P = "doc:kept-admin-meeting~p"


def note(i, a, text, target=None):  # as 2.32.8 saves one (release-carry-points.ndjson)
    return {"id": i, "anchor_id": a, "text": text, "status": "open", "author": "reviewer@example.invalid", "author_name": "Reviewer",
            "created_at": "2026-11-21T10:00:00Z", **({"target": target} if target else {})}


RELEASED = [note("w", "s:kept:p2", "words", {"schema": 1, "tag": "p", "selected_quote": "the picture"}),
            note("r", "tbl:kept:row:first", "row", {"tag": "td", "offset": {"dx": .3, "dy": .4}, "css": "td:nth-of-type(2)"}),
            note("c", "tbl:kept:row:first", "cell", {"tag": "img", "offset": {"dx": .3, "dy": .4}, "css": "td:nth-of-type(2) > figure:nth-of-type(2) > img:nth-of-type(1)"}),
            note("p", "fig:wide", "point", {"tag": "img", "offset": {"dx": .3, "dy": .4}, "css": "img:nth-of-type(1)"})]


def meeting(tmp_path, monkeypatch):
    html, page = published(tmp_path)
    (page / "versions").mkdir()
    (page / "versions" / "v1.html").write_text(html)
    (page / "current.meta.json").write_text(json.dumps({"history": [{"version": "v1", "ts": "2026-11-20T00:00:00Z"}]}))
    store = {"schema_version": 2, "anchors": {}, "archived": {}}
    for n in RELEASED:
        store["anchors"].setdefault(n["anchor_id"], []).append(n)
    (page / "comments.json").write_text(json.dumps(store))
    monkeypatch.setattr(links, "MEETING", page)
    monkeypatch.setattr(links, "USAGE_AUDIT", tmp_path / "missing.html")
    monkeypatch.setattr(links, "LOAD_TEST", tmp_path / "missing")
    proto = tmp_path / "proto"
    proto.mkdir()
    (proto / "current.meta.json").write_text(json.dumps({"ui": "proto"}))
    (proto / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {}, "archived": {}}))
    return page, proto


def test_released_notes_show_on_their_places_in_the_kept_reader(tmp_path, monkeypatch):
    page, proto = meeting(tmp_path, monkeypatch)
    got = {n["id"]: n for n in links._build(proto)["notes"]}
    assert got["w"]["a"] == f"{P}~s:kept:p2" and got["w"]["target"]["quote"] == "the picture"
    assert got["r"]["a"] == f"{P}~tbl:kept:row:first"
    assert got["c"]["a"] == f"{P}~tbl:kept:row:first~p2"  # the second picture in the row: Proto.media.pk
    assert got["p"]["a"] == f"{P}~fig:wide"
    assert not any(n["sent"] for n in got.values())  # unsent there, so listed in Send


def test_a_note_saved_in_the_prototype_lands_in_the_publications_store(tmp_path, monkeypatch):
    page, proto = meeting(tmp_path, monkeypatch)
    before = (page / "comments.json").read_bytes()
    store = pub.merge(proto, json.loads((proto / "comments.json").read_text()))
    assert pub.split(proto, store)["anchors"] == {} and (page / "comments.json").read_bytes() == before  # nothing changed: not written
    store["anchors"].setdefault(f"{P}~tbl:kept:row:first~p1", []).append(
        {"id": "new", "anchor_id": f"{P}~tbl:kept:row:first~p1", "text": "proto point", "target": {"schema": 1, "tag": "img", "offset": {"dx": .5, "dy": .5}}})
    store["anchors"].setdefault(f"{P}~s:kept:p1", []).append({"id": "q", "anchor_id": f"{P}~s:kept:p1", "text": "proto words", "target": {"schema": 1, "tag": "p", "quote": "Intro"}})
    store["anchors"].setdefault("doc:kept-admin-meeting", []).append({"id": "whole", "anchor_id": "doc:kept-admin-meeting", "text": "whole"})
    # 2.32.8 saves another note meanwhile: it stays
    s = json.loads((page / "comments.json").read_text())
    s["anchors"]["s:kept:p1"] = [note("later", "s:kept:p1", "later")]
    (page / "comments.json").write_text(json.dumps(s))
    own = pub.split(proto, store)
    assert list(own["anchors"]) == ["doc:kept-admin-meeting"]  # no anchor for the whole document: it stays here
    s = json.loads((page / "comments.json").read_text())
    by = {c["id"]: c for v in s["anchors"].values() for c in v}
    assert set(by) == {"w", "r", "c", "p", "later", "new", "q"} and by["c"] == RELEASED[2]  # 2.32.8's own unchanged
    assert by["new"]["anchor_id"] == "tbl:kept:row:first" and by["new"]["target"]["css"] == "td:nth-of-type(2) > figure:nth-of-type(1) > img:nth-of-type(1)"
    assert by["q"]["anchor_id"] == "s:kept:p1" and by["q"]["target"]["selected_quote"] == "Intro"
    # a removed note goes from the publication's store too
    store = pub.merge(proto, own)
    store["anchors"][f"{P}~s:kept:p1"] = [c for c in store["anchors"][f"{P}~s:kept:p1"] if c["id"] != "q"]
    pub.split(proto, store)
    assert "q" not in {c["id"] for v in json.loads((page / "comments.json").read_text())["anchors"].values() for c in v}


def test_policies_notes_by_the_readers_line_numbers(tmp_path):
    html, page = published(tmp_path)
    root = tmp_path / "rebex"
    (root / "reviews").mkdir(parents=True)
    page.rename(root / "reviews" / "rebex-policies")
    (root / "reviews" / "rebex-policies" / "current.html").write_text(html)
    (root / "reviews" / "rebex-policies" / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {"tbl:kept:row:first": [RELEASED[2]]}, "archived": {}}))
    proto = tmp_path / "copy"
    proto.mkdir()
    (proto / "current.meta.json").write_text(json.dumps({"proto_copy_of": "rebex", "proto_source": str(root / "reviews" / "rebex")}))
    (n,) = reference.notes(proto)
    b = links.html_blocks(html, reference._kept_src("policies", root / "reviews" / "rebex-policies"))
    i = next(i for i, x in enumerate(b) if x[0] == "tbl")
    assert n["a"] == f"ref:policies~x~{i}~r1~p2"


def test_go_to_it_keeps_an_earlier_revision_for_a_row_and_a_cell_picture():
    src = re.search(r"const m = (/\^ref:.*?/)\.exec\(a \|\| ''\), x = m && xOf", REF).group(1)
    rx = re.compile(src[1:-1].replace("\\/", "/"))
    for k in ("ref:plan~v1~4", "ref:plan~v1~4~r2", "ref:plan~v1~4~r2~p1"):
        assert rx.fullmatch(k).group(2) == "v1", k
    assert rx.fullmatch("ref:lib~c~3").group(2) == "c"
