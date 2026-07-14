// ── annotate universal shell — chrome logic ──────────────────────────
// This file drives the version-stable chrome: version rail, comment
// drawer, ball-in-court badges, author identity, general feedback.
// It NEVER reaches into iframe content directly — all cross-frame
// communication goes through postMessage (see the "Bridge" section).
// Identical behavior across every slug/project/version.
(function () {
'use strict';

// ── Base path + API helpers ───────────────────────────────────────
// The shell is served at <public_base_path>/ ; all API calls are relative
// to that same origin+prefix so this works both on localhost and behind
// the Cloudflare tunnel's /schema (or /prem-fin, etc.) prefix.
function apiUrl(path) {
  return path; // relative fetch — browser resolves against current document URL
}

let STORE = { schema_version: 2, anchors: {}, archived: {} };
let META = { current: null, history: [], content_stamps: {} };
let SEEN = {}; // { version: {ts, whole_hash, section_hashes} }
let READ = {}; // { commentId: {ts, sig} } — this viewer's per-comment read state
let NUM_MAP = {}; // { commentId: n } — stable per-version comment number (pin #n ↔ card #n)
let CURRENT_VERSION = null;
let AUTHOR = null;
let IDENTITY = null;
let SESSION_MONITOR = { active: false, monitor_count: 0, delivery: 'queued' };
let activeFilter = 'all';
let showArchivedInline = false;
let showAllVersions = false; // drawer scope: current version only vs every version
let unreadFirst = false;     // drawer ordering: unread comments sorted to top
let highlightedCommentId = null;
// T11: unposted drafts survive re-renders, VERSION SWITCHES, and reloads.
// Keys: comment id for reply boxes, 'gf:<version>' for general feedback.
let DRAFTS = {};
let draftsSaveTimer = null;
function saveDraftsSoon() {
  clearTimeout(draftsSaveTimer);
  draftsSaveTimer = setTimeout(() => {
    try { localStorage.setItem('annotate:drafts', JSON.stringify(DRAFTS)); } catch {}
  }, 400);
}
function setDraft(key, value) {
  if (value) DRAFTS[key] = value;
  else delete DRAFTS[key];
  saveDraftsSoon();
}

// ── OAuth identity ─────────────────────────────────────────────────
function normalizeIdentity(payload) {
  if (!payload || typeof payload !== 'object') return null;
  const nested = payload.identity || payload.user || {};
  const email = payload.email || nested.email || payload.author_email || null;
  const name = payload.name || payload.display_name || nested.name || nested.display_name || null;
  if (!email || email === 'anonymous') return null;
  return { email: String(email).trim(), name: name ? String(name).trim() : null };
}

function authorValue(identity) {
  if (!identity) return null;
  return identity.name && identity.name !== identity.email
    ? `${identity.name} <${identity.email}>`
    : identity.email;
}

async function resolveIdentity() {
  // Cloudflare Access exposes the identity already established by OAuth.
  // This same-origin endpoint is unavailable locally, so fall through to
  // the annotation server's authenticated-header echo.
  try {
    const r = await fetch('/cdn-cgi/access/get-identity', { cache: 'no-store', credentials: 'same-origin' });
    if (r.ok) {
      const j = await r.json();
      const identity = normalizeIdentity(j);
      if (identity) return identity;
    }
  } catch {}
  try {
    const r = await fetch(apiUrl('./api/identity'), { cache: 'no-store' });
    if (r.ok) {
      const identity = normalizeIdentity(await r.json());
      if (identity) return identity;
    }
  } catch {}
  try {
    const r = await fetch(apiUrl('./api/seen'), { cache: 'no-store' });
    if (r.ok) {
      const j = await r.json();
      const identity = normalizeIdentity({ email: j.author });
      if (identity) return identity;
    }
  } catch {}
  return null;
}

function updateAuthorIndicator() {
  const ind = document.getElementById('author-ind');
  ind.textContent = IDENTITY
    ? '\u{1F464} ' + authorValue(IDENTITY)
    : '\u{1F512} OAuth sign-in required to comment';
  ind.title = IDENTITY ? 'Identity supplied by OAuth' : 'No OAuth identity was received';
}

function authorLabel(record) {
  if (!record) return 'anonymous';
  if (record.author_name && record.author_email && record.author_name !== record.author_email) {
    return `${record.author_name} <${record.author_email}>`;
  }
  return record.author_email || record.author || 'anonymous';
}

// ── HTTP helpers ──────────────────────────────────────────────────
function authorQuery() {
  return AUTHOR ? ('?author=' + encodeURIComponent(AUTHOR)) : '';
}

async function loadStore() {
  try {
    const r = await fetch(apiUrl('./comments.json'), { cache: 'no-store' });
    if (!r.ok) return false;
    const store = await r.json();
    STORE = store && store.schema_version === 2 ? store : { schema_version: 2, anchors: {}, archived: {} };
    computeNumbers();
    return true;
  } catch { return false; }
}

// ── Per-version comment numbering ───────────────────────────────────
// Every comment gets a stable 1-based number within its version, assigned in
// creation order over ALL comments of that version INCLUDING archived ones —
// so accepting/archiving a comment never renumbers its neighbors mid-session.
// The number renders on the sidebar card (#7) and on the page pin (7): the
// shared visual key that disambiguates two comments on the same section.
function computeNumbers() {
  NUM_MAP = {};
  const byVersion = {};
  for (const c of flattenAll(true)) {
    (byVersion[c.version || ''] = byVersion[c.version || ''] || []).push(c);
  }
  for (const v of Object.keys(byVersion)) {
    byVersion[v].sort((a, b) =>
      new Date(a.created_at) - new Date(b.created_at) || String(a.id).localeCompare(String(b.id)));
    byVersion[v].forEach((c, i) => { NUM_MAP[c.id] = i + 1; });
  }
}

async function loadMeta() {
  try {
    const r = await fetch(apiUrl('./current.meta.json'), { cache: 'no-store' });
    if (!r.ok) return false;
    META = await r.json();
    return true;
  } catch { return false; }
}

async function loadSeen() {
  try {
    const r = await fetch(apiUrl('./api/seen' + authorQuery()), { cache: 'no-store' });
    if (!r.ok) return false;
    const j = await r.json();
    SEEN = j.seen || {};
    return true;
  } catch { return false; }
}

async function markSeen(version) {
  try {
    await fetch(apiUrl('./api/seen'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ version }),
    });
  } catch {}
}

// ── Per-comment read model ──────────────────────────────────────────
// A comment is read only while its stored sig matches its live activity sig.
// Read is set on ENGAGEMENT (opening the card, visiting its anchor, acting on
// it) — never as a side effect of page load. Any later agent activity
// (response_text, status change, new reply) shifts the sig, so the comment
// re-enters the unread queue with a "NEW reply" chip.
function commentSig(c) {
  const s = [c.status || '', c.response_text || '', String((c.replies || []).length), c.edited_at || ''].join('');
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  return h.toString(36);
}

// 'read' | 'unread' (never engaged) | 'new-activity' (read before, agent acted since)
function readStateOf(c) {
  if (c.status === 'archived') return 'read';
  const rec = READ[c.id];
  if (!rec) return 'unread';
  return rec.sig === commentSig(c) ? 'read' : 'new-activity';
}

async function loadReadState() {
  try {
    const r = await fetch(apiUrl('./api/read-state' + authorQuery()), { cache: 'no-store' });
    if (!r.ok) return false;
    const j = await r.json();
    READ = j.read || {};
    return true;
  } catch { return false; }
}

// Optimistic: READ is updated locally before the POST so the UI decrements
// instantly; the server merge is idempotent.
function markRead(comments) {
  const items = [];
  const now = new Date().toISOString();
  for (const c of comments) {
    if (!c || !c.id) continue;
    const sig = commentSig(c);
    const rec = READ[c.id];
    if (rec && rec.sig === sig) continue; // already read at this sig
    READ[c.id] = { ts: now, sig };
    items.push({ id: c.id, sig });
  }
  if (!items.length) return Promise.resolve(null);
  return fetch(apiUrl('./api/read-state' + authorQuery()), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  }).catch(() => null);
}

function findCommentById(id) {
  for (const c of flattenAll(true)) if (c.id === id) return c;
  return null;
}

async function apiCreateComment(anchorId, anchorLabel, text, version, target) {
  try {
    const r = await fetch(apiUrl('./api/comments' + authorQuery()), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        anchor_id: anchorId,
        anchor_label: anchorLabel,
        text,
        version,
        // granular sub-anchor selector captured by adapter.js at click time
        target: target || null,
        author: AUTHOR,
        author_name: IDENTITY && IDENTITY.name,
        author_email: IDENTITY && IDENTITY.email,
      }),
    });
    if (r.ok) return await r.json();
  } catch {}
  return null;
}

async function apiPutComment(id, patch) {
  try {
    const r = await fetch(apiUrl('./api/comments/' + encodeURIComponent(id) + authorQuery()), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign({
        author: AUTHOR,
        author_name: IDENTITY && IDENTITY.name,
        author_email: IDENTITY && IDENTITY.email,
      }, patch)),
    });
    if (r.ok) return await r.json();
  } catch {}
  return null;
}

async function apiReply(id, text) {
  try {
    const r = await fetch(apiUrl('./api/comments/' + encodeURIComponent(id) + '/reply' + authorQuery()), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text,
        author: AUTHOR,
        author_name: IDENTITY && IDENTITY.name,
        author_email: IDENTITY && IDENTITY.email,
      }),
    });
    if (r.ok) return await r.json();
  } catch {}
  return null;
}

async function apiAccept(id) {
  try {
    const r = await fetch(apiUrl('./api/comments/' + encodeURIComponent(id) + '/accept' + authorQuery()), { method: 'POST' });
    if (r.ok) return await r.json();
  } catch {}
  return null;
}

async function apiArchive(id) {
  try {
    const r = await fetch(apiUrl('./api/comments/' + encodeURIComponent(id) + '/archive' + authorQuery()), { method: 'POST' });
    if (r.ok) return await r.json();
  } catch {}
  return null;
}

async function apiRestore(id) {
  try {
    const r = await fetch(apiUrl('./api/comments/' + encodeURIComponent(id) + '/restore' + authorQuery()), { method: 'POST' });
    if (r.ok) return await r.json();
  } catch {}
  return null;
}

async function apiPushAll() {
  try {
    const r = await fetch(apiUrl('./api/push-session'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    if (r.ok) return await r.json();
  } catch {}
  return null;
}

async function loadSessionMonitor() {
  try {
    const r = await fetch(apiUrl('./api/session-monitor'), { cache: 'no-store' });
    if (r.ok) SESSION_MONITOR = await r.json();
  } catch {
    SESSION_MONITOR = { active: false, monitor_count: 0, delivery: 'queued' };
  }
  return SESSION_MONITOR;
}

// ── Ball-in-court classification ───────────────────────────────────
// needsReview  = addressed_by_agent, OR (open AND last reply author starts with "agent:")
// waitingAgent = open AND (no replies OR last reply author does NOT start with "agent:")
// done         = user_confirmed OR archived
function isAgentAuthor(a) {
  return !!a && a.indexOf('agent:') === 0;
}
function lastReplyAuthor(c) {
  const replies = c.replies || [];
  return replies.length ? replies[replies.length - 1].author : null;
}
function classify(c) {
  if (c.status === 'addressed_by_agent') return 'review';
  if (c.status === 'open') {
    return isAgentAuthor(lastReplyAuthor(c)) ? 'review' : 'waiting';
  }
  // user_confirmed or archived
  return 'done';
}

function flattenAll(includeArchived) {
  const all = [];
  for (const [aid, items] of Object.entries(STORE.anchors || {})) {
    for (const c of items) all.push(Object.assign({}, c, { anchor_id: aid }));
  }
  if (includeArchived) {
    for (const [aid, items] of Object.entries(STORE.archived || {})) {
      for (const c of items) all.push(Object.assign({}, c, { anchor_id: aid }));
    }
  }
  return all;
}

function countsForVersion(version) {
  const all = flattenAll(false).filter(c => !version || c.version === version);
  let review = 0, waiting = 0, done = 0;
  for (const c of all) {
    const cls = classify(c);
    if (cls === 'review') review++;
    else if (cls === 'waiting') waiting++;
    else done++;
  }
  return { review, waiting, done, total: all.length };
}

// ── ↑NEW detection ──────────────────────────────────────────────────
function hasNewContent(version) {
  const stamp = (META.content_stamps || {})[version];
  if (!stamp) return false;
  const seenRec = SEEN[version];
  if (!seenRec) return true; // never visited -> not "new", just unvisited; handled separately
  return seenRec.whole_hash !== stamp.whole;
}
function neverVisited(version) {
  return !SEEN[version];
}

// ── Version rail ─────────────────────────────────────────────────
function renderVersionRail() {
  const body = document.getElementById('vrail-body');
  const history = (META.history || []).slice().reverse();
  if (!history.length) {
    body.innerHTML = '<div class="vrail-empty">No versions found</div>';
    return;
  }
  body.innerHTML = history.map(h => {
    const counts = countsForVersion(h.version);
    const isCur = h.version === CURRENT_VERSION;
    const isNew = !neverVisited(h.version) && hasNewContent(h.version);
    let dotHtml = '<span class="vrow-dot"></span>';
    if (counts.waiting > 0 && counts.review === 0) dotHtml = '<span class="vrow-dot-hollow" title="Your comments awaiting agent"></span>';
    const badgeHtml = counts.review > 0
      ? `<span class="vrow-badge">${counts.review}</span>`
      : `<span class="vrow-badge zero">0</span>`;
    const newHtml = isNew ? '<span class="vrow-new" title="Content updated since your last visit">↑NEW</span>' : '';
    return `<div class="vrow ${isCur ? 'current' : ''}" data-version="${escAttr(h.version)}" title="${escAttr(h.label || '')}">
      ${dotHtml}
      <span class="vrow-label">${esc(h.version)}${h.label ? ' &middot; ' + esc(h.label) : ''}</span>
      ${newHtml}
      ${badgeHtml}
    </div>`;
  }).join('');
  Array.from(body.querySelectorAll('.vrow')).forEach(row => {
    row.addEventListener('click', () => switchVersion(row.dataset.version));
  });
}

function switchVersion(v) {
  if (!v || v === CURRENT_VERSION) return;
  CURRENT_VERSION = v;
  loadIframe(v);
  const u = new URL(window.location.href);
  u.searchParams.set('v', v);
  window.history.replaceState({}, '', u.toString());
  renderAll();
  // T11: the general-feedback draft is per-version
  const gf = document.getElementById('gf-ta');
  if (gf) gf.value = DRAFTS['gf:' + v] || '';
}

function loadIframe(v) {
  const frame = document.getElementById('content-frame');
  frame.src = './content?v=' + encodeURIComponent(v);
}

// ── Drawer ───────────────────────────────────────────────────────
function esc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function escAttr(s) { return esc(s).replace(/'/g, '&#39;'); }
function fmtTs(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return String(iso).slice(0, 16).replace('T', ' '); }
}

function anchorLabel(c) {
  return c.anchor_label || c.anchor_id;
}

// Drawer scope: null = every version ("All versions" toggle on), else the
// version currently shown in the iframe.
function drawerScope() {
  return showAllVersions ? null : CURRENT_VERSION;
}
function inScope(c) {
  const scope = drawerScope();
  return !scope || c.version === scope;
}

function renderChips() {
  const all = flattenAll(false).filter(inScope);
  let review = 0, waiting = 0, done = 0, unread = 0;
  for (const c of all) {
    const cls = classify(c);
    if (cls === 'review') review++;
    else if (cls === 'waiting') waiting++;
    else done++;
    if (readStateOf(c) !== 'read') unread++;
  }
  const total = all.length;
  const row = document.getElementById('chip-row');
  row.querySelector('.chip-review .chip-n').textContent = review;
  row.querySelector('.chip-waiting .chip-n').textContent = waiting;
  row.querySelector('.chip-done .chip-n').textContent = done;
  row.querySelector('.chip-all .chip-n').textContent = total;
  document.getElementById('cnt-badge').textContent = total + (total === 1 ? ' comment' : ' comments');
  const ub = document.getElementById('unread-badge');
  ub.textContent = unread + ' unread';
  ub.style.display = unread > 0 ? '' : 'none';
  updateStripBadge();
}

function renderDrawer() {
  renderChips();
  const listEl = document.getElementById('comment-list');
  const empty = document.getElementById('drawer-empty');

  // Preserve in-progress reply drafts across re-renders AND version
  // switches (T11): capture into the persistent DRAFTS store before the
  // innerHTML swap — cards filtered out by the new scope keep their draft
  // for when they render again.
  let focusedDraftFor = null;
  listEl.querySelectorAll('.reply-ta').forEach(ta => {
    setDraft(ta.dataset.replyFor, ta.value || '');
    if (ta === document.activeElement) focusedDraftFor = ta.dataset.replyFor;
  });

  let all = flattenAll(false).filter(inScope);
  if (activeFilter !== 'all') {
    all = all.filter(c => classify(c) === activeFilter);
  }

  all.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  if (unreadFirst) {
    const rank = c => (readStateOf(c) === 'read' ? 1 : 0);
    all.sort((a, b) => rank(a) - rank(b) || (new Date(b.created_at) - new Date(a.created_at)));
  }

  document.getElementById('archived-count').textContent =
    Object.values(STORE.archived || {}).reduce((n, l) => n + l.filter(inScope).length, 0);

  if (!all.length && !showArchivedInline) {
    empty.style.display = 'flex';
    listEl.style.display = 'none';
    listEl.innerHTML = '';
    return;
  }
  empty.style.display = 'none';
  listEl.style.display = 'block';

  let html = all.map(renderCItem).join('');

  if (showArchivedInline) {
    const arch = [];
    for (const [aid, items] of Object.entries(STORE.archived || {})) {
      for (const c of items) if (inScope(c)) arch.push(Object.assign({}, c, { anchor_id: aid }));
    }
    if (arch.length) {
      html += `<div class="cgroup"><div class="cgroup-lbl">Archived</div>${arch.map(renderCItem).join('')}</div>`;
    }
  }

  listEl.innerHTML = html || '<div class="drawer-empty" style="padding:24px 12px">No comments match this filter.</div>';

  listEl.querySelectorAll('.reply-ta').forEach(ta => {
    const draft = DRAFTS[ta.dataset.replyFor];
    if (draft) ta.value = draft;
  });
  if (focusedDraftFor) {
    const ta = listEl.querySelector('[data-reply-for="' + cssEsc(focusedDraftFor) + '"]');
    if (ta) {
      ta.focus();
      ta.selectionStart = ta.selectionEnd = ta.value.length;
    }
  }

  Array.from(listEl.querySelectorAll('[data-action="goto"]')).forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      markRead([findCommentById(btn.dataset.id)].filter(Boolean));
      goToCommentLocation(btn.dataset.anchor, btn.dataset.version, btn.dataset.id);
    });
  });
  wireCardActions(listEl);
}

// ── Go-to-location: cross-version-aware, with unresolvable feedback ────
// Requirements (per user report -- click-a-comment must reveal where it was
// tagged, the old flow silently did nothing / flashed too briefly / never
// switched version for a cross-version comment):
//   1. If the comment's tagged version differs from what's currently shown,
//      switch the iframe to that version FIRST, and wait for the new
//      document's 'annotate:ready' before asking it to scroll (the iframe
//      doesn't exist yet / hasn't parsed anchors until then).
//   2. Ask adapter.js to resolve + scroll + highlight (highlight now persists
///     ~5s, see adapter.js scrollToAnchor).
//   3. adapter.js reports back whether the anchor actually resolved
//      ('annotate:scroll-result'); if not, mark the card so the user sees
//      "location unavailable in this version" instead of nothing happening.
let pendingGoto = null; // {commentId, anchorId, target} awaiting scroll-result after a version switch
const gotoUnavailable = {}; // commentId -> true, once we've heard back it can't resolve

function goToCommentLocation(anchorId, version, commentId) {
  highlightedCommentId = commentId;
  // Granular goto: pass the comment's captured inner target (if any) so the
  // adapter highlights the exact element, not just the section container.
  const c = commentId ? findCommentById(commentId) : null;
  const target = (c && c.target) || null;
  if (version && version !== CURRENT_VERSION) {
    pendingGoto = { commentId, anchorId, target };
    switchVersion(version);
    // switchVersion() re-points the iframe's src; the actual scroll-to is
    // sent once that document announces 'annotate:ready' (see wireBridge).
  } else {
    scrollToAnchorInFrame(anchorId, target);
  }
  renderDrawer();
}

function markGotoUnavailable(commentId) {
  gotoUnavailable[commentId] = true;
  renderDrawer();
}

// `general:<version>` anchor ids (minted by wireGeneralFeedback()) are not
// tied to any content-doc node -- there is nothing in the iframe to scroll
// to. Every other anchor id is a real content location.
function isGeneralAnchor(anchorId) {
  return typeof anchorId === 'string' && anchorId.indexOf('general:') === 0;
}

function renderCItem(c) {
  const cls = classify(c);
  const clsMap = { review: 'needs-review', waiting: 'waiting-agent', done: 'done' };
  const statusLabelMap = { review: 'Needs my review', waiting: 'Waiting on agent', done: c.status === 'archived' ? 'Archived' : 'Done' };
  const ts = fmtTs(c.created_at);
  // #n mirrors the numbered pin on the page (pin 7 ↔ card #7).
  const num = NUM_MAP[c.id];
  const numHtml = num ? `<span class="citem-num">#${num}</span>` : '';
  const vchipHtml = `<span class="citem-vchip">${esc(c.version || '?')}</span>`;
  const rstate = readStateOf(c);
  let unreadChipHtml = '';
  if (rstate === 'new-activity') unreadChipHtml = '<span class="citem-chip-newreply" title="The agent responded since you last read this">&uarr; NEW reply</span>';
  else if (rstate === 'unread') unreadChipHtml = '<span class="citem-chip-unread" title="You have not opened this comment yet">Unread</span>';
  const unreadCls = rstate !== 'read' ? ' is-unread' : '';
  const hl = c.id === highlightedCommentId ? ' hl' : '';

  const replyHtml = (c.replies || []).map(r => `
    <div class="thread-reply">
      <div class="thread-reply-hdr">${esc(authorLabel(r))} &middot; ${esc(fmtTs(r.ts))}</div>
      <div>${esc(r.text)}</div>
    </div>`).join('');
  const agentReplyHtml = c.response_text ? `
    <div class="agent-reply">
      <div class="agent-reply-hdr">Agent response</div>
      <div>${esc(c.response_text)}</div>
    </div>` : '';

  let actions = '';
  if (c.status !== 'archived') {
    if (cls === 'review') {
      actions += `<button class="alink accept" data-action="accept" data-id="${escAttr(c.id)}">&#10003; Accept &amp; archive</button>`;
      actions += `<button class="alink" data-action="reopen" data-id="${escAttr(c.id)}" data-anchor="${escAttr(c.anchor_id)}">Reopen</button>`;
    } else if (c.status === 'user_confirmed') {
      actions += `<button class="alink accept" data-action="accept" data-id="${escAttr(c.id)}">&#10003; Accept &amp; archive</button>`;
      actions += `<button class="alink" data-action="reopen" data-id="${escAttr(c.id)}" data-anchor="${escAttr(c.anchor_id)}">Reopen</button>`;
    } else {
      actions += `<button class="alink" data-action="archive" data-id="${escAttr(c.id)}">Archive</button>`;
    }
    // Re-pin: correct a mis-anchored comment by clicking its true location.
    // Only meaningful when the comment's version is the one on screen.
    if (!isGeneralAnchor(c.anchor_id) && c.version === CURRENT_VERSION) {
      actions += `<button class="alink" data-action="repin" data-id="${escAttr(c.id)}" title="Click a new location in the document to move this comment's pin">&#128204; Re-pin</button>`;
    }
  } else {
    actions += `<button class="alink" data-action="restore" data-id="${escAttr(c.id)}">Restore</button>`;
  }

  const replyFormHtml = c.status !== 'archived' ? `
    <div class="reply-form">
      <textarea class="reply-ta" data-reply-for="${escAttr(c.id)}" placeholder="Add a reply&hellip;" rows="2"></textarea>
      <button class="reply-submit" data-action="reply" data-id="${escAttr(c.id)}">Post reply</button>
    </div>` : '';

  // ── Go-to-location affordance: ALWAYS visible, never a silent no-op.
  // general:* comments have no content-doc location by design (they're the
  // "+ General feedback" bucket, not anchored to a section) -- say so
  // explicitly rather than offering a button that can't do anything.
  // gotoUnavailable[c.id] is set once adapter.js has told us (via
  // 'annotate:scroll-result', see wireBridge) that this anchor genuinely
  // does not resolve to any node in its tagged version's content doc.
  let gotoHtml;
  if (isGeneralAnchor(c.anchor_id)) {
    gotoHtml = `<div class="citem-goto unavailable">
        <span class="citem-goto-label">General feedback &mdash; not tied to a location</span>
      </div>`;
  } else if (gotoUnavailable[c.id]) {
    gotoHtml = `<div class="citem-goto unavailable">
        <span class="citem-goto-label">${esc(anchorLabel(c))} &mdash; location unavailable in this version</span>
        <button class="citem-goto-btn err" data-action="goto" data-id="${escAttr(c.id)}" data-anchor="${escAttr(c.anchor_id)}" data-version="${escAttr(c.version)}" title="Content may have been restructured since this comment was made">&#10007; Not found</button>
      </div>`;
  } else {
    gotoHtml = `<div class="citem-goto" data-goto-row data-goto-id="${escAttr(c.id)}">
        <span class="citem-goto-label">${esc(anchorLabel(c))}</span>
        <button class="citem-goto-btn" data-action="goto" data-id="${escAttr(c.id)}" data-anchor="${escAttr(c.anchor_id)}" data-version="${escAttr(c.version)}">&rarr; Go to location</button>
      </div>`;
  }

  return `<div class="citem ${clsMap[cls]}${hl}${unreadCls}" data-comment-id="${escAttr(c.id)}" title="Click to show this comment's location in the document">
    <div class="citem-node">
      <span class="citem-node-name">${numHtml}${vchipHtml}${esc(anchorLabel(c))}</span>
      ${unreadChipHtml}<span class="citem-status cstatus-${cls}">${esc(statusLabelMap[cls])}</span>
    </div>
    ${gotoHtml}
    <div class="citem-txt">${esc(c.text)}</div>
    ${agentReplyHtml}
    ${replyHtml}
    <div class="citem-meta">
      <span class="citem-author">${esc(authorLabel(c))}</span>
      <span>${ts}${c.edited_at ? ' (edited)' : ''}</span>
    </div>
    <div class="citem-actions">${actions}</div>
    ${replyFormHtml}
  </div>`;
}

// The user acted on the comment, so they have unambiguously seen its current
// state: re-sync read state to the post-action sig (otherwise their own reply
// or reopen would flag the card as NEW activity). Must run AFTER the store
// refresh so the sig reflects the post-action comment, then re-render.
function markReadAfterAction(commentId) {
  const c = findCommentById(commentId);
  if (c && c.status !== 'archived') {
    markRead([c]);
    renderDrawer();
    sendCommentCountsToFrame();
  }
}

function wireCardActions(root) {
  // Whole-card click navigates (T1): every surveyed review tool treats the
  // sidebar card as the navigation affordance, not just a small button.
  // Buttons/links/textareas inside the card keep their own behavior.
  root.querySelectorAll('.citem').forEach(card => card.addEventListener('click', (e) => {
    if (e.target.closest('button, textarea, a, input, select')) return;
    const c = findCommentById(card.dataset.commentId);
    if (!c) return;
    markRead([c]);
    highlightedCommentId = c.id;
    if (isGeneralAnchor(c.anchor_id)) {
      // No content-doc location by design — just mark active/read; the card
      // already shows the "not tied to a location" notice.
      renderDrawer();
      sendCommentCountsToFrame();
      return;
    }
    goToCommentLocation(c.anchor_id, c.version, c.id);
    sendCommentCountsToFrame();
  }));
  root.querySelectorAll('[data-action="accept"]').forEach(btn => btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    await apiAccept(btn.dataset.id);
    await refreshStore();
  }));
  root.querySelectorAll('[data-action="archive"]').forEach(btn => btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    await apiArchive(btn.dataset.id);
    await refreshStore();
  }));
  root.querySelectorAll('[data-action="restore"]').forEach(btn => btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    await apiRestore(btn.dataset.id);
    await refreshStore();
    markReadAfterAction(btn.dataset.id);
  }));
  root.querySelectorAll('[data-action="reopen"]').forEach(btn => btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    await apiPutComment(btn.dataset.id, { status: 'open' });
    await refreshStore();
    markReadAfterAction(btn.dataset.id);
  }));
  root.querySelectorAll('[data-action="reply"]').forEach(btn => btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    const ta = root.querySelector('[data-reply-for="' + cssEsc(btn.dataset.id) + '"]');
    const text = (ta && ta.value || '').trim();
    if (!text) { if (ta) ta.focus(); return; }
    const posted = await apiReply(btn.dataset.id, text);
    // Clear BEFORE the re-render: renderDrawer preserves non-empty reply
    // drafts across re-renders, so a successfully-posted text left in the
    // box would be re-injected forever (T8, user-reported). On failure the
    // text stays so nothing typed is lost.
    if (posted) {
      if (ta) ta.value = '';
      setDraft(btn.dataset.id, ''); // posted — drop the persistent draft too
    }
    await refreshStore();
    markReadAfterAction(btn.dataset.id);
  }));
  root.querySelectorAll('[data-action="repin"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    startRepin(btn.dataset.id);
  }));
}
function cssEsc(s) { return String(s).replace(/(["\\\[\]\(\)])/g, '\\$1'); }

async function refreshStore() {
  await loadStore();
  renderAll();
}

// ── Filter chips ─────────────────────────────────────────────────
function wireChips() {
  document.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      activeFilter = chip.dataset.filter;
      renderDrawer();
    });
  });
}

// ── Popover (create/edit a comment) ────────────────────────────────
let pendingAnchor = null; // {anchorId, anchorLabel, target}
let editingCommentId = null;

function openPopoverForCreate(anchorId, anchorLabel, x, y, target) {
  if (!IDENTITY) {
    updateAuthorIndicator();
    return;
  }
  pendingAnchor = { anchorId, anchorLabel, target: target || null };
  editingCommentId = null;
  const pop = document.getElementById('popover');
  document.getElementById('pop-node-name').textContent = anchorLabel || anchorId;
  document.getElementById('pop-ta').value = '';
  positionPopover(x, y);
  pop.classList.add('vis');
  document.getElementById('pop-ta').focus();
}
function positionPopover(cx, cy) {
  const pop = document.getElementById('popover');
  const pw = 332, ph = 220;
  let left = cx + 12, top = cy + 12;
  if (left + pw > window.innerWidth - 8) left = cx - pw - 12;
  if (top + ph > window.innerHeight - 8) top = cy - ph - 12;
  if (left < 8) left = 8;
  if (top < 8) top = 8;
  pop.style.left = left + 'px';
  pop.style.top = top + 'px';
}
function closePopover() {
  document.getElementById('popover').classList.remove('vis');
  pendingAnchor = null;
  editingCommentId = null;
}
async function savePopover() {
  if (!IDENTITY) return;
  const text = document.getElementById('pop-ta').value.trim();
  if (!text || !pendingAnchor) return;
  const created = await apiCreateComment(pendingAnchor.anchorId, pendingAnchor.anchorLabel, text, CURRENT_VERSION, pendingAnchor.target);
  closePopover();
  if (created) {
    await refreshStore();
    // The author has obviously "read" their own new comment.
    markReadAfterAction(created.id);
  }
}

// ── Re-pin: correct a mis-anchored comment ───────────────────────────
// Arms a one-shot mode: the next click in the content doc becomes the
// comment's new location (anchor + captured inner target), saved as a
// manual-repin re-anchor — the original creation record is never rewritten,
// the new fields carry their own provenance (per R2: re-anchoring is a new
// fact, not an edit of history).
let repinCommentId = null;

function startRepin(commentId) {
  repinCommentId = commentId;
  const banner = document.getElementById('repin-banner');
  if (banner) {
    banner.style.display = 'flex';
    const c = findCommentById(commentId);
    const num = c && NUM_MAP[c.id] ? '#' + NUM_MAP[c.id] + ' ' : '';
    banner.querySelector('.repin-banner-txt').textContent =
      'Re-pinning comment ' + num + '— click its correct location in the document (Esc to cancel)';
  }
}

function cancelRepin() {
  repinCommentId = null;
  const banner = document.getElementById('repin-banner');
  if (banner) banner.style.display = 'none';
}

async function completeRepin(anchorId, anchorLabel, target) {
  const id = repinCommentId;
  cancelRepin();
  if (!id) return;
  const updated = await apiPutComment(id, {
    anchor_id: anchorId,
    anchor_label: anchorLabel,
    target: target || null,
    reanchor: {
      strategy: 'manual-repin',
      confidence: 1.0,
      ts: new Date().toISOString(),
      by: AUTHOR,
    },
  });
  await refreshStore();
  if (updated) {
    markReadAfterAction(id);
    goToCommentLocation(anchorId, updated.version, id); // show the new spot
  }
}

// ── Pin popover (pin → comment reverse lookup, T2) ───────────────────
// Clicking a numbered pin in the content doc lists that pin's comment(s)
// here AND focuses the matching sidebar card. Clicking the anchor's own
// text/element still opens the CREATE popover — the adapter routes pin
// clicks separately ('annotate:pin-open') and they never fall through.
let pinPopoverCtx = null; // {anchorId, anchorLabel, x, y} of the open pin popover

function renderPinPopItem(c) {
  const cls = classify(c);
  const statusLabelMap = { review: 'Needs my review', waiting: 'Waiting on agent', done: c.status === 'archived' ? 'Archived' : 'Done' };
  const num = NUM_MAP[c.id];
  const respHtml = c.response_text
    ? `<div class="pinpop-item-resp"><b>Agent:</b> ${esc(c.response_text)}</div>`
    : '';
  return `<div class="pinpop-item" data-comment-id="${escAttr(c.id)}">
    <div class="pinpop-item-hdr">
      ${num ? `<span class="citem-num">#${num}</span>` : ''}
      <span class="citem-vchip">${esc(c.version || '?')}</span>
      <span class="citem-status cstatus-${cls}">${esc(statusLabelMap[cls])}</span>
    </div>
    <div class="pinpop-item-txt">${esc(c.text)}</div>
    ${respHtml}
    <div class="pinpop-item-meta">
      <span>${esc(authorLabel(c))}</span>
      <span>${esc(fmtTs(c.created_at))}</span>
    </div>
    <div class="pinpop-item-hint">Click to jump to its exact location &rarr;</div>
  </div>`;
}

// anchorIds = the pin's anchor PLUS every registered anchor nested inside its
// DOM subtree (computed by the adapter at click time): a pin on an outer box
// reveals ALL comments written within that box's area, grouped by anchor.
function openPinPopover(anchorId, anchorIds, commentIds, anchorLabelText, x, y) {
  const idSet = new Set((anchorIds && anchorIds.length ? anchorIds : [anchorId]));
  const byId = {};
  flattenAll(false).forEach(c => {
    if (idSet.has(c.anchor_id) && c.version === CURRENT_VERSION) byId[c.id] = c;
  });
  (commentIds || []).forEach(id => {
    const c = findCommentById(id);
    if (c) byId[c.id] = c;
  });
  const comments = Object.values(byId);
  if (!comments.length) return;
  comments.sort((a, b) => (NUM_MAP[a.id] || 0) - (NUM_MAP[b.id] || 0));
  markRead(comments); // viewing the thread in the popover = reading it
  pinPopoverCtx = { anchorId, anchorLabel: anchorLabelText || comments[0].anchor_label || anchorId, x, y };

  document.getElementById('pinpop-title').textContent =
    pinPopoverCtx.anchorLabel + ' — ' + comments.length + (comments.length === 1 ? ' comment' : ' comments');
  const body = document.getElementById('pinpop-body');

  // Group by anchor: the pin's own anchor first, nested anchors after.
  const groups = [];
  const seen = {};
  for (const c of comments) {
    if (!(c.anchor_id in seen)) {
      seen[c.anchor_id] = groups.length;
      groups.push({ anchor_id: c.anchor_id, label: c.anchor_label || c.anchor_id, items: [] });
    }
    groups[seen[c.anchor_id]].items.push(c);
  }
  groups.sort((a, b) => (a.anchor_id === anchorId ? -1 : 0) - (b.anchor_id === anchorId ? -1 : 0));
  body.innerHTML = groups.map(g => {
    const lbl = groups.length > 1
      ? `<div class="cgroup-lbl">${esc(g.label)}${g.anchor_id === anchorId ? '' : ' &middot; nested'}</div>`
      : '';
    return lbl + g.items.map(renderPinPopItem).join('');
  }).join('');
  body.querySelectorAll('.pinpop-item').forEach(item => {
    item.addEventListener('click', () => {
      const c = findCommentById(item.dataset.commentId);
      if (!c) return;
      // Jump to the comment's exact location AND focus its sidebar card.
      goToCommentLocation(c.anchor_id, c.version, c.id);
      focusSidebarCard(c.id);
    });
  });

  const pop = document.getElementById('pin-popover');
  pop.classList.add('vis');
  positionPinPopover(x, y);
  focusSidebarCard(comments[0].id);
}

function positionPinPopover(cx, cy) {
  const pop = document.getElementById('pin-popover');
  const pw = pop.offsetWidth || 360;
  const ph = pop.offsetHeight || 300;
  let left = cx + 12, top = cy + 12;
  if (left + pw > window.innerWidth - 8) left = cx - pw - 12;
  if (top + ph > window.innerHeight - 8) top = cy - ph - 12;
  if (left < 8) left = 8;
  if (top < 8) top = 8;
  pop.style.left = left + 'px';
  pop.style.top = top + 'px';
}

function closePinPopover() {
  document.getElementById('pin-popover').classList.remove('vis');
  pinPopoverCtx = null;
}

function wirePinPopover() {
  document.getElementById('pinpop-close').addEventListener('click', closePinPopover);
  document.getElementById('pinpop-add').addEventListener('click', () => {
    const ctx = pinPopoverCtx;
    closePinPopover();
    if (ctx) openPopoverForCreate(ctx.anchorId, ctx.anchorLabel, ctx.x, ctx.y);
  });
  document.getElementById('repin-cancel').addEventListener('click', cancelRepin);
}

// Scroll the drawer to a card and mark it active. If the current chip filter
// hides the card, fall back to the All filter so the focus is never a no-op.
function focusSidebarCard(commentId) {
  if (isDrawerCollapsed()) setDrawerCollapsed(false); // pin/card focus needs the rail visible
  highlightedCommentId = commentId;
  renderDrawer();
  let el = document.querySelector('#comment-list [data-comment-id="' + cssEsc(commentId) + '"]');
  if (!el && activeFilter !== 'all') {
    activeFilter = 'all';
    document.querySelectorAll('.chip').forEach(ch => ch.classList.toggle('active', ch.dataset.filter === 'all'));
    renderDrawer();
    el = document.querySelector('#comment-list [data-comment-id="' + cssEsc(commentId) + '"]');
  }
  if (el) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  sendCommentCountsToFrame(); // pin unread coloring may have changed via markRead
}

// ── General feedback (inline textarea — no window.prompt, AC7) ─────
function wireGeneralFeedback() {
  const toggle = document.getElementById('general-feedback-toggle');
  const box = document.getElementById('general-feedback-box');
  const cancel = document.getElementById('gf-cancel');
  const save = document.getElementById('gf-save');
  toggle.addEventListener('click', () => {
    box.style.display = box.style.display === 'none' ? 'flex' : 'none';
    box.style.flexDirection = 'column';
    if (box.style.display !== 'none') document.getElementById('gf-ta').focus();
  });
  cancel.addEventListener('click', () => {
    document.getElementById('gf-ta').value = '';
    box.style.display = 'none';
  });
  save.addEventListener('click', async () => {
    if (!IDENTITY) {
      updateAuthorIndicator();
      return;
    }
    const ta = document.getElementById('gf-ta');
    const text = ta.value.trim();
    if (!text) { ta.focus(); return; }
    const anchorId = 'general:' + CURRENT_VERSION;
    const created = await apiCreateComment(anchorId, 'General feedback', text, CURRENT_VERSION);
    ta.value = '';
    setDraft('gf:' + CURRENT_VERSION, '');
    box.style.display = 'none';
    await refreshStore();
    if (created) markReadAfterAction(created.id);
  });
  // T11: general-feedback drafts persist per version
  document.getElementById('gf-ta').addEventListener('input', (e) => {
    setDraft('gf:' + CURRENT_VERSION, e.target.value || '');
  });
}

// ── Collapsible rails (T7) ───────────────────────────────────────────
// Rails must never squeeze the document (user report: expanded ER diagram
// lost its rightmost portion to the comment rail — the diagram's fullscreen
// is position:fixed INSIDE the iframe, so its 100vw ends where the drawer
// begins). Commercial pattern (R1: Figma/Frame.io): collapsible panels,
// never overlap. Collapsed state persists; drawer auto-expands when a pin
// or card interaction needs it.
function setDrawerCollapsed(collapsed, persist) {
  document.getElementById('drawer').classList.toggle('collapsed', collapsed);
  if (persist !== false) {
    try { localStorage.setItem('annotate:drawerCollapsed', collapsed ? '1' : '0'); } catch {}
  }
  updateStripBadge();
}
function setVrailCollapsed(collapsed, persist) {
  document.getElementById('vrail').classList.toggle('collapsed', collapsed);
  if (persist !== false) {
    try { localStorage.setItem('annotate:vrailCollapsed', collapsed ? '1' : '0'); } catch {}
  }
}

// P1: content fullscreen (a diagram's ⛶ overlay inside the iframe)
// auto-collapses both rails so the overlay gets the full window — the user
// must never see chrome occlusion without acting. Prior states restore on
// exit; the temporary collapse is never persisted to localStorage.
let railsBeforeFullscreen = null;
function autoCollapseForFullscreen(active) {
  if (active) {
    if (railsBeforeFullscreen) return; // already handled this overlay
    railsBeforeFullscreen = {
      drawer: isDrawerCollapsed(),
      vrail: document.getElementById('vrail').classList.contains('collapsed'),
    };
    setDrawerCollapsed(true, false);
    setVrailCollapsed(true, false);
  } else if (railsBeforeFullscreen) {
    setDrawerCollapsed(railsBeforeFullscreen.drawer, false);
    setVrailCollapsed(railsBeforeFullscreen.vrail, false);
    railsBeforeFullscreen = null;
  }
}
function isDrawerCollapsed() {
  return document.getElementById('drawer').classList.contains('collapsed');
}
function updateStripBadge() {
  const el = document.getElementById('drawer-strip-unread');
  if (!el) return;
  const unread = flattenAll(false).filter(c => inScope(c) && readStateOf(c) !== 'read').length;
  el.textContent = String(unread);
  el.style.display = unread > 0 ? '' : 'none';
}
function wireRailCollapse() {
  document.getElementById('drawer-collapse').addEventListener('click', () => setDrawerCollapsed(true));
  document.getElementById('drawer-strip').addEventListener('click', () => setDrawerCollapsed(false));
  document.getElementById('vrail-collapse').addEventListener('click', () => setVrailCollapsed(true));
  document.getElementById('vrail-strip').addEventListener('click', () => setVrailCollapsed(false));
  try {
    if (localStorage.getItem('annotate:drawerCollapsed') === '1') setDrawerCollapsed(true);
    if (localStorage.getItem('annotate:vrailCollapsed') === '1') setVrailCollapsed(true);
  } catch {}
}

// ── Archived toggle ─────────────────────────────────────────────────
function wireArchivedToggle() {
  document.getElementById('archived-toggle').addEventListener('click', () => {
    showArchivedInline = !showArchivedInline;
    document.getElementById('archived-toggle').classList.toggle('active', showArchivedInline);
    renderDrawer();
  });
}

// ── Drawer view controls: all-versions / unread-first / mark-all-read ──
function wireDrawerControls() {
  const av = document.getElementById('allversions-toggle');
  const uf = document.getElementById('unreadfirst-toggle');
  av.classList.toggle('active', showAllVersions);
  uf.classList.toggle('active', unreadFirst);
  av.addEventListener('click', () => {
    showAllVersions = !showAllVersions;
    try { localStorage.setItem('annotate:allVersions', showAllVersions ? '1' : '0'); } catch {}
    av.classList.toggle('active', showAllVersions);
    renderDrawer();
  });
  uf.addEventListener('click', () => {
    unreadFirst = !unreadFirst;
    try { localStorage.setItem('annotate:unreadFirst', unreadFirst ? '1' : '0'); } catch {}
    uf.classList.toggle('active', unreadFirst);
    renderDrawer();
  });
  document.getElementById('markallread-btn').addEventListener('click', async () => {
    // Scoped to the current view (version scope; chip filter ignored).
    const targets = flattenAll(false).filter(c => inScope(c) && readStateOf(c) !== 'read');
    await markRead(targets);
    renderDrawer();
    sendCommentCountsToFrame();
  });
}

// ── Push to session ─────────────────────────────────────────────────
// A comment needs pushing only if it's open AND has user-side activity newer
// than its last push. Pushing sets flagged_for_session/flagged_at server-side
// but leaves status open — counting bare open comments made the badge show
// "1 remaining" forever after a successful push (T6, user-reported).
function needsPush(c) {
  if (c.status !== 'open') return false;
  if (!c.flagged_for_session) return true;
  const flaggedAt = c.flagged_at ? new Date(c.flagged_at).getTime() : 0;
  let latest = c.edited_at ? new Date(c.edited_at).getTime() : 0;
  for (const r of (c.replies || [])) {
    if (!isAgentAuthor(r.author)) latest = Math.max(latest, new Date(r.ts).getTime());
  }
  return latest > flaggedAt;
}
function countOpenComments() {
  let n = 0;
  for (const items of Object.values(STORE.anchors || {})) {
    for (const c of items) if (needsPush(c)) n++;
  }
  return n;
}
function updatePushCounter() {
  const btn = document.getElementById('push-session-btn');
  const cnt = document.getElementById('push-session-counter');
  const n = countOpenComments();
  cnt.textContent = String(n);
  btn.disabled = (n === 0);
  const owner = SESSION_MONITOR.owner && SESSION_MONITOR.owner.owner_session;
  const route = SESSION_MONITOR.active
    ? 'The active session monitor is armed' + (owner ? ' by ' + owner : '')
    : 'No live monitor is armed; a push will be queued for the next session turn';
  btn.title = n === 0
    ? 'Nothing new to push — all open comments already sent or queued. ' + route
    : 'Send ' + n + ' comment(s) with new activity. ' + route;
}
function wirePushSession() {
  document.getElementById('push-session-btn').addEventListener('click', async () => {
    const btn = document.getElementById('push-session-btn');
    btn.disabled = true;
    const j = await apiPushAll();
    if (j) {
      SESSION_MONITOR = {
        active: j.delivery === 'active_monitor',
        monitor_count: j.monitor_count || 0,
        delivery: j.delivery || 'queued',
        owner: j.monitor_owner || null,
      };
      const delivered = j.delivery === 'active_monitor';
      btn.classList.add(delivered ? 'success' : 'queued');
      btn.querySelector('span:first-child').textContent = delivered
        ? '✅ Sent ' + j.flagged_count + ' to active session'
        : '⏳ Queued ' + j.flagged_count + ' — no monitor armed';
      await refreshStore();
      setTimeout(() => {
        btn.classList.remove('success', 'queued');
        btn.querySelector('span:first-child').textContent = '\u{1F4E8} Push to session';
        updatePushCounter();
      }, 3000);
    } else {
      btn.disabled = false;
    }
  });
}

// ── Bridge: postMessage with the content iframe ─────────────────────
// Content -> shell: {type:'annotate:pin-click', anchorId, anchorLabel, x, y}   (anchor clicked → CREATE popover)
//                   {type:'annotate:pin-open', anchorId, anchorLabel, commentIds, x, y}  (pin clicked → reverse lookup)
//                   {type:'annotate:ready', version}
//                   {type:'annotate:scroll-result', anchorId, found}
// Shell -> content: {type:'annotate:scroll-to', anchorId}
//                   {type:'annotate:comment-counts', counts: {anchorId: n},
//                    pins: {anchorId: [{id, n, unread, target}]}}
//
// Click coordinates arriving from the iframe are iframe-viewport-relative;
// translate them into shell-viewport coordinates before positioning popovers.
function frameOffset() {
  const frame = document.getElementById('content-frame');
  if (!frame) return { left: 0, top: 0 };
  const r = frame.getBoundingClientRect();
  return { left: r.left, top: r.top };
}

function wireBridge() {
  window.addEventListener('message', (e) => {
    const data = e.data || {};
    if (!data || typeof data !== 'object') return;
    if (data.type === 'annotate:pin-click') {
      // Re-pin mode: the click IS the comment's new location.
      if (repinCommentId) {
        completeRepin(data.anchorId, data.anchorLabel, data.target || null);
        return;
      }
      const off = frameOffset();
      closePinPopover();
      openPopoverForCreate(data.anchorId, data.anchorLabel,
        (data.x || window.innerWidth / 2) + off.left,
        (data.y || window.innerHeight / 2) + off.top,
        data.target || null);
    } else if (data.type === 'annotate:pin-open') {
      // Re-pin mode: clicking a pin re-anchors to that pin's anchor (no
      // inner target — the pin represents the whole anchor).
      if (repinCommentId) {
        completeRepin(data.anchorId, data.anchorLabel, null);
        return;
      }
      const off = frameOffset();
      closePopover();
      const pinCommentIds = data.commentIds || [];
      // A numbered pin represents one exact comment. Make that a one-click
      // reverse lookup: reveal the rail, switch filters if necessary, and
      // focus the matching card. Aggregate pins still need the chooser
      // popover because they intentionally represent multiple comments.
      if (pinCommentIds.length === 1) {
        const c = findCommentById(pinCommentIds[0]);
        if (c) {
          closePinPopover();
          markRead([c]);
          focusSidebarCard(c.id);
          return;
        }
      }
      openPinPopover(data.anchorId, data.anchorIds || [], data.commentIds || [], data.anchorLabel,
        (data.x || window.innerWidth / 2) + off.left,
        (data.y || window.innerHeight / 2) + off.top);
    } else if (data.type === 'annotate:content-fullscreen') {
      // P1: a full-viewport overlay opened/closed inside the content doc
      autoCollapseForFullscreen(!!data.active);
    } else if (data.type === 'annotate:ready') {
      // content doc finished loading + adapter.js initialized
      autoCollapseForFullscreen(false); // version switch discards any overlay
      sendCommentCountsToFrame();
      markSeen(CURRENT_VERSION);
      loadSeen().then(renderVersionRail);
      // If a goto-location click triggered a version switch to get here,
      // the scroll-to couldn't be sent until now (the previous iframe
      // document, and its anchor registry, didn't exist yet).
      if (pendingGoto && pendingGoto.commentId === highlightedCommentId) {
        const { anchorId, target } = pendingGoto;
        pendingGoto = null;
        scrollToAnchorInFrame(anchorId, target);
      } else {
        pendingGoto = null;
      }
    } else if (data.type === 'annotate:scroll-result') {
      // adapter.js reports whether the requested anchor actually resolved to
      // a DOM node. Only act on it when it belongs to the comment we just
      // asked to scroll to (same comment AND same anchor) — avoids a stale
      // result from an earlier click clobbering a newer one.
      if (!highlightedCommentId) return;
      const c = findCommentById(highlightedCommentId);
      if (!c || c.anchor_id !== data.anchorId) return;
      if (!data.found) {
        markGotoUnavailable(highlightedCommentId);
      } else if (gotoUnavailable[highlightedCommentId]) {
        // Anchor resolved after all (e.g. retried on its birth version):
        // clear the sticky "location unavailable" state.
        delete gotoUnavailable[highlightedCommentId];
        renderDrawer();
      }
    }
  });
}

function sendCommentCountsToFrame() {
  const frame = document.getElementById('content-frame');
  if (!frame || !frame.contentWindow) return;
  const counts = {};
  const pins = {};
  for (const [aid, items] of Object.entries(STORE.anchors || {})) {
    const list = items.filter(c => c.version === CURRENT_VERSION);
    if (!list.length) continue;
    counts[aid] = list.length;
    pins[aid] = list
      .map(c => ({
        id: c.id,
        n: NUM_MAP[c.id] || 0,
        unread: readStateOf(c) !== 'read',
        // Creation-time granular target. Older comments without one remain
        // at the anchor corner; new comments can render the numbered pin at
        // the exact clicked element/offset inside that anchor.
        target: c.target || null,
      }))
      .sort((a, b) => a.n - b.n);
  }
  frame.contentWindow.postMessage({ type: 'annotate:comment-counts', counts, pins }, '*');
}

function scrollToAnchorInFrame(anchorId, target) {
  const frame = document.getElementById('content-frame');
  if (!frame || !frame.contentWindow) return;
  frame.contentWindow.postMessage({ type: 'annotate:scroll-to', anchorId, target: target || null }, '*');
}

// ── Wire popover buttons ─────────────────────────────────────────────
function wirePopover() {
  document.getElementById('pop-close').addEventListener('click', closePopover);
  document.getElementById('pop-cancel').addEventListener('click', closePopover);
  document.getElementById('pop-save').addEventListener('click', savePopover);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { closePopover(); closePinPopover(); cancelRepin(); }
    if ((e.key === 'Enter' && (e.ctrlKey || e.metaKey)) && document.getElementById('popover').classList.contains('vis')) {
      savePopover();
    }
  });
}

// ── Master render ─────────────────────────────────────────────────
function renderAll() {
  const hdrSub = document.getElementById('hdr-sub');
  if (hdrSub) hdrSub.textContent = CURRENT_VERSION ? ('Version ' + CURRENT_VERSION) : '';
  renderVersionRail();
  renderDrawer();
  updatePushCounter();
  sendCommentCountsToFrame();
}

// ── Init ─────────────────────────────────────────────────────────
async function init() {
  document.getElementById('hdr-title').textContent = document.title || 'annotate';

  try {
    showAllVersions = localStorage.getItem('annotate:allVersions') === '1';
    unreadFirst = localStorage.getItem('annotate:unreadFirst') === '1';
    DRAFTS = JSON.parse(localStorage.getItem('annotate:drafts') || '{}') || {};
  } catch {}

  // T11: live draft capture — every keystroke lands in the persistent
  // store, so even a reload (not just a re-render/version switch) keeps it.
  document.getElementById('comment-list').addEventListener('input', (e) => {
    if (e.target && e.target.classList && e.target.classList.contains('reply-ta')) {
      setDraft(e.target.dataset.replyFor, e.target.value || '');
    }
  });

  wireChips();
  wirePopover();
  wirePinPopover();
  wireGeneralFeedback();
  wireArchivedToggle();
  wireDrawerControls();
  wireRailCollapse();
  wirePushSession();
  wireBridge();

  await loadStore();
  await loadMeta();
  await loadSessionMonitor();

  const urlV = new URL(window.location.href).searchParams.get('v');
  CURRENT_VERSION = urlV || META.current || (META.history && META.history.length ? META.history[META.history.length - 1].version : null);

  IDENTITY = await resolveIdentity();
  AUTHOR = authorValue(IDENTITY);
  updateAuthorIndicator();

  await loadSeen();
  await loadReadState();

  document.getElementById('hdr-sub').textContent = CURRENT_VERSION ? ('Version ' + CURRENT_VERSION) : '';

  if (CURRENT_VERSION) loadIframe(CURRENT_VERSION);
  renderAll();
  const gfInit = document.getElementById('gf-ta');
  if (gfInit && CURRENT_VERSION) gfInit.value = DRAFTS['gf:' + CURRENT_VERSION] || '';

  // Poll for new comments every 8s (mirrors legacy template.html behavior).
  // Skip the re-render when nothing changed — an unconditional 8s re-render
  // would discard drawer scroll position and interrupt in-progress typing
  // for no reason (drafts are additionally preserved in renderDrawer).
  let lastSnap = JSON.stringify(STORE) + JSON.stringify(META) + JSON.stringify(READ);
  setInterval(async () => {
    await loadStore();
    await loadMeta();
    await loadReadState();
    await loadSessionMonitor();
    const snap = JSON.stringify(STORE) + JSON.stringify(META) + JSON.stringify(READ);
    if (snap !== lastSnap) {
      lastSnap = snap;
      renderAll();
    } else {
      updatePushCounter();
    }
  }, 8000);
}

document.addEventListener('DOMContentLoaded', init);
})();
