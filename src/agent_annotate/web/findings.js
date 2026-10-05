// ── The Findings tab (audits and recommendations) ───────────────────────
// Findings are decision cards in the page's one comment store (category
// "findings", grouped by set). A finding stays in this register until it is
// done, under the rail's own section words (Needs you · Ready to send ·
// Waiting on agent · Done), so an agreed fix cannot scroll away the way
// resolved cards do in a review.
//
// Chang: an agent "can mark it fixed on its own - it just needs to have
// proof as anywhere else". The agent marks a finding fixed with proof
// (`annotate finding SLUG --fixed N --proof …`; the server refuses a browser
// fix); the proof shows on the finding; the reviewer can reopen it, and the
// reopen goes out with the one Send.
(function () {
  'use strict';
  const AA = window.AA, UI = window.AAUI, D = () => window.AnnotateDocs;
  const $ = (s) => document.querySelector(s);
  const esc = UI.esc;
  let F = [], BY = {}, SETS = {}, SET_ORDER = [];
  let selected = null, changing = false, reopening = false, shown = false, busy = false;
  // Unsaved text per finding, kept in this browser until it is saved (UI-8,
  // UI-9, UI-12): the comment box and the reopen note. A finding with a
  // reopen note in progress keeps its reopen form open.
  const drafts = { compose: UI.local.get('find:drafts', {}), reopen: UI.local.get('find:reopen-drafts', {}) };
  const DRAFT_KEY = { compose: 'find:drafts', reopen: 'find:reopen-drafts' };
  function setDraft(kind, id, text) {
    if (text) drafts[kind][id] = text; else delete drafts[kind][id];
    UI.local.set(DRAFT_KEY[kind], drafts[kind]);
  }

  // ── The store's findings ────────────────────────────────────────────────
  function load() {
    const d = D();
    if (!d || !d.categories()) return;
    const cats = d.categories();
    SET_ORDER = (cats.findings_sets || []).map(s => s.id);
    SETS = {};
    (cats.findings_sets || []).forEach(s => { SETS[s.id] = s; });
    const all = d.comments(false).filter(c => d.commentCategory(c) === 'findings');
    F = all.filter(c => c.finding && c.decision_request);
    F.forEach(f => { if (!SETS[f.finding.set]) { SETS[f.finding.set] = { id: f.finding.set, label: f.finding.set }; SET_ORDER.push(f.finding.set); } });
    F.sort((a, b) => SET_ORDER.indexOf(a.finding.set) - SET_ORDER.indexOf(b.finding.set) || (a.number || 0) - (b.number || 0));
    BY = {};
    F.forEach(f => { BY[f.id] = f; });
    if (!selected || !BY[selected]) selected = (UI.local.get('find:selected', null) in BY) ? UI.local.get('find:selected', null) : (F[0] && F[0].id);
  }
  // A reviewer's comments on a finding: plain comments on its anchor.
  const commentsOf = (f) => D().comments(false).filter(c => c.anchor_id === f.anchor_id && !c.decision_request);
  // A finding's short name: its set's item label and number ("Gap 3").
  const tag = (f) => ((SETS[f.finding.set] && SETS[f.finding.set].item_label) || 'Finding') + ' ' + (f.number || '');
  const titleOf = (f) => f.finding.title || D().displayPrompt(f);
  function optionOf(f, choice) {
    const opts = (f.decision_request.options || []).filter(o => o && typeof o === 'object');
    return opts.find(o => o.id === choice) || opts.find(o => o.label === choice) || null;
  }
  function answerOf(f) {
    const d = f.decision;
    if (d && d.verdict) {
      const label = D().answerLabel(f).text;
      const o = optionOf(f, d.option_id || d.option || label);
      return { label, ts: d.ts, fix: !(o && (o.id === 'keep' || o.id === 'no')) && d.verdict !== 'reject', pending: !!d.round_pending };
    }
    // A reopen moves the verdict to decision_history (it must not answer the
    // reopened question for the agent); the reviewer still sees their answer.
    const prev = (f.reopened || []).length ? (f.decision_history || []).filter(x => x && x.verdict).slice(-1)[0] : null;
    if (prev) {
      const label = D().answerLabel(Object.assign({}, f, { decision: prev })).text;
      const o = optionOf(f, prev.option_id || prev.option || label);
      return { label, ts: prev.ts, fix: !(o && (o.id === 'keep' || o.id === 'no')) && prev.verdict !== 'reject', pending: false };
    }
    if (f.response_text) {
      const yes = optionOf(f, 'yes') || optionOf(f, 'fix');
      return { label: yes ? yes.label : 'Agreed', ts: null, fix: true, note: f.response_text };
    }
    return null;
  }
  // The agent's latest "fixed" post (the current one, or the one reopened).
  const fixOf = (f) => f.fixed || null;
  const lastFixOf = (f) => f.fixed || (f.fixed_history || []).slice(-1)[0] || null;
  function reopenOf(f) {
    if (f.fixed) return null;
    const r = (f.reopened || []).slice(-1)[0];
    const fx = lastFixOf(f);
    return r && fx && r.ts >= fx.ts ? r : null;
  }
  // The server's own section rule (categories.comment_section), so the
  // register, the rail and the header count always agree.
  function statusOf(f) {
    const d = f.decision || {};
    if (f.round_pending || (d.round_pending && f.status !== 'resolved_in_version')) return 'ready';
    if (f.fixed) return 'done';
    if (!d.verdict) return f.reopened && f.reopened.length || f.response_text ? 'waiting' : 'needs';
    let choice = d.option_id || d.option;
    if (choice == null && d.verdict === 'select') choice = d.text;
    const o = optionOf(f, choice);
    if (o) choice = o.id;
    return choice === 'keep' || choice === 'no' || d.verdict === 'reject' ? 'done' : 'waiting';
  }
  function pendingItems() {
    const d = D(), out = [];
    F.forEach(f => {
      const label = tag(f) + ' · ' + titleOf(f);
      if (d.isRoundPending(f)) out.push({ item: f.id, label, answer: D().answerLabel(f).text, kind: 'round' });
      if (d.isReopenPending(f)) {
        const r = (f.reopened || []).slice(-1)[0];
        out.push({ item: f.id, label, answer: 'Reopened' + (r && r.text ? ': ' + r.text.split('\n')[0].slice(0, 60) : ''), kind: 'round' });
      }
      // UI-5: a finding with an answer or reply the agent has not had yet
      // (answered outside a Send) goes with the push, so it is listed too.
      if (d.needsPush(f)) {
        const reply = (f.replies || []).filter(r => !String(r.author || '').startsWith('agent:')).slice(-1)[0];
        out.push({ item: f.id, label, answer: d.decisionAnswer(f) ? d.answerLabel(f).text : 'Comment: ' + String(reply ? reply.text : f.text || '').split('\n')[0].slice(0, 60), kind: 'push' });
      }
      commentsOf(f).filter(c => d.needsPush(c)).forEach(c => out.push({ item: f.id, label, answer: 'Comment: ' + c.text.split('\n')[0].slice(0, 60), kind: 'push' }));
    });
    return out;
  }
  // Unread here means a "fixed" post this viewer has not opened yet.
  const unreadOf = (f) => !!f.fixed && D().readStateOf(f) !== 'read';
  // The card's context, and the evidence the agent quoted after a blank line.
  function contextParts(f) {
    const raw = String(f.decision_request.context || '').replace(/\s*Crops: https?:\S+/, '').trim();
    const at = raw.indexOf('\n\n');
    return at === -1 ? { ctx: raw, evidence: '' } : { ctx: raw.slice(0, at).trim(), evidence: raw.slice(at + 2).trim() };
  }

  // ── Register: a document, in the Review document's own styles ───────────
  const SECTIONS = [
    { key: 'needs', label: 'Needs you', badge: 'badge-error', cls: 'sec-needs' },
    { key: 'ready', label: 'Ready to send', badge: 'badge-primary' },
    { key: 'waiting', label: 'Waiting on agent' },
    { key: 'done', label: 'Done', open: false },
  ];
  const STATUS_WORD = { needs: 'Needs you', ready: 'Ready to send', waiting: 'Waiting on agent', done: 'Done' };
  function statusChip(f, st) {
    if (st === 'done' && fixOf(f)) return '<span class="chip">Fixed · proof attached</span>';
    if (st === 'waiting' && reopenOf(f)) return '<span class="chip">Reopened · waiting on agent</span>';
    return `<span class="chip${st === 'needs' ? ' blocking' : ''}">${esc(STATUS_WORD[st])}</span>`;
  }
  function renderRegister() {
    const count = (k) => F.filter(f => statusOf(f) === k).length;
    const fixed = F.filter(f => statusOf(f) === 'done' && fixOf(f)).length;
    let html = `<div class="plan-scope"><strong>Findings</strong> · kept here until each one is done</div>
      <div class="kpis"><div class="kpi${count('needs') ? ' bad' : ''}"><b>${count('needs')}</b><span>need you</span></div>
      <div class="kpi"><b>${count('ready')}</b><span>ready to send</span></div>
      <div class="kpi warn"><b>${count('waiting')}</b><span>waiting on agent (agreed, not done yet)</span></div>
      <div class="kpi ok"><b>${count('done')}</b><span>done${fixed ? ' (' + fixed + ' fixed, with proof)' : ''}</span></div></div>`;
    SET_ORDER.forEach(id => {
      const set = SETS[id];
      const rows = F.filter(f => f.finding.set === id);
      if (!rows.length) return;
      html += `<section id="set-${esc(id)}"><h2>${esc(set.label)}</h2>
        ${set.intro ? `<p>${esc(set.intro)}</p>` : ''}
        <p class="muted">${set.created_at ? 'Posted ' + esc(UI.fmtTs(set.created_at)) + ' · ' : ''}${rows.length} findings</p>
        <div class="wrap"><table><thead><tr><th>#</th><th>Finding</th><th>Your answer</th><th>Status</th></tr></thead><tbody>${rows.map(f => {
          const a = answerOf(f), st = statusOf(f);
          return `<tr data-f="${esc(f.id)}" data-anchor-id="${esc(f.anchor_id)}" tabindex="0"${f.id === selected ? ' class="sp-sel"' : ''}><td>${esc(f.number || '')}</td><td>${unreadOf(f) ? '<span class="unread-dot" role="img" aria-label="Unread" title="Marked fixed since you last looked"></span> ' : ''}${esc(titleOf(f))}</td><td>${a ? esc(a.label) : '—'}</td><td>${statusChip(f, st)}</td></tr>`;
        }).join('')}</tbody></table></div></section>`;
    });
    if (!F.length) html += '<p class="muted">No findings yet.</p>';
    const root = $('#find-register');
    root.innerHTML = html;
    root.querySelectorAll('tr[data-f]').forEach(r => {
      r.addEventListener('click', () => select(r.dataset.f, true));
      r.addEventListener('keydown', (e) => { if (e.key === 'Enter') select(r.dataset.f, true); });
    });
  }

  // ── Rail: every finding as a card under the rail's sections ─────────────
  function optionsHtml(f, chosenLabel) {
    const rec = f.decision_request.recommendation;
    return `<div class="decision-btns has-consequences">${(f.decision_request.options || []).filter(o => o && typeof o === 'object').map(o => `<button class="btn decision-btn decision-custom${o.id === rec ? ' is-recommended' : ''}" data-opt="${esc(o.id)}" aria-pressed="${o.label === chosenLabel}"${busy ? ' disabled' : ''}><span class="decision-opt-head"><span class="decision-opt-label">${o.label === chosenLabel ? '☑ ' : ''}${esc(o.label)}</span>${o.id === rec ? '<span class="badge badge-success badge-soft badge-xs decision-rec-badge">Recommended</span>' : ''}</span>${o.consequence ? `<span class="decision-consequence">${esc(o.consequence)}</span>` : ''}</button>`).join('')}</div>`;
  }
  function lineCard(f) {
    const a = answerOf(f), fx = statusOf(f) === 'done' && fixOf(f);
    const unread = unreadOf(f) ? '<span class="unread-dot" role="img" aria-label="Unread" title="Marked fixed since you last looked"></span>' : '';
    return `<div class="citem is-line${unread ? ' is-unread' : ''}" data-card="${esc(f.id)}" tabindex="0" role="group" aria-label="${esc(tag(f) + ' · ' + titleOf(f))}"><div class="citem-line">${unread}<span class="citem-num">${esc(tag(f))}</span><span class="citem-line-txt"><span class="citem-line-q">${esc(titleOf(f))}</span>${fx ? '<span class="citem-line-arrow">→</span><span class="ans">Fixed</span>' : a ? `<span class="citem-line-arrow">→</span><span class="ans">${esc(a.label)}</span>` : ''}</span></div></div>`;
  }
  const IMG = /\.(png|jpe?g|gif|webp|avif|svg)(\?|#|$)/i;
  const WEB = /^https?:\/\//i;
  function proofUrl(p) { return p.attachment ? './attachments/' + encodeURIComponent(p.attachment) : p.url; }
  // UI-1: an agent's attachment never opens as a page on this origin. An
  // image shows as an <img> only (no click-through); any other attachment
  // downloads. A proof URL on another site stays a plain link.
  function proofLink(p) {
    if (p.attachment) return `<a href="${esc(proofUrl(p))}" download="${esc(p.attachment)}">${esc(p.label)}</a>`;
    if (WEB.test(p.url || '')) return `<a href="${esc(p.url)}" target="_blank" rel="noopener noreferrer">${esc(p.label)} ${UI.ico('external')}</a>`;
    return `<span>${esc(p.label)}</span>`;
  }
  function proofHtml(fx) {
    const proof = fx.proof || [];
    const imgs = proof.filter(p => IMG.test(p.attachment || p.url || '') && (p.attachment || WEB.test(p.url || '')));
    const links = proof.filter(p => !imgs.includes(p));
    return `<div class="fix-proof" data-proof-count="${proof.length}">
      ${imgs.map(p => `<figure class="fix-proof-img"><img src="${esc(proofUrl(p))}" alt="${esc(p.label)}" loading="lazy"><figcaption>${UI.ico('image')} ${esc(p.label)}</figcaption></figure>`).join('')}
      ${links.length ? `<ul class="doc-list fix-proof-links">${links.map(p => `<li>${proofLink(p)}${p.detail ? `<span class="project-detail">${esc(p.detail)}</span>` : ''}</li>`).join('')}</ul>` : ''}
    </div>`;
  }
  function fixBlock(f) {
    const r = reopenOf(f);
    const fx = r ? lastFixOf(f) : fixOf(f);
    if (!fx) return '';
    const d = D();
    const head = `<div class="fix-head"><span class="badge badge-sm badge-soft badge-success">Marked fixed</span><span class="citem-author">${esc(d.whoName({ by: fx.by }))}</span><span>${esc(UI.fmtTs(fx.ts))}</span></div>`;
    let action = '';
    if (r) {
      action = `<div class="citem-meta"><span>${esc(d.whoName({ by: r.by }))} reopened it · ${esc(UI.fmtTs(r.ts))} · ${f.round_pending ? 'goes out with Send' : 'sent; waiting on agent'}</span></div>${r.text ? `<div class="citem-txt">${esc(r.text)}</div>` : ''}`;
    } else if (reopening || drafts.reopen[f.id]) {
      action = `<textarea class="textarea decision-say-ta" id="f-reopen-ta" placeholder="What is still wrong? (optional)" rows="2" aria-label="Why reopen ${esc(tag(f))}" data-submit="#f-reopen-save">${esc(drafts.reopen[f.id] || '')}</textarea>
        <div class="gf-ft"><span class="gf-hint">Goes out with Send</span><button type="button" class="btn btn-ghost btn-xs" id="f-reopen-cancel">Cancel</button><button type="button" class="btn btn-xs" id="f-reopen-save">Reopen</button></div>`;
    } else {
      action = `<div class="fix-actions"><button type="button" class="btn btn-sm" id="f-reopen">${UI.ico('rotate')} Reopen</button><span class="gf-hint">Not fixed? Reopen it with a note; it goes back to the agent with Send.</span></div>`;
    }
    return `<div class="fix-block${r ? ' is-reopened' : ''}">${head}${fx.note ? `<div class="citem-txt">${esc(fx.note)}</div>` : ''}${proofHtml(fx)}${action}</div>`;
  }
  function fullCard(f) {
    const d = D();
    const a = answerOf(f), st = statusOf(f);
    const { ctx, evidence } = contextParts(f);
    const answer = a && !changing
      ? `<div class="citem is-line"><div class="citem-line"><span class="citem-line-txt"><span class="citem-line-q">${esc(titleOf(f))}</span><span class="citem-line-arrow">→</span><span class="ans">${esc(a.label)}</span></span>${f.decision_request ? `<button type="button" class="btn btn-ghost btn-xs btn-square change-btn" id="f-change" aria-label="Change answer to ${esc(tag(f))}" title="Change">${UI.ico('pencil')}</button>` : ''}</div></div>`
      : optionsHtml(f, a && a.label);
    const fx = fixOf(f) || reopenOf(f);
    const note = fx ? '' : st === 'waiting' ? (a && a.note ? a.note + ' Not marked built yet.' : 'Agreed; not fixed yet. It stays here until the agent marks it fixed, with proof.') : st === 'done' ? 'No change.' : st === 'ready' ? 'Goes out with Send.' : '';
    const comments = commentsOf(f).map(c => `<div class="citem-meta"><span class="citem-author">${esc(d.whoName(c))}</span><span>${esc(UI.fmtTs(c.created_at))}${d.needsPush(c) ? ' · ready to send' : ''}</span></div><div class="citem-txt">${esc(c.text)}</div>`).join('');
    return `<div class="citem hl${st === 'needs' ? ' decision-required' : ''}" data-card="${esc(f.id)}" role="group" aria-label="${esc(tag(f) + ' · ' + titleOf(f))}">
      <div class="citem-node"><span class="citem-node-name"><span class="citem-num">${esc(tag(f))}</span></span><span class="citem-kbd"><kbd class="kbd kbd-xs" title="Previous finding">A</kbd><kbd class="kbd kbd-xs" title="Next finding">F</kbd></span></div>
      <div class="citem-meta"><span class="citem-author">${esc(d.whoName(f))}</span><span>${esc(UI.fmtTs(f.created_at))}</span></div>
      <div class="decision-block"><div class="decision-prompt">${d.ticketsHTML(titleOf(f))}</div>
      ${ctx ? `<div class="decision-context">${d.ticketsHTML(ctx)}</div>` : ''}
      ${evidence ? `<figure class="decision-excerpt"><figcaption class="decision-excerpt-src">${esc(tag(f))} evidence</figcaption><blockquote class="decision-excerpt-text">${esc(evidence)}</blockquote></figure>` : ''}
      ${answer}${note ? `<div class="citem-meta"><span>${a && a.ts ? esc(UI.fmtTs(a.ts)) + ' · ' : ''}${esc(note)}</span></div>` : ''}
      <div class="decision-feedback" id="f-feedback"></div></div>
      ${fixBlock(f)}
      ${comments}
      <textarea class="textarea decision-say-ta" id="f-compose" placeholder="Comment (optional)" rows="2" aria-label="Comment on ${esc(tag(f))}" data-submit="#f-save">${esc(drafts.compose[f.id] || '')}</textarea>
      <div class="gf-ft"><span class="gf-hint">Goes out with Send</span><button type="button" class="btn btn-ghost btn-xs" id="f-save">Save</button></div></div>`;
  }
  function renderRail() {
    let html = '';
    SECTIONS.forEach(sec => {
      const rows = F.filter(f => statusOf(f) === sec.key);
      if (!rows.length) return;
      const open = sec.open === false ? rows.some(f => f.id === selected) : true;
      html += UI.section(sec.key, sec.label, rows.length, rows.map(f => f.id === selected ? fullCard(f) : lineCard(f)).join(''), { cls: sec.cls, badge: sec.badge || 'badge-ghost', open, scope: 'find' });
    });
    const rail = $('#rail-findings');
    // The boxes' text lives in the per-finding drafts, so a re-render keeps
    // it; keep the caret too when the reviewer was typing.
    const ae = document.activeElement;
    const typing = ae && (ae.id === 'f-compose' || ae.id === 'f-reopen-ta') && rail.contains(ae)
      ? { id: ae.id, start: ae.selectionStart, end: ae.selectionEnd } : null;
    rail.innerHTML = html || '<p class="project-detail rail-note">No findings yet.</p>';
    if (typing) {
      const el = document.getElementById(typing.id);
      if (el) { el.focus({ preventScroll: true }); try { el.setSelectionRange(typing.start, typing.end); } catch {} }
    }
    UI.wireSections(rail);
    const f = BY[selected];
    const keep = (id, kind) => { const el = document.getElementById(id); if (el && f) el.addEventListener('input', () => setDraft(kind, f.id, el.value)); };
    keep('f-compose', 'compose');
    keep('f-reopen-ta', 'reopen');
    rail.querySelectorAll('.citem.is-line[data-card]').forEach(el => {
      el.addEventListener('click', () => select(el.dataset.card, false));
      el.addEventListener('keydown', (e) => { if (e.key === 'Enter') select(el.dataset.card, false); });
    });
    const on = (id, fn) => { const el = document.getElementById(id); if (el) el.addEventListener('click', fn); };
    const fail = (msg) => { const el = $('#f-feedback'); if (el) { el.textContent = msg; el.classList.add('is-error'); } };
    on('f-change', () => { changing = true; renderRail(); });
    rail.querySelectorAll('[data-opt]').forEach(b => b.addEventListener('click', async () => {
      const o = optionOf(f, b.dataset.opt);
      busy = true;
      const v = D().selectVerdictId();
      const r = await D().decide(f.id, v, v === 'select' ? o.label : 'Selected: ' + o.label);
      busy = false;
      if (!r || r.fallback) { fail('Failed to send — try again.'); return; }
      changing = false;
      await D().refreshStore();
    }));
    on('f-save', async () => {
      const t = $('#f-compose').value.trim(); if (!t) return;
      const c = await D().createComment(f.anchor_id, tag(f) + ' · ' + titleOf(f), t, f.version, null, { category: 'findings' });
      if (!c) { fail('Failed to save — try again.'); return; }
      setDraft('compose', f.id, '');
      const box = $('#f-compose'); if (box) box.value = '';
      await D().refreshStore();
    });
    on('f-reopen', () => { reopening = true; renderRail(); const ta = $('#f-reopen-ta'); if (ta) ta.focus(); });
    on('f-reopen-cancel', () => { reopening = false; setDraft('reopen', f.id, ''); renderRail(); });
    on('f-reopen-save', async () => {
      const text = $('#f-reopen-ta').value.trim() || 'Reopened';
      try { await UI.api('./api/comments/' + encodeURIComponent(f.id) + '/reopen', { text }); }
      catch { fail('Failed to reopen — try again.'); return; }
      reopening = false;
      setDraft('reopen', f.id, '');
      await D().refreshStore();
    });
    const sel = rail.querySelector('.citem.hl');
    if (sel && !rail.hidden) sel.scrollIntoView({ block: 'nearest' });
    if (AA.rail.tab === 'history') AA.rail.renderHistory();
  }
  function renderHistory(el) {
    const f = BY[selected];
    if (!f || !el) { if (el) el.innerHTML = ''; return; }
    const d = D();
    const who = (a) => esc(d.whoName({ by: a }));
    const e = [{ ts: f.created_at, html: `<b>${esc(d.whoName(f))}</b> · posted in ${esc(SETS[f.finding.set].label)}`, text: titleOf(f) }];
    // final/: the first, sent answer reads "answered"; every later answer,
    // and any answer not sent yet, reads "changed the answer · sent | not
    // sent yet" (final/app/findings.js:235-238).
    // A discarded answer (UI-14) never went out; History leaves it out.
    (f.decision_history || []).concat(f.decision ? [f.decision] : []).filter(x => x && x.verdict && !x.discarded).forEach((x, i) => {
      const what = i === 0 && !x.round_pending ? 'answered' : 'changed the answer · ' + (x.round_pending ? 'not sent yet' : 'sent');
      e.push({ ts: x.ts, html: `<b>${who(x.by)}</b> · ${what}`, text: x.verdict === 'select' ? String(x.text || '').replace(/^Selected:\s*/, '') : (x.text || x.verdict) });
    });
    if (f.response_text) e.push({ ts: f.created_at, html: `<b>${esc(d.whoName(f))}</b> · resolved in ${esc(f.resolved_in_version || 'v1')}`, text: f.response_text });
    (f.fixed_history || []).concat(f.fixed ? [f.fixed] : []).forEach(fx => e.push({ ts: fx.ts, html: `<b>${who(fx.by)}</b> · marked fixed, with ${(fx.proof || []).length} proof item${(fx.proof || []).length === 1 ? '' : 's'}`, text: fx.note || '' }));
    (f.reopened || []).forEach((r, i, all) => e.push({ ts: r.ts, html: `<b>${who(r.by)}</b> · reopened · ${i === all.length - 1 && f.round_pending ? 'not sent yet' : 'sent'}`, text: r.text || '' }));
    commentsOf(f).forEach(c => e.push({ ts: c.created_at, html: `<b>${esc(d.whoName(c))}</b> · comment · ${d.needsPush(c) ? 'not sent yet' : 'sent'}`, text: c.text }));
    e.sort((x, y) => (x.ts < y.ts ? 1 : -1));
    el.innerHTML = `<p class="project-detail hist-sub">${esc(tag(f) + ' · ' + titleOf(f))}</p>` + e.map(h => `<div class="hist-item"><div class="hist-head">${h.html}<span>· ${esc(UI.fmtTs(h.ts))}</span></div><div class="hist-text">${esc(h.text)}</div></div>`).join('');
  }

  function select(id, user) {
    if (!BY[id]) return;
    selected = id; changing = false; reopening = false;
    UI.local.set('find:selected', id);
    D().markRead([BY[id]]);
    renderAll();
    AA.changed();
    if (user) {
      history.replaceState(null, '', '#view=findings&set=' + BY[id].finding.set + '&f=' + id);
      // Phone: the finding's card is in the rail (the bottom sheet).
      if (D().isMobileLayout()) AA.rail.reveal();
    }
  }
  function renderAll() { renderRegister(); renderRail(); }
  function applyHash(h) {
    const set = h.get('set');
    if (set && set !== 'all' && SETS[set] && !h.get('f')) { const first = F.find(f => f.finding.set === set); if (first) selected = first.id; }
    if (h.get('f') && BY[h.get('f')]) selected = h.get('f');
    changing = h.get('change') === '1';
    reopening = h.get('reopen') === '1';
    if (BY[selected]) D().markRead([BY[selected]]);
    renderAll();
    if (h.get('tab')) AA.rail.setTab(h.get('tab'));
    if (h.get('f') && h.get('sheet') === 'open') AA.rail.reveal();
    const scroller = $('#find-scroll');
    if (set && set !== 'all') { const sec = document.getElementById('set-' + set); if (sec) sec.scrollIntoView({ block: 'start' }); }
    else if (scroller && !h.get('f')) scroller.scrollTop = 0;
    const row = document.querySelector('#find-register tr.sp-sel'); if (row && h.get('f')) row.scrollIntoView({ block: 'nearest' });
  }
  // A previous / F next finding, in the rail's order (E3).
  function shortcut(e) {
    if (UI.isTyping(e.target)) return;
    const k = e.key.toLowerCase();
    if (k === 'a' || k === 'f') {
      const order = SECTIONS.flatMap(sec => F.filter(f => statusOf(f) === sec.key).map(f => f.id));
      if (!order.length) return;
      e.preventDefault();
      let i = order.indexOf(selected);
      i = i === -1 ? 0 : Math.max(0, Math.min(order.length - 1, i + (k === 'f' ? 1 : -1)));
      select(order[i], false);
      return;
    }
    if (/^[1-9]$/.test(e.key)) {
      const btn = document.querySelectorAll('#rail-findings .citem.hl [data-opt]')[Number(e.key) - 1];
      if (btn) { e.preventDefault(); btn.click(); }
    }
  }

  // ── The tab's part of the page ─────────────────────────────────────────
  document.addEventListener('annotate:store', () => { load(); if (shown) renderAll(); });
  AA.provider('findings', {
    pending: () => { load(); return pendingItems(); },
    afterSend() { load(); if (shown) renderAll(); },
    async show(h) { load(); shown = true; applyHash(h); },
    hide() { shown = false; },
    history(el) { load(); renderHistory(el); },
    shortcut,
  });
})();
