"""Your own comments and worded answers can be edited and sent again, and each
says whether it has been sent (Chang, 2026-10-30)."""

import json

import pytest
from test_keep_drafts import _directory, _session

playwright = pytest.importorskip("playwright.sync_api")


def _stored(directory, cid):
    return next(c for items in json.loads((directory / "comments.json").read_text())["anchors"].values()
                for c in items if c["id"] == cid)


def _send(page):
    page.locator("#send-btn").click()
    page.locator("#round-submit-btn").click()
    page.wait_for_function("() => !document.querySelector('#round-confirm-backdrop.vis')")


def _card(page, text):
    return page.locator("#comment-list .citem", has_text=text).first


def test_edit_your_comment_and_send_it_again(tmp_path):
    directory = _directory(tmp_path)
    with _session(tmp_path, directory) as (page, base, _):
        page.frame_locator("#content-frame").locator('[data-anchor-id="s:checks"] h2').click(position={"x": 10, "y": 5})
        page.locator("#pop-ta").fill("Build note, first take")
        page.locator("#pop-save").click()
        card = _card(page, "Build note, first take")
        card.wait_for()
        assert card.locator(".send-state").inner_text() == "Pending"
        _send(page)
        playwright.expect(_card(page, "Build note, first take").locator(".send-state")).to_have_text("In inbox · owner delivery pending")
        card = _card(page, "Build note, first take")

        card.locator('[data-action="menu"]').click()
        card.locator('[data-action="edit"]').click()
        box = page.locator("#comment-list .edit-ta")
        assert box.input_value() == "Build note, first take"
        box.fill("Build note, corrected")
        page.locator('#comment-list [data-action="edit-save"]').click()
        card = _card(page, "Build note, corrected")
        card.wait_for()
        assert "(edited)" in card.inner_text()
        assert card.locator(".send-state").inner_text() == "Pending"
        cid = card.get_attribute("data-comment-id")
        assert _stored(directory, cid)["text"] == "Build note, corrected"
        _send(page)
        page.wait_for_function("id => document.querySelector(`#comment-list [data-comment-id='${id}'] .send-state`)?.textContent === 'In inbox · owner delivery pending'", arg=cid)


def _round_answers(directory):
    # What each Send delivered (a round or a push), as the page's history keeps it.
    path = directory / "rounds.ndjson"
    rounds = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    return rounds[-1]["answers"] if rounds else []


def test_notes_add_up_and_every_one_reaches_the_agent(tmp_path):
    """#2659: a second worded answer replaced the first, and only the second was sent."""
    directory = _directory(tmp_path)
    with _session(tmp_path, directory) as (page, base, _):
        page.on("dialog", lambda d: d.accept())
        frame = page.frame_locator("#content-frame")
        item = frame.locator('[data-strip-item="question-11"]')
        item.locator("textarea").fill("Change the time to 10:30")
        item.locator(".annotate-decision-btns button").last.click()  # Answer in words
        item.locator(".annotate-add-note textarea").wait_for()
        for text in ("Send the reminder at 8:30AM", "Typo, ignore this"):
            item.locator(".annotate-add-note textarea").fill(text)
            item.locator(".annotate-note-add").click()
            page.wait_for_function("t => document.querySelector('#content-frame').contentDocument.body.textContent.includes(t)", arg=text)
        notes = item.locator(".annotate-answer-note-txt")
        assert notes.all_inner_texts() == ["Change the time to 10:30", "Send the reminder at 8:30AM", "Typo, ignore this"]
        # Delete the unsent typo; edit the first note.
        item.locator(".annotate-answer-note", has_text="Typo").locator(".annotate-note-delete-btn").click()
        page.wait_for_function("() => !document.querySelector('#content-frame').contentDocument.body.textContent.includes('Typo, ignore')")
        item.locator(".annotate-answer-note").first.locator(".annotate-note-edit-btn").click()
        edit = item.locator("textarea.annotate-note-edit")
        assert edit.input_value() == "Change the time to 10:30"
        edit.fill("Change the time to 10:30 and leave the roll-out time blank")
        item.locator(".annotate-note-save").click()
        page.wait_for_function("() => document.querySelector('#content-frame').contentDocument.body.textContent.includes('roll-out time blank')")
        assert item.locator(".annotate-send-state.is-pending").count() == 2
        _send(page)
        page.wait_for_function("() => document.querySelector('#content-frame').contentDocument.querySelectorAll('.annotate-send-state.is-pending').length === 0")
        answer = next(a for a in _round_answers(directory) if a["comment_id"] == "question-11")
        assert "roll-out time blank" in answer["text"] and "Send the reminder at 8:30AM" in answer["text"]
        assert "Typo" not in answer["text"]
        # A note added after Send goes with the next one, alone.
        item.locator(".annotate-add-note textarea").fill("One more thing: tell QA")
        item.locator(".annotate-note-add").click()
        page.wait_for_function("() => document.querySelector('#content-frame').contentDocument.querySelectorAll('.annotate-send-state.is-pending').length === 1")
        _send(page)
        for _ in range(50):
            later = [a for a in _round_answers(directory) if a["comment_id"] == "question-11"]
            if later and later[0]["text"] == "One more thing: tell QA":
                break
            page.wait_for_timeout(100)
        assert later[0]["text"] == "One more thing: tell QA"


def test_changing_the_choice_keeps_the_notes(tmp_path):
    directory = _directory(tmp_path)
    with _session(tmp_path, directory) as (page, base, _):
        item = page.frame_locator("#content-frame").locator('[data-strip-item="question-11"]')
        item.locator("textarea").fill("After the demo")
        item.locator(".annotate-decision-btns button").first.click()  # Ship now, with a note
        item.locator(".annotate-answer-change").click()
        assert "Your notes stay" in item.inner_text()
        # Changing keeps every way to answer, words included (2026-10-31).
        assert item.locator(".annotate-decision-btns button", has_text="Answer in words").count() == 1
        item.locator("textarea.annotate-decision-cmt").fill("Tell QA first")
        item.locator(".annotate-decision-btns button", has_text="Ship later").click()
        page.wait_for_function("() => document.querySelector('#content-frame').contentDocument.querySelector('.annotate-answer-choice')?.textContent === 'Ship later'")
        assert _stored(directory, "question-11")["decision"]["text"] == "Ship later\n\nAfter the demo\n\nTell QA first"


def test_the_send_summary_uses_the_screen(tmp_path):
    directory = _directory(tmp_path)
    with _session(tmp_path, directory) as (page, base, _):
        page.locator('#comment-list [data-decision-say-ta="question-11"]').fill("Ship now")
        page.locator("#send-btn").click()
        box = page.locator("#round-confirm").bounding_box()
        # The reading list's full 780 px measure (Chang approved send-final, 2026-10-31), not a cramped box.
        assert box["width"] >= 780
        assert box["y"] >= 0 and box["y"] + box["height"] <= page.viewport_size["height"]


def test_delete_an_unsent_comment_but_not_a_sent_one(tmp_path):
    directory = _directory(tmp_path)
    with _session(tmp_path, directory) as (page, base, _):
        page.on("dialog", lambda d: d.accept())
        frame = page.frame_locator("#content-frame")
        for text, where in (("Typed by accident", '[data-anchor-id="s:checks"] h2'), ("Meant this one", '[data-anchor-id="s:checks:p1"]')):
            frame.locator(where).first.click(position={"x": 10, "y": 5})
            page.locator("#pop-ta").fill(text)
            page.locator("#pop-save").click()
            _card(page, text).wait_for()
        card = _card(page, "Typed by accident")
        card.locator('[data-action="menu"]').click()
        card.locator('[data-action="delete"]').click()
        page.wait_for_function("() => !document.querySelector('#comment-list').textContent.includes('Typed by accident')")
        texts = [c["text"] for items in json.loads((directory / "comments.json").read_text())["anchors"].values() for c in items]
        assert "Typed by accident" not in texts and "Meant this one" in texts
        _send(page)
        card = _card(page, "Meant this one")
        playwright.expect(card.locator(".send-state")).to_have_text("In inbox · owner delivery pending")
        card.locator('[data-action="menu"]').click()
        assert card.locator('[data-action="delete"]').count() == 0
        assert card.locator('[data-action="edit"]').count() == 1
