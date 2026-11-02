"""Full-suite receipts and subprocess chunking without running the full suite here."""

import importlib.util
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("ci_runner", Path(__file__).parents[1] / "scripts/ci.py")
ci = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ci)


@pytest.mark.parametrize("workers", [1, 4])
def test_real_pytest_chunks_merge_pass_fail_skip_and_keep_logs(tmp_path, monkeypatch, capsys, workers):
    browser = tmp_path / "tests/browser"
    browser.mkdir(parents=True)
    (tmp_path / "tests/test_runtime.py").write_text("def test_runtime(): assert True\n")
    for name, source in {"a": "def test_ok(): assert True\n", "b": "def test_bad(): assert False\n",
                         "c": "import pytest\ndef test_skip(): pytest.skip('fixture')\n"}.items():
        (browser / f"test_{name}.py").write_text(source)
    original_run = subprocess.run

    def run(argv, **kwargs):
        if argv[1:3] == ["-m", "ruff"]:
            return subprocess.CompletedProcess(argv, 0)
        return original_run(argv, **kwargs)

    monkeypatch.setattr(ci.subprocess, "run", run)
    report = tmp_path / "artifacts with spaces/junit.xml"
    assert ci.run_full(workers, report, tmp_path) == 1
    line = capsys.readouterr().out
    assert len(line.splitlines()) == 1
    assert line.startswith("FAIL ")
    assert "runtime=1p/0f/0s" in line
    assert "browser-1=1p/0f/0s" in line
    assert "browser-2=0p/1f/0s" in line
    assert "browser-3=0p/0f/1s" in line
    assert "tests/browser/test_b.py::test_bad" in line
    assert "duration=" in line
    root = ET.parse(report).getroot()
    assert sum(int(s.get("failures")) for s in root) == 1
    assert len(root.findall(".//testcase")) == 5  # four tests and lint
    assert "AssertionError" in (report.parent / "browser-2.log").read_text()
    assert len(list(report.parent.glob("browser-*.xml"))) == 3


def test_missing_xml_and_tool_failures_cannot_report_a_pass(tmp_path, monkeypatch, capsys):
    (tmp_path / "runtime.xml").write_text('<testsuites><testsuite><testcase name="stale"/></testsuite></testsuites>')
    monkeypatch.setattr(ci.subprocess, "run", lambda argv, **kwargs: subprocess.CompletedProcess(argv, 2))
    assert ci.run_full(1, tmp_path / "junit.xml", tmp_path) == 1
    line = capsys.readouterr().out
    assert "ruff=0p/1f/0s" in line
    assert "runtime::pytest-process" in line
    assert "stale" not in line
    assert len(ET.parse(tmp_path / "junit.xml").findall(".//failure")) == 2


def test_full_chunk_manifest_includes_each_browser_file_once():
    chunks = ci.full_chunks()
    assert chunks[0] == ("runtime", ["tests", "--ignore=tests/browser"])
    paths = [path for _, targets in chunks[1:] for path in targets]
    assert len(paths) == len(set(paths))
    assert set(paths) == {str(path.relative_to(ci.ROOT)) for path in (ci.ROOT / "tests/browser").glob("test_*.py")}


def test_full_local_cli_returns_failure_and_respects_serial_and_report(monkeypatch, tmp_path):
    report = tmp_path / "junit.xml"
    calls = []
    monkeypatch.setattr(ci, "full_route", lambda: pytest.fail("local run consulted route"))
    monkeypatch.setattr(ci, "run_full", lambda workers, junit: calls.append((workers, junit)) or 1)
    assert ci.main(["--full", "--local", "--workers", "1", "--junitxml", str(report)]) == 1
    assert calls == [(1, report)]


def test_full_rejects_unbounded_workers():
    with pytest.raises(SystemExit):
        ci.main(["--full", "--local", "--workers", "100"])


@pytest.mark.parametrize("xml", ["<testsuites><testsuite tests='0'/></testsuites>", "invalid", ""])
def test_successful_process_with_empty_or_broken_xml_fails_closed(tmp_path, monkeypatch, capsys, xml):
    def run(argv, **kwargs):
        if "pytest" in argv and xml:
            (tmp_path / "runtime.xml").write_text(xml)
        return subprocess.CompletedProcess(argv, 0)
    monkeypatch.setattr(ci.subprocess, "run", run)
    assert ci.run_full(1, tmp_path / "junit.xml", tmp_path) == 1
    assert "runtime::missing-results" in capsys.readouterr().out


def test_subprocess_launch_failure_still_writes_receipt(tmp_path, monkeypatch, capsys):
    def run(argv, **kwargs):
        raise FileNotFoundError("fixture missing executable")
    monkeypatch.setattr(ci.subprocess, "run", run)
    assert ci.run_full(1, tmp_path / "junit.xml", tmp_path) == 1
    assert "runtime::pytest-process" in capsys.readouterr().out
    assert "fixture missing executable" in (tmp_path / "runtime.log").read_text()
