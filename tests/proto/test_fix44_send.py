"""r12 audit37 frame 1-3, the class: every way a stored card reply or pending answer can be undelivered is its own Send row."""
import json

from agent_annotate.proto_data import questions as qd
from test_fix13_send import Q, grab, node

T0, T1, T2 = "2026-11-20T00:00:00Z", "2026-11-21T00:00:00Z", "2026-11-22T00:00:00Z"
LONG1, LONG2 = "First long reply " + "a" * 150, "Second reply with its own words " + "b" * 150


def _q(cid, n, **extra):
    return {"id": cid, "number": n, "version": "v2", "anchor_id": f"d:q{n}", "author": "agent:x", "status": "open", "text": f"Q{n}?",
            "decision_request": {"prompt": f"Q{n}?", "context": "", "options": [{"id": "a", "label": "A"}]}, **extra}


def _r(text, ts=T1, sent=None, author="member"):
    return {"author": author, "text": text, "ts": ts, "sent_at": sent}


def _page(tmp_path, monkeypatch):
    monkeypatch.setattr(qd, "BOARD", str(tmp_path / "no-board"))
    page = tmp_path / "page"
    (page / "versions").mkdir(parents=True)
    (page / "versions" / "v2.html").write_text("<div>Doc</div>")
    sent = {"verdict": "select", "option_id": "a", "text": "A", "ts": T0, "by": "member"}
    pend = {"verdict": "select", "option_id": "a", "text": "A", "ts": T2, "by": "member", "round_pending": True}
    anchors = {
        "d:q1": [_q("c1", 1, replies=[_r("✓ plain words")])],  # open, any opening characters
        "d:q2": [_q("c2", 2, decision=sent, flagged_at=T0, replies=[_r("☑ Selected: A", T0, T0), _r("after the answer")])],  # answered
        "d:q4": [_q("c4", 4, answer_later={"ts": T0, "by": "member"}, replies=[_r("set aside reply")])],  # set aside
        "d:q5": [_q("c5", 5, replies=[_r(LONG1), _r(LONG2, T2), _r("agent says", T2, None, "agent:x")])],  # several per card
        # mixed with a decision: its own generated line (same ts and author) is no reply; his typed lines are, whatever they open with
        "d:q6": [_q("c6", 6, decision=pend, replies=[_r("☑ Selected: A", T2), _r("☑ Selected: my own words", T1), _r("↺ my words", T2)])],
        "d:q8": [_q("c8", 8, decision=pend, answer_later={"ts": T0, "by": "member"})],  # set aside, answer pending
    }
    archived = {
        "d:q3": [_q("c3", 3, status="archived", archived_by="member", replies=[_r("reply on a closed card")])],  # archived
        "d:q7": [_q("c7", 7, status="archived", archived_by="member", decision=pend, replies=[_r("☑ Selected: A", T2)])],  # archived, answer pending
    }
    (page / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": anchors, "archived": archived}))
    (page / "current.meta.json").write_text(json.dumps({"current": "v2", "history": []}))
    return page


def test_every_undelivered_reply_and_answer_is_its_own_row(tmp_path, monkeypatch):
    qs = qd.build(_page(tmp_path, monkeypatch))["questions"]
    assert [q["n"] for q in qs] == [1, 2, 3, 4, 5, 6, 7, 8]
    items = grab(Q, "function sendItems() {", "\n    return it;\n  }")
    pend = grab(Q, "const pendA = ", "in words: “${esc(cut(String(pd.text || ''), 120))}”`; };")
    js = """
const esc = s => String(s), cut = (s, n) => String(s).slice(0, n), optLabel = (q, id) => (q.options.find(o => o.id === id) || {}).label;
const drafts = {c3: {close: true}}, draft = id => drafts[id] || {}, isDraft = q => false;
const isClosing = q => !q.closed && !!draft(q.id).close, hasReply = q => false, abPicks = () => ({}), Q = () => [], notesNow = () => [];
const typingNote = () => null, mk = s => s, NK = {}, P = {};
const D = {questions: %s, notes: []};
""" % json.dumps(qs) + pend + "\n" + items + r"""
const rows = sendItems(), keys = rows.map(r => r[2]), html = rows.map(r => r[1]);
const want = ['qr0:c1', 'qr1:c2', 'qr0:c3', 'c:c3', 'qr0:c4', 'qr0:c5', 'qr1:c5', 'qp:c6', 'qr1:c6', 'qr2:c6', 'qp:c7', 'qp:c8'];
if (JSON.stringify(keys) !== JSON.stringify(want)) throw new Error('rows ' + JSON.stringify(keys));
const has = (k, w) => { const h = html[keys.indexOf(k)]; if (!h.includes(w)) throw new Error(k + ' lacks ' + w + ': ' + h); };
has('qr0:c1', '✓ plain words'); has('qr0:c3', 'reply on a closed card'); has('qr0:c4', 'set aside reply');
has('qr0:c5', 'First long reply'); has('qr1:c5', 'Second reply with its own words');
if (html[keys.indexOf('qr0:c5')].includes('Second')) throw new Error('two replies merged');
has('qr1:c6', '☑ Selected: my own words'); has('qr2:c6', '↺ my words');
"""
    node(tmp_path, js)
    # the card's thread hides only the decision's own line, by the store, never by words
    assert "q.replies.filter(r => !r.dec)" in Q and "SYS" not in Q
    # the round: a closed card with pending rows opens before the submit and closes after it; a Close archives only after
    # the round is in, so the server's round (which skips archived cards) carries the card's reply and answer
    post = grab(Q, "async function post(", "\n  // Discard all")
    sub, fail = post.index("api/rounds/submit"), post.index("} catch (e) {")
    assert post.index("/restore`") < sub < post.index("for (const q of new Set([...closes, ...shut2])) if (!q.closed)") < fail
    assert "/archive`" not in post[:sub]
    assert "for (const q of shut2) if (!q.closed)" in post[fail:]  # a failed round leaves the card closed as it was
    assert "if (listed.keys.has(`qr${j}:${q.id}`)) r.sent = true" in post  # each delivered reply by its own row
    # Go to it on a pending row opens its card
    assert "if (at) k = 'q:' + k.slice(k.indexOf(':') + 1);" in Q
    # the groups and counts read the same pending list: a pending answer is answered, any pending row is To send (questions 5)
    assert "|| isClosing(q) || !!pendA(q);" in Q and "hasReply(q) || pending(q)" in Q


def test_one_note_is_one_row_in_every_sheet(tmp_path):
    # History's stored edit (hcn:) and its open Edit (ty:edit:) on the same note: the open Edit's row alone (r12 audit37 running 2)
    items = grab(Q, "function sendItems() {", "\n    return it;\n  }")
    js = """
const esc = s => String(s), cut = (s, n) => String(s).slice(0, n), draft = () => ({}), abPicks = () => ({}), notesNow = () => [];
const typingNote = () => null, mk = s => s, NK = {}, P = {inflight: () => false}, D = {questions: [], notes: []};
const pendA = () => null, pendR = () => [], isClosing = () => false, hasReply = () => false;
const rows = [{key: 'hcn:n1', group: 'Notes', note: 'n1', html: 'stored', remove: null},
  {key: 'ty:edit:n1', group: 'Notes', html: 'Edited', save: () => {}, remove: () => {}},
  {key: 'hcn:n2', group: 'Notes', note: 'n2', html: 'other'}];
const Q = () => rows;
""" + items + r"""
const keys = sendItems().map(r => r[2]);
if (JSON.stringify(keys) !== JSON.stringify(['x:ty:edit:n1', 'x:hcn:n2'])) throw new Error('rows ' + JSON.stringify(keys));
"""
    node(tmp_path, js)
    # Questions' own note rows leave out a note an open Edit's row stands for, as they do another tab's note row
    assert "const myNotes = q => { const own = owned(q);" in Q and "const own = owned(q);\n    if (!D) return" in Q


def test_waiting_leaves_out_his_pending_answer(tmp_path, monkeypatch):
    page = _page(tmp_path, monkeypatch)
    # open and unanswered: c1 and c5 (replies alone do not answer); c6 and c8 have his answer pending; c4, c8 set aside; c3, c7 closed
    assert qd.waiting(page) == 2


def test_failed_close_undo_takes_the_close(tmp_path):
    re_ = grab(Q, "async function reopen(q) {", "\n  function undo(q)")
    assert "if (shut) setDraft(q.id, {close: null});" in re_ and "if (shut) setDraft(q.id, {close: true});" in re_


def test_same_words_twice_in_a_line_are_two_spots(tmp_path):
    # every reader's text-range target carries where the words start (2.32.8's selected_quote alone could not tell them apart)
    from test_fix43_send import LINKS
    from test_fix13_send import REF
    assert "quote: sel.slice(0, 300), at: NK.textAt(anchorEl)}" in Q and "quote: q.slice(0, 300), at: NK().textAt(b)}" in REF
    assert "quote: q.slice(0, 300), at: P.notes.textAt(ln)}" in LINKS
    made, mq = grab(Q, "const made = b => ", ";"), grab(Q, "    mark(el, quote, at) {", "\n      r.surroundContents(document.createElement('mark')); },")
    node(tmp_path, made + r"""
const a = made({anchor_id: 'p', text: 'same', target: {quote: 'a', at: 26}}), b = made({anchor_id: 'p', text: 'same', target: {quote: 'a', at: 40}});
if (a === b) throw new Error('two occurrences are two spots');
const nodes = [{nodeValue: 'with a picture'}, {nodeValue: ' and a line'}];
let got;
global.document = {createRange: () => ({setStart: (n, i) => { got = [n, i]; }, setEnd() {}, surroundContents() {}}), createElement: () => ({})};
const NK = {texts: () => nodes, """ + mq + r"""};
NK.mark({}, 'a', 19); if (got[0] !== nodes[1] || got[1] !== 5) throw new Error('second occurrence: ' + JSON.stringify(got));
NK.mark({}, 'a', 5); if (got[0] !== nodes[0] || got[1] !== 5) throw new Error('first occurrence');
NK.mark({}, 'a'); if (got[0] !== nodes[0]) throw new Error('an older note without at: the first');
""")
    assert "NK.mark(el, t.quote, t.at)" in Q
    # held round (r12 audit37 reference 1): the typed note's row in Reference and Pages & links (a folder file or a kept
    # document, one selection path) carries the selection's target, `at` with it, so the round's made-set refuses only the
    # same occurrence and a note on the second one, saved while the round is out, posts
    assert "key: 'rnn:' + tr.a, tgt: tr.tgt || undefined" in REF and "tgt: S.tgt, text: e.target.value" in LINKS
    assert "ln.closest('[data-doc]').dataset.doc + '~' + ln.dataset.line" in LINKS
    assert "mark({anchor_id: x.spot || nn[m[1]](m[2]), text: x.say, target: x.tgt})" in Q
    assert "CARRY.made.has(made(body))" in Q
    node(tmp_path, made + r"""
const going = new Set([made({anchor_id: 'doc:f.md~3', text: 'n', target: {schema: 1, tag: 'p', quote: 'same', at: 7}})]);
if (!going.has(made({anchor_id: 'doc:f.md~3', text: 'n', target: {schema: 1, tag: 'p', quote: 'same', at: 7}}))) throw new Error('the same spot');
if (going.has(made({anchor_id: 'doc:f.md~3', text: 'n', target: {schema: 1, tag: 'p', quote: 'same', at: 49}}))) throw new Error('second occurrence refused');
""")


def test_move_label_follows_the_current_anchor(tmp_path):
    """r12 audit37 reference 2: a Move, its Undo and a failed round after: Send's row names the note's new line in Pages & links."""
    from test_fix43_send import LINKS
    from test_fix13_send import REF
    fn = grab(LINKS, "  function repin(c, l, id, v) {", "\n  }") + "\n" + grab(LINKS, "  const MOVED = {}", "return n; };")
    node(tmp_path, r"""
const store = {'draft:lnotes': [{id: 'n1', a: 'doc:f.md~3', l: 'f.md', line: 'Paragraph after 2.'}]};
const c = {prefs: {get: (k, d) => k in store ? store[k] : d, set: (k, v) => { store[k] = v; }}};
const drawn = {id: 'n1', a: 'doc:f.md~3', line: 'Paragraph after 2.'}, mine = [];
let LD = {notes: [{id: 'n1', a: 'doc:f.md~3', line: 'Paragraph after 2.'}]};  // a fresher read than the drawn view's: Send's
""" + fn + r"""
repin(c, [drawn, ...mine], 'n1', {a: 'doc:f.md~5', l: 'f.md', target: undefined, line: ''});
for (const x of [drawn, LD.notes[0], store['draft:lnotes'][0]]) if (x.a !== 'doc:f.md~5' || x.line !== '') throw new Error('stale ' + JSON.stringify(x));
repin(c, [drawn], 'n1', {a: 'doc:f.md~3', l: 'f.md', target: null, line: ''});  // Undo puts it back, on every copy too
if (LD.notes[0].a !== 'doc:f.md~3' || store['draft:lnotes'][0].a !== 'doc:f.md~3') throw new Error('undo');
// a read begun before the Move's write lands after it with the old anchor: the visit's Move is laid over it (r12 audit38 frame 2)
repin(c, [drawn], 'n1', {a: 'doc:f.md~5', l: 'f.md', target: undefined, line: ''});
LD = {notes: [{id: 'n1', a: 'doc:f.md~3', line: 'Paragraph after 2.'}]};
const late = moved(LD.notes[0]); if (late.a !== 'doc:f.md~5' || late.line !== '') throw new Error('late read ' + JSON.stringify(late));
""")
    assert "].map(moved).filter(n => P.notes.out(n)" in LINKS and "CUR = D; D.notes.forEach(moved);" in LINKS
    # the row's line is read from its anchor when the line is cleared; Move and its Undo go through the same apply
    assert "repin(ctx, [n, ...D.notes, ...mine], n.id, {a: p.anchor_id, l: p.anchor_label, target: p.target, line: ''})" in LINKS
    assert "if (n.line || !LD) return n.line || '';" in LINKS and "undo: () => put(from, false)" in Q
    # Reference and History keep one copy per feed and set the label from the new anchor's own
    assert "Object.assign(n, {a: p.anchor_id, l: p.anchor_label, target: p.target})" in REF
