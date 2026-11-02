"""Browser free-port probes retain cross-process leases until test teardown."""

import importlib.util
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
