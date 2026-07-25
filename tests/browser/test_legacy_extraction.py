"""A baked legacy slug is served through the universal shell.

Chrome baked into versions/<v>.html at generation time is why a fix to the
artifact chrome never reached an already-published page. The server now
recovers the author's canvas from the baked file at request time and serves it
through the shell, so chrome comes from the skill dir on every request — a
legacy page picks up the current adapter.js with no file regenerated and no
duplicate written to disk.

These tests use a slug whose only content is a BAKED artifact: versions/ only,
no content/ directory.
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

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
TEMPLATE = Path(__file__).parents[2] / "src" / "agent_annotate" / "web" / "template.html"

CANVAS = """
<div class="no" id="s:demo:prose">
  <h2>Prose</h2>
  <p id="plain-para">Plain prose stays annotatable.</p>
  <button id="legacy-openpopover" onclick="if(typeof openPopover==='function')openPopover('s:demo:prose',10,10)">Comment</button>
</div>
<div class="no" id="s:demo:controls">
  <h2>Controls</h2>
  <select id="demo-select"><option value="a">Alpha</option><option value="b">Bravo</option></select>
  <input id="demo-input" type="text" value="typed">
</div>
"""

REGISTRY = {"s:demo:prose": {"name": "Prose"}, "s:demo:controls": {"name": "Controls"}}


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _bake(tmp_path):
    """Produce a slug containing only a baked artifact — no content/ dir."""
    html = TEMPLATE.read_text(encoding="utf-8")
    for token, value in {
        "{{CANVAS}}": CANVAS,
        "{{ANCHOR_REGISTRY}}": json.dumps(REGISTRY),
        "{{DOC_ID}}": "baked-demo",
        "{{VERSION}}": "v1",
        "{{TITLE}}": "Baked demo",
        "{{SUBTITLE}}": "extraction fixture",
        "{{DATE}}": "2026-07-25",
        "{{LEGEND}}": "",
    }.items():
        html = html.replace(token, value)

    slug_dir = tmp_path / "baked"
    (slug_dir / "versions").mkdir(parents=True)
    (slug_dir / "versions" / "v1.html").write_text(html, encoding="utf-8")
    (slug_dir / "current.html").write_text(html, encoding="utf-8")
    (slug_dir / "current.meta.json").write_text(
        json.dumps({"current": "v1", "history": [{"version": "v1", "ts": "", "label": ""}]}),
        encoding="utf-8",
    )
    (slug_dir / "comments.json").write_text(
        json.dumps({"schema_version": 2, "anchors": {}, "archived": {}}), encoding="utf-8"
    )
    assert not (slug_dir / "content").exists()
    return slug_dir


def _serve(tmp_path):
    slug_dir = _bake(tmp_path)
    port = _free_port()
    env = os.environ.copy()
    env["ANNOTATE_STATE_DIR"] = str(tmp_path / "state")
    process = subprocess.Popen(
        [
            sys.executable, "-m", "agent_annotate.sync_server",
            "--slug-dir", str(slug_dir),
            "--slug", "baked",
            "--bus-dir", str(tmp_path / "bus"),
            "--port", str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    base = f"http://127.0.0.1:{port}/"
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            urllib.request.urlopen(base, timeout=1).close()
            break
        except OSError:
            time.sleep(0.05)
    else:
        process.terminate()
        raise AssertionError("server did not become ready")
    return process, base, slug_dir


def test_baked_slug_serves_shell_and_extracted_content(tmp_path):
    process, base, slug_dir = _serve(tmp_path)
    try:
        root = urllib.request.urlopen(base, timeout=5).read().decode()
        # Root is the universal shell, not the baked page.
        assert 'id="drawer"' in root
        assert 'id="content-frame"' in root

        content = urllib.request.urlopen(base + "content?v=v1", timeout=5).read().decode()
        # The author's canvas survived.
        assert 'id="s:demo:prose"' in content
        assert 'id="demo-select"' in content
        # The registry was re-encoded into the form adapter.js reads.
        assert 'id="anchor-registry-data"' in content
        assert "s:demo:prose" in content
        # adapter.js was injected.
        assert "adapter.js" in content
        # None of the baked chrome came along.
        assert 'id="popover"' not in content
        assert 'class="panel"' not in content
        assert "const ANCHOR_REGISTRY" not in content

        # Extraction writes nothing to disk — that is what keeps it universal.
        assert not (slug_dir / "content").exists()
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_explicit_content_doc_wins_over_extraction(tmp_path):
    """A hand-tuned content/<v>.html must never be overridden."""
    process, base, slug_dir = _serve(tmp_path)
    try:
        (slug_dir / "content").mkdir()
        (slug_dir / "content" / "v1.html").write_text(
            "<!doctype html><html><body><div id='hand-tuned'>explicit</div></body></html>",
            encoding="utf-8",
        )
        content = urllib.request.urlopen(base + "content?v=v1", timeout=5).read().decode()
        assert "hand-tuned" in content
        assert 'id="s:demo:prose"' not in content
    finally:
        process.terminate()
        process.wait(timeout=5)


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
def test_baked_slug_is_annotatable_through_the_shell(tmp_path):
    process, base, _ = _serve(tmp_path)
    try:
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(
                viewport={"width": 1280, "height": 800},
                extra_http_headers={
                    "Cf-Access-Authenticated-User-Email": "reviewer@example.com",
                    "Cf-Access-Authenticated-User-Name": "Browser Reviewer",
                },
            )
            page.set_default_timeout(5_000)
            page.goto(base, wait_until="networkidle")
            frame = page.frame_locator("#content-frame")
            popover = page.locator("#pop-ta")

            # Plain content still comments.
            frame.locator("#plain-para").click()
            popover.wait_for(state="visible")
            page.keyboard.press("Escape")
            page.wait_for_timeout(200)

            # The interactive-control fix now applies to this legacy page
            # WITHOUT its baked chrome being patched — the whole point.
            frame.locator("#demo-input").click()
            page.wait_for_timeout(200)
            assert not popover.is_visible()
            frame.locator("#demo-select").select_option("b")
            assert frame.locator("#demo-select").input_value() == "b"

            # In-canvas openPopover() affordances still work via the shim.
            frame.locator("#legacy-openpopover").click()
            popover.wait_for(state="visible")

            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
