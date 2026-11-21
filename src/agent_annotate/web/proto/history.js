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
      f.onload = () => fit(f, ctx);
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
        go: () => { S.cn = d.v; S.q = ''; if (HE && HE.el.querySelector('#h-list')) { draw(HE.el, HE.ctx); focusC(HE.el); } else ctx.go('history'); },
        remove: () => { ctx.prefs.set('draft:hnote', null); if (S.cn === d.v) S.cn = ''; redrawH();
          return () => { ctx.prefs.set('draft:hnote', d); S.cn = d.v; redrawH(); }; }}] : [])(typedC(ctx))],
    sent: ctx => { CX = ctx; const l = [...TELL.keys()]; TELL.clear(); l.forEach(again); if (typedC(ctx)) { S.cn = ''; ctx.prefs.set('draft:hnote', null); redrawH(); } },
  });

  // The frame grows to its content, so the page has one scroll; pictures get their own size control.
  function fit(f, ctx) {
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
    const keyOf = img => (img.getAttribute('src') || '').split('?')[0];
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
    const close = () => { dlg.remove(); document.removeEventListener('keydown', key, true); if (back && back.focus) back.focus(); };
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
  let HE = null, QD = null, CN = [];  // HE: the tab on screen; QD: Questions' feed, whose notes hold saved chart notes; CN: saved this visit
  const CLAB = v => `Questions asked per version, version ${vn(v)}`;
  const typedC = c => { const d = c.prefs.get('draft:hnote', null); return d && (d.text || '').trim() ? d : null; };
  const redrawH = () => { if (HE && HE.el.querySelector('#h-list')) draw(HE.el, HE.ctx); };
  const focusC = el => { const t = el.querySelector('#h-nt'); if (t) { t.scrollIntoView({block: 'center'}); t.focus({preventScroll: true}); } };
  const qpv = () => Object.entries(D.versions || {}).filter(([v]) => /^v\d+$/.test(v)).sort((a, b) => +vn(a[0]) - +vn(b[0])).slice(-40);
  const cnotes = v => { const q = (QD && QD.notes) || []; return [...q, ...CN.filter(n => !q.some(x => x.id === n.id))].filter(n => n.anchor === 'chart:' + v); };
  function strip(ctx) {
    const {esc, icon} = ctx, vs = qpv();
    if (vs.length < 2) return '';
    const n = m => m.items || 0, mx = Math.max(1, ...vs.map(([, m]) => n(m))), X = i => 34 + i * 20, Y = k => 50 - k / mx * 42;
    const pts = vs.map(([v, m], i) => { const on = S.cn === v || cnotes(v).length > 0, t = `Version ${vn(v)}: ${pl(n(m), 'question', 'questions')}, ${m.open || 0} still open`;
      return `<circle data-cpt="${esc(v)}" cx="${X(i)}" cy="${Y(n(m)).toFixed(1)}" r="${on ? 5 : 3.5}" class="h-cpt${on ? ' on' : ''}" tabindex="0" role="button" aria-label="${esc(t)}. Write a note on it"><title>${esc(t)}</title></circle>`; }).join('');
    const notes = vs.flatMap(([v]) => cnotes(v).map(x => `<div class="h-cnote">${icon('note')}<span class="small mut">Version ${esc(vn(v))}</span> ${esc(x.text)}</div>`)).join('');
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
      CN.push({id: c.id, anchor: 'chart:' + v, label: CLAB(v), text: c.text || text});
      S.cn = ''; ctx.prefs.set('draft:hnote', null); draw(el, ctx); ctx.refreshChips();
      ctx.toast('Note saved', {undo: async () => { await ctx.api('api/comments/' + encodeURIComponent(c.id), undefined, 'DELETE'); CN = CN.filter(x => x.id !== c.id);
        if (QD) QD.notes = (QD.notes || []).filter(x => x.id !== c.id); redrawH(); ctx.refreshChips(); }});
    } catch (er) { ctx.toast(`The note was not saved: ${er.message}`); }
  }

  /* ---------- the tab ---------- */
  let D = null, R = null;
  async function render(el, ctx, anchor) {
    D = await ctx.data('history');
    // the copy's findings audits and Copy library, from Reference's own data; History never waits for it, the rows join when it arrives
    if (!R) ctx.data('reference').then(r => { R = r; if (el.querySelector('#h-list')) draw(el, ctx); }).catch(() => {});
    ctx.data('questions').then(q => { QD = q; if (el.querySelector('#h-list') && qpv().some(([v]) => cnotes(v).length)) draw(el, ctx); }).catch(() => {});
    const {esc, icon} = ctx;
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
      else if (e.target.dataset && e.target.dataset.cpt && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); e.target.dispatchEvent(new MouseEvent('click', {bubbles: true})); }
    };
    draw(el, ctx);
    if (S.cn && typedC(ctx)) focusC(el);
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
        if (!hs.length) return `<div class="h-grp h-none" id="h-${esc(v)}"><div class="h-gh"><span class="h-fold h-nofold"><b>Version ${esc(vn(v))}</b>
          <span class="small mut"><span class="h-dot">· </span>published ${esc(when(m.at, m.t))} · no answers sent${m.items ? ` · ${pl(m.items, 'item', 'items')}, ${m.open} still open` : ''}</span></span>${eye}</div>${note}</div>`;
        const top = first && !q; first = false;
        const op = !!q || top !== S.open.has(v);
        return `<div class="h-grp" id="h-${esc(v)}"><div class="h-gh"><button class="h-fold" data-fold="${esc(v)}" aria-expanded="${op}">${icon('chev')}<b>Version ${esc(vn(v))}</b>
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
  function li(h, ctx) {
    const {esc} = ctx;
    const tag = h.ovr ? `<span class="h-ovr" tabindex="0">⤼ overruled<span class="h-tip" role="tooltip">The agent wrote “${esc(h.ovr[0])}”: ${esc(h.ovr[1])} Your answer stays here as you sent it.</span></span> ` : '';
    return `<li>${h.n ? `<span class="h-n">Question ${h.n}</span> ` : ''}${tag}${esc(h.q)} → <b>${esc(h.a)}</b></li>`;
  }
  function click(e, el, ctx) {
    const pt = e.target.closest('[data-cpt]');
    if (pt) { S.cn = S.cn === pt.dataset.cpt ? '' : pt.dataset.cpt; draw(el, ctx); return focusC(el); }
    const b = e.target.closest('button');
    if (!b) return;
    if (b.hasAttribute('data-csave')) return saveC(el, ctx);
    if (b.hasAttribute('data-ccancel')) { S.cn = ''; ctx.prefs.set('draft:hnote', null); return draw(el, ctx); }
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
    const v = anchor, m = D.versions[v] || {}, hs = D.answers.filter(h => h.v === v);
    S.wnOpen = null;
    P.viewVersion(el, ctx, {title: `Version ${vn(v)}`, src: `content?v=${encodeURIComponent(v)}`, onClose: close,
      before: `${m.note ? `<p class="small"><span class="mut">Agent's note on this version:</span> ${esc(m.note)}</p>` : ''}
        ${v !== D.current ? waitingNow(v, ctx) : ''}
        <div class="h-cols"><div><h3 class="h-ph">Its sections</h3><div class="h-secs"><p class="small mut">Loading…</p></div></div>
        <div><h3 class="h-ph">What you sent on it</h3><ul class="h-list">${hs.map(h => li(h, ctx)).join('') || '<li class="mut">No answers sent on this version.</li>'}</ul></div></div>`});
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
