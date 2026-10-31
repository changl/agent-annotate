"""Long pages in the browser: Earlier updates opens on demand, Full size, History in pages of 20, archives in Open project."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from agent_annotate import long_pages  # noqa: E402
from agent_annotate.categories import publish_plan_revision  # noqa: E402
from agent_annotate.pagegen import generate  # noqa: E402

sys.path.insert(0, str(Path(__file__).parents[1]))
from test_pagegen_images import png, write  # noqa: E402

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _page(tmp_path, monkeypatch) -> Path:
    real = long_pages.subprocess.run

    def sips(command, **kwargs):
        if command[0] != "/usr/bin/sips":
            return real(command, **kwargs)
        Path(command[-1]).write_bytes(png(600, 400))
        return type("Done", (), {"returncode": 0})()
    monkeypatch.setattr(long_pages.shutil, "which", lambda name: "/usr/bin/sips")
    monkeypatch.setattr(long_pages.subprocess, "run", sips)
    write(tmp_path / "shots" / "wide.png", png(2400, 1600, (40, 120, 200)))
    slug = tmp_path / "long"
    for n in range(1, 26):
        text = "Changed again." if n > 1 else "First."
        source = tmp_path / f"v{n}.md"
        source.write_text("---\ntitle: Long\nother_files_required: none\n---\n\n"
                          "## Alpha\n\nFinished work.\n\n![Board](shots/wide.png)\n\n"
                          f"## Beta\n\n{text} {n}\n", encoding="utf-8")
        generate(source, slug, version=f"v{n}")
    meta = json.loads((slug / "current.meta.json").read_text())
    meta["current"] = "v25"
    meta["history"] = [{"version": f"v{n}", "ts": f"2026-10-{n + 1:02d}T10:00:00Z", "label": f"Round {n}"}
                       for n in range(1, 26)]
    (slug / "current.meta.json").write_text(json.dumps(meta))
    publish_plan_revision(slug, "archive-2026-10-20", "<!DOCTYPE html><html><body><p>old</p></body></html>",
                          title="Archive Oct 2–20 · Gamma", section="archive")
    path = slug / "plans" / "archive-2026-10-20" / "meta.json"
    path.write_text(json.dumps({**json.loads(path.read_text()),
                                "archive": {"sections": 3, "screenshots": 4, "from": "2026-10-02", "to": "2026-10-20"}}))
    return slug


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_earlier_updates_full_size_history_and_archives(tmp_path, monkeypatch):
    slug = _page(tmp_path, monkeypatch)
    html = (slug / "versions" / "v25.html").read_text()
    assert '<details class="aa-earlier"' in html and 'class="aa-full"' in html
    port = _free_port()
    sandbox = Path(tempfile.mkdtemp(prefix="long-pages-browser-", dir=tmp_path))
    env = os.environ.copy()
    env.update({name: str(sandbox / name.lower()) for name in (
        "ANNOTATE_STATE_DIR", "ANNOTATE_BUS_ROOT", "ANNOTATE_CONFIG_DIR", "ANNOTATE_DATA_DIR", "ANNOTATE_BUS_ARCHIVE_ROOT")})
    env["ANNOTATE_CLAUDE_SETTINGS"] = str(sandbox / "claude" / "settings.json")
    env["ANNOTATE_SHIM_PATH"] = str(sandbox / "bin" / "annotate")
    process = subprocess.Popen(
        [sys.executable, "-m", "agent_annotate.sync_server", "--slug-dir", str(slug), "--slug", "long",
         "--bus-dir", str(sandbox / "bus"), "--port", str(port), "--local-author", "reviewer@example.com"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        base = f"http://127.0.0.1:{port}/"
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                urllib.request.urlopen(base, timeout=1).close()
                break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError(f"sync server did not come up on port {port}")
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.set_default_timeout(10_000)
            page.goto(base + "#view=review", wait_until="networkidle")
            page.locator('body[data-ready="1"]').wait_for(state="attached")
            frame = page.frame_locator("#content-frame")
            frame.locator("details.aa-earlier").wait_for(state="attached")
            # Folded: nothing of Alpha is built, so its screenshot is never requested.
            assert frame.locator('[data-anchor-id="s:alpha"]').count() == 0
            assert frame.locator("img").count() == 0
            # A jump into the fold opens it.
            page.evaluate("""() => document.getElementById('content-frame').contentWindow.postMessage(
                {type: 'annotate:scroll-to', anchorId: 's:alpha'}, location.origin)""")
            frame.locator('[data-anchor-id="s:alpha"]').wait_for()
            assert frame.locator("details.aa-earlier").get_attribute("open") is not None
            img = frame.locator("img")
            assert img.get_attribute("src").startswith("assets/preview/") and img.get_attribute("loading") == "lazy"
            link = frame.locator("a.aa-full")
            assert link.get_attribute("href") == img.get_attribute("data-full") and link.get_attribute("target") == "_blank"

            page.evaluate("() => window.AA.rail.reveal('history')")
            rows = page.locator("#vrail-body-review .vrow")
            rows.first.wait_for()
            assert rows.count() == 20
            page.locator("#vrail-body-review .vrail-more").click()
            assert rows.count() == 25 and page.locator("#vrail-body-review .vrail-more").count() == 0

            page.evaluate("() => window.AA.rail.reveal('documents')")
            docs = page.locator("#documents-body")
            docs.get_by_text("Archive Oct 2–20 · Gamma").wait_for()
            assert "Finished · 3 sections · 4 screenshots" in docs.inner_text()
            assert "this page" in docs.inner_text()
            assert page.locator("#view-hd-plan option[value='archive-2026-10-20']").count() == 0
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=10)
