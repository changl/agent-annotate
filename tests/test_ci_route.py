"""scripts/ci.py --full goes to the M1 through wm-test only when a private route is ready (agent-annotate-4zw)."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("ci_script", Path(__file__).resolve().parents[1] / "scripts/ci.py")
ci = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ci)

READY = {"ready": True, "repos": {"agent-annotate": {"source": "/x"}}, "profiles": {"full": {}}}


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run([*git, "init", "-q"], check=True)
    (root / "a.txt").write_text("a\n")
    subprocess.run([*git, "add", "a.txt"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "a"], check=True)
    head = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "wm-test").write_text("#!/bin/sh\n")
    (bin_dir / "wm-test").chmod(0o755)
    config = tmp_path / "wm-test.json"
    config.write_text(json.dumps(READY))
    return root, head, config, {"PATH": str(bin_dir)}


def test_ready_route_submits_exactly_head_of_a_clean_checkout(repo):
    root, head, config, env = repo
    route = ci.full_route(root, env, config)
    assert route[1:] == ["agent-annotate", "full", "--sha", head, "--config", str(config)]
    assert Path(route[0]).name == "wm-test"


def test_inside_the_executor_full_stays_local(repo):
    root, _, config, env = repo
    assert ci.full_route(root, {**env, "WM_TEST_ARTIFACTS": "/job/artifacts"}, config) is None


@pytest.mark.parametrize("settings", [None, {**READY, "repos": {"other": {}}}, {**READY, "profiles": {"fast": {}}},
                                      {"ready": False, "repos": {"other": {}}, "profiles": {"full": {}}}])
def test_no_config_for_this_repo_and_profile_stays_local(repo, settings):
    root, _, config, env = repo
    if settings is None:
        config.unlink()
    else:
        config.write_text(json.dumps(settings))
    assert ci.full_route(root, env, config) is None


@pytest.mark.parametrize("ready", [False, None, "true"])
def test_registered_route_that_is_not_ready_fails_instead_of_running_here(repo, ready):
    root, _, config, env = repo
    settings = {**READY, "ready": ready} if ready is not None else {k: v for k, v in READY.items() if k != "ready"}
    config.write_text(json.dumps(settings))
    with pytest.raises(SystemExit, match="configured but not ready"):
        ci.full_route(root, env, config)


@pytest.mark.parametrize("change", ["modified", "untracked"])
def test_uncommitted_or_untracked_changes_are_refused_not_left_out(repo, change):
    root, _, config, env = repo
    (root / ("a.txt" if change == "modified" else "new.txt")).write_text("changed\n")
    with pytest.raises(SystemExit, match="uncommitted or untracked"):
        ci.full_route(root, env, config)


def test_ready_route_without_the_helper_fails_instead_of_running_here(repo, tmp_path):
    root, _, config, _ = repo
    with pytest.raises(SystemExit, match="not on PATH"):
        ci.full_route(root, {"PATH": str(tmp_path / "empty")}, config)


def test_unreadable_config_fails_loudly(repo):
    root, _, config, env = repo
    config.write_text("{not json")
    with pytest.raises(ValueError):
        ci.full_route(root, env, config)


@pytest.fixture
def steps(monkeypatch):
    calls = []
    monkeypatch.setattr(ci.subprocess, "run", lambda command, **kwargs: calls.append(command)
                        or subprocess.CompletedProcess(command, 0))
    return calls


def test_routed_full_runs_only_wm_test(monkeypatch, steps):
    monkeypatch.setattr(ci, "full_route", lambda: ["wm-test", "agent-annotate", "full", "--sha", "a" * 40])
    with pytest.raises(SystemExit) as exit_info:
        ci.main(["--full", "--work-item", "agent-annotate-4zw"])
    assert exit_info.value.code == 0
    assert steps == [["wm-test", "agent-annotate", "full", "--sha", "a" * 40, "--work-item", "agent-annotate-4zw"]]


@pytest.mark.parametrize("argv", [[], ["--full", "--local"]])
def test_fast_gate_and_explicit_local_never_consult_the_route(monkeypatch, steps, argv):
    monkeypatch.setattr(ci, "full_route", lambda: pytest.fail("route consulted"))
    ci.main(argv)
    assert steps[0][1:4] == ["-m", "ruff", "check"]
    assert steps[-1][1:4] == ["-m", "pytest", "-q"]
    assert ("tests" in steps[-1]) == ("--full" in argv)
