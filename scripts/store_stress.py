#!/usr/bin/env python3
"""Concurrency stress for a page's record store (Stage 5e).

4 server threads (HTTP requests to an in-process page server) and 4 CLI
processes make mixed writes to one page at once; every write leaves a unique
token, and afterwards every token must be found:

  server  content stamp for a new version (current.meta.json), a new comment
          (comments.json), a read-state entry (read-state.json)
  CLI     a meta token through the CLI's meta writer, a reply through a
          comment-store transaction, a round (rounds.ndjson)

    store_stress.py [--backend json|sqlite] [--writes 1000] [--unlocked-meta]
    store_stress.py --kill [--kills 10]

--unlocked-meta makes the CLI processes write meta the way the CLI did before
it took current.meta.json.lock (read, modify, write with no lock): the race
_merge_content_stamp documents. It must lose writes, which proves this
harness sees a lost update. --kill runs kill -9 against a writer in the
middle of multi-file transactions and checks the page recovers.

One line out: `sqlite · 1,000 writes · 4 server threads + 4 CLI processes · 0 lost · db diff 0 · 3.1 s`.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import random
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ANCHOR = "s:stress"


def make_page(root: Path, versions: int) -> Path:
    page = root / "page"
    for folder in ("versions", "content"):
        (page / folder).mkdir(parents=True)
    card = {"id": "card", "anchor_id": ANCHOR, "version": "v1", "number": 1, "author": "agent:test",
            "status": "open", "text": "Stress", "replies": []}
    (page / "comments.json").write_text(json.dumps({"schema_version": 2, "anchors": {ANCHOR: [card]}, "archived": {}}))
    (page / "current.meta.json").write_text(json.dumps({"current": "v1", "history": [{"version": "v1", "ts": "t"}]}))
    for n in range(1, versions + 1):
        html = f'<html><body><section data-anchor-id="{ANCHOR}">v{n}</section></body></html>'
        (page / "versions" / f"v{n}.html").write_text(html)
        (page / "content" / f"v{n}.html").write_text(html)
    (root / "bus").mkdir()
    return page


def _request(port: int, method: str, path: str, payload=None) -> int:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    try:
        body = json.dumps(payload) if payload is not None else None
        connection.request(method, path, body, {"Content-Type": "application/json"} if body else {})
        response = connection.getresponse()
        response.read()
        return response.status
    finally:
        connection.close()


def server_writes(port: int, worker: int, count: int, versions: list[int], failures: list) -> None:
    for i in range(count):
        kind, token = i % 3, f"s{worker}-{i}"
        if kind == 0 and versions:
            status = _request(port, "GET", f"/content?v=v{versions.pop()}")
        elif kind == 1:
            status = _request(port, "POST", "/api/comments", {"anchor_id": ANCHOR, "text": token})
        else:
            status = _request(port, "POST", "/api/read-state", {"items": [{"id": token, "sig": "x"}]})
        if status not in (200, 201):
            failures.append(f"{token}: HTTP {status}")


def cli_worker(page: Path, worker: int, count: int, unlocked: bool) -> None:
    from agent_annotate import cli, store
    for i in range(count):
        kind, token = i % 3, f"c{worker}-{i}"
        if kind == 0:
            if unlocked:  # the CLI's meta write before it took current.meta.json.lock
                meta = json.loads((page / "current.meta.json").read_text())
                meta.setdefault("stress", []).append(token)
                time.sleep(0.002)
                tmp = page / f"current.meta.json.{os.getpid()}.tmp"
                tmp.write_text(json.dumps(meta, indent=2))
                os.replace(tmp, page / "current.meta.json")
            else:
                cli._write_meta_locked(page, lambda meta, token=token: meta.setdefault("stress", []).append(token))
        elif kind == 1:
            with store.transaction(page):
                data = cli._coerce_store_file(page)
                data["anchors"][ANCHOR][0]["replies"].append({"author": "agent:stress", "text": token})
                store.write_json(page / "comments.json", data)
        else:
            store.append_round(page, {"id": token, "ts": "t"})


def check(page: Path, writes: int, versions: int) -> list[str]:
    per = writes // 8
    meta = json.loads((page / "current.meta.json").read_text())
    store = json.loads((page / "comments.json").read_text())
    read_state = json.loads((page / "read-state.json").read_text()) if (page / "read-state.json").exists() else {}
    rounds = {json.loads(line)["id"] for line in (page / "rounds.ndjson").read_text().split("\n") if line.strip()}
    comments = {c.get("text") for c in store["anchors"].get(ANCHOR, [])}
    replies = {r.get("text") for c in store["anchors"].get(ANCHOR, []) for r in c.get("replies") or []}
    stamps = set((meta.get("content_stamps") or {}))
    tokens = set(meta.get("stress") or [])
    seen = {key for entries in read_state.values() for key in entries}
    lost = []
    for w in range(4):
        for i in range(per):
            server, client = f"s{w}-{i}", f"c{w}-{i}"
            if i % 3 == 1 and server not in comments:
                lost.append(f"comment {server}")
            if i % 3 == 2 and server not in seen:
                lost.append(f"read-state {server}")
            if i % 3 == 0 and client not in tokens:
                lost.append(f"meta {client}")
            if i % 3 == 1 and client not in replies:
                lost.append(f"reply {client}")
            if i % 3 == 2 and client not in rounds:
                lost.append(f"round {client}")
    lost += [f"stamp v{n}" for n in range(2, versions + 1) if f"v{n}" not in stamps]
    return lost


def run(backend: str, writes: int, unlocked: bool) -> dict:
    from agent_annotate import store, sync_server
    started = time.monotonic()
    root = Path(tempfile.mkdtemp(prefix="aa-stress-"))
    per = writes // 8
    stamp_writes = sum(1 for i in range(per) if i % 3 == 0) * 4
    page = make_page(root, stamp_writes + 1)
    if backend == "sqlite":
        store.import_page(page, project="stress", slug="page", bus_file=root / "bus" / "page.ndjson")
    handler = sync_server.make_handler(page, slug="page", bus_dir=root / "bus", local_author="reviewer@example.test")
    httpd = sync_server.ReviewHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    versions = list(range(2, stamp_writes + 2))
    random.shuffle(versions)
    failures: list[str] = []
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}
    workers = [subprocess.Popen([sys.executable, __file__, "--worker", str(w), "--page", str(page),
                                 "--count", str(per), *(["--unlocked-meta"] if unlocked else [])], env=env)
               for w in range(4)]
    threads = [threading.Thread(target=server_writes, args=(httpd.server_port, w, per, versions, failures))
               for w in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    codes = [worker.wait() for worker in workers]
    httpd.shutdown()
    lost = check(page, writes, stamp_writes + 1)
    differences = None
    if backend == "sqlite":
        with store.transaction(page) as tx:
            sources = store.Sources(page, project="stress", slug="page", bus_file=root / "bus" / "page.ndjson")
            differences = store.diff(tx.conn, sources)[0]
    return {"backend": backend, "writes": per * 8, "lost": lost, "failures": failures + [f"worker exit {c}" for c in codes if c],
            "differences": differences, "seconds": time.monotonic() - started, "page": str(page)}


def kill_worker(page: Path) -> None:
    """Publish-shaped transactions forever: comments, meta, a draft and cards in one."""
    from agent_annotate import cli, store
    (page / ".review-drafts").mkdir(exist_ok=True)
    n = int(json.loads((page / "current.meta.json").read_text())["current"][1:]) + 1
    while True:
        with store.transaction(page):
            data = cli._coerce_store_file(page)
            data["anchors"][ANCHOR][0]["replies"].append({"text": f"k{n}", "pad": "x" * 20000})
            store.write_json(page / "comments.json", data)
            store.write_json(page / ".review-drafts" / f"v{n}.json", {"version": f"v{n}", "label": "k"})
            store.write_text(page / "cards.json", json.dumps([{"n": n}]) + "\n")
            cli._write_meta_locked(page, lambda meta, n=n: meta.update(current=f"v{n}"))
            store.remove(page / ".review-drafts" / f"v{n}.json")
        n += 1


def run_kills(kills: int) -> dict:
    from agent_annotate import store
    started = time.monotonic()
    root = Path(tempfile.mkdtemp(prefix="aa-stress-kill-"))
    page = make_page(root, 1)
    bus = root / "bus" / "page.ndjson"
    store.import_page(page, project="stress", slug="page", bus_file=bus)
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(p for p in sys.path if p)}
    problems, recovered = [], 0
    for k in range(kills):
        worker = subprocess.Popen([sys.executable, __file__, "--kill-worker", "--page", str(page)], env=env)
        time.sleep(0.3 + random.random() * 0.4)
        worker.send_signal(signal.SIGKILL)
        worker.wait()
        recovered += (page / "page.db.writing").exists()
        with store.transaction(page) as tx:     # the next writer repairs
            differences = store.diff(tx.conn, store.Sources(page, project="stress", slug="page", bus_file=bus))[0]
            check_ok = tx.conn.execute("PRAGMA integrity_check").fetchone()[0]
        if differences or check_ok != "ok" or (page / "page.db.writing").exists():
            problems.append(f"kill {k}: {differences[:3]} integrity {check_ok}")
        for name in ("comments.json", "current.meta.json"):
            json.loads((page / name).read_text())   # never a torn file
    conn = store.connect(page / "page.db")
    counts = dict(conn.execute("SELECT key, value FROM meta WHERE key LIKE 'store_%'"))
    conn.close()
    return {"kills": kills, "mid_write": recovered, "problems": problems, "counts": counts,
            "seconds": time.monotonic() - started}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--backend", choices=("json", "sqlite"), default="sqlite")
    ap.add_argument("--writes", type=int, default=1000)
    ap.add_argument("--unlocked-meta", action="store_true")
    ap.add_argument("--kill", action="store_true")
    ap.add_argument("--kills", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--worker", type=int, help=argparse.SUPPRESS)
    ap.add_argument("--kill-worker", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--page", help=argparse.SUPPRESS)
    ap.add_argument("--count", type=int, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    if not os.environ.get("ANNOTATE_STATE_DIR"):  # never the live estate: workers inherit this sandbox
        sandbox = Path(tempfile.mkdtemp(prefix="aa-stress-state-"))
        for name, sub in (("ANNOTATE_STATE_DIR", "state"), ("ANNOTATE_BUS_ROOT", "bus"),
                          ("ANNOTATE_CONFIG_DIR", "config"), ("ANNOTATE_BUS_ARCHIVE_ROOT", "archive")):
            os.environ[name] = str(sandbox / sub)
        os.environ["ANNOTATE_VERSION_GUARD"] = "0"
    if args.worker is not None:
        cli_worker(Path(args.page), args.worker, args.count, args.unlocked_meta)
        return 0
    if args.kill_worker:
        kill_worker(Path(args.page))
        return 0
    if args.kill:
        result = run_kills(args.kills)
        print(json.dumps(result) if args.json else
              f"kill -9 × {result['kills']} · {result['mid_write']} mid-write · "
              f"{len(result['problems'])} problems · {result['seconds']:.1f} s")
        return 1 if result["problems"] else 0
    import contextlib
    with contextlib.redirect_stdout(sys.stderr):  # the page server logs each request
        result = run(args.backend, args.writes, args.unlocked_meta)
    diff = "" if result["differences"] is None else f" · db diff {len(result['differences'])}"
    race = " (unlocked CLI meta writer)" if args.unlocked_meta else ""
    print(json.dumps(result) if args.json else
          f"{result['backend']}{race} · {result['writes']:,} writes · 4 server threads + 4 CLI processes · "
          f"{len(result['lost'])} lost{diff} · {len(result['failures'])} failed requests · {result['seconds']:.1f} s")
    return 1 if result["lost"] or result["failures"] or result["differences"] else 0


if __name__ == "__main__":
    sys.exit(main())
