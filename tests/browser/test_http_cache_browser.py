"""A real image page reuses immutable assets and only revalidates mutable files."""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from test_card_layout import _serve

from agent_annotate.pagegen import generate

playwright = pytest.importorskip("playwright.sync_api")


def test_second_page_load_reuses_assets_and_revalidates_images(tmp_path):
    # Use the existing installed browser without changing the shared installation.
    executable = os.environ.get("ANNOTATE_TEST_BROWSER")
    if not executable:
        executable = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if not Path(executable).exists():
        pytest.skip("Browser executable is unavailable")
    from test_pagegen_images import png

    (tmp_path / "photo.png").write_bytes(png(390, 844, (180, 200, 220)))
    directory = tmp_path / "review"
    (directory / "attachments").mkdir(parents=True)
    (directory / "attachments/plain.png").write_bytes((tmp_path / "photo.png").read_bytes())
    card = {"number": 1, "anchor_id": "d:q1", "text": "Ship this image?", "decision_request": {
        "prompt": "Ship this image?", "recommendation": "ship",
        "options": [{"id": "ship", "label": "Ship"}, {"id": "hold", "label": "Hold"}],
        "evidence": [{"label": "Image", "anchor": "fig:photo"}]}}
    source = tmp_path / "page.md"
    source.write_text('---\ntitle: Cache smoke\n---\n\n## Photo\n\n![Photo](photo.png)\n\n'
                      '![Proof](attachments/plain.png)\n\n'
                      '## Questions\n\n```cards\n' + json.dumps([card]) + '\n```\n')
    generate(source, directory)
    process, base = _serve(tmp_path, directory)
    try:
        request = urllib.request.Request(base + "api/comments/batch", method="POST",
                                        data=json.dumps({"items": [dict(card, version="v1")]}).encode(),
                                        headers={"Content-Type": "application/json", "X-Annotate-Agent": "agent:cache-smoke"})
        try:
            urllib.request.urlopen(request).close()
        except urllib.error.HTTPError as error:
            pytest.fail(error.read().decode())
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=executable, headless=True)
            page = browser.new_page()
            page.set_default_timeout(15_000)
            session = page.context.new_cdp_session(page)
            session.send("Network.enable")
            responses = []
            session.on("Network.responseReceived", lambda event: responses.append(event["response"]))

            def loaded():
                page.locator('body[data-ready="1"]').wait_for(state="attached")
                frame = page.frame_locator("#content-frame")
                frame.locator("img").first.wait_for()
                frame.locator("body").evaluate("async () => { await Promise.all([...document.images].map(i => i.decode())); }")
                page.wait_for_load_state("networkidle")
                assert frame.locator(".annotate-decision-strip").count() > 0
                return page.evaluate("performance.getEntriesByType('resource').map(r => ({url:r.name, bytes:r.transferSize}))") + frame.locator("body").evaluate(
                    "() => performance.getEntriesByType('resource').map(r => ({url:r.name, bytes:r.transferSize}))")

            page.goto(base + "#view=review", wait_until="commit")
            cold = loaded()
            assert any("/assets/" in resource["url"] and resource["bytes"] > 0 for resource in cold)
            responses.clear()
            page.reload(wait_until="commit")
            warm = loaded()
            immutable = [resource for resource in warm if "/assets/" in resource["url"]]
            assert immutable and all(resource["bytes"] == 0 for resource in immutable)
            image = [response for response in responses if response["url"].endswith("attachments/plain.png")]
            assert image and all(response["status"] == 304 for response in image)
            # Revalidating JS/HTML still allows the shell to render its card.
            assert not [response for response in responses if response["status"] >= 400]
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
