"""Managed title, table typography, and canonical question labels survive rounds."""

import json
import urllib.request

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from test_card_layout import CHROME, _serve  # noqa: E402

from agent_annotate.pagegen import generate  # noqa: E402

TITLE = "Runtime and feedback review"
TABLE = """
## Coverage

| Configuration | Recommendation | Implementation | Verification | Performance | Ownership | Dependencies | Communication |
|---|---|---|---|---|---|---|---|
| Consistent configuration | Existing components | Small implementation | Independent verification | Predictable performance | Established ownership | Existing dependencies | Bidirectional communication |
"""


def _document(version="v1", cards=None, title=TITLE):
    body = TABLE
    if cards:
        body += "\n## Questions for Chang\n\n```cards\n" + json.dumps(cards) + "\n```\n"
    return (f"---\ntitle: {title}\nversion: {version}\nfull_plan: true\nother_files_required: none\n---\n"
            f"# {title}\n" + body)


def _page(tmp_path):
    source = tmp_path / "page.md"
    source.write_text(_document())
    directory = tmp_path / "items-model"
    generate(source, directory)
    return directory


_WORDS = """table => {
  const fragments = [];
  const walk = document.createTreeWalker(table, NodeFilter.SHOW_TEXT);
  while (walk.nextNode()) {
    const node = walk.currentNode;
    for (const word of node.textContent.matchAll(/[A-Za-z]{4,}/g)) {
      const range = document.createRange();
      range.setStart(node, word.index);
      range.setEnd(node, word.index + word[0].length);
      const lines = new Set([...range.getClientRects()]
        .filter(r => r.width > 0 && r.height > 0).map(r => Math.round(r.top)));
      if (lines.size > 1) fragments.push(word[0]);
    }
  }
  return fragments;
}"""


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width", [1440, 390])
def test_normal_table_words_stay_whole_or_scroll_horizontally(tmp_path, width):
    process, base = _serve(tmp_path, _page(tmp_path))
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.goto(base, wait_until="networkidle")
            table = page.frame_locator("#content-frame").locator(".aa table")
            table.wait_for(state="visible")
            page.screenshot(path=f"/tmp/annotate-core-table-{width}.png", full_page=True)
            assert table.evaluate(_WORDS) == []
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert table.evaluate("el => document.documentElement.scrollWidth <= innerWidth")
            assert table.evaluate("""el => {
                const wrap = el.closest('.wrap');
                if (wrap.scrollWidth <= wrap.clientWidth) return true;
                wrap.scrollLeft = wrap.scrollWidth;
                const canScroll = wrap.scrollLeft > 0;
                wrap.scrollLeft = 0;
                return canScroll;
            }""")
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width", [1440, 390])
def test_frontmatter_title_is_visible_in_managed_content_and_shell(tmp_path, width):
    directory = _page(tmp_path)
    # Emulate a frozen generated version from before the visible-title fix.
    # The original template header holds the title outside the canvas.
    version = directory / "versions" / "v1.html"
    version.write_text(version.read_text().replace(f'<h1 class="aa-page-title">{TITLE}</h1>', ""))
    process, base = _serve(tmp_path, directory)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.goto(base, wait_until="networkidle")
            frame = page.frame_locator("#content-frame")
            title = frame.locator(".aa-page-title")
            page.screenshot(path=f"/tmp/annotate-core-title-{width}.png", full_page=True)
            assert title.count() == 1 and title.is_visible()
            assert title.inner_text() == TITLE
            assert title.evaluate("el => { const r = el.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; }")
            assert page.locator("#hdr-title").inner_text() == TITLE
            assert page.title() == TITLE
            assert frame.locator('section[data-anchor-id="s:coverage"]').count() == 1
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


def _question(number):
    return {"number": number, "anchor_id": f"d:q{number}", "text": f"Choose response {number}.",
            "decision_request": {"prompt": "Choose a response?", "evidence": [{"anchor": "s:coverage"}],
                                 "options": [{"id": "accept", "label": "Approve"}, {"id": "reject", "label": "Revise"}]}}


def _api(base, path, body, method="POST", reviewer=False):
    headers = {"Content-Type": "application/json"}
    if reviewer:
        headers["Origin"] = base.rstrip("/")
    else:
        headers["X-Annotate-Agent"] = "agent:ui-regression"
    request = urllib.request.Request(base + path, data=json.dumps(body).encode(), method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width", [1440, 390])
def test_explicit_labels_survive_two_rounds_repose_carry_history_and_new_questions(tmp_path, width):
    from agent_annotate.cli import _decision_cards

    directory = tmp_path / "items-model"
    first_source = tmp_path / "v1.md"
    first_source.write_text(_document(cards=[_question(13), _question(14)]))
    generate(first_source, directory)
    process, base = _serve(tmp_path, directory)
    try:
        ids = _api(base, "api/comments/batch", {"items": [dict(_question(n), version="v1") for n in (13, 14)]})["ids"]
        _api(base, f"api/comments/{ids[0]}/decision", {"verdict": "accept", "defer_push": True}, reviewer=True)
        _api(base, "api/rounds/submit", {"note": "First round complete; carry the remaining question."}, reviewer=True)
        second_title = TITLE + " — second round"
        second_source = tmp_path / "v2.md"
        second_source.write_text(_document("v2", [_question(n) for n in (13, 14, 15)], title=second_title))
        generate(second_source, directory)
        _api(base, f"api/comments/{ids[0]}", {"status": "resolved_in_version", "resolved_in_version": "v2",
                                             "resolution_anchor_id": "s:coverage"}, method="PUT")
        _api(base, f"api/comments/{ids[1]}", {"carry_forward": {"version": "v2", "anchor_id": "d:q14"}}, method="PUT")
        added = _api(base, "api/comments/batch", {"items": [dict(_question(n), version="v2") for n in (13, 15)]})["ids"]
        expected = {added[0]: 13, ids[1]: 14, added[1]: 15}
        meta = json.loads((directory / "current.meta.json").read_text())
        meta["current"] = "v2"
        meta["history"].append({"version": "v2", "label": "Second round"})
        (directory / "current.meta.json").write_text(json.dumps(meta))
        original_ids = set(ids)

        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": width, "height": 1000})
            page.set_default_timeout(5000)
            page.goto(base, wait_until="networkidle")
            frame = page.frame_locator("#content-frame")

            def assert_labels():
                for cid, number in expected.items():
                    rail = page.locator(f'.citem[data-comment-id="{cid}"] .citem-num')
                    assert rail.inner_text() == f"#{number}"
                    strip = frame.locator(f'[data-strip-item="{cid}"] .annotate-decision-prompt')
                    assert strip.inner_text().startswith(f"#{number}")
                    pin = frame.locator(f'[data-pin-comments="{cid}"]')
                    assert pin.first.inner_text() == str(number)
                    assert frame.locator(f'.card[data-anchor-id="d:q{number}"] .item-num').inner_text() == f"#{number}"
                stored = json.loads((directory / "comments.json").read_text())
                assert {card["id"]: card["number"] for card in _decision_cards(stored)} == expected

            assert_labels()
            for cid in expected:
                _api(base, f"api/comments/{cid}/decision", {"verdict": "accept", "defer_push": True}, reviewer=True)
            _api(base, "api/rounds/submit", {"note": "Second round complete."}, reviewer=True)
            page.reload(wait_until="networkidle")
            assert_labels()
            assert page.title() == second_title
            if width > 1160:
                page.locator('#vrail-body button[data-version="v1"]').click()
            else:
                page.locator(".mobile-version-select").select_option("v1")
            page.wait_for_function("title => document.title === title", arg=TITLE)
            assert frame.locator(".aa-page-title").inner_text() == TITLE
            assert frame.locator('.card[data-anchor-id="d:q13"] .item-num').inner_text() == "#13"
            if width > 1160:
                page.locator('#vrail-body button[data-version="v2"]').click()
            else:
                page.locator(".mobile-version-select").select_option("v2")
            page.wait_for_function("title => document.title === title", arg=second_title)
            assert_labels()
            page.screenshot(path=f"/tmp/annotate-core-numbering-{width}.png", full_page=True)
            browser.close()

        stored = json.loads((directory / "comments.json").read_text())
        live_ids = {comment["id"] for items in stored["anchors"].values() for comment in items}
        assert original_ids.issubset(live_ids)
        carried = next(comment for items in stored["anchors"].values() for comment in items if comment["id"] == ids[1])
        assert carried["number"] == 14 and carried["carry_history"]
        assert [entry["version"] for entry in json.loads((directory / "current.meta.json").read_text())["history"]] == ["v1", "v2"]
        events = [json.loads(line) for line in (tmp_path / "bus" / "items-model.ndjson").read_text().splitlines()]
        assert len([event for event in events if event.get("event") == "round_submitted"]) == 2
    finally:
        process.terminate()
        process.wait(timeout=5)
