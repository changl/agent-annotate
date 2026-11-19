"""Who can open a shared link: every person x every link x desk and phone, signed out first.

Google is stood in for by the fake token endpoint in test_signin.py. For each case
the test follows the link signed out, signs in, and checks where the person lands,
what they can see, and whether answering and Send are allowed or refused.

Cases the code does not meet yet are marked xfail(strict=True) with the reason;
their assertions are the design's, unchanged. When the feature lands they pass,
strict turns that into a failure, and the marker must come off.
"""
import inspect
import json
import urllib.parse

import pytest
from test_signin import GUEST, OWNER, PROJ, _configure, _cookies, _session, _sign_in, world  # noqa: F401

from agent_annotate import signin

EDITOR, VIEWER, STRANGER, REMOVED, CHANGED = (GUEST, "viewer@example.com", "stranger@example.com",
                                              "removed@example.com", "changed@example.com")
DESK = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
PHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 "
         "(KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1")
BASE = "/annotate/proj/page/"
NO_ROLES = ("roles are not built: members.json maps a person to projects only, "
            "so everyone added can answer and send")
NO_ASK = "the not-shared page has no way to ask for access"

# person -> (can see the page, can answer and send); None for the owner, who is on no list.
PEOPLE = {
    "owner": (OWNER, True, True),
    "can answer and send": (EDITOR, True, True),
    "can view": (VIEWER, True, False),
    "not on the list": (STRANGER, False, False),
    "removed": (REMOVED, False, False),
    "role changed to can view": (CHANGED, True, False),
}
LINKS = ("page", "question", "picture note")


def _grant(email, role):
    """Add a person with a role ("view" or "answer"), the way the People page will."""
    if "role" in inspect.signature(signin.change_member).parameters:
        signin.change_member("add", email, PROJ, role=role)
    else:  # today's only way to share: a plain add, which can answer and send
        signin.change_member("add", email, PROJ)


def _setup(env):
    """The People list for the matrix, plus one question and one note on a picture."""
    _grant(EDITOR, "answer")
    _grant(VIEWER, "view")
    _grant(REMOVED, "answer")
    signin.change_member("remove", REMOVED, PROJ)
    _grant(CHANGED, "answer")
    _grant(CHANGED, "view")
    question = {"anchor_id": "s:progress:p1", "text": "Ship it?", "version": "v1", "decision_request": {
        "prompt": "Ship it?", "context": "because", "recommendation": "accept",
        "options": [{"id": "accept", "label": "Yes", "consequence": "ships"},
                    {"id": "reject", "label": "No", "consequence": "waits"}], "impact": "low"}}
    note = {"anchor_id": "fig:proof", "text": "Look at the corner of this picture.", "version": "v1"}
    owner = _session(_sign_in(env, OWNER)[1][1])
    ids = {}
    for name, body in (("question", question), ("picture note", note)):
        code, _, text = env["request"]("proj", "api/comments", owner, "POST", body)
        assert code == 201, text
        ids[name] = json.loads(text)["id"]
    code, _, text = env["request"]("proj", "api/rounds/submit", owner, "POST", {})  # sent, so others see them
    assert code == 200, text
    return ids


def _with_ua(env, ua):
    request = env["request"]
    return {**env, "request": lambda *a, **k: request(*a, **{"User-Agent": ua, **k})}


def _link(name, ids):
    return BASE + ("" if name == "page" else "#feedback=" + ids[name])


def _land(env, email, link):
    """Signed out: the shell sends the person to Google with the whole link, then back."""
    request = env["request"]
    code, _, shell = request("proj", "")
    assert code == 200 and f'<meta name="annotate-signin" content="{signin.ROUTE}/login?next="' in shell
    # shell.js appends encodeURIComponent(pathname + search + hash) to that content.
    _, (code, headers, _) = _sign_in(env, email, next_path=link)
    assert code == 302
    return headers["Location"], _session(headers), signin.ASSET_COOKIE + "=" + _cookies(headers)[signin.ASSET_COOKIE]


def _rights(env, cookie, asset, ids, link):
    """(sees, answers, sends) for a signed-in person, each from real requests."""
    request = env["request"]
    code, _, body = request("proj", "api/comments", cookie)
    sees = code == 200 and all(i in body for i in ids.values())
    if link == "picture note":
        image = request("proj", "assets/x.png", asset, Origin="null",
                        **{"Sec-Fetch-Mode": "no-cors", "Sec-Fetch-Site": "cross-site"})[0]
        sees = sees and image == 200
        code = request("proj", f"api/comments/{ids['picture note']}/reply", cookie, "POST", {"text": "Seen."})[0]
    else:
        code = request("proj", f"api/comments/{ids['question']}/decision", cookie, "POST",
                       {"verdict": "accept", "defer_push": True})[0]
    answers = code in (200, 201)
    sends = request("proj", "api/rounds/submit", cookie, "POST", {})[0] in (200, 201)
    return sees, answers, sends


def _case(person, link, ua):
    marks = [pytest.mark.xfail(reason=NO_ROLES, strict=True)] if not PEOPLE[person][2] and PEOPLE[person][1] else []
    return pytest.param(person, link, ua, marks=marks, id=f"{person}-{link}-{'phone' if ua == PHONE else 'desk'}")


@pytest.mark.parametrize("person,link,ua", [_case(p, k, u) for p in PEOPLE for k in LINKS for u in (DESK, PHONE)])
def test_access_matrix(world, monkeypatch, person, link, ua):  # noqa: F811
    _configure(monkeypatch)
    ids = _setup(world)
    env = _with_ua(world, ua)
    email, may_see, may_write = PEOPLE[person]
    target = _link(link, ids)
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
        assert code == 403 and "not shared with you" in page and email in page
        assert "Private proj content" not in page
    assert _rights(env, cookie, asset, ids, link) == (may_see, may_write, may_write)


def test_removed_person_open_session_stops_at_once(world, monkeypatch):  # noqa: F811
    _configure(monkeypatch)
    ids = _setup(world)
    _grant(REMOVED, "answer")
    location, cookie, asset = _land(world, REMOVED, _link("question", ids))
    assert _rights(world, cookie, asset, ids, "picture note") == (True, True, True)
    signin.change_member("remove", REMOVED, PROJ)  # same tab, same cookie, no sign-out
    request = world["request"]
    assert _rights(world, cookie, asset, ids, "question") == (False, False, False)
    assert request("proj", "api/identity", cookie)[0] == 403
    assert request("proj", "assets/x.png", asset, Origin="null",
                   **{"Sec-Fetch-Mode": "no-cors", "Sec-Fetch-Site": "cross-site"})[0] == 403
    assert f'content="{signin.ROUTE}/denied?next="' in request("proj", "", cookie)[2]


@pytest.mark.xfail(reason=NO_ROLES, strict=True)
def test_role_lowered_while_signed_in_stops_answering_at_once(world, monkeypatch):  # noqa: F811
    _configure(monkeypatch)
    ids = _setup(world)
    _grant(EDITOR, "answer")
    _, cookie, asset = _land(world, EDITOR, _link("question", ids))
    assert _rights(world, cookie, asset, ids, "question") == (True, True, True)
    _grant(EDITOR, "view")
    assert _rights(world, cookie, asset, ids, "question") == (True, False, False)


def test_role_raised_while_signed_in_can_answer_at_once(world, monkeypatch):  # noqa: F811
    _configure(monkeypatch)
    ids = _setup(world)
    _, cookie, asset = _land(world, VIEWER, _link("question", ids))
    _grant(VIEWER, "answer")
    assert _rights(world, cookie, asset, ids, "question") == (True, True, True)


@pytest.mark.xfail(reason=NO_ASK, strict=True)
def test_not_shared_page_offers_to_ask_for_access(world, monkeypatch):  # noqa: F811
    _configure(monkeypatch)
    ids = _setup(world)
    _, cookie, _ = _land(world, STRANGER, _link("question", ids))
    code, _, page = world["request"]("proj", signin.ROUTE + "/denied?" + urllib.parse.urlencode(
        {"next": _link("question", ids)}), cookie)
    assert code == 403 and "isn't shared with you yet" in page.replace("&#x27;", "'")
    assert "ask for access" in page.lower()
