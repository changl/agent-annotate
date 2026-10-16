"""Page HTML can render scripts without gaining the review page's authority."""

import base64
import json
import os
from pathlib import Path

import pytest
from test_card_layout import _serve
from test_pagegen_images import png

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


@pytest.mark.parametrize("suffix", [".html", ".htm"])
def test_html_asset_renders_but_cannot_access_cookie_api_or_top(tmp_path, suffix):
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
              const response = await fetch('/api/seen?asset-probe=1', {method, credentials: 'include',
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
    process, base = _serve(tmp_path, directory)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=executable, headless=True)
            page = browser.new_page()
            page.add_init_script("""window.addEventListener('message', event => {
              if (event.data?.type === 'asset-probe') window.assetProbe = {...event.data, messageOrigin: event.origin};
            });""")
            page.context.add_cookies([{"name": "page_cookie", "value": "private-review-session", "url": base}])
            # CORS failures hide response events from page JS and Playwright;
            # CDP's extra-info events still expose the server's actual verdict.
            session = page.context.new_cdp_session(page)
            session.send("Network.enable")
            requests, statuses = {}, {}
            session.on("Network.requestWillBeSent", lambda event: requests.update({event["requestId"]: event["request"]})
                       if event["request"]["url"] == base + "api/seen?asset-probe=1" else None)
            session.on("Network.responseReceivedExtraInfo", lambda event: statuses.update({event["requestId"]: event["statusCode"]}))
            page.goto(base + "#view=review", wait_until="commit")
            page.wait_for_function("window.assetProbe")
            asset = page.frame_locator("#content-frame").frame_locator("#plan")
            assert asset.locator("#rendered").inner_text() == "Plan script rendered"
            assert page.evaluate("window.assetProbe") == {
                "type": "asset-probe", "origin": "null", "messageOrigin": "null",
                "cookie": "SecurityError", "parentCookie": "SecurityError", "topNavigation": "SecurityError",
                "GET": "TypeError", "POST": "TypeError",
                "omit": {"proof": "loaded"}, "include": "TypeError", "xhr": {"proof": "loaded"},
            }
            assert asset.locator("#proof").evaluate("async image => { await image.decode(); return [image.naturalWidth, image.naturalHeight]; }") == [32, 16]
            assert asset.locator("#demo").evaluate("async video => { await video.play(); video.pause(); return [video.videoWidth, video.videoHeight]; }") == [32, 16]
            assert page.evaluate("document.cookie") == "page_cookie=private-review-session"
            assert "escaped" not in page.url
            assert {request["method"]: statuses[key] for key, request in requests.items()} == {"GET": 403, "POST": 403}
            seen = page.evaluate("async () => (await fetch('/api/seen')).json()")
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
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
