"""r12 audit39 running 1-2, frame 1: a second spot never loses a failed Save's words or the next composer's focus."""
from test_fix13_send import Q, REF
from test_fix43_send import LINKS


def test_a_failed_save_keeps_its_words_at_their_own_spot():
    # running 1: with another note typed, a rejected Save's words were dropped (one typed slot). They are a draft at their own
    # spot now: listed in Send with Save and Remove, back in that spot's composer; a composer opened over typed words keeps them too
    assert "backs: {all: (c, k) => c.prefs.get(k, []), at: (c, k, a, tgt) => NK.backs.all(c, k).find(x => NK.same(x, a, tgt))," in Q
    for src, kit, bk, row in ((LINKS, "P.notes", "'draft:lback'", "'lnb:'"), (REF, "NK()", "'draft:rback'", "'rnb:'")):
        assert f"const BK = {bk};" in src
        assert f"else if (!{kit}.same(now, d.a, d.tgt)) {kit}.backs.put(" in src  # putBack
        assert "putBack(" in src[src.index("} catch (er) {", src.index("data") if src is LINKS else 0):]
        assert f"{kit}.backs.drop(" in src and f"{kit}.backs.at(ctx, BK, k, S.tgt)" in src
        assert f"key: {row} + " in src and "spot: " in src
    # Send's round marks a kept draft's note as made, so its own Save past the check is the same note
    assert "if ((m || x.spot) && x.save && listed.keys.has('x:' + x.key)) mark({anchor_id: x.spot || nn[m[1]](m[2])" in Q


def test_a_redraw_keeps_the_composer_focus():
    # running 2: an earlier note's save redrew Pages & links and the next composer lost its focus; Reference's draw kept it
    assert "const a = document.activeElement, keep = a && a.id && w.contains(a) ? [a.id, a.selectionStart, a.selectionEnd] : null;" in LINKS
    assert "if (b && b !== document.activeElement) { b.focus({preventScroll: true});" in LINKS


def test_a_line_label_reads_only_a_pictures_caption():
    # frame 1: a table row's live label quoted "Picture 1 ·" and the dots; the reloaded one reads the cells' words only
    assert "filter(n => !n.parentElement.closest('.qcap') || n.parentElement.closest('.qcapt'))" in Q
