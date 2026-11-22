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


def handler(proto):
    from agent_annotate.sync_server import make_handler
    H = make_handler(proto, slug="proto")
    return H.__new__(H)


def by_id(store):
    return {c["id"]: (part, a, c) for part in ("anchors", "archived") for a, v in store[part].items() for c in v}


def test_a_save_never_writes_the_publications_store(tmp_path, monkeypatch):
    page, proto = meeting(tmp_path, monkeypatch)
    live = page / "comments.json"
    before, stamp = live.read_bytes(), live.stat().st_mtime_ns
    h = handler(proto)
    store = h._v2_load()
    h._v2_save(store)  # nothing changed: the prototype's store stays empty
    assert json.loads((proto / "comments.json").read_text())["anchors"] == {} and live.read_bytes() == before
    store = h._v2_load()
    store["anchors"].setdefault(f"{P}~tbl:kept:row:first~p1", []).append(
        {"id": "new", "anchor_id": f"{P}~tbl:kept:row:first~p1", "text": "proto point", "target": {"schema": 1, "tag": "img", "offset": {"dx": .5, "dy": .5}}})
    _, _, w = by_id(store)["w"]
    w["text"] = "edited here"  # edit a release note
    r = by_id(store)["r"][2]
    store["anchors"][f"{P}~tbl:kept:row:first"].remove(r)  # archive one
    store["archived"].setdefault(f"{P}~tbl:kept:row:first", []).append({**r, "status": "archived"})
    store["anchors"][f"{P}~fig:wide"] = []  # delete one
    h._v2_save(store)
    assert live.read_bytes() == before and live.stat().st_mtime_ns == stamp  # never rewritten, not even unchanged
    own = by_id(json.loads((proto / "comments.json").read_text()))
    assert set(own) == {"new", "w", "r", "p"} and own["p"][2]["status"] == "deleted" and own["w"][2]["text"] == "edited here"
    # 2.32.8 saves another note meanwhile; the next read has it, and the prototype's copies win
    s = json.loads(live.read_text())
    s["anchors"]["s:kept:p1"] = [note("later", "s:kept:p1", "later")]
    live.write_text(json.dumps(s))
    got = {n["id"]: n for n in links._build(proto)["notes"]}
    assert set(got) == {"w", "r", "c", "later", "new"} and got["w"]["text"] == "edited here" and got["r"]["closed"]
    assert got["later"]["a"] == f"{P}~s:kept:p1" and got["c"]["a"] == f"{P}~tbl:kept:row:first~p2"
    store = h._v2_load()
    assert set(by_id(store)) == {"w", "r", "c", "later", "new"}
    # re-open the archived one: still the prototype's copy
    r = by_id(store)["r"][2]
    store["archived"][f"{P}~tbl:kept:row:first"].remove(r)
    store["anchors"].setdefault(f"{P}~tbl:kept:row:first", []).append({**r, "status": "open"})
    s_before, s_stamp = live.read_bytes(), live.stat().st_mtime_ns
    h._v2_save(store)
    assert live.read_bytes() == s_before and live.stat().st_mtime_ns == s_stamp
    assert by_id(h._v2_load())["r"][2]["status"] == "open"


def test_the_reviewer_edits_and_removes_their_own_release_note_as_in_2_32_8(tmp_path, monkeypatch):
    """2.32.8 lets the note's author edit or remove it; the prototype masks the signed-in address, so the release note's
    author is masked the same way when read, and the change goes to the prototype's own store."""
    import http.client
    import threading
    from agent_annotate.sync_server import ReviewHTTPServer, make_handler
    page, proto = meeting(tmp_path, monkeypatch)
    live = page / "comments.json"
    before, stamp = live.read_bytes(), live.stat().st_mtime_ns
    httpd = ReviewHTTPServer(("127.0.0.1", 0), make_handler(proto, slug="proto", local_author="reviewer@example.invalid"))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    origin = "http://%s:%d" % httpd.server_address
    try:
        def call(method, path, body=None):
            conn = http.client.HTTPConnection(*httpd.server_address, timeout=5)
            conn.request(method, path, body=json.dumps(body) if body is not None else None,
                         headers={"Content-Type": "application/json", "Origin": origin, "Sec-Fetch-Site": "same-origin"})
            r = conn.getresponse()
            out = r.status, r.read()
            conn.close()
            return out
        assert call("PUT", "/api/comments/w", {"text": "edited in the prototype"})[0] == 200
        assert call("DELETE", "/api/comments/p")[0] == 200
        assert live.read_bytes() == before and live.stat().st_mtime_ns == stamp
        own = by_id(json.loads((proto / "comments.json").read_text()))
        assert own["w"][2]["text"] == "edited in the prototype" and own["p"][2]["status"] == "deleted"
        assert "reviewer@example.invalid" not in (proto / "comments.json").read_text()  # no address stored here
        got = {n["id"]: n for n in links._build(proto)["notes"]}
        assert "p" not in got and got["w"]["text"] == "edited in the prototype"
        assert call("POST", "/api/comments/r/archive", {})[0] == 200
        served = [(part, c["id"], c.get("text")) for part, _, c in pub._items(json.loads(call("GET", "/comments.json")[1]))]
        assert sorted(i for _, i, _ in served) == sorted({"w", "r", "c"}), served  # one copy each, the removed one gone
        assert ("anchors", "w", "edited in the prototype") in served and [p for p, i, _ in served if i == "r"] == ["archived"]
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_remove_holds_when_two_readers_share_one_publications_folder(tmp_path, monkeypatch):
    """The auditors' fixture serves the meeting and the usage audit from one folder, so each release note is read twice;
    removing it still leaves a tombstone and editing it still keeps one copy."""
    page, proto = meeting(tmp_path, monkeypatch)
    (page / "current.html").write_text((page / "versions" / "v1.html").read_text())
    monkeypatch.setattr(links, "USAGE_AUDIT", page / "current.html")
    store = pub.merge(proto, json.loads((proto / "comments.json").read_text()))
    assert len(store["_published"]["pub"]["p"]) == 2
    first = next(v for v in store["anchors"].values() if any(c["id"] == "p" for c in v))
    first[:] = [c for c in first if c["id"] != "p"]  # as _v2_delete_comment removes the first copy it finds
    own = pub.split(proto, store)
    assert [c["status"] for v in own["archived"].values() for c in v if c["id"] == "p"] == ["deleted"]
    (proto / "comments.json").write_text(json.dumps(own))
    assert "p" not in {c["id"] for _, _, c in pub._items(pub.merge(proto, own)) if c.get("status") != "deleted"}
    # an edit through the server keeps one copy in the served store
    import http.client, threading
    from agent_annotate.sync_server import ReviewHTTPServer, make_handler
    httpd = ReviewHTTPServer(("127.0.0.1", 0), make_handler(proto, slug="proto", local_author="reviewer@example.invalid"))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        conn = http.client.HTTPConnection(*httpd.server_address, timeout=5)
        conn.request("PUT", "/api/comments/w", json.dumps({"text": "edited"}), {"Content-Type": "application/json"})
        assert conn.getresponse().status == 200
        conn.request("GET", "/comments.json")
        served = [c.get("text") for _, _, c in pub._items(json.loads(conn.getresponse().read())) if c["id"] == "w"]
        assert served == ["edited"], served
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_the_shape_check_export_puts_a_prototype_note_in_2_32_8s_shape(tmp_path, monkeypatch):
    page, proto = meeting(tmp_path, monkeypatch)
    store = pub.merge(proto, {"schema_version": 2, "anchors": {}, "archived": {}})
    store["anchors"][f"{P}~tbl:kept:row:first~p1"] = [
        {"id": "new", "anchor_id": f"{P}~tbl:kept:row:first~p1", "text": "proto point", "target": {"schema": 1, "tag": "img", "offset": {"dx": .5, "dy": .5}}}]
    store["anchors"][f"{P}~s:kept:p1"] = [{"id": "q", "anchor_id": f"{P}~s:kept:p1", "text": "words", "target": {"schema": 1, "tag": "p", "quote": "Intro"}}]
    before = (page / "comments.json").read_bytes()
    out = by_id(pub.export(proto, page, store))
    assert (page / "comments.json").read_bytes() == before
    assert set(out) == {"w", "r", "c", "p", "new", "q"} and out["c"][2] == RELEASED[2]
    assert out["new"][1] == "tbl:kept:row:first" and out["new"][2]["target"]["css"] == "td:nth-of-type(2) > figure:nth-of-type(1) > img:nth-of-type(1)"
    assert out["q"][1] == "s:kept:p1" and out["q"][2]["target"]["selected_quote"] == "Intro"


def hosted():
    """The hosted prototype's page folder (annotate-proto/env.sh: DEST=$ROOT/reviews/$SLUG)."""
    env = Path("/Users/changlee/annotate-proto/env.sh")
    if not env.is_file():
        return None
    v = dict(re.findall(r"^(?:export )?(ROOT|SLUG|DEST)=(\S+)", env.read_text(), re.M))
    return Path(v["DEST"].replace("$ROOT", v["ROOT"]).replace("$SLUG", v["SLUG"]))


LIVE = [Path.home() / "projects/fastlane-drive/reviews/fld-admin-meeting", Path.home() / "projects/FastLane Drive/planning/operations/usage-audit-2026-11-06/page",
        Path.home() / "projects/rebex/reviews/rebex-policies"]


def test_the_hosted_prototypes_saves_stay_under_its_root(monkeypatch):
    from agent_annotate.proto_data.replaced import PROTO_ROOT
    monkeypatch.delenv("ANNOTATE_PROTO_ROOT")
    dest = hosted()
    for page in ([dest] if dest else []) + [PROTO_ROOT / "reviews/fld-proto", PROTO_ROOT / "reviews/proto-rebex"]:
        assert PROTO_ROOT in pub.guard(page / "comments.json").parents
    for folder in LIVE + [PROTO_ROOT.parent / "projects/agent-annotate/reviews/x", Path("/Volumes/x")]:
        try:
            pub.guard(folder / "comments.json")
        except PermissionError:
            continue
        raise AssertionError(f"{folder} was allowed")


def test_the_save_hook_refuses_a_page_outside_the_root(tmp_path, monkeypatch):
    page, proto = meeting(tmp_path, monkeypatch)
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.setenv("ANNOTATE_PROTO_ROOT", str(tmp_path / "elsewhere"))
    h = handler(proto)
    before = (proto / "comments.json").read_bytes()
    try:
        h._v2_save(h._v2_load())
    except PermissionError:
        assert (proto / "comments.json").read_bytes() == before
    else:
        raise AssertionError("saved outside the prototype's root")


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
