"""Fail loudly when an installed piece of annotate differs from the installed release.

The installed release is the runtime the launcher at SHIM_PATH
(~/.local/bin/annotate) executes. Each component is compared with it by
version and build id:

    launcher  the `annotate` found on PATH
    skill     each registered or default skill directory (.annotate-install.json)
    plugin    each installed Codex plugin tree of agent-annotate
    page      each registered page server (the runtime in /api/capabilities)

The check is read-only: it never installs, syncs, restarts or deletes, and
every mismatch carries the exact command that fixes it. `local_only` reads
page runtimes from the registry instead of asking the servers, so the prompt
hook, `workspace` and a starting page server stay off the network.
ANNOTATE_VERSION_GUARD=0 silences those passive notices (the test suite sets
it); `doctor --versions` always runs.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__, paths
from .updates import build_identity, runtime_manifest

OK, MISMATCH, SKIP = "OK", "MISMATCH", "SKIP"
PLUGIN_NAME = "agent-annotate"
PAGE_TIMEOUT = 2.0
_VERSION_RE = re.compile(r"^__version__\s*=\s*[\"']([^\"']+)[\"']", re.MULTILINE)


def passive_enabled() -> bool:
    return os.environ.get("ANNOTATE_VERSION_GUARD") != "0"


def _short(build_id: str | None) -> str:
    if not build_id:
        return "no build id"
    prefix, _, digest = build_id.rpartition(":")
    return (prefix + ":" if prefix else "") + digest[:12]


def _label(version: str | None, build_id: str | None) -> str:
    return f"{version or 'unknown'} ({_short(build_id)})"


def _package_dir(python: Path) -> Path | None:
    """The agent_annotate package `python` imports: the venv layout on disk,
    else asked of the interpreter (editable and custom installs)."""
    if not python.is_file():
        return None
    for init in sorted(python.parent.parent.glob("lib/python3*/site-packages/agent_annotate/__init__.py")):
        return init.parent
    try:
        result = subprocess.run(
            [str(python), "-I", "-c", "import agent_annotate, os; print(os.path.dirname(agent_annotate.__file__))"],
            capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    found = Path(result.stdout.strip()) if result.returncode == 0 and result.stdout.strip() else None
    return found if found is not None and (found / "__init__.py").is_file() else None


def runtime_identity(python: Path) -> dict:
    """{python, package_dir, version, build_id} of the agent_annotate a Python runs."""
    python = Path(python)
    if os.path.abspath(python.parent.parent) == os.path.abspath(sys.prefix):
        manifest = runtime_manifest()
        return {"python": str(python), "package_dir": str(paths.PACKAGE_DIR),
                "version": manifest["package_version"], "build_id": manifest["build_id"]}
    package = _package_dir(python)
    if package is None:
        return {"python": str(python), "package_dir": None, "version": None, "build_id": None}
    try:
        match = _VERSION_RE.search((package / "__init__.py").read_text(encoding="utf-8"))
        build_id = build_identity(package)[0]
    except (OSError, ValueError):
        match, build_id = None, None
    return {"python": str(python), "package_dir": str(package),
            "version": match.group(1) if match else None, "build_id": build_id}


def launcher_python(path: Path) -> Path | None:
    """The interpreter an agent-annotate launcher executes: the shim's
    `exec PYTHON -m agent_annotate.cli`, or a console script's shebang."""
    try:
        body = Path(path).read_text(encoding="utf-8", errors="replace")[:8192]
    except OSError:
        return None
    if "agent_annotate" not in body and "agent-annotate shim" not in body:
        return None
    lines = body.splitlines()
    try:
        if lines and lines[0].startswith("#!") and "python" in lines[0]:
            argv = shlex.split(lines[0][2:])
            return Path(argv[0]) if argv and os.path.isabs(argv[0]) else None
        for line in lines:
            line = line.strip()
            if line.startswith("'''exec' "):  # uv/pip's long-shebang trampoline
                line = "exec " + line[len("'''exec' "):]
            if line.startswith("exec "):
                argv = shlex.split(line[len("exec "):])
                if (argv and os.path.isabs(argv[0])
                        and ("agent_annotate.cli" in argv or argv[1:2] == ["$0"])):
                    return Path(argv[0])
                return None
    except ValueError:
        return None
    return None


def installed_release() -> dict:
    python = launcher_python(paths.SHIM_PATH)
    if python is None:
        return {"python": None, "package_dir": None, "version": None, "build_id": None,
                "source": str(paths.SHIM_PATH)}
    return {**runtime_identity(python), "source": str(paths.SHIM_PATH)}


def _row(kind, name, status, version=None, build_id=None, detail="", fix=None, label=None) -> dict:
    return {"kind": kind, "name": name, "status": status, "version": version, "build_id": build_id,
            "detail": detail, "fix": fix, "label": label or kind}


def _compare(kind, name, version, build_id, release, fix, label=None) -> dict:
    if version is None:
        return _row(kind, name, MISMATCH, detail="runtime unknown", fix=fix, label=label)
    if not build_id:
        return _row(kind, name, MISMATCH, version, None,
                    f"{_label(version, None)}; cannot prove it is release {_label(release['version'], release['build_id'])}",
                    fix, label)
    if (version, build_id) != (release["version"], release["build_id"]):
        return _row(kind, name, MISMATCH, version, build_id,
                    f"{_label(version, build_id)} != release {_label(release['version'], release['build_id'])}",
                    fix, label)
    return _row(kind, name, OK, version, build_id, _label(version, build_id), label=label)


def _launcher_row(release: dict) -> dict:
    shim = paths.SHIM_PATH
    first = f'export PATH="{shim.parent}:$PATH"'
    found = shutil.which("annotate")
    if not found:
        return _row("launcher", "annotate", MISMATCH, detail="`annotate` is not on PATH", fix=first)
    try:
        if os.path.samefile(found, shim):
            return _row("launcher", found, OK, release["version"], release["build_id"],
                        _label(release["version"], release["build_id"]))
    except OSError:
        pass
    python = launcher_python(Path(found))
    if python is None:
        return _row("launcher", found, MISMATCH, detail=f"{found} is not the installed agent-annotate launcher",
                    fix=first)
    identity = runtime_identity(python)
    return _compare("launcher", found, identity["version"], identity["build_id"], release, first)


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _skill_rows(release: dict, inv: str) -> list[dict]:
    registered = _read_json(paths.CONFIG_DIR / "skill-installs.json")
    registered = registered if isinstance(registered, dict) else {}
    dirs: dict[str, tuple[Path, bool]] = {}
    for path in registered:
        dirs.setdefault(os.path.realpath(path), (Path(path), True))
    for path in paths.SKILL_DIRS:
        if (path / "SKILL.md").is_file() or (path / ".annotate-install.json").is_file():
            dirs.setdefault(os.path.realpath(path), (path, False))
    rows = []
    for real, (path, is_registered) in sorted(dirs.items()):
        if not path.is_dir():
            rows.append(_row("skill", str(path), SKIP, detail="registered skill directory is gone"))
            continue
        manifest = _read_json(path / ".annotate-install.json")
        manifest = manifest if isinstance(manifest, dict) else None
        provider = ((manifest or {}).get("provider") or registered.get(str(path)) or registered.get(real)
                    or ("codex" if ".agents" in path.parts else "claude"))
        fix = (f"{inv} sync-skills" if is_registered
               else f"{inv} install-skill --provider {provider} --dest {shlex.quote(str(path))}")
        label = f"skill:{provider}"
        if manifest is None:
            rows.append(_row("skill", str(path), MISMATCH, detail="no install stamp (.annotate-install.json)",
                             fix=fix, label=label))
            continue
        rows.append(_compare("skill", str(path), manifest.get("version"), manifest.get("build_id"),
                             release, fix, label))
    return rows


def _plugin_rows(release: dict) -> list[dict]:
    newest: dict[str, Path] = {}
    for manifest in paths.CODEX_PLUGIN_CACHE.glob(f"*/{PLUGIN_NAME}/*/.codex-plugin/plugin.json"):
        tree = manifest.parents[1]
        marketplace = manifest.parents[3].name
        try:
            if marketplace not in newest or tree.stat().st_mtime > newest[marketplace].stat().st_mtime:
                newest[marketplace] = tree
        except OSError:
            continue
    expected = (Path(release["package_dir"]) / "skills" / "codex" / "SKILL.md"
                if release.get("package_dir") else None)
    rows = []
    for marketplace, tree in sorted(newest.items()):
        fix = (f"codex plugin marketplace upgrade {marketplace} && "
               f"codex plugin add {PLUGIN_NAME}@{marketplace}")
        plugin = _read_json(tree / ".codex-plugin" / "plugin.json")
        version = plugin.get("version") if isinstance(plugin, dict) else None
        if version != release["version"]:
            rows.append(_row("plugin", str(tree), MISMATCH, version,
                             detail=f"plugin {version or 'unknown'} != release {release['version']}",
                             fix=fix, label="codex plugin"))
            continue
        try:
            same = expected is None or (tree / "skills" / "annotate" / "SKILL.md").read_bytes() == expected.read_bytes()
        except OSError:
            same = False
        rows.append(_row("plugin", str(tree), OK if same else MISMATCH, version,
                         detail=version if same else f"{version}, but its SKILL.md differs from the release's",
                         fix=None if same else fix, label="codex plugin"))
    return rows


def _registry() -> list[tuple[str, str, dict]]:
    out = []
    for state_file in sorted(paths.STATE_DIR.glob("*.json")) if paths.STATE_DIR.is_dir() else []:
        state = _read_json(state_file)
        if not isinstance(state, dict) or not isinstance(state.get("slugs"), dict):
            continue
        project = state.get("project") or state_file.stem
        out.extend((project, slug, record) for slug, record in sorted(state["slugs"].items())
                   if isinstance(record, dict))
    return out


def _alive(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _restart_fix(release: dict, project: str, slug: str) -> str:
    code = ("from agent_annotate.deployment import restart_record; "
            f"print(restart_record({json.dumps(project)}, {json.dumps(slug)}))")
    return f"{shlex.quote(release['python'])} -I -c {shlex.quote(code)}"


def _unregistered_servers(registered: set[str]) -> list[dict]:
    """Running page servers on this estate's bus that no registry record
    knows, e.g. a legacy skill-directory sync_server.py. Servers of another
    estate (a sandbox or preview with its own bus root) are not ours. Read
    from `ps`; full check only."""
    try:
        out = subprocess.run(["ps", "-ww", "-eo", "pid=,args="], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    bus_root = os.path.realpath(paths.BUS_ROOT) + os.sep
    servers = []
    for line in out.splitlines():
        if "sync_server" not in line or "--slug-dir" not in line:
            continue
        pid, _, rest = line.strip().partition(" ")
        try:
            argv = shlex.split(rest)
            start = next(i for i, arg in enumerate(argv)
                         if arg == "agent_annotate.sync_server" or Path(arg).name == "sync_server.py") + 1
            tail = argv[start:]
            flags = {arg: tail[i + 1] for i, arg in enumerate(tail[:-1])
                     if arg.startswith("--") and not tail[i + 1].startswith("--")}
            directory, port = os.path.realpath(flags["--slug-dir"]), int(flags["--port"])
            ours = (os.path.realpath(flags["--bus-dir"]) + os.sep).startswith(bus_root)
        except (ValueError, StopIteration, KeyError):
            continue
        if ours and directory not in registered and 0 < port < 65536:
            servers.append({"pid": int(pid), "port": port, "slug_dir": directory, "tail": tail,
                            "slug": flags.get("--slug") or Path(directory).name,
                            "public_base_path": flags.get("--public-base-path") or None})
    return servers


def _page_rows(release: dict, local_only: bool) -> list[dict]:
    rows = []
    entries = _registry()
    if not local_only:
        for server in _unregistered_servers({os.path.realpath(record.get("slug_dir") or "")
                                             for _p, _s, record in entries}):
            log = paths.LOG_DIR / f"{server['slug']}.log"
            fix = (f"kill {server['pid']} && nohup {shlex.quote(release['python'])} -I -m agent_annotate.sync_server "
                   f"{shlex.join(server['tail'])} >> {shlex.quote(str(log))} 2>&1 &")
            record = {"local_url": f"http://127.0.0.1:{server['port']}/", "port": server["port"],
                      "public_base_path": server["public_base_path"]}
            entries.append((None, f"{server['slug_dir']} (unregistered, pid {server['pid']})", record, fix))
    for entry in entries:
        project, slug, record = entry[:3]
        name = f"{project}/{slug}" if project else slug
        fix = entry[3] if len(entry) > 3 else _restart_fix(release, project, slug)
        if local_only:
            manifest = record.get("runtime_manifest")
            if not _alive(record.get("pid")) or not isinstance(manifest, dict):
                continue  # Only the full check asks a server for its runtime.
            rows.append(_compare("page", name, manifest.get("package_version"), manifest.get("build_id"),
                                 release, fix))
            continue
        from .cli import _api
        code, body = _api(record, "GET", "/api/capabilities", None, "version-guard", timeout=PAGE_TIMEOUT)
        if code == 0:
            rows.append(_row("page", name, SKIP, detail="not running"))
            continue
        runtime = body.get("runtime") if code == 200 and isinstance(body, dict) else None
        if not isinstance(runtime, dict):
            rows.append(_row("page", name, MISMATCH,
                             body.get("version") if code == 200 and isinstance(body, dict) else None,
                             detail=f"runtime unknown (/api/capabilities HTTP {code}; legacy server)", fix=fix))
            continue
        rows.append(_compare("page", name, runtime.get("package_version"), runtime.get("build_id"), release, fix))
    return rows


def check(*, local_only: bool = False, pages: bool = True, server: tuple[str, str] | None = None) -> dict:
    """Compare every installed piece with the installed release.

    `server` adds a row for the calling page server (project, slug)."""
    release = installed_release()
    rows: list[dict] = []
    inv = "annotate"
    if release["version"] is None:
        rows.append(_row("release", release["source"], MISMATCH,
                         detail="no installed release: the launcher is missing or runs an unknown runtime",
                         fix=f"{shlex.quote(sys.executable)} -m agent_annotate.cli install-shim"))
    else:
        rows.append(_row("release", release["source"], OK, release["version"], release["build_id"],
                         f"{_label(release['version'], release['build_id'])} via {release['python']}"))
        rows.append(_launcher_row(release))
        if rows[-1]["status"] != OK:
            inv = f"{shlex.quote(release['python'])} -I -m agent_annotate.cli"
        rows += _skill_rows(release, inv)
        rows += _plugin_rows(release)
        if pages:
            rows += _page_rows(release, local_only)
        if server is not None:
            rows.append(_compare("page", f"{server[0]}/{server[1]} (this server)", __version__,
                                 runtime_manifest()["build_id"], release,
                                 _restart_fix(release, *server), label="this server"))
    bad = [row for row in rows if row["status"] == MISMATCH]
    compared = [row for row in rows if row["kind"] != "release" and row["status"] != SKIP]
    if release["version"] is None:
        summary = f"ANNOTATE VERSION CHECK FAILED: no installed release at {release['source']}"
    elif bad:
        names = ", ".join(f"{row['kind']} {row['name']}" for row in bad[:4])
        more = f", +{len(bad) - 4} more" if len(bad) > 4 else ""
        summary = (f"ANNOTATE VERSION MISMATCH: {len(bad)} of {len(compared)} component(s) differ from "
                   f"installed release {_label(release['version'], release['build_id'])}: {names}{more}")
    else:
        summary = (f"annotate versions OK: {len(compared)} component(s) match installed release "
                   f"{_label(release['version'], release['build_id'])}")
    return {
        "ok": not bad,
        "release": {key: release.get(key) for key in ("version", "build_id", "python", "source")},
        "components": rows,
        "fixes": list(dict.fromkeys(row["fix"] for row in bad if row["fix"])),
        "summary": summary,
        "invocation": inv,
    }


def format_lines(result: dict) -> list[str]:
    lines = []
    for row in result["components"]:
        line = f"{row['status']:<9} {row['kind']:<9} {row['name']}  {row['detail']}"
        if row["status"] == MISMATCH and row["fix"]:
            line += f"  fix: {row['fix']}"
        lines.append(line)
    return lines


def _safe_component(value: str) -> str:
    out = "".join(ch if (ch.isalnum() or ch in "._-") else "-" for ch in (value or ""))
    return out.strip("-") or "unknown"


def session_notice(session_id: str, *, dry_run: bool = False) -> str | None:
    """One line for a session whose installed pieces differ, at most once per
    session. Local files only; silent without an installed release. Never raises."""
    if not passive_enabled():
        return None
    marker = paths.HOOK_OFFSET_ROOT / _safe_component(session_id) / "version-guard"
    if marker.exists():
        return None
    try:
        result = check(local_only=True)
    except Exception:
        return None
    line = None
    if result["release"]["version"] and not result["ok"]:
        line = (f"[annotate] {result['summary']}. Details and fix commands: {result['invocation']} doctor --versions")
    if not dry_run:
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text((line or "ok") + "\n", encoding="utf-8")
        except OSError:
            pass
    return line


def server_status(project: str, slug: str) -> dict:
    """Checked once when a page server starts: logged loudly on a mismatch and
    served in /api/capabilities without local paths. Never raises."""
    if not passive_enabled():
        return {"ok": None, "checked": False}
    try:
        result = check(local_only=True, pages=False, server=(project, slug))
    except Exception as exc:  # A page must start even if the check breaks.
        return {"ok": None, "checked": False, "error": type(exc).__name__}
    if result["release"]["version"] is None:
        return {"ok": None, "checked": True, "release": None, "mismatched": []}
    if not result["ok"]:
        print(f"WARNING: {result['summary']}. Fix: {' ; '.join(result['fixes'])}", file=sys.stderr, flush=True)
    return {
        "ok": result["ok"],
        "checked": True,
        "release": {"version": result["release"]["version"], "build_id": result["release"]["build_id"]},
        "mismatched": sorted({row["label"] for row in result["components"] if row["status"] == MISMATCH}),
    }
