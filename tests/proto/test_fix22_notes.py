"""Fix22 notes: the three note actions today's release has (shell.js cardMenuItems, canEditComment, showReply), in the kit:
Edit on his own sent note (in place, re-opened, goes with Send), Post reply under the agent's response, and Close storing
today's Resolve (accept) where today offers it and Archive elsewhere."""

from agent_annotate.proto_data.questions import note_thread
from test_fix17_notes import KIT, Q, STUBS, node

FIX_STUBS = STUBS.replace("const P = {};", "const P = {ctx: null};")


def test_kit_edit_reply_and_close(tmp_path):
    node(tmp_path, FIX_STUBS + KIT + """
(async () => {
  // Edit on a sent note of his own; none on another's or a closed one
  const n = {id: 'n1', sent: true, st: 'addressed_by_agent', text: 'old', mine: true};
  assert(/data-nedit="n1"/.test(NK.acts(c, n)));
  assert(!/data-nedit/.test(NK.acts(c, {...n, mine: false})));
  let got = null;
  assert(await NK.fix(c, n, 'new words', api, (w, p) => { got = p; }));
  assert.deepStrictEqual(calls.at(-1), ['api/comments/n1', {text: 'new words', status: 'open'}, 'PUT']);  // today's edit-save re-opens it
  assert(got.edited && got.status === 'open' && got.text === 'new words');
  Object.assign(n, got);
  assert(NK.out(n) && /edited · goes with Send/.test(NK.words(c, n)) && !NK.sent([n]));
  // Close: Resolve (accept) where today's menu offers it, Archive elsewhere; Restore undoes either
  for (const [st, replies, route] of [['resolved_in_version', [], 'accept'], ['user_confirmed', [], 'accept'], ['open', [{agent: true}], 'accept'],
                                      ['open', [], 'archive'], ['addressed_by_agent', [], 'archive'], ['open', [{agent: false}], 'archive']]) {
    const x = {id: 'c1', sent: true, st, replies};
    await NK.set(c, x, 'close', api, async () => {}, true);
    assert.strictEqual(calls.at(-1)[0], 'api/comments/c1/' + route, st + ' ' + JSON.stringify(replies));
    await NK.set(c, x, 'restore', api, async () => {}, true);
    assert.strictEqual(calls.at(-1)[0], 'api/comments/c1/restore');
  }
  // the thread: the agent's response, the latest reply, older ones folded, and Post reply while open
  const t = {id: 't1', sent: true, st: 'addressed_by_agent', resp: 'Done in v3', replies: [{agent: true, text: 'a'}, {agent: false, text: 'b'}, {agent: true, text: 'c'}]};
  const h = NK.thread(c, t);
  assert(/Agent response/.test(h) && /2 earlier replies/.test(h) && /data-nreply="t1"/.test(h) && /c<\\/div>/.test(h) && !/>a<\\/div>/.test(h));
  assert(!/data-nreply/.test(NK.thread(c, {...t, closed: true})));
  assert.strictEqual(NK.thread(c, {id: 'q', sent: true}), '');
  c.api = api;
  assert(await NK.reply(c, t, ' more ', () => {}));
  assert.deepStrictEqual(calls.at(-1), ['api/comments/t1/reply', {text: 'more'}, undefined]);
  assert(t.replies.at(-1).text === 'more' && t.status === 'open');
})().catch(e => { console.error(e); process.exit(1); });
""")


def test_feed_marks_an_edit_after_send():
    sent = {"author": "you@example.com", "flagged_for_session": True, "flagged_at": "2026-11-21T10:00:00Z"}
    assert note_thread({**sent, "edited_at": "2026-11-21T11:00:00Z"})["edited"]
    assert not note_thread({**sent, "edited_at": "2026-11-21T09:00:00Z"})["edited"]
    assert not note_thread({**sent, "edited_at": "2026-11-21T11:00:00Z", "edited_by": "agent:x"})["edited"]
    assert not note_thread({"author": "you@example.com", "edited_at": "2026-11-21T11:00:00Z"})["edited"]  # never sent: a draft
    t = note_thread({**sent, "response_text": "ok", "replies": [{"author": "agent:x", "text": "hi"}]})
    assert t["resp"] == "ok" and t["replies"][0]["agent"] and t["mine"]


def test_questions_uses_the_kit_edit_not_a_new_correction():
    assert "data-nfix" not in Q and "NK.fix(ctx, n, text, call," in Q and "${NK.thread(ctx, n)}" in Q
