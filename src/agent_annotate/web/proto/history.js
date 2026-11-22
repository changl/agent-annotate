/* History tab: every past answer by version, read-only (#69, #75). Search also finds overruled, superseded,
   overridden and replaced answers, all under one "overruled" tag (#70, #117). Filters All, Questions, Reference (#114).
   The eye opens an older version read-only; Close returns; no Older / Newer bar, no arrow keys (#115, #116).
   Also defines Proto.viewVersion and Proto.picSizes, used by Pages & links too. */
(function () {
  'use strict';
  const P = window.Proto = window.Proto || {};
  const S = {q: '', f: 'all', nv: 20, open: new Set(), wd: false, ref: false, nref: 60, wnOpen: null};
  const pl = (n, one, many) => `${Number(n).toLocaleString()} ${n === 1 ? one : many}`;
  const vn = v => String(v || '').replace(/^v/, '');
  const cut = (s, n) => (s = String(s || '').trim()).length > n ? s.slice(0, n - 1) + '…' : s;
  // a Send or a version in the browser's local time, as the header and the real page date it (audit7 running 2)
  const when = (iso, day) => { const t = new Date(iso); return iso && !isNaN(t) ? t.toLocaleString([], {month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'}) : day || ''; };
  // a Send's delivery state, in the header's words (frame.js DELIV)
  const DELIV = {acknowledged: 'read by the agent', accepted: 'delivered', started: 'agent working on it', pending: 'saved, agent not told yet', queued: 'saved, agent not told yet', active_monitor: 'delivered', uncertain: 'not confirmed yet', superseded: 'not delivered: the page changed agents'};

  /* ---------- a version or plan revision, read-only, with a close bar; says why when it fails to load ---------- */
  P.viewVersion = function (host, ctx, o) {
    const {esc, icon} = ctx;
    host.innerHTML = `<div class="hv-view" role="region" aria-label="${esc(o.title)}">
      <div class="hv-bar"><b>${esc(o.title)}</b><span class="small mut">read-only</span><span class="spacer"></span>
        <a class="ib" href="${esc(o.src)}" target="_blank" rel="noopener" title="Open it in a new tab" aria-label="Open it in a new tab">${icon('ext')}</a>
        <button class="btn sm" data-hv-close title="Close and go back">${icon('x')} Close</button></div>
      ${o.before || ''}<div class="hv-frame"></div></div>`;
    host.querySelector('[data-hv-close]').onclick = o.onClose;
    const box = host.querySelector('.hv-frame');
    CX = ctx;
    const told = () => TELL.has(o.src);
    async function load(retried) {
      box.innerHTML = `<p class="small mut">${icon('reload')} Loading…</p>`;
      let why = '';
      try {
        const r = await fetch(o.src, {cache: 'no-store'});
        if (!r.ok) {
          const body = await r.text().catch(() => '');
          let msg = ''; try { msg = JSON.parse(body).error || ''; } catch { msg = body.slice(0, 120); }
          why = `The page server answered “${msg || r.statusText || 'error'}” (code ${r.status}).`;
        }
      } catch (e) { why = `The page server did not answer: ${e.message}.`; }
      if (why) return fail(why, retried);
      box.innerHTML = '<iframe class="hv-if" title="The version, read-only"></iframe>';
      const f = box.querySelector('iframe');
      f.onload = () => fit(f, ctx, o.at);
      f.src = o.src;
    }
    function fail(why, retried) {
      const at = new Date().toTimeString().slice(0, 5);
      box.innerHTML = `<div class="hv-err" role="alert">${icon('warn')}<div><b>${esc(o.failTitle || 'This version could not load.')}</b> ${esc(why)} Nothing you wrote is lost.
        ${retried ? `<span class="small mut">Retried at ${at}: still failing.</span>` : ''}
        <div class="hv-acts"><button class="btn sm" data-retry>${icon('reload')} Retry</button>
        ${told() ? `<span class="small h-ok">${icon('tick')} The agent is told with your next Send</span> <button class="lk small" data-untell>Undo</button>` : `<button class="btn sm" data-tell>${icon('msg')} Tell the agent</button>`}${P.inertMark()}</div></div></div>`;
      box.querySelector('[data-retry]').onclick = () => load(true);
      // Undo sits beside the done line, as in the mock (#107); nothing is sent in the prototype
      const tell = box.querySelector('[data-tell]'), untell = box.querySelector('[data-untell]');
      const again = () => { if (box.isConnected) fail(why, retried); };
      LIVE.set(o.src, again);  // the failure on screen now, so Send's Remove and its Undo redraw this one, not a closed one
      if (tell) tell.onclick = () => { TELL.set(o.src, {text: (o.failTitle || 'This version could not load.').replace(/\.$/, '') + '; please republish it.', go: location.hash.slice(1)}); again(); };
      if (untell) untell.onclick = () => { TELL.delete(o.src); again(); };
    }
    load(false);
  };
  // "Tell the agent" about a page that could not load goes with the one Send, under Replies to the agent (r12 fix6, running 2)
  // kept in prefs as a draft, so it survives a reload with "Unsent answers and notes" on, as task drafts do (r12 fix8, running 2)
  let CX;
  const all = () => ({...(CX ? CX.prefs.get('draft:tell', {}) : {})}), put = a => CX && CX.prefs.set('draft:tell', a);
  const TELL = {has: s => s in all(), set: (s, t) => put({...all(), [s]: t}), delete: s => { const a = all(); delete a[s]; put(a); },
    keys: () => Object.keys(all()), clear: () => put({}), [Symbol.iterator]: () => Object.entries(all())[Symbol.iterator]()};
  const LIVE = new Map();
  const again = src => { const f = LIVE.get(src); if (f) f(); };
  if (P.queue) P.queue({
    items: ctx => [...(CX = ctx, [...TELL]).map(([src, t]) => ({key: 'tell:' + src, group: 'Replies to the agent', html: `About the page that could not load: “${ctx.esc(t.text)}”`,
      go: () => { location.hash = t.go; }, remove: () => { TELL.delete(src); again(src); return () => { TELL.set(src, t); again(src); }; }})),
      // a note being typed on the chart's point is in Send before Save, as a Pages & links note is (audit8 running 1, 3)
      ...(d => d ? [{key: 'hnn:' + d.v, group: 'Notes', html: `On “${ctx.esc(CLAB(d.v))}”: ${ctx.esc(d.text.trim().length > 140 ? d.text.trim().slice(0, 139) + '…' : d.text.trim())}`,
        go: () => { S.cn = d.v; S.q = ''; if (onH()) { draw(HE.el, HE.ctx); focusC(HE.el); } else ctx.go('history'); },
        remove: () => { ctx.prefs.set('draft:hnote', null); if (S.cn === d.v) S.cn = ''; redrawH();
          return () => { ctx.prefs.set('draft:hnote', d); S.cn = d.v; redrawH(); }; }}] : [])(typedC(ctx)),
      // a saved note on a point is History's own: Go to it shows it on the chart, Remove takes it off the chart too (audit9 running 1)
      ...savedC(ctx).map(n => ({key: 'hcn:' + n.id, group: 'Notes', note: n.id, html: `On “${ctx.esc(n.label || 'Questions asked per version')}”: ${ctx.esc(cut(n.text, 140))}`,
        go: () => { S.cn = ''; S.q = ''; S.hl = n.id; if (onH()) { draw(HE.el, HE.ctx); litC(HE.el); } else ctx.go('history'); },
        remove: () => takeC(ctx, n)}))],
    sent: ctx => { CX = ctx; const l = [...TELL.keys()]; TELL.clear(); l.forEach(again); if (typedC(ctx)) { S.cn = ''; ctx.prefs.set('draft:hnote', null); redrawH(); }
      savedC(ctx).forEach(n => { n.sent = true; n.edited = false; }); ctx.prefs.set('draft:hcnotes', []); },
  });

  // The frame grows to its content, so the page has one scroll; pictures get their own size control.
  function fit(f, ctx, at) {
    let doc;
    try { doc = f.contentDocument; } catch { return; }
    if (!doc) return;
    const theme = () => { doc.documentElement.dataset.theme = document.documentElement.dataset.theme; };
    theme();
    // follows a theme change while it is open; stops once the frame is closed
    const mo = new MutationObserver(() => f.isConnected ? theme() : mo.disconnect());
    mo.observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
    P.picSizes(doc, ctx);
    const size = () => { f.style.height = Math.max(200, doc.documentElement.scrollHeight) + 'px'; };
    size();
    try { new ResizeObserver(size).observe(doc.body); } catch {}
    // a resolution in this version: its spot opens, is scrolled to and stays outlined (r12 audit15 questions 3)
    const spot = at && doc.querySelector(`[data-anchor-id="${CSS.escape(at)}"]`);
    if (spot) {
      for (let d = spot.closest('details'); d; d = d.parentElement && d.parentElement.closest('details')) d.open = true;
      if (!spot.getClientRects().length) { const t = (spot.closest('section') || spot).querySelector('.annotate-unchanged-toggle[aria-expanded=false]'); if (t) t.click(); }
      P.notes.lit(spot);
      const go = () => { const top = document.getElementById('p-top'); size();
        window.scrollTo({top: scrollY + f.getBoundingClientRect().top + spot.getBoundingClientRect().top - (top ? top.offsetHeight : 0) - 120}); };
      requestAnimationFrame(go);
      // the reader's lists and pictures can still grow after the jump: keep the spot in view until he scrolls or 3 s pass (r12 fix17)
      const view = f.closest('.hv-view'), end = Date.now() + 3000, ro = new ResizeObserver(() => Date.now() < end ? go() : ro.disconnect()), stop = () => ro.disconnect();
      if (view) { ro.observe(view); ro.observe(doc.body); for (const e of ['wheel', 'touchstart', 'keydown']) window.addEventListener(e, stop, {once: true}); }
    }
    // a version's section index, beside "What you sent on it" (the mock's "Its sections"); each line scrolls to its section
    const secs = f.closest('.hv-view').querySelector('.h-secs');
    if (!secs) return;
    const hs = [...doc.querySelectorAll('h2')].filter(h => h.textContent.trim());
    secs.innerHTML = hs.map((h, i) => `<button class="lk h-sec" data-sec="${i}">${ctx.esc(h.textContent.trim())}</button>`).join('') || '<p class="small mut">No sections in this version.</p>';
    secs.onclick = e => { const b = e.target.closest('[data-sec]'); if (!b) return;
      const h = hs[+b.dataset.sec], sec = h.closest('section') || h;
      // a folded section (unchanged, or all answered) opens first, through the page's own fold button
      if (!h.getClientRects().length) { const t = sec.querySelector(':scope > .annotate-sfold-bar > .annotate-unchanged-toggle[aria-expanded=false], :scope > .annotate-unchanged-bar > .annotate-unchanged-toggle[aria-expanded=false]'); if (t) t.click(); }
      requestAnimationFrame(() => { const el = h.getClientRects().length ? h : sec, top = document.getElementById('p-top');
        size();
        window.scrollTo({top: scrollY + f.getBoundingClientRect().top + el.getBoundingClientRect().top - (top ? top.offsetHeight : 0) - 8, behavior: 'smooth'}); }); };
  }

  /* ---------- each picture remembers its own size (#118): 25 / 50 / 75 / 100 %, kept per picture ---------- */
  const SIZES = [25, 50, 75, 100];
  // root: a document (a version's frame) or an element of this page (Questions, Reference)
  P.picSizes = function (root, ctx) {
    const doc = root.ownerDocument || root;
    if (!doc.getElementById('pp-size-css')) {
      const st = doc.createElement('style'); st.id = 'pp-size-css';
      st.textContent = '.pp-size{display:flex;flex-wrap:wrap;gap:4px;align-items:center;margin:4px 0 10px;font:12px system-ui,sans-serif;color:#666}'
        + '.pp-size button{border:1px solid #bbb;background:transparent;color:inherit;border-radius:6px;padding:1px 7px;cursor:pointer;font:inherit}'
        + '.pp-size button[aria-pressed=true]{background:#222;color:#fff;border-color:#222}'
        + '[data-theme=dark] .pp-size{color:#aaa}[data-theme=dark] .pp-size button[aria-pressed=true]{background:#eee;color:#111}'
        // one set of controls: the page's own zoom buttons and Full size link open inside the frame, which is as tall as the page,
        // so its viewer would sit far above the screen; ours open this page's viewer instead (audit5 running 2). Its IMG id stays.
        + 'img.pp-sized~.aa-img-bar .aa-img-zoom,figure:has(img.pp-sized)>a.aa-full{display:none!important}';
      doc.head.appendChild(st);
    }
    // as in the mock: the sizes open the full-size viewer at that share of the screen width and this picture keeps it;
    // the picture on the page stays as published (#38, #118)
    const all = ctx.prefs.get('picsize', {}), def = () => ctx.prefs.get('zoomDef', 75);
    // each picture by its place, never its file (Proto.media.pk: its anchor and its order there), and its version's address,
    // so two copies of one file, or one spot in two versions, keep their own sizes (r12 audit18 frame 3)
    const keyOf = img => { if (!img.getAttribute('src')) return '';
      const a = img.closest('[data-anchor-id]'), j = a === img ? 0 : [...(a || doc).querySelectorAll('img')].indexOf(img) + 1;
      return doc.location.pathname + '|' + P.media.pk(a ? a.dataset.anchorId : 'pic', j); };
    const zOf = img => all[keyOf(img)] || def();
    const remember = (img, z) => { if (z === def()) delete all[keyOf(img)]; else all[keyOf(img)] = z; ctx.prefs.set('picsize', all); };
    const pageFull = img => { const f = img.closest('figure'); return f && f.querySelector(':scope > a.aa-full'); };
    // the original, not the page's preview: the picture's data-full, else the page's own Full size link
    const orig = img => { const a = pageFull(img), u = img.dataset.full || (a && a.getAttribute('href')); return u ? new URL(u, doc.baseURI).href : img.currentSrc || img.src; };
    const apply = (img, bar) => {
      const z = zOf(img), own = keyOf(img) in all;
      bar.querySelectorAll('[data-pct]').forEach(b => b.setAttribute('aria-pressed', String(+b.dataset.pct === z)));
      bar.querySelector('[data-full]').dataset.z = z;
      const d = bar.querySelector('[data-defs]'); d.hidden = !own;
      if (own) d.firstChild.textContent = `this picture ${z}%, others ${def()}% `;
    };
    const add = img => {
      if (img.dataset.ppSized || !keyOf(img)) return;
      if (Math.max(+img.getAttribute('width') || 0, img.naturalWidth || 0) < 160) return;  // icons and thumbnails keep their size; a narrow preview of a big picture does not
      img.dataset.ppSized = '1'; img.classList.add('pp-sized');
      img.style.width = '';  // a size kept inline by an earlier prototype
      const bar = doc.createElement('div');
      bar.className = 'pp-size';
      bar.innerHTML = `<span>Open full size at</span>${SIZES.map(s => `<button type="button" data-pct="${s}" aria-label="Open at ${s}%">${s}%</button>`).join('')}<button type="button" data-full title="Open the original full size">⤢ Full size</button><span data-defs hidden>x<button type="button" data-def>Use the default</button></span>`;
      bar.onclick = e => {
        const b = e.target.closest('button'); if (!b) return;
        if (b.hasAttribute('data-def')) { delete all[keyOf(img)]; ctx.prefs.set('picsize', all); return apply(img, bar); }
        if (b.dataset.pct) { remember(img, +b.dataset.pct); apply(img, bar); }
        P.zoom(orig(img), img.alt, zOf(img), ctx, z => { remember(img, z); apply(img, bar); });
      };
      const pf = pageFull(img);
      // after the page's own bar and Full size link, which it stands in for; outside a note's pin box, so pins keep their spot
      (pf || img.closest('a, .qpinwrap') || img).after(bar);
      apply(img, bar);
    };
    root.querySelectorAll('img').forEach(img => {
      img.loading = 'eager';  // the frame is as tall as its content, so a lazy picture would wait for nothing
      if (img.complete && img.naturalWidth) add(img); else img.addEventListener('load', () => add(img), {once: true});
    });
  };

  /* ---------- full-size viewer (#39): the picture at 25-100% of the screen width, Close or Esc ---------- */
  P.zoom = function (src, cap, z, ctx, onSize) {
    const {esc} = ctx;
    let dlg = document.getElementById('pp-zoom');
    if (dlg) dlg.remove();
    dlg = document.createElement('div');
    dlg.id = 'pp-zoom'; dlg.className = 'pp-zoom'; dlg.setAttribute('role', 'dialog'); dlg.setAttribute('aria-modal', 'true'); dlg.setAttribute('aria-label', 'Full-size picture');
    const back = document.activeElement;
    P.notes.endMove();  // opening or closing a picture viewer ends a Move, as on every tab (r12 audit18 frame 1, 2)
    const close = () => { dlg.remove(); P.notes.endMove(); document.removeEventListener('keydown', key, true); if (back && back.focus) back.focus(); };
    const key = e => { if (e.key === 'Escape') { e.stopPropagation(); close(); } };
    const draw = () => {
      dlg.innerHTML = `<div class="pp-zbar"><b class="small">${esc(cap || 'Picture')}</b><span class="pp-zseg" role="group" aria-label="Size">${SIZES.map(x => `<button class="chipb" data-z="${x}" aria-pressed="${x === z}">${x}%</button>`).join('')}</span>
        <span class="small mut pp-zhint">of the screen width · <kbd>Esc</kbd> closes</span><span class="spacer"></span><button class="btn sm" data-zclose>${ctx.icon('x')} Close</button></div>
        <div class="pp-zpic" style="width:${z}vw"><img src="${esc(src)}" alt="${esc(cap || '')}"></div>`;
      dlg.querySelector('[data-zclose]').focus();
    };
    dlg.onclick = e => { const b = e.target.closest('button'); if (!b) return; if (b.dataset.z) { z = +b.dataset.z; draw(); if (onSize) onSize(z); } else if (b.hasAttribute('data-zclose')) close(); };
    document.addEventListener('keydown', key, true);
    document.body.appendChild(dlg);
    draw();
  };

  /* ---------- Questions asked per version, the newest 40 (the mock's chartOf): a compact strip over the list; a point takes a note ---------- */
  // the full chart lives in Analytics; the strip reads the same per-version counts the version rows show
  let HE = null, QD = null, QR = null, CN = [];  // HE: the tab on screen; QD: Questions' feed, whose notes hold saved chart notes; CN: saved this visit
  const CLAB = v => `Questions asked per version, version ${vn(v)}`;
  const typedC = c => { const d = c.prefs.get('draft:hnote', null); return d && (d.text || '').trim() ? d : null; };
  // the list on screen; a box left behind by another tab no longer counts, so Go to it switches tabs (audit9 running 1)
  const onH = () => !!(HE && HE.el.isConnected && HE.el.querySelector('#h-list'));
  const redrawH = () => { if (onH()) draw(HE.el, HE.ctx); };
  const focusC = el => { const t = el.querySelector('#h-nt, #h-et'); if (t) { t.scrollIntoView({block: 'center'}); t.focus({preventScroll: true}); } };
  // the note stays lit through a redraw (Questions' feed arriving) for 2.5 s, as Questions' qlit
  const litC = el => { const id = S.hl, t = id && el.querySelector(`[data-cnote="${CSS.escape(id)}"]`); if (!t || S.hlT === id) return; S.hlT = id;
    t.scrollIntoView({block: 'center'}); t.classList.add('lit');
    setTimeout(() => { if (S.hl === id) S.hl = ''; S.hlT = ''; document.querySelectorAll('[data-cnote].lit').forEach(e => e.classList.remove('lit')); }, 2500); };
  const qpv = () => Object.entries(D.versions || {}).filter(([v]) => /^v\d+$/.test(v)).sort((a, b) => +vn(a[0]) - +vn(b[0])).slice(-40);
  // a closed note stays on its point, folded with Re-open, as on every tab (the notes kit, r12 audit16 frame 6)
  const allC = () => { const q = (QD && QD.notes) || []; return [...q, ...CN.filter(n => !q.some(x => x.id === n.id))].filter(n => /^chart:/.test(n.anchor || '')); };
  const cnotes = v => allC().filter(n => n.anchor === 'chart:' + v);
  // saved and not yet sent; Questions' feed is read here too, so Send lists them before History is opened
  // kept as saved records too (draft:hcnotes): while that feed is held or failed, Send lists them from what was saved (r12 fix14 running 1)
  const savedC = ctx => { if (!QR) QR = ctx.data('questions').then(q => { if (q && q !== QD) { QD = q; ctx.refreshTop && ctx.refreshTop(); } }).catch(() => {}).finally(() => { QR = null; });
    const m = ctx.prefs.get('draft:hcnotes', []);
    if (!QD) return [...m, ...CN.filter(n => P.notes.out(n) && !m.some(x => x.id === n.id))];
    // a saved record the read predates stays: no late or stale read removes its row (r12 audit14 running 1)
    const inQ = new Set((QD.notes || []).map(n => n.id)), l0 = allC().filter(n => P.notes.out(n) && !n.closed);
    const l = [...l0, ...m.filter(r => !inQ.has(r.id) && !l0.some(x => x.id === r.id) && r.at && QD.at && Date.parse(r.at) >= Date.parse(QD.at) && !ctx.taken(r.id))];
    const s = l.map(n => ({id: n.id, anchor: n.anchor, label: n.label, text: n.text, at: n.at}));
    if (JSON.stringify(s) !== JSON.stringify(m)) ctx.prefs.set('draft:hcnotes', s);
    return l; };
  const dropC = id => { CN = CN.filter(x => x.id !== id); if (QD) QD.notes = (QD.notes || []).filter(x => x.id !== id); };
  // takes a saved note back (its Undo icon, Send's Remove); returns what puts it back
  async function takeC(ctx, n) {
    const was = ctx.prefs.get('draft:hcnotes', []);
    ctx.prefs.set('draft:hcnotes', was.filter(x => x.id !== n.id));  // Send's count follows at once
    // the record stays in the store until Undo is gone: Undo puts back the very note, its saved version too (r12 audit13 questions 2, running 2)
    const keep = ctx.take(n.id, 'api/comments/' + encodeURIComponent(n.id));
    dropC(n.id); if (S.ce === n.id) S.ce = ''; redrawH(); ctx.refreshChips();
    // its saved record goes back too, so every later first Send lists it before Questions answers (r12 audit13 running 2)
    return async () => { keep(); const l = P.putBack(ctx.prefs.get('draft:hcnotes', []), was, n.id); if (!l.some(x => x.id === n.id)) l.push({id: n.id, anchor: n.anchor, label: n.label, text: n.text, at: n.at});
      ctx.prefs.set('draft:hcnotes', l); CN.push({...n, sent: false}); redrawH(); ctx.refreshChips(); };
  }
  // a saved note on a point, as the mock's noteBox: Edit, Undo, Copy note and Copy note link; Edit opens its own wording (audit10 running 3)
  function cbox(ctx, x, no, v) {
    const {esc, icon} = ctx, id = esc(x.id), what = `Note ${no} on version ${esc(vn(v))}`, lit = S.hlT === x.id ? ' lit' : '';
    const ib = (k, label, attr) => `<button class="ib sm" title="${label}" aria-label="${label}" ${attr}="${id}">${icon(k)}</button>`;
    const mk = `<span class="qmk${x.sent ? ' sent' : ''}" title="Your note ${no}${x.sent ? ', sent' : ''}">${icon('note')}${no}</span>`;
    if (S.ce === x.id) return `<div class="qnote h-cnote" id="hn-${id}" data-cnote="${id}">${mk}<b>${what}</b> <span class="small mut">· goes with your next Send</span>
      <textarea id="h-et" rows="3" aria-label="${what}">${esc(x.text)}</textarea>
      <div class="h-nacts"><button class="btn sm pri" data-csavee="${id}">Save</button><button class="btn sm" data-ccancel>Cancel</button><span class="small mut"><kbd>⌘↵</kbd> saves · an empty note is dropped</span></div></div>`;
    // a sent one carries the notes kit's lifecycle (Re-open, View resolution, Move, Close); a closed one folds with Re-open (r12 audit16 frame 6)
    const K = P.notes, cp = ib('copy', 'Copy the note text', 'data-ccopy') + ib('link', 'Copy a link to this note', 'data-clink');
    if (x.closed) return `<div class="qnote small h-cnote sent closed${lit}" id="hn-${id}" data-cnote="${id}">${mk}<span class="saved">${icon('archive')} ${what} closed</span> <span class="mut">${esc(x.text)}</span><span class="nacts">${K.closedActs(x)}</span></div>`;
    const acts = x.sent ? K.acts(ctx, x, S.cmove === x.id) + cp : ib('edit', 'Edit this note', 'data-cned') + ib('undo', 'Undo: remove this note', 'data-cdel') + cp;
    return `<div class="qnote small h-cnote${x.sent ? ' sent' : ''}${S.cmove === x.id ? ' moving' : ''}${lit}" id="hn-${id}" data-cnote="${id}">${mk}<b>${what}:</b> ${esc(x.text)} ${x.sent ? `${K.words(ctx, x)} ${K.view(x)}` : '<span class="saved">· goes with Send</span>'}<span class="nacts">${acts}</span>${x.sent ? K.thread(ctx, x) : ''}</div>`;
  }
  async function editC(el, ctx, id) {
    const n = allC().find(x => x.id === id), t = el.querySelector('#h-et'), text = ((t && t.value) || '').trim();
    S.ce = '';
    if (!n || text === n.text) return draw(el, ctx);
    if (!text && !n.sent) { const back = await takeC(ctx, n); return ctx.toast('Note removed', {undo: back}); }
    // the kit's edit, as on every tab: in place, with Undo; a sent one goes with the next Send again (today's edit on a sent note)
    const ok = await P.notes.fix(ctx, n, text, ctx.api, (w, p) => { [...CN, ...((QD && QD.notes) || [])].forEach(x => { if (x.id === id) Object.assign(x, p); }); redrawH(); ctx.refreshTop(); });
    if (!ok) { S.ce = id; draw(el, ctx); }
  }
  // Move: the kit's re-pin to the point he clicks, with Undo
  function moveC(el, ctx, v) {
    const x = allC().find(n => n.id === S.cmove); S.cmove = '';
    if (!x || x.anchor === 'chart:' + v) return draw(el, ctx);
    return P.notes.move(ctx, x.id, {anchor_id: x.anchor, anchor_label: x.label, target: x.target || null}, {anchor_id: 'chart:' + v, anchor_label: CLAB(v), target: null}, ctx.api,
      p => { if (p) [...CN, ...((QD && QD.notes) || [])].forEach(n => { if (n.id === x.id) Object.assign(n, {anchor: p.anchor_id, label: p.anchor_label, target: p.target}); });
        S.hl = p ? x.id : ''; S.hlT = ''; redrawH(); if (p && onH()) litC(HE.el); });
  }
  // the notes kit's hooks: Send's Go to it on a re-opened chart note, and a redraw
  (P.noteHooks = P.noteHooks || {}).history = {redo: () => redrawH(),
    go: r => { S.cn = ''; S.q = ''; S.hl = r.id; S.hlT = ''; if (onH()) { draw(HE.el, HE.ctx); litC(HE.el); } else P.ctx.go('history'); }};
  async function copyC(ctx, text, what) {
    try { await navigator.clipboard.writeText(text); ctx.toast(what + ' copied'); } catch { ctx.toast('Copy failed: your browser blocked it'); }
  }
  function strip(ctx) {
    const {esc, icon} = ctx, vs = qpv();
    if (vs.length < 2) return '';
    const n = m => m.items || 0, mx = Math.max(1, ...vs.map(([, m]) => n(m))), X = i => 34 + i * 20, Y = k => 50 - k / mx * 42;
    // a marked point is a marker: it lists its notes, with Go to it and + Comment (the notes kit's spot list, r12 audit16 frame 6)
    const pts = vs.map(([v, m], i) => { const k = cnotes(v).length, on = S.cn === v || k > 0, t = `Version ${vn(v)}: ${pl(n(m), 'question', 'questions')}, ${m.open || 0} still open`;
      return `<circle data-cpt="${esc(v)}" cx="${X(i)}" cy="${Y(n(m)).toFixed(1)}" r="${on ? 5 : 3.5}" class="h-cpt${on ? ' on' : ''}${S.cn !== v && P.notes.sent(cnotes(v)) ? ' sent' : ''}" tabindex="0" role="button" aria-expanded="${S.cspot === v}" aria-label="${esc(t)}. ${k ? `${pl(k, 'note', 'notes')}: list them` : 'Write a note on it'}"><title>${esc(t)}</title></circle>`; }).join('');
    const order = allC();
    const notes = vs.flatMap(([v]) => [...(S.cspot === v && cnotes(v).length ? [P.notes.spot(ctx, cnotes(v).map(x => [x, order.indexOf(x) + 1]), `on version ${esc(vn(v))}`, `data-spotadd="${esc(v)}"`)] : []),
      ...cnotes(v).map(x => cbox(ctx, x, order.indexOf(x) + 1, v))]).join('');
    const dr = ctx.prefs.get('draft:hnote', null), m = S.cn && (D.versions[S.cn] || {});
    const box = S.cn ? `<div class="h-nbox"><div class="small mut">New note on version ${esc(vn(S.cn))}: ${pl(n(m), 'question', 'questions')} asked · goes with your next Send</div>
      <textarea id="h-nt" rows="3" placeholder="Write a note for the agent about this version" aria-label="Your note">${esc(dr && dr.v === S.cn ? dr.text : '')}</textarea>
      <div class="h-nacts"><button class="btn sm pri" data-csave>Save note</button><button class="btn sm" data-ccancel>Cancel</button><span class="small mut"><kbd>⌘↵</kbd> saves</span></div></div>` : '';
    return `<div class="h-chart"><div class="h-ctl small"><b>Questions asked per version</b><br><span class="mut">the newest ${vs.length} versions, versions ${esc(vn(vs[0][0]))} to ${esc(vn(vs.at(-1)[0]))} · most: ${mx}</span></div>
      <svg viewBox="0 0 ${X(vs.length) + 4} 58" role="img" aria-label="Questions asked per version"><polyline fill="none" stroke="currentColor" stroke-opacity=".35" points="${vs.map(([, m], i) => `${X(i)},${Y(n(m)).toFixed(1)}`).join(' ')}"/>${pts}
      <text x="0" y="${Y(mx) + 4}" class="h-cax">${mx}</text><text x="0" y="52" class="h-cax">0</text></svg>${notes || box ? `<div class="h-cnotes">${notes}${box}</div>` : ''}</div>`;
  }
  async function saveC(el, ctx) {
    const v = S.cn, text = (el.querySelector('#h-nt').value || '').trim();
    if (!text) return ctx.toast('Write something first');
    try {
      const c = await ctx.api('api/comments', {anchor_id: 'chart:' + v, anchor_label: CLAB(v), text});
      CN.push({id: c.id, anchor: 'chart:' + v, label: CLAB(v), text: c.text || text, at: c.created_at || new Date().toISOString()});
      S.cn = ''; ctx.prefs.set('draft:hnote', null); draw(el, ctx); ctx.refreshChips();
      ctx.toast('Note saved', {undo: async () => { await ctx.api('api/comments/' + encodeURIComponent(c.id), undefined, 'DELETE'); CN = CN.filter(x => x.id !== c.id);
        if (QD) QD.notes = (QD.notes || []).filter(x => x.id !== c.id); redrawH(); ctx.refreshChips(); }});
    } catch (er) { ctx.toast(`The note was not saved: ${er.message}`); }
  }

  /* ---------- the tab ---------- */
  let D = null, R = null;
  async function render(el, ctx, anchor) {
    P.notes.slot(S, 'history', 'cmove');  // S.cmove is the kit's one Move; navigating here ended any earlier one (r12 audit17 reference 4, fix20)
    D = await ctx.data('history');
    // the copy's findings audits and Copy library, from Reference's own data; History never waits for it, the rows join when it arrives
    if (!R) ctx.data('reference').then(r => { R = r; if (el.querySelector('#h-list')) draw(el, ctx); }).catch(() => {});
    ctx.data('questions').then(q => { QD = q; if (el.querySelector('#h-list') && qpv().some(([v]) => cnotes(v).length)) { draw(el, ctx); litC(el); } }).catch(() => {});
    const {esc, icon} = ctx;
    if (/^hn-/.test(anchor || '')) { S.hl = anchor.slice(3); S.hlT = ''; anchor = ''; }  // a copied note link lands on the note
    if (anchor) return openView(el, ctx, anchor);
    HE = {el, ctx};
    const dr = typedC(ctx);  // the note he was typing on a point before a reload reopens, words and all
    if (dr && !S.cn) S.cn = dr.v;
    const chips = [['all', 'All', ''], ['q', 'Questions', 'q'], ['ref', 'Reference', 'ref']]
      .map(([k, t, i]) => `<button class="chipb" data-hf="${k}" aria-pressed="${S.f === k}">${i ? icon(i) : ''}${t}</button>`).join('');
    el.innerHTML = `<div class="h-wrap"><div class="h-bar"><input type="search" id="h-q" placeholder="Find a past decision" aria-label="Find a past decision" value="${esc(S.q)}">
      <span class="h-chips" role="group" aria-label="Show">${chips}</span><span class="spacer"></span>
      <span class="small mut">${pl(D.count, 'answer', 'answers')} in ${pl(D.sends, 'Send', 'Sends')} · read-only</span></div><div id="h-list"></div></div>`;
    const input = el.querySelector('#h-q');
    let t;
    input.oninput = () => { clearTimeout(t); t = setTimeout(() => { S.q = input.value.trim(); S.nv = 20; draw(el, ctx); }, 120); };
    el.querySelectorAll('[data-hf]').forEach(b => { b.onclick = () => { S.f = b.dataset.hf; el.querySelectorAll('[data-hf]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); draw(el, ctx); }; });
    const wrap = el.querySelector('.h-wrap');
    wrap.onclick = e => click(e, el, ctx);
    wrap.oninput = e => { if (e.target.id !== 'h-nt' || !S.cn) return;
      const was = !!typedC(ctx); ctx.prefs.set('draft:hnote', {v: S.cn, text: e.target.value}); if (was !== !!typedC(ctx)) ctx.refreshTop(); };
    // ⌘↵ in the note saves it, as in the mock; Enter or Space on a point opens its note
    wrap.onkeydown = e => {
      if (e.target.id === 'h-nt' && (e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); saveC(el, ctx); }
      else if (e.target.id === 'h-et' && (e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); editC(el, ctx, S.ce); }
      else if (e.key === 'Escape' && S.cmove) { S.cmove = ''; draw(el, ctx); }
      else if (e.target.dataset && e.target.dataset.cpt && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); e.target.dispatchEvent(new MouseEvent('click', {bubbles: true})); }
    };
    draw(el, ctx);
    if (S.cn && typedC(ctx)) focusC(el);
    else litC(el);  // Send's Go to it on a saved note; if Questions' feed is still on its way, once it is in
  }

  const hay = h => (`${h.n} ${h.q} ${h.a}` + (h.ovr ? ` overruled ${h.ovr[0]} ${h.ovr[1]}` : '')).toLowerCase();
  function draw(el, ctx) {
    const {esc, icon} = ctx, q = S.q.toLowerCase(), num = /^\d{1,6}$/.test(q) ? +q : -1;
    const box = el.querySelector('#h-list');
    let html = q ? '' : strip(ctx);  // as in the mock: over the list, with no search
    if (S.f !== 'ref') {
      const list = q ? D.answers.filter(h => h.n === num || hay(h).includes(q)) : D.answers;
      const byV = new Map();
      for (const h of list) { if (!byV.has(h.v)) byV.set(h.v, []); byV.get(h.v).push(h); }
      // every published version is listed, newest first, so one with questions but no Send still opens (#73); searching lists only matches
      const num_ = v => +vn(v) || 0;
      const vers = q ? [...byV] : [...new Set([...Object.keys(D.versions), ...byV.keys()])].sort((a, b) => num_(b) - num_(a)).map(v => [v, byV.get(v) || []]);
      const fix = n => /\bfix/i.test(n) ? '<span class="h-fix">fix</span> ' : '';
      if (q) html += `<p class="small mut">${pl(list.length, 'match', 'matches')}</p>`;
      let first = true;
      html += vers.slice(0, S.nv).map(([v, hs]) => {
        const m = D.versions[v] || {}, eye = `<button class="ib" data-hv="${esc(v)}" title="Open version ${esc(vn(v))} read-only" aria-label="Open version ${esc(vn(v))} read-only">${icon('eye')}</button>`;
        const note = m.note ? `<div class="small h-note">${fix(m.note)}<span class="mut">Agent's note:</span> ${esc(m.note)}</div>` : '';
        const nw = newV(ctx, v, [m.at, hs[0] && hs[0].at].filter(Boolean).sort().at(-1)) ? ' <span class="rf-new" title="New since you last looked">new</span>' : '';
        if (!hs.length) return `<div class="h-grp h-none" id="h-${esc(v)}" data-hseen="${esc(v)}"><div class="h-gh"><span class="h-fold h-nofold"><b>Version ${esc(vn(v))}</b>${nw}
          <span class="small mut"><span class="h-dot">· </span>published ${esc(when(m.at, m.t))} · no answers sent${m.items ? ` · ${pl(m.items, 'item', 'items')}, ${m.open} still open` : ''}</span></span>${eye}</div>${note}</div>`;
        const top = first && !q; first = false;
        const op = !!q || top !== S.open.has(v);
        return `<div class="h-grp" id="h-${esc(v)}" data-hseen="${esc(v)}"><div class="h-gh"><button class="h-fold" data-fold="${esc(v)}" aria-expanded="${op}">${icon('chev')}<b>Version ${esc(vn(v))}</b>${nw}
          <span class="small mut"><span class="h-dot">· </span>sent ${esc(when(hs[0].at, hs[0].t))} · ${pl(hs.length, 'answer', 'answers')}${DELIV[hs[0].dl] ? ` · ${DELIV[hs[0].dl]}` : ''}${m.items ? ` · ${pl(m.items, 'item', 'items')}, ${m.open} still open` : ''}${top ? ' · newest Send' : ''}</span></button>
          ${eye}</div>${note}
          ${op ? `<ul class="h-list">${hs.map(h => li(h, ctx)).join('')}</ul>` : ''}</div>`;
      }).join('') || (q ? '<p class="mut">No past answer matches.</p>' : '<p class="mut">No answers sent on this page yet.</p>');
      if (vers.length > S.nv) html += `<button class="btn sm" data-hmore>Show ${Math.min(20, vers.length - S.nv)} earlier versions</button>`;
      const wd = D.withdrawn.filter(w => !q || w.n === num || `${w.q} ${w.why}`.toLowerCase().includes(q));
      if (wd.length) {
        const op = S.wd || !!q;
        html += `<div class="h-grp"><button class="h-fold" data-wd aria-expanded="${op}">${icon('chev')}<b>Questions the agent withdrew</b> <span class="small mut">${pl(wd.length, 'question', 'questions')} · read-only</span></button>
          ${op ? `<ul class="h-list">${wd.slice(0, 80).map(w => `<li><span class="h-n">Question ${w.n} · version ${esc(vn(w.v))} · ${esc(w.t)}</span> ${esc(w.q)}<br><span class="mut small">Withdrawn: ${esc(w.why)}</span></li>`).join('')}</ul>${wd.length > 80 ? `<p class="small mut">${pl(wd.length - 80, 'more', 'more')}: search to narrow them.</p>` : ''}` : ''}</div>`;
      }
    }
    if (S.f !== 'q') {
      const all = D.plans.flatMap(p => p.revs.map((r, i) => ({p, r, i}))).sort((a, b) => b.r[1].localeCompare(a.r[1]) || a.p.t.localeCompare(b.p.t) || b.i - a.i)
        .filter(x => !q || `${x.p.t} ${x.r[2]}`.toLowerCase().includes(q));
      // a run of same-day revisions of one plan is one row with its count, as in the mock (#114); the eye opens the newest
      const lab = r => /^[A-Z0-9][A-Z0-9-]{5,}\b/.test(r[2] || '') ? '' : r[2] || '', revs = [];
      for (const x of all) {
        const g = revs.at(-1), l = lab(x.r);
        if (g && g.p === x.p && g.r[1] === x.r[1] && g.lo === x.i + 1) { g.lo = x.i; g.n++; if (l) g.labs.add(l); }
        else revs.push({...x, lo: x.i, n: 1, labs: new Set(l ? [l] : [])});
      }
      const op = S.f === 'ref' || S.ref || !!q;
      const rows = revs.slice(0, S.nref).map(x => `<div class="h-line">${icon(/checklist/i.test(x.p.t) ? 'check' : 'plan')}<span class="h-grow"><b>${esc(x.p.t)}</b> · ${x.n > 1 ? `revisions ${x.lo + 1} to ${x.i + 1} of ${x.p.revs.length} <span class="h-cnt">${x.n}</span>` : `revision ${x.i + 1} of ${x.p.revs.length}`}${x.labs.size ? ` · <span class="mut">${esc([...x.labs].join(', '))}</span>` : ''}</span>
        <span class="small mut">${esc(x.r[1])}</span><button class="ib" data-hp="${esc(x.p.id)}~${esc(x.r[0])}" title="Open this revision read-only" aria-label="Open ${esc(x.p.t)}, revision ${x.i + 1}, read-only">${icon('eye')}</button></div>`).join('');
      const more = revs.length > S.nref ? `<button class="btn sm" data-refmore>Show ${Math.min(60, revs.length - S.nref)} more</button>` : '';
      // a copy's findings audits and its Copy library head the list, each with its eye into Reference, as the mock shows Rebex's (#114, audit7 running 4)
      const ex = ((R && R.extras) || []).filter(x => (x.find || x.id === 'copy-library') && (!q || x.t.toLowerCase().includes(q)));
      const rb = ex.map(x => `<div class="h-line">${icon(x.find ? 'data' : 'text')}<span class="h-grow">${esc(x.t)} · ${x.find ? pl(x.find.items.length, 'finding', 'findings') : esc(String(x.m || '').split(' · ')[0])}</span>
        <button class="ib" data-href="${esc(x.id)}" title="Open it in Reference" aria-label="Open ${esc(x.t)} in Reference">${icon('eye')}</button></div>`).join('');
      html += S.f === 'ref' ? (rb + rows + more || '<p class="mut">No Reference changes match.</p>')
        : revs.length || rb ? `<div class="h-grp"><button class="h-fold" data-refall aria-expanded="${op}">${icon('chev')}<b>Reference changes</b> <span class="small mut">${[revs.length && `${pl(all.length, 'revision', 'revisions')} of ${pl(D.plans.length, 'plan', 'plans')}`, ex.length && pl(ex.length, 'audit or library', 'audits and libraries')].filter(Boolean).join(' · ')}</span></button>${op ? rb + rows + more : ''}</div>` : '';
    }
    box.innerHTML = html;
  }
  function li(h, ctx, ro) {
    const {esc} = ctx;
    const tag = h.ovr ? `<span class="h-ovr" tabindex="0">⤼ overruled<span class="h-tip" role="tooltip">The agent wrote “${esc(h.ovr[0])}”: ${esc(h.ovr[1])} Your answer stays here as you sent it.</span></span> ` : '';
    // a card answered twice: the older answer is his earlier pick; the newest, on a card still asked, offers Change (catalog 52);
    // the read-only version reader (ro) shows the answer without Change, as the mock does (r12 audit15 running 1)
    const newest = h.id && D.answers.find(x => x.id === h.id), old = newest && newest !== h;
    const ch = !ro && !old && h.ch ?` <button class="lk small" data-hchange="${esc(h.id)}" title="Pick again on its card in Questions; this answer stays here">Change</button>` : '';
    return `<li${old ? ' class="h-old"' : ''}>${h.n ? `<span class="h-n">Question ${h.n}</span> ` : ''}${tag}${esc(h.q)} → <b>${esc(h.a)}</b>${old ? ' <span class="small mut">· your earlier pick, changed since</span>' : ''}${ch}</li>`;
  }
  // a version published since he last looked carries Reference's "changed" mark until he opens it (catalog 68)
  const hFirst = ctx => { let b = ctx.prefs.get('h-first'); if (!b) { b = new Date(Date.now() - 14 * 864e5).toISOString().slice(0, 16); ctx.prefs.set('h-first', b); } return b; };
  const newV = (ctx, v, at) => !!at && String(at).replace(' ', 'T') > (ctx.prefs.get('h-seen', {})[v] || hFirst(ctx));
  const seeV = (ctx, v) => { const s = ctx.prefs.get('h-seen', {}); s[v] = new Date().toISOString().slice(0, 19); ctx.prefs.set('h-seen', s); };
  async function click(e, el, ctx) {
    const pt = e.target.closest('[data-cpt]');
    if (pt) {  // Move: this point takes the note; a marked point lists its notes; a bare one opens a new note (r12 audit16 frame 6)
      const v = pt.dataset.cpt;
      if (S.cmove) return moveC(el, ctx, v);
      S.ce = '';
      if (cnotes(v).length) { S.cn = ''; S.cspot = S.cspot === v ? '' : v; return draw(el, ctx); }
      S.cspot = ''; S.cn = S.cn === v ? '' : v;
      draw(el, ctx); return focusC(el);
    }
    const g = e.target.closest('[data-hseen]');  // reading a version clears its mark
    if (g && g.querySelector('.rf-new')) { seeV(ctx, g.dataset.hseen); g.querySelectorAll('.h-gh .rf-new').forEach(x => x.remove()); }
    const b = e.target.closest('button');
    if (!b) return;
    const ds = b.dataset, cn = id => allC().find(x => x.id === id);
    if (ds.hchange) return ctx.go('questions', 'q-' + ds.hchange);
    // the marker list and a sent note's lifecycle: the notes kit, as on every tab
    if (ds.spotx !== undefined) { S.cspot = ''; return draw(el, ctx); }
    if (ds.spotadd) { S.cspot = ''; S.ce = ''; S.cn = ds.spotadd; draw(el, ctx); return focusC(el); }
    if (ds.spotgo) { S.cspot = ''; S.hl = ds.spotgo; S.hlT = ''; draw(el, ctx); return litC(el); }
    const life = how => { const x = cn(ds.nclose || ds.nopen || ds.nreopen); return x && P.notes.set(ctx, x, how, ctx.api, async id => { S.cspot = ''; S.hl = id; S.hlT = ''; draw(el, ctx); litC(el); ctx.refreshChips(); }); };
    if (ds.nclose) return life('close');
    if (ds.nopen) return life('restore');
    if (ds.nreopen) return life('reopen');
    if (ds.nres) { const x = cn(ds.nres); return x && P.notes.goRes(ctx, x); }
    if (ds.nmove) { S.cmove = S.cmove === ds.nmove ? '' : ds.nmove; draw(el, ctx); if (S.cmove) ctx.toast('Click the point for this note · Esc cancels'); return; }
    if (b.hasAttribute('data-csave')) return saveC(el, ctx);
    if (ds.csavee) return editC(el, ctx, ds.csavee);
    if (ds.cned || ds.nedit) { S.cn = ''; S.ce = ds.cned || ds.nedit; draw(el, ctx); return focusC(el); }  // the kit's Edit on a sent one opens the same editor
    if (ds.cdel) { const n = cn(ds.cdel); if (n) { const back = await takeC(ctx, n); ctx.toast('Note removed', {undo: back}); } return; }
    if (ds.ccopy) return copyC(ctx, (cn(ds.ccopy) || {}).text || '', 'Note');
    if (ds.clink) return copyC(ctx, location.href.split('#')[0] + '#history/hn-' + ds.clink, 'Link to the note');
    if (b.hasAttribute('data-ccancel')) { if (S.ce) { S.ce = ''; return draw(el, ctx); } S.cn = ''; ctx.prefs.set('draft:hnote', null); return draw(el, ctx); }
    if (b.dataset.fold) { S.open.has(b.dataset.fold) ? S.open.delete(b.dataset.fold) : S.open.add(b.dataset.fold); draw(el, ctx); }
    else if (b.hasAttribute('data-wd')) { S.wd = !S.wd; draw(el, ctx); }
    else if (b.hasAttribute('data-refall')) { S.ref = !S.ref; draw(el, ctx); }
    else if (b.hasAttribute('data-hmore')) { S.nv += 20; draw(el, ctx); }
    else if (b.hasAttribute('data-refmore')) { S.nref += 60; draw(el, ctx); }
    else if (b.dataset.hv) ctx.go('history', b.dataset.hv);
    else if (b.dataset.hp) ctx.go('history', 'plan~' + b.dataset.hp);
    else if (b.dataset.href) ctx.go('reference', b.dataset.href);
  }

  function openView(el, ctx, anchor) {
    const {esc} = ctx, close = () => ctx.go('history');
    if (anchor.startsWith('plan~')) {
      const [, id, v] = anchor.split('~'), p = D.plans.find(x => x.id === id);
      const i = p ? p.revs.findIndex(r => r[0] === v) : -1;
      return P.viewVersion(el, ctx, {title: `${p ? p.t : id}, revision ${i + 1}${p ? ` of ${p.revs.length}` : ''}`, src: `plans/${encodeURIComponent(id)}/${encodeURIComponent(v)}.html`, onClose: close,
        before: p && p.revs[i] && p.revs[i][2] ? `<p class="small"><span class="mut">Agent's note on this revision:</span> ${esc(p.revs[i][2])}</p>` : ''});
    }
    // "<version>~<anchor>": a note's View resolution opens the version at that spot (r12 audit15 questions 3)
    const v = anchor.split('~')[0], at = anchor.slice(v.length + 1), m = D.versions[v] || {}, hs = D.answers.filter(h => h.v === v);
    S.wnOpen = null;
    P.viewVersion(el, ctx, {title: `Version ${vn(v)}`, src: `content?v=${encodeURIComponent(v)}`, onClose: close, at,
      before: `${m.note ? `<p class="small"><span class="mut">Agent's note on this version:</span> ${esc(m.note)}</p>` : ''}
        ${v !== D.current ? waitingNow(v, ctx) : ''}
        <div class="h-cols"><div><h3 class="h-ph">Its sections</h3><div class="h-secs"><p class="small mut">Loading…</p></div></div>
        <div><h3 class="h-ph">What you sent on it</h3><ul class="h-list">${hs.map(h => li(h, ctx, true)).join('') || '<li class="mut">No answers sent on this version.</li>'}</ul></div></div>`});
    el.querySelector('.hv-view').addEventListener('click', e => { const b = e.target.closest('[data-wnfold], [data-qgo]'); if (!b) return;
      // Questions scrolls to the card once its data is in; read it first so a cold load lands on the card too
      if (b.dataset.qgo) return ctx.data('questions').catch(() => {}).then(() => ctx.go('questions', 'q-' + b.dataset.qgo));
      S.wnOpen = b.getAttribute('aria-expanded') !== 'true'; el.querySelector('.h-wn').outerHTML = waitingNow(v, ctx); });
  }
  // an older version says which questions waiting now it held, and jumps to each in the current version (the mock's T8)
  function waitingNow(v, ctx) {
    const {esc, icon} = ctx, wq = D.waiting || [], cur = vn(D.current), hn = vn(v), inV = q => q.in.includes(v);
    if (!wq.length) return '';
    const op = S.wnOpen == null ? wq.some(inV) : S.wnOpen;  // open by default when this version held a question still waiting
    return `<div class="h-wn"><button class="h-fold" data-wnfold aria-expanded="${op}">${icon('chev')}<b>Questions waiting now</b>
        <span class="small mut">${wq.filter(inV).length} of ${wq.length} were in version ${esc(hn)}; you answer them in version ${esc(cur)}</span></button>
      ${op ? `<ul class="h-list h-wnl">${wq.map(q => `<li><span class="h-qn">Q ${esc(q.n)}</span><span class="h-grow">${esc(q.q)}</span>
        <span class="small mut">${inV(q) ? `in version ${esc(hn)} too` : `not in version ${esc(hn)}`} · asked in version ${esc(vn(q.from))}</span>
        <button class="lk small" data-qgo="${esc(q.id)}">Open it in version ${esc(cur)} ›</button></li>`).join('')}</ul>` : ''}</div>`;
  }

  P.tab({key: 'history', render, chip: async ctx => ({text: (await ctx.data('history')).count.toLocaleString(), title: 'answers you sent'})});
})();
