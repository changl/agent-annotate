"""Publishing to a page whose owner has gone makes the publisher the owner.

Chang, 2026-10-31: three Sends on the Agent Annotate page waited for an owner
session that had ended on Oct 21, while another session published to it.
"""

from types import SimpleNamespace

import pytest

from agent_annotate import cli, delivery


@pytest.fixture
def publish(monkeypatch, tmp_path):
    record = {"slug_dir": str(tmp_path), "pid": 1, "owner_session": "gone", "owner_target": {"handle": "old"}}
    claims = []
    monkeypatch.setattr(cli, "_project_config", lambda project: {})
    monkeypatch.setattr(cli, "_session_id", lambda: "me")
    monkeypatch.setattr(cli, "_session_agent", lambda: "claude")
    monkeypatch.setattr(cli, "_load_state_for_project", lambda project: {"slugs": {"page": record}})
    monkeypatch.setattr(cli, "_run_gate", lambda record, args: None)
    monkeypatch.setattr(cli, "_print_publish", lambda *args, **kwargs: 0)
    monkeypatch.setattr(cli, "cmd_claim", lambda args: claims.append(args.slug) or 0)
    monkeypatch.setattr(delivery, "capture_target", lambda session, agent: {"handle": "mine"})

    def run(owner_alive):
        monkeypatch.setattr(delivery, "_target_ready", lambda target: (owner_alive, ""))
        claims.clear()
        cli._publish_already_running("reviews", "page", tmp_path, dict(record), SimpleNamespace(transport=None))
        return claims
    return run


def test_a_gone_owner_is_replaced_by_the_publisher(publish):
    assert publish(owner_alive=False) == ["reviews/page"]


def test_a_live_owner_keeps_the_page(publish):
    assert publish(owner_alive=True) == []
