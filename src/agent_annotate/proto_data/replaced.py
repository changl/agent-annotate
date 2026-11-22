"""Delete a replaced prototype copy or its database (Chang, card #160): python3 -m agent_annotate.proto_data.replaced ROOT PATH...

Only the newest copy is kept. A replaced copy is first renamed into ROOT/trash/ (so the swap stays two renames), then deleted here.
Refused, in code: a ROOT outside the prototype folder, a PATH that is a symlink or resolves outside ROOT/trash/.
That keeps the live copy (ROOT/reviews/...), real reviews, ~/projects and /Volumes out of reach. Each deletion is logged with its size.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

PROTO_ROOT = Path("/Users/changlee/annotate-proto")
# shutil.rmtree only below this folder; tests point it at their sandbox (inherited by the background re-copy's process)
ENV = "ANNOTATE_PROTO_ROOT"
NEVER = ("/Users/changlee/projects", "/Volumes")  # refused whatever ROOT says


def _size(p: Path) -> int:
    if p.is_symlink() or p.is_file():
        return p.lstat().st_size
    return sum(f.lstat().st_size for f in p.rglob("*") if f.is_file() and not f.is_symlink())


def delete(root, path) -> int:
    """Delete PATH, a replaced copy (or its database) under ROOT/trash/; returns the bytes freed. Raises ValueError when refused."""
    root, path = Path(root), Path(path)
    allowed = Path(os.environ.get(ENV) or PROTO_ROOT)
    base, top = allowed.resolve(), root.resolve()
    if top != base and base not in top.parents:
        raise ValueError(f"refused: {root} is not the prototype folder {allowed}")
    trash = top / "trash"
    if path.is_symlink():
        raise ValueError(f"refused: {path} is a symlink")
    real = path.resolve()
    if any(Path(n).resolve() in (real, *real.parents) for n in NEVER):
        raise ValueError(f"refused: {path} is under {', '.join(NEVER)}")
    if trash not in real.parents:
        raise ValueError(f"refused: {path} is not a replaced copy under {trash}")
    if not real.exists():
        return 0
    size = _size(real)
    if real.is_dir():
        shutil.rmtree(real)  # rmtree removes symlinks inside without following them
    else:
        real.unlink()
    print(f"deleted replaced copy {real} ({size / 1e6:.1f} MB)", file=sys.stderr)
    return size


if __name__ == "__main__":
    a = sys.argv[1:]
    for p in a[1:]:
        delete(a[0], p)
