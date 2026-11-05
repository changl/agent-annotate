#!/usr/bin/env python3
"""Stage 5f rehearsal of page.db on copies of a Mac's pages. Never touches a live page.

    store_rehearsal.py copy DEST [SLUG ...]   clone every registered page (or the named ones), its bus,
                                              cursors and delivery journal into DEST; live servers keep running
    store_rehearsal.py run DEST [--port 18700] [SLUG ...]

`run` works only inside DEST, with the annotate roots pointed at DEST and a
fake `orca` first on PATH, and with every owner stripped from the copied
registry, so a replayed round can never reach a live session. Per page:
db import, db diff, start a sandbox server (ports 18700-18799), replay a
round (a reviewer answer or note, then Send), check the round reached
page.db, the files, the inbox and the history with db diff 0, stop the
server, db off, and check the page still serves on JSON. One line per page.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

LIVE_STATE = Path.home() / ".claude/annotate-state/state"
SRC = Path(__file__).resolve().parents[1] / "src"
_OWNER = ("owner_session", "owner_agent", "owner_label", "owner_claimed_at", "owner_target", "owner_pid")


def copy(dest: Path, only: set[str]) -> None:
    (dest / "state").mkdir(parents=True, exist_ok=True)
    for registry in sorted(LIVE_STATE.glob("*.json")):
        try:
            data = json.loads(registry.read_text())
        except ValueError:
            continue
        project = registry.stem
        slugs = {s: r for s, r in (data.get("slugs") or {}).items() if isinstance(r, dict) and (not only or s in only)
                 and Path(r.get("slug_dir") or "").is_dir()}
        if not slugs:
            continue
        for slug, record in slugs.items():
            target = dest / "pages" / project / slug
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():  # APFS clone: no extra space, the live directory is only read
                subprocess.run(["cp", "-cR", record["slug_dir"], str(target)], check=True)
            bus = Path(record.get("bus_file") or Path.home() / f".claude/annotate-bus/{project}/{slug}.ndjson")
            if bus.is_file():
                (dest / "bus" / project).mkdir(parents=True, exist_ok=True)
                shutil.copy2(bus, dest / "bus" / project / bus.name)
            for root in ("bus-offsets", "hook-offsets", "monitor-offsets"):
                for path in [*(LIVE_STATE / root).glob(f"{project}/{slug}.offset*"),
                             *(LIVE_STATE / root).glob(f"*/{project}/{slug}.offset*")]:
                    (dest / "state" / path.relative_to(LIVE_STATE)).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, dest / "state" / path.relative_to(LIVE_STATE))
            journal = LIVE_STATE / "deliveries" / project / f"{slug}.json"
            if journal.is_file():
                (dest / "state/deliveries" / project).mkdir(parents=True, exist_ok=True)
                shutil.copy2(journal, dest / "state/deliveries" / project / journal.name)
            print(f"copied {project}/{slug}")
        data["slugs"] = {s: {**{k: v for k, v in r.items() if k not in _OWNER},
                             "slug_dir": str(dest / "pages" / project / s), "transport": "local",
                             "bus_file": str(dest / "bus" / project / f"{s}.ndjson")} for s, r in slugs.items()}
        (dest / "state" / registry.name).write_text(json.dumps(data, indent=2))


def _env(dest: Path) -> dict:
    fake = dest / "bin"
    fake.mkdir(exist_ok=True)
    (fake / "orca").write_text("#!/bin/sh\necho '{}'\nexit 1\n")
    (fake / "orca").chmod(0o755)
    (dest / "config").mkdir(exist_ok=True)
    (dest / "config" / "projects.toml").write_text('[defaults]\ntransport = "local"\nport_base = 18700\n')
    return {**os.environ, "ANNOTATE_STATE_DIR": str(dest / "state"), "ANNOTATE_BUS_ROOT": str(dest / "bus"),
            "ANNOTATE_CONFIG_DIR": str(dest / "config"), "ANNOTATE_BUS_ARCHIVE_ROOT": str(dest / "bus-archive"),
            "ANNOTATE_VERSION_GUARD": "0", "ANNOTATE_SESSION_ID": "rehearsal", "PYTHONPATH": str(SRC),
            "PATH": f"{fake}{os.pathsep}{os.environ.get('PATH', '')}"}


def _annotate(env, *args) -> tuple[int, str]:
    done = subprocess.run([sys.executable, "-c", "import sys; from agent_annotate.cli import main; sys.exit(main())",
                           *args], env=env, capture_output=True, text=True, timeout=600)
    return done.returncode, (done.stdout + done.stderr).strip()


def _call(port, method, path, payload=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    try:
        connection.request(method, path, json.dumps(payload) if payload is not None else None,
                           {"Content-Type": "application/json"} if payload is not None else {})
        response = connection.getresponse()
        body = response.read()
        return response.status, body
    finally:
        connection.close()


def _serve(env, directory: Path, slug: str, bus_dir: Path, port: int):
    server = subprocess.Popen([sys.executable, "-m", "agent_annotate.sync_server", "--slug-dir", str(directory),
                               "--slug", slug, "--bus-dir", str(bus_dir), "--port", str(port), "--strict-port",
                               "--local-author", "rehearsal@example.test"],
                              env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            if _call(port, "GET", "/api/capabilities")[0] == 200:
                return server
        except OSError:
            time.sleep(0.1)
    server.kill()
    raise RuntimeError(f"server on {port} did not start")


def _open_card(directory: Path) -> str | None:
    store = json.loads((directory / "comments.json").read_text())
    meta = json.loads((directory / "current.meta.json").read_text())
    for comments in store.get("anchors", {}).values():
        for c in comments:
            if (c.get("decision_request") and not c.get("decision") and c.get("version") == meta.get("current")
                    and c.get("status") == "open" and not c.get("withdrawn")):
                return c["id"]
    return None


def rehearse(dest: Path, env: dict, project: str, slug: str, port: int) -> str:
    directory, bus = dest / "pages" / project / slug, dest / "bus" / project / f"{slug}.ndjson"
    for leftover in directory.glob("page.db*"):
        leftover.unlink()
    started = time.monotonic()
    code, imported = _annotate(env, "db", "import", f"{project}/{slug}")
    if code:
        return f"{slug} FAILED import: {imported}"
    seconds = time.monotonic() - started
    code, diff = _annotate(env, "db", "diff", f"{project}/{slug}")
    if code:
        return f"{slug} FAILED diff: {diff}"
    size = (directory / "page.db").stat().st_size
    server = _serve(env, directory, slug, bus.parent, port)
    if (directory / "archived.json").exists() or (directory / "consolidated.json").exists():
        try:  # read-only page: writes are refused exactly as on JSON
            refused = _call(port, "POST", "/api/comments", {"anchor_id": "s:x", "text": "x"})[0] == 410
            served = _call(port, "GET", "/api/comments")[0] == 200
        finally:
            server.terminate()
            server.wait(10)
        code, off = _annotate(env, "db", "off", f"{project}/{slug}")
        ok = refused and served and code == 0
        return (f"{slug} {'ok' if ok else 'FAILED'} · import {seconds:.1f} s · {size / 1e6:.1f} MB · "
                f"{diff.split(' · ', 1)[1]} · read-only page: write refused (410), reads served · db off")
    try:
        card = _open_card(directory)
        note = f"Rehearsal note {time.time_ns()}"
        if card:
            status, _ = _call(port, "POST", f"/api/comments/{card}/decision", {"verdict": "accept", "defer_push": True})
            replay = f"answered {card}"
        else:
            anchor = next(iter(json.loads((directory / "comments.json").read_text()).get("anchors") or {}), "s:rehearsal")
            status, _ = _call(port, "POST", "/api/comments", {"anchor_id": anchor, "text": note})
            replay = "note"
        if status not in (200, 201):
            return f"{slug} FAILED replay ({replay}): HTTP {status}"
        status, body = _call(port, "POST", "/api/rounds/submit", {})
        if status != 200:
            return f"{slug} FAILED send: HTTP {status} {body[:200]!r}"
        sent = json.loads(body).get("delivery_id") or json.loads(body).get("round_id")
        rounds = [json.loads(line).get("id") for line in (directory / "rounds.ndjson").read_text().split("\n") if line.strip()]
        history_status, history = _call(port, "GET", "/api/history")
        code, after = _annotate(env, "db", "diff", f"{project}/{slug}")
        _, inbox = _annotate(env, "inbox", f"{project}/{slug}", "--unread", "--json")
        try:
            events = [e.get("event") for e in json.loads(inbox).get("events", [])]
        except ValueError:
            events = []
        checks = {"round in rounds.ndjson": bool(sent) and sent in rounds,
                  "round in history": history_status == 200 and bool(sent) and sent in history.decode(),
                  "round in inbox": "round_submitted" in events,
                  "db diff 0 after the round": code == 0}
    finally:
        server.terminate()
        server.wait(10)
    code, off = _annotate(env, "db", "off", f"{project}/{slug}")
    checks["db off"] = code == 0 and "back on json" in off
    server = _serve(env, directory, slug, bus.parent, port)
    try:
        checks["serves on json"] = _call(port, "GET", "/api/comments")[0] == 200 and not (directory / "page.db").exists()
    finally:
        server.terminate()
        server.wait(10)
    failed = [name if ok or name != "db diff 0 after the round" else f"{name} ({after})"
              for name, ok in checks.items() if not ok]
    return (f"{slug} {'ok' if not failed else 'FAILED ' + ', '.join(failed)} · import {seconds:.1f} s · "
            f"{size / 1e6:.1f} MB · {diff.split(' · ', 1)[1]} · replay {replay}, sent · db off")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("action", choices=("copy", "run"))
    ap.add_argument("dest")
    ap.add_argument("slugs", nargs="*")
    ap.add_argument("--port", type=int, default=18700)
    args = ap.parse_args(argv)
    dest = Path(args.dest).resolve()
    if args.action == "copy":
        copy(dest, set(args.slugs))
        return 0
    if not 18700 <= args.port <= 18799:
        raise SystemExit("sandbox ports are 18700-18799")
    env = _env(dest)
    failed = 0
    pages = sorted(p for p in (dest / "pages").glob("*/*") if p.is_dir() and (not args.slugs or p.name in args.slugs))
    for index, page in enumerate(pages):
        line = rehearse(dest, env, page.parent.name, page.name, args.port + index % 100)
        failed += "FAILED" in line
        print(line, flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
