// ── annotate content adapter ─────────────────────────────────────────
// Injected by sync_server.py into every /content?v=vN response, just
// before </body>. NEVER baked into the content/*.html files on disk —
// this keeps the interactivity layer swappable independent of content.
//
// Responsibilities:
//   - Read the anchor registry the extraction step embedded as
//     <script type="application/json" id="anchor-registry-data">
//   - Click-to-comment: click any [data-anchor-id] or legacy id="sec-*"/
//     class="no" element -> postMessage 'annotate:pin-click' to the
//     parent shell (which owns the popover UI)
//   - Render comment-count pin badges when the shell sends
//     'annotate:comment-counts' (dual strategy: SVG getBBox() vs HTML
//     inline child, mirroring the old template.html drift-fix)
//   - Scroll-to-anchor + flash highlight when the shell sends
//     'annotate:scroll-to'
//   - Announce 'annotate:ready' once initialized so the shell can sync
//     pin badges + mark this version as seen
(function () {
'use strict';

const META = window.__ANNOTATE_CONTENT_META__ || {};
document.querySelectorAll('time[data-decided-time]').forEach(el => {
  el.textContent = new Date(el.dateTime).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
});

// The reviewer's text size (shell's Aa menu, same origin), before the shell
// re-sends it on load, so the document does not first draw at 100%.
try {
  const size = parseFloat(localStorage.getItem('annotate:text-size'));
  if (size >= 0.9 && size <= 2) document.documentElement.style.setProperty('--aa-text', String(size));
} catch {}

// Reading the parent proves same-origin access. srcdoc reports a null
// location origin, so use its inherited security origin only after that read.
const PARENT_ORIGIN = (() => {
  if (window.parent === window) return null;
  try {
    const origin = window.parent.location.origin;
    const inherited = origin === 'null' ? window.parent.origin : origin;
    return /^https?:\/\//.test(inherited) ? inherited : null;
  } catch { return null; }
})();
function postToParent(data) {
  if (PARENT_ORIGIN) window.parent.postMessage(data, PARENT_ORIGIN);
}

// Elements whose own click behavior must win over click-to-comment: native
// form controls, links, ARIA widgets, and the artifact chrome. Anything NOT
// matched here stays fully annotatable, so click-anywhere-to-comment is
// unchanged everywhere else. Add [data-annotate-interactive] to opt a custom
// widget in; Alt/Option-click opts back out for a one-off comment.
const INTERACTIVE_SEL = [
  'a[href]', 'button', 'input', 'select', 'textarea', 'option', 'optgroup',
  'label', 'summary', 'audio[controls]', 'video[controls]',
  '[contenteditable]:not([contenteditable="false"])',
  '[tabindex]:not([tabindex="-1"]):not(.unified-table-scroll)',
  '[role="button"]', '[role="link"]', '[role="checkbox"]', '[role="radio"]',
  '[role="combobox"]', '[role="listbox"]', '[role="option"]', '[role="menu"]',
  '[role="menuitem"]', '[role="menuitemcheckbox"]', '[role="menuitemradio"]',
  '[role="slider"]', '[role="spinbutton"]', '[role="switch"]', '[role="tab"]',
  '[role="textbox"]', '[role="searchbox"]',
  '[data-annotate-interactive]',
  '.col-resize-handle', '.title-collapse-toggle', '.alink', 'th.sortable',
].join(',');

let ANCHOR_REGISTRY = {};
try {
  const el = document.getElementById('anchor-registry-data');
  if (el) ANCHOR_REGISTRY = JSON.parse(el.textContent || '{}');
} catch (e) { console.warn('[adapter] failed to parse anchor-registry-data', e); }

let latestCounts = {};
// Per-anchor comment metadata from the shell:
// {anchorId: [{id, n, unread, target}]}
// where n is the comment's per-version number (mirrored on the sidebar card,
// so pin #7 on the page == card #7 in the drawer). `target` is the optional
// creation-time inner element/click offset used for granular pin placement.
let latestPins = {};
// {anchorId: {state: 'review'|'waiting'|'done', label}} for question cards.
let latestCardStates = {};
// When a text selection opened the composer, swallow the click that ends it.
let selectionOpenedAt = 0;

function cssEsc(s) {
  return String(s).replace(/(["\\\[\]\(\)])/g, '\\$1');
}

// ── Mobile layout detection ──────────────────────────────────────────
// Matches shell.css/shell.js's breakpoint exactly (own copy: this script
// runs inside the content iframe, a separate window from the shell page).
function isMobileLayout() {
  return window.matchMedia('(max-width: 768px), (max-height: 480px)').matches;
}

function findAnchorEl(anchorId) {
  return document.querySelector('[data-anchor-id="' + cssEsc(anchorId) + '"]') || document.getElementById(anchorId);
}

// The element that stands for an anchor on screen. A generated question card
// the interactive strip replaces is hidden (renderDecisionStrips), so pins,
// hover and scroll-to land on its strip instead of on a zero-size box.
// A question's strip is its location: the static card it replaces is hidden,
// and a page built without a "Questions" section has no element for the
// card's own d:qN anchor at all, only the strip at its evidence.
function displayAnchorEl(anchorId) {
  const el = findAnchorEl(anchorId);
  if (!el || (el.dataset && el.dataset.annotateReplaced)) {
    const strip = document.querySelector('.annotate-decision-strip[data-strip-anchor="' + cssEsc(anchorId) + '"]');
    if (strip) return strip;
  }
  return el;
}

// ── Click -> parent anchor resolution (mirrors legacy findParentAnchor) ──
function findParentAnchor(el) {
  let cur = el;
  while (cur && cur !== document.body) {
    if (cur.dataset && cur.dataset.anchorId) return cur;
    if (cur.classList && cur.classList.contains('no') && cur.id) return cur;
    cur = cur.parentElement;
  }
  return null;
}
function getAnchorIdFromEl(el) {
  if (!el) return null;
  if (el.dataset && el.dataset.anchorId) return el.dataset.anchorId;
  if (el.id) return el.id;
  return null;
}
function anchorName(anchorId) {
  // A table row reads "<section name> · row <row label>".
  const row = /^tbl:(.+):row:(.+)$/.exec(anchorId || '');
  if (row) {
    const section = ANCHOR_REGISTRY['s:' + row[1]];
    return ((section && section.name) || anchorName('tbl:' + row[1])) + ' · row ' + row[2];
  }
  const e = ANCHOR_REGISTRY[anchorId];
  return (e && e.name) ? e.name : anchorId;
}

function normText(s) {
  return String(s || '').replace(/\s+/g, ' ').trim();
}

// ── Granular target capture (W3C-style multi-selector, pragmatic subset) ──
// At comment-creation click time, record WHERE inside the registered anchor
// the user actually clicked: the innermost meaningful element, described
// redundantly (id → relative CSS path → text quote → click offset) so a
// future goto can resolve it even if one selector breaks (R2: capture
// redundantly at write time, resolve by verify-then-degrade at read time).
const MEANINGFUL_TAG = /^(div|section|article|tr|td|th|li|ul|ol|table|pre|p|h1|h2|h3|h4|h5|h6|blockquote|figure|dl|dt|dd|label|svg|g|rect|text)$/i;

function cssPathFrom(root, el) {
  const segs = [];
  let cur = el;
  while (cur && cur !== root) {
    const tag = cur.tagName.toLowerCase();
    let i = 1, sib = cur;
    while ((sib = sib.previousElementSibling)) if (sib.tagName === cur.tagName) i++;
    segs.unshift(tag + ':nth-of-type(' + i + ')');
    cur = cur.parentElement;
  }
  return cur === root ? segs.join(' > ') : null;
}

// The text the reviewer selected inside one anchor, or ''.
function selectedQuoteIn(anchorEl) {
  const s = getSelection();
  if (!s || s.isCollapsed || !s.rangeCount || !anchorEl.contains(s.anchorNode) || !anchorEl.contains(s.focusNode)) return '';
  return normText(s.toString());
}

function captureTarget(clickEl, anchorEl, ev) {
  const target = captureClickTarget(clickEl, anchorEl, ev);
  const quote = anchorEl ? selectedQuoteIn(anchorEl) : '';
  if (!quote) return target;
  return Object.assign(target || { schema: 1 }, { selected_quote: quote });
}

function captureClickTarget(clickEl, anchorEl, ev) {
  const start = clickEl && clickEl.nodeType === 1 ? clickEl : (clickEl && clickEl.parentElement);
  // Climb from the click target to the first meaningful component boundary
  // strictly below the registered anchor.
  let chosen = null;
  for (let cur = start; cur && cur !== anchorEl && cur !== document.body; cur = cur.parentElement) {
    if ((cur.dataset && cur.dataset.anchorId) || cur.id || MEANINGFUL_TAG.test(cur.tagName)) {
      chosen = cur;
      break;
    }
  }
  if (!chosen || chosen === anchorEl) return null; // click was on the anchor itself
  const target = { schema: 1 };
  if (chosen.dataset && chosen.dataset.anchorId) target.inner_anchor_id = chosen.dataset.anchorId;
  if (chosen.id) target.inner_dom_id = chosen.id;
  const css = cssPathFrom(anchorEl, chosen);
  if (css) target.css = css;
  const quote = normText(chosen.textContent).slice(0, 160);
  if (quote) target.quote = quote;
  const cls = typeof chosen.className === 'string' ? chosen.className : '';
  target.tag = chosen.tagName.toLowerCase() + (cls ? '.' + cls.split(/\s+/).filter(Boolean).slice(0, 2).join('.') : '');
  if (ev) {
    const r = chosen.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) {
      target.offset = {
        dx: Math.round(((ev.clientX - r.left) / r.width) * 1000) / 1000,
        dy: Math.round(((ev.clientY - r.top) / r.height) * 1000) / 1000,
      };
    }
  }
  return target;
}

// Resolve a captured target back to a DOM element inside its anchor.
// Order (per R2 verify-then-degrade): inner anchor id → DOM id → relative
// CSS path (quote-verified when possible) → smallest element containing the
// quote → null (caller falls back to the section anchor). Never lands on a
// wrong-but-plausible element: css hits are quote-verified, quote hits take
// the tightest match.
function resolveInnerEl(anchorEl, target) {
  if (!target || typeof target !== 'object') return null;
  if (target.inner_anchor_id) {
    const el = findAnchorEl(target.inner_anchor_id);
    if (el) return { el, how: 'inner-anchor-id' };
  }
  if (target.inner_dom_id) {
    const el = document.getElementById(target.inner_dom_id);
    if (el) return { el, how: 'inner-dom-id' };
  }
  if (target.css) {
    try {
      const el = anchorEl.querySelector(target.css);
      if (el) {
        const t = normText(el.textContent);
        const q = target.quote || '';
        if (!q || t.indexOf(q.slice(0, 40)) !== -1 || q.indexOf(t.slice(0, 40)) !== -1) {
          return { el, how: 'css-path' };
        }
      }
    } catch {}
  }
  if (target.quote && target.quote.length >= 12) {
    const q = target.quote;
    let cand = null, candLen = Infinity;
    anchorEl.querySelectorAll('*').forEach(el2 => {
      if (el2.closest('#badge-layer') || el2.closest('[data-annotate-strip]') || el2.closest('[data-annotate-back]') || el2.closest('.annotate-unchanged-bar') || el2.classList.contains('bpin-inline') || el2.tagName === 'SCRIPT' || el2.tagName === 'STYLE') return;
      const t = normText(el2.textContent);
      if (!t) return;
      if (t.indexOf(q) !== -1 || (q.length >= 60 && t.indexOf(q.slice(0, 60)) !== -1)) {
        if (t.length < candLen) { cand = el2; candLen = t.length; }
      }
    });
    if (cand) return { el: cand, how: 'text-quote' };
  }
  return null;
}

function wireClicks() {
  document.addEventListener('click', (e) => {
    if (selectionOpenedAt && performance.now() - selectionOpenedAt < 250 && !e.target.closest(INTERACTIVE_SEL)) return;
    // Pin clicks take precedence over everything, including click-to-CREATE:
    // a pin is the reverse-lookup affordance (pin -> its existing comments),
    // whereas clicking the anchor's own text/element still creates. Capture
    // phase + stopPropagation guarantees the create path below never fires
    // for a pin click.
    const pin = e.target.closest('.bpin, .bpin-inline');
    if (pin && pin.dataset.pinAnchor) {
      e.stopPropagation();
      e.preventDefault();
      // Box-pin aggregation: a pin on an outer box reveals every comment
      // anchored within that box's subtree — its own anchor plus any
      // registered anchors nested inside it (DOM containment, computed live).
      const pinAid = pin.dataset.pinAnchor;
      const anchorIds = [pinAid];
      const anchorEl = findAnchorEl(pinAid);
      if (anchorEl) {
        anchorEl.querySelectorAll('[data-anchor-id], .no[id]').forEach(d => {
          const nested = (d.dataset && d.dataset.anchorId) || d.id;
          if (nested && anchorIds.indexOf(nested) === -1) anchorIds.push(nested);
        });
      }
      // Touch tap equivalent of hover-linking (wireHoverLinking below): a
      // mouse user confirms a pin↔row pairing by hovering before clicking;
      // a touch user has no hover, so light the row for a beat right as the
      // tap opens the popover instead of skipping that confirmation.
      if (isMobileLayout() && anchorEl) {
        ensureHoverStyle();
        highlightAnchor(pinAid, true);
        setTimeout(() => highlightAnchor(pinAid, false), 1500);
      }
      postToParent({
        type: 'annotate:pin-open',
        anchorId: pinAid,
        anchorIds,
        anchorLabel: anchorName(pinAid),
        commentIds: (pin.dataset.pinComments || '').split(',').filter(Boolean),
        x: e.clientX,
        y: e.clientY,
      });
      return;
    }

    // Inline decision strips (see "Inline body decision strips" below) wire
    // their own click handlers directly on their buttons/textarea. A click on
    // any other part of a strip (prompt text, padding) must never fall
    // through to click-to-CREATE — it isn't a click on the underlying anchor.
    if (e.target.closest('[data-annotate-strip]')) return;
    // Same for the chrome this file adds around content: the "Back to #N"
    // marker an evidence jump leaves, and an unchanged section's header.
    if (e.target.closest('[data-annotate-back], .annotate-unchanged-bar')) return;

    // Don't hijack clicks on real interactive controls. This listener runs in
    // the CAPTURE phase and calls stopPropagation() below, so anything it
    // claims never receives its own click at all — a native <select> would
    // never open its dropdown, a checkbox would never toggle. Alt/Option-click
    // overrides the bail-out so a control can still be annotated deliberately.
    if (!e.altKey && e.target.closest(INTERACTIVE_SEL)) return;

    let target = findParentAnchor(e.target);
    if (!target) return;

    if (e.shiftKey) {
      const reg = ANCHOR_REGISTRY[getAnchorIdFromEl(target)];
      if (reg && reg.parent) {
        const parentEl = findAnchorEl(reg.parent);
        if (parentEl) target = parentEl;
      }
    }
    const aid = getAnchorIdFromEl(target);
    if (!aid) return;
    e.stopPropagation();

    document.querySelectorAll('[data-anchor-id].active, .no.active').forEach(el => el.classList.remove('active'));
    target.classList.add('active');

    postToParent({
      type: 'annotate:pin-click',
      anchorId: aid,
      anchorLabel: anchorName(aid),
      // Granular capture: exactly which inner element was clicked (null when
      // the click was on the anchor itself). Stored on the comment so goto
      // can return to the precise spot, not just the section.
      target: captureTarget(e.target, target, e),
      x: e.clientX,
      y: e.clientY,
    });
  }, true);
}

// Compatibility shim for content recovered from a baked legacy artifact.
// Those documents were authored against template.html, whose chrome defined a
// global openPopover(); in-canvas affordances ("comment on this row" buttons)
// call it directly. The chrome no longer ships with the content, so without
// this the buttons would silently no-op — they are guarded by
// `typeof openPopover === 'function'`, which fails quietly rather than loudly.
// Route them through the same pin-click path a normal click takes.
if (typeof window.openPopover !== 'function') {
  window.openPopover = function (anchorId, x, y) {
    if (!anchorId) return;
    const el = findAnchorEl(anchorId);
    if (el) {
      document.querySelectorAll('[data-anchor-id].active, .no.active')
        .forEach(n => n.classList.remove('active'));
      el.classList.add('active');
    }
    postToParent({
      type: 'annotate:pin-click',
      anchorId: anchorId,
      anchorLabel: anchorName(anchorId),
      target: null,
      x: typeof x === 'number' ? x : 0,
      y: typeof y === 'number' ? y : 0,
    });
  };
}

// ── Pin badges (dual SVG / HTML strategy — mirrors template.html renderBadges) ──
function ensureBadgeLayer() {
  let layer = document.getElementById('badge-layer');
  if (!layer) {
    layer = document.createElement('div');
    layer.id = 'badge-layer';
    layer.style.cssText = 'position:absolute;inset:0;pointer-events:none;overflow:visible;z-index:10';
    const wrapper = document.getElementById('canvas-wrapper') || document.body;
    wrapper.style.position = wrapper.style.position || 'relative';
    wrapper.appendChild(layer);
  }
  return layer;
}

// Pins are CLICKABLE (reverse lookup: pin -> its comments in the shell
// drawer). Base geometry stays inline (computed per-position); interaction
// affordances live in one injected style block.
function ensurePinStyle() {
  if (document.getElementById('annotate-pin-style')) return;
  const style = document.createElement('style');
  style.id = 'annotate-pin-style';
  style.textContent = `
    .bpin, .bpin-inline { pointer-events: auto; cursor: pointer; }
    .bpin:hover, .bpin-inline:hover {
      box-shadow: 0 0 0 3px color-mix(in oklab,var(--color-primary) 35%,transparent), 0 1px 4px color-mix(in oklab,var(--color-neutral) 25%,transparent) !important;
    }
    .bpin-unread { background: var(--color-error) !important; }
    .bpin-cluster {
      background: var(--color-primary) !important;
      box-shadow: 0 0 0 2px var(--color-base-100), 0 1px 4px color-mix(in oklab,var(--color-neutral) 35%,transparent) !important;
    }
    .bpin-cluster:hover {
      box-shadow: 0 0 0 2px var(--color-base-100), 0 0 0 5px color-mix(in oklab,var(--color-primary) 35%,transparent) !important;
    }
    /* Decision pins take priority over unread/cluster styling — placed
       last so equal-specificity !important rules resolve in its favor. */
    .bpin-decision {
      background: var(--color-primary) !important;
      box-shadow: 0 0 0 3px var(--color-base-100), 0 1px 4px color-mix(in oklab,var(--color-neutral) 30%,transparent) !important;
      animation: bpinDecisionPulse 1.5s ease-in-out 3;
    }
    @keyframes bpinDecisionPulse {
      0%, 100% { box-shadow: 0 0 0 3px var(--color-base-100), 0 0 0 3px color-mix(in oklab,var(--color-primary) 50%,transparent); }
      50% { box-shadow: 0 0 0 3px var(--color-base-100), 0 0 0 8px color-mix(in oklab,var(--color-primary) 0%,transparent); }
    }
    @media (max-width: 768px), (max-height: 480px) {
      /* No 300ms tap delay + no accidental text selection on a fast tap. */
      .bpin, .bpin-inline { touch-action: manipulation; }
      /* AC: pins need a >=44px tap target, but a 44px VISUAL dot would
         blanket the diagram at any real pin density. Keep the rendered pin
         at its enlarged-but-still-compact 26px (PIN_SIZE_MOBILE) and widen
         only the invisible hit area via a same-positioning-context
         pseudo-element — the pin is already position:absolute (inline
         style from renderBadges), which is what lets an inset ::before
         extend its clickable box without moving the visible dot. */
      .bpin::before, .bpin-inline::before {
        content: ''; position: absolute; inset: -9px;
      }
    }
  `;
  document.head.appendChild(style);
}

const PIN_SIZE_DESKTOP = 18; // px — keep in sync with pinBaseCss()
const PIN_SIZE_MOBILE = 26;  // px — larger touch target (AC: pins scale up on touch devices)
// Computed live (not a cached const): a version switch reloads this whole
// document, but a resize crossing the mobile breakpoint within one document
// lifetime must still get the right size on the next badge refresh —
// scheduleBadgeRefresh() already re-renders on resize, so this just needs
// to reflect the CURRENT viewport each time it's called.
function PIN_SIZE() { return isMobileLayout() ? PIN_SIZE_MOBILE : PIN_SIZE_DESKTOP; }
function pinBaseCss() {
  const s = PIN_SIZE();
  return `width:${s}px;height:${s}px;color:var(--color-primary-content);border-radius:50%;font-size:${s > 20 ? 11 : 9.5}px;font-weight:700;display:flex;align-items:center;justify-content:center;box-shadow:0 1px 4px color-mix(in oklab,var(--color-neutral) 25%,transparent);background:var(--color-primary)`;
}

// Build one pin element. `entries` = the comment(s) this pin represents
// ([{id, n, unread}]); a single-comment pin shows its number, a cluster pin
// shows the count. Clicking either sends 'annotate:pin-open' (see wireClicks).
function makePin(anchorId, entries, isCluster) {
  const b = document.createElement('div');
  b.style.cssText = pinBaseCss();
  b.dataset.pinAnchor = anchorId;
  b.dataset.pinComments = entries.map(x => x.id).join(',');
  const hasDecision = entries.some(x => x.decision);
  if (hasDecision) b.classList.add('bpin-decision');
  if (isCluster) {
    b.classList.add('bpin-cluster');
    b.textContent = String(entries.length);
    b.title = anchorName(anchorId) + ': ' + entries.length + ' comments (#' +
      entries.map(x => x.n).join(', #') + ')' + (hasDecision ? ' — decision needed' : '') + ' — click to view';
  } else {
    b.textContent = String(entries[0].n);
    if (entries[0].unread) b.classList.add('bpin-unread');
    b.title = anchorName(anchorId) + ': comment #' + entries[0].n +
      (entries[0].unread ? ' (unread)' : '') +
      (entries[0].decision ? ' — decision needed' : '') + ' — click to view';
  }
  b.setAttribute('role', 'button');
  b.tabIndex = 0;
  b.setAttribute('aria-label', 'Open feedback ' + entries.map(x => '#' + x.n).join(', '));
  b.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); b.click(); }
  });
  return b;
}

// Legacy comments without granular targets stay grouped at the anchor corner:
// up to 3 numbered pins, then a cluster. If any comment on the anchor has a
// creation-time target, keep the comments individually numbered so each new
// pin can live at its own clicked position inside the larger box.
// A function, not a const, for the same reason as PIN_SIZE(): must reflect
// the current viewport, and the larger mobile pin (26px) needs more spacing
// between stacked/nudged pins than the desktop 18px one to avoid overlap.
function PIN_SPACING() { return PIN_SIZE() + 2; }
function pinSpecsFor(anchorId) {
  const entries = (latestPins[anchorId] || []).slice().sort((a, b) => parseInt(a.n, 10) - parseInt(b.n, 10));
  if (!entries.length) {
    // Shell predates pins payload (or race before first counts message):
    // degrade to a count cluster so the badge never vanishes. Empty
    // data-pin-comments makes the shell list every comment on this anchor.
    const count = latestCounts[anchorId] || 0;
    if (!count) return [];
    const b = makePin(anchorId, [], true);
    b.textContent = String(count);
    b.title = anchorName(anchorId) + ': ' + count + ' comment(s) — click to view';
    return [{ pin: b, entry: null }];
  }
  const hasGranular = entries.some(en => en.target && en.target.offset);
  if (entries.length > 3 && !hasGranular) {
    return [{ pin: makePin(anchorId, entries, true), entry: null }];
  }
  return entries.map(en => ({ pin: makePin(anchorId, [en], false), entry: en }));
}

function clamp01(value, fallback) {
  return typeof value === 'number' && Number.isFinite(value)
    ? Math.max(0, Math.min(1, value))
    : fallback;
}

function pinPoint(anchorEl, entry, wrapperRect) {
  const resolved = entry && entry.target ? resolveInnerEl(anchorEl, entry.target) : null;
  const row = (resolved ? resolved.el : anchorEl).closest && (resolved ? resolved.el : anchorEl).closest('tr');
  if (row) {
    const rect = row.getBoundingClientRect();
    const scroll = row.closest('.unified-table-scroll');
    const edge = scroll ? scroll.getBoundingClientRect().left : rect.left;
    return { left: edge - wrapperRect.left - PIN_SIZE() - 4, top: rect.top - wrapperRect.top + rect.height / 2 - PIN_SIZE() / 2, granular: false, centered: true };
  }
  const placementEl = resolved ? resolved.el : anchorEl;
  const rect = placementEl.getBoundingClientRect();
  if (!rect.width && !rect.height) return null;
  const offset = resolved && entry.target && entry.target.offset;
  if (offset) {
    return {
      left: rect.left - wrapperRect.left + clamp01(offset.dx, 0.5) * rect.width,
      top: rect.top - wrapperRect.top + clamp01(offset.dy, 0.5) * rect.height,
      granular: true,
    };
  }
  // Legacy (non-granular) placement: the anchor's top-right corner — EXCEPT
  // for table rows (the reported case: real decision-table rows run
  // 73-165px tall, well past any plausible "short row" height cutoff), where
  // that corner sits exactly on the shared boundary between two rows and
  // reads as belonging to either one ("pin on adjacent row looked like it
  // was for decision 7"). Centering keys off the placement element's OWN
  // tag (a real <tr>, whatever its height) rather than a height threshold —
  // a <60px height also still centers, for any non-TR row-like anchor that
  // happens to be short. Centered anchors get their pin vertically centered
  // in their own row band; renderBadges renders this WITHOUT the corner
  // case's translate(0,-100%) shift (point.centered below), so the pin's
  // true rendered center lands on rect's vertical midpoint, unambiguously
  // inside the row. Non-TR, taller-than-60px elements are unaffected — same
  // corner placement as before.
  const centered = placementEl.tagName === 'TR' || (rect.height > 0 && rect.height <= 60);
  return {
    left: rect.right - wrapperRect.left,
    top: centered
      ? rect.top - wrapperRect.top + rect.height / 2 - PIN_SIZE() / 2
      : rect.top - wrapperRect.top,
    granular: false,
    centered,
  };
}

// A pin's left is wrapper-relative; wrapperRect.left + left is its absolute
// viewport x. Legacy corner placement (rect.right of a wide/overflowing
// element, e.g. a table row wider than its own scroll container) or the
// collision nudge below can push that past the visible viewport edge — the
// badge layer doesn't clip, so an unclamped pin inflates the document's
// horizontal scrollWidth and forces an unwanted scrollbar. Only the right
// bound is pulled in: vertical page scroll is normal and expected, so top
// is left untouched.
function clampPinLeft(left, wrapperRect, granular) {
  // Mobile pins extend their invisible hit area by 9px; reserve all of it
  // so the touch target does not add a 1px horizontal scrollbar.
  const inset = isMobileLayout() ? 9 : 8;
  const viewportW = document.documentElement.clientWidth || window.innerWidth;
  // `left` is the pin's CSS left, not its right edge: a granular pin is
  // horizontally centered on it (translate(-50%,...)), so only half its box
  // extends past `left`, but a legacy corner pin (translate(0,-100%)) has
  // `left` AS its left edge, so the full box extends past it. Reserve the
  // right amount or the pin's own width still pokes past the clamp target.
  const reserve = granular ? PIN_SIZE() / 2 : PIN_SIZE();
  const maxLeft = viewportW - wrapperRect.left - inset - reserve;
  return Number.isFinite(maxLeft) && left > maxLeft ? Math.max(inset, maxLeft) : left;
}

function renderBadges() {
  ensurePinStyle();
  document.querySelectorAll('.bpin-inline').forEach(p => p.remove());
  const layer = ensureBadgeLayer();
  layer.innerHTML = '';

  positionBackPill();
  for (const [anchorId, count] of Object.entries(latestCounts)) {
    if (!count) continue;
    const el = displayAnchorEl(anchorId);
    if (!el) continue;

    // Skip elements hidden inside a non-active tab-panel/sub-panel.
    const panel = el.closest('.tab-panel');
    if (panel && !panel.classList.contains('active')) continue;
    const subPanel = el.closest('.sub-panel');
    if (subPanel && !subPanel.classList.contains('active')) continue;

    const specs = pinSpecsFor(anchorId);
    if (!specs.length) continue;
    const wrapper = layer.parentElement;
    if (!wrapper) continue;
    const wrapperRect = wrapper.getBoundingClientRect();
    const occupied = new Map();

    specs.forEach((spec, i) => {
      const point = pinPoint(el, spec.entry, wrapperRect);
      if (!point) return;
      const b = spec.pin;
      b.classList.add('bpin');
      b.style.position = 'absolute';
      b.style.zIndex = '20';

      let finalLeft;
      if (point.granular) {
        // Two clicks can resolve to effectively the same pixel. Nudge later
        // numbers sideways instead of hiding them under the first pin.
        const key = Math.round(point.left / 8) + ':' + Math.round(point.top / 8);
        const collisionIndex = occupied.get(key) || 0;
        occupied.set(key, collisionIndex + 1);
        finalLeft = point.left + collisionIndex * PIN_SPACING();
        b.style.top = point.top + 'px';
        b.style.transform = 'translate(-50%,-50%)';
      } else {
        finalLeft = point.left - (specs.length - 1 - i) * PIN_SPACING();
        b.style.top = point.top + 'px';
        // Centered pins (see pinPoint's `centered` flag) already carry their
        // own vertical center in `top` — no corner shift. Everything else
        // keeps the original top-right-corner placement (bottom-anchored
        // via -100%). Single shared flag, not a re-derived condition, so
        // this can never drift out of sync with pinPoint's own predicate.
        b.style.transform = point.centered ? 'translate(0,0)' : 'translate(0,-100%)';
      }
      b.style.left = clampPinLeft(finalLeft, wrapperRect, point.granular) + 'px';
      layer.appendChild(b);
    });
  }
}

let badgeRefreshTimer = null;
function scheduleBadgeRefresh() {
  clearTimeout(badgeRefreshTimer);
  // Piggyback content-fullscreen detection on the same mutation-driven
  // cadence: the ⛶ toggle (and its Esc exit) mutate the host's style
  // attribute, which is exactly what the badge MutationObserver watches.
  badgeRefreshTimer = setTimeout(() => {
    renderBadges();
    detectContentFullscreen();
  }, 80);
}
let stripRefresh = 0;
function scheduleStripRefresh() {
  if (stripRefresh) return;
  stripRefresh = requestAnimationFrame(() => {
    stripRefresh = 0;
    renderDecisionStrips();
    renderBadges();
    postExcerpts();
  });
}

function installBadgeMutObs() {
  const target = document.getElementById('canvas-wrapper') || document.body;
  const obs = new MutationObserver(mutations => {
    // Badge rendering itself mutates #badge-layer. Ignore those mutations or
    // the observer schedules an endless 80ms re-render loop.
    const contentChanged = mutations.some(m => {
      const el = m.target && m.target.nodeType === 1 ? m.target : m.target.parentElement;
      return !(el && el.closest && el.closest('#badge-layer'));
    });
    if (contentChanged) scheduleBadgeRefresh();
    // A document tab switched: its questions render at their evidence now.
    if (mutations.some(m => m.type === 'attributes' && m.attributeName === 'class' &&
        m.target.matches && m.target.matches('.tab-panel, .sub-panel'))) scheduleStripRefresh();
  });
  obs.observe(target, { subtree: true, childList: true, attributes: true, attributeFilter: ['class', 'style'] });
  // Granular pins live in a shared overlay so they work for HTML and SVG.
  // Recompute geometry when any nested diagram/document scroller moves.
  document.addEventListener('scroll', scheduleBadgeRefresh, true);
  document.addEventListener('toggle', scheduleBadgeRefresh, true);
  window.addEventListener('resize', scheduleBadgeRefresh);
}

// ── Hover linking: pin <-> anchor <-> strip ──────────────────────────
// Kills the same adjacent-row ambiguity the pin-centering fix above targets,
// from a different angle: hovering a pin lights up the row it belongs to
// (and vice versa), so a reviewer can visually confirm the pairing before
// clicking anything. Cheap and generic — two document-level delegated
// listeners, no per-pin/per-anchor wiring, so newly rendered pins/strips/
// anchors need no extra setup.
function ensureHoverStyle() {
  if (document.getElementById('annotate-hover-style')) return;
  const style = document.createElement('style');
  style.id = 'annotate-hover-style';
  style.textContent = `
    .annotate-anchor-hl {
      outline: 2px solid var(--link) !important;
      outline-offset: -1px !important;
      background: color-mix(in oklab,var(--color-primary) 6%,transparent) !important;
    }
    .bpin-hl {
      transform: scale(1.25) !important;
      box-shadow: 0 0 0 3px var(--color-base-100), 0 0 0 6px color-mix(in oklab,var(--color-primary) 45%,transparent) !important;
    }
  `;
  document.head.appendChild(style);
}

function highlightAnchor(anchorId, on) {
  const el = anchorId && displayAnchorEl(anchorId);
  if (el) el.classList.toggle('annotate-anchor-hl', on);
}
function highlightPinsFor(anchorId, on) {
  document.querySelectorAll(
    '.bpin[data-pin-anchor="' + cssEsc(anchorId) + '"], .bpin-inline[data-pin-anchor="' + cssEsc(anchorId) + '"]'
  ).forEach(p => p.classList.toggle('bpin-hl', on));
}

// Strip -> anchor id: only the strip's own wrapper carries data-strip-anchor
// (buildStripEl); the optional outer <tr> wrapper (TR-anchor case) does not.
function stripAnchorIdFromEl(el) {
  const strip = el.closest('[data-strip-anchor]');
  return strip ? strip.dataset.stripAnchor : null;
}

// Hover feedback is for a mouse only. A tap on iPad also fires mouseover; a
// highlight added then makes iOS treat the tap as a hover and drop the click,
// so every choice took two taps (Chang, 2026-10-31).
const byMouse = e => e.pointerType === 'mouse';
function wireHoverLinking() {
  ensureHoverStyle();
  document.addEventListener('pointerover', (e) => {
    if (!byMouse(e)) return;
    const pin = e.target.closest('.bpin, .bpin-inline');
    if (pin && pin.dataset.pinAnchor) { highlightAnchor(pin.dataset.pinAnchor, true); return; }
    const stripAid = stripAnchorIdFromEl(e.target);
    if (stripAid) { highlightAnchor(stripAid, true); return; }
    const anchorEl = e.target.closest('[data-anchor-id], .no[id]');
    if (anchorEl) {
      const aid = getAnchorIdFromEl(anchorEl);
      if (aid && latestPins[aid] && latestPins[aid].length) highlightPinsFor(aid, true);
    }
  });
  document.addEventListener('pointerout', (e) => {
    if (!byMouse(e)) return;
    const pin = e.target.closest('.bpin, .bpin-inline');
    if (pin && pin.dataset.pinAnchor) { highlightAnchor(pin.dataset.pinAnchor, false); return; }
    const stripAid = stripAnchorIdFromEl(e.target);
    if (stripAid) { highlightAnchor(stripAid, false); return; }
    const anchorEl = e.target.closest('[data-anchor-id], .no[id]');
    if (anchorEl) {
      const aid = getAnchorIdFromEl(anchorEl);
      if (aid) highlightPinsFor(aid, false);
    }
  });
}

// ── Question cards in the body ───────────────────────────────────────
// The rail card and the card drawn here, at the anchored element, are one
// card: shell.js builds both (renderDecisionBlock; stripCard gives this
// document its copy, with this document's classes, wired to the same actions),
// so a reviewer scanning the body never has to open the drawer to answer.
// Rebuilt only when the shell sends a fresh 'annotate:comment-counts' message
// (see wireBridge) — NOT on every resize/scroll-driven badge refresh, so DOM
// insertion here can never feed back into the MutationObserver above and loop.
function cardApi() {
  try { return PARENT_ORIGIN ? window.parent.AnnotateDocs : null; } catch { return null; }
}
// "Show more" under a quoted excerpt only when its clamp cuts the text off.
function syncAllExcerptClamps(root) {
  const api = cardApi();
  if (api && api.syncClamps) api.syncClamps(root || document);
}

function ensureStripStyle() {
  if (document.getElementById('annotate-strip-style')) return;
  const style = document.createElement('style');
  style.id = 'annotate-strip-style';
  style.textContent = `
    .annotate-questions-moved { display: none !important; }
    .annotate-decision-strip {
      font-family:"Inter", sans-serif !important;
      background: var(--primary-soft) !important;
      border: 1.5px solid var(--link) !important;
      border-radius: 8px !important;
      padding: 8px 10px !important;
      margin: 6px 0 !important;
      box-sizing: border-box !important;
      max-width: 100% !important;
      display: block !important;
      text-align: left !important;
    }
    .annotate-decision-accept { color:var(--color-success-content) !important; }
    .annotate-decision-reject { color:var(--color-error-content) !important; }
    .annotate-decision-changes { color:var(--color-warning-content) !important; }
    .bpin-unread { color:var(--color-error-content) !important; }
    .annotate-strip-tr > td { padding: 0 !important; border: none !important; background: transparent !important; }
    .annotate-strip-abs { pointer-events: auto !important; }
    .annotate-decision-item + .annotate-decision-item {
      margin-top: 8px !important; padding-top: 8px !important;
      border-top: 1px solid color-mix(in oklab,var(--color-primary) 25%,transparent) !important;
    }
    .annotate-decision-prompt {
      font-size: calc(12px * var(--aa-text, 1)) !important; font-weight: 600 !important; color: var(--link) !important;
      margin: 0 0 6px !important; line-height: 1.4 !important; white-space: normal !important;
    }
    .annotate-decision-num { display: inline-block !important; margin-right: 6px !important; font-weight: 800 !important; color: var(--link) !important; }
    .annotate-decision-resolved .annotate-decision-prompt { margin-bottom: 5px !important; }
    .annotate-decision-text {
      font-size: calc(11.5px * var(--aa-text, 1)) !important; color: var(--color-base-content) !important; line-height: 1.5 !important;
      margin: -2px 0 6px !important; white-space: pre-wrap !important; word-break: break-word !important;
    }
    /* Options are rows (radio-tile layout): label, its consequence under it,
       a Recommended badge, nothing preselected. One click still answers. */
    .annotate-decision-btns {
      display: flex !important; flex-direction: column !important; align-items: stretch !important;
      gap: 6px !important; min-width: 0 !important;
    }
    .annotate-decision-btn {
      font-size: calc(11px * var(--aa-text, 1)) !important; font-weight: 700 !important; padding: 5px 11px !important;
      border-radius: 6px !important; border: none !important; cursor: pointer !important;
      color:var(--color-primary-content) !important; font-family:"Inter", sans-serif !important;
      /* An option label longer than the strip used to force the flex line
         wider than the page; the button and its consequence line then ran
         off the right edge (user-reported). */
      max-width: 100% !important; min-width: 0 !important; text-align: left !important;
      line-height: 1.35 !important; white-space: normal !important; overflow-wrap: anywhere !important;
    }
    .annotate-decision-btn:hover { filter: brightness(.92) !important; }
    /* UI-25: Enter on a focused option answers it, so the focus must show. */
    .annotate-decision-btn:focus-visible { outline: 2px solid var(--color-primary) !important; outline-offset: 2px !important; }
    .annotate-decision-btn:disabled { opacity: .55 !important; cursor: not-allowed !important; filter: none !important; }
    .annotate-decision-accept { background: var(--color-success) !important; }
    .annotate-decision-reject { background: var(--color-error) !important; }
    .annotate-decision-comment { background: var(--color-primary) !important; }
    /* D2 "Request changes": amber, deliberately not Reject's red. */
    .annotate-decision-changes { background: var(--warn-text) !important; }
    /* display is intentionally NOT set here: it's driven entirely by the
       inline style.setProperty(..., 'important') toggle in JS (open/closed),
       which an author-stylesheet !important rule here would permanently
       defeat. */
    .annotate-decision-ta {
      width: 100% !important; min-height: 40px !important; padding: 5px 7px !important;
      border: 1px solid var(--line) !important; border-radius: 5px !important; font-size: calc(11px * var(--aa-text, 1)) !important;
      font-family:"Inter", sans-serif !important; resize: vertical !important; color: var(--color-base-content) !important;
      background: var(--color-base-100) !important; box-sizing: border-box !important; line-height: 1.4 !important;
    }
    .annotate-decision-ta:focus { outline: none !important; border-color: var(--link) !important; }
    .annotate-decision-feedback {
      margin-top: 5px !important; font-size: calc(10.5px * var(--aa-text, 1)) !important; font-weight: 600 !important;
      color: var(--link) !important; min-height: 12px !important;
    }
    .annotate-decision-feedback.is-error { color: var(--color-error) !important; }
    .annotate-decision-feedback:empty { min-height: 0 !important; margin-top: 0 !important; }
    .annotate-verdict-chip {
      display: inline-block !important; font-size: calc(10.5px * var(--aa-text, 1)) !important; font-weight: 700 !important;
      padding: 4px 10px !important; border-radius: 10px !important;
    }
    .annotate-verdict-chip.verdict-accept { background: var(--success-soft) !important; color: var(--ok-text) !important; }
    .annotate-verdict-chip.verdict-reject { background: var(--error-soft) !important; color: var(--color-error) !important; }
    .annotate-verdict-chip.verdict-comment { background: var(--primary-soft) !important; color: var(--link) !important; }
    .annotate-verdict-chip.verdict-changes { background: var(--warning-soft) !important; color: var(--warn-text) !important; }
    .annotate-decision-cancel {
      background: none !important; color: var(--link) !important; font-weight: 600 !important;
      padding: 4px 6px !important; margin-left: 6px !important; text-decoration: none !important;
    }
    .annotate-decision-cancel:hover { filter: none !important; text-decoration: underline !important; }
    .annotate-decision-changing-note {
      display: flex !important; align-items: center !important; justify-content: space-between !important;
      gap: 8px !important; font-size: calc(11px * var(--aa-text, 1)) !important; font-weight: 600 !important; color: var(--link) !important;
      background: var(--primary-soft) !important; border-radius: 6px !important; padding: 5px 8px !important;
      margin-bottom: 6px !important;
    }
    .annotate-strip-anchor-label {
      font-size: calc(10px * var(--aa-text, 1)) !important; font-weight: 700 !important; color: var(--muted) !important;
      text-transform: uppercase !important; letter-spacing: .03em !important;
      margin: 0 0 5px !important; white-space: normal !important;
    }
    /* v2.19 fields. Context is always shown in full: it is what the
       reviewer needs to decide, so it never sits behind a disclosure. */
    .annotate-decision-context {
      font-size: calc(11px * var(--aa-text, 1)) !important; color: var(--muted) !important; line-height: 1.5 !important;
      margin: -2px 0 6px !important; white-space: pre-wrap !important; word-break: break-word !important;
      font-weight: 400 !important;
    }
    .annotate-decision-reco-line {
      font-size: calc(11px * var(--aa-text, 1)) !important; color: var(--ok-text) !important; font-weight: 600 !important;
      line-height: 1.4 !important; margin: 0 0 6px !important;
    }
    .annotate-decision-reco-line b { font-weight: 800 !important; }
    /* Quoted excerpt of the element the card is about, read from this page. */
    .annotate-excerpt {
      margin: 0 0 8px !important; padding: 5px 9px !important; background: var(--color-base-100) !important;
      border: none !important; border-left: 3px solid var(--line) !important; border-radius: 0 6px 6px 0 !important;
      min-width: 0 !important; max-width: 100% !important; box-sizing: border-box !important;
    }
    .annotate-excerpt-src {
      font-size: calc(10.5px * var(--aa-text, 1)) !important; font-weight: 700 !important; color: var(--muted) !important;
      text-transform: uppercase !important; letter-spacing: .03em !important; margin: 0 0 2px !important;
    }
    .annotate-excerpt-text {
      margin: 0 !important; padding: 0 !important; border: none !important; quotes: none !important;
      font-size: calc(11px * var(--aa-text, 1)) !important; font-style: normal !important; font-weight: 400 !important;
      color: var(--color-base-content) !important; line-height: 1.5 !important; white-space: pre-line !important;
      word-break: break-word !important; overflow-wrap: anywhere !important; background: none !important;
      display: -webkit-box !important; -webkit-box-orient: vertical !important; -webkit-line-clamp: 4 !important;
      overflow: hidden !important;
    }
    .annotate-excerpt.is-open .annotate-excerpt-text { display: block !important; -webkit-line-clamp: unset !important; overflow: visible !important; }
    .annotate-excerpt-more {
      font-size: calc(10.5px * var(--aa-text, 1)) !important; font-weight: 600 !important; color: var(--link) !important;
      background: none !important; border: none !important; padding: 2px 0 !important; margin: 2px 0 0 !important;
      cursor: pointer !important; font-family:"Inter", sans-serif !important;
    }
    .annotate-excerpt-more[hidden] { display: none !important; }
    .annotate-card-replaced { display: none !important; }
    .annotate-decision-meta { display: flex !important; gap: 5px !important; flex-wrap: wrap !important; margin: 0 0 6px !important; }
    .annotate-decision-chip {
      font-size: calc(9px * var(--aa-text, 1)) !important; font-weight: 700 !important; padding: 2px 7px !important; border-radius: 8px !important;
      text-transform: uppercase !important; letter-spacing: .04em !important; white-space: nowrap !important;
    }
    .annotate-chip-impact-low { background: var(--color-base-200) !important; color: var(--muted) !important; }
    .annotate-chip-impact-medium { background: var(--warning-soft) !important; color: var(--warn-text) !important; }
    .annotate-chip-impact-high { background: var(--error-soft) !important; color: var(--err-text) !important; }
    .annotate-chip-blocking { background: var(--color-primary) !important; color:var(--color-primary-content) !important; }
    .annotate-decision-btns > .annotate-decision-btn {
      display: block !important; width: 100% !important; box-sizing: border-box !important;
      background: var(--color-base-100) !important; color: var(--color-base-content) !important; text-align: left !important;
      border: 1px solid var(--line) !important; border-left: 4px solid var(--muted) !important;
      padding: 7px 10px !important; font-weight: 700 !important;
    }
    .annotate-decision-btns > .annotate-decision-btn:hover {
      filter: none !important; background: var(--color-base-200) !important;
      border-top-color: var(--link) !important; border-right-color: var(--link) !important; border-bottom-color: var(--link) !important;
    }
    .annotate-decision-btns > .annotate-decision-accept { border-left-color: var(--color-success) !important; }
    .annotate-decision-btns > .annotate-decision-reject { border-left-color: var(--color-error) !important; }
    .annotate-decision-btns > .annotate-decision-comment { border-left-color: var(--link) !important; }
    .annotate-decision-btns > .annotate-decision-changes { border-left-color: var(--warn-text) !important; }
    .annotate-decision-btns > .annotate-decision-custom { border-left-color: var(--muted) !important; }
    .annotate-decision-btns > .annotate-decision-custom.annotate-style-primary { border-left-color: var(--link) !important; }
    .annotate-decision-btns > .annotate-decision-custom.annotate-style-danger { border-left-color: var(--color-error) !important; }
    .annotate-opt-head { display: flex !important; align-items: center !important; gap: 6px !important; flex-wrap: wrap !important; }
    .annotate-opt-label { font-weight: 700 !important; }
    .annotate-decision-consequence {
      display: block !important; margin-top: 2px !important;
      font-size: calc(10.5px * var(--aa-text, 1)) !important; font-weight: 400 !important; color: var(--muted) !important; line-height: 1.4 !important;
      white-space: pre-wrap !important; word-break: break-word !important;
    }
    .annotate-decision-rec {
      font-size: calc(9.5px * var(--aa-text, 1)) !important; font-weight: 800 !important; letter-spacing: .05em !important;
      text-transform: uppercase !important; background: var(--success-soft) !important; color: var(--ok-text) !important;
      border: 1px solid var(--line) !important; padding: 1px 6px !important; border-radius: 999px !important;
    }
    .annotate-decision-custom { background: var(--muted) !important; }
    .annotate-decision-custom.annotate-style-primary { background: var(--color-primary) !important; }
    .annotate-decision-custom.annotate-style-danger { background: var(--color-error) !important; }
    /* Evidence: a collapsed "Evidence (n)" disclosure; each item previews its
       target inside the card, and "Go to" jumps there leaving "Back to #N". */
    .annotate-decision-evidence { display: block !important; margin: 8px 0 0 !important; font-size: calc(10.5px * var(--aa-text, 1)) !important; color: var(--muted) !important; }
    .annotate-decision-evidence-toggle, .annotate-decision-evidence-link {
      font-size: calc(10.5px * var(--aa-text, 1)) !important; font-weight: 700 !important; color: var(--link) !important;
      background: none !important; border: none !important; padding: 2px 0 !important;
      cursor: pointer !important; font-family:"Inter", sans-serif !important; display: inline-flex !important;
      align-items: center !important; gap: 4px !important; text-align: left !important;
    }
    .annotate-decision-evidence-link { font-weight: 600 !important; text-decoration: none !important; }
    .annotate-decision-evidence-label { text-decoration: underline dotted !important; }
    .annotate-decision-evidence-toggle::before, .annotate-decision-evidence-link::before {
      content: '\\25B8'; font-size: calc(9px * var(--aa-text, 1)); transition: transform .12s; text-decoration: none;
    }
    .annotate-decision-evidence-toggle[aria-expanded="true"]::before,
    .annotate-decision-evidence-link[aria-expanded="true"]::before { transform: rotate(90deg); }
    .annotate-decision-evidence-list {
      display: flex !important; flex-direction: column !important; gap: 4px !important;
      margin: 4px 0 0 !important; padding: 0 0 0 12px !important;
    }
    .annotate-decision-evidence-list[hidden], .annotate-decision-evidence-preview[hidden] { display: none !important; }
    .annotate-decision-evidence-preview {
      margin: 2px 0 2px !important; padding: 6px 8px !important; background: var(--color-base-200) !important;
      border: 1px solid var(--line) !important; border-radius: 6px !important; box-sizing: border-box !important;
    }
    .annotate-decision-evidence-preview .annotate-excerpt { margin: 0 0 6px !important; }
    .annotate-decision-evidence-missing { font-style: italic !important; color: var(--muted) !important; margin: 0 0 6px !important; }
    .annotate-decision-evidence-goto {
      font-size: calc(10.5px * var(--aa-text, 1)) !important; font-weight: 700 !important; color:var(--color-primary-content) !important; background: var(--color-primary) !important;
      border: none !important; border-radius: 5px !important; padding: 3px 10px !important;
      cursor: pointer !important; font-family:"Inter", sans-serif !important;
    }
    .annotate-decision-evidence-goto:disabled { opacity: .5 !important; cursor: not-allowed !important; }
    /* "Back to #N": left on the target by an evidence jump, returns to the card. */
    .annotate-back-row { display: block !important; list-style: none !important; margin: 4px 0 !important; padding: 0 !important; text-align: left !important; }
    .annotate-back-tr > td { padding: 3px 0 !important; border: none !important; background: transparent !important; }
    .annotate-back-pill {
      font: 700 calc(11.5px * var(--aa-text, 1)) "Inter", sans-serif !important;
      color:var(--color-primary-content) !important; background: var(--color-primary) !important; border: none !important; border-radius: 999px !important;
      padding: 5px 12px !important; cursor: pointer !important; box-shadow: 0 2px 8px color-mix(in oklab,var(--color-primary) 30%,transparent) !important;
      line-height: 1.3 !important; white-space: nowrap !important;
    }
    .annotate-back-pill:hover { background: var(--color-primary) !important; }
    .annotate-back-abs { position: absolute !important; pointer-events: auto !important; z-index: 16 !important; }
    @media (max-width: 768px), (max-height: 480px) {
      .annotate-decision-evidence-toggle, .annotate-decision-evidence-link, .annotate-excerpt-more { min-height: 44px !important; padding: 10px 4px !important; touch-action: manipulation !important; }
      .annotate-decision-evidence-goto, .annotate-back-pill { min-height: 44px !important; padding: 10px 16px !important; touch-action: manipulation !important; }
      /* The toggle's own 44px target already spaces it from the options. */
      .annotate-decision-evidence { margin-top: 0 !important; }
      /* Thumb-sized buttons, buttons free to wrap to their own row, and a
         16px textarea so iOS doesn't zoom the page in on focus. */
      .annotate-decision-btn {
        min-height: 44px !important; padding: 10px 16px !important; font-size: calc(13px * var(--aa-text, 1)) !important;
        flex: 1 1 auto !important; touch-action: manipulation !important;
      }
      .annotate-decision-ta { font-size: calc(16px * var(--aa-text, 1)) !important; min-height: 48px !important; }
      .annotate-decision-cancel { min-height: 44px !important; padding: 10px 12px !important; touch-action: manipulation !important; }
    }
    /* ── Feedback prototype (X1/E4): the strip follows the shell
       using stock daisyUI light/dark tokens. C2 keeps the question bold. */
    .annotate-decision-strip {
      background: var(--color-base-100) !important; border: 1px solid var(--line) !important;
      border-radius: .5rem !important; padding: 10px 12px !important;
      box-shadow: 0 1px 2px color-mix(in oklab,var(--color-neutral) 6%,transparent) !important; color: var(--color-base-content) !important;
    }
    .annotate-decision-item + .annotate-decision-item { border-top-color: var(--line) !important; }
    .annotate-decision-prompt { color: var(--color-base-content) !important; font-weight: 700 !important; font-size: calc(11px * var(--aa-text, 1)) !important; }
    .annotate-decision-num {
      color: var(--color-base-content) !important; background: var(--color-base-300) !important; border-radius: 999px !important;
      padding: 0 6px !important; font-size: calc(9.5px * var(--aa-text, 1)) !important; font-weight: 700 !important;
    }
    .annotate-decision-btns > .annotate-decision-btn, .annotate-decision-btns > .annotate-decision-btn:hover {
      background: var(--color-base-200) !important; color: var(--color-base-content) !important;
      border: 1px solid var(--line) !important; border-radius: .25rem !important; font-weight: 600 !important;
      box-shadow: 0 1px 1px color-mix(in oklab,var(--color-neutral) 4%,transparent) !important;
    }
    .annotate-decision-btns > .annotate-decision-btn:hover { background: var(--color-base-300) !important; }
    .annotate-decision-rec { background: color-mix(in oklab,var(--color-success) 15%,transparent) !important; color: var(--ok-text) !important; border: none !important; }
    .annotate-decision-reco-line { color: var(--ok-text) !important; }
    .annotate-excerpt { background: var(--color-base-200) !important; border-left-color: color-mix(in oklab,var(--color-primary) 45%,transparent) !important; }
    .annotate-decision-evidence-toggle, .annotate-decision-evidence-link, .annotate-excerpt-more { color: color-mix(in oklab,var(--color-base-content) 65%,transparent) !important; }
    .annotate-decision-evidence-goto { background: var(--color-base-300) !important; color: var(--color-base-content) !important; border-radius: .25rem !important; }
    .annotate-decision-ta, .annotate-decision-cmt {
      border: 1px solid color-mix(in oklab,var(--color-base-content) 20%,transparent) !important; border-radius: .25rem !important;
      background: var(--color-base-100) !important; font-size: calc(11px * var(--aa-text, 1)) !important; margin-top: 8px !important;
      min-height: 2.25rem !important; padding: 6px 8px !important;
    }
    .annotate-decision-ta:focus { outline: 2px solid color-mix(in oklab,var(--color-base-content) 50%,transparent) !important; outline-offset: 2px !important; }
    .annotate-decision-cmt-hint { font-size: calc(11px * var(--aa-text, 1)) !important; color: color-mix(in oklab,var(--color-base-content) 75%,transparent) !important; margin-top: 4px !important; }
    /* Secondary text derives from the active stock foreground token. */
    .annotate-decision-consequence, .annotate-excerpt-src { color: color-mix(in oklab,var(--color-base-content) 75%,transparent) !important; }
    .annotate-decision-cmt-hint:empty { display: none !important; }
    .annotate-decision-feedback { color: color-mix(in oklab,var(--color-base-content) 70%,transparent) !important; }
    .annotate-verdict-chip { border-radius: .5rem !important; font-weight: 700 !important; }
    .annotate-verdict-chip.verdict-accept { background: color-mix(in oklab,var(--color-success) 15%,transparent) !important; color: var(--ok-text) !important; }
    .annotate-verdict-chip.verdict-reject { background: color-mix(in oklab,var(--color-error) 15%,transparent) !important; color: var(--err-text) !important; }
    .annotate-verdict-chip.verdict-changes { background: color-mix(in oklab,var(--color-warning) 20%,transparent) !important; color: var(--warn-text) !important; }
    .annotate-verdict-chip.verdict-comment, .annotate-verdict-chip.verdict-select { background: color-mix(in oklab,var(--color-info) 15%,transparent) !important; color: var(--info-text) !important; }
    .annotate-decision-changing-note { background: var(--color-base-200) !important; color: var(--color-base-content) !important; border: 1px solid var(--line) !important; }
    .annotate-decision-cancel { color: var(--color-base-content) !important; }
    .annotate-decision-later {
      display: block !important; margin: 6px 0 !important; padding: 4px 8px !important; min-height: 0 !important; width: auto !important; background: transparent !important;
      color: color-mix(in oklab,var(--color-base-content) 70%,transparent) !important; font-weight: 600 !important;
      font-size: calc(12px * var(--aa-text, 1)) !important; border-radius: .25rem !important;
    }
    @media (pointer: coarse) { .annotate-decision-later { position: relative !important; touch-action: manipulation !important; } .annotate-decision-later::before { content: '' !important; position: absolute !important; inset: -10px 0 !important; } }
    /* Answered card: your choice, your notes, add a note (2026-10-30). Buttons
       keep their words on one line; the note text takes the rest. */
    .annotate-decision-cancel, .annotate-answer-change, .annotate-note-add, .annotate-note-cancel, .annotate-note-save {
      white-space: nowrap !important; flex: 0 0 auto !important; width: auto !important; font-size: calc(11px * var(--aa-text, 1)) !important;
    }
    .annotate-answer-row { display: flex !important; align-items: center !important; flex-wrap: wrap !important; gap: 6px 8px !important; margin-top: 6px !important; }
    .annotate-answer-lbl { font-size: calc(10px * var(--aa-text, 1)) !important; font-weight: 700 !important; text-transform: uppercase !important; letter-spacing: .03em !important; color: color-mix(in oklab,var(--color-base-content) 65%,transparent) !important; }
    .annotate-answer-choice { font-weight: 700 !important; font-size: calc(12px * var(--aa-text, 1)) !important; }
    .annotate-answer-choice.is-none { font-weight: 400 !important; color: color-mix(in oklab,var(--color-base-content) 65%,transparent) !important; }
    .annotate-answer-change, .annotate-note-cancel { background: transparent !important; color: var(--link) !important; font-weight: 600 !important; padding: 4px 8px !important; border-radius: .25rem !important; }
    .annotate-answer-notes { display: flex !important; flex-direction: column !important; gap: 6px !important; margin-top: 10px !important; }
    .annotate-answer-note { display: flex !important; align-items: flex-start !important; gap: 8px !important; padding: 8px 10px !important; border-radius: .375rem !important; background: var(--color-base-200) !important; }
    .annotate-answer-note.is-editing { flex-direction: column !important; align-items: stretch !important; }
    .annotate-answer-note-txt { flex: 1 1 auto !important; min-width: 0 !important; white-space: pre-wrap !important; overflow-wrap: anywhere !important; font-size: calc(12px * var(--aa-text, 1)) !important; line-height: 1.45 !important; }
    .annotate-note-actions { display: flex !important; align-items: center !important; justify-content: flex-end !important; gap: 4px !important; flex: 0 0 auto !important; }
    .annotate-note-icon { display: inline-flex !important; align-items: center !important; justify-content: center !important; width: 28px !important; height: 28px !important; padding: 0 !important; background: transparent !important; color: color-mix(in oklab,var(--color-base-content) 70%,transparent) !important; border-radius: .25rem !important; }
    .annotate-note-icon:hover { background: var(--color-base-300) !important; }
    .annotate-note-save { background: var(--color-primary) !important; color: var(--color-primary-content) !important; font-weight: 600 !important; padding: 4px 12px !important; border-radius: .25rem !important; }
    .annotate-send-state { display: inline-block !important; padding: 0 6px !important; border-radius: 999px !important; border: 1px solid var(--line) !important; font-size: calc(10px * var(--aa-text, 1)) !important; font-weight: 600 !important; line-height: 1.6 !important; color: color-mix(in oklab,var(--color-base-content) 70%,transparent) !important; white-space: nowrap !important; }
    .annotate-send-state.is-pending { background: var(--color-warning) !important; border-color: var(--color-warning) !important; color: var(--color-warning-content) !important; }
    .annotate-add-note { display: flex !important; align-items: flex-end !important; gap: 8px !important; margin-top: 10px !important; }
    .annotate-add-note .annotate-decision-ta { flex: 1 1 auto !important; margin-top: 0 !important; }
    .annotate-note-add { background: var(--color-base-300) !important; color: var(--color-base-content) !important; font-weight: 600 !important; padding: 6px 12px !important; border-radius: .25rem !important; min-height: 2.25rem !important; }
  `;
  document.head.appendChild(style);
}

// Overlay used only for the "neither DOM insertion strategy applies" case
// (SVG content, or a flow insertion that throws). Deliberately separate
// from #badge-layer: renderBadges() does `layer.innerHTML = ''` on every
// tick, which would silently delete a strip living in that layer.
function ensureStripLayer() {
  let layer = document.getElementById('annotate-strip-layer');
  if (!layer) {
    layer = document.createElement('div');
    layer.id = 'annotate-strip-layer';
    layer.style.cssText = 'position:absolute;inset:0;pointer-events:none;overflow:visible;z-index:15';
    const wrapper = document.getElementById('canvas-wrapper') || document.body;
    wrapper.style.position = wrapper.style.position || 'relative';
    wrapper.appendChild(layer);
  }
  return layer;
}

function evidenceOf(dr) {
  return (dr && Array.isArray(dr.evidence))
    ? dr.evidence.filter(e => e && typeof e === 'object' && typeof e.anchor === 'string' && e.anchor)
    : [];
}

// ── Excerpts: an element's text, quoted inside a card ────────────────
// Read from this document, so the card shows what it is about without the
// reviewer scrolling to find it. Block boundaries become line breaks, table
// cells are joined with " | ", and everything this file injected (strips,
// pins, markers, state chips) is left out.
const EXCERPT_MAX = 1200;
const EXCERPT_SKIP_SEL = '.aa-img-zoom, [data-annotate-strip], [data-annotate-back], .annotate-embed-note,.bpin, .bpin-inline, #badge-layer, #annotate-strip-layer, .annotate-card-state, .annotate-unchanged-bar, script, style, template, noscript';
const EXCERPT_BLOCK_TAG = /^(p|div|section|article|aside|header|footer|li|ul|ol|tr|table|thead|tbody|tfoot|caption|h1|h2|h3|h4|h5|h6|pre|blockquote|dl|dt|dd|figure|figcaption|br|hr)$/i;

function excerptText(el) {
  if (!el) return '';
  let out = '';
  const walk = (node) => {
    if (out.length > EXCERPT_MAX * 3) return;
    if (node.nodeType === 3) { out += node.nodeValue; return; }
    if (node.nodeType !== 1) return;
    if (node.matches && node.matches(EXCERPT_SKIP_SEL)) return;
    const block = EXCERPT_BLOCK_TAG.test(node.tagName);
    if (block) out += '\n';
    if (/^li$/i.test(node.tagName)) out += '• ';
    for (const child of node.childNodes) walk(child);
    if (/^(td|th)$/i.test(node.tagName)) out += ' | ';
    if (block) out += '\n';
  };
  walk(el);
  const text = out.split('\n')
    .map(line => line.replace(/[ \t \r]+/g, ' ').replace(/(\s*\|\s*)+$/, '').trim())
    .filter(Boolean)
    .join('\n');
  return text.length > EXCERPT_MAX ? text.slice(0, EXCERPT_MAX - 1).trimEnd() + '…' : text;
}

// "Columns › status": where the quoted text lives, from the anchor registry.
function excerptSource(anchorId) {
  const e = ANCHOR_REGISTRY[anchorId];
  if (!e) return '';
  const name = normText(e.name), grp = normText(e.grp);
  return (grp && name && grp !== name) ? grp + ' › ' + name : (name || grp);
}

// A question card baked into a generated page (pagegen's ```cards block).
// Scoped to that markup so a hand-built page's own `.card` content is never
// mistaken for one and hidden.
function isStaticCard(el) {
  return !!(el && el.matches && el.matches('.aa .cards > .card'));
}

function buildStripEl(anchorId, items, x) {
  const api = cardApi();
  const cards = api ? items.map(e => e.decisionRequest ? api.stripCard(document, e.id, x) : api.stripVerdictChip(document, e.id)).filter(Boolean) : [];
  if (!cards.length) return null;
  const wrap = document.createElement('div');
  wrap.className = 'annotate-decision-strip';
  wrap.dataset.annotateStrip = '1';
  wrap.dataset.stripAnchor = anchorId;
  // Mis-attribution fix (user-reported: a pin/strip on an adjacent row read
  // as belonging to a different decision): prefix the strip with the
  // anchor's own human label from the registry (e.g. "D7: Scoring weights"),
  // so a reviewer scanning strips never has to guess which row one belongs
  // to. Skipped when the registry has no real name for this anchor (falls
  // back to the anchor id itself, which isn't useful to show).
  // A strip standing in for a generated question card is that card: its
  // number and prompt are the title, and the registry name (the card's own
  // first sentence) would only repeat them.
  const label = anchorName(anchorId);
  if (label && label !== anchorId && !isStaticCard(findAnchorEl(anchorId))) {
    const hdr = document.createElement('div');
    hdr.className = 'annotate-strip-anchor-label';
    hdr.textContent = label; // textContent only — registry data, not markup
    wrap.appendChild(hdr);
  }
  cards.forEach(card => wrap.appendChild(card));
  return wrap;
}

// Rebuilds the feedback queue from latestPins. Called only from the
// 'annotate:comment-counts' handler (see wireBridge) — i.e. once per actual
// data change, never on the resize/scroll-driven badge-refresh cadence, so
// this function's own DOM mutations can't feed the MutationObserver above
// into a rebuild loop the way renderBadges() must guard against.
// Baked question cards (`.card[data-anchor-id]`, written into the page at
// generation time) show the live state the rail shows, with the same label.
// Without this a card the rail lists as answered or addressed still read
// "Answer it on the card" in the body (Chang, 2026-09-23).
function ensureCardStateStyle() {
  if (document.getElementById('annotate-card-state-style')) return;
  const style = document.createElement('style');
  style.id = 'annotate-card-state-style';
  style.textContent = `
    .card[data-annotate-state="waiting"], .card[data-annotate-state="done"] { opacity: .6; }
    .card[data-annotate-state="waiting"] > p.q, .card[data-annotate-state="done"] > p.q { display: none; }
    .annotate-card-state { display: inline-block; margin: 0 0 6px; padding: 1px 8px; border-radius: 10px;
      font: 700 calc(9.5px * var(--aa-text, 1)) "Inter", sans-serif; letter-spacing: .02em; }
    .annotate-card-state.review { background: var(--error-soft); color: var(--color-error); }
    .annotate-card-state.waiting { background: var(--color-base-200); color: var(--muted); }
    .annotate-card-state.done { background: var(--success-soft); color: var(--ok-text); }
  `;
  document.head.appendChild(style);
}

function renderCardStates() {
  ensureCardStateStyle();
  document.querySelectorAll('.card[data-anchor-id]').forEach(card => {
    const st = latestCardStates[card.dataset.anchorId];
    let chip = card.querySelector(':scope > .annotate-card-state');
    if (!st) {
      delete card.dataset.annotateState;
      if (chip) chip.remove();
      return;
    }
    card.dataset.annotateState = st.state;
    if (!chip) {
      chip = document.createElement('div');
      card.insertBefore(chip, card.firstChild);
    }
    chip.className = 'annotate-card-state ' + st.state;
    chip.textContent = st.label; // textContent only
  });
}

// The generated question cards a strip stands in for: the card that owns the
// anchor, and any card bound to it ("Anchored to …" links to the anchor).
function staticCardsFor(anchorId) {
  const out = [];
  const el = findAnchorEl(anchorId);
  if (isStaticCard(el)) out.push(el);
  document.querySelectorAll('.aa .cards > .card.card-bound').forEach(card => {
    const a = card.querySelector('.card-ref a[href]');
    if (a && a.getAttribute('href') === '#' + anchorId && out.indexOf(card) === -1) out.push(card);
  });
  return out;
}

// Real-document-flow insertion after `after` (the anchor element, or the
// previous strip placed at it). Returns true on success; false means the
// caller must use the absolute-overlay fallback. SVG content is routed
// straight to the fallback: an HTML element appended as a sibling of SVG
// children has no rendering box (only <foreignObject> children paint).
function insertStripInFlow(el, after, stripEl) {
  if (el.ownerSVGElement || el.tagName.toLowerCase() === 'svg' || el.closest('svg')) return false;
  try {
    if (el.tagName === 'TR') {
      const tr = document.createElement('tr');
      tr.className = 'annotate-strip-tr';
      tr.dataset.annotateStrip = '1';
      const td = document.createElement('td');
      td.colSpan = el.children.length || 1;
      td.appendChild(stripEl);
      tr.appendChild(td);
      after.insertAdjacentElement('afterend', tr);
      return tr;
    }
    stripEl.classList.add('annotate-strip-block');
    after.insertAdjacentElement('afterend', stripEl);
    return stripEl;
  } catch (e) {
    console.warn('[adapter] strip DOM-flow injection failed, falling back to overlay', e);
    return false;
  }
}

// Absolute-overlay fallback: positions the strip just below the anchor's own
// rect, clamped horizontally into the viewport the same way clampPinLeft
// clamps pins (an unclamped strip could otherwise inflate scrollWidth).
function placeStripAbsolute(el, stripEl) {
  const layer = ensureStripLayer();
  const wrapper = layer.parentElement;
  if (!wrapper) return;
  stripEl.classList.add('annotate-strip-abs');
  layer.appendChild(stripEl); // attach before measuring so offsetWidth is real
  const wrapperRect = wrapper.getBoundingClientRect();
  const rect = el.getBoundingClientRect();
  const w = stripEl.getBoundingClientRect().width || 260;
  const viewportW = document.documentElement.clientWidth || window.innerWidth;
  const inset = 8;
  let left = rect.left - wrapperRect.left;
  const maxLeft = viewportW - wrapperRect.left - inset - w;
  if (Number.isFinite(maxLeft) && left > maxLeft) left = Math.max(inset, maxLeft);
  if (left < inset) left = inset;
  stripEl.style.left = left + 'px';
  stripEl.style.top = (rect.bottom - wrapperRect.top + 4) + 'px';
}

function inActivePanel(el) {
  const panel = el.closest('.tab-panel');
  if (panel && !panel.classList.contains('active')) return false;
  const subPanel = el.closest('.sub-panel');
  return !(subPanel && !subPanel.classList.contains('active'));
}

// A `###` heading is a bare <h3>, so citing it means the heading and what
// follows it up to the next heading of its level. The question goes after
// that content, not between the heading and the pictures it asks about
// (Chang, 2026-10-23: feedback comes after what he reviews).
function headingBlockEnd(el) {
  const level = /^H([1-6])$/.exec(el.tagName);
  if (!level) return el;
  let end = el;
  for (let n = el.nextElementSibling; n; n = n.nextElementSibling) {
    const h = /^H([1-6])$/.exec(n.tagName);
    if ((h && +h[1] <= +level[1]) || n.matches('.cards')) break;
    if (!n.matches('[data-annotate-strip], [data-annotate-back], .bpin, .bpin-inline, .annotate-unchanged-bar')) end = n;
  }
  return end;
}

// Where a question renders: right after its evidence, so the reviewer
// answers beside the images or rows it asks about instead of scrolling
// between a question list and the content (Chang, 2026-10-10). With several
// evidence targets it follows the last one in reading order. A question
// without visible evidence stays at its own card.
function stripTarget(anchorId, items) {
  const own = findAnchorEl(anchorId);
  const targets = [];
  items.forEach(e => evidenceOf(e.decisionRequest).forEach(x => {
    const el = findAnchorEl(x.anchor);
    if (el && el !== own && !isStaticCard(el) && !el.closest('.cards') && inActivePanel(el)) targets.push(headingBlockEnd(el));
  }));
  if (!targets.length) return own;
  // The target that ends last: compare deepest last descendants; a container
  // ends after (or with) everything inside it.
  const endOf = el => { let n = el; while (n.lastElementChild) n = n.lastElementChild; return n; };
  let target = targets.reduce((best, el) => {
    const a = endOf(best), b = endOf(el);
    if (a === b) return el.contains(best) ? el : best;
    return (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING) ? el : best;
  });
  // Never inside a closed disclosure, and never as a squeezed item of a grid
  // or flex row: the question goes after the whole block.
  for (let closed; (closed = target.parentElement && target.parentElement.closest('details:not([open])'));) target = closed;
  while (target.tagName !== 'TR' && target.parentElement && target.parentElement !== document.body &&
         /^(inline-)?(grid|flex)$/.test(getComputedStyle(target.parentElement).display)) target = target.parentElement;
  return target;
}

function renderDecisionStrips() {
  ensureStripStyle();
  lastExcerpts = excerptMap();
  // v9o: a rebuild under the reviewer's typing keeps the box focused with
  // its caret (its text is the card's draft, kept by the shell).
  const ae = document.activeElement;
  const typing = ae && ae.matches && ae.matches('textarea[data-strip-say]')
    ? { id: ae.dataset.stripSay, start: ae.selectionStart, end: ae.selectionEnd, dir: ae.selectionDirection } : null;
  document.querySelectorAll('[data-annotate-strip]').forEach(n => n.remove());
  // One card per question in the body. A generated card whose question the
  // interactive strip now renders is hidden (it stays in the HTML as the
  // no-JavaScript fallback) and comes back if the strip goes away.
  document.querySelectorAll('[data-annotate-replaced]').forEach(card => {
    card.classList.remove('annotate-card-replaced');
    delete card.dataset.annotateReplaced;
  });
  document.querySelectorAll('[data-annotate-moved]').forEach(sec => {
    sec.classList.remove('annotate-questions-moved');
    delete sec.dataset.annotateMoved;
  });

  const placed = [];
  for (const [anchorId, entries] of Object.entries(latestPins)) {
    const items = (entries || []).filter(e => e.decisionRequest || e.decisionVerdict);
    if (!items.length) continue;
    const el = stripTarget(anchorId, items);
    if (!el || !inActivePanel(el)) continue;
    items.sort((a, b) => (parseInt(a.n, 10) || 0) - (parseInt(b.n, 10) || 0));
    placed.push({ anchorId, items, el });
  }
  // Questions sharing a target keep their numbers' order under it.
  placed.sort((a, b) => (parseInt(a.items[0].n, 10) || 0) - (parseInt(b.items[0].n, 10) || 0));
  const lastAt = new Map();
  placed.forEach(({ anchorId, items, el }) => {
    const stripEl = buildStripEl(anchorId, items, lastExcerpts);
    if (!stripEl) return;
    const node = insertStripInFlow(el, lastAt.get(el) || el, stripEl);
    if (node) lastAt.set(el, node);
    else placeStripAbsolute(el, stripEl);
    if (items.some(e => e.decisionRequest)) {
      staticCardsFor(anchorId).forEach(card => {
        card.classList.add('annotate-card-replaced');
        card.dataset.annotateReplaced = '1';
      });
    }
  });
  // A "Questions for Chang" section whose every card moved to its evidence
  // would be a bare heading; hide it until a card comes back.
  document.querySelectorAll('.aa .cards').forEach(list => {
    const sec = list.closest('section[data-anchor-id]');
    if (!sec || list.querySelector('.card:not(.annotate-card-replaced)') || sec.querySelector('[data-annotate-strip]')) return;
    const other = [...sec.children].some(c => c !== list && !/^H[1-6]$/.test(c.tagName) &&
      !c.matches('[data-annotate-strip], .bpin, .bpin-inline, .annotate-unchanged-bar'));
    if (other) return;
    sec.classList.add('annotate-questions-moved');
    sec.dataset.annotateMoved = '1';
  });
  syncAllExcerptClamps();
  const back = typing && document.querySelector('textarea[data-strip-say="' + CSS.escape(typing.id) + '"]');
  if (back) {
    back.focus({ preventScroll: true });
    try { back.setSelectionRange(typing.start, typing.end, typing.dir); } catch {}
  }
}

// Reading order of anchors, with a question counted where its strip renders,
// so the rail lists feedback in the order the document shows it.
function contentAnchorOrder() {
  const order = {};
  let index = 0;
  document.querySelectorAll('[data-anchor-id], [id], .annotate-decision-strip[data-strip-anchor]').forEach(el => {
    if (el.closest('.annotate-decision-strip') && !el.matches('.annotate-decision-strip')) return;
    if (el.closest('[data-annotate-replaced]')) return; // a hidden card; its strip counts
    const aid = el.matches('.annotate-decision-strip') ? el.dataset.stripAnchor : (el.dataset.anchorId || el.id);
    if (!Object.prototype.hasOwnProperty.call(order, aid)) order[aid] = index++;
  });
  return order;
}

// ── Go-to-location persistent highlight ─────────────────────────────
// Injected once at init (not baked into content/*.html — this is
// adapter-owned interactivity, same rule as everything else in this file).
// Deliberately visually distinct from the subtler [data-anchor-id].active
// hover/click-to-comment state (CONTENT_CSS_TEMPLATE in extract_content.py):
// go-to-location is a comment-review action the user explicitly asked for
// ("→ Go to location"), so it gets a stronger, longer-lived treatment.
const GOTO_HIGHLIGHT_MS = 5000;
let gotoHighlightTimer = null;
function ensureGotoHighlightStyle() {
  if (document.getElementById('goto-highlight-style')) return;
  const style = document.createElement('style');
  style.id = 'goto-highlight-style';
  style.textContent = `
    .goto-highlight{
      outline: 3px solid var(--color-warning) !important;
      outline-offset: 2px;
      background: color-mix(in oklab,var(--color-warning) 14%,transparent) !important;
      border-radius: 4px;
      animation: gotoHighlightPulse 1.1s ease-in-out 2;
      transition: outline-color .3s, background .3s;
    }
    svg .goto-highlight-svg{ stroke:var(--color-warning) !important; stroke-width:3px !important; }
    @keyframes gotoHighlightPulse{
      0%,100%{ box-shadow: 0 0 0 0 color-mix(in oklab,var(--color-warning) 35%,transparent); }
      50%{ box-shadow: 0 0 0 6px color-mix(in oklab,var(--color-warning) 0%,transparent); }
    }
  `;
  document.head.appendChild(style);
}
function clearGotoHighlight() {
  document.querySelectorAll('.goto-highlight, .goto-highlight-svg').forEach(el => {
    el.classList.remove('goto-highlight', 'goto-highlight-svg');
  });
  if (gotoHighlightTimer) { clearTimeout(gotoHighlightTimer); gotoHighlightTimer = null; }
}

// ── Scroll-to-anchor + persistent highlight (mirrors template.html scrollToAnchor) ──
// Reports back to the shell via 'annotate:scroll-result' whether the anchor
// resolved to a real DOM node, so the shell can show an explicit
// "location unavailable" state instead of doing nothing on click (this was
// the exact failure mode reported: clicking a comment with an unresolvable
// anchor used to just silently return here).
// Make an anchor's hidden ancestors visible by driving the content doc's own
// tab controls. Handles three conventions, best-effort, outermost first:
//   1. v4-x: .tab-panel/#panel-<id> + #tab-btn-<id>, .sub-panel/#sub-<id> + #sub-tab-btn-<id>
//   2. data-panel="X" sections toggled by [data-tab="X"] buttons (ontology docs)
//   3. ARIA: [role=tab][aria-controls=<ancestor id>] (or any [aria-controls])
// Returns true if any control was clicked (caller waits a settle frame).
function revealAnchor(el) {
  let clicked = false;
  const panel = el.closest('.tab-panel');
  if (panel && !panel.classList.contains('active')) {
    const tabId = panel.id ? panel.id.replace(/^panel-/, '') : null;
    const btn = tabId ? document.getElementById('tab-btn-' + tabId) : null;
    if (btn) { btn.click(); clicked = true; }
  }
  const subPanel = el.closest('.sub-panel');
  if (subPanel && !subPanel.classList.contains('active')) {
    const subId = subPanel.id ? subPanel.id.replace(/^sub-/, '') : null;
    const btn = subId ? document.getElementById('sub-tab-btn-' + subId) : null;
    if (btn) { btn.click(); clicked = true; }
  }
  const ancestors = [];
  for (let cur = el; cur && cur !== document.body; cur = cur.parentElement) ancestors.push(cur);
  ancestors.reverse(); // outermost hidden container first
  for (const cur of ancestors) {
    let st;
    try { st = getComputedStyle(cur); } catch { continue; }
    if (st.display !== 'none' && st.visibility !== 'hidden') continue;
    let btn = null;
    if (cur.dataset && cur.dataset.panel) {
      btn = document.querySelector('[data-tab="' + cssEsc(cur.dataset.panel) + '"]');
    }
    if (!btn && cur.id) {
      btn = document.querySelector('[role="tab"][aria-controls="' + cssEsc(cur.id) + '"]')
        || document.querySelector('[aria-controls="' + cssEsc(cur.id) + '"]');
    }
    if (btn) { btn.click(); clicked = true; }
  }
  return clicked;
}

// Scrolls this document only. scrollIntoView also scrolls every ancestor,
// the shell's page included, which pushed the shell header out of view.
function scrollInFrame(el, block) {
  const r = el.getBoundingClientRect();
  const top = block === 'start' ? r.top : r.top - (window.innerHeight - r.height) / 2;
  window.scrollTo({ top: Math.max(0, window.scrollY + top), behavior: 'smooth' });
}

// `back` ({commentId, n, from: 'strip'|'rail'}) is set by an evidence "Go to":
// the target then carries a "Back to #N" marker that returns to the card.
function scrollToAnchor(anchorId, target, back) {
  ensureGotoHighlightStyle();
  openEarlierFor(anchorId);
  const anchorEl = displayAnchorEl(anchorId);
  if (!anchorEl) {
    postToParent({ type: 'annotate:scroll-result', anchorId, found: false });
    return;
  }

  // Granular resolution: if the comment captured an inner target, scroll to
  // and highlight THAT element; degrade to the section anchor when the inner
  // target no longer resolves (structure changed) — never a wrong element.
  const inner = resolveInnerEl(anchorEl, target);
  const el = inner ? inner.el : anchorEl;
  for (let parent = el.parentElement; parent; parent = parent.parentElement) {
    if (parent.tagName === 'DETAILS') parent.open = true;
  }

  // A jump into a collapsed unchanged section opens it first.
  expandUnchangedAncestor(el);
  // If inside hidden tab panels, switch the content doc's own tabs first.
  const switched = revealAnchor(el);

  setTimeout(() => {
    // Still not visible (unknown tab system, collapsed container, …):
    // report honestly instead of "scrolling" to an invisible element —
    // the shell renders "location unavailable in this version".
    if (!el.getClientRects().length) {
      postToParent({ type: 'annotate:scroll-result', anchorId, found: false });
      return;
    }
    const marker = back && back.commentId ? placeBackPill(el, back) : null;
    const isSvgEl = !!(el.ownerSVGElement || el.tagName.toLowerCase() === 'svg');
    if (isSvgEl) {
      const svg = document.querySelector('svg');
      if (svg) {
        let bbox;
        try { bbox = el.getBBox(); } catch { bbox = null; }
        if (bbox) {
          const svgRect = svg.getBoundingClientRect();
          const vbWidth = (svg.viewBox && svg.viewBox.baseVal && svg.viewBox.baseVal.width) || 1920;
          const scale = svgRect.width / vbWidth;
          window.scrollTo({ top: Math.max(0, svgRect.top + window.scrollY + bbox.y * scale - 120), behavior: 'smooth' });
        }
      }
    } else if (marker && marker.row !== marker.pill &&
               el.getBoundingClientRect().height > window.innerHeight * 0.6) {
      // Too tall to center with its marker in view: start at the marker.
      scrollInFrame(marker.row, 'start');
    } else {
      scrollInFrame(el, 'center');
    }
    clearGotoHighlight();
    el.classList.add('active');
    el.classList.add(isSvgEl ? 'goto-highlight-svg' : 'goto-highlight');
    gotoHighlightTimer = setTimeout(() => {
      el.classList.remove('active', 'goto-highlight', 'goto-highlight-svg');
      gotoHighlightTimer = null;
    }, GOTO_HIGHLIGHT_MS);
    postToParent({
      type: 'annotate:scroll-result',
      anchorId,
      found: true,
      resolved: inner ? inner.how : 'anchor',
    });
  }, switched ? 150 : 0);
}

// ── "Back to #N": the marker an evidence jump leaves on its target ──────
// Wikipedia's reference previews and GitHub's review threads both keep the
// reader anchored to where they came from; this is the way back from the
// evidence to the question card that cited it. Inserted in flow just above
// the target (a sibling row for a table row), or absolutely positioned where
// flow insertion is not possible (SVG, table cells). One at a time.
let backPillAbs = null; // {pill, el} while an absolutely-positioned marker is up

function removeBackPills() {
  document.querySelectorAll('[data-annotate-back]').forEach(n => n.remove());
  backPillAbs = null;
}

function positionBackPill() {
  if (!backPillAbs) return;
  const { pill, el } = backPillAbs;
  if (!pill.isConnected || !el.isConnected) { backPillAbs = null; return; }
  const wrapper = pill.parentElement && pill.parentElement.parentElement;
  if (!wrapper) return;
  const wr = wrapper.getBoundingClientRect();
  const r = el.getBoundingClientRect();
  const h = pill.getBoundingClientRect().height || 26;
  pill.style.left = Math.max(8, r.left - wr.left) + 'px';
  pill.style.top = Math.max(0, r.top - wr.top - h - 4) + 'px';
}

function placeBackPill(el, back) {
  removeBackPills();
  ensureStripStyle();
  const pill = document.createElement('button');
  pill.type = 'button';
  pill.className = 'annotate-back-pill';
  pill.textContent = back.n ? '↩ Back to #' + back.n : '↩ Back to the question';
  pill.title = 'Return to the question card that cited this';
  pill.addEventListener('click', (e) => {
    e.stopPropagation();
    goBackToCard(back);
  });
  const tag = el.tagName.toUpperCase();
  const inSvg = !!(el.ownerSVGElement || tag === 'SVG' || el.closest('svg'));
  let row;
  try {
    if (!inSvg && tag === 'TR') {
      row = document.createElement('tr');
      row.className = 'annotate-back-tr';
      const td = document.createElement('td');
      td.colSpan = el.children.length || 1;
      td.appendChild(pill);
      row.appendChild(td);
      el.insertAdjacentElement('beforebegin', row);
    } else if (!inSvg && el.parentElement &&
               !/^(TD|TH|THEAD|TBODY|TFOOT|CAPTION|COLGROUP|COL|OPTION|OPTGROUP|DT|DD|HTML|BODY)$/.test(tag)) {
      row = document.createElement(tag === 'LI' ? 'li' : 'div');
      row.className = 'annotate-back-row';
      row.appendChild(pill);
      el.insertAdjacentElement('beforebegin', row);
    }
  } catch (err) {
    row = null;
  }
  if (!row) {
    row = pill;
    pill.classList.add('annotate-back-abs');
    ensureStripLayer().appendChild(pill);
    backPillAbs = { pill, el };
    positionBackPill();
  }
  row.dataset.annotateBack = '1';
  return { row, pill };
}

function flashEl(el) {
  clearGotoHighlight();
  el.classList.add('goto-highlight');
  gotoHighlightTimer = setTimeout(() => {
    el.classList.remove('goto-highlight');
    gotoHighlightTimer = null;
  }, 1600);
}

function goBackToCard(back) {
  removeBackPills();
  if (back.from === 'rail') {
    // The card lives in the shell's rail: the shell reopens and focuses it.
    postToParent({ type: 'annotate:back-to-card', commentId: back.commentId });
    return;
  }
  const item = document.querySelector('[data-strip-item="' + cssEsc(back.commentId) + '"]');
  if (!item) return;
  expandUnchangedAncestor(item);
  revealAnchor(item);
  scrollInFrame(item, 'center');
  flashEl(item);
}

// ── Unchanged sections (v2+) ─────────────────────────────────────────
// pagegen stamps `data-unchanged-since="vN"` on every `##` section identical
// to the previous version's. Those render collapsed behind a one-line header,
// so a reviewer reads what changed instead of the whole plan again. The header
// is the section's heading in both states (WAI-ARIA APG accordion: a heading
// wrapping a button with aria-expanded) and stands in for the generated <h2>,
// which stays in the DOM for no-JS readers. A section holding an open question
// card, or the evidence an open card cites, is opened automatically, and so
// is any section a jump lands in. Without JavaScript nothing collapses.
const unchangedChoice = {}; // section key -> true/false once the reviewer toggles it

function ensureUnchangedStyle() {
  if (document.getElementById('annotate-unchanged-style')) return;
  const style = document.createElement('style');
  style.id = 'annotate-unchanged-style';
  style.textContent = `
    section.annotate-unchanged-collapsed > :not(.annotate-unchanged-bar) { display: none !important; }
    /* The bar is the section's heading in both states; the generated one
       would only repeat its title. */
    section[data-unchanged-since] > .annotate-unchanged-heading { display: none !important; }
    .annotate-unchanged-bar { display: block !important; margin: 26px 0 10px !important; padding: 0 !important; }
    section.annotate-unchanged-collapsed > .annotate-unchanged-bar { margin-bottom: 4px !important; }
    .annotate-unchanged-toggle {
      display: flex !important; align-items: baseline !important; gap: 4px 10px !important; flex-wrap: wrap !important;
      width: 100% !important; box-sizing: border-box !important; text-align: left !important;
      font: 600 calc(13px * var(--aa-text, 1))/1.4 "Inter", sans-serif !important;
      color: var(--color-base-content) !important; background: var(--color-base-200) !important; border: 1px dashed var(--line) !important;
      border-radius: 8px !important; padding: 8px 12px !important; cursor: pointer !important; margin: 0 !important;
    }
    .annotate-unchanged-toggle:hover { background: var(--color-base-200) !important; border-color: var(--muted) !important; }
    .annotate-unchanged-toggle:focus-visible { outline: 2px solid var(--link) !important; outline-offset: 1px !important; }
    .annotate-unchanged-toggle::before { content: '\\25B8'; font-size: calc(11px * var(--aa-text, 1)); color: var(--muted); transition: transform .12s; align-self: center; }
    .annotate-unchanged-toggle[aria-expanded="true"]::before { transform: rotate(90deg); }
    .annotate-unchanged-title { font-size: calc(12.5px * var(--aa-text, 1)) !important; font-weight: 700 !important; color: var(--color-base-content) !important; }
    .annotate-unchanged-note { font-weight: 500 !important; color: var(--muted) !important; font-size: calc(10.5px * var(--aa-text, 1)) !important; }
    @media (max-width: 768px), (max-height: 480px) {
      .annotate-unchanged-toggle { min-height: 44px !important; touch-action: manipulation !important; }
    }
  `;
  document.head.appendChild(style);
}

function unchangedKey(sec) {
  return sec.dataset.anchorId || sec.id;
}

function setUnchangedOpen(sec, open) {
  sec.classList.toggle('annotate-unchanged-collapsed', !open);
  const btn = sec.querySelector(':scope > .annotate-unchanged-bar > .annotate-unchanged-toggle');
  if (!btn) return;
  btn.setAttribute('aria-expanded', open ? 'true' : 'false');
  const note = btn.querySelector('.annotate-unchanged-note');
  if (note) {
    note.textContent = 'Unchanged since ' + (sec.dataset.unchangedSince || 'the last version') +
      (open ? ' — hide' : ' — show');
  }
  if (open) syncAllExcerptClamps(sec);
}

function initUnchangedSections() {
  const sections = document.querySelectorAll('section[data-unchanged-since]');
  if (!sections.length) return;
  ensureUnchangedStyle();
  sections.forEach((sec, i) => {
    if (sec.querySelector(':scope > .annotate-unchanged-bar')) return;
    if (!sec.id) sec.id = 'annotate-unchanged-' + (i + 1);
    const key = unchangedKey(sec);
    const heading = sec.querySelector(':scope > h2, :scope > h1, :scope > h3');
    const bar = document.createElement('div');
    bar.className = 'annotate-unchanged-bar';
    bar.setAttribute('role', 'heading');
    bar.setAttribute('aria-level', heading ? heading.tagName.slice(1) : '2');
    if (heading) heading.classList.add('annotate-unchanged-heading');
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'annotate-unchanged-toggle';
    btn.setAttribute('aria-controls', sec.id);
    const title = document.createElement('span');
    title.className = 'annotate-unchanged-title';
    title.textContent = normText(heading ? heading.textContent : anchorName(key));
    const note = document.createElement('span');
    note.className = 'annotate-unchanged-note';
    btn.appendChild(title);
    btn.appendChild(note);
    btn.addEventListener('click', () => {
      const open = sec.classList.contains('annotate-unchanged-collapsed');
      unchangedChoice[key] = open;
      setUnchangedOpen(sec, open);
    });
    bar.appendChild(btn);
    sec.insertBefore(bar, sec.firstChild);
    setUnchangedOpen(sec, false);
  });
}

// Never leave an open question, or what it cites, folded away.
function openUnchangedSectionsForOpenCards() {
  if (!document.querySelector('section[data-unchanged-since]')) return;
  const keep = new Set();
  const note = (aid) => {
    const el = aid && findAnchorEl(aid);
    const sec = el && el.closest('section[data-unchanged-since]');
    if (sec) keep.add(sec);
  };
  for (const [aid, entries] of Object.entries(latestPins)) {
    for (const e of entries || []) {
      const open = e.decision === true || (e.decisionRequest && e.changing);
      if (!open) continue;
      note(aid);
      evidenceOf(e.decisionRequest).forEach(x => note(x.anchor));
    }
  }
  keep.forEach(sec => {
    if (unchangedChoice[unchangedKey(sec)] === false) return; // the reviewer folded it
    if (sec.classList.contains('annotate-unchanged-collapsed')) setUnchangedOpen(sec, true);
  });
}

// ── Earlier updates (long pages) ─────────────────────────────────────
// publish folds finished topics into <details class="aa-earlier">; their HTML
// waits in a <template>, so its screenshots load only when the bar is opened,
// or when a jump (Open in document, an evidence link) lands inside it.
function foldedAnchorEl(anchorId) {
  for (const tpl of document.querySelectorAll('details.aa-earlier > template.aa-earlier-body')) {
    const el = tpl.content.querySelector('[data-anchor-id="' + cssEsc(anchorId) + '"]');
    if (el) return el;
  }
  return null;
}

function openEarlier(details) {
  const tpl = details.querySelector(':scope > template.aa-earlier-body');
  if (!tpl) return;
  // Already folded once: no second "Unchanged since" fold inside this one.
  tpl.content.querySelectorAll('section[data-unchanged-since]').forEach(sec => sec.removeAttribute('data-unchanged-since'));
  tpl.replaceWith(tpl.content);
  details.open = true;
  labelImages();
  wrapScrollTables();
  wireCopyButtons();
  renderDecisionStrips();
  renderCardStates();
  renderBadges();
  postExcerpts();
}

function openEarlierFor(anchorId) {
  const el = !findAnchorEl(anchorId) && foldedAnchorEl(anchorId);
  if (el) openEarlier(document.querySelector('details.aa-earlier'));
}

function wireEarlier() {
  document.querySelectorAll('details.aa-earlier').forEach(details => {
    details.addEventListener('toggle', () => { if (details.open) openEarlier(details); });
  });
}

function expandUnchangedAncestor(el) {
  const sec = el && el.closest ? el.closest('section[data-unchanged-since]') : null;
  if (!sec || !sec.classList.contains('annotate-unchanged-collapsed')) return false;
  setUnchangedOpen(sec, true);
  return true;
}

// ── Excerpts for the rail card ───────────────────────────────────────
// shell.js never reads this document; the rail card's quoted excerpt and
// evidence previews arrive here, one message per change in what they say.
let lastExcerptsJson = '';
let lastExcerpts = null; // read when the cards were last drawn
// {anchorId: {text, name, card} | {missing: true}} for every anchor an open
// question cites; the cards here quote it, and so does the rail.
function excerptMap() {
  const out = {};
  const add = (aid) => {
    if (!aid || Object.prototype.hasOwnProperty.call(out, aid)) return;
    const el = findAnchorEl(aid) || foldedAnchorEl(aid);
    out[aid] = el
      ? { text: excerptText(el), name: excerptSource(aid), card: isStaticCard(el) }
      : { missing: true };
  };
  for (const [aid, entries] of Object.entries(latestPins)) {
    for (const e of entries || []) {
      if (!e.decisionRequest) continue;
      add(aid);
      evidenceOf(e.decisionRequest).forEach(x => add(x.anchor));
    }
  }
  return out;
}
function postExcerpts() {
  if (window.parent === window) return;
  const out = lastExcerpts || excerptMap();
  const anchorOrder = contentAnchorOrder();
  const json = JSON.stringify({ out, anchorOrder });
  if (json === lastExcerptsJson) return;
  lastExcerptsJson = json;
  postToParent({ type: 'annotate:excerpts', version: META.version || null, excerpts: out, anchorOrder });
}

// ── E3 shortcuts while focus is in the document ─────────────────────
// Clicking the document moves keyboard focus into this frame, where the
// shell's key handler cannot hear. Pass the shortcut keys up (never while
// typing, never with Alt/Ctrl/Cmd except ⌘/Ctrl+Enter, and Escape).
function wireShortcutForwarding() {
  document.addEventListener('keydown', (e) => {
    const t = e.target;
    if (t && t.closest && (t.isContentEditable || t.closest('input, textarea, select'))) return;
    const mod = e.metaKey || e.ctrlKey;
    const send = e.key === 'Enter' && mod;
    if (e.altKey || (mod && !send)) return;
    if (!(send || e.key === 'Escape' || /^[afcAFC1-9]$/.test(e.key))) return;
    if (e.key !== 'Escape') e.preventDefault();
    postToParent({ type: 'annotate:key', key: e.key, meta: e.metaKey, ctrl: e.ctrlKey, shift: e.shiftKey });
  });
}

// ── Bridge: listen for shell messages ────────────────────────────────
function wireBridge() {
  wireShortcutForwarding();
  window.addEventListener('message', (e) => {
    if (!PARENT_ORIGIN || e.origin !== PARENT_ORIGIN || e.source !== window.parent) return;
    const data = e.data || {};
    if (!data || typeof data !== 'object') return;
    if (data.type === 'annotate:theme' && ['dark', 'light'].includes(data.theme)) {
      document.documentElement.dataset.theme = data.theme;
    } else if (data.type === 'annotate:text-size' && typeof data.size === 'number' && data.size >= 0.5 && data.size <= 3) {
      document.documentElement.style.setProperty('--aa-text', String(data.size));
      window.dispatchEvent(new Event('resize')); // pins and strips follow the reflow
    } else if (data.type === 'annotate:card-hover') {
      setCardHover(data.on ? data.anchorId : null, data.target || null);
    } else if (data.type === 'annotate:scroll-to') {
      closeViewer();
      scrollToAnchor(data.anchorId, data.target || null, data.back || null);
    } else if (data.type === 'annotate:comment-counts') {
      latestCounts = data.counts || {};
      latestPins = data.pins || {};
      latestCardStates = data.cardStates || {};
      linkBoardIds(data.board);
      // Strips first: they can insert real sibling rows/elements that shift
      // layout, so pins must be positioned AFTER that shift, not before it.
      renderDecisionStrips();
      openUnchangedSectionsForOpenCards();
      renderCardStates();
      renderBadges();
      viewerPins();
      postExcerpts();
    }
  });
}

// ── Issue ids on the project's board link to the issue ──────────────
// "agent-annotate-w6e.4" in the document's text opens that issue on the
// project's board (decision #20). Done once per board; the shell sends the
// board (an already-checked http(s) URL and the id prefix) with the counts.
let linkedBoard = '';
function linkBoardIds(board) {
  const sig = board && board.url && board.prefix ? board.url + '\n' + board.prefix : '';
  if (!sig || sig === linkedBoard) return;
  linkedBoard = sig;
  const prefix = board.prefix.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp('(?<![A-Za-z0-9_.-])' + prefix + '-[a-z0-9]+(?:\\.[0-9]+)*(?![A-Za-z0-9_-])', 'g');
  const root = document.querySelector('.aa') || document.body;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: n => n.parentElement && n.parentElement.closest('a, pre, script, style, textarea, button, [data-annotate-strip], #badge-layer')
      ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
  });
  const nodes = [];
  for (let n; (n = walker.nextNode());) { re.lastIndex = 0; if (re.test(n.data)) nodes.push(n); }
  nodes.forEach(node => {
    const frag = document.createDocumentFragment();
    let offset = 0;
    re.lastIndex = 0;
    for (const m of node.data.matchAll(re)) {
      frag.appendChild(document.createTextNode(node.data.slice(offset, m.index)));
      const a = document.createElement('a');
      a.className = 'annotate-issue-link';
      a.href = board.url + (board.url.indexOf('?') === -1 ? '?' : '&') + 'bead=' + encodeURIComponent(m[0]);
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.title = 'Open ' + m[0];
      a.textContent = m[0];
      frag.appendChild(a);
      offset = m.index + m[0].length;
    }
    frag.appendChild(document.createTextNode(node.data.slice(offset)));
    node.replaceWith(frag);
  });
}

// ── Content-rendering bootstrap (Observable Plot diagrams) ─────────
// Content docs built with the Plot/D3 diagram engine (diagram-plot.js)
// declare mount points as `<!-- DIAGRAM:name --> ` HTML comments;
// AnnotateDiagrams.mountDiagrams() (defined in diagram-plot.js, loaded via
// <script src> in the content doc's <head>) scans for them and renders
// each as an SVG host. This call is content-rendering, not an annotation
// feature, but the original monolithic per-file script bundled it
// together with the annotation engine — the extraction step correctly
// strips that whole bundle, so the adapter (content-side bootstrap) is
// responsible for re-triggering it. Docs without the diagram engine
// (e.g. v4-2, whose SVGs are baked directly into markup) simply have no
// AnnotateDiagrams global and this is a no-op.
async function mountContentDiagrams() {
  if (typeof window.AnnotateDiagrams !== 'undefined' && typeof window.AnnotateDiagrams.mountDiagrams === 'function') {
    try {
      await window.AnnotateDiagrams.mountDiagrams();
    } catch (e) {
      console.warn('[adapter] mountDiagrams failed:', e);
    }
  }
}

// ── Extracted-content scroll contract (T10/T12, user-reported) ───────
// Content documents live inside a shell-owned iframe. They are documents, not
// nested app shells, so the iframe viewport is always the vertical scroller.
//
// Earlier versions tried to infer whether body{height:100vh;overflow:hidden}
// was intentional. That heuristic was timing-dependent: it could run while the
// short Overview tab was active, decide there was nothing below the fold, and
// never release the lock after a long tab (Schema, Migration, Examples) became
// active. At narrow iframe widths, legacy @media rules also stacked every tab,
// producing a 47k-pixel document with no usable scroll range.
//
// The adapter is injected only into extracted content, so the reliable contract
// is explicit rather than heuristic: document scrolling is enabled, legacy
// canvas scrollers are allowed to grow with their active tab, and exactly one
// tab panel remains visible at every iframe width. Diagram widgets keep their
// own overflow:auto and fullscreen behavior.
function ensureContentScrollContractStyle() {
  if (document.getElementById('annotate-content-scroll-contract')) return;
  const style = document.createElement('style');
  style.id = 'annotate-content-scroll-contract';
  style.textContent = `
    html {
      height: auto !important;
      min-height: 100% !important;
      overflow-y: auto !important;
      overscroll-behavior-y: contain;
    }
    body {
      display: block !important;
      height: auto !important;
      min-height: 100% !important;
      max-height: none !important;
      overflow-y: visible !important;
    }
    body > .canvas-wrapper,
    .canvas-area {
      height: auto !important;
      min-height: 0 !important;
      max-height: none !important;
      overflow-y: visible !important;
    }
    .tab-panel { display: none !important; }
    .tab-panel.active { display: block !important; }
  `;
  document.head.appendChild(style);
}

function fixViewportScrollLock() {
  // Kept as a named compatibility hook for older tests and resize callbacks.
  // The deterministic stylesheet above owns the actual repair.
  ensureContentScrollContractStyle();
}

// Layout is viewport-dependent (content docs carry responsive media queries
// that restructure below 720px iframe width — tab panels stack), so the lock
// check re-runs on resize (rail collapse/expand changes iframe width too).
let scrollLockRecheckTimer = null;
function scheduleScrollLockRecheck() {
  clearTimeout(scrollLockRecheckTimer);
  scrollLockRecheckTimer = setTimeout(fixViewportScrollLock, 250);
}

// ── Canvas-chain width repair (user-reported: "schema tab not scrollable"
// + "right side cut off") ─────────────────────────────────────────────
// The pre-extraction app shell let the ER tab widen the canvas chain
// (body.er-tab-wide .canvas-wrapper{max-width:none}) because #canvas-area
// was a viewport-sized overflow:auto box the user could h-scroll. After
// chrome extraction that constraint is gone: the wrapper chain (flex child
// of body, min-width:auto) stretches to the diagram's fixed width (2440px),
// NOTHING in the chain actually h-scrolls, and body overflow-x:hidden clips
// the right ~1500px with no user-input path to reach it. Clamping the chain
// back to the viewport restores the containers' own overflow:auto behavior:
// #er-container gets a real horizontal scrollbar and wheel-scrolls on both
// axes. Docs without these classes: pure no-op.
function ensureGeometryFixStyle() {
  if (document.getElementById('annotate-geometry-fix')) return;
  const style = document.createElement('style');
  style.id = 'annotate-geometry-fix';
  // NEVER force `.canvas-wrapper { max-width: 100% }` — that destroys the
  // author's intentional centered content column (e.g. schema's 1180px cap)
  // on wide displays and reads as "horizontal stretch" (user-reported on
  // m5max). Instead: (a) let flex children shrink below their content width
  // via `min-width:0` so an oversized ER diagram doesn't drag its parent
  // chain wider than authored, and (b) contain the ER diagram itself so it
  // scrolls horizontally inside its wrapper instead of overflowing.
  style.textContent = `
    .canvas-wrapper, .canvas-area { min-width: 0 !important; }
    .er-container { max-width: 100% !important; overflow-x: auto !important; }
  `;
  document.head.appendChild(style);
}

// ── Legacy in-content chrome suppression (user-reported "stretched
// horizontally" on wide displays) ──────────────────────────────────────────
// Pre-v2 content pages (e.g. schema v4.6, orca-operating-model-review v1)
// bake their own full-app chrome inside the document: a top .hdr, a left
// .vrail version rail, and a right .drawer feedback panel. Under the v2
// universal shell those elements are duplicated — the outer shell already
// renders that chrome — and the doubled rails eat horizontal room, leaving
// the actual content column visibly cramped/off-center on wide viewports.
// Hide baked chrome inside content iframes only. Loading a legacy page
// standalone (without the outer shell) leaves this file uninjected, so no
// standalone view is affected. Same-origin child of the shell only.
function ensureLegacyChromeSuppressStyle() {
  if (window.parent === window) return; // standalone view — leave chrome visible
  if (document.getElementById('annotate-legacy-chrome-suppress')) return;
  const style = document.createElement('style');
  style.id = 'annotate-legacy-chrome-suppress';
  style.textContent = `
    body > .hdr,
    body > .main > .vrail,
    body > .main > .drawer,
    body > .repin-banner,
    body > #popover,
    body > #pin-popover,
    body > #author-modal,
    body > #mobile-dialog-backdrop,
    body > .mobile-fab { display: none !important; }
    body > .main { display: block !important; }
    body > .main > .canvas-area,
    body > .main > .frame-area { flex: initial !important; width: 100% !important; max-width: 100% !important; min-width: 0 !important; }
  `;
  document.head.appendChild(style);
}

// ── Diagram cluster jumps (T13, user-reported dead controls) ───────
// Legacy v4.2 baked its own handler, while extracted/Plot-backed versions lost
// that script entirely. Own the behavior in the universal adapter so every
// artifact gets one implementation. Locate a representative node by semantic
// kind, then center it inside the diagram's real scroll container; no diagram-
// specific pixel coordinates are required.
const CLUSTER_TARGET_SELECTORS = {
  hubs: [
    '.annotate-kind-hub',
    '.er-table[class*="layer-hub-"]',
  ],
  subtypes: [
    '.annotate-kind-subtype',
    '.er-table[class*="layer-sub-"]',
    '.er-table[class*="layer-pay-"]',
  ],
  joins: [
    '.annotate-kind-sidecar',
    '.er-table.layer-join',
    '.er-table.layer-deferred',
  ],
  derivations: [
    '.annotate-kind-derivation',
    '.annotate-kind-view',
    '.er-table.layer-derivation',
    '.er-table.layer-view',
  ],
  catalogs: [
    '.annotate-kind-catalog',
    '.er-table.layer-catalog',
  ],
  source: [
    '.annotate-kind-audit',
    '.er-table.layer-source',
  ],
};

function firstClusterTarget(cluster) {
  for (const selector of (CLUSTER_TARGET_SELECTORS[cluster] || [])) {
    const el = document.querySelector('#er-container ' + selector);
    if (el) return el;
  }
  return null;
}

function jumpToDiagramCluster(btn) {
  const cluster = btn.dataset.clusterJump;
  const container = document.getElementById('er-container');
  const target = firstClusterTarget(cluster);
  if (!container || !target) return false;

  // The control lives in the prose summary above the ER viewport. Move the
  // document to that viewport first, then pan the viewport to the requested
  // semantic cluster. Without this first step the internal scroll could work
  // while the user remained several screens above it, making the button look
  // inert.
  scrollInFrame(container, 'start');
  const cr = container.getBoundingClientRect();
  const tr = target.getBoundingClientRect();
  const left = container.scrollLeft + tr.left - cr.left - (container.clientWidth - tr.width) / 2;
  const top = container.scrollTop + tr.top - cr.top - Math.min(container.clientHeight / 3, 180);
  container.scrollTo({
    left: Math.max(0, left),
    top: Math.max(0, top),
    behavior: 'smooth',
  });
  target.classList.add('goto-highlight-svg');
  setTimeout(() => target.classList.remove('goto-highlight-svg'), 1800);
  return true;
}

function wireDiagramClusterJumps() {
  document.querySelectorAll('.er-cluster-jump').forEach(btn => {
    if (btn.dataset.annotateJumpWired === 'true') return;
    btn.dataset.annotateJumpWired = 'true';
    btn.textContent = 'Jump to diagram \u2193';
    btn.setAttribute('aria-label', 'Jump to the ' + (btn.dataset.clusterJump || '') + ' cluster in the diagram');
    // Capture phase plus stopImmediatePropagation replaces any stale baked
    // handler, preventing two competing smooth-scroll animations in v4.2.
    btn.addEventListener('click', e => {
      e.preventDefault();
      e.stopImmediatePropagation();
      const ok = jumpToDiagramCluster(btn);
      if (!ok) {
        btn.disabled = true;
        btn.title = 'Diagram target unavailable in this version';
      }
    }, true);
  });
}

// ── Content-fullscreen detection (P1: rails must auto-collapse) ─────
// Content docs own their fullscreen affordances (diagram-plot's ⛶ button
// sets the host to position:fixed inside the IFRAME viewport). The shell
// can't see that directly, so the adapter watches for any large fixed
// overlay and tells the shell, which auto-collapses the rails for the
// duration (restoring them on exit). Detection is generic: any visible
// position:fixed element covering most of the viewport at high z-index.
let lastFullscreenState = false;
function detectContentFullscreen() {
  let active = false;
  try {
    const els = document.querySelectorAll('[style*="fixed"], .diagram-fullscreen-host');
    for (const el of els) {
      const cs = getComputedStyle(el);
      if (cs.position !== 'fixed') continue;
      if ((parseInt(cs.zIndex, 10) || 0) < 1000) continue;
      const r = el.getBoundingClientRect();
      if (r.width >= window.innerWidth * 0.85 && r.height >= window.innerHeight * 0.85) {
        active = true;
        break;
      }
    }
  } catch {}
  if (active !== lastFullscreenState) {
    lastFullscreenState = active;
    postToParent({ type: 'annotate:content-fullscreen', active });
  }
}

// ── Selection, hover and table affordances (U-03, U-04, U-12) ─────────
// A drag that selects text inside one anchor opens the composer quoting it.
function wireSelectionComments() {
  let gesture = null;
  document.addEventListener('mousedown', e => { gesture = { x: e.clientX, y: e.clientY }; }, true);
  document.addEventListener('mouseup', e => {
    if (!gesture) return;
    const drag = Math.hypot(e.clientX - gesture.x, e.clientY - gesture.y) > 3 || e.detail >= 2;
    gesture = null;
    if (!drag) return;
    const s = getSelection();
    const start = s && s.anchorNode && s.anchorNode.parentElement;
    if (!start || start.closest(INTERACTIVE_SEL + ', [data-annotate-strip], #badge-layer')) return;
    const anchor = findParentAnchor(start);
    if (!anchor || !selectedQuoteIn(anchor)) return;
    const aid = getAnchorIdFromEl(anchor);
    selectionOpenedAt = performance.now();
    postToParent({ type: 'annotate:pin-click', anchorId: aid, anchorLabel: anchorName(aid),
      target: captureTarget(start, anchor, e), x: e.clientX, y: e.clientY });
  }, true);
}
// Hovering a rail card outlines what it is about; hovering the document
// outlines what a click would comment on.
let cardHoverEl = null;
function setCardHover(anchorId, target) {
  if (cardHoverEl) cardHoverEl.classList.remove('unified-annotation-hover');
  cardHoverEl = null;
  if (!anchorId) return;
  const a = displayAnchorEl(anchorId);
  const inner = a && resolveInnerEl(a, target);
  cardHoverEl = (inner && inner.el) || a;
  if (cardHoverEl) cardHoverEl.classList.add('unified-annotation-hover');
}
function wireCommentableHover() {
  let commentable = null;
  document.addEventListener('pointerover', e => {
    if (!byMouse(e)) return;
    if (commentable) commentable.classList.remove('unified-commentable');
    commentable = null;
    if (e.target.closest(INTERACTIVE_SEL + ', [data-annotate-strip], .annotate-unchanged-bar, #badge-layer')) return;
    const a = findParentAnchor(e.target);
    if (a) { commentable = a; a.classList.add('unified-commentable'); }
  });
  document.addEventListener('pointerout', e => {
    if (!byMouse(e)) return;
    if (commentable && !commentable.contains(e.relatedTarget)) {
      commentable.classList.remove('unified-commentable');
      commentable = null;
    }
  });
}
// Tables wrap to fit the document at every width, whole words only (lh1).
// Only when a single word or image cannot fit does the table scroll sideways
// in its own labelled region; then the side with more columns fades and the
// hint shows, so it reads as its own scroll box, not the page.
function wrapScrollTables() {
  document.querySelectorAll('table').forEach(t => {
    if (t.closest('.unified-table-scroll') || t.closest('[data-annotate-strip]')) return;
    const frame = document.createElement('div');
    frame.className = 'unified-table-frame';
    const wrap = document.createElement('div');
    wrap.className = 'unified-table-scroll';
    wrap.tabIndex = 0;
    wrap.setAttribute('role', 'region');
    wrap.setAttribute('aria-label', 'Table · scroll sideways');
    t.before(frame);
    frame.append(wrap);
    wrap.append(t);
    const hint = document.createElement('p');
    hint.className = 'unified-table-hint';
    hint.textContent = 'Scroll sideways to see all columns';
    frame.after(hint);
    wrap.addEventListener('scroll', () => markTableEdges(wrap), { passive: true });
    t.querySelectorAll('img').forEach(img => img.addEventListener('load', () => markTableEdges(wrap)));
    markTableEdges(wrap);
  });
  window.addEventListener('resize', () => document.querySelectorAll('.unified-table-scroll').forEach(markTableEdges));
  scheduleBadgeRefresh();
}
// Code and terminal blocks get a copy button, top right (GitHub, VitePress,
// Docusaurus): it shows on hover or focus, always on touch, and turns into a
// check with "Copied" for 2 s.
const COPY_ICONS = '<svg class="aa-copy-i" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>'
  + '<svg class="aa-copied-i" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M20 6 9 17l-5-5"/></svg>';
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch {}
  // No Clipboard API (plain-http page, or blocked): the selection fallback.
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.setAttribute('readonly', '');
  ta.style.cssText = 'position:fixed;top:0;left:-9999px;font-size:12pt';
  document.body.append(ta);
  ta.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch {}
  ta.remove();
  return ok;
}
function wireCopyButtons() {
  let live = document.getElementById('aa-copy-live');
  if (!live) {
    live = document.createElement('span');
    live.id = 'aa-copy-live';
    live.className = 'aa-sr';
    live.setAttribute('role', 'status');
    document.body.append(live);
  }
  document.querySelectorAll('pre').forEach(pre => {
    if (pre.querySelector(':scope > .aa-copy') || pre.closest('[data-annotate-strip]')) return;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'aa-copy';
    btn.title = btn.ariaLabel = 'Copy';
    btn.innerHTML = COPY_ICONS;
    btn.addEventListener('click', async () => {
      const src = pre.cloneNode(true);
      src.querySelectorAll('.aa-copy').forEach(b => b.remove());
      const ok = await copyText(src.textContent.replace(/\n$/, ''));
      btn.classList.toggle('is-copied', ok);
      btn.title = btn.ariaLabel = live.textContent = ok ? 'Copied' : 'Copy failed';
      clearTimeout(btn._t);
      btn._t = setTimeout(() => { btn.classList.remove('is-copied'); btn.title = btn.ariaLabel = 'Copy'; live.textContent = ''; }, 2000);
    });
    pre.classList.add('aa-copy-host');
    pre.append(btn);
  });
}
function markTableEdges(wrap) {
  const rest = wrap.scrollWidth - wrap.clientWidth - wrap.scrollLeft;
  const wide = wrap.scrollWidth - wrap.clientWidth > 1;
  wrap.parentElement.classList.toggle('is-more-left', wrap.scrollLeft > 1);
  wrap.parentElement.classList.toggle('is-more-right', rest > 1);
  wrap.parentElement.classList.toggle('is-wide', wide);
  wrap.setAttribute('aria-label', wide ? 'Table · scroll sideways' : 'Table');
  const hint = wrap.parentElement.nextElementSibling;
  if (hint && hint.classList.contains('unified-table-hint')) hint.hidden = !wide;
}
function ensureAffordanceStyle() {
  if (document.getElementById('annotate-affordance-style')) return;
  const style = document.createElement('style');
  style.id = 'annotate-affordance-style';
  style.textContent = `
    .unified-annotation-hover,.unified-commentable{outline:2px solid var(--color-primary)!important;outline-offset:2px!important}
    .unified-commentable{cursor:crosshair}
    .bpin[role=button]:focus-visible{outline:3px solid var(--color-primary);outline-offset:3px}
    .unified-table-frame{position:relative;max-width:calc(100% - 28px);margin-left:28px}
    .unified-table-frame::before,.unified-table-frame::after{content:'';position:absolute;top:0;bottom:0;width:32px;pointer-events:none;opacity:0}
    .unified-table-frame::before{left:0;background:linear-gradient(to right,var(--color-base-100),transparent)}
    .unified-table-frame::after{right:2px;background:linear-gradient(to left,var(--color-base-100),transparent)}
    .unified-table-frame.is-more-left::before,.unified-table-frame.is-more-right::after{opacity:1}
    .unified-table-scroll{overflow-x:auto;overscroll-behavior-x:contain}
    .unified-table-frame.is-wide .unified-table-scroll{border-right:2px solid var(--color-base-300)}
    .unified-table-scroll table{width:100%;min-width:0;max-width:100%;table-layout:auto!important}
    .unified-table-scroll th,.unified-table-scroll td{overflow-wrap:normal!important;word-break:normal!important;hyphens:none!important;min-width:0}
    @media (max-width:480px){.unified-table-scroll th,.unified-table-scroll td{padding-left:4px!important;padding-right:4px!important}}
    .unified-table-hint{font-size:calc(10.5px * var(--aa-text, 1));margin:4px 0 14px 28px;color:var(--color-base-content)}
    pre{white-space:pre-wrap!important;overflow-wrap:anywhere}
    pre.aa-copy-host{position:relative;padding-right:44px!important}
    .aa-copy{position:absolute;top:6px;right:6px;display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;padding:0;border:1px solid var(--color-base-300);border-radius:6px;background:var(--color-base-100);color:var(--color-base-content);cursor:pointer;opacity:0;transition:opacity .15s}
    .aa-copy svg{width:15px;height:15px}
    pre:hover>.aa-copy,.aa-copy:focus-visible,.aa-copy.is-copied{opacity:1}
    @media (hover:none){.aa-copy{opacity:1}}
    .aa-copy:focus-visible{outline:2px solid var(--color-primary);outline-offset:1px}
    .aa-copy .aa-copied-i,.aa-copy.is-copied .aa-copy-i{display:none}
    .aa-copy.is-copied .aa-copied-i{display:block;color:var(--color-success,currentColor)}
    .aa-sr{position:fixed;top:0;left:0;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
  `;
  document.head.append(style);
}
// U-11: a link to another page on this server opens in the whole window,
// never inside the document frame. Links into this document stay in place.
// UI-21: a link to another site opens in a new tab (the browser's own
// target=_blank, so no pop-up blocker), never inside the document frame.
function wirePageLinks() {
  document.addEventListener('click', e => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const link = e.target.closest && e.target.closest('a[href]');
    if (!link || (link.target && link.target !== '_self')) return;
    let url;
    try { url = new URL(link.getAttribute('href'), document.baseURI); } catch { return; }
    if ((url.protocol === 'http:' || url.protocol === 'https:') && url.origin !== location.origin && url.origin !== PARENT_ORIGIN) {
      link.target = '_blank';
      link.rel = (link.rel ? link.rel + ' ' : '') + 'noopener';
      return;
    }
    if (!PARENT_ORIGIN || url.origin !== PARENT_ORIGIN) return;
    if (url.pathname === location.pathname && url.search === location.search) return;
    e.preventDefault();
    postToParent({ type: 'annotate:navigate', url: url.href });
  });
}

// ── Plans: what changed since the previous revision ──────────────────
// A plan revision (plans/<id>/vN.html) reads the previous revision next to
// it, compares section by section, and offers "show changes": changed
// sections get a "Changed in vN" tag, and inside them changed words are
// marked (added: underlined, removed: struck). Comments, pins and decisions
// are the shell's own and are not touched.
function initPlanChanges() {
  const planId = typeof META.doc === 'string' && META.doc.startsWith('plan:') ? META.doc.slice(5) : null;
  const m = /^v(\d+)$/.exec(META.version || '');
  if (!planId || !m) return;
  const N = parseInt(m[1], 10);
  const V = 'v' + N, PREV = 'v' + (N - 1);
  const KEY = 'annotate:plan-changes';
  const css = `
  .sp-rev button,.sp-rev a{font:inherit;font-size:calc(10.5px * var(--aa-text, 1));color:inherit;background:none;border:0;padding:0;cursor:pointer;text-decoration:underline;text-underline-offset:2px}
  .sp-chg-tag{display:none}
  body.sp-show-changes .sp-chg-tag{display:inline-block}
  ins.sp-ins{text-decoration:none;background:var(--success-soft);color:inherit}
  del.sp-del{color:var(--muted)}
  .sp-ins-block{background:var(--success-soft)}
  .sp-del-block{color:var(--muted);text-decoration:line-through;margin:4px 0}`;
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const LEAF = 'p,li,td,th,h2,h3,h4,figcaption,dt,dd';
  const leaves = (root) => [...root.querySelectorAll(LEAF)].filter(el => !el.querySelector(LEAF) && !el.closest('.sp-rev'));
  // Longest-common-subsequence diff over two arrays (small: one section).
  function lcs(a, b) {
    const n = a.length, mm = b.length;
    const t = Array.from({ length: n + 1 }, () => new Int32Array(mm + 1));
    for (let i = n - 1; i >= 0; i--) for (let j = mm - 1; j >= 0; j--)
      t[i][j] = a[i] === b[j] ? t[i + 1][j + 1] + 1 : Math.max(t[i + 1][j], t[i][j + 1]);
    const ops = [];
    let i = 0, j = 0;
    while (i < n && j < mm) {
      if (a[i] === b[j]) { ops.push(['=', i, j]); i++; j++; }
      else if (t[i + 1][j] >= t[i][j + 1]) { ops.push(['-', i, -1]); i++; }
      else { ops.push(['+', -1, j]); j++; }
    }
    while (i < n) ops.push(['-', i++, -1]);
    while (j < mm) ops.push(['+', -1, j++]);
    return ops;
  }
  const escH = (s) => s.replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  function wordDiff(oldText, newText) {
    const a = oldText.split(/(\s+)/), b = newText.split(/(\s+)/);
    if (a.length * b.length > 250000) return '<del class="sp-del">' + escH(oldText) + '</del> <ins class="sp-ins">' + escH(newText) + '</ins>';
    let out = '', del = '', ins = '';
    const flush = () => { if (del.trim()) out += '<del class="sp-del">' + escH(del) + '</del>'; else out += escH(del); if (ins.trim()) out += '<ins class="sp-ins">' + escH(ins) + '</ins>'; else out += escH(ins); del = ''; ins = ''; };
    lcs(a, b).forEach(([op, i, j]) => {
      if (op === '=') { flush(); out += escH(b[j]); }
      else if (op === '-') del += a[i];
      else ins += b[j];
    });
    flush();
    return out;
  }
  let applied = null; // [{el, html}] originals to restore
  // Snapshot the document as authored, before pins and strips are added.
  function sectionsOf(doc) {
    const map = new Map();
    doc.querySelectorAll('section[data-anchor-id]').forEach(sec => {
      const ls = leaves(sec).filter(el => el.tagName !== 'H2');
      map.set(sec.dataset.anchorId, { sec, text: norm(sec.textContent), leaves: ls, texts: ls.map(el => norm(el.textContent)) });
    });
    return map;
  }
  const ORIG = sectionsOf(document);
  function apply(prevDoc) {
    const cur = ORIG, old = sectionsOf(prevDoc);
    applied = [];
    let changed = 0;
    cur.forEach((c, id) => {
      const sec = c.sec;
      const o = old.get(id);
      const isNew = !o;
      if (!isNew && o.text === c.text) return;
      changed++;
      sec.classList.add('sp-changed');
      const h = sec.querySelector('h2');
      if (h && !h.querySelector('.sp-chg-tag')) h.insertAdjacentHTML('beforeend', `<span class="chip sp-chg-tag">${isNew ? 'New in ' + V : 'Changed in ' + V}</span>`);
      if (isNew) return;
      const nl = c.leaves, ol = o.leaves;
      const ops = lcs(o.texts, c.texts);
      // Pair a removed leaf with the next added leaf as one changed line.
      for (let k = 0; k < ops.length; k++) {
        const [op, i, j] = ops[k];
        if (op === '-' && ops[k + 1] && ops[k + 1][0] === '+') {
          const el = nl[ops[k + 1][2]];
          applied.push({ el, html: el.innerHTML, mark: true });
          el.dataset.spNew = el.innerHTML;
          el.dataset.spDiff = wordDiff(o.texts[i], c.texts[ops[k + 1][2]]);
          k++;
        } else if (op === '+') {
          applied.push({ el: nl[j], cls: 'sp-ins-block' });
        } else if (op === '-' && !/^(TD|TH)$/.test(ol[i].tagName)) {
          // A removed paragraph or list item: shown struck through where it was.
          const next = ops.slice(k + 1).find(x => x[0] === '=');
          const anchorEl = next ? nl[next[2]] : null;
          const ghost = document.createElement(ol[i].tagName === 'LI' ? 'li' : 'p');
          ghost.className = 'sp-del-block sp-ghost';
          ghost.textContent = norm(ol[i].textContent);
          ghost.hidden = true;
          if (anchorEl && anchorEl.parentNode) anchorEl.parentNode.insertBefore(ghost, anchorEl);
          else (ol[i].tagName === 'LI' ? (sec.querySelector('ul,ol') || sec) : sec).appendChild(ghost);
          applied.push({ el: ghost, ghost: true });
        }
      }
    });
    return changed;
  }
  function show(on) {
    document.body.classList.toggle('sp-show-changes', on);
    (applied || []).forEach(a => {
      if (a.mark) a.el.innerHTML = on ? a.el.dataset.spDiff : a.el.dataset.spNew;
      else if (a.cls) a.el.classList.toggle(a.cls, on);
      else if (a.ghost) a.el.hidden = !on;
    });
    const btn = document.getElementById('sp-rev-toggle');
    if (btn) { btn.setAttribute('aria-pressed', String(on)); btn.textContent = on ? 'hide changes' : 'show changes'; }
    try { localStorage.setItem(KEY, on ? 'on' : 'off'); } catch {}
    // Re-place pins after the text moved.
    window.dispatchEvent(new Event('resize'));
  }
  (async () => {
    const style = document.createElement('style'); style.id = 'annotate-plan-changes-style'; style.textContent = css; document.head.appendChild(style);
    const base = (META.publicBasePath || '') + '/';
    let meta = null;
    try { meta = await (await fetch(base + 'api/plans/' + encodeURIComponent(planId), { cache: 'no-cache' })).json(); } catch {}
    const hist = (meta && meta.history) || [];
    const mine = hist.find(h => h.version === V) || {};
    const total = hist.length || N;
    const bar = document.createElement('span');
    bar.className = 'sp-rev';
    bar.innerHTML = ` · Revision ${V} of ${total}${mine.label ? ' (' + escH(mine.label) + ')' : ''}` +
      (N > 1 ? ` · <span id="sp-rev-chg">comparing with ${PREV}…</span> — <button type="button" id="sp-rev-toggle" aria-pressed="false">show changes</button> · <a href="#" data-rev="${PREV}" title="Open the previous revision">${PREV}</a>` : ' · first revision') +
      (N < total ? ` · <a href="#" data-rev="v${N + 1}" title="Open the next revision">v${N + 1}</a>` : '');
    ['click', 'mousedown', 'mouseup', 'pointerdown', 'pointerup'].forEach(t => bar.addEventListener(t, e => e.stopPropagation()));
    // A revision opens in the page's Plans tab (one URL, #view=plans&v=…).
    bar.addEventListener('click', e => {
      const a = e.target.closest('a[data-rev]');
      if (!a) return;
      e.preventDefault();
      postToParent({ type: 'annotate:open-version', version: a.dataset.rev });
    });
    const scope = document.querySelector('.aa');
    if (!scope) return;
    let banner = scope.querySelector('.plan-scope');
    if (!banner) { banner = document.createElement('div'); banner.className = 'plan-scope'; banner.innerHTML = '<strong>Plan</strong>'; scope.prepend(banner); }
    banner.appendChild(bar);
    if (N <= 1) return;
    let prevDoc;
    try {
      const r = await fetch(base + 'plans/' + encodeURIComponent(planId) + '/' + PREV + '.html', { cache: 'no-cache' });
      if (!r.ok) throw new Error(String(r.status));
      prevDoc = new DOMParser().parseFromString(await r.text(), 'text/html');
    } catch { document.getElementById('sp-rev-chg').textContent = PREV + ' could not be read'; return; }
    const n = apply(prevDoc);
    document.getElementById('sp-rev-chg').textContent = n ? n + (n === 1 ? ' section' : ' sections') + ' changed since ' + PREV : 'No changes since ' + PREV;
    const btn = document.getElementById('sp-rev-toggle');
    btn.addEventListener('click', () => show(btn.getAttribute('aria-pressed') !== 'true'));
    let pref = null;
    try { pref = localStorage.getItem(KEY); } catch {}
    let top = '';
    try { top = window.parent.location.hash; } catch {}
    const h = new URLSearchParams(top.replace(/^#/, ''));
    const want = h.has('changes') ? h.get('changes') === '1' : pref !== 'off';
    if (n && want) show(true);
  })();
}

// ── Annotate owns colour, type and width (Chang, 2026-10-10) ─────────
// Author CSS keeps its layout, but its colours, fonts and page width caps
// give way to annotate's theme, text size and widths, so every document reads
// in light and dark. Neutral text and surfaces take the theme's; tinted ones
// map by hue to the theme's state colours (red → error, amber → warning,
// green → success, blue/purple → link); strong accent fills stay. Font sizes
// keep the author's hierarchy and follow the text size. SVG graphics keep
// their own colours; embedded pages (iframes) keep their own look and say so.
const OWNED_BORDER_COLORS = ['border-top-color', 'border-right-color', 'border-bottom-color', 'border-left-color'];
const SVG_SELECTOR = /(^|[\s>+~,(])(svg|path|rect|circle|ellipse|line|polyline|polygon|text|tspan|g|marker|use|foreignObject)\b/i;
const PAGE_SELECTOR = /^\s*(html|body|:root)\b/i;
const PAGE_CAP_PX = 720;
const STATE_TEXT = { err: 'var(--err-text)', warn: 'var(--warn-text)', ok: 'var(--ok-text)', link: 'var(--link)' };
const STATE_SOFT = { err: 'var(--error-soft)', warn: 'var(--warning-soft)', ok: 'var(--success-soft)', link: 'var(--primary-soft)' };
function isAnnotateSheet(sheet) {
  const node = sheet.ownerNode;
  if (!node) return false;
  if (node.id && (node.id.startsWith('annotate') || node.id === 'goto-highlight-style')) return true;
  return /\/(daisyui|content)\.css(\?|$)/.test(node.href || '');
}
// Any CSS colour as {h, l, c, a} (HSL hue and lightness, chroma c = max − min;
// 0–1 except h), read back through a 1px canvas so named, hex, rgb, hsl and
// oklch colours all work. A var() resolves against the page's root custom
// properties. Annotate's own theme tokens, and values that cannot be resolved,
// return null and are left as written.
const THEME_TOKEN = /var\(--(color-|ok-text|warn-text|err-text|info-text|link|muted|faint|line|soft|primary-soft|success-soft|warning-soft|error-soft)/;
const colorCache = new Map();
let colorProbe = null;
function colorOf(value) {
  if (!value || THEME_TOKEN.test(value) || /currentcolor|inherit|initial|unset|revert/i.test(value)) return null;
  if (colorCache.has(value)) return colorCache.get(value);
  let resolved = value;
  for (let i = 0; i < 4 && /var\(/.test(resolved); i++) {
    resolved = resolved.replace(/var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*(?:\([^()]*\))?[^()]*))?\)/g, (_, name, fallback) =>
      getComputedStyle(document.documentElement).getPropertyValue(name).trim() || (fallback || '').trim());
  }
  let out = null;
  if (resolved && !/var\(/.test(resolved) && CSS.supports('color', resolved)) {
    colorProbe = colorProbe || document.createElement('canvas').getContext('2d', { willReadFrequently: true });
    colorProbe.clearRect(0, 0, 1, 1);
    colorProbe.fillStyle = resolved;
    colorProbe.fillRect(0, 0, 1, 1);
    const [r, g, b, a] = [...colorProbe.getImageData(0, 0, 1, 1).data].map(v => v / 255);
    const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
    let h = 0;
    if (d) h = 60 * (max === r ? ((g - b) / d + 6) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4);
    out = { h, l: (max + min) / 2, c: d, a };
  }
  colorCache.set(value, out);
  return out;
}
// Greys, near-black and dark slates are surfaces and inks, not meaning.
function isNeutral(c) {
  return c.c < 0.06 || c.l <= 0.08 || (c.l < 0.3 && c.c < 0.15);
}
function stateOf(h) {
  return h < 20 || h >= 330 ? 'err' : h < 65 ? 'warn' : h < 170 ? 'ok' : 'link';
}
function ownColor(style, prop, page) {
  const value = style.getPropertyValue(prop).trim();
  if (!value || THEME_TOKEN.test(value)) return;
  if (page) { style.removeProperty(prop); return; } // the page's own colours are the theme's
  const c = colorOf(value);
  if (!c || c.a === 0) return;
  const priority = style.getPropertyPriority(prop);
  if (prop === 'background-color') {
    if (!isNeutral(c) && c.l < 0.97) { // tinted: pastel → soft state colour; accent fill stays
      if (c.l >= 0.8) style.setProperty(prop, STATE_SOFT[stateOf(c.h)], priority);
      return;
    }
    // A sticky or fixed bar must stay opaque over the content scrolling under it.
    if (c.l >= 0.85 && /sticky|fixed/.test(style.getPropertyValue('position'))) style.setProperty(prop, 'var(--color-base-100)', priority);
    else if (c.l >= 0.85) style.removeProperty(prop);
    else style.setProperty(prop, c.l > 0.4 ? 'var(--color-base-200)' : 'var(--color-neutral)', priority);
    return;
  }
  if (c.l >= 0.85) return; // light text sits on a dark or accent fill, which stays dark
  // Dark inks (navy, slate) are body text; clearly coloured text keeps its meaning.
  if (c.c > 0.2) style.setProperty(prop, STATE_TEXT[stateOf(c.h)], priority);
  else style.removeProperty(prop);
}
function scaleSize(style, prop, page) {
  const m = /^([\d.]+)(px|%)$/.exec(style.getPropertyValue(prop).trim());
  if (m && (m[2] === 'px' || page)) {
    style.setProperty(prop, 'calc(' + m[1] + m[2] + ' * var(--aa-text, 1))', style.getPropertyPriority(prop));
  }
}
function ownDeclarations(style, page) {
  // Light or transparent text was drawn on this rule's own fill (a button,
  // a hero, gradient-clipped text): the pair stays together.
  const paired = ['color', '-webkit-text-fill-color'].some(p => {
    const c = colorOf(style.getPropertyValue(p).trim());
    return c && (c.a === 0 || c.l >= 0.85);
  });
  if (!paired || page) {
    ownColor(style, 'background-color', page);
    if (/gradient\(/.test(style.getPropertyValue('background-image'))) style.removeProperty('background-image');
  }
  ownColor(style, 'color', page);
  ownColor(style, '-webkit-text-fill-color', page);
  OWNED_BORDER_COLORS.forEach(p => {
    const c = colorOf(style.getPropertyValue(p).trim());
    if (c && c.a > 0 && isNeutral(c)) style.setProperty(p, 'var(--line)', style.getPropertyPriority(p)); // accents stay
  });
  if (!/mono|courier|consolas|menlo/i.test(style.getPropertyValue('font-family'))) style.removeProperty('font-family');
  scaleSize(style, 'font-size', page);
  scaleSize(style, 'line-height', false);
  const cap = /^([\d.]+)(px|rem|em)$/.exec(style.getPropertyValue('max-width').trim());
  if (cap && parseFloat(cap[1]) * (cap[2] === 'px' ? 1 : 16) >= PAGE_CAP_PX) style.removeProperty('max-width');
}
function ownRules(rules) {
  for (const rule of rules) {
    if (rule.selectorText !== undefined && rule.style && !SVG_SELECTOR.test(rule.selectorText)) {
      ownDeclarations(rule.style, PAGE_SELECTOR.test(rule.selectorText));
    }
    if (rule.cssRules) ownRules(rule.cssRules); // @media, @supports, @layer, nesting
  }
}
function ownAuthorStyles() {
  for (const sheet of document.styleSheets) {
    if (isAnnotateSheet(sheet)) continue;
    let rules;
    try { rules = sheet.cssRules; } catch { continue; } // a cross-origin sheet cannot be read
    ownRules(rules);
  }
  document.querySelectorAll('[style]').forEach(el => {
    if (!el.closest('svg')) ownDeclarations(el.style, el === document.body || el === document.documentElement);
  });
  document.querySelectorAll('[bgcolor]').forEach(el => { if (!el.closest('svg')) el.removeAttribute('bgcolor'); });
  document.querySelectorAll('font').forEach(el => ['color', 'face', 'size'].forEach(a => el.removeAttribute(a)));
  // A hand-built document gets annotate's face and text colour; its layout
  // and components stay its own (no .aa rules).
  if (!document.querySelector('.aa')) document.body.classList.add('aa-owned');
  document.querySelectorAll('iframe').forEach(frame => {
    if (frame.previousElementSibling && frame.previousElementSibling.classList.contains('annotate-embed-note')) return;
    const note = document.createElement('div');
    note.className = 'annotate-embed-note';
    note.textContent = 'Embedded page · keeps its own styling';
    frame.insertAdjacentElement('beforebegin', note);
  });
}

// ── Images: the IMG id label and the scale view ─────────────────────
// An image's id is the start of its content hash: publish writes it as
// data-img (long_pages.image_ids); an older page falls back to the same hash
// at the front of a staged asset's file name (assets/<sha256[:12]>-name).
// Under each image: its id and 25/50/75/100%, which open it at that share of
// its real pixel size (Chang, 2026-10-31). A tap on the image itself is
// unchanged: it comments, as everywhere else.
function imageId(img) {
  if (/^[0-9A-F]{4,64}$/.test(img.dataset.img || '')) return img.dataset.img;
  const m = /(?:^|\/)([0-9a-f]{12})-[^/]*$/.exec(img.getAttribute('data-full') || img.getAttribute('src') || '');
  return m ? m[1].slice(0, 4).toUpperCase() : '';
}

function viewableImage(img) {
  return !img.closest('a[href], .aa-viewer, #badge-layer, [data-annotate-strip]') && findParentAnchor(img) ? img : null;
}

const SCALES = [25, 50, 75, 100];
const MAGNIFIER = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/><path d="M11 8v6"/><path d="M8 11h6"/></svg>';
function scaleButtons(label, current) {
  return `<span class="aa-img-zoom" role="group" aria-label="${label}"><span class="aa-img-zoom-icon">${MAGNIFIER}</span>` +
    SCALES.map(p => `<button type="button" data-aa-scale="${p}" aria-pressed="${p === current}">${p}%</button>`).join('') + '</span>';
}

const labelled = new WeakSet();
function labelImages() {
  document.querySelectorAll('img').forEach(img => {
    if (labelled.has(img) || !viewableImage(img)) return;
    labelled.add(img);
    const id = imageId(img);
    const bar = document.createElement('span');
    bar.className = 'aa-img-bar';
    bar.innerHTML = (id ? `<span class="aa-img-id">IMG ${id}</span>` : '') +
      scaleButtons(`View ${id ? 'IMG ' + id : 'the image'} larger at`, 0);
    bar.querySelectorAll('[data-aa-scale]').forEach(b => b.addEventListener('click', () => openViewer(img, +b.dataset.aaScale)));
    img.after(bar);
  });
}

// The image's real pixels: publish writes the original's width and height,
// also when the page shows a 1,200 px preview.
function imagePixels(img, big) {
  const w = +img.getAttribute('width'), h = +img.getAttribute('height');
  if (w > 0 && h > 0) return [w, h];
  return big && big.naturalWidth ? [big.naturalWidth, big.naturalHeight] : null;
}

// The preview while it holds every pixel this scale draws on this screen, else the original.
function scaleSource(img, pct) {
  const shown = img.currentSrc || img.src, full = img.getAttribute('data-full');
  const px = imagePixels(img);
  if (!full) return shown;
  return px && img.naturalWidth >= px[0] * pct / 100 * (window.devicePixelRatio || 1) ? shown : full;
}

let viewer = null; // {box, img, big, aid, id, css, stage, frame, pins, pct, scrollY}

function viewerPins() {
  if (!viewer) return;
  const { pins, aid, id, css } = viewer;
  pins.querySelectorAll('.bpin').forEach(p => p.remove());
  (latestPins[aid] || []).forEach(en => {
    const t = en.target;
    if (!t || !t.offset || !(id ? t.image === id : t.css === css)) return;
    const b = makePin(aid, [en], false);
    b.classList.add('bpin', 'aa-viewer-pin');
    b.style.left = clamp01(t.offset.dx, 0.5) * 100 + '%';
    b.style.top = clamp01(t.offset.dy, 0.5) * 100 + '%';
    pins.append(b);
  });
}

// Show the image at pct of its pixels. A new view starts at the image's top
// left; a change of scale keeps the spot in the middle of the view there.
function viewerScale(pct, fresh) {
  const v = viewer;
  const px = imagePixels(v.img, v.big);
  if (!px) return;
  const { stage, frame } = v;
  const st = stage.getBoundingClientRect(), before = frame.getBoundingClientRect();
  const mid = [st.left + stage.clientWidth / 2, st.top + stage.clientHeight / 2];
  const at = fresh || !before.width ? [0, 0] : [(mid[0] - before.left) / before.width, (mid[1] - before.top) / before.height];
  v.pct = pct;
  frame.style.width = Math.round(px[0] * pct / 100) + 'px';
  frame.style.height = Math.round(px[1] * pct / 100) + 'px';
  if (v.big.getAttribute('src') !== v.img.getAttribute('data-full')) v.big.src = scaleSource(v.img, pct); // once on the original, stay
  v.box.querySelectorAll('[data-aa-scale]').forEach(b => b.setAttribute('aria-pressed', String(+b.dataset.aaScale === pct)));
  const after = frame.getBoundingClientRect();
  if (fresh) { stage.scrollLeft = 0; stage.scrollTop = 0; return; }
  stage.scrollLeft += after.left + at[0] * after.width - mid[0];
  stage.scrollTop += after.top + at[1] * after.height - mid[1];
}

function closeViewer() {
  if (!viewer) return;
  const { box, scrollY } = viewer;
  viewer = null;
  box.remove();
  document.documentElement.classList.remove('aa-viewer-open');
  window.scrollTo(window.scrollX, scrollY);
}

function openViewer(img, pct) {
  closeViewer();
  const anchorEl = findParentAnchor(img);
  const aid = getAnchorIdFromEl(anchorEl);
  const id = imageId(img);
  const box = document.createElement('div');
  box.className = 'aa-viewer';
  box.setAttribute('role', 'dialog');
  box.setAttribute('aria-modal', 'true');
  box.innerHTML = `<div class="aa-viewer-bar"><span class="aa-viewer-title"></span>
    ${scaleButtons('Scale', pct)}
    <span class="aa-viewer-hint">Tap the image to comment on that spot</span>
    <button type="button" class="aa-viewer-close" aria-label="Close the image">✕</button></div>
    <div class="aa-viewer-stage"><div class="aa-viewer-frame"><img alt=""><div class="aa-viewer-pins"></div></div></div>`;
  const title = (id ? 'IMG ' + id + ' · ' : '') + (img.getAttribute('alt') || anchorName(aid));
  box.querySelector('.aa-viewer-title').textContent = title;
  box.setAttribute('aria-label', title);
  const big = box.querySelector('.aa-viewer-frame img');
  big.alt = img.getAttribute('alt') || '';
  viewer = { box, img, big, aid, id, css: cssPathFrom(anchorEl, img) || '', scrollY: window.scrollY, pct,
             stage: box.querySelector('.aa-viewer-stage'), frame: box.querySelector('.aa-viewer-frame'),
             pins: box.querySelector('.aa-viewer-pins') };
  big.src = scaleSource(img, pct);
  document.documentElement.classList.add('aa-viewer-open');
  document.body.append(box);
  viewerScale(pct, true);
  // A page without the original's size learns it from the file.
  big.addEventListener('load', () => { if (viewer && viewer.big === big && !imagePixels(img)) viewerScale(viewer.pct); });
  viewerPins();
  box.querySelectorAll('[data-aa-scale]').forEach(b => b.addEventListener('click', () => viewerScale(+b.dataset.aaScale)));
  box.querySelector('.aa-viewer-close').addEventListener('click', closeViewer);
  big.addEventListener('click', viewerComment);
  box.querySelector('.aa-viewer-close').focus();
}

// A tap on the image: the same create message a click on the page sends,
// with the point on the image, so the page pin lands on that spot too.
function viewerComment(e) {
  const v = viewer;
  const r = v.big.getBoundingClientRect();
  const dx = (e.clientX - r.left) / r.width, dy = (e.clientY - r.top) / r.height;
  if (!(dx >= 0 && dx <= 1 && dy >= 0 && dy <= 1)) return;
  const target = { schema: 1, tag: 'img', offset: { dx: Math.round(dx * 1000) / 1000, dy: Math.round(dy * 1000) / 1000 } };
  if (v.css) target.css = v.css;
  if (v.id) target.image = v.id;
  target.image_src = v.img.getAttribute('data-full') || v.img.getAttribute('src') || '';
  v.pins.querySelectorAll('.aa-viewer-new').forEach(p => p.remove());
  const mark = document.createElement('div');
  mark.className = 'aa-viewer-pin aa-viewer-new';
  mark.style.left = dx * 100 + '%';
  mark.style.top = dy * 100 + '%';
  v.pins.append(mark);
  postToParent({ type: 'annotate:pin-click', anchorId: v.aid, anchorLabel: anchorName(v.aid), target, x: e.clientX, y: e.clientY });
}

function wireViewerKeys() {
  window.addEventListener('keydown', e => {
    if (!viewer || e.key !== 'Escape') return;
    e.stopImmediatePropagation();
    closeViewer();
  }, true);
}

// ── Init ─────────────────────────────────────────────────────────
async function init() {
  try { ownAuthorStyles(); } catch (e) { console.warn('[adapter] could not apply annotate styling', e); }
  initPlanChanges();
  wireClicks();
  wireBridge();
  wireSelectionComments();
  wireCommentableHover();
  wirePageLinks();
  ensureAffordanceStyle();
  wrapScrollTables();
  wireCopyButtons();
  installBadgeMutObs();
  wireHoverLinking();
  // Before the first paint settles, so a later version opens compact.
  initUnchangedSections();
  wireEarlier();
  labelImages();
  wireViewerKeys();

  window.addEventListener('resize', scheduleBadgeRefresh);
  window.addEventListener('resize', scheduleScrollLockRecheck);
  window.addEventListener('scroll', scheduleBadgeRefresh);

  ensureContentScrollContractStyle();
  await mountContentDiagrams();
  ensureGeometryFixStyle();
  ensureLegacyChromeSuppressStyle();
  ensureGotoHighlightStyle();
  wireDiagramClusterJumps();
  fixViewportScrollLock();

  // Announce readiness once the DOM (and any deferred diagram scripts)
  // have had a frame to settle.
  requestAnimationFrame(() => requestAnimationFrame(() => {
    postToParent({ type: 'annotate:ready', version: META.version });
    renderBadges();
  }));
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

})();
