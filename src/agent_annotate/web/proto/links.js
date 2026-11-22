/* Pages & links tab (#84): this project's pages, each with a Copy link icon that copies at once, no access check
   (#85, #147); repos and folders with Copy path (#86); a version that fails to load says why, with Retry and Tell
   the agent (#87, shared with History through Proto.viewVersion); People, with two roles (#128). No usage report
   and no other projects' documents. */
(function () {
  'use strict';
  const P = window.Proto = window.Proto || {};
  const S = {arch: false, view: '', copied: '', kept: '', dq: '', dk: '', dsel: -1, open: new Set(), note: '', tgt: null, bad: false, rv: {}, marks: false, hl: '', scroll: false};
  let mine = [], SAVING = false;  // notes written here this visit, so Undo can take them back; SAVING: the editor's Save note is out
  const DK = {md: ['file-md', 'Markdown'], pdf: ['file-pdf', 'PDF'], word: ['file-word', 'Word'], sheet: ['file-sheet', 'Sheet'], video: ['file-video', 'Video']};
  const kb = n => n >= 1024 ? `${(n / 1024).toFixed(1)} MB` : `${n} KB`;
  const fpath = f => ['~/projects/FastLane Drive', f.g, f.sub, f.n].filter(Boolean).join('/');
  const dm = d => { const t = new Date(String(d).slice(0, 10) + 'T12:00'); return isNaN(t) ? String(d || '') : t.toLocaleDateString('en-GB', {day: 'numeric', month: 'short'}); };
  const mdBlocks = t => P.media.blocks(t);  // the one Markdown reader, shared with Reference (Proto.media)
  const rowsOf = b => Array.isArray(b[1]) ? b[1] : b[2];  // a kept document's table is [tbl, rows]; a Markdown one [tbl, text, rows]
  let docK = '';  // the document being drawn, set by its view: its pictures' keys start with it
  let CUR = null;  // the feed being drawn, for the pictures' markers
  // `line(i)` (optional) gives block i its note attributes and returns what follows it: its notes and composer
  // `tag` (optional): a revision mark after the text; `ins` marks the text itself as new
  // each body row of a table takes its own note (line <i>~r<n>), as in Reference; the header row notes the whole table
  // `id` (optional): the block's anchor from the feed, the published page's own (reference.html_blocks), instead of its number;
  // a table's is [its own, then each body row's]
  const blockHtml = (b, i, esc, line, tag = '', ins = false, id = null) => { if (id != null) i = Array.isArray(id) ? id[0] : id;
    const rk = ri => Array.isArray(id) && id[ri] ? id[ri] : `${i}~r${ri}`;
    const [k, t] = b, a = line ? ` data-line="${esc(i)}" tabindex="0"` : '', after = line ? line(i) : '', x = ins ? `<ins>${esc(t)}</ins>` : esc(t);
    // a picture, on its own line or in a table cell (its row is the anchor, as today): Proto.media's figure, Full size here,
    // at the size last picked for it, by its key: the document and its place (Proto.media.pk)
    // a picture that takes notes shows its point markers, as Reference's (the notes kit's pins; r12 audit18 reference 3)
    // its size is kept per revision (data-pk); its notes, like its line's, by the place alone (data-nk)
    const pic = (src, alt, n, a = '', place = String(i)) => { const k = docK + '~' + place, nk = k.replace(/~rev\d+(?=~)/, ''), pk = `data-pk="${esc(k)}" data-nk="${esc(nk)}"`, z = P.media.zoom(k), f = P.media.fig(src, alt, n, z, ` data-lzoom="${z}" ${pk}`, ` data-lzoom ${pk}`, a);
      return line && CUR ? f.replace(/<img [^>]*>/, m => `<span class="qpinwrap">${m}${P.notes.pins(notesAt(CUR, nk, true), S.pin, S.note === nk && !S.full && S.tgt)}</span>`) : f; };
    if (k === 'tbl') { const R = rowsOf(b), ra = ri => line && ri ? ` data-line="${esc(rk(ri))}" tabindex="0"` : '', cell = (ri, ci, c) => P.media.cell(b[4], ri, ci, c, esc, (p, j) => pic(p[1], p[2], p[3], '', P.media.pk(rk(ri), j)));
      // a row's pictures each keep their own notes, under the row's (Reference's rowPics)
      const rowPics = ri => Array.from({length: b[4] && b[4][ri] ? b[4][ri].flat().filter(p => p && p[0] === 'img').length : 0}, (_, j) => line(P.media.pk(rk(ri), j + 1))).join('');
      return `<div class="l-tw" style="--c:${Math.max(1, ...R.map(r => r.length))}"${a}><table>${R.map((r, ri) => `<tr${ra(ri)}>${r.map((c, ci) => ri ? `<td>${cell(ri, ci, c)}</td>` : `<th>${cell(ri, ci, c)}</th>`).join('')}</tr>`).join('')}</table></div>${after}${line ? R.map((_, ri) => ri ? line(rk(ri)) + rowPics(ri) : '').join('') : ''}`; }
    if (k === 'img') return pic(t, b[2], b[3], a).replace(/<\/figure>$/, `${tag}</figure>`) + after;
    return (k === 'h' ? `<h4${a}>${x}${tag}</h4>` : k === 'li' ? `<p class="l-li"${a}>• ${x}${tag}</p>` : k === 'pre' ? P.media.code(t, a) : `<p${a}>${x}${tag}</p>`) + after; };
  const blocksHtml = (bs, esc, line, ids) => bs.map((b, i) => blockHtml(b, i, esc, line, '', false, ids ? ids[i] : null)).join('');
  // a note's line key split into its document and line (data-doc, data-line): a kept page's line is its anchor; a file's its number
  const lineKey = k => /^(doc:kept-[^~]+~p)~([^~]+(?:~r\d+)?)$/.exec(k) || /^(.*?)~(\d+(?:~r\d+)?)$/.exec(k);
  // a kept document's block and row by a line's anchor: [block, row (0 for the whole block)], or null
  const atLine = (d, t) => { const I = d.ids;
    if (!I) { const m = /^(\d+)(?:~r(\d+))?$/.exec(t); return m ? [+m[1], +(m[2] || 0)] : null; }  // the load test's lines, by number
    for (let i = 0; i < I.length; i++) { const x = I[i], r = Array.isArray(x) ? x.indexOf(t) : -1; if (x === t || r === 0) return [i, 0]; if (r > 0) return [i, r]; }
    const m = /^(.+)~r(\d+)$/.exec(t), p = m && atLine(d, m[1]);
    return p ? [p[0], +m[2]] : null; };
  // an earlier revision's lines take only the notes whose anchor the newest lacks: the rest show on the newest
  const bare = k => String(k).replace(/~p\d+$/, '');  // a picture point's key, as its row's
  const oldLine = (R, line) => { const has = new Set(R[R.length - 1].ids.flat().map(String)); return i => has.has(bare(i)) ? '' : line(i); };
  // the revision a kept note opens on: the newest, or the newest earlier one with its anchor (null: the newest)
  const revOf = (d, a) => { const m = lineKey(bare(a)); if (!d.revs || !m || atLine(d, m[2])) return null;
    for (let j = d.revs.length - 2; j >= 0; j--) if (d.revs[j].ids && atLine({ids: d.revs[j].ids}, m[2])) return j;
    return null; };
  // paragraphs paired by their exact text (longest common run): the same, added, or removed where it stood
  // shortcut: no "changed" pairing or word-by-word marks as Reference has; share Reference's alignBlocks when the prototype graduates
  function align(A, B) {
    const n = A.length, m = B.length, L = Array.from({length: n + 1}, () => new Array(m + 1).fill(0)), out = [];
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = A[i][1] === B[j][1] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
    for (let i = 0, j = 0; i < n || j < m;) {
      if (i < n && j < m && A[i][1] === B[j][1]) { out.push({k: 'same', b: j++}); i++; }
      else if (j < m && (i >= n || L[i][j + 1] >= L[i + 1][j])) out.push({k: 'add', b: j++});
      else out.push({k: 'del', a: i++});
    }
    return out;
  }
  // a kept document with revisions (the admin meeting), as the mock's reader: a revision bar with Show marks, the text, the revision list beside it
  function revDoc(ctx, D, d, line) {
    const {esc} = ctx, R = d.revs, n = R.length, last = n - 1, cur = S.rv[d.id] != null ? S.rv[d.id] : last, B = R[cur].blocks;
    docK += '~rev' + (cur + 1);  // its pictures' keys name the revision, so each revision's picture keeps its own size (r12 audit18 reference 5)
    const al = n > 1 ? align(R[last - 1].blocks, R[last].blocks) : [], nk = k => al.filter(x => x.k === k).length, csum = n > 1 ? `${nk('add')} added · ${nk('del')} removed` : '';
    const tag = w => ` <span class="l-tag">${w} in revision ${n}</span>`, mk = S.marks && cur === last && n > 1;
    // an earlier revision reads as it was; notes go on the newest, and one whose words left it on its own revision, as 2.32.8
    const doc = cur !== last ? blocksHtml(B, esc, R[cur].ids && line ? oldLine(R, line) : null, R[cur].ids)
      : mk ? al.map(x => x.k === 'same' ? blockHtml(B[x.b], x.b, esc, line, '', false, d.ids ? d.ids[x.b] : null) : x.k === 'add' ? blockHtml(B[x.b], x.b, esc, line, tag('added'), true, d.ids ? d.ids[x.b] : null)
        : `<p class="small"><del>${esc(blockText(R[last - 1].blocks[x.a]))}</del>${tag('removed')}</p>`).join('')  // a picture or table by its words, not its address
      : blocksHtml(B, esc, line, d.ids);
    const bar = n > 1 ? `<div class="l-revbar"><b>Revision ${cur + 1} of ${n}</b>${cur === last ? `<span class="small">${mk ? `${csum}, against revision ${n - 1}: <del>struck</del> paragraphs left, <ins>marked</ins> ones came in` : 'marks hidden'}</span><button class="lk small" data-marks>${mk ? 'Hide marks' : 'Show marks'}</button>`
      : `<span class="small">an earlier revision, as it read</span><button class="lk small" data-rv="${esc(d.id)}~${last}">Back to the newest</button>`}</div>` : '';
    const list = n > 1 ? `<nav class="l-vlist" aria-label="Revisions"><h5>${pl(n, 'revision', 'revisions')}</h5>${R.map((r, i) => [r, i]).reverse().map(([r, i]) =>
      `<button class="l-vrow" data-rv="${esc(d.id)}~${i}" aria-current="${i === cur}"><b>Revision ${i + 1} · ${esc(dm(r.ts))}${i === last ? ' · newest' : ''}</b><span class="small mut">${i === last ? csum : ''}</span></button>`).join('')}</nav>` : '';
    return `${bar}<div class="l-r8v"><div class="l-rtext">${doc}</div>${list}</div>`;
  }
  const pl = (n, one, many) => `${Number(n).toLocaleString()} ${n === 1 ? one : many}`;
  const ROLE = {view: 'Can view', send: 'Can answer and send'}, ROLEIC = {view: 'eye', send: 'edit'};
  const ROLEHINT = {view: 'Reads the page, its questions, Reference and History', send: 'Also answers, writes notes and presses Send'};
  const MASK = 'member@example.com';

  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch {}
    const t = Object.assign(document.createElement('textarea'), {value: text});
    document.body.appendChild(t); t.select();
    let ok = false; try { ok = document.execCommand('copy'); } catch {}
    t.remove();
    return ok;
  }
  const abs = u => new URL(u, location.href).href;

  async function render(el, ctx, anchor) {
    P.notes.slot(S, 'links');  // S.move is the kit's one Move; navigating here ended any earlier one (r12 audit17 reference 4, fix20)
    let D = LD = await ctx.data('links');
    el.innerHTML = '<div class="l-wrap"></div>';
    const w = el.firstElementChild;
    if (anchor === 'people') return people(w, ctx, D);
    // every return to the tab reads its list again behind what is on screen, so a link added since shows without a reload;
    // no throttle: the server answers from its cache (audit10 running 5, audit11 running 4)
    ctx.data('links', true).then(F => { if (!w.isConnected || JSON.stringify(F) === JSON.stringify(D)) return;
      D = LD = F; if (ON && ON.w === w) ON.D = F;
      if (!w.contains(document.activeElement) || !document.activeElement.matches('input, textarea')) draw(w, ctx, D); }).catch(() => {});
    const ka = /^kept-(.+)/.exec(decodeURIComponent(anchor || ''));  // a copied kept-document link opens that document
    if (ka && (D.kept || []).some(d => d.id === ka[1])) S.kept = ka[1];
    const dr = typed(ctx);  // the note he was typing before a reload reopens on its line, words and all (audit8 running 1)
    const back = dr && (!ka || dr.a.startsWith(`doc:kept-${ka[1]}~`) || dr.a === `doc:kept-${ka[1]}`) && (!S.note || S.note === dr.a);
    if (back) { openAt(D, dr.a); S.note = dr.a; S.tgt = dr.tgt || null; S.hl = ''; }
    draw(w, ctx, D); ON = {w, ctx, D};
    if (back) { const t = w.querySelector('#l-nt'); if (t) { t.scrollIntoView({block: 'center'}); t.focus({preventScroll: true}); } }
    else if (ka) { const t = w.querySelector(`[data-kept="${CSS.escape(ka[1])}"]`); if (t) t.scrollIntoView({block: 'start'}); }
    w.onclick = e => click(e, w, ctx, D);
    w.oninput = e => { if (e.target.matches('[data-nedtext]')) S.edt = e.target.value;  // an edit survives a redraw
      if (e.target.id !== 'l-nt' || !S.note) return;
      const was = !!typed(ctx);
      ctx.prefs.set('draft:lnote', {a: S.note, tgt: S.tgt, text: e.target.value, ...place(w, D, S.note, e.target)});
      if (was !== !!typed(ctx)) ctx.refreshTop(); };
    // ⌘↵ in the note saves it, as the mock and the shortcut help say; it never reaches the frame's Send (audit8 frame 3)
    w.onkeydown = e => { if (e.target.id === 'l-nt' && (e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault(); e.stopPropagation(); const b = w.querySelector('[data-nsave]'); if (b) b.click(); }
      else if (e.key === 'Escape' && (S.move || S.edit)) { S.move = S.edit = ''; S.edt = null; draw(w, ctx, D); } };
  }

  function draw(w, ctx, D) {
    const {esc, icon} = ctx;
    CUR = D;
    const copyBtn = (key, name) => `<button class="ib" data-copylink="${esc(key)}" data-name="${esc(name)}" title="Copy link to ${esc(name)}" aria-label="Copy link to ${esc(name)}">${icon(S.copied === key ? 'copied' : 'link')}</button>`;
    const pageRow = (name, sub, key, open) => `<div class="l-line">${icon('doc')}<span class="l-grow">${open}<span class="small mut l-sub">${sub}</span></span>${copyBtn(key, name)}</div>`;
    // each page says why it is its own page, so he can choose between them (#81); counts follow
    const me = pageRow(D.name, `the review page you answer on today; its rounds are the versions in History · this prototype copy, ${pl(D.versions, 'version', 'versions')}`, ctx.base,
      `<button class="lk" data-goq>${esc(D.name)}</button>`);
    const others = D.pages.map(p => pageRow(p.name, `${esc(p.why || 'its own page')}${p.versions != null ? ` · ${pl(p.versions, 'version', 'versions')}` : ''}${p.last ? ` · last ${esc(dm(p.last))}` : ''}`, p.ref ? `#reference/${encodeURIComponent(p.ref)}` : p.url,
      p.ref ? `<button class="lk" data-goref="${esc(p.ref)}">${esc(p.name)}</button>` : `<a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.name)} ${icon('ext')}</a>`)).join('');
    const ppl = 1 + ctx.prefs.get('people', []).length;
    const arch = S.arch ? D.archived.map(a => a.url ? `<div class="l-line l-subrow">${icon('archive')}<span class="l-grow"><a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.t)} ${icon('ext')}</a>
        <span class="small mut l-sub">${esc(a.why)}${a.when ? ` · last ${esc(dm(a.when))}` : ''}</span></span>${copyBtn(a.url, a.t)}</div>` : `<div class="l-line l-subrow">${icon('archive')}<span class="l-grow"><button class="lk l-left" data-arch="${esc(a.id)}" aria-expanded="${S.view === a.id}">${esc(a.t)}</button>
        <span class="small mut l-sub">${esc(a.when)} · read-only, takes no answers</span></span>${copyBtn(`plans/${a.id}/${a.v}.html`, a.t)}</div>${S.view === a.id ? '<div class="l-view" data-view></div>' : ''}`).join('') : '';
    w.innerHTML = `<div class="l-cols"><section><h2 class="l-ph">${icon('pages')} Pages of this project <span class="badge grey">${1 + D.pages.length}</span></h2>${me}${others}
        <div class="l-line">${icon('people')}<span class="l-grow"><button class="lk" data-people>People</button><span class="small mut l-sub">who can open this page · ${pl(ppl, 'person', 'people')}</span></span>${icon('chev')}</div>
        <div class="l-grp"><button class="l-fold" data-archall aria-expanded="${S.arch}">${icon('chev')}<b>Archived pages</b> <span class="small mut">${D.archived.length ? D.archived.some(a => a.url) ? pl(D.archived.length, 'page', 'pages') : pl(D.archived.length, 'snapshot', 'snapshots') : 'none'}</span></button>${arch}</div>
        <div class="l-line">${icon('warn')}<span class="l-grow"><button class="lk l-left" data-bad aria-expanded="${S.view === 'bad'}">${esc(badTitle(D))}</button><span class="small mut l-sub"><span class="l-errt">could not load</span> · an example, to try Retry and Tell the agent</span></span></div>
        ${S.view === 'bad' ? '<div class="l-view" data-view></div>' : ''}</section>
      <section><h2 class="l-ph">${icon('code')} Repos, folders and links</h2>
        ${D.folders.map(f => `<div class="l-line">${icon('code')}<span class="l-grow">${esc(f.name)}<span class="small mut l-sub">${esc(f.what)}</span></span><button class="btn sm" data-copypath="${esc(f.path)}" title="Copy ${esc(f.path)}">${icon(S.copied === f.path ? 'copied' : 'copy')} Copy path</button></div>`).join('')}
        ${D.links.map(l => l.url ? `<div class="l-line">${icon(l.ic || 'bead')}<span class="l-grow"><a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.name)} ${icon('ext')}</a><span class="small mut l-sub">${esc(l.what)}</span></span>${copyBtn(l.url, l.name)}</div>`
          : `<div class="l-line">${icon('ext')}<span class="l-grow">${esc(l.name)}<span class="small mut l-sub">${esc(l.what)}</span></span></div>`).join('')}
        ${D.folders.length || D.links.length ? '' : '<p class="small mut">Repos, folders and links: none recorded for this project yet.</p>'}</section>
      ${docsHtml(ctx, D, copyBtn)}</div>`;
    const host = w.querySelector('[data-view]');
    if (host) {
      const a = D.archived.find(x => x.id === S.view);
      const close = () => { S.view = ''; draw(w, ctx, D); };
      P.viewVersion(host, ctx, a ? {title: a.t, src: `plans/${encodeURIComponent(a.id)}/${encodeURIComponent(a.v)}.html`, onClose: close}
        : {title: badTitle(D), src: 'content?v=v0', onClose: close, failTitle: `The publish of ${badWhen(D)} could not load.`});
    }
    const q = w.querySelector('#l-dq');
    if (q) {
      let t;
      q.oninput = () => { clearTimeout(t); t = setTimeout(() => { S.dq = q.value.trim(); S.dsel = -1; draw(w, ctx, D); const n = w.querySelector('#l-dq'); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }, 150); };
    }
    if (S.scroll) { S.scroll = false; const h = w.querySelector('.l-hl'); if (h) h.scrollIntoView({block: 'center'}); }
    // View resolution on this tab: its destination line or bar, outlined by the kit and scrolled to (r12 audit16 frame 2)
    const m = S.res && lineKey(S.res), rs = m && (w.querySelector(`[data-doc="${CSS.escape(m[1])}"] [data-line="${CSS.escape(m[2])}"]`) || w.querySelector(`[data-bnote="${CSS.escape(S.res)}"]`));
    if (rs) { P.notes.lit(rs); if (S.resGo) { S.resGo = false; rs.scrollIntoView({block: 'center'}); } }
    if (S.full) P.media.redrawView();  // the open picture viewer shows the same notes
  }
  // the failed publish is named by its date, as in the mock (#87); it is an example: no publish of this page failed
  const badWhen = D => { const [d, t] = String(D.current_t || '').split(' '); return d ? `${dm(d)}${t ? ', ' + t : ''}` : 'today'; };
  const badTitle = D => `${D.name}, the publish of ${badWhen(D).split(',')[0]}`;

  /* ---------- Documents (#16): kept on this page, then every file in the project's folder ---------- */
  // `old`: a picture's notes also take the point notes saved on its row before pictures had keys (Proto.media.was)
  const notesAt = (D, k, old) => { const o = old && P.media.was(k);
    return [...D.notes, ...mine.filter(n => !D.notes.some(x => x.id === n.id))].filter(n => n.a === k || (o && n.a === o && n.target && n.target.offset)); };
  const onWords = (esc, t, no) => t && t.quote ? ` on “${esc(t.quote.length > 60 ? t.quote.slice(0, 58).trimEnd() + '…' : t.quote)}”` : t && t.offset ? ` at spot ${no || '+'} on the picture` : '';
  const viewing = k => !!S.full && S.full.k === k;  // this picture is open Full size: its viewer holds its composer
  // `dlg`: drawn in the picture viewer
  function noteBox(ctx, D, k, dlg) {
    const {esc, icon} = ctx, ns = notesAt(D, k, dlg), dr = ctx.prefs.get('draft:lnote', null), words = dr && dr.a === k ? dr.text || '' : '', box = S.note === k && viewing(k) === !!dlg;
    if (!ns.length && !box) return '';
    // a sent note carries the lifecycle Questions and Reference use (P.notes: Re-open, View resolution, Move, Close); a closed one folds (r12 fix17)
    // the edit box only where he sees it: in the viewer while this picture is open there (r12 audit19 reference 5)
    const ed = n => S.edit === n.id && viewing(k) === !!dlg;
    const K = P.notes, cls = n => `l-nt${S.hl === n.id ? ' l-hl' : ''}${S.move === n.id ? ' moving' : ''}`;
    const spotNo = n => ns.filter(x => x.target && x.target.offset && !x.closed).indexOf(n) + 1;
    // its marker lists every note on the spot, with Go to it and + Comment (the kit's spot list, as Questions and Reference; r12 audit16 frame 5)
    // its colour: the kit's one rule, purple while one goes with Send (catalog 24)
    const pin = ns.length ? `<button class="qmk qmkb${K.sent(ns) ? ' sent' : ''}" data-spot="${esc(k)}" aria-expanded="${S.spot === k && !S.pin}" title="${pl(ns.length, 'note', 'notes')} here: list them" aria-label="${pl(ns.length, 'note', 'notes')} here: list them">${icon('note')}${ns.length}</button>` : '';
    const p = S.pin && ns.find(n => n.id === S.pin), sl = p ? K.near(ns, p) : ns;  // a point marker lists the notes at its point
    const list = S.spot === k && viewing(k) === !!dlg && ns.length ? K.spot(ctx, sl.map(n => [n, spotNo(n) || ns.indexOf(n) + 1]), p ? 'at this point' : 'on this spot', `data-spotadd="${esc(k)}"${p ? ` data-spotpin="${esc(p.id)}"` : ''}`) : '';
    // a saved, unsent one: the kit's Edit in place and Remove (r12 audit18 reference 4)
    return `<div class="l-notes">${pin}${list}${ns.map(n => n.closed ? `<div class="${cls(n)}" data-nid="${esc(n.id)}">${icon('archive')} Note closed <span class="mut">${esc(n.text)}</span> ${K.closedActs(n)}</div>`
      : `<div class="${cls(n)}" data-nid="${esc(n.id)}">${icon('note')}<b>${esc(n.who)}</b> <span class="small mut">${esc(dm(n.at))}${onWords(esc, n.target, spotNo(n))}</span> ${n.sent ? K.sentBody(ctx, n, S.move === n.id, ed(n) ? (S.edt != null ? S.edt : n.text) : null)
        : ed(n) ? K.editBox({...n, text: S.edt != null ? S.edt : n.text}) : `${esc(n.text)} <span class="saved">· goes with Send</span><span class="nacts">${K.draftActs(n, S.move === n.id)}</span>`}</div>`).join('')}
      ${box ? `<div class="l-nbox">${S.tgt ? `<div class="small mut">New note${onWords(esc, S.tgt)}</div>` : ''}<textarea id="l-nt" rows="3" placeholder="Write a note for the agent about this" aria-label="Your note">${esc(words)}</textarea>
        <div class="l-nacts"><button class="btn sm pri" data-nsave="${esc(k)}">Save note</button><button class="btn sm" data-ncancel data-going="lnn:${esc(k)}">Cancel</button><span class="small mut">goes with your next Send · <kbd>⌘↵</kbd> saves</span></div></div>` : ''}</div>`;
  }
  function chartHtml(ctx, D, d) {
    const {esc} = ctx, c = d.chart, max = Math.max(c.gate || 0, ...c.pts.map(p => p[1])) || 1;
    // the mock's barChart: one column per measure in one row, the gate a horizontal dashed line labelled at its end (audit9 reference 3)
    const g = c.gate ? `<s style="bottom:${(c.gate / max * 100).toFixed(1)}%" aria-hidden="true"></s>` : '';
    return `<figure class="l-chart"><figcaption class="small"><b>${esc(c.t)}</b> <span class="mut">· ${c.pts.length} measures · click a bar to write a note on it</span></figcaption>
      <div class="l-bars" role="list" style="--n:${c.pts.length}">${c.pts.map(([lab, v], i) => { const k = `doc:kept-${d.id}~${i}`, n = notesAt(D, k).length;
        return `<button class="l-bar${n || S.note === k ? ' on' : ''}" role="listitem" data-bnote="${esc(k)}" aria-pressed="${S.note === k}" title="${esc(lab)}: ${v.toLocaleString()} ms${c.gate && v > c.gate ? `, over the ${c.gate.toLocaleString()} ms limit` : ''}. Click to write a note on it"><span class="l-bt"><i style="height:${(v / max * 100).toFixed(1)}%"><span class="l-bv">${v.toLocaleString()} ms${n ? ` ${ctx.icon('note')}${n}` : ''}</span></i>${g}</span><span class="l-bl">${esc(lab)}</span></button>`; }).join('')}${c.gate ? `<span class="l-glab" aria-hidden="true"><span class="l-bt"><b style="bottom:${(c.gate / max * 100).toFixed(1)}%">limit ${c.gate.toLocaleString()} ms</b></span></span>` : ''}</div>
      <p class="small mut">${esc(c.axis)}</p></figure>
      ${c.pts.map((_, i) => noteBox(ctx, D, `doc:kept-${d.id}~${i}`)).join('')}`;
  }
  // Approve beside Write a note, as in the mock; it goes with the one Send under Reference (r12 fix8, reference 3)
  const apprs = ctx => ctx.prefs.get('draft:lappr', []);
  const apprBtn = (ctx, id) => { const on = apprs(ctx).includes(id);
    return `<button class="btn sm${on ? ' rec' : ''}" data-kappr="${ctx.esc(id)}" aria-pressed="${on}">${on ? '✓ Approved · Undo' : 'Approve'}</button>`; };
  const keptBody = (ctx, D, d) => { const line = i => noteBox(ctx, D, `doc:kept-${d.id}~p~${i}`); docK = `doc:kept-${d.id}~p`;
    return d.revs ? revDoc(ctx, D, d, line) : blocksHtml(d.blocks || [], ctx.esc, line, d.ids); };
  function docsHtml(ctx, D, copyBtn) {
    const {esc, icon} = ctx, kept = D.kept || [], F = ((D.docs || {}).files || []).map((f, i) => ({...f, i})), groups = (D.docs || {}).groups || {};
    const keptRows = kept.map(d => `<div class="l-line"><span class="l-grow"><button class="lk l-left" data-kept="${esc(d.id)}" aria-expanded="${S.kept === d.id}">${icon('doc')} ${esc(d.t)}</button><span class="small mut l-sub">${esc(d.sub)}</span></span>${copyBtn(`#links/kept-${encodeURIComponent(d.id)}`, d.t)}</div>
      ${S.kept === d.id ? `<div class="l-doc" data-doc="doc:kept-${esc(d.id)}~p" data-docname="${esc(d.t)}"><div class="l-dbar"><b>${esc(d.t)}</b><span class="small mut">read-only · select words to write a note on them</span><span class="spacer"></span><button class="btn sm" data-kept="${esc(d.id)}">${icon('x')} Close</button></div>
        ${d.chart ? chartHtml(ctx, D, d) : ''}${keptBody(ctx, D, d)}${noteBox(ctx, D, `doc:kept-${d.id}`)}
        <div class="l-nacts"><button class="btn sm" data-bnote="doc:kept-${esc(d.id)}">${icon('note')} Write a note</button>${apprBtn(ctx, d.id)}<span class="small mut">Click any line to write a note on it</span></div></div>` : ''}`).join('');
    const q = S.dq.toLowerCase(), hit = f => !q || `${f.n} ${f.sub} ${groups[f.g] || ''}`.toLowerCase().includes(q);
    const sh = F.filter(f => hit(f) && (!S.dk || f.k === S.dk)), kinds = Object.keys(DK).filter(k => F.some(f => f.k === k));
    const gs = Object.keys(groups).filter(g => sh.some(f => f.g === g)).sort((a, b) => (a === '' ? -1 : b === '' ? 1 : 0) || sh.filter(f => f.g === b).length - sh.filter(f => f.g === a).length);
    const dic = k => `<span class="l-dk k-${k}" title="${DK[k][1]}">${icon(DK[k][0])}</span>`;
    const row = f => `<div class="l-d9"${S.dsel === f.i ? ' aria-current="true"' : ''}>${dic(f.k)}<button class="lk l-nm" data-dopen="${f.i}" ${f.md ? `aria-expanded="${S.dsel === f.i}" title="Open it here"` : 'title="Opens in a new tab"'}>${esc(f.n)}${f.md ? '' : ' ↗'}${f.sub ? `<span class="small mut l-dsub">${esc(f.sub)}</span>` : ''}</button><span class="small mut l-sz">${kb(f.kb)}</span><span class="small mut l-dt">${esc(dm(f.d))}</span><button class="ib" data-copypath="${esc(fpath(f))}" title="Copy its path" aria-label="Copy the path of ${esc(f.n)}">${icon(S.copied === fpath(f) ? 'copied' : 'copy')}</button></div>
      ${S.dsel === f.i && f.md ? mdView(ctx, D, f, dic, groups) : ''}`;
    const list = gs.map(g => { const l = sh.filter(f => f.g === g), key = 'dg:' + g, op = !!q || S.open.has(key) || (S.dsel >= 0 && F[S.dsel] && F[S.dsel].g === g && sh.includes(F[S.dsel])), all = S.open.has('dga:' + g);
      return `<div class="l-grp"><button class="l-fold" data-fold="${esc(key)}" aria-expanded="${op}">${icon('chev')}<b>${esc(groups[g])}</b> <span class="small mut">${pl(l.length, 'file', 'files')}</span></button>
        ${op ? l.slice(0, all ? l.length : 8).map(row).join('') + (l.length > 8 ? `<button class="lk small l-more" data-fold="dga:${esc(g)}">${all ? 'Show the first 8' : `Show all ${l.length}`}</button>` : '') : ''}</div>`; }).join('') || '<p class="mut">No document matches.</p>';
    return `<section class="l-docs" id="docs"><h2 class="l-ph">${icon('doc')} Documents</h2>
      <div class="l-kept"><div class="l-kh"><b>Kept on this page</b> <span class="badge grey">${kept.length}</span></div>${keptRows || '<p class="small mut">None yet</p>'}</div>
      <h3 class="l-ph3">Files in this project's folder</h3>
      ${F.length ? `<div class="l-dbar2"><input type="search" id="l-dq" placeholder="Find a document by name or folder" aria-label="Find a document" value="${esc(S.dq)}">
        <span class="l-chips" role="group" aria-label="Kind"><button class="chipb" data-dk="" aria-pressed="${!S.dk}">All <span class="n">${F.filter(hit).length}</span></button>${kinds.map(k => `<button class="chipb" data-dk="${k}" aria-pressed="${S.dk === k}" title="Only ${DK[k][1]} files">${dic(k)}${DK[k][1]} <span class="n">${F.filter(f => hit(f) && f.k === k).length}</span></button>`).join('')}</span></div>
      <p class="small mut">${pl(F.length, 'file', 'files')} in this project's folder · Markdown opens here, other kinds in a new tab</p>${list}`
        : '<p class="small mut">None recorded for this project yet.</p>'}</section>`;
  }
  // a Markdown file opened under its row, as in the mock (docMd): every block takes a note, selected words too, and the whole file one
  const docKey = f => 'doc:' + [f.g, f.sub, f.n].filter(Boolean).join('/');  // the same key Reference uses, so notes show in both
  function mdView(ctx, D, f, dic, groups) {
    const {esc, icon} = ctx, k = docKey(f);
    docK = k;
    return `<div class="l-doc" data-doc="${esc(k)}" data-docname="${esc(f.n)}"><div class="l-dbar">${dic('md')}<b>${esc(f.n)}</b><span class="small mut">${esc(groups[f.g] || '')}${f.sub ? ' / ' + esc(f.sub) : ''} · ${kb(f.kb)} · changed ${esc(dm(f.d))} · select words to write a note on them</span><span class="spacer"></span><button class="btn sm" data-dopen="${f.i}">${icon('x')} Close</button></div>
      ${blocksHtml(mdBlocks(f.md), esc, i => noteBox(ctx, D, `${k}~${i}`))}${noteBox(ctx, D, `${k}~all`)}
      <div class="l-nacts"><button class="btn sm" data-bnote="${esc(k)}~all">${icon('note')} Write a note</button><span class="small mut">Click any line to write a note on it</span></div></div>`;
  }

  async function click(e, w, ctx, D) {
    const zb = e.target.closest('.l-doc [data-lzoom]');  // a picture's size or ⤢ Full size: the shared viewer, not a new tab
    if (zb) { e.preventDefault(); const im = zb.closest('figure').querySelector('img'), k = zb.dataset.pk, z = +(zb.dataset.zoom || P.media.zoom(k));
      let from = zb;
      if (S.move) { const all = [...w.querySelectorAll('.l-doc [data-lzoom]')], i = all.indexOf(zb); S.move = ''; draw(w, ctx, D); from = w.querySelectorAll('.l-doc [data-lzoom]')[i] || null; }  // the viewer ends a Move, as in Reference (r12 audit17 reference 4)
      // the viewer takes and shows this picture's point notes through the notes kit, as Reference's does (r12 audit18 reference 3)
      // an earlier revision reads as it was and takes no notes, as inline
      if (!zb.closest('figure').closest('[data-line]')) return P.media.view(im.getAttribute('src'), im.dataset.zcap, z, from, k);
      const nk = zb.dataset.nk || k;  // its notes by the place; the viewer's size by the revision's key (k)
      if (S.note === nk) { S.note = ''; S.tgt = null; }
      S.full = {k: nk, name: (zb.closest('[data-docname]') || {dataset: {}}).dataset.docname || ''}; S.spot = S.pin = '';
      return P.media.view(im.getAttribute('src'), im.dataset.zcap, z, from, k, {
        pins: () => P.notes.pins(notesAt(D, nk, true), S.pin, viewing(nk) && S.note === nk && S.tgt),
        list: () => noteBox(ctx, D, nk, true),
        // Move armed in the viewer: the tap is its new point on this picture, the kit's re-pin (r12 audit19 running 2, reference 2)
        tap: tgt => { if (S.move) return moveTo(w, ctx, D, nk, document.querySelector('#p-mview .pic img'), tgt);
          S.tgt = tgt; S.note = nk; S.spot = S.pin = ''; draw(w, ctx, D); },
        click: ev => click(ev, w, ctx, D), input: ev => w.oninput(ev),
        close: () => { S.full = null; if (S.note === nk) { S.note = ''; S.tgt = null; } S.spot = S.pin = ''; draw(w, ctx, D); }}); }
    const b = e.target.closest('button');
    // a tap on a picture inline: a point note on that picture, by its own key, as in Reference
    const im = !b && e.target.closest('.l-doc figure img'), pk = im && ((im.closest('figure').querySelector('[data-nk]') || {}).dataset || {}).nk;
    if (pk && (im.closest('[data-line]'))) { const tgt = P.notes.at(e, im);
      if (S.move) return moveTo(w, ctx, D, pk, im, tgt);
      S.tgt = tgt; S.spot = S.pin = ''; S.note = pk; draw(w, ctx, D);
      const t = w.querySelector('#l-nt'); if (t) t.focus(); return; }
    const ln = !b &&!e.target.closest('textarea, .l-notes') && e.target.closest('.l-doc [data-line]');
    if (ln) {  // a line of an open Markdown file takes a note; words selected in it become the note's target
      const sel = getSelection(), q = sel && !sel.isCollapsed ? String(sel).trim() : '';
      const tgt = q && ln.contains(sel.anchorNode) ? {schema: 1, tag: ln.tagName.toLowerCase(), quote: q.slice(0, 300)} : null, k = ln.closest('[data-doc]').dataset.doc + '~' + ln.dataset.line;
      if (S.move) return moveTo(w, ctx, D, k, ln, tgt);  // Move: this line is its new place, as in Reference (r12 audit16 frame 3)
      S.tgt = tgt; S.spot = '';
      S.note = k; draw(w, ctx, D);
      const t = w.querySelector('#l-nt'); if (t) t.focus();
      return;
    }
    if (!b) return;
    if (b.hasAttribute('data-codecopy')) return P.media.onCopy(b);  // the code Copy every document reader shares
    if (b.dataset.copylink || b.dataset.copypath) {
      const key = b.dataset.copylink || b.dataset.copypath, path = !!b.dataset.copypath;
      const ok = await copyText(path ? key : abs(key));
      if (!ok) return ctx.toast('Copy failed: your browser blocked the clipboard');
      S.copied = key; draw(w, ctx, D);
      ctx.toast(path ? `Path copied: ${key}` : `Link to ${b.dataset.name} copied`);
      setTimeout(() => { if (S.copied === key) { S.copied = ''; draw(w, ctx, D); } }, 2000);
    } else if (b.hasAttribute('data-archall')) { S.arch = !S.arch; draw(w, ctx, D); }
    else if (b.dataset.arch) { S.view = S.view === b.dataset.arch ? '' : b.dataset.arch; draw(w, ctx, D); }
    else if (b.hasAttribute('data-bad')) { S.view = S.view === 'bad' ? '' : 'bad'; draw(w, ctx, D); }
    else if (b.hasAttribute('data-people')) ctx.go('links', 'people');
    else if (b.hasAttribute('data-goq')) ctx.go('questions');
    else if (b.dataset.kappr) { const id = b.dataset.kappr, a = apprs(ctx); if (a.includes(id) && P.going('lappr:' + id)) return;  // carried by the round past its check (r12 fix38)
      ctx.prefs.set('draft:lappr', a.includes(id) ? a.filter(x => x !== id) : [...a, id]); draw(w, ctx, D); ctx.refreshTop(); }
    else if (b.dataset.kept) { S.kept = S.kept === b.dataset.kept ? '' : b.dataset.kept; S.note = ''; draw(w, ctx, D); }
    else if (b.dataset.rv) { const [id, i] = b.dataset.rv.split('~'); S.rv[id] = +i; draw(w, ctx, D); }
    else if (b.hasAttribute('data-marks')) { S.marks = !S.marks; draw(w, ctx, D); }
    else if (b.dataset.dk !== undefined) { S.dk = b.dataset.dk; draw(w, ctx, D); }
    else if (b.dataset.fold) { S.open.has(b.dataset.fold) ? S.open.delete(b.dataset.fold) : S.open.add(b.dataset.fold); draw(w, ctx, D); }
    else if (b.dataset.dopen) {
      const i = +b.dataset.dopen, f = D.docs.files[i];
      // as in the mock: other kinds open in a new tab; the prototype stays inert, so it only says so
      if (!f.md) return ctx.toast(`Opens “${f.n}” in a new tab${f.k === 'pdf' ? '; PDFs open in place later' : ''}`, {inert: true});
      S.dsel = S.dsel === i ? -1 : i; draw(w, ctx, D);
    } else if (b.hasAttribute('data-goref')) ctx.go('reference', b.dataset.goref);
    else if (b.dataset.nclose || b.dataset.nopen || b.dataset.nreopen || b.dataset.nres) {
      const id = b.dataset.nclose || b.dataset.nopen || b.dataset.nreopen || b.dataset.nres, n = D.notes.concat(mine).find(x => x.id === id);
      if (!n) return;
      if (b.dataset.nres) return P.notes.goRes(ctx, n);
      P.notes.set(ctx, n, b.dataset.nclose ? 'close' : b.dataset.nopen ? 'restore' : 'reopen', ctx.api, async nid => { S.hl = nid; draw(w, ctx, D); ctx.refreshChips(); });
    } else if (b.dataset.nmove) { S.move = S.move === b.dataset.nmove ? '' : b.dataset.nmove; draw(w, ctx, D); if (S.move) ctx.toast('Click the bar or line for this note · Esc cancels'); }
    else if (b.dataset.bnote && S.move) moveTo(w, ctx, D, b.dataset.bnote, b, null);  // Move: the next bar or Write a note it is pressed on takes the note
    // a marker's list: the kit's spot list, as Questions and Reference (r12 audit16 frame 5)
    else if (b.dataset.spot !== undefined) { S.pin = ''; S.spot = S.spot === b.dataset.spot ? '' : b.dataset.spot; draw(w, ctx, D); }
    else if (b.dataset.pin) { const n = D.notes.concat(mine).find(x => x.id === b.dataset.pin); if (!n) return; const on = S.pin === n.id;
      S.pin = on ? '' : n.id; S.spot = on ? '' : S.full ? S.full.k : (b.closest('figure').querySelector('[data-nk]') || {dataset: {}}).dataset.nk || n.a; draw(w, ctx, D); }
    else if (b.hasAttribute('data-spotx')) { S.spot = S.pin = ''; draw(w, ctx, D); }
    else if (b.dataset.spotadd) { const p = b.dataset.spotpin && D.notes.concat(mine).find(x => x.id === b.dataset.spotpin);
      S.spot = S.pin = ''; S.tgt = p ? {...p.target} : null; S.note = b.dataset.spotadd; draw(w, ctx, D); const t = document.getElementById('l-nt'); if (t) t.focus(); }
    else if (b.dataset.spotgo) { S.spot = S.pin = ''; S.hl = b.dataset.spotgo; S.scroll = true; if (S.full) P.media.closeView(); else draw(w, ctx, D); }
    // a saved, unsent note: the kit's Edit in place and Remove (r12 audit18 reference 4)
    else if (b.dataset.nedit) { S.edit = b.dataset.nedit; S.edt = null; draw(w, ctx, D); const t = document.querySelector('[data-nedtext]'); if (t) { t.focus(); t.setSelectionRange(t.value.length, t.value.length); } }
    else if (b.hasAttribute('data-nedcancel')) { S.edit = ''; S.edt = null; draw(w, ctx, D); }
    else if (b.dataset.nedsave) { const n = D.notes.concat(mine).find(x => x.id === b.dataset.nedsave), t = b.closest('[data-nedbox]').querySelector('textarea'); if (!n) return;
      P.notes.fix(ctx, n, t.value, ctx.api, (x, p) => { D.notes.concat(mine, (LD || {}).notes || []).forEach(y => { if (y.id === n.id) Object.assign(y, p); }); S.edit = ''; S.edt = null; S.hl = n.id; draw(w, ctx, D); ctx.refreshTop(); }); }
    // a bar with notes lists them first; + Comment writes another (a blank editor only on a bar with none)
    else if (b.dataset.bnote && b.classList.contains('l-bar') && notesAt(D, b.dataset.bnote).length && S.note !== b.dataset.bnote) { S.note = ''; S.spot = S.spot === b.dataset.bnote ? '' : b.dataset.bnote; draw(w, ctx, D); }
    else if (b.dataset.bnote) { S.tgt = null; S.spot = ''; S.note = S.note === b.dataset.bnote ? '' : b.dataset.bnote; draw(w, ctx, D); const t = w.querySelector('#l-nt'); if (t) t.focus(); }
    else if (b.hasAttribute('data-ncancel')) { S.note = ''; S.tgt = null; ctx.prefs.set('draft:lnote', null); draw(w, ctx, D); }
    else if (b.dataset.nsave) {
      const k = b.dataset.nsave, text = (document.getElementById('l-nt').value || '').trim(), target = S.tgt || undefined;
      if (!text) return ctx.toast('Write something first');
      try {
        const {l, line} = place(w, D, k, b);
        // while its Save is out the typed row has no Remove: the note is being stored, and Remove would hide it until it lands (r12 audit33 reference 1)
        SAVING = true; ctx.refreshTop();
        const c = await ctx.api('api/comments', {anchor_id: k, anchor_label: l, text, target}).finally(() => { SAVING = false; });
        mine.push({id: c.id, a: k, l, line, text: c.text || text, who: c.author_name || 'You', at: c.created_at || new Date().toISOString(), target});
        S.note = ''; S.tgt = null; ctx.prefs.set('draft:lnote', null); draw(w, ctx, D); ctx.refreshChips();
        ctx.toast('Note saved', {undo: () => undoNote(c.id, w, ctx, D)});
      } catch (er) { ctx.toast(`The note was not saved: ${er.message}`); }
    } else if (b.dataset.nundo) undoNote(b.dataset.nundo, w, ctx, D);
  }
  // Move to a bar, a Write a note or a line: the kit's re-pin, with Undo
  function moveTo(w, ctx, D, k, el, target) {
    const n = D.notes.concat(mine).find(x => x.id === S.move); S.move = '';
    if (!n || (n.a === k && !target)) return draw(w, ctx, D);
    const {l} = place(w, D, k, el);
    return P.notes.move(ctx, n.id, {anchor_id: n.a, anchor_label: n.l, target: n.target || null}, {anchor_id: k, anchor_label: l, target}, ctx.api,
      p => { if (p) Object.assign(n, {a: p.anchor_id, l: p.anchor_label, target: p.target, line: ''}); S.hl = p ? n.id : ''; draw(w, ctx, D); });
  }
  // where a note sits: its label (the document, or its chart bar) and the line it is on, so Send names it by its line (r12 fix8, running 3)
  function place(w, D, k, el) {
    const d = (D.kept || []).find(x => k.startsWith(`doc:kept-${x.id}`)), i = k.split('~')[1], file = el.closest('[data-docname]');
    const bar = d && d.chart && /^\d+$/.test(i || '') ? ', ' + d.chart.pts[+i][0] : '';  // ~<n> is a chart bar; ~p~<n> a line of text
    const m = lineKey(k), le = m && w.querySelector(`[data-doc="${CSS.escape(m[1])}"] [data-line="${CSS.escape(m[2])}"]`);
    return {l: d ? `${d.t}${bar}` : file ? file.dataset.docname : S.full && S.full.name ? S.full.name : 'Pages & links', line: le ? (le.cells ? [...le.cells].map(c => c.textContent).join(' ') : le.textContent).trim().replace(/\s+/g, ' ') : ''};
  }
  // Remove, as Send's Remove: the stored record stays until Undo is gone, so Undo puts back the very note
  function undoNote(id, w, ctx, D) {
    const n = D.notes.concat(mine).find(x => x.id === id); if (!n) return;
    let undo; try { undo = takeNote(ctx, n); } catch (e) { if (P.carried(e)) return; throw e; }  // past the round check: refused, and said so
    if (S.edit === id) S.edit = '';
    ctx.toast('Note removed', {undo}); ctx.refreshTop();
  }

  /* ---------- People: two roles; edits change only this copy, kept in this browser ---------- */
  function people(w, ctx, D) {
    const {esc, icon} = ctx;
    let list = ctx.prefs.get('people', []), role = 'view', err = '';
    const save = l => { list = l; ctx.prefs.set('people', l); ctx.refreshChips(); draw(); };
    const owners = D.people.length ? D.people : [{name: 'You', email: MASK, role: 'owner', seen: ''}];
    const seg = (cur, attr, label) => `<span class="l-seg" role="group" aria-label="${esc(label)}">${['view', 'send'].map(r => `<button type="button" ${attr}="${r}" aria-pressed="${cur === r}" title="${esc(ROLEHINT[r])}">${icon(ROLEIC[r])}${ROLE[r]}</button>`).join('')}</span>`;
    function draw() {
      w.innerHTML = `<div class="l-people"><button class="lk small l-back" data-back>${icon('chev')} Pages &amp; links</button>
        <h2 class="l-ph">${icon('people')} People on ${esc(D.name)} <span class="badge grey">${owners.length + list.length}</span></h2>
        <p class="small mut">Only you, the owner, add or remove people and change what they can do. In this prototype a change stays in this copy: nobody's real access changes.</p>
        <div role="list">${owners.map(o => `<div class="l-prow" role="listitem"><span class="l-av" aria-hidden="true">${esc(o.name[0])}</span><div class="l-grow"><b>${esc(o.name)}</b> <span class="small mut">(you)</span><div class="small mut">${MASK} · Google sign-in · owner</div></div><span class="chip">${icon('key')} Owner</span></div>`).join('')}
        ${list.map((x, i) => `<div class="l-prow" role="listitem"><span class="l-av" aria-hidden="true">${esc(x.name[0] || '?')}</span><div class="l-grow"><b>${esc(x.name)}</b><div class="small mut">${MASK} · added ${esc(x.added)} · has not opened it yet</div></div>
          ${seg(x.role, `data-prole="${i}" data-r`, `What ${x.name} can do`)}<button class="ib" data-prm="${i}" title="Remove ${esc(x.name)}" aria-label="Remove ${esc(x.name)}">${icon('trash')}</button></div>`).join('')}</div>
        <form class="l-add" data-add><input type="text" id="l-pname" placeholder="Their name" aria-label="Their name" required>
          <input type="email" id="l-pmail" placeholder="Their Google email" aria-label="Their Google email" required>
          ${seg(role, 'data-newrole', 'What they can do')}<button class="btn pri sm" type="submit">${icon('plus')} Add</button></form>
        ${err ? `<p class="small l-err" role="alert">${esc(err)}</p>` : ''}
        <p class="small mut l-hint">${icon('eye')} Can view: reads the page, its questions, Reference and History. ${icon('edit')} Can answer and send: also answers, writes notes and presses Send.</p></div>`;
      w.querySelector('[data-back]').onclick = () => ctx.go('links');
      w.querySelectorAll('[data-newrole]').forEach(b => { b.onclick = () => { role = b.dataset.newrole; w.querySelectorAll('[data-newrole]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); }; });
      w.querySelectorAll('[data-prole]').forEach(b => { b.onclick = () => { const i = +b.dataset.prole, was = list[i].role, n = list.map((x, j) => j === i ? {...x, role: b.dataset.r} : x);
        save(n); ctx.toast(`${list[i].name}: ${ROLE[b.dataset.r].toLowerCase()}`, {undo: () => save(list.map((x, j) => j === i ? {...x, role: was} : x))}); }; });
      w.querySelectorAll('[data-prm]').forEach(b => { b.onclick = () => { const before = list, x = list[+b.dataset.prm];
        save(list.filter((_, j) => j !== +b.dataset.prm)); ctx.toast(`${x.name} removed`, {undo: () => save(before)}); }; });
      w.querySelector('[data-add]').onsubmit = e => {
        e.preventDefault();
        const name = w.querySelector('#l-pname').value.trim(), mail = w.querySelector('#l-pmail').value.trim();
        err = !name ? 'Type their name.' : !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(mail) ? 'Type their full Google email address.'
          : list.some(x => x.name.toLowerCase() === name.toLowerCase()) ? `${name} is already on the list.` : '';
        if (err) return draw();
        const before = list;  // the email itself is never kept: every email shows as member@example.com
        save([...list, {name, role, added: new Date().toISOString().slice(0, 10)}]);
        ctx.toast(`${name} added: ${ROLE[role].toLowerCase()}`, {undo: () => save(before)});
      };
    }
    draw();
  }

  // notes on kept documents go with the one Send, under Notes; Go to it opens that document (r12 fix6, running 4)
  let ON = null, LD = null;  // the Pages & links view on screen, to redraw it when Send takes a note back; LD: its feed
  const redo = () => { if (ON && ON.w.isConnected) draw(ON.w, ON.ctx, ON.D); };
  // Go to it opens the note's document and lands on the note, outlined, as the mock does (r12 fix8, running 3)
  async function goNote(c, n) {
    openAt(await c.data('links'), n.a);
    S.hl = n.id; S.note = ''; S.scroll = true;
    if (ON && ON.w.isConnected) draw(ON.w, ON.ctx, ON.D); else c.go('links');  // on screen: the same hash fires no hashchange
  }
  // the notes kit's hooks: Send's Go to it on a re-opened note, a redraw, and a resolution on a line here, opened and outlined (r12 audit16 frame 1, 2)
  (P.noteHooks = P.noteHooks || {}).links = {go: r => goNote(P.ctx, {id: r.id, a: r.a}), redo: () => redo(), unedit: id => { if (S.edit === id) { S.edit = ''; S.edt = null; } },
    res: n => { S.res = n.ra; S.resGo = true; S.spot = ''; return goNote(P.ctx, {id: '', a: n.ra}); }};
  function openAt(D, a) {  // opens the document a note's anchor is in
    const kept = (/^doc:kept-([^~]+)/.exec(a) || [])[1];
    if (kept) { S.kept = kept; const d = (D.kept || []).find(x => x.id === kept), j = d ? revOf(d, a) : null;
      if (d && d.revs) { if (j == null) delete S.rv[d.id]; else S.rv[d.id] = j; } }
    else { const f = ((D.docs || {}).files || []).findIndex(f => a === docKey(f) || a.startsWith(docKey(f) + '~')); if (f >= 0) S.dsel = f; }
  }
  // the note being typed: a draft, in Send before Save and kept across a reload with "Unsent answers and notes" on, as Questions' open note is (audit8 running 1)
  const typed = c => { const d = c.prefs.get('draft:lnote', null); return d && (d.text || '').trim() ? d : null; };
  const goTyped = async (c, d) => { openAt(await c.data('links'), d.a); S.note = d.a; S.tgt = d.tgt || null; S.hl = '';
    const focus = () => { const t = ON && ON.w.isConnected && ON.w.querySelector('#l-nt'); if (t) { t.scrollIntoView({block: 'center'}); t.focus({preventScroll: true}); } };
    if (ON && ON.w.isConnected) { draw(ON.w, ON.ctx, ON.D); focus(); } else c.go('links'); };
  const cut = (s, n) => s.length > n ? s.slice(0, n - 1) + '…' : s;
  let KEPT = null;  // kept documents' titles, for Send before Pages & links has opened
  // unsent notes from the feed (after a reload: the server's, or a copy's simulated ones) and from this visit, once each (r12 fix8)
  const unsent = c => {
    if (!LD) c.data('links').then(d => { if (!LD) { LD = d; c.refreshTop(); } }).catch(() => {});
    // before links.json is in (a reload), the notes as Send last listed them, saved with the drafts (r12 fix10 frame 1, reference 2)
    const fd = LD ? LD.notes || [] : c.prefs.get('draft:lnotes', []);
    const l = [...fd, ...mine.filter(n => !fd.some(x => x.id === n.id))].filter(n => P.notes.out(n) && !n.closed && /^doc:/.test(n.a)).map(n => Object.assign(n, {line: lineOf(n)}));
    if (LD) { const s = l.map(n => ({id: n.id, a: n.a, l: n.l, text: n.text, target: n.target, line: n.line, ...P.notes.state(n)})); if (JSON.stringify(s) !== JSON.stringify(c.prefs.get('draft:lnotes', []))) c.prefs.set('draft:lnotes', s); }
    return l;
  };
  // the line a note sits on, read back from its document after a reload, so Send still names it by its line (audit7 running 5)
  // `r`: a table's body row, by its number
  const blockText = (b, r) => !b ? '' : b[0] === 'tbl' ? (r ? [rowsOf(b)[r] || []] : rowsOf(b)).map(x => x.join(' ')).join(' ') : b[0] === 'img' ? `Picture ${b[3]}${b[2] ? ': ' + b[2] : ''}`
    : (b[0] === 'li' ? '• ' : '') + String(b[1]).replace(/\s+/g, ' ').trim();
  function lineOf(n) {
    if (n.line || !LD) return n.line || '';
    let m = /^doc:kept-([^~]+)~p~(.+)$/.exec(n.a);  // a kept document's line, by its anchor (~<n> alone is a chart bar, named in its label)
    if (m) { const d = (LD.kept || []).find(x => x.id === m[1]), p = d && atLine(d, m[2]); return p ? blockText((d.blocks || [])[p[0]], p[1]) : ''; }
    m = /^(doc:.+?)~(\d+)(?:~r(\d+))?$/.exec(n.a);  // a line of a Markdown file in the project's folder
    const f = m && ((LD.docs || {}).files || []).find(f => f.md && docKey(f) === m[1]);
    return f ? blockText(mdBlocks(f.md)[+m[2]], +m[3]) : '';
  }
  // a saved note taken back, by Send's Remove or its own: hidden now, its DELETE goes when Undo is gone, so Undo keeps the very stored note (r12 fix15)
  function takeNote(c, n) {
    const keep = c.take(n.id, 'api/comments/' + encodeURIComponent(n.id)), wm = mine, wd = LD && LD.notes, ws = c.prefs.get('draft:lnotes', []);
    mine = mine.filter(x => x.id !== n.id); if (LD) LD.notes = LD.notes.filter(x => x.id !== n.id); c.prefs.set('draft:lnotes', ws.filter(x => x.id !== n.id)); redo();
    return () => { keep(); mine = P.putBack(mine, wm, n.id);
      if (LD) { LD.notes = P.putBack(LD.notes || [], wd || [], n.id); if (!LD.notes.some(x => x.id === n.id)) LD.notes.push(n); }  // a feed read while it was hidden lacks it
      const l = P.putBack(c.prefs.get('draft:lnotes', []), ws, n.id); if (!l.some(x => x.id === n.id)) l.push({id: n.id, a: n.a, l: n.l, text: n.text, target: n.target, line: n.line});
      c.prefs.set('draft:lnotes', l); redo(); };
  }
  if (P.queue) P.queue({
    items: c => [...apprs(c).map(id => { if (!KEPT) c.data('links').then(d => { if (!KEPT) { KEPT = d.kept || []; c.refreshTop(); } }).catch(() => {});
      // the feed the tab or its chip already read names it at once; never the internal id (audit7 reference 5)
      const d = (KEPT || (LD || {}).kept || (ON ? ON.D.kept : null) || []).find(x => x.id === id), tl = c.prefs.get('draft:lappr-t', {});
      if (d && tl[id] !== d.t) c.prefs.set('draft:lappr-t', {...tl, [id]: d.t});  // its title, for Send before the feed is in after a reload (r12 fix10)
      return {key: 'lappr:' + id, group: 'Reference', html: `${c.esc(d ? d.t : tl[id] || id)} → <b>approved</b>`,
        go: () => { S.kept = id; S.hl = ''; if (ON && ON.w.isConnected) draw(ON.w, ON.ctx, ON.D); else c.go('links', 'kept-' + id); },
        remove: () => { c.prefs.set('draft:lappr', apprs(c).filter(x => x !== id)); redo(); return () => { c.prefs.set('draft:lappr', [...apprs(c), id]); redo(); }; }}; }),
    // say: its full words, so the round check sees a change past the listing's 140 (r12 audit32 running 1)
    ...(d => d ? [{key: 'lnn:' + d.a, group: 'Notes', say: d.text.trim(), html: `On “${c.esc(cut((d.tgt && d.tgt.quote) || d.line || d.l || 'Pages & links', 50))}”:${c.esc(cut(d.text.trim(), 140))}`,
      go: () => goTyped(c, d),
      // Send saves the listed draft as its own write before the round goes; the editor closes only once it is saved (r12 audit30 questions 3)
      save: async () => { const r = await c.api('api/comments', {anchor_id: d.a, anchor_label: d.l, text: d.text.trim(), target: d.tgt || undefined}, undefined, true);
        mine.push({id: r.id, a: d.a, l: d.l, line: d.line, text: r.text || d.text.trim(), who: r.author_name || 'You', at: r.created_at || new Date().toISOString(), target: d.tgt || undefined});
        const now = typed(c); if (now && now.a === d.a && now.text === d.text) { if (S.note === d.a) S.note = ''; c.prefs.set('draft:lnote', null); }
        else if (now && now.a === d.a) P.notes.late(r.id, d.text.trim(), now.text, {a: d.a, tab: 'links', on: (d.tgt && d.tgt.quote) || d.line || d.l || ''},
          () => { c.prefs.set('draft:lnote', null); if (S.note === d.a) S.note = ''; S.edit = r.id; S.edt = null; redo(); });
        return r; },
      remove: SAVING ? null : () => { c.prefs.set('draft:lnote', null); if (S.note === d.a) S.note = ''; redo();
        return () => { c.prefs.set('draft:lnote', d); S.note = d.a; S.tgt = d.tgt || null; redo(); }; }}] : [])(typed(c)),
    // a sent note he re-opened is the notes kit's own row, from the one draft store (r12 audit16 frame 1)
    ...unsent(c).map(n => ({key: 'ln:' + n.id, group: 'Notes', note: n.id, peer: !P.notes.mine(n), say: P.notes.say(n), html: `On “${c.esc(cut((n.target && n.target.quote) || n.line || n.l || 'Pages & links', 50))}”:${c.esc(cut(P.notes.say(n), 140))}`,
      go: () => goNote(c, n),
      remove: P.notes.rowRm(n) ? () => takeNote(c, n) : null}))],
    // the note he was typing is saved by Send itself (save above); one typed since stays for the next Send (r12 audit30 questions 3)
    // an approval made after the round check stays for the next Send (r12 audit31 running 4)
    sent: (c, was, done) => { unsent(c).forEach(P.notes.gone); c.prefs.set('draft:lappr', apprs(c).filter(id => !done('lappr:' + id))); c.prefs.set('draft:lnotes', []); redo(); },
  });
  P.tab({key: 'links', render, chip: async ctx => { const D = LD = await ctx.data('links'); return {text: String(1 + D.pages.length), title: 'pages'}; }});
})();
