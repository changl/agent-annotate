"""Loopback route timings on copies only; no live registry, owner or transport.

PYTHONPATH=src python scripts/bench_writes.py --output /tmp/before.json
Uses the suite's sandbox before importing annotate, just like bench_http_cache.
"""
import argparse
import cProfile
import gzip
import http.client
import io
import json
import math
import os
import pstats
import shutil
import statistics
import sys
import threading
import time
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
import conftest  # noqa: E402

from agent_annotate import delivery  # noqa: E402
from agent_annotate.approval_catalog import seal_review  # noqa: E402
from agent_annotate.categories import publish_plan_revision  # noqa: E402
from agent_annotate.paths import STATE_DIR, WEB_DIR  # noqa: E402
from agent_annotate.sync_server import ReviewHTTPServer, make_handler  # noqa: E402

REQUEST_ENCODING = "identity"


def request(server, method, path, payload=None, headers=None):
    conn = http.client.HTTPConnection(*server.server_address, timeout=30)
    try:
        conn.request(method, path, json.dumps(payload) if payload is not None else None,
                     headers={"Content-Type": "application/json", "Accept-Encoding": REQUEST_ENCODING, **(headers or {})})
        response = conn.getresponse()
        body = response.read()
        if response.status not in (200, 201, 304):
            raise RuntimeError(f"{method} {path}: {response.status} {body[:400]!r}")
        decoded = gzip.decompress(body) if body and response.getheader("Content-Encoding") == "gzip" else body
        value = json.loads(decoded) if decoded and "application/json" in response.getheader("Content-Type", "") else decoded
        return response.status, dict(response.getheaders()), value
    finally:
        conn.close()


def prepare(root, source=None):
    page = (root / "page").resolve()
    if source:
        # Dereference assets into the sandbox; never retain links to live data.
        shutil.copytree(source, page, ignore=shutil.ignore_patterns("*.lock", "*.log"))
    else:
        page.mkdir(parents=True)
        (page / "comments.json").write_text('{"schema_version":2,"anchors":{},"archived":{}}')
        (page / "current.meta.json").write_text('{"current":"v1","history":[{"version":"v1"}]}')
    meta = json.loads((page / "current.meta.json").read_text())
    meta.pop("owner", None)
    version = meta["current"]
    (page / "current.meta.json").write_text(json.dumps(meta))
    store = json.loads((page / "comments.json").read_text())
    # Include one realistic image-heavy card on each copy, alongside its own cards.
    assets = page / "assets" / "benchmark"
    assets.mkdir(parents=True, exist_ok=True)
    images = []
    for n in range(40):
        name = f"assets/benchmark/{n}.png"
        (page / name).write_bytes(b"\x89PNG\r\n\x1a\n" + bytes([n]) * (512 * 1024))
        images.append(f'<img src="./{name}">')
    html = '<html><body><section data-anchor-id="bench-evidence">' + ''.join(images) + '</section></body></html>'
    cards = [{"id": f"bench-{n}", "anchor_id": "bench-evidence", "number": 10000+n,
              "text": "Benchmark card", "version": version, "status": "open", "replies": [],
              "decision_request": {"prompt": "Choose", "evidence": [{"anchor": "bench-evidence"}],
                                   "options": [{"id": "a", "label": "Option A"}]}}
             for n in range(60 if source is None else 1)]
    store["anchors"]["bench-evidence"] = cards
    (page / "comments.json").write_text(json.dumps(store))
    _, tokens = seal_review(page, html, version, store)
    publish_plan_revision(page, "benchmark", "<html><body>Plan</body></html>", title="Benchmark")
    return page, version, tokens


def measure(root, source, samples, delay, contention_only=False, bus_source=None, contention_path="/api/categories"):
    page, version, tokens = prepare(root, source)
    profile = cProfile.Profile()
    base = make_handler(page, slug=root.name, bus_dir=root / root.name, v2_mode=True,
                        local_author="bench@example.test", skill_dir=WEB_DIR)
    if bus_source:
        base.bus_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bus_source, base.bus_dir / f"{root.name}.ndjson")

    class Handler(base):
        profiling = False
        cpu = {}

        def handle_one_request(self):
            begin = time.thread_time()
            try:
                if self.profiling:
                    profile.runcall(super().handle_one_request)
                else:
                    super().handle_one_request()
            finally:
                if getattr(self, "raw_requestline", None) and getattr(self, "headers", None):
                    label = self.headers.get("X-Benchmark-Label")
                    if label:
                        self.cpu.setdefault(label, []).append((time.thread_time() - begin) * 1000)

    server = ReviewHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    proc = delivery._process(os.getpid())
    target = {"pid": os.getpid(), "process_start": proc[0], "agent": Path(proc[1]).name,
              "handle": "term_fake", "incarnation": "fake", "worktree": "fake"}
    record = {"slug_dir": str(page), "port": server.server_port,
              "bus_file": str(root / root.name / f"{root.name}.ndjson"),
              "owner_session": "benchmark", "owner_target": target, "workspace_primary": True}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    (STATE_DIR / f"{root.name}.json").write_text(json.dumps({"slugs": {root.name: record}}))
    fake = root / "fake-orca"
    fake_log = conftest._SANDBOX / "fake-orca-calls.ndjson"
    fake.write_text('#!/usr/bin/env python3\nimport json,time,sys\n'
                    f'with open({str(fake_log)!r},"a") as log: log.write(json.dumps(sys.argv)+"\\n")\n'
                    f'time.sleep({delay})\n'
                    f'terminal={{"incarnationId":"fake","worktreeId":"fake","agentIdentity":{target["agent"]!r},"connected":True,"writable":True}}\n'
                    'print(json.dumps({"ok":True,"result":{"terminal":terminal,"send":{"accepted":True,"prompt":{"stages":["input_accepted"]}}}}))\n')
    fake.chmod(0o700)
    os.environ["ORCA_CLI_COMMAND"] = str(fake)
    times, validators, statuses, wire = {}, {}, {}, {}
    original = (page / "comments.json").read_bytes()

    def call(label, method, path, payload=None):
        started = time.perf_counter()
        status, headers, body = request(server, method, path, payload, headers={"X-Benchmark-Label": label})
        times.setdefault(label, []).append((time.perf_counter() - started) * 1000)
        statuses.setdefault(label, set()).add(status)
        wire.setdefault(label, []).append(int(headers.get("Content-Length", 0)) if status != 304 else 0)
        if headers.get("ETag"):
            validators[path] = headers["ETag"]
        return body

    try:
        for iteration in range(0 if contention_only else samples):
            # Restore a fixed-size input so iteration count cannot inflate the store.
            (page / "comments.json").write_bytes(original)
            comment = call("comment create", "POST", "/api/comments", {"anchor_id": "bench-evidence", "text": "New feedback"})
            cid = comment["id"]
            call("reply", "POST", f"/api/comments/{cid}/reply", {"text": "Reply"})
            call("edit", "PUT", f"/api/comments/{cid}", {"text": "Edited feedback"})
            call("comment batch", "POST", "/api/comments/batch", {"items": [{"anchor_id": "bench-evidence", "text": "Batch feedback"}]})
            for verdict in ("accept", "select", "reject", "comment", "changes"):
                call("decision " + verdict, "POST", "/api/comments/bench-0/decision",
                     {"verdict": verdict, "text": "Option A" if verdict == "select" else "Verdict note",
                      "option_id": "a" if verdict == "select" else None, "defer_push": True,
                      "evidence": tokens["bench-0"]})
            call("verdict notes", "POST", "/api/comments/bench-0/decision",
                 {"verdict": "accept", "text": f"Note {iteration}", "defer_push": True, "evidence": tokens["bench-0"]})
            call("rounds/submit", "POST", "/api/rounds/submit", {"note": f"Round {iteration}"})
            for verdict in ("accept", "select", "reject", "comment", "changes"):
                call("immediate " + verdict, "POST", "/api/comments/bench-0/decision",
                     {"verdict": verdict, "text": f"Immediate note {iteration}", "evidence": tokens["bench-0"]})
            request(server, "POST", "/api/comments", {"anchor_id": "bench-evidence", "text": f"More feedback {iteration}"})
            call("push-session", "POST", "/api/push-session", {})
            call("push single", "POST", f"/api/comments/{cid}/push", {})
            call("archive", "POST", f"/api/comments/{cid}/archive", {})
            call("restore", "POST", f"/api/comments/{cid}/restore", {})
            call("accept comment", "POST", f"/api/comments/{cid}/accept", {})
            call("rounds/discard", "POST", "/api/rounds/discard", {})
            call("read-state write", "POST", "/api/read-state", {"items": [{"id": cid, "sig": "signature"}]})
            call("seen write", "POST", "/api/seen", {"version": version})
            for path in ("/comments.json", "/comments.json?view=poll", "/current.meta.json", "/api/read-state", "/api/seen",
                         "/api/categories", "/api/session-monitor", "/api/board", "/api/plans/benchmark",
                         "/api/history", "/api/project", "/api/copy", "/api/delivery", "/api/identity", "/api/capabilities"):
                call("GET " + path, "GET", path)
                started = time.perf_counter()
                label = "conditional " + path
                status, headers, _ = request(server, "GET", path, headers={"If-None-Match": validators.get(path, '"missing"'), "X-Benchmark-Label": label})
                times.setdefault(label, []).append((time.perf_counter() - started) * 1000)
                statuses.setdefault(label, set()).add(status)
                wire.setdefault(label, []).append(int(headers.get("Content-Length", 0)) if status != 304 else 0)
        # Rendering the real document seals its evidence view, so measure load
        # after writes rather than replacing the synthetic image-card view
        # between accept/select samples.
        for _ in range(0 if contention_only or not (page / "current.html").is_file() else samples):
            for path in ("/", "/content"):
                call("GET " + path, "GET", path)
        if contention_only:
            for iteration in range(samples):
                errors = []

                def poll():
                    try:
                        request(server, "GET", contention_path)
                    except Exception as exc:
                        errors.append(str(exc))
                poller = threading.Thread(target=poll)
                poller.start()
                time.sleep(.05)  # give the real categories route the shared lock
                call("comment create during " + contention_path, "POST", "/api/comments", {"anchor_id": "bench-evidence", "text": f"Concurrent {iteration}"})
                poller.join(timeout=30)
                if errors or poller.is_alive():
                    raise RuntimeError(f"concurrent poll failed: {errors}")
        slowest = max((k for k in times if not k.startswith(("GET", "conditional"))), key=lambda k: statistics.median(times[k]))
        # Profile a full pass separately so profiling overhead is absent from timings.
        Handler.profiling = True
        request(server, "POST", "/api/comments/bench-0/decision", {"verdict": "accept", "text": "profile", "defer_push": True, "evidence": tokens["bench-0"]})
        Handler.profiling = False
        stream = io.StringIO()
        pstats.Stats(profile, stream=stream).sort_stats("cumulative").print_stats(30)
        write_profile = stream.getvalue()
        profile.clear()
        # Force a new history revision, then profile cold and warm reads separately.
        request(server, "POST", "/api/comments", {"anchor_id": "bench-evidence", "text": "History profile"})
        Handler.profiling = True
        request(server, "GET", "/api/history")
        Handler.profiling = False
        stream = io.StringIO()
        pstats.Stats(profile, stream=stream).sort_stats("cumulative").print_stats(30)
        return {"source": str(source) if source else "synthetic: 60 cards, 40 x 512 KiB images",
                "fake_orca_calls_started": sum(str(fake) in line for line in fake_log.read_text().splitlines()) if fake_log.exists() else 0,
                "comments_bytes": len(original), "fake_orca_seconds": delay, "samples": samples,
                "bus_source": str(bus_source) if bus_source else None,
                "accept_encoding": REQUEST_ENCODING,
                "slowest_write": slowest, "profile_decision_accept": write_profile, "profile_history": stream.getvalue(),
                "routes": {k: {"p50": round(statistics.median(v), 2), "p95": round(sorted(v)[math.ceil(len(v)*.95)-1], 2),
                               "max": round(max(v), 2), "statuses": sorted(statuses[k]),
                               "body_bytes_p50": statistics.median(wire[k]),
                               "server_cpu_p50_ms": round(statistics.median(Handler.cpu.get(k, [0])), 2)} for k, v in times.items()}}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def main():
    global REQUEST_ENCODING
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--orca-delay", type=float, default=1)
    parser.add_argument("--source", type=Path, action="append")
    parser.add_argument("--no-synthetic", action="store_true")
    parser.add_argument("--contention-only", action="store_true")
    parser.add_argument("--bus-source", type=Path)
    parser.add_argument("--contention-path", default="/api/categories")
    parser.add_argument("--accept-encoding", choices=("identity", "gzip"), default="identity")
    args = parser.parse_args()
    REQUEST_ENCODING = args.accept_encoding
    sources = args.source or [Path("/Users/changlee/projects/agent-annotate/reviews/annotate-conformity-20260927"),
                              Path("/Users/changlee/projects/agent-annotate/reviews/annotate-assessment-20260917")]
    results = []
    for n, source in enumerate(sources if args.no_synthetic else [*sources, None]):
        # Retain diagnostics without flooding the benchmark output.
        with (conftest._SANDBOX / f"fixture-{n}.log").open("w") as log, redirect_stdout(log):
            result = measure(conftest._SANDBOX / f"fixture-{n}", source, args.samples, args.orca_delay,
                             args.contention_only, args.bus_source, args.contention_path)
        results.append(result)
        args.output.write_text(json.dumps(results, indent=2))
        print(json.dumps({"fixture": result["source"], "writes": {k: v for k, v in result["routes"].items() if not k.startswith(("GET", "conditional"))}}), flush=True)


if __name__ == "__main__":
    main()
