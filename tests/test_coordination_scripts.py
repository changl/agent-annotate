"""Stage 2 coordination scripts: leases, the run digest and the brief template (agent-annotate-90o)."""

import importlib.util
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lease = load("lease")
run_summary = load("run_summary")
brief = load("brief")


@pytest.fixture(autouse=True)
def runs_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ORCA_RUNS_DIR", str(tmp_path))
    return tmp_path


def test_lease_take_refuse_expire_release(runs_dir, capsys, monkeypatch):
    base = ["--run", "run_t"]
    assert lease.main(["take", "ports-18710", *base, "--owner", "a", "--note", "sandbox"]) == 0
    assert lease.main(["take", "ports-18710", *base, "--owner", "b"]) == 1
    assert "held by a" in capsys.readouterr().out
    assert lease.main(["take", "ports-18710", *base, "--owner", "a"]) == 0  # renewing your own lease
    assert lease.main(["take", "ci-slot", *base, "--owner", "a"]) == 0
    assert lease.main(["release", *base, "--owner", "b"]) == 0  # b holds nothing; a's leases stay
    assert len(list((runs_dir / "run_t/leases").glob("*.json"))) == 2
    assert lease.main(["release", *base, "--owner", "a"]) == 0  # no names: all of a's
    assert not list((runs_dir / "run_t/leases").glob("*.json"))
    assert lease.main(["take", "disk", *base, "--owner", "a", "--ttl-min", "1"]) == 0
    real_time = lease.time.time
    monkeypatch.setattr(lease.time, "time", lambda: real_time() + 120)
    assert lease.main(["take", "disk", *base, "--owner", "b"]) == 0  # expired leases are taken over
    lease.main(["list", *base])
    assert "disk b until" in capsys.readouterr().out.splitlines()[-1]


@pytest.mark.parametrize("name", ["../x", "a/b", "", ".hidden"])
def test_lease_rejects_unsafe_names(name):
    with pytest.raises(SystemExit):
        lease.main(["take", name, "--run", "run_t", "--owner", "a"])


def test_run_summary_stays_within_40_lines():
    many = 30
    orca = {
        "run": {"objective": "x" * 200},
        "tasks": [{"id": f"task_{i}", "status": "ready", "title": f"t{i}"} for i in range(many)],
        "workers": [{"dispatchId": f"ctx_{i}", "taskId": f"task_{i}", "state": "ready", "liveness": "live"} for i in range(many)],
        "gates": [],
    }
    beads = {"in_progress": [{"id": f"b{i}", "title": "t", "priority": "1"} for i in range(many)],
             "ready": [{"id": f"r{i}", "title": "t"} for i in range(many)]}
    leases = [{"name": f"l{i}", "owner": "o", "expires": 2_000_000_000} for i in range(many)]
    status = [{"t": "2026-11-04T06:00:00Z", "dispatch": "ctx_1", "subject": "s"}] * many
    lines = run_summary.render("run_t", orca, beads, leases, status, now=1_900_000_000)
    assert len(lines) <= run_summary.MAX_LINES
    assert lines[0].startswith("Run run_t: ")
    assert "Workers live: 30" in lines
    assert any(line.startswith("Leases: 30 held") for line in lines)


def test_run_summary_tolerates_missing_sources():
    lines = run_summary.render("run_t", {}, None, [], [], now=0)
    assert "Beads: bd unavailable here" in lines
    assert "Tasks: none" in lines


def test_brief_fills_rules_and_delta():
    text = brief.render({"id": "aa-1", "title": "Do X", "description": "Why X."}, "run_t", "main", "changl/x", "Only X.")
    assert text.startswith("Bead aa-1: Do X")
    assert "open a PR against main" in text and "Only X." in text
    assert f"python3 {brief.LEASE} take NAME --run run_t" in text
    assert "--priority high" in text and "{" not in text
