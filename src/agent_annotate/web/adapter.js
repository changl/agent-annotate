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

function cssEsc(s) {
  return String(s).replace(/(["\\\[\]\(\)])/g, '\\$1');
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
      if (el2.closest('#badge-layer') || el2.classList.contains('bpin-inline') || el2.tagName === 'SCRIPT' || el2.tagName === 'STYLE') return;
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
  `;
  document.head.appendChild(style);
}

const PIN_BASE_CSS = 'width:18px;height:18px;color:#FFF;border-radius:50%;font-size:10px;font-weight:700;display:flex;align-items:center;justify-content:center;box-shadow:0 1px 4px rgba(0,0,0,.25);background:#4338CA';

// Build one pin element. `entries` = the comment(s) this pin represents
// ([{id, n, unread}]); a single-comment pin shows its number, a cluster pin
// shows the count. Clicking either sends 'annotate:pin-open' (see wireClicks).
function makePin(anchorId, entries, isCluster) {
  const b = document.createElement('div');
  b.style.cssText = PIN_BASE_CSS;
  b.dataset.pinAnchor = anchorId;
  b.dataset.pinComments = entries.map(x => x.id).join(',');
  if (isCluster) {
    b.classList.add('bpin-cluster');
    b.textContent = String(entries.length);
    b.title = anchorName(anchorId) + ': ' + entries.length + ' comments (#' +
      entries.map(x => x.n).join(', #') + ') — click to view';
  } else {
    b.textContent = String(entries[0].n);
    if (entries[0].unread) b.classList.add('bpin-unread');
    b.title = anchorName(anchorId) + ': comment #' + entries[0].n +
      (entries[0].unread ? ' (unread)' : '') + ' — click to view';
  }
  return b;
}

// Legacy comments without granular targets stay grouped at the anchor corner:
// up to 3 numbered pins, then a cluster. If any comment on the anchor has a
// creation-time target, keep the comments individually numbered so each new
// pin can live at its own clicked position inside the larger box.
const PIN_SPACING = 20;
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
  return {
    left: rect.right - wrapperRect.left,
    top: rect.top - wrapperRect.top,
    granular: false,
  };
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

      if (point.granular) {
        // Two clicks can resolve to effectively the same pixel. Nudge later
        // numbers sideways instead of hiding them under the first pin.
        const key = Math.round(point.left / 8) + ':' + Math.round(point.top / 8);
        const collisionIndex = occupied.get(key) || 0;
        occupied.set(key, collisionIndex + 1);
        b.style.left = (point.left + collisionIndex * PIN_SPACING) + 'px';
        b.style.top = point.top + 'px';
        b.style.transform = 'translate(-50%,-50%)';
      } else {
        b.style.left = (point.left - (specs.length - 1 - i) * PIN_SPACING) + 'px';
        b.style.top = point.top + 'px';
        b.style.transform = 'translate(0,-100%)';
      }
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
  style.textContent = `
    .canvas-wrapper { max-width: 100% !important; min-width: 0 !important; }
    body > .canvas-wrapper { max-width: 100vw !important; }
    .canvas-area { max-width: 100% !important; min-width: 0 !important; }
    .er-container { max-width: 100% !important; }
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

  window.addEventListener('resize', scheduleBadgeRefresh);
  window.addEventListener('resize', scheduleScrollLockRecheck);
  window.addEventListener('scroll', scheduleBadgeRefresh);

  ensureContentScrollContractStyle();
  await mountContentDiagrams();
  ensureGeometryFixStyle();
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
