"""Stage 4 rollout.py: every apply step fails once and rolls back; the remote gate sends nothing."""

import hashlib
import importlib.util
import json
import os
import signal
import stat
import subprocess
import sys
import threading
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "rollout.py"


@pytest.fixture
def rollout(tmp_path, monkeypatch):
    monkeypatch.setenv("ANNOTATE_ROLLOUT_HOME", str(tmp_path / "rollout"))
    monkeypatch.setenv("ANNOTATE_ROLLOUT_MAC", "M1")
    monkeypatch.delenv("UV_TOOL_DIR", raising=False)
    spec = importlib.util.spec_from_file_location("rollout", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeMac:
    """One Mac: installed version, two skill dirs, three running pages on sandbox ports."""

    def __init__(self, tmp_path, rollout, fail=None):
        self.rollout, self.fail, self.version, self.calls = rollout, fail, "2.28.2", []
        self.skills = [tmp_path / "skills/claude", tmp_path / "skills/codex"]
        for path in self.skills:
            path.mkdir(parents=True)
            (path / "SKILL.md").write_text("old skill")
        self.pages = {f"p{i}": "2.28.2" for i in range(3)}
        self.ports = {f"p{i}": 18710 + i for i in range(3)}
        self.backends, self.holds = {}, set()
        wheel = b"wheel 2.29.0"
        self.assets = {"v2.29.0/agent_annotate-2.29.0-py3-none-any.whl": wheel,
                       "v2.29.0/SHA256SUMS": f"{hashlib.sha256(wheel).hexdigest()}  agent_annotate-2.29.0-py3-none-any.whl\n".encode()}
        for version in ("2.30.0", "2.33.0", "2.34.0", "2.35.0"):
            wheel = version.encode()
            self.assets[f"v{version}/agent_annotate-{version}-py3-none-any.whl"] = wheel
            self.assets[f"v{version}/SHA256SUMS"] = (
                f"{hashlib.sha256(wheel).hexdigest()}  agent_annotate-{version}-py3-none-any.whl\n".encode())
        for name in ("inspect", "fetch", "free_bytes", "install", "sync_skills", "restart", "doctor", "capabilities", "disable_databases"):
            setattr(rollout, name, getattr(self, name))

    def on(self, version):
        self.version = version
        self.pages = dict.fromkeys(self.pages, version)
        return self

    def _maybe_fail(self, step):
        self.calls.append(step)
        if self.fail == step:
            self.fail = None  # fails once; the rollback's own call succeeds
            raise self.rollout.Failed(step, "injected")

    def inspect(self):
        pages = [{"project": "proj", "slug": s, "port": self.ports[s], "base": "", "action": "restart"} for s in self.pages]
        pages.append({"project": "proj", "slug": "memory", "port": 18719, "base": "",
                      "backend": "json",
                      "action": "page registry lacks a valid directory, current document or port"})
        return {"version": self.version, "pages": pages, "skills": [str(p) for p in self.skills]}

    def fetch(self, url):
        key = url.split("/download/")[-1]
        if self.fail == "preflight" and key.endswith(".whl"):
            return b"tampered"
        if key not in self.assets:
            raise OSError("404")
        return self.assets[key]

    def free_bytes(self):
        return 1 if self.fail == "disk" else 50 * 1024 ** 3

    def install(self, url):
        self._maybe_fail("install")
        self.version = url.rsplit("agent_annotate-", 1)[1].split("-py3")[0]

    def sync_skills(self):
        self._maybe_fail("skills")
        for path in self.skills:
            (path / "SKILL.md").write_text(f"skill {self.version}")
            (path / "new.md").write_text("added")

    def restart(self, project, slug, **options):
        self._maybe_fail(f"restart {slug}")
        self.pages[slug] = self.version
        if options:
            assert options["migrate_db"] is True
            if options["hold_json"]:
                self.holds.add(slug)
            elif options["move"]:
                self.holds.discard(slug)
            reason = "held for this rollout" if slug in self.holds else "injected import failure" if self.fail == f"import {slug}" else ""
            self.backends[slug] = "json" if reason else "page.db"
            return {"storage": {"backend": self.backends[slug], "reason": reason}}

    def disable_databases(self, pages):
        self.calls.append("db off")
        for _project, slug, _port, _base in pages:
            self.backends[slug] = "json"

    def doctor(self):
        self._maybe_fail("check")
        return {"ok": True, "release": {"version": self.version},
                "components": [{"kind": "launcher", "name": "annotate", "status": "OK", "version": self.version},
                               {"kind": "page", "name": "memory", "status": "MISMATCH", "version": "2.27.0"}]}

    def capabilities(self, port, base):
        slug = next(s for s, p in self.ports.items() if p == port)
        return {"version": self.pages[slug]}

    def assert_old(self):
        assert self.version == "2.28.2"
        assert set(self.pages.values()) == {"2.28.2"}
        for path in self.skills:
            assert (path / "SKILL.md").read_text() == "old skill" and not (path / "new.md").exists()


def test_plan_line(rollout, tmp_path):
    FakeMac(tmp_path, rollout)
    info = rollout.plan("M1", "2.29.0")
    assert info["line"] == ("M1 2.28.2 → 2.29.0 · 4 pages: 3 restart, 1 skip (no current version) · "
                            "2 skill dirs · ready")
    assert "not ready: release v2.31.0 not found" in rollout.plan("M1", "2.31.0")["line"]


def test_page_db_apply_holds_fallbacks_and_moves_one_page(rollout, tmp_path):
    mac = FakeMac(tmp_path, rollout, fail="import p1")
    code, line = rollout.apply("M1", "2.30.0", "", hold_json=["p2"])
    assert code == 0 and "JSON: p1 (injected import failure), p2 (held for this rollout), memory (no current version)" in line
    assert mac.backends == {"p0": "page.db", "p1": "json", "p2": "json"}
    mac.fail = None
    code, line = rollout.apply("M1", "2.30.0", "", move_page="p2")
    assert code == 0 and "1 pages restarted" in line and mac.backends["p2"] == "page.db"
    assert mac.calls.count("restart p0") == 1 and mac.calls.count("restart p2") == 2


def test_page_db_rollback_disables_before_install(rollout, tmp_path):
    mac = FakeMac(tmp_path, rollout)
    assert rollout.apply("M1", "2.30.0", "")[0] == 0
    mac.calls.clear()
    assert rollout.rollback("M1", "")[0] == 0
    assert mac.calls[:2] == ["db off", "install"]
    assert set(mac.backends.values()) == {"json"}
    mac.assert_old()


# uzd.9: 2.34.0 reads split pages, 2.35.0 makes them; 2.33.0 and older read comments.json alone.

def test_a_splitting_release_goes_only_onto_a_reader(rollout, tmp_path):
    mac = FakeMac(tmp_path, rollout).on("2.33.0")
    code, line = rollout.apply("M1", "2.35.0", "")
    assert (code, line) == (2, "M1 refused: 2.35.0 splits pages and 2.33.0 cannot read them; apply 2.34.0 first")
    assert mac.version == "2.33.0" and mac.calls == [] and not rollout.FLOOR.exists()
    assert rollout.apply("M1", "2.34.0", "")[0] == 0 and not rollout.FLOOR.exists()  # a reader sets no floor
    assert rollout.apply("M1", "2.35.0", "")[0] == 0 and mac.version == "2.35.0"


def test_a_splitting_release_sets_a_floor_nothing_goes_below(rollout, tmp_path):
    mac = FakeMac(tmp_path, rollout, fail="restart p1").on("2.34.0")
    code, line = rollout.apply("M1", "2.35.0", "")
    assert code == 1 and "rolled back to 2.34.0 · doctor ok" in line  # 2.35 -> 2.34 touches no data
    assert json.loads(rollout.FLOOR.read_text()) == {"version": "2.34.0"} and mac.version == "2.34.0"
    mac.calls.clear()
    old = {"version": "2.33.0", "wheel_url": "unused", "skills": [], "pages": []}
    with pytest.raises(rollout.Failed, match="2.33.0 cannot read pages that 2.35.0 or later split on this Mac; "
                                             "roll back to 2.34.0 or later"):
        rollout.restore(tmp_path, old, [])  # whether or not a split file exists
    assert mac.calls == [] and mac.version == "2.34.0"
    rollout.raise_floor("2.20.0")  # never lowered
    assert json.loads(rollout.FLOOR.read_text()) == {"version": "2.34.0"}
    rollout.FLOOR.write_text("{")
    code, line = rollout.apply("M1", "2.35.0", "")
    assert code == 1 and "floor.json is unreadable" in line and line.endswith("nothing changed")
    assert mac.version == "2.34.0"


def test_one_apply_or_rollback_at_a_time(rollout, tmp_path):
    mac = FakeMac(tmp_path, rollout).on("2.33.0")
    assert rollout.apply("M1", "2.34.0", "")[0] == 0
    entered, resume, install, result = threading.Event(), threading.Event(), rollout.install, {}

    def paused(url):  # the rollback has passed its floor check and is about to install 2.33.0
        entered.set()
        resume.wait(10)
        install(url)

    rollout.install = paused
    worker = threading.Thread(target=lambda: result.update(rollback=rollout.rollback("M1", "")))
    worker.start()
    try:
        assert entered.wait(10)
        rollout.install = install
        refused = (2, "M1 refused: another apply or rollback is running on this Mac; try again when it ends")
        assert rollout.apply("M1", "2.35.0", "") == refused
        assert rollout.rollback("M1", "") == refused
        assert mac.version == "2.34.0" and not rollout.FLOOR.exists()
    finally:
        resume.set()
        worker.join(10)
    assert result["rollback"][0] == 0 and mac.version == "2.33.0"
    assert "2.33.0 cannot read them" in rollout.apply("M1", "2.35.0", "")[1]  # the lock went with the rollback


def test_plan_says_what_apply_refuses(rollout, tmp_path):
    mac = FakeMac(tmp_path, rollout).on("2.30.0")
    rollout.raise_floor("2.34.0")
    assert rollout.plan("M1", "2.33.0")["line"].endswith(
        "not ready: 2.33.0 cannot read pages that 2.35.0 or later split on this Mac; roll back to 2.34.0 or later")
    mac.on("2.33.0")
    assert rollout.plan("M1", "2.35.0")["line"].endswith(
        "not ready: 2.35.0 splits pages and 2.33.0 cannot read them; apply 2.34.0 first")
    assert rollout.plan("M1", "2.34.0")["line"].endswith("ready")


def test_the_floor_survives_power_loss(rollout, monkeypatch):
    synced, real = [], os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: (synced.append(stat.S_ISDIR(os.fstat(fd).st_mode)), real(fd))[1])
    rollout.raise_floor("2.34.0")
    assert synced == [False, True]  # the file, then its directory after the rename


def test_rollback_below_the_reader_from_a_splitting_release_installed_by_hand(rollout, tmp_path):
    mac = FakeMac(tmp_path, rollout).on("2.33.0")
    assert rollout.apply("M1", "2.34.0", "")[0] == 0
    mac.on("2.35.0")  # `uv tool install` outside rollout: no floor yet
    mac.calls.clear()
    code, line = rollout.rollback("M1", "")
    assert code == 1 and line.startswith("M1 FAILED at rollback floor (2.33.0 cannot read")
    assert mac.calls == [] and mac.version == "2.35.0" and rollout.floor() == (2, 34, 0)


def test_page_db_failed_mac_check_disables_before_old_wheel(rollout, tmp_path):
    mac = FakeMac(tmp_path, rollout, fail="check")
    code, line = rollout.apply("M1", "2.30.0", "")
    assert code == 1 and "rolled back to 2.28.2" in line
    assert mac.calls[mac.calls.index("db off") + 1] == "install"
    assert set(mac.backends.values()) == {"json"}
    mac.assert_old()


def test_later_move_preserves_the_release_rollback(rollout, tmp_path):
    mac = FakeMac(tmp_path, rollout)
    assert rollout.apply("M1", "2.30.0", "", hold_json=["p2"])[0] == 0
    code, line = rollout.apply("M1", "2.30.0", "", move_page="p2")
    assert code == 0 and "release rollback kept" in line
    assert rollout.entries()[-1]["action"] == "move"
    assert rollout.rollback("M1", "")[0] == 0
    assert set(mac.backends.values()) == {"json"}
    mac.assert_old()


def test_unknown_or_unrestartable_move_does_nothing(rollout, tmp_path):
    mac = FakeMac(tmp_path, rollout)
    for options in ({"hold_json": ["typo"]}, {"move_page": "memory"}, {"move_page": "missing"}):
        assert rollout.apply("M1", "2.30.0", "", **options)[0] == 2
    assert not mac.calls


def test_receipt_does_not_call_an_existing_skipped_database_json(rollout, tmp_path):
    mac = FakeMac(tmp_path, rollout)
    inspect = mac.inspect
    def stopped_database():
        result = inspect()
        result["pages"][-1]["backend"] = "sqlite"
        return result
    rollout.inspect = stopped_database
    code, line = rollout.apply("M1", "2.30.0", "")
    assert code == 0 and "1 skipped" in line and line.endswith("JSON: none")


def test_m1_defaults_to_holding_fld_and_sorts_small_pages_first(rollout, tmp_path):
    mac = FakeMac(tmp_path, rollout)
    mac.pages["fld-stack-round8"] = mac.version
    mac.ports["fld-stack-round8"] = 18720
    inspect = mac.inspect
    def sized_pages():
        result = inspect()
        for page in result["pages"]:
            page["bytes"] = {"p0": 1000, "p1": 10, "p2": 100, "fld-stack-round8": 10000}.get(page["slug"], 0)
        return result
    rollout.inspect = sized_pages
    assert rollout.apply("M1", "2.30.0", "")[0] == 0
    assert mac.backends["fld-stack-round8"] == "json"
    assert [call for call in mac.calls if call.startswith("restart ")] == [
        "restart p1", "restart p2", "restart p0", "restart fld-stack-round8"]
    assert rollout.apply("M1", "2.30.0", "", move_page="fld-stack-round8")[0] == 0
    assert mac.backends["fld-stack-round8"] == "page.db"


def test_apply_ok_then_rollback(rollout, tmp_path, capsys):
    mac = FakeMac(tmp_path, rollout)
    assert rollout.main(["apply", "2.29.0", "--mac", "M1"]) == 0
    assert capsys.readouterr().out.strip() == ("M1 2.29.0 ok · 3 pages restarted · 1 skipped · doctor ok · "
                                               "rollback kept: 2.28.2")
    assert mac.version == "2.29.0" and set(mac.pages.values()) == {"2.29.0"}
    assert (mac.skills[0] / "new.md").exists()
    assert rollout.main(["rollback", "--mac", "M1"]) == 0
    assert capsys.readouterr().out.strip() == "M1 back on 2.28.2 · 3 pages restarted · doctor ok"
    mac.assert_old()
    log = [json.loads(line) for line in (tmp_path / "rollout/log.ndjson").read_text().splitlines()]
    assert [(e["action"], e["result"]) for e in log] == [("apply", "ok"), ("rollback", "ok")]


@pytest.mark.parametrize("step", ["install", "skills", "restart p1", "check"])
def test_each_step_fails_once_and_rolls_back(rollout, tmp_path, capsys, step):
    mac = FakeMac(tmp_path, rollout, fail=step)
    assert rollout.main(["apply", "2.29.0", "--mac", "M1"]) == 1
    line = capsys.readouterr().out.strip()
    assert line == f"M1 FAILED at {step} (injected) · rolled back to 2.28.2 · doctor ok"
    mac.assert_old()
    if step == "restart p1":  # only the pages the apply touched restart again: p0 and the refused p1
        assert mac.calls.count("restart p0") == 2 and mac.calls.count("restart p1") == 2
        assert mac.calls.count("restart p2") == 0
    assert json.loads((tmp_path / "rollout/log.ndjson").read_text())["result"] == "failed"


def test_rollback_restores_a_skill_with_an_absolute_symlink(rollout, tmp_path, capsys):
    mac = FakeMac(tmp_path, rollout, fail="restart p1")
    target = tmp_path / "state-target"
    target.mkdir()
    (mac.skills[0] / "state").symlink_to(target)  # the live annotate skill links its state dir absolutely
    assert rollout.main(["apply", "2.29.0", "--mac", "M1"]) == 1
    assert capsys.readouterr().out.strip() == "M1 FAILED at restart p1 (injected) · rolled back to 2.28.2 · doctor ok"
    mac.assert_old()
    assert os.readlink(mac.skills[0] / "state") == str(target)


def test_check_fails_when_a_page_stays_old(rollout, tmp_path, capsys):
    mac = FakeMac(tmp_path, rollout)
    real = mac.restart
    mac.rollout.restart = lambda project, slug: None if slug == "p2" else real(project, slug)
    assert rollout.main(["apply", "2.29.0", "--mac", "M1"]) == 1
    assert "FAILED at check (not on 2.29.0: page p2)" in capsys.readouterr().out


@pytest.mark.parametrize("fail", ["preflight", "disk"])
def test_preflight_changes_nothing(rollout, tmp_path, capsys, fail):
    mac = FakeMac(tmp_path, rollout, fail=fail)
    assert rollout.main(["apply", "2.29.0", "--mac", "M1"]) == 1
    assert "FAILED at preflight" in capsys.readouterr().out
    assert mac.calls == [] and [p.name for p in (tmp_path / "rollout").iterdir()] == ["rollout.lock"]
    mac.assert_old()


def test_install_runs_uv_with_the_wheel(rollout, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    uv.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {tmp_path}/uv-args\n")
    uv.chmod(uv.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    rollout.install("https://example.test/agent_annotate-2.29.0-py3-none-any.whl")
    assert (tmp_path / "uv-args").read_text().splitlines() == [
        "tool", "install", "--python", "3.12", "--force",
        "agent-annotate[mcp] @ https://example.test/agent_annotate-2.29.0-py3-none-any.whl"]


def fake_orca(tmp_path, monkeypatch, tail):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (tmp_path / "tail.json").write_text(json.dumps({"ok": True, "result": {"terminal": {"tail": tail}}}))
    orca = bin_dir / "orca"
    orca.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$@\" >> {tmp_path}/orca-calls\n"
        "case \"$4\" in\n"
        "  create) echo '{\"ok\": true, \"result\": {\"terminal\": {\"handle\": \"term_x\"}}}' ;;\n"
        f"  read) cat {tmp_path}/tail.json ;;\n"
        "esac\n")
    orca.chmod(orca.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return tmp_path / "orca-calls"


def test_remote_without_approval_sends_nothing(rollout, tmp_path, monkeypatch, capsys):
    calls = fake_orca(tmp_path, monkeypatch, [])
    for argv in (["apply", "2.29.0", "--mac", "M5"], ["plan", "2.29.0", "--mac", "M5"], ["rollback", "--mac", "M5"]):
        assert rollout.main(argv) == 2
        assert capsys.readouterr().out.strip() == (
            "refused: M5 needs Chang's yes · ask on the page, then add --approval \"card #N\"")
    assert rollout.main(["apply", "2.29.0", "--mac", "M5", "--approval", "card $HOME"]) == 2
    assert not calls.exists()


def test_remote_apply_with_approval(rollout, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rollout.uuid, "uuid4", lambda: type("U", (), {"hex": "abc123def456" * 3})())
    marker = "ROLLOUT-END-abc123def456"
    calls = fake_orca(tmp_path, monkeypatch, [
        "mkdir -p ~/.local/share/annotate-rollout/stage-abc123def456 && ...", "rollout.py: OK", "M5 2.35.0 ok · 4 pages restarted · 2 skipped · doctor ok · rollback kept: 2.34.0", marker])
    assert rollout.main(["apply", "2.35.0", "--mac", "M5", "--approval", "card #212"]) == 0
    assert capsys.readouterr().out.strip().startswith("M5 2.35.0 ok · 4 pages restarted")
    sent = calls.read_text().splitlines()
    assert sent[:4] == ["--environment", "M5Max", "terminal", "create"]
    command = sent[sent.index("--command") + 1]
    assert "$" not in command and "--local --approval 'card #212'" in command
    # Downloaded into this request's own folder and checked; bootstrap places it only where none is placed.
    stage = "~/.local/share/annotate-rollout/stage-abc123def456"
    assert command.startswith(f"mkdir -p {stage} && cd {stage} && curl")
    assert "shasum -a 256 -c -" in command and "/v2.35.0/rollout.py" in command
    assert (f"python3 -I {stage}/rollout.py bootstrap 2.35.0 --mac M5 --local && "
            "python3 -I ~/.local/share/annotate-rollout/rollout.py apply 2.35.0") in command
    assert "close" in sent
    entry = json.loads((tmp_path / "rollout/log.ndjson").read_text())
    assert entry["approval"] == "card #212" and entry["version"] == "2.35.0"


def _remote_text(rollout, tmp_path, monkeypatch, argv):
    """The text remote() types on M5 for `argv`."""
    calls = fake_orca(tmp_path, monkeypatch, ["ROLLOUT-END-abc123def456"])
    monkeypatch.setattr(rollout.uuid, "uuid4", lambda: type("U", (), {"hex": "abc123def456" * 3})())
    rollout.main([*argv, "--mac", "M5", "--approval", "card #1"])
    sent = calls.read_text().splitlines()
    return sent[len(sent) - sent[::-1].index("--command")]  # the latest call's


def test_remote_older_plan_never_replaces_the_controller_across_a_concurrent_apply(rollout, tmp_path, monkeypatch):
    """Review 5: plan 2.33.0 paused where the old text sat between its floor check and its copy; a 2.35.0
    apply raises the floor; the plan resumes. The controller stays, and the rollback is refused."""
    mac = FakeMac(tmp_path, rollout).on("2.33.0")
    assert rollout.apply("M5", "2.34.0", "")[0] == 0  # the last good apply's backup is 2.33.0; no floor yet
    controller, record = SCRIPT.read_bytes(), rollout.HOME / "controller.json"
    (rollout.HOME / "rollout.py").write_bytes(controller)
    record.write_text('{"version": "2.34.0"}\n')
    home, assets, bin_dir = tmp_path / "m5", tmp_path / "assets", tmp_path / "m5bin"
    for path in (home / ".local/share", assets, bin_dir):
        path.mkdir(parents=True)
    (home / ".local/share/annotate-rollout").symlink_to(rollout.HOME)  # M5's state is this test's
    old = b"print('M5 2.33.0 updater: back on 2.33.0')\n"
    (assets / "rollout.py").write_bytes(old)
    (assets / "SHA256SUMS").write_text(f"{hashlib.sha256(old).hexdigest()}  rollout.py\n")
    curl = bin_dir / "curl"  # parks until `go` exists: the window between the floor check and the copy
    curl.write_text(f'#!/bin/sh\nfor a; do last=$a; done\necho "$last" >> {tmp_path}/curl-calls\n'
                    f'i=0; while [ ! -f {tmp_path}/go ] && [ $i -lt 300 ]; do sleep 0.1; i=$((i+1)); done\n'
                    f'cp {assets}/"$(basename "$last")" .\n')
    curl.chmod(0o755)
    env = {"HOME": str(home), "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "ANNOTATE_ROLLOUT_MAC": "M5",
           "UV_TOOL_DIR": str(tmp_path / "no-tools"), "UV_TOOL_BIN_DIR": str(tmp_path / "no-bin")}
    plan = subprocess.Popen(["/bin/sh", "-c", _remote_text(rollout, tmp_path, monkeypatch, ["plan", "2.33.0"])],
                            cwd=home, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        for _ in range(300):
            if (tmp_path / "curl-calls").exists() or plan.poll() is not None:
                break
            threading.Event().wait(0.1)
        mac.fail = "restart p1"  # 2.35.0 splits its first page, fails, and recovers to 2.34.0
        assert "rolled back to 2.34.0" in rollout.apply("M5", "2.35.0", "")[1]
        assert rollout.floor() == (2, 34, 0)
    finally:
        (tmp_path / "go").write_text("")
        output = plan.communicate(timeout=60)[0]
    assert (rollout.HOME / "rollout.py").read_bytes() == controller, output
    assert "M5 FAILED at plan (agent-annotate is not installed" in output  # the guarded controller ran the plan
    assert json.loads(record.read_text()) == {"version": "2.34.0"}
    rollback = subprocess.run(["/bin/sh", "-c", _remote_text(rollout, tmp_path, monkeypatch, ["rollback"])],
                              cwd=home, env=env, capture_output=True, text=True, timeout=60)
    assert "M5 FAILED at rollback floor (2.33.0 cannot read pages" in rollback.stdout, rollback.stdout + rollback.stderr
    assert mac.version == "2.34.0"


def test_the_controller_is_replaced_only_under_the_lock_and_only_upward(rollout, tmp_path):
    mac = FakeMac(tmp_path, rollout).on("2.34.0")
    for version in ("2.33.0", "2.34.0", "2.35.0"):
        body = f"controller {version}".encode()
        mac.assets[f"v{version}/rollout.py"] = body
        mac.assets[f"v{version}/SHA256SUMS"] += f"{hashlib.sha256(body).hexdigest()}  rollout.py\n".encode()
    rollout.CONTROLLER.parent.mkdir(parents=True)
    rollout.CONTROLLER.write_bytes(b"guarded 2.34.0")
    rollout.CONTROLLER_RECORD.write_text('{"version": "2.34.0"}\n')
    assert rollout.update_controller("M1", "2.33.0") == rollout.update_controller("M1", "2.34.0") == (0, "kept")
    assert rollout.CONTROLLER.read_bytes() == b"guarded 2.34.0"
    entered, resume, fetch, result = threading.Event(), threading.Event(), rollout.fetch, {}

    def paused(url):  # checked against the floor and this controller; about to fetch the new one
        if url.endswith("/rollout.py"):
            entered.set()
            resume.wait(10)
        return fetch(url)

    rollout.fetch = paused
    worker = threading.Thread(target=lambda: result.update(update=rollout.update_controller("M1", "2.35.0")))
    worker.start()
    try:
        assert entered.wait(10)
        refused = (2, "M1 refused: another apply or rollback is running on this Mac; try again when it ends")
        assert rollout.apply("M1", "2.35.0", "") == rollout.rollback("M1", "") == refused
    finally:
        resume.set()
        worker.join(10)
    assert result["update"] == (0, "replaced") and rollout.CONTROLLER.read_bytes() == b"controller 2.35.0"
    assert json.loads(rollout.CONTROLLER_RECORD.read_text()) == {"version": "2.35.0"}
    mac.assets["v2.35.0/rollout.py"] = b"tampered"
    rollout.CONTROLLER_RECORD.write_text('{"version": "2.34.0"}\n')
    with pytest.raises(rollout.Failed, match="rollout.py does not match its SHA256SUMS"):
        rollout.update_controller("M1", "2.35.0")
    assert rollout.CONTROLLER.read_bytes() == b"controller 2.35.0"


def test_a_newer_release_takes_over_the_controller_and_runs_the_request(tmp_path):
    home, releases = tmp_path / "home", tmp_path / "releases"
    folder = home / ".local/share/annotate-rollout"
    folder.mkdir(parents=True)
    (folder / "rollout.py").write_bytes(SCRIPT.read_bytes())
    (folder / "controller.json").write_text('{"version": "2.34.0"}\n')
    new = b"import sys; print('M5 2.35.0 controller ran', *sys.argv[1:])\n"
    (releases / "v2.35.0").mkdir(parents=True)
    (releases / "v2.35.0/rollout.py").write_bytes(new)
    (releases / "v2.35.0/SHA256SUMS").write_text(f"{hashlib.sha256(new).hexdigest()}  rollout.py\n")
    proc = subprocess.run([sys.executable, "-I", str(folder / "rollout.py"), "plan", "2.35.0", "--mac", "M5", "--local"],
                          capture_output=True, text=True, timeout=60,
                          env={"HOME": str(home), "PATH": os.environ["PATH"], "ANNOTATE_ROLLOUT_MAC": "M5",
                               "ANNOTATE_ROLLOUT_RELEASES": releases.as_uri(), "UV_TOOL_DIR": str(tmp_path / "t"),
                               "UV_TOOL_BIN_DIR": str(tmp_path / "b")})
    assert proc.stdout == "M5 2.35.0 controller ran plan 2.35.0 --mac M5 --local\n", proc.stdout + proc.stderr
    assert (folder / "rollout.py").read_bytes() == new
    assert json.loads((folder / "controller.json").read_text()) == {"version": "2.35.0"}


def test_remote_without_a_floor_keeping_controller_runs_nothing_older(rollout, tmp_path, monkeypatch):
    for argv in (["plan", "2.33.0"], ["rollback"]):
        text = _remote_text(rollout, tmp_path, monkeypatch, argv)
        assert "curl" not in text and "bootstrap" not in text
        assert text.startswith("if test -f ~/.local/share/annotate-rollout/controller.json; then true; else echo "
                               "'M5 refused: no floor-keeping rollout.py there yet; apply' 2.34.0 or later first; "
                               "false; fi && python3 -I")


def _m5_shell(rollout, tmp_path):
    """M5 as its terminal sees it: its rollout folder is this test's HOME, with no controller placed;
    curl serves release 2.34.0's rollout.py (this one) and its SHA256SUMS. Returns (home, env, bin)."""
    home, assets, bin_dir = tmp_path / "m5", tmp_path / "assets", tmp_path / "m5bin"
    for path in (home / ".local/share", assets, bin_dir, rollout.HOME):
        path.mkdir(parents=True, exist_ok=True)
    (home / ".local/share/annotate-rollout").symlink_to(rollout.HOME)
    (assets / "rollout.py").write_bytes(SCRIPT.read_bytes())
    (assets / "SHA256SUMS").write_text(f"{hashlib.sha256(SCRIPT.read_bytes()).hexdigest()}  rollout.py\n")
    curl = bin_dir / "curl"
    curl.write_text(f'#!/bin/sh\nfor a; do last=$a; done\n/bin/cp {assets}/"$(basename "$last")" .\n')
    curl.chmod(0o755)
    env = {"HOME": str(home), "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "ANNOTATE_ROLLOUT_MAC": "M5",
           "UV_TOOL_DIR": str(tmp_path / "no-tools"), "UV_TOOL_BIN_DIR": str(tmp_path / "no-bin")}
    return home, env, bin_dir


def _until(done):
    for _ in range(300):
        if done():
            return
        threading.Event().wait(0.1)


def test_two_first_applies_place_one_whole_controller(rollout, tmp_path, monkeypatch):
    """Review 6: two first applies on a Mac with no controller. The first pauses after its copy; the second
    opens the same copy target and is killed there; the first publishes and runs. Whatever they leave, the
    controller is the release's whole rollout.py, both runs used it, and a retry runs it."""
    home, env, bin_dir = _m5_shell(rollout, tmp_path)
    cp = bin_dir / "cp"  # the first copy waits after copying; the second truncates its target and hangs
    cp.write_text("#!/bin/sh\nfor a; do last=$a; done\n"
                  f"if mkdir {tmp_path}/cp1 2>/dev/null; then /bin/cp \"$@\"; touch {tmp_path}/cp1/done; wait=go1\n"
                  f"else : > \"$last\"; touch {tmp_path}/cp2; wait=go2; fi\n"
                  f"i=0; while [ ! -f {tmp_path}/$wait ] && [ $i -lt 300 ]; do sleep 0.1; i=$((i+1)); done\n")
    cp.chmod(0o755)
    text = _remote_text(rollout, tmp_path, monkeypatch, ["apply", "2.34.0"])

    def start(stage):  # each request names its own download folder
        return subprocess.Popen(["/bin/sh", "-c", text.replace("stage-abc123def456", stage)], cwd=home, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)

    first = start("stage-first")
    _until(lambda: (tmp_path / "cp1/done").exists() or first.poll() is not None)
    second = start("stage-second")
    _until(lambda: (tmp_path / "cp2").exists() or second.poll() is not None)
    (tmp_path / "go1").write_text("")
    first_out = first.communicate(timeout=60)[0]
    if second.poll() is None:
        os.killpg(second.pid, signal.SIGKILL)  # the second copy is interrupted
    second_out = second.communicate(timeout=60)[0]
    retry = subprocess.run(["/bin/sh", "-c", text.replace("stage-abc123def456", "stage-retry")], cwd=home, env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
    assert rollout.CONTROLLER.read_bytes() == SCRIPT.read_bytes(), first_out
    assert json.loads(rollout.CONTROLLER_RECORD.read_text()) == {"version": "2.34.0"}
    for output in (first_out, second_out, retry.stdout):  # the controller ran the apply: no tool installed here
        assert "agent-annotate is not installed" in output, output
    assert not list(rollout.HOME.glob("stage-*"))


@pytest.mark.parametrize("record", ["", '{"version": "2.3'], ids=["stopped-after-the-rename", "truncated"])
def test_a_bootstrap_cut_short_is_placed_again(rollout, tmp_path, monkeypatch, record):
    """Review 6: the controller is in place but its record is empty (the run stopped after the rename, with the
    record opened) or cut off. That is no controller: rollback and older releases are refused, and the next
    apply of a floor-keeping release places it again and runs on it."""
    home, env, _bin = _m5_shell(rollout, tmp_path)
    rollout.CONTROLLER.write_bytes(SCRIPT.read_bytes())
    rollout.CONTROLLER_RECORD.write_text(record)

    def run(argv):
        return subprocess.run(["/bin/sh", "-c", _remote_text(rollout, tmp_path, monkeypatch, argv)], cwd=home,
                              env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60).stdout

    for argv in (["rollback"], ["plan", "2.33.0"]):
        assert "M5 refused: no floor-keeping rollout.py there yet; apply 2.34.0 or later first" in run(argv)
    output = run(["apply", "2.34.0"])
    assert "agent-annotate is not installed" in output, output
    assert json.loads(rollout.CONTROLLER_RECORD.read_text()) == {"version": "2.34.0"}
    assert rollout.CONTROLLER.read_bytes() == SCRIPT.read_bytes()


def test_bootstrap_places_one_checked_controller_under_the_lock_record_last(rollout, monkeypatch):
    def release(name, body, listed=None):
        stage = rollout.HOME / name
        stage.mkdir(parents=True)
        (stage / "rollout.py").write_bytes(body)
        (stage / "SHA256SUMS").write_text(f"{hashlib.sha256(listed or body).hexdigest()}  rollout.py\n")
        return stage / "rollout.py"

    tampered = release("stage-tampered", b"tampered", listed=b"controller 2.34.0")
    assert rollout.bootstrap("M5", "2.34.0", tampered) == (
        1, "M5 FAILED at bootstrap (downloaded v2.34.0 rollout.py does not match its SHA256SUMS) · no controller placed")
    assert not rollout.CONTROLLER.exists() and not rollout.CONTROLLER_RECORD.exists()
    write_atomic, first = rollout.write_atomic, release("stage-first", b"controller 2.34.0")

    def crash(path, data):  # power lost after the controller's rename, before its record
        if path == rollout.CONTROLLER_RECORD:
            raise OSError("power lost")
        write_atomic(path, data)

    monkeypatch.setattr(rollout, "write_atomic", crash)
    assert rollout.bootstrap("M5", "2.34.0", first)[1] == "M5 FAILED at bootstrap (power lost) · no controller placed"
    assert rollout.CONTROLLER.read_bytes() == b"controller 2.34.0" and rollout.controller_version() is None
    entered, resume, result = threading.Event(), threading.Event(), {}

    def paused(path, data):  # the first run, about to publish
        if path == rollout.CONTROLLER:
            entered.set()
            resume.wait(10)
        write_atomic(path, data)

    monkeypatch.setattr(rollout, "write_atomic", paused)
    worker = threading.Thread(target=lambda: result.update(first=rollout.bootstrap("M5", "2.34.0", first)))
    worker.start()
    second = release("stage-second", b"controller 2.34.0, second download")
    try:
        assert entered.wait(10)
        assert rollout.bootstrap("M5", "2.34.0", second) == (
            2, "M5 refused: another apply or rollback is running on this Mac; try again when it ends")
    finally:
        resume.set()
        worker.join(10)
    assert result["first"] == (0, "") and rollout.controller_version() == (2, 34, 0)
    assert rollout.bootstrap("M5", "2.34.0", second) == (0, "")  # rechecked under the lock: one is placed
    assert rollout.CONTROLLER.read_bytes() == b"controller 2.34.0"


def test_status_reads_remote_versions_from_the_log(rollout, tmp_path, capsys):
    mac = FakeMac(tmp_path, rollout)
    mac.version = "2.29.0"
    rollout.releases = lambda: [(2, 28, 2), (2, 29, 0)]
    rollout.log({"mac": "M5", "action": "apply", "remote": True, "result": "ok", "version": "2.28.2"})
    assert rollout.main(["status"]) == 0
    assert capsys.readouterr().out.strip() == "M1 2.29.0 ok · M5 2.28.2 (1 behind) · M1Max16 unknown"


def test_wrong_mac_and_unsafe_sandbox_refused(rollout, tmp_path, monkeypatch, capsys):
    FakeMac(tmp_path, rollout)
    assert rollout.main(["apply", "2.29.0", "--mac", "M5", "--local"]) == 2
    assert "this Mac is M1" in capsys.readouterr().out
    monkeypatch.setenv("UV_TOOL_DIR", str(tmp_path / "tools"))
    monkeypatch.delenv("UV_TOOL_BIN_DIR", raising=False)
    assert rollout.main(["apply", "2.29.0", "--mac", "M1"]) == 2
    assert "live annotate launcher" in capsys.readouterr().out


def test_release_lists_rollout_py_beside_the_wheel(tmp_path):
    spec = importlib.util.spec_from_file_location("release", SCRIPT.parent / "release.py")
    release = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release)
    from agent_annotate.updates import _checksum
    wheel = tmp_path / "agent_annotate-2.29.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    (tmp_path / "rollout.py").write_bytes(SCRIPT.read_bytes())
    sums = release.checksums(wheel)
    assert _checksum(sums.encode(), wheel.name) == hashlib.sha256(b"wheel").hexdigest()
    line = next(x for x in sums.splitlines() if "  rollout.py" in x)  # what the remote's grep -F picks
    assert line == f"{hashlib.sha256(SCRIPT.read_bytes()).hexdigest()}  rollout.py"


def test_a_failed_rollback_says_so(rollout, tmp_path, capsys):
    FakeMac(tmp_path, rollout)

    def down():
        raise rollout.Failed("check", "doctor down")

    rollout.doctor = down
    assert rollout.main(["apply", "2.29.0", "--mac", "M1"]) == 1
    line = capsys.readouterr().out.strip()
    assert line.startswith("M1 FAILED at check (doctor down) · rollback to 2.28.2 FAILED at check (doctor down); backup ")
    assert "rolled back" not in line
