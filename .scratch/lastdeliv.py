import json
import sys
from pathlib import Path

p = Path.home() / ".claude/annotate-state/state/deliveries" / sys.argv[1] / f"{sys.argv[2]}.json"
rows = list(json.loads(p.read_text())["deliveries"].values())
for r in rows[-int(sys.argv[3] if len(sys.argv) > 3 else 4):]:
    t = r.get("target") or {}
    print(json.dumps({k: r.get(k) for k in ("id", "state", "created_at", "attempted_at", "accepted_at", "acknowledged_at", "detail")}
                     | {"handle": t.get("handle"), "pid": t.get("pid")}))
