"""Fast PR gate. --full runs every test, on the M1 through wm-test when a private route is configured."""

import argparse
import json
import os
import shutil
import subprocess
import sys
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
    "tests/test_decision_api.py::test_deferred_verdicts_then_submit_emit_exactly_one_session_push",
    "tests/test_decision_api.py::test_an_answer_in_words_rides_the_round_and_counts_as_answered",
    "tests/test_comment_carryover.py::test_carry_forward_moves_card_to_new_version_and_preserves_origin",
    "tests/test_comment_carryover.py::test_rerunning_ask_with_the_same_question_keeps_the_verdict",
)


def full_route(root=ROOT, env=os.environ, config=None):
    """The wm-test command for --full when a private route is configured; None runs it here.

    Inside the M1 executor (WM_TEST_ARTIFACTS set), without a config, or with
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
                         "(the M1 run tests exactly HEAD) or pass --local")
    wm_test = shutil.which("wm-test", path=env.get("PATH"))
    if not wm_test:
        raise SystemExit("ci.py --full: the wm-test route is ready but wm-test is not on PATH")
    sha = subprocess.run([*git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    return [wm_test, "agent-annotate", "full", "--sha", sha, "--config", str(config)]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true",
                        help="Run every test, including browser coverage: through the configured wm-test route, "
                             "or here when none is configured")
    parser.add_argument("--local", action="store_true",
                        help="with --full, run here even when a wm-test route is configured (no receipt)")
    parser.add_argument("--work-item", help="with a routed --full, the bead or task the receipt belongs to")
    args = parser.parse_args(argv)
    route = full_route() if args.full and not args.local else None
    if route:
        print("ci.py --full: running on the M1 through " + " ".join(route[1:5]), flush=True)
        work_item = ["--work-item", args.work_item] if args.work_item else []
        sys.exit(subprocess.run(route + work_item).returncode)
    subprocess.run([sys.executable, "-m", "ruff", "check", "src", "tests", "scripts/ci.py", "scripts/release.py"], check=True)
    for script in sorted((Path(__file__).resolve().parents[1] / "src/agent_annotate/web").glob("*.js")):
        subprocess.run(["node", "--check", str(script)], check=True)
    subprocess.run([sys.executable, "-m", "pytest", "-q", *(["tests"] if args.full else TESTS)], check=True)


if __name__ == "__main__":
    main()
