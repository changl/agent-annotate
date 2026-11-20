/* Pages & links tab (#84): this project's pages, each with a Copy link icon that copies at once, no access check
   (#85, #147); repos and folders with Copy path (#86); a version that fails to load says why, with Retry and Tell
   the agent (#87, shared with History through Proto.viewVersion); People, with two roles (#128). No usage report
   and no other projects' documents. */
(function () {
  'use strict';
  const P = window.Proto = window.Proto || {};
  const S = {arch: false, view: '', copied: ''};
  const pl = (n, one, many) => `${Number(n).toLocaleString()} ${n === 1 ? one : many}`;
  const ROLE = {view: 'Can view', send: 'Can answer and send'}, ROLEIC = {view: 'eye', send: 'edit'};
  const ROLEHINT = {view: 'Reads the page, its questions, Reference and History', send: 'Also answers, writes notes and presses Send'};
  const MASK = 'member@example.com';

  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch {}
    const t = Object.assign(document.createElement('textarea'), {value: text});
    document.body.appendChild(t); t.select();
    let ok = false; try { ok = document.execCommand('copy'); } catch {}
    t.remove();
    return ok;
  }
  const abs = u => new URL(u, location.href).href;

  async function render(el, ctx, anchor) {
    const D = await ctx.data('links');
    el.innerHTML = '<div class="l-wrap"></div>';
    const w = el.firstElementChild;
    if (anchor === 'people') return people(w, ctx, D);
    draw(w, ctx, D);
    w.onclick = e => click(e, w, ctx, D);
  }

  function draw(w, ctx, D) {
    const {esc, icon} = ctx;
    const copyBtn = (key, name) => `<button class="ib" data-copylink="${esc(key)}" data-name="${esc(name)}" title="Copy link to ${esc(name)}" aria-label="Copy link to ${esc(name)}">${icon(S.copied === key ? 'copied' : 'link')}</button>`;
    const pageRow = (name, sub, key, open) => `<div class="l-line">${icon('doc')}<span class="l-grow">${open}<span class="small mut l-sub">${sub}</span></span>${copyBtn(key, name)}</div>`;
    const me = pageRow(D.name, `this prototype copy · version ${esc(D.current.replace(/^v/, ''))} · ${pl(D.versions, 'version', 'versions')}`, ctx.base,
      `<button class="lk" data-goq>${esc(D.name)}</button>`);
    const others = D.pages.map(p => pageRow(p.name, `live page · ${pl(p.versions, 'version', 'versions')}${p.last ? ` · last ${esc(p.last)}` : ''}`, p.url,
      `<a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.name)} ${icon('ext')}</a>`)).join('');
    const ppl = 1 + ctx.prefs.get('people', []).length;
    const arch = S.arch ? D.archived.map(a => `<div class="l-line l-subrow">${icon('archive')}<span class="l-grow"><button class="lk l-left" data-arch="${esc(a.id)}" aria-expanded="${S.view === a.id}">${esc(a.t)}</button>
        <span class="small mut l-sub">${esc(a.when)} · read-only, takes no answers</span></span>${copyBtn(`plans/${a.id}/${a.v}.html`, a.t)}</div>${S.view === a.id ? '<div class="l-view" data-view></div>' : ''}`).join('') : '';
    w.innerHTML = `<div class="l-cols"><section><h2 class="l-ph">${icon('pages')} Pages of this project <span class="badge grey">${1 + D.pages.length}</span></h2>${me}${others}
        <div class="l-line">${icon('people')}<span class="l-grow"><button class="lk" data-people>People</button><span class="small mut l-sub">who can open this page · ${pl(ppl, 'person', 'people')}</span></span>${icon('chev')}</div>
        <div class="l-grp"><button class="l-fold" data-archall aria-expanded="${S.arch}">${icon('chev')}<b>Archived pages</b> <span class="small mut">${pl(D.archived.length, 'snapshot', 'snapshots')}</span></button>${arch}</div>
        <div class="l-line">${icon('warn')}<span class="l-grow"><button class="lk l-left" data-bad aria-expanded="${S.view === 'bad'}">A version that fails to load</button><span class="small mut l-sub">an example, to try Retry and Tell the agent</span></span></div>
        ${S.view === 'bad' ? '<div class="l-view" data-view></div>' : ''}</section>
      <section><h2 class="l-ph">${icon('code')} Repos, folders and links</h2>
        ${D.folders.map(f => `<div class="l-line">${icon('code')}<span class="l-grow">${esc(f.name)}<span class="small mut l-sub">${esc(f.what)}</span></span><button class="btn sm" data-copypath="${esc(f.path)}" title="Copy ${esc(f.path)}">${icon(S.copied === f.path ? 'copied' : 'copy')} Copy path</button></div>`).join('')}
        ${D.links.map(l => `<div class="l-line">${icon('bead')}<span class="l-grow"><a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.name)} ${icon('ext')}</a><span class="small mut l-sub">${esc(l.what)}</span></span>${copyBtn(l.url, l.name)}</div>`).join('')}
        <p class="small mut">This project's documents are in <button class="lk" data-goref>Reference</button>.</p></section></div>`;
    const host = w.querySelector('[data-view]');
    if (host) {
      const a = D.archived.find(x => x.id === S.view);
      const close = () => { S.view = ''; draw(w, ctx, D); };
      P.viewVersion(host, ctx, a ? {title: a.t, src: `plans/${encodeURIComponent(a.id)}/${encodeURIComponent(a.v)}.html`, onClose: close}
        : {title: 'A version that fails to load', src: 'content?v=v0', onClose: close});
    }
  }

  async function click(e, w, ctx, D) {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.copylink || b.dataset.copypath) {
      const key = b.dataset.copylink || b.dataset.copypath, path = !!b.dataset.copypath;
      const ok = await copyText(path ? key : abs(key));
      if (!ok) return ctx.toast('Copy failed: your browser blocked the clipboard');
      S.copied = key; draw(w, ctx, D);
      ctx.toast(path ? `Path copied: ${key}` : `Link to ${b.dataset.name} copied`);
      setTimeout(() => { if (S.copied === key) { S.copied = ''; draw(w, ctx, D); } }, 2000);
    } else if (b.hasAttribute('data-archall')) { S.arch = !S.arch; draw(w, ctx, D); }
    else if (b.dataset.arch) { S.view = S.view === b.dataset.arch ? '' : b.dataset.arch; draw(w, ctx, D); }
    else if (b.hasAttribute('data-bad')) { S.view = S.view === 'bad' ? '' : 'bad'; draw(w, ctx, D); }
    else if (b.hasAttribute('data-people')) ctx.go('links', 'people');
    else if (b.hasAttribute('data-goq')) ctx.go('questions');
    else if (b.hasAttribute('data-goref')) ctx.go('reference');
  }

  /* ---------- People: two roles; edits change only this copy, kept in this browser ---------- */
  function people(w, ctx, D) {
    const {esc, icon} = ctx;
    let list = ctx.prefs.get('people', []), role = 'view', err = '';
    const save = l => { list = l; ctx.prefs.set('people', l); ctx.refreshChips(); draw(); };
    const owners = D.people.length ? D.people : [{name: 'You', email: MASK, role: 'owner', seen: ''}];
    const seg = (cur, attr, label) => `<span class="l-seg" role="group" aria-label="${esc(label)}">${['view', 'send'].map(r => `<button ${attr}="${r}" aria-pressed="${cur === r}" title="${esc(ROLEHINT[r])}">${icon(ROLEIC[r])}${ROLE[r]}</button>`).join('')}</span>`;
    function draw() {
      w.innerHTML = `<div class="l-people"><button class="lk small l-back" data-back>${icon('chev')} Pages &amp; links</button>
        <h2 class="l-ph">${icon('people')} People on ${esc(D.name)} <span class="badge grey">${owners.length + list.length}</span></h2>
        <p class="small mut">Only you, the owner, add or remove people and change what they can do. In this prototype a change stays in this copy: nobody's real access changes.</p>
        <div role="list">${owners.map(o => `<div class="l-prow" role="listitem"><span class="l-av" aria-hidden="true">${esc(o.name[0])}</span><div class="l-grow"><b>${esc(o.name)}</b> <span class="small mut">(you)</span><div class="small mut">${MASK} · Google sign-in · owner</div></div><span class="chip">${icon('key')} Owner</span></div>`).join('')}
        ${list.map((x, i) => `<div class="l-prow" role="listitem"><span class="l-av" aria-hidden="true">${esc(x.name[0] || '?')}</span><div class="l-grow"><b>${esc(x.name)}</b><div class="small mut">${MASK} · added ${esc(x.added)} · has not opened it yet</div></div>
          ${seg(x.role, `data-prole="${i}" data-r`, `What ${x.name} can do`)}<button class="ib" data-prm="${i}" title="Remove ${esc(x.name)}" aria-label="Remove ${esc(x.name)}">${icon('trash')}</button></div>`).join('')}</div>
        <form class="l-add" data-add><input type="text" id="l-pname" placeholder="Their name" aria-label="Their name" required>
          <input type="email" id="l-pmail" placeholder="Their Google email" aria-label="Their Google email" required>
          ${seg(role, 'data-newrole', 'What they can do')}<button class="btn pri sm" type="submit">${icon('plus')} Add</button></form>
        ${err ? `<p class="small l-err" role="alert">${esc(err)}</p>` : ''}
        <p class="small mut l-hint">${icon('eye')} Can view: reads the page, its questions, Reference and History. ${icon('edit')} Can answer and send: also answers, writes notes and presses Send.</p></div>`;
      w.querySelector('[data-back]').onclick = () => ctx.go('links');
      w.querySelectorAll('[data-newrole]').forEach(b => { b.onclick = () => { role = b.dataset.newrole; w.querySelectorAll('[data-newrole]').forEach(x => x.setAttribute('aria-pressed', String(x === b))); }; });
      w.querySelectorAll('[data-prole]').forEach(b => { b.onclick = () => { const i = +b.dataset.prole, was = list[i].role, n = list.map((x, j) => j === i ? {...x, role: b.dataset.r} : x);
        save(n); ctx.toast(`${list[i].name}: ${ROLE[b.dataset.r].toLowerCase()}`, {undo: () => save(list.map((x, j) => j === i ? {...x, role: was} : x))}); }; });
      w.querySelectorAll('[data-prm]').forEach(b => { b.onclick = () => { const before = list, x = list[+b.dataset.prm];
        save(list.filter((_, j) => j !== +b.dataset.prm)); ctx.toast(`${x.name} removed`, {undo: () => save(before)}); }; });
      w.querySelector('[data-add]').onsubmit = e => {
        e.preventDefault();
        const name = w.querySelector('#l-pname').value.trim(), mail = w.querySelector('#l-pmail').value.trim();
        err = !name ? 'Type their name.' : !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(mail) ? 'Type their full Google email address.'
          : list.some(x => x.name.toLowerCase() === name.toLowerCase()) ? `${name} is already on the list.` : '';
        if (err) return draw();
        const before = list;  // the email itself is never kept: every email shows as member@example.com
        save([...list, {name, role, added: new Date().toISOString().slice(0, 10)}]);
        ctx.toast(`${name} added: ${ROLE[role].toLowerCase()}`, {undo: () => save(before)});
      };
    }
    draw();
  }

  P.tab({key: 'links', render, chip: async ctx => { const D = await ctx.data('links'); return {text: String(1 + D.pages.length), title: 'pages'}; }});
})();
