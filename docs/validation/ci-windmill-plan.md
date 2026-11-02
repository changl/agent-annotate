# Full-suite automation proposal (agent-annotate-va0)

Status: coordinator approved the plan for later activation on 2026-11-02 (blocking ask answered). No M1Max16 or Windmill changes made by this worker. Chang approval is still needed for the extra installs and Windmill changes below.

## Trigger and return path

Keep Windmill in Docker on the M1. Reuse the existing wm-test request/receipt protocol and fixed host executor rather than installing a Windmill worker on macOS. The dispatcher launches a deterministic Python command in an Orca terminal on environment M1Max16; it must select that environment explicitly and fail closed if remote placement is unverified. There is no agent launch.

Initial trigger: `wm-test agent-annotate full --sha <40-character-commit> --work-item agent-annotate-va0`. The existing clean-HEAD `scripts/ci.py --full` route can submit this without inspecting logs; `--local` is the explicit override. Submission and wait are scripts and use zero AI tokens. A passing job returns one result line and a Windmill evidence link, with merged JUnit and per-chunk logs retained as artifacts.

After the first remote and backup proofs, add a Windmill schedule polling trusted PR heads every minute. It submits each new SHA once after the quick check passes, sets a named `full-suite` GitHub status pending and then success/failure on that exact SHA, and cancels superseded admissions without assuming that cancellation has cleaned up a running host process. This avoids exposing the private Windmill endpoint to GitHub-hosted runners. A fine-grained GitHub credential needs repository read and commit-status write only. PR forks/untrusted branches require human authorization before execution under the host user. The one-command trigger remains available and uses the same deduplication key.

## Placement, backup and cleanup

M1Max16 is the primary; this M1 is the automatic backup. One heavy slot per machine, isolated clean checkout/venv/state/tmp per run, browser port leases in 18700–18799, explicit source/profile/toolchain/environment hashes, bounded timeouts and process-group cleanup. Both targets run the same candidate SHA and frozen uv.lock. No installed annotate package, live page, live route, M5 or shared development checkout is changed.

Fail over automatically on primary preflight unavailability before execution, or after positive proof that a started attempt has exited and cleanup succeeded. An assertion failure is a test failure, not a reason to seek a green backup. A lost connection or uncertain ownership yields HOLD and a failed/blocked status; do not launch overlapping work on the backup. If both targets are unavailable, return infrastructure failure with the Windmill link. Preserve attempt/host identity in the receipt, and do not hide a primary infrastructure failure in the backup result.

## Installation and authorization gate

Known from the dispatch: M1Max16 has uv, Python 3.12, annotate 2.28.2 and Command Line Tools. This worker has not independently inspected or changed it. Chrome plus the Playwright browser downloads are already approved. Additional approval requested: Node LTS (needed by `node --check`), the repo-local frozen dev/mcp/browser Python environment, and a reviewed copy of the fixed host executor plus private config/credential files and scratch/artifact directories. No Windmill worker or host daemon is proposed. Use the existing Orca remote bridge after verifying its exact environment/terminal placement capabilities; if it cannot launch a plain command there, return for a placement decision instead of silently installing another service.

M1 already has Chrome, Playwright browser cache, uv and the pilot host executor; this work adds only its checkout-local .venv. Its local wm-test config says ready=true but records submitter/publisher credential expiry on 2026-10-27. Activation must renew narrowly scoped identities, refresh pinned executor/profile/toolchain hashes and validate actual auth; the ready flag alone is insufficient.

Changes needing approval in Windmill: dispatcher target selection and backup policy; receipt schema/validation including host identity; scoped credential renewal; polling schedule and GitHub status reporter. Keep existing pilot recovery/cancel/receipt semantics. First prove remote pass, a forced primary-preflight failure with backup pass, assertion failure without fallback, disconnected/unknown execution without duplicate fallback, cleanup, and exact-SHA status reporting.

## Judgment and tokens

Dependency setup, source verification, lint, syntax checks, test selection, execution, JUnit parsing, skip allowlist checking, cleanup, fallback, artifact validation and status publication are deterministic scripts. Passing runs require **0 agent launches and 0 AI tokens**. Existing GitHub checks and the pilot executor already consume zero AI tokens; agent-driven local runs add unmeasured model tokens for starting, monitoring and interpreting them, so a numeric historical baseline is not claimed.

A failing assertion, changed product expectation, security judgment or flaky-test fix may require a developer. Windmill first returns the failing IDs and logs without invoking a model. The coordinator explicitly deferred optional Haiku triage. No model integration is part of activation; a failed run returns evidence to a developer. No small-model call is necessary for a passing run or infrastructure fallback.

## Dependency boundary

The pilot profiles, clean-HEAD routing and their tests are carried into this PR. Its unmerged runtime argv/deployment/version-guard changes and verified-install helper are not required to execute or report a full suite; they remain on their owning branch. Any inherited failing tests in those areas must be reported separately. No release-wheel install or post-test deployment belongs to this automation.
