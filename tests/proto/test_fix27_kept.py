"""r12 audit23: a removed release note stays removed whatever happened to it first (running 1); a copy's mirror of its
policies notes joins the release record on the reader's key (running 2); a note whose words left the newest meeting
revision stays on its own revision (reference 1); another reviewer's release drafts are a peer's (frame 1)."""
import http.client
import json
import threading

from test_fix26_kept import P, RELEASED, by_id, meeting, note

from agent_annotate.proto_data import links, published as pub


class Server:
    def __init__(self, proto, author="reviewer@example.invalid"):
        from agent_annotate.sync_server import ReviewHTTPServer, make_handler
        self.httpd = ReviewHTTPServer(("127.0.0.1", 0), make_handler(proto, slug="proto", local_author=author))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.origin = "http://%s:%d" % self.httpd.server_address

    def __call__(self, method, path, body=None):
        conn = http.client.HTTPConnection(*self.httpd.server_address, timeout=5)
        conn.request(method, path, body=json.dumps(body) if body is not None else None,
                     headers={"Content-Type": "application/json", "Origin": self.origin, "Sec-Fetch-Site": "same-origin"})
        r = conn.getresponse()
        out = r.status, r.read()
        conn.close()
        return out

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def served_ids(call):
    return {c["id"] for _, _, c in pub._items(json.loads(call("GET", "/comments.json")[1])) if c.get("status") != "deleted"}


def test_a_changed_release_note_stays_removed(tmp_path, monkeypatch):
    """Edit → Remove and Close → Re-open → Remove: the removal wins over the prototype's own copy and the release record."""
    page, proto = meeting(tmp_path, monkeypatch)
    live = page / "comments.json"
    before, stamp = live.read_bytes(), live.stat().st_mtime_ns
    call = Server(proto)
    try:
        assert call("PUT", "/api/comments/w", {"text": "edited here"})[0] == 200
        assert call("DELETE", "/api/comments/w")[0] == 200
        assert call("POST", "/api/comments/p/archive", {})[0] == 200
        assert call("POST", "/api/comments/p/restore", {})[0] == 200
        assert call("DELETE", "/api/comments/p")[0] == 200
        assert call("DELETE", "/api/comments/r")[0] == 200  # unchanged: as before
        assert served_ids(call) == {"c"}
        own = by_id(json.loads((proto / "comments.json").read_text()))
        assert {i: own[i][2]["status"] for i in "wpr"} == {"w": "deleted", "p": "deleted", "r": "deleted"}
        assert live.read_bytes() == before and live.stat().st_mtime_ns == stamp
    finally:
        call.close()
    pub._homes.clear()  # as after a restart
    call = Server(proto)
    try:
        assert served_ids(call) == {"c"}
        assert {n["id"] for n in links._build(proto)["notes"]} == {"c"}
    finally:
        call.close()


def test_a_copys_mirror_joins_the_release_record_on_the_readers_key(tmp_path, monkeypatch):
    """The Rebex copy holds its policies notes under copy:policies with the same ids: merged by id onto the reader's key,
    with the mirror's own fields and replies, and put back unchanged by split()."""
    page, proto = meeting(tmp_path, monkeypatch)
    mirror = {**RELEASED[0], "anchor_id": "copy:policies", "decision_request": {"prompt": "?"}, "replies": [{"id": "x", "text": "mirror reply"}]}
    store = {"schema_version": 2, "anchors": {"copy:policies": [mirror]}, "archived": {}}
    (proto / "comments.json").write_text(json.dumps(store))
    got = {n["id"]: n for n in links._build(proto)["notes"]}
    assert got["w"]["a"] == f"{P}~s:kept:p2"  # on the reader's place, not dropped for the mirror
    merged = pub.merge(proto, store)
    assert "copy:policies" not in merged["anchors"]
    w = by_id(merged)["w"][2]
    assert w["decision_request"] == {"prompt": "?"} and [r["text"] for r in w["replies"]] == ["mirror reply"]
    assert pub.split(proto, merged) == store  # unchanged: the mirror back where it was, nothing else kept
    # removed: gone from both, with a tombstone
    merged["anchors"][f"{P}~s:kept:p2"] = []
    own = pub.split(proto, merged)
    assert "copy:policies" not in own["anchors"] and [c["status"] for _, _, c in pub._items(own) if c["id"] == "w"] == ["deleted"]
    assert "w" not in {c["id"] for _, _, c in pub._items(pub.merge(proto, own)) if c.get("status") != "deleted"}


def test_a_note_on_words_gone_from_the_newest_revision_stays_on_its_revision(tmp_path, monkeypatch):
    page, proto = meeting(tmp_path, monkeypatch)
    v1 = (page / "versions" / "v1.html").read_text()
    v2 = v1.replace('data-anchor-id="s:kept:p2"', 'data-anchor-id="s:kept:p2-gone"').replace("the picture", "other words")
    assert v2 != v1
    (page / "versions" / "v2.html").write_text(v2)
    (page / "current.meta.json").write_text(json.dumps({"history": [{"version": "v1", "ts": "2026-11-20T00:00:00Z"}, {"version": "v2", "ts": "2026-11-21T00:00:00Z"}]}))
    pub._homes.clear()
    got = {n["id"]: n for n in links._build(proto)["notes"]}
    assert got["w"]["a"] == f"{P}~s:kept:p2"  # revision 1's anchor, not the whole document's
    m = links.meeting(page)
    assert "s:kept:p2" in m["revs"][0]["ids"] and "s:kept:p2" not in m["ids"]


def test_another_reviewers_release_drafts_are_a_peers(tmp_path, monkeypatch):
    page, proto = meeting(tmp_path, monkeypatch)
    s = json.loads((page / "comments.json").read_text())
    s["anchors"]["s:kept:p1"] = [{**note("peer", "s:kept:p1", "peer draft"), "author": "peer@example.test", "author_email": "peer@example.test"}]
    (page / "comments.json").write_text(json.dumps(s))
    live = page / "comments.json"
    before, stamp = live.read_bytes(), live.stat().st_mtime_ns
    call = Server(proto)
    try:
        assert call("DELETE", "/api/comments/peer")[0] == 403  # 2.32.8 offers a peer no Remove
        assert call("PUT", "/api/comments/peer", {"text": "x"})[0] == 403
        assert call("PUT", "/api/comments/w", {"text": "mine"})[0] == 200  # his own stays editable (0970379)
        body = call("GET", "/comments.json")[1].decode()
        assert "@example.test" not in body and "@example.invalid" not in body  # no raw address leaves
        c = by_id(json.loads(body))
        assert c["peer"][2]["author"].startswith("reviewer-") and c["w"][2]["author"] == "member@example.com"
        from agent_annotate.proto_data.questions import author_key
        assert author_key(c["peer"][2]["author"]) != author_key("member@example.com")  # the feed's `by` is never his
        assert live.read_bytes() == before and live.stat().st_mtime_ns == stamp
    finally:
        call.close()
