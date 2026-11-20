"""A real browser follows the shared links that test_signin_matrix.py checks over HTTP.

Headless Chrome over its DevTools pipe (tests/signin_browser.mjs), each visit in a fresh
browser context with an empty cookie jar, the pages over https as on Funnel, and Google's
account chooser stood in for. Playwright's WebKit is not installed here, so the phone is
Chrome's phone emulation: 390x844, touch, an iPhone user agent.

Chrome runs in its own process group with a temporary HOME and profile, and may only reach
the test servers: every connection goes through a local gate that lets through only the
page and the stand-in Google and refuses anything else, and the run fails on any refusal,
on a page's request to one of the Google names that skip the gate (they fail to resolve
instead), on a socket that skips the gate, or on a file left in that HOME. The whole group is killed
at the deadline. These checks need Google Chrome (macOS app, or google-chrome on Linux, as
on GitHub's Ubuntu runner) and node; without them they skip.
"""
import json
import os
import select
import shutil
import signal
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
import urllib.parse
from pathlib import Path

import pytest
from review_fixtures import complete
from test_signin import OWNER, _bind, _configure, world  # noqa: F401
from test_signin_matrix import EDITOR, PRIVATE, STRANGER, _setup

from agent_annotate import signin
from agent_annotate.pagegen import generate

MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME = MAC_CHROME if Path(MAC_CHROME).exists() else shutil.which("google-chrome")
SCRIPT = Path(__file__).with_name("signin_browser.mjs")
DEADLINE = 120
SECOND = "Second version, published after the card."


def _pids(*args):
    return subprocess.run(["pgrep", *args], capture_output=True, text=True).stdout.split()


def _sockets(group, seconds):
    """Remote ends of every connection the browser's process group holds right now; nothing
    if lsof does not answer within `seconds`, so a stuck call cannot hold up the cleanup."""
    try:
        out = subprocess.run(["lsof", "-nP", "-a", "-g", str(group), "-i"], capture_output=True, text=True,
                             timeout=seconds).stdout
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return {line.split("->")[1].split()[0] for line in out.splitlines() if "->" in line}


class _Gate(socketserver.ThreadingTCPServer):
    """Chrome's proxy: tunnels to an allowed (host, port), refuses and records anything else."""
    daemon_threads = True

    def __init__(self, address, handler):
        self.allowed, self.passed, self.refused = set(), [], []
        super().__init__(address, handler)


class _GateHandler(socketserver.BaseRequestHandler):
    def handle(self):
        client, server = self.request, self.server
        client.settimeout(10)
        head = b""
        try:
            while b"\r\n\r\n" not in head and len(head) < 65536:
                chunk = client.recv(65536)
                if not chunk:
                    return
                head += chunk
            line = head.split(b"\r\n", 1)[0].decode("latin-1")
            method, target = (line.split(" ") + [""])[:2]
            if method == "CONNECT":
                host, _, port = target.rpartition(":")
            else:  # plain http: an absolute URL
                url = urllib.parse.urlsplit(target)
                host, port = url.hostname or "", url.port or 80
            if (host, int(port or 0)) not in server.allowed:
                server.refused.append(line)
                client.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                return
            server.passed.append(line)
            with socket.create_connection(("127.0.0.1", int(port)), timeout=10) as upstream:
                if method == "CONNECT":
                    client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                    head = head.split(b"\r\n\r\n", 1)[1]
                # The stand-in Google answers one plain request and closes, so this tunnel ends with it.
                upstream.sendall(head)
                while True:
                    ready, _, _ = select.select([client, upstream], [], [], 10)
                    if not ready:
                        return
                    for side in ready:
                        data = side.recv(65536)
                        if not data:
                            return
                        (upstream if side is client else client).sendall(data)
        except (OSError, ValueError):
            return


def _drive(world, visits):  # noqa: F811
    if not CHROME or not shutil.which("node"):
        pytest.skip("the browser checks need Google Chrome and node; this runner lacks one")
    page = world["pages"]["proj"]
    gate = _bind(_GateHandler, _Gate)
    host = page["host"].split(":")[0]
    gate.allowed |= {(host, page["port"]), ("127.0.0.1", urllib.parse.urlsplit(signin.AUTH_URL).port)}
    gate_thread = threading.Thread(target=gate.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    gate_thread.start()
    with tempfile.TemporaryDirectory(prefix="annotate-signin-chrome-") as root:
        plan, home, profile = Path(root) / "plan.json", Path(root) / "home", Path(root) / "profile"
        home.mkdir()
        plan.write_text(json.dumps({"chrome": CHROME, "profile": str(profile), "host": host, "port": page["port"],
                                    "proxy": gate.server_address[1], "visits": visits}))
        with open(Path(root) / "out", "w+") as out, open(Path(root) / "err", "w+") as err:
            # Its own process group: the deadline kills node, Chrome and every helper together.
            # On Linux, fontconfig and NSS keep their caches in the XDG dirs: beside the profile, not in HOME.
            xdg = {f"XDG_{kind}_HOME": str(Path(root) / f"xdg-{kind.lower()}") for kind in ("CACHE", "CONFIG", "DATA")}
            try:
                node = subprocess.Popen(["node", str(SCRIPT), str(plan)], stdout=out, stderr=err,
                                        start_new_session=True, env={**os.environ, **xdg, "HOME": str(home)})
            except BaseException:  # no node to wait for: close the gate here
                gate.shutdown()
                gate.server_close()
                raise
            reached, ends = set(), time.monotonic() + DEADLINE
            try:
                while node.poll() is None and (remaining := ends - time.monotonic()) > 0:
                    reached |= _sockets(node.pid, remaining)
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
                gate.shutdown()
                gate.server_close()
            out.seek(0)
            err.seek(0)
            stdout, stderr = out.read(), err.read()
        written = sorted(str(p.relative_to(home)) for p in home.rglob("*"))
    assert not left, f"Chrome processes outlived the run: {left}"
    assert not timed_out, f"no result in {DEADLINE} s: {stderr}"
    assert node.returncode == 0, stderr
    assert gate.refused == [], f"Chrome tried to reach outside the test: {gate.refused}"
    assert gate.passed, "nothing went through the gate, so the checks above prove nothing"
    assert reached, "saw no socket at all, so the next check would prove nothing"
    assert reached <= {f"127.0.0.1:{gate.server_address[1]}"}, f"Chrome connected around the gate: {reached}"
    assert written == [], f"Chrome wrote outside its profile: {written}"
    result = json.loads(stdout)
    assert result["unresolved"] == [], f"Chrome tried to reach a name the gate lets bypass it: {result['unresolved']}"
    return {v["name"]: v for v in result["visits"]}


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
    assert seen["card"] == {"highlighted": True, "onScreen": True, "open": True, "text": seen["card"]["text"]}, seen
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
def test_a_question_link_opens_the_question_after_sign_in_on_desk_and_phone(world, monkeypatch):  # noqa: F811
    """An open question follows the current version, so it is linked on v1, the only version."""
    _configure(monkeypatch)
    card = _setup(world)["ids"]["question"]
    link = f"https://{world['pages']['proj']['host']}/annotate/proj/page/#feedback={card}"
    world["google"]["accounts"] = [EDITOR, EDITOR]
    seen = _drive(world, [{"name": device, "device": device, "url": link, "card": card} for device in ("desk", "phone")])
    landed = {device: seen[device]["first"] for device in ("desk", "phone")}
    for device, first in landed.items():
        assert first["who"] == EDITOR
        assert first["href"] == link + "&view=review", first["href"]  # no v: it follows the viewer
    # Both widths in one check, so a miss on either shows.
    cards = {device: {**first["card"], "text": "Ship it?" in first["card"]["text"]} for device, first in landed.items()}
    assert cards == {device: {"highlighted": True, "onScreen": True, "open": True, "text": True} for device in landed}
    assert world["google"]["accounts"] == []


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
