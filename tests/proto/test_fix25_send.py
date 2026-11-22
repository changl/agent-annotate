"""Fix25 send: a re-opened note is a pending edit Send lists without Remove, it yields to the store after another client's
Send, and a saved row from an earlier build offers no Remove until a read confirms it (r12 audit21 frame 1-2, running 2, questions 1-2)."""

from test_fix17_notes import KIT, Q, STUBS, node


def test_reopened_row_has_no_remove_and_discard_leaves_it():
    i = Q.index("if (P.queue) P.queue({items: c => Object.entries(NK.reo(c))")
    assert "remove:" not in Q[i:Q.index("\n  // A read-only copy", i)]
    assert "x.remove ? 'x:' + x.key : ''" in Q and "sendItems().filter(x => x[3])" in Q and "x.remove && x.remove()" in Q


def test_reopen_yields_to_the_store_after_another_send(tmp_path):
    node(tmp_path, STUBS.replace("const P = {};", "const P = {ctx: null}; global.location = {pathname: '/'};") + KIT + """
(async () => {
  P.ctx = c; c.refreshTop = () => {};
  const n = {id: 'r', sent: true, status: 'resolved_in_version', text: 't', anchor: 's:a'};
  await NK.set(c, n, 'reopen', api, async () => {});
  NK.out({id: 'r', sent: true, edited: false, status: 'open', replies: []});  // a read begun before the Re-open: this visit keeps it
  assert(NK.reo(c).r);
  store['draft:reopen'].r.vis = 'earlier';  // a reload
  NK.out({id: 'r', sent: true, edited: true, status: 'open', replies: []});  // still pending in the store
  assert(NK.reo(c).r);
  NK.put(c, 'r', {...NK.reo(c).r, text: 'moved'});  // a rewrite keeps its visit
  assert.strictEqual(NK.reo(c).r.vis, 'earlier');
  NK.out({id: 'r', sent: true, edited: false, status: 'open', replies: []});  // another client's Send took it
  assert(!NK.reo(c).r);
})().catch(e => { console.error(e); process.exit(1); });
""")


def test_saved_row_from_an_earlier_build_waits_for_the_read(tmp_path):
    node(tmp_path, STUBS.replace("const P = {};", "const P = {ctx: null};") + KIT + """
const old = {id: 'p', text: 'peer', sent: false, edited: false, replies: []};  // an earlier build's row: no author, no rm
assert(!NK.rowRm(old));
assert(!NK.rowRm({...old, rm: true}));  // its own "can remove" alone is not trusted
assert(NK.rowRm({...old, rm: true, by: true}));  // a confirmed read wrote both
const mine = {id: 'm', text: 'mine', status: 'open', by: true, sent: false, edited: false, replies: []};
assert(NK.rowRm(mine) && NK.rowRm({id: 'm', text: 'mine', ...NK.state(mine)}));
assert(!NK.rowRm({id: 'o', text: 'o', ...NK.state({...mine, by: 'other@x'})}));
assert(NK.rowRm({id: 'w', text: 'written this visit'}));  // a note written in this visit, not a saved row
""")
