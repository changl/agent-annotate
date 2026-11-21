"""Fifteenth check: every document reader draws pictures and code with the same shared code (r12 audit15 reference 4, 5)."""

import re
from pathlib import Path

from test_fix14_frame import grab, node

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
QS, REF, LNK = ((WEB / f).read_text() for f in ("questions.js", "reference.js", "links.js"))
MEDIA = grab(QS, "  const M = P.media = {", "    },\n  };\n")
STUB = """const assert = require('assert');
const P = {ctx: {esc: s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'})[c])}, icon: k => '<i data-i="' + k + '"></i>'};
const esc = s => P.ctx.esc(s), ic = k => P.icon(k);
"""


def test_reference_and_links_call_the_shared_code_not_their_own():
    assert "P.media.code(t)" in REF and "P.media.label(n)" in REF and "P.media.onCopy(b)" in REF
    assert "P.media.code(t, a)" in LNK and "P.media.onCopy(b)" in LNK
    for src in (REF, LNK):
        assert "<pre><code>" not in src and not re.search(r"<pre\$\{a\}><code>", src)  # no reader keeps its own code block


def test_reference_picture_line_is_numbered_with_zoom_and_full_size(tmp_path):
    bar = grab(REF, "  let picN = 0;", "za))}</figcaption>`; };\n")
    node(tmp_path, STUB + MEDIA + f"""
const zOf = () => 50;
{bar}
const h = zoomBar('ref:p~3', 'a/b.png', 'Board <front>', 3);
assert.match(h, /^<figcaption class="qcap"><b class="qpicn">Picture 3<\\/b><span>·<\\/span><span class="qcapt">Board &lt;front&gt;<\\/span>/);
assert.strictEqual((h.match(/data-zk="ref:p~3"/g) || []).length, 5);  // four sizes and Full size open this picture's viewer
assert.match(h, /<a class="aa-full" href="a\\/b.png"[^>]* data-zoom="50" data-zk="ref:p~3">⤢ Full size<\\/a>/);
assert.match(h, /data-zoom="50" data-zk="ref:p~3" aria-pressed="true"/);
""")


def test_shared_code_block_has_copy_and_copies_the_command_alone(tmp_path):
    node(tmp_path, STUB + MEDIA + """
const h = M.code('git status\\n<x>', ' data-line="4"');
assert.strictEqual(h, '<pre class="qcodehost" data-line="4"><code>git status\\n&lt;x&gt;</code><button class="btn sm qcodecopy" data-codecopy title="Copy the command" aria-label="Copy the command"><i data-i="copy"></i><span>Copy</span></button></pre>');
// onCopy: the clipboard gets the code without the button's label, then the button reads Copied
let got = '', toast = '';
P.ctx.toast = m => { toast = m; };
Object.defineProperty(globalThis, 'navigator', {value: {clipboard: {writeText: async t => { got = t; }}}, configurable: true});
const btn = {innerHTML: 'Copy', closest: () => ({cloneNode: () => ({querySelectorAll: () => [], textContent: 'git status\\n'})})};
M.onCopy(btn).then(() => { assert.strictEqual(got, 'git status'); assert.strictEqual(toast, 'Command copied'); assert.match(btn.innerHTML, /Copied/); process.exit(0); });
""")
