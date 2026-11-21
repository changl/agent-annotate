"""Read-only copies follow their real page (audit5 questions #02), and the fifth check's Questions fixes stay."""

import json
import time
from pathlib import Path

from agent_annotate.proto_data import copies

WEB = Path(copies.__file__).resolve().parents[1] / "web/proto"


def _real(d: Path, version: str, mail: str) -> Path:
    (d / "versions").mkdir(parents=True, exist_ok=True)
    (d / "versions" / f"{version}.html").write_text(f"<p>{version} by {mail}</p>")
    (d / "comments.json").write_text(json.dumps({"anchors": {"a": [{"id": "c1", "text": f"ask {mail}"}]}}))
    (d / "current.meta.json").write_text(json.dumps({"current": version, "owner": {"agent": "x"}}))
    return d


def test_copy_follows_its_real_page(tmp_path):
    real = _real(tmp_path / "real", "v1", "someone@gmail.com")
    root = tmp_path / "root"
    copy = copies.refresh(root, "rebex", "Rebex", real)
    meta = json.loads((copy / "current.meta.json").read_text())
    assert meta["current"] == "v1" and meta["proto_copy_of"] == "rebex" and "owner" not in meta
    assert "someone@gmail.com" not in (copy / "comments.json").read_text()  # masked
    assert not copies.fresh(copy)  # same version: nothing to do
    (copy / "versions" / "v1.html").write_text("<p>kept scrubbed v1</p>")
    _real(real, "v2", "someone@gmail.com")
    t = time.monotonic()
    assert copies.fresh(copy) == "v2" and time.monotonic() - t < 1  # the real page moved on: copied behind, no read waits
    assert json.loads((copy / "current.meta.json").read_text())["current"] == "v1"  # the copy serves its own version meanwhile
    assert copies.fresh(copy) == "v2" and copies.build(copy) == {"copying": "v2", "current": "v1"}  # one copy at a time, and the frame is told
    for _ in range(600):
        if not copies._busy:
            break
        time.sleep(0.1)
    assert copies.fresh(copy) == ""  # the copy is current: Reload turns blue on the minute's check
    assert json.loads((copy / "current.meta.json").read_text())["current"] == "v2"
    assert (copy / "versions" / "v1.html").read_text() == "<p>kept scrubbed v1</p>"  # a published version is reused, not scrubbed again
    assert "someone@gmail.com" not in (copy / "versions" / "v2.html").read_text()
    assert json.loads((real / "current.meta.json").read_text()).get("owner")  # the real page is never written
    assert any(p.name.startswith("proto-rebex-") for p in (root / "trash").iterdir())  # the old copy went to trash


def test_copy_meta_route_starts_the_copy():
    s = (WEB.parent.parent / "proto_data/__init__.py").read_text()
    assert "_COPY_META" in s and "fresh(" in s and "_bound.pop" in Path(copies.__file__).read_text()


def test_fifth_check_questions_fixes():
    s, c = (WEB / "questions.js").read_text(), (WEB / "questions.css").read_text()
    assert "el.onmouseover = onHover" in s and ".evh" in c  # #06: a card lights its evidence on hover
    assert "t.closest('.qevb')" in s and "S.note.inq" in s  # #03: Cards only evidence takes a note under its line
    assert "topSecs(DOC).find(s => s.contains(at))" in s  # #04: Go to it opens the note's folded section


def test_copy_rounds_take_their_real_delivery_state(tmp_path):
    """audit6 questions #03: a round the agent read says so on the copy, from the real delivery record (read only)."""
    live = tmp_path / "deliveries"
    (live / "rebex").mkdir(parents=True)
    (live / "rebex" / "rebex.json").write_text(json.dumps({"deliveries": {"r1": {"id": "r1", "state": "acknowledged"}}}))
    d = tmp_path / "copy"
    d.mkdir()
    (d / "rounds.ndjson").write_text(json.dumps({"id": "r1", "ts": "t", "delivery": "queued"}) + "\n" + json.dumps({"id": "r2", "ts": "t", "delivery": "queued"}) + "\n")
    copies._deliveries(d, "rebex", live)
    rows = [json.loads(x) for x in (d / "rounds.ndjson").read_text().splitlines()]
    assert [r["delivery"] for r in rows] == ["acknowledged", "queued"]
    assert json.loads((live / "rebex" / "rebex.json").read_text())["deliveries"]["r1"]["state"] == "acknowledged"


def test_sixth_check_send_fixes():
    s, c, f = (WEB / "questions.js").read_text(), (WEB / "questions.css").read_text(), (WEB / "frame.js").read_text()
    # questions #02, frame #02: Go to it picks a filter that lists the card, and opens its folded section from another tab
    assert "['need', 'later', 'ready', 'wait', 'arch'].find(k => FILTERS[k](q))" in s and "if (q0 && S.view === 'doc')" in s
    assert "'r:' + q.id" in s and "showAt(id, at)" in s  # a reply's Go to it opens the card at the reply
    # questions #04: a today-and-proposed picture takes a pick that joins Answers in Send, with Undo
    assert "Pick ${s === 'current' ? 'today\\'s' : 'the proposed'}" in s and "data-unab" in s and "Object.keys(abPicks()).length" in s
    assert '[data-anchor-id^="cmp:"]' in s and "^(current|today|before)" in s  # the page's Current/Proposed blocks and Before/After pairs
    assert "ctx.refreshChips();  // a Remove or Undo over another tab" in s  # the Questions chip follows a Remove over Running
    assert "padding:60px 16px" in c and "max-height:calc(100vh - 90px)" in c  # questions #05: the phone's inset summary
    assert "body.qsheet-open .p-toastwrap{z-index:45}" in c  # frame #01: Undo over the sheet
    assert "data-snone" in s  # frame #06
    # running #04, frame #03: a newer version repaints the waiting badges on every tab
    assert "sendP.newer()" in f and "refreshTop(); toast('Loaded the newer version')" in f and "newer: () => { stale = true;" in s
