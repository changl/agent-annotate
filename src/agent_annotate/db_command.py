"""`annotate db`: move a page's records into page.db and back (operator only)."""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import store


def storage_lines() -> list[str]:
    from .cli import _registry_entries
    lines = []
    for project, slug, record in _registry_entries():
        directory = Path(record.get("slug_dir") or "")
        backend = "page.db" if record.get("slug_dir") and store.backend(directory) == "sqlite" else "JSON"
        reason = record.get("db_hold") or record.get("db_reason") or ""
        if backend == "JSON" and directory.resolve().is_relative_to(Path("/Volumes")):
            reason = "page.db refused under /Volumes"
        lines.append(f"storage {project}/{slug}: {backend}" + (f" ({reason})" if backend == "JSON" and reason else ""))
    return lines


def _pages(args) -> list[tuple[str, str, dict]]:
    from .cli import _registry_entries
    entries = [(p, s, r) for p, s, r in _registry_entries() if Path(r.get("slug_dir") or "").is_dir()]
    if getattr(args, "all", False):
        return entries
    if not args.slug:
        raise ValueError("name a page · fix: annotate db import SLUG (or --all)")
    found = [(p, s, r) for p, s, r in entries if args.slug in (s, f"{p}/{s}")]
    if len(found) != 1:
        raise ValueError(f"{args.slug}: {'no registered page' if not found else 'several pages'} · fix: use PROJECT/SLUG")
    return found


def _sources_args(project: str, slug: str, record: dict) -> dict:
    return {"project": project, "slug": slug, "bus_file": record.get("bus_file")}


def _import(project, slug, record, args) -> str:
    from .cli import _running_servers
    directory = Path(record["slug_dir"])
    if not args.trial and _running_servers().get(str(directory.resolve())):
        return f"{slug} not imported: its server is running · fix: stop the page server first"
    try:
        r = store.import_page(directory, **_sources_args(project, slug, record), dry_run=args.trial)
    except store.Refused as exc:
        return f"{slug} not imported: {len(exc.rows)} problem(s) · first: {exc.rows[0]}"
    except (OSError, ValueError) as exc:
        return f"{slug} not imported: {exc}"
    shared = f" · {len(r['shared_numbers'])} legacy numbers on two anchors" if r.get("shared_numbers") else ""
    verb = "would import" if args.trial else "imported"
    return (f"{slug} {verb} · {r['items']:,} items · {r['versions']:,} versions · {r['events']:,} events · "
            f"diff 0 · {r['seconds']:.1f} s{shared}")


def _diff(project, slug, record) -> tuple[str, list[str]]:
    directory = Path(record["slug_dir"])
    if not (directory / store.DB_NAME).is_file():
        return f"{slug} json · no {store.DB_NAME}", []
    with store.transaction(directory) as tx:  # takes in other writers' files and bus lines first
        sources = store.Sources(directory, **_sources_args(project, slug, record))
        differences = store.refresh_cursors(tx.conn, sources)
        differences += store.diff(tx.conn, sources)[0]
    if not differences:
        return f"{slug} db = json · 0 differences", []
    return f"{slug} db ≠ json · {len(differences)} differences", differences[:5]


def _status(project, slug, record) -> str:
    directory = Path(record["slug_dir"])
    if store.backend(directory) != "sqlite":
        return f"{slug} json"
    conn = store.connect(directory / store.DB_NAME)
    try:
        stale = [key[3:] for key, value in conn.execute("SELECT key, value FROM meta WHERE key LIKE 'fp:%'")
                 if json.loads(value) != store._fingerprint(directory / key[3:])]
        last = store._meta_value(conn, "last_write") or store._meta_value(conn, "imported_at")
    finally:
        conn.close()
    from datetime import datetime
    age = int(time.time() - datetime.fromisoformat(last.replace("Z", "+00:00")).timestamp()) if last else 0
    export = "json export current" if not stale else f"json export stale ({', '.join(stale[:3])})"
    return f"{slug} sqlite · {export} · {age} s since last write"


def cmd_db(args) -> int:
    try:
        pages = _pages(args) if args.db_action != "status" or args.slug else _pages(type("A", (), {"all": True})())
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2
    failed = 0
    for project, slug, record in pages:
        directory = Path(record["slug_dir"])
        if args.db_action == "import":
            line = _import(project, slug, record, args)
            failed += " not imported" in line
        elif args.db_action == "diff":
            line, rows = _diff(project, slug, record)
            failed += bool(rows)
            line = "\n".join([line, *(f"  {row}" for row in rows)])
        elif args.db_action == "export":
            if store.backend(directory) != "sqlite":
                line = f"{slug} json · nothing to export"
            else:
                with store.transaction(directory) as tx:
                    names = store.export_page(directory)
                    caught = store.catch_up_bus(directory, tx.conn)
                line = f"{slug} exported {len(names)} files · bus caught up ({caught} events)"
        elif args.db_action == "status":
            line = _status(project, slug, record)
        else:
            if store.backend(directory) != "sqlite":
                line = f"{slug} json · nothing to turn off"
            else:
                kept = store.db_off(directory)
                line = f"{slug} back on json · {store.DB_NAME} kept as {kept.name}"
        print(line)
    return 1 if failed else 0


def add_parser(sub) -> None:
    sp = sub.add_parser("db", help="move a page's records into page.db and back (operator only)")
    actions = sp.add_subparsers(dest="db_action", required=True)
    for name, text in (("import", "build page.db from the page's files, diff it, then enable it"),
                       ("diff", "compare page.db with the page's files"),
                       ("export", "write the page's files from page.db"),
                       ("status", "one line per page: backend, export, last write"),
                       ("off", "back to JSON; page.db is kept aside")):
        action = actions.add_parser(name, help=text)
        action.add_argument("slug", nargs="?", metavar="SLUG")
        if name == "import":
            action.add_argument("--all", action="store_true", help="every registered page")
            action.add_argument("--dry-run", dest="trial", action="store_true", help="build and diff in a temporary file only")
        action.set_defaults(func=cmd_db)
