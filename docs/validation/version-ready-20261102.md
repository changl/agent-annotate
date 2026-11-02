# Complete, immutable Review versions (agent-annotate-b93)

Regression baseline: `005a450` (agent-annotate 2.28.2). Integration base: `b131005` (`origin/changl/next-2.28.3`, including PR #92). Runtime code: `e4489a3`; worktree: `changl/version-ready`. The rebase retained the numbering fix and both Unreleased changelog entries.

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

- Frozen-runtime full non-browser suite at `e4489a3`: **1781 passed, 2 skipped** (254.35 s).
- Publish/version/numbering/verification focused chunk: 101 passed. Final readiness/publication/security/metadata-alias chunk: **64 passed**, including all **18 readiness cases** and both generated/manual HTML publication paths.
- [GitHub Checks on the frozen runtime](https://github.com/changl/agent-annotate/actions/runs/41541130819) passed: **1244 passed, 4 skipped** on Linux (164.12 s for pytest; 3m7s job). Ruff and JavaScript syntax checks passed. The readiness and publish-version modules are included in the CI test list.
- Full browser suite: four file-disjoint chunks, 297 cases exercised (294 initially passed; the three failing cases later passed focused reruns). First-pass chunks were 73 passed / 1 failed, 79 passed / 1 failed, 71 passed / 1 failed, and 71 passed. The legacy-number fixture was updated to expect only published items and use an allocated sandbox port. Popup and image-scroll checks passed individually; the image scroll assertion also failed in a combined rerun (3526 vs 3296), so the full browser sweep is not a single clean pass. Isolated original 2.28.2 and final candidate image checks both passed. The post-visibility desktop/iPad update/numbering chunk passed all 18 cases.

Tests use this worktree's absolute `src` in `PYTHONPATH` with `/Users/changlee/projects/agent-annotate/codex/.venv/bin/python`. Rendering/lifecycle fixtures now explicitly author drafts and make complete synthetic snapshots visible; the new publication tests use direct HTTP against real sandbox servers.

The Claude, Codex and plugin `SKILL.md` copies gained one sentence: shown versions are frozen, changes/additional Review cards use the next version, and `--fixes vN` marks a follow-up. Both checked-in `page.md` references explain staged generation, the complete one-command publish, retries and `history[].fixes`; the Codex bundle receives that shared reference at packaging time. `docs/skill-commands.md` was regenerated from the execution parser for the added flag and changed `--ask` help. No installed copies were synced.
