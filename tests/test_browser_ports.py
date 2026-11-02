"""Browser free-port probes retain cross-process leases until test teardown."""

import importlib.util
import io
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("browser_ports", Path(__file__).parent / "browser/conftest.py")
ports = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ports)


def test_free_port_probe_stays_reserved_across_processes(monkeypatch):
    fixture = ports.sandbox_ports.__wrapped__(monkeypatch)
    next(fixture)
    try:
        with socket.socket() as first:
            first.bind(("127.0.0.1", 0))
            port = first.getsockname()[1]
        with socket.socket() as second:
            second.bind(("127.0.0.1", 0))
            assert 18700 <= second.getsockname()[1] < 18800
            assert second.getsockname()[1] != port
        probe = "import fcntl,sys; f=open(sys.argv[1],'a'); fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)"
        lease = Path("/tmp") / f"annotate-browser-ports-{ports.os.getuid()}" / str(port)
        assert subprocess.run([sys.executable, "-c", probe, str(lease)], capture_output=True).returncode != 0
        with socket.socket() as explicit:
            explicit.bind(("127.0.0.1", port))
            assert explicit.getsockname()[1] == port
        with socket.socket() as forbidden, pytest.raises(OSError, match="outside sandbox"):
            forbidden.bind(("127.0.0.1", 8800))
    finally:
        with pytest.raises(StopIteration):
            next(fixture)
    assert subprocess.run([sys.executable, "-c", probe, str(lease)], capture_output=True).returncode == 0


@pytest.mark.parametrize("matching", [False, True])
def test_server_start_requires_its_own_pid_and_directory(monkeypatch, tmp_path, matching):
    class Process:
        pid = 987654
        polls = 0
        stopped = False
        def poll(self):
            self.polls += 1
            return None if self.polls < 4 else 1
        def terminate(self):
            self.stopped = True
        def wait(self, timeout):
            return 0
    process = Process()
    monkeypatch.setattr(ports.subprocess, "Popen", lambda *a, **kw: process)
    monkeypatch.setattr(ports.time, "sleep", lambda delay: None)
    identity = {"pid": process.pid if matching else 123, "slug_dir": str(tmp_path)}
    monkeypatch.setattr(ports.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(json.dumps(identity).encode()))
    fixture = ports.sandbox_ports.__wrapped__(monkeypatch)
    next(fixture)
    try:
        command = [sys.executable, "-m", "agent_annotate.sync_server", "--slug-dir", str(tmp_path), "--port", "18766"]
        if matching:
            assert ports.subprocess.Popen(command) is process
        else:
            with pytest.raises(AssertionError, match="test server identity failed"):
                ports.subprocess.Popen(command)
    finally:
        with pytest.raises(StopIteration):
            next(fixture)
    assert process.stopped == matching


def test_session_cleanup_stops_only_its_unique_temporary_estate(request, tmp_path, monkeypatch):
    from types import SimpleNamespace

    from agent_annotate import cli

    module = request.config.pluginmanager.getplugin(str(Path(__file__).parent / "conftest.py"))
    stopped = []
    monkeypatch.setattr(cli, "_running_servers", lambda **kwargs: {
        str(tmp_path / "owned"): [{"pid": 1}],
        str(module._SANDBOX / "owned"): [{"pid": 2}],
        str(tmp_path.parent / "another-suite"): [{"pid": 3}],
    })
    monkeypatch.setattr(cli, "_stop_server", stopped.append)
    cleanup = module._stop_test_servers.__wrapped__(SimpleNamespace(getbasetemp=lambda: tmp_path))
    next(cleanup)
    with pytest.raises(StopIteration):
        next(cleanup)
    assert stopped == [1, 2]


@pytest.mark.parametrize("port", [8800, 8899])
def test_root_guard_refuses_a_live_range_server_before_spawning(tmp_path, port):
    with pytest.raises(AssertionError, match="live range"):
        subprocess.Popen([sys.executable, "-m", "agent_annotate.sync_server", "--slug-dir", str(tmp_path), "--port", str(port)])
