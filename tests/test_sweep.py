"""Stage 4 sweep.py: one line per check, judgment items to a file, removal only when finished."""

import importlib.util
import os
import plistlib
import subprocess
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
NOW = 1_800_000_000


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sweep(tmp_path, monkeypatch):
    monkeypatch.delenv("ANNOTATE_OWNERSHIP_MANIFEST", raising=False)
    monkeypatch.setenv("ANNOTATE_SWEEP_DIR", str(tmp_path / "sweeps"))
    monkeypatch.setenv("ANNOTATE_BUS_ROOT", str(tmp_path / "bus"))
    return load("sweep")


def test_unset_ownership_preserves_baseline_bytes(sweep, monkeypatch, capsys):
    monkeypatch.setattr(sweep.time, "time", lambda: NOW)
    for name in ("beads", "disk", "sessions"):
        monkeypatch.setattr(sweep, name, lambda *a, n=name: (f"{n}: baseline", [f"{n} item"]))
    assert sweep.main(["all"]) == 0
    lines = b"beads: baseline\ndisk: baseline\nsessions: baseline\n"
    assert capsys.readouterr().out.encode() == lines
    stamp = time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime(NOW)).encode()
    assert (sweep.OUT / "latest.txt").read_bytes() == (
        b"sweep " + stamp + b"\n" + lines + b"\nbeads item\ndisk item\nsessions item\n")
    assert not (sweep.OUT / "ownership-latest.json").exists()


def test_failing_ownership_helper_writes_error(sweep, tmp_path, monkeypatch, capsys):
    helper = tmp_path / "fails.py"
    helper.write_text("raise SystemExit(1)\n")
    monkeypatch.setenv("ANNOTATE_OWNERSHIP_MANIFEST", str(helper))
    for name in ("beads", "disk", "sessions"):
        monkeypatch.setattr(sweep, name, lambda *a, n=name: (f"{n}: baseline", []))
    assert sweep.main(["all"]) == 1
    assert "ownership: error " in capsys.readouterr().out
    assert "ownership: error " in (sweep.OUT / "latest.txt").read_text()
    assert '"status": "error"' in (sweep.OUT / "ownership-latest.json").read_text()


def stamp(hours_ago):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - hours_ago * 3600))


def test_beads_line_and_items(sweep, monkeypatch):
    answers = {
        "open": [{"id": f"aa-{i}"} for i in range(4)],
        "in_progress": [{"id": "aa-old", "title": "Stale", "updated_at": stamp(30)},
                        {"id": "aa-new", "title": "Fresh", "updated_at": stamp(2)}],
        "ready": [{"id": "aa-1"}],
        "closed": [{"id": "aa-c1", "title": "Proved", "close_reason": "PR #9 merged; full suite 2187 passed"},
                   {"id": "aa-c2", "title": "Bare", "close_reason": "done"}],
    }

    def fake(argv, cwd=None):
        return answers["ready"] if argv[1] == "ready" else answers[argv[argv.index("--status") + 1]]

    monkeypatch.setattr(sweep, "run_json", fake)
    line, items = sweep.beads(None, NOW)
    assert line == "beads: 4 open · 1 ready · 1 in progress over 24 h · 1 closed without proof"
    assert items[0].startswith("bead aa-old in progress, untouched 30 h") and "aa-c2 closed without proof" in items[1]
    monkeypatch.setattr(sweep, "run_json", lambda argv, cwd=None: None)
    assert sweep.beads(None, NOW) == ("beads: bd unavailable here", [])


def test_disk_counts_quiet_buses(sweep, tmp_path):
    bus = tmp_path / "bus/reviews"
    bus.mkdir(parents=True)
    for name, days in (("old", 40), ("new", 1)):
        (bus / f"{name}.ndjson").write_text("{}\n")
        os.utime(bus / f"{name}.ndjson", (NOW - days * 86400,) * 2)
    line, items = sweep.disk(NOW)
    assert line.startswith("disk: ") and line.endswith("· 1 quiet buses over 30 days")
    assert items == ["bus reviews/old quiet 40 days (annotate prune-bus --apply archives it)"]


def test_bead_ids_from_branch_and_path():
    sweep = load("sweep")
    assert {"fld-13hb", "agent-annotate-zsc", "FLD-r7a1"} <= set(
        sweep.bead_ids(["fld-13hb-provisioner-auth", "Ship it (agent-annotate-zsc)", "FLD-r7a1-carplay-trim"]))
    assert "aa-stage4" not in sweep.bead_ids(["changl/aa-stage4"])


def test_sessions_removes_only_finished_and_never_denied(sweep, tmp_path, monkeypatch):
    trees = {name: tmp_path / name for name in ("done", "dirty", "open-bead", "no-bead", "main")}
    for path in trees.values():
        path.mkdir()
    denied = sweep.DENY[0]
    listing = [{"id": f"r::{p}", "path": str(p), "hostId": "local", "branch": f"refs/heads/w/{n}-x1y",
                "isMainWorktree": n == "main"} for n, p in trees.items()]
    listing.append({"id": "r::deny", "path": denied, "hostId": "local", "branch": "refs/heads/changl/rebex-library-performance"})
    listing.append({"id": "r::far", "path": str(trees["done"]), "hostId": "runtime:m5", "branch": "refs/heads/w/far"})
    calls = []

    def fake_json(argv, cwd=None):
        calls.append((argv, cwd))
        if argv[:3] == ["orca", "worktree", "list"]:
            return {"worktrees": listing}
        if argv[:3] == ["orca", "worktree", "rm"]:
            return {"removed": True}
        if argv[:2] == ["gh", "pr"]:
            return [{"number": 7, "title": "t", "body": "" if cwd.endswith("no-bead") else "bead aa-x1y"}]
        if argv[:2] == ["bd", "show"]:  # only aa-x1y exists; other bead-like words are not beads
            return [{"id": "aa-x1y", "status": "open" if cwd.endswith("open-bead") else "closed"}] if argv[2] == "aa-x1y" else None
        raise AssertionError(argv)

    real_run = subprocess.run

    def fake_run(argv, **kw):
        if argv[:2] == ["git", "--no-optional-locks"]:
            assert os.path.realpath(argv[3]) != os.path.realpath(denied)  # the deny list is never inspected
            dirty = " M x\n" if argv[3].endswith("dirty") else ""
            return subprocess.CompletedProcess(argv, 0, dirty, "")
        return real_run(argv, **kw)

    monkeypatch.setattr(sweep, "run_json", fake_json)
    monkeypatch.setattr(sweep.subprocess, "run", fake_run)
    line, items = sweep.sessions(apply=False)
    assert line == "sessions: 1 finished worktrees (PR merged, bead closed, clean tree) · 0 removed"
    assert not [c for c in calls if c[0][:3] == ["orca", "worktree", "rm"]]
    assert any("no-bead: PR #7 merged, tree clean, no bead named" in i for i in items)
    assert any(denied in i and "not inspected" in i for i in items)
    line, items = sweep.sessions(apply=True)
    assert line.endswith("· 1 removed")
    removed = [c[0] for c in calls if c[0][:3] == ["orca", "worktree", "rm"]]
    assert removed == [["orca", "worktree", "rm", "--worktree", f"id:r::{trees['done']}", "--json"]]


def test_main_writes_latest_and_run_summary_shows_it(sweep, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sweep, "beads", lambda d, now: ("beads: 1 open · 0 ready · 0 in progress over 24 h · 0 closed without proof", ["bead x"]))
    monkeypatch.setattr(sweep, "sessions", lambda apply: ("sessions: 0 finished worktrees (PR merged, bead closed, clean tree) · 0 removed", []))
    assert sweep.main(["all"]) == 0
    assert len(capsys.readouterr().out.splitlines()) == 3
    latest = tmp_path / "sweeps/latest.txt"
    run_summary = load("run_summary")
    shown = run_summary.summary_lines(latest)
    assert shown[0].startswith("sweep ") and shown[1].startswith("beads: ") and len(shown) == 4
    lines = run_summary.render("run_t", {}, None, [], [], now=0, extra=[shown])
    assert lines[-3].startswith("beads: ") and "bead x" not in "\n".join(lines)


def test_plist_is_hourly_report_only():
    plist = plistlib.loads((SCRIPTS / "launchd/com.changlee.annotate-sweep.plist").read_bytes())
    assert plist["Label"] == "com.changlee.annotate-sweep" and plist["StartInterval"] == 3600
    assert plist["ProgramArguments"][2:4] == ["/Users/changlee/.local/share/annotate-sweeps/sweep.py", "all"]
    assert "--apply" not in plist["ProgramArguments"] and plist["RunAtLoad"] is False


def test_brief_names_the_full_suite_receipt():
    brief = load("brief")
    text = brief.render({"id": "aa-1", "title": "X"}, "run_t", None, None, None)
    assert "scripts/ci.py --full → read the receipt line" in text
