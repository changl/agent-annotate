"""Fix17 notes (r12 audit15): one note lifecycle for Questions and Reference (P.notes); a resolved note's Re-open is its own
Send row with Remove and Undo; View resolution in an earlier version lands on its spot; a carried note's Undo leaves no row;
a picture pin lists its notes; History's version reader has no Change; Reference markers list and closed plan notes stay."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from agent_annotate.proto_data import reference

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
Q = (WEB / "questions.js").read_text()
HIST = (WEB / "history.js").read_text()
REF = (WEB / "reference.js").read_text()


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


KIT = grab(Q, "  const stOf = ", "\n  };")
STUBS = """const assert = require('assert'); const P = {}; global.document = {getElementById: () => null};
const esc = s => String(s), ic = k => '', cut = (s, n) => s, pl = (n, a, b) => n + ' ' + (n === 1 ? a : b);
const mk = n => `[${n}]`, ibw = (k, label, t, attrs) => `<button ${attrs}>${label}</button>`;
const store = {}, calls = [], toasts = [];
const c = {prefs: {get: (k, d) => k in store ? JSON.parse(JSON.stringify(store[k])) : d, set: (k, v) => { store[k] = v; }},
  toast: (m, o) => toasts.push([m, o]), go: (t, a) => calls.push(['go', t, a])};
const api = async (u, body, m) => { calls.push([u, body, m]); return {}; };
"""


def test_reopen_is_its_own_send_row_with_remove_and_undo(tmp_path):
    """Questions 2, Reference 3: Re-open on a resolved note is a draft (no store write; the agent alone marks it resolved),
    listed as re-opened until Remove; Undo puts it back; Close and a closed note's Re-open are today's archive and restore."""
    node(tmp_path, STUBS + KIT + """
(async () => {
  const n = {id: 'n1', sent: true, st: 'resolved_in_version', rv: 'v2', ra: 's:p2', text: 'x'};
  assert(NK.resolved(n) && !NK.isReo(c, n) && /data-nreopen/.test(NK.acts(c, n)) && /data-nres/.test(NK.view(n)));
  const undo = await NK.set(c, n, 'reopen', api, async () => {});
  assert(NK.isReo(c, n) && /re-opened · goes with Send/.test(NK.words(c, n)) && !/data-nreopen/.test(NK.acts(c, n)));
  assert(/Re-opened/.test(NK.row(n, 2, 'On “a”')));
  // the store says open at once, as today's Re-open (r12 audit20 frame 4); no Undo: only the agent may resolve it again
  assert.deepStrictEqual(calls.at(-1), ['api/comments/n1', {status: 'open'}, 'PUT']);
  assert(n.st === 'open' && (await undo()) === null && NK.isReo(c, n));
  await NK.set(c, n, 'close', api, async () => {});
  assert(n.closed && calls.at(-1)[0] === 'api/comments/n1/archive' && !NK.isReo(c, n));  // now open, its Close is today's Archive
  const r = {id: 'n2', sent: true, st: 'resolved_in_version', text: 'y'};
  await NK.set(c, r, 'close', api, async () => {});
  assert(r.closed && calls.at(-1)[0] === 'api/comments/n2/accept');  // a resolved note's Close is today's Resolve (r12 fix22)
  await NK.set(c, n, 'restore', api, async () => {});
  // a sent note's Re-open is today's restore, then stored open with his words (r12 audit43 reference 1)
  assert(!n.closed && calls.at(-2)[0] === 'api/comments/n1/restore' && calls.at(-1)[0] === 'api/comments/n1' && calls.at(-1)[2] === 'PUT');
  NK.goRes(c, n); assert.deepStrictEqual(calls.at(-1), ['go', 'history', 'v2~s:p2']);
})().catch(e => { console.error(e); process.exit(1); });
""")
    # Send writes each re-opened note back to open before the round goes, then clears the drafts
    post = grab(Q, "  async function post(", "\n  }")
    assert post.index("{status: 'open'}, 'PUT'") < post.index("api/rounds/submit") < post.index("ctx.prefs.set('draft:reopen', {})")
    items = grab(Q, "  function sendItems() {", "\n  }")
    assert "'reopen:'" not in items and "isRo" not in Q  # the kit lists re-opens (test_fix18_notes)


def test_reference_uses_the_shared_kit_and_lists_its_reopened_notes():
    """Reference 2, 3: the marker list, note words and actions, Close/Re-open and Move are P.notes, not a copy."""
    for call in ("NK().spot(", "K.sentBody(ctx, n,", "K.closedActs(n)", "NK().set(ctx, n, how", "NK().move(ctx,"):
        assert call in REF, call
    for attr in ("data-spot=", "data-pin=", "spotadd", "spotgo", "nclose", "nopen", "nreopen", "nres", "nmove"):
        assert attr in REF, attr
    assert "key: 'reo:'" not in REF and "P.noteHooks" in REF
    assert "<button class=\"rf-pin${" in REF and "data-spot=" in REF  # the marker is a control, not a span
    # a plan note's resolution opens its plan revision at that line, outlined by the shared lit()
    assert "S.res = n.ra" in REF and "lit(rs)" in REF


def test_reference_notes_keep_closed_ones_and_their_resolution(tmp_path):
    """Reference 3: today's Close moves a note into "archived"; it stays at its line, closed, and a resolved one names its spot."""
    page = tmp_path / "page"
    page.mkdir()
    a = "ref:plan~v3~7"
    base = {"anchor_id": a, "version": "v3", "author": "member", "created_at": "2026-11-21T10:00:00Z", "flagged_for_session": True}
    store = {"schema_version": 2,
             "anchors": {a: [{**base, "id": "r1", "text": "r", "status": "resolved_in_version", "resolved_in_version": "v3",
                              "resolution_anchor_id": "ref:plan~v3~8"}]},
             "archived": {a: [{**base, "id": "c1", "text": "c", "status": "archived"}], "s:other": [{**base, "id": "x", "anchor_id": "s:other"}]}}
    (page / "comments.json").write_text(json.dumps(store))
    n = {x["id"]: x for x in reference.notes(page)}
    assert set(n) == {"r1", "c1"}
    assert n["c1"]["closed"] and not n["r1"]["closed"]
    assert (n["r1"]["rv"], n["r1"]["ra"], n["r1"]["st"]) == ("v3", "ref:plan~v3~8", "resolved_in_version")


def test_resolution_in_an_earlier_version_lands_on_its_spot():
    """Questions 3: History reads "<version>~<anchor>" (an anchor may hold ~), opens that version and outlines the spot."""
    ov = grab(HIST, "  function openView(", "\n  }")
    assert "at = anchor.slice(v.length + 1)" in ov and ", at," in ov
    fit = grab(HIST, "  function fit(", "\n  }")
    assert "P.notes.lit(spot)" in fit and "window.scrollTo(" in fit
    assert "Date.now() < end ? go() : ro.disconnect()" in fit and "ro.observe(view)" in fit  # stays in view while the page grows
    assert "NK.goRes(ctx, n)" in Q


def test_carried_note_undo_leaves_no_row():
    """Questions 4: Undo of Send it again drops the copy's saved record and its row before deleting it, so no read puts it back."""
    body = grab(Q, "  async function carried(", "\n  }")
    assert body.index("savedNotes().filter(x => x.id !== cid)") < body.index("'DELETE'")
    assert "D.notes = D.notes.filter(x => x.id !== cid)" in body


def test_picture_pin_lists_its_notes():
    """Questions 6: a numbered pin is a button; in the viewer it lists the notes at its point with + Comment at that point."""
    assert '<button class="qpin${NK.sent([n]) ? \' sent\' : \'\'}" data-pin=' in Q
    assert "if (ds.pin) {" in Q and "data-spotpin" in Q and "NK.near(" in Q
    zv = grab(Q, "  function zoomView() {", "\n  }")
    assert "S.spot && S.pin ? spotBox(S.spot)" in zv and "pinB(n, no, n.target.offset)" in zv
    assert "button.qpin{pointer-events:auto" in (WEB / "questions.css").read_text()


def test_links_notes_use_the_shared_kit():
    """Pages & links: sent notes take the kit's words, View resolution and actions; a re-opened one is its own Send row."""
    L = (WEB / "links.js").read_text()
    assert "K.sentBody(ctx, n, S.move === n.id," in L
    assert "P.notes.set(ctx, n, b.dataset.nclose ? 'close'" in L and "P.notes.goRes(ctx, n)" in L and "P.notes.move(" in L
    assert "lreo:" not in L and "P.noteHooks" in L


def test_version_reader_has_no_change(tmp_path):
    """Running 1: the read-only version reader lists the answers without Change; History's main list keeps it."""
    li = grab(HIST, "  function li(h, ctx, ro) {", "\n  }")
    node(tmp_path, "const assert = require('assert'); const ctx = {esc: s => String(s)};\n"
         "const h = {id: 'c1', n: 3, q: 'Ship?', a: 'B', ch: true, v: 'v2'}, old = {...h, a: 'A'}; const D = {answers: [h, old]};\n"
         + li + "\nassert(/data-hchange/.test(li(h, ctx)) && !/data-hchange/.test(li(h, ctx, true)));\n"
         "assert(/your earlier pick/.test(li(old, ctx, true)));\n")
    assert "li(h, ctx, true)" in grab(HIST, "  function openView(", "\n  }")
