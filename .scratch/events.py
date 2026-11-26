"""Count bus event types across all buses (read-only)."""
import collections
import json
from pathlib import Path

counts = collections.Counter()
for bus in (Path.home() / ".claude/annotate-bus").glob("*/*.ndjson"):
    for line in bus.read_bytes().splitlines()[-200:]:
        try:
            counts[json.loads(line).get("event")] += 1
        except Exception:
            pass
for event, n in counts.most_common():
    print(n, event)
