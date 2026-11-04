"""Lease loopback test ports across parallel suites, including server subprocesses."""

import fcntl
import json
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def sandbox_ports(monkeypatch):
    # Keep the lease after a free-port probe closes, until its test's servers stop.
    leases = {}
    directory = Path("/tmp") / f"annotate-browser-ports-{os.getuid()}"
    directory.mkdir(exist_ok=True, mode=0o700)
    original_bind = socket.socket.bind
    original_popen = subprocess.Popen
    children = []

    def bind(sock, address):
        if not isinstance(address, tuple) or address[0] not in ("127.0.0.1", "localhost"):
            return original_bind(sock, address)
        requested = address[1]
        if requested and not 18700 <= requested < 18800:
            raise OSError(f"browser server port outside sandbox: {requested}")
        if requested in leases:
            return original_bind(sock, address)
        for port in ([requested] if requested else range(18700, 18800)):
            lease = (directory / str(port)).open("a")
            try:
                fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                original_bind(sock, (address[0], port))
            except OSError:
                lease.close()
                continue
            leases[port] = lease
            return None
        raise OSError("no sandbox browser port available in 18700-18799")

    monkeypatch.setattr(socket.socket, "bind", bind)

    def start(command, *args, **kwargs):
        if not isinstance(command, (list, tuple)) or "agent_annotate.sync_server" not in command:
            return original_popen(command, *args, **kwargs)
        port = int(command[command.index("--port") + 1])
        assert 18700 <= port < 18800, f"browser server port outside sandbox: {port}"
        process = original_popen(command, *args, **kwargs)
        children.append(process)
        directory = str(Path(command[command.index("--slug-dir") + 1]).resolve())
        prefix = command[command.index("--public-base-path") + 1] if "--public-base-path" in command else ""
        request = urllib.request.Request(f"http://127.0.0.1:{port}{prefix}/api/capabilities",
                                         headers={"X-Annotate-Identity": "1"})
        observed = None
        deadline = time.monotonic() + 15
        while process.poll() is None and time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(request, timeout=1) as response:
                    observed = json.load(response)
                if observed.get("pid") == process.pid and observed.get("slug_dir") == directory:
                    return process
            except (OSError, ValueError):
                pass
            time.sleep(.05)
        raise AssertionError(f"test server identity failed: pid={process.pid} page={directory} port={port} observed={observed}")

    monkeypatch.setattr(subprocess, "Popen", start)
    yield
    for process in children:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    for lease in leases.values():
        lease.close()
