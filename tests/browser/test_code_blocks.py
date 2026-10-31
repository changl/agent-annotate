"""Code blocks wrap and copy in one click; a card jump never moves the shell header.

Chang, 2026-10-30: the orchestrator's terminal commands were cut off at the
block's right edge and had to be selected by hand; the whole page, header
included, scrolled.
"""

import json

import pytest
from single_page import browser_page, feedback
from test_card_jump import _card
from test_card_layout import CHROME, _wait

from agent_annotate.pagegen import generate

playwright = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.skipif(not CHROME.exists(), reason="Google Chrome is not installed")

COMMAND = "sudo /bin/bash -c '/usr/sbin/chown -R root:wheel /Applications/Xcode-27.app' && " + "/usr/bin/true " * 40
SOURCE = f"""---
title: Commands
version: v1
---

Intro.

## Install

Run this:

```
{COMMAND.strip()}
echo SITTING-EXIT=$?
```

{"Filler paragraph. " * 400}

## Tail

The end.
"""


@pytest.fixture
def page_dir(tmp_path):
    source = tmp_path / "commands.md"
    source.write_text(SOURCE)
    directory = tmp_path / "commands"
    generate(source, directory)
    card = _card("card-1", 1, "d:q1", "Ran it?", ["accept", "reject"], [{"label": "Tail", "anchor": "s:tail"}])
    (directory / "comments.json").write_text(json.dumps(
        {"schema_version": 2, "anchors": {"d:q1": [card]}, "archived": {}}))
    return directory


@pytest.mark.parametrize("width", [1440, 390])
def test_code_wraps_copies_and_the_header_stays(tmp_path, page_dir, width):
    with browser_page(tmp_path, page_dir, width=width, height=800) as (page, _):
        page.context.grant_permissions(["clipboard-read", "clipboard-write"])
        frame = page.frame_locator("#content-frame")
        pre = frame.locator("pre").first
        assert pre.evaluate("e => e.scrollWidth <= e.clientWidth"), "long lines wrap, never cut off"

        pre.hover()
        button = pre.locator(".aa-copy")
        button.click()
        _wait(lambda: button.get_attribute("aria-label") == "Copied", page)
        copied = page.evaluate("navigator.clipboard.readText()")
        assert copied == COMMAND.strip() + "\necho SITTING-EXIT=$?"
        assert frame.locator("#aa-copy-live").text_content() == "Copied"

        feedback(page)
        card = page.locator('.citem[data-comment-id="card-1"]')
        card.locator(".decision-evidence-toggle").click()
        card.locator(".decision-evidence-link").first.click()
        card.locator(".decision-evidence-goto").first.click()
        _wait(lambda: frame.locator("body").evaluate("() => window.scrollY") > 0, page)
        page.wait_for_timeout(600)
        assert page.evaluate("""() => [document.scrollingElement, document.body, document.querySelector('.main'),
            document.querySelector('#frame-area')].every(e => e.scrollTop === 0)
            && document.querySelector('.hdr').getBoundingClientRect().top === 0""")


def test_the_shell_snaps_back_when_the_browser_scrolls_it(tmp_path, page_dir):
    # iPad browsers scroll the page itself (toolbar collapse); body overflow:hidden leaves no way back.
    with browser_page(tmp_path, page_dir, width=834, height=1100) as (page, _):
        page.evaluate("""() => { const tall = document.createElement('div');
            tall.style.cssText = 'position:absolute;top:0;left:0;width:1px;height:4000px';
            document.body.append(tall); window.scrollTo(0, 600); }""")
        _wait(lambda: page.evaluate("() => window.scrollY") == 0, page)
        assert page.evaluate("() => document.querySelector('.hdr').getBoundingClientRect().top") == 0
