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
// v2.19 server capabilities, probed ONCE at init via GET ./api/capabilities.
// null = legacy server (404) → every new behavior is off and the chrome acts
// exactly as before: no defer_push, no round bar, no /api/rounds calls.
let CAPS = null;
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

// ── Stable page-wide item numbering ─────────────────────────────────
// Explicit `number` is canonical. Legacy cards recover an unsuffixed Q<number>
// from their prompt; everything else receives the next unused number in
// creation order over live + archived history. One map drives rail, pin and
// body order, so a response item never has three competing labels.
function computeNumbers() {
  NUM_MAP = {};
  const all = flattenAll(true);
  const used = new Set();
  for (const c of all) {
    if (Number.isInteger(c.number) && c.number > 0 && !used.has(c.number)) {
      NUM_MAP[c.id] = c.number;
      used.add(c.number);
    }
  }
  for (const c of all) {
    if (NUM_MAP[c.id]) continue;
    const prompt = c.decision_request && c.decision_request.prompt;
    const match = typeof prompt === 'string' ? prompt.match(/^Q(\d+)(?![0-9A-Za-z])/i) : null;
    const n = match ? Number(match[1]) : 0;
    if (n > 0 && !used.has(n)) {
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
async function apiRoundSubmit(note) {
  try {
    const r = await fetch(apiUrl('./api/rounds/submit' + authorQuery()), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note: note || undefined }),
    });
    if (r.ok) return await r.json();
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
  renderMobileVersionSelect(history);
}

// Mobile replacement for the version rail (hidden on mobile — see
// shell.css): a native <select> in the header. Rebuilt alongside the rail
// itself so the two can never drift out of sync. Each option's label
// carries a review-count suffix so the "needs my review" signal the rail's
// red badge conveys isn't lost in the mobile layout.
function renderMobileVersionSelect(history) {
  const sel = document.getElementById('mobile-version-select');
  if (!sel) return;
  sel.innerHTML = history.map(h => {
    const counts = countsForVersion(h.version);
    const suffix = counts.review > 0 ? ` (${counts.review})` : '';
    return `<option value="${escAttr(h.version)}">${esc(h.version)}${h.label ? ' · ' + esc(h.label) : ''}${suffix}</option>`;
  }).join('');
  sel.value = CURRENT_VERSION || '';
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

// A human section name, or '' — raw anchor ids (d:q19, s:…, tbl:…) are
// internal addresses and never shown beside the #N badge.
function anchorLabel(c) {
  return (c.anchor_label && c.anchor_label !== c.anchor_id) ? c.anchor_label : '';
}

// Drawer scope: null = every version ("All versions" toggle on), else the
// version currently shown in the iframe.
function drawerScope() {
  return showAllVersions ? null : CURRENT_VERSION;
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
  return followsViewer(c) ? CURRENT_VERSION : c.version;
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
  updateMobileFab(total, unread);
}

// Mobile FAB mirrors the drawer's own total/unread counts (renderChips is
// the single place that computes both, scoped to the current drawer scope
// exactly like the badges above it).
function updateMobileFab(total, unread) {
  const fab = document.getElementById('mobile-fab');
  if (!fab) return;
  const badge = document.getElementById('mobile-fab-badge');
  const countEl = document.getElementById('mobile-fab-count');
  if (countEl) countEl.textContent = String(total);
  if (badge) {
    badge.textContent = String(unread > 99 ? '99+' : unread);
    badge.style.display = unread > 0 ? 'flex' : 'none';
  }
  fab.title = total + (total === 1 ? ' comment' : ' comments') + (unread > 0 ? ', ' + unread + ' unread' : '') + ' — open feedback';
}

function renderDrawer() {
  renderChips();
  const listEl = document.getElementById('comment-list');
  const empty = document.getElementById('drawer-empty');
  // The 8s poll (and any other re-render) rebuilds #comment-list wholesale,
  // which resets scroll to the top. Preserve it — matters most for the
  // mobile bottom sheet, where a re-render mid-scroll is jarring, but this
  // is a plain improvement on desktop too.
  const drawerBodyEl = document.getElementById('drawer-body');
  const savedScrollTop = drawerBodyEl ? drawerBodyEl.scrollTop : 0;

  // Preserve in-progress reply drafts across re-renders AND version
  // switches (T11): capture into the persistent DRAFTS store before the
  // innerHTML swap — cards filtered out by the new scope keep their draft
  // for when they render again.
  let focusedDraftFor = null;
  let focusedTa = null;
  listEl.querySelectorAll('.reply-ta').forEach(ta => {
    setDraft(ta.dataset.replyFor, ta.value || '');
    if (ta === document.activeElement) focusedDraftFor = ta.dataset.replyFor;
  });
  // v2.19: the optional verdict note survives re-renders the same way, and
  // so (D3) do the "Request changes" and standing-Comment boxes — a focus-
  // driven goto or an 8s poll must never eat what is half-typed in one.
  listEl.querySelectorAll('.decision-note-ta').forEach(ta => {
    setDraft('note:' + ta.dataset.decisionNoteTa, ta.value || '');
    if (ta === document.activeElement) focusedTa = '[data-decision-note-ta="' + cssEsc(ta.dataset.decisionNoteTa) + '"]';
  });
  listEl.querySelectorAll('.decision-comment-ta').forEach(ta => {
    setDraft('changes:' + ta.dataset.decisionCommentTa, ta.value || '');
    if (ta === document.activeElement) focusedTa = '[data-decision-comment-ta="' + cssEsc(ta.dataset.decisionCommentTa) + '"]';
  });
  listEl.querySelectorAll('.decision-say-ta').forEach(ta => {
    setDraft('say:' + ta.dataset.decisionSayTa, ta.value || '');
    if (ta === document.activeElement) focusedTa = '[data-decision-say-ta="' + cssEsc(ta.dataset.decisionSayTa) + '"]';
  });

  let all = flattenAll(false).filter(inScope);
  if (activeFilter !== 'all') {
    all = all.filter(c => classify(c) === activeFilter);
  }

  all.sort((a, b) => (NUM_MAP[a.id] || 0) - (NUM_MAP[b.id] || 0));
  if (unreadFirst) {
    const rank = c => (readStateOf(c) === 'read' ? 1 : 0);
    all.sort((a, b) => rank(a) - rank(b) ||
      ((NUM_MAP[a.id] || 0) - (NUM_MAP[b.id] || 0)));
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
  listEl.querySelectorAll('.decision-note-ta').forEach(ta => {
    const draft = DRAFTS['note:' + ta.dataset.decisionNoteTa];
    if (draft) ta.value = draft;
  });
  listEl.querySelectorAll('.decision-comment-ta').forEach(ta => {
    const draft = DRAFTS['changes:' + ta.dataset.decisionCommentTa];
    if (draft) ta.value = draft;
  });
  listEl.querySelectorAll('.decision-say-ta').forEach(ta => {
    const draft = DRAFTS['say:' + ta.dataset.decisionSayTa];
    if (draft) ta.value = draft;
  });
  if (focusedTa && !focusedDraftFor) {
    const ta = listEl.querySelector(focusedTa);
    if (ta) {
      ta.focus();
      ta.selectionStart = ta.selectionEnd = ta.value.length;
    }
  }
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
  wireDecisionActions(listEl);
  // Skip when a reply textarea just reclaimed focus above — the browser's
  // own scroll-into-view for that focus is the more correct outcome, and
  // forcing the old scrollTop back would fight it mid-keystroke.
  if (drawerBodyEl && !focusedDraftFor && !focusedTa) drawerBodyEl.scrollTop = savedScrollTop;
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
// Context up to this many chars renders as a muted paragraph; longer context
// goes behind the "Why / details" WAI-ARIA disclosure.
const DECISION_CONTEXT_INLINE_MAX = 160;
const DECISION_IMPACTS = ['low', 'medium', 'high'];

// T-verdict-reversal (user-reported: clicked Reject by mistake on decision
// D8, no way to reverse it): comment ids currently showing the change-verdict
// form instead of their resolved chip. A module-level map (not render-local
// state) so the 8s poll's re-render doesn't silently snap the card back to
// the chip mid-correction; cleared on submit or explicit Cancel.
const decisionChanging = {};
// v2.19 per-card UI state that must survive the 8s re-render: the context
// disclosure's expanded state and whether the optional "Add a note" form is
// open. Note TEXT lives in DRAFTS under 'note:<id>' (same store as replies).
const decisionDetailsOpen = {};
const decisionNoteOpen = {};
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
      if (DECISION_OPTIONS_ALL.indexOf(o) === -1) continue;
      const id = canonicalOptionId(o);
      const cq = typeof cons[o] === 'string' ? cons[o] : (typeof cons[id] === 'string' ? cons[id] : '');
      out.push({ id, labelHtml: DECISION_BTN_LABEL[id], labelText: id, consequence: cq, style: null, custom: false });
    } else if (o && typeof o === 'object' && typeof o.id === 'string' && o.id) {
      const id = canonicalOptionId(o.id);
      const known = DECISION_OPTIONS_ALL.indexOf(id) !== -1;
      const label = typeof o.label === 'string' && o.label.trim() ? o.label.trim() : null;
      out.push({
        id: known ? id : o.id,
        labelHtml: label ? esc(label) : (known ? DECISION_BTN_LABEL[id] : esc(o.id)),
        labelText: label || o.id,
        consequence: typeof o.consequence === 'string' ? o.consequence : (typeof cons[o.id] === 'string' ? cons[o.id] : ''),
        style: (o.style === 'primary' || o.style === 'danger' || o.style === 'default') ? o.style : null,
        custom: !known,
      });
    }
  }
  return out;
}

function renderDecisionContext(c, dr) {
  const ctx = typeof dr.context === 'string' ? dr.context.trim() : '';
  if (!ctx) return '';
  if (ctx.length <= DECISION_CONTEXT_INLINE_MAX) return `<div class="decision-context">${esc(ctx)}</div>`;
  const open = !!decisionDetailsOpen[c.id];
  const rid = 'dctx-' + escAttr(c.id);
  return `<div class="decision-disclosure">
      <button type="button" class="decision-disclosure-btn" aria-expanded="${open ? 'true' : 'false'}" aria-controls="${rid}" data-decision-action="toggle-details" data-id="${escAttr(c.id)}">Why / details</button>
      <div class="decision-context" id="${rid}" role="region" aria-label="Decision details"${open ? '' : ' hidden'}>${esc(ctx)}</div>
    </div>`;
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
function renderDecisionEvidence(dr) {
  const ev = Array.isArray(dr.evidence)
    ? dr.evidence.filter(e => e && typeof e === 'object' && typeof e.anchor === 'string' && e.anchor)
    : [];
  if (!ev.length) return '';
  const links = ev.map(e =>
    `<button type="button" class="decision-evidence-link" data-decision-action="evidence" data-anchor="${escAttr(e.anchor)}" title="Scroll to ${escAttr(e.anchor)} in the document">${esc(e.label || e.anchor)}</button>`
  ).join('');
  return `<div class="decision-evidence"><span class="decision-evidence-lbl">Evidence:</span>${links}</div>`;
}
function renderDecisionPending(c) {
  if (!isRoundPending(c)) return '';
  return `<div class="decision-pending-row">
      <span class="decision-pending-chip" title="This verdict is recorded but has not been sent to the agent yet. Finish the review to send every pending verdict at once.">Pending &mdash; not sent</span>
      <button type="button" class="alink decision-send-now" data-decision-action="send-now" data-id="${escAttr(c.id)}" title="Send just this verdict now, outside the round">Send now</button>
    </div>`;
}

// One-click decision block: an agent poses accept/reject/changes via
// c.decision_request; a click on Accept/Reject submits immediately, Request
// changes (Comment on a pre-D2 server) reveals an inline textarea whose text
// is mandatory. Once c.decision exists, the same slot renders
// a resolved verdict chip (plus a "Change verdict" link, unless the card is
// mid-correction, in which case it shows the buttons again).
// v2.19 additions (all optional, all absent on a legacy request): context
// paragraph / disclosure, "Recommended" badge, per-option consequences,
// impact + blocking chips, evidence links, "Pending — not sent" chip with
// "Send now" in round mode, and an optional note on Accept/Reject.
function renderDecisionBlock(c) {
  if (!c.decision_request || c.status === 'archived') return '';
  const dr = c.decision_request;
  if (c.status === 'resolved_in_version') {
    return `<div class="decision-block decision-resolved">
      <div class="decision-prompt">${esc(displayPrompt(c))}</div>
      <span class="decision-verdict-chip">Resolved in ${esc(c.resolved_in_version || 'later version')}</span>
    </div>`;
  }
  if (c.status === 'addressed_by_agent' && !decisionAnswer(c)) {
    return `<div class="decision-block decision-resolved">
      <div class="decision-prompt">${esc(displayPrompt(c))}</div>
      <span class="decision-verdict-chip">Addressed by agent &mdash; no answer needed</span>
    </div>`;
  }
  const changing = !!decisionChanging[c.id];
  if (decisionAnswer(c) && !changing) {
    const label = DECISION_VERDICT_LABEL[c.decision.verdict] || c.decision.verdict;
    return `<div class="decision-block decision-resolved">
      <div class="decision-prompt">${esc(displayPrompt(c))}</div>
      <span class="decision-verdict-chip verdict-${escAttr(c.decision.verdict)}">${esc(label)} &middot; ${esc(fmtTs(c.decision.ts))}</span>
      <button class="alink decision-change-link" data-decision-action="change" data-id="${escAttr(c.id)}">&#8634; Change verdict</button>
      ${renderDecisionPending(c)}
    </div>`;
  }
  const opts = decisionOptions(dr);
  // D2: the free-text slot posts `changes` (note mandatory) when this card
  // carries the Request-changes option, `comment` otherwise.
  const wantsChanges = opts.some(o => o.id === 'changes');
  // Free-text answer. Skipped when `comment` is already one of the posed
  // options and on a card that already carries an answer.
  const showSay = !opts.some(o => o.id === 'comment') && !decisionAnswer(c);
  const hasCons = opts.some(o => !!o.consequence);
  const rec = typeof dr.recommendation === 'string' ? dr.recommendation : null;
  let btns = '';
  for (const o of opts) {
    const isRec = !!rec && canonicalOptionId(rec) === o.id;
    const cls = o.custom
      ? ('decision-custom' + (o.style ? ' decision-style-' + o.style : ''))
      : DECISION_BTN_CLASS[o.id];
    const action = o.custom ? 'custom' : o.id;
    const extra = o.custom ? ` data-option-id="${escAttr(o.id)}" data-option-label="${escAttr(o.labelText)}"` : '';
    const badge = isRec ? '<span class="decision-rec-badge">Recommended</span>' : '';
    const btn = `<button class="decision-btn ${cls}${isRec ? ' is-recommended' : ''}" data-decision-action="${action}" data-id="${escAttr(c.id)}"${extra}${isRec ? ' title="Recommended by the agent"' : ''}>${o.labelHtml}${badge}</button>`;
    btns += hasCons
      ? `<div class="decision-opt">${btn}${o.consequence ? `<div class="decision-consequence">${esc(o.consequence)}</div>` : ''}</div>`
      : btn;
  }
  const changingNote = (c.decision && changing) ? `<div class="decision-changing-note">
      <span>Changing verdict &mdash; currently ${esc(DECISION_VERDICT_TEXT[c.decision.verdict] || c.decision.verdict)}</span>
      <button class="alink" data-decision-action="cancel-change" data-id="${escAttr(c.id)}">Cancel</button>
    </div>` : '';
  const sayOpen = !!decisionSayOpen[c.id];
  const sayHtml = showSay ? `<div class="decision-say-row">
      <button type="button" class="decision-say" data-decision-action="say" data-id="${escAttr(c.id)}" aria-expanded="${sayOpen ? 'true' : 'false'}" title="Answer this question in your own words.">&#128172; Answer in words</button>
      <span class="decision-say-hint">counts as answered</span>
    </div>
    <div class="decision-comment-form decision-say-form" data-decision-say-for="${escAttr(c.id)}" style="display:${sayOpen ? 'flex' : 'none'}">
      <textarea class="decision-say-ta" data-decision-say-ta="${escAttr(c.id)}" placeholder="Answer in your own words&hellip;" rows="2"></textarea>
      <button class="decision-comment-submit" data-decision-action="say-submit" data-id="${escAttr(c.id)}">Send answer</button>
    </div>` : '';
  const noteOpen = !!decisionNoteOpen[c.id];
  const noteHtml = opts.some(o => o.id === 'accept' || o.id === 'reject') ? `<div class="decision-note-row">
      <button type="button" class="decision-note-toggle" data-decision-action="note-toggle" data-id="${escAttr(c.id)}" aria-expanded="${noteOpen ? 'true' : 'false'}">${noteOpen ? '&minus; Remove note' : '+ Add a note'}</button>
      <div class="decision-note-form"${noteOpen ? '' : ' hidden'}><textarea class="decision-note-ta" data-decision-note-ta="${escAttr(c.id)}" placeholder="Optional note sent with Accept / Reject&hellip;" rows="2"></textarea></div>
    </div>` : '';
  return `<div class="decision-block">
    ${changingNote}
    <div class="decision-prompt">${esc(displayPrompt(c))}</div>
    ${renderDecisionContext(c, dr)}
    ${renderDecisionMeta(dr)}
    <div class="decision-btns${hasCons ? ' has-consequences' : ''}">${btns}</div>
    ${renderDecisionEvidence(dr)}
    ${sayHtml}
    ${noteHtml}
    <div class="decision-comment-form" data-decision-comment-for="${escAttr(c.id)}" style="display:${decisionChangesOpen[c.id] ? 'flex' : 'none'}">
      <textarea class="decision-comment-ta" data-decision-comment-ta="${escAttr(c.id)}" placeholder="${wantsChanges ? 'What needs to change&hellip;' : 'Add your comment&hellip;'}" rows="2"></textarea>
      <button class="decision-comment-submit" data-decision-action="comment-submit" data-id="${escAttr(c.id)}"${wantsChanges ? ' data-verdict="changes"' : ''}>Send</button>
    </div>
    <div class="decision-feedback" data-decision-feedback="${escAttr(c.id)}"></div>
  </div>`;
}

function renderCItem(c) {
  const cls = classify(c);
  const clsMap = { review: 'needs-review', waiting: 'waiting-agent', done: 'done' };
  const doneLabel = c.status === 'archived' ? 'Archived'
    : c.status === 'resolved_in_version' ? `Resolved in ${c.resolved_in_version || 'later version'}`
    : c.status === 'addressed_by_agent' ? 'Addressed'
    : 'Done';
  const statusLabelMap = { review: 'Needs my review', waiting: 'Waiting on agent', done: doneLabel };
  const ts = fmtTs(c.created_at);
  // #n mirrors the numbered pin on the page (pin 7 ↔ card #7).
  const num = NUM_MAP[c.id];
  const numHtml = num ? `<span class="citem-num">#${num}</span>` : '';
  const rstate = readStateOf(c);
  let unreadChipHtml = '';
  if (rstate === 'new-activity') unreadChipHtml = '<span class="citem-chip-newreply" title="The agent responded since you last read this">&uarr; NEW reply</span>';
  else if (rstate === 'unread') unreadChipHtml = '<span class="citem-chip-unread" title="You have not opened this comment yet">Unread</span>';
  const unreadCls = rstate !== 'read' ? ' is-unread' : '';
  const hl = c.id === highlightedCommentId ? ' hl' : '';
  const decisionCls = isUnresolvedDecision(c) ? ' decision-required' : '';

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
    } else if (c.status === 'user_confirmed' || c.status === 'resolved_in_version') {
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
    if (c.status === 'resolved_in_version' && c.resolved_in_version && c.resolution_anchor_id) {
      actions += `<button class="alink" data-action="resolution" data-id="${escAttr(c.id)}">View resolution in ${esc(c.resolved_in_version)}</button>`;
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
        <span class="citem-goto-label">Location unavailable in this version</span>
        <button class="citem-goto-btn err" data-action="goto" data-id="${escAttr(c.id)}" data-anchor="${escAttr(c.anchor_id)}" data-version="${escAttr(gotoVersionFor(c))}" title="Content may have been restructured since this comment was made">&#10007; Not found</button>
      </div>`;
  } else {
    gotoHtml = `<div class="citem-goto" data-goto-row data-goto-id="${escAttr(c.id)}">
        <span class="citem-goto-label">${esc(anchorLabel(c))}</span>
        <button class="citem-goto-btn" data-action="goto" data-id="${escAttr(c.id)}" data-anchor="${escAttr(c.anchor_id)}" data-version="${escAttr(gotoVersionFor(c))}">&rarr; Go to location</button>
      </div>`;
  }

  return `<div class="citem ${clsMap[cls]}${hl}${unreadCls}${decisionCls}" data-comment-id="${escAttr(c.id)}" title="Click to show this comment's location in the document">
    <div class="citem-node">
      <span class="citem-node-name">${numHtml}${esc(anchorLabel(c))}</span>
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
    ${renderDecisionBlock(c)}
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
    goToCommentLocation(c.anchor_id, gotoVersionFor(c), c.id);
    sendCommentCountsToFrame();
  }));
  // D3 item 3 (user-reported: "i also would like to be able to automatically
  // be brought to the location when i click into the feedback box instead of
  // having to do that manually"). The whole-card click above deliberately
  // ignores clicks that land in a control, so typing a reply or a verdict
  // note never moved the document. Focus entering any of the card's boxes is
  // the same intent as clicking the card, so it navigates too — quietly, so
  // the box the reviewer just clicked into survives.
  root.querySelectorAll('.citem').forEach(card => card.addEventListener('focusin', (e) => {
    if (!e.target.closest('textarea, input')) return;
    const c = findCommentById(card.dataset.commentId);
    if (!c || isGeneralAnchor(c.anchor_id)) return;
    if (highlightedCommentId === c.id) return; // already showing this location
    markRead([c]);
    goToCommentLocation(c.anchor_id, gotoVersionFor(c), c.id, { quiet: true });
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
  root.querySelectorAll('[data-action="resolution"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const c = findCommentById(btn.dataset.id);
    if (!c || !c.resolved_in_version || !c.resolution_anchor_id) return;
    goToCommentLocation(c.resolution_anchor_id, c.resolved_in_version, null);
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

// ── One-click decision buttons ───────────────────────────────────────
function setDecisionFeedback(root, id, msg, isError) {
  const el = root.querySelector('[data-decision-feedback="' + cssEsc(id) + '"]');
  if (!el) return;
  el.textContent = msg;
  el.classList.toggle('is-error', !!isError);
}
function setDecisionButtonsDisabled(root, id, disabled) {
  root.querySelectorAll('.decision-btn[data-id="' + cssEsc(id) + '"]').forEach(b => { b.disabled = disabled; });
  const submitBtn = root.querySelector('[data-decision-action="comment-submit"][data-id="' + cssEsc(id) + '"]');
  if (submitBtn) submitBtn.disabled = disabled;
}

// Optional note typed under Accept/Reject ("+ Add a note"); null when the form
// is closed or empty, so a plain click posts exactly what it always did.
function decisionNoteText(root, id) {
  if (!decisionNoteOpen[id]) return null;
  const ta = root.querySelector('[data-decision-note-ta="' + cssEsc(id) + '"]');
  const t = (ta && ta.value || '').trim();
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
    return;
  }
  delete decisionChanging[id]; // resolved again (first vote or a correction) — drop back to the chip
  delete decisionNoteOpen[id];
  setDraft('note:' + id, '');
  delete decisionSayOpen[id];
  delete decisionChangesOpen[id];
  setDraft('say:' + id, '');
  setDraft('changes:' + id, '');
  if (result.delivery === 'deferred' || (roundsEnabled() && result.decision && result.decision.round_pending)) {
    setDecisionFeedback(root, id, 'Pending — not sent. Finish review to send.', false);
  } else {
    const delivered = result.delivery === 'active_monitor';
    setDecisionFeedback(root, id, delivered ? '✅ Sent to active session' : '⏳ Queued — no monitor armed', false);
  }
  await refreshStore();
  markReadAfterAction(id);
}

// Evidence link → scroll + flash the referenced anchor in the content doc
// (same postMessage path as "Go to location"). On mobile the sheet covers the
// document, so dismiss it first exactly like goToCommentLocation does.
function goToEvidence(anchorId) {
  if (!anchorId) return;
  if (isMobileLayout()) setMobileSheetOpen(false);
  scrollToAnchorInFrame(anchorId, null);
}

function wireDecisionActions(root) {
  root.querySelectorAll('[data-decision-action="accept"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    submitDecision(root, btn.dataset.id, 'accept', decisionNoteText(root, btn.dataset.id));
  }));
  root.querySelectorAll('[data-decision-action="reject"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    submitDecision(root, btn.dataset.id, 'reject', decisionNoteText(root, btn.dataset.id));
  }));
  // Custom option (object form with an id outside accept/reject/changes):
  // a real choice, so it posts the `select` verdict naming it. Against a
  // server that predates `select` it posts `comment` with the pre-D3 text.
  root.querySelectorAll('[data-decision-action="custom"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const label = btn.dataset.optionLabel || btn.dataset.optionId || 'option';
    const note = decisionNoteText(root, btn.dataset.id);
    const v = selectVerdictId();
    const text = (v === 'select' ? label : 'Selected: ' + label) + (note ? '\n\n' + note : '');
    submitDecision(root, btn.dataset.id, v, text);
  }));
  root.querySelectorAll('[data-decision-action="toggle-details"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const id = btn.dataset.id;
    const open = !decisionDetailsOpen[id];
    decisionDetailsOpen[id] = open;
    // Toggle in place (no re-render): keeps focus on the disclosure button,
    // which is what assistive tech expects from aria-expanded.
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    const region = document.getElementById(btn.getAttribute('aria-controls'));
    if (region) region.hidden = !open;
  }));
  root.querySelectorAll('[data-decision-action="evidence"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    goToEvidence(btn.dataset.anchor);
  }));
  root.querySelectorAll('[data-decision-action="note-toggle"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const id = btn.dataset.id;
    const open = !decisionNoteOpen[id];
    decisionNoteOpen[id] = open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    btn.innerHTML = open ? '&minus; Remove note' : '+ Add a note';
    const form = btn.parentElement && btn.parentElement.querySelector('.decision-note-form');
    if (form) {
      form.hidden = !open;
      const ta = form.querySelector('.decision-note-ta');
      if (open && ta) ta.focus();
      if (!open && ta) { ta.value = ''; setDraft('note:' + id, ''); }
    }
  }));
  root.querySelectorAll('[data-decision-action="send-now"]').forEach(btn => btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    btn.disabled = true;
    btn.textContent = 'Sending…';
    const j = await apiPushSingle(btn.dataset.id);
    if (!j) { btn.disabled = false; btn.textContent = 'Send now'; return; }
    await refreshStore();
    markReadAfterAction(btn.dataset.id);
  }));
  // "Comment" (legacy server) and "Request changes" (D2) share one slot: both
  // reveal the inline textarea, and neither submits without text.
  root.querySelectorAll('[data-decision-action="comment"], [data-decision-action="changes"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const form = root.querySelector('[data-decision-comment-for="' + cssEsc(btn.dataset.id) + '"]');
    if (!form) return;
    decisionChangesOpen[btn.dataset.id] = true;
    form.style.display = 'flex';
    const ta = form.querySelector('.decision-comment-ta');
    if (ta) ta.focus();
  }));
  // D3: the standing Comment button. Its own form and its own verdict, so a
  // card that offers "Request changes" still lets a reviewer just talk.
  root.querySelectorAll('[data-decision-action="say"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const id = btn.dataset.id;
    const open = !decisionSayOpen[id];
    decisionSayOpen[id] = open;
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    const form = root.querySelector('[data-decision-say-for="' + cssEsc(id) + '"]');
    if (!form) return;
    form.style.display = open ? 'flex' : 'none';
    const ta = form.querySelector('.decision-say-ta');
    if (open && ta) ta.focus();
  }));
  root.querySelectorAll('[data-decision-action="say-submit"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const id = btn.dataset.id;
    const ta = root.querySelector('[data-decision-say-ta="' + cssEsc(id) + '"]');
    const text = (ta && ta.value || '').trim();
    if (!text) { if (ta) ta.focus(); return; }
    submitDecision(root, id, 'comment', text);
  }));
  root.querySelectorAll('[data-decision-action="comment-submit"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const id = btn.dataset.id;
    const ta = root.querySelector('[data-decision-comment-ta="' + cssEsc(id) + '"]');
    const text = (ta && ta.value || '').trim();
    if (!text) { if (ta) ta.focus(); return; }
    submitDecision(root, id, btn.dataset.verdict || 'comment', text);
  }));
  root.querySelectorAll('[data-decision-action="change"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    decisionChanging[btn.dataset.id] = true;
    renderDrawer();
  }));
  root.querySelectorAll('[data-decision-action="cancel-change"]').forEach(btn => btn.addEventListener('click', (e) => {
    e.stopPropagation();
    delete decisionChanging[btn.dataset.id];
    renderDrawer();
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
  const doneLabel = c.status === 'archived' ? 'Archived'
    : c.status === 'resolved_in_version' ? `Resolved in ${c.resolved_in_version || 'later version'}`
    : c.status === 'addressed_by_agent' ? 'Addressed'
    : 'Done';
  const statusLabelMap = { review: 'Needs my review', waiting: 'Waiting on agent', done: doneLabel };
  const num = NUM_MAP[c.id];
  const respHtml = c.response_text
    ? `<div class="pinpop-item-resp"><b>Agent:</b> ${esc(c.response_text)}</div>`
    : '';
  return `<div class="pinpop-item" data-comment-id="${escAttr(c.id)}">
    <div class="pinpop-item-hdr">
      ${num ? `<span class="citem-num">#${num}</span>` : ''}
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
  // On mobile the drawer is a bottom sheet, not a collapsible rail — this
  // same button (still visually the "»" affordance in the drawer header)
  // closes the sheet instead of setting the desktop .collapsed state, so
  // the two mechanisms never both apply to the one element at once.
  document.getElementById('drawer-collapse').addEventListener('click', () => {
    if (isMobileLayout()) { setMobileSheetOpen(false); return; }
    setDrawerCollapsed(true);
  });
  document.getElementById('drawer-strip').addEventListener('click', () => setDrawerCollapsed(false));
  document.getElementById('vrail-collapse').addEventListener('click', () => setVrailCollapsed(true));
  document.getElementById('vrail-strip').addEventListener('click', () => setVrailCollapsed(false));
  try {
    // A collapsed-rail preference saved from a prior desktop session must
    // not apply on a phone: mobile visibility is owned entirely by
    // body.is-mobile-sheet-open, never by .collapsed.
    if (!isMobileLayout() && localStorage.getItem('annotate:drawerCollapsed') === '1') setDrawerCollapsed(true);
    if (localStorage.getItem('annotate:vrailCollapsed') === '1') setVrailCollapsed(true);
  } catch {}
}

// ── Mobile-only chrome: FAB, version <select>, dialog backdrop ─────────
function wireMobileChrome() {
  const fab = document.getElementById('mobile-fab');
  if (fab) fab.addEventListener('click', () => setMobileSheetOpen(true));
  const sel = document.getElementById('mobile-version-select');
  if (sel) sel.addEventListener('change', () => switchVersion(sel.value));
  const backdrop = document.getElementById('mobile-dialog-backdrop');
  if (backdrop) backdrop.addEventListener('click', () => { closePopover(); closePinPopover(); cancelRepin(); });
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
      // textContent here (not innerHTML): this transient status string is
      // plain text, and using textContent replaces the icon/label spans
      // below wholesale — restored on reset so the mobile
      // ".push-session-label{display:none}" rule still has a label span to
      // target afterward.
      btn.querySelector('span:first-child').textContent = delivered
        ? '✅ Sent ' + j.flagged_count + ' to active session'
        : '⏳ Queued ' + j.flagged_count + ' — no monitor armed';
      await refreshStore();
      setTimeout(() => {
        btn.classList.remove('success', 'queued');
        btn.querySelector('span:first-child').innerHTML =
          '<span class="push-session-icon">\u{1F4E8}</span><span class="push-session-label"> Push to session</span>';
        updatePushCounter();
      }, 3000);
    } else {
      btn.disabled = false;
    }
  });
}

// ── v2.19 review rounds: sticky bar + submit confirm ─────────────────
// Only active when the server advertised capabilities.rounds. Verdicts are
// posted with defer_push (see apiDecision) and accumulate as
// decision.round_pending; the bar shows how many are waiting and submits
// them as ONE session_push{round:true} so the agent never reacts to a
// half-finished review. Counts span every version (a round is per page).
function roundStats() {
  let pending = 0, decided = 0, total = 0, undecided = 0;
  for (const c of flattenAll(false)) {
    if (!hasDecisionRequest(c)) continue;
    total++;
    if (decisionAnswer(c)) decided++; else undecided++;
    if (isRoundPending(c)) pending++;
  }
  return { pending, decided, total, undecided };
}
// The bar lives inside the drawer above its footer on desktop. On mobile the
// drawer is a translated-off-screen bottom sheet (a transform makes it the
// containing block for position:fixed descendants), so the node is moved to
// <body> where body>.round-bar pins it to the viewport bottom.
function placeRoundBar() {
  const bar = document.getElementById('round-bar');
  const slot = document.getElementById('round-bar-slot');
  if (!bar || !slot) return;
  if (isMobileLayout()) {
    if (bar.parentElement !== document.body) document.body.appendChild(bar);
  } else if (bar.parentElement !== slot) {
    slot.appendChild(bar);
  }
}
let roundBarNote = null; // {text, cls, until} — transient result line after submit/discard
let roundBarNoteTimer = null;
function setRoundBarNote(text, cls, ms) {
  roundBarNote = { text, cls: cls || '', until: Date.now() + (ms || 6000) };
  clearTimeout(roundBarNoteTimer);
  roundBarNoteTimer = setTimeout(() => { roundBarNote = null; renderRoundBar(); }, (ms || 6000) + 50);
}
function renderRoundBar() {
  const bar = document.getElementById('round-bar');
  if (!bar) return;
  placeRoundBar();
  const s = roundStats();
  const noteLive = !!(roundBarNote && Date.now() < roundBarNote.until);
  const show = roundsEnabled() && (s.pending > 0 || noteLive);
  bar.style.display = show ? 'flex' : 'none';
  document.body.classList.toggle('has-round-bar', show && isMobileLayout());
  if (!show) return;
  document.getElementById('round-bar-main').textContent = s.decided + ' of ' + s.total + ' decided';
  document.getElementById('round-pending-n').textContent = String(s.pending);
  const btn = document.getElementById('round-finish-btn');
  btn.disabled = s.pending === 0;
  btn.title = s.pending === 0
    ? 'No pending verdicts'
    : 'Send ' + s.pending + ' pending verdict' + (s.pending === 1 ? '' : 's') + ' to the agent as one review round';
  const sub = document.getElementById('round-bar-sub');
  if (noteLive) {
    sub.textContent = roundBarNote.text;
    sub.className = 'round-bar-sub' + (roundBarNote.cls ? ' ' + roundBarNote.cls : '');
  } else {
    sub.textContent = s.pending + ' verdict' + (s.pending === 1 ? '' : 's') + ' pending — not sent yet';
    sub.className = 'round-bar-sub';
  }
}
function openRoundConfirm() {
  const s = roundStats();
  if (!roundsEnabled() || s.pending === 0) return;
  document.getElementById('round-confirm-sub').textContent =
    s.pending + ' pending verdict' + (s.pending === 1 ? '' : 's') + ' will be sent to the agent as one review round (' +
    s.decided + ' of ' + s.total + ' cards decided).';
  const warn = document.getElementById('round-confirm-warn');
  if (s.undecided > 0) {
    warn.textContent = s.undecided + ' card' + (s.undecided === 1 ? ' is' : 's are') +
      ' still undecided — the round will report ' + (s.undecided === 1 ? 'it' : 'them') + ' as undecided.';
    warn.style.display = '';
  } else {
    warn.style.display = 'none';
  }
  const ta = document.getElementById('round-note-ta');
  ta.value = DRAFTS['round-note'] || '';
  ['round-submit-btn', 'round-discard-btn', 'round-cancel-btn'].forEach(id => { document.getElementById(id).disabled = false; });
  document.getElementById('round-confirm-backdrop').classList.add('vis');
  ta.focus();
}
function closeRoundConfirm() {
  const bd = document.getElementById('round-confirm-backdrop');
  if (bd) bd.classList.remove('vis');
}
function isRoundConfirmOpen() {
  const bd = document.getElementById('round-confirm-backdrop');
  return !!(bd && bd.classList.contains('vis'));
}
async function submitRound() {
  const ta = document.getElementById('round-note-ta');
  const note = (ta.value || '').trim();
  const btns = ['round-submit-btn', 'round-discard-btn', 'round-cancel-btn'].map(id => document.getElementById(id));
  btns.forEach(b => { b.disabled = true; });
  const submitBtn = btns[0];
  submitBtn.textContent = 'Sending…';
  const j = await apiRoundSubmit(note);
  submitBtn.textContent = 'Submit review';
  if (!j) {
    btns.forEach(b => { b.disabled = false; });
    document.getElementById('round-confirm-sub').textContent = 'Failed to submit — try again.';
    return;
  }
  ta.value = '';
  setDraft('round-note', '');
  closeRoundConfirm();
  const delivered = j.delivery === 'active_monitor';
  SESSION_MONITOR = {
    active: delivered,
    monitor_count: j.monitor_count || 0,
    delivery: j.delivery || 'queued',
    owner: j.monitor_owner || null,
  };
  const n = j.comment_count != null ? j.comment_count : 0;
  setRoundBarNote(
    delivered ? '✅ Sent to session (' + n + ')' : '⏳ Queued — no session listening (' + n + ')',
    delivered ? 'is-success' : 'is-queued');
  await refreshStore();
}
async function discardRound() {
  const btns = ['round-submit-btn', 'round-discard-btn', 'round-cancel-btn'].map(id => document.getElementById(id));
  btns.forEach(b => { b.disabled = true; });
  const j = await apiRoundDiscard();
  if (!j) {
    btns.forEach(b => { b.disabled = false; });
    document.getElementById('round-confirm-sub').textContent = 'Failed to discard — try again.';
    return;
  }
  closeRoundConfirm();
  const n = j.comment_count != null ? j.comment_count : 0;
  setRoundBarNote('Discarded ' + n + ' pending verdict' + (n === 1 ? '' : 's') + ' — nothing sent', '', 5000);
  await refreshStore();
}
function wireRoundBar() {
  const finish = document.getElementById('round-finish-btn');
  if (!finish) return;
  finish.addEventListener('click', openRoundConfirm);
  document.getElementById('round-cancel-btn').addEventListener('click', closeRoundConfirm);
  document.getElementById('round-submit-btn').addEventListener('click', submitRound);
  document.getElementById('round-discard-btn').addEventListener('click', discardRound);
  document.getElementById('round-confirm-backdrop').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeRoundConfirm();
  });
  document.getElementById('round-note-ta').addEventListener('input', (e) => setDraft('round-note', e.target.value || ''));
  let t = null;
  window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(renderRoundBar, 120); });
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
  if (!label) {
    el.style.display = 'none';
    el.textContent = '';
    el.title = '';
    return;
  }
  const when = o.claimed_at || o.ts || o.since || o.updated_at || null;
  el.textContent = '';
  const dot = document.createElement('span');
  dot.className = 'owner-chip-dot';
  el.appendChild(dot);
  el.appendChild(document.createTextNode('Owner: ' + label));
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
  el.style.display = '';
}

// ── Bridge: postMessage with the content iframe ─────────────────────
// Content -> shell: {type:'annotate:pin-click', anchorId, anchorLabel, x, y}   (anchor clicked → CREATE popover)
//                   {type:'annotate:pin-open', anchorId, anchorLabel, commentIds, x, y}  (pin clicked → reverse lookup)
//                   {type:'annotate:ready', version}
//                   {type:'annotate:scroll-result', anchorId, found}
//                   {type:'annotate:decision-posted', commentId}  (body-inline decision strip resolved)
// Shell -> content: {type:'annotate:scroll-to', anchorId}
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
  if (!frame || !frame.contentWindow) return;
  const counts = {};
  const pins = {};
  for (const [aid, items] of Object.entries(STORE.anchors || {})) {
    // F9: unresolved decision cards get a pin + strip on whichever version
    // is being viewed (adapter.js skips the strip if the anchor no longer
    // exists in this version's document).
    const list = items.filter(onCurrentVersion);
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
          // v2.19 round mode: verdict recorded but not yet sent.
          roundPending: isRoundPending(c),
        };
      })
      .sort((a, b) => a.n - b.n);
  }
  // `rounds` tells the adapter to post its own verdicts with defer_push;
  // `changes` tells it the server offers the D2 "Request changes" verdict;
  // `select` tells it a custom option id posts the D3 `select` verdict.
  frame.contentWindow.postMessage({ type: 'annotate:comment-counts', counts, pins, rounds: roundsEnabled(), changes: changesEnabled(), select: selectVerdictId() === 'select' }, '*');
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
  // One delegated keydown handler on the document: Ctrl/Cmd+Enter submits
  // whichever comment composer holds focus, so every composer behaves
  // identically and the binding survives drawer re-renders. The reply and
  // decision-comment textareas used to wire their own per-render listeners,
  // which drifted apart and left the general-feedback box with no shortcut.
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { closePopover(); closePinPopover(); cancelRepin(); closeRoundConfirm(); }
    if (!(e.key === 'Enter' && (e.ctrlKey || e.metaKey))) return;
    const t = e.target;
    if (isRoundConfirmOpen()) {
      e.preventDefault();
      submitRound();
    } else if (document.getElementById('popover').classList.contains('vis')) {
      savePopover();
    } else if (t.classList.contains('reply-ta')) {
      e.preventDefault();
      const btn = document.querySelector('[data-action="reply"][data-id="' + cssEsc(t.dataset.replyFor) + '"]');
      if (btn) btn.click();
    } else if (t.classList.contains('decision-comment-ta')) {
      e.preventDefault();
      const btn = document.querySelector('[data-decision-action="comment-submit"][data-id="' + cssEsc(t.dataset.decisionCommentTa) + '"]');
      if (btn) btn.click();
    } else if (t.classList.contains('decision-say-ta')) {
      e.preventDefault();
      const btn = document.querySelector('[data-decision-action="say-submit"][data-id="' + cssEsc(t.dataset.decisionSayTa) + '"]');
      if (btn) btn.click();
    } else if (t.id === 'gf-ta') {
      e.preventDefault();
      const save = document.getElementById('gf-save');
      if (save) save.click();
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
  renderRoundBar();
  renderOwnerChip();
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
    } else if (e.target && e.target.classList && e.target.classList.contains('decision-note-ta')) {
      setDraft('note:' + e.target.dataset.decisionNoteTa, e.target.value || '');
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
  wireMobileChrome();
  wireRoundBar();
  wireBridge();

  await loadStore();
  await loadMeta();
  await loadSessionMonitor();
  await loadCapabilities(); // v2.19: the ONE probe; 404 → legacy mode for this page load

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
