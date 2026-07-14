import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _request(url, method="GET", body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        method=method,
        data=data,
        headers={"Content-Type": "application/json", "Cf-Access-Authenticated-User-Email": "test@example.com"},
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        return response.status, response.read().decode("utf-8")


def test_server_serves_shell_content_and_comment_lifecycle(tmp_path):
    slug_dir = tmp_path / "review"
    versions = slug_dir / "versions"
    content_dir = slug_dir / "content"
    versions.mkdir(parents=True)
    content_dir.mkdir(parents=True)
    html = "<!doctype html><body><section data-anchor-id='s:test'>Test</section></body>"
    (versions / "v1.html").write_text(html, encoding="utf-8")
    (content_dir / "v1.html").write_text(html, encoding="utf-8")
    (slug_dir / "current.html").symlink_to(Path("versions") / "v1.html")
    (slug_dir / "current.meta.json").write_text(
        json.dumps({"current": "v1", "history": [{"version": "v1", "label": "test"}]}),
        encoding="utf-8",
    )
    (slug_dir / "comments.json").write_text(
        json.dumps({"schema_version": 2, "anchors": {}, "archived": {}}), encoding="utf-8"
    )
    bus_dir = tmp_path / "bus"
    port = _free_port()
    env = os.environ.copy()
    env["ANNOTATE_STATE_DIR"] = str(tmp_path / "state")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "agent_annotate.sync_server",
            "--slug-dir",
            str(slug_dir),
            "--slug",
            "review",
            "--bus-dir",
            str(bus_dir),
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.time() + 5
        while True:
            try:
                status, shell = _request(base + "/")
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.05)
        assert status == 200
        assert 'id="drawer"' in shell

        status, content = _request(base + "/content?v=v1")
        assert status == 200
        assert "adapter.js" in content

        status, created = _request(
            base + "/api/comments",
            method="POST",
            body={"anchor_id": "s:test", "text": "Precise feedback", "version": "v1"},
        )
        assert status == 201
        comment = json.loads(created)
        assert comment["text"] == "Precise feedback"
        assert (bus_dir / "review.ndjson").read_text(encoding="utf-8").count("comment_created") == 1
    finally:
        process.terminate()
        process.wait(timeout=5)
