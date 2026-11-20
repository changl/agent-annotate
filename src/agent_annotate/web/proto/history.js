/* History tab: every past answer by version, read-only (#69, #75). Search also finds overruled, superseded,
   overridden and replaced answers, all under one "overruled" tag (#70, #117). Filters All, Questions, Reference (#114).
   The eye opens an older version read-only; Close returns; no Older / Newer bar, no arrow keys (#115, #116).
   Also defines Proto.viewVersion and Proto.picSizes, used by Pages & links too. */
(function () {
  'use strict';
  const P = window.Proto = window.Proto || {};
  const S = {q: '', f: 'all', nv: 20, open: new Set(), wd: false, ref: false, nref: 60};
  const pl = (n, one, many) => `${Number(n).toLocaleString()} ${n === 1 ? one : many}`;
  const vn = v => String(v || '').replace(/^v/, '');

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
    let told = false;
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
      box.innerHTML = `<div class="hv-err" role="alert">${icon('warn')}<div><b>This version could not load.</b> ${esc(why)} Nothing you wrote is lost.
        ${retried ? `<span class="small mut">Retried at ${at}: still failing.</span>` : ''}
        <div class="hv-acts"><button class="btn sm" data-retry>${icon('reload')} Retry</button>
        ${told ? `<span class="small h-ok">${icon('tick')} The agent is told with your next Send</span>` : `<button class="btn sm" data-tell>${icon('msg')} Tell the agent</button>`}${P.inertMark()}</div></div></div>`;
      box.querySelector('[data-retry]').onclick = () => load(true);
      const tell = box.querySelector('[data-tell]');
      if (tell) tell.onclick = () => { told = true; fail(why, retried); ctx.inert('The agent will be told with your next Send', () => { told = false; fail(why, retried); }); };
    }
    load(false);
  };

  // The frame grows to its content, so the page has one scroll; pictures get their own size control.
  function fit(f, ctx) {
    let doc;
    try { doc = f.contentDocument; } catch { return; }
    if (!doc) return;
    doc.documentElement.dataset.theme = document.documentElement.dataset.theme;
    P.picSizes(doc, ctx);
    const size = () => { f.style.height = Math.max(200, doc.documentElement.scrollHeight) + 'px'; };
    size();
    try { new ResizeObserver(size).observe(doc.body); } catch {}
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
        + '[data-theme=dark] .pp-size{color:#aaa}[data-theme=dark] .pp-size button[aria-pressed=true]{background:#eee;color:#111}';
      doc.head.appendChild(st);
    }
    const all = ctx.prefs.get('picsize', {});
    const keyOf = img => (img.getAttribute('src') || '').split('?')[0];
    const apply = (img, bar) => {
      const pct = all[keyOf(img)];
      img.style.width = pct ? `${Math.round((img.naturalWidth || img.width) * pct / 100)}px` : '';
      img.style.maxWidth = '100%'; img.style.height = 'auto';
      bar.querySelectorAll('[data-pct]').forEach(b => b.setAttribute('aria-pressed', String(+b.dataset.pct === pct)));
      bar.querySelector('[data-def]').hidden = !pct;
    };
    const add = img => {
      if (img.dataset.ppSized || !keyOf(img)) return;
      if ((img.naturalWidth || 0) < 160) return;  // icons and thumbnails keep their size
      img.dataset.ppSized = '1';
      const bar = doc.createElement('div');
      bar.className = 'pp-size';
      bar.innerHTML = `<span>This picture:</span>${SIZES.map(s => `<button type="button" data-pct="${s}">${s}%</button>`).join('')}<button type="button" data-def>As published</button>`;
      bar.onclick = e => {
        const b = e.target.closest('button'); if (!b) return;
        if (b.dataset.pct) all[keyOf(img)] = +b.dataset.pct; else delete all[keyOf(img)];
        ctx.prefs.set('picsize', all);
        apply(img, bar);
      };
      (img.closest('a, .qpinwrap') || img).after(bar);  // outside a note's pin box, so pins keep their spot
      apply(img, bar);
    };
    root.querySelectorAll('img').forEach(img => {
      img.loading = 'eager';  // the frame is as tall as its content, so a lazy picture would wait for nothing
      if (img.complete && img.naturalWidth) add(img); else img.addEventListener('load', () => add(img), {once: true});
    });
  };

  /* ---------- the tab ---------- */
  let D = null;
  async function render(el, ctx, anchor) {
    D = await ctx.data('history');
    const {esc, icon} = ctx;
    if (anchor) return openView(el, ctx, anchor);
    const chips = [['all', 'All', ''], ['q', 'Questions', 'q'], ['ref', 'Reference', 'ref']]
      .map(([k, t, i]) => `<button class="chipb" data-hf="${k}" aria-pressed="${S.f === k}">${i ? icon(i) : ''}${t}</button>`).join('');
    el.innerHTML = `<div class="h-wrap"><div class="h-bar"><input type="search" id="h-q" placeholder="Find a past decision" aria-label="Find a past decision" value="${esc(S.q)}">
      <span class="h-chips" role="group" aria-label="Show">${chips}</span><span class="spacer"></span>
      <span class="small mut">${pl(D.count, 'answer', 'answers')} in ${pl(D.sends, 'Send', 'Sends')} · read-only</span></div><div id="h-list"></div></div>`;
    const input = el.querySelector('#h-q');
    let t;
    input.oninput = () => { clearTimeout(t); t = setTimeout(() => { S.q = input.value.trim(); S.nv = 20; draw(el, ctx); }, 120); };
    el.querySelectorAll('[data-hf]').forEach(b => { b.onclick = () => { S.f = b.dataset.hf; el.querySelectorAll('[data-hf]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); draw(el, ctx); }; });
    el.querySelector('.h-wrap').onclick = e => click(e, el, ctx);
    draw(el, ctx);
  }

  const hay = h => (`${h.n} ${h.q} ${h.a}` + (h.ovr ? ` overruled ${h.ovr[0]} ${h.ovr[1]}` : '')).toLowerCase();
  function draw(el, ctx) {
    const {esc, icon} = ctx, q = S.q.toLowerCase(), num = /^\d{1,6}$/.test(q) ? +q : -1;
    const box = el.querySelector('#h-list');
    let html = '';
    if (S.f !== 'ref') {
      const list = q ? D.answers.filter(h => h.n === num || hay(h).includes(q)) : D.answers;
      const byV = new Map();
      for (const h of list) { if (!byV.has(h.v)) byV.set(h.v, []); byV.get(h.v).push(h); }
      const vers = [...byV];
      if (q) html += `<p class="small mut">${pl(list.length, 'match', 'matches')}</p>`;
      html += vers.slice(0, S.nv).map(([v, hs], i) => {
        const m = D.versions[v] || {}, op = !!q || (i === 0) !== S.open.has(v);
        return `<div class="h-grp" id="h-${esc(v)}"><div class="h-gh"><button class="h-fold" data-fold="${esc(v)}" aria-expanded="${op}">${icon('chev')}<b>Version ${esc(vn(v))}</b>
          <span class="small mut"><span class="h-dot">· </span>sent ${esc(hs[0].t)} · ${pl(hs.length, 'answer', 'answers')}${m.items ? ` · ${pl(m.items, 'item', 'items')}, ${m.open} still open` : ''}${i === 0 && !q ? ' · newest' : ''}</span></button>
          <button class="ib" data-hv="${esc(v)}" title="Open version ${esc(vn(v))} read-only" aria-label="Open version ${esc(vn(v))} read-only">${icon('eye')}</button></div>
          ${m.note ? `<div class="small h-note"><span class="mut">Agent's note:</span> ${esc(m.note)}</div>` : ''}
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
      const revs = D.plans.flatMap(p => p.revs.map((r, i) => ({p, r, i}))).sort((a, b) => b.r[1].localeCompare(a.r[1]) || b.i - a.i)
        .filter(x => !q || `${x.p.t} ${x.r[2]}`.toLowerCase().includes(q));
      const op = S.f === 'ref' || S.ref || !!q;
      const rows = revs.slice(0, S.nref).map(x => `<div class="h-line">${icon(/checklist/i.test(x.p.t) ? 'check' : 'plan')}<span class="h-grow"><b>${esc(x.p.t)}</b> · revision ${x.i + 1} of ${x.p.revs.length}${x.r[2] ? ` · <span class="mut">${esc(x.r[2])}</span>` : ''}</span>
        <span class="small mut">${esc(x.r[1])}</span><button class="ib" data-hp="${esc(x.p.id)}~${esc(x.r[0])}" title="Open this revision read-only" aria-label="Open ${esc(x.p.t)}, revision ${x.i + 1}, read-only">${icon('eye')}</button></div>`).join('');
      const more = revs.length > S.nref ? `<button class="btn sm" data-refmore>Show ${Math.min(60, revs.length - S.nref)} more</button>` : '';
      html += S.f === 'ref' ? (rows + more || '<p class="mut">No Reference changes match.</p>')
        : revs.length ? `<div class="h-grp"><button class="h-fold" data-refall aria-expanded="${op}">${icon('chev')}<b>Reference changes</b> <span class="small mut">${pl(revs.length, 'revision', 'revisions')} of ${pl(D.plans.length, 'plan', 'plans')}</span></button>${op ? rows + more : ''}</div>` : '';
    }
    box.innerHTML = html;
  }
  function li(h, ctx) {
    const {esc} = ctx;
    const tag = h.ovr ? `<span class="h-ovr" tabindex="0">⤼ overruled<span class="h-tip" role="tooltip">The agent wrote “${esc(h.ovr[0])}”: ${esc(h.ovr[1])} Your answer stays here as you sent it.</span></span> ` : '';
    return `<li>${h.n ? `<span class="h-n">Question ${h.n}</span> ` : ''}${tag}${esc(h.q)} → <b>${esc(h.a)}</b></li>`;
  }
  function click(e, el, ctx) {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.fold) { S.open.has(b.dataset.fold) ? S.open.delete(b.dataset.fold) : S.open.add(b.dataset.fold); draw(el, ctx); }
    else if (b.hasAttribute('data-wd')) { S.wd = !S.wd; draw(el, ctx); }
    else if (b.hasAttribute('data-refall')) { S.ref = !S.ref; draw(el, ctx); }
    else if (b.hasAttribute('data-hmore')) { S.nv += 20; draw(el, ctx); }
    else if (b.hasAttribute('data-refmore')) { S.nref += 60; draw(el, ctx); }
    else if (b.dataset.hv) ctx.go('history', b.dataset.hv);
    else if (b.dataset.hp) ctx.go('history', 'plan~' + b.dataset.hp);
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
    P.viewVersion(el, ctx, {title: `Version ${vn(v)}`, src: `content?v=${encodeURIComponent(v)}`, onClose: close,
      before: `${m.note ? `<p class="small"><span class="mut">Agent's note on this version:</span> ${esc(m.note)}</p>` : ''}
        <h3 class="h-ph">What you sent on it</h3><ul class="h-list">${hs.map(h => li(h, ctx)).join('') || '<li class="mut">No answers sent on this version.</li>'}</ul>
        ${v !== D.current ? `<p class="small mut">You answer today's questions in version ${esc(vn(D.current))}, in Questions.</p>` : ''}`});
  }

  P.tab({key: 'history', render, chip: async ctx => ({text: (await ctx.data('history')).count.toLocaleString(), title: 'answers you sent'})});
})();
