# Skill simplification validation — 2026-10-16

PR: https://github.com/changl/agent-annotate/pull/24

The Codex benchmark compares v2.25.1 skill text against the seven-step text at `72d7a90`, using the same `72d7a90` runtime for both. Both fixtures ran N=3, interleaved, with `gpt-6.1-sol` at medium effort. The final reference subsequently clarifies nested-heading anchors and accurately describes the shipped refusal boundary; that text correction is not measured below.

## Word counts

Whitespace-separated words, including front matter and examples; no instruction length caps.

| Text | v2.25.1 | Current |
| --- | ---: | ---: |
| SKILL.md | 441 | 380 |
| References | 2731 (6 files) | 481 (1 file) |
| Total | 3172 | 861 |

Claude, Codex and plugin SKILL.md files are byte-identical; reference copies are generated through `sync-skills --packaged .`. Installed user skills and the installed runtime are outside this change.

## Final Codex benchmark

| Fixture | Text | Output tokens, median | Seconds, median | Tool failures, runs 1/2/3 | Outcome checks passed |
| --- | --- | ---: | ---: | --- | --- |
| round-2 | old | 2,109 | 58.6 | 2/1/2 | 3/3 |
| round-2 | new | 2,152 | 46.4 | 0/1/0 | 0/3 |
| v1-page | old | 1,993 | 46.8 | 0/0/1 | 3/3 |
| v1-page | new | 1,187 | 31.1 | 0/0/0 | 1/3 |

Total output across six rounds: 11,640 old → 10,121 new (-13.0%). Round-2 median output increased 2%; v1-page decreased 40%. The strict per-fixture no-increase interpretation is not met. Codex does not report dollar cost in this stream, so no priced-cost claim is made.

All 12 sandbox checks passed. Tool failures count failed shell tool results containing annotate calls; a mixed shell command can include an unrelated failure. Outcome checks are independent of tool exit status.

Per-run values (not a selected subset):

| Fixture | Text | Run | Output tokens | Seconds | Tool failures | Failed outcome checks |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| round-2 | old | 1 | 2,109 | 57.6 | 2 | none |
| round-2 | new | 1 | 2,152 | 46.4 | 0 | disposed:v1 |
| v1-page | old | 1 | 2,099 | 47.5 | 0 | none |
| v1-page | new | 1 | 1,187 | 31.1 | 0 | cards_json |
| round-2 | old | 2 | 1,773 | 207.9 | 1 | none |
| round-2 | new | 2 | 2,675 | 53.9 | 1 | disposed:v1 |
| v1-page | old | 2 | 1,293 | 33.5 | 0 | none |
| v1-page | new | 2 | 1,428 | 78.4 | 0 | none |
| round-2 | old | 3 | 2,373 | 58.6 | 2 | none |
| round-2 | new | 3 | 1,635 | 33.9 | 0 | disposed:v1 |
| v1-page | old | 3 | 1,993 | 46.8 | 1 | none |
| v1-page | new | 3 | 1,044 | 25.7 | 0 | cards_json |

## Findings and limitations

- New round-2 produced v2 with the reconcile-job backfill, but all three runs failed `disposed:v1`. The existing fixture requires explicit old-comment resolution; shipped withdrawal refuses answered questions, and the requested skill omits resolve/carry. This lifecycle gap remains open; no fixture checks were weakened.
- Two new v1-page runs failed `cards_json` because `###` evidence anchors omitted their parent section. The format reference now documents nested-heading grammar. Shipped card refusal accepts a card's own generated anchor even if its evidence IDs are wrong; this report does not claim that broader validation was fixed.
- The earlier complete exploratory Codex N=3 run measured round-2 3,536→2,308 tokens (-35%), 72→55 seconds, outcomes 3/3→1/3; v1-page 2,796→1,960 tokens (-30%), 56→41 seconds, outcomes 2/3→2/3. It used a mutable worktree and exposed shell-temp isolation and reviewer-heading issues; the pinned final table above is the reproducible comparison.
- Claude produced no valid model measurements here because its existing OAuth session was expired. The coordinator explicitly took the Claude half; invalid authentication rows are excluded.

## Validation

- Full non-browser suite: **1,381 passed, 2 skipped**.
- Local CI gate passed; subsequent plan/finding deep-link and reviewer-heading checks passed.
- GitHub CI passed at `ffef199`: https://github.com/changl/agent-annotate/actions/runs/38969308103/job/117203461041.
- Parser-help listing, generated command reference, mentioned command/flag validity, skill parity, linked receipts, full inbox prompts, generator cleanup and benchmark isolation regressions pass.
- `monitor` remains parseable with its existing flags. Packaged hooks do not invoke it; legacy `connect` still invokes it, so it is hidden from default help rather than removed.

## Reproduce

Run from this worktree; the old/new runtimes and texts are pinned:

```sh
env PYTHONPATH=/Users/changlee/orca/workspaces/codex/simplify-skill/src /Users/changlee/projects/agent-annotate/codex/.venv/bin/python scripts/bench.py --ref 72d7a90 --ref 72d7a90 --skill-ref v2.25.1 --skill-ref 72d7a90 --provider codex --scenario round-2 --scenario v1-page --runs 3 --jobs 2 --port-base 9600 --json /tmp/simplify-bench-codex-final.json --keep
```

For the coordinator's Claude half, change `--provider codex` to `--provider claude`, use `--port-base 9400`, and output `/tmp/simplify-bench-claude-final.json`.

Retained source directories for this measured run:

- Old Claude: `/private/var/folders/80/z4mj96kn0dn16r_dc45rv_8w0000gn/T/annotate-bench-builds-94lc4uaw/v2.25.1-2cc0b67/src/agent_annotate/skills/claude`.
- New Claude: `/private/var/folders/80/z4mj96kn0dn16r_dc45rv_8w0000gn/T/annotate-bench-builds-94lc4uaw/HEAD-72d7a90/src/agent_annotate/skills/claude`.
- Codex text is the sibling `skills/codex/SKILL.md`; references are shared from the Claude directory.

## Isolation incident and reversal ledger

An initial Codex attempt exposed a PATH-reset defect: login shells reached installed annotate while preserving temporary state roots. Three fixture-only Funnel paths were created on ports 9600/9620: `/annotate/reviews/orders-status-rename`, `/annotate/orders-service/orders-service`, and `/annotate/orders-service/orders-status-review`. They were narrowly removed after matching the fixture registries, and a Serve-status read verified zero remaining handlers to either port. The coordinator was notified immediately and instructed that no further route changes be made.

No real page content, real annotate registry, installed skill/tool files or user settings were found changed. The harness now restores login-shell PATH and temp prefixes, forces local transport, supplies fake tailscale/cloudflared/orca executables, denies real transport/Orca/installed-annotate execution and outside writes on macOS, and rejects non-sandbox routes/processes. Sandbox servers are stopped by their exact temporary-root match; temporary copied Codex auth files are removed even when evidence directories are retained. The final run passed every sandbox-boundary check.
