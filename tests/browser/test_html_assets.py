"""Page HTML can render scripts without gaining the review page's authority."""

import json
import os
from pathlib import Path

import pytest
from test_card_layout import _serve

playwright = pytest.importorskip("playwright.sync_api")


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
    (directory / "assets/v2" / ("plan" + suffix)).write_text("""<html><body>
        <h1 id="rendered">Waiting for script</h1><script>
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
            }
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
