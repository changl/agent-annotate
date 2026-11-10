"""Fast PR gate. --full runs every test, on M1Max16 (M1 backup) through wm-test when a private route is configured."""

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TESTS = (
    "tests/test_http_cache.py",
    "tests/test_fast_writes.py",
    "tests/test_package_contract.py",
    "tests/test_skill_contract_parity.py",
    "tests/test_skillgen.py",
    "tests/test_skill_cli.py",
    "tests/test_decision_quality.py",
    "tests/test_cli_reads.py",
    "tests/test_pagegen.py",
    "tests/test_ask_cards.py",
    "tests/test_ask_numbers.py",
    "tests/test_ask_section.py",
    "tests/test_fix_lines.py",
    "tests/test_version_ready.py",
    "tests/test_publish_version.py",
    "tests/test_page_names.py",
    "tests/test_fleet.py",
    "tests/test_reports.py",
    "tests/test_measurement.py",
    "tests/test_meta_stamp_safety.py",
    "tests/test_bench.py",
    "tests/test_mcp_server_build.py",
    "tests/test_review_access.py",
    "tests/test_reviewer_authoring_boundary.py",
    "tests/test_delivery.py",
    "tests/test_explicit_send.py",
    "tests/test_ci_runner.py",
    "tests/test_ci_route.py",
    "tests/test_windmill_profiles.py",
    "tests/test_browser_ports.py",
    "tests/test_updates.py",
    "tests/test_funnel.py",
    "tests/test_published_urls.py",
    "tests/test_project_state.py",
    "tests/test_copy_state.py",
    "tests/test_copy_api.py",
    "tests/test_review_history.py",
    "tests/test_history_cache.py",
    "tests/test_categories.py",
    "tests/test_categories_api.py",
    "tests/test_approval_catalog.py",
    "tests/test_approval_catalog_api.py",
    "tests/test_plans_backfill.py",
    "tests/test_categories_parity.py",
    "tests/test_cli_categories.py",
    "tests/test_consolidate.py",
    "tests/test_archive.py",
    "tests/test_port_identity.py",
    "tests/test_deployment.py",
    "tests/test_unpublish_scope.py",
    "tests/test_transport_opts.py",
    "tests/test_revive.py",
    "tests/test_backend_review_fixes.py",
    "tests/test_ci_contract.py",
    "tests/test_fix_ui_server.py",
    "tests/test_version_guard.py",
    "tests/test_session_start.py",
    "tests/test_workspace.py",
    "tests/test_workspace_commands.py",
    "tests/test_shim_install.py",
    "tests/test_ui_numbering.py",
    "tests/test_decision_api.py::test_legacy_comment_numbers_stay_fixed_when_cards_are_added_or_renumbered",
    "tests/test_decision_api.py::test_legacy_number_conflict_hint_works_on_retry_without_partial_migration",
    "tests/test_decision_api.py::test_poll_labels_do_not_report_legacy_pinning_as_a_content_change",
    "tests/test_decision_api.py::test_deferred_verdicts_then_submit_emit_exactly_one_session_push",
    "tests/test_decision_api.py::test_an_answer_in_words_rides_the_round_and_counts_as_answered",
    "tests/test_comment_carryover.py::test_carry_forward_moves_card_to_new_version_and_preserves_origin",
    "tests/test_comment_carryover.py::test_rerunning_ask_with_the_same_question_keeps_the_verdict",
)


def full_route(root=ROOT, env=os.environ, config=None):
    """The wm-test command for --full when a private route is configured; None runs it here.

    Inside the host executor (WM_TEST_ARTIFACTS set), without a config, or with
    one that does not register agent-annotate's full profile, --full runs
    locally as before. A registered route that is not ready fails instead of
    silently running the heavy suite here. A routed run tests exactly HEAD, so
    uncommitted or untracked changes are refused rather than left out.
    """
    if env.get("WM_TEST_ARTIFACTS"):
        return None
    config = Path(config or Path.home() / ".config/agent-tools/wm-test.json")
    if not config.is_file():
        return None
    settings = json.loads(config.read_text())
    if "agent-annotate" not in settings.get("repos", {}) or "full" not in settings.get("profiles", {}):
        return None
    if settings.get("ready") is not True:
        raise SystemExit("ci.py --full: the wm-test route for agent-annotate full is configured but not ready; "
                         "fix the route or pass --local")
    git = ["git", "-C", str(root)]
    if subprocess.run([*git, "status", "--porcelain"], capture_output=True, text=True, check=True).stdout.strip():
        raise SystemExit("ci.py --full: uncommitted or untracked changes; commit them "
                         "(the routed run tests exactly HEAD) or pass --local")
    wm_test = shutil.which("wm-test", path=env.get("PATH"))
    if not wm_test:
        raise SystemExit("ci.py --full: the wm-test route is ready but wm-test is not on PATH")
    sha = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    target = ["--target", "auto"] if settings["repos"]["agent-annotate"].get("auto_target") is True else []
    return [wm_test, "agent-annotate", "full", "--sha", sha, "--config", str(config), *target]


def full_chunks(root=ROOT):
    browser = sorted((root / "tests/browser").glob("test_*.py"))
    return [("runtime", ["tests", "--ignore=tests/browser"])] + [
        (f"browser-{i + 1}", [str(path.relative_to(root)) for path in browser[i::3]])
        for i in range(3) if browser[i::3]
    ]


def run_full(workers, junit, root=ROOT):
    """Keep verbose diagnostics on disk; stdout is one receipt even on failure."""
    started = time.monotonic()
    junit = Path(junit).resolve()
    junit.parent.mkdir(parents=True, exist_ok=True)
    suites = ET.Element("testsuites")
    results = []
    failures = []

    def run_chunk(chunk):
        name, targets = chunk
        xml = junit.parent / f"{name}.xml"
        xml.unlink(missing_ok=True)
        with (junit.parent / f"{name}.log").open("w") as log:
            try:
                code = subprocess.run([sys.executable, "-m", "pytest", "-q", *targets,
                                       "-o", "junit_family=legacy", f"--junitxml={xml}"],
                                      cwd=root, stdout=log, stderr=subprocess.STDOUT).returncode
            except OSError as error:
                log.write(str(error))
                code = 1
        try:
            document = ET.parse(xml).getroot()
        except (OSError, ET.ParseError):
            document = ET.Element("testsuites")
        if code and not document.findall(".//failure") and not document.findall(".//error"):
            suite = ET.SubElement(document, "testsuite", name=name, tests="1", failures="1")
            case = ET.SubElement(suite, "testcase", name="pytest-process", classname=name)
            ET.SubElement(case, "failure", message=f"pytest exited {code}; see {name}.log")
        if not document.findall(".//testcase"):
            suite = ET.SubElement(document, "testsuite", name=name, tests="1", failures="1")
            case = ET.SubElement(suite, "testcase", name="missing-results", classname=name)
            ET.SubElement(case, "failure", message="pytest produced no test results")
        return name, document

    checks = [("ruff", [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts/ci.py", "scripts/release.py"]),
              ("js", ["node", "--check"])]
    for name, command in checks:
        suite = ET.SubElement(suites, "testsuite", name=name)
        commands = [command] if name == "ruff" else [command + [str(path)] for path in sorted((root / "src/agent_annotate/web").glob("*.js"))]
        with (junit.parent / f"{name}.log").open("w") as log:
            for argv in commands:
                case = ET.SubElement(suite, "testcase", name=str(argv[-1]) if name == "js" else "check", classname=name)
                try:
                    code = subprocess.run(argv, cwd=root, stdout=log, stderr=subprocess.STDOUT).returncode
                except OSError as error:
                    log.write(str(error))
                    code = 1
                if code:
                    ET.SubElement(case, "failure", message=f"exit {code}; see {name}.log")

    chunks = full_chunks(root)
    # Runtime tests exercise port allocation and detached publishers; finish cleanup first.
    documents = [run_chunk(chunks[0])]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        documents.extend(pool.map(run_chunk, chunks[1:]))
    for name, document in documents:
        chunk_suite = ET.SubElement(suites, "testsuite", name=name)
        for case in document.findall(".//testcase"):
            chunk_suite.append(case)

    for suite in suites:
        cases = list(suite)
        failed = [case for case in cases if case.find("failure") is not None or case.find("error") is not None]
        skipped = sum(case.find("skipped") is not None for case in cases)
        suite.set("tests", str(len(cases)))
        suite.set("failures", str(sum(case.find("failure") is not None for case in cases)))
        suite.set("errors", str(sum(case.find("error") is not None for case in cases)))
        suite.set("skipped", str(skipped))
        results.append(f"{suite.get('name')}={len(cases) - len(failed) - skipped}p/{len(failed)}f/{skipped}s")
        failures.extend(f"{case.get('file', case.get('classname', ''))}::{case.get('name')}" for case in failed)
    duration = time.monotonic() - started
    suites.set("time", f"{duration:.2f}")
    ET.ElementTree(suites).write(junit, encoding="utf-8", xml_declaration=True)
    print(f"{'FAIL' if failures else 'PASS'} " + " ".join(results)
          + f" duration={duration:.1f}s failing={','.join(failures) or '-'} junit={junit}", flush=True)
    return int(bool(failures))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true",
                        help="Run every test, including browser coverage: through the configured wm-test route, "
                             "or here when none is configured")
    parser.add_argument("--local", action="store_true",
                        help="with --full, run here even when a wm-test route is configured (no receipt)")
    parser.add_argument("--work-item", help="with a routed --full, the bead or task the receipt belongs to")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=4,
                        help="full-suite subprocesses (1 for a serial timing baseline; default: 4)")
    parser.add_argument("--junitxml", type=Path,
                        default=Path(os.environ.get("WM_TEST_ARTIFACTS", ".ci-results")) / "junit.xml",
                        help="merged full-suite JUnit report; chunk XML and logs are saved beside it")
    args = parser.parse_args(argv)
    route = full_route() if args.full and not args.local else None
    if route:
        work_item = ["--work-item", args.work_item] if args.work_item else []
        sys.exit(subprocess.run(route + work_item).returncode)
    if args.full:
        return run_full(args.workers, args.junitxml)
    subprocess.run([sys.executable, "-m", "ruff", "check", "src", "tests", "scripts/ci.py", "scripts/release.py"], check=True)
    for script in sorted((Path(__file__).resolve().parents[1] / "src/agent_annotate/web").glob("*.js")):
        subprocess.run(["node", "--check", str(script)], check=True)
    subprocess.run([sys.executable, "-m", "pytest", "-q", *TESTS], check=True)


if __name__ == "__main__":
    sys.exit(main())
