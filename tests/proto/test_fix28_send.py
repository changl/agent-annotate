"""Fix28 Send: Send opened first waits for the Reference and Pages & links reads, then lists a copy's 2.32.8 drafts; the
copy's Send records each by id; the receipt counts the round's ids on every row; a note saved on an earlier version of its
publication offers no Move, as today's Re-pin (r12 audit24 reference 1, 2, running 1, questions 1)."""

import json
from pathlib import Path

from agent_annotate.proto_data import published

WEB = Path(__file__).resolve().parents[2] / "src/agent_annotate/web/proto"


def test_send_waits_for_the_other_tabs_reads():
    q = (WEB / "questions.js").read_text()
    assert "const readOthers = c => others || (others = Promise.all(['reference', 'links'].map(a => c.data(a).catch(() => null))).then(() => { S.oin = true; relist(); }));" in q
    assert "readFor(c);\n    readOthers(c);" in q  # the toolbar's Send
    assert "S.gen = false; readOthers(ctx); draw(true)" in q  # ⌘↵ on Questions
    assert "const ok = n && D && S.oin," in q
    assert "data-sothers>Reading the notes on Reference and Pages &amp; links…" in q
    assert "if (!D || !S.oin) return ctx.toast(" in q


def test_copy_send_records_release_drafts_by_id():
    q = (WEB / "questions.js").read_text()
    sub = q[q.index("async function submitSim()"):q.index("P.copyWrite = fake;")]
    assert "for (const n of [D.notes, ...feeds].flat()) if (NK.out(n) && NK.own(n)) ids.add(n.id);" in sub
    assert "ids.forEach(id => NOTES.sent.add(id));" in sub and "return {ok: true, comment_ids: [...ids]};" in sub
    assert "else if (path === 'api/rounds/submit' && D) return submitSim();" in q
    # the feed brings a sent release note back as sent
    assert ".map(n => NOTES.sent.has(n.id) && !n.sent ? {...n, sent: true, flagged: true} : n)" in q


def test_receipt_counts_the_rounds_ids_on_every_row():
    q = (WEB / "questions.js").read_text()
    assert "notes = rows.map(x => x[5]).filter(Boolean), all = rows.length + (gen().trim() ? 1 : 0)" in q
    assert "const got = r && r.delivery === 'noop' ? 0 : ids ? Math.max(0, listed.all - listed.notes.filter(id => !ids.has(id)).length) : n;" in q
    assert "ctx.queueSent(got);" in q


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
