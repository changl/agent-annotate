"""Runtime deployment reconciles processes and preserves page ownership."""

import copy
import json
import os
import shlex
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_annotate import cli, deployment

MANIFEST = {"package_version": "2.20.0", "build_id": "new-build", "assets": {"shell.js": "new-sha"}}
REAL_VERIFY = deployment._verify_server
REAL_TARGET = deployment._target_manifest


@pytest.fixture
def estate(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    for name, value in {"STATE_DIR": state_dir, "LOCK_DIR": state_dir / "locks",
                        "LOG_DIR": state_dir / "logs", "BUS_ROOT": tmp_path / "bus",
                        "SHIM_PATH": tmp_path / "bin" / "annotate"}.items():
        monkeypatch.setattr(cli, name, value)
    old = tmp_path / "old" / "python"
    new = tmp_path / "new" / "python"
    for python in (old, new):
        python.parent.mkdir()
        python.write_text("fake interpreter")
        python.chmod(0o755)
    records = {}
    processes = {}
    stops, spawns = [], []
    counter = [100]

    def add(slug="review", port=8802, pid=10):
        page = tmp_path / "pages" / slug
        page.mkdir(parents=True)
        (page / "current.html").write_text('<h1 data-anchor-id="title">review</h1>')
        (page / "comments.json").write_text('{"keep":"reviewer history"}')
        record = {"slug_dir": str(page), "project": "reviews", "pid": pid, "port": port,
                  "bus_file": str(tmp_path / "bus" / "reviews" / f"{slug}.ndjson"),
                  "public_base_path": f"/{slug}", "transport": "tailscale", "url": "https://keep-url",
                  "transport_details": {"https_port": 8447}, "owner_session": "previous-agent",
                  "owner_agent": "claude", "owner_claimed_at": "2026-09-01", "owner_label": "previous"}
        records[slug] = record
        argv = deployment._arguments(record, old)
        processes[pid] = {"pid": pid, "port": port, "directory": str(page.resolve()), "argv": argv}
        cli._save_state_for_project("reviews", {"project": "reviews", "slugs": records})
        return record

    def running():
        result = {}
        for process in processes.values():
            result.setdefault(process["directory"], []).append({"pid": process["pid"], "port": process["port"]})
        return result

    def stop(pid):
        stops.append(pid)
        processes.pop(pid, None)
        return True

    def run(argv, **kwargs):
        assert argv[0] == "ps"
        process = processes.get(int(argv[argv.index("-p") + 1]))
        return SimpleNamespace(stdout=shlex.join(process["argv"]) if process else "")

    def spawn(argv, **kwargs):
        assert kwargs["start_new_session"]
        assert "PYTHONPATH" not in kwargs["env"] and "PYTHONHOME" not in kwargs["env"]
        counter[0] += 1
        pid = counter[0]
        spawns.append(argv)
        processes[pid] = {"pid": pid, "port": int(argv[argv.index("--port") + 1]),
                          "directory": str(Path(argv[argv.index("--slug-dir") + 1]).resolve()), "argv": argv}
        return SimpleNamespace(pid=pid)

    monkeypatch.setattr(cli, "_running_servers", running)
    monkeypatch.setattr(cli, "_port_listen_pid", lambda port: next((p["pid"] for p in processes.values() if p["port"] == port), None))
    monkeypatch.setattr(cli, "_is_process_alive", lambda pid: pid in processes)
    monkeypatch.setattr(cli, "_stop_server", stop)
    monkeypatch.setattr(cli, "_wait_listening", lambda port, pid: pid in processes)
    monkeypatch.setattr(deployment.subprocess, "run", run)
    monkeypatch.setattr(deployment.subprocess, "Popen", spawn)
    monkeypatch.setattr(deployment, "_target_manifest", lambda python: copy.deepcopy(MANIFEST))
    monkeypatch.setattr(deployment, "_verify_server", lambda record, pid, expected: {"anchors": 1, "runtime": expected})
    cli.SHIM_PATH.parent.mkdir()
    cli.SHIM_PATH.write_text(f"#!/bin/sh\n# {cli.SHIM_MARKER}\nexec old\n")
    add()
    return SimpleNamespace(old=old, new=new, add=add, records=records, processes=processes,
                           stops=stops, spawns=spawns, tmp=tmp_path)


def test_restart_preserves_owner_comments_routes_and_exact_port(estate, monkeypatch):
    original = copy.deepcopy(estate.records["review"])
    monkeypatch.setenv("PYTHONPATH", "/old/source")
    monkeypatch.setenv("PYTHONHOME", "/old/python")
    result = deployment.restart_record("reviews", "review", estate.new)
    current = cli._load_state_for_project("reviews")["slugs"]["review"]
    for key, value in original.items():
        if key != "pid":
            assert current[key] == value
    assert current["pid"] == result["pid"] == 101
    assert estate.stops == [10]
    assert estate.spawns[0][:4] == [str(estate.new), "-I", "-m", "agent_annotate.sync_server"]
    assert "--strict-port" in estate.spawns[0]
    assert (Path(current["slug_dir"]) / "comments.json").read_text() == '{"keep":"reviewer history"}'


def test_stale_registry_pid_uses_reconciled_server_only(estate):
    state = cli._load_state_for_project("reviews")
    state["slugs"]["review"]["pid"] = 999
    cli._save_state_for_project("reviews", state)
    deployment.restart_record("reviews", "review", estate.new)
    assert estate.stops == [10]


def test_duplicate_live_servers_refuse_before_any_stop(estate):
    estate.processes[11] = {**estate.processes[10], "pid": 11}
    with pytest.raises(deployment.DeploymentError, match="ambiguous"):
        deployment.activate_runtime(estate.new)
    assert estate.stops == []
    assert estate.spawns == []


def test_foreign_listener_refuses_before_any_stop(estate, monkeypatch):
    monkeypatch.setattr(cli, "_port_listen_pid", lambda port: 444)
    with pytest.raises(deployment.DeploymentError, match="listener"):
        deployment.activate_runtime(estate.new)
    assert estate.stops == []


def test_process_command_must_match_resolved_directory(estate):
    argv = estate.processes[10]["argv"]
    argv[argv.index("--slug-dir") + 1] = "/some/other/page"
    with pytest.raises(deployment.DeploymentError, match="command identity"):
        deployment.restart_record("reviews", "review", estate.new)
    assert estate.stops == []


def test_identity_rechecked_immediately_before_stop(estate, monkeypatch):
    original = cli._running_servers
    reads = [0]
    def running():
        reads[0] += 1
        if reads[0] == 2:
            estate.processes[20] = {**estate.processes.pop(10), "pid": 20}
        return original()
    monkeypatch.setattr(cli, "_running_servers", running)
    with pytest.raises(deployment.DeploymentError, match="changed before stop"):
        deployment.restart_record("reviews", "review", estate.new)
    assert estate.stops == []
    assert 20 in estate.processes


def test_unrecognized_python_command_is_never_guessed(estate):
    estate.processes[10]["argv"][0] = "python3"
    with pytest.raises(deployment.DeploymentError, match="command identity"):
        deployment.restart_record("reviews", "review", estate.new)
    assert estate.stops == []


def test_restart_preserves_original_loopback_author_settings(estate):
    estate.processes[10]["argv"] += ["--local-author", "chang", "--local-author-name", "Chang Lee"]
    deployment.restart_record("reviews", "review", estate.new)
    assert estate.spawns[0][-4:] == ["--local-author", "chang", "--local-author-name", "Chang Lee"]


def test_later_foreign_page_fails_estate_preflight_before_first_stop(estate):
    estate.add("second", 8803, 11)
    estate.processes[11]["argv"][0] = "unknown-python"
    with pytest.raises(deployment.DeploymentError):
        deployment.activate_runtime(estate.new)
    assert estate.stops == []


def test_failed_start_restores_original_argv_owner_and_launcher(estate, monkeypatch):
    original = copy.deepcopy(estate.processes[10]["argv"])
    shim = cli.SHIM_PATH.read_bytes()
    verify = deployment._verify_server
    def fail_candidate(record, pid, expected):
        if expected is not None:
            raise deployment.DeploymentError("bad new build")
        return verify(record, pid, expected)
    monkeypatch.setattr(deployment, "_verify_server", fail_candidate)
    with pytest.raises(deployment.DeploymentError) as error:
        deployment.activate_runtime(estate.new)
    assert error.value.result["rolled_back"]
    assert estate.spawns[-1] == original
    current = cli._load_state_for_project("reviews")["slugs"]["review"]
    assert current["owner_session"] == "previous-agent"
    assert current["pid"] == 102
    assert "runtime_python" not in current
    assert cli.SHIM_PATH.read_bytes() == shim


def test_later_page_failure_rolls_back_earlier_successful_restart(estate, monkeypatch):
    estate.add("second", 8803, 11)
    verify = deployment._verify_server
    def fail_second(record, pid, expected):
        if record["port"] == 8803 and expected is not None:
            raise deployment.DeploymentError("second build failed")
        return verify(record, pid, expected)
    monkeypatch.setattr(deployment, "_verify_server", fail_second)
    with pytest.raises(deployment.DeploymentError) as error:
        deployment.activate_runtime(estate.new)
    assert error.value.result["rolled_back"]
    current = cli._load_state_for_project("reviews")["slugs"]
    assert all(record["owner_session"] == "previous-agent" for record in current.values())
    assert all("runtime_python" not in record for record in current.values())
    assert all(process["argv"][0] == str(estate.old) for process in estate.processes.values())


def test_activation_failure_restores_initially_stopped_page_state(estate, monkeypatch):
    estate.processes.pop(10)
    estate.add("second", 8803, 11)
    verify = deployment._verify_server
    def fail_second(record, pid, expected):
        if record["port"] == 8803 and expected is not None:
            raise deployment.DeploymentError("second build failed")
        return verify(record, pid, expected)
    monkeypatch.setattr(deployment, "_verify_server", fail_second)
    with pytest.raises(deployment.DeploymentError) as error:
        deployment.activate_runtime(estate.new)
    assert error.value.result["rolled_back"]
    current = cli._load_state_for_project("reviews")["slugs"]["review"]
    assert current["pid"] == 10
    assert "runtime_python" not in current
    assert not any(process["port"] == 8802 for process in estate.processes.values())


def test_activation_reports_failed_current_page_rollback(estate, monkeypatch):
    def replaced_candidate(record, pid, expected):
        estate.processes[999] = {**estate.processes.pop(pid), "pid": 999}
        raise deployment.DeploymentError("replacement stolen")
    monkeypatch.setattr(deployment, "_verify_server", replaced_candidate)
    with pytest.raises(deployment.DeploymentError) as error:
        deployment.activate_runtime(estate.new)
    assert not error.value.result["rolled_back"]
    assert error.value.result["rollback_errors"]
    assert estate.stops == [10]


def test_post_stop_foreign_port_is_never_killed_or_displaced(estate, monkeypatch):
    original_stop = cli._stop_server
    def stopped_then_foreign(pid):
        original_stop(pid)
        estate.processes[444] = {"pid": 444, "port": 8802, "directory": "/foreign", "argv": ["foreign"]}
        return True
    monkeypatch.setattr(cli, "_stop_server", stopped_then_foreign)
    with pytest.raises(deployment.DeploymentError) as error:
        deployment.activate_runtime(estate.new)
    assert not error.value.result["rolled_back"]
    assert estate.stops == [10]
    assert estate.spawns == []
    assert 444 in estate.processes


def test_foreign_process_during_rollback_is_never_killed(estate, monkeypatch):
    def replaced_candidate(record, pid, expected):
        estate.processes[999] = {**estate.processes.pop(pid), "pid": 999}
        raise deployment.DeploymentError("replacement stolen")
    monkeypatch.setattr(deployment, "_verify_server", replaced_candidate)
    with pytest.raises(deployment.DeploymentError) as error:
        deployment.restart_record("reviews", "review", estate.new)
    assert not error.value.result["rolled_back"]
    assert estate.stops == [10]
    assert 999 in estate.processes


def test_successful_activation_replaces_symlink_without_modifying_target(estate):
    old_launcher = estate.tmp / "old-launcher"
    old_launcher.write_bytes(cli.SHIM_PATH.read_bytes())
    original = old_launcher.read_bytes()
    cli.SHIM_PATH.unlink()
    cli.SHIM_PATH.symlink_to(old_launcher)
    result = deployment.activate_runtime(estate.new)
    assert result["ok"]
    assert not cli.SHIM_PATH.is_symlink()
    assert str(estate.new) in cli.SHIM_PATH.read_text()
    assert old_launcher.read_bytes() == original
    assert cli.SHIM_PATH.stat().st_mode & 0o111


def test_foreign_launcher_blocks_before_any_page_stop(estate):
    cli.SHIM_PATH.write_text("#!/bin/sh\nexec libgd\n")
    with pytest.raises(deployment.DeploymentError, match="another tool"):
        deployment.activate_runtime(estate.new)
    assert estate.stops == []


def test_duplicate_registry_ports_refuse_before_any_stop(estate):
    estate.add("second", 8802, 11)
    with pytest.raises(deployment.DeploymentError, match="duplicate"):
        deployment.activate_runtime(estate.new)
    assert estate.stops == []


def test_shim_replace_failure_rolls_pages_back_and_preserves_original_link(estate, monkeypatch):
    target = estate.tmp / "old-launcher"
    target.write_bytes(cli.SHIM_PATH.read_bytes())
    cli.SHIM_PATH.unlink()
    cli.SHIM_PATH.symlink_to(target)
    def fail_replace(*args, **kwargs):
        raise OSError("cannot replace launcher")
    monkeypatch.setattr(deployment, "_replace_shim", fail_replace)
    with pytest.raises(deployment.DeploymentError) as error:
        deployment.activate_runtime(estate.new)
    assert error.value.result["rolled_back"]
    assert cli.SHIM_PATH.is_symlink()
    assert os.readlink(cli.SHIM_PATH) == str(target)
    assert all(process["argv"][0] == str(estate.old) for process in estate.processes.values())


def test_verify_requires_exact_runtime_build_and_content_anchors(estate, monkeypatch):
    response = SimpleNamespace()
    class Reply:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, limit):
            return json.dumps({"version": "2.20.0", "runtime": response.runtime}).encode()
    monkeypatch.setattr(deployment.urllib.request, "urlopen", lambda *args, **kwargs: Reply())
    monkeypatch.setattr(deployment.verify, "probe_http", lambda *args, **kwargs: SimpleNamespace(ok=True, anchors=3))
    response.runtime = MANIFEST
    record = estate.records["review"]
    assert REAL_VERIFY(record, 10, MANIFEST)["anchors"] == 3
    response.runtime = {**MANIFEST, "build_id": "other-build"}
    with pytest.raises(deployment.DeploymentError, match="version/build/assets"):
        REAL_VERIFY(record, 10, MANIFEST)


@pytest.mark.parametrize("path", [Path("relative-python"), Path("/nonexistent/python")])
def test_staged_python_must_be_existing_absolute_executable(estate, path):
    with pytest.raises(deployment.DeploymentError, match="absolute executable"):
        REAL_TARGET(path)
    assert estate.stops == []


def test_staged_python_manifest_must_match_reported_version(estate, monkeypatch):
    def run(argv, **kwargs):
        assert argv[1] == "-I"
        if argv[-1] == "--version":
            return SimpleNamespace(stdout="agent-annotate 2.20.0\n")
        return SimpleNamespace(stdout=json.dumps({**MANIFEST, "package_version": "2.19.0"}))
    monkeypatch.setattr(deployment.subprocess, "run", run)
    with pytest.raises(deployment.DeploymentError, match="manifest"):
        REAL_TARGET(estate.new)
    assert estate.stops == []
