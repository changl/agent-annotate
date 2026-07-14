/**
 * diagram-plot.js — AnnotateDiagrams namespace for annotate skill v2.1
 *
 * Renders interactive Observable Plot-based domain/entity diagrams
 * inside annotatable HTML artifacts. Each rendered SVG element carries
 * `data-anchor-id` so the existing annotate click-handler picks it up.
 *
 * Requires (template.html injects both — order matters, d3 first):
 *   <script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"></script>
 *   <script src="https://cdn.jsdelivr.net/npm/@observablehq/plot@0.6.16/dist/plot.umd.min.js"></script>
 *
 * Why Plot + d3 (not d3-only): Plot gives concise, declarative spec for
 * dot/text/arrow layers; d3 stays available globally for escape-hatch
 * layouts (force, hierarchy, zoom) — see renderForceGraph TODO at bottom.
 *
 * Spec shape:
 *   {
 *     id:    "schema-v3",            // optional, prefixed into anchor ids
 *     width: 1200,                   // optional
 *     height: 700,                   // optional
 *     nodes: [
 *       { id: "person", label: "person", kind: "hub", x: 100, y: 80,
 *         anchorId: "dgm:schema:node:person", description: "..." }
 *     ],
 *     edges: [
 *       { from: "person", to: "person_company", kind: "fk", label: "M:N" }
 *     ],
 *     legend: [
 *       { kind: "hub",    label: "Hub table" },
 *       { kind: "subtype", label: "Subtype / join" }
 *     ]
 *   }
 *
 * Node kinds → fill colors:
 *   hub         #4338CA  indigo
 *   subtype     #0891B2  cyan
 *   sidecar     #7C3AED  purple
 *   catalog     #059669  emerald
 *   derivation  #D97706  amber
 *   audit       #64748B  slate
 *   tooling     #0F766E  teal
 *
 * Edge kinds:
 *   fk       solid arrow
 *   ref      dashed arrow
 *   m2m      solid line, diamond on source side (rendered via Plot.arrow w/ short head)
 *   inherit  solid line, open-triangle head
 */

(function (global) {
  'use strict';

  // ── Palette ───────────────────────────────────────────────────────
  const KIND_FILL = {
    hub:        '#4338CA',
    subtype:    '#0891B2',
    sidecar:    '#7C3AED',
    catalog:    '#059669',
    derivation: '#D97706',
    audit:      '#64748B',
    tooling:    '#0F766E',
  };
  const KIND_ORDER = ['hub', 'subtype', 'sidecar', 'catalog', 'derivation', 'audit', 'tooling'];
  const DEFAULT_FILL = '#94A3B8';

  function kindFill(kind) {
    return KIND_FILL[kind] || DEFAULT_FILL;
  }

  // ── Geometry helpers ──────────────────────────────────────────────
  const NODE_W = 140;
  const NODE_H = 48;

  // Compute padded x/y extents for the spec
  function _extents(nodes) {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const n of nodes) {
      if (n.x < minX) minX = n.x;
      if (n.y < minY) minY = n.y;
      if (n.x > maxX) maxX = n.x;
      if (n.y > maxY) maxY = n.y;
    }
    if (!isFinite(minX)) { minX = 0; minY = 0; maxX = 600; maxY = 400; }
    return {
      minX: minX - 80,
      minY: minY - 60,
      maxX: maxX + NODE_W + 80,
      maxY: maxY + NODE_H + 60,
    };
  }

  // Auto-place nodes missing x/y on a coarse grid
  function _autoLayout(nodes) {
    let col = 0, row = 0;
    const GRID_CX = 200, GRID_CY = 110;
    for (const n of nodes) {
      if (n.x == null || n.y == null) {
        n.x = 80 + col * GRID_CX;
        n.y = 80 + row * GRID_CY;
        col++;
        if (col > 5) { col = 0; row++; }
      }
    }
  }

  // Box-edge intersection — line from (cx,cy) to box-center, return point on box border closest to (cx,cy)
  function _boxIntersect(fromX, fromY, bx, by, bw, bh) {
    const hw = bw / 2, hh = bh / 2;
    const mx = bx + hw, my = by + hh;
    const dx = fromX - mx, dy = fromY - my;
    if (dx === 0 && dy === 0) return { x: mx, y: my };
    const scaleX = dx !== 0 ? hw / Math.abs(dx) : Infinity;
    const scaleY = dy !== 0 ? hh / Math.abs(dy) : Infinity;
    const scale = Math.min(scaleX, scaleY);
    return { x: mx + dx * scale, y: my + dy * scale };
  }

  // Compute edge endpoint segments for Plot.link (one segment per edge)
  function _edgeSegments(edges, nodeMap) {
    const segs = [];
    edges.forEach((edge, idx) => {
      const src = nodeMap[edge.from];
      const tgt = nodeMap[edge.to];
      if (!src || !tgt) return;
      const sx0 = src.x + NODE_W / 2, sy0 = src.y + NODE_H / 2;
      const tx0 = tgt.x + NODE_W / 2, ty0 = tgt.y + NODE_H / 2;
      const s = _boxIntersect(tx0, ty0, src.x, src.y, NODE_W, NODE_H);
      const t = _boxIntersect(sx0, sy0, tgt.x, tgt.y, NODE_W, NODE_H);
      segs.push({
        idx,
        x1: s.x, y1: s.y, x2: t.x, y2: t.y,
        kind: edge.kind || 'fk',
        label: edge.label || '',
        from: edge.from, to: edge.to,
        anchorId: edge.anchorId || null,
      });
    });
    return segs;
  }

  // ── Render: domain map ────────────────────────────────────────────
  /**
   * renderDomainMap(container, spec)
   *
   * @param {HTMLElement|string} container  DOM element or CSS selector
   * @param {Object} spec
   * @returns {SVGElement} the rendered svg
   */
  function renderDomainMap(container, spec) {
    if (typeof container === 'string') container = document.querySelector(container);
    if (!container) {
      console.error('[AnnotateDiagrams] container not found');
      return null;
    }
    if (typeof Plot === 'undefined') {
      console.error('[AnnotateDiagrams] Observable Plot is not loaded');
      return null;
    }
    if (typeof d3 === 'undefined') {
      console.error('[AnnotateDiagrams] d3 is not loaded (Plot depends on it)');
      return null;
    }

    container.innerHTML = '';

    const nodes = (spec.nodes || []).map(n => ({ ...n }));
    const edges = spec.edges || [];
    const legend = spec.legend || [];
    const specId = spec.id || 'schema';

    _autoLayout(nodes);

    // node lookup
    const nodeMap = {};
    nodes.forEach(n => { nodeMap[n.id] = n; });

    // pre-compute anchorIds (so SVG path nodes can carry them)
    nodes.forEach(n => {
      if (!n.anchorId) n.anchorId = `dgm:${specId}:node:${n.id}`;
    });

    const segs = _edgeSegments(edges, nodeMap);
    segs.forEach(s => {
      if (!s.anchorId) s.anchorId = `dgm:${specId}:edge:${s.idx}`;
    });

    const ext = _extents(nodes);
    const svgW = spec.width || Math.max(ext.maxX - ext.minX, 600);
    const svgH = spec.height || Math.max(ext.maxY - ext.minY, 400);

    // Build Plot marks. Order: edges (lines) below nodes.
    const marks = [];

    // 1. Frame
    marks.push(Plot.frame({
      stroke: '#E2E8F0',
      strokeWidth: 1,
      rx: 6,
    }));

    // 2. Edges as Plot.link — keep this minimal so Plot's marker/SVG
    //    plumbing isn't fought. We annotate per-edge attributes
    //    (data-anchor-id, dash, marker) in a post-Plot d3 step below.
    marks.push(Plot.link(segs, {
      x1: 'x1', y1: 'y1', x2: 'x2', y2: 'y2',
      stroke: '#CBD5E1',
      strokeWidth: 1.5,
    }));

    // 3. Edge labels (white background rect would be nice but Plot.text is fine)
    const labelSegs = segs.filter(s => s.label);
    if (labelSegs.length) {
      marks.push(Plot.text(labelSegs, {
        x: (d) => (d.x1 + d.x2) / 2,
        y: (d) => (d.y1 + d.y2) / 2,
        text: 'label',
        fontSize: 9,
        fill: '#64748B',
        stroke: 'white',
        strokeWidth: 3,
        paintOrder: 'stroke',
      }));
    }

    // 4. Nodes — drawn via a custom Plot mark (Plot.marks(...) doesn't fight
    //    the reconciler the way a render override on Plot.dot does). We use
    //    a "null" mark that yields an empty <g>, then append boxes in a
    //    separate post-Plot d3 step (see below).

    const plotEl = Plot.plot({
      width: svgW,
      height: svgH,
      x: { domain: [ext.minX, ext.maxX], axis: null },
      // y domain ordered low→high makes Plot place ext.minY at the TOP of
      // the SVG (since Plot inverts y for SVG); spec coords are already
      // top-down (y=0 at top, y grows downward), so this lines up.
      y: { domain: [ext.minY, ext.maxY], axis: null, reverse: true },
      margin: 0,
      style: { background: 'transparent', fontFamily: "'Helvetica Neue', -apple-system, sans-serif" },
      marks,
    });

    // Inject SVG <defs> for arrow / inherit / diamond markers
    const svg = plotEl.tagName === 'svg' || plotEl.tagName === 'SVG'
      ? plotEl
      : plotEl.querySelector('svg');
    if (svg) {
      _ensureMarkers(svg);
    }

    container.appendChild(plotEl);

    // ── Annotate edge paths post-Plot ─────────────────────────────
    // Plot.link emits one <path> per datum (under g[aria-label="link"])
    // in document order. Map each path back to its `seg` by index and
    // apply data-anchor-id, dash, and marker-end based on edge kind.
    if (svg) {
      const linkG = svg.querySelector('g[aria-label="link"]');
      if (linkG) {
        const edgePaths = Array.from(linkG.querySelectorAll('path'));
        edgePaths.forEach((el, i) => {
          const s = segs[i];
          if (!s) return;
          if (s.anchorId) el.setAttribute('data-anchor-id', s.anchorId);
          el.style.cursor = 'pointer';
          if (s.kind === 'ref') el.setAttribute('stroke-dasharray', '5,3');
          if (s.kind === 'inherit') {
            el.setAttribute('marker-end', 'url(#annotate-inherit)');
            el.setAttribute('stroke', '#94A3B8');
          } else {
            el.setAttribute('marker-end', 'url(#annotate-arrow)');
          }
          if (s.kind === 'm2m') el.setAttribute('marker-start', 'url(#annotate-diamond)');
        });
      }
    }

    // ── Draw nodes post-Plot (avoids fighting the reconciler) ─────
    // Plot's SVG uses its own internal pixel coordinate system equal to
    // the viewBox. Since width/height/margin are explicit and we set
    // y.reverse=true, mapping from spec coordinates (top-down) to SVG
    // pixels is identity for the plot area's interior:
    //   px = (x - minX) / (maxX - minX) * svgW
    //   py = (y - minY) / (maxY - minY) * svgH
    if (svg) {
      const ns = 'http://www.w3.org/2000/svg';
      const xRange = ext.maxX - ext.minX || 1;
      const yRange = ext.maxY - ext.minY || 1;
      const xPx = (x) => ((x - ext.minX) / xRange) * svgW;
      const yPx = (y) => ((y - ext.minY) / yRange) * svgH;

      const nodeLayer = document.createElementNS(ns, 'g');
      nodeLayer.setAttribute('class', 'annotate-plot-nodes');
      svg.appendChild(nodeLayer);

      nodes.forEach((n) => {
        const fill = kindFill(n.kind);
        const px = xPx(n.x);
        const py = yPx(n.y);

        const grp = document.createElementNS(ns, 'g');
        grp.setAttribute('class', 'annotate-plot-node annotate-kind-' + (n.kind || 'default'));
        grp.setAttribute('data-anchor-id', n.anchorId);
        grp.setAttribute('transform', `translate(${px},${py})`);
        grp.style.cursor = 'pointer';

        const rect = document.createElementNS(ns, 'rect');
        rect.setAttribute('width', String(NODE_W));
        rect.setAttribute('height', String(NODE_H));
        rect.setAttribute('rx', '8');
        rect.setAttribute('fill', '#FFFFFF');
        rect.setAttribute('stroke', fill);
        rect.setAttribute('stroke-width', '1.5');
        grp.appendChild(rect);

        const accent = document.createElementNS(ns, 'rect');
        accent.setAttribute('width', '4');
        accent.setAttribute('height', String(NODE_H));
        accent.setAttribute('rx', '2');
        accent.setAttribute('fill', fill);
        accent.style.pointerEvents = 'none';
        grp.appendChild(accent);

        // Two-line block (label 12px + kind 9px) centered in the 48px box:
        // line centers at 18 / 32 with dominant-baseline central. Raw
        // baseline y=20/34 sat the block ~2px above box center. text-anchor
        // must stay explicit on every <text>: Plot's root <svg> carries
        // text-anchor="middle", which inherits into appended text.
        // Long table names shrink to fit the fixed-width box (estimate
        // ~0.62em/char; getComputedTextLength is 0 in hidden tab panels).
        // Below the 8px legibility floor, truncate with an ellipsis and
        // keep the full name in the hover <title>.
        const labelText = n.label || n.id;
        let labelDisplay = labelText;
        let labelFs = 12;
        const labelAvail = NODE_W - 12;
        const labelEstW = labelText.length * labelFs * 0.62;
        if (labelEstW > labelAvail) {
          labelFs = Math.max(8, Math.round(labelFs * labelAvail / labelEstW * 10) / 10);
          const fitChars = Math.floor(labelAvail / (labelFs * 0.62));
          if (labelText.length > fitChars) {
            labelDisplay = labelText.slice(0, Math.max(1, fitChars - 1)) + '…';
          }
        }
        const label = document.createElementNS(ns, 'text');
        label.setAttribute('x', String(NODE_W / 2 + 2));
        label.setAttribute('y', '18');
        label.setAttribute('text-anchor', 'middle');
        label.setAttribute('dominant-baseline', 'central');
        label.setAttribute('font-size', String(labelFs));
        label.setAttribute('font-weight', '600');
        label.setAttribute('fill', '#0F172A');
        label.style.pointerEvents = 'none';
        label.textContent = labelDisplay;
        grp.appendChild(label);

        const sub = document.createElementNS(ns, 'text');
        sub.setAttribute('x', String(NODE_W / 2 + 2));
        sub.setAttribute('y', '32');
        sub.setAttribute('text-anchor', 'middle');
        sub.setAttribute('dominant-baseline', 'central');
        sub.setAttribute('font-size', '9');
        sub.setAttribute('fill', '#94A3B8');
        sub.style.pointerEvents = 'none';
        sub.textContent = n.kind || '';
        grp.appendChild(sub);

        if (n.description || labelDisplay !== labelText) {
          const t = document.createElementNS(ns, 'title');
          t.textContent = labelDisplay !== labelText
            ? (n.description ? labelText + '\n' + n.description : labelText)
            : n.description;
          grp.appendChild(t);
        }

        // Hover-highlight neighbor edges (edges are <path> under g[aria-label=link])
        grp.addEventListener('mouseenter', () => {
          rect.setAttribute('stroke-width', '2.5');
          svg.querySelectorAll('g[aria-label="link"] path[data-anchor-id]').forEach((el) => {
            const a = el.getAttribute('data-anchor-id') || '';
            const m = a.match(/edge:(\d+)/);
            if (!m) return;
            const seg = segs[Number(m[1])];
            if (!seg) return;
            if (seg.from === n.id || seg.to === n.id) {
              el.setAttribute('stroke', '#4338CA');
              el.setAttribute('stroke-width', '2.5');
            }
          });
        });
        grp.addEventListener('mouseleave', () => {
          rect.setAttribute('stroke-width', '1.5');
          svg.querySelectorAll('g[aria-label="link"] path[data-anchor-id]').forEach((el) => {
            el.setAttribute('stroke', '#CBD5E1');
            el.setAttribute('stroke-width', '1.5');
          });
        });

        nodeLayer.appendChild(grp);
      });
    }

    // ── Legend ────────────────────────────────────────────────────
    if (legend.length && svg) {
      const ns = 'http://www.w3.org/2000/svg';
      const legG = document.createElementNS(ns, 'g');
      legG.setAttribute('class', 'annotate-plot-legend');
      legG.setAttribute('transform', `translate(${svgW - 168}, 16)`);
      const bg = document.createElementNS(ns, 'rect');
      bg.setAttribute('width', '156');
      bg.setAttribute('height', String(legend.length * 22 + 24));
      bg.setAttribute('rx', '6');
      bg.setAttribute('fill', 'white');
      bg.setAttribute('stroke', '#E2E8F0');
      bg.setAttribute('stroke-width', '1');
      legG.appendChild(bg);
      const title = document.createElementNS(ns, 'text');
      title.setAttribute('x', '10');
      title.setAttribute('y', '17');
      title.setAttribute('text-anchor', 'start');
      title.setAttribute('font-size', '10');
      title.setAttribute('font-weight', '600');
      title.setAttribute('fill', '#64748B');
      title.textContent = 'LEGEND';
      legG.appendChild(title);
      legend.forEach((item, i) => {
        const gy = 26 + i * 22;
        const sw = document.createElementNS(ns, 'rect');
        sw.setAttribute('x', '10');
        sw.setAttribute('y', String(gy - 1));
        sw.setAttribute('width', '14');
        sw.setAttribute('height', '14');
        sw.setAttribute('rx', '3');
        sw.setAttribute('fill', kindFill(item.kind));
        legG.appendChild(sw);
        const tx = document.createElementNS(ns, 'text');
        tx.setAttribute('x', '30');
        tx.setAttribute('y', String(gy + 10));
        tx.setAttribute('text-anchor', 'start');
        tx.setAttribute('font-size', '10');
        tx.setAttribute('fill', '#475569');
        tx.textContent = item.label || item.kind;
        legG.appendChild(tx);
      });
      svg.appendChild(legG);
    }

    container._annotateDiagramSvg = svg;
    return svg;
  }

  // ── Marker defs ───────────────────────────────────────────────────
  function _ensureMarkers(svg) {
    const ns = 'http://www.w3.org/2000/svg';
    let defs = svg.querySelector('defs');
    if (!defs) {
      defs = document.createElementNS(ns, 'defs');
      svg.insertBefore(defs, svg.firstChild);
    }
    if (!svg.querySelector('#annotate-arrow')) {
      const m = document.createElementNS(ns, 'marker');
      m.setAttribute('id', 'annotate-arrow');
      m.setAttribute('viewBox', '0 -5 10 10');
      m.setAttribute('refX', '10');
      m.setAttribute('refY', '0');
      m.setAttribute('markerWidth', '8');
      m.setAttribute('markerHeight', '8');
      m.setAttribute('orient', 'auto');
      const p = document.createElementNS(ns, 'path');
      p.setAttribute('d', 'M0,-5L10,0L0,5');
      p.setAttribute('fill', '#94A3B8');
      m.appendChild(p);
      defs.appendChild(m);
    }
    if (!svg.querySelector('#annotate-inherit')) {
      const m = document.createElementNS(ns, 'marker');
      m.setAttribute('id', 'annotate-inherit');
      m.setAttribute('viewBox', '0 -6 12 12');
      m.setAttribute('refX', '12');
      m.setAttribute('refY', '0');
      m.setAttribute('markerWidth', '10');
      m.setAttribute('markerHeight', '10');
      m.setAttribute('orient', 'auto');
      const p = document.createElementNS(ns, 'path');
      p.setAttribute('d', 'M0,-6L12,0L0,6Z');
      p.setAttribute('fill', 'none');
      p.setAttribute('stroke', '#94A3B8');
      p.setAttribute('stroke-width', '1.5');
      m.appendChild(p);
      defs.appendChild(m);
    }
    if (!svg.querySelector('#annotate-diamond')) {
      const m = document.createElementNS(ns, 'marker');
      m.setAttribute('id', 'annotate-diamond');
      m.setAttribute('viewBox', '-6 -4 12 8');
      m.setAttribute('refX', '-6');
      m.setAttribute('refY', '0');
      m.setAttribute('markerWidth', '10');
      m.setAttribute('markerHeight', '8');
      m.setAttribute('orient', 'auto');
      const p = document.createElementNS(ns, 'path');
      p.setAttribute('d', 'M0,0L-5,-3L-10,0L-5,3Z');
      p.setAttribute('fill', 'none');
      p.setAttribute('stroke', '#94A3B8');
      p.setAttribute('stroke-width', '1.5');
      m.appendChild(p);
      defs.appendChild(m);
    }
  }

  // ── mountDiagrams: scan DOM for <!-- DIAGRAM:NAME --> ─────────────
  async function mountDiagrams() {
    const walker = document.createTreeWalker(
      document.body, NodeFilter.SHOW_COMMENT, null
    );
    const placeholders = [];
    let node;
    while ((node = walker.nextNode())) {
      const txt = (node.nodeValue || '').trim();
      const m = txt.match(/^DIAGRAM:([A-Za-z0-9_-]+)$/);
      if (m) placeholders.push({ comment: node, name: m[1] });
    }
    for (const { comment, name } of placeholders) {
      let spec = null;
      const inlineEl = document.getElementById('diagram-spec-' + name);
      if (inlineEl) {
        try { spec = JSON.parse(inlineEl.textContent); }
        catch (e) { console.warn('[AnnotateDiagrams] inline spec parse error for', name, e); }
      }
      if (!spec) {
        try {
          const r = await fetch('./' + name + '.json', { cache: 'no-store' });
          if (r.ok) spec = await r.json();
        } catch {}
      }
      if (!spec) {
        console.warn('[AnnotateDiagrams] no spec found for DIAGRAM:' + name);
        continue;
      }
      const host = document.createElement('div');
      host.className = 'annotate-diagram-host';
      host.dataset.diagramName = name;
      host.style.cssText = 'background:#fff;border:1px solid #E2E8F0;border-radius:8px;padding:16px;margin:12px 0;overflow-x:auto';
      comment.parentNode.replaceChild(host, comment);
      renderDomainMap(host, spec);
    }
  }

  // ── Public namespace ──────────────────────────────────────────────
  global.AnnotateDiagrams = {
    renderDomainMap,
    mountDiagrams,
    _kindFill: kindFill,
    _KIND_ORDER: KIND_ORDER,
  };

  // ── Escape hatch (NOT implemented) ────────────────────────────────
  // TODO(force-layout): implement renderForceGraph(container, spec) using
  // d3.forceSimulation for graphs where x/y are not pre-laid-out. Sketch:
  //
  //   const sim = d3.forceSimulation(nodes)
  //     .force('link', d3.forceLink(edges).id(d => d.id).distance(120))
  //     .force('charge', d3.forceManyBody().strength(-300))
  //     .force('center', d3.forceCenter(width/2, height/2));
  //   sim.on('tick', () => { /* update node g.transform + edge line endpoints */ });
  //   sim.on('end', () => { /* annotate svg paths/lines with data-anchor-id */ });

})(window);

/*
 * ── Usage example ────────────────────────────────────────────────────
 *
 * Annotatable HTML:
 *
 *   <!-- DIAGRAM:domain-map -->
 *
 *   <script type="application/json" id="diagram-spec-domain-map">
 *   {
 *     "id": "schema",
 *     "nodes": [
 *       { "id": "person",         "label": "person",         "kind": "hub",        "x": 100, "y": 80,
 *         "anchorId": "dgm:schema:node:person" },
 *       { "id": "company",        "label": "company",        "kind": "hub",        "x": 400, "y": 80 },
 *       { "id": "person_company", "label": "person_company", "kind": "subtype",    "x": 250, "y": 220 },
 *       { "id": "signal",         "label": "signal",         "kind": "sidecar",    "x": 400, "y": 220 },
 *       { "id": "lead",           "label": "lead",           "kind": "derivation", "x": 100, "y": 340 }
 *     ],
 *     "edges": [
 *       { "from": "person",  "to": "person_company", "kind": "fk",  "label": "M:N" },
 *       { "from": "company", "to": "person_company", "kind": "fk",  "label": "M:N" },
 *       { "from": "company", "to": "signal",         "kind": "fk",  "label": "1:N" },
 *       { "from": "lead",    "to": "person",         "kind": "ref", "label": "target" }
 *     ],
 *     "legend": [
 *       { "kind": "hub",        "label": "Hub table" },
 *       { "kind": "subtype",    "label": "Subtype / join" },
 *       { "kind": "sidecar",    "label": "Signal sidecar" },
 *       { "kind": "derivation", "label": "Derivation / lead" }
 *     ]
 *   }
 *   </script>
 *
 * Call after DOM ready (annotate skill init() does this):
 *   AnnotateDiagrams.mountDiagrams();
 *
 * Or directly:
 *   AnnotateDiagrams.renderDomainMap(document.getElementById('host'), spec);
 */
