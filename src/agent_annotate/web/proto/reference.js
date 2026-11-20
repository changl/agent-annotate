/* Reference tab: plans by topic, the go-live checklist, Windmill workflows and the project's documents (build-list stage 3).
   Ported from round9/final/mock.html (reference, viewer, checklistHtml, ftree, docList) onto the module contract.
   Saves use today's endpoints: api/plan-topics (rename, combine, move) and api/comments (notes, Undo = DELETE). */
(function () {
  const P = window.Proto;
  const S = {q: '', sec: 'all', kind: '', sel: '', fx: new Set(), rv: {}, marks: true, clf: new Set(), dk: '', dsel: '', open: new Set(),
    trn: '', tmerge: '', note: '', scroll: false};
  let ctx, D, el, mine = [];  // mine: notes written in this visit, so Undo can take them back
  const blocks = {}, loading = {};
  const ico = (n, l) => P.icon(n, l), pl = (n, a, b) => `${n} ${n === 1 ? a : b}`;
  const esc = s => ctx.esc(s);
  const dm = s => { const d = new Date(String(s).slice(0, 10) + 'T12:00'); return isNaN(d) ? '' : d.toLocaleDateString('en-GB', {day: 'numeric', month: 'short'}); };
  const KN = {plan: 'Plans', check: 'Checklists', flow: 'Workflows', doc: 'Documents'};
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
  const lastTs = p => p.revs[p.revs.length - 1][1];
  const nSteps = ss => ss.reduce((n, s) => n + 1 + nSteps(s.sub || []) + (s.br || []).reduce((m, b) => m + nSteps(b[1]), 0), 0);
  function rows() {
    const out = D.plans.map(p => ({id: p.id, t: p.t, m: `${pl(p.revs.length, 'revision', 'revisions')} · changed ${dm(lastTs(p))}`, kind: p.kind, st: p.st,
      g: p.kind === 'plan' ? 't:' + p.topic : 'k:check', p, stamp: lastTs(p), s: p.topic}));
    for (const f of D.flows) out.push({id: f.id, t: f.t, m: `Windmill · runs ${f.when} · ${pl(nSteps(f.steps), 'step', 'steps')} · ${f.last ? `last run ${dm(f.last.at)}, ${f.last.ok ? 'passed' : 'failed'}` : 'not run yet'}`,
      kind: 'flow', st: 'ref', g: 'k:flow', f, stamp: f.edited, s: f.what + ' ' + JSON.stringify(f.steps.map(x => x.n))});
    out.forEach(r => r.ch = changed(r.id, r.stamp));
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
  function noteList(k) {
    const ns = notesAt(k), box = S.note === k;
    if (!ns.length && !box) return '';
    return `<div class="rf-notes">${ns.map(n => `<div class="rf-nt"><span class="rf-nw">${ico('note')}<b>${esc(n.who)}</b> · ${esc(dm(n.at))}</span> ${esc(n.text)}${mine.some(x => x.id === n.id) ? ` <button class="lk small" data-nundo="${esc(n.id)}">Undo</button>` : ''}</div>`).join('')}
      ${box ? `<div class="rf-box"><textarea id="rf-nt" rows="3" placeholder="Write a note for the agent: a question, a change, or ask for another version" aria-label="Your note"></textarea>
        <div class="rf-acts"><button class="btn sm pri" data-nsave="${esc(k)}">Save note</button><button class="btn sm" data-ncancel>Cancel</button><span class="small mut">Saved on this page for the agent</span></div></div>` : ''}</div>`;
  }
  const at = (k, label) => `data-line="${esc(k)}" data-label="${esc(String(label || '').slice(0, 80))}"`;

  /* ---------- a plan revision, read from today's plans/<id>/<v>.html as blocks ---------- */
  const CHROME = 'header.hdr,aside,nav,#popover,#legend,script,style,button,select,textarea,input,noscript,template,svg';
  const BLOCK = /^(P|DIV|SECTION|ARTICLE|MAIN|H[1-6]|UL|OL|LI|TABLE|PRE|FIGURE|IMG|BLOCKQUOTE|DETAILS|SUMMARY|DL|DT|DD|HR|HEADER|FOOTER)$/;
  function parse(html) {
    const doc = new DOMParser().parseFromString(html, 'text/html'), out = [], T = e => e.textContent.replace(/\s+/g, ' ').trim();
    doc.querySelectorAll(CHROME).forEach(e => e.remove());
    const img = e => { const s = (e.getAttribute('src') || '').replace(/^\/annotate\/reviews\/[^/]+\//, ''); if (s && !s.startsWith('data:')) out.push(['img', new URL(s, location.origin + ctx.base).href, e.getAttribute('alt') || '']); };
    (function walk(n) {
      for (const e of n.children) {
        const t = e.tagName;
        if (/^H[1-6]$/.test(t)) { const x = T(e); if (x) out.push(['h', x]); }
        else if (t === 'TABLE') { const r = [...e.rows].map(row => [...row.cells].map(T)).filter(row => row.some(Boolean)); if (r.length) out.push(['tbl', r.flat().join(' '), r, !!e.querySelector('th')]); }
        else if (t === 'PRE') out.push(['pre', e.textContent.replace(/\n+$/, '')]);
        else if (t === 'IMG') img(e);
        else if (t === 'LI') { const c = e.cloneNode(true); c.querySelectorAll('ul,ol,table,pre').forEach(x => x.remove()); const x = T(c); if (x) out.push(['li', x]); e.querySelectorAll(':scope > ul, :scope > ol').forEach(walk); }
        else if ([...e.children].some(c => BLOCK.test(c.tagName))) walk(e);
        else { e.querySelectorAll('img').forEach(img); const x = T(e); if (x) out.push([t === 'DT' || t === 'SUMMARY' ? 'h' : 'p', x]); }
      }
    })(doc.body);
    return out;
  }
  function need(id, v) {
    const k = id + '~' + v;
    if (blocks[k] || loading[k]) return blocks[k];
    loading[k] = fetch(`${ctx.base}plans/${encodeURIComponent(id)}/${encodeURIComponent(v)}.html`, {cache: 'no-store'})
      .then(r => r.ok ? r.text() : Promise.reject(new Error('HTTP ' + r.status)))
      .then(h => { blocks[k] = parse(h); }, e => { blocks[k] = [['p', 'This revision could not be read: ' + e.message]]; })
      .then(() => draw());
    return null;
  }

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
    if (n * m > 4e6) return B.map((_, b) => ({k: 'same', b}));  // too long to pair: show it plain
    const L = Array.from({length: n + 1}, () => new Uint16Array(m + 1));
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
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
    while (i < n && j < m) { if (x[i] === y[j]) { flush(); out.push({k: 'same', a: i++, b: j++}); } else if (L[i + 1][j] >= L[i][j + 1]) ga.push(i++); else gb.push(j++); }
    while (i < n) ga.push(i++); while (j < m) gb.push(j++); flush();
    return out;
  }

  const untag = t => t.replace(/^[A-Za-z0-9][\w.-]{3,}:\s*/, '');  // a workstream name before the title is a worker's, not his
  /* a task a plan names reads "title · bead id · state", coloured by its state */
  const beadIn = h => h.replace(/\bFLD-[a-z0-9]{3,6}(?:\.\d+)*\b/g, id => { const b = D.beads[id]; if (!b) return id;
    const t = untag(b[0]);
    return `<span class="rf-bd st-${BST[b[1]] || 'none'}" title="Its task on the board"><i class="dot"></i>${esc(t)} · <code>${id}</code> · ${esc(b[1])}</span>`; });

  // one block: heading, paragraph, list line, code, table or picture; `inner` replaces the text (diff marks)
  function block(b, k, inner, tag) {
    const [kind, t, x, hd] = b, tg = tag || '', a = at(k, kind === 'img' ? 'Picture: ' + x : kind === 'tbl' ? 'Table: ' + x[0].join(' · ') : t);
    const body = kind === 'tbl' ? `<div class="tblw" style="--c:${Math.max(...x.map(r => r.length))}" ${a}>${pin(k)}<table>${x.map((r, ri) => `<tr>${r.map(c => ri === 0 && hd ? `<th>${esc(c)}</th>` : `<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</table>${tg}</div>`
      : kind === 'img' ? `<figure ${a}>${pin(k)}<img src="${esc(t)}" alt="${esc(x || 'Picture')}" loading="lazy">${x ? `<figcaption>${esc(x)}</figcaption>` : ''}${tg}</figure>`
      : kind === 'pre' ? `<div class="rf-code" ${a}>${pin(k)}<pre><code>${esc(t)}</code></pre><button class="btn sm" data-copy="${esc(t)}">${ico('copy')}Copy</button>${tg}</div>`
      : `<${kind === 'h' ? 'h4' : 'p'} class="${kind === 'li' ? 'li' : ''}" ${a}>${pin(k)}${inner || esc(t)}${tg}</${kind === 'h' ? 'h4' : 'p'}>`;
    return body + noteList(k);
  }

  /* ---------- the list ---------- */
  function topicHead(t, n) {
    const real = D.topics.includes(t) && t !== 'Unsorted', others = D.topics.filter(x => x !== t && x !== 'Unsorted');
    if (S.trn === t) return `<div class="r8gh">${ico('plan')}<input type="text" id="rf-trn" value="${esc(t)}" aria-label="New name for the topic ${esc(t)}"><button class="btn sm pri" data-trnsave="${esc(t)}">Save</button><button class="ib" data-trn="" title="Cancel" aria-label="Cancel renaming">${ico('x')}</button></div>`;
    return `<div class="r8gh">${ico('plan')}<span class="gt">${esc(t)}</span><span class="n">${n}</span><span class="spacer"></span>${real ? `<button class="tact" data-trn="${esc(t)}" title="Rename this topic">${ico('edit')}<span>Rename</span></button><button class="tact" data-tmerge="${esc(t)}" aria-expanded="${S.tmerge === t}" title="Combine this topic with another: its plans move into that topic, and this one goes away">${ico('combine')}<span>Combine</span></button>` : ''}
      ${S.tmerge === t ? `<div class="pop" role="menu"><div class="small mut">Combine with… its ${pl(n, 'plan moves', 'plans move')} into</div>${others.map(x => `<button role="menuitem" data-tmergeto="${esc(x)}">${esc(x)}</button>`).join('') || '<div class="small mut">No other topic yet</div>'}</div>` : ''}</div>`;
  }
  const stPill = s => `<span class="rf-st ${s}" title="${esc(SN[s][1])}"><i></i>${SN[s][0]}</span>`;
  const chg = '<span class="rf-new" title="Changed since you last looked">changed</span>';
  const row = r => `<button class="r8row" data-ref="${esc(r.id)}" aria-pressed="${S.sel === r.id}">${ico(r.kind)}<span class="t">${esc(r.t)} ${r.ch ? chg : ''}</span><span class="s">${stPill(r.st)}</span><span class="m">${esc(r.m)}</span></button>`;

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
    const shown = R.filter(r => hit(r) && inSt(r) && inK(r)), docsOn = (!S.kind || S.kind === 'doc') && (S.sec === 'all' || S.sec === 'ref');
    const nd = F.filter(dhit).length;
    const stN = s => R.filter(r => hit(r) && inK(r) && (s === 'all' || r.st === s)).length + ((!S.kind || S.kind === 'doc') && (s === 'all' || s === 'ref') ? nd : 0);
    const kN = k => k === 'doc' ? (S.sec === 'all' || S.sec === 'ref' ? nd : 0) : R.filter(r => hit(r) && inSt(r) && r.kind === k).length;
    const gs = [...new Set(shown.map(r => r.g))].sort((a, b) => {
      const o = g => g[0] === 't' ? D.topics.indexOf(g.slice(2)) : 100 + ['check', 'flow'].indexOf(g.slice(2));
      return o(a) - o(b); });
    const nch = R.filter(r => r.ch).length + F.filter(f => f.ch).length;
    const bar = `<div class="r8bar"><input type="search" id="rf-q" placeholder="Find a plan, checklist, workflow or document" aria-label="Find in Reference" value="${esc(S.q)}">
      <span class="rf-chips" role="group" aria-label="State">${['all', 'prop', 'ok', 'ref'].map(s => `<button class="chipb" data-sec="${s}" aria-pressed="${S.sec === s}" title="${s === 'all' ? 'Every item' : esc(SN[s][1])}">${s === 'all' ? 'All' : SN[s][0]} <span class="n">${stN(s)}</span></button>`).join('')}</span>
      <span class="sep" aria-hidden="true"></span><span class="rf-chips" role="group" aria-label="Kind">${Object.keys(KN).map(k => `<button class="chipb" data-kind="${k}" aria-pressed="${S.kind === k}" title="Only ${KN[k].toLowerCase()}">${ico(k === 'doc' ? 'doc' : k)}${KN[k]} <span class="n">${kN(k)}</span></button>`).join('')}</span>
      <span class="spacer"></span><span class="small mut rf-chl">${nch ? `${chg} ${pl(nch, 'item changed', 'items changed')} since you last looked · <button class="lk small" data-allseen>Mark all as seen</button>` : 'Nothing changed since you last looked'}</span></div>`;
    const lst = gs.length ? `<div class="r8list">${gs.map(g => { const rs = shown.filter(r => r.g === g);
      return `<div class="r8g">${g[0] === 't' ? topicHead(g.slice(2), rs.length) : `<div class="r8gh">${ico(g.slice(2))}<span class="gt">${KN[g.slice(2)]}</span><span class="n">${rs.length}</span></div>`}${rs.map(r => r.kind === 'flow' ? flowRow(r) : row(r)).join('')}</div>`; }).join('')}</div>` : (docsOn && nd ? '' : '<p class="mut">Nothing matches.</p>');
    return bar + lst + (docsOn ? docList(F.filter(dhit), F.length) : '');
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
    const drow = f => `<div class="doc9"${S.dsel === f.id ? ' aria-current="true"' : ''}>${dic(f.k)}<button class="nm" data-dopen="${esc(f.id)}" ${f.md ? `aria-expanded="${S.dsel === f.id}" title="Open it here"` : 'title="Copies its path, to open it from Finder"'}>${esc(f.n)} ${f.ch ? chg : ''}${f.sub ? `<span class="sub">${esc(f.sub)}</span>` : ''}</button><span class="sz">${kb(f.kb)}</span><span class="d9t">${esc(dm(f.d))}</span><button class="ib" data-copy="${esc(path(f))}" title="Copy its path" aria-label="Copy the path of ${esc(f.n)}">${ico('copy')}</button></div>${S.dsel === f.id && f.md ? docView(f) : ''}`;
    return `<section class="rf-docs" aria-label="Documents"><div class="r8gh rf-dh">${ico('doc')}<span class="gt">Documents</span><span class="n">${pl(total, 'file', 'files')} in this project's folder · Markdown opens here, other kinds copy their path for Finder</span></div>
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
      return `<div class="cl9" ${at(k, it)}>${cm(st)}<span class="tx">${pin(k)}${esc(it)}<span class="small mut rf-task">${bead ? `${cm(b0 ? b0[1] : 'none', 'Task ')}<span class="rf-bd st-${BST[b0 && b0[1]] || 'none'}">${esc(t || 'not on the board')} · <code>${esc(bead)}</code> · ${esc(b0 ? b0[1] : 'unknown')}</span>` : 'no task'}</span></span>
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
    else {
      const v = p.revs[cur][0], key = i => `${k}~${v}~${i}`, mk = S.marks && cur === last && n > 1;
      if (mk) {
        const al = alignBlocks(A, B), nk = x => al.filter(y => y.k === x).length, when = `in revision ${n}`, tag = w => ` <span class="rf-tag">${w} ${when}</span>`;
        csum = `${pl(nk('chg'), 'part', 'parts')} changed · ${nk('add')} added · ${nk('del')} removed`;
        doc = al.map(x => x.k === 'same' ? block(B[x.b], key(x.b))
          : x.k === 'chg' ? block(B[x.b], key(x.b), ['img', 'tbl', 'pre'].includes(B[x.b][0]) ? '' : wdiff(A[x.a][1], B[x.b][1]), tag('changed'))
          : x.k === 'add' ? block(B[x.b], key(x.b), ['img', 'tbl', 'pre'].includes(B[x.b][0]) ? '' : `<ins>${esc(B[x.b][1])}</ins>`, tag('added'))
          : `<p class="small"><del>${esc(A[x.a][0] === 'img' ? 'Picture: ' + (A[x.a][2] || '') : A[x.a][0] === 'tbl' ? 'Table: ' + A[x.a][2][0].join(' · ') : A[x.a][1])}</del>${tag('removed')}</p>`).join('');
      } else doc = B.map((b, i) => block(b, key(i))).join('') || '<p class="mut">This revision has no text.</p>';
      doc = beadIn(doc);
    }
    const vlist = n > 1 ? `<nav class="vlist" aria-label="Revisions"><h5>${pl(n, 'revision', 'revisions')}</h5>${p.revs.map((r, i) => [r, i]).reverse().map(([[v, ts, label], i]) =>
      `<button class="vrow" data-rv="${i}" aria-current="${i === cur}"><b>Revision ${i + 1} · ${esc(dm(ts))}${i === last ? ' · newest' : ''}</b><span>${esc(i === last && csum ? csum : label || '')}</span></button>`).join('')}</nav>` : '';
    const revbar = n > 1 ? `<div class="revbar"><b>Revision ${cur + 1} of ${n}</b>${cur === last ? `<span>${S.marks ? `${csum ? csum + ', ' : ''}marked word by word against revision ${n - 1}: <del>struck</del> words left, <ins>marked</ins> words came in` : 'marks hidden'}</span><button class="lk small" data-marks>${S.marks ? 'Hide marks' : 'Show marks'}</button>` : `<span>an earlier revision, as it read</span><button class="lk small" data-rv="${last}">Back to the newest</button>`}</div>` : '';
    const text = `<div class="${vlist ? 'r8v' : ''}"><div><div class="doc">${doc}</div></div>${vlist}</div>`;
    const topics = D.topics.filter(t => t !== 'Unsorted');
    return `<div class="rf-acts rf-vh">${ico(p.kind)}<b class="rf-vt">${esc(p.t)}</b>${stPill(p.st)}<span class="spacer"></span>
        ${p.kind === 'plan' ? `<label class="small mut rf-topic">Topic <select data-move="${esc(p.id)}" aria-label="Topic">${p.topic === 'Unsorted' ? '<option selected>Unsorted</option>' : ''}${topics.map(t => `<option${t === p.topic ? ' selected' : ''}>${esc(t)}</option>`).join('')}<option value="__new">New topic…</option></select></label>` : ''}
        <button class="ib" data-link="${esc(p.id)}" title="Copy a link to this item" aria-label="Copy a link to this item">${ico('link')}</button></div>
      ${isCheck ? checklistHtml() + `<details class="rf-det"${S.det ? ' open' : ''}><summary>The checklist plan as written, with its ${pl(n, 'revision', 'revisions')}</summary>${revbar}${text}</details>` : revbar + text}
      ${noteList(k + '~all')}<div class="rf-acts"><button class="btn sm" data-note="${esc(k)}~all">${ico('note')}Write a note</button><span class="small mut">Click any line, table, picture${isCheck ? ', row or the chart' : ''} to write a note on it. To ask for another version, say so in a note.</span></div>`;
  }
  function flowView(f) {
    const k = 'ref:' + f.id;
    return `<div class="rf-acts rf-vh">${ico('flow')}<b class="rf-vt">${esc(f.t)}</b><span class="small mut">Windmill workflow · runs ${esc(f.when)} · last edited ${esc(dm(f.edited))} · read-only here</span><span class="spacer"></span><button class="ib" data-link="${esc(f.id)}" title="Copy a link to this item" aria-label="Copy a link to this item">${ico('link')}</button></div>
      <p class="rf-what" ${at(k + '~what', f.what)}>${pin(k + '~what')}${esc(f.what)}</p>${noteList(k + '~what')}
      <p class="small"><b>${lastRun(f)}</b></p>${ftree(f.steps, k, !!f.last)}${failTree(f, k)}
      <p class="small mut">As deployed in Windmill today. Change it there or ask the agent in a note; this view only shows it.</p>
      ${noteList(k + '~all')}<div class="rf-acts"><button class="btn sm" data-note="${esc(k)}~all">${ico('note')}Write a note</button><span class="small mut">Click a step to write a note on it</span></div>`;
  }
  function viewer() {
    const p = D.plans.find(x => x.id === S.sel), f = !p && D.flows.find(x => x.id === S.sel);
    if (!p && !f) return '';
    return `<div class="viewer" id="rf-viewer">${p ? planView(p) : flowView(f)}</div>`;
  }

  /* ---------- draw and events ---------- */
  const here = () => el && el.isConnected && el.classList.contains('tab-reference');  // #p-main is shared by every tab
  function draw() {
    if (!here()) return;
    const a = document.activeElement, keep = a && a.id && el.contains(a) ? [a.id, a.selectionStart, a.selectionEnd, a.value] : null;
    el.innerHTML = `<div class="rf">${list()}${viewer()}</div>`;
    if (keep) { const b = document.getElementById(keep[0]); if (b) { if (keep[0] === 'rf-nt') b.value = keep[3]; b.focus(); try { b.setSelectionRange(keep[1], keep[2]); } catch {} } }
    if (S.note && !keep) { const t = document.getElementById('rf-nt'); if (t) t.focus({preventScroll: true}); }
    if (S.scroll) { S.scroll = false; const v = document.getElementById('rf-viewer'); if (v) v.scrollIntoView({block: 'start'}); }
  }
  const open = id => { S.sel = S.sel === id ? '' : id; S.note = ''; if (S.sel) { markSeen([id]); S.scroll = true; } history.replaceState(null, '', '#reference' + (S.sel ? '/' + encodeURIComponent(S.sel) : '')); draw(); };
  const copy = (t, what) => navigator.clipboard.writeText(t).then(() => ctx.toast(what + ' copied'), () => ctx.toast('Could not copy'));
  const fail = e => ctx.toast('Not saved: ' + e.message);
  const topics = cfg => { if (cfg && cfg.topics) { const names = cfg.topics.map(t => t.name); D.topics = (D.topics.includes('Unsorted') ? ['Unsorted'] : []).concat(names); } };
  async function topicChange(body, done, undo, msg) {
    try { topics(await ctx.api('api/plan-topics', body)); done(); draw(); ctx.toast(msg, {undo: async () => { try { await undo(); draw(); } catch (e) { fail(e); } }}); }
    catch (e) { fail(e); }
  }

  async function onClick(e) {
    if (!here()) return;
    const b =e.target.closest('button,[data-line],summary,a,select,input,textarea');
    if (!b || !el.contains(b)) { if (S.tmerge) { S.tmerge = ''; draw(); } return; }
    const d = b.dataset;
    if (b.matches('[data-line]')) {
      if (window.getSelection().toString()) return;
      S.note = d.line; draw(); return;
    }
    if (b.tagName === 'SUMMARY') { S.det = !b.parentElement.open; return; }  // kept across redraws
    if (b.tagName !== 'BUTTON') return;
    if (S.tmerge && d.tmerge === undefined && d.tmergeto === undefined) S.tmerge = '';
    if (d.ref !== undefined) return open(d.ref);
    if (d.sec) { S.sec = d.sec; return draw(); }
    if (d.kind) { S.kind = S.kind === d.kind ? '' : d.kind; return draw(); }
    if (d.allseen !== undefined) { markSeen([...rows().map(r => r.id), ...docs().map(f => f.id)]); return draw(); }
    if (d.fx) { S.fx.has(d.fx) ? S.fx.delete(d.fx) : S.fx.add(d.fx); return draw(); }
    if (d.rv !== undefined) { S.rv[S.sel] = +d.rv; return draw(); }
    if (d.marks !== undefined) { S.marks = !S.marks; return draw(); }
    if (d.clf !== undefined) { if (!d.clf) S.clf.clear(); else S.clf.has(d.clf) ? S.clf.delete(d.clf) : S.clf.add(d.clf); return draw(); }
    if (d.dk !== undefined) { S.dk = d.dk; return draw(); }
    if (d.fold) { S.open.has(d.fold) ? S.open.delete(d.fold) : S.open.add(d.fold); return draw(); }
    if (d.copy) return copy(d.copy, d.copy.startsWith('~/') ? 'Path' : 'Text');
    if (d.link) return copy(location.origin + location.pathname + '#reference/' + encodeURIComponent(d.link), 'Link');
    if (d.dopen) {
      const f = docs().find(x => x.id === d.dopen);
      if (!f) return;
      markSeen([f.id]);
      if (!f.md) return copy(path(f), 'Path');
      S.dsel = S.dsel === f.id ? '' : f.id; S.note = ''; return draw();
    }
    if (d.note) { S.note = d.note; return draw(); }
    if (d.ncancel !== undefined) { S.note = ''; return draw(); }
    if (d.nsave) {
      const k = d.nsave, text = (document.getElementById('rf-nt').value || '').trim();
      if (!text) return ctx.toast('Write something first');
      const src = el.querySelector(`[data-line="${CSS.escape(k)}"]`);
      try {
        const c = await ctx.api('api/comments', {anchor_id: k, anchor_label: src ? src.dataset.label : 'Reference', text, ...noteMeta(k)});
        mine.push({id: c.id, a: k, text: c.text, who: c.author_name || 'You', at: c.created_at || new Date().toISOString(), v: c.version});
        S.note = ''; draw(); ctx.refreshChips();
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
  function renameTopic(old, to) {
    if (!to || to === old) { S.trn = ''; return draw(); }
    const set = (a, b) => D.plans.forEach(p => { if (p.topic === a) p.topic = b; });
    topicChange({rename: old, to}, () => { S.trn = ''; set(old, to); },
      async () => { topics(await ctx.api('api/plan-topics', {rename: to, to: old})); set(to, old); }, `Topic renamed to “${to}”`);
  }
  function combine(from, into) {
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
    topicChange({move: p.id, topic, ...(isNew ? {new: true} : {})}, () => { p.topic = topic; },
      old === 'Unsorted' ? async () => ctx.toast('It stays in “' + topic + '”: an item cannot go back to Unsorted') : async () => { topics(await ctx.api('api/plan-topics', {move: p.id, topic: old})); p.topic = old; },
      `Moved to “${topic}”`);
  }
  function onInput(e) { if (here() && e.target.id === 'rf-q') { S.q = e.target.value; draw(); } }
  function onKey(e) {
    if (!here()) return;
    if (e.target.id === 'rf-trn' && e.key === 'Enter') renameTopic(S.trn, e.target.value.trim());
    if (e.key === 'Escape' && (S.trn || S.tmerge || S.note)) { S.trn = S.tmerge = S.note = ''; draw(); }
    if (e.target.matches('[data-line]') && e.key === 'Enter') { S.note = e.target.dataset.line; draw(); }
  }

  Proto.tab({key: 'reference',
    chip: async c => { ctx = c; D = await c.data('reference'); const n = countChanged(); return n ? {text: `${n} changed`, tone: 'amber'} : null; },
    render: async (main, c, anchor) => {
      ctx = c; el = main;
      if (!D) { main.innerHTML = '<p class="mut">Reading Reference…</p>'; D = await c.data('reference'); }
      const id = anchor ? decodeURIComponent(anchor) : '';
      if (id && (D.plans.some(p => p.id === id) || D.flows.some(f => f.id === id))) { S.sel = id; S.scroll = true; markSeen([id]); }
      if (!main._rf) {
        main._rf = true;
        main.addEventListener('click', onClick); main.addEventListener('change', onChange);
        main.addEventListener('input', onInput); main.addEventListener('keydown', onKey);
      }
      draw();
    }});
})();
