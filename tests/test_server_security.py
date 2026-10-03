import http.client
import http.server
import io
import json
import stat
import threading
import urllib.parse

import pytest

from agent_annotate import cli
from agent_annotate.sync_server import AnnotateHandler, _atomic_write_json, _version_file, make_handler


def _handler(directory, *, v2=True):
    handler = AnnotateHandler.__new__(AnnotateHandler)
    handler.artifact_dir = directory
    handler.artifact_file = "current.html" if v2 else "review.html"
    handler.v2_mode = v2
    handler.skill_dir = None
    handler.public_base_path = ""
    handler.slug = "review"
    handler.responses = []
    handler._respond = lambda code, body, *args, **kwargs: handler.responses.append((code, body))
    handler._ensure_content_stamp = lambda *args: None
    handler.headers = {}
    return handler


@pytest.mark.parametrize("version", ["../../outside", "/outside", "v1/../v2", "v1.html", "v1%2f..", "v1</script>"])
def test_version_input_cannot_read_outside_html(tmp_path, version):
    artifact = tmp_path / "review"
    (artifact / "content").mkdir(parents=True)
    outside = tmp_path / "outside.html"
    outside.write_text("PRIVATE_INERT_MARKER")
    handler = _handler(artifact)
    handler._v2_serve_content(urllib.parse.urlparse("/content?" + urllib.parse.urlencode({"v": version})))
    assert handler.responses[-1][0] == 400
    assert b"PRIVATE_INERT_MARKER" not in handler.responses[-1][1]


@pytest.mark.parametrize("subtree", ["content", "versions"])
@pytest.mark.parametrize("directory_link", [False, True])
def test_version_resolution_refuses_symlink_escape(tmp_path, subtree, directory_link):
    artifact = tmp_path / "review"
    artifact.mkdir()
    outside = tmp_path / "private"
    outside.mkdir()
    (outside / "v1.html").write_text("PRIVATE_INERT_MARKER")
    if directory_link:
        (artifact / subtree).symlink_to(outside, target_is_directory=True)
    else:
        (artifact / subtree).mkdir()
        (artifact / subtree / "v1.html").symlink_to(outside / "v1.html")
    with pytest.raises(PermissionError):
        _version_file(artifact, "v1", subtree)


def test_valid_content_and_current_version_symlink_still_work(tmp_path):
    (tmp_path / "content").mkdir()
    (tmp_path / "versions").mkdir()
    (tmp_path / "content/v1.html").write_text("<html><body>PUBLIC_INERT_CONTENT</body></html>")
    (tmp_path / "versions/v1.html").write_text("public legacy version")
    (tmp_path / "current.html").symlink_to("versions/v1.html")
    handler = _handler(tmp_path)
    assert handler._version_path(None) == (tmp_path / "versions/v1.html").resolve()
    handler._v2_serve_content(urllib.parse.urlparse("/content?v=v1"))
    assert handler.responses[-1][0] == 200
    assert b"PUBLIC_INERT_CONTENT" in handler.responses[-1][1]


@pytest.mark.parametrize("doc", ["../outside", "/outside", "..", "review/other"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_legacy_doc_traversal_never_reads_or_writes(tmp_path, doc, method):
    artifact = tmp_path / "review"
    artifact.mkdir()
    outside = tmp_path / "outside.comments.json"
    outside.write_text('{"PRIVATE_INERT_MARKER":[]}')
    handler = _handler(artifact, v2=False)
    handler.headers = {"Content-Length": "2"}
    handler.rfile = io.BytesIO(b"{}")
    getattr(handler, f"_v1_{method}_comments")(urllib.parse.urlparse("/api/comments?" + urllib.parse.urlencode({"doc": doc})))
    assert handler.responses[-1][0] == 400
    assert outside.read_text() == '{"PRIVATE_INERT_MARKER":[]}'
    assert b"PRIVATE_INERT_MARKER" not in handler.responses[-1][1]


def test_legacy_comment_symlink_and_predictable_temp_symlink_are_safe(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("PRIVATE_INERT_MARKER")
    artifact = tmp_path / "review"
    artifact.mkdir()
    comments = artifact / "review.comments.json"
    comments.symlink_to(outside)
    handler = _handler(artifact, v2=False)
    handler.headers = {"Content-Length": "2"}
    handler.rfile = io.BytesIO(b"{}")
    handler._v1_post_comments(urllib.parse.urlparse("/api/comments?doc=review"))
    assert handler.responses[-1][0] == 403
    comments.unlink()
    (artifact / "review.comments.json.tmp").symlink_to(outside)
    handler.rfile = io.BytesIO(b"{}")
    handler._v1_post_comments(urllib.parse.urlparse("/api/comments?doc=review"))
    assert handler.responses[-1][0] == 200
    assert json.loads(comments.read_text()) == {}
    assert outside.read_text() == "PRIVATE_INERT_MARKER"


@pytest.mark.parametrize("doc", ["review draft", "审阅计划", "a" * 129])
def test_legacy_valid_basenames_keep_read_write_support(tmp_path, doc):
    handler = _handler(tmp_path, v2=False)
    payload = {"anchor": [{"text": "inert feedback"}]}
    body = json.dumps(payload).encode()
    handler.headers = {"Content-Length": str(len(body))}
    handler.rfile = io.BytesIO(body)
    parsed = urllib.parse.urlparse("/api/comments?" + urllib.parse.urlencode({"doc": doc}))
    handler._v1_post_comments(parsed)
    assert handler.responses[-1][0] == 200
    assert json.loads((tmp_path / (doc + ".comments.json")).read_text()) == payload
    handler._v1_get_comments(parsed)
    assert handler.responses[-1][0] == 200
    assert json.loads(handler.responses[-1][1]) == payload


def test_mounted_root_redirect_preserves_query_and_keeps_mount_boundary(tmp_path):
    handler = make_handler(artifact_dir=tmp_path, public_base_path="/review", slug="review", v2_mode=True)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        conn = http.client.HTTPConnection(*server.server_address, timeout=2)
        conn.request("GET", "/review?v=v3&label=a%20b")
        response = conn.getresponse()
        assert response.status == 308
        assert response.getheader("Location") == "/review/?v=v3&label=a%20b"
        assert response.read() == b""
        conn.request("GET", "/api/identity")
        response = conn.getresponse()
        assert response.status == 404
        response.read()
        conn.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("relative", [".env", ".git/config", "current.meta.json.tmp", "comments.json.bak", "project.json",
    "cards.json", "metrics.json", "seen.json", "read-state.json", "private/data.json", "attachments/.env", "assets/project.json"])
def test_static_internal_files_are_not_public(tmp_path, relative):
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("PRIVATE_INERT_MARKER")
    handler = _handler(tmp_path)
    handler._serve_static("/" + relative)
    assert handler.responses[-1][0] == 404
    assert b"PRIVATE_INERT_MARKER" not in handler.responses[-1][1]


@pytest.mark.parametrize("relative", ["diagram-plot.js", "style.css", "image.png", "assets/chart.json", "attachments/report.pdf"])
def test_public_assets_and_attachments_remain_available(tmp_path, relative):
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"PUBLIC_INERT_MARKER")
    handler = _handler(tmp_path)
    handler._serve_static("/" + relative)
    assert handler.responses[-1] == (200, b"PUBLIC_INERT_MARKER")


def test_static_alias_cannot_expose_private_or_outside_files(tmp_path):
    (tmp_path / "project.json").write_text("PRIVATE_INERT_MARKER")
    (tmp_path / "public.js").symlink_to("project.json")
    handler = _handler(tmp_path)
    handler._serve_static("/public.js")
    assert handler.responses[-1][0] == 404
    outside = tmp_path.parent / "outside.js"
    outside.write_text("PRIVATE_INERT_MARKER")
    (tmp_path / "public.js").unlink()
    (tmp_path / "public.js").symlink_to(outside)
    handler._serve_static("/public.js")
    assert handler.responses[-1][0] == 403


def test_json_atomic_write_preserves_private_mode(tmp_path):
    path = tmp_path / "comments.json"
    path.write_text("{}")
    path.chmod(0o600)
    _atomic_write_json(path, {"anchors": {}})
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_hook_registration_preserves_settings_mode_and_does_not_follow_temp_link(tmp_path, monkeypatch):
    settings = tmp_path / "settings.json"
    settings.write_text("{}")
    settings.chmod(0o600)
    outside = tmp_path / "private.txt"
    outside.write_text("PRIVATE_INERT_MARKER")
    (tmp_path / "settings.json.tmp").symlink_to(outside)
    hook = tmp_path / "check-comment-bus.sh"
    hook.write_text("#!/bin/sh\nexit 0\n")
    hook.chmod(0o755)
    monkeypatch.setattr(cli, "SETTINGS_JSON", settings)
    monkeypatch.setattr(cli, "HOOK_SCRIPT", hook)
    monkeypatch.setattr(cli, "HOOK_COMMAND", str(hook))
    assert cli._ensure_hook_installed()[0] is True
    assert stat.S_IMODE(settings.stat().st_mode) == 0o600
    assert outside.read_text() == "PRIVATE_INERT_MARKER"
