"""Fix16 notes: a saved note lists at once from its stored record; no late or stale read removes a row (r12 audit14 questions 1,
running 1); notes close, re-open and move; a sent answer offers Change; new activity is marked."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from agent_annotate.proto_data import history, questions

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
Q = (WEB / "questions.js").read_text()
HIST = (WEB / "history.js").read_text()


def grab(src, start, end):
    i = src.index(start)
    return src[i:src.index(end, i) + len(end)]


def node(tmp_path, js):
    exe = shutil.which("node")
    if not exe:
        pytest.skip("node not installed")
    f = tmp_path / "t.js"
    f.write_text(js)
    r = subprocess.run([exe, str(f)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr + r.stdout


def test_questions_keeps_a_saved_note_the_read_predates(tmp_path):
    """Finding 1, running 1: a read built before the save keeps the stored record; a newer read that lacks it drops it."""
    fn = grab(Q, "  const after = ", "sent: false, at: r.at});\n  }")
    node(tmp_path, f"""
const assert = require('assert');
let saved = [{{id: 'n1', v: 'v3', at: '2026-11-21T10:00:05Z', anchor: 'a', text: 'x'}}, {{id: 'n2', v: 'v2', at: '2026-11-21T10:00:05Z'}}, {{id: 'n3', v: 'v3', at: '2026-11-21T10:00:05Z'}}];
const savedNotes = () => saved, P = {{ctx: {{taken: id => id === 'n3'}}, notes: {{out: n => !n.sent || !!n.edited}}}};
{fn}
const old = {{version: 'v3', at: '2026-11-21T10:00:00Z', notes: []}};
keepSaved(old); assert.deepStrictEqual(old.notes.map(n => n.id), ['n1']);  // other version and a taken one stay out
const fresh = {{version: 'v3', at: '2026-11-21T10:00:09Z', notes: []}};
keepSaved(fresh); assert.deepStrictEqual(fresh.notes, []);  // removed on the server since: gone
const has = {{version: 'v3', at: '2026-11-21T10:00:00Z', notes: [{{id: 'n1', text: 'server'}}]}};
keepSaved(has); assert.deepStrictEqual(has.notes.map(n => n.text), ['server']);
""")
    # the stored record lists at once, before the re-read; the copy's questions feed carries its notes to every tab
    add = grab(Q, "  async function addNote(", "\n  }")
    assert add.index("D.notes.push(") < add.index("await refresh()") and "at: c.created_at" in add
    assert "if (area === 'questions') return d && Array.isArray(d.notes) ? simNotes(d) : d;" in Q


def test_history_keeps_a_saved_point_note_the_read_predates(tmp_path):
    """Running 1: a stale Questions read never drops History's saved point note from Send; a newer one that lacks it does."""
    fn = grab(HIST, "  const savedC = ctx => {", "    return l; };")
    node(tmp_path, f"""
const assert = require('assert');
const store = {{'draft:hcnotes': [{{id: 'h1', anchor: 'chart:v2', text: 'pt', at: '2026-11-21T10:00:05Z'}}]}};
const ctx = {{prefs: {{get: (k, d) => k in store ? store[k] : d, set: (k, v) => {{ store[k] = v; }}}}, taken: () => false,
  data: () => new Promise(() => {{}}), refreshTop: () => {{}}}};
let QR = null, CN = [], QD = {{at: '2026-11-21T10:00:00Z', notes: []}};
const P = {{notes: {{out: n => !n.sent || !!n.edited, state: n => ({{}})}}}};
const allC = () => {{ const q = (QD && QD.notes) || []; return [...q, ...CN.filter(n => !q.some(x => x.id === n.id))].filter(n => !n.closed && /^chart:/.test(n.anchor || '')); }};
{fn}
assert.deepStrictEqual(savedC(ctx).map(n => n.id), ['h1']);  // the earlier, stale read answered: still listed
assert.deepStrictEqual(store['draft:hcnotes'].map(n => n.id), ['h1']);
QD = {{at: '2026-11-21T10:00:09Z', notes: []}};
assert.deepStrictEqual(savedC(ctx), []);  // a read after it that lacks it: removed on the server
QD = {{at: '2026-11-21T10:00:09Z', notes: [{{id: 'h2', anchor: 'chart:v1', text: 'x', closed: true}}]}};
assert.deepStrictEqual(savedC(ctx), []);  // a closed note is not sent
""")
    assert "at: r.created_at || new Date().toISOString()" in HIST


def _page(tmp_path, monkeypatch):
    monkeypatch.setattr(questions, "BOARD", str(tmp_path / "no-board"))
    page = tmp_path / "page"
    (page / "versions").mkdir(parents=True)
    (page / "versions" / "v2.html").write_text("<div class=aa>Doc</div>")
    q = {"id": "c1", "number": 1, "version": "v2", "anchor_id": "d:q1", "author": "agent:x", "status": "open", "text": "Ship?",
         "decision_request": {"prompt": "Ship?", "options": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]},
         "decision": {"verdict": "select", "text": "B", "option_id": "b", "ts": "2026-11-20T00:00:00Z"}, "flagged_for_session": True,
         "decision_history": [{"verdict": "select", "text": "A\n\nwords", "option_id": "a", "ts": "2026-11-19T00:00:00Z"},
                              {"text": "gone", "discarded": True}],
         "replies": [{"author": "agent:x", "text": "noted", "ts": "2026-11-20T05:00:00Z"}, {"author": "member", "text": "ok", "ts": "2026-11-20T06:00:00Z"}]}
    note = {"version": "v2", "author": "member", "text": "n", "created_at": "2026-11-20T01:00:00Z"}
    anchors = {"d:q1": [q], "s:p1": [{**note, "id": "n1", "anchor_id": "s:p1", "status": "resolved_in_version",
                                      "resolved_in_version": "v2", "resolution_anchor_id": "s:p2"}]}
    archived = {"s:p3": [{**note, "id": "n2", "anchor_id": "s:p3", "status": "archived"}]}
    (page / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": anchors, "archived": archived}))
    (page / "current.meta.json").write_text(json.dumps({"current": "v2", "history": []}))
    return page


def test_questions_data_for_close_move_change_and_new(tmp_path, monkeypatch):
    d = questions.build(_page(tmp_path, monkeypatch))
    assert d["at"].endswith("Z")
    n = {x["id"]: x for x in d["notes"]}
    assert n["n2"]["closed"] and not n["n1"]["closed"]  # a closed note comes, for Closed and Re-open
    assert (n["n1"]["rv"], n["n1"]["ra"], n["n1"]["at"]) == ("v2", "s:p2", "2026-11-20T01:00:00Z")
    q = d["questions"][0]
    assert q["earlier"][0] == {"v": "v2", "t": "2026-11-19", "q": "Ship?", "a": "A", "own": True}  # his earlier pick; discarded skipped
    assert len([e for e in q["earlier"] if e.get("own")]) == 1
    assert q["act"] == "2026-11-20T05:00:00Z"  # the agent's last word, not his


def test_history_answers_offer_change(tmp_path):
    page = tmp_path / "page"
    page.mkdir()
    q = {"id": "c1", "number": 1, "version": "v2", "anchor_id": "d:q1", "author": "agent:x", "status": "open",
         "decision_request": {"prompt": "Ship?"}}
    (page / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {"d:q1": [q]}, "archived": {}}))
    (page / "current.meta.json").write_text(json.dumps({"current": "v2", "history": [{"version": "v2"}]}))
    rounds = [{"id": "r1", "ts": "2026-11-19T00:00:00Z", "version": "v2", "answers": [{"comment_id": "c1", "prompt": "Ship?", "text": "A"}]},
              {"id": "r2", "ts": "2026-11-20T00:00:00Z", "version": "v2", "answers": [{"comment_id": "c1", "prompt": "Ship?", "text": "B"}]}]
    (page / "rounds.ndjson").write_text("".join(json.dumps(r) + "\n" for r in rounds))
    a = history.build(page)["answers"]
    assert [(x["a"], x["id"], x["ch"]) for x in a] == [("B", "c1", True), ("A", "c1", True)]
    li = grab(HIST, "  function li(h, ctx, ro) {", "\n  }")
    assert "your earlier pick, changed since" in li and "data-hchange" in li


def test_note_controls_and_marks_are_wired():
    """Findings 2, 7, 8, 9, 10: every new control has its handler; Close is today's archive, Re-open restore or PUT open."""
    for attr in ("spot", "spotx", "spotadd", "spotgo", "nclose", "nopen", "nreopen", "nres", "nmove", "change"):
        assert f"data-{attr}" in Q
    # fix17: the shared kit (P.notes); a resolved note's Re-open is a draft Send writes as open
    assert "api(u + (how === 'close' ? (NK.resolves(n) ? '/accept' : '/archive') : '/restore'), {})" in Q and "{status: 'open'}, 'PUT'" in Q
    assert "strategy: 'manual-repin'" in Q and "if (S.move) return moveNote(" in Q
    assert "'⋯'" not in Q and "…</button>" not in Q  # no ⋯ menu (#139)
    assert "rf-new" in Q and "rf-new" in HIST and "markSeenQ" in Q and "seeV(ctx" in HIST
    assert ".qsec.qshut > :not(h2,.qsecans){display:none}" in (WEB / "questions.css").read_text()


def test_remove_waits_for_identity_before_dropping_the_row():
    """Reference 1: Remove drops the saved row (Send's count) only after the identity read, in step with the sheet's redraw."""
    body = Q[Q.index("async function delNote"):]
    body = body[:body.index("\n  }\n")]
    assert body.index("await who()") < body.index("ctx.prefs.set('draft:qnotes'")
