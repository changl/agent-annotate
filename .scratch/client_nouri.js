(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const btn = t => [...document.querySelectorAll('button')].filter(b => b.offsetParent && b.innerText.trim() === t);
  document.querySelector('cfc-select[role=combobox]').click();
  await sleep(1200);
  [...document.querySelectorAll('[role=option]')].find(x => x.innerText.trim() === 'Web application').click();
  await sleep(2000);
  const name = [...document.querySelectorAll('input.mat-mdc-input-element')].filter(i => i.offsetParent)[0];
  name.focus(); name.value = 'agent-annotate pages';
  name.dispatchEvent(new Event('input', { bubbles: true })); name.dispatchEvent(new Event('blur', { bubbles: true }));
  await sleep(800);
  const c = btn('Create'); c[c.length - 1].click();
  await sleep(10000);
  const d = document.querySelector('mat-dialog-container,[role=dialog]');
  const t = d ? d.innerText : '';
  return JSON.stringify({ name: name.value, created: /OAuth client created/i.test(t), err: /failed|error/i.test(t), errText: /failed|error/i.test(t) ? t.slice(0, 200) : '' });
})()
