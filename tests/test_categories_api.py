"""Browser contract through the real HTTP request gate and page storage."""
import http.client
import json
import uuid

from test_copy_api import _seed
from test_decision_api import _call, _card, _events, _store
from test_decision_api import server as server

from agent_annotate.categories import (
    comment_sig,
    mark_finding_fixed,
    publish_plan_revision,
    save_findings_sets,
)
from agent_annotate.copy_state import load_copy
from agent_annotate.project_state import save_project


def finding(httpd):
    body = {**_card("d:gap"), "category": "findings", "finding": {"set": "design", "title": "Gap"}}
    status, card = _call(httpd, "POST", "/api/comments", body)
    assert status == 201
    return card


def test_categories_defaults_and_legacy_documents_load_without_changes(server):
    httpd, directory, _ = server
    _seed(directory)
    save_project(directory, {"title": "Rebex", "modules": [{"id": "notes", "title": "Notes", "kind": "notes", "items": [{"text": "Existing"}]}]})
    originals = {name: (directory / name).read_bytes() for name in ("comments.json", "copy.json", "project.json")}
    status, result = _call(httpd, "GET", "/api/categories")
    assert status == 200
    assert [c["id"] for c in result["categories"] if c["available"]] == ["review", "library"]
    assert result["findings_sets"] == result["plans"] == result["linked_pages"] == []
    assert originals == {name: (directory / name).read_bytes() for name in originals}
    assert _call(httpd, "GET", "/api/project")[0] == _call(httpd, "GET", "/api/copy")[0] == 200


def test_mixed_round_sends_library_and_reopen_once_with_category_snapshots(server):
    httpd, directory, bus = server
    _seed(directory)
    card = finding(httpd)
    save_findings_sets(directory, [{"id": "design", "label": "Design"}])
    mark_finding_fixed(directory, card["id"], by="agent:builder", note="Repaired", proof=[])
    status, reopened = _call(httpd, "POST", f"/api/comments/{card['id']}/reopen", {"text": "Still wrong"}, author="chang@example.com")
    assert status == 200 and reopened["round_pending"] is True
    _, review = _call(httpd, "POST", "/api/comments", _card("d:review"))
    _call(httpd, "POST", f"/api/comments/{review['id']}/decision", {"verdict": "accept", "defer_push": True}, author="chang@example.com")
    body = {"delta": {"ops": [{"insert": "Changed\n"}]}, "base_revision": "r1", "request_id": str(uuid.uuid4())}
    assert _call(httpd, "POST", "/api/copy/hero/revisions", body, author="chang@example.com")[0] == 200
    assert _events(bus, "session_push") == []
    # Another reviewer cannot send or overwrite these drafts.
    assert _call(httpd, "POST", "/api/copy/hero/revisions", body, author="other@example.com")[0] == 403
    assert _call(httpd, "POST", f"/api/comments/{card['id']}/reopen", {"text": "Overwrite"}, author="other@example.com")[0] == 403
    other = _call(httpd, "POST", "/api/rounds/submit", {}, author="other@example.com")[1]
    assert other["delivery"] == "noop"
    result = _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")[1]
    assert result["comment_count"] == 2 and result["edit_count"] == 1
    round_record = _call(httpd, "GET", "/api/history")[1]["rounds"][0]
    assert {a["category"] for a in round_record["answers"]} == {"review", "findings"}
    assert round_record["edits"][0]["category"] == "library"
    assert round_record["edits"][0]["delta"] == body["delta"]
    assert not load_copy(directory)["blocks"][0]["revisions"][-1]["round_pending"]
    assert not _store(directory)["anchors"]["d:gap"][0].get("round_pending")
    assert _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")[1]["delivery"] == "noop"
    assert len(_events(bus, "session_push")) == 1


def test_restore_is_an_authored_pending_revision_and_retry_safe(server):
    httpd, directory, bus = server
    _seed(directory)
    body = {"revision_id": "r1", "request_id": str(uuid.uuid4())}
    for _ in range(2):
        status, result = _call(httpd, "POST", "/api/copy/hero/restore", body, author="chang@example.com")
        assert status == 200
        block = result["blocks"][0]
        assert len(block["revisions"]) == 2 and block["current"] == "r1"
        assert block["revisions"][-1]["delta"] == block["revisions"][0]["delta"]
    assert _events(bus, "session_push") == []
    assert _call(httpd, "POST", "/api/copy/hero/restore", body, author="other@example.com")[0] == 403
    assert _call(httpd, "POST", "/api/copy/hero/restore", {**body, "revision_id": "missing"}, author="chang@example.com")[0] == 404


def test_plan_document_has_adapter_and_distinct_inline_comment_address(server):
    httpd, directory, _ = server
    publish_plan_revision(directory, "shopify-plan", "<html><head></head><body><p id='s:a'>Plan one</p></body></html>", title="Shopify")
    publish_plan_revision(directory, "shopify-plan", "<html><head></head><body>Plan two</body></html>")
    assert _call(httpd, "GET", "/api/plans/shopify-plan")[1]["current"] == "v2"
    status, html = _call(httpd, "GET", "/plans/shopify-plan/v1.html")
    assert status == 200 and b"adapter.js" in html and b'"doc": "plan:shopify-plan"' in html
    assert b"Plan one" in html and b"daisyui.css" in html
    assert _call(httpd, "GET", "/plans/shopify-plan/v999.html")[0] == 404
    status, comment = _call(httpd, "POST", "/api/comments", {"anchor_id": "s:a", "text": "Plan note", "doc": "plan:shopify-plan"}, author="chang@example.com")
    assert status == 201 and comment["category"] == "plans" and comment["version"] == "v2"
    assert comment["doc"] == "plan:shopify-plan"
    assert _call(httpd, "POST", "/api/comments", {"anchor_id": "s:a", "text": "Invalid", "doc": "plan:../escape"}, author="chang@example.com")[0] == 400


def test_new_routes_refuse_traversal_and_browser_fixed_authoring(server):
    httpd, directory, _ = server
    card = finding(httpd)
    assert _call(httpd, "PUT", f"/api/comments/{card['id']}", {"fixed": {"note": "Fake"}}, author="chang@example.com")[0] == 403
    assert _call(httpd, "POST", "/api/comments", {"anchor_id": "s:a", "text": "Fake", "fixed": {}}, author="chang@example.com")[0] == 403
    assert _call(httpd, "PUT", f"/api/comments/{card['id']}", {"text": "Stolen"}, author="chang@example.com")[0] == 403
    for path in ("/api/plans/../outside", "/api/plans/%2e%2e%2foutside", "/plans/..%2foutside/v1.html"):
        assert _call(httpd, "GET", path)[0] == 400
    publish_plan_revision(directory, "safe", "<p>safe</p>")
    target = directory / "plans/safe/versions/v1.html"
    target.unlink()
    outside = directory.parent / "secret.html"
    outside.write_text("secret")
    target.symlink_to(outside)
    assert _call(httpd, "GET", "/plans/safe/v1.html")[0] == 400
    assert _call(httpd, "GET", "/attachments/..%2f..%2fsecret.html")[0] in (403, 404)


def test_new_writes_have_origin_gate_and_body_size_limits(server):
    httpd, directory, _ = server
    _seed(directory)
    for route in ("/api/copy/hero/revisions", "/api/copy/hero/restore", "/api/comments/gap/reopen", "/api/rounds/submit"):
        connection = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1])
        connection.request("POST", route, body=b"{}", headers={"Origin": "https://evil.example"})
        response = connection.getresponse()
        assert response.status == 403
        response.read()
        connection.close()
        assert _call(httpd, "POST", route, {"text": "x" * (256 * 1024)}, author="chang@example.com")[0] == 413
    assert len(load_copy(directory)["blocks"][0]["revisions"]) == 1


def test_retry_after_partial_round_clear_uses_the_saved_receipt(server, monkeypatch):
    httpd, directory, bus = server
    _seed(directory)
    card = finding(httpd)
    _call(httpd, "POST", f"/api/comments/{card['id']}/decision", {"verdict": "select", "text": "Fix", "defer_push": True}, author="chang@example.com")
    body = {"delta": {"ops": [{"insert": "Changed\n"}]}, "base_revision": "r1", "request_id": str(uuid.uuid4())}
    _call(httpd, "POST", "/api/copy/hero/revisions", body, author="chang@example.com")
    handler = httpd.RequestHandlerClass
    def fail_save(self, store):
        raise OSError("simulated crash after copy flags cleared")
    with monkeypatch.context() as patch:
        patch.setattr(handler, "_v2_save", fail_save)
        try:
            _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")
        except http.client.RemoteDisconnected:
            pass
    assert len(_events(bus, "session_push")) == 1
    assert _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")[1]["delivery"] == "noop"
    assert len(_call(httpd, "GET", "/api/history")[1]["rounds"]) == 1
    assert len(_events(bus, "session_push")) == 1


def test_linked_exception_is_project_scoped_and_registry_based(server):
    from agent_annotate.paths import STATE_DIR
    httpd, directory, _ = server
    primary = {"slug_dir": str(directory), "port": httpd.server_address[1], "url": "http://127.0.0.1:8980/", "workspace_primary": True}
    child = {"slug_dir": str(directory.parent / "lab"), "title": "Motion lab", "url": "http://127.0.0.1:8981/",
             "exception": {"reason": "Interactive worksheet", "parent_slug": "review"}}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    registry = STATE_DIR / "bus.json"
    registry.write_text(json.dumps({"project": "Rebex", "slugs": {"review": primary, "motion-lab": child}}))
    try:
        result = _call(httpd, "GET", "/api/categories")[1]
        assert result["linked_pages"] == [{"slug": "motion-lab", "title": "Motion lab", "url": child["url"], "reason": "Interactive worksheet"}]
    finally:
        registry.unlink()


def test_category_unread_uses_the_same_declared_aliases_as_read_state(server, monkeypatch):
    httpd, _, _ = server
    monkeypatch.setattr(httpd.RequestHandlerClass, "_reviewer_authors", lambda self, author: {author, "old@example.com"})
    card = finding(httpd)
    assert _call(httpd, "POST", "/api/read-state", {"items": [{"id": card["id"], "sig": comment_sig(card)}]}, author="old@example.com")[0] == 200
    categories = _call(httpd, "GET", "/api/categories", author="new@example.com")[1]["categories"]
    assert next(c for c in categories if c["id"] == "findings")["counts"]["unread"] == 0
