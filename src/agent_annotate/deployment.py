"""Activate staged runtimes without reclaiming pages or changing routes."""

from __future__ import annotations

import copy
import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from . import cli, verify
from .updates import version_tuple


class DeploymentError(RuntimeError):
    def __init__(self, message: str, **result):
        super().__init__(message)
        self.result = {"ok": False, "error": message, **result}


def _environment() -> dict:
    return {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}}


def _target_manifest(python: Path) -> dict:
    if not python.is_absolute() or not python.is_file() or not os.access(python, os.X_OK):
        raise DeploymentError("runtime Python must be an absolute executable file")
    result = subprocess.run([str(python), "-I", "-m", "agent_annotate.cli", "--version"],
                            check=True, capture_output=True, text=True, timeout=30, env=_environment())
    prefix = "agent-annotate "
    if not result.stdout.strip().startswith(prefix):
        raise DeploymentError("staged interpreter did not identify Agent Annotate")
    version = result.stdout.strip()[len(prefix):]
    version_tuple(version)
    code = "import json; from agent_annotate.updates import runtime_manifest; print(json.dumps(runtime_manifest()))"
    manifest = json.loads(subprocess.run([str(python), "-I", "-c", code], check=True,
                         capture_output=True, text=True, timeout=30, env=_environment()).stdout)
    if (not isinstance(manifest, dict) or manifest.get("package_version") != version
            or not manifest.get("build_id") or not isinstance(manifest.get("assets"), dict)):
        raise DeploymentError("staged runtime manifest does not match its version")
    return manifest


def _arguments(record: dict, python: Path) -> list[str]:
    slug_dir = Path(record["slug_dir"]).resolve()
    bus_dir = Path(record.get("bus_file") or cli.BUS_ROOT / record["project"] / f"{slug_dir.name}.ndjson").parent
    argv = [str(python), "-I", "-m", "agent_annotate.sync_server", "--slug-dir", str(slug_dir),
            "--slug", slug_dir.name, "--bus-dir", str(bus_dir), "--port", str(record["port"]), "--strict-port"]
    if record.get("public_base_path"):
        argv += ["--public-base-path", record["public_base_path"]]
    return argv


def _identity(record: dict, *, listening: bool = True) -> dict:
    directory = Path(record.get("slug_dir") or "").resolve()
    port = int(record.get("port") or 0)
    if not record.get("slug_dir") or not (directory / "current.html").is_file() or not 0 < port < 65536:
        raise DeploymentError("page registry lacks a valid directory, current document or port")
    processes = cli._running_servers().get(str(directory), [])
    listener = cli._port_listen_pid(port)  # Fail closed when listener identity cannot be read.
    if len(processes) > 1:
        raise DeploymentError(f"ambiguous servers for {directory}")
    if not processes:
        if listener is not None or (record.get("pid") and cli._is_process_alive(record["pid"])):
            raise DeploymentError(f"foreign or unreconciled process for port {port}")
        python = Path(record.get("runtime_python") or sys.executable)
        return {"pid": None, "python": str(python), "argv": _arguments(record, python)}
    process = processes[0]
    pid = process["pid"]
    if process.get("port") != port or (listener != pid if listening else listener not in (None, pid)):
        raise DeploymentError(f"foreign or unreconciled listener for port {port}")
    result = subprocess.run(["ps", "-ww", "-p", str(pid), "-o", "args="],
                            check=True, capture_output=True, text=True, timeout=5)
    argv = shlex.split(result.stdout.strip())
    def arg(flag):
        return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else None
    module = "-m" in argv and arg("-m") == "agent_annotate.sync_server"
    script = len(argv) > 1 and Path(argv[1]).is_absolute() and Path(argv[1]).name == "sync_server.py"
    python = Path(argv[0]) if argv else Path("")
    expected_bus = Path(record.get("bus_file") or cli.BUS_ROOT / record["project"] / f"{directory.name}.ndjson").parent
    if (not (module or script) or not python.is_absolute() or not python.is_file()
            or not os.access(python, os.X_OK) or not arg("--slug-dir")
            or Path(arg("--slug-dir")).resolve() != directory or arg("--port") != str(port)
            or arg("--slug") != directory.name
            or not arg("--bus-dir") or Path(arg("--bus-dir")).resolve() != expected_bus.resolve()
            or (arg("--public-base-path") or "") != (record.get("public_base_path") or "")):
        raise DeploymentError(f"server command identity does not match registry for {directory}")
    return {"pid": pid, "python": str(python), "argv": argv}


def _stop(record: dict, identity: dict, *, listening: bool = True) -> None:
    fresh = _identity(record, listening=listening)
    if fresh != identity:
        raise DeploymentError("server identity changed before stop; no signal sent")
    if identity["pid"] is not None:
        cli._stop_server(identity["pid"])


def _spawn(record: dict, argv: list[str]) -> int:
    if cli._port_listen_pid(int(record["port"])) is not None:
        raise DeploymentError("page port remains occupied; no replacement started")
    cli.LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (cli.LOG_DIR / f"{Path(record['slug_dir']).name}.log").open("ab", buffering=0) as log:
        return subprocess.Popen(argv, stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                                start_new_session=True, env=_environment()).pid


def _verify_server(record: dict, pid: int, expected: dict | None) -> dict:
    if not cli._wait_listening(int(record["port"]), pid) or _identity(record)["pid"] != pid:
        raise DeploymentError("replacement failed exact process/listener verification")
    origin = f"http://127.0.0.1:{record['port']}{record.get('public_base_path') or ''}/"
    if expected is not None:
        with urllib.request.urlopen(origin + "api/capabilities", timeout=5) as response:
            capabilities = json.loads(response.read(1024 * 1024 + 1))
        runtime = capabilities.get("runtime")
        if (capabilities.get("version") != expected["package_version"] or not isinstance(runtime, dict)
                or any(runtime.get(key) != expected[key] for key in ("package_version", "build_id", "assets"))):
            raise DeploymentError("replacement capability version/build/assets do not match staged runtime")
    rendered = verify.probe_http("origin", origin, timeout=8)
    if not rendered.ok or not rendered.anchors:
        raise DeploymentError("replacement content has no verified commentable anchors")
    return {"anchors": rendered.anchors, "runtime": expected, "browser_verified": False}


def _restart(project: str, slug: str, python: Path, expected: dict | None,
             *, argv: list[str] | None = None, provenance: dict | None = None) -> dict:
    with cli._flock(cli._state_lock_path(project)):
        state = cli._load_state_for_project(project)
        record = (state.get("slugs") or {}).get(slug)
        if not isinstance(record, dict):
            raise DeploymentError(f"page is no longer registered: {project}/{slug}")
        record["project"] = project
        original = copy.deepcopy(record)
        before = _identity(record)
        _stop(record, before)  # Immediate second fresh process/listener proof.
        started = None
        try:
            command = argv or _arguments(record, python)
            if argv is None:
                for flag in ("--local-author", "--local-author-name"):
                    if flag in before["argv"]:
                        index = before["argv"].index(flag)
                        command += [flag, before["argv"][index + 1]]
            started = _spawn(record, command)
            proof = _verify_server(record, started, expected)
            record.update({"pid": started, "runtime_python": str(python), "runtime_manifest": expected})
            if provenance is not None:
                for key in ("runtime_python", "runtime_manifest"):
                    if key in provenance:
                        record[key] = provenance[key]
                    else:
                        record.pop(key, None)
            cli._save_state_for_project(project, state)
            return {"ok": True, "project": project, "slug": slug, "pid": started,
                    "previous_python": before["python"], "verification": proof}
        except Exception as exc:
            rollback_error = None
            try:
                if started is not None:
                    candidate = _identity(record, listening=False)
                    if candidate["pid"] not in (None, started):
                        raise DeploymentError("replacement identity changed; foreign process left alone")
                    _stop(record, candidate, listening=False)
                if before["pid"] is not None:
                    restored = _spawn(original, before["argv"])
                    _verify_server(original, restored, None)
                    original["pid"] = restored
                    state["slugs"][slug] = original
                    cli._save_state_for_project(project, state)
            except Exception as rollback:
                rollback_error = str(rollback)
            raise DeploymentError(f"restart failed for {project}/{slug}: {exc}; "
                                  + (f"rollback failed: {rollback_error}" if rollback_error else "rollback completed"),
                                  project=project, slug=slug, rolled_back=rollback_error is None) from exc


def restart_record(project: str, slug: str, python: Path | None = None) -> dict:
    python = Path(python) if python is not None else Path(sys.executable)
    return _restart(project, slug, python, _target_manifest(python))


def _restore_stopped(project: str, slug: str, original: dict) -> None:
    with cli._flock(cli._state_lock_path(project)):
        state = cli._load_state_for_project(project)
        record = state["slugs"][slug]
        _stop(record, _identity(record))
        for key in ("pid", "runtime_python", "runtime_manifest"):
            if key in original:
                record[key] = original[key]
            else:
                record.pop(key, None)
        cli._save_state_for_project(project, state)


def _shim_snapshot() -> dict:
    path = cli.SHIM_PATH
    if not path.exists() and not path.is_symlink():
        return {"exists": False}
    body = path.read_bytes()
    if not cli._is_ours(body.decode("utf-8", errors="replace")):
        raise DeploymentError("annotate launcher belongs to another tool; left alone")
    return {"exists": True, "link": os.readlink(path) if path.is_symlink() else None,
            "body": body, "mode": stat.S_IMODE(path.stat().st_mode)}


def _replace_shim(body: bytes | None = None, *, link: str | None = None, mode: int = 0o755) -> None:
    path = cli.SHIM_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".annotate-update-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            if body is not None:
                handle.write(body)
        if link is not None:
            os.unlink(temp)
            os.symlink(link, temp)
        else:
            os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def activate_runtime(python: Path) -> dict:
    python = Path(python)
    expected = _target_manifest(python)
    with cli._flock(cli.LOCK_DIR / "runtime-update.lock"):
        snapshot = _shim_snapshot()
        entries = cli._registry_entries()
        journal, seen = [], set()
        for project, slug, record in entries:
            record = {**record, "project": project}
            key = (str(Path(record.get("slug_dir") or "").resolve()), int(record.get("port") or 0))
            if any(key[0] == old[0] or key[1] == old[1] for old in seen):
                raise DeploymentError("registry has duplicate directory or port ownership")
            seen.add(key)
            journal.append((project, slug, record, _identity(record)))
        changed, results = [], []
        try:
            for project, slug, record, before in journal:
                results.append(_restart(project, slug, python, expected))
                changed.append((project, slug, record, before))
            # Recheck launcher ownership/content immediately before replacement.
            if _shim_snapshot() != snapshot:
                raise DeploymentError("launcher changed during activation; left alone")
            body = (f"#!/bin/sh\n# {cli.SHIM_MARKER}\n"
                    f'exec {shlex.quote(str(python))} -I -m agent_annotate.cli "$@"\n').encode()
            _replace_shim(body)
            cli._INV_CACHE = None
            return {"ok": True, "python": str(python), "runtime": expected, "pages": results}
        except Exception as exc:
            failures = []
            if isinstance(exc, DeploymentError) and exc.result.get("rolled_back") is False:
                failures.append(str(exc))
            for project, slug, record, before in reversed(changed):
                try:
                    if before["pid"] is None:
                        _restore_stopped(project, slug, record)
                    else:
                        _restart(project, slug, Path(before["python"]), None,
                                 argv=before["argv"], provenance=record)
                except Exception as rollback:
                    failures.append(f"{project}/{slug}: {rollback}")
            # A failed atomic replace leaves original launcher intact. Restore
            # only our successful replacement; never overwrite a peer's edit.
            try:
                if cli.SHIM_PATH.exists() and cli.SHIM_PATH.read_bytes() == locals().get("body"):
                    if snapshot["exists"]:
                        _replace_shim(snapshot["body"], link=snapshot["link"], mode=snapshot["mode"])
                    else:
                        cli.SHIM_PATH.unlink()
            except Exception as rollback:
                failures.append(f"launcher: {rollback}")
            raise DeploymentError(f"activation failed: {exc}; "
                                  + ("rollback incomplete: " + "; ".join(failures) if failures else "rollback completed"),
                                  rolled_back=not failures, rollback_errors=failures) from exc
