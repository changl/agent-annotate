"""Stage 4 rollout.py: every apply step fails once and rolls back; the remote gate sends nothing."""

import hashlib
import importlib.util
import json
import os
import stat
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
        for version in ("2.30.0",):
            wheel = version.encode()
            self.assets[f"v{version}/agent_annotate-{version}-py3-none-any.whl"] = wheel
            self.assets[f"v{version}/SHA256SUMS"] = (
                f"{hashlib.sha256(wheel).hexdigest()}  agent_annotate-{version}-py3-none-any.whl\n".encode())
        for name in ("inspect", "fetch", "free_bytes", "install", "sync_skills", "restart", "doctor", "capabilities", "disable_databases"):
            setattr(rollout, name, getattr(self, name))

    def _maybe_fail(self, step):
        self.calls.append(step)
        if self.fail == step:
            self.fail = None  # fails once; the rollback's own call succeeds
            raise self.rollout.Failed(step, "injected")

    def inspect(self):
        pages = [{"project": "proj", "slug": s, "port": self.ports[s], "base": "", "action": "restart"} for s in self.pages]
        pages.append({"project": "proj", "slug": "memory", "port": 18719, "base": "",
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


def test_page_db_failed_mac_check_disables_before_old_wheel(rollout, tmp_path):
    mac = FakeMac(tmp_path, rollout, fail="check")
    code, line = rollout.apply("M1", "2.30.0", "")
    assert code == 1 and "rolled back to 2.28.2" in line
    assert mac.calls[mac.calls.index("db off") + 1] == "install"
    assert set(mac.backends.values()) == {"json"}
    mac.assert_old()


def test_unknown_or_unrestartable_move_does_nothing(rollout, tmp_path):
    mac = FakeMac(tmp_path, rollout)
    for options in ({"hold_json": ["typo"]}, {"move_page": "memory"}, {"move_page": "missing"}):
        assert rollout.apply("M1", "2.30.0", "", **options)[0] == 2
    assert not mac.calls


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
    assert mac.calls == [] and not (tmp_path / "rollout").exists()
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
        "python3 -I ~/.local/share/annotate-rollout/rollout.py apply 2.29.0 --mac M5 --local; echo ROLLOUT\"\"-END-abc123def456",
        "rollout.py: OK", "M5 2.29.0 ok · 4 pages restarted · 2 skipped · doctor ok · rollback kept: 2.28.2", marker])
    assert rollout.main(["apply", "2.29.0", "--mac", "M5", "--approval", "card #212"]) == 0
    assert capsys.readouterr().out.strip().startswith("M5 2.29.0 ok · 4 pages restarted")
    sent = calls.read_text().splitlines()
    assert sent[:4] == ["--environment", "M5Max", "terminal", "create"]
    command = sent[sent.index("--command") + 1]
    assert "$" not in command and "--local --approval 'card #212'" in command
    assert "shasum -a 256 -c -" in command and "/v2.29.0/rollout.py" in command
    assert "close" in sent
    entry = json.loads((tmp_path / "rollout/log.ndjson").read_text())
    assert entry["approval"] == "card #212" and entry["version"] == "2.29.0"


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
