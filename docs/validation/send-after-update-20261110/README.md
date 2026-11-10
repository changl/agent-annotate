# Send after a page update

Bead: `agent-annotate-z4l`. Baseline: `origin/main` at `3aa043e`.

Send excluded saved follow-up notes after the agent resolved their card, in
both the browser's pending count and the server's push filter. Publication
also creates a new record for a reissued question: text keyed to the old id
went to the old card even when its number appeared again. Reply-box text was
persisted locally but was absent from the Send plan.

The shared document Send path now includes reply drafts and targets the
latest card with the same number, falling back to the original record when
that card is absent. Publication carries saved notes and pending text answers
to a reissued number, using the existing draft privacy snapshots. Approval
choices stay on the version whose evidence they answered. Unsent notes remain
sendable after resolution. The summary displays the words being sent.

## Rebex reproduction

Read the `rebex/rebex` registry entry to locate
`/Users/changlee/projects/rebex/reviews/rebex`, then copied that directory into
temporary directories. The copy's `page.db` was removed to replay its JSON
export. On the copy only, selected historical v109 and reopened card #167,
retaining its sent choice, then typed and saved a follow-up. Published v111
without that card and resolved the old card through the real HTTP route.

Each run used its own temporary registry, bus and delivery journal, a loopback
server in 18700–18799, and headless Google Chrome through Playwright. The owner
was replaced with `sandbox-only`; Orca dispatch returned a simulated
`input_accepted` receipt. No live page, server or owner terminal was changed.

Before the fix: pending **1 → 0**, desktop Send disabled, phone Send disabled.
After the fix: pending **1 → 1**, both Send controls enabled; one Send recorded
the exact note in `rounds.ndjson`, dispatched once, and cleared pending to zero.

| Evidence | Before | After |
| --- | --- | --- |
| Typed text before publication | [Open editor](before-open-desktop.png) | |
| Desktop after publication | [Disabled Send](before-saved-desktop.png) | [Send summary with the preserved note](after-saved-desktop.png) |
| Phone after publication | [Disabled Send bar](before-saved-phone.png) | [Send bar with one pending item](after-saved-phone.png) |

## Checks

`tests/browser/test_send_after_update.py::test_feedback_survives_publication_and_reaches_owner`
has 16 cases: open note editor, saved follow-up note, saved text answer, and
reply editor × same numbered card reissued/card removed × desktop/390 px phone.
It publishes through the actual ready transaction, refreshes and reloads,
checks both Send controls and summary text, sends to the simulated owner,
checks the destination record and round, and reloads again to rule out a
duplicate send.

Against the extracted baseline source, all four saved-note cases fail with
pending zero. Both same-number open-editor cases fail because the text is sent
to the old record; the two removed-card cases already passed. The fixed matrix
passes all 16 cases. After tightening carry to leave already-sent replies from
the same second untouched, all four saved-text-answer cases pass again.

API regressions cover notes resolved before Send, privacy of carried notes
from multiple reviewers, keeping a pending approval on its original evidence,
preserving replies already sent within the same second, and retaining an
earlier confirmed approval when a later pending text answer is carried.
An additional browser regression covers a reviewer replacing an unsent choice
with a text answer before publication: the carried answer sends once and the
superseded choice leaves no stale pending count.

The first fast-gate run under Homebrew Python 3.14 had one unrelated failure:
`test_process_argv_is_exact_where_ps_text_is_lossy` compared the venv launcher
path to macOS's framework executable path. Its isolated rerun passes under
the existing standalone Python 3.12; the final fast gate uses a temporary
Python 3.12 environment with the absolute worktree `src` on `PYTHONPATH`.

Fast-gate tail after rebasing onto main at `4aec53d`
(`python3 scripts/ci.py`):

```text
All checks passed!
.............                                                            [100%]
1519 passed, 7 skipped in 180.49s (0:03:00)
```

Existing browser regressions (`test_explicit_send_browser.py`,
`test_typing_while_cards_arrive.py`, `test_send_dialog_parts.py`,
`test_send_summary_lazy.py`, `test_keep_drafts.py`): **37 passed, 6 skipped**
in 450.08 seconds. The skips require Playwright WebKit, which is not installed.
After rebase, all **17 new browser cases passed** in 212.80 seconds (the
16-case matrix plus the superseded-choice regression). The saved-answer rerun
also passed all four cases in 50.08 seconds.
The final publication/privacy/round API selection passed all 38 tests in
15.59 seconds.

The whole browser suite and physical-device Safari were not run. Live rollout,
a real owner-terminal canary, and merge are left to the coordinator.
