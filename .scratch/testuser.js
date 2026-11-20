(async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  let lab = null;
  const w = n => n.querySelectorAll('*').forEach(e => { let v = null; try { v = e.getAttribute('aria-label'); } catch (x) {} if (v && v.startsWith('Account:')) lab = v; if (e.shadowRoot) w(e.shadowRoot); });
  w(document);
  const em = lab.slice(lab.lastIndexOf('(') + 1, lab.lastIndexOf(')')).trim();
  if (!/@gmail\.com$/i.test(em)) return 'not gmail';
  [...document.querySelectorAll('button')].find(b => b.innerText.trim() === 'Add users').click();
  await sleep(1500);
  const i = [...document.querySelectorAll('input')].find(x => x.getAttribute('aria-label') === 'Text field for emails' && x.offsetParent);
  if (!i) return 'no input';
  i.focus(); i.value = em;
  i.dispatchEvent(new Event('input', { bubbles: true }));
  i.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
  await sleep(800);
  const chips = [...document.querySelectorAll('mat-chip-row,.mat-mdc-chip')].map(c => c.innerText);
  let form = i.parentElement;
  while (form && ![...form.querySelectorAll('button')].some(b => b.innerText.trim() === 'Save')) form = form.parentElement;
  const s = [...form.querySelectorAll('button')].filter(b => b.innerText.trim() === 'Save');
  const state = { valid: form.className.includes('ng-valid'), invalid: form.className.includes('ng-invalid') };
  s[0].click();
  await sleep(5000);
  return JSON.stringify({ chipMatch: chips.some(c => c.includes(em)), saves: s.length, state, errs: [...form.querySelectorAll('mat-error')].map(e => e.innerText.replace(/[\w.+-]+@[\w.-]+/g, '<E>')) });
})()
