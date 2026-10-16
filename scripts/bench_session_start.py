"""Measure the installed hook command against 40 isolated page records; no services."""

import hashlib
import json
import os
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "src/agent_annotate/hooks/session_start.py"


def measure(command, env, cwd):
    wall, cpu, output = [], [], ""
    for _ in range(21):
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        start = time.perf_counter()
        result = subprocess.run(command, input=json.dumps({"cwd": str(cwd)}), env=env,
                                capture_output=True, text=True, check=True, timeout=10)
        wall.append((time.perf_counter() - start) * 1000)
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu.append((after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime) * 1000)
        output = result.stdout
        assert not result.stderr
    line = json.loads(output)["systemMessage"] if output else ""
    return {"median_ms": round(statistics.median(wall), 2), "p95_ms": round(sorted(wall)[19], 2),
            "median_cpu_ms": round(statistics.median(cpu), 2), "line_chars": len(line),
            "wire_bytes": len(output.encode())}


def main():
    with tempfile.TemporaryDirectory(prefix="annotate-session-bench-") as temporary:
        root = Path(temporary)
        state, page, repo = (root / name for name in ("state", "page", "repo"))
        for directory in (state, page, repo):
            directory.mkdir()
        subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), "config", "remote.origin.url",
                        "https://example.test/team/project.git"], check=True)
        (page / "comments.json").write_text(json.dumps({"anchors": {
            "d:q1": [{"status": "open", "decision_request": {"prompt": "Ship?"}}]}}))
        keys = state / "review-keys"
        keys.mkdir()
        (keys / (hashlib.sha256(str(page.resolve()).encode()).hexdigest() + ".key")).write_text("a" * 43)
        records = {f"page-{index}": {"slug_dir": str(page), "workspace_repos": [
            "git:example.test/team/" + ("project" if index == 0 else str(index))],
            "workspace_folders": [], "transport": "funnel", "workspace_primary": True,
            "url": "https://macbook-pro.tail2b8ab9.ts.net/annotate/reviews/project/"} for index in range(40)}
        (state / "project.json").write_text(json.dumps({"project": "project", "slugs": records}))
        env = {**os.environ, "ANNOTATE_STATE_DIR": str(state), "ANNOTATE_CONFIG_DIR": str(root / "config"),
               "ANNOTATE_VERSION_GUARD": "0"}
        hook = [sys.executable, "-S", str(HOOK)]
        print(json.dumps({"records": 40, "runs": 21,
                          "match": measure(hook, env, repo), "silent": measure(hook, env, root),
                          "python_startup": measure([sys.executable, "-S", "-c", "pass"], env, root)}, indent=2))


if __name__ == "__main__":
    main()
