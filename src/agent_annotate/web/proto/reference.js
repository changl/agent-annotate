/* Reference tab: plans by topic, the go-live checklist, Windmill workflows, designs, app text and findings (build-list stage 3); documents are in Pages & links.
   Ported from round9/final/mock.html (reference, viewer, checklistHtml, ftree, the copy library's pairs view) onto the module contract.
   Saves use today's endpoints: api/plan-topics (rename, combine, move) and api/comments (notes, Undo = DELETE). */
(function () {
  const P = window.Proto;
  const S = {q: '', sec: 'all', kind: '', sel: '', fx: new Set(), rv: {}, marks: true, clf: new Set(), open: new Set(),
    trn: '', tmerge: '', note: '', scroll: false, reopen: new Map(), rsent: new Map(), appr: new Set(), hl: '', cp: new Map(), cpEd: '', cq: ''};  // reopen, rsent (sent reopens: [time, why]), appr (approved items) and cp (copy-library choices): kept in this browser, the prototype sends nothing
  let ctx, D, el, mine = [];  // mine: notes written in this visit, so Undo can take them back
  // reopen, rsent, cp and appr go with the next Send: kept in prefs (draft:ref) like every draft, so a reload keeps them while
  // "Unsent answers and notes" is on (r12 fix8); notes come back from the server, or on a copy from its simulation (P.copyData)
  let kept = false;
  function restoreDrafts() {
    if (kept || !ctx) return;
    kept = true;
    const s = ctx.prefs.get('draft:ref', null);
    if (s) { S.reopen = new Map(s.reopen || []); S.rsent = new Map(s.rsent || []); S.cp = new Map(s.cp || []); S.appr = new Set(s.appr || []); LBL = s.lbl || {}; SNOTES = s.notes || []; }
  }
  // what Send names each draft and the unsent notes, saved with the drafts: after a reload Send lists them at once,
  // while reference.json is still on its way or if it fails (r12 fix10 frame 1, reference 2); the feed replaces them once in
  let LBL = {}, SNOTES = [];
  const keepDrafts = () => { if (kept) ctx.prefs.set('draft:ref', {reopen: [...S.reopen], rsent: [...S.rsent], cp: [...S.cp], appr: [...S.appr], lbl: LBL, notes: SNOTES}); };
  // a task opened from a checklist pill: closing its panel in Running comes back here with the checklist open, as in the mock
  let taskBack = '';
  // the store's own links are refused from inside its sandbox, so it asks this page to open the next of its pages
  addEventListener('message', e => { const f = document.querySelector('iframe.rf-embed[src]'), h = e.data && e.data.rbxStore;
    if (f && e.source === f.contentWindow && typeof h === 'string' && /^[\w-]+\.html(\?[\w=&%.-]*)?$/.test(h)) f.src = new URL(h, f.src).href; });
  const backFromTask = () => { if (taskBack && location.hash.startsWith('#running')) { const id = taskBack; taskBack = ''; setTimeout(() => ctx.go('reference', id), 0); } };
  // capture phase: Running redraws its panel away while handling the same event
  document.addEventListener('click', e => { if (e.target.closest('.tab-running .tpanel [data-task=""]')) backFromTask(); }, true);
  addEventListener('keydown', e => { if (e.key === 'Escape' && document.querySelector('.tab-running .tpanel') && !(e.target.closest && e.target.closest('textarea,input'))) backFromTask(); }, true);
  addEventListener('hashchange', () => { if (!location.hash.startsWith('#running')) taskBack = ''; });
  const blocks = {}, loading = {};
  const ico = (n, l) => P.icon(n, l), pl = (n, a, b) => `${n} ${n === 1 ? a : b}`;
  const esc = s => ctx.esc(s);
  const dm = s => { const d = new Date(String(s).slice(0, 10) + 'T12:00'); return isNaN(d) ? '' : d.toLocaleDateString('en-GB', {day: 'numeric', month: 'short'}); };
  const KN = {plan: 'Plans', check: 'Checklists', design: 'Diagrams and designs', text: 'App text', data: 'Sheets and findings', flow: 'Workflows', mem: 'Memory'};  // documents: Pages & links
  const KG = {...KN, decision: 'Decisions'};  // group names: decisions are plans, listed apart from the topics
  const SN = {prop: ['Proposed', 'Waits on your decision: something the agent proposed'], ok: ['Approved', 'You approved it, or it was decided'], ref: ['For reference', 'Kept for looking things up']};
  const BST = {closed: 'done', 'in progress': 'progress', blocked: 'blocked', deferred: 'waiting', open: 'none'};

  /* ---------- changed since you last looked: one time per entry, kept in this browser ---------- */
  // shortcut: before his first visit everything from the last 14 days counts as changed; a server-side seen store would follow him across browsers
  const firstLook = () => { let b = ctx.prefs.get('ref-first'); if (!b) { b = new Date(Date.now() - 14 * 864e5).toISOString().slice(0, 16); ctx.prefs.set('ref-first', b); } return b; };
  const seen = () => ctx.prefs.get('ref-seen', {});
  const changed = (id, stamp) => !!stamp && String(stamp).replace(' ', 'T') > (seen()[id] || firstLook());
  const markSeen = ids => { const s = seen(), now = new Date().toISOString().slice(0, 16); ids.forEach(i => s[i] = now); ctx.prefs.set('ref-seen', s); ctx.refreshChips(); };

  /* ---------- rows ---------- */
  // shortcut: filing (Proposed, Approved, For reference) is kept in this browser; no reviewer endpoint moves a plan between sections yet
  const filed = () => ctx.prefs.get('ref-file', {}), stOf = p => filed()[p.id] || p.st;
  const lastTs = p => p.revs[p.revs.length - 1][1], xOf = id => ((D && D.extras) || []).find(x => x.id === id);
  const nSteps = ss => ss.reduce((n, s) => n + 1 + nSteps(s.sub || []) + (s.br || []).reduce((m, b) => m + nSteps(b[1]), 0), 0);
  function rows() {
    const out = D.plans.map(p => ({id: p.id, t: p.t, m: `${pl(p.revs.length, 'revision', 'revisions')} · changed ${dm(lastTs(p))}`, kind: p.kind, st: stOf(p),
      g: p.kind !== 'plan' ? 'k:' + p.kind : p.id.startsWith('decision-') ? 'k:decision' : 't:' + p.topic, p, stamp: lastTs(p), s: p.topic}));
    for (const x of D.extras || []) out.push({id: x.id, t: x.t, m: x.m || (x.find ? `${dm(x.d)} · ${pl(x.find.items.length, 'finding', 'findings')}` : `from the project folder · ${x.from.split('/').pop()} · changed ${dm(x.d)}`), kind: x.kind, st: stOf(x),
      g: x.kind === 'plan' ? 't:Plans' : 'k:' + x.kind, x, stamp: x.d, s: (x.md || (x.parts ? JSON.stringify(x.parts) : '') || (x.find ? x.find.conclusion + ' ' + x.find.items.map(f => f.label + ' ' + f.text).join(' ') : '')
        || (x.copy ? x.copy.map(c => c[0] + ' ' + c[1]).join(' ') : '') || (x.fset ? x.fset.items.map(f => f.t + ' ' + f.a).join(' ') : '') || (x.blocks ? x.blocks.map(b => b[0] === 'img' ? b[2] : b[1]).join(' ') : '') || x.note || '').slice(0, 60000)});  // finds words inside them too
    for (const f of D.flows) out.push({id: f.id, t: f.t, m: `Windmill · runs ${f.when} · ${pl(nSteps(f.steps), 'step', 'steps')} · ${f.last ? `last run ${dm(f.last.at)}, ${f.last.ok ? 'passed' : 'failed'}` : 'not run yet'}`,
      kind: 'flow', st: 'ref', g: 'k:flow', f, stamp: f.edited, s: f.what + ' ' + JSON.stringify(f.steps.map(x => x.n))});
    out.forEach(r => r.ch = changed(r.id, r.stamp));
    out.push({id: 'mem:later', t: 'Memory tree', m: 'later: what the agents remember about this project, as a tree you can open', kind: 'mem', st: 'ref', g: 'k:mem', later: true});
    return out;
  }
  const countChanged = () => rows().filter(r => r.ch).length;

  /* ---------- notes: any line, table, picture, chart or step takes one ---------- */
  const allNotes = () => [...D.notes, ...mine.filter(n => !D.notes.some(x => x.id === n.id))];
  const notesAt = k => allNotes().filter(n => n.a === k);
  const planOf = k => { const m = /^ref:([^~]+)~/.exec(k); return m && D.plans.find(p => p.id === m[1]); };
  function noteMeta(k) {
    if (k.startsWith('chk:') && D.checklist) return {category: 'plans', doc: 'plan:' + D.checklist.plan, version: D.checklist.version};
    const p = planOf(k);
    if (!p) return {};
    const v = k.split('~')[1];
    return {category: 'plans', doc: 'plan:' + p.id, version: p.revs.some(r => r[0] === v) ? v : p.current};
  }
  // a marker is a control: it lists the notes on its line or, on a picture, at its point, with + Comment (catalog 25, r12 audit15 reference 2)
  const pin = k => { const n = notesAt(k).length; return n ? `<button class="rf-pin" data-spot="${esc(k)}" aria-expanded="${S.spot === k && !S.pin}" title="${pl(n, 'note', 'notes')} here: list them" aria-label="${pl(n, 'note', 'notes')} here: list them">${ico('note')}${n}</button>` : ''; };
  const NK = () => P.notes;
  const cutq = s => s.length > 60 ? s.slice(0, 58).trimEnd() + '…' : s;
  // what a note is on: selected words, a spot on a picture (numbered as its pin), or the whole line
  const onWhat = (t, no) => !t ? '' : t.quote ? ` on “${esc(cutq(t.quote))}”` : t.offset ? ` at spot ${no || '+'} on the picture` : '';
  const spotNo = (k, n) => notesAt(k).filter(x => x.target && x.target.offset && !x.closed).indexOf(n) + 1;  // a closed note leaves the picture
  const spots = k => notesAt(k).filter(n => n.target && n.target.offset && !n.closed).map((n, i) => `<button class="pinm" data-pin="${esc(n.id)}" style="left:${n.target.offset.dx * 100}%;top:${n.target.offset.dy * 100}%" aria-expanded="${S.pin === n.id}" title="The notes at this point" aria-label="Note at spot ${i + 1}: the notes at this point">${i + 1}</button>`).join('')
    + (S.note === k && S.tgt && S.tgt.offset ? `<span class="pinm new" style="left:${S.tgt.offset.dx * 100}%;top:${S.tgt.offset.dy * 100}%">+</span>` : '');
  // one note: his unsent one with Undo; a sent one with the shared lifecycle (Re-open, View resolution, Move, Close); a closed one folded with Re-open (r12 audit15 reference 3)
  function noteLine(k, n) {
    const K = NK(), hd = `${ico('note')}<b>${esc(n.who)}</b> · ${esc(dm(n.at))}${onWhat(n.target, spotNo(k, n))}`, cls = `rf-nt${S.hl === n.id ? ' rf-hl' : ''}`;
    if (n.closed) return `<div class="${cls} rf-closed" data-nid="${esc(n.id)}"><span class="rf-nw">${ico('archive')} Note closed</span> <span class="mut">${esc(n.text)}</span><span class="nacts">${K.closedActs(n)}</span></div>`;
    if (!n.sent) return `<div class="${cls}" data-nid="${esc(n.id)}"><span class="rf-nw">${hd}</span> ${esc(n.text)}${mine.some(x => x.id === n.id) ? ` <button class="lk small" data-nundo="${esc(n.id)}">Undo</button>` : ''}</div>`;
    return `<div class="${cls}${S.move === n.id ? ' moving' : ''}" data-nid="${esc(n.id)}"><span class="rf-nw">${hd}</span> ${esc(n.text)} ${K.words(ctx, n)} ${K.view(n)}<span class="nacts">${K.acts(ctx, n, S.move === n.id)}</span></div>`;
  }
  // the list a marker opens: on its line, or at a picture pin's point (S.pin)
  function spotList(k, ns) {
    const p = S.pin && ns.find(n => n.id === S.pin), sl = p ? NK().near(ns, p) : ns;
    return NK().spot(ctx, sl.map(n => [n, (n.target && n.target.offset ? spotNo(k, n) : ns.indexOf(n) + 1) || '·']), p ? 'at this point' : 'on this line', `data-spotadd="${esc(k)}"${p ? ` data-spotpin="${esc(p.id)}"` : ''}`);
  }
  function noteList(k, dlg) {
    const ns = notesAt(k), box = S.note === k && !S.full === !dlg;  // the open picture viewer holds the composer for its picture
    const list = S.spot === k && !S.full === !dlg && ns.length;
    if (!ns.length && !box) return '';
    return `<div class="rf-notes">${list ? spotList(k, ns) : ''}${ns.map(n => noteLine(k, n)).join('')}
      ${box ? `<div class="rf-box">${S.tgt ? `<div class="small rf-on">New note${onWhat(S.tgt)}</div>` : ''}<textarea id="rf-nt" rows="3" placeholder="Write a note for the agent: a question, a change, or ask for another version" aria-label="Your note"></textarea>
        <div class="rf-acts"><button class="btn sm pri" data-nsave="${esc(k)}">Save note</button><button class="btn sm" data-ncancel>Cancel</button><span class="small mut">Saved on this page for the agent</span></div></div>` : ''}</div>`;
  }
  const at = (k, label) => `data-line="${esc(k)}" data-label="${esc(String(label || '').slice(0, 80))}"`;

  /* ---------- a plan revision, read from today's plans/<id>/<v>.html as blocks ---------- */
  const CHROME = 'header.hdr,aside,nav,#popover,#legend,script,style,button,select,textarea,input,noscript,template,svg';
  const BLOCK = /^(P|DIV|SECTION|ARTICLE|MAIN|H[1-6]|UL|OL|LI|TABLE|PRE|FIGURE|IMG|BLOCKQUOTE|DETAILS|SUMMARY|DL|DT|DD|HR|HEADER|FOOTER)$/;
  const pics = {};  // embedded picture -> object URL, shared by every revision so the same picture pairs as unchanged
  const pic = (sha, b64) => pics[sha] || (pics[sha] = URL.createObjectURL(new Blob([Uint8Array.from(atob(b64), c => c.charCodeAt(0))], {type: b64.startsWith('iVBOR') ? 'image/png' : 'image/jpeg'})));
  function parse(html) {
    const doc = new DOMParser().parseFromString(html, 'text/html'), out = [], clean = s => s.replace(/[\s\u0001]+/g, ' ').trim(), T = e => clean(e.textContent);
    let emb = {};  // pictures some plans carry inline, by hash: <img src="" data-embedded="<sha>">
    try { const j = doc.getElementById('embedded-captures'); if (j) emb = JSON.parse(j.textContent); } catch {}
    doc.querySelectorAll(CHROME).forEach(e => e.remove());
    doc.querySelectorAll('br').forEach(b => b.replaceWith('\u0001'));  // a line break starts a new line, as in the mock
    const img = e => { const h = e.getAttribute('data-embedded'), s = (e.getAttribute('src') || '').replace(/^\/annotate\/reviews\/[^/]+\//, '');
      const u = h && emb[h] ? pic(h, emb[h]) : s && !s.startsWith('data:') ? new URL(s, location.origin + ctx.base).href : s.startsWith('data:image/') ? s : '';
      if (u) out.push(['img', u, e.getAttribute('alt') || '']); };
    (function walk(n) {
      for (const e of n.children) {
        const t = e.tagName;
        if (/^H[1-6]$/.test(t)) { const x = T(e); if (x) out.push(['h', x]); }
        else if (t === 'TABLE') { const r = [...e.rows].map(row => [...row.cells].map(T)).filter(row => row.some(Boolean)); if (r.length) out.push(['tbl', r.flat().join(' '), r, !!e.querySelector('th')]); }
        else if (t === 'PRE') out.push(['pre', e.textContent.replace(/\n+$/, '')]);
        else if (t === 'IMG') img(e);
        else if (t === 'LI') { const c = e.cloneNode(true); c.querySelectorAll('ul,ol,table,pre').forEach(x => x.remove()); const x = T(c); if (x) out.push(['li', x]); e.querySelectorAll(':scope > ul, :scope > ol').forEach(walk); }
        else if ([...e.children].some(c => BLOCK.test(c.tagName))) walk(e);
        else { e.querySelectorAll('img').forEach(img); e.textContent.split('\u0001').map(clean).filter(Boolean).forEach(x => out.push([t === 'DT' || t === 'SUMMARY' ? 'h' : 'p', x])); }
      }
    })(doc.body);
    return out;
  }
  // a revision is read up to three times: the tunnel answers 502 now and then; a failed read is not kept, so Try again reads it afresh
  const get = (u, n = 3) => fetch(u, {cache: 'no-store'}).then(r => r.ok ? r.text() : Promise.reject(new Error('HTTP ' + r.status)))
    .catch(e => n > 1 ? new Promise(ok => setTimeout(ok, 1500)).then(() => get(u, n - 1)) : Promise.reject(e));
  function need(id, v) {
    const k = id + '~' + v;
    if (blocks[k] || loading[k]) return blocks[k];
    loading[k] = get(`${ctx.base}plans/${encodeURIComponent(id)}/${encodeURIComponent(v)}.html`)
      .then(h => { blocks[k] = parse(h); }, e => { blocks[k] = Object.assign([], {err: e.message}); })
      .then(() => draw());
    return null;
  }
  const retry = (id, v) => { const k = id + '~' + v; delete blocks[k]; delete loading[k]; draw(); };

  /* word diff and block pairing, as in the mock (cycle 6, c W2) */
  function wdiff(a, b) {
    const x = a.split(' '), y = b.split(' '), n = x.length, m = y.length;
    if (n * m > 60000) return esc(b);
    const L = Array.from({length: n + 1}, () => new Uint16Array(m + 1));
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
    const out = []; let i = 0, j = 0;
    while (i < n && j < m) { if (x[i] === y[j]) { out.push(esc(x[i])); i++; j++; } else if (L[i + 1][j] >= L[i][j + 1]) out.push(`<del>${esc(x[i++])}</del>`); else out.push(`<ins>${esc(y[j++])}</ins>`); }
    while (i < n) out.push(`<del>${esc(x[i++])}</del>`); while (j < m) out.push(`<ins>${esc(y[j++])}</ins>`);
    return out.join(' ');
  }
  const wset = s => new Set(String(s).toLowerCase().split(/\W+/).filter(Boolean));
  const alike = (p, q) => { const a = wset(p), b = wset(q); let c = 0; a.forEach(w => b.has(w) && c++); return c / Math.max(1, a.size, b.size); };
  function alignBlocks(A, B) {
    const key = b => b[0] + '\u0001' + b[1], x = A.map(key), y = B.map(key), n = x.length, m = y.length, out = [];
    // pair only the middle that differs: long plans (the car catalog) change a few paragraphs between equal starts and ends
    let s0 = 0, e0 = 0;
    while (s0 < n && s0 < m && x[s0] === y[s0]) s0++;
    while (e0 < n - s0 && e0 < m - s0 && x[n - 1 - e0] === y[m - 1 - e0]) e0++;
    const mn = n - s0 - e0, mm = m - s0 - e0, ys = new Set(y.slice(s0, m - e0)), xs = new Set(x.slice(s0, n - e0));
    const L = mn * mm > 4e6 ? null : Array.from({length: mn + 1}, () => new Uint16Array(mm + 1));
    if (L) for (let i = mn - 1; i >= 0; i--) for (let j = mm - 1; j >= 0; j--) L[i][j] = x[s0 + i] === y[s0 + j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
    // shortcut: a middle too long for the table pairs greedily by exact match; fine while revisions edit a few spots
    const dropA = (i, j) => L ? L[i + 1 - s0][j - s0] >= L[i - s0][j + 1 - s0] : !ys.has(x[i]) || xs.has(y[j]);
    let ga = [], gb = [];
    const txt = b => b[0] === 'img' ? b[2] : b[1];
    const flush = () => { let bi = 0;
      for (const a of ga) { let best = -1, bs = 0.4;
        for (let t = bi; t < gb.length; t++) { if (A[a][0] !== B[gb[t]][0]) continue; const s = alike(txt(A[a]), txt(B[gb[t]])); if (s > bs) { bs = s; best = t; } }
        if (best < 0) { out.push({k: 'del', a}); continue; }
        for (let t = bi; t < best; t++) out.push({k: 'add', b: gb[t]});
        out.push({k: 'chg', a, b: gb[best]}); bi = best + 1; }
      for (let t = bi; t < gb.length; t++) out.push({k: 'add', b: gb[t]});
      ga = []; gb = []; };
    let i = 0, j = 0;
    for (; i < s0; i++, j++) out.push({k: 'same', a: i, b: j});
    while (i < n - e0 && j < m - e0) { if (x[i] === y[j]) { flush(); out.push({k: 'same', a: i++, b: j++}); } else if (dropA(i, j)) ga.push(i++); else gb.push(j++); }
    while (i < n - e0) ga.push(i++); while (j < m - e0) gb.push(j++); flush();
    for (; i < n; i++, j++) out.push({k: 'same', a: i, b: j});
    return out;
  }

  const untag = t => t.replace(/^[A-Za-z0-9][\w.-]{3,}:\s*/, '');  // a workstream name before the title is a worker's, not his
  /* a task a plan names reads "title · bead id · state", coloured by its state */
  const beadIn = h => h.replace(/\b(?:FLD|RBX|agent-annotate)-[a-z0-9]{3,6}(?:\.\d+)*\b/g, id => { const b = D.beads[id]; if (!b) return id;
    const t = untag(b[0]), cut = t.length > 40 ? t.slice(0, 38).trimEnd() + '…' : t;
    return `<button class="rf-bd lk st-${BST[b[1]] || 'none'}" data-task="${id}" title="Open its task: ${esc(t)}"><i class="dot"></i>${esc(cut)} · <code>${id}</code> · ${esc(b[1])}</button>`; });

  /* pictures open full size at 25-100% of the screen width, each remembering its own; the default comes from the settings menu */
  const ZS = [25, 50, 75, 100], zOf = k => ctx.prefs.get('ref-zoom', {})[k] || ctx.prefs.get('zoomDef', 75);
  // the caption line every document reader shares (Proto.media, with Questions): "Picture N · caption · 25-100% · ⤢ Full size"
  let picN = 0;  // pictures numbered in reading order, from 1 in each document the viewer draws
  const zoomBar = (k, src, cap, n) => { const za = ` data-zk="${esc(k)}"`;
    return `<figcaption class="qcap">${P.media.line(P.media.label(n), cap ? esc(cap) : '', P.media.ctl(zOf(k), src, ` data-zoom="${zOf(k)}"${za}`, za))}</figcaption>`; };
  function zoomView() {
    const f = S.full;
    if (!f) return '';
    return `<div class="zoomv" role="dialog" aria-modal="true" aria-label="Full-size picture"><div class="zbar"><b class="small">${esc(cutq(f.cap || 'Picture'))}</b><span class="seg">${ZS.map(z => `<button data-zoom="${z}" data-zk="${esc(f.k)}" aria-pressed="${z === f.z}">${z}%</button>`).join('')}</span><span class="small mut hide-ph">of the screen width · tap a spot to write a note · <kbd>Esc</kbd> closes</span><span class="spacer"></span><button class="btn sm" data-zclose>Close</button></div>
      <div class="qpinwrap pic" ${at(f.k, 'Picture: ' + f.cap)} style="width:${f.z}vw"><img src="${esc(f.src)}" alt="${esc(f.cap || 'Picture')}">${spots(f.k)}</div>
      <div class="zn">${noteList(f.k, true)}</div></div>`;
  }

  // one block: heading, paragraph, list line, code, table or picture; `inner` replaces the text (diff marks)
  function block(b, k, inner, tag) {
    const [kind, t, x, hd] = b, tg = tag || '', a = at(k, kind === 'img' ? 'Picture: ' + x : kind === 'tbl' ? 'Table: ' + x[0].join(' · ') : t);
    // each body row takes its own note (key <table>~r<n>); the header row notes the whole table
    const rk = ri => ri === 0 && hd ? k : `${k}~r${ri}`;
    const body = kind === 'tbl' ? `<div class="tblw" style="--c:${Math.max(...x.map(r => r.length))}" ${a}>${hd ? '' : pin(k)}<table>${x.map((r, ri) => `<tr ${ri === 0 && hd ? '' : at(rk(ri), 'Row: ' + r.join(' · '))}>${r.map((c, ci) => ri === 0 && hd ? `<th>${ci ? '' : pin(k)}${esc(c)}</th>` : `<td>${ci ? '' : pin(rk(ri))}${beadIn(esc(c))}</td>`).join('')}</tr>`).join('')}</table>${tg}</div>${x.map((_, ri) => ri === 0 && hd ? '' : noteList(rk(ri))).join('')}`
      : kind === 'img' ? (n => `<figure ${a}>${pin(k)}<span class="qpinwrap"><img src="${esc(t)}" alt="${esc(x || 'Picture')}" data-zcap="${esc(`Picture ${n}${x ? ' · ' + x : ''}`)}" loading="lazy">${spots(k)}</span>${zoomBar(k, t, x, n)}${tg}</figure>`)(++picN)
      : kind === 'pre' ? `<div class="rf-code" ${a}>${pin(k)}${P.media.code(t)}${tg}</div>`
      : `<${kind === 'h' ? 'h4' : 'p'} class="${kind === 'li' ? 'li' : ''}" ${a}>${pin(k)}${beadIn(inner || esc(t))}${tg}</${kind === 'h' ? 'h4' : 'p'}>`;
    return body + noteList(k);
  }

  /* ---------- the list ---------- */
  function topicHead(t, n) {
    const real = D.topics.includes(t), others = D.topics.filter(x => x !== t && x !== 'Unsorted');
    if (S.trn === t) return `<div class="r8gh">${ico('plan')}<input type="text" id="rf-trn" value="${esc(t)}" aria-label="New name for the topic ${esc(t)}"><button class="btn sm pri" data-trnsave="${esc(t)}">Save</button><button class="ib" data-trn="" title="Cancel" aria-label="Cancel renaming">${ico('x')}</button></div>`;
    return `<div class="r8gh">${ico('plan')}<span class="gt">${esc(t)}</span><span class="n">${n}</span><span class="spacer"></span>${real ? `<button class="tact" data-trn="${esc(t)}" title="Rename this topic">${ico('edit')}<span>Rename</span></button><button class="tact" data-tmerge="${esc(t)}" aria-expanded="${S.tmerge === t}" title="Combine this topic with another: its plans move into that topic, and this one goes away">${ico('combine')}<span>Combine</span></button>` : ''}
      ${S.tmerge === t ? `<div class="pop" role="menu"><div class="small mut">Combine with… its ${pl(n, 'plan moves', 'plans move')} into</div>${others.map(x => `<button role="menuitem" data-tmergeto="${esc(x)}">${esc(x)}</button>`).join('') || '<div class="small mut">No other topic yet</div>'}</div>` : ''}</div>`;
  }
  const stPill = s => `<span class="rf-st ${s}" title="${esc(SN[s][1])}"><i></i>${SN[s][0]}</span>`;
  const chg = '<span class="rf-new" title="Changed since you last looked">changed</span>';
  const row = r => r.later ? `<button class="r8row later" aria-disabled="true" title="Comes later: ${esc(r.m)}">${ico(r.kind)}<span class="t">${esc(r.t)}</span><span class="s"><span class="rf-st ref"><i></i>Later</span></span><span class="m">${esc(r.m)}</span></button>`
    : `<button class="r8row" data-ref="${esc(r.id)}" aria-pressed="${S.sel === r.id}">${ico(r.kind)}<span class="t">${esc(r.t)} ${r.ch ? chg : ''}</span><span class="s">${stPill(r.st)}</span><span class="m">${esc(r.m)}</span></button>`;

  function stepKinds(s) {
    return [s.ai ? ['ai', 'AI agent', 'An AI agent does this step'] : s.t === 'script' ? ['code', 'Script', 'A saved script the workflow calls'] : s.t === 'rawscript' ? ['code', 'Inline code', 'A few lines of code kept inside the workflow'] : /loop/.test(s.t) ? ['loop', 'Loop', 'Repeats the steps under it'] : /branch/.test(s.t) ? ['branch', 'Branch', 'Takes one of the paths under it'] : ['code', s.t || 'Step', ''],
      ...(s.wait ? [/\byour\b/i.test(s.n) ? ['hand', 'Waiting for you', 'Stops here until you answer'] : ['mac', 'Hands to a Mac', 'Hands the work to a Mac and waits for its answer']] : []),
      ...(s.stop ? [['branch', 'Can end the run here', 'Ends the run early when its check says so']] : [])];
  }
  const MK = {ok: ['ok', 'Passed'], fail: ['fail', 'Failed'], skipped: ['skp', 'Skipped'], none: ['none', 'Did not run']};
  const mark = (s, what) => { const [c, t] = MK[s] || MK.none; return `<span class="sm9 ${c}" role="img" aria-label="${esc(t + ' ' + what)}" title="${esc(t + ' ' + what)}">${c === 'ok' ? ico('tick') : c === 'fail' ? ico('x') : ''}</span>`; };
  function ftree(ss, k, last, inner) {
    return `<ol class="ftree">${ss.map(s => { const kk = k ? `${k}~${s.id}` : '';
      const m = inner ? '<span></span>' : last ? mark(s.st || 'none', 'last run') : mark('none', 'yet: this workflow has not run');
      return `<li><div class="fs9" ${kk ? at(kk, 'Step: ' + s.n) : ''}>${m}<span class="nm">${kk ? pin(kk) : ''}${esc(s.n)}</span><span class="kd">${stepKinds(s).map(([i, l, t]) => `<span class="kpill${i === 'ai' ? ' ai' : i === 'hand' ? ' wait' : ''}" title="${esc(t)}">${ico(i)}${esc(l)}</span>`).join('')}</span></div>${kk ? noteList(kk) : ''}
        ${s.sub ? `<div class="fgrp">${ico('loop')}Each round</div>${ftree(s.sub, k, last, true)}` : ''}
        ${(s.br || []).map(([l, b, taken]) => `<div class="fgrp${taken ? ' taken' : ''}">${ico('branch')}${esc(l)}${taken ? ' · taken last run' : ''}</div>${b.length ? ftree(b, k, last, true) : '<p class="small mut rf-none">nothing: goes on to the next step</p>'}`).join('')}</li>`; }).join('')}</ol>`;
  }
  const lastRun = f => f.last ? `Last run ${esc(dm(f.last.at))}, ${esc(f.last.at.slice(11))} · ${f.last.ok ? 'passed' : 'failed'} · took ${pl(f.last.s, 'second', 'seconds')}${f.queued ? ` · ${pl(f.queued, 'run', 'runs')} waiting their turn` : ''}` : 'Not run yet';
  const failTree = (f, k) => f.fail.length ? `<div class="fgrp rf-failg">If any step fails</div>${ftree(f.fail, k, false, true)}` : '';
  function flowRow(r) {
    const f = r.f, op = S.fx.has(r.id);
    return `<div class="r9fl"><button class="chev" data-fx="${esc(r.id)}" aria-expanded="${op}" title="${op ? 'Hide' : 'Show'} its steps" aria-label="${op ? 'Hide' : 'Show'} the steps of ${esc(f.t)}">${ico('chev')}</button>${row(r)}</div>${op ? `<div class="r9fx"><p class="small mut">${lastRun(f)}</p>${ftree(f.steps, '', !!f.last)}${failTree(f, '')}</div>` : ''}`;
  }

  function list() {
    const R = rows(), q = S.q.toLowerCase();
    const hit = r => !q || (r.t + ' ' + r.m + ' ' + (r.s || '')).toLowerCase().includes(q);
    const inSt = r => S.sec === 'all' || r.st === S.sec, inK = r => !S.kind || r.kind === S.kind;
    const shown = R.filter(r => hit(r) && inSt(r) && inK(r));
    const stN = s => R.filter(r => hit(r) && inK(r) && (s === 'all' || r.st === s)).length;
    const kN = k => R.filter(r => hit(r) && inSt(r) && r.kind === k).length;
    // topics first (the mock's left column), then the kinds in their chip order
    const KO = [...Object.keys(KN), 'decision'], o = g => g[0] === 't' ? (g === 't:Plans' ? 99 : D.topics.indexOf(g.slice(2))) : 100 + KO.indexOf(g.slice(2));
    const gs = [...new Set(shown.map(r => r.g))].sort((a, b) => o(a) - o(b));
    const nch = R.filter(r => r.ch).length;
    const kinds = Object.keys(KN).filter(k => R.some(r => r.kind === k));  // FastLane Drive has no app text
    const bar = `<div class="r8bar"><input type="search" id="rf-q" placeholder="Find a plan, checklist, design or workflow" aria-label="Find in Reference" value="${esc(S.q)}">
      <span class="rf-chips" role="group" aria-label="State">${['all', 'prop', 'ok', 'ref'].map(s => `<button class="chipb" data-sec="${s}" aria-pressed="${S.sec === s}" title="${s === 'all' ? 'Every item' : esc(SN[s][1])}">${s === 'all' ? 'All' : SN[s][0]} <span class="n">${stN(s)}</span></button>`).join('')}</span>
      <span class="sep" aria-hidden="true"></span><span class="rf-chips" role="group" aria-label="Kind">${kinds.map(k => `<button class="chipb" data-kind="${k}" aria-pressed="${S.kind === k}" title="Only ${KN[k].toLowerCase()}">${ico(k)}${KN[k]} <span class="n">${kN(k)}</span></button>`).join('')}</span>
      <span class="spacer"></span><span class="small mut rf-chl">${nch ? `${chg} ${pl(nch, 'item changed', 'items changed')} since you last looked · <button class="lk small" data-allseen>Mark all as seen</button>` : 'Nothing changed since you last looked'}</span></div>`;
    const lst = gs.length ? `<div class="r8list">${gs.map(g => { const rs = shown.filter(r => r.g === g);
      return `<div class="r8g">${g[0] === 't' ? topicHead(g.slice(2), rs.length) : `<div class="r8gh">${ico(g === 'k:decision' ? 'plan' : g.slice(2))}<span class="gt">${KG[g.slice(2)]}</span><span class="n">${rs.length}</span></div>`}${(g === 'k:decision' && !q && !S.open.has(g) ? rs.slice(0, 6) : rs).map(r => r.kind === 'flow' ? flowRow(r) : row(r)).join('')}${g === 'k:decision' && !q && rs.length > 6 ? `<button class="lk small rf-more" data-fold="${g}">${S.open.has(g) ? 'Show the first 6' : `Show all ${rs.length}`}</button>` : ''}</div>`; }).join('')}</div>` : '<p class="mut">Nothing matches.</p>';
    return bar + lst;
  }

  /* ---------- Markdown as blocks ---------- */
  function mdBlocks(t) {
    const out = [], L = t.replace(/\r/g, '').split('\n'), inl = s => s.replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1').replace(/(\*\*|__|`)(.+?)\1/g, '$2').replace(/<[^>]+>/g, '');
    let i = 0, para = [];
    const flush = () => { if (para.length) out.push(['p', inl(para.join(' '))]); para = []; };
    if (L[0] === '---') { i = 1; while (i < L.length && L[i] !== '---') i++; i++; }  // front matter
    while (i < L.length) {
      const l = L[i];
      if (/^\s*```/.test(l)) { flush(); const b = []; i++; while (i < L.length && !/^\s*```/.test(L[i])) b.push(L[i++]); i++; out.push(['pre', b.join('\n')]); continue; }
      if (/^#{1,6}\s/.test(l)) { flush(); out.push(['h', inl(l.replace(/^#+\s*/, ''))]); i++; continue; }
      if (/^\s*\|/.test(l)) { flush(); const r = []; while (i < L.length && /^\s*\|/.test(L[i])) { const c = L[i].trim().replace(/^\||\|$/g, '').split('|').map(x => inl(x.trim())); if (!c.every(x => /^:?-{2,}:?$/.test(x))) r.push(c); i++; } out.push(['tbl', r.flat().join(' '), r, true]); continue; }
      if (/^\s*([-*+]|\d+\.)\s+/.test(l)) { flush(); out.push(['li', inl(l.replace(/^\s*([-*+]|\d+\.)\s+/, ''))]); i++; continue; }
      if (!l.trim() || /^(-{3,}|\*{3,})$/.test(l.trim())) { flush(); i++; continue; }
      para.push(l.trim()); i++;
    }
    flush();
    return out;
  }

  /* ---------- the go-live checklist: one row per item, filter chips as on GitHub's issue list ---------- */
  const CM = {done: ['ok', 'Done', 'done'], 'in progress': ['in', 'In progress', 'progress'], 'not started': ['todo', 'Not started', 'none'], blocked: ['blocked', 'Blocked', 'blocked'],
    closed: ['ok', 'Task closed', 'done'], open: ['todo', 'Task open', 'none']};
  const cm = (s, pre = '') => { const [c, t] = CM[s] || ['todo', s]; return `<span class="sm9 ${c}" role="img" aria-label="${esc(pre + t)}" title="${esc(pre + t)}">${c === 'ok' ? ico('tick') : ''}</span>`; };
  function checklistHtml() {
    const cl = D.checklist, by = {};
    cl.items.forEach(r => by[r[2]] = (by[r[2]] || 0) + 1);
    const whoOf = w => /^Chang\b/.test(w) ? 'You' : /unassigned/i.test(w) ? 'No one yet' : 'An agent', pfOf = p => p === 'Shared' ? 'Both' : p, bi = b => D.beads[b];
    const val = {pf: r => pfOf(r[0]), st: r => r[2], who: r => whoOf(r[3]), bd: r => (bi(r[4]) || [])[1] || 'none'};
    const G = [['st', 'State', ['blocked', 'in progress', 'not started', 'done']], ['pf', 'Platform', ['iOS', 'Android', 'Both']], ['who', 'Who', ['You', 'An agent', 'No one yet']], ['bd', 'Its task', ['open', 'in progress', 'blocked', 'closed']]];
    const on = g => G.find(x => x[0] === g)[2].filter(v => S.clf.has(g + '~' + v)), pass = (r, skip) => G.every(([g]) => g === skip || !on(g).length || on(g).includes(val[g](r)));
    const shown = cl.items.map((r, i) => [r, i]).filter(([r]) => pass(r)), nOf = (g, v) => cl.items.filter(r => pass(r, g) && val[g](r) === v).length;
    const lab = (g, v) => g === 'st' ? `${cm(v)}${CM[v][1]}` : g === 'bd' ? `${cm(v)}${v[0].toUpperCase() + v.slice(1)}` : esc(v);
    const chips = `<div class="r9chips" role="group" aria-label="Filter the checklist">${G.map(([g, gl, vs]) => `<span class="cg"><span class="cgl">${gl}</span>${vs.map(v => { const n = nOf(g, v), p = S.clf.has(g + '~' + v);
        return `<button class="chipb" data-clf="${g}~${esc(v)}" aria-pressed="${p}"${!n && !p ? ' disabled' : ''} title="${p ? 'Stop filtering by' : 'Show only'} ${esc(gl.toLowerCase())}: ${esc(v)}">${lab(g, v)}<span class="n">${n}</span></button>`; }).join('')}</span>`).join('')}
      ${S.clf.size ? `<span class="small"><b>${pl(shown.length, 'item', 'items')} shown</b> of ${cl.items.length} · <button class="lk small" data-clf="">Clear filters</button></span>` : ''}</div>`;
    const crow = ([[pf, it, st, who, bead], i]) => { const b0 = bi(bead), t = b0 && untag(b0[0]), k = 'chk:' + i;
      return `<div class="cl9" ${at(k, it)}>${cm(st)}<span class="tx">${pin(k)}${esc(it)}<span class="small mut rf-task">${bead ? `<button class="pl9 bid9" ${b0 ? `data-task="${esc(bead)}" title="Its task: ${esc(t)} · ${esc(b0[1])}. Opens it in Running"` : 'disabled title="Not on the board"'}>${cm(b0 ? b0[1] : 'none', 'Task ')}${esc(bead)}</button> ${esc(t ? (t.length > 70 ? t.slice(0, 68).trimEnd() + '…' : t) : 'not on the board')} · ${esc(b0 ? b0[1] : 'unknown')}` : 'no task'}</span></span>
        <span class="pl"><span class="pl9 pf" title="Platform">${esc(pfOf(pf))}</span><span class="pl9 who9${whoOf(who) === 'You' ? ' you' : ''}" title="Who does it">${whoOf(who)}</span></span></div>${noteList(k)}`; };
    const COL = {done: 'var(--st-done)', 'in progress': 'var(--st-progress)', 'not started': 'var(--st-none)', blocked: 'var(--st-blocked)'};
    return `<div class="rf-chart" ${at('chk:chart', 'The checklist chart')}>${pin('chk:chart')}<b>${pl(cl.items.length, 'item', 'items')}</b><span class="prog2" role="img" aria-label="${Object.entries(by).map(([s, n]) => `${n} ${s}`).join(', ')}">${Object.entries(by).map(([s, n]) => `<i style="flex:${n};background:${COL[s]}" title="${n} ${s}"></i>`).join('')}</span>
      <span class="rf-legend">${Object.entries(by).map(([s, n]) => `<span>${cm(s)}${n} ${esc(s)}</span>`).join('')}</span><span class="small mut">from the plan of ${esc(dm(cl.when))}</span></div>${noteList('chk:chart')}
      ${chips}<div class="chkl">${shown.map(crow).join('') || '<p class="mut">No item matches these filters.</p>'}</div>`;
  }

  /* ---------- the opened entry, under the list ---------- */
  function planView(p) {
    const n = p.revs.length, last = n - 1, cur = S.rv[p.id] != null ? S.rv[p.id] : last, k = 'ref:' + p.id;
    const B = need(p.id, p.revs[cur][0]), A = cur === last && n > 1 ? need(p.id, p.revs[last - 1][0]) : [];
    const isCheck = D.checklist && p.id === D.checklist.plan;
    let doc, csum = '';
    if (!B || !A) doc = '<p class="mut">Reading this revision…</p>';
    else if (B.err) doc = `<p class="rf-err">Revision ${cur + 1} could not be read just now (${esc(B.err)}). <button class="btn sm" data-retry="${esc(p.revs[cur][0])}">Try again</button></p>`;
    else {
      const v = p.revs[cur][0], key = i => `${k}~${v}~${i}`, mk = S.marks && cur === last && n > 1 && !A.err;  // no marks against a revision that failed to read
      if (mk) {
        const al = alignBlocks(A, B), nk = x => al.filter(y => y.k === x).length, when = `in revision ${n}`, tag = w => ` <span class="rf-tag">${w} ${when}</span>`;
        csum = `${pl(nk('chg'), 'paragraph', 'paragraphs')} changed · ${nk('add')} added · ${nk('del')} removed`;
        doc = al.map(x => x.k === 'same' ? block(B[x.b], key(x.b))
          : x.k === 'chg' ? block(B[x.b], key(x.b), ['img', 'tbl', 'pre'].includes(B[x.b][0]) ? '' : wdiff(A[x.a][1], B[x.b][1]), tag('changed'))
          : x.k === 'add' ? block(B[x.b], key(x.b), ['img', 'tbl', 'pre'].includes(B[x.b][0]) ? '' : `<ins>${esc(B[x.b][1])}</ins>`, tag('added'))
          : `<p class="small"><del>${esc(A[x.a][0] === 'img' ? 'Picture: ' + (A[x.a][2] || '') : A[x.a][0] === 'tbl' ? 'Table: ' + A[x.a][2][0].join(' · ') : A[x.a][1])}</del>${tag('removed')}</p>`).join('');
      } else doc = B.map((b, i) => block(b, key(i))).join('') || '<p class="mut">This revision has no text.</p>';
    }
    const vlist = n > 1 ? `<nav class="vlist" aria-label="Revisions"><h5>${pl(n, 'revision', 'revisions')}</h5>${p.revs.map((r, i) => [r, i]).reverse().map(([[v, ts, label], i]) =>
      `<button class="vrow" data-rv="${i}" aria-current="${i === cur}"><b>Revision ${i + 1} · ${esc(dm(ts))}${i === last ? ' · newest' : ''}</b><span>${esc(i === last && csum ? csum : label || '')}</span></button>`).join('')}</nav>` : '';
    const revbar = n > 1 ? `<div class="revbar"><b>Revision ${cur + 1} of ${n}</b>${cur === last ? A && A.err ? `<span>revision ${n - 1} could not be read just now, so nothing is marked</span><button class="lk small" data-retry="${esc(p.revs[last - 1][0])}">Try again</button>` : `<span>${S.marks ? `${csum ? csum + ', ' : ''}marked word by word against revision ${n - 1}: <del>struck</del> words left, <ins>marked</ins> words came in` : 'marks hidden'}</span><button class="lk small" data-marks>${S.marks ? 'Hide marks' : 'Show marks'}</button>` : `<span>an earlier revision, as it read</span><button class="lk small" data-rv="${last}">Back to the newest</button>`}</div>` : '';
    const text = `<div class="${vlist ? 'r8v' : ''}"><div><div class="doc">${doc}</div></div>${vlist}</div>`;
    const topics = D.topics.filter(t => t !== 'Unsorted');
    const st = stOf(p);
    return `<div class="rf-acts rf-vh">${ico(p.kind)}<b class="rf-vt">${esc(p.t)}</b>${stPill(st)}<span class="spacer"></span>
        <button class="ib" data-link="${esc(p.id)}" title="Copy a link to this item" aria-label="Copy a link to this item">${ico('link')}</button></div>
      ${isCheck ? checklistHtml() + `<details class="rf-det"${S.det ? ' open' : ''}><summary>The checklist plan as written, with its ${pl(n, 'revision', 'revisions')}</summary>${revbar}${text}</details>` : revbar + text}
      ${foot(k, st, p.kind === 'plan' ? `<label class="small mut rf-topic">Topic <select data-move="${esc(p.id)}" aria-label="Topic"><option${p.topic === 'Unsorted' ? ' selected' : ''}>Unsorted</option>${topics.map(t => `<option${t === p.topic ? ' selected' : ''}>${esc(t)}</option>`).join('')}<option value="__new">New topic…</option></select></label>` : '',
        `Click any line, table, picture${isCheck ? ', row or the chart' : ''} or select words to write a note on them. To ask for another version, say so in a note.`)}`;
  }
  // the plan footer, as in the mock: a note, where it is filed, its topic
  const foot = (k, st, topic, hint) => `${noteList(k + '~all')}<div class="rf-acts"><button class="btn sm" data-note="${esc(k)}~all">${ico('note')}Write a note</button>
      <button class="btn sm${S.appr.has(k) ? ' rec' : ''}" data-appr="${esc(k)}" title="Approve it as a whole; goes with your next Send">${S.appr.has(k) ? '✓ Approved · Undo' : 'Approve'}</button>
      <span class="small mut">Filed as</span><span class="seg" role="group" aria-label="Filed as">${['prop', 'ok', 'ref'].map(s => `<button data-plansec="${s}" aria-pressed="${st === s}" title="${esc(SN[s][1])}">${SN[s][0]}</button>`).join('')}</span>
      ${topic}<span class="spacer"></span><span class="small mut">${hint}</span></div>`;
  // a project file the mock files under Reference: Markdown as text, sheets as tables, each line and row open to a note
  // an audit as a findings register, as the mock shows Rebex's etching audit: what was screened, the conclusion, each finding with its proof, Reopen
  function findView(x) {
    const b = x.find, k = 'ref:' + x.id, seen = b.items.filter(f => f.state === 'Rebex mark seen').length;
    const items = b.items.map((f, i) => { const fk = `${x.id}~${i}`, op = (i === 0) !== S.open.has('fd:' + fk), r = S.reopen.get(fk), rs = S.rsent.get(fk);
      return `<div class="grp"><div class="rf-fh"><button class="fold" data-fold="fd:${esc(fk)}" aria-expanded="${op}">${esc(f.label)}</button><span class="tag${f.state === 'No Rebex mark' ? ' high' : ''}">${esc(f.state)}</span>${rs && r === undefined ? `<span class="saved">Reopened · sent ${esc(rs[0])}</span>` : r !== undefined ? `<span class="saved">Reopened</span>${P.inertMark()}<button class="lk small" data-unreopen="${esc(fk)}">Undo</button>` : `<button class="lk small" data-freopen="${esc(fk)}" title="Say it is not settled, with why; the audit's record stays">Reopen</button>`}</div>
        ${r !== undefined ? `<textarea id="rf-ro-${i}" data-reopen="${esc(fk)}" rows="2" placeholder="Why reopen it?" aria-label="Why reopen ${esc(f.label)}">${esc(r)}</textarea>` : ''}
        ${op ? `${block(['p', f.text], `${k}~f~${i}`)}${f.src ? `<div class="figs">${block(['img', f.src, 'Proof: ' + f.label], `${k}~f${i}`)}</div>` : ''}
        <div class="rf-acts small"><span class="grow mut">Proof file: ${esc(f.file)} · fingerprint ${esc(f.sha)} · the original is kept unchanged; this is a copy</span><button class="lk small" data-copy="${esc(f.file)}" data-what="Path">Copy path</button></div>` : ''}</div>`; }).join('');
    return `<div class="rf-acts rf-vh">${ico(x.kind)}<b class="rf-vt">${esc(x.t)}</b>${stPill(stOf(x))}<span class="small mut">${esc(x.from)} · audited ${esc(dm(b.when))} · read-only here</span><span class="spacer"></span><button class="ib" data-link="${esc(x.id)}" title="Copy a link to this item" aria-label="Copy a link to this item">${ico('link')}</button></div>
      <div class="tiles">${b.screened.map(([n, w]) => `<div><b>${n.toLocaleString()}</b><span>${esc(w)} screened</span></div>`).join('')}<div><b>${b.items.length}</b><span>findings, ${seen} with the Rebex mark</span></div></div>
      <p ${at(k + '~c', 'Conclusion')}>${pin(k + '~c')}<b>Conclusion:</b> ${esc(b.conclusion)}</p>${noteList(k + '~c')}
      <p class="small"><b>Timeline:</b> audited ${esc(b.when)} · ${b.untouched ? 'no original photo or catalog choice changed' : 'originals changed'}${b.items.map((f, i) => [f, S.rsent.get(`${x.id}~${i}`)]).filter(([, rs]) => rs).map(([f, [t, why]]) => ` · you reopened “${esc(f.label)}” at ${esc(t)}: “${esc(cutq(why))}”`).join('')}</p>
      ${items}<details class="ddet"><summary>${pl(b.limits.length, 'limit', 'limits')} of this audit</summary><ul>${b.limits.map(l => `<li>${esc(l)}</li>`).join('')}</ul></details>
      ${foot(k, stOf(x), '', 'Click a finding, its proof or the conclusion to write a note on it')}`;
  }
  const head = x => `<div class="rf-acts rf-vh">${ico(x.kind)}<b class="rf-vt">${esc(x.t)}</b>${stPill(stOf(x))}<span class="small mut">${esc(x.m || x.from)} · read-only here</span><span class="spacer"></span><button class="ib" data-link="${esc(x.id)}" title="Copy a link to this item" aria-label="Copy a link to this item">${ico('link')}</button></div>`;
  // the app's text library, as the mock's pairs view: Needs you first, 20 a group; every action is kept in memory and sends nothing
  const RTE = [['bold', '<b>B</b>'], ['italic', '<i>I</i>'], ['strikeThrough', '<s>S</s>'], ['formatBlock:h3', 'Heading'], ['formatBlock:blockquote', 'Quote'], ['insertUnorderedList', '• List'], ['createLink', 'Link'], ['undo', '↶ Undo'], ['redo', '↷ Redo']];
  const CST = {ok: '✓ Approved', held: 'Held back', old: 'Earlier wording chosen', edit: 'Edited'};
  // the editor's formatting, kept on Save: only the tags its buttons make, links only to web or mail addresses
  const RICH = /^(B|STRONG|I|EM|S|STRIKE|DEL|U|H3|BLOCKQUOTE|UL|OL|LI|A|BR|P|DIV)$/;
  function rich(h) {
    const t = document.createElement('template'); t.innerHTML = h;
    (function walk(n) { for (const e of [...n.children]) { walk(e);
      if (!RICH.test(e.tagName)) { e.replaceWith(...e.childNodes); continue; }
      const href = e.tagName === 'A' && /^(https?:|mailto:)/i.test(e.getAttribute('href') || '') ? e.getAttribute('href') : null;
      [...e.attributes].forEach(a => e.removeAttribute(a.name));
      if (href) { e.setAttribute('href', href); e.setAttribute('target', '_blank'); e.setAttribute('rel', 'noopener'); } } })(t.content);
    return t.innerHTML.trim();
  }
  const cpRank = s => s === 'Done' ? 2 : s === 'Held back' ? 1 : 0;  // copy groups: Needs you, Held back, Done
  function copyView(x) {
    const k = 'ref:' + x.id, q = (S.cq || '').toLowerCase(), rank = cpRank, ckOf = i => `${k}~c~${i}`;
    const L = x.copy.map((c, i) => [c, i]).filter(([c]) => !q || (c[0] + ' ' + c[1]).toLowerCase().includes(q));
    const held = x.copy.filter((c, i) => { const s = S.cp.get(ckOf(i)); return s ? s.st === 'held' : c[2] === 'Held back'; }).length;
    const grp = r => { const rs = L.filter(([c]) => rank(c[2]) === r), fk = `cpall:${x.id}:${r}`, all = S.open.has(fk) || !!q, n = rs.length;
      if (!n) return '';
      return `<tr><td colspan="3" class="small"><b>${['Needs you', 'Held back', 'Done'][r]}</b> <span class="mut">· ${pl(n, 'line', 'lines')}</span></td></tr>${(all ? rs : rs.slice(0, 20)).map(([[key, y, nd, old, alts], i]) => {
        const ck = ckOf(i), s = S.cp.get(ck), ed = S.cpEd === ck, txt = s && s.st === 'old' ? esc(old) : s && s.st === 'edit' ? s.html : old && old !== y ? wdiff(old, y) : esc(y);
        return `<tr><td class="rf-ck"><b>${esc(key)}</b><br><span class="tag">${esc(nd)}</span>${alts.length ? ` <span class="small mut">${pl(alts.length, 'other wording', 'other wordings')}, under Edit</span>` : ''}</td><td ${ed ? '' : at(ck, key)}>${ed ? '' : pin(ck)}${txt}${s ? `<span class="cst">${CST[s.st]}</span>${P.inertMark()}` : ''}${ed ? `<div class="rf-acts rf-rtb">${RTE.map(([c, l]) => `<button class="btn sm" data-rte="${c}">${l}</button>`).join('')}</div><div class="rf-rte" contenteditable="true" aria-label="Edit the text of ${esc(key)}">${esc(y)}</div>
          ${alts.length ? `<div class="small mut">Other wordings: ${alts.map(a => `<button class="lk small" data-cpalt="${esc(a)}" title="Put this wording in the editor">${esc(cutq(a))}</button>`).join(' · ')}</div>` : ''}<div class="rf-acts"><button class="btn sm pri" data-cpsave="${esc(ck)}">Save</button><button class="btn sm" data-cpcancel>Cancel</button></div>` : ''}${noteList(ck)}</td>
          <td class="rf-cact">${s ? `<button class="lk small" data-cpundo="${esc(ck)}">Undo</button>` : ed ? '' : `<button class="lk small" data-cpst="${esc(ck)}|ok">Approve</button> · <button class="lk small" data-cpst="${esc(ck)}|held">Hold back</button> · <button class="lk small" data-cped="${esc(ck)}">Edit</button>${old && old !== y ? ` · <button class="lk small" data-cpst="${esc(ck)}|old">Use earlier</button>` : ''}`}</td></tr>`; }).join('')}${n > 20 && !q ? `<tr><td colspan="3" class="small mut">${all ? `All ${n} shown` : `20 of ${n} shown`} · <button class="lk small" data-fold="${esc(fk)}" aria-expanded="${all}">${all ? 'Show the first 20' : `Show all ${n}`}</button></td></tr>` : ''}`; };
    return `${head(x)}<p class="small mut">Lines that need you come first. Click a piece of text to write a note on it, or select words; approve, hold back, edit, or go back to the earlier wording.</p>
      <div class="r8bar"><input type="search" id="rf-cq" placeholder="Find a piece of text or its key" aria-label="Find in the copy library" value="${esc(S.cq || '')}">${q ? `<span class="small mut">${pl(L.length, 'line matches', 'lines match')}</span>` : ''}</div>
      <div class="tblw rf-copy"><table><tbody>${[0, 1, 2].map(grp).join('') || '<tr><td class="mut">Nothing matches.</td></tr>'}</tbody></table></div>
      ${held > 1 ? `${noteList(k + '~held')}${S.note === k + '~held' ? '' : `<button class="btn sm" data-note="${esc(k)}~held">${ico('note')}Ask one question about the ${held} held-back lines</button>`}` : ''}
      <p class="small mut">Earlier wording: the text before its latest change; newest: as it reads now. Removed words are struck, new words marked.</p>
      ${foot(k, stOf(x), '', 'Click a piece of text, or select words, to write a note on it')}`;
  }
  // a findings set from the page's own register, as Rebex shows it: each finding, his answer and where it stands
  const FST = {needs: 'Needs you', ready: 'Ready', waiting: 'Waiting on the agent', done: 'Done'};
  function setView(x) {
    const k = 'ref:' + x.id, F = x.fset.items, n = s => F.filter(f => f.st === s).length;
    return `${head(x)}${x.fset.intro ? `<p ${at(k + '~i', 'Intro')}>${pin(k + '~i')}${esc(x.fset.intro)}</p>${noteList(k + '~i')}` : ''}
      <div class="tiles">${[['needs', 'need you'], ['waiting', 'waiting on the agent: agreed, not done yet'], ['done', 'done']].map(([s, w]) => `<div><b>${n(s)}</b><span>${w}</span></div>`).join('')}</div>
      <div class="doc">${block(['tbl', '', [['#', 'Finding', 'Your answer', 'Status'], ...F.map(f => [String(f.n), f.t + (f.why ? ' — ' + f.why : ''), f.a || '—', FST[f.st] + (f.note ? ' · ' + f.note : '')])], true], k + '~t')}</div>
      ${foot(k, stOf(x), '', 'Click a finding to write a note on it')}`;
  }
  function extraView(x) {
    if (x.find) return findView(x);
    if (x.copy) return copyView(x);
    if (x.fset) return setView(x);
    const k = 'ref:' + x.id, B = x.blocks ? x.blocks.map(b => b[0] === 'img' ? ['img', new URL(b[1], location.origin + ctx.base).href, b[2]] : b)
      : x.img ? [['img', x.img, x.note]] : x.md ? mdBlocks(x.md) : x.parts ? x.parts.flatMap(([t, h, rs]) => [['h', t], ['tbl', '', [h, ...rs], true]]) : [];
    // a designed message shows as the member sees it, sandboxed: no scripts run and its links go nowhere
    // a working page (Rebex's store) runs its own scripts in an opaque sandbox: it cannot reach this page or its saves
    const body = x.src ? `<iframe class="rf-embed wide" sandbox="allow-scripts" src="${esc(new URL(x.src, location.origin + ctx.base).href)}" title="${esc(x.t)}"></iframe>`
      : x.html ? `<iframe class="rf-embed${x.wide ? ' wide' : ''}" sandbox="" srcdoc="${esc(x.html)}" title="${esc(x.t)}"></iframe>` : B.map((b, i) => block(b, `${k}~x~${i}`)).join('') || `<p class="mut">${x.note ? esc(x.note) : 'This file has no text.'}</p>`;
    return `<div class="rf-acts rf-vh">${ico(x.kind)}<b class="rf-vt">${esc(x.t)}</b>${stPill(stOf(x))}<span class="small mut">${esc(x.from)} · changed ${esc(dm(x.d))} · read-only here</span><span class="spacer"></span><button class="ib" data-link="${esc(x.id)}" title="Copy a link to this item" aria-label="Copy a link to this item">${ico('link')}</button></div>
      ${x.note && (x.src || x.html || B.length) && !x.img ? `<p class="small mut">${esc(x.note)}</p>` : ''}<div class="doc">${body}</div>
      ${foot(k, stOf(x), '', 'Click any line or row, or select words, to write a note on them')}`;
  }
  function flowView(f) {
    const k = 'ref:' + f.id;
    return `<div class="rf-acts rf-vh">${ico('flow')}<b class="rf-vt">${esc(f.t)}</b><span class="small mut">Windmill workflow · runs ${esc(f.when)} · last edited ${esc(dm(f.edited))} · read-only here</span><span class="spacer"></span><button class="btn sm" data-wmopen="${esc(f.t)}" title="Open this workflow in Windmill, in a new tab">Open in Windmill ${ico('ext')}</button><button class="ib" data-link="${esc(f.id)}" title="Copy a link to this item" aria-label="Copy a link to this item">${ico('link')}</button></div>
      <p class="rf-what" ${at(k + '~what', f.what)}>${pin(k + '~what')}${esc(f.what)}</p>${noteList(k + '~what')}
      <p class="small"><b>${lastRun(f)}</b></p>${ftree(f.steps, k, !!f.last)}${failTree(f, k)}
      <p class="small mut">As deployed in Windmill today. Change it there or ask the agent in a note; this view only shows it.</p>
      ${noteList(k + '~all')}<div class="rf-acts"><button class="btn sm" data-note="${esc(k)}~all">${ico('note')}Write a note</button><span class="small mut">Click a step to write a note on it</span></div>`;
  }
  function viewer() {
    const p = D.plans.find(x => x.id === S.sel), f = !p && D.flows.find(x => x.id === S.sel), x = !p && !f && xOf(S.sel);
    if (!p && !f && !x) return '';
    picN = 0;
    return `<div class="viewer" id="rf-viewer">${p ? planView(p) : f ? flowView(f) : extraView(x)}</div>`;
  }

  /* ---------- draw and events ---------- */
  const here = () => el && el.isConnected && el.classList.contains('tab-reference');  // #p-main is shared by every tab
  function draw() {
    keepDrafts();  // every change to a draft redraws, on this tab or from Send
    if (!here() || !D) return;  // still reading: render draws once the data is in, with what Send's Remove or Undo changed (r12 audit11 frame 2, reference 3)
    const a = document.activeElement, keep = a && a.id && el.contains(a) ? [a.id, a.selectionStart, a.selectionEnd, a.value] : null;
    const zt = (el.querySelector('.zoomv') || {}).scrollTop || 0;
    el.innerHTML = `<div class="rf">${list()}${viewer()}${zoomView()}</div>`;
    const zv = el.querySelector('.zoomv'); if (zv) zv.scrollTop = zt;
    if (keep) { const b = document.getElementById(keep[0]); if (b) { if (keep[0] === 'rf-nt') b.value = keep[3]; b.focus(); try { b.setSelectionRange(keep[1], keep[2]); } catch {} } }
    if (S.note && !keep) { const t = document.getElementById('rf-nt'); if (t) t.focus({preventScroll: true}); }
    if (S.scroll) { const h = S.hl && el.querySelector('.rf-hl'), v = h || document.getElementById('rf-viewer'); if (v) v.scrollIntoView({block: h ? 'center' : 'start'});
      S.scroll = !!(S.hl && !h && Object.keys(loading).some(k => !blocks[k])); }  // a highlight in a revision still being read scrolls once it is drawn
    const rs = S.res && el.querySelector(`[data-line="${CSS.escape(S.res)}"]`);
    if (rs) { NK().lit(rs); if (S.resGo) { S.resGo = false; rs.scrollIntoView({block: 'center'}); } }
  }
  const open = id => { S.sel = S.sel === id ? '' : id; S.note = S.hl = S.res = ''; if (S.sel) { markSeen([id]); S.scroll = true; } history.replaceState(null, '', '#reference' + (S.sel ? '/' + encodeURIComponent(S.sel) : '')); draw(); };
  const copy = (t, what) => navigator.clipboard.writeText(t).then(() => ctx.toast(what + ' copied'), () => ctx.toast('Could not copy'));
  const fail = e => ctx.toast('Not saved: ' + e.message);
  // the server answers with the topics; a read-only copy's simulated write does not, so the change is made here
  const topics = (cfg, b) => { if (cfg && cfg.topics) { const names = cfg.topics.map(t => t.name); D.topics = (D.topics.includes('Unsorted') ? ['Unsorted'] : []).concat(names); }
    else if (b.rename) D.topics = D.topics.map(t => t === b.rename ? b.to : t);
    else if (b.merge) D.topics = D.topics.filter(t => t !== b.merge);
    else if (b.new && !D.topics.includes(b.topic)) D.topics = [...D.topics, b.topic];
    unsort(); };
  const topicApi = async b => topics(await ctx.api('api/plan-topics', b), b);
  // shortcut: back-to-Unsorted is kept in this browser (plan_topics has no unsort move); add one to plan_topics when the prototype graduates
  const unsorted = () => ctx.prefs.get('ref-unsort', []);
  const unsort = () => { const u = unsorted(); D.plans.forEach(p => { if (u.includes(p.id)) p.topic = 'Unsorted'; }); if (u.length && !D.topics.includes('Unsorted')) D.topics = ['Unsorted', ...D.topics]; };
  const setUnsort = (ids, on) => { const u = unsorted().filter(x => !ids.includes(x)); ctx.prefs.set('ref-unsort', on ? [...u, ...ids] : u); };
  async function topicChange(body, done, undo, msg) {
    try { await topicApi(body); done(); draw(); ctx.toast(msg, {undo: async () => { try { await undo(); draw(); } catch (e) { fail(e); } }}); }
    catch (e) { fail(e); }
  }

  async function onClick(e) {
    if (!here()) return;
    const b =e.target.closest('button,[data-line],summary,a,select,input,textarea');
    if (!b || !el.contains(b)) { if (S.tmerge) { S.tmerge = ''; draw(); } return; }
    const d = b.dataset;
    if (b.matches('[data-line]')) {  // a spot on a picture, the selected words, or else the whole line
      const im = e.target.closest('img'), sel = getSelection(), q = String(sel || '').replace(/\s+/g, ' ').trim();
      if (im) { const r = im.getBoundingClientRect(); S.tgt = {schema: 1, tag: 'img', offset: {dx: +((e.clientX - r.left) / r.width).toFixed(3), dy: +((e.clientY - r.top) / r.height).toFixed(3)}}; }
      else S.tgt = q && b.contains(sel.anchorNode) ? {schema: 1, tag: b.tagName.toLowerCase(), quote: q.slice(0, 300)} : null;
      if (S.move) return moveNote(S.move, d.line, b.dataset.label || '', S.tgt);  // Move: this line is its new place
      S.note = d.line; draw(); return;
    }
    if (b.tagName === 'SUMMARY') { S.det = !b.parentElement.open; return; }  // kept across redraws
    if (b.matches('a[data-zoom]')) e.preventDefault();  // ⤢ Full size opens the viewer here, not a new tab
    else if (b.tagName !== 'BUTTON') return;
    if (d.codecopy !== undefined) return P.media.onCopy(b);
    if (S.tmerge && d.tmerge === undefined && d.tmergeto === undefined) S.tmerge = '';
    if (d.ref !== undefined) return open(d.ref);
    if (d.task) { ctx.prefs.set('task', d.task); ctx.go('running', d.task); taskBack = S.sel; return; }  // Running opens the task kept in prefs
    if (d.retry) return retry(S.sel, d.retry);
    if (d.plansec) {
      const p = D.plans.find(x => x.id === S.sel) || xOf(S.sel), f = filed(), was = f[p.id];
      ctx.prefs.set('ref-file', {...f, [p.id]: d.plansec}); draw();
      return ctx.inert(`Filed “${cutq(p.t)}” as ${SN[d.plansec][0]}`, () => { const g = filed(); if (was) g[p.id] = was; else delete g[p.id]; ctx.prefs.set('ref-file', g); draw(); });
    }
    if (d.freopen) {
      const fk = d.freopen;
      S.reopen.set(fk, ''); draw();
      const t = el.querySelector(`[data-reopen="${CSS.escape(fk)}"]`); if (t) t.focus();
      return ctx.inert('Finding reopened', () => { S.reopen.delete(fk); draw(); });
    }
    if (d.appr) {  // approve the whole item: goes with the next Send, kept in memory
      const k = d.appr, on = !S.appr.has(k), flip = v => { v ? S.appr.add(k) : S.appr.delete(k); draw(); };
      flip(on);
      return ctx.inert(on ? 'Approved; goes with your next Send' : 'Approval taken back', () => flip(!on));
    }
    if (d.unreopen) { const fk = d.unreopen, t = S.reopen.get(fk); S.reopen.delete(fk); draw(); return ctx.inert('Reopen taken back', () => { S.reopen.set(fk, t); draw(); }); }
    if (d.wmopen) return ctx.toast(`Opens “${d.wmopen}” in Windmill, in a new tab`, {inert: true});
    if (d.sec) { S.sec = d.sec; return draw(); }
    if (d.kind) { S.kind = S.kind === d.kind ? '' : d.kind; return draw(); }
    if (d.allseen !== undefined) { markSeen(rows().map(r => r.id)); return draw(); }
    if (d.fx) { S.fx.has(d.fx) ? S.fx.delete(d.fx) : S.fx.add(d.fx); return draw(); }
    if (d.rv !== undefined) { S.rv[S.sel] = +d.rv; return draw(); }
    if (d.marks !== undefined) { S.marks = !S.marks; return draw(); }
    if (d.clf !== undefined) { if (!d.clf) S.clf.clear(); else S.clf.has(d.clf) ? S.clf.delete(d.clf) : S.clf.add(d.clf); return draw(); }
    if (d.fold) { S.open.has(d.fold) ? S.open.delete(d.fold) : S.open.add(d.fold); return draw(); }
    if (d.copy) return copy(d.copy, d.what || (d.copy.startsWith('~/') ? 'Path' : 'Text'));
    if (d.link) return copy(location.origin + location.pathname + '#reference/' + encodeURIComponent(d.link), 'Link');
    if (d.cpst) {  // Approve, Hold back or Use earlier: kept in memory, the copy sends nothing
      const [ck, st] = d.cpst.split('|'), was = S.cp.get(ck);
      S.cp.set(ck, {st}); draw();
      return ctx.inert(st === 'ok' ? 'Text approved' : st === 'held' ? 'Text held back' : 'Earlier wording chosen', () => { was ? S.cp.set(ck, was) : S.cp.delete(ck); draw(); });
    }
    if (d.cpundo) { const ck = d.cpundo, was = S.cp.get(ck); S.cp.delete(ck); draw(); return ctx.inert('Text restored', () => { S.cp.set(ck, was); draw(); }); }
    if (d.cped) { S.cpEd = d.cped; draw(); const t = el.querySelector('.rf-rte'); if (t) t.focus(); return; }
    if (d.cpalt !== undefined) { const t = el.querySelector('.rf-rte'); if (t) t.textContent = d.cpalt; return; }  // an earlier wording into the editor
    if (d.rte) { document.execCommand(d.rte.split(':')[0], false, d.rte.split(':')[1] || (d.rte === 'createLink' ? prompt('Link address') || '' : undefined)); return; }
    if (d.cpsave) {
      const ck = d.cpsave, t = el.querySelector('.rf-rte'), was = S.cp.get(ck);
      S.cp.set(ck, {st: 'edit', html: t ? rich(t.innerHTML) : ''}); S.cpEd = ''; draw();
      return ctx.inert('Edit saved', () => { was ? S.cp.set(ck, was) : S.cp.delete(ck); draw(); });
    }
    if (d.cpcancel !== undefined) { S.cpEd = ''; return draw(); }
    // a marker's list and the note lifecycle: the code Questions uses (P.notes), so every tab behaves the same (r12 audit15 reference 2, 3)
    const nt = id => allNotes().find(x => x.id === id);
    if (d.spot !== undefined) { S.pin = ''; S.spot = S.spot === d.spot ? '' : d.spot; return draw(); }
    if (d.pin) { const n = nt(d.pin); if (!n) return; const on = S.pin === n.id; S.pin = on ? '' : n.id; S.spot = on ? '' : n.a; return draw(); }
    if (d.spotx !== undefined) { S.spot = S.pin = ''; return draw(); }
    if (d.spotadd) { const p = d.spotpin && nt(d.spotpin); S.spot = S.pin = ''; S.note = d.spotadd; S.tgt = p ? {...p.target} : null; return draw(); }
    if (d.spotgo) { S.spot = S.pin = ''; S.hl = d.spotgo; if (S.full) closeZoom(); else draw(); const x = el.querySelector(`[data-nid="${CSS.escape(d.spotgo)}"]`); if (x) x.scrollIntoView({block: 'center'}); return; }
    const life = how => id => { const n = nt(id); return n && NK().set(ctx, n, how, ctx.api, async nid => { S.spot = S.pin = ''; S.hl = nid; draw(); ctx.refreshChips(); }); };
    if (d.nclose) return life('close')(d.nclose);
    if (d.nopen) return life('restore')(d.nopen);
    if (d.nreopen) return life('reopen')(d.nreopen);
    // a plan note's resolution is a line of that plan: its revision opens there, outlined; any other goes to History
    if (d.nres) { const n = nt(d.nres); if (!n) return; if (!/^(ref|chk):/.test(n.ra || '')) return NK().goRes(ctx, n); S.res = n.ra; S.resGo = true; return goRef(itemOf(n.ra), '', n.ra)(); }
    if (d.nmove) { S.move = S.move === d.nmove ? '' : d.nmove; draw(); if (S.move) ctx.toast('Click the new line for this note · Esc cancels'); return; }
    if (d.note) { S.note = d.note; S.tgt = null; return draw(); }
    if (d.ncancel !== undefined) { S.note = ''; return draw(); }
    if (d.zoom) {
      const k = d.zk, im = S.full && S.full.k === k ? null : el.querySelector(`[data-line="${CSS.escape(k)}"] img`);
      ctx.prefs.set('ref-zoom', {...ctx.prefs.get('ref-zoom', {}), [k]: +d.zoom});
      S.full = im ? {k, src: im.getAttribute('src'), cap: im.dataset.zcap, z: +d.zoom} : {...S.full, z: +d.zoom};
      if (S.note !== k) S.note = '';
      return draw();
    }
    if (d.zclose !== undefined) return closeZoom();
    if (d.nsave) {
      const k = d.nsave, text = (document.getElementById('rf-nt').value || '').trim();
      if (!text) return ctx.toast('Write something first');
      const src = el.querySelector(`[data-line="${CSS.escape(k)}"]`);
      try {
        const target = S.tgt || undefined;
        const c = await ctx.api('api/comments', {anchor_id: k, anchor_label: src ? src.dataset.label : 'Reference', text, target, ...noteMeta(k)});
        mine.push({id: c.id, a: k, l: src ? src.dataset.label : '', text: c.text, who: c.author_name || 'You', at: c.created_at || new Date().toISOString(), v: c.version, target: c.target || target});
        S.note = ''; S.tgt = null; draw(); ctx.refreshChips();
        ctx.toast('Note saved', {undo: () => undoNote(c.id)});
      } catch (er) { fail(er); }
      return;
    }
    if (d.nundo) return undoNote(d.nundo);
    if (d.trn !== undefined) { S.trn = d.trn; draw(); const i = document.getElementById('rf-trn'); if (i) { i.focus(); i.select(); } return; }
    if (d.trnsave) return renameTopic(d.trnsave, (document.getElementById('rf-trn').value || '').trim());
    if (d.tmerge) { S.tmerge = S.tmerge === d.tmerge ? '' : d.tmerge; return draw(); }
    if (d.tmergeto) return combine(S.tmerge, d.tmergeto);
  }
  function moveNote(id, a, l, target) {
    const n = allNotes().find(x => x.id === id); S.move = ''; if (!n) return draw();
    return NK().move(ctx, id, {anchor_id: n.a, anchor_label: n.l, target: n.target || null}, {anchor_id: a, anchor_label: l, target: target || null}, ctx.api,
      p => { if (p) Object.assign(n, {a: p.anchor_id, l: p.anchor_label, target: p.target}); S.hl = p ? id : ''; draw(); });
  }
  async function undoNote(id) {
    try { await ctx.api('api/comments/' + encodeURIComponent(id), undefined, 'DELETE'); mine = mine.filter(n => n.id !== id); D.notes = D.notes.filter(n => n.id !== id); draw(); ctx.toast('Note taken back'); }
    catch (e) { fail(e); }
  }
  // Unsorted is not a stored topic: renaming or combining it files each of its plans under the named topic, one move each
  async function unsortedTo(topic, isNew) {
    const ps = D.plans.filter(p => p.topic === 'Unsorted');
    S.trn = S.tmerge = '';
    try {
      const ids = ps.map(p => p.id);
      setUnsort(ids, false);
      for (const [i, p] of ps.entries()) { await topicApi({move: p.id, topic, ...(isNew && !i ? {new: true} : {})}); p.topic = topic; }
      draw(); ctx.toast(`${pl(ps.length, 'plan', 'plans')} filed under “${topic}”`, {undo: () => { setUnsort(ids, true); unsort(); draw(); }});
    } catch (e) { draw(); fail(e); }
  }
  function renameTopic(old, to) {
    if (!to || to === old) { S.trn = ''; return draw(); }
    if (old === 'Unsorted') return unsortedTo(to, !D.topics.includes(to));
    const set = (a, b) => D.plans.forEach(p => { if (p.topic === a) p.topic = b; });
    topicChange({rename: old, to}, () => { S.trn = ''; set(old, to); },
      async () => { await topicApi({rename: to, to: old}); set(to, old); }, `Topic renamed to “${to}”`);
  }
  function combine(from, into) {
    if (from === 'Unsorted') return unsortedTo(into, false);
    const moved = D.plans.filter(p => p.topic === from);
    S.tmerge = '';
    topicChange({merge: from, into}, () => moved.forEach(p => p.topic = into),
      async () => {  // no un-combine endpoint: recreate the topic and move its plans back (its title words stay with the other topic)
        for (const [i, p] of moved.entries()) await topicApi({move: p.id, topic: from, ...(i ? {} : {new: true})});
        moved.forEach(p => p.topic = from);
      }, `“${from}” combined into “${into}”`);
  }
  async function onChange(e) {
    const s = here() && e.target.closest('select[data-move]');
    if (!s) return;
    const p = D.plans.find(x => x.id === s.dataset.move), old = p.topic;
    let topic = s.value, isNew = false;
    if (topic === '__new') { topic = (prompt('Name the new topic') || '').trim(); isNew = true; if (!topic) return draw(); }
    const back = () => { setUnsort([p.id], true); unsort(); };  // to Unsorted, as the mock allows
    if (topic === 'Unsorted') {
      if (old === 'Unsorted') return;
      back(); draw();
      return ctx.toast('Moved back to “Unsorted”', {undo: () => { setUnsort([p.id], false); p.topic = old; draw(); }});
    }
    topicChange({move: p.id, topic, ...(isNew ? {new: true} : {})}, () => { setUnsort([p.id], false); p.topic = topic; },
      old === 'Unsorted' ? async () => back() : async () => { await topicApi({move: p.id, topic: old}); p.topic = old; },
      `Moved to “${topic}”`);
  }
  function onInput(e) {
    if (here() && e.target.id === 'rf-q') { S.q = e.target.value; draw(); }
    if (here() && e.target.id === 'rf-cq') { S.cq = e.target.value; draw(); }
    if (here() && e.target.dataset.reopen) { S.reopen.set(e.target.dataset.reopen, e.target.value); keepDrafts(); }
  }  function closeZoom() { if (S.full && S.note === S.full.k) S.note = ''; S.full = null; draw(); }
  function onDocKey(e) { if (here() && S.full && e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeZoom(); } }
  function onKey(e) {
    if (!here() || S.full) return;
    if (e.target.id === 'rf-trn' && e.key === 'Enter') renameTopic(S.trn, e.target.value.trim());
    if (e.key === 'Escape' && (S.trn || S.tmerge || S.note || S.move || S.spot)) { S.trn = S.tmerge = S.note = S.move = S.spot = S.pin = ''; draw(); }
    if (e.target.matches('[data-line]') && e.key === 'Enter') { S.note = e.target.dataset.line; draw(); }
  }

  // what Reference says goes with the next Send, in the one Send (r12 fix6): reopened findings with their why (reference 5),
  // copy-library choices, and notes written here (reference 4), which a plan's own version keeps out of Questions' list
  // notes from an earlier visit are listed too, while reference.json says they are unsent (r12 fix7)
  // Go to it: opens the item (a checklist row's note opens the checklist) and, for a note, highlights it; the same hash fires no hashchange, so redraw then
  const itemOf = a => a.startsWith('chk:') && D && D.checklist ? D.checklist.plan : a.replace(/^ref:/, '').split('~')[0];
  // a note in a folded copy group or on an older plan revision: open that group or revision first (r12 fix9)
  function reach(a) {
    const m = /^ref:([^~]+)~(.+)~(\d+)$/.exec(a || ''), x = m && xOf(m[1]), p = m && D.plans.find(q => q.id === m[1]);
    if (m && m[2] === 'c' && x && x.copy && x.copy[+m[3]]) { S.cq = ''; S.open.add(`cpall:${x.id}:${cpRank(x.copy[+m[3]][2])}`); }
    else if (p) { const i = p.revs.findIndex(r => r[0] === m[2]); if (i >= 0) S.rv[p.id] = i; if (D.checklist && D.checklist.plan === p.id) S.det = true; }
  }
  // before reference.json is in, the item is reached once render has it (r12 fix10 reference 1)
  const goRef = (id, nid, a) => () => { S.sel = id; S.hl = nid || ''; S.note = ''; S.scroll = true; if (D) reach(a); else S.reach = a;
    if (here() && location.hash === '#reference/' + encodeURIComponent(id)) draw(); else ctx.go('reference', id); };
  const redo = () => draw();  // draw keeps the drafts, then redraws only on this tab
  const out = (key, group, html, id, take, put) => ({key, group, html, go: goRef(id), remove: () => { take(); redo(); return () => { put(); redo(); }; }});
  if (Proto.queue) Proto.queue({
    items: c => {
      ctx = ctx || c; restoreDrafts();  // listed from what was saved, before reference.json is in (r12 fix10 frame 1)
      const it = [], was = JSON.stringify([LBL, SNOTES]);
      const name = (k, fresh, none) => fresh ? (LBL[k] = fresh) : LBL[k] || none;  // with the data: its name, kept for the next reload
      for (const [fk, why] of S.reopen) { if (!why.trim()) continue;
        const [id, i] = fk.split('~'), f = (((xOf(id) || {}).find || {}).items || [])[+i] || {};
        it.push(out('ro:' + fk, 'Reference', `Finding “${c.esc(name('ro:' + fk, f.label, 'a finding'))}” → <b>reopened</b>: “${c.esc(cutq(why))}”`, id, () => S.reopen.delete(fk), () => S.reopen.set(fk, why))); }
      for (const [ck, s] of S.cp) { const m = /^ref:(.+)~c~(\d+)$/.exec(ck), x = m && xOf(m[1]); if (!m || (D && !x)) continue;
        // an edit shows its saved wording with its formatting: s.html is already cleaned to the editor's own tags (rich)
        const what = s.st === 'edit' ? `edited: “<span class="rf-sendrt">${s.html}</span>”` : `<b>${{ok: 'approved', held: 'held back', old: 'earlier wording'}[s.st]}</b>`;
        const nm = name('cp:' + ck, x && `${x.t}, ${(x.copy[+m[2]] || [])[0] || 'line ' + (+m[2] + 1)}`, `Copy library, line ${+m[2] + 1}`);
        it.push(out('cp:' + ck, 'Reference', `${c.esc(nm)} → ${what}`, m[1], () => S.cp.delete(ck), () => S.cp.set(ck, s))); }
      for (const k of S.appr) { const id = k.slice(4), x = (D && D.plans.find(p => p.id === id)) || xOf(id);
        it.push(out('ap:' + k, 'Reference', `${c.esc(name('ap:' + k, x && x.t, id))} → <b>approved</b>`, id, () => S.appr.delete(k), () => S.appr.add(k))); }
      // a document's note (doc:) is Pages & links' own, so it is listed there once (r12 fix8)
      // m: where it was saved (its plan revision, document and category), so Undo puts back the same record before the data is in (r12 fix14 frame 1)
      if (D) SNOTES = allNotes().filter(n => !n.sent && !/^doc:/.test(n.a)).map(n => ({id: n.id, a: n.a, l: n.l, text: n.text, target: n.target, item: itemOf(n.a), m: {...noteMeta(n.a), ...(n.v ? {version: n.v} : {})}}));
      for (const n of SNOTES) it.push({key: 'rn:' + n.id, group: 'Notes', note: n.id, html: `On “${c.esc(cutq((n.target && n.target.quote) || n.l || 'Reference'))}”:${c.esc(n.text.length > 140 ? n.text.slice(0, 139) + '…' : n.text)}`,
        go: goRef(n.item || itemOf(n.a), n.id, n.a), remove: async () => {
          // the record stays in the store until Undo is gone, so Undo puts back the very note: id, number, time, revision and all (r12 audit13 frame 4)
          const keep = ctx.take(n.id, 'api/comments/' + encodeURIComponent(n.id)), wm = mine, wd = D && D.notes, ws = SNOTES;
          mine = mine.filter(x => x.id !== n.id); if (D) D.notes = D.notes.filter(x => x.id !== n.id); SNOTES = SNOTES.filter(x => x.id !== n.id); keepDrafts(); redo();
          return async () => { keep(); mine = P.putBack(mine, wm, n.id); if (D && wd) D.notes = P.putBack(D.notes, wd, n.id); SNOTES = P.putBack(SNOTES, ws, n.id); keepDrafts(); redo(); }; }});
      // a sent note he re-opened goes again, its own row; Remove puts it back as the agent left it, with Undo (P.notes, r12 audit15 reference 3)
      if (D && P.notes) allNotes().filter(n => !/^doc:/.test(n.a) && P.notes.isReo(c, n)).forEach(n => it.push({key: 'reo:' + n.id, group: 'Notes', note: n.id,
        html: P.notes.row(n, '↻', `On “${c.esc(cutq((n.target && n.target.quote) || n.l || 'Reference'))}”`), go: goRef(itemOf(n.a), n.id, n.a),
        remove: () => P.notes.set(c, n, 'unreopen', c.api, async () => redo(), true)}));
      if (JSON.stringify([LBL, SNOTES]) !== was) keepDrafts();
      return it;
    },
    sent: () => { const t = new Date().toTimeString().slice(0, 5);  // a sent reopen keeps its status and why, in memory as every simulated write
      for (const [fk, why] of S.reopen) if (why.trim()) S.rsent.set(fk, [t, why]);
      S.reopen.clear(); S.cp.clear(); S.appr.clear(); if (D) allNotes().forEach(n => { n.sent = true; }); SNOTES = []; keepDrafts(); redo(); },
  });
  Proto.tab({key: 'reference',
    chip: async c => { ctx = c; restoreDrafts(); D = await c.data('reference'); unsort(); const n = countChanged(); return n ? {text: `${n} changed`, tone: 'amber'} : null; },
    render: async (main, c, anchor) => {
      ctx = c; el = main; restoreDrafts();
      if (!D) { main.innerHTML = '<p class="mut">Reading Reference…</p>'; D = await c.data('reference'); }
      unsort();
      if (S.reach) { reach(S.reach); S.reach = ''; }  // Go to it pressed before the data was in (r12 fix10 reference 1)
      taskBack = '';
      const id = anchor ? decodeURIComponent(anchor) : '';
      if (id && (D.plans.some(p => p.id === id) || D.flows.some(f => f.id === id) || xOf(id))) { S.sel = id; S.scroll = true; markSeen([id]); }
      if (!main._rf) {
        main._rf = true;
        main.addEventListener('click', onClick); main.addEventListener('change', onChange);
        main.addEventListener('input', onInput); main.addEventListener('keydown', onKey);
        main.addEventListener('mousedown', e => { if (e.target.closest('[data-rte]')) e.preventDefault(); });  // the editor keeps its selection
        document.addEventListener('keydown', onDocKey, true);  // Esc closes the picture viewer wherever the focus is
      }
      draw();
    }});
})();
