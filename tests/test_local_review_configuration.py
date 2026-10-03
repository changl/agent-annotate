from types import SimpleNamespace

import pytest

from agent_annotate import cli


def test_explicit_local_reviewer_config_reaches_server_and_not_transport(tmp_path, monkeypatch):
    config = {"local_author": "reviewer@example.test", "local_author_name": "Local Reviewer", "transport": "local"}
    monkeypatch.setattr(cli, "_load_projects_toml", lambda: {"reviews": config})
    monkeypatch.setattr(cli, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(cli.time, "sleep", lambda *args: None)
    calls = []
    monkeypatch.setattr(cli.subprocess, "Popen", lambda args, **kwargs: calls.append(args) or SimpleNamespace(pid=1234))
    assert cli._start_server(tmp_path / "page", 8800, tmp_path / "bus/reviews", None) == 1234
    assert calls[0][calls[0].index("--local-author") + 1] == "reviewer@example.test"
    assert calls[0][calls[0].index("--local-author-name") + 1] == "Local Reviewer"
    assert cli._transport_opts(config) == {}


@pytest.mark.parametrize("config", [{"local_author": "bad\nidentity"}, {"local_author_name": "name-only"}, {"local_author": True}])
def test_bad_local_identity_fails_before_any_server_or_log_creation(tmp_path, monkeypatch, config):
    monkeypatch.setattr(cli, "_load_projects_toml", lambda: {"reviews": config})
    monkeypatch.setattr(cli, "LOG_DIR", tmp_path / "logs")
    with pytest.raises(ValueError):
        cli._start_server(tmp_path / "page", 8800, tmp_path / "bus/reviews", None)
    assert not (tmp_path / "logs").exists()
