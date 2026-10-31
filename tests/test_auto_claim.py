"""Publishing to a page whose owner has gone makes the publisher the owner.

Chang, 2026-10-31: three Sends on the Agent Annotate page waited for an owner
session that had ended on Oct 21, while another session published to it.
"""

from types import SimpleNamespace

import pytest

from agent_annotate import cli, delivery


@pytest.fixture
def publish(monkeypatch, tmp_path):
    record = {"slug_dir": str(tmp_path), "pid": 1, "owner_session": "gone",
              "owner_target": {"handle": "old", "pid": 123, "process_start": "original"}}
    claims = []
    monkeypatch.setattr(cli, "_project_config", lambda project: {})
    monkeypatch.setattr(cli, "_session_id", lambda: "me")
    monkeypatch.setattr(cli, "_session_agent", lambda: "claude")
    monkeypatch.setattr(cli, "_load_state_for_project", lambda project: {"slugs": {"page": record}})
    monkeypatch.setattr(cli, "_run_gate", lambda record, args: None)
    monkeypatch.setattr(cli, "_print_publish", lambda *args, **kwargs: 0)
    monkeypatch.setattr(cli, "cmd_claim", lambda args: claims.append(args.slug) or 0)
    def run(process=("original", "claude"), error=None, target=record["owner_target"], publisher=True,
            process_error=None):
        def kill(pid, signal):
            assert (pid, signal) == (123, 0)
            if error:
                raise error
        monkeypatch.setattr(delivery.os, "kill", kill)
        def inspect(pid):
            if process_error:
                raise process_error
            return process
        monkeypatch.setattr(delivery, "_process", inspect)
        monkeypatch.setattr(delivery, "capture_target", lambda *args: {"handle": "mine"} if publisher else None)
        record["owner_target"] = target
        claims.clear()
        cli._publish_already_running("reviews", "page", tmp_path, dict(record), SimpleNamespace(transport=None))
        return claims
    return run


def test_a_provably_dead_owner_is_replaced_by_the_publisher(publish):
    assert publish(error=ProcessLookupError()) == ["reviews/page"]


def test_a_reused_pid_is_replaced_by_the_publisher(publish):
    assert publish(process=("different", "claude")) == ["reviews/page"]


def test_a_live_owner_keeps_the_page(publish):
    assert publish() == []


@pytest.mark.parametrize("kwargs", [
    {"target": None}, {"target": {"handle": "old"}},
    {"target": {"pid": 0}}, {"target": {"pid": "invalid"}}, {"target": {"pid": None}},
    {"process": None}, {"error": PermissionError()}, {"error": OSError()},
    {"process_error": ProcessLookupError()},
    {"target": {"pid": 123}, "process": ("different", "claude")},
    {"error": ProcessLookupError(), "publisher": False},
])
def test_an_unknown_owner_or_unbound_publisher_keeps_the_owner(publish, kwargs):
    assert publish(**kwargs) == []
