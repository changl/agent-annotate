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
import urllib.request
import venv
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import platformdirs
import pytest

from agent_annotate import cli, deployment, pagegen, sync_server

# pip/uv's launcher header: the kernel cannot exec a #! interpreter path with a space.
PYTHON_SCRIPT = f"#!/bin/sh\n'''exec' \"{sys.executable}\" \"$0\" \"$@\"\n' '''\n"


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


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("candidate", [False, True])
def test_forged_http_pid_is_refused_by_process_command(tmp_path, monkeypatch, legacy, candidate):
    page = tmp_path / "page"
    page.mkdir()
    (page / "current.html").write_text("review")
    class Fake(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            payload = {"version": "2.26.1", "runtime": {"package_version": "2.26.1"}}
            if not legacy:
                payload.update(pid=os.getpid(), slug_dir=str(page.resolve()),
                               port=self.server.server_port, public_base_path="")
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    with listener(Fake) as port:
        # Even a candidate from the process scan must pass the fresh, real ps -p read.
        monkeypatch.setattr(cli, "_running_servers", lambda **kw: {
            str(page.resolve()): [{"pid": os.getpid(), "port": port}]} if candidate else {})
        with pytest.raises(deployment.DeploymentError, match="command identity" if candidate else "foreign"):
            deployment._identity({"slug_dir": str(page), "port": port, "project": "fake"})


def test_browser_capabilities_do_not_expose_process_identity(tmp_path):
    handler = sync_server.make_handler(tmp_path, v2_mode=True)
    with listener(handler) as port:
        origin = f"http://127.0.0.1:{port}"
        for headers in ({}, {"X-Annotate-Identity": "1", "Origin": origin, "Sec-Fetch-Site": "same-origin"}):
            request = urllib.request.Request(origin + "/api/capabilities", headers=headers)
            with urllib.request.urlopen(request, timeout=1) as response:
                payload = json.load(response)
            assert payload["version"] and payload["runtime"]
            assert not {"pid", "slug_dir", "port", "public_base_path"}.intersection(payload)


def test_process_argv_is_exact_where_ps_text_is_lossy(tmp_path):
    argv = [sys.executable, "-c", "import time; print('ready', flush=True); time.sleep(30)",
            "--slug-dir", str(tmp_path / "a dir" / "page dir"), "--public-base-path", "",
            "--local-author-name", "Ada  Lovelace"]
    child = subprocess.Popen(argv, stdout=subprocess.PIPE, text=True)
    try:
        assert child.stdout.readline() == "ready\n"
        exact = sys.platform == "darwin" or sys.platform.startswith("linux")
        assert cli._process_argv(child.pid) == (argv if exact else None)
    finally:
        child.kill()
        child.wait()
        child.stdout.close()
    assert cli._process_argv(child.pid) is None


def test_process_argv_never_reads_the_environment_as_an_argument():
    # macOS: an empty argv[0] looks like the padding before it, and the environment
    # follows argv. Linux keeps it exact; macOS cannot place it, so it is unread.
    # A new session keeps CPython off posix_spawn, which refuses an empty argv[0].
    child = subprocess.Popen(["", "3"], executable="/bin/sleep", env={"WM_ARGV_SENTINEL": "controlled"},
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        time.sleep(0.2)  # Popen returns at exec; the new image places its argv just after
        argv = cli._process_argv(child.pid)
        assert child.poll() is None
    finally:
        child.kill()
        child.wait()
    assert argv == (["", "3"] if sys.platform.startswith("linux") else None)
    assert not any("WM_ARGV_SENTINEL" in arg for arg in argv or [])


def test_running_servers_never_map_a_spaced_directory_to_its_prefix(tmp_path, monkeypatch):
    prefix, spaced = tmp_path / "legacy", tmp_path / "legacy page"
    prefix.mkdir()
    spaced.mkdir()
    exact = {41: [sys.executable, "-I", "-m", "agent_annotate.sync_server", "--slug-dir", str(spaced),
                  "--slug", spaced.name, "--port", "8802"]}
    # `ps` joins argv with spaces and quotes nothing; 42's argv cannot be read (exited, or another user's).
    table = (f"   41 {' '.join(exact[41])}\n"
             f"   42 {sys.executable} -m agent_annotate.sync_server --slug-dir {prefix} --port 8803\n")
    monkeypatch.setattr(subprocess, "run", lambda command, *args, **kwargs: SimpleNamespace(stdout=table))
    monkeypatch.setattr(cli, "_process_argv", exact.get)
    assert cli._running_servers(strict=True) == {
        str(spaced.resolve()): [{"pid": 41, "port": 8802, "public_base_path": None}]}


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    """Run worktree source, including isolated deployment subprocesses, only."""
    source = Path(cli.__file__).resolve().parents[1]
    monkeypatch.setenv("PYTHONPATH", str(source))
    python = tmp_path / "python"
    python.write_text(f"{PYTHON_SCRIPT}import os, sys\nos.environ['PYTHONPATH'] = {str(source)!r}\n"
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
        stub.write_text(f"{PYTHON_SCRIPT}import time\nfrom pathlib import Path\n"
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


@pytest.mark.parametrize("rollback", [False, True])
def test_legacy_server_restarts_onto_new_identity_and_can_roll_back(runtime, tmp_path, monkeypatch, rollback):
    """An old server ignores the identity header and serves the 2.26.1 payload."""
    package = Path(cli.__file__).parent
    overlay = tmp_path / "legacy-source"
    legacy = overlay / "agent_annotate"
    legacy.mkdir(parents=True)
    (legacy / "__init__.py").write_text(f"__version__ = '2.26.1'\n__path__.append({str(package)!r})\n")
    (legacy / "sync_server.py").write_text(
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('agent_annotate._legacy_server', {str(package / 'sync_server.py')!r})\n"
        "server = importlib.util.module_from_spec(spec)\nsys.modules[spec.name] = server\n"
        "spec.loader.exec_module(server)\n"
        "server.AnnotateHandler._is_identity_probe = lambda self: False\nserver.main()\n")
    # A sandbox interpreter keeps its source path on rollback even when deployment
    # intentionally strips PYTHONPATH. No installed runtime or environment is edited.
    # Spaced on purpose: `ps` cannot quote these paths, and identity must not depend on it.
    spaced = tmp_path / "spaced dir"
    legacy_env = spaced / "legacy env"
    venv.EnvBuilder(with_pip=False, symlinks=True).create(legacy_env)
    site = next((legacy_env / "lib").glob("python*/site-packages"))
    (site / "sandbox-source.pth").write_text(f"{overlay}\n{package.parent}\n{Path(platformdirs.__file__).parents[1]}\n")
    legacy_python = legacy_env / "bin" / "python"
    markdown = tmp_path / "legacy.md"
    markdown.write_text("---\ntitle: Legacy sandbox\n---\n\n## Scope\n\nUpgrade this sandbox.\n")
    page = spaced / "legacy-page"
    pagegen.generate(markdown, page, version="v1")
    with socket.socket() as sock:
        sock.bind(("localhost", 0))
        port = sock.getsockname()[1]
    bus = cli.BUS_ROOT / "legacy"
    bus.mkdir(parents=True)
    record = {"slug_dir": str(page), "project": "legacy", "port": port, "public_base_path": "/legacy",
              "bus_file": str(bus / "legacy-page.ndjson")}
    process = subprocess.Popen(deployment._arguments(record, legacy_python), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    record["pid"] = process.pid
    cli._save_state_for_project("legacy", {"project": "legacy", "slugs": {"legacy-page": record}})
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        payload = cli._server_capabilities(port, "/legacy")
        if payload:
            break
        time.sleep(0.05)
    else:
        pytest.fail("legacy server did not start")
    assert payload["version"] == "2.26.1" and "pid" not in payload
    assert deployment._identity(record)["pid"] == process.pid
    if rollback:
        verify = deployment._verify_server
        def reject_new(record, pid, expected):
            if expected is not None:
                verify(record, pid, expected)
                raise deployment.DeploymentError("reject new runtime")
            return verify(record, pid, expected)
        monkeypatch.setattr(deployment, "_verify_server", reject_new)
        with pytest.raises(deployment.DeploymentError) as error:
            deployment.restart_record("legacy", "legacy-page", runtime)
        assert error.value.result["rolled_back"], str(error.value)
        assert "pid" not in cli._server_capabilities(port, "/legacy")
    else:
        result = deployment.restart_record("legacy", "legacy-page", runtime)
        assert result["ok"] and result["pid"] != process.pid
        assert cli._server_capabilities(port, "/legacy")["pid"] == result["pid"]
    assert not cli._is_process_alive(process.pid)
