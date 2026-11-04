"""Page look (Chang, 2026-11-02): one number chip on the right, section and subsection
headings that read as breaks, and tables whose short columns shrink.

- The number chip sits right of what it numbers, so the text keeps its left edge.
  Red needs you, orange is answered but not sent (no separate Pending chip),
  yellow the agent has it (sent, owner receipt back), light green addressed,
  neutral grey otherwise (Chang #123, #136); each passes 4.5:1, in light and dark. A question card
  in the page carries its own chip, so its anchor gets no second one.
- A `##` is a tinted band with an accent bar; a `###` is bold with a thinner bar.
- Table headers step towards the text colour; a short column shrinks, one with a
  longer cell wraps it to two lines instead of widening; the label column keeps room.
"""

import json
import socket

import pytest
from review_fixtures import complete
from single_page import CHROME, ready
from test_keep_drafts import _start, _stop

from agent_annotate.pagegen import generate

playwright = pytest.importorskip("playwright.sync_api")

ME = "reviewer@example.com"
T, SENT = "2026-11-02T10:00:00Z", "2026-11-02T10:05:00Z"
FIREBASE, TWILIO_P, ROW = "s:blocked-items:firebase-login", "s:blocked-items:p3", "tbl:blocked-items:row:deletion-merge"
SOURCE = """---
title: Page look
version: v1
full_plan: true
other_files_required: none
---

## Blocked items

Every item here waits on you.

| What holds them | Beads | What's left | Moves when |
|---|---|---|---|
| Queued on the M1Max16 now | 9 | iPhone large-text check (running), then 15 server and web items in a queue | Soon |
| Android release line (Play96) | 2 + the 10 above again | Merge into Android main, gates, picture check; carries the stop-box fix | Later |
| Deletion merge | 1 | Done 02:25 (below) | Now |

### Firebase login

Switch off the leaked login.

### Twilio key

Revoke the old key.

## Questions for Chang

```cards
CARDS
```
"""
OPTIONS = [{"id": "now", "label": "Ship now"}, {"id": "later", "label": "Ship later"}]


def _directory(tmp_path):
    cards = [{"number": n, "anchor_id": f"d:q{n}", "text": f"Question {n}.", "decision_request": {
        "prompt": f"Question {n}?", "options": OPTIONS, "recommendation": "now", "evidence": [{"anchor": FIREBASE, "label": "Firebase"}]}}
        for n in (1, 2, 3)]
    source = tmp_path / "review.md"
    source.write_text(SOURCE.replace("CARDS", json.dumps(cards)))
    directory = tmp_path / "review"
    generate(source, directory)
    complete(directory)  # a draft is never shown (PR 95)
    anchors = {}
    for card in cards:
        c = dict(card, id=f"question-{card['number']}", author="agent:page-look", created_at=T, version="v1", status="open")
        c["decision_request"] = dict(card["decision_request"], requested_at=T)
        anchors[card["anchor_id"]] = [c]
    # #2 answered, not sent: orange. #3 answered and sent: neutral. #1 open: red.
    anchors["d:q2"][0]["decision"] = {"verdict": "select", "text": "Ship now", "ts": SENT, "by": ME, "round_pending": True}
    anchors["d:q3"][0].update(decision={"verdict": "select", "text": "Ship now", "ts": T, "by": ME},
                              flagged_for_session=True, flagged_at=SENT)
    mine = {"author": ME, "created_at": T, "version": "v1", "status": "open", "flagged_for_session": True, "flagged_at": SENT}
    anchors[TWILIO_P] = [dict(mine, id="agent-replied", anchor_id=TWILIO_P, text="Is it off?", number=4,
                              replies=[{"author": "agent:page-look", "text": "Yes; the laptop copy needs you.", "ts": SENT}])]
    anchors[ROW] = [dict(mine, id="waiting", anchor_id=ROW, text="When?", number=5, replies=[])]
    # #6 sent and the owner read it: yellow. #7 addressed by the agent: light green.
    anchors[FIREBASE] = [dict(mine, id="working", anchor_id=FIREBASE, text="Switch it off today.", number=6, replies=[],
                              delivery_id="d-read"),
                         dict(mine, id="addressed", anchor_id=FIREBASE, text="And log it.", number=7, replies=[],
                              status="addressed_by_agent", delivery_id="d-read")]
    journal = tmp_path / "state" / "deliveries" / "bus" / "items-model.json"
    journal.parent.mkdir(parents=True, exist_ok=True)
    journal.write_text(json.dumps({"deliveries": {"d-read": {"id": "d-read", "state": "acknowledged"}}}))
    (directory / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": anchors, "archived": {}}))
    return directory


@pytest.fixture(params=["ipad-webkit", "desktop-chrome"])
def frame(request, tmp_path):
    directory = _directory(tmp_path)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = _start(tmp_path, directory, port)
    try:
        with playwright.sync_playwright() as runner:
            if request.param == "ipad-webkit":
                try:
                    browser = runner.webkit.launch()
                except Exception:
                    pytest.skip("Playwright WebKit is not installed")
                page = browser.new_context(**dict(runner.devices["iPad Pro 11"])).new_page()
            else:
                if not CHROME.exists():
                    pytest.skip("Google Chrome is not installed")
                browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 960})
            page.set_default_timeout(8000)
            try:
                page.goto(f"http://127.0.0.1:{port}/#view=review", wait_until="networkidle")
                ready(page)
                page.frame_locator("#content-frame").locator('[data-strip-item="question-3"]').wait_for()
                f = page.query_selector("#content-frame").content_frame()
                f.wait_for_selector('#badge-layer .bpin[data-pin-anchor="%s"]' % ROW, state="attached")
                f.evaluate(HELPERS)
                yield page, f
            finally:
                browser.close()
    finally:
        _stop(server)


# Colours resolved through a canvas, so oklch()/color-mix() compare as sRGB.
HELPERS = """() => {
  const ctx = document.createElement('canvas').getContext('2d', {willReadFrequently: true});
  const rgb = css => { ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = '#000'; ctx.fillStyle = css; ctx.fillRect(0, 0, 1, 1); return [...ctx.getImageData(0, 0, 1, 1).data].slice(0, 3); };
  const lum = css => { const [r, g, b] = rgb(css).map(v => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const page = () => getComputedStyle(document.body).backgroundColor;
  window.__look = {rgb, lum, ratio, page};
}"""


def L_of(rgb):
    """Relative luminance of an sRGB triple."""
    lin = [(v / 255) / 12.92 if v / 255 <= 0.04045 else ((v / 255 + 0.055) / 1.055) ** 2.4 for v in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _theme(page, f, theme):
    page.evaluate("t => { document.documentElement.setAttribute('data-theme', t); document.querySelector('#content-frame').contentDocument.documentElement.setAttribute('data-theme', t); }", theme)
    page.wait_for_timeout(150)


def test_one_number_chip_on_the_right_coloured_by_state(frame):
    page, f = frame
    # Text keeps its left edge: a pin sits right of what it numbers, a table row's right of the table.
    place = f.evaluate("""([p, row]) => {
      const pin = a => document.querySelector('#badge-layer .bpin[data-pin-anchor="' + a + '"]');
      const r = el => el.getBoundingClientRect();
      const para = document.querySelector('[data-anchor-id="' + p + '"]');
      const table = document.querySelector('[data-anchor-id="' + row + '"]').closest('.unified-table-scroll');
      return {pText: pin(p).textContent, pLeft: r(pin(p)).left, paraRight: r(para).right, paraLeft: r(para).left,
              rowLeft: r(pin(row)).left, tableRight: r(table).right, tableLeft: r(table).left,
              pinState: pin(p).className, rowState: pin(row).className,
              cardPins: [...document.querySelectorAll('#badge-layer .bpin')].filter(b => /question-/.test(b.dataset.pinComments)).length,
              vw: document.documentElement.clientWidth, pinRight: r(pin(p)).right};
    }""", [TWILIO_P, ROW])
    assert place["pText"] == "#4"
    assert place["pLeft"] >= place["paraRight"] and place["rowLeft"] >= place["tableRight"], place
    assert place["tableLeft"] == place["paraLeft"], "tables share the text's left edge"
    assert place["pinRight"] <= place["vw"], place
    assert "is-needs" in place["pinState"] and "is-" not in place["rowState"].replace("bpin", ""), place
    assert place["cardPins"] == 0, "a card in the page carries its own number"
    # Cards in the page: the chip starts the question line (Chang #172); orange replaces the Pending chip.
    cards = f.evaluate("""() => [1, 2, 3].map(n => {
      const item = document.querySelector('[data-strip-item="question-' + n + '"]');
      const chip = item.querySelector('.annotate-decision-num'), r = chip.getBoundingClientRect();
      const line = chip.parentElement.getBoundingClientRect();
      const after = [...chip.parentElement.children].filter(c => c !== chip).map(c => c.getBoundingClientRect().left);
      return {cls: chip.className, text: chip.textContent, first: Math.min(...after) >= r.right, atStart: r.left - line.left < 2,
              pending: item.querySelectorAll('.annotate-send-state.is-pending').length};
    })""")
    assert [c["text"] for c in cards] == ["#1", "#2", "#3"]
    assert all(c["first"] and c["atStart"] for c in cards), cards
    assert [c["cls"].replace("annotate-decision-num", "").strip() for c in cards] == ["is-needs", "is-pending", ""]
    assert all(c["pending"] == 0 for c in cards), cards
    # Right column (Chang #172): the chip is the first thing on each card's line, and
    # there is no separate unread dot; Needs you cards have no tinted background.
    rail = page.evaluate("""() => { const cards = [...document.querySelectorAll('#comment-list .citem')];
      const card = document.querySelector('#comment-list .citem[data-comment-id="agent-replied"]');
      return card && card.offsetWidth ? {cls: card.querySelector('.citem-num').className,
        firsts: cards.filter(c => c.querySelector('.citem-num')).map(c => (c.querySelector('.citem-node, .citem-line').firstElementChild || {}).className),
        dots: document.querySelectorAll('.unread-dot').length,
        tinted: cards.filter(c => getComputedStyle(c).backgroundColor !== getComputedStyle(cards[0]).backgroundColor).length} : null; }""")
    if rail:  # the rail is closed on narrow layouts
        assert "is-needs" in rail["cls"] and rail["dots"] == 0 and rail["tinted"] == 0, rail
        assert rail["firsts"] and all(f.startswith("citem-num") for f in rail["firsts"]), rail
    for theme in ("light", "dark"):
        _theme(page, f, theme)
        look = f.evaluate("""() => { const L = window.__look, root = getComputedStyle(document.documentElement);
          return [...document.querySelectorAll('#badge-layer .bpin, .annotate-decision-num')].map(c => { const cs = getComputedStyle(c);
            return {cls: c.className, bg: L.rgb(cs.backgroundColor), text: L.ratio(cs.color, cs.backgroundColor),
                    page: L.ratio(cs.backgroundColor, L.page()), darker: L.lum(cs.backgroundColor) < L.lum(L.page()),
                    fits: c.scrollWidth <= c.clientWidth + 0.5,
                    error: L.rgb(root.getPropertyValue('--color-error')), warning: L.rgb(root.getPropertyValue('--color-warning')),
                    success: L.rgb(root.getPropertyValue('--color-success'))}; }); }""")
        assert {w for c in look for w in c["cls"].split() if w.startswith("is-")} >= {"is-needs", "is-pending", "is-working", "is-done"}, look
        # Yellow and orange part clearly: at least 1.4:1 between their backgrounds.
        bg = {w: c["bg"] for c in look for w in c["cls"].split() if w in ("is-pending", "is-working")}
        hi, lo = sorted([L_of(bg["is-working"]), L_of(bg["is-pending"])], reverse=True)
        assert (hi + 0.05) / (lo + 0.05) >= 1.4, (theme, bg)
        for chip in look:
            assert chip["text"] >= 4.5 and chip["fits"], (theme, chip)
            if "is-needs" in chip["cls"]:
                assert chip["bg"] == chip["error"], (theme, chip)
            elif "is-pending" in chip["cls"]:
                # Orange: between the theme's warning and error, red above green above blue.
                r, g, b = chip["bg"]
                assert chip["bg"] not in (chip["warning"], chip["error"]) and r > g > b, (theme, chip)
            elif "is-working" in chip["cls"]:
                # #148: a step lighter than the stock warning, clearly apart from orange.
                r, g, b = chip["bg"]
                assert r > b and g > b and chip["bg"] != chip["warning"], (theme, chip)
                assert L_of(chip["bg"]) > L_of(chip["warning"]), (theme, chip)
            elif "is-done" in chip["cls"]:
                # Light green: a tint of success, never the full colour.
                r, g, b = chip["bg"]
                assert g > r and g > b and chip["bg"] != chip["success"] and chip["page"] < 2, (theme, chip)
            else:
                # Neutral: darker grey on light, lighter grey on dark, clear of the page.
                assert chip["page"] >= 3 and chip["darker"] == (theme == "light"), (theme, chip)


def test_sections_are_bands_and_subsections_still_read_as_breaks(frame):
    page, f = frame
    for theme in ("light", "dark"):
        _theme(page, f, theme)
        h = f.evaluate("""() => { const L = window.__look, s = el => getComputedStyle(el);
          const h2 = s(document.querySelector('.aa h2')), h3 = s(document.querySelector('.aa h3')), p = s(document.querySelector('.aa p'));
          const th = s(document.querySelector('.aa th'));
          return {h2bar: h2.borderLeftWidth, h2fill: L.ratio(h2.backgroundColor, L.page()), h2weight: +h2.fontWeight, h2size: parseFloat(h2.fontSize),
                  h3bar: h3.borderLeftWidth, h3weight: +h3.fontWeight, h3size: parseFloat(h3.fontSize), body: parseFloat(p.fontSize),
                  h3barColour: L.ratio(h3.borderLeftColor, L.page()),
                  thLighter: L.lum(th.backgroundColor) > L.lum(L.page()), thStep: L.ratio(th.backgroundColor, L.page()), thWeight: +th.fontWeight}; }""")
        assert h["h2bar"] == "3px" and h["h2fill"] > 1.05 and h["h2weight"] >= 700, (theme, h)
        assert h["h3bar"] == "2px" and h["h3weight"] >= 700 and h["h3barColour"] >= 1.5, (theme, h)
        assert h["body"] < h["h3size"] < h["h2size"], (theme, h)
        # The header row steps towards the text: lighter than a dark page, darker than a light one.
        assert h["thLighter"] == (theme == "dark") and h["thStep"] > 1.15 and h["thWeight"] >= 700, (theme, h)


def test_short_columns_shrink_and_a_longer_cell_wraps_to_two_lines(frame):
    _, f = frame
    t = f.evaluate("""() => { const rows = [...document.querySelector('.aa table').rows];
      const col = i => rows.map(r => r.cells[i]);
      const lines = cell => { const range = document.createRange(); range.selectNodeContents(cell);
        return new Set([...range.getClientRects()].map(r => Math.round(r.top))).size; };
      const font = parseFloat(getComputedStyle(rows[1].cells[0]).fontSize);
      return {first: col(0)[0].getBoundingClientRect().width / font, beads: col(1)[0].getBoundingClientRect().width,
              beadsLines: lines(rows[2].cells[1]), whenLines: col(3).map(lines), when: col(3)[0].getBoundingClientRect().width,
              prose: col(2)[0].getBoundingClientRect().width}; }""")
    assert t["first"] >= 12, t  # the label column is not squeezed
    assert t["beadsLines"] == 2, t  # "2 + the 10 above again" wraps to two lines, not one wide line
    assert t["whenLines"] == [1, 1, 1, 1] and t["when"] < 100, t  # short values stay on one line, column shrinks
    assert t["prose"] > 3 * t["beads"], t


# Chang #172: the quoted context has no line on its left and its own background;
# the recommended option sits on light green (its Recommended tag stays, so
# colour is not the only sign), in the right column and in the page, dark and light.
LOOK = """root => { const L = window.__look, s = el => getComputedStyle(el);
  const under = el => { for (el = el.parentElement; el; el = el.parentElement) { const c = s(el).backgroundColor; if (c !== 'rgba(0, 0, 0, 0)' && c !== 'transparent') return c; } return L.page(); };
  const q = sel => root.querySelector(sel);
  const ex = q('.decision-excerpt, .annotate-excerpt'), rec = q('.decision-btn.is-recommended, .annotate-decision-btn.is-recommended');
  const other = q('.decision-btn:not(.is-recommended), .annotate-decision-btn:not(.is-recommended)');
  return {exLine: s(ex).borderLeftWidth, exApart: L.ratio(s(ex).backgroundColor, under(ex)), exText: L.ratio(s(ex).color, s(ex).backgroundColor),
          rec: L.rgb(s(rec).backgroundColor), recVsOther: L.ratio(s(rec).backgroundColor, s(other).backgroundColor),
          recText: L.ratio(s(rec).color, s(rec).backgroundColor), tag: !!rec.querySelector('.decision-rec-badge, .annotate-decision-rec')}; }"""


def test_context_block_and_recommended_option_stand_out_in_dark_and_light(frame):
    page, f = frame
    page.evaluate(HELPERS)
    rail = page.locator('#comment-list .citem[data-comment-id="question-1"]')
    doc = f.locator('[data-strip-item="question-1"]')
    for theme in ("dark", "light"):
        _theme(page, f, theme)
        found = {"page": doc.evaluate(LOOK)}
        if rail.is_visible():  # the rail is closed on narrow layouts
            found["rail"] = rail.evaluate(LOOK)
        for where, x in found.items():
            r, g, b = x["rec"]
            assert x["exLine"] == "0px" and x["exApart"] >= 1.15 and x["exText"] >= 4.5, (theme, where, x)
            assert g > r and g > b and x["recVsOther"] >= 1.15 and x["recText"] >= 4.5 and x["tag"], (theme, where, x)
