"""Fix23 actions: every note offers today's actions (shell.js cardMenuItems, canEditComment, canDeleteComment, showReply),
from the kit's one list, with Resolve and Archive as one Close (#138). Each state is a stored record, read through the
feed (note_thread, and own() for this reader) into the kit, and compared with today's rules on the same record."""

import json

from agent_annotate.proto_data.questions import _mine, note_thread, own, was_sent
from test_fix17_notes import KIT, Q, STUBS, node


def test_a_superseded_draw_never_restores_its_old_scroll():
    # a late draw(true) waiting on its document must not scrollTo(0, y) after a newer draw: that undid his scroll and the Edit tap hit another note
    d = Q[Q.index("  async function draw(keepScroll) {"):Q.index("  function listView() {")]
    assert "gen = ++S.drawGen" in d and d.index("if (gen !== S.drawGen) return false;") < d.index("docEl.innerHTML = doc;") < d.index("if (keepScroll) scrollTo(0, y);")
    assert "draw().then(ok => ok !== false && scrollTo(0, S.vy[v] || 0))" in Q

ME = "you@example.com"
BASE = {"author": ME, "status": "open", "flagged_for_session": True, "flagged_at": "2026-11-21T10:00:00Z"}
AGENT = [{"author": "agent:x", "text": "a", "ts": "2026-11-21T10:05:00Z"}]
STATES = {
    "draft": {"flagged_for_session": False, "flagged_at": None},
    "sent": {},
    "edited-sent": {"flagged_for_session": False, "edited_at": "2026-11-21T11:00:00Z", "edited_by": ME},
    "with-response": {"status": "addressed_by_agent", "response_text": "done"},
    "agent-latest-reply": {"replies": AGENT},
    "addressed": {"status": "addressed_by_agent"},
    "confirmed": {"status": "user_confirmed"},
    "resolved": {"status": "resolved_in_version", "resolved_in_version": "v2", "resolution_anchor_id": "s:b"},
    "archived": {"status": "archived"},
    "archived-draft": {"status": "archived", "flagged_for_session": False, "flagged_at": None},
    "other-reviewer": {"author": "other@example.com"},
    "agents-own": {"author": "agent:x", "flagged_for_session": False, "flagged_at": None},
}


def today(c):
    """2.32.8's menu and reply box for this record, in the prototype's words (Delete is Remove, Re-pin is Move, Restore is Re-open)."""
    mine, st, rs = c["author"] == ME, c["status"], c.get("replies") or []
    if st == "archived":
        return ["Re-open"], None, False
    acts = (["Edit"] if mine else []) + (["Remove"] if mine and not c.get("flagged_for_session") and not rs and not c.get("response_text") else [])
    review = st == "open" and rs and rs[-1]["author"].startswith("agent:")
    close = "accept" if review or st in ("user_confirmed", "resolved_in_version") else "archive"
    acts += ["Move"] + (["Re-open"] if close == "accept" else []) + ["Close"]
    reply = bool(c.get("response_text") or any(r["author"].startswith("agent:") for r in rs) or c["author"].startswith("agent:"))
    return acts, close, reply


def proto(c):
    """The note as the feed gives it to this reader (questions.build's note fields, then own())."""
    n = {"id": "n", "sent": was_sent(c) or not _mine(c["author"]), "status": c["status"], "closed": c["status"] == "archived", **note_thread(c)}
    return json.loads(own(json.dumps(n).encode(), {ME}))


def test_feed_marks_only_his_own_notes():
    assert proto({**BASE})["by"] is True
    assert proto({**BASE, "author": "other@example.com"})["by"] not in (True, None)
    n = proto({**BASE, "author": "agent:x"})
    assert n["ag"] and n["by"] is not True and n["sent"]


def test_every_state_offers_todays_actions(tmp_path):
    cases = {k: (proto({**BASE, **v}), today({**BASE, **v})) for k, v in STATES.items()}
    node(tmp_path, STUBS.replace("const P = {};", "const P = {ctx: null};") + KIT + f"""
const cases = {json.dumps(cases)};
const words = h => [...h.matchAll(/>([^<]+)<\\/button>/g)].map(m => m[1]);
(async () => {{
  for (const [k, [n, [acts, close, reply]]] of Object.entries(cases)) {{
    assert.deepStrictEqual(words(NK.acts(c, n, false)), acts, k);
    if (close) {{ await NK.set(c, {{...n}}, 'close', api, async () => {{}}, true); assert.strictEqual(calls.at(-1)[0], 'api/comments/n/' + close, k); }}
    if (!n.closed) assert.strictEqual(/data-nreply=/.test(NK.thread(c, n)), reply, k);
  }}
  // an edit of his own sent note clears its flag: Remove shows, as today's Delete; the same words still PUT (reference 11)
  const s = cases.sent[0];
  assert(!/data-nundo/.test(NK.acts(c, s)));
  assert(await NK.fix(c, s, s.text || '', api, (w, p) => Object.assign(s, p)) === false);  // empty words: refused, as before
  s.text = 'same';
  assert(await NK.fix(c, s, 'same', api, (w, p) => Object.assign(s, p)));
  assert.deepStrictEqual(calls.at(-1), ['api/comments/n', {{text: 'same'}}, 'PUT']);
  assert(s.edited && /data-nundo="n"/.test(NK.acts(c, s)) && /data-ndel="n"/.test(NK.acts(c, s, false, '', 'ndel')));
}})().catch(e => {{ console.error(e); process.exit(1); }});
""")
