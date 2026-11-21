"""Thirteenth check: Reload is neutral while any check is on its way (r12 audit13 frame 3, questions 3, reference 2)."""

from test_fix14_frame import FRAME, grab, node


def test_reload_is_neutral_while_a_check_is_pending(tmp_path):
    check = grab(FRAME, "  let copyWatch = 0", "    return true;\n  }\n")
    node(tmp_path, f"""
const assert = require('assert');
const COPY = 'rebex', S = {{loadedV: 'v438', menu: '', checked: '11:00'}};
const hhmm = () => '12:00';
const held = [];
const hold = () => new Promise(ok => held.push(ok));
const api = p => hold();
api.meta = () => hold();
api.comments = () => Promise.resolve({{anchors: {{}}}});
const setTimeout = () => 1;
const meta = v => ({{current: v, history: [{{version: 'v438'}}, {{version: v}}]}});
{check}
(async () => {{
  // a check starts: the earlier "Up to date" goes at once
  const a = checkNewer();
  assert.strictEqual(S.checked, '');
  // Reload pressed while the first is held: the first, answering last with the old version, never paints "Up to date"
  const [aMeta, aCp] = held.splice(0);
  const b = checkNewer();
  const [bMeta, bCp] = held.splice(0);
  aMeta(meta('v438')); aCp({{copying: '', current: 'v438'}});
  await new Promise(r => setImmediate(r));
  assert.strictEqual(S.checked, '');
  bMeta(meta('v450')); bCp({{copying: '', current: 'v450'}});
  assert.strictEqual(await b, true); assert.strictEqual(await a, true);
  assert.strictEqual(S.checked, ''); assert.strictEqual(S.newer.v, 'v450');
}})().catch(e => {{ console.error(e); process.exit(1); }});
""")
