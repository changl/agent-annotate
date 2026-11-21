"""Eighth check: counts with their version, drafts listed before their tab's data, the receipt chip and the phone Send (r12 fix10)."""

from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / "src" / "agent_annotate" / "web" / "proto"
FRAME = (WEB / "frame.js").read_text()
REF = (WEB / "reference.js").read_text()
RUN = (WEB / "running.js").read_text()
LINKS = (WEB / "links.js").read_text()
Q = (WEB / "questions.js").read_text()
FCSS = (WEB / "frame.css").read_text()
QCSS = (WEB / "questions.css").read_text()


def test_reference_lists_saved_drafts_without_its_data():
    """Frame 1, reference 2: a slow or failed reference.json read never holds a saved draft or note out of Send."""
    items = REF[REF.index("items: c => {"):REF.index("sent: () =>")]
    assert "if (!D) return [];" not in items
    assert "ctx = ctx || c; restoreDrafts();" in items
    assert "LBL = s.lbl || {}; SNOTES = s.notes || [];" in REF and "lbl: LBL, notes: SNOTES" in REF
    assert "for (const n of SNOTES) it.push(" in items


def test_running_and_links_list_saved_drafts_without_their_data():
    assert "return []; }" not in RUN[RUN.index("P.queue && P.queue({"):RUN.index("sent: ctx =>")]
    assert "ctx.prefs.keys(/^tcm:/)" in RUN and "keys(re) {" in FRAME
    assert "LD ? LD.notes || [] : c.prefs.get('draft:lnotes', [])" in LINKS


def test_go_to_waits_for_reference_data():
    """Reference 1: Go to it pressed before the data is in reaches the copy line once it is."""
    assert "if (D) reach(a); else S.reach = a;" in REF and "if (S.reach) { reach(S.reach); S.reach = ''; }" in REF


def test_counts_paint_with_their_version():
    """Running 2, frame 1: Send, waiting and the Questions chip are read together, and set with the version."""
    start = FRAME[FRAME.index("async function start()"):]
    assert start.index("putCounts(await Promise.race([readCounts()") < start.index("S.meta = meta; S.loadedV = meta && meta.current;") < start.index("route();")
    rc = FRAME[FRAME.index("if (S.newer) {"):FRAME.index("checkNewer().then(found")]
    assert "readCounts()]).then(([m, c]) =>" in rc and "putCounts(c);" in rc
    assert rc.index("putCounts(c);") < rc.index("toast('Loaded the newer version')")
    assert "if (S.settling) return;" in FRAME


def test_receipt_chip_and_open_summary():
    """Frame 4 and reference 2: the chip repaints with the receipt; an open summary follows the count."""
    assert "S.sentPaint = true;" in FRAME and "if (S.sentPaint) { S.sentPaint = false; drawTop();" in FRAME
    assert "if (sendP.changed) sendP.changed();" in FRAME and "changed: async () =>" in Q


def test_phone_send_undo_and_hint():
    """Frame 2 and 5: no notice over the countdown; the hint wraps between words, keycaps whole."""
    assert "body:has(.qsend.sending) .p-toastwrap{display:none}" in FCSS
    assert "white-space:nowrap;overflow-wrap:normal" in FCSS
    hint = QCSS[QCSS.index(".qsendkey{"):]
    assert "display:flex" not in hint[:hint.index("}")]
