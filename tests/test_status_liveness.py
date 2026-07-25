"""`annotate status` must not call a serving page dead.

A server restarted outside the CLI keeps its original pid in the state file
forever. Trusting that pid made live pages report as dead, which sent people
chasing an ingress problem that did not exist. Status now falls back to
locating the process by slug_dir.
"""

import json

import pytest

from agent_annotate import cli


class _Args:
    slug = None


def _write_state(tmp_path, monkeypatch, rec):
    state_file = tmp_path / "docs.json"
    state_file.write_text(json.dumps({"project": "docs", "slugs": {"demo": rec}}))
    monkeypatch.setattr(cli, "_all_state_files", lambda: [state_file])
    return state_file


@pytest.fixture
def base_record(tmp_path):
    slug_dir = tmp_path / "demo"
    slug_dir.mkdir()
    return {
        "slug": "demo",
        "slug_dir": str(slug_dir),
        "pid": 999999,          # long gone
        "port": 8800,
        "url": "http://localhost:8800/",
    }


def test_stale_pid_with_live_process_reports_alive(tmp_path, monkeypatch, capsys, base_record):
    _write_state(tmp_path, monkeypatch, base_record)
    monkeypatch.setattr(cli, "_is_process_alive", lambda pid: False)
    monkeypatch.setattr(
        cli, "_running_servers",
        lambda: {str(tmp_path / "demo"): [{"pid": 4242, "port": 8809}]},
    )

    assert cli.cmd_status(_Args()) == 0
    out = capsys.readouterr().out
    assert "alive*" in out
    # The real pid and port are surfaced, not the stale ones.
    assert "4242" in out
    assert "8809" in out
    assert "stale" in out


def test_no_live_process_still_reports_dead(tmp_path, monkeypatch, capsys, base_record):
    _write_state(tmp_path, monkeypatch, base_record)
    monkeypatch.setattr(cli, "_is_process_alive", lambda pid: False)
    monkeypatch.setattr(cli, "_running_servers", lambda: {})

    assert cli.cmd_status(_Args()) == 0
    out = capsys.readouterr().out
    assert "dead" in out
    assert "alive" not in out


def test_duplicate_servers_for_one_slug_are_flagged(tmp_path, monkeypatch, capsys, base_record):
    """Two servers on one slug_dir fight over comments.json — say so."""
    _write_state(tmp_path, monkeypatch, base_record)
    monkeypatch.setattr(cli, "_is_process_alive", lambda pid: False)
    monkeypatch.setattr(
        cli, "_running_servers",
        lambda: {str(tmp_path / "demo"): [{"pid": 1, "port": 8800}, {"pid": 2, "port": 8809}]},
    )

    assert cli.cmd_status(_Args()) == 0
    out = capsys.readouterr().out
    assert "dup" in out
    assert "comments.json" in out


def test_live_recorded_pid_needs_no_fallback(tmp_path, monkeypatch, capsys, base_record):
    _write_state(tmp_path, monkeypatch, base_record)
    monkeypatch.setattr(cli, "_is_process_alive", lambda pid: True)

    def _boom():
        raise AssertionError("must not probe when the recorded pid is alive")

    monkeypatch.setattr(cli, "_running_servers", _boom)
    # _running_servers is called once up front; make it cheap but assert the
    # recorded-pid path still wins.
    monkeypatch.setattr(cli, "_running_servers", lambda: {})
    assert cli.cmd_status(_Args()) == 0
    out = capsys.readouterr().out
    assert "alive" in out
    assert "alive*" not in out
