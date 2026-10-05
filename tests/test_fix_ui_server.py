"""Fix-UI server parts: Discard puts a sent answer back (UI-14); a changed option names the option it replaces (UI-15)."""

from test_decision_api import _call, _card, _store
from test_decision_api import server as server

from agent_annotate.review_history import review_history

REVIEWER = "reviewer@example.com"


def _decide(httpd, cid, verdict, text=None, defer=True):
    body = {"verdict": verdict, "defer_push": defer}
    if text is not None:
        body["text"] = text
    return _call(httpd, "POST", f"/api/comments/{cid}/decision", body, author=REVIEWER)


def test_ui14_discarding_a_changed_answer_shows_the_sent_answer_again(server):
    httpd, slug_dir, _ = server
    _, card = _call(httpd, "POST", "/api/comments", _card())
    _decide(httpd, card["id"], "select", "Park the store check")
    assert _call(httpd, "POST", "/api/rounds/submit", {}, author=REVIEWER)[0] == 200
    _decide(httpd, card["id"], "select", "One more attempt")
    replies = len(_store(slug_dir)["anchors"]["s:a"][0]["replies"])
    status, result = _call(httpd, "POST", "/api/rounds/discard", {}, author=REVIEWER)
    assert status == 200 and result["comment_ids"] == [card["id"]]
    stored = _store(slug_dir)["anchors"]["s:a"][0]
    assert stored["decision"]["text"] == "Park the store check"
    assert "round_pending" not in stored["decision"]
    # The discarded answer stays in the history, marked, and its unsent reply is gone.
    assert stored["decision_history"][-1]["text"] == "One more attempt"
    assert stored["decision_history"][-1]["discarded"] is True
    assert len(stored["replies"]) == replies - 1
    assert not any("One more attempt" in r["text"] for r in stored["replies"])
    # Nothing goes out with the next Send, and History lists only the sent answer.
    assert _call(httpd, "POST", "/api/rounds/submit", {}, author=REVIEWER)[1]["delivery"] == "noop"
    answers = [a["text"] for v in review_history(slug_dir)["versions"] for a in v["answers"]]
    assert "One more attempt" not in answers


def test_ui14_a_first_answer_that_was_never_sent_stays_recorded(server):
    httpd, slug_dir, _ = server
    _, card = _call(httpd, "POST", "/api/comments", _card())
    _decide(httpd, card["id"], "accept")
    _call(httpd, "POST", "/api/rounds/discard", {}, author=REVIEWER)
    stored = _store(slug_dir)["anchors"]["s:a"][0]
    assert stored["decision"]["verdict"] == "accept" and "round_pending" not in stored["decision"]


def test_ui15_changing_an_option_names_the_earlier_option(server):
    httpd, slug_dir, _ = server
    _, card = _call(httpd, "POST", "/api/comments", _card())
    _decide(httpd, card["id"], "select", "One more round\n\nTry the other supplier")
    _decide(httpd, card["id"], "select", "Park it")
    reply = _store(slug_dir)["anchors"]["s:a"][0]["replies"][-1]["text"]
    assert reply.endswith("(revised verdict; was ☑ One more round)"), reply
    assert "☑ Selected)" not in reply
