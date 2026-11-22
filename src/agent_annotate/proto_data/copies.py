"""Read-only copies of other projects' pages (Rebex, Agent Annotate), kept at their real page's latest version.

copy.sh makes them on every restart: python3 -m agent_annotate.proto_data.copies ROOT KEY NAME SRC.
The server calls fresh() as it serves a copy's meta (and <copy>/proto/data/copies.json): a newer version on the real page
is copied in the background, and the frame says so until the copy turns Reload blue. The real page is only read: an APFS clone, then the clone is changed:
- page.db forgets its bus file first, so nothing the store does while exporting can reach the real bus;
- page.db goes back to JSON (db_off) and its database is deleted (replaced.delete);
- owner, lease, delivery, workspace and move keys leave the meta; "ui": "proto" and "proto_copy_of": KEY are set;
- every address is masked and review keys redacted (python3 -m agent_annotate.proto_data), and Rebex's preview store staged.
The clone is built in trash/ and swapped in with two renames, so the copy being served is never half made;
then the replaced copy (or a half-made one) is deleted: only the newest copy is kept (card #160).
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

from .. import store
from .replaced import delete

_lock = threading.Lock()


def _current(d: Path) -> str:
    try:
        return str(json.loads((d / "current.meta.json").read_text(encoding="utf-8")).get("current") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def _scrub(d: Path, old: Path) -> None:
    """Mask every address and redact review keys in D's text files, as python3 -m agent_annotate.proto_data does.
    A published version (versions/, source/, a plan's versions/) never changes, so one the old copy already scrubbed is reused: seconds, not 20."""
    from . import scrub, scrub_json
    for p in d.rglob("*"):
        if not p.is_file() or p.is_symlink():
            continue
        rel = p.relative_to(d)
        if ("versions" in rel.parts[:-1] or rel.parts[0] == "source") and (old / rel).is_file():
            shutil.copyfile(old / rel, p)
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # images and other binary files
        if scrub(text, escaped=True) != text:  # JSON is scrubbed by value so it stays valid
            p.write_text(scrub_json(text) if p.suffix in (".json", ".ndjson") else scrub(text, escaped=True), encoding="utf-8")


# the live delivery records (read only): a round's "delivery" in rounds.ndjson stays "queued"; its real state is kept here
LIVE_DELIVERIES = Path.home() / ".claude" / "annotate-state" / "state" / "deliveries"


def _deliveries(d: Path, slug: str, live: Path = LIVE_DELIVERIES) -> None:
    """Each round in D's rounds.ndjson takes its real delivery state ("acknowledged": read by the agent), as the real page shows it (audit6 questions #03)."""
    states = {}
    for p in sorted(live.glob(f"*/{slug}.json")):
        try:
            states.update({k: r.get("state") for k, r in json.loads(p.read_text(encoding="utf-8")).get("deliveries", {}).items() if r.get("state")})
        except (OSError, ValueError, AttributeError):
            continue
    path = d / "rounds.ndjson"
    if not states or not path.is_file():
        return
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            out.append(line)
            continue
        if isinstance(r, dict) and states.get(r.get("id")):
            r["delivery"] = states[r["id"]]
            line = json.dumps(r, ensure_ascii=False)
        out.append(line)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def refresh(root: Path, key: str, name: str, src: Path) -> Path:
    """A fresh read-only copy of SRC at ROOT/reviews/proto-KEY; the old copy is deleted."""
    dest = root / "reviews" / f"proto-{key}"
    stamp = time.strftime("%Y%m%dT%H%M%S")
    trash = root / "trash"
    trash.mkdir(parents=True, exist_ok=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = trash / f"proto-{key}-new-{stamp}"
    try:
        subprocess.run(["cp", "-cR", str(src), str(tmp)], check=True)
        db = tmp / store.DB_NAME
        if db.exists():
            conn = sqlite3.connect(db)
            conn.execute("DELETE FROM meta WHERE key = 'bus_file'")
            conn.commit()
            conn.close()
            kept = store.db_off(tmp)
            old_db = trash / f"proto-{key}-{kept.name}-{stamp}"
            shutil.move(str(kept), str(old_db))
            delete(root, old_db)
        meta_path = tmp / "current.meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        for k in ("owner", "lease", "delivery", "workspace_owner", "moved_to"):
            meta.pop(k, None)
        meta.update(name=name, ui="proto", proto_copy_of=key, proto_source=str(src))
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        assert "owner" not in json.loads(meta_path.read_text()) and not db.exists()
        _deliveries(tmp, src.name)
        _scrub(tmp, dest)
        from .reference import stage_store
        stage_store(tmp)  # Rebex's working preview store; nothing for a project without one
        old = trash / f"proto-{key}-{stamp}"
        if dest.exists():
            shutil.move(str(dest), str(old))
        tmp.rename(dest)
        delete(root, old)  # only the newest copy is kept (card #160)
    finally:
        delete(root, tmp)  # a half-made copy; nothing once it was swapped in
    return dest


_busy: dict = {}  # copy folder -> the newer version being copied into it


def fresh(copy: Path) -> str:
    """When the real page has a newer version: start one background re-copy (one at a time per copy) and return that version;
    "" when the copy is current. No request waits for it (up to 120 s): the copy serves its own version until the swap (r12 fix10 slowread)."""
    try:
        meta = json.loads((copy / "current.meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    key, src = meta.get("proto_copy_of"), Path(meta.get("proto_source") or "")
    if meta.get("ui") != "proto" or not key or not src.is_dir():
        return ""
    newer, at = _current(src), str(Path(copy).resolve())
    with _lock:
        if at in _busy:
            return _busy[at]
        if newer in ("", str(meta.get("current") or "")):
            return ""
        _busy[at] = newer
    threading.Thread(target=_recopy, args=(at, key, meta.get("name") or key, src), daemon=True).start()
    return newer


def _recopy(at: str, key: str, name: str, src: Path) -> None:
    # its own process: the scrub is CPU-bound and would hold up every other request of this server
    try:
        subprocess.run([sys.executable, "-m", "agent_annotate.proto_data.copies", str(Path(at).parents[1]), key, name, str(src)],
                       check=True, stdout=subprocess.DEVNULL, timeout=120)
        from .frame import _bound, _bound_lock
        with _bound_lock:  # the served copy's caches belong to the old folder
            for k in [k for k in _bound if k[1] == key]:
                _bound.pop(k)
    except (subprocess.SubprocessError, OSError) as exc:  # the last copy keeps serving; a half-made one is deleted
        print(f"copy of {key} not refreshed: {exc}", file=sys.stderr)
    finally:
        with _lock:
            _busy.pop(at, None)


def build(page_dir) -> dict:
    """<copy>/proto/data/copies.json: the newer version being copied into this copy, "" when none (and starts it when behind),
    and the version the copy holds, read after: the frame says "Up to date" only when that is the one on screen (r12 audit12 frame 2)."""
    copying = fresh(Path(page_dir))
    return {"copying": copying, "current": _current(Path(page_dir))}


if __name__ == "__main__":
    a = sys.argv[1:]
    print(f"read-only copy ready: {refresh(Path(a[0]), a[1], a[2], Path(a[3]))}")
