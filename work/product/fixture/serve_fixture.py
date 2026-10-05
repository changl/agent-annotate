#!/usr/bin/env python3
"""Run main's server on the isolated Rebex fixture with a fixed local identity."""
from __future__ import annotations

import argparse
import json
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from build_fixture import LOCAL_AUTHOR, LOCAL_AUTHOR_NAME, SANDBOX, sandbox_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8980)
    parser.add_argument("--state", type=Path, default=SANDBOX / "fixture")
    args = parser.parse_args()
    if not 8980 <= args.port <= 8982:
        parser.error("Slice B owns 8980–8983; choose 8980–8982 (Linked page uses N+1)")
    state = args.state.absolute()
    sandbox_environment(state)
    from agent_annotate.sync_server import _atomic_write_json
    registry_path = state / "state/Rebex.json"
    registry = json.loads(registry_path.read_text())
    # Refuse occupied ports before starting either page. Main's fallback port
    # discovery would otherwise make the registered links inaccurate.
    for port in (args.port, args.port + 1):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    processes = []
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        for offset, slug in enumerate(("rebex", "rebex-motion-lab")):
            record = registry["slugs"][slug]
            port = args.port + offset
            record.update(port=port, local_url=f"http://127.0.0.1:{port}/", url=f"http://127.0.0.1:{port}/")
            command = [sys.executable, "-m", "agent_annotate.sync_server", "--slug-dir", record["slug_dir"],
                       "--slug", slug, "--port", str(port), "--strict-port", "--bus-dir", str(state / "bus/Rebex"),
                       "--local-author", LOCAL_AUTHOR, "--local-author-name", LOCAL_AUTHOR_NAME]
            process = subprocess.Popen(command)
            processes.append(process)
            record["pid"] = process.pid
        _atomic_write_json(registry_path, registry)
        print(f"Rebex: http://127.0.0.1:{args.port}/\nLinked motion lab: http://127.0.0.1:{args.port + 1}/", flush=True)
        while not stopping:
            if any(process.poll() is not None for process in processes):
                raise RuntimeError("fixture server exited unexpectedly")
            time.sleep(0.2)
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
