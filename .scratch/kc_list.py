#!/usr/bin/env python3
"""List keychain service names mentioning infisical. No account names or values."""
import re, subprocess
out = subprocess.run(['/usr/bin/security', 'dump-keychain'], capture_output=True, text=True).stdout
print(sorted({s for s in re.findall(r'"svce"<blob>="([^"]*)"', out) if 'infisical' in s.lower()}))
