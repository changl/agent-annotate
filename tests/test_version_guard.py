"""ENF-08: the launcher, skills, Codex plugin and live pages must match the
installed release, and `doctor --versions` fails loudly when one does not.

The installed release here is this test interpreter (the sandbox launcher
execs it); older runtimes are fakes on disk or a fake page server.
"""

import fcntl
import http.server
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_annotate import __version__, cli, paths, skillgen, version_guard
from agent_annotate.updates import build_identity, runtime_manifest

ROOT = Path(__file__).resolve().parents[1]
UNREGISTERED_SERVERS = version_guard._unregistered_servers


@pytest.fixture
def estate(monkeypatch, tmp_path):
    monkeypatch.delenv("ANNOTATE_VERSION_GUARD", raising=False)
    # Inside the suite sandbox: conftest checks the patched roots never leave it.
    tmp_path = Path(os.environ["ANNOTATE_STATE_DIR"]).parent / "version-guard" / tmp_path.name
    tmp_path.mkdir(parents=True)
    tmp_path = tmp_path.resolve()
    shim = tmp_path / "bin" / "annotate"
    shim.parent.mkdir()
    shim.write_text(f'#!/bin/sh\n# agent-annotate shim\nexec "{sys.executable}" -m agent_annotate.cli "$@"\n')
    shim.chmod(0o755)
    claude, codex = tmp_path / "home" / ".claude" / "skills" / "annotate", tmp_path / "home" / ".agents" / "skills" / "annotate"
    for name, value in {"SHIM_PATH": shim, "CONFIG_DIR": tmp_path / "config", "STATE_DIR": tmp_path / "state",
                        "HOOK_OFFSET_ROOT": tmp_path / "state" / "hook-offsets", "LOCK_DIR": tmp_path / "state" / "locks",
                        "SKILL_DIRS": (claude, codex),
                        "CODEX_PLUGIN_CACHE": tmp_path / "codex" / "plugins" / "cache"}.items():
        monkeypatch.setattr(paths, name, value)
    monkeypatch.setattr(skillgen, "CONFIG_DIR", tmp_path / "config")
    # The machine's own page servers are not this test's estate.
    monkeypatch.setattr(version_guard, "_unregistered_servers", lambda registered: [])
    monkeypatch.setenv("PATH", f"{shim.parent}{os.pathsep}{os.environ['PATH']}")
    return SimpleNamespace(root=tmp_path, shim=shim, claude=claude, codex=codex,
                           env={"ANNOTATE_SHIM_PATH": str(shim), "ANNOTATE_CONFIG_DIR": str(tmp_path / "config"),
                                "ANNOTATE_STATE_DIR": str(tmp_path / "state"), "ANNOTATE_BUS_ROOT": str(tmp_path / "bus"),
                                "ANNOTATE_SKILL_DIRS": os.pathsep.join(map(str, (claude, codex))),
                                "ANNOTATE_CODEX_PLUGIN_CACHE": str(tmp_path / "codex" / "plugins" / "cache"),
                                "PATH": f"{shim.parent}{os.pathsep}{os.environ['PATH']}"})


def _install_everything(estate):
    skillgen.install_skill("claude", estate.claude)
    skillgen.install_skill("codex", estate.codex)
    tree = paths.CODEX_PLUGIN_CACHE / "local" / "agent-annotate" / __version__
    shutil.copytree(ROOT / "plugins" / "codex" / "agent-annotate", tree)
    return tree


class _Capabilities(http.server.BaseHTTPRequestHandler):
    body = b"{}"

    def do_GET(self):
        self.send_response(200 if self.body and self.path.endswith("/api/capabilities") else 404)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.body or b'{"error":"not found"}')

    def log_message(self, *args):
        pass


@pytest.fixture
def page_server():
    servers = []

    def start(runtime):
        handler = type("Handler", (_Capabilities,), {"body": json.dumps(
            {"version": runtime["package_version"], "runtime": runtime}).encode() if runtime else None})
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return server.server_address[1]

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


def _register(slug, port, manifest=None):
    state = paths.STATE_DIR / "proj.json"
    data = json.loads(state.read_text()) if state.exists() else {"project": "proj", "slugs": {}}
    data["slugs"][slug] = {"slug": slug, "port": port, "pid": os.getpid(), "local_url": f"http://127.0.0.1:{port}/",
                           **({"runtime_manifest": manifest} if manifest else {})}
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps(data))


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _doctor(capsys, **flags):
    code = cli.cmd_doctor(SimpleNamespace(versions=True, json=False, **flags))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_install_stamp_records_the_build_id(estate):
    skillgen.install_skill("claude", estate.claude)
    stamp = json.loads((estate.claude / ".annotate-install.json").read_text())
    assert stamp["version"] == __version__ and stamp["build_id"] == build_identity()[0]


def test_everything_matching_the_installed_release_exits_zero(estate, page_server, capsys):
    _install_everything(estate)
    _register("live", page_server(runtime_manifest()))
    _register("stopped", _free_port())
    code, out, err = _doctor(capsys)
    assert code == 0, out + err
    assert err == ""
    rows = {line.split()[1] for line in out.splitlines() if line.startswith("OK ")}
    assert rows == {"release", "launcher", "skill", "plugin", "page"}
    assert "SKIP      page      proj/stopped  not running" in out
    assert "MISMATCH" not in out
    assert out.splitlines()[-1].startswith("annotate versions OK: 5 component(s) match installed release")


def test_a_stale_skill_fails_loudly_and_names_it(estate, capsys):
    _install_everything(estate)
    stamp = estate.claude / ".annotate-install.json"
    stale = json.loads(stamp.read_text())
    stale["version"] = "2.21.0"
    del stale["build_id"]
    stamp.write_text(json.dumps(stale))
    code, out, err = _doctor(capsys)
    assert code == 1
    assert f"MISMATCH  skill     {estate.claude}" in out
    assert "fix: annotate sync-skills" in out
    assert err.splitlines()[0] == (f"ERROR: ANNOTATE VERSION MISMATCH: 1 of 4 component(s) differ from installed "
                                   f"release {version_guard._label(__version__, build_identity()[0])}: "
                                   f"skill {estate.claude}")
    assert "  fix: annotate sync-skills" in err.splitlines()


def test_an_unregistered_hand_copied_skill_gets_the_install_command(estate, capsys):
    estate.codex.mkdir(parents=True)
    (estate.codex / "SKILL.md").write_text("old copy")
    code, out, _err = _doctor(capsys)
    assert code == 1
    assert "no install stamp" in out
    assert f"fix: annotate install-skill --provider codex --dest {estate.codex}" in out


def test_a_live_page_on_an_older_runtime_is_reported(estate, page_server, capsys):
    _install_everything(estate)
    _register("old", page_server({"package_version": "2.21.0", "build_id": "assets:" + "a" * 64, "assets": {}}))
    code, out, err = _doctor(capsys)
    assert code == 1
    line = next(line for line in out.splitlines() if "proj/old" in line)
    assert line.startswith("MISMATCH  page      proj/old  2.21.0 (assets:aaaaaaaaaaaa) != release")
    assert 'restart_record("proj", "old")' in line and sys.executable in line
    assert "page proj/old" in err


def test_an_unregistered_legacy_server_is_found_and_reported(estate, page_server, monkeypatch, capsys):
    _install_everything(estate)
    port = page_server(None)  # a pre-capabilities server: /api/capabilities is 404
    bus = paths.BUS_ROOT / "prem-fin"
    page = estate.root / "prem-fin"
    page.mkdir()
    _register("registered", 1)  # pid os.getpid(), port 1
    legacy = (f"  4242 /usr/bin/python3 /home/x/.claude/skills/annotate/sync_server.py --slug-dir {page} "
              f"--slug prem-fin --bus-dir {bus} --port {port} --public-base-path /prem-fin\n"
              # another estate's sandbox server (its own bus root) is not reported
              f"  4343 /venv/bin/python -m agent_annotate.sync_server --slug-dir {estate.root} --slug p "
              f"--bus-dir /tmp/x/bus/p --port {port} --strict-port\n"
              # a registered server whose spaced path `ps` cannot quote: its pid is a record's, never a kill target
              f"  {os.getpid()} /venv/bin/python -m agent_annotate.sync_server --slug-dir {estate.root} --slug q "
              f"--bus-dir {bus} --port {port} --strict-port\n"
              # a directory that does not exist (a mis-split path) is skipped
              f"  4545 /venv/bin/python -m agent_annotate.sync_server --slug-dir /no/such/half --slug r "
              f"--bus-dir {bus} --port {port} --strict-port\n")
    original = subprocess.run
    monkeypatch.setattr(subprocess, "run", lambda command, *args, **kwargs: SimpleNamespace(stdout=legacy)
                        if command[:1] == ["ps"] else original(command, *args, **kwargs))
    monkeypatch.setattr(version_guard, "_unregistered_servers", UNREGISTERED_SERVERS)
    code, out, _err = _doctor(capsys)
    assert code == 1
    line = next(line for line in out.splitlines() if "prem-fin" in line)
    assert line.startswith(f"MISMATCH  page      {page} (unregistered, pid 4242)  runtime unknown "
                           "(/api/capabilities HTTP 404; legacy server)")
    assert (f"fix: kill 4242 && nohup {sys.executable} -I -m agent_annotate.sync_server --slug-dir {page} "
            f"--slug prem-fin --bus-dir {bus} --port {port} --public-base-path /prem-fin >> ") in line
    assert "4343" not in out and f"pid {os.getpid()}" not in out and "4545" not in out


def test_json_output_lists_components_and_fixes(estate, page_server, capsys):
    _install_everything(estate)
    _register("old", page_server({"package_version": "2.21.0", "build_id": "b" * 40}))
    code = cli.cmd_doctor(SimpleNamespace(versions=True, json=True))
    result = json.loads(capsys.readouterr().out)
    assert code == 1 and result["ok"] is False
    assert result["release"]["version"] == __version__
    page = next(row for row in result["components"] if row["kind"] == "page")
    assert page["status"] == "MISMATCH" and page["version"] == "2.21.0"
    assert result["fixes"] == [page["fix"]]


def test_an_older_annotate_first_on_path_is_reported(estate, monkeypatch, capsys):
    old = estate.root / "old" / "venv"
    package = old / "lib" / "python3.12" / "site-packages" / "agent_annotate"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('__version__ = "2.21.0"\n')
    (package / "_build.json").write_text(json.dumps({"build_id": "c" * 40}))
    (old / "bin").mkdir()
    (old / "bin" / "python").write_text("")
    other = estate.root / "other-bin"
    other.mkdir()
    (other / "annotate").write_text(f"#!/bin/sh\n# agent-annotate shim\nexec {old / 'bin' / 'python'} -I -m agent_annotate.cli \"$@\"\n")
    (other / "annotate").chmod(0o755)
    monkeypatch.setenv("PATH", f"{other}{os.pathsep}{os.environ['PATH']}")
    code, out, _err = _doctor(capsys)
    assert code == 1
    assert f"MISMATCH  launcher  {other / 'annotate'}  2.21.0 (cccccccccccc) != release" in out
    assert f'fix: export PATH="{estate.shim.parent}:$PATH"' in out


def test_no_installed_launcher_fails(estate, capsys):
    estate.shim.unlink()
    code, out, err = _doctor(capsys)
    assert code == 1
    assert "no installed release" in out
    assert "install-shim" in err


def test_a_codex_plugin_from_another_release_is_reported(estate, capsys):
    tree = _install_everything(estate)
    manifest = tree / ".codex-plugin" / "plugin.json"
    manifest.write_text(json.dumps({**json.loads(manifest.read_text()), "version": "2.21.0"}))
    code, out, _err = _doctor(capsys)
    assert code == 1
    assert "plugin 2.21.0 != release" in out
    assert "fix: codex plugin marketplace upgrade local && codex plugin add agent-annotate@local" in out


def test_the_prompt_hook_prints_one_line_once_per_session(estate):
    _install_everything(estate)
    stamp = estate.claude / ".annotate-install.json"
    stamp.write_text(json.dumps({**json.loads(stamp.read_text()), "build_id": "other-build"}))
    (estate.root / "bus").mkdir()
    env = {**os.environ, **estate.env}
    env.pop("ANNOTATE_VERSION_GUARD", None)

    def run(session):
        proc = subprocess.run([sys.executable, "-m", "agent_annotate.cli", "hook-check"],
                              input=json.dumps({"session_id": session}), capture_output=True,
                              text=True, env=env, timeout=30)
        assert proc.returncode == 0, proc.stderr
        return proc.stdout

    first = run("sess-a").splitlines()
    assert len(first) == 1
    assert first[0].startswith("[annotate] ANNOTATE VERSION MISMATCH: 1 of 4 component(s)")
    assert first[0].endswith("Details and fix commands: annotate doctor --versions")
    assert run("sess-a") == ""
    assert run("sess-b").splitlines() == first


def test_the_session_notice_reads_page_runtimes_from_the_registry_only(estate, monkeypatch):
    _install_everything(estate)
    _register("old", 1, {"package_version": "2.21.0", "build_id": "d" * 40})
    monkeypatch.setattr(cli, "_api", lambda *args, **kwargs: pytest.fail("the hot path must not call a server"))
    line = version_guard.session_notice("sess")
    assert "page proj/old" in line
    assert version_guard.session_notice("sess") is None


def test_a_starting_page_server_logs_and_serves_the_mismatch(estate, capsys):
    _install_everything(estate)
    stamp = estate.codex / ".annotate-install.json"
    stamp.write_text(json.dumps({**json.loads(stamp.read_text()), "version": "2.21.0"}))
    status = version_guard.server_status("proj", "page", log=True)
    assert status == {"ok": False, "checked": True,
                      "release": {"version": __version__, "build_id": build_identity()[0]},
                      "mismatched": ["skill:codex"]}
    warning = capsys.readouterr().err
    assert warning.startswith("WARNING: ANNOTATE VERSION MISMATCH: 1 of 5 component(s)")
    assert "annotate sync-skills" in warning
    assert str(estate.root) not in json.dumps(status)  # served publicly: no local paths

    # The real server: it starts anyway, logs the line and serves the result.
    slug_dir = estate.root / "pages" / "page"
    slug_dir.mkdir(parents=True)
    (slug_dir / "current.html").write_text("<!doctype html><html><body><p>x</p></body></html>")
    (estate.root / "bus" / "proj").mkdir(parents=True)
    env = {**os.environ, **estate.env}
    env.pop("ANNOTATE_VERSION_GUARD", None)
    port = _free_port()
    log_path = estate.root / "server.log"
    with log_path.open("wb") as log:
        proc = subprocess.Popen([sys.executable, "-m", "agent_annotate.sync_server", "--slug-dir", str(slug_dir),
                                 "--bus-dir", str(estate.root / "bus" / "proj"), "--port", str(port),
                                 "--strict-port"], stdout=log, stderr=subprocess.STDOUT, env=env)
    try:
        caps = None
        deadline = time.monotonic() + 15
        while caps is None and time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/capabilities", timeout=2) as response:
                    caps = json.loads(response.read())
            except OSError:
                time.sleep(0.1)
        assert caps is not None, log_path.read_text()
        assert caps["version_guard"] == status
        while "WARNING: ANNOTATE VERSION MISMATCH" not in log_path.read_text() and time.monotonic() < deadline:
            time.sleep(0.1)  # logged by the start thread
        assert "WARNING: ANNOTATE VERSION MISMATCH: 1 of 5 component(s)" in log_path.read_text()
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_an_update_in_progress_defers_the_warning_and_the_served_status(estate, monkeypatch, capsys):
    """`update --apply` restarts pages before it repoints the launcher; a page
    restarted on the new runtime must not report itself against the old one."""
    _install_everything(estate)
    old = estate.root / "old" / "venv"
    package = old / "lib" / "python3.12" / "site-packages" / "agent_annotate"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text('__version__ = "2.21.0"\n')
    (package / "_build.json").write_text(json.dumps({"build_id": "e" * 40}))
    (old / "bin").mkdir()
    (old / "bin" / "python").write_text("")
    current = estate.shim.read_text()
    estate.shim.write_text(f"#!/bin/sh\n# agent-annotate shim\nexec {old / 'bin' / 'python'} -I -m agent_annotate.cli \"$@\"\n")
    monkeypatch.setattr(version_guard, "CACHE_SECONDS", 0)
    lock = paths.LOCK_DIR / "runtime-update.lock"
    lock.parent.mkdir(parents=True)
    with lock.open("a") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX)
        assert version_guard.cached_server_status("proj", "page")["pending"] == "runtime update in progress"
        thread = threading.Thread(target=version_guard.warn_at_start, args=("proj", "page"), daemon=True)
        thread.start()
        thread.join(0.5)
        assert thread.is_alive() and capsys.readouterr().err == ""
        estate.shim.write_text(current)  # the update repoints the launcher, then releases the lock
    thread.join(5)
    assert not thread.is_alive()
    assert capsys.readouterr().err == ""  # this server matches the launcher it now finds
    assert version_guard.cached_server_status("proj", "page")["ok"] is True


def test_a_locally_edited_registered_skill_gets_the_overwriting_command(estate, capsys):
    _install_everything(estate)
    stamp = estate.claude / ".annotate-install.json"
    stamp.write_text(json.dumps({**json.loads(stamp.read_text()), "version": "2.21.0"}))
    (estate.claude / "SKILL.md").write_text("edited by hand")
    code, out, _err = _doctor(capsys)
    assert code == 1
    assert (f"fix: annotate install-skill --provider claude --dest {estate.claude}  "
            "# overwrites local edits to SKILL.md") in out


def test_the_passive_notices_are_off_in_the_suite(estate, monkeypatch):
    monkeypatch.setenv("ANNOTATE_VERSION_GUARD", "0")
    estate.shim.unlink()
    assert version_guard.session_notice("sess") is None
    assert version_guard.server_status("proj", "page") == {"ok": None, "checked": False}
