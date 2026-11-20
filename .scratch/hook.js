(() => {
  if (window.__aaLog) return 'already';
  window.__aaLog = [];
  const red = s => String(s).replace(/GOCSPX-[\w-]+/g, '<SECRET>').replace(/[\w.+-]+@[\w.-]+/g, '<E>').slice(0, 1500);
  const keep = (url, method, status, body) => {
    if (method === 'GET' && status < 400) return;
    window.__aaLog.push({ url: red(url).slice(0, 200), method, status, body: red(body) });
  };
  const of = window.fetch;
  window.fetch = async function (input, init) {
    const r = await of.apply(this, arguments);
    try {
      const url = typeof input === 'string' ? input : input.url;
      const method = (init && init.method) || (input && input.method) || 'GET';
      r.clone().text().then(t => keep(url, method.toUpperCase(), r.status, t));
    } catch (e) {}
    return r;
  };
  const oo = XMLHttpRequest.prototype.open, os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__m = m; this.__u = u; return oo.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function () {
    this.addEventListener('loadend', () => { try { keep(this.__u, String(this.__m).toUpperCase(), this.status, this.responseType === '' || this.responseType === 'text' ? this.responseText : '[' + this.responseType + ']'); } catch (e) {} });
    return os.apply(this, arguments);
  };
  return 'hooked';
})()
