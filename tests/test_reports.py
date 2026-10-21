import datetime as dt
import html
from types import SimpleNamespace

import pytest

from agent_annotate import cli, reports
from agent_annotate.metrics import collect_metrics
from agent_annotate.pagegen import generate


def test_report_keeps_project_owner_when_stopped(tmp_path, monkeypatch):
    directory = tmp_path / "weekly"
    directory.mkdir()
    record = {"slug_dir":str(directory),"pid":100,"owner_session":"owner","owner_target":{"handle":"current-owner"}}
    monkeypatch.setattr(cli,"_load_state_for_project",lambda project:{"slugs":{"weekly":record}})
    monkeypatch.setattr(reports,"write_report",lambda path:{"version":"v2","label":"week"})
    monkeypatch.setattr(cli,"_carryover_blockers",lambda *args:[])
    monkeypatch.setattr(cli,"cmd_publish_version",lambda args:0)
    monkeypatch.setattr(cli,"_is_process_alive",lambda pid:False)
    monkeypatch.setattr(cli,"_running_servers",lambda:{})
    monkeypatch.setattr(cli,"_live_tailnet_host",lambda:None)
    monkeypatch.setattr(cli,"_revive_one",lambda *args:("revived","same owner"))
    verified=[]
    monkeypatch.setattr(cli,"_publish_already_running",lambda *args:verified.append(args[3]) or 0)
    monkeypatch.setattr(cli,"cmd_publish",lambda args:(_ for _ in ()).throw(AssertionError("must not reclaim owner")))
    assert reports.cmd_report(SimpleNamespace(slug_dir=str(directory),project="reviews",install=False,publish=True))==0
    assert verified[0]["owner_session"]=="owner"
    assert verified[0]["owner_target"]=={"handle":"current-owner"}


def test_report_does_not_touch_another_directory_with_same_slug(tmp_path, monkeypatch):
    directory=tmp_path/"mine"/"weekly"
    monkeypatch.setattr(cli,"_load_state_for_project",lambda p:{"slugs":{"weekly":{"slug_dir":str(tmp_path/"other"/"weekly")}}})
    monkeypatch.setattr(reports,"write_report",lambda path:(_ for _ in ()).throw(AssertionError("must not generate")))
    assert reports.cmd_report(SimpleNamespace(slug_dir=str(directory),project="reviews",install=False,publish=True))==1
    assert not directory.exists()


def test_report_generation_is_managed_and_does_not_read_inbox(tmp_path, monkeypatch):
    now=dt.datetime(2026,9,30,tzinfo=dt.UTC)
    monkeypatch.setattr(reports.costs,"collect",lambda args:[])
    monkeypatch.setattr(cli,"cmd_inbox",lambda args:(_ for _ in ()).throw(AssertionError("no inbox reads")))
    import agent_annotate.metrics as metrics
    monkeypatch.setattr(metrics,"collect_metrics",lambda start,end:collect_metrics(start,end,tmp_path/"state",tmp_path/"bus"))
    result=reports.write_report(tmp_path/"weekly",now)
    assert result["version"]=="v1"
    assert "Feedback delivery" in result["html"].read_text()
    assert not (tmp_path/"state").exists()
    assert (tmp_path/"weekly"/"metrics.json").is_file()


def test_first_report_uses_complete_publish_options(tmp_path, monkeypatch):
    directory=tmp_path/"weekly"
    monkeypatch.setattr(cli,"_load_state_for_project",lambda project:{"slugs":{}})
    monkeypatch.setattr(reports,"write_report",lambda path:{"version":"v1","label":"week"})
    captured=[]
    monkeypatch.setattr(cli,"cmd_publish",lambda args:captured.append(args) or 0)
    assert reports.cmd_report(SimpleNamespace(slug_dir=str(directory),project="reviews",install=False,publish=True))==0
    assert captured[0].transport is None
    assert captured[0].path_prefix is None
    assert captured[0].verify_timeout==45.0


@pytest.mark.parametrize("name", ["Operations | Q1 [approved]", "团队 🐳 &amp; [Q1]",
                                  "Operations](https://unconfigured.test/) | [remainder"])
def test_fleet_report_renders_plain_page_names_without_breaking_links_or_columns(tmp_path, name):
    metrics = {"global": {}}
    cost = {"calls": 0, "failures": 0, "rounds": 0, "output_tokens": 0, "median_round_tokens": None}
    fleet = {"summary": {"total": 1, "by_machine": {"mbp": 1}, "healthy": 1, "degraded": 0, "unreachable": 0},
             "targets": [{"machine": "mbp", "name": name, "url": "https://example.test/operations/",
                          "owner_present": True, "package_version": "2.21.0", "latest_delivery_state": "none",
                          "health": "healthy"}], "limitations": []}
    source = tmp_path / "report.md"
    source.write_text(reports.report_source(metrics, metrics, cost, "2026-10-20", fleet))
    result = generate(source, tmp_path / "report")
    rendered = result["html"].read_text()
    assert f'<a href="https://example.test/operations/">{html.escape(name)}</a>' in rendered
    assert '<a href="https://unconfigured.test/">' not in rendered
