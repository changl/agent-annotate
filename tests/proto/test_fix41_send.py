"""Fix41 Send (r12 audit36 running 1): a note write that lands is not delivery. After a failed round every row the round did not
deliver stays in Send once, with the editor's words, in every reader, as a reload shows it. Send's own save of an open Edit or
Reply records it in the kit's one record (put1), as the editor's own Save and Post reply do; a reader whose feed copy of the
note is stale (Pages & links, History, Reference read once) lists it from that record."""

from pathlib import Path

from test_fix17_notes import KIT, Q, STUBS, grab, node

WEB = Path(__file__).resolve().parents[2] / "src/agent_annotate/web/proto"
SRC = {f: (WEB / f).read_text() for f in ("links.js", "history.js", "reference.js", "running.js")}
ROWS = grab(Q, "  const TABN = ", "\n  // every re-opened note")
SEND = grab(Q, "      const L0 = Object.fromEntries(", "if (ctx.queueSent) ctx.queueSent(got, listed.q);")

# every reader that lists a sent note's Edit or Reply, by its anchor
READERS = {"questions": "q1", "history chart": "chart:v3", "kept meeting": "doc:kept-admin-meeting~p~s:p1",
           "folder Markdown": "doc:notes.md~3", "Reference plan": "ref:plan-1~2", "kept document": "doc:kept-policies~p~s:p2"}


def test_a_failed_round_keeps_every_edit_and_reply_in_every_reader(tmp_path):
    node(tmp_path, STUBS + KIT + """
c.refreshTop = () => {}; c.api = async () => ({}); P.ctx = c;
""" + ROWS + f"""
const READERS = {READERS!r};
(async () => {{
  for (const [reader, a] of Object.entries(READERS)) for (const kind of ['edit', 'reply']) {{
    for (const k of Object.keys(NK.loc())) delete NK.L[k];
    const id = reader.replace(/ /g, '-') + '-' + kind, base = {{id, sent: true, st: 'open', text: 'delivered', anchor: a, a, resp: 'ok', replies: []}};
    const feed = {{...base, replies: []}};  // the reader's feed copy, read before the round: never re-read after it fails
    NK.eds.set(id, {{...base}}); NK.th.set(id, {{...base, replies: []}});  // the editor's own copy
    if (kind === 'edit') NK.tySet('edit:' + id, {{...NK.rec(base), id, text: 'his new words', was: 'delivered', sent: true}});
    else NK.typed.set(id, 'his reply');
    const row = P.tyRows(c).find(x => x.key === 'ty:' + kind + ':' + id);
    assert(row, reader + ' ' + kind + ': listed');
    await row.save();  // Send's own write lands; the round then fails: nothing marks it delivered
    assert(!P.tyRows(c).some(x => x.key === row.key), reader + ' ' + kind + ': the editor row went into the note row');
    assert(NK.out(feed), reader + ' ' + kind + ': still goes with Send from a stale feed copy');
    assert(NK.mine(feed), reader + ' ' + kind + ': his row');
    assert.strictEqual(NK.say(feed), kind === 'edit' ? 'his new words' : 'Reply: his reply', reader + ' ' + kind + ': the editor\\'s words');
    NK.gone(feed);  // a round that does go takes it
    assert(!NK.out(feed), reader + ' ' + kind + ': delivered once');
  }}
}})().catch(e => {{ console.error(e); process.exit(1); }});
""")


def test_the_rounds_own_save_is_no_change_after_the_check():
    # the kit record the save writes is the round's own: a successful round clears it, never leaves it for the next Send
    assert "if (w && w.id && w.id in NK.loc()) L0[w.id] = JSON.stringify(NK.loc()[w.id]); }" in SEND
    assert SEND.index("const L0 = ") < SEND.index("await x.save()") < SEND.index("const L1 = ")


def test_no_other_editor_draft_clears_before_the_round_is_submitted():
    # new note, task comment, General feedback, Reference note, answer and reply drafts: each clear in the round comes after its
    # own write (a saved note joins its reader's unsent list) or after the submission; a failed round re-reads and keeps them
    sub = SEND.index("api/rounds/submit")
    assert SEND.index("ctx.prefs.set('q:general', '')") > sub
    assert SEND.index("ctx.prefs.set('draft:reopen', {})") > sub
    assert "mine.push({id: r.id" in SRC["links.js"] and "mine.push({id: r.id" in SRC["reference.js"] and "CN.push({id: r.id" in SRC["history.js"]
    fail = grab(Q, "    } catch (e) {\n      S.pending = null; ROUND = null; CARRY = null; open();", "Your drafts are kept.');")
    assert "await refresh();" in fail and "NK.gone" not in fail and "tySet" not in fail
