"""Fix31 Send (r12 audit27): a redraw of the open sheet keeps the selection's direction, so Shift-arrows keep moving
the same end (running 1, questions 2); a warm Questions refresh on its way or failed counts as unread, so the sheet never
says Nothing ready yet over it and Send never delivers a note it did not list (questions 1)."""

import re
from pathlib import Path

from test_fix13_send import grab, node

WEB = Path(__file__).resolve().parents[2] / "src/agent_annotate/web/proto"
Q = (WEB / "questions.js").read_text()


def test_every_focus_restore_keeps_the_direction():
    assert "d: a.selectionDirection}" in Q and "d: fa.selectionDirection}" in Q
    # every caret restore after a rebuild that reads a saved range passes its direction
    saved = re.findall(r"\.setSelectionRange\((\w+)\.a, \1\.b(.*?)\)", Q)
    assert saved and all(rest == f", {v}.d" for v, rest in saved)


def test_a_warm_refresh_in_flight_or_failed_is_unread(tmp_path):
    load = grab(Q, "  let reading = null;", "\n  };")
    state = grab(Q, "  const RS = {}", "  const allRead = () => !!(oin() && qIn());")  # fix33: the one read state
    node(tmp_path, f"""
const assert = require('assert');
let D = {{v: 0}}, stale = false, ctx = null, n = 0, fail = false, hang = null, redraws = 0; const S = {{}};
const sim = d => d, relist = () => {{ redraws++; }};
const c = {{data: () => fail ? Promise.reject(Error('503')) : new Promise(r => {{ hang = r; }})}};
{load}
{state}
RS.reference = RS.links = {{st: 'done'}};
(async () => {{
  assert.ok(allRead(), 'first read in');
  stale = true; assert.ok(!allRead(), 'a note saved since the read');
  const p = load(c); assert.ok(!allRead(), 'refresh on its way'); assert.ok(redraws >= 1, 'the open sheet hears it start');
  hang({{v: 1}}); await p; assert.ok(allRead(), 'refresh in');
  stale = true; fail = true;
  await load(c).catch(() => {{}});
  assert.ok(qerr() && !allRead(), 'a failed refresh, from a count, is the sheet\\'s failure');
  const before = n; await load(c); assert.strictEqual(n, before, 'a count never re-reads a failed read');
  fail = false; const q = load(c, true); hang({{v: 2}}); await q;
  assert.ok(allRead() && D.v === 2, 'Try again reads and clears it');
}})().catch(e => {{ console.error(e); process.exit(1); }});
""")


def test_send_and_the_round_wait_on_every_read():
    assert "const ok = sendOn(n)," in Q and "const sendOn = n => !!n && settled();" in Q  # fix32: one gate; fix33: a write on its way too
    s = grab(Q, "  function send() {", "\n  }")
    assert "if (!sendOn(sendCount() || 1))" in s  # fix33: the one gate
    p = grab(Q, "  async function post(", "api/rounds/submit")
    assert p.index("await ctx.takeNow()") < p.index("if (!settled()")
    r = grab(Q, "  async function relist() {", "\n  }")
    assert "if (stale && !reading && !qerr() && ctx) return readFor(ctx);" in r  # never loops on a failing read
    assert "if (qerr() && !again) throw Error(" in grab(Q, "  const load = async", "\n  };")  # a cold failed read: counts wait for Try again, never re-read
