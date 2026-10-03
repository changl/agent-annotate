"""Real editor formatting, safe paste, proposal retry, and collapsed history."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from agent_annotate.copy_state import load_copy, propose_copy, save_copy  # noqa: E402

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web"


@pytest.fixture
def copy_site(tmp_path):
    revisions = [{"id": "old-1", "created_at": "2026-10-01T10:00:00Z", "author": {"id": "agent:copy"},
                  "status": "draft", "delta": {"ops": [{"insert": "Old headline\n"}]}},
                 {"id": "draft-2", "created_at": "2026-10-02T10:00:00Z", "author": {"id": "agent:copy"},
                  "status": "draft", "delta": {"ops": [{"insert": "Everyday essentials", "attributes": {"bold": True}},
                                                        {"insert": "\n"}, {"insert": "Shop the collection.\n"}]}}]
    save_copy(tmp_path, {"blocks": [{"id": "hero", "title": "Home hero", "current": "draft-2", "revisions": revisions}]})
    state = {"fail_after_commit": False, "posts": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, body, code=200, content_type="application/json"):
            body = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/api/copy":
                self.send(json.dumps(load_copy(tmp_path)))
            elif self.path == "/":
                self.send('''<!doctype html><html data-theme="dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
                  <link rel="stylesheet" href="/daisyui.css"><link rel="stylesheet" href="/quill.snow.css">
                  <link rel="stylesheet" href="/copy-editor.css"><style>body{margin:0;background:var(--color-base-100);color:var(--color-base-content);font-family:system-ui}</style>
                  </head><body><main id="copy"></main><script src="/quill.js"></script><script src="/copy-editor.js"></script>
                  <script>window.copyReady=AnnotateCopy.mount(document.querySelector('#copy'),{identity:{email:'reviewer:chang',name:'Chang'}})</script></body></html>''', content_type="text/html")
            elif self.path.removeprefix("/") in {"daisyui.css", "quill.snow.css", "copy-editor.css", "quill.js", "copy-editor.js"}:
                name = self.path.removeprefix("/")
                self.send((WEB / name).read_bytes(), content_type="text/css" if name.endswith(".css") else "text/javascript")
            else:
                self.send("{}", 404)

        def do_POST(self):
            if self.path != "/api/copy/hero/proposal":
                self.send("{}", 404)
                return
            state["posts"] += 1
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            try:
                result = propose_copy(tmp_path, "hero", payload["delta"], {"id": "reviewer:chang", "name": "Chang"},
                                      base_revision=payload["base_revision"], request_id=payload["request_id"])
            except ValueError as exc:
                self.send(json.dumps({"error": str(exc)}), 400)
                return
            if state["fail_after_commit"]:
                state["fail_after_commit"] = False
                self.send(json.dumps({"error": "Connection interrupted. Your draft is kept; try again."}), 503)
            else:
                self.send(json.dumps(result), 201)

    class Server(ThreadingHTTPServer):
        request_queue_size = 64

    server = Server(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield f"http://127.0.0.1:{server.server_port}/", state, tmp_path
    server.shutdown()
    server.server_close()
    worker.join(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width,theme", [(1440, "dark"), (1440, "light"), (390, "dark"), (390, "light")])
def test_copy_format_save_retry_history_and_reopen(copy_site, width, theme):
    base, state, directory = copy_site
    with playwright.sync_playwright() as runner:
        browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
        page = browser.new_page(viewport={"width": width, "height": 850})
        page.set_default_timeout(4000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base, wait_until="networkidle")
        page.evaluate("theme => document.documentElement.dataset.theme=theme", theme)
        page.locator(".copy-block").wait_for()
        assert page.locator(".copy-document strong").inner_text() == "Everyday essentials"
        assert page.locator(".copy-history").get_attribute("open") is None
        assert not page.get_by_text("Old headline", exact=True).is_visible()
        page.get_by_role("button", name="Revise", exact=True).click()
        editor = page.get_by_role("textbox", name="Edit Home hero")
        editor.click()
        page.keyboard.press("ControlOrMeta+A")
        page.keyboard.type("Made for your day")
        page.keyboard.press("ControlOrMeta+A")
        if editor.locator("strong").count():
            page.get_by_role("button", name="Bold", exact=True).click()
            assert editor.locator("strong").count() == 0
        page.get_by_role("button", name="Bold", exact=True).click()
        page.get_by_role("combobox", name="Heading", exact=True).select_option("2")
        page.get_by_role("button", name="Link", exact=True).click()
        assert page.get_by_role("textbox", name="Link URL", exact=True).evaluate("el => el === document.activeElement")
        page.get_by_role("textbox", name="Link URL", exact=True).fill("https://example.com/shop")
        assert page.get_by_role("textbox", name="Link URL", exact=True).evaluate("el => el === document.activeElement")
        assert editor.inner_text().strip() == "Made for your day"
        page.get_by_role("button", name="Apply", exact=True).click()
        assert editor.locator("h2 strong").count() == 1, editor.inner_html()
        assert editor.locator("h2 strong").inner_text() == "Made for your day"
        assert editor.locator("a").get_attribute("href") == "https://example.com/shop"
        page.screenshot(path=f"/tmp/annotate-copy-editor-{width}-{theme}.png", full_page=True)
        state["fail_after_commit"] = True
        page.get_by_role("button", name="Propose change", exact=True).click()
        page.get_by_role("status").filter(has_text="Connection interrupted").wait_for()
        assert page.get_by_role("button", name="Propose change", exact=True).is_enabled()
        assert editor.locator("h2 strong").inner_text() == "Made for your day"
        page.reload(wait_until="networkidle")
        page.get_by_role("button", name="Continue draft", exact=True).click()
        assert page.get_by_role("textbox", name="Edit Home hero").locator("h2 strong").inner_text() == "Made for your day"
        page.get_by_role("button", name="Propose change", exact=True).click()
        page.locator(".copy-proposal[open] .copy-document h2 strong").wait_for()
        block = load_copy(directory)["blocks"][0]
        assert block["current"] == "draft-2"
        assert len(block["revisions"]) == 3
        assert state["posts"] == 2
        assert block["revisions"][-1]["author"] == {"id": "reviewer:chang", "name": "Chang"}
        assert {"bold", "link"}.issubset(block["revisions"][-1]["delta"]["ops"][0]["attributes"])
        assert block["revisions"][-1]["delta"]["ops"][-1]["attributes"]["header"] == 2
        page.locator(".copy-history > summary").click()
        page.locator(".copy-history-entry > summary").click()
        page.get_by_text("Old headline", exact=True).wait_for(state="visible")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=f"/tmp/annotate-copy-{width}-{theme}.png", full_page=True)
        page.reload(wait_until="networkidle")
        assert page.locator(".copy-history").get_attribute("open") is None
        page.locator(".copy-proposal > summary").click()
        assert page.locator(".copy-proposal .copy-document h2 strong").inner_text() == "Made for your day"
        assert not errors
        browser.close()


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_editor_paste_undo_and_attack_text_stays_safe(copy_site):
    base, _state, directory = copy_site
    with playwright.sync_playwright() as runner:
        browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
        page = browser.new_page()
        page.goto(base, wait_until="networkidle")
        page.get_by_role("button", name="Revise", exact=True).click()
        page.evaluate('''() => {
          window.attackExecuted = false;
          const q=Quill.find(document.querySelector('.copy-editor'));
          q.setSelection(0, q.getLength());
          q.clipboard.dangerouslyPasteHTML('<p><strong>Safe bold</strong> <a href="javascript:alert(1)">unsafe link</a><img src=x onerror="window.attackExecuted=true"><iframe src="javascript:alert(1)"></iframe></p>', 'user');
        }''')
        editor = page.get_by_role("textbox", name="Edit Home hero")
        assert editor.locator("strong").inner_text() == "Safe bold"
        assert editor.locator("img,iframe,script").count() == 0
        assert editor.locator('[href^="javascript:"]').count() == 0
        assert not page.evaluate("window.attackExecuted")
        page.get_by_role("button", name="Undo", exact=True).click()
        assert [line for line in editor.inner_text().splitlines() if line] == ["Everyday essentials", "Shop the collection."]
        page.get_by_role("button", name="Redo", exact=True).click()
        assert editor.locator("strong").inner_text() == "Safe bold"
        page.get_by_role("button", name="Propose change", exact=True).click()
        page.locator(".copy-proposal[open]").wait_for()
        delta = load_copy(directory)["blocks"][0]["revisions"][-1]["delta"]
        assert all(isinstance(op["insert"], str) for op in delta["ops"])
        assert not any("link" in op.get("attributes", {}) for op in delta["ops"])
        assert not page.evaluate("window.attackExecuted")
        browser.close()


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width", [1440, 390])
def test_many_copy_blocks_are_searchable_and_switching_keeps_drafts(copy_site, width):
    base, _state, directory = copy_site
    data = load_copy(directory)
    for index in range(132):
        data["blocks"].append({"id": f"field-{index}", "title": f"Product field {index:03}", "current": "draft-1",
                               "revisions": [{"id": "draft-1", "created_at": "2026-10-02T10:00:00Z",
                                              "author": {"id": "agent:copy"}, "status": "draft",
                                              "delta": {"ops": [{"insert": f"Current field {index}\n"}]}}]})
    save_copy(directory, data)
    with playwright.sync_playwright() as runner:
        browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
        page = browser.new_page(viewport={"width": width, "height": 850})
        page.set_default_timeout(4000)
        page.goto(base, wait_until="networkidle")
        assert page.locator(".copy-document").count() == 1
        assert page.locator(".copy-block-list button").count() == 133
        page.get_by_role("button", name="Revise", exact=True).click()
        editor = page.get_by_role("textbox", name="Edit Home hero")
        editor.click()
        page.keyboard.press("ControlOrMeta+End")
        page.keyboard.type(" Local draft")
        page.get_by_role("searchbox", name="Find copy").fill("Product field 129")
        assert page.locator(".copy-block-list button").count() == 1
        if width > 600:
            page.get_by_role("button", name="Product field 129", exact=True).click()
        else:
            page.get_by_role("combobox", name="Copy block", exact=True).select_option("field-129")
        assert page.locator(".copy-document").count() == 1
        assert page.locator(".copy-editor").count() == 0
        assert page.get_by_text("Current field 129", exact=True).is_visible()
        page.get_by_role("searchbox", name="Find copy").fill("")
        if width > 600:
            page.get_by_role("button", name="Home hero", exact=True).click()
        else:
            page.get_by_role("combobox", name="Copy block", exact=True).select_option("hero")
        page.get_by_role("button", name="Continue draft", exact=True).click()
        assert "Local draft" in page.get_by_role("textbox", name="Edit Home hero").inner_text()
        page.screenshot(path=f"/tmp/annotate-copy-many-{width}.png", full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.reload(wait_until="networkidle")
        page.get_by_role("button", name="Continue draft", exact=True).click()
        assert "Local draft" in page.get_by_role("textbox", name="Edit Home hero").inner_text()
        assert len(load_copy(directory)["blocks"][0]["revisions"]) == 2
        browser.close()
