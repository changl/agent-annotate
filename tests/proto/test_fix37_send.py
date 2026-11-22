"""Fix37 Send (r12 audit32 running 1-6, questions 1-6): every Send row gives the round check its full words; a new note
changed while the round is out becomes an open Edit of the posted note on every editor; the receipt is never replaced;
a refused Remove is caught; a lone Close is a stored round; a failed re-read after a saved round is no Send failure."""

import re
from pathlib import Path

from test_fix13_send import grab, node

WEB = Path(__file__).resolve().parents[2] / "src/agent_annotate/web/proto"
Q = (WEB / "questions.js").read_text()
FRAME = (WEB / "frame.js").read_text()
TABS = {f: (WEB / f).read_text() for f in ["questions.js", "links.js", "history.js", "reference.js", "running.js"]}
SHORT = re.compile(r"\bcutq?\(|\.slice\(0, 139\)|NK\.row\(")


def test_every_tabs_row_has_a_full_words_signature():
    """Running 1, questions 1: a row whose listing is shortened carries its full words in say, which ctx.sig compares."""
    assert "sig: x => x.say || x.html," in FRAME
    rows = 0
    for f, src in TABS.items():
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if not (("key: '" in line and "group: '" in line) or "it.push(out(" in line):
                continue
            rows += 1
            seg = line if "it.push(out(" in line else line + "\n" + (lines[i + 1] if i + 1 < len(lines) else "")
            nxt = seg.find("{key: '", seg.find("{key: '") + 1)
            if nxt > 0:
                seg = seg[:nxt]
            if SHORT.search(seg):
                assert "say:" in seg, f"{f}:{i + 1} lists shortened words with no full-words say: {line.strip()[:120]}"
    assert rows >= 14, rows
    # Questions' own rows: their full words are read when Send is pressed, never when the countdown ends
    send = grab(Q, "  function send() {", "\n  }")
    assert "sig = fullSig()" in send and "sig: fullSig()" not in Q


def test_a_late_new_note_becomes_an_open_edit_on_every_editor(tmp_path):
    """Running 2, questions 2: the kit's late() turns the newer words into the posted note's open Edit, a row for the next Send."""
    late = grab(Q, "    late(id, was, text, rec, open) {", "\n    },")
    tyrows = grab(Q, "  P.tyRows = c => ", "}; });")
    node(tmp_path, """
const assert = require('assert');
let opened = 0; const esc = s => s, cut = s => s, TABN = {};
const document = {activeElement: null, querySelector: () => null};
const NK = {m: {}, ty() { return this.m; }, tySet(k, r) { if (r) this.m[k] = r; else delete this.m[k]; }, hooks: {}, eds: new Map(), th: new Map()};
const P = {};
NK.""" + late.strip().replace("late(id", "late = function (id", 1).rstrip(",") + """;
""" + tyrows + """
NK.late('n1', 'first words', 'first words, new ending', {a: 'doc:x~1', tab: 'links', on: 'A line'}, () => { opened++; });
assert.strictEqual(opened, 1);
const rows = P.tyRows({});
assert.strictEqual(rows.length, 1); assert.strictEqual(rows[0].key, 'ty:edit:n1'); assert.strictEqual(rows[0].say, 'Edited: first words, new ending');
""")
    for f in ["links.js", "history.js", "reference.js"]:
        assert ".late(r.id, " in TABS[f], f
    # Questions: the newer words stay as an open Edit of the posted note (listed by openEd), never a PUT marked sent
    assert "const keep = {...e, edit: tnLate}; S.note = keep;" in Q and "{text: e.text.trim()}, 'PUT'" not in Q
    assert "(NK.out(x) || openEd(x))" in Q


def test_the_receipt_is_never_replaced_by_an_undo_toast(tmp_path):
    """Running 3, questions 6: a toast with its own Undo waits until the four-second receipt has shown."""
    fn = grab(FRAME, "  let toastTimer, wroteAt = 0, heldTo = 0;", "\n  }")
    node(tmp_path, """
const assert = require('assert');
const el = {innerHTML: '', querySelector: () => null}, document = {getElementById: () => el};
const S = {}, COPY = false, esc = s => s, P = {inertMark: () => ''};
let later = [], now = 1000; Date.now = () => now;
const setTimeout = (f, ms) => { later.push([f, ms]); return later.length; }, clearTimeout = () => {};
""" + fn + """
toast('Sent 1 item', {inert: true, hold: 4000});
toast('Note saved · goes with Send', {undo: () => {}});
assert.ok(/Sent 1 item/.test(el.innerHTML), el.innerHTML);
const w = later.find(([, ms]) => ms > 3000 && ms <= 4000); assert.ok(w, JSON.stringify(later.map(x => x[1])));
now += 4000; w[0](); assert.ok(/Note saved/.test(el.innerHTML) && /data-undo/.test(el.innerHTML), el.innerHTML);
""")


def test_a_refused_remove_is_caught_everywhere():
    """Running 5: the refusal past the round check is marked, and every Remove caller catches it."""
    assert "{carried: true}" in FRAME and "P.carried = e => !!(e && e.carried);" in FRAME
    assert Q.count("P.carried(e)") >= 2
    for f in ["links.js", "history.js", "reference.js"]:
        assert "P.carried(e)" in TABS[f], f
    tc = grab(TABS["history.js"], "  async function takeC(ctx, n) {", "\n  }")
    assert tc.index("ctx.take(") < tc.index("ctx.prefs.set('draft:hcnotes'"), "refused before anything is hidden"


def test_close_alone_refresh_failure_focus_and_revision():
    """Questions 3, 4; running 4, 6."""
    post = grab(Q, "  async function post(", "\n  // Discard all")
    assert "note = [fb, ...shut, ...says]" in post
    assert "try { await refresh(); } catch (x) { console.warn('refresh after Send', x); }" in post
    assert "HELD = typingIn(); host.remove();" in Q and "k = typingIn() || HELD; HELD = null;" in Q
    assert "if (!S.reach) S.reach = r.a;" in TABS["reference.js"]
