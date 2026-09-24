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

// Elements whose own click behavior must win over click-to-comment: native
// form controls, links, ARIA widgets, and the artifact chrome. Anything NOT
// matched here stays fully annotatable, so click-anywhere-to-comment is
// unchanged everywhere else. Add [data-annotate-interactive] to opt a custom
// widget in; Alt/Option-click opts back out for a one-off comment.
const INTERACTIVE_SEL = [
  'a[href]', 'button', 'input', 'select', 'textarea', 'option', 'optgroup',
  'label', 'summary', 'audio[controls]', 'video[controls]',
  '[contenteditable]:not([contenteditable="false"])',
  '[tabindex]:not([tabindex="-1"])',
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

function captureTarget(clickEl, anchorEl, ev) {
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
      if (el2.closest('#badge-layer') || el2.closest('[data-annotate-strip]') || el2.classList.contains('bpin-inline') || el2.tagName === 'SCRIPT' || el2.tagName === 'STYLE') return;
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
      window.parent.postMessage({
        type: 'annotate:pin-open',
        anchorId: pinAid,
        anchorIds,
        anchorLabel: anchorName(pinAid),
        commentIds: (pin.dataset.pinComments || '').split(',').filter(Boolean),
        x: e.clientX,
        y: e.clientY,
      }, '*');
      return;
    }

    // Inline decision strips (see "Inline body decision strips" below) wire
    // their own click handlers directly on their buttons/textarea. A click on
    // any other part of a strip (prompt text, padding) must never fall
    // through to click-to-CREATE — it isn't a click on the underlying anchor.
    if (e.target.closest('[data-annotate-strip]')) return;

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

    window.parent.postMessage({
      type: 'annotate:pin-click',
      anchorId: aid,
      anchorLabel: anchorName(aid),
      // Granular capture: exactly which inner element was clicked (null when
      // the click was on the anchor itself). Stored on the comment so goto
      // can return to the precise spot, not just the section.
      target: captureTarget(e.target, target, e),
      x: e.clientX,
      y: e.clientY,
    }, '*');
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
    window.parent.postMessage({
      type: 'annotate:pin-click',
      anchorId: anchorId,
      anchorLabel: anchorName(anchorId),
      target: null,
      x: typeof x === 'number' ? x : 0,
      y: typeof y === 'number' ? y : 0,
    }, '*');
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
      box-shadow: 0 0 0 3px rgba(67,56,202,.35), 0 1px 4px rgba(0,0,0,.25) !important;
    }
    .bpin-unread { background: #DC2626 !important; }
    .bpin-cluster {
      background: #312E81 !important;
      box-shadow: 0 0 0 2px #FFF, 0 1px 4px rgba(0,0,0,.35) !important;
    }
    .bpin-cluster:hover {
      box-shadow: 0 0 0 2px #FFF, 0 0 0 5px rgba(49,46,129,.35) !important;
    }
    /* Decision pins take priority over unread/cluster styling — placed
       last so equal-specificity !important rules resolve in its favor. */
    .bpin-decision {
      background: #4338CA !important;
      box-shadow: 0 0 0 3px #FFF, 0 1px 4px rgba(0,0,0,.3) !important;
      animation: bpinDecisionPulse 1.5s ease-in-out 3;
    }
    @keyframes bpinDecisionPulse {
      0%, 100% { box-shadow: 0 0 0 3px #FFF, 0 0 0 3px rgba(67,56,202,.5); }
      50% { box-shadow: 0 0 0 3px #FFF, 0 0 0 8px rgba(67,56,202,0); }
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
  return `width:${s}px;height:${s}px;color:#FFF;border-radius:50%;font-size:${s > 20 ? 12 : 10}px;font-weight:700;display:flex;align-items:center;justify-content:center;box-shadow:0 1px 4px rgba(0,0,0,.25);background:#4338CA`;
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
  const inset = 8;
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

  for (const [anchorId, count] of Object.entries(latestCounts)) {
    if (!count) continue;
    const el = findAnchorEl(anchorId);
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
      outline: 2px solid #4338CA !important;
      outline-offset: -1px !important;
      background: rgba(67,56,202,0.06) !important;
    }
    .bpin-hl {
      transform: scale(1.25) !important;
      box-shadow: 0 0 0 3px #FFF, 0 0 0 6px rgba(67,56,202,.45) !important;
    }
  `;
  document.head.appendChild(style);
}

function highlightAnchor(anchorId, on) {
  const el = anchorId && findAnchorEl(anchorId);
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
// v2.19 per-item UI state that must survive a rebuild: context disclosure
// open, optional-note form open, and the note draft text.
const stripDetailsOpen = {};
const stripNoteOpen = {};
const stripNoteText = {};
// D3: the standing Comment form's open state and draft, kept across a
// rebuild exactly like the note above.
const stripSayOpen = {};
const stripSayText = {};
const DECISION_BTN_TEXT = { accept: '✓ Accept', reject: '✗ Reject', comment: '💬 Comment', changes: '↻ Request changes' };
const DECISION_BTN_CLASS = { accept: 'annotate-decision-accept', reject: 'annotate-decision-reject', comment: 'annotate-decision-comment', changes: 'annotate-decision-changes' };
const DECISION_CONTEXT_INLINE_MAX = 160;
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
      if (DECISION_OPTIONS_ALL.indexOf(o) === -1) continue;
      const sid = stripCanonicalOptionId(o);
      const scq = typeof cons[o] === 'string' ? cons[o] : (typeof cons[sid] === 'string' ? cons[sid] : '');
      out.push({ id: sid, label: DECISION_BTN_TEXT[sid], consequence: scq, style: null, custom: false });
    } else if (o && typeof o === 'object' && typeof o.id === 'string' && o.id) {
      const oid = stripCanonicalOptionId(o.id);
      const known = DECISION_OPTIONS_ALL.indexOf(oid) !== -1;
      const label = typeof o.label === 'string' && o.label.trim() ? o.label.trim() : null;
      out.push({
        id: known ? oid : o.id,
        label: label || (known ? DECISION_BTN_TEXT[oid] : o.id),
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
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
      background: #EEF2FF !important;
      border: 1.5px solid #4338CA !important;
      border-radius: 8px !important;
      padding: 8px 10px !important;
      margin: 6px 0 !important;
      box-sizing: border-box !important;
      max-width: 100% !important;
      display: block !important;
      text-align: left !important;
    }
    .annotate-strip-tr > td { padding: 0 !important; border: none !important; background: transparent !important; }
    .annotate-strip-abs { pointer-events: auto !important; }
    .annotate-decision-item + .annotate-decision-item {
      margin-top: 8px !important; padding-top: 8px !important;
      border-top: 1px solid rgba(67,56,202,.25) !important;
    }
    .annotate-decision-prompt {
      font-size: 12px !important; font-weight: 600 !important; color: #312E81 !important;
      margin: 0 0 6px !important; line-height: 1.4 !important; white-space: normal !important;
    }
    .annotate-decision-btns { display: flex !important; gap: 6px !important; flex-wrap: wrap !important; min-width: 0 !important; }
    .annotate-decision-btn {
      font-size: 11.5px !important; font-weight: 700 !important; padding: 5px 11px !important;
      border-radius: 6px !important; border: none !important; cursor: pointer !important;
      color: #FFF !important; font-family: inherit !important;
      /* An option label longer than the strip used to force the flex line
         wider than the page; the button and its consequence line then ran
         off the right edge (user-reported). */
      max-width: 100% !important; min-width: 0 !important; text-align: left !important;
      line-height: 1.35 !important; white-space: normal !important; overflow-wrap: anywhere !important;
    }
    .annotate-decision-btn:hover { filter: brightness(.92) !important; }
    .annotate-decision-btn:disabled { opacity: .55 !important; cursor: not-allowed !important; filter: none !important; }
    .annotate-decision-accept { background: #16A34A !important; }
    .annotate-decision-reject { background: #DC2626 !important; }
    .annotate-decision-comment, .annotate-decision-submit { background: #4338CA !important; }
    /* D2 "Request changes": amber, deliberately not Reject's red. */
    .annotate-decision-changes { background: #B45309 !important; }
    /* display is intentionally NOT set here: it's driven entirely by the
       inline style.setProperty(..., 'important') toggle in JS (open/closed),
       which an author-stylesheet !important rule here would permanently
       defeat. */
    .annotate-decision-form { margin-top: 6px !important; flex-direction: column !important; gap: 5px !important; }
    .annotate-decision-ta {
      width: 100% !important; min-height: 40px !important; padding: 5px 7px !important;
      border: 1px solid #C7D2FE !important; border-radius: 5px !important; font-size: 11px !important;
      font-family: inherit !important; resize: vertical !important; color: #0F172A !important;
      background: #FFF !important; box-sizing: border-box !important; line-height: 1.4 !important;
    }
    .annotate-decision-ta:focus { outline: none !important; border-color: #4338CA !important; }
    .annotate-decision-feedback {
      margin-top: 5px !important; font-size: 10.5px !important; font-weight: 600 !important;
      color: #4338CA !important; min-height: 12px !important;
    }
    .annotate-decision-feedback.is-error { color: #DC2626 !important; }
    .annotate-decision-delivery {
      font-size: 11px !important; color: #64748B !important; margin-left: 8px !important;
    }
    .annotate-verdict-chip {
      display: inline-block !important; font-size: 11px !important; font-weight: 700 !important;
      padding: 4px 10px !important; border-radius: 10px !important;
    }
    .annotate-verdict-chip.verdict-accept { background: #DCFCE7 !important; color: #15803D !important; }
    .annotate-verdict-chip.verdict-reject { background: #FEF2F2 !important; color: #DC2626 !important; }
    .annotate-verdict-chip.verdict-comment { background: #E0E7FF !important; color: #4338CA !important; }
    .annotate-verdict-chip.verdict-changes { background: #FEF3C7 !important; color: #B45309 !important; }
    .annotate-decision-change, .annotate-decision-cancel {
      background: none !important; color: #4338CA !important; font-weight: 600 !important;
      padding: 4px 6px !important; margin-left: 6px !important; text-decoration: none !important;
    }
    .annotate-decision-change:hover, .annotate-decision-cancel:hover { filter: none !important; text-decoration: underline !important; }
    .annotate-decision-changing-note {
      display: flex !important; align-items: center !important; justify-content: space-between !important;
      gap: 8px !important; font-size: 11px !important; font-weight: 600 !important; color: #4338CA !important;
      background: #E0E7FF !important; border-radius: 6px !important; padding: 5px 8px !important;
      margin-bottom: 6px !important;
    }
    .annotate-strip-anchor-label {
      font-size: 10px !important; font-weight: 700 !important; color: #64748B !important;
      text-transform: uppercase !important; letter-spacing: .03em !important;
      margin: 0 0 5px !important; white-space: normal !important;
    }
    /* v2.19 fields */
    .annotate-decision-context {
      font-size: 11px !important; color: #475569 !important; line-height: 1.5 !important;
      margin: -2px 0 6px !important; white-space: pre-wrap !important; word-break: break-word !important;
      font-weight: 400 !important;
    }
    .annotate-decision-disclosure { margin: -2px 0 6px !important; }
    .annotate-decision-disclosure-btn {
      font-size: 10.5px !important; font-weight: 600 !important; color: #4338CA !important;
      background: none !important; border: none !important; padding: 2px 0 !important;
      cursor: pointer !important; font-family: inherit !important; display: inline-flex !important;
      align-items: center !important; gap: 4px !important;
    }
    .annotate-decision-disclosure-btn::before { content: '\\25B8'; font-size: 9px; transition: transform .12s; }
    .annotate-decision-disclosure-btn[aria-expanded="true"]::before { transform: rotate(90deg); }
    .annotate-decision-disclosure .annotate-decision-context {
      margin: 4px 0 0 !important; padding: 6px 8px !important; background: #F8FAFC !important;
      border: 1px solid #E2E8F0 !important; border-radius: 6px !important;
    }
    .annotate-decision-context[hidden] { display: none !important; }
    .annotate-decision-meta { display: flex !important; gap: 5px !important; flex-wrap: wrap !important; margin: 0 0 6px !important; }
    .annotate-decision-chip {
      font-size: 9px !important; font-weight: 700 !important; padding: 2px 7px !important; border-radius: 8px !important;
      text-transform: uppercase !important; letter-spacing: .04em !important; white-space: nowrap !important;
    }
    .annotate-chip-impact-low { background: #F1F5F9 !important; color: #475569 !important; }
    .annotate-chip-impact-medium { background: #FEF3C7 !important; color: #B45309 !important; }
    .annotate-chip-impact-high { background: #FEE2E2 !important; color: #B91C1C !important; }
    .annotate-chip-blocking { background: #312E81 !important; color: #FFF !important; }
    .annotate-decision-btns.has-consequences { flex-direction: column !important; align-items: stretch !important; }
    .annotate-decision-opt { display: flex !important; flex-direction: column !important; gap: 3px !important; min-width: 0 !important; max-width: 100% !important; }
    .annotate-decision-opt .annotate-decision-btn { align-self: flex-start !important; }
    .annotate-decision-consequence {
      font-size: 10.5px !important; color: #64748B !important; line-height: 1.4 !important;
      padding-left: 2px !important; white-space: pre-wrap !important; word-break: break-word !important;
    }
    .annotate-decision-btn.is-recommended { box-shadow: 0 0 0 2px #FFF, 0 0 0 4px #4338CA !important; }
    .annotate-decision-rec {
      font-size: 8.5px !important; font-weight: 800 !important; letter-spacing: .05em !important;
      text-transform: uppercase !important; background: rgba(255,255,255,.28) !important;
      padding: 1px 5px !important; border-radius: 6px !important; margin-left: 6px !important;
    }
    .annotate-decision-say-row {
      display: flex !important; align-items: center !important; gap: 8px !important;
      flex-wrap: wrap !important; margin-top: 8px !important;
    }
    .annotate-decision-say {
      font-size: 11.5px !important; font-weight: 700 !important; padding: 5px 11px !important;
      border-radius: 6px !important; border: 1px solid #C7D2FE !important; cursor: pointer !important;
      background: #FFF !important; color: #4338CA !important; font-family: inherit !important;
      max-width: 100% !important; text-align: left !important; line-height: 1.35 !important;
      white-space: normal !important; overflow-wrap: anywhere !important;
    }
    .annotate-decision-say:hover { background: #E0E7FF !important; filter: none !important; }
    .annotate-decision-say-hint { font-size: 10.5px !important; color: #64748B !important; }
    .annotate-decision-commented { margin: 0 0 6px !important; }
    .annotate-decision-commented-txt { font-size: 10.5px !important; color: #64748B !important; margin-left: 6px !important; }
    .annotate-decision-custom { background: #475569 !important; }
    .annotate-decision-custom.annotate-style-primary { background: #4338CA !important; }
    .annotate-decision-custom.annotate-style-danger { background: #DC2626 !important; }
    .annotate-decision-evidence {
      display: flex !important; flex-wrap: wrap !important; align-items: center !important;
      gap: 2px 6px !important; margin: 6px 0 0 !important; font-size: 10.5px !important; color: #64748B !important;
    }
    .annotate-decision-evidence-lbl { font-weight: 600 !important; }
    .annotate-decision-evidence-link {
      font-size: 10.5px !important; color: #4338CA !important; font-weight: 600 !important;
      background: none !important; border: none !important; padding: 1px 2px !important;
      cursor: pointer !important; font-family: inherit !important; text-decoration: underline dotted !important;
    }
    .annotate-decision-note-toggle {
      font-size: 10.5px !important; color: #64748B !important; background: none !important;
      border: none !important; padding: 2px 0 !important; cursor: pointer !important;
      font-family: inherit !important; margin-top: 6px !important; display: block !important;
    }
    .annotate-decision-note-toggle:hover { color: #4338CA !important; filter: none !important; }
    .annotate-decision-note-form { margin-top: 4px !important; }
    .annotate-decision-note-form[hidden] { display: none !important; }
    .annotate-decision-pending {
      display: inline-block !important; font-size: 9.5px !important; font-weight: 700 !important;
      padding: 2px 8px !important; border-radius: 8px !important; background: #FEF3C7 !important;
      color: #B45309 !important; border: 1px dashed #F59E0B !important; text-transform: uppercase !important;
      letter-spacing: .04em !important; margin-left: 8px !important; vertical-align: middle !important;
    }
    .annotate-decision-sendnow {
      background: none !important; color: #4338CA !important; font-weight: 600 !important;
      padding: 4px 6px !important; margin-left: 4px !important; font-size: 10.5px !important;
    }
    .annotate-decision-sendnow:hover { filter: none !important; text-decoration: underline !important; }
    @media (max-width: 768px), (max-height: 480px) {
      .annotate-decision-disclosure-btn, .annotate-decision-evidence-link, .annotate-decision-note-toggle,
      .annotate-decision-sendnow { min-height: 44px !important; padding: 10px 4px !important; touch-action: manipulation !important; }
      /* Thumb-sized buttons, buttons free to wrap to their own row, and a
         16px textarea so iOS doesn't zoom the page in on focus. */
      .annotate-decision-btn, .annotate-decision-say {
        min-height: 44px !important; padding: 10px 16px !important; font-size: 13px !important;
        flex: 1 1 auto !important; touch-action: manipulation !important;
      }
      .annotate-decision-ta { font-size: 16px !important; min-height: 48px !important; }
      .annotate-decision-change, .annotate-decision-cancel { min-height: 44px !important; padding: 10px 12px !important; touch-action: manipulation !important; }
    }
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
function appendPendingControls(itemEl, id) {
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
    window.parent.postMessage({ type: 'annotate:decision-posted', commentId: id }, '*');
  });
  itemEl.appendChild(send);
}

function swapStripItemToResolved(itemEl, verdict, deliveryMsg, pendingId) {
  itemEl.innerHTML = '';
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
  window.parent.postMessage({ type: 'annotate:decision-posted', commentId: id }, '*');
}

function makeStripBtn(label, cls) {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'annotate-decision-btn ' + cls;
  b.textContent = label;
  return b;
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
    const chip = document.createElement('span');
    chip.className = 'annotate-verdict-chip verdict-' + entry.decisionVerdict;
    chip.textContent = DECISION_VERDICT_LABEL[entry.decisionVerdict] || entry.decisionVerdict;
    item.appendChild(chip);
    // T-verdict-reversal: only offer "Change" when the shell still sent the
    // original decisionRequest alongside decisionVerdict (new shell always
    // does once resolved — see shell.js sendCommentCountsToFrame). An old
    // shell that predates this fix never will, so this just quietly shows
    // the plain chip against it instead of erroring.
    if (entry.decisionRequest) {
      const changeBtn = makeStripBtn('↺ Change', 'annotate-decision-change');
      changeBtn.addEventListener('click', () => {
        stripChanging[id] = true;
        renderDecisionStrips();
      });
      item.appendChild(changeBtn);
    }
    if (entry.roundPending) appendPendingControls(item, id);
    return item;
  }

  const dr = entry.decisionRequest || {};
  const promptEl = document.createElement('div');
  promptEl.className = 'annotate-decision-prompt';
  // textContent only — decision_request.prompt is store/agent-controlled
  // data and must never be interpreted as markup.
  promptEl.textContent = dr.prompt || '';
  item.appendChild(promptEl);

  // v2.19: context — short inline, long behind a WAI-ARIA disclosure that
  // opens inline (no sheet) so it works identically on mobile.
  const ctx = typeof dr.context === 'string' ? dr.context.trim() : '';
  if (ctx) {
    const ctxEl = document.createElement('div');
    ctxEl.className = 'annotate-decision-context';
    ctxEl.textContent = ctx;
    if (ctx.length <= DECISION_CONTEXT_INLINE_MAX) {
      item.appendChild(ctxEl);
    } else {
      const disc = document.createElement('div');
      disc.className = 'annotate-decision-disclosure';
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'annotate-decision-disclosure-btn';
      btn.textContent = 'Why / details';
      const rid = 'annotate-dctx-' + id;
      ctxEl.id = rid;
      ctxEl.setAttribute('role', 'region');
      ctxEl.setAttribute('aria-label', 'Decision details');
      const open = !!stripDetailsOpen[id];
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
      btn.setAttribute('aria-controls', rid);
      ctxEl.hidden = !open;
      btn.addEventListener('click', () => {
        const now = !stripDetailsOpen[id];
        stripDetailsOpen[id] = now;
        btn.setAttribute('aria-expanded', now ? 'true' : 'false');
        ctxEl.hidden = !now;
      });
      disc.appendChild(btn);
      disc.appendChild(ctxEl);
      item.appendChild(disc);
    }
  }
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
    label.textContent = 'Changing verdict — currently ' +
      (DECISION_VERDICT_TEXT[entry.decisionVerdict] || entry.decisionVerdict);
    note.appendChild(label);
    const cancelBtn = makeStripBtn('Cancel', 'annotate-decision-cancel');
    cancelBtn.addEventListener('click', () => {
      delete stripChanging[id];
      renderDecisionStrips();
    });
    note.appendChild(cancelBtn);
    item.appendChild(note);
  }

  const btnRow = document.createElement('div');
  btnRow.className = 'annotate-decision-btns';
  item.appendChild(btnRow);

  const form = document.createElement('div');
  form.className = 'annotate-decision-form';
  // The stylesheet's `.annotate-decision-form{display:flex!important}` (needed
  // to beat host-doc CSS) would otherwise permanently defeat a plain inline
  // `style.display` toggle — only an inline !important can out-rank it.
  form.style.setProperty('display', stripFormOpen[id] ? 'flex' : 'none', 'important');
  const ta = document.createElement('textarea');
  ta.className = 'annotate-decision-ta';
  ta.rows = 2;
  ta.placeholder = latestChanges ? 'What needs to change…' : 'Add your comment…';
  ta.value = stripDraftText[id] || '';
  ta.addEventListener('input', () => { stripDraftText[id] = ta.value; });
  const submitBtn = makeStripBtn('Send', 'annotate-decision-submit');
  ta.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      submitBtn.click();
    }
  });
  form.appendChild(ta);
  form.appendChild(submitBtn);
  item.appendChild(form);

  const feedback = document.createElement('div');
  feedback.className = 'annotate-decision-feedback';
  item.appendChild(feedback);

  const opts = stripDecisionOptions(dr);
  const hasCons = opts.some(o => !!o.consequence);
  if (hasCons) btnRow.classList.add('has-consequences');
  const rec = typeof dr.recommendation === 'string' ? dr.recommendation : null;

  // Optional note for Accept/Reject ("+ Add a note"); null when closed/empty.
  let noteTa = null;
  const noteText = () => {
    if (!stripNoteOpen[id] || !noteTa) return null;
    const t = (noteTa.value || '').trim();
    return t || null;
  };

  const mountOption = (b, o) => {
    if (rec && stripCanonicalOptionId(rec) === o.id) {
      b.classList.add('is-recommended');
      b.title = 'Recommended by the agent';
      const badge = document.createElement('span');
      badge.className = 'annotate-decision-rec';
      badge.textContent = 'Recommended';
      b.appendChild(badge);
    }
    if (!hasCons) { btnRow.appendChild(b); return; }
    const wrap = document.createElement('div');
    wrap.className = 'annotate-decision-opt';
    wrap.appendChild(b);
    if (o.consequence) {
      const c = document.createElement('div');
      c.className = 'annotate-decision-consequence';
      c.textContent = o.consequence; // textContent only — agent data
      wrap.appendChild(c);
    }
    btnRow.appendChild(wrap);
  };

  for (const o of opts) {
    if (o.id === 'accept' || o.id === 'reject') {
      const b = makeStripBtn(o.label, DECISION_BTN_CLASS[o.id]);
      b.addEventListener('click', () => submitStripDecision(id, o.id, noteText(), item));
      mountOption(b, o);
    } else if (o.id === 'comment' || o.id === 'changes') {
      // One slot, two spellings: "Comment" pre-D2, "Request changes" after.
      // Both reveal the textarea; neither submits empty.
      const b = makeStripBtn(o.label, DECISION_BTN_CLASS[o.id]);
      b.addEventListener('click', () => {
        stripFormOpen[id] = true;
        form.style.setProperty('display', 'flex', 'important');
        ta.focus();
      });
      mountOption(b, o);
    } else {
      // custom option id → the `select` verdict naming the choice, or the
      // pre-D3 `comment` text against a server that predates it.
      const b = makeStripBtn(o.label, 'annotate-decision-custom' + (o.style ? ' annotate-style-' + o.style : ''));
      b.addEventListener('click', () => {
        const n = noteText();
        const v = latestSelect ? 'select' : 'comment';
        const text = (v === 'select' ? o.label : 'Selected: ' + o.label) + (n ? '\n\n' + n : '');
        submitStripDecision(id, v, text, item);
      });
      mountOption(b, o);
    }
  }
  submitBtn.addEventListener('click', () => {
    const text = (ta.value || '').trim();
    if (!text) { ta.focus(); return; }
    submitStripDecision(id, opts.some(o => o.id === 'changes') ? 'changes' : 'comment', text, item);
  });

  // Free-text answer. A reviewer reply on an unanswered card also answers it.
  if (!opts.some(o => o.id === 'comment') && !entry.decisionVerdict) {
    const sayRow = document.createElement('div');
    sayRow.className = 'annotate-decision-say-row';
    const sayBtn = document.createElement('button');
    sayBtn.type = 'button';
    sayBtn.className = 'annotate-decision-say';
    sayBtn.textContent = '💬 Answer in words';
    sayBtn.title = 'Answer this question in your own words';
    const sayHint = document.createElement('span');
    sayHint.className = 'annotate-decision-say-hint';
    sayHint.textContent = 'counts as answered';
    sayRow.appendChild(sayBtn);
    sayRow.appendChild(sayHint);
    item.appendChild(sayRow);

    const sayForm = document.createElement('div');
    sayForm.className = 'annotate-decision-form';
    sayForm.style.setProperty('display', stripSayOpen[id] ? 'flex' : 'none', 'important');
    const sayTa = document.createElement('textarea');
    sayTa.className = 'annotate-decision-ta';
    sayTa.rows = 2;
    sayTa.placeholder = 'Answer in your own words…';
    sayTa.value = stripSayText[id] || '';
    sayTa.addEventListener('input', () => { stripSayText[id] = sayTa.value; });
    const saySubmit = makeStripBtn('Send answer', 'annotate-decision-submit');
    sayTa.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        saySubmit.click();
      }
    });
    saySubmit.addEventListener('click', () => {
      const text = (sayTa.value || '').trim();
      if (!text) { sayTa.focus(); return; }
      submitStripDecision(id, 'comment', text, item);
    });
    sayBtn.addEventListener('click', () => {
      stripSayOpen[id] = !stripSayOpen[id];
      sayForm.style.setProperty('display', stripSayOpen[id] ? 'flex' : 'none', 'important');
      if (stripSayOpen[id]) sayTa.focus();
    });
    sayForm.appendChild(sayTa);
    sayForm.appendChild(saySubmit);
    item.appendChild(sayForm);
  }

  // v2.19: evidence links → scroll + flash the referenced anchor in THIS
  // document (same scrollToAnchor path the shell's "Go to location" uses).
  const ev = Array.isArray(dr.evidence)
    ? dr.evidence.filter(e => e && typeof e === 'object' && typeof e.anchor === 'string' && e.anchor)
    : [];
  if (ev.length) {
    const row = document.createElement('div');
    row.className = 'annotate-decision-evidence';
    const lbl = document.createElement('span');
    lbl.className = 'annotate-decision-evidence-lbl';
    lbl.textContent = 'Evidence:';
    row.appendChild(lbl);
    for (const e of ev) {
      const a = document.createElement('button');
      a.type = 'button';
      a.className = 'annotate-decision-evidence-link';
      a.textContent = e.label || e.anchor;
      a.title = 'Scroll to ' + e.anchor;
      a.addEventListener('click', () => scrollToAnchor(e.anchor, null));
      row.appendChild(a);
    }
    item.appendChild(row);
  }

  // v2.19: optional note under Accept/Reject
  if (opts.some(o => o.id === 'accept' || o.id === 'reject')) {
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'annotate-decision-note-toggle';
    const noteForm = document.createElement('div');
    noteForm.className = 'annotate-decision-note-form';
    noteTa = document.createElement('textarea');
    noteTa.className = 'annotate-decision-ta';
    noteTa.rows = 2;
    noteTa.placeholder = 'Optional note sent with Accept / Reject…';
    noteTa.value = stripNoteText[id] || '';
    noteTa.addEventListener('input', () => { stripNoteText[id] = noteTa.value; });
    noteForm.appendChild(noteTa);
    const syncNote = () => {
      const open = !!stripNoteOpen[id];
      toggle.textContent = open ? '− Remove note' : '+ Add a note';
      toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
      noteForm.hidden = !open;
    };
    toggle.addEventListener('click', () => {
      stripNoteOpen[id] = !stripNoteOpen[id];
      if (!stripNoteOpen[id]) { noteTa.value = ''; delete stripNoteText[id]; }
      syncNote();
      if (stripNoteOpen[id]) noteTa.focus();
    });
    syncNote();
    item.appendChild(toggle);
    item.appendChild(noteForm);
  }

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
  const label = anchorName(anchorId);
  if (label && label !== anchorId) {
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
      font: 700 11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; letter-spacing: .02em; }
    .annotate-card-state.review { background: #FEF2F2; color: #DC2626; }
    .annotate-card-state.waiting { background: #F1F5F9; color: #64748B; }
    .annotate-card-state.done { background: #DCFCE7; color: #15803D; }
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

function renderDecisionStrips() {
  ensureStripStyle();
  document.querySelectorAll('[data-annotate-strip]').forEach(n => n.remove());

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
  }
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
      outline: 3px solid #F59E0B !important;
      outline-offset: 2px;
      background: rgba(245,158,11,.14) !important;
      border-radius: 4px;
      animation: gotoHighlightPulse 1.1s ease-in-out 2;
      transition: outline-color .3s, background .3s;
    }
    svg .goto-highlight-svg{ stroke:#F59E0B !important; stroke-width:3px !important; }
    @keyframes gotoHighlightPulse{
      0%,100%{ box-shadow: 0 0 0 0 rgba(245,158,11,.35); }
      50%{ box-shadow: 0 0 0 6px rgba(245,158,11,0); }
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

function scrollToAnchor(anchorId, target) {
  ensureGotoHighlightStyle();
  const anchorEl = findAnchorEl(anchorId);
  if (!anchorEl) {
    window.parent.postMessage({ type: 'annotate:scroll-result', anchorId, found: false }, '*');
    return;
  }

  // Granular resolution: if the comment captured an inner target, scroll to
  // and highlight THAT element; degrade to the section anchor when the inner
  // target no longer resolves (structure changed) — never a wrong element.
  const inner = resolveInnerEl(anchorEl, target);
  const el = inner ? inner.el : anchorEl;

  // If inside hidden tab panels, switch the content doc's own tabs first.
  const switched = revealAnchor(el);

  setTimeout(() => {
    // Still not visible (unknown tab system, collapsed container, …):
    // report honestly instead of "scrolling" to an invisible element —
    // the shell renders "location unavailable in this version".
    if (!el.getClientRects().length) {
      window.parent.postMessage({ type: 'annotate:scroll-result', anchorId, found: false }, '*');
      return;
    }
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
    window.parent.postMessage({
      type: 'annotate:scroll-result',
      anchorId,
      found: true,
      resolved: inner ? inner.how : 'anchor',
    }, '*');
  }, switched ? 150 : 0);
}

// ── Bridge: listen for shell messages ────────────────────────────────
function wireBridge() {
  window.addEventListener('message', (e) => {
    const data = e.data || {};
    if (!data || typeof data !== 'object') return;
    if (data.type === 'annotate:scroll-to') {
      scrollToAnchor(data.anchorId, data.target || null);
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
      renderCardStates();
      renderBadges();
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
    window.parent.postMessage({ type: 'annotate:content-fullscreen', active }, '*');
  }
}

// ── Init ─────────────────────────────────────────────────────────
async function init() {
  wireClicks();
  wireBridge();
  installBadgeMutObs();
  wireHoverLinking();

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
    window.parent.postMessage({ type: 'annotate:ready', version: META.version }, '*');
    renderBadges();
  }));
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
})();
