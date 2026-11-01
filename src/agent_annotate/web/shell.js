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
// screen (null while Library or Findings is shown); rendering
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
let SEEN = {}; // { version: {ts, whole_hash} }
let READ = {}; // { commentId: {ts, sig} } — this viewer's per-comment read state
let NUM_MAP = {}; // { commentId: n } — canonical item number shared by rail, body and pin
let CURRENT_VERSION = null;
let AUTHOR = null;
let IDENTITY = null;
let SESSION_MONITOR = { active: false, monitor_count: 0, delivery: 'queued' };
// Page-specific read-only and sharing capabilities.
let CAPS = null;
// Feedback prototype: the chip filters, "All versions" and "Unread first" are
// replaced by collapsible sections (B2) and the History tab (B3).
// SECTION_OPEN[key] overrides the default open state of a section.
let SECTION_OPEN = {};
const SECTION_DEFAULT_OPEN = { later: false, needs: true, ready: true, waiting: true, done: false, earlier: false, archived: false };
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
  external: '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
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
document.getElementById('content-frame').addEventListener('load', () => { applyTheme(currentTheme()); applyTextSize(TEXT_SIZE); });
try { const t = localStorage.getItem('annotate:theme'); if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t); } catch {}

// ── Text size (Chang, 2026-10-10): all text in the shell and the document
// scales with --aa-text (content.css, shell.css); layout and images keep
// their size. Steps as in Google Docs' zoom menu, saved per browser.
const TEXT_SIZES = [0.9, 1, 1.1, 1.25, 1.5, 1.75, 2];
let TEXT_SIZE = (() => {
  try { const s = parseFloat(localStorage.getItem('annotate:text-size')); return TEXT_SIZES.includes(s) ? s : 1; } catch { return 1; }
})();
function applyTextSize(s) {
  document.documentElement.style.setProperty('--aa-text', String(s));
  const content = document.getElementById('content-frame');
  try { if (content && content.contentDocument) content.contentDocument.documentElement.style.setProperty('--aa-text', String(s)); } catch {}
  postToFrame({ type: 'annotate:text-size', size: s });
  document.getElementById('text-size-val').textContent = Math.round(s * 100) + '%';
  document.getElementById('text-size-down').disabled = s <= TEXT_SIZES[0];
  document.getElementById('text-size-up').disabled = s >= TEXT_SIZES[TEXT_SIZES.length - 1];
  document.getElementById('text-size-reset').disabled = s === 1;
}
function setTextSize(s) {
  TEXT_SIZE = s;
  try { if (s === 1) localStorage.removeItem('annotate:text-size'); else localStorage.setItem('annotate:text-size', String(s)); } catch {}
  applyTextSize(s);
}
function stepTextSize(dir) {
  const i = TEXT_SIZES.indexOf(TEXT_SIZE);
  setTextSize(TEXT_SIZES[Math.max(0, Math.min(TEXT_SIZES.length - 1, i + dir))]);
}
(() => {
  const btn = document.getElementById('text-size-btn');
  const panel = document.getElementById('text-size-panel');
  const setOpen = (open) => { panel.hidden = !open; btn.setAttribute('aria-expanded', open ? 'true' : 'false'); };
  btn.addEventListener('click', (e) => { e.stopPropagation(); setOpen(panel.hidden); });
  document.addEventListener('click', (e) => { if (!panel.hidden && !e.target.closest('#text-size')) setOpen(false); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !panel.hidden) { setOpen(false); btn.focus(); } });
  window.addEventListener('blur', () => setOpen(false)); // a click in the document frame
  document.getElementById('text-size-down').addEventListener('click', () => stepTextSize(-1));
  document.getElementById('text-size-up').addEventListener('click', () => stepTextSize(1));
  document.getElementById('text-size-reset').addEventListener('click', () => setTextSize(1));
  applyTextSize(TEXT_SIZE);
})();
// T11: unposted drafts survive re-renders, VERSION SWITCHES, and reloads.
// Keys: comment id for reply boxes, 'say:<id>' for a card's comment box,
// 'gf' for general feedback, 'pop' for the comment composer
// ({anchorId, anchorLabel, target, version, text}). Drafts are kept per page
// and document, since two documents can share a version name (Review v6,
// Plans v6). v9o: every keystroke is written at once (a reload, a restart or
// a closed tab right after typing kept nothing under the old 400 ms
// debounce), and a draft is cleared only when its post succeeds.
let DRAFTS = {};
function draftsKey(doc) {
  return 'annotate:drafts:' + location.pathname + ':' + (doc === 'plans' ? 'plan:' + PLAN_ID : doc);
}
function loadDrafts(doc) {
  let drafts;
  try { drafts = JSON.parse(localStorage.getItem(draftsKey(doc)) || '{}') || {}; } catch { return {}; }
  // General feedback used to be kept per version ('gf:<version>'), so a new
  // version or a reload onto the latest showed an empty box.
  const old = Object.keys(drafts).filter(k => k.indexOf('gf:') === 0 || k.indexOf('sending:') === 0);
  for (const k of old) {
    if (k.indexOf('sending:') === 0) {
      // The page closed before a post's answer: its text goes back in its
      // box unless the server has it (the store is loaded first).
      const key = k.slice(8);
      if (!sentLanded(key, drafts[k])) drafts[key] = mergeDraft(drafts[key], drafts[k]);
    } else if (!drafts.gf && drafts[k]) drafts.gf = drafts[k];
    delete drafts[k];
  }
  if (old.length) try { localStorage.setItem(draftsKey(doc), JSON.stringify(drafts)); } catch {}
  return drafts;
}
// Two tabs on one page share the key: a write changes only its own entry in
// what is stored, so one tab never erases what the other typed.
function setDraft(key, value) {
  if ((DRAFTS[key] || '') === (value || '')) return;
  if (value) DRAFTS[key] = value;
  else delete DRAFTS[key];
  try {
    const k = draftsKey(DOC);
    const stored = JSON.parse(localStorage.getItem(k) || '{}') || {};
    if (value) stored[key] = value; else delete stored[key];
    localStorage.setItem(k, JSON.stringify(stored));
  } catch {}
}

// ── Compact layout detection ─────────────────────────────────────────
// Matches shell.css exactly. The rail sits inline beside the document from
// 1024px (Atlassian's aside; below that a 440px rail would leave the
// document under ~580px); narrower, it is a right-side overlay.
function isMobileLayout() {
  return window.matchMedia('(max-width: 1023px), (max-height: 480px)').matches;
}

// In the compact layout the rail is a right-side overlay (body.is-mobile-
// sheet-open, see shell.css) and, while open, a modal dialog (APG): focus
// moves in, Tab stays inside, Escape closes, focus returns to what opened
// it. This is the single place that flips it, so the edge strip, the
// rail's own close control, and any other callers stay in sync. Open-state
// and the drawer's own scroll position (renderDrawer) both survive the 8s
// poll's re-render because neither lives inside the re-rendered DOM.
let railOpener = null;
function setMobileSheetOpen(open) {
  const was = isMobileSheetOpen();
  document.body.classList.toggle('is-mobile-sheet-open', open);
  syncRailDialog();
  if (open && !was) {
    railOpener = document.activeElement;
    requestAnimationFrame(() => syncExcerptClamps(document.getElementById('comment-list')));
    if (!document.getElementById('drawer').contains(document.activeElement)) focusRailTab();
  } else if (!open && was) {
    const back = railOpener && railOpener.isConnected && railOpener.getClientRects().length ? railOpener : document.getElementById('drawer-strip');
    railOpener = null;
    if (document.getElementById('drawer').contains(document.activeElement) || document.activeElement === document.body) back.focus({ preventScroll: true });
  }
}
function isMobileSheetOpen() {
  return document.body.classList.contains('is-mobile-sheet-open');
}
function isRailModal() {
  return isMobileLayout() && isMobileSheetOpen();
}
// Inline the rail is a complementary landmark; open as the overlay it is a
// dialog that owns the phone Send bar (it stays in reach above the rail).
function syncRailDialog() {
  const drawer = document.getElementById('drawer');
  const modal = isRailModal();
  if (modal) {
    drawer.setAttribute('role', 'dialog');
    drawer.setAttribute('aria-modal', 'true');
    drawer.setAttribute('aria-labelledby', 'drawer-title');
    drawer.setAttribute('aria-owns', 'round-bar');
    drawer.removeAttribute('aria-label');
  } else {
    drawer.setAttribute('role', 'complementary');
    drawer.setAttribute('aria-label', 'Feedback');
    ['aria-modal', 'aria-labelledby', 'aria-owns'].forEach(a => drawer.removeAttribute(a));
  }
  const shown = isMobileLayout() ? modal : !isDrawerCollapsed();
  document.querySelectorAll('#rail-strip button, #drawer-collapse').forEach(b => b.setAttribute('aria-expanded', shown ? 'true' : 'false'));
}
function focusRailTab() {
  const tab = document.querySelector('#drawer-tabs [role="tab"][aria-selected="true"]');
  if (tab) tab.focus({ preventScroll: true });
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

// Library and Findings name people the way final/ does: the reviewer's own
// records carry the reviewer's display name (as in the avatar menu), never a
// raw login; anyone else keeps their name, then their id.
function whoName(record) {
  if (!record) return 'anonymous';
  const id = String(record.author_email || record.author || record.by || '');
  const mine = IDENTITY && id && (IDENTITY.reviewer_authors || [IDENTITY.email]).includes(id);
  if (mine && IDENTITY.name) return IDENTITY.name;
  if (record.author_name && record.author_name !== id) return record.author_name;
  return authorLabel({ author: id, author_name: record.author_name });
}

// ── HTTP helpers ──────────────────────────────────────────────────
function authorQuery() {
  return AUTHOR ? ('?author=' + encodeURIComponent(AUTHOR)) : '';
}

// ── Polled reads (v9o) ──────────────────────────────────────────────
// Every read the 8 s poll repeats asks with the last answer's ETag, so an
// unchanged answer is a 304 with no body; without an ETag an identical body
// counts as unchanged too. `same` answers keep what the page already has and
// cost no parsing or rendering; `pollChanged` records whether any read in a
// poll brought something new (`quiet` reads handle their own changes).
const pollLast = {};
let pollChanged = false;
// Posts not answered yet, each with how to put it on a fresh store (see
// "Optimistic posts").
const pendingEdits = new Map();
async function pollJson(url, quiet) {
  const last = pollLast[url];
  const r = await fetch(apiUrl(url), { cache: 'no-store', headers: last && last.etag ? { 'If-None-Match': last.etag } : {}, signal: AbortSignal.timeout(10000) });
  // Read the empty 304 body: an unread one ends as an aborted request.
  if (r.status === 304 && last) { await r.text(); return { ok: true, same: true, data: last.data }; }
  if (!r.ok) return { ok: false, status: r.status };
  const text = await r.text();
  const etag = r.headers.get('ETag');
  if (last && last.text != null && text === last.text) { last.etag = etag; return { ok: true, same: true, data: last.data }; }
  const data = JSON.parse(text);
  // The body is kept for comparing only when the server sends no ETag (the
  // FLD store's text is megabytes held twice otherwise).
  pollLast[url] = { etag, text: etag ? null : text, data };
  if (!quiet) pollChanged = true;
  return { ok: true, same: false, data };
}

// The page's one comment store, shared by every document and tab.
// `view=poll` (servers from v9o on) leaves out each comment's carry_history, which
// nothing in the browser shows (megabytes on long-lived pages); an older
// server ignores the query and sends the whole store, which works the same.
async function loadStore() {
  try {
    const got = await pollJson('./comments.json?view=poll');
    if (!got.ok) return false;
    if (got.same) return true;
    const store = got.data;
    STORE = store && store.schema_version === 2 ? store : { schema_version: 2, anchors: {}, archived: {} };
    // Posts still on their way stay on screen (v9o).
    for (const apply of pendingEdits.values()) apply();
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
    const got = await pollJson(url);
    if (!got.ok) return false;
    if (doc !== DOC) return false;
    if (got.same && (META.current || (META.history || []).length)) return true;
    const meta = got.data;
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
    const got = await pollJson('./api/read-state' + authorQuery());
    if (!got.ok) return false;
    if (!got.same) READ = got.data.read || {};
    return true;
  } catch { return false; }
}

// Optimistic: READ is updated locally before the POST so the UI decrements
// instantly; the server merge is idempotent.
function markRead(comments) {
  const items = [];
  const now = new Date().toISOString();
  for (const c of comments) {
    if (!c || !c.id || c.pending) continue;
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

// A copy of the one match only: copying the whole store per call made each
// rail render O(n²) on long pages (1,418 comments on FLD).
// While one render runs, lookups use an id index built once for it.
let ID_INDEX = null;
function withIdIndex(fn) {
  if (ID_INDEX) return fn();
  ID_INDEX = new Map();
  for (const area of [STORE.anchors, STORE.archived]) {
    for (const [aid, items] of Object.entries(area || {})) for (const c of items) if (!ID_INDEX.has(c.id)) ID_INDEX.set(c.id, [c, aid]);
  }
  try { return fn(); } finally { ID_INDEX = null; }
}
function findCommentById(id) {
  if (ID_INDEX) {
    const hit = ID_INDEX.get(id);
    return hit ? Object.assign({}, hit[0], { anchor_id: hit[1] }) : null;
  }
  for (const area of [STORE.anchors, STORE.archived]) {
    for (const [aid, items] of Object.entries(area || {})) {
      for (const c of items) if (c.id === id) return Object.assign({}, c, { anchor_id: aid });
    }
  }
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

async function apiDelete(id) {
  try {
    const r = await fetch(apiUrl('./api/comments/' + encodeURIComponent(id) + authorQuery()), { method: 'DELETE' });
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

// `win`: the window of the document the card is in, which sends it (a card in
// the document posts from the document, as it always has).
async function apiDecision(id, verdict, text, optionId, win = window) {
  try {
    const r = await win.fetch(apiUrl('./api/comments/' + encodeURIComponent(id) + '/decision' + authorQuery()), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        verdict,
        text: text || undefined,
        option_id: optionId,
        evidence: document.getElementById('content-frame')?.contentWindow?.__ANNOTATE_CONTENT_META__?.evidence?.[id],
        author: AUTHOR,
        author_name: IDENTITY && IDENTITY.name,
        author_email: IDENTITY && IDENTITY.email,
        defer_push: true,
      }),
    });
    if (r.ok) return await r.json();
  } catch {}
  return null;
}

// ── Page capabilities + review rounds ───────────────────────────────
async function loadCapabilities() {
  CAPS = null;
  try {
    const r = await fetch(apiUrl('./api/capabilities'), { cache: 'no-store' });
    if (r.ok) {
      const j = await r.json();
      if (j && typeof j === 'object') CAPS = j;
    }
  } catch {}
  document.body.classList.toggle('page-read-only', !!(CAPS && CAPS.read_only));
  return CAPS;
}
function pageReadOnly() { return !!(CAPS && CAPS.read_only); }
function canonicalOptionId(id) {
  return (id === 'comment' || id === 'changes') ? 'changes' : id;
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

async function apiPushAll(send) {
  try {
    const r = await fetch(apiUrl('./api/push-session'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(send || {}) });
    if (r.ok) return await r.json();
  } catch {}
  return null;
}

async function loadSessionMonitor() {
  try {
    const got = await pollJson('./api/session-monitor');
    if (got.ok && !got.same) SESSION_MONITOR = got.data;
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
  return flattenStore(includeArchived).filter(c => docOf(c) === DOC && (!c.withdrawn || strandedSay(c)));
}

function withdrawnQuestions() {
  return flattenStore(true).filter(c => c.withdrawn).map(c => ({
    cat: commentCategory(c), number: NUM_MAP[c.id], version: c.version,
    prompt: c.withdrawn.decision_request.prompt, reason: c.withdrawn.reason,
  }));
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
    return `<li><a href="${escAttr(url.href)}" target="_blank" rel="noopener noreferrer">${esc(item.label)}${ico('external')}</a>${item.description ? `<span class="project-detail">${ticketsHTML(item.description)}</span>` : ''}${item.declared ? `<span class="project-detail">${esc(item.declared)}</span>` : ''}</li>`;
  }).join('');
}
// PROJECT.tabs of kind reference (F5) are listed with the project's links.
function referenceTabs() {
  return (PROJECT.tabs || []).filter(t => t && t.url && (!t.kind || t.kind === 'reference'));
}
// k5y (Chang: "let's make sure that we are referencing things by the same name
// consistently"): the project's other pages are listed once, here, each by its
// own name: the reference tabs in their order, then the declared exceptions
// with their reason. A reference that is not a registered page keeps its label.
function projectPages() {
  const related = PROJECT.related_pages || [];
  const page = (p) => ({ label: p.name, url: p.url, description: p.reason,
    declared: p.declared_by ? `Declared by ${p.declared_by} to ${p.told_to || 'the orchestrator'}${p.declared_at ? ' · ' + fmtTs(p.declared_at) : ''}` : '' });
  const items = referenceTabs().map(t => {
    const p = t.slug && related.find(r => r.slug === t.slug);
    return p ? page(p) : { label: t.name || t.label, url: t.url };
  });
  const listed = new Set(referenceTabs().map(t => t.slug));
  return items.concat(related.filter(p => !listed.has(p.slug)).map(page));
}
// Long pages: this page first, then its archive pages newest first, each with its size.
function archivePagesHtml(archives) {
  if (!archives.length) return '';
  const size = (n, shots) => `${n} section${n === 1 ? '' : 's'}${shots ? ` · ${shots} screenshot${shots === 1 ? '' : 's'}` : ''}`;
  const latest = (META.history || []).find(h => h.version === latestVersion()) || {};
  const here = `<li><a href="#view=review"><strong>${esc(PROJECT.title || PROJECT.name || 'This page')}</strong> <span class="badge badge-primary badge-sm">this page</span></a>`
    + (latest.sections != null ? `<span class="project-detail">Now · ${esc(size(latest.sections, latest.screenshots))}</span>` : '') + '</li>';
  const sorted = archives.slice().sort((a, b) => String(b.id).localeCompare(String(a.id), undefined, { numeric: true }));
  const items = sorted.map(p => {
    const a = p.archive || {};
    return `<li><a href="#view=plans&plan=${encodeURIComponent(p.id)}">${esc(p.title || p.id)}</a>`
      + (a.sections != null ? `<span class="project-detail">Finished · ${esc(size(a.sections, a.screenshots))}</span>` : '') + '</li>';
  }).join('');
  return `<section class="hist-section"><h3 class="hist-lbl">This project's pages</h3><ul class="doc-list">${here}${items}</ul></section>`;
}
// U-01 + F2: project branding wins, then the page's stable name.
function updateProjectTitle() {
  const title = PROJECT.title || PROJECT.name || 'annotate';
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
  const pages = DOC === 'review' ? projectPages() : [];
  if (pages.length) links.unshift({ id: 'project-pages', title: 'Project pages', items: pages });
  const archives = DOC === 'review' ? PLANS.filter(isArchivePlan) : [];
  // Documents tab
  const docTab = document.getElementById('tab-documents');
  const docBody = document.getElementById('documents-body');
  if (DOC !== VIEW_DOC) {
    // Only the document on screen fills the Documents tab.
  } else if (links.length || archives.length) {
    docTab.hidden = false;
    docTab.textContent = links.length === 1 && !pages.length && !archives.length ? links[0].title : 'Documents';
    docBody.innerHTML = archivePagesHtml(archives) + links.map(m => `<section class="hist-section">${links.length > 1 || archives.length ? `<h3 class="hist-lbl">${esc(m.title)}</h3>` : ''}<ul class="doc-list">${projectLinkItems(m)}</ul></section>`).join('');
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
    const got = await pollJson('./api/project');
    if (!got.ok || got.same) return;
    const data = got.data;
    if (doc !== DOC) return;
    const snapshot = JSON.stringify(data);
    if (snapshot !== projectSnapshot) { PROJECT = data; projectSnapshot = snapshot; renderProject(); }
  } catch {}
}
// The board's ready count (./api/board) for the header link. The server answers
// from its cache, so this never holds up the page; it is not awaited.
let BOARD_READY = null;
let boardFirstTries = 0;
async function loadBoard() {
  if (!PROJECT.board) { BOARD_READY = null; return; }
  try {
    // Its check time moves every minute; only the ready count matters.
    const got = await pollJson('./api/board', true);
    if (!got.ok) return;
    const data = got.data;
    // The server's first count is still running: ask again soon, a few times.
    if (!data.checked_at && boardFirstTries < 8) { boardFirstTries++; setTimeout(loadBoard, 1500); }
    const ready = typeof data.ready === 'number' ? data.ready : null;
    if (ready !== BOARD_READY) { BOARD_READY = ready; if (window.AA) window.AA.changed(); }
  } catch {}
}
function boardLink() {
  const b = PROJECT.board, url = b && safeHttpUrl(b.url);
  return url ? { url, label: b.label || 'Board', project: b.project, ready: BOARD_READY } : null;
}
// F17 + U-07: History lists the rounds the server recorded, newest first,
// each with its answers; the header keeps the latest one beside Send.
let HISTORY_DATA = null;
let historyDirty = true;
let historyLoading = false;
// The header and Send read only the latest round; the full list loads once History is opened.
let historyFull = false;
async function loadHistory() {
  if ((HISTORY_DATA && !historyDirty) || historyLoading) return;
  historyLoading = true;
  const full = historyFull;
  try {
    const r = await fetch(apiUrl('./api/history' + (full ? '' : '?latest=1')), { cache: 'no-store', signal: AbortSignal.timeout(10000) });
    const data = await r.json();
    if (!r.ok || !Array.isArray(data.rounds)) throw new Error('history');
    HISTORY_DATA = data;
    historyDirty = full !== historyFull;
    if (window.AA) window.AA.changed();
  } catch { /* History keeps the last rounds it had */ } finally {
    historyLoading = false;
    if (full !== historyFull) loadHistory();
  }
}
function wantFullHistory() {
  if (historyFull) return;
  historyFull = true;
  historyDirty = true;
  loadHistory();
}
function roundItemText(answer) {
  const c = answer.comment_id ? findCommentById(answer.comment_id) : null;
  const n = (c && NUM_MAP[c.id]) || answer.number;
  // P5: the prompt the round recorded, even after the card's prompt changed.
  const prompt = answer.prompt ? displayPrompt({ id: answer.comment_id, decision_request: { prompt: answer.prompt } })
    : c ? displayPrompt(c) || firstLine(c.text) : '';
  const ans = answer.text ? (answer.verdict === 'select' ? answer.text.replace(/^Selected:\s*/, '') : answer.text)
    : (DECISION_VERDICT_LABEL[answer.verdict] || answer.verdict || '');
  // A plain comment is its own label; never repeat it as the answer.
  const same = ans && firstLine(ans) === prompt;
  return (n ? '#' + n + ' · ' : '') + prompt + (ans && !same ? ' → ' + firstLine(ans) : '');
}
// The rounds the server recorded, newest first, each line tagged with its
// tab (History nests each under the version it was sent on).
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
  // UI-2: the round and the push each keep the lines they carried; one Send's
  // receipt is both, in the summary's tab order.
  const tabOrder = ['review', 'library', 'findings', 'plans'];
  return groups.map(g => {
    const withReceipt = g.filter(r => Array.isArray(r.receipt) && r.receipt.length)
      .sort((a, b) => (a.ts < b.ts ? -1 : a.ts > b.ts ? 1 : 0));
    const ts = g.map(r => r.ts).sort()[0];
    // The page version the Send was made on (pushes may not record one).
    const version = (g.find(r => typeof r.version === 'string' && r.version) || {}).version || '';
    if (withReceipt.length) {
      const items = [].concat(...withReceipt.map(r => r.receipt)).map(it => ({ cat: it.cat, label: it.label, answer: it.answer || '', doc: it.doc }))
        .map((it, i) => [it, i]).sort((a, b) => (tabOrder.indexOf(a[0].cat) - tabOrder.indexOf(b[0].cat)) || (a[1] - b[1])).map(x => x[0]);
      return { ts, version, result: roundResult(items.length, g.map(r => r.id)), delivery_ids: g.map(r => r.id), items, send_id: withReceipt[0].send_id };
    }
    const legacy = legacyRound(g.find(r => r.kind !== 'push') || g[0]);
    return Object.assign(legacy, { version, result: roundResult(legacy.n, g.map(r => r.id)), delivery_ids: g.map(r => r.id) });
  }).filter(r => r.items.length);
}
// Only a matching owner receipt proves delivery, including after reload.
function deliveryLabel(id) {
  if (Array.isArray(id)) return id.length && id.every(value => deliveryLabel(value) === 'Sent') ? 'Sent' : 'In inbox · owner delivery pending';
  const data = SUMMARY_DELIVERY || {};
  const receipt = (data.deliveries || []).find(r => r.id === id) || (data.latest?.id === id ? data.latest : null);
  return receipt?.delivered ? 'Sent' : 'In inbox · owner delivery pending';
}
function deliveryHtml(id) {
  const ids = Array.isArray(id) ? id : [id];
  return `<span data-delivery-ids="${escAttr(ids.filter(Boolean).join(','))}">${esc(deliveryLabel(id))}</span>`;
}
function roundResult(n, ids) {
  return (ids?.length && ids.every(id => deliveryLabel(id) === 'Sent') ? 'Sent' : 'In inbox · owner delivery pending') + ' (' + n + ')';
}
function legacyRound(r) {
  {
    const items = (r.answers || []).map(a => {
      const c = a.comment_id ? findCommentById(a.comment_id) : null;
      const cat = a.category || (c ? commentCategory(c) : 'review');
      const text = roundItemText(a);
      const at = text.indexOf(' → ');
      return { cat, label: at === -1 ? text : text.slice(0, at), answer: at === -1 ? '' : text.slice(at + 3), doc: c ? c.doc : undefined };
    });
    (r.edits || []).forEach(e => items.push({ cat: 'library', label: e.label || e.block_id, answer: 'Edited', block: e.block_id }));
    if (r.note) items.push({ cat: 'review', label: 'General feedback', answer: r.note });
    const n = (r.answers || []).length + (r.edits || []).length;
    return { ts: r.ts, result: roundResult(n, [r.id]), items, n };
  }
}
async function loadDelivery() {
  const node = document.getElementById('delivery-status');
  try {
    let data = SUMMARY_DELIVERY;
    if (!HAS_SUMMARY || DOC !== VIEW_DOC || DOC !== 'review' || docBusy) {
      const got = await pollJson('./api/delivery');
      if (!got.ok || got.same) return;
      data = got.data;
    }
    data = data || {};
    SUMMARY_DELIVERY = data;
    node.hidden = !data.latest;
    if (data.latest) {
      const labels = {acknowledged: 'Owner read this feedback round; project work is tracked separately', pending: 'Submitted; owner delivery pending — waiting in the inbox', accepted: 'Submitted; owner delivery unconfirmed — waiting in the inbox', started: 'Owner turn started; agent response pending', uncertain: 'Submitted; owner delivery unconfirmed — waiting in the inbox', superseded: 'Page owner changed before this round was delivered'};
      node.textContent = ((data.latest.delivered && data.latest.state === 'accepted' ? 'Sent to owner session; agent response pending' : labels[data.latest.state]) || 'Feedback delivery: ' + data.latest.state) + (data.latest.detail && ['pending', 'uncertain'].includes(data.latest.state) ? '. ' + data.latest.detail : '');
    }
    window.AA?.send?.delivery(data.deliveries || []);
    for (const root of [document, document.getElementById('content-frame')?.contentDocument]) {
      root?.querySelectorAll('[data-delivery-ids]').forEach(label => {
        const text = deliveryLabel(label.dataset.deliveryIds.split(',').filter(Boolean));
        if (label.textContent !== text) label.textContent = text;
      });
    }
  } catch {}
}

// ── Version rail ─────────────────────────────────────────────────
// final/: each document's versions sit in its own History section
// (#vrail-body-<doc>); a version of a document that is not on screen opens
// that document's tab at that version.
// yvj: one list. Each version's chevron opens what was sent on it and what
// the agent did in response; the separate Sent rounds list is gone.
let HISTORY_SHOWN = null; // the tabs History shows (app/rail.js); null = every tab
// The versions in publish order: a republish updates its version's time in
// place, so the list's own order is not the order they went live.
function historyByTime() {
  const t = (h) => Date.parse(h.ts) || 0;
  return (META.history || []).slice().sort((a, b) => t(a) - t(b));
}
function versionAt(ts) {
  const t = Date.parse(ts) || 0;
  const hs = historyByTime();
  let at = null;
  for (const h of hs) if ((Date.parse(h.ts) || 0) <= t) at = h.version;
  return at || (hs[0] || {}).version || null;
}
// What the agent published next: the first other version to go live after
// the last round sent on this one (or after this one, with no rounds).
function publishedAfter(h, rounds) {
  const t = Math.max(Date.parse(h.ts) || 0, ...rounds.map(r => Date.parse(r.ts) || 0));
  return historyByTime().find(x => x.version !== h.version && (Date.parse(x.ts) || 0) > t) || null;
}
// The rounds sent on each version of this document, oldest first. Review
// rounds name their version; others (and older records) go under the
// version on screen at their time. Review also carries Library and Findings
// lines, which have no versions of their own.
function roundsByVersion(shown) {
  const known = new Set((META.history || []).map(h => h.version));
  const rounds = window.AA && window.AA.send ? window.AA.send.receipts() : sentRounds();
  const out = {};
  for (const r of rounds) {
    const items = r.items.filter(it => (!shown || shown.includes(it.cat)) &&
      ((it.cat === DOC && (DOC !== 'plans' || !it.doc || it.doc === 'plan:' + PLAN_ID)) ||
        (DOC === 'review' && !(window.AA && window.AA.isDoc(it.cat)))));
    if (!items.length) continue;
    const v = DOC === 'review' && known.has(r.version) ? r.version : versionAt(r.ts);
    if (v) (out[v] = out[v] || []).unshift(Object.assign({}, r, { items }));
  }
  return out;
}
// What the agent did on a version's comments: resolved or addressed them.
function versionFolds(value) {
  const key = 'annotate:vfold:' + location.pathname + ':' + (DOC === 'plans' ? 'plan:' + PLAN_ID : DOC);
  try {
    if (value !== undefined) localStorage.setItem(key, JSON.stringify(value));
    return JSON.parse(localStorage.getItem(key) || '{}') || {};
  } catch { return {}; }
}
function versionActivityHtml(h, next, rounds, done) {
  const tag = (cat) => cat !== DOC && window.AA && window.AA.rail ? window.AA.rail.tagHtml(cat) + ' ' : '';
  const sent = rounds.map(r => `<div class="vact-block">
      <div class="vact-head">Feedback · ${r.delivery_ids ? deliveryHtml(r.delivery_ids) + ' (' + (r.n ?? r.items.length) + ')' : esc(r.result)} · ${esc(fmtTs(r.ts))}</div>
      <ul>${r.items.map(it => `<li>${tag(it.cat)}${esc(it.label)}${it.answer ? ' → ' + esc(it.answer) : ''}</li>`).join('')}</ul>
    </div>`).join('');
  const lines = done.map(c => {
    const n = NUM_MAP[c.id];
    const what = c.status === 'resolved_in_version' ? 'Resolved in ' + (c.resolved_in_version || 'a later version') : 'Addressed';
    return `<li>${n ? '#' + n + ' · ' : ''}${esc(displayPrompt(c) || firstLine(c.text))} — ${esc(what)}</li>`;
  }).join('');
  const agent = next || lines ? `<div class="vact-block vact-agent">
      <div class="vact-head">Agent${next ? ' · Published ' + esc(next.version) + (next.label ? ' · ' + esc(next.label) : '') + ' · ' + esc(fmtTs(next.ts)) : ''}</div>
      ${lines ? `<ul>${lines}</ul>` : ''}
    </div>` : '';
  return sent + agent;
}
// Long pages: History lists the latest 20 versions; Show 20 earlier adds more.
const HISTORY_PAGE = 20;
const historyLimit = {};
function renderVersionRail(shown) {
  const body = document.getElementById('vrail-body-' + DOC);
  if (!body) return;
  if (shown !== undefined) HISTORY_SHOWN = shown;
  // Built when History is opened, never while it is hidden.
  if (body.closest('[hidden]')) { if (DOC === VIEW_DOC) renderVersionBanner(); return; }
  wantFullHistory();
  const doc = DOC;
  const focused = document.activeElement && document.activeElement.closest && document.activeElement.closest('#vrail-body-' + doc + ' .vitem');
  const focusedVersion = focused ? focused.dataset.version : null;
  const focusedToggle = focused && document.activeElement.classList.contains('vrow-toggle');
  // The keyboard hint belongs to the document on screen only, as in final/.
  const hint = body.parentNode.querySelector('.unified-history-hint');
  if (hint) hint.hidden = doc !== VIEW_DOC;
  const byVersion = roundsByVersion(HISTORY_SHOWN);
  // Library or Findings alone: only the versions their lines were sent on.
  const sentOnly = !!HISTORY_SHOWN && !HISTORY_SHOWN.includes(doc);
  const allHistory = (META.history || []).slice().reverse().filter(h => !sentOnly || byVersion[h.version]);
  // The version on screen is always listed, however far back.
  const limit = Math.max(historyLimit[doc] || HISTORY_PAGE, allHistory.findIndex(h => h.version === CURRENT_VERSION) + 1);
  const history = allHistory.slice(0, limit);
  if (!history.length) {
    body.innerHTML = '<div class="vrail-empty">No versions found</div>';
    return 0;
  }
  const folds = versionFolds();
  // One pass over the comments for every version: per-version scans made
  // History freeze for 2.2 s on FLD (535 versions × 1,418 comments).
  const doneBy = {}, countsBy = {};
  for (const c of flattenAll(true)) {
    if (c.status === 'resolved_in_version' || c.status === 'addressed_by_agent') (doneBy[c.version] = doneBy[c.version] || []).push(c);
  }
  for (const c of flattenAll(false)) {
    const v = followsViewer(c) ? CURRENT_VERSION : c.version;
    const k = countsBy[v] = countsBy[v] || { review: 0, waiting: 0, done: 0, total: 0 };
    const cls = classify(c);
    k[cls === 'review' ? 'review' : cls === 'waiting' ? 'waiting' : 'done']++;
    k.total++;
  }
  body.innerHTML = history.map(h => {
    const rounds = byVersion[h.version] || [];
    const done = sentOnly ? [] : (doneBy[h.version] || []);
    const activity = rounds.length || done.length;
    const next = activity ? publishedAfter(h, rounds) : null;
    const open = !!activity && (h.version in folds ? folds[h.version] : sentOnly || h.version === CURRENT_VERSION);
    const pid = 'vact-' + doc + '-' + h.version;
    const counts = countsBy[h.version] || { review: 0, waiting: 0, done: 0, total: 0 };
    const isCur = h.version === CURRENT_VERSION;
    const isNew = !neverVisited(h.version) && hasNewContent(h.version);
    let dotHtml = '<span class="vrow-dot"></span>';
    if (counts.waiting > 0 && counts.review === 0) dotHtml = '<span class="vrow-dot-hollow" title="Your comments awaiting agent"></span>';
    const badgeHtml = counts.review > 0
      ? `<span class="badge badge-error badge-xs vrow-badge">${counts.review}</span>`
      : '';
    const newHtml = isNew ? '<span class="vrow-new" title="Content updated since your last visit">↑NEW</span>' : '';
    const toggleHtml = activity
      ? `<button type="button" class="btn btn-ghost btn-xs btn-square vrow-toggle" aria-expanded="${open}" aria-controls="${escAttr(pid)}" aria-label="What was sent and done on ${escAttr(h.version)}" title="What was sent and done on ${escAttr(h.version)}">${ico('chevRight')}</button>`
      : '';
    return `<div class="vitem" role="listitem" data-version="${escAttr(h.version)}">
      <div class="vitem-row">
        <button type="button" aria-current="${isCur ? 'page' : 'false'}" class="vrow ${isCur ? 'current' : ''}" data-version="${escAttr(h.version)}" title="${escAttr(h.label || '')}">
          ${dotHtml}
          <span class="vrow-label">${esc(h.version)}${h.label ? ' &middot; ' + esc(h.label) : ''}</span>
          ${newHtml}
          ${badgeHtml}
        </button>
        ${toggleHtml}
      </div>
      ${activity ? `<div class="vact" id="${escAttr(pid)}"${open ? '' : ' hidden'}>${versionActivityHtml(h, next, rounds, done)}</div>` : ''}
    </div>`;
  }).join('') + (allHistory.length > limit
    ? `<button type="button" class="btn btn-ghost btn-xs vrail-more">Show ${Math.min(HISTORY_PAGE, allHistory.length - limit)} earlier</button>` : '');
  const more = body.querySelector('.vrail-more');
  if (more) more.addEventListener('click', () => {
    historyLimit[doc] = limit + HISTORY_PAGE;
    withDoc(doc, () => renderVersionRail());
    const rows = body.querySelectorAll('.vrow');
    if (rows[limit]) rows[limit].focus();
  });
  Array.from(body.querySelectorAll('.vrow')).forEach(row => {
    row.addEventListener('click', () => {
      if (doc !== VIEW_DOC) { if (window.AA) window.AA.go({ view: doc, v: row.dataset.version }); return; }
      switchVersion(row.dataset.version);
      // Phone: the sheet covers the document; show the version just picked.
      if (isMobileLayout()) setMobileSheetOpen(false);
    });
  });
  Array.from(body.querySelectorAll('.vrow-toggle')).forEach(btn => {
    btn.addEventListener('click', () => {
      const open = btn.getAttribute('aria-expanded') !== 'true';
      btn.setAttribute('aria-expanded', String(open));
      document.getElementById(btn.getAttribute('aria-controls')).hidden = !open;
      withDoc(doc, () => versionFolds(Object.assign(versionFolds(), { [btn.closest('.vitem').dataset.version]: open })));
    });
  });
  // U-14: Up/Down/Home/End move between the versions; one version (and its
  // chevron) is in the Tab order, not every chevron in the list.
  const rows = [...body.querySelectorAll('.vrow')];
  const rove = (to) => rows.forEach(x => {
    x.tabIndex = x === to ? 0 : -1;
    const toggle = x.parentNode.querySelector('.vrow-toggle');
    if (toggle) toggle.tabIndex = x.tabIndex;
  });
  rove(rows.find(r => r.dataset.version === CURRENT_VERSION) || rows[0]);
  rows.forEach(r => {
    r.addEventListener('keydown', e => {
      let n = rows.indexOf(r);
      if (e.key === 'ArrowDown') n++;
      else if (e.key === 'ArrowUp') n--;
      else if (e.key === 'Home') n = 0;
      else if (e.key === 'End') n = rows.length - 1;
      else return;
      e.preventDefault();
      const next = rows[Math.max(0, Math.min(rows.length - 1, n))];
      rove(next);
      next.focus();
    });
  });
  const restore = focusedVersion && !document.getElementById('history-body').hidden && (!isMobileLayout() || isMobileSheetOpen()) && rows.find(r => r.dataset.version === focusedVersion);
  if (restore) {
    rove(restore);
    const toggle = focusedToggle && restore.parentNode.querySelector('.vrow-toggle');
    (toggle || restore).focus();
  }
  if (doc === VIEW_DOC) renderVersionBanner();
  return rows.length;
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
  // v9o: one general-feedback draft per document; it goes with the version
  // on screen at Send.
  const gf = document.getElementById('gf-ta');
  if (gf) gf.value = DRAFTS.gf || '';
  renderGeneralFeedback();
  updateSendState();
}

function loadIframe(v) {
  ANCHOR_ORDER = {};
  const frame = document.getElementById('content-frame');
  frame.dataset.doc = DOC;
  frame.dataset.version = v;
  const doc = DOC;
  frame.onload = () => {
    if (doc !== 'review') return;
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
// Escaped text with issue ids as links: ids the agent listed in
// PROJECT.issue_links (any tracker), and ids on the project's board
// (PROJECT.board, e.g. agent-annotate-w6e.4), which open that issue there.
const ISSUE_ID_RE = /(?<![A-Za-z0-9_.-])[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+(?:\.[0-9]+)*(?![A-Za-z0-9_-])/g;
function boardIssueUrl(id) {
  const b = PROJECT.board;
  if (!b || !b.prefix || id.indexOf(b.prefix + '-') !== 0 || !/^[a-z0-9]+(?:\.[0-9]+)*$/.test(id.slice(b.prefix.length + 1))) return '';
  const url = safeHttpUrl(b.url);
  return url ? url + (url.indexOf('?') === -1 ? '?' : '&') + 'bead=' + encodeURIComponent(id) : '';
}
function issueUrl(id) {
  const links = PROJECT.issue_links || {};
  const raw = Object.prototype.hasOwnProperty.call(links, id) ? links[id] : null;
  return (typeof raw === 'string' && !/[\\\u0000- \u007f]/.test(raw) && safeHttpUrl(raw)) || boardIssueUrl(id);
}
function ticketsHTML(value) {
  const text = String(value == null ? '' : value);
  let html = '', offset = 0;
  for (const match of text.matchAll(ISSUE_ID_RE)) {
    const id = match[0];
    const url = issueUrl(id);
    if (!url) continue;
    html += esc(text.slice(offset, match.index)) +
      `<a class="ticket-link" href="${escAttr(url)}" target="_blank" rel="noopener noreferrer" title="Open ${escAttr(id)}">${esc(id)}</a>`;
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
// The IMG id of the image a comment was placed on (adapter.js viewerComment).
function imageTag(target) {
  const id = target && target.image;
  return typeof id === 'string' && /^[0-9A-F]{4,64}$/.test(id) ? 'IMG ' + id : '';
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
// Answer later: the server remembers it (comments.json); answering clears it.
function isSetAside(c) {
  return !!(c && c.answer_later) && isUnresolvedDecision(c);
}
async function setAnswerLater(id, on) {
  if (!storedComment(id)) return;
  const was = storedComment(id).answer_later;
  const key = 'later:' + id;
  addPendingEdit(key, () => { const c = storedComment(id); if (c) c.answer_later = on ? { ts: new Date().toISOString() } : undefined; });
  renderAll();
  let ok = false;
  await settlePending((async () => {
    try {
      const r = await fetch(apiUrl('./api/comments/' + encodeURIComponent(id) + '/answer-later' + authorQuery()), {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ on: !!on }) });
      ok = r.ok;
    } catch {}
  })());
  pendingEdits.delete(key);
  if (!ok) {
    const c = storedComment(id);
    if (c) c.answer_later = was;
    setSendNote(on ? 'Could not set this question aside. Try again.' : 'Could not move this question back. Try again.', 'is-error', 4000);
  }
  refreshStore();
}
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
const SECTION_ORDER = ['later', 'needs', 'ready', 'waiting', 'done', 'earlier', 'archived'];
const SECTION_LABEL = { later: 'Answer later', needs: 'Needs you', ready: 'Ready to send', waiting: 'Waiting on agent', done: 'Done', earlier: 'Earlier feedback', archived: 'Archived' };
function sectionOpen(k) {
  return Object.prototype.hasOwnProperty.call(SECTION_OPEN, k) ? !!SECTION_OPEN[k] : !!SECTION_DEFAULT_OPEN[k];
}
function setSectionOpen(k, open) {
  SECTION_OPEN[k] = !!open;
  try { localStorage.setItem('annotate:sections', JSON.stringify(SECTION_OPEN)); } catch {}
}
// A reviewer's own comment or reply that has not gone to the agent yet.
function userNeedsSend(c) {
  return needsPush(c);
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
  mirrorSay(id);
}
// P1: text typed while an answered card's Change is open (on the card or in
// the Send summary) is that card's new answer at Send, as on an open card.
function hasSayDraft(c) {
  return isUnresolvedDecision(c) && sayIsNew(c);
}
// Change opens with the saved words in the box; only different text is new.
function sayIsNew(c) {
  const d = decisionAnswer(c);
  return !!sayDraft(c) && sayDraft(c) !== String((d && d.text) || '').trim();
}
// Text typed on a question the agent then answered, withdrew or replaced.
// The card keeps showing it, and Send posts it as a reply (Chang lost these
// as the orchestrator loaded new cards, 2026-10-30).
function strandedSay(c) {
  return sayIsNew(c) && !hasSayDraft(c) && c.status !== 'archived';
}
function strandedSayHtml(c) {
  return `<div class="decision-stranded">
    <div class="decision-feedback">This card changed while you were typing. Your text is kept and goes as a reply when you send.</div>
    <textarea class="textarea textarea-sm decision-say-ta" data-decision-say-ta="${escAttr(c.id)}" rows="2" aria-label="Your reply on #${NUM_MAP[c.id] || ''}"></textarea>
  </div>`;
}
// A reply or comment typed on the card and not sent yet.
function hasUnsentText(c) {
  return !!((DRAFTS[c.id] || '').trim() || (DRAFTS['say:' + c.id] || '').trim());
}
function isChangingAnswer(c) {
  return !!(c && (decisionChanging[c.id] || sumEditing === c.id) && canChangeAnswer(c));
}
function sectionOf(c) {
  if (pageReadOnly()) return 'archived';
  if (c.status === 'archived') return 'archived';
  if (isRoundPending(c) || userNeedsSend(c) || strandedSay(c)) return 'ready';
  if (isSetAside(c)) return 'later';
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
    if (hasSayDraft(c)) answers.push(c);
    else if (isRoundPending(c)) round.push(c);
    else if (needsPush(c) || strandedSay(c)) push.push(c);
  }
  return { round, answers, push };
}
function sendables() {
  if (pageReadOnly()) return { verdicts: 0, answers: 0, comments: 0, gf: false, total: 0 };
  const p = sendPlan();
  const gf = !!gfDraft();
  return { verdicts: p.round.length, answers: p.answers.length, comments: p.push.length, gf,
    total: p.round.length + p.answers.length + p.push.length + (gf ? 1 : 0) };
}
function gfDraft() {
  return CURRENT_VERSION ? (DRAFTS.gf || '').trim() : '';
}

// final/: one count model for the whole page. docCounts() is what the
// header tabs, the phone menu and the rail badges read for a document.
function docCounts() {
  if (pageReadOnly()) return { needs: 0, unread: 0, waiting: 0, total: 0, pending: 0 };
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
  if (window.AA) window.AA.changed();
}

function renderDrawer() { return withIdIndex(renderDrawerNow); }
function renderDrawerNow() {
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
  listEl.querySelectorAll('.note-edit-ta').forEach(ta => {
    const k = ta.dataset.noteEdit + '|' + ta.dataset.key;
    if (!editingNote[k]) return;
    setDraft('note:' + k, ta.value || '');
    if (ta === document.activeElement) focusedTa = '[data-note-edit="' + cssEsc(ta.dataset.noteEdit) + '"][data-key="' + cssEsc(ta.dataset.key) + '"]';
  });
  for (const k of Object.keys(DRAFTS)) if (k.startsWith('note:') && DRAFTS[k]) editingNote[k.slice(5)] = true;
  listEl.querySelectorAll('.edit-ta').forEach(ta => {
    if (!editingComment[ta.dataset.editFor]) return; // just saved or cancelled
    setDraft('edit:' + ta.dataset.editFor, ta.value || '');
    if (ta === document.activeElement) focusedTa = '[data-edit-for="' + cssEsc(ta.dataset.editFor) + '"]';
  });
  // An edit left open survives a reload: its draft reopens the editor.
  for (const k of Object.keys(DRAFTS)) if (k.startsWith('edit:') && DRAFTS[k]) editingComment[k.slice(5)] = true;

  // v9o: a card holding unsent text stays open with its box, even after the
  // agent answered or resolved it meanwhile (its section opens too).
  for (const c of flattenAll(false)) {
    if (!hasUnsentText(c)) continue;
    cardExpanded[c.id] = true;
  }

  const groups = { later: [], needs: [], ready: [], waiting: [], done: [], earlier: [], archived: [] };
  // Feedback given on earlier versions stays listed, collapsed under
  // "Earlier feedback", instead of vanishing when a version is published.
  const earlier = (c) => !inScope(c) && !isNewerThanViewed(c);
  for (const c of flattenAll(false)) {
    if (inScope(c)) groups[sectionOf(c)].push(c);
    else if (earlier(c)) groups.earlier.push(c);
  }
  for (const [aid, items] of Object.entries(STORE.archived || {})) {
    for (const c of items) {
      const item = Object.assign({}, c, { anchor_id: aid });
      if (docOf(item) !== DOC) continue;
      if (inScope(item)) groups.archived.push(item);
      else if (earlier(item)) groups.earlier.push(item);
    }
  }
  SECTION_ORDER.forEach(k => groups[k].sort(byContentOrder));

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
    const open = sectionOpen(k) || groups[k].some(hasUnsentText);
    const bodyId = 'sec-body-' + k;
    const badgeCls = k === 'needs' ? 'badge-error' : k === 'later' ? 'badge-ghost' : k === 'ready' ? 'badge-primary' : 'badge-ghost';
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
  listEl.querySelectorAll('.note-edit-ta').forEach(ta => {
    const k = ta.dataset.noteEdit + '|' + ta.dataset.key;
    const n = cardNotes(findCommentById(ta.dataset.noteEdit) || {}).find(n => n.key === ta.dataset.key);
    ta.value = DRAFTS['note:' + k] || (n && n.text) || '';
  });
  listEl.querySelectorAll('.edit-ta').forEach(ta => {
    const c = findCommentById(ta.dataset.editFor);
    ta.value = DRAFTS['edit:' + ta.dataset.editFor] || (c && c.text) || '';
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
  wireNoteActions(listEl);
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
// are the same slot, shown as Request changes.
const DECISION_OPTIONS_ALL = ['accept', 'reject', 'comment', 'changes'];
const DECISION_OPTIONS_DEFAULT = ['accept', 'reject', 'changes'];
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
// Request-changes hint or a failed send per card ({ph, msg, error}), shown in
// both places until it is answered.
const decisionHint = {};
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
let ANCHOR_ORDER = {};
function byContentOrder(a, b) {
  return (ANCHOR_ORDER[a.anchor_id] ?? Infinity) - (ANCHOR_ORDER[b.anchor_id] ?? Infinity) ||
    (NUM_MAP[a.id] || 0) - (NUM_MAP[b.id] || 0);
}
// Whether the standing "Answer in words" form is open. Its text lives in DRAFTS
// under 'say:<id>', the same store as replies and verdict notes.
const decisionSayOpen = {};
// …and the same for the "Request changes" form, whose
// open state used to live in the DOM alone — so a re-render triggered while
// the reviewer was typing closed it and lost the box.
const decisionChangesOpen = {};

// v2.19 schema: dr.options may be the legacy string list or
// [{id, label, consequence, style}]; dr.consequences {accept, reject} is the
// shortcut for string options. Unknown ids are custom `select` choices.
function decisionOptions(dr) {
  const raw = (Array.isArray(dr.options) && dr.options.length) ? dr.options : DECISION_OPTIONS_DEFAULT;
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

// Every card offers "Answer in words" as its last choice (the skill promises
// it); the comment box holds the words. Skipped when the card already poses it.
function withAnswerInWords(opts) {
  if (opts.some(o => o.id === 'comment')) return opts;
  return opts.concat({ id: 'comment', labelHtml: DECISION_BTN_LABEL.comment, labelText: 'comment',
    plainLabel: DECISION_PLAIN_LABEL.comment, consequence: '', style: null, custom: false });
}

// Context is what the reviewer needs in order to decide, so it is always
// shown in full (NN/g: never hide what the decision depends on).
function renderDecisionContext(dr) {
  const ctx = typeof dr.context === 'string' ? dr.context.trim() : '';
  return ctx ? `<div class="${k('decision-context', 'annotate-decision-context')}">${agentText(ctx)}</div>` : '';
}
// "Recommended: <option>" — the MADR "chosen option" line, stated once.
function renderDecisionReco(opts, dr) {
  const rec = typeof dr.recommendation === 'string' ? dr.recommendation : null;
  if (!rec) return '';
  const id = canonicalOptionId(rec);
  const o = opts.find(x => x.id === id);
  const label = o ? o.plainLabel : (DECISION_PLAIN_LABEL[id] || rec);
  return `<div class="${k('decision-reco-line', 'annotate-decision-reco-line')}">Recommended: <b>${esc(label)}</b></div>`;
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
  if (S.doc) return S.x; // read by adapter.js from the document it draws the card in
  return (EXCERPTS_VERSION === CURRENT_VERSION && gotoVersionFor(c) === CURRENT_VERSION) ? EXCERPTS : null;
}
// A quoted excerpt clamped to four lines; "Show more" appears only when the
// text is cut off (see syncExcerptClamps).
function renderExcerptBox(key, text, source, footExtra) {
  const open = !!S.excerptOpen[key];
  const qid = idFor('q|' + key);
  const more = `<button type="button" class="${k('decision-excerpt-more', 'annotate-excerpt-more')}" data-decision-action="excerpt-more" data-key="${escAttr(key)}" aria-controls="${qid}" aria-expanded="${open ? 'true' : 'false'}" hidden>${open ? 'Show less' : 'Show more'}</button>`;
  return `<figure class="${k('decision-excerpt', 'annotate-excerpt')}${open ? ' is-open' : ''}">
      ${source ? `<figcaption class="${k('decision-excerpt-src', 'annotate-excerpt-src')}">${esc(source)}</figcaption>` : ''}
      <blockquote class="${k('decision-excerpt-text', 'annotate-excerpt-text')}" id="${qid}">${esc(text)}</blockquote>
      ${S.doc ? more : `<div class="decision-excerpt-ft">${more}${footExtra || ''}</div>`}
    </figure>`;
}
// The element the card is about, quoted inside the card: the first evidence
// anchor, else the card's own anchor when that is not the card itself.
// C2: the quote carries "Open in document" (the card's own location). In the
// document the card stands right after its own anchor, so only evidence is quoted.
function renderDecisionExcerpt(c, dr) {
  const x = excerptsFor(c);
  if (!x) return '';
  const link = S.doc || isGeneralAnchor(c.anchor_id) || gotoUnavailable[c.id] ? '' : openDocBtn(c, ' data-excerpt-goto="1"');
  const ev = evidenceList(dr);
  const first = ev.length ? x[ev[0].anchor] : null;
  if (first && first.text) return renderExcerptBox(c.id + '|first', first.text, first.name, link);
  const own = !S.doc && x[c.anchor_id];
  if (own && own.text && !own.card) return renderExcerptBox(c.id + '|own', own.text, own.name, link);
  return '';
}
function renderDecisionMeta(dr) {
  let h = '';
  if (typeof dr.impact === 'string' && DECISION_IMPACTS.indexOf(dr.impact) !== -1) {
    h += `<span class="${k('decision-chip decision-chip-impact-', 'annotate-decision-chip annotate-chip-impact-')}${dr.impact}" title="Impact if decided wrongly">Impact: ${dr.impact}</span>`;
  }
  if (dr.blocking === true) {
    h += `<span class="${k('decision-chip decision-chip-blocking', 'annotate-decision-chip annotate-chip-blocking')}" title="The agent cannot proceed until this is decided">Blocking</span>`;
  }
  return h ? `<div class="${k('decision-meta', 'annotate-decision-meta')}">${h}</div>` : '';
}
// "Evidence (n)", collapsed. Each item opens a preview of its target inside
// the card (Wikipedia's reference previews); "Go to" scrolls the document
// there and leaves a "Back to #N" marker that returns to this card. The
// items are built when the list is first opened (evidenceItemsHtml).
function renderDecisionEvidence(c, dr) {
  const ev = evidenceList(dr);
  if (!ev.length) return '';
  const open = !!S.evOpen[c.id];
  const listId = idFor('evl|' + c.id);
  const list = S.doc ? 'div' : 'ul';
  return `<div class="${k('decision-evidence', 'annotate-decision-evidence')}">
      <button type="button" class="${k('decision-evidence-toggle', 'annotate-decision-evidence-toggle')}" data-decision-action="evidence-toggle" data-id="${escAttr(c.id)}" aria-expanded="${open ? 'true' : 'false'}" aria-controls="${listId}">Evidence (${ev.length})</button>
      <${list} class="${k('decision-evidence-list', 'annotate-decision-evidence-list')}" id="${listId}"${open ? '' : ' hidden'}>${open ? evidenceItemsHtml(c, ev) : ''}</${list}>
    </div>`;
}
function evidenceItemsHtml(c, ev) {
  const x = excerptsFor(c);
  const item = S.doc ? 'div' : 'li';
  return ev.map((e, i) => {
    const key = c.id + '|' + e.anchor + '|' + i;
    const itemOpen = !!S.evItemOpen[key];
    const pid = idFor('evp|' + key);
    const hit = x ? x[e.anchor] : null;
    const preview = hit && hit.text
      ? renderExcerptBox('ev|' + key, hit.text, hit.name)
      : `<div class="${k('decision-evidence-missing', 'annotate-decision-evidence-missing')}">${hit && hit.missing ? 'Not on this version of the page.' : S.doc ? 'Nothing to quote here.' : 'No preview for this version.'}</div>`;
    const go = S.doc
      ? `<button type="button" class="annotate-decision-evidence-goto" data-decision-action="evidence" data-anchor="${escAttr(e.anchor)}" data-id="${escAttr(c.id)}" title="Scroll to ${escAttr(e.anchor)}; a &quot;Back&quot; marker there returns here"${hit && hit.missing ? ' disabled' : ''}>Go to ↓</button>`
      : `<button type="button" class="decision-evidence-goto" data-decision-action="evidence" data-anchor="${escAttr(e.anchor)}" data-id="${escAttr(c.id)}" title="Scroll the document to ${escAttr(e.anchor)}; a Back marker there returns here">Go to &rarr;</button>`;
    return `<${item} class="${k('decision-evidence-item', 'annotate-decision-evidence-item')}">
        <button type="button" class="${k('decision-evidence-link', 'annotate-decision-evidence-link')}" data-decision-action="evidence-preview" data-key="${escAttr(key)}" aria-expanded="${itemOpen ? 'true' : 'false'}" aria-controls="${pid}" title="Preview ${escAttr(e.anchor)}"><span class="${k('decision-evidence-label', 'annotate-decision-evidence-label')}">${esc(e.label || e.anchor)}</span></button>
        <div class="${k('decision-evidence-preview', 'annotate-decision-evidence-preview')}" id="${pid}"${itemOpen ? '' : ' hidden'}>
          ${preview}
          ${go}
        </div>
      </${item}>`;
  }).join('');
}
// Show "Show more" only under an excerpt the clamp actually cuts off. An
// unrendered one (collapsed rail, closed preview) is judged by its length.
function syncExcerptClamps(root) {
  if (!root) return;
  // Every measurement first, then every change: interleaving them forced a
  // layout per card (150 ms per render on FLD).
  const writes = [];
  root.querySelectorAll('.decision-excerpt, .annotate-excerpt').forEach(box => {
    const t = box.querySelector('.decision-excerpt-text, .annotate-excerpt-text');
    const more = box.querySelector('.decision-excerpt-more, .annotate-excerpt-more');
    if (!t || !more) return;
    if (box.classList.contains('is-open')) { writes.push([more, false]); return; }
    const text = t.textContent || '';
    writes.push([more, !(t.clientHeight > 0
      ? t.scrollHeight > t.clientHeight + 1
      : (text.length > 220 || (text.match(/\n/g) || []).length >= 4))]);
  });
  // UI-23: long comment text in a card.
  root.querySelectorAll('.citem-txt-more').forEach(more => {
    const t = document.getElementById(more.getAttribute('aria-controls'));
    if (!t) return;
    if (t.classList.contains('is-open')) { writes.push([more, false]); return; }
    writes.push([more, !(t.clientHeight > 0 ? t.scrollHeight > t.clientHeight + 1 : true)]);
  });
  for (const [el, hidden] of writes) el.hidden = hidden;
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
  if (pageReadOnly()) return `<div class="decision-block decision-resolved"><div class="decision-prompt">${ticketsHTML(displayPrompt(c))}</div><span class="badge badge-ghost">Archived · read-only</span></div>`;
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
  const changing = !!S.changing[c.id];
  if (decisionAnswer(c) && !changing) return answerBlockHtml(c);
  // Changing the choice: the options only; your notes stay as they are.
  // Changing keeps every way to answer, words included (Chang, 2026-10-31).
  const opts = withAnswerInWords(decisionOptions(dr));
  const wantsChanges = opts.some(o => o.id === 'changes');
  const hasCons = opts.some(o => !!o.consequence);
  const rec = typeof dr.recommendation === 'string' ? dr.recommendation : null;
  const kbd = !S.doc && showKbd(c);
  const id = escAttr(c.id);
  let btns = '';
  opts.forEach((o, i) => {
    const isRec = !!rec && canonicalOptionId(rec) === o.id;
    const cls = o.custom
      ? k('decision-custom', 'annotate-decision-custom') + (o.style ? k(' decision-style-', ' annotate-style-') + o.style : '')
      : k('', 'annotate-') + DECISION_BTN_CLASS[o.id];
    const action = o.custom ? 'custom' : o.id;
    const extra = o.custom ? ` data-option-id="${escAttr(o.id)}" data-option-label="${escAttr(o.labelText)}"` : '';
    const badge = isRec ? k('<span class="badge badge-success badge-soft badge-xs decision-rec-badge">Recommended</span>', '<span class="annotate-decision-rec">Recommended</span>') : '';
    const cons = o.consequence ? `<span class="${k('decision-consequence', 'annotate-decision-consequence')}">${esc(o.consequence)}</span>` : '';
    const key = kbd && i < 9 ? `<kbd class="kbd kbd-xs">${i + 1}</kbd>` : '';
    btns += `<button type="button" class="${k('btn decision-btn', 'annotate-decision-btn annotate-opt-row')} ${cls}${isRec ? ' is-recommended' : ''}" data-decision-action="${action}" data-id="${id}"${extra}${isRec ? ' title="Recommended by the agent"' : ''}><span class="${k('decision-opt-head', 'annotate-opt-head')}">${key}<span class="${k('decision-opt-label', 'annotate-opt-label')}">${o.labelHtml}</span>${badge}</span>${cons}</button>`;
  });
  const changingNote = (c.decision && changing) ? `<div class="${k('decision-changing-note', 'annotate-decision-changing-note')}">
      <span>Pick a new answer. Your notes stay.</span>
      <button type="button" class="${k('btn btn-ghost btn-xs', 'annotate-decision-btn annotate-decision-cancel')}" data-decision-action="cancel-change" data-id="${id}">Cancel</button>
    </div>` : '';
  const hint = decisionHint[c.id];
  // A1: one optional box under the options; it goes with whichever option is
  // picked, and with none picked it is the answer at Send.
  const cmtHtml = S.doc
    ? `<textarea class="annotate-decision-ta annotate-decision-cmt" data-decision-say-ta="${id}" data-strip-say="${id}" data-wants-changes="${wantsChanges ? '1' : ''}" placeholder="${escAttr(hint && hint.ph ? hint.ph : 'Comment (optional)')}" rows="1" aria-label="Comment (optional)"></textarea>
    <div class="annotate-decision-cmt-hint" data-say-hint="${id}"></div>`
    : `<div class="decision-cmt">
      <div class="add-note">
        <textarea class="textarea textarea-sm decision-say-ta" data-decision-say-ta="${id}" data-wants-changes="${wantsChanges ? '1' : ''}" placeholder="${escAttr(hint && hint.ph ? hint.ph : 'Add a note (optional)')}" rows="1" aria-label="Note on #${NUM_MAP[c.id] || ''} (optional)"></textarea>
        <button type="button" class="btn btn-sm" data-note-action="add" data-id="${id}" title="Answer in words with this note">Add note</button>
      </div>
      ${kbd ? '<kbd class="kbd kbd-xs">C</kbd>' : ''}
      <div class="decision-cmt-hint" data-say-hint="${id}"></div>
    </div>`;
  // The document's card replaces the generated one, so it keeps the card's own
  // text when that says more than the prompt (the rail shows it above).
  const text = S.doc && typeof c.text === 'string' ? c.text.trim() : '';
  const textHtml = text && normText(text) !== normText(displayPrompt(c)) ? `<div class="annotate-decision-text">${esc(text)}</div>` : '';
  return `<div class="${k('decision-block', 'annotate-decision-item')}"${docItemAttr(c)}>
    ${S.doc ? '' : changingNote}
    ${promptHtml(c)}
    ${textHtml}
    ${renderDecisionMeta(dr)}
    ${S.doc ? changingNote : ''}
    ${renderDecisionContext(dr)}
    ${renderDecisionReco(opts, dr)}
    ${renderDecisionExcerpt(c, dr)}
    <div class="${k('decision-btns', 'annotate-decision-btns')}${hasCons ? ' has-consequences' : ''}" data-options>${btns}</div>
    ${decisionAnswer(c) ? '' : `<button type="button" class="${k('btn btn-ghost btn-sm decision-later', 'annotate-decision-btn annotate-decision-later')}" data-decision-action="later" data-later="${isSetAside(c) ? '0' : '1'}" data-id="${id}">${isSetAside(c) ? 'Back to Needs you' : 'Answer later'}</button>`}
    ${renderDecisionEvidence(c, dr)}
    ${cmtHtml}
    ${feedbackHtml(c)}
  </div>`;
}
function promptHtml(c) {
  if (!S.doc) return `<div class="decision-prompt">${ticketsHTML(displayPrompt(c))}</div>`;
  const n = NUM_MAP[c.id];
  return `<div class="annotate-decision-prompt">${n ? `<span class="annotate-decision-num">#${n}</span>` : ''}${esc(displayPrompt(c))}</div>`;
}
function docItemAttr(c) {
  return S.doc ? ` data-strip-item="${escAttr(c.id)}"` : '';
}
function feedbackHtml(c) {
  const h = decisionHint[c.id];
  return `<div class="${k('decision-feedback', 'annotate-decision-feedback')}${h && h.error ? ' is-error' : ''}" data-decision-feedback="${escAttr(c.id)}">${h && h.msg ? esc(h.msg) : ''}</div>`;
}
function normText(s) {
  return String(s || '').replace(/\s+/g, ' ').trim();
}
// The hint under the comment box says what typed text will do.
function syncSayHint(ta) {
  const id = ta.dataset.decisionSayTa;
  const hint = ta.ownerDocument.querySelector('[data-say-hint="' + cssEsc(id) + '"]');
  if (!hint) return;
  hint.textContent = (ta.value || '').trim()
    ? 'Saved with your choice. With no choice picked, it counts as your answer when you send.'
    : '';
}

// C3: rare actions in one ⋯ menu (Resolve, Re-open, Archive, Re-pin, …).
function cardMenuItems(c, cls) {
  const id = escAttr(c.id);
  const items = [];
  if (canEditComment(c)) items.push(`<li><button type="button" data-action="edit" data-id="${id}">${ico('pencil')} Edit</button></li>`);
  if (canDeleteComment(c)) items.push(`<li><button type="button" data-action="delete" data-id="${id}">Delete</button></li>`);
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
// Your own comment (not a question card) can be edited; the edit goes to the
// agent with the next Send (Chang, 2026-10-30).
const editingComment = {};
function isMine(author) {
  return !!author && (author === AUTHOR || !!(IDENTITY && (IDENTITY.reviewer_authors || [IDENTITY.email]).includes(author)));
}
function canEditComment(c) {
  return !pageReadOnly() && !c.pending && !c.decision_request && c.status !== 'archived' && isMine(c.author);
}
// Not sent and not answered: nothing to archive, so it can simply go (Chang,
// 2026-10-30). The server refuses anything else.
function canDeleteComment(c) {
  return canEditComment(c) && !c.flagged_for_session && !(c.replies || []).length && !c.response_text && !c.round_pending;
}
function editBoxHtml(c) {
  return `<div class="comment-edit">
    <textarea class="textarea textarea-sm edit-ta" data-edit-for="${escAttr(c.id)}" rows="3" aria-label="Edit your comment"></textarea>
    <div class="comment-edit-ft">
      <button type="button" class="btn btn-ghost btn-xs" data-action="edit-cancel" data-id="${escAttr(c.id)}">Cancel</button>
      <button type="button" class="btn btn-primary btn-xs" data-action="edit-save" data-id="${escAttr(c.id)}">Save</button>
    </div>
  </div>${replyError[c.id] ? `<div class="decision-feedback is-error" role="alert">${esc(replyError[c.id])}</div>` : ''}`;
}
// ── A question card's answer: your choice and your notes ──────────────
// A second worded answer used to replace the first, and only the last one
// reached the agent (Chang, 2026-10-30, #2659 and #2671). Words are now
// notes: adding one never replaces another, each can be edited, and an
// unsent one deleted. The choice is separate and changing it keeps them.
// The first note lives in the decision; later ones are your replies.
const GENERATED_REPLY = /^(💬 Answer in words: |☑ Selected: |↻ Changes requested: |✓ Accepted|✗ Rejected|↺ Changed to )/;
const editingNote = {}; // 'id|key' while that note's editor is open

// ── One question card in two places ──────────────────────────────────
// The rail and the document draw a question card with this one builder
// (renderDecisionBlock and the helpers it calls). adapter.js asks for the
// document's copy through stripCard below, so both copies share every rule and
// action. Each place keeps its own classes (the rail's daisyUI + shell.css, the
// document's adapter.js styles), and its own open, changing and editing state.
const RAIL_CARD = { doc: false, changing: decisionChanging, editing: editingNote,
  evOpen: decisionEvidenceOpen, evItemOpen: decisionEvidenceItemOpen, excerptOpen: decisionExcerptOpen };
const DOC_CARD = { doc: true, changing: {}, editing: {}, evOpen: {}, evItemOpen: {}, excerptOpen: {}, x: null };
let S = RAIL_CARD; // the place being drawn
const k = (rail, doc) => S.doc ? doc : rail;
const surfaceOf = el => el.closest('[data-strip-item]') ? DOC_CARD : RAIL_CARD;
// Agent text: issue ids link in the rail; the document links its own (linkBoardIds).
const agentText = s => S.doc ? esc(s) : ticketsHTML(s);
const icon = name => S.doc ? ico(name).replace('<svg class="i" ', '<svg width="14" height="14" ') : ico(name);
// Redraw the place an action came from. The document's card is replaced at
// once, as the click lands; the counts message then brings the frame in line.
function redrawCard(el) {
  if (!surfaceOf(el).doc) return renderDrawer();
  const item = el.closest('[data-strip-item]');
  const fresh = item && stripCard(item.ownerDocument, item.dataset.stripItem, DOC_CARD.x);
  if (fresh) item.replaceWith(fresh);
  sendCommentCountsToFrame();
}
function withSurface(s, fn) {
  const was = S;
  S = s;
  try { return fn(); } finally { S = was; }
}
// The document's card for one question, wired to the same actions as the
// rail's; adapter.js places it. `x` is that document's excerpts.
function stripCard(doc, id, x) {
  const c = findCommentById(id);
  if (!c || !c.decision_request) return null;
  DOC_CARD.x = x || {};
  const t = doc.createElement('template');
  t.innerHTML = withSurface(DOC_CARD, () => renderDecisionBlock(c));
  const el = t.content.firstElementChild;
  if (!el) return null;
  el.querySelectorAll('[data-decision-say-ta]').forEach(ta => { ta.value = DRAFTS['say:' + id] || ''; syncSayHint(ta); });
  el.querySelectorAll('[data-note-edit]').forEach(ta => { ta.value = DOC_CARD.editing[id + '|' + ta.dataset.key] || ''; });
  wireDecisionActions(el, doc);
  wireNoteActions(el, doc);
  return el;
}
// A read-only page has no questions to answer, only their answers.
function stripVerdictChip(doc, id) {
  const c = findCommentById(id);
  const d = c && decisionAnswer(c);
  if (!d) return null;
  const t = doc.createElement('template');
  t.innerHTML = `<div class="annotate-decision-item annotate-decision-resolved" data-strip-item="${escAttr(id)}"><span class="annotate-verdict-chip verdict-${escAttr(d.verdict)}">${esc(answerLabel(c).text)}</span></div>`;
  return t.content.firstElementChild;
}
function choiceLabel(c) {
  const d = decisionAnswer(c);
  if (!d || d.verdict === 'comment' || d.verdict === 'changes') return '';
  if (d.verdict === 'select') return String(d.text || '').split('\n\n')[0].replace(/^Selected:\s*/, '');
  const o = decisionOptions(c.decision_request || {}).find(o => o.id === d.verdict);
  return o ? o.labelText : (DECISION_VERDICT_LABEL[d.verdict] || d.verdict);
}
function decisionNote(c) {
  const d = decisionAnswer(c);
  if (!d || !d.text) return '';
  if (d.verdict === 'select' || /^Selected: /.test(d.text)) {
    const at = d.text.indexOf('\n\n');
    return at === -1 ? '' : d.text.slice(at + 2).trim();
  }
  return d.text.trim();
}
const tsOf = s => new Date(s || 0).getTime();
// The server's _note_unsent: new notes carry sent_at; older ones go by the card's last send.
function noteUnsent(c, r) {
  if ('sent_at' in r) return !r.sent_at;
  return !c.flagged_at || tsOf(c.flagged_at) < tsOf(r.edited_at || r.ts);
}
function cardNotes(c) {
  const notes = [];
  const d = decisionAnswer(c);
  const dn = decisionNote(c);
  if (dn && isMine(d.by)) notes.push({ key: 'decision', text: dn, delivery_id: d.delivery_id, pending: !!(d.round_pending || d.pending) });
  (c.replies || []).forEach((r, i) => {
    if (!isMine(r.author) || r.pending || GENERATED_REPLY.test(r.text || '')) return;
    const pending = noteUnsent(c, r);
    notes.push({ key: 'r' + i, idx: i, ts: r.ts, text: r.text, delivery_id: r.delivery_id, pending, deletable: pending });
  });
  return notes;
}
// The card shows the add-note box itself, so typed text is a note, not stranded.
function hasAddNoteBox(c) {
  return !pageReadOnly() && !!c.decision_request && !!decisionAnswer(c) && c.status !== 'archived' && c.status !== 'resolved_in_version';
}
function stateTag(pending, c) {
  const cls = k('send-state', 'annotate-send-state');
  return pending ? `<span class="${cls} is-pending" title="Saved here. Goes to the agent when you press Send.">Pending</span>`
    : `<span class="${cls}" title="Owner session delivery">${deliveryHtml(c && c.delivery_id)}</span>`;
}
function noteHtml(c, n) {
  const id = escAttr(c.id), key = escAttr(n.key);
  const btn = (action, rail, doc, label) => `<button type="button" class="${k(rail, 'annotate-decision-btn ' + doc)}" data-note-action="${action}" data-id="${id}" data-key="${key}"${label || ''}>`;
  if (S.editing[c.id + '|' + n.key] !== undefined) return `<div class="${k('answer-note', 'annotate-answer-note')} is-editing">
      <textarea class="${k('textarea textarea-sm note-edit-ta', 'annotate-decision-ta annotate-note-edit')}" data-note-edit="${id}" data-key="${key}" rows="3" aria-label="Edit your note"></textarea>
      <div class="${k('note-actions', 'annotate-note-actions')}">${btn('cancel', 'btn btn-ghost btn-xs', 'annotate-note-cancel')}Cancel</button>${btn('save', 'btn btn-primary btn-xs', 'annotate-note-save')}Save</button></div>
    </div>`;
  const iconBtn = (action, name, label, cls) => btn(action, 'btn btn-ghost btn-xs btn-square', 'annotate-note-icon ' + cls,
    ` aria-label="${label}" title="${k(label.split(' ')[0], label)}"`) + icon(name) + '</button>';
  return `<div class="${k('answer-note', 'annotate-answer-note')}">
      <div class="${k('answer-note-txt', 'annotate-answer-note-txt')}">${agentText(n.text)}</div>
      <div class="${k('note-actions', 'annotate-note-actions')}">${stateTag(n.pending, n)}${iconBtn('edit', 'pencil', 'Edit note', 'annotate-note-edit-btn')}${n.deletable ? iconBtn('delete', 'trash', 'Delete note', 'annotate-note-delete-btn') : ''}</div>
    </div>`;
}
function addNoteHtml(c) {
  const id = escAttr(c.id);
  return `<div class="${k('add-note', 'annotate-add-note')}">
      <textarea class="${k('textarea textarea-sm decision-say-ta', 'annotate-decision-ta annotate-decision-cmt')}" data-decision-say-ta="${id}"${S.doc ? ` data-strip-say="${id}"` : ''} rows="1" placeholder="Add a note…" aria-label="${S.doc ? 'Add a note' : 'Add a note to #' + (NUM_MAP[c.id] || '')}"></textarea>
      <button type="button" class="${k('btn btn-sm', 'annotate-decision-btn annotate-note-add')}" data-note-action="add" data-id="${id}">Add note</button>
    </div>`;
}
// An answered card: your choice (Change keeps your notes), then your notes,
// each with Pending/Sent, Edit and (while unsent) Delete, then "Add a note".
function answerBlockHtml(c) {
  const choice = choiceLabel(c);
  const notes = cardNotes(c);
  const d = decisionAnswer(c);
  const lbl = k('answer-lbl', 'annotate-answer-lbl');
  const choiceHtml = S.doc
    ? `<span class="annotate-answer-choice${choice ? '' : ' is-none'}">${esc(choice || 'None (answered in words)')}</span>`
    : `<span class="answer-choice">${choice ? esc(choice) : '<span class="answer-none">None (answered in words)</span>'}</span>`;
  return `<div class="${k('decision-block decision-answered', 'annotate-decision-item annotate-decision-resolved annotate-answered')}"${docItemAttr(c)}>
      ${promptHtml(c)}
      <div class="${k('answer-row', 'annotate-answer-row')}"><span class="${lbl}">Your choice</span>${choiceHtml}${choice ? stateTag(!!(d.round_pending || d.pending), d) : ''}${canChangeAnswer(c) ? `<button type="button" class="${k('btn btn-ghost btn-xs', 'annotate-decision-btn annotate-answer-change')}" data-decision-action="change" data-id="${escAttr(c.id)}">${choice ? 'Change' : 'Choose'}</button>` : ''}</div>
      ${notes.length ? `<div class="${k('answer-notes', 'annotate-answer-notes')}"><span class="${lbl}">Your notes</span>${notes.map(n => noteHtml(c, n)).join('')}</div>` : ''}
      ${addNoteHtml(c)}
      ${feedbackHtml(c)}
      ${c.catalog_plan && !S.doc ? `<a href="#view=plans&plan=${encodeURIComponent(c.catalog_plan)}">Filed in Plans</a>` : ''}
      ${c.decision?.catalog_conflict && !S.doc ? '<p>A newer decision is current in Plans; this vote is preserved in history.</p>' : ''}
    </div>`;
}
async function apiReplyNote(id, idx, ts, text) {
  try {
    const url = apiUrl('./api/comments/' + encodeURIComponent(id) + '/replies/' + idx + authorQuery());
    const r = text == null
      ? await fetch(url + (url.includes('?') ? '&' : '?') + 'ts=' + encodeURIComponent(ts), { method: 'DELETE' })
      : await fetch(url, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ts, text }) });
    return r.ok;
  } catch { return false; }
}
// A decision re-posted with new words keeps whatever the box under it holds.
async function keepingAddNoteDraft(id, fn) {
  const keep = DRAFTS['say:' + id] || '';
  const r = await fn();
  if (keep && !DRAFTS['say:' + id]) { setDraft('say:' + id, keep); mirrorSay(id); renderDrawer(); }
  return r;
}
async function addNote(root, id) {
  const c = findCommentById(id);
  const text = c && sayDraft(c);
  if (!text) return;
  // No answer yet: the first note answers the card in words.
  if (!decisionAnswer(c)) return submitDecision(root, id, 'comment', text);
  if (await apiReply(id, text)) {
    clearSayDraft(id);
    await refreshStore();
    markReadAfterAction(id);
  } else setDecisionFeedback(root, id, 'Could not add the note. Your text is still in the box; try again.', true);
}
async function saveNote(root, id, key, text) {
  const c = findCommentById(id);
  if (!c || !text) return false;
  if (key === 'decision') {
    const d = decisionAnswer(c);
    const verdict = d.verdict;
    const body = verdict === 'select' ? choiceLabel(c) + '\n\n' + text : text;
    return !!(await keepingAddNoteDraft(id, () => submitDecision(root, id, verdict, body, d.option_id)));
  }
  const n = cardNotes(c).find(n => n.key === key);
  const ok = n && await apiReplyNote(id, n.idx, n.ts, text);
  if (ok) { await refreshStore(); markReadAfterAction(id); }
  return !!ok;
}
async function deleteNote(id, key) {
  const n = cardNotes(findCommentById(id) || {}).find(n => n.key === key);
  if (!n || !n.deletable || !confirm('Delete this note? It has not been sent.')) return;
  if (await apiReplyNote(id, n.idx, n.ts, null)) await refreshStore();
  else { alert('Could not delete the note; it may have just been sent. Edit it instead.'); await refreshStore(); }
}
// `scope` is where the card's boxes live: the rail list, or the document.
function wireNoteActions(root, scope = root) {
  root.querySelectorAll('[data-note-action]').forEach(btn => btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    const { id, key } = btn.dataset;
    const k = id + '|' + key;
    const action = btn.dataset.noteAction;
    if (action === 'add') return addNote(scope, id);
    if (action === 'delete') return deleteNote(id, key);
    if (surfaceOf(btn).doc) return docNoteAction(btn, scope, id, key, action);
    if (action === 'edit') {
      editingNote[k] = true;
      renderDrawer();
      const ta = document.querySelector('#comment-list [data-note-edit="' + cssEsc(id) + '"][data-key="' + cssEsc(key) + '"]');
      if (ta) { ta.focus(); ta.selectionStart = ta.selectionEnd = ta.value.length; }
      return;
    }
    if (action === 'cancel') { delete editingNote[k]; setDraft('note:' + k, ''); return renderDrawer(); }
    if (action === 'save') {
      const ta = root.querySelector('[data-note-edit="' + cssEsc(id) + '"][data-key="' + cssEsc(key) + '"]');
      const text = (ta && ta.value || '').trim();
      if (!text) return;
      btn.disabled = true;
      delete editingNote[k];
      setDraft('note:' + k, '');
      if (!(await saveNote(root, id, key, text))) {
        setDraft('note:' + k, text);
        editingNote[k] = true;
        renderDrawer();
        setDecisionFeedback(document, id, 'Could not save the note. Your text is still here; try again.', true);
      }
    }
  }));
  root.querySelectorAll('[data-note-edit]').forEach(ta => ta.addEventListener('input', () => {
    const k = ta.dataset.noteEdit + '|' + ta.dataset.key;
    if (surfaceOf(ta).doc) DOC_CARD.editing[k] = ta.value;
    else setDraft('note:' + k, ta.value);
  }));
  root.querySelectorAll('[data-action="open-card"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    cardExpanded[btn.dataset.id] = true;
    renderDrawer();
    const ta = document.querySelector('#comment-list [data-decision-say-ta="' + cssEsc(btn.dataset.id) + '"]');
    if (ta) ta.focus();
  }));
}
// A note action on the document's card: its editor state is the document's own.
async function docNoteAction(btn, scope, id, key, action) {
  const k = id + '|' + key;
  if (action === 'edit') {
    const n = cardNotes(findCommentById(id) || {}).find(n => n.key === key);
    DOC_CARD.editing[k] = n ? n.text : '';
  } else if (action === 'cancel') {
    delete DOC_CARD.editing[k];
  } else if (action === 'save') {
    const ta = btn.closest('[data-strip-item]').querySelector('[data-note-edit][data-key="' + cssEsc(key) + '"]');
    const text = (ta && ta.value || '').trim();
    if (!text) return;
    btn.disabled = true;
    if (!(await saveNote(scope, id, key, text))) {
      btn.disabled = false;
      setDecisionFeedback(scope, id, 'Could not save the note. Your text is still here; try again.', true);
      return;
    }
    delete DOC_CARD.editing[k];
  }
  redrawCard(btn);
}
// Pending: saved here, not sent to the agent yet. Sent: in a Send (or round).
function sendStateHtml(c) {
  if (!isMine(c.author) && !(c.decision && isMine(c.decision.by))) return '';
  if (needsPush(c) || isRoundPending(c) || strandedSay(c)) return '<span class="send-state is-pending" title="Saved here. Goes to the agent when you press Send.">Pending</span>';
  if (c.flagged_for_session || (c.decision && !c.decision.round_pending)) return stateTag(false, c);
  return '';
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
  if (cardExpanded[c.id] || decisionChanging[c.id] || strandedSay(c)) return false;
  if (!c.decision_request || c.status === 'archived') return false;
  return !!decisionAnswer(c) || c.status === 'resolved_in_version' || c.status === 'addressed_by_agent';
}

// U-10: an open card from a newer version than the one on screen says so,
// with the way to its version; one-line cards too, as in final/ (UI-19).
function newerLocationHtml(c) {
  return isNewerThanViewed(c) && followsViewer(c)
    ? `<div class="citem-loc unified-newer-location">Not in ${esc(CURRENT_VERSION)} — <button type="button" class="btn btn-link btn-xs" data-action="goto" data-id="${escAttr(c.id)}" data-anchor="${escAttr(c.anchor_id)}" data-version="${escAttr(c.version)}">open ${esc(c.version)}</button></div>`
    : '';
}
// UI-23: a long comment is clamped to a few lines in its card; final/'s
// "Show more" / "Show less" (as on quoted excerpts) appears only when the
// clamp cuts the text off (see syncExcerptClamps).
const commentTextOpen = {};
// v9o: the error of a reply that failed.
const replyError = {};
function commentTextHtml(c) {
  const text = String(c.text == null ? '' : c.text);
  if (text.length < 400 && (text.match(/\n/g) || []).length < 10) return `<div class="citem-txt">${ticketsHTML(text)}</div>`;
  const open = !!commentTextOpen[c.id];
  const tid = idFor('txt|' + c.id);
  return `<div class="citem-txt is-clampable${open ? ' is-open' : ''}" id="${tid}">${ticketsHTML(text)}</div><button type="button" class="decision-excerpt-more citem-txt-more" data-action="text-more" data-id="${escAttr(c.id)}" aria-controls="${tid}" aria-expanded="${open ? 'true' : 'false'}" hidden>${open ? 'Show less' : 'Show more'}</button>`;
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
        ${sendStateHtml(c)}
        ${hasAddNoteBox(c) ? `<button type="button" class="btn btn-ghost btn-xs btn-square change-btn" data-action="open-card" data-id="${escAttr(c.id)}" aria-label="Edit your answer to #${num || ''}" title="Edit your answer">${ico('pencil')}</button>` : ''}
        ${cardMenuHtml(c, cls)}
      </div>
      ${c.catalog_plan ? `<a href="#view=plans&plan=${encodeURIComponent(c.catalog_plan)}">Filed in Plans</a>` : ''}
      ${c.decision?.catalog_conflict ? '<p>A newer decision is current in Plans; this vote is preserved in history.</p>' : ''}
      ${cardMenuPanel(c, cls)}${newerLocationHtml(c)}
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
  const replies = (c.replies || []).filter(r => !(c.decision_request && isMine(r.author) && !GENERATED_REPLY.test(r.text || ''))).filter(r => !(d && r.ts === d.ts && r.author === d.by &&
    (r.text === generatedAnswer || r.text.startsWith(generatedAnswer + '\n\n(revised verdict'))));
  const renderReply = r => `
    <div class="thread-reply${r.pending ? ' is-pending' : ''}">
      <div class="thread-reply-hdr">${esc(authorLabel(r))} &middot; ${r.pending ? 'Sending…' : esc(fmtTs(r.ts))}</div>
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

  const showReply = !pageReadOnly() && c.status !== 'archived' && agentResponded(c) && !isUnresolvedDecision(c) && !decisionChanging[c.id] && !hasAddNoteBox(c);
  const replyFormHtml = showReply ? `
    <div class="reply-form">
      <textarea class="textarea textarea-sm reply-ta" data-reply-for="${escAttr(c.id)}" placeholder="Add a reply&hellip;" rows="2"></textarea>
      <button class="btn btn-sm reply-submit" data-action="reply" data-id="${escAttr(c.id)}">Post reply</button>
    </div>${replyError[c.id] ? `<div class="decision-feedback is-error" role="alert">${esc(replyError[c.id])}</div>` : ''}` : '';

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
  const newerHtml = newerLocationHtml(c);
  const navKeys = showKbd(c) ? '<span class="citem-kbd"><kbd class="kbd kbd-xs" title="Previous card">A</kbd><kbd class="kbd kbd-xs" title="Next card">F</kbd></span>' : '';

  return `<div class="citem${hl}${unreadCls}${decisionCls}${c.pending ? ' is-pending' : ''}" data-comment-id="${escAttr(c.id)}" title="Click to show this comment's location in the document">
    <div class="citem-node">
      ${unreadDotHtml(c)}
      <span class="citem-node-name">${numHtml}${imageTag(c.target) ? `<span class="citem-img-id">${imageTag(c.target)}</span> ` : ''}${esc(anchorLabel(c))}</span>
      ${navKeys}${collapseHtml}${c.pending ? '' : cardMenuHtml(c, cls)}
    </div>
    ${c.pending ? '' : cardMenuPanel(c, cls)}
    ${locHtml}
    ${editingComment[c.id] ? editBoxHtml(c) : sameText(c.text, c.decision_request && (c.decision_request.prompt || '')) ? '' : commentTextHtml(c)}
    ${agentReplyHtml}
    ${replyHtml}
    ${quoteHtml}${newerHtml}
    <div class="citem-meta">
      <span class="citem-author">${esc(authorLabel(c))}</span>
      <span>${c.pending ? 'Sending…' : fmtTs(c.created_at) + (c.edited_at ? ' (edited)' : '')} ${c.pending ? '' : sendStateHtml(c)}</span>
    </div>
    ${decisionHtml}
    ${strandedSay(c) && !hasAddNoteBox(c) ? strandedSayHtml(c) : ''}
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
    // Mouse only: on a tap the highlight made iPad drop the click (see adapter.js byMouse).
    card.addEventListener('pointerenter', e => { if (e.pointerType === 'mouse') hover(true); });
    card.addEventListener('pointerleave', e => { if (e.pointerType === 'mouse') hover(false); });
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
  root.querySelectorAll('[data-action="edit"]').forEach(btn => btn.addEventListener('click', closeMenuThen(async (b) => {
    editingComment[b.dataset.id] = true;
    renderDrawer();
    const ta = document.querySelector('#comment-list [data-edit-for="' + cssEsc(b.dataset.id) + '"]');
    if (ta) { ta.focus(); ta.selectionStart = ta.selectionEnd = ta.value.length; }
  })));
  root.querySelectorAll('[data-action="delete"]').forEach(btn => btn.addEventListener('click', closeMenuThen(async (b) => {
    if (!confirm('Delete this comment? It has not been sent, so the agent never sees it.')) return;
    if (await apiDelete(b.dataset.id)) {
      delete editingComment[b.dataset.id];
      setDraft('edit:' + b.dataset.id, '');
      await refreshStore();
    } else {
      alert('Could not delete this comment; it may have just been sent. Archive it instead.');
      await refreshStore();
    }
  })));
  root.querySelectorAll('.edit-ta').forEach(ta => ta.addEventListener('input', () => setDraft('edit:' + ta.dataset.editFor, ta.value)));
  root.querySelectorAll('[data-action="edit-cancel"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    delete editingComment[btn.dataset.id];
    setDraft('edit:' + btn.dataset.id, '');
    renderDrawer();
  }));
  root.querySelectorAll('[data-action="edit-save"]').forEach(btn => btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    const id = btn.dataset.id;
    const c = findCommentById(id);
    const ta = root.querySelector('[data-edit-for="' + cssEsc(id) + '"]');
    const text = (ta && ta.value || '').trim();
    if (!c || !text) return;
    btn.disabled = true;
    // Saved text goes to the agent with the next Send; a closed comment re-opens.
    const patch = c.status === 'open' ? { text } : { text, status: 'open' };
    if (await apiPutComment(id, patch)) {
      delete editingComment[id];
      setDraft('edit:' + id, '');
      await refreshStore();
      markReadAfterAction(id);
    } else {
      btn.disabled = false;
      replyError[id] = 'Could not save the edit. Your text is still here; try again.';
      renderDrawer();
    }
  }));
  root.querySelectorAll('[data-action="reply"]').forEach(btn => btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    const id = btn.dataset.id;
    const ta = root.querySelector('[data-reply-for="' + cssEsc(id) + '"]');
    const text = (ta && ta.value || '').trim();
    const c = storedComment(id);
    if (!text || !c) { if (ta) ta.focus(); return; }
    // v9o: the reply shows at once, marked Sending…, and the box is free for
    // the next one; the text waits as a 'sending:' draft until the server has
    // it, and a failure puts it back in the box (ahead of anything newer).
    const reply = { text, author: AUTHOR, author_name: IDENTITY && IDENTITY.name, author_email: IDENTITY && IDENTITY.email, ts: new Date().toISOString(), pending: true };
    const unpost = () => [c, storedComment(id)].forEach(cur => { const i = cur ? (cur.replies || []).indexOf(reply) : -1; if (i !== -1) cur.replies.splice(i, 1); });
    addPendingEdit(reply, () => { const cur = storedComment(id); if (cur && !(cur.replies || []).includes(reply)) (cur.replies = cur.replies || []).push(reply); });
    setDraft('sending:' + id, text);
    setDraft(id, '');
    ta.value = '';
    delete replyError[id];
    renderDrawer();
    let posted = await settlePending(apiReply(id, text));
    pendingEdits.delete(reply);
    unpost();
    // An answer lost on the way back: the server may have the reply anyway.
    if (!posted && await loadStore()) posted = sentLanded(id, text);
    setDraft('sending:' + id, '');
    if (!posted) {
      const merged = mergeDraft(DRAFTS[id], text);
      setDraft(id, merged);
      const box = document.querySelector('#comment-list [data-reply-for="' + cssEsc(id) + '"]');
      if (box) box.value = merged;
      replyError[id] = 'Reply not sent — the server did not answer. Your text is still in the box; try again.';
      renderDrawer();
      return;
    }
    await refreshStore();
    markReadAfterAction(id);
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
  root.querySelectorAll('[data-options] > [data-id="' + cssEsc(id) + '"]').forEach(b => { b.disabled = disabled; });
}

// A1: the one comment box under the options. Its text goes with whichever
// option is clicked (2.20's optional note); null when empty.
function decisionCommentText(root, id) {
  const ta = root.querySelector('[data-decision-say-ta="' + cssEsc(id) + '"]');
  const t = ((ta ? ta.value : DRAFTS['say:' + id]) || '').trim();
  return t || null;
}

// v9o: the answer shows at once (the card, its strip and the counts); the
// comment box keeps its draft until the server has the answer, and a failure
// puts the card back as it was, text included.
async function submitDecision(root, id, verdict, text, optionId) {
  setDecisionButtonsDisabled(root, id, true);
  setDecisionFeedback(root, id, 'Sending…', false);
  const c = storedComment(id);
  const was = c && { changing: decisionChanging[id], docChanging: DOC_CARD.changing[id], expanded: cardExpanded[id] };
  const optimistic = { verdict, text: text || undefined, option_id: optionId, by: IDENTITY ? IDENTITY.email : AUTHOR,
    ts: new Date().toISOString(), round_pending: true, pending: true };
  // The card it went on and what it replaced (a store read meanwhile puts
  // it on the fresh copy of the card).
  let holder = null, prior = null;
  if (c) {
    addPendingEdit(optimistic, () => {
      const cur = storedComment(id);
      if (cur && cur.decision !== optimistic) { holder = cur; prior = cur.decision; cur.decision = optimistic; }
    });
    delete decisionChanging[id];
    delete DOC_CARD.changing[id];
    delete decisionHint[id];
    renderDrawer();
    sendCommentCountsToFrame();
    updateSendState();
  }
  const result = await settlePending(apiDecision(id, verdict, text, optionId, (root.ownerDocument || root).defaultView || window));
  pendingEdits.delete(optimistic);
  if (!result) {
    if (c) {
      if (holder && holder.decision === optimistic) holder.decision = prior;
      if (was.changing) decisionChanging[id] = true;
      if (was.docChanging) DOC_CARD.changing[id] = true;
      if (was.expanded) cardExpanded[id] = true;
      // Kept as state: the document redraws its card after this returns.
      decisionHint[id] = { msg: 'Failed to send — try again.', error: true };
      renderDrawer();
      sendCommentCountsToFrame();
      updateSendState();
    }
    setDecisionFeedback(root, id, 'Failed to send — try again.', true);
    setDecisionButtonsDisabled(root, id, false);
    return null;
  }
  delete decisionChanging[id];
  delete DOC_CARD.changing[id];
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
// UI-15: the comment sent with an earlier option answer, so changing the
// option without typing a new comment keeps it. A word answer (comment,
// changes) is the answer itself, not a comment beside it.
function earlierAnswerComment(c) {
  const d = decisionAnswer(c);
  if (!d || !d.text) return null;
  if (d.verdict === 'accept' || d.verdict === 'reject') return d.text;
  if (d.verdict === 'select' || (d.verdict === 'comment' && /^Selected: /.test(d.text))) {
    const at = d.text.indexOf('\n\n');
    return at === -1 ? null : (d.text.slice(at + 2).trim() || null);
  }
  return null;
}
function pickOption(root, btn) {
  const id = btn.dataset.id;
  const action = btn.dataset.decisionAction;
  const c = findCommentById(id);
  // A new choice on an answered card keeps the note that went with the old
  // one (a word answer included); the add-note box is left as it is.
  if (c && decisionAnswer(c)) {
    const note = [decisionNote(c), decisionCommentText(root, id)].filter(Boolean).join('\n\n') || null;
    if (action === 'accept' || action === 'reject') return submitDecision(root, id, action, note);
    if (action === 'comment' || action === 'changes') {
      if (!note) { setDecisionFeedback(root, id, 'Write your answer in the box, then pick it again.', false); return null; }
      return submitDecision(root, id, action, note);
    }
    const label = btn.dataset.optionLabel || btn.dataset.optionId || 'option';
    return submitDecision(root, id, 'select', label + (note ? '\n\n' + note : ''), btn.dataset.optionId);
  }
  const note = decisionCommentText(root, id) ||
    (action === 'comment' || action === 'changes' ? null : earlierAnswerComment(c));
  if (action === 'accept' || action === 'reject') return submitDecision(root, id, action, note);
  if (action === 'comment' || action === 'changes') {
    if (!note) {
      // Kept in state (not only in the DOM) so a re-render that lands right
      // after — e.g. the excerpts refresh that follows an earlier verdict —
      // draws the same hint again instead of wiping it.
      decisionHint[id] = action === 'changes'
        ? { ph: 'What needs to change…', msg: 'Say what needs to change in the box, then pick it again.' }
        : { ph: 'Answer in your own words…', msg: 'Write your answer in the box, then pick it again.' };
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
  // Custom option → `select` naming the choice.
  const label = btn.dataset.optionLabel || btn.dataset.optionId || 'option';
  const text = label + (note ? '\n\n' + note : '');
  return submitDecision(root, id, 'select', text, btn.dataset.optionId);
}

// `scope` is where the card's boxes and messages live: the rail list, or the
// document the card is drawn in.
function wireDecisionActions(root, scope = root) {
  root.querySelectorAll('[data-options] > [data-decision-action]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    pickOption(scope, btn);
  }));
  const toggleRegion = (btn, open) => {
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    const region = btn.ownerDocument.getElementById(btn.getAttribute('aria-controls'));
    if (region) region.hidden = !open;
    return region;
  };
  root.querySelectorAll('[data-decision-action="evidence-toggle"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const s = surfaceOf(btn);
    const id = btn.dataset.id;
    const open = !s.evOpen[id];
    s.evOpen[id] = open;
    const region = toggleRegion(btn, open);
    // Evidence is built when it is first opened.
    if (open && region && !region.firstElementChild) {
      const c = findCommentById(id);
      region.innerHTML = c ? withSurface(s, () => evidenceItemsHtml(c, evidenceList(c.decision_request || {}))) : '';
      wireDecisionActions(region, scope);
    }
    if (open) syncExcerptClamps(region);
  }));
  root.querySelectorAll('[data-decision-action="evidence-preview"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const s = surfaceOf(btn);
    const open = !s.evItemOpen[btn.dataset.key];
    s.evItemOpen[btn.dataset.key] = open;
    const region = toggleRegion(btn, open);
    if (open) syncExcerptClamps(region);
  }));
  root.querySelectorAll('[data-decision-action="excerpt-more"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const s = surfaceOf(btn);
    const open = !s.excerptOpen[btn.dataset.key];
    s.excerptOpen[btn.dataset.key] = open;
    const box = btn.closest('.decision-excerpt, .annotate-excerpt');
    if (box) box.classList.toggle('is-open', open);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    btn.textContent = open ? 'Show less' : 'Show more';
    if (box && box.parentElement) syncExcerptClamps(box.parentElement);
  }));
  root.querySelectorAll('[data-decision-action="evidence"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const id = btn.dataset.id;
    if (surfaceOf(btn).doc) scrollToAnchorInFrame(btn.dataset.anchor, null, { commentId: id, n: NUM_MAP[id] || 0, from: 'strip' });
    else goToEvidence(btn.dataset.anchor, id);
  }));
  root.querySelectorAll('[data-decision-say-ta]').forEach(ta => ta.addEventListener('input', () => {
    setDraft('say:' + ta.dataset.decisionSayTa, ta.value || '');
    syncSayHint(ta);
    mirrorSay(ta.dataset.decisionSayTa, ta);
    updateSendState();
  }));
  root.querySelectorAll('[data-decision-action="change"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (surfaceOf(btn).doc) { DOC_CARD.changing[btn.dataset.id] = true; return redrawCard(btn); }
    decisionChanging[btn.dataset.id] = true;
    highlightedCommentId = btn.dataset.id;
    renderDrawer();
    updateSendState();
    const ta = document.querySelector('#comment-list [data-comment-id="' + cssEsc(btn.dataset.id) + '"]');
    if (ta) ta.scrollIntoView({ block: 'nearest' });
  }));
  root.querySelectorAll('[data-decision-action="later"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    setAnswerLater(btn.dataset.id, btn.dataset.later === '1');
  }));
  root.querySelectorAll('[data-decision-action="cancel-change"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    delete surfaceOf(btn).changing[btn.dataset.id];
    delete decisionHint[btn.dataset.id];
    redrawCard(btn);
    updateSendState();
  }));
}
// A card's box shows the same draft in the rail, the Send summary and the
// document; typing in one fills the others (never the box being typed in).
function frameDoc() {
  try { return document.getElementById('content-frame').contentDocument; } catch { return null; }
}
function mirrorSay(id, from) {
  const text = DRAFTS['say:' + id] || '';
  for (const doc of [document, frameDoc()]) {
    if (!doc) continue;
    doc.querySelectorAll('[data-decision-say-ta="' + cssEsc(id) + '"]').forEach(ta => {
      if (ta === from || ta === doc.activeElement || ta.value === text) return;
      ta.value = text;
      syncSayHint(ta);
    });
  }
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

// v9o: the composer's text is the 'pop' draft, saved with where it goes on
// every keystroke. A click elsewhere in the document, a re-render, a new
// version, a restart or a reload never empties it: until Save succeeds or
// Cancel is pressed, any click that would open a composer opens this one.
function popDraft() {
  const d = DRAFTS.pop;
  return d && typeof d === 'object' && d.text ? d : null;
}
function openPopoverForCreate(anchorId, anchorLabel, x, y, target) {
  if (pageReadOnly()) return;
  if (!IDENTITY) {
    updateAuthorIndicator();
    return;
  }
  const pop = document.getElementById('popover');
  const ta = document.getElementById('pop-ta');
  const kept = popDraft();
  if (kept && pop.classList.contains('vis')) { ta.focus(); return; }
  if (kept) ({ anchorId, anchorLabel, target } = kept);
  pendingAnchor = { anchorId, anchorLabel, target: target || null, version: (kept && kept.version) || CURRENT_VERSION };
  editingCommentId = null;
  const node = document.getElementById('pop-node-name');
  const quote = target && target.selected_quote;
  node.classList.toggle('unified-selection-title', !!quote);
  node.textContent = quote ? '“' + quote + '”' : [imageTag(target), anchorLabel || anchorId].filter(Boolean).join(' · ');
  node.title = node.textContent;
  ta.value = kept ? kept.text : '';
  document.getElementById('pop-err').textContent = '';
  positionPopover(x, y);
  pop.classList.add('vis');
  setMobileBackdropVisible(true);
  ta.focus();
}
function keepPopDraft() {
  const text = document.getElementById('pop-ta').value;
  setDraft('pop', pendingAnchor && text.trim() ? Object.assign({}, pendingAnchor, { text }) : '');
}
function discardPopover() {
  setDraft('pop', '');
  closePopover();
}
// After a reload or a restart the composer that held unsent text is open
// again, on its document.
function reopenPopDraft() {
  const d = popDraft();
  if (!d || DOC !== VIEW_DOC || document.getElementById('popover').classList.contains('vis')) return;
  openPopoverForCreate(d.anchorId, d.anchorLabel, window.innerWidth / 2, window.innerHeight / 3, d.target);
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
// v9o: the card shows at once, marked Sending…, and the composer is free for
// the next note; the text waits as the 'sending:pop' draft until the server
// has it. A failed post takes the card away and opens the composer again
// with the text (ahead of anything typed since) and the error.
async function savePopover() {
  if (!IDENTITY) return;
  const text = document.getElementById('pop-ta').value.trim();
  if (!text || !pendingAnchor) return;
  const at = pendingAnchor;
  const sent = Object.assign({}, at, { text });
  setDraft('sending:pop', sent);
  setDraft('pop', '');
  closePopover();
  const temp = addPendingComment(at.anchorId, {
    anchor_label: at.anchorLabel, text, version: at.version || CURRENT_VERSION, target: at.target || null,
    ...(DOC === 'plans' ? { category: 'plans', doc: 'plan:' + PLAN_ID } : {}),
  });
  setActiveTab('feedback');
  focusSidebarCard(temp.id);
  let created = await settlePending(apiCreateComment(at.anchorId, at.anchorLabel, text, at.version || CURRENT_VERSION, at.target));
  dropPendingComment(temp);
  // An answer lost on the way back: the server may have the comment anyway.
  if (!created && await loadStore()) created = sentLanded('pop', sent);
  setDraft('sending:pop', '');
  if (!created) {
    setDraft('pop', mergeDraft(DRAFTS.pop, sent));
    closePopover();
    renderAll();
    openPopoverForCreate(at.anchorId, at.anchorLabel, window.innerWidth / 2, window.innerHeight / 3, at.target);
    document.getElementById('pop-err').textContent = 'Not saved — the server did not answer. Your text is still here; try again.';
    return;
  }
  await refreshStore();
  // The author has obviously "read" their own new comment.
  markReadAfterAction(created.id);
  setActiveTab('feedback');
  focusSidebarCard(created.id);
}

// ── Optimistic posts (v9o) ──────────────────────────────────────────
// A comment, reply or answer is drawn the moment it is posted, marked
// Sending…. The 8 s poll waits until the server has answered, and any store
// read in between (a poll already on its way, another action's refresh)
// gets each one again from pendingEdits, so it never leaves the screen.
let pendingPosts = 0;
async function settlePending(promise) {
  pendingPosts++;
  try { return await promise; } finally { pendingPosts--; }
}
// The comment as the store holds it (findCommentById gives a copy).
function storedComment(id) {
  for (const area of [STORE.anchors, STORE.archived]) {
    for (const items of Object.values(area || {})) for (const c of items) if (c.id === id) return c;
  }
  return null;
}
function addPendingEdit(key, apply) {
  pendingEdits.set(key, apply);
  apply();
}
function addPendingComment(anchorId, fields) {
  const c = Object.assign({
    id: 'pending-' + Math.random().toString(36).slice(2), anchor_id: anchorId, status: 'open', pending: true,
    author: AUTHOR, author_name: IDENTITY && IDENTITY.name, author_email: IDENTITY && IDENTITY.email,
    created_at: new Date().toISOString(), replies: [],
  }, fields);
  addPendingEdit(c, () => {
    const list = STORE.anchors[anchorId] = STORE.anchors[anchorId] || [];
    if (!list.includes(c)) list.push(c);
  });
  computeNumbers();
  return c;
}
// A post whose text waits as a 'sending:' draft ('sending:pop' for the
// composer, 'sending:<comment id>' for a reply): what the server has of it.
function sentLanded(key, sent) {
  const same = x => !x.pending && String(x.text || '').trim() === String(key === 'pop' ? sent.text : sent).trim();
  if (key === 'pop') return (STORE.anchors[sent.anchorId] || []).find(same) || null;
  const c = findCommentById(key);
  return (c && (c.replies || []).find(same)) || null;
}
// Text that did not reach the server goes back ahead of what was typed since.
function mergeDraft(now, sent) {
  if (typeof sent === 'object') return now && (now.text || '').trim() ? Object.assign({}, sent, { text: sent.text + '\n\n' + now.text }) : sent;
  return now && now.trim() ? sent + '\n\n' + now : sent;
}
function dropPendingComment(c) {
  pendingEdits.delete(c);
  const list = STORE.anchors[c.anchor_id];
  const i = list ? list.indexOf(c) : -1;
  if (i !== -1) list.splice(i, 1);
  if (list && !list.length) delete STORE.anchors[c.anchor_id];
  computeNumbers();
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
  highlightedCommentId = commentId;
  // The card must be visible: Feedback tab (before the overlay opens, so
  // focus lands on it), and its section open.
  if (activeTab !== 'feedback') setActiveTab('feedback');
  if (isMobileLayout()) setMobileSheetOpen(true); // pin/card focus needs the overlay open, not just scrolled-to
  else if (isDrawerCollapsed()) setDrawerCollapsed(false); // inline: rail must be expanded
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
    setDraft('gf', '');
    setGeneralFeedbackOpen(false);
    updateSendState();
  });
  // T11: the general-feedback draft persists (one per document, v9o)
  document.getElementById('gf-ta').addEventListener('input', (e) => {
    setDraft('gf', e.target.value || '');
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
  syncRailDialog();
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
// The edge strip mirrors the rail's tabs: which are shown, their names and
// (B1) the same counts as the tab badges, whoever set them (the shell for
// Review and Plans, app.js for the other tabs).
function syncRailStrip() {
  document.querySelectorAll('#rail-strip [data-rail-open]').forEach(btn => {
    const tab = document.getElementById('tab-' + btn.dataset.railOpen);
    const label = Array.from(tab.childNodes).filter(n => n.nodeType === Node.TEXT_NODE).map(n => n.textContent).join('').trim();
    const n = tab.querySelector('.tab-n');
    const count = n && !n.hidden ? n.textContent : '';
    const badge = btn.querySelector('.rail-strip-n');
    if (badge) { badge.textContent = count; badge.hidden = !count; }
    btn.hidden = tab.hidden;
    btn.title = label + (count ? ' — ' + count + ' need you' : '');
    btn.setAttribute('aria-label', btn.title);
  });
}
// Open the rail (on a tab, if given): inline it expands, compact it opens
// the overlay. Focus moves into the rail either way.
function openRail(tab) {
  if (tab) setActiveTab(tab);
  if (isMobileLayout()) setMobileSheetOpen(true);
  else { setDrawerCollapsed(false); focusRailTab(); }
}
function wireRailCollapse() {
  // In the compact layout the rail is an overlay, not a collapsible column —
  // its close control (×) closes the overlay; the panel toggle collapses
  // the inline rail, so the two mechanisms never both apply at once.
  document.getElementById('drawer-collapse').addEventListener('click', () => {
    if (isMobileLayout()) { setMobileSheetOpen(false); return; }
    setDrawerCollapsed(true);
    document.getElementById('drawer-strip').focus();
  });
  document.getElementById('drawer-strip').addEventListener('click', () => openRail());
  document.querySelectorAll('#rail-strip [data-rail-open]').forEach(btn => btn.addEventListener('click', () => openRail(btn.dataset.railOpen)));
  new MutationObserver(syncRailStrip).observe(document.getElementById('drawer-tabs'), { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['hidden'] });
  syncRailStrip();
  try {
    // A collapsed-rail preference saved from a prior wide session must not
    // apply in the compact layout: there the overlay is owned entirely by
    // body.is-mobile-sheet-open, never by .collapsed.
    if (!isMobileLayout() && localStorage.getItem('annotate:drawerCollapsed') === '1') setDrawerCollapsed(true);
  } catch {}
  syncRailDialog();
}

// ── Compact-only chrome: the rail overlay, dialog backdrop ───────────
function wireMobileChrome() {
  // U-12: the overlay closes with ×, a tap outside it, Escape (onShellKey)
  // or a swipe toward the edge.
  document.getElementById('unified-sheet-close').addEventListener('click', () => setMobileSheetOpen(false));
  document.getElementById('unified-sheet-backdrop').addEventListener('click', () => setMobileSheetOpen(false));
  const hdr = document.querySelector('.drawer-hdr');
  let touchX = null;
  hdr.addEventListener('touchstart', e => { touchX = e.touches[0] ? e.touches[0].clientX : null; }, { passive: true });
  hdr.addEventListener('touchend', e => {
    if (touchX !== null && e.changedTouches[0].clientX - touchX > 65) setMobileSheetOpen(false);
    touchX = null;
  }, { passive: true });
  // Crossing the breakpoint (a resize, a tablet turned): the open overlay
  // stays open as the inline rail, even if it was collapsed there before;
  // the inline rail becomes the closed overlay, and focus inside it moves to
  // the edge strip rather than being lost.
  window.matchMedia('(max-width: 1023px), (max-height: 480px)').addEventListener('change', () => {
    if (!isMobileLayout() && isMobileSheetOpen()) {
      document.body.classList.remove('is-mobile-sheet-open');
      railOpener = null;
      if (isDrawerCollapsed()) setDrawerCollapsed(false);
      // The collapsed rail's style change already dropped focus from the dialog.
      if (document.activeElement === document.body) focusRailTab();
    } else if (isMobileLayout() && document.getElementById('drawer').contains(document.activeElement)) {
      document.getElementById('drawer-strip').focus({ preventScroll: true });
    }
    syncRailDialog();
  });
  // APG modal: Tab and Shift+Tab stay inside the open overlay (and the Send
  // bar it owns). Another dialog on top (Send summary, popovers) keeps its own.
  document.addEventListener('keydown', e => {
    if (e.key !== 'Tab' || !isRailModal()) return;
    const scope = [document.getElementById('drawer'), document.getElementById('round-bar')];
    const active = document.activeElement;
    if (active !== document.body && !scope.some(el => el.contains(active))) return;
    const items = scope.flatMap(el => Array.from(el.querySelectorAll('button, [href], input, select, textarea, summary, [tabindex]:not([tabindex="-1"])')))
      .filter(el => el.tabIndex >= 0 && !el.disabled && el.getClientRects().length);
    if (!items.length) return;
    // Moved by hand throughout: the edge strip sits between the two in the DOM.
    const i = items.indexOf(active), n = items.length;
    e.preventDefault();
    items[i === -1 ? (e.shiftKey ? n - 1 : 0) : (i + (e.shiftKey ? n - 1 : 1)) % n].focus();
  });
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
  // The server's _comment_needs_push: a pending reopen goes with the round.
  if (c.round_pending || (c.decision && c.decision.round_pending)) return false;
  if (c.status !== 'open' && !(c.status === 'user_confirmed' && (c.replies || []).some(r => !isAgentAuthor(r.author) && noteUnsent(c, r)))) return false;
  const flaggedAt = c.flagged_at ? new Date(c.flagged_at).getTime() : 0;
  let latest = !isAgentAuthor(c.author) && c.created_at ? new Date(c.created_at).getTime() : 0;
  if (c.edited_at && !isAgentAuthor(c.edited_by || c.author)) latest = Math.max(latest, new Date(c.edited_at).getTime());
  for (const r of (c.replies || [])) {
    if (!isAgentAuthor(r.author)) latest = Math.max(latest, new Date(r.ts).getTime());
  }
  if (c.decision && !isAgentAuthor(c.decision.by)) latest = Math.max(latest, new Date(c.decision.ts).getTime());
  if ((c.replies || []).some(r => r.sent_at === null && !isAgentAuthor(r.author))) return true;
  if (!latest) return false;
  if (!c.flagged_for_session) return true;
  return latest > flaggedAt;
}
// "x of n decided" counts the rail's Needs you set (the strip badge's filter)
// plus what the reviewer has answered there and not sent yet. A card answered
// in an earlier round and waiting on the agent no longer needs the reviewer,
// so it is not counted (w6e.16).
function answersNeed(c) {
  return sectionOf(c) === 'ready' &&
    (hasDecisionRequest(c) || (c.replies || []).some(r => isAgentAuthor(r.author)));
}
function roundStats() {
  let pending = 0, decided = 0, total = 0, undecided = 0;
  for (const c of flattenAll(false)) {
    if (!inScope(c)) continue;
    if (sectionOf(c) === 'needs') { total++; undecided++; }
    else if (isSetAside(c) && hasSayDraft(c)) total++; // answered in words at this Send
    else if (answersNeed(c)) { total++; decided++; }
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
const sumRestOpen = new Set(); // documents whose 'Not in this Send' group is open
function summarySentence() {
  const plan = sendPlan();
  const q = sendables();
  // One plain phrase per document; app.js joins them into the dialog's one line.
  const roundN = plan.round.length + plan.answers.length;
  const parts = [];
  if (roundN) parts.push(roundN + (roundN === 1 ? ' answer' : ' answers'));
  if (plan.push.length) parts.push(plan.push.length + (plan.push.length === 1 ? ' comment' : ' comments'));
  if (q.gf) parts.push('general feedback');
  return parts.length > 1 ? parts.slice(0, -1).join(', ') + ' and ' + parts[parts.length - 1] : (parts[0] || '');
}
function summaryWarning() {
  const plan = sendPlan();
  const roundN = plan.round.length + plan.answers.length;
  const undecided = flattenAll(false).filter(c => hasDecisionRequest(c) && !decisionAnswer(c) && !hasSayDraft(c) && !isSetAside(c)).length;
  if (undecided > 0 && roundN > 0) {
    return undecided + (undecided === 1 ? ' question is' : ' questions are') + ' still unanswered; the agent will see ' + (undecided === 1 ? 'it' : 'them') + ' as open.';
  }
  return '';
}
function renderSummaryInto(list, editable) {
  const plan = sendPlan();
  const byNum = (a, b) => (NUM_MAP[a.id] || 0) - (NUM_MAP[b.id] || 0);
  const inSend = new Set([...plan.round, ...plan.answers, ...plan.push].map(c => c.id));
  // Not in this Send: newest first, by when it was sent or answered; card number when neither (Chang 2026-10-31).
  const restTs = c => Math.max(Date.parse(c.flagged_at) || 0, Date.parse(c.decision && c.decision.ts) || 0);
  const rest = flattenAll(false).filter(c => hasDecisionRequest(c) && !inSend.has(c.id))
    .sort((a, b) => restTs(b) - restTs(a) || byNum(b, a));
  const doc = DOC;
  const decisionRow = (c) => {
    const num = NUM_MAP[c.id];
    const answered = !!decisionAnswer(c);
    const draft = hasSayDraft(c);
    const missing = !answered && !draft;
    const editing = editable && sumEditing === c.id;
    const sent = answered && !draft && !isRoundPending(c);
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
    // The answer under its question, full length; a picked option and
    // the note typed with it read as label + paragraph.
    let ans;
    if (draft) ans = `<p class="rl-note">${esc(sayDraft(c))}</p>`;
    else if (!answered) ans = '<span class="rl-none">Not answered</span>';
    else {
      const t = answerLabel(c).text;
      const d = decisionAnswer(c);
      const cut = t.indexOf('\n\n');
      const label = d.verdict === 'select' ? (cut === -1 ? t : t.slice(0, cut)) : '';
      const note = d.verdict === 'select' ? (cut === -1 ? '' : t.slice(cut + 2).trim()) : t;
      ans = (label ? `<span class="rl-label">${esc(label)}</span>` : '') + (note ? `<p class="rl-note">${esc(note)}</p>` : '');
      if (sent) ans += `<span class="rl-sent">${deliveryHtml(c.delivery_id)}</span>`;
    }
    return `<div class="sum-row rl-row${missing ? ' is-missing' : ''}${sent ? ' is-sent' : ''}" data-sum-id="${escAttr(c.id)}">
      <div class="rl-k">${num ? `<span class="rl-num">#${num}</span>` : '<span class="rl-num"></span>'}<span class="rl-q">${esc(displayPrompt(c))}</span></div>
      <div class="rl-a">${ans}</div>
      ${pencil}
      ${edit}
    </div>`;
  };
  const commentRow = (c) => {
    if (hasDecisionRequest(c) && !strandedSay(c)) return decisionRow(c);
    const num = NUM_MAP[c.id];
    const last = (c.replies || []).filter(r => !isAgentAuthor(r.author)).slice(-1)[0];
    const text = strandedSay(c) ? sayDraft(c) : last ? last.text : c.text;
    const key = strandedSay(c) || last ? (isAgentAuthor(c.author) ? firstLine(c.text) : 'Reply') : 'Comment';
    return `<div class="sum-row rl-row" data-sum-id="${escAttr(c.id)}">
      <div class="rl-k"><span class="rl-num">${num ? '#' + num : ''}</span><span class="rl-q">${esc(key)}</span></div>
      <div class="rl-a"><p class="rl-note">${esc(text)}</p></div>
    </div>`;
  };
  const group = (label, n) => `<div class="sum-group">${label}${n == null ? '' : ` <span class="badge badge-sm badge-ghost">${n}</span>`}</div>`;
  let html = '';
  const verdictRows = [...plan.round, ...plan.answers].sort(byNum);
  if (verdictRows.length) html += group('Answers', verdictRows.length) + verdictRows.map(decisionRow).join('');
  if (plan.push.length) html += group('Comments', plan.push.length) + plan.push.slice().sort(byNum).map(commentRow).join('');
  // General feedback for the document on screen is an open box at the top
  // of the dialog, no button to reveal it (Chang 2026-10-31). Another
  // document's stays a row whose Edit opens that document's tab.
  const gf = gfDraft();
  const gfHost = editable ? document.getElementById('sum-gf-host') : null;
  if (gfHost) {
    gfHost.innerHTML = `<label class="rl-gf"><span class="rl-gf-lbl">General feedback</span>
      <textarea class="textarea sum-gf-ta rl-gf-ta" id="sum-gf-ta" rows="2" placeholder="Anything else for the agent? (optional)"></textarea></label>`;
  } else if (gf) {
    html += group('General feedback', 1);
    html += `<div class="sum-row" data-sum-id="gf-${doc}">
      <div class="sum-main">
        <span class="sum-q">“${esc(firstLine(gf))}”</span>
        <button type="button" class="btn btn-xs" data-sum-edit="gf" data-sum-doc="${doc}" aria-label="Edit general feedback">Edit</button>
      </div>
    </div>`;
  }
  // Collapsed by default and built only when opened, like the rail
  // sections (Chang 2026-10-31: "no need to constantly show this or even
  // load it"). The header keeps unanswered ones discoverable.
  if (rest.length) {
    const open = sumRestOpen.has(doc) || rest.some(c => c.id === sumEditing);
    const missing = rest.filter(c => !decisionAnswer(c) && !hasSayDraft(c)).length;
    html += `<button type="button" class="sec-hdr sum-group sum-rest-hdr" data-sum-rest="${doc}" aria-expanded="${open ? 'true' : 'false'}">${ico('chevDown')}<span>Not in this Send</span><span class="badge badge-sm badge-ghost">${rest.length}</span>${missing ? `<span class="sum-rest-missing">· ${missing} not answered</span>` : ''}</button>`;
    if (open) html += rest.map(decisionRow).join('');
  }
  list.innerHTML = html;
  list.querySelectorAll('[data-sum-rest]').forEach(btn => btn.addEventListener('click', () => {
    if (!sumRestOpen.delete(btn.dataset.sumRest)) sumRestOpen.add(btn.dataset.sumRest);
    renderSummary();
  }));

  // Another document's rows: the pencil opens that document's tab, where
  // the same summary opens with that row in edit mode.
  if (!editable) {
    list.querySelectorAll('[data-sum-edit]').forEach(btn => btn.addEventListener('click', () => {
      if (window.AA) window.AA.go({ view: btn.dataset.sumDoc, send: '1', sumedit: btn.dataset.sumEdit });
    }));
    return;
  }
  const gta = gfHost.querySelector('#sum-gf-ta');
  // The open box grows with its text up to its CSS max-height, then scrolls.
  const grow = () => { gta.style.height = 'auto'; gta.style.height = (gta.scrollHeight + 2) + 'px'; };
  if (gta) {
    gta.value = DRAFTS.gf || '';
    gta.addEventListener('input', () => {
      setDraft('gf', gta.value || '');
      const box = document.getElementById('gf-ta');
      if (box) box.value = gta.value;
      renderGeneralFeedback();
      updateSendState();
      syncSummaryCounts();
      grow();
    });
    // Not focused on open: that would raise the iPad keyboard.
    requestAnimationFrame(grow);
    if (sumEditing === 'gf') gta.focus(); // Edit from another tab
  }
  list.querySelectorAll('[data-decision-say-ta]').forEach(ta => {
    ta.value = DRAFTS['say:' + ta.dataset.decisionSayTa] || '';
    ta.addEventListener('input', () => {
      setDraft('say:' + ta.dataset.decisionSayTa, ta.value || '');
      mirrorSay(ta.dataset.decisionSayTa, ta);
      updateSendState();
    });
  });
  list.querySelectorAll('[data-sum-edit]').forEach(btn => btn.addEventListener('click', () => {
    sumEditing = sumEditing === btn.dataset.sumEdit ? null : btn.dataset.sumEdit;
    renderSummary();
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
    const answer = hasSayDraft(c) ? sayDraft(c) : decisionAnswer(c) ? answerLabel(c).text : '';
    // UI-2: `kind` says which call carries the line (the round or the push)
    // and `id` lets a failed draft drop its line; neither goes to the server.
    return { label: '#' + (NUM_MAP[c.id] || '') + ' · ' + label, answer, kind: p.push.includes(c) ? 'push' : 'round', id: c.id };
  });
  if (gfDraft()) items.push({ label: 'General feedback', answer: gfDraft(), kind: 'push', id: 'gf:' + DOC });
  // A Plans line names its plan (History lists it under that plan only).
  if (DOC === 'plans') items.forEach(it => { it.doc = 'plan:' + PLAN_ID; });
  return items;
}
// A document's part of one Send (2.20's order): comment-box text on an
// unanswered card becomes its answer, general feedback becomes its
// general:* item. No UI here; app/send.js reports it.
async function prepareDocCore() {
  const items = sendItems();
  let ok = true;
  const failed = [];
  for (const c of flattenAll(false).filter(hasSayDraft)) {
    const r = await apiDecision(c.id, 'comment', sayDraft(c));
    if (r) { clearSayDraft(c.id); delete decisionChanging[c.id]; } else { ok = false; failed.push(c.id); }
  }
  for (const c of flattenAll(false).filter(strandedSay)) {
    if (await apiReply(c.id, sayDraft(c))) clearSayDraft(c.id); else { ok = false; failed.push(c.id); }
  }
  const gf = gfDraft();
  if (gf) {
    const created = IDENTITY ? await apiCreateComment('general:' + CURRENT_VERSION, 'General feedback', gf, CURRENT_VERSION) : null;
    if (created) setDraft('gf', ''); else { ok = false; failed.push('gf:' + DOC); }
  }
  if (DOC === VIEW_DOC) {
    const g = document.getElementById('gf-ta');
    if (g) g.value = DRAFTS.gf || '';
  }
  return { ok, items, failed };
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
// reopens, Library revisions across every tab and the open comments with new
// activity), or, with nothing round-pending, ONE push of those comments.
// `alsoPending` says another tab has round-pending
// work the comment store does not show (Library revisions).
// `receipt`: the Send summary's lines, kept by the server for History.
// UI-2: each call carries only its own receipt lines (the round's verdicts,
// reopens and edits; the push's comments), both under one send_id, so a
// failed call leaves its lines out of History. Returns the lines actually
// sent and the lines that were not (they stay pending, as their drafts,
// verdicts and comments are untouched).
async function submitPage(alsoPending, receipt) {
  let sentCount = 0, delivered = false, last = null;
  const lines = Array.isArray(receipt) ? receipt : [];
  const sendId = lines.length ? newSendId() : null;
  const failedIds = new Set();
  for (const doc of DOCS) {
    const r = await withDocAsync(doc, prepareDocCore);
    (r.failed || []).forEach(id => failedIds.add(doc + '|' + id));
  }
  const failed = lines.filter(it => it.id && failedIds.has(it.cat + '|' + it.id));
  const sent = [];
  // Library lines carry no kind: its comments read "Comment: …".
  const kindOf = (it) => it.kind || (/^Comment: /.test(it.answer || '') ? 'push' : 'round');
  let roundLines = lines.filter(it => !failed.includes(it) && kindOf(it) === 'round');
  let pushLines = lines.filter(it => !failed.includes(it) && kindOf(it) === 'push');
  await loadStore();
  const doRound = pageRoundPending() > 0 || alsoPending;
  // The round carries open comments with new activity (general feedback,
  // replies), so a Send wakes the owner once; push only when there is no round.
  let doPush = !doRound && flattenStore(false).some(needsPush);
  // A line whose own call is not needed goes with the other call.
  if (!doRound) { pushLines = roundLines.concat(pushLines); roundLines = []; }
  if (!doPush) { roundLines = roundLines.concat(pushLines); pushLines = []; }
  if (doRound) {
    const j = await withDocAsync('review', () => apiRoundSubmit(null, receiptPayload(roundLines, sendId)));
    if (j) { last = j; sentCount += (j.comment_count || 0) + (j.edit_count || 0); delivered = delivered || j.delivery === 'active_monitor'; sent.push(...roundLines); } else failed.push(...roundLines);
    await loadStore();
    // Activity arriving during this Send waits for the next manual Send.
    doPush = false;
  }
  if (doPush) {
    const j = await apiPushAll(receiptPayload(pushLines, sendId));
    if (j) { last = j; sentCount += j.flagged_count || 0; delivered = delivered || j.delivery === 'active_monitor'; sent.push(...pushLines); } else failed.push(...pushLines);
  }
  if (!doRound && !doPush) sent.push(...roundLines);
  if (last) {
    SESSION_MONITOR = { active: delivered, monitor_count: last.monitor_count || 0, delivery: last.delivery || 'queued', owner: last.monitor_owner || null };
  }
  historyDirty = true;
  await Promise.all([loadStore(), loadReadState()]);
  loadHistory();
  const order = (it) => lines.indexOf(it);
  sent.sort((a, b) => order(a) - order(b));
  failed.sort((a, b) => order(a) - order(b));
  if (last) {
    // Legacy monitor counts do not prove that Orca accepted the prompt.
    delivered = false;
    try {
      const response = await fetch(apiUrl('./api/delivery'), { cache: 'no-store' });
      const data = await response.json();
      SUMMARY_DELIVERY = data;
      delivered = data.latest?.id === last.delivery_id && data.latest.delivered === true;
    } catch {}
  }
  return { ok: !failed.length, sent, failed, sentCount, delivered, automatic: true, any: !!last, send_id: sendId, delivery_id: last?.delivery_id };
}
function newSendId() {
  return crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 12);
}
function receiptPayload(receipt, id) {
  if (!id) return {};
  if (!Array.isArray(receipt) || !receipt.length) return { send_id: id };
  return {
    send_id: id,
    receipt: receipt.slice(0, 200).map(it => {
      const line = { cat: it.cat, label: String(it.label || '—').slice(0, 300) };
      if (it.answer) line.answer = String(it.answer).slice(0, 600);
      if (it.doc) line.doc = it.doc;
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
//                   {type:'annotate:excerpts', version, excerpts: {anchorId: {text, name, card} | {missing}}}
//                   {type:'annotate:back-to-card', commentId}  ("Back to #N" clicked on an evidence target)
// Shell -> content: {type:'annotate:scroll-to', anchorId, target, back: {commentId, n, from} | null}
//                   {type:'annotate:comment-counts', counts: {anchorId: n},
//                    pins: {anchorId: [{id, n, unread, target, decision,
//                                        decisionRequest: {evidence}, decisionVerdict, changing}]}}
// A pin with decisionRequest gets a question card in the document, built by
// stripCard (the rail's builder); its actions run here, not in the frame.
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
      loadSeen().then(() => renderVersionRail());
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
      ANCHOR_ORDER = data.anchorOrder || {};
      renderDrawer();
    } else if (data.type === 'annotate:back-to-card') {
      // "Back to #N" on an evidence target the rail card sent the reader to.
      const c = data.commentId ? findCommentById(data.commentId) : null;
      if (c) focusSidebarCard(c.id);
    } else if (data.type === 'annotate:key') {
      onShellKey({ key: String(data.key || ''), metaKey: !!data.meta, ctrlKey: !!data.ctrl, shiftKey: !!data.shift, altKey: false,
        target: document.body, preventDefault() {} });
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
          // The document draws a card for these (stripCard builds it); the
          // evidence says where it goes. Sent after the answer too, so the
          // card keeps its place with your choice and notes on it.
          decisionRequest: hasDecisionRequest && !pageReadOnly()
            ? { evidence: Array.isArray(c.decision_request.evidence) ? c.decision_request.evidence : null } : null,
          decisionVerdict: decisionResolved ? c.decision.verdict : null,
          changing: !!DOC_CARD.changing[c.id],
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
  const board = boardLink();
  postToFrame({ type: 'annotate:comment-counts', counts, pins, cardStates,
    board: board ? { url: board.url, prefix: PROJECT.board.prefix } : null });
}


function scrollToAnchorInFrame(anchorId, target, back) {
  postToFrame({ type: 'annotate:scroll-to', anchorId, target: target || null, back: back || null });
}

// ── Wire popover buttons ─────────────────────────────────────────────
function wirePopover() {
  // Close (×, Esc) keeps the text for the next composer; Cancel discards it.
  document.getElementById('pop-close').addEventListener('click', closePopover);
  document.getElementById('pop-cancel').addEventListener('click', discardPopover);
  document.getElementById('pop-save').addEventListener('click', savePopover);
  document.getElementById('pop-ta').addEventListener('input', keepPopDraft);
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
      // The open rail overlay closes last: only when nothing on top of it was open.
      const layered = document.getElementById('popover').classList.contains('vis') || document.getElementById('pin-popover').classList.contains('vis') || isRoundConfirmOpen() || openMenuId;
      if (!layered && isRailModal()) setMobileSheetOpen(false);
      closePopover(); closePinPopover(); cancelRepin(); closeRoundConfirm();
      if (openMenuId) { openMenuId = null; document.querySelectorAll('.citem-menu').forEach(m => { m.hidden = true; }); }
      const wp = document.getElementById('who-panel'); if (wp) wp.hidden = true;
    }
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      const t = e.target;
      if (isRoundConfirmOpen()) {
        e.preventDefault(); // Only the Send button submits the round.
      } else if (document.getElementById('popover').classList.contains('vis')) {
        savePopover();
      } else if (t.dataset && t.dataset.submit) {
        // Library and Findings boxes name their own Save button: ⌘↵ saves
        // the typed text there, like the reply box, instead of opening Send.
        e.preventDefault();
        const btn = document.querySelector(t.dataset.submit);
        if (btn && !btn.disabled) btn.click();
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
    META: { current: null, history: [], content_stamps: {} }, SEEN: {}, CURRENT_VERSION: null, EXCERPTS: {}, EXCERPTS_VERSION: null, ANCHOR_ORDER: {},
    DRAFTS: loadDrafts(doc), pendingGoto: null, highlightedCommentId: null, openMenuId: null, sumEditing: null, gfOpen: false,
  };
}
function captureDocState() {
  return { META, SEEN, CURRENT_VERSION, EXCERPTS, EXCERPTS_VERSION, ANCHOR_ORDER, DRAFTS, pendingGoto, highlightedCommentId, openMenuId, sumEditing, gfOpen };
}
function installDocState(s) {
  ({ META, SEEN, CURRENT_VERSION, EXCERPTS, EXCERPTS_VERSION, ANCHOR_ORDER, DRAFTS, pendingGoto, highlightedCommentId, openMenuId, sumEditing, gfOpen } = s);
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
  if (!CURRENT_VERSION) {
    await loadMeta();
    CURRENT_VERSION = latestVersion();
  }
  if (version && version !== CURRENT_VERSION && (META.history || []).some(h => h.version === version)) CURRENT_VERSION = version;
  const frame = document.getElementById('content-frame');
  if (frame.dataset.doc !== doc || frame.dataset.version !== CURRENT_VERSION || frame.dataset.plan !== String(PLAN_ID)) {
    frameReady = { doc: null, version: null };
    frame.dataset.plan = String(PLAN_ID);
    loadIframe(CURRENT_VERSION);
  }
  const gf = document.getElementById('gf-ta');
  if (gf) gf.value = DRAFTS.gf || '';
  projectSnapshot = '';
  renderProject();
  loadDelivery();
  renderAll();
  openLinkedCard();
  // v9o: the first time a document shows after a load, a composer that held
  // unsent text is open again.
  if (!popReopened.has(doc)) { popReopened.add(doc); reopenPopDraft(); }
  return whenFrameReady();
}
const popReopened = new Set();
function parkDoc() {
  VIEW_DOC = null;
}

// ── Categories (one page per project) ───────────────────────────────
// ./api/categories: which tabs exist, the server's counts per tab (so every
// device agrees), the findings sets, the plans and the linked pages.
let CATEGORIES = null;
async function loadCategories() {
  try {
    const got = await pollJson('./api/categories');
    if (!got.ok) return false;
    if (got.same) return true;
    CATEGORIES = got.data;
    if (typeof CATEGORIES.read_only === 'boolean') {
      CAPS = Object.assign({}, CAPS, { read_only: CATEGORIES.read_only });
      document.body.classList.toggle('page-read-only', pageReadOnly());
    }
    const previousPlan = PLANS.find(p => p.id === PLAN_ID);
    PLANS = Array.isArray(CATEGORIES.plans) ? CATEGORIES.plans : [];
    const nextPlan = PLANS.find(p => p.id === PLAN_ID);
    if (previousPlan && nextPlan && previousPlan.current !== nextPlan.current) {
      const saved = DOC_STATE.plans;
      if (saved) {
        if (saved.CURRENT_VERSION === previousPlan.current) saved.CURRENT_VERSION = nextPlan.current;
        saved.META = { ...saved.META, current: nextPlan.current, history: nextPlan.history };
      }
      // v9o: never under a box being typed in or an open composer; the
      // "Latest is …" banner offers the new revision instead.
      if (DOC === 'plans' && CURRENT_VERSION === previousPlan.current && !isEditing() && !document.getElementById('popover').classList.contains('vis')) {
        CURRENT_VERSION = nextPlan.current;
        loadIframe(CURRENT_VERSION);
      }
      if (DOC === 'plans') META = { ...META, current: nextPlan.current, history: nextPlan.history };
    }
    // Plans opens on the first plan in section order (tracking first); a
    // hidden plan opens only by link, an archive page from Open project.
    if (!PLAN_ID || !PLANS.some(p => p.id === PLAN_ID)) PLAN_ID = (PLANS.find(p => p.section !== 'hidden' && !isArchivePlan(p)) || PLANS.find(isArchivePlan) || {}).id || null;
    DOCS = PLAN_ID ? ['review', 'plans'] : ['review'];
    if (window.AnnotateDocs) window.AnnotateDocs.docs = DOCS;
    if (DOC === 'review') renderProject(); // Open project lists the archive pages
    return true;
  } catch { return false; }
}
// An archive page of finished Review topics (long_pages.py), stored as a plan:
// out of the Plans picker, listed under Open project. categories.is_archive_plan mirrors it.
function isArchivePlan(p) {
  return !!p && p.section === 'archive';
}
// The Plans tab shows one plan; another plan starts from its latest revision.
async function selectPlan(id) {
  if (!PLANS.some(p => p.id === id) || id === PLAN_ID) return;
  await docQueue;
  if (DOC === 'plans') enterDoc('review');
  PLAN_ID = id;
  if (!DOCS.includes('plans')) { DOCS = ['review', 'plans']; if (window.AnnotateDocs) window.AnnotateDocs.docs = DOCS; }
  delete DOC_STATE.plans;
  await loadDocState('plans');
  if (window.AA) window.AA.go({ view: 'plans', plan: id });
}

// ── Init ─────────────────────────────────────────────────────────
// The address the page was opened with, tidied before anything else runs
// (this runs when the script loads, before init, any request or the frame):
// - a private review key (#review=<key>) leaves the address bar at once;
//   the session exchange below uses this copy (UI-27);
// - a 2.20.3-era version link (?v=vN, the Review document) moves into the
//   hash (#view=review&v=vN), where the router reads versions (UI-10).
const REVIEW_KEY = (() => {
  const hash = new URLSearchParams(location.hash.slice(1));
  const search = new URLSearchParams(location.search);
  const key = hash.get('review');
  const v = search.get('v');
  const reload = performance.getEntriesByType('navigation')[0]?.type === 'reload';
  if (reload) { hash.delete('v'); search.delete('v'); }
  if (key == null && !v && !reload) return null;
  hash.delete('review');
  if (v && !reload) {
    search.delete('v');
    const view = hash.get('view');
    if (!hash.get('v') && (!view || view === 'review')) { hash.set('view', 'review'); hash.set('v', v); }
  }
  const s = search.toString(), h = hash.toString();
  history.replaceState(null, '', location.pathname + (s ? '?' + s : '') + (h ? '#' + h : ''));
  return key;
})();
// F7: a private review link (#review=<key>) opens a reviewer session first;
// without it every API call is refused on the public origin.
async function startReviewerSession() {
  const reviewKey = REVIEW_KEY;
  if (!reviewKey) return true;
  let name = 'Reviewer';
  try { name = localStorage.getItem('annotate:reviewer-name') || name; } catch {}
  const response = await fetch(apiUrl('./api/reviewer/session'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: reviewKey, name }) }).catch(() => null);
  if (!response || !response.ok) {
    showStatus('This review link is invalid or expired.');
    return false;
  }
  return true;
}
function showStatus(text) {
  const status = document.getElementById('delivery-status');
  status.hidden = false;
  status.textContent = text;
}
// UI-24: a card link (#feedback=<id>, main's form; #c=<id> also) opens that
// card: the router shows its document (at the card's own version unless the
// card follows the viewer), then the rail shows the card expanded and
// highlighted. takeCardLink() runs before the router reads the hash.
let linkedCard = null;
function takeCardLink() {
  const p = new URLSearchParams(location.hash.slice(1));
  const id = p.get('feedback') || p.get('c');
  const c = id ? findCommentById(id) : null;
  const doc = c && docOf(c);
  if (!doc || !DOCS.includes(doc)) return;
  linkedCard = c.id;
  const sameView = p.get('view') === doc;
  if (!sameView) p.set('view', doc);
  if (!sameView || !p.get('v')) {
    const own = withDoc(doc, () => followsViewer(c) ? null : c.version);
    if (own) p.set('v', own); else p.delete('v');
  }
  history.replaceState(null, '', location.pathname + location.search + '#' + p.toString());
}
function openLinkedCard() {
  const c = linkedCard && findCommentById(linkedCard);
  linkedCard = null;
  if (!c || docOf(c) !== VIEW_DOC) return;
  cardExpanded[c.id] = true;
  focusSidebarCard(c.id);
}
// True while the reviewer is typing in the rail or the document. A render
// never rebuilds the composer or the general-feedback box, so typing there
// holds nothing back (v9o); every box's text is a draft either way.
function isEditing() {
  const ae = document.activeElement;
  if (ae && ae.closest('textarea,input,[contenteditable="true"]') && !ae.closest('#popover, #general-feedback-box')) return true;
  try {
    const inner = document.getElementById('content-frame').contentDocument.activeElement;
    return !!(inner && inner.closest('textarea,input,[contenteditable="true"]'));
  } catch { return false; }
}
// The shell itself never scrolls; only its panes do. iPad browsers still
// scroll the page (toolbar collapse, the keyboard), and with body
// overflow:hidden there is no way back: the header and Send are gone (Chang,
// 2026-10-30, iPad Chrome). Put it back, except while the keyboard is up.
function keepShellUnscrolled() {
  const typing = el => !!(el && el.closest && el.closest('textarea,input,[contenteditable="true"]'));
  const unscroll = () => {
    if (!window.scrollY && !document.body.scrollTop) return;
    let ae = document.activeElement;
    try { if (ae && ae.tagName === 'IFRAME') ae = ae.contentDocument.activeElement; } catch {}
    if (typing(ae)) return;
    window.scrollTo(0, 0);
    document.body.scrollTop = 0;
  };
  window.addEventListener('scroll', unscroll, { passive: true });
  document.body.addEventListener('scroll', unscroll, { passive: true });
  if (window.visualViewport) window.visualViewport.addEventListener('resize', unscroll); // keyboard closed
  window.addEventListener('focusin', () => setTimeout(unscroll, 300));
}
let DOCS_LOADED_resolve;
const DOCS_LOADED = new Promise(res => { DOCS_LOADED_resolve = res; });
async function init() {
  keepShellUnscrolled();
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
  // UI-23: "Show more" / "Show less" under a long comment.
  document.getElementById('comment-list').addEventListener('click', (e) => {
    const btn = e.target.closest && e.target.closest('[data-action="text-more"]');
    if (!btn) return;
    e.stopPropagation();
    const open = !commentTextOpen[btn.dataset.id];
    commentTextOpen[btn.dataset.id] = open;
    const t = document.getElementById(btn.getAttribute('aria-controls'));
    if (t) t.classList.toggle('is-open', open);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    btn.textContent = open ? 'Show less' : 'Show more';
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
  loadBoard();
  DRAFTS = loadDrafts(DOC);
  for (const doc of DOCS) await loadDocState(doc);
  takeCardLink();
  DOCS_LOADED_resolve();
  document.dispatchEvent(new CustomEvent('annotate:store'));
  if (window.AA) window.AA.changed();
  loadHistory();

  // One refresh at a time. Hidden tabs make no requests; foreground resumes now.
  // v9o: a poll that brings nothing new (every read a 304 or the same body)
  // does no other work. Every 8 s while things change or the reviewer is
  // active; after a quiet minute every 15 s, after two every 30 s; any key,
  // click or return to the tab brings 8 s back. A render the reviewer's
  // typing held back runs on the next poll even if nothing else changed.
  let refreshing = false;
  let refreshTimer;
  let nextAt = 0;
  let idlePolls = 0;
  let held = false;
  let lastStoreSig = JSON.stringify(STORE) + JSON.stringify(READ) + pageReadOnly();
  const pollDelay = () => idlePolls < 8 ? 8000 : idlePolls < 16 ? 15000 : 30000;
  function schedule(ms) {
    clearTimeout(refreshTimer);
    if (document.hidden) return;
    nextAt = Date.now() + ms;
    refreshTimer = setTimeout(refresh, ms);
  }
  async function refresh() {
    clearTimeout(refreshTimer);
    if (document.hidden) return;
    if (refreshing || docBusy || pendingPosts) { schedule(8000); return; }
    refreshing = true;
    let changed = false;
    try {
      pollChanged = false;
      await Promise.all([loadStore(), loadReadState(), loadCategories(), loadSessionMonitor(), loadProject()]);
      if (historyDirty) loadHistory();
      loadBoard();
      const doc = VIEW_DOC;
      const onDoc = doc && DOC === doc && !docBusy;
      if (onDoc) await loadMeta();
      loadDelivery();
      changed = pollChanged;
      if (changed || held) {
        held = false;
        // The store is written out once per poll (megabytes on FLD).
        const storeJson = JSON.stringify(STORE), readJson = JSON.stringify(READ);
        const storeSig = storeJson + readJson + pageReadOnly();
        if (storeSig !== lastStoreSig) {
          if (isEditing()) held = true;
          else { lastStoreSig = storeSig; document.dispatchEvent(new CustomEvent('annotate:store')); }
        }
        if (onDoc && !docBusy) {
          const snap = storeJson + JSON.stringify(META) + readJson + pageReadOnly();
          if (snap !== lastSnap[doc]) { if (isEditing()) held = true; else { lastSnap[doc] = snap; renderAll(); } } else updateSendState();
        }
        if (window.AA) window.AA.changed();
      }
    } finally {
      refreshing = false;
      idlePolls = changed ? 0 : idlePolls + 1;
      schedule(pollDelay());
    }
  }
  const active = () => {
    if (idlePolls < 8) return;
    idlePolls = 0;
    if (nextAt - Date.now() > 8000) schedule(8000);
  };
  document.addEventListener('pointerdown', active, true);
  document.addEventListener('keydown', active, true);
  window.addEventListener('message', (e) => { if (e.data && e.data.type && String(e.data.type).indexOf('annotate:') === 0) active(); });
  document.addEventListener('visibilitychange', () => {
    clearTimeout(refreshTimer);
    idlePolls = 0;
    if (!document.hidden) refresh();
  });
  schedule(8000);
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
  olderShown: (doc) => withDoc(doc, () => !!CURRENT_VERSION && !!latestVersion() && CURRENT_VERSION !== latestVersion()),
  roundStats: (doc) => withDoc(doc, roundStats),
  sendables: (doc) => withDoc(doc, sendables),
  sentence: (doc) => withDoc(doc, summarySentence),
  warning: (doc) => withDoc(doc, summaryWarning),
  items: (doc) => withDoc(doc, sendItems),
  renderSummaryInto: (doc, el) => withDoc(doc, () => renderSummaryInto(el, doc === VIEW_DOC)),
  renderHistoryInto: (doc, shown) => withDoc(doc, () => renderVersionRail(shown)),
  isArchivePlan,
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
  board: boardLink,
  plans: () => PLANS,
  planId: () => PLAN_ID,
  selectPlan,
  sentRounds,
  sentRoundsRaw: () => HISTORY_DATA?.rounds || [],
  withdrawnQuestions,
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
  deliveryLabel,
  deliveryHtml,
  decisionAnswer,
  answerLabel,
  displayPrompt,
  decisionOptions,
  ticketsHTML,
  authorLabel,
  whoName,
  createComment: apiCreateComment,
  decide: apiDecision,
  refreshStore: reloadPage,
  ico,
  // adapter.js draws the document's question cards with the rail's builder.
  stripCard,
  stripVerdictChip,
  syncClamps: syncExcerptClamps,
};

document.addEventListener('DOMContentLoaded', init);
// A new private review link in the address bar starts a new session.
window.addEventListener('hashchange', () => {
  if (new URLSearchParams(location.hash.slice(1)).has('review')) { location.reload(); return; }
  takeCardLink(); // runs before the router's own hashchange listener (app.js)
});

})();
