import pytest

from agent_annotate.transports.cloudflare import _auth


def test_cloudflare_auth_uses_portable_environment(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "account")
    monkeypatch.setenv("ANNOTATE_CLOUDFLARE_TUNNEL_ID", "tunnel")
    monkeypatch.setenv("ANNOTATE_CLOUDFLARE_HOSTNAME", "reviews.example.com")

    assert _auth({}) == ("account", "tunnel", "reviews.example.com", "token")


def test_cloudflare_auth_has_no_embedded_project_defaults(monkeypatch):
    for name in (
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "ANNOTATE_CLOUDFLARE_TUNNEL_ID",
        "ANNOTATE_CLOUDFLARE_HOSTNAME",
        "ANNOTATE_CLOUDFLARE_ENV_FILE",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="CLOUDFLARE_API_TOKEN"):
        _auth({})
