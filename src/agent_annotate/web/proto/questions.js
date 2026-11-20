/* Prototype Questions tab: the review document, whole, with each question's card at its evidence; and Cards only.
   Picks, words and replies are drafts in this browser until Send; Send posts them through today's endpoints
   (decision, reply, rounds/submit) after a short Undo window. Notes, Later and Close save at once and undo
   through today's calls (DELETE, answer-later off, restore). The sandboxed server delivers nothing. */
(function () {
  'use strict';
  const P = window.Proto;
  const SEND_DELAY = 6000;
  const S = {open: new Set(), shut: new Set(), view: null, filter: 'need', armed: false, pending: null, note: null, copied: null};
  let D = null, ctx = null, root = null, DOC = null;

  /* ---------- helpers ---------- */
  const esc = s => P.ctx.esc(s);
  const ic = (k, l) => P.icon(k, l);
  const cut = (s, n) => (s = String(s || '')).length <= n ? s : s.slice(0, n).replace(/[\s,:;]+\S*$/, '') + '…';
  const pl = (n, one, many) => `${n} ${n === 1 ? one : many}`;
  const drafts = () => ctx.prefs.get('q:drafts', {});
  const draft = id => drafts()[id] || {};
  function setDraft(id, patch) {
    const all = drafts(), d = Object.assign({}, all[id], patch);
    for (const k of Object.keys(d)) if (d[k] === '' || d[k] == null || d[k] === false) delete d[k];
    if (Object.keys(d).length) all[id] = d; else delete all[id];
    ctx.prefs.set('q:drafts', all);
  }
  async function who() {
    if (who.q != null) return who.q;
    try { const i = await ctx.api.identity(); who.q = i && i.email ? '?author=' + encodeURIComponent(i.name && i.name !== i.email ? `${i.name} <${i.email}>` : i.email) : ''; } catch { who.q = ''; }
    return who.q;
  }
  const call = async (path, body, method) => ctx.api(path + await who(), body, method);
  const ibw = (k, word, label, attrs) => `<button class="ib ibw" title="${esc(label)}" aria-label="${esc(label)}" ${attrs}>${ic(k)}<span class="ibt">${word}</span></button>`;
  const ib = (k, label, attrs) => `<button class="ib sm" title="${esc(label)}" aria-label="${esc(label)}" ${attrs}>${ic(k)}</button>`;

  /* ---------- state of a question ---------- */
  const optLabel = (q, id) => (q.options.find(o => o.id === id) || {}).label || id;
  const isDraft = q => { const d = draft(q.id); return !!(d.pick || (d.words || '').trim()); };
  const isDone = q => q.closed || q.sent || q.later || isDraft(q);
  const isWaiting = q => !isDone(q);
  const cardOpen = q => isDone(q) ? S.open.has(q.id) : !S.shut.has(q.id);
  const waitingCount = () => (D ? D.questions.filter(isWaiting).length : 0);
  const toSend = () => D ? D.questions.filter(q => !q.closed && (isDraft(q) || (draft(q.id).reply || '').trim())).length : 0;

  function stateOf(q) {
    const d = draft(q.id), w = (d.words || '').trim();
    if (d.pick) return `<span class="saved">${ic('tick')} ${esc(cut(optLabel(q, d.pick), 40))}${w ? ' + your words' : ''} · goes with Send</span><button class="lk small" data-undo="${q.id}">Undo</button>`;
    if (w) return `<span class="saved">${ic('tick')} Answered in words · goes with Send</span><button class="lk small" data-undo="${q.id}">Undo</button>`;
    if (q.closed) return `<span class="saved">${ic('archive')} Closed: no answer needed</span><button class="lk small" data-reopen="${q.id}">Undo</button>`;
    if (q.sent) return `<span class="saved">${ic('send')} Sent ${esc(fmt(q.decision.ts))}</span>${q.read ? `<span class="qread">${ic('eye')} read by the agent</span>` : '<span class="small mut">not read yet</span>'}`;
    if (q.later) return `<span class="small mut">${ic('later')} Set aside</span><button class="lk small" data-unlater="${q.id}">Back to waiting</button>`;
    return '';
  }
  const fmt = ts => { if (!ts) return ''; const t = new Date(ts); return isNaN(t) ? '' : t.toLocaleString([], {month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'}); };
  const IMPW = {high: 'High impact', medium: 'Medium impact', low: 'Low impact'};
  const impMark = q => IMPW[q.impact] ? `<span class="impw ${q.impact}" title="${IMPW[q.impact]}: how much the agent says this answer changes"><span class="imp ${q.impact}" aria-hidden="true"><i></i><i></i><i></i></span>${q.impact === 'medium' ? 'Med' : q.impact[0].toUpperCase() + q.impact.slice(1)}</span>` : '<span class="impw none" aria-hidden="true"></span>';
  const blkMark = q => q.blocking ? `<span class="blkp" title="A task on the board waits on this answer">${ic('block')}Blocks a task</span>` : '';
  const numChip = q => `<span class="qnum">Q ${esc(q.n)}</span>`;

  function taskChip(id) {
    const b = (D.beads || {})[id];
    return `<button class="qtask" data-task="${esc(id)}" title="Open this task in Running"><span class="dot st-${b ? b.state : 'none'}"></span>${b ? `<span>${esc(cut(b.title, 60))}</span>` : ''}<span class="bid">· ${esc(id)}</span>${b ? `<span class="mut">· ${esc(b.status.replace('_', ' '))}</span>` : ''}</button>`;
  }
  // a card's task: one the question names, else the first on the board that its evidence names
  function beadOf(q) {
    if (q.bead) return q.bead;
    for (const ev of q.evidence || []) {
      const el = DOC && DOC.querySelector(`[data-anchor-id="${CSS.escape(ev.anchor)}"]`);
      const m = el && (el.textContent.match(/\bFLD-[a-z0-9]+(?:\.\d+)*\b/g) || []).find(x => (D.beads || {})[x]);
      if (m) return m;
    }
    return null;
  }

  /* ---------- the card ---------- */
  function card(q, inList) {
    const d = draft(q.id), open = inList ? true : cardOpen(q);
    const cls = `qcard${d.pick || (d.words || '').trim() ? ' answered' : q.sent ? ' sent' : q.closed ? ' closed' : q.later ? ' later' : ''}`;
    const marks = `<span class="qmarks">${blkMark(q)}${impMark(q)}</span>`;
    if (!open) return `<div class="${cls} folded" id="q-${q.id}" data-q="${q.id}"><div class="qhead"><button class="qfold" data-fold="${q.id}" aria-expanded="false" title="Open this card">${numChip(q)}<span class="qt">${esc(q.prompt)}</span></button><span class="qstate">${stateOf(q)}</span>${marks}</div></div>`;
    const done = isDone(q), rp = d.replyOpen || (d.reply || '').trim();
    const acts = `${done ? '' : ibw('later', 'Later', 'Answer later: set it aside; it comes back under Answer later', `data-later="${q.id}"`)}${ibw('reply', 'Reply', 'Reply to the agent without answering', `data-reply="${q.id}" aria-pressed="${!!rp}"`)}${S.copied === q.id ? ibw('copied', 'Copied', 'Link copied', `data-link="${q.id}"`) : ibw('link', 'Link', 'Copy a link to this question', `data-link="${q.id}"`)}${q.closed || q.sent ? '' : ibw('archive', 'Close', 'Close without an answer: no answer needed. Undo puts it back', `data-close="${q.id}"`)}`;
    const title = done && !inList ? `<button class="qfold" data-fold="${q.id}" aria-expanded="true" title="Fold this card">${numChip(q)}<span class="qt">${esc(q.prompt)}</span></button>` : `<span class="qfold static">${numChip(q)}<span class="qt">${esc(q.prompt)}</span></span>`;
    const head = `<div class="qhead">${title}<span class="qstate">${stateOf(q)}</span><span class="eacts">${acts}</span>${marks}</div>`;
    const cx = q.context ? `<div class="qctx">${q.context.split('\n').map(p => `<p>${beadText(esc(p))}</p>`).join('')}</div>` : '';
    const th = q.replies.filter(r => !/^(☑ Selected|💬 Answer in words|↻|✓|✗|↺)/.test(r.text)), tOpen = S.open.has('th' + q.id);
    const typing = (d.reply || '').trim() ? `<li class="you"><span class="who">You · goes with Send</span> ${esc(d.reply)}</li>` : '';
    const thread = th.length || typing ? `<div class="small"><b>Thread with the agent</b>${th.length > 2 ? ` · <button class="lk small" data-fold="th${q.id}" aria-expanded="${tOpen}">${tOpen ? 'Hide earlier replies' : pl(th.length - 2, 'earlier reply', 'earlier replies')}</button>` : ''}</div><ul class="qthread">${(tOpen ? th : th.slice(-2)).map(r => `<li class="${r.you ? 'you' : 'agent'}"><span class="who">${r.you ? 'You' : 'Agent'} · ${esc(fmt(r.ts))}${r.you && !r.sent ? ' · not sent' : ''}</span> ${esc(r.text)}</li>`).join('')}${typing}</ul>` : '';
    const bead = beadOf(q), hso = S.open.has('hs' + q.id);
    const ask = d.askfile ? `<span class="saved">${ic('tick')} Asked the agent to file one</span> ${P.inertMark()} <button class="lk small" data-askfile="${q.id}">Undo</button>`
      : `<button class="lk small" data-askfile="${q.id}" title="Ask the agent to file a task for this question">Ask the agent to file one</button> ${P.inertMark()}`;
    const meta = `<div class="qmeta">${bead ? `<span>${ic('task')} ${taskChip(bead)}</span>` : `<span>${ic('task')} No task on the board yet · ${ask}</span>`}${q.earlier.length ? `<button class="dfold" data-fold="hs${q.id}" aria-expanded="${hso}" title="Your earlier answers on the same question">${ic('hist')} Decided before · ${q.earlier.length}</button>` : ''}${q.evidence.length && !inList ? `<button class="lk small" data-ev="${esc(q.evidence[0].anchor)}">${ic('place')} ${esc(cut(q.evidence[0].label || 'Its evidence', 40))}</button>` : ''}</div>${hso ? `<ul class="qhist">${q.earlier.map(h => `<li><span class="mut">${esc(h.t)} · version ${esc(String(h.v).slice(1))}</span> — ${esc(h.q)} → <b>${esc(h.a)}</b></li>`).join('')}</ul>` : ''}`;
    const norec = !q.rec ? `<p class="small mut">The agent gave no recommendation${q.options.length ? '' : ' and no choices'}.</p>` : '';
    const an = `${norec}<div class="qopts">${q.options.map((o, i) => `<button class="qopt${o.id === q.rec ? ' rec' : ''}" data-pick="${q.id}" data-opt="${esc(o.id)}" aria-pressed="${d.pick === o.id}">${o.id === q.rec ? '<span class="rl">Recommended</span>' : ''}<b>${i + 1}. ${esc(o.label)}</b>${o.c ? `<span>${esc(o.c)}</span>` : ''}</button>`).join('')}</div>
      <textarea class="qwords" data-words="${q.id}" aria-label="Answer in words" placeholder="${q.options.length ? 'Answer in words. With no choice picked, this is your answer; with one, it goes with it.' : 'Your answer: there are no choices'}">${esc(d.words || '')}</textarea>
      <p class="hint">Saved as you type · <kbd>⌘↵</kbd> twice sends</p>
      ${rp ? `<label class="small"><b>Reply to the agent</b></label><textarea class="qwords" data-replytext="${q.id}" placeholder="Ask or tell the agent something about this question">${esc(d.reply || '')}</textarea><p class="hint">Saved as you type; goes with your next Send. <button class="lk small" data-unreply="${q.id}">Remove</button></p>` : ''}`;
    const body = `<div class="qbody"><div class="qcx">${cx}${thread}${meta}</div><div class="qan">${an}</div></div>`;
    return `<div class="${cls}" id="q-${q.id}" data-q="${q.id}">${head}${body}</div>`;
  }
  // tasks the agent names: title · bead id · state
  const beadText = h => h.replace(/\bFLD-[a-z0-9]+(?:\.\d+)*\b/g, m => (D.beads || {})[m] ? taskChip(m) : m);

  /* ---------- the document ---------- */
  async function loadDoc(v) {
    if (loadDoc.v === v && loadDoc.html) return loadDoc.html;
    const r = await fetch(ctx.base + 'content?v=' + encodeURIComponent(v), {cache: 'no-store'});
    if (!r.ok) throw new Error('the document did not load (HTTP ' + r.status + ')');
    const doc = new DOMParser().parseFromString(await r.text(), 'text/html');
    for (const l of doc.querySelectorAll('link[rel=stylesheet][href*="content.css"]'))
      if (!document.querySelector(`link[data-qdoc]`)) document.head.appendChild(Object.assign(document.createElement('link'), {rel: 'stylesheet', href: l.getAttribute('href')})).dataset.qdoc = '1';
    doc.querySelectorAll('script,style').forEach(n => n.remove());
    const aa = doc.querySelector('.aa') || doc.body;
    // personal addresses never show on the prototype; the company's own stay readable (same rule as proto_data/questions.py)
    loadDoc.v = v; loadDoc.html = aa.innerHTML.replace(/[\w.+-]+@(?!fastlanedrive\.com\b)[a-z][\w-]*(?:\.[\w-]+)*\.[a-z]{2,}\b/gi, 'member@example.com');
    return loadDoc.html;
  }
  function wrapTasks(rootEl) {  // FLD-xxx in the document's text becomes a task line
    const w = document.createTreeWalker(rootEl, NodeFilter.SHOW_TEXT), hits = [];
    for (let n; (n = w.nextNode());) if (/\bFLD-[a-z0-9]/.test(n.nodeValue) && !n.parentElement.closest('.qcard,a,button,code,pre')) hits.push(n);
    for (const n of hits) {
      const html = beadText(esc(n.nodeValue));
      if (html === esc(n.nodeValue)) continue;
      const span = document.createElement('span'); span.innerHTML = html; n.replaceWith(span);
    }
  }
  function placeCards(docEl, top) {
    const unplaced = [];
    for (const q of D.questions) {
      if (document.getElementById('q-' + q.id) && root.contains(document.getElementById('q-' + q.id))) continue;
      const html = card(q);
      const ph = docEl.querySelector(`.card[data-anchor-id="${CSS.escape(q.anchor)}"]`);
      const ev = !ph && top && q.evidence[0] && docEl.querySelector(`[data-anchor-id="${CSS.escape(q.evidence[0].anchor)}"]`);
      if (ph) ph.outerHTML = html;
      else if (ev) ev.insertAdjacentHTML(ev.tagName === 'SECTION' ? 'beforeend' : 'afterend', html);
      else if (top) unplaced.push(html);
    }
    if (unplaced.length) docEl.insertAdjacentHTML('afterbegin', `<section class="qunplaced"><h2>Questions with no place in this version</h2>${unplaced.join('')}</section>`);
  }
  function inflate(d) {  // "Earlier updates" carry their sections in a <template> until opened, as on today's page
    const tpl = d.querySelector(':scope > template');
    if (tpl) { tpl.replaceWith(tpl.content.cloneNode(true)); placeCards(d); placeNotes(d); wrapTasks(d); }
  }
  function placeNotes(docEl) {
    D.notes.forEach((n, i) => {
      const el = docEl.querySelector(`[data-anchor-id="${CSS.escape(n.anchor)}"]`);
      if (!el) return;
      const t = n.target || {};
      if (t.tag === 'img' && t.offset) {
        const img = el.tagName === 'IMG' ? el : el.querySelector('img');
        if (img) pinOn(img, i + 1, t.offset);
      } else if (t.quote) markQuote(el, t.quote);
      const after = el.tagName === 'TR' ? el.closest('table').closest('.wrap') || el.closest('table') : el.tagName === 'LI' ? el : el;
      after.insertAdjacentHTML(el.tagName === 'SECTION' ? 'beforeend' : 'afterend', noteBox(n, i + 1));
    });
  }
  function pinOn(img, no, off) {
    let wrap = img.parentElement.classList.contains('qpinwrap') ? img.parentElement : null;
    if (!wrap) { wrap = document.createElement('span'); wrap.className = 'qpinwrap'; img.replaceWith(wrap); wrap.appendChild(img); }
    wrap.insertAdjacentHTML('beforeend', `<span class="qpin" style="left:${off.dx * 100}%;top:${off.dy * 100}%">${no}</span>`);
  }
  function markQuote(el, quote) {
    const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let n; (n = w.nextNode());) {
      const i = n.nodeValue.indexOf(quote);
      if (i < 0) continue;
      const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + quote.length);
      r.surroundContents(document.createElement('mark')); return;
    }
  }
  const mk = (no, sent) => `<span class="qmk${sent ? ' sent' : ''}" title="Your note ${no}${sent ? ', sent' : ''}">${ic('note')}${no}</span>`;
  function noteBox(n, no) {
    const t = n.target || {}, what = t.quote ? `on “${esc(cut(t.quote, 50))}”` : t.tag === 'img' ? 'at this spot' : 'on this line';
    if (S.note && S.note.edit === n.id) return `<div class="qnote" data-note="${n.id}">${mk(no)}<b>Note ${no} ${what}</b><textarea data-notetext aria-label="Note ${no}">${esc(n.text)}</textarea><div class="acts"><button class="btn sm pri" data-nsave="${n.id}">Save</button><button class="lk small" data-ncancel>Cancel</button><span class="small mut"><kbd>⌘↵</kbd> saves</span></div></div>`;
    const acts = n.sent ? ib('copy', 'Copy the note text', `data-ncopy="${n.id}"`)
      : ib('edit', 'Edit this note', `data-nedit="${n.id}"`) + ib('undo', 'Undo: remove this note', `data-ndel="${n.id}"`) + ib('copy', 'Copy the note text', `data-ncopy="${n.id}"`) + ib('link', 'Copy a link to this note', `data-nlink="${n.id}"`);
    return `<div class="qnote${n.sent ? ' sent' : ''}" id="n-${n.id}" data-note="${n.id}">${mk(no, n.sent)}<b>Note ${no} ${what}:</b> ${esc(n.text)} <span class="${n.sent ? 'mut' : 'saved'}">· ${n.sent ? 'sent' : 'goes with Send'}</span><span class="nacts">${acts}</span></div>`;
  }
  function newNoteBox() {
    const n = S.note, what = n.target.quote ? `on “${esc(cut(n.target.quote, 50))}”` : n.target.tag === 'img' ? 'at this spot' : 'on this line';
    return `<div class="qnote new" data-newnote>${mk('+')}<b>New note ${what}</b> <span class="mut small">· goes with your next Send</span><textarea data-notetext aria-label="Your note" placeholder="Type your note"></textarea><div class="acts"><button class="btn sm pri" data-nadd>Save</button><button class="lk small" data-ncancel>Cancel</button><span class="small mut"><kbd>⌘↵</kbd> saves · an empty note is dropped</span></div></div>`;
  }

  /* ---------- the bar ---------- */
  const FILTERS = {need: isWaiting, later: q => q.later && !q.closed && !isDraft(q) && !q.sent, ready: q => isDraft(q) || !!(draft(q.id).reply || '').trim(), wait: q => q.sent, arch: q => q.closed};
  function bar() {
    const cnt = k => D.questions.filter(FILTERS[k]).length, lv = S.view === 'list';
    const decided = D.questions.filter(q => !isWaiting(q) && !q.later).length, all = D.questions.length;
    const chips = [['need', `Waiting ${cnt('need')}`], ['later', `<span class="hide-ph">Answer later</span><span class="ph-only">Later</span> ${cnt('later')}`], ['ready', `To send ${cnt('ready')}`], ['wait', `Sent ${cnt('wait')}`], ['arch', `Closed ${cnt('arch')}`]];
    const vsw = `<span class="qseg" role="group" aria-label="View">${[['doc', 'doc', 'Document', 'The review document, each card at its evidence'], ['list', 'list', 'Cards only', 'Only the cards, open; each folds once answered']].map(([v, k, t, tip]) => `<button data-view="${v}" aria-pressed="${S.view === v}" title="${tip}">${ic(k)}<span class="hide-ph">${t}</span></button>`).join('')}</span>`;
    const n = toSend() + D.notes.filter(x => !x.sent).length + (ctx.prefs.get('q:general', '').trim() ? 1 : 0);
    return `<div class="qbar">${vsw}<span class="qchips">${chips.map(([k, t]) => `<button class="chipb" data-filter="${k}" aria-pressed="${lv && S.filter === k}"${lv ? '' : ' title="Show these in Cards only"'}>${t}</button>`).join('')}</span>
      <span class="prog" title="${decided} of ${all} questions decided">${decided} of ${all}<span class="hide-ph"> decided</span><i><b style="width:${all ? Math.round(decided / all * 100) : 0}%"></b></i></span>
      <span class="spacer"></span>${lv ? `<span class="qseg" role="group" aria-label="Open or fold the cards">${ib('expand', 'Expand all: open every card', 'data-all="expand"')}${ib('collapse', 'Collapse all: fold every card to its line', 'data-all="collapse"')}${ib('colans', 'Collapse answered: fold the cards you answered, closed or set aside', 'data-all="answered"')}</span>` : ''}
      <button class="btn sm${n ? ' pri' : ''}" data-sendopen ${n ? '' : 'disabled'} title="Send your answers and notes · ⌘↵ twice">${ic('send')} Send${n ? ' ' + n : ''}</button></div>${sendPanel(n)}`;
  }
  function sendPanel(n) {
    if (S.pending) return `<div class="qsend sending" role="status">${ic('send')} Sending ${pl(S.pending.n, 'item', 'items')}… <button class="lk" data-sendundo>Undo</button> ${P.inertMark()}</div>`;
    if (!S.armed) return '';
    const answers = D.questions.filter(isDraft), replies = D.questions.filter(q => (draft(q.id).reply || '').trim()), notes = D.notes.filter(x => !x.sent);
    return `<div class="qsend" role="dialog" aria-label="Send"><b>Send to the agent</b><ul class="small">${answers.length ? `<li>${pl(answers.length, 'answer', 'answers')}</li>` : ''}${replies.length ? `<li>${pl(replies.length, 'reply', 'replies')}</li>` : ''}${notes.length ? `<li>${pl(notes.length, 'note', 'notes')}</li>` : ''}</ul>
      <label class="small"><b>General feedback</b> <span class="mut">(optional)</span></label><textarea class="qwords" data-general placeholder="Anything about the page as a whole">${esc(ctx.prefs.get('q:general', ''))}</textarea>
      <div class="acts"><button class="btn pri" data-send ${n ? '' : 'disabled'}>${ic('send')} Send</button><button class="lk" data-sendclose>Not yet</button><span class="small mut"><kbd>⌘↵</kbd> again sends</span>${P.inertMark()}</div></div>`;
  }

  /* ---------- draw ---------- */
  async function draw(keepScroll) {
    const y = scrollY;
    const html = S.view === 'list' ? listView() : null;
    if (html != null) { root.innerHTML = bar() + html; }
    else {
      root.innerHTML = bar() + `<div class="aa qdoc"></div>`;
      const docEl = root.querySelector('.qdoc');
      docEl.innerHTML = await loadDoc(D.version);
      DOC = docEl;
      placeCards(docEl, true); placeNotes(docEl); wrapTasks(docEl);
      docEl.querySelectorAll('details.aa-earlier').forEach(d => { if (S.open.has('earlier')) { d.open = true; inflate(d); } });
      if (S.note) {
        const el = docEl.querySelector(`[data-anchor-id="${CSS.escape(S.note.anchor)}"]:not(.qcard)`);
        const after = el && (el.tagName === 'TR' ? el.closest('.wrap') || el.closest('table') : el);
        if (after) after.insertAdjacentHTML(el.tagName === 'SECTION' ? 'beforeend' : 'afterend', newNoteBox());
      }
    }
    if (keepScroll) scrollTo(0, y);
    ctx.refreshChips();
  }
  function listView() {
    const list = D.questions.filter(FILTERS[S.filter] || FILTERS.need);
    if (!DOC) loadDoc(D.version).then(h => { DOC = document.createElement('div'); DOC.innerHTML = h; if (S.view === 'list') draw(true); });
    return `<div class="qlist">${list.length ? list.map(q => {
      const open = cardOpen(q);
      if (!open) return card(q);
      return `<div class="qitem">${card(q).replace('<div class="qbody">', `<div class="qbody">${evidence(q)}`)}</div>`;
    }).join('') : `<p class="mut">${S.filter === 'wait' ? 'Nothing sent from this version yet.' : 'Nothing here.'}</p>`}</div>`;
  }
  // a card's evidence, copied from the document into Cards only: the line, row or section it points at
  function evidence(q) {
    const ev = q.evidence[0], el = ev && DOC && DOC.querySelector(`[data-anchor-id="${CSS.escape(ev.anchor)}"]`);
    if (!el) return '';
    let h;
    if (el.tagName === 'SECTION') h = [...el.children].filter(c => !c.matches('.cards,section')).slice(0, 2).map(c => c.outerHTML).join('');
    else h = el.tagName === 'TR' ? `<table>${el.outerHTML}</table>` : el.outerHTML;
    return `<div class="qev"><div class="small mut">${ic('place')} Its evidence in the document: <button class="lk small" data-indoc="${q.id}">${esc(cut(ev.label || 'open in the document', 50))}</button></div><div class="aa qevb">${h}</div></div>`;
  }

  /* ---------- actions ---------- */
  const qOf = id => D.questions.find(q => q.id === id);
  async function refresh() { D = await ctx.data('questions', true); await draw(true); }
  function pick(q, opt) {
    const was = draft(q.id).pick;
    setDraft(q.id, {pick: was === opt ? null : opt});
    draw(true);
  }
  async function later(q, on) {
    await call(`api/comments/${encodeURIComponent(q.id)}/answer-later`, {on});
    q.later = on; draw(true);
    if (on) ctx.toast('Set aside for later', {undo: () => later(q, false)});
  }
  async function close(q) {
    await call(`api/comments/${encodeURIComponent(q.id)}/archive`, {});
    q.closed = true; draw(true);
    ctx.toast('Closed: no answer needed', {undo: () => reopen(q)});
  }
  async function reopen(q) { await call(`api/comments/${encodeURIComponent(q.id)}/restore`, {}); q.closed = false; S.open.delete(q.id); draw(true); }
  function undo(q) {
    const keep = draft(q.id);
    setDraft(q.id, {pick: null, words: null}); S.open.delete(q.id); draw(true);
    ctx.toast('Answer removed', {undo: () => { setDraft(q.id, {pick: keep.pick, words: keep.words}); draw(true); }});
  }
  async function addNote(text) {
    const n = S.note; S.note = null;
    if (!text.trim()) return draw(true);
    const c = await call('api/comments', {anchor_id: n.anchor, anchor_label: n.label, text, version: D.version, target: n.target});
    await refresh();
    ctx.toast('Note saved · goes with Send', {undo: () => delNote(c.id, true)});
  }
  async function delNote(id, quiet) {
    const n = D.notes.find(x => x.id === id);
    await call(`api/comments/${encodeURIComponent(id)}`, undefined, 'DELETE');
    await refresh();
    if (!quiet && n) ctx.toast('Note removed', {undo: async () => { await call('api/comments', {anchor_id: n.anchor, anchor_label: n.label, text: n.text, version: D.version, target: n.target}); refresh(); }});
  }
  async function copy(text, what) {
    try { await navigator.clipboard.writeText(text); ctx.toast(what + ' copied'); } catch { ctx.toast('Copy failed: your browser blocked it'); }
  }

  /* Send: ⌘↵ once opens the summary, again sends. The posts wait SEND_DELAY ms, with Undo, then go through today's endpoints. */
  function arm() {
    if (S.pending) return;
    if (!S.armed) { S.armed = true; draw(true).then(() => { const t = root.querySelector('[data-send]'); if (t) t.focus(); }); return; }
    send();
  }
  function send() {
    const answers = D.questions.filter(q => isDraft(q) && !q.closed), replies = D.questions.filter(q => (draft(q.id).reply || '').trim() && !q.closed);
    const n = answers.length + replies.length + D.notes.filter(x => !x.sent).length + (ctx.prefs.get('q:general', '').trim() ? 1 : 0);
    if (!n) { S.armed = false; return draw(true); }
    S.armed = false;
    S.pending = {n, timer: setTimeout(() => post(answers, replies), SEND_DELAY)};
    draw(true);
  }
  async function post(answers, replies) {
    try {
      for (const q of answers) {
        const d = draft(q.id), w = (d.words || '').trim();
        const body = d.pick ? {verdict: 'select', text: optLabel(q, d.pick) + (w ? '\n\n' + w : ''), option_id: d.pick, defer_push: true} : {verdict: 'comment', text: w, defer_push: true};
        await call(`api/comments/${encodeURIComponent(q.id)}/decision`, body);
        setDraft(q.id, {pick: null, words: null});
      }
      for (const q of replies) { await call(`api/comments/${encodeURIComponent(q.id)}/reply`, {text: draft(q.id).reply.trim()}); setDraft(q.id, {reply: null, replyOpen: null}); }
      await call('api/rounds/submit', {note: ctx.prefs.get('q:general', '').trim() || undefined, version: D.version});
      ctx.prefs.set('q:general', '');
      S.pending = null;
      await refresh();
      ctx.toast(`Sent ${pl(answers.length, 'answer', 'answers')}: saved as a round in this copy`, {inert: true});
    } catch (e) {
      S.pending = null; await refresh();
      ctx.toast('Send failed: ' + e.message + '. Your drafts are kept.');
    }
  }

  function onClick(e) {
    const t = e.target.closest('button,a,[data-anchor-id],img');
    if (!t || !root.contains(t)) return;
    const ds = t.dataset, q = id => qOf(id);
    if (t.tagName === 'A') {  // links inside the document: "#d:q38833" jumps to the card, never to another tab
      const h = t.getAttribute('href') || '';
      if (h.startsWith('#')) { e.preventDefault(); const id = decodeURIComponent(h.slice(1)), qq = D.questions.find(x => x.anchor === id); const el = qq ? document.getElementById('q-' + qq.id) : root.querySelector(`[data-anchor-id="${CSS.escape(id)}"]`); if (qq) { S.shut.delete(qq.id); if (isDone(qq)) S.open.add(qq.id); } if (el) el.scrollIntoView({block: 'start', behavior: 'smooth'}); }
      return;
    }
    if (ds.view) { S.view = ds.view; ctx.prefs.set('q:view', S.view); return draw(); }
    if (ds.filter) { S.filter = ds.filter; S.view = 'list'; ctx.prefs.set('q:view', 'list'); return draw(); }
    if (ds.all) { for (const x of D.questions) { if (ds.all === 'expand') { S.shut.delete(x.id); if (isDone(x)) S.open.add(x.id); } else if (ds.all === 'collapse') { S.shut.add(x.id); S.open.delete(x.id); } else if (isDone(x)) S.open.delete(x.id); } return draw(true); }
    if (ds.fold) { const k = ds.fold, x = q(k); if (x) { const open = cardOpen(x); if (isDone(x)) open ? S.open.delete(k) : S.open.add(k); else open ? S.shut.add(k) : S.shut.delete(k); } else S.open.has(k) ? S.open.delete(k) : S.open.add(k); return draw(true); }
    if (ds.pick) return pick(q(ds.pick), ds.opt);
    if (ds.undo) return undo(q(ds.undo));
    if (ds.later) return later(q(ds.later), true);
    if (ds.unlater) return later(q(ds.unlater), false);
    if (ds.close) return close(q(ds.close));
    if (ds.reopen) return reopen(q(ds.reopen));
    if (ds.reply) { const d = draft(ds.reply); setDraft(ds.reply, {replyOpen: !(d.replyOpen || (d.reply || '').trim())}); return draw(true); }
    if (ds.unreply) { setDraft(ds.unreply, {reply: null, replyOpen: null}); return draw(true); }
    if (ds.link) { S.copied = ds.link; setTimeout(() => { S.copied = null; }, 3000); copy(location.href.split('#')[0] + '#questions/q-' + ds.link, 'Link'); return draw(true); }
    if (ds.askfile) { const on = !draft(ds.askfile).askfile; setDraft(ds.askfile, {askfile: on}); draw(true); if (on) ctx.inert('Asked the agent to file a task', () => { setDraft(ds.askfile, {askfile: null}); draw(true); }); return; }
    if (ds.task) return ctx.go('running', ds.task);
    if (ds.ev) { const el = root.querySelector(`[data-anchor-id="${CSS.escape(ds.ev)}"]`); if (el) { el.scrollIntoView({block: 'center', behavior: 'smooth'}); el.classList.add('qlit'); setTimeout(() => el.classList.remove('qlit'), 2000); } return; }
    if (ds.indoc) { S.view = 'doc'; ctx.prefs.set('q:view', 'doc'); S.open.add(ds.indoc); return draw().then(() => { const el = document.getElementById('q-' + ds.indoc); if (el) el.scrollIntoView({block: 'start'}); }); }
    if (t.hasAttribute('data-sendopen')) { S.armed = !S.armed; return draw(true); }
    if (t.hasAttribute('data-sendclose')) { S.armed = false; return draw(true); }
    if (t.hasAttribute('data-send')) return send();
    if (t.hasAttribute('data-sendundo')) { clearTimeout(S.pending.timer); S.pending = null; ctx.toast('Send undone: nothing left this page'); return draw(true); }
    if (t.hasAttribute('data-nadd')) return addNote(root.querySelector('[data-newnote] textarea').value);
    if (t.hasAttribute('data-ncancel')) { S.note = null; return draw(true); }
    if (ds.nedit) { S.note = {edit: ds.nedit}; return draw(true); }
    if (ds.nsave) return saveNote(ds.nsave, t.closest('.qnote').querySelector('textarea').value);
    if (ds.ndel) return delNote(ds.ndel);
    if (ds.ncopy) return copy((D.notes.find(x => x.id === ds.ncopy) || {}).text || '', 'Note');
    if (ds.nlink) return copy(location.href.split('#')[0] + '#questions/n-' + ds.nlink, 'Link');
    // a note: tap a picture spot, select words, or click a line, row or item of the document
    if (S.view !== 'doc' || t.closest('.qcard,.qnote,.qbar,.qsend,figcaption,summary')) return;
    const img = e.target.closest('img');
    const anchorEl = e.target.closest('[data-anchor-id]');
    if (!anchorEl || anchorEl.tagName === 'SECTION' && !img) return;
    const label = cut(anchorEl.textContent.trim() || (img && img.alt) || '', 60);
    let target;
    if (img) { const r = img.getBoundingClientRect(); target = {schema: 1, tag: 'img', offset: {dx: +((e.clientX - r.left) / r.width).toFixed(3), dy: +((e.clientY - r.top) / r.height).toFixed(3)}, css: 'img:nth-of-type(1)', image: img.dataset.img || null, image_src: img.dataset.full || img.getAttribute('src')}; }
    else { const sel = String(getSelection() || '').trim(); target = sel && anchorEl.contains(getSelection().anchorNode) ? {schema: 1, tag: anchorEl.tagName.toLowerCase(), quote: sel.slice(0, 300)} : {schema: 1, tag: anchorEl.tagName.toLowerCase()}; }
    S.note = {anchor: anchorEl.dataset.anchorId, label, target};
    draw(true).then(() => { const ta = root.querySelector('[data-newnote] textarea'); if (ta) ta.focus({preventScroll: true}); });
  }
  async function saveNote(id, text) {
    S.note = null;
    if (!text.trim()) return delNote(id);
    await call(`api/comments/${encodeURIComponent(id)}`, {text}, 'PUT');
    refresh();
  }
  function onInput(e) {
    const t = e.target, ds = t.dataset;
    if (ds.words) { const was = isDraft(qOf(ds.words)); setDraft(ds.words, {words: t.value}); if (was !== isDraft(qOf(ds.words))) { ctx.refreshChips(); updateBar(); } }
    else if (ds.replytext) setDraft(ds.replytext, {reply: t.value, replyOpen: true});
    else if (t.hasAttribute('data-general')) ctx.prefs.set('q:general', t.value);
  }
  function updateBar() { const b = root.querySelector('.qbar'); if (b) { const tmp = document.createElement('div'); tmp.innerHTML = bar(); b.replaceWith(tmp.querySelector('.qbar')); } }
  function onKey(e) {
    if (!root || !root.isConnected || !(e.metaKey || e.ctrlKey) || e.key !== 'Enter') return;
    e.preventDefault();
    const nt = e.target.closest && e.target.closest('.qnote');
    if (nt) return nt.hasAttribute('data-newnote') ? addNote(nt.querySelector('textarea').value) : saveNote(nt.dataset.note, nt.querySelector('textarea').value);
    arm();
  }
  function onChange(e) {  // a typed answer folds its card when the box is left
    const ds = e.target.dataset;
    if (ds.words && isDraft(qOf(ds.words)) && S.view === 'doc') draw(true);
  }
  addEventListener('keydown', onKey);
  document.addEventListener('toggle', e => {
    const d = e.target;
    if (!(d instanceof HTMLDetailsElement) || !d.classList.contains('aa-earlier') || !root || !root.contains(d)) return;
    d.open ? S.open.add('earlier') : S.open.delete('earlier');
    if (d.open) inflate(d);
  }, true);

  P.tab({
    key: 'questions',
    chip: async c => { ctx = ctx || c; D = D || await c.data('questions'); const n = waitingCount(); return n ? {text: `${n} waiting`, tone: 'red', title: pl(n, 'question waits', 'questions wait') + ' for your answer'} : null; },
    render: async (el, c, anchor) => {
      ctx = c; root = el;
      S.view = S.view || ctx.prefs.get('q:view', 'doc');
      el.innerHTML = '<p class="mut">Loading the questions…</p>';
      D = await c.data('questions');
      if (anchor && anchor.startsWith('q-')) { const id = anchor.slice(2), q = qOf(id); if (q) { S.shut.delete(id); if (isDone(q)) S.open.add(id); } }
      el.onclick = onClick; el.oninput = onInput; el.onchange = onChange;
      await draw();
    },
  });
  // shortcut: exposed for tests in a browser console only
  P.questionsState = () => ({S, D});
})();
