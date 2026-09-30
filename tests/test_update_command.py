from pathlib import Path
from types import SimpleNamespace

from agent_annotate import cli, deployment, updates


def test_equal_cli_version_still_activates_unmanaged_old_servers(monkeypatch):
    release={"version":cli.__version__, "html_url":"https://github.com/changl/agent-annotate/releases/tag/v"+cli.__version__}
    monkeypatch.setattr(updates,"latest_release",lambda:release)
    monkeypatch.setattr(updates,"read_enrollment",lambda:{"enabled":False})
    writes=[]
    monkeypatch.setattr(updates,"write_enrollment",lambda data:writes.append(data))
    monkeypatch.setattr(cli,"_registry_entries",lambda:[("reviews","demo",{"owner_session":"owner"})])
    monkeypatch.setattr(updates,"stage_release",lambda item:Path("/staged/python"))
    calls=[]
    monkeypatch.setattr(deployment,"activate_runtime",lambda python:calls.append(python) or {"runtime":{"build_id":"tested-build"}})
    monkeypatch.setattr(cli.subprocess,"run",lambda *a,**k:(_ for _ in ()).throw(AssertionError("runtime updates must not synchronize user-managed skills")))
    assert cli.cmd_update(SimpleNamespace(enable=False,disable=False,apply=True))==0
    assert calls==[Path("/staged/python")]
    assert writes[0]["active_build_id"]=="tested-build"


def test_already_activated_same_build_does_not_restart_pages(monkeypatch):
    monkeypatch.setattr(updates,"latest_release",lambda:{"version":cli.__version__, "html_url":"release"})
    monkeypatch.setattr(updates,"read_enrollment",lambda:{"active_version":cli.__version__,"active_build_id":"build","active_manifest":{"build_id":"build"},"active_python":"/staged/python"})
    monkeypatch.setattr(cli,"_registry_entries",lambda:[("reviews","demo",{"runtime_manifest":{"build_id":"build"},"runtime_python":"/staged/python"})])
    monkeypatch.setattr(updates,"stage_release",lambda _:(_ for _ in ()).throw(AssertionError("should skip")))
    assert cli.cmd_update(SimpleNamespace(enable=False,disable=False,apply=True))==0
