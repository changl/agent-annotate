#!/usr/bin/env python3
"""annotate — single CLI entry point for Agent Annotate.

Subcommands:
    annotate publish <slug-dir>                      start sync_server + register transport
    annotate unpublish <slug>                        tear down route + stop server
    annotate status [<slug>]                         list active slugs / health
    annotate migrate <legacy.html>                   one-shot v1→v2 migration
    annotate inbox <slug> [--unread]                 dump new comments
    annotate watch <slug>                            tail comments to stdout (sidecar)
    annotate monitor <slug> [--owner ID]             exclusive session monitor + live lease
    annotate publish-version <slug-dir> <vN>         add new version + swap symlink
    annotate archive-comment <slug> <comment-id>
    annotate addressed <slug> <comment-id> [--response "<text>"]

State uses platform-standard application directories. Set ANNOTATE_CONFIG_DIR,
ANNOTATE_DATA_DIR, and ANNOTATE_STATE_DIR to override them.
"""

import argparse
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .paths import (
    BUS_ROOT,
    CONFIG_DIR,
    DATA_DIR,
    HOOK_SCRIPT,
    LOG_DIR,
    MONITOR_OFFSET_ROOT,
    MONITOR_ROOT,
    PROJECTS_TOML,
    STATE_DIR,
    WEB_DIR,
    ensure_runtime_dirs,
)

MONITOR_EVENTS = {
    "comment_created",
    "comment_updated",
    "comment_reply",
    "comment_accepted",
    "comment_archived",
    "comment_reanchored",
    "comment_restored",
    "session_push",
}


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_state_for_project(project: str) -> dict:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    p = STATE_DIR / f"{project}.json"
    if not p.exists():
        return {"project": project, "slugs": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"project": project, "slugs": {}}


def _save_state_for_project(project: str, state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    p = STATE_DIR / f"{project}.json"
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def _all_state_files() -> list[Path]:
    if not STATE_DIR.exists():
        return []
    return sorted(STATE_DIR.glob("*.json"))


def _load_projects_toml() -> dict:
    """Return parsed projects.toml — or empty dict if missing.

    Uses tomllib (3.11+) or tomli fallback.
    """
    if not PROJECTS_TOML.exists():
        return {}
    try:
        import tomllib  # type: ignore[import]
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            print("WARN: no tomllib/tomli available — projects.toml ignored", file=sys.stderr)
            return {}
    return tomllib.loads(PROJECTS_TOML.read_text(encoding="utf-8"))


def _slug_project(slug_dir: Path, explicit_project: str | None = None) -> tuple[str, str]:
    """Return (project, slug). Project defaults to slug_dir.parent.name."""
    slug = slug_dir.name
    project = explicit_project or slug_dir.parent.name or "default"
    return project, slug


def _project_config(project: str) -> dict:
    cfg = _load_projects_toml().get(project, {})
    cfg.setdefault("transport", "local")
    cfg.setdefault("hostname", None)
    cfg.setdefault("port_base", 8800)
    cfg.setdefault("path_prefix", None)
    return cfg


def _find_free_port_after(start: int) -> int:
    import socket
    p = start
    while p < start + 50:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", p))
                return p
            except OSError:
                p += 1
    raise RuntimeError(f"No free port found in [{start}, {start+50})")


def _is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _resolve_author(cli_value: str | None) -> str:
    """Resolve author identity in priority order:
    1. CLI --author flag
    2. $ANNOTATE_AUTHOR env var
    3. $CLAUDE_AGENT_ID env var
    4. Default 'agent:opus-4-7'
    """
    if cli_value:
        return cli_value
    env_val = os.environ.get("ANNOTATE_AUTHOR")
    if env_val:
        return env_val
    env_val = os.environ.get("CLAUDE_AGENT_ID")
    if env_val:
        return env_val
    return "agent:opus-4-7"


# ────────────────────────────────────────────────────────────────────────────
# Provider integration
# ────────────────────────────────────────────────────────────────────────────
HOOK_COMMAND = str(HOOK_SCRIPT)


# ────────────────────────────────────────────────────────────────────────────
# Server lifecycle
# ────────────────────────────────────────────────────────────────────────────
def _start_server(slug_dir: Path, port: int, bus_dir: Path, public_base_path: str | None) -> int:
    """Spawn sync_server.py in v2 mode. Returns PID."""
    cmd = [
        sys.executable,
        "-m",
        "agent_annotate.sync_server",
        "--slug-dir", str(slug_dir),
        "--slug", slug_dir.name,
        "--bus-dir", str(bus_dir),
        "--port", str(port),
    ]
    if public_base_path:
        cmd += ["--public-base-path", public_base_path]
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{slug_dir.name}.log"
    fh = open(log_path, "ab", buffering=0)
    proc = subprocess.Popen(
        cmd,
        stdout=fh,
        stderr=fh,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    # Give it a moment to bind
    time.sleep(0.5)
    return proc.pid


def _stop_server(pid: int) -> bool:
    if not _is_process_alive(pid):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    for _ in range(20):
        time.sleep(0.1)
        if not _is_process_alive(pid):
            return True
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    return True


# ────────────────────────────────────────────────────────────────────────────
# Task 4 — Build-time JS lint
# ────────────────────────────────────────────────────────────────────────────
# Matches a full <script ...>...</script> block, capturing the opening tag and body.
# Group 1 = opening tag (e.g. `<script type="text/javascript">`),
# Group 2 = body content.
_SCRIPT_BLOCK_RE = re.compile(
    r'(<script(?:\s[^>]*)?/>|<script(?:\s[^>]*)?>)(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
# Matches src= in a script opening tag → external file, not inline JS.
_SCRIPT_SRC_RE = re.compile(r'\bsrc\s*=', re.IGNORECASE)
# Matches type= values that are NOT JavaScript (e.g. application/json, text/template).
# We skip any type that isn't absent, "text/javascript", or "module".
_SCRIPT_NON_JS_TYPE_RE = re.compile(
    r'\btype\s*=\s*["\'](?!(?:text/javascript|module)["\'])([^"\']*)["\']',
    re.IGNORECASE,
)


def _check_js_lint(html_path: Path, skip: bool = False) -> tuple[bool, list[str]]:
    """Extract inline JavaScript <script> blocks and run `node --check` on each.

    Skips:
      - <script src="..."> external references
      - <script type="application/json"> and other non-JS type values
      - <script /> self-closing tags (no body)

    Returns (all_ok, list_of_error_strings).
    If skip=True, returns (True, []) without running node at all.
    Exits with code 3 if `node` is not found on PATH (unless skip=True).
    """
    if skip:
        return True, []

    # Verify node is available
    node_bin = None
    for candidate in ["node", "nodejs"]:
        try:
            result = subprocess.run(
                [candidate, "--version"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                node_bin = candidate
                break
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    if node_bin is None:
        print(
            "ERROR: `node` not found on PATH — cannot run JS lint.\n"
            "  Install Node.js or pass --skip-js-lint to bypass (emergency only).",
            file=sys.stderr,
        )
        sys.exit(3)

    html = html_path.read_text(encoding="utf-8", errors="replace")
    errors = []
    block_num = 0

    for m in _SCRIPT_BLOCK_RE.finditer(html):
        open_tag = m.group(1)
        js_src = m.group(2)

        # Skip self-closing <script /> (no executable body)
        if open_tag.rstrip().endswith('/>'):
            continue

        # Skip external script refs (<script src="...">)
        if _SCRIPT_SRC_RE.search(open_tag):
            continue

        # Skip non-JS types (application/json, text/template, text/x-handlebars, etc.)
        if _SCRIPT_NON_JS_TYPE_RE.search(open_tag):
            continue

        # Skip empty bodies
        if not js_src.strip():
            continue

        block_num += 1
        html_line_start = html[:m.start()].count('\n') + 1

        with tempfile.NamedTemporaryFile(
            suffix=".js",
            prefix=f"annotate_lint_block{block_num}_",
            mode="w",
            encoding="utf-8",
            delete=False,
        ) as tf:
            tf.write(js_src)
            tf_path = tf.name

        try:
            result = subprocess.run(
                [node_bin, "--check", tf_path],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                err_raw = (result.stderr or result.stdout or "").strip()
                err_display = err_raw.replace(
                    tf_path,
                    f"{html_path} (inline script block #{block_num}, HTML line ~{html_line_start})",
                )
                errors.append(
                    f"  Block #{block_num} (HTML line ~{html_line_start}):\n"
                    + "\n".join("    " + ln for ln in err_display.splitlines())
                )
        except subprocess.TimeoutExpired:
            errors.append(f"  Block #{block_num}: node --check timed out")
        finally:
            try:
                os.unlink(tf_path)
            except OSError:
                pass

    return (len(errors) == 0), errors


# ────────────────────────────────────────────────────────────────────────────
# Commands
# ────────────────────────────────────────────────────────────────────────────
def cmd_publish(args) -> int:
    slug_dir = Path(args.slug_dir).resolve()
    if not slug_dir.exists() or not slug_dir.is_dir():
        print(f"ERROR: slug-dir not found or not a directory: {slug_dir}", file=sys.stderr)
        return 2
    project, slug = _slug_project(slug_dir, args.project)
    cfg = _project_config(project)

    # ── Task 4: Build-time JS lint ──────────────────────────────────
    skip_lint = getattr(args, "skip_js_lint", False)
    current_html = slug_dir / "current.html"
    if current_html.exists():
        # Resolve symlink so we lint the actual file content
        try:
            lint_target = current_html.resolve()
        except OSError:
            lint_target = current_html
        print(f"  JS lint:       checking {lint_target.name} …", end=" ", flush=True)
        lint_ok, lint_errors = _check_js_lint(lint_target, skip=skip_lint)
        if lint_ok:
            if skip_lint:
                print("SKIPPED (--skip-js-lint)")
            else:
                print("OK")
        else:
            print("FAILED")
            print(f"\nERROR: inline JS syntax errors in {lint_target}", file=sys.stderr)
            for e in lint_errors:
                print(e, file=sys.stderr)
            print(
                "\nFix the JS errors above and re-run `annotate publish`.\n"
                "  Use --skip-js-lint ONLY for emergency deploys (not recommended).",
                file=sys.stderr,
            )
            return 1
    else:
        print("  JS lint:       skipped (no current.html found yet)")

    state = _load_state_for_project(project)
    existing = state["slugs"].get(slug)
    if existing and _is_process_alive(existing.get("pid", 0)):
        print(f"  Slug {slug!r} already running:")
        print(f"    pid:  {existing['pid']}")
        print(f"    port: {existing['port']}")
        print(f"    url:  {existing.get('url')}")
        print(f"  (use `annotate unpublish {slug}` first to re-publish)")
        return 0

    # Pick port (use config base; auto-bump; allow override)
    if args.port:
        port = args.port
    else:
        port_base = existing.get("port") if existing else cfg.get("port_base", 8800)
        port = _find_free_port_after(int(port_base))

    bus_dir = BUS_ROOT / project
    bus_dir.mkdir(parents=True, exist_ok=True)

    # Transport: publish (insert public route)
    transport_name = args.transport or cfg.get("transport", "local")
    hostname = args.hostname or cfg.get("hostname")
    path_prefix = args.path_prefix or cfg.get("path_prefix") or f"/{slug}"
    if path_prefix and not path_prefix.startswith("/"):
        path_prefix = "/" + path_prefix
    path_prefix = path_prefix.rstrip("/")

    transport_url = None
    transport_details: dict = {}
    transport_error: str | None = None
    if transport_name != "local":
        try:
            from .transports import load as _load_transport
            tmod = _load_transport(transport_name)
            opts = {}
            if hostname:
                opts["hostname"] = hostname
            slug_for_route = path_prefix.lstrip("/")
            result = tmod.publish(slug_for_route, port, **opts)
            transport_url = result.get("url")
            transport_details = result.get("details", {})
        except NotImplementedError as e:
            transport_error = str(e)
            print(f"WARN: transport {transport_name!r}: {e}", file=sys.stderr)
        except Exception as e:
            transport_error = str(e)
            print(f"ERROR: transport {transport_name!r} publish failed: {e}", file=sys.stderr)

    # Start server (with public_base_path if transport set a sub-path mount)
    pbp = path_prefix if transport_name != "local" and transport_url else ""
    pid = _start_server(slug_dir, port, bus_dir, pbp)

    # Record state
    record = {
        "slug": slug,
        "slug_dir": str(slug_dir),
        "project": project,
        "pid": pid,
        "port": port,
        "transport": transport_name,
        "public_base_path": pbp or None,
        "url": transport_url or f"http://localhost:{port}/",
        "local_url": f"http://localhost:{port}/",
        "bus_file": str(bus_dir / f"{slug}.ndjson"),
        "started_at": _now_iso(),
        "transport_details": transport_details,
        "transport_error": transport_error,
    }
    state["slugs"][slug] = record
    _save_state_for_project(project, state)

    print()
    print(f"  annotate publish — {project}/{slug}")
    print("  ─────────────────────────────────────────────")
    print(f"  URL:           {record['url']}")
    print(f"  Local URL:     {record['local_url']}")
    print(f"  PID:           {pid}")
    print(f"  Port:          {port}")
    print(f"  Transport:     {transport_name}")
    if transport_error:
        print(f"  Transport err: {transport_error}")
    print(f"  Slug dir:      {slug_dir}")
    print(f"  NDJSON bus:    {record['bus_file']}")
    print(f"  State file:    {STATE_DIR / (project + '.json')}")
    print("  ─────────────────────────────────────────────")
    print("  Agent adapter: explicit; run `annotate sessions` or arm a provider monitor")
    print()
    return 0


def cmd_unpublish(args) -> int:
    slug = args.slug
    # Locate the state file that owns this slug
    record = None
    project = None
    for sf in _all_state_files():
        st = json.loads(sf.read_text(encoding="utf-8"))
        if slug in st.get("slugs", {}):
            record = st["slugs"][slug]
            project = st["project"]
            break
    if not record:
        print(f"ERROR: no state record for slug {slug!r}", file=sys.stderr)
        return 2

    # Stop server
    pid = record.get("pid", 0)
    stopped = _stop_server(pid)
    print(f"  Server pid={pid} {'stopped' if stopped else 'not running'}")

    # Transport teardown
    transport_name = record.get("transport", "local")
    pbp = (record.get("public_base_path") or "").lstrip("/")
    if transport_name != "local" and pbp:
        try:
            from .transports import load as _load_transport
            tmod = _load_transport(transport_name)
            opts = {}
            host = record.get("transport_details", {}).get("hostname")
            if host:
                opts["hostname"] = host
            r = tmod.unpublish(pbp, **opts)
            print(f"  Transport {transport_name}: {r.get('details', {}).get('action', 'ok')}")
        except NotImplementedError as e:
            print(f"WARN: transport {transport_name}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"WARN: transport {transport_name} unpublish failed: {e}", file=sys.stderr)

    # Remove from state
    state = _load_state_for_project(project)
    state["slugs"].pop(slug, None)
    _save_state_for_project(project, state)
    print(f"  Removed from state file: {STATE_DIR / (project + '.json')}")
    return 0


def cmd_status(args) -> int:
    rows = []
    for sf in _all_state_files():
        st = json.loads(sf.read_text(encoding="utf-8"))
        project = st.get("project")
        for slug, rec in st.get("slugs", {}).items():
            if args.slug and slug != args.slug:
                continue
            pid = rec.get("pid", 0)
            alive = _is_process_alive(pid)
            rows.append((project, slug, pid, rec.get("port"), rec.get("url"), "alive" if alive else "dead"))
    if not rows:
        print("(no active slugs)")
        return 0
    print(f"  {'PROJECT':<15} {'SLUG':<24} {'PID':<8} {'PORT':<6} {'STATE':<7} URL")
    print(f"  {'-'*15} {'-'*24} {'-'*8} {'-'*6} {'-'*7} {'-'*40}")
    for project, slug, pid, port, url, state in rows:
        print(f"  {project[:15]:<15} {slug[:24]:<24} {pid!s:<8} {port!s:<6} {state:<7} {url}")
    return 0


def cmd_migrate(args) -> int:
    """One-shot legacy-HTML → v2 directory layout.

    Steps:
      1. Resolve <legacy.html> path.
      2. Create <slug>/ in the same parent directory.
      3. Move HTML to versions/v1.html; symlink current.html → versions/v1.html.
      4. Write current.meta.json.
      5. Migrate any sibling *.comments.json into <slug>/comments.json (v2).
    """
    legacy_path = Path(args.legacy_html).resolve()
    if not legacy_path.exists() or not legacy_path.is_file():
        print(f"ERROR: legacy HTML not found: {legacy_path}", file=sys.stderr)
        return 2

    slug = args.slug or legacy_path.stem
    parent = legacy_path.parent
    slug_dir = parent / slug
    versions_dir = slug_dir / "versions"
    content_dir = slug_dir / "content"
    archive_dir = slug_dir / "archive"
    slug_dir.mkdir(exist_ok=True)
    versions_dir.mkdir(exist_ok=True)
    content_dir.mkdir(exist_ok=True)
    archive_dir.mkdir(exist_ok=True)

    initial_version = args.version or "v1"
    target_html = versions_dir / f"{initial_version}.html"

    if args.copy:
        target_html.write_bytes(legacy_path.read_bytes())
        action = "copied"
    else:
        os.replace(legacy_path, target_html)
        action = "moved"
    (content_dir / f"{initial_version}.html").write_bytes(target_html.read_bytes())

    current_symlink = slug_dir / "current.html"
    if current_symlink.exists() or current_symlink.is_symlink():
        current_symlink.unlink()
    current_symlink.symlink_to(Path("versions") / f"{initial_version}.html")

    meta = {
        "current": initial_version,
        "history": [
            {"version": initial_version, "ts": _now_iso(), "label": args.label or "initial"}
        ],
    }
    (slug_dir / "current.meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Migrate comments
    legacy_stem = legacy_path.stem
    legacy_comments_candidates = [
        parent / f"{legacy_stem}.comments.json",
        parent / "comments.json",
    ]
    src_comments = None
    for cand in legacy_comments_candidates:
        if cand.exists():
            src_comments = cand
            break

    if src_comments:
        try:
            raw = json.loads(src_comments.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"WARN: could not parse {src_comments}: {e}", file=sys.stderr)
            raw = []

        # Reuse the canonical v2 coercion logic.
        from .sync_server import _coerce_v2
        store = _coerce_v2(raw)
        # Stamp version on every comment
        for items in store["anchors"].values():
            for c in items:
                c.setdefault("version", initial_version)
        (slug_dir / "comments.json").write_text(
            json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        # Back up original comments
        if args.copy:
            backup = slug_dir / f"comments.{legacy_stem}.v1.bak.json"
            backup.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            os.replace(src_comments, slug_dir / f"comments.{legacy_stem}.v1.bak.json")
    else:
        (slug_dir / "comments.json").write_text(
            json.dumps({"schema_version": 2, "anchors": {}, "archived": {}}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    print(f"  Migrated {legacy_path} → {slug_dir}/")
    print(f"    HTML:          {action} → versions/{initial_version}.html")
    print(f"    review content: copied → content/{initial_version}.html")
    print(f"    current.html:  symlink → versions/{initial_version}.html")
    print("    meta:          current.meta.json")
    print(f"    comments:      comments.json (from {src_comments or 'fresh'})")
    print()
    print(f"  Next: annotate publish {slug_dir}")
    return 0


def cmd_publish_version(args) -> int:
    slug_dir = Path(args.slug_dir).resolve()
    if not slug_dir.exists() or not slug_dir.is_dir():
        print(f"ERROR: slug-dir not found: {slug_dir}", file=sys.stderr)
        return 2
    new_version = args.version
    versions_dir = slug_dir / "versions"
    target = versions_dir / f"{new_version}.html"
    if not target.exists():
        print(f"ERROR: versions/{new_version}.html not found — drop it in first", file=sys.stderr)
        return 2
    current_symlink = slug_dir / "current.html"
    if current_symlink.exists() or current_symlink.is_symlink():
        current_symlink.unlink()
    current_symlink.symlink_to(Path("versions") / f"{new_version}.html")

    meta_path = slug_dir / "current.meta.json"
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    meta.setdefault("history", [])
    meta["current"] = new_version
    meta["history"].append({
        "version": new_version,
        "ts": _now_iso(),
        "label": args.label or "",
    })
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Swapped current.html → versions/{new_version}.html")
    print(f"  meta:current = {new_version}")
    return 0


def cmd_inbox(args) -> int:
    slug = args.slug
    # Locate state record
    record = None
    project = None
    for sf in _all_state_files():
        st = json.loads(sf.read_text(encoding="utf-8"))
        if slug in st.get("slugs", {}):
            record = st["slugs"][slug]
            project = st["project"]
            break
    if not record:
        print(f"ERROR: no state record for slug {slug!r}", file=sys.stderr)
        return 2
    bus_file = Path(record["bus_file"])
    if not bus_file.exists():
        print("(no events)")
        return 0
    offset_file = STATE_DIR / "bus-offsets" / project / f"{slug}.offset"
    offset_file.parent.mkdir(parents=True, exist_ok=True)
    offset = 0
    if args.unread and offset_file.exists():
        try:
            offset = int(offset_file.read_text().strip())
        except Exception:
            offset = 0
    with bus_file.open("r", encoding="utf-8") as f:
        f.seek(offset)
        lines = f.readlines()
        new_offset = f.tell()
    if not lines:
        print("(no new events)")
        return 0
    for line in lines:
        line = line.rstrip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        print(f"  [{ev.get('ts')}] {ev.get('event'):<18} {ev.get('anchor_id') or ''} "
              f"by {ev.get('author', 'anonymous')}")
    if args.unread:
        offset_file.write_text(str(new_offset))
    return 0


def cmd_watch(args) -> int:
    slug = args.slug
    record = None
    for sf in _all_state_files():
        st = json.loads(sf.read_text(encoding="utf-8"))
        if slug in st.get("slugs", {}):
            record = st["slugs"][slug]
            break
    if not record:
        print(f"ERROR: no state record for slug {slug!r}", file=sys.stderr)
        return 2
    bus_file = Path(record["bus_file"])
    print(f"  Tailing {bus_file} (Ctrl-C to stop)")
    bus_file.parent.mkdir(parents=True, exist_ok=True)
    if not bus_file.exists():
        bus_file.touch()
    with bus_file.open("r", encoding="utf-8") as f:
        f.seek(0, os.SEEK_END)
        try:
            while True:
                line = f.readline()
                if not line:
                    time.sleep(0.5)
                    continue
                print(line.rstrip())
        except KeyboardInterrupt:
            print()
            return 0


def _live_monitor_leases(lease_dir: Path, expected_bus: Path) -> list[tuple[Path, dict]]:
    live = []
    expected = str(expected_bus.resolve())
    for path in lease_dir.glob("*.json"):
        try:
            lease = json.loads(path.read_text(encoding="utf-8"))
            pid = int(lease.get("pid", 0))
            if str(Path(lease.get("bus_file", "")).resolve()) != expected:
                raise ValueError("bus mismatch")
            if not _is_process_alive(pid):
                raise ValueError("dead process")
            live.append((path, lease))
        except Exception:
            path.unlink(missing_ok=True)
    return live


def _stop_monitor_leases(leases: list[tuple[Path, dict]]) -> bool:
    pids = {int(lease.get("pid", 0)) for _, lease in leases if int(lease.get("pid", 0)) > 0}
    for pid in pids:
        if pid == os.getpid():
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    deadline = time.time() + 3
    while time.time() < deadline and any(_is_process_alive(pid) for pid in pids if pid != os.getpid()):
        time.sleep(0.1)
    if any(_is_process_alive(pid) for pid in pids if pid != os.getpid()):
        return False
    for path, _ in leases:
        path.unlink(missing_ok=True)
    return True


def _monitor_owner_label(explicit: str | None) -> tuple[str, str]:
    owner = (
        explicit
        or os.environ.get("ANNOTATE_SESSION_ID")
        or os.environ.get("CLAUDE_SESSION_ID")
        or os.environ.get("CODEX_THREAD_ID")
        or f"interactive-ppid-{os.getppid()}"
    )
    if os.environ.get("CLAUDE_SESSION_ID") or os.environ.get("CLAUDE_AGENT_ID"):
        agent = "claude-code"
    elif os.environ.get("CODEX_THREAD_ID") or os.environ.get("CODEX_HOME"):
        agent = "codex"
    else:
        agent = "coding-agent"
    return owner, agent


def cmd_monitor(args) -> int:
    """Tail actionable events while advertising a live session monitor.

    This command is designed to run inside Claude Code's persistent Monitor
    tool. The lease lets the web UI distinguish an interactive handoff from a
    queued event; the shared byte offset lets a newly armed monitor replay any
    events that arrived while no session monitor was active.
    """
    slug = args.slug
    record = None
    project = None
    for sf in _all_state_files():
        st = json.loads(sf.read_text(encoding="utf-8"))
        if slug in st.get("slugs", {}):
            record = st["slugs"][slug]
            project = st["project"]
            break
    if not record or not project:
        print(f"ERROR: no state record for slug {slug!r}", file=sys.stderr)
        return 2

    bus_file = Path(record["bus_file"])
    bus_file.parent.mkdir(parents=True, exist_ok=True)
    if not bus_file.exists():
        bus_file.touch()

    lease_dir = MONITOR_ROOT / project / slug
    lease_dir.mkdir(parents=True, exist_ok=True)
    existing = _live_monitor_leases(lease_dir, bus_file)
    if existing:
        current_owner = existing[0][1].get("owner_session") or f"pid {existing[0][1].get('pid')}"
        if not args.takeover:
            print(
                f"ERROR: monitor for {project}/{slug} is already owned by {current_owner}.\n"
                f"  Use --takeover only during an explicit session handoff.",
                file=sys.stderr,
            )
            return 3
        if not _stop_monitor_leases(existing):
            print(f"ERROR: could not stop the current monitor for {project}/{slug}", file=sys.stderr)
            return 3

    lease_path = lease_dir / "owner.json"
    owner_session, owner_agent = _monitor_owner_label(args.owner)
    provider_name = getattr(args, "provider", "stdout")
    provider_session = getattr(args, "session_id", None) or owner_session
    lease = {
        "schema_version": 2,
        "pid": os.getpid(),
        "project": project,
        "slug": slug,
        "bus_file": str(bus_file),
        "owner_session": owner_session,
        "owner_agent": owner_agent,
        "provider": provider_name,
        "provider_session": provider_session,
        "host": socket.gethostname(),
        "started_at": _now_iso(),
        "events": sorted(MONITOR_EVENTS),
    }
    try:
        fd = os.open(lease_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # Another session won the claim race after the live-lease check.
        print(f"ERROR: monitor ownership changed while claiming {project}/{slug}; retry the handoff", file=sys.stderr)
        return 3
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(lease, fh, indent=2)

    print("ANNOTATE_MONITOR_ARMED " + json.dumps({
        "project": project,
        "slug": slug,
        "owner_session": owner_session,
        "owner_agent": owner_agent,
        "provider": provider_name,
        "pid": os.getpid(),
    }, ensure_ascii=False, separators=(",", ":")), flush=True)

    offset_file = MONITOR_OFFSET_ROOT / project / f"{slug}.offset"
    offset_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        offset = int(offset_file.read_text(encoding="utf-8").strip()) if offset_file.exists() else bus_file.stat().st_size
    except Exception:
        offset = bus_file.stat().st_size

    try:
        with bus_file.open("r", encoding="utf-8") as f:
            f.seek(min(offset, bus_file.stat().st_size))
            while True:
                line_start = f.tell()
                line = f.readline()
                if not line:
                    time.sleep(0.25)
                    continue
                next_offset = f.tell()
                try:
                    ev = json.loads(line)
                except Exception:
                    offset_file.write_text(str(next_offset), encoding="utf-8")
                    continue
                if ev.get("event") not in MONITOR_EVENTS:
                    offset_file.write_text(str(next_offset), encoding="utf-8")
                    continue
                print("ANNOTATE_EVENT " + json.dumps(ev, ensure_ascii=False, separators=(",", ":")), flush=True)
                if provider_name == "codex-app-server" and ev.get("event") == "session_push":
                    try:
                        from .providers.codex_app_server import CodexAppServerAdapter

                        comment_ids = ev.get("comment_ids") or ev.get("comments") or []
                        count = ev.get("count") or len(comment_ids)
                        page_url = record.get("url") or record.get("local_url")
                        message = (
                            f"[Agent Annotate] The user pushed {count} feedback item(s) from "
                            f"{project}/{slug} to this session. Page: {page_url}. "
                            f"Comment IDs: {comment_ids}. Run `annotate inbox {slug} --unread`, "
                            "review the exact comments and anchors, then reply through the annotation API."
                        )
                        result = CodexAppServerAdapter().deliver(provider_session, message)
                        print("ANNOTATE_DELIVERED " + json.dumps(result.__dict__, separators=(",", ":")), flush=True)
                    except Exception as exc:
                        print(f"ANNOTATE_DELIVERY_ERROR {exc}", file=sys.stderr, flush=True)
                        f.seek(line_start)
                        time.sleep(2)
                        continue
                offset_file.write_text(str(next_offset), encoding="utf-8")
    except KeyboardInterrupt:
        return 0
    finally:
        try:
            current = json.loads(lease_path.read_text(encoding="utf-8"))
            if int(current.get("pid", 0)) == os.getpid():
                lease_path.unlink(missing_ok=True)
        except Exception:
            pass


def cmd_archive_comment(args) -> int:
    author = _resolve_author(getattr(args, "author", None))
    return _http_post_local(args.slug, f"/api/comments/{args.comment_id}/archive", {}, author)


def cmd_addressed(args) -> int:
    body = {"status": "addressed_by_agent"}
    if args.response:
        body["response_text"] = args.response
    author = _resolve_author(getattr(args, "author", None))
    return _http_put_local(args.slug, f"/api/comments/{args.comment_id}", body, author)


def _http_post_local(slug: str, path: str, body: dict, author: str) -> int:
    rec = _find_record(slug)
    if not rec:
        print(f"ERROR: no state record for slug {slug!r}", file=sys.stderr)
        return 2
    base = rec["local_url"].rstrip("/")
    pbp = rec.get("public_base_path") or ""
    url = f"{base}{pbp}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, method="POST", data=data, headers={
        "Content-Type": "application/json",
        "Cf-Access-Authenticated-User-Email": author,
    })
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(resp.read().decode())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    return 0


def _http_put_local(slug: str, path: str, body: dict, author: str) -> int:
    rec = _find_record(slug)
    if not rec:
        print(f"ERROR: no state record for slug {slug!r}", file=sys.stderr)
        return 2
    base = rec["local_url"].rstrip("/")
    pbp = rec.get("public_base_path") or ""
    url = f"{base}{pbp}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, method="PUT", data=data, headers={
        "Content-Type": "application/json",
        "Cf-Access-Authenticated-User-Email": author,
    })
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(resp.read().decode())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    return 0


def _find_record(slug: str) -> dict | None:
    for sf in _all_state_files():
        st = json.loads(sf.read_text(encoding="utf-8"))
        if slug in st.get("slugs", {}):
            return st["slugs"][slug]
    return None


def cmd_doctor(args) -> int:
    """Validate the portable installation without changing provider config."""

    ensure_runtime_dirs()
    checks = [
        ("version", True, __version__),
        ("config_dir", CONFIG_DIR.is_dir(), str(CONFIG_DIR)),
        ("data_dir", DATA_DIR.is_dir(), str(DATA_DIR)),
        ("state_dir", STATE_DIR.is_dir(), str(STATE_DIR)),
        ("web_assets", all((WEB_DIR / name).is_file() for name in ("shell.html", "shell.js", "shell.css", "adapter.js")), str(WEB_DIR)),
        ("node", shutil.which("node") is not None, shutil.which("node") or "not found; inline JS lint unavailable"),
        ("codex", shutil.which("codex") is not None, shutil.which("codex") or "not found; Codex adapter unavailable"),
    ]
    failed = False
    for name, ok, detail in checks:
        failed = failed or not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name:<12} {detail}")
    return 1 if failed else 0


def cmd_sessions(args) -> int:
    """List Codex sessions that can be assigned to an annotation page."""

    from .providers.codex_app_server import CodexAppServerAdapter

    try:
        sessions = CodexAppServerAdapter().list_sessions(cwd=args.cwd)
    except Exception as exc:
        print(f"ERROR: could not list Codex sessions: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(sessions, indent=2, ensure_ascii=False))
        return 0
    if not sessions:
        print("(no matching Codex sessions)")
        return 0
    current = os.environ.get("CODEX_THREAD_ID")
    print(f"  {'CURRENT':<7} {'THREAD':<38} {'STATUS':<10} {'CWD':<36} PREVIEW")
    for session in sessions:
        status = session.get("status", {}).get("type", "unknown")
        preview = " ".join(session.get("preview", "").split())[:72]
        cwd = session.get("cwd", "")
        marker = "yes" if session.get("id") == current else ""
        print(f"  {marker:<7} {session.get('id', ''):<38} {status:<10} {cwd[-36:]:<36} {preview}")
    return 0


def cmd_send(args) -> int:
    """Deliver a coordination message to one existing Codex thread."""

    from .providers.codex_app_server import CodexAppServerAdapter

    try:
        result = CodexAppServerAdapter().deliver(args.thread, args.message)
    except Exception as exc:
        print(f"ERROR: Codex delivery failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.__dict__, indent=2))
    return 0


def cmd_connect(args) -> int:
    """Run the Codex page monitor as a detached delivery worker."""

    if not _find_record(args.slug):
        print(f"ERROR: no state record for slug {args.slug!r}", file=sys.stderr)
        return 2
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{args.slug}-codex-monitor.log"
    cmd = [
        sys.executable,
        "-m",
        "agent_annotate.cli",
        "monitor",
        args.slug,
        "--owner",
        args.thread,
        "--provider",
        "codex-app-server",
        "--session-id",
        args.thread,
    ]
    if args.takeover:
        cmd.append("--takeover")
    with log_path.open("ab", buffering=0) as log:
        proc = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    deadline = time.time() + 4
    while time.time() < deadline:
        if proc.poll() is not None:
            print(f"ERROR: monitor stopped; inspect {log_path}", file=sys.stderr)
            return 2
        rec = _find_record(args.slug)
        if rec:
            project = rec["project"]
            lease = MONITOR_ROOT / project / args.slug / "owner.json"
            if lease.exists():
                print(f"Connected {project}/{args.slug} to Codex thread {args.thread}")
                print(f"Monitor PID: {proc.pid}")
                print(f"Log: {log_path}")
                return 0
        time.sleep(0.1)
    proc.terminate()
    print(f"ERROR: monitor did not acquire its lease; inspect {log_path}", file=sys.stderr)
    return 2


def cmd_disconnect(args) -> int:
    rec = _find_record(args.slug)
    if not rec:
        print(f"ERROR: no state record for slug {args.slug!r}", file=sys.stderr)
        return 2
    lease_dir = MONITOR_ROOT / rec["project"] / args.slug
    leases = _live_monitor_leases(lease_dir, Path(rec["bus_file"]))
    if not leases:
        print(f"No live monitor owns {rec['project']}/{args.slug}")
        return 0
    if not _stop_monitor_leases(leases):
        print(f"ERROR: could not stop monitor for {rec['project']}/{args.slug}", file=sys.stderr)
        return 2
    print(f"Disconnected monitor for {rec['project']}/{args.slug}; server remains running")
    return 0


def cmd_hook_check(args) -> int:
    """Provider hook fallback: report bus activity since the previous call."""

    offset_root = STATE_DIR / "hook-offsets"
    summaries = []
    for bus_file in sorted(BUS_ROOT.glob("*/*.ndjson")):
        project = bus_file.parent.name
        slug = bus_file.stem
        offset_file = offset_root / project / f"{slug}.offset"
        offset_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            previous = int(offset_file.read_text(encoding="utf-8")) if offset_file.exists() else 0
        except ValueError:
            previous = 0
        size = bus_file.stat().st_size
        if size > previous:
            with bus_file.open("r", encoding="utf-8") as handle:
                handle.seek(previous)
                count = sum(1 for line in handle if line.strip())
            if count:
                summaries.append(f"{project}/{slug}: {count} new event(s)")
            offset_file.write_text(str(size), encoding="utf-8")
    if summaries:
        print("[annotate] " + "; ".join(summaries))
        print("Run `annotate inbox <slug> --unread` to inspect them.")
    return 0


def cmd_mcp(args) -> int:
    from .mcp_server import main as mcp_main

    mcp_main()
    return 0


# ────────────────────────────────────────────────────────────────────────────
# Argparse
# ────────────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(prog="annotate", description="annotate v2 CLI")
    p.add_argument("--version", action="version", version=f"agent-annotate {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_doc = sub.add_parser("doctor", help="validate installation and local integrations")
    sp_doc.set_defaults(func=cmd_doctor)

    sp_sessions = sub.add_parser("sessions", help="list Codex sessions available for page ownership")
    sp_sessions.add_argument("--cwd", default=None, help="only list sessions with this exact working directory")
    sp_sessions.add_argument("--json", action="store_true")
    sp_sessions.set_defaults(func=cmd_sessions)

    sp_send = sub.add_parser("send", help="send one coordination message to a Codex thread")
    sp_send.add_argument("--thread", required=True)
    sp_send.add_argument("message")
    sp_send.set_defaults(func=cmd_send)

    sp_connect = sub.add_parser("connect", help="connect one page to a Codex thread in the background")
    sp_connect.add_argument("slug")
    sp_connect.add_argument("--thread", required=True)
    sp_connect.add_argument("--takeover", action="store_true")
    sp_connect.set_defaults(func=cmd_connect)

    sp_disconnect = sub.add_parser("disconnect", help="release a page monitor without stopping its server")
    sp_disconnect.add_argument("slug")
    sp_disconnect.set_defaults(func=cmd_disconnect)

    sp_hook = sub.add_parser("hook-check", help=argparse.SUPPRESS)
    sp_hook.set_defaults(func=cmd_hook_check)

    sp_mcp = sub.add_parser("mcp", help="run the Agent Annotate MCP server over stdio")
    sp_mcp.set_defaults(func=cmd_mcp)

    sp_pub = sub.add_parser("publish", help="start server + register transport route")
    sp_pub.add_argument("slug_dir")
    sp_pub.add_argument("--project", default=None)
    sp_pub.add_argument("--port", type=int, default=None)
    sp_pub.add_argument("--transport", default=None, choices=["local", "cloudflare", "tailscale"])
    sp_pub.add_argument("--hostname", default=None)
    sp_pub.add_argument("--path-prefix", default=None)
    sp_pub.add_argument(
        "--skip-js-lint",
        dest="skip_js_lint",
        action="store_true",
        default=False,
        help="EMERGENCY ONLY: skip inline JS syntax check (not recommended)",
    )
    sp_pub.set_defaults(func=cmd_publish)

    sp_unpub = sub.add_parser("unpublish", help="tear down route + stop server")
    sp_unpub.add_argument("slug")
    sp_unpub.set_defaults(func=cmd_unpublish)

    sp_st = sub.add_parser("status", help="list active slugs")
    sp_st.add_argument("slug", nargs="?", default=None)
    sp_st.set_defaults(func=cmd_status)

    sp_mig = sub.add_parser("migrate", help="legacy HTML → v2 layout")
    sp_mig.add_argument("legacy_html")
    sp_mig.add_argument("--slug", default=None)
    sp_mig.add_argument("--version", default="v1")
    sp_mig.add_argument("--label", default=None)
    sp_mig.add_argument("--copy", action="store_true", help="copy instead of move")
    sp_mig.set_defaults(func=cmd_migrate)

    sp_pv = sub.add_parser("publish-version", help="add new version + swap symlink")
    sp_pv.add_argument("slug_dir")
    sp_pv.add_argument("version")
    sp_pv.add_argument("--label", default=None)
    sp_pv.set_defaults(func=cmd_publish_version)

    sp_in = sub.add_parser("inbox", help="dump new comments since last call")
    sp_in.add_argument("slug")
    sp_in.add_argument("--unread", action="store_true")
    sp_in.set_defaults(func=cmd_inbox)

    sp_w = sub.add_parser("watch", help="tail comments to stdout")
    sp_w.add_argument("slug")
    sp_w.set_defaults(func=cmd_watch)

    sp_mon = sub.add_parser("monitor", help="tail actionable events and advertise an active session monitor")
    sp_mon.add_argument("slug")
    sp_mon.add_argument("--owner", default=None,
                        help="interactive session/thread label stored in the ownership lease")
    sp_mon.add_argument("--takeover", action="store_true",
                        help="explicit handoff: stop the existing monitor for this slug and claim ownership")
    sp_mon.add_argument("--provider", choices=["stdout", "codex-app-server"], default="stdout",
                        help="delivery backend; stdout is for an attached agent monitor")
    sp_mon.add_argument("--session-id", default=None,
                        help="provider session/thread id used by an automatic delivery backend")
    sp_mon.set_defaults(func=cmd_monitor)

    sp_arc = sub.add_parser("archive-comment", help="archive a comment")
    sp_arc.add_argument("slug")
    sp_arc.add_argument("comment_id")
    sp_arc.add_argument("--author", default=None,
                        help="author identity (overrides $ANNOTATE_AUTHOR, $CLAUDE_AGENT_ID; default agent:opus-4-7)")
    sp_arc.set_defaults(func=cmd_archive_comment)

    sp_addr = sub.add_parser("addressed", help="mark comment as addressed_by_agent")
    sp_addr.add_argument("slug")
    sp_addr.add_argument("comment_id")
    sp_addr.add_argument("--response", default=None)
    sp_addr.add_argument("--author", default=None,
                         help="author identity (overrides $ANNOTATE_AUTHOR, $CLAUDE_AGENT_ID; default agent:opus-4-7)")
    sp_addr.set_defaults(func=cmd_addressed)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
