/* Prototype frame: top bar, six tabs, settings, Home, the phone's menu, area loading and the ctx every tab gets. Contract: README.md. */
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
  let started = false;
  P.tab = spec => {
    if (!spec || !byKey[spec.key]) return console.warn('Proto.tab: unknown key', spec && spec.key);
    Object.assign(byKey[spec.key], spec);
    if (started) { drawTabs(); if (!S.home && S.tab === spec.key) show(S.tab, null); }
  };
  // The area that owns answering registers Send: count(ctx) -> number ready, open(ctx) opens its Send summary.
  let sendP = null;
  P.send = spec => { sendP = spec; if (started) refreshTop(); };
  // An optional top-bar slot beside the version (Running's worker squares): render(el, ctx).
  let barP = null;
  P.bar = spec => { barP = spec; if (started) drawBar(); };

  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const pl = (n, one, many) => `${Number(n).toLocaleString()} ${n === 1 ? one : many}`;
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
  const REM = {folds: true, tab: true, drafts: true};
  const remember = kind => ({...REM, ...prefs.get('rem', {})})[kind] !== false;

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
  const S = {tab: 'questions', home: false, menu: '', sheet: '', meta: null, loadedV: '', newer: null, checked: '',
    fd: null, who: null, board: null, boardUrl: '', sendN: 0, chips: {}, people: null};
  const ctx = {
    base, api, data, prefs, esc, toast, inert, remember,
    icon: (n, l) => P.icon(n, l),
    go(tab, anchor) { location.hash = tab + (anchor ? '/' + encodeURIComponent(anchor) : ''); },
    get phone() { return phoneQ.matches; },
    refreshChips: () => { drawTabs(); refreshTop(); },
    refreshTop: () => refreshTop(),
  };
  P.ctx = ctx;
  P.frameState = S;  // for tests and screenshots only
  const I =(n, l) => P.icon(n, l);

  /* ---------- tabs and their chips ---------- */
  // A chip is {text, tone, title} or {empty: true}; empty dims the tab and reads "nothing yet" (#93).
  const chipHtml = c => !c ? '' : c.empty ? '<span class="ct none">nothing yet</span>'
    : c.text == null || c.text === '' ? '' : `<span class="ct ${esc(c.tone || '')}"${c.title ? ` title="${esc(c.title)}"` : ''}>${esc(c.text)}</span>`;
  function paintChip(key) {
    const c = S.chips[key];
    document.querySelectorAll(`#p-top [data-chip="${key}"], #p-tabs [data-chip="${key}"], #p-layer [data-chip="${key}"]`).forEach(el => { el.innerHTML = chipHtml(c); });
    document.querySelectorAll(`.tab[data-tab="${key}"], .pm-tab[data-tab="${key}"]`).forEach(el => el.classList.toggle('empty', !!(c && c.empty)));
  }
  function drawTabs() {
    const nav = document.getElementById('p-tabs');
    nav.hidden = S.home;
    nav.innerHTML = TABS.map(t => `<button class="tab ${t.tone}" role="tab" data-tab="${t.key}" aria-selected="${!S.home && t.key === S.tab}">${I(t.icon)}<span class="tl">${esc(t.label)}</span><span class="cw" data-chip="${t.key}"></span></button>`).join('');
    for (const t of TABS) {
      paintChip(t.key);
      if (t.chip) Promise.resolve().then(() => t.chip(ctx)).then(c => {
        S.chips[t.key] = c == null || c === '' ? null : typeof c === 'object' ? c : {text: String(c)};
        paintChip(t.key);
      }).catch(e => console.warn('chip', t.key, e));
    }
  }

  function show(key, anchor) {
    const t = byKey[key] || TABS[0];
    S.tab = t.key;
    document.querySelectorAll('.tab[data-tab], .pm-tab[data-tab]').forEach(b => b.setAttribute('aria-selected', String(!S.home && b.dataset.tab === S.tab)));
    const el = document.getElementById('p-main');
    el.className = 'p-main area-' + t.area + ' tab-' + t.key;
    if (!t.render) {
      el.innerHTML = `<div class="p-empty">${I(t.icon)}<p>${esc(t.label)}: not built yet.</p></div>`;
      if (t.key === 'questions') questionsPreview(el);
      return;
    }
    el.innerHTML = '';
    Promise.resolve().then(() => t.render(el, ctx, anchor)).then(() => {
      const target = anchor && document.getElementById(anchor);
      if (target) target.scrollIntoView({block: 'start'});
    }).catch(e => { el.innerHTML = `<div class="p-empty">${I('warn')}<p>${esc(t.label)} failed to draw: ${esc(e.message)}</p></div>`; console.error(e); });
  }
  // Until the questions area registers: this version's real questions, read through today's API.
  async function questionsPreview(el) {
    const [meta, store] = await Promise.all([api.meta(), api.comments()]);
    const qs = Object.values(store.anchors || {}).flat()
      .filter(c => c.decision_request && c.version === meta.current && !c.parent_id);
    const old = el.querySelector('.p-qlist');  // two quick routes must not draw the list twice
    if (old) old.remove();
    el.insertAdjacentHTML('beforeend', `<ul class="p-qlist">${qs.map(c => `<li><span class="dot ${c.decision ? 'st-done' : 'st-waiting'}"></span><span class="p-primary">${esc(c.decision_request.prompt || c.text)}</span></li>`).join('')}</ul>`);
  }

  /* ---------- top bar ---------- */
  const projName = () => (S.meta && S.meta.name) || 'This project';
  const myName = () => (S.who && S.who.name) || 'You';
  // One waiting count: the Questions tab's, with his unsent answers; the server's same rule until it loads.
  const waitingHere = () => S.qWait != null ? S.qWait : (S.fd && S.fd.waiting) || 0;
  const projs = () => ((S.fd && S.fd.projects) || []).map(x => x.this ? {...x, waiting: waitingHere()} : x);
  // One ready count: Running's, read from the board with `bd ready`.
  const readyHere = () => S.ready != null ? S.ready : null;
  function reloadBtn() {
    const nw = S.newer;
    if (nw) return `<button class="rl2 new" data-recheck title="A newer version is ready. Red: ${pl(nw.n, 'new question', 'new questions')}. Amber: ${pl(nw.fix, 'fix', 'fixes')} to your notes. Press to load it; your place and what you typed are kept." aria-label="Load the newer version: ${pl(nw.n, 'new question', 'new questions')}, ${pl(nw.fix, 'fix', 'fixes')}">${I('reload')}${nw.n ? `<span class="n q">${nw.n}</span>` : ''}${nw.fix ? `<span class="n f">${nw.fix}</span>` : ''}</button>`;
    return `<button class="rl2" data-recheck title="Up to date${S.checked ? ', checked at ' + S.checked : ''}. The icon turns blue when the agent publishes a newer version; the page changes only when you press it." aria-label="Up to date. Check for a newer version">${I('reload')}</button>`;
  }
  function projRows() {
    return projs().map(x => `<button class="mi" role="menuitem" ${x.this ? `data-gothis${S.home ? '' : ' aria-current="page"'}` : `data-home title="${esc(x.name)} is read-only in the prototype: its counts show on Home"`}><span class="nm">${esc(x.name)}</span>${x.waiting ? `<span class="badge qw" title="${pl(x.waiting, 'question waits', 'questions wait')} for your answer">${x.waiting} waiting</span>` : ''}${x.this ? '' : '<span class="small mut">read-only</span>'}</button>`).join('');
  }
  function settingsBody() {
    const fs = prefs.get('fs', 100), theme = themeMode(), rem = {...REM, ...prefs.get('rem', {})}, z = prefs.get('zoomDef', 75);
    const th = [['light', 'sun', 'Light'], ['dark', 'moon', 'Dark'], ['system', 'sys', 'System: follows your Mac, iPad or phone']];
    const tg = (attr, t, tip, on) => `<label class="tgl"${tip ? ` title="${esc(tip)}"` : ''}><span>${t}</span><input type="checkbox" role="switch" ${attr}${on ? ' checked' : ''}><i aria-hidden="true"></i></label>`;
    const n = S.people ? S.people.length : 1;
    return `<div class="me-h"><span class="av big" aria-hidden="true">${esc(myName()[0])}</span><span class="grow"><b>${esc(myName())}</b><span class="small mut">${S.who && S.who.authenticated ? 'Signed in' : 'On this Mac'}</span></span><span class="me-ic">
      <button class="icb" data-sheet="keys" title="Keyboard shortcuts" aria-label="Keyboard shortcuts">${I('keys')}</button>
      ${S.home ? '' : `<button class="icb" data-sheet="people" title="People on ${esc(projName())}: ${pl(n, 'person', 'people')}" aria-label="People on ${esc(projName())}">${I('people')}</button>`}
      <button class="icb" data-copylink title="Copy a link to this page" aria-label="Copy a link to this page">${I('link')}</button>
      <button class="icb" data-signout title="Sign out" aria-label="Sign out">${I('out')}</button></span></div>
    <div class="sep"></div>
    <div class="srow2"><span class="sl">Theme</span><span class="seg ic3" role="group" aria-label="Theme">${th.map(([t, i, l]) => `<button data-set-theme="${t}" aria-pressed="${theme === t}" title="${l}" aria-label="${l}">${I(i)}</button>`).join('')}</span></div>
    <div class="srow2"><span class="sl">Text size</span><span class="fsbox"><button data-fs="-10" title="Smaller text" aria-label="Smaller text">−</button><input type="text" data-fsin inputmode="numeric" value="${fs}%" aria-label="Text size: pick a step or type a percentage" title="Pick a step or type a percentage from 70 to 160"><span class="fslist" role="listbox" aria-label="Text size steps">${[70, 80, 90, 100, 110, 120, 130, 140, 150, 160].map(v => `<button data-fsset="${v}" aria-current="${v === fs}">${v}%</button>`).join('')}</span><button data-fs="10" title="Larger text" aria-label="Larger text">+</button></span></div>
    <div class="srow2"><span class="sl">Pictures open at</span><span class="seg zs" role="group" aria-label="Full-size pictures open at">${[25, 50, 75, 100].map(v => `<button data-zdef="${v}" aria-pressed="${v === z}" title="Open full-size pictures at ${v}% of the screen width; each picture keeps its own zoom buttons">${v}%</button>`).join('')}</span></div>
    <div class="sep"></div>
    <div class="tgls">${tg('data-optsfirst', 'Options first', "Show each card's choices above its pictures and text", prefs.get('optsFirst', false))}</div>
    <h3>Remember after a reload</h3><div class="tgls">${tg('data-rem="folds"', 'Folded sections', '', rem.folds)}${tg('data-rem="tab"', 'Open tab', '', rem.tab)}${tg('data-rem="drafts"', 'Unsent answers and notes', '', rem.drafts)}</div>
    ${S.home ? '' : `<div class="srow2 small me-ag">${I('agent')}<span class="sl">Your Send is saved on this copy and reaches no agent</span>${P.inertMark()}</div>`}`;
  }
  function sendBtn(cls) {
    const n = S.sendN;
    return `<button class="btn ${n ? 'pri' : ''} ${cls || ''}" data-send${n ? '' : ' aria-disabled="true"'} title="${n ? 'Open the Send summary (⌘↵); ⌘↵ again sends' : 'Nothing is ready to send yet'}">${I('send')}Send${n ? ' ' + n : ''}</button>`;
  }
  function drawTop() {
    const top = document.getElementById('p-top'), w = waitingHere();
    const cur = byKey[S.tab] || TABS[0];
    const mb = `<button class="mbtn" data-menu="nav" aria-haspopup="dialog" aria-expanded="${S.menu === 'nav'}" title="Menu: tabs, projects and settings" aria-label="Menu: tabs, projects and settings">${I(S.menu === 'nav' ? 'x' : 'menu')}</button>`;
    const allW = projs().reduce((s, x) => s + (x.waiting || 0), 0);
    const pt = `<button class="ptitle" data-menu="nav" aria-label="Menu: tabs, projects and settings">${S.home ? `<b>All projects</b><span class="tn">${pl(allW, 'question waiting', 'questions waiting')}</span>` : `<b>${esc(projName())}</b><span class="tn">${esc(cur.label)}<span data-chip="${cur.key}">${chipHtml(S.chips[cur.key])}</span></span>`}</button>`;
    const brand = `<a class="brand" href="#home" title="Home: every project" aria-label="Home: every project"${S.home ? ' aria-current="page"' : ''}>${I('home')}<span class="full">Agent Annotate</span></a>`;
    const projMenu = S.menu === 'proj' ? `<div class="menu" role="menu" aria-label="Projects"><h3>Your projects</h3>${projRows()}<div class="sep"></div><button class="mi" data-home><span class="nm">All projects (home)</span></button></div>` : '';
    const me = S.menu === 'me' ? `<div class="menu right smenu" role="menu" aria-label="Settings">${settingsBody()}</div>` : '';
    const who = `<div class="dd"><button class="btn ghost who" data-menu="me" aria-haspopup="menu" aria-expanded="${S.menu === 'me'}" title="Settings, people and sign out"><span class="av" aria-hidden="true">${esc(myName()[0])}</span><span class="hide-ph">${esc(myName())}</span> ▾</button>${me}</div>`;
    const dd = `<div class="dd hide-ph"><button class="btn" data-menu="proj" aria-haspopup="menu" aria-expanded="${S.menu === 'proj'}"><b>${S.home ? 'All projects' : esc(projName())}</b>${!S.home && w ? `<span class="badge qw" title="${pl(w, 'question waits', 'questions wait')} for your answer on this project">${w} waiting</span>` : ''} ▾</button>${projMenu}</div>`;
    if (S.home) { top.innerHTML = `${mb}${brand}${pt}${dd}<span class="spacer"></span>${who}`; return; }
    const ver = S.meta ? `<span class="chip hide-ph verchip" title="The version on screen">Version ${esc(String(S.meta.current || '').replace(/^v/, ''))}</span>` : '';
    const ready = readyHere();
    const beads = S.boardUrl ? `<a class="btn ghost hide-ph bdchip" href="${esc(S.boardUrl)}" target="_blank" rel="noopener" title="Open the bead board (read-only from here)">${I('bead')}Beads${ready != null ? `<span class="badge ok">${ready} ready</span>` : ''}</a>` : '';
    top.innerHTML = `${mb}${brand}${pt}${dd}${ver}<span class="p-bar" id="p-bar"></span><span class="spacer"></span>${reloadBtn()}${beads}${sendBtn('hide-ph')}${who}`;
    drawBar();
  }
  function drawBar() {
    const el = document.getElementById('p-bar');
    if (el && barP && !S.home) Promise.resolve().then(() => barP.render(el, ctx)).catch(e => console.warn('bar', e));
  }
  function drawFab() {
    const f = document.getElementById('p-fab');
    f.hidden = !(S.sendN && !S.home && S.menu !== 'nav');
    f.innerHTML = `${I('send')}Send ${S.sendN || ''}`;
    f.setAttribute('aria-label', `Send: ${pl(S.sendN, 'thing is', 'things are')} ready`);
  }
  function drawLayer() {
    const L = document.getElementById('p-layer');
    let h = '';
    if (S.menu === 'nav') h += navMenu();
    if (S.sheet === 'keys') h += keysSheet();
    if (S.sheet === 'people') h += peopleSheet();
    L.innerHTML = h;
    document.body.classList.toggle('p-locked', S.menu === 'nav' || !!S.sheet);
  }
  function drawAll() { drawTop(); drawFab(); drawLayer(); }
  let topTimer;
  function refreshTop() {
    clearTimeout(topTimer);
    topTimer = setTimeout(async () => {
      await Promise.all([
        sendP ? Promise.resolve().then(() => sendP.count(ctx)).then(n => { S.sendN = +n || 0; }).catch(e => console.warn('send count', e)) : null,
        sendP && sendP.waiting ? Promise.resolve().then(() => sendP.waiting(ctx)).then(n => { S.qWait = +n || 0; }).catch(e => console.warn('waiting', e)) : null,
        data('running').then(r => { S.ready = r && r.board && typeof r.board.ready === 'number' ? r.board.ready : null; }).catch(() => {}),
        data('frame', true).then(d => { S.fd = d; }).catch(() => {}),
      ]);
      drawTop(); drawFab(); if (S.menu === 'nav') drawLayer();
      if (S.home) drawHome();  // its row for this page shows the same waiting count
    }, 300);
  }

  /* ---------- the phone's menu, People and keyboard shortcuts ---------- */
  function navMenu() {
    const tabs = S.home ? '' : `<nav aria-label="Tabs">${TABS.map(t => { const c = S.chips[t.key]; return `<button class="pm-tab ${t.tone}${c && c.empty ? ' empty' : ''}" role="tab" data-tab="${t.key}" aria-selected="${S.tab === t.key}">${I(t.icon)}<span>${esc(t.label)}</span><span data-chip="${t.key}">${chipHtml(c)}</span></button>`; }).join('')}</nav>
      <div class="pm-acts">${sendBtn('')}${S.boardUrl ? `<a class="btn" href="${esc(S.boardUrl)}" target="_blank" rel="noopener">${I('bead')} Bead board${readyHere() != null ? ` <span class="badge ok">${readyHere()} ready</span>` : ''}</a>` : ''}</div>`;
    return `<div class="pmenu" role="dialog" aria-label="Menu">${tabs}<h3>Projects</h3>${projRows()}<button class="mi" data-home${S.home ? ' aria-current="page"' : ''}><span class="nm ri8">${I('home')} All projects</span></button><div class="smb">${settingsBody()}</div></div>`;
  }
  const KEYS = [['F', 'next question'], ['A', 'previous question'], ['1–9', 'pick that choice on the highlighted question'], ['C', 'write words on the highlighted question'],
    ['⌘↵', 'open the Send summary, from anywhere, even while typing an answer; in a note box it saves the note'], ['⌘↵ again', 'send, once the Send summary is open'],
    ['Esc', 'close a menu, sheet or picture'], ['J K', 'next or previous task, while a task is open'], ['?', 'this list']];
  const keysSheet = () => `<div class="sheet" data-scrim><div class="box" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts"><h2 class="ph">${I('keys')} Keyboard shortcuts</h2><ul class="keys">${KEYS.map(([k, t]) => `<li><kbd>${k}</kbd><span>${t}</span></li>`).join('')}</ul><div class="acts"><button class="btn" data-close>Close</button></div></div></div>`;
  const ROLE = {owner: 'Owner', view: 'Can view', send: 'Can answer and send'}, ROLEIC = {owner: 'key', view: 'eye', send: 'edit'};
  const ROLEHINT = {owner: 'Sees every project and is the only one who can change who has access', view: 'Reads the page, its questions, Reference and History; cannot answer, write notes or send', send: 'Also answers questions, writes notes and presses Send'};
  function peopleSheet() {
    S.people = S.people || [{n: myName(), role: 'owner'}];
    const nr = S.newRole || 'view';
    return `<div class="sheet" data-scrim><div class="box" role="dialog" aria-modal="true" aria-label="People on ${esc(projName())}">
      <h2 class="ph ri8">${I('people')} People on ${esc(projName())} <span class="badge grey">${S.people.length}</span></h2>
      <p class="small mut">Only you, the owner, can add or remove people and change what they can do.</p>
      <div role="list">${S.people.map((x, i) => `<div class="prow" role="listitem"><span class="av" aria-hidden="true">${esc(x.n[0])}</span><div class="grow"><b>${esc(x.n)}</b>${x.role === 'owner' ? ' <span class="small mut">(you)</span>' : ''}</div>
        ${x.role === 'owner' ? `<span class="ri8 small" title="${esc(ROLEHINT.owner)}">${I(ROLEIC.owner)}${ROLE.owner}</span>` : `<span class="seg" role="group" aria-label="What ${esc(x.n)} can do">${['view', 'send'].map(r => `<button data-prole="${i}~${r}" aria-pressed="${x.role === r}" title="${esc(ROLEHINT[r])}">${I(ROLEIC[r])} ${ROLE[r]}</button>`).join('')}</span><button class="icb" data-prm="${i}" title="Remove ${esc(x.n)}" aria-label="Remove ${esc(x.n)}">${I('trash')}</button>`}</div>`).join('')}</div>
      <div class="addrow"><input type="email" id="p-newperson" placeholder="Their Google email" aria-label="Their Google email"><span class="seg" role="group" aria-label="What they can do">${['view', 'send'].map(r => `<button data-pnewrole="${r}" aria-pressed="${nr === r}" title="${esc(ROLEHINT[r])}">${I(ROLEIC[r])} ${ROLE[r]}</button>`).join('')}</span><button class="btn pri sm" data-padd>Add</button>${P.inertMark()}</div>
      ${S.pErr ? `<p class="small err-t" role="alert">${esc(S.pErr)}</p>` : ''}
      <div class="acts"><button class="btn" data-close>Done</button></div></div></div>`;
  }
  const nameOf = v => { const l = v.split('@')[0].replace(/[._-]+/g, ' ').trim(); return l ? l[0].toUpperCase() + l.slice(1) : v; };  // a name, never an address

  /* ---------- Home: every project, read-only past this one ---------- */
  async function drawHome() {
    const el = document.getElementById('p-main');
    el.className = 'p-main home';
    const fd = S.fd || await data('frame').catch(() => null);
    if (!fd) { el.innerHTML = `<div class="p-empty">${I('warn')}<p>Home could not load its counts.</p></div>`; return; }
    S.fd = fd;
    const run = await data('running').catch(() => ({}));
    const days = fd.days || 14;
    const ago = h => h == null ? 'no page yet' : h < 1 ? 'under an hour ago' : h < 48 ? `${Math.round(h)} h ago` : `${Math.round(h / 24)} days ago`;
    const SL = {working: 'working', stuck: 'no sign of life', failed: 'failed', done: 'done', later: 'later', stopped: 'stopped'};
    const rows = projs().map(x => {
      // running.json keeps workers by Mac, every project's; this row shows this project's, as Running does
      // shortcut: the project is fixed to FastLane Drive, as in running.js; take it from the page when other pages use this UI
      const rw = Array.isArray(run.workers) ? run.workers : run.workers && typeof run.workers === 'object'
        ? Object.values(run.workers).flatMap(v => (v && v.workers) || []).filter(w => w.proj === 'fld') : null;
      const ws = x.this && rw ? rw.map(w => ({name: w.name || '', s: w.s || w.state || 'working'})) : null;
      const jobs = x.this && Array.isArray(run.jobs) ? run.jobs : null;
      const bad = (jobs || []).filter(j => j.failing).length + (ws || []).filter(w => w.s === 'stuck' || w.s === 'failed').length;
      const h = x.lastAgoH;
      const health = bad ? ['bad', `${pl(bad, 'thing needs', 'things need')} a look: failing jobs or workers with no sign of life`] : h == null ? ['idle', 'No page yet'] : h > 24 * 30 ? ['idle', 'Quiet: no update in a month'] : x.waiting && h > 24 * 7 ? ['warn', 'Questions wait and nothing new in a week'] : ['ok', 'Fine'];
      return {...x, ws, jobs, bad, health};
    }).sort((a, b) => (b.this ? 1 : 0) - (a.this ? 1 : 0) || b.waiting - a.waiting || b.bad - a.bad || (a.lastAgoH ?? 1e9) - (b.lastAgoH ?? 1e9));
    const maxW = Math.max(1, ...rows.map(r => r.waiting)), maxV = Math.max(1, ...rows.flatMap(r => r.vday));
    const totW = rows.reduce((s, r) => s + r.waiting, 0), fresh = rows.filter(r => r.lastAgoH != null && r.lastAgoH < 24).length;
    const spark = r => { const bw = 8, g = 2, W = days * (bw + g);
      return `<svg class="spark" viewBox="0 0 ${W} 30" preserveAspectRatio="none" width="${W}" height="30" role="img" aria-label="${pl(r.vday.reduce((s, n) => s + n, 0), 'version', 'versions')} and ${pl(r.aday.reduce((s, n) => s + n, 0), 'answer round', 'answer rounds')} in ${days} days">${r.vday.map((n, i) => `<g><title>${days - 1 - i ? `${days - 1 - i} days ago` : 'today'}: ${pl(n, 'version', 'versions')} published, ${pl(r.aday[i], 'answer round', 'answer rounds')} from you</title><rect class="sb0" x="${i * (bw + g)}" y="0" width="${bw}" height="24"/>${n ? `<rect class="sb" x="${i * (bw + g)}" y="${24 - Math.max(2, n / maxV * 24)}" width="${bw}" height="${Math.max(2, n / maxV * 24)}"/>` : ''}${r.aday[i] ? `<rect class="sa" x="${i * (bw + g)}" y="26" width="${bw}" height="4"/>` : ''}</g>`).join('')}</svg>`; };
    const unread = what => `<span class="small mut" title="Not read in the prototype yet"><span class="ph-only">${what} </span>—</span>`;
    const dots = ws => !ws ? unread('workers') : ws.length ? ws.slice(0, 16).map(w => `<i class="dt ${esc(w.s)}" title="${esc(w.name)}: ${esc(SL[w.s] || w.s)}"></i>`).join('') + (ws.length > 16 ? `<span class="small mut">+${ws.length - 16} more</span>` : '') : '<span class="small mut">no workers</span>';
    const jobsCell = js => !js ? unread('scheduled jobs') : js.length ? js.map(j => `<i class="dq ${j.failing ? 'bad' : 'ok'}" title="${esc(j.name)}: ${j.failing ? 'failing' : 'fine'}"></i>`).join('') : '<span class="small mut">no scheduled jobs</span>';
    const row = r => `<div class="hrow" role="row"><span class="hc nm" role="cell"><i class="hd ${r.health[0]}" title="${esc(r.health[1])}" aria-label="${esc(r.health[1])}"></i>${r.this ? `<button class="lk" data-gothis>${esc(r.name)}</button>` : `<span class="ro" title="Read-only in the prototype">${esc(r.name)}</span>`}<span class="small mut hpg">${pl(r.pages, 'page', 'pages')}</span></span>
      <span class="hc wt" role="cell" title="${pl(r.waiting, 'question', 'questions')} waiting">${r.waiting ? `<span class="wbar"><i style="width:${Math.max(4, r.waiting / maxW * 100)}%"></i></span><b class="err-t">${r.waiting} waiting</b>` : '<span class="small mut">nothing waiting</span>'}</span>
      <span class="hc wk" role="cell">${dots(r.ws)}</span><span class="hc jb" role="cell">${jobsCell(r.jobs)}</span>
      <span class="hc ac" role="cell">${spark(r)}</span><span class="hc ls small mut" role="cell">${ago(r.lastAgoH)}</span></div>`;
    const tile = (big, sub, cls, viz) => `<div class="htile ${cls}"><b>${big}</b><span>${sub}</span>${viz || ''}</div>`;
    el.innerHTML = `<section class="home"><div class="hhead"><h2 class="ph">All projects</h2><span class="small mut">from the project pages on this Mac · ${esc(fd.asOf || '')} · other projects are read-only here</span></div>
      <div class="htiles">${tile(totW.toLocaleString(), `questions waiting, in ${pl(rows.filter(r => r.waiting).length, 'project', 'projects')}`, totW ? 'bad' : '', `<span class="stack">${rows.filter(r => r.waiting).map(r => `<i style="flex:${r.waiting}" title="${esc(r.name)}: ${r.waiting} waiting"></i>`).join('')}</span>`)}
        ${tile(rows.reduce((s, r) => s + r.pages, 0).toLocaleString(), `pages, in ${pl(rows.length, 'project', 'projects')}`, '')}
        ${tile(rows.reduce((s, r) => s + r.vday.reduce((a, n) => a + n, 0), 0).toLocaleString(), `versions published in ${days} days`, '')}
        ${tile(fresh.toLocaleString(), `${fresh === 1 ? 'project' : 'projects'} updated in the last day`, '')}</div>
      <div class="htab" role="table" aria-label="Every project"><div class="hrow hh" role="row"><span class="hc nm" role="columnheader">Project</span><span class="hc wt" role="columnheader">Waiting</span><span class="hc wk" role="columnheader">Workers</span><span class="hc jb" role="columnheader">Scheduled jobs</span><span class="hc ac" role="columnheader">Last ${days} days</span><span class="hc ls" role="columnheader">Last update</span></div>${rows.map(row).join('')}</div>
      <p class="small mut hleg"><span><i class="hd ok"></i>fine</span><span><i class="hd warn"></i>questions wait, nothing new in a week</span><span><i class="hd bad"></i>a job failing or a worker with no sign of life</span><span><i class="hd idle"></i>quiet</span><span><svg width="8" height="10"><rect class="sb" width="8" height="10"/></svg> versions published a day</span><span><svg width="8" height="4"><rect class="sa" width="8" height="4"/></svg> a day you answered</span></p></section>`;
  }

  /* ---------- routing ---------- */
  function route() {
    const [key, anchor] = location.hash.replace(/^#/, '').split('/');
    S.home = key === 'home';
    S.menu = '';
    if (S.home) { drawTabs(); drawAll(); drawHome(); return; }
    const tab = byKey[key] ? key : remember('tab') ? prefs.get('tab', 'questions') : 'questions';
    S.tab = byKey[tab] ? tab : 'questions';
    prefs.set('tab', S.tab);
    drawTabs(); drawAll();
    show(S.tab, anchor ? decodeURIComponent(anchor) : null);
  }

  /* ---------- a newer version: checked once a minute; the page changes only when he presses the icon ---------- */
  async function checkNewer() {
    const m = await api.meta().catch(() => null);
    S.checked = new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
    if (!m || !S.loadedV) return false;
    if (m.current === S.loadedV) { S.newer = null; return false; }
    const vs = (m.history || []).map(h => h.version), from = vs.indexOf(S.loadedV), fresh = new Set(from < 0 ? [m.current] : vs.slice(from + 1));
    const store = await api.comments().catch(() => ({anchors: {}}));
    // A question re-asked in each version is not new: count prompts he has not seen on screen yet.
    const all = Object.values(store.anchors || {}).flat(), prompt = c => (c.decision_request.prompt || c.text || '').trim();
    const seen = new Set(all.filter(c => c.decision_request && !fresh.has(c.version)).map(prompt));
    const asked = new Set(all.filter(c => c.decision_request && !c.decision && fresh.has(c.version) && !seen.has(prompt(c))).map(prompt));
    const fix = all.filter(c => fresh.has(c.version) && !c.decision_request && String(c.author || '').startsWith('agent:')).length;
    S.newer = {v: m.current, n: asked.size, fix};
    return true;
  }

  /* ---------- theme and text size ---------- */
  const THEMES = ['light', 'dark', 'system'];
  // own key: ordinary pages share this origin and read annotate:theme
  function themeMode() { const t = prefs.get('theme', 'system'); return THEMES.includes(t) ? t : 'system'; }
  function applyTheme(mode) {
    const dark = mode === 'dark' || (mode === 'system' && matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  }
  const setFs = v => { v = Math.max(70, Math.min(160, Math.round(+v) || 100)); prefs.set('fs', v); document.documentElement.style.setProperty('--fs', v / 100); };

  /* ---------- clicks and keys ---------- */
  function onClick(e) {
    // Only the frame's own controls: an area's buttons (its own data-send, data-close, ...) are never caught here.
    const t = e.target.closest('#p-top button, #p-top a, #p-layer button, #p-layer a, #p-layer [data-scrim], #p-fab, #p-tabs button, .p-main.home button');
    if (!t) {
      if (S.menu && S.menu !== 'nav' && !e.target.closest('.menu')) { S.menu = ''; drawAll(); }
      return;
    }
    const d = t.dataset;
    if (d.scrim !== undefined) { if (t === e.target) { S.sheet = ''; drawLayer(); } return; }
    if (d.menu) { S.menu = S.menu === d.menu ? '' : d.menu; drawAll(); return; }
    if (t.matches('.brand') || d.home !== undefined) { e.preventDefault(); S.menu = ''; if (location.hash === '#home') route(); else location.hash = 'home'; return; }
    if (d.gothis !== undefined) { S.menu = ''; location.hash = S.tab || 'questions'; if (!S.home) drawAll(); return; }
    if (d.tab && t.matches('.pm-tab')) { S.menu = ''; ctx.go(d.tab); drawAll(); return; }
    if (d.tab && t.matches('.tab')) { ctx.go(d.tab); return; }
    if (d.send !== undefined) {
      S.menu = ''; drawAll();
      if (!S.sendN || !sendP) return toast('Nothing is ready to send yet');
      return Promise.resolve().then(() => sendP.open(ctx)).catch(err => toast('Send could not open: ' + err.message));
    }
    if (t.id === 'p-fab') { return sendP && Promise.resolve().then(() => sendP.open(ctx)); }
    if (d.recheck !== undefined) {
      if (S.newer) { S.loadedV = S.newer.v; S.newer = null; for (const k in cache) delete cache[k]; api.meta().then(m => { S.meta = m; }).finally(() => { route(); toast('Loaded the newer version'); }); return; }
      checkNewer().then(found => { drawTop(); if (!found) toast('Up to date'); });
      return;
    }
    if (d.sheet) { S.sheet = d.sheet; S.menu = ''; S.pErr = ''; drawAll(); return; }
    if (d.close !== undefined) { S.sheet = ''; drawLayer(); return; }
    if (d.copylink !== undefined) {
      const done = () => toast('Link copied');
      (navigator.clipboard ? navigator.clipboard.writeText(location.href) : Promise.reject()).then(done, () => toast('Copy did not work here: ' + location.href));
      return;
    }
    if (d.signout !== undefined) { S.menu = ''; drawAll(); inert('Signed out'); return; }
    if (d.setTheme) { prefs.set('theme', d.setTheme); applyTheme(d.setTheme); drawAll(); return; }
    if (d.fs) { setFs(prefs.get('fs', 100) + +d.fs); drawAll(); return; }
    if (d.fsset) { setFs(d.fsset); drawAll(); return; }
    if (d.zdef) { prefs.set('zoomDef', +d.zdef); drawAll(); return; }
    if (d.prole) { const [i, r] = d.prole.split('~'), x = S.people[+i], was = x.role; x.role = r; drawLayer(); inert(`${x.n}: ${ROLE[r].toLowerCase()}`, () => { x.role = was; drawLayer(); }); return; }
    if (d.prm) { const i = +d.prm, x = S.people[i]; S.people.splice(i, 1); drawLayer(); inert(`${x.n} removed`, () => { S.people.splice(i, 0, x); drawLayer(); }); return; }
    if (d.pnewrole) { S.newRole = d.pnewrole; drawLayer(); return; }
    if (d.padd !== undefined) {
      const v = (document.getElementById('p-newperson').value || '').trim();
      S.pErr = /^[^@\s]+@[^@\s]+\.\w+$/.test(v) ? '' : 'Type their full Google email address.';
      if (!S.pErr && S.people.some(x => x.n.toLowerCase() === nameOf(v).toLowerCase())) S.pErr = `${nameOf(v)} is already on the list.`;
      if (!S.pErr) { const n = nameOf(v), role = S.newRole || 'view'; S.people.push({n, role}); inert(`${n} added: ${ROLE[role].toLowerCase()}`, () => { S.people = S.people.filter(x => x.n !== n); drawLayer(); }); }
      drawLayer(); return;
    }
  }
  function onChange(e) {
    const t = e.target, d = t.dataset;
    if (d.fsin !== undefined) { setFs(parseInt(t.value, 10)); drawAll(); return; }
    if (d.optsfirst !== undefined) { prefs.set('optsFirst', t.checked); document.body.classList.toggle('opts-first', t.checked); return; }
    if (d.rem) { prefs.set('rem', {...REM, ...prefs.get('rem', {}), [d.rem]: t.checked}); return; }
  }
  const typing = el => el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
  function onKey(e) {
    if (e.key === 'Escape' && (S.menu || S.sheet)) { S.menu = ''; S.sheet = ''; drawAll(); return; }
    if (e.key === 'Enter' && e.target.dataset && e.target.dataset.fsin !== undefined) { e.target.blur(); return; }
    if (e.key === '?' && !typing(e.target) && !e.metaKey && !e.ctrlKey) { S.sheet = 'keys'; S.menu = ''; drawAll(); }
  }
  // Phone: the top bar slides away as you scroll down and comes back as you scroll up.
  let lastY = 0;
  function onScroll() {
    const y = scrollY, top = document.getElementById('p-top');
    top.classList.toggle('hid', phoneQ.matches && y > 60 && y > lastY && !S.menu);
    lastY = y;
  }

  const load = (tag, attrs) => new Promise(done => {
    const el = Object.assign(document.createElement(tag), attrs);
    el.onload = done; el.onerror = () => { el.remove(); done(); };  // an area with no file yet is fine
    document.head.appendChild(el);
  });

  async function start() {
    applyTheme(themeMode());
    setFs(prefs.get('fs', 100));
    document.body.classList.toggle('opts-first', !!prefs.get('optsFirst', false));
    matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => applyTheme(themeMode()));
    document.addEventListener('click', onClick);
    document.addEventListener('change', onChange);
    document.addEventListener('keydown', onKey);
    addEventListener('scroll', onScroll, {passive: true});
    phoneQ.addEventListener('change', () => { S.menu = ''; drawAll(); });
    const [meta, who, fd, proj, board] = await Promise.all([api.meta(), api.identity(), data('frame'), api.project(), api.board()].map(p => p.catch(() => null)));
    S.meta = meta; S.loadedV = meta && meta.current; S.who = who; S.fd = fd; S.board = board;
    S.boardUrl = (proj && proj.board && proj.board.url) || (board && board.board && board.board.url) || '';
    document.title = projName() + ' · Agent Annotate';
    await Promise.all(AREAS.flatMap(a => [load('link', {rel: 'stylesheet', href: `proto/${a}.css`}), load('script', {src: `proto/${a}.js`})]));
    started = true;
    route();
    addEventListener('hashchange', route);
    if (sendP) refreshTop();
    setInterval(() => { checkNewer().then(() => { if (!S.menu) drawTop(); }); }, 60000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
