"""r12 audit38 running 1-2: the notes kit's methods are distinct, and every text reader marks a saved quote."""
import re

from test_fix13_send import Q, REF
from test_fix43_send import LINKS


def test_notes_kit_has_no_duplicate_keys():
    # a second key of one name replaced the first: a text selection called the picture-point method and threw (running 1)
    kit = Q[Q.index("const NK = P.notes = {"):]
    kit = kit[:kit.index("\n  };")]
    keys = re.findall(r"^    (?:async )?([A-Za-z_$][\w$]*)(?:\s*:|\()", kit, re.M)
    dup = {k for k in keys if keys.count(k) > 1}
    assert not dup, dup
    assert "textAt" in keys and "pointAt" in keys and "at" not in keys
    for src in (Q, REF, LINKS):
        assert not re.search(r"(NK|NK\(\)|P\.notes)\.at\(", src)


def test_open_edit_base_is_the_last_written_words():
    # frame 4: History's editor copy can hold the delivered words after Send wrote the replacement; typing the delivered words
    # back must be a change from what the store now holds, so the open Edit stays one row that puts the store back
    assert "const L = NK.loc()[eid], base = L && L.text != null ? L.text : n ? n.text : '';" in Q
    assert "text: t.value, was: base, sent: !!(n && n.sent) || !!L}" in Q


def test_every_text_reader_marks_a_saved_quote():
    # Questions, the Reference plan and Pages & links (kept documents and folder files) all use the kit's one mark (running 2)
    assert "NK.mark(el, t.quote, t.at)" in Q
    assert "NK().mark(le, t.quote, t.at)" in REF
    assert "P.notes.mark(le, t.quote, t.at)" in LINKS
