"""Seventh check: drafts and counts across a reload or a newer version (frame 1-2, running 1, questions 1)."""

import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
Q = (WEB / "questions.js").read_text()
FRAME = (WEB / "frame.js").read_text()


def grab(start, end):
    i = Q.index(start)
    return Q[i:Q.index(end, i) + len(end)]


def node(tmp_path, js):
    exe = shutil.which("node")
    if not exe:
        pytest.skip("node not installed")
    f = tmp_path / "t.js"
    f.write_text(js)
    r = subprocess.run([exe, str(f)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr + r.stdout


def test_reload_onto_newer_version_keeps_drafts(tmp_path):
    """Frame 1, questions 1: with no old version in memory, an answer, Close or reply moves to the question re-asked under a new id."""
    set_draft = grab("  function setDraft(id, patch) {", "\n  }")
    carry = grab("  function carry(old, d) {", "\n  }")
    node(tmp_path, f"""
const assert = require('assert');
const store = {{}}; const ctx = {{prefs: {{get: (k, d) => k in store ? store[k] : d, set: (k, v) => {{ store[k] = JSON.parse(JSON.stringify(v)); }}}}}};
const drafts = () => ctx.prefs.get('q:drafts', {{}});
let D = {{questions: [{{id: 'old1', prompt: 'Build it?'}}, {{id: 'old3', prompt: 'Gone?'}}]}};
const SIM = {{old2: {{later: false, p: 'Close it?'}}, note9: {{closed: true}}}}; let saved = 0; const simSave = () => saved++;
const optLabel = (q, k) => 'choice ' + k;
{set_draft}
{carry}
setDraft('old1', {{pick: 'a', reply: 'short quotes'}});
setDraft('old3', {{close: true}});
assert.strictEqual(store['q:drafts'].old1.p, 'Build it?');
setDraft('old3', {{close: null}});
assert.ok(!('old3' in store['q:drafts']), 'a draft with only its words left is dropped');
D = null;  // a browser reload: the old version is gone from memory
carry(D, {{questions: [{{id: 'new1', prompt: 'Build it?'}}, {{id: 'new2', prompt: 'Close it?'}}]}});
assert.deepStrictEqual(store['q:drafts'], {{new1: {{pick: 'a', reply: 'short quotes', p: 'Build it?', pl: 'choice a'}}}});
assert.ok(SIM.new2 && !SIM.old2 && SIM.note9 && saved === 1);
""")


def test_counts_wait_for_the_read_on_its_way(tmp_path):
    """Running 1: a count asked while the newer version is being read waits for it; marked stale mid-read, it reads again."""
    load = grab("  let reading = null;", "\n  };")
    node(tmp_path, f"""
const assert = require('assert');
let D = {{v: 0}}, stale = true, ctx = null, n = 0; const S = {{}}, relist = () => {{}};
const sim = d => d;
const c = {{data: () => new Promise(r => setTimeout(() => r({{v: ++n}}), 20))}};
{load}
(async () => {{
  const a = load(c), b = load(c);  // the Questions chip and the top bar at once
  await b; assert.strictEqual(D.v, 1); await a;
  assert.strictEqual(n, 1, 'one read');
  const p = load(c); stale = true;  // nothing to read: returns at once
  await p; const q = load(c); await Promise.resolve(); stale = true; await q;
  assert.strictEqual(D.v, 3, 'marked stale while reading: read again');
}})().catch(e => {{ console.error(e); process.exit(1); }});
""")


def test_send_count_follows_each_tab_data():
    """Frame 2: once a tab's chip has its data, the Send count repaints, so restored Reference drafts count without a click."""
    i = FRAME.index("function drawTabs()")
    assert "refreshSend();  // its tab's data is in" in FRAME[i:FRAME.index("\n  }\n", i)]
