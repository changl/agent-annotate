import http.client
import json
import re

import pytest
from test_decision_api import _call, _card, _events, _store
from test_decision_api import server as server

from agent_annotate.approval_catalog import item_id


def seed(server, text="First design", version="v1", **extra):
    httpd, directory, _ = server
    (directory / "content").mkdir(exist_ok=True)
    (directory / f"content/{version}.html").write_text(
        f'<html><head></head><body><section data-anchor-id="s:design"><h2>{text}</h2>'
        '<p>Complete evidence</p></section></body></html>')
    (directory / "current.meta.json").write_text(json.dumps({"current": version, "history": [{"version": version}]}))
    status, comment = _call(httpd, "POST", "/api/comments/batch", {"idempotency": "anchor", "items": [
        {**_card("d:q1", evidence=[{"anchor": "s:design"}], **extra), "version": version, "number": 1}]})
    assert status == 200
    return _store(directory)["anchors"]["d:q1"][-1]


def token(httpd, comment, version=None):
    status, body = _call(httpd, "GET", "/content" + ("?v=" + version if version else ""))
    assert status == 200
    meta = json.loads(re.search(rb'window.__ANNOTATE_CONTENT_META__=(.*?);</script>', body)[1])
    return meta["evidence"][comment["id"]]


def vote(httpd, comment, evidence, verdict="accept", **extra):
    status, result = _call(httpd, "POST", f"/api/comments/{comment['id']}/decision",
                          {"verdict": verdict, "evidence": evidence, **extra}, author="chang@example.com")
    assert status == 200
    return result


def plans(httpd):
    return _call(httpd, "GET", "/api/categories")[1]["plans"]


@pytest.mark.parametrize("path", ["immediate", "round", "single"])
def test_all_commit_paths_file_once_and_keep_exact_displayed_version(server, path):
    httpd, directory, _ = server
    comment = seed(server)
    evidence = token(httpd, comment)
    # The author overwrites the published file while the reviewer has it open.
    (directory / "content/v1.html").write_text("<p>Changed after display</p>")
    deferred = path != "immediate"
    vote(httpd, comment, evidence, defer_push=deferred)
    if deferred:
        assert plans(httpd) == []
        route = "/api/rounds/submit" if path == "round" else f"/api/comments/{comment['id']}/push"
        for _ in range(2):
            assert _call(httpd, "POST", route, {}, author="chang@example.com")[0] == 200
    else:
        vote(httpd, comment, evidence)
    plan = plans(httpd)[0]
    assert len(plan["history"]) == 1 and plan["current"] == "v1"
    assert plan["history"][0]["evidence_incomplete"] is False
    status, html = _call(httpd, "GET", f"/plans/{plan['id']}/v1.html")
    assert status == 200 and b"First design" in html and b"Changed after display" not in html
    assert _store(directory)["anchors"]["d:q1"][0]["catalog_plan"] == plan["id"]


def test_changes_and_reject_leave_current_then_new_approval_supersedes(server):
    httpd, _, _ = server
    comment = seed(server)
    vote(httpd, comment, token(httpd, comment))
    comment = seed(server, "Second design", "v2")
    evidence = token(httpd, comment)
    for verdict in ("changes", "reject", "comment"):
        vote(httpd, comment, evidence, verdict, text="Needs work", defer_push=True)
        _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")
        assert plans(httpd)[0]["current"] == "v1"
    vote(httpd, comment, evidence, defer_push=True)
    _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")
    plan = plans(httpd)[0]
    assert plan["current"] == "v2" and len(plan["history"]) == 2
    assert "Superseded" in plan["history"][0]["label"]
    assert b"First design" in _call(httpd, "GET", f"/plans/{plan['id']}/v1.html")[1]
    assert b"Second design" in _call(httpd, "GET", f"/plans/{plan['id']}/v2.html")[1]


def test_select_files_consequence_and_incomplete_evidence_never_blocks(server):
    httpd, directory, _ = server
    comment = seed(server, options=[{"id": "later", "label": "Next month", "consequence": "Defer rollout"}])
    evidence = token(httpd, comment)
    vote(httpd, comment, evidence, "select", text="Next month", option_id="later")
    plan = plans(httpd)[0]
    assert plan["kind"] == "Decided" and plan["history"][0]["consequence"] == "Defer rollout"
    assert b"Decided: Next month" in _call(httpd, "GET", f"/plans/{plan['id']}/v1.html")[1]
    # An old client can still answer, despite lacking a displayed snapshot.
    comment = seed(server, "Second design", "v2")
    vote(httpd, comment, None)
    plan = plans(httpd)[0]
    assert plan["history"][-1]["evidence_incomplete"]
    assert b"Evidence incomplete" in _call(httpd, "GET", f"/plans/{plan['id']}/v2.html")[1]
    assert _store(directory)["anchors"]["d:q1"][-1]["decision"]["verdict"] == "accept"


def test_opt_out_discard_and_other_reviewer_submit_do_not_file(server):
    httpd, _, _ = server
    comment = seed(server, catalog=False)
    vote(httpd, comment, token(httpd, comment))
    assert plans(httpd) == []
    comment = seed(server, "New proposal", "v2")
    vote(httpd, comment, token(httpd, comment), defer_push=True)
    assert _call(httpd, "POST", "/api/rounds/submit", {}, author="other@example.com")[1]["delivery"] == "noop"
    assert _call(httpd, "POST", f"/api/comments/{comment['id']}/push", {}, author="other@example.com")[0] == 403
    _call(httpd, "POST", "/api/rounds/discard", {}, author="chang@example.com")
    _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")
    assert plans(httpd) == []


def test_crash_after_round_receipt_recovers_catalog_once(server, monkeypatch):
    httpd, directory, bus = server
    comment = seed(server)
    vote(httpd, comment, token(httpd, comment), defer_push=True)
    def fail_save(self, store):
        raise OSError("simulated crash")
    with monkeypatch.context() as patch:
        patch.setattr(httpd.RequestHandlerClass, "_v2_save", fail_save)
        with pytest.raises(http.client.RemoteDisconnected):
            _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")
    assert not _store(directory).get("approved_plans")
    assert _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")[1]["delivery"] == "noop"
    assert len(plans(httpd)[0]["history"]) == 1
    assert len(_events(bus, "session_push")) == 1


def test_token_cannot_file_another_items_evidence(server):
    httpd, directory, _ = server
    comment = seed(server)
    evidence = token(httpd, comment)
    _, other = _call(httpd, "POST", "/api/comments", _card("d:q2"))
    vote(httpd, other, evidence)
    plan = _store(directory)["approved_plans"][item_id(other)]
    assert plan["history"][0]["evidence_incomplete"]
    assert _call(httpd, "GET", "/approval-evidence/" + evidence["revision"] + "/bundle.json")[0] == 404
