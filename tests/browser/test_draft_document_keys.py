"""agent-annotate-hnc: a draft stays with the document it was typed in.

The PR #48 review found text typed while another plan loads, or in a plan
that is withdrawn, stored under the other plan's drafts key, so it showed on
the wrong plan and was missing where it was typed.
"""

import json
import shutil

import pytest
from single_page import feedback, ready
from test_card_layout import CHROME, _page, _serve

from agent_annotate.categories import publish_plan_revision

playwright = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")


def _drafts(page, plan):
    return page.evaluate("k => JSON.parse(localStorage.getItem(k) || '{}')", f"annotate:drafts:/:plan:{plan}")


def _open(tmp_path):
    slug_dir = _page(tmp_path)
    publish_plan_revision(slug_dir, "alpha", "<h1>Alpha</h1><p>First plan.</p>", title="Alpha", section="tracking")
    publish_plan_revision(slug_dir, "beta", "<h1>Beta</h1><p>Second plan.</p>", title="Beta")
    return slug_dir


def _type_gf(page, text):
    feedback(page)
    if not page.locator("#gf-ta").is_visible():
        page.locator("#general-feedback-toggle").click()
    page.locator("#gf-ta").fill(text)


def _session(tmp_path, slug_dir, body):
    process, base = _serve(tmp_path, slug_dir)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.set_default_timeout(8000)
            page.goto(base + "#view=plans&plan=alpha", wait_until="networkidle")
            ready(page)
            playwright.expect(page.frame_locator("#content-frame").locator("h1")).to_have_text("Alpha")
            body(page)
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_draft_typed_while_another_plan_loads_stays_with_its_plan(tmp_path):
    slug_dir = _open(tmp_path)

    def body(page):
        _type_gf(page, "Alpha")
        # Hold the next plan's metadata so the switch is still loading.
        page.evaluate("""() => {
            const real = window.fetch;
            let release;
            window.__held = new Promise(r => { release = r; });
            window.__release = release;
            window.fetch = async (url, opts) => {
                if (String(url).includes('api/plans/beta')) await window.__held;
                return real(url, opts);
            };
        }""")
        page.evaluate("() => window.AA.go({view: 'plans', plan: 'beta'})")
        page.wait_for_function("() => window.AnnotateDocs.planId() === 'beta'")
        page.locator("#gf-ta").fill("Alpha, typed while Beta loads")
        page.evaluate("() => window.__release()")
        playwright.expect(page.frame_locator("#content-frame").locator("h1")).to_have_text("Beta")
        ready(page)
        assert _drafts(page, "alpha").get("gf") == "Alpha, typed while Beta loads"
        assert "gf" not in _drafts(page, "beta")
        assert page.locator("#gf-ta").input_value() == ""

    _session(tmp_path, slug_dir, body)


def test_draft_in_a_withdrawn_plan_stays_with_that_plan(tmp_path):
    slug_dir = _open(tmp_path)

    def body(page):
        _type_gf(page, "Alpha")
        shutil.rmtree(slug_dir / "plans" / "alpha")
        page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        page.wait_for_function("() => window.AnnotateDocs.planId() === 'beta'")
        # Still typing in the box the reviewer had open.
        page.locator("#gf-ta").fill("Alpha, after it was withdrawn")
        assert _drafts(page, "alpha").get("gf") == "Alpha, after it was withdrawn"
        assert "gf" not in _drafts(page, "beta"), json.dumps(_drafts(page, "beta"))
        page.evaluate("() => window.AA.go({view: 'review'})")
        page.evaluate("() => window.AA.go({view: 'plans', plan: 'beta'})")
        playwright.expect(page.frame_locator("#content-frame").locator("h1")).to_have_text("Beta")
        ready(page)
        assert page.locator("#gf-ta").input_value() == ""
        assert "gf" not in _drafts(page, "beta")

    _session(tmp_path, slug_dir, body)
