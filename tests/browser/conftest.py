"""Lease loopback test ports across parallel suites, including server subprocesses."""

import fcntl
import os
import socket
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def sandbox_ports(monkeypatch):
    # Keep the lease after a free-port probe closes, until its test's servers stop.
    leases = {}
    directory = Path("/tmp") / f"annotate-browser-ports-{os.getuid()}"
    directory.mkdir(exist_ok=True, mode=0o700)
    original_bind = socket.socket.bind

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
    yield
    for lease in leases.values():
        lease.close()
