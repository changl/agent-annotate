# bench — before/after agent runs

Every agent-facing change (skill text, CLI output, the markdown format, a
gate) ships on a comparison of real `claude -p` runs: main against the
candidate, same scenarios, same model. The harness is `scripts/bench.py` plus
the fixtures here; neither is part of the package.

## Run

```bash
.venv/bin/python scripts/bench.py --ref main --ref my-branch --runs 3 --json /tmp/bench.json
```

- `--ref` repeats; the first is the baseline. A git ref is exported with
  `git archive`; a directory (`--ref .`) is used as-is, uncommitted edits
  included. `--ref main --ref main` measures the noise floor.
- `--scenario NAME` (repeatable; default all), `--runs N` (default 3),
  `--model` (opus), `--effort` (medium), `--max-budget-usd X` per run,
  `--timeout` (1200 s), `--jobs N` concurrent runs (default 1).
- `--no-model` runs setup and checks only, free: use it to confirm a
  candidate still builds the fixtures before paying for runs.
- `--keep` keeps each sandbox (`transcript.ndjson`, `claude.stderr`, the page)
  and prints its path.

Run it with an interpreter that has the package's dependencies (the project
venv); every build runs under it with `PYTHONPATH=<export>/src`.

## What it measures

Per scenario, per ref: median `[min–max]` of output tokens, thinking tokens,
cache read, cache creation, cost, duration, turns, annotate calls (Bash calls
that run `annotate`) and annotate failures (non-zero exit, `ERROR`, `FAIL`,
`NOT PUBLISHED`, `Traceback`), plus outcome passes; then each later ref's
delta against the first. Failed checks and failing calls are listed under the
table. `--json` keeps every raw row, including per-subcommand counts, failure
excerpts, check details and `diag` (page owned by the run's session, hook
notices, any port below 9400).

## Isolation

Each run gets a fresh `$TMPDIR/annotate-bench-*` sandbox: `ANNOTATE_*` roots
(state, bus, config, settings, shim) inside it, a `bin/annotate` launcher for
the build first on `PATH`, the build's skill at `<cwd>/.claude/skills/annotate`,
and `claude -p --setting-sources project --settings <sandbox settings>
--strict-mcp-config --no-session-persistence --permission-mode dontAsk
--session-id <uuid>`. The sandbox settings allow Bash/Read/Write/Edit/Glob/Grep/
Skill and register the build's UserPromptSubmit hook. `~/.claude/CLAUDE.md`
still loads; it is the same for every ref. Every project is `transport =
"local"` from port 9400 (the launcher adds any project a slug dir names), so
no sandbox page touches a live port, route or registry. Teardown stops every
process whose command line or environment names the sandbox, then deletes it.

## Scenarios

`fixtures/<name>/scenario.json`: `cwd` (project dir name), `files` (sandbox
path → fixture path), optional `setup`, `prompt` (`{slug}` comes from setup),
`checks`. Setup publishes a page as the run's session with `new --publish
--ask`, posts the reviewer's verdicts through the page API with `defer_push`
exactly as the browser does, and submits the round. Check kinds: `live`,
`version_html`, `current`, `cards_json`, `source_cards`, `posed`, `disposed`,
`keywords`.

| Scenario | Prompt | Passes when |
|---|---|---|
| `v1-page` | a 300-word design note with 3 open questions → "Put these notes up as an annotate review page for Chang with a decision card for each open question." | a live registered page, `versions/v1.html`, `cards.json` with 3 cards that each carry context, a recommendation, a consequence per option and evidence anchors on the page, 3 cards posed |
| `round-2` | v1 published and answered (one select, one Answer in words, one accept), round submitted → "Chang submitted his review of orders-status-rename. Read his answers and publish v2 that addresses them." | v2 current and served, no v1 item left open, v2 cards (if any) conform, the Answer-in-words instruction (`reconcile`) is in the v2 source |

## Cost

One opus/medium run, measured 2026-09-27 on main: `v1-page` $0.30 in 48 s,
`round-2` $0.29 in 47 s (`total_cost_usd`, list price; a subscription spends
quota instead). A 3-run comparison of two refs over both scenarios is 12 runs:
about $3.60 and 10 minutes sequential.
