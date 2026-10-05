// ── The Library tab (copy and policies) ────────────────────────────────
// Library items are the page's copy blocks (./api/copy): each with its key,
// place, group, status, alternatives and immutable revisions (Quill Deltas).
// Each item is edited directly in the bundled Quill 2 editor, commented on
// (whole item or a selected phrase), and has its own History with Restore.
// A question about library items (#9) lives here only: in this tab's list,
// its rail and its History, never in Review's rail. Edits are saved as
// round-pending revisions, comments as page comments; both, and answers,
// go out with the one Send.
(function () {
  'use strict';
  const AA = window.AA, UI = window.AAUI, D = () => window.AnnotateDocs;
  const $ = (s) => document.querySelector(s);
  const esc = UI.esc;
  let DATA = null, ITEMS = [], BY_ID = {}, GROUPS = {}, GROUP_ORDER = [];
  let selected = null, quill = null, pendingQuote = null, pendingRange = null, query = '';
  const openGroups = UI.local.get('lib:groups', {});
  const drafts = UI.local.get('lib:drafts', {}); // unsaved editor text, per item
  const draftBases = UI.local.get('lib:draft-base', {}); // the revision each draft started from
  const commentDrafts = UI.local.get('lib:comment-drafts', {}); // unsaved comment text, per item
  const saveIntents = UI.local.get('lib:save-intent', {}); // one request id per save attempt, reused on retry
  let shown = false, loading = null;
  // The open editor: which item, which revision it started from, and whether
  // the newer-revision notice is showing (a later Save then replaces it).
  let editorItem = null, editorBase = null, staleSeen = null, saving = false, copySig = '';
  const STALE_NOTE = 'A newer version was saved while you were editing. Save replaces it with your text; Cancel loads the newer version.';
  const TOO_BIG_NOTE = 'Too long to save — shorten the text and try again.';

  // ── Data ───────────────────────────────────────────────────────────────
  async function loadCopy() {
    try { setData(await UI.api('./api/copy')); } catch (e) { console.warn('[annotate] copy', e); setData(DATA || { blocks: [], groups: [] }); }
    AA.changed();
  }
  function setData(data) {
    DATA = data;
    copySig = JSON.stringify(DATA);
    ITEMS = DATA.blocks || [];
    BY_ID = {};
    ITEMS.forEach(it => { BY_ID[it.id] = it; });
    GROUPS = {};
    GROUP_ORDER = [];
    (DATA.groups || []).forEach(g => { GROUPS[g.id] = g.label; GROUP_ORDER.push(g.id); });
    ITEMS.forEach(it => { if (it.group && !GROUPS[it.group]) { GROUPS[it.group] = it.group; GROUP_ORDER.push(it.group); } });
    if (ITEMS.some(it => !it.group)) { GROUPS[''] = 'Other copy'; GROUP_ORDER.push(''); }
    if (!selected || !BY_ID[selected]) {
      const s = UI.local.get('lib:selected', null);
      // As final/: the page's declared first item (start_item), when the copy
      // data names one; else the first item the question covers.
      const start = DATA.start_item && BY_ID[DATA.start_item] ? DATA.start_item : null;
      selected = s && BY_ID[s] ? s : start || (ITEMS.find(it => it.question_comment_id) || ITEMS[0] || {}).id || null;
    }
  }
  const me = () => { const i = D().identity(); return i ? (i.reviewer_authors || [i.email]) : []; };
  const plainOfDelta = (delta) => ((delta && delta.ops) || []).map(op => typeof op.insert === 'string' ? op.insert : '').join('').replace(/\n+$/, '');
  const latestRev = (it) => it.revisions[it.revisions.length - 1];
  const plainOf = (it) => plainOfDelta(latestRev(it).delta);
  const groupLabel = (it) => GROUPS[it.group || ''] || '';
  // final/ names an item without a row number by its title, else its place,
  // and shows its key in the key line. A block's title is its key when the
  // copy has no human title (a dotted identifier such as "policy.terms").
  const titleIsKey = (it) => /^[\w.:-]+$/.test(it.title || '') && /[._]/.test(it.title || '');
  const keyOf = (it) => titleIsKey(it) ? it.title : it.id;
  const nameOf = (it) => (!titleIsKey(it) && it.title) || String(it.where || it.title || it.id).replace(/^Store page · /, '');
  function labelOf(it) {
    if (it.number != null) return '#' + it.number + ' ' + (it.where || it.title);
    return nameOf(it) + ' · ' + groupLabel(it);
  }
  // The item's recorded history: the agent's seeded events, kept on an
  // archived comment of the item (target.seed_history).
  const seedRecord = (it) => D().comments(true).find(x => x.target && x.target.copy_block === it.id && Array.isArray(x.target.seed_history));
  function seedHistory(it) {
    const c = seedRecord(it);
    return c ? c.target.seed_history : [];
  }
  // The item's status in the copy page's own words: the latest history
  // status, else the imported record's status line, else the block status.
  function statusText(it) {
    const added = seedHistory(it).filter(h => h.status).slice(-1)[0];
    if (added) return added.status;
    const rec = seedRecord(it);
    if (rec && rec.text && it.status !== 'held') return rec.text;
    if (it.status === 'held') return 'held back: ' + (it.held_note || '');
    if (it.status === 'needs_you') return 'draft for your edit';
    if (it.status === 'done') return 'approved';
    return it.status || '';
  }
  const myPendingRevs = (it) => it.revisions.filter(r => r.round_pending && me().includes(r.author && r.author.id));
  const myRevs = (it) => it.revisions.filter(r => r.author && me().includes(r.author.id) && r.status === 'proposed');
  function seedComments(it) {
    // The agent's own "held back" reason, shown as the agent's note on the
    // phrase it is about.
    if (it.status !== 'held' || !it.held_note) return [];
    const reason = it.held_note;
    const q = /not '([^']+)'/.exec(reason) || /'([^']+)'/.exec(reason);
    const added = seedHistory(it).find(h => h.kind === 'added');
    return [{ id: 'agent-' + it.id, author: 'agent:claude', ts: added ? added.ts : '', text: 'Held back: ' + reason, quote: q ? q[1] : null, agent: true }];
  }
  // Reviewer and agent comments on the item (page comments on copy:<id>).
  function storedComments(it) {
    return D().comments(false).filter(c => c.anchor_id === 'copy:' + it.id && !c.decision_request && !(c.target && c.target.copy_revision))
      .map(c => ({ id: c.id, author: c.author, name: D().whoName(c), ts: c.created_at, text: c.text, quote: (c.target && c.target.selected_quote) || null, agent: String(c.author || '').startsWith('agent:'), comment: c }));
  }
  const commentsOf = (it) => seedComments(it).concat(storedComments(it));
  const question = (it) => it && it.question_comment_id ? D().findComment(it.question_comment_id) : null;
  function questionComment() {
    const ids = [...new Set(ITEMS.map(it => it.question_comment_id).filter(Boolean))];
    return ids.length ? D().findComment(ids[0]) : null;
  }
  const qAnswer = (q) => q && D().decisionAnswer(q) ? D().answerLabel(q).text : null;
  function pendingItems() {
    const d = D(), out = [];
    ITEMS.forEach(it => {
      if (myPendingRevs(it).length) out.push({ item: it.id, label: labelOf(it), answer: 'Edited' });
      storedComments(it).filter(c => !c.agent && d.needsPush(c.comment)).forEach(c => out.push({ item: it.id, label: labelOf(it) + (c.quote ? ' · “' + c.quote + '”' : ''), answer: 'Comment: ' + c.text.split('\n')[0].slice(0, 60) }));
    });
    const q = questionComment();
    if (q && d.isRoundPending(q)) out.push({ item: null, label: '#' + (d.number(q.id) || '') + ' ' + d.displayPrompt(q), answer: qAnswer(q) });
    return out;
  }
  const isPendingItem = (it) => pendingItems().some(p => p.item === it.id);
  const readKey = (it) => 'copy:' + it.id;
  const isUnread = (it) => { const r = D().readRecord(readKey(it)); return !r || r.sig !== latestRev(it).id; };
  // What counts as unread (as the server's Library count): the agent's note on
  // the item, or an agent revision after its first text.
  const hasAgentNews = (it) => !!seedComments(it).length ||
    (it.revisions.length > 1 && String((latestRev(it).author || {}).id || '').startsWith('agent:'));
  function markSeen(it) {
    if (it && isUnread(it)) D().markReadItems([{ id: readKey(it), sig: latestRev(it).id }]);
  }

  // ── Status words (the copy page's own) ─────────────────────────────────
  function chip(it) {
    if (myPendingRevs(it).length) return '<span class="badge badge-sm badge-soft badge-primary">Edited</span>';
    const s = statusText(it);
    if (/^held back/.test(s)) return '<span class="badge badge-sm badge-soft badge-warning">Held back</span>';
    if (/pending review/.test(s)) return '<span class="badge badge-sm badge-soft badge-info">Pending review</span>';
    if (/^not rendered/.test(s)) return '<span class="badge badge-sm badge-ghost">Not rendered</span>';
    if (/^approved/.test(s)) return '<span class="badge badge-sm badge-soft badge-success">Approved</span>';
    if (/^draft/.test(s)) return '<span class="badge badge-sm badge-soft badge-info">Draft</span>';
    return '';
  }

  // ── List ───────────────────────────────────────────────────────────────
  function rowHtml(it) {
    const num = it.number != null ? `<span class="citem-num">#${it.number}</span>` : '';
    const where = it.number != null ? it.where : nameOf(it);
    const unread = isUnread(it) && hasAgentNews(it) ? '<span class="unread-dot" title="You have not opened the agent\'s note on this item yet" role="img" aria-label="Unread"></span>' : '';
    return `<div class="citem sp-row${it.id === selected ? ' hl' : ''}${unread ? ' is-unread' : ''}" data-item="${esc(it.id)}" tabindex="0" role="button" aria-current="${it.id === selected ? 'true' : 'false'}"><div class="citem-node">${unread}<span class="citem-node-name">${num}${esc(where)}</span>${chip(it)}</div><div class="citem-txt">${esc(plainOf(it).slice(0, 160))}</div></div>`;
  }
  function renderList() {
    const q = query.toLowerCase();
    const match = (it) => !q || (labelOf(it) + ' ' + it.title + ' ' + plainOf(it) + ' ' + groupLabel(it)).toLowerCase().includes(q);
    const items = ITEMS.filter(match);
    $('#sp-list-count').textContent = 'Copy and policies · ' + items.length + (q ? ' of ' + ITEMS.length : '');
    let html = '';
    const qc = questionComment();
    const held = items.filter(it => it.question_comment_id);
    if (qc && !qAnswer(qc) && held.length) html += UI.section('needs', 'Needs you', held.length, `<p class="project-detail">Question #${esc(D().number(qc.id) || '')} covers these ${held.length} held-back lines. Answer it, or edit a line yourself.</p>` + held.map(rowHtml).join(''), { cls: 'sec-needs', badge: 'badge-error', open: openGroups.needs !== false, scope: 'lib' });
    const ready = items.filter(isPendingItem);
    if (ready.length) html += UI.section('ready', 'Ready to send', ready.length, ready.map(rowHtml).join(''), { open: openGroups.ready !== false, scope: 'lib' });
    GROUP_ORDER.forEach(g => {
      const rows = items.filter(it => (it.group || '') === g);
      if (!rows.length) return;
      const sel = BY_ID[selected];
      const open = q ? true : (openGroups[g] != null ? openGroups[g] : !!(sel && (sel.group || '') === g));
      html += UI.section(g || 'other', GROUPS[g], rows.length, rows.map(rowHtml).join(''), { open, scope: 'lib' });
    });
    if (!items.length) html = '<p class="project-detail">No matching copy.</p>';
    const body = $('#sp-list-body');
    body.innerHTML = html;
    UI.wireSections(body, (k, o) => { openGroups[k] = o; UI.local.set('lib:groups', openGroups); });
    body.querySelectorAll('.sp-row').forEach(b => {
      b.addEventListener('click', () => select(b.dataset.item, true));
      b.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(b.dataset.item, true); } });
    });
  }

  // ── Editor (Quill 2, bundled locally) ──────────────────────────────────
  const Inline = Quill.import('blots/inline');
  class CommentMark extends Inline {
    static create(v) { const n = super.create(); n.setAttribute('data-c', v); n.setAttribute('title', 'Comment'); return n; }
    static formats(n) { return n.getAttribute('data-c'); }
  }
  CommentMark.blotName = 'cmark'; CommentMark.tagName = 'mark'; CommentMark.className = 'sp-cmark';
  Quill.register(CommentMark, true);
  const FORMATS = ['bold', 'italic', 'underline', 'strike', 'link', 'header', 'list', 'blockquote', 'cmark'];
  // Comment marks are a view of the comments, never part of the copy.
  function withoutMarks(delta) {
    return { ops: (delta.ops || []).map(op => {
      if (!op.attributes || !('cmark' in op.attributes)) return op;
      const attributes = Object.assign({}, op.attributes); delete attributes.cmark;
      const out = Object.assign({}, op); if (Object.keys(attributes).length) out.attributes = attributes; else delete out.attributes;
      return out;
    }) };
  }
  // Links the copy may keep (as the server: HTTP, HTTPS or mailto, no
  // credentials). Quill turns an unsafe pasted href into about:blank; the
  // text stays and the link is dropped.
  function safeLink(v) {
    if (typeof v !== 'string' || /[\s\\]/.test(v) || /[\u0000-\u001f\u007f]/.test(v)) return false;
    try {
      const u = new URL(v);
      if (u.protocol === 'mailto:') return !!u.pathname;
      return (u.protocol === 'https:' || u.protocol === 'http:') && !!u.hostname && !u.username && !u.password;
    } catch { return false; }
  }
  function forSave(delta) {
    return { ops: withoutMarks(delta).ops.map(op => {
      if (!op.attributes || !('link' in op.attributes) || safeLink(op.attributes.link)) return op;
      const attributes = Object.assign({}, op.attributes); delete attributes.link;
      const out = Object.assign({}, op); if (Object.keys(attributes).length) out.attributes = attributes; else delete out.attributes;
      return out;
    }) };
  }

  function toolbarHtml() {
    const b = (f, label, title, extra) => `<button type="button" class="btn btn-ghost btn-xs" data-fmt="${f}" title="${title}" aria-label="${title}" aria-pressed="false"${extra || ''}>${label}</button>`;
    return `<select class="select select-xs" id="sp-heading" aria-label="Text style"><option value="">Text</option><option value="1">Heading 1</option><option value="2">Heading 2</option><option value="3">Heading 3</option></select>
      <span class="sep"></span>${b('bold', '<b>B</b>', 'Bold')}${b('italic', '<i>I</i>', 'Italic')}${b('underline', '<u>U</u>', 'Underline')}${b('strike', '<s>S</s>', 'Strikethrough')}
      <span class="sep"></span>${b('bullet', UI.ico('list'), 'Bulleted list')}${b('ordered', UI.ico('olist'), 'Numbered list')}${b('blockquote', UI.ico('quote'), 'Quote')}
      <span class="sep"></span><button type="button" class="btn btn-ghost btn-xs" id="sp-link-btn" title="Link" aria-label="Link">${UI.ico('link')}</button>
      <span class="sp-link-edit" id="sp-link-edit" hidden><input type="url" class="input input-xs" id="sp-link-url" placeholder="https://…" aria-label="Link URL"><button type="button" class="btn btn-xs" id="sp-link-apply">Apply</button><button type="button" class="btn btn-ghost btn-xs" id="sp-link-remove">Remove</button></span>
      <span class="sep"></span><button type="button" class="btn btn-ghost btn-xs" id="sp-undo" title="Undo" aria-label="Undo">${UI.ico('undo')}</button><button type="button" class="btn btn-ghost btn-xs" id="sp-redo" title="Redo" aria-label="Redo">${UI.ico('redo')}</button>
      <span class="gap"></span><button type="button" class="btn btn-ghost btn-xs" id="sp-comment-sel" disabled title="Select words in the text, then comment on them">${UI.ico('message')} Comment on selection</button>`;
  }
  function statusLabel(it) {
    const s = statusText(it);
    return /^held back/.test(s) ? 'Held back' : /pending review/.test(s) ? 'Pending review' : /^not rendered/.test(s) ? 'Not rendered' : /^approved/.test(s) ? 'Approved' : 'Draft for your edit';
  }
  function renderItem() {
    const it = BY_ID[selected];
    if (!it) { $('#sp-item').innerHTML = '<p class="muted">No copy yet.</p>'; return; }
    const num = it.number != null ? ' · row ' + it.number : '';
    const title = it.number != null ? it.where : nameOf(it);
    const alts = (it.alternatives || []).map(a => ({ label: a.label, text: plainOfDelta(a.delta) }));
    const card = (seedHistory(it).find(h => h.kind === 'decision' && h.card) || {}).card;
    const cardRef = card ? (/polic/i.test(groupLabel(it)) ? 'Policies' : 'Copy') + ' card #' + card : '';
    const mine = myRevs(it).slice(-1)[0];
    const edited = mine && latestRev(it).id === mine.id;
    $('#sp-item').innerHTML = `
      <button type="button" class="btn btn-ghost btn-sm sp-back" id="sp-back">${UI.ico('chevLeft')} All copy</button>
      <div class="plan-scope"><strong>${esc(groupLabel(it))}</strong>${num}${cardRef ? ' · ' + esc(cardRef) : ''}</div>
      <section><h2>${esc(title)}<span class="chip">${esc(statusLabel(it))}</span></h2>
      <p class="muted"><code>${esc(keyOf(it))}</code> · ${esc(it.where || '')}</p>
      <div class="card"><p class="ctx">${esc(statusText(it))}</p></div>
      <div class="sp-editor-card">
        <div class="sp-toolbar" id="sp-toolbar" role="toolbar" aria-label="Formatting">${toolbarHtml()}</div>
        <div class="sp-editor" id="sp-editor"></div>
        <div class="sp-edit-ft"><span class="gf-hint" id="sp-edit-status" role="status">${edited ? 'Your edit · ' + esc(UI.fmtTs(mine.created_at)) + (mine.round_pending ? ' · goes out with Send' : ' · sent') : 'Goes out with Send'}</span><button type="button" class="btn btn-sm" id="sp-discard" disabled>Cancel</button><button type="button" class="btn btn-sm" id="sp-save" disabled>Save</button></div>
      </div>
      ${alts.length ? `<details class="aa-details" id="sp-alts"><summary>Earlier alternatives from the agent (${alts.length})</summary><div class="wrap"><table><thead><tr><th></th><th>Text</th><th></th></tr></thead><tbody>${alts.map((a, i) => `<tr><td>${esc(a.label)}</td><td>${esc(a.text)}</td><td>${a.text && !/^— none/.test(a.text) ? `<button type="button" class="btn btn-ghost btn-xs" data-use="${i}">Use this</button>` : ''}</td></tr>`).join('')}</tbody></table></div></details>` : ''}
      </section>`;
    $('#sp-back').addEventListener('click', () => setView('list'));
    mountEditor(it);
    document.querySelectorAll('[data-use]').forEach(b => b.addEventListener('click', () => {
      const a = it.alternatives[Number(b.dataset.use)];
      quill.setContents(a.delta, 'user'); quill.focus();
    }));
  }
  let baseline = '';
  const latestOf = (id) => BY_ID[id] ? latestRev(BY_ID[id]).id : null;
  const editorChanged = () => !!quill && JSON.stringify(withoutMarks(quill.getContents()).ops) !== baseline;
  function forgetDraft(id) {
    delete drafts[id]; delete draftBases[id];
    UI.local.set('lib:drafts', drafts); UI.local.set('lib:draft-base', draftBases);
  }
  // A newer revision than the one the editor started from is the latest.
  // The notice stays in the status line until Save (which then replaces the
  // newer revision with this text) or Cancel (which loads it).
  function showStale() { staleSeen = latestOf(editorItem); setStatus(STALE_NOTE); }
  const isStale = () => !!editorItem && latestOf(editorItem) !== editorBase;
  function mountEditor(it) {
    quill = new Quill('#sp-editor', { theme: 'snow', formats: FORMATS, modules: { toolbar: false, history: { userOnly: true } }, placeholder: 'Write the copy…' });
    const draft = drafts[it.id];
    quill.setContents(latestRev(it).delta, 'silent');
    commentsOf(it).forEach(markComment);
    baseline = JSON.stringify(withoutMarks(quill.getContents()).ops);
    editorItem = it.id; staleSeen = null;
    editorBase = draft && draftBases[it.id] && it.revisions.some(r => r.id === draftBases[it.id]) ? draftBases[it.id] : latestRev(it).id;
    if (draft) { quill.setContents(draft, 'silent'); commentsOf(it).forEach(markComment); setStatus('Draft kept in this browser.'); }
    quill.history.clear();
    quill.root.setAttribute('aria-label', 'Edit ' + labelOf(it));
    quill.root.setAttribute('role', 'textbox');
    quill.root.setAttribute('aria-multiline', 'true');
    wireToolbar();
    quill.on('text-change', (_d, _o, source) => {
      if (source !== 'user') return;
      const c = editorChanged();
      $('#sp-save').disabled = !c; $('#sp-save').classList.toggle('btn-primary', c);
      $('#sp-discard').disabled = !c;
      if (c) {
        drafts[it.id] = withoutMarks(quill.getContents());
        if (!draftBases[it.id]) draftBases[it.id] = editorBase;
        UI.local.set('lib:drafts', drafts); UI.local.set('lib:draft-base', draftBases);
        setStatus(staleSeen ? STALE_NOTE : 'Draft kept in this browser.');
      } else { forgetDraft(it.id); setStatus(''); }
    });
    if (draft && editorChanged()) { $('#sp-save').disabled = false; $('#sp-save').classList.add('btn-primary'); $('#sp-discard').disabled = false; }
    if (draft && isStale()) showStale();
    quill.on('selection-change', (range) => {
      if (!range) return;
      syncToolbar(range);
      const b = $('#sp-comment-sel');
      b.disabled = !range.length;
      if (range.length) { pendingRange = range; }
    });
    quill.root.addEventListener('click', (e) => {
      const m = e.target.closest('mark.sp-cmark');
      if (m) highlightComment(m.getAttribute('data-c'), true);
    });
    $('#sp-save').addEventListener('click', () => saveEdit(it));
    $('#sp-discard').addEventListener('click', () => { forgetDraft(it.id); renderItem(); });
  }
  // The copy changed on the server (another browser, the agent, a Send). An
  // editor with no unsaved text shows the latest revision; one with unsaved
  // text keeps it and shows the notice.
  function syncEditor() {
    const it = BY_ID[selected];
    if (!it || !quill || saving || editorItem !== it.id) return;
    const latest = latestRev(it).id;
    if (latest === editorBase) return;
    const intent = saveIntents[it.id];
    if (intent && latest === 'r_' + intent.id) return; // this browser's own save; a retry reuses its request id
    if (!editorChanged()) {
      const focus = quill.hasFocus() ? quill.getSelection() : null;
      forgetDraft(it.id);
      renderItem();
      if (focus) { quill.focus(); const n = Math.max(0, quill.getLength() - 1); quill.setSelection(Math.min(focus.index, n), 0, 'silent'); }
    } else if (staleSeen !== latest) showStale();
  }
  function setStatus(t) { const s = $('#sp-edit-status'); if (s && t) s.textContent = t; }
  function markComment(c) {
    if (!c.quote) return;
    const text = quill.getText();
    const i = text.indexOf(c.quote);
    if (i >= 0) quill.formatText(i, c.quote.length, 'cmark', c.id, 'silent');
  }
  function syncToolbar(range) {
    const f = quill.getFormat(range.index, range.length);
    document.querySelectorAll('#sp-toolbar [data-fmt]').forEach(b => {
      const k = b.dataset.fmt;
      const on = k === 'bullet' || k === 'ordered' ? f.list === k : !!f[k];
      b.setAttribute('aria-pressed', String(on));
    });
    $('#sp-heading').value = String(f.header || '');
  }
  function wireToolbar() {
    // The toolbar formats the selection as it is now. Typing moves the caret
    // without a selection-change event, so read the live selection (Quill
    // restores the last one when focus is in the link box or the heading).
    let range = { index: 0, length: 0 };
    const current = () => { const r = quill.getSelection(true); if (r) range = r; return range; };
    quill.on('selection-change', r => { if (r) range = r; });
    quill.on('text-change', () => { const r = quill.getSelection(); if (r) range = r; });
    const apply = (fmt, val) => { const r = current(); quill.setSelection(r.index, r.length, 'silent'); quill.format(fmt, val, 'user'); syncToolbar(quill.getSelection() || r); };
    document.querySelectorAll('#sp-toolbar [data-fmt]').forEach(b => {
      b.addEventListener('mousedown', e => e.preventDefault());
      b.addEventListener('click', () => {
        const r = current(), k = b.dataset.fmt, f = quill.getFormat(r.index, r.length);
        if (k === 'bullet' || k === 'ordered') apply('list', f.list === k ? false : k);
        else apply(k, !f[k]);
      });
    });
    $('#sp-heading').addEventListener('change', (e) => apply('header', e.target.value ? Number(e.target.value) : false));
    $('#sp-undo').addEventListener('click', () => quill.history.undo());
    $('#sp-redo').addEventListener('click', () => quill.history.redo());
    $('#sp-link-btn').addEventListener('mousedown', e => e.preventDefault());
    $('#sp-link-btn').addEventListener('click', () => { const ed = $('#sp-link-edit'); ed.hidden = !ed.hidden; const r = current(); $('#sp-link-url').value = quill.getFormat(r.index, r.length).link || ''; if (!ed.hidden) $('#sp-link-url').focus(); });
    $('#sp-link-apply').addEventListener('click', () => {
      const v = $('#sp-link-url').value.trim();
      if (!/^(https?:|mailto:)/.test(v)) { setStatus('Use an HTTP, HTTPS, or mailto link.'); return; }
      apply('link', v); $('#sp-link-edit').hidden = true;
    });
    $('#sp-link-remove').addEventListener('click', () => { apply('link', false); $('#sp-link-edit').hidden = true; });
    const cs = $('#sp-comment-sel');
    cs.addEventListener('mousedown', e => e.preventDefault());
    cs.addEventListener('click', () => startComment(pendingRange));
  }
  // POST that keeps the HTTP status (UI.api throws only a message).
  async function post(path, body) {
    try {
      const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      return { ok: r.ok, status: r.status, data: await r.json().catch(() => ({})) };
    } catch { return { ok: false, status: 0, data: {} }; }
  }
  const tooBig = (r) => r.status === 413 || (r.status === 400 && /^copy (text|document) .*at most \d+ characters/.test(String(r.data.error || '')));
  async function saveEdit(it) {
    const delta = forSave(quill.getContents());
    const content = JSON.stringify(delta.ops);
    const save = $('#sp-save');
    // The server takes at most 256 KB per request; say so before sending.
    if (new Blob([content]).size > 255 * 1024) { setStatus(TOO_BIG_NOTE); return; }
    save.disabled = true;
    // A retry of the same save (same item, base and text) reuses its request
    // id, so a save whose answer was lost is not stored twice.
    let intent = saveIntents[it.id];
    if (!(intent && intent.content === content && (intent.base === editorBase || intent.base === staleSeen))) {
      await loadCopy();
      if (isStale() && staleSeen !== latestOf(it.id)) { showStale(); save.disabled = false; return; }
      intent = { id: crypto.randomUUID(), base: latestOf(it.id) || editorBase, content };
      saveIntents[it.id] = intent; UI.local.set('lib:save-intent', saveIntents);
    }
    saving = true;
    const r = await post('./api/copy/' + encodeURIComponent(it.id) + '/revisions', { delta, base_revision: intent.base, request_id: intent.id });
    saving = false;
    if (!r.ok) {
      // Refused outright (not a lost answer): the next Save is a new attempt.
      if (r.status >= 400 && r.status < 500) { delete saveIntents[it.id]; UI.local.set('lib:save-intent', saveIntents); }
      save.disabled = false;
      if (r.status === 409) { await loadCopy(); showStale(); return; }
      setStatus(tooBig(r) ? TOO_BIG_NOTE : 'Could not save — try again.');
      return;
    }
    delete saveIntents[it.id]; UI.local.set('lib:save-intent', saveIntents);
    forgetDraft(it.id);
    setData(r.data);
    renderAll();
    setStatus('Saved · goes out with Send');
  }
  async function restore(it, revisionId) {
    // base_revision: the latest revision this browser has seen; the server
    // refuses a stale one with 409 (the notice; unsaved text stays).
    const r = await post('./api/copy/' + encodeURIComponent(it.id) + '/restore', { revision_id: revisionId, base_revision: latestOf(it.id) || latestRev(it).id, request_id: crypto.randomUUID() });
    if (r.status === 409) { await loadCopy(); if (AA.view === 'library' && editorItem === it.id) showStale(); return; }
    if (!r.ok) { setStatus('Could not restore — try again.'); return; }
    forgetDraft(it.id);
    await loadCopy();
    if (AA.view !== 'library') AA.go({ view: 'library', item: it.id });
    renderAll();
    AA.rail.setTab('feedback');
    setStatus('Saved · goes out with Send');
  }

  // ── Rail: Feedback (question, ready to send, comments) and History ─────
  function qCard(q) {
    const d = D();
    const n = d.number(q.id) || '';
    const ans = qAnswer(q);
    if (ans) {
      return `<div class="citem is-line" data-q="${esc(q.id)}"><div class="citem-line"><span class="citem-num">#${esc(n)}</span><span class="citem-line-txt"><span class="citem-line-q">${esc(d.displayPrompt(q))}</span><span class="citem-line-arrow">→</span><span class="ans">${esc(ans)}</span></span><button type="button" class="btn btn-ghost btn-xs btn-square change-btn" id="q-change" aria-label="Change answer to #${esc(n)}" title="Change">${UI.ico('pencil')}</button></div></div>`;
    }
    const dr = q.decision_request;
    const opts = (dr.options || []).filter(o => o && typeof o === 'object');
    const btns = opts.map(o => `<button class="btn decision-btn decision-custom${o.id === dr.recommendation ? ' is-recommended' : ''}" data-q-opt="${esc(o.id)}"${o.id === dr.recommendation ? ' title="Recommended by the agent"' : ''}><span class="decision-opt-head"><span class="decision-opt-label">${esc(o.label)}</span>${o.id === dr.recommendation ? '<span class="badge badge-success badge-soft badge-xs decision-rec-badge">Recommended</span>' : ''}</span>${o.consequence ? `<span class="decision-consequence">${esc(o.consequence)}</span>` : ''}</button>`).join('');
    const reco = opts.find(o => o.id === dr.recommendation);
    const covered = ITEMS.filter(it => it.question_comment_id === q.id).length;
    return `<div class="citem decision-required" data-q="${esc(q.id)}" role="group" aria-label="Feedback #${esc(n)} · ${esc(d.displayPrompt(q))}">
      <div class="citem-node"><span class="citem-node-name"><span class="citem-num">#${esc(n)}</span></span></div>
      <div class="citem-meta"><span class="citem-author">${esc(d.whoName(q))}</span><span>${esc(UI.fmtTs(q.created_at))}${q.edited_at ? ' (edited)' : ''}</span></div>
      <div class="decision-block"><div class="decision-prompt">${d.ticketsHTML(d.displayPrompt(q))}</div>
      ${dr.context ? `<div class="decision-context">${d.ticketsHTML(dr.context)}</div>` : ''}
      ${reco ? `<div class="decision-reco-line">Recommended: <b>${esc(reco.label)}</b></div>` : ''}
      <p class="project-detail">A question about library items lives in the Library: it covers the ${covered} held-back lines here, including this one.</p>
      <div class="decision-btns has-consequences">${btns}</div>
      <div class="decision-feedback" id="q-feedback"></div></div></div>`;
  }
  function commentCard(c) {
    return `<div class="citem" data-cid="${esc(c.id)}" tabindex="0" role="group" aria-label="Comment${c.quote ? ' on “' + esc(c.quote) + '”' : ''}">
      <div class="citem-meta"><span class="citem-author">${esc(c.agent ? c.author : c.name)}</span><span>${esc(UI.fmtTs(c.ts))}</span></div>
      ${c.quote ? `<div class="unified-selected-quote">“${esc(c.quote)}”</div>` : ''}
      <div class="citem-txt">${esc(c.text)}</div></div>`;
  }
  function renderRail() {
    const it = BY_ID[selected];
    const rail = $('#rail-library');
    if (!it) { rail.innerHTML = '<p class="project-detail rail-note">No copy yet.</p>'; return; }
    const d = D();
    let html = '';
    const q = question(it);
    if (q && !qAnswer(q)) html += UI.section('needs', 'Needs you', 1, qCard(q), { cls: 'sec-needs', badge: 'badge-error', scope: 'lib' });
    const stored = storedComments(it);
    const readyC = stored.filter(c => !c.agent && d.needsPush(c.comment));
    const lastEdit = myPendingRevs(it).slice(-1)[0];
    const qReady = q && qAnswer(q) && d.isRoundPending(q);
    const nReady = readyC.length + (lastEdit ? 1 : 0) + (qReady ? 1 : 0);
    if (nReady) {
      html += UI.section('ready', 'Ready to send', nReady,
        (qReady ? qCard(q) : '') +
        (lastEdit ? `<div class="citem"><div class="citem-meta"><span class="citem-author">${esc(d.whoName({ author: lastEdit.author.id, author_name: lastEdit.author.name }))}</span><span>${esc(UI.fmtTs(lastEdit.created_at))}</span></div><div class="citem-txt"><b>Edited</b> · see History for the change</div></div>` : '') +
        readyC.map(commentCard).join(''), { scope: 'lib' });
    }
    const others = commentsOf(it).filter(c => !readyC.some(r => r.id === c.id));
    html += UI.section('comments', 'Comments', others.length, (others.map(commentCard).join('') || '<p class="project-detail">No comments on this item yet.</p>'), { scope: 'lib' });
    if (q && qAnswer(q) && !qReady) html += UI.section('done', 'Done', 1, qCard(q), { open: false, scope: 'lib' });
    // The rail's own "+ General feedback" box (A3), for this item. Its
    // unsaved text is this item's draft (kept in this browser until Save).
    const typed = commentDrafts[it.id] || '';
    const open = !!(pendingQuote || typed);
    html = `<div class="gf" id="sp-compose">
      <button type="button" class="gf-row" id="sp-compose-toggle" aria-expanded="${open ? 'true' : 'false'}" aria-controls="sp-compose-box">${UI.ico('plus')}<span>Comment on this item</span></button>
      <div class="gf-box" id="sp-compose-box" ${open ? '' : 'hidden'}>
        <div class="unified-selected-quote" id="sp-compose-quote" ${pendingQuote ? '' : 'hidden'}>${pendingQuote ? '“' + esc(pendingQuote) + '”' : ''}</div>
        <textarea class="textarea gf-ta" id="sp-compose-ta" placeholder="Add your feedback, question, or redline note&hellip;" rows="3" aria-label="Comment on ${esc(labelOf(it))}" data-submit="#sp-compose-save"></textarea>
        <div class="gf-ft"><span class="gf-hint">Goes out with Send</span><button type="button" class="btn btn-ghost btn-xs" id="sp-compose-cancel">Cancel</button><button type="button" class="btn btn-ghost btn-xs" id="sp-compose-save">Save</button></div>
      </div></div>` + html;
    rail.innerHTML = html;
    const cta = $('#sp-compose-ta');
    cta.value = typed;
    cta.addEventListener('input', () => setCommentDraft(it.id, cta.value));
    UI.wireSections(rail);
    rail.querySelectorAll('[data-q-opt]').forEach(b => b.addEventListener('click', async () => {
      const o = q.decision_request.options.find(x => x.id === b.dataset.qOpt);
      const v = d.selectVerdictId();
      const r = await d.decide(q.id, v, v === 'select' ? o.label : 'Selected: ' + o.label);
      if (!r || r.fallback) { const f = $('#q-feedback'); if (f) { f.textContent = 'Failed to send — try again.'; f.classList.add('is-error'); } return; }
      await d.refreshStore();
    }));
    const ch = $('#q-change');
    if (ch) ch.addEventListener('click', () => { rail.querySelector('[data-q]').outerHTML = qCardOpen(q); wireQ(rail, q); });
    rail.querySelectorAll('[data-cid]').forEach(el => {
      el.addEventListener('mouseenter', () => highlightComment(el.dataset.cid, false));
      el.addEventListener('mouseleave', () => highlightComment(null, false));
      el.addEventListener('click', () => highlightComment(el.dataset.cid, false, true));
    });
    $('#sp-compose-toggle').addEventListener('click', () => { const box = $('#sp-compose-box'); box.hidden = !box.hidden; $('#sp-compose-toggle').setAttribute('aria-expanded', String(!box.hidden)); if (!box.hidden) $('#sp-compose-ta').focus(); });
    $('#sp-compose-cancel').addEventListener('click', () => {
      $('#sp-compose-box').hidden = true; $('#sp-compose-toggle').setAttribute('aria-expanded', 'false');
      if (pendingRange && quill) quill.formatText(pendingRange.index, pendingRange.length, 'cmark', false, 'silent');
      pendingQuote = null; pendingRange = null; $('#sp-compose-ta').value = ''; setCommentDraft(it.id, ''); $('#sp-compose-quote').hidden = true;
    });
    $('#sp-compose-save').addEventListener('click', () => saveComment(it));
    if (AA.rail.tab === 'history') AA.rail.renderHistory();
  }
  function setCommentDraft(id, text) {
    if (text.trim()) commentDrafts[id] = text; else delete commentDrafts[id];
    UI.local.set('lib:comment-drafts', commentDrafts);
  }
  // "Change" on an answered question shows its options again.
  function qCardOpen(q) {
    const saved = q.decision;
    q.decision = null;
    try { return qCard(q); } finally { q.decision = saved; }
  }
  function wireQ(rail, q) {
    rail.querySelectorAll('[data-q-opt]').forEach(b => b.addEventListener('click', async () => {
      const o = q.decision_request.options.find(x => x.id === b.dataset.qOpt);
      const v = D().selectVerdictId();
      const r = await D().decide(q.id, v, v === 'select' ? o.label : 'Selected: ' + o.label);
      if (r && !r.fallback) await D().refreshStore();
    }));
  }
  function startComment(range) {
    if (!range || !range.length) return;
    pendingRange = { index: range.index, length: range.length };
    pendingQuote = quill.getText(range.index, range.length).trim();
    quill.formatText(range.index, range.length, 'cmark', 'pending', 'silent');
    AA.rail.reveal();
    $('#sp-compose-box').hidden = false; $('#sp-compose-toggle').setAttribute('aria-expanded', 'true');
    const qn = $('#sp-compose-quote'); qn.hidden = false; qn.textContent = '“' + pendingQuote + '”';
    const ta = $('#sp-compose-ta');
    ta.scrollIntoView({ block: 'center' });
    ta.focus();
  }
  async function saveComment(it) {
    const ta = $('#sp-compose-ta');
    const text = ta.value.trim();
    if (!text) { ta.focus(); return; }
    const target = Object.assign({ copy_block: it.id }, pendingQuote ? { selected_quote: pendingQuote } : {});
    const c = await D().createComment('copy:' + it.id, labelOf(it), text, undefined, target, { category: 'library' });
    if (!c) { setStatus('Could not save the comment — try again.'); return; }
    ta.value = '';
    setCommentDraft(it.id, '');
    pendingQuote = null; pendingRange = null;
    await D().refreshStore();
    // ⌘↵ leaves focus in the box, so the store refresh skips the rail.
    if (shown && selected === it.id) { renderList(); renderRail(); }
    highlightComment(c.id, true);
  }
  function highlightComment(cid, scrollRail, scrollDoc) {
    document.querySelectorAll('mark.sp-cmark').forEach(m => m.classList.toggle('is-hl', !!cid && m.getAttribute('data-c') === cid));
    document.querySelectorAll('#rail-library [data-cid]').forEach(el => el.classList.toggle('hl', el.dataset.cid === cid));
    if (cid && scrollRail) { AA.rail.setTab('feedback'); const el = document.querySelector('#rail-library [data-cid="' + CSS.escape(cid) + '"]'); if (el) el.scrollIntoView({ block: 'nearest' }); }
    if (cid && scrollDoc) { const m = document.querySelector('mark.sp-cmark[data-c="' + CSS.escape(cid) + '"]'); if (m) m.scrollIntoView({ block: 'center' }); }
  }
  function renderHistory(el) {
    const it = BY_ID[selected];
    if (!it || !el) { if (el) el.innerHTML = ''; return; }
    const d = D();
    const entries = [];
    seedHistory(it).forEach(h => entries.push(h));
    const q = question(it);
    // A discarded answer (UI-14) never went out; History leaves it out.
    if (q) (q.decision_history || []).concat(q.decision ? [q.decision] : []).filter(x => x && x.verdict && !x.discarded).forEach(x => entries.push({ ts: x.ts, who: d.whoName({ by: x.by }), kind: 'q', text: x.verdict === 'select' ? String(x.text || '').replace(/^Selected:\s*/, '') : (x.text || x.verdict), sent: !x.round_pending, n: d.number(q.id), prompt: d.displayPrompt(q) }));
    it.revisions.forEach((r, i) => {
      if (r.status !== 'proposed') return;
      const prev = it.revisions[i - 1];
      entries.push({ ts: r.created_at, who: d.whoName({ author: r.author.id, author_name: r.author.name }), kind: 'edit', text: plainOfDelta(r.delta), prev: prev ? plainOfDelta(prev.delta) : '', prevId: prev ? prev.id : null, sent: !r.round_pending });
    });
    storedComments(it).filter(c => !c.agent).forEach(c => entries.push({ ts: c.ts, who: c.name, kind: 'comment', text: c.text, quote: c.quote, sent: !d.needsPush(c.comment) }));
    entries.sort((a, b) => (a.ts < b.ts ? 1 : -1));
    const seed = it.revisions.find(r => r.status !== 'proposed');
    const row = (h) => {
      let head = '', body = '', actions = '';
      if (h.kind === 'added') { head = `<b>${esc(h.who)}</b> · added in ${esc(h.version)}${h.label ? ' (' + esc(h.label) + ')' : ''}`; body = h.text ? esc(h.text) : ''; if (h.text && seed && it.number != null) actions = `<button type="button" class="btn btn-ghost btn-xs" data-restore="${esc(seed.id)}">Restore this text</button>`; }
      else if (h.kind === 'changed') { head = `<b>${esc(h.who)}</b> · ${esc(h.version)}: ${esc((h.changed || []).join(', '))} changed`; body = esc(h.status || ''); }
      else if (h.kind === 'decision') { head = `<b>${esc(h.who)}</b> · answered copy card #${esc(h.card)}`; body = esc(h.text) + (h.prompt ? `<div class="project-detail">${esc(h.prompt)}</div>` : ''); }
      else if (h.kind === 'response') { head = `<b>${esc(h.who)}</b> · agent response`; body = esc(h.text); }
      else if (h.kind === 'edit') { head = `<b>${esc(h.who)}</b> · edited · ${h.sent ? 'sent' : 'not sent yet'}`; body = UI.diffWords(h.prev, h.text); actions = h.prevId ? `<button type="button" class="btn btn-ghost btn-xs" data-restore="${esc(h.prevId)}">Restore the earlier text</button>` : ''; }
      else if (h.kind === 'comment') { head = `<b>${esc(h.who)}</b> · comment · ${h.sent ? 'sent' : 'not sent yet'}`; body = (h.quote ? '“' + esc(h.quote) + '” ' : '') + esc(h.text); }
      else if (h.kind === 'q') { head = `<b>${esc(h.who)}</b> · answered #${esc(h.n || '')} · ${h.sent ? 'sent' : 'not sent yet'}`; body = esc(h.text) + `<div class="project-detail">${esc(h.prompt)}</div>`; }
      return `<div class="hist-item"><div class="hist-head">${head}<span>· ${esc(UI.fmtTs(h.ts))}</span></div><div class="hist-text">${body}</div>${actions ? `<div class="hist-actions">${actions}</div>` : ''}</div>`;
    };
    el.innerHTML = `<p class="project-detail hist-sub">${esc(labelOf(it))}</p>${entries.map(row).join('')}`;
    el.querySelectorAll('[data-restore]').forEach(b => b.addEventListener('click', () => restore(it, b.dataset.restore)));
  }

  // ── Selection, views, deep links ───────────────────────────────────────
  const root = $('#view-library');
  function setView(v) {
    root.classList.toggle('is-list', v === 'list');
    root.classList.toggle('is-item', v !== 'list');
    const sc = $('#sp-doc'); if (sc) sc.scrollTop = 0;
  }
  function select(id, user) {
    if (!BY_ID[id]) return;
    selected = id;
    pendingQuote = null; pendingRange = null;
    UI.local.set('lib:selected', id);
    markSeen(BY_ID[id]);
    renderAll();
    if (user) { setView('item'); history.replaceState(null, '', '#view=library&item=' + id); }
  }
  function renderAll() { renderList(); renderItem(); renderRail(); AA.changed(); }
  function selectPhrase(phrase) {
    const i = quill.getText().indexOf(phrase);
    if (i < 0) return;
    quill.focus();
    quill.setSelection(i, phrase.length, 'user');
    pendingRange = { index: i, length: phrase.length };
    $('#sp-comment-sel').disabled = false;
  }
  function applyHash(h) {
    let id = h.get('item');
    if (id && !BY_ID[id] && BY_ID['row-' + id]) id = 'row-' + id;
    if (!id && h.get('group')) { const g = ITEMS.find(it => it.group === h.get('group') || /polic/i.test(h.get('group')) && /polic/i.test(groupLabel(it))); if (g) id = g.id; }
    if (id && BY_ID[id] && id !== selected) select(id);
    else { markSeen(BY_ID[selected]); renderAll(); }
    setView(h.get('list') === '1' ? 'list' : 'item');
    if (h.get('tab')) AA.rail.setTab(h.get('tab'));
    if (h.get('sel')) setTimeout(() => selectPhrase(h.get('sel')), 50);
    if (h.get('compose')) setTimeout(() => { if (h.get('sel')) startComment(pendingRange); else { AA.rail.reveal(); $('#sp-compose-box').hidden = false; $('#sp-compose-ta').focus(); } }, 80);
  }

  // A previous / F next item, in the list's order (E3, as on Review's rail).
  function shortcut(e) {
    if (UI.isTyping(e.target)) return;
    const k = e.key.toLowerCase();
    if (k !== 'a' && k !== 'f') return;
    const rows = [...document.querySelectorAll('#sp-list-body .sp-row')].map(r => r.dataset.item).filter((v, i, a) => a.indexOf(v) === i);
    if (!rows.length) return;
    e.preventDefault();
    let i = rows.indexOf(selected);
    i = i === -1 ? 0 : Math.max(0, Math.min(rows.length - 1, i + (k === 'f' ? 1 : -1)));
    select(rows[i], true);
    const el = document.querySelector('#sp-list-body .sp-row[data-item="' + CSS.escape(rows[i]) + '"]');
    if (el) el.scrollIntoView({ block: 'nearest' });
  }

  // ── The tab's part of the page ─────────────────────────────────────────
  $('#sp-search').addEventListener('input', (e) => { query = e.target.value; renderList(); });
  // The page's store changed (an action, a Send or the 8 s poll).
  document.addEventListener('annotate:store', async () => {
    await loadCopy();
    if (shown && !UI.isTyping(document.activeElement)) { renderList(); renderRail(); }
    if (shown) syncEditor();
  });
  // The shell's refresh watches comments, not copy: while the Library is
  // open, look for new revisions (another browser, the agent) every 8 s.
  async function checkCopy() {
    if (!shown || document.hidden || saving || !DATA) return;
    let data;
    try { data = await UI.api('./api/copy'); } catch { return; }
    if (JSON.stringify(data) === copySig || saving) return;
    setData(data);
    AA.changed();
    if (!shown) return;
    if (!UI.isTyping(document.activeElement)) { renderList(); renderRail(); }
    syncEditor();
  }
  setInterval(checkCopy, 8000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) checkCopy(); });
  const ready = () => loading || (loading = loadCopy());
  AA.provider('library', {
    pending: () => (DATA ? pendingItems() : []),
    roundPending: () => ITEMS.some(it => myPendingRevs(it).length),
    async afterSend() { await loadCopy(); if (shown) renderAll(); },
    async show(h) { await ready(); shown = true; applyHash(h); },
    hide() { shown = false; },
    history(el) { if (DATA) { const title = document.getElementById('hist-library-title'); if (title) title.textContent = 'This item'; renderHistory(el); } },
    shortcut,
  });
  ready();
})();
