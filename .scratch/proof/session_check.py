"""Read-only: does the Claude session-file lookup find the annotate orchestrator's live pid?"""
from agent_annotate import delivery

session = "3c3ae250-871e-46d2-874e-f294e25585bd"
pids = delivery._resumed_pids(session, "claude")
print("pids", pids)
for pid in pids:
    data = delivery._claude_session(pid) or {}
    print(pid, data.get("sessionId") == session, data.get("status"))
print("fork id finds", delivery._resumed_pids("00000000-fork-not-live", "claude"))
