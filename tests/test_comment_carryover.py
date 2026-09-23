"""Prior-round comments must be dispositioned before a new version publishes.

Regression coverage for the v1 -> v2 failure reported on 2026-09-22:
``addressed`` demoted accepted cards, while old open/addressed cards followed
the reviewer onto the new document without either a resolution pointer or a
new anchor.
"""

import http.client
import http.server
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_annotate import cli
from agent_annotate.sync_server import make_handler


def _call(httpd, method, path, body=None, author="agent:test"):
    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=3)
    headers = {"Cf-Access-Authenticated-User-Email": author}
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    conn.request(method, path, body=payload, headers=headers)
    response = conn.getresponse()
    raw = response.read()
    conn.close()
    try:
        return response.status, json.loads(raw)
    except ValueError:
        return response.status, raw


@pytest.fixture
def server(tmp_path):
    slug_dir = tmp_path / "review"
    slug_dir.mkdir()
    versions = slug_dir / "versions"
    versions.mkdir()
    (versions / "v1.html").write_text(
        "<html><body><section data-anchor-id='s:old'>Old</section></body></html>",
        encoding="utf-8",
    )
    (versions / "v2.html").write_text(
        "<html><body><section data-anchor-id='s:new'>New</section></body></html>",
        encoding="utf-8",
    )
    (slug_dir / "comments.json").write_text(
        json.dumps({"schema_version": 2, "anchors": {}, "archived": {}}),
        encoding="utf-8",
    )
    (slug_dir / "current.meta.json").write_text(
        json.dumps({
            "current": "v2",
            "history": [
                {"version": "v1", "label": "round 1"},
                {"version": "v2", "label": "round 2"},
            ],
        }),
        encoding="utf-8",
    )
    bus_dir = tmp_path / "bus"
    handler = make_handler(
        artifact_dir=slug_dir,
        public_base_path="",
        slug="review",
        bus_dir=bus_dir,
        v2_mode=True,
    )
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, slug_dir, bus_dir / "review.ndjson"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)


def _create_card(httpd, status="open"):
    code, card = _call(httpd, "POST", "/api/comments", {
        "anchor_id": "s:old",
        "text": "Old question",
        "version": "v1",
        "decision_request": {"prompt": "Old question?"},
    })
    assert code == 201
    if status != "open":
        code, card = _call(
            httpd,
            "PUT",
            f"/api/comments/{card['id']}",
            {"status": status},
            author="reviewer@example.com",
        )
        assert code == 200
    return card


def test_addressed_cannot_demote_a_reviewer_confirmed_card(server):
    httpd, slug_dir, _ = server
    card = _create_card(httpd, status="user_confirmed")

    code, error = _call(
        httpd,
        "PUT",
        f"/api/comments/{card['id']}",
        {"status": "addressed_by_agent", "response_text": "Applied in v2"},
    )

    assert code == 409
    assert "cannot demote" in error["error"]
    stored = json.loads((slug_dir / "comments.json").read_text(encoding="utf-8"))
    assert stored["anchors"]["s:old"][0]["status"] == "user_confirmed"


def test_resolved_in_version_records_pointer_and_reviewer_reply_reopens(server):
    httpd, slug_dir, bus = server
    card = _create_card(httpd, status="addressed_by_agent")

    code, resolved = _call(httpd, "PUT", f"/api/comments/{card['id']}", {
        "status": "resolved_in_version",
        "resolved_in_version": "v2",
        "resolution_anchor_id": "s:new",
        "response_text": "Applied in v2 under New design.",
    })

    assert code == 200
    assert resolved["status"] == "resolved_in_version"
    assert resolved["resolved_in_version"] == "v2"
    assert resolved["resolution_anchor_id"] == "s:new"
    assert resolved["resolved_at"]
    assert resolved["resolved_by"] == "agent:test"

    events = [json.loads(line) for line in bus.read_text(encoding="utf-8").splitlines()]
    disposition = [event for event in events if event.get("event") == "comment_resolved"]
    assert disposition[-1]["comment_id"] == card["id"]
    assert disposition[-1]["resolved_in_version"] == "v2"
    assert disposition[-1]["resolution_anchor_id"] == "s:new"

    code, reopened = _call(
        httpd,
        "POST",
        f"/api/comments/{card['id']}/reply",
        {"text": "This still needs work."},
        author="reviewer@example.com",
    )
    assert code == 200
    assert reopened["status"] == "open"
    assert reopened["resolution_reopened_at"]
    assert reopened["resolved_in_version"] == "v2"  # provenance stays

    stored = json.loads((slug_dir / "comments.json").read_text(encoding="utf-8"))
    assert stored["anchors"]["s:old"][0]["status"] == "open"


def test_carry_forward_moves_card_to_new_version_and_preserves_origin(server):
    httpd, slug_dir, bus = server
    card = _create_card(httpd, status="addressed_by_agent")

    code, carried = _call(httpd, "PUT", f"/api/comments/{card['id']}", {
        "carry_forward": {"version": "v2", "anchor_id": "s:new"},
    })

    assert code == 200
    assert carried["status"] == "open"
    assert carried["version"] == "v2"
    assert carried["anchor_id"] == "s:new"
    assert carried["origin_version"] == "v1"
    assert carried["origin_anchor_id"] == "s:old"
    assert carried["carry_history"][-1]["to_version"] == "v2"
    assert carried["carry_history"][-1]["to_anchor_id"] == "s:new"

    store = json.loads((slug_dir / "comments.json").read_text(encoding="utf-8"))
    assert "s:old" not in store["anchors"]
    assert store["anchors"]["s:new"][0]["id"] == card["id"]
    events = [json.loads(line) for line in bus.read_text(encoding="utf-8").splitlines()]
    assert [event for event in events if event.get("event") == "comment_carried_forward"]


def _versioned_slug(tmp_path, status="addressed_by_agent"):
    slug_dir = tmp_path / "demo"
    versions = slug_dir / "versions"
    versions.mkdir(parents=True)
    (versions / "v1.html").write_text(
        "<html><body><section data-anchor-id='s:old'>Old</section></body></html>",
        encoding="utf-8",
    )
    (versions / "v2.html").write_text(
        "<html><body><section data-anchor-id='s:new'>New</section></body></html>",
        encoding="utf-8",
    )
    (slug_dir / "current.html").symlink_to(Path("versions") / "v1.html")
    (slug_dir / "current.meta.json").write_text(json.dumps({
        "current": "v1",
        "history": [{"version": "v1", "label": "round 1"}],
    }), encoding="utf-8")
    (slug_dir / "comments.json").write_text(json.dumps({
        "schema_version": 2,
        "anchors": {
            "s:old": [{
                "id": "aaaaaaaaaaaa",
                "anchor_id": "s:old",
                "text": "Old question",
                "status": status,
                "version": "v1",
            }],
        },
        "archived": {},
    }), encoding="utf-8")
    return slug_dir


def test_publish_version_refuses_prior_round_comment_in_limbo(tmp_path, monkeypatch, capsys):
    slug_dir = _versioned_slug(tmp_path)
    monkeypatch.setattr(cli, "BUS_ROOT", tmp_path / "bus")

    result = cli.cmd_publish_version(SimpleNamespace(
        slug_dir=str(slug_dir), version="v2", label="round 2", project=None,
    ))

    assert result == 2
    assert (slug_dir / "current.html").readlink() == Path("versions/v1.html")
    assert json.loads((slug_dir / "current.meta.json").read_text())["current"] == "v1"
    error = capsys.readouterr().err
    assert "prior-round comment" in error
    assert "aaaaaaaaaaaa" in error
    assert "annotate resolve" in error
    assert "annotate carry" in error


def test_publish_version_allows_explicit_resolution(tmp_path, monkeypatch):
    slug_dir = _versioned_slug(tmp_path, status="resolved_in_version")
    store = json.loads((slug_dir / "comments.json").read_text(encoding="utf-8"))
    comment = store["anchors"]["s:old"][0]
    comment["resolved_in_version"] = "v2"
    comment["resolution_anchor_id"] = "s:new"
    (slug_dir / "comments.json").write_text(json.dumps(store), encoding="utf-8")
    monkeypatch.setattr(cli, "BUS_ROOT", tmp_path / "bus")

    result = cli.cmd_publish_version(SimpleNamespace(
        slug_dir=str(slug_dir), version="v2", label="round 2", project=None,
    ))

    assert result == 0
    assert (slug_dir / "current.html").readlink() == Path("versions/v2.html")
    assert json.loads((slug_dir / "current.meta.json").read_text())["current"] == "v2"
