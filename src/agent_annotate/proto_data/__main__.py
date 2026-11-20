"""Scrub a prototype page copy in place: python3 -m agent_annotate.proto_data DEST.

Every text file under DEST (author fields, free text, versions, plans) loses its addresses and review keys.
Prints counts only, never a match.
"""
import sys
from pathlib import Path

from . import scrub

changed = 0
for p in sorted(x for x in Path(sys.argv[1]).rglob("*") if x.is_file() and not x.is_symlink()):
    try:
        text = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue  # images and other binary files
    clean = scrub(text)
    if clean != text:
        p.write_text(clean, encoding="utf-8")
        changed += 1
print(f"scrubbed {changed} file(s)")
