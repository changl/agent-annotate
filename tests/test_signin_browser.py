"""A real browser follows the shared links that test_signin_matrix.py checks over HTTP.

Headless Chrome over its DevTools pipe (tests/signin_browser.mjs), each visit in a fresh
browser context with an empty cookie jar, the pages over https as on Funnel, and Google's
account chooser stood in for. Playwright's WebKit is not installed here, so the phone is
Chrome's phone emulation: 390x844, touch, an iPhone user agent.

Chrome runs in its own process group with a temporary HOME and profile, and may only reach
the test servers: the run fails if it connects anywhere else or leaves a file in that HOME,
and the whole group is killed at the deadline. These checks need macOS Google Chrome and
node, so on the Linux PR runner they skip.
"""
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
from review_fixtures import complete
from test_signin import OWNER, _configure, world  # noqa: F401
from test_signin_matrix import EDITOR, PRIVATE, STRANGER, _setup

from agent_annotate.pagegen import generate

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
SCRIPT = Path(__file__).with_name("signin_browser.mjs")
DEADLINE = 120
SECOND = "Second version, published after the card."


def _pids(*args):
    return subprocess.run(["pgrep", *args], capture_output=True, text=True).stdout.split()


def _sockets(group):
    """Remote ends of every connection the browser's process group holds right now."""
    out = subprocess.run(["lsof", "-nP", "-a", "-g", str(group), "-i"], capture_output=True, text=True).stdout
    return {line.split("->")[1].split()[0] for line in out.splitlines() if "->" in line}


def _drive(world, visits):  # noqa: F811
    if not Path(CHROME).exists() or not shutil.which("node"):
        pytest.skip("the browser checks need macOS Google Chrome and node; this runner has neither")
    page = world["pages"]["proj"]
    with tempfile.TemporaryDirectory(prefix="annotate-signin-chrome-") as root:
        plan, home, profile = Path(root) / "plan.json", Path(root) / "home", Path(root) / "profile"
        home.mkdir()
        plan.write_text(json.dumps({"chrome": CHROME, "profile": str(profile), "host": page["host"].split(":")[0],
                                    "port": page["port"], "visits": visits}))
        with open(Path(root) / "out", "w+") as out, open(Path(root) / "err", "w+") as err:
            # Its own process group: the deadline kills node, Chrome and every helper together.
            node = subprocess.Popen(["node", str(SCRIPT), str(plan)], stdout=out, stderr=err, start_new_session=True,
                                    env={**os.environ, "HOME": str(home)})
            reached, ends = set(), time.monotonic() + DEADLINE
            try:
                while node.poll() is None and time.monotonic() < ends:
                    reached |= _sockets(node.pid)
                    time.sleep(0.3)
            finally:
                timed_out = node.poll() is None
                try:
                    os.killpg(node.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                node.wait()
                for _ in range(50):  # killed helpers go to launchd; wait until they are gone
                    left = _pids("-f", str(profile))
                    if not left:
                        break
                    time.sleep(0.1)
                for pid in left:
                    os.kill(int(pid), signal.SIGKILL)
            out.seek(0)
            err.seek(0)
            stdout, stderr = out.read(), err.read()
        written = sorted(str(p.relative_to(home)) for p in home.rglob("*"))
    assert not left, f"Chrome processes outlived the run: {left}"
    assert not timed_out, f"no result in {DEADLINE} s: {stderr}"
    assert node.returncode == 0, stderr
    assert reached, "saw no connection at all, so the next check would prove nothing"
    assert {r.rsplit(":", 1)[0] for r in reached} <= {"127.0.0.1"}, f"Chrome reached outside the test: {reached}"
    assert all(18700 <= int(r.rsplit(":", 1)[1]) < 18800 for r in reached), reached
    assert written == [], f"Chrome wrote outside its profile: {written}"
    return {v["name"]: v for v in json.loads(stdout)}


def _second_version(world):  # noqa: F811
    """Publish v2 after the cards, so a link to a v1 card must open v1, not the latest."""
    directory = world["pages"]["proj"]["dir"]
    source = directory.parents[1] / "proj.md"
    generate(source, directory, text=source.read_text().replace("Private proj content.", f"Private proj content. {SECOND}"))
    complete(directory)
    assert (directory / "versions" / "v2.html").exists()


def _landed(seen, link, card):
    """Signed in as the editor, on the page at the card it was sent to, at the card's own
    (older) version, the document readable and its picture drawn."""
    assert seen["who"] == EDITOR
    assert seen["href"] == link + "&view=review&v=v1", seen["href"]  # shell.js adds the card's view and version
    assert seen["card"] == {"highlighted": True, "onScreen": True, "text": seen["card"]["text"]}, seen
    assert "Look at the corner of this picture." in seen["card"]["text"]
    assert seen["frame"] == "./content?v=v1"
    assert PRIVATE in seen["document"]["text"] and SECOND not in seen["document"]["text"]
    assert seen["document"]["picture"] == {"complete": True, "width": 240, "height": 160}


@pytest.mark.parametrize("world", ["tls"], indirect=True)
def test_a_person_on_the_list_lands_on_the_picture_note_on_desk_and_phone(world, monkeypatch):  # noqa: F811
    _configure(monkeypatch)
    case = _setup(world)
    _second_version(world)
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
    _second_version(world)
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


@pytest.mark.parametrize("world", ["tls"], indirect=True)
def test_copy_link_gives_a_link_that_opens_without_google(world, monkeypatch):  # noqa: F811
    """The owner presses Copy link; the clipboard's URL, opened in a fresh browser with no
    cookies, carries the review key and lets its holder in without Google asking who they are.
    Temporary (README: "#review= links keep working for one release"): when Copy link stops
    adding the key, this test must change to expect the sign-in page."""
    _configure(monkeypatch)
    _setup(world)
    page = world["pages"]["proj"]
    home = f"https://{page['host']}/annotate/proj/page/"
    world["google"]["accounts"] = [OWNER, STRANGER]  # the owner signs in; the forwarded link must not
    seen = _drive(world, [{"name": "owner", "device": "desk", "url": home, "copy": True},
                          {"name": "forwarded", "device": "phone", "url": "@copied"}])
    owner, forwarded = seen["owner"], seen["forwarded"]
    assert owner["first"]["who"] == OWNER and owner["menuClicked"] and owner["copyClicked"] and owner["button"] == "Copied"
    assert owner["copied"] == f"{home}#review={page['key']}"
    assert forwarded["opened"] == owner["copied"]
    assert world["google"]["accounts"] == [STRANGER]  # Google was never asked
    landed = forwarded["first"]
    assert landed["who"].startswith("reviewer:"), landed
    assert "review=" not in landed["href"]  # the key leaves the address bar
    assert PRIVATE in landed["document"]["text"]
