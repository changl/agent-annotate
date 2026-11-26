"""Round 13 Running, Analytics and History fixes: chart keys, the week still running, History's new chip and sections, unread reads."""

import json

from test_fix14_frame import FRAME, RUN, WEB, grab, node

from agent_annotate.proto_data import history

HIST = (WEB / "history.js").read_text()


def test_iso_week_matches_the_data_and_the_running_week_is_left_off(tmp_path):
    """Row 11: the server keys weeks %G-W%V; the browser names the same week, so the unfinished one leaves the line."""
    iso = grab(RUN, "  const isoWk = t =>", "padStart(2, '0')}`; };")
    node(tmp_path, f"""
const assert = require('assert');
{iso}
assert.strictEqual(isoWk('2026-11-25T12:00:00Z'), '2026-W48');
assert.strictEqual(isoWk('2027-01-01T12:00:00Z'), '2026-W53');
assert.strictEqual(isoWk('2025-12-29T12:00:00Z'), '2026-W01');
""")
    assert "wks = oc ? oc.weeks.filter(w => w[0] !== cw)" in RUN and "This week so far" in RUN


def test_threshold_labels_sit_in_a_key_not_on_the_line():
    """Row 11: a chart's gate is named once in a key under it, never as text drawn over the bars."""
    assert 'class="cax gt"' not in RUN and "${gkey(o)}" in RUN and RUN.count("</svg>${gkey(o)}") == 2


def test_only_versions_after_his_last_look_are_new(tmp_path):
    """Row 13: History's "new" chip follows the page's seen record, not every version since this browser first opened it."""
    page = tmp_path / "page"
    page.mkdir()
    (page / "seen.json").write_text(json.dumps({"r1": {"v1": {"ts": "2026-11-01T00:00:00Z"}, "v2": {"ts": "2026-11-20T09:00:00Z"}},
                                                "r2": {"v2": {"ts": "2026-11-10T00:00:00Z"}}}))
    assert history.last_seen(page) == "2026-11-20T09:00:00Z"
    (page / "seen.json").write_text("not json")
    assert history.last_seen(page) == ""
    assert "D.lastSeen" in HIST


def test_sections_list_before_the_frame_finishes(tmp_path):
    """Row 17: "Its sections" is filled from the version's HTML once it is read, not after every picture in the frame loads."""
    assert "else secsEarly(host, body, ctx);" in HIST
    early = grab(HIST, "  function secsEarly(host, html, ctx) {", "\n  }")
    node(tmp_path, f"""
const assert = require('assert');
const secs = {{textContent: 'Loading…', innerHTML: ''}}, host = {{querySelector: () => secs}};
global.DOMParser = class {{ parseFromString() {{ return {{querySelectorAll: () => [{{textContent: ' One '}}, {{textContent: ''}}, {{textContent: 'Two <b>'}}]}}; }} }};
const ctx = {{esc: s => s.replace(/</g, '&lt;')}};
{early}
secsEarly(host, '', ctx);
assert.ok(secs.innerHTML.includes('data-sec="0">One<') && secs.innerHTML.includes('data-sec="1">Two &lt;b><'));
// fit() has already drawn the list with its jumps: never drawn over
secs.textContent = 'One'; secs.innerHTML = 'kept'; secsEarly(host, '', ctx);
assert.strictEqual(secs.innerHTML, 'kept');
""")


def test_unread_running_read_never_shows_zero_on_home():
    """Board outage: Home draws without waiting for the running read, and an unread read shows a dash and Try again, never "0 workers"."""
    home = FRAME[FRAME.index("async function drawHome"):FRAME.index("function drawOther")]
    assert "await readRun" not in home and "!S.run ? tile('—', `workers: ${noRun}`" in home and "data-homerun" in home
    assert "if (S.home) drawHome();" in grab(FRAME, "  function putRun", "\n  }")
    assert "d.homerun !== undefined" in FRAME


def test_running_says_a_slow_read_and_rereads_an_unread_board():
    """Board outage: Running says it is still reading after 5 s, and re-reads an unread board by itself, one loop at a time."""
    render = grab(RUN, "  async function render(el, ctx, anchor, tab) {", "\n  }")
    assert "data-slow hidden" in render and "clearTimeout(slow)" in render
    assert "if (tab === 'running' && D.board && (D.board.error || D.board.stale)) reread();" in render
    rr = grab(RUN, "  async function reread() {", "\n  }")
    assert "if (REREAD) return;" in rr and "finally { REREAD = false; }" in rr and "!(d.board || {}).stale" in rr
    # the frame's last good board, marked stale, says when it was read
    assert "The board as read at" in RUN and "b.stale && b.read" in RUN
