import http.client
import json
import mmap
import os
import re
import threading

import pytest
from test_decision_api import _call, _card, _events, _store
from test_decision_api import server as server

from agent_annotate.approval_catalog import item_id


@pytest.fixture
def image_seal(tmp_path):
    from agent_annotate.approval_catalog import bind_evidence, persist_evidence, seal_review

    comment = {"id": "card", "anchor_id": "design", "version": "v1",
               "decision_request": {"prompt": "Approve?", "evidence": [{"anchor": "design"}]}}
    store = {"anchors": {"design": [comment]}}
    html = '<section id="design"><img src="a.png" alt="A"><img src="b.png" alt="B"></section>'

    def seal():
        return seal_review(tmp_path, html, "v1", store)[1]["card"]

    def approve(token):
        return persist_evidence(tmp_path, comment, bind_evidence(tmp_path, store, comment, token))

    return seal, approve


def test_seal_invalidates_on_duplicate_source_change(tmp_path, image_seal):
    seal, approve = image_seal
    (tmp_path / "a.png").write_bytes(b"original")
    (tmp_path / "b.png").write_bytes(b"original")
    displayed = seal()
    (tmp_path / "a.png").write_bytes(b"replacement")
    refreshed = seal()
    assert displayed != refreshed
    bundle = approve(refreshed)
    assert len(bundle["assets"]) == 2 and not bundle["incomplete"]
    assert approve(displayed)["incomplete"]


@pytest.mark.parametrize("changed,unchanged", [("A", "B"), ("B", "A")])
def test_approval_keeps_only_the_unchanged_duplicate_image(tmp_path, image_seal, changed, unchanged):
    seal, approve = image_seal
    for name in ("a.png", "b.png"):
        (tmp_path / name).write_bytes(b"reviewed")
    displayed = seal()
    (tmp_path / f"{changed.lower()}.png").write_bytes(b"replacement")
    bundle = approve(displayed)
    pinned, = bundle["assets"]
    assert (tmp_path / pinned).read_bytes() == b"reviewed"
    assert f'<img src="./{pinned}" alt="{unchanged}">' in bundle["html"]
    assert f'<img data-evidence-image-unavailable="" alt="{changed}">' in bundle["html"]
    assert len(bundle["incomplete"]) == 1


def test_seal_invalidates_when_missing_image_is_restored(tmp_path, image_seal):
    seal, approve = image_seal
    (tmp_path / "b.png").write_bytes(b"present")
    displayed = seal()
    (tmp_path / "a.png").write_bytes(b"restored")
    refreshed = seal()
    assert displayed != refreshed
    assert not approve(refreshed)["incomplete"]


def test_new_seal_captures_same_stat_mapped_image_edit(tmp_path, image_seal, monkeypatch):
    from agent_annotate import sync_server

    seal, approve = image_seal
    path = tmp_path / "a.png"
    path.write_bytes(b"original")
    (tmp_path / "b.png").write_bytes(b"second image")
    file_key = sync_server._file_key
    original_key = file_key(path)
    monkeypatch.setattr(sync_server, "_file_key", lambda p: original_key if p == path else file_key(p))
    with path.open("r+b") as source, mmap.mmap(source.fileno(), 0) as mapped:
        mapped[:] = b"original"
        displayed = seal()
        mapped[:] = b"updated!"
        refreshed = seal()
    assert refreshed != displayed
    bundle = approve(refreshed)
    assert {(tmp_path / name).read_bytes() for name in bundle["assets"]} == {b"updated!", b"second image"}
    assert not bundle["incomplete"]


def test_seal_does_not_cache_a_digest_with_a_newer_file_stat(tmp_path, image_seal, monkeypatch):
    from agent_annotate import approval_catalog

    seal, approve = image_seal
    a = tmp_path / "a.png"
    a.write_bytes(b"original")
    (tmp_path / "b.png").write_bytes(b"second")
    image_hash = approval_catalog._image_hash

    def replace_after_hash(path, **kwargs):
        digest = image_hash(path, **kwargs)
        if path == a:
            a.write_bytes(b"replacement")
            monkeypatch.setattr(approval_catalog, "_image_hash", image_hash)
        return digest

    monkeypatch.setattr(approval_catalog, "_image_hash", replace_after_hash)
    displayed = seal()
    refreshed = seal()
    assert refreshed != displayed
    assert not approve(refreshed)["incomplete"]


def seed(server, text="First design", version="v1", **extra):
    httpd, directory, _ = server
    (directory / "content").mkdir(exist_ok=True)
    (directory / f"content/{version}.html").write_text(
        f'<html><head></head><body><section data-anchor-id="s:design"><h2>{text}</h2>'
        '<p>Complete evidence</p></section></body></html>')
    status, comment = _call(httpd, "POST", "/api/comments/batch", {"idempotency": "anchor", "items": [
        {**_card("d:q1", **{"evidence": [{"anchor": "s:design"}], "catalog": True, **extra}), "version": version}]})
    assert status == 200
    (directory / "current.meta.json").write_text(json.dumps({"current": version, "history": [{"version": version}]}))
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
    if not extra.get("defer_push"):
        assert _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")[0] == 200
    return result


def plans(httpd):
    return _call(httpd, "GET", "/api/categories")[1]["plans"]


def test_warm_seals_skip_managed_and_absent_predecessor_lookups(tmp_path, monkeypatch):
    from agent_annotate import approval_catalog
    from agent_annotate.categories import publish_plan_revision

    (tmp_path / "plans/empty").mkdir(parents=True)
    publish_plan_revision(tmp_path, "unrelated", "<h1>Not cited</h1>")
    ids = ["managed", "absent", "empty"]
    cards = [{"id": identifier, "anchor_id": "design", "version": "v1",
              "decision_request": {"prompt": "Approve?", "item_id": identifier}}
             for identifier in ids]
    store = {"anchors": {"design": cards}, "approved_plans": {"managed": {"current": "v5"}}}
    html = '<section id="design">Design</section>'
    _, first = approval_catalog.seal_review(tmp_path, html, "v1", store)
    assert {key: first[key]["predecessor"] for key in ids} == {"managed": "v5", "absent": None, "empty": None}

    lookups, reads = [], []
    current, read_json = approval_catalog._current, approval_catalog._json

    def count_lookup(page_dir, values, identifier):
        lookups.append(identifier)
        return current(page_dir, values, identifier)

    def count_read(path, default):
        reads.append(path)
        return read_json(path, default)

    monkeypatch.setattr(approval_catalog, "_current", count_lookup)
    monkeypatch.setattr(approval_catalog, "_json", count_read)
    for _ in range(12):
        assert approval_catalog.seal_review(tmp_path, html, "v1", store)[1] == first
    assert lookups == reads == []

    publish_plan_revision(tmp_path, "empty", "<h1>Now cited</h1>")
    assert approval_catalog.seal_review(tmp_path, html, "v1", store)[1]["empty"]["predecessor"] == "v1"
    assert lookups == ["empty"]
    assert reads == [tmp_path / "plans/empty/meta.json"]


def test_seal_revalidates_plan_predecessor_with_preserved_mtime(server):
    from agent_annotate.categories import publish_plan_revision

    httpd, directory, _ = server
    comment = seed(server, item_id="design")
    publish_plan_revision(directory, "design", "<h1>First</h1>")
    meta = directory / "plans/design/meta.json"
    original = meta.stat()
    assert token(httpd, comment)["predecessor"] == "v1"
    publish_plan_revision(directory, "design", "<h1>Second</h1>")
    os.utime(meta, ns=(original.st_atime_ns, original.st_mtime_ns))
    assert token(httpd, comment)["predecessor"] == "v2"


def test_seal_refreshes_predecessor_after_same_stat_plan_edit(server, monkeypatch):
    from agent_annotate import sync_server
    from agent_annotate.categories import publish_plan_revision

    httpd, directory, _ = server
    comment = seed(server, item_id="design")
    publish_plan_revision(directory, "design", "<h1>First</h1>")
    publish_plan_revision(directory, "design", "<h1>Second</h1>")
    path = directory / "plans/design/meta.json"
    original = path.read_bytes().replace(b'"current": "v2"', b'"current": "v1"')
    path.write_bytes(original)
    key = sync_server._file_key
    original_key = key(path)
    monkeypatch.setattr(sync_server, "_file_key", lambda target: original_key if target == path else key(target))
    assert token(httpd, comment)["predecessor"] == "v1"
    with path.open("r+b") as source, mmap.mmap(source.fileno(), 0) as mapped:
        mapped[:] = original.replace(b'"current": "v1"', b'"current": "v2"')
        evidence = token(httpd, comment)
    assert evidence["predecessor"] == "v2"
    vote(httpd, comment, evidence)
    assert plans(httpd)[0]["current"] == "v3"


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
        _call(httpd, "POST", f"/api/comments/{comment['id']}/push", {}, author="chang@example.com")
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
    received = _call(httpd, "GET", "/api/comments")[1][0]
    assert received["decision"]["verdict"] == "accept" and "agent_snapshot" not in received


def test_token_cannot_file_another_items_evidence(server):
    httpd, directory, _ = server
    comment = seed(server)
    evidence = token(httpd, comment)
    _, other = _call(httpd, "POST", "/api/comments", _card("d:q2", catalog=True))
    vote(httpd, other, evidence)
    plan = _store(directory)["approved_plans"][item_id(other)]
    assert plan["history"][0]["evidence_incomplete"]
    assert _call(httpd, "GET", "/approval-evidence/" + evidence["revision"] + "/bundle.json")[0] == 404


@pytest.mark.parametrize("reload", [False, True])
def test_same_card_accept_select_accept_creates_three_committed_decisions(server, reload, monkeypatch):
    import agent_annotate.sync_server as sync_server
    # Even rapid corrections in the same clock second are distinct decisions.
    monkeypatch.setattr(sync_server, "_now_iso", lambda: "2026-10-17T10:00:00Z")
    httpd, directory, bus = server
    comment = seed(server)
    evidence = token(httpd, comment)
    ids = []
    for index, (verdict, text) in enumerate([("accept", None), ("select", "No"), ("accept", None)], 1):
        if reload:
            evidence = token(httpd, comment)
        result = vote(httpd, comment, evidence, verdict, text=text, defer_push=True)
        ids.append(result["decision"]["id"])
        assert _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")[0] == 200
        assert _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")[1]["delivery"] == "noop"
        plan = plans(httpd)[0]
        assert len(plan["history"]) == index and plan["current"] == f"v{index}"
        assert not _store(directory)["anchors"]["d:q1"][0]["decision"].get("catalog_conflict")
    assert len(set(ids)) == 3
    assert plans(httpd)[0]["kind"] == "Approved"
    assert len(_events(bus, "round_submitted")) == 3


def test_evidence_gets_add_no_writes_beyond_the_existing_fingerprint_cache(server):
    httpd, directory, _ = server
    comment = seed(server)
    (directory / "assets").mkdir()
    (directory / "assets/cited.png").write_bytes(b"image")
    content = directory / "content/v1.html"
    content.write_text(content.read_text().replace("Complete evidence", '<img src="assets/cited.png">'))
    (directory / ".comments.json.lock").unlink()
    token(httpd, comment)  # origin/main's existing fingerprint-cache write.
    def snapshot():
        return {str(path.relative_to(directory)): (path.read_bytes(), path.stat().st_mode, path.stat().st_mtime_ns)
                for path in directory.rglob("*") if path.is_file()}
    before = snapshot()
    for _ in range(2):
        evidence = token(httpd, comment)
        for route in ("/comments.json", "/api/comments", "/api/categories", "/api/history", "/current.meta.json"):
            assert _call(httpd, "GET", route)[0] == 200
        assert "view" in evidence
    assert snapshot() == before
    assert not (directory / "approval-evidence").exists()
    assert not (directory / "attachments").exists()
    # The accept POST persists evidence before Send, while Plans remains empty.
    vote(httpd, comment, evidence, defer_push=True)
    assert (directory / "approval-evidence").is_dir()
    assert plans(httpd) == []
    _call(httpd, "POST", "/api/rounds/submit", {}, author="chang@example.com")
    assert (directory / "approval-evidence").is_dir()


def test_bad_anchor_and_missing_bundle_never_break_review_vote_or_plans(server):
    httpd, directory, _ = server
    comment = seed(server, evidence=[{"anchor": []}])
    evidence = token(httpd, comment)
    vote(httpd, comment, evidence)
    plan = plans(httpd)[0]
    assert plan["history"][0]["evidence_incomplete"]
    revision = plan["history"][0]["evidence_revision"]
    (directory / "approval-evidence" / revision / "bundle.json").unlink()
    status, body = _call(httpd, "GET", f"/plans/{plan['id']}/v1.html")
    assert status == 200 and b"Evidence incomplete" in body


@pytest.mark.parametrize("route", ["single", "round"])
def test_agents_and_legacy_votes_are_not_cataloged_on_push(server, route):
    httpd, directory, _ = server
    comment = seed(server)
    evidence = token(httpd, comment)
    assert _call(httpd, "POST", f"/api/comments/{comment['id']}/decision", {"verdict": "accept", "evidence": evidence})[0] == 200
    assert plans(httpd) == []
    store = _store(directory)
    store["anchors"]["d:q1"][0]["decision"] = {"verdict": "accept", "by": "chang@example.com", "ts": "2025-01-01T00:00:00Z", "round_pending": True}
    (directory / "comments.json").write_text(json.dumps(store))
    path = f"/api/comments/{comment['id']}/push" if route == "single" else "/api/rounds/submit"
    assert _call(httpd, "POST", path, {}, author="chang@example.com")[0] == 200
    assert plans(httpd) == [] and not (directory / "approval-evidence").exists()


def test_browser_card_text_is_ignored_and_compact_store_permissions_preserved(server):
    httpd, directory, _ = server
    comment = seed(server)
    evidence = token(httpd, comment)
    path = directory / "comments.json"
    path.chmod(0o644)
    vote(httpd, comment, evidence, shown_request={"prompt": "Invented browser prompt", "context": "Invented"})
    assert path.stat().st_mode & 0o777 == 0o644
    assert path.read_text().startswith('{"schema_version":2,"anchors":{')
    plan = plans(httpd)[0]
    status, body = _call(httpd, "GET", f"/plans/{plan['id']}/v1.html")
    assert status == 200 and b"Invented" not in body and b"Rename?" in body
    assert b"Chosen: <strong>Yes</strong>" in body and b"<li>No" not in body


def test_manual_publish_checks_managed_identity_under_the_store_lock(server, monkeypatch):
    import agent_annotate.categories as categories
    from agent_annotate.sync_server import _locked_store
    _, directory, _ = server
    observed, started = threading.Event(), threading.Event()
    original = categories._comments
    errors = []
    def inspect(page):
        observed.set()
        return original(page)
    def publish():
        started.set()
        try:
            categories.publish_plan_revision(directory, "managed", "<p>Unapproved</p>")
        except ValueError as exc:
            errors.append(str(exc))
    monkeypatch.setattr(categories, "_comments", inspect)
    with _locked_store(directory):
        thread = threading.Thread(target=publish)
        thread.start()
        assert started.wait(1)
        assert not observed.wait(0.1), "manual guard read outside the page lock"
        store = _store(directory)
        store["approved_plans"] = {"managed": {"current": "v1", "history": []}}
        (directory / "comments.json").write_text(json.dumps(store))
    thread.join(timeout=2)
    assert not thread.is_alive() and errors
    assert "reviewer decisions" in errors[0]
    assert not (directory / "plans/managed/versions").exists()


@pytest.mark.parametrize("loss", ["restart", "eviction"])
@pytest.mark.parametrize("verdict", ["accept", "select"])
def test_vote_evidence_survives_restart_or_eviction_before_send(server, loss, verdict):
    from agent_annotate.approval_catalog import _SEALS, _VIEWS, read_bundle
    httpd, directory, _ = server
    comment = seed(server)
    (directory / "assets").mkdir()
    original = directory / "assets/cited.png"
    original.write_bytes(b"reviewed-image")
    source = directory / "content/v1.html"
    source.write_text(source.read_text().replace("Complete evidence", '<img src="assets/cited.png">'))
    evidence = token(httpd, comment)
    posted = vote(httpd, comment, evidence, verdict, text="Yes" if verdict == "select" else None, defer_push=True)
    saved = posted["decision"]["evidence"]
    assert saved["committed"] and plans(httpd) == []
    bundle = read_bundle(directory, saved["revision"])
    pinned = next(iter(bundle["assets"]))
    assert (directory / pinned).read_bytes() == b"reviewed-image"
    original.write_bytes(b"changed-after-vote")
    if loss == "eviction":
        for _ in range(17):
            _SEALS.clear()  # an unchanged page reuses its view; each read must mint one to evict
            token(httpd, comment)
    else:
        _VIEWS.clear()
    assert (str(directory), evidence["view"]) not in _VIEWS
    receiver = httpd
    if loss == "restart":
        receiver = type(httpd)(("127.0.0.1", 0), httpd.RequestHandlerClass)
        thread = threading.Thread(target=receiver.serve_forever, daemon=True)
        thread.start()
    try:
        assert _call(receiver, "POST", "/api/rounds/submit", {}, author="chang@example.com")[0] == 200
        plan = plans(receiver)[0]
        assert len(plan["history"]) == 1 and not plan["history"][0]["evidence_incomplete"]
        assert plan["history"][0]["evidence_revision"] == saved["revision"]
        assert (directory / pinned).read_bytes() == b"reviewed-image"
        assert b"First design" in _call(receiver, "GET", f"/plans/{plan['id']}/v1.html")[1]
    finally:
        if receiver is not httpd:
            receiver.shutdown()
            receiver.server_close()
            thread.join(timeout=2)


def test_review_keeps_image_and_link_urls_working_after_cache_eviction(server):
    from agent_annotate.approval_catalog import _VIEWS
    httpd, directory, _ = server
    comment = seed(server)
    (directory / "assets").mkdir()
    (directory / "assets/cited.png").write_bytes(b"image")
    source = directory / "content/v1.html"
    source.write_text(source.read_text().replace("Complete evidence", '<img src="assets/cited.png">')
                      .replace("</body>", '<img src="assets/cited.png"><a href="assets/cited.png">Original</a></body>'))
    status, html = _call(httpd, "GET", "/content?v=v1")
    assert status == 200 and html.count(b'src="assets/cited.png"') == 2
    assert b'href="assets/cited.png"' in html and b"/api/review-evidence/" not in html
    for _ in range(17):
        token(httpd, comment)
    _VIEWS.clear()
    assert _call(httpd, "GET", "/assets/cited.png") == (200, b"image")


@pytest.mark.parametrize("with_token", [False, True])
def test_repeated_immediate_accept_is_idempotent_even_after_cache_loss(server, with_token):
    from agent_annotate.approval_catalog import _VIEWS
    httpd, _, bus = server
    comment = seed(server)
    evidence = token(httpd, comment) if with_token else None
    first = vote(httpd, comment, evidence)
    _VIEWS.clear()
    for _ in range(2):
        repeated = vote(httpd, comment, evidence)
        assert repeated["delivery"] == "noop"
        assert repeated["decision"]["id"] == first["decision"]["id"]
    assert len(plans(httpd)[0]["history"]) == 1
    assert len(_events(bus, "session_push")) == 1


def test_unnumbered_carry_and_new_comment_reask_preserve_lineage(server):
    httpd, directory, _ = server
    (directory / "versions").mkdir()
    (directory / "versions/v2.html").write_text('<p data-anchor-id="s:new">Moved evidence</p>')
    status, first = _call(httpd, "POST", "/api/comments", _card("s:old"))
    assert status == 201
    status, carried = _call(httpd, "PUT", f"/api/comments/{first['id']}", {"carry_forward": {"version": "v2", "anchor_id": "s:new"}})
    assert status == 200 and carried["origin_id"] == first["id"]
    assert item_id(carried) == item_id(first)
    _call(httpd, "POST", f"/api/comments/{first['id']}/decision", {"verdict": "accept"}, author="chang@example.com")
    status, result = _call(httpd, "POST", "/api/comments/batch", {"idempotency": "anchor", "items": [
        {**_card("s:new", prompt="Revised proposal?"), "version": "v3"}]})
    assert status == 200 and result["created"] == 1
    reasked = _store(directory)["anchors"]["s:new"][-1]
    assert reasked["id"] != first["id"] and reasked["origin_id"] == first["id"]
    assert item_id(reasked) == item_id(first)


def test_unnumbered_reask_does_not_merge_ambiguous_shared_anchor_cards(server):
    httpd, directory, _ = server
    first = _call(httpd, "POST", "/api/comments", _card("s:shared", prompt="First?"))[1]
    second = _call(httpd, "POST", "/api/comments", _card("s:shared", prompt="Second?"))[1]
    for comment in (first, second):
        _call(httpd, "POST", f"/api/comments/{comment['id']}/decision", {"verdict": "accept"}, author="chang@example.com")
    status, _ = _call(httpd, "POST", "/api/comments/batch", {"idempotency": "anchor", "items": [
        {**_card("s:shared", prompt="Another?"), "version": "v2"}]})
    assert status == 200
    (directory / "current.meta.json").write_text(json.dumps({"current": "v2", "history": [{"version": "v1"}, {"version": "v2"}]}))
    comments = _call(httpd, "GET", "/api/comments")[1]
    third = next(c for c in comments if c["text"] == "Another?")
    assert item_id(third) not in {item_id(first), item_id(second)}
