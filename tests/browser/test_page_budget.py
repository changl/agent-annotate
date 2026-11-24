"""uzd: on a long page the first load and a Send each move under a tenth of the comment store.

Chang (card 251): a Send carried thousands of old history items and comments the
review page does not show. Settled feedback from older versions loads when the
reviewer opens it (test_page_store); a Send carries only this round.
"""

import gzip
import json
import urllib.request

import pytest
from test_keep_drafts import _agent, _directory, _session

from agent_annotate import store as page_storage
from agent_annotate.categories import publish_plan_revision

playwright = pytest.importorskip("playwright.sync_api")

# Every byte the top frame read since `since` (304s count as nothing: they carry no body).
BYTES = """(since) => performance.getEntriesByType('resource').slice(since)
  .map(e => [e.name.replace(location.origin, ''), e.decodedBodySize])"""


def _long_history(directory, n=1500):
    path = directory / "comments.json"
    store = json.loads(path.read_text())
    done = {"verdict": "accept", "by": "reviewer@example.com", "at": "2026-09-01T10:00:00Z"}
    for i in range(n):
        aid = f"s:old{i}"
        area = "archived" if i % 2 else "anchors"
        store[area][aid] = [{
            "id": f"old-{i}", "anchor_id": aid, "version": "v0", "author": "agent:old",
            "status": "archived" if i % 2 else "addressed_by_agent", "created_at": "2026-09-01T09:00:00Z",
            "text": "Settled long ago. " * 20, "decision": done,
            "decision_request": {"prompt": f"Old question {i}?", "options": [{"id": "accept", "label": "Yes"}]},
            "replies": [{"author": "reviewer@example.com", "text": "Answered. " * 15, "sent_at": "2026-09-01T10:00:00Z"}]}]
    path.write_text(json.dumps(store))
    meta_path = directory / "current.meta.json"
    meta = json.loads(meta_path.read_text())
    meta["history"] = [{"version": "v0"}] + meta.get("history", [])  # an older published version
    meta_path.write_text(json.dumps(meta))


def test_first_load_and_send_stay_under_a_tenth_of_the_store(tmp_path):
    directory = _directory(tmp_path)
    _long_history(directory)
    with _session(tmp_path, directory) as (page, base, _):
        with urllib.request.urlopen(base + "comments.json?view=poll") as response:
            full = len(response.read())
        assert full > 1_000_000
        page.wait_for_load_state("networkidle")
        first = page.evaluate(BYTES, 0)
        store = [(url, size) for url, size in first if "comments.json" in url]
        assert store and all(url.endswith("view=page") for url, _ in store), store
        assert sum(size for _, size in store) * 10 < full, store

        posts = []
        page.on("request", lambda r: r.method != "GET" and posts.append(len(r.post_data or "")))
        since = len(page.evaluate(BYTES, 0))
        page.locator('#comment-list [data-comment-id="question-11"] .decision-btn').first.click()
        page.locator("#send-btn").click()
        page.locator("#round-submit-btn").click()
        page.wait_for_function("() => !document.querySelector('#round-confirm-backdrop.vis')")
        page.wait_for_load_state("networkidle")
        send = page.evaluate(BYTES, since)
        assert not any("view=poll" in url for url, _ in send), send
        assert sum(size for _, size in send) * 10 < full, send
        assert posts and sum(posts) < 4096, posts


def test_store_snapshot_metadata_does_not_scale_with_old_cards(tmp_path):
    directory = _directory(tmp_path)
    _long_history(directory)
    with _session(tmp_path, directory) as (_, base, _):
        for view in ("page", "poll"):
            request = urllib.request.Request(base + "comments.json?view=" + view, headers={"Accept-Encoding": "gzip"})
            with urllib.request.urlopen(request) as response:
                wire = response.read()
            body = gzip.decompress(wire)
            baseline = json.loads(body)
            for field in ("store_mark", "item_stamps", "omitted_stamps"):
                baseline.pop(field, None)
            plain = json.dumps(baseline, ensure_ascii=False, separators=(",", ":")).encode()
            baseline_wire = gzip.compress(plain, compresslevel=6, mtime=0)
            # A single fixed-size mark also has to fit this tiny projected fixture.
            assert len(body) - len(plain) <= max(64, len(plain) * 0.02)
            assert len(wire) - len(baseline_wire) <= max(64, len(baseline_wire) * 0.02)


def test_opening_earlier_feedback_keeps_new_questions_behind_refresh(tmp_path):
    directory = _directory(tmp_path)
    _long_history(directory, 2)
    with _session(tmp_path, directory) as (page, _base, _):
        rail = page.locator("#comment-list")
        new_question = rail.locator('[data-comment-id="new-question"]')
        old_question = rail.locator('[data-comment-id="old-0"]')
        assert old_question.count() == 0

        def add_question(route):
            # The first full read sees a question the last partial poll could not see.
            path = directory / "comments.json"
            store = json.loads(path.read_text())
            store["anchors"].setdefault("s:checks", []).append({
                "id": "new-question", "anchor_id": "s:checks", "version": "v1", "author": "agent:late",
                "status": "open", "text": "Did the new build pass?", "replies": [],
                "decision_request": {"prompt": "Did the new build pass?", "options": [{"id": "yes", "label": "Yes"}]},
            })
            path.write_text(json.dumps(store))
            route.continue_()

        page.route("**/comments.json?view=poll", add_question, times=1)
        rail.locator('[data-section-toggle="earlier"]').click()
        old_question.wait_for()
        assert new_question.count() == 0
        playwright.expect(page.locator("#aa-fresh .aa-fresh-n")).to_have_text("1")

        page.locator("#aa-fresh").click()
        new_question.wait_for()


def test_opening_earlier_feedback_holds_an_answer_edited_in_another_tab_for_refresh(tmp_path):
    directory = _directory(tmp_path)
    _long_history(directory, 2)
    path = directory / "comments.json"
    store = json.loads(path.read_text())
    store["anchors"]["s:old0"][0]["decision"].update(
        text="Original answer note", by="Browser Reviewer <reviewer@example.com>"
    )
    path.write_text(json.dumps(store))

    with _session(tmp_path, directory) as (page, base, _):
        old_selector = '#comment-list [data-comment-id="old-0"]'
        assert page.locator(old_selector).count() == 0
        other = page.context.new_page()
        other.set_default_timeout(8000)
        other.goto(base + "#view=review&feedback=old-0", wait_until="networkidle")
        old = other.locator(old_selector)
        edit = old.locator('[data-note-action="edit"][data-key="decision"]')
        note = old.locator('[data-note-edit][data-key="decision"]')
        edit.click()
        note.fill("Updated answer note")
        with other.expect_response(lambda r: "/api/comments/old-0/decision" in r.url) as saved:
            old.locator('[data-note-action="save"][data-key="decision"]').click()
        assert saved.value.ok
        playwright.expect(old).to_contain_text("Updated answer note")
        old.locator('[data-action="open-card"]').click()
        edit.click()
        note.fill("Unfinished answer edit")
        page.bring_to_front()

        page.locator('#comment-list [data-section-toggle="earlier"]').click()
        playwright.expect(page.locator('#comment-list [data-comment-id="old-1"]')).to_be_visible()
        playwright.expect(page.locator(old_selector)).to_have_count(0)
        playwright.expect(page.locator("#aa-fresh .aa-fresh-n")).to_have_text("1")
        page.locator("#aa-fresh").click()
        playwright.expect(page.locator(old_selector)).to_be_visible()

        # Opening a link to the answer still restores the draft from the other tab.
        page.goto(base + "#view=review&feedback=old-0")
        page.reload(wait_until="networkidle")
        linked = page.locator(old_selector + ".hl")
        playwright.expect(linked.locator('[data-note-edit][data-key="decision"]')).to_have_value("Unfinished answer edit")


def test_cold_link_restores_draft_when_its_omitted_answer_changed(tmp_path):
    directory = _directory(tmp_path)
    _long_history(directory, 2)
    with _session(tmp_path, directory) as (page, base, _):
        partial = page.request.get(base + "comments.json?view=page").json()
        assert all(c["id"] != "old-0" for items in partial["anchors"].values() for c in items)
        changed = page.request.post(base + "api/comments/old-0/decision", data={
            "verdict": "accept", "text": "Edited answer note",
        })
        assert changed.ok, changed.text()
        page.evaluate("""localStorage.setItem('annotate:drafts:' + location.pathname + ':review',
                         JSON.stringify({'note:old-0|decision': 'Unfinished answer edit'}))""")
        linked = page.context.new_page()
        linked.route("**/comments.json?view=page", lambda route: route.fulfill(json=partial), times=1)
        linked.goto(base + "#view=review&feedback=old-0", wait_until="networkidle")
        highlighted = linked.locator('#comment-list [data-comment-id="old-0"].hl')
        editor = highlighted.locator('[data-note-edit][data-key="decision"]')
        playwright.expect(editor).to_have_value("Unfinished answer edit")


def test_refresh_excludes_questions_withdrawn_during_earlier_load(tmp_path):
    directory = _directory(tmp_path)
    _long_history(directory, 2)

    def question(cid):
        return {
            "id": cid, "anchor_id": "s:checks", "version": "v1", "author": "agent:late",
            "status": "open", "text": cid, "replies": [],
            "decision_request": {"prompt": cid, "options": [{"id": "yes", "label": "Yes"}]},
        }

    with _session(tmp_path, directory) as (page, base, _):
        def update(route):
            path = directory / "comments.json"
            store = json.loads(path.read_text())
            store["anchors"].setdefault("s:checks", []).extend([
                question("superseded-question"), question("replacement-question"),
            ])
            path.write_text(json.dumps(store))
            _agent(base, "api/comments/superseded-question", {
                "decision_request": None, "withdraw_reason": "Superseded by a later question",
            }, method="PUT")
            route.continue_()

        page.route("**/comments.json?view=poll", update, times=1)
        rail = page.locator("#comment-list")
        rail.locator('[data-section-toggle="earlier"]').click()
        playwright.expect(rail.locator('[data-comment-id="old-0"]')).to_be_visible()
        fresh = page.locator("#aa-fresh")
        playwright.expect(fresh.locator(".aa-fresh-n")).to_have_text("1")
        fresh.click()
        playwright.expect(rail.locator('[data-comment-id="replacement-question"]')).to_be_visible()
        playwright.expect(rail.locator('[data-comment-id="superseded-question"]')).to_have_count(0)


def test_opening_earlier_feedback_keeps_plan_history_after_a_new_revision(tmp_path):
    directory = _directory(tmp_path)
    publish_plan_revision(directory, "rollout", "<h1>Rollout v1</h1>", title="Rollout")
    path = directory / "comments.json"
    store = json.loads(path.read_text())
    historical = {
        "id": "plan-legacy", "anchor_id": "s:rollout", "text": "Legacy rollout feedback",
        "category": "plans", "doc": "plan:rollout", "version": "v0", "status": "addressed_by_agent",
        "author": "reviewer@example.com", "created_at": "2026-09-01T10:00:00Z", "replies": [],
    }
    store["anchors"]["s:rollout"] = [historical]
    path.write_text(json.dumps(store))

    with _session(tmp_path, directory) as (page, base, _):
        page.goto(base + "#view=plans&plan=rollout", wait_until="networkidle")
        playwright.expect(page.frame_locator("#content-frame").get_by_role("heading", name="Rollout v1")).to_be_visible()
        rail = page.locator("#comment-list")
        old = rail.locator('[data-comment-id="plan-v1"]')
        current = rail.locator('[data-comment-id="plan-v2"]')

        def publish_revision(route):
            # The full read sees v2 and feedback absent from the v1 snapshot.
            publish_plan_revision(directory, "rollout", "<h1>Rollout v2</h1>", title="Rollout")
            latest = json.loads(path.read_text())
            latest["anchors"]["s:rollout"].extend([
                dict(historical, id="plan-v1", version="v1", text="New feedback on the first revision"),
                dict(historical, id="plan-v2", version="v2", text="Feedback on the second revision"),
            ])
            path.write_text(json.dumps(latest))
            route.continue_()

        page.route("**/comments.json?view=poll", publish_revision, times=1)
        rail.locator('[data-section-toggle="earlier"]').click()
        playwright.expect(rail.locator('[data-comment-id="plan-legacy"]')).to_be_visible()
        assert page.evaluate("!window.AnnotateDocs.findComment('plan-v1')")
        playwright.expect(current).to_have_count(0)
        playwright.expect(page.locator("#aa-fresh .aa-fresh-n")).to_have_text("2")

        page.locator("#aa-fresh").click()
        rail.locator('[data-section-toggle="done"]').click()
        playwright.expect(current).to_be_visible()
        playwright.expect(old).to_be_visible()


def test_approval_managed_plan_keeps_new_questions_behind_refresh(tmp_path):
    directory = _directory(tmp_path)
    path = directory / "comments.json"
    store = json.loads(path.read_text())
    store["approved_plans"] = {"rollout": {
        "title": "Filed rollout", "current": "v1", "section": "approved", "managed": True,
        "history": [{"version": "v1", "source_version": "v1", "evidence_revision": "missing",
                     "label": "Approved", "source_card": "question-11", "by": "Reviewer",
                     "ts": "2026-10-01T00:00:00Z", "consequence": "Release."}],
    }}
    path.write_text(json.dumps(store))

    with _session(tmp_path, directory) as (page, base, _):
        page.goto(base + "#view=plans&plan=rollout", wait_until="networkidle")
        playwright.expect(page.frame_locator("#content-frame").get_by_role("heading", name="Filed rollout")).to_be_visible()

        def add_question(route):
            _agent(base, "api/comments/batch", {"items": [{
                "id": "catalog-question", "anchor_id": "s:rollout", "doc": "plan:rollout", "version": "v1",
                "text": "Can we release?", "decision_request": {
                    "prompt": "Can we release?", "options": [{"id": "yes", "label": "Yes"}],
                },
            }]})
            route.continue_()

        page.route("**/comments.json?view=poll", add_question, times=1)
        page.locator("#tab-history").click()
        page.wait_for_function("() => !window.AnnotateDocs.store().partial")
        page.locator("#tab-feedback").click()
        question = page.locator('#comment-list [data-comment-id="catalog-question"]')
        playwright.expect(question).to_have_count(0)
        playwright.expect(page.locator("#aa-fresh .aa-fresh-n")).to_have_text("1")
        page.locator("#aa-fresh").click()
        playwright.expect(question).to_be_visible()


def test_late_full_response_keeps_the_newer_etag(tmp_path):
    directory = _directory(tmp_path)
    _long_history(directory, 2)
    full_url = "comments.json?view=poll"
    with _session(tmp_path, directory) as (page, base, _):
        def poll():
            with page.expect_response(lambda r: r.url.endswith(full_url)) as response:
                page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
            return response.value

        held = []
        page.route("**/" + full_url, lambda route: held.append((route, route.fetch())), times=1)
        page.locator('#comment-list [data-section-toggle="earlier"]').click()
        page.wait_for_function("() => document.querySelector('#sec-body-earlier')?.textContent.includes('Loading earlier feedback')")
        route, initial = held.pop()
        comment_url = base + "api/comments"
        assert page.request.post(comment_url, data={
            "id": "temporary", "anchor_id": "s:checks", "text": "Temporary note", "version": "v1",
        }).status == 201
        newer = poll()
        assert newer.headers["etag"] != initial.headers["etag"]
        route.fulfill(response=initial)
        playwright.expect(page.locator('#comment-list [data-comment-id="old-0"]')).to_be_visible()
        badge = page.locator("#aa-fresh .aa-fresh-n")
        playwright.expect(badge).to_have_text("1")

        assert page.request.delete(comment_url + "/temporary").ok
        assert page.request.get(base + full_url).headers["etag"] == initial.headers["etag"]
        after_delete = poll()
        assert after_delete.request.headers["if-none-match"] == newer.headers["etag"]
        assert after_delete.status == 200
        playwright.expect(badge).to_be_hidden()
        page.locator("#aa-fresh").click()
        assert page.evaluate("!window.AnnotateDocs.findComment('temporary')")


def test_unchanged_multi_plan_full_store_revalidates_after_restart(tmp_path, monkeypatch):
    directory = _directory(tmp_path)
    for n in range(8):
        publish_plan_revision(directory, f"plan-{n}", f"<h1>Plan {n}</h1>", title=f"Plan {n}")
    monkeypatch.setenv("PYTHONHASHSEED", "1")
    with _session(tmp_path, directory) as (page, base, restart):
        _agent(base, "api/comments/batch", {"items": [{
            "id": f"note-{n}", "anchor_id": "s:checks", "doc": f"plan:plan-{n}",
            "version": "v1", "text": f"Agent note {n}",
        } for n in range(8)]})
        url = base + "comments.json?view=poll"
        etag = page.request.get(url).headers["etag"]
        monkeypatch.setenv("PYTHONHASHSEED", "2")
        restart()
        response = page.request.get(url, headers={"If-None-Match": etag})
        assert response.status == 304


def _expect_full_adoption(page, response):
    full = response.json()
    assert full["snapshot_expired"]
    page.wait_for_function("() => !window.AnnotateDocs.store().partial")
    assert page.evaluate("window.AnnotateDocs.store()") == full
    playwright.expect(page.locator("#aa-fresh .aa-fresh-n")).to_be_hidden()


@pytest.mark.parametrize("backend", ["json", "sqlite"])
@pytest.mark.parametrize("archived_only", [False, True], ids=["new-note", "archived-only"])
def test_earlier_feedback_keeps_history_when_a_restart_expires_its_mark(tmp_path, backend, archived_only):
    directory = _directory(tmp_path)
    _long_history(directory, 2)
    if archived_only:
        path = directory / "comments.json"
        store = json.loads(path.read_text())
        del store["anchors"]["s:old0"]
        path.write_text(json.dumps(store))
    if backend == "sqlite":
        page_storage.import_page(directory, project="bus", slug="items-model", state_dir=tmp_path / "state")
    assert page_storage.backend(directory) == backend

    with _session(tmp_path, directory) as (page, base, restart):
        restart()
        note_url = base + "api/comments"
        assert page.request.post(note_url, data={
            "id": "restart-note", "anchor_id": "s:checks", "text": "Note after restart", "version": "v1",
        }).status == 201
        if archived_only:
            assert page.request.delete(note_url + "/restart-note").ok

        rail = page.locator("#comment-list")
        earlier = rail.locator('[data-section-toggle="earlier"]')
        archived = rail.locator('[data-comment-id="old-1"]')
        note = rail.locator('[data-comment-id="restart-note"]')
        with page.expect_response(lambda r: r.url.endswith("comments.json?view=poll")) as loaded:
            earlier.click()
        playwright.expect(archived).to_be_visible()
        _expect_full_adoption(page, loaded.value)
        if not archived_only:
            playwright.expect(rail.locator('[data-comment-id="old-0"]')).to_be_visible()
            playwright.expect(note).to_be_visible()

        with page.expect_response(lambda r: r.url.endswith("comments.json?view=poll")):
            page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
        playwright.expect(archived).to_be_visible()
        playwright.expect(page.locator("#aa-fresh .aa-fresh-n")).to_be_hidden()


@pytest.mark.parametrize("backend", ["json", "sqlite"])
def test_expired_mark_adopts_notes_on_both_plan_revisions(tmp_path, backend):
    directory = _directory(tmp_path)
    publish_plan_revision(directory, "rollout", "<h1>Rollout v1</h1>", title="Rollout")
    path = directory / "comments.json"
    store = json.loads(path.read_text())
    store["anchors"]["s:rollout"] = [{
        "id": "plan-history", "anchor_id": "s:rollout", "doc": "plan:rollout", "category": "plans",
        "version": "v0", "status": "addressed_by_agent", "author": "reviewer@example.com",
        "text": "Settled earlier plan feedback", "created_at": "2026-09-01T00:00:00Z", "replies": [],
    }]
    path.write_text(json.dumps(store))
    if backend == "sqlite":
        page_storage.import_page(directory, project="bus", slug="items-model", state_dir=tmp_path / "state")
    assert page_storage.backend(directory) == backend

    with _session(tmp_path, directory) as (page, base, restart):
        page.goto(base + "#view=plans&plan=rollout", wait_until="networkidle")
        playwright.expect(page.frame_locator("#content-frame").get_by_role("heading", name="Rollout v1")).to_be_visible()
        restart()

        def add_note(version):
            _agent(base, "api/comments/batch", {"items": [{
                "id": f"late-{version}-note", "anchor_id": "s:rollout", "doc": "plan:rollout",
                "version": version, "text": f"Feedback on {version}",
            }]})

        def publish_during_read(route):
            add_note("v1")
            publish_plan_revision(directory, "rollout", "<h1>Rollout v2</h1>", title="Rollout")
            add_note("v2")
            route.continue_()

        page.route("**/comments.json?view=poll", publish_during_read, times=1)
        rail = page.locator("#comment-list")
        with page.expect_response(lambda r: r.url.endswith("comments.json?view=poll")) as loaded:
            rail.locator('[data-section-toggle="earlier"]').click()
        _expect_full_adoption(page, loaded.value)
        assert page.evaluate("['late-v1-note', 'late-v2-note'].every(id => window.AnnotateDocs.findComment(id))")
        playwright.expect(rail.locator('[data-comment-id="plan-history"]')).to_be_visible()


def test_expired_mark_keeps_an_older_answer_when_its_prompt_is_repeated(tmp_path):
    directory = _directory(tmp_path)
    for version in ("v1", "v2"):
        publish_plan_revision(directory, "rollout", f"<h1>Rollout {version}</h1>", title="Rollout")
    path = directory / "comments.json"
    store = json.loads(path.read_text())
    question = {"prompt": "Is rollout ready?", "options": [{"id": "yes", "label": "Yes"}]}
    store["anchors"]["s:rollout"] = [{
        "id": "old-answer", "anchor_id": "s:rollout", "doc": "plan:rollout", "category": "plans",
        "version": "v1", "status": "addressed_by_agent", "author": "agent:review-test",
        "text": "Settled earlier plan question", "created_at": "2026-09-01T00:00:00Z", "replies": [],
        "decision_request": question,
        "decision": {"verdict": "accept", "by": "reviewer@example.com", "at": "2026-09-02T00:00:00Z"},
    }]
    path.write_text(json.dumps(store))

    with _session(tmp_path, directory) as (page, base, restart):
        page.goto(base + "#view=plans&plan=rollout", wait_until="networkidle")
        playwright.expect(page.frame_locator("#content-frame").get_by_role("heading", name="Rollout v2")).to_be_visible()
        assert page.evaluate("!window.AnnotateDocs.findComment('old-answer')")
        restart()
        _agent(base, "api/comments/batch", {"items": [{
            "id": "repeated-question", "anchor_id": "s:rollout", "doc": "plan:rollout", "version": "v2",
            "text": "Current plan question", "decision_request": question,
        }]})
        rail = page.locator("#comment-list")
        with page.expect_response(lambda r: r.url.endswith("comments.json?view=poll")) as loaded:
            rail.locator('[data-section-toggle="earlier"]').click()
        playwright.expect(rail.locator('[data-section="earlier"] [data-comment-id="old-answer"]')).to_be_visible()
        playwright.expect(rail.locator('[data-comment-id="repeated-question"]')).to_be_visible()
        _expect_full_adoption(page, loaded.value)
