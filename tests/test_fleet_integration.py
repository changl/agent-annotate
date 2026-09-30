import json
import stat
from types import SimpleNamespace

import pytest

from agent_annotate import cli, reports


def test_inventory_merges_explicit_remote_and_local_without_duplicate_fetches(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cli.socket, "gethostname", lambda: "M1Max.local")
    local = {"machine": "M1Max", "project": "reviews", "slug": "local", "url": "http://localhost:8800/local/"}
    remote = {"machine": "M5Max", "project": "reviews", "slug": "remote", "url": "https://host.test/remote/"}
    (tmp_path / "fleet.json").write_text(json.dumps({"schema_version": 1, "targets": [local, remote]}))
    monkeypatch.setattr(cli, "_registry_entries", lambda: [
        ("reviews", "local", {"url": local["url"]}), ("reviews", "bad", {"url": "https://secret@host.test/"}),
    ])
    import agent_annotate.fleet as fleet
    monkeypatch.setattr(fleet, "collect_fleet", lambda config: {"targets": config["targets"], "limitations": []})
    snapshot = cli._fleet_snapshot()
    assert snapshot["targets"] == [local, remote]
    assert snapshot["excluded_local_records"] == 1
    assert "observed_at" in snapshot


def test_explicit_missing_inventory_fails_without_producing_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_registry_entries", lambda: [])
    output = tmp_path / "result.json"
    assert cli.cmd_fleet(SimpleNamespace(from_file=str(tmp_path / "missing.json"), snapshot=str(output), json=True)) == 2
    assert not output.exists()


@pytest.mark.parametrize("remote", [
    {"machine": "M1Max", "project": "reviews", "slug": "local", "url": "https://wrong.test/other/"},
    {"machine": "M5Max", "project": "other", "slug": "other", "url": "http://localhost:8800/local/"},
])
def test_incompatible_inventory_merge_is_visible_failure(tmp_path, monkeypatch, remote):
    monkeypatch.setattr(cli, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cli.socket, "gethostname", lambda: "M1Max.local")
    monkeypatch.setattr(cli, "_registry_entries", lambda: [("reviews", "local", {"url": "http://localhost:8800/local/"})])
    (tmp_path / "fleet.json").write_text(json.dumps({"schema_version": 1, "targets": [remote]}))
    with pytest.raises(ValueError, match="conflicts"):
        cli._fleet_snapshot()


def test_snapshot_replacement_is_private(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_fleet_snapshot", lambda path: {"summary": {"total": 0}, "targets": []})
    output = tmp_path / "result.json"
    output.write_text("old")
    output.chmod(0o644)
    assert cli.cmd_fleet(SimpleNamespace(from_file=None, snapshot=str(output), json=True)) == 0
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text())["targets"] == []


def test_weekly_fleet_table_reports_unknowns_and_observation_limits():
    metric = {"global": {}}
    cost = {"calls": 0, "failures": 0, "rounds": 0, "output_tokens": 0, "median_round_tokens": None}
    snapshot = {
        "summary": {"total": 1, "by_machine": {"M5Max": 1}, "healthy": 0, "degraded": 1, "unreachable": 0},
        "targets": [{"machine": "M5Max", "project": "reviews", "slug": "legacy", "url": "https://host.test/legacy/",
                     "owner_present": None, "package_version": None, "latest_delivery_state": "unknown", "health": "degraded"}],
        "limitations": ["Owner metadata is not validated live ownership."],
    }
    source = reports.report_source(metric, metric, cost, "2026-09-29", snapshot)
    assert "unknown | unknown | unknown | degraded" in source
    assert "Owner metadata is not validated live ownership." in source


def test_invalid_inventory_is_visible_in_report_without_zero_claim():
    metric = {"global": {}}
    cost = {"calls": 0, "failures": 0, "rounds": 0, "output_tokens": 0, "median_round_tokens": None}
    source = reports.report_source(metric, metric, cost, "2026-09-29", {"error": "inventory_unavailable"})
    assert "missing observations are not zero activity" in source


@pytest.mark.parametrize("path,encoded", [("/plan(2026)/", "/plan%282026%29/"), ("/x|y/", "/x%7Cy/"), ("/a[b]/", "/a%5Bb%5D/")])
def test_report_links_preserve_url_delimiters_after_render(tmp_path, path, encoded):
    from agent_annotate.pagegen import generate

    metric = {"global": {}}
    cost = {"calls": 0, "failures": 0, "rounds": 0, "output_tokens": 0, "median_round_tokens": None}
    snapshot = {
        "summary": {"total": 1, "by_machine": {"M5Max": 1}, "healthy": 1, "degraded": 0, "unreachable": 0},
        "targets": [{"machine": "M5Max", "project": "reviews", "slug": "demo", "url": "https://host.test" + path,
                     "owner_present": True, "package_version": "2.20.3", "latest_delivery_state": "none", "health": "healthy"}],
        "limitations": [],
    }
    source = tmp_path / "report.md"
    source.write_text(reports.report_source(metric, metric, cost, "2026-09-29", snapshot))
    output = generate(source, tmp_path / "page")["html"].read_text()
    assert f'href="https://host.test{encoded}"' in output
