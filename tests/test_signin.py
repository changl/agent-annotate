"""Google sign-in for Funnel pages, driven end to end against a fake Google token endpoint."""
import base64
import hashlib
import http.client
import http.server
import json
import threading
import time
import urllib.parse
from http.cookies import SimpleCookie

import pytest
from review_fixtures import complete

from agent_annotate import cli, review_access, signin, sync_server
from agent_annotate.pagegen import generate

HOST = "host.ts.net"
OWNER, GUEST = "owner@example.com", "guest@example.com"
SECRETS = {"GOOGLE_OAUTH_CLIENT_ID": "client-1.apps.googleusercontent.com",
           "GOOGLE_OAUTH_CLIENT_SECRET": "test-client-secret", "ANNOTATE_SESSION_KEY": "test-session-key",
           "ANNOTATE_OWNER_EMAIL": "Owner@Example.com"}


def _bind(handler):
    for port in range(18700, 18800):  # sandbox test ports only
        try:
            return http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        except OSError:
            continue
    raise RuntimeError("no free test port in 18700-18799")


def _b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")


@pytest.fixture
def world(tmp_path, monkeypatch):
    for name in SECRETS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(signin, "MEMBERS", tmp_path / "config" / "members.json")
    google = {"claims": {}, "forms": []}

    class Token(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            form = urllib.parse.parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
            google["forms"].append({k: v[0] for k, v in form.items()})
            body = json.dumps({"id_token": "e30." + _b64(google["claims"]) + ".unsigned"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    servers = [_bind(Token)]
    monkeypatch.setattr(signin, "TOKEN_URL", f"http://127.0.0.1:{servers[0].server_port}/token")
    pages = {}
    for project in ("proj", "other"):
        directory = tmp_path / project / "page"
        source = tmp_path / f"{project}.md"
        source.write_text(f"## Progress\n\nPrivate {project} content.\n")
        generate(source, directory)
        complete(directory)
        (directory / "assets").mkdir(exist_ok=True)
        (directory / "assets" / "x.png").write_bytes(b"private proof")
        bus = cli.BUS_ROOT / project
        bus.mkdir(parents=True, exist_ok=True)
        base = f"/annotate/{project}/page"
        server = _bind(sync_server.make_handler(directory, bus_dir=bus, slug="page", public_base_path=base,
                                                skill_dir=sync_server.WEB_DIR))
        cli._save_state_for_project(project, {"project": project, "slugs": {"page": {
            "slug_dir": str(directory), "port": server.server_port, "transport": "funnel",
            "url": f"https://{HOST}{base}/"}}})
        servers.append(server)
        pages[project] = {"port": server.server_port, "base": base, "key": review_access.ensure_key(directory)}
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
    for thread in threads:
        thread.start()

    def request(project, path, cookie="", method="GET", body=None, host=HOST, **headers):
        page = pages[project]
        connection = http.client.HTTPConnection("127.0.0.1", page["port"], timeout=5)
        sent = {"Host": host, **({"Cookie": cookie} if cookie else {}), **headers}
        if host == HOST:
            sent.setdefault("Sec-Fetch-Site", "same-origin")
        if body is not None:
            sent["Content-Type"] = "application/json"
        route = path if path.startswith(signin.ROUTE) else page["base"] + "/" + path
        connection.request(method, route, body=json.dumps(body) if body is not None else None, headers=sent)
        response = connection.getresponse()
        result = response.status, response.headers, response.read().decode()
        connection.close()
        return result

    yield {"request": request, "pages": pages, "google": google}
    for server in servers:
        server.shutdown()
        server.server_close()
    for thread in threads:
        thread.join(timeout=5)


def _configure(monkeypatch):
    for name, value in SECRETS.items():
        monkeypatch.setenv(name, value)


def _cookies(headers) -> dict[str, str]:
    parsed = SimpleCookie()
    for value in headers.get_all("Set-Cookie") or []:
        parsed.load(value)
    return {name: morsel.value for name, morsel in parsed.items()}


def _sign_in(world, email, *, claims=None, next_path="/annotate/proj/page/#feedback=c1"):
    request, google = world["request"], world["google"]
    code, headers, _ = request("proj", signin.ROUTE + "/login?" + urllib.parse.urlencode({"next": next_path}))
    assert code == 302
    location = urllib.parse.urlsplit(headers["Location"])
    query = {k: v[0] for k, v in urllib.parse.parse_qs(location.query).items()}
    name = signin.FLOW_COOKIE + query["state"]
    flow = name + "=" + _cookies(headers)[name]
    google["claims"] = {"iss": "https://accounts.google.com", "aud": SECRETS["GOOGLE_OAUTH_CLIENT_ID"],
                        "exp": int(time.time()) + 3600, "email": email, "email_verified": True,
                        "name": "Guest Person", **(claims or {})}
    result = request("proj", signin.ROUTE + "/callback?" + urllib.parse.urlencode(
        {"code": "auth-code", "state": query["state"]}), cookie=flow, **{"Sec-Fetch-Site": "cross-site"})
    return query, result


def _session(headers) -> str:
    return signin.SESSION_COOKIE + "=" + _cookies(headers)[signin.SESSION_COOKIE]


def _seal_with(key, payload, monkeypatch):
    monkeypatch.setenv("ANNOTATE_SESSION_KEY", key)
    value = signin._seal(payload)
    monkeypatch.setenv("ANNOTATE_SESSION_KEY", SECRETS["ANNOTATE_SESSION_KEY"])
    return signin.SESSION_COOKIE + "=" + value


def test_full_google_flow_signs_in_a_member_and_returns_to_the_page(world, monkeypatch):
    _configure(monkeypatch)
    signin.change_member("add", GUEST, "proj")
    request, google = world["request"], world["google"]
    code, headers, body = request("proj", "")
    assert code == 200 and f'content="{signin.ROUTE}/login?next="' in body  # the shell goes to Google
    query, (code, headers, _) = _sign_in(world, GUEST)
    assert query["scope"] == "openid email profile" and query["code_challenge_method"] == "S256"
    assert query["redirect_uri"] == f"https://{HOST}/annotate/auth/callback"
    assert query["client_id"] == SECRETS["GOOGLE_OAUTH_CLIENT_ID"]
    form = google["forms"][-1]
    assert form["grant_type"] == "authorization_code" and form["code"] == "auth-code"
    assert form["redirect_uri"] == query["redirect_uri"] and form["client_secret"] == SECRETS["GOOGLE_OAUTH_CLIENT_SECRET"]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest()).decode().rstrip("=")
    assert challenge == query["code_challenge"]
    assert code == 302 and headers["Location"] == "/annotate/proj/page/#feedback=c1"
    issued = SimpleCookie()
    for value in headers.get_all("Set-Cookie"):
        issued.load(value)
    session = issued[signin.SESSION_COOKIE]
    assert session["path"] == "/" and session["samesite"] == "Lax" and session["httponly"] and session["secure"]
    assert int(session["max-age"]) == 30 * 86400 and not session["domain"]
    assert issued[signin.ASSET_COOKIE]["samesite"] == "None" and issued[signin.FLOW_COOKIE + query["state"]].value == ""
    cookie = _session(headers)
    code, _, body = request("proj", "api/identity", cookie)
    assert code == 200 and json.loads(body)["email"] == GUEST
    code, _, body = request("proj", "")
    assert 'name="annotate-signin"' in body  # no cookie, still sent to sign in
    code, _, body = request("proj", "", cookie)
    assert code == 200 and 'name="annotate-signin"' not in body
    code, _, body = request("proj", "api/comments", cookie, "POST", {"anchor_id": "s:progress:p1", "text": "Hi", "version": "v1"})
    assert code in (200, 201), body
    asset = signin.ASSET_COOKIE + "=" + _cookies(headers)[signin.ASSET_COOKIE]
    code, _, _ = request("proj", "assets/x.png", asset, Origin="null", **{"Sec-Fetch-Mode": "no-cors", "Sec-Fetch-Site": "cross-site"})
    assert code == 200
    code, _, _ = request("proj", "api/comments", asset)
    assert code == 403  # the SameSite=None twin opens images only


def test_owner_sees_every_project_and_a_member_is_blocked_from_another(world, monkeypatch):
    _configure(monkeypatch)
    signin.change_member("add", GUEST, "proj")  # the owner has no entry: ANNOTATE_OWNER_EMAIL
    request = world["request"]
    owner = _session(_sign_in(world, OWNER)[1][1])
    guest = _session(_sign_in(world, GUEST)[1][1])
    for project in ("proj", "other"):
        code, _, body = request(project, "api/identity", owner)
        assert code == 200 and json.loads(body)["email"] == OWNER
    assert signin.allowed(OWNER, "any-future-project")
    code, _, _ = request("other", "api/comments", guest)
    assert code == 403
    code, _, body = request("other", "", guest)
    assert f'content="{signin.ROUTE}/denied?next="' in body
    code, _, body = request("other", signin.ROUTE + "/denied?next=/annotate/other/page/", guest)
    assert code == 403 and "not shared with you" in body and GUEST in body
    assert "/annotate/auth/login?next=%2Fannotate%2Fother%2Fpage%2F" in body
    assert request("proj", "api/comments", guest)[0] == 200
    signin.MEMBERS.write_text('{"guest@example.com": "proj"')  # corrupt: shares nothing...
    assert request("proj", "api/comments", guest)[0] == 403
    for project in ("proj", "other"):  # ...but never locks the owner out
        assert request(project, "api/comments", owner)[0] == 200
        assert 'name="annotate-signin"' not in request(project, "", owner)[2]


def test_two_tabs_signing_in_at_once_both_finish(world, monkeypatch):
    _configure(monkeypatch)
    request = world["request"]
    flows = []
    for _ in range(2):
        _, headers, _ = request("proj", signin.ROUTE + "/login?next=/annotate/proj/page/")
        state = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(headers["Location"]).query))["state"]
        flows.append((state, signin.FLOW_COOKIE + state + "=" + _cookies(headers)[signin.FLOW_COOKIE + state]))
    jar = "; ".join(cookie for _, cookie in flows)
    world["google"]["claims"] = {"iss": "accounts.google.com", "aud": SECRETS["GOOGLE_OAUTH_CLIENT_ID"],
                                 "exp": int(time.time()) + 3600, "email": OWNER, "email_verified": True}
    for state, _ in flows:
        code, headers, _ = request("proj", signin.ROUTE + "/callback?" + urllib.parse.urlencode(
            {"code": "c", "state": state}), cookie=jar)
        assert code == 302 and signin.SESSION_COOKIE in _cookies(headers)


def test_removed_member_loses_access_at_once(world, monkeypatch):
    _configure(monkeypatch)
    signin.change_member("add", GUEST, "proj")
    signin.change_member("add", GUEST, "other")
    cookie = _session(_sign_in(world, GUEST)[1][1])
    assert world["request"]("proj", "api/comments", cookie)[0] == 200
    assert signin.change_member("remove", GUEST, "proj") == {GUEST: ["other"]}
    assert world["request"]("proj", "api/comments", cookie)[0] == 403
    assert world["request"]("other", "api/comments", cookie)[0] == 200
    assert signin.change_member("remove", GUEST, None) == {}
    assert world["request"]("other", "api/comments", cookie)[0] == 403


def test_forged_and_expired_cookies_are_refused(world, monkeypatch):
    _configure(monkeypatch)
    request = world["request"]
    now = int(time.time())
    forged = _seal_with("someone-elses-key", {"use": "session", "email": OWNER, "name": "", "exp": now + 3600}, monkeypatch)
    expired = _seal_with(SECRETS["ANNOTATE_SESSION_KEY"], {"use": "session", "email": OWNER, "name": "", "exp": now - 1}, monkeypatch)
    flow = _seal_with(SECRETS["ANNOTATE_SESSION_KEY"], {"use": "flow", "email": OWNER, "name": "", "exp": now + 3600}, monkeypatch)
    good = _seal_with(SECRETS["ANNOTATE_SESSION_KEY"], {"use": "session", "email": GUEST, "name": "", "exp": now + 3600}, monkeypatch)
    body, signature = good.split("=", 1)[1].split(".")
    swapped = signin.SESSION_COOKIE + "=" + _b64({"use": "session", "email": OWNER, "name": "", "exp": now + 3600}) + "." + signature
    for cookie in (forged, expired, flow, swapped):
        assert request("proj", "api/comments", cookie)[0] == 403
        assert 'content="/annotate/auth/login?next="' in request("proj", "", cookie)[2]


@pytest.mark.parametrize("claims", [{"aud": "someone-else"}, {"iss": "https://evil.example"},
                                    {"exp": 1000}, {"email_verified": False}, {"email_verified": "true"}])
def test_callback_refuses_an_id_token_google_did_not_vouch_for(world, monkeypatch, claims):
    _configure(monkeypatch)
    code, headers, body = _sign_in(world, OWNER, claims=claims)[1]
    assert code == 403 and "did not confirm" in body and signin.SESSION_COOKIE not in _cookies(headers)


def test_callback_refuses_a_wrong_state_and_an_offsite_return(world, monkeypatch):
    _configure(monkeypatch)
    request = world["request"]
    _, headers, _ = request("proj", signin.ROUTE + "/login?next=//evil.example/")
    flow = "; ".join(f"{name}={value}" for name, value in _cookies(headers).items())
    code, headers, _ = request("proj", signin.ROUTE + "/callback?code=x&state=wrong", cookie=flow)
    assert code == 400 and signin.SESSION_COOKIE not in _cookies(headers)
    assert request("proj", signin.ROUTE + "/callback?code=x&state=%C3%A9", cookie=flow)[0] == 400
    assert world["google"]["forms"] == []  # Google was never asked
    assert _sign_in(world, OWNER, next_path="//evil.example/")[1][1]["Location"] == "/"


def test_review_links_still_work_with_sign_in_on(world, monkeypatch):
    _configure(monkeypatch)
    request, page = world["request"], world["pages"]["proj"]
    code, headers, _ = request("proj", "api/reviewer/session", method="POST", body={"key": page["key"], "name": "Reviewer A"})
    assert code == 200
    cookie = headers.get_all("Set-Cookie")[0].split(";", 1)[0]
    code, _, body = request("proj", "api/identity", cookie)
    assert code == 200 and json.loads(body)["name"] == "Reviewer A"
    assert 'name="annotate-signin"' not in request("proj", "", cookie)[2]


def test_local_agent_and_tailnet_calls_never_sign_in(world, monkeypatch):
    _configure(monkeypatch)
    request, port = world["request"], world["pages"]["proj"]["port"]
    code, _, _ = request("proj", "api/comments", host=f"127.0.0.1:{port}", **{"X-Annotate-Agent": "agent:test"})
    assert code == 200
    code, _, body = request("proj", "", host=f"127.0.0.1:{port}")
    assert 'name="annotate-signin"' not in body
    code, _, body = request("proj", "api/identity", **{"Tailscale-User-Login": "changl@github"})
    assert code == 200 and json.loads(body)["email"] == "changl@github"
    assert request("proj", signin.ROUTE + "/login", host=f"127.0.0.1:{port}")[0] == 404


def test_without_all_four_values_nothing_changes(world, monkeypatch):
    request, page = world["request"], world["pages"]["proj"]
    _configure(monkeypatch)
    monkeypatch.delenv("ANNOTATE_OWNER_EMAIL")
    assert not signin.configured()  # three secrets, no owner: still off
    monkeypatch.setenv("ANNOTATE_OWNER_EMAIL", OWNER)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET")
    cookie = _seal_with(SECRETS["ANNOTATE_SESSION_KEY"], {"use": "session", "email": OWNER, "name": "",
                                                          "exp": int(time.time()) + 3600}, monkeypatch)
    monkeypatch.delenv("ANNOTATE_SESSION_KEY")
    assert not signin.configured()
    code, _, body = request("proj", "", cookie)
    assert code == 200 and 'name="annotate-signin"' not in body
    assert request("proj", "api/comments", cookie)[0] == 403
    for route in ("/login", "/callback?code=x&state=y", "/denied"):
        assert request("proj", signin.ROUTE + route)[0] == 404
    code, headers, _ = request("proj", "api/reviewer/session", method="POST", body={"key": page["key"]})
    assert code == 200
    assert request("proj", "api/comments", headers.get_all("Set-Cookie")[0].split(";", 1)[0])[0] == 200


def test_member_command_adds_lists_and_removes(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(signin, "MEMBERS", tmp_path / "members.json")

    def run(*argv):
        args = cli.build_parser().parse_args(["member", *argv])
        return args.func(args)
    assert run("add", GUEST) == 1 and not signin.MEMBERS.exists()  # a forgotten project grants nothing
    assert "needs a project" in capsys.readouterr().out
    assert run("add", "Guest@Example.com", "proj") == 0
    assert run("add", GUEST, "other") == 0
    assert run("add", "x@example.com", "proj") == 0
    capsys.readouterr()
    assert run("list", GUEST) == 0
    assert capsys.readouterr().out.splitlines() == [f"{GUEST}  other, proj"]
    assert run("remove", GUEST, "other") == 0
    assert signin.load_members() == {GUEST: ["proj"], "x@example.com": ["proj"]}
    assert signin.MEMBERS.stat().st_mode & 0o777 == 0o600
    assert run("remove", GUEST) == 0 and GUEST not in signin.load_members()
    assert run("add", "not-an-email", "proj") == 1 and run("remove") == 1
    signin.MEMBERS.write_text('{"Mixed@Example.com": ["proj"]}')  # hand-edited case still matches
    assert signin.allowed("mixed@example.com", "proj") and not signin.allowed("mixed@example.com", "other")
    signin.MEMBERS.write_text('{"x@example.com": "proj"}')
    assert not signin.allowed("x@example.com", "p")  # a malformed list shares nothing
