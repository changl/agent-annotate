#!/usr/bin/env python3
"""Report whether the infisical CLI keychain session exists and whether its JWT is expired. Prints no values."""
import base64, json, subprocess, time

cfg = json.load(open('/Users/changlee/.infisical/infisical-config.json'))
for user in cfg.get('loggedInUsers', []):
    for service in ('infisical-cli', 'infisical'):
        r = subprocess.run(['/usr/bin/security', 'find-generic-password', '-s', service, '-a', user['email'], '-w'],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(service, 'missing')
            continue
        raw = r.stdout.strip()
        if raw.startswith('go-keyring-base64:'):
            raw = base64.b64decode(raw.split(':', 1)[1]).decode()
        try:
            data = json.loads(raw)
        except ValueError:
            print(service, 'present, not json, len', len(raw))
            continue
        tok = data.get('JTWToken') or data.get('JWTToken') or ''
        exp = None
        if tok.count('.') == 2:
            p = tok.split('.')[1]
            exp = json.loads(base64.urlsafe_b64decode(p + '=' * (-len(p) % 4))).get('exp')
        print(service, 'present keys', sorted(data), 'expired' if exp and exp < time.time() else 'valid' if exp else 'no-exp')
