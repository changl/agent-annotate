"""Page HTML can render scripts without gaining the review page's authority."""

import base64
import json
import os
import ssl
import subprocess
import threading
from contextlib import contextmanager
from http.cookies import SimpleCookie
from pathlib import Path

import pytest
from test_pagegen_images import png

from agent_annotate import cli, review_access
from agent_annotate.sync_server import WEB_DIR, ReviewHTTPServer, make_handler

playwright = pytest.importorskip("playwright.sync_api")

# Two blue 32x16 VP8 frames in WebM; no runtime encoder dependency.
VIDEO = base64.b64decode(
    "GkXfo59ChoEBQveBAULygQRC84EIQoKEd2VibUKHgQJChYECGFOAZwEAAAAAAAIZEU2bdLpNu4tTq4QVSalmU6yBoU27i1Or"
    "hBZUrmtTrIHYTbuMU6uEElTDZ1OsggElTbuMU6uEHFO7a1OsggID7AEAAAAAAABZAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAVSalmsirX"
    "sYMPQkBNgI1MYXZmNjIuMTIuMTAxV0GNTGF2ZjYyLjEyLjEwMUSJiECPQAAAAAAAFlSua8iuAQAAAAAAAD/XgQFzxYjw5cqI"
    "g9xE/JyBACK1nIN1bmSIgQCGhVZfVlA4g4EBI+ODhB3NZQDgkLCBILqBEJqBAlWwhFW5gQESVMNn/HNzoGPAgGfImkWjh0VO"
    "Q09ERVJEh41MYXZmNjIuMTIuMTAxc3PWY8CLY8WI8OXKiIPcRPxnyKFFo4dFTkNPREVSRIeUTGF2YzYyLjI4LjEwMSBsaWJ2"
    "cHhnyKFFo4hEVVJBVElPTkSHkzAwOjAwOjAxLjAwMDAwMDAwMAAfQ7Z12OeBAKO8gQAAgLACAJ0BKiAAEAAARwiFhYiFhIgC"
    "AgJ1qgP4AgnCFQD+/00S//xYV/FhX8WFf/FhX/z8zu3F/OYAo5WBAfQAsQEABRCsABgAGFgv9AAIQAAcU7trkbuPs4EAt4r3"
    "gQHxggGm8IED"
)


@contextmanager
def _asset_server(tmp_path, directory, https):
    """Record real server responses for local HTTP or sandboxed Funnel-style TLS."""
    key = review_access.ensure_key(directory) if https else None
    handler = make_handler(directory, public_base_path="/review" if https else "", slug="page",
                           v2_mode=True, skill_dir=WEB_DIR,
                           local_author=None if https else "reviewer@example.com",
                           local_author_name=None if https else "Browser Reviewer")
    observed = []

    def record_response(self, code, size="-"):
        cookies = SimpleCookie()
        cookies.load(self.headers.get("Cookie") or "")
        observed.append({"path": self.path, "cookies": list(cookies), "referer": self.headers.get("Referer"),
                         "mode": self.headers.get("Sec-Fetch-Mode"), "method": self.command,
                         "status": code, "origin": self.headers.get("Origin")})

    handler.log_request = record_response
    httpd = ReviewHTTPServer(("127.0.0.1", 0), handler)
    if https:
        tls = tmp_path / "tls"
        tls.mkdir(exist_ok=True)
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                        "-subj", "/CN=review.test", "-keyout", str(tls / "key.pem"), "-out", str(tls / "cert.pem")],
                       check=True, capture_output=True, timeout=15)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(tls / "cert.pem", tls / "key.pem")
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    project = f"tls-html-{httpd.server_port}"
    handler.bus_dir = cli.BUS_ROOT / project
    handler.bus_dir.mkdir(parents=True, exist_ok=True)
    base = f"https://review.test:{httpd.server_port}/review/" if https else f"http://127.0.0.1:{httpd.server_port}/"
    if https:
        cli._save_state_for_project(project, {"project": project, "slugs": {"page": {
            "slug_dir": str(directory), "port": httpd.server_port, "transport": "funnel", "url": base}}})
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield base, key, observed
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("suffix", [".html", ".htm"])
@pytest.mark.parametrize("https", [False, True])
def test_html_asset_renders_but_cannot_access_cookie_api_or_top(tmp_path, suffix, https):
    executable = os.environ.get("ANNOTATE_TEST_BROWSER", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not Path(executable).exists():
        pytest.skip("Browser executable is unavailable")
    directory = tmp_path / "review"
    (directory / "content").mkdir(parents=True)
    (directory / "assets/v2").mkdir(parents=True)
    (directory / "attachments").mkdir()
    html = f'<html><body><iframe id="plan" src="assets/v2/plan{suffix}"></iframe></body></html>'
    (directory / "current.html").write_text(html)
    (directory / "content/v1.html").write_text(html)
    (directory / "current.meta.json").write_text('{"current":"v1","history":[{"version":"v1"}]}')
    (directory / "comments.json").write_text('{"schema_version":2,"anchors":{},"archived":{}}')
    (directory / "assets/v2/proof.png").write_bytes(png(32, 16, (40, 80, 200)))
    (directory / "assets/v2/demo.webm").write_bytes(VIDEO)
    (directory / "assets/v2/manifest.json").write_text('{"proof":"loaded"}')
    (directory / "assets/v2" / ("plan" + suffix)).write_text("""<html><body>
        <h1 id="rendered">Waiting for script</h1>
        <img id="proof" src="proof.png"><video id="demo" src="demo.webm" preload="auto" muted></video>
        <script>
        (async () => {
          const result = {type: 'asset-probe', origin: self.origin};
          document.querySelector('#rendered').textContent = 'Plan script rendered';
          for (const [key, action] of Object.entries({
            cookie: () => document.cookie,
            parentCookie: () => parent.document.cookie,
            topNavigation: () => { top.location.href = '/?escaped=1'; }
          })) {
            try { result[key] = action(); } catch (error) { result[key] = error.name; }
          }
          for (const method of ['GET', 'POST']) {
            try {
              const response = await fetch(new URL('../../api/seen?asset-probe=1', location.href), {method, credentials: 'include',
                ...(method === 'POST' ? {headers: {'Content-Type': 'text/plain'},
                  body: JSON.stringify({version: 'asset-attack'})} : {})});
              result[method] = await response.text();
            } catch (error) { result[method] = error.name; }
          }
          for (const credentials of ['omit', 'include']) {
            try {
              result[credentials] = await (await fetch('manifest.json', {credentials})).json();
            } catch (error) { result[credentials] = error.name; }
          }
          result.xhr = await new Promise(resolve => {
            const xhr = new XMLHttpRequest(); xhr.open('GET', 'manifest.json');
            xhr.onload = () => resolve(JSON.parse(xhr.responseText)); xhr.onerror = () => resolve('blocked');
            xhr.send();
          });
          top.postMessage(result, '*');
        })();
        </script></body></html>""")
    (directory / "attachments" / ("proof" + suffix)).write_text("<script>top.location.href = '/?escaped=1';</script>")
    server = _asset_server(tmp_path, directory, https)
    base, key, observed = server.__enter__()
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=executable, headless=True,
                                            args=["--host-resolver-rules=MAP review.test 127.0.0.1", "--no-proxy-server"])
            page = browser.new_page(ignore_https_errors=True)
            page.add_init_script("""window.addEventListener('message', event => {
              if (event.data?.type === 'asset-probe') window.assetProbe = {...event.data, messageOrigin: event.origin};
            });""")
            page.context.add_cookies([{"name": "page_cookie", "value": "private-review-session", "url": base}])
            if https:
                page.goto(base, wait_until="networkidle")
                assert page.evaluate("async key => (await fetch('api/reviewer/session', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({key})})).status", key) == 200
                page.reload(wait_until="commit")
            else:
                page.goto(base + "#view=review", wait_until="commit")
            page.wait_for_function("window.assetProbe")
            asset = page.frame_locator("#content-frame").frame_locator("#plan")
            assert asset.locator("#rendered").inner_text() == "Plan script rendered"
            assert page.evaluate("window.assetProbe") == {
                "type": "asset-probe", "origin": "null", "messageOrigin": "null",
                "cookie": "SecurityError", "parentCookie": "SecurityError", "topNavigation": "SecurityError",
                "GET": "TypeError", "POST": "TypeError",
                "omit": "TypeError", "include": "TypeError", "xhr": "blocked",
            }
            if https:
                media = [request for request in observed if request["path"].endswith(("/proof.png", "/demo.webm"))]
                assert media and all(review_access.asset_cookie_name(directory) in request["cookies"] for request in media), media
                assert all(review_access.cookie_name(directory) not in request["cookies"] for request in media), media
            assert asset.locator("#proof").evaluate("async image => { await image.decode(); return [image.naturalWidth, image.naturalHeight]; }") == [32, 16]
            assert asset.locator("#demo").evaluate("async video => { await video.play(); video.pause(); return [video.videoWidth, video.videoHeight]; }") == [32, 16]
            assert page.evaluate("document.cookie") == "page_cookie=private-review-session"
            assert "escaped" not in page.url
            # CORS hides responses from JS; an out-of-process sandboxed iframe's
            # requests also bypass page-level CDP sessions. Observe the server.
            probes = [request for request in observed if request["path"].endswith("/api/seen?asset-probe=1")]
            assert {request["method"]: request["status"] for request in probes} == {"GET": 403, "POST": 403}, probes
            assert all(request["status"] == 403 and request["origin"] == "null" for request in probes), probes
            seen = page.evaluate("async () => (await fetch('api/seen')).json()")
            assert "asset-attack" not in json.dumps(seen)

            page.evaluate("""suffix => {
              const link = document.createElement('a'); link.id = 'download-proof';
              link.href = 'attachments/proof' + suffix; link.textContent = 'Download proof';
              document.body.append(link);
            }""", suffix)
            with page.expect_download() as event:
                page.locator("#download-proof").click()
            download = event.value
            assert download.suggested_filename == "proof" + suffix
            assert download.failure() is None
            assert "escaped" not in page.url
            page.evaluate("""() => {
              const link = document.createElement('a'); link.id = 'manifest-download';
              link.href = 'assets/v2/manifest.json'; link.textContent = 'Download manifest'; document.body.append(link);
            }""")
            with page.expect_download() as event:
                page.locator("#manifest-download").click()
            assert Path(event.value.path()).read_text() == '{"proof":"loaded"}'
            browser.close()
    finally:
        server.__exit__(None, None, None)
