"""Google sign-in for Funnel pages, driven end to end against a fake Google token endpoint."""
import base64
import hashlib
import http.client
import http.server
import json
import os
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.parse
from http.cookies import SimpleCookie
from pathlib import Path

import pytest
from review_fixtures import complete
from test_pagegen_images import png

from agent_annotate import cli, review_access, signin, sync_server
from agent_annotate.pagegen import generate

HOST = "host.ts.net"
OWNER, GUEST = "owner@example.com", "guest@example.com"
SECRETS = {"GOOGLE_OAUTH_CLIENT_ID": "client-1.apps.googleusercontent.com",
           "GOOGLE_OAUTH_CLIENT_SECRET": "test-client-secret", "ANNOTATE_SESSION_KEY": "test-session-key",
           "ANNOTATE_OWNER_EMAIL": "Owner@Example.com"}
PREFIX = "signin-test-"  # project names no other test uses
PROJ, OTHER = PREFIX + "proj", PREFIX + "other"


class _DeferredTLS(http.server.ThreadingHTTPServer):
    """The TLS handshake runs on the request's own thread, so a client that connects and
    sends nothing cannot hold up the accept loop, other requests or shutdown()."""

    def finish_request(self, request, client_address):
        request.settimeout(10)
        try:
            request.do_handshake()
        except (OSError, ssl.SSLError):
            return
        request.settimeout(None)
        super().finish_request(request, client_address)


def _bind(handler, server=http.server.ThreadingHTTPServer):
    for port in range(18700, 18800):  # sandbox test ports only
        try:
            return server(("127.0.0.1", port), handler)
        except OSError:
            continue
    raise RuntimeError("no free test port in 18700-18799")


def _b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")


@pytest.fixture
def world(request, monkeypatch):
    # The fixture owns its files: nothing stays behind in pytest's kept tmp dirs.
    with tempfile.TemporaryDirectory(prefix="annotate-signin-") as root:
        yield from _world(Path(root), monkeypatch, tls=getattr(request, "param", None) == "tls")


def _world(tmp_path, monkeypatch, tls):
    """Two Funnel pages and a stand-in Google. tls=True serves them over https, as a real browser needs."""
    for name in SECRETS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(signin, "MEMBERS", tmp_path / "config" / "members.json")
    google = {"claims": {}, "forms": [], "accounts": []}
    context = None
    if tls:
        cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
        try:
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                            "-subj", "/CN=" + HOST, "-keyout", str(key), "-out", str(cert)],
                           check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError):
            pytest.skip("openssl is needed for the https test pages")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)

    class Token(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            """Google's account chooser: the next account in google["accounts"] picks itself."""
            query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
            email = google["accounts"].pop(0)
            google["claims"] = {"iss": "https://accounts.google.com", "aud": SECRETS["GOOGLE_OAUTH_CLIENT_ID"],
                                "exp": int(time.time()) + 3600, "email": email, "email_verified": True, "name": "Person"}
            self.send_response(302)
            self.send_header("Location", query["redirect_uri"] + "?" + urllib.parse.urlencode(
                {"code": "auth-code", "state": query["state"]}))
            self.end_headers()

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
    monkeypatch.setattr(signin, "AUTH_URL", f"http://127.0.0.1:{servers[0].server_port}/auth")
    # Nothing shared is left behind: bus and review keys live in tmp_path, and the
    # only shared files (the two state records) use names no other test uses and go at teardown.
    monkeypatch.setattr(review_access, "STATE_DIR", tmp_path / "state")
    pages = {}
    for key in ("proj", "other"):
        project = PREFIX + key
        directory = tmp_path / key / "page"
        source = tmp_path / f"{key}.md"
        (tmp_path / f"{key}-proof.png").write_bytes(png(240, 160, (30, 120, 200)))
        source.write_text(f"## Progress\n\nPrivate {key} content.\n\n![Proof]({key}-proof.png)\n")
        generate(source, directory)
        complete(directory)
        (directory / "assets").mkdir(exist_ok=True)
        (directory / "assets" / "x.png").write_bytes(png(8, 8))
        bus = tmp_path / "bus" / project
        bus.mkdir(parents=True)
        base = f"/annotate/{key}/page"
        server = _bind(sync_server.make_handler(directory, bus_dir=bus, slug="page", public_base_path=base,
                                                skill_dir=sync_server.WEB_DIR),
                       _DeferredTLS if context else http.server.ThreadingHTTPServer)
        if context:
            server.socket = context.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
        # Over https the browser sends the port in Host, so the published URL carries it.
        public = f"{HOST}:{server.server_port}" if tls else HOST
        cli._save_state_for_project(project, {"project": project, "slugs": {"page": {
            "slug_dir": str(directory), "port": server.server_port, "transport": "funnel",
            "url": f"https://{public}{base}/"}}})
        servers.append(server)
        pages[key] = {"port": server.server_port, "base": base, "key": review_access.ensure_key(directory),
                      "host": public, "dir": directory}
    threads = [threading.Thread(target=s.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True) for s in servers]
    for thread in threads:
        thread.start()

    def request(project, path, cookie="", method="GET", body=None, host=None, **headers):
        page = pages[project]
        host = host or page["host"]
        connection = (http.client.HTTPSConnection("127.0.0.1", page["port"], timeout=5,
                                                  context=ssl._create_unverified_context()) if tls
                      else http.client.HTTPConnection("127.0.0.1", page["port"], timeout=5))
        sent = {"Host": host, **({"Cookie": cookie} if cookie else {}), **headers}
        if host == page["host"]:
            sent.setdefault("Sec-Fetch-Site", "same-origin")
        if body is not None:
            sent["Content-Type"] = "application/json"
        route = path if path.startswith(signin.ROUTE) else page["base"] + "/" + path
        connection.request(method, route, body=json.dumps(body) if body is not None else None, headers=sent)
        response = connection.getresponse()
        raw = response.read()
        result = response.status, response.headers, (raw if raw.startswith(b"\x89PNG") else raw.decode())
        connection.close()
        return result

    try:
        yield {"request": request, "pages": pages, "google": google}
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=5)
        for key in pages:
            (cli.STATE_DIR / f"{PREFIX}{key}.json").unlink(missing_ok=True)


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
    signin.change_member("add", GUEST, PROJ)
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
    signin.change_member("add", GUEST, PROJ)  # the owner has no entry: ANNOTATE_OWNER_EMAIL
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
    signin.MEMBERS.write_text('{"guest@example.com": "' + PROJ + '"')  # corrupt: shares nothing...
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
    signin.change_member("add", GUEST, PROJ)
    signin.change_member("add", GUEST, OTHER)
    cookie = _session(_sign_in(world, GUEST)[1][1])
    assert world["request"]("proj", "api/comments", cookie)[0] == 200
    assert signin.change_member("remove", GUEST, PROJ) == {GUEST: [OTHER]}
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


@pytest.mark.parametrize("world", ["tls"], indirect=True)
def test_an_idle_connection_does_not_stall_the_https_pages(world):
    with socket.create_connection(("127.0.0.1", world["pages"]["proj"]["port"])):  # connects, never says hello
        assert world["request"]("proj", "")[0] == 200


def test_page_servers_fill_missing_values_from_infisical(monkeypatch, tmp_path):
    toml = tmp_path / "projects.toml"
    monkeypatch.setattr(signin, "PROJECTS_TOML", toml)
    signin.load_from_infisical()  # no projects.toml: nothing asked, still off
    toml.write_text('[signin]\nkeychain_service = "svc"\nkeychain_account = "acct"\n'
                    'project_id = "p1"\nenvironment = "dev"\npath = "/projects/x"\n')
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, '{"clientId": "id", "clientSecret": "cs"}', "")

    class Response:
        def __init__(self, data):
            self.data = json.dumps(data).encode()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, limit):
            return self.data

    def urlopen(request, timeout):
        calls.append(request.full_url)
        if request.full_url.endswith("universal-auth/login"):
            assert json.loads(request.data) == {"clientId": "id", "clientSecret": "cs"}
            return Response({"accessToken": "tok"})
        assert request.get_header("Authorization") == "Bearer tok"
        return Response({"secrets": [{"secretKey": k, "secretValue": v} for k, v in SECRETS.items()]
                         + [{"secretKey": "githubaa", "secretValue": "not-ours"}]})
    monkeypatch.setattr(signin.subprocess, "run", run)
    monkeypatch.setattr(signin.urllib.request, "urlopen", urlopen)
    for name in (*SECRETS, "githubaa"):  # undo then removes what the call sets
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANNOTATE_OWNER_EMAIL", "kept@example.com")  # the environment wins
    signin.load_from_infisical()
    assert signin.configured() and os.environ["ANNOTATE_OWNER_EMAIL"] == "kept@example.com"
    assert os.environ["ANNOTATE_SESSION_KEY"] == SECRETS["ANNOTATE_SESSION_KEY"] and "githubaa" not in os.environ
    assert calls[0][-5:] == ["-s", "svc", "-a", "acct", "-w"]
    assert "workspaceId=p1&environment=dev&secretPath=%2Fprojects%2Fx" in calls[2]


def test_member_command_adds_lists_and_removes(capsys, monkeypatch):
    with tempfile.TemporaryDirectory(prefix="annotate-members-") as root:  # not pytest's kept tmp dirs
        monkeypatch.setattr(signin, "MEMBERS", Path(root) / "members.json")
        _member_command(capsys)


def _member_command(capsys):

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
