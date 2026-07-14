#!/usr/bin/env python3
"""migrate.py — convert a legacy v1 annotate HTML + comments.json into the
v2 directory layout.

Thin wrapper around `annotate migrate`. The real implementation lives in
cli.py to avoid duplication.

Usage:
    python migrate.py <legacy.html> [--slug <slug>] [--version v1] [--label "..."] [--copy]

Outputs a <slug>/ directory next to <legacy.html> with:
    versions/<version>.html
    current.html → versions/<version>.html (symlink)
    current.meta.json
    comments.json  (v2 shape)
    archive/
"""

import argparse
import sys

from .cli import cmd_migrate


def main():
    p = argparse.ArgumentParser(description="legacy → annotate v2 migration")
    p.add_argument("legacy_html")
    p.add_argument("--slug", default=None)
    p.add_argument("--version", default="v1")
    p.add_argument("--label", default=None)
    p.add_argument("--copy", action="store_true", help="copy instead of move")
    args = p.parse_args()
    sys.exit(cmd_migrate(args))


if __name__ == "__main__":
    main()
