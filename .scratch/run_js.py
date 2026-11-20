#!/usr/bin/env python3
"""usage: run_js.py <session> <file.js> [more.js ...] — eval each file in order in the opencli session."""
import subprocess, sys
for f in sys.argv[2:]:
    print(subprocess.run(['opencli', 'browser', '--session', sys.argv[1], 'eval', open(f).read()],
                         capture_output=True, text=True, timeout=110).stdout.strip())
