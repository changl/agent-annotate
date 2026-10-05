// ── annotate universal shell — chrome logic ──────────────────────────
// This file drives the version-stable chrome: version rail, comment
// drawer, ball-in-court badges, author identity, general feedback.
// Cross-frame communication goes through postMessage pinned to this
// page's own origin (see the "Bridge" section).
// Identical behavior across every slug/project/version.
(function () {
'use strict';

// ── Base path + API helpers ───────────────────────────────────────
// The shell is served at <public_base_path>/ ; all API calls are relative
// to that same origin+prefix so this works both on localhost and behind
// the Cloudflare tunnel's /schema (or /prem-fin, etc.) prefix.
// One page per project: this shell serves every document tab of the
// project page — Review (the page's own versions) and Plans (the selected
// plan's revisions, plans/<id>/vN.html). Both share the page's one comment
// store; a comment belongs to a document by its category and `doc`. DOC is
// the document whose version state is loaded into the variables below;
// DOC_STATE keeps the other document's, and withDoc() swaps it in for a
// synchronous read (counts, Send summary). VIEW_DOC is the document on
// screen (null while Library, Findings or Linked pages is shown); rendering
// only ever happens for VIEW_DOC.
let DOCS = ['review'];
let DOC = 'review';
let VIEW_DOC = null;
let PLANS = [];       // [{id, title, current, history}] from ./api/categories
let PLAN_ID = null;   // the plan the Plans tab shows
function apiUrl(path) {
  return path; // relative fetch — browser resolves against current document URL
}
const BRIDGE_ORIGIN = (() => {
  const origin = window.location.origin;
  if (/^https?:\/\//.test(origin)) return origin;
  try {
    const parentOrigin = window.parent.location.origin;
    const inherited = parentOrigin === 'null' ? window.parent.origin : parentOrigin;
    return /^https?:\/\//.test(inherited) ? inherited : null;
  } catch { return null; }
})();
function postToFrame(data) {
  const frame = document.getElementById('content-frame');
  if (frame && frame.contentWindow && BRIDGE_ORIGIN) frame.contentWindow.postMessage(data, BRIDGE_ORIGIN);
}
// The document a comment belongs to: 'review', 'plans' (the plan on
// screen), or null for Library and Findings items.
function commentCategory(c) {
  if (c.category) return c.category;
  return String(c.anchor_id || '').startsWith('copy:') ? 'library' : 'review';
}
function docOf(c) {
  const cat = commentCategory(c);
  if (cat === 'review') return 'review';
  if (cat === 'plans' && PLAN_ID && c.doc === 'plan:' + PLAN_ID) return 'plans';
  return null;
}

let STORE = { schema_version: 2, anchors: {}, archived: {} };
let META = { current: null, history: [], content_stamps: {} };
let SEEN = {}; // { version: {ts, whole_hash, section_hashes} }
let READ = {}; // { commentId: {ts, sig} } — this viewer's per-comment read state
let NUM_MAP = {}; // { commentId: n } — canonical item number shared by rail, body and pin
let CURRENT_VERSION = null;
let AUTHOR = null;
let IDENTITY = null;
let SESSION_MONITOR = { active: false, monitor_count: 0, delivery: 'queued' };
// v2.19 server capabilities, probed ONCE at init via GET ./api/capabilities.
// null = legacy server (404) → every new behavior is off and the chrome acts
// exactly as before: no defer_push, no round bar, no /api/rounds calls.
let CAPS = null;
// Feedback prototype: the chip filters, "All versions" and "Unread first" are
// replaced by collapsible sections (B2) and the History tab (B3).
// SECTION_OPEN[key] overrides the default open state of a section.
let SECTION_OPEN = {};
const SECTION_DEFAULT_OPEN = { needs: true, ready: true, waiting: true, done: false, archived: false };
let activeTab = 'feedback';
const cardExpanded = {};   // C1: answered cards shown in full instead of one line
const earlierOpen = {};    // B3: "n earlier replies" expanded
let openMenuId = null;     // C3: the card whose ⋯ menu is open
let highlightedCommentId = null;

// ── Icons (Lucide, ISC License, (c) Lucide Icons and Contributors) ──
const ICONS = {
  pencil: '<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/>',
  plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
  more: '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
  moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
  chevDown: '<path d="m6 9 6 6 6-6"/>',
  chevRight: '<path d="m9 18 6-6-6-6"/>',
  chevUp: '<path d="m18 15-6-6-6 6"/>',
  locate: '<line x1="2" x2="5" y1="12" y2="12"/><line x1="19" x2="22" y1="12" y2="12"/><line x1="12" x2="12" y1="2" y2="5"/><line x1="12" x2="12" y1="19" y2="22"/><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="3"/>',
};
function ico(name) {
  return '<svg class="i" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' + (ICONS[name] || '') + '</svg>';
}

// ── Theme (X1/E4): stock daisyUI dark (default) and light ──
function currentTheme() {
  return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
}
function applyTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  const content = document.getElementById('content-frame');
  try { if (content && content.contentDocument) content.contentDocument.documentElement.setAttribute('data-theme', t); } catch {}
  postToFrame({ type: 'annotate:theme', theme: t });
  document.dispatchEvent(new CustomEvent('annotate:theme', { detail: t }));
  const btn = document.getElementById('theme-toggle');
  if (btn) {
    const next = t === 'dark' ? 'light' : 'dark';
    btn.innerHTML = ico(t === 'dark' ? 'sun' : 'moon');
    btn.setAttribute('aria-label', 'Switch to ' + next + ' theme');
    btn.title = 'Switch to ' + next + ' theme';
  }
}
document.getElementById('content-frame').addEventListener('load', () => applyTheme(currentTheme()));
try { const t = localStorage.getItem('annotate:theme'); if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t); } catch {}
// T11: unposted drafts survive re-renders, VERSION SWITCHES, and reloads.
// Keys: comment id for reply boxes, 'gf:<version>' for general feedback.
// Drafts are kept per page and document, since two documents can share a
// version name (Review v6, Plans v6).
let DRAFTS = {};
const draftsSaveTimer = {};
function draftsKey(doc) {
  return 'annotate:drafts:' + location.pathname + ':' + (doc === 'plans' ? 'plan:' + PLAN_ID : doc);
}
function loadDrafts(doc) {
  try { return JSON.parse(localStorage.getItem(draftsKey(doc)) || '{}') || {}; } catch { return {}; }
}
function saveDraftsSoon() {
  const key = draftsKey(DOC), drafts = DRAFTS;
  clearTimeout(draftsSaveTimer[key]);
  draftsSaveTimer[key] = setTimeout(() => {
    try { localStorage.setItem(key, JSON.stringify(drafts)); } catch {}
  }, 400);
}
function setDraft(key, value) {
  if (value) DRAFTS[key] = value;
  else delete DRAFTS[key];
  saveDraftsSoon();
}

// ── Compact layout detection ─────────────────────────────────────────
// Matches shell.css exactly.  The width includes constrained desktop
// webviews (not just phones): with both fixed rails expanded, anything below
// 1160px would leave less than a useful 600px document canvas.
function isMobileLayout() {
  return window.matchMedia('(max-width: 1160px), (max-height: 480px)').matches;
}

// The drawer becomes a bottom sheet on mobile (body.is-mobile-sheet-open,
// see shell.css); this is the single place that flips it, so the FAB, the
// drawer's own close control, and any future callers stay in sync. Sheet
// open-state and the drawer's own scroll position (renderDrawer) both
// survive the 8s poll's re-render because neither lives inside the
// re-rendered DOM.
function setMobileSheetOpen(open) {
  document.body.classList.toggle('is-mobile-sheet-open', open);
  if (open) requestAnimationFrame(() => syncExcerptClamps(document.getElementById('comment-list')));
}
function isMobileSheetOpen() {
  return document.body.classList.contains('is-mobile-sheet-open');
}

// ── OAuth identity ─────────────────────────────────────────────────
function normalizeIdentity(payload) {
  if (!payload || typeof payload !== 'object') return null;
  const nested = payload.identity || payload.user || {};
  const email = payload.email || nested.email || payload.author_email || null;
  const name = payload.name || payload.display_name || nested.name || nested.display_name || null;
  if (!email || email === 'anonymous') return null;
  const reviewerAuthors = Array.isArray(payload.reviewer_authors) ? payload.reviewer_authors.filter(v => typeof v === 'string') : [String(email).trim()];
  return { email: String(email).trim(), name: name ? String(name).trim() : null, reviewer_authors: reviewerAuthors };
}

function authorValue(identity) {
  if (!identity) return null;
  if (identity.email.startsWith('reviewer:')) return identity.name || 'Reviewer';
  return identity.name && identity.name !== identity.email
    ? `${identity.name} <${identity.email}>`
    : identity.email;
}

async function resolveIdentity() {
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
    : '\u{1F512} Review access required';
  ind.title = IDENTITY ? 'Reviewer identity' : 'Open the private review link';
  // E1: the reviewer lives in the avatar menu; the button shows initials.
  const ini = document.getElementById('who-initials');
  if (ini) {
    const src = IDENTITY ? (IDENTITY.name || IDENTITY.email || '') : '';
    const words = src.replace(/[<(].*$/, '').trim().split(/\s+/).filter(Boolean);
    ini.textContent = words.length ? words.slice(0, 2).map(w => w[0].toUpperCase()).join('') : '?';
  }
}

function authorLabel(record) {
  if (!record) return 'anonymous';
  const id = record.author_email || record.author || '';
  if (id.startsWith('reviewer:')) return record.author_name || 'Reviewer';
  if (record.author_name && record.author_email && record.author_name !== record.author_email) {
    return `${record.author_name} <${record.author_email}>`;
  }
  return record.author_email || record.author || 'anonymous';
}

// ── HTTP helpers ──────────────────────────────────────────────────
function authorQuery() {
  return AUTHOR ? ('?author=' + encodeURIComponent(AUTHOR)) : '';
}

// The page's one comment store, shared by every document and tab.
async function loadStore() {
  try {
    const r = await fetch(apiUrl('./comments.json'), { cache: 'no-cache', signal: AbortSignal.timeout(10000) });
    if (!r.ok) return false;
    const store = await r.json();
    STORE = store && store.schema_version === 2 ? store : { schema_version: 2, anchors: {}, archived: {} };
    computeNumbers();
    return true;
  } catch { return false; }
}

// ── Stable page-wide item numbering ─────────────────────────────────
// Explicit `number` is canonical. Legacy cards recover an unsuffixed Q<number>
// from their prompt; everything else receives the next unused number in
// creation order over live + archived history. One map drives rail, pin and
// body order, so a response item never has three competing labels.
function computeNumbers() {
  NUM_MAP = {};
  const all = flattenStore(true);
  const used = new Set();
  for (const c of all) {
    if (Number.isInteger(c.number) && c.number > 0 && !NUM_MAP[c.id]) {
      NUM_MAP[c.id] = c.number;
      used.add(c.number);
    }
  }
  for (const c of all) {
    if (NUM_MAP[c.id]) continue;
    const prompt = c.decision_request && c.decision_request.prompt;
    const match = typeof prompt === 'string' ? prompt.match(/^Q(\d+)(?![0-9A-Za-z])/i) : null;
    const n = match ? Number(match[1]) : 0;
    if (n > 0) {
      NUM_MAP[c.id] = n;
      used.add(n);
    }
  }
  let next = used.size ? Math.max(...used) + 1 : 1;
  all.sort((a, b) =>
    new Date(a.created_at) - new Date(b.created_at) || String(a.id).localeCompare(String(b.id)));
  for (const c of all) {
    if (NUM_MAP[c.id]) continue;
    while (used.has(next)) next++;
    NUM_MAP[c.id] = next;
    used.add(next);
    next++;
  }
}

// A document's versions: the page's own (current.meta.json) for Review,
// the selected plan's revisions (./api/plans/<id>) for Plans.
async function loadMeta() {
  const doc = DOC;
  try {
    const url = doc === 'plans' ? './api/plans/' + encodeURIComponent(PLAN_ID) : './current.meta.json';
    const r = await fetch(apiUrl(url), { cache: 'no-cache', signal: AbortSignal.timeout(10000) });
    if (!r.ok) return false;
    const meta = await r.json();
    if (doc !== DOC) return false;
    if (doc === 'plans') { META = { current: meta.current, history: meta.history || [], content_stamps: {}, title: meta.title }; return true; }
    if (JSON.stringify(meta.history || []) !== JSON.stringify(META.history || [])) historyDirty = true;
    if (meta.project_info && meta.delivery_status) {
      HAS_SUMMARY = true;
      SUMMARY_PROJECT = meta.project_info;
      SUMMARY_DELIVERY = meta.delivery_status;
      delete meta.project_info;
      delete meta.delivery_status;
    }
    META = meta;
    return true;
  } catch { return false; }
}

async function loadSeen() {
  const doc = DOC;
  // ↑NEW compares Review's content stamps; plan revisions have none.
  if (doc !== 'review') { SEEN = {}; return true; }
  try {
    const r = await fetch(apiUrl('./api/seen' + authorQuery()), { cache: 'no-store' });
    if (!r.ok) return false;
    const j = await r.json();
    if (doc !== DOC) return false;
    SEEN = j.seen || {};
    return true;
  } catch { return false; }
}

async function markSeen(version) {
  if (DOC !== 'review') return;
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

// Read state is per viewer and shared by every document.
async function loadReadState() {
  try {
    const r = await fetch(apiUrl('./api/read-state' + authorQuery()), { cache: 'no-store', signal: AbortSignal.timeout(10000) });
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
  return postReadItems(items);
}
// Library items are read by key ('copy:<block id>') at their latest revision.
function markReadItems(list) {
  const now = new Date().toISOString();
  const items = list.filter(it => !(READ[it.id] && READ[it.id].sig === it.sig));
  items.forEach(it => { READ[it.id] = { ts: now, sig: it.sig }; });
  return postReadItems(items);
}
function postReadItems(items) {
  if (!items.length) return Promise.resolve(null);
  return fetch(apiUrl('./api/read-state' + authorQuery()), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items }),
  }).then(r => { refreshCountsSoon(); return r; }).catch(() => null);
}
// The header's unread counts are the server's; refetch them once a burst of
// read marks has landed, so opening an item clears its count at once.
let countsRefresh = null;
function refreshCountsSoon() {
  clearTimeout(countsRefresh);
  countsRefresh = setTimeout(async () => { if (await loadCategories() && window.AA) window.AA.changed(); }, 250);
}

function findCommentById(id) {
  for (const c of flattenStore(true)) if (c.id === id) return c;
  return null;
}

// `extra` carries a Library/Findings comment's category; a Plans comment
// names its plan document.
async function apiCreateComment(anchorId, anchorLabel, text, version, target, extra) {
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
        ...(extra || (DOC === 'plans' ? { category: 'plans', doc: 'plan:' + PLAN_ID } : {})),
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

async function apiPushSingle(id) {
  try {
    const r = await fetch(apiUrl('./api/comments/' + encodeURIComponent(id) + '/push' + authorQuery()), { method: 'POST' });
    if (r.ok) return await r.json();
  } catch {}
  return null;
}

// Returns { fallback: true } when the live server predates /decision (404/405)
// so the caller can drop into the composite fallback path instead.
// v2.19: in round mode the verdict is posted with defer_push so the server
// parks it (decision.round_pending) instead of emitting a session_push per
// click; POST /api/rounds/submit later sends the whole round at once.
async function apiDecision(id, verdict, text) {
  try {
    const r = await fetch(apiUrl('./api/comments/' + encodeURIComponent(id) + '/decision' + authorQuery()), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        verdict,
        text: text || undefined,
        author: AUTHOR,
        author_name: IDENTITY && IDENTITY.name,
        author_email: IDENTITY && IDENTITY.email,
        ...(roundsEnabled() ? { defer_push: true } : {}),
      }),
    });
    if (r.status === 404 || r.status === 405) return { fallback: true };
    if (r.ok) return await r.json();
  } catch {}
  return null;
}

// ── v2.19 capabilities + review rounds ───────────────────────────────
// One probe per page load. A 404 (old server) or a network error leaves CAPS
// null; nothing ever re-probes, so a legacy server sees exactly one extra
// request and never a /api/rounds call.
async function loadCapabilities() {
  CAPS = null;
  try {
    const r = await fetch(apiUrl('./api/capabilities'), { cache: 'no-store' });
    if (r.ok) {
      const j = await r.json();
      if (j && typeof j === 'object') CAPS = j;
    }
  } catch {}
  return CAPS;
}
function roundsEnabled() {
  return !!(CAPS && CAPS.rounds);
}
// D2: true when the live server advertises the "changes" verdict. A legacy
// server (no /api/capabilities, or one that predates D2) leaves this false
// and every decision card keeps its pre-D2 "Comment" button.
function changesEnabled() {
  return !!(CAPS && Array.isArray(CAPS.verdicts) && CAPS.verdicts.indexOf('changes') !== -1);
}
// The third verdict's id on THIS server: 'changes' where advertised,
// 'comment' otherwise. Both spellings in a decision_request map onto it, so
// an old cards.json saying "comment" shows "Request changes" on a new server
// and a new one saying "changes" still works against an old server.
function textVerdictId() {
  return changesEnabled() ? 'changes' : 'comment';
}
// D3: the verdict a click on a custom option id posts. `select` where the
// server advertises it, `comment` against anything older — which is what the
// chrome always posted, so an old server behaves exactly as it did.
function selectVerdictId() {
  return (CAPS && Array.isArray(CAPS.verdicts) && CAPS.verdicts.indexOf('select') !== -1)
    ? 'select' : 'comment';
}
function canonicalOptionId(id) {
  return (id === 'comment' || id === 'changes') ? textVerdictId() : id;
}
async function apiRoundSubmit(note, send) {
  try {
    const r = await fetch(apiUrl('./api/rounds/submit' + authorQuery()), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign({ note: note || undefined, version: CURRENT_VERSION }, send || {})),
    });
    if (r.ok) { historyDirty = true; return await r.json(); }
  } catch {}
  return null;
}
async function apiRoundDiscard() {
  try {
    const r = await fetch(apiUrl('./api/rounds/discard' + authorQuery()), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    if (r.ok) return await r.json();
  } catch {}
  return null;
}
function isRoundPending(c) {
  return !!(c && c.decision && c.decision.round_pending &&
    IDENTITY && (IDENTITY.reviewer_authors || [IDENTITY.email]).includes(c.decision.by) &&
    c.status !== 'archived' && c.status !== 'resolved_in_version');
}
function hasDecisionRequest(c) {
  return !!(c && c.decision_request &&
    c.status !== 'archived' && c.status !== 'resolved_in_version');
}

// OLD-SERVER FALLBACK: composes the same outcome from routes that predate
// /decision. decision_request stays unresolved server-side (no c.decision
// field is ever set), so the card's buttons remain live after a refresh —
// acceptable degraded behavior, documented in CHANGELOG.
async function apiDecisionFallback(id, verdict, text) {
  const verdictText = { accept: '✓ Accepted', reject: '✗ Rejected' };
  const isText = verdict === 'comment' || verdict === 'changes';
  let replyText = verdict === 'changes' ? '↻ Changes requested: ' + text
    : verdict === 'comment' ? '💬 Answer in words: ' + text : verdictText[verdict];
  if (!isText && text) replyText += '\n\n' + text;
  const replied = await apiReply(id, replyText);
  if (!replied) return null;
  const statusMap = { accept: 'user_confirmed', reject: 'open', comment: 'open', changes: 'open' };
  await apiPutComment(id, { status: statusMap[verdict] });
  return await apiPushSingle(id);
}

async function apiPushAll(send) {
  try {
    const r = await fetch(apiUrl('./api/push-session'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(send || {}) });
    if (r.ok) return await r.json();
  } catch {}
  return null;
}

async function loadSessionMonitor() {
  try {
    const r = await fetch(apiUrl('./api/session-monitor'), { cache: 'no-store', signal: AbortSignal.timeout(10000) });
    if (r.ok) SESSION_MONITOR = await r.json();
  } catch {
    SESSION_MONITOR = { active: false, monitor_count: 0, delivery: 'queued' };
  }
  return SESSION_MONITOR;
}

// ── Ball-in-court classification ───────────────────────────────────
// needsReview  = unanswered decision card, OR (open AND last reply is the agent's)
// waitingAgent = open AND (no replies OR last reply is the reviewer's)
// done         = addressed_by_agent, user_confirmed, resolved_in_version, archived
// An item stays in front of the reviewer only while it still needs them
// (Chang, 2026-09-23). The agent addressing or withdrawing it ends that; a
// reviewer reply reopens it on the server.
function isAgentAuthor(a) {
  return !!a && a.indexOf('agent:') === 0;
}
function lastReplyAuthor(c) {
  const replies = c.replies || [];
  return replies.length ? replies[replies.length - 1].author : null;
}
function classify(c) {
  // An unresolved decision card is by definition waiting on the REVIEWER,
  // even though the agent authored it (an agent-authored open comment would
  // otherwise read as "waiting on agent" and the "Needs my review" chip
  // would stay at 0 with nine open questions on the page). Once a verdict
  // exists the ordinary rules below apply (accept → done, reject → waiting).
  if (isUnresolvedDecision(c)) return 'review';
  if (c.status === 'open') {
    return isAgentAuthor(lastReplyAuthor(c)) ? 'review' : 'waiting';
  }
  // user_confirmed, resolved_in_version or archived
  return 'done';
}

// The one status text for an item, shared by the rail, the pin popover and
// the page body's baked question cards, so all three always agree.
function statusLabel(c, cls) {
  if (cls === 'review') return 'Needs my review';
  if (cls === 'waiting') return 'Waiting on agent';
  if (c.status === 'archived') return 'Archived';
  if (c.status === 'resolved_in_version') return `Resolved in ${c.resolved_in_version || 'later version'}`;
  if (c.status === 'addressed_by_agent') return 'Addressed';
  return 'Done';
}

// Every comment on the page (all documents and tabs).
function flattenStore(includeArchived) {
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
// The comments of the document whose state is loaded (DOC).
function flattenAll(includeArchived) {
  return flattenStore(includeArchived).filter(c => docOf(c) === DOC);
}

function countsForVersion(version) {
  // A card that follows the viewer is attributed to the version ON SCREEN
  // (where it is actionable) rather than to its origin version, so the
  // rail's red badge agrees with the drawer's "Needs my review" chip.
  const all = flattenAll(false).filter(c => !version || (
    followsViewer(c) ? version === CURRENT_VERSION : c.version === version));
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

// Persistent project modules are independent of whichever review version is open.
let PROJECT = { modules: [] };
let HAS_SUMMARY = false;
let SUMMARY_PROJECT = null;
let SUMMARY_DELIVERY = null;
let projectSnapshot = '';
function projectPreference(key, value) {
  try {
    const storageKey = 'annotate:project:' + location.pathname + DOC + ':' + key;
    if (value !== undefined) localStorage.setItem(storageKey, value ? 'open' : 'closed');
    return localStorage.getItem(storageKey);
  } catch { return null; }
}
// E2 (Chang: "we can consolidate progress and history … documents or other
// assets and decisions … can be additional tabs"): the project's progress and
// notes modules render at the top of the History tab; a links module becomes
// its own tab (named after the module) between Feedback and History.
function projectLinkItems(module) {
  return module.items.map(item => {
    let url; try { url = new URL(item.url); } catch { return ''; }
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return '';
    return `<li><a href="${escAttr(url.href)}" target="_blank" rel="noopener noreferrer">${esc(item.label)}</a>${item.description ? `<span class="project-detail">${ticketsHTML(item.description)}</span>` : ''}</li>`;
  }).join('');
}
// PROJECT.tabs of kind reference (F5) are listed with the project's links.
function referenceTabs() {
  return (PROJECT.tabs || []).filter(t => t && t.url && (!t.kind || t.kind === 'reference'));
}
// U-01 + F2: the header names the project only — PROJECT.title, else the
// document's own title.
let documentTitle = '';
function updateProjectTitle() {
  const title = PROJECT.title || documentTitle || 'annotate';
  const header = document.getElementById('hdr-title');
  header.textContent = title;
  header.title = title;
  if (window.AA) window.AA.setTitle(title);
}
const PROJECT_STATE_BADGE = { done: 'badge-success', blocked: 'badge-error', in_progress: 'badge-info', todo: 'badge-ghost' };
function renderProject() {
  // The project's links and progress belong to Review; a plan has none.
  if (DOC === 'review') updateProjectTitle();
  const panel = document.getElementById('project-panel-' + DOC);
  if (!panel) return;
  const modules = DOC === 'review' ? (PROJECT.modules || []) : [];
  const links = modules.filter(m => m.kind === 'links');
  const rest = modules.filter(m => m.kind !== 'links');
  const refs = DOC === 'review' ? referenceTabs() : [];
  if (refs.length) links.push({ id: 'reference-tabs', title: 'Documents', items: refs.map(t => ({ label: t.label, url: t.url })) });
  // Documents tab
  const docTab = document.getElementById('tab-documents');
  const docBody = document.getElementById('documents-body');
  if (DOC !== VIEW_DOC) {
    // Only the document on screen fills the Documents tab.
  } else if (links.length) {
    docTab.hidden = false;
    docTab.textContent = links.length === 1 ? links[0].title : 'Documents';
    docBody.innerHTML = links.map(m => `<section class="hist-section">${links.length > 1 ? `<h3 class="hist-lbl">${esc(m.title)}</h3>` : ''}<ul class="doc-list">${projectLinkItems(m)}</ul></section>`).join('');
  } else {
    docTab.hidden = true;
    docBody.innerHTML = '';
    if (activeTab === 'documents') setActiveTab('feedback');
  }
  // Progress (History tab)
  if (!rest.length) { panel.hidden = true; panel.innerHTML = ''; return; }
  panel.hidden = false;
  panel.innerHTML = `<div class="project-heading"><strong>${esc(PROJECT.title || 'Project links and progress')}</strong><small>${PROJECT.updated_at ? 'Updated ' + esc(fmtTs(PROJECT.updated_at)) : ''}</small></div>` + rest.map((module) => {
    const preference = projectPreference(module.id);
    // 2.20: progress and notes modules start collapsed.
    const open = preference ? preference === 'open' : false;
    const items = module.items.map(item => {
      if (module.kind === 'progress') return `<li><span class="badge badge-sm badge-soft ${PROJECT_STATE_BADGE[item.status] || 'badge-ghost'} project-state">${esc(item.status.replace(/_/g, ' '))}</span>${safeHttpUrl(item.url) ? `<a href="${escAttr(safeHttpUrl(item.url))}" target="_blank" rel="noopener noreferrer">${esc(item.label)}</a>` : ticketsHTML(item.label)}${item.failed_count ? `<span class="badge badge-error badge-soft badge-sm failed-pill">failed ${esc(item.failed_count)}x</span>` : ''}${item.detail ? `<span class="project-detail">${ticketsHTML(item.detail)}</span>` : ''}</li>`;
      return `<li>${ticketsHTML(item.text)}</li>`;
    }).join('');
    return `<details class="project-module" data-module="${escAttr(module.id)}" ${open ? 'open' : ''}><summary>${esc(module.title)} (${module.items.length})</summary><ul>${items}</ul></details>`;
  }).join('');
  panel.querySelectorAll('details').forEach(node => {
    node.addEventListener('toggle', () => projectPreference(node.dataset.module, node.open));
  });
}
async function loadProject() {
  try {
    if (HAS_SUMMARY) {
      const snapshot = JSON.stringify(SUMMARY_PROJECT);
      if (snapshot !== projectSnapshot) { PROJECT = SUMMARY_PROJECT; projectSnapshot = snapshot; renderProject(); }
      return;
    }
    const doc = DOC;
    const response = await fetch(apiUrl('./api/project'), { cache: 'no-store', signal: AbortSignal.timeout(10000) });
    if (!response.ok) return;
    const data = await response.json();
    if (doc !== DOC) return;
    const snapshot = JSON.stringify(data);
    if (snapshot !== projectSnapshot) { PROJECT = data; projectSnapshot = snapshot; renderProject(); }
  } catch {}
}
// F17 + U-07: History lists the rounds the server recorded, newest first,
// each with its answers; the header keeps the latest one beside Send.
let HISTORY_DATA = null;
let historyDirty = true;
let historyLoading = false;
async function loadHistory() {
  if ((HISTORY_DATA && !historyDirty) || historyLoading) return;
  historyLoading = true;
  try {
    const r = await fetch(apiUrl('./api/history'), { cache: 'no-store', signal: AbortSignal.timeout(10000) });
    const data = await r.json();
    if (!r.ok || !Array.isArray(data.rounds)) throw new Error('history');
    HISTORY_DATA = data;
    historyDirty = false;
    if (window.AA) window.AA.changed();
  } catch { /* History keeps the last rounds it had */ } finally { historyLoading = false; }
}
function roundItemText(answer) {
  const c = answer.comment_id ? findCommentById(answer.comment_id) : null;
  const n = (c && NUM_MAP[c.id]) || answer.number;
  const prompt = c ? displayPrompt(c) || firstLine(c.text) : (answer.prompt || '');
  const ans = answer.text ? (answer.verdict === 'select' ? answer.text.replace(/^Selected:\s*/, '') : answer.text)
    : (DECISION_VERDICT_LABEL[answer.verdict] || answer.verdict || '');
  // A plain comment is its own label; never repeat it as the answer.
  const same = ans && firstLine(ans) === prompt;
  return (n ? '#' + n + ' · ' : '') + prompt + (ans && !same ? ' → ' + firstLine(ans) : '');
}
// The rounds the server recorded, newest first, each line tagged with its
// tab (app/rail.js renders them under History · Sent rounds).
// One Send leaves a round record and/or a push record, tied by send_id; its
// receipt is the Send summary's lines (every tab). Older records without a
// receipt are listed from their answers and edits.
function sentRounds() {
  const groups = [], byId = {};
  for (const r of ((HISTORY_DATA && HISTORY_DATA.rounds) || [])) {
    if (r.send_id && byId[r.send_id]) { byId[r.send_id].push(r); continue; }
    const g = [r];
    if (r.send_id) byId[r.send_id] = g;
    groups.push(g);
  }
  return groups.map(g => {
    const withReceipt = g.find(r => Array.isArray(r.receipt) && r.receipt.length);
    const ts = g.map(r => r.ts).sort()[0];
    if (withReceipt) {
      const items = withReceipt.receipt.map(it => ({ cat: it.cat, label: it.label, answer: it.answer || '' }));
      return { ts, result: 'Sent (' + items.length + ')', items, send_id: withReceipt.send_id };
    }
    return legacyRound(g.find(r => r.kind !== 'push') || g[0]);
  }).filter(r => r.items.length);
}
function legacyRound(r) {
  {
    const items = (r.answers || []).map(a => {
      const c = a.comment_id ? findCommentById(a.comment_id) : null;
      const cat = a.category || (c ? commentCategory(c) : 'review');
      const text = roundItemText(a);
      const at = text.indexOf(' → ');
      return { cat, label: at === -1 ? text : text.slice(0, at), answer: at === -1 ? '' : text.slice(at + 3) };
    });
    (r.edits || []).forEach(e => items.push({ cat: 'library', label: e.label || e.block_id, answer: 'Edited', block: e.block_id }));
    if (r.note) items.push({ cat: 'review', label: 'General feedback', answer: r.note });
    const n = (r.answers || []).length + (r.edits || []).length;
    return { ts: r.ts, result: 'Sent (' + n + ')', items };
  }
}
async function loadDelivery() {
  if (DOC !== VIEW_DOC) return;
  const node = document.getElementById('delivery-status');
  if (!CAPS || !CAPS.automatic_round_delivery) {
    node.hidden = !!CAPS;
    if (!CAPS) node.textContent = 'This server predates Finish review and automatic delivery. Update its agent-annotate runtime.';
    return;
  }
  try {
    let data = SUMMARY_DELIVERY;
    if (!HAS_SUMMARY) {
      const response = await fetch(apiUrl('./api/delivery'), { cache: 'no-store', signal: AbortSignal.timeout(10000) });
      if (!response.ok) return;
      data = await response.json();
    }
    node.hidden = !data.latest;
    if (data.latest) {
      const labels = {acknowledged: 'Owner read this feedback round; project work is tracked separately', pending: 'Feedback saved; owner wake-up pending', accepted: 'Owner prompt accepted by Orca; agent response pending', started: 'Owner turn started; agent response pending', uncertain: 'Feedback saved; prompt delivery unproven', superseded: 'Page owner changed before this round was delivered'};
      node.textContent = (labels[data.latest.state] || 'Feedback delivery: ' + data.latest.state) + (data.latest.detail && ['pending', 'uncertain'].includes(data.latest.state) ? '. ' + data.latest.detail : '');
    }
  } catch {}
}

// ── Version rail ─────────────────────────────────────────────────
// final/: each document's versions sit in its own History section
// (#vrail-body-<doc>); a version of a document that is not on screen opens
// that document's tab at that version.
function renderVersionRail() {
  const body = document.getElementById('vrail-body-' + DOC);
  if (!body) return;
  const doc = DOC;
  const focusedVersion = document.activeElement && document.activeElement.closest && document.activeElement.closest('#vrail-body-' + doc + ' .vrow') ? document.activeElement.closest('.vrow').dataset.version : null;
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
      ? `<span class="badge badge-error badge-xs vrow-badge">${counts.review}</span>`
      : '';
    const newHtml = isNew ? '<span class="vrow-new" title="Content updated since your last visit">↑NEW</span>' : '';
    return `<button type="button" aria-current="${isCur ? 'page' : 'false'}" class="vrow ${isCur ? 'current' : ''}" data-version="${escAttr(h.version)}" title="${escAttr(h.label || '')}">
      ${dotHtml}
      <span class="vrow-label">${esc(h.version)}${h.label ? ' &middot; ' + esc(h.label) : ''}</span>
      ${newHtml}
      ${badgeHtml}
    </button>`;
  }).join('');
  Array.from(body.querySelectorAll('.vrow')).forEach(row => {
    row.addEventListener('click', () => {
      if (doc !== VIEW_DOC) { if (window.AA) window.AA.go({ view: doc, v: row.dataset.version }); return; }
      switchVersion(row.dataset.version);
      // Phone: the sheet covers the document; show the version just picked.
      if (isMobileLayout()) setMobileSheetOpen(false);
    });
  });
  // U-14: the version list is a keyboard listbox.
  const rows = [...body.querySelectorAll('.vrow')];
  rows.forEach(r => {
    r.setAttribute('role', 'option');
    r.setAttribute('aria-selected', String(r.dataset.version === CURRENT_VERSION));
    r.tabIndex = r.dataset.version === CURRENT_VERSION ? 0 : -1;
    r.addEventListener('keydown', e => {
      let n = rows.indexOf(r);
      if (e.key === 'ArrowDown') n++;
      else if (e.key === 'ArrowUp') n--;
      else if (e.key === 'Home') n = 0;
      else if (e.key === 'End') n = rows.length - 1;
      else return;
      e.preventDefault();
      const next = rows[Math.max(0, Math.min(rows.length - 1, n))];
      rows.forEach(x => { x.tabIndex = x === next ? 0 : -1; });
      next.focus();
    });
  });
  const restore = focusedVersion && !document.getElementById('history-body').hidden && (!isMobileLayout() || isMobileSheetOpen()) && rows.find(r => r.dataset.version === focusedVersion);
  if (restore) { rows.forEach(r => { r.tabIndex = r === restore ? 0 : -1; }); restore.focus(); }
  if (doc === VIEW_DOC) renderVersionBanner();
}
// U-10: an older version on screen says so, with the way back.
function renderVersionBanner() {
  const banner = document.getElementById('unified-version-banner');
  const latest = META.current || ((META.history || []).slice(-1)[0] || {}).version;
  banner.hidden = !latest || CURRENT_VERSION === latest;
  if (banner.hidden) return;
  banner.innerHTML = 'Viewing ' + esc(CURRENT_VERSION) + ' (older) · Latest is ' + esc(latest) + ' — <button type="button" class="btn btn-link btn-sm">back to latest</button>';
  banner.querySelector('button').onclick = () => switchVersion(latest);
}
// (The phone header's version <select> is gone: History is the one version
// picker on every layout — B3.)

function switchVersion(v) {
  if (!v || v === CURRENT_VERSION) return;
  CURRENT_VERSION = v;
  loadIframe(v);
  // final/: the version is part of the page's hash (#view=plans&v=v5), since
  // one URL holds several documents.
  if (window.AA) window.AA.noteVersion(DOC, v);
  renderAll();
  // T11: the general-feedback draft is per-version
  const gf = document.getElementById('gf-ta');
  if (gf) gf.value = DRAFTS['gf:' + v] || '';
  renderGeneralFeedback();
  updateSendState();
}

function loadIframe(v) {
  const frame = document.getElementById('content-frame');
  frame.dataset.doc = DOC;
  frame.dataset.version = v;
  const doc = DOC;
  frame.onload = () => {
    if (doc !== 'review') return;
    try { documentTitle = frame.contentDocument.title || ''; } catch { /* foreign content keeps the last title */ }
    if (DOC === 'review') updateProjectTitle();
  };
  frame.src = doc === 'plans'
    ? './plans/' + encodeURIComponent(PLAN_ID) + '/' + encodeURIComponent(v) + '.html'
    : './content?v=' + encodeURIComponent(v);
}

// ── Drawer ───────────────────────────────────────────────────────
function esc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function escAttr(s) { return esc(s).replace(/'/g, '&#39;'); }
function safeHttpUrl(value) {
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : '';
  } catch { return ''; }
}
// Escaped text with known Linear issue ids (PROJECT.issue_links) as links.
function ticketsHTML(value) {
  const text = String(value == null ? '' : value);
  const links = PROJECT.issue_links || {};
  const ids = /(?<![A-Za-z0-9_-])[A-Z][A-Z0-9]{0,20}-[1-9][0-9]{0,9}(?![A-Za-z0-9_-])/g;
  let html = '', offset = 0;
  for (const match of text.matchAll(ids)) {
    html += esc(text.slice(offset, match.index));
    const id = match[0];
    let url;
    try {
      const raw = Object.prototype.hasOwnProperty.call(links, id) ? links[id] : null;
      if (typeof raw === 'string' && !/[\\\u0000-\u0020\u007f]/.test(raw)) {
        const parsed = new URL(raw);
        if (parsed.protocol === 'https:' && parsed.hostname === 'linear.app' && !parsed.username && !parsed.password && !parsed.port) url = parsed.href;
      }
    } catch {}
    html += url ? `<a class="ticket-link" href="${escAttr(url)}" target="_blank" rel="noopener noreferrer" title="Open ${escAttr(id)} in Linear">${esc(id)}</a>` : esc(id);
    offset = match.index + id.length;
  }
  return html + esc(text.slice(offset));
}
function fmtTs(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch { return String(iso).slice(0, 16).replace('T', ' '); }
}

// A human section name, or '' — raw anchor ids (d:q19, s:…, tbl:…) are
// internal addresses and never shown beside the #N badge.
function anchorLabel(c) {
  return (c.anchor_label && c.anchor_label !== c.anchor_id) ? c.anchor_label : '';
}

// Drawer scope: null = every version ("All versions" toggle on), else the
// version currently shown in the iframe.
function drawerScope() {
  // B3: no "All versions" toggle; other versions are opened from History.
  return CURRENT_VERSION;
}
// Every stored verdict answers a card. `comment` is the free-text answer;
// a reviewer's reply on an unanswered card is recorded as one by the server.
function isAnswerVerdict(v) {
  return !!v;
}
function decisionAnswer(c) {
  const d = c && c.decision;
  return (d && isAnswerVerdict(d.verdict)) ? d : null;
}
// F9: an UNRESOLVED decision card must never disappear behind the version
// filter. After a republish the reviewer lands on vN while the agent's open
// questions were posed on v1; hiding them read as "where are the decision
// options?". Such cards are always listed (origin version chip still shown)
// and always get a pin/strip on the version being viewed. Resolved and plain
// comments keep the normal per-version scope.
function isUnresolvedDecision(c) {
  return !!(c && c.decision_request && !decisionAnswer(c) &&
    c.status !== 'archived' && c.status !== 'resolved_in_version' &&
    c.status !== 'addressed_by_agent');
}
// The prompt as shown: a legacy "Q10 …" prefix repeats the #10 badge, so it
// is dropped when it matches. One number per item.
function displayPrompt(c) {
  const p = (c && c.decision_request && c.decision_request.prompt) || '';
  const n = NUM_MAP[c.id];
  const m = p.match(/^\s*(?:Q|#)\s*(\d+)[\s:.\-—–]*/i);
  return (m && n && Number(m[1]) === n) ? p.slice(m[0].length) : p;
}
// Cards that follow the reviewer to whichever version is on screen: open
// questions, plus verdicts still pending in the current round (so the
// "Pending — not sent" chip and "Send now" stay reachable until submit).
function followsViewer(c) {
  return isUnresolvedDecision(c) || isRoundPending(c);
}
// True when the card belongs on the version being viewed: its own version,
// or any version while it follows the viewer.
function onCurrentVersion(c) {
  return c.version === CURRENT_VERSION || followsViewer(c);
}
function inScope(c) {
  const scope = drawerScope();
  return !scope || c.version === scope || followsViewer(c);
}
// Version the chrome should scroll/pin for: an unresolved card carried over
// from an older version is located on the CURRENT document (its anchor id
// is expected to survive a republish), not by switching back to its origin.
function gotoVersionFor(c) {
  if (isNewerThanViewed(c)) return c.version;
  return followsViewer(c) ? CURRENT_VERSION : c.version;
}
// Position in the published history, so any version label orders correctly.
function versionIndex(v) {
  return (META.history || []).findIndex(h => h.version === v);
}
// A card posed on a version published after the one being viewed.
function isNewerThanViewed(c) {
  const at = versionIndex(c.version), viewing = versionIndex(CURRENT_VERSION);
  return at !== -1 && viewing !== -1 && at > viewing;
}

// ── Sections (B2) and counts (B1) ────────────────────────────────────
// Four sections replace the chip filters, "Mark all read" and the per-card
// status pill: Needs you · Ready to send · Waiting on agent · Done (plus
// Archived at the bottom when there is any).
const SECTION_ORDER = ['needs', 'ready', 'waiting', 'done', 'archived'];
const SECTION_LABEL = { needs: 'Needs you', ready: 'Ready to send', waiting: 'Waiting on agent', done: 'Done', archived: 'Archived' };
function sectionOpen(k) {
  return Object.prototype.hasOwnProperty.call(SECTION_OPEN, k) ? !!SECTION_OPEN[k] : !!SECTION_DEFAULT_OPEN[k];
}
function setSectionOpen(k, open) {
  SECTION_OPEN[k] = !!open;
  try { localStorage.setItem('annotate:sections', JSON.stringify(SECTION_OPEN)); } catch {}
}
// A reviewer's own comment or reply that has not gone to the agent yet.
function userNeedsSend(c) {
  return c.status === 'open' && classify(c) === 'waiting' && needsPush(c);
}
// A1: text typed in an unanswered card's comment box, with no option
// picked, is that card's answer once Send is pressed.
function sayDraft(c) {
  return (DRAFTS['say:' + c.id] || '').trim();
}
// Clear a card's comment draft everywhere it is shown (rail, summary, body
// strip), so a re-render cannot read the old text back out of a box.
function clearSayDraft(id) {
  setDraft('say:' + id, '');
  document.querySelectorAll('[data-decision-say-ta="' + cssEsc(id) + '"]').forEach(ta => { ta.value = ''; });
  syncStripSayDraft(id);
}
function hasSayDraft(c) {
  return isUnresolvedDecision(c) && !!sayDraft(c);
}
function sectionOf(c) {
  if (c.status === 'archived') return 'archived';
  if (isRoundPending(c) || userNeedsSend(c)) return 'ready';
  const cls = classify(c);
  return cls === 'review' ? 'needs' : cls === 'waiting' ? 'waiting' : 'done';
}
// Everything one Send would send (A2). Spans every version, like a round.
// Exactly what one Send sends, in the same order Send sends it (High 1 /
// Medium 1 of the check): pending verdicts and typed answers go as the round;
// every other open item with unsent activity is pushed — the same rule 2.20's
// "Push to session" counted, so open cards are never stranded; general
// feedback becomes one more pushed item.
function sendPlan() {
  const round = [], answers = [], push = [];
  for (const c of flattenAll(false)) {
    if (isRoundPending(c)) round.push(c);
    else if (hasSayDraft(c)) answers.push(c);
    else if (needsPush(c)) push.push(c);
  }
  return { round, answers, push };
}
function sendables() {
  const p = sendPlan();
  const gf = !!gfDraft();
  return { verdicts: p.round.length, answers: p.answers.length, comments: p.push.length, gf,
    total: p.round.length + p.answers.length + p.push.length + (gf ? 1 : 0) };
}
function gfDraft() {
  return CURRENT_VERSION ? (DRAFTS['gf:' + CURRENT_VERSION] || '').trim() : '';
}

// final/: one count model for the whole page. docCounts() is what the
// header tabs, the phone menu and the rail badges read for a document.
function docCounts() {
  const all = flattenAll(false).filter(inScope);
  let needs = 0, unread = 0, waiting = 0;
  for (const c of all) {
    const s = sectionOf(c);
    if (s === 'needs') needs++;
    if (s === 'waiting') waiting++;
    if (readStateOf(c) !== 'read') unread++;
  }
  return { needs, unread, waiting, total: all.length, pending: sendables().total };
}
function renderCounts() {
  if (DOC !== VIEW_DOC) return;
  const k = docCounts();
  // B1: the tab badge counts only the cards that still need you.
  const tb = document.getElementById('tab-feedback-n');
  if (tb) { tb.textContent = String(k.needs); tb.hidden = k.needs === 0; }
  updateStripBadge();
  updateMobileFab(k.total, k.unread);
  if (window.AA) window.AA.changed();
}

// Phone button: 2.20's title; no count badge (B1: one progress count —
// the bottom bar and the Feedback tab already carry the numbers).
function updateMobileFab(total, unread) {
  const fab = document.getElementById('mobile-fab');
  if (!fab) return;
  const badge = document.getElementById('mobile-fab-badge');
  const countEl = document.getElementById('mobile-fab-count');
  if (countEl) countEl.textContent = String(total);
  if (badge) badge.style.display = 'none';
  fab.title = total + (total === 1 ? ' comment' : ' comments') + (unread > 0 ? ', ' + unread + ' unread' : '') + ' — open feedback';
}

function renderDrawer() {
  if (DOC !== VIEW_DOC) return;
  renderCounts();
  const listEl = document.getElementById('comment-list');
  const empty = document.getElementById('drawer-empty');
  const drawerBodyEl = document.getElementById('drawer-body');
  const savedScrollTop = drawerBodyEl ? drawerBodyEl.scrollTop : 0;

  // Keep half-typed text across re-renders (T11).
  let focusedTa = null;
  const unifiedCaret = document.activeElement && document.activeElement.selectionStart != null ? [document.activeElement.selectionStart, document.activeElement.selectionEnd, document.activeElement.selectionDirection] : null;
  listEl.querySelectorAll('.reply-ta').forEach(ta => {
    setDraft(ta.dataset.replyFor, ta.value || '');
    if (ta === document.activeElement) focusedTa = '[data-reply-for="' + cssEsc(ta.dataset.replyFor) + '"]';
  });
  listEl.querySelectorAll('.decision-say-ta').forEach(ta => {
    setDraft('say:' + ta.dataset.decisionSayTa, ta.value || '');
    if (ta === document.activeElement) focusedTa = '[data-decision-say-ta="' + cssEsc(ta.dataset.decisionSayTa) + '"]';
  });

  const groups = { needs: [], ready: [], waiting: [], done: [], archived: [] };
  for (const c of flattenAll(false).filter(inScope)) groups[sectionOf(c)].push(c);
  for (const [aid, items] of Object.entries(STORE.archived || {})) {
    for (const c of items) {
      const item = Object.assign({}, c, { anchor_id: aid });
      if (docOf(item) === DOC && inScope(item)) groups.archived.push(item);
    }
  }
  const byNum = (a, b) => (NUM_MAP[a.id] || 0) - (NUM_MAP[b.id] || 0);
  SECTION_ORDER.forEach(k => groups[k].sort(byNum));

  const anything = SECTION_ORDER.some(k => groups[k].length);
  if (!anything) {
    empty.style.display = 'flex';
    listEl.style.display = 'none';
    listEl.innerHTML = '';
    return;
  }
  empty.style.display = 'none';
  listEl.style.display = 'block';

  listEl.innerHTML = SECTION_ORDER.filter(k => groups[k].length).map(k => {
    const open = sectionOpen(k);
    const bodyId = 'sec-body-' + k;
    const badgeCls = k === 'needs' ? 'badge-error' : k === 'ready' ? 'badge-primary' : 'badge-ghost';
    return `<section class="sec sec-${k}" data-section="${k}">
      <button type="button" class="sec-hdr" data-section-toggle="${k}" aria-expanded="${open ? 'true' : 'false'}" aria-controls="${bodyId}">${ico('chevDown')}<span>${SECTION_LABEL[k]}</span><span class="badge badge-sm ${badgeCls}">${groups[k].length}</span></button>
      <div class="sec-body" id="${bodyId}"${open ? '' : ' hidden'}>${open ? groups[k].map(renderCItem).join('') : ''}</div>
    </section>`;
  }).join('');

  listEl.querySelectorAll('.reply-ta').forEach(ta => {
    const draft = DRAFTS[ta.dataset.replyFor];
    if (draft) ta.value = draft;
  });
  listEl.querySelectorAll('.decision-say-ta').forEach(ta => {
    const draft = DRAFTS['say:' + ta.dataset.decisionSayTa];
    if (draft) ta.value = draft;
    syncSayHint(ta);
  });
  if (focusedTa) {
    const ta = listEl.querySelector(focusedTa);
    if (ta) {
      ta.focus();
      if (unifiedCaret) ta.setSelectionRange(...unifiedCaret); else ta.selectionStart = ta.selectionEnd = ta.value.length;
    }
  }

  listEl.querySelectorAll('[data-section-toggle]').forEach(btn => btn.addEventListener('click', () => {
    setSectionOpen(btn.dataset.sectionToggle, !sectionOpen(btn.dataset.sectionToggle));
    renderDrawer();
  }));
  Array.from(listEl.querySelectorAll('[data-action="goto"]')).forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      markRead([findCommentById(btn.dataset.id)].filter(Boolean));
      goToCommentLocation(btn.dataset.anchor, btn.dataset.version, btn.dataset.id);
    });
  });
  wireCardActions(listEl);
  wireDecisionActions(listEl);
  syncExcerptClamps(listEl);
  if (drawerBodyEl && !focusedTa) drawerBodyEl.scrollTop = savedScrollTop;
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

// `opts.quiet` (D3 item 3): navigate WITHOUT re-rendering the drawer. Used
// when the trigger is focus landing in one of the card's textareas — a
// re-render would rebuild that textarea underneath the caret.
function goToCommentLocation(anchorId, version, commentId, opts) {
  // Drawer -> content is a "take me there" action; on mobile the sheet
  // covers the content entirely, so leaving it open would scroll/highlight
  // the anchor invisibly behind it. Dismiss so the result is immediately
  // visible (mirrors why goToCommentLocation exists at all — R1, "go-to
  // never a silent no-op").
  if (isMobileLayout()) setMobileSheetOpen(false);
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
  if (opts && opts.quiet) markActiveCardInPlace(commentId);
  else renderDrawer();
}

// Move the `hl` ring to one card without rebuilding the list (see the `quiet`
// path above).
function markActiveCardInPlace(commentId) {
  document.querySelectorAll('#comment-list .citem').forEach(el => {
    el.classList.toggle('hl', el.dataset.commentId === commentId);
  });
}

function markGotoUnavailable(commentId) {
  gotoUnavailable[commentId] = true;
  const ae = document.activeElement;
  if (ae && ae.closest && ae.closest('#comment-list textarea, #comment-list input')) return;
  renderDrawer();
}

// `general:<version>` anchor ids (minted by wireGeneralFeedback()) are not
// tied to any content-doc node -- there is nothing in the iframe to scroll
// to. Every other anchor id is a real content location.
function isGeneralAnchor(anchorId) {
  return typeof anchorId === 'string' && anchorId.indexOf('general:') === 0;
}

const DECISION_VERDICT_LABEL = { accept: 'Accepted', reject: 'Rejected', changes: 'Changes requested', comment: 'Answered in words', select: 'Selected' };
// Prior-verdict text for the rail's "Changing verdict — currently X" note,
// checkmark-prefixed to match the reply text sync_server.py generates on a
// revision (_DECISION_PRIOR_LABEL) so the card and the bus event read the
// same way.
const DECISION_VERDICT_TEXT = { accept: '✓ Accepted', reject: '✗ Rejected', changes: '↻ Changes requested', comment: 'Answered in words', select: '☑ Selected' };
// Every option id this chrome knows how to render. "comment" and "changes"
// are the same slot: which one a page shows is decided by the server's
// advertised verdicts, never by both appearing at once.
const DECISION_OPTIONS_ALL = ['accept', 'reject', 'comment', 'changes'];
// D2: the third verdict is "Request changes" (note required) on any server
// that advertises it; a server that does not still gets the pre-D2 "Comment".
const DECISION_OPTIONS_DEFAULT = ['accept', 'reject', 'comment'];
const DECISION_OPTIONS_DEFAULT_CHANGES = ['accept', 'reject', 'changes'];
// Default button labels/classes. accept/reject/comment are byte-identical to
// the pre-2.19 markup so a legacy decision_request (string options, nothing
// else) against a legacy server renders exactly as it always has.
const DECISION_BTN_LABEL = { accept: '&#10003; Accept', reject: '&#10007; Reject', comment: '&#128172; Answer in words', changes: '&#8635; Request changes' };
const DECISION_BTN_CLASS = { accept: 'decision-accept', reject: 'decision-reject', comment: 'decision-comment', changes: 'decision-changes' };
// The same options without their glyphs, for the "Recommended: …" sentence.
const DECISION_PLAIN_LABEL = { accept: 'Accept', reject: 'Reject', comment: 'Answer in words', changes: 'Request changes' };
const DECISION_IMPACTS = ['low', 'medium', 'high'];

// T-verdict-reversal (user-reported: clicked Reject by mistake on decision
// D8, no way to reverse it): comment ids currently showing the change-verdict
// form instead of their resolved chip. A module-level map (not render-local
// state) so the 8s poll's re-render doesn't silently snap the card back to
// the chip mid-correction; cleared on submit or explicit Cancel.
const decisionChanging = {};
// Request-changes hint per card (placeholder + message), until it is answered.
const decisionHint = {};
// v2.19 per-card UI state that must survive the 8s re-render: whether the
// optional "Add a note" form is open. Note TEXT lives in DRAFTS under
// 'note:<id>' (same store as replies).
const decisionNoteOpen = {};
// Card layout state, kept across re-renders the same way: the "Evidence (n)"
// list per card, each evidence preview, and each excerpt expanded past its
// four-line clamp.
const decisionEvidenceOpen = {};
const decisionEvidenceItemOpen = {};
const decisionExcerptOpen = {};
// Text of the anchors the open cards refer to, read by adapter.js from the
// document on screen ('annotate:excerpts'); the shell never reads the iframe.
// {anchorId: {text, name, card} | {missing: true}} for EXCERPTS_VERSION.
let EXCERPTS = {};
let EXCERPTS_VERSION = null;
// Whether the standing "Answer in words" form is open. Its text lives in DRAFTS
// under 'say:<id>', the same store as replies and verdict notes.
const decisionSayOpen = {};
// …and the same for the "Request changes" (pre-D2: "Comment") form, whose
// open state used to live in the DOM alone — so a re-render triggered while
// the reviewer was typing closed it and lost the box.
const decisionChangesOpen = {};

// v2.19 schema: dr.options may be the legacy string list or
// [{id, label, consequence, style}]; dr.consequences {accept, reject} is the
// shortcut for string options. Returns a uniform list. A string option that is
// not accept/reject/comment/changes is dropped (as before); an OBJECT option
// with an unknown id is kept as a "custom" choice, which the chrome posts as
// a `comment` verdict whose text names the selected option — unchanged by D2,
// so a card with custom ids behaves exactly as it did.
function decisionOptions(dr) {
  const fallback = changesEnabled() ? DECISION_OPTIONS_DEFAULT_CHANGES : DECISION_OPTIONS_DEFAULT;
  const raw = (Array.isArray(dr.options) && dr.options.length) ? dr.options : fallback;
  const cons = (dr.consequences && typeof dr.consequences === 'object') ? dr.consequences : {};
  const out = [];
  for (const o of raw) {
    if (typeof o === 'string') {
      if (DECISION_OPTIONS_ALL.indexOf(o) === -1) {
        out.push({id:o, labelHtml:esc(o), labelText:o, plainLabel:o, consequence:cons[o] || '', style:null, custom:true});
        continue;
      }
      const id = canonicalOptionId(o);
      const cq = typeof cons[o] === 'string' ? cons[o] : (typeof cons[id] === 'string' ? cons[id] : '');
      out.push({ id, labelHtml: DECISION_BTN_LABEL[id], labelText: id, plainLabel: DECISION_PLAIN_LABEL[id], consequence: cq, style: null, custom: false });
    } else if (o && typeof o === 'object' && typeof o.id === 'string' && o.id) {
      const id = canonicalOptionId(o.id);
      const known = DECISION_OPTIONS_ALL.indexOf(id) !== -1;
      const label = typeof o.label === 'string' && o.label.trim() ? o.label.trim() : null;
      out.push({
        id: known ? id : o.id,
        labelHtml: label ? esc(label) : (known ? DECISION_BTN_LABEL[id] : esc(o.id)),
        labelText: label || o.id,
        plainLabel: label || (known ? DECISION_PLAIN_LABEL[id] : o.id),
        consequence: typeof o.consequence === 'string' ? o.consequence : (typeof cons[o.id] === 'string' ? cons[o.id] : ''),
        style: (o.style === 'primary' || o.style === 'danger' || o.style === 'default') ? o.style : null,
        custom: !known,
      });
    }
  }
  return out;
}

// Context is what the reviewer needs in order to decide, so it is always
// shown in full (NN/g: never hide what the decision depends on).
function renderDecisionContext(dr) {
  const ctx = typeof dr.context === 'string' ? dr.context.trim() : '';
  return ctx ? `<div class="decision-context">${ticketsHTML(ctx)}</div>` : '';
}
// "Recommended: <option>" — the MADR "chosen option" line, stated once.
function renderDecisionReco(opts, dr) {
  const rec = typeof dr.recommendation === 'string' ? dr.recommendation : null;
  if (!rec) return '';
  const id = canonicalOptionId(rec);
  const o = opts.find(x => x.id === id);
  const label = o ? o.plainLabel : (DECISION_PLAIN_LABEL[id] || rec);
  return `<div class="decision-reco-line">Recommended: <b>${esc(label)}</b></div>`;
}

function idFor(key) {
  let h = 5381;
  const s = String(key);
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  return 'dx-' + h.toString(36);
}
function evidenceList(dr) {
  return Array.isArray(dr.evidence)
    ? dr.evidence.filter(e => e && typeof e === 'object' && typeof e.anchor === 'string' && e.anchor)
    : [];
}
// Excerpts describe the document on screen; a card that belongs to another
// version gets none rather than text from the wrong page.
function excerptsFor(c) {
  return (EXCERPTS_VERSION === CURRENT_VERSION && gotoVersionFor(c) === CURRENT_VERSION) ? EXCERPTS : null;
}
// A quoted excerpt clamped to four lines; "Show more" appears only when the
// text is cut off (see syncExcerptClamps).
function renderExcerptBox(key, text, source, footExtra) {
  const open = !!decisionExcerptOpen[key];
  const qid = idFor('q|' + key);
  return `<figure class="decision-excerpt${open ? ' is-open' : ''}">
      ${source ? `<figcaption class="decision-excerpt-src">${esc(source)}</figcaption>` : ''}
      <blockquote class="decision-excerpt-text" id="${qid}">${esc(text)}</blockquote>
      <div class="decision-excerpt-ft">
        <button type="button" class="decision-excerpt-more" data-decision-action="excerpt-more" data-key="${escAttr(key)}" aria-controls="${qid}" aria-expanded="${open ? 'true' : 'false'}" hidden>${open ? 'Show less' : 'Show more'}</button>
        ${footExtra || ''}
      </div>
    </figure>`;
}
// The element the card is about, quoted inside the card: the first evidence
// anchor, else the card's own anchor when that is not the card itself.
// C2: the quote carries "Open in document" (the card's own location).
function renderDecisionExcerpt(c, dr) {
  const x = excerptsFor(c);
  if (!x) return '';
  const link = isGeneralAnchor(c.anchor_id) || gotoUnavailable[c.id] ? '' : openDocBtn(c, ' data-excerpt-goto="1"');
  const ev = evidenceList(dr);
  const first = ev.length ? x[ev[0].anchor] : null;
  if (first && first.text) return renderExcerptBox(c.id + '|first', first.text, first.name, link);
  const own = x[c.anchor_id];
  if (own && own.text && !own.card) return renderExcerptBox(c.id + '|own', own.text, own.name, link);
  return '';
}
function renderDecisionMeta(dr) {
  let h = '';
  if (typeof dr.impact === 'string' && DECISION_IMPACTS.indexOf(dr.impact) !== -1) {
    h += `<span class="decision-chip decision-chip-impact-${dr.impact}" title="Impact if decided wrongly">Impact: ${dr.impact}</span>`;
  }
  if (dr.blocking === true) {
    h += '<span class="decision-chip decision-chip-blocking" title="The agent cannot proceed until this is decided">Blocking</span>';
  }
  return h ? `<div class="decision-meta">${h}</div>` : '';
}
// "Evidence (n)", collapsed. Each item opens a preview of its target inside
// the card (Wikipedia's reference previews); "Go to" scrolls the document
// there and leaves a "Back to #N" marker that returns to this card.
function renderDecisionEvidence(c, dr) {
  const ev = evidenceList(dr);
  if (!ev.length) return '';
  const x = excerptsFor(c);
  const open = !!decisionEvidenceOpen[c.id];
  const listId = idFor('evl|' + c.id);
  const items = ev.map((e, i) => {
    const key = c.id + '|' + e.anchor + '|' + i;
    const itemOpen = !!decisionEvidenceItemOpen[key];
    const pid = idFor('evp|' + key);
    const hit = x ? x[e.anchor] : null;
    const preview = hit && hit.text
      ? renderExcerptBox('ev|' + key, hit.text, hit.name)
      : `<div class="decision-evidence-missing">${hit && hit.missing ? 'Not on this version of the page.' : 'No preview for this version.'}</div>`;
    return `<li class="decision-evidence-item">
        <button type="button" class="decision-evidence-link" data-decision-action="evidence-preview" data-key="${escAttr(key)}" aria-expanded="${itemOpen ? 'true' : 'false'}" aria-controls="${pid}" title="Preview ${escAttr(e.anchor)}"><span class="decision-evidence-label">${esc(e.label || e.anchor)}</span></button>
        <div class="decision-evidence-preview" id="${pid}"${itemOpen ? '' : ' hidden'}>
          ${preview}
          <button type="button" class="decision-evidence-goto" data-decision-action="evidence" data-anchor="${escAttr(e.anchor)}" data-id="${escAttr(c.id)}" title="Scroll the document to ${escAttr(e.anchor)}; a Back marker there returns here">Go to &rarr;</button>
        </div>
      </li>`;
  }).join('');
  return `<div class="decision-evidence">
      <button type="button" class="decision-evidence-toggle" data-decision-action="evidence-toggle" data-id="${escAttr(c.id)}" aria-expanded="${open ? 'true' : 'false'}" aria-controls="${listId}">Evidence (${ev.length})</button>
      <ul class="decision-evidence-list" id="${listId}"${open ? '' : ' hidden'}>${items}</ul>
    </div>`;
}
// Show "Show more" only under an excerpt the clamp actually cuts off. An
// unrendered one (collapsed rail, closed preview) is judged by its length.
function syncExcerptClamps(root) {
  if (!root) return;
  root.querySelectorAll('.decision-excerpt').forEach(box => {
    const t = box.querySelector('.decision-excerpt-text');
    const more = box.querySelector('.decision-excerpt-more');
    if (!t || !more) return;
    if (box.classList.contains('is-open')) { more.hidden = false; return; }
    const text = t.textContent || '';
    more.hidden = !(t.clientHeight > 0
      ? t.scrollHeight > t.clientHeight + 1
      : (text.length > 220 || (text.match(/\n/g) || []).length >= 4));
  });
}
// A2: no per-card "Pending — not sent" chip or "Send now"; a pending verdict
// sits in the "Ready to send" section until the one Send.
function verdictBadgeClass(v) {
  return v === 'accept' ? 'badge-success' : v === 'reject' ? 'badge-error' : v === 'changes' ? 'badge-warning' : 'badge-info';
}
function firstLine(s) {
  return String(s || '').split('\n').map(x => x.trim()).filter(Boolean)[0] || '';
}
// C1: the answer as one short phrase, for the one-line card and the summary.
function answerLabel(c) {
  const d = decisionAnswer(c);
  if (!d) {
    if (c.status === 'resolved_in_version') return { text: 'Resolved in ' + (c.resolved_in_version || 'later version'), muted: true };
    if (c.status === 'addressed_by_agent') return { text: 'Addressed by agent — no answer needed', muted: true };
    return { text: 'Not answered', muted: true };
  }
  // U-06-r2: show the saved answer itself, without a verdict prefix or quotes.
  // The same text feeds the rail cards, Send summary and document strips.
  if (d.text) return { text: d.verdict === 'select' ? d.text.replace(/^Selected:\s*/, '') : d.text };
  return { text: DECISION_VERDICT_LABEL[d.verdict] || d.verdict };
}
function canChangeAnswer(c) {
  return !!(decisionAnswer(c) && c.decision_request && c.status !== 'archived' && c.status !== 'resolved_in_version');
}
function changeBtnHtml(c) {
  return `<button type="button" class="btn btn-ghost btn-xs btn-square change-btn" data-decision-action="change" data-id="${escAttr(c.id)}" aria-label="Change answer to #${NUM_MAP[c.id] || ''}" title="Change">${ico('pencil')}</button>`;
}
// Shortcut hints (E3) are drawn only on the active card, and never on phones.
function showKbd(c) {
  return c.id === highlightedCommentId && !isMobileLayout();
}

// One-click decision block (2.20 behaviour kept: one click on an option
// answers; nothing is preselected; Request changes needs text). A1: one
// optional comment box under the options replaces "Answer in words",
// "+ Add a note" and the Request-changes box.
function renderDecisionBlock(c) {
  if (!c.decision_request || c.status === 'archived') return '';
  const dr = c.decision_request;
  if (c.status === 'resolved_in_version') {
    return `<div class="decision-block decision-resolved">
      <div class="decision-prompt">${ticketsHTML(displayPrompt(c))}</div>
      <span class="badge badge-soft badge-ghost decision-verdict-chip">Resolved in ${esc(c.resolved_in_version || 'later version')}</span>
    </div>`;
  }
  if (c.status === 'addressed_by_agent' && !decisionAnswer(c)) {
    return `<div class="decision-block decision-resolved">
      <div class="decision-prompt">${ticketsHTML(displayPrompt(c))}</div>
      <span class="badge badge-soft badge-ghost decision-verdict-chip">Addressed by agent &mdash; no answer needed</span>
    </div>`;
  }
  const changing = !!decisionChanging[c.id];
  if (decisionAnswer(c) && !changing) {
    const a = answerLabel(c);
    return `<div class="decision-block decision-resolved">
      <div class="decision-prompt">${ticketsHTML(displayPrompt(c))}</div>
      <div class="decision-resolved-row">
        <div class="decision-answer-text">${esc(a.text)}</div>
        ${canChangeAnswer(c) ? changeBtnHtml(c) : ''}
      </div>
    </div>`;
  }
  const opts = decisionOptions(dr);
  const wantsChanges = opts.some(o => o.id === 'changes');
  const hasCons = opts.some(o => !!o.consequence);
  const rec = typeof dr.recommendation === 'string' ? dr.recommendation : null;
  const kbd = showKbd(c);
  let btns = '';
  opts.forEach((o, i) => {
    const isRec = !!rec && canonicalOptionId(rec) === o.id;
    const cls = o.custom
      ? ('decision-custom' + (o.style ? ' decision-style-' + o.style : ''))
      : DECISION_BTN_CLASS[o.id];
    const action = o.custom ? 'custom' : o.id;
    const extra = o.custom ? ` data-option-id="${escAttr(o.id)}" data-option-label="${escAttr(o.labelText)}"` : '';
    const badge = isRec ? '<span class="badge badge-success badge-soft badge-xs decision-rec-badge">Recommended</span>' : '';
    const cons = o.consequence ? `<span class="decision-consequence">${esc(o.consequence)}</span>` : '';
    const k = kbd && i < 9 ? `<kbd class="kbd kbd-xs">${i + 1}</kbd>` : '';
    btns += `<button class="btn decision-btn ${cls}${isRec ? ' is-recommended' : ''}" data-decision-action="${action}" data-id="${escAttr(c.id)}"${extra}${isRec ? ' title="Recommended by the agent"' : ''}><span class="decision-opt-head">${k}<span class="decision-opt-label">${o.labelHtml}</span>${badge}</span>${cons}</button>`;
  });
  const changingNote = (c.decision && changing) ? `<div class="decision-changing-note">
      <span>Changing verdict &mdash; currently ${esc(c.decision.verdict === 'select' ? '☑ ' + answerLabel(c).text : (DECISION_VERDICT_TEXT[c.decision.verdict] || c.decision.verdict))}</span>
      <button class="btn btn-ghost btn-xs" data-decision-action="cancel-change" data-id="${escAttr(c.id)}">Cancel</button>
    </div>` : '';
  const cmtHtml = `<div class="decision-cmt">
      <textarea class="textarea textarea-sm decision-say-ta" data-decision-say-ta="${escAttr(c.id)}" data-wants-changes="${wantsChanges ? '1' : ''}" placeholder="${escAttr(decisionHint[c.id] ? decisionHint[c.id].ph : 'Comment (optional)')}" rows="1" aria-label="Comment on #${NUM_MAP[c.id] || ''} (optional)"></textarea>
      ${kbd ? '<kbd class="kbd kbd-xs">C</kbd>' : ''}
      <div class="decision-cmt-hint" data-say-hint="${escAttr(c.id)}"></div>
    </div>`;
  return `<div class="decision-block">
    ${changingNote}
    <div class="decision-prompt">${ticketsHTML(displayPrompt(c))}</div>
    ${renderDecisionMeta(dr)}
    ${renderDecisionContext(dr)}
    ${renderDecisionReco(opts, dr)}
    ${renderDecisionExcerpt(c, dr)}
    <div class="decision-btns${hasCons ? ' has-consequences' : ''}">${btns}</div>
    ${renderDecisionEvidence(c, dr)}
    ${cmtHtml}
    <div class="decision-feedback" data-decision-feedback="${escAttr(c.id)}">${decisionHint[c.id] ? esc(decisionHint[c.id].msg) : ''}</div>
  </div>`;
}
// The hint under the comment box says what typed text will do.
function syncSayHint(ta) {
  const id = ta.dataset.decisionSayTa;
  const hint = document.querySelector('[data-say-hint="' + cssEsc(id) + '"]');
  if (!hint) return;
  hint.textContent = (ta.value || '').trim()
    ? 'Saved with your choice. With no choice picked, it counts as your answer when you send.'
    : '';
}

// C3: rare actions in one ⋯ menu (Resolve, Re-open, Archive, Re-pin, …).
function cardMenuItems(c, cls) {
  const id = escAttr(c.id);
  const items = [];
  if (c.status !== 'archived') {
    if (cls === 'review' || c.status === 'user_confirmed' || c.status === 'resolved_in_version') {
      items.push(`<li><button type="button" data-action="accept" data-id="${id}">Resolve</button></li>`);
      items.push(`<li><button type="button" data-action="reopen" data-id="${id}" data-anchor="${escAttr(c.anchor_id)}">Re-open</button></li>`);
    } else {
      items.push(`<li><button type="button" data-action="archive" data-id="${id}">Archive</button></li>`);
    }
    if (!isGeneralAnchor(c.anchor_id) && c.version === CURRENT_VERSION) {
      items.push(`<li><button type="button" data-action="repin" data-id="${id}" title="Click a new location in the document to move this comment's pin">&#128204; Re-pin</button></li>`);
    }
    if (c.status === 'resolved_in_version' && c.resolved_in_version && c.resolution_anchor_id) {
      items.push(`<li><button type="button" data-action="resolution" data-id="${id}">View resolution in ${esc(c.resolved_in_version)}</button></li>`);
    }
  } else {
    items.push(`<li><button type="button" data-action="restore" data-id="${id}">Restore</button></li>`);
  }
  return items.join('');
}
function cardMenuHtml(c, cls) {
  const num = NUM_MAP[c.id];
  const open = openMenuId === c.id;
  return `<button type="button" class="btn btn-ghost btn-xs btn-square citem-menu-btn" data-action="menu" data-id="${escAttr(c.id)}" aria-haspopup="menu" aria-expanded="${open ? 'true' : 'false'}" aria-label="More actions${num ? ' for #' + num : ''}" title="More actions">${ico('more')}</button>`;
}
function cardMenuPanel(c, cls) {
  return `<ul class="menu menu-sm citem-menu" role="menu" data-menu-for="${escAttr(c.id)}"${openMenuId === c.id ? '' : ' hidden'}>${cardMenuItems(c, cls)}</ul>`;
}
function unreadDotHtml(c) {
  const rstate = readStateOf(c);
  if (rstate === 'new-activity') return '<span class="unread-dot new-reply" title="The agent responded since you last read this" role="img" aria-label="↑ NEW reply"></span>';
  if (rstate === 'unread') return '<span class="unread-dot" title="You have not opened this comment yet" role="img" aria-label="Unread"></span>';
  return '';
}
// A1: a reply box only once the agent has said something on this item.
function agentResponded(c) {
  if (c.response_text) return true;
  if ((c.replies || []).some(r => isAgentAuthor(r.author))) return true;
  return !c.decision_request && isAgentAuthor(c.author);
}
function isLineCard(c) {
  if (cardExpanded[c.id] || decisionChanging[c.id]) return false;
  if (!c.decision_request || c.status === 'archived') return false;
  return !!decisionAnswer(c) || c.status === 'resolved_in_version' || c.status === 'addressed_by_agent';
}

function renderCItem(c) {
  const cls = classify(c);
  const num = NUM_MAP[c.id];
  const numHtml = num ? `<span class="citem-num">#${num}</span>` : '';
  const rstate = readStateOf(c);
  const unreadCls = rstate !== 'read' ? ' is-unread' : '';
  const hl = c.id === highlightedCommentId ? ' hl' : '';

  // C1: an answered card is one line: number, question → answer, Change.
  if (isLineCard(c)) {
    const a = answerLabel(c);
    return `<div class="citem is-line${hl}${unreadCls}" data-comment-id="${escAttr(c.id)}" title="Click to show this comment's location in the document">
      <div class="citem-line">
        ${unreadDotHtml(c)}${numHtml}
        <span class="citem-line-txt"><span class="citem-line-q">${ticketsHTML(displayPrompt(c))}</span><span class="citem-line-arrow" aria-hidden="true">&rarr;</span><span class="ans${a.muted ? ' is-muted' : ''}">${esc(a.text)}</span></span>
        ${canChangeAnswer(c) ? changeBtnHtml(c) : ''}
        ${cardMenuHtml(c, cls)}
      </div>
      ${cardMenuPanel(c, cls)}
    </div>`;
  }

  const decisionCls = isUnresolvedDecision(c) ? ' decision-required' : '';
  // B3: the latest reply inline; older ones behind "n earlier replies".
  // The saved answer is already rendered below. Omit only the server's
  // duplicate reply for that exact decision; keep user replies and history.
  const d = !decisionChanging[c.id] && decisionAnswer(c);
  const generatedAnswer = d && ((d.verdict === 'comment' ? '💬 Answer in words: '
    : d.verdict === 'changes' ? '↻ Changes requested: '
    : d.verdict === 'select' ? '☑ Selected: ' : '') +
    (['comment', 'changes', 'select'].includes(d.verdict) ? (d.text || '')
      : (DECISION_VERDICT_TEXT[d.verdict] || d.verdict) + (d.text ? '\n\n' + d.text : '')));
  const replies = (c.replies || []).filter(r => !(d && r.ts === d.ts && r.author === d.by &&
    (r.text === generatedAnswer || r.text.startsWith(generatedAnswer + '\n\n(revised verdict'))));
  const renderReply = r => `
    <div class="thread-reply">
      <div class="thread-reply-hdr">${esc(authorLabel(r))} &middot; ${esc(fmtTs(r.ts))}</div>
      <div>${ticketsHTML(r.text)}</div>
    </div>`;
  let replyHtml = '';
  if (replies.length > 1) {
    const n = replies.length - 1;
    const open = !!earlierOpen[c.id];
    const lid = idFor('er|' + c.id);
    replyHtml += `<button type="button" class="earlier-toggle" data-action="earlier" data-id="${escAttr(c.id)}" aria-expanded="${open ? 'true' : 'false'}" aria-controls="${lid}">${ico('chevRight')}${n} earlier repl${n === 1 ? 'y' : 'ies'}</button>
      <div class="earlier-list" id="${lid}"${open ? '' : ' hidden'}>${replies.slice(0, -1).map(renderReply).join('')}</div>`;
  }
  if (replies.length) replyHtml += renderReply(replies[replies.length - 1]);
  const agentReplyHtml = c.response_text ? `
    <div class="agent-reply">
      <div class="agent-reply-hdr">Agent response</div>
      <div>${ticketsHTML(c.response_text)}</div>
    </div>` : '';

  const showReply = c.status !== 'archived' && agentResponded(c) && !isUnresolvedDecision(c) && !decisionChanging[c.id];
  const replyFormHtml = showReply ? `
    <div class="reply-form">
      <textarea class="textarea textarea-sm reply-ta" data-reply-for="${escAttr(c.id)}" placeholder="Add a reply&hellip;" rows="2"></textarea>
      <button class="btn btn-sm reply-submit" data-action="reply" data-id="${escAttr(c.id)}">Post reply</button>
    </div>` : '';

  // Location: always visible, never a silent no-op (2.20). C2: decision
  // cards carry "Open in document" on their quoted excerpt instead.
  const decisionHtml = renderDecisionBlock(c);
  const hasExcerptLink = decisionHtml.indexOf('data-excerpt-goto') !== -1;
  let locHtml = '';
  if (isGeneralAnchor(c.anchor_id)) {
    locHtml = `<div class="citem-loc unavailable">General feedback &mdash; not tied to a location</div>`;
  } else if (gotoUnavailable[c.id]) {
    locHtml = `<div class="citem-loc unavailable">Location unavailable in this version
        <button class="btn btn-ghost btn-xs err" data-action="goto" data-id="${escAttr(c.id)}" data-anchor="${escAttr(c.anchor_id)}" data-version="${escAttr(gotoVersionFor(c))}" title="Content may have been restructured since this comment was made">&#10007; Not found</button>
      </div>`;
  } else if (!hasExcerptLink) {
    locHtml = `<div class="citem-loc">${openDocBtn(c)}</div>`;
  }
  const collapseHtml = (c.decision_request && cardExpanded[c.id] && !decisionChanging[c.id] && (decisionAnswer(c) || c.status === 'resolved_in_version' || c.status === 'addressed_by_agent'))
    ? `<button type="button" class="btn btn-ghost btn-xs btn-square collapse-btn" data-action="collapse" data-id="${escAttr(c.id)}" aria-label="Collapse to one line" title="Collapse">${ico('chevUp')}</button>`
    : '';
  // U-03: the phrase the reviewer selected when commenting.
  const quote = c.target && c.target.selected_quote;
  const quoteHtml = quote ? `<blockquote class="unified-selected-quote">“${esc(quote)}”</blockquote>` : '';
  // U-10: an open card from a newer version than the one on screen.
  const newerHtml = isNewerThanViewed(c) && followsViewer(c)
    ? `<div class="citem-loc unified-newer-location">Not in ${esc(CURRENT_VERSION)} — <button type="button" class="btn btn-link btn-xs" data-action="goto" data-id="${escAttr(c.id)}" data-anchor="${escAttr(c.anchor_id)}" data-version="${escAttr(c.version)}">open ${esc(c.version)}</button></div>`
    : '';
  const navKeys = showKbd(c) ? '<span class="citem-kbd"><kbd class="kbd kbd-xs" title="Previous card">A</kbd><kbd class="kbd kbd-xs" title="Next card">F</kbd></span>' : '';

  return `<div class="citem${hl}${unreadCls}${decisionCls}" data-comment-id="${escAttr(c.id)}" title="Click to show this comment's location in the document">
    <div class="citem-node">
      ${unreadDotHtml(c)}
      <span class="citem-node-name">${numHtml}${esc(anchorLabel(c))}</span>
      ${navKeys}${collapseHtml}${cardMenuHtml(c, cls)}
    </div>
    ${cardMenuPanel(c, cls)}
    ${locHtml}
    ${sameText(c.text, c.decision_request && (c.decision_request.prompt || '')) ? '' : `<div class="citem-txt">${ticketsHTML(c.text)}</div>`}
    ${agentReplyHtml}
    ${replyHtml}
    ${quoteHtml}${newerHtml}
    <div class="citem-meta">
      <span class="citem-author">${esc(authorLabel(c))}</span>
      <span>${fmtTs(c.created_at)}${c.edited_at ? ' (edited)' : ''}</span>
    </div>
    ${decisionHtml}
    ${replyFormHtml}
  </div>`;
}
// The card's own text is left out when it only repeats the question (the
// body strip in adapter.js already does this).
function sameText(a, b) {
  const n = s => String(s || '').replace(/^\s*(?:Q|#)\s*\d+[\s:.\-—–]*/i, '').replace(/\s+/g, ' ').trim().toLowerCase();
  return !!b && n(a) === n(b);
}
function openDocBtn(c, extraAttr) {
  return `<button type="button" class="open-doc" data-action="goto" data-id="${escAttr(c.id)}" data-anchor="${escAttr(c.anchor_id)}" data-version="${escAttr(gotoVersionFor(c))}"${extraAttr || ''}>${ico('locate')}Open in document</button>`;
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
  // U-14: each card is a named, focusable group; Enter opens it.
  // U-04: hovering a card outlines what it is about in the document.
  root.querySelectorAll('.citem').forEach(card => {
    const c = findCommentById(card.dataset.commentId);
    if (!c) return;
    card.tabIndex = 0;
    card.setAttribute('role', 'group');
    card.setAttribute('aria-label', 'Feedback #' + (NUM_MAP[c.id] || '') + ' · ' + displayPrompt(c));
    card.addEventListener('keydown', e => {
      if (e.key !== 'Enter' || e.target !== card) return;
      e.preventDefault();
      card.click();
      const next = root.querySelector('[data-comment-id="' + cssEsc(c.id) + '"]');
      if (next) next.focus();
    });
    const hover = on => {
      if (gotoVersionFor(c) !== CURRENT_VERSION || isGeneralAnchor(c.anchor_id)) return;
      postToFrame({ type: 'annotate:card-hover', anchorId: c.anchor_id, target: c.target || null, on });
    };
    card.addEventListener('mouseenter', () => hover(true));
    card.addEventListener('mouseleave', () => hover(false));
  });
  // Whole-card click navigates (T1). On a one-line answered card (C1) it
  // also expands the card.
  root.querySelectorAll('.citem').forEach(card => card.addEventListener('click', (e) => {
    if (e.target.closest('button, textarea, a, input, select, .citem-menu')) return;
    const c = findCommentById(card.dataset.commentId);
    if (!c) return;
    markRead([c]);
    highlightedCommentId = c.id;
    if (card.classList.contains('is-line')) cardExpanded[c.id] = true;
    if (isGeneralAnchor(c.anchor_id)) {
      renderDrawer();
      sendCommentCountsToFrame();
      return;
    }
    // Fix (not a sheet item): rebuild the body strips BEFORE asking the
    // document to scroll. 2.20.3 did it after, so the strip the scroll was
    // aimed at was replaced mid-flight and decision cards read "Not found".
    sendCommentCountsToFrame();
    goToCommentLocation(c.anchor_id, gotoVersionFor(c), c.id);
  }));
  // D3 item 3 (2.20): focus entering a card's box navigates too, quietly.
  root.querySelectorAll('.citem').forEach(card => card.addEventListener('focusin', (e) => {
    if (!e.target.closest('textarea, input')) return;
    const c = findCommentById(card.dataset.commentId);
    if (!c || isGeneralAnchor(c.anchor_id)) return;
    if (highlightedCommentId === c.id) return;
    markRead([c]);
    sendCommentCountsToFrame();
    // Keep the phone composer reachable; explicit Open in document still navigates.
    if (isMobileLayout()) {
      highlightedCommentId = c.id;
      markActiveCardInPlace(c.id);
    } else goToCommentLocation(c.anchor_id, gotoVersionFor(c), c.id, { quiet: true });
  }));
  // C3: the ⋯ menu
  root.querySelectorAll('[data-action="menu"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const id = btn.dataset.id;
    openMenuId = openMenuId === id ? null : id;
    root.querySelectorAll('.citem-menu').forEach(m => { m.hidden = m.dataset.menuFor !== openMenuId; });
    root.querySelectorAll('[data-action="menu"]').forEach(b => b.setAttribute('aria-expanded', b.dataset.id === openMenuId ? 'true' : 'false'));
    const first = openMenuId && root.querySelector('.citem-menu[data-menu-for="' + cssEsc(openMenuId) + '"] button');
    if (first) first.focus();
  }));
  const closeMenuThen = (fn) => async (e) => {
    e.stopPropagation();
    openMenuId = null;
    await fn(e.currentTarget);
  };
  root.querySelectorAll('[data-action="earlier"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const open = !earlierOpen[btn.dataset.id];
    earlierOpen[btn.dataset.id] = open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    const list = document.getElementById(btn.getAttribute('aria-controls'));
    if (list) list.hidden = !open;
  }));
  root.querySelectorAll('[data-action="collapse"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    delete cardExpanded[btn.dataset.id];
    renderDrawer();
  }));
  root.querySelectorAll('[data-action="accept"]').forEach(btn => btn.addEventListener('click', closeMenuThen(async (b) => {
    await apiAccept(b.dataset.id);
    await refreshStore();
  })));
  root.querySelectorAll('[data-action="archive"]').forEach(btn => btn.addEventListener('click', closeMenuThen(async (b) => {
    await apiArchive(b.dataset.id);
    await refreshStore();
  })));
  root.querySelectorAll('[data-action="restore"]').forEach(btn => btn.addEventListener('click', closeMenuThen(async (b) => {
    await apiRestore(b.dataset.id);
    await refreshStore();
    markReadAfterAction(b.dataset.id);
  })));
  root.querySelectorAll('[data-action="reopen"]').forEach(btn => btn.addEventListener('click', closeMenuThen(async (b) => {
    await apiPutComment(b.dataset.id, { status: 'open' });
    await refreshStore();
    markReadAfterAction(b.dataset.id);
  })));
  root.querySelectorAll('[data-action="resolution"]').forEach(btn => btn.addEventListener('click', closeMenuThen(async (b) => {
    const c = findCommentById(b.dataset.id);
    if (!c || !c.resolved_in_version || !c.resolution_anchor_id) return;
    goToCommentLocation(c.resolution_anchor_id, c.resolved_in_version, null);
  })));
  root.querySelectorAll('[data-action="repin"]').forEach(btn => btn.addEventListener('click', closeMenuThen(async (b) => {
    renderDrawer();
    startRepin(b.dataset.id);
  })));
  root.querySelectorAll('[data-action="reply"]').forEach(btn => btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    const ta = root.querySelector('[data-reply-for="' + cssEsc(btn.dataset.id) + '"]');
    const text = (ta && ta.value || '').trim();
    if (!text) { if (ta) ta.focus(); return; }
    const posted = await apiReply(btn.dataset.id, text);
    if (posted) {
      if (ta) ta.value = '';
      setDraft(btn.dataset.id, '');
    }
    await refreshStore();
    markReadAfterAction(btn.dataset.id);
  }));
}

// ── One-click decision buttons ───────────────────────────────────────
function setDecisionFeedback(root, id, msg, isError) {
  const el = root.querySelector('[data-decision-feedback="' + cssEsc(id) + '"]');
  if (!el) return;
  el.textContent = msg;
  el.classList.toggle('is-error', !!isError);
}
function setDecisionButtonsDisabled(root, id, disabled) {
  root.querySelectorAll('.decision-btn[data-id="' + cssEsc(id) + '"]').forEach(b => { b.disabled = disabled; });
}

// A1: the one comment box under the options. Its text goes with whichever
// option is clicked (2.20's optional note); null when empty.
function decisionCommentText(root, id) {
  const ta = root.querySelector('[data-decision-say-ta="' + cssEsc(id) + '"]');
  const t = ((ta ? ta.value : DRAFTS['say:' + id]) || '').trim();
  return t || null;
}

async function submitDecision(root, id, verdict, text) {
  setDecisionButtonsDisabled(root, id, true);
  setDecisionFeedback(root, id, 'Sending…', false);
  let result = await apiDecision(id, verdict, text);
  if (!result || result.fallback) result = await apiDecisionFallback(id, verdict, text);
  if (!result) {
    setDecisionFeedback(root, id, 'Failed to send — try again.', true);
    setDecisionButtonsDisabled(root, id, false);
    return null;
  }
  delete decisionChanging[id];
  delete cardExpanded[id];
  delete decisionHint[id];
  clearSayDraft(id);
  await refreshStore();
  markReadAfterAction(id);
  updateSendState();
  return result;
}

// Evidence "Go to" (2.20, unchanged).
function goToEvidence(anchorId, commentId) {
  if (!anchorId) return;
  if (isMobileLayout()) setMobileSheetOpen(false);
  const back = commentId ? { commentId, n: NUM_MAP[commentId] || 0, from: 'rail' } : null;
  scrollToAnchorInFrame(anchorId, null, back);
}

// Click on an option, from the card or from the send summary. Request
// changes still needs words (2.20); with an empty box it asks for them.
function pickOption(root, btn) {
  const id = btn.dataset.id;
  const action = btn.dataset.decisionAction;
  const note = decisionCommentText(root, id);
  if (action === 'accept' || action === 'reject') return submitDecision(root, id, action, note);
  if (action === 'comment' || action === 'changes') {
    if (!note) {
      // Kept in state (not only in the DOM) so a re-render that lands right
      // after — e.g. the excerpts refresh that follows an earlier verdict —
      // draws the same hint again instead of wiping it.
      decisionHint[id] = action === 'changes'
        ? { ph: 'What needs to change…', msg: 'Say what needs to change in the box, then pick it again.' }
        : { ph: 'Add your comment…', msg: 'Write your answer in the box, then pick it again.' };
      const ta = root.querySelector('[data-decision-say-ta="' + cssEsc(id) + '"]');
      if (ta) {
        ta.placeholder = decisionHint[id].ph;
        ta.focus();
      }
      setDecisionFeedback(root, id, decisionHint[id].msg, false);
      return null;
    }
    return submitDecision(root, id, action, note);
  }
  // custom option → `select` naming the choice (or pre-D3 `comment`)
  const label = btn.dataset.optionLabel || btn.dataset.optionId || 'option';
  const v = selectVerdictId();
  const text = (v === 'select' ? label : 'Selected: ' + label) + (note ? '\n\n' + note : '');
  return submitDecision(root, id, v, text);
}

function wireDecisionActions(root) {
  root.querySelectorAll('.decision-btn[data-decision-action]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    pickOption(root, btn);
  }));
  const toggleRegion = (btn, open) => {
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    const region = document.getElementById(btn.getAttribute('aria-controls'));
    if (region) region.hidden = !open;
    return region;
  };
  root.querySelectorAll('[data-decision-action="evidence-toggle"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const open = !decisionEvidenceOpen[btn.dataset.id];
    decisionEvidenceOpen[btn.dataset.id] = open;
    const region = toggleRegion(btn, open);
    if (open) syncExcerptClamps(region);
  }));
  root.querySelectorAll('[data-decision-action="evidence-preview"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const open = !decisionEvidenceItemOpen[btn.dataset.key];
    decisionEvidenceItemOpen[btn.dataset.key] = open;
    const region = toggleRegion(btn, open);
    if (open) syncExcerptClamps(region);
  }));
  root.querySelectorAll('[data-decision-action="excerpt-more"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const open = !decisionExcerptOpen[btn.dataset.key];
    decisionExcerptOpen[btn.dataset.key] = open;
    const box = btn.closest('.decision-excerpt');
    if (box) box.classList.toggle('is-open', open);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    btn.textContent = open ? 'Show less' : 'Show more';
    if (box && box.parentElement) syncExcerptClamps(box.parentElement);
  }));
  root.querySelectorAll('[data-decision-action="evidence"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    goToEvidence(btn.dataset.anchor, btn.dataset.id);
  }));
  root.querySelectorAll('.decision-say-ta').forEach(ta => ta.addEventListener('input', () => {
    setDraft('say:' + ta.dataset.decisionSayTa, ta.value || '');
    syncSayHint(ta);
    syncStripSayDraft(ta.dataset.decisionSayTa);
    updateSendState();
  }));
  root.querySelectorAll('[data-decision-action="change"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    decisionChanging[btn.dataset.id] = true;
    highlightedCommentId = btn.dataset.id;
    renderDrawer();
    const ta = document.querySelector('#comment-list [data-comment-id="' + cssEsc(btn.dataset.id) + '"]');
    if (ta) ta.scrollIntoView({ block: 'nearest' });
  }));
  root.querySelectorAll('[data-decision-action="cancel-change"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    delete decisionChanging[btn.dataset.id];
    delete decisionHint[btn.dataset.id];
    renderDrawer();
  }));
}
function cssEsc(s) { return String(s).replace(/(["\\\[\]\(\)])/g, '\\$1'); }

// After an action: the store and the server's counts, then every tab.
async function refreshStore() {
  await Promise.all([loadStore(), loadCategories()]);
  renderAll();
  document.dispatchEvent(new CustomEvent('annotate:store'));
}

// ── Rail tabs (E2: Feedback first, History last, extra tabs between) ──
// final/: the rail is shared by every tab of the page, so app/rail.js owns
// its tabs (Feedback · Documents · History); the shell asks it to switch.
function setActiveTab(tab) {
  if (!['feedback', 'documents', 'history'].includes(tab)) tab = 'feedback';
  activeTab = tab;
  if (window.AA) window.AA.rail.setTab(tab);
}
function wireTabs() {
  document.addEventListener('annotate:rail-tab', (e) => { activeTab = e.detail; });
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
  const node = document.getElementById('pop-node-name');
  const quote = target && target.selected_quote;
  node.classList.toggle('unified-selection-title', !!quote);
  node.textContent = quote ? '“' + quote + '”' : (anchorLabel || anchorId);
  node.title = node.textContent;
  document.getElementById('pop-ta').value = '';
  positionPopover(x, y);
  pop.classList.add('vis');
  setMobileBackdropVisible(true);
  document.getElementById('pop-ta').focus();
}
function positionPopover(cx, cy) {
  const pop = document.getElementById('popover');
  // Mobile: shell.css renders this as a fixed bottom sheet — leave its
  // inline left/top/bottom untouched so the stylesheet fully owns position
  // (an anchored click-point popover can otherwise land off-screen on a
  // 390px-wide viewport).
  if (isMobileLayout()) { pop.style.left = ''; pop.style.top = ''; return; }
  const pw = 332, ph = 220;
  let left = cx + 12, top = cy + 12;
  if (left + pw > window.innerWidth - 8) left = cx - pw - 12;
  if (top + ph > window.innerHeight - 8) top = cy - ph - 12;
  if (left < 8) left = 8;
  if (top < 8) top = 8;
  pop.style.left = left + 'px';
  pop.style.top = top + 'px';
}
function setMobileBackdropVisible(visible) {
  const bd = document.getElementById('mobile-dialog-backdrop');
  if (bd) bd.classList.toggle('vis', visible);
}
function closePopover() {
  document.getElementById('popover').classList.remove('vis');
  // Release focus from the hidden box so keys (E3) are not typed into it.
  const pta = document.getElementById('pop-ta');
  if (pta && document.activeElement === pta) pta.blur();
  pendingAnchor = null;
  editingCommentId = null;
  if (!document.getElementById('pin-popover').classList.contains('vis')) setMobileBackdropVisible(false);
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
    setActiveTab('feedback');
    focusSidebarCard(created.id);
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
  const num = NUM_MAP[c.id];
  const respHtml = c.response_text
    ? `<div class="pinpop-item-resp"><b>Agent:</b> ${ticketsHTML(c.response_text)}</div>`
    : '';
  return `<div class="pinpop-item" data-comment-id="${escAttr(c.id)}">
    <div class="pinpop-item-hdr">
      ${unreadDotHtml(c)}${num ? `<span class="citem-num">#${num}</span>` : ''}
    </div>
    <div class="pinpop-item-txt">${ticketsHTML(c.text)}</div>
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
    if (idSet.has(c.anchor_id) && onCurrentVersion(c)) byId[c.id] = c;
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
      goToCommentLocation(c.anchor_id, gotoVersionFor(c), c.id);
      focusSidebarCard(c.id);
    });
  });

  const pop = document.getElementById('pin-popover');
  pop.classList.add('vis');
  setMobileBackdropVisible(true);
  positionPinPopover(x, y);
  focusSidebarCard(comments[0].id);
}

function positionPinPopover(cx, cy) {
  const pop = document.getElementById('pin-popover');
  // Mobile: shell.css renders this as a fixed bottom sheet, clamped fully
  // on-screen by construction — an x/y-anchored placement is exactly the
  // "off-screen popover" failure mode this is meant to avoid on a phone.
  if (isMobileLayout()) { pop.style.left = ''; pop.style.top = ''; return; }
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
  if (!document.getElementById('popover').classList.contains('vis')) setMobileBackdropVisible(false);
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
  if (isMobileLayout()) setMobileSheetOpen(true); // pin/card focus needs the sheet visible, not just scrolled-to
  else if (isDrawerCollapsed()) setDrawerCollapsed(false); // desktop: rail must be expanded
  highlightedCommentId = commentId;
  // The card must be visible: Feedback tab, and its section open.
  if (activeTab !== 'feedback') setActiveTab('feedback');
  const fc = findCommentById(commentId);
  if (fc && !sectionOpen(sectionOf(fc))) SECTION_OPEN[sectionOf(fc)] = true; // for this visit only
  renderDrawer();
  const el = document.querySelector('#comment-list [data-comment-id="' + cssEsc(commentId) + '"]');
  if (el) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  sendCommentCountsToFrame(); // pin unread coloring may have changed via markRead
}

// ── General feedback (A3 + X2) ─────────────────────────────────────
// One field at the top of the Feedback tab, collapsed by default (Chang:
// "it needs to be collapsible/expandable. collapsed by default as it's not a
// box that's often used"). Its text is a draft that goes out with Send; the
// send summary shows the same text (D1) — there is no second box.
let gfOpen = false;
function renderGeneralFeedback() {
  if (DOC !== VIEW_DOC) return;
  const row = document.getElementById('general-feedback-toggle');
  const box = document.getElementById('general-feedback-box');
  if (!row || !box) return;
  const text = gfDraft();
  row.classList.toggle('has-text', !!text);
  row.setAttribute('aria-expanded', gfOpen ? 'true' : 'false');
  if (text && !gfOpen) {
    row.innerHTML = `<span class="gf-preview"><b>General feedback:</b> “${esc(firstLine(text))}”</span><span class="gf-edit" title="Edit">${ico('pencil')}</span>`;
    row.setAttribute('aria-label', 'Edit general feedback');
  } else {
    row.innerHTML = `${ico(gfOpen ? 'chevDown' : 'plus')}<span>General feedback</span>`;
    row.setAttribute('aria-label', gfOpen ? 'Collapse general feedback' : 'Add general feedback');
  }
  box.hidden = !gfOpen;
}
function setGeneralFeedbackOpen(open) {
  gfOpen = !!open;
  renderGeneralFeedback();
  if (gfOpen) document.getElementById('gf-ta').focus();
}
function wireGeneralFeedback() {
  document.getElementById('general-feedback-toggle').addEventListener('click', () => setGeneralFeedbackOpen(!gfOpen));
  document.getElementById('gf-done').addEventListener('click', () => setGeneralFeedbackOpen(false));
  document.getElementById('gf-cancel').addEventListener('click', () => {
    document.getElementById('gf-ta').value = '';
    setDraft('gf:' + CURRENT_VERSION, '');
    setGeneralFeedbackOpen(false);
    updateSendState();
  });
  // T11: general-feedback drafts persist per version
  document.getElementById('gf-ta').addEventListener('input', (e) => {
    setDraft('gf:' + CURRENT_VERSION, e.target.value || '');
    updateSendState();
  });
  renderGeneralFeedback();
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
  if (!collapsed) requestAnimationFrame(() => syncExcerptClamps(document.getElementById('comment-list')));
}
// (The left version rail moved into the History tab, so only the feedback
// rail collapses now.)

// P1: content fullscreen (a diagram's ⛶ overlay inside the iframe)
// auto-collapses both rails so the overlay gets the full window — the user
// must never see chrome occlusion without acting. Prior states restore on
// exit; the temporary collapse is never persisted to localStorage.
let railsBeforeFullscreen = null;
function autoCollapseForFullscreen(active) {
  if (active) {
    if (railsBeforeFullscreen) return; // already handled this overlay
    railsBeforeFullscreen = { drawer: isDrawerCollapsed() };
    setDrawerCollapsed(true, false);
  } else if (railsBeforeFullscreen) {
    setDrawerCollapsed(railsBeforeFullscreen.drawer, false);
    railsBeforeFullscreen = null;
  }
}
function isDrawerCollapsed() {
  return document.getElementById('drawer').classList.contains('collapsed');
}
function updateStripBadge() {
  const el = document.getElementById('drawer-strip-unread');
  if (!el || DOC !== VIEW_DOC) return;
  // B1: same "needs you" count as the Feedback tab badge.
  const needs = flattenAll(false).filter(c => inScope(c) && sectionOf(c) === 'needs').length;
  el.textContent = String(needs);
  el.style.display = needs > 0 ? '' : 'none';
}
function wireRailCollapse() {
  // On mobile the drawer is a bottom sheet, not a collapsible rail — this
  // same button (still visually the "»" affordance in the drawer header)
  // closes the sheet instead of setting the desktop .collapsed state, so
  // the two mechanisms never both apply to the one element at once.
  document.getElementById('drawer-collapse').addEventListener('click', () => {
    if (isMobileLayout()) { setMobileSheetOpen(false); return; }
    setDrawerCollapsed(true);
  });
  document.getElementById('drawer-strip').addEventListener('click', () => setDrawerCollapsed(false));
  try {
    // A collapsed-rail preference saved from a prior desktop session must
    // not apply on a phone: mobile visibility is owned entirely by
    // body.is-mobile-sheet-open, never by .collapsed.
    if (!isMobileLayout() && localStorage.getItem('annotate:drawerCollapsed') === '1') setDrawerCollapsed(true);
  } catch {}
}

// ── Mobile-only chrome: FAB, dialog backdrop ─────────────────────────
function wireMobileChrome() {
  const fab = document.getElementById('mobile-fab');
  if (fab) fab.addEventListener('click', () => setMobileSheetOpen(true));
  // U-12: the phone sheet closes with ×, a tap outside it or a swipe down.
  document.getElementById('unified-sheet-close').addEventListener('click', () => setMobileSheetOpen(false));
  document.getElementById('unified-sheet-backdrop').addEventListener('click', () => setMobileSheetOpen(false));
  const hdr = document.querySelector('.drawer-hdr');
  let touchY = null;
  hdr.addEventListener('touchstart', e => { touchY = e.touches[0] ? e.touches[0].clientY : null; }, { passive: true });
  hdr.addEventListener('touchend', e => {
    if (touchY !== null && e.changedTouches[0].clientY - touchY > 65) setMobileSheetOpen(false);
    touchY = null;
  }, { passive: true });
  // U-14: skip links.
  document.querySelectorAll('.unified-skip').forEach(a => a.addEventListener('click', e => {
    e.preventDefault();
    if (a.dataset.skip === 'document') {
      if (isMobileLayout()) setMobileSheetOpen(false);
      document.getElementById('content-frame').focus();
    } else {
      setActiveTab('feedback');
      setDrawerCollapsed(false, false);
      if (isMobileLayout()) setMobileSheetOpen(true);
      document.getElementById('drawer').focus();
    }
  }));
  const backdrop = document.getElementById('mobile-dialog-backdrop');
  if (backdrop) backdrop.addEventListener('click', () => { closePopover(); closePinPopover(); cancelRepin(); });
}

// ── Header: theme toggle and the avatar menu (E1) ────────────────────
function wireHeader() {
  applyTheme(currentTheme());
  // #theme=light|dark deep links (app.js router).
  document.addEventListener('annotate:set-theme', (e) => {
    if (e.detail !== 'light' && e.detail !== 'dark') return;
    applyTheme(e.detail);
    try { localStorage.setItem('annotate:theme', e.detail); } catch {}
  });
  document.getElementById('theme-toggle').addEventListener('click', () => {
    const t = currentTheme() === 'dark' ? 'light' : 'dark';
    applyTheme(t);
    try { localStorage.setItem('annotate:theme', t); } catch {}
  });
  document.getElementById('copy-link-btn').addEventListener('click', async event => {
    const button = event.currentTarget;
    try {
      const response = await fetch(apiUrl('./api/share-link'), { cache: 'no-store' });
      const data = await response.json();
      if (!response.ok || !data.url) return;
      await navigator.clipboard.writeText(data.url);
      button.textContent = 'Copied';
      setTimeout(() => { button.textContent = 'Copy link'; }, 2000);
    } catch { button.textContent = 'Copy failed'; }
  });
  const btn = document.getElementById('who-btn');
  const panel = document.getElementById('who-panel');
  const setOpen = (open) => { panel.hidden = !open; btn.setAttribute('aria-expanded', open ? 'true' : 'false'); };
  btn.addEventListener('click', (e) => { e.stopPropagation(); setOpen(panel.hidden); });
  document.addEventListener('click', (e) => {
    if (!panel.hidden && !e.target.closest('#who')) setOpen(false);
    // C3: a click anywhere else closes an open ⋯ menu
    if (openMenuId && !e.target.closest('.citem-menu, [data-action="menu"]')) {
      openMenuId = null;
      document.querySelectorAll('.citem-menu').forEach(m => { m.hidden = true; });
      document.querySelectorAll('[data-action="menu"]').forEach(b => b.setAttribute('aria-expanded', 'false'));
    }
  });
}

// ── Send (A2: one Send for everything) ─────────────────────────────
// 2.20 had three paths: header "Push to session" (comments), the round
// bar's "Finish review" (verdicts) and a per-card "Send now". Here every
// verdict, comment and general-feedback draft waits for one Send, which
// does what those did, in one go: answers typed without an option are
// recorded, general feedback is posted, the round is submitted, and open
// comments are pushed.
// A comment needs pushing only if it's open AND has user-side activity newer
// than its last push (2.20 rule, kept).
function needsPush(c) {
  if (c.status !== 'open' || (c.decision && c.decision.round_pending)) return false;
  const flaggedAt = c.flagged_at ? new Date(c.flagged_at).getTime() : 0;
  let latest = !isAgentAuthor(c.author) && c.created_at ? new Date(c.created_at).getTime() : 0;
  if (c.edited_at && !isAgentAuthor(c.edited_by || c.author)) latest = Math.max(latest, new Date(c.edited_at).getTime());
  for (const r of (c.replies || [])) {
    if (!isAgentAuthor(r.author)) latest = Math.max(latest, new Date(r.ts).getTime());
  }
  if (c.decision && !isAgentAuthor(c.decision.by)) latest = Math.max(latest, new Date(c.decision.ts).getTime());
  if (!latest) return false;
  if (!c.flagged_for_session) return true;
  return latest > flaggedAt;
}
function roundStats() {
  let pending = 0, decided = 0, total = 0, undecided = 0;
  for (const c of flattenAll(false)) {
    if (!hasDecisionRequest(c) || c.status === 'addressed_by_agent') continue;
    total++;
    if (decisionAnswer(c)) decided++; else undecided++;
    if (isRoundPending(c)) pending++;
  }
  return { pending, decided, total, undecided };
}

// ── final/: the one Send ─────────────────────────────────────────────
// app/send.js owns the header Send, the phone Send bar and the summary
// dialog for the whole page. For each document the shell supplies what it
// would send (sendables), its rows in the summary (renderSummaryInto) and
// its part of the sending (prepareDocCore); submitPage sends the page in
// one round. Wording is 2.20's.
function setSendNote(text, cls, ms) {
  if (window.AA) window.AA.send.note(text, cls, ms);
}
function updateSendState() {
  if (window.AA) window.AA.changed();
}
// Kept for callers that still name the 2.20 functions.
function updatePushCounter() { updateSendState(); }
function renderRoundBar() { updateSendState(); }

// ── D1: send summary rows for this document ─────────────────────────
// Every decision card with its answer and a pencil to change it in place;
// unanswered cards highlighted; unsent comments; the one general-feedback
// field (pencil to edit, + to add). Only the document on screen is edited
// in place; another document's pencil opens that document's tab.
let sumEditing = null; // card id or 'gf' being edited inside the summary
function summarySentence() {
  const s = roundStats();
  const plan = sendPlan();
  const q = sendables();
  // 2.20's own sentences, counted over exactly what this Send sends.
  const roundN = plan.round.length + plan.answers.length;
  if (roundN > 0) {
    return roundN + ' pending verdict' + (roundN === 1 ? '' : 's') + ' will be sent to the agent as one review round (' +
      (s.decided + plan.answers.length) + ' of ' + s.total + ' cards decided).';
  }
  return q.total === 0 ? 'Nothing to send yet.' : '';
}
function summaryWarning() {
  const plan = sendPlan();
  const roundN = plan.round.length + plan.answers.length;
  const undecided = flattenAll(false).filter(c => hasDecisionRequest(c) && !decisionAnswer(c) && !hasSayDraft(c)).length;
  if (undecided > 0 && roundN > 0) {
    return undecided + ' card' + (undecided === 1 ? ' is' : 's are') +
      ' still undecided — the round will report ' + (undecided === 1 ? 'it' : 'them') + ' as undecided.';
  }
  return '';
}
function renderSummaryInto(list, editable) {
  const plan = sendPlan();
  const byNum = (a, b) => (NUM_MAP[a.id] || 0) - (NUM_MAP[b.id] || 0);
  const inSend = new Set([...plan.round, ...plan.answers, ...plan.push].map(c => c.id));
  const rest = flattenAll(false).filter(c => hasDecisionRequest(c) && !inSend.has(c.id)).sort(byNum);
  const doc = DOC;
  const decisionRow = (c) => {
    const num = NUM_MAP[c.id];
    const answered = !!decisionAnswer(c);
    const draft = !answered && hasSayDraft(c);
    const missing = !answered && !draft;
    const editing = editable && sumEditing === c.id;
    const ansText = answered ? answerLabel(c).text : draft ? '“' + firstLine(sayDraft(c)) + '”' : 'Not answered';
    const sent = answered && !isRoundPending(c);
    const editLabel = missing ? 'Answer' : 'Change';
    let edit = '';
    if (editing) {
      const opts = decisionOptions(c.decision_request);
      edit = `<div class="sum-edit">
        <div class="sum-opts">${opts.map(o => {
          const action = o.custom ? 'custom' : o.id;
          const extra = o.custom ? ` data-option-id="${escAttr(o.id)}" data-option-label="${escAttr(o.labelText)}"` : '';
          return `<button type="button" class="btn btn-sm decision-btn-sum" data-decision-action="${action}" data-id="${escAttr(c.id)}"${extra}>${o.labelHtml}</button>`;
        }).join('')}</div>
        <textarea class="textarea textarea-sm sum-gf-ta" data-decision-say-ta="${escAttr(c.id)}" placeholder="Comment (optional)" rows="2"></textarea>
        <div class="decision-feedback" data-decision-feedback="${escAttr(c.id)}"></div>
      </div>`;
    }
    const pencil = (canChangeAnswer(c) || !answered)
      ? `<button type="button" class="btn btn-ghost btn-xs btn-square" data-sum-edit="${escAttr(c.id)}" data-sum-doc="${doc}" aria-label="${editLabel} #${num || ''}" title="${editLabel}" aria-expanded="${editing ? 'true' : 'false'}">${ico('pencil')}</button>`
      : '<span class="btn btn-xs btn-square btn-ghost" aria-hidden="true" style="visibility:hidden"></span>';
    return `<div class="sum-row${missing ? ' is-missing' : ''}" data-sum-id="${escAttr(c.id)}">
      <div class="sum-main">
        <span class="sum-q">${num ? `<span class="citem-num">#${num}</span>` : ''}${esc(displayPrompt(c))}</span>
        <span class="sum-a${sent ? ' is-sent' : ''}">${esc(ansText)}${sent ? ' · sent' : ''}</span>
        ${pencil}
      </div>
      ${edit}
    </div>`;
  };
  const commentRow = (c) => {
    if (hasDecisionRequest(c)) return decisionRow(c);
    const num = NUM_MAP[c.id];
    const last = (c.replies || []).filter(r => !isAgentAuthor(r.author)).slice(-1)[0];
    const text = last ? last.text : c.text;
    return `<div class="sum-row"><div class="sum-main"><span class="sum-q">${num ? `<span class="citem-num">#${num}</span>` : ''}${esc(firstLine(text))}</span></div></div>`;
  };
  const group = (label, n) => `<div class="sum-group">${label}${n == null ? '' : ` <span class="badge badge-sm badge-ghost">${n}</span>`}</div>`;
  let html = '';
  const verdictRows = [...plan.round, ...plan.answers].sort(byNum);
  if (verdictRows.length) html += group('Verdicts', verdictRows.length) + verdictRows.map(decisionRow).join('');
  if (plan.push.length) html += group('Open comments', plan.push.length) + plan.push.slice().sort(byNum).map(commentRow).join('');
  // General feedback: pencil to edit inline, or + to add (Chang, D1).
  const gf = gfDraft();
  const gfEditing = editable && sumEditing === 'gf';
  html += group('General feedback', gf ? 1 : 0);
  html += `<div class="sum-row" data-sum-id="${editable ? 'gf' : 'gf-' + doc}">
    <div class="sum-main">
      <span class="sum-q">${gf ? '“' + esc(firstLine(gf)) + '”' : '<span class="sum-none">None</span>'}</span>
      <button type="button" class="btn btn-ghost btn-xs btn-square" data-sum-edit="gf" data-sum-doc="${doc}" aria-label="${gf ? 'Edit general feedback' : 'Add general feedback'}" title="${gf ? 'Edit' : 'Add general feedback'}" aria-expanded="${gfEditing ? 'true' : 'false'}">${ico(gf ? 'pencil' : 'plus')}</button>
    </div>
    ${gfEditing ? `<div class="sum-edit"><textarea class="textarea textarea-sm sum-gf-ta" id="sum-gf-ta" placeholder="Feedback not tied to a specific section&hellip;" rows="3"></textarea></div>` : ''}
  </div>`;
  if (rest.length) html += group('Not in this Send') + rest.map(decisionRow).join('');
  list.innerHTML = html;

  // Another document's rows: the pencil opens that document's tab, where
  // the same summary opens with that row in edit mode.
  if (!editable) {
    list.querySelectorAll('[data-sum-edit]').forEach(btn => btn.addEventListener('click', () => {
      if (window.AA) window.AA.go({ view: btn.dataset.sumDoc, send: '1', sumedit: btn.dataset.sumEdit });
    }));
    return;
  }
  const gta = list.querySelector('#sum-gf-ta');
  if (gta) {
    gta.value = DRAFTS['gf:' + CURRENT_VERSION] || '';
    gta.addEventListener('input', () => {
      setDraft('gf:' + CURRENT_VERSION, gta.value || '');
      const box = document.getElementById('gf-ta');
      if (box) box.value = gta.value;
      renderGeneralFeedback();
      updateSendState();
      syncSummaryCounts();
    });
    gta.focus();
  }
  list.querySelectorAll('[data-decision-say-ta]').forEach(ta => {
    ta.value = DRAFTS['say:' + ta.dataset.decisionSayTa] || '';
    ta.addEventListener('input', () => {
      setDraft('say:' + ta.dataset.decisionSayTa, ta.value || '');
      syncStripSayDraft(ta.dataset.decisionSayTa);
      updateSendState();
    });
  });
  list.querySelectorAll('[data-sum-edit]').forEach(btn => btn.addEventListener('click', () => {
    sumEditing = sumEditing === btn.dataset.sumEdit ? null : btn.dataset.sumEdit;
    renderSummary();
    if (sumEditing === 'gf') renderGeneralFeedback();
  }));
  list.querySelectorAll('.decision-btn-sum').forEach(btn => btn.addEventListener('click', async () => {
    const r = await pickOption(list, btn);
    if (r) { sumEditing = null; renderSummary(); }
  }));
}
function renderSummary() { if (window.AA) window.AA.send.render(); }
function syncSummaryCounts() { if (window.AA) window.AA.send.syncCounts(); }
function openRoundConfirm() { sumEditing = null; if (window.AA) window.AA.send.open(); }
function closeRoundConfirm() { sumEditing = null; if (window.AA) window.AA.send.close(); }
function isRoundConfirmOpen() { return !!(window.AA && window.AA.send.isOpen()); }
function submitRound() { if (window.AA) return window.AA.send.submit(); }

// What this document's part of one Send carries, as receipt lines.
function sendItems() {
  const p = sendPlan();
  const items = [...p.round, ...p.answers, ...p.push].map(c => {
    const last = (c.replies || []).filter(r => !isAgentAuthor(r.author)).slice(-1)[0];
    const label = hasDecisionRequest(c) ? displayPrompt(c) : firstLine(last ? last.text : c.text);
    const answer = decisionAnswer(c) ? answerLabel(c).text : hasSayDraft(c) ? sayDraft(c) : '';
    return { label: '#' + (NUM_MAP[c.id] || '') + ' · ' + label, answer };
  });
  if (gfDraft()) items.push({ label: 'General feedback', answer: gfDraft() });
  return items;
}
// A document's part of one Send (2.20's order): comment-box text on an
// unanswered card becomes its answer, general feedback becomes its
// general:* item. No UI here; app/send.js reports it.
async function prepareDocCore() {
  const items = sendItems();
  let ok = true;
  for (const c of flattenAll(false).filter(hasSayDraft)) {
    let r = await apiDecision(c.id, 'comment', sayDraft(c));
    if (!r || r.fallback) r = await apiDecisionFallback(c.id, 'comment', sayDraft(c));
    if (r) clearSayDraft(c.id); else ok = false;
  }
  const gf = gfDraft();
  if (gf && IDENTITY) {
    const created = await apiCreateComment('general:' + CURRENT_VERSION, 'General feedback', gf, CURRENT_VERSION);
    if (created) setDraft('gf:' + CURRENT_VERSION, ''); else ok = false;
  }
  if (DOC === VIEW_DOC) {
    const g = document.getElementById('gf-ta');
    if (g) g.value = DRAFTS['gf:' + CURRENT_VERSION] || '';
  }
  return { ok, items };
}
// A reopened finding this reviewer has not sent yet.
function isReopenPending(c) {
  const last = (c.reopened || []).slice(-1)[0];
  return !!(c.round_pending && last && IDENTITY && (IDENTITY.reviewer_authors || [IDENTITY.email]).includes(last.by));
}
// Everything this reviewer has recorded for the page's one round.
function pageRoundPending() {
  return flattenStore(false).filter(c => isRoundPending(c) || isReopenPending(c)).length;
}
// The page's one Send: every document's drafts, then ONE round (verdicts,
// reopens and Library revisions across every tab), then ONE push of the open
// comments with new activity. `alsoPending` says another tab has round-pending
// work the comment store does not show (Library revisions).
// `receipt`: the Send summary's lines, kept by the server for History.
async function submitPage(alsoPending, receipt) {
  let ok = true, sentCount = 0, delivered = false, last = null;
  const send = receiptPayload(receipt);
  for (const doc of DOCS) {
    const r = await withDocAsync(doc, prepareDocCore);
    if (!r.ok) ok = false;
  }
  await loadStore();
  if (roundsEnabled() && (pageRoundPending() > 0 || alsoPending)) {
    const j = await withDocAsync('review', () => apiRoundSubmit(null, send));
    if (j) { last = j; sentCount += (j.comment_count || 0) + (j.edit_count || 0); delivered = delivered || j.delivery === 'active_monitor'; } else ok = false;
    await loadStore();
  }
  if (flattenStore(false).some(needsPush)) {
    const j = await apiPushAll(send);
    if (j) { last = j; sentCount += j.flagged_count || 0; delivered = delivered || j.delivery === 'active_monitor'; } else ok = false;
  }
  if (last) {
    SESSION_MONITOR = { active: delivered, monitor_count: last.monitor_count || 0, delivery: last.delivery || 'queued', owner: last.monitor_owner || null };
  }
  historyDirty = true;
  await Promise.all([loadStore(), loadReadState()]);
  loadHistory();
  return { ok: ok || !!last, sentCount, delivered, any: !!last, send_id: send.send_id };
}
function receiptPayload(receipt) {
  if (!Array.isArray(receipt) || !receipt.length) return {};
  const id = (crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 12));
  return {
    send_id: id,
    receipt: receipt.slice(0, 200).map(it => {
      const line = { cat: it.cat, label: String(it.label || '—').slice(0, 300) };
      if (it.answer) line.answer = String(it.answer).slice(0, 600);
      return line;
    }),
  };
}
// 2.20 behaviour and wording: clears the pending verdicts only (typed
// comments and general feedback stay as drafts). Returns the count or null.
async function discardPage() {
  const j = await apiRoundDiscard();
  if (!j) return null;
  await loadStore();
  return j.comment_count != null ? j.comment_count : 0;
}
function wireRoundBar() {
  let t = null;
  window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(updateSendState, 120); });
}

// ── v2.19 owner chip ─────────────────────────────────────────────────
// current.meta.json `owner` is stamped by cli.py publish/claim:
// {owner_session, owner_agent, owner_label, claimed_at}. Read-only here —
// no liveness polling; META is refreshed by the existing 8s poll.
function relTime(iso) {
  const t = iso ? new Date(iso).getTime() : NaN;
  if (!t) return '';
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return 'just now';
  const m = s / 60;
  if (m < 60) return Math.round(m) + ' min ago';
  const h = m / 60;
  if (h < 24) return Math.round(h) + ' h ago';
  const d = h / 24;
  if (d < 14) return Math.round(d) + ' d ago';
  try { return 'on ' + new Date(iso).toLocaleDateString(); } catch { return ''; }
}
function renderOwnerChip() {
  const el = document.getElementById('owner-chip');
  if (!el) return;
  const o = META && META.owner;
  const label = o && typeof o === 'object'
    ? (o.owner_label || o.label || o.owner_agent || o.owner_session || null)
    : null;
  const row = document.getElementById('owner-row');
  if (!label) {
    if (row) row.hidden = true;
    el.textContent = '';
    el.title = '';
    return;
  }
  if (row) row.hidden = false;
  const when = o.claimed_at || o.ts || o.since || o.updated_at || null;
  el.textContent = '';
  const dot = document.createElement('span');
  dot.className = 'owner-chip-dot';
  el.appendChild(dot);
  el.appendChild(document.createTextNode(label));
  const rel = when ? relTime(when) : '';
  if (rel) {
    const w = document.createElement('span');
    w.className = 'owner-chip-when';
    w.textContent = ' · claimed ' + rel;
    el.appendChild(w);
  }
  el.title = (o.owner_session ? 'Session ' + o.owner_session : 'Owner ' + label)
    + (o.owner_agent ? ' (' + o.owner_agent + ')' : '')
    + (when ? '\nclaimed ' + when : '');
}

// ── Bridge: postMessage with the content iframe ─────────────────────
// Content -> shell: {type:'annotate:pin-click', anchorId, anchorLabel, x, y}   (anchor clicked → CREATE popover)
//                   {type:'annotate:pin-open', anchorId, anchorLabel, commentIds, x, y}  (pin clicked → reverse lookup)
//                   {type:'annotate:ready', version}
//                   {type:'annotate:scroll-result', anchorId, found}
//                   {type:'annotate:decision-posted', commentId}  (body-inline decision strip resolved)
//                   {type:'annotate:excerpts', version, excerpts: {anchorId: {text, name, card} | {missing}}}
//                   {type:'annotate:back-to-card', commentId}  ("Back to #N" clicked on an evidence target)
// Shell -> content: {type:'annotate:scroll-to', anchorId, target, back: {commentId, n, from} | null}
//                   {type:'annotate:comment-counts', counts: {anchorId: n},
//                    pins: {anchorId: [{id, n, unread, target, decision,
//                                        decisionRequest, decisionVerdict}]}}
// decisionRequest is sent whenever c.decision_request exists — UNRESOLVED
// (decision boolean/decisionVerdict null) OR RESOLVED (decisionVerdict set).
// adapter.js reads "decisionRequest + decisionVerdict both present" as
// resolved-but-changeable, so its body-inline strip can offer the same
// "↺ Change" affordance the rail card does (see buildDecisionItemEl). An
// older adapter.js that predates this simply ignores the extra field on a
// resolved entry and shows the plain chip — graceful, not broken.
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
    // F1: only our own document frame, on our own origin, is heard.
    const frameEl = document.getElementById('content-frame');
    if (!BRIDGE_ORIGIN || e.origin !== BRIDGE_ORIGIN || !frameEl || e.source !== frameEl.contentWindow) return;
    const data = e.data || {};
    if (!data || typeof data !== 'object') return;
    if (data.type === 'annotate:navigate') {
      // U-11: a link to another page on this server opens in the whole window.
      let url;
      try { url = new URL(String(data.url || ''), location.href); } catch { return; }
      if (url.origin === BRIDGE_ORIGIN) window.location.assign(url.href);
      return;
    }
    if (data.type === 'annotate:open-version') {
      // A plan revision's previous/next link opens it in the same tab.
      if (window.AA && VIEW_DOC && /^v\d{1,10}$/.test(String(data.version))) window.AA.go({ view: VIEW_DOC, v: data.version });
      return;
    }
    // The frame shows VIEW_DOC; a message is only handled while that
    // document's state is the one loaded (and never from a frame that is
    // still showing the previous document).
    if (DOC !== VIEW_DOC) return;
    if (frameEl.dataset.doc !== DOC) return;
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
    } else if (data.type === 'annotate:excerpts') {
      // Text of the anchors the open cards cite, for the rail card's quoted
      // excerpt and evidence previews. Posted only when it changes.
      if (!data.excerpts || typeof data.excerpts !== 'object') return;
      if (data.version && data.version !== CURRENT_VERSION) return; // a stale document
      EXCERPTS = data.excerpts;
      EXCERPTS_VERSION = data.version || CURRENT_VERSION;
      renderDrawer();
    } else if (data.type === 'annotate:back-to-card') {
      // "Back to #N" on an evidence target the rail card sent the reader to.
      const c = data.commentId ? findCommentById(data.commentId) : null;
      if (c) focusSidebarCard(c.id);
    } else if (data.type === 'annotate:key') {
      onShellKey({ key: String(data.key || ''), metaKey: !!data.meta, ctrlKey: !!data.ctrl, shiftKey: !!data.shift, altKey: false,
        target: document.body, preventDefault() {} });
    } else if (data.type === 'annotate:say-draft') {
      // A1: the body strip's comment box and the rail card's box are the
      // same draft, so either one can carry the card's comment to Send.
      if (!data.commentId) return;
      const text = typeof data.text === 'string' ? data.text : '';
      setDraft('say:' + data.commentId, text);
      const ta = document.querySelector('#comment-list [data-decision-say-ta="' + cssEsc(data.commentId) + '"]');
      if (ta && ta !== document.activeElement) { ta.value = text; syncSayHint(ta); }
      updateSendState();
    } else if (data.type === 'annotate:decision-posted') {
      // A body-inline decision strip (adapter.js) just resolved a decision.
      // Refresh immediately so the rail card's decision block and the pins
      // payload sync now, not on the 8s poll.
      refreshStore().then(() => markReadAfterAction(data.commentId));
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
  if (!frame || !frame.contentWindow || DOC !== VIEW_DOC) return;
  const counts = {};
  const pins = {};
  for (const [aid, items] of Object.entries(STORE.anchors || {})) {
    // F9: unresolved decision cards get a pin + strip on whichever version
    // is being viewed (adapter.js skips the strip if the anchor no longer
    // exists in this version's document).
    const list = items.map(c => Object.assign({}, c, { anchor_id: aid }))
      .filter(c => docOf(c) === DOC).filter(onCurrentVersion).filter(c => !isNewerThanViewed(c));
    if (!list.length) continue;
    counts[aid] = list.length;
    pins[aid] = list
      .map(c => {
        const withdrawn = c.status === 'addressed_by_agent' && !decisionAnswer(c);
        const hasDecisionRequest = !!(c.decision_request && !withdrawn &&
          c.status !== 'archived' && c.status !== 'resolved_in_version');
        const decisionPending = hasDecisionRequest && !decisionAnswer(c);
        const decisionResolved = !!(decisionAnswer(c) &&
          c.status !== 'archived' && c.status !== 'resolved_in_version');
        return {
          id: c.id,
          n: NUM_MAP[c.id] || 0,
          unread: readStateOf(c) !== 'read',
          // Creation-time granular target. Older comments without one remain
          // at the anchor corner; new comments can render the numbered pin at
          // the exact clicked element/offset inside that anchor.
          target: c.target || null,
          decision: decisionPending,
          // Body-inline decision strips (adapter.js): raw prompt/options text.
          // Sent whenever the decision_request still exists — including after
          // resolution — so the strip can offer "↺ Change" the same way the
          // rail card does. adapter.js assigns this via textContent only,
          // never innerHTML.
          // The card's own text: the body strip shows it under the prompt
          // when it says more, since the strip replaces the generated card.
          text: hasDecisionRequest && typeof c.text === 'string' ? c.text : null,
          decisionRequest: hasDecisionRequest ? {
            prompt: displayPrompt(c),
            options: Array.isArray(c.decision_request.options) ? c.decision_request.options : null,
            // v2.19 fields (absent on a legacy request → undefined → adapter
            // renders exactly the old strip).
            context: typeof c.decision_request.context === 'string' ? c.decision_request.context : null,
            recommendation: typeof c.decision_request.recommendation === 'string' ? c.decision_request.recommendation : null,
            consequences: (c.decision_request.consequences && typeof c.decision_request.consequences === 'object') ? c.decision_request.consequences : null,
            evidence: Array.isArray(c.decision_request.evidence) ? c.decision_request.evidence : null,
            impact: typeof c.decision_request.impact === 'string' ? c.decision_request.impact : null,
            blocking: c.decision_request.blocking === true,
          } : null,
          decisionVerdict: decisionResolved ? c.decision.verdict : null,
          // Feedback prototype: the answer as one phrase (C1) and the shared
          // comment-box draft (A1) for the body strip.
          answerText: decisionResolved ? answerLabel(c).text : null,
          sayDraft: DRAFTS['say:' + c.id] || '',
          // v2.19 round mode: verdict recorded but not yet sent.
          roundPending: isRoundPending(c),
        };
      })
      .sort((a, b) => a.n - b.n);
  }
  // `rounds` tells the adapter to post its own verdicts with defer_push;
  // `changes` tells it the server offers the D2 "Request changes" verdict;
  // `select` tells it a custom option id posts the D3 `select` verdict.
  // Live state for every question card baked into the page body: the body
  // must never show a question as open when the rail says it is not.
  const cardStates = {};
  const noteCard = (c, archived) => {
    if (docOf(c) !== DOC || isNewerThanViewed(c)) return;
    if (!c.decision_request) return;
    const prev = cardStates[c.anchor_id];
    if (prev && !prev.archived) return; // a live card beats an archived copy
    const cls = archived ? 'done' : classify(c);
    cardStates[c.anchor_id] = { state: cls, label: statusLabel(c, cls), archived };
  };
  for (const [aid, items] of Object.entries(STORE.anchors || {})) {
    items.forEach(c => noteCard(Object.assign({}, c, { anchor_id: aid }), false));
  }
  for (const [aid, items] of Object.entries(STORE.archived || {})) {
    (Array.isArray(items) ? items : []).forEach(c =>
      noteCard(Object.assign({}, c, { anchor_id: aid, status: 'archived' }), true));
  }
  postToFrame({ type: 'annotate:comment-counts', counts, pins, cardStates, rounds: roundsEnabled(), changes: changesEnabled(), select: selectVerdictId() === 'select' });
}

function syncStripSayDraft(commentId) {
  postToFrame({ type: 'annotate:say-draft-set', commentId, text: DRAFTS['say:' + commentId] || '' });
}

function scrollToAnchorInFrame(anchorId, target, back) {
  postToFrame({ type: 'annotate:scroll-to', anchorId, target: target || null, back: back || null });
}

// ── Wire popover buttons ─────────────────────────────────────────────
function wirePopover() {
  document.getElementById('pop-close').addEventListener('click', closePopover);
  document.getElementById('pop-cancel').addEventListener('click', closePopover);
  document.getElementById('pop-save').addEventListener('click', savePopover);
  // One delegated keydown handler on the document: Ctrl/Cmd+Enter submits
  // whichever comment composer holds focus, so every composer behaves
  // identically and the binding survives drawer re-renders. The reply and
  // decision-comment textareas used to wire their own per-render listeners,
  // which drifted apart and left the general-feedback box with no shortcut.
  document.addEventListener('keydown', onShellKey);
}
// One key handler for keys pressed in the rail and keys the document frame
// forwards ('annotate:key', see adapter.js) — E3 shortcuts work after a
// click in the document too.
function onShellKey(e) {
  {
    if (e.key === 'Escape') {
      closePopover(); closePinPopover(); cancelRepin(); closeRoundConfirm();
      if (openMenuId) { openMenuId = null; document.querySelectorAll('.citem-menu').forEach(m => { m.hidden = true; }); }
      const wp = document.getElementById('who-panel'); if (wp) wp.hidden = true;
    }
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      const t = e.target;
      if (isRoundConfirmOpen()) {
        e.preventDefault();
        submitRound();
      } else if (document.getElementById('popover').classList.contains('vis')) {
        savePopover();
      } else if (t.classList && t.classList.contains('reply-ta')) {
        e.preventDefault();
        const btn = document.querySelector('[data-action="reply"][data-id="' + cssEsc(t.dataset.replyFor) + '"]');
        if (btn) btn.click();
      } else if (!document.getElementById('send-btn').disabled || isMobileLayout()) {
        // E3: ⌘↵ opens the send summary (and sends from inside it, above).
        e.preventDefault();
        openRoundConfirm();
      }
      return;
    }
    handleShortcut(e);
  }
}

// ── E3: keyboard shortcuts ────────────────────────────────────────────
// A previous / F next card · 1–9 pick an option on the active card ·
// C comment on the active card · ⌘↵ send. Never while typing.
function visibleCards() {
  return Array.from(document.querySelectorAll('#comment-list .citem'));
}
function handleShortcut(e) {
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  // final/: on Library and Findings the same keys move through that view.
  if (DOC !== VIEW_DOC) { if (window.AA) window.AA.shortcut(e); return; }
  const t = e.target;
  if (t && t.closest && (t.isContentEditable || t.closest('textarea, input, select'))) return;
  if (isRoundConfirmOpen() || document.getElementById('popover').classList.contains('vis')) return;
  const k = e.key.toLowerCase();
  if (k === 'a' || k === 'f') {
    if (activeTab !== 'feedback') setActiveTab('feedback');
    const cards = visibleCards();
    if (!cards.length) return;
    e.preventDefault();
    let i = cards.findIndex(el => el.dataset.commentId === highlightedCommentId);
    i = i === -1 ? (k === 'f' ? 0 : cards.length - 1) : Math.max(0, Math.min(cards.length - 1, i + (k === 'f' ? 1 : -1)));
    const c = findCommentById(cards[i].dataset.commentId);
    if (!c) return;
    markRead([c]);
    highlightedCommentId = c.id;
    sendCommentCountsToFrame();
    if (isGeneralAnchor(c.anchor_id)) renderDrawer();
    else goToCommentLocation(c.anchor_id, gotoVersionFor(c), c.id);
    const el = document.querySelector('#comment-list [data-comment-id="' + cssEsc(c.id) + '"]');
    if (el) el.scrollIntoView({ block: 'nearest' });
    return;
  }
  const card = highlightedCommentId && document.querySelector('#comment-list [data-comment-id="' + cssEsc(highlightedCommentId) + '"]');
  if (!card) return;
  if (/^[1-9]$/.test(e.key)) {
    const btn = card.querySelectorAll('.decision-btn')[Number(e.key) - 1];
    if (btn && !btn.disabled) { e.preventDefault(); btn.click(); }
    return;
  }
  if (k === 'c') {
    const ta = card.querySelector('.decision-say-ta, .reply-ta');
    if (ta) { e.preventDefault(); ta.focus(); }
  }
}

// ── Master render ─────────────────────────────────────────────────
function renderAll() {
  renderVersionRail();
  if (DOC !== VIEW_DOC) return;
  if (window.AA) window.AA.docTitle(DOC, CURRENT_VERSION ? ('Version ' + CURRENT_VERSION) : '');
  renderDrawer();
  renderGeneralFeedback();
  updateSendState();
  renderOwnerChip();
  sendCommentCountsToFrame();
}

// ── Document state ───────────────────────────────────────────────
// The variables at the top hold the version state of document DOC; the
// other document's is kept in DOC_STATE. The comment store, read state,
// numbering and project are page-wide and never swapped.
const DOC_STATE = {};
const lastSnap = {};
let docBusy = 0;
let frameReady = { doc: null, version: null };
let frameWaiters = [];
function freshDocState(doc) {
  return {
    META: { current: null, history: [], content_stamps: {} }, SEEN: {}, CURRENT_VERSION: null, EXCERPTS: {}, EXCERPTS_VERSION: null,
    DRAFTS: loadDrafts(doc), pendingGoto: null, highlightedCommentId: null, openMenuId: null, sumEditing: null, gfOpen: false,
  };
}
function captureDocState() {
  return { META, SEEN, CURRENT_VERSION, EXCERPTS, EXCERPTS_VERSION, DRAFTS, pendingGoto, highlightedCommentId, openMenuId, sumEditing, gfOpen };
}
function installDocState(s) {
  ({ META, SEEN, CURRENT_VERSION, EXCERPTS, EXCERPTS_VERSION, DRAFTS, pendingGoto, highlightedCommentId, openMenuId, sumEditing, gfOpen } = s);
}
function enterDoc(doc) {
  DOC_STATE[DOC] = captureDocState();
  installDocState(DOC_STATE[doc] || freshDocState(doc));
  DOC = doc;
}
// A synchronous read of another document (counts, summary rows).
function withDoc(doc, fn) {
  if (doc === DOC) return fn();
  const prev = DOC;
  enterDoc(doc);
  try { return fn(); } finally { enterDoc(prev); }
}
// An asynchronous job on one document (loading, sending). Jobs run one at a
// time; the page shows a modal (the Send summary) or nothing interactive
// for that document meanwhile.
let docQueue = Promise.resolve();
function withDocAsync(doc, fn) {
  const run = async () => {
    const prev = DOC;
    docBusy++;
    enterDoc(doc);
    try { return await fn(); } finally { enterDoc(prev); docBusy--; }
  };
  const p = docQueue.then(run, run);
  docQueue = p.catch(() => {});
  return p;
}
function latestVersion() {
  return META.current || (META.history && META.history.length ? META.history[META.history.length - 1].version : null);
}
async function loadDocState(doc) {
  return withDocAsync(doc, async () => {
    await loadMeta();
    const want = window.AA ? window.AA.versionFor(doc) : null;
    if (!CURRENT_VERSION) CURRENT_VERSION = (want && (META.history || []).some(h => h.version === want)) ? want : latestVersion();
    await loadSeen();
    lastSnap[doc] = JSON.stringify(STORE) + JSON.stringify(META) + JSON.stringify(READ);
  });
}
// Re-read the page from the server (after a Send); renders the document on
// screen and tells every tab.
async function reloadPage() {
  await Promise.all([loadStore(), loadReadState(), loadCategories()]);
  if (VIEW_DOC) withDoc(VIEW_DOC, renderAll);
  document.dispatchEvent(new CustomEvent('annotate:store'));
  if (window.AA) window.AA.changed();
}
function frameIsReady() {
  return frameReady.doc === VIEW_DOC && frameReady.version === CURRENT_VERSION;
}
function whenFrameReady() {
  if (frameIsReady()) return Promise.resolve();
  return new Promise(res => { frameWaiters.push(res); setTimeout(res, 8000); });
}
// Show a document: its rail, its frame and its History section.
async function activateDoc(doc, version) {
  await DOCS_LOADED;
  await docQueue;
  if (!DOCS.includes(doc)) doc = 'review';
  if (DOC !== doc) enterDoc(doc);
  VIEW_DOC = doc;
  if (version && version !== CURRENT_VERSION && (META.history || []).some(h => h.version === version)) CURRENT_VERSION = version;
  const frame = document.getElementById('content-frame');
  if (frame.dataset.doc !== doc || frame.dataset.version !== CURRENT_VERSION || frame.dataset.plan !== String(PLAN_ID)) {
    frameReady = { doc: null, version: null };
    frame.dataset.plan = String(PLAN_ID);
    loadIframe(CURRENT_VERSION);
  }
  const gf = document.getElementById('gf-ta');
  if (gf) gf.value = DRAFTS['gf:' + CURRENT_VERSION] || '';
  projectSnapshot = '';
  renderProject();
  loadDelivery();
  renderAll();
  return whenFrameReady();
}
function parkDoc() {
  VIEW_DOC = null;
}

// ── Categories (one page per project) ───────────────────────────────
// ./api/categories: which tabs exist, the server's counts per tab (so every
// device agrees), the findings sets, the plans and the linked pages.
let CATEGORIES = null;
async function loadCategories() {
  try {
    const r = await fetch(apiUrl('./api/categories'), { cache: 'no-store', signal: AbortSignal.timeout(10000) });
    if (!r.ok) return false;
    CATEGORIES = await r.json();
    PLANS = Array.isArray(CATEGORIES.plans) ? CATEGORIES.plans : [];
    if (!PLAN_ID || !PLANS.some(p => p.id === PLAN_ID)) PLAN_ID = PLANS.length ? PLANS[0].id : null;
    DOCS = PLAN_ID ? ['review', 'plans'] : ['review'];
    if (window.AnnotateDocs) window.AnnotateDocs.docs = DOCS;
    return true;
  } catch { return false; }
}
// The Plans tab shows one plan; another plan starts from its latest revision.
async function selectPlan(id) {
  if (!PLANS.some(p => p.id === id) || id === PLAN_ID) return;
  await docQueue;
  if (DOC === 'plans') enterDoc('review');
  PLAN_ID = id;
  delete DOC_STATE.plans;
  await loadDocState('plans');
  if (window.AA) window.AA.go({ view: 'plans', plan: id });
}

// ── Init ─────────────────────────────────────────────────────────
// F7: a private review link (#review=<key>) opens a reviewer session first;
// without it every API call is refused on the public origin.
async function startReviewerSession() {
  const reviewKey = new URLSearchParams(location.hash.slice(1)).get('review');
  if (!reviewKey) return true;
  let name = 'Reviewer';
  try { name = localStorage.getItem('annotate:reviewer-name') || name; } catch {}
  const response = await fetch(apiUrl('./api/reviewer/session'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: reviewKey, name }) }).catch(() => null);
  if (!response || !response.ok) {
    showStatus('This review link is invalid or expired.');
    return false;
  }
  history.replaceState(null, '', location.pathname + location.search);
  return true;
}
function showStatus(text) {
  const status = document.getElementById('delivery-status');
  status.hidden = false;
  status.textContent = text;
}
// True while the reviewer is typing in the rail or the document.
function isEditing() {
  const ae = document.activeElement;
  if (ae && ae.closest('textarea,input,[contenteditable="true"]')) return true;
  try {
    const inner = document.getElementById('content-frame').contentDocument.activeElement;
    return !!(inner && inner.closest('textarea,input,[contenteditable="true"]'));
  } catch { return false; }
}
let DOCS_LOADED_resolve;
const DOCS_LOADED = new Promise(res => { DOCS_LOADED_resolve = res; });
async function init() {
  if (!await startReviewerSession()) return;

  try {
    SECTION_OPEN = JSON.parse(localStorage.getItem('annotate:sections') || '{}') || {};
  } catch {}

  // T11: live draft capture — every keystroke lands in the persistent
  // store, so even a reload (not just a re-render/version switch) keeps it.
  document.getElementById('comment-list').addEventListener('input', (e) => {
    if (e.target && e.target.classList && e.target.classList.contains('reply-ta')) {
      setDraft(e.target.dataset.replyFor, e.target.value || '');
    }
  });

  wireHeader();
  wireTabs();
  wirePopover();
  wirePinPopover();
  wireGeneralFeedback();
  wireRailCollapse();
  wireMobileChrome();
  wireRoundBar();
  wireBridge();
  window.addEventListener('message', (e) => {
    const frame = document.getElementById('content-frame');
    if (!frame || e.source !== frame.contentWindow || e.origin !== BRIDGE_ORIGIN) return;
    if (!e.data || e.data.type !== 'annotate:ready') return;
    frameReady = { doc: frame.dataset.doc, version: frame.dataset.version };
    const w = frameWaiters; frameWaiters = [];
    setTimeout(() => w.forEach(f => f()), 0);
  });

  await Promise.all([loadSessionMonitor(), loadCapabilities()]);
  document.getElementById('share-row').hidden = !(CAPS && CAPS.private_share_links);

  IDENTITY = await resolveIdentity();
  AUTHOR = authorValue(IDENTITY);
  updateAuthorIndicator();
  if (!IDENTITY && location.protocol === 'https:' && !CAPS) {
    showStatus('Open the private review link to view this page.');
    return;
  }

  // The page's store and every document are loaded up front, so the page's
  // counts and the one Send cover all of them before any tab is opened.
  await Promise.all([loadStore(), loadReadState(), loadCategories(), loadProject()]);
  DRAFTS = loadDrafts(DOC);
  for (const doc of DOCS) await loadDocState(doc);
  DOCS_LOADED_resolve();
  document.dispatchEvent(new CustomEvent('annotate:store'));
  if (window.AA) window.AA.changed();
  loadHistory();

  // One refresh at a time. Hidden tabs make no requests; foreground resumes now.
  let refreshing = false;
  let refreshTimer;
  async function refresh() {
    clearTimeout(refreshTimer);
    if (document.hidden || refreshing || docBusy) {
      if (!document.hidden) refreshTimer = setTimeout(refresh, 8000);
      return;
    }
    refreshing = true;
    try {
      const before = JSON.stringify(STORE) + JSON.stringify(READ);
      await Promise.all([loadStore(), loadReadState(), loadCategories(), loadSessionMonitor(), loadProject()]);
      if (historyDirty) loadHistory();
      const storeChanged = JSON.stringify(STORE) + JSON.stringify(READ) !== before;
      if (storeChanged && !isEditing()) document.dispatchEvent(new CustomEvent('annotate:store'));
      const doc = VIEW_DOC;
      if (doc && DOC === doc && !docBusy) {
        await loadMeta();
        loadDelivery();
        const snap = JSON.stringify(STORE) + JSON.stringify(META) + JSON.stringify(READ);
        if (snap !== lastSnap[doc]) { if (!isEditing()) { lastSnap[doc] = snap; renderAll(); } } else updateSendState();
      }
      if (window.AA) window.AA.changed();
    } finally {
      refreshing = false;
      if (!document.hidden) refreshTimer = setTimeout(refresh, 8000);
    }
  }
  document.addEventListener('visibilitychange', () => {
    clearTimeout(refreshTimer);
    if (!document.hidden) refresh();
  });
  refreshTimer = setTimeout(refresh, 8000);
}

// What app/*.js reads and calls. Reads go through withDoc(), so a document
// that is not on screen answers from its own state.
window.AnnotateDocs = {
  docs: DOCS,
  loaded: DOCS_LOADED,
  viewDoc: () => VIEW_DOC,
  activate: activateDoc,
  park: parkDoc,
  whenFrameReady,
  version: (doc) => withDoc(doc, () => CURRENT_VERSION),
  counts: (doc) => withDoc(doc, docCounts),
  roundStats: (doc) => withDoc(doc, roundStats),
  sendables: (doc) => withDoc(doc, sendables),
  sentence: (doc) => withDoc(doc, summarySentence),
  warning: (doc) => withDoc(doc, summaryWarning),
  items: (doc) => withDoc(doc, sendItems),
  renderSummaryInto: (doc, el) => withDoc(doc, () => renderSummaryInto(el, doc === VIEW_DOC)),
  renderHistoryInto: (doc) => withDoc(doc, () => { renderVersionRail(); }),
  submitPage,
  discardPage,
  pageRoundPending,
  reload: reloadPage,
  sumEdit: (id) => { sumEditing = id; },
  setDrawerCollapsed: (c) => setDrawerCollapsed(c, false),
  setMobileSheetOpen,
  isMobileLayout,
  // The page's shared state and helpers for Library and Findings.
  categories: () => CATEGORIES,
  plans: () => PLANS,
  planId: () => PLAN_ID,
  selectPlan,
  sentRounds,
  store: () => STORE,
  comments: (includeArchived) => flattenStore(includeArchived),
  findComment: findCommentById,
  commentCategory,
  number: (id) => NUM_MAP[id],
  identity: () => IDENTITY,
  readStateOf,
  markRead,
  markReadItems,
  readRecord: (id) => READ[id] || null,
  isRoundPending,
  isReopenPending,
  needsPush,
  decisionAnswer,
  answerLabel,
  displayPrompt,
  decisionOptions,
  selectVerdictId,
  ticketsHTML,
  authorLabel,
  createComment: apiCreateComment,
  decide: apiDecision,
  refreshStore: reloadPage,
  ico,
};

document.addEventListener('DOMContentLoaded', init);
// A new private review link in the address bar starts a new session.
window.addEventListener('hashchange', () => {
  if (new URLSearchParams(location.hash.slice(1)).has('review')) location.reload();
});

})();
