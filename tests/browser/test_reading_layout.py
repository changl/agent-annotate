"""Reading layout from Chang's 2026-10-10 feedback, in a real Chrome.

The document uses a wide monitor while text keeps its measure; one text-size
control scales the shell and the document; feedback from earlier versions stays
listed (collapsed); a Markdown plan is readable in both themes.
"""

import json

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from test_card_layout import CHROME, _page, _serve  # noqa: E402

from agent_annotate.categories import publish_plan_revision  # noqa: E402
from agent_annotate.pagegen import render_plan  # noqa: E402

PLAN = "---\ntitle: Rollout\n---\n\nShip in two steps.\n\n## Steps\n\n- Build the wheel\n- Install on both Macs\n"

# A hand-built HTML plan with its own light-only palette, as agents publish them.
CUSTOM = """<!doctype html><html><head><style>
:root{--accent:#4f46e5}
html{font-size:62.5%}
body{background:#f8fafc;color:#161b36;font-family:Georgia}
.main{max-width:1360px;margin:0 auto}
.panel{background:#ffffff;color:#111827;border:1px solid #e5e7eb;font-size:16px}
.bad{color:#dc2626}
.pill{background:#dcfce7;color:#166534}
.bar{position:sticky;top:0;background:#fff}
.btn{background-color:var(--accent);color:#fff}
.grad{background-image:linear-gradient(90deg,#4f46e5,#db2777);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.tri{width:0;height:0;border:8px solid transparent;border-top-color:#333}
.cards{display:grid;grid-template-columns:repeat(3,1fr)}
.rem{font-size:1.6rem}
.token{color:var(--ok-text)}
</style></head><body><div class="main"><div class="bar">Toolbar</div>
<h1>Custom plan</h1><div class="panel"><p>Panel text</p><p class="bad">Blocked</p><span class="pill">Done</span></div>
<span class="btn">Go</span><span class="grad">Gradient</span><span class="tri"></span>
<div class="cards"><div class="card">A</div><div class="card">B</div><div class="card">C</div></div>
<p class="rem">Rem text</p><p class="token">Token</p>
<svg width="40" height="20"><text x="0" y="15" style="fill:#111">S</text></svg></div></body></html>"""


def _luminance(color):
    """Relative luminance of a computed `rgb(...)` colour."""
    r, g, b = (int(x) / 255 for x in color[color.index("(") + 1:color.index(")")].split(",")[:3])
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# Computed colours as rgb(): the theme tokens are oklch, so read them back
# through a canvas, which always reports sRGB.
TEXT_ON_BG = """e => {
  const rgb = c => { const x = document.createElement('canvas').getContext('2d'); x.fillStyle = c; x.fillRect(0, 0, 1, 1);
    const [r, g, b] = x.getImageData(0, 0, 1, 1).data; return `rgb(${r}, ${g}, ${b})`; };
  let b = e; while (b && getComputedStyle(b).backgroundColor === 'rgba(0, 0, 0, 0)') b = b.parentElement;
  return [rgb(getComputedStyle(e).color), rgb(b ? getComputedStyle(b).backgroundColor : '#fff')];
}"""


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_wide_document_text_size_earlier_feedback_and_plan_contrast(tmp_path):
    slug_dir = _page(tmp_path)
    store = json.loads((slug_dir / "comments.json").read_text())
    store["anchors"]["s:scope:li2"] = [{
        "id": "old-1", "anchor_id": "s:scope:li2", "text": "Tier ownership is unclear.", "author": "reviewer@example.com",
        "created_at": "2026-09-20T09:00:00Z", "version": "v1", "status": "open",
        "flagged_for_session": True, "flagged_at": "2026-09-20T09:01:00Z"}]
    (slug_dir / "comments.json").write_text(json.dumps(store))
    # Published pages carry a frozen copy of content.css (with a leading
    # comment); the server must drop it so today's rules apply.
    frozen = '<style data-annotate-style="managed">/* old */\n.aa{max-width:1080px;margin:0 auto}</style>'
    for doc in slug_dir.rglob("*.html"):
        text = doc.read_text(encoding="utf-8")
        start = text.find('<style data-annotate-style="managed">')
        if start != -1:
            end = text.index("</style>", start) + len("</style>")
            doc.write_text(text[:start] + frozen + text[end:], encoding="utf-8")
    html, title = render_plan(PLAN, "rollout")
    publish_plan_revision(slug_dir, "rollout", html, title=title)
    publish_plan_revision(slug_dir, "custom", CUSTOM, title="Custom")
    process, base = _serve(tmp_path, slug_dir)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": 2400, "height": 1200})
            page.set_default_timeout(5000)
            page.goto(base, wait_until="networkidle")
            frame = page.frame_locator("#content-frame")
            frame.locator('[data-strip-item="card-1"]').wait_for()

            # The document fills a wide pane; prose and question cards keep 1080px.
            widths = frame.locator("body").evaluate(
                "() => ({vw: innerWidth, aa: document.querySelector('.aa').getBoundingClientRect().width,"
                " p: document.querySelector('.aa p').getBoundingClientRect().width,"
                " table: document.querySelector('.aa table').getBoundingClientRect().width,"
                " strip: document.querySelector('.annotate-decision-strip').getBoundingClientRect().width})")
            assert widths["aa"] == widths["vw"] > 1800, widths
            assert widths["table"] > 1600, widths
            assert widths["p"] <= 1080 and widths["strip"] <= 1080, widths

            # Feedback from v1 is listed under a collapsed "Earlier feedback".
            head = page.locator('#comment-list [data-section-toggle="earlier"]')
            assert head.get_attribute("aria-expanded") == "false"
            head.click()
            assert page.locator('#comment-list .sec[data-section="earlier"] .citem[data-comment-id="old-1"]').count() == 1

            # One control scales every text, in the shell and the document; it persists.
            assert frame.locator(".aa p").first.evaluate("e => getComputedStyle(e).fontSize") == "11px"
            page.locator("#text-size-btn").click()
            page.locator("#text-size-up").click()
            page.locator("#text-size-up").click()
            assert page.locator("#text-size-val").inner_text() == "125%"
            assert frame.locator(".aa p").first.evaluate("e => getComputedStyle(e).fontSize") == "13.75px"
            assert page.locator(".decision-prompt").first.evaluate("e => getComputedStyle(e).fontSize") == "13.75px"
            page.keyboard.press("Escape")
            assert page.locator("#text-size-panel").is_hidden()
            page.reload(wait_until="networkidle")
            frame.locator('[data-strip-item="card-1"]').wait_for()
            assert frame.locator(".aa p").first.evaluate("e => getComputedStyle(e).fontSize") == "13.75px"
            page.locator("#text-size-btn").click()
            page.locator("#text-size-reset").click()
            assert frame.locator(".aa p").first.evaluate("e => getComputedStyle(e).fontSize") == "11px"

            # A Markdown plan is served as a content document and reads in both themes.
            for theme in ("dark", "light"):
                page.evaluate("t => localStorage.setItem('annotate:theme', t)", theme)
                page.goto(base + "#view=plans&plan=rollout", wait_until="networkidle")
                page.reload(wait_until="networkidle")
                plan = page.frame_locator("#content-frame")
                plan.locator(".aa p").first.wait_for()
                assert plan.locator(".canvas-area").count() == 0
                text, bg = plan.locator(".aa p").first.evaluate(TEXT_ON_BG)
                assert _contrast(text, bg) >= 4.5, (theme, text, bg)

                # Annotate owns colour, type and width in hand-built HTML too.
                page.goto(base + "#view=plans&plan=custom", wait_until="networkidle")
                custom = page.frame_locator("#content-frame")
                custom.locator(".panel").wait_for()
                for selector in (".panel p", "h1", ".bar", ".btn"):
                    text, bg = custom.locator(selector).first.evaluate(TEXT_ON_BG)
                    assert _contrast(text, bg) >= 4.5, (theme, selector, text, bg)
                owned = custom.locator("body").evaluate("""b => {
                  const cs = s => getComputedStyle(document.querySelector(s));
                  const probe = document.createElement('span'); probe.style.color = 'var(--ok-text)'; b.appendChild(probe);
                  return {marker: b.classList.contains('aa-owned'), aa: b.classList.contains('aa'),
                          font: cs('.panel').fontFamily, main: cs('.main').maxWidth, bad: cs('.bad').color,
                          svg: cs('svg text').fill, grad: cs('.grad').backgroundImage, tri: cs('.tri').borderLeftColor,
                          columns: cs('.cards').gridTemplateColumns.split(' ').length, card: cs('.card').display,
                          rem: cs('.rem').fontSize, token: cs('.token').color, okText: getComputedStyle(probe).color};
                }""")
                # Annotate's face, theme and widths; the author's layout and components stay.
                assert owned["marker"] and not owned["aa"] and "Georgia" not in owned["font"], owned
                assert owned["main"] == "none" and owned["columns"] == 3 and owned["card"] != "none", owned
                assert owned["svg"] == "rgb(17, 17, 17)", owned  # graphics keep their own colours
                assert owned["bad"] != "rgb(220, 38, 38)", owned  # a red word takes the theme's error colour
                assert "gradient" in owned["grad"], owned  # gradient-clipped text keeps its fill
                assert owned["tri"] == "rgba(0, 0, 0, 0)", owned  # transparent borders stay transparent
                assert owned["rem"] == "16px", owned  # the page's own root size still holds at 100%
                assert owned["token"] == owned["okText"], owned  # annotate's own tokens are left alone
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
