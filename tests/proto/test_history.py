"""History data: past answers by version, one "overruled" tag, withdrawn questions, plan revisions, no emails."""

import json

from agent_annotate.proto_data import history


def _page(tmp_path):
    page = tmp_path / "page"
    (page / "plans" / "roadmap").mkdir(parents=True)
    (page / "plans" / "archive-2026-11-01").mkdir(parents=True)
    (page / "current.meta.json").write_text(json.dumps({"current": "v3", "history": [
        {"version": "v1", "ts": "2026-11-01T10:00:00Z", "label": "First"},
        {"version": "v2", "ts": "2026-11-02T10:00:00Z", "label": "Second, for someone@corp.com"}]}))
    comments = [
        {"id": "c1", "version": "v1", "status": "open", "author": "agent:claude", "text": "q1",
         "decision_request": {"prompt": "Ship it?"}, "replies": [{"author": "agent:claude", "text": "This was superseded by the new plan."}]},
        {"id": "c2", "version": "v2", "status": "resolved", "author": "agent:claude", "text": "q2",
         "decision": {"verdict": "select", "catalog_conflict": {"plan": "x"}}},
        {"id": "c3", "version": "v2", "status": "open", "author": "agent:claude", "text": "q3",
         "withdrawn": {"reason": "not asked again", "ts": "2026-11-02T11:00:00Z", "decision_request": {"prompt": "Old question?"}}},
        # one question asked in v1, carried to v3 and waiting; one answered in v3; one left for later
        {"id": "c4", "version": "v1", "status": "open", "author": "agent:claude", "number": 7, "decision_request": {"prompt": "Who drives?"}},
        {"id": "c5", "version": "v3", "status": "open", "author": "agent:claude", "number": 7, "origin_id": "c4", "decision_request": {"prompt": "Who drives?"}},
        {"id": "c6", "version": "v3", "status": "open", "author": "agent:claude", "number": 8, "decision_request": {"prompt": "Done?"},
         "decision": {"verdict": "select", "text": "Yes"}},
        {"id": "c7", "version": "v3", "status": "open", "author": "agent:claude", "number": 9, "decision_request": {"prompt": "Later?"}, "answer_later": True},
    ]
    (page / "comments.json").write_text(json.dumps({"anchors": {"a": comments}, "archived": {}}))
    rounds = [
        {"id": "r1", "ts": "2026-11-01T12:00:00Z", "version": "v1", "by": "me@gmail.com", "answers": [
            {"comment_id": "c1", "number": 101, "prompt": "Ship it?", "text": "Yes\nmore words", "ts": "2026-11-01T11:59:00Z"},
            {"comment_id": "c1", "number": 101, "prompt": "Ship it?", "text": "Yes"}]},
        {"id": "r2", "ts": "2026-11-02T12:00:00Z", "version": "v2", "answers": [
            {"comment_id": "c2", "number": 102, "prompt": "Pick?", "verdict": "select", "text": "B, mail me@gmail.com"}]},
    ]
    (page / "rounds.ndjson").write_text("\n".join(json.dumps(r) for r in rounds) + '\n{"id": "cut sho')
    (page / "plans" / "roadmap" / "meta.json").write_text(json.dumps({"title": "Roadmap", "history": [
        {"version": "v1", "ts": "2026-11-01T00:00:00Z", "label": "start"}, {"version": "v2", "ts": "2026-11-03T00:00:00Z"}]}))
    (page / "plans" / "archive-2026-11-01" / "meta.json").write_text(json.dumps({"title": "Old", "history": [{"version": "v1"}]}))
    return page


def test_history_record(tmp_path):
    d = history.build(_page(tmp_path))
    assert d["count"] == 3 and d["sends"] == 2  # the cut-short last line is skipped
    assert [a["v"] for a in d["answers"]] == ["v2", "v1"]  # newest first; the repeat in one Send listed once
    newest, oldest = d["answers"]
    assert newest["ovr"][0] == "overruled" and oldest["ovr"][0] == "superseded"
    assert oldest["a"] == "Yes" and oldest["n"] == 101
    assert d["versions"]["v2"] == {"t": "2026-11-02", "note": "Second, for member@example.com", "items": 2, "open": 1}
    # an older version jumps to each question waiting now: only c5, first asked in v1 (finding 10)
    assert d["waiting"] == [{"id": "c5", "n": 7, "q": "Who drives?", "from": "v1", "in": ["v1", "v3"]}]
    assert d["withdrawn"] == [{"n": 0, "v": "v2", "t": "2026-11-02", "q": "Old question?", "why": "not asked again"}]
    assert [p["id"] for p in d["plans"]] == ["roadmap"] and len(d["plans"][0]["revs"]) == 2
    text = json.dumps(d)
    assert "gmail" not in text and "corp.com" not in text


def test_overruled_words():
    said = lambda t: history.overruled({"replies": [{"author": "agent:x", "text": t}]})
    assert said("Your pick was overridden by the release.")[0] == "overridden"
    assert said("Done. Replaced by the newer card.")[0] == "replaced"
    assert said("Nothing changed here.") is None
    assert history.overruled({"replies": [{"author": "me@x.com", "text": "superseded"}]}) is None  # only the agent's words count
