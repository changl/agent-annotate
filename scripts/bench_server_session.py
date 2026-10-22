"""Separate-process RSS/CPU and wire bytes for an accelerated 30-minute session.

225 eight-second poll ticks, 30 content reloads and 60 writes. Simulated time
is explicit: real elapsed seconds and one actual idle minute are also measured.
All state uses tests/conftest.py and the source directory is copied read-only.
"""
import argparse
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
import conftest  # noqa: E402


def stats(pid):
    output = subprocess.run(["ps", "-p", str(pid), "-o", "rss=,time="], capture_output=True,
                            text=True, check=True, cwd=Path.home()).stdout.split()
    parts = output[1].split(":")
    cpu = sum(float(part) * 60 ** n for n, part in enumerate(reversed(parts)))
    return {"rss_mib": round(int(output[0]) / 1024, 2), "cpu_seconds": cpu}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--poll-view", default="")
    parser.add_argument("--idle-seconds", type=float, default=60)
    args = parser.parse_args()
    root = conftest._SANDBOX.resolve()
    page = root / "page"
    shutil.copytree(args.source, page, ignore=shutil.ignore_patterns("*.lock", "*.log"))
    meta = json.loads((page / "current.meta.json").read_text())
    meta.pop("owner", None)
    (page / "current.meta.json").write_text(json.dumps(meta))
    fake = root / "fake-orca"
    fake.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(1)\nprint(\'{"ok":true,"result":{}}\')\n')
    fake.chmod(0o700)
    env = {**os.environ, "ORCA_CLI_COMMAND": str(fake)}
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    store = json.loads((page / "comments.json").read_text())
    plan = next(iter(store.get("approved_plans", {})), None)
    if plan is None:
        plan = next((path.parent.name for path in (page / "plans").glob("*/meta.json")), None)
    paths = ["/comments.json" + args.poll_view, "/api/read-state", "/api/categories", "/api/session-monitor", "/api/board"]
    if plan:
        paths.append("/api/plans/" + plan)
    validators, wire = {}, {}

    def request(path, method="GET", payload=None, conditional=True):
        headers = {"Accept-Encoding": "gzip", "Connection": "close"}
        if conditional and path in validators:
            headers["If-None-Match"] = validators[path]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=90)
        try:
            conn.request(method, path, json.dumps(payload) if payload is not None else None, headers)
            response = conn.getresponse()
            data = response.read()
            if response.status not in (200, 201, 304):
                raise RuntimeError(f"{path}: {response.status} {data[:200]!r}")
            if response.getheader("ETag"):
                validators[path] = response.getheader("ETag")
            if method == "GET":
                row = wire.setdefault(path, {"200_count": 0, "304_count": 0, "body_bytes": 0, "max_body_bytes": 0})
                row[f"{response.status}_count"] += 1
                row["body_bytes"] += len(data)
                row["max_body_bytes"] = max(row["max_body_bytes"], len(data))
            return response.status
        finally:
            conn.close()

    result = {"source": str(args.source), "simulated_minutes": 30, "ticks": 225,
              "content_reloads": 30, "writes": 60, "poll_view": args.poll_view,
              "rss": [], "wire": wire, "notes": "Accelerated request-count simulation; not 30 minutes of elapsed time."}
    with (root / "server.log").open("w") as log:
        process = subprocess.Popen([sys.executable, "-m", "agent_annotate.sync_server", "--slug-dir", str(page),
                                    "--slug", "fixture", "--bus-dir", str(root / "bus"), "--port", str(port),
                                    "--strict-port", "--local-author", "bench@example.test"],
                                   env=env, stdout=log, stderr=log, cwd=Path.home())
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    request("/api/capabilities")
                    break
                except OSError:
                    if time.monotonic() >= deadline or process.poll() is not None:
                        raise RuntimeError("sandbox server failed to start: " + (root / "server.log").read_text()[-2000:])
                    time.sleep(.05)
            request("/content", conditional=False)
            for path in paths:
                request(path)
            idle_before = stats(process.pid)
            time.sleep(args.idle_seconds)
            idle_after = stats(process.pid)
            result["actual_idle_seconds"] = args.idle_seconds
            result["idle_cpu_seconds_per_minute"] = round((idle_after["cpu_seconds"] - idle_before["cpu_seconds"]) * 60 / args.idle_seconds, 4)
            result["idle_rss_mib_before_after"] = [idle_before["rss_mib"], idle_after["rss_mib"]]
            started = time.monotonic()
            initial = stats(process.pid)
            result["rss"].append({"simulated_minute": 0, **initial})
            for minute in range(1, 31):
                request("/content", conditional=False)
                request("/api/comments", "POST", {"anchor_id": "_page", "text": f"Simulated minute {minute}"}, conditional=False)
                request("/api/seen", "POST", {"version": meta["current"]}, conditional=False)
                # Alternate 7 and 8 poll cycles = 225 ticks over 30 minutes.
                for _ in range(7 + minute % 2):
                    for path in paths:
                        request(path)
                current = stats(process.pid)
                result["rss"].append({"simulated_minute": minute, **current})
                result["real_workload_seconds"] = round(time.monotonic() - started, 2)
                result["workload_cpu_seconds"] = round(current["cpu_seconds"] - initial["cpu_seconds"], 3)
                result["polling_cpu_seconds_per_simulated_minute"] = round(result["workload_cpu_seconds"] / minute, 3)
                args.output.write_text(json.dumps(result, indent=2) + "\n")
                print(json.dumps({"minute": minute, **current}), flush=True)
                if current["rss_mib"] > 1500:
                    raise RuntimeError("sandbox RSS exceeded 1500 MiB; partial results retained")
            # An actual minute at the real eight-second polling cadence
            # separates a burst's allocator high-water mark from idle use.
            idle_start = time.monotonic()
            poll_idle_before = stats(process.pid)
            for tick in range(8):
                for path in paths:
                    request(path)
                time.sleep(max(0, idle_start + min(60, (tick + 1) * 8) - time.monotonic()))
            poll_idle_after = stats(process.pid)
            result["actual_polling_idle_seconds"] = round(time.monotonic() - idle_start, 2)
            result["polling_idle_cpu_seconds_per_minute"] = round(poll_idle_after["cpu_seconds"] - poll_idle_before["cpu_seconds"], 3)
            result["post_burst_idle_rss_mib"] = poll_idle_after["rss_mib"]
            args.output.write_text(json.dumps(result, indent=2) + "\n")
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
