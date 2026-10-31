import http.server
import json
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.cookies import SimpleCookie

import pytest

from agent_annotate import cli, review_access, sync_server
from agent_annotate.pagegen import generate


def test_link_keys_and_cookies_are_private_scoped_and_tamper_resistant(tmp_path, monkeypatch):
    monkeypatch.setattr(review_access, "STATE_DIR", tmp_path / "private-state")
    directory = tmp_path / "repo" / "page"
    directory.mkdir(parents=True)
    content = directory / "content.html"
    content.write_text("Public page asset")
    key = review_access.ensure_key(directory)
    assert review_access.ensure_key(directory) == key
    key_path = review_access._key_path(directory)
    assert key_path.stat().st_mode & 0o777 == 0o600
    assert key_path.parent.stat().st_mode & 0o777 == 0o700
    assert not key_path.is_relative_to(tmp_path / "repo")
    assert list(directory.iterdir()) == [content]
    assert all(key not in path.read_text() for path in (tmp_path / "repo").rglob("*") if path.is_file())
    with pytest.raises(ValueError, match="invalid review link"):
        review_access.issue_cookie(directory, "wrong")
    cookie = review_access.issue_cookie(directory, key, "External reviewer")
    header = review_access.cookie_name(directory) + "=" + cookie
    email, name = review_access.identity(directory, header)
    assert email.startswith("reviewer:") and name == "External reviewer"
    assert review_access.identity(directory, header[:-1] + ("a" if header[-1] != "a" else "b")) == ("", "")
    other = tmp_path / "other"
    review_access.ensure_key(other)
    assert review_access.identity(other, header) == ("", "")
    asset_header = review_access.asset_cookie_name(directory) + "=" + cookie
    assert review_access.identity(directory, asset_header) == ("", "")
    assert review_access.identity(directory, asset_header, asset=True) == (email, name)
    assert review_access.identity(other, asset_header, asset=True) == ("", "")
    assert review_access.identity(directory, asset_header + "tampered", asset=True) == ("", "")


def test_simultaneous_sessions_receive_one_complete_private_key(tmp_path, monkeypatch):
    monkeypatch.setattr(review_access, "STATE_DIR", tmp_path / "private-state")
    directory = tmp_path / "repo" / "page"
    with ThreadPoolExecutor(max_workers=8) as pool:
        keys = list(pool.map(lambda _: review_access.ensure_key(directory), range(20)))
    assert len(set(keys)) == 1
    assert not directory.exists()
    assert list((review_access.STATE_DIR / "review-keys").iterdir()) == [review_access._key_path(directory)]


def test_reopening_review_link_preserves_identity_and_allows_display_name_edit(tmp_path):
    directory = tmp_path / "page"
    key = review_access.ensure_key(directory)
    cookie = review_access.issue_cookie(directory, key, "External reviewer")
    header = review_access.cookie_name(directory) + "=" + cookie
    original = review_access.identity(directory, header)
    reopened = review_access.issue_cookie(directory, key, existing_cookie=header)
    reopened_header = review_access.cookie_name(directory) + "=" + reopened
    assert review_access.identity(directory, reopened_header) == original
    renamed = review_access.issue_cookie(directory, key, "Edited name", reopened_header)
    assert review_access.identity(directory, review_access.cookie_name(directory) + "=" + renamed) == (original[0], "Edited name")
    with pytest.raises(ValueError, match="invalid review link"):
        review_access.issue_cookie(directory, "wrong", existing_cookie=reopened_header)


def test_reopening_tampered_expired_or_other_page_cookie_never_reuses_identity(tmp_path, monkeypatch):
    directory = tmp_path / "page"
    key = review_access.ensure_key(directory)
    monkeypatch.setattr(review_access.time, "time", lambda: 1000)
    cookie = review_access.issue_cookie(directory, key, "External reviewer")
    header = review_access.cookie_name(directory) + "=" + cookie
    original = review_access.identity(directory, header)
    tampered = header[:-1] + ("a" if header[-1] != "a" else "b")
    assert review_access.identity(directory, tampered) == ("", "")
    renewed = review_access.issue_cookie(directory, key, existing_cookie=tampered)
    assert review_access.identity(directory, review_access.cookie_name(directory) + "=" + renewed)[0] != original[0]
    other = tmp_path / "other"
    other_key = review_access.ensure_key(other)
    reused = review_access.issue_cookie(other, other_key, existing_cookie=header)
    assert review_access.identity(other, review_access.cookie_name(other) + "=" + reused)[0] != original[0]
    monkeypatch.setattr(review_access.time, "time", lambda: 1000 + 30 * 86400 + 1)
    assert review_access.identity(directory, header) == ("", "")
    renewed = review_access.issue_cookie(directory, key, existing_cookie=header)
    assert review_access.identity(directory, review_access.cookie_name(directory) + "=" + renewed)[0] != original[0]


def test_long_unicode_reviewer_name_round_trips(tmp_path):
    directory = tmp_path / "page"
    key = review_access.ensure_key(directory)
    name = "😀" * 80
    cookie = review_access.issue_cookie(directory, key, name)
    assert review_access.identity(directory, review_access.cookie_name(directory) + "=" + cookie)[1] == name


@pytest.mark.parametrize("legacy", [False, True])
def test_funnel_browser_needs_private_link_for_content_and_feedback(tmp_path, legacy):
    directory = tmp_path / "page"
    source = tmp_path / "page.md"
    source.write_text("## Progress\n\nPrivate project content.\n")
    generate(source, directory)
    for relative in ("assets/x.png", "assets/proof.webm", "assets/manifest.json", "assets/plan.html", "attachments/x.png"):
        target = directory / relative
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(b"private proof")
    if legacy:
        (directory / "versions" / "v1.html").write_text(
            '<html><body><p data-anchor-id="s:progress:p1">Private project content.</p></body></html>')
    key = review_access.ensure_key(directory)
    bus = cli.BUS_ROOT / "test-funnel"
    bus.mkdir(parents=True, exist_ok=True)
    handler = sync_server.make_handler(directory, bus_dir=bus, slug="page", public_base_path="/page", skill_dir=sync_server.WEB_DIR)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    record = {"slug_dir": str(directory), "port": server.server_port, "transport": "funnel", "url": "https://host.ts.net/page/"}
    cli._save_state_for_project("test-funnel", {"project": "test-funnel", "slugs": {"page": record}})
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def request(route, payload=None, cookie=None, origin="https://host.ts.net", *, referer=None, method=None, mode=None):
        headers = {"Host": "host.ts.net", "Sec-Fetch-Site": "cross-site" if origin != "https://host.ts.net" else "same-origin"}
        if origin is not None:
            headers["Origin"] = origin
        if referer is not None:
            headers["Referer"] = referer
        if mode is not None:
            headers["Sec-Fetch-Mode"] = mode
        if cookie:
            headers["Cookie"] = cookie
        raw = json.dumps(payload).encode() if payload is not None else None
        if raw is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/page/{route}", data=raw, headers=headers, method=method)
        return urllib.request.urlopen(req, timeout=3)
    try:
        with request("") as response:
            assert 'id="drawer-tabs"' in response.read().decode()
        # The accepted shell's fonts are bootstrap chrome, like its CSS.
        with request("RobotoVariable.woff2") as response:
            assert response.headers["Content-Type"].startswith("font/woff2")
        with pytest.raises(urllib.error.HTTPError) as error:
            request("content")
        assert error.value.code == 403
        with pytest.raises(urllib.error.HTTPError) as error:
            request("assets/x.png", origin="null", referer="https://host.ts.net/page/assets/plan.html")
        assert error.value.code == 403
        with pytest.raises(urllib.error.HTTPError):
            request("api/reviewer/session", {"key": "wrong"})
        with request("api/reviewer/session", {"key": key, "name": "External reviewer"}) as response:
            issued = response.headers.get_all("Set-Cookie")
            assert len(issued) == 2
            parsed = SimpleCookie()
            for value in issued:
                parsed.load(value)
            review = parsed[review_access.cookie_name(directory)]
            asset = parsed[review_access.asset_cookie_name(directory)]
            assert asset.value == review.value
            assert review["samesite"] == "Strict" and review["path"] == "/page/"
            assert asset["samesite"] == "None" and asset["path"] == "/page/assets/"
            assert asset["secure"] and asset["httponly"] and not asset["domain"]
            asset_cookie = asset.key + "=" + asset.value
            cookie = response.headers["Set-Cookie"]
            assert "HttpOnly; Secure; SameSite=Strict" in cookie
            cookie = cookie.split(";", 1)[0]
        own_referer = "https://host.ts.net/page/assets/plan.html"
        for route in ("assets/x.png", "assets/proof.webm"):
            for method in ("GET", "HEAD"):
                with request(route, cookie=asset_cookie, origin="null", referer=own_referer, method=method) as response:
                    assert response.status == 200
                    assert response.headers.get("Access-Control-Allow-Origin") is None
                    assert response.headers.get("Access-Control-Allow-Credentials") is None
            with request(route, cookie=cookie) as response:
                assert response.status == 200
        for origin in (None, "null"):
            with request("assets/x.png", cookie=asset_cookie, origin=origin, referer=own_referer) as response:
                assert response.status == 200
            for referer in (None, "https://foreign.test/page"):
                with pytest.raises(urllib.error.HTTPError) as error:
                    request("assets/x.png", cookie=asset_cookie, origin=origin, referer=referer, mode="cors")
                assert error.value.code == 403
                assert error.value.headers.get("Access-Control-Allow-Origin") is None
                with request("assets/x.png", cookie=asset_cookie, origin=origin, referer=referer, mode="no-cors") as response:
                    assert response.status == 200
                    assert response.headers.get("Access-Control-Allow-Origin") is None
        for route in ("api/comments", "api/identity", "content", "assets/plan.html", "assets/manifest.json", "attachments/x.png"):
            with pytest.raises(urllib.error.HTTPError) as error:
                request(route, cookie=asset_cookie, referer=own_referer)
            assert error.value.code == 403
        for method in ("POST", "PUT", "OPTIONS"):
            with pytest.raises(urllib.error.HTTPError) as error:
                request("assets/x.png", cookie=asset_cookie, referer=own_referer, method=method)
            assert error.value.code == 403
        with pytest.raises(urllib.error.HTTPError) as error:
            request("assets/x.png", cookie=asset_cookie + "tampered", origin="null", referer=own_referer)
        assert error.value.code == 403
        with request("content", cookie=cookie) as response:
            assert "Private project content." in response.read().decode()
        with request("api/comments", {"anchor_id": "s:progress:p1", "text": "Useful feedback", "version": "v1"}, cookie) as response:
            cid = json.load(response)["id"]
        store = json.loads((directory / "comments.json").read_text())
        comment = store["anchors"]["s:progress:p1"][0]
        assert comment["id"] == cid and comment["author_name"] == "External reviewer"
        with request("api/read-state", {"items": [{"id": cid, "sig": "read-before-reopen"}]}, cookie) as response:
            read_author = json.load(response)["author"]
        with request("api/reviewer/session", {"key": key}, cookie) as response:
            reopened_cookie = response.headers["Set-Cookie"].split(";", 1)[0]
        with request("api/read-state", cookie=reopened_cookie) as response:
            read_state = json.load(response)
        assert read_state["author"] == read_author == comment["author"]
        assert read_state["read"][cid]["sig"] == "read-before-reopen"
        assert review_access.identity(directory, reopened_cookie)[1] == "External reviewer"
        with pytest.raises(urllib.error.HTTPError):
            request("api/comments", {"text": "CSRF"}, cookie, "https://foreign.test")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
