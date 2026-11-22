import pytest


@pytest.fixture(autouse=True)
def _no_live_publications(monkeypatch, tmp_path_factory):
    """The kept documents' own note stores (proto_data.published) are live pages: a test reads its own copies only, and the
    prototype's saves are allowed under the test's sandbox (published.guard)."""
    from agent_annotate.proto_data import links
    gone = tmp_path_factory.mktemp("no-publication")
    monkeypatch.setattr(links, "MEETING", gone / "meeting")
    monkeypatch.setattr(links, "USAGE_AUDIT", gone / "usage" / "current.html")
    monkeypatch.setenv("ANNOTATE_PROTO_ROOT", str(tmp_path_factory.getbasetemp()))
