# Combined bug-fix integration — 2026-11-01

Integrated PRs 81–85 into `changl/fixes`, based on `064b1d5c34e8d0949768df52c9080c6d6f1d6663` (2.28.0).
Nothing was released, installed, version-bumped, published to live pages, or merged to main.

## Merge receipts

Each PR has its own two-parent `--no-ff` merge commit, in the requested order:

| PR | Source branch | Merge commit | GitHub state |
| --- | --- | --- | --- |
| [81](https://github.com/changl/agent-annotate/pull/81) | `changl/fix-server` | `f7f056ffc393a843c8f445793ed92966e625a4d7` | MERGED |
| [82](https://github.com/changl/agent-annotate/pull/82) | `changl/fix-publish` | `f5468eafc5bb6c33559ab499427f5ec943744a11` | MERGED |
| [83](https://github.com/changl/agent-annotate/pull/83) | `changl/fix-send` | `fe67125dbdb23cfc23e0a8a8a76859496a3d339a` | MERGED |
| [84](https://github.com/changl/agent-annotate/pull/84) | `changl/fix-live` | `b83ffbe647e0e7dea51d7a3b7ae2bfb2537932fc` | MERGED |
| [85](https://github.com/changl/agent-annotate/pull/85) | `changl/fix-drafts` | `bee9817b5efca80ee2cdc8e50d5e90b9ea662dc4` | MERGED |

GitHub confirmed all five as MERGED at `2026-11-01T19:05:29Z`, after pushing the integration branch.
All five still target `changl/fixes`; no `gh pr merge` fallback was needed.
The pushed code/test head before this documentation commit is `491337da9392c6a12b4cd2e9ecdca6b41a9ab256`.

## Conflict resolutions

- `CHANGELOG.md`: retained every PR's Unreleased entries.
- `src/agent_annotate/cli.py`: wrapped the store in the submitted-only projection while retaining current-version metadata for canonical duplicate numbering.
- `tests/test_fast_writes.py`: retained the reader-specific three-part cache key and compared the file snapshot against the file portion of the combined file/version signature.
- `src/agent_annotate/web/shell.js`: retained lost-response recovery through `pollStore`/`LIVE` without applying unrelated changes, while clearing/recovering drafts through their captured document-owned object.

The automatic `sync_server.py` merge was inspected: its response cache retains both current-version invalidation and separate reviewer/agent representations, and agent reads use the submitted-only projection.
The shell retains receipt-only Sent labels across tabs, poll-only LIVE updates, reviewer-controlled STORE adoption, and document-specific draft keys.

## Full combined run

The six chunks covered all 141 test files, each full chunk once.
They used `/Users/changlee/projects/agent-annotate/codex/.venv/bin/python -m pytest` with this worktree's `src` first on PYTHONPATH.
An external test-only pytest plugin allocated port-zero requests inside 18700–18799 and rejected in-process listeners outside that range; subprocess server fixtures received their selected explicit `--port`.
The plugin and manifests did not modify repository test configuration or production configuration.

| Chunk | Original full-run result | Seconds |
| --- | --- | --- |
| Non-browser A–F | 733 passed, 2 skipped | 117.18 |
| Non-browser G–P | 633 passed | 94.52 |
| Non-browser Q–Z plus monitor | 386 passed | 30.44 |
| Browser A–F | 113 passed | 973.19 |
| Browser G–P | 56 passed, 1 failed | 453.52 |
| Browser Q–Z | 93 passed, 2 failed | 845.45 |

The two skips are the existing `tests/test_backend_review_fixes.py` checks gated by `REVIEW_BROWSER=1`; neither is new in these PRs.

### Corrections and focused verification

1. G–P failed `test_a_new_version_waits_in_the_banner_while_the_reviewer_types[rail-chrome]`.
   An unchanged isolated retry also failed, in 10.24 seconds.
   `syncSayHint` searched the document while `stripCard` built a detached template, so the initial hint could stay blank until another keystroke.
   Commit `d6e45cde15f29846c845b4f9fb871280cf592b5c` makes the helper find the hint inside its own card.
   All eight `tests/browser/test_live_updates.py` cases then passed in 67.73 seconds, including Chrome, iPad WebKit, and single-render checks.

2. Q–Z failed both variants of `test_withdrawn_question_keeps_typed_answer_and_its_send_count`.
   Their old assumption was that blur and polling apply a withdrawal, contrary to PR 84's explicit banner rule.
   Commit `491337da9392c6a12b4cd2e9ecdca6b41a9ab256` preserves the original draft/Send-count assertions, adds assertions that blur and polling leave the shown card unchanged, and taps the banner before checking the withdrawn state.
   Both rail/document variants passed in 25.75 seconds.

No timeout was increased, no assertion was removed, and no failure was skipped.
Full chunks were not repeated after these corrections; only the affected regression groups were rerun.
The first five chunks ran on the five-merge head; Q–Z ran after the hint fix.

JUnit reconciliation gives **2,017 distinct passed cases, 2 existing skips, and zero unresolved failures**.
The union of newly added/renamed test functions from all five PRs contains **48 functions / 76 parametrized cases**, all with passing results after the corrections.

## Other checks and cleanup

- `ruff check .`: passed.
- `node --check` for all seven browser JavaScript assets: passed.
- `git diff --check`: passed.
- All integration pytest processes exited; recorded test-owned processes were gone; no TCP listener remained in 18700–18799.
- Browser/server fixtures closed their resources, including failed-test contexts.
- No M5/M1Max16 work or access to the excluded `rebex-library-performance` worktree.

Local raw logs, JUnit, manifests, the new-test coverage receipt, port guard, and cleanup receipt:
`/tmp/aa-fixes-integration-20261101/`.
The full-run failures remain in those receipts; the totals above use the focused passing results for the corrected cases.
