"""uzd: on a long page the first load and a Send each move under a tenth of the comment store.

Chang (card 251): a Send carried thousands of old history items and comments the
review page does not show. Settled feedback from older versions loads when the
reviewer opens it (test_page_store); a Send carries only this round.
"""

import json
import urllib.request

import pytest
from test_keep_drafts import _directory, _session

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


def test_opening_earlier_feedback_restores_an_answer_edited_in_another_tab(tmp_path):
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
        partial = page.request.get(base + "comments.json?view=page").json()
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
        playwright.expect(page.locator(old_selector)).to_be_visible()
        playwright.expect(page.locator("#aa-fresh .aa-fresh-n")).to_be_hidden()

        # A link opened with the same partial snapshot still finds the saved draft via the full store.
        page.route("**/comments.json?view=page", lambda route: route.fulfill(json=partial), times=1)
        page.goto(base + "#view=review&feedback=old-0")
        page.reload(wait_until="networkidle")
        linked = page.locator(old_selector + ".hl")
        playwright.expect(linked.locator('[data-note-edit][data-key="decision"]')).to_have_value("Unfinished answer edit")


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
                dict(historical, id="plan-v1", version="v1", text="Feedback on the first revision"),
                dict(historical, id="plan-v2", version="v2", text="Feedback on the second revision"),
            ])
            path.write_text(json.dumps(latest))
            route.continue_()

        page.route("**/comments.json?view=poll", publish_revision, times=1)
        rail.locator('[data-section-toggle="earlier"]').click()
        playwright.expect(rail.locator('[data-comment-id="plan-legacy"]')).to_be_visible()
        rail.locator('[data-section-toggle="done"]').click()
        playwright.expect(old).to_be_visible()
        playwright.expect(current).to_have_count(0)
        playwright.expect(page.locator("#aa-fresh .aa-fresh-n")).to_have_text("1")

        page.locator("#aa-fresh").click()
        playwright.expect(current).to_be_visible()
