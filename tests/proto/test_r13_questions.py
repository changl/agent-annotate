"""Round 13 questions fix: each approved decision as the mock has it. 03 a sent card reads "Sent 09:03 · read by the agent";
06 a task in the agent's text is a title link, then bead id and state; 08 note actions are icons alone; 09 an open Cards only
card keeps its line, impact mark before the state; 14 a Close leaves Waiting at once."""

from test_fix17_notes import KIT, Q, STUBS, grab, node

BASE = "const esc = s => String(s), ic = k => '', cut = (s, n) => s.length > n ? s.slice(0, n) + '…' : s;\n"


def test_03_sent_line_is_short_with_read_state(tmp_path):
    js = grab(Q, "  const sentAt = ", "; };") + "\n" + grab(Q, "  function stateOf(q) {", "\n  }\n")
    node(tmp_path, "const assert = require('assert');\n" + BASE + """
const draft = () => ({}), isClosing = () => false, pendA = () => null, pendW = () => '', optLabel = () => 'Yes, ship it';
""" + js + """
const now = new Date(); now.setHours(9, 3, 0, 0);
const q = {id: 'q1', sent: true, read: true, decision: {option_id: 'a', ts: now.toISOString()}};
let h = stateOf(q);
assert(/>Sent 09:03 · read by the agent<\\/span>/.test(h), h);
assert(/title="Your answer: Yes, ship it"/.test(h) && !/>[^<]*Yes, ship it/.test(h), 'the answer is in the title, not the line');
assert(/data-change="q1"/.test(h), 'Change stays (catalog 52)');
h = stateOf({...q, read: false, decision: {option_id: 'a', ts: '2026-11-20T15:00:00'}});
assert(/>Sent Nov 20 15:00 · not read yet</.test(h), h);
""")


def test_06_task_in_text_is_a_title_link(tmp_path):
    node(tmp_path, "const assert = require('assert');\n" + BASE + """
const D = {beads: {'FLD-dkkz.11': {title: 'Primary email replacement', status: 'in_progress', state: 'progress'}}};
""" + grab(Q, "  const beadText = ", ": m; });") + """
const h = beadText('see FLD-dkkz.11 and FLD-none.1');
assert(/<button class="lk bdl" data-task="FLD-dkkz.11"[^>]*>Primary email replacement<\\/button> <span class="bid">FLD-dkkz.11<\\/span><span class="small mut"> · in progress<\\/span>/.test(h), h);
assert(!/qtask|dot/.test(h), 'no pill, no dot');
assert(/FLD-none\\.1$/.test(h), 'an id not on the board stays as text');
""")


def test_08_note_actions_are_icons_alone(tmp_path):
    acts = grab(Q, "    acts: (c, n, moving, before, del = 'nundo') =>", "\n    life:")
    assert "ibw(" not in acts, "no words beside note actions (#103)"
    box = grab(Q, "  function noteBox(n, no, dlg) {", "\n  }\n")
    assert "ibw(" not in box
    # card actions keep their words on the desk (#139)
    assert "ibw('later', 'Later'" in Q and "ibw('archive', 'Close'" in Q
    node(tmp_path, STUBS.replace("const P = {};", "const P = {ctx: null};") + KIT + """
const n = {id: 'n', by: true, own: true, text: 'x'};
const h = NK.acts(c, n, false);
assert(/data-nedit="n"/.test(h) && /data-nmove="n"/.test(h) && /data-nclose="n"/.test(h), 'every ability stays: ' + h);
""")


def test_09_open_cards_only_card_keeps_its_line():
    card = grab(Q, "  function card(q, inList) {", "\n  }\n")
    line = grab(card, "const line = () =>", "</div>`; };")
    assert line.index("${marks}") < line.index('<span class="qright">'), "the impact mark sits before the state or quick answer"
    assert 'aria-expanded="${open}"' in line
    assert "const head = lined ? line() :" in card, "open or folded, Cards only shows the same line"
    assert '${lined ? `<div class="qlacts"><span class="eacts">${acts}</span></div>` : \'\'}' in card, "its actions on their own row"


def test_14_close_leaves_waiting_at_once(tmp_path):
    node(tmp_path, "const assert = require('assert');\n" + """
let closing = false; const isDraft = () => false, isClosing = () => closing, hasReply = () => false, pending = () => false;
""" + grab(Q, "  const FILTERS = {", "q.closed || isClosing(q)};") + """
const q = {id: 'q'};
assert(FILTERS.need(q) && !FILTERS.arch(q));
closing = true;
assert(!FILTERS.need(q), 'out of Waiting');
assert(FILTERS.arch(q) && FILTERS.ready(q), 'in Closed and To send');
""")
