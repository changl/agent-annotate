# E. Where the helpers' effort goes

Follow `docs/design/from-zero/briefs/common-data.md`. It overrides anything below.

## Why

The new method replaces long-lived coordinating helpers with short runs that start from a record and end. One target is that it costs only a little more helper effort than today, and ideally less for the same progress. That needs a baseline: what helper effort costs today, per session, per role and per kind of activity, and how much of it is doing the work as against reading, re-reading, coordinating, waiting and recovering.

## Sources

- `DATA/wave2/m1max-snapshot.jsonl`: `kind: "session"` rows carry project, role, model, start, end, tokens where the transcript has them, compactions, errors and wakes. Schema in `DATA/corpus/README.md`.
- `DATA/scripts/extract_human_layer.py`: shows how each transcript format is parsed. Reuse its reading code.
- The transcripts themselves (`~/.claude/projects/`, `~/.codex/sessions/`), through scripts only, for tool-call level detail. Sample if a full pass is too slow: at least 400 sessions, spread by project, role and month, with the sampling stated.
- `/Users/changlee/projects/agent-annotate/shared/agents/cost-3day-20261110/`: an earlier three-day cost study. Read its method and check your numbers against it where they overlap.
- `DATA/corpus/tasks.jsonl` and `goal_candidates.jsonl`, and `DATA/goals/*.jsonl` if present, to tie sessions to goals.

Only M1 Max. Do not read the other Macs.

## Build

`DATA/scripts/effort.py` and `DATA/effort/`:

1. **Per session**: tokens in, out, cache-read and cache-write where known; a cost figure using published list prices, with the price table stated and dated (say plainly that subscriptions make the money figure notional); wall-clock time; active time (sum of turn durations); number of tool calls.
2. **Per activity**, by fixed rules on tool names and commands, each rule written down: doing the work (edits, builds, tests); reading and searching; re-reading something already read in the same session; talking to other helpers (messages, waits, checks, heartbeats); keeping boards, pages and notes; talking to the person; recovering (retries after errors, restarts, compaction summaries); idle waiting.
3. **Cold start**: for each session, the tokens and seconds spent before its first action that changes or produces anything. This is what every short run would pay.
4. **By role**: direct, coordinator, worker, subagent. For coordinators: tokens per worker managed, turns per worker result handled, and the share of their effort that is re-reading their own history (cache-read).
5. **Per goal**, where sessions can be tied to a goal: total tokens, sessions, coordinator share.

## Findings file

`docs/design/from-zero/research/e-effort.md`, under 120 lines:

- totals by project, role and month; coverage (how many sessions had token data);
- the activity split overall and by role, with the share that is "doing the work";
- cold start: median and 90th percentile tokens and seconds, by helper kind and role;
- coordinators: what one costs per day, per worker and per result, and what share is re-reading;
- per goal, where known: median and range;
- the cost of recovery (errors, restarts, compactions) as a share;
- then a plain estimate, with its assumptions stated: for a medium goal, what would N short runs cost at today's cold-start figures, against today's pattern? At what number of runs does the short-run pattern cost more?

Say what could not be measured.

## Done means

`DATA/effort/` holds per-session rows; every number names its command; the activity rules were checked by reading 60 random tool calls and the error rate is reported.
