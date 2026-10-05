"""Fast PR gate. Full browser/runtime verification belongs on the local machine."""

import argparse
import subprocess
import sys
from pathlib import Path

TESTS = (
    "tests/test_package_contract.py",
    "tests/test_skill_contract_parity.py",
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
    "tests/test_categories.py",
    "tests/test_categories_api.py",
    "tests/test_categories_parity.py",
    "tests/test_cli_categories.py",
    "tests/test_ci_contract.py",
    "tests/test_decision_api.py::test_deferred_verdicts_then_submit_emit_exactly_one_session_push",
    "tests/test_decision_api.py::test_an_answer_in_words_rides_the_round_and_counts_as_answered",
    "tests/test_comment_carryover.py::test_carry_forward_moves_card_to_new_version_and_preserves_origin",
    "tests/test_comment_carryover.py::test_rerunning_ask_with_the_same_question_keeps_the_verdict",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="Run all local tests, including installed browser coverage")
    args = parser.parse_args()
    subprocess.run([sys.executable, "-m", "ruff", "check", "src", "tests", "scripts/ci.py", "scripts/release.py"], check=True)
    for script in sorted((Path(__file__).resolve().parents[1] / "src/agent_annotate/web").glob("*.js")):
        subprocess.run(["node", "--check", str(script)], check=True)
    subprocess.run([sys.executable, "-m", "pytest", "-q", *(["tests"] if args.full else TESTS)], check=True)


if __name__ == "__main__":
    main()
