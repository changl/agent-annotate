"""Print the last N screen lines of an Orca terminal, without the footer that shows the account."""
import json
import subprocess
import sys

out = subprocess.run(["orca", "terminal", "read", "--terminal", sys.argv[1], "--json"],
                     capture_output=True, text=True).stdout
tail = json.loads(out)["result"]["terminal"]["tail"]
for line in tail[-int(sys.argv[2] if len(sys.argv) > 2 else 15):]:
    if "@" not in line:
        print(line.rstrip())
