"""scripts/verified_install.py installs a wheel only behind a validated full receipt for its exact commit."""

import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("verified_install", ROOT / "scripts/verified_install.py")
verified_install = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verified_install)

COMMIT = "229b9432ea6c" + "0" * 28
PASSED = {"validated": True, "verdict": "passed", "cleanup": "verified", "attempt_id": "a" * 64,
          "result_job_id": "0193a5b2-0000-7000-8000-000000000001", "evidence_url": "https://wm.example/jobs_u/get/x",
          "counts": {"passed": 1877, "failed": 0, "skipped": 2}}


def _wheel(directory, version="2.27.7", stamp=None):
    path = directory / f"agent_annotate-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        if stamp is not False:
            archive.writestr("agent_annotate/_build.json",
                             json.dumps(stamp or {"build_id": COMMIT, "tag": "v" + version}))
    return path


def _tool(directory, name, body):
    path = directory / name
    path.write_text(f"#!{sys.executable}\nimport json, os, sys\n{body}\n")
    path.chmod(0o755)
    return path


@pytest.fixture
def rig(tmp_path, monkeypatch):
    log = tmp_path / "calls.jsonl"
    record = f"open({str(log)!r}, 'a').write(json.dumps([os.path.basename(sys.argv[0]), sys.argv[1:], os.environ.get('UV_TOOL_DIR')]) + '\\n')"
    wm = _tool(tmp_path, "wm-test", record + "\nsys.stdout.write(os.environ.get('FAKE_WM_OUT', ''))"
               "\nsys.stderr.write(os.environ.get('FAKE_WM_ERR', ''))\nsys.exit(int(os.environ.get('FAKE_WM_CODE', '0')))")
    uv = _tool(tmp_path, "uv", record)
    request = tmp_path / "state.json"
    request.write_text(json.dumps({"job_id": "0193a5b2-0000-7000-8000-00000000f10w",
                                   "request": {"repo": "agent-annotate", "profile": "full", "sha": COMMIT}}))
    monkeypatch.setenv("FAKE_WM_OUT", json.dumps(PASSED))
    target = tmp_path / "disposable-tools"

    def run(*extra, wheel=None):
        argv = [str(wheel or _wheel(tmp_path)), "--request", str(request), "--wm-test", str(wm), "--uv", str(uv),
                "--tool-dir", str(target), "--bin-dir", str(tmp_path / "disposable-bin"), *extra]
        return verified_install.main(argv)

    def calls():
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []

    return run, calls, request, target, tmp_path


def test_validated_receipt_for_the_wheels_commit_installs_that_wheel(rig, capsys):
    run, calls, request, target, tmp_path = rig
    assert run() == 0
    (wm, wm_args, _), (uv, uv_args, tool_dir) = calls()
    assert (wm, wm_args) == ("wm-test", ["validate", "0193a5b2-0000-7000-8000-00000000f10w", "--request", str(request)])
    wheel = (tmp_path / "agent_annotate-2.27.7-py3-none-any.whl").resolve()
    assert (uv, uv_args) == ("uv", ["tool", "install", "--python", "3.12", "--force", f"agent-annotate[mcp] @ {wheel.as_uri()}"])
    assert tool_dir == str(target)
    report = json.loads(capsys.readouterr().out)
    assert report["installed"] is True and report["build_id"] == COMMIT and report["receipt_job"] == PASSED["result_job_id"]


def test_dry_run_validates_and_installs_nothing(rig):
    run, calls, *_ = rig
    assert run("--dry-run") == 0
    assert [name for name, *_ in calls()] == ["wm-test"]


@pytest.mark.parametrize("code, out, err, reason", [
    ("2", "", json.dumps({"validated": False, "error": "receipt_not_passed_and_clean:failed"}), "receipt_not_passed_and_clean"),
    ("2", "", json.dumps({"validated": False, "error": "receipt_identity_sha"}), "receipt_identity_sha"),
    ("0", json.dumps({**PASSED, "cleanup": "uncertain"}), "", "wm-test exit 0"),
    ("0", "not json", "", "wm-test exit 0"),
])
def test_rejected_receipt_installs_nothing(rig, monkeypatch, capsys, code, out, err, reason):
    run, calls, *_ = rig
    monkeypatch.setenv("FAKE_WM_CODE", code)
    monkeypatch.setenv("FAKE_WM_OUT", out)
    monkeypatch.setenv("FAKE_WM_ERR", err)
    assert run() == 2
    assert [name for name, *_ in calls()] == ["wm-test"]
    assert reason in json.loads(capsys.readouterr().err)["error"]


@pytest.mark.parametrize("change", [{"sha": "f" * 40}, {"profile": "fast"}, {"repo": "other"}])
def test_receipt_for_another_commit_profile_or_repo_is_refused_before_validation(rig, change):
    run, calls, request, *_ = rig
    state = json.loads(request.read_text())
    state["request"].update(change)
    request.write_text(json.dumps(state))
    assert run() == 2
    assert calls() == []


@pytest.mark.parametrize("stamp", [False, {"build_id": "main", "tag": "v2.27.7"}, {"build_id": COMMIT, "tag": "v2.27.6"}])
def test_wheel_without_an_exact_stamp_is_refused(rig, stamp):
    run, calls, *_, tmp_path = rig
    assert run(wheel=_wheel(tmp_path, stamp=stamp)) == 2
    assert calls() == []


def test_downloaded_wheel_must_match_the_release_checksums(tmp_path, monkeypatch):
    body = _wheel(tmp_path).read_bytes()
    url = "https://github.com/changl/agent-annotate/releases/download/v2.27.7/agent_annotate-2.27.7-py3-none-any.whl"
    sums = {"good": verified_install.hashlib.sha256(body).hexdigest(), "bad": "0" * 64}
    for case, digest in sums.items():
        files = {url: body, url.rsplit("/", 1)[0] + "/SHA256SUMS": f"{digest}  {url.rsplit('/', 1)[1]}\n".encode()}
        monkeypatch.setattr(verified_install, "urlopen", lambda address, timeout: io.BytesIO(files[address]))
        if case == "good":
            assert verified_install.fetch(url, tmp_path / "wheels").read_bytes() == body
        else:
            with pytest.raises(ValueError, match="SHA256SUMS"):
                verified_install.fetch(url, tmp_path / "rejected")
            assert not (tmp_path / "rejected").exists() or not any((tmp_path / "rejected").iterdir())
