#!/usr/bin/env bash
# Thin provider hook. The Python runtime owns portable path resolution,
# offset tracking, and output formatting.

if command -v annotate >/dev/null 2>&1; then
    exec annotate hook-check
fi

exit 0
