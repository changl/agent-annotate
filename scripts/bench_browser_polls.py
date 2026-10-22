"""Measure real shell polling on a private copy, using tests/conftest.py isolation.

Set PYTHONPATH to the source revision being measured. No timer acceleration or
synthetic fetch loop: the selected revision's shell runs for three idle minutes.
"""
import argparse
import collections
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
import conftest  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


def cpu_seconds(pid):
    value = subprocess.check_output(["ps", "-p", str(pid), "-o", "time="], text=True).strip()
    return sum(float(part) * 60 ** n for n, part in enumerate(reversed(value.split(":"))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=float, default=180)
    args = parser.parse_args()
    root = conftest._SANDBOX
    directory = root / "page"
    shutil.copytree(args.source, directory, ignore=shutil.ignore_patterns("*.lock", "*.log"))
    meta_path = directory / "current.meta.json"
    meta = json.loads(meta_path.read_text())
    source_meta_bytes = meta_path.stat().st_size
    source_meta_sha256 = hashlib.sha256(meta_path.read_bytes()).hexdigest()
    meta.pop("owner", None)
    meta_path.write_text(json.dumps(meta))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}/"
    # Record a sandbox Funnel origin so the baseline exercises its production
    # no-store metadata branch. Traffic remains on loopback; no TLS/route changes.
    record = {"slug_dir": str(directory), "port": port, "transport": "funnel",
              "url": f"https://127.0.0.1:{port}/", "workspace_primary": True}
    (root / "state").mkdir(exist_ok=True)
    (root / "state/project.json").write_text(json.dumps({"slugs": {"fixture": record}}))
    server_code = """
import sys
from pathlib import Path
from agent_annotate.sync_server import ReviewHTTPServer, make_handler
from agent_annotate import sync_server
directory, port, bus = Path(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
handler = make_handler(directory, v2_mode=True, slug='fixture', bus_dir=bus,
                       skill_dir=Path(sync_server.__file__).parent / 'web',
                       local_author='bench@example.test')
ReviewHTTPServer(('127.0.0.1', port), handler).serve_forever()
"""
    env = {**os.environ, "ORCA_CLI_COMMAND": "/usr/bin/false"}
    endpoints = {"/comments.json", "/api/read-state", "/api/session-monitor", "/api/categories", "/api/board",
                 "/current.meta.json", "/api/delivery", "/api/history", "/api/project"}
    with (root / "server.log").open("w") as log:
        server = subprocess.Popen([sys.executable, "-c", server_code, str(directory), str(port), str(root / "bus/project")],
                                  env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    with urllib.request.urlopen(base + "api/capabilities", timeout=1):
                        break
                except OSError:
                    if time.monotonic() > deadline or server.poll() is not None:
                        raise RuntimeError((root / "server.log").read_text()[-2000:])
                    time.sleep(.05)
            with sync_playwright() as runner:
                browser = runner.chromium.launch(
                    executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless=True)
                context = browser.new_context(viewport={"width": 1440, "height": 960})
                # The fixture can contain remote media. Deny every non-loopback
                # URL; pollJson already bypasses browser caching itself.
                context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(base) else route.abort())
                page = context.new_page()
                cdp = context.new_cdp_session(page)
                cdp.send("Network.enable")
                requests, responses, finished = {}, {}, []
                measuring = [False]

                def requested(event):
                    path = urllib.parse.urlsplit(event["request"]["url"]).path
                    if measuring[0] and event["request"]["method"] == "GET" and (
                            path in endpoints or path.startswith("/api/plans/")):
                        requests[event["requestId"]] = path

                def responded(event):
                    if event["requestId"] in requests:
                        responses[event["requestId"]] = event["response"]

                def loaded(event):
                    request_id = event["requestId"]
                    if request_id in responses:
                        response = responses.pop(request_id)
                        headers = {key.lower(): value for key, value in response["headers"].items()}
                        finished.append({"path": requests.pop(request_id), "status": int(response["status"]),
                                         "wire_bytes": event["encodedDataLength"],
                                         "body_bytes": int(headers.get("content-length", 0)) if response["status"] != 304 else 0})

                cdp.on("Network.requestWillBeSent", requested)
                cdp.on("Network.responseReceived", responded)
                cdp.on("Network.loadingFinished", loaded)
                page.goto(base + "#view=review", wait_until="networkidle", timeout=60000)
                page.locator('body[data-ready="1"]').wait_for(timeout=30000)
                # The first normal timer poll picks up content stamps written
                # while the iframe bootstraps. Exclude that real change from idle.
                with page.expect_response(lambda response: response.url.endswith("/current.meta.json"), timeout=30000):
                    page.wait_for_timeout(9000)
                before_cpu = cpu_seconds(server.pid)
                started = time.monotonic()
                measuring[0] = True
                while time.monotonic() - started < args.seconds:
                    page.wait_for_timeout(min(1000, max(1, (args.seconds - (time.monotonic() - started)) * 1000)))
                elapsed = time.monotonic() - started
                after_cpu = cpu_seconds(server.pid)
                measuring[0] = False
                rows = {}
                for item in finished:
                    row = rows.setdefault(item["path"], {"body_bytes": 0, "wire_bytes": 0, "statuses": collections.Counter()})
                    row["body_bytes"] += item["body_bytes"]
                    row["wire_bytes"] += item["wire_bytes"]
                    row["statuses"][str(item["status"])] += 1
                assert rows.get("/current.meta.json"), "review document must actually poll metadata"
                assert all(int(status) in (200, 304) for row in rows.values() for status in row["statuses"]), rows
                result = {"source_fixture": args.source.name, "fixture_meta_bytes": meta_path.stat().st_size,
                          "source_meta_bytes": source_meta_bytes, "source_meta_sha256": source_meta_sha256,
                          "version_files": len(list((directory / "versions").glob("v*.html"))),
                          "history_versions": len(meta.get("history", [])), "elapsed_seconds": round(elapsed, 3),
                          "cpu_seconds_per_minute": round((after_cpu - before_cpu) * 60 / elapsed, 4),
                          "body_bytes_per_minute": round(sum(row["body_bytes"] for row in rows.values()) * 60 / elapsed, 2),
                          "wire_bytes_per_minute": round(sum(row["wire_bytes"] for row in rows.values()) * 60 / elapsed, 2),
                          "poll_endpoints": rows, "requests_in_flight_at_end": len(requests),
                          "notes": "Real browser timers, warmed bootstrap excluded; private copy and isolated state, no external traffic; no synthetic polling."}
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, indent=2) + "\n")
                print(json.dumps(result), flush=True)
                browser.close()
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    main()
