"""Sandbox owner record, delivery journal and resume markers (run through ./aa py)."""
import json

from agent_annotate import paths

record = json.loads((paths.STATE_DIR / "proof.json").read_text())["slugs"]["proof-page"]
target = record.get("owner_target") or {}
print("owner", record.get("owner_session"), target.get("handle"), target.get("pid"), target.get("process_start"))
journal = paths.STATE_DIR / "deliveries" / "proof" / "proof-page.json"
if journal.exists():
    for row in json.loads(journal.read_text())["deliveries"].values():
        stages = (row.get("receipt") or {}).get("prompt", {}).get("stages")
        print("send", row["id"], row["state"], (row.get("target") or {}).get("handle"), stages, row.get("detail"))
for marker in sorted((paths.STATE_DIR / "resumes").glob("*.json")):
    row = json.loads(marker.read_text())
    stages = (row.get("receipt") or {}).get("prompt", {}).get("stages")
    print("resume", marker.name, row["state"], row["via"], row["target"]["handle"], stages, row.get("detail"))
