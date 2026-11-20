(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const btn = t => [...document.querySelectorAll('button')].filter(b => b.offsetParent && b.innerText.trim() === t);
  await sleep(6000);
  document.querySelector('cfc-select[role=combobox]').click();
  await sleep(1200);
  [...document.querySelectorAll('[role=option]')].find(x => x.innerText.trim() === 'Web application').click();
  await sleep(2000);
  const set = (el, v) => { el.focus(); el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('blur', { bubbles: true })); };
  const vis = () => [...document.querySelectorAll('input.mat-mdc-input-element')].filter(i => i.offsetParent);
  set(vis()[0], 'agent-annotate pages');
  btn('Add URI')[1].click();
  await sleep(1200);
  set(vis()[1], 'https://m1max.tail2b8ab9.ts.net/annotate/auth/callback');
  await sleep(1000);
  const sec = (document.querySelector('main') || document.body).innerText;
  const form = sec.slice(sec.indexOf('Authorized JavaScript origins'), sec.indexOf('Use this client')).replace(/\s+/g, ' ');
  const c = btn('Create'); c[c.length - 1].click();
  await sleep(12000);
  const d = document.querySelector('mat-dialog-container,[role=dialog]');
  const t = d ? d.innerText : '';
  return JSON.stringify({ form, name: vis()[0] && vis()[0].value, created: /OAuth client created/i.test(t), err: /failed|error/i.test(t), errText: /failed|error/i.test(t) ? t.slice(0, 200) : '' });
})()
