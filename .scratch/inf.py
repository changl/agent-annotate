#!/usr/bin/env python3
"""Infisical writes for agent-annotate sign-in. Never prints secret values; prints names, lengths and statuses only.

usage: inf.py probe | session-key | client <downloaded.json> | owner | check
"""
import base64, json, secrets, subprocess, sys, urllib.error, urllib.parse, urllib.request

API = 'https://app.infisical.com/api/'
PROJECT = '00316527-5e56-4423-b7de-421e1db0dccf'
ENV = 'dev'
PATH = '/projects/agent-annotate'
NAMES = ('GOOGLE_OAUTH_CLIENT_ID', 'GOOGLE_OAUTH_CLIENT_SECRET', 'ANNOTATE_SESSION_KEY', 'ANNOTATE_OWNER_EMAIL')


def call(method, path, body=None, token=None, cookie=None):
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if cookie:
        headers['Cookie'] = cookie
    req = urllib.request.Request(API + path, method=method, headers=headers,
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get('message', '')
        except ValueError:
            msg = ''
        return e.code, {'error': str(msg)[:200]}


def token():
    cfg = json.load(open('/Users/changlee/.infisical/infisical-config.json'))
    email = cfg['loggedInUsers'][0]['email']
    raw = subprocess.run(['/usr/bin/security', 'find-generic-password', '-s', 'infisical-cli', '-a', email, '-w'],
                         capture_output=True, text=True, check=True).stdout.strip()
    if raw.startswith('go-keyring-base64:'):
        raw = base64.b64decode(raw.split(':', 1)[1]).decode()
    status, data = call('POST', 'v1/auth/token', {}, cookie='jid=' + json.loads(raw)['RefreshToken'])
    if status != 200 or not data.get('token'):
        sys.exit('refresh failed: HTTP %s %s' % (status, data.get('error')))
    return data['token']


def q(**kw):
    return urllib.parse.urlencode({'workspaceId': PROJECT, 'environment': ENV, **kw})


def names(tok, path):
    status, data = call('GET', 'v3/secrets/raw?' + q(secretPath=path), token=tok)
    return status, {s['secretKey']: len(s.get('secretValue') or '') for s in data.get('secrets', [])}


def ensure_folder(tok):
    status, data = call('GET', 'v1/folders?' + q(path='/projects'), token=tok)
    if 'agent-annotate' in [f['name'] for f in data.get('folders', [])]:
        return
    status, _ = call('POST', 'v1/folders', {'workspaceId': PROJECT, 'environment': ENV, 'path': '/projects',
                                            'name': 'agent-annotate'}, token=tok)
    print('created folder', PATH, 'HTTP', status)


def put(tok, name, value):
    assert name in NAMES and value
    body = {'workspaceId': PROJECT, 'environment': ENV, 'secretPath': PATH, 'secretValue': value, 'type': 'shared'}
    status, _ = call('POST', 'v3/secrets/raw/' + name, body, token=tok)
    if status not in (200, 201):
        status, _ = call('PATCH', 'v3/secrets/raw/' + name, body, token=tok)
    print(name, 'HTTP', status)
    if status not in (200, 201):
        sys.exit(1)


def owner_email():
    js = ("(()=>{let r=null;const w=n=>{n.querySelectorAll('*').forEach(e=>{const v=e.getAttribute&&e.getAttribute('aria-label');"
          "if(v&&v.startsWith('Account:'))r=v;if(e.shadowRoot)w(e.shadowRoot)})};w(document);return r})()")
    out = subprocess.run(['opencli', 'browser', '--session', 'gcp', 'eval', js], capture_output=True, text=True).stdout
    label = json.loads(out).get('data') or ''
    email = label[label.rfind('(') + 1:label.rfind(')')].strip().lower()
    assert email.endswith('@gmail.com') and '@' in email[:-10], 'no gmail account label on the gcp page'
    return email


def main():
    cmd = sys.argv[1]
    tok = token()
    if cmd == 'probe':
        status, data = call('GET', 'v1/folders?' + q(path='/projects'), token=tok)
        print('folders under /projects HTTP', status, sorted(f['name'] for f in data.get('folders', [])))
        for p in (PATH, '/projects/agentannotate'):
            print(p, *names(tok, p))
    elif cmd == 'session-key':
        ensure_folder(tok)
        put(tok, 'ANNOTATE_SESSION_KEY', secrets.token_urlsafe(32))
    elif cmd == 'client':
        f = sys.argv[2]
        web = json.load(open(f))['web']
        put(tok, 'GOOGLE_OAUTH_CLIENT_ID', web['client_id'])
        put(tok, 'GOOGLE_OAUTH_CLIENT_SECRET', web['client_secret'])
        print('redirect_uris', web.get('redirect_uris'))
        open(f, 'w').write('{}')
        print('overwrote', f)
    elif cmd == 'owner':
        put(tok, 'ANNOTATE_OWNER_EMAIL', owner_email())
    elif cmd == 'check':
        status, got = names(tok, PATH)
        for n in NAMES:
            print(n, 'set len %d' % got[n] if got.get(n) else 'missing')


if __name__ == '__main__':
    main()
