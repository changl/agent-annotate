#!/usr/bin/env bash
# SessionStart hook: local notice; Orca delivery only when its owner resumes.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 0
for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        exec "$cmd" "$DIR/session_start.py" "$@"
    fi
done
exit 0
