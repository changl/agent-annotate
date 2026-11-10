"""Board discovery, guarded actions and judgement receipts never use live state."""

import datetime
import json
import os
import subprocess
from pathlib import Path

import pytest

from agent_annotate import board_checks as checks_module
from agent_annotate import board_followups as followups
from agent_annotate import cli
from agent_annotate.hooks.check_comment_bus import _slug_line

NOW = datetime.datetime(2026, 11, 10, 6, 5, tzinfo=datetime.timezone.utc)


@pytest.fixture
def checks(tmp_path, monkeypatch):
    monkeypatch.setenv("ANNOTATE_BOARD_DRY_RUN", "1")
    monkeypatch.setattr(checks_module, "OUT", tmp_path / "board-checks")
    return checks_module


def board(tmp_path):
    page = tmp_path / "page"
    page.mkdir(exist_ok=True)
    return {"path": str(tmp_path / ".beads"), "repo": str(tmp_path), "prefix": "agent-annotate",
            "project": "p", "slug": "s", "record": {"slug_dir": str(page), "owner_session": "one"}}


def test_discovery_owner_worktree_fallback_newest_and_deduplicated(checks, tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("ANNOTATE_STATE_DIR", str(state))
    owner = tmp_path / "owner"
    owner.mkdir()
    entries = {}
    for name, age in (("old", 1), ("new", 2), ("unowned", 3), ("archived", 4), ("no-board", 5), ("fallback", 0)):
        page = tmp_path / name
        page.mkdir()
        entries[name] = {"slug_dir": str(page), "owner_session": None if name == "unowned" else "owner",
                         "started_at": age, "owner_target": {"worktree": "id::" + str(owner)},
                         "archived": name == "archived"}
    entries["no-board"]["owner_target"] = {}
    entries["fallback"]["owner_target"] = {"worktree": "id::/missing"}
    (state / "p.json").write_text(json.dumps({"slugs": entries}))
    calls = []

    def where(argv, cwd):
        calls.append(cwd)
        assert argv == ["bd", "--readonly", "where", "--json"]
        return None if cwd.endswith("no-board") else {"path": str(tmp_path / ".beads")}

    monkeypatch.setattr(checks, "run_json", where)
    monkeypatch.setattr(checks, "sh", lambda *args, **kw: "agent-annotate\n")
    monkeypatch.setattr(checks.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", ""))
    found, unchecked = checks.discover_boards()
    assert not unchecked and len(found) == 1
    assert found[0]["slug"] == "new" and found[0]["repo"] == str(owner)
    assert calls.count(str(owner)) == 1 and str(tmp_path / "fallback") in calls


def test_settle_survives_sessions_checkss_and_changed_fingerprint_reopens(checks, tmp_path, monkeypatch, capsys):
    b = board(tmp_path)
    monkeypatch.setattr(cli, "_resolve_slug", lambda *a: ("p", "s", b["record"]))
    monkeypatch.setattr(cli, "_session_id", lambda: "first-session")
    beads = [{"id": "agent-annotate-xyz", "status": "blocked", "notes": "BLOCKED BY: the moon"}]
    nobody = {"names": set(), "ctxs": set(), "terms": set()}

    def save(prev, now):
        f = checks.check_board(beads, 0, nobody, {}, "", now, b["prefix"])
        p, state = checks.plan(f, prev, [], 0, now)
        checks.save_followups(b, dict(f, beads=beads), p, state, now)
        return state

    state = save(None, NOW)
    first = followups.open_items(b["record"], "p", "s")[0]
    args = cli.build_parser().parse_args(["board", "p/s", "--settle", first["key"], "keep blocked", "--json"])
    assert args.func(args) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt == {"key": first["key"], "fingerprint": first["fingerprint"], "verdict": "keep blocked",
                       "session": "first-session", "at": receipt["at"]}
    assert followups.open_items(b["record"], "p", "s") == []
    state = save(state, NOW + datetime.timedelta(hours=1))
    assert followups.open_items(b["record"], "p", "s") == []
    beads[0]["notes"] = "BLOCKED BY: a changed moon"
    save(state, NOW + datetime.timedelta(hours=2))
    reopened = followups.open_items(b["record"], "p", "s")[0]
    assert reopened["key"] == first["key"] and reopened["fingerprint"] != first["fingerprint"]
    assert reopened["since"] != first["since"]
    # Disappearing evidence and a fresh session do not erase unjudged work.
    beads.clear()
    save(state, NOW + datetime.timedelta(hours=3))
    assert followups.open_items(b["record"], "p", "s") == [reopened]
    assert sorted(p.name for p in Path(b["record"]["slug_dir"]).iterdir()) == [
        "board-followups.json", "board-followups.lock", "board-verdicts.ndjson"]


def test_turn_check_dry_run_and_default_writes_readback_one_note_per_write(checks, tmp_path, monkeypatch):
    b = board(tmp_path)
    records = [{"id": "agent-annotate-go", "status": "blocked", "notes": "BLOCKED BY: agent-annotate-end"},
               {"id": "agent-annotate-end", "status": "closed"}]
    monkeypatch.setattr(checks, "discover_boards", lambda: ([b], []))
    monkeypatch.setattr(checks, "live_workers", lambda: ({}, []))
    monkeypatch.setattr(checks, "board_workers", lambda *a: ({"names": set(), "ctxs": set(), "terms": set()}, 0))
    monkeypatch.setattr(checks.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, "Human Name\n", ""))
    writes = []

    def sh(*argv, **kw):
        if argv[0] == "annotate":
            return "[]"
        if "export" in argv:
            return "\n".join(json.dumps(b) for b in records)
        if "ready" in argv:
            return "[]"
        if "show" in argv:
            return json.dumps([records[0]])
        writes.append(argv)
        if "update" in argv:
            records[0]["status"] = argv[-1]
        if "note" in argv:
            records[0]["notes"] += "\n" + argv[-1]
        return ""

    monkeypatch.setattr(checks, "sh", sh)
    result = checks.check_one(b, NOW.timestamp())
    assert result["actions"][0]["mode"] == "dry-run" and writes == []
    monkeypatch.delenv("ANNOTATE_BOARD_DRY_RUN")
    result = checks.check_one(b, (NOW + datetime.timedelta(minutes=1)).timestamp())
    assert result["actions"][0]["mode"] == "apply" and len(writes) == 2
    assert records[0]["notes"].count("SWEEP-AUTO") == 1
    actions = [json.loads(p.read_text()) for p in checks.OUT.glob("runs/*/*/actions.json")]
    assert any(a and a[0].get("readback", {}).get("ok") for a in actions)
    assert not list(tmp_path.rglob("page.db*")) and not list(tmp_path.rglob("comments.json"))


def test_board_git_user_guard_and_dynamic_prefix(checks):
    nobody = {"names": set(), "ctxs": set(), "terms": set()}
    f = checks.check_board([{"id": "rebex-a", "status": "blocked", "notes": "BLOCKED BY: rebex-b"},
                           {"id": "rebex-b", "status": "closed"},
                           {"id": "rebex-human", "status": "in_progress", "assignee": "Human Name"}],
                          0, nobody, {}, "", NOW, "rebex", {"Human Name"})
    assert f["blocked_with_closed_blocker"][0]["id"] == "rebex-a"
    assert f["in_progress_guarded"][0]["id"] == "rebex-human"
    assert f["in_progress_without_live_worker"] == []


@pytest.mark.parametrize("count", [0, 1, 5])
def test_per_turn_clause_zero_or_three_plus_more(tmp_path, count):
    b = board(tmp_path)
    seed_items(Path(b["record"]["slug_dir"]), count)
    baseline = _slug_line("p", "s", 1, [], {}, False, record={"slug_dir": "/does-not-exist"})
    actual = _slug_line("p", "s", 1, [], {}, False, record=b["record"])
    expected = followups.clause(b["record"], "p", "s")
    assert actual == baseline + expected
    assert actual.count('--settle') == min(count, 3)
    assert ("+2 more: annotate board p/s" in actual) == (count == 5)
    assert bool(expected) == bool(count)


def seed_items(directory, count):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "board-followups.json").write_text(json.dumps({"items": [
        {"key": f"sort-other:aa-{i}", "fingerprint": str(i), "line": f"aa-{i}: free-text blocker needs judgement",
         "since": "2026-11-10T06:05:00Z", "settle": f'annotate board p/s --settle sort-other:aa-{i} "verdict"'}
        for i in range(count)]}))


def test_redirect_keeps_all_followup_writes_out_of_live_page(checks, tmp_path, monkeypatch):
    b = board(tmp_path)
    live = Path(b["record"]["slug_dir"])
    (live / "comments.json").write_text("untouched")
    monkeypatch.setenv("ANNOTATE_BOARD_FOLLOWUPS_ROOT", str(tmp_path / "output"))
    checks.save_followups(b, {"beads": []}, {"needs_model": {"unsettled": [], "new_ready": []}},
                         {"flags": {}, "ready": []}, NOW)
    assert list(live.iterdir()) == [live / "comments.json"]
    assert followups.directory(b["record"], "p", "s") == tmp_path / "output/p/s"
    assert followups.open_items(b["record"], "p", "s") == []
    assert not os.path.exists(live / "board-followups.json")


def test_live_workers_uses_remote_pagination_and_three_terminal_lists(checks, monkeypatch, tmp_path):
    b = board(tmp_path)
    calls = []

    def orca(*args):
        calls.append(args)
        if args[1] == "worker-list":
            assert "--include-remote" in args
            second = "--cursor" in args
            return {"workers": [{"dispatchId": "ctx_aaaaaaaaaaaa", "agentTerminalHandle": "term-live",
                                 "runId": "run-project", "projection": {"liveness": {"verdict": "live"},
                                 "workspace": {"id": "id::" + b["repo"]}}}] if not second else [],
                    "page": {"hasMore": not second, "nextCursor": "next" if not second else None}}
        if args[0] == "terminal":
            return {"terminals": [{"handle": "term-remote", "connected": True}]}
        return {"tasks": [{"title": "GATE-RUNNER-one task"}]}

    monkeypatch.setattr(checks, "orca_json", orca)
    workers, unchecked = checks.live_workers()
    live, count = checks.board_workers(b, workers)
    assert not unchecked and count == 1
    assert live["names"] == {"GATE-RUNNER-one", "GR-one"}
    assert live["ctxs"] == {"ctx_aaaaaaaaaaaa"} and "term-remote" in live["terms"]
    terminals = [args for args in calls if args[0] == "terminal"]
    assert len(terminals) == 3
    assert terminals[1][-2:] == ("--environment", "M5Max")
    assert terminals[2][-2:] == ("--environment", "M1Max16")


def test_unchecked_liveness_never_resets_or_starts_reset_clock(checks, tmp_path, monkeypatch):
    b = board(tmp_path)
    records = [{"id": "agent-annotate-gone", "status": "in_progress", "assignee": "GONE"}]
    monkeypatch.setattr(checks, "discover_boards", lambda: ([b], []))
    monkeypatch.setattr(checks, "live_workers", lambda: ({}, [{"source": "terminal list", "reason": "unavailable"}]))
    monkeypatch.setattr(checks, "board_workers", lambda *a: ({"names": set(), "ctxs": set(), "terms": set()}, 0))
    monkeypatch.setattr(checks.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, "Human Name\n", ""))
    monkeypatch.setattr(checks, "sh", lambda *a, **kw: json.dumps(records[0]) if "export" in a else "[]")
    checks.check_one(b, NOW.timestamp())
    result = checks.check_one(b, (NOW + datetime.timedelta(hours=1)).timestamp())
    assert result["actions"] == []
    state = json.loads(next(checks.OUT.glob("*-state.json")).read_text())
    assert not any(key.startswith("reset:") for key in state["flags"])


def test_new_ready_is_durable_under_cap_and_page_handoff_carries_unjudged(checks, tmp_path):
    b = board(tmp_path)
    record = {"id": "agent-annotate-new", "status": "open", "title": "Ready"}
    state = {"flags": {}, "ready": [record["id"]]}
    planned = {"needs_model": {"unsettled": [], "new_ready": [record["id"]]}}
    first = checks.save_followups(b, {"beads": [record]}, planned, state, NOW)
    assert len(first) == 1 and first[0]["key"] == "ready:agent-annotate-new"
    previous = checks.followups_dir(b)
    b["slug"] = "successor"
    b["record"] = {"slug_dir": str(tmp_path / "successor")}
    second = checks.save_followups(b, {"beads": [record]}, {"needs_model": {"unsettled": [], "new_ready": []}},
                                  state, NOW, str(previous))
    assert second[0]["key"] == first[0]["key"] and second[0]["fingerprint"] == first[0]["fingerprint"]
    assert "annotate board p/successor" in second[0]["settle"]


def test_board_lists_one_line_and_json_has_full_records(tmp_path, monkeypatch, capsys):
    b = board(tmp_path)
    seed_items(Path(b["record"]["slug_dir"]), 5)
    monkeypatch.setattr(cli, "_resolve_slug", lambda *a: ("p", "s", b["record"]))
    monkeypatch.setattr(checks_module, "check_page", lambda *a: (None, None))
    parser = cli.build_parser()
    args = parser.parse_args(["board", "p/s"])
    assert cli.run_command(args) == 0
    output = capsys.readouterr().out
    assert len(output.splitlines()) == 1 and output.count("--settle") == 5
    args = parser.parse_args(["board", "p/s", "--json"])
    assert cli.run_command(args) == 0
    assert len(json.loads(capsys.readouterr().out)) == 5
    for key, verdict in (("missing", "no"), ("sort-other:aa-0", " ")):
        args = parser.parse_args(["board", "p/s", "--settle", key, verdict])
        assert cli.run_command(args) == 1
    assert not (Path(b["record"]["slug_dir"]) / "board-verdicts.ndjson").exists()


def test_folder_page_fallback_uses_board_root_for_fld_proof_and_latest_notes(checks, tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    repo = tmp_path / "FastLane Drive"
    (repo / ".beads").mkdir(parents=True)
    page = repo / "planning/operations/audit/page"
    page.mkdir(parents=True)
    reports = repo / "planning/operations/orchestration/run_c9d587c967ba/reports/bead-sweep"
    reports.mkdir(parents=True)
    (reports / "sweep-1.md").write_text("old")
    (reports / "sweep-12.md").write_text("latest")
    (state / "p.json").write_text(json.dumps({"slugs": {"page": {
        "owner_session": "owner", "slug_dir": str(page), "owner_target": {"worktree": "folder:id"}}}}))
    monkeypatch.setenv("ANNOTATE_STATE_DIR", str(state))
    monkeypatch.setattr(checks, "run_json", lambda *a: {"path": str(tmp_path / "central/.beads")})
    monkeypatch.setattr(checks, "sh", lambda *a, **kw: "FLD")
    monkeypatch.setattr(checks.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 1, "", ""))
    found, errors = checks.discover_boards()
    assert not errors and len(found) == 1 and found[0]["repo"] == str(repo)
    assert checks.latest_board_sweep(found[0]) == (str(reports / "sweep-12.md"), "latest")


def test_page_handoff_keeps_verdict_and_changed_evidence_reopens(checks, tmp_path):
    b = board(tmp_path)
    record = {"id": "agent-annotate-new", "status": "open", "title": "Ready"}
    state = {"flags": {}, "ready": [record["id"]]}
    planned = {"needs_model": {"unsettled": [], "new_ready": [record["id"]]}}
    first = checks.save_followups(b, {"beads": [record]}, planned, state, NOW)[0]
    previous = checks.followups_dir(b)
    (previous / "board-verdicts.ndjson").write_text(json.dumps({
        "key": first["key"], "fingerprint": first["fingerprint"], "verdict": "wait"}) + "\n")
    b["slug"] = "successor"
    b["record"] = {"slug_dir": str(tmp_path / "successor")}
    planned["needs_model"]["new_ready"] = []
    assert checks.save_followups(b, {"beads": [record]}, planned, state, NOW, str(previous)) == []
    assert followups.open_items(b["record"], "p", "successor") == []
    record["title"] = "Changed"
    second = checks.save_followups(b, {"beads": [record]}, planned, state, NOW)
    assert len(second) == 1 and second[0]["fingerprint"] != first["fingerprint"]
    assert followups.open_items(b["record"], "p", "successor") == second


def test_board_page_pin_routes_cards_and_followups_without_changing_board_repo(checks, tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    repo = tmp_path / "board-repo"
    repo.mkdir()
    audit, coordinator = repo / "audit", tmp_path / "coordinator"
    audit.mkdir()
    coordinator.mkdir()
    board_path = str(tmp_path / "central/.beads")
    entries = {"audit": {"slug_dir": str(audit), "owner_session": "audit-owner", "started_at": 2,
                         "owner_target": {"worktree": "id::" + str(repo)}},
               "coordinator": {"slug_dir": str(coordinator), "owner_session": "lead", "started_at": 1,
                               "owner_target": {"worktree": "folder:coordinator"}}}
    (state / "reviews.json").write_text(json.dumps({"project": "reviews", "slugs": entries}))
    monkeypatch.setenv("ANNOTATE_STATE_DIR", str(state))
    monkeypatch.setenv("ANNOTATE_BOARD_FOLLOWUPS_ROOT", str(tmp_path / "followups"))
    monkeypatch.setattr(checks, "run_json", lambda argv, cwd: {"path": board_path} if cwd == str(repo) else None)
    monkeypatch.setattr(checks.subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(
        argv, 0, str(repo) if "rev-parse" in argv else "Human Name", ""))
    monkeypatch.setattr(checks, "live_workers", lambda: ({"rows": [], "live": [], "names_by_run": {},
                                                        "ctxs": set(), "terms": set()}, []))
    calls = []

    def sh(*argv, **kw):
        calls.append((argv, kw))
        if argv[0] == "annotate":
            return json.dumps([{"number": 123, "verdict": "select"}])
        assert argv[:4] == ("bd", "--readonly", "-C", str(repo))
        if "config" in argv:
            return "FLD"
        if "export" in argv:
            return json.dumps({"id": "FLD-abc", "status": "blocked", "notes": "BLOCKED BY: owner card 123"})
        assert "ready" in argv
        return "[]"

    monkeypatch.setattr(checks, "sh", sh)
    found, errors = checks.discover_boards()
    assert not errors and len(found) == 1 and found[0]["slug"] == "audit"
    (state / "board-pages.txt").write_text(board_path + " reviews/coordinator\n")
    found, errors = checks.discover_boards()
    assert not errors and found[0]["slug"] == "coordinator" and found[0]["repo"] == str(repo)
    assert found[0]["record"] == entries["coordinator"]
    selected, error = checks.check_page("reviews", "audit", entries["audit"])
    assert error is None and selected["slug"] == "coordinator"
    assert (("annotate", "cards", "reviews/coordinator", "--json"), {"cwd": str(repo)}) in calls
    items = followups.open_items(entries["coordinator"], "reviews", "coordinator")
    assert items[0]["key"] == "card-answered:FLD-abc"
    assert 'annotate board reviews/coordinator --settle' in items[0]["settle"]
    assert not (tmp_path / "followups/reviews/audit/board-followups.json").exists()
    assert not list(audit.iterdir()) and not list(coordinator.iterdir())


def test_invalid_page_pin_skips_board_instead_of_using_discovery(checks, tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    (state / "p.json").write_text(json.dumps({"slugs": {"page": {
        "owner_session": "owner", "slug_dir": str(repo)}}}))
    monkeypatch.setenv("ANNOTATE_STATE_DIR", str(state))
    board_path = str(tmp_path / ".beads")
    monkeypatch.setattr(checks, "run_json", lambda *a: {"path": board_path})
    monkeypatch.setattr(checks, "sh", lambda *a, **kw: "test")
    monkeypatch.setattr(checks.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, str(repo), ""))
    (state / "board-pages.txt").write_text(board_path + " p/missing\n")
    found, errors = checks.discover_boards()
    assert found == [] and errors == ["board-pages.txt: page not owned or active: p/missing; board skipped"]


@pytest.mark.parametrize("failure", [RuntimeError("board offline"), subprocess.TimeoutExpired("bd export", 1), TypeError("invalid response")])
def test_failed_or_timed_out_check_lists_stored_items_and_receipt(checks, tmp_path, monkeypatch, capsys, failure):
    b = board(tmp_path)
    b["pages"] = ["p/s"]
    page = Path(b["record"]["slug_dir"])
    seed_items(page, 1)
    before = (page / "board-followups.json").read_bytes()
    monkeypatch.setattr(cli, "_resolve_slug", lambda *a: ("p", "s", b["record"]))
    monkeypatch.setattr(checks, "discover_boards", lambda: ([b], []))

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(checks, "sh", fail)
    args = cli.build_parser().parse_args(["board", "p/s"])
    assert cli.run_command(args) == 1
    output = capsys.readouterr()
    assert '--settle sort-other:aa-0 "verdict"' in output.out
    assert len(output.err.splitlines()) == 1 and output.err.startswith("board check failed: ")
    assert (page / "board-followups.json").read_bytes() == before
    assert any("error" in json.loads(p.read_text()) for p in checks.OUT.glob("runs/*/*/findings.json"))
    args = cli.build_parser().parse_args(["board", "p/s", "--json"])
    assert cli.run_command(args) == 1
    result = json.loads(capsys.readouterr().out)
    assert len(result["items"]) == 1 and result["error"].startswith("board check failed: ")


def test_list_checks_once_and_settle_does_not_check(tmp_path, monkeypatch, capsys):
    b = board(tmp_path)
    seed_items(Path(b["record"]["slug_dir"]), 1)
    monkeypatch.setattr(cli, "_resolve_slug", lambda *a: ("p", "s", b["record"]))
    calls = []
    monkeypatch.setattr(checks_module, "check_page", lambda *args: (calls.append(args), None))
    parser = cli.build_parser()
    assert cli.run_command(parser.parse_args(["board", "p/s"])) == 0
    assert len(calls) == 1
    assert cli.run_command(parser.parse_args(["board", "p/s", "--settle", "sort-other:aa-0", "wait"])) == 0
    assert len(calls) == 1
    assert capsys.readouterr().out.endswith("settled sort-other:aa-0\n")


def test_board_presence_reads_only_local_metadata_and_pins(tmp_path, monkeypatch):
    from agent_annotate import paths

    state = paths.STATE_DIR / "presence"
    state.mkdir(parents=True)
    monkeypatch.setattr(paths, "STATE_DIR", state)
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: pytest.fail("delivery spawned a process"))
    common = tmp_path / "repo/.git"
    linked = common / "worktrees/linked"
    linked.mkdir(parents=True)
    (linked / "commondir").write_text("../..")
    (common.parent / ".beads").mkdir()
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: " + str(linked))
    assert followups.has_board({"owner_target": {"worktree": "id::" + str(worktree)}}, "p", "linked")
    assert not followups.has_board({"slug_dir": str(tmp_path / "unknown")}, "p", "unknown")
    (state / "board-pages.txt").write_text("/central/.beads reviews/coordinator\n")
    assert followups.has_board({"slug_dir": str(tmp_path / "separate")}, "reviews", "coordinator")
    assert followups.check_clause({}, "reviews", "coordinator") == "; check the board: annotate board reviews/coordinator"
