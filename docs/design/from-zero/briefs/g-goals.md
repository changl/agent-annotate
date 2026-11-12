# G. Cycles per goal today

Follow `docs/design/from-zero/briefs/common-data.md`. It overrides anything below. Your project and output names are in your task message.

## Why

The headline number of the new method is **cycles to done**. A cycle is one time the work comes back to the person and he sends it on: a typed message to a helper, or a round of answers sent from a review page. Cycles are counted for one goal, from the moment he first states it to the moment he accepts the result. Each cycle has exactly one cause. Nobody has ever counted this. You are counting it for one project, so the new method has a baseline to beat.

## Sources

- `DATA/corpus/*.jsonl`: his typed messages with context, and the session rows (schema in `DATA/corpus/README.md`).
- `DATA/corpus/questions.jsonl` and `rounds.jsonl`: questions put to him on review pages and the rounds of answers he sent.
- `DATA/corpus/items.jsonl`, `tasks.jsonl`, `goal_candidates.jsonl`: board items, worker tasks and candidate goals.
- The transcripts themselves, through scripts, when a row's context is not enough.

Use whichever of these exist when you start. Say which were missing.

## Do

1. **Pick the goals.** From your project, choose up to 15 goals that the person would recognise as one thing he asked for, spread across small (hours), medium (days) and large (weeks). Prefer goals with a clear first statement and a clear end. Include at least three that went badly. List the ones you rejected and why.
2. **Rebuild each goal's path.** In time order: his first statement; every later moment the goal reached him; what he did each time; when he accepted, or that it was never accepted.
3. **Give each cycle one cause:**
   - `his_decision`: only he could decide it (taste, money, risk, direction).
   - `sent_back_intent`: the work did not match what he meant.
   - `sent_back_quality`: the work was wrong or unfinished against what was clear.
   - `not_needed`: he was asked something a helper could have settled.
   - `his_change`: he changed what he wanted.
   - `status_or_nudge`: he had to ask, or push after silence.
   - `relay`: he carried something between helpers.
   - `tooling`: the working system itself needed him.
4. **Measure the first statement.** How much of what was finally accepted was already in his first statement? What was missing: things he knew and did not say, things nobody knew yet, or things already written down that the helper did not use?
5. **Set a par for each goal** by the method's rule: 2, plus 1 for each decision of taste that needed something to look at first. Record par next to the actual count.

## Output

- `DATA/goals/<project>.jsonl`: one row per goal: `title` in plain words, `size`, `first_statement` (his words), `first_at`, `accepted_at` or null, `cycles` (a list: time, what reached him, what he did, cause, words he typed, minutes he likely spent), `par`, `calendar_days`, `helper_sessions` involved, `tokens` if known, and `first_statement_coverage` with what was missing.
- `docs/design/from-zero/research/g-<project>.md`, under 100 lines: goals counted; median and range of cycles; cycles by cause; actual against par; his words and minutes per goal; what the first statement lacked; the three goals that went worst, told in five lines each; and what could not be rebuilt.

## Done means

At least 10 goals rebuilt (or a clear account of why fewer were possible), every cycle has one cause, and a second pass over three goals chosen at random gives the same cycle count within one.
