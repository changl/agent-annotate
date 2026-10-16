#!/usr/bin/env bash
# SessionStart hook: local files only, no CLI startup or network requests.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 0
for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        exec "$cmd" "$DIR/session_start.py" "$@"
    fi
done
exit 0
