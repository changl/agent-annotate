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
  // the other tabs' chips read their data only once the first reading is in: five reads at once kept Questions' waiting (r12 fix10 slowread)
  let firstRead;
  const firstIn = new Promise(r => { firstRead = r; });
  // and every read the tab on screen does not need (other tabs' chips, the board, the other feeds) waits until that tab has drawn:
  // started together they held its own reads on the server for seconds (r13 speed). Areas wait on P.shown for theirs.
  let shownDone;
  const firstShown = P.shown = new Promise(r => { shownDone = r; });
  setTimeout(() => shownDone(), 4000);  // a tab whose read stalls lets the others read anyway
  P.tab = spec => {
    if (!spec || !byKey[spec.key]) return console.warn('Proto.tab: unknown key', spec && spec.key);
    Object.assign(byKey[spec.key], spec);
    if (started) { drawTabs(); if (!S.home && !S.other && S.tab === spec.key) show(S.tab, null); }
  };
  // The area that owns answering registers Send: count(ctx) -> number ready, open(ctx) opens its Send summary, wrote(path) hears every write,
  // saved(ctx) -> what its sheet lists now from the saved drafts alone, at once (the count until the reads are in).
  let sendP = null;
  P.send = spec => { sendP = spec; if (started) refreshTop(); };
  const sendable = () => !!sendP;  // a read-only copy's Send is simulated by Questions: it writes nothing
  // The one Send queue (r12 fix6): what any tab says "goes with your next Send". An area registers a source,
  // P.queue({items: ctx => [{key, group, html, go(), remove() -> undo or null, note?: comment id}], sent: ctx => {}});
  // Questions lists the items in its Send under their group, counts them, and calls sent() on every source after a Send.
  const SRC = [];
  P.queue = src => { SRC.push(src); refreshSend(); };
  const queued = () => SRC.flatMap(s => { try { return s.items(ctx) || []; } catch (e) { console.warn('queue', e); return []; } });
  // Kept so an area's call does no harm: the frame draws the mock's worker squares itself, per project, with the overview on hover and focus (#12)
  P.bar = () => {};

  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const pl = (n, one, many) => `${Number(n).toLocaleString()} ${n === 1 ? one : many}`;
  const base = location.pathname.replace(/[^/]*$/, '');  // the page's directory URL, always ending in "/"
  // A read-only copy of another project's page is served under <root>/proto/p/<key>/ (frame.py serve_other)
  const COPY = (base.match(/\/proto\/p\/([a-z0-9-]+)\/$/) || [])[1] || '';
  const ROOT = COPY ? base.slice(0, -`proto/p/${COPY}/`.length) : base;
  // The one request wrapper: every write this tab makes, from any tab's module, passes here. own: a write Send's round makes
  // itself. Any other note write made once a round is going waits for it, so it goes with the next Send (r12 audit30 frame 1)
  async function api(path, body, method, own) {
    const write = body !== undefined || !!method;
    // past the round check a write, other than the round's own, that changes a row the round carries never goes: no control can
    // get round the take-back gate (r12 audit35 running 1-4, frame 1-4)
    // by the path without its query: Questions posts to api/comments?author=… (r12 audit36 frame 1, questions 1)
    if (write && own && path.split('?')[0] === 'api/comments' && sendP && sendP.made) sendP.made(body);
    if (write && !own && sendP && sendP.carriesPath && sendP.carriesPath(path, body)) {
      toast('This is already going with Send: it was not taken back');
      return Promise.reject(Object.assign(new Error('already going with Send'), {carried: true}));
    }
    const hold = write && !own && sendP && sendP.hold ? sendP.hold(path) : null;
    if (hold) await hold;
    if (COPY && write && P.copyWrite) { wroteAt = Date.now(); const r = P.copyWrite(path, body, method); wrote(path, own); return r; }  // a read-only copy writes nothing: questions.js answers it in memory
    const opts = !write ? {cache: 'no-store'}
      : {method: method || 'POST', headers: {'Content-Type': 'application/json'}, body: body === undefined ? undefined : JSON.stringify(body), keepalive: method === 'DELETE'};  // a removal finishing as the page closes still lands
    const go = fetch(base + path.replace(/^\//, ''), opts).then(async r => {
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.error || ('HTTP ' + r.status));
      if (write) wrote(path, own);
      return data;
    });
    if (write && sendP && sendP.writing) sendP.writing(path, go, own);  // a write still on its way counts in Send's round check (r12 audit29 questions 1)
    // every read, the version and metadata too, fails after 20 s so its tab or the frame offers Try again; a write is never cut short (r12 audit10 frame 1)
    return write ? go : Promise.race([go, late()]);
  }
  // a note written on any tab changes the next Send: Questions re-reads its notes, and the Send count follows
  const wrote = (path, own) => { if (sendP && sendP.wrote) sendP.wrote(path, own); refreshSend(); };
  // A note removed from Send or its tab leaves the store only once its Undo is gone: Undo keeps the very record, its id, number,
  // time and every field (r12 audit13 frame 4, questions 2). Until then every feed hides it; kept in prefs, a reload hides it too and finishes the removal.
  const TAKEN = new Map(), takenT = {}, TAKE_MS = 10000;  // the Undo toast lasts 9 s
  const keepTaken = () => prefs.set('taken', Object.fromEntries(TAKEN));
  function finishTake(id, own) {
    const path = TAKEN.get(id); clearTimeout(takenT[id]); delete takenT[id];
    if (!path) return Promise.resolve();
    const rm = () => { if (P.notes && P.notes.rmd) P.notes.rmd.add(id); };  // not found: an earlier visit's DELETE already went
    return api(path, undefined, 'DELETE', own).then(rm).catch(e => { if (/not found/i.test(e.message)) rm(); else toast('A note you removed could not be removed: ' + e.message); })
      .finally(() => { TAKEN.delete(id); keepTaken(); });
  }
  const take = (id, path) => {
    // past the round check a note the round carries cannot be taken back: say so and stop the caller before it hides the note or says it was removed (r12 audit31 questions 3)
    if (sendP && sendP.carries && sendP.carries(id)) { toast('This note is already going with Send: it was not removed'); throw Object.assign(new Error('already going with Send'), {carried: true}); }
    TAKEN.set(id, path); keepTaken(); takenT[id] = setTimeout(() => finishTake(id), TAKE_MS);
    const reo = P.notes && P.notes.drop ? P.notes.drop(ctx, id) : () => {};  // its Re-open row leaves Send now; a reload or the DELETE never brings it back (r12 audit44 reference 1)
    refreshSend();
    return () => { clearTimeout(takenT[id]); delete takenT[id]; TAKEN.delete(id); keepTaken(); reo(); refreshSend(); };
  };
  // the refusal above: every Remove caller catches it, so it is said once and never an uncaught exception (r12 audit32 running 5)
  P.carried = e => !!(e && e.carried);
  // a saved-draft list with the removed record id back at its old place, from was (the list before Remove); later changes kept
  P.putBack = (now, was, id) => { const i = was.findIndex(x => x.id === id), l = now.filter(x => x.id !== id); if (i >= 0) l.splice(Math.min(i, l.length), 0, was[i]); return l; };
  // and every read takes his Close and Re-open of this visit first (the notes kit's lc), however late it answers (r12 audit42 reference 1)
  // a read the store answered before its DELETE landed (a reload with the Remove pending) never shows the note again (r12 audit45 questions 2)
  const gone = id => TAKEN.has(id) || !!(P.notes && P.notes.rmd && P.notes.rmd.has(id));
  const unTaken = d => (d = P.notes && P.notes.lc ? P.notes.lc(d) : d) && Array.isArray(d.notes) && d.notes.some(n => gone(n.id)) ? {...d, notes: d.notes.filter(n => !gone(n.id))} : d;
  // Today's page API, as the live shell calls it. Writes land in this copy only; delivery is sandboxed.
  Object.assign(api, {
    meta: () => api('current.meta.json'), comments: () => api('comments.json'), project: () => api('api/project'),
    history: () => api('api/history'), board: () => api('api/board'),
    // the one read per visit, the frame's at load: a tab's first write (Questions' ?author=) waits for no network, so a Save
    // lands before any redraw can close its editor on the old words or a reload can lose it (r12 fix53 questions 3)
    identity: () => api.idP || (api.idP = api('api/identity').catch(e => { api.idP = null; throw e; })),
    capabilities: () => api('api/capabilities'), delivery: () => api('api/delivery'), categories: () => api('api/categories'),
    seen: () => api('api/seen'), readState: () => api('api/read-state'), copy: () => api('api/copy'),
  });
  const cache = {}, failed = new Set();
  const reread = () => { failed.forEach(a => delete cache[a]); failed.clear(); };  // Try again: the failed reads are read afresh
  // on a copy, the notes it simulated join each tab's feed (questions.js P.copyData), so a reload keeps them where they were written
  // a read with no answer in 20 s fails, so the tab offers Try again instead of reading for ever (r12 audit9 reference)
  const late = () => new Promise((_, no) => setTimeout(() => no(new Error('no answer in 20 seconds')), 20000));
  // pre: a read start() began before the tab scripts loaded; the first data() call takes it over (r12 fix12 perf)
  const pre = {};
  let scriptsDone; const scriptsIn = new Promise(r => { scriptsDone = r; });
  const data = (area, fresh) => {
    if (!fresh && cache[area]) return cache[area];
    const got = (!fresh && pre[area]) || api(`proto/data/${area}.json`);
    delete pre[area];
    const p = cache[area] = Promise.race([got, late()])
      // a copy's read waits for the tab scripts: one landing before questions.js would be cached without the copy's notes (r12 audit22 questions 2)
      .then(d => COPY && !P.copyData ? scriptsIn.then(() => d) : d).then(d => unTaken(COPY && P.copyData ? P.copyData(area, d) : d)).catch(e => { if (cache[area] === p) failed.add(area); throw e; });  // a stalled read failing late never marks the fresh one Try again started
    // a failed read stays cached, failed: every later data(area) from any tab gets that failure, and only Try again
    // (reread, or a fresh read) reads again, so a down server is never asked on its own (r12 audit30 questions 4)
    failed.delete(area);
    // Beads follows every board read, Running's Try again too, in the same paint as Tasks, whatever else still loads (r12 audit14 frame 1)
    if (sendP && sendP.read) sendP.read(area, p);  // every new read, first or background, from any tab: Send's one read state (r12 audit29 running 2)
    p.then(() => refreshSend(), () => {});  // a read landing can change what Send lists or offers Remove on: an open sheet follows it (r12 audit22 reference 3)
    p.then(() => { landed[area] = true; }, () => {});
    if (area === 'running') { const n = ++runSeq; p.then(r => n === runSeq && putRun(r), () => n === runSeq && putRun(null, true)); }
    return p;
  };
  let runSeq = 0;
  // a heavy tab's first screen (proto_data/first.py): its whole read once that is in, else a small slice marked part, which the tab
  // draws and then draws the whole read over; the slice is never cached or given to Send (r13 speed)
  const landed = {}, firsts = {};
  const first = area => {
    if (cache[area] && landed[area]) return cache[area];  // a whole read has been in this visit: the tab waits for it, as before
    return firsts[area] || (firsts[area] = Promise.race([api(`proto/data/${area}.first.json`), late()])
      .then(d => COPY && !P.copyData ? scriptsIn.then(() => d) : d).then(d => unTaken(COPY && P.copyData ? P.copyData(area, d) : d))
      .finally(() => { delete firsts[area]; }));
  };
  // Unsent answers, notes and task changes: with "Unsent answers and notes" off they live in memory only, so a reload drops them (#80).
  const DRAFT = /^(q:drafts|q:general|q:newnote|tst|tcm:.*|draft:.*)$/;
  // Settings are his everywhere; everything else (drafts, folds, the open tab, views) belongs to one project's page
  const GLOBAL = /^(theme|fs|rem|optsFirst|zoomDef)$/;
  const store = k => 'annotate-proto:' + (COPY && !GLOBAL.test(k) ? `p/${COPY}:` : '') + k;
  const mem = {};
  const prefs = {
    get(k, d) { if (k in mem) return mem[k] == null ? d : mem[k]; try { const v = JSON.parse(localStorage.getItem(store(k)) || 'null'); return v == null ? d : v; } catch { return d; } },
    set(k, v) {
      if (DRAFT.test(k) && !remember('drafts')) { mem[k] = v; return; }
      delete mem[k];
      try { localStorage.setItem(store(k), JSON.stringify(v)); } catch {}
    },
    // the saved keys matching re: a tab lists its drafts from these before its data is in (r12 fix10 frame 1)
    keys(re) {
      const ks = new Set(Object.keys(mem)), pre = store('');
      try { for (const k of Object.keys(localStorage)) if (k.startsWith(pre)) ks.add(k.slice(pre.length)); } catch {}
      return [...ks].filter(k => re.test(k));
    },
  };
  const REM = {folds: true, tab: true, drafts: true};
  const remember = kind => ({...REM, ...prefs.get('rem', {})})[kind] !== false;
  function dropStoredDrafts() {
    try { Object.keys(localStorage).filter(k => k.startsWith('annotate-proto:') && DRAFT.test(k.slice(15).replace(/^p\/[a-z0-9-]+:/, ''))).forEach(k => localStorage.removeItem(k)); } catch {}
  }
  // Folded sections (#80): every <details> an area draws, by tab and its summary, kept only while the switch is on.
  // Reference draws one item at a time, so its folds belong to that item: two checklists with as many revisions never share one
  const foldBase = d => S.tab + (S.tab === 'reference' ? '/' + (location.hash.split('/')[1] || '') : '') + ':' + (d.id || d.className + ':' + ((d.querySelector('summary') || {}).textContent || '').trim().replace(/\s+/g, ' ').slice(0, 60));
  // folds that look alike (every Analytics "Table") are told apart by their order on the page, so each keeps its own (r12 audit14 frame 3)
  function foldKeys() {
    const seen = {}, m = new Map();
    for (const d of document.querySelectorAll('#p-main details')) { const k = foldBase(d), n = seen[k] = (seen[k] || 0) + 1; m.set(d, n > 1 ? k + '#' + n : k); }
    return m;
  }
  function saveFold(e) {
    const d = e.target;
    if (!(d instanceof HTMLDetailsElement) || !d.closest('#p-main') || S.home || !remember('folds')) return;
    prefs.set('folds', {...prefs.get('folds', {}), [foldKeys().get(d) || foldBase(d)]: d.open});
  }
  function restoreFolds(el) {
    const on = remember('folds'), f = on ? prefs.get('folds', {}) : {}, fresh = el.querySelectorAll('details:not([data-pf])');
    const ks = fresh.length ? foldKeys() : null;
    fresh.forEach(d => { d.dataset.pf = '1'; const v = f[ks.get(d) || foldBase(d)]; if (on && v != null && d.open !== v) d.open = v; });
    // Questions' document sections fold with their own button (data-sfold, aria-expanded): pressed once, the first time each shows (#4)
    if (on) el.querySelectorAll('button[data-sfold]').forEach(b => {
      const k = S.tab + ':s:' + b.dataset.sfold, v = f[k];
      if (v == null || secDone.has(k)) return;
      secDone.add(k);
      if ((b.getAttribute('aria-expanded') === 'true') !== v) b.click();
    });
  }
  const secDone = new Set();
  function saveSecFold(e) {
    const b = e.target.closest && e.target.closest('#p-main button[data-sfold], #p-main [data-secall]');
    if (!b || !e.isTrusted || S.home || !remember('folds')) return;
    const all = [...document.querySelectorAll('#p-main button[data-sfold]')], f = {...prefs.get('folds', {})};
    // one section turns over; "Collapse all" opens every section when none is open, else folds them all
    const opened = b.dataset.sfold != null ? b.getAttribute('aria-expanded') !== 'true' : !all.some(x => x.getAttribute('aria-expanded') === 'true');
    for (const x of b.dataset.sfold != null ? [b] : all) { f[S.tab + ':s:' + x.dataset.sfold] = opened; secDone.add(S.tab + ':s:' + x.dataset.sfold); }
    prefs.set('folds', f);
  }

  let toastTimer, wroteAt = 0, heldTo = 0;
  function toast(msg, opts = {}) {
    // a Send receipt (hold) stays readable: any toast after it, a held Save landing with its own Undo too, shows once it has (r12 audit31 running 6, audit32 running 3)
    const wait = heldTo - Date.now();
    if (!opts.hold && wait > 0) { setTimeout(() => toast(msg, opts), wait); return; }
    if (opts.hold) heldTo = Date.now() + opts.hold;
    const el = document.getElementById('p-toast');
    // On a copy every simulated write says so, whichever tab drew it: an undoable change, or a toast just after a write
    const mark = opts.inert || (COPY && (opts.undo || Date.now() - wroteAt < 3000));
    // a plain notice never takes a pending Undo away: it shows above it for its 5 s, and the Undo stays until used or timed out (r12 audit44 reference 2)
    if (!opts.undo && !opts.hold && el.querySelector('[data-undo]')) {
      const x = document.createElement('div'); x.className = 'p-toast'; x.setAttribute('role', 'status');
      x.innerHTML = `<span>${esc(msg)}</span>${mark ? P.inertMark() : ''}`; el.prepend(x); setTimeout(() => { x.remove(); clearUnder(); }, 5000);
      setTimeout(clearUnder); return;  // after the caller's redraw
    }
    clearTimeout(toastTimer);
    if (S.sentPaint) { S.sentPaint = false; drawTop(); drawFab(); if (S.menu === 'nav') drawLayer(); }  // the last-Send chip changes with the receipt (r12 fix10 frame 4)
    el.innerHTML = `<div class="p-toast" role="status"><span>${esc(msg)}</span>${mark ? P.inertMark() : ''}${opts.undo ? '<button class="lk" data-undo>Undo</button>' : ''}</div>`;
    const undo = el.querySelector('[data-undo]');
    // the one toast Undo gate (r12 audit35 running 1-6): past the round check an Undo of a row the round carries (opts.going: its
    // keys or note ids) is refused and leaves everything as it is; an Undo naming no row is refused while the round is held.
    // going set to false only for an Undo that touches no Send row (test_fix40_send lists them)
    const keys = opts.going === undefined ? [true] : [].concat(opts.going);
    if (undo) undo.onclick = () => { if (P.going && keys.some(k => P.going(typeof k === 'function' ? k() : k))) return; el.innerHTML = ''; clearUnder(); opts.undo(); };
    toastTimer = setTimeout(() => { el.innerHTML = ''; clearUnder(); }, opts.undo ? 9000 : 5000);
    setTimeout(clearUnder);
  }
  // The notices stay where the mock puts them and float over the page as it scrolls under them. At rest no page control sits
  // under them: the page scrolls the least distance that leaves none covered (r12 audit45 frame 2, reference 2). While they
  // show, the page keeps room at its end as tall as their band, so any control can be scrolled clear of them, and only a
  // notice's own box takes the pointer (frame.css) (r12 audit46 running 1). Text lines ([data-line]) are not controls.
  const CTRL = 'a[href],button,input,select,textarea,summary,[role=button]';
  const pinned = e => { for (; e && e !== document.body; e = e.parentElement) if (/fixed|sticky/.test(getComputedStyle(e).position)) return true; return false; };
  function clearUnder() {
    const el = document.getElementById('p-toast'), b = document.body;
    const r = el && el.children.length && !/\b(p-locked|qsheet-open)\b/.test(b.className) ? el.getBoundingClientRect() : null, top = r && r.top - 6, bot = r && r.bottom + 6, R = 600;
    if (!r || !r.height) { b.style.paddingBottom = ''; return; }
    const band = Math.ceil(innerHeight - top);  // the page sets no padding of its own below (frame.css)
    b.style.paddingBottom = band + 'px';
    const cs = [...document.querySelectorAll(CTRL)].map(c => [c, c.getBoundingClientRect()])
      .filter(([c, x]) => x.width && x.height && x.right > r.left && x.left < r.right && x.bottom > top - R && x.top < bot + R && !el.contains(c) && !pinned(c)).map(([, x]) => x);
    const clear = d => cs.every(x => x.bottom - d <= top || x.top - d >= bot);  // d: how far the page scrolls down
    const ds = [0, ...cs.flatMap(x => [x.bottom - top, x.top - bot])].filter(d => d >= -scrollY && Math.abs(d) <= R).sort((p, q) => Math.abs(p) - Math.abs(q));
    const d = ds.find(clear);
    if (!d) return;
    const room = document.documentElement.scrollHeight - innerHeight - scrollY;
    if (d > room) b.style.paddingBottom = band + Math.ceil(d - room) + 'px';
    scrollBy({top: d, behavior: 'instant'});
  }
  // a refused write already said so: a caller that does not catch it logs nothing (r12 audit35 frame 1)
  addEventListener('unhandledrejection', e => { if (P.carried(e.reason)) e.preventDefault(); });
  P.inertMark = () => '<span class="p-inert" title="This prototype never reaches an agent, Orca, Windmill or the board">prototype: not sent</span>';
  // An action that would reach a real agent or system: look done, say so, offer Undo, reach nothing.
  const inert = (msg, undo, going) => toast(msg, {inert: true, undo: undo || (() => {}), going: undo ? going : false});

  const phoneQ = matchMedia('(max-width: 900px)');  // up to 900 the frame folds into its menu: the mock's desk header overflows below 1074 (#8)
  const S = {tab: 'questions', home: false, menu: '', sheet: '', meta: null, loadedV: '', newer: null, checked: '',
    fd: null, who: null, board: null, boardUrl: '', sendN: 0, chips: {}, people: null, sent: prefs.get('lastSend', null),
    countsIn: false, stall: new Map()};  // stall: the frame's first reads that failed, 'version' or 'counts' -> why
  const ctx = {
    base, api, data, first, prefs, esc, toast, inert, remember,
    icon: (n, l) => P.icon(n, l),
    go(tab, anchor) { location.hash = tab + (anchor ? '/' + encodeURIComponent(anchor) : ''); },
    goTo: id => goTarget(id, () => true),
    get phone() { return phoneQ.matches; },
    get me() { return COPY ? 'You' : myName(); },  // his reply's author as the store names it: a copy names his notes You (r12 audit46 running 2)
    refreshChips: () => { drawTabs(); refreshTop(); },
    // take(id, path) -> Undo: the note is hidden now and its DELETE goes when Undo is gone; taken(id); takeNow(): every pending one goes (before a Send)
    take, taken: id => TAKEN.has(id), takeNow: () => Promise.all([...TAKEN.keys()].map(id => finishTake(id, true))),  // Send's own: its round waits for them
    refreshTop: () => refreshTop(),
    // n: the items just sent; the header and the phone menu show this round as the last Send (r12 fix7 frame 3), after a reload too (r12 fix8 frame 4)
    // what was queued went: Send reads 0 with the receipt, not after the re-read (r12 fix11 frame 1)
    // sig: a row's full words (say) or, with none, its listing: the round check and the clear compare these, never a shortened preview (r12 audit31 questions 2)
    sig: x => x.say || x.html,
    // done(key): the row went with this round as it reads now; a row changed or added after the round check stays (r12 audit31 running 1, 4)
    // a round that failed after its check delivered nothing: every row with a base (a Copy library choice, an approval, a recovery
    // request, a task status or comment) that reads as its last delivered words (sentSig) is no change, so it drops off (r12 audit35 running 7)
    queueFailed: () => { const went = prefs.get('sentSig', {});
      SRC.forEach(s => { try { if (s.failed) s.failed(ctx); for (const x of s.items(ctx) || []) if (!x.note && !x.save && x.remove && went[x.key] != null && went[x.key] === ctx.sig(x)) x.remove(); } catch (e) { console.warn('queue failed', e); } });
      refreshSend(); },
    queueWent: was => { if (!was) return; const went = prefs.get('sentSig', {}); for (const [k, sig] of was) went[k] = sig; prefs.set('sentSig', went); },
    queued, queueSent: (n, was) => { if (n) { prefs.set('lastSend', S.sent = {ts: new Date().toISOString(), n}); S.sentPaint = true; S.sendN = 0; } SRC.forEach(s => { try { if (!s.sent) return; const now = new Map((s.items(ctx) || []).map(x => [x.key, ctx.sig(x)])); s.sent(ctx, was, k => !was || (was.has(k) && was.get(k) === now.get(k))); } catch (e) { console.warn('queue sent', e); } }); if (sendP && sendP.saved) S.sendN = savedN(); paintSend(); refreshSend(); },  // a noop too: the top count follows the store at once (r12 audit23 frame 2)
  };
  P.ctx = ctx;
  P.frameState = S;  // for tests and screenshots only
  const I =(n, l) => P.icon(n, l);

  /* ---------- tabs and their chips ---------- */
  // A chip is {text, tone, title} or {empty: true}; empty dims the tab and reads "nothing yet" (#93).
  const chipHtml = c => !c ? '' : c.empty ? '<span class="ct none">nothing yet</span>'
    : c.text == null || c.text === '' ? '' : `<span class="ct ${esc(c.tone || '')}"${c.title ? ` title="${esc(c.title)}"` : ''}>${esc(c.text)}</span>`;
  // A project with no copy here: every tab dimmed, "nothing yet" (#1, #93)
  const chipOf = key => !S.other ? S.chips[key] : {empty: true};
  function paintChip(key) {
    const c = chipOf(key);
    document.querySelectorAll(`#p-top [data-chip="${key}"], #p-tabs [data-chip="${key}"], #p-layer [data-chip="${key}"]`).forEach(el => { el.innerHTML = chipHtml(c); });
    document.querySelectorAll(`.tab[data-tab="${key}"], .pm-tab[data-tab="${key}"]`).forEach(el => el.classList.toggle('empty', !!(c && c.empty)));
  }
  function drawTabs() {
    const nav = document.getElementById('p-tabs');
    nav.hidden = S.home;
    nav.innerHTML = TABS.map(t => `<button class="tab ${t.tone}" role="tab" data-tab="${t.key}" aria-selected="${!S.home && t.key === S.tab}">${I(t.icon)}<span class="tl">${esc(t.label)}</span><span class="cw" data-chip="${t.key}"></span></button>`).join('');
    for (const t of TABS) {
      paintChip(t.key);
      if (t.chip && !S.other) (t.key === 'questions' ? Promise.resolve() : Promise.all([firstIn, firstShown])).then(() => t.chip(ctx)).then(c => {
        S.chips[t.key] = c == null || c === '' ? null : typeof c === 'object' ? c : {text: String(c)};
        if (!S.other) paintChip(t.key);
        refreshSend();  // its tab's data is in: the drafts it restored now count in Send (r12 audit7 frame 2)
      }).catch(e => console.warn('chip', t.key, e));
    }
  }

  // Scroll to an element's top, clear of the pinned frame (scroll-padding) and of a tab's own pinned bar such as Questions' strip (#6, #7)
  function scrollClear(el) {
    el.scrollIntoView({block: 'start'});
    const r = el.getBoundingClientRect();
    let c = document.elementFromPoint(Math.max(0, Math.min(r.left + 8, innerWidth - 1)), Math.max(0, r.top + 2));
    while (c && c !== document.body && !/sticky|fixed/.test(getComputedStyle(c).position)) c = c.parentElement;
    if (c && c !== document.body && !c.contains(el) && !el.contains(c)) scrollBy(0, r.top - c.getBoundingClientRect().bottom - 8);
  }
  // Go to it: its card or note can land after the render (a cold read, a draw a later one replaced): wait for it, then scroll to it
  // and outline it, again on the node a redraw puts in its place (r12 audit23 questions 1)
  function goTarget(id, live) {
    const t0 = Date.now(); let lit = null, at = 0;
    const tick = () => {
      const el = live() && document.getElementById(id);
      if (el && el !== lit) {
        const r = el.getBoundingClientRect();
        if (!lit || r.bottom < 0 || r.top > innerHeight) scrollClear(el);
        if (!lit) at = Date.now();
        el.classList.add('qlit'); lit = el;
      }
      if (lit && Date.now() - at > 2500) { const x = document.getElementById(id); if (x) x.classList.remove('qlit'); return; }
      if (!live() || !lit && Date.now() - t0 > 20000) return;
      setTimeout(tick, 100);
    };
    tick();
  }
  function show(key, anchor) {
    const t = byKey[key] || TABS[0];
    S.tab = t.key;
    document.querySelectorAll('.tab[data-tab], .pm-tab[data-tab]').forEach(b => b.setAttribute('aria-selected', String(!S.home && b.dataset.tab === S.tab)));
    const el = document.getElementById('p-main');
    el.className = 'p-main area-' + t.area + ' tab-' + t.key;
    if (!t.render) {
      shownDone();
      el.innerHTML = `<div class="p-empty">${I(t.icon)}<p>${esc(t.label)}: not built yet.</p></div>`;
      if (t.key === 'questions') questionsPreview(el);
      return;
    }
    // Each render draws into its own box: when the tab changes first, the next draw drops that box,
    // so a render that finishes late paints off-page, never over the tab he opened (Running fixer R2).
    el.innerHTML = '';
    const view = el.appendChild(Object.assign(document.createElement('div'), {className: 'p-view area-' + t.area + ' tab-' + t.key}));
    const live = () => view.isConnected;
    Promise.resolve().then(() => t.render(view, ctx, anchor)).then(() => {
      shownDone();
      if (live() && anchor && /^[qn]-/.test(anchor)) goTarget(anchor, live);
      else { const target = live() && anchor && document.getElementById(anchor); if (target) scrollClear(target); }
    }).catch(e => {
      shownDone();
      if (!live()) return;
      view.innerHTML = `<div class="p-empty">${I('warn')}<p>${esc(t.label)} could not be read: ${esc(e.message)}</p><button class="btn sm" data-again>Try again</button></div>`;
      view.querySelector('[data-again]').onclick = () => { reread(); again(); route(); };  // the failed reads are dropped, so this reads afresh, the frame's stalled reads too
      console.error(e);
    });
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
  const curName = () => S.other ? S.other.name : projName();
  const myName = () => (S.who && S.who.name) || 'You';
  // One waiting count: the Questions tab's, with his unsent answers; the server's same rule until it loads.
  const waitingHere = () => S.qWait != null ? S.qWait : (S.fd && S.fd.waiting) || 0;
  const projs = () => ((S.fd && S.fd.projects) || []).map(x => x.this ? {...x, waiting: waitingHere()} : x);
  // One ready count: Running's, read from the board with `bd ready`.
  const readyHere = () => S.ready != null ? S.ready : null;
  const copyingText = () => `Copying version ${S.copying.replace(/^v/, '')} from the real page; this copy shows its current version until then.`;
  function reloadBtn() {
    const nw = S.newer;
    if (nw) return `<button class="rl2 new" data-recheck title="A newer version is ready. Red: ${pl(nw.n, 'new question', 'new questions')}. Amber: ${pl(nw.fix, 'fix', 'fixes')} to your notes. Press to load it; your place and what you typed are kept." aria-label="Load the newer version: ${pl(nw.n, 'new question', 'new questions')}, ${pl(nw.fix, 'fix', 'fixes')}">${I('reload')}${nw.n ? `<span class="n q">${nw.n}</span>` : ''}${nw.fix ? `<span class="n f">${nw.fix}</span>` : ''}</button>`;
    if (S.copying) return `<button class="rl2 cp" data-recheck title="${esc(copyingText())} Reload turns blue when it is ready." aria-label="${esc(copyingText())} Check again">${I('reload')}<span>Copying ${esc(S.copying.replace(/^v/, ''))}…</span></button>`;
    // "Up to date" only once a check confirmed it: until then a copy may be behind its real page (r12 audit10 frame 5)
    if (!S.checked) return `<button class="rl2" data-recheck title="Checking for a newer version. The icon turns blue when one is ready; the page changes only when you press it." aria-label="Check for a newer version">${I('reload')}</button>`;
    return `<button class="rl2" data-recheck title="Up to date, checked at ${S.checked}. The icon turns blue when the agent publishes a newer version; the page changes only when you press it." aria-label="Up to date. Check for a newer version">${I('reload')}</button>`;
  }
  // the projects, as rows: the project dropdown and the phone's menu share them (mock: projRows)
  const isCur = x => !S.home && (x.this ? !S.other : S.other && S.other.key === x.key);
  // a prototype page of its own (the FastLane Drive copy, a read-only copy): a link to it; any other project: its summary here
  const projOpen = (x, tag, cls, inner) => x.href != null && !x.this
    ? `<a class="${cls}" ${tag} href="${esc(ROOT + x.href)}#questions">${inner}</a>`
    : `<button class="${cls}" ${tag} ${x.this ? 'data-gothis' : `data-proj="${esc(x.key)}"`}>${inner}</button>`;
  function projRows() {
    return projs().map(x => { const st = (workersOf(x.code) || []).filter(w => w.s === 'stuck').length;
      return projOpen(x, `role="menuitem"${isCur(x) ? ' aria-current="page"' : ''}`, 'mi', `<span class="nm">${esc(x.name)}</span>${x.waiting ? `<span class="badge qw" title="${pl(x.waiting, 'question waits', 'questions wait')} for your answer">${x.waiting} waiting</span>` : ''}${st ? `<span class="badge warn" title="${pl(st, 'worker has', 'workers have')} shown no sign of life">${st} no sign of life</span>` : ''}`); }).join('');
  }

  /* ---------- workers and scheduled jobs, from Running's data (mock: workerDots, wkCard) ---------- */
  const SL = {working: 'working', stuck: 'no sign of life', failed: 'failed', done: 'done', later: 'later', stopped: 'stopped'};
  const WORDER = ['failed', 'stuck', 'working', 'later', 'done', 'stopped'];
  const MODEL = {'claude-opus-5-5': 'Opus 5.5', 'claude-opus-5': 'Opus 5', 'claude-fable-5-2': 'Fable 5.2', 'gpt-6.1-sol': 'GPT-6.1 Sol', 'gpt-6.2-sol': 'GPT-6.2 Sol'};
  const dur = m => m < 60 ? `${Math.round(m)} min` : m < 48 * 60 ? `${Math.round(m / 6) / 10} h` : `${Math.round(m / 1440)} days`;
  const thisCode = () => ((projs().find(x => x.this) || {}).code) || 'fld';
  // running.json keeps workers by Mac, every project's; null until it is read
  function workersOf(code) {
    const w = S.run && S.run.workers;
    const all = Array.isArray(w) ? w : w && typeof w === 'object' ? Object.entries(w).flatMap(([mac, v]) => ((v && v.workers) || []).map(x => ({...x, mac}))) : null;
    return all && all.filter(x => x.proj === code).map(x => ({...x, s: x.s || x.state || 'working'}));
  }
  // Running reads every enabled schedule in the Windmill workspace; each belongs to a project by its folder (#9).
  // shortcut: folders by path, until a schedule carries its project; no folder is Rebex's
  const JOBP = [[/^f\/(fld_ops|sweep|uat|usage|ops)\//, 'fld'], [/^f\/test\//, 'annotate'], [/^u\/[^/]+\/mac_daily_update$/, 'multimac'], [/^u\/[^/]+\/windmill_/, 'windmill']];
  const jobProj = p => (JOBP.find(([re]) => re.test(p || '')) || [])[1] || 'other';
  const jobsOf = code => S.run && Array.isArray(S.run.jobs) && code && code !== 'other' ? S.run.jobs.filter(j => jobProj(j.path) === code) : null;
  const countBy = ws => ws.reduce((c, w) => (c[w.s] = (c[w.s] || 0) + 1, c), {});
  const curCode = () => S.other ? S.other.code : thisCode();
  const runHash = anchor => S.other ? `project/${S.other.key}/running` : 'running' + (anchor ? '/' + anchor : '');
  function wkCard(ws, c, fail) {
    const states = WORDER.filter(s => c[s]);
    const bar = o => `<span class="wc-bar">${states.filter(s => o[s]).map(s => `<i class="${s}" style="flex:${o[s]}" title="${o[s]} ${SL[s]}"></i>`).join('')}</span>`;
    // workers at once in each of the last 24 hours, from how long each has run
    const now = Date.now(), st = w => now - (w.mins || 0) * 6e4, live = w => w.s === 'working' || w.s === 'stuck';
    const hrs = Array.from({length: 24}, (_, h) => { const a = now - (24 - h) * 36e5, b = a + 36e5; return ws.filter(w => st(w) < b && (live(w) ? now : st(w) + Math.max(1, w.heard != null && !live(w) ? (w.mins || 1) - w.heard : (w.mins || 1)) * 6e4) > a).length; });
    hrs[23] = Math.max(hrs[23], ws.filter(live).length);
    const mx = Math.max(1, ...hrs);
    const sp = `<svg class="wc-sp" viewBox="0 0 240 26" preserveAspectRatio="none" role="img" aria-label="Most workers at once in the last 24 hours: ${mx}">${hrs.map((n, i) => `<rect class="${i === 23 ? 'now' : ''}" x="${i * 10}" y="${26 - Math.max(n ? 2 : 0, n / mx * 24)}" width="8" height="${Math.max(n ? 2 : 0, n / mx * 24)}"><title>${23 - i ? `${23 - i} h ago` : 'this hour'}: ${pl(n, 'worker', 'workers')}</title></rect>`).join('')}</svg><div class="wc-spl"><span>24 h ago</span><span>now · most at once: ${pl(Math.max(...hrs), 'worker', 'workers')}</span></div>`;
    const macs = {}; ws.forEach(w => { const m = macs[w.mac || 'This Mac'] = macs[w.mac || 'This Mac'] || {n: 0}; m.n++; m[w.s] = (m[w.s] || 0) + 1; });
    const top = [...ws].sort((a, b) => WORDER.indexOf(a.s) - WORDER.indexOf(b.s) || (a.mins || 0) - (b.mins || 0)).slice(0, 6);
    const mdl = w => MODEL[w.model] || (w.agent ? w.agent[0].toUpperCase() + w.agent.slice(1) : '');
    const row = w => `<button class="wc-row" data-go="${runHash('workers')}" title="${esc(w.name)}"><i class="dt ${esc(w.s)}"></i><span class="nm">${esc(w.name)}</span><span class="mt">${mdl(w) ? `<span class="mdl">${esc(mdl(w))}</span>` : ''}<span title="${w.s === 'working' ? 'Running for' : 'Ran for'}">${dur(w.mins || 0)}</span></span><span class="rp">${w.s === 'stuck' ? `<span class="stuck-t">no sign of life for ${dur(w.heard || 0)}</span> · ` : ''}${esc(w.report ? w.report.slice(0, 70) : 'no report yet')}</span></button>`;
    return `<div class="hpop wcard" role="tooltip"><div class="wc-top"><b>${pl(ws.length, 'worker', 'workers')}</b><span class="small mut">on ${pl(Object.keys(macs).length, 'Mac', 'Macs')}</span></div>
      ${bar(c)}<div class="wc-leg">${states.map(s => `<span><i class="dt ${s}"></i>${c[s]} ${SL[s]}</span>`).join('')}</div>
      <div class="hp-h">Workers at once, last 24 hours</div>${sp}
      <div class="hp-h">By Mac</div><div class="wc-mac">${Object.entries(macs).sort((a, b) => b[1].n - a[1].n).map(([m, o]) => `<span>${esc(m)}</span>${bar(o)}<span class="small mut">${o.n}</span>`).join('')}</div>
      <div class="hp-h">${c.failed || c.stuck ? 'Needs a look first' : 'Latest'}</div>${top.map(row).join('')}
      ${fail.length ? `<div class="hp-h">Scheduled jobs failing</div>${fail.map(j => `<button class="wc-row" data-go="${runHash('jobs')}"><i class="dt job"></i><span class="nm">${esc(j.name)}</span><span class="mt"></span></button>`).join('')}` : ''}
      <div class="small mut" style="margin-top:4px">${ws.length > top.length ? `${pl(ws.length - top.length, 'more worker', 'more workers')} under Running · ` : ''}click to open them there</div></div>`;
  }
  // one dot per worker up to 12; past 12 a grid of small squares six rows high, with the counts that need a look (#95, #131)
  function workerDots() {
    if (!S.run) return '';
    const code = curCode(), ws = workersOf(code) || [], fail = (jobsOf(code) || []).filter(j => j.failing), MAX = 12;
    const sorted = [...ws].sort((a, b) => WORDER.indexOf(a.s) - WORDER.indexOf(b.s)), c = countBy(ws);
    const sum = ws.length ? Object.entries(c).map(([s, n]) => `${n} ${SL[s]}`).join(', ') : 'no workers running';
    const dot = w => `<button class="wd" data-go="${runHash('workers')}" title="${esc(w.name)}: ${esc(SL[w.s] || w.s)}" aria-label="${esc(w.name)}: ${esc(SL[w.s] || w.s)}"><i class="dt ${esc(w.s)}"></i></button>`;
    const job = j => `<button class="wd jd" data-go="${runHash('jobs')}" title="Scheduled job failing: ${esc(j.name)}" aria-label="Scheduled job failing: ${esc(j.name)}"><i class="dt job"></i></button>`;
    const viz = ws.length <= MAX ? sorted.map(dot).join('') : `<button class="wkg" data-go="${runHash('workers')}" aria-label="${pl(ws.length, 'worker', 'workers')}: ${esc(sum)}. Open them under Running">${sorted.map(w => `<i class="${esc(w.s)}"></i>`).join('')}</button><span class="wcnt">${['failed', 'stuck', 'working'].filter(s => c[s]).map(s => `<span title="${c[s]} ${SL[s]}"><i class="dt ${s}"></i>${c[s]}</span>`).join('')}<span class="tot hide-ph" title="${pl(ws.length, 'worker', 'workers')} in all">${pl(ws.length, 'worker', 'workers')}</span></span>`;
    return `<span class="wdots hov" role="group" aria-label="Workers: ${esc(sum)}">${ws.length ? viz : `<span class="small mut wd0" title="No workers running">no workers</span>`}${fail.length ? `<span class="wsep" aria-hidden="true"></span>${fail.map(job).join('')}<span class="wcnt"><span class="tot jf err-t" title="${pl(fail.length, 'scheduled job is', 'scheduled jobs are')} failing">${pl(fail.length, 'job failing', 'jobs failing')}</span></span>` : ''}${ws.length || fail.length ? wkCard(ws, c, fail) : ''}</span>`;
  }

  /* ---------- the bead board: ready, waiting on you, a hover breakdown; it opens under Running (#36, #65, #122) ---------- */
  const board = () => (S.run && S.run.board) || null;
  const waitTasks = () => { const b = board(); return b && Array.isArray(b.waiting) ? [...b.waiting].sort((a, c) => (c[2] ? 1 : 0) - (a[2] ? 1 : 0)) : []; };
  function beadsCtl(phone) {
    const b = board(), ready = readyHere(), wy = waitTasks(), wyN = wy.length;
    if (S.other || (!b && !S.boardUrl && !prefs.get('hadBoard', false))) return '';
    // an unread board has no counts: never "Nothing ready" or "0 tasks", as Tasks (r12 fix14 frame)
    // before its first read the board is unknown, not empty: Questions' read may hold it back (r12 audit13 frame 2)
    const unread = !!(S.runErr || (b && b.error)), unknown = !b && !unread;
    const noRead = unread ? 'The board could not be read just now.' : 'Reading the board…';
    if (unread || unknown) {
      const lbl = `Beads: ${noRead} Opens Running${unread ? ' to try again' : ''}`, tag = unread ? 'not read' : '…', tcls = unread ? 'badge' : 'badge grey';
      if (phone) return `<button class="btn" data-go="running/tasks" aria-label="${lbl}">${I('bead')} Beads <span class="${tcls}">${tag}</span></button>`;
      return `<span class="hov hide-ph bdchip"><button class="btn ghost" data-go="running/tasks" aria-label="${lbl}">${I('bead')}<span class="bl">Beads</span>${unknown ? '<span class="badge grey" title="Reading the board">…</span>' : ''}</button><div class="hpop" role="tooltip"><b>Bead board</b><div class="small mut">${noRead}</div>
      <button class="hp-t" data-go="running/tasks">${unread ? 'Open Running to try again' : 'Open the board under Running'}</button></div></span>`;
    }
    const wait = wyN ? `<button class="btn ghost" data-go="running/waiting" title="${pl(wyN, 'task', 'tasks')} on the bead board wait on you. Opens Running at Waiting" aria-label="${pl(wyN, 'task waits', 'tasks wait')} on you: open Running at Waiting"><span class="badge wait">${wyN} waiting</span></button>` : '';
    if (phone) return `<button class="btn" data-go="running/tasks">${I('bead')} Beads${ready != null ? ` <span class="badge ok">${ready} ready</span>` : ''}</button>${wait.replace('btn ghost', 'btn')}`;
    const bt = id => (b && b.beads && b.beads[id]) || {};
    const cut = (s, n) => s.length > n ? s.slice(0, n - 1) + '…' : s;
    const rdy = b ? (b.tasks || []).filter(t => t.g === 'ready' && !t.chore) : [], wyM = wy.filter(x => x[2]).length;
    const open = b ? (b.tasks || []).length : 0;
    const pop = `<div class="hpop" role="tooltip"><b>Bead board</b>${wyN ? `<div class="hp-h">Waiting${wyM ? ` · ${pl(wyM, 'merge', 'merges')} among them` : ''}</div>${wy.slice(0, 3).map(([id, , mg]) => `<button class="hp-t" data-go="running/waiting">${mg ? 'Merge: ' : ''}${esc(cut(bt(id).t || id, 52))} <span class="bid">· ${esc(id)}${bt(id).st ? ' · ' + esc(bt(id).st) : ''}</span></button>`).join('')}${wyN > 3 ? `<div class="small mut">and ${wyN - 3} more, all listed at the top of Running</div>` : ''}` : ''}
      <div class="hp-h">Ready to start</div>${rdy.slice(0, 5).map(t => `<button class="hp-t" data-go="running/tasks">${esc(cut(t.title || t.id, 52))} <span class="bid">· ${esc(t.id)} · ready</span></button>`).join('') || '<div class="small mut">Nothing ready</div>'}
      <div class="small mut" style="margin-top:4px">${pl(open, 'task not closed', 'tasks not closed')} on the board · click a count to open the board under Running${S.boardUrl ? ` · <a href="${esc(S.boardUrl)}" target="_blank" rel="noopener">the separate board ↗</a>` : ''}</div></div>`;
    return `<span class="hov hide-ph bdchip"><button class="btn ghost" data-go="running/tasks" aria-label="Bead board${ready != null ? ': ' + pl(ready, 'task ready', 'tasks ready') : ''}${wyN ? `, ${wyN} waiting` : ''}. Opens the board under Running">${I('bead')}<span class="bl">Beads</span>${ready != null ? `<span class="badge ok" title="${pl(ready, 'task is', 'tasks are')} ready to start on the bead board">${ready} ready</span>` : ''}</button>${wait}${pop}</span>`;
  }

  /* ---------- the last Send, in the header (catalog 14, 72) ---------- */
  const DELIV = {acknowledged: 'read by the agent', accepted: 'delivered', started: 'agent working on it', pending: 'saved, agent not told yet', queued: 'saved, agent not told yet', active_monitor: 'delivered', uncertain: 'not confirmed yet', superseded: 'not delivered: the page changed agents'};
  function lastSendChip(cls = 'hide-ph') {
    const r = S.fd && S.fd.lastSend, l = S.deliv, s = S.sent;
    // a round sent in this visit outranks an older record: it is simulated here, so it never claims delivery (r12 fix7 frame 3)
    if (s && (COPY || !l || !(new Date(l.updated_at || l.created_at) >= new Date(s.ts) - 5000))) {
      const t = new Date(s.ts), at = t.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
      return `<span class="chip ${cls} sentchip" title="Your last Send, ${esc(t.toLocaleString())}: ${esc(pl(s.n, 'item', 'items'))}, simulated on this copy. Nothing reached an agent.">Sent ${esc(at)} · prototype: not sent</span>`;
    }
    if (!r && !l) return '';
    const iso = (l && (l.updated_at || l.created_at)) || r.ts, t = new Date(iso), st = (l && l.state) || r.delivery;
    if (isNaN(t)) return '';
    const today = t.toDateString() === new Date().toDateString();
    const at = today ? t.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'}) : t.toLocaleDateString([], {day: 'numeric', month: 'short'});
    const word = l && l.delivered ? 'delivered' : DELIV[st] || 'saved';
    const tone = /^not delivered/.test(word) ? 'err' : /delivered|read|working/.test(word) ? 'ok' : '';
    return `<span class="chip ${cls} sentchip ${tone}" title="Your last Send, ${esc(t.toLocaleString())}: ${esc(word)}. On this copy nothing reaches an agent.">Sent ${esc(at)} · ${esc(word)}</span>`;
  }
  function settingsBody() {
    const fs = prefs.get('fs', 100), theme = themeMode(), rem = {...REM, ...prefs.get('rem', {})}, z = prefs.get('zoomDef', 50);
    const th = [['light', 'sun', 'Light'], ['dark', 'moon', 'Dark'], ['system', 'sys', 'System: follows your Mac, iPad or phone']];
    const tg = (attr, t, tip, on) => `<label class="tgl"${tip ? ` title="${esc(tip)}"` : ''}><span>${t}</span><input type="checkbox" role="switch" ${attr}${on ? ' checked' : ''}><i aria-hidden="true"></i></label>`;
    const n = S.people ? S.people.length : 1;
    return `<div class="me-h"><span class="av big" aria-hidden="true">${esc(myName()[0])}</span><span class="grow"><b>${esc(myName())}</b><span class="small mut">${S.who && S.who.authenticated ? 'Signed in' : 'On this Mac'}</span></span><span class="me-ic">
      <button class="icb" data-sheet="keys" title="Keyboard shortcuts" aria-label="Keyboard shortcuts">${I('keys')}</button>
      ${S.home ? '' : `<button class="icb" data-sheet="people" title="People on ${esc(curName())}: ${pl(n, 'person', 'people')}" aria-label="People on ${esc(curName())}">${I('people')}</button>`}
      <button class="icb" data-copylink title="Copy a link to this page" aria-label="Copy a link to this page">${I('link')}</button>
      <button class="icb" data-signout title="Sign out" aria-label="Sign out">${I('out')}</button></span></div>
    <div class="sep"></div>
    <div class="srow2"><span class="sl">Theme</span><span class="seg ic3" role="group" aria-label="Theme">${th.map(([t, i, l]) => `<button data-set-theme="${t}" aria-pressed="${theme === t}" title="${l}" aria-label="${l}">${I(i)}</button>`).join('')}</span></div>
    <div class="srow2"><span class="sl">Text size</span><span class="fsbox"><button data-fs="-10" title="Smaller text" aria-label="Smaller text">−</button><input type="text" data-fsin inputmode="numeric" value="${fs}%" aria-label="Text size: pick a step or type a percentage" title="Pick a step or type a percentage from 70 to 160"><span class="fslist" role="listbox" aria-label="Text size steps">${[80, 90, 100, 110, 125, 150].map(v => `<button data-fsset="${v}" role="option" aria-current="${v === fs}">${v}%</button>`).join('')}</span><button data-fs="10" title="Larger text" aria-label="Larger text">+</button></span></div>
    <div class="srow2"><span class="sl">Pictures open at</span><span class="seg zs" role="group" aria-label="Full-size pictures open at">${[25, 50, 75, 100].map(v => `<button data-zdef="${v}" aria-pressed="${v === z}" title="Open full-size pictures at ${v}% of the screen width; each picture keeps its own zoom buttons">${v}%</button>`).join('')}</span></div>
    <div class="sep"></div>
    <div class="tgls">${tg('data-optsfirst', 'Options first', "Show each card's choices above its pictures and text", prefs.get('optsFirst', false))}</div>
    <h3>Remember after a reload</h3><div class="tgls">${tg('data-rem="folds"', 'Folded sections', '', rem.folds)}${tg('data-rem="tab"', 'Open tab', '', rem.tab)}${tg('data-rem="drafts"', 'Unsent answers and notes', '', rem.drafts)}</div>
    ${S.home ? '' : `<div class="srow2 small me-ag">${I('agent')}<span class="sl">${ownerLine()}</span>${P.inertMark()}</div>`}`;
  }
  // the agent session that owns the page, and its last sign of life (mock: "Your Send goes to <owner> · alive today")
  const AGENT = {claude: 'Claude', codex: 'Codex'};
  function ownerLine() {
    const p = S.other || projs().find(x => x.this), o = p && p.owner;
    if (!o) return 'No agent session is running: your Send waits until one starts';
    const who = `${esc(p.this ? projName() : p.name)}'s ${esc(AGENT[o.agent] || 'agent')} session`;
    const t = new Date(o.at), since = isNaN(t) ? '' : t.toDateString() === new Date().toDateString() ? 'today' : 'since ' + t.toLocaleDateString([], {day: 'numeric', month: 'short'});
    return o.alive === false ? `Your Send goes to ${who} · not running now: it waits until the session starts again`
      : o.alive ? `Your Send goes to ${who} · alive now` : `Your Send goes to ${who}${since ? ' · claimed the page ' + since.replace('since ', 'on ') : ''}`;
  }
  // One Send state for the header, the phone menu and the floating button (r12 audit11 frame 1, questions 1, reference 2, running 1):
  // '' shows the count; "…" while the counts are read; "?" once that read failed.
  // The number is what the Send sheet lists now (from the saved drafts until the read is in), read at each paint, so the two never disagree;
  // "…" and "?" only when nothing is saved, pending or failed (r12 audit13 frame 1, questions 1, reference 1)
  const sendNum = () => sendable() && sendP.saved ? savedN() : S.sendN;
  const sendSt = () => !sendable() || S.countsIn || sendNum() > 0 ? '' : S.stall.has('counts') ? '?' : '…';
  // the desk's Send opens at zero, where General feedback can start (r12 fix7 frame 2); the phone menu's waits for a draft, as in the mock.
  // Its paint and its press both ask this, so a Send that shows a number always opens (r12 audit15 questions 1)
  const sendOff = cls => !sendable() || (!sendSt() && !sendNum() && cls !== 'hide-ph');
  const SENDTIP = {'…': 'Counting what is ready to send… Press to see what you saved.', '?': 'What is ready to send could not be counted: press Try again. Press Send to see what you saved.'};
  // every Send on screen repaints together, so none keeps an old state
  function paintSend() {
    document.querySelectorAll('#p-top [data-send], #p-layer [data-send]').forEach(b => { b.outerHTML = sendBtn(b.classList.contains('hide-ph') ? 'hide-ph' : ''); });
    drawFab();
  }
  function sendBtn(cls) {
    // until the counts are in, Send never looks empty: it reads "…", or "?" once the read gave no answer (r12 audit10 frame 1); pressed, it opens with what was saved
    const st = sendSt();
    if (st) return `<button class="btn ${cls || ''}" data-send${st === '…' ? ' aria-busy="true"' : ''} aria-label="Send: ${esc(SENDTIP[st])}" title="${esc(SENDTIP[st])}">${I('send')}<span class="bl">Send</span> ${st}</button>`;
    const n = sendNum(), off = sendOff(cls);
    return `<button class="btn ${n ? 'pri' : ''} ${cls || ''}" data-send${off ? ' aria-disabled="true"' : ''} aria-label="Send${n ? ': ' + n + ' ready' : ''}" title="${!off ? 'Open the Send summary (⌘↵); ⌘↵ again sends' : 'Nothing is ready to send yet'}">${I('send')}<span class="bl">Send</span>${n ? ' ' + n : ''}</button>`;
  }
  function drawTop() {
    const top = document.getElementById('p-top'), w = S.other ? S.other.waiting || 0 : waitingHere();
    const cur = byKey[S.tab] || TABS[0];
    const mb = `<button class="mbtn" data-menu="nav" aria-haspopup="dialog" aria-expanded="${S.menu === 'nav'}" title="Menu: tabs, projects and settings" aria-label="Menu: tabs, projects and settings">${I(S.menu === 'nav' ? 'x' : 'menu')}</button>`;
    const allW = projs().reduce((s, x) => s + (x.waiting || 0), 0);
    const pt = `<button class="ptitle" data-menu="nav" aria-label="Menu: tabs, projects and settings">${S.home ? `<b>All projects</b><span class="tn">${pl(allW, 'question waiting', 'questions waiting')}</span>` : `<b>${esc(curName())}</b><span class="tn">${esc(cur.label)}<span data-chip="${cur.key}">${chipHtml(chipOf(cur.key))}</span></span>`}</button>`;
    const brand = `<a class="brand" href="#home" title="Home: every project" aria-label="Home: every project"${S.home ? ' aria-current="page"' : ''}>${I('home')}<span class="full">Agent Annotate</span></a>`;
    const projMenu = S.menu === 'proj' ? `<div class="menu" role="menu" aria-label="Projects"><h3>Your projects</h3>${projRows()}<div class="sep"></div><button class="mi" data-home><span class="nm">All projects (home)</span></button></div>` : '';
    const me = S.menu === 'me' ? `<div class="menu right smenu" role="menu" aria-label="Settings">${settingsBody()}</div>` : '';
    const who = `<div class="dd"><button class="btn ghost who" data-menu="me" aria-haspopup="menu" aria-expanded="${S.menu === 'me'}" title="Settings, people and sign out"><span class="av" aria-hidden="true">${esc(myName()[0])}</span><span class="hide-ph">${esc(myName())}</span> ▾</button>${me}</div>`;
    const dd = `<div class="dd hide-ph"><button class="btn" data-menu="proj" aria-haspopup="menu" aria-expanded="${S.menu === 'proj'}"><b>${S.home ? 'All projects' : esc(curName())}</b>${!S.home && w ? `<span class="badge qw" title="${pl(w, 'question waits', 'questions wait')} for your answer on this project">${w} waiting</span>` : ''} ▾</button>${projMenu}</div>`;
    if (S.home) { top.innerHTML = `${mb}${brand}${pt}${dd}<span class="spacer"></span>${who}`; return; }
    if (S.other) { top.innerHTML = `${mb}${brand}${pt}${dd}<span class="p-bar" id="p-bar">${workerDots()}</span><span class="spacer"></span>${who}`; return; }
    const hv = S.tab === 'history' && S.meta ? decodeURIComponent(location.hash.split('/')[1] || '') : '';  // an older version open in History, as the mock's header marks it
    const ver = S.meta && S.loadedV ? `<span class="chip hide-ph verchip" title="The version on screen">Version ${esc(String(S.meta.current || '').replace(/^v/, ''))}${/^v\d+$/.test(hv) && hv !== S.meta.current ? ` · viewing ${esc(hv.slice(1))} (older)` : ''}</span>` : '';
    top.innerHTML = `${mb}${brand}${pt}${dd}${ver}<span class="p-bar" id="p-bar"></span><span class="spacer"></span>${lastSendChip()}${reloadBtn()}${beadsCtl()}${sendBtn('hide-ph')}${who}`;
    drawBar();
    keepPaint();
  }
  // the version and its three counts as last read: the next reload paints them at once, until its own read is in (r12 fix12 perf)
  let kept = '';
  function keepPaint() {
    if (S.settling || !S.loadedV || !S.meta || S.loadedV !== S.meta.current || !sendable()) return;
    const k = JSON.stringify({v: S.loadedV, n: S.sendN, w: S.qWait, chip: S.chips.questions || null});
    if (k !== kept) { kept = k; prefs.set('firstPaint', JSON.parse(k)); }
  }
  function drawBar() {
    const el = document.getElementById('p-bar');
    if (el && !S.home) el.innerHTML = workerDots();
  }
  function drawFab() {
    const f = document.getElementById('p-fab');
    const st = sendSt(), n = sendNum();
    f.hidden = !((n || st) && !S.home && !S.other && S.menu !== 'nav');  // Send follows the page on screen: never another project's (RR1); a copy floats its simulated Send too
    f.innerHTML = `${I('send')}Send ${st || n || ''}`;
    f.classList.toggle('unk', !!st);  // not purple until the count is known
    f.setAttribute('aria-label', st ? 'Send: ' + SENDTIP[st] : `Send: ${pl(n, 'thing is', 'things are')} ready`);
    if (st === '…') f.setAttribute('aria-busy', 'true'); else f.removeAttribute('aria-busy');
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
  // Running's data: workers, scheduled jobs and the bead board, for the top bar and Home
  // runErr: the whole read failed (HTTP 503, no answer): Beads says the board could not be read, as Tasks does (r12 audit13 questions 4)
  // a board once read keeps Beads in the header, so a failed read says so instead of dropping it (r12 audit14 running 3)
  function putRun(r, err) {
    if (err) { S.runErr = true; S.ready = null; } else {
      S.run = r || null; S.runErr = false; S.ready = r && r.board && typeof r.board.ready === 'number' ? r.board.ready : null;
      if (r && r.board && !prefs.get('hadBoard', false)) prefs.set('hadBoard', true);
    }
    if (started) { drawTop(); if (S.menu === 'nav') drawLayer(); }
  }
  const readRun = () => data('running').then(() => {}, () => {});
  // Questions' three counts, read from one load and painted together: Send, the waiting badge and the Questions tab's chip.
  // A reload and a newer version show them with the version they belong to, never one before the others (r12 fix10 frame 1, running 2)
  const chipVal = c => c == null || c === '' ? null : typeof c === 'object' ? c : {text: String(c)};
  // again: Try again, which drops a read still on its way and starts a new one (r12 audit11 reference 1)
  async function readCounts(again) {
    if (!sendable()) return null;
    const qc = byKey.questions.chip;
    try {
      // count starts first, so the waiting count and the chip share its new read
      const [n, w, chip] = await Promise.all([sendP.count(ctx, again), sendP.waiting ? sendP.waiting(ctx) : null, qc ? qc(ctx) : undefined]);
      return {n: +n || 0, w: w == null ? null : +w || 0, chip};
    } catch (e) {
      console.warn('counts', e);
      if (!S.countsIn) { S.stall.set('counts', e.message); drawStall(); paintSend(); }  // the first counts never came: the tab on screen offers Try again (r12 audit10 frame 1)
      return null;
    }
  }
  const putCounts = c => {
    if (!c) return;
    S.sendN = c.n; if (c.w != null) S.qWait = c.w; if (c.chip !== undefined) S.chips.questions = chipVal(c.chip);
    S.countsIn = true; if (S.stall.delete('counts')) drawStall();
    paintSend();
  };
  const hhmm = () => new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
  // A first read with no answer: a line above the tab on screen, whichever tab, with Try again (r12 audit10 frame 1, running 2)
  const STALLED = {version: "The page's version", counts: 'What waits for you and what is ready to send'};
  function drawStall() {
    let el = document.getElementById('p-stall');
    if (!el) { el = Object.assign(document.createElement('div'), {id: 'p-stall'}); document.getElementById('p-main').before(el); }
    const ks = [...S.stall.keys()];
    el.hidden = !ks.length || S.home || !!S.other;
    el.innerHTML = el.hidden ? '' : `<div class="p-stall" role="alert">${I('warn')}<p>${ks.map(k => `${esc(STALLED[k])} could not be read: ${esc(S.stall.get(k))}.`).join(' ')} Your saved answers and notes are kept.</p><button class="btn sm" data-stallagain>Try again</button></div>`;
  }
  let retrying = null;
  function again() {
    if (retrying || !S.stall.size) return retrying;
    const v = S.stall.has('version'), c = S.stall.has('counts');
    S.stall.clear(); drawStall(); drawTop(); paintSend();  // every Send reads "…" again while it reads
    return retrying = Promise.all([
      v && api.meta().then(m => {
        S.meta = m; S.loadedV = S.loadedV || m.current; S.checked = !COPY && m.current === S.loadedV ? hhmm() : S.checked;
        document.title = (m.name || 'This project') + ' · Agent Annotate';
      }, e => { S.stall.set('version', e.message); }),
      c && readCounts(true).then(putCounts),
    ]).finally(() => { retrying = null; drawStall(); drawTop(); drawFab(); if (S.menu === 'nav') drawLayer(); });
  }
  let topTimer;
  function refreshTop() {
    if (started) paintSend();  // a draft added or removed on any tab: Send follows its sheet in the same paint
    clearTimeout(topTimer);
    topTimer = setTimeout(async () => {
      if (S.settling) return;  // a newer version is loading: its counts paint with it
      await Promise.all([
        readCounts().then(c => { if (S.settling) return; putCounts(c); if (c) { paintChip('questions'); drawTop(); drawFab(); } }),
        readRun(),
        data('frame', true).then(d => { S.fd = d; }).catch(() => {}),
        api.delivery().then(d => { S.deliv = d && d.latest; }).catch(() => {}),
      ]);
      if (S.settling) return;
      drawTop(); drawFab(); if (S.menu === 'nav') drawLayer();
      if (S.home) drawHome();  // its row for this page shows the same waiting count
    }, 300);
  }
  // The Send count, the moment a draft is added or removed on any tab: only the Send buttons repaint, so a box he types in keeps its focus
  let sendT;
  const savedN = () => { try { return +sendP.saved(ctx) || 0; } catch (e) { console.warn('send saved', e); return S.sendN; } };
  function refreshSend() {
    clearTimeout(sendT);
    sendT = setTimeout(async () => {
      if (!started || !sendable()) return;
      // until the counts are in, Send counts the saved drafts, as its sheet lists them: a cleared one leaves the count at once (r12 fix14)
      const pre = !S.countsIn && sendP.saved;
      if (S.settling && !pre) return;
      const n = pre ? savedN() : await Promise.resolve().then(() => sendP.count(ctx)).then(x => +x || 0, () => S.sendN);
      // the rows too: a read that grants Remove leaves the count as it was, and the open sheet must still list it (r12 audit22 reference 3)
      const sg = sendP.sig ? sendP.sig() : '';
      if (!pre && S.settling || (pre ? n === S.sendN && S.warm === n > 0 : n === S.sendN) && sg === S.sendSig) return;
      S.sendSig = sg; S.sendN = n; if (pre) S.warm = n > 0;
      if (sendP.changed) sendP.changed();  // an open Send summary lists what the count now holds (r12 fix10 reference 2)
      paintSend(); keepPaint();
    }, 30);
  }

  /* ---------- the phone's menu, People and keyboard shortcuts ---------- */
  function navMenu() {
    const tabs = S.home ? '' : `<nav aria-label="Tabs">${TABS.map(t => { const c = chipOf(t.key); return `<button class="pm-tab ${t.tone}${c && c.empty ? ' empty' : ''}" role="tab" data-tab="${t.key}" aria-selected="${S.tab === t.key}">${I(t.icon)}<span class="pl">${esc(t.label)}</span><span data-chip="${t.key}">${chipHtml(c)}</span></button>`; }).join('')}</nav>
      ${S.other ? '' : `<div class="pm-acts">${sendBtn('') + beadsCtl(true) + lastSendChip('')}</div>`}`;
    return `<div class="pmenu" role="dialog" aria-label="Menu">${tabs}<h3>Projects</h3>${projRows()}<button class="mi" data-home${S.home ? ' aria-current="page"' : ''}><span class="nm ri8">${I('home')} All projects</span></button><div class="smb">${settingsBody()}</div></div>`;
  }
  const KEYS = [['F', 'next question'], ['A', 'previous question'], ['1–9', 'pick that choice on the highlighted question'], ['C', 'write words on the highlighted question'],
    ['⌘↵', 'open the Send summary, from anywhere, even while typing an answer; in a note box it saves the note'], ['⌘↵ again', 'send, once the Send summary is open'],
    ['Esc', 'close a menu, sheet or picture'], ['J K', 'next or previous task, while a task is open'], ['← →', 'older or newer version, while one is open in History'], ['?', 'this list']];
  const keysSheet = () => `<div class="sheet" data-scrim><div class="box" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts"><h2 class="ph">${I('keys')} Keyboard shortcuts</h2><ul class="keys">${KEYS.map(([k, t]) => `<li><kbd>${k}</kbd><span>${t}</span></li>`).join('')}</ul><div class="acts"><button class="btn" data-close>Close</button></div></div></div>`;
  const ROLE = {owner: 'Owner', view: 'Can view', send: 'Can answer and send'}, ROLEIC = {owner: 'key', view: 'eye', send: 'edit'};
  const ROLEHINT = {owner: 'Sees every project and is the only one who can change who has access', view: 'Reads the page, its questions, Reference and History; cannot answer, write notes or send', send: 'Also answers questions, writes notes and presses Send'};
  function peopleSheet() {
    S.people = S.people || [{n: myName(), role: 'owner'}];
    const nr = S.newRole || 'view';
    return `<div class="sheet" data-scrim><div class="box" role="dialog" aria-modal="true" aria-label="People on ${esc(curName())}">
      <h2 class="ph ri8">${I('people')} People on ${esc(curName())} <span class="badge grey">${S.people.length}</span></h2>
      <p class="small mut">Only you, the owner, can add or remove people and change what they can do. A change applies on their next click: the page checks this list on every visit.</p>
      <div role="list">${S.people.map((x, i) => `<div class="prow" role="listitem"><span class="av" aria-hidden="true">${esc(x.n[0])}</span><div class="grow"><b>${esc(x.n)}</b>${x.role === 'owner' ? ' <span class="small mut">(you)</span>' : ''}<div class="sub">${x.role === 'owner' ? 'Google sign-in · sees every project' : 'Added · has not opened it yet'}</div></div>
        ${x.role === 'owner' ? `<span class="roleseg"><span class="ri8 small" title="${esc(ROLEHINT.owner)}">${I(ROLEIC.owner)}${ROLE.owner}</span></span><span></span>` : `<span class="seg roleseg" role="group" aria-label="What ${esc(x.n)} can do">${['view', 'send'].map(r => `<button data-prole="${i}~${r}" aria-pressed="${x.role === r}" title="${esc(ROLEHINT[r])}">${I(ROLEIC[r])} ${ROLE[r]}</button>`).join('')}</span><button class="icb" data-prm="${i}" title="Remove ${esc(x.n)}" aria-label="Remove ${esc(x.n)}">${I('trash')}</button>`}</div>`).join('')}</div>
      <div class="addrow"><input type="email" id="p-newperson" placeholder="Their Google email" aria-label="Their Google email"><span class="seg" role="group" aria-label="What they can do">${['view', 'send'].map(r => `<button data-pnewrole="${r}" aria-pressed="${nr === r}" title="${esc(ROLEHINT[r])}">${I(ROLEIC[r])} ${ROLE[r]}</button>`).join('')}</span><button class="btn pri sm" data-padd>Add</button>${P.inertMark()}</div>
      ${S.pErr ? `<p class="small err-t" role="alert">${esc(S.pErr)}</p>` : ''}
      <p class="small mut">${I('eye')} Can view: reads the page, its questions, Reference and History. ${I('edit')} Can answer and send: also answers, writes notes and presses Send.</p>
      <div class="acts"><button class="btn" data-close>Done</button><button class="lk small" data-denied>See what someone without access sees</button></div></div></div>`;
  }
  const nameOf = v => { const l = v.split('@')[0].replace(/[._-]+/g, ' ').trim(); return l ? l[0].toUpperCase() + l.slice(1) : v; };  // a name, never an address

  /* ---------- Home: every project, read-only past this one ---------- */
  async function drawHome() {
    const el = document.getElementById('p-main');
    el.className = 'p-main home';
    const fd = S.fd || await data('frame').catch(() => null);
    if (!S.home) return;  // he left Home while it read: never draw over the tab he opened (#2)
    if (!fd) { el.innerHTML = `<div class="p-empty">${I('warn')}<p>Home could not load its counts.</p></div>`; return; }
    S.fd = fd;
    // the rows draw at once; workers and jobs ("—" until then) fill in when Running's read lands (r13 speed)
    if (!S.run) readRun().then(() => { if (S.home && S.run) drawHome(); });
    const days = fd.days || 14;
    const ago = h => h == null ? 'no page yet' : h < 1 ? 'under an hour ago' : h < 48 ? `${Math.round(h)} h ago` : `${Math.round(h / 24)} days ago`;
    // 'other' gathers unrelated projects, so its workers belong to no one row
    const rows = projs().map(x => {
      const ws = x.code && x.code !== 'other' ? workersOf(x.code) : null, jobs = jobsOf(x.code);
      const bad = (jobs || []).filter(j => j.failing).length + (ws || []).filter(w => w.s === 'stuck' || w.s === 'failed').length;
      const h = x.lastAgoH;
      const health = bad ? ['bad', `${pl(bad, 'thing needs', 'things need')} a look: failing jobs or workers with no sign of life`] : h == null ? ['idle', 'No page yet'] : h > 24 * 30 ? ['idle', 'Quiet: no update in a month'] : x.waiting && h > 24 * 7 ? ['warn', 'Questions wait and nothing new in a week'] : ['ok', 'Fine'];
      return {...x, ws, jobs, bad, health};
    }).sort((a, b) => b.waiting - a.waiting || b.bad - a.bad || (a.lastAgoH ?? 1e9) - (b.lastAgoH ?? 1e9));
    const maxW = Math.max(1, ...rows.map(r => r.waiting)), maxV = Math.max(1, ...rows.flatMap(r => r.vday));
    const totW = rows.reduce((s, r) => s + r.waiting, 0), fresh = rows.filter(r => r.lastAgoH != null && r.lastAgoH < 24).length;
    // the copy and its project share one code: count each project's workers and jobs once
    const once = [...new Map(rows.filter(r => r.ws || r.jobs).map(r => [r.code, r])).values()];
    const allWs = once.flatMap(r => r.ws || []), c = countBy(allWs), failJ = once.reduce((s, r) => s + (r.jobs || []).filter(j => j.failing).length, 0);
    const spark = r => { const bw = 8, g = 2, W = days * (bw + g);
      return `<svg class="spark" viewBox="0 0 ${W} 30" preserveAspectRatio="none" width="${W}" height="30" role="img" aria-label="${pl(r.vday.reduce((s, n) => s + n, 0), 'version', 'versions')} and ${pl(r.aday.reduce((s, n) => s + n, 0), 'answer round', 'answer rounds')} in ${days} days">${r.vday.map((n, i) => `<g><title>${days - 1 - i ? `${days - 1 - i} days ago` : 'today'}: ${pl(n, 'version', 'versions')} published, ${pl(r.aday[i], 'answer round', 'answer rounds')} from you</title><rect class="sb0" x="${i * (bw + g)}" y="0" width="${bw}" height="24"/>${n ? `<rect class="sb" x="${i * (bw + g)}" y="${24 - Math.max(2, n / maxV * 24)}" width="${bw}" height="${Math.max(2, n / maxV * 24)}"/>` : ''}${r.aday[i] ? `<rect class="sa" x="${i * (bw + g)}" y="26" width="${bw}" height="4"/>` : ''}</g>`).join('')}</svg>`; };
    const unread = what => `<span class="small mut" title="${what[0].toUpperCase() + what.slice(1)}: not read yet"><span class="ph-only">${what} </span>—</span>`;
    const dots = (ws, r) => !ws ? (S.run && r.code === 'other' ? `<span class="small mut" title="Workers of projects without a tag of their own are not split by project"><span class="ph-only">workers </span>—</span>` : unread('workers')) : ws.length ? ws.slice(0, 16).map(w => `<i class="dt ${esc(w.s)}" title="${esc(w.name)}: ${esc(SL[w.s] || w.s)}"></i>`).join('') + (ws.length > 16 ? `<span class="small mut">+${ws.length - 16} more</span>` : '') : '<span class="small mut">no workers</span>';
    const jobsCell = (js, r) => !js ? (S.run && r.code === 'other' ? `<span class="small mut" title="${esc(r.name)} gathers projects with no Windmill folder of their own">no scheduled jobs</span>` : unread('scheduled jobs'))
      : js.length ? js.map(j => `<i class="dq ${j.failing ? 'bad' : 'ok'}" title="${esc(j.name)}: ${j.failing ? 'failing' : 'fine'}"></i>`).join('')
      : `<span class="small mut" title="No enabled Windmill schedule on this Mac belongs to ${esc(r.name)}">no scheduled jobs</span>`;
    const row = r => `<div class="hrow" role="row"><span class="hc nm" role="cell"><i class="hd ${r.health[0]}" title="${esc(r.health[1])}" aria-label="${esc(r.health[1])}"></i>${projOpen(r, '', 'lk', esc(r.name))}<span class="small mut hpg">${pl(r.pages, 'page', 'pages')}</span></span>
      <span class="hc wt" role="cell" title="${pl(r.waiting, 'question', 'questions')} waiting">${r.waiting ? `<span class="wbar"><i style="width:${Math.max(4, r.waiting / maxW * 100)}%"></i></span><b class="err-t">${r.waiting} waiting</b>` : '<span class="small mut">nothing waiting</span>'}</span>
      <span class="hc wk" role="cell">${dots(r.ws, r)}</span><span class="hc jb" role="cell">${jobsCell(r.jobs, r)}</span>
      <span class="hc ac" role="cell">${spark(r)}</span><span class="hc ls small mut" role="cell">${ago(r.lastAgoH)}</span></div>`;
    const tile = (big, sub, cls, viz) => `<div class="htile ${cls}"><b>${big}</b><span>${sub}</span>${viz || ''}</div>`;
    el.innerHTML = `<section class="home"><div class="hhead"><h2 class="ph">All projects</h2><span class="small mut">from the project pages on this Mac · ${esc(fd.asOf || '')}</span></div>
      <div class="htiles">${tile(totW.toLocaleString(), `questions waiting, in ${pl(rows.filter(r => r.waiting).length, 'project', 'projects')}`, totW ? 'bad' : '', `<span class="stack">${rows.filter(r => r.waiting).map(r => `<i style="flex:${r.waiting}" title="${esc(r.name)}: ${r.waiting} waiting"></i>`).join('')}</span>`)}
        ${tile(allWs.length.toLocaleString(), `workers: ${['working', 'stuck', 'failed', 'done'].filter(s => c[s]).map(s => `${c[s]} ${SL[s]}`).join(', ') || 'none'}`, c.stuck || c.failed ? 'warn' : 'ok', `<span class="stack ws">${['working', 'stuck', 'failed', 'done'].filter(s => c[s]).map(s => `<i class="${s}" style="flex:${c[s]}"></i>`).join('')}</span>`)}
        ${tile(failJ.toLocaleString(), failJ === 1 ? 'scheduled job failing' : 'scheduled jobs failing', failJ ? 'bad' : 'ok')}
        ${tile(fresh.toLocaleString(), `${fresh === 1 ? 'project' : 'projects'} updated in the last day`, '')}</div>
      <div class="htab" role="table" aria-label="Every project"><div class="hrow hh" role="row"><span class="hc nm" role="columnheader">Project</span><span class="hc wt" role="columnheader">Waiting</span><span class="hc wk" role="columnheader">Workers</span><span class="hc jb" role="columnheader">Scheduled jobs</span><span class="hc ac" role="columnheader">Last ${days} days</span><span class="hc ls" role="columnheader">Last update</span></div>${rows.map(row).join('')}</div>
      <p class="small mut hleg"><span><i class="hd ok"></i>fine</span><span><i class="hd warn"></i>questions wait, nothing new in a week</span><span><i class="hd bad"></i>a job failing or a worker with no sign of life</span><span><i class="hd idle"></i>quiet</span><span><i class="dt working"></i>working</span><span><i class="dt stuck"></i>no sign of life</span><span><svg width="8" height="10"><rect class="sb" width="8" height="10"/></svg> versions published a day</span><span><svg width="8" height="4"><rect class="sa" width="8" height="4"/></svg> a day you answered</span></p></section>`;
  }

  // A project with no copy in the prototype (#1): its six tabs stay, dimmed, and each says why, with a link through to its own page.
  // Rebex and Agent Annotate are carried as read-only copies (copy.sh), so their rows open their own prototype pages instead.
  function drawOther() {
    const o = S.other, el = document.getElementById('p-main'), t = byKey[S.tab] || TABS[0];
    el.className = 'p-main other tab-' + t.key;
    const what = {questions: 'questions', reference: 'reference material', running: 'workers and tasks', analytics: 'analytics', history: 'history', links: 'pages and links'}[t.key];
    const own = o.url ? `<a href="${esc(o.url)}" target="_blank" rel="noopener">Open ${esc(o.name)}'s own page ↗</a>` : `${esc(o.name)} has no page address on this Mac.`;
    el.innerHTML = `<section class="p-other"><h2 class="ph">${I(t.icon)} ${esc(o.name)} · ${esc(t.label)}</h2>
      <p class="mut dim">Nothing yet: ${esc(o.name)}'s ${what} are not copied into this prototype, which carries ${esc(projs().filter(x => x.href != null).map(x => x.name).join(', '))} only. ${own}</p>
      <p class="acts"><button class="btn ghost" data-home>${I('home')} All projects</button></p></section>`;
  }

  /* ---------- routing ---------- */
  let routed = false;
  function route() {
    let [key, anchor, sub] = location.hash.replace(/^#/, '').split('/');
    // A reload with "Open tab" off starts on Questions, even though the address still names the last tab (#80).
    const nav = !routed && performance.getEntriesByType && performance.getEntriesByType('navigation')[0];
    routed = true;
    if (nav && nav.type === 'reload' && !remember('tab')) {
      if (byKey[key]) { key = 'questions'; anchor = ''; history.replaceState(null, '', '#questions'); }
      if (key === 'project' && sub && sub !== 'questions') { sub = 'questions'; history.replaceState(null, '', `#project/${anchor}/questions`); }  // another project's too (#5)
    }
    S.home = key === 'home';
    S.menu = '';
    S.other = key === 'project' ? projs().find(x => x.key === anchor && !x.this) || null : null;
    drawStall();
    if (key === 'project' && !S.other && S.fd) { location.replace('#home'); return; }
    if (S.other && S.other.href != null) { location.replace(ROOT + S.other.href + '#' + (byKey[sub] ? sub : 'questions')); return; }  // a project with its own prototype page
    if (S.home) { drawTabs(); drawAll(); drawHome().finally(() => shownDone()); return; }
    if (S.other) { S.tab = byKey[sub] ? sub : 'questions'; drawTabs(); drawAll(); drawOther(); shownDone(); return; }
    const tab = byKey[key] ? key : remember('tab') ? prefs.get('tab', 'questions') : 'questions';
    S.tab = byKey[tab] ? tab : 'questions';
    prefs.set('tab', S.tab);
    drawTabs(); drawAll();
    show(S.tab, anchor ? decodeURIComponent(anchor) : null);
  }

  /* ---------- a newer version: checked once a minute; the page changes only when he presses the icon ---------- */
  let copyWatch = 0, checkSeq = 0, checkLast = null;
  // Reload's title, label and look, in place: a press keeps its focus, an open menu stays open
  function paintReload() {
    const el = typeof document !== 'undefined' && document.querySelector('#p-top [data-recheck]');
    if (!el) return;
    const t = document.createElement('template'); t.innerHTML = reloadBtn();
    const n = t.content.firstElementChild;
    el.className = n.className; el.title = n.title; el.setAttribute('aria-label', n.getAttribute('aria-label')); el.innerHTML = n.innerHTML;
  }
  // while any check is on its way Reload is neutral, never an earlier "Up to date"; only the latest check paints (r12 audit13 frame 3, questions 3, reference 2)
  function checkNewer() {
    const my = ++checkSeq;
    S.checked = ''; paintReload();
    return checkLast = checkOnce(my).finally(paintReload);
  }
  async function checkOnce(my) {
    // a copy whose real page moved on copies the newer version in the background: it says so, never "Up to date" (r12 fix10 slowread)
    let [m, cp] = await Promise.all([api.meta().catch(() => null), COPY ? api('proto/data/copies.json').catch(() => null) : null]);
    if (my !== checkSeq) return checkLast;
    // a copy swapped in between the two reads leaves the metadata a version behind the copy: read it again (r12 audit12 frame 2)
    const ahead = () => !!(m && cp && cp.current && cp.current !== m.current && !(m.history || []).some(h => h.version === cp.current));
    if (ahead()) m = await api.meta().catch(() => null);
    if (my !== checkSeq) return checkLast;
    // until the metadata reaches the copy's version, that version is still on its way: "Copying", then blue, never "Up to date"
    S.copying = (cp && cp.copying) || (ahead() ? cp.current : '');
    if (S.copying && !copyWatch) copyWatch = setTimeout(() => { copyWatch = 0; checkNewer().then(() => { if (!S.menu) drawTop(); }); }, 10000);
    // "Up to date" needs both answers to name the version on screen: the page's metadata and (on a copy) the copy itself (r12 audit10 frame 5, audit12 frame 2)
    S.checked = m && S.loadedV && m.current === S.loadedV && (!COPY || (cp && cp.current === S.loadedV)) && !S.copying ? hhmm() : '';
    if (!m || !S.loadedV) return false;
    if (m.current === S.loadedV) { S.newer = null; return false; }
    const vs = (m.history || []).map(h => h.version), from = vs.indexOf(S.loadedV), fresh = new Set(from < 0 ? [m.current] : vs.slice(from + 1));
    const store = await api.comments().catch(() => ({anchors: {}}));
    if (my !== checkSeq) return checkLast;
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
    const t = e.target.closest('#p-top button, #p-top a, #p-layer button, #p-layer a, #p-layer [data-scrim], #p-fab, #p-tabs button, .p-main.home button, .p-main.other button, #p-gate button, #p-stall button, a.skip');
    if (!t) {
      if (S.menu && S.menu !== 'nav' && !e.target.closest('.menu')) { S.menu = ''; drawAll(); }
      return;
    }
    const d = t.dataset;
    if (d.skip) { e.preventDefault(); skipTo(d.skip); return; }
    if (d.signin !== undefined) { signIn(d.signin === 'back'); return; }
    if (d.denied !== undefined) { denied(false); return; }
    if (d.gateask !== undefined) { denied(true); return; }
    if (d.scrim !== undefined) { if (t === e.target) { S.sheet = ''; drawLayer(); } return; }
    if (d.menu) { S.menu = S.menu === d.menu ? '' : d.menu; drawAll(); return; }
    if (t.matches('.brand') || d.home !== undefined) { e.preventDefault(); S.menu = ''; if (location.hash === '#home') route(); else location.hash = 'home'; return; }
    if (d.gothis !== undefined) { S.menu = ''; const back = S.other ? 'questions' : S.tab || 'questions'; if (location.hash === '#' + back) route(); else location.hash = back; return; }
    if (d.proj) { S.menu = ''; location.hash = `project/${d.proj}/questions`; return; }
    if (d.go) { S.menu = ''; location.hash = d.go; return; }
    if (d.tab && S.other) { S.menu = ''; location.hash = `project/${S.other.key}/${d.tab}`; return; }
    if (d.tab && t.matches('.pm-tab')) { S.menu = ''; ctx.go(d.tab); drawAll(); return; }
    if (d.tab && t.matches('.tab')) { ctx.go(d.tab); return; }
    if (d.stallagain !== undefined) { again(); return; }
    if (d.send !== undefined) {
      S.menu = ''; drawAll();
      // while the counts are unknown or failed, Send opens at once with what was saved (r12 audit11 frame 1, questions 1)
      if (sendOff(t.classList.contains('hide-ph') ? 'hide-ph' : '')) return toast('Nothing is ready to send yet');
      return openSend();
    }
    if (t.id === 'p-fab') return openSend();
    if (d.recheck !== undefined) {
      // every tab's counts follow the new version at once: Questions re-reads, then the badges repaint (audit6 running #04, frame #03)
      // the version, Send, the waiting badge and the Questions chip change in one paint, and only then does it say so (r12 fix10 running 2)
      if (S.settling) return;
      if (S.newer) {
        const v = S.newer.v; S.settling = true;
        for (const k in cache) delete cache[k]; failed.clear(); if (sendP && sendP.newer) sendP.newer();
        Promise.all([api.meta().catch(() => null), readCounts()]).then(([m, c]) => {
          if (m) S.meta = m; S.loadedV = (m && m.current) || v; S.newer = null; putCounts(c);
        }).finally(() => { S.settling = false; route(); refreshTop(); toast('Loaded the newer version'); });
        return;
      }
      checkNewer().then(found => { drawTop(); if (!found) toast(S.copying ? copyingText() + ' Reload turns blue when it is ready.' : S.checked ? 'Up to date' : 'Could not check for a newer version just now'); });
      return;
    }
    if (d.sheet) { S.sheet = d.sheet; S.menu = ''; S.pErr = ''; drawAll(); return; }
    if (d.close !== undefined) { S.sheet = ''; drawLayer(); return; }
    if (d.copylink !== undefined) {
      const done = () => toast('Link copied');
      (navigator.clipboard ? navigator.clipboard.writeText(location.href) : Promise.reject()).then(done, () => toast('Copy did not work here: ' + location.href));
      return;
    }
    if (d.signout !== undefined) { signOut(); return; }
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
  const openSend = key => sendable() && Promise.resolve().then(() => sendP.open(ctx, key)).catch(err => toast('Send could not open: ' + err.message));
  function onChange(e) {
    const t = e.target, d = t.dataset;
    if (d.fsin !== undefined) { setFs(parseInt(t.value, 10)); drawAll(); return; }
    if (d.optsfirst !== undefined) { prefs.set('optsFirst', t.checked); document.body.classList.toggle('opts-first', t.checked); return; }
    if (d.rem) {
      prefs.set('rem', {...REM, ...prefs.get('rem', {}), [d.rem]: t.checked});
      if (d.rem === 'drafts' && t.checked) for (const k of Object.keys(mem)) prefs.set(k, mem[k]);  // typed while off: kept from now on
      if (d.rem === 'folds' && !t.checked) prefs.set('folds', {});
      return;
    }
  }
  const typing = el => el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
  const onQuestions = () => !S.home && !S.other && S.tab === 'questions';
  // Questions owns F, A, 1–9, C and Esc on its tab; from any other tab F and A open Questions and hand the key over (#7)
  async function questionKey(e) {
    const k = e.key.toLowerCase();
    if ((k !== 'f' && k !== 'a') || onQuestions()) return;
    e.preventDefault();
    ctx.go('questions');
    for (let i = 0; i < 30 && !document.querySelector('#p-main .qcard[data-q]'); i++) await new Promise(r => setTimeout(r, 100));  // the tab may still be drawing
    document.body.dispatchEvent(new KeyboardEvent('keydown', {key: k, bubbles: true}));
  }
  function onKey(e) {
    if (e.key === 'Escape' && (S.menu || S.sheet)) { S.menu = ''; S.sheet = ''; drawAll(); return; }
    if (e.key === 'Escape') {  // an area's own dialog in the page that does not close itself: its dismiss button
      // a Move still armed, whatever has focus: its pressed button lets it go, through the tab's own handler (r12 audit17 reference 4)
      const mv = !onQuestions() && document.querySelector('#p-main [data-nmove][aria-pressed="true"]');
      if (mv) { e.preventDefault(); mv.click(); return; }
      const x = !onQuestions() && !document.body.classList.contains('qsheet-open') && document.querySelector('#p-main [role=dialog] :is([data-esc],[data-sendclose])');
      if (x) { e.preventDefault(); x.click(); }
      return;
    }
    // ⌘↵ from any other tab, even while typing: the Send summary opens over it and asks for a second press (r12 fix7 frame 1)
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && !onQuestions() && !S.home && !S.other && !S.gated && sendable()) {
      e.preventDefault(); e.stopPropagation();  // Questions' own ⌘↵ listens on window: this press is handled once
      if (S.menu || S.sheet) { S.menu = ''; S.sheet = ''; drawAll(); }
      openSend(true);
      return;
    }
    if (e.key === 'Enter' && e.target.dataset && e.target.dataset.fsin !== undefined) { e.target.blur(); return; }
    if (typing(e.target) || e.metaKey || e.ctrlKey || e.altKey || S.sheet || S.menu || S.gated || document.body.classList.contains('qsheet-open')) return;
    if (e.key === '?') { S.sheet = 'keys'; S.menu = ''; drawAll(); return; }
    if (historyKey(e)) return;
    questionKey(e);
  }
  // ← → step to the older or newer version while one is open in History (#13)
  function historyKey(e) {
    if ((e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') || S.home || S.other || S.tab !== 'history') return false;
    const v = decodeURIComponent(location.hash.replace(/^#/, '').split('/')[1] || ''), vs = ((S.meta && S.meta.history) || []).map(h => h.version), i = v ? vs.indexOf(v) : -1;
    const to = i < 0 ? null : vs[i + (e.key === 'ArrowLeft' ? -1 : 1)];
    if (!to) return false;
    e.preventDefault();
    ctx.go('history', to);
    return true;
  }

  /* ---------- skip links (#17): tabs, questions, the review document ---------- */
  // (#7) the first card he can see, opening its folded section if every card is folded away; the document view, never a card's evidence
  async function skipTo(kind) {
    // scroll-padding keeps the target clear of the pinned frame
    const focus = el => { if (!el) return false; if (!el.matches('a,button,input,textarea,[tabindex]')) el.tabIndex = -1; el.focus({preventScroll: true}); scrollClear(el); return true; };
    // the phone's tabs live in its menu: open it, then focus the first tab (r12 fix7 frame 4)
    if (kind === 'tabs' && phoneQ.matches && !S.home) { S.menu = 'nav'; S.sheet = ''; drawAll(); const b = document.querySelector('#p-layer .pm-tab'); if (b) b.focus(); return !!b; }
    if (kind === 'tabs') return focus(document.querySelector('#p-tabs .tab[aria-selected="true"]') || document.querySelector('#p-tabs .tab'));
    if (S.home || S.other || S.tab !== 'questions') ctx.go('questions');
    const m = document.getElementById('p-main'), vis = el => !!el && el.getClientRects().length > 0;
    const wait = async test => { for (let i = 0; i < 30 && !test(); i++) await new Promise(r => setTimeout(r, 100)); return test(); };  // the tab may still be drawing
    if (kind !== 'questions') {
      await wait(() => vis(m.querySelector('.aa.qdoc')) || m.querySelector('[data-view="doc"]'));
      const b = m.querySelector('[data-view="doc"]');
      if (!vis(m.querySelector('.aa.qdoc')) && b) b.click();  // Cards only: back to the document first
      // the document's text, not its empty box: Questions puts back the old scroll once the text is in, so land after that (audit4 frame 1)
      return focus(await wait(() => [...m.querySelectorAll('.aa.qdoc')].find(x => vis(x) && x.childElementCount)) || m);
    }
    const card = () => [...m.querySelectorAll('.qcard[data-q]')].find(vis);
    await wait(() => m.querySelector('.qcard[data-q]'));
    if (!card()) {
      const c = m.querySelector('.qcard[data-q]'), sec = c && c.closest('section.qsec'), b = sec && sec.querySelector(':scope > h2 [data-sfold]');
      if (b) { b.click(); await wait(card); }
    }
    return focus(card() || m);
  }

  /* ---------- sign out (#8): the sign-in screen covers the page; signing in comes back to the same place ---------- */
  function gate(html) {
    S.gated = true; S.menu = ''; S.sheet = ''; drawAll();
    document.body.classList.add('p-gated');
    let g = document.getElementById('p-gate');
    if (!g) { g = Object.assign(document.createElement('main'), {id: 'p-gate'}); document.body.appendChild(g); }
    g.innerHTML = `<div class="gate">${html}<p class="small">${P.inertMark()}</p></div>`;
    g.querySelector('.btn.pri, .lk').focus();
  }
  function signOut() {
    gate(`<h2 class="ph">Agent Annotate</h2><p>Sign in to see your projects and answer what is waiting.</p><button class="btn pri" data-signin>Sign in with Google</button><p class="small mut">Only people on a project's People list can open its page.</p>`);
  }
  // People's "See what someone without access sees" (audit4 frame 2): the mock's sample denial screen, with a way back
  function denied(asked) {
    const own = myName().split(' ')[0];
    gate(`<h2 class="ph">This page isn't shared with you yet</h2><p>You're signed in, but not on ${esc(curName())}'s People list.</p>${asked
      ? `<p class="okline" role="status">${I('check')} Asked. ${esc(own)} sees your request under People; this link opens the page once ${esc(own)} adds you.</p>`
      : `<div class="acts gacts"><button class="btn pri" data-gateask>Ask ${esc(own)} for access</button><button class="btn" data-signout>Use another Google account</button></div>`}
      <p class="small mut"><button class="lk small" data-signin="back">Back to the page (you are the owner)</button></p>`);
  }
  function signIn(back) {
    S.gated = false;
    document.body.classList.remove('p-gated');
    const g = document.getElementById('p-gate');
    if (g) g.remove();
    if (!back) toast('Signed in', {inert: true});
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
    document.addEventListener('toggle', saveFold, true);
    document.addEventListener('click', saveSecFold, true);  // before Questions turns the section over
    document.addEventListener('click', refreshSend); document.addEventListener('input', refreshSend);  // after the tab's own handler changed a draft
    if (!remember('drafts')) dropStoredDrafts();  // left over from before the switch went off (#4)
    // areas redraw their cards and sections: keep the highlight on the same question and the folds as he left them
    const main = document.getElementById('p-main');
    new MutationObserver(() => { if (!S.home) restoreFolds(main); }).observe(main, {childList: true, subtree: true});
    addEventListener('scroll', onScroll, {passive: true});
    phoneQ.addEventListener('change', () => { S.menu = ''; drawAll(); });
    // removals whose Undo went with the last visit: hidden from the first read, and they finish now
    for (const [id, path] of Object.entries(prefs.get('taken', {}))) TAKEN.set(id, path);
    // one round on a busy host, not three: Questions' read and the tab scripts start with the frame's reads (r12 fix12 perf)
    (pre.questions = api('proto/data/questions.json')).catch(() => {});
    const scripts = Promise.all(AREAS.flatMap(a => [load('link', {rel: 'stylesheet', href: `proto/${a}.css`}), load('script', {src: `proto/${a}.js`})]));
    scripts.then(scriptsDone, scriptsDone);  // on their own: the frame's read below waits for them on a copy, so start() must not hold them (fix26 deadlock)
    let why = '';
    // Questions' document starts with the version, beside its data, not after it (r13 speed): questions.js loadDoc takes it over
    const k0 = location.hash.replace(/^#/, '').split('/')[0], nav0 = performance.getEntriesByType('navigation')[0];
    const qFirst = !k0 || k0 === 'questions' || (byKey[k0] && nav0 && nav0.type === 'reload' && !remember('tab'));
    // the name and version alone: the whole metadata grows with every version, and is read once the tab has drawn (r13 speed)
    const metaP = api('proto/data/head.json');
    if (qFirst) metaP.then(m => {
      if (!m || !m.current || P.docPre) return;
      const r = fetch(base + 'content?v=' + encodeURIComponent(m.current), {cache: 'no-store'}); r.catch(() => {});
      P.docPre = {v: m.current, r};
    }, () => {});
    const [meta, who, fd, proj, board] = await Promise.all([metaP.catch(e => { why = e.message; return null; }), ...[api.identity(), data('frame'), api.project(), api.board()].map(p => p.catch(() => null))]);
    S.who = who; S.fd = fd; S.board = board;
    S.boardUrl = (proj && proj.board && proj.board.url) || (board && board.board && board.board.url) || '';
    document.title = ((meta && meta.name) || 'This project') + ' · Agent Annotate';
    await scripts;
    [...TAKEN.keys()].forEach(id => finishTake(id));  // after the scripts: a copy's removal goes to its in-memory store (P.copyWrite)
    started = true;
    // the tab paints at once; the version shows with the counts: each tab's drafts count from what it saved, not its data (r12 fix10 frame 1, running 2)
    // the version waits for its counts however slow the read: never Version with Send 0 before the restored count (r12 fix11 frame)
    // a failed read resolves at once, and no read waits past 20 s (r12 audit9 frame 2, fix10 slowread)
    S.meta = meta; S.settling = true;
    // the last reading of this same version paints at once, all three together, while Questions' read finishes (r12 fix12 perf)
    const was = remember('drafts') && meta && prefs.get('firstPaint', null);
    if (was && was.v === meta.current) { S.sendN = was.n; S.qWait = was.w; S.chips.questions = was.chip; S.loadedV = was.v; S.warm = was.n > 0; }  // a remembered 0 may predate a draft: Send reads "…" (r12 fix12 frame 1)
    // Send's number before any read is what its sheet lists from the saved drafts; "…" only when nothing is saved (r12 fix14)
    if (sendable() && sendP.saved) { S.sendN = savedN(); S.warm = S.sendN > 0; }
    if (!meta) S.stall.set('version', why || 'it came back empty');  // api() gives up on any read at 20 s
    route();
    addEventListener('hashchange', route);
    // the board comes from the same read as Running's: Beads changes in the same paint as Tasks, not after Questions (r12 audit13 running 4)
    firstShown.then(readRun);  // putRun paints Beads when it lands; after the tab on screen has drawn (r13 speed)
    if (S.loadedV || S.warm) { drawTop(); drawFab(); }
    putCounts(await readCounts());
    S.loadedV = meta && meta.current; S.settling = false;
    if (meta && !COPY) S.checked = hhmm();  // the version just read is the page's own; a copy waits for its copy status
    drawTop(); drawFab();
    firstRead();
    if (COPY) checkNewer().then(() => drawTop());  // a copy refresh already running shows from the first paint on
    firstShown.then(() => refreshTop());  // counts, workers, the board and the last Send
    // the whole metadata (History's ← → walk its versions), for the version just shown; a newer one waits for Reload as before
    firstShown.then(() => api.meta()).then(m => { if (m && S.meta && m.current === S.meta.current) S.meta = m; }, () => {});
    setInterval(() => { checkNewer().then(() => { if (!S.menu) drawTop(); }); }, 60000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
