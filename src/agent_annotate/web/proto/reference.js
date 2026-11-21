/* Reference tab: plans by topic, the go-live checklist, Windmill workflows and the project's documents (build-list stage 3).
   Ported from round9/final/mock.html (reference, viewer, checklistHtml, ftree, docList) onto the module contract.
   Saves use today's endpoints: api/plan-topics (rename, combine, move) and api/comments (notes, Undo = DELETE). */
(function () {
  const P = window.Proto;
  const S = {q: '', sec: 'all', kind: '', sel: '', fx: new Set(), rv: {}, marks: true, clf: new Set(), dk: '', dsel: '', open: new Set(),
    trn: '', tmerge: '', note: '', scroll: false, reopen: new Map()};  // reopen: finding -> why, in memory only (the prototype sends nothing)
  let ctx, D, el, mine = [];  // mine: notes written in this visit, so Undo can take them back
  // a task opened from a checklist pill: closing its panel in Running comes back here with the checklist open, as in the mock
  let taskBack = '';
  const backFromTask = () => { if (taskBack && location.hash.startsWith('#running')) { const id = taskBack; taskBack = ''; setTimeout(() => ctx.go('reference', id), 0); } };
  // capture phase: Running redraws its panel away while handling the same event
  document.addEventListener('click', e => { if (e.target.closest('.tab-running .tpanel [data-task=""]')) backFromTask(); }, true);
  addEventListener('keydown', e => { if (e.key === 'Escape' && document.querySelector('.tab-running .tpanel') && !(e.target.closest && e.target.closest('textarea,input'))) backFromTask(); }, true);
  addEventListener('hashchange', () => { if (!location.hash.startsWith('#running')) taskBack = ''; });
  const blocks = {}, loading = {};
  const ico = (n, l) => P.icon(n, l), pl = (n, a, b) => `${n} ${n === 1 ? a : b}`;
  const esc = s => ctx.esc(s);
  const dm = s => { const d = new Date(String(s).slice(0, 10) + 'T12:00'); return isNaN(d) ? '' : d.toLocaleDateString('en-GB', {day: 'numeric', month: 'short'}); };
  const KN = {plan: 'Plans', check: 'Checklists', design: 'Diagrams and designs', text: 'App text', data: 'Sheets and findings', flow: 'Workflows', mem: 'Memory', doc: 'Documents'};
  const KG = {...KN, decision: 'Decisions'};  // group names: decisions are plans, listed apart from the topics
  const SN = {prop: ['Proposed', 'Waits on your decision: something the agent proposed'], ok: ['Approved', 'You approved it, or it was decided'], ref: ['For reference', 'Kept for looking things up']};
  const DK = {md: ['file-md', 'Markdown'], pdf: ['file-pdf', 'PDF'], word: ['file-word', 'Word'], sheet: ['file-sheet', 'Sheet'], video: ['file-video', 'Video']};
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
  const lastTs = p => p.revs[p.revs.length - 1][1], xOf = id => (D.extras || []).find(x => x.id === id);
  const nSteps = ss => ss.reduce((n, s) => n + 1 + nSteps(s.sub || []) + (s.br || []).reduce((m, b) => m + nSteps(b[1]), 0), 0);
  function rows() {
    const out = D.plans.map(p => ({id: p.id, t: p.t, m: `${pl(p.revs.length, 'revision', 'revisions')} · changed ${dm(lastTs(p))}`, kind: p.kind, st: stOf(p),
      g: p.kind !== 'plan' ? 'k:' + p.kind : p.id.startsWith('decision-') ? 'k:decision' : 't:' + p.topic, p, stamp: lastTs(p), s: p.topic}));
    for (const x of D.extras || []) out.push({id: x.id, t: x.t, m: x.find ? `${dm(x.d)} · ${pl(x.find.items.length, 'finding', 'findings')}` : `from the project folder · ${x.from.split('/').pop()} · changed ${dm(x.d)}`, kind: x.kind, st: stOf(x),
      g: x.kind === 'plan' ? 't:Plans' : 'k:' + x.kind, x, stamp: x.d, s: (x.md || (x.parts ? JSON.stringify(x.parts) : '') || (x.find ? x.find.conclusion + ' ' + x.find.items.map(f => f.label + ' ' + f.text).join(' ') : '') || x.note || '').slice(0, 20000)});  // finds words inside them too
    for (const f of D.flows) out.push({id: f.id, t: f.t, m: `Windmill · runs ${f.when} · ${pl(nSteps(f.steps), 'step', 'steps')} · ${f.last ? `last run ${dm(f.last.at)}, ${f.last.ok ? 'passed' : 'failed'}` : 'not run yet'}`,
      kind: 'flow', st: 'ref', g: 'k:flow', f, stamp: f.edited, s: f.what + ' ' + JSON.stringify(f.steps.map(x => x.n))});
    out.forEach(r => r.ch = changed(r.id, r.stamp));
    out.push({id: 'mem:later', t: 'Memory tree', m: 'later: what the agents remember about this project, as a tree you can open', kind: 'mem', st: 'ref', g: 'k:mem', later: true});
    return out;
  }
  const docId = f => 'doc:' + [f.g, f.sub, f.n].filter(Boolean).join('/');
  const docs = () => D.docs.files.map(f => ({...f, id: docId(f), ch: changed(docId(f), f.d)}));
  const countChanged = () => rows().filter(r => r.ch).length + docs().filter(f => f.ch).length;

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
  const pin = k => { const n = notesAt(k).length; return n ? `<span class="rf-pin" title="${pl(n, 'note', 'notes')} here">${ico('note')}${n}</span>` : ''; };
  const cutq = s => s.length > 60 ? s.slice(0, 58).trimEnd() + '…' : s;
  // what a note is on: selected words, a spot on a picture (numbered as its pin), or the whole line
  const onWhat = (t, no) => !t ? '' : t.quote ? ` on “${esc(cutq(t.quote))}”` : t.offset ? ` at spot ${no || '+'} on the picture` : '';
  const spotNo = (k, n) => notesAt(k).filter(x => x.target && x.target.offset).indexOf(n) + 1;
  const spots = k => notesAt(k).filter(n => n.target && n.target.offset).map((n, i) => `<span class="pinm" style="left:${n.target.offset.dx * 100}%;top:${n.target.offset.dy * 100}%">${i + 1}</span>`).join('')
    + (S.note === k && S.tgt && S.tgt.offset ? `<span class="pinm new" style="left:${S.tgt.offset.dx * 100}%;top:${S.tgt.offset.dy * 100}%">+</span>` : '');
  function noteList(k, dlg) {
    const ns = notesAt(k), box = S.note === k && !S.full === !dlg;  // the open picture viewer holds the composer for its picture
    if (!ns.length && !box) return '';
    return `<div class="rf-notes">${ns.map(n => `<div class="rf-nt"><span class="rf-nw">${ico('note')}<b>${esc(n.who)}</b> · ${esc(dm(n.at))}${onWhat(n.target, spotNo(k, n))}</span> ${esc(n.text)}${mine.some(x => x.id === n.id) ? ` <button class="lk small" data-nundo="${esc(n.id)}">Undo</button>` : ''}</div>`).join('')}
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
  const zoomBar = (k, src, cap) => `<figcaption>${cap ? esc(cap) + ' · ' : ''}<span class="seg zm" role="group" aria-label="Open full size at">${ZS.map(z => `<button data-zoom="${z}" data-zk="${esc(k)}" aria-label="Open at ${z}%" aria-pressed="${z === zOf(k)}">${z}%</button>`).join('')}</span> <button class="lk small" data-zoom="${zOf(k)}" data-zk="${esc(k)}">⤢ Full size</button> · tap a spot to write a note</figcaption>`;
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
      : kind === 'img' ? `<figure ${a}>${pin(k)}<span class="qpinwrap"><img src="${esc(t)}" alt="${esc(x || 'Picture')}" loading="lazy">${spots(k)}</span>${zoomBar(k, t, x)}${tg}</figure>`
      : kind === 'pre' ? `<div class="rf-code" ${a}>${pin(k)}<pre><code>${esc(t)}</code></pre><button class="btn sm" data-copy="${esc(t)}">${ico('copy')}Copy</button>${tg}</div>`
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
    const R = rows(), F = docs(), q = S.q.toLowerCase();
    const hit = r => !q || (r.t + ' ' + r.m + ' ' + (r.s || '')).toLowerCase().includes(q), dhit = f => !q || (f.n + ' ' + f.sub + ' ' + (D.docs.groups[f.g] || '')).toLowerCase().includes(q);
    const inSt = r => S.sec === 'all' || r.st === S.sec, inK = r => !S.kind || r.kind === S.kind;
    const shown = R.filter(r => hit(r) && inSt(r) && inK(r)), docsOn = F.length > 0 && (!S.kind || S.kind === 'doc') && (S.sec === 'all' || S.sec === 'ref');
    const nd = F.filter(dhit).length;
    const stN = s => R.filter(r => hit(r) && inK(r) && (s === 'all' || r.st === s)).length + ((!S.kind || S.kind === 'doc') && (s === 'all' || s === 'ref') ? nd : 0);
    const kN = k => k === 'doc' ? (S.sec === 'all' || S.sec === 'ref' ? nd : 0) : R.filter(r => hit(r) && inSt(r) && r.kind === k).length;
    // topics first (the mock's left column), then the kinds in their chip order
    const KO = [...Object.keys(KN), 'decision'], o = g => g[0] === 't' ? (g === 't:Plans' ? 99 : D.topics.indexOf(g.slice(2))) : 100 + KO.indexOf(g.slice(2));
    const gs = [...new Set(shown.map(r => r.g))].sort((a, b) => o(a) - o(b));
    const nch = R.filter(r => r.ch).length + F.filter(f => f.ch).length;
    const kinds = Object.keys(KN).filter(k => k === 'doc' ? F.length : R.some(r => r.kind === k));  // FastLane Drive has no app text; a copy has no project files
    const bar = `<div class="r8bar"><input type="search" id="rf-q" placeholder="Find a plan, checklist, design or workflow" aria-label="Find in Reference" value="${esc(S.q)}">
      <span class="rf-chips" role="group" aria-label="State">${['all', 'prop', 'ok', 'ref'].map(s => `<button class="chipb" data-sec="${s}" aria-pressed="${S.sec === s}" title="${s === 'all' ? 'Every item' : esc(SN[s][1])}">${s === 'all' ? 'All' : SN[s][0]} <span class="n">${stN(s)}</span></button>`).join('')}</span>
      <span class="sep" aria-hidden="true"></span><span class="rf-chips" role="group" aria-label="Kind">${kinds.map(k => `<button class="chipb" data-kind="${k}" aria-pressed="${S.kind === k}" title="Only ${KN[k].toLowerCase()}">${ico(k === 'doc' ? 'doc' : k)}${KN[k]} <span class="n">${kN(k)}</span></button>`).join('')}</span>
      <span class="spacer"></span><span class="small mut rf-chl">${nch ? `${chg} ${pl(nch, 'item changed', 'items changed')} since you last looked · <button class="lk small" data-allseen>Mark all as seen</button>` : 'Nothing changed since you last looked'}</span></div>`;
    const lst = gs.length ? `<div class="r8list">${gs.map(g => { const rs = shown.filter(r => r.g === g);
      return `<div class="r8g">${g[0] === 't' ? topicHead(g.slice(2), rs.length) : `<div class="r8gh">${ico(g === 'k:decision' ? 'plan' : g.slice(2))}<span class="gt">${KG[g.slice(2)]}</span><span class="n">${rs.length}</span></div>`}${(g === 'k:decision' && !q && !S.open.has(g) ? rs.slice(0, 6) : rs).map(r => r.kind === 'flow' ? flowRow(r) : row(r)).join('')}${g === 'k:decision' && !q && rs.length > 6 ? `<button class="lk small rf-more" data-fold="${g}">${S.open.has(g) ? 'Show the first 6' : `Show all ${rs.length}`}</button>` : ''}</div>`; }).join('')}</div>` : (docsOn && nd ? '' : '<p class="mut">Nothing matches.</p>');
    return [bar + lst, docsOn ? docList(F.filter(dhit), F.length) : ''];  // documents go under the opened item, never between the list and it
  }

  /* ---------- documents: this project's files, like Finder's list view ---------- */
  const kb = n => n >= 1024 ? `${(n / 1024).toFixed(1)} MB` : `${n} KB`;
  const path = f => ['~/projects/FastLane Drive', f.g, f.sub, f.n].filter(Boolean).join('/');
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
  function docView(f) {
    const k = 'doc:' + f.id.slice(4);
    return `<div class="viewer rf-docv"><div class="rf-acts"><span class="rf-dk k-md">${ico('file-md')}</span><b>${esc(f.n)}</b><span class="small mut">${esc(D.docs.groups[f.g] || '')}${f.sub ? ' / ' + esc(f.sub) : ''} · ${kb(f.kb)} · changed ${esc(dm(f.d))}</span><span class="spacer"></span><button class="btn sm" data-dopen="${esc(f.id)}">${ico('x')}Close</button></div>
      <div class="doc">${mdBlocks(f.md).map((b, i) => block(b, `${k}~${i}`)).join('')}</div>
      ${noteList(k + '~all')}<div class="rf-acts"><button class="btn sm" data-note="${esc(k)}~all">${ico('note')}Write a note</button><span class="small mut">Click any line to write a note on it</span></div></div>`;
  }
  function docList(F, total) {
    const kinds = Object.keys(DK).filter(k => F.some(f => f.k === k)), sh = F.filter(f => !S.dk || f.k === S.dk);
    const gs = Object.keys(D.docs.groups).filter(g => sh.some(f => f.g === g)).sort((a, b) => (a === '' ? -1 : b === '' ? 1 : 0) || sh.filter(f => f.g === b).length - sh.filter(f => f.g === a).length);
    const dic = k => `<span class="rf-dk k-${k}" title="${DK[k][1]}">${ico(DK[k][0], DK[k][1])}</span>`;
    const drow = f => `<div class="doc9"${S.dsel === f.id ? ' aria-current="true"' : ''}>${dic(f.k)}<button class="nm" data-dopen="${esc(f.id)}" ${f.md ? `aria-expanded="${S.dsel === f.id}" title="Open it here"` : 'title="Opens in a new tab"'}>${esc(f.n)}${f.md ? '' : ' ↗'} ${f.ch ? chg : ''}${f.sub ? `<span class="sub">${esc(f.sub)}</span>` : ''}</button><span class="sz">${kb(f.kb)}</span><span class="d9t">${esc(dm(f.d))}</span><button class="ib" data-copy="${esc(path(f))}" data-what="Path" title="Copy its path" aria-label="Copy the path of ${esc(f.n)}">${ico('copy')}</button></div>${S.dsel === f.id && f.md ? docView(f) : ''}`;
    return `<section class="rf-docs" aria-label="Documents"><div class="r8gh rf-dh">${ico('doc')}<span class="gt">Documents</span><span class="n">${pl(total, 'file', 'files')} in this project's folder · Markdown opens here, other kinds in a new tab</span></div>
      <div class="docbar"><button class="chipb" data-dk="" aria-pressed="${!S.dk}">All <span class="n">${F.length}</span></button>${kinds.map(k => `<button class="chipb" data-dk="${k}" aria-pressed="${S.dk === k}" title="Only ${DK[k][1]} files">${dic(k)}${DK[k][1]} <span class="n">${F.filter(f => f.k === k).length}</span></button>`).join('')}</div>
      ${gs.map(g => { const l = sh.filter(f => f.g === g), key = 'dg:' + g, op = !!S.q || S.open.has(key) || sh.some(f => f.id === S.dsel && f.g === g), all = S.open.has('dga:' + g), nchg = l.filter(f => f.ch).length;
        return `<div class="rf-grp"><button class="fold" data-fold="${esc(key)}" aria-expanded="${op}"><span>${esc(D.docs.groups[g])}</span> <span class="small mut">${pl(l.length, 'file', 'files')}${nchg ? ` · ${nchg} changed` : ''}</span></button>
          ${op ? l.slice(0, all ? l.length : 8).map(drow).join('') + (l.length > 8 ? `<button class="lk small rf-more" data-fold="dga:${esc(g)}">${all ? 'Show the first 8' : `Show all ${l.length}`}</button>` : '') : ''}</div>`; }).join('') || '<p class="mut">No document matches.</p>'}</section>`;
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
      <span class="small mut">Filed as</span><span class="seg" role="group" aria-label="Filed as">${['prop', 'ok', 'ref'].map(s => `<button data-plansec="${s}" aria-pressed="${st === s}" title="${esc(SN[s][1])}">${SN[s][0]}</button>`).join('')}</span>
      ${topic}<span class="spacer"></span><span class="small mut">${hint}</span></div>`;
  // a project file the mock files under Reference: Markdown as text, sheets as tables, each line and row open to a note
  // an audit as a findings register, as the mock shows Rebex's etching audit: what was screened, the conclusion, each finding with its proof, Reopen
  function findView(x) {
    const b = x.find, k = 'ref:' + x.id, seen = b.items.filter(f => f.state === 'Rebex mark seen').length;
    const items = b.items.map((f, i) => { const fk = `${x.id}~${i}`, op = (i === 0) !== S.open.has('fd:' + fk), r = S.reopen.get(fk);
      return `<div class="grp"><div class="rf-fh"><button class="fold" data-fold="fd:${esc(fk)}" aria-expanded="${op}">${esc(f.label)}</button><span class="tag${f.state === 'No Rebex mark' ? ' high' : ''}">${esc(f.state)}</span>${r !== undefined ? `<span class="saved">Reopened</span>${P.inertMark()}<button class="lk small" data-unreopen="${esc(fk)}">Undo</button>` : `<button class="lk small" data-freopen="${esc(fk)}" title="Say it is not settled, with why; the audit's record stays">Reopen</button>`}</div>
        ${r !== undefined ? `<textarea id="rf-ro-${i}" data-reopen="${esc(fk)}" rows="2" placeholder="Why reopen it?" aria-label="Why reopen ${esc(f.label)}">${esc(r)}</textarea>` : ''}
        ${op ? `${block(['p', f.text], `${k}~f~${i}`)}${f.src ? `<div class="figs">${block(['img', f.src, 'Proof: ' + f.label], `${k}~f${i}`)}</div>` : ''}
        <div class="rf-acts small"><span class="grow mut">Proof file: ${esc(f.file)} · fingerprint ${esc(f.sha)} · the original is kept unchanged; this is a copy</span><button class="lk small" data-copy="${esc(f.file)}" data-what="Path">Copy path</button></div>` : ''}</div>`; }).join('');
    return `<div class="rf-acts rf-vh">${ico(x.kind)}<b class="rf-vt">${esc(x.t)}</b>${stPill(stOf(x))}<span class="small mut">${esc(x.from)} · audited ${esc(dm(b.when))} · read-only here</span><span class="spacer"></span><button class="ib" data-link="${esc(x.id)}" title="Copy a link to this item" aria-label="Copy a link to this item">${ico('link')}</button></div>
      <div class="tiles">${b.screened.map(([n, w]) => `<div><b>${n.toLocaleString()}</b><span>${esc(w)} screened</span></div>`).join('')}<div><b>${b.items.length}</b><span>findings, ${seen} with the Rebex mark</span></div></div>
      <p ${at(k + '~c', 'Conclusion')}>${pin(k + '~c')}<b>Conclusion:</b> ${esc(b.conclusion)}</p>${noteList(k + '~c')}
      <p class="small"><b>Timeline:</b> audited ${esc(b.when)} · ${b.untouched ? 'no original photo or catalog choice changed' : 'originals changed'}</p>
      ${items}<details class="ddet"><summary>${pl(b.limits.length, 'limit', 'limits')} of this audit</summary><ul>${b.limits.map(l => `<li>${esc(l)}</li>`).join('')}</ul></details>
      ${foot(k, stOf(x), '', 'Click a finding, its proof or the conclusion to write a note on it')}`;
  }
  function extraView(x) {
    if (x.find) return findView(x);
    const k = 'ref:' + x.id, B = x.img ? [['img', x.img, x.note]] : x.md ? mdBlocks(x.md) : x.parts ? x.parts.flatMap(([t, h, rs]) => [['h', t], ['tbl', '', [h, ...rs], true]]) : [];
    // a designed message shows as the member sees it, sandboxed: no scripts run and its links go nowhere
    const body = x.html ? `<iframe class="rf-embed" sandbox="" srcdoc="${esc(x.html)}" title="${esc(x.t)}"></iframe>` : B.map((b, i) => block(b, `${k}~x~${i}`)).join('') || `<p class="mut">${x.note ? esc(x.note) : 'This file has no text.'}</p>`;
    return `<div class="rf-acts rf-vh">${ico(x.kind)}<b class="rf-vt">${esc(x.t)}</b>${stPill(stOf(x))}<span class="small mut">${esc(x.from)} · changed ${esc(dm(x.d))} · read-only here</span><span class="spacer"></span><button class="ib" data-link="${esc(x.id)}" title="Copy a link to this item" aria-label="Copy a link to this item">${ico('link')}</button></div>
      ${x.note && (x.html || B.length) && !x.img ? `<p class="small mut">${esc(x.note)}</p>` : ''}<div class="doc">${body}</div>
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
    return `<div class="viewer" id="rf-viewer">${p ? planView(p) : f ? flowView(f) : extraView(x)}</div>`;
  }

  /* ---------- draw and events ---------- */
  const here = () => el && el.isConnected && el.classList.contains('tab-reference');  // #p-main is shared by every tab
  function draw() {
    if (!here()) return;
    const a = document.activeElement, keep = a && a.id && el.contains(a) ? [a.id, a.selectionStart, a.selectionEnd, a.value] : null;
    const zt = (el.querySelector('.zoomv') || {}).scrollTop || 0;
    const [lst, dl] = list();
    el.innerHTML = `<div class="rf">${lst}${viewer()}${dl}${zoomView()}</div>`;
    const zv = el.querySelector('.zoomv'); if (zv) zv.scrollTop = zt;
    if (keep) { const b = document.getElementById(keep[0]); if (b) { if (keep[0] === 'rf-nt') b.value = keep[3]; b.focus(); try { b.setSelectionRange(keep[1], keep[2]); } catch {} } }
    if (S.note && !keep) { const t = document.getElementById('rf-nt'); if (t) t.focus({preventScroll: true}); }
    if (S.scroll) { S.scroll = false; const v = document.getElementById('rf-viewer'); if (v) v.scrollIntoView({block: 'start'}); }
  }
  const open = id => { S.sel = S.sel === id ? '' : id; S.note = ''; if (S.sel) { markSeen([id]); S.scroll = true; } history.replaceState(null, '', '#reference' + (S.sel ? '/' + encodeURIComponent(S.sel) : '')); draw(); };
  const copy = (t, what) => navigator.clipboard.writeText(t).then(() => ctx.toast(what + ' copied'), () => ctx.toast('Could not copy'));
  const fail = e => ctx.toast('Not saved: ' + e.message);
  const topics = cfg => { if (cfg && cfg.topics) { const names = cfg.topics.map(t => t.name); D.topics = (D.topics.includes('Unsorted') ? ['Unsorted'] : []).concat(names); } unsort(); };
  // shortcut: back-to-Unsorted is kept in this browser (plan_topics has no unsort move); add one to plan_topics when the prototype graduates
  const unsorted = () => ctx.prefs.get('ref-unsort', []);
  const unsort = () => { const u = unsorted(); D.plans.forEach(p => { if (u.includes(p.id)) p.topic = 'Unsorted'; }); if (u.length && !D.topics.includes('Unsorted')) D.topics = ['Unsorted', ...D.topics]; };
  const setUnsort = (ids, on) => { const u = unsorted().filter(x => !ids.includes(x)); ctx.prefs.set('ref-unsort', on ? [...u, ...ids] : u); };
  async function topicChange(body, done, undo, msg) {
    try { topics(await ctx.api('api/plan-topics', body)); done(); draw(); ctx.toast(msg, {undo: async () => { try { await undo(); draw(); } catch (e) { fail(e); } }}); }
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
      S.note = d.line; draw(); return;
    }
    if (b.tagName === 'SUMMARY') { S.det = !b.parentElement.open; return; }  // kept across redraws
    if (b.tagName !== 'BUTTON') return;
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
    if (d.unreopen) { const fk = d.unreopen, t = S.reopen.get(fk); S.reopen.delete(fk); draw(); return ctx.inert('Reopen taken back', () => { S.reopen.set(fk, t); draw(); }); }
    if (d.wmopen) return ctx.toast(`Opens “${d.wmopen}” in Windmill, in a new tab`, {inert: true});
    if (d.sec) { S.sec = d.sec; return draw(); }
    if (d.kind) { S.kind = S.kind === d.kind ? '' : d.kind; return draw(); }
    if (d.allseen !== undefined) { markSeen([...rows().map(r => r.id), ...docs().map(f => f.id)]); return draw(); }
    if (d.fx) { S.fx.has(d.fx) ? S.fx.delete(d.fx) : S.fx.add(d.fx); return draw(); }
    if (d.rv !== undefined) { S.rv[S.sel] = +d.rv; return draw(); }
    if (d.marks !== undefined) { S.marks = !S.marks; return draw(); }
    if (d.clf !== undefined) { if (!d.clf) S.clf.clear(); else S.clf.has(d.clf) ? S.clf.delete(d.clf) : S.clf.add(d.clf); return draw(); }
    if (d.dk !== undefined) { S.dk = d.dk; return draw(); }
    if (d.fold) { S.open.has(d.fold) ? S.open.delete(d.fold) : S.open.add(d.fold); return draw(); }
    if (d.copy) return copy(d.copy, d.what || (d.copy.startsWith('~/') ? 'Path' : 'Text'));
    if (d.link) return copy(location.origin + location.pathname + '#reference/' + encodeURIComponent(d.link), 'Link');
    if (d.dopen) {
      const f = docs().find(x => x.id === d.dopen);
      if (!f) return;
      markSeen([f.id]);
      // shortcut: no route serves the project's files yet, so the prototype says what opens; its path still copies beside it
      if (!f.md) return ctx.toast(`Opens “${f.n}” in a new tab${f.k === 'pdf' ? '; PDFs open in place later' : ''}`, {inert: true});
      S.dsel = S.dsel === f.id ? '' : f.id; S.note = ''; return draw();
    }
    if (d.note) { S.note = d.note; S.tgt = null; return draw(); }
    if (d.ncancel !== undefined) { S.note = ''; return draw(); }
    if (d.zoom) {
      const k = d.zk, im = S.full && S.full.k === k ? null : el.querySelector(`[data-line="${CSS.escape(k)}"] img`);
      ctx.prefs.set('ref-zoom', {...ctx.prefs.get('ref-zoom', {}), [k]: +d.zoom});
      S.full = im ? {k, src: im.getAttribute('src'), cap: im.getAttribute('alt'), z: +d.zoom} : {...S.full, z: +d.zoom};
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
        mine.push({id: c.id, a: k, text: c.text, who: c.author_name || 'You', at: c.created_at || new Date().toISOString(), v: c.version, target: c.target || target});
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
      for (const [i, p] of ps.entries()) { topics(await ctx.api('api/plan-topics', {move: p.id, topic, ...(isNew && !i ? {new: true} : {})})); p.topic = topic; }
      draw(); ctx.toast(`${pl(ps.length, 'plan', 'plans')} filed under “${topic}”`, {undo: () => { setUnsort(ids, true); unsort(); draw(); }});
    } catch (e) { draw(); fail(e); }
  }
  function renameTopic(old, to) {
    if (!to || to === old) { S.trn = ''; return draw(); }
    if (old === 'Unsorted') return unsortedTo(to, !D.topics.includes(to));
    const set = (a, b) => D.plans.forEach(p => { if (p.topic === a) p.topic = b; });
    topicChange({rename: old, to}, () => { S.trn = ''; set(old, to); },
      async () => { topics(await ctx.api('api/plan-topics', {rename: to, to: old})); set(to, old); }, `Topic renamed to “${to}”`);
  }
  function combine(from, into) {
    if (from === 'Unsorted') return unsortedTo(into, false);
    const moved = D.plans.filter(p => p.topic === from);
    S.tmerge = '';
    topicChange({merge: from, into}, () => moved.forEach(p => p.topic = into),
      async () => {  // no un-combine endpoint: recreate the topic and move its plans back (its title words stay with the other topic)
        for (const [i, p] of moved.entries()) topics(await ctx.api('api/plan-topics', {move: p.id, topic: from, ...(i ? {} : {new: true})}));
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
      old === 'Unsorted' ? async () => back() : async () => { topics(await ctx.api('api/plan-topics', {move: p.id, topic: old})); p.topic = old; },
      `Moved to “${topic}”`);
  }
  function onInput(e) {
    if (here() && e.target.id === 'rf-q') { S.q = e.target.value; draw(); }
    if (here() && e.target.dataset.reopen) S.reopen.set(e.target.dataset.reopen, e.target.value);
  }  function closeZoom() { if (S.full && S.note === S.full.k) S.note = ''; S.full = null; draw(); }
  function onDocKey(e) { if (here() && S.full && e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeZoom(); } }
  function onKey(e) {
    if (!here() || S.full) return;
    if (e.target.id === 'rf-trn' && e.key === 'Enter') renameTopic(S.trn, e.target.value.trim());
    if (e.key === 'Escape' && (S.trn || S.tmerge || S.note)) { S.trn = S.tmerge = S.note = ''; draw(); }
    if (e.target.matches('[data-line]') && e.key === 'Enter') { S.note = e.target.dataset.line; draw(); }
  }

  Proto.tab({key: 'reference',
    chip: async c => { ctx = c; D = await c.data('reference'); unsort(); const n = countChanged(); return n ? {text: `${n} changed`, tone: 'amber'} : null; },
    render: async (main, c, anchor) => {
      ctx = c; el = main;
      if (!D) { main.innerHTML = '<p class="mut">Reading Reference…</p>'; D = await c.data('reference'); }
      unsort();
      taskBack = '';
      const id = anchor ? decodeURIComponent(anchor) : '';
      if (id && (D.plans.some(p => p.id === id) || D.flows.some(f => f.id === id) || xOf(id))) { S.sel = id; S.scroll = true; markSeen([id]); }
      if (!main._rf) {
        main._rf = true;
        main.addEventListener('click', onClick); main.addEventListener('change', onChange);
        main.addEventListener('input', onInput); main.addEventListener('keydown', onKey);
        document.addEventListener('keydown', onDocKey, true);  // Esc closes the picture viewer wherever the focus is
      }
      draw();
    }});
})();
