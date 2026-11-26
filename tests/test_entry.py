import os
import subprocess
import sys
from pathlib import Path

import agent_annotate

PROBE = """
import sys
sys.argv = ["annotate"] + sys.argv[1:]
from agent_annotate import entry
try:
    entry.main()
except SystemExit as exit:
    heavy = any(m in sys.modules for m in ("agent_annotate.cli", "agent_annotate.updates", "urllib.request"))
    sys.stderr.write("heavy=%s code=%s" % (heavy, exit.code))
"""


def _run(*args):
    env = {**os.environ, "PYTHONPATH": str(Path(agent_annotate.__file__).parents[1])}
    return subprocess.run([sys.executable, "-c", PROBE, *args], input='{"session_id": "entry-test"}',
                          capture_output=True, text=True, env=env, timeout=60)


def test_the_prompt_hook_skips_the_full_cli_and_the_update_checker():
    assert _run("hook-check").stderr.endswith("heavy=False code=0")


def test_other_commands_still_reach_the_cli():
    proc = _run("--version")
    assert proc.stdout.startswith("agent-annotate ")
    assert proc.stderr.endswith("heavy=True code=0")
