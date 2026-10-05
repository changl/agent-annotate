"""Frame commands require both the expected origin and the expected WindowProxy."""

import http.server
import json
import threading
from contextlib import contextmanager

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from test_card_layout import CHROME, _serve  # noqa: E402
from test_ui_regressions import _api, _page  # noqa: E402

from agent_annotate.paths import WEB_DIR  # noqa: E402


@contextmanager
def _fixture(tmp_path, *, writable_adapter=False):
    process, base = _serve(tmp_path, _page(tmp_path))
    try:
        item = _api(
            base,
            "api/comments",
            {"anchor_id": "s:coverage", "number": 31, "version": "v1", "text": "Review coverage"},
        )
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.set_default_timeout(5000)
            page.goto(base, wait_until="networkidle")
            page.locator('body[data-ready="1"]').wait_for(state="attached")
            page.frame_locator("#content-frame").locator('[data-anchor-id="s:coverage"]').wait_for()
            if writable_adapter:
                page.frame_locator("#content-frame").locator(f'[data-pin-comments="{item["id"]}"]').wait_for()
            try:
                yield page, base, item["id"]
            finally:
                browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_shell_rejects_forged_sources_but_valid_reference_link_focuses_canonical_feedback(tmp_path):
    with _fixture(tmp_path) as (page, _base, cid):
        for foreign in (True, False):
            page.evaluate(
                """foreign => {
                const frame = document.getElementById('content-frame');
                window.dispatchEvent(new MessageEvent('message', {
                    origin: foreign ? 'https://foreign.invalid' : location.origin,
                    source: foreign ? frame.contentWindow : window,
                    data: {type:'annotate:pin-click', anchorId:'s:coverage'}
                }));
            }""",
                foreign,
            )
            assert not page.locator("#popover").is_visible()
            assert page.locator("body").get_attribute("data-view") == "review"
        frame = page.frame_locator("#content-frame")
        frame.locator("body").evaluate("() => window.openPopover('s:coverage', 100, 120)")
        page.locator("#popover").wait_for(state="visible")
        box = page.locator("#popover").bounding_box()
        assert box and 0 <= box["x"] < 1440 and 0 <= box["y"] < 900
        page.keyboard.press("Escape")
        page.locator("#popover").wait_for(state="hidden")
        frame.locator("body").evaluate(
            "(body,cid) => parent.postMessage({type:'annotate:pin-open',anchorId:'s:coverage',commentIds:[cid]}, location.origin)",
            cid,
        )
        card = page.locator(f'.citem.hl[data-comment-id="{cid}"]')
        card.wait_for(state="visible")
        assert page.locator("body").get_attribute("data-view") == "review"
        box = card.bounding_box()
        assert box and 0 <= box["x"] < 1440 and 0 <= box["y"] < 900


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_adapter_rejects_foreign_origin_and_wrong_source_then_accepts_real_parent_command(tmp_path):
    with _fixture(tmp_path, writable_adapter=True) as (page, _base, cid):
        frame = page.frame_locator("#content-frame")
        for foreign in (True, False):
            frame.locator("body").evaluate(
                """(body, foreign) => {
                window.dispatchEvent(new MessageEvent('message', {
                    origin: foreign ? 'https://foreign.invalid' : location.origin,
                    source: foreign ? window.parent : window,
                    data: {type:'annotate:comment-counts', counts:{'s:coverage':1},
                           pins:{'s:coverage':[{id:'forged',n:999}]}}
                }));
            }""",
                foreign,
            )
            assert frame.locator('[data-pin-comments="forged"]').count() == 0
            assert frame.locator(f'[data-pin-comments="{cid}"]').first.inner_text() == "31"
        page.evaluate("""() => {
            document.getElementById('content-frame').contentWindow.postMessage({
                type:'annotate:comment-counts', counts:{'s:coverage':1},
                pins:{'s:coverage':[{id:'valid-parent-command',n:32}]}
            }, location.origin);
        }""")
        pin = frame.locator('[data-pin-comments="valid-parent-command"]')
        pin.wait_for()
        assert pin.first.inner_text() == "32"


@contextmanager
def _foreign_server(app_origin, comment_id):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = (
                "<script>window.received=[];addEventListener('message',e=>received.push(e.data));"
                "parent.postMessage({type:'annotate:pin-click',anchorId:'s:coverage',x:40,y:40},"
                + json.dumps(app_origin)
                + ");"
                "parent.postMessage({type:'annotate:pin-open',anchorId:'s:coverage',commentIds:["
                + json.dumps(comment_id) + "]},"
                + json.dumps(app_origin)
                + ");</script><p>Foreign frame</p>"
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_foreign_navigation_reuses_windowproxy_but_cannot_send_commands_or_receive_feedback(tmp_path):
    with _fixture(tmp_path) as (page, base, cid), _foreign_server(base.rstrip("/"), cid) as foreign:
        page.evaluate(
            """url => {
            const frame = document.getElementById('content-frame');
            window.originalProxy = frame.contentWindow;
            frame.src = url;
        }""",
            foreign,
        )
        frame = page.frame_locator("#content-frame")
        frame.locator("p").filter(has_text="Foreign frame").wait_for()
        assert page.evaluate("originalProxy === document.getElementById('content-frame').contentWindow")
        assert not page.locator("#popover").is_visible()
        assert page.locator("#pin-popover").is_hidden()
        assert page.locator("body").get_attribute("data-view") == "review"
        page.locator("#theme-toggle").click()
        page.wait_for_timeout(100)
        assert frame.locator("body").evaluate("() => window.received") == []


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_srcdoc_inherits_exact_bridge_origin_and_preserves_two_way_commands(tmp_path):
    with _fixture(tmp_path) as (page, _base, cid):
        page.evaluate("""() => {
            const frame = document.getElementById('content-frame');
            frame.srcdoc = frame.contentDocument.documentElement.outerHTML;
        }""")
        frame = page.frame_locator("#content-frame")
        frame.locator('[data-anchor-id="s:coverage"]').wait_for()
        assert frame.locator("body").evaluate("() => location.origin") == "null"
        page.evaluate(
            "() => document.getElementById('content-frame').contentWindow.postMessage({type:'annotate:theme',theme:'light'}, location.origin)"
        )
        playwright.expect(frame.locator("html")).to_have_attribute("data-theme", "light")
        frame.locator("body").evaluate(
            "(body,cid) => parent.postMessage({type:'annotate:pin-open',anchorId:'s:coverage',commentIds:[cid]}, parent.location.origin)",
            cid,
        )
        page.locator(f'.citem.hl[data-comment-id="{cid}"]').wait_for(state="visible")
        assert page.locator("body").get_attribute("data-view") == "review"
        assert page.locator("#popover").is_hidden()


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_shell_nested_under_srcdoc_retains_inherited_security_origin(tmp_path):
    with _fixture(tmp_path) as (page, _base, cid):
        shell = page.evaluate("() => fetch(location.href).then(response => response.text())")
        page.evaluate("""() => {
            document.getElementById('content-frame').srcdoc = '<iframe id="nested-shell"></iframe>';
        }""")
        outer = page.frame_locator("#content-frame")
        outer.locator("#nested-shell").evaluate("(frame, html) => frame.srcdoc = html", shell)
        nested = outer.frame_locator("#nested-shell")
        nested.locator('body[data-ready="1"]').wait_for(state="attached")
        content = nested.frame_locator("#content-frame")
        content.locator('[data-anchor-id="s:coverage"]').wait_for()
        assert nested.locator("body").evaluate("() => location.origin") == "null"
        content.locator("body").evaluate(
            "(body,cid) => parent.postMessage({type:'annotate:pin-open',anchorId:'s:coverage',commentIds:[cid]}, parent.origin)",
            cid,
        )
        nested.locator(f'.citem.hl[data-comment-id="{cid}"]').wait_for(state="visible")
        assert nested.locator("body").get_attribute("data-view") == "review"
        assert nested.locator("#popover").is_hidden()


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_opaque_srcdoc_fails_closed_without_wildcard_parent_exports(tmp_path):
    with _fixture(tmp_path) as (page, _base, _cid):
        adapter = (WEB_DIR / "adapter.js").read_text().replace("</script", "<\\/script")
        document = (
            '<p data-anchor-id="s:opaque">Opaque canvas</p>'
            '<script type="application/json" id="anchor-registry-data">{"s:opaque":{"name":"Opaque"}}</script>'
            "<script>" + adapter + "</script>"
        )
        page.evaluate(
            """html => {
            window.opaqueMessages = [];
            addEventListener('message', e => {
                if (e.origin === 'null' && e.data && String(e.data.type).startsWith('annotate:')) opaqueMessages.push(e.data.type);
            });
            const frame = document.getElementById('content-frame');
            frame.setAttribute('sandbox', 'allow-scripts');
            frame.srcdoc = html;
        }""",
            document,
        )
        frame = page.frame_locator("#content-frame")
        frame.locator('[data-anchor-id="s:opaque"]').wait_for()
        frame.locator("body").evaluate("() => window.openPopover('s:opaque', 50, 50)")
        page.wait_for_timeout(100)
        assert page.evaluate("opaqueMessages") == []
        assert not page.locator("#popover").is_visible()


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_shell_posts_only_to_exact_bridge_origin(tmp_path):
    with _fixture(tmp_path) as (page, base, cid):
        page.evaluate("""() => {
            const frame=document.getElementById('content-frame');
            const original=frame.contentWindow.postMessage.bind(frame.contentWindow);
            window.bridgeTargets=[];
            frame.contentWindow.postMessage=(message,target,...rest)=>{
                bridgeTargets.push({type:message.type,target});
                return original(message,target,...rest);
            };
        }""")
        page.locator("#theme-toggle").click()
        page.locator(f'.citem[data-comment-id="{cid}"]').click()
        page.wait_for_function(
            "() => bridgeTargets.some(m=>m.type==='annotate:theme') && bridgeTargets.some(m=>m.type==='annotate:scroll-to')"
        )
        targets = page.evaluate("bridgeTargets")
        assert len(targets) >= 2
        assert {m["target"] for m in targets} == {base.rstrip("/")}
