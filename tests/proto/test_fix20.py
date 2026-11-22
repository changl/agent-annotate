"""Fix20 (r12 audit18): the notes kit holds the one armed Move for every tab, and Escape, a picture viewer opening or
closing, leaving the tab and another Move end it there; a pin's list uses its pin's picture key; read-only version
readers and kept-document revisions key each picture by its place; an inline cell-picture note saves under its own key;
a small picture never grows past its own width in a viewer."""

from test_fix18_notes import HIST, KIT, L, Q, REF, STUBS, WEB, node

QCSS = (WEB / "questions.css").read_text()
DOCSTUB = ("const toastEl = {textContent: 'Click the new spot for this note in the document · Esc cancels', innerHTML: 'x'};\n"
           "const document = {querySelectorAll: () => [], getElementById: () => toastEl};\n")


def test_one_move_for_every_tab_and_endmove_ends_it(tmp_path):
    """Frame 1, 2: each tab's S.move is the kit's one slot; another Move replaces it; endMove clears it and redraws its tab."""
    node(tmp_path, DOCSTUB + STUBS + KIT + """
const q = {}, r = {}, h = {}, drawn = [];
NK.slot(q, 'questions'); NK.slot(r, 'reference'); NK.slot(h, 'history', 'cmove');
P.noteHooks.reference = {redo: () => drawn.push('reference')};
r.move = 'n1'; assert.strictEqual(r.move, 'n1'); assert.strictEqual(q.move, '');
r.move = 'n2'; assert.strictEqual(r.move, 'n2');           // another Move on the same tab replaces it
q.move = 'n3'; assert.strictEqual(r.move, ''); assert.strictEqual(q.move, 'n3');  // or on another tab
q.move = null; assert.strictEqual(NK.mv, null);
r.move = 'n4'; q.move = '';  assert.strictEqual(r.move, 'n4');  // clearing one tab never ends another's
assert.strictEqual(NK.endMove(), true); assert.strictEqual(r.move, ''); assert.deepStrictEqual(drawn, ['reference']);
assert.strictEqual(toastEl.innerHTML, '');                    // the Move hint goes with it
toastEl.textContent = 'Note saved'; toastEl.innerHTML = 'x'; r.move = 'n5'; NK.endMove(false);
assert.strictEqual(toastEl.innerHTML, 'x');                   // any other toast stays
assert.strictEqual(NK.endMove(), false);                     // nothing armed: no redraw
h.cmove = 'c1'; NK.endMove(false); assert.strictEqual(h.cmove, ''); assert.deepStrictEqual(drawn, ['reference']);
""")


def test_a_render_never_ends_its_own_tabs_move(tmp_path):
    """Fix20 follow-up: a tab re-renders after his Move click (route() on a newer version or a retry); its slot() call keeps
    that Move, and only ends one armed on another tab."""
    node(tmp_path, DOCSTUB + STUBS + KIT + """
const r = {}, l = {};
NK.slot(r, 'reference'); r.move = 'n1';
NK.slot(r, 'reference'); assert.strictEqual(r.move, 'n1');   // the same tab rendering again keeps it
NK.slot(l, 'links'); assert.strictEqual(r.move, ''); assert.strictEqual(NK.mv, null);  // another tab's render ends it
""")


def test_every_cancel_path_reaches_endmove():
    """Escape and leaving the tab (kit), the viewer opening or closing on each surface, all through NK.endMove."""
    assert "addEventListener('keydown', e => { if (e.key === 'Escape') NK.endMove(); }, true);" in Q
    assert "addEventListener('hashchange', () => { NK.endMove(false); });" in Q
    assert "if (!!S.zoom !== !!S.zWas) { S.zWas = !!S.zoom; NK.endMove(false); }" in Q  # Questions viewer: any open or close
    assert "if (!!S.full !== !!S.fWas) { S.fWas = !!S.full; NK().endMove(false); }" in REF  # Reference viewer
    # Proto.media.view: opening (not a redraw of the open viewer, which keeps a Move begun in it) and closing
    assert Q.count("if (!v) NK.endMove();") == 1 and "v.remove(); NK.endMove();" in Q
    assert "P.notes.endMove();  // opening or closing" in HIST and "dlg.remove(); P.notes.endMove();" in HIST  # read-only readers
    assert "P.notes.slot(S, 'links')" in L and "P.notes.slot(S, 'history', 'cmove')" in HIST and "NK().slot(S, 'reference')" in REF


def test_pin_list_uses_the_pins_picture_key(tmp_path):
    """Questions 2: an old note on picture 1 and a keyed one at the same spot on picture 2 list apart."""
    node(tmp_path, DOCSTUB + STUBS + KIT + """
const old = {id: 'o', target: {image: 'IMG1', offset: {dx: .5, dy: .5}}}, nu = {id: 'n', target: {image: 'IMG1', pk: 'r~p2', offset: {dx: .5, dy: .5}}};
const pk = n => n.target.pk || 'r~p1';  // the old note is drawn on the first picture
assert.deepStrictEqual(NK.near([old, nu], old, pk).map(n => n.id), ['o']);
assert.deepStrictEqual(NK.near([old, nu], nu, pk).map(n => n.id), ['n']);
assert.deepStrictEqual(NK.near([old, nu], nu).map(n => n.id), ['o', 'n']);  // by file alone they would merge
""")
    assert "NK.near(all, p, pinPk)" in Q and "pinPk(n) === pk" in Q


def test_read_only_readers_and_revisions_key_pictures_by_place():
    """Frame 3 and Reference 5: no picture size keyed by its file; a kept revision's pictures name the revision."""
    assert "img.getAttribute('src') || '').split('?')[0]" not in HIST
    assert "doc.location.pathname + doc.location.search + '|' + P.media.pk(" in HIST  # and its version (r12 fix23)
    assert "q:zoomPer" not in Q and "const zoomOf = k => M.zoom(k);" in Q
    assert "docK += '~rev' + (cur + 1);" in L


def test_inline_cell_picture_note_saves_under_its_key():
    """Reference 1: a cell picture is its own note line, so a click on it saves under its Proto.media.pk key."""
    assert "` data-pk=\"${esc(pk)}\" ${at(pk, 'Picture: ' + (p[2] || ''))}`" in REF


def test_viewer_pictures_stop_at_their_own_width():
    """Questions 4: Questions' and Proto.media's viewers cap a picture at its natural width, as Reference does."""
    assert ".qzpic:not(.qzdgm){max-width:fit-content}" in QCSS and ".mview .pic{display:block;max-width:fit-content;" in QCSS
