# Complete, immutable Review versions (agent-annotate-b93)

Regression baseline: `005a450` (agent-annotate 2.28.2). Final integration base: `2c52d27` (`origin/changl/next-2.28.3`, including PRs #92 and #93). Final runtime source: `2b6c9cf`; worktree: `changl/version-ready`. Rebases retained the numbering fix, CI/port isolation and every Unreleased entry.

## Result

`annotate new DIR --from page.md --version vN --publish --ask` remains one command. Generation stages the page, source and version-specific cards without changing current or History. Server checks use an unguessable draft preview; ordinary version/content/static routes cannot load the draft. The final card batch validates every staged card and number before saving cards, withdrawing omitted unanswered questions and switching current/History under the shared store lock. A failed commit restores the prior store, metadata and current link. No quiet window or additional agent completion command exists. Reviewer store/comment/category responses also hide Review items whose versions are not published, covering legacy or interrupted seeds without rewriting the feedback store.

Shown versions cannot be regenerated or published again. `annotate ask` also refuses to add Review cards to a shown version and names the next version to use. Authoring changes through the server's single/batch/PUT card APIs receive the same refusal; reviewer answers, replies and resolution/withdrawal lifecycle actions remain available. A stable question asked in a new version gets a new record with lineage, preserving the previous version's wording.

Optional `new --fixes vN` is exposed as `current.meta.json.history[].fixes` through `GET /current.meta.json`. For example, the copied-page CLI run published `v654` with `fixes: "v653"`. No header indicator or shell/adapter code changed; that indicator follows PR #94.

Older page servers must advertise `review_ready: true` before the CLI sends a publication batch. Otherwise it refuses before posting any cards. Draft verification binds the rendered HTML and card file to the checked fingerprint, so editing or regenerating the draft requires fresh checks.

## CLI proof on copies

All estate roots, launchers and configuration were redirected into `/tmp/aa-version-ready-measure`; transport was local. FLD was copied with APFS clones; its live directory, servers and routes were not changed. Final local validation was constrained to ports 18700–18799. Early fixture invocations briefly used their default local ports 8811, 8812, 8817 and 8818; all five copied-test server processes were identified by their pytest directories and stopped, and validation was rerun within the sandbox range. No live page was restarted or changed. No release, deployment, installed runtime/skill sync, M5 or M1Max16 work occurred.

- Baseline 2.28.2 normal publish: one command, exit 0, `v652` current. A separate baseline number-conflict run exited 2 but still left `v652` current, with its proposed #14568 round absent from the feedback store.
- Candidate normal publish on the copied FLD page: one command, exit 0, complete `v653` current. A fresh page also published its initial `v1` in one command.
- A copied FLD round deliberately reused existing number 463 on another anchor: exit 2 / HTTP 409; requested `v655` stayed out of History, `v654` remained current, and `comments.json` was byte-for-byte unchanged. The staged version can be retried.
- `--fixes v653` round-tripped as `history[-1].fixes == "v653"` on copied FLD `v654`.

## Agent steps and output

Same normal-publish command template and compact default output, using the pinned baseline source and candidate worktree source with the existing Python environment:

| Measurement | Before | After |
|---|---:|---:|
| Agent command count | 1 | 1 |
| Standard output, UTF-8 bytes | 111 | 111 |
| Standard error, bytes | 80 | 0 |
| Combined output, characters | 189 | 109 |
| Output token proxy, ceil(characters / 4) | 48 | 28 |

The baseline stderr was an erroneous exact-page-resolution diagnostic from the early `publish-version` call, even though the command completed. Standard-output size is unchanged. These are output/step measurements, not model-context token telemetry or a claim about total agent token savings. Timing was observed under concurrent tests and is not a controlled latency comparison.

## Tests and instructions

The three original regression cases failed on the baseline: failed seeding changed current, a shown version could be republished, and `--fixes` was unavailable. Dedicated coverage now includes bad cards, number conflicts, failed/unavailable checks, checked-file changes, incomplete batches, storage rollback, shown-version/card immutability, fix metadata and old-server refusal.

- On the final integration base, `scripts/ci.py --full --local --workers 3` exercised the entire suite: **1822 runtime passed, 2 skipped**; browser chunks **96 passed**, **103 passed / 4 failed**, **94 passed**; ruff and all seven JS checks passed (1429.7 s total).
- The four failures were the dense-workspace fixture's earlier `v0` questions lacking a published History entry. The fixture now declares that earlier publication; its full **six-case rerun passed**, retaining every product assertion. All **297 unique browser cases** were exercised. The original merged receipt remains FAIL rather than being rewritten; this is not a claim of a single all-green full-suite receipt.
- The subsequent one-line version-specific card-file fix and its regression passed the complete readiness/page-generation/publication chunk: **83 passed**, including all **21 readiness cases**. The prior security/concurrency/verification chunk passed **88** cases; the post-visibility desktop/iPad update/numbering chunk passed **18**. These cover failed cards, number collisions, checked-file changes, rollback, peer publication, stale markers, immutable shown versions and metadata round-trips.
- [GitHub Checks on the final runtime](https://github.com/changl/agent-annotate/actions/runs/41547072745) passed: **1286 passed, 4 skipped** on Linux; ruff/JS checks passed. The new readiness and publish-version modules are included in CI.
- Earlier manual parallel runs encountered popup/image-scroll timing failures. Their isolated reruns passed; neither failed in the final isolated full sweep. No live/public Funnel verification was performed, as the task requires copies only.

Tests use this worktree's absolute `src` in `PYTHONPATH` with `/Users/changlee/projects/agent-annotate/codex/.venv/bin/python`. Rendering/lifecycle fixtures now explicitly author drafts and make complete synthetic snapshots visible; the new publication tests use direct HTTP against real sandbox servers.

The Claude, Codex and plugin `SKILL.md` copies gained one sentence: shown versions are frozen, changes/additional Review cards use the next version, and `--fixes vN` marks a follow-up. Both checked-in `page.md` references explain staged generation, the complete one-command publish, retries and `history[].fixes`; the Codex bundle receives that shared reference at packaging time. `docs/skill-commands.md` was regenerated from the execution parser for the added flag and changed `--ask` help. No installed copies were synced.
