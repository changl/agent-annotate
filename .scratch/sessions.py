"""Resumed Claude sessions: project dir, handle, last transcript write before boot."""
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

out = subprocess.run(["pgrep", "-fl", "--", "--resume"], capture_output=True, text=True).stdout
projects = Path.home() / ".claude/projects"
for line in out.splitlines():
    parts = line.split()
    if "--resume" not in parts:
        continue
    pid, sess = parts[0], parts[parts.index("--resume") + 1]
    env = subprocess.run(["ps", "eww", "-p", pid, "-o", "command="], capture_output=True, text=True).stdout
    handle = next((t.split("=", 1)[1] for t in env.split() if t.startswith("ORCA_TERMINAL_HANDLE=")), None)
    start = subprocess.run(["ps", "-p", pid, "-o", "lstart="], capture_output=True, text=True).stdout.strip()
    hits = list(projects.glob(f"*/{sess}.jsonl"))
    where = hits[0].parent.name if hits else "?"
    # Transcript entries since resume make mtime useless; read the first user prompt instead.
    first = ""
    if hits:
        with hits[0].open() as fh:
            for raw in fh:
                if '"type":"user"' in raw and '"content":"' in raw:
                    first = raw.split('"content":"', 1)[1][:90]
                    break
    print(pid, sess, handle, start, where, first.replace("\\n", " "), sep=" | ")
