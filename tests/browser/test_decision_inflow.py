"""A posed question's controls sit in the page flow, right under its content.

Chang, 2026-10-09: "let's get this updated properly so that i can view the
images, then press the recommended or other options and/or type in my
comments as i would with any other feedback item." A build that collected
every question into one list above the page, with the body cards hidden, put
the buttons ahead of the pictures they ask about.
"""

import base64
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

from agent_annotate.pagegen import generate  # noqa: E402

CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

# A 1x1 PNG, scaled by width/height so the picture has a real box.
PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

PAGE = """---
title: In-flow questions
---

## Intro

A short opening paragraph that sits above every picture.

## Route drawn on open

The design draws the road route as soon as Route opens.

```cards
[{"number":1,"anchor_id":"d:q1","decision_request":{"prompt":"Draw the road route as soon as Route opens?","recommendation":"yes","options":[{"id":"yes","label":"Yes","style":"primary"},{"id":"yes-change","label":"Yes, with a change"},{"id":"no","label":"No"},{"id":"comment","label":"Answer in words"}],"evidence":[{"label":"the design","anchor":"s:route-drawn-on-open"}]}}]
```

## Legs and publish wording

Each leg shows distance and time.

```cards
[{"number":2,"anchor_id":"d:q2","decision_request":{"prompt":"Do the legs and the publish wording look right?","recommendation":"looks-right","options":[{"id":"looks-right","label":"Looks right","style":"primary"},{"id":"off","label":"Something is off"},{"id":"comment","label":"Answer in words"}],"evidence":[{"label":"the legs","anchor":"s:legs-and-publish-wording"}]}}]
```
"""


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _with_pictures(slug_dir):
    """Put a picture between each item's text and its card, as a review page does."""
    (slug_dir / "assets").mkdir(exist_ok=True)
    (slug_dir / "assets" / "pic.png").write_bytes(PIXEL)
    html_path = slug_dir / "versions" / "v1.html"
    html = html_path.read_text(encoding="utf-8")
    for section in ("route-drawn-on-open", "legs-and-publish-wording"):
        marker = f'<p class="lede" data-anchor-id="s:{section}:p1">'
        head, tail = html.split(marker, 1)
        paragraph, rest = tail.split("</p>", 1)
        figure = (
            f'<figure data-anchor-id="s:{section}:fig1" class="fld-pic">'
            f'<img src="assets/pic.png" alt="{section}" width="600" height="320"></figure>'
        )
        html = head + marker + paragraph + "</p>\n" + figure + rest
    html_path.write_text(html, encoding="utf-8")


def _serve(tmp_path, slug_dir):
    port = _free_port()
    sandbox = Path(tempfile.mkdtemp(prefix="inflow-browser-", dir=tmp_path))
    env = os.environ.copy()
    env.update(
        {
            "ANNOTATE_STATE_DIR": str(sandbox / "state"),
            "ANNOTATE_BUS_ROOT": str(sandbox / "bus"),
            "ANNOTATE_CONFIG_DIR": str(sandbox / "config"),
            "ANNOTATE_DATA_DIR": str(sandbox / "data"),
            "ANNOTATE_CLAUDE_SETTINGS": str(sandbox / "claude" / "settings.json"),
            "ANNOTATE_SHIM_PATH": str(sandbox / "bin" / "annotate"),
            "ANNOTATE_BUS_ARCHIVE_ROOT": str(sandbox / "bus-archive"),
        }
    )
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "agent_annotate.sync_server",
            "--slug-dir",
            str(slug_dir),
            "--slug",
            slug_dir.name,
            "--bus-dir",
            str(sandbox / "bus"),
            "--port",
            str(port),
            "--local-author",
            "reviewer@example.com",
            "--local-author-name",
            "Browser Reviewer",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    base = f"http://127.0.0.1:{port}/"
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            urllib.request.urlopen(base, timeout=1).close()
            break
        except OSError:
            time.sleep(0.05)
    else:
        process.terminate()
        raise AssertionError(f"sync server never came up on {port}")
    return process, base


def _pose(base, slug_dir):
    cards = json.loads((slug_dir / "cards.json").read_text())
    request = urllib.request.Request(
        base + "api/comments/batch",
        method="POST",
        data=json.dumps({"items": [dict(card, version="v1") for card in cards]}).encode(),
        headers={"Content-Type": "application/json", "X-Annotate-Agent": "agent:inflow-browser"},
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)["ids"]


def _decision(slug_dir, anchor):
    store = json.loads((slug_dir / "comments.json").read_text())
    return (store["anchors"][anchor][0].get("decision") or {})


def _box(locator):
    box = locator.bounding_box()
    assert box, "element has no box"
    return box


@pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")
@pytest.mark.parametrize("width,height", [(1440, 960), (390, 844)])
def test_question_controls_sit_under_their_pictures_and_answers_survive_reload(tmp_path, width, height):
    source = tmp_path / "page.md"
    source.write_text(PAGE, encoding="utf-8")
    slug_dir = tmp_path / "inflow-review"
    generate(source, slug_dir)
    _with_pictures(slug_dir)
    process, base = _serve(tmp_path, slug_dir)
    try:
        ids = _pose(base, slug_dir)
        assert len(ids) == 2
        with playwright.sync_playwright() as runner:
            browser = runner.chromium.launch(executable_path=str(CHROME), headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            page.set_default_timeout(10_000)
            page.goto(base + "#view=review", wait_until="networkidle")
            page.locator('body[data-ready="1"]').wait_for(state="attached")
            frame = page.frame_locator("#content-frame")
            strips = frame.locator(".annotate-decision-strip")
            strips.nth(1).wait_for()
            assert strips.count() == 2

            # No collected list above the page, and nothing answerable above
            # the first picture.
            assert frame.locator("#annotate-feedback-top").count() == 0
            first_picture = _box(frame.locator("figure.fld-pic img").first)
            for button in frame.locator(".annotate-decision-strip button").all():
                if button.is_visible():
                    assert _box(button)["y"] >= first_picture["y"] + first_picture["height"]

            for n, section in ((1, "route-drawn-on-open"), (2, "legs-and-publish-wording")):
                card = frame.locator(f'.card[data-anchor-id="d:q{n}"]')
                assert card.is_hidden(), "the static card is the no-JavaScript fallback"
                strip = frame.locator(f'.annotate-decision-strip[data-strip-anchor="d:q{n}"]')
                # The strip takes the card's place in the flow: right after it,
                # inside the same section, below that section's picture.
                assert strip.evaluate(
                    "(el, n) => el.previousElementSibling?.dataset.anchorId === 'd:q' + n", n
                )
                assert strip.evaluate(
                    "(el, s) => el.closest('section')?.dataset.anchorId === 's:' + s", section
                )
                picture = _box(frame.locator(f'[data-anchor-id="s:{section}:fig1"] img'))
                assert _box(strip)["y"] >= picture["y"] + picture["height"]

            first = frame.locator('.annotate-decision-strip[data-strip-anchor="d:q1"]')
            yes = first.get_by_role("button", name="Yes", exact=False).first
            assert "Yes" in yes.inner_text()
            assert first.locator(".annotate-decision-reco-line").inner_text().strip() == "Recommended: Yes"
            assert first.get_by_role("button", name="Answer in words").count() == 1
            assert page.evaluate("() => document.documentElement.scrollWidth") <= width

            # A choice with a note.
            first.locator("textarea.annotate-decision-cmt").fill("Only once the route has loaded")
            yes.click()
            first.locator(".annotate-verdict-chip").wait_for()
            deadline = time.time() + 5
            while not _decision(slug_dir, "d:q1") and time.time() < deadline:
                time.sleep(0.05)
            saved = _decision(slug_dir, "d:q1")
            assert saved["verdict"] == "select"
            assert saved["text"].startswith("Yes")
            assert "Only once the route has loaded" in saved["text"]

            # Answer in words.
            second = frame.locator('.annotate-decision-strip[data-strip-anchor="d:q2"]')
            second.locator("textarea.annotate-decision-cmt").fill("The second leg shows the wrong time")
            second.get_by_role("button", name="Answer in words").click()
            second.locator(".annotate-verdict-chip").wait_for()
            deadline = time.time() + 5
            while not _decision(slug_dir, "d:q2") and time.time() < deadline:
                time.sleep(0.05)
            saved = _decision(slug_dir, "d:q2")
            assert saved["verdict"] in ("comment", "changes")  # one text slot; the server picks the spelling
            assert saved["text"] == "The second leg shows the wrong time"

            # Both answers survive a reload, still in place under their pictures.
            page.reload(wait_until="networkidle")
            page.locator('body[data-ready="1"]').wait_for(state="attached")
            frame = page.frame_locator("#content-frame")
            first = frame.locator('.annotate-decision-strip[data-strip-anchor="d:q1"]')
            second = frame.locator('.annotate-decision-strip[data-strip-anchor="d:q2"]')
            first.locator(".annotate-verdict-chip").wait_for()
            second.locator(".annotate-verdict-chip").wait_for()
            assert "Yes" in first.locator(".annotate-verdict-chip").inner_text()
            assert frame.locator("#annotate-feedback-top").count() == 0
            assert first.evaluate("el => el.previousElementSibling?.dataset.anchorId === 'd:q1'")
            assert _decision(slug_dir, "d:q1")["verdict"] == "select"
            assert _decision(slug_dir, "d:q2")["text"] == "The second leg shows the wrong time"
            browser.close()
    finally:
        process.terminate()
        process.wait(timeout=5)
