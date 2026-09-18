#!/usr/bin/env bash
# check-comment-bus.sh — UserPromptSubmit hook for Agent Annotate.
#
# Thin shim: the work lives in check_comment_bus.py next to this file, which
# does the whole scan in one process. The previous shell implementation forked
# basename/mkdir/wc/cat/tail/grep per bus file — roughly 200 processes per
# prompt at 32 buses — and that fork storm, not the volume of data, is what
# exceeded the hook timeout on a loaded machine.
#
# `exec` matters twice over: it keeps the process count at one, and it hands
# the Python the hook's stdin unchanged. Claude Code delivers the hook payload
# (session_id, cwd) there, and without it every prompt would look like it came
# from an unknown session.
#
# The script is located relative to this file rather than through `annotate`
# on PATH: on at least one machine that name resolves to libgd's image tool.
#
# Exit code is always 0 — never block a prompt, even with no Python present.

set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 0
PY="$DIR/check_comment_bus.py"
[ -f "$PY" ] || exit 0

for cmd in python3 python; do
    if command -v "$cmd" >/dev/null 2>&1; then
        exec "$cmd" "$PY" "$@"
    fi
done

exit 0
