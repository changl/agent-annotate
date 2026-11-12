# D4. Goals and how they travelled: boards, runs and hand-offs

Follow `docs/design/from-zero/briefs/common-data.md`. It overrides anything below.

## Why

The headline number of the new method is cycles to done: how many times a goal comes back to the person before he accepts it. Today nothing counts that. Work is tracked as items on Beads boards, as worker tasks in Orca runs, and in hand-over notes between long-running sessions. The design needs to know how goals actually travelled through those: how long, how many hand-offs, how often reopened, how often a helper said "done" when it was not.

## Sources (read-only; change nothing)

- Beads boards: run `bd where` in each project folder under `~/projects/` and each repo under `~/orca/workspaces/`. Where a board answers, read it with `bd list`, `bd show`, `bd stats` and their `--json` forms. Never create, claim, edit or close anything.
- Orca: `orca worktree ps --json`, `orca orchestration run-list --json` and the read-only `worker-list`, `task-list`, `inbox` forms. Check `--help` first. Never send, reply, start or stop anything. Never run a plain `orca orchestration check`: it takes mail away from its owner. Use only forms that are documented as not consuming mail.
- Hand-over notes: `/Users/changlee/projects/agent-annotate/shared/agents/handoff-*.md` and any `handoff*.md` in other projects' shared folders.
- Cost reports: `/Users/changlee/projects/agent-annotate/shared/agents/cost-3day-20261110/`.
- Git: merged pull requests and release tags of the repos, with `git log` only.

## Build

1. `DATA/corpus/items.jsonl`, one row per board item: `project`, `id`, `type`, `title`, `created`, `closed`, `days_open`, `has_acceptance_checks`, number of checks, `reopened` count, number of comments, parent, and whether a pull request or commit is linked as proof.
2. `DATA/corpus/tasks.jsonl`, one row per worker task in an Orca run, as far as Orca still holds them: `run`, `project`, `task`, `started`, `finished`, `agent`, `model`, `outcome`, `retries`, number of messages between worker and coordinator, number of questions the worker asked, whether the coordinator sent it back.
3. `DATA/corpus/handoffs.jsonl`, one row per hand-over between sessions: `project`, `date`, size of the note in words, how many open items it carried, and how many items carried over from the note before it (things that kept being handed on unfinished).
4. `DATA/corpus/goal_candidates.jsonl`: group items into goals, where a goal is something the person would recognise as one thing he asked for (usually an epic, a release, or a set of items under one parent). For each: `project`, `title` in plain words, `first_seen`, `accepted_or_closed`, `days`, number of items, number of worker tasks, number of releases or pull requests, and whether "done" was ever claimed and then undone.

## Findings file

`docs/design/from-zero/research/d4-goals.md`:

- items, tasks, hand-overs and goal candidates, per project and overall;
- how long a goal takes from first seen to closed: median and 90th percentile;
- share of items with acceptance checks written before the work; does having them change reopen rate or days open?
- how often "done" was claimed and then undone, and what was missed;
- worker tasks: share finished first time, share sent back, share retried or stalled, questions asked per task;
- hand-overs: how often, how big, and how much unfinished work rides from one to the next;
- how many goals were in flight at once, week by week;
- what share of all work on the boards is about the work, and what share is about keeping the working system itself running (tooling, bookkeeping, coordination). This last number matters a great deal: be careful and show how you decided.

## Done means

The four files exist, every number names its command, and you state which of these records cannot support a cycles-per-goal count and what would be needed to get one.
