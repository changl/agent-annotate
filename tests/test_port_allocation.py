"""Port allocation must answer the same question the server will ask.

Two ways to get this wrong, both found the hard way on 2026-07-31:

1. Binding ("", p) with no options. A loopback socket in TIME_WAIT refuses a
   0.0.0.0 bind, so a slug re-published moments after serving traffic silently
   moved to the next port — and a moving local port makes a `tailscale serve`
   mapping leak a fresh entry on every publish.
2. "Fixing" that by adding SO_REUSEADDR while still binding ("", p). On
   BSD/macOS that lets a wildcard bind sit on top of a different local address,
   so 0.0.0.0:<p> binds cleanly while a server is LISTENing on 127.0.0.1:<p>.
   Allocation then hands out a port already in use and two servers fight over
   one slug. This is strictly worse than the bug it replaced.

The probe binds ("localhost", p) with SO_REUSEADDR — exactly what
http.server.HTTPServer does — so it reuses TIME_WAIT and is still refused by a
live listener.
"""

import json
import socket
import subprocess
import sys
import threading

from agent_annotate import cli, sync_server


def test_automatic_pickers_skip_registered_ports(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("p", "live", {"port": 18730, "slug_dir": str(tmp_path)})])
    assert sync_server.find_free_port(18730) != 18730
    assert cli._find_free_port_after(18730) != 18730
    assert sync_server.find_free_port(18730, tmp_path) == 18730
    assert cli._find_free_port_after(18730, slug_dir=tmp_path) == 18730


def test_server_refuses_another_pages_registered_port(tmp_path):
    import os
    state = tmp_path / "state"
    state.mkdir()
    page = tmp_path / "sandbox"
    page.mkdir()
    (state / "p.json").write_text(json.dumps({"project": "p", "slugs": {
        "live": {"port": 18731, "slug_dir": str(tmp_path / "live")}}}))
    result = subprocess.Popen([sys.executable, "-m", "agent_annotate.sync_server", "--slug-dir", str(page),
                               "--port", "18731", "--strict-port"],
                              env={**os.environ, "ANNOTATE_STATE_DIR": str(state)},
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        try:
            _, err = result.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            result.terminate()
            result.communicate(timeout=3)
            raise AssertionError("sandbox server accepted another page's registered port") from None
        assert result.returncode != 0
        assert "registered" in err and str(tmp_path / "live") in err
    finally:
        if result.poll() is None:
            result.terminate()
            result.wait(timeout=3)


def _listener(port_hint: int = 0):
    """A real LISTENing socket bound the way sync_server binds."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("localhost", port_hint))
    s.listen(5)
    return s, s.getsockname()[1]


def test_a_live_listener_is_never_allocated():
    """The regression that matters: handing out an in-use port would put two
    sync servers on one slug."""
    sock, port = _listener()
    try:
        assert cli._find_free_port_after(port) != port
    finally:
        sock.close()


def test_allocation_walks_past_a_live_listener_to_the_next_free_port():
    sock, port = _listener()
    try:
        assert cli._find_free_port_after(port) > port
    finally:
        sock.close()


def test_a_free_port_is_returned_unchanged():
    sock, port = _listener()
    sock.close()  # nothing ever connected, so no TIME_WAIT
    assert cli._find_free_port_after(port) == port


def test_a_port_left_in_time_wait_is_still_offered():
    """The original defect. The server can bind it (allow_reuse_address), so a
    probe that refuses it makes the slug's port drift on every re-publish."""
    srv, port = _listener()
    accepted = []

    def _connect():
        c = socket.create_connection(("127.0.0.1", port))
        c.sendall(b"x")
        accepted.append(c)

    t = threading.Thread(target=_connect)
    t.start()
    conn, _ = srv.accept()
    conn.recv(16)
    conn.close()  # server-side close leaves 127.0.0.1:<port> in TIME_WAIT
    t.join()
    for c in accepted:
        c.close()
    srv.close()

    assert cli._find_free_port_after(port) == port
