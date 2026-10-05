import copy
import http.client
import http.server
import json
import threading
import uuid
from types import SimpleNamespace

import pytest

from agent_annotate import cli, delivery, project_state, review_access, sync_server
from agent_annotate.pagegen import generate
from agent_annotate.urls import page_url


@pytest.fixture
def reviewer_page(tmp_path, monkeypatch):
    directory = tmp_path / "page"
    source = tmp_path / "page.md"
    source.write_text("## Progress\n\nKeep the existing review history.\n")
    generate(source, directory)
    card = {"id": "agent-card", "anchor_id": "d:q1", "number": 1, "text": "Original owner question",
            "author": "agent:owner", "version": "v1", "status": "open",
            "decision_request": {"prompt": "Original owner question", "options": ["accept", "reject"]},
            "decision": {"verdict": "accept", "text": "Original rationale", "by": "prior-reviewer", "ts": "2026-01-01T00:00:00Z"},
            "decision_history": [{"verdict": "reject", "text": "Older rationale", "by": "prior-reviewer"}],
            "replies": [{"author": "prior-reviewer", "text": "Original explanation", "ts": "2026-01-01T00:00:00Z"}]}
    store = {"schema_version": 2, "anchors": {"d:q1": [card], "s:progress:p1": [
        {"id": "original-comment", "anchor_id": "s:progress:p1", "text": "Original user feedback",
         "author": "prior-reviewer", "version": "v1", "status": "open", "replies": []}]},
        "archived": {"old": [{"id": "archived-comment", "text": "Keep archived feedback"}]}}
    (directory / "comments.json").write_text(json.dumps(store))
    (directory / "project.json").write_text('{"schema_version":1,"title":"Original project","modules":[]}')
    key = review_access.ensure_key(directory)
    project = "reviewer-boundary-" + uuid.uuid4().hex[:8]
    bus = cli.BUS_ROOT / project
    bus.mkdir(parents=True, exist_ok=True)
    handler = sync_server.make_handler(directory, bus_dir=bus, slug="page", public_base_path="/page",
                                       v2_mode=True, skill_dir=sync_server.WEB_DIR)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    cli._save_state_for_project(project, {"project": project, "slugs": {"page": {
        "slug_dir": str(directory), "port": server.server_port, "transport": "funnel",
        "url": "https://host.ts.net/page/", "owner_target": None}}})
    monkeypatch.setattr(delivery, "dispatch_record", lambda *args, **kwargs: None)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def call(method, route, payload=None, *, public=True, cookie=None, headers=None, browser=True):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
        values = {"Host": "host.ts.net"} if public else {"X-Annotate-Agent": "agent:owner"}
        if browser:
            values.update(Origin="https://host.ts.net" if public else f"http://127.0.0.1:{server.server_port}",
                          **{"Sec-Fetch-Site": "same-origin"})
        if cookie:
            values["Cookie"] = cookie
        values.update(headers or {})
        body = json.dumps(payload).encode() if payload is not None else None
        if body is not None:
            values["Content-Type"] = "application/json"
        connection.request(method, "/page/" + route, body=body, headers=values)
        response = connection.getresponse()
        status, response_headers, raw = response.status, dict(response.getheaders()), response.read()
        connection.close()
        try:
            result = json.loads(raw)
        except ValueError:
            result = raw.decode()
        return status, response_headers, result

    status, headers, _ = call("POST", "api/reviewer/session", {"key": key, "name": "External reviewer"})
    assert status == 200
    cookie = headers["Set-Cookie"].split(";", 1)[0]
    identity = review_access.identity(directory, cookie)[0]
    try:
        yield SimpleNamespace(directory=directory, call=call, cookie=cookie, identity=identity,
                              original=copy.deepcopy(store), bus=bus / "page.ndjson")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.parametrize("payload", [{"schema_version": 2, "anchors": {}, "archived": {}}, {}, {"s:new": []}])
@pytest.mark.parametrize("browser", [True, False])
def test_public_reviewer_cannot_replace_store_and_history_is_byte_identical(reviewer_page, payload, browser):
    page = reviewer_page
    before = (page.directory / "comments.json").read_bytes()
    status, _, result = page.call("POST", "api/comments", payload, cookie=page.cookie, browser=browser)
    assert status == 403, result
    assert (page.directory / "comments.json").read_bytes() == before
    assert not page.bus.exists() or "bulk_overwrite" not in page.bus.read_text()


def test_local_non_browser_import_remains_usable(reviewer_page):
    page = reviewer_page
    payload = {"schema_version": 2, "anchors": {}, "archived": {}}
    status, _, result = page.call("POST", "api/comments", payload, public=False, browser=False)
    assert status == 200 and result["mode"] == "bulk"
    assert json.loads((page.directory / "comments.json").read_text()) == payload


def test_public_create_reply_verdict_revision_free_text_and_round_preserve_history(reviewer_page):
    page = reviewer_page
    spoof = {"author": "agent:spoof", "author_email": "spoof@example.invalid", "author_name": "Spoofed owner"}
    status, _, created = page.call("POST", "api/comments", {
        "anchor_id": "s:progress:p1", "text": "Useful new feedback", "version": "v1", **spoof}, cookie=page.cookie,
        headers={"X-Annotate-Agent": "agent:spoof"})
    assert status == 201 and created["author"] == page.identity and created["author_name"] == "External reviewer"
    status, _, edited = page.call("PUT", "api/comments/" + created["id"], {
        "text": "Clarified useful feedback"}, cookie=page.cookie)
    assert status == 200 and edited["text"] == "Clarified useful feedback" and edited["author"] == page.identity
    status, _, reply = page.call("POST", "api/comments/agent-card/reply", {"text": "Reviewer explanation", **spoof}, cookie=page.cookie)
    assert status == 200 and reply["replies"][-1]["author"] == page.identity
    status, _, rejected = page.call("POST", "api/comments/agent-card/decision", {
        "verdict": "reject", "text": "Changed my mind: this is the explanation", "defer_push": True, **spoof}, cookie=page.cookie)
    assert status == 200 and rejected["decision"]["by"] == page.identity
    status, _, answered = page.call("POST", "api/comments/agent-card/decision", {
        "verdict": "comment", "text": "Answer in words after changing the verdict", "defer_push": True, **spoof}, cookie=page.cookie)
    assert status == 200 and answered["decision"]["text"] == "Answer in words after changing the verdict"
    status, _, submitted = page.call("POST", "api/rounds/submit", {"note": "Completed external review"}, cookie=page.cookie)
    assert status == 200 and submitted["comment_count"] == 1 and submitted["comment_ids"] == ["agent-card"]
    store = json.loads((page.directory / "comments.json").read_text())
    card = store["anchors"]["d:q1"][0]
    assert card["text"] == "Original owner question" and card["decision_request"]["prompt"] == "Original owner question"
    assert [entry["verdict"] for entry in card["decision_history"]] == ["reject", "accept", "reject"]
    assert card["replies"][0]["text"] == "Original explanation"
    assert "round_pending" not in card["decision"] and card["flagged_by"] == page.identity
    assert store["archived"] == page.original["archived"]


def test_public_project_authoring_has_no_mutation_endpoint(reviewer_page):
    page = reviewer_page
    before = (page.directory / "project.json").read_bytes()
    for method in ("POST", "PUT"):
        status, _, _ = page.call(method, "api/project", {"schema_version": 1, "title": "Overwrite", "modules": []}, cookie=page.cookie)
        assert status == 404
    assert (page.directory / "project.json").read_bytes() == before


def test_public_batch_cannot_impersonate_agent_or_idempotently_repose_agent_card(reviewer_page):
    page = reviewer_page
    before = copy.deepcopy(page.original["anchors"]["d:q1"][0])
    status, _, result = page.call("POST", "api/comments/batch", {"idempotency": "anchor", "items": [{
        "anchor_id": "d:q1", "number": 1, "text": "Try to re-pose the owner's question", "author": "agent:owner",
        "decision_request": {"prompt": "A replacement question", "options": ["accept", "reject"]}}]}, cookie=page.cookie)
    store = json.loads((page.directory / "comments.json").read_text())
    assert store["anchors"]["d:q1"][0] == before
    if status != 403:
        assert status == 200 and result["updated"] == 0 and result["created"] == 1
        assert store["anchors"]["d:q1"][1]["author"] == page.identity


@pytest.mark.parametrize("payload", [
    {"text": "Replacement invented question", "decision_request": None},
    {"text": "Replacement invented question"},
    {"decision_request": None},
])
def test_public_reviewer_cannot_erase_existing_agent_question_context(reviewer_page, payload):
    page = reviewer_page
    before = (page.directory / "comments.json").read_bytes()
    status, _, result = page.call("PUT", "api/comments/agent-card", payload, cookie=page.cookie)
    assert status == 403, result
    assert (page.directory / "comments.json").read_bytes() == before


def test_project_get_grants_only_transient_bounded_child_links_without_persisting_keys(reviewer_page):
    page = reviewer_page
    project = page.bus.parent.name
    scope = "git:example/" + project
    state = cli._load_state_for_project(project)
    primary = state["slugs"]["page"]
    primary.update(workspace_primary=True, workspace_key=scope, workspace_root=str(page.directory))
    keys, urls = {}, {}
    for name, directory, standalone, workspace_key in [
        ("child", page.directory / "child", False, scope),
        ("foreign", page.directory.parent / "foreign", False, "git:example/foreign-project"),
        ("worksheet", page.directory / "worksheet", True, scope),
    ]:
        generate(page.directory.parent / "page.md", directory)
        keys[name] = review_access.ensure_key(directory)
        urls[name] = f"https://host.ts.net/{project}-{name}/"
        state["slugs"][name] = {"slug_dir": str(directory), "port": 18000 + len(urls),
            "transport": "funnel", "url": urls[name], "workspace_key": workspace_key, "standalone": standalone}
    cli._save_state_for_project(project, state)
    project_state.save_project(page.directory, {"schema_version": 1, "modules": [], "tabs": [
        {"id": name, "label": name, "url": url} for name, url in urls.items()]})
    before = (page.directory / "project.json").read_bytes()
    status, _, _ = page.call("GET", "api/project")
    assert status == 403
    status, headers, data = page.call("GET", "api/project", cookie=page.cookie)
    assert status == 200 and headers["Cache-Control"] == "no-store"
    returned = {tab["id"]: tab["url"] for tab in data["tabs"]}
    assert returned["child"] == page_url(state["slugs"]["child"])
    assert returned["foreign"] == urls["foreign"] and returned["worksheet"] == urls["worksheet"]
    assert keys["child"] in json.dumps(data)
    assert keys["foreign"] not in json.dumps(data) and keys["worksheet"] not in json.dumps(data)
    assert (page.directory / "project.json").read_bytes() == before
    assert all(key.encode() not in before for key in keys.values())


@pytest.mark.parametrize("operation", ["submit", "discard"])
def test_review_round_handles_only_callers_drafts_and_preserves_other_reviewers(reviewer_page, operation):
    page = reviewer_page
    status, headers, _ = page.call("POST", "api/reviewer/session", {
        "key": review_access.read_key(page.directory), "name": "Second external reviewer"})
    assert status == 200
    other_cookie = headers["Set-Cookie"].split(";", 1)[0]
    other_identity = review_access.identity(page.directory, other_cookie)[0]
    assert other_identity != page.identity
    store = json.loads((page.directory / "comments.json").read_text())
    second = copy.deepcopy(store["anchors"]["d:q1"][0])
    second.update(id="second-agent-card", anchor_id="d:q2", number=2, text="Another owner question")
    second["decision_request"]["prompt"] = "Another owner question"
    store["anchors"]["d:q2"] = [second]
    (page.directory / "comments.json").write_text(json.dumps(store))
    status, _, _ = page.call("POST", "api/comments/agent-card/decision", {
        "verdict": "reject", "text": "My unfinished first-reviewer draft", "defer_push": True}, cookie=page.cookie)
    assert status == 200
    status, _, _ = page.call("POST", "api/comments/second-agent-card/decision", {
        "verdict": "accept", "text": "Second reviewer's answer", "defer_push": True}, cookie=other_cookie)
    assert status == 200
    before = json.loads((page.directory / "comments.json").read_text())["anchors"]["d:q1"][0]
    assert before["decision"]["round_pending"] and before["decision"]["by"] == page.identity
    status, _, result = page.call("POST", "api/rounds/" + operation, {}, cookie=other_cookie)
    assert status == 200
    after = json.loads((page.directory / "comments.json").read_text())
    assert after["anchors"]["d:q1"][0] == before, result
    assert result["comment_count"] == 1 and result["comment_ids"] == ["second-agent-card"]
    assert "round_pending" not in after["anchors"]["d:q2"][0]["decision"]
    if page.bus.exists():
        events = [json.loads(line) for line in page.bus.read_text().splitlines()]
        for event in events:
            if event.get("event") in ("round_submitted", "round_discarded", "session_push"):
                assert "agent-card" not in event.get("comment_ids", [])


@pytest.mark.parametrize("operation", ["submit", "discard"])
def test_declared_account_alias_can_finish_legacy_drafts_without_relabeling_or_foreign_grants(
        reviewer_page, monkeypatch, operation):
    page = reviewer_page
    project = page.bus.parent.name
    current_author, legacy_author = "current@example.invalid", "legacy@example.invalid"
    config = page.directory.parent / "projects.toml"
    config.write_text(f'[{project}.reviewer_aliases]\n"{current_author}" = ["{legacy_author}"]\n')
    monkeypatch.setattr(sync_server, "PROJECTS_TOML", config)
    store = json.loads((page.directory / "comments.json").read_text())
    legacy = store["anchors"]["d:q1"][0]
    legacy["decision"].update(by=legacy_author, round_pending=True, text="Saved legacy explanation")
    foreign = copy.deepcopy(legacy)
    foreign.update(id="foreign-card", anchor_id="d:q2", number=2)
    foreign["decision"]["by"] = "other-reviewer@example.invalid"
    store["anchors"]["d:q2"] = [foreign]
    (page.directory / "comments.json").write_text(json.dumps(store))
    before = (page.directory / "comments.json").read_bytes()
    status, guest_headers, _ = page.call("POST", "api/reviewer/session", {
        "key": review_access.read_key(page.directory), "name": current_author})
    assert status == 200
    guest_cookie = guest_headers["Set-Cookie"].split(";", 1)[0]
    guest_author = review_access.identity(page.directory, guest_cookie)[0]
    status, _, guest = page.call("GET", "api/identity", cookie=guest_cookie)
    assert status == 200 and guest["name"] == current_author and guest["reviewer_authors"] == [guest_author]
    status, _, denied = page.call("POST", "api/rounds/" + operation, {}, cookie=guest_cookie)
    assert status == 200 and denied["comment_count"] == 0 and denied["comment_ids"] == []
    assert (page.directory / "comments.json").read_bytes() == before
    trusted_proxy = {"Tailscale-User-Login": current_author, "Tailscale-User-Name": "Actual account"}
    status, _, owner = page.call("GET", "api/identity", headers=trusted_proxy)
    assert status == 200 and set(owner["reviewer_authors"]) == {current_author, legacy_author}
    assert (page.directory / "comments.json").read_bytes() == before
    status, _, completed = page.call("POST", "api/rounds/" + operation, {}, headers=trusted_proxy)
    assert status == 200 and completed["comment_count"] == 1 and completed["comment_ids"] == ["agent-card"]
    after = json.loads((page.directory / "comments.json").read_text())
    card = after["anchors"]["d:q1"][0]
    if operation == "discard" and legacy["decision_history"]:
        # UI-14: a discarded change puts the sent answer back; the draft stays
        # in the history under its own author, never relabeled.
        assert card["decision"] == legacy["decision_history"][-1]
        draft = card["decision_history"][-1]
        assert draft["by"] == legacy_author and draft["text"] == "Saved legacy explanation" and draft["discarded"]
        assert "round_pending" not in draft
        assert card["decision_history"][:-1] == legacy["decision_history"][:-1] and card["replies"] == legacy["replies"]
    else:
        assert card["decision"]["by"] == legacy_author and card["decision"]["text"] == "Saved legacy explanation"
        assert "round_pending" not in card["decision"]
        assert card["decision_history"] == legacy["decision_history"] and card["replies"] == legacy["replies"]
    assert after["anchors"]["d:q2"][0] == foreign


@pytest.mark.parametrize("filename,route,field,signature", [
    ("seen.json", "api/seen", "seen", "whole_hash"),
    ("read-state.json", "api/read-state", "read", "sig"),
])
def test_alias_read_bookkeeping_merges_latest_items_without_writes_or_foreign_state(
        reviewer_page, monkeypatch, filename, route, field, signature):
    page = reviewer_page
    current, legacy = "current@example.invalid", "legacy@example.invalid"
    config = page.directory.parent / "projects.toml"
    config.write_text(f'[{page.bus.parent.name}.reviewer_aliases]\n"{current}" = ["{legacy}"]\n')
    monkeypatch.setattr(sync_server, "PROJECTS_TOML", config)

    def item(hour, marker):
        return {"ts": f"2026-01-01T{hour:02d}:00:00Z", signature: marker}

    data = {current: {"shared-old": item(10, "current-older"), "shared-new": item(14, "current-newer"),
                      "current-only": item(15, "current-only")},
            legacy: {"shared-old": item(11, "legacy-newer"), "shared-new": item(13, "legacy-older"),
                     "legacy-only": item(12, "legacy-only")},
            page.identity: {"shared-old": item(23, "foreign-state"), "guest-only": item(22, "guest-only")}}
    path = page.directory / filename
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    trusted_proxy = {"Tailscale-User-Login": current, "Tailscale-User-Name": "Actual account"}
    status, _, owner = page.call("GET", route, headers=trusted_proxy)
    assert status == 200 and owner["author"] == current
    assert owner[field] == {"shared-old": data[legacy]["shared-old"], "shared-new": data[current]["shared-new"],
                            "current-only": data[current]["current-only"], "legacy-only": data[legacy]["legacy-only"]}
    status, _, guest = page.call("GET", route, cookie=page.cookie)
    assert status == 200 and guest["author"] == page.identity and guest[field] == data[page.identity]
    assert path.read_bytes() == before
