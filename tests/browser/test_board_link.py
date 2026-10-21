"""The header links to the project's board with its ready count (decision #20).

The board is tracker-neutral project data (url, project id, optional
directory) the agent sets; the server counts `bd ready --json` there off the
request path, so the page never waits for it. Issue ids on that board, in the
document and in the rail, open the issue.
"""

import json

import pytest
from single_page import browser_page, feedback, go, section
from test_card_jump import page_dir  # noqa: F401  (fixture)
from test_card_layout import CHROME, _wait

from agent_annotate.project_state import save_project

playwright = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")

BOARD = "https://board.example:8473/p/jump"

@pytest.fixture
def board_page(tmp_path, page_dir, monkeypatch):  # noqa: F811
    fake = tmp_path / "bd"
    # A second of latency, like the real bd: the page must not wait for it.
    fake.write_text("#!/bin/sh\nsleep 1\necho '[" + ",".join('{"id":"jump-%d"}' % i for i in range(7)) + "]'\n")
    fake.chmod(0o755)
    monkeypatch.setenv("ANNOTATE_BD", str(fake))
    save_project(page_dir, {"title": "Jump", "modules": [], "board": {
        "url": BOARD, "project": "jump", "label": "Beads", "dir": str(tmp_path)}})
    html = page_dir / "versions" / "v1.html"
    html.write_text(html.read_text().replace("The end.", "Tracked as jump-w6e.4, not as notjump-w6e.4."))
    path = page_dir / "comments.json"
    store = json.loads(path.read_text())
    store["anchors"]["d:q2"][0]["decision_request"]["context"] = "Filed as jump-w6e.4."
    path.write_text(json.dumps(store))
    return page_dir


def _link(page):
    return page.locator("#aa-tabs a.aa-board-link")


def test_header_board_link_with_ready_count_on_every_tab(tmp_path, board_page):
    with browser_page(tmp_path, board_page) as (page, base):
        link = _link(page)
        link.wait_for()
        assert link.get_attribute("href") == BOARD
        assert link.get_attribute("target") == "_blank" and link.get_attribute("rel") == "noopener noreferrer"
        assert link.inner_text().startswith("Beads")
        # The count arrives after the page is usable, from the server's cache.
        _wait(lambda: link.locator(".aa-board-count").count() == 1, page, timeout_ms=10_000)
        assert link.locator(".aa-board-count").inner_text() == "7 ready"
        # The page never exposes the board's local directory.
        project = json.loads(page.evaluate("() => fetch('./api/project').then(r => r.text())"))
        assert "dir" not in project["board"]
        board = json.loads(page.evaluate("() => fetch('./api/board').then(r => r.text())"))
        assert board["ready"] == 7 and "dir" not in board["board"]
        # It sits with the tabs, after the last one.
        assert page.evaluate("() => document.querySelector('#aa-tabs .tabs').lastElementChild.classList.contains('aa-board-link')")
        page.screenshot(path=str(tmp_path / "board-link-1440.png"), clip={"x": 0, "y": 0, "width": 1440, "height": 120})
        for view, extra in (("plans", {"plan": "launch"}), ("findings", {})):
            go(page, view, **extra)
            assert _link(page).is_visible() and "7 ready" in _link(page).inner_text()
        go(page, "review")
        # Issue ids on the board link to the issue, in the document and in the rail.
        frame = page.frame_locator("#content-frame")
        doc_link = frame.locator("a.annotate-issue-link")
        doc_link.first.wait_for()
        assert doc_link.count() == 1  # "notjump-w6e.4" is not on this board
        assert doc_link.get_attribute("href") == BOARD + "?bead=jump-w6e.4"
        feedback(page)
        rail_link = page.locator('.citem[data-comment-id="card-2"] .decision-context .ticket-link')
        assert rail_link.get_attribute("href") == BOARD + "?bead=jump-w6e.4"


def test_phone_header_menu_lists_the_board(tmp_path, board_page):
    with browser_page(tmp_path, board_page, width=390, height=844) as (page, _):
        menu = page.locator("#aa-tabs-menu")
        menu.locator("summary").click()
        item = menu.locator("a.aa-board-link")
        _wait(lambda: "7 ready" in item.inner_text(), page, timeout_ms=10_000)
        assert item.get_attribute("href") == BOARD and item.get_attribute("target") == "_blank"
        page.screenshot(path=str(tmp_path / "board-link-390.png"))


# w6e.15: header items never overlap, clip or squeeze, at any width, rail open
# or closed; the tabs, the board link and its count share one baseline.
HEADER_GEOMETRY = r"""() => {
  const shown = el => { const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden'; };
  const hdr = document.querySelector('.hdr'), H = hdr.getBoundingClientRect();
  const items = [document.querySelector('.hdr-title'), ...document.querySelectorAll('#aa-tabs .tab'),
    document.querySelector('#aa-tabs-menu > summary'), ...document.querySelectorAll('.hdr-right > *')]
    .filter(el => el && shown(el)).map(el => ({ el, r: el.getBoundingClientRect(),
      name: el.id || el.dataset.view || el.className }));
  const problems = [];
  items.forEach((a, i) => {
    if (a.r.left < H.left - .5 || a.r.right > H.right + .5 || a.r.top < H.top - .5 || a.r.bottom > H.bottom + .5)
      problems.push(a.name + ' leaves the header');
    items.slice(i + 1).forEach(b => {
      if (a.r.left < b.r.right - .5 && b.r.left < a.r.right - .5 && a.r.top < b.r.bottom - .5 && b.r.top < a.r.bottom - .5)
        problems.push(a.name + ' overlaps ' + b.name);
    });
  });
  // Roboto's baseline sits 0.927/1.171 down its glyph box.
  const baseline = el => { const n = [...el.childNodes].find(c => c.nodeType === 3 && c.textContent.trim());
    const range = document.createRange(); range.selectNodeContents(n); const r = range.getBoundingClientRect();
    return r.top + r.height * 0.927 / 1.171; };
  const lines = [...document.querySelectorAll('#aa-tabs .tab')].filter(shown).flatMap(t =>
    [baseline(t), ...[...t.querySelectorAll('.badge')].map(baseline)]);
  return { problems, spread: lines.length ? Math.max(...lines) - Math.min(...lines) : 0,
    tabs: lines.length > 0, wraps: [...document.querySelectorAll('#aa-tabs .tab')].filter(shown)
      .filter(t => t.getBoundingClientRect().height > 44.5 || t.scrollWidth > t.clientWidth + 1).length };
}"""


def test_header_items_never_overlap_and_share_one_baseline(tmp_path, board_page):
    with browser_page(tmp_path, board_page) as (page, _):
        _wait(lambda: _link(page).locator(".aa-board-count").count() == 1, page, timeout_ms=10_000)
        # k5y: the project's other pages are listed in the rail, never in the header.
        assert page.locator('#aa-tabs [data-view="linked"]').count() == 0
        for collapsed in (False, True):
            page.set_viewport_size({"width": 1440, "height": 900})
            page.evaluate("id => document.getElementById(id).click()", "drawer-collapse" if collapsed else "drawer-strip")
            assert page.evaluate("() => document.getElementById('drawer').classList.contains('collapsed')") == collapsed
            for width in (390, 768, 1100, 1161, 1280, 1440, 1920, 2560):
                page.set_viewport_size({"width": width, "height": 900})
                page.wait_for_timeout(150)
                geometry = page.evaluate(HEADER_GEOMETRY)
                assert geometry["problems"] == [], (width, collapsed, geometry)
                assert geometry["wraps"] == 0, (width, collapsed)
                assert geometry["spread"] < 1, (width, collapsed, geometry["spread"])
                if width >= 1440:
                    assert geometry["tabs"], f"tabs fold at {width}px with room to spare"
                if width in (1100, 1280, 1440, 1920) and not collapsed:
                    page.screenshot(path=str(tmp_path / f"header-{width}.png"), clip={"x": 0, "y": 0, "width": width, "height": 120})


# w6e.16: the header's "x of n decided" counts exactly the rail's Needs you set
# and what the reviewer has answered there this round; a card answered in an
# earlier round and waiting on the agent is not counted.
def test_header_progress_counts_the_needs_you_set(tmp_path, board_page):
    path = board_page / "comments.json"
    store = json.loads(path.read_text())
    store["anchors"]["d:q2"][0]["decision"] = {"verdict": "reject", "by": "reviewer@example.com",
                                               "ts": "2026-10-16T11:00:00Z", "text": "Not yet"}
    # Submitted in an earlier round: delivered to the agent, which has not replied.
    store["anchors"]["d:q2"][0].update(flagged_for_session=True, flagged_at="2026-10-16T11:01:00Z")
    path.write_text(json.dumps(store))
    with browser_page(tmp_path, board_page) as (page, _):
        feedback(page)
        needs = page.locator('#comment-list .sec[data-section="needs"] .citem')
        progress = page.locator("#hdr-progress-txt")
        _wait(lambda: needs.count() == 1 and progress.is_visible(), page)
        assert section(page, "waiting").locator('.citem[data-comment-id="card-2"]').count() == 1
        assert progress.inner_text() == "0 of 1 decided"
        page.locator('.citem[data-comment-id="card-1"] .decision-btns > .decision-btn').first.click()
        _wait(lambda: progress.inner_text() == "1 of 1 decided", page)
        assert needs.count() == 0
