"""Questions tab data: this version's questions in order, earlier answers, closed vs withdrawn, notes, masking."""

import json

from agent_annotate.proto_data import questions


def _q(cid, n, version, prompt, **extra):
    return {"id": cid, "number": n, "version": version, "anchor_id": f"d:q{n}", "author": "agent:x", "status": "open",
            "text": prompt, "decision_request": {"prompt": prompt, "context": "", "options": [{"id": "a", "label": "A"}]}, **extra}


def _page(tmp_path, monkeypatch):
    monkeypatch.setattr(questions, "BOARD", str(tmp_path / "no-board"))  # never the live board
    page = tmp_path / "page"
    (page / "versions").mkdir(parents=True)
    (page / "versions" / "v2.html").write_text("<div class=aa>Doc</div>")
    anchors = {
        "d:q1": [_q("c1", 1, "v1", "Ship it?", decision={"verdict": "select", "text": "Yes ship", "option_id": "a", "ts": "2026-11-01T00:00:00Z"})],
        "d:q3": [_q("c3", 3, "v2", "Ship it?", replies=[{"author": "member", "text": "mail me at someone@gmail.com", "sent_at": None}])],
        "d:q2": [_q("c2", 2, "v2", "Who drives?", decision={"verdict": "select", "option_id": "a", "ts": "x", "round_pending": True})],
        "s:p1": [{"id": "n1", "version": "v2", "anchor_id": "s:p1", "author": "member", "text": "my note", "status": "open"}],
    }
    archived = {
        "d:q4": [_q("c4", 4, "v2", "Closed by me", status="archived", archived_by="member")],
        "d:q5": [_q("c5", 5, "v2", "Withdrawn", status="archived", archived_by="agent:x")],
    }
    (page / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": anchors, "archived": archived}))
    (page / "current.meta.json").write_text(json.dumps({"current": "v2", "history": []}))
    return page


def test_build(tmp_path, monkeypatch):
    d = questions.build(_page(tmp_path, monkeypatch))
    assert d["version"] == "v2"
    assert [q["n"] for q in d["questions"]] == [2, 3, 4]  # agent-withdrawn one skipped, older version skipped
    q2, q3, q4 = d["questions"]
    assert not q2["sent"] and q2["decision"]["round_pending"]  # a pick not yet sent
    assert q3["earlier"] and q3["earlier"][0]["a"] == "Yes ship"  # same words, earlier version
    assert q3["replies"][0]["text"] == "mail me at member@example.com" and not q3["replies"][0]["sent"]
    assert q4["closed"]
    assert [n["id"] for n in d["notes"]] == ["n1"]
    assert d["beads"] == {}


def test_mask_covers_company_and_keeps_images():
    assert questions._mask("a@b.com support@fastlanedrive.com x@2x.png") == "member@example.com member@example.com x@2x.png"
