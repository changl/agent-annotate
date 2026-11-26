"""One-off inventory: page owners, liveness, current terminal, queued sends."""
import json
import os
import subprocess
from pathlib import Path

STATE = Path.home() / ".claude/annotate-state/state"
resumed = {}
out = subprocess.run(["pgrep", "-fl", "--", "--resume"], capture_output=True, text=True).stdout
for line in out.splitlines():
    parts = line.split()
    if "--resume" in parts:
        resumed[parts[parts.index("--resume") + 1]] = int(parts[0])


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def handle_of(pid):
    r = subprocess.run(["ps", "eww", "-p", str(pid), "-o", "command="], capture_output=True, text=True)
    for tok in r.stdout.split():
        if tok.startswith("ORCA_TERMINAL_HANDLE="):
            return tok.split("=", 1)[1]
    return None


for f in sorted(STATE.glob("*.json")):
    try:
        state = json.loads(f.read_text())
    except Exception:
        continue
    project = state.get("project") or f.stem
    for slug, rec in (state.get("slugs") or {}).items():
        if not isinstance(rec, dict) or rec.get("archived") or rec.get("consolidated_into"):
            continue
        sess = rec.get("owner_session")
        tgt = rec.get("owner_target") or {}
        old_pid = tgt.get("pid")
        journal = STATE / "deliveries" / project / f"{slug}.json"
        queued = []
        try:
            rows = json.loads(journal.read_text()).get("deliveries", {}).values()
            queued = [(r.get("created_at"), r.get("state"), (r.get("detail") or "")[:60])
                      for r in rows if r.get("state") in ("pending", "attempting", "uncertain")]
        except Exception:
            pass
        new_pid = resumed.get(sess)
        last_bus = None
        try:
            tail = Path(rec.get("bus_file")).read_bytes()[-4000:].splitlines()
            last_bus = json.loads(tail[-1]).get("ts")
        except Exception:
            pass
        print(json.dumps({
            "last_bus": last_bus,
            "project": project, "slug": slug, "session": sess,
            "claimed": rec.get("owner_claimed_at") or rec.get("claimed_at"),
            "old_pid": old_pid, "old_alive": alive(old_pid) if old_pid else None,
            "old_handle": tgt.get("handle"),
            "resumed_pid": new_pid, "resumed_handle": handle_of(new_pid) if new_pid else None,
            "queued": queued,
        }))
