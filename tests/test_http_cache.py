"""Wire-level caching, compression and HTTP/1.1 framing on isolated servers."""

import gzip
import hashlib
import http.client
import threading
from contextlib import contextmanager

import pytest

from agent_annotate.sync_server import ReviewHTTPServer, _asset_bytes, _mtime_stamp, make_handler


@pytest.fixture
def server(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "shell.js").write_bytes(b"const message = 'hello';\n" * 300)
    (web / "daisyui.css").write_text("@font-face {src:url(RobotoVariable.ttf)}")
    (web / "RobotoVariable.ttf").write_bytes(b"font version one")
    (tmp_path / "comments.json").write_text('{"schema_version":2,"anchors":{},"archived":{}}')
    (tmp_path / "current.meta.json").write_text('{"current":"v1","history":[]}')
    (tmp_path / "current.html").write_text("<html><body>Review</body></html>")
    handler = make_handler(tmp_path, v2_mode=True, skill_dir=web, public_base_path="/review", slug="review")
    httpd = ReviewHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd, tmp_path, web
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=2)


@contextmanager
def connection(server):
    conn = http.client.HTTPConnection(*server[0].server_address, timeout=2)
    try:
        yield conn
    finally:
        conn.close()


def request(conn, path, *, method="GET", headers=None, body=None):
    conn.request(method, path, body=body, headers=headers or {})
    response = conn.getresponse()
    data = response.read()
    assert response.version == 11
    assert response.getheader("X-Content-Type-Options") == "nosniff"
    assert response.getheader("Content-Length") is not None
    if method != "HEAD" and response.status not in (204, 304):
        assert int(response.getheader("Content-Length")) == len(data)
    return response, data


def test_stamped_assets_validate_bytes_and_keep_immutable_policy_on_304(server):
    _, _, web = server
    path = f"/review/assets/{_mtime_stamp(web / 'shell.js')}/shell.js"
    with connection(server) as conn:
        first, data = request(conn, path)
        assert first.status == 200 and data == (web / "shell.js").read_bytes()
        assert first.getheader("Cache-Control") == "public, max-age=31536000, immutable"
        etag = first.getheader("ETag")
        assert etag == '"' + hashlib.sha256(data).hexdigest() + '"'
        sock = conn.sock
        cached, body = request(conn, path, headers={"If-None-Match": '"other", W/' + etag})
        assert cached.status == 304 and body == b""
        assert cached.getheader("Content-Length") == str(len(data))
        assert cached.getheader("Cache-Control") == first.getheader("Cache-Control")
        assert conn.sock is sock
        (web / "shell.js").write_bytes(b"new bytes")
        stale, _ = request(conn, path)
        assert stale.status == 404 and stale.getheader("Cache-Control") == "no-store"
        fake, _ = request(conn, "/review/assets/0/shell.js")
        assert fake.status == 404


def test_css_fonts_have_independent_validated_hashes(server):
    _, _, web = server
    css = web / "daisyui.css"
    stamp = _mtime_stamp(css)
    with connection(server) as conn:
        response, data = request(conn, f"/review/assets/{stamp}/daisyui.css")
        assert response.status == 200
        font_stamp = _mtime_stamp(web / "RobotoVariable.ttf")
        assert f"url(../{font_stamp}/RobotoVariable.ttf)".encode() in data
        assert data == _asset_bytes(css)
        font, body = request(conn, f"/review/assets/{font_stamp}/RobotoVariable.ttf")
        assert font.status == 200 and body == b"font version one"
        assert "immutable" in font.getheader("Cache-Control")
        (web / "RobotoVariable.ttf").write_bytes(b"font version two")
        assert _mtime_stamp(css) != stamp
        assert request(conn, f"/review/assets/{stamp}/daisyui.css")[0].status == 404


@pytest.mark.parametrize("directory", ["assets", "attachments"])
@pytest.mark.parametrize("hashed", [False, "prefix", "suffix"])
def test_page_images_cache_without_losing_security_headers(server, directory, hashed):
    _, root, _ = server
    data = b"\x89PNG\r\n" + b"compressible but never gzip an image" * 300
    digest = hashlib.sha256(data).hexdigest()[:12]
    name = f"{digest}-picture.png" if hashed == "prefix" else f"picture.{digest}.png" if hashed else "picture.png"
    target = root / directory / name
    target.parent.mkdir()
    target.write_bytes(data)
    with connection(server) as conn:
        first, body = request(conn, f"/review/{directory}/{name}", headers={"Accept-Encoding": "gzip"})
        assert body == data and first.getheader("Content-Encoding") is None
        assert first.getheader("Vary") is None
        assert first.getheader("Content-Security-Policy") == "sandbox"
        assert ("immutable" in first.getheader("Cache-Control")) == bool(hashed)
        cached, body = request(conn, f"/review/{directory}/{name}", headers={"If-None-Match": first.getheader("ETag")})
        assert cached.status == 304 and body == b""
        assert cached.getheader("Content-Security-Policy") == "sandbox"
        target.write_bytes(data + b"changed")
        changed, _ = request(conn, f"/review/{directory}/{name}", headers={"If-None-Match": first.getheader("ETag")})
        assert changed.status == 200
        assert changed.getheader("Cache-Control") == "no-cache"


@pytest.mark.parametrize("accept,compressed", [
    (None, False), ("identity", False), ("br", False), ("gzip", True), ("br, gzip;q=0.5", True),
    ("gzip;q=0, *;q=1", False), ("*;q=1", True), ("GZip; q=1", True),
    ("gzip;q=garbage", False), ("gzip;q=0.0", False), ("gzip ; q=1", True),
])
def test_gzip_negotiation_and_representation_etags(server, accept, compressed):
    _, _, web = server
    with connection(server) as conn:
        headers = {"Accept-Encoding": accept} if accept else {}
        response, body = request(conn, "/review/shell.js", headers=headers)
        assert response.getheader("Vary") == "Accept-Encoding"
        assert (response.getheader("Content-Encoding") == "gzip") == compressed
        assert (gzip.decompress(body) if compressed else body) == (web / "shell.js").read_bytes()
        assert response.getheader("ETag") == '"' + hashlib.sha256(body).hexdigest() + '"'
        conditional, empty = request(conn, "/review/shell.js", headers={**headers, "If-None-Match": response.getheader("ETag")})
        assert conditional.status == 304 and empty == b""
        assert conditional.getheader("Vary") == "Accept-Encoding"
        if compressed:
            identity, _ = request(conn, "/review/shell.js", headers={"If-None-Match": response.getheader("ETag")})
            assert identity.status == 200
            assert identity.getheader("ETag") != response.getheader("ETag")


@pytest.mark.parametrize("directory,suffix", [
    (directory, suffix) for directory in ("assets", "attachments")
    for suffix in (".html", ".htm", ".css", ".js", ".json", ".svg")
    if directory == "attachments" or suffix not in (".html", ".htm")
])
def test_text_uploads_compress_and_304_keeps_sandbox_and_download(server, directory, suffix):
    root = server[1]
    (root / directory).mkdir()
    (root / directory / ("text" + suffix)).write_bytes(b"text content " * 300)
    path = f"/review/{directory}/text{suffix}"
    with connection(server) as conn:
        response, body = request(conn, path, headers={"Accept-Encoding": "gzip"})
        assert gzip.decompress(body) == b"text content " * 300
        assert response.getheader("Content-Security-Policy") == "sandbox"
        assert response.getheader("Content-Disposition").startswith("attachment;")
        cached, _ = request(conn, path,
                            headers={"Accept-Encoding": "gzip", "If-None-Match": response.getheader("ETag")})
        assert cached.status == 304
        assert cached.getheader("Content-Disposition") == response.getheader("Content-Disposition")
        assert cached.getheader("Content-Security-Policy") == "sandbox"


@pytest.mark.parametrize("suffix", [".html", ".htm", ".HTML"])
@pytest.mark.parametrize("hashed", [False, True])
def test_page_html_runs_in_opaque_sandbox_and_keeps_cache_headers(server, suffix, hashed):
    root = server[1]
    data = b"<html><body><script>document.title = 'Rendered';</script></body></html>" * 30
    name = (hashlib.sha256(data).hexdigest()[:12] + "-" if hashed else "") + "plan" + suffix
    target = root / "assets/v2" / name
    target.parent.mkdir(parents=True)
    target.write_bytes(data)
    path = f"/review/assets/v2/{name}"
    with connection(server) as conn:
        response, body = request(conn, path, headers={"Accept-Encoding": "gzip"})
        assert response.status == 200 and gzip.decompress(body) == data
        assert response.getheader("Content-Type") == "text/html; charset=utf-8"
        assert response.getheader("Content-Disposition") is None
        assert response.getheader("Content-Security-Policy") == "sandbox allow-scripts"
        assert ("immutable" in response.getheader("Cache-Control")) == hashed
        for method in ("GET", "HEAD"):
            cached, body = request(conn, path, method=method,
                                   headers={"Accept-Encoding": "gzip", "If-None-Match": response.getheader("ETag")})
            assert cached.status == 304 and body == b""
            for header in ("Content-Security-Policy", "Content-Disposition", "ETag", "Cache-Control"):
                assert cached.getheader(header) == response.getheader(header)
        target.write_bytes(data + b"changed")
        changed, _ = request(conn, path, headers={"If-None-Match": response.getheader("ETag")})
        assert changed.status == 200 and changed.getheader("Cache-Control") == "no-cache"


@pytest.mark.parametrize("source,destination", [("assets", "attachments"), ("attachments", "assets")])
def test_html_aliases_across_upload_boundaries_still_download(server, source, destination):
    root = server[1]
    (root / source).mkdir()
    (root / destination).mkdir()
    (root / destination / "plan.html").write_text("<script>document.title = 'Upload';</script>")
    (root / source / "alias.html").symlink_to(root / destination / "plan.html")
    with connection(server) as conn:
        response, _ = request(conn, f"/review/{source}/alias.html")
        assert response.status == 200
        assert response.getheader("Content-Disposition").startswith("attachment;")
        assert response.getheader("Content-Security-Policy") == "sandbox"


def test_http11_framing_redirect_head_errors_and_polling(server):
    with connection(server) as conn:
        assert request(conn, "/review")[0].status == 308
        sock = conn.sock
        for path in ("/review/shell.js", "/review/comments.json", "/review/current.meta.json",
                     "/review/api/comments", "/review/api/seen", "/review/api/session-monitor", "/review/missing"):
            response, _ = request(conn, path)
            assert response.status in (200, 404)
            assert conn.sock is sock
        head, body = request(conn, "/review/shell.js", method="HEAD", headers={"Accept-Encoding": "gzip"})
        assert body == b"" and int(head.getheader("Content-Length")) > 0
        assert conn.sock is sock
        assert request(conn, "/review/shell.js")[0].status == 200
        options, body = request(conn, "/review/", method="OPTIONS")
        assert options.status == 204 and body == b"" and options.getheader("Content-Length") == "0"
    with connection(server) as conn:
        error, _ = request(conn, "/review/", method="DELETE")
        assert error.status == 501


def test_rejected_mutation_closes_unread_body_and_idle_connections_expire(server):
    with connection(server) as conn:
        response, _ = request(conn, "/review/unknown", method="POST", body=b"{}")
        assert response.status == 404 and response.getheader("Connection") == "close"
        assert conn.sock is None
    server[0].RequestHandlerClass.timeout = 0.15
    with connection(server) as conn:
        request(conn, "/review/shell.js")
        assert conn.sock.recv(1) == b""
