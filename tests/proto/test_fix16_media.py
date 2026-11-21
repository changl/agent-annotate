"""Fourteenth check: every picture gets zoom, Full size and its label; code gets Copy; a diagram becomes a figure (r12 audit14 questions 3-6)."""

import html
import re
import subprocess
from pathlib import Path

import pytest

from test_fix14_frame import grab

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
QS = (WEB / "questions.js").read_text()
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

# today's server markup: only a large picture gets a preview and a ⤢ Full size link; a small one gets neither
DOC = """<article class="aa"><section data-anchor-id="s:a"><h2>A</h2>
<figure class="aa-figure" data-anchor-id="fig:big"><img src="assets/preview/b.jpg" data-full="assets/big.png" data-img="AB12" alt="Big one"><a class="aa-full" href="assets/big.png" target="_blank" rel="noopener">⤢ Full size</a><figcaption>Big one</figcaption></figure>
<figure class="aa-figure" data-anchor-id="fig:small"><img src="assets/small.png" data-img="CD34" alt="Small one" width="1108" height="186"><figcaption>Small one</figcaption></figure>
<pre data-anchor-id="s:a:cmd"><code>annotate doctor</code></pre>
<p>Flow:</p><!-- DIAGRAM:flow -->
<script type="application/json" id="diagram-spec-flow">{"nodes":[{"id":"a","label":"A"}],"edges":[]}</script>
</section></article>"""


def run(tmp_path):
    if not CHROME.exists():
        pytest.skip("Chrome not installed")
    code = grab(QS, "  function diagrams(doc) {", "    el.querySelectorAll('img').forEach(i => { i.loading = 'eager'; });\n  }\n")
    page = tmp_path / "t.html"
    page.write_text(f"""<!doctype html><body><template id="src">{DOC}</template><div id="out"></div><script>
const esc = s => String(s).replace(/[&<>"]/g, c => ({{'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}})[c]);
const ic = k => '<svg data-i="' + k + '"></svg>', ctx = {{prefs: {{get: (k, d) => d}}}}, mounted = [];
function mountDgm(f) {{ mounted.push(f.dataset.dgm); }}
const zoomOf = src => (ctx.prefs.get('q:zoomPer', {{}}))[src] || ctx.prefs.get('zoomDef', 75);
{code}
const doc = new DOMParser().parseFromString(document.getElementById('src').innerHTML, 'text/html');
diagrams(doc); doc.querySelectorAll('script').forEach(n => n.remove()); numberPics(doc);
const out = document.getElementById('out'); out.innerHTML = doc.body.innerHTML; zoomBars(out);
out.dataset.mounted = mounted.join(',');
</script></body>""")
    r = subprocess.run([str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={tmp_path / 'c'}",
                        "--allow-file-access-from-files", "--dump-dom", page.as_uri()], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout[r.stdout.index('<div id="out"'):]


def test_every_picture_gets_zoom_full_size_and_label_not_only_a_previewed_one(tmp_path):
    out = run(tmp_path)
    for name, src in (("big", "assets/big.png"), ("small", "assets/small.png")):
        fig = re.search(rf'<figure[^>]*fig:{name}".*?</figure>', out, re.S).group(0)
        assert 'class="qzm"' in fig and f'data-zfull="{src}"' in fig, name
        assert re.search(r'<b class="qpicn"[^>]*>Picture \d</b>', fig), name
        assert fig.count('class="aa-full"') == 1, name  # the server's link is replaced, not doubled
    assert re.search(r'fig:small".*?Picture 2.*?Small one', out, re.S)


def test_code_block_gets_copy_and_diagram_becomes_a_numbered_figure(tmp_path):
    out = run(tmp_path)
    assert re.search(r'<pre[^>]*qcodehost[^>]*>.*annotate doctor.*data-codecopy', out, re.S)
    fig = re.search(r'<figure class="qdgm"[^>]*>.*?</figure>', out, re.S).group(0)
    assert 'data-dgm="flow"' in fig and 'data-anchor-id="dgm:flow"' in fig and 'Picture 3' in fig and 'data-zdgm="flow"' in fig
    assert '"nodes"' in html.unescape(fig)  # its spec survived the scripts being dropped
    assert 'data-mounted="flow"' in out
