"""Who can open a shared link: every person x every link x desk and phone, signed out first.

Google is stood in for by the fake token endpoint in test_signin.py. For each case
the test follows the link signed out, signs in, and checks where the person lands,
what the server gives them (page, document, picture, cards) and whether answering
and Send work or are refused, then checks on the owner's side that a refused write
changed nothing. tests/test_signin_browser.py follows the same links in Chrome.

Two parts of the design are not built yet: the "can view" role and asking for
access. Only those checks are expected to fail; set-up, sign-in and reading are
ordinary assertions. When a missing part lands, its checks pass and the test fails
until the mark comes off (the same as xfail strict).
"""
import inspect
import json
import os
import urllib.parse
from html.parser import HTMLParser
from pathlib import Path

import pytest
from test_signin import (  # noqa: F401
    GUEST,
    HOST,
    OWNER,
    PROJ,
    _configure,
    _cookies,
    _session,
    _sign_in,
    world,
)

from agent_annotate import signin
from agent_annotate.review_history import _events

EDITOR, VIEWER, STRANGER, REMOVED, CHANGED = (GUEST, "viewer@example.com", "stranger@example.com",
                                              "removed@example.com", "changed@example.com")
DESK = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
PHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 "
         "(KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1")
BASE = "/annotate/proj/page/"
PRIVATE = "Private proj content"
NO_ROLES = ("roles are not built: members.json maps a person to projects only, "
            "so everyone added can answer and send")
NO_ASK = "the not-shared page has no way to ask for access"
IMAGE = {"Origin": "null", "Sec-Fetch-Mode": "no-cors", "Sec-Fetch-Site": "cross-site"}  # the sandboxed document's <img>

# person -> (email, can see the page, can answer and send). The owner is on no list.
PEOPLE = {
    "owner": (OWNER, True, True),
    "can answer and send": (EDITOR, True, True),
    "can view": (VIEWER, True, False),
    "not on the list": (STRANGER, False, False),
    "removed": (REMOVED, False, False),
    "role changed to can view": (CHANGED, True, False),
}
LINKS = ("page", "question", "picture note")
ANCHORS = {"question": "s:progress:p1", "picture note": "fig:proof"}


class NotBuiltYet:
    """Checks for a part of the design that is missing. Collect them, run every real
    assertion, then settle: any miss is the expected failure; no miss means it is built."""

    def __init__(self, reason):
        self.reason, self.misses = reason, []

    def expect(self, ok, what):
        if not ok:
            self.misses.append(what)

    def settle(self):
        if self.misses:
            pytest.xfail(self.reason + " (" + "; ".join(self.misses) + ")")
        pytest.fail("built now, so take the expected failure off: " + self.reason)


def _grant(email, role):
    """Add a person with a role ("view" or "answer"), the way the People page will."""
    if "role" in inspect.signature(signin.change_member).parameters:
        signin.change_member("add", email, PROJ, role=role)
    else:  # today's only way to share: a plain add, which can answer and send
        signin.change_member("add", email, PROJ)


def _setup(env):
    """The People list for the matrix, then the owner posts one question and one note on the
    picture and sends them. Returns the card ids, the picture's path and the owner's cookies."""
    _grant(EDITOR, "answer")
    _grant(VIEWER, "view")
    _grant(REMOVED, "answer")
    signin.change_member("remove", REMOVED, PROJ)
    _grant(CHANGED, "answer")
    _grant(CHANGED, "view")
    directory = env["pages"]["proj"]["dir"]
    picture = "assets/" + next((directory / "assets").glob("*-proj-proof.png")).name
    assert f'data-anchor-id="{ANCHORS["picture note"]}"' in (directory / "versions" / "v1.html").read_text()
    question = {"anchor_id": ANCHORS["question"], "text": "Ship it?", "version": "v1", "decision_request": {
        "prompt": "Ship it?", "context": "because", "recommendation": "accept",
        "options": [{"id": "accept", "label": "Yes", "consequence": "ships"},
                    {"id": "reject", "label": "No", "consequence": "waits"}], "impact": "low"}}
    note = {"anchor_id": ANCHORS["picture note"], "text": "Look at the corner of this picture.", "version": "v1"}
    _, (_, headers, _) = _sign_in(env, OWNER)
    owner = _session(headers)
    ids = {}
    for name, body in (("question", question), ("picture note", note)):
        code, _, text = env["request"]("proj", "api/comments", owner, "POST", body)
        assert code == 201, text
        ids[name] = json.loads(text)["id"]
    code, _, text = env["request"]("proj", "api/rounds/submit", owner, "POST", {})
    assert code == 200 and set(json.loads(text)["comment_ids"]) == set(ids.values()), text  # really sent
    return {"ids": ids, "picture": picture, "owner": owner}


def _with_ua(env, ua):
    request = env["request"]
    return {**env, "request": lambda *a, **k: request(*a, **{"User-Agent": ua, **k})}


def _link(name, ids):
    return BASE + ("" if name == "page" else "#feedback=" + ids[name])


def _land(env, email, link):
    """Signed out: the shell sends the person to Google with the whole link, then back."""
    code, _, shell = env["request"]("proj", "")
    assert code == 200 and f'<meta name="annotate-signin" content="{signin.ROUTE}/login?next="' in shell
    assert PRIVATE not in shell
    # shell.js appends encodeURIComponent(pathname + search + hash) to that content.
    _, (code, headers, _) = _sign_in(env, email, next_path=link)
    assert code == 302
    return headers["Location"], _session(headers), signin.ASSET_COOKIE + "=" + _cookies(headers)[signin.ASSET_COOKIE]


def _owner_view(env, case):
    """What the owner sees stored: every card as it is now, and every round sent."""
    code, _, body = env["request"]("proj", "api/comments", case["owner"])
    assert code == 200
    rounds = list(_events(env["pages"]["proj"]["dir"] / "rounds.ndjson"))
    return json.loads(body), rounds


def _reads(env, cookie, asset, case, may_see):
    """The shell, the document, the picture and the cards, each with its exact status."""
    request, ids = env["request"], case["ids"]
    code, _, shell = request("proj", "", cookie)
    assert code == 200 and PRIVATE not in shell  # the private page is only ever in the document
    code, _, document = request("proj", "content?v=v1", cookie)
    assert (code, PRIVATE in document) == ((200, True) if may_see else (403, False))
    code, _, image = request("proj", case["picture"], asset, **IMAGE)
    assert (code, isinstance(image, bytes)) == ((200, True) if may_see else (403, False))
    code, _, body = request("proj", "api/comments", cookie)
    if may_see:
        assert code == 200
        cards = {c["id"]: c["anchor_id"] for c in json.loads(body)}
        assert cards == {ids[name]: ANCHORS[name] for name in ANCHORS}
    else:
        assert code == 403 and json.loads(body) == {"error": "authenticated proxy boundary required"}


def _writes(env, cookie, case, link, email, may_write, missing):
    """Answer the card the link points at (the question for a page link), then Send with a note,
    so Send has work to do even if the answer was refused. Checks the owner's side after."""
    request, ids = env["request"], case["ids"]
    before = _owner_view(env, case)
    card = ids["picture note"] if link == "picture note" else ids["question"]
    if link == "picture note":
        code, _, answered = request("proj", f"api/comments/{card}/reply", cookie, "POST", {"text": "Seen, from " + email})
    else:
        code, _, answered = request("proj", f"api/comments/{card}/decision", cookie, "POST",
                                    {"verdict": "accept", "defer_push": True})
    send, _, sent = request("proj", "api/rounds/submit", cookie, "POST", {"note": "Round from " + email})
    after = _owner_view(env, case)
    new_rounds = after[1][len(before[1]):]
    # Answered and sent: the card went out in one new round, by this person, with their note.
    went_through = (code == 200 and send == 200 and card in json.loads(sent).get("comment_ids", [])
                    and [(r["by"], r["note"]) for r in new_rounds] == [(email, "Round from " + email)]
                    and card in [a["comment_id"] for a in new_rounds[0]["answers"]])
    refused = (code, send) == (403, 403) and after == before
    if may_write:
        assert went_through, (code, send, sent, new_rounds)
        return
    if missing is None:  # no access at all: refused for that reason, and nothing changed for the owner
        assert refused
        assert json.loads(answered) == json.loads(sent) == {"error": "authenticated proxy boundary required"}
        return
    # Expected to fail only as today: answer and Send go through in full. Built: both refused and
    # nothing changes. Anything in between (403 that still saves, 200 that sends nothing) fails.
    assert went_through or refused, f"neither today's behaviour nor the role: answer {code}, Send {send}, {sent}"
    missing.expect(refused, f"answer got {code}; Send got {send}; the owner sees the answer and a round")


def _case(person, link, ua):
    return pytest.param(person, link, ua, id=f"{person}-{link}-{'phone' if ua == PHONE else 'desk'}")


@pytest.mark.parametrize("person,link,ua", [_case(p, k, u) for p in PEOPLE for k in LINKS for u in (DESK, PHONE)])
def test_access_matrix(world, monkeypatch, person, link, ua):  # noqa: F811
    _configure(monkeypatch)
    case = _setup(world)
    env = _with_ua(world, ua)
    email, may_see, may_write = PEOPLE[person]
    target = _link(link, case["ids"])
    location, cookie, asset = _land(env, email, target)
    assert location == target  # back at the page, question or note they were sent
    code, _, shell = env["request"]("proj", "", cookie)
    assert code == 200
    if may_see:
        assert 'name="annotate-signin"' not in shell
    else:  # the shell sends them to the not-shared page, keeping the link
        assert f'content="{signin.ROUTE}/denied?next="' in shell
        denied = signin.ROUTE + "/denied?" + urllib.parse.urlencode({"next": target})
        code, _, page = env["request"]("proj", denied, cookie)
        assert code == 403 and "not shared with you" in page and email in page and PRIVATE not in page
    _reads(env, cookie, asset, case, may_see)
    missing = NotBuiltYet(NO_ROLES) if may_see and not may_write else None
    _writes(env, cookie, case, link, email, may_write, missing)
    if missing:
        missing.settle()


def test_review_key_link_lets_anyone_in_until_google_signin_is_live(world, monkeypatch):  # noqa: F811
    """Temporary path (README: "#review= links keep working for one release"). Whoever holds a
    copied link gets in, People list or not, and removal does not shut it. Copy link itself is
    pressed in a real browser in test_signin_browser.py. When Copy link stops adding the key,
    delete this test and add the copied URL to test_access_matrix."""
    _configure(monkeypatch)
    case = _setup(world)
    request, key = world["request"], world["pages"]["proj"]["key"]
    assert request("proj", "api/share-link")[0] == 403  # signed out: nothing to copy
    for email in (STRANGER, REMOVED):
        _, (_, headers, _) = _sign_in(world, email)
        google = _session(headers)
        assert request("proj", "api/comments", google)[0] == 403  # Google sign-in alone: refused
        code, headers, _ = request("proj", "api/reviewer/session", google, "POST", {"key": key, "name": "Forwarded"})
        assert code == 200
        cookie = headers.get_all("Set-Cookie")[0].split(";", 1)[0]
        code, _, document = request("proj", "content?v=v1", cookie)
        assert code == 200 and PRIVATE in document
        assert request("proj", f"api/comments/{case['ids']['picture note']}/reply", cookie, "POST",
                       {"text": "Forwarded link"})[0] in (200, 201)


def test_removed_person_is_refused_from_the_next_request(world, monkeypatch):  # noqa: F811
    """Removal holds on the next request with the same cookies: page, document, picture, cards,
    answer and Send. Not covered: a tab already showing the page keeps it on screen until it
    loads again (a refused poll leaves the view as it is)."""
    _configure(monkeypatch)
    case = _setup(world)
    _grant(REMOVED, "answer")
    _, cookie, asset = _land(world, REMOVED, _link("question", case["ids"]))
    _reads(world, cookie, asset, case, True)
    signin.change_member("remove", REMOVED, PROJ)  # same tab, same cookie, no sign-out
    request = world["request"]
    _reads(world, cookie, asset, case, False)
    _writes(world, cookie, case, "question", REMOVED, False, None)
    assert request("proj", "api/identity", cookie)[0] == 403
    assert f'content="{signin.ROUTE}/denied?next="' in request("proj", "", cookie)[2]


def test_role_lowered_while_signed_in_stops_answering_at_once(world, monkeypatch):  # noqa: F811
    _configure(monkeypatch)
    case = _setup(world)
    _grant(EDITOR, "answer")
    _, cookie, asset = _land(world, EDITOR, _link("question", case["ids"]))
    _reads(world, cookie, asset, case, True)
    _writes(world, cookie, case, "question", EDITOR, True, None)  # before: answers and sends
    _grant(EDITOR, "view")
    _reads(world, cookie, asset, case, True)  # after, same cookie: still reads
    missing = NotBuiltYet(NO_ROLES)
    _writes(world, cookie, case, "picture note", EDITOR, False, missing)
    missing.settle()


def test_role_raised_while_signed_in_can_answer_at_once(world, monkeypatch):  # noqa: F811
    _configure(monkeypatch)
    case = _setup(world)
    _, cookie, asset = _land(world, VIEWER, _link("question", case["ids"]))
    _reads(world, cookie, asset, case, True)
    missing = NotBuiltYet(NO_ROLES)
    _writes(world, cookie, case, "picture note", VIEWER, False, missing)  # before: refused (not built)
    _grant(VIEWER, "answer")
    _reads(world, cookie, asset, case, True)
    _writes(world, cookie, case, "question", VIEWER, True, None)  # after, same cookie: answers and sends
    missing.settle()


class _Forms(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.forms = [], []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.links.append(attrs.get("href", ""))
        elif tag == "form":
            self.forms.append({"action": attrs.get("action", ""), "method": attrs.get("method", "get"), "fields": {}})
        elif tag in ("input", "button") and self.forms and attrs.get("name"):
            self.forms[-1]["fields"][attrs["name"]] = attrs.get("value", "")


def test_not_shared_page_offers_another_account_and_lands_on_the_card(world, monkeypatch):  # noqa: F811
    """Today's not-shared page, and the wrong-account retry through its own link."""
    _configure(monkeypatch)
    case = _setup(world)
    target = _link("question", case["ids"])
    _, cookie, _ = _land(world, STRANGER, target)
    request = world["request"]
    code, _, page = request("proj", signin.ROUTE + "/denied?" + urllib.parse.urlencode({"next": target}), cookie)
    assert code == 403 and "This page is not shared with you." in page and STRANGER in page and PRIVATE not in page
    parsed = _Forms()
    parsed.feed(page)
    switch = [href for href in parsed.links if href.startswith(signin.ROUTE + "/login?")]
    assert len(switch) == 1 and "Use another Google account" in page
    next_path = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(switch[0].replace("&amp;", "&")).query))["next"]
    assert next_path == target  # the switch keeps the card
    _, (code, headers, _) = _sign_in(world, EDITOR, next_path=next_path)
    assert code == 302 and headers["Location"] == target
    assert request("proj", "api/comments", _session(headers))[0] == 200


def test_not_shared_page_offers_to_ask_for_access(world, monkeypatch):  # noqa: F811
    _configure(monkeypatch)
    case = _setup(world)
    target = _link("question", case["ids"])
    _, cookie, _ = _land(world, STRANGER, target)
    request = world["request"]
    code, _, page = request("proj", signin.ROUTE + "/denied?" + urllib.parse.urlencode({"next": target}), cookie)
    assert code == 403  # the page itself is ordinary; only the control is missing
    parsed = _Forms()
    parsed.feed(page)
    missing = NotBuiltYet(NO_ASK)
    asks = [f for f in parsed.forms if f["method"].lower() == "post" and f["fields"].get("next") == target]
    missing.expect(asks != [], "no form that asks for access to this card")
    if asks:  # only the missing form is expected; once there, sending it must work and be recorded
        assert len(asks) == 1, asks
        roots = (world["pages"]["proj"]["dir"].parents[1], Path(os.environ["ANNOTATE_STATE_DIR"]).parent)
        before = _files(roots)
        code, _, body = request("proj", asks[0]["action"], cookie, "POST", asks[0]["fields"])
        assert code in (200, 201, 202, 303), (code, body)
        assert any(STRANGER in text and (PROJ in text or BASE in text) for text in _written(roots, before)), \
            "asking recorded no request naming this person and page"
    missing.settle()


def _files(roots):
    return {path: path.stat().st_mtime_ns for root in roots for path in root.rglob("*") if path.is_file()}


def _written(roots, before):
    """The text of every file created or changed since `before`."""
    return [path.read_bytes().decode(errors="ignore") for path, mtime in _files(roots).items() if before.get(path) != mtime]
