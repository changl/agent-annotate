// Drives headless Chrome over its DevTools pipe for tests/test_signin_browser.py; asserts nothing.
// Run: node signin_browser.mjs <plan.json>. Prints one JSON line of what each visit saw.
// The plan: {chrome, profile, host, port, proxy, visits: [{name, device, url, card, click, copy}]}.
// Each visit gets its own browser context, so its own empty cookie jar. url "@copied" opens
// what the previous visit's Copy link put on the clipboard.
// The Python side starts this in its own process group and kills the group on its deadline;
// here every DevTools call and the shutdown have their own deadline too.
import {spawn} from 'node:child_process';
import {readFileSync} from 'node:fs';

const plan = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const CALL_MS = 15000, CLOSE_MS = 5000;
const PHONE_UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1';
const DEVICES = {
  desk: {width: 1440, height: 900, deviceScaleFactor: 1, mobile: false},
  phone: {width: 390, height: 844, deviceScaleFactor: 3, mobile: true},
};
// The pipe needs no debugging port. Every connection, loopback included, goes through the test's
// gate (plan.proxy), which refuses all but the test servers; WebRTC may not send around it.
// Direct name lookups fail, the test host's certificate is self-signed, and Chrome's own
// background traffic is off.
const chrome = spawn(plan.chrome, ['--headless=new', '--remote-debugging-pipe', `--user-data-dir=${plan.profile}`,
  '--no-first-run', '--no-default-browser-check', '--disable-gpu', '--ignore-certificate-errors',
  `--proxy-server=http://127.0.0.1:${plan.proxy}`, '--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
  // Chrome's own Google services (it preconnects to accounts.google.com and www.google.com for every
  // context, flags or not) go direct instead, where the resolver rule below fails every name.
  '--proxy-bypass-list=<-loopback>;*.google.com;*.gstatic.com;*.googleapis.com',
  '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1',
  '--disable-background-networking', '--disable-component-update', '--disable-sync', '--disable-breakpad',
  '--disable-crash-reporter', '--disable-domain-reliability', '--disable-client-side-phishing-detection',
  '--disable-default-apps', '--disable-extensions', '--no-pings', '--metrics-recording-only',
  '--use-mock-keychain', '--password-store=basic', '--no-service-autorun', 'about:blank'],
  {stdio: ['ignore', 'ignore', 'ignore', 'pipe', 'pipe']});
const exited = new Promise(resolve => chrome.once('exit', resolve));
const sleep = ms => new Promise(r => setTimeout(r, ms));
let id = 0, buffer = '';
const pending = new Map();
chrome.stdio[4].on('data', chunk => {
  buffer += chunk.toString();
  let end;
  while ((end = buffer.indexOf('\0')) >= 0) {
    const message = JSON.parse(buffer.slice(0, end));
    buffer = buffer.slice(end + 1);
    if (message.id && pending.has(message.id)) pending.get(message.id)(message);
  }
});
chrome.stdio[3].on('error', () => {});
exited.then(() => { for (const done of pending.values()) done({error: {message: 'Chrome exited'}}); });
const send = (method, params = {}, sessionId, ms = CALL_MS) => new Promise((resolve, reject) => {
  const i = ++id;
  const timer = setTimeout(() => { pending.delete(i); reject(new Error(`${method}: no answer in ${ms} ms`)); }, ms);
  pending.set(i, m => {
    clearTimeout(timer);
    pending.delete(i);
    m.error ? reject(new Error(method + ': ' + m.error.message)) : resolve(m.result);
  });
  chrome.stdio[3].write(JSON.stringify({id: i, method, params, ...(sessionId ? {sessionId} : {})}) + '\0');
});
let copied = null;

async function visit(v) {
  const {browserContextId} = await send('Target.createBrowserContext', {disposeOnDetach: true});
  const origin = `https://${plan.host}:${plan.port}`;
  await send('Browser.grantPermissions', {origin, browserContextId,
    permissions: ['clipboardReadWrite', 'clipboardSanitizedWrite']});
  const {targetId} = await send('Target.createTarget', {url: 'about:blank', browserContextId});
  const {sessionId} = await send('Target.attachToTarget', {targetId, flatten: true});
  const s = (method, params) => send(method, params, sessionId);
  await s('Page.enable');
  await s('Emulation.setFocusEmulationEnabled', {enabled: true});
  await s('Emulation.setDeviceMetricsOverride', DEVICES[v.device]);
  if (v.device === 'phone') {
    await s('Emulation.setUserAgentOverride', {userAgent: PHONE_UA, platform: 'iPhone'});
    await s('Emulation.setTouchEmulationEnabled', {enabled: true, maxTouchPoints: 5});
  }
  const evaluate = async (expression, contextId) => {
    const r = await s('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true, ...(contextId ? {contextId} : {})});
    return r.exceptionDetails ? {error: r.exceptionDetails.text} : r.result.value;
  };
  // Settled: the shell drew the linked card (or the document, for a link with no card),
  // or a page with no shell (the not-shared page) loaded.
  const settle = async () => {
    for (let i = 0; i < 100; i++) {
      await sleep(200);
      const ready = await evaluate(`document.readyState === 'complete' && location.host === ${JSON.stringify(plan.host + ':' + plan.port)}
        && (!document.getElementById('comment-list') || !!document.querySelector(${JSON.stringify(v.card ? '#comment-list .citem.hl' : '#comment-list .citem')}))`).catch(() => false);
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
  // A real click at the middle of the element, the way a person would press it.
  const press = async find => {
    const box = await evaluate(`(() => { const a = ${find}; const r = a && a.getBoundingClientRect();
      return r && r.width && r.height ? {x: r.left + r.width / 2, y: r.top + r.height / 2} : null; })()`);
    if (!box) return false;
    for (const type of ['mousePressed', 'mouseReleased']) {
      await s('Input.dispatchMouseEvent', {type, x: box.x, y: box.y, button: 'left', clickCount: 1});
    }
    return true;
  };
  if (v.url === '@copied' && !(typeof copied === 'string' && copied)) throw new Error('nothing was copied: ' + JSON.stringify(copied));
  await s('Page.navigate', {url: v.url === '@copied' ? copied : v.url});
  await settle();
  const result = {name: v.name, device: v.device, opened: v.url === '@copied' ? copied : v.url, first: await look()};
  if (v.click) {
    result.clicked = await press(`[...document.links].find(l => l.textContent.trim() === ${JSON.stringify(v.click)})`);
    if (result.clicked) {
      await sleep(500);
      await settle();
      result.after = await look();
    }
  }
  if (v.copy) {  // the avatar menu, Copy link in it, then what the clipboard holds
    result.menuClicked = await press(`document.getElementById('who-btn')`);
    await sleep(300);
    result.copyClicked = await press(`document.getElementById('copy-link-btn')`);
    for (let i = 0; i < 50 && (await evaluate(`document.getElementById('copy-link-btn').textContent`)) !== 'Copied'; i++) await sleep(100);
    result.button = await evaluate(`document.getElementById('copy-link-btn').textContent`);
    copied = result.copied = await evaluate(`navigator.clipboard.readText()`);
    if (!copied) copied = {button: result.button, clicked: result.copyClicked, read: copied};
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
  await send('Browser.close', {}, undefined, CLOSE_MS).catch(() => {});
  if (await Promise.race([exited.then(() => true), sleep(CLOSE_MS).then(() => false)]) === false) {
    chrome.kill('SIGKILL');
    await exited;
  }
}
