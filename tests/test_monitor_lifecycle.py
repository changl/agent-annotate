"""`annotate monitor`: a lease that is released on SIGTERM, no heartbeat by
default, and only rounds and pushes on stdout.

Every lease found on the live machine had been left behind by a SIGTERM from
Claude Code's Monitor tool, and each one made the page report a listener that
was not there.
"""

import json
import os
import signal
import subprocess
import sys
import time


def _estate(tmp_path):
    state = tmp_path / "state"
    bus_root = tmp_path / "bus"
    (bus_root / "proj").mkdir(parents=True)
    state.mkdir()
    bus = bus_root / "proj" / "demo.ndjson"
    bus.write_text("")
    (state / "proj.json").write_text(json.dumps({"project": "proj", "slugs": {"demo": {
        "slug": "demo", "slug_dir": str(tmp_path / "pages" / "demo"), "project": "proj",
        "pid": 0, "port": 8899, "local_url": "http://localhost:8899/", "bus_file": str(bus)}}}))
    return state, bus_root, bus


def _start(state, bus_root, extra_env=None):
    env = os.environ.copy()
    env["ANNOTATE_STATE_DIR"] = str(state)
    env["ANNOTATE_BUS_ROOT"] = str(bus_root)
    env["CLAUDE_CODE_SESSION_ID"] = "sess-mon"
    env.update(extra_env or {})
    return subprocess.Popen([sys.executable, "-m", "agent_annotate.cli", "monitor", "demo"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)


def _wait_for(path, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return True
        time.sleep(0.05)
    return False


def test_sigterm_releases_the_lease_and_records_the_exit(tmp_path):
    state, bus_root, bus = _estate(tmp_path)
    lease = state / "monitors" / "proj" / "demo" / "owner.json"
    proc = _start(state, bus_root)
    try:
        assert _wait_for(lease), proc.stderr.read()
        recorded = json.loads(lease.read_text())
        assert recorded["owner_session"] == "sess-mon"
        assert recorded["pid"] == proc.pid
        assert "round_submitted" in recorded["events"]

        # A verdict inside a round is not printed; the round submit is.
        with bus.open("a") as fh:
            fh.write(json.dumps({"ts": "2026-09-17T10:00:00Z", "event": "comment_updated", "slug": "demo",
                                 "comment_id": "aaaaaaaaaaaa", "author": "r@x", "decision": "accept",
                                 "deferred": True}) + "\n")
            fh.write(json.dumps({"ts": "2026-09-17T10:01:00Z", "event": "round_submitted", "slug": "demo",
                                 "comment_ids": ["aaaaaaaaaaaa"], "by": "r@x", "note": "ok",
                                 "verdict_counts": {"accept": 1, "reject": 0, "comment": 0},
                                 "undecided_ids": []}) + "\n")
        time.sleep(1.0)
        proc.send_signal(signal.SIGTERM)
        out, err = proc.communicate(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()

    assert proc.returncode == 0, err
    assert not lease.exists()
    lines = [line for line in out.splitlines() if line.strip()]
    assert lines[0].startswith("ANNOTATE_MONITOR_ARMED ")
    assert len(lines) == 2, lines
    assert lines[1].startswith("ANNOTATE_EVENT ") and "round_submitted" in lines[1]
    assert "accept=1" in lines[1] and 'note="ok"' in lines[1]
    assert "ANNOTATE_MONITOR_HEARTBEAT" not in out

    events = [json.loads(line)["event"] for line in bus.read_text().splitlines() if line.strip()]
    assert events[0] == "monitor_armed"
    assert events[-1] == "monitor_exited"
    exited = json.loads(bus.read_text().splitlines()[-1])
    assert exited["lease_released"] is True and exited["owner_session"] == "sess-mon"


def test_a_second_monitor_refuses_without_takeover(tmp_path):
    state, bus_root, _ = _estate(tmp_path)
    lease = state / "monitors" / "proj" / "demo" / "owner.json"
    first = _start(state, bus_root)
    try:
        assert _wait_for(lease)
        second = _start(state, bus_root, {"CLAUDE_CODE_SESSION_ID": "sess-two"})
        _, err = second.communicate(timeout=10)
        assert second.returncode == 3
        assert "already owned by sess-mon" in err
        assert json.loads(lease.read_text())["owner_session"] == "sess-mon"
    finally:
        first.send_signal(signal.SIGTERM)
        first.communicate(timeout=10)


def test_heartbeat_is_opt_in(tmp_path):
    state, bus_root, _ = _estate(tmp_path)
    lease = state / "monitors" / "proj" / "demo" / "owner.json"
    proc = _start(state, bus_root, {"ANNOTATE_MONITOR_HEARTBEAT_INTERVAL": "0.2"})
    try:
        assert _wait_for(lease)
        time.sleep(0.8)
        proc.send_signal(signal.SIGTERM)
        out, _ = proc.communicate(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert out.count("ANNOTATE_MONITOR_HEARTBEAT") >= 2
