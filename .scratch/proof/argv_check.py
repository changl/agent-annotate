"""Read-only: exact argv of this process and of a shell whose argument contains spaces."""
import os
import subprocess

from agent_annotate import delivery

print(delivery._argv(os.getpid()))
child = subprocess.Popen(["sleep", "5"])
print(delivery._argv(child.pid))
child.kill()
spaced = subprocess.Popen(["/bin/sh", "-c", "sleep 5", "resume OLD-ID please"])
print(delivery._argv(spaced.pid))
spaced.kill()
