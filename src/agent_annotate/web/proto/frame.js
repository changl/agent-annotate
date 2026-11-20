/* Prototype frame: top bar, six tabs, area loading and the ctx every tab gets. Contract: README.md. */
(function () {
  'use strict';
  const P = window.Proto = window.Proto || {};
  const AREAS = ['questions', 'reference', 'running', 'history', 'links'];
  // Built-in order and defaults; an area's Proto.tab({key, ...}) fills in render and chip.
  const TABS = [
    {key: 'questions', label: 'Questions', icon: 'q', area: 'questions', tone: 'k-q'},
    {key: 'reference', label: 'Reference', icon: 'ref', area: 'reference', tone: 'k-ref'},
    {key: 'running', label: 'Running', icon: 'run', area: 'running', tone: 'k-run'},
    {key: 'analytics', label: 'Analytics', icon: 'an', area: 'running', tone: 'k-an'},
    {key: 'history', label: 'History', icon: 'hist', area: 'history', tone: 'k-hist'},
    {key: 'links', label: 'Pages & links', icon: 'pages', area: 'links', tone: 'k-pages'},
  ];
  const byKey = Object.fromEntries(TABS.map(t => [t.key, t]));
  P.tab = spec => {
    if (!spec || !byKey[spec.key]) return console.warn('Proto.tab: unknown key', spec && spec.key);
    Object.assign(byKey[spec.key], spec);
    if (started) { drawTabs(); if (current === spec.key) show(current, null); }
  };

  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const base = location.pathname.replace(/[^/]*$/, '');  // the page's directory URL, always ending in "/"
  async function api(path, body, method) {
    const opts = body === undefined && !method ? {cache: 'no-store'}
      : {method: method || 'POST', headers: {'Content-Type': 'application/json'}, body: body === undefined ? undefined : JSON.stringify(body)};
    const r = await fetch(base + path.replace(/^\//, ''), opts);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || ('HTTP ' + r.status));
    return data;
  }
  // Today's page API, as the live shell calls it. Writes land in this copy only; delivery is sandboxed.
  Object.assign(api, {
    meta: () => api('current.meta.json'), comments: () => api('comments.json'), project: () => api('api/project'),
    history: () => api('api/history'), board: () => api('api/board'), identity: () => api('api/identity'),
    capabilities: () => api('api/capabilities'), delivery: () => api('api/delivery'), categories: () => api('api/categories'),
    seen: () => api('api/seen'), readState: () => api('api/read-state'), copy: () => api('api/copy'),
  });
  const cache = {};
  const data = (area, fresh) => (!fresh && cache[area]) || (cache[area] = api(`proto/data/${area}.json`).catch(e => { delete cache[area]; throw e; }));
  const prefs = {
    get(k, d) { try { const v = JSON.parse(localStorage.getItem('annotate-proto:' + k) || 'null'); return v == null ? d : v; } catch { return d; } },
    set(k, v) { try { localStorage.setItem('annotate-proto:' + k, JSON.stringify(v)); } catch {} },
  };

  let toastTimer;
  function toast(msg, opts = {}) {
    const el = document.getElementById('p-toast');
    clearTimeout(toastTimer);
    el.innerHTML = `<div class="p-toast" role="status"><span>${esc(msg)}</span>${opts.inert ? P.inertMark() : ''}${opts.undo ? '<button class="lk" data-undo>Undo</button>' : ''}</div>`;
    const undo = el.querySelector('[data-undo]');
    if (undo) undo.onclick = () => { el.innerHTML = ''; opts.undo(); };
    toastTimer = setTimeout(() => { el.innerHTML = ''; }, opts.undo ? 9000 : 5000);
  }
  P.inertMark = () => '<span class="p-inert" title="This prototype never reaches an agent, Orca, Windmill or the board">prototype: not sent</span>';
  // An action that would reach a real agent or system: look done, say so, offer Undo, reach nothing.
  const inert = (msg, undo) => toast(msg, {inert: true, undo: undo || (() => {})});

  const phoneQ = matchMedia('(max-width: 600px)');
  let current = null, started = false;
  const ctx = {
    base, api, data, prefs, esc, toast, inert,
    icon: (n, l) => P.icon(n, l),
    go(tab, anchor) { location.hash = tab + (anchor ? '/' + encodeURIComponent(anchor) : ''); },
    get phone() { return phoneQ.matches; },
    refreshChips: () => drawTabs(),
  };
  P.ctx = ctx;

  function drawTabs() {
    const nav = document.getElementById('p-tabs');
    nav.innerHTML = TABS.map(t => `<button class="tab ${t.tone}" role="tab" data-tab="${t.key}" aria-selected="${t.key === current}">${P.icon(t.icon)}<span class="tl">${esc(t.label)}</span><span class="ct" data-chip="${t.key}" hidden></span></button>`).join('');
    nav.querySelectorAll('[data-tab]').forEach(b => { b.onclick = () => ctx.go(b.dataset.tab); });
    for (const t of TABS) if (t.chip) Promise.resolve().then(() => t.chip(ctx)).then(c => {
      const el = nav.querySelector(`[data-chip="${t.key}"]`);
      if (!el || c == null || c === '') return;
      const v = typeof c === 'object' ? c : {text: c};
      el.textContent = v.text; el.className = 'ct ' + (v.tone || ''); el.hidden = false;
      if (v.title) el.title = v.title;
    }).catch(e => console.warn('chip', t.key, e));
  }

  function show(key, anchor) {
    const t = byKey[key] || TABS[0];
    current = t.key;
    document.querySelectorAll('#p-tabs [data-tab]').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === current)));
    const el = document.getElementById('p-main');
    el.className = 'p-main area-' + t.area + ' tab-' + t.key;
    if (!t.render) {
      el.innerHTML = `<div class="p-empty">${P.icon(t.icon)}<p>${esc(t.label)}: not built yet.</p></div>`;
      if (t.key === 'questions') questionsPreview(el);
      return;
    }
    el.innerHTML = '';
    Promise.resolve().then(() => t.render(el, ctx, anchor)).then(() => {
      const target = anchor && document.getElementById(anchor);
      if (target) target.scrollIntoView({block: 'start'});
    }).catch(e => { el.innerHTML = `<div class="p-empty">${P.icon('warn')}<p>${esc(t.label)} failed to draw: ${esc(e.message)}</p></div>`; console.error(e); });
  }
  // Until the questions area registers: this version's real questions, read through today's API.
  async function questionsPreview(el) {
    const [meta, store] = await Promise.all([api.meta(), api.comments()]);
    const qs = Object.values(store.anchors || {}).flat()
      .filter(c => c.decision_request && c.version === meta.current && !c.parent_id);
    el.insertAdjacentHTML('beforeend', `<ul class="p-qlist">${qs.map(c => `<li><span class="dot ${c.decision ? 'st-done' : 'st-waiting'}"></span>${esc(c.decision_request.prompt || c.text)}</li>`).join('')}</ul>`);
  }
  function route() {
    const [key, anchor] = location.hash.replace(/^#/, '').split('/');
    show(byKey[key] ? key : prefs.get('tab', 'questions'), anchor ? decodeURIComponent(anchor) : null);
    prefs.set('tab', current);
  }

  // Theme: light, dark or system, shared with today's page through annotate:theme.
  const THEMES = ['system', 'light', 'dark'];
  function applyTheme(mode) {
    const dark = mode === 'dark' || (mode === 'system' && matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    const b = document.getElementById('p-theme');
    b.innerHTML = P.icon(mode === 'system' ? 'sys' : mode === 'dark' ? 'moon' : 'sun');
    b.title = b.ariaLabel = `Theme: ${mode}`;
  }
  function theme() { try { const t = localStorage.getItem('annotate:theme'); return THEMES.includes(t) ? t : 'system'; } catch { return 'system'; } }

  const load = (tag, attrs) => new Promise(done => {
    const el = Object.assign(document.createElement(tag), attrs);
    el.onload = done; el.onerror = () => { el.remove(); done(); };  // an area with no file yet is fine
    document.head.appendChild(el);
  });

  async function start() {
    document.getElementById('p-reload').innerHTML = P.icon('reload');
    document.getElementById('p-reload').onclick = () => { for (const k in cache) delete cache[k]; drawTabs(); route(); };
    applyTheme(theme());
    document.getElementById('p-theme').onclick = () => {
      const next = THEMES[(THEMES.indexOf(theme()) + 1) % THEMES.length];
      try { localStorage.setItem('annotate:theme', next); } catch {}
      applyTheme(next);
    };
    api.meta().then(m => {
      document.getElementById('p-name').textContent = m.name || 'Prototype';
      document.title = (m.name || 'Prototype') + ' · Agent Annotate';
    }).catch(() => {});
    await Promise.all(AREAS.flatMap(a => [load('link', {rel: 'stylesheet', href: `proto/${a}.css`}), load('script', {src: `proto/${a}.js`})]));
    started = true;
    drawTabs();
    route();
    addEventListener('hashchange', route);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
