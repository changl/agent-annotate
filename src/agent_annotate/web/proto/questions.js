/* Prototype Questions tab: the review document, whole, with each question's card at its evidence; and Cards only.
   Picks, words, replies and Close are drafts in this browser until Send; Send posts them through today's endpoints
   (decision, reply, archive, rounds/submit) after a short Undo window. Notes and Later save at once and undo
   through today's calls (DELETE, answer-later off). The sandboxed server delivers nothing. */
(function () {
  'use strict';
  const P = window.Proto;
  const SEND_DELAY = 6000;
  const S = {open: new Set(), shut: new Set(), view: null, filter: 'need', armed: false, sendKey: false, pending: null, note: null, copied: null,
    hl: null, vy: {}, gen: false, zoom: null, sdef: new Map(), sdefV: null};
  let D = null, ctx = null, root = null, DOC = null, REF = null;

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
  const ASKFILE = 'Please file a task on the board for this question.';
  const gen = () => ctx.prefs.get('q:general', '');

  /* ---------- state of a question ---------- */
  const optLabel = (q, id) => (q.options.find(o => o.id === id) || {}).label || id;
  const isDraft = q => { const d = draft(q.id); return !!(d.pick || (d.words || '').trim()); };
  const isClosing = q => !q.closed && !!draft(q.id).close;  // Close goes with Send, Undo until then (#23)
  const hasReply = q => !!(draft(q.id).reply || '').trim();
  const isDone = q => q.closed || q.sent || q.later || isDraft(q) || isClosing(q);
  const isWaiting = q => !isDone(q);
  const cardOpen = q => isDone(q) ? S.open.has(q.id) : !S.shut.has(q.id);
  const waitingCount = () => (D ? D.questions.filter(isWaiting).length : 0);
  // the one Send count, in items as the Send summary lists them: the bar here, the top bar and the phone's floating Send
  const sendCount = () => D ? D.questions.reduce((n, q) => n + (q.closed ? 0 : isDraft(q) + isClosing(q) + hasReply(q)), 0) + D.notes.filter(x => !x.sent).length + (gen().trim() ? 1 : 0) : 0;

  function stateOf(q) {
    const d = draft(q.id), w = (d.words || '').trim();
    if (d.pick) return `<span class="saved">${ic('tick')} ${esc(cut(optLabel(q, d.pick), 40))}${w ? ' + your words' : ''} · goes with Send</span><button class="lk small" data-undo="${q.id}">Undo</button>`;
    if (w) return `<span class="saved">${ic('tick')} Answered in words · goes with Send</span><button class="lk small" data-undo="${q.id}">Undo</button>`;
    if (isClosing(q)) return `<span class="saved">${ic('archive')} Closed: no answer needed · goes with Send</span><button class="lk small" data-unclose="${q.id}">Undo</button>`;
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
    return `<button class="qtask" data-task="${esc(id)}" title="Open this task here"><span class="dot st-${b ? b.state : 'none'}"></span>${b ? `<span>${esc(cut(b.title, 60))}</span>` : ''}<span class="bid">· ${esc(id)}</span>${b ? `<span class="mut">· ${esc(b.status.replace('_', ' '))}</span>` : ''}</button>`;
  }
  // a card's task: one the question names or the page's tracking table links to it, else the first on the board that its evidence names
  function beadOf(q) {
    if (q.bead) return q.bead;
    for (const ev of q.evidence || []) {
      const el = DOC && DOC.querySelector(`[data-anchor-id="${CSS.escape(ev.anchor)}"]`);
      const m = el && (el.textContent.match(/\bFLD-[a-z0-9]+(?:\.\d+)*\b/g) || []).find(x => (D.beads || {})[x]);
      if (m) return m;
    }
    return null;
  }
  // the plan this question belongs to: the one sharing the most words with it, two at least (the mock's planOf)
  const WD = s => new Set((String(s).toLowerCase().match(/[a-z]{4,}/g) || []).filter(w => !['with', 'that', 'this', 'from', 'plan', 'should', 'what', 'which', 'approve', 'there'].includes(w)));
  function planOf(q) {
    if (!REF || !REF.plans) return null;
    const w = WD(q.prompt + ' ' + secTitle(q)); let best = null, bn = 1;
    for (const p of REF.plans) { const n = [...WD(p.t)].filter(x => w.has(x)).length; if (n > bn) { bn = n; best = p; } }
    return best;
  }
  const PLANST = {prop: 'Proposed', ok: 'Approved', ref: 'For reference'};
  // the title of the section a question's evidence sits in
  function secTitle(q) {
    const ev = q.evidence[0], el = ev && DOC && DOC.querySelector(`[data-anchor-id="${CSS.escape(ev.anchor)}"]`);
    const s = el && (el.tagName === 'SECTION' ? el : el.closest('section'));
    const h = s && s.querySelector(':scope > h2');
    return h ? h.textContent.replace(/:\s*\d+\s+cards?$/i, '').trim() : (ev && ev.label) || '';
  }

  /* ---------- the card ---------- */
  function card(q, inList) {
    const d = draft(q.id), open = inList ? true : cardOpen(q);
    const cls = `qcard${d.pick || (d.words || '').trim() ? ' answered' : q.sent ? ' sent' : q.closed || isClosing(q) ? ' closed' : q.later ? ' later' : ''}${S.hl === q.id ? ' hl' : ''}`;
    const marks = `<span class="qmarks">${blkMark(q)}${impMark(q)}</span>`;
    if (!open) {
      if (S.view !== 'list') return `<div class="${cls} folded" id="q-${q.id}" data-q="${q.id}"><div class="qhead"><button class="qfold" data-fold="${q.id}" aria-expanded="false" title="Open this card">${numChip(q)}<span class="qt">${esc(q.prompt)}</span></button><span class="qstate">${stateOf(q)}</span>${marks}</div></div>`;
      // Cards only: one line keeps the section, the marks and a one-click answer (#13)
      const rec = q.options.find(o => o.id === q.rec), ap = !rec && q.options.find(o => /^approve$/i.test(o.label)), st = stateOf(q);
      const right = st ? `<span class="qstate">${st}</span>` : rec ? `<button class="btn sm quick rec" data-pick="${q.id}" data-opt="${esc(rec.id)}" title="Agree with the recommended answer: ${esc(rec.label)}">${ic('tick')} ${esc(cut(rec.label, 26))}</button>`
        : ap ? `<button class="btn sm quick" data-pick="${q.id}" data-opt="${esc(ap.id)}">${ic('tick')} Approve</button>`
        : `<button class="btn sm quick" data-fold="${q.id}">${q.options.length ? 'No recommendation · Open' : 'Needs words · Open'}</button>`;
      return `<div class="${cls} folded qline" id="q-${q.id}" data-q="${q.id}"><div class="qhead"><button class="qfold" data-fold="${q.id}" aria-expanded="false" title="Open the whole card here, with its evidence">${numChip(q)}<span class="qt">${esc(q.prompt)}</span><span class="small mut qsect hide-ph">${esc(cut(secTitle(q), 40))}</span></button>${marks}<span class="qright">${right}</span></div></div>`;
    }
    const done = isDone(q), rp = d.replyOpen || (d.reply || '').trim();
    const acts = `${done ? '' : ibw('later', 'Later', 'Answer later: set it aside; it comes back under Answer later', `data-later="${q.id}"`)}${ibw('reply', 'Reply', 'Reply to the agent without answering', `data-reply="${q.id}" aria-pressed="${!!rp}"`)}${S.copied === q.id ? ibw('copied', 'Copied', 'Link copied', `data-link="${q.id}"`) : ibw('link', 'Link', 'Copy a link to this question', `data-link="${q.id}"`)}${q.closed || q.sent || isClosing(q) ? '' : ibw('archive', 'Close', 'Close without an answer: no answer needed. Goes with Send; Undo until then', `data-close="${q.id}"`)}`;
    const title = done && !inList ? `<button class="qfold" data-fold="${q.id}" aria-expanded="true" title="Fold this card">${numChip(q)}<span class="qt">${esc(q.prompt)}</span></button>` : `<span class="qfold static">${numChip(q)}<span class="qt">${esc(q.prompt)}</span></span>`;
    const head = `<div class="qhead">${title}<span class="qstate">${stateOf(q)}</span><span class="eacts">${acts}</span>${marks}</div>`;
    const cx = q.context ? `<div class="qctx p-primary">${q.context.split('\n').map(p => `<p>${beadText(esc(p))}</p>`).join('')}</div>` : '';
    const th = q.replies.filter(r => !/^(☑ Selected|💬 Answer in words|↻|✓|✗|↺)/.test(r.text)), tOpen = S.open.has('th' + q.id);
    const typing = (d.reply || '').trim() ? `<li class="you"><span class="who">You · goes with Send</span> ${esc(d.reply)}</li>` : '';
    const thread = th.length || typing ? `<div class="small"><b>Thread with the agent</b>${th.length > 2 ? ` · <button class="lk small" data-fold="th${q.id}" aria-expanded="${tOpen}">${tOpen ? 'Hide earlier replies' : pl(th.length - 2, 'earlier reply', 'earlier replies')}</button>` : ''}</div><ul class="qthread">${(tOpen ? th : th.slice(-2)).map(r => `<li class="${r.you ? 'you' : 'agent'}"><span class="who">${r.you ? 'You' : 'Agent'} · ${esc(fmt(r.ts))}${r.you && !r.sent ? ' · not sent' : ''}</span> ${esc(r.text)}</li>`).join('')}${typing}</ul>` : '';
    const bead = beadOf(q), hso = S.open.has('hs' + q.id), plan = planOf(q);
    const asked = (d.reply || '').trim() === ASKFILE;
    const ask = asked ? `<span class="saved">${ic('tick')} Asked to file one · goes with Send</span> <button class="lk small" data-askfile="${q.id}">Undo</button>`
      : `<button class="lk small" data-askfile="${q.id}" title="A reply to the agent, sent with your next Send">Ask the agent to file one</button>`;
    const meta = `<div class="qmeta">${bead ? `<span>${ic('task')} ${taskChip(bead)}</span>` : `<span>${ic('task')} No task on the board yet · ${ask}</span>`}${plan ? `<span>Plan: <button class="lk small" data-plan="${esc(plan.id)}">${esc(cut(plan.t, 40))}</button> · ${esc(PLANST[plan.st] || 'For reference')}</span>` : ''}<button class="dfold" data-fold="hs${q.id}" aria-expanded="${hso}" title="Your earlier answers on the same topic">${ic('hist')} Decided before · ${q.earlier.length}</button>${q.evidence.length && !inList ? `<button class="lk small" data-ev="${esc(q.evidence[0].anchor)}" data-evq="${q.id}">${ic('place')} ${esc(cut(q.evidence[0].label || 'Its evidence', 40))}</button>` : ''}</div>${hso ? `<ul class="qhist">${q.earlier.length ? q.earlier.map(h => `<li><span class="mut">${esc(h.t)} · version ${esc(String(h.v).slice(1))}</span> — ${esc(cut(h.q, 140))} → <b>${esc(cut(h.a, 160))}</b></li>`).join('') : '<li class="mut">Nothing decided on this before.</li>'}</ul>` : ''}`;
    const norec = !q.rec ? `<p class="small mut">The agent gave no recommendation${q.options.length ? '' : ' and no choices'}.</p>` : '';
    const an = `${norec}<div class="qopts">${q.options.map((o, i) => `<button class="qopt${o.id === q.rec ? ' rec' : ''}" data-pick="${q.id}" data-opt="${esc(o.id)}" aria-pressed="${d.pick === o.id}">${o.id === q.rec ? '<span class="rl">Recommended</span>' : ''}<b>${i + 1}. ${esc(o.label)}</b>${o.c ? `<span>${esc(o.c)}</span>` : ''}</button>`).join('')}</div>
      <textarea class="qwords" data-words="${q.id}" aria-label="Answer in words" placeholder="${q.options.length ? 'Answer in words. With no choice picked, this is your answer; with one, it goes with it.' : 'Your answer: there are no choices'}">${esc(d.words || '')}</textarea>
      <p class="hint">Saved as you type · <kbd>⌘↵</kbd> opens Send</p>
      ${rp ? `<label class="small"><b>Reply to the agent</b></label><textarea class="qwords" data-replytext="${q.id}" placeholder="Ask or tell the agent something about this question">${esc(d.reply || '')}</textarea><p class="hint">Saved as you type; goes with your next Send. <button class="lk small" data-unreply="${q.id}">Remove</button></p>` : ''}`;
    const body = `<div class="qbody"><div class="qcx">${cx}${thread}${meta}</div><div class="qan">${an}</div></div>`;
    return `<div class="${cls}" id="q-${q.id}" data-q="${q.id}">${head}${body}</div>`;
  }
  // tasks the agent names: title · bead id · state
  const beadText = h => h.replace(/\bFLD-[a-z0-9]+(?:\.\d+)*\b/g, m => (D.beads || {})[m] ? taskChip(m) : m);

  /* ---------- the document ---------- */
  // Markdown the agent left unrendered: links become links, pictures the page has become pictures (#02)
  function unmark(doc, node) {
    node = node || doc.body;
    const w = doc.createTreeWalker(node, NodeFilter.SHOW_TEXT), hits = [];
    for (let n; (n = w.nextNode());) if (/\]\(/.test(n.nodeValue) && n.parentElement && !n.parentElement.closest('code,pre,a')) hits.push(n);
    for (const n of hits) {
      const h = esc(n.nodeValue).replace(/(!?)\[([^\]]*)\]\(([^)\s]+)\)/g, (m, bang, t, href) => {
        if (/^(?!https?:)[a-z][\w+.-]*:/i.test(href)) return m;  // only page, relative and web links
        if (bang) return /^(\.\.\/|\/|https?:)/i.test(href) ? `<span class="qmissing" title="${href}">${ic('warn')} Picture not on this page: ${esc(href.split('/').slice(-3).join('/'))}</span>` : `<img src="${href}" alt="${t}">`;
        return `<a href="${href}"${href.startsWith('#') ? '' : ' target="_blank" rel="noopener"'}>${t}</a>`;
      });
      const span = doc.createElement('span'); span.innerHTML = h; n.replaceWith(span);
    }
    for (const tpl of node.querySelectorAll('template')) unmark(doc, tpl.content);  // "Earlier updates" keep theirs in a template
  }
  async function loadDoc(v) {
    if (loadDoc.v === v && loadDoc.html) return loadDoc.html;
    const r = await fetch(ctx.base + 'content?v=' + encodeURIComponent(v), {cache: 'no-store'});
    if (!r.ok) throw new Error('the document did not load (HTTP ' + r.status + ')');
    const doc = new DOMParser().parseFromString(await r.text(), 'text/html');
    for (const l of doc.querySelectorAll('link[rel=stylesheet][href*="content.css"]'))
      if (!document.querySelector(`link[data-qdoc]`)) document.head.appendChild(Object.assign(document.createElement('link'), {rel: 'stylesheet', href: l.getAttribute('href')})).dataset.qdoc = '1';
    doc.querySelectorAll('script,style').forEach(n => n.remove());
    unmark(doc);
    const aa = doc.querySelector('.aa') || doc.body;
    // no address shows on the prototype, company mailboxes included (same rule as proto_data/questions.py); picture names like x@2x.png stay
    loadDoc.v = v; loadDoc.html = aa.innerHTML.replace(/[\w.+-]+@[a-z][\w-]*(?:\.[\w-]+)*\.(?!png\b|jpe?g\b|gif\b|webp\b|svg\b)[a-z]{2,}\b/gi, 'member@example.com');
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
    if (tpl) { tpl.replaceWith(tpl.content.cloneNode(true)); placeCards(d); placeNotes(d); wrapTasks(d); indexRows(d); zoomBars(d); }
  }
  function placeNotes(docEl) {
    D.notes.forEach((n, i) => {
      const el = docEl.querySelector(`[data-anchor-id="${CSS.escape(n.anchor)}"]`);
      if (!el) return;
      const t = n.target || {};
      if (t.tag === 'img' && t.offset) {
        const img = el.tagName === 'IMG' ? el : t.image ? el.querySelector(`img[data-img="${CSS.escape(t.image)}"]`) || el.querySelector('img') : el.querySelector('img');
        if (img) pinOn(img, i + 1, t.offset);
      } else if (t.quote) markQuote(el, t.quote);
      const after = el.tagName === 'TR' ? el.closest('table').closest('.wrap') || el.closest('table') : el;
      after.insertAdjacentHTML(el.tagName === 'SECTION' ? 'beforeend' : 'afterend', noteBox(n, i + 1));
    });
    for (const c of D.carried || []) {  // his note from an earlier version, at its line here (#16)
      const el = docEl.querySelector(`[data-anchor-id="${CSS.escape(c.anchor)}"]`);
      if (el) (el.tagName === 'TR' ? el.closest('.wrap') || el.closest('table') : el).insertAdjacentHTML(el.tagName === 'SECTION' ? 'beforeend' : 'afterend', carriedBox(c));
    }
  }
  function carriedBox(c) {
    const st = (ctx.prefs.get('q:carried', {}))[c.id];
    const act = st === 'drop' ? `<span class="saved">Dropped</span> <button class="lk small" data-carried="${c.id}~">Undo</button>`
      : st === 'resend' ? `<span class="saved">Goes with Send</span> <button class="lk small" data-carried="${c.id}~">Undo</button>`
      : `<button class="lk small" data-carried="${c.id}~drop">Drop it</button> · <button class="lk small" data-carried="${c.id}~resend">Send it again</button>`;
    return `<div class="qnote sent car">${mk('↻', true)}<b>Your note from version ${esc(String(c.v).slice(1))}, carried to version ${esc(String(D.version).slice(1))}:</b> ${esc(c.text)}${c.changed ? ' <span class="warn-t">· the text under it changed since you wrote it</span>' : ''} ${act}</div>`;
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
  const KIND = t => t.quote ? `on “${esc(cut(t.quote, 50))}”` : t.tag === 'img' ? 'at this spot' : t.tag === 'tr' ? 'on this row' : /^h\d$/.test(t.tag || '') ? 'on this heading' : 'on this line';
  function noteBox(n, no) {
    const t = n.target || {}, what = KIND(t);
    if (S.note && S.note.edit === n.id) return `<div class="qnote" data-note="${n.id}">${mk(no)}<b>Note ${no} ${what}</b><textarea data-notetext aria-label="Note ${no}">${esc(n.text)}</textarea><div class="acts"><button class="btn sm pri" data-nsave="${n.id}">Save</button><button class="lk small" data-ncancel>Cancel</button><span class="small mut"><kbd>⌘↵</kbd> saves</span></div></div>`;
    const acts = n.sent ? ib('edit', 'Correct it; the fix goes with your next Send', `data-nfix="${n.id}"`) + ib('copy', 'Copy the note text', `data-ncopy="${n.id}"`)
      : ib('edit', 'Edit this note', `data-nedit="${n.id}"`) + ib('undo', 'Undo: remove this note', `data-ndel="${n.id}"`) + ib('copy', 'Copy the note text', `data-ncopy="${n.id}"`) + ib('link', 'Copy a link to this note', `data-nlink="${n.id}"`);
    return `<div class="qnote${n.sent ? ' sent' : ''}" id="n-${n.id}" data-note="${n.id}">${mk(no, n.sent)}<b>Note ${no} ${what}:</b> ${esc(n.text)} <span class="${n.sent ? 'mut' : 'saved'}">· ${n.sent ? 'sent' : 'goes with Send'}</span><span class="nacts">${acts}</span></div>`;
  }
  function newNoteBox() {
    const n = S.note, fx = n.fixOf ? ' · fix to a sent note' : '';
    return `<div class="qnote new" data-newnote>${mk('+')}<b>New note ${KIND(n.target)}</b> <span class="mut small">${fx} · goes with your next Send</span><textarea data-notetext aria-label="Your note" placeholder="Type your note">${esc(n.text || '')}</textarea><div class="acts"><button class="btn sm pri" data-nadd>Save</button><button class="lk small" data-ncancel>Cancel</button><span class="small mut"><kbd>⌘↵</kbd> saves · an empty note is dropped</span></div></div>`;
  }

  /* ---------- document navigation: header, jump menu, section folds, tiles, question rows (#12, #19) ---------- */
  const topSecs = docEl => [...docEl.querySelectorAll(':scope > section[data-anchor-id]')];
  function secQs(sec) { const ids = new Set([...sec.querySelectorAll('.qcard[data-q]')].map(e => e.dataset.q)); return D.questions.filter(q => ids.has(q.id)); }
  // decided once per visit, so answering never folds the page under you: open while a question in it waits, or when new with no questions
  function secDefault(sec) {
    const a = sec.dataset.anchorId;
    if (S.sdefV !== D.version) { S.sdef = new Map(); S.sdefV = D.version; }
    if (!S.sdef.has(a)) { const qs = secQs(sec); S.sdef.set(a, qs.length ? qs.some(isWaiting) : (D.since || {})[a] === '' || !(a in (D.since || {}))); }
    return S.sdef.get(a);
  }
  const secOpen = sec => secDefault(sec) !== S.open.has('d:' + sec.dataset.anchorId);
  function foldSections(docEl) {
    for (const sec of topSecs(docEl)) {
      const h = sec.querySelector(':scope > h2'), a = sec.dataset.anchorId;
      if (!h) continue;
      const open = secOpen(sec), qs = secQs(sec), nq = qs.filter(isWaiting).length, since = (D.since || {})[a];
      sec.classList.add('qsec'); sec.classList.toggle('qshut', !open);
      const last = h.lastChild; if (last && last.nodeType === 3) last.nodeValue = last.nodeValue.replace(/:\s*\d+\s+cards?\s*$/i, '');
      h.insertAdjacentHTML('afterbegin', `<button class="qsecf" data-sfold="${esc(a)}" aria-expanded="${open}" title="${open ? 'Fold this section' : 'Open this section'}"></button>`);
      h.insertAdjacentHTML('beforeend', `<span class="qsecm">${nq ? `<span class="badge qw">${pl(nq, 'question waiting', 'questions waiting')}</span>` : qs.length ? `<span class="badge ok">${qs.length} of ${qs.length} decided</span>` : ''}${since === '' ? '<span class="qnew">new in this version</span>' : since ? `<span class="small mut">unchanged since version ${esc(since.slice(1))}</span>` : ''}</span>`);
    }
    const first = topSecs(docEl)[0], t = D.tiles, h2 = first && first.querySelector(':scope > h2');
    if (t && h2) h2.insertAdjacentHTML('afterend', `<div class="qtiles">${[[t.versions, 'versions published', ''], [t.open, 'notes still open', 'warn'], [t.addressed, 'notes the agent addressed', 'ok'], [t.sends, 'Sends received', '']].map(([n, w, c]) => `<div class="${c}"><b>${Number(n).toLocaleString()}</b><span>${w}</span></div>`).join('')}</div>`);
  }
  function docHead(docEl) {
    const secs = topSecs(docEl), figs = [...docEl.querySelectorAll('figure[data-anchor-id]')].filter(f => !f.parentElement.closest('figure'));
    const anyOpen = secs.some(secOpen);
    const jump = `<select data-secjump aria-label="Go to a section"><option value="">Go to a section…</option><optgroup label="Sections">${secs.map(s => `<option value="${esc(s.dataset.anchorId)}">${esc(cut((s.querySelector(':scope > h2') || {}).textContent || '', 60))}</option>`).join('')}</optgroup>${figs.length ? `<optgroup label="Pictures and diagrams">${figs.map((f, i) => `<option value="${esc(f.dataset.anchorId)}">Picture ${i + 1} · ${esc(cut((f.querySelector('figcaption') || {}).textContent || '', 40))}</option>`).join('')}</optgroup>` : ''}</select>`;
    return `<div class="qdoch"><h2>The review document</h2><span class="small mut">version ${esc(String(D.version).slice(1))} · click a line or row, select words, or tap a picture to write a note</span><span class="spacer"></span>${jump}<button class="btn sm" data-secall>${anyOpen ? 'Collapse all' : 'Expand all'}</button></div>`;
  }
  // "Open for you: #N (what), …" in the agent's text: one row of question chips per list, not a paragraph of numbers (#19)
  function indexRows(docEl) {
    const RE = /([^:.<>]{2,80}):\s*((?:<a href="#d:q\d+">[^<]*<\/a>\s*(?:\([^)]*\))?\s*[,;]?\s*(?:and\s+)?)+)/g;
    for (const p of docEl.querySelectorAll('p')) {
      if (p.closest('.qcard') || (p.querySelectorAll('a[href^="#d:q"]').length < 2)) continue;
      const h = p.innerHTML.replace(/<\/?strong>/g, ''), rows = [];
      const rest = h.replace(RE, (m, lab, list) => {
        rows.push(`<div class="qrow"><b class="small">${lab.trim()}</b><span class="qcs">${[...list.matchAll(/<a href="#d:q(\d+)">[^<]*<\/a>\s*(?:\(([^)]*)\))?/g)].map(([, n, t]) => { const q = D.questions.find(x => String(x.n) === n);
          return `<button class="qchip" data-qref="${n}" title="Open question ${n}${q ? ': ' + esc(q.prompt) : ''}"><span class="qnum">Q ${n}</span><span>${t ? t : q ? esc(cut(q.prompt, 48)) : ''}</span></button>`; }).join('')}</span></div>`);
        return '';
      }).replace(/Click a number to jump to it\.?/i, '').trim();
      if (!rows.length) continue;
      const div = document.createElement('div');
      div.className = 'qrows'; if (p.dataset.anchorId) div.dataset.anchorId = p.dataset.anchorId;
      div.innerHTML = rows.join('') + (rest.replace(/<[^>]+>/g, '').replace(/[\s.,;]/g, '') ? `<p>${rest}</p>` : '');
      p.replaceWith(div);
    }
  }

  /* ---------- pictures: size buttons open the in-page viewer, with its notes (#24) ---------- */
  const zoomOf = src => (ctx.prefs.get('q:zoomPer', {}))[src] || ctx.prefs.get('zoomDef', 75);
  function zoomBars(el) {
    for (const a of el.querySelectorAll('a.aa-full')) {
      if (a.previousElementSibling && a.previousElementSibling.classList.contains('qzm')) continue;
      const src = a.getAttribute('href'), z = zoomOf(src);
      a.dataset.zfull = src; a.textContent = '⤢ Full size';
      a.insertAdjacentHTML('beforebegin', `<span class="qzm" role="group" aria-label="Open full size at">${[25, 50, 75, 100].map(x => `<button data-zoom="${x}" aria-pressed="${x === z}" title="Open full size at ${x}% of the screen width">${x}%</button>`).join('')}</span>`);
    }
    el.querySelectorAll('img').forEach(i => { i.loading = 'eager'; });
  }
  function zoomView() {
    if (!S.zoom) return '';
    const {src, cap, z, img} = S.zoom;
    const ns = D.notes.map((n, i) => [n, i + 1]).filter(([n]) => (n.target || {}).tag === 'img' && (n.target.image_src === src || (img && n.target.image === img)));
    return `<div class="qzoom" role="dialog" aria-label="Full-size picture"><div class="qzbar"><b class="small">${esc(cut(cap, 60))}</b><span class="qzm">${[25, 50, 75, 100].map(x => `<button data-zoomto="${x}" aria-pressed="${x === z}">${x}%</button>`).join('')}</span><span class="small mut hide-ph">of the screen width · tap a spot to write a note · <kbd>Esc</kbd> closes</span><span class="spacer"></span><button class="btn sm" data-zclose>Close</button></div>
      <div class="qzpic" style="width:${z}vw"><img src="${esc(src)}" alt="${esc(cap)}" data-zimg>${ns.map(([n, no]) => `<span class="qpin" style="left:${n.target.offset.dx * 100}%;top:${n.target.offset.dy * 100}%">${no}</span>`).join('')}</div>
      ${ns.length ? `<div class="qznotes">${ns.map(([n, no]) => noteBox(n, no)).join('')}</div>` : ''}</div>`;
  }

  /* ---------- the bar ---------- */
  const FILTERS = {
    need: q => !q.sent && !q.later && !q.closed,  // an answered card stays at its place in Waiting, with its Undo (#20)
    later: q => q.later && !q.closed && !isDraft(q) && !q.sent,
    ready: q => isDraft(q) || isClosing(q) || hasReply(q), wait: q => q.sent, arch: q => q.closed || isClosing(q)};
  function bar() {
    const cnt = k => D.questions.filter(FILTERS[k]).length, lv = S.view === 'list';
    const decided = D.questions.filter(q => !isWaiting(q) && !q.later).length, all = D.questions.length;
    const chips = [['need', `Waiting ${waitingCount()}`], ['later', `<span class="hide-ph">Answer later</span><span class="ph-only">Later</span> ${cnt('later')}`], ['ready', `To send ${cnt('ready')}`], ['wait', `Sent ${cnt('wait')}`], ['arch', `Closed ${cnt('arch')}`]];
    const vsw = `<span class="qseg" role="group" aria-label="View">${[['doc', 'doc', 'Document', 'The review document, each card at its evidence'], ['list', 'list', 'Cards only', 'Only the cards, open; each folds once answered']].map(([v, k, t, tip]) => `<button data-view="${v}" aria-pressed="${S.view === v}" title="${tip}">${ic(k)}<span class="hide-ph">${t}</span></button>`).join('')}</span>`;
    const n = sendCount(), g = gen().trim();
    return `<div class="qbar">${vsw}<span class="qchips">${chips.map(([k, t]) => `<button class="chipb" data-filter="${k}" aria-pressed="${lv && S.filter === k}"${lv ? '' : ' title="Show these in Cards only"'}>${t}</button>`).join('')}<button class="chipb" data-done title="Your answers from earlier versions, in History">Done ${Number(D.done || 0).toLocaleString()} ›</button></span>
      <span class="prog" title="${decided} of ${all} questions decided">${decided} of ${all}<span class="hide-ph"> decided</span><i><b style="width:${all ? Math.round(decided / all * 100) : 0}%"></b></i></span>
      <span class="spacer"></span>${lv ? `<span class="qseg" role="group" aria-label="Open or fold the cards">${ib('expand', 'Expand all: open every card in this list', 'data-all="expand"')}${ib('collapse', 'Collapse all: fold every card in this list to its line', 'data-all="collapse"')}${ib('colans', 'Collapse answered: fold the cards you answered, closed or set aside', 'data-all="answered"')}</span>` : ''}
      <button class="btn sm${g ? ' rec' : ''}" data-genopen aria-pressed="${S.gen}">${g ? `${ic('tick')} General feedback · Edit` : 'General feedback'}</button>
      <button class="btn sm qbsend${n ? ' pri' : ''}" data-sendopen ${n ? '' : 'disabled'} title="Send your answers and notes · ⌘↵ twice">${ic('send')} Send${n ? ' ' + n : ''}</button></div>${genSheet()}${sendPanel(n)}`;
  }
  function genSheet() {
    if (!S.gen) return '';
    const g = gen();
    return `<div class="qgen" role="dialog" aria-label="General feedback"><b>General feedback</b><textarea class="qwords" data-general placeholder="Not tied to one spot; goes first in your next Send">${esc(g)}</textarea><p class="hint">Saved as you type.</p><div class="acts"><button class="btn sm pri" data-genclose>Done</button>${g.trim() ? '<button class="lk small" data-ungen>Remove</button>' : ''}</div></div>`;
  }
  // every item of the next Send: [group, html, go-to target, remove key] (the mock's sendItems)
  function sendItems() {
    const it = [];
    for (const q of D.questions) {
      const d = draft(q.id), w = (d.words || '').trim();
      if (q.closed) continue;
      if (d.pick) it.push(['Answers', `Q ${esc(q.n)} · ${esc(q.prompt)} → <b>${esc(optLabel(q, d.pick))}</b>${w ? ` + “${esc(cut(w, 80))}”` : ''}`, 'q:' + q.id, 'ans:' + q.id]);
      else if (w) it.push(['Answers', `Q ${esc(q.n)} · ${esc(q.prompt)} → in words: “${esc(cut(w, 120))}”`, 'q:' + q.id, 'ans:' + q.id]);
      if (isClosing(q)) it.push(['Answers', `Q ${esc(q.n)} · ${esc(q.prompt)} → <b>Closed: no answer needed</b>`, 'q:' + q.id, 'close:' + q.id]);
    }
    for (const q of D.questions) if (!q.closed && hasReply(q)) it.push(['Replies to the agent', `On Q ${esc(q.n)}: “${esc(cut(draft(q.id).reply, 120))}”`, 'q:' + q.id, 'reply:' + q.id]);
    D.notes.forEach((n, i) => { if (!n.sent) it.push(['Notes', `${mk(i + 1)}${(n.target || {}).quote ? `On “${esc(cut(n.target.quote, 40))}”` : (n.target || {}).tag === 'img' ? 'At a spot on a picture' : `On “${esc(cut(n.label || '', 50))}”`}: ${esc(cut(n.text, 140))}`, 'n:' + n.id, 'note:' + n.id]); });
    return it;
  }
  function sendPanel(n) {
    if (S.pending) return `<div class="qsend sending" role="status">${ic('send')} Sending ${pl(S.pending.n, 'item', 'items')}… <button class="lk" data-sendundo>Undo</button> ${P.inertMark()}</div>`;
    if (!S.armed) return '';
    const it = sendItems(), g = {}, un = waitingCount(), lat = D.questions.filter(FILTERS.later).length;
    it.forEach(x => (g[x[0]] = g[x[0]] || []).push(x));
    return `<div class="qsheet" data-sendclose><div class="qsend" role="dialog" aria-label="Send"><h2>Send to the agent · ${pl(n, 'item', 'items')}</h2>
      <p class="small mut">Goes to the FastLane Drive agent session. Nothing goes until you press Send. ${P.inertMark()}</p>
      ${S.sendKey && n ? `<div class="qsendkey" role="status">${ic('send')} Press <kbd>⌘↵</kbd> again to send ${pl(n, 'item', 'items')} · <kbd>Esc</kbd> keeps editing</div>` : ''}
      <h4>General feedback · goes first</h4><textarea class="qwords" data-general placeholder="Not tied to one spot (optional)">${esc(gen())}</textarea>
      ${Object.entries(g).map(([t, l]) => `<h4>${esc(t)} · ${l.length}</h4><ul class="qhist">${l.map(([, h, go, rm]) => `<li>${h} <button class="lk small" data-sgo="${esc(go)}">Go to it</button> · <button class="lk small" data-srm="${esc(rm)}">Remove</button></li>`).join('')}</ul>`).join('') || (gen().trim() ? '' : '<p class="small mut">Nothing ready yet.</p>')}
      <h4>Not in this Send</h4><p class="small">${un || lat ? `<span class="warn-t">${pl(un, 'question still waits', 'questions still wait')}</span>; ${lat} set aside. They stay for next time. <button class="lk small" data-sgo="need">Open Questions</button>` : 'Every question has an answer.'}</p>
      <div class="acts"><button class="btn pri" data-send ${n ? '' : 'disabled'}>${ic('send')} Send ${n} <kbd>⌘↵</kbd></button><button class="btn" data-discard ${n ? '' : 'disabled'}>Discard all</button><button class="btn ghost" data-sendclose>Keep editing</button><span class="small mut"><kbd>⌘↵</kbd> sends</span></div></div></div>`;
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
      placeCards(docEl, true); placeNotes(docEl); wrapTasks(docEl); indexRows(docEl); foldSections(docEl);
      docEl.insertAdjacentHTML('afterbegin', docHead(docEl));
      docEl.querySelectorAll('details.aa-earlier').forEach(d => { if (S.open.has('earlier')) { d.open = true; inflate(d); } });
      if (S.note) {
        const el = docEl.querySelector(`[data-anchor-id="${CSS.escape(S.note.anchor)}"]:not(.qcard)`);
        const after = el && (el.tagName === 'TR' ? el.closest('.wrap') || el.closest('table') : el);
        if (after) after.insertAdjacentHTML(el.tagName === 'SECTION' ? 'beforeend' : 'afterend', newNoteBox());
      }
    }
    zoomBars(root);
    if (S.zoom) root.insertAdjacentHTML('beforeend', zoomView());
    document.body.classList.toggle('qsheet-open', !!(S.armed || S.zoom));
    if (keepScroll) scrollTo(0, y);
    ctx.refreshChips(); if (ctx.refreshTop) ctx.refreshTop();
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
  // a card's evidence, copied from the document into Cards only: its lines, rows, tables and every picture (#01)
  function evHtml(el) {
    if (el.tagName === 'SECTION') {
      let p = 0;
      return [...el.children].filter(c => !c.matches('.cards,section,details,template')).filter(c => c.matches('h2,h3,h4,figure,.wrap,table') || c.querySelector('img') || p++ < 3).map(c => c.outerHTML).join('');
    }
    if (/^H[2-6]$/.test(el.tagName)) {
      const lv = +el.tagName[1], out = [el.outerHTML];
      for (let s = el.nextElementSibling; s && out.length < 10; s = s.nextElementSibling) {
        if (/^H[2-6]$/.test(s.tagName) && +s.tagName[1] <= lv || s.matches('.cards')) break;
        out.push(s.outerHTML);
      }
      return out.join('');
    }
    if (el.tagName === 'TR') { const t = el.closest('table'); return `<table>${t && t.tHead ? t.tHead.outerHTML : ''}<tbody>${el.outerHTML}</tbody></table>`; }
    return el.outerHTML;
  }
  function evidence(q) {
    if (!DOC || !q.evidence.length) return '';
    const els = [];
    for (const ev of q.evidence) {
      const el = DOC.querySelector(`[data-anchor-id="${CSS.escape(ev.anchor)}"]`);
      if (el && !els.some(x => x.contains(el))) els.push(el);
    }
    if (!els.length) return '';
    const ev = q.evidence[0];
    const box = document.createElement('div'); box.innerHTML = els.map(evHtml).join('');
    box.querySelectorAll('.qcard,.qnote,.qsecf,.qsecm,.qtiles,.qpeek').forEach(x => x.remove());  // the document's own text only, not this tab's additions
    return `<div class="qev"><div class="small mut">${ic('place')} Its evidence in the document: <button class="lk small" data-indoc="${q.id}">${esc(cut(ev.label || 'open in the document', 50))}</button></div><div class="aa qevb">${box.innerHTML}</div></div>`;
  }

  /* ---------- actions ---------- */
  const qOf = id => D.questions.find(q => q.id === id);
  async function refresh() { D = await ctx.data('questions', true); await draw(true); }
  function pick(q, opt) {
    const was = draft(q.id).pick;
    setDraft(q.id, {pick: was === opt ? null : opt});
    S.hl = q.id;
    draw(true);
  }
  async function later(q, on) {
    await call(`api/comments/${encodeURIComponent(q.id)}/answer-later`, {on});
    q.later = on; draw(true);
    if (on) ctx.toast('Set aside for later', {undo: () => later(q, false)});
  }
  function close(q) {
    setDraft(q.id, {close: true}); S.open.delete(q.id); draw(true);
    ctx.toast('Closed: no answer needed · goes with Send', {undo: () => { setDraft(q.id, {close: null}); draw(true); }});
  }
  async function reopen(q) { await call(`api/comments/${encodeURIComponent(q.id)}/restore`, {}); q.closed = false; S.open.delete(q.id); draw(true); }
  function undo(q) {
    const keep = draft(q.id);
    setDraft(q.id, {pick: null, words: null}); S.open.delete(q.id); draw(true);
    ctx.toast('Answer removed', {undo: () => { setDraft(q.id, {pick: keep.pick, words: keep.words}); draw(true); }});
  }
  async function addNote(text) {
    const n = S.note; S.note = null; ctx.prefs.set('q:newnote', null);
    if (!text.trim()) return draw(true);
    const c = await call('api/comments', {anchor_id: n.anchor, anchor_label: n.label, text, version: D.version, target: n.target});
    await refresh();
    ctx.toast(n.fixOf ? 'Correction saved · goes with Send' : 'Note saved · goes with Send', {undo: () => delNote(c.id, true)});
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
  // the card, its section and the evidence open, scrolled to and lit together (#19, catalog 26)
  async function jumpTo(id, view) {
    const q = qOf(id); if (!q) return;
    if (view && S.view !== view) { S.vy[S.view] = scrollY; S.view = view; ctx.prefs.set('q:view', view); }
    S.hl = id; S.shut.delete(id); if (isDone(q)) S.open.add(id);
    if (S.view === 'list' && !FILTERS[S.filter](q)) S.filter = q.later ? 'later' : q.sent ? 'wait' : q.closed ? 'arch' : 'need';
    if (S.view === 'doc' && DOC) { const c = DOC.querySelector(`#q-${CSS.escape(id)}`), sec = c && c.closest('section.qsec'); if (sec && !secOpen(sec)) S.open.has('d:' + sec.dataset.anchorId) ? S.open.delete('d:' + sec.dataset.anchorId) : S.open.add('d:' + sec.dataset.anchorId); }
    if (S.view === 'doc' && q.anchor && DOC && !DOC.querySelector(`#q-${CSS.escape(id)}`)) S.open.add('earlier');
    await draw(true);
    const el = document.getElementById('q-' + id); if (!el) return;
    el.scrollIntoView({block: 'start'});
    const ev = q.evidence[0] && root.querySelector(`[data-anchor-id="${CSS.escape(q.evidence[0].anchor)}"]:not(.qcard)`);
    for (const x of [el, ev]) if (x) { x.classList.add('qlit'); setTimeout(() => x.classList.remove('qlit'), 2500); }
  }
  function switchView(v) {
    S.vy[S.view] = scrollY; S.view = v; ctx.prefs.set('q:view', v);
    return draw().then(() => scrollTo(0, S.vy[v] || 0));  // each view keeps its own place (#22)
  }

  /* Send: ⌘↵ once opens the summary, again sends. The posts wait SEND_DELAY ms, with Undo, then go through today's endpoints. */
  function arm() {
    if (S.pending) return;
    if (!S.armed) { S.armed = true; S.sendKey = true; S.gen = false; draw(true).then(() => { const t = root.querySelector('[data-send]'); if (t) t.focus(); }); return; }
    send();
  }
  function send() {
    const answers = D.questions.filter(q => isDraft(q) && !q.closed), replies = D.questions.filter(q => hasReply(q) && !q.closed), closes = D.questions.filter(isClosing);
    const n = sendCount();
    S.armed = false; S.sendKey = false;
    if (!n) return draw(true);
    S.pending = {n, timer: setTimeout(() => post(answers, replies, closes), SEND_DELAY)};
    draw(true);
  }
  async function post(answers, replies, closes) {
    try {
      for (const q of answers) {
        const d = draft(q.id), w = (d.words || '').trim();
        const body = d.pick ? {verdict: 'select', text: optLabel(q, d.pick) + (w ? '\n\n' + w : ''), option_id: d.pick, defer_push: true} : {verdict: 'comment', text: w, defer_push: true};
        await call(`api/comments/${encodeURIComponent(q.id)}/decision`, body);
        setDraft(q.id, {pick: null, words: null});
      }
      for (const q of replies) { await call(`api/comments/${encodeURIComponent(q.id)}/reply`, {text: draft(q.id).reply.trim()}); setDraft(q.id, {reply: null, replyOpen: null}); }
      for (const q of closes) { await call(`api/comments/${encodeURIComponent(q.id)}/archive`, {}); setDraft(q.id, {close: null}); }
      await call('api/rounds/submit', {note: gen().trim() || undefined, version: D.version});
      ctx.prefs.set('q:general', '');
      S.pending = null;
      await refresh();
      ctx.toast(`Sent ${pl(answers.length, 'answer', 'answers')}: saved as a round in this copy`, {inert: true});
    } catch (e) {
      S.pending = null; await refresh();
      ctx.toast('Send failed: ' + e.message + '. Your drafts are kept.');
    }
  }
  // Discard all: every draft, the general feedback and the unsent notes go, with one Undo (#10)
  async function discardAll() {
    const keep = drafts(), g = gen(), notes = D.notes.filter(x => !x.sent);
    const all = {};
    for (const [id, d] of Object.entries(keep)) { const r = Object.assign({}, d); for (const k of ['pick', 'words', 'reply', 'replyOpen', 'close']) delete r[k]; if (Object.keys(r).length) all[id] = r; }
    ctx.prefs.set('q:drafts', all); ctx.prefs.set('q:general', ''); S.armed = false; S.sendKey = false;
    for (const n of notes) await call(`api/comments/${encodeURIComponent(n.id)}`, undefined, 'DELETE');
    await refresh();
    ctx.toast(`Discarded ${pl(notes.length + Object.keys(keep).length + (g.trim() ? 1 : 0), 'draft', 'drafts')}`, {undo: async () => {
      ctx.prefs.set('q:drafts', keep); ctx.prefs.set('q:general', g);
      for (const n of notes) await call('api/comments', {anchor_id: n.anchor, anchor_label: n.label, text: n.text, version: D.version, target: n.target});
      refresh();
    }});
  }
  function sendRemove(k) {
    const [kind, id] = [k.slice(0, k.indexOf(':')), k.slice(k.indexOf(':') + 1)];
    if (kind === 'ans') { const keep = draft(id); setDraft(id, {pick: null, words: null}); draw(true); ctx.toast('Answer removed', {undo: () => { setDraft(id, {pick: keep.pick, words: keep.words}); draw(true); }}); }
    else if (kind === 'close') { setDraft(id, {close: null}); draw(true); ctx.toast('Close removed', {undo: () => { setDraft(id, {close: true}); draw(true); }}); }
    else if (kind === 'reply') { const r = draft(id).reply; setDraft(id, {reply: null, replyOpen: null}); draw(true); ctx.toast('Reply removed', {undo: () => { setDraft(id, {reply: r}); draw(true); }}); }
    else if (kind === 'note') delNote(id);
  }
  function sendGo(k) {
    S.armed = false; S.sendKey = false;
    if (k === 'need') { S.filter = 'need'; return switchView('list'); }
    if (k.startsWith('q:')) return jumpTo(k.slice(2));
    if (k.startsWith('n:')) { const go = () => { const el = document.getElementById('n-' + k.slice(2)); if (el) { el.scrollIntoView({block: 'center', behavior: 'smooth'}); el.classList.add('qlit'); setTimeout(() => el.classList.remove('qlit'), 2500); } }; return (S.view === 'doc' ? draw(true) : switchView('doc')).then(go); }
  }
  // a task opens beside the text it sits in, not in another tab (#27)
  function peek(btn) {
    const id = btn.dataset.task, nx = btn.nextElementSibling;
    if (nx && nx.classList.contains('qpeek')) return nx.remove();
    const b = (D.beads || {})[id];
    btn.insertAdjacentHTML('afterend', `<span class="qpeek small" role="note">${b ? `“${esc(b.title)}” · ${esc(b.status.replace('_', ' '))} on the board` : 'Not on the board'} · task ${esc(id)} · <button class="lk small" data-taskrun="${esc(id)}">Open in Running</button> · <button class="lk small" data-copytext="bd show ${esc(id)}">Copy “bd show ${esc(id)}”</button> · <button class="lk small" data-peekclose>Close</button></span>`);
  }
  async function carried(id, st) {
    const all = ctx.prefs.get('q:carried', {}), c = (D.carried || []).find(x => x.id === id), was = all[id];
    if (st === 'resend' && c) { const r = await call('api/comments', {anchor_id: c.anchor, anchor_label: 'Carried note', text: c.text, version: D.version}); all[id + ':copy'] = r && r.id; }
    if (!st && was === 'resend' && all[id + ':copy']) { await call(`api/comments/${encodeURIComponent(all[id + ':copy'])}`, undefined, 'DELETE'); delete all[id + ':copy']; }
    if (st) all[id] = st; else delete all[id];
    ctx.prefs.set('q:carried', all);
    refresh();
  }

  function onClick(e) {
    const card0 = e.target.closest('.qcard[data-q]');  // any click on a card makes it the one the keys act on
    if (card0 && S.hl !== card0.dataset.q) { root.querySelectorAll('.qcard.hl').forEach(x => x.classList.remove('hl')); S.hl = card0.dataset.q; card0.classList.add('hl'); }
    const t = e.target.closest('button,a,[data-anchor-id],img,.qsheet');
    if (!t || !root.contains(t)) return;
    const ds = t.dataset, q = id => qOf(id);
    if (t.classList.contains('qsheet') && e.target !== t) return;  // a click inside the Send panel, not on its backdrop
    if (t.tagName === 'A') {  // links inside the document: "#d:q38833" jumps to the card, never to another tab
      const h = t.getAttribute('href') || '';
      if (t.dataset.zfull) { e.preventDefault(); const img = t.closest('figure') && t.closest('figure').querySelector('img'); S.zoom = {src: t.dataset.zfull, cap: img ? img.alt : '', img: img && img.dataset.img, anchor: (t.closest('[data-anchor-id]') || {}).dataset?.anchorId, z: zoomOf(t.dataset.zfull)}; return draw(true); }
      if (h.startsWith('#')) {
        e.preventDefault();
        const id = decodeURIComponent(h.slice(1)), qq = D.questions.find(x => x.anchor === id);
        if (qq) return jumpTo(qq.id);
        const el = root.querySelector(`[data-anchor-id="${CSS.escape(id)}"]`); if (el) el.scrollIntoView({block: 'start'});
      }
      return;
    }
    if (ds.view) return switchView(ds.view);
    if (ds.filter) { S.filter = ds.filter; return S.view === 'list' ? draw() : switchView('list'); }
    if (t.hasAttribute('data-done')) return ctx.go('history');
    if (ds.all) { const set = S.view === 'list' ? D.questions.filter(FILTERS[S.filter] || FILTERS.need) : D.questions; for (const x of set) { if (ds.all === 'expand') { S.shut.delete(x.id); if (isDone(x)) S.open.add(x.id); } else if (ds.all === 'collapse') { S.shut.add(x.id); S.open.delete(x.id); } else if (isDone(x)) S.open.delete(x.id); } return draw(true); }
    if (ds.fold) { const k = ds.fold, x = q(k); if (x) { const open = cardOpen(x); if (isDone(x)) open ? S.open.delete(k) : S.open.add(k); else open ? S.shut.add(k) : S.shut.delete(k); S.hl = k; } else S.open.has(k) ? S.open.delete(k) : S.open.add(k); return draw(true); }
    if (ds.sfold) { const k = 'd:' + ds.sfold; S.open.has(k) ? S.open.delete(k) : S.open.add(k); return draw(true); }
    if (t.hasAttribute('data-secall')) { const secs = DOC ? topSecs(DOC) : [], open = !secs.some(secOpen); for (const s of secs) (open === secDefault(s)) ? S.open.delete('d:' + s.dataset.anchorId) : S.open.add('d:' + s.dataset.anchorId); return draw(true); }
    if (ds.qref) { const qq = D.questions.find(x => String(x.n) === ds.qref); return qq ? jumpTo(qq.id) : ctx.go('history'); }
    if (ds.pick) return pick(q(ds.pick), ds.opt);
    if (ds.undo) return undo(q(ds.undo));
    if (ds.later) return later(q(ds.later), true);
    if (ds.unlater) return later(q(ds.unlater), false);
    if (ds.close) return close(q(ds.close));
    if (ds.unclose) { setDraft(ds.unclose, {close: null}); return draw(true); }
    if (ds.reopen) return reopen(q(ds.reopen));
    if (ds.reply) { const d = draft(ds.reply); setDraft(ds.reply, {replyOpen: !(d.replyOpen || (d.reply || '').trim())}); return draw(true); }
    if (ds.unreply) { setDraft(ds.unreply, {reply: null, replyOpen: null}); return draw(true); }
    if (ds.link) { S.copied = ds.link; setTimeout(() => { S.copied = null; }, 3000); copy(location.href.split('#')[0] + '#questions/q-' + ds.link, 'Link'); return draw(true); }
    // asking the agent to file a task is a reply: it joins Send, Undo takes it out (#04)
    if (ds.askfile) { const on = (draft(ds.askfile).reply || '').trim() !== ASKFILE; setDraft(ds.askfile, {reply: on ? ASKFILE : null, replyOpen: null}); draw(true); if (on) ctx.toast('Asked the agent to file a task · goes with Send', {undo: () => { setDraft(ds.askfile, {reply: null}); draw(true); }}); return; }
    if (ds.task) return peek(t);
    if (ds.taskrun) return ctx.go('running', ds.taskrun);
    if (t.hasAttribute('data-peekclose')) return t.closest('.qpeek').remove();
    if (ds.copytext) return copy(ds.copytext, 'Command');
    if (ds.plan) return ctx.go('reference', ds.plan);
    if (ds.ev) { const el = root.querySelector(`[data-anchor-id="${CSS.escape(ds.ev)}"]:not(.qcard)`); if (el) { el.scrollIntoView({block: 'center', behavior: 'smooth'}); el.classList.add('qlit'); setTimeout(() => el.classList.remove('qlit'), 2000); } return; }
    if (ds.indoc) { S.open.add(ds.indoc); return jumpTo(ds.indoc, 'doc'); }
    if (ds.zoom) { const a = t.closest('.qzm').nextElementSibling, src = a && a.dataset.zfull; if (!src) return; const per = ctx.prefs.get('q:zoomPer', {}); per[src] = +ds.zoom; ctx.prefs.set('q:zoomPer', per); const img = t.closest('figure') && t.closest('figure').querySelector('img'); S.zoom = {src, cap: img ? img.alt : '', img: img && img.dataset.img, anchor: (t.closest('[data-anchor-id]') || {}).dataset?.anchorId, z: +ds.zoom}; return draw(true); }
    if (ds.zoomto) { S.zoom.z = +ds.zoomto; const per = ctx.prefs.get('q:zoomPer', {}); per[S.zoom.src] = +ds.zoomto; ctx.prefs.set('q:zoomPer', per); return draw(true); }
    if (t.hasAttribute('data-zclose')) { S.zoom = null; return draw(true); }
    if (t.hasAttribute('data-zimg') && S.zoom && S.zoom.anchor) { const r = t.getBoundingClientRect(); S.note = {anchor: S.zoom.anchor, label: cut(S.zoom.cap, 60), target: {schema: 1, tag: 'img', offset: {dx: +((e.clientX - r.left) / r.width).toFixed(3), dy: +((e.clientY - r.top) / r.height).toFixed(3)}, css: 'img:nth-of-type(1)', image: S.zoom.img || null, image_src: S.zoom.src}}; S.zoom = null; return draw(true).then(() => { const ta = root.querySelector('[data-newnote] textarea'); if (ta) { ta.scrollIntoView({block: 'center'}); ta.focus({preventScroll: true}); } }); }
    if (t.hasAttribute('data-genopen')) { S.gen = !S.gen; return draw(true).then(() => { const ta = root.querySelector('.qgen textarea'); if (ta) ta.focus(); }); }
    if (t.hasAttribute('data-genclose')) { S.gen = false; return draw(true); }
    if (t.hasAttribute('data-ungen')) { const g = gen(); ctx.prefs.set('q:general', ''); S.gen = false; draw(true); return ctx.toast('General feedback removed', {undo: () => { ctx.prefs.set('q:general', g); draw(true); }}); }
    if (t.hasAttribute('data-sendopen')) { S.armed = !S.armed; S.sendKey = false; S.gen = false; return draw(true); }
    if (t.hasAttribute('data-sendclose')) { S.armed = false; S.sendKey = false; return draw(true); }
    if (t.hasAttribute('data-send')) return send();
    if (t.hasAttribute('data-discard')) return discardAll();
    if (ds.sgo) return sendGo(ds.sgo);
    if (ds.srm) return sendRemove(ds.srm);
    if (t.hasAttribute('data-sendundo')) { clearTimeout(S.pending.timer); S.pending = null; ctx.toast('Send undone: nothing left this page'); return draw(true); }
    if (t.hasAttribute('data-nadd')) return addNote(root.querySelector('[data-newnote] textarea').value);
    if (t.hasAttribute('data-ncancel')) { S.note = null; ctx.prefs.set('q:newnote', null); return draw(true); }
    if (ds.nedit) { S.note = {edit: ds.nedit}; return draw(true); }
    if (ds.nfix) { const n = D.notes.find(x => x.id === ds.nfix); if (!n) return; S.note = {anchor: n.anchor, label: n.label, target: n.target || {schema: 1, tag: 'p'}, text: n.text, fixOf: n.id}; ctx.prefs.set('q:newnote', S.note); return draw(true).then(() => { const ta = root.querySelector('[data-newnote] textarea'); if (ta) ta.focus({preventScroll: true}); }); }
    if (ds.nsave) return saveNote(ds.nsave, t.closest('.qnote').querySelector('textarea').value);
    if (ds.ndel) return delNote(ds.ndel);
    if (ds.ncopy) return copy((D.notes.find(x => x.id === ds.ncopy) || {}).text || '', 'Note');
    if (ds.nlink) return copy(location.href.split('#')[0] + '#questions/n-' + ds.nlink, 'Link');
    if (ds.carried) { const [id, st] = ds.carried.split('~'); return carried(id, st); }
    // a note: tap a picture spot, select words, or click a line, row or item of the document
    if (S.view !== 'doc' || t.closest('.qcard,.qnote,.qbar,.qsend,.qzm,.qdoch,.qtiles,.qrows,figcaption,summary')) return;
    const img = e.target.closest('img');
    const anchorEl = e.target.closest('[data-anchor-id]');
    if (!anchorEl || anchorEl.tagName === 'SECTION' && !img) return;
    const label = cut(anchorEl.textContent.trim() || (img && img.alt) || '', 60);
    let target;
    if (img) { const r = img.getBoundingClientRect(); target = {schema: 1, tag: 'img', offset: {dx: +((e.clientX - r.left) / r.width).toFixed(3), dy: +((e.clientY - r.top) / r.height).toFixed(3)}, css: 'img:nth-of-type(1)', image: img.dataset.img || null, image_src: img.dataset.full || img.getAttribute('src')}; }
    else { const sel = String(getSelection() || '').trim(); target = sel && anchorEl.contains(getSelection().anchorNode) ? {schema: 1, tag: anchorEl.tagName.toLowerCase(), quote: sel.slice(0, 300)} : {schema: 1, tag: anchorEl.tagName.toLowerCase()}; }
    S.note = {anchor: anchorEl.dataset.anchorId, label, target};
    ctx.prefs.set('q:newnote', S.note);
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
    else if (ds.replytext) { const was = hasReply(qOf(ds.replytext)); setDraft(ds.replytext, {reply: t.value, replyOpen: true}); if (was !== hasReply(qOf(ds.replytext))) updateBar(); }
    else if (t.hasAttribute('data-general')) { const was = !!gen().trim(); ctx.prefs.set('q:general', t.value); if (was !== !!t.value.trim() && !S.armed) updateBar(); }
    else if (t.hasAttribute('data-notetext') && t.closest('[data-newnote]') && S.note) { S.note.text = t.value; ctx.prefs.set('q:newnote', S.note); }  // an unsaved note survives a reload (#08)
  }
  function updateBar() {
    const b = root.querySelector('.qbar'); if (!b) return;
    const tmp = document.createElement('div'); tmp.innerHTML = bar(); b.replaceWith(tmp.querySelector('.qbar'));
    if (ctx.refreshTop) ctx.refreshTop();
  }
  function onKey(e) {
    if (!root || !root.isConnected || !root.classList.contains('tab-questions')) return;
    if (e.key === 'Escape') {  // closes the picture, the Send summary (drafts kept) or General feedback (#06)
      if (S.zoom || S.armed || S.gen) { e.preventDefault(); S.zoom = null; S.armed = false; S.sendKey = false; S.gen = false; draw(true); }
      return;
    }
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      const nt = e.target.closest && e.target.closest('.qnote');
      if (nt) return nt.hasAttribute('data-newnote') ? addNote(nt.querySelector('textarea').value) : saveNote(nt.dataset.note, nt.querySelector('textarea').value);
      return arm();
    }
    // F and A step through waiting questions, 1-9 picks on the highlighted one, C writes words on it (#05)
    if (/TEXTAREA|INPUT|SELECT/.test(e.target.tagName) || e.target.isContentEditable || e.metaKey || e.ctrlKey || e.altKey || S.armed || S.zoom || !D) return;
    const order = D.questions.filter(q => FILTERS[S.view === 'list' ? S.filter : 'need'](q)), wait = order.filter(isWaiting);
    const k = order.findIndex(q => q.id === S.hl);
    if (e.key === 'f' || e.key === 'a') {
      const f = e.key === 'f', nx = k < 0 ? wait[0] : f ? order.slice(k + 1).find(isWaiting) : order.slice(0, k).reverse().find(isWaiting);
      if (!nx) return;
      e.preventDefault(); jumpTo(nx.id);
    } else if (/^[1-9]$/.test(e.key) && S.hl) {
      const q = qOf(S.hl), o = q && !q.closed && !q.sent && q.options[+e.key - 1];
      if (!o) return;
      e.preventDefault(); setDraft(q.id, {pick: o.id});
      const nx = order.slice(order.findIndex(x => x.id === q.id) + 1).find(isWaiting);
      if (nx) jumpTo(nx.id); else draw(true);
    } else if (e.key === 'c' && S.hl) {
      const ta = root.querySelector(`[data-words="${CSS.escape(S.hl)}"]`); if (ta) { e.preventDefault(); ta.focus(); }
    }
  }
  function onChange(e) {
    const t = e.target, ds = t.dataset;
    if (ds.words && isDraft(qOf(ds.words)) && S.view === 'doc') return draw(true);  // a typed answer folds its card when the box is left
    if (t.hasAttribute('data-secjump') && t.value) {
      const el = DOC && DOC.querySelector(`[data-anchor-id="${CSS.escape(t.value)}"]`), sec = el && (el.closest('section.qsec'));
      if (sec && !secOpen(sec)) { const k = 'd:' + sec.dataset.anchorId; S.open.has(k) ? S.open.delete(k) : S.open.add(k); }
      const a = t.value;
      return draw(true).then(() => { const x = root.querySelector(`[data-anchor-id="${CSS.escape(a)}"]`); if (x) { x.scrollIntoView({block: 'start'}); x.classList.add('qlit'); setTimeout(() => x.classList.remove('qlit'), 2000); } });
    }
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
    chip: async c => {
      ctx = ctx || c; D = D || await c.data('questions');
      const n = waitingCount(), later = D.questions.filter(FILTERS.later).length;
      if (n) return {text: `${n} waiting`, tone: 'red', title: pl(n, 'question waits', 'questions wait') + ' for your answer'};
      return later ? {text: `${later} later`, title: pl(later, 'question', 'questions') + ' set aside to answer later'} : null;
    },
    render: async (el, c, anchor) => {
      ctx = c; root = el;
      S.view = S.view || ctx.prefs.get('q:view', 'doc');
      el.innerHTML = '<p class="mut">Loading the questions…</p>';
      D = await c.data('questions');
      if (!REF) c.data('reference').then(r => { REF = r; if (root && root.isConnected && root.classList.contains('tab-questions')) draw(true); }).catch(() => { REF = {}; });
      if (!S.note && ctx.prefs.get('q:newnote', null)) S.note = ctx.prefs.get('q:newnote', null);  // the note he was typing before a reload
      if (anchor && anchor.startsWith('q-')) { const id = anchor.slice(2), q = qOf(id); if (q) { S.shut.delete(id); if (isDone(q)) S.open.add(id); S.hl = id; } }
      el.onclick = onClick; el.oninput = onInput; el.onchange = onChange;
      await draw();
    },
  });
  const load = async c => { ctx = ctx || c; D = D || await c.data('questions'); };
  P.send({
    count: async c => { await load(c); return sendCount(); },
    waiting: async c => { await load(c); return waitingCount(); },  // the top bar and Home read this page's waiting from here
    open: c => { S.armed = true; S.gen = false; if (root && root.isConnected && root.classList.contains('tab-questions')) draw(true); else c.go('questions'); },
  });
  // shortcut: exposed for tests in a browser console only
  P.questionsState = () => ({S, D});
})();
