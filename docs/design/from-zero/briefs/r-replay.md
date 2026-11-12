# R. Replay: would an agreement up front have saved the cycles?

Follow `docs/design/from-zero/briefs/common-data.md` and read `docs/design/from-zero/briefs/wave2-m1max.md`. They override anything below.

## Why

The method's central claim is that one agreement before work starts (the goal said back, what "done" means, what the helper will decide, what only he can decide, what is not being done) removes most of the cycles that follow. Nobody has tested that. The record lets us test it now: for past goals we know his first sentence and everything that happened afterwards. Write the agreement the method would have produced from the first sentence alone, without knowing what came next, and then see which of the later cycles it would have prevented.

## Inputs

- `DATA/goals/*.jsonl`: goals rebuilt from the record, one row each, with `first_statement`, `first_at`, every cycle with its cause, `par`, and what the first statement lacked. Use whichever files exist when you start and say which.
- `DATA/corpus/rules.jsonl` and `DATA/d3/seed.jsonl`: his standing instructions, some with dates.
- The method's agreement format: section 5 of `docs/design/from-zero-20261112.md`. What the outside evidence says an agreement must also carry: `docs/design/from-zero/research/d5-outside.md` (P3, P6) and `d7-other-fields.md` (rules 1, 2 and 6).

## Step 1. Choose the goals

Up to 36 goals: up to six from each goals file, spread across small, medium and large, and across goals that went well and badly. Each must have a clear first statement in his own words. List what you chose and what you rejected.

## Step 2. Write the agreements blind

The writer must not know what happened after the first statement. Enforce that mechanically: for each goal a script builds a **packet** file containing only what the brief below allows, and a fresh helper run with no other context reads the packet and writes the agreement. Start each writer as its own short run in an empty folder under `/tmp`, with a prompt that tells it to read only the packet (for example `codex exec` with the packet path; check its `--help`). Record the wall-clock time of each run. The writer may not read `DATA`, the transcripts or the repositories.

Three ways of writing, for every goal:

- **A. His sentence alone.** The packet holds his first statement and the date.
- **B. With the rule book.** The packet adds the 30 seed rules and any dated rules of his from before that date that the script judges relevant by keyword (state the rule for choosing them).
- **C. With the rule book and a look at the project.** The packet also adds a short factual description of the project as it stood before that date, built by a script from records dated earlier than the first statement only: what the project is, what existed, the last few things finished. Nothing from after the date. If no such description can be built for a goal, skip C for it and say so.

Each agreement, in the method's format, at most 180 words: what I heard; done means (checkable lines); I'll decide; only you can decide (each with a recommendation, and whether it can be undone); not doing; when you will next see something; and the par.

## Step 3. Hand over for judging

Do not judge your own agreements. Write, for the judges:

- `DATA/replay/agreements.jsonl`: one row per goal and way: the packet path, the agreement text, word count, seconds the run took.
- `DATA/replay/actual.jsonl`: one row per goal: the first statement, the full path of cycles with causes, and what was finally accepted.
- `DATA/replay/README.md`: how the packets were built, with one full example of each way, and how blindness was enforced.

## Findings file

`docs/design/from-zero/research/r-replay-writing.md`, under 80 lines: goals chosen and rejected; how many agreements were written for each way; word counts; seconds per run (this is a live measure of what a short run costs); how often the writer asked a question that his later messages show he did care about; how often it stated an assumption that his later messages contradict; and what the writer could not have known under each way. No judgement of cycles saved: that is the judges' job.

## Done means

The three files exist, every chosen goal has A and B and (where possible) C, blindness is enforced by the packet-and-fresh-run mechanism and described, and every number names its command.
