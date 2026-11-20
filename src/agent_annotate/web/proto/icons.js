/* The prototype's one icon set: every glyph from round9/final/mock.html (ICON, KI, UI, IC, IC8), one per thing.
   16 px grid, Lucide-style strokes. Use Proto.icon(name) or Proto.icon(name, 'Accessible label'). */
(function () {
  const P = window.Proto = window.Proto || {};
  const link = '<path d="M6.5 9.5l3-3M7 4.5l1-1a2.5 2.5 0 0 1 3.5 3.5l-1 1M9 11.5l-1 1A2.5 2.5 0 0 1 4.5 8l1-1"/>';
  const reload = '<path d="M13 8a5 5 0 1 1-1.5-3.5"/><path d="M13 2.5v3h-3"/>';
  const edit = '<path d="M10.5 2.5l3 3L6 13H3v-3z"/><path d="M9 4l3 3"/>';
  const tick = '<path d="M3 8.5l3 3 7-7"/>';
  const page = '<path d="M4 1.5h5.5L12.5 4.5v10h-8.5z"/><path d="M9.5 1.5v3h3"/>';
  const I = P.ICONS = {
    /* tabs */
    q: '<circle cx="8" cy="8" r="6.5"/><path d="M6 6.2a2 2 0 1 1 2.8 1.8c-.5.3-.8.7-.8 1.3v.3"/><path d="M8 11.6v.2"/>',
    ref: '<path d="M2 3h4a2 2 0 0 1 2 2v8a1.5 1.5 0 0 0-1.5-1.5H2zM14 3h-4a2 2 0 0 0-2 2v8a1.5 1.5 0 0 1 1.5-1.5H14z"/>',
    run: '<path d="M1.5 8.5h3l1.5-4 3 8 1.5-4h4"/>',
    an: '<path d="M2 13.5h12"/><path d="M4 11V8M7 11V4.5M10 11V7M13 11V3"/>',
    hist: '<circle cx="8" cy="8" r="6.5"/><path d="M8 4.5V8l2.5 1.5"/>',
    pages: link,
    /* frame */
    home: '<path d="M2.5 7.5 8 3l5.5 4.5"/><path d="M4 6.5V13h3V9.5h2V13h3V6.5"/>',
    reload, bead: '<rect x="1.5" y="2.5" width="13" height="11" rx="1.5"/><path d="M6 2.5v11M10.5 2.5v11"/><path d="M3 5h1.5M7.5 5h1.5M7.5 7h1.5M12 5h1"/>',
    idle: '<circle cx="8" cy="8" r="5.5"/><path d="M5.5 8h5"/>',
    keys: '<rect x="1.5" y="4" width="13" height="8" rx="1.5"/><path d="M4 6.5h1M7 6.5h1M10 6.5h2M4.5 9.5h7"/>',
    people: '<circle cx="6" cy="5.5" r="2.3"/><path d="M1.8 13c.4-2.3 2.1-3.6 4.2-3.6s3.8 1.3 4.2 3.6"/><circle cx="11.5" cy="6" r="1.8"/><path d="M11.5 9.4c1.6 0 2.7 1 3 2.6"/>',
    out: '<path d="M6 2.5H3.5a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1H6"/><path d="M10 5l3 3-3 3M13 8H6"/>',
    agent: '<rect x="3" y="5" width="10" height="8" rx="2"/><path d="M8 5V2.5M6 9h.01M10 9h.01"/>',
    sun: '<circle cx="8" cy="8" r="2.8"/><path d="M8 1.5v1.6M8 12.9v1.6M1.5 8h1.6M12.9 8h1.6M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M3.4 12.6l1.1-1.1M11.5 4.5l1.1-1.1"/>',
    moon: '<path d="M13.5 9.5A5.5 5.5 0 1 1 6.5 2.5a4.5 4.5 0 0 0 7 7z"/>',
    sys: '<circle cx="8" cy="8" r="5.8"/><path d="M8 2.2a5.8 5.8 0 0 1 0 11.6z" fill="currentColor"/>',
    menu: '<path d="M2.5 4h11M2.5 8h11M2.5 12h11"/>',
    /* actions */
    link, copied: tick, tick, edit,
    undo: '<path d="M5.5 3.5L2.5 6.5l3 3"/><path d="M2.5 6.5H10a3.5 3.5 0 0 1 0 7H7"/>',
    copy: '<rect x="5.5" y="5.5" width="8" height="8" rx="1.5"/><path d="M10.5 5.5V3.5a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2"/>',
    later: '<circle cx="8" cy="8" r="6.5"/><path d="M8 4.5V8h3"/>',
    reply: '<path d="M2.5 3.5h11v7.5h-6l-3 2.5V11h-2z"/>',
    more: '<circle cx="3.5" cy="8" r=".6"/><circle cx="8" cy="8" r=".6"/><circle cx="12.5" cy="8" r=".6"/>',
    list: '<path d="M5.5 4h8M5.5 8h8M5.5 12h8"/><circle cx="2.5" cy="4" r=".5"/><circle cx="2.5" cy="8" r=".5"/><circle cx="2.5" cy="12" r=".5"/>',
    place: '<path d="M8 14.5s-4.5-4.2-4.5-7.5a4.5 4.5 0 0 1 9 0c0 3.3-4.5 7.5-4.5 7.5z"/><circle cx="8" cy="7" r="1.6"/>',
    block: '<circle cx="8" cy="8" r="6.5"/><path d="M3.5 12.5l9-9"/>',
    task: '<rect x="2.5" y="2.5" width="11" height="11" rx="2"/><path d="M5.5 8l2 2 3.5-4"/>',
    send: '<path d="M14 2L7 9M14 2l-4.5 12L7 9 2 6.5z"/>',
    archive: '<rect x="1.5" y="2.5" width="13" height="3.5" rx="1"/><path d="M2.5 6v6.5a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1V6M6.5 9h3"/>',
    expand: '<path d="M4.5 10.5 8 14l3.5-3.5M4.5 5.5 8 2l3.5 3.5"/>',
    collapse: '<path d="M4.5 14 8 10.5l3.5 3.5M4.5 2 8 5.5 11.5 2"/>',
    colans: '<path d="M1 8.2l1.8 1.8L6.2 6.4"/><path d="M8.5 14l3-3 3 3M8.5 2l3 3 3-3"/>',
    combine: '<path d="M3 14.5l5-5.5V1.5M13 14.5l-3.2-3.5M5 4.5l3-3 3 3"/>',
    chev: '<path d="M6 3.5L10.5 8 6 12.5"/>', up: '<path d="M4 10l4-4 4 4"/>', down: '<path d="M4 6l4 4 4-4"/>',
    ext: '<path d="M6 3H3v10h10v-3M9 2h5v5M14 2L7 9"/>',
    eye: '<path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z"/><circle cx="8" cy="8" r="2"/>',
    x: '<path d="M4 4l8 8M12 4l-8 8"/>', plus: '<path d="M8 3v10M3 8h10"/>',
    trash: '<path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.7 9h5.6l.7-9"/>',
    key: '<circle cx="5.5" cy="10.5" r="3"/><path d="M7.7 8.3l5.8-5.8M11.3 4.7l1.6 1.6"/>',
    warn: '<path d="M8 2l6.5 11.5h-13z"/><path d="M8 6.5v3M8 11.5v.1"/>',
    /* reference kinds */
    doc: '<path d="M4 1.5h5.5L13 5v9.5H4z"/><path d="M9.5 1.5V5H13M6 8h5M6 10.5h5M6 13h3"/>',
    plan: '<path d="M4 1.5h5.5L12.5 4.5v10h-8.5z"/><path d="M9.5 1.5v3h3M6 8h4.5M6 10.5h4.5"/>',
    check: '<path d="M2 3.5l1.2 1.2L5.5 2.5M2 8.5l1.2 1.2 2.3-2.2M2 13.5l1.2 1.2 2.3-2.2M8 4h6M8 9h6M8 14h6"/>',
    design: '<rect x="1.5" y="2.5" width="13" height="11" rx="1.5"/><circle cx="5.5" cy="6" r="1.3"/><path d="M1.5 12l4-4 3 3 2-2 4 4"/>',
    text: '<path d="M2 13L5.5 3 9 13M3.3 9.5h4.4M10.5 8.5c.5-1 1.3-1.5 2.2-1.5 1.2 0 1.8.8 1.8 2v4M14.5 10.5c-2.6 0-4 .5-4 1.7 0 .8.6 1.3 1.5 1.3 1.4 0 2.5-1 2.5-2.5"/>',
    data: '<rect x="1.5" y="2.5" width="13" height="11" rx="1"/><path d="M1.5 6.5h13M1.5 10h13M6 2.5v11"/>',
    flow: '<rect x="1.5" y="1.5" width="5" height="3.5" rx="1"/><rect x="9.5" y="6.25" width="5" height="3.5" rx="1"/><rect x="1.5" y="11" width="5" height="3.5" rx="1"/><path d="M6.5 3.25h1.5v4.75h1.5M6.5 12.75h1.5V8"/>',
    mem: '<circle cx="8" cy="2.8" r="1.5"/><circle cx="3.5" cy="13" r="1.5"/><circle cx="8" cy="13" r="1.5"/><circle cx="12.5" cy="13" r="1.5"/><path d="M8 4.3v7.2M8 7.5H3.5v4M8 7.5h4.5v4"/>',
    report: '<path d="M2 14.5h12M4 12V8M7 12V4M10 12V6.5M13 12V2.5"/>',
    /* document files: Markdown is the landscape "M↓" mark, never a page, so it cannot pass for Word (his v14 note) */
    'file-md': '<rect x="1" y="3.5" width="14" height="9" rx="1.5"/><path d="M3.5 10.5v-5l2 2.5 2-2.5v5M11.5 5.5v5M9.8 8.8l1.7 1.7 1.7-1.7"/>',
    'file-word': page + '<path d="M5.6 7.5l1 4 1.4-3 1.4 3 1-4"/>',
    'file-pdf': page + '<rect x="5" y="8" width="5.5" height="3.5" rx=".5"/>',
    'file-sheet': '<rect x="1.5" y="2.5" width="13" height="11" rx="1"/><path d="M1.5 6.5h13M1.5 10h13M6 2.5v11"/>',
    'file-video': '<rect x="1.5" y="3" width="13" height="10" rx="1.5"/><path d="M6.5 6v4l3.5-2z"/>',
    /* running */
    merge: '<path d="M3 2v3.5a3 3 0 0 0 3 3h4M13 2v3.5a3 3 0 0 1-3 3M8 8.5V14M5.5 11.5L8 14l2.5-2.5"/>',
    loop: '<path d="M13 6.5A5 5 0 0 0 3.6 5M3 9.5A5 5 0 0 0 12.4 11M3.5 2v3h3M12.5 14v-3h-3"/>',
    branch: '<circle cx="4" cy="3" r="1.5"/><circle cx="4" cy="13" r="1.5"/><circle cx="12" cy="6" r="1.5"/><path d="M4 4.5v7M12 7.5c0 3-8 2-8 4"/>',
    code: '<path d="M5.5 4L1.5 8l4 4M10.5 4l4 4-4 4"/>',
    ai: '<path d="M8 1.5l1.6 4.4 4.4 1.6-4.4 1.6L8 13.5 6.4 9.1 2 7.5l4.4-1.6z"/>',
    hand: '<path d="M5.5 8V3.5a1 1 0 0 1 2 0V7M7.5 7V2.5a1 1 0 0 1 2 0V7M9.5 7V3.5a1 1 0 0 1 2 0V9c0 2.5-1.5 4.5-4 4.5S4 12 3 10L2 8.2a1 1 0 0 1 1.7-1L5.5 9"/>',
    mac: '<rect x="2" y="2.5" width="12" height="8" rx="1"/><path d="M5.5 13.5h5M8 10.5v3"/>',
    term: '<path d="M2.5 3.5h11v9h-11z"/><path d="M5 7l2 1.5L5 10M8.5 10.5H11"/>',
    msg: '<path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z"/>',
    rerun: reload, pulse: '<path d="M1.5 8.5h3l1.5-4 3 8 1.5-4h4"/>',
    user: '<circle cx="8" cy="5.5" r="2.5"/><path d="M3 13.5c.5-2.5 2.5-4 5-4s4.5 1.5 5 4"/>',
  };
  I.note = I.pen = edit;  // the mock drew notes and pens with the edit pencil
  const esc = s => String(s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  P.icon = (name, label) => {
    const d = I[name];
    if (!d) console.warn('Proto.icon: no icon named', name);
    const a = label ? `role="img" aria-label="${esc(label)}"><title>${esc(label)}</title` : 'aria-hidden="true"';
    return `<svg class="pi pi-${esc(name)}" viewBox="0 0 16 16" ${a}>${d || '<circle cx="8" cy="8" r="6"/>'}</svg>`;
  };
})();
