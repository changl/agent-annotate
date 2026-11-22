/* Prototype Questions tab: the review document, whole, with each question's card at its evidence; and Cards only.
   Picks, words, replies and Close are drafts in this browser until Send; Send posts them through today's endpoints
   (decision, reply, archive, rounds/submit) after a short Undo window. Notes and Later save at once and undo
   through today's calls (DELETE, answer-later off). The sandboxed server delivers nothing. */
(function () {
  'use strict';
  const P = window.Proto;
  const SEND_DELAY = 6000;
  const S = {open: new Set(), shut: new Set(), view: null, filter: 'need', armed: false, sendKey: false, pending: null, note: null, copied: null,
    hl: null, vy: {}, gen: false, zoom: null, sdef: new Map(), sdefV: null, drawGen: 0};
  let D = null, ctx = null, root = null, DOC = null, REF = null;

  /* ---------- helpers ---------- */
  const esc = s => P.ctx.esc(s);
  const ic = (k, l) => P.icon(k, l);
  const cut = (s, n) => (s = String(s || '')).length <= n ? s : s.slice(0, n).replace(/[\s,:;]+\S*$/, '') + '…';
  const pl = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  const drafts = () => ctx.prefs.get('q:drafts', {});
  const draft = id => drafts()[id] || {};
  function setDraft(id, patch) {
    const all = drafts(), w = Object.assign({}, all[id], patch), d = {...w}, q = D && D.questions.find(x => x.id === id);
    for (const k of ['p', 'pl', 'n']) delete d[k];
    for (const k of Object.keys(d)) if (d[k] === '' || d[k] == null || d[k] === false) delete d[k];
    // p: its question's words, so a browser reload onto a version that re-asks it under a new id finds it again (carry);
    // n and pl: its number and the picked choice's words, so Send names it before the questions are read (r12 audit11 frame 1)
    if (Object.keys(d).length) all[id] = {...d, p: q ? q.prompt : w.p, n: q ? q.n : w.n, ...(d.pick ? {pl: q ? optLabel(q, d.pick) : w.pl} : {})}; else delete all[id];
    ctx.prefs.set('q:drafts', all);
  }
  async function who() {
    if (who.q != null) return who.q;
    try { const i = await ctx.api.identity(); who.q = i && i.email ? '?author=' + encodeURIComponent(i.name && i.name !== i.email ? `${i.name} <${i.email}>` : i.email) : ''; } catch { who.q = ''; }
    return who.q;
  }
  const call = async (path, body, method) => ctx.api(path + await who(), body, method);
  const ibw = (k, word, label, attrs) => `<button class="ib ibw" title="${esc(label)}" aria-label="${esc(label)}" ${attrs}>${ic(k)}<span class="ibt">${word}</span></button>`;
  const ib = (k, label, attrs) => `<button class="ib sm" title="${esc(label)}" aria-label="${esc(label)}" ${attrs}>${ic(k)}</button>`;
  const ASKFILE = 'Please file a task on the board for this question and link it on the card.';
  const gen = () => ctx.prefs.get('q:general', '');
  /* ---------- one note lifecycle for every tab: Questions, Reference and Pages & links call these (r12 fix17) ---------- */
  // Re-open on a note the agent addressed goes with the next Send as its own row: a draft (id → its status) until Send writes it,
  // (the store says open at once, as today; the row tells the agent with the next Send)
  const stOf = n => n.status !== undefined ? n.status : n.st;
  const VISIT = Date.now().toString(36) + Math.random().toString(36).slice(2, 6);  // this page load, for the kit's kept edits
  const AGENT_ST =['addressed_by_agent', 'resolved_in_version'];  // statuses only the agent may set (sync_server's comment PUT)
  const NK = P.notes = {
    resolved: n => ['resolved_in_version', 'addressed_by_agent', 'user_confirmed'].includes(stOf(n)),
    // the one draft store for every tab's Re-open: id → the note's record (status, spot, words, tab), so Send lists it
    // from the record alone, before any tab's feed answers (r12 audit16 frame 1)
    // an earlier build kept the status alone (id → status): it becomes a record as the store loads, so Send counts it at once,
    // and learns its spot and words from the first feed that has the note (r12 audit17 frame 5)
    reo(c) {
      const m = c.prefs.get('draft:reopen', {}), old = Object.keys(m).filter(id => typeof m[id] === 'string');
      if (!old.length) return m;
      for (const id of old) m[id] = {st: m[id], a: '', tab: '', text: '', on: '', vis: 'old'};
      c.prefs.set('draft:reopen', m);
      if (c.data) old.forEach(id => NK.find(c, id).then(() => c.refreshTop && c.refreshTop()));  // fill in the spot and words once a read answers
      return m;
    },
    // a record without its spot: its note from whichever feed answers first, kept into the record
    find: (c, id) => Promise.any(['questions', 'reference', 'links'].map(a => c.data(a).then(d => {
      const n = ((d || {}).notes || []).find(x => x.id === id); if (!n) throw 0; return n; })))
      .then(n => { const r = NK.reo(c)[id]; if (!r) return null; const x = {...NK.rec(n), st: r.st || stOf(n)}; NK.put(c, id, x); return x; }, () => null),
    isReo(c, n) {
      const m = NK.reo(c);  // sent or not: today's Re-open on a review note doesn't wait for a Send (r12 audit20 questions 3)
      if (n.closed) { if (n.id in m) NK.put(c, n.id, null); return false; }  // a Close an earlier build left queued
      if (m[n.id] && !m[n.id].a) NK.put(c, n.id, {...NK.rec(n), st: m[n.id].st || stOf(n)});
      return n.id in m;
    },
    tabOf: a => /^doc:/.test(a) ? 'links' : /^(ref|chk):/.test(a) ? 'reference' : /^chart:/.test(a) ? 'history' : 'questions',
    rec: n => { const a = n.anchor || n.a || '', t = n.target || {};
      return {st: stOf(n), a, tab: NK.tabOf(a), text: n.text || '', on: t.quote || n.line || n.label || n.l || '', img: t.tag === 'img'}; },
    // vis: the visit that re-opened it, kept through every rewrite of its record, so settle() can tell an earlier visit's (r12 audit21 frame 2)
    put(c, id, r) { const m = NK.reo(c); if (r) m[id] = {...r, vis: r.vis || (m[id] && m[id].vis) || VISIT}; else delete m[id]; c.prefs.set('draft:reopen', m); },
    setReo(c, n, on) { NK.put(c, n.id, on ? NK.rec(n) : null); },
    // each tab tells the kit how to show a note and redraw (go(record), redo(), res(note) for a resolution on that tab);
    // P.noteHooks, since the tabs' scripts load in any order
    hooks: P.noteHooks = P.noteHooks || {},
    redo: tab => { const h = NK.hooks[tab]; if (h && h.redo) h.redo(); },
    // his edits and replies on sent notes since the last Send, by note id ({text, replies}): the one record every tab's Send row
    // reads, so no copy of the note a tab holds (a first read, a re-read behind it, a saved row) can lose them (r12 audit19 frame 1, 4, running 1)
    // Each entry names the visit that made it (vis). One from an earlier visit yields to the store: a feed read in this visit that
    // shows the note sent with no pending edit or reply means a Send took it, here or from another client (r12 audit20 frame 1).
    // One from this visit stays, since a read begun before his edit can still answer after it
    loc: () => NK.L || (NK.L = (P.ctx && P.ctx.prefs.get('draft:nkput', {})) || {}),
    put1(id, p) { const m = NK.loc(), o = m[id] || {replies: []}; m[id] = {...o, ...p, replies: [...o.replies, ...(p.replies || [])], vis: VISIT}; if (P.ctx) P.ctx.prefs.set('draft:nkput', m); },
    // a feed's note (it has a status; saved Send rows do not), on a page whose store is real (a copy's feed doesn't hold its replies)
    // A Re-open from an earlier visit follows the same rule: its status PUT is an edit the store counts until a Send takes it
    settle(n) { const m = NK.loc(), l = m[n.id], c = P.ctx, r = c && NK.reo(c)[n.id];
      if ((!l || l.vis === VISIT) && (!r || r.vis === VISIT) || stOf(n) === undefined || /\/proto\/p\/[a-z0-9-]+\//.test(location.pathname)) return;
      if (!n.sent || n.edited || (n.replies || []).some(x => x.unsent)) return;
      if (l && l.vis !== VISIT) { delete m[n.id]; if (c) c.prefs.set('draft:nkput', m); }
      if (r && r.vis !== VISIT) { NK.put(c, n.id, null); setTimeout(() => { NK.redo('questions'); if (r.tab && r.tab !== 'questions') NK.redo(r.tab); c.refreshTop && c.refreshTop(); }); } },
    // goes with the next Send: never sent, or his edit or reply since (today's needs-push rule counts edited_at and reply times)
    // a re-opened one is listed once, as the kit's Re-open row: its status PUT reads as an edit in the feed, never a second row (r12 audit22 running 2)
    reoQ: n => { const r = P.ctx && NK.reo(P.ctx)[n.id]; return !!r && typeof r === 'object'; },
    out: n => { NK.settle(n); return !NK.reoQ(n) && (!n.sent || !!n.edited || (n.replies || []).some(r => r.unsent) || n.id in NK.loc()); },
    // a Send took it, with its edit and replies; another reviewer's stays pending, as the server leaves it (r12 audit22 frame 2)
    gone: n => { if (!NK.own(n)) return; Object.assign(n, {sent: true, edited: false, flagged: true}); (n.replies || []).forEach(r => { r.unsent = false; });
      if (n.id in NK.loc()) { delete NK.L[n.id]; if (P.ctx) P.ctx.prefs.set('draft:nkput', NK.L); } },
    // what a saved Send row keeps of a note, so it lists and offers Remove as the loaded one does before any read is in
    // rm: whether its row offers Remove (rowRm), as the loaded note decides it, since the row keeps no author or replies
    // by: his own as the kit decides it (own), so a note written on a copy, which carries no `by`, keeps Remove (r12 audit22 reference 4)
    state: n => ({sent: !!n.sent, edited: !!n.edited, replies: (n.replies || []).filter(r => r.unsent).map(r => ({text: r.text, unsent: true})), rm: NK.rowRm(n), by: NK.own(n)}),
    // his own note (today's isMine): the feed marks his own `by: true` for each reader; one written in this visit has no `by`
    own: n => n.by === true || (n.by == null && n.mine !== false),
    // today's canDeleteComment: his own, not flagged for the session (an edit clears it), no replies, no response, no pending round
    removable: n => NK.own(n) && !(n.flagged != null ? n.flagged : n.sent && !n.edited) && !(n.replies || []).length && !n.resp && !n.rp,
    // its Send row's words, as today's summary (commentRow): a posted reply as "Reply" with its words, else the note's words.
    // A sent note's row has no Remove: the server refuses to delete a sent note, and today's row offers none
    say: n => { const l = NK.loc()[n.id] || {replies: []}, r = [...new Set([...(n.replies || []).filter(x => x.unsent).map(x => x.text), ...l.replies.map(x => x.text)])];
      return r.length ? 'Reply: ' + r.join(' · ') : l.text != null ? l.text : n.text; },
    // its row keeps no Remove once sent: from the loaded note, its saved row or his edit or reply on it
    kept: n => !!n.sent || n.id in NK.loc(),
    // Send's Remove on a note row, on every tab: never once kept, and only where the note's own Remove shows (canDeleteComment),
    // so another reviewer's draft or one the agent replied to lists with no Remove, as today (r12 audit20 questions 2, running 2)
    // A saved row (sent state, no status) offers it only when a read confirmed both his authorship and Remove; an earlier
    // build's row has neither, so it waits for the read (r12 audit21 running 2, questions 1)
    rowRm: n => !NK.kept(n) && (stOf(n) === undefined && 'edited' in n ? n.rm === true && n.by === true : NK.removable(n)),
    // today's edit body (shell.js edit-save): the words, and a closed status re-opens, so the agent reads it again
    body: (n, text) => stOf(n) && stOf(n) !== 'open' ? {text, status: 'open'} : {text},
    // Close stores what today's menu offers for this note (cardMenuItems): Resolve (accept) on a review note, a confirmed or
    // resolved one; Archive on any other. Restore undoes either (r12 fix22)
    resolves: n => ['user_confirmed', 'resolved_in_version'].includes(stOf(n)) || (stOf(n) === 'open' && !!(n.replies || []).length && n.replies[n.replies.length - 1].agent),
    // the words after a sent note: edited, re-opened, resolved, addressed or sent
    words: (c, n) => n.edited ? `<span class="saved">· edited · goes with Send</span>` : NK.isReo(c, n) ? `<span class="saved">· re-opened · goes with Send</span>`
      : NK.resolved(n) ? `<span class="saved">· ${ic('tick')} ${stOf(n) === 'resolved_in_version' ? `resolved${n.rv ? ' in ' + esc(String(n.rv).replace(/^v/, 'version ')) : ''}` : 'addressed by the agent'}</span>` : '<span class="mut">· sent</span>',
    view: n => NK.resolved(n) && n.rv && n.ra ? `<button class="lk small" data-nres="${esc(n.id)}">${ic('eye')} View resolution in ${esc(String(n.rv).replace(/^v/, 'version '))}</button>` : '',
    // every note's actions on every tab, today's menu (shell.js cardMenuItems): Edit on his own (canEditComment), Remove while
    // the server would delete it (canDeleteComment), Move (Re-pin), Re-open beside Close where today offers Resolve, and one
    // Close for Resolve or Archive (#138); a closed one has Re-open (Restore). before: the tab's own; del: the tab's Remove
    acts: (c, n, moving, before, del = 'nundo') => { if (n.closed) return NK.closedActs(n);
      const id = esc(n.id);
      return (before || '') + (NK.own(n) ? ibw('edit', 'Edit', n.sent ? 'Edit this note; the change goes with your next Send' : 'Edit this note', `data-nedit="${id}"`) : '')
        + (NK.removable(n) ? ibw('undo', 'Remove', 'Undo: remove this note', `data-${del}="${id}"`) : '')
        // Move only on a note saved on its page's current version, as today's Re-pin (n.old: an earlier one) (r12 audit24 running 1)
        + (n.old ? '' : ibw('place', moving ? 'Moving' : 'Move', moving ? 'Click a new spot in the document; Esc cancels' : 'Move this note to another spot', `data-nmove="${id}" aria-pressed="${!!moving}"`))
        + (NK.resolves(n) && !NK.isReo(c, n) ? ibw('rerun', 'Re-open', 'Re-open: the agent looks at it again with your next Send', `data-nreopen="${id}"`) : '')
        + ibw('archive', 'Close', 'Close this note: nothing more to do. Undo until you leave', `data-nclose="${id}"`); },
    closedActs: n => ibw('rerun', 'Re-open', 'Re-open this note', `data-nopen="${esc(n.id)}"`),
    // Close and a closed note's Re-open: today's archive and restore; Re-open on a resolved one: a draft Send writes; each with Undo (#138, catalog 64)
    async set(c, n, how, api, redraw, quiet) {
      const u = `api/comments/${encodeURIComponent(n.id)}`, was = how === 'close' ? NK.reo(c)[n.id] : null;
      // Re-open stores open at once, as today's PUT {status: open}, and keeps its Send row, so the agent reads it with the next
      // Send (r12 audit20 frame 4). Its Undo puts back the status it had; the server lets only the agent set an agent-only one
      let prev = null;
      if (how === 'reopen' || how === 'unreopen') {
        const r = NK.reo(c)[n.id]; prev = how === 'reopen' ? stOf(n) : r && r.st;
        const to = how === 'reopen' ? 'open' : prev, rec = how === 'reopen' ? NK.rec(n) : null;
        if (to && to !== stOf(n)) {
          try { await api(u, {status: to}, 'PUT'); } catch (e) { c.toast('Not changed: ' + e.message); return null; }
          n['status' in n ? 'status' : 'st'] = to;
        }
        NK.put(c, n.id, rec);
      } else {
        try { await api(u + (how === 'close' ? (NK.resolves(n) ? '/accept' : '/archive') : '/restore'), {}); } catch (e) { c.toast('Not changed: ' + e.message); return null; }
        n.closed = how === 'close';
        if (was) NK.put(c, n.id, null);  // Close ends a pending Re-open: nothing goes with Send; its Undo brings it back (r12 audit17 frame 1)
      }
      await redraw(n.id);
      const back = {close: 'restore', restore: 'close', reopen: 'unreopen', unreopen: 'reopen'}[how],
        undo = async () => { const r = await NK.set(c, n, back, api, redraw, true); if (r && was) { NK.put(c, n.id, was); await redraw(n.id); } return r; };
      const can = !(how === 'reopen' && AGENT_ST.includes(prev));
      if (!quiet) c.toast({close: 'Note closed: it is under Closed', restore: 'Note re-opened', reopen: 'Note re-opened: it goes with your next Send', unreopen: 'Re-open taken back'}[how], can ? {undo} : {});
      return can ? undo : async () => null;
    },
    // Move: today's manual re-pin to the spot he clicks next, with Undo (catalog 65); apply(p) shows it (p null: it failed)
    async move(c, id, from, to, api, apply) {
      const put = async (p, again) => {
        await api(`api/comments/${encodeURIComponent(id)}`, {...p, reanchor: {strategy: 'manual-repin', confidence: 1.0, ts: new Date().toISOString()}}, 'PUT');
        const r = NK.reo(c)[id];  // a re-opened note's Send row and Go to it follow it to its new spot
        if (r) NK.put(c, id, {...NK.rec({anchor: p.anchor_id, label: p.anchor_label, target: p.target, text: r.text}), st: r.st});
        await apply(p);
        if (again) c.toast('Note moved', {undo: () => put(from, false)});
      };
      try { await put(to, true); } catch (e) { c.toast('Not moved: ' + e.message); await apply(null); }
    },
    // the one armed Move, on any tab ({tab, id}): each tab's S.move (History's S.cmove) reads and sets it, so another Move
    // replaces it; Escape, a picture viewer opening or closing, and leaving the tab end it through endMove (r12 audit18 frame 1, 2)
    mv: null,
    // a tab calls it on every render: it ends only a Move from another tab, never one armed here, since a render can come
    // after his click (route() re-renders on a newer version, a retry, a late read) (r12 fix20 follow-up)
    slot(S, tab, key = 'move') { if (NK.mv && NK.mv.tab !== tab) NK.endMove(false);
      Object.defineProperty(S, key, {configurable: true, get: () => (NK.mv && NK.mv.tab === tab && NK.mv.id) || '',
      // a Move ended by the tab itself (a second Move press, View resolution, its new spot) takes its hint too (r12 audit19 questions 9)
      set: id => { if (id) NK.mv = {tab, id}; else if (NK.mv && NK.mv.tab === tab) { NK.mv = null; NK.unhint(); } }}); },
    unhint() { const t = document.getElementById('p-toast'); if (t && /· Esc cancels$/.test(t.textContent)) t.innerHTML = ''; },  // the Move hint no longer applies
    endMove(redraw = true) {
      const w = NK.mv; if (!w) return false;
      NK.mv = null;
      document.querySelectorAll('[data-nmove][aria-pressed="true"]').forEach(b => b.setAttribute('aria-pressed', 'false'));  // before any later Escape handler reads it
      NK.unhint();
      if (redraw) NK.redo(w.tab);
      return true;
    },
    // Send's row for a re-opened note: its number, what it is on and its words
    row: (n, no, on) => `${mk(no)}Re-opened · ${on}${n.text ? ': ' + esc(cut(n.text, 140)) : ''}`,
    // every note at one marker, with Go to it on each and + Comment for another (today's pin popover, catalog 25)
    spot: (c, ns, kind, add) => `<div class="qspot" role="dialog" aria-label="Notes at this marker"><div class="qspoth"><b class="small">${pl(ns.length, 'note', 'notes')} ${kind}</b><span class="spacer"></span><button class="btn sm pri" ${add}>${ic('plus')} Comment</button><button class="ib sm" data-spotx title="Close this list" aria-label="Close this list" data-esc>${ic('x')}</button></div>
      <ul class="qhist">${ns.map(([n, no]) => `<li>${mk(no, n.sent || n.closed)} ${esc(cut(n.text, 160))} <span class="small mut">· ${n.closed ? 'closed' : NK.isReo(c, n) ? 're-opened · goes with Send' : NK.resolved(n) ? 'addressed' : n.sent ? 'sent' : 'goes with Send'}</span> <button class="lk small" data-spotgo="${esc(n.id)}">Go to it</button></li>`).join('')}</ul></div>`,
    // View resolution in another version: History opens it at the resolution, scrolled to and lit, as today's page does (r12 audit15 questions 3)
    // a resolution on a Reference or Pages & links line opens that line there, outlined (the tab's res hook)
    // the shared picture viewer closes first, so the outlined destination is in sight, as Reference's does (r12 audit19 running 3, reference 3)
    goRes: (c, n) => { if (document.getElementById('p-mview')) P.media.closeView();
      const t = NK.tabOf(n.ra || ''), h = NK.hooks[t]; return t !== 'questions' && h && h.res ? h.res(n) : c.go('history', `${n.rv}~${n.ra}`); },
    // the resolution's spot, outlined where View resolution lands (History's version reader, a Reference plan line)
    lit: e => { e.style.cssText += ';outline:3px solid #7c3aed;outline-offset:4px;border-radius:4px;background:color-mix(in oklab,#7c3aed 16%,transparent)'; e.setAttribute('data-resolution', ''); },
    // the notes at a picture pin: on the same picture (by `pic`, the key its pin is drawn under), within a few percent of its point
    near: (ns, p, pic = n => n.target.image || '') => { const o = (p.target || {}).offset; return o ? ns.filter(n => { const t = (n.target || {}).offset; return t && pic(n) === pic(p) && Math.hypot(t.dx - o.dx, t.dy - o.dy) < 0.04; }) : [p]; },
    // one colour rule for every marker, line or picture: purple while a note on it goes with Send, muted once all are sent (catalog 24)
    sent: ns => ns.length > 0 && ns.every(n => !NK.out(n) && !NK.reoQ(n) || n.closed),
    // a picture's point markers, numbered, each listing the notes at its point; `tgt` the point a new note is being written at
    pins: (ns, open, tgt) => ns.filter(n => n.target && n.target.offset && !n.closed).map((n, i) => `<button class="qpin pinm${NK.sent([n]) ? ' sent' : ''}" data-pin="${esc(n.id)}" style="left:${n.target.offset.dx * 100}%;top:${n.target.offset.dy * 100}%" aria-expanded="${open === n.id}" title="The notes at this point" aria-label="Note at spot ${i + 1}: the notes at this point">${i + 1}</button>`).join('')
      + (tgt && tgt.offset ? `<span class="qpin pinm new" style="left:${tgt.offset.dx * 100}%;top:${tgt.offset.dy * 100}%">+</span>` : ''),
    // where a tap fell on a picture, as a point note's target
    at: (e, im) => { const r = im.getBoundingClientRect(); return {schema: 1, tag: 'img', offset: {dx: +((e.clientX - r.left) / r.width).toFixed(3), dy: +((e.clientY - r.top) / r.height).toFixed(3)}}; },
    // a saved, unsent note: Edit opens its words in place, Remove takes it back, as today's release (r12 audit18 reference 4)
    // and Move and Close too, as today's menu (r12 audit19 questions 6, reference 7): the one list above
    draftActs: (n, moving) => NK.acts(P.ctx, n, moving),
    editBox: n => `<div class="nkedit" data-nedbox="${esc(n.id)}"><textarea data-nedtext rows="3" aria-label="Edit your note">${esc(n.text)}</textarea><div class="acts"><button class="btn sm pri" data-nedsave="${esc(n.id)}">Save</button><button class="lk small" data-nedcancel>Cancel</button><span class="small mut"><kbd>⌘↵</kbd> saves</span></div></div>`,
    // Save on an edit: today's PUT of its words, so the note keeps its id, number and time and Send lists the new words; with Undo.
    // a sent one (today's edit on a sent note) goes with the next Send again: edited, and re-opened if closed by status.
    // apply(t, p) puts the words (p: every changed field) on the tab's copies and redraws; false when nothing was saved
    async fix(c, n, text, api, apply) {
      const was = n.text, t = String(text || '').trim();
      if (!t) { c.toast(n.sent ? 'Write something first' : 'Write something first, or Remove the note'); return false; }
      // the same words still PUT: today's Save records an edit, so a sent note goes with the next Send (r12 audit19 reference 11).
      // The PUT clears flagged_for_session, so his own with no replies or response can be removed again, as today
      const put = async w => { const b = NK.body(n, w); await api(`api/comments/${encodeURIComponent(n.id)}`, b, 'PUT');
        if (n.sent) NK.put1(n.id, {text: w});
        await apply(w, {...b, ...(n.sent ? {edited: true} : {}), flagged: false}); };
      try { await put(t); } catch (e) { c.toast('Not changed: ' + e.message); return false; }
      c.toast('Note changed · goes with Send', {undo: () => put(was)});
      return true;
    },
    // a sent note's body on any tab: its words, state, View resolution, actions and thread; the edit box (edit: its words) while Edit is open
    sentBody: (c, n, moving, edit) => edit != null ? NK.editBox({...n, text: edit})
      : `${esc(n.text)} ${NK.words(c, n)} ${NK.view(n)}<span class="nacts">${NK.acts(c, n, moving)}</span>${NK.thread(c, n)}`,
    // the agent's response and the replies under a note, the latest shown and older ones behind "n earlier replies"; a
    // reply box with Post reply once the agent has answered and the note is not closed (today's renderCItem, showReply)
    th: new Map(), earlier: new Set(), typed: new Map(),  // typed: a reply being written, kept across a redraw of its tab
    thread(c, n) {
      const rs = n.replies || [], k = rs.length - 1, id = esc(n.id);
      // a note the agent wrote has its reply box from the start (agentResponded: the agent is its author) (r12 audit19 questions 8)
      if (!n.resp && !rs.length && !n.ag) return '';
      NK.th.set(n.id, n);
      const one = r => `<div class="nkrep${r.agent ? ' ag' : ''}"><b class="small">${esc(r.who || (r.agent ? 'Agent' : 'You'))}</b> <span class="small mut">${esc(String(r.ts || '').slice(0, 16).replace('T', ' '))}</span><div>${esc(r.text)}</div></div>`;
      const open = NK.earlier.has(n.id), box = !n.closed && (!!n.resp || !!n.ag || rs.some(r => r.agent));
      return `<div class="nkth" data-nth="${id}">${n.resp ? `<div class="nkrep ag"><b class="small">Agent response</b><div>${esc(n.resp)}</div></div>` : ''}`
        + (k > 0 ? `<button class="lk small" data-nearlier="${id}" aria-expanded="${open}">${ic('chev')} ${k} earlier repl${k === 1 ? 'y' : 'ies'}</button>${open ? rs.slice(0, -1).map(one).join('') : ''}` : '')
        + (rs.length ? one(rs[k]) : '')
        + (box ? `<div class="nkreply"><textarea data-nreplytext="${id}" rows="2" placeholder="Add a reply…" aria-label="Reply to the agent">${esc(NK.typed.get(n.id) || '')}</textarea><button class="btn sm" data-nreply="${id}">Post reply</button></div>` : '') + '</div>';
    },
    // Post reply: today's route (POST …/reply); the server re-opens the note and the reply goes with the next Send
    async reply(c, n, text, redraw) {
      const t = String(text || '').trim();
      if (!t) return false;
      try { await c.api(`api/comments/${encodeURIComponent(n.id)}/reply`, {text: t}); } catch (e) { c.toast('Not posted: ' + e.message); return false; }
      NK.typed.delete(n.id);
      (n.replies = n.replies || []).push({agent: false, who: 'You', text: t, ts: new Date().toISOString(), unsent: true});
      NK.put1(n.id, {replies: [{text: t}]});
      if (stOf(n) && stOf(n) !== 'open') n.status = 'open';
      redraw();
      c.toast('Reply posted · it goes with your next Send');
      return true;
    },
  };
  // the thread's buttons on any tab: one handler, ahead of each tab's own, for the note the thread was drawn from
  document.addEventListener('click', e => {
    const b = e.target.closest && e.target.closest('[data-nreply],[data-nearlier]');
    if (!b) return;
    e.stopPropagation(); e.preventDefault();
    const id = b.dataset.nreply || b.dataset.nearlier, n = NK.th.get(id), tab = n && NK.tabOf(n.anchor || n.a || '');
    if (!n) return;
    if (b.dataset.nearlier) { NK.earlier.has(id) ? NK.earlier.delete(id) : NK.earlier.add(id); return NK.redo(tab); }
    const ta = b.closest('[data-nth]').querySelector('textarea');
    if (!ta.value.trim()) return ta.focus();
    b.disabled = true;
    NK.reply(P.ctx, n, ta.value, () => NK.redo(tab)).then(ok => { if (!ok) b.disabled = false; });
  }, true);
  document.addEventListener('input', e => { const id = e.target.dataset && e.target.dataset.nreplytext; if (id) NK.typed.set(id, e.target.value); }, true);
  // Remove or Close on the note being moved ends its Move on every tab, before the tab's own handler (r12 audit19 questions 2)
  document.addEventListener('click', e => { const b = e.target.closest && e.target.closest('[data-ndel],[data-nundo],[data-nclose]');
    if (b && NK.mv && NK.mv.id === (b.dataset.ndel || b.dataset.nundo || b.dataset.nclose)) NK.endMove(false); }, true);
  NK.slot(S, 'questions');
  // Escape and any navigation (another tab, or another place in this one) end a Move on every tab; the router's own
  // rewrites use replaceState, which fires no hashchange
  addEventListener('keydown', e => { if (e.key === 'Escape') NK.endMove(); }, true);
  addEventListener('hashchange', () => { NK.endMove(false); });
  // ⌘↵ in an open edit saves it, on any tab
  document.addEventListener('keydown', e => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && e.target.matches && e.target.matches('[data-nedtext]')) {
    const b = e.target.closest('[data-nedbox]').querySelector('[data-nedsave]'); e.preventDefault(); e.stopPropagation(); b.click(); } }, true);
  // every re-opened note, on any tab, is one Send row listed from its stored record
  const TABN = {questions: 'Questions', reference: 'Reference', links: 'Pages & links', history: 'Questions asked per version'};
  if (P.queue) P.queue({items: c => Object.entries(NK.reo(c)).filter(([, r]) => r && typeof r === 'object').map(([id, r]) => ({key: 'reo:' + id, group: 'Notes', note: id,
    html: NK.row(r, '↻', r.img && !r.on ? 'At a spot on a picture' : r.on || r.tab ? `On “${esc(cut(r.on || TABN[r.tab], 50))}”` : 'A note the agent addressed'),
    // a record not yet told its spot (an earlier build's) finds its note first
    // no Remove: Re-open stored open at once, so the note is a pending edit the server keeps, which today's summary lists
    // without Remove and Discard all leaves (r12 audit21 frame 1)
    go: async () => { const x = r.a ? r : (await NK.find(c, id)) || r, h = NK.hooks[x.tab]; if (h && h.go) h.go({id, ...x}); else c.go(x.tab || 'questions'); }}))});
  // A read-only copy (frame.json copyOf) takes no writes: the frame hands every write on a copy here (P.copyWrite), for
  // every tab. It stands in for the server, so it is kept like his drafts (prefs draft:copy): a reload keeps it while
  // "Unsent answers and notes" is on (r12 fix8). Questions shows it through sim(); Reference and Links through P.copyData.
  const SIM = {}, NOTES = {add: [], gone: new Set(), text: {}, sent: new Set()};
  let simN = 0, simIn = false;
  function simLoad() {
    if (simIn || !P.ctx) return;
    simIn = true;
    const s = P.ctx.prefs.get('draft:copy', null);
    if (!s) return;
    Object.assign(SIM, s.sim || {});
    NOTES.add = s.add || []; NOTES.gone = new Set(s.gone || []); NOTES.text = s.text || {}; NOTES.sent = new Set(s.sent || []);
  }
  const simSave = () => P.ctx.prefs.set('draft:copy', {sim: SIM, add: NOTES.add, gone: [...NOTES.gone], text: NOTES.text, sent: [...NOTES.sent]});
  function fake(full, body, method) {
    simLoad();
    const r = fakeWrite(full, body, method);
    simSave();
    return r;
  }
  function fakeWrite(full, body, method) {
    const path = full.split('?')[0], ts = new Date().toISOString();
    const [, id, act] = path.match(/^api\/comments(?:\/([^/]+))?(?:\/([a-z-]+))?$/) || [];
    const nid = id && decodeURIComponent(id), added = NOTES.add.find(n => n.id === nid),
      set = p => { SIM[nid] = {...SIM[nid], ...p, p: ((D && D.questions.find(x => x.id === nid)) || {}).prompt || (SIM[nid] || {}).p}; };
    if (path === 'api/comments') {  // ids stay unique across reloads
      const n = {id: `copy-${Date.now().toString(36)}-${++simN}`, anchor: body.anchor_id, label: body.anchor_label, text: body.text, target: body.target, sent: false, at: ts, version: body.version};
      NOTES.add.push(n);
      return {id: n.id, text: n.text, author_name: 'You', created_at: ts, version: body.version, target: n.target};
    }
    if (act === 'answer-later') set({later: !!body.on});
    else if (act === 'restore') set({closed: false});
    else if (act === 'archive' || act === 'accept') set({closed: true, ...(act === 'accept' ? {accepted: ts} : {})});
    else if (act === 'decision') {  // a changed answer keeps the earlier pick under Decided before, as the server's decision_history does
      const cur = (D && D.questions.find(x => x.id === nid)) || {}, prev = cur.sent && cur.decision;
      set({sent: true, read: false, decision: {...body, ts}, ...(prev ? {earlier: [{v: D.version, t: String(prev.ts || '').slice(0, 10), q: cur.prompt, a: (prev.text || '').split('\n\n')[0], own: true}, ...(cur.earlier || [])]} : {})});
    }
    else if (act === 'reply') { const cur = (D && D.questions.find(x => x.id === nid)) || {}; set({replies: [...(cur.replies || []), {you: true, text: body.text, ts, sent: true}]}); }
    else if (id && !act && method === 'DELETE') { if (added) NOTES.add.splice(NOTES.add.indexOf(added), 1); else NOTES.gone.add(nid); }
    else if (id && !act && method === 'PUT' && body.text != null) { if (added) added.text = body.text; else NOTES.text[nid] = body.text; set({...(body.status ? {status: body.status} : {}), edited: true}); }  // edited: the feed keeps it only on a sent note
    // a note's Re-open (status) or Move (anchor): kept like Close, by the note's id
    else if (id && !act && method === 'PUT') set({...(body.status ? {status: body.status, closed: false} : {}), ...(body.anchor_id ? {anchor: body.anchor_id, label: body.anchor_label, target: body.target} : {})});
    else if (path === 'api/rounds/submit' && D) return submitSim();
    return {ok: true};  // any other write (Reference's plan topics): its tab already changed its own view
  }
  // the copy's round, as the server's: it takes his every unsent note and every edit, re-open or reply on a sent one, from
  // every feed (a release note on Policies is in Reference's alone), never a peer's, and answers their ids (r12 audit24 reference 2)
  async function submitSim() {
    const feeds = await Promise.all(['reference', 'links'].map(a => P.ctx.data(a).then(d => (d && d.notes) || [], () => [])));
    const ids = new Set(Object.keys(NK.reo(P.ctx)));
    for (const n of [D.notes, ...feeds].flat()) if (NK.out(n) && NK.own(n)) ids.add(n.id);
    // and every note the copy saved, from its own store: one put back by Discard's Undo may be missing from D.notes (r12 audit23 frame 3)
    for (const n of NOTES.add) if (!NOTES.sent.has(n.id)) ids.add(n.id);
    for (const [id, s] of Object.entries(SIM)) { if (s.edited) ids.add(id); s.edited = false; }
    ids.forEach(id => NOTES.sent.add(id));
    simSave();
    return {ok: true, comment_ids: [...ids]};
  }
  P.copyWrite = fake;
  // the copy's notes on Reference (ref:, chk:) and Pages & links (doc:), in their feeds' shape, so each tab lists its own after a reload
  const FEED = {reference: /^(ref|chk):/, links: /^doc:/};
  P.copyData = (area, d) => {
    simLoad();
    // the copy's notes join the questions feed for every tab that reads it, so History lists a chart note from any read (r12 audit14 running 1)
    if (area === 'questions') return d && Array.isArray(d.notes) ? simNotes(d) : d;
    if (!FEED[area] || !d || !Array.isArray(d.notes)) return d;
    const have = new Set(d.notes.map(n => n.id));
    // a release note the copy's Send took is sent by its own id, as the feed brings it back (r12 audit24 reference 2)
    d.notes = d.notes.filter(n => !NOTES.gone.has(n.id)).map(n => n.id in NOTES.text ? {...n, text: NOTES.text[n.id]} : n)
      .map(n => NOTES.sent.has(n.id) && !n.sent ? {...n, sent: true, flagged: true} : n)
      .concat(NOTES.add.filter(n => FEED[area].test(n.anchor || '') && !have.has(n.id))
        .map(n => ({id: n.id, a: n.anchor, l: n.label || '', text: n.text, who: 'You', at: n.at || '', v: n.version, target: n.target, sent: !!n.sent || NOTES.sent.has(n.id)})))
      // a note's Close, Re-open and Move on the copy, as Questions shows them (r12 fix17)
      .map(n => { const s = SIM[n.id]; return !s ? n : {...n, ...('status' in s ? {status: s.status} : {}), ...('closed' in s ? {closed: s.closed} : {}), ...(s.edited && n.sent ? {edited: true} : {}), ...(s.anchor ? {a: s.anchor, l: s.label || '', target: s.target} : {})}; });
    return d;
  };
  // a newer version asks the same question again under a new id: his unsent answer and a copy's simulated one move to it (audit5 #02),
  // after a browser reload too, when the old version is no longer in memory: each keeps its question's words (p) (r12 audit7 frame 1, questions 1)
  function carry(old, d) {
    const all = drafts(), ids = new Set(d.questions.map(q => q.id)), was = new Map(((old || {}).questions || []).map(q => [q.id, q.prompt]));
    let moved = false, simMoved = false;
    for (const [box, put] of [[all, () => { moved = true; }], [SIM, () => { simMoved = true; }]]) {
      for (const id of Object.keys(box)) {
        const words = was.get(id) || box[id].p, nq = !ids.has(id) && words && d.questions.find(x => x.prompt === words);
        if (!nq || box[nq.id]) continue;
        box[nq.id] = {...box[id], p: words}; delete box[id]; put();
      }
    }
    if (moved) ctx.prefs.set('q:drafts', all);
    if (simMoved) simSave();
  }
  // a task the board read here missed (slow or failed) takes its title and state from Running's own records (audit9 questions 1)
  const RST = {closed: 'done', 'in progress': 'progress', blocked: 'blocked', deferred: 'none', open: 'waiting'};
  let RB = null;
  const runBeads = d => { if (!RB || !d) return; d.beads = d.beads || {};
    for (const [id, b] of Object.entries(RB)) if (!d.beads[id]) d.beads[id] = {title: b.t || '', status: b.st || '', state: RST[b.st] || 'none'}; };
  const readRun = () => { if (RB || !ctx) return; RB = {};
    ctx.data('running').then(r => { RB = ((r || {}).board || {}).beads || {}; if (!D) return; runBeads(D);
      if (root && root.isConnected && root.classList.contains('tab-questions')) draw(true); }).catch(() => {}); };
  function sim(d) {
    if (!d) return d;
    readRun(); runBeads(d);
    simLoad();
    if (!D || (D !== d && D.version !== d.version)) carry(D, d);
    for (const q of d.questions) if (SIM[q.id]) Object.assign(q, SIM[q.id]);
    simNotes(d);
    if (ctx) keepSaved(d);
    return d;
  }
  const NOTEP = ['closed', 'status', 'anchor', 'label', 'target'];
  function simNotes(d) {
    simLoad();
    const added = new Set(NOTES.add.map(n => n.id));  // the cached data may have been through here already
    d.notes = d.notes.filter(n => !NOTES.gone.has(n.id) && !added.has(n.id)).concat(NOTES.add)
      .filter(n => !(P.ctx && P.ctx.taken(n.id)))  // removed, its Undo still open (frame take)
      .map(n => { const s = SIM[n.id] || {}, o = {...n, text: n.id in NOTES.text ? NOTES.text[n.id] : n.text, sent: n.sent || NOTES.sent.has(n.id)};
        for (const k of NOTEP) if (k in s) o[k] = s[k];
        return o; });
    return d;
  }
  // a saved note the read predates stays: no late or stale read removes its row (r12 audit14 questions 1, running 1)
  const after = (r, d) => !!r.at && !!d.at && Date.parse(r.at) >= Date.parse(d.at);
  function keepSaved(d) {
    const have = new Set(d.notes.map(n => n.id));
    for (const r of savedNotes()) if (!have.has(r.id) && r.v === d.version && after(r, d) && !(P.ctx && P.ctx.taken(r.id)))
      d.notes.push({id: r.id, anchor: r.anchor, label: r.label, text: r.text, target: r.target, sent: false, at: r.at});
  }

  /* ---------- state of a question ---------- */
  const optLabel = (q, id) => (q.options.find(o => o.id === id) || {}).label || id;
  const isDraft = q => { const d = draft(q.id); return !!(d.pick || (d.words || '').trim()); };
  const isClosing = q => !q.closed && !isDraft(q) && !!draft(q.id).close;  // Close goes with Send, Undo until then (#23); an answer outranks it, so one card is one decision (r12 audit3 #01)
  const hasReply = q => !!(draft(q.id).reply || '').trim();
  const isDone = q => q.closed || q.sent || q.later || isDraft(q) || isClosing(q);
  const isWaiting = q => !isDone(q);
  const cardOpen = q => isDone(q) ? S.open.has(q.id) : !S.shut.has(q.id);
  const waitingCount = () => (D ? D.questions.filter(isWaiting).length : 0);
  // what the other tabs queued for the next Send (frame's P.queue): tasks, replies, Reference changes, their notes
  const Q = () => (ctx && ctx.queued ? ctx.queued() : []);
  // a note another tab lists itself is counted once, under that tab's item
  // a document note (doc:) is Pages & links' alone: this tab's feed can still hold one Send removed there, a stray whose Go to it opened Questions (audit7 reference 3)
  // a sent note he re-opened is the kit's own Send row, listed from the one draft store on every tab (r12 audit16 frame 1)
  const myNotes = q => { const own = new Set(q.map(x => x.note).filter(Boolean)); return D.notes.filter(x => NK.out(x) && !x.closed && !own.has(x.id) && !/^doc:/.test(x.anchor || '')); };
  // the one Send count, in items as the Send summary lists them: the bar here, the top bar and the phone's floating Send
  // the new note still being typed says it goes with the next Send, so Send lists, counts and carries it (audit7 #03)
  // a saved note open in its editor reads as he left it: in the editor, in Send and after a reload (audit8 #01)
  const editText = n => { const e = S.note || ctx.prefs.get('q:newnote', null); return e && e.edit === n.id && e.text != null ? e.text : n.text; };
  const typingNote = () => { const n = S.note || ctx.prefs.get('q:newnote', null); return n && !n.edit && (n.text || '').trim() ? n : null; };
  // before the questions are read, the answers, Closes and replies count from what was saved (r12 audit11 frame 1)
  const savedQs = () => Object.keys(drafts()).map(id => ({id, pre: true}));
  // his unsent notes (line, paragraph, chart point) as last read, so Send lists and counts each from its saved record while the questions are still on their way (r12 fix14 questions 1, running 1)
  const savedNotes = () => ctx.prefs.get('draft:qnotes', []);
  function notesNow(q) {
    const own = new Set(q.map(x => x.note).filter(Boolean));
    if (!D) return savedNotes().filter(n => !own.has(n.id));
    const l = myNotes(q), s = l.map(n => ({id: n.id, anchor: n.anchor, label: n.label, text: n.text, target: n.target, i: D.notes.indexOf(n) + 1, v: D.version, at: n.at, ...NK.state(n)}));
    if (JSON.stringify(s) !== JSON.stringify(savedNotes())) ctx.prefs.set('draft:qnotes', s);
    return l;
  }
  // counted from the very rows the Send sheet lists, plus General feedback, so the number and the rows never disagree (r12 audit13 reference 1)
  // what Send delivers, so the counts before it match the receipt: every listed item but another reviewer's note (lead, r12 fix28)
  const sendCount = () => sendItems().filter(x => !x[4]).length + (gen().trim() ? 1 : 0);

  function stateOf(q) {
    const d = draft(q.id), w = (d.words || '').trim();
    if (d.pick) return `<span class="saved">${ic('tick')} ${esc(cut(optLabel(q, d.pick), 40))}${w ? ' + your words' : ''} · goes with Send</span><button class="lk small" data-undo="${q.id}">Undo</button>`;
    if (w) return `<span class="saved">${ic('tick')} Answered in words · goes with Send</span><button class="lk small" data-undo="${q.id}">Undo</button>`;
    if (isClosing(q)) return `<span class="saved">${ic('archive')} Closed: no answer needed · goes with Send</span><button class="lk small" data-unclose="${q.id}">Undo</button>`;
    if (q.closed) return `<span class="saved">${ic('archive')} Closed: no answer needed</span><button class="lk small" data-reopen="${q.id}">Undo</button>`;
    // a sent answer shows what he picked, with Change for a new pick; the old one stays under Decided before (catalog 52)
    if (q.sent) { const dc = q.decision || {}, was = (dc.option_id && optLabel(q, dc.option_id)) || (dc.text || '').split('\n')[0];
      return `<span class="saved">${ic('send')} Sent${was ? ': ' + esc(cut(was, 40)) : ''} · ${esc(fmt(dc.ts))}</span>${q.read ? `<span class="qread">${ic('eye')} read by the agent</span>` : '<span class="small mut">not read yet</span>'}<button class="lk small" data-change="${q.id}" title="Pick again: the new answer goes with your next Send; this one stays under Decided before">Change</button>`; }
    if (q.later) return `<span class="small mut">${ic('later')} Set aside</span><button class="lk small" data-unlater="${q.id}">Back to waiting</button>`;
    return '';
  }
  const fmt = ts => { if (!ts) return ''; const t = new Date(ts); return isNaN(t) ? '' : t.toLocaleString([], {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'}); };
  const IMPW = {high: 'High impact', medium: 'Medium impact', low: 'Low impact'};
  const impMark = q => IMPW[q.impact] ? `<span class="impw ${q.impact}" title="${IMPW[q.impact]}: how much the agent says this answer changes"><span class="imp ${q.impact}" aria-hidden="true"><i></i><i></i><i></i></span>${q.impact === 'medium' ? 'Med' : q.impact[0].toUpperCase() + q.impact.slice(1)}</span>` : '<span class="impw none" aria-hidden="true"></span>';
  const blkMark = q => q.blocking ? `<span class="blkp" title="A task on the board waits on this answer">${ic('block')}Blocks a task</span>` : '';
  // the agent wrote on it since he last looked: Reference's "changed" mark and its 14-day first look; opening the card clears it (catalog 68)
  const firstLook = () => { let b = ctx.prefs.get('q-first'); if (!b) { b = new Date(Date.now() - 14 * 864e5).toISOString().slice(0, 16); ctx.prefs.set('q-first', b); } return b; };
  const isNew = q => !!q.act && String(q.act).replace(' ', 'T') > (ctx.prefs.get('q-seen', {})[q.id] || firstLook());
  const markSeenQ = ids => { const s = ctx.prefs.get('q-seen', {}), now = new Date().toISOString().slice(0, 19); ids.forEach(i => s[i] = now); ctx.prefs.set('q-seen', s); };
  const numChip = q => `<span class="qnum">Q ${esc(q.n)}</span>${isNew(q) ? '<span class="rf-new" title="The agent wrote here since you last looked">new</span>' : ''}`;

  function taskChip(id) {
    const b = (D.beads || {})[id];
    return `<button class="qtask" data-task="${esc(id)}" title="Open this task here"><span class="dot st-${b ? b.state : 'none'}"></span>${b ? `<span>${esc(cut(b.title, 60))}</span>` : ''}<span class="bid">· ${esc(id)}</span>${b ? `<span class="mut">· ${esc(b.status.replace('_', ' '))}</span>` : ''}</button>`;
  }
  // a card's task: one the question names or the page's tracking table links to it, else the first on the board that its evidence names
  function beadOf(q) {
    if (q.bead) return q.bead;
    for (const ev of q.evidence || []) {
      const el = DOC && DOC.querySelector(`[data-anchor-id="${CSS.escape(ev.anchor)}"]`);
      const m = el && (el.textContent.match(/\bFLD-[a-z0-9]+(?:\.\d+)*\b/g) || []).find(x => (D.beads || {})[x]);
      if (m) return m;
    }
    return null;
  }
  // the plan this question belongs to: the one sharing the most words with it, two at least (the mock's planOf)
  const WD = s => new Set((String(s).toLowerCase().match(/[a-z]{4,}/g) || []).filter(w => !['with', 'that', 'this', 'from', 'plan', 'should', 'what', 'which', 'approve', 'there'].includes(w)));
  function planOf(q) {
    if (!REF || !REF.plans) return null;
    const w = WD(q.prompt + ' ' + secTitle(q)); let best = null, bn = 1;
    for (const p of REF.plans) { const n = [...WD(p.t)].filter(x => w.has(x)).length; if (n > bn) { bn = n; best = p; } }
    return best;
  }
  const PLANST = {prop: 'Proposed', ok: 'Approved', ref: 'For reference'};
  // the title of the section a question's evidence sits in
  function secTitle(q) {
    const ev = q.evidence[0], el = ev && DOC && DOC.querySelector(`[data-anchor-id="${CSS.escape(ev.anchor)}"]`);
    const s = el && (el.tagName === 'SECTION' ? el : el.closest('section'));
    const h = s && s.querySelector(':scope > h2');
    return h ? h.textContent.replace(/:\s*\d+\s+cards?$/i, '').trim() : (ev && ev.label) || '';
  }

  /* ---------- the card ---------- */
  function card(q, inList) {
    const d = draft(q.id), open = inList ? true : cardOpen(q);
    const cls = `qcard${d.pick || (d.words || '').trim() ? ' answered' : q.sent ? ' sent' : q.closed || isClosing(q) ? ' closed' : q.later ? ' later' : ''}${S.hl === q.id ? ' hl' : ''}`;
    const marks = `<span class="qmarks">${blkMark(q)}${impMark(q)}</span>`;
    if (!open) {
      if (S.view !== 'list') return `<div class="${cls} folded" id="q-${q.id}" data-q="${q.id}"><div class="qhead"><button class="qfold" data-fold="${q.id}" aria-expanded="false" title="Open this card">${numChip(q)}<span class="qt">${esc(q.prompt)}</span></button><span class="qstate">${stateOf(q)}</span>${marks}</div></div>`;
      // Cards only: one line keeps the section, the marks and a one-click answer (#13)
      const rec = q.options.find(o => o.id === q.rec), ap = !rec && q.options.find(o => /^approve$/i.test(o.label)), st = stateOf(q);
      const right = st ? `<span class="qstate">${st}</span>` : rec ? `<button class="btn sm quick rec" data-pick="${q.id}" data-opt="${esc(rec.id)}" title="Agree with the recommended answer: ${esc(rec.label)}">${ic('tick')} ${esc(cut(rec.label, 26))}</button>`
        : ap ? `<button class="btn sm quick" data-pick="${q.id}" data-opt="${esc(ap.id)}">${ic('tick')} Approve</button>`
        : `<button class="btn sm quick" data-fold="${q.id}">${q.options.length ? 'No recommendation · Open' : 'Needs words · Open'}</button>`;
      return `<div class="${cls} folded qline" id="q-${q.id}" data-q="${q.id}"><div class="qhead"><button class="qfold" data-fold="${q.id}" aria-expanded="false" title="Open the whole card here, with its evidence">${numChip(q)}<span class="qt">${esc(q.prompt)}</span><span class="small mut qsect hide-ph">${esc(cut(secTitle(q), 40))}</span></button>${marks}<span class="qright">${right}</span></div></div>`;
    }
    const done = isDone(q), rp = d.replyOpen || (d.reply || '').trim();
    const acts = `${done ? '' : ibw('later', 'Later', 'Answer later: set it aside; it comes back under Answer later', `data-later="${q.id}"`)}${ibw('reply', 'Reply', 'Reply to the agent without answering', `data-reply="${q.id}" aria-pressed="${!!rp}"`)}${S.copied === q.id ? ibw('copied', 'Copied', 'Link copied', `data-link="${q.id}"`) : ibw('link', 'Link', 'Copy a link to this question', `data-link="${q.id}"`)}${done ? '' : ibw('archive', 'Close', 'Close without an answer: no answer needed. Goes with Send; Undo until then', `data-close="${q.id}"`)}`;
    // Cards only: every open card folds to its line by its chevron, a waiting one too (the mock's qline, audit8 #03)
    const title = (done || S.view === 'list') && !inList ? `<button class="qfold" data-fold="${q.id}" aria-expanded="true" title="${S.view === 'list' ? 'Fold this card back to its line' : 'Fold this card'}">${numChip(q)}<span class="qt">${esc(q.prompt)}</span></button>` : `<span class="qfold static">${numChip(q)}<span class="qt">${esc(q.prompt)}</span></span>`;
    const head = `<div class="qhead">${title}<span class="qstate">${stateOf(q)}</span><span class="eacts">${acts}</span>${marks}</div>`;
    const cx = q.context ? `<div class="qctx p-primary">${q.context.split('\n').map(p => `<p>${beadText(esc(p))}</p>`).join('')}</div>` : '';
    const th = q.replies.filter(r => !/^(☑ Selected|💬 Answer in words|↻|✓|✗|↺)/.test(r.text)), tOpen = S.open.has('th' + q.id);
    const typing = (d.reply || '').trim() ? `<li class="you"><span class="who">You · goes with Send</span> ${esc(d.reply)}</li>` : '';
    const thread = th.length || typing ? `<div class="small"><b>Thread with the agent</b>${th.length > 2 ? ` · <button class="lk small" data-fold="th${q.id}" aria-expanded="${tOpen}">${tOpen ? 'Hide earlier replies' : pl(th.length - 2, 'earlier reply', 'earlier replies')}</button>` : ''}</div><ul class="qthread">${(tOpen ? th : th.slice(-2)).map(r => `<li class="${r.you ? 'you' : 'agent'}"><span class="who">${r.you ? 'You' : 'Agent'} · ${esc(fmt(r.ts))}${r.you && !r.sent ? ' · not sent' : ''}</span> ${esc(r.text)}</li>`).join('')}${typing}</ul>` : '';
    const bead = beadOf(q), hso = S.open.has('hs' + q.id), plan = planOf(q);
    const asked = (d.reply || '').trim() === ASKFILE;
    const ask = asked ? `<span class="saved">${ic('tick')} Asked to file one · goes with Send</span> <button class="lk small" data-askfile="${q.id}">Undo</button>`
      : `<button class="lk small" data-askfile="${q.id}" title="A reply to the agent, sent with your next Send">Ask the agent to file one</button>`;
    const meta = `<div class="qmeta">${bead ? `<span>${ic('task')} ${taskChip(bead)}</span>` : `<span>${ic('task')} No task on the board yet · <button class="lk small" data-board title="Open the bead board under Running">Open the board</button> · ${ask}</span>`}${plan ? `<span>Plan: <button class="lk small" data-plan="${esc(plan.id)}">${esc(cut(plan.t, 40))}</button> · ${esc(PLANST[plan.st] || 'For reference')}</span>` : ''}<button class="dfold" data-fold="hs${q.id}" aria-expanded="${hso}" title="Your earlier answers on the same topic">${ic('hist')} Decided before · ${q.earlier.length}</button>${q.evidence.length && !inList ? `<button class="lk small" data-ev="${esc(q.evidence[0].anchor)}" data-evq="${q.id}">${ic('place')} ${esc(cut(q.evidence[0].label || 'Its evidence', 40))}</button>` : ''}</div>${hso ? `<ul class="qhist">${q.earlier.length ? q.earlier.map(h => h.own ? `<li><span class="mut">${esc(h.t)} · version ${esc(String(h.v).slice(1))}</span> — <b>Your earlier pick on this card:</b> ${esc(cut(h.a, 160))} <span class="small mut">· changed since</span></li>` : `<li><span class="mut">${esc(h.t)} · version ${esc(String(h.v).slice(1))}</span> — ${esc(cut(h.q, 140))} → <b>${esc(cut(h.a, 160))}</b></li>`).join('') : '<li class="mut">Nothing decided on this before.</li>'}</ul>` : ''}`;
    const norec = !q.rec ? `<p class="small mut">The agent gave no recommendation${q.options.length ? '' : ' and no choices'}.</p>` : '';
    const an = `${norec}<div class="qopts">${q.options.map((o, i) => `<button class="qopt${o.id === q.rec ? ' rec' : ''}" data-pick="${q.id}" data-opt="${esc(o.id)}" aria-pressed="${d.pick === o.id}">${o.id === q.rec ? '<span class="rl">Recommended</span>' : ''}<b>${i + 1}. ${esc(o.label)}</b>${o.c ? `<span>${esc(o.c)}</span>` : ''}</button>`).join('')}</div>
      <textarea class="qwords" data-words="${q.id}" aria-label="Answer in words" placeholder="${q.options.length ? 'Answer in words. With no choice picked, this is your answer; with one, it goes with it.' : 'Your answer: there are no choices'}">${esc(d.words || '')}</textarea>
      <p class="hint">Saved as you type · <kbd>⌘↵</kbd> opens Send</p>
      ${rp ? `<label class="small"><b>Reply to the agent</b></label><textarea class="qwords" data-replytext="${q.id}" placeholder="Ask or tell the agent something about this question">${esc(d.reply || '')}</textarea><p class="hint">Saved as you type; goes with your next Send. <button class="lk small" data-unreply="${q.id}">Remove</button></p>` : ''}`;
    const body = `<div class="qbody"><div class="qcx">${cx}${thread}${meta}</div><div class="qan">${an}</div></div>`;
    return `<div class="${cls}" id="q-${q.id}" data-q="${q.id}">${head}${body}</div>`;
  }
  // tasks the agent names: title · bead id · state
  const beadText = h => h.replace(/\bFLD-[a-z0-9]+(?:\.\d+)*\b/g, m => (D.beads || {})[m] ? taskChip(m) : m);

  /* ---------- the document ---------- */
  // Markdown the agent left unrendered: links become links, pictures the page has become pictures (#02)
  function unmark(doc, node) {
    node = node || doc.body;
    const w = doc.createTreeWalker(node, NodeFilter.SHOW_TEXT), hits = [];
    for (let n; (n = w.nextNode());) if (/\]\(/.test(n.nodeValue) && n.parentElement && !n.parentElement.closest('code,pre,a')) hits.push(n);
    for (const n of hits) {
      const h = esc(n.nodeValue).replace(/(!?)\[([^\]]*)\]\(([^)\s]+)\)/g, (m, bang, t, href) => {
        if (/^(?!https?:)[a-z][\w+.-]*:/i.test(href)) return m;  // only page, relative and web links
        const kept = bang && href.startsWith('../') && 'assets/carried/' + href.replace(/^(\.\.\/)+/, '');  // copied in by copy.sh (r12 #01)
        if (kept && (D.pics || []).includes(kept.slice(15))) return `<img src="${kept}" alt="${t || esc(kept.split('/').slice(-3).join('/'))}" loading="eager">`;
        if (bang) return /^(\.\.\/|\/|https?:)/i.test(href) ? `<span class="qmissing" title="${href}">${ic('warn')} Picture not on this page: ${esc(href.split('/').slice(-3).join('/'))}</span>` : `<img src="${href}" alt="${t}">`;
        return `<a href="${href}"${href.startsWith('#') ? '' : ' target="_blank" rel="noopener"'}>${t}</a>`;
      });
      const span = doc.createElement('span'); span.innerHTML = h; n.replaceWith(span);
    }
    for (const tpl of node.querySelectorAll('template')) unmark(doc, tpl.content);  // "Earlier updates" keep theirs in a template
  }
  async function loadDoc(v) {
    if (loadDoc.v === v && loadDoc.html) return loadDoc.html;
    const r = await fetch(ctx.base + 'content?v=' + encodeURIComponent(v), {cache: 'no-store'});
    if (!r.ok) throw new Error('the document did not load (HTTP ' + r.status + ')');
    const doc = new DOMParser().parseFromString(await r.text(), 'text/html');
    for (const l of doc.querySelectorAll('link[rel=stylesheet][href*="content.css"]'))
      if (!document.querySelector(`link[data-qdoc]`)) document.head.appendChild(Object.assign(document.createElement('link'), {rel: 'stylesheet', href: l.getAttribute('href')})).dataset.qdoc = '1';
    const dgp = doc.querySelector('script[src*="diagram-plot.js"]');
    if (dgp) loadDoc.dgp = new URL(dgp.getAttribute('src'), r.url).href;
    diagrams(doc);  // before the scripts go: a diagram's spec is a script
    doc.querySelectorAll('script,style').forEach(n => n.remove());
    unmark(doc);
    numberPics(doc);
    for (const img of doc.querySelectorAll('td img')) img.closest('table').classList.add('qpics');  // a picture table: equal picture columns (r12 #01, #04)
    const aa = doc.querySelector('.aa') || doc.body;
    // no address shows on the prototype, company mailboxes included (same rule as proto_data/questions.py); picture names like x@2x.png stay
    loadDoc.v = v; loadDoc.html = aa.innerHTML.replace(/[\w.+-]+@[a-z][\w-]*(?:\.[\w-]+)*\.(?!png\b|jpe?g\b|gif\b|webp\b|svg\b)[a-z]{2,}\b/gi, 'member@example.com');
    return loadDoc.html;
  }
  function wrapTasks(rootEl) {  // FLD-xxx in the document's text becomes a task line
    const w = document.createTreeWalker(rootEl, NodeFilter.SHOW_TEXT), hits = [];
    for (let n; (n = w.nextNode());) if (/\bFLD-[a-z0-9]/.test(n.nodeValue) && !n.parentElement.closest('.qcard,a,button,code,pre')) hits.push(n);
    for (const n of hits) {
      const html = beadText(esc(n.nodeValue));
      if (html === esc(n.nodeValue)) continue;
      const span = document.createElement('span'); span.innerHTML = html; n.replaceWith(span);
    }
  }
  function placeCards(docEl, top) {
    const unplaced = [];
    for (const q of D.questions) {
      if (document.getElementById('q-' + q.id) && root.contains(document.getElementById('q-' + q.id))) continue;
      const html = card(q);
      const ph = docEl.querySelector(`.card[data-anchor-id="${CSS.escape(q.anchor)}"]`);
      const ev = !ph && top && q.evidence[0] && docEl.querySelector(`[data-anchor-id="${CSS.escape(q.evidence[0].anchor)}"]`);
      if (ph) ph.outerHTML = html;
      else if (ev) ev.insertAdjacentHTML(ev.tagName === 'SECTION' ? 'beforeend' : 'afterend', html);
      else if (top) unplaced.push(html);
    }
    if (unplaced.length) docEl.insertAdjacentHTML('afterbegin', `<section class="qunplaced"><h2>Questions with no place in this version</h2>${unplaced.join('')}</section>`);
  }
  function inflate(d) {  // "Earlier updates" carry their sections in a <template> until opened, as on today's page
    const tpl = d.querySelector(':scope > template');
    if (tpl) { tpl.replaceWith(tpl.content.cloneNode(true)); placeCards(d); placeNotes(d); abBars(d); wrapTasks(d); indexRows(d); zoomBars(d); }
  }
  function placeNotes(docEl) {
    D.notes.forEach((n, i) => {
      const el = docEl.querySelector(`[data-anchor-id="${CSS.escape(n.anchor)}"]`);
      if (!el) return;
      const t = n.closed ? {} : n.target || {};
      if (t.tag === 'img' && t.offset) {
        const img = noteImg(el, t);
        if (img) pinOn(img, i + 1, t.offset, n);
      } else if (t.quote) markQuote(el, t.quote);
      const after = el.tagName === 'TR' ? el.closest('table').closest('.wrap') || el.closest('table') : el;
      after.insertAdjacentHTML(el.tagName === 'SECTION' ? 'beforeend' : 'afterend', noteBox(n, i + 1));
    });
    if (S.spot && !S.zoom) {  // the open marker's list, under the spot's notes (in the picture viewer while it is open)
      const boxes = [...docEl.querySelectorAll('.qnote[data-note]')].filter(b => (D.notes.find(n => n.id === b.dataset.note) || {}).anchor === S.spot);
      if (boxes.length) boxes.at(-1).insertAdjacentHTML('afterend', spotBox(S.spot));
    }
    for (const c of D.carried || []) {  // his note from an earlier version, at its line here (#16)
      const el = docEl.querySelector(`[data-anchor-id="${CSS.escape(c.anchor)}"]`);
      if (el) (el.tagName === 'TR' ? el.closest('.wrap') || el.closest('table') : el).insertAdjacentHTML(el.tagName === 'SECTION' ? 'beforeend' : 'afterend', carriedBox(c));
    }
  }
  function carriedBox(c) {
    const st = (ctx.prefs.get('q:carried', {}))[c.id];
    const act = st === 'drop' ? `<span class="saved">Dropped</span> <button class="lk small" data-carried="${c.id}~">Undo</button>`
      : st === 'resend' ? `<span class="saved">Goes with Send</span> <button class="lk small" data-carried="${c.id}~">Undo</button>`
      : `<button class="lk small" data-carried="${c.id}~drop">Drop it</button> · <button class="lk small" data-carried="${c.id}~resend">Send it again</button>`;
    return `<div class="qnote sent car">${mk('↻', true)}<b>Your note from version ${esc(String(c.v).slice(1))}, carried to version ${esc(String(D.version).slice(1))}:</b> ${esc(c.text)}${c.changed ? ' <span class="warn-t">· the text under it changed since you wrote it</span>' : ''} ${act}</div>`;
  }
  function pinOn(img, no, off, n) {
    let wrap = img.parentElement.classList.contains('qpinwrap') ? img.parentElement : null;
    if (!wrap) { wrap = document.createElement('span'); wrap.className = 'qpinwrap'; img.replaceWith(wrap); wrap.appendChild(img); }
    wrap.insertAdjacentHTML('beforeend', pinB(n, no, off));
  }
  // a numbered pin is a control: it lists the notes at its point, with + Comment for another (catalog 25)
  const pinB = (n, no, off) => `<button class="qpin${NK.sent([n]) ? ' sent' : ''}" data-pin="${esc(n.id)}" style="left:${off.dx * 100}%;top:${off.dy * 100}%" title="The notes at this point" aria-label="Note ${no}: the notes at this point" aria-expanded="${S.pin === n.id}">${no}</button>`;
  function markQuote(el, quote) {
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let n; (n = w.nextNode());) {
      const i = n.nodeValue.indexOf(quote);
      if (i < 0) continue;
      const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + quote.length);
      r.surroundContents(document.createElement('mark')); return;
    }
  }
  const mk = (no, sent) => `<span class="qmk${sent ? ' sent' : ''}" title="Your note ${no}${sent ? ', sent' : ''}">${ic('note')}${no}</span>`;
  // a marker in the document is a control: it lists every note on its spot, with + Comment for another (catalog 25)
  const mkb = (no, n) => `<button class="qmk qmkb${n.sent || n.closed ? ' sent' : ''}" data-spot="${esc(n.anchor)}" aria-expanded="${S.spot === n.anchor}" title="Every note on this spot" aria-label="Note ${no}: every note on this spot">${ic('note')}${no}</button>`;
  const KIND = t => t.quote ? `on “${esc(cut(t.quote, 50))}”` : t.tag === 'img' ? 'at this spot' : t.tag === 'tr' ? 'on this row' : /^h\d$/.test(t.tag || '') ? 'on this heading' : 'on this line';
  // the agent marked it addressed: resolved, or addressed and waiting for him
  const isResolved = NK.resolved;
  const noteNo = n => D.notes.indexOf(n) + 1;
  const closedNotes = () => D.notes.filter(n => n.closed);  // closed notes sit under Closed with their Re-open (catalog 64)
  // `dlg`: drawn in the picture viewer; while it is open the edit box is there alone, as Reference's (r12 audit20 questions 1)
  function noteBox(n, no, dlg) {
    const t = n.target || {}, what = KIND(t);
    if (S.note && S.note.edit === n.id && !S.zoom === !dlg) return `<div class="qnote" id="n-${n.id}" data-note="${n.id}">${mk(no)}<b>Note ${no} ${what}</b><textarea data-notetext aria-label="Note ${no}">${esc(editText(n))}</textarea><div class="acts"><button class="btn sm pri" data-nsave="${n.id}">Save</button><button class="lk small" data-ncancel>Cancel</button><span class="small mut"><kbd>⌘↵</kbd> saves</span></div></div>`;
    const id = esc(n.id), move = S.move === n.id;
    // a closed note folds to one line, its Re-open beside it, as an answered card keeps its Undo (#138)
    if (n.closed) return `<div class="qnote sent closed" id="n-${id}" data-note="${id}">${mkb(no, n)}<span class="saved">${ic('archive')} Note ${no} closed</span> <span class="mut">${esc(cut(n.text, 80))}</span><span class="nacts">${NK.closedActs(n)}</span></div>`;
    const cp = ibw('copy', 'Copy', 'Copy the note text', `data-ncopy="${id}"`) + ibw('link', 'Link', 'Copy a link to this note', `data-nlink="${id}"`);
    const acts = NK.acts(ctx, n, move, '', 'ndel') + cp;  // the kit's one list, sent or not (r12 audit19)
    const st = n.sent ? NK.words(ctx, n) : '<span class="saved">· goes with Send</span>';
    return `<div class="qnote${n.sent ? ' sent' : ''}${move ? ' moving' : ''}" id="n-${id}" data-note="${id}">${mkb(no, n)}<b>Note ${no} ${what}:</b> ${esc(n.text)} ${st} ${NK.view(n)}<span class="nacts">${acts}</span>${NK.thread(ctx, n)}</div>`;
  }
  // every note on one spot, opened from its marker, with + Comment for another (today's pin popover, catalog 25);
  // a picture pin (S.pin) lists the notes at its point only, and + Comment writes another there
  function spotBox(a) {
    const all = D.notes.filter(n => n.anchor === a), p = S.pin && all.find(n => n.id === S.pin), ns = p ? NK.near(all, p, pinPk) : all, first = ns[0];
    if (!first) return '';
    return NK.spot(ctx, ns.map(n => [n, noteNo(n)]), p ? 'at this point' : KIND(first.target || {}), p ? `data-spotadd="${esc(a)}" data-spotpin="${esc(p.id)}"` : `data-spotadd="${esc(a)}"`);
  }
  function newNoteBox() {
    const n = S.note, fx = n.fixOf ? ' · fix to a sent note' : '';
    return `<div class="qnote new" data-newnote>${mk('+')}<b>New note ${KIND(n.target)}</b> <span class="mut small">${fx} · goes with your next Send</span><textarea data-notetext aria-label="Your note" placeholder="Type your note">${esc(n.text || '')}</textarea><div class="acts"><button class="btn sm pri" data-nadd>Save</button><button class="lk small" data-ncancel>Cancel</button><span class="small mut"><kbd>⌘↵</kbd> saves · an empty note is dropped</span></div></div>`;
  }

  /* ---------- document navigation: header, jump menu, section folds, tiles, question rows (#12, #19) ---------- */
  const topSecs = docEl => [...docEl.querySelectorAll(':scope > section[data-anchor-id]')];
  function secQs(sec) { const ids = new Set([...sec.querySelectorAll('.qcard[data-q]')].map(e => e.dataset.q)); return D.questions.filter(q => ids.has(q.id)); }
  // decided once per visit, so answering never folds the page under you: open while a question in it waits, or when new with no questions
  function secDefault(sec) {
    const a = sec.dataset.anchorId;
    if (S.sdefV !== D.version) { S.sdef = new Map(); S.sdefV = D.version; }
    if (!S.sdef.has(a)) { const qs = secQs(sec); S.sdef.set(a, qs.length ? qs.some(isWaiting) : (D.since || {})[a] === '' || !(a in (D.since || {}))); }
    return S.sdef.get(a);
  }
  const secOpen = sec => secDefault(sec) !== S.open.has('d:' + sec.dataset.anchorId);
  function foldSections(docEl) {
    for (const sec of topSecs(docEl)) {
      const h = sec.querySelector(':scope > h2'), a = sec.dataset.anchorId;
      if (!h) continue;
      const open = secOpen(sec), qs = secQs(sec), nq = qs.filter(isWaiting).length, since = (D.since || {})[a];
      sec.classList.add('qsec'); sec.classList.toggle('qshut', !open);
      const last = h.lastChild; if (last && last.nodeType === 3) last.nodeValue = last.nodeValue.replace(/:\s*\d+\s+cards?\s*$/i, '');
      h.insertAdjacentHTML('afterbegin', `<button class="qsecf" data-sfold="${esc(a)}" aria-expanded="${open}" title="${open ? 'Fold this section' : 'Open this section'}"></button>`);
      h.insertAdjacentHTML('beforeend', `<span class="qsecm">${nq ? `<span class="badge qw">${pl(nq, 'question waiting', 'questions waiting')}</span>` : qs.length ? `<span class="badge ok">${qs.length} of ${qs.length} decided</span>` : ''}${since === '' ? '<span class="qnew">new in this version</span>' : since ? `<span class="small mut">unchanged since version ${esc(since.slice(1))}</span>` : ''}</span>`);
      // folded after a reload, a section keeps the answers still to send on their lines under its heading, each with its Undo (r12 #09)
      S.kept = S.kept || new Set();  // once kept this visit it stays, so its Undo never drops it into the folded section
      const keep = open ? [] : qs.filter(q => (isDraft(q) || isClosing(q) || S.kept.has(q.id)) && S.kept.add(q.id)).map(q => sec.querySelector(`#q-${CSS.escape(q.id)}`)).filter(Boolean);
      if (keep.length) { const box = document.createElement('div'); box.className = 'qsecans'; box.append(...keep); h.after(box); }
    }
    const first = topSecs(docEl)[0], t = D.tiles, h2 = first && first.querySelector(':scope > h2');
    if (t && h2) h2.insertAdjacentHTML('afterend', `<div class="qtiles">${[[t.versions, 'versions published', ''], [t.open, 'notes still open', 'warn'], [t.addressed, 'notes the agent addressed', 'ok'], [t.sends, 'Sends received', '']].map(([n, w, c]) => `<div class="${c}"><b>${Number(n).toLocaleString()}</b><span>${w}</span></div>`).join('')}</div>`);
  }
  function docHead(docEl) {
    const secs = topSecs(docEl), figs = [...docEl.querySelectorAll('figure[data-anchor-id]')].filter(f => !f.parentElement.closest('figure'));
    const anyOpen = secs.some(secOpen);
    const jump = `<select data-secjump aria-label="Go to a section"><option value="">Go to a section…</option><optgroup label="Sections">${secs.map(s => `<option value="${esc(s.dataset.anchorId)}">${esc(cut((s.querySelector(':scope > h2') || {}).textContent || '', 60))}</option>`).join('')}</optgroup>${figs.length ? `<optgroup label="Pictures and diagrams">${figs.map((f, i) => `<option value="${esc(f.dataset.anchorId)}">Picture ${f.dataset.pic || (f.querySelector('[data-pic]') || {dataset: {}}).dataset.pic || i + 1} · ${esc(cut(f.matches('.qdgm') ? 'Diagram' : capOf(f) || (f.querySelector('img') || {}).alt || '', 40))}</option>`).join('')}</optgroup>` : ''}</select>`;
    return `<div class="qdoch"><h2>The review document</h2><span class="small mut">version ${esc(String(D.version).slice(1))} · click a line or row, select words, or tap a picture to write a note</span><span class="spacer"></span>${jump}<button class="btn sm" data-secall>${anyOpen ? 'Collapse all' : 'Expand all'}</button></div>`;
  }
  // "Open for you: #N (what), …" in the agent's text: one row of question chips per list, not a paragraph of numbers (#19)
  function indexRows(docEl) {
    const RE = /([^:.<>]{2,80}):\s*((?:<a href="#d:q\d+">[^<]*<\/a>\s*(?:\([^)]*\))?\s*[,;]?\s*(?:and\s+)?)+)/g;
    for (const p of docEl.querySelectorAll('p')) {
      if (p.closest('.qcard') || (p.querySelectorAll('a[href^="#d:q"]').length < 2)) continue;
      const h = p.innerHTML.replace(/<\/?strong>/g, ''), rows = [];
      const rest = h.replace(RE, (m, lab, list) => {
        rows.push(`<div class="qrow"><b class="small">${lab.trim()}</b><span class="qcs">${[...list.matchAll(/<a href="#d:q(\d+)">[^<]*<\/a>\s*(?:\(([^)]*)\))?/g)].map(([, n, t]) => { const q = D.questions.find(x => String(x.n) === n);
          return `<button class="qchip" data-qref="${n}" title="Open question ${n}${q ? ': ' + esc(q.prompt) : ''}"><span class="qnum">Q ${n}</span><span>${t ? t : q ? esc(cut(q.prompt, 48)) : ''}</span></button>`; }).join('')}</span></div>`);
        return '';
      }).replace(/Click a number to jump to it\.?/i, '').trim();
      if (!rows.length) continue;
      const div = document.createElement('div');
      div.className = 'qrows'; if (p.dataset.anchorId) div.dataset.anchorId = p.dataset.anchorId;
      div.innerHTML = rows.join('') + (rest.replace(/<[^>]+>/g, '').replace(/[\s.,;]/g, '') ? `<p>${rest}</p>` : '');
      p.replaceWith(div);
    }
  }

  /* ---------- pictures: size buttons open the in-page viewer, with its notes (#24) ---------- */
  // every picture and diagram, not only a large one the server previewed (its ⤢ Full size link), gets the mock's
  // caption line: "Picture N · caption · 25-100% · ⤢ Full size" (audit14 #04, #05); every code block gets Copy (#03)
  // a size picked before keys (by file) still opens until this picture's own size is picked
  const zoomOf = k => M.zoom(k);  // by the picture's own key only: a size kept by its file would reach every copy of it (r12 audit18 frame 3)
  // a published diagram (today's <!-- DIAGRAM:name --> and its diagram-spec-name script) becomes one figure (#06)
  function diagrams(doc) {
    for (const r of [doc.body, ...[...doc.querySelectorAll('template')].map(t => t.content)]) {
      const w = doc.createTreeWalker(r, NodeFilter.SHOW_COMMENT), hits = [];
      for (let c; (c = w.nextNode());) { const m = /^\s*DIAGRAM:([A-Za-z0-9_-]+)\s*$/.exec(c.nodeValue); if (m) hits.push([c, m[1]]); }
      for (const [c, name] of hits) {
        const f = doc.createElement('figure'), sp = r.querySelector('#diagram-spec-' + CSS.escape(name));
        f.className = 'qdgm'; f.dataset.dgm = name; f.dataset.anchorId = 'dgm:' + name;
        if (sp) f.dataset.spec = sp.textContent;
        c.replaceWith(f);
      }
    }
  }
  function numberPics(doc) {  // once per document, "Earlier updates" included, so a picture keeps its number
    let n = 0;
    for (const r of [doc.body, ...[...doc.querySelectorAll('template')].map(t => t.content)]) r.querySelectorAll('img,figure.qdgm').forEach(x => {
      x.dataset.pic = ++n;
      // its key, as in every reader: its place (its anchor and its order there), not its file, so two copies of one file keep their own size and notes (r12 audit17 #2)
      const a = x.closest('[data-anchor-id]');
      x.dataset.pk = !a ? 'pic:' + n : a === x ? a.dataset.anchorId : P.media.pk(a.dataset.anchorId, [...a.querySelectorAll('img,figure.qdgm')].indexOf(x) + 1);
    });
  }
  // a point note's picture: its key, or for a note saved before keys its image id, then the first of its file, then the first picture
  const noteImg = (el, t) => el.tagName === 'IMG' ? el : (t.pk && el.querySelector(`img[data-pk="${CSS.escape(t.pk)}"]`)) || (t.image && el.querySelector(`img[data-img="${CSS.escape(t.image)}"]`))
    || [...el.querySelectorAll('img')].find(i => (i.dataset.full || i.getAttribute('src')) === t.image_src) || el.querySelector('img');
  // the key of the picture a point note's pin is drawn on, so the pin's list and the viewer use the pin's own key (r12 audit18 questions 2)
  const pinPk = n => { const t = n.target || {}, el = root && root.querySelector(`[data-anchor-id="${CSS.escape(n.anchor || '')}"]:not(.qcard)`), i = el && noteImg(el, t); return i ? i.dataset.pk || '' : t.pk || ''; };
  const picName = x =>x && x.dataset.pic ? P.media.title(x.dataset.pic, x.alt) : (x && x.alt) || '';
  // one picture line and one code Copy for every document reader: Questions, Reference plans and the Copy library,
  // and Pages & links documents call these, so a picture or a command reads and works the same in each (r12 audit15 reference #4, #5)
  const M = P.media = {
    lead: n => new RegExp(`^\\s*Picture\\s+${n}(?!\\d)\\s*[—–:·.,-]?\\s*`, 'i'),  // a caption that already says "Picture N —"
    // a viewer's title, "Picture N · caption", with the number once when the caption already starts with it (r12 audit16 running 5)
    title: (n, cap) => !cap ? `Picture ${n}` : M.lead(n).test(cap) ? cap.trim() : `Picture ${n} · ${cap}`,
    // the caption beside its "Picture N" label, without a repeat of the label
    bare: (n, cap) => String(cap || '').replace(M.lead(n), ''),
    label:(n, title) => `<b class="qpicn"${title ? ` title="${esc(title)}"` : ''}>Picture ${n}</b>`,
    // the size buttons and ⤢ Full size; `za` goes on each size button and `fa` on Full size: the reader's own data
    ctl: (z, href, fa = '', za = '') => `<span class="qzm" role="group" aria-label="Open full size at">${[25, 50, 75, 100].map(v => `<button data-zoom="${v}"${za} aria-pressed="${v === z}" title="Open full size at ${v}% of the screen width">${v}%</button>`).join('')}</span><a class="aa-full" href="${esc(href)}" target="_blank" rel="noopener"${fa}>⤢ Full size</a>`,
    tap: '<span class="hide-ph">· tap a spot to write a note</span>',
    // the mock's caption line: "Picture N · caption · 25-100% · ⤢ Full size · tap a spot to write a note" (caption is HTML)
    line: (lab, cap, ctl, tap = M.tap) => `${lab}<span>·</span>${cap ? `<span class="qcapt">${cap}</span><span>·</span>` : ''}${ctl}${tap}`,
    copyBtn: () => `<button class="btn sm qcodecopy" data-codecopy title="Copy the command" aria-label="Copy the command">${ic('copy')}<span>Copy</span></button>`,
    code: (t, a = '') => `<pre class="qcodehost"${a}><code>${esc(t)}</code>${M.copyBtn()}</pre>`,
    // the one Markdown reader (Reference plans and files, Pages & links documents): blocks of [kind, text, ...]:
    // ['h'|'p'|'li'|'pre', text], ['tbl', its text, rows, true, cells with pictures], ['img', src, description, its number from 1].
    // As today's release: a picture on its own line or inside a table cell is drawn; one in a sentence or a list line is not
    // (today's `annotate new` refuses a page with one). One with no file the feed could find keeps its description.
    blocks(t) {
      const out = [], L = String(t || '').replace(/\r/g, '').split('\n'), inl = s => s.replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1').replace(/(\*\*|__|`)(.+?)\1/g, '$2').replace(/<[^>]+>/g, '');
      let i = 0, para = [], pics = 0, m;
      const gone = alt => ['t', `${inl(alt) || 'Picture'} (picture not found)`];
      // a cell with pictures as its parts: ['t', text] and ['img', src, description, number] (pagegen.PageBuilder._cell)
      const cellParts = x => { const ps = [], re = /!\[([^\]]*)\]\(\s*([^)\s]*)\s*\)/g; let pos = 0, c;
        while ((c = re.exec(x))) { ps.push(['t', inl(x.slice(pos, c.index))], c[2] ? ['img', c[2], inl(c[1]), ++pics] : gone(c[1])); pos = re.lastIndex; }
        return ps.length ? [...ps, ['t', inl(x.slice(pos))]].filter(p => p[0] !== 't' || p[1].trim()) : null; };
      const flush = () => { if (para.length) out.push(['p', inl(para.join(' '))]); para = []; };
      if (L[0] === '---') { i = 1; while (i < L.length && L[i] !== '---') i++; i++; }  // front matter
      while (i < L.length) {
        const l = L[i];
        if (/^\s*```/.test(l)) { flush(); const b = []; i++; while (i < L.length && !/^\s*```/.test(L[i])) b.push(L[i++]); i++; out.push(['pre', b.join('\n')]); continue; }
        if ((m = /^\s*!\[([^\]]*)\]\(\s*([^)\s]*)\s*\)\s*$/.exec(l))) { flush(); out.push(m[2] ? ['img', m[2], inl(m[1]), ++pics] : ['p', `${inl(m[1]) || 'Picture'} (picture not found)`]); i++; continue; }
        if (/^#{1,6}\s/.test(l)) { flush(); out.push(['h', inl(l.replace(/^#+\s*/, ''))]); i++; continue; }
        if (/^\s*\|/.test(l)) { flush(); const r = [], cp = [];
          while (i < L.length && /^\s*\|/.test(L[i])) { const raw = L[i].trim().replace(/^\||\|$/g, '').split('|').map(x => x.trim()), c = raw.map(inl);
            if (!c.every(x => /^:?-{2,}:?$/.test(x))) { r.push(c); cp.push(raw.map(cellParts)); } i++; }
          out.push(['tbl', r.flat().join(' '), r, true, ...cp.flat().some(Boolean) ? [cp] : []]); continue; }
        if (/^\s*([-*+]|\d+\.)\s+/.test(l)) { flush(); out.push(['li', inl(l.replace(/^\s*([-*+]|\d+\.)\s+/, ''))]); i++; continue; }
        if (!l.trim() || /^(-{3,}|\*{3,})$/.test(l.trim())) { flush(); i++; continue; }
        para.push(l.trim()); i++;
      }
      flush();
      return out;
    },
    // a picture with its caption line; `fa` and `za` are the reader's own data for Full size and the size buttons.
    // No "tap a spot" hint: these pictures (Pages & links, Reference table cells) take no spot notes
    fig: (src, alt, n, z, fa = '', za = '', a = '') => `<figure class="mfig"${a}><img src="${esc(src)}"${M.wh(src)} alt="${esc(alt || 'Picture')}" data-zcap="${esc(M.title(n, alt))}" loading="lazy"><figcaption class="qcap">${M.line(M.label(n), alt ? esc(M.bare(n, alt)) : '', M.ctl(z, src, fa, za), '')}</figcaption></figure>`,
    // a table cell: its text through `txt`, or, when it holds pictures (cp from blocks), each picture through `img(part, j)`,
    // j its order in the row from 1, so two pictures of one file in a row stay two pictures (r12 audit17 reference 2)
    cell: (cp, ri, ci, c, txt, img) => { const ps = cp && cp[ri] && cp[ri][ci]; if (!ps) return txt(c);
      let j = cp[ri].slice(0, ci).flat().filter(p => p && p[0] === 'img').length;
      return ps.map(p => p[0] === 'img' ? img(p, ++j) : txt(p[1])).join(' '); },
    // a picture's size rides on its address (#wh=480x300), from the published HTML's width and height or, for Markdown, the
    // feed (reference.doc_pictures), so every reader reserves its space before it loads, as today's release (r12 audit19 reference 1)
    sized: (src, w, h) => src && !/^data:|#/.test(src) && w > 0 && h > 0 ? `${src}#wh=${Math.round(w)}x${Math.round(h)}` : src,
    wh: src => { const m = /#wh=(\d+)x(\d+)$/.exec(src || ''); return m ? ` width="${m[1]}" height="${m[2]}"` : ''; },
    // one key per picture, from its document and place: a picture on its own line is its block's anchor; one in a table
    // cell is its row's anchor and its order in the row (~p1, ~p2). Every reader keys its title, size and point notes by it
    pk: (place, j) => j ? `${place}~p${j}` : place,
    // a row's first picture also shows the point notes saved on the row, before its pictures had keys of their own
    was: k => /~r\d+~p1$/.test(k) ? k.replace(/~p1$/, '') : '',
    // the size each picture was last opened at, by its key; the settings menu's default before that
    zoom: k => { const p = P.ctx && P.ctx.prefs; return (p && k && p.get('ref-zoom', {})[k]) || (p && p.get('zoomDef', 75)) || 75; },
    setZoom: (k, z) => { const p = P.ctx && P.ctx.prefs; if (p && k) p.set('ref-zoom', {...p.get('ref-zoom', {}), [k]: z}); },
    // a reader with no picture notes of its own (Pages & links) opens Full size here: the picture at 25-100% of the screen width;
    // with its key `k`, the size picked is remembered for that picture and shows pressed on its caption line (r12 audit17 reference 6)
    // `nk` (optional): the reader's picture notes, through the notes kit, as Reference's viewer takes them (r12 audit18 reference 3):
    // pins() its markers, list() its notes and composer, tap(target) a tap on the picture, click(e) any other button, input(e), close()
    view(src, cap, z, from, k, nk) {
      let v = document.getElementById('p-mview');
      // opening or closing a picture viewer ends a Move, as on every tab (r12 audit18 frame 1, 2); a redraw of the open one keeps a Move begun in it
      if (!v) NK.endMove();
      if (!v) {
        v = document.body.appendChild(Object.assign(document.createElement('div'), {id: 'p-mview', className: 'mview'}));
        Object.entries({role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Full-size picture'}).forEach(([k, x]) => v.setAttribute(k, x));
        v.onclick = e => { const b = e.target.closest('button'), x = M._v, im = !b && e.target.closest('.pic img');
          if (b && b.dataset.mz) M.view(x.src, x.cap, +b.dataset.mz, x.from, x.k, x.nk); else if (b && b.hasAttribute('data-mclose')) M.closeView();
          else if (x && x.nk && im) x.nk.tap(NK.at(e, im)); else if (x && x.nk && b) x.nk.click(e); };
        v.oninput = e => { const x = M._v; if (x && x.nk && x.nk.input) x.nk.input(e); };
        // ⌘↵ in the viewer's composer saves, as on the page
        v.addEventListener('keydown', e => { if (e.key !== 'Enter' || !(e.metaKey || e.ctrlKey) || !e.target.matches('textarea')) return;
          const s = v.querySelector('[data-nsave]'); if (s && !e.target.matches('[data-nedtext]')) { e.preventDefault(); e.stopPropagation(); s.click(); } });  // the frame's ⌘↵ (open Send) must not also fire
        if (!M._esc) document.addEventListener('keydown', M._esc = e => { if (e.key === 'Escape' && document.getElementById('p-mview')) { e.preventDefault(); e.stopPropagation(); M.closeView(); } }, true);
      }
      M._v = {src, cap, z, from: from || (M._v && M._v.from), k, nk};
      if (k) { M.setZoom(k, z); document.querySelectorAll(`button[data-zoom][data-pk="${CSS.escape(k)}"]`).forEach(x => x.setAttribute('aria-pressed', String(+x.dataset.zoom === z))); }
      const top = v.scrollTop;
      v.innerHTML = `<div class="zbar"><b class="small">${esc(cap || 'Picture')}</b><span class="qzm" role="group" aria-label="Size">${[25, 50, 75, 100].map(x => `<button data-mz="${x}" aria-pressed="${x === z}">${x}%</button>`).join('')}</span><span class="small mut hide-ph">of the screen width${nk ? ' · tap a spot to write a note' : ''} · <kbd>Esc</kbd> closes</span><span class="spacer"></span><button class="btn sm" data-mclose>Close</button></div>
        <div class="pic${nk ? ' qpinwrap' : ''}" style="width:${z}vw"><img src="${esc(src)}" alt="${esc(cap || 'Picture')}">${nk ? nk.pins() : ''}</div>${nk ? `<div class="zn">${nk.list()}</div>` : ''}`;
      v.scrollTop = top;
      const t = v.querySelector('textarea'); (t || v.querySelector('[data-mclose]')).focus({preventScroll: !!t});
    },
    // the reader redrew its notes: the open viewer follows
    redrawView() { const x = M._v; if (x && x.nk && document.getElementById('p-mview')) M.view(x.src, x.cap, x.z, x.from, x.k, x.nk); },
    closeView() { const v = document.getElementById('p-mview'); if (v) v.remove(); NK.endMove(); const x = M._v, f = x && x.from; M._v = null; if (x && x.nk && x.nk.close) x.nk.close(); if (f && f.isConnected) f.focus(); },
    // a code Copy clicked: the command as written, then "Copied" for 2 seconds
    async onCopy(btn) {
      const p = btn.closest('pre').cloneNode(true); p.querySelectorAll('.qcodecopy').forEach(b => b.remove());
      try { await navigator.clipboard.writeText(p.textContent.replace(/\n$/, '')); } catch { P.ctx.toast('Copy failed: your browser blocked it'); return; }
      P.ctx.toast('Command copied');
      btn.innerHTML = ic('tick') + '<span>Copied</span>'; setTimeout(() => { btn.innerHTML = ic('copy') + '<span>Copy</span>'; }, 2000);
    },
  };
  function zoomBars(el) {
    for (const x of el.querySelectorAll('[data-pic]:not([data-pbar])')) {
      if (x.closest('.qzoom')) continue;
      x.dataset.pbar = '1';
      const dgm = x.tagName === 'FIGURE', src = dgm ? 'dgm:' + x.dataset.dgm : x.dataset.full || x.getAttribute('src'), z = zoomOf(x.dataset.pk);
      const at = x.parentElement.classList.contains('qpinwrap') ? x.parentElement : x;
      const old = at.nextElementSibling; if (old && old.matches('a.aa-full')) old.remove();
      const ctl = M.ctl(z, dgm ? '#' : src, ` data-zfull="${esc(src)}" data-pk="${esc(x.dataset.pk || '')}" data-zcap="${esc(dgm ? `Picture ${x.dataset.pic} · Diagram` : picName(x))}"${x.dataset.img ? ` data-zid="${esc(x.dataset.img)}"` : ''}${dgm ? ` data-zdgm="${esc(x.dataset.dgm)}"` : ''}`);
      const lab = M.label(x.dataset.pic, x.dataset.img && 'IMG ' + x.dataset.img);
      const fig = !dgm && x.closest('figure'), fc = fig && fig.querySelectorAll('img').length === 1 && fig.querySelector(':scope > figcaption');
      // a caption under the picture takes the line; a compare cell's label above it does not
      if (fc && x.compareDocumentPosition(fc) & Node.DOCUMENT_POSITION_FOLLOWING) { fc.classList.add('qcap'); fc.innerHTML = M.line(lab, M.bare(x.dataset.pic, fc.innerHTML), ctl); }
      else if (dgm) { x.insertAdjacentHTML('beforeend', `<figcaption class="qcap">${M.line(lab, 'Diagram', ctl, '')}</figcaption>`); mountDgm(x); }
      else at.insertAdjacentHTML('afterend', `<div class="qcap qpicbar">${M.line(lab, '', ctl)}</div>`);
    }
    for (const pre of el.querySelectorAll('pre')) {
      if (pre.closest('.qzoom') || pre.querySelector(':scope > .qcodecopy')) continue;
      pre.classList.add('qcodehost');
      pre.insertAdjacentHTML('beforeend', M.copyBtn());
    }
    el.querySelectorAll('img').forEach(i => { i.loading = 'eager'; });
  }
  // today's diagram engine (diagram-plot.js with d3 and Observable Plot, the versions it names) draws it; its drawing is kept for the viewer
  const DGM = {}, LIBS = ['https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js', 'https://cdn.jsdelivr.net/npm/@observablehq/plot@0.6.16/dist/plot.umd.min.js'];
  let dgmLibs = null;
  const addScript = src => new Promise((ok, no) => document.head.appendChild(Object.assign(document.createElement('script'), {src, onload: ok, onerror: () => no(new Error(src))})));
  async function mountDgm(f) {
    const name = f.dataset.dgm;
    f.insertAdjacentHTML('afterbegin', `<div class="qdgmhost">${DGM[name] || '<span class="small mut">Drawing the diagram…</span>'}</div>`);
    if (DGM[name]) return;
    const host = f.firstElementChild;
    try {
      let spec = f.dataset.spec ? JSON.parse(f.dataset.spec) : null;
      if (!spec) { const r = await fetch(ctx.base + encodeURIComponent(name) + '.json', {cache: 'no-store'}); if (r.ok) spec = await r.json(); }
      if (!spec || !loadDoc.dgp) throw new Error('no diagram');
      if (!window.AnnotateDiagrams) await (dgmLibs = dgmLibs || [...LIBS, loadDoc.dgp].reduce((p, s) => p.then(() => addScript(s)), Promise.resolve()).catch(e => { dgmLibs = null; throw e; }));
      window.AnnotateDiagrams.renderDomainMap(host, spec);
      if (!host.querySelector('svg')) throw new Error('not drawn');
      DGM[name] = host.innerHTML;
      if (S.zoom && S.zoom.dgm === name) draw(true);
    } catch { host.innerHTML = `<span class="qmissing">${ic('warn')} This diagram could not be drawn</span>`; }
  }
  const zoomAt = (a, z) => ({src: a.dataset.zfull, pk: a.dataset.pk, cap: a.dataset.zcap || '', img: a.dataset.zid, dgm: a.dataset.zdgm, anchor: (a.closest('[data-anchor-id]') || {}).dataset?.anchorId, z,
    inq: S.view === 'list' ? ((a.closest('.qcard[data-q]') || {}).dataset || {}).q : undefined});  // Cards only: the card whose evidence it is
  function zoomView() {
    if (!S.zoom) return '';
    const {src, cap, z, pk, dgm} = S.zoom;
    const ns = dgm ? [] : D.notes.map((n, i) => [n, i + 1]).filter(([n]) => !n.closed && (n.target || {}).tag === 'img' && n.target.offset && pinPk(n) === pk);
    return `<div class="qzoom" role="dialog" aria-label="${dgm ? 'Full-screen diagram' : 'Full-size picture'}"><div class="qzbar"><b class="small">${esc(cut(cap, 60))}</b><span class="qzm">${[25, 50, 75, 100].map(x => `<button data-zoomto="${x}" aria-pressed="${x === z}">${x}%</button>`).join('')}</span><span class="small mut hide-ph">of the screen width${dgm ? '' : ' · tap a spot to write a note'} · <kbd>Esc</kbd> closes</span><span class="spacer"></span><button class="btn sm" data-zclose>Close</button></div>
      ${dgm ? `<div class="qzpic qzdgm" style="width:${z}vw">${DGM[dgm] || '<span class="small mut">Drawing the diagram…</span>'}</div>`
      : `<div class="qzpic" style="width:${z}vw"><img src="${esc(src)}" alt="${esc(cap)}" data-zimg>${ns.map(([n, no]) => pinB(n, no, n.target.offset)).join('')}</div>`}
      ${ns.length ? `<div class="qznotes">${S.spot && S.pin ? spotBox(S.spot) : ''}${ns.map(([n, no]) => noteBox(n, no, true)).join('')}</div>` : ''}</div>`;
  }

  /* ---------- today and proposed: a comparison picture takes a pick, an answer that goes with Send (the mock's pickAB, audit6 #04) ---------- */
  const abPicks = () => ctx.prefs.get('draft:qab', {});  // {figure anchor: {side: current|proposed, cap}}; a draft, so it follows "Unsent answers and notes"
  function setAB(a, p) { const all = abPicks(); if (p) all[a] = p; else delete all[a]; ctx.prefs.set('draft:qab', all); }
  const capOf = f => ((f.querySelector(':scope > figcaption .qcapt') || f.querySelector(':scope > figcaption') || {}).textContent || '').trim();
  // one picture holding both sides ("today on the left, this change on the right", "before … after"), or a Today/Before picture followed by its Proposed/After one
  const isAB = f => /\btoday\b[\s\S]*\b(proposed|this change|after)\b|\bbefore\b[\s\S]*\bafter\b/i.test(capOf(f)) || /before-after/i.test((f.querySelector('img') || {}).dataset?.full || '');
  const sideOf = f => /^(current|today|before)\b/i.test(capOf(f)) ? 'current' : /^(proposed|after)\b/i.test(capOf(f)) ? 'proposed' : '';
  function abBars(el) {
    const figs = [...el.querySelectorAll('figure')].filter(f => !f.parentElement.closest('figure') && f.closest('[data-anchor-id]'));
    const key = f => f.closest('[data-anchor-id]').dataset.anchorId;  // a picture in a table cell goes by its row
    const bar = (f, a, sides, cap) => {
      if (f.querySelector(':scope > .abpick')) return;
      const p = abPicks()[a];
      f.insertAdjacentHTML('beforeend', `<div class="abpick">${sides.map(s => p && p.side === s ? `<span class="saved">${ic('tick')} You picked ${sides.length > 1 ? (s === 'current' ? 'today\'s' : 'the proposed') : 'this'} · goes with Send</span><button class="lk small" data-unab="${esc(a)}">Undo</button>`
        : `<button class="btn sm" data-ab="${esc(a)}~${s}" data-abcap="${esc(cap)}">Pick ${s === 'current' ? 'today\'s' : 'the proposed'}</button>`).join('')}</div>`);
    };
    // the page's own comparison block: Current and Proposed cells under one anchor
    el.querySelectorAll('[data-anchor-id^="cmp:"]').forEach(c => { if (c.querySelector('[data-role=current]') && c.querySelector('[data-role=proposed]')) bar(c, c.dataset.anchorId, ['current', 'proposed'], capOf(c) || c.dataset.anchorId.slice(4)); });
    figs.forEach((f, i) => {
      if (f.closest('[data-anchor-id^="cmp:"]')) return;
      if (isAB(f)) return bar(f, key(f), ['current', 'proposed'], capOf(f));
      const g = figs[i + 1];
      if (sideOf(f) === 'current' && g && sideOf(g) === 'proposed') { const cap = capOf(f) + ' / ' + capOf(g); bar(f, key(f), ['current'], cap); bar(g, key(f), ['proposed'], cap); }
    });
  }
  // its section (or Earlier updates) opens; true when that changed what is drawn
  function openFor(a) {
    const at = DOC && DOC.querySelector(`[data-anchor-id="${CSS.escape(a)}"]`), sec = at && topSecs(DOC).find(s => s.contains(at)), was = [...S.open].join();
    if (sec && !secOpen(sec)) { const o = 'd:' + sec.dataset.anchorId; S.open.has(o) ? S.open.delete(o) : S.open.add(o); }
    if (at && at.closest('details.aa-earlier')) S.open.add('earlier');
    return [...S.open].join() !== was;
  }
  const litFig = a => { const el = root.querySelector(`[data-anchor-id="${CSS.escape(a)}"]:not(.qcard)`); if (el) { el.scrollIntoView({block: 'center'}); el.classList.add('qlit'); setTimeout(() => el.classList.remove('qlit'), 2500); } };
  async function goAB(a) {
    openFor(a); S.view = 'doc'; ctx.prefs.set('q:view', 'doc');
    if (host) { drawHost(); S.goFig = a; return ctx.go('questions'); }
    await draw(true); if (openFor(a)) await draw(true);
    litFig(a);
  }

  /* ---------- the bar ---------- */
  const FILTERS = {
    need: q => !q.sent && !q.later && !q.closed,  // an answered card stays at its place in Waiting, with its Undo (#20)
    later: q => q.later && !q.closed && !isDraft(q) && !q.sent,
    ready: q => isDraft(q) || isClosing(q) || hasReply(q), wait: q => q.sent, arch: q => q.closed || isClosing(q)};
  function bar() {
    const cnt = k => D.questions.filter(FILTERS[k]).length + (k === 'arch' ? closedNotes().length : 0), lv = S.view === 'list';
    const decided = D.questions.filter(q => !isWaiting(q) && !q.later).length, all = D.questions.length;
    const chips = [['need', `Waiting ${waitingCount()}`], ['later', `<span class="hide-ph">Answer later</span><span class="ph-only">Later</span> ${cnt('later')}`], ['ready', `To send ${cnt('ready')}`], ['wait', `Sent ${cnt('wait')}`], ['arch', `Closed ${cnt('arch')}`]];
    const vsw = `<span class="qseg" role="group" aria-label="View">${[['doc', 'doc', 'Document', 'The review document, each card at its evidence'], ['list', 'list', 'Cards only', 'Only the cards, open; each folds once answered']].map(([v, k, t, tip]) => `<button data-view="${v}" aria-pressed="${S.view === v}" title="${tip}">${ic(k)}<span class="hide-ph">${t}</span></button>`).join('')}</span>`;
    const n = sendCount(), g = gen().trim();
    return `<div class="qbar">${vsw}<span class="qchips">${chips.map(([k, t]) => `<button class="chipb" data-filter="${k}" aria-pressed="${lv && S.filter === k}"${lv ? '' : ' title="Show these in Cards only"'}>${t}</button>`).join('')}<button class="chipb" data-done title="Your answers from earlier versions, in History">Done ${Number(D.done || 0).toLocaleString()} ›</button></span>
      <span class="prog" title="${decided} of ${all} questions decided">${decided} of ${all}<span class="hide-ph"> decided</span><i><b style="width:${all ? Math.round(decided / all * 100) : 0}%"></b></i></span>
      <span class="spacer"></span>${lv ? `<span class="qseg" role="group" aria-label="Open or fold the cards">${ib('expand', 'Expand all: open every card in this list', 'data-all="expand"')}${ib('collapse', 'Collapse all: fold every card in this list to its line', 'data-all="collapse"')}${ib('colans', 'Collapse answered: fold the cards you answered, closed or set aside', 'data-all="answered"')}</span>` : ''}
      <button class="btn sm${g ? ' rec' : ''}" data-genopen aria-pressed="${S.gen}">${g ? `${ic('tick')} General feedback · Edit` : 'General feedback'}</button>
      <button class="btn sm qbsend${n ? ' pri' : ''}" data-sendopen ${n ? '' : 'disabled'} title="Send your answers and notes · ⌘↵ twice">${ic('send')} Send${n ? ' ' + n : ''}</button></div>${genSheet()}${sendPanel(n)}`;
  }
  function genSheet() {
    if (!S.gen) return '';
    const g = gen();
    return `<div class="qgen" role="dialog" aria-label="General feedback"><b>General feedback</b><textarea class="qwords" data-general placeholder="Not tied to one spot; goes first in your next Send">${esc(g)}</textarea><p class="hint">Saved as you type.</p><div class="acts"><button class="btn sm pri" data-genclose>Done</button>${g.trim() ? '<button class="lk small" data-ungen>Remove</button>' : ''}</div></div>`;
  }
  // every item of the next Send: [group, html, go-to target, remove key] (the mock's sendItems)
  function sendItems() {
    const it = [], qs = D ? D.questions : savedQs();
    // before the questions are read: each named by the number, words and choice saved with its draft (r12 audit11 frame 1)
    const qn = q => q.pre ? `${draft(q.id).n ? `Q ${esc(draft(q.id).n)} · ` : ''}${esc(draft(q.id).p || 'A question')}` : `Q ${esc(q.n)} · ${esc(q.prompt)}`;
    for (const q of qs) {
      const d = draft(q.id), w = (d.words || '').trim();
      if (q.closed) continue;
      if (d.pick) it.push(['Answers', `${qn(q)} → <b>${esc(q.pre ? d.pl || 'your choice' : optLabel(q, d.pick))}</b>${w ? ` + “${esc(cut(w, 80))}”` : ''}`, 'q:' + q.id, 'ans:' + q.id]);
      else if (w) it.push(['Answers', `${qn(q)} → in words: “${esc(cut(w, 120))}”`, 'q:' + q.id, 'ans:' + q.id]);
      if (isClosing(q)) it.push(['Answers', `${qn(q)} → <b>Closed: no answer needed</b>`, 'c:' + q.id, 'close:' + q.id]);
    }
    for (const q of qs) if (!q.closed && hasReply(q)) it.push(['Replies to the agent', `On ${q.pre ? qn(q) : 'Q ' + esc(q.n)}: “${esc(cut(draft(q.id).reply, 120))}”`, 'r:' + q.id, 'reply:' + q.id]);
    for (const [a, p] of Object.entries(abPicks())) it.push(['Answers', `“${esc(cut(p.cap, 80))}” → <b>${p.side === 'current' ? 'keep today\'s' : 'the proposed'}</b>`, 'ab:' + a, 'ab:' + a]);
    const q = Q();
    const on = n => (n.target || {}).quote ? `On “${esc(cut(n.target.quote, 40))}”` : (n.target || {}).tag === 'img' ? 'At a spot on a picture' : `On “${esc(cut(n.label || '', 50))}”`;
    // [4]: another reviewer's note, listed but never in his round (the server sends only his own), so the receipt leaves it out (r12 audit22 frame 2)
    for (const n of notesNow(q)) it.push(['Notes', `${mk(D ? D.notes.indexOf(n) + 1 : n.i)}${on(n)}: ${esc(cut(NK.say({...n, text: editText(n)}), 140))}`, 'n:' + n.id, NK.rowRm(n) ? 'note:' + n.id : '', !NK.own(n), n.id]);
    const tn = typingNote(); if (tn) it.push(['Notes', `${mk('+')}${on(tn)}: ${esc(cut(tn.text, 140))}`, 'nn:', 'newnote:']);
    // the questions feed holds the page's notes; a copy's release notes are in Reference's and Pages & links' feeds alone, so their rows say (x.peer)
    const peer = id => { const n = id && D && D.notes.find(x => x.id === id); return !!n && !NK.own(n); };
    for (const x of q) it.push([x.group, x.html, 'x:' + x.key, x.remove ? 'x:' + x.key : '', !!x.peer || peer(x.note), x.note]);
    return it;
  }
  function sendPanel(n) {
    if (S.pending) return `<div class="qsend sending" role="status">${ic('send')} Sending ${pl(S.pending.n, 'item', 'items')}… <button class="lk" data-sendundo>Undo</button> ${P.inertMark()}</div>`;
    if (!S.armed) return '';
    const it = sendItems(), g = {}, un = waitingCount(), lat = D ? D.questions.filter(FILTERS.later).length : 0;
    const ok = n && D && S.oin, rd = ok || !n ? '' : ` title="Reading ${D ? 'the notes on other tabs' : 'the questions'} first: Send and Discard all follow in a moment"`;  // they act on the questions read; listing and Remove do not wait (r12 audit11)
    const ORD = ['Answers', 'Replies to the agent', 'Notes', 'Reference', 'Tasks'], at = k => (ORD.indexOf(k) + 1 || 99);  // the mock's order, whatever order the tabs loaded in
    it.slice().sort((a, b) => at(a[0]) - at(b[0])).forEach(x => (g[x[0]] = g[x[0]] || []).push(x));
    return `<div class="qsheet" data-sendclose><div class="qsend" role="dialog" aria-label="Send"><h2>Send to the agent · ${pl(n, 'item', 'items')}</h2>
      <p class="small mut">${S.copyOf ? `Would go to the ${esc(S.copyOf)} agent session; this read-only copy only shows the steps.` : S.copyOf === '' ? 'Goes to the FastLane Drive agent session.' : ''} Nothing goes until you press Send. ${P.inertMark()}</p>
      ${S.sendKey && n ? `<div class="qsendkey" role="status">${ic('send')} Press <kbd>⌘↵</kbd> again to send ${pl(n, 'item', 'items')} · <kbd>Esc</kbd> keeps editing</div>` : ''}
      <h4>General feedback · goes first</h4><textarea class="qwords" data-general placeholder="Not tied to one spot (optional)">${esc(gen())}</textarea>
      ${Object.entries(g).map(([t, l]) => `<h4>${esc(t)} · ${l.length}</h4><ul class="qhist">${l.map(([, h, go, rm, pe]) => `<li${pe ? ' data-speer' : ''}>${h}${pe ? ' <span class="small mut">· another reviewer’s, not sent</span>' : ''} <button class="lk small" data-sgo="${esc(go)}">Go to it</button>${rm ? ` · <button class="lk small" data-srm="${esc(rm)}">Remove</button>` : ''}</li>`).join('')}</ul>`).join('') || (S.oin ? `<p class="small mut" data-snone${gen().trim() ? ' hidden' : ''}>Nothing ready yet.</p>` : '')}
      ${S.oin ? '' : `<p class="small mut" aria-busy="true" data-sothers>Reading the notes on Reference and Pages &amp; links…</p>`}
      <h4>Not in this Send</h4><p class="small">${!D ? S.qerr ? `<span class="warn-t">The questions and your notes on them could not be read.</span> <button class="lk small" data-sretry>Try again</button>` : `<span class="mut" aria-busy="true">Reading the questions and your notes on them…</span>` : un || lat ? `${un ? `<span class="warn-t">${pl(un, 'question still waits', 'questions still wait')}</span>; ` : ''}${lat} set aside. They stay for next time. <button class="lk small" data-sgo="need">Open Questions</button>` : 'Every question has an answer.'}</p>
      <div class="acts"><button class="btn pri" data-send ${ok ? '' : 'disabled'}${rd}>${ic('send')} Send ${n} <kbd>⌘↵</kbd></button><button class="btn" data-discard ${ok ? '' : 'disabled'}${rd}>Discard all</button><button class="btn ghost" data-sendclose>Keep editing</button><span class="small mut"><kbd>⌘↵</kbd> sends</span></div></div></div>`;
  }

  // the Send sheet over another tab (r12 fix7 frame 5): closing it leaves him where he was
  let host = null;
  const onQ = () => !!root && root.isConnected && root.classList.contains('tab-questions');
  function drawHost() {
    if (!S.armed && !S.pending) { host.remove(); host = null; }
    else host.innerHTML = sendPanel(sendCount());
    document.body.classList.toggle('qsheet-open', !!(host && S.armed));
    ctx.refreshChips();  // a Remove or Undo over another tab moves the Questions count too
  }

  /* ---------- draw ---------- */
  async function draw(keepScroll) {
    // the picture viewer opening or closing, by any path (Full size, a size, Close, a tap, Go to it), ends a Move (r12 audit18 frame 1)
    if (!!S.zoom !== !!S.zWas) { S.zWas = !!S.zoom; NK.endMove(false); }
    if (host) return drawHost();
    if (!root || !D) return;  // Send was closed over another tab before Questions ever drew, or its data is still on its way: render draws it (r12 audit10 frame 2, audit11)
    const y = scrollY, gen = ++S.drawGen;
    // a late redraw (its document or Reference arriving) keeps the answer or reply he is in, as C left it (r12 audit10 frame 3)
    const fa = document.activeElement, fk = fa && root.contains(fa) && ['words', 'replytext'].find(k => fa.dataset[k] != null);
    const keep = fk && {sel: `[data-${fk}="${CSS.escape(fa.dataset[fk])}"]`, a: fa.selectionStart, b: fa.selectionEnd};
    const html = S.view === 'list' ? listView() : null;
    if (html != null) {
      root.innerHTML = bar() + html;
      // Cards only: a card's evidence takes notes as the document does; the new one opens under its line in that card (audit5 #03)
      root.querySelectorAll('.qevb').forEach(placeNotes);
      const evb = S.note && S.note.inq && root.querySelector(`#q-${CSS.escape(S.note.inq)} .qevb`);
      const el = evb && evb.querySelector(`[data-anchor-id="${CSS.escape(S.note.anchor)}"]`);
      const after = el && (el.tagName === 'TR' ? el.closest('.wrap') || el.closest('table') : el);
      if (after) after.insertAdjacentHTML(el.tagName === 'SECTION' ? 'beforeend' : 'afterend', newNoteBox());
    }
    else {
      root.innerHTML = bar() + `<div class="aa qdoc"></div>`;
      const docEl = root.querySelector('.qdoc');
      const doc = await loadDoc(D.version);
      // a later draw replaced this one while the document loaded: stop, or its scrollTo(0, y) undoes his scroll and a tap lands on another note (fix23 Edit miss)
      if (gen !== S.drawGen) return false;
      docEl.innerHTML = doc;
      DOC = docEl;
      placeCards(docEl, true); placeNotes(docEl); abBars(docEl); wrapTasks(docEl); indexRows(docEl); foldSections(docEl);
      docEl.insertAdjacentHTML('afterbegin', docHead(docEl));
      docEl.querySelectorAll('details.aa-earlier').forEach(d => { if (S.open.has('earlier')) { d.open = true; inflate(d); } });
      if (S.note) {
        const el = docEl.querySelector(`[data-anchor-id="${CSS.escape(S.note.anchor)}"]:not(.qcard)`);
        const after = el && (el.tagName === 'TR' ? el.closest('.wrap') || el.closest('table') : el);
        if (after) after.insertAdjacentHTML(el.tagName === 'SECTION' ? 'beforeend' : 'afterend', newNoteBox());
      }
    }
    zoomBars(root);
    if (S.zoom) root.insertAdjacentHTML('beforeend', zoomView());
    document.body.classList.toggle('qsheet-open', !!(S.armed || S.zoom));
    const back = keep && root.querySelector(keep.sel);
    if (back && (!document.activeElement || document.activeElement === document.body)) { back.focus({preventScroll: true}); back.setSelectionRange(keep.a, keep.b); }
    if (keepScroll) scrollTo(0, y);
    ctx.refreshChips(); if (ctx.refreshTop) ctx.refreshTop();
  }
  function listView() {
    const list = D.questions.filter(FILTERS[S.filter] || FILTERS.need), shut = S.filter === 'arch' ? closedNotes() : [];
    if (!DOC) loadDoc(D.version).then(h => { DOC = document.createElement('div'); DOC.innerHTML = h; if (S.view === 'list') draw(true); });
    return `<div class="qlist">${list.length || shut.length ? list.map(q => {
      const open = cardOpen(q);
      if (!open) return card(q);
      return `<div class="qitem">${card(q).replace('<div class="qbody">', `<div class="qbody">${evidence(q)}`)}</div>`;
    }).join('') + shut.map(n => noteBox(n, noteNo(n))).join('') : `<p class="mut">${S.filter === 'wait' ? 'Nothing sent from this version yet.' : 'Nothing here.'}</p>`}</div>`;
  }
  // a card's evidence, copied from the document into Cards only: its lines, rows, tables and every picture (#01)
  function evHtml(el) {
    if (el.tagName === 'SECTION') {
      let p = 0;
      return [...el.children].filter(c => !c.matches('.cards,section,details,template')).filter(c => c.matches('h2,h3,h4,figure,.wrap,table') || c.querySelector('img') || p++ < 3).map(c => c.outerHTML).join('');
    }
    if (/^H[2-6]$/.test(el.tagName)) {
      const lv = +el.tagName[1], out = [el.outerHTML];
      for (let s = el.nextElementSibling; s && out.length < 10; s = s.nextElementSibling) {
        if (/^H[2-6]$/.test(s.tagName) && +s.tagName[1] <= lv || s.matches('.cards')) break;
        out.push(s.outerHTML);
      }
      return out.join('');
    }
    if (el.tagName === 'TR') { const t = el.closest('table'); return `<table>${t && t.tHead ? t.tHead.outerHTML : ''}<tbody>${el.outerHTML}</tbody></table>`; }
    return el.outerHTML;
  }
  // a card placed inside its evidence section: the blocks just above its own spot, back to its heading or the cards before,
  // not the whole shared section (the mock's evx, audit8 #05); null when the card has no place in the section
  function spotOf(sec, q) {
    const ph = sec.querySelector(`.card[data-anchor-id="${CSS.escape(q.anchor || '')}"], .cards > #q-${CSS.escape(q.id)}`);
    if (!ph) return null;
    const out = [];
    for (let s = (ph.closest('.cards') || ph).previousElementSibling; s && out.length < 5; s = s.previousElementSibling) {
      if (s.matches('.cards,.qcard') && !out.length) continue;  // cards in a row share the lines above them
      if (s.matches('.cards,.qcard,section,details,template,h2')) break;
      if (s.matches('.qnote,.qsecf,.qsecm,.qtiles,.qdoch')) continue;
      out.unshift(s);
      if (/^H[3-6]$/.test(s.tagName)) break;
    }
    return out.length ? out.map(x => x.outerHTML).join('') : null;
  }
  function evidence(q) {
    if (!DOC || !q.evidence.length) return '';
    const els = [], spots = [];
    for (const ev of q.evidence) {
      const el = DOC.querySelector(`[data-anchor-id="${CSS.escape(ev.anchor)}"]`), spot = el && el.tagName === 'SECTION' && spotOf(el, q);
      if (spot) { if (!spots.includes(spot)) spots.push(spot); }
      else if (el && !els.some(x => x.contains(el))) els.push(el);
    }
    if (!els.length && !spots.length) return '';
    const ev = q.evidence[0];
    const box = document.createElement('div'); box.innerHTML = spots.join('') + els.map(evHtml).join('');
    box.querySelectorAll('.qcard,.qnote,.qsecf,.qsecm,.qtiles').forEach(x => x.remove());  // the document's own text only, not this tab's additions
    return `<div class="qev"><div class="small mut">${ic('place')} Its evidence in the document: <button class="lk small" data-indoc="${q.id}">${esc(cut(ev.label || 'open in the document', 50))}</button></div><div class="aa qevb">${box.innerHTML}</div></div>`;
  }

  /* ---------- actions ---------- */
  const qOf = id => D.questions.find(q => q.id === id);
  async function refresh() { stale = false; D = sim(await ctx.data('questions', true)); await draw(true); }
  function pick(q, opt) {
    const was = draft(q.id).pick;
    setDraft(q.id, {pick: was === opt ? null : opt});
    S.hl = q.id;
    draw(true);
  }
  async function later(q, on) {
    await call(`api/comments/${encodeURIComponent(q.id)}/answer-later`, {on});
    q.later = on; draw(true);
    ctx.toast(on ? 'Set aside for later' : 'Back to waiting', {undo: () => later(q, !on)});
  }
  function close(q) {
    setDraft(q.id, {close: true}); S.open.delete(q.id); draw(true);
    ctx.toast('Closed: no answer needed · goes with Send', {undo: () => { setDraft(q.id, {close: null}); draw(true); }});
  }
  async function reopen(q) {
    await call(`api/comments/${encodeURIComponent(q.id)}/restore`, {}); q.closed = false; S.open.delete(q.id); draw(true);
    ctx.toast('Restored to waiting', {undo: async () => { await call(`api/comments/${encodeURIComponent(q.id)}/archive`, {}); q.closed = true; draw(true); }});
  }
  function undo(q) {
    const keep = draft(q.id);
    setDraft(q.id, {pick: null, words: null}); S.open.delete(q.id); draw(true);
    ctx.toast('Answer removed', {undo: () => { setDraft(q.id, {pick: keep.pick, words: keep.words}); draw(true); }});
  }
  async function addNote(text) {
    const n = S.note; S.note = null; ctx.prefs.set('q:newnote', null);
    if (!text.trim()) return draw(true);
    const c = await call('api/comments', {anchor_id: n.anchor, anchor_label: n.label, text, version: D.version, target: n.target});
    // listed at once from its stored record: Send, its count and the document never wait on the re-read (r12 audit14 questions 1)
    if (c && c.id && !D.notes.some(x => x.id === c.id)) D.notes.push({id: c.id, anchor: n.anchor, label: n.label, text: c.text || text, target: n.target, sent: false, at: c.created_at || new Date().toISOString()});
    notesNow(Q());
    ctx.toast(n.fixOf ? 'Correction saved · goes with Send' : 'Note saved · goes with Send', {undo: () => delNote(c.id, true)});
    await draw(true);
    await refresh();
  }
  async function delNote(id, quiet) {
    const n = (D ? D.notes : savedNotes()).find(x => x.id === id);
    if (S.note && S.note.edit === id) { S.note = null; ctx.prefs.set('q:newnote', null); }
    // the identity read comes first: the saved record, the count and the sheet's row then leave in one task, never the count alone (r12 audit14 reference 1)
    const as = await who(), was = savedNotes();
    ctx.prefs.set('draft:qnotes', was.filter(x => x.id !== id));
    // the record stays in the store until Undo is gone, so Undo puts back the very note (r12 audit13 frame 4, questions 2)
    const keep = ctx.take(id, `api/comments/${encodeURIComponent(id)}${as}`);
    if (D) D.notes = D.notes.filter(x => x.id !== id);
    await draw(true);
    const back = async () => { keep(); ctx.prefs.set('draft:qnotes', P.putBack(savedNotes(), was, id)); await (D ? refresh() : draw(true)); };
    if (!quiet && n) ctx.toast('Note removed', {undo: back});
    return back;
  }
  async function copy(text, what) {
    try { await navigator.clipboard.writeText(text); ctx.toast(what + ' copied'); return true; } catch { ctx.toast('Copy failed: your browser blocked it'); return false; }
  }
  // the card, its section and the evidence open, scrolled to and lit together (#19, catalog 26)
  // a card is shown: in Cards only a filter that lists it (an answered "later" one is under To send), in Document its section open (audit6 #02, frame #02)
  function reveal(q) {
    const id = q.id;
    S.hl = id; S.shut.delete(id); if (isDone(q)) S.open.add(id);
    if (S.view === 'list' && !FILTERS[S.filter](q)) S.filter = ['need', 'later', 'ready', 'wait', 'arch'].find(k => FILTERS[k](q)) || 'need';
    if (S.view === 'doc' && DOC) { const c = DOC.querySelector(`#q-${CSS.escape(id)}`), sec = c && c.closest('section.qsec'); if (sec && !secOpen(sec)) S.open.has('d:' + sec.dataset.anchorId) ? S.open.delete('d:' + sec.dataset.anchorId) : S.open.add('d:' + sec.dataset.anchorId); }
    if (S.view === 'doc' && q.anchor && DOC && !DOC.querySelector(`#q-${CSS.escape(id)}`)) S.open.add('earlier');
  }
  // the part of the card a Send item names: its reply or its answer
  function showAt(id, at) {
    const c = at && document.getElementById('q-' + id);
    const el = c && (at === 'reply' ? c.querySelector('[data-replytext]') : at === 'close' ? c.querySelector('.qstate') : c.querySelector('.qopt[aria-pressed=true]') || c.querySelector('[data-words]'));
    if (el) el.scrollIntoView({block: 'center'});
  }
  async function jumpTo(id, view, at) {
    const q = qOf(id); if (!q) return;
    if (view && S.view !== view) { S.vy[S.view] = scrollY; S.view = view; ctx.prefs.set('q:view', view); }
    reveal(q);
    await draw(true);
    const el = document.getElementById('q-' + id); if (!el) return;
    el.scrollIntoView({block: 'start'}); showAt(id, at);
    const ev = q.evidence[0] && root.querySelector(`[data-anchor-id="${CSS.escape(q.evidence[0].anchor)}"]:not(.qcard)`);
    for (const x of [el, ev]) if (x) { x.classList.add('qlit'); setTimeout(() => x.classList.remove('qlit'), 2500); }
  }
  function switchView(v) {
    S.vy[S.view] = scrollY; S.view = v; ctx.prefs.set('q:view', v);
    return draw().then(ok => ok !== false && scrollTo(0, S.vy[v] || 0));  // each view keeps its own place (#22); a superseded draw leaves it to the later one
  }

  /* Send: ⌘↵ once opens the summary, again sends. The posts wait SEND_DELAY ms, with Undo, then go through today's endpoints. */
  function arm() {
    if (S.pending) return;
    if (!S.armed && !D) return openSheet(ctx, true);  // its tab still reading: the sheet opens over it with what was saved
    if (!S.armed) { S.armed = true; S.sendKey = true; S.gen = false; readOthers(ctx); draw(true).then(() => { const t = root.querySelector('[data-send]'); if (t) t.focus(); }); return; }
    send();
  }
  function send() {
    if (!D || !S.oin) return ctx.toast(`Reading ${D ? 'the notes on other tabs' : 'the questions'} first: Send works in a moment`);  // ⌘↵ again before they are read
    const answers = D.questions.filter(q => isDraft(q) && !q.closed), replies = D.questions.filter(q => hasReply(q) && !q.closed), closes = D.questions.filter(isClosing);
    // his unsent notes this Send lists ([5]): one the server's round leaves out went first from another client of his
    // every row on a note, whichever tab lists it (a release draft, a peer's draft or reply): the round's ids say which went
    const rows = sendItems(), notes = rows.map(x => x[5]).filter(Boolean), all = rows.length + (gen().trim() ? 1 : 0), n = sendCount();
    S.armed = false; S.sendKey = false;
    if (!n) return draw(true);
    S.pending = {n, timer: setTimeout(() => post(answers, replies, closes, n, {all, notes}), SEND_DELAY)};
    draw(true);
  }
  async function post(answers, replies, closes, n, listed) {
    // past the countdown Undo can no longer stop it: it goes, never visible and broken (r12 fix11 frame 1)
    S.pending.going = true; document.querySelectorAll('[data-sendundo]').forEach(b => b.remove());
    try {
      await ctx.takeNow();  // a note removed with its Undo still open leaves first, so the round never carries it
      for (const q of answers) {
        const d = draft(q.id), w = (d.words || '').trim();
        const body = d.pick ? {verdict: 'select', text: optLabel(q, d.pick) + (w ? '\n\n' + w : ''), option_id: d.pick, defer_push: true} : {verdict: 'comment', text: w, defer_push: true};
        await call(`api/comments/${encodeURIComponent(q.id)}/decision`, body);
        setDraft(q.id, {pick: null, words: null});
      }
      for (const q of replies) { await call(`api/comments/${encodeURIComponent(q.id)}/reply`, {text: draft(q.id).reply.trim()}); setDraft(q.id, {reply: null, replyOpen: null}); }
      for (const q of closes) { await call(`api/comments/${encodeURIComponent(q.id)}/archive`, {}); setDraft(q.id, {close: null}); }
      const tn = typingNote();  // the note still open goes as it reads now, as Send listed it
      if (tn) { await call('api/comments', {anchor_id: tn.anchor, anchor_label: tn.label, text: tn.text.trim(), version: D.version, target: tn.target}); S.note = null; ctx.prefs.set('q:newnote', null); }
      const ed = S.note || ctx.prefs.get('q:newnote', null), en = ed && ed.edit && D.notes.find(x => x.id === ed.edit);  // a saved note open in its editor goes with its new words
      if (en) { if ((ed.text || '').trim() && ed.text !== en.text) await call(`api/comments/${encodeURIComponent(en.id)}`, {text: ed.text}, 'PUT'); S.note = null; ctx.prefs.set('q:newnote', null); }
      // a picked side has no endpoint of its own: it goes as a note on the picture, which this round carries
      for (const [a, p] of Object.entries(abPicks())) { await call('api/comments', {anchor_id: a, anchor_label: cut(p.cap, 60), text: p.side === 'current' ? 'Picked today\'s: keep it as it is' : 'Picked the proposed', version: D.version, target: {schema: 1, tag: 'figure'}}); setAB(a, null); }
      // a re-opened note goes back to open now, so the round carries it to the agent again
      for (const id of Object.keys(NK.reo(ctx))) await call(`api/comments/${encodeURIComponent(id)}`, {status: 'open'}, 'PUT');
      const r = await call('api/rounds/submit', {note: gen().trim() || undefined, version: D.version});
      // the receipt counts what the server took: a note another client of his sent first is not in this round, and a round
      // with nothing new is a noop (r12 audit23 frame 2). Every listed row on a note the round's ids leave out stays
      // behind (a peer's draft or reply, on any tab), so it is not counted (r12 audit24 questions 1); a copy's round answers its ids too
      const ids = r && Array.isArray(r.comment_ids) ? new Set(r.comment_ids) : null;
      const got = r && r.delivery === 'noop' ? 0 : ids ? Math.max(0, listed.all - listed.notes.filter(id => !ids.has(id)).length) : n;
      ctx.prefs.set('q:general', '');
      D.notes.forEach(NK.gone);  // the round took his every unsent note: Send reads what is left with the receipt, before the re-read
      ctx.prefs.set('draft:reopen', {});  // and every re-opened one, on any tab
      NK.L = {}; ctx.prefs.set('draft:nkput', {});  // and every edit and reply on a sent note, whatever tab holds it
      if (ctx.queueSent) ctx.queueSent(got);  // the other tabs' items went with it: inert, each tab clears its own; the frame shows this round as the last Send
      S.pending = null;
      document.querySelectorAll('.qsend.sending').forEach(x => x.remove());  // straight to the receipt, as in the mock, while the tab re-reads
      updateBar();  // the toolbar's Send count follows the store with the top bar's, not after the re-read
      ctx.toast(got ? `Sent ${pl(got, 'item', 'items')}: ${S.copyOf ? 'nothing saved in this copy' : 'saved as a round in this copy'}` : 'Nothing new was sent: these items had already gone in an earlier Send', {inert: true});
      await refresh();
    } catch (e) {
      S.pending = null; await refresh();
      ctx.toast('Send failed: ' + e.message + '. Your drafts are kept.');
    }
  }
  // Discard all: every draft, the general feedback and the unsent notes go, with one Undo (#10)
  async function discardAll() {
    const keep = drafts(), g = gen(), ab = abPicks(), q = Q(), notes = myNotes(q),  // counted as Send lists them: an answer and a reply are two (r12 fix7, questions 5)
      // a sent note's edit or reply has no Remove and stays, as today's Discard all (pending verdicts only): not counted (r12 audit19 reference 6)
      total = sendItems().filter(x => x[3]).length + (gen().trim() ? 1 : 0);
    const all = {};
    for (const [id, d] of Object.entries(keep)) { const r = Object.assign({}, d); for (const k of ['pick', 'words', 'reply', 'replyOpen', 'close']) delete r[k]; if (Object.keys(r).length) all[id] = r; }
    const tn = typingNote(); if (tn) { S.note = null; ctx.prefs.set('q:newnote', null); }
    ctx.prefs.set('q:drafts', all); ctx.prefs.set('q:general', ''); ctx.prefs.set('draft:qab', {}); S.armed = false; S.sendKey = false;
    const undos = (await Promise.all(q.map(x => x.remove && x.remove()))).filter(Boolean);  // each tab takes its own back out; a sent note's edit or reply stays (the server keeps it)
    // kept until Undo is gone: Undo puts back the very notes (a re-opened one is the kit's queue row, removed above)
    const backs = []; for (const n of notes) if (NK.rowRm(n)) backs.push(await delNote(n.id, true));  // only the ones Send could Remove: the server keeps the rest
    await refresh();
    ctx.toast(`Discarded ${pl(total, 'draft', 'drafts')}`, {undo: async () => {
      ctx.prefs.set('q:drafts', keep); ctx.prefs.set('q:general', g); ctx.prefs.set('draft:qab', ab);
      if (tn) { S.note = tn; ctx.prefs.set('q:newnote', tn); }
      await Promise.all(undos.map(u => u()));
      for (const b of backs.reverse()) if (b) await b();  // last out, first back: each returns to its own place
      if (D) await refresh();  // another tab's note put back: the feed every Send count reads has it again (r12 audit23 frame 3)
    }});
  }
  async function sendRemove(k) {
    const [kind, id] = [k.slice(0, k.indexOf(':')), k.slice(k.indexOf(':') + 1)];
    // Undo puts back the question's saved words and number too, so Send still names it before the questions are read
    const keep = draft(id), meta = {p: keep.p, n: keep.n, pl: keep.pl};
    if (kind === 'ans') { setDraft(id, {pick: null, words: null}); draw(true); ctx.toast('Answer removed', {undo: () => { setDraft(id, {...meta, pick: keep.pick, words: keep.words}); draw(true); }}); }
    else if (kind === 'close') { setDraft(id, {close: null}); draw(true); ctx.toast('Close removed', {undo: () => { setDraft(id, {...meta, close: true}); draw(true); }}); }
    else if (kind === 'reply') { setDraft(id, {reply: null, replyOpen: null}); draw(true); ctx.toast('Reply removed', {undo: () => { setDraft(id, {...meta, reply: keep.reply}); draw(true); }}); }
    else if (kind === 'note') delNote(id);
    else if (kind === 'newnote') { const n = typingNote(); S.note = null; ctx.prefs.set('q:newnote', null); draw(true); ctx.toast('Note removed', {undo: () => { S.note = n; ctx.prefs.set('q:newnote', n); draw(true); }}); }
    else if (kind === 'ab') { const p = abPicks()[id]; setAB(id, null); draw(true); ctx.toast('Pick removed', {undo: () => { setAB(id, p); draw(true); }}); }
    else if (kind === 'x') {  // another tab's item: it leaves that tab too (r12 fix6)
      const x = Q().find(i => i.key === id); if (!x) return;
      // a note is a comment: read the list again once it is gone or back; never before the receipt, which a slow read must not hold back (r12 audit11 frame 2)
      // the sheet redraws at once, in the paint its Send count moves in (r12 audit13 reference 1); a note's re-read follows
      const again = () => Promise.resolve(draw(true)).then(() => x.note && D && refresh()).catch(e => { console.warn('send relist', e); return draw(true); });
      let back;
      try { back = await x.remove(); } catch (e) { again(); return ctx.toast('Could not remove it: ' + e.message); }
      ctx.toast('Removed from Send', back ? {undo: async () => { await back(); again(); }} : {});
      again();
    }
  }
  function sendGo(k) {
    S.armed = false; S.sendKey = false;
    if (k.startsWith('x:')) { const x = Q().find(i => i.key === k.slice(2)); draw(true); if (x) x.go(); return; }
    const at = {r: 'reply', q: 'answer', c: 'close'}[k[0]] || null;  // "r:" a reply, "q:" an answer, "c:" a Close and its receipt: the card opens at it (audit7 #04)
    if (at) k = 'q:' + k.slice(2);
    if (k.startsWith('ab:')) return goAB(k.slice(3));
    // a note another tab owns, listed here before that tab claimed it: Go to it opens its own tab, never Questions (audit9 running 1)
    const on = k.startsWith('n:') && (D ? D.notes : savedNotes()).find(x => x.id === k.slice(2)), a = (on && on.anchor) || '';
    const own = /^chart:/.test(a) ? ['history'] : /^ref:/.test(a) ? ['reference', a.slice(4).split('~')[0]] : /^chk:/.test(a) ? ['reference'] : /^doc:/.test(a) ? ['links'] : null;
    if (own) { host ? drawHost() : draw(true); return ctx.go(...own); }
    const nn = k === 'nn:' && typingNote();  // the note still being typed: its open editor (audit7 #03)
    if (nn) S.note = nn;
    // one typed in a card's evidence in Cards only: the filter that lists the card, the card open (audit8 #02)
    const nq = nn && nn.inq && qOf(nn.inq);
    if (nq) { S.view = 'list'; ctx.prefs.set('q:view', 'list'); reveal(nq); }
    if (k.startsWith('n:') || nn) {
      // a note in a folded section (or in Earlier updates): open it first, so the note is on screen (audit5 #04)
      const n = nn || on, at = n && DOC && DOC.querySelector(`[data-anchor-id="${CSS.escape(n.anchor)}"]`);
      const sec = at && topSecs(DOC).find(s => s.contains(at));
      if (sec && !secOpen(sec)) { const o = 'd:' + sec.dataset.anchorId; S.open.has(o) ? S.open.delete(o) : S.open.add(o); }
      if (at && at.closest('details.aa-earlier')) S.open.add('earlier');
      if (host && !(nn && nn.inq)) { S.view = 'doc'; ctx.prefs.set('q:view', 'doc'); }  // a note lives in the document
    }
    if (host) {  // opened over another tab: Questions opens at the item
      drawHost(); S.goAt = at; S.goNew = !!nn;
      if (k === 'need') { S.filter = 'need'; S.view = 'list'; ctx.prefs.set('q:view', 'list'); }
      return ctx.go('questions', k === 'need' || nn ? undefined : (k[0] === 'q' ? 'q-' : 'n-') + k.slice(2));
    }
    if (nn) return (nn.inq || S.view === 'doc' ? draw(true) : switchView('doc')).then(goNew);
    if (k === 'need') { S.filter = 'need'; return switchView('list'); }
    if (k.startsWith('q:')) return jumpTo(k.slice(2), null, at);
    if (k.startsWith('n:')) {
      return (S.view === 'doc' ? draw(true) : switchView('doc')).then(() => ctx.goTo('n-' + k.slice(2))); }  // the frame waits for the note if the draw was replaced
  }
  const goNew = () => { const el = root && root.querySelector('[data-newnote]'); if (el) { el.scrollIntoView({block: 'center'}); el.classList.add('qlit'); setTimeout(() => el.classList.remove('qlit'), 2500); } };
  // a task opens its full record beside Questions, Running's own panel, not in another tab (#27, audit4 04); ↑ ↓ step through the tasks on screen
  function peek(btn) {
    const main = root.parentElement, id = btn.dataset.task;
    if (!P.taskPanel) return ctx.go('running', id);
    const host = main.querySelector(':scope > .qtaskside') || main.appendChild(Object.assign(document.createElement('div'), {className: 'area-running qtaskside'}));
    P.taskPanel(host, ctx, id, [...new Set([...root.querySelectorAll('[data-task]')].map(x => x.dataset.task))]);
  }
  async function carried(id, st) {
    const all = ctx.prefs.get('q:carried', {}), c = (D.carried || []).find(x => x.id === id), was = all[id];
    if (st === 'resend' && c) { const r = await call('api/comments', {anchor_id: c.anchor, anchor_label: 'Carried note', text: c.text, version: D.version}); all[id + ':copy'] = r && r.id; }
    if (!st && was === 'resend' && all[id + ':copy']) {  // its saved record goes too, so no read puts its Send row back (r12 audit15 questions 4)
      const cid = all[id + ':copy'];
      ctx.prefs.set('draft:qnotes', savedNotes().filter(x => x.id !== cid)); D.notes = D.notes.filter(x => x.id !== cid);
      await call(`api/comments/${encodeURIComponent(cid)}`, undefined, 'DELETE'); delete all[id + ':copy'];
    }
    if (st) all[id] = st; else delete all[id];
    ctx.prefs.set('q:carried', all);
    refresh();
  }

  function onClick(e) {
    const card0 = e.target.closest('.qcard[data-q]');  // any click on a card makes it the one the keys act on
    if (card0 && S.hl !== card0.dataset.q) { root.querySelectorAll('.qcard.hl').forEach(x => x.classList.remove('hl')); S.hl = card0.dataset.q; card0.classList.add('hl'); }
    if (card0 && card0.querySelector('.qhead .rf-new')) { markSeenQ([card0.dataset.q]); card0.querySelectorAll('.qhead .rf-new').forEach(x => x.remove()); }  // reading it clears its mark
    const t = e.target.closest('button,a,[data-anchor-id],img,.qsheet');
    if (!t || !(host || root).contains(t)) return;
    const ds = t.dataset, q = id => qOf(id);
    if (t.classList.contains('qsheet') && e.target !== t) return;  // a click inside the Send panel, not on its backdrop
    if (t.tagName === 'A') {  // links inside the document: "#d:q38833" jumps to the card, never to another tab
      const h = t.getAttribute('href') || '';
      if (t.dataset.zfull) { e.preventDefault(); S.zoom = zoomAt(t, zoomOf(t.dataset.pk)); return draw(true); }
      if (h.startsWith('#')) {
        e.preventDefault();
        const id = decodeURIComponent(h.slice(1)), qq = D.questions.find(x => x.anchor === id);
        if (qq) return jumpTo(qq.id);
        const el = root.querySelector(`[data-anchor-id="${CSS.escape(id)}"]`); if (el) el.scrollIntoView({block: 'start'});
      }
      return;
    }
    if (ds.view) return switchView(ds.view);
    if (ds.filter) { S.filter = ds.filter; return S.view === 'list' ? draw() : switchView('list'); }
    if (t.hasAttribute('data-done')) return ctx.go('history');
    if (ds.all) { const set = S.view === 'list' ? D.questions.filter(FILTERS[S.filter] || FILTERS.need) : D.questions; for (const x of set) { if (ds.all === 'expand') { S.shut.delete(x.id); if (isDone(x)) S.open.add(x.id); } else if (ds.all === 'collapse') { S.shut.add(x.id); S.open.delete(x.id); } else if (isDone(x)) S.open.delete(x.id); } return draw(true); }
    if (ds.fold) { const k = ds.fold, x = q(k); if (x) { const open = cardOpen(x); if (isDone(x)) open ? S.open.delete(k) : S.open.add(k); else open ? S.shut.add(k) : S.shut.delete(k); S.hl = k; } else S.open.has(k) ? S.open.delete(k) : S.open.add(k); return draw(true); }
    if (ds.sfold) { const k = 'd:' + ds.sfold; S.open.has(k) ? S.open.delete(k) : S.open.add(k); return draw(true); }
    if (t.hasAttribute('data-secall')) { const secs = DOC ? topSecs(DOC) : [], open = !secs.some(secOpen); for (const s of secs) (open === secDefault(s)) ? S.open.delete('d:' + s.dataset.anchorId) : S.open.add('d:' + s.dataset.anchorId); return draw(true); }
    if (ds.qref) { const qq = D.questions.find(x => String(x.n) === ds.qref); return qq ? jumpTo(qq.id) : ctx.go('history'); }
    if (ds.change) { S.open.add(ds.change); return draw(true).then(() => { const o = root.querySelector(`#q-${CSS.escape(ds.change)} .qopts`); if (o) { o.scrollIntoView({block: 'center'}); (o.querySelector('button') || o).focus({preventScroll: true}); } markSeenQ([ds.change]); }); }
    if (ds.pick) return pick(q(ds.pick), ds.opt);
    if (ds.undo) return undo(q(ds.undo));
    if (ds.later) return later(q(ds.later), true);
    if (ds.unlater) return later(q(ds.unlater), false);
    if (ds.close) return close(q(ds.close));
    if (ds.unclose) { setDraft(ds.unclose, {close: null}); return draw(true); }
    if (ds.reopen) return reopen(q(ds.reopen));
    if (ds.reply) { const d = draft(ds.reply); setDraft(ds.reply, {replyOpen: !(d.replyOpen || (d.reply || '').trim())}); return draw(true); }
    if (ds.unreply) { setDraft(ds.unreply, {reply: null, replyOpen: null, askWas: null}); return draw(true); }
    if (ds.link) { S.copied = ds.link; setTimeout(() => { S.copied = null; }, 3000); copy(location.href.split('#')[0] + '#questions/q-' + ds.link, 'Link'); return draw(true); }
    // asking the agent to file a task is a reply: it joins Send; either Undo takes out only the request and puts back the reply it replaced (#04, audit7 #02)
    if (ds.askfile) {
      const id = ds.askfile, d = draft(id), on = (d.reply || '').trim() !== ASKFILE, was = on ? d.reply : d.askWas;
      setDraft(id, on ? {reply: ASKFILE, askWas: was, replyOpen: null} : {reply: was, askWas: null});
      draw(true);
      if (on) ctx.toast('Asked the agent to file a task · goes with Send', {undo: () => { setDraft(id, {reply: was, askWas: null}); draw(true); }});
      return;
    }
    if (t.hasAttribute('data-board')) return ctx.go('running', 'tasks');
    if (ds.task) return peek(t);
    if (ds.copytext) return copy(ds.copytext, 'Command');
    if (ds.plan) return ctx.go('reference', ds.plan);
    if (ds.ev) { const el = root.querySelector(`[data-anchor-id="${CSS.escape(ds.ev)}"]:not(.qcard)`); if (el) { const p = backPill(el, ds.evq); (el.tagName === 'SECTION' && p ? p : el).scrollIntoView({block: el.tagName === 'SECTION' ? 'start' : 'center', behavior: 'smooth'}); el.classList.add('qlit'); setTimeout(() => el.classList.remove('qlit'), 2000); } return; }
    if (ds.back) { root.querySelectorAll('.qbackrow').forEach(x => x.remove()); const c = document.getElementById('q-' + ds.back); if (c) { c.scrollIntoView({block: 'start', behavior: 'smooth'}); c.classList.add('qlit'); setTimeout(() => c.classList.remove('qlit'), 2000); } return; }
    if (ds.indoc) { S.open.add(ds.indoc); return jumpTo(ds.indoc, 'doc'); }
    if (ds.zoom) { const a = t.closest('.qzm').nextElementSibling, src = a && a.dataset.zfull; if (!src) return; M.setZoom(a.dataset.pk, +ds.zoom); S.zoom = zoomAt(a, +ds.zoom); return draw(true); }
    if (t.hasAttribute('data-codecopy')) return M.onCopy(t);
    if (ds.zoomto) { S.zoom.z = +ds.zoomto; M.setZoom(S.zoom.pk, +ds.zoomto); return draw(true); }
    if (t.hasAttribute('data-zclose')) { S.zoom = null; return draw(true); }
    // a tap in the viewer: Move's new point, kept open to show it (r12 audit19 questions 1), else a point note in the document,
    // in Cards only under the card it was opened from (r12 audit19 questions 3)
    if (t.hasAttribute('data-zimg') && S.zoom && S.zoom.anchor) { const r = t.getBoundingClientRect(), next = {anchor: S.zoom.anchor, label: cut(S.zoom.cap, 60), target: {schema: 1, tag: 'img', offset: {dx: +((e.clientX - r.left) / r.width).toFixed(3), dy: +((e.clientY - r.top) / r.height).toFixed(3)}, css: 'img:nth-of-type(1)', image: S.zoom.img || null, image_src: S.zoom.src, pk: S.zoom.pk}, inq: S.zoom.inq};
      if (S.move) return moveNote(S.move, next);
      S.zoom = null; return openNote(next, true); }
    if (t.hasAttribute('data-genopen')) { S.gen = !S.gen; return draw(true).then(() => { const ta = root.querySelector('.qgen textarea'); if (ta) ta.focus(); }); }
    if (t.hasAttribute('data-genclose')) { S.gen = false; return draw(true); }
    if (t.hasAttribute('data-ungen')) { const g = gen(); ctx.prefs.set('q:general', ''); S.gen = false; draw(true); return ctx.toast('General feedback removed', {undo: () => { ctx.prefs.set('q:general', g); draw(true); }}); }
    if (t.hasAttribute('data-sendopen')) { S.armed = !S.armed; S.sendKey = false; S.gen = false; return draw(true); }
    if (t.hasAttribute('data-sendclose')) { S.armed = false; S.sendKey = false; return draw(true); }
    if (t.hasAttribute('data-send')) return send();
    if (t.hasAttribute('data-discard')) return discardAll();
    if (t.hasAttribute('data-sretry')) return readFor(ctx, true);
    if (ds.sgo) return sendGo(ds.sgo);
    if (ds.srm) return sendRemove(ds.srm);
    if (t.hasAttribute('data-sendundo')) { if (!S.pending || S.pending.going) return; clearTimeout(S.pending.timer); S.pending = null; ctx.toast('Send undone: nothing left this page'); return draw(true); }
    if (t.hasAttribute('data-nadd')) return addNote(root.querySelector('[data-newnote] textarea').value);
    if (t.hasAttribute('data-ncancel')) { S.note = null; ctx.prefs.set('q:newnote', null); return draw(true); }
    if (ds.nedit) return openNote({edit: ds.nedit});
    if (ds.nsave) return saveNote(ds.nsave, t.closest('.qnote').querySelector('textarea').value);
    if (ds.ndel) return delNote(ds.ndel);
    if (ds.ncopy) return copy((D.notes.find(x => x.id === ds.ncopy) || {}).text || '', 'Note');
    if (ds.nlink) return copy(location.href.split('#')[0] + '#questions/n-' + ds.nlink, 'Link');
    if (ds.carried) { const [id, st] = ds.carried.split('~'); return carried(id, st); }
    if (ds.spot != null) { S.pin = null; S.spot = S.spot === ds.spot ? null : ds.spot; return draw(true); }
    if (ds.pin) { const n = D.notes.find(x => x.id === ds.pin); if (!n) return; const on = S.pin === n.id; S.pin = on ? null : n.id; S.spot = on ? null : n.anchor; return draw(true); }
    if (t.hasAttribute('data-spotx')) { S.spot = S.pin = null; return draw(true); }
    if (ds.spotadd) {
      const p = ds.spotpin && D.notes.find(n => n.id === ds.spotpin), f = p || D.notes.find(n => n.anchor === ds.spotadd) || {};
      // in Cards only the editor opens in that card's copied evidence, where the marker was (r12 audit17 questions 1)
      const card = S.view === 'list' && (t.closest('.qcard[data-q]') || (root.querySelector(`.qevb [data-anchor-id="${CSS.escape(ds.spotadd)}"]`) || t).closest('.qcard[data-q]'));
      const inq = card ? card.dataset.q : undefined;
      S.spot = S.pin = null; S.zoom = null;  // a pin's + Comment writes at its point, in the document as a tap on the viewer does
      return openNote({anchor: ds.spotadd, label: f.label || '', target: p ? {...p.target} : {schema: 1, tag: (f.target || {}).tag || 'p'}, inq}, !!p);
    }
    if (ds.spotgo) { S.spot = S.pin = null; S.zoom = null; return draw(true).then(() => litNote(ds.spotgo)); }
    if (ds.nclose) return noteState(ds.nclose, 'close');
    if (ds.nopen) return noteState(ds.nopen, 'restore');
    if (ds.nreopen) return noteState(ds.nreopen, 'reopen');
    if (ds.nres) return goResolution(ds.nres);
    if (ds.nmove) { S.move = S.move === ds.nmove ? null : ds.nmove; draw(true); if (S.move) ctx.toast('Click the new spot for this note in the document · Esc cancels'); return; }
    if (ds.ab) {
      const [a, side] = ds.ab.split('~');
      setAB(a, {side, cap: ds.abcap || a}); draw(true);
      return ctx.toast('Picked · goes with Send', {undo: () => { setAB(a, null); draw(true); }});
    }
    if (ds.unab) { setAB(ds.unab, null); return draw(true); }
    // a note: tap a picture spot, select words, or click a line, row or item of the document
    const evb = S.view === 'list' && t.closest('.qevb');  // Cards only: a card's copied evidence takes notes too (audit5 #03)
    if (evb ? t.closest('.qnote,.qspot,.qzm,.qcap,figcaption,summary') : S.view !== 'doc' || t.closest('.qcard,.qnote,.qspot,.qbar,.qsend,.qzm,.qcap,.qzoom,.qdoch,.qtiles,.qrows,.abpick,figcaption,summary')) return;
    const img = e.target.closest('img');
    const anchorEl = e.target.closest('figure.qdgm') || e.target.closest('[data-anchor-id]');  // a diagram takes its note as a whole
    if (evb && (!anchorEl || !evb.contains(anchorEl))) return;
    // a section takes a note from a click on its own heading, as today's page does (r12 audit17 questions 3)
    const hd = anchorEl && anchorEl.tagName === 'SECTION' && e.target.closest('h1,h2,h3,h4,h5,h6');
    if (!anchorEl || anchorEl.tagName === 'SECTION' && !img && !(hd && anchorEl.contains(hd))) return;
    const label = cut((img && picName(img)) || (anchorEl.matches('figure.qdgm') ? `Picture ${anchorEl.dataset.pic} · Diagram` : (hd || anchorEl).textContent.replace(/\s*\d+\s+(questions? waiting|of \d+ decided).*$/i, '').trim()) || '', 60);
    let target;
    if (img) { const r = img.getBoundingClientRect(); target = {schema: 1, tag: 'img', offset: {dx: +((e.clientX - r.left) / r.width).toFixed(3), dy: +((e.clientY - r.top) / r.height).toFixed(3)}, css: 'img:nth-of-type(1)', image: img.dataset.img || null, image_src: img.dataset.full || img.getAttribute('src'), pk: img.dataset.pk}; }
    else { const sel = String(getSelection() || '').trim(); target = sel && anchorEl.contains(getSelection().anchorNode) ? {schema: 1, tag: anchorEl.tagName.toLowerCase(), quote: sel.slice(0, 300)} : {schema: 1, tag: anchorEl.tagName.toLowerCase()}; }
    if (S.move) return moveNote(S.move, {anchor: anchorEl.dataset.anchorId, label, target});
    return openNote({anchor: anchorEl.dataset.anchorId, label, target, inq: evb ? evb.closest('.qcard[data-q]').dataset.q : undefined});
  }
  const litNote = id => { const el = document.getElementById('n-' + id); if (el) { el.scrollIntoView({block: 'center'}); el.classList.add('qlit'); setTimeout(() => el.classList.remove('qlit'), 2500); } };
  // Close, Re-open and the closed note's Re-open: the shared lifecycle (P.notes.set), each with Undo (#138, catalog 64)
  const noteRedraw = async id => { S.spot = S.pin = null; notesNow(Q()); await draw(true); if (!host) litNote(id); };
  NK.hooks.questions = {go: r => sendGo('n:' + r.id), redo: () => draw(true)};
  function noteState(id, how, quiet) {
    const n = D.notes.find(x => x.id === id);
    return n ? NK.set(ctx, n, how, call, noteRedraw, quiet) : null;
  }
  // where the agent addressed it: in this version's document, or the version that resolved it in History (today's View resolution)
  async function goResolution(id) {
    const n = D.notes.find(x => x.id === id); if (!n || !n.ra) return;
    S.zoom = null; S.spot = null; S.move = null;  // a picture viewer closes first, so the destination is in sight (r12 audit17 reference 3)
    if (n.rv && n.rv !== D.version) return NK.goRes(ctx, n);
    if (S.view !== 'doc') { S.view = 'doc'; ctx.prefs.set('q:view', 'doc'); }
    openFor(n.ra); await draw(true);
    const el = root.querySelector(`[data-anchor-id="${CSS.escape(n.ra)}"]:not(.qcard)`);
    if (el) { el.scrollIntoView({block: 'center', behavior: 'smooth'}); el.classList.add('qlit'); setTimeout(() => el.classList.remove('qlit'), 2500); }
  }
  // Move: the next click in the document is its new spot; today's manual re-pin, with Undo (catalog 65)
  async function moveNote(id, to) {
    S.move = null;
    const n = D.notes.find(x => x.id === id); if (!n) return draw(true);
    return NK.move(ctx, id, {anchor_id: n.anchor, anchor_label: n.label, target: n.target || null}, {anchor_id: to.anchor, anchor_label: to.label, target: to.target}, call,
      async p => { if (p) Object.assign(n, {anchor: p.anchor_id, label: p.anchor_label, target: p.target}); notesNow(Q()); await draw(true); if (p) litNote(id); });
  }
  // an evidence jump leaves "Back to Q N" just above the evidence, one at a time, as today's page does (catalog 32, audit8 #04)
  function backPill(el, qid) {
    const q = qOf(qid); if (!q) return;
    root.querySelectorAll('.qbackrow').forEach(x => x.remove());
    const at = el.tagName === 'TR' ? el.closest('.wrap') || el.closest('table') : /^(TD|TH|LI)$/.test(el.tagName) ? el.closest('table,ul,ol') || el : el;
    at.insertAdjacentHTML('beforebegin', `<div class="qbackrow"><button class="qback" data-back="${esc(q.id)}" title="Return to the question card that cited this">${ic('undo')} Back to Q ${esc(q.n)}</button></div>`);
    return at.previousElementSibling;
  }
  // a second note never erases the first: the unfinished one is saved on its own line before the next opens, as the mock keeps it (r12 #02)
  async function openNote(next, scroll) {
    const was = S.note, ta = was && root.querySelector(was.edit ? `[data-note="${CSS.escape(was.edit)}"] textarea` : '[data-newnote] textarea');
    // an Edit's box takes typing at once too, in the viewer when it is open (r12 audit20 questions 1)
    const focus = () => { const e = S.note && S.note.edit, nt = root.querySelector(e ? `[data-note="${CSS.escape(e)}"] textarea` : '[data-newnote] textarea'); if (nt) { if (scroll) nt.scrollIntoView({block: 'center'}); nt.focus({preventScroll: true}); nt.setSelectionRange(nt.value.length, nt.value.length); } };
    if (was && !was.edit && !was.fixOf && !next.edit && was.anchor === next.anchor && !(next.target || {}).offset) return focus();  // the same line again: keep typing
    const text = ta ? ta.value : '';
    if (was && was.edit && text.trim() && text !== (D.notes.find(x => x.id === was.edit) || {}).text) await saveNote(was.edit, text);
    else if (was && !was.edit && text.trim()) await addNote(text);
    S.note = next;
    ctx.prefs.set('q:newnote', next);
    await draw(true);
    focus();
  }
  async function saveNote(id, text) {
    S.note = null; ctx.prefs.set('q:newnote', null);
    const n = D.notes.find(x => x.id === id);
    if (!text.trim() && !(n && n.sent)) return delNote(id);  // a sent one cannot be deleted, as today
    if (!n) return draw(true);
    // the kit's edit, as on every tab: in place (today's PUT), its Undo; a sent one goes with the next Send again
    if (await NK.fix(ctx, n, text, call, (w, p) => { Object.assign(n, p); return draw(true); })) await refresh();
    else draw(true);
  }
  function onInput(e) {
    const t = e.target, ds = t.dataset;
    if (ds.words) { const was = isDraft(qOf(ds.words)); setDraft(ds.words, {words: t.value}); if (was !== isDraft(qOf(ds.words))) { ctx.refreshChips(); updateBar(); } }
    else if (ds.replytext) { const was = hasReply(qOf(ds.replytext)); setDraft(ds.replytext, {reply: t.value, replyOpen: true}); if (was !== hasReply(qOf(ds.replytext))) updateBar(); }
    else if (t.hasAttribute('data-general')) { const was = !!gen().trim(); ctx.prefs.set('q:general', t.value); if (was !== !!t.value.trim()) S.armed ? sheetCount() : updateBar(); }
    else if (t.hasAttribute('data-notetext') && t.closest('[data-newnote]') && S.note) { const was = !!typingNote(); S.note.text = t.value; ctx.prefs.set('q:newnote', S.note); if (was !== !!typingNote()) { ctx.refreshChips(); updateBar(); } }  // an unsaved note survives a reload (#08) and counts in Send (audit7 #03)
    else if (t.hasAttribute('data-notetext') && S.note && S.note.edit && t.closest('.qnote').dataset.note === S.note.edit) { S.note.text = t.value; ctx.prefs.set('q:newnote', S.note); }  // an edit to a saved note: kept like a new one (audit8 #01)
  }
  // typing General feedback inside the Send sheet: heading and buttons follow in place, the cursor stays (r12 fix6, questions 02)
  function sheetCount() {
    const n = sendCount(), s = (host || root).querySelector('.qsend[role=dialog]'), $ = x => s.querySelector(x); if (!s) return updateBar();
    $('h2').textContent = `Send to the agent · ${pl(n, 'item', 'items')}`;
    $('[data-send]').disabled = !n || !D; $('[data-send]').innerHTML = `${ic('send')} Send ${n} <kbd>⌘↵</kbd>`; $('[data-discard]').disabled = !n || !D;
    if ($('[data-snone]')) $('[data-snone]').hidden = !!gen().trim();  // General feedback is an item: the empty caption goes (audit6 frame #06)
    const b = root && root.querySelector('.qbsend');
    if (b) { b.disabled = !n; b.classList.toggle('pri', !!n); b.innerHTML = `${ic('send')} Send${n ? ' ' + n : ''}`; }
    if (ctx.refreshTop) ctx.refreshTop();
  }
  function updateBar() {
    const b = root && root.querySelector('.qbar'); if (!b) return;
    const tmp = document.createElement('div'); tmp.innerHTML = bar(); b.replaceWith(tmp.querySelector('.qbar'));
    if (ctx.refreshTop) ctx.refreshTop();
  }
  function onKey(e) {
    if (host && e.key === 'Escape' && S.armed) { e.preventDefault(); S.armed = false; S.sendKey = false; return drawHost(); }
    if (!onQ()) return;  // ⌘↵ on another tab is the frame's: it calls open(ctx, true)
    if (e.key === 'Escape') {  // closes the picture, the Send summary (drafts kept) or General feedback (#06)
      if (S.zoom || S.armed || S.gen || S.spot || S.move) { e.preventDefault(); S.zoom = null; S.armed = false; S.sendKey = false; S.gen = false; S.spot = null; S.move = null; draw(true); }
      return;
    }
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      // only a note's own editor saves on ⌘↵; from a saved note's buttons (Copy, Move…) it opens Send (r12 audit17 frame 2)
      const nt = e.target.tagName === 'TEXTAREA' && e.target.closest('.qnote');
      if (nt) return nt.hasAttribute('data-newnote') ? addNote(e.target.value) : saveNote(nt.dataset.note, e.target.value);
      return arm();
    }
    // F and A step through waiting questions, 1-9 picks on the highlighted one, C writes words on it (#05)
    if (/TEXTAREA|INPUT|SELECT/.test(e.target.tagName) || e.target.isContentEditable || e.metaKey || e.ctrlKey || e.altKey || S.armed || S.zoom || !D) return;
    const order = D.questions.filter(q => FILTERS[S.view === 'list' ? S.filter : 'need'](q)), wait = order.filter(isWaiting);
    const k = order.findIndex(q => q.id === S.hl);
    if (e.key === 'f' || e.key === 'a') {
      const f = e.key === 'f', nx = k < 0 ? wait[0] : f ? order.slice(k + 1).find(isWaiting) : order.slice(0, k).reverse().find(isWaiting);
      if (!nx) return;
      e.preventDefault(); jumpTo(nx.id);
    } else if (/^[1-9]$/.test(e.key) && S.hl) {
      const q = qOf(S.hl), o = q && !q.closed && !q.sent && q.options[+e.key - 1];
      if (!o) return;
      e.preventDefault(); setDraft(q.id, {pick: o.id});
      const nx = order.slice(order.findIndex(x => x.id === q.id) + 1).find(isWaiting);
      if (nx) jumpTo(nx.id); else draw(true);
    } else if (e.key === 'c' && S.hl) {
      const ta = root.querySelector(`[data-words="${CSS.escape(S.hl)}"]`); if (ta) { e.preventDefault(); ta.focus(); }
    }
  }
  function onChange(e) {
    const t = e.target, ds = t.dataset;
    if (ds.words && isDraft(qOf(ds.words)) && S.view === 'doc') return draw(true);  // a typed answer folds its card when the box is left
    if (t.hasAttribute('data-secjump') && t.value) {
      const el = DOC && DOC.querySelector(`[data-anchor-id="${CSS.escape(t.value)}"]`), sec = el && (el.closest('section.qsec'));
      if (sec && !secOpen(sec)) { const k = 'd:' + sec.dataset.anchorId; S.open.has(k) ? S.open.delete(k) : S.open.add(k); }
      const a = t.value;
      return draw(true).then(() => { const x = root.querySelector(`[data-anchor-id="${CSS.escape(a)}"]`); if (x) { x.scrollIntoView({block: 'start'}); x.classList.add('qlit'); setTimeout(() => x.classList.remove('qlit'), 2000); } });
    }
  }
  // a card and its evidence light each other while the pointer is on either, as the mock does (a26, audit5 #06)
  let evLit = '';
  function onHover(e) {
    const c = S.view === 'doc' && e.target.closest('.qcard[data-q]'), q = c && qOf(c.dataset.q);
    const a = S.view === 'doc' && !c && e.target.closest('[data-anchor-id]:not(section)'), k = q ? 'q:' + q.id : a ? 'a:' + a.dataset.anchorId : '';
    if (k === evLit && (!k || root.querySelector('.evh'))) return;  // a redraw drops the marks: light them again
    evLit = k;
    root.querySelectorAll('.evh').forEach(x => x.classList.remove('evh'));
    const line = x => x.tagName === 'SECTION' ? x.querySelector(':scope > h2, :scope > h3') : x;  // a section's evidence lights its heading line, not the whole section
    const lit = q ? q.evidence.flatMap(v => [...root.querySelectorAll(`[data-anchor-id="${CSS.escape(v.anchor)}"]:not(.qcard)`)].map(line).filter(Boolean))
      : a ? D.questions.filter(x => x.evidence.some(v => v.anchor === a.dataset.anchorId)).map(x => document.getElementById('q-' + x.id)).filter(Boolean) : [];
    if (a && lit.length) lit.push(a);
    // the line the card sits under (above its group of cards), when it is part of its evidence: the mock's lit line
    const sib = q && c.previousElementSibling, prev = sib && !sib.matches('.qcard,.qnote') ? sib : q && c.parentElement.matches('.cards') ? c.parentElement.previousElementSibling : null;
    if (prev && !prev.matches('.qcard,.qnote') && q.evidence.some(v => { const e = root.querySelector(`[data-anchor-id="${CSS.escape(v.anchor)}"]:not(.qcard)`); return e && e.contains(prev); })) lit.push(prev);
    lit.forEach(x => x.classList.add('evh'));
  }
  addEventListener('keydown', onKey);
  document.addEventListener('toggle', e => {
    const d = e.target;
    if (!(d instanceof HTMLDetailsElement) || !d.classList.contains('aa-earlier') || !root || !root.contains(d)) return;
    d.open ? S.open.add('earlier') : S.open.delete('earlier');
    if (d.open) inflate(d);
  }, true);

  P.tab({
    key: 'questions',
    chip: async c => {
      await load(c);  // a newer version marks the data stale: the chip counts the new one (audit6 running #04)
      const n = waitingCount(), later = D.questions.filter(FILTERS.later).length;
      if (!D.questions.length) return {empty: true};
      // the mock: always "N waiting", red while any wait, green at zero; set-aside ones only in the tip (audit4 frame 5)
      return {text: `${n} waiting`, tone: n ? 'red' : 'green', title: pl(n, 'question waits', 'questions wait') + ' for your answer' + (later ? ` · ${later} set aside to answer later` : '')};
    },
    render: async (el, c, anchor) => {
      ctx = c; root = el; S.move = null;  // leaving the tab and coming back cancels Move (r12 audit17 reference 4)
      // listening before the reads: Send can open here while they finish, and its Go to it works on the first click (r12 fix14 questions 2)
      el.onclick = onClick; el.oninput = onInput; el.onchange = onChange; el.onmouseover = onHover;
      S.view = S.view || ctx.prefs.get('q:view', 'doc');
      el.innerHTML = '<p class="mut">Loading the questions…</p>';
      const fresh = stale; stale = false;
      D = sim(await c.data('questions', fresh));
      await findCopy(c);
      if (host) { host.remove(); host = null; }  // the Send opened over another tab now shows in this bar
      if (!REF) c.data('reference').then(r => { REF = r; if (root && root.isConnected && root.classList.contains('tab-questions')) draw(true); }).catch(() => { REF = {}; });
      if (!S.note && ctx.prefs.get('q:newnote', null)) S.note = ctx.prefs.get('q:newnote', null);  // the note he was typing before a reload
      const q0 = anchor && anchor.startsWith('q-') && qOf(anchor.slice(2));
      if (q0) reveal(q0);
      el.onclick = onClick; el.oninput = onInput; el.onchange = onChange; el.onmouseover = onHover; evLit = '';
      await draw();
      // Go to it from another tab: its folded section is known only once the document is drawn (audit6 frame #02)
      if (q0 && S.view === 'doc') { const was = [...S.open].join(); reveal(q0); if ([...S.open].join() !== was) await draw(true); }
      if (S.goFig) { const a = S.goFig; S.goFig = null; if (openFor(a)) await draw(true); setTimeout(() => litFig(a), 80); }
      if (q0 && S.goAt) { const a = S.goAt; S.goAt = null; setTimeout(() => showAt(q0.id, a), 80); }  // after the frame's scroll to the card
      if (S.goNew) { S.goNew = false; setTimeout(goNew, 80); }
    },
  });
  // a note written on another tab (or removed there) is re-read before the next count (r12 audit4 reference #4)
  let stale = false;
  // one read at a time: a count asked while a read is on its way waits for it, never counting the old version (r12 audit7 running 1)
  // again (Try again): a read still on its way is dropped and a new one starts, never waiting on the stalled one (r12 audit11 reference 1)
  let reading = null;
  const load = async (c, again) => {
    ctx = ctx || c;
    if (again) reading = null;
    for (;;) {
      if (reading) { await reading; continue; }  // marked stale meanwhile: read again
      if (D && !stale && !again) return;
      const fresh = !!D || !!again; stale = false; again = false;
      const r = reading = c.data('questions', fresh).then(d => { D = sim(d); S.qerr = false; }).finally(() => { if (reading === r) reading = null; });
    }
  };
  // the Send sheet open before the questions were read: their items join it once they are in, or it says the read failed
  const readFor = (c, again) => { S.qerr = false; relist(); return load(c, again).then(relist, () => { S.qerr = true; relist(); }); };
  // the same for the notes Reference and Pages & links list (a 2.32.8 Policies or meeting note is in their feeds alone): the
  // sheet says it is reading them and Send waits, then lists them; the tabs' own first reads, never a second (r12 audit24 reference 1)
  let others = null;
  const readOthers = c => others || (others = Promise.all(['reference', 'links'].map(a => c.data(a).catch(() => null)))
    .then(() => { S.oin = true; relist(); }));
  // the open Send summary lists what the count now holds, unless he is typing in it (r12 fix10 reference 2)
  async function relist() {
    const s = document.querySelector('.qsend:not(.sending)'), a = document.activeElement;
    if (!S.armed || !s || (s.contains(a) && /^(TEXTAREA|INPUT)$/.test(a.tagName))) return;
    const f = s.contains(a) && a.matches('[data-send]'); await draw(true); const b = f && document.querySelector('.qsend [data-send]'); if (b) b.focus();
  }
  // copyOf is the project's key; its name, as the frame shows it, is the page's meta name
  async function findCopy(c) { if (S.copyOf === undefined) S.copyOf = await c.data('frame').then(f => f && f.copyOf ? c.api.meta().then(m => m.name || f.copyOf, () => f.copyOf) : '', () => ''); }
  P.send({
    count: async (c, again) => { await load(c, again); return sendCount(); },
    saved: c => { ctx = ctx || c; return sendCount(); },  // what Send lists now, from the saved drafts alone while no read is in (r12 fix14)
    wrote: path => { if (/^api\/comments(\/[^/]+)?$/.test(path.split('?')[0])) stale = true; },
    newer: () => { stale = true; DOC = null; },  // the frame loaded a newer version: read the questions again on any tab
    // the count moved while the summary is open (a tab's note just saved): list it too, unless he is typing in it (r12 fix10 reference 2)
    changed: relist,
    // the rows and their Remove: a read that confirms his note moves these, not the count, and the open sheet follows (r12 audit22 reference 3, 4)
    sig: () => JSON.stringify(sendItems().map(x => [x[2], x[3]])),
    waiting: async c => { await load(c); return waitingCount(); },  // the top bar and Home read this page's waiting from here
    open: openSheet,
  });
  // key: opened by ⌘↵, which asks for a second press; a second ⌘↵ sends. Off Questions the sheet opens over the tab on screen (r12 fix7 frame 1, 5)
  // it opens at once, listing what was saved; the questions' own items join once read (r12 audit11 frame 1, questions 1)
  function openSheet(c, key) {
    ctx = ctx || c;
    if (key && S.armed) return arm();
    S.armed = true; S.sendKey = !!key; S.gen = false;
    if (!D || stale) readFor(c);
    readOthers(c);
    if (S.copyOf === undefined) findCopy(c).then(relist);
    if (onQ() && D) return draw(true);
    host = host || document.body.appendChild(Object.assign(document.createElement('div'), {className: 'area-questions tab-questions qhost'}));
    host.onclick = onClick; host.oninput = onInput;
    drawHost();
    const b = key && host.querySelector('[data-send]:not([disabled])'); if (b) b.focus();
  }
  // shortcut: exposed for tests in a browser console only
  P.questionsState = () => ({S, D});
})();
