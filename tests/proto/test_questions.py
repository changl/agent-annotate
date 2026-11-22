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


def test_task_blocking_topic_and_page_counts(tmp_path, monkeypatch):
    """Round 12 #03 #07 #12 #14 #15 #16: the tracking table names a task, Blocked items marks it,
    same-topic answers show, and the tiles, section ages and carried notes come with the data."""
    monkeypatch.setattr(questions, "BOARD", str(tmp_path / "no-board"))
    page = tmp_path / "page"
    (page / "versions").mkdir(parents=True)
    same = '<section data-anchor-id="s:old"><h2>Old</h2><p data-anchor-id="s:old:p">Same text</p></section>'
    (page / "versions" / "v1.html").write_text(same)
    (page / "versions" / "v2.html").write_text(
        same + '<section data-anchor-id="s:blocked-items"><h2>Blocked</h2><table><tr><td><a href="#d:q7">#7</a></td>'
        '<td>FLD-abc1 blocked</td></tr></table></section>')
    ev = [{"anchor": "s:blocked-items:firebase", "label": "Firebase"}]
    q7 = _q("c7", 7, "v2", "Switch off the Firebase CLI login that leaked?")
    q7["decision_request"]["evidence"] = ev
    anchors = {
        "d:q6": [_q("c6", 6, "v1", "Should the Firebase CLI login stay?", decision={"verdict": "select", "text": "Off", "ts": "2026-11-01"})],
        "d:q7": [q7],
        "s:old:p": [{"id": "n9", "version": "v1", "anchor_id": "s:old:p", "author": "member", "text": "old note", "status": "open"}],
    }
    (page / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": anchors, "archived": {}}))
    (page / "current.meta.json").write_text(json.dumps({"current": "v2", "history": [{"version": "v1"}, {"version": "v2"}]}))
    (page / "rounds.ndjson").write_text('{"a":1}\n{"a":2}\n')
    d = questions.build(page)
    q = d["questions"][0]
    assert q["bead"] == "FLD-abc1" and q["blocking"]
    assert [e["a"] for e in q["earlier"]] == ["Off"]  # firebase, cli, login in common
    assert d["done"] == 1 and d["tiles"] == {"versions": 2, "open": 1, "addressed": 0, "sends": 2}
    assert d["since"] == {"s:old": "v1", "s:blocked-items": ""}
    assert [(c["id"], c["changed"]) for c in d["carried"]] == [("n9", False)]


def test_carry_loose_table_pictures(tmp_path):
    """Round 12 second pass #01: a picture the agent named in a table cell is copied in from its run folder,
    and the data lists it so the card shows it instead of a "not on this page" chip."""
    page, run = tmp_path / "page", tmp_path / "roots" / "run_1"
    (page / "versions").mkdir(parents=True)
    (page / "versions" / "v2.html").write_text(
        "<td>![](../../../reports/b5/pictures/drawn/a.png)</td><td>![](../../../reports/b5/pictures/built/a.png)</td>"
        "<td>![](../../../reports/../../escape.png)</td>")
    (run / "reports/b5/pictures/drawn").mkdir(parents=True)
    (run / "reports/b5/pictures/drawn/a.png").write_bytes(b"png")
    got = questions.carry_pictures(page, [str(tmp_path / "roots")])
    assert got["reports/b5/pictures/drawn/a.png"] and got["reports/b5/pictures/built/a.png"] is None
    assert (page / "assets/carried/reports/b5/pictures/drawn/a.png").read_bytes() == b"png"
    assert not (tmp_path / "escape.png").exists() and "reports/../../escape.png" not in got  # never writes outside the copy
    assert questions.carried_pictures(page) == ["reports/b5/pictures/drawn/a.png"]


def test_second_note_keeps_the_first():
    """Round 12 second pass #02: opening another note saves the unfinished one first (no JS runner here)."""
    s = (questions.Path(questions.__file__).resolve().parents[1] / "web/proto/questions.js").read_text()
    assert "else if (was && !was.edit && text.trim()) await addNote(text);" in s
    assert "S.note = {anchor: anchorEl.dataset.anchorId" not in s  # every opener goes through openNote


def test_copy_writes_are_simulated():
    """Round 12 third pass: on a read-only copy every write (Send, notes, Later, Close-undo, other tabs' notes)
    is answered in memory and none reaches the server (no JS runner here)."""
    web = questions.Path(questions.__file__).resolve().parents[1] / "web/proto"
    s, f = (web / "questions.js").read_text(), (web / "frame.js").read_text()
    assert "const write = body !== undefined || !!method;" in f
    assert "if (COPY && write && P.copyWrite) { wroteAt = Date.now(); const r = P.copyWrite(path, body, method); wrote(path, own); return r; }" in f
    assert f.index("P.copyWrite(path") < f.index("fetch(base")  # the hook runs before any request
    fake = s[s.index("function fake("):s.index("P.copyWrite = fake;")]
    assert "fetch(" not in fake and "ctx.api" not in fake and "call(" not in fake
    for act in ("answer-later", "restore", "archive", "decision", "reply", "'DELETE'", "'PUT'", "api/rounds/submit"):
        assert act in fake, act
    assert "throw" not in fake  # an unknown write (Reference's plan topics) is answered too, never "not found"
    assert "f.copyOf" in s  # the README contract: frame.json copyOf marks a copy


def test_third_check_fixes_stay():
    """Round 12 audit3 (no JS runner here): Close cannot join an answer; the copy's marker, floating Send and receipt."""
    web = questions.Path(questions.__file__).resolve().parents[1] / "web/proto"
    s, f, c = (web / "questions.js").read_text(), (web / "frame.js").read_text(), (web / "questions.css").read_text()
    # questions 01: an answered card offers no Close, and a stale close draft never joins its answer in Send
    assert "${done ? '' : ibw('archive', 'Close'" in s
    assert "const isClosing = q => !q.closed && !isDraft(q) && !!draft(q.id).close;" in s
    # questions 02 / reference 05: the frame marks every undoable or just-written toast on a copy
    assert "const mark = opts.inert || (COPY && (opts.undo || Date.now() - wroteAt < 3000));" in f
    # frame 03: a copy floats Send like FastLane Drive; Questions' bar Send stays hidden on the phone
    assert "!COPY && S.menu !== 'nav'" not in f and ".qcopy" not in c
    # frame 04: the receipt counts every item it sent
    assert "Sent ${pl(got, 'item', 'items')}" in s


def test_seventh_check_fixes_stay():
    """Round 12 audit7 questions 2-6 (no JS runner here)."""
    s = (questions.Path(questions.__file__).resolve().parents[1] / "web/proto/questions.js").read_text()
    # 2: asking for a task keeps the reply it replaced, and either Undo puts it back
    assert "setDraft(id, on ? {reply: ASKFILE, askWas: was, replyOpen: null} : {reply: was, askWas: null});" in s
    assert "undo: () => { setDraft(id, {reply: was, askWas: null}); draw(true); }" in s
    # 3: the note still being typed is listed, counted, removable and carried by Send
    assert "const tn = typingNote(); if (tn) it.push(['Notes'" in s and "'nn:', 'newnote:'" in s
    assert "kind === 'newnote'" in s and s.index("const tn = typingNote();  // the note still open") < s.rindex("call('api/rounds/submit'")
    # 4: Go to it beside a Close lands on its receipt
    assert "'c:' + q.id, 'close:' + q.id" in s and "at === 'close' ? c.querySelector('.qstate')" in s
    # 5 and 6: Open the board beside the request, and the mock's wording
    assert "data-board title=" in s and "ctx.go('running', 'tasks')" in s
    assert "'Please file a task on the board for this question and link it on the card.'" in s


def test_eighth_check_fixes_stay():
    """Round 12 audit8 questions 1-5 (no JS runner here; the browser replays are in round12/fix10/questions)."""
    s = (questions.Path(questions.__file__).resolve().parents[1] / "web/proto/questions.js").read_text()
    # 1: an edit to a saved note is kept as a draft: typed words stored, shown in the editor and Send, carried by Send
    assert "S.note.text = t.value; ctx.prefs.set('q:newnote', S.note); }  // an edit to a saved note" in s
    assert "esc(editText(n))" in s and "esc(cut(NK.say({...n, text: editText(n)}), 140))" in s
    assert s.index("en = ed && ed.edit") < s.rindex("call('api/rounds/submit'")
    assert "S.note = next;\n    ctx.prefs.set('q:newnote', next);" in s
    # 2: Go to it beside a note typed in a card's evidence opens the filter that lists the card
    assert "const nq = nn && nn.inq && qOf(nn.inq);" in s and "reveal(nq)" in s
    # 3: Cards only gives every open card its fold chevron
    assert "(done || S.view === 'list') && !inList ? `<button class=\"qfold\"" in s
    # 4: an evidence jump leaves Back to Q N
    assert "backPill(el, ds.evq)" in s and "if (ds.back)" in s
    # 5: a card inside its evidence section shows only the blocks above its own spot
    assert "spot = el && el.tagName === 'SECTION' && spotOf(el, q)" in s


def test_mask_covers_company_and_keeps_images():
    assert questions._mask("a@b.com support@fastlanedrive.com x@2x.png") == "member@example.com member@example.com x@2x.png"
