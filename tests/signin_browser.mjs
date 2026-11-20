// Drives headless Chrome over its DevTools pipe for tests/test_signin_browser.py; asserts nothing.
// Run: node signin_browser.mjs <plan.json>. Prints one JSON line of what each visit saw.
// The plan: {chrome, profile, host, port, visits: [{name, device, url, card, click}]}.
// Each visit gets its own browser context, so its own empty cookie jar.
import {spawn} from 'node:child_process';
import {readFileSync} from 'node:fs';

const plan = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const PHONE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1';
const DEVICES = {
  desk: {width: 1440, height: 900, deviceScaleFactor: 1, mobile: false},
  phone: {width: 390, height: 844, deviceScaleFactor: 3, mobile: true},
};
// The pipe needs no debugging port; the host maps to the test server, whose certificate is self-signed.
const chrome = spawn(plan.chrome, ['--headless=new', '--remote-debugging-pipe', `--user-data-dir=${plan.profile}`,
  '--no-first-run', '--no-default-browser-check', '--disable-gpu', '--ignore-certificate-errors',
  `--host-resolver-rules=MAP ${plan.host} 127.0.0.1`, 'about:blank'], {stdio: ['ignore', 'ignore', 'ignore', 'pipe', 'pipe']});
const sleep = ms => new Promise(r => setTimeout(r, ms));
let id = 0, buffer = '';
const pending = new Map();
chrome.stdio[4].on('data', chunk => {
  buffer += chunk.toString();
  let end;
  while ((end = buffer.indexOf('\0')) >= 0) {
    const message = JSON.parse(buffer.slice(0, end));
    buffer = buffer.slice(end + 1);
    if (message.id && pending.has(message.id)) { pending.get(message.id)(message); pending.delete(message.id); }
  }
});
const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
  const i = ++id;
  pending.set(i, m => m.error ? reject(new Error(method + ': ' + m.error.message)) : resolve(m.result));
  chrome.stdio[3].write(JSON.stringify({id: i, method, params, ...(sessionId ? {sessionId} : {})}) + '\0');
});

async function visit(v) {
  const {browserContextId} = await send('Target.createBrowserContext', {disposeOnDetach: true});
  const {targetId} = await send('Target.createTarget', {url: 'about:blank', browserContextId});
  const {sessionId} = await send('Target.attachToTarget', {targetId, flatten: true});
  const s = (method, params) => send(method, params, sessionId);
  await s('Page.enable');
  await s('Emulation.setDeviceMetricsOverride', DEVICES[v.device]);
  if (v.device === 'phone') {
    await s('Emulation.setUserAgentOverride', {userAgent: PHONE_UA, platform: 'iPhone'});
    await s('Emulation.setTouchEmulationEnabled', {enabled: true, maxTouchPoints: 5});
  }
  const evaluate = async (expression, contextId) => {
    const r = await s('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true, ...(contextId ? {contextId} : {})});
    return r.exceptionDetails ? {error: r.exceptionDetails.text} : r.result.value;
  };
  // Settled: the shell drew the linked card, or a page with no shell (the not-shared page) loaded.
  const settle = async () => {
    for (let i = 0; i < 100; i++) {
      await sleep(200);
      const ready = await evaluate(`document.readyState === 'complete' && location.host === ${JSON.stringify(plan.host + ':' + plan.port)}
        && (!document.getElementById('comment-list') || !!document.querySelector('#comment-list .citem.hl'))`).catch(() => false);
      if (ready === true) break;
    }
    await sleep(1500);  // the card scrolls into view smoothly; the picture decodes
  };
  const look = async () => {
    const top = await evaluate(`(async () => {
      const who = document.getElementById('comment-list')
        ? await fetch('./api/identity', {cache: 'no-store'}).then(r => r.json()).then(i => i.email, () => null) : null;
      const card = document.querySelector('#comment-list [data-comment-id="${v.card}"]');
      const r = card && card.getBoundingClientRect();
      const hit = r && document.elementFromPoint(r.left + r.width / 2, Math.min(r.top + 10, innerHeight - 1));
      const frame = document.getElementById('content-frame');
      return {href: location.href, who, text: document.body.innerText.slice(0, 400),
              card: card ? {highlighted: card.classList.contains('hl'), onScreen: !!hit && card.contains(hit),
                            text: card.innerText.slice(0, 120)} : null,
              frame: frame ? frame.getAttribute('src') : null};
    })()`);
    // The document is a sandboxed frame; read it from inside.
    const {frameTree} = await s('Page.getFrameTree');
    const child = (frameTree.childFrames || []).map(f => f.frame).find(f => f.url.includes('/content'));
    if (child) {
      const {executionContextId} = await s('Page.createIsolatedWorld', {frameId: child.id});
      top.document = await evaluate(`(() => {
        const img = document.querySelector('[data-anchor-id="fig:proof"] img');
        return {url: location.href, text: document.body.innerText.slice(0, 400),
                picture: img ? {complete: img.complete, width: img.naturalWidth, height: img.naturalHeight} : null};
      })()`, executionContextId);
    }
    return top;
  };
  await s('Page.navigate', {url: v.url});
  await settle();
  const result = {name: v.name, device: v.device, first: await look()};
  if (v.click) {  // a real click on the link with that text, the way a person would press it
    const box = await evaluate(`(() => { const a = [...document.links].find(l => l.textContent.trim() === ${JSON.stringify(v.click)});
      if (!a) return null; const r = a.getBoundingClientRect(); return {x: r.left + r.width / 2, y: r.top + r.height / 2}; })()`);
    result.clicked = !!box;
    if (box) {
      for (const type of ['mousePressed', 'mouseReleased']) {
        await s('Input.dispatchMouseEvent', {type, x: box.x, y: box.y, button: 'left', clickCount: 1});
      }
      await sleep(500);
      await settle();
      result.after = await look();
    }
  }
  await send('Target.closeTarget', {targetId});
  await send('Target.disposeBrowserContext', {browserContextId});
  return result;
}

try {
  const results = [];
  for (const v of plan.visits) results.push(await visit(v));
  console.log(JSON.stringify(results));
} finally {
  await send('Browser.close').catch(() => {});
  chrome.kill();
}
