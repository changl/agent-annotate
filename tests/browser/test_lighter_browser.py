"""Lighter load (2026-10-31): History and strip Evidence are built when opened, fonts are woff2 fetched once,
and Send's General feedback row has a text button. WebKit with the iPad Pro 11 profile."""

import json
import socket
from contextlib import contextmanager

import pytest
from test_keep_drafts import _agent, _directory, _loaded, _poll, _start, _stop

playwright = pytest.importorskip("playwright.sync_api")


def _rounds(directory):
    rounds = [
        {"id": "r-old", "ts": "2026-10-02T10:05:00Z", "by": "reviewer@example.com", "version": "v1", "send_id": "s-old",
         "receipt": [{"cat": "review", "label": "Older round line", "answer": "Fine"}]},
        {"id": "r-new", "ts": "2026-10-02T10:30:00Z", "by": "reviewer@example.com", "version": "v1", "send_id": "s-new",
         "receipt": [{"cat": "review", "label": "Latest round line", "answer": "Ship now"}]},
    ]
    (directory / "rounds.ndjson").write_text("".join(json.dumps(r) + "\n" for r in rounds))


@contextmanager
def _ipad(tmp_path, directory):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = _start(tmp_path, directory, port)
    base = f"http://127.0.0.1:{port}/"
    try:
        with playwright.sync_playwright() as runner:
            try:
                browser = runner.webkit.launch()
            except Exception:
                pytest.skip("Playwright WebKit is not installed")
            page = browser.new_context(**dict(runner.devices["iPad Pro 11"])).new_page()
            page.set_default_timeout(8000)
            history = []
            page.on("request", lambda r: "/api/history" in r.url and history.append(r.url.split("/api/history")[1]))
            fonts = []
            page.on("request", lambda r: r.resource_type == "font" and fonts.append(r.url.rsplit("/", 1)[1]))
            page.goto(base + "#view=review", wait_until="networkidle")
            _loaded(page)
            yield page, base, history, fonts
            browser.close()
    finally:
        _stop(server)


def test_history_is_built_and_fully_fetched_only_when_opened(tmp_path):
    directory = _directory(tmp_path)
    _rounds(directory)
    with _ipad(tmp_path, directory) as (page, _, history, _fonts):
        # The header's receipt comes from the latest round alone; the hidden list is not built.
        page.wait_for_function("() => document.getElementById('send-note').textContent.includes('Feedback saved (1)')")
        assert history == ["?latest=1"]
        assert page.locator("#vrail-body-review .vrow").count() == 0

        page.evaluate("window.AA.rail.reveal('history')")
        page.locator("#vrail-body-review .vrow").first.wait_for()
        body = page.locator("#vrail-body-review")
        page.wait_for_function("() => document.getElementById('vrail-body-review').textContent.includes('Older round line')")
        assert "Latest round line" in body.inner_text()
        assert history == ["?latest=1", ""]
        # Polls keep the full list (no fall back to the latest round) and the list stays drawn.
        _poll(page, 2)
        assert history.count("?latest=1") == 1
        assert "Older round line" in body.inner_text()


def test_strip_evidence_is_built_on_open_and_stays_open_across_a_poll_redraw(tmp_path):
    directory = _directory(tmp_path)
    with _ipad(tmp_path, directory) as (page, base, _history, _fonts):
        page.keyboard.press("Escape")  # the feedback sheet covers the document on iPad
        page.locator("#unified-sheet-backdrop").wait_for(state="hidden")
        frame = page.frame_locator("#content-frame")
        toggle = frame.locator(".annotate-decision-evidence-toggle").first
        toggle.wait_for()
        assert toggle.inner_text() == "Evidence (1)"
        assert frame.locator(".annotate-decision-evidence-item").count() == 0

        toggle.tap()
        item = frame.locator(".annotate-decision-evidence-item")
        item.wait_for()
        assert item.count() == 1
        frame.locator(".annotate-decision-evidence-toggle").first.evaluate("el => { el.dataset.before = '1'; }")

        # An agent change redraws the strips on the next poll.
        _agent(base, "api/comments/batch", {"items": [{"anchor_id": "s:checks", "text": "A note from the agent.", "version": "v1"}]})
        _poll(page, 3)
        page.wait_for_function("""() => {
          const doc = document.getElementById('content-frame').contentDocument;
          const t = doc.querySelector('.annotate-decision-evidence-toggle');
          return t && !t.dataset.before;
        }""")
        redrawn = frame.locator(".annotate-decision-evidence-toggle").first
        assert redrawn.get_attribute("aria-expanded") == "true"
        assert frame.locator(".annotate-decision-evidence-item").count() == 1
        assert frame.locator(".annotate-decision-evidence-list").first.is_visible()


def test_fonts_are_woff2_and_fetched_once_across_shell_and_document(tmp_path):
    directory = _directory(tmp_path)
    with _ipad(tmp_path, directory) as (page, _, _history, fonts):
        page.wait_for_function("() => document.fonts.status === 'loaded'")
        assert fonts and all(name.endswith(".woff2") for name in fonts), fonts
        timing = """() => performance.getEntriesByType('resource')
          .filter(e => e.name.endsWith('/RobotoVariable.woff2')).map(e => e.transferSize)"""
        frame = page.locator("#content-frame").element_handle().content_frame()
        frame.wait_for_function("() => document.fonts.status === 'loaded'")
        sizes = page.evaluate(timing) + frame.evaluate(timing)
        # The document frame asks for the same URL and gets it from the cache.
        assert len(sizes) == 2 and sum(1 for n in sizes if n > 0) == 1, sizes
        assert frame.evaluate("() => document.fonts.check('12px Roboto')")


def test_general_feedback_row_has_add_and_edit_text_buttons(tmp_path):
    directory = _directory(tmp_path)
    with _ipad(tmp_path, directory) as (page, _, _history, _fonts):
        page.evaluate("window.AA.send.open()")
        row = page.locator('#round-confirm-backdrop [data-sum-id="gf"]')
        button = row.locator('[data-sum-edit="gf"]')
        button.wait_for()
        assert button.inner_text() == "Add general feedback"
        assert button.locator("svg").count() == 0

        button.tap()
        box = row.locator("#sum-gf-ta")
        box.wait_for()
        box.fill("Overall this reads well")
        button.tap()
        page.wait_for_function("""() => document.querySelector('#round-confirm-backdrop [data-sum-id="gf"] [data-sum-edit="gf"]')
          .textContent === 'Edit'""")
        assert "Overall this reads well" in row.inner_text()
        assert button.get_attribute("aria-label") == "Edit general feedback"

        button.tap()
        box.wait_for()
        assert box.input_value() == "Overall this reads well"
