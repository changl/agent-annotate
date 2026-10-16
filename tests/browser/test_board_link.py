"""The header links to the project's board with its ready count (decision #20).

The board is tracker-neutral project data (url, project id, optional
directory) the agent sets; the server counts `bd ready --json` there off the
request path, so the page never waits for it. Issue ids on that board, in the
document and in the rail, open the issue.
"""

import json

import pytest
from single_page import browser_page, feedback, go
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
