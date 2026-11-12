# Rules for every data worker

You are a research worker on a design programme. The programme designs a method for one person to get work done through many helpers with the least attention. Read sections 1 to 4 of `docs/design/from-zero-20261112.md` first (two minutes). Do not read `docs/design/first-attempt-20261112/`.

## Where things go

- `DATA` = `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/`. Raw rows, scripts and working files go here, under the paths your brief names. This folder is not in git.
- Findings go in the one file your brief names under `docs/design/from-zero/research/`. Keep it under 120 lines. Lead with the numbers. Plain words.

## Hard limits

- Read-only everywhere except those two places.
- No git commit, push, branch, stash or checkout. The lead commits.
- No installs, releases or rollouts. No changes to skills, AGENTS.md, CLAUDE.md, settings, hooks, Windmill, schedules, pages, beads, or any other Mac.
- Do not message any other session. Do not use the annotate skill. Create no beads.
- Other projects: read their transcripts and records only. Change nothing.
- Never read a whole transcript into your context. Write a script, run it, read its summary. Sample rows to check it.
- This Mac is busy. Run one heavy process at a time, with `nice -n 19`. Stop every process you start.
- Secrets: if a transcript row holds a key, token or password, drop that row's text and keep only its metadata.

## Privacy

- Raw text stays in `DATA`.
- In the findings file: numbers, short paraphrase and row ids only. No customer names. No verbatim text from projects other than agent-annotate, except short quotes of the person's own instructions about how he wants work done.

## Quality

- Every number must be reproducible: name the script and the command that produced it.
- Say what could not be measured and why. Never fill a gap with a guess.
- Check your extraction by reading at least 50 random rows, and report the error rate you saw.

## Finishing

Send `worker_done` once, with at most 15 lines: files written, the main counts, the three findings that matter most for the design, and what could not be measured.
