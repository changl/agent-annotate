"""Cleanup needs an exact page scope and a corroborated process/route."""

import copy
import shlex
import signal
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_annotate import cli, deployment, mcp_server, transports


@pytest.fixture
def estate(tmp_path, monkeypatch):
    for name, value in {"STATE_DIR": tmp_path / "state", "LOCK_DIR": tmp_path / "locks",
                        "BUS_ROOT": tmp_path / "bus"}.items():
        monkeypatch.setattr(cli, name, value)
    processes, signals, routes = {}, [], []
    foreign = set()
    behavior = {"result": {"ok": True, "details": {"action": "removed"}}, "stubborn": False}

    def add(project="alpha", slug="shared", pid=10, port=8802, mount="/shared"):
        page = tmp_path / "pages" / project / slug
        page.mkdir(parents=True)
        (page / "current.html").write_text("<h1>Review</h1>")
        (page / "comments.json").write_text('{"history":"keep"}')
        bus = tmp_path / "bus" / project / f"{slug}.ndjson"
        bus.parent.mkdir(parents=True, exist_ok=True)
        bus.write_text('{"event":"keep"}\n')
        record = {"project": project, "slug": slug, "slug_dir": str(page), "pid": pid, "port": port,
                  "transport": "tailscale", "public_base_path": mount,
                  "bus_file": str(bus), "url": "https://page.example/", "owner_session": "mine",
                  "transport_details": {"hostname": "page.example", "https_port": 8447}}
        state = cli._load_state_for_project(project)
        state["slugs"][slug] = record
        cli._save_state_for_project(project, state)
        if pid is not None:
            processes[pid] = {"pid": pid, "port": port, "directory": str(page),
                              "argv": deployment._arguments(record, Path(sys.executable))}
        return record

    def running():
        result = {}
        for p in processes.values():
            result.setdefault(p["directory"], []).append({"pid": p["pid"], "port": p["port"]})
        return result

    def run(argv, **kwargs):
        assert argv[:2] == ["ps", "-ww"]
        return SimpleNamespace(stdout=shlex.join(processes[int(argv[argv.index("-p") + 1])]["argv"]))

    def kill(pid, sig):
        assert pid in processes, "never signal the stored PID without ownership"
        signals.append((pid, sig))
        if not behavior["stubborn"]:
            processes.pop(pid)

    def remove(slug, **opts):
        routes.append((slug, opts))
        if isinstance(behavior["result"], Exception):
            raise behavior["result"]
        return copy.deepcopy(behavior["result"])

    monkeypatch.setattr(cli, "_running_servers", running)
    monkeypatch.setattr(cli, "_port_listen_pid", lambda port: next((p["pid"] for p in processes.values() if p["port"] == port), None))
    monkeypatch.setattr(cli, "_is_process_alive", lambda pid: pid in processes or pid in foreign)
    monkeypatch.setattr(cli, "_project_config", lambda project: {})
    monkeypatch.setattr(cli, "_session_id", lambda: "mine")
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)
    monkeypatch.setattr(cli.os, "kill", kill)
    monkeypatch.setattr(deployment.subprocess, "run", run)
    monkeypatch.setattr(transports, "load", lambda name: SimpleNamespace(unpublish=remove))
    return SimpleNamespace(add=add, processes=processes, signals=signals, routes=routes,
                           foreign=foreign, behavior=behavior)


def cleanup(slug="alpha/shared", project=None):
    return cli.cmd_unpublish(SimpleNamespace(slug=slug, project=project))


@pytest.mark.parametrize("target,project", [("shared", None), ("missing/shared", None),
                                          ("pha/shared", None), ("alpha/shared", "beta"),
                                          ("shared", "missing"), ("shared/alpha", None)])
def test_ambiguous_or_wrong_scope_never_tears_down(estate, target, project):
    estate.add()
    estate.add("beta", pid=None, port=8803)
    assert cleanup(target, project) == 2
    assert estate.signals == estate.routes == []
    assert "shared" in cli._load_state_for_project("alpha")["slugs"]
    assert "shared" in cli._load_state_for_project("beta")["slugs"]


@pytest.mark.parametrize("target,project", [("alpha/shared", None), ("shared", "alpha")])
def test_exact_qualification_cleans_only_selected_page_and_preserves_history(estate, target, project):
    record = estate.add()
    estate.add("zzalpha", pid=11, port=8803)
    assert cleanup(target, project) == 0
    assert estate.signals == [(10, signal.SIGTERM)]
    assert cli._load_state_for_project("alpha")["slugs"] == {}
    assert "shared" in cli._load_state_for_project("zzalpha")["slugs"]
    assert (Path(record["slug_dir"]) / "comments.json").read_text() == '{"history":"keep"}'
    assert Path(record["bus_file"]).read_text() == '{"event":"keep"}\n'


def test_root_mount_still_removes_recorded_transport(estate):
    estate.add(mount="")
    assert cleanup() == 0
    assert estate.routes == [("", {"port": 8802, "hostname": "page.example", "https_port": 8447})]


def test_recycled_record_pid_is_never_signaled(estate):
    estate.add()
    estate.processes.pop(10)
    estate.foreign.add(10)
    assert cleanup() == 1
    assert estate.signals == estate.routes == []
    assert "shared" in cli._load_state_for_project("alpha")["slugs"]


def test_restarted_owned_server_uses_current_pid_not_stale_record(estate):
    estate.add()
    estate.processes[20] = {**estate.processes.pop(10), "pid": 20}
    estate.foreign.add(10)
    assert cleanup() == 0
    assert estate.signals == [(20, signal.SIGTERM)]
    assert cli._load_state_for_project("alpha")["slugs"] == {}
    assert 10 in estate.foreign


@pytest.mark.parametrize("fault", ["listener", "argv", "ambiguous"])
def test_owned_process_proof_precedes_transport_removal(estate, monkeypatch, fault):
    estate.add()
    if fault == "listener":
        monkeypatch.setattr(cli, "_port_listen_pid", lambda port: 999)
    elif fault == "argv":
        estate.processes[10]["argv"][-1] = "/different"
    else:
        estate.processes[11] = {**estate.processes[10], "pid": 11}
    assert cleanup() == 1
    assert estate.signals == estate.routes == []


@pytest.mark.parametrize("result", [{"ok": False}, RuntimeError("inert failure"),
                                   {"ok": True, "details": {"action": "noop", "reason": ":8447 now proxies other"}},
                                   {"ok": True, "details": {"action": "noop"}},
                                   {"ok": True, "details": {"tailscale": {"action": "noop", "reason": "refusing to guess"}}}])
def test_failed_or_uncorroborated_teardown_retains_receipt_and_live_process(estate, result, capsys):
    estate.add()
    estate.behavior["result"] = result
    assert cleanup() == 1
    assert estate.signals == []
    assert 10 in estate.processes
    assert "shared" in cli._load_state_for_project("alpha")["slugs"]
    assert "registration retained" in capsys.readouterr().err


@pytest.mark.parametrize("details", [{"action": "noop", "reason": "no serve mapping on :8447"},
                                    {"action": "noop", "reason": "no matching rule"},
                                    {"action": "noop", "cloudflare": {"action": "noop", "reason": "no matching rule"},
                                     "tailscale": {"action": "noop", "reason": "no serve mapping for origin"}}])
def test_proven_already_absent_route_is_success(estate, details):
    estate.add(pid=None)
    estate.behavior["result"] = {"ok": True, "details": details}
    assert cleanup() == 0
    assert estate.signals == []


def test_stop_failure_retains_receipt_without_hard_kill(estate, capsys):
    estate.add()
    estate.behavior["stubborn"] = True
    assert cleanup() == 1
    assert estate.signals == [(10, signal.SIGTERM)]
    assert "shared" in cli._load_state_for_project("alpha")["slugs"]
    assert "no hard kill" in capsys.readouterr().err


def test_process_identity_change_after_route_removal_sends_no_signal(estate, monkeypatch):
    estate.add()
    original = cli._running_servers
    calls = [0]
    def changed():
        calls[0] += 1
        if calls[0] == 2:
            estate.processes[20] = {**estate.processes.pop(10), "pid": 20}
        return original()
    monkeypatch.setattr(cli, "_running_servers", changed)
    assert cleanup() == 1
    assert len(estate.routes) == 1
    assert estate.signals == []
    assert "shared" in cli._load_state_for_project("alpha")["slugs"]


def test_registration_changed_after_selection_is_not_removed(estate, monkeypatch):
    estate.add()
    original = cli._resolve_scoped_slug
    def changed(*args):
        selected = original(*args)
        state = cli._load_state_for_project("alpha")
        state["slugs"]["shared"]["port"] = 9999
        cli._save_state_for_project("alpha", state)
        return selected
    monkeypatch.setattr(cli, "_resolve_scoped_slug", changed)
    assert cleanup() == 1
    assert estate.routes == estate.signals == []
    assert cli._load_state_for_project("alpha")["slugs"]["shared"]["port"] == 9999


@pytest.mark.parametrize("alias", ["directory", "port"])
def test_receipt_shared_with_another_scope_refuses_all_teardown(estate, alias):
    first = estate.add()
    estate.add("beta", pid=None, port=8803)
    state = cli._load_state_for_project("beta")
    key = "slug_dir" if alias == "directory" else "port"
    state["slugs"]["shared"][key] = first[key]
    cli._save_state_for_project("beta", state)
    assert cleanup() == 1
    assert estate.routes == estate.signals == []
    assert "shared" in cli._load_state_for_project("alpha")["slugs"]


@pytest.mark.parametrize("command", [cli.cmd_claim, cli.cmd_connect, cli.cmd_disconnect, cli.cmd_monitor,
                                      cli.cmd_ask, cli.cmd_close, cli.cmd_archive_comment, cli.cmd_addressed,
                                      cli.cmd_resolve, cli.cmd_carry, cli.cmd_deliver, cli.cmd_project,
                                      cli.cmd_retire, cli.cmd_finding, cli.cmd_plan, cli.cmd_copy])
@pytest.mark.parametrize("target", ["shared", "missing/shared"])
def test_mutations_refuse_ambiguous_and_missing_project_before_action(estate, monkeypatch, command, target):
    estate.add()
    estate.add("beta", pid=None, port=8803)
    before = {project: cli._load_state_for_project(project) for project in ("alpha", "beta")}
    monkeypatch.setattr(cli, "_api", lambda *a, **kw: pytest.fail("ambiguous call must never reach HTTP"))
    args = SimpleNamespace(slug=target, project=None, comment_id="c1", response="done", in_version="v2",
                           to_version="v2", anchor="a1", from_file="inert.json", dead=False)
    assert command(args) == 2
    assert estate.routes == estate.signals == []
    assert before == {project: cli._load_state_for_project(project) for project in ("alpha", "beta")}


@pytest.mark.parametrize("target,project", [("alpha/shared", None), ("shared", "alpha")])
def test_exact_comment_mutation_routes_to_selected_scope(estate, monkeypatch, target, project):
    estate.add()
    estate.add("zzalpha", pid=None, port=8803)
    called = []
    def api(record, *args):
        called.append(record["project"])
        return 200, {"id": "c1"}
    monkeypatch.setattr(cli, "_api", api)
    assert cli.cmd_addressed(SimpleNamespace(slug=target, project=project, comment_id="c1",
                                            response="done", author="agent:inert")) == 0
    assert called == ["alpha"]


def test_mcp_duplicate_bare_slug_refuses_and_exact_project_selects(estate):
    estate.add()
    estate.add("zzalpha", pid=None, port=8803)
    with pytest.raises(ValueError, match="unique exact"):
        mcp_server._record("shared")
    assert mcp_server._record("alpha/shared")["project"] == "alpha"
    assert mcp_server._record("zzalpha/shared")["project"] == "zzalpha"


@pytest.mark.parametrize("target", ["missing/shared", "pha/shared", "shared/alpha"])
def test_mcp_missing_exact_qualification_cannot_fall_back(estate, target):
    estate.add()
    with pytest.raises(ValueError, match="unique exact"):
        mcp_server._record(target)
