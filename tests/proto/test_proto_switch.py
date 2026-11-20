"""Only a page whose meta asks for "ui": "proto" gets the prototype shell; every other page is untouched."""

import http.client
import json
import shutil
import threading
from pathlib import Path

import pytest

from agent_annotate.paths import WEB_DIR
from agent_annotate.sync_server import ReviewHTTPServer, make_handler


def _page(tmp_path, meta):
    page = tmp_path / "page"
    page.mkdir()
    (page / "comments.json").write_text('{"schema_version":2,"anchors":{},"archived":{}}')
    (page / "current.meta.json").write_text(json.dumps(meta))
    (page / "current.html").write_text("<html><body>Review</body></html>")
    (page / "proto").mkdir()
    (page / "proto" / "frame.js").write_text("page file")  # a page-owned file at the same path
    return page


@pytest.fixture
def serve(tmp_path):
    servers = []

    def start(meta):
        web = tmp_path / "web"
        if not web.exists():
            shutil.copytree(WEB_DIR, web)
        handler = make_handler(_page(tmp_path / str(len(servers)), meta), skill_dir=web,
                               public_base_path="/p", slug="page")
        httpd = ReviewHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        servers.append(httpd)

        def get(path):
            conn = http.client.HTTPConnection(*httpd.server_address, timeout=3)
            conn.request("GET", path)
            response = conn.getresponse()
            body = response.read()
            conn.close()
            return response.status, body
        return get, web

    (tmp_path / "0").mkdir()
    (tmp_path / "1").mkdir()
    yield start
    for httpd in servers:
        httpd.shutdown()
        httpd.server_close()


def test_proto_page_gets_the_prototype(serve):
    get, web = serve({"current": "v1", "history": [], "ui": "proto"})
    status, body = get("/p/")
    assert status == 200 and body == (web / "proto" / "shell.html").read_bytes()
    assert get("/p/proto/frame.js") == (200, (web / "proto" / "frame.js").read_bytes())
    assert get("/p/proto/data/nothing_yet.json") == (200, b"{}")
    assert get("/p/proto/missing.js")[0] == 404
    assert get("/p/proto/..%2Fshell.html")[0] == 404


def test_area_module_is_dispatched(serve, monkeypatch):
    import sys
    import types
    module = types.ModuleType("agent_annotate.proto_data.fakearea")
    module.build = lambda page_dir: {"page": Path(page_dir).name}
    monkeypatch.setitem(sys.modules, "agent_annotate.proto_data.fakearea", module)
    get, _ = serve({"current": "v1", "history": [], "ui": "proto"})
    assert get("/p/proto/data/fakearea.json") == (200, b'{"page": "page"}')


def test_other_pages_render_as_today(serve):
    get, web = serve({"current": "v1", "history": []})
    status, body = get("/p/")
    assert status == 200 and b"proto/frame.js" not in body
    assert body.startswith(b"<html><body>Review") or b'id="aa-tabs"' in body
    # /proto/ paths fall through to the page's own static files, exactly as before
    assert get("/p/proto/data/questions.json")[0] == 404
    assert get("/p/proto/frame.js")[0] == 404
