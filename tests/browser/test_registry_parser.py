"""Registry labels remain data across the browser's script tokenization states."""

import json

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from test_card_layout import CHROME  # noqa: E402

from agent_annotate.extract import build_content_document  # noqa: E402
from agent_annotate.pagegen import generate  # noqa: E402
from agent_annotate.paths import WEB_DIR  # noqa: E402


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("label", ["<!--<script></script>", "<!--<ScRiPt></ScRiPt>",
                                   "</script><script>window.__registry_probe=1</script>"])
def test_legacy_registry_is_parseable_and_following_adapter_executes(label):
    registry = {"s:one": {"name": label}}
    encoded = json.dumps(registry).replace("<", "\\u003c")
    baked = ('<html><head><title>Legacy review</title></head><body>'
             '<!-- CANVAS CONTENT --><p data-anchor-id="s:one">Safe canvas</p><!-- END CANVAS CONTENT -->'
             '<script>const ANCHOR_REGISTRY = ' + encoded + ';</script></body></html>')
    content = build_content_document(baked)
    adapter = (WEB_DIR / "adapter.js").read_text().replace("</script", "<\\/script")
    content = content.replace('</body>', '<script>' + adapter + '</script>'
                              '<script>window.__adapter_canary = typeof window.openPopover === "function";</script></body>')
    with playwright.sync_playwright() as runner:
        browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
        page = browser.new_page()
        page.set_content(content, wait_until="load")
        assert page.evaluate('JSON.parse(document.getElementById("anchor-registry-data").textContent)') == registry
        assert page.evaluate("window.__adapter_canary") is True
        assert page.evaluate("typeof window.__registry_probe") == "undefined"
        browser.close()


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_generated_standalone_registry_survives_double_escape_label(tmp_path):
    source = tmp_path / "page.md"
    source.write_text("---\ntitle: Registry parser review\n---\n\n## Coverage <!--<script></script>\n\nSafe text.\n")
    generated = generate(source, tmp_path / "review")
    baked = generated["html"].read_text()
    with playwright.sync_playwright() as runner:
        browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
        page = browser.new_page()
        page.set_content(baked, wait_until="load")
        assert page.evaluate("typeof ANCHOR_REGISTRY") == "object"
        registry = page.evaluate("ANCHOR_REGISTRY")
        assert any("<!--<script></script>" in item["name"] for item in registry.values())
        assert page.locator("#canvas-wrapper").is_visible()
        browser.close()
