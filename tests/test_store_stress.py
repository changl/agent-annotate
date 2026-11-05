"""Stage 5e: concurrent writers lose nothing on page.db; kill -9 mid-write recovers."""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "store_stress.py"


def _run(*args):
    env = {**os.environ, "PYTHONPATH": str(SCRIPT.parents[1] / "src")}
    done = subprocess.run([sys.executable, str(SCRIPT), "--json", *args], env=env, capture_output=True,
                          text=True, timeout=600)
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_no_lost_writes_on_sqlite_or_json():
    for backend in ("sqlite", "json"):
        result = _run("--backend", backend, "--writes", "400")
        assert (result["lost"], result["failures"]) == ([], []), backend
    assert result["differences"] is None


def test_the_harness_sees_a_lost_update():
    """The CLI's meta write before it took current.meta.json.lock loses writes here."""
    assert any(_run("--backend", "json", "--writes", "400", "--unlocked-meta")["lost"] for _ in range(3))


def test_kill_9_mid_write_recovers():
    result = _run("--kill", "--kills", "5")
    assert result["problems"] == [] and result["mid_write"] >= 1
    assert int(result["counts"]["store_recovered"]) >= 1
