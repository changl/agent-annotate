/* Prototype Running and Analytics tabs, from round9/final/mock.html (running(), taskPanel(), analytics()) on live, read-only data:
   proto/data/running.json (proto_data/running.py). Rerun, status changes and comments are inert: they look done, say so, offer Undo, reach nothing. */
(function () {
  'use strict';
  const P = window.Proto;
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const ic = (n, l) => P.icon(n, l);
  const pl = (n, a, b) => `${Number(n).toLocaleString()} ${n === 1 ? a : b}`;
  const cut = (s, n) => { s = String(s || ''); return s.length <= n ? s : s.slice(0, n).replace(/\s+\S*$/, '') + '…'; };
  const ago = m => m == null ? '' : m < 1 ? 'under a minute' : m < 60 ? `${m} min` : m < 1440 ? `${Math.round(m / 60)} h` : pl(Math.round(m / 1440), 'day', 'days');
  const dm = d => new Date(d + 'T12:00:00Z').toLocaleDateString('en-GB', {day: 'numeric', month: 'short'});
  let PROJ = 'fld', PNAME = 'FastLane Drive';
  // the page's own project (a read-only copy is Rebex's or Agent Annotate's), as running.py read it
  const own = d => { if (d && d.proj) { PROJ = d.proj; PNAME = d.pname || d.proj; } return d; };
  // worker state → the page's one colour per state: working is in progress, no sign of life is blocked, failed is failed
  const WS = {working: ['progress', 'working'], stuck: ['blocked', 'no sign of life'], failed: ['failed', 'failed'], done: ['done', 'done']};
  const WORDER = ['failed', 'stuck', 'working', 'done'];
  const BST = {'open': 'none', 'in progress': 'progress', 'blocked': 'blocked', 'closed': 'done', 'deferred': 'none', 'waiting': 'waiting'};
  const stPill = st => `<span class="rn-pill st-${BST[st] || 'none'}"><i class="dot"></i>${esc(st)}</span>`;
  // a model id in words: claude-opus-5-5 → Opus 5.5, gpt-6.2-sol → GPT 6.2 Sol
  const mdl = w => { const m = (w.model || '').replace(/^claude-/, '').replace(/-(\d+)-(\d+)$/, ' $1.$2').replace(/^gpt-/, 'GPT ').replace(/-/g, ' ');
    return m ? m.replace(/\b[a-z]/g, c => c.toUpperCase()) : w.agent === 'codex' ? 'Codex' : w.agent === 'claude' ? 'Claude' : 'Agent'; };
  // a worker named by its task code ("CHAT-SAVED-NOW-1-S") reads as words ("Chat saved now"); the code stays in its tooltip
  const wnm = n => /^[A-Z0-9]+(-[A-Z0-9]+)+$/.test(n || '') ? (t => t.charAt(0).toUpperCase() + t.slice(1))(n.replace(/(-\d+)?(-S)?$/, '').replace(/-/g, ' ').toLowerCase()) : (n || 'A worker');
  const scrub = s => (s || '').replace(/\b(ctx|task|term|msg|run)_[0-9a-z-]{6,}\b/gi, '').replace(/\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b/g, '').replace(/[ \t]{2,}/g, ' ');
  const tclean = s => scrub((s || '').replace(/\s*\((?:cards?\s+#?\d[^)]*|[^)]*#\d{4,6}[^)]*)\)/gi, '')).trim();
  const tref = (id, t, st) => `<span class="tref">${esc(tclean(t))}</span> <span class="bid">· ${esc(id)}${st ? ' ·' : ''}</span>${st ? ' ' + stPill(st) : ''}`;  // title · bead id · state
  const ICONS = {  // two glyphs this area adds, in the Proto.icon style
    dash: '<path d="M3 8h10"/>',
  };
  Object.keys(ICONS).forEach(k => { if (!P.ICONS[k]) P.ICONS[k] = ICONS[k]; });

  const S = {open: new Set(), ask: '', rerun: new Map(), task: '', list: [], peek: ''};
  let CTX = null, EL = null, D = null;

  /* ------------------------------------------------------------ the chip: only the most urgent state */
  function urgent(d) {
    // crashed: failed workers and failing jobs; a worker with no sign of life is blocked, as on its tile
    const ws = mine(d), failed = ws.filter(w => w.s === 'failed').length, stuck = ws.filter(w => w.s === 'stuck').length;
    const failing = myJobs(d).filter(j => j.failing).length, wait = ((d.board || {}).waiting || []).length;
    if (failed + failing) return {text: `${failed + failing} crashed`, tone: 'red', title: [failed && pl(failed, 'worker failed', 'workers failed'), failing && pl(failing, 'scheduled job is failing', 'scheduled jobs are failing')].filter(Boolean).join('; ')};
    if (stuck) return {text: `${stuck} blocked`, tone: 'orange', title: `${pl(stuck, 'worker has', 'workers have')} shown no sign of life for half an hour`};
    if (wait) return {text: `${wait} waiting`, tone: 'blue', title: `${pl(wait, 'task waits', 'tasks wait')} on you`};
    return ws.length ? {text: `${ws.length} running`, tone: 'green'} : null;
  }
  // running.json lists every project's scheduled jobs (Home counts them all); Running shows the page's own
  const myJobs = d => (Array.isArray(d.jobs) ? d.jobs : []).filter(j => j.proj === PROJ);
  const mine = d => Object.entries(d.workers || {}).filter(([k]) => k !== 'error').flatMap(([m, v]) => (v.workers || []).filter(w => w.proj === PROJ).map(w => ({...w, mac: m})));

  /* ------------------------------------------------------------ Running */
  function running() {
    const d = D, b = d.board && !d.board.error ? d.board : {tasks: [], beads: {}, waiting: [], groups: []}, B = b.beads || {};
    if (!S.list.includes(S.task)) S.list = [...new Set([...b.waiting.map(x => x[0]), ...b.tasks.map(t => t.id)])];
    const wy = new Set(b.waiting.map(x => x[0]));
    // Waiting: only the tasks whose own notes on the board say they wait on him; merges marked
    const wyo = S.open.has('wy'), wyl = [...b.waiting].sort((x, y) => y[2] - x[2]), merges = b.waiting.filter(x => x[2]).length;
    const waits = `<section class="wyband" id="waiting"><div class="wgh"><span class="wyi">${ic('hand')}</span><b>Waiting</b><span class="cnt">${b.waiting.length}</span>
        <span class="small mut">${ic('merge')} ${merges ? pl(merges, 'merge', 'merges') + ' waiting' : 'no merge waiting'}</span></div>
      ${b.waiting.length ? wyl.slice(0, wyo ? wyl.length : 4).map(([id, need, mg]) => `<div class="line sub">${mg ? `<span class="mg" title="A merge waiting for you">${ic('merge', 'merge')}</span>` : '<span></span>'}<button class="lk tbtn" data-task="${esc(id)}">${tref(id, (B[id] || {}).t || id, (B[id] || {}).st)}</button><span class="grow small mut">${esc(need)}</span></div>`).join('')
        : `<p class="small mut">${b.none ? esc(b.none) : d.board && d.board.error ? 'The board could not be read just now.' : 'Nothing waits on you.'}</p>`}
      ${b.waiting.length > 4 ? `<button class="lk small" data-fold="wy" aria-expanded="${wyo}">${wyo ? 'Show the first 4' : `Show all ${b.waiting.length}`}</button>` : ''}</section>`;
    // Workers: by machine, then by the work they belong to
    const ws = mine(d), W = d.workers || {}, L = d.load || {};
    const lmark = m => { const v = L[m] || {};
      if (!v.load) return `<span class="lm none" title="This Mac's load could not be read just now">${ic('dash')} load not recorded yet</span>`;
      const pc = v.load[0] / v.cpus, cls = pc >= 0.9 ? 'bad' : pc >= 0.7 ? 'warn' : 'ok', lab = cls === 'bad' ? 'busy' : cls === 'warn' ? 'getting busy' : 'calm';
      const at = new Date(v.hist && v.hist.length ? v.hist[v.hist.length - 1][0] * 1000 : d.built).toLocaleString('en-GB', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'});
      return `<span class="lm ${cls}" title="Load ${pc.toFixed(1)} per core on the ${esc(m)} (${v.load[0].toFixed(0)} over ${v.cpus} cores), read ${esc(at)}. New workers wait over 0.9 per core."><span class="mt"><i style="width:${Math.min(100, pc / 1.2 * 100)}%"></i></span><b>${lab}</b><span class="mut">${pc.toFixed(1)} per core</span></span>`; };
    const stack = c => `<span class="stack" role="img" aria-label="${WORDER.filter(s => c[s]).map(s => `${c[s]} ${WS[s][1]}`).join(', ')}">${WORDER.filter(s => c[s]).map(s => `<i class="st-${WS[s][0]}${s === 'stuck' ? ' hatch' : ''}" style="flex:${c[s]}"></i>`).join('')}</span>
      <span class="small">${WORDER.filter(s => c[s]).map(s => `<span class="nw"><i class="dot st-${WS[s][0]}"></i> ${c[s]} ${WS[s][1]}</span>`).join(' · ')}</span>`;
    const count = list => list.reduce((o, w) => (o[w.s] = (o[w.s] || 0) + 1, o), {});
    const wsec = ['M1 Max', 'M5 Max', 'M1 Max 16'].map(m => {
      const here = ws.filter(w => w.mac === m).sort((x, y) => WORDER.indexOf(x.s) - WORDER.indexOf(y.s)), v = W[m] || {};
      const works = [...new Set(here.map(w => w.work || 'Other work'))];
      return `<div class="mgrp${here.length ? '' : ' none'}" data-mac="${esc(m)}"><div class="mgh"><h3>${ic('mac')} ${esc(m)}</h3><span class="cnt">${pl(here.length, 'worker', 'workers')}</span>
          ${here.length ? stack(count(here)) : `<span class="small mut">${v.ok === false ? 'could not be read just now' : 'none for ' + PNAME}</span>`}<span class="spacer"></span>${lmark(m)}</div>
        ${works.map(o => { const g = here.filter(w => (w.work || 'Other work') === o);
          return `<div class="wgrp"><div class="wgh"><b>${esc(o)}</b><span class="cnt">${g.length}</span></div><div class="wgrid">${g.map(tile).join('')}</div></div>`; }).join('')}</div>`; }).join('');
    // Tasks: title · bead id · state; a click opens the task panel
    const tline = t => `<div class="line sub tl${S.task === t.id ? ' ev' : ''}"><button class="lk tbtn" data-task="${esc(t.id)}">${tref(t.id, t.title, t.st)}</button>
      <span class="grow"></span>${wy.has(t.id) ? `<span class="wyi" title="Waiting on you">${ic('hand', 'waiting on you')}</span>` : ''}${t.on.length ? `<span class="small mut nw" title="Waits on ${esc(t.on.map(x => tclean(x[1])).join('; '))}">${ic('link')} ${t.on.length}</span>` : ''}<span class="small mut nw">${esc(t.type)}</span></div>`;
    const tgroup = ([g, label, c]) => { const all = b.tasks.filter(t => t.g === g), o = S.open.has('tg:' + g) !== (g === 'ready' || g === 'blocked'), full = S.open.has('tgall:' + g);
      return `<div class="grp"><button class="fold" data-fold="tg:${g}" aria-expanded="${o}">${ic('chev')} ${esc(label)} <span class="cnt">${c}</span></button>${o ? all.slice(0, full ? all.length : 12).map(tline).join('')
        + (all.length > 12 ? `<p class="small mut"><button class="lk small" data-fold="tgall:${g}" aria-expanded="${full}">${full ? 'Show the first 12' : `Show all ${all.length}`}</button></p>` : '') : ''}</div>`; };
    const jobs = myJobs(d), nfail = jobs.filter(j => j.failing).length;
    const jrow = j => { const q = S.rerun.get(j.path), when = t => t ? new Date(t).toLocaleString('en-GB', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'}) : '';
      return `<div class="line job"><i class="dot st-${j.failing ? 'failed' : 'done'}" role="img" aria-label="${j.failing ? 'failing' : 'passing'}"></i><span class="grow">${esc(j.name)}${j.failing ? ` <span class="err-t small nw">failing${j.since ? ' since ' + esc(when(j.since)) : ''}</span>` : ''}</span>
        <span class="runs" role="img" aria-label="Last ${j.runs.length} runs, newest first">${j.runs.slice(0, 12).map(r => `<i class="st-${r.ok === false ? 'failed' : r.ok == null ? 'progress' : 'done'}" title="${esc(when(r.t))}: ${r.ok === false ? 'failed' : r.ok == null ? 'running' : 'passed'}"></i>`).join('')}</span>
        ${q ? `<span class="saved small">Rerun started</span>${P.inertMark()}<button class="lk small" data-unrerun="${esc(j.path)}">Undo</button>`
          : S.ask === j.path ? `<span class="small">Rerun now?</span><button class="btn sm" data-rerun="${esc(j.path)}">Rerun</button><button class="lk small" data-ask="">Keep</button>${P.inertMark()}`
          : `<button class="ib" data-ask="${esc(j.path)}" title="Rerun ${esc(j.name)}" aria-label="Rerun ${esc(j.name)}">${ic('rerun')}</button>`}</div>`; };
    const prs = Array.isArray(d.prs) ? d.prs : [], po = S.open.has('prs'), opn = prs.filter(p => p.state === 'open').length;
    return `${waits}
      <section class="rsec" id="workers"><h2 class="ph">Workers <span class="cnt">${ws.length}</span> <span class="small mut nb">live on the three Macs</span></h2>${W.error ? `<p class="mut">Orca could not be read just now.</p>` : wsec}</section>
      <div class="rgrid"><section class="rsec" id="tasks"><h2 class="ph">Tasks <span class="cnt">${b.tasks.length}</span> <span class="small mut nb">not closed on the board · ${b.ready || 0} ready</span></h2>
          ${(b.groups || []).map(tgroup).join('')}<p class="small mut">${b.none ? esc(b.none) : `The ${esc(PNAME)} board, read only${b.closed ? `; the ${b.closed.toLocaleString()} closed tasks are not listed` : ''}.`}</p></section>
        <div><section class="rsec" id="jobs"><h2 class="ph">Scheduled jobs <span class="cnt${nfail ? ' bad' : ''}">${nfail ? nfail + ' failing' : jobs.length}</span></h2>${jobs.map(jrow).join('') || `<p class="mut small">${d.jobs && d.jobs.error ? 'Windmill could not be read just now.' : `${esc(PNAME)} has no scheduled jobs, so none are listed.`}</p>`}</section>
          <section class="rsec" id="prs"><h2 class="ph"><button class="fold" data-fold="prs" aria-expanded="${po}">${ic('chev')} Pull requests <span class="cnt">${opn ? opn + ' open' : prs.length}</span></button></h2>
            ${po ? prs.map(p => `<div class="line sub"><span class="grow"><b>${esc(p.id)}</b> · ${esc(cut(p.title, 110))}</span>${stPill(p.state === 'merged' ? 'closed' : p.state === 'open' ? 'in progress' : 'deferred').replace(/>[a-z ]+<\/span>$/, `>${esc(p.draft ? 'draft' : p.state)}</span>`)}<button class="ib" data-copy="${esc(p.url)}" title="Copy the link to ${esc(p.id)}" aria-label="Copy the link to ${esc(p.id)}">${ic('copy')}</button></div>`).join('') || `<p class="small mut">${d.prs && d.prs.error ? 'GitHub could not be read just now.' : `${esc(PNAME)} has no pull requests this page can read, so none are listed.`}</p>` : ''}</section></div></div>
      <p class="small mut rn-src">Read ${esc(new Date(d.built).toLocaleString('en-GB', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'}))}; each source is read at most once a minute.</p>
      ${panel()}${termSheet(ws)}`;
  }
  // Open terminal on a phone or iPad: Orca's terminal can't show here, so the worker's last report and Bring it forward on the Mac (the mock's termSheet, #120)
  function termSheet(ws) {
    const w = S.peek && ws.find(x => x.name === S.peek); if (!w) return '';
    return `<div class="sheet rn-peek" role="dialog" aria-label="Terminal of ${esc(wnm(w.name))}"><div class="box"><div class="tpbar"><b>${esc(wnm(w.name))}</b><span class="spacer"></span><button class="ib" data-peek="" aria-label="Close">${ic('x')}</button></div>
      <p class="small">Its terminal is in Orca on the ${esc(w.mac || 'M1 Max')}. A phone or iPad can't show an Orca terminal from this page, so here is what it said last; Bring it forward puts it on the Mac's screen.</p>
      <div class="wt st-${WS[w.s][0]}"><div class="wt2"><i class="dot st-${WS[w.s][0]}" role="img" aria-label="${WS[w.s][1]}"></i><span>${WS[w.s][1]}</span><span class="mb ${esc(w.agent)}">${esc(mdl(w))}</span><span class="small">${ago(w.mins)}</span></div>
        <div class="wt3 small">${ic('msg')}<span class="${w.report ? '' : 'mut'}">${esc(scrub(w.report) || 'no report yet')}</span></div></div>
      <p><button class="btn pri" data-termmac="${esc(w.name)}">${ic('term')} Bring it forward on the Mac</button> <button class="btn" data-peek="">Close</button>${P.inertMark()}</p></div></div>`;
  }
  // a worker as a tile, every worker, as in the mock: state and name with Open terminal; model, time running, last sign of life; last report; no Stop
  const tile = w => `<div class="wt st-${WS[w.s][0]}${w.s === 'stuck' ? ' hatch' : ''}"><div class="wt1"><i class="dot st-${WS[w.s][0]}" role="img" aria-label="${WS[w.s][1]}"></i><b class="wn" title="${esc(w.name)}">${esc(wnm(w.name))}</b>
        <button class="ib" data-term="${esc(w.name)}" title="Open its terminal in Orca" aria-label="Open the terminal of ${esc(wnm(w.name))} in Orca">${ic('term')}</button></div>
      <div class="wt2"><span class="mb ${esc(w.agent)}">${esc(mdl(w))}</span><span class="tbar" title="Running ${ago(w.mins)}"><i style="width:${Math.max(4, Math.min(100, (w.mins || 0) / 120 * 100))}%"></i></span><span class="small nw">${ago(w.mins)}</span>
        ${w.s !== 'failed' && w.heard != null ? `<span class="small nw ${w.s === 'stuck' ? 'stuck-t' : 'mut'}" title="Its last sign of life">${ic('pulse')} ${ago(w.heard)} ago</span>` : ''}</div>
      <div class="wt3 small" title="${esc(w.report || 'No report yet')}">${ic('msg')}<span class="${w.report ? '' : 'mut'}">${esc(scrub(w.report) || 'no report yet')}</span></div></div>`;

  /* ------------------------------------------------------------ the task panel: review, status and comment */
  const PRI = ['most urgent', 'urgent', 'normal', 'low', 'lowest'];
  function panel() {
    if (!S.task) return '';
    const id = S.task, b = ((D.board || {}).beads || {})[id], wyx = ((D.board || {}).waiting || []).find(x => x[0] === id);
    const pos = S.list.indexOf(id), prv = pos > 0 ? S.list[pos - 1] : '', nxt = pos >= 0 && pos < S.list.length - 1 ? S.list[pos + 1] : '';
    const bar = `<div class="tpbar"><span class="tpnav"><button class="ib" data-task="${esc(prv)}" ${prv ? '' : 'disabled'} title="Previous task (K)" aria-label="Previous task">${ic('up')}</button><span class="pos" aria-live="polite">${pos >= 0 ? `task ${pos + 1} of ${S.list.length}` : ''}</span><button class="ib" data-task="${esc(nxt)}" ${nxt ? '' : 'disabled'} title="Next task (J)" aria-label="Next task">${ic('down')}</button></span>
      <span class="spacer"></span><button class="ib" data-copy="${esc(id)}" title="Copy the bead id" aria-label="Copy the bead id">${ic('copy')}</button><button class="ib" data-task="" title="Close (Esc)" aria-label="Close the task">${ic('x')}</button></div>`;
    if (!b) return `<aside class="tpanel" role="dialog" aria-label="Task ${esc(id)}">${bar}<div class="tpscroll"><h2 class="tpti">${esc(id)}</h2><p class="mut">Not open on the board.</p></div></aside>`;
    const dot = st => `<i class="dot st-${BST[st] || 'none'}"></i>`;
    const own = b.own === 'changlee' ? 'You' : !b.own ? 'Nobody yet' : 'A worker';
    const pills = `<div class="tpills"><span class="tpl" title="State on the board">${dot(b.st)}${esc(b.st)}</span><span class="tpl" title="Owner">${ic('user')}${own}</span>${b.pri != null ? `<span class="tpl pri${esc(b.pri)}" title="Priority ${esc(b.pri)} of 0 to 4">P${esc(b.pri)} · ${PRI[b.pri] || ''}</span>` : ''}</div>`;
    const openOn = b.on.filter(x => x[2] !== 'closed');
    const need = wyx ? wyx[1].charAt(0).toUpperCase() + wyx[1].slice(1) : b.st === 'blocked' && openOn.length ? `Waits on ${pl(openOn.length, 'task', 'tasks')} first: ${tclean(openOn[0][1])}` : b.st === 'in progress' ? 'Being worked on' : cut(scrub(b.desc).split(/(?<=\.)\s/)[0] || 'No description written.', 140);
    const tst = CTX.prefs.get('tst', {}), pend = tst[id], cur = pend || b.st;
    const seg = `<div class="tseg" role="radiogroup" aria-label="Status">${['open', 'in progress', 'blocked', 'closed'].map(s => `<button role="radio" aria-checked="${cur === s}" data-tst="${esc(s)}" title="${s === b.st ? 'Its state on the board' : 'Change it to ' + s}">${dot(s)}<span class="l">${s.charAt(0).toUpperCase() + s.slice(1)}</span></button>`).join('')}</div>
      ${pend ? `<div class="tpend" role="status">${dot(b.st)}${esc(b.st)} → ${dot(pend)}<b>${esc(pend)}</b><span class="mut">· goes to the board with your next Send</span>${P.inertMark()}<button class="lk small" data-untst="1">Undo</button></div>` : ''}`;
    const chips = (h, xs) => `<div class="small mut tph">${h} <span class="cnt">${xs.length}</span></div>${xs.length ? `<div class="dchips">${xs.map(([x, t, st]) => `<button class="dchip" ${((D.board || {}).beads || {})[x] ? `data-task="${esc(x)}"` : 'disabled'} title="${esc(tclean(t))} · ${esc(x)} · ${esc(st)}">${dot(st)}<span class="t">${esc(cut(tclean(t), 44))}</span><span class="bid">${esc(x)}</span></button>`).join('')}</div>` : '<p class="small mut nothing">nothing</p>'}`;
    const fold = (h, v, n) => { const o = S.open.has('tp:' + h); return `<div class="tfold"><button data-fold="tp:${h}" aria-expanded="${o}">${ic('chev')}${h}${n != null ? ` <span class="cnt">${n}</span>` : ''}${!v && n == null ? ' <span class="small mut nb">none written</span>' : ''}</button>${o ? v || '' : ''}</div>`; };
    const da = S.open.has('tp:descall'), long = (b.desc || '').length > 600;
    const ctext = CTX.prefs.get('tcm:' + id, '');
    return `<aside class="tpanel" role="dialog" aria-label="Task ${esc(id)}">${bar}
      <div class="tpscroll"><h2 class="tpti">${esc(tclean(b.t))} <span class="bid">${esc(id)}</span></h2>${pills}
        <div class="tneed${wyx ? ' you' : ''}">${ic(wyx ? 'hand' : 'pulse')}<span>${esc(need)}</span></div>${seg}
        <div class="small mut tph">Description</div><div class="tdesc${long && !da ? ' clamp' : ''}">${esc(scrub(b.desc)) || '<span class="mut">No description written.</span>'}</div>${long ? `<button class="lk small" data-fold="tp:descall" aria-expanded="${da}">${da ? 'Show less' : 'Show all'}</button>` : ''}
        ${chips('Needs first', b.on)}${chips('Needed by', b.by)}
        ${fold('Design', b.design && `<div class="tpt">${esc(scrub(b.design))}</div>`)}${fold('Acceptance', b.acc && `<div class="tpt">${esc(scrub(b.acc))}</div>`)}${fold('Notes', b.notes && `<div class="tpt">${esc(scrub(b.notes))}</div>`)}
        ${fold('Comments', b.cm.map(([at, t]) => `<div class="tcm"><span class="small mut">${esc(at)}</span><div class="tpt">${esc(scrub(t))}</div></div>`).join('') || `<p class="small mut">${b.ncm ? pl(b.ncm, 'comment', 'comments') + ' on the board' : 'none yet'}</p>`, b.ncm || b.cm.length)}
        <p class="small mut">${esc(b.type)} · opened ${esc(b.made)} · updated ${esc(b.upd)} · from the ${PNAME} board, read only</p></div>
      <div class="tcbox"><textarea data-tcm aria-label="Comment on this task" placeholder="Comment on this task">${esc(ctext)}</textarea>
        <div class="acts small mut"><span data-tcmsay>${ctext.trim() ? 'Saved as you type · goes to the board with your next Send' : 'Goes to the board with your next Send'}</span>${P.inertMark()}<button class="lk small" data-untcm ${ctext.trim() ? '' : 'hidden'}>Remove</button></div></div></aside>`;
  }

  /* ------------------------------------------------------------ chart helpers (the mock's, after the dataviz method) */
  const tip = (h, d) => `data-tip="${esc(h)}|${esc(d || '')}"`;
  const narrow = () => innerWidth < 700;
  function spark(vals) {
    const W = 200, H = 28, mx = Math.max(...vals) || 1, mn = Math.min(...vals), X = i => 2 + i * (W - 6) / Math.max(1, vals.length - 1), Y = v => H - 3 - (v - mn) / ((mx - mn) || 1) * (H - 6);
    return `<svg class="spk" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true"><polyline class="ln" points="${vals.map((v, i) => `${X(i)},${Y(v)}`).join(' ')}"/><circle class="pt" cx="${X(vals.length - 1)}" cy="${Y(vals.at(-1))}" r="2.5"/></svg>`;
  }
  function lchart(pts, o = {}) {
    if (!pts.length) return '<p class="small mut">No readings yet.</p>';
    const fmt = o.fmt || (v => Math.round(v).toLocaleString()), n = pts.length, W = narrow() ? 380 : 640, H = 176, L = 44, R = 12, B = 146, mx = o.max || Math.max(...pts.map(p => p[1])) || 1;
    const X = i => L + (n < 2 ? 0 : i * (W - L - R) / (n - 1)), Y = v => B - v / mx * 122, st = n > 1 ? (W - L - R) / (n - 1) : W - L - R;
    const line = pts.map(([, v], i) => `${X(i)},${Y(v)}`).join(' ');
    return `<svg class="ach lnc" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.t || '')}">
      ${[0, .5, 1].map(f => `<line x1="${L}" x2="${W - R}" y1="${Y(mx * f)}" y2="${Y(mx * f)}" class="${f ? 'grid' : 'axl'}"/><text x="${L - 6}" y="${Y(mx * f) + 4}" text-anchor="end" class="cax">${fmt(mx * f)}</text>`).join('')}
      ${o.gate ? `<line x1="${L}" x2="${W - R}" y1="${Y(o.gate[0])}" y2="${Y(o.gate[0])}" class="gl"/><text x="${W - R}" y="${Y(o.gate[0]) - 4}" text-anchor="end" class="cax gt">${esc(o.gate[1])}</text>` : ''}
      <polygon class="ar" points="${X(0)},${B} ${line} ${X(n - 1)},${B}"/><polyline class="ln" points="${line}"/>
      ${pts.map(([d, v], i) => `<g class="xg${i === n - 1 ? ' end' : ''}" ${tip(fmt(v), d)}><rect class="hit" x="${X(i) - st / 2}" y="0" width="${st}" height="${B}"/><line class="xh" x1="${X(i)}" x2="${X(i)}" y1="10" y2="${B}"/><circle class="pt" cx="${X(i)}" cy="${Y(v)}" r="4.5"/></g>`).join('')}
      <text x="${X(n - 1)}" y="${Y(pts[n - 1][1]) - 10}" text-anchor="end" class="cax vl">${fmt(pts[n - 1][1])}</text>
      <text x="${L}" y="${H - 10}" class="cax">${esc(pts[0][0])}</text><text x="${W - R}" y="${H - 10}" text-anchor="end" class="cax">${esc(pts[n - 1][0])}</text></svg>`;
  }
  function cols(pts, o = {}) {
    if (!pts.length) return '<p class="small mut">Nothing yet.</p>';
    const fmt = o.fmt || (v => Math.round(v).toLocaleString()), n = pts.length, W = narrow() ? 380 : 640, H = 170, L = 8, B = 140, mx = Math.max(o.gate ? o.gate[0] : 0, ...pts.map(p => p[1])) || 1, bw = (W - L * 2) / n, Y = v => B - v / mx * 118;
    const im = pts.reduce((m, p, i) => p[1] > pts[m][1] ? i : m, 0);
    return `<svg class="ach" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.t || '')}">
      ${[.5, 1].map(f => `<line x1="${L}" x2="${W - L}" y1="${Y(mx * f)}" y2="${Y(mx * f)}" class="grid"/>`).join('')}<line x1="${L}" x2="${W - L}" y1="${B}" y2="${B}" class="axl"/>
      ${o.gate ? `<line x1="${L}" x2="${W - L}" y1="${Y(o.gate[0])}" y2="${Y(o.gate[0])}" class="gl"/><text x="${W - L}" y="${Y(o.gate[0]) - 4}" text-anchor="end" class="cax gt">${esc(o.gate[1])}</text>` : ''}
      ${pts.map(([d, v], i) => `<g class="bar${i === o.hl ? ' hl' : ''}"><rect x="${L + i * bw + 1}" y="${Y(v)}" width="${Math.max(2, bw - 2)}" height="${Math.max(0.5, B - Y(v))}" rx="${Math.min(4, bw / 4)}"/><rect class="hit" x="${L + i * bw}" y="0" width="${bw}" height="${B}" ${tip(fmt(v), d)}/></g>`).join('')}
      ${[im, n - 1].filter((x, j, a) => a.indexOf(x) === j).map(i => `<text x="${L + i * bw + bw / 2}" y="${Y(pts[i][1]) - 5}" text-anchor="${i > n - 3 ? 'end' : 'middle'}" class="cax vl">${fmt(pts[i][1])}</text>`).join('')}
      <text x="${L}" y="${H - 12}" class="cax">${esc(pts[0][0])}</text><text x="${W - L}" y="${H - 12}" text-anchor="end" class="cax">${esc(pts[n - 1][0])}</text></svg>`;
  }
  function hbars(rows, o = {}) {
    const fmt = o.fmt || (v => Math.round(v).toLocaleString()), mx = o.max || Math.max(...rows.map(r => r[1])) || 1;
    return `<div class="hb" role="list">${rows.map(([l, v, h, t]) => `<div class="hbr${h ? ' hl' : ''}" role="listitem" ${tip(fmt(v), t || l)}><span class="hbl">${esc(l)}</span><span class="hbt"><i style="width:${Math.max(1, v / mx * 100)}%"></i></span><span class="hbv">${fmt(v)}</span></div>`).join('')}</div>`;
  }
  function stacks(rows, keys) {
    const mx = Math.max(...rows.map(r => keys.reduce((s, [k]) => s + (r[1][k] || 0), 0))) || 1;
    return `<div class="lgd small">${keys.map(([k, l, st]) => `<span><i class="key st-${st}"></i> ${esc(l)}</span>`).join('')}</div><div class="hb">${rows.map(([l, c, h]) => { const tot = keys.reduce((s, [k]) => s + (c[k] || 0), 0);
      return `<div class="hbr${h ? ' hl' : ''}"><span class="hbl">${esc(l)}</span><span class="hbt stk" style="--w:${tot / mx * 100}%">${keys.map(([k, kl, st]) => c[k] ? `<i class="st-${st}" style="flex:${c[k]}" ${tip(`${c[k].toLocaleString()} ${kl}`, `${l}: ${Math.round(c[k] / tot * 100)}% of ${tot.toLocaleString()} workers`)}></i>` : '').join('')}</span><span class="hbv">${tot.toLocaleString()}</span></div>`; }).join('')}</div>`;
  }
  function segbar(parts, unit) {
    const tot = parts.reduce((s, p) => s + p[1], 0) || 1, col = (l, i) => /^Other\b/.test(l) ? '#898781' : `var(--c${i + 1})`;
    return `<div class="segbar" role="img" aria-label="${esc(parts.map(([l, n]) => `${l} ${Math.round(n / tot * 100)}%`).join(', '))}">${parts.map(([l, n], i) => { const p = Math.round(n / tot * 100);
        return `<i class="${i === 3 ? 'dk' : ''}" style="flex:${n};background:${col(l, i)}" tabindex="0" ${tip(`${l}: ${p}%`, `${n.toLocaleString()} ${unit} of ${tot.toLocaleString()}`)}>${p >= 12 ? p + '%' : ''}</i>`; }).join('')}</div>
      <div class="lgd small">${parts.map(([l, n], i) => `<span><i class="key" style="background:${col(l, i)}"></i>${esc(l)} <b>${Math.round(n / tot * 100)}%</b></span>`).join('')}</div>`;
  }
  function donut(a, b, la, lb, unit) {
    const t = a + b || 1, C = 2 * Math.PI * 50, p = Math.round(a / t * 100);
    return `<div class="donut"><svg viewBox="0 0 132 132" role="img" aria-label="${esc(`${la} ${p}%, ${lb} ${100 - p}%`)}"><circle class="trk" cx="66" cy="66" r="50" ${tip(`${lb}: ${100 - p}%`, `${b.toLocaleString()} ${unit}`)}/><circle class="arc" cx="66" cy="66" r="50" stroke-dasharray="${a / t * C} ${C}" transform="rotate(-90 66 66)" ${tip(`${la}: ${p}%`, `${a.toLocaleString()} ${unit}`)}/></svg>
      <div><div class="big">${p}%</div><div class="small">${esc(la)} · ${a.toLocaleString()} ${unit}</div><div class="small mut">${esc(lb)} · ${b.toLocaleString()} ${unit}</div></div></div>`;
  }
  const tbl = (head, rows) => `<details class="tview"><summary class="small">Table</summary><div class="tw"><table><thead><tr>${head.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>`;
  const acard = (t, body, src) => `<div class="acard"><h3>${t}</h3>${body}<p class="src">${src}</p></div>`;
  const atile = (big, lab, cls = '', sp) => `<div class="atile ${cls}"><b>${big}</b><span>${lab}</span>${sp || ''}</div>`;

  /* ------------------------------------------------------------ Analytics */
  function analytics() {
    const A = D.an && !D.an.error ? D.an : {}, N = A.names || {}, q = (A.qa || {})[PROJ], oc = (A.orca || {})[PROJ], cb = A.comeback || {}, U = A.usage || [];
    const pct = (a, b) => b ? Math.round(a / b * 100) : 0;
    const qaRows = Object.entries(A.qa || {}).filter(([, x]) => x.sel >= 10).sort((a, b) => pct(b[1].rec, b[1].sel) - pct(a[1].rec, a[1].sel));
    const wk = (A.qaWeeks || []).map(([w, n, r]) => [w.replace(/^\d+-W/, 'week '), pct(r, n)]);
    const ttvRows = Object.entries(A.qa || {}).filter(([, x]) => x.ttvMed != null && x.sends >= 5).sort((a, b) => a[1].ttvMed - b[1].ttvMed);
    const sesRows = Object.entries(A.sessions || {}).filter(([p]) => p !== 'other').sort((a, b) => b[1] - a[1]);
    const QA = `<div class="agrp cv h1" id="an-qa"><h2 class="ph">Questions and answers</h2><div class="atiles">
        ${q && q.sel ? atile(pct(q.rec, q.sel) + '%', `of ${q.sel.toLocaleString()} picks were the recommended choice, by week`, '', wk.length > 1 ? spark(wk.map(x => x[1])) : '') : atile('—', 'no picks recorded yet', 'dim')}
        ${q && q.ttvMed != null ? atile(ago(q.ttvMed), 'median time from a question to your answer') : ''}
        ${cb.questions ? atile((cb.questions - cb.oneSend).toLocaleString(), `of ${cb.questions.toLocaleString()} questions needed a second Send on the same card`, cb.questions - cb.oneSend ? 'warn' : '') : ''}
        ${q ? atile(q.sends.toLocaleString(), `Sends, with ${q.words.toLocaleString()} answers in words`) : ''}</div>
      <div class="agrid">
        ${acard('Recommended choice picked, by project', hbars(qaRows.map(([p, x]) => [N[p] || p, pct(x.rec, x.sel), p === PROJ, `${N[p] || p}: ${x.rec.toLocaleString()} of ${x.sel.toLocaleString()} picks`]), {max: 100, fmt: v => v + '%'}) + tbl(['Project', 'Picks', 'Recommended'], qaRows.map(([p, x]) => [N[p] || p, x.sel, x.rec])),
          `${PNAME} from this page's own record; the others from their review pages on this Mac. A pick counts as recommended when it matches the option the card recommended. Projects with fewer than 10 picks left out.`)}
        ${wk.length ? acard(`Recommended choice picked, by week · ${PNAME}`, lchart(wk, {fmt: v => Math.round(v) + '%', t: 'Recommended share by week', max: 100}) + tbl(['Week', 'Picks', 'Recommended'], A.qaWeeks), "This page's Sends, by the week of the answer.") : ''}
        ${acard('Time from a question to your answer, by project', hbars(ttvRows.map(([p, x]) => [N[p] || p, x.ttvMed, p === PROJ]), {fmt: v => ago(v)}) + tbl(['Project', 'Median minutes', 'Sends'], ttvRows.map(([p, x]) => [N[p] || p, x.ttvMed, x.sends])),
          `Median minutes from when a card asked to when you answered it.${q && q.ttvP90 != null ? ` On this page the slowest tenth took over ${ago(q.ttvP90)}.` : ''}`)}
        ${(A.qpv || []).length ? acard('Questions asked per version · the newest 40', cols(A.qpv.map(([v, n]) => [`version ${v}`, n]), {t: 'Questions asked per version', hl: A.qpv.length - 1}) + tbl(['Version', 'Questions'], A.qpv), "Questions asked in each published version of this page.") : ''}
        ${cb.sendsHist ? acard('The same issue coming back', `${segbar(cb.sendsHist.map(([s, n]) => [s === 1 ? 'settled in 1 Send' : `answered in ${s} Sends`, n]), 'questions')}${tbl(['Sends', 'Questions'], cb.sendsHist)}
            <p class="small"><b>${cb.reasked}</b> more came back as a new card with the same wording, which the count above leaves out. Most often:</p>${(cb.top || []).map(([n, t]) => `<div class="line small"><span class="cnt">${n}×</span><span class="grow">${esc(cut(t, 90))}</span></div>`).join('')}`,
          "This page's Sends: a card answered in more than one Send, and the same wording asked again on a new card.") : ''}
      </div></div>`;
    const orcRows = Object.entries(A.orca || {}).filter(([p]) => p !== 'other').sort((a, b) => b[1].workers - a[1].workers), ses = A.sessions || {};
    const SW = `<div class="agrp cv h7" id="an-work"><h2 class="ph">Sessions and workers</h2><div class="atiles">
        ${atile((ses[PROJ] || 0).toLocaleString(), `Claude Code sessions for ${PNAME} on this Mac`)}
        ${oc ? atile(oc.workers.toLocaleString(), `Orca workers since ${esc(A.orcaSince)}, by week`, '', oc.weeks.length > 1 ? spark(oc.weeks.map(w => w[1])) : '') : atile('0', 'Orca workers on this Mac', 'dim')}
        ${oc ? atile(pct(oc.failed, oc.workers) + '%', 'of workers failed', pct(oc.failed, oc.workers) > 15 ? 'warn' : '') : ''}
        ${oc ? atile(`${oc.codex.toLocaleString()} · ${oc.claude.toLocaleString()}`, 'Codex · Claude workers') : ''}</div>
      <div class="agrid">
        ${acard('Workers by project and outcome', stacks(orcRows.map(([p, o]) => [N[p] || p, {done: o.ok, failed: Math.max(0, o.failed - o.stopped), stopped: o.stopped}, p === PROJ]), [['done', 'finished', 'done'], ['failed', 'failed', 'failed'], ['stopped', 'stopped by a coordinator', 'none']]) + tbl(['Project', 'Workers', 'Finished', 'Failed', 'Stopped'], orcRows.map(([p, o]) => [N[p] || p, o.workers, o.ok, o.failed, o.stopped])),
          `Orca's record on this Mac since ${esc(A.orcaSince)}. Work run from the M5 Max's own coordinators is in its record, not here.`)}
        ${oc && oc.weeks.length ? acard(`Workers per week · ${PNAME}`, lchart(oc.weeks.map(([w, n]) => [w.replace(/^\d+-W/, 'week '), n]), {t: 'Workers per week'}) + tbl(['Week', 'Workers'], oc.weeks), 'Orca workers started each ISO week, this Mac.') : ''}
        ${oc && oc.codex + oc.claude ? acard('Which agent ran the workers', donut(oc.codex, oc.claude, 'Codex', 'Claude', 'workers') + tbl(['Agent', 'Workers'], [['Codex', oc.codex], ['Claude', oc.claude]]),`Orca's record on this Mac since ${esc(A.orcaSince)}.`) : ''}
        ${acard('Claude Code sessions by project', hbars(sesRows.map(([p, n]) => [N[p] || p, n, p === PROJ])) + tbl(['Project', 'Sessions'], sesRows.map(([p, n]) => [N[p] || p, n])),
          `Session transcripts under the Claude Code folder on this Mac, by the folder each ran in; ${(ses.other || 0).toLocaleString()} sessions in other folders left out. Codex sessions are not counted yet.`)}
      </div></div>`;
    const last = U[U.length - 1] || {}, w7 = U.slice(-7), wUsd = w7.reduce((s, d) => s + d.usd, 0), wC = w7.reduce((s, d) => s + d.commits, 0);
    const ROLE = {'orchestrator': 'coordinators', 'design-ui': 'screen design', 'worker-other': 'other workers', 'uat-device': 'phone tests', 'gate-runner': 'checks before merge', 'page-annotate': 'review pages', 'review-judge': 'reviews', 'sweep': 'clean-ups', 'team-lead': 'leads', 'ci-build-merge': 'builds and merges', 'interactive': 'your own sessions'};
    const roles = (last.roles || []).map(([r, v]) => [ROLE[r] || r.replace(/-/g, ' '), v]).sort((a, b) => b[1] - a[1]);
    const UC = `<div class="agrp cv h2" id="an-use"><h2 class="ph">Usage and cost</h2>${U.length ? `<div class="atiles">
        ${atile('$' + Math.round(last.usd).toLocaleString(), `spent on ${dm(last.d)}, API-equivalent; ${U.length} days`, '', spark(U.map(d => d.usd)))}${atile('$' + Math.round(wUsd).toLocaleString(), 'the last 7 days', '', spark(w7.map(d => d.usd)))}
        ${atile('$' + (wC ? (wUsd / wC).toFixed(1) : '—'), `per merged app change, last 7 days (${wC} changes)`, '', spark(w7.map(d => d.commits ? d.usd / d.commits : 0)))}${atile(last.cacheM + 'M', `tokens of context saved for reuse that day; ${U.length} days`, '', spark(U.map(d => d.cacheM || 0)))}</div>
      <div class="agrid">
        ${acard('Spend per day', lchart(U.map(d => [dm(d.d), d.usd]), {fmt: v => '$' + Math.round(v).toLocaleString(), t: 'Spend per day'}) + tbl(['Day', 'Dollars', 'Requests', 'Merged changes'], U.map(d => [d.d, d.usd, d.req, d.commits])), `${PNAME}'s daily usage reports, ${U.length} days, API-equivalent dollars.`)}
        ${acard('Requests per day', lchart(U.map(d => [dm(d.d), d.req]), {t: 'Requests per day'}) + tbl(['Day', 'Requests'], U.map(d => [d.d, d.req])), `${PNAME}'s daily usage reports.`)}
        ${acard('Most workers at once, per day', cols(U.map(d => [dm(d.d), d.peak]), {t: 'Most workers at once', gate: [8, 'cap 8'], hl: U.length - 1}) + tbl(['Day', 'Workers at once'], U.map(d => [d.d, d.peak])), `${PNAME}'s daily usage reports.`)}
        ${roles.length ? acard(`Where ${dm(last.d)}'s spend went, by role`, segbar([...roles.slice(0, 5), ...(roles.length > 5 ? [['Other roles', roles.slice(5).reduce((s, x) => s + x[1], 0)]] : [])], 'dollars') + tbl(['Role', 'Dollars'], roles), "The newest daily usage report's split by worker role: the five largest, the rest as other roles.") : ''}
      </div>` : PROJ === 'fld' ? `<p class="mut">No usage reports could be read.</p>` : `<p class="mut dim">Nothing yet: ${PNAME} keeps no usage reports. FastLane Drive's daily reports are the only ones on this Mac.</p>`}</div>`;
    const SV = `<div class="agrp" id="an-saves"><h2 class="ph">What this page saves</h2>${savesHtml(q, cb)}</div>`;
    return `<nav class="ajump small" aria-label="Analytics groups">${[['an-qa', 'Questions and answers'], ['an-work', 'Sessions and workers'], ['an-use', 'Usage and cost'], ['an-mac', 'Machine load'], ['an-saves', 'What this page saves']].map(([i, t]) => `<a href="#analytics/${i}">${t}</a>`).join('')}</nav>${QA}${SW}${UC}${loadGroup()}${SV}`;
  }
  // What this page saves, from the mock: clicks measured by its click script against today's page, and one round projected from them
  const SAVES = [['Answer with the recommended choice', 1, 1], ['Answer with another choice', 1, 1], ['Send what you answered', 2, 2], ['Pin a note on a picture', 3, 2], ['Compare two versions', 3, 2], ['Find a past decision', 2, 1, 'one click and a scroll'], ['Open the bead board', 1, 1], ['Switch light and dark', 1, 1]];
  function savesHtml(q, cb) {
    const o = S.open.has('saves'), r = {q: 17, pin: 3, cmp: 1, past: 1}, t = SAVES, tot = i => r.q * t[0][i] + t[2][i] + r.pin * t[3][i] + r.cmp * t[4][i] + r.past * t[5][i];
    return `<div class="grp"><button class="fold" data-fold="saves" aria-expanded="${o}">${ic('chev')} What this page saves <span class="small mut nb">· ${tot(1) - tot(2)} clicks in a round like today's, projected</span></button>${o ? `<div class="tw"><table class="svt"><thead><tr><th>Task</th><th>Clicks today</th><th>Clicks now</th></tr></thead><tbody>${t.map(([w, a, b, note]) => `<tr><td>${esc(w)}</td><td>${note ? esc(note) : pl(a, 'click', 'clicks')}</td><td>${pl(b, 'click', 'clicks')}${b < a ? ` <span class="rn-pill st-done">saves ${pl(a - b, 'click', 'clicks')}</span>` : ''}</td></tr>`).join('')}
      <tr><td><b>A round like today's</b>: ${r.q} questions answered, ${r.pin} notes on pictures, ${r.cmp} comparison, ${r.past} past decision found, then Send</td><td><b>${pl(tot(1), 'click', 'clicks')}</b> plus a scroll</td><td><b>${pl(tot(2), 'click', 'clicks')}</b></td></tr>
      ${q && q.ttvMed != null ? `<tr><td>Time from a question appearing to your answer</td><td>median ${ago(q.ttvMed)}</td><td class="small mut">counted from the same record once this page ships</td></tr>` : ''}
      ${cb && cb.questions ? `<tr><td>Sends per decision</td><td>${cb.oneSend.toLocaleString()} of ${pl(cb.questions, 'question', 'questions')} settled in one Send</td><td>the same one Send; Undo and Answer later keep it at one</td></tr>` : ''}</tbody></table></div>
      <p class="small mut">Clicks measured on the approved mock by its click script, today's counts on the live page. The page does not change how many Sends a round takes, so no saving in turns is claimed.</p>` : ''}</div>`;
  }
  // machine load: each Mac's recorder (one line a minute, launchd)
  function loadGroup() {
    const L = D.load || {}, m1 = L['M1 Max'] || {}, h = m1.hist || [];
    const thin = h => { const step = Math.max(1, Math.round(h.length / 144)); return h.filter((_, i) => i % step === 0 || i === h.length - 1); };  // one point per ten minutes over a day
    const pts = thin(h);
    const t = e => new Date(e * 1000).toLocaleTimeString('en-GB', {hour: '2-digit', minute: '2-digit'});
    const charts = ['M1 Max', 'M5 Max', 'M1 Max 16'].filter(m => ((L[m] || {}).hist || []).length).map(m => { const v = L[m], p = thin(v.hist);
      return acard(`Load per core, last 24 hours · ${m}`, lchart(p.map(r => [t(r[0]), r[1] / v.cpus]), {fmt: x => x.toFixed(1), t: 'Load per core', gate: [0.9, 'new workers wait']}) + tbl(['Time', 'Load', 'Per core'], p.map(r => [t(r[0]), r[1], (r[1] / v.cpus).toFixed(2)])), `The ${m}'s own recorder: the 1-minute load average over its ${v.cpus} cores, one reading a minute. New workers wait over 0.9 per core.`)
        + acard(`Memory free, last 24 hours · ${m}`, lchart(p.map(r => [t(r[0]), r[2]]), {fmt: x => Math.round(x) + '%', t: 'Memory free', max: 100}) + tbl(['Time', 'Memory free %', 'Disk used %'], p.map(r => [t(r[0]), r[2], r[3]])), 'Free, inactive and speculative memory as a share of the whole, from the same readings.'); }).join('');
    const pc = m1.load ? m1.load[0] / m1.cpus : null, lastMem = h.length ? h[h.length - 1][2] : null, disk = h.length ? h[h.length - 1][3] : null;
    const rows = ['M1 Max', 'M5 Max', 'M1 Max 16'].map(m => { const v = L[m] || {};
      return `<div class="line sub">${ic('mac')}<b class="grow">${esc(m)}</b>${v.recorded ? `<span class="rn-pill st-done"><i class="dot"></i>recording once a minute</span><span class="small mut">since ${esc(new Date(v.since * 1000).toLocaleString('en-GB', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'}))}</span>` : '<span class="rn-pill st-progress"><i class="dot"></i>recorder installed: first readings soon</span>'}</div>`; }).join('');
    return `<div class="agrp cv h3" id="an-mac"><h2 class="ph">Machine load</h2><div class="atiles">
        ${pc != null ? atile(pc.toFixed(1), `load per core on the M1 Max now (${Math.round(m1.load[0])} over ${m1.cpus} cores)`, pc > 0.9 ? 'bad' : pc > 0.7 ? 'warn' : '', h.length > 1 ? spark(pts.map(r => r[1] / m1.cpus)) : '') : ''}
        ${lastMem != null ? atile(lastMem + '%', 'memory free or reclaimable at the last reading', lastMem < 10 ? 'warn' : '') : ''}
        ${disk != null ? atile(disk + '%', 'disk used at the last reading', disk > 90 ? 'warn' : '') : ''}
        ${atile(pl(h.length, 'reading', 'readings'), 'on the M1 Max in the last 24 hours')}</div>
      <div class="agrid">
        ${charts}
        ${acard('Which Macs record their load', rows, 'Recording costs about 15 CPU-seconds a day and 2.5 MB of disk a month on each Mac, with no tokens.')}
      </div></div>`;
  }

  /* ------------------------------------------------------------ events */
  function bind(el, tab) {
    el.onclick = e => {
      const t = e.target.closest('button,a');
      if (!t || !el.contains(t)) return;
      const ds = t.dataset;
      if (ds.fold != null) { S.open.has(ds.fold) ? S.open.delete(ds.fold) : S.open.add(ds.fold); return draw(); }
      if (ds.task != null) { openTask(ds.task); return; }  // draw() sets the arrows' list to the task lines on screen
      if (ds.term) { if (innerWidth < 900) { S.peek = ds.term; return draw(); } return CTX.inert(`${wnm(ds.term)}: its terminal opens in Orca`); }
      if (ds.peek != null) { S.peek = ds.peek; return draw(); }
      if (ds.termmac) { const w = mine(D).find(x => x.name === ds.termmac); S.peek = ''; draw();
        return CTX.inert(`Orca brought the terminal of ${wnm(ds.termmac)} forward on the ${(w && w.mac) || 'M1 Max'}`); }
      if (ds.ask != null) { S.ask = ds.ask; return draw(); }
      if (ds.rerun) { const p = ds.rerun; S.rerun.set(p, Date.now()); S.ask = ''; draw();
        return CTX.inert('Rerun started', () => { S.rerun.delete(p); draw(); }); }
      if (ds.unrerun) { S.rerun.delete(ds.unrerun); return draw(); }
      if (ds.copy) { navigator.clipboard && navigator.clipboard.writeText(ds.copy).catch(() => {}); t.innerHTML = ic('tick'); setTimeout(() => { t.innerHTML = ic('copy'); }, 2000); return CTX.toast('Copied'); }
      if (ds.tst) { const all = CTX.prefs.get('tst', {}), id = S.task, b = D.board.beads[id], prev = all[id];
        if (ds.tst === b.st) delete all[id]; else all[id] = ds.tst; CTX.prefs.set('tst', all); draw();
        return CTX.inert(`Status ${ds.tst === b.st ? 'back to ' + b.st : 'set to ' + ds.tst}: goes with your next Send`, () => { const a = CTX.prefs.get('tst', {}); if (prev) a[id] = prev; else delete a[id]; CTX.prefs.set('tst', a); draw(); }); }
      if (ds.untst) { const a = CTX.prefs.get('tst', {}); delete a[S.task]; CTX.prefs.set('tst', a); return draw(); }
      if (t.hasAttribute('data-untcm')) { const k = 'tcm:' + S.task, old = CTX.prefs.get(k, ''); CTX.prefs.set(k, ''); draw(); return CTX.toast('Comment removed', {undo: () => { CTX.prefs.set(k, old); draw(); }}); }
    };
    el.oninput = e => { if (!e.target.matches('[data-tcm]')) return;
      CTX.prefs.set('tcm:' + S.task, e.target.value);
      const say = el.querySelector('[data-tcmsay]'), rm = el.querySelector('[data-untcm]');
      if (say) say.textContent = e.target.value.trim() ? 'Saved as you type · goes to the board with your next Send' : 'Goes to the board with your next Send';
      if (rm) rm.hidden = !e.target.value.trim(); };
  }
  function openTask(id) { S.task = id; if (tabNow !== 'side') CTX.prefs.set('task', id); draw(); const ta = EL.querySelector('.tpanel .tpscroll'); if (ta) ta.scrollTop = 0; }
  // the same panel beside another tab (Questions' task links, audit4 questions 04); host carries .area-running for the panel's look
  P.taskPanel = async (host, ctx, id, list) => {
    CTX = CTX || ctx; D = D || own(await ctx.data('running'));
    if (!host.isConnected) return;
    EL = host; tabNow = 'side'; S.list = list; bind(host); openTask(id);
  };
  addEventListener('keydown', e => {
    if (e.key === 'Escape' && S.peek && EL && EL.isConnected) { S.peek = ''; return draw(); }
    if (!EL || !EL.isConnected || !EL.classList.contains('tab-running') || !S.task || e.target.closest('textarea,input')) return;
    const pos = S.list.indexOf(S.task);
    if (e.key === 'Escape') openTask('');
    else if ((e.key === 'j' || e.key === 'ArrowDown') && pos < S.list.length - 1) { e.preventDefault(); openTask(S.list[pos + 1]); }
    else if ((e.key === 'k' || e.key === 'ArrowUp') && pos > 0) { e.preventDefault(); openTask(S.list[pos - 1]); }
  });
  // one tooltip for every chart mark
  (() => { let el;
    const show = (html, x, y) => { if (!el) { el = document.createElement('div'); el.className = 'rn-vtip'; el.setAttribute('role', 'tooltip'); document.body.append(el); }
      el.innerHTML = html; el.hidden = false; const r = el.getBoundingClientRect();
      el.style.left = Math.max(4, Math.min(innerWidth - r.width - 4, x + 12)) + 'px'; el.style.top = (y - r.height - 12 < 4 ? y + 18 : y - r.height - 12) + 'px'; };
    const hide = () => el && (el.hidden = true);
    const body = t => { const [h, d] = t.dataset.tip.split('|'); return `<b>${esc(h)}</b><span>${esc(d)}</span>`; };
    const find = e => e.target.closest && e.target.closest('.area-running [data-tip]');
    // pointermove alone missed hovers that arrive as mouse events only (some automation, #145); a tap on touch shows it too
    const at = e => { const t = find(e); t ? show(body(t), e.clientX, e.clientY) : hide(); };
    ['pointermove', 'mouseover', 'pointerdown'].forEach(n => document.addEventListener(n, at));
    document.addEventListener('focusin', e => { const t = find(e); if (!t) return hide(); const r = t.getBoundingClientRect(); show(body(t), r.left + r.width / 2, r.top); });
    document.addEventListener('scroll', hide, true); })();

  let tabNow = 'running';
  function draw() {
    if (!EL || !D) return;
    const y = scrollY, ps = EL.querySelector('.tpanel .tpscroll'), py = ps ? ps.scrollTop : 0;
    EL.innerHTML = tabNow === 'side' ? panel() : tabNow === 'running' ? running() : analytics();
    // the task arrows step through the tasks shown on screen, not the folded groups (#144); one redraw when they differ
    if (tabNow === 'running' && S.task) {
      const l = [...new Set([...EL.querySelectorAll('[data-task]')].filter(x => !x.closest('.tpanel')).map(x => x.dataset.task).filter(x => x && ((D.board || {}).beads || {})[x]))];
      if (l.includes(S.task) && l.join() !== S.list.join()) { S.list = l; EL.innerHTML = running(); }
    }
    scrollTo(0, y);
    const ps2 = EL.querySelector('.tpanel .tpscroll'); if (ps2) ps2.scrollTop = py;
  }
  async function render(el, ctx, anchor, tab) {
    CTX = ctx; EL = el; tabNow = tab;
    if (!D) el.innerHTML = `<div class="p-empty">${P.icon('reload')}<p>Reading workers, the board and Windmill…</p></div>`;
    D = own(await ctx.data('running'));
    if (!el.classList.contains('tab-' + tab)) return;  // another tab opened while this one read its data: never draw over it
    tabNow = tab;
    if (tab === 'running') S.task = ctx.prefs.get('task', '');
    bind(el, tab);
    draw();
    if (anchor && tab === 'analytics') { const t = document.getElementById(anchor); if (t) t.scrollIntoView({block: 'start'}); }
  }
  matchMedia('(max-width: 699px)').addEventListener('change', () => { if (EL && EL.isConnected && tabNow === 'analytics') draw(); });

  /* ------------------------------------------------------------ the top-bar worker squares and their overview card (#131) */
  let BOPEN = false;
  async function bar(el, ctx) {
    const d = own(await ctx.data('running')), ws = mine(d).sort((x, y) => WORDER.indexOf(x.s) - WORDER.indexOf(y.s));
    const jobs = myJobs(d).filter(j => j.failing), c = ws.reduce((o, w) => (o[w.s] = (o[w.s] || 0) + 1, o), {});
    if (!ws.length && !jobs.length) { el.innerHTML = ''; return; }
    const sq = ws.slice(0, 24).map(w => `<i class="st-${WS[w.s][0]}${w.s === 'stuck' ? ' hatch' : ''}"></i>`).join('');
    const counts = WORDER.filter(s => c[s] && s !== 'done').map(s => `<span class="nw"><i class="dot st-${WS[s][0]}"></i>${c[s]}</span>`).join('');
    el.innerHTML = `<span class="rn-bar"><button class="rn-bbtn" aria-haspopup="dialog" aria-expanded="${BOPEN}" title="This project's workers and scheduled jobs">
        <span class="rn-sqs" aria-hidden="true">${sq}</span>${counts}<b class="nw">${pl(ws.length, 'worker', 'workers')}</b>${jobs.length ? `<span class="rn-jf nw">${jobs.slice(0, 3).map(() => ic('x')).join('')} ${pl(jobs.length, 'job', 'jobs')} failing</span>` : ''}</button>
      ${BOPEN ? `<div class="rn-bcard" role="dialog" aria-label="Workers overview">${overview(d, ws, jobs, c)}</div>` : ''}</span>`;
    el.querySelector('.rn-bbtn').onclick = e => { e.stopPropagation(); BOPEN = !BOPEN; bar(el, ctx); };
    const card = el.querySelector('.rn-bcard');
    if (card) card.onclick = e => { const g = e.target.closest('[data-bgo]'); if (g) { BOPEN = false; bar(el, ctx); ctx.go('running', 'workers'); } e.stopPropagation(); };
    BAR = () => bar(el, ctx);
  }
  let BAR = null;
  document.addEventListener('click', () => { if (BOPEN && BAR) { BOPEN = false; BAR(); } });
  addEventListener('keydown', e => { if (e.key === 'Escape' && BOPEN && BAR) { BOPEN = false; BAR(); } });
  function overview(d, ws, jobs, c) {
    const macs = ['M1 Max', 'M5 Max', 'M1 Max 16'].map(m => [m, ws.filter(w => w.mac === m)]).filter(([, l]) => l.length), mx = Math.max(1, ...macs.map(([, l]) => l.length));
    const H = Array.isArray(d.hours) ? d.hours : [], hm = Math.max(1, ...H);
    const look = ws.filter(w => w.s === 'stuck' || w.s === 'failed');
    return `<div class="rn-bh"><b>${pl(ws.length, 'worker', 'workers')}</b> <span class="small mut">on ${pl(macs.length, 'Mac', 'Macs')}</span></div>
      <div class="small rn-bst">${WORDER.filter(s => c[s]).map(s => `<span class="nw"><i class="dot st-${WS[s][0]}"></i> ${c[s]} ${WS[s][1]}</span>`).join('')}</div>
      ${H.length ? `<div class="rn-bk">Workers at once, last 24 hours</div><div class="rn-hrs" role="img" aria-label="Most at once in the last 24 hours: ${Math.max(0, ...H)}">${H.map((n, i) => `<i style="height:${Math.max(2, n / hm * 100)}%" title="${24 - i} h ago: ${pl(n, 'worker', 'workers')}"></i>`).join('')}</div>
        <div class="small mut rn-hax"><span>24 h ago</span><span>now · most at once: ${pl(Math.max(0, ...H), 'worker', 'workers')}</span></div>` : ''}
      ${macs.length ? `<div class="rn-bk">By Mac</div>${macs.map(([m, l]) => { const k = l.reduce((o, w) => (o[w.s] = (o[w.s] || 0) + 1, o), {});
        return `<div class="rn-bm"><span>${esc(m)}</span><span class="rn-bmt" style="width:${l.length / mx * 100}%">${WORDER.filter(s => k[s]).map(s => `<i class="st-${WS[s][0]}" style="flex:${k[s]}" title="${k[s]} ${WS[s][1]}"></i>`).join('')}</span><b>${l.length}</b></div>`; }).join('')}` : ''}
      ${look.length ? `<div class="rn-bk">Needs a look first</div>${look.slice(0, 6).map(w => `<button class="rn-bw" data-bgo><i class="dot st-${WS[w.s][0]}"></i><span class="rn-bwn"><b>${esc(wnm(w.name))}</b><span class="small"><span class="${w.s === 'stuck' ? 'stuck-t' : 'err-t'}">${w.s === 'stuck' ? `no sign of life for ${ago(w.heard)}` : 'failed'}</span> · ${esc(scrub(w.report) || 'no report yet')}</span></span><span class="mb ${esc(w.agent)}">${esc(mdl(w))}</span><span class="small nw">${ago(w.mins)}</span></button>`).join('')}` : ''}
      ${jobs.length ? `<div class="rn-bk">Scheduled jobs failing</div>${jobs.map(j => `<div class="rn-bj">${ic('x')}<b>${esc(j.name)}</b></div>`).join('')}` : ''}
      <button class="lk small rn-bmore" data-bgo>${ws.length - Math.min(6, look.length) > 0 ? `${pl(ws.length - Math.min(6, look.length), 'more worker', 'more workers')} under Running · ` : ''}open Running</button>`;
  }
  P.bar({render: bar});

  // status changes and task comments "go with your next Send": the one Send lists them under Tasks (r12 fix6, running 1)
  // the side panel's host (Questions) has no tab class: redraw it too, so Undo shows the comment in the open panel
  const redraw = () => { if (EL && EL.isConnected && (tabNow === 'side' || EL.classList.contains('tab-' + tabNow))) draw(); };
  P.queue && P.queue({
    items: ctx => {
      if (!D) { ctx.data('running').then(d => { if (!D) { D = own(d); ctx.refreshTop(); } }).catch(() => {}); return []; }
      const B = (D.board || {}).beads || {}, tst = ctx.prefs.get('tst', {}), out = [];
      const ttl = id => `${esc(cut(tclean((B[id] || {}).t || id), 60))} <span class="bid">${esc(id)}</span>`;
      // from Running itself the hash is already #running, so no hashchange redraws: open the task here (r12 fix8, running 1)
      const go = id => () => { ctx.prefs.set('task', id); if (location.hash === '#running' && tabNow === 'running' && EL && EL.isConnected) openTask(id); else ctx.go('running'); };
      for (const [id, st] of Object.entries(tst)) out.push({key: 'tst:' + id, group: 'Tasks', html: `${ttl(id)} → <b>${esc(st)}</b>`, go: go(id),
        remove: () => { const a = ctx.prefs.get('tst', {}); delete a[id]; ctx.prefs.set('tst', a); redraw(); return () => { ctx.prefs.set('tst', {...ctx.prefs.get('tst', {}), [id]: st}); redraw(); }; }});
      for (const id of Object.keys(B)) { const k = 'tcm:' + id, c = ctx.prefs.get(k, '');
        if (c.trim()) out.push({key: k, group: 'Tasks', html: `${ttl(id)} → comment: “${esc(cut(c, 120))}”`, go: go(id), remove: () => { ctx.prefs.set(k, ''); redraw(); return () => { ctx.prefs.set(k, c); redraw(); }; }}); }
      return out;
    },
    sent: ctx => { ctx.prefs.set('tst', {}); Object.keys(((D || {}).board || {}).beads || {}).forEach(id => ctx.prefs.set('tcm:' + id, '')); redraw(); },
  });
  P.tab({key: 'running', chip: async ctx => urgent(own(await ctx.data('running'))), render: (el, ctx, a) => render(el, ctx, a, 'running')});
  P.tab({key: 'analytics', render: (el, ctx, a) => render(el, ctx, a, 'analytics')});
  P._running = {urgent, mine, wnm, mdl};  // for tests
})();
