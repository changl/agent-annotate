// ── annotate: one page per project ──────────────────────────────────────
// The page has the tabs Review · Library · Findings · Plans (each shown when
// the project has that kind of content) and, when the owner declared one, a
// "Linked pages" tab. They switch views in place on one URL and share one
// feedback rail, one History, one Send and one set of needs-you and unread
// counts (computed by the server, ./api/categories, so every device agrees).
// Review and Plans are documents served by the accepted shell (shell.js,
// window.AnnotateDocs); Library and Findings are views of this page
// (library.js, findings.js). This file holds the shared helpers (AAUI), the
// page core (AA), the header tabs, the rail, the one Send and Linked pages.

// ── Shared helpers ──────────────────────────────────────────────────────
(function () {
  'use strict';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  function fmtTs(iso) {
    if (!iso) return '';
    try { return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); }
    catch { return String(iso).slice(0, 16).replace('T', ' '); }
  }
  // Lucide icons (ISC License, (c) Lucide Icons and Contributors)
  const ICON = {
    pencil: '<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/>',
    chevDown: '<path d="m6 9 6 6 6-6"/>',
    chevLeft: '<path d="m15 18-6-6 6-6"/>',
    message: '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
    undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11"/>',
    redo: '<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5A5.5 5.5 0 0 0 4 14.5A5.5 5.5 0 0 0 9.5 20H13"/>',
    link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    list: '<line x1="8" x2="21" y1="6" y2="6"/><line x1="8" x2="21" y1="12" y2="12"/><line x1="8" x2="21" y1="18" y2="18"/><line x1="3" x2="3.01" y1="6" y2="6"/><line x1="3" x2="3.01" y1="12" y2="12"/><line x1="3" x2="3.01" y1="18" y2="18"/>',
    olist: '<line x1="10" x2="21" y1="6" y2="6"/><line x1="10" x2="21" y1="12" y2="12"/><line x1="10" x2="21" y1="18" y2="18"/><path d="M4 6h1v4"/><path d="M4 10h2"/><path d="M6 18H4c0-1 2-2 2-3s-1-1.5-2-1"/>',
    quote: '<path d="M3 21c3 0 7-1 7-8V5c0-1.25-.756-2.017-2-2H4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2 1 0 1 0 1 1v1c0 1-1 2-2 2s-1 .008-1 1.031V20c0 1 0 1 1 1z"/><path d="M15 21c3 0 7-1 7-8V5c0-1.25-.757-2.017-2-2h-4c-1.25 0-2 .75-2 1.972V11c0 1.25.75 2 2 2h.75c0 2.25.25 4-2.75 4v3c0 1 0 1 1 1z"/>',
    plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
    external: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    image: '<rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>',
    rotate: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
  };
  const ico = (n) => '<svg class="i" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' + (ICON[n] || '') + '</svg>';

  // A rail section in the accepted style (B2: sections, 2.20.3 words).
  function section(key, label, count, bodyHtml, opts) {
    opts = opts || {};
    const open = opts.open !== false;
    const id = 'sec-' + (opts.scope ? opts.scope + '-' : '') + key;
    const badge = count == null ? '' : `<span class="badge badge-sm ${opts.badge || 'badge-ghost'}">${count}</span>`;
    return `<section class="sec ${opts.cls || ''}" data-section="${esc(key)}"><button type="button" class="sec-hdr" data-sec-toggle="${esc(key)}" aria-expanded="${open}" aria-controls="${esc(id)}">${ico('chevDown')}<span>${esc(label)}</span>${badge}</button><div class="sec-body" id="${esc(id)}"${open ? '' : ' hidden'}>${bodyHtml}</div></section>`;
  }
  function wireSections(root, store) {
    root.querySelectorAll('[data-sec-toggle]').forEach(b => b.addEventListener('click', () => {
      const body = document.getElementById(b.getAttribute('aria-controls'));
      const open = b.getAttribute('aria-expanded') !== 'true';
      b.setAttribute('aria-expanded', String(open));
      body.hidden = !open;
      if (store) store(b.dataset.secToggle, open);
    }));
  }
  // Word-level difference (added underlined, removed struck).
  function diffWords(a, b) {
    const x = String(a || '').split(/(\s+)/), y = String(b || '').split(/(\s+)/);
    const n = x.length, m = y.length;
    if (n * m > 200000) return '<del>' + esc(a) + '</del> <ins>' + esc(b) + '</ins>';
    const t = Array.from({ length: n + 1 }, () => new Int32Array(m + 1));
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) t[i][j] = x[i] === y[j] ? t[i + 1][j + 1] + 1 : Math.max(t[i + 1][j], t[i][j + 1]);
    let i = 0, j = 0, out = '', del = '', ins = '';
    const flush = () => { out += del.trim() ? '<del>' + esc(del) + '</del>' : esc(del); out += ins.trim() ? '<ins>' + esc(ins) + '</ins>' : esc(ins); del = ins = ''; };
    while (i < n && j < m) {
      if (x[i] === y[j]) { flush(); out += esc(y[j]); i++; j++; }
      else if (t[i + 1][j] >= t[i][j + 1]) del += x[i++];
      else ins += y[j++];
    }
    while (i < n) del += x[i++];
    while (j < m) ins += y[j++];
    flush();
    return out;
  }
  const newId = () => Math.random().toString(16).slice(2, 14) + Date.now().toString(16);
  const isTyping = (t) => !!(t && t.closest && (t.isContentEditable || t.closest('textarea, input, select, [contenteditable="true"]')));
  // Per-viewer conveniences only (open groups, the selected item).
  const local = {
    get(k, d) { try { const v = JSON.parse(localStorage.getItem('annotate:' + location.pathname + ':' + k) || 'null'); return v == null ? d : v; } catch { return d; } },
    set(k, v) { try { localStorage.setItem('annotate:' + location.pathname + ':' + k, JSON.stringify(v)); } catch {} },
  };
  async function api(path, body) {
    const r = await fetch(path, body === undefined ? { cache: 'no-store' }
      : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || ('HTTP ' + r.status));
    return data;
  }

  window.AAUI = { esc, fmtTs, ico, section, wireSections, diffWords, newId, isTyping, local, api };
})();

// ── The page core: tabs, providers, counts, router ──────────────────────
(function () {
  'use strict';
  const UI = window.AAUI;
  const DOCS = () => window.AnnotateDocs;
  const ALL_TABS = [
    { id: 'review', label: 'Review', kind: 'doc', title: 'Decisions and status: the document with its feedback rail' },
    { id: 'library', label: 'Library', sub: 'Copy and policies', title: 'Copy and policies: edit each item, comment on it, see its history' },
    { id: 'findings', label: 'Findings', sub: 'Audits and recommendations', title: 'Audit findings and recommendations, kept until each one is done' },
    { id: 'plans', label: 'Plans', kind: 'doc', title: 'Plans and research: every revision, with inline comments' },
  ];
  // A tab exists when the project has that kind of content (Review always).
  function tabs() {
    const cats = DOCS() && DOCS().categories();
    if (!cats) return ALL_TABS.filter(t => t.id === 'review');
    const on = new Set(cats.categories.filter(c => c.available).map(c => c.id));
    return ALL_TABS.filter(t => t.id === 'review' || on.has(t.id));
  }
  const tab = (id) => tabs().find(t => t.id === id);
  const isDoc = (id) => !!(ALL_TABS.find(t => t.id === id) || {}).kind;

  // ── Providers ──────────────────────────────────────────────────────────
  // Library and Findings register pending() → send lines, show(params),
  // hide(), history(el), shortcut(e). Review and Plans are the shell's.
  const providers = {};
  function provider(id, p) { providers[id] = p; changed(); }

  // The one count model: the server's counts per tab (needs you, waiting,
  // unread); what each tab would send is counted here, drafts included.
  const ZERO = { needs: 0, unread: 0, pending: 0, waiting: 0 };
  function sendCount(id) {
    const d = DOCS();
    try {
      if (isDoc(id)) return d && d.docs.includes(id) ? d.sendables(id).total : 0;
      const p = providers[id];
      return p && p.pending ? p.pending().length : 0;
    } catch (e) { console.warn('[annotate] send count', id, e); return 0; }
  }
  function counts() {
    const cats = DOCS() && DOCS().categories();
    const out = {};
    ALL_TABS.forEach(t => {
      const c = cats && cats.categories.find(x => x.id === t.id);
      let k = c ? c.counts : null;
      // UI-26 (final/): a document shown at an older version or revision
      // counts that version's cards, as its rail does.
      const d = DOCS();
      if (k && isDoc(t.id) && d && d.docs.includes(t.id) && d.olderShown && d.olderShown(t.id)) {
        const own = d.counts(t.id);
        k = Object.assign({}, k, { needs_you: own.needs, unread: own.unread, waiting: own.waiting });
      }
      out[t.id] = Object.assign({}, ZERO, k ? { needs: k.needs_you, unread: k.unread, waiting: k.waiting } : {},
        { pending: k ? sendCount(t.id) : 0, known: !!k });
    });
    return out;
  }

  // One change notification for the whole page; renders once per frame.
  const listeners = [];
  let scheduled = false;
  function changed() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      const k = counts();
      listeners.forEach(fn => { try { fn(k); } catch (e) { console.error(e); } });
    });
  }
  function onChange(fn) { listeners.push(fn); }

  // ── Router ─────────────────────────────────────────────────────────────
  let view = null;
  let projectTitle = '';
  const versions = {}; // the version on screen per document, this visit
  const params = () => new URLSearchParams(location.hash.replace(/^#/, ''));
  function go(p, opts) {
    const q = new URLSearchParams();
    Object.entries(p).forEach(([k, v]) => { if (v != null && v !== '') q.set(k, v); });
    const h = '#' + q.toString();
    if (opts && opts.replace) { history.replaceState(null, '', h); route(); }
    else if (location.hash === h) route();
    else location.hash = h;
  }
  // The shell reports a version switch; it becomes part of the URL.
  function noteVersion(doc, v) {
    versions[doc] = v;
    const p = params();
    if ((p.get('view') || view) === doc) { p.set('view', doc); p.set('v', v); history.replaceState(null, '', '#' + p.toString()); }
  }
  function versionFor(doc) {
    const p = params();
    if ((p.get('view') || UI.local.get('view', 'review')) === doc && p.get('v')) return p.get('v');
    return null;
  }
  // The content title row: "Review · Version v75", "Plans · Version v6".
  function docTitle(doc, text) {
    if (doc !== view) return;
    const sub = document.getElementById('view-hd-sub-doc');
    if (sub) sub.textContent = text;
    renderPlanPicker();
  }
  function renderPlanPicker() {
    const pick = document.getElementById('view-hd-plan');
    const plans = DOCS() ? DOCS().plans() : [];
    pick.hidden = view !== 'plans' || plans.length < 2;
    if (pick.hidden) return;
    const cur = DOCS().planId();
    pick.innerHTML = plans.map(p => `<option value="${UI.esc(p.id)}"${p.id === cur ? ' selected' : ''}>${UI.esc(p.title || p.id)}</option>`).join('');
  }
  function setTitle(title) {
    projectTitle = title || projectTitle;
    const t = tab(view);
    document.title = (projectTitle || 'annotate') + (view ? ' · ' + (t ? t.label : 'Linked pages') : '');
  }
  function showPane(id) {
    document.getElementById('frame-area').hidden = !isDoc(id);
    ['library', 'findings', 'linked'].forEach(v => { const el = document.getElementById('view-' + v); if (el) el.hidden = v !== id; });
    document.body.dataset.view = id;
  }
  let routing = Promise.resolve();
  function route() {
    routing = routing.then(doRoute, doRoute);
    return routing;
  }
  async function doRoute() {
    const p = params();
    if (p.get('theme') === 'light' || p.get('theme') === 'dark') document.dispatchEvent(new CustomEvent('annotate:set-theme', { detail: p.get('theme') }));
    let next = p.get('view') || UI.local.get('view', 'review');
    if (!tab(next) && !(next === 'linked' && AA.linked)) next = 'review';
    if (next === 'plans' && p.get('plan') && p.get('plan') !== DOCS().planId()) {
      await DOCS().selectPlan(p.get('plan'));
      return;
    }
    const prev = view;
    view = next;
    UI.local.set('view', next);
    if (prev && prev !== next && providers[prev] && providers[prev].hide) providers[prev].hide();
    // A new tab starts without the previous tab's Send summary open.
    if (prev && prev !== next && p.get('send') !== '1' && AA.send.isOpen()) AA.send.close();
    // Phone: a new tab starts with its content, not with the rail's sheet.
    if (prev && prev !== next && DOCS().isMobileLayout()) DOCS().setMobileSheetOpen(false);
    showPane(next);
    AA.rail.setView(next);
    setTitle();
    if (isDoc(next)) {
      document.getElementById('view-hd-name').textContent = tab(next).label;
      await DOCS().activate(next, p.get('v') || versions[next] || null);
      if (view !== next) return;
    } else {
      DOCS().park();
      const pr = providers[next];
      if (pr && pr.show) await pr.show(p);
    }
    if (p.get('send') === '1') AA.send.open();
    if (p.get('sumedit') && isDoc(next)) { DOCS().sumEdit(p.get('sumedit')); AA.send.render(); }
    if (p.get('history')) AA.rail.setFilter(p.get('history'));
    if (p.get('tab') && isDoc(next)) AA.rail.setTab(p.get('tab'));
    AA.header.openMenu(p.get('cats') === 'open');
    changed();
    document.body.dataset.ready = '1';
  }

  // A/F and the number keys on Library and Findings (the shell forwards).
  function shortcut(e) {
    const pr = providers[view];
    if (pr && pr.shortcut) pr.shortcut(e);
  }

  window.AA = {
    ALL_TABS, get TABS() { return tabs(); }, tab, isDoc, provider, providers, counts, changed, onChange,
    go, route, params, noteVersion, versionFor, docTitle, setTitle, shortcut,
    get view() { return view; },
    get linkedPages() { const c = DOCS() && DOCS().categories(); return (c && c.linked_pages) || []; },
    get linked() { return this.linkedPages.length > 0; },
    esc: UI.esc,
    // Filled below by the header, the rail and the Send.
    header: null, rail: null, send: null,
  };

  async function start() {
    document.getElementById('view-hd-plan').addEventListener('change', (e) => DOCS().selectPlan(e.target.value));
    window.addEventListener('hashchange', () => {
      if (new URLSearchParams(location.hash.slice(1)).has('review')) return; // the shell reloads for a review link
      route();
    });
    document.addEventListener('annotate:store', changed);
    await DOCS().loaded;
    route();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();

// ── The header's tabs ───────────────────────────────────────────────────
// The project name sits in a fixed-width block (Chang: tabs must start at
// the same place on every tab), then the tabs, each with its red "needs
// you" count, then the project's linked pages (an exception the owner
// declared). On a phone the tabs become one menu with a sentence per tab.
(function () {
  'use strict';
  const AA = window.AA, esc = AA.esc;
  const ICON_DOWN = '<svg class="i" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="m6 9 6 6 6-6"/></svg>';
  const nav = document.getElementById('aa-tabs');
  const menu = document.getElementById('aa-tabs-menu');

  function sentence(k) {
    if (!k.known) return { text: 'Loading…' };
    const parts = [];
    let needs = false;
    if (k.needs) { parts.push(k.needs + (k.needs === 1 ? ' needs you' : ' need you')); needs = true; }
    else if (k.pending) parts.push(k.pending + ' ready to send');
    else if (k.waiting) parts.push(k.waiting + ' waiting on agent');
    else parts.push('Nothing needs you');
    if (k.unread) parts.push(k.unread + ' unread');
    return { text: parts.join(' · '), needs };
  }
  const href = (id) => '#view=' + id;

  function render(counts) {
    const cur = AA.view;
    const linked = AA.linkedPages;
    nav.innerHTML = '<div class="tabs tabs-border">' + AA.TABS.map(t => {
      const k = counts[t.id], s = sentence(k);
      const badge = k.needs ? ` <span class="badge badge-error badge-xs" aria-hidden="true">${k.needs}</span>` : '';
      return `<a class="tab${t.id === cur ? ' tab-active' : ''}" href="${href(t.id)}" data-view="${t.id}"${t.id === cur ? ' aria-current="page"' : ''} title="${esc(t.title)} · ${esc(s.text)}" aria-label="${esc(t.label + ', ' + s.text)}">${esc(t.label)}${badge}</a>`;
    }).join('') + (linked.length ? `<a class="tab aa-linked-tab${cur === 'linked' ? ' tab-active' : ''}" href="${href('linked')}" data-view="linked"${cur === 'linked' ? ' aria-current="page"' : ''} title="Separate pages the owner declared for this project">Linked pages <span class="badge badge-ghost badge-xs" aria-hidden="true">${linked.length}</span></a>` : '') + '</div>';

    const curTab = AA.tab(cur);
    const curLabel = curTab ? curTab.label : 'Linked pages';
    const curNeeds = curTab ? counts[cur].needs : 0;
    const others = AA.TABS.filter(t => t.id !== cur).reduce((n, t) => n + counts[t.id].needs, 0);
    const open = menu.open;
    menu.innerHTML = `<summary aria-label="Tab: ${esc(curLabel)}${others ? ', ' + others + ' need you elsewhere' : ''}">${esc(curLabel)}${curNeeds ? ` <span class="badge badge-error badge-xs">${curNeeds}</span>` : ''}${ICON_DOWN}</summary>
      <div class="aa-tabs-list" role="list">${AA.TABS.map(t => {
        const s = sentence(counts[t.id]);
        return `<a role="listitem" href="${href(t.id)}" data-view="${t.id}"${t.id === cur ? ' aria-current="page"' : ''}><span class="aa-tab-name">${esc(t.label)}</span><span class="aa-tab-state${s.needs ? ' is-needs' : ''}">${esc(s.text)}</span></a>`;
      }).join('')}${linked.length ? `<a role="listitem" href="${href('linked')}" data-view="linked" class="aa-linked-tab"${cur === 'linked' ? ' aria-current="page"' : ''}><span class="aa-tab-name">Linked pages</span><span class="aa-tab-state">${linked.length} separate page${linked.length === 1 ? '' : 's'} declared for this project</span></a>` : ''}</div>`;
    menu.open = open;
  }
  function openMenu(on) { menu.open = !!on; }
  menu.addEventListener('click', (e) => { if (e.target.closest('a[href]')) menu.open = false; });
  document.addEventListener('click', (e) => { if (menu.open && !menu.contains(e.target)) menu.open = false; });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && menu.open) { menu.open = false; menu.querySelector('summary').focus(); } });

  AA.onChange(render);
  AA.header = { render: () => render(AA.counts()), openMenu, sentence };
})();

// ── The one feedback rail ───────────────────────────────────────────────
// One rail for the whole page, with the accepted tabs Feedback · Documents ·
// History. Feedback shows the tab on screen: the shell's cards for Review
// and Plans, the selected item's feedback in Library, the findings in
// Findings. History is one list for the project; each part carries its
// tab's tag, and it shows the tab on screen unless "All tabs" is chosen.
// Sent rounds (recorded by the server) sit at the top, each line tagged.
(function () {
  'use strict';
  const AA = window.AA, UI = window.AAUI, esc = UI.esc;
  const $ = (s) => document.querySelector(s);
  const FEEDBACK_PANE = { review: 'drawer-body', plans: 'drawer-body', library: 'rail-library', findings: 'rail-findings', linked: 'rail-linked' };
  const ALL_PANES = ['drawer-body', 'rail-library', 'rail-findings', 'rail-linked', 'documents-body', 'history-body'];
  let railTab = 'feedback';
  let view = 'review';
  let filter = null; // null = the tab on screen; 'all' = every tab

  function setTab(t) {
    if (!['feedback', 'documents', 'history'].includes(t)) t = 'feedback';
    if (t === 'documents' && ($('#tab-documents').hidden || !AA.isDoc(view))) t = 'feedback';
    railTab = t;
    document.querySelectorAll('#drawer-tabs [role="tab"]').forEach(el => {
      const on = el.dataset.tab === t;
      el.classList.toggle('tab-active', on);
      el.setAttribute('aria-selected', on ? 'true' : 'false');
      el.tabIndex = on ? 0 : -1;
    });
    const pane = t === 'feedback' ? FEEDBACK_PANE[view] : t === 'documents' ? 'documents-body' : 'history-body';
    ALL_PANES.forEach(id => { const el = document.getElementById(id); if (el) el.hidden = id !== pane; });
    $('#tab-feedback').setAttribute('aria-controls', FEEDBACK_PANE[view]);
    document.dispatchEvent(new CustomEvent('annotate:rail-tab', { detail: t }));
    if (t === 'history') renderHistory();
  }
  function setView(v) {
    view = v;
    filter = null;
    // The Documents tab belongs to a document (its links module).
    if (!AA.isDoc(v)) $('#tab-documents').hidden = true;
    setTab(railTab);
    badges(AA.counts());
  }
  function setFilter(f) { filter = f === 'all' ? 'all' : null; renderHistory(); }

  // Feedback tab badge, collapsed-rail strip and phone button for the tab on
  // screen (the shell keeps them for Review and Plans as it always did).
  function badges(counts) {
    if (AA.isDoc(view)) return;
    const k = counts[view] || { needs: 0, unread: 0 };
    const tb = $('#tab-feedback-n');
    tb.textContent = String(k.needs); tb.hidden = !k.needs;
    const strip = $('#drawer-strip-unread');
    strip.textContent = String(k.needs); strip.style.display = k.needs ? '' : 'none';
    const fab = $('#mobile-fab');
    if (fab) fab.title = (k.needs ? k.needs + ' need you' : 'Nothing needs you') + (k.unread ? ', ' + k.unread + ' unread' : '') + ' — open feedback';
  }

  // ── History ────────────────────────────────────────────────────────────
  function shownTabs() {
    if (filter === 'all') return AA.TABS.map(t => t.id);
    return AA.tab(view) ? [view] : [];
  }
  function renderHistory() {
    const body = $('#history-body');
    if (!body) return;
    const cur = AA.tab(view);
    const f = $('#hist-filter');
    const on = (yes) => yes ? ' btn-soft btn-primary' : ' btn-ghost';
    f.innerHTML = `<div class="join">${cur ? `<button type="button" class="btn btn-xs join-item${on(filter !== 'all')}" data-hist-filter="tab" aria-pressed="${filter !== 'all'}">${esc(cur.label)}</button>` : ''}<button type="button" class="btn btn-xs join-item${on(filter === 'all' || !cur)}" data-hist-filter="all" aria-pressed="${filter === 'all' || !cur}">All tabs</button></div>`;
    f.querySelectorAll('[data-hist-filter]').forEach(b => b.addEventListener('click', () => setFilter(b.dataset.histFilter)));
    const shown = cur ? shownTabs() : AA.TABS.map(t => t.id);
    const docs = window.AnnotateDocs ? window.AnnotateDocs.docs : [];
    body.querySelectorAll('.hist-cat').forEach(sec => {
      const on = shown.includes(sec.dataset.cat) && (!AA.isDoc(sec.dataset.cat) || docs.includes(sec.dataset.cat));
      sec.hidden = !on;
      if (!on) return;
      const p = AA.providers[sec.dataset.cat];
      if (AA.isDoc(sec.dataset.cat)) {
        window.AnnotateDocs.renderHistoryInto(sec.dataset.cat);
        // "All tabs": another document's versions show its latest five.
        clip(sec.querySelector('.vrail-body'), sec.dataset.cat !== view);
      } else if (p && p.history) p.history(sec.querySelector('.hist-cat-body'));
    });
    renderSent(shown);
  }
  const unclipped = new Set();
  function clip(list, on) {
    if (!list) return;
    const cat = list.id.replace('vrail-body-', '');
    const rows = list.querySelectorAll('.vrow').length;
    const clipped = on && rows > 5 && !unclipped.has(cat);
    list.classList.toggle('is-clipped', clipped);
    let more = list.parentNode.querySelector('.hist-more');
    if (!clipped) { if (more) more.remove(); return; }
    if (!more) {
      more = document.createElement('button');
      more.type = 'button';
      more.className = 'btn btn-ghost btn-xs hist-more';
      more.addEventListener('click', () => { unclipped.add(cat); clip(list, false); });
      list.after(more);
    }
    more.textContent = 'All ' + rows + ' versions';
  }
  function tagHtml(cat) {
    const t = AA.ALL_TABS.find(x => x.id === cat);
    return `<span class="badge badge-xs badge-ghost hist-tag">${esc(t ? t.label : cat)}</span>`;
  }
  function renderSent(shown) {
    const el = $('#hist-sent-body');
    const rs = AA.send ? AA.send.receipts() : [];
    const list = rs.map(r => Object.assign({}, r, { items: r.items.filter(it => shown.includes(it.cat)) })).filter(r => r.items.length);
    el.innerHTML = list.length ? list.map(r => `<details class="unified-receipt"><summary>${esc(r.result)} · ${esc(UI.fmtTs(r.ts))}</summary><ul>${r.items.map(it => `<li>${tagHtml(it.cat)} ${esc(it.label)}${it.answer ? ' → ' + esc(it.answer) : ''}</li>`).join('')}</ul></details>`).join('')
      : '';
    // As in the accepted History: the section shows once something was sent.
    $('#hist-sent').hidden = !list.length;
  }

  // Rail tab clicks and arrow keys (E2 order: Feedback first, History last).
  document.querySelectorAll('#drawer-tabs [role="tab"]').forEach(t => t.addEventListener('click', () => setTab(t.dataset.tab)));
  $('#drawer-tabs').addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const tabs = Array.from(document.querySelectorAll('#drawer-tabs [role="tab"]')).filter(t => !t.hidden);
    const i = tabs.findIndex(t => t.dataset.tab === railTab);
    const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    setTab(next.dataset.tab);
    next.focus();
  });
  AA.onChange((k) => { badges(k); if (railTab === 'history') renderSent(AA.tab(view) ? shownTabs() : AA.TABS.map(t => t.id)); });

  AA.rail = {
    setTab, setView, setFilter, renderHistory, tagHtml,
    get tab() { return railTab; },
    // Open the rail on the Feedback tab (phone: the bottom sheet).
    reveal() {
      setTab('feedback');
      window.AnnotateDocs.setDrawerCollapsed(false);
      if (window.AnnotateDocs.isMobileLayout()) window.AnnotateDocs.setMobileSheetOpen(true);
    },
  };
})();

// ── The one Send ────────────────────────────────────────────────────────
// One Send for the project. Its count, the phone Send bar and the summary
// cover every tab; the summary groups what goes out by tab (Review ·
// Library · Findings · Plans). One Send sends the page in one round:
// every document's typed answers and general feedback, then one round of
// verdicts, reopens and Library edits, then one push of new comments.
(function () {
  'use strict';
  const AA = window.AA, UI = window.AAUI, esc = UI.esc;
  const $ = (s) => document.querySelector(s);
  let open = false;
  let sending = false;
  let note = null; // {text, cls, until}: a passing line (e.g. after Discard)
  let noteTimer = null;
  let lastSend = null; // this visit's last Send: {ts, result, items}

  // Sent rounds as the server recorded them (each Send's summary lines, by
  // send_id). This visit's last Send keeps its exact result line.
  function receipts() {
    const server = window.AnnotateDocs ? window.AnnotateDocs.sentRounds() : [];
    if (!lastSend) return server;
    const i = lastSend.send_id ? server.findIndex(r => r.send_id === lastSend.send_id) : -1;
    if (i !== -1) return server.map((r, j) => j === i ? Object.assign({}, r, { result: lastSend.result }) : r);
    return [lastSend].concat(server);
  }
  // What each tab would send now.
  function plan() {
    const out = [];
    let total = 0;
    const k = AA.counts();
    AA.TABS.forEach(t => {
      const n = k[t.id].pending;
      out.push({ id: t.id, label: t.label, n });
      total += n;
    });
    return { tabs: out, total };
  }

  // ── Header Send, progress and the phone Send bar ───────────────────────
  function refresh(counts) {
    const p = plan();
    const btn = $('#send-btn');
    $('#send-count').textContent = String(p.total);
    btn.disabled = p.total === 0 || sending;
    btn.title = p.total === 0 ? 'Nothing to send yet' : 'Send ' + p.total + ' item' + (p.total === 1 ? '' : 's') + ' to the agent (⌘↵)';
    // B1: "x of n decided" belongs to the document on screen.
    const docs = window.AnnotateDocs;
    const doc = AA.isDoc(AA.view) && docs && docs.docs.includes(AA.view) ? AA.view : null;
    const s = doc ? docs.roundStats(doc) : null;
    const prog = $('#hdr-progress');
    prog.hidden = !s || s.total === 0;
    if (s && s.total) {
      const bar = $('#hdr-progress-bar');
      bar.max = Math.max(1, s.total);
      bar.value = s.decided;
      $('#hdr-progress-txt').textContent = s.decided + ' of ' + s.total + ' decided';
    }
    const live = note && Date.now() < note.until;
    const last = receipts()[0];
    const n = $('#send-note');
    if (live) { n.textContent = note.text; n.className = 'send-note' + (note.cls ? ' ' + note.cls : ''); }
    else if (last) { n.textContent = last.result + ' · ' + UI.fmtTs(last.ts); n.className = 'send-note unified-durable-receipt'; }
    else { n.textContent = ''; n.className = 'send-note'; }
    // D2: the phone bar, on every tab.
    const mobile = docs && docs.isMobileLayout();
    const bar = $('#round-bar');
    const show = !!mobile;
    bar.classList.toggle('is-on', show);
    bar.style.display = show ? '' : 'none';
    document.body.classList.toggle('has-round-bar', show);
    $('#round-bar-main').textContent = s && s.total ? (s.decided + ' of ' + s.total + ' decided') : (p.total ? p.total + ' to send' : 'Nothing to send yet');
    $('#round-pending-n').textContent = String(p.total);
    const fb = $('#round-finish-btn');
    fb.disabled = p.total === 0 || sending;
    fb.title = btn.title;
    const k = counts || AA.counts();
    const elsewhere = AA.TABS.filter(t => t.id !== AA.view && k[t.id].needs).map(t => t.label + ' ' + k[t.id].needs);
    const sub = $('#round-bar-sub');
    sub.textContent = live ? note.text : elsewhere.length ? 'Needs you: ' + elsewhere.join(' · ') : (last ? last.result : '');
    sub.className = 'round-bar-sub' + (live && note.cls ? ' ' + note.cls : '');
    if (open && !sending) syncCounts();
  }
  function setNote(text, cls, ms) {
    note = { text, cls: cls || '', until: Date.now() + (ms || 6000) };
    clearTimeout(noteTimer);
    noteTimer = setTimeout(() => { note = null; refresh(); }, (ms || 6000) + 50);
    refresh();
  }

  // ── The summary ────────────────────────────────────────────────────────
  function render() {
    if (!open) return;
    const p = plan();
    const docs = window.AnnotateDocs;
    const list = $('#sum-list');
    const scroll = list.scrollTop;
    list.innerHTML = p.tabs.map(t => `<section class="sum-tab" data-sum-tab="${t.id}">
      <div class="sp-sum-cat">${esc(t.label)} <span class="badge badge-sm badge-ghost">${t.n}</span>${t.id !== AA.view ? `<a href="#view=${t.id}" data-sum-open="${t.id}">Open ${esc(t.label)}</a>` : ''}</div>
      <div class="sp-sum-note" data-sum-sub="${t.id}"></div>
      <div class="sum-tab-body" id="sum-body-${t.id}"></div></section>`).join('');
    const warns = [];
    p.tabs.forEach(t => {
      const body = document.getElementById('sum-body-' + t.id);
      const sub = list.querySelector(`[data-sum-sub="${t.id}"]`);
      if (AA.isDoc(t.id) && !t.n && t.id !== AA.view) {
        // A document not on screen with nothing to send: one line.
        sub.textContent = 'Nothing to send yet.';
      } else if (AA.isDoc(t.id)) {
        if (!docs.docs.includes(t.id)) { sub.textContent = 'Nothing to send yet.'; return; }
        docs.renderSummaryInto(t.id, body);
        sub.textContent = docs.sentence(t.id);
        const w = docs.warning(t.id);
        if (w) warns.push(t.label + ': ' + w);
      } else {
        const pr = AA.providers[t.id];
        const items = pr && pr.pending ? pr.pending() : [];
        sub.textContent = items.length ? '' : 'Nothing to send yet.';
        body.innerHTML = items.map(it => `<div class="sum-row"><div class="sum-main"><span class="sum-q">${esc(it.label)}</span><span class="sum-a">${esc(it.answer || '')}</span></div></div>`).join('');
      }
      if (!sub.textContent) sub.hidden = true;
    });
    list.querySelectorAll('[data-sum-open]').forEach(a => a.addEventListener('click', () => close()));
    $('#round-confirm-sub').textContent = p.total
      ? p.total + (p.total === 1 ? ' item' : ' items') + ' will be sent to the agent as one review round, from every tab.'
      : 'Nothing to send yet.';
    const warn = $('#round-confirm-warn');
    warn.textContent = warns.join(' ');
    warn.style.display = warns.length ? '' : 'none';
    list.scrollTop = scroll;
    syncCounts();
  }
  function syncCounts() {
    const p = plan();
    $('#round-submit-btn').disabled = p.total === 0 || sending;
    $('#sum-send-n').textContent = String(p.total);
    p.tabs.forEach(t => { const b = document.querySelector(`[data-sum-tab="${t.id}"] .sp-sum-cat .badge`); if (b) b.textContent = String(t.n); });
    const pending = window.AnnotateDocs ? window.AnnotateDocs.pageRoundPending() : 0;
    $('#round-discard-btn').disabled = pending === 0 || sending;
  }
  function openSummary() {
    if (open) { render(); return; }
    open = true;
    ['round-submit-btn', 'round-cancel-btn'].forEach(id => { document.getElementById(id).disabled = false; });
    render();
    document.body.classList.add('has-summary');
    $('#round-confirm-backdrop').classList.add('vis');
    const b = $('#round-submit-btn');
    if (!b.disabled) b.focus(); else $('#round-cancel-btn').focus();
  }
  function close() {
    open = false;
    $('#round-confirm-backdrop').classList.remove('vis');
    document.body.classList.remove('has-summary');
    const p = AA.params();
    if (p.get('send') || p.get('sumedit')) { p.delete('send'); p.delete('sumedit'); history.replaceState(null, '', '#' + p.toString()); }
  }

  // ── Sending ────────────────────────────────────────────────────────────
  async function submit() {
    const p = plan();
    if (p.total === 0 || sending) return;
    sending = true;
    const btns = ['round-submit-btn', 'round-discard-btn', 'round-cancel-btn'].map(id => document.getElementById(id));
    btns.forEach(b => { b.disabled = true; });
    const submitBtn = btns[0];
    const submitHtml = submitBtn.innerHTML;
    submitBtn.textContent = 'Sending…';
    // The lines this Send carries, tagged with their tabs, for the receipt.
    const docs = window.AnnotateDocs;
    const items = [];
    p.tabs.forEach(t => {
      if (!t.n) return;
      const lines = AA.isDoc(t.id) ? docs.items(t.id) : (AA.providers[t.id] && AA.providers[t.id].pending ? AA.providers[t.id].pending() : []);
      // `kind` and `id` (UI-2) tell the shell which call carries a line.
      lines.forEach(it => items.push({ cat: t.id, label: it.label, answer: it.answer || '', kind: it.kind, id: it.id }));
    });
    const libraryPending = !!(AA.providers.library && AA.providers.library.roundPending && AA.providers.library.roundPending());
    let r = null;
    try { r = await docs.submitPage(libraryPending, items); } catch (e) { console.error('[annotate] send', e); }
    submitBtn.innerHTML = submitHtml;
    sending = false;
    // UI-2: the receipt lists only what was sent; what failed stays pending.
    const sent = r ? (r.sent || []).map(it => ({ cat: it.cat, label: it.label, answer: it.answer || '' })) : [];
    const failed = r ? (r.failed || []).length : items.length;
    if (!sent.length) {
      btns.forEach(b => { b.disabled = false; });
      if (r) { await docs.reload(); AA.changed(); }
      $('#round-confirm-sub').textContent = 'Failed to submit — try again.';
      return;
    }
    const n = sent.length;
    const result = r.delivered ? '✅ Sent to session (' + n + ')' : '⏳ Queued — no session listening (' + n + ')';
    lastSend = { ts: new Date().toISOString(), result, items: sent, fresh: true, send_id: r.send_id };
    if (failed) {
      // A partial Send: the summary stays open on what is still pending.
      setNote(result, r.delivered ? 'is-success' : 'is-queued');
      await docs.reload();
      AA.TABS.forEach(t => { const pr = AA.providers[t.id]; if (pr && pr.afterSend) pr.afterSend(); });
      btns.forEach(b => { b.disabled = false; });
      render();
      $('#round-confirm-sub').textContent = 'Failed to send ' + failed + (failed === 1 ? ' item' : ' items') + ' — try again.';
      if (AA.rail.tab === 'history') AA.rail.renderHistory();
      AA.changed();
      return;
    }
    close();
    setNote(result, r.delivered ? 'is-success' : 'is-queued');
    await docs.reload();
    AA.TABS.forEach(t => { const pr = AA.providers[t.id]; if (pr && pr.afterSend) pr.afterSend(); });
    if (AA.rail.tab === 'history') AA.rail.renderHistory();
    AA.changed();
  }
  // 2.20's Discard pending: the pending verdicts of the page.
  async function discard() {
    const docs = window.AnnotateDocs;
    if (!docs || sending) return;
    sending = true;
    const btns = ['round-submit-btn', 'round-discard-btn', 'round-cancel-btn'].map(id => document.getElementById(id));
    btns.forEach(b => { b.disabled = true; });
    const n = await docs.discardPage();
    sending = false;
    if (n == null) {
      btns.forEach(b => { b.disabled = false; });
      $('#round-confirm-sub').textContent = 'Failed to discard — try again.';
      return;
    }
    close();
    setNote('Discarded ' + n + ' pending verdict' + (n === 1 ? '' : 's') + ' — nothing sent', '', 5000);
    await docs.reload();
  }

  $('#send-btn').addEventListener('click', openSummary);
  $('#round-finish-btn').addEventListener('click', openSummary);
  $('#round-cancel-btn').addEventListener('click', close);
  $('#round-submit-btn').addEventListener('click', submit);
  $('#round-discard-btn').addEventListener('click', discard);
  $('#round-confirm-backdrop').addEventListener('click', (e) => { if (e.target === e.currentTarget) close(); });

  AA.onChange(refresh);
  AA.send = {
    open: openSummary, close, isOpen: () => open, submit, render, syncCounts, note: setNote, receipts, refresh, plan,
    justSent: () => !!(lastSend && lastSend.fresh),
  };
})();

// ── Linked pages (declared exceptions) ──────────────────────────────────
// Chang: "any exceptions would be spelled out to the orchestrator. but even
// then, it should be linked from a tab in the annotation page." A project
// whose owner declared a separate page lists it here, with why; the page
// itself opens in a new browser tab. The tab exists only when the project
// declares at least one linked page.
(function () {
  'use strict';
  const AA = window.AA, UI = window.AAUI, esc = UI.esc;
  function render() {
    const pages = AA.linkedPages;
    document.getElementById('linked-list').innerHTML = `<div class="plan-scope"><strong>Linked pages</strong> · separate pages the owner declared for this project</div>
      <p>Each project has one annotate page. A separate page exists only when the owner spells out the exception to the orchestrator; it is still listed here, so everything about the project starts from this page.</p>
      <div class="cards">${pages.map(p => `<div class="card" data-linked="${esc(p.slug)}">
        <h4><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title || p.slug)} ${UI.ico('external')}</a></h4>
        ${p.reason ? `<p class="ctx">${esc(p.reason)}</p>` : ''}
        ${p.declared_by ? `<p class="muted">Declared by ${esc(p.declared_by)} to ${esc(p.told_to || 'the orchestrator')}${p.declared_at ? ' · ' + esc(UI.fmtTs(p.declared_at)) : ''}</p>` : ''}
      </div>`).join('')}</div>`;
    document.getElementById('rail-linked').innerHTML = `<p class="project-detail rail-note">Feedback on a linked page is given on that page.</p>`;
  }
  AA.provider('linked', { show() { render(); } });
})();
