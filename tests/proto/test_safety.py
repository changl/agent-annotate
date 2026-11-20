"""The prototype page returns no real address and no review key; an ordinary page is unchanged."""

import gzip
import http.client
import json
import shutil
import threading

import pytest

from agent_annotate.paths import WEB_DIR
from agent_annotate.proto_data import questions, scrub
from agent_annotate.sync_server import ReviewHTTPServer, make_handler

REAL = "pat.doe@realmail.test"
COMPANY = "support@fastlanedrive.com"
KEY = "FAKEreviewKEY0123456789abcdef"
TEXT = f"Ask {COMPANY} or {REAL}; see https://h.ts.net/annotate/reviews/x/#review={KEY} and icon@2x.png"


def test_scrub_masks_every_address_and_key():
    out = scrub(TEXT)
    assert REAL not in out and COMPANY not in out and KEY not in out
    assert out.count("member@example.com") == 2 and "#review=redacted" in out and "icon@2x.png" in out
    assert scrub("member@example.com") == "member@example.com"
    assert questions._mask(COMPANY) == "member@example.com"  # no company exemption


@pytest.fixture
def serve(tmp_path):
    servers = []

    def start(meta):
        web = tmp_path / "web"
        if not web.exists():
            shutil.copytree(WEB_DIR, web)
        page = tmp_path / str(len(servers)) / "page"
        page.mkdir(parents=True)
        card = {"id": "c1", "anchor_id": "a1", "author": REAL, "author_email": REAL, "text": TEXT, "version": "v1"}
        (page / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {"a1": [card]}, "archived": {}}))
        (page / "current.meta.json").write_text(json.dumps(meta))
        (page / "current.html").write_text("<html><body>Review</body></html>")
        handler = make_handler(page, skill_dir=web, public_base_path="/p", slug="page", local_author=REAL)
        httpd = ReviewHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        servers.append(httpd)

        def get(path, gz=False):
            conn = http.client.HTTPConnection(*httpd.server_address, timeout=5)
            conn.request("GET", path, headers={"Accept-Encoding": "gzip"} if gz else {})
            r = conn.getresponse()
            body = r.read()
            if r.getheader("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            conn.close()
            return r.status, body.decode()
        return get

    yield start
    for httpd in servers:
        httpd.shutdown()
        httpd.server_close()


@pytest.mark.parametrize("path", ["/p/comments.json", "/p/api/comments", "/p/api/identity", "/p/api/history"])
@pytest.mark.parametrize("gz", [False, True])
def test_proto_replies_are_masked(serve, path, gz):
    status, body = serve({"current": "v1", "history": [], "ui": "proto"})(path, gz)
    assert status == 200
    assert REAL not in body and COMPANY not in body and KEY not in body


def test_ordinary_page_is_unchanged(serve):
    get = serve({"current": "v1", "history": []})
    assert REAL in get("/p/comments.json")[1]
    assert REAL in get("/p/api/identity")[1]
