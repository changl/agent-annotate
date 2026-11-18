"""Google sign-in for Funnel pages, off until its three secrets are in the environment.

The ID token comes straight from Google's token endpoint over TLS, which
stands in for its signature (OpenID Connect Core 3.1.3.7, step 6), so no
crypto library is needed. The session cookie is HMAC-signed like the
review-link cookie in review_access.py. Members are read on every request,
so removing one takes effect at once.
"""

import base64
import hashlib
import hmac
import html
import json
import os
import secrets
import time
import urllib.parse
import urllib.request
from http.cookies import CookieError, SimpleCookie

from .paths import CONFIG_DIR
from .review_access import _valid_name

ROUTE = "/annotate/auth"
SESSION_COOKIE = "__Host-annotate_session"
ASSET_COOKIE = SESSION_COOKIE + "_assets"  # SameSite=None twin, honoured only for sandboxed image loads
FLOW_COOKIE = "annotate_signin_"  # + state, so two tabs signing in at once keep their own
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
SESSION_SECONDS = 30 * 86400
MEMBERS = CONFIG_DIR / "members.json"
# The owner sees every project and is pinned here, so a broken members.json never locks them out.
_ENV = ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "ANNOTATE_SESSION_KEY", "ANNOTATE_OWNER_EMAIL")


def configured() -> bool:
    return all(os.environ.get(name) for name in _ENV)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _signature(body: str) -> str:
    return hmac.new(os.environ["ANNOTATE_SESSION_KEY"].encode(), body.encode(), hashlib.sha256).hexdigest()


def _seal(payload: dict) -> str:
    body = _b64(json.dumps(payload).encode())
    return body + "." + _signature(body)


def _open(header: str, name: str, use: str) -> dict | None:
    try:
        cookies = SimpleCookie()
        cookies.load(header)
        value = cookies[name].value
        if len(value) > 4096:
            return None
        body, signature = value.split(".", 1)
        if not hmac.compare_digest(signature.encode(), _signature(body).encode()):
            return None
        payload = json.loads(_unb64(body))
        if (not isinstance(payload, dict) or payload.get("use") != use
                or type(payload.get("exp")) is not int or payload["exp"] < time.time()):
            return None
        return payload
    except (ValueError, KeyError, TypeError, CookieError):
        return None


def session(header: str, *, asset: bool = False) -> tuple[str, str]:
    """The signed-in (email, name), or ("", "")."""
    payload = _open(header, ASSET_COOKIE if asset else SESSION_COOKIE, "session") if configured() else None
    if not payload or not isinstance(payload.get("email"), str) or not isinstance(payload.get("name"), str):
        return "", ""
    return payload["email"], payload["name"]


def load_members() -> dict[str, list[str]]:
    try:
        data = json.loads(MEMBERS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict) or not all(
            isinstance(email, str) and isinstance(projects, list) and all(isinstance(p, str) for p in projects)
            for email, projects in data.items()):
        raise ValueError(f"{MEMBERS} must map emails to lists of projects")
    members: dict[str, list[str]] = {}
    for email, projects in data.items():  # hand-edited keys may differ only in case
        members.setdefault(email.strip().lower(), []).extend(projects)
    return members


def allowed(email: str, project: str) -> bool:
    email = email.lower()
    owner = os.environ.get("ANNOTATE_OWNER_EMAIL", "").strip().lower()
    if owner and email == owner:
        return True
    try:
        return project in load_members().get(email, [])
    except (OSError, ValueError):
        return False  # an unreadable list shares nothing (the owner is checked above)


def member(header: str, project: str, *, asset: bool = False) -> tuple[str, str]:
    """The signed-in person when this project is shared with them, else ("", "")."""
    email, name = session(header, asset=asset)
    return (email, name) if email and allowed(email, project) else ("", "")


def change_member(action: str, email: str, project: str | None = None) -> dict[str, list[str]]:
    """add one email to one project, or remove it from one project (no project: from all)."""
    email = email.strip().lower()
    if "@" not in email or any(c.isspace() for c in email):
        raise ValueError("member must be an email address")
    if action == "add" and not project:
        raise ValueError("member add needs a project; the owner is ANNOTATE_OWNER_EMAIL and sees every project")
    members = load_members()
    projects = members.get(email, [])
    if action == "add":
        members[email] = sorted(set(projects) | {project})
    elif project:
        members[email] = [p for p in projects if p != project]
    if action == "remove" and (not project or not members.get(email)):
        members.pop(email, None)
    from .updates import _atomic_json
    _atomic_json(MEMBERS, members)
    return members


def cmd_member(args) -> int:
    try:
        if args.action == "list":
            members = load_members()
            if args.email:
                members = {k: v for k, v in members.items() if k == args.email.strip().lower()}
        elif not args.email:
            raise ValueError(f"member {args.action} needs an email")
        else:
            members = change_member(args.action, args.email, args.project)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 1
    for email, projects in sorted(members.items()):
        print(email + "  " + ", ".join(projects))
    return 0


def _next(value: str) -> str:
    # Only a path on this host, so the callback never sends anyone elsewhere.
    ok = value.startswith("/") and not value.startswith("//") and all(32 < ord(c) < 127 and c != "\\" for c in value)
    return value if ok else "/"


def _page(code: int, text: str, link: tuple[str, str] | None = None) -> tuple[int, dict, bytes]:
    body = ('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            f'<title>Agent Annotate</title><p>{html.escape(text)}</p>')
    if link:
        body += f'<p><a href="{html.escape(link[0])}">{html.escape(link[1])}</a></p>'
    return code, {}, body.encode()


def _exchange(code: str, verifier: str, redirect_uri: str) -> tuple[str, str]:
    client_id = os.environ["GOOGLE_OAUTH_CLIENT_ID"]
    form = urllib.parse.urlencode({
        "code": code, "client_id": client_id, "client_secret": os.environ["GOOGLE_OAUTH_CLIENT_SECRET"],
        "redirect_uri": redirect_uri, "grant_type": "authorization_code", "code_verifier": verifier}).encode()
    with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=form), timeout=10) as response:
        claims = json.loads(_unb64(json.loads(response.read(65536))["id_token"].split(".")[1]))
    email, name = claims.get("email"), claims.get("name")
    if (claims.get("aud") != client_id or claims.get("iss") not in ISSUERS
            or type(claims.get("exp")) is not int or claims["exp"] < time.time()
            or claims.get("email_verified") is not True or not isinstance(email, str) or "@" not in email):
        raise ValueError("Google did not confirm this account")
    return email.lower(), name if _valid_name(name) else ""


def handle(route: str, query: str, cookie: str, origin: str) -> tuple[int, dict, bytes]:
    """Serve ROUTE/login, ROUTE/callback and ROUTE/denied for `origin` (https://host)."""
    params = urllib.parse.parse_qs(query)

    def first(name: str) -> str:
        return (params.get(name) or [""])[0]

    redirect_uri = origin + ROUTE + "/callback"
    flow_attributes = f"Path={ROUTE}/; HttpOnly; Secure; SameSite=Lax"
    if route == ROUTE + "/login":
        state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
        flow = _seal({"use": "flow", "state": state, "verifier": verifier,
                      "next": _next(first("next")), "exp": int(time.time()) + 600})
        url = AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": os.environ["GOOGLE_OAUTH_CLIENT_ID"], "redirect_uri": redirect_uri,
            "response_type": "code", "scope": "openid email profile", "state": state,
            "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),
            "code_challenge_method": "S256", "prompt": "select_account"})
        return 302, {"Location": url, "Set-Cookie": f"{FLOW_COOKIE}{state}={flow}; Max-Age=600; {flow_attributes}"}, b""
    if route == ROUTE + "/callback":
        flow = _open(cookie, FLOW_COOKIE + first("state"), "flow")
        if not flow or not first("code") or not hmac.compare_digest(first("state").encode(), flow["state"].encode()):
            return _page(400, "Sign-in did not finish. Open the page again to retry.")
        try:
            email, name = _exchange(first("code"), flow["verifier"], redirect_uri)
        except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError):
            return _page(403, "Google did not confirm this account. Open the page again to retry.")
        value = _seal({"use": "session", "email": email, "name": name, "exp": int(time.time()) + SESSION_SECONDS})
        attributes = f"Path=/; Max-Age={SESSION_SECONDS}; HttpOnly; Secure"
        return 302, {"Location": flow["next"], "Set-Cookie": [
            f"{SESSION_COOKIE}={value}; {attributes}; SameSite=Lax",
            f"{ASSET_COOKIE}={value}; {attributes}; SameSite=None",
            f"{FLOW_COOKIE}{flow['state']}=; Max-Age=0; {flow_attributes}"]}, b""
    if route == ROUTE + "/denied":
        email = session(cookie)[0]
        text = "This page is not shared with you." + (f" You are signed in as {email}." if email else "")
        return _page(403, text, (ROUTE + "/login?" + urllib.parse.urlencode({"next": _next(first("next"))}),
                                 "Use another Google account"))
    return _page(404, "Not found.")
