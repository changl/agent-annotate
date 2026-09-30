"""One card layout with its context inside it, and unchanged sections folded.

Chang's complaints, from transcripts: to answer a card he scrolled the page to
find what it referred to; its context sat behind "Why / details" 94% of the
time; evidence links scrolled the page away with no way back; each question
rendered up to three times; and every later version repeated the whole plan at
full weight. This drives a generated v2 page in a real Chrome and checks each
of those on both surfaces — the body strip and the rail card.
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from agent_annotate.pagegen import generate  # noqa: E402

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

CONTEXT = ("Lifecycle and delivery both write `status` today, so every consumer "
           "branches on a value whose meaning depends on the writer. The billing "
           "export already mis-read it twice this quarter, and v3 adds a fourth reader.")

PLAN = """
The items table backs three services.

## Scope

What this round decides.

- The status column rename
- Which service owns tier

## Columns

| Column | Type | Note |
|---|---|---|
| status | text | Ambiguous: lifecycle and delivery both write it |
| tier | text | Stable, but ownership is unassigned |

## Migration sketch

{migration}
"""

CARDS = [
    {"number": 1, "anchor_id": "d:q1",
     "text": "Rename status to lifecycle_state. Three services read the column.",
     "decision_request": {
         "prompt": "Rename status → lifecycle_state?",
         "context": CONTEXT,
         "recommendation": "accept",
         "options": [
             {"id": "accept", "label": "Rename with a dual-write week",
              "consequence": "One week of dual writes, three deploys."},
             {"id": "reject", "label": "Keep status",
              "consequence": "The name stays ambiguous through v3."}],
         "evidence": [{"label": "the column", "anchor": "tbl:columns:row:status"},
                      {"label": "migration sketch", "anchor": "s:migration-sketch"}]}},
    {"number": 2, "anchor_id": "d:q2", "text": "Drop the shadow column?",
     "decision_request": {
         "prompt": "Drop the shadow column?",
         "evidence": [{"label": "migration sketch", "anchor": "s:migration-sketch"}]}},
]


def _doc(version, migration, cards=None):
    front = (f"---\ntitle: Items model\nversion: {version}\n"
             "full_plan: true\nother_files_required: none\n---\n")
    body = PLAN.format(migration=migration)
    if cards:
        body += "\n## Questions for Chang\n\n```cards\n" + json.dumps(cards) + "\n```\n"
    return front + body


def _comment(cid, card, created="2026-09-27T09:00:00Z"):
    return {"id": cid, "anchor_id": card["anchor_id"], "number": card["number"],
            "text": card["text"], "author": "agent:test", "created_at": created,
            "version": "v2", "status": "open",
            "decision_request": dict(card["decision_request"], requested_at=created)}


def _page(tmp_path):
    slug_dir = tmp_path / "items-model"
    v1 = tmp_path / "v1.md"
    v1.write_text(_doc("v1", "Two statements and a week of dual writes."), encoding="utf-8")
    generate(v1, slug_dir)
    v2 = tmp_path / "v2.md"
    v2.write_text(_doc("v2", "Two statements and two weeks of dual writes.", CARDS),
                  encoding="utf-8")
    result = generate(v2, slug_dir)
    assert result["unchanged_sections"] == ["s:scope", "s:columns"]
    (slug_dir / "current.html").unlink()
    (slug_dir / "current.html").symlink_to(Path("versions") / "v2.html")
    (slug_dir / "current.meta.json").write_text(json.dumps({
        "current": "v2",
        "history": [{"version": "v1", "label": "round 1"},
                    {"version": "v2", "label": "round 2"}],
    }), encoding="utf-8")
    plain = {"id": "plain-scope", "anchor_id": "s:scope:li1", "text": "Is this still true?",
             "author": "reviewer@example.com", "created_at": "2026-09-27T09:05:00Z",
             "version": "v2", "status": "open"}
    (slug_dir / "comments.json").write_text(json.dumps({
        "schema_version": 2,
        "anchors": {"d:q1": [_comment("card-1", CARDS[0])],
                    "d:q2": [_comment("card-2", CARDS[1])],
                    "s:scope:li1": [plain]},
        "archived": {},
    }), encoding="utf-8")
    return slug_dir


def _serve(tmp_path, slug_dir):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env["ANNOTATE_STATE_DIR"] = str(tmp_path / "state")
    process = subprocess.Popen(
        [sys.executable, "-m", "agent_annotate.sync_server", "--slug-dir", str(slug_dir),
         "--slug", "items-model", "--bus-dir", str(tmp_path / "bus"), "--port", str(port),
         "--local-author", "reviewer@example.com", "--local-author-name", "Browser Reviewer"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    base = f"http://127.0.0.1:{port}/"
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            urllib.request.urlopen(base, timeout=1).close()
            return process, base
        except OSError:
            time.sleep(0.05)
    process.terminate()
    raise AssertionError("sync server did not come up")


def _in_view(locator):
    return locator.evaluate(
        "el => { const r = el.getBoundingClientRect();"
        " return r.height > 0 && r.top >= 0 && r.bottom <= window.innerHeight; }")


def _wait(predicate, page, timeout_ms=3000):
    waited = 0
    while not predicate():
        if waited >= timeout_ms:
            raise AssertionError("condition never became true")
        page.wait_for_timeout(100)
        waited += 100


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_card_layout_and_unchanged_sections(tmp_path):
    slug_dir = _page(tmp_path)
    process, base = _serve(tmp_path, slug_dir)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": 1400, "height": 900})
            page.set_default_timeout(5_000)
            page.goto(base, wait_until="networkidle")
            frame = page.frame_locator("#content-frame")
            strip = frame.locator('.annotate-decision-strip[data-strip-anchor="d:q1"]')
            strip.wait_for(state="visible")

            # ── Unchanged sections fold; the one an open card cites does not.
            assert frame.locator('section[data-unchanged-since="v1"]').count() == 2
            scope = frame.locator('section[data-anchor-id="s:scope"]')
            assert "annotate-unchanged-collapsed" in scope.get_attribute("class")
            assert not frame.locator('[data-anchor-id="s:scope:li1"]').is_visible()
            bar = scope.locator(".annotate-unchanged-toggle")
            assert bar.get_attribute("aria-expanded") == "false"
            assert "Scope" in bar.inner_text()
            assert "Unchanged since v1 — show" in bar.inner_text()
            columns = frame.locator('section[data-anchor-id="s:columns"]')
            assert "annotate-unchanged-collapsed" not in (columns.get_attribute("class") or "")
            assert frame.locator('[data-anchor-id="tbl:columns:row:status"]').is_visible()
            # Open or folded, the header is one control that carries the
            # section title; the generated <h2> is not shown twice.
            open_bar = columns.locator(".annotate-unchanged-toggle")
            assert open_bar.inner_text().split("\n")[0] == "Columns"
            assert "Unchanged since v1 — hide" in open_bar.inner_text()
            assert columns.locator(".annotate-unchanged-bar").get_attribute("role") == "heading"
            for sec in (scope, columns):
                assert not sec.locator(":scope > h2").is_visible()
            assert frame.locator(
                'section[data-anchor-id="s:migration-sketch"] .annotate-unchanged-bar').count() == 0

            # ── One card per question in the body.
            assert not frame.locator('.card[data-anchor-id="d:q1"]').is_visible()
            assert frame.locator('.annotate-decision-strip[data-strip-anchor="d:q1"]').count() == 1

            # ── Strip: number + prompt, full context, recommendation, excerpt, rows.
            assert strip.locator(".annotate-decision-prompt").inner_text().startswith("#1")
            assert strip.locator(".annotate-decision-context").inner_text() == CONTEXT
            assert "Why / details" not in strip.inner_text()
            assert strip.locator(".annotate-decision-reco-line").inner_text() == (
                "Recommended: Rename with a dual-write week")
            excerpt = strip.locator(".annotate-excerpt").first
            assert "status" in excerpt.locator(".annotate-excerpt-text").inner_text()
            assert "Ambiguous" in excerpt.locator(".annotate-excerpt-text").inner_text()
            assert excerpt.locator(".annotate-excerpt-src").inner_text().lower() == (
                "columns › status")
            rows = strip.locator(".annotate-decision-btns > .annotate-opt-row")
            assert rows.count() == 2
            assert rows.nth(0).locator(".annotate-decision-rec").count() == 1
            assert "One week of dual writes" in rows.nth(0).inner_text()
            assert rows.nth(1).locator(".annotate-decision-rec").count() == 0

            # ── Evidence: collapsed, previews in place, Go to leaves Back to #1.
            toggle = strip.locator(".annotate-decision-evidence-toggle")
            # Nothing empty sits between the last option and "Evidence (n)".
            gap = strip.evaluate("""s => {
                const rows = s.querySelectorAll('.annotate-opt-row');
                const r = document.createRange();
                r.selectNodeContents(s.querySelector('.annotate-decision-evidence-toggle'));
                return r.getBoundingClientRect().top - rows[rows.length - 1].getBoundingClientRect().bottom;
            }""")
            assert gap <= 18, gap
            assert toggle.inner_text() == "Evidence (2)"
            assert toggle.get_attribute("aria-expanded") == "false"
            items = strip.locator(".annotate-decision-evidence-link")
            assert not items.first.is_visible()
            toggle.click()
            items.first.click()
            preview = strip.locator(".annotate-decision-evidence-preview").first
            assert preview.is_visible()
            assert "Ambiguous" in preview.inner_text()
            preview.locator(".annotate-decision-evidence-goto").click()
            back = frame.locator("[data-annotate-back] .annotate-back-pill, .annotate-back-pill")
            back.first.wait_for(state="visible")
            assert back.first.inner_text() == "↩ Back to #1"
            _wait(lambda: _in_view(frame.locator('[data-anchor-id="tbl:columns:row:status"]')), page)
            back.first.click()
            item = frame.locator('[data-strip-item="card-1"]')
            _wait(lambda: _in_view(item), page)
            assert frame.locator(".annotate-back-pill").count() == 0

            # ── Rail card: the same layout.
            rail = page.locator('.citem[data-comment-id="card-1"]')
            assert rail.locator(".decision-context").inner_text() == CONTEXT
            assert rail.locator(".decision-disclosure-btn").count() == 0
            assert rail.locator(".decision-reco-line").inner_text() == (
                "Recommended: Rename with a dual-write week")
            rail.locator(".decision-excerpt-text").first.wait_for()
            assert "Ambiguous" in rail.locator(".decision-excerpt-text").first.inner_text()
            assert rail.locator(".decision-btns > .decision-btn").count() == 2
            rail.locator(".decision-evidence-toggle").click()
            rail.locator(".decision-evidence-link").nth(1).click()
            rail_preview = rail.locator(".decision-evidence-preview").nth(1)
            assert "two weeks of dual writes" in rail_preview.inner_text()
            rail_preview.locator(".decision-evidence-goto").click()
            frame.locator(".annotate-back-pill").wait_for(state="visible")
            frame.locator(".annotate-back-pill").click()
            page.locator('.citem.hl[data-comment-id="card-1"]').wait_for()

            # ── A jump into a folded section opens it.
            page.locator('.citem[data-comment-id="plain-scope"] [data-action="goto"]').click()
            _wait(lambda: frame.locator('[data-anchor-id="s:scope:li1"]').is_visible(), page)
            assert "annotate-unchanged-collapsed" not in (scope.get_attribute("class") or "")
            assert bar.get_attribute("aria-expanded") == "true"
            assert "Unchanged since v1 — hide" in bar.inner_text()
            # …and the header folds it again.
            bar.click()
            assert not frame.locator('[data-anchor-id="s:scope:li1"]').is_visible()
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_project_modules_and_custom_choices_share_managed_ui(tmp_path):
    from agent_annotate.project_state import save_project
    source = tmp_path / "source.md"
    source.write_text(_doc("v1", "```details\nSupporting evidence\nThis is a hidden detail.\n```"))
    directory = tmp_path / "items-model"
    generate(source, directory)
    save_project(directory, {"title":"Project workspace", "modules":[
        {"id":"resources","title":"Open project","kind":"links","items":[{"label":"Payload CMS","url":"https://cms.example/admin"}]},
        {"id":"progress","title":"Progress","kind":"progress","items":[{"label":"Review pipeline","status":"done"}]}]})
    process, base = _serve(tmp_path, directory)
    try:
        item = {"number":1, "anchor_id":"s:scope", "text":"Pick a runtime", "version":"v1",
                "decision_request":{"prompt":"Pick a runtime", "options":["Shared runtime","Keep fork"], "recommendation":"Shared runtime"}}
        request = urllib.request.Request(base + "api/comments/batch", data=json.dumps({"items":[item]}).encode(),
            headers={"Content-Type":"application/json", "X-Annotate-Agent":"agent:test"})
        urllib.request.urlopen(request).close()
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width":1440,"height":1000})
            page.goto(base, wait_until="networkidle")
            frame = page.frame_locator('#content-frame')
            panel = frame.locator('#project-panel')
            panel.locator(':scope > summary').click()
            panel.locator('details[data-module="resources"] summary').click()
            panel.locator('a').wait_for(state="visible")
            assert panel.locator('a').get_attribute('href') == 'https://cms.example/admin'
            assert page.locator('#vrail-body .vrow').first.evaluate('e => e.tagName') == 'BUTTON'
            frame.locator('link[href*="content.css"]').wait_for(state="attached")
            assert frame.locator('.aa-details').count() == 1
            assert frame.locator('.aa-details').get_attribute('open') is None
            page.locator('#comment-list button').filter(has_text='Shared runtime').click()
            page.locator('#round-finish-btn').wait_for(state="visible")
            assert 'PENDING' in page.locator('#comment-list').inner_text()
            page.screenshot(path='/tmp/annotate-managed-desktop.png', full_page=True)
            panel.locator('details[data-module="resources"] summary').click()
            page.reload(wait_until="networkidle")
            panel.wait_for(state="visible")
            assert panel.locator('details[data-module="resources"]').get_attribute('open') is None
            page.set_viewport_size({"width":390,"height":844})
            _wait(lambda: _in_view(page.locator("#round-finish-btn")), page)
            page.screenshot(path='/tmp/annotate-managed-mobile.png', full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
