"""Compare recorded owner worktree ids with the resumed terminal's worktree id."""
import json
import subprocess
from pathlib import Path

STATE = Path.home() / ".claude/annotate-state/state"
pairs = {"FLD usage audit": ("page", "term_18941829-e4a5-4809-9587-1e6b59ae3f6e"),
         "leadory": ("wind-down-plan", "term_10527dac-4040-4699-886d-a2edf70714d2"),
         "cheerticketing": ("ui-revamp-2026-11", "term_5b205216-aa3a-41ac-841b-9694f9be241d"),
         "multimac-orch": ("storage", "term_354f206e-2c04-4514-828a-a29f17508f70")}
for project, (slug, handle) in pairs.items():
    rec = json.loads((STATE / f"{project}.json").read_text())["slugs"][slug]
    out = subprocess.run(["orca", "terminal", "show", "--terminal", handle, "--json"],
                         capture_output=True, text=True).stdout
    term = json.loads(out)["result"]["terminal"]
    print(project, rec["owner_target"].get("worktree"), term["worktreeId"],
          rec["owner_target"].get("agent"), term["agentIdentity"])
