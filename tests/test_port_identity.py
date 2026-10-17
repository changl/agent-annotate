"""Local identity and real page operations never depend on lsof or mounts."""

import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from agent_annotate import cli, deployment, pagegen, sync_server


@contextmanager
def listener(handler):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_foreign_http_listener_is_unknown_and_not_free():
    with listener(http.server.SimpleHTTPRequestHandler) as port:
        assert not cli._port_is_free(port)
        with pytest.raises(RuntimeError, match=f"unknown occupant on port {port}"):
            cli._server_capabilities(port)
        assert cli._find_free_port_after(port, registered_pid=999999) > port


def test_bound_port_without_http_is_unknown():
    with socket.socket() as sock:
        sock.bind(("localhost", 0))
        sock.listen()
        port = sock.getsockname()[1]
        start = time.monotonic()
        with pytest.raises(RuntimeError, match="unknown occupant"):
            cli._server_capabilities(port, timeout=0.1)
        assert time.monotonic() - start < 1
        assert not cli._wait_listening(port, os.getpid(), seconds=0.1)


def test_refused_connection_with_bound_nonlistener_is_unknown():
    with socket.socket() as sock:
        sock.bind(("localhost", 0))
        with pytest.raises(RuntimeError, match="unknown occupant"):
            cli._server_capabilities(sock.getsockname()[1])


def test_capabilities_are_fast_without_registry_or_version_checks(tmp_path, monkeypatch):
    handler = sync_server.make_handler(tmp_path, v2_mode=True, public_base_path="/review")
    monkeypatch.setattr(handler, "_published_proxy_origins", lambda self: pytest.fail("local health read registry"))
    monkeypatch.setattr(handler, "_version_guard", lambda self: pytest.fail("local health checked versions"))
    monkeypatch.setattr(handler, "_moved", lambda self: pytest.fail("local health read page store"))
    with listener(handler) as port:
        start = time.monotonic()
        result = cli._server_capabilities(port, "/review")
        assert time.monotonic() - start < 1
        assert result["pid"] == os.getpid()
        assert result["slug_dir"] == str(tmp_path.resolve())
        assert result["port"] == port and result["public_base_path"] == "/review"


def test_forged_http_pid_is_refused_by_process_command(tmp_path, monkeypatch):
    page = tmp_path / "page"
    page.mkdir()
    (page / "current.html").write_text("review")
    class Fake(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"pid": os.getpid(), "slug_dir": str(page.resolve()),
                               "port": self.server.server_port, "public_base_path": ""}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    with listener(Fake) as port:
        # Even a candidate from the process scan must pass the fresh, real ps -p read.
        monkeypatch.setattr(cli, "_running_servers", lambda **kw: {
            str(page.resolve()): [{"pid": os.getpid(), "port": port}]})
        with pytest.raises(deployment.DeploymentError, match="command identity"):
            deployment._identity({"slug_dir": str(page), "port": port, "project": "fake"})


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    """Run worktree source, including isolated deployment subprocesses, only."""
    source = Path(cli.__file__).resolve().parents[1]
    monkeypatch.setenv("PYTHONPATH", str(source))
    python = tmp_path / "python"
    python.write_text(f"#!{sys.executable}\nimport os, sys\nos.environ['PYTHONPATH'] = {str(source)!r}\n"
                      f"os.execvpe({sys.executable!r}, [{sys.executable!r}, "
                      "*[a for a in sys.argv[1:] if a != '-I']], os.environ)\n")
    python.chmod(0o755)
    for name, value in {"STATE_DIR": tmp_path / "state", "LOCK_DIR": tmp_path / "locks",
                        "LOG_DIR": tmp_path / "logs", "BUS_ROOT": tmp_path / "bus"}.items():
        monkeypatch.setattr(cli, name, value)
    monkeypatch.setattr(cli, "_ensure_hook_installed", lambda: (False, "sandbox"))
    monkeypatch.setattr(cli, "_ensure_shim_installed", lambda: (False, "sandbox"))
    # Reap our child servers as a normal process supervisor would, avoiding zombie liveness.
    children = []
    original_spawn, original_alive = subprocess.Popen, cli._is_process_alive
    def spawn(*args, **kwargs):
        child = original_spawn(*args, **kwargs)
        children.append(child)
        return child
    def alive(pid):
        child = next((p for p in children if p.pid == pid), None)
        return child.poll() is None if child else original_alive(pid)
    monkeypatch.setattr(subprocess, "Popen", spawn)
    monkeypatch.setattr(cli, "_is_process_alive", alive)
    yield python
    for child in children:
        if child.poll() is None:
            child.terminate()
            child.wait(timeout=5)


@pytest.mark.parametrize("lsof_mode", ["missing", "sleeps-60s"])
def test_real_page_lifecycle_finishes_in_seconds_without_lsof(runtime, tmp_path, monkeypatch, lsof_mode):
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in ("ps", "git", "node"):
        executable = shutil.which(name)
        if executable:
            (tools / name).symlink_to(executable)
    marker = tmp_path / "lsof-called"
    if lsof_mode == "sleeps-60s":
        stub = tools / "lsof"
        stub.write_text(f"#!{sys.executable}\nimport time\nfrom pathlib import Path\n"
                        f"Path({str(marker)!r}).touch()\ntime.sleep(60)\n")
        stub.chmod(0o755)
    monkeypatch.setenv("PATH", str(tools))
    assert bool(shutil.which("lsof")) == (lsof_mode == "sleeps-60s")
    markdown = tmp_path / "page.md"
    markdown.write_text("---\ntitle: Sandbox\n---\n\n## Scope\n\nRestart only this sandbox.\n")
    page = tmp_path / "pages" / "sandbox"
    pagegen.generate(markdown, page, version="v1")
    with socket.socket() as sock:
        sock.bind(("localhost", 0))
        port = sock.getsockname()[1]
    parser = cli.build_parser()
    def command(arguments):
        args = parser.parse_args(arguments)
        start = time.monotonic()
        assert cli.run_command(args) == 0
        assert time.monotonic() - start < 6

    start = time.monotonic()
    assert cli._find_free_port_after(port) == port
    assert time.monotonic() - start < 1
    command(["publish", str(page), "--project", "sandbox", "--port", str(port), "--transport", "local",
             "--skip-js-lint", "--no-verify"])
    state = cli._load_state_for_project("sandbox")
    old_pid = state["slugs"]["sandbox"]["pid"]
    # A recycled registry PID must not stop the unrelated test process.
    state["slugs"]["sandbox"]["pid"] = os.getpid()
    cli._save_state_for_project("sandbox", state)
    start = time.monotonic()
    result = deployment.restart_record("sandbox", "sandbox", runtime)
    assert time.monotonic() - start < 6
    assert result["ok"] and result["pid"] != old_pid
    assert not cli._is_process_alive(old_pid)
    command(["archive", "sandbox/sandbox", "--why", "Sandbox test"])
    command(["unarchive", "sandbox/sandbox"])
    command(["unpublish", "sandbox/sandbox"])
    assert not cli._load_state_for_project("sandbox")["slugs"]
    assert not marker.exists()
