# P. How work stalls, and who notices

Follow `docs/design/from-zero/briefs/common-data.md`. It overrides anything below.

## Why

The method promises the person that silence means all is well. That promise fails the first time work stops and he is the one who finds out. The design needs a census of every way work has stopped, gone wrong quietly, or been reported finished when it was not: how often, for how long, and who noticed.

## Sources

- `DATA/corpus/*.jsonl`: session rows (API errors, compactions, long gaps, how each ended) and his `human` turns (schema in `DATA/corpus/README.md`).
- `DATA/labels/*.jsonl` if present: turns labelled `nudge`, `status_check`, `quality_fix`.
- `DATA/corpus/tasks.jsonl` and `handoffs.jsonl` if present.
- Transcripts, through scripts, to confirm what happened around each candidate.
- Memory notes in `~/.claude/projects/*/memory/` that record past failures of the working system.

## Count these, each with: how many, how long each lasted, who noticed (him, another helper, a script, nobody), and what it cost (his turns, lost hours, redone work)

1. **Silent stop.** A helper stopped mid-task and said nothing (an error, a limit, a crash, a prompt waiting for a key).
2. **Waiting on nobody.** A helper was waiting for a message, a worker or an event that was never coming.
3. **Waiting on him without telling him.** Work blocked on a question or approval he did not know about.
4. **Lost message.** Something sent between helpers that did not arrive, arrived late, or was read by the wrong one.
5. **False finish.** A helper said "done" and it was not: tests not run, wrong thing built, part missing, not actually released.
6. **Lost memory.** After a restart, a compaction or a hand-over, a helper forgot an instruction, repeated work, or contradicted an earlier decision.
7. **Drift.** A helper kept working but on something other than what was asked.
8. **Collision.** Two helpers changed the same thing, or undid each other's work.
9. **Machine trouble.** A computer asleep, a disk or share unreachable, a service down.
10. **Anything else that recurs.** Name it.

Start from scripts that find candidates (long gaps inside a running turn; errors in the last lines of a session; his next message being a nudge or a status check; "done" followed within a day by a fix request on the same thing). Read each candidate's context before counting it. Report how many candidates you rejected.

## Output

- `DATA/stalls/events.jsonl`: one row per confirmed event: kind, project, mac, start, how long, who noticed, what it cost, the evidence (session and row ids).
- `docs/design/from-zero/research/p-stalls.md`, under 120 lines:
  - the census table: kind, count, median and longest duration, share noticed by him;
  - for each kind: what signal was available at the time that a script could have read, and how soon;
  - which kinds a plain clock would catch, which need a second helper to judge, and which nothing would have caught;
  - how many of his messages and how many hours the whole census accounts for;
  - the five worst single events, in four lines each.

## Done means

Every kind has a count or a stated reason it could not be counted; every counted event has evidence ids; the share noticed by him is reported for each kind.
