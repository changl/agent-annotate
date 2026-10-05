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
// v2.19: true when the shell said the server supports review rounds; strip
// verdicts are then posted with defer_push (parked until "Finish review").
let latestRounds = false;
// D2: true when the shell said the server offers the "changes" verdict, so
// the strip's third button is "Request changes" instead of "Comment". Absent
// from an old shell's message → false → the pre-D2 strip, unchanged.
let latestChanges = false;
// D3: true when the shell said the server understands the `select` verdict,
// which a click on a custom option id posts. Absent from an old shell's
// message → false → those clicks post `comment`, exactly as before D3.
let latestSelect = false;
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
function displayAnchorEl(anchorId) {
  const el = findAnchorEl(anchorId);
  if (el && el.dataset && el.dataset.annotateReplaced) {
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
  const entries = (latestPins[anchorId] || []).slice().sort((a, b) => a.n - b.n);
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

function wireHoverLinking() {
  ensureHoverStyle();
  document.addEventListener('mouseover', (e) => {
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
  document.addEventListener('mouseout', (e) => {
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

// ── Inline body decision strips ──────────────────────────────────────
// The rail card (shell.js renderDecisionBlock) is the drawer-side surface
// for a decision_request. This is the same affordance rendered AT the
// anchored element, inside this document, so a reviewer scanning the body
// never has to open the drawer to answer. Rebuilt only when the shell sends
// a fresh 'annotate:comment-counts' message (see wireBridge) — NOT on every
// resize/scroll-driven badge refresh, so DOM insertion here can never
// feed back into the MutationObserver above and loop.
const DECISION_VERDICT_LABEL = { accept: 'Accepted', reject: 'Rejected', changes: 'Changes requested', comment: 'Answered in words', select: 'Selected' };
// Checkmark-prefixed variant for the plain-text "currently X" changing-note
// (the resolved chip itself is color-coded so it doesn't need one; the note
// has no color coding, so it gets the same symbol shell.js's rail card and
// sync_server.py's revision reply text use, for a consistent read).
const DECISION_VERDICT_TEXT = { accept: '✓ Accepted', reject: '✗ Rejected', changes: '↻ Changes requested', comment: 'Answered in words', select: '☑ Selected' };
const DECISION_OPTIONS_ALL = ['accept', 'reject', 'comment', 'changes'];
const DECISION_OPTIONS_DEFAULT = ['accept', 'reject', 'comment'];
const DECISION_OPTIONS_DEFAULT_CHANGES = ['accept', 'reject', 'changes'];
// D2: mirrors shell.js textVerdictId()/canonicalOptionId(). "comment" and
// "changes" are one slot; which spelling this page uses follows the server.
function stripTextVerdictId() {
  return latestChanges ? 'changes' : 'comment';
}
function stripCanonicalOptionId(id) {
  return (id === 'comment' || id === 'changes') ? stripTextVerdictId() : id;
}
// Comment ids currently mid-flight (POST sent, no response yet): rendered
// disabled with "Sending…" even across a rebuild triggered by an unrelated
// counts message arriving before the response does.
const pendingDecisionIds = new Set();
// In-progress "Comment" text/open-state per comment id, so an 8s-poll-driven
// rebuild never silently discards what the reviewer is mid-typing.
const stripDraftText = {};
const stripFormOpen = {};
// T-verdict-reversal: comment ids currently showing the change-verdict form
// on the BODY strip instead of their resolved chip. Mirrors shell.js's
// decisionChanging map so a rebuild triggered by an unrelated
// annotate:comment-counts message doesn't snap a mid-correction strip back
// to the chip.
const stripChanging = {};
// v2.19 per-item UI state that must survive a rebuild: optional-note form
// open, and the note draft text.
const stripNoteOpen = {};
const stripNoteText = {};
// D3: the standing Comment form's open state and draft, kept across a
// rebuild exactly like the note above.
const stripSayOpen = {};
const stripSayText = {};
// Card layout: which excerpts are expanded past their 4-line clamp, whether
// a card's "Evidence (n)" list is open, and which evidence previews are open.
// Keyed per card so an 8s-poll rebuild never snaps them shut.
const stripExcerptOpen = {};
const stripEvidenceOpen = {};
const stripEvidenceItemOpen = {};
const DECISION_BTN_TEXT = { accept: '✓ Accept', reject: '✗ Reject', comment: '💬 Comment', changes: '↻ Request changes' };
// The same options without their glyphs, for the "Recommended: …" sentence.
const DECISION_PLAIN_LABEL = { accept: 'Accept', reject: 'Reject', comment: 'Comment', changes: 'Request changes' };
const DECISION_BTN_CLASS = { accept: 'annotate-decision-accept', reject: 'annotate-decision-reject', comment: 'annotate-decision-comment', changes: 'annotate-decision-changes' };
const DECISION_IMPACTS = ['low', 'medium', 'high'];

// Same normalization as shell.js decisionOptions(): legacy string options
// keep their exact pre-2.19 labels; object options bring label/consequence/
// style; an object option with an id outside accept/reject/comment is a
// "custom" choice posted as a comment verdict naming the selection.
function stripDecisionOptions(dr) {
  const fallback = latestChanges ? DECISION_OPTIONS_DEFAULT_CHANGES : DECISION_OPTIONS_DEFAULT;
  const raw = (Array.isArray(dr.options) && dr.options.length) ? dr.options : fallback;
  const cons = (dr.consequences && typeof dr.consequences === 'object') ? dr.consequences : {};
  const out = [];
  for (const o of raw) {
    if (typeof o === 'string') {
      if (DECISION_OPTIONS_ALL.indexOf(o) === -1) {
        out.push({id:o, label:o, plain:o, consequence:cons[o] || '', style:null, custom:true});
        continue;
      }
      const sid = stripCanonicalOptionId(o);
      const scq = typeof cons[o] === 'string' ? cons[o] : (typeof cons[sid] === 'string' ? cons[sid] : '');
      out.push({ id: sid, label: DECISION_BTN_TEXT[sid], plain: DECISION_PLAIN_LABEL[sid], consequence: scq, style: null, custom: false });
    } else if (o && typeof o === 'object' && typeof o.id === 'string' && o.id) {
      const oid = stripCanonicalOptionId(o.id);
      const known = DECISION_OPTIONS_ALL.indexOf(oid) !== -1;
      const label = typeof o.label === 'string' && o.label.trim() ? o.label.trim() : null;
      out.push({
        id: known ? oid : o.id,
        label: label || (known ? DECISION_BTN_TEXT[oid] : o.id),
        plain: label || (known ? DECISION_PLAIN_LABEL[oid] : o.id),
        consequence: typeof o.consequence === 'string' ? o.consequence : (typeof cons[o.id] === 'string' ? cons[o.id] : ''),
        style: (o.style === 'primary' || o.style === 'danger' || o.style === 'default') ? o.style : null,
        custom: !known,
      });
    }
  }
  return out;
}

function ensureStripStyle() {
  if (document.getElementById('annotate-strip-style')) return;
  const style = document.createElement('style');
  style.id = 'annotate-strip-style';
  style.textContent = `
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
      font-size: 12px !important; font-weight: 600 !important; color: var(--link) !important;
      margin: 0 0 6px !important; line-height: 1.4 !important; white-space: normal !important;
    }
    .annotate-decision-num { display: inline-block !important; margin-right: 6px !important; font-weight: 800 !important; color: var(--link) !important; }
    .annotate-decision-resolved .annotate-decision-prompt { margin-bottom: 5px !important; }
    .annotate-decision-text {
      font-size: 11.5px !important; color: var(--color-base-content) !important; line-height: 1.5 !important;
      margin: -2px 0 6px !important; white-space: pre-wrap !important; word-break: break-word !important;
    }
    /* Options are rows (radio-tile layout): label, its consequence under it,
       a Recommended badge, nothing preselected. One click still answers. */
    .annotate-decision-btns {
      display: flex !important; flex-direction: column !important; align-items: stretch !important;
      gap: 6px !important; min-width: 0 !important;
    }
    .annotate-decision-btn {
      font-size: 11px !important; font-weight: 700 !important; padding: 5px 11px !important;
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
    .annotate-decision-comment, .annotate-decision-submit { background: var(--color-primary) !important; }
    /* D2 "Request changes": amber, deliberately not Reject's red. */
    .annotate-decision-changes { background: var(--warn-text) !important; }
    /* display is intentionally NOT set here: it's driven entirely by the
       inline style.setProperty(..., 'important') toggle in JS (open/closed),
       which an author-stylesheet !important rule here would permanently
       defeat. */
    .annotate-decision-form { margin-top: 6px !important; flex-direction: column !important; gap: 5px !important; }
    .annotate-decision-ta {
      width: 100% !important; min-height: 40px !important; padding: 5px 7px !important;
      border: 1px solid var(--line) !important; border-radius: 5px !important; font-size: 11px !important;
      font-family:"Inter", sans-serif !important; resize: vertical !important; color: var(--color-base-content) !important;
      background: var(--color-base-100) !important; box-sizing: border-box !important; line-height: 1.4 !important;
    }
    .annotate-decision-ta:focus { outline: none !important; border-color: var(--link) !important; }
    .annotate-decision-feedback {
      margin-top: 5px !important; font-size: 10.5px !important; font-weight: 600 !important;
      color: var(--link) !important; min-height: 12px !important;
    }
    .annotate-decision-feedback.is-error { color: var(--color-error) !important; }
    .annotate-decision-feedback:empty { min-height: 0 !important; margin-top: 0 !important; }
    .annotate-decision-delivery {
      font-size: 11px !important; color: var(--muted) !important; margin-left: 8px !important;
    }
    .annotate-verdict-chip {
      display: inline-block !important; font-size: 10.5px !important; font-weight: 700 !important;
      padding: 4px 10px !important; border-radius: 10px !important;
    }
    .annotate-verdict-chip.verdict-accept { background: var(--success-soft) !important; color: var(--ok-text) !important; }
    .annotate-verdict-chip.verdict-reject { background: var(--error-soft) !important; color: var(--color-error) !important; }
    .annotate-verdict-chip.verdict-comment { background: var(--primary-soft) !important; color: var(--link) !important; }
    .annotate-verdict-chip.verdict-changes { background: var(--warning-soft) !important; color: var(--warn-text) !important; }
    .annotate-decision-change, .annotate-decision-cancel {
      background: none !important; color: var(--link) !important; font-weight: 600 !important;
      padding: 4px 6px !important; margin-left: 6px !important; text-decoration: none !important;
    }
    .annotate-decision-change:hover, .annotate-decision-cancel:hover { filter: none !important; text-decoration: underline !important; }
    .annotate-decision-changing-note {
      display: flex !important; align-items: center !important; justify-content: space-between !important;
      gap: 8px !important; font-size: 11px !important; font-weight: 600 !important; color: var(--link) !important;
      background: var(--primary-soft) !important; border-radius: 6px !important; padding: 5px 8px !important;
      margin-bottom: 6px !important;
    }
    .annotate-strip-anchor-label {
      font-size: 10px !important; font-weight: 700 !important; color: var(--muted) !important;
      text-transform: uppercase !important; letter-spacing: .03em !important;
      margin: 0 0 5px !important; white-space: normal !important;
    }
    /* v2.19 fields. Context is always shown in full: it is what the
       reviewer needs to decide, so it never sits behind a disclosure. */
    .annotate-decision-context {
      font-size: 11px !important; color: var(--muted) !important; line-height: 1.5 !important;
      margin: -2px 0 6px !important; white-space: pre-wrap !important; word-break: break-word !important;
      font-weight: 400 !important;
    }
    .annotate-decision-reco-line {
      font-size: 11px !important; color: var(--ok-text) !important; font-weight: 600 !important;
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
      font-size: 10.5px !important; font-weight: 700 !important; color: var(--muted) !important;
      text-transform: uppercase !important; letter-spacing: .03em !important; margin: 0 0 2px !important;
    }
    .annotate-excerpt-text {
      margin: 0 !important; padding: 0 !important; border: none !important; quotes: none !important;
      font-size: 11px !important; font-style: normal !important; font-weight: 400 !important;
      color: var(--color-base-content) !important; line-height: 1.5 !important; white-space: pre-line !important;
      word-break: break-word !important; overflow-wrap: anywhere !important; background: none !important;
      display: -webkit-box !important; -webkit-box-orient: vertical !important; -webkit-line-clamp: 4 !important;
      overflow: hidden !important;
    }
    .annotate-excerpt.is-open .annotate-excerpt-text { display: block !important; -webkit-line-clamp: unset !important; overflow: visible !important; }
    .annotate-excerpt-more {
      font-size: 10.5px !important; font-weight: 600 !important; color: var(--link) !important;
      background: none !important; border: none !important; padding: 2px 0 !important; margin: 2px 0 0 !important;
      cursor: pointer !important; font-family:"Inter", sans-serif !important;
    }
    .annotate-excerpt-more[hidden] { display: none !important; }
    .annotate-card-replaced { display: none !important; }
    .annotate-decision-meta { display: flex !important; gap: 5px !important; flex-wrap: wrap !important; margin: 0 0 6px !important; }
    .annotate-decision-chip {
      font-size: 9px !important; font-weight: 700 !important; padding: 2px 7px !important; border-radius: 8px !important;
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
      font-size: 10.5px !important; font-weight: 400 !important; color: var(--muted) !important; line-height: 1.4 !important;
      white-space: pre-wrap !important; word-break: break-word !important;
    }
    .annotate-decision-rec {
      font-size: 9.5px !important; font-weight: 800 !important; letter-spacing: .05em !important;
      text-transform: uppercase !important; background: var(--success-soft) !important; color: var(--ok-text) !important;
      border: 1px solid var(--line) !important; padding: 1px 6px !important; border-radius: 999px !important;
    }
    .annotate-decision-say-row {
      display: flex !important; align-items: center !important; gap: 8px !important;
      flex-wrap: wrap !important; margin-top: 8px !important;
    }
    .annotate-decision-say {
      font-size: 11.5px !important; font-weight: 700 !important; padding: 5px 11px !important;
      border-radius: 6px !important; border: 1px solid var(--line) !important; cursor: pointer !important;
      background: var(--color-base-100) !important; color: var(--link) !important; font-family:"Inter", sans-serif !important;
      max-width: 100% !important; text-align: left !important; line-height: 1.35 !important;
      white-space: normal !important; overflow-wrap: anywhere !important;
    }
    .annotate-decision-say:hover { background: var(--primary-soft) !important; filter: none !important; }
    .annotate-decision-say-hint { font-size: 10.5px !important; color: var(--muted) !important; }
    .annotate-decision-commented { margin: 0 0 6px !important; }
    .annotate-decision-commented-txt { font-size: 10.5px !important; color: var(--muted) !important; margin-left: 6px !important; }
    .annotate-decision-custom { background: var(--muted) !important; }
    .annotate-decision-custom.annotate-style-primary { background: var(--color-primary) !important; }
    .annotate-decision-custom.annotate-style-danger { background: var(--color-error) !important; }
    /* Evidence: a collapsed "Evidence (n)" disclosure; each item previews its
       target inside the card, and "Go to" jumps there leaving "Back to #N". */
    .annotate-decision-evidence { display: block !important; margin: 8px 0 0 !important; font-size: 10.5px !important; color: var(--muted) !important; }
    .annotate-decision-evidence-toggle, .annotate-decision-evidence-link {
      font-size: 10.5px !important; font-weight: 700 !important; color: var(--link) !important;
      background: none !important; border: none !important; padding: 2px 0 !important;
      cursor: pointer !important; font-family:"Inter", sans-serif !important; display: inline-flex !important;
      align-items: center !important; gap: 4px !important; text-align: left !important;
    }
    .annotate-decision-evidence-link { font-weight: 600 !important; text-decoration: none !important; }
    .annotate-decision-evidence-label { text-decoration: underline dotted !important; }
    .annotate-decision-evidence-toggle::before, .annotate-decision-evidence-link::before {
      content: '\\25B8'; font-size: 9px; transition: transform .12s; text-decoration: none;
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
      font-size: 10.5px !important; font-weight: 700 !important; color:var(--color-primary-content) !important; background: var(--color-primary) !important;
      border: none !important; border-radius: 5px !important; padding: 3px 10px !important;
      cursor: pointer !important; font-family:"Inter", sans-serif !important;
    }
    .annotate-decision-evidence-goto:disabled { opacity: .5 !important; cursor: not-allowed !important; }
    /* "Back to #N": left on the target by an evidence jump, returns to the card. */
    .annotate-back-row { display: block !important; list-style: none !important; margin: 4px 0 !important; padding: 0 !important; text-align: left !important; }
    .annotate-back-tr > td { padding: 3px 0 !important; border: none !important; background: transparent !important; }
    .annotate-back-pill {
      font: 700 11.5px "Inter", sans-serif !important;
      color:var(--color-primary-content) !important; background: var(--color-primary) !important; border: none !important; border-radius: 999px !important;
      padding: 5px 12px !important; cursor: pointer !important; box-shadow: 0 2px 8px color-mix(in oklab,var(--color-primary) 30%,transparent) !important;
      line-height: 1.3 !important; white-space: nowrap !important;
    }
    .annotate-back-pill:hover { background: var(--color-primary) !important; }
    .annotate-back-abs { position: absolute !important; pointer-events: auto !important; z-index: 16 !important; }
    .annotate-decision-note-toggle {
      font-size: 10.5px !important; color: var(--muted) !important; background: none !important;
      border: none !important; padding: 2px 0 !important; cursor: pointer !important;
      font-family:"Inter", sans-serif !important; margin-top: 6px !important; display: block !important;
    }
    .annotate-decision-note-toggle:hover { color: var(--link) !important; filter: none !important; }
    .annotate-decision-note-form { margin-top: 4px !important; }
    .annotate-decision-note-form[hidden] { display: none !important; }
    .annotate-decision-pending {
      display: inline-block !important; font-size: 9.5px !important; font-weight: 700 !important;
      padding: 2px 8px !important; border-radius: 8px !important; background: var(--warning-soft) !important;
      color: var(--warn-text) !important; border: 1px dashed var(--color-warning) !important; text-transform: uppercase !important;
      letter-spacing: .04em !important; margin-left: 8px !important; vertical-align: middle !important;
    }
    .annotate-decision-sendnow {
      background: none !important; color: var(--link) !important; font-weight: 600 !important;
      padding: 4px 6px !important; margin-left: 4px !important; font-size: 10.5px !important;
    }
    .annotate-decision-sendnow:hover { filter: none !important; text-decoration: underline !important; }
    @media (max-width: 768px), (max-height: 480px) {
      .annotate-decision-evidence-toggle, .annotate-decision-evidence-link, .annotate-decision-note-toggle,
      .annotate-excerpt-more, .annotate-decision-sendnow { min-height: 44px !important; padding: 10px 4px !important; touch-action: manipulation !important; }
      .annotate-decision-evidence-goto, .annotate-back-pill { min-height: 44px !important; padding: 10px 16px !important; touch-action: manipulation !important; }
      /* The toggle's own 44px target already spaces it from the options. */
      .annotate-decision-evidence { margin-top: 0 !important; }
      /* Thumb-sized buttons, buttons free to wrap to their own row, and a
         16px textarea so iOS doesn't zoom the page in on focus. */
      .annotate-decision-btn, .annotate-decision-say {
        min-height: 44px !important; padding: 10px 16px !important; font-size: 13px !important;
        flex: 1 1 auto !important; touch-action: manipulation !important;
      }
      .annotate-decision-ta { font-size: 16px !important; min-height: 48px !important; }
      .annotate-decision-change, .annotate-decision-cancel { min-height: 44px !important; padding: 10px 12px !important; touch-action: manipulation !important; }
    }
    /* ── Feedback prototype (X1/E4): the strip follows the shell
       using stock daisyUI light/dark tokens. C2 keeps the question bold. */
    .annotate-decision-strip {
      background: var(--color-base-100) !important; border: 1px solid var(--line) !important;
      border-radius: .5rem !important; padding: 10px 12px !important;
      box-shadow: 0 1px 2px color-mix(in oklab,var(--color-neutral) 6%,transparent) !important; color: var(--color-base-content) !important;
    }
    .annotate-decision-item + .annotate-decision-item { border-top-color: var(--line) !important; }
    .annotate-decision-prompt { color: var(--color-base-content) !important; font-weight: 700 !important; font-size: 11px !important; }
    .annotate-decision-num {
      color: var(--color-base-content) !important; background: var(--color-base-300) !important; border-radius: 999px !important;
      padding: 0 6px !important; font-size: 9.5px !important; font-weight: 700 !important;
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
      background: var(--color-base-100) !important; font-size: 11px !important; margin-top: 8px !important;
      min-height: 2.25rem !important; padding: 6px 8px !important;
    }
    .annotate-decision-ta:focus { outline: 2px solid color-mix(in oklab,var(--color-base-content) 50%,transparent) !important; outline-offset: 2px !important; }
    .annotate-decision-cmt-hint { font-size: 11px !important; color: color-mix(in oklab,var(--color-base-content) 75%,transparent) !important; margin-top: 4px !important; }
    /* Secondary text derives from the active stock foreground token. */
    .annotate-decision-consequence, .annotate-excerpt-src { color: color-mix(in oklab,var(--color-base-content) 75%,transparent) !important; }
    .annotate-decision-cmt-hint:empty { display: none !important; }
    .annotate-decision-feedback { color: color-mix(in oklab,var(--color-base-content) 70%,transparent) !important; }
    .annotate-verdict-chip { border-radius: .5rem !important; font-weight: 700 !important; }
    .annotate-verdict-chip.verdict-accept { background: color-mix(in oklab,var(--color-success) 15%,transparent) !important; color: var(--ok-text) !important; }
    .annotate-verdict-chip.verdict-reject { background: color-mix(in oklab,var(--color-error) 15%,transparent) !important; color: var(--err-text) !important; }
    .annotate-verdict-chip.verdict-changes { background: color-mix(in oklab,var(--color-warning) 20%,transparent) !important; color: var(--warn-text) !important; }
    .annotate-verdict-chip.verdict-comment, .annotate-verdict-chip.verdict-select { background: color-mix(in oklab,var(--color-info) 15%,transparent) !important; color: var(--info-text) !important; }
    .annotate-decision-change {
      display: inline-flex !important; align-items: center !important; justify-content: center !important;
      width: 26px !important; height: 26px !important; padding: 0 !important; margin-left: 6px !important;
      background: transparent !important; color: color-mix(in oklab,var(--color-base-content) 70%,transparent) !important; border-radius: .25rem !important;
      vertical-align: middle !important;
    }
    .annotate-decision-change:hover { background: var(--color-base-300) !important; text-decoration: none !important; }
    .annotate-decision-changing-note { background: var(--color-base-200) !important; color: var(--color-base-content) !important; border: 1px solid var(--line) !important; }
    .annotate-decision-cancel { color: var(--color-base-content) !important; }
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

// ── Body-inline decision API calls ───────────────────────────────────
// The server resolves author identity from trusted OAuth/proxy headers, not
// from the request body (see sync_server.py _identity()) — so unlike the
// rail card's shell.js equivalents, these never need to pass author fields.
async function stripApiDecision(id, verdict, text) {
  try {
    const r = await fetch('./api/comments/' + encodeURIComponent(id) + '/decision', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // v2.19 round mode: park the verdict instead of pushing per click.
      body: JSON.stringify({ verdict, text: text || undefined, ...(latestRounds ? { defer_push: true } : {}) }),
    });
    if (r.status === 404 || r.status === 405) return { fallback: true };
    if (r.ok) return await r.json();
  } catch (e) { console.warn('[adapter] decision POST failed', e); }
  return null;
}
async function stripApiReply(id, text) {
  try {
    const r = await fetch('./api/comments/' + encodeURIComponent(id) + '/reply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (r.ok) return await r.json();
  } catch (e) { console.warn('[adapter] fallback reply failed', e); }
  return null;
}
async function stripApiPutComment(id, patch) {
  try {
    const r = await fetch('./api/comments/' + encodeURIComponent(id), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
    if (r.ok) return await r.json();
  } catch (e) { console.warn('[adapter] fallback PUT failed', e); }
  return null;
}
async function stripApiPushSingle(id) {
  try {
    const r = await fetch('./api/comments/' + encodeURIComponent(id) + '/push', { method: 'POST' });
    if (r.ok) return await r.json();
  } catch (e) { console.warn('[adapter] fallback push failed', e); }
  return null;
}
// OLD-SERVER FALLBACK (server predates /decision, 404/405): same composite
// the rail card falls back to — reply + status PUT + push. Mirrors
// shell.js's apiDecisionFallback exactly so both surfaces degrade the same
// way against an un-upgraded server.
async function stripApiDecisionFallback(id, verdict, text) {
  const verdictText = { accept: '✓ Accepted', reject: '✗ Rejected' };
  const isText = verdict === 'comment' || verdict === 'changes';
  let replyText = verdict === 'changes' ? '↻ Changes requested: ' + text
    : verdict === 'comment' ? '💬 Answer in words: ' + text : verdictText[verdict];
  if (!isText && text) replyText += '\n\n' + text;
  const replied = await stripApiReply(id, replyText);
  if (!replied) return null;
  const statusMap = { accept: 'user_confirmed', reject: 'open', comment: 'open', changes: 'open' };
  await stripApiPutComment(id, { status: statusMap[verdict] });
  return await stripApiPushSingle(id);
}

function setStripItemDisabled(itemEl, disabled) {
  itemEl.querySelectorAll('button').forEach(b => { b.disabled = disabled; });
}

// v2.19: "Pending — not sent" chip + "Send now" for a verdict parked in the
// current review round. Send now = the existing single-card push route; the
// server clears round_pending and the shell refresh removes the chip.
// Feedback prototype (A2/B2): no "Pending — not sent" chip and no "Send
// now" — a pending verdict waits for the one Send in the shell header.
function appendPendingControls(itemEl, id) {
  return;
  // eslint-disable-next-line no-unreachable
  const pend = document.createElement('span');
  pend.className = 'annotate-decision-pending';
  pend.textContent = 'Pending — not sent';
  pend.title = 'Recorded but not sent to the agent yet. Finish the review in the feedback rail to send every pending verdict at once.';
  itemEl.appendChild(pend);
  const send = makeStripBtn('Send now', 'annotate-decision-sendnow');
  send.title = 'Send just this verdict now, outside the round';
  send.addEventListener('click', async () => {
    send.disabled = true;
    send.textContent = 'Sending…';
    const j = await stripApiPushSingle(id);
    if (!j) { send.disabled = false; send.textContent = 'Send now'; return; }
    pend.remove();
    send.remove();
    postToParent({ type: 'annotate:decision-posted', commentId: id });
  });
  itemEl.appendChild(send);
}

function swapStripItemToResolved(itemEl, verdict, deliveryMsg, pendingId) {
  // The question stays on screen above its verdict, as on a rebuilt strip.
  const promptEl = itemEl.querySelector(':scope > .annotate-decision-prompt');
  itemEl.innerHTML = '';
  if (promptEl) itemEl.appendChild(promptEl);
  itemEl.classList.add('annotate-decision-resolved');
  const chip = document.createElement('span');
  chip.className = 'annotate-verdict-chip verdict-' + verdict;
  chip.textContent = DECISION_VERDICT_LABEL[verdict] || verdict;
  itemEl.appendChild(chip);
  if (pendingId) appendPendingControls(itemEl, pendingId);
  if (deliveryMsg) {
    const note = document.createElement('span');
    note.className = 'annotate-decision-delivery';
    note.textContent = deliveryMsg;
    itemEl.appendChild(note);
    setTimeout(() => { if (note.isConnected) note.remove(); }, 4000);
  }
}

async function submitStripDecision(id, verdict, text, itemEl) {
  pendingDecisionIds.add(id);
  setStripItemDisabled(itemEl, true);
  const feedback = itemEl.querySelector('.annotate-decision-feedback');
  if (feedback) { feedback.classList.remove('is-error'); feedback.textContent = 'Sending…'; }

  let result = await stripApiDecision(id, verdict, text);
  if (!result || result.fallback) result = await stripApiDecisionFallback(id, verdict, text);
  pendingDecisionIds.delete(id);

  if (!result) {
    setStripItemDisabled(itemEl, false);
    if (feedback) { feedback.classList.add('is-error'); feedback.textContent = 'Failed to send — try again.'; }
    return;
  }

  delete stripDraftText[id];
  delete stripFormOpen[id];
  delete stripChanging[id]; // resolved again (first vote or a correction) — drop back to the chip
  delete stripNoteOpen[id];
  delete stripNoteText[id];
  const deferred = result.delivery === 'deferred' || !!(result.decision && result.decision.round_pending);
  const delivered = result.delivery === 'active_monitor';
  // Optimistic in-place swap (don't wait for the counts message this
  // triggers below): the strip must not sit there looking answerable for
  // however long the shell's refreshStore() round-trip takes.
  // Delivery note rides on the resolved strip briefly since the swap
  // destroys the feedback node.
  if (deferred) {
    swapStripItemToResolved(itemEl, verdict, null, id);
  } else {
    swapStripItemToResolved(itemEl, verdict, delivered ? '✅ Sent to active session' : '⏳ Queued — no monitor armed');
  }
  postToParent({ type: 'annotate:decision-posted', commentId: id });
}

// Lucide "pencil" (ISC License, (c) Lucide Icons and Contributors).
function pencilSvg() {
  const NS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', '14');
  svg.setAttribute('height', '14');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '2');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  ['M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z', 'm15 5 4 4'].forEach(d => {
    const p = document.createElementNS(NS, 'path');
    p.setAttribute('d', d);
    svg.appendChild(p);
  });
  return svg;
}

function makeStripBtn(label, cls) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'annotate-decision-btn ' + cls;
  b.textContent = label;
  return b;
}

// One option row: its label, a Recommended badge when the agent recommends
// it, and its consequence on the line under it — the whole row is the button,
// so a click anywhere on it answers exactly as the old button did.
function makeOptionBtn(o, cls, recommended) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'annotate-decision-btn annotate-opt-row ' + cls;
  const head = document.createElement('span');
  head.className = 'annotate-opt-head';
  const label = document.createElement('span');
  label.className = 'annotate-opt-label';
  label.textContent = o.label; // textContent only — agent data
  head.appendChild(label);
  if (recommended) {
    b.classList.add('is-recommended');
    b.title = 'Recommended by the agent';
    const badge = document.createElement('span');
    badge.className = 'annotate-decision-rec';
    badge.textContent = 'Recommended';
    head.appendChild(badge);
  }
  b.appendChild(head);
  if (o.consequence) {
    const c = document.createElement('span');
    c.className = 'annotate-decision-consequence';
    c.textContent = o.consequence; // textContent only — agent data
    b.appendChild(c);
  }
  return b;
}

function buildPromptEl(entry, dr) {
  const el = document.createElement('div');
  el.className = 'annotate-decision-prompt';
  if (entry.n) {
    const num = document.createElement('span');
    num.className = 'annotate-decision-num';
    num.textContent = '#' + entry.n;
    el.appendChild(num);
  }
  // textContent only — decision_request.prompt is store/agent-controlled
  // data and must never be interpreted as markup.
  el.appendChild(document.createTextNode((dr && dr.prompt) || ''));
  return el;
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
const EXCERPT_SKIP_SEL = '[data-annotate-strip], [data-annotate-back], .bpin, .bpin-inline, #badge-layer, #annotate-strip-layer, .annotate-card-state, .annotate-unchanged-bar, script, style, template, noscript';
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

function domId(prefix, key) {
  let h = 5381;
  const s = String(key);
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) >>> 0;
  return prefix + '-' + h.toString(36);
}

// A quoted excerpt clamped to four lines, with a "Show more" disclosure that
// appears only when the text is actually cut off.
function buildExcerptEl(key, text, source) {
  const box = document.createElement('figure');
  box.className = 'annotate-excerpt' + (stripExcerptOpen[key] ? ' is-open' : '');
  if (source) {
    const cap = document.createElement('figcaption');
    cap.className = 'annotate-excerpt-src';
    cap.textContent = source;
    box.appendChild(cap);
  }
  const quote = document.createElement('blockquote');
  quote.className = 'annotate-excerpt-text';
  quote.id = domId('annotate-x', key);
  quote.textContent = text;
  box.appendChild(quote);
  const more = document.createElement('button');
  more.type = 'button';
  more.className = 'annotate-excerpt-more';
  more.setAttribute('aria-controls', quote.id);
  more.hidden = true;
  more.addEventListener('click', () => {
    stripExcerptOpen[key] = !stripExcerptOpen[key];
    box.classList.toggle('is-open', !!stripExcerptOpen[key]);
    syncExcerptClamp(box);
  });
  box.appendChild(more);
  return box;
}

function syncExcerptClamp(box) {
  const t = box && box.querySelector('.annotate-excerpt-text');
  const more = box && box.querySelector('.annotate-excerpt-more');
  if (!t || !more) return;
  const open = box.classList.contains('is-open');
  more.textContent = open ? 'Show less' : 'Show more';
  more.setAttribute('aria-expanded', open ? 'true' : 'false');
  if (open) { more.hidden = false; return; }
  const text = t.textContent || '';
  // Unrendered (inside a collapsed container): judge by length instead.
  more.hidden = !(t.clientHeight > 0
    ? t.scrollHeight > t.clientHeight + 1
    : (text.length > 220 || (text.match(/\n/g) || []).length >= 4));
}
function syncAllExcerptClamps(root) {
  (root || document).querySelectorAll('.annotate-excerpt').forEach(syncExcerptClamp);
}

// "Evidence (n)": collapsed by default. Each item previews its target in
// place; "Go to" scrolls there and leaves "Back to #N" on the target.
function buildEvidenceEl(entry, ev) {
  const id = entry.id;
  const wrap = document.createElement('div');
  wrap.className = 'annotate-decision-evidence';
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'annotate-decision-evidence-toggle';
  toggle.textContent = 'Evidence (' + ev.length + ')';
  const list = document.createElement('div');
  list.className = 'annotate-decision-evidence-list';
  list.id = domId('annotate-evl', id);
  toggle.setAttribute('aria-controls', list.id);
  const syncList = () => {
    const open = !!stripEvidenceOpen[id];
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    list.hidden = !open;
  };
  toggle.addEventListener('click', () => {
    stripEvidenceOpen[id] = !stripEvidenceOpen[id];
    syncList();
    if (stripEvidenceOpen[id]) syncAllExcerptClamps(list);
  });
  ev.forEach((e, i) => {
    const key = id + '\n' + e.anchor + '\n' + i;
    const row = document.createElement('div');
    row.className = 'annotate-decision-evidence-item';
    const link = document.createElement('button');
    link.type = 'button';
    link.className = 'annotate-decision-evidence-link';
    const linkLabel = document.createElement('span');
    linkLabel.className = 'annotate-decision-evidence-label';
    linkLabel.textContent = e.label || e.anchor;
    link.appendChild(linkLabel);
    link.title = 'Preview ' + e.anchor;
    const preview = document.createElement('div');
    preview.className = 'annotate-decision-evidence-preview';
    preview.id = domId('annotate-evp', key);
    link.setAttribute('aria-controls', preview.id);
    const target = findAnchorEl(e.anchor);
    const text = target ? excerptText(target) : '';
    if (text) {
      preview.appendChild(buildExcerptEl('ev\n' + key, text, excerptSource(e.anchor)));
    } else {
      const miss = document.createElement('div');
      miss.className = 'annotate-decision-evidence-missing';
      miss.textContent = target ? 'Nothing to quote here.' : 'Not on this version of the page.';
      preview.appendChild(miss);
    }
    const go = document.createElement('button');
    go.type = 'button';
    go.className = 'annotate-decision-evidence-goto';
    go.textContent = 'Go to ↓';
    go.title = 'Scroll to ' + e.anchor + '; a "Back" marker there returns here';
    go.disabled = !target;
    go.addEventListener('click', () => scrollToAnchor(e.anchor, null, { commentId: id, n: entry.n || 0, from: 'strip' }));
    preview.appendChild(go);
    const syncItem = () => {
      const open = !!stripEvidenceItemOpen[key];
      link.setAttribute('aria-expanded', open ? 'true' : 'false');
      preview.hidden = !open;
    };
    link.addEventListener('click', () => {
      stripEvidenceItemOpen[key] = !stripEvidenceItemOpen[key];
      syncItem();
      if (stripEvidenceItemOpen[key]) syncAllExcerptClamps(preview);
    });
    syncItem();
    row.appendChild(link);
    row.appendChild(preview);
    list.appendChild(row);
  });
  syncList();
  wrap.appendChild(toggle);
  wrap.appendChild(list);
  return wrap;
}

// Builds ONE decision item (either the live accept/reject/comment controls,
// or — once resolved — a compact verdict chip) for a single comment entry.
function buildDecisionItemEl(entry) {
  const id = entry.id;
  const item = document.createElement('div');
  item.className = 'annotate-decision-item';
  item.dataset.stripItem = id;

  if (entry.decisionVerdict && !stripChanging[id]) {
    item.classList.add('annotate-decision-resolved');
    // The strip replaces the generated card in the body, so the question
    // itself stays readable above its verdict.
    if (entry.decisionRequest) item.appendChild(buildPromptEl(entry, entry.decisionRequest));
    const chip = document.createElement('span');
    chip.className = 'annotate-verdict-chip verdict-' + entry.decisionVerdict;
    // C1: the answer itself ("Tonight at 11pm"), not just "Selected".
    chip.textContent = entry.answerText || DECISION_VERDICT_LABEL[entry.decisionVerdict] || entry.decisionVerdict;
    item.appendChild(chip);
    // T-verdict-reversal: only offer "Change" when the shell still sent the
    // original decisionRequest alongside decisionVerdict (new shell always
    // does once resolved — see shell.js sendCommentCountsToFrame). An old
    // shell that predates this fix never will, so this just quietly shows
    // the plain chip against it instead of erroring.
    if (entry.decisionRequest) {
      // D1 (Chang): "the edit should be a pencil icon".
      const changeBtn = makeStripBtn('', 'annotate-decision-change');
      changeBtn.appendChild(pencilSvg());
      changeBtn.setAttribute('aria-label', 'Change answer');
      changeBtn.title = 'Change';
      changeBtn.addEventListener('click', () => {
        stripChanging[id] = true;
        renderDecisionStrips();
      });
      item.appendChild(changeBtn);
    }
    if (entry.roundPending) appendPendingControls(item, id);
    return item;
  }

  // Card layout, the same on the rail: number and prompt, the card's own
  // text when it says more than the prompt, chips, context in full,
  // "Recommended: …", a quoted excerpt of the first evidence target, the
  // options as rows, then a collapsed "Evidence (n)".
  const dr = entry.decisionRequest || {};
  item.appendChild(buildPromptEl(entry, dr));
  const cardText = typeof entry.text === 'string' ? entry.text.trim() : '';
  if (cardText && normText(cardText) !== normText(dr.prompt)) {
    const textEl = document.createElement('div');
    textEl.className = 'annotate-decision-text';
    textEl.textContent = cardText; // textContent only — agent data
    item.appendChild(textEl);
  }
  const ev = evidenceOf(dr);
  // v2.19: impact / blocking chips
  const hasImpact = typeof dr.impact === 'string' && DECISION_IMPACTS.indexOf(dr.impact) !== -1;
  if (hasImpact || dr.blocking === true) {
    const meta = document.createElement('div');
    meta.className = 'annotate-decision-meta';
    if (hasImpact) {
      const s = document.createElement('span');
      s.className = 'annotate-decision-chip annotate-chip-impact-' + dr.impact;
      s.textContent = 'Impact: ' + dr.impact;
      s.title = 'Impact if decided wrongly';
      meta.appendChild(s);
    }
    if (dr.blocking === true) {
      const s = document.createElement('span');
      s.className = 'annotate-decision-chip annotate-chip-blocking';
      s.textContent = 'Blocking';
      s.title = 'The agent cannot proceed until this is decided';
      meta.appendChild(s);
    }
    item.appendChild(meta);
  }

  if (entry.decisionVerdict && stripChanging[id]) {
    const note = document.createElement('div');
    note.className = 'annotate-decision-changing-note';
    const label = document.createElement('span');
    label.textContent = 'Changing verdict — currently ' + (entry.decisionVerdict === 'select'
      ? '☑ ' + entry.answerText
      : (DECISION_VERDICT_TEXT[entry.decisionVerdict] || entry.decisionVerdict));
    note.appendChild(label);
    const cancelBtn = makeStripBtn('Cancel', 'annotate-decision-cancel');
    cancelBtn.addEventListener('click', () => {
      delete stripChanging[id];
      renderDecisionStrips();
    });
    note.appendChild(cancelBtn);
    item.appendChild(note);
  }

  const ctx = typeof dr.context === 'string' ? dr.context.trim() : '';
  if (ctx) {
    const ctxEl = document.createElement('div');
    ctxEl.className = 'annotate-decision-context';
    ctxEl.textContent = ctx; // textContent only — agent data
    item.appendChild(ctxEl);
  }

  const opts = stripDecisionOptions(dr);
  const hasCons = opts.some(o => !!o.consequence);
  const rec = typeof dr.recommendation === 'string' ? dr.recommendation : null;
  if (rec) {
    const recId = stripCanonicalOptionId(rec);
    const recOpt = opts.find(o => o.id === recId);
    const recLine = document.createElement('div');
    recLine.className = 'annotate-decision-reco-line';
    recLine.appendChild(document.createTextNode('Recommended: '));
    const recName = document.createElement('b');
    recName.textContent = recOpt ? recOpt.plain : (DECISION_PLAIN_LABEL[recId] || rec);
    recLine.appendChild(recName);
    item.appendChild(recLine);
  }

  // The first evidence target, quoted. The strip's own anchor is the element
  // right above it, so it is never quoted here (the rail card quotes it).
  const firstTarget = ev.length ? findAnchorEl(ev[0].anchor) : null;
  if (firstTarget) {
    const text = excerptText(firstTarget);
    if (text) item.appendChild(buildExcerptEl(id + '\nfirst', text, excerptSource(ev[0].anchor)));
  }

  const btnRow = document.createElement('div');
  btnRow.className = 'annotate-decision-btns';
  item.appendChild(btnRow);
  if (hasCons) btnRow.classList.add('has-consequences');

  // A1: one optional comment box under the options. It is the same draft as
  // the rail card's box (shared through the shell), goes with whichever
  // option is clicked, and with no option picked it is the answer at Send.
  const ta = document.createElement('textarea');
  ta.className = 'annotate-decision-ta annotate-decision-cmt';
  ta.rows = 1;
  ta.placeholder = 'Comment (optional)';
  ta.setAttribute('aria-label', 'Comment (optional)');
  ta.dataset.stripSay = id;
  ta.value = typeof entry.sayDraft === 'string' ? entry.sayDraft : '';
  const hint = document.createElement('div');
  hint.className = 'annotate-decision-cmt-hint';
  const syncHint = () => {
    hint.textContent = (ta.value || '').trim()
      ? 'Saved with your choice. With no choice picked, it counts as your answer when you send.'
      : '';
  };
  syncHint();
  ta.addEventListener('annotate-sync', syncHint);
  ta.addEventListener('input', () => {
    syncHint();
    postToParent({ type: 'annotate:say-draft', commentId: id, text: ta.value });
  });

  const feedback = document.createElement('div');
  feedback.className = 'annotate-decision-feedback';

  const noteText = () => {
    const t = (ta.value || '').trim();
    return t || null;
  };
  const clearDraft = () => {
    postToParent({ type: 'annotate:say-draft', commentId: id, text: '' });
  };

  const isRec = o => !!rec && stripCanonicalOptionId(rec) === o.id;
  for (const o of opts) {
    if (o.id === 'accept' || o.id === 'reject') {
      const b = makeOptionBtn(o, DECISION_BTN_CLASS[o.id], isRec(o));
      b.addEventListener('click', () => { const n = noteText(); clearDraft(); submitStripDecision(id, o.id, n, item); });
      btnRow.appendChild(b);
    } else if (o.id === 'comment' || o.id === 'changes') {
      // Request changes (pre-D2: Comment) still needs words.
      const b = makeOptionBtn(o, DECISION_BTN_CLASS[o.id], isRec(o));
      b.addEventListener('click', () => {
        const n = noteText();
        if (!n) {
          ta.placeholder = o.id === 'changes' ? 'What needs to change…' : 'Add your comment…';
          ta.focus();
          feedback.classList.remove('is-error');
          feedback.textContent = o.id === 'changes' ? 'Say what needs to change in the box, then pick it again.' : 'Write your answer in the box, then pick it again.';
          return;
        }
        clearDraft();
        submitStripDecision(id, o.id, n, item);
      });
      btnRow.appendChild(b);
    } else {
      // custom option id → the `select` verdict naming the choice, or the
      // pre-D3 `comment` text against a server that predates it.
      const b = makeOptionBtn(o, 'annotate-decision-custom' + (o.style ? ' annotate-style-' + o.style : ''), isRec(o));
      b.addEventListener('click', () => {
        const n = noteText();
        const v = latestSelect ? 'select' : 'comment';
        const text = (v === 'select' ? o.label : 'Selected: ' + o.label) + (n ? '\n\n' + n : '');
        clearDraft();
        submitStripDecision(id, v, text, item);
      });
      btnRow.appendChild(b);
    }
  }

  if (ev.length) item.appendChild(buildEvidenceEl(entry, ev));
  item.appendChild(ta);
  item.appendChild(hint);
  item.appendChild(feedback);

  if (pendingDecisionIds.has(id)) {
    setStripItemDisabled(item, true);
    feedback.textContent = 'Sending…';
  }

  return item;
}

function buildStripEl(anchorId, items) {
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
  items.forEach(entry => wrap.appendChild(buildDecisionItemEl(entry)));
  return wrap;
}

// Real-document-flow insertion, per anchor element shape. Returns true on
// success; false means the caller must use the absolute-overlay fallback.
// SVG content is routed straight to the fallback: an HTML element appended
// as a sibling of SVG children has no rendering box (only <foreignObject>
// children paint), so DOM-flow insertion would silently produce nothing.
function insertStripInFlow(el, stripEl) {
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
      el.insertAdjacentElement('afterend', tr);
      return true;
    }
    stripEl.classList.add('annotate-strip-block');
    el.insertAdjacentElement('afterend', stripEl);
    return true;
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

// Rebuilds every inline decision strip from latestPins. Called only from the
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
      font: 700 9.5px "Inter", sans-serif; letter-spacing: .02em; }
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

function renderDecisionStrips() {
  ensureStripStyle();
  document.querySelectorAll('[data-annotate-strip]').forEach(n => n.remove());
  // One card per question in the body. A generated card whose question the
  // interactive strip now renders is hidden (it stays in the HTML as the
  // no-JavaScript fallback) and comes back if the strip goes away.
  document.querySelectorAll('[data-annotate-replaced]').forEach(card => {
    card.classList.remove('annotate-card-replaced');
    delete card.dataset.annotateReplaced;
  });

  for (const [anchorId, entries] of Object.entries(latestPins)) {
    const items = (entries || []).filter(e => e.decisionRequest || e.decisionVerdict);
    if (!items.length) continue;
    const el = findAnchorEl(anchorId);
    if (!el) continue;

    // Same hidden-tab-panel skip as pins: never render a strip on top of, or
    // inside, an inactive tab panel.
    const panel = el.closest('.tab-panel');
    if (panel && !panel.classList.contains('active')) continue;
    const subPanel = el.closest('.sub-panel');
    if (subPanel && !subPanel.classList.contains('active')) continue;

    items.sort((a, b) => (a.n || 0) - (b.n || 0));
    const stripEl = buildStripEl(anchorId, items);
    if (!insertStripInFlow(el, stripEl)) placeStripAbsolute(el, stripEl);
    if (items.some(e => e.decisionRequest)) {
      staticCardsFor(anchorId).forEach(card => {
        card.classList.add('annotate-card-replaced');
        card.dataset.annotateReplaced = '1';
      });
    }
  }
  syncAllExcerptClamps();
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

// `back` ({commentId, n, from: 'strip'|'rail'}) is set by an evidence "Go to":
// the target then carries a "Back to #N" marker that returns to the card.
function scrollToAnchor(anchorId, target, back) {
  ensureGotoHighlightStyle();
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
      marker.row.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
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
  item.scrollIntoView({ behavior: 'smooth', block: 'center' });
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
      font: 600 13px/1.4 "Inter", sans-serif !important;
      color: var(--color-base-content) !important; background: var(--color-base-200) !important; border: 1px dashed var(--line) !important;
      border-radius: 8px !important; padding: 8px 12px !important; cursor: pointer !important; margin: 0 !important;
    }
    .annotate-unchanged-toggle:hover { background: var(--color-base-200) !important; border-color: var(--muted) !important; }
    .annotate-unchanged-toggle:focus-visible { outline: 2px solid var(--link) !important; outline-offset: 1px !important; }
    .annotate-unchanged-toggle::before { content: '\\25B8'; font-size: 11px; color: var(--muted); transition: transform .12s; align-self: center; }
    .annotate-unchanged-toggle[aria-expanded="true"]::before { transform: rotate(90deg); }
    .annotate-unchanged-title { font-size: 12.5px !important; font-weight: 700 !important; color: var(--color-base-content) !important; }
    .annotate-unchanged-note { font-weight: 500 !important; color: var(--muted) !important; font-size: 10.5px !important; }
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
      const open = e.decision === true || (e.decisionRequest && stripChanging[e.id]);
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
function postExcerpts() {
  if (window.parent === window) return;
  const out = {};
  const add = (aid) => {
    if (!aid || Object.prototype.hasOwnProperty.call(out, aid)) return;
    const el = findAnchorEl(aid);
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
  const json = JSON.stringify(out);
  if (json === lastExcerptsJson) return;
  lastExcerptsJson = json;
  postToParent({ type: 'annotate:excerpts', version: META.version || null, excerpts: out });
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
    } else if (data.type === 'annotate:card-hover') {
      setCardHover(data.on ? data.anchorId : null, data.target || null);
    } else if (data.type === 'annotate:scroll-to') {
      scrollToAnchor(data.anchorId, data.target || null, data.back || null);
    } else if (data.type === 'annotate:say-draft-set') {
      // A1: the rail card's comment box changed; mirror it here.
      document.querySelectorAll('textarea[data-strip-say]').forEach(ta => {
        if (ta.dataset.stripSay !== data.commentId || ta === document.activeElement) return;
        ta.value = typeof data.text === 'string' ? data.text : '';
        ta.dispatchEvent(new Event('annotate-sync'));
      });
    } else if (data.type === 'annotate:comment-counts') {
      latestCounts = data.counts || {};
      latestPins = data.pins || {};
      latestRounds = data.rounds === true; // absent from an old shell → legacy posting
      latestChanges = data.changes === true; // absent from an old shell → "Comment"
      latestSelect = data.select === true;   // absent from an old shell → `comment`
      latestCardStates = data.cardStates || {};
      // Strips first: they can insert real sibling rows/elements that shift
      // layout, so pins must be positioned AFTER that shift, not before it.
      renderDecisionStrips();
      openUnchangedSectionsForOpenCards();
      renderCardStates();
      renderBadges();
      postExcerpts();
    }
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
  container.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
  document.addEventListener('mouseover', e => {
    if (commentable) commentable.classList.remove('unified-commentable');
    commentable = null;
    if (e.target.closest(INTERACTIVE_SEL + ', [data-annotate-strip], .annotate-unchanged-bar, #badge-layer')) return;
    const a = findParentAnchor(e.target);
    if (a) { commentable = a; a.classList.add('unified-commentable'); }
  });
  document.addEventListener('mouseout', e => {
    if (commentable && !commentable.contains(e.relatedTarget)) {
      commentable.classList.remove('unified-commentable');
      commentable = null;
    }
  });
}
// Wide tables scroll sideways in their own labelled region.
function wrapScrollTables() {
  document.querySelectorAll('table').forEach(t => {
    if (t.closest('.unified-table-scroll') || t.closest('[data-annotate-strip]')) return;
    const wrap = document.createElement('div');
    wrap.className = 'unified-table-scroll';
    wrap.tabIndex = 0;
    wrap.setAttribute('role', 'region');
    wrap.setAttribute('aria-label', 'Table · scroll sideways');
    t.before(wrap);
    wrap.append(t);
    const hint = document.createElement('p');
    hint.className = 'unified-table-hint';
    hint.textContent = 'Scroll sideways to see all columns';
    wrap.after(hint);
  });
  scheduleBadgeRefresh();
}
function ensureAffordanceStyle() {
  if (document.getElementById('annotate-affordance-style')) return;
  const style = document.createElement('style');
  style.id = 'annotate-affordance-style';
  style.textContent = `
    .unified-annotation-hover,.unified-commentable{outline:2px solid var(--color-primary)!important;outline-offset:2px!important}
    .unified-commentable{cursor:crosshair}
    .bpin[role=button]:focus-visible{outline:3px solid var(--color-primary);outline-offset:3px}
    .unified-table-scroll{overflow-x:auto;max-width:calc(100% - 28px);margin-left:28px;scrollbar-gutter:stable;overscroll-behavior-x:contain;border-right:2px solid var(--color-base-300)}
    .unified-table-scroll table{min-width:1000px;width:100%;max-width:none;table-layout:auto!important}
    .unified-table-scroll th,.unified-table-scroll td{overflow-wrap:normal!important;word-break:normal!important;min-width:120px}
    .unified-table-scroll th:first-child,.unified-table-scroll td:first-child{min-width:48px}
    .unified-table-hint{font-size:10.5px;margin:4px 0 14px 28px;color:var(--color-base-content)}
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
  .sp-rev button,.sp-rev a{font:inherit;font-size:10.5px;color:inherit;background:none;border:0;padding:0;cursor:pointer;text-decoration:underline;text-underline-offset:2px}
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
    const style = document.createElement('style'); style.textContent = css; document.head.appendChild(style);
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

// ── Init ─────────────────────────────────────────────────────────
async function init() {
  initPlanChanges();
  wireClicks();
  wireBridge();
  wireSelectionComments();
  wireCommentableHover();
  wirePageLinks();
  ensureAffordanceStyle();
  wrapScrollTables();
  installBadgeMutObs();
  wireHoverLinking();
  // Before the first paint settles, so a later version opens compact.
  initUnchangedSections();

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
