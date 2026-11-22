"""Fix28 Send: Send opened first waits for the Reference and Pages & links reads, then lists a copy's 2.32.8 drafts; the
copy's Send records each by id; the receipt counts the round's ids on every row; a note saved on an earlier version of its
publication offers no Move, as today's Re-pin (r12 audit24 reference 1, 2, running 1, questions 1)."""

import json
from pathlib import Path

from agent_annotate.proto_data import published

WEB = Path(__file__).resolve().parents[2] / "src/agent_annotate/web/proto"


def test_send_waits_for_the_other_tabs_reads():
    q = (WEB / "questions.js").read_text()
    # fix33: the other tabs' reads are in the one read state
    assert "const readOthers = (c, again) => OTHERS.forEach(([a]) => { const f = rs(a) === 'failed'; if (!rs(a) || (again && f)) { retry(a); track(a, c.data(a, f)).catch(() => {}); } });" in q
    assert "readFor(c);  // a failed read is not read again on opening: the sheet says so, with Try again (r12 audit30 questions 4)\n    readOthers(c);" in q  # the toolbar's Send
    assert "S.gen = false; readOthers(ctx); draw(true)" in q  # ⌘↵ on Questions
    assert "const ok = sendOn(n)," in q and "const allRead = () => !!(oin() && qIn());" in q
    assert "data-sothers>Reading the notes on ${OTHERS.filter(([a]) => rs(a) !== 'done').map(x => x[1]).join(' and ')}…" in q
    assert "if (!sendOn(sendCount() || 1)) { relist(); return ctx.toast(" in q  # fix33: the one gate


def test_copy_send_records_release_drafts_by_id():
    q = (WEB / "questions.js").read_text()
    sub = q[q.index("async function submitSim()"):q.index("P.copyWrite = fake;")]
    assert "for (const n of [D.notes, ...feeds].flat()) if (NK.out(n) && NK.mine(n)) ids.add(n.id);" in sub
    assert "ids.forEach(id => NOTES.sent.add(id));" in sub and "return {ok: true, comment_ids: [...ids]};" in sub
    assert "else if (path === 'api/rounds/submit' && D) return submitSim();" in q
    # the feed brings a sent release note back as sent
    assert ".map(n => NOTES.sent.has(n.id) && !n.sent ? {...n, sent: true, flagged: true} : n)" in q


def test_receipt_counts_the_rounds_ids_on_every_row():
    q = (WEB / "questions.js").read_text()
    assert "notes = rows.map(x => x[5]).filter(Boolean), all = rows.length + (gen().trim() ? 1 : 0)" in q
    assert "const got = again ? 0 : r && r.delivery === 'noop' ? Math.max(0, listed.all - listed.notes.length - answers.length - replies.length - closes.length - (fb ? 1 : 0)) : ids ? Math.max(0, listed.all - listed.notes.filter(id => !ids.has(id)).length) + [...ids].filter(id => !known.has(id)).length : n;" in q  # fix32: plus what it carried unlisted
    assert "ctx.queueSent(got, listed.q);" in q


def test_no_move_on_an_earlier_version_note(tmp_path, monkeypatch):
    q = (WEB / "questions.js").read_text()
    assert "+ (n.old ? '' : ibw('place', moving ? 'Moving' : 'Move'," in q
    r = (WEB.parents[1] / "proto_data/reference.py").read_text()
    assert '**({"old": True} if c.get("id") in cur and c.get("version") and c.get("version") != cur[c.get("id")] else {})' in r
    # merge carries each release note's publication's current version; split leaves it out of the prototype's store
    pub = tmp_path / "policy"
    pub.mkdir()
    (pub / "current.meta.json").write_text(json.dumps({"current": "v2"}))
    (pub / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {"s:a:p1": [{"id": "x1", "anchor_id": "s:a:p1", "version": "v1", "text": "t", "status": "open"}]}, "archived": {}}))
    home = published.Home(pub, "ref:policies~x", "ref:policies", [], [], {}, True)
    monkeypatch.setattr(published, "homes", lambda d: [home])
    store = published.merge(tmp_path, {"schema_version": 2, "anchors": {}, "archived": {}})
    assert (store.get(published.KEY) or {}).get("cur", {}).get("x1") == "v2"


def test_send_counts_what_it_delivers():
    """Lead's decision: the head, the toolbar and the sheet's Send count what Send delivers; peers' rows stay listed, marked."""
    q = (WEB / "questions.js").read_text()
    assert "const sendCount = () => sendItems().filter(x => !x[4]).length + (gen().trim() ? 1 : 0);" in q
    assert "sentCount" not in q  # one count, before and after
    assert "x.peer != null ? !!x.peer : peer(x.note), x.note]" in q
    assert "another reviewer’s, not sent" in q
    for f, s in [("reference.js", "note: n.id, peer: !NK().mine(n), html:"), ("links.js", "note: n.id, peer: !P.notes.mine(n), html:"),
                 ("history.js", "note: n.id, peer: !P.notes.mine(n), html:")]:
        assert s in (WEB / f).read_text(), f


def _whose(page_dir):
    return {"viewer": published.reader()}


def test_pooled_build_gets_the_readers_hash_and_caches_per_reader(tmp_path, monkeypatch):
    """The pooled worker is another process: the reader's hash goes in with the build, never through module state."""
    import sys
    import types
    import agent_annotate.proto_data as P
    mod = types.ModuleType("agent_annotate.proto_data.whosearea")
    mod.build, mod.stamp = _whose, (lambda d: 1)
    monkeypatch.setitem(sys.modules, "agent_annotate.proto_data.whosearea", mod)
    monkeypatch.setattr(P, "_ready", {})
    calls = []

    class Fresh:  # a worker with none of the server's module state
        def submit(self, fn, *a):
            calls.append(a)
            was, published._viewer["h"] = published._viewer["h"], None
            try:
                out = fn(*a)
            finally:
                published._viewer["h"] = was
            return types.SimpleNamespace(result=lambda timeout=None: out)
    monkeypatch.setattr(P, "_pool", Fresh())
    me, peer = published._hash("me@example.test"), published._hash("peer@example.test")
    assert json.loads(P._pooled("whosearea", tmp_path, me))["viewer"] == me
    assert json.loads(P._pooled("whosearea", tmp_path, peer))["viewer"] == peer
    assert json.loads(P._pooled("whosearea", tmp_path, None))["viewer"] is None  # an agent's read: nobody's own
    assert {k[2] for k in P._ready} == {me, peer, None}  # one cached build per reader
    assert [a[2] for a in calls] == [me, peer, None]
    # the server hands each area read this request's hash, taken before the build
    serve = (Path(P.__file__)).read_text()
    assert 'who = handler._identity()' in serve and 'getattr(handler, "proto_viewer", None))' in serve
    assert "self.proto_viewer = published.viewer(email)" in (Path(P.__file__).parents[1] / "sync_server.py").read_text()
    assert published.viewer("agent:x") is None and published.viewer("me@example.test") == me
