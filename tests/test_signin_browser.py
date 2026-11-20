"""A real browser follows the shared links that test_signin_matrix.py checks over HTTP.

Headless Chrome over its DevTools pipe (tests/signin_browser.mjs), each visit in a fresh
browser context with an empty cookie jar, the pages over https as on Funnel, and Google's
account chooser stood in for. Playwright's WebKit is not installed here, so the phone is
Chrome's phone emulation: 390x844, touch, an iPhone user agent.
"""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from test_signin import _configure, world  # noqa: F401
from test_signin_matrix import EDITOR, PRIVATE, STRANGER, _setup

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SCRIPT = Path(__file__).with_name("signin_browser.mjs")


def _drive(world, visits):  # noqa: F811
    if not Path(CHROME).exists() or not shutil.which("node"):
        pytest.skip("needs Google Chrome and node")
    page = world["pages"]["proj"]
    with tempfile.TemporaryDirectory(prefix="annotate-signin-chrome-") as root:
        plan = Path(root) / "plan.json"
        plan.write_text(json.dumps({"chrome": CHROME, "profile": str(Path(root) / "profile"),
                                    "host": page["host"].split(":")[0], "port": page["port"], "visits": visits}))
        done = subprocess.run(["node", str(SCRIPT), str(plan)], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return {v["name"]: v for v in json.loads(done.stdout)}


def _landed(seen, link, card):
    """Signed in as the editor, on the page at the card it was sent to, at the card's version,
    the document readable and its picture drawn."""
    assert seen["who"] == EDITOR
    assert seen["href"] == link + "&view=review&v=v1", seen["href"]  # shell.js adds the card's view and version
    assert seen["card"] == {"highlighted": True, "onScreen": True, "text": seen["card"]["text"]}, seen
    assert "Look at the corner of this picture." in seen["card"]["text"]
    assert seen["frame"] == "./content?v=v1"
    assert PRIVATE in seen["document"]["text"]
    assert seen["document"]["picture"] == {"complete": True, "width": 240, "height": 160}


@pytest.mark.parametrize("world", ["tls"], indirect=True)
def test_a_person_on_the_list_lands_on_the_picture_note_on_desk_and_phone(world, monkeypatch):  # noqa: F811
    _configure(monkeypatch)
    case = _setup(world)
    card = case["ids"]["picture note"]
    link = f"https://{world['pages']['proj']['host']}/annotate/proj/page/#feedback={card}"
    world["google"]["accounts"] = [EDITOR, EDITOR]  # who picks themself in Google's chooser, per visit
    seen = _drive(world, [{"name": device, "device": device, "url": link, "card": card} for device in ("desk", "phone")])
    for device in ("desk", "phone"):
        _landed(seen[device]["first"], link, card)
    assert world["google"]["accounts"] == []  # each fresh jar signed in once


@pytest.mark.parametrize("world", ["tls"], indirect=True)
def test_wrong_account_switches_from_the_not_shared_page_back_to_the_card(world, monkeypatch):  # noqa: F811
    _configure(monkeypatch)
    case = _setup(world)
    card = case["ids"]["picture note"]
    link = f"https://{world['pages']['proj']['host']}/annotate/proj/page/#feedback={card}"
    world["google"]["accounts"] = [STRANGER, EDITOR]  # signs in with the wrong account first
    seen = _drive(world, [{"name": "retry", "device": "phone", "url": link, "card": card,
                           "click": "Use another Google account"}])["retry"]
    first = seen["first"]
    assert "This page is not shared with you." in first["text"] and STRANGER in first["text"]
    assert first["card"] is None and "document" not in first and PRIVATE not in first["text"]
    assert seen["clicked"]
    _landed(seen["after"], link, card)
