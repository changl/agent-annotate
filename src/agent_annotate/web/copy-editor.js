// Copy stays in Delta form. Never export/render user HTML (Quill GHSA-v3m3-f69x-jf25).
(() => {
  'use strict';
  const FORMATS = ['bold', 'italic', 'underline', 'strike', 'code', 'link', 'header', 'list', 'blockquote', 'indent'];
  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }
  function button(label, action, style = 'btn-ghost') {
    const element = node('button', `btn btn-xs ${style}`, label);
    element.type = 'button';
    element.addEventListener('click', action);
    return element;
  }
  function safeLink(value) {
    if (typeof value !== 'string' || !value || /[\s\\\u0000-\u001f\u007f]/u.test(value)) return false;
    try {
      const parsed = new URL(value);
      return ['http:', 'https:', 'mailto:'].includes(parsed.protocol) &&
        !parsed.username && !parsed.password &&
        (parsed.protocol === 'mailto:' ? Boolean(parsed.pathname) && !parsed.host : Boolean(parsed.hostname));
    } catch { return false; }
  }
  function cleanDelta(delta, document = true) {
    if (!delta || !Array.isArray(delta.ops) || !delta.ops.length || delta.ops.length > 5000) throw new Error('Copy format is invalid.');
    let size = 0;
    const ops = delta.ops.map(op => {
      if (!op || typeof op.insert !== 'string' || !op.insert || Object.keys(op).some(key => !['insert', 'attributes'].includes(key))) throw new Error('Only formatted text is supported.');
      size += op.insert.length;
      const attributes = {};
      Object.entries(op.attributes || {}).forEach(([key, value]) => {
        if (!FORMATS.includes(key)) throw new Error('Unsupported copy formatting.');
        if (['bold', 'italic', 'underline', 'strike', 'code', 'blockquote'].includes(key) && value !== true) throw new Error('Unsupported copy formatting.');
        if (key === 'header' && ![1, 2, 3].includes(value)) throw new Error('Unsupported heading.');
        if (key === 'list' && !['ordered', 'bullet'].includes(value)) throw new Error('Unsupported list.');
        if (key === 'indent' && ![1, 2, 3, 4].includes(value)) throw new Error('Unsupported indentation.');
        if (key === 'link' && !safeLink(value)) throw new Error('Links must use HTTP, HTTPS, or mailto.');
        attributes[key] = value;
      });
      return {insert: op.insert, ...(Object.keys(attributes).length ? {attributes} : {})};
    });
    if (size > 50000 || (document && !ops[ops.length - 1].insert.endsWith('\n'))) throw new Error('Copy is too long or incomplete.');
    return {ops};
  }
  function clipboardText(_element, delta) {
    // Quill handles clipboard/undo. Drop unsupported embeds and unsafe attributes.
    const ops = delta.ops.filter(op => typeof op.insert === 'string').map(op => {
      const attributes = {};
      Object.entries(op.attributes || {}).forEach(([key, value]) => {
        try { cleanDelta({ops:[{insert:'x', attributes:{[key]:value}}]}, false); attributes[key] = value; } catch {}
      });
      return {insert:op.insert, ...(Object.keys(attributes).length ? {attributes} : {})};
    });
    return new (Quill.import('delta'))(ops);
  }
  function view(parent, delta, label) {
    const container = node('div', 'copy-document');
    parent.append(container);
    const quill = new Quill(container, {theme:'snow', readOnly:true, formats:FORMATS, modules:{toolbar:false}});
    quill.setContents(cleanDelta(delta), 'silent');
    quill.root.setAttribute('aria-label', label);
    quill.root.removeAttribute('tabindex');
    container.querySelectorAll('a').forEach(link => { link.rel = 'noopener noreferrer'; });
  }
  function who(revision) {
    return revision.author.name || (revision.author.id.startsWith('agent:') ? 'Agent' : revision.author.id.startsWith('reviewer:') ? 'Reviewer' : revision.author.id);
  }
  function when(revision) {
    const date = new Date(revision.created_at);
    return Number.isNaN(date.valueOf()) ? '' : date.toLocaleString();
  }

  async function mount(root, options = {}) {
    if (!root || typeof Quill === 'undefined') throw new Error('Copy editor is unavailable.');
    root.classList.add('annotate-copy');
    const request = options.fetch || window.fetch.bind(window);
    const api = new URL('api/copy', options.apiBase ? new URL(options.apiBase, document.baseURI) : document.baseURI);
    const identity = options.identity || {};
    const viewer = identity.email || identity.id || 'reviewer';
    const draftPrefix = `annotate:copy:${location.pathname}:${viewer}:`;
    let selected;
    try { selected = localStorage.getItem(draftPrefix + ':selected'); } catch {}
    let destroyed = false;
    function draftRead(id) {
      try {
        const draft = JSON.parse(localStorage.getItem(draftPrefix + id) || 'null');
        if (draft) cleanDelta(draft.delta);
        return draft;
      } catch { return null; }
    }
    function draftWrite(id, value) {
      try {
        if (value) localStorage.setItem(draftPrefix + id, JSON.stringify(value));
        else localStorage.removeItem(draftPrefix + id);
        return true;
      } catch { return false; }
    }
    async function responseJson(response) {
      let result;
      try { result = await response.json(); } catch { throw new Error('Could not read the response. Your draft is kept.'); }
      if (!response.ok) throw new Error(result.error || 'Could not save. Your draft is kept; try again.');
      return result;
    }
    function render(data) {
      if (!Array.isArray(data.blocks)) throw new Error('Copy response is invalid.');
      root.replaceChildren();
      if (!data.blocks.length) { root.append(node('p', 'copy-empty', 'No copy blocks yet.')); return; }
      const layout = node('div', 'copy-layout');
      const navigation = node('aside', 'copy-nav');
      const search = node('input', 'copy-search input input-sm');
      search.type = 'search'; search.placeholder = 'Find copy…'; search.setAttribute('aria-label', 'Find copy');
      const list = node('div', 'copy-block-list');
      const picker = node('select', 'copy-block-picker select select-sm');
      picker.setAttribute('aria-label', 'Copy block');
      const detail = node('div', 'copy-detail');
      navigation.append(search, picker, list); layout.append(navigation, detail); root.append(layout);
      function select(id) {
        selected = id;
        try { localStorage.setItem(draftPrefix + ':selected', id); } catch {}
        list.querySelectorAll('button').forEach(item => item.setAttribute('aria-current', String(item.dataset.id === id)));
        picker.value = id;
        detail.replaceChildren();
        renderBlock(data.blocks.find(block => block.id === id));
      }
      function filter() {
        const query = search.value.trim().toLowerCase();
        const blocks = data.blocks.filter(block => `${block.title} ${block.id}`.toLowerCase().includes(query));
        list.replaceChildren(); picker.replaceChildren();
        for (const block of blocks) {
          const item = button(block.title, () => select(block.id));
          item.dataset.id = block.id; item.title = block.title; item.setAttribute('aria-current', String(block.id === selected));
          list.append(item);
          const option = node('option', '', block.title); option.value = block.id; picker.append(option);
        }
        picker.value = selected;
        if (!blocks.length) list.append(node('p', 'copy-empty', 'No matching copy.'));
      }
      search.addEventListener('input', filter);
      picker.addEventListener('change', () => select(picker.value));
      filter();
      select(data.blocks.some(block => block.id === selected) ? selected : data.blocks[0].id);
      function renderBlock(block) {
        const current = block.revisions.find(revision => revision.id === block.current);
        if (!current) throw new Error('Current copy revision is missing.');
        const card = node('section', 'copy-block');
        card.dataset.copyBlock = block.id;
        const header = node('div', 'copy-block-head');
        header.append(node('h2', '', block.title), node('span', 'badge badge-xs badge-neutral', current.status === 'approved' ? 'approved' : 'draft'));
        card.append(header);
        view(card, current.delta, `${block.title}: current copy`);
        const latest = [...block.revisions].reverse().find(revision => revision.status === 'proposed' && revision.id !== block.current);
        if (latest) {
          const proposal = node('details', 'copy-proposal');
          const summary = node('summary', '', `Proposed by ${who(latest)}`);
          summary.title = when(latest);
          proposal.append(summary);
          proposal.addEventListener('toggle', () => {
            if (proposal.open && !proposal.dataset.loaded) { view(proposal, latest.delta, `${block.title}: proposal`); proposal.dataset.loaded = '1'; }
          });
          card.append(proposal);
        }
        const controls = node('div', 'copy-actions');
        const draft = draftRead(block.id);
        const revise = button(draft ? 'Continue draft' : 'Revise', () => openEditor());
        header.append(revise);
        const previous = block.revisions.filter(revision => revision.id !== block.current && (!latest || revision.id !== latest.id));
        if (previous.length) {
          const history = node('details', 'copy-history');
          history.append(node('summary', '', `History (${previous.length})`));
          history.addEventListener('toggle', () => {
            if (!history.open || history.dataset.loaded) return;
            history.dataset.loaded = '1';
            for (const revision of [...previous].reverse()) {
              const entry = node('details', 'copy-history-entry');
              const summary = node('summary', '', `${who(revision)} · ${when(revision)} · ${revision.status}`);
              entry.append(summary);
              entry.addEventListener('toggle', () => {
                if (entry.open && !entry.dataset.loaded) { view(entry, revision.delta, `${block.title}: previous revision`); entry.dataset.loaded = '1'; }
              });
              history.append(entry);
            }
          });
          controls.append(history);
        }
        card.append(controls);
        detail.append(card);
        let editing = false;
        function openEditor() {
          if (editing) return;
          editing = true;
          revise.hidden = true;
          const editorPanel = node('div', 'copy-edit');
          const toolbar = node('div', 'copy-toolbar');
          const editor = node('div', 'copy-editor');
          const status = node('p', 'copy-save-status');
          status.setAttribute('role', 'status');
          const actions = node('div', 'copy-edit-actions');
          editorPanel.append(toolbar, editor, actions, status);
          card.append(editorPanel);
          const quill = new Quill(editor, {theme:'snow', formats:FORMATS,
            modules:{toolbar:{container:toolbar}, history:{userOnly:true}, clipboard:{matchers:[[Node.ELEMENT_NODE, clipboardText]]}}});
          let editRange = {index:0,length:0};
          function formats() { return quill.getFormat(editRange.index, editRange.length); }
          function applyFormat(format, value) {
            quill.focus(); quill.setSelection(editRange.index, editRange.length, 'silent');
            quill.format(format, value, 'user');
          }
          // Native controls keep toolbar keyboard behavior and daisyUI appearance.
          const heading = node('select', 'select select-xs');
          heading.setAttribute('aria-label', 'Heading');
          for (const [value, label] of [['', 'Text'], ['1', 'H1'], ['2', 'H2'], ['3', 'H3']]) {
            const option = node('option', '', label); option.value = value; heading.append(option);
          }
          heading.addEventListener('change', () => applyFormat('header', heading.value ? Number(heading.value) : false));
          toolbar.append(heading);
          const formatButtons = [];
          for (const [format, label, title] of [['bold','B','Bold'], ['italic','I','Italic'], ['underline','U','Underline'], ['list','•','Bullet list'], ['blockquote','❝','Quote']]) {
            const toggle = button(label, () => {
              const value = format === 'list' ? (formats().list === 'bullet' ? false : 'bullet') : !formats()[format];
              applyFormat(format, value);
            });
            toggle.addEventListener('mousedown', event => event.preventDefault());
            toggle.title = title; toggle.setAttribute('aria-label', title); toggle.dataset.format = format;
            toolbar.append(toggle); formatButtons.push(toggle);
          }
          toolbar.append(button('↶', () => quill.history.undo()), button('↷', () => quill.history.redo()));
          toolbar.querySelectorAll('button').forEach(item => {
            if (item.textContent === '↶') { item.title = 'Undo'; item.setAttribute('aria-label', 'Undo'); }
            if (item.textContent === '↷') { item.title = 'Redo'; item.setAttribute('aria-label', 'Redo'); }
          });
          const base = latest && latest.author.id === viewer ? latest : current;
          let pending = draftRead(block.id) || {delta:base.delta, base_revision:base.id, request_id:crypto.randomUUID()};
          quill.setContents(cleanDelta(pending.delta), 'silent');
          quill.history.clear();
          quill.root.setAttribute('aria-label', `Edit ${block.title}`);
          quill.root.setAttribute('role', 'textbox');
          quill.root.setAttribute('aria-multiline', 'true');
          const linkEdit = node('span', 'copy-link-edit');
          linkEdit.hidden = true;
          const linkInput = node('input', 'input input-xs');
          linkInput.type = 'url'; linkInput.placeholder = 'https://…'; linkInput.setAttribute('aria-label', 'Link URL');
          linkEdit.append(linkInput, button('Apply', () => {
            if (!safeLink(linkInput.value)) { status.textContent = 'Use an HTTP, HTTPS, or mailto link.'; return; }
            applyFormat('link', linkInput.value); linkEdit.hidden = true;
          }), button('Remove', () => { applyFormat('link', false); linkEdit.hidden = true; }));
          toolbar.append(button('Link', () => {
            linkInput.value = formats().link || '';
            linkEdit.hidden = !linkEdit.hidden;
            if (!linkEdit.hidden) linkInput.focus();
          }), linkEdit);
          quill.on('selection-change', range => {
            // getFormat() with no range focuses Quill. Never steal focus from
            // the Link URL field while a browser is inserting its text.
            if (!range) return;
            editRange = {index:range.index,length:range.length};
            const currentFormats = formats();
            heading.value = String(currentFormats.header || '');
            formatButtons.forEach(item => item.setAttribute('aria-pressed', String(item.dataset.format === 'list' ? currentFormats.list === 'bullet' : Boolean(currentFormats[item.dataset.format]))));
          });
          quill.on('text-change', (_change, _previous, source) => {
            if (source !== 'user') return;
            pending = {...pending, delta:quill.getContents(), request_id:crypto.randomUUID()};
            status.textContent = draftWrite(block.id, pending) ? 'Draft kept in this browser.' : 'Browser storage is full. Keep this tab open until saved.';
          });
          const save = button('Propose change', async () => {
            save.disabled = true;
            quill.enable(false);
            status.textContent = 'Saving…';
            draftWrite(block.id, pending);
            try {
              const delta = cleanDelta(quill.getContents());
              const payload = {delta, base_revision:pending.base_revision, request_id:pending.request_id};
              const result = await responseJson(await request(new URL(`${encodeURIComponent(block.id)}/proposal`, api.href + '/'), {
                method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)}));
              if (!result.blocks?.find(item => item.id === block.id)?.revisions.some(revision => revision.id === 'r_' + pending.request_id)) throw new Error('Save was not confirmed. Your draft is kept; try again.');
              draftWrite(block.id, null);
              if (!destroyed) { render(result); root.querySelector(`[data-copy-block="${CSS.escape(block.id)}"] .copy-proposal`)?.setAttribute('open',''); }
            } catch (error) {
              status.textContent = error.message || 'Could not save. Your draft is kept; try again.';
              save.disabled = false;
              quill.enable(true);
            }
          }, 'btn-primary');
          actions.append(save, button('Close', () => { editorPanel.remove(); editing = false; revise.hidden = false; revise.textContent = draftRead(block.id) ? 'Continue draft' : 'Revise'; }));
          quill.focus();
        }
      }
    }
    async function reload() {
      if (destroyed) return;
      if (!root.childElementCount) root.append(node('p', 'copy-empty', 'Loading copy…'));
      try {
        const data = await responseJson(await request(api, {cache:'no-store'}));
        if (!destroyed) render(data);
      } catch (error) {
        if (destroyed) return;
        root.replaceChildren(node('p', 'copy-load-error', error.message || 'Copy is unavailable.'), button('Retry', reload));
      }
    }
    await reload();
    return {reload, destroy() { destroyed = true; root.replaceChildren(); }};
  }
  window.AnnotateCopy = {mount};
})();
