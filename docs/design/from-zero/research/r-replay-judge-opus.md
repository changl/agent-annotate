# R — Replay judge (opus): what each blind agreement would have changed

**The agreement on its own removes almost nothing. Way A, the clean test, prevents 0 of 416 returns and moves 3 up. It also adds its own sitting, so cycles rise from 416 to 453. Nearly all of the possible saving comes from the other parts of the method (watch, checks, record, defaults, one doorway, rule book), and only if they work as designed.**

Rows: `DATA/replay/judge-opus.jsonl` holds 1,177 cycle rows (goal × way × cycle) and 95 agreement rows. `DATA` = `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/`.
Numbers: `python3 -I /tmp/rj-opus/build.py` rebuilds the rows from my per-goal verdict files in `/tmp/rj-opus/j/` (scratch). The table is a plain sum of the agreement rows in the jsonl.

| | A (sentence) | B (+ rule book) | C (+ project state) | A, B, C on C's 23 goals |
|---|---:|---:|---:|---|
| Goals judged | 36 | 36 | 23 | 23 |
| Actual cycles | 416 | 416 | 345 | 345 |
| Par (sum) | 87 | 87 | 54 | 54 |
| Predicted, agreement alone | 453 | 447 | 365 | A 366 · B 363 · C 365 |
| Predicted, whole method | 227 | 222 | 163 | A 164 · B 162 · C 163 |
| Prevented | 0 | 2 | 4 | A 0 · B 1 · C 4 |
| Moved up | 3 | 5 | 1 | A 3 · B 5 · C 1 |
| Unchanged | 190 | 186 | 140 | |
| Not about intent | 223 | 223 | 200 | |
| Wrong assumptions | 15 | 5 | 10 | A 10 · B 5 · C 10 |
| Needless questions | 13 | 9 | 6 | A 6 · B 5 · C 6 |
| He would say go: yes / after one fix / no | 24 / 8 / 4 (67%) | 31 / 5 / 0 (86%) | 17 / 6 / 0 (74%) | |

How each figure is defined:

- **Agreement alone** = 1 (the agreement sitting) + every cycle not prevented or moved up + any extra cycle the agreement itself causes (a rewrite, an outline showing nobody needed, or a wrong line that would be built).
- **Whole method** = the same, minus each cycle a named other part would remove. I counted a removal only when the defect could be checked objectively: a stall, a relay, a repeated ask, a false "done", or a case where he said himself that it did not need him. Taste and genuinely new requests stay.
- **"After one fix"** = one or two lines changed while reading. **"No"** = he would have had to rewrite it, or it parks all work on a question the context already answered.

## Where the cycles went (way A)

- **Intent-type returns: 191** (117 decisions, 59 sent back for intent, 15 changes of mind). The agreement touched 3. Of the decisions, 106 only existed once there was work to look at: approvals, picks among options found on the way, taste rounds. The 59 send-backs were mostly new requirements found on seeing the work, design disagreements, urgency, and standing preferences.
- **Not about intent: 223.** 203 have a part that would remove them; 20 have none (logging in for him, tool quirks, pace). Another 23 cycles the agreement leaves unchanged can still be removed by defaults or the record. Removals by part, 226 in all: watch 67, checks 51, record 33, defaults 29, one doorway 29, rule book 17.
- **Drift: 8 cycles.** The helper lost something already in his first sentence and in every agreement's done lines (B10 c10, D04 c9, D07 c13, D07 c20, E06 c19, E11 c4, E11 c21, F2-1 c1). I scored them as checks or record, not as prevented: the helper already had his words, so a restatement would not have stopped the drift; only checking the done line does. This is the agreement's real contribution: it supplies the checklist.
- **First statement as a cycle: 16 goals.** Cycle 0 is the first statement itself, so no agreement can remove it. Nine are answers to a helper's card, and the writer never saw the card's question.

## What an agreement catches, and what it never does

**Catches** (the 10 distinct cycles credited across the three ways):

- An open number or set the writer turned into a question: leads per universe (D07, A and B); which universes share the schema (D04, A and B); scope against deadline (C08, B); which plans are in scope (a13, B); which source governs (E11, B and C).
- A stated assumption he would have corrected while reading: questions go on the tickets, not in chat (E07, A).
- An assumption or boundary that happened to match his later choice: one shared login plus session labels (B05, C); measure first (B02, C); the helper picks the fix (a04, B and C); keep working features (a13, B and C).

**Never catches:** decisions that arise inside the work; taste, which needs something to look at; new requirements he finds on seeing the work (four fixed zoom steps in a12, deleting an unsent comment in a08, the full release content in a14); design direction (D04); urgency (C10 went from staged restore proofs to "launch is today"); standing process preferences (scripts over agents, store badges, plain totals, commit identity), which belong to the rule book; stalls, relays and false "done" claims.

**Hurts:**

- **Exclusions he did not say.** All 30 wrong assumptions are the writer's own additions; I did not count restatements of his own words. Most are added exclusions: "diagnosis only" when he wanted a fix (D11); "no execution" (E06 C, E14); "no release" (a13 C, F1-2 C); "no reduced coverage" when he wanted smoke runs (B02 C); "not doing backups or broad rewrites".
- **Machinery he rejected:** restoration evidence for every stage (C10), and inventories before a one-click move (D09).
- **Parking work on referents.** A parks the work to ask what "me" or "the item" means when the sentence answered a card (B04, B06, C01).

## Are B and C worth their cost over A?

**B, yes, as a guard against bad agreements, not as a saver of cycles.** Wrong assumptions drop from 15 to 5, needless questions from 13 to 9, and "no" from 4 to 0. B prevents or moves up 7 cycles to A's 3. Two of those 7 are at risk of hindsight: a04 and a13 B/C cite seeds d3s-26/d3s-07 ("proceed on a safe path, ask only for reserved decisions") and d3s-09 ("don't remove working features"). Those seeds are undated and may have been learned from these very goals (both Oct 2026). The same seeds may also explain why B adds fewer "diagnosis only" limits. Without them, B's clean gain is 5 cycles against 3.

**C, no.** On the same 23 goals, C predicts 365 cycles against B's 363 and has twice B's wrong assumptions (10 against 5). The project description adds more NOT DOING lines (repairs, release, execution), several of them wrong. 13 of 36 goals had no usable earlier project state, so C could not be written.

## Five goals where the agreement helped most

- **D07** (55 cycles, A): asks count and split per lead universe and recommends separate targets, which moves up the c2 send-back "100–300 for each of the 3". Saves 1. The other parts would remove 41 of the 55: watch 12, checks 9, record 8, doorway 7, rule book 4, defaults 1.
- **D04** (54 cycles, A/B): asks the "adjacent scope", so his later "one target schema for every universe" (c40) is settled at the start. Saves 1; the other 53 are design rounds and failures to keep his work.
- **E07** (6 cycles, A): states "questions come back here" as an assumption. He cared and would have changed it to ticket comments while reading. Moves up 1 of 6, the only clean case of a surfaced assumption working.
- **a13** (5 cycles, B): "working features stay intact" keeps the dropdown he defended, and B asks which plans are in scope. Removes 2 of 5, but the first credit is at risk of hindsight (seed d3s-09).
- **E11** (28 cycles, B/C): raises the exact question the helper asked first, new pack or current records. Moves up 1 of 28; the rest is relayed review lists, stalls and new requirements.

## Five goals where it hurt or did nothing

- **D09** (1 cycle): "move this session to another group". Every agreement adds a check or a showing; B and C want an inventory of processes first. He did it himself with one right-click. 1 cycle becomes 3.
- **B04 / B06 / C01** (answers to cards): A asks who "me" is, or which email or candidates, and parks all work. He would rewrite it. Each gains 1 cycle; B recommends the obvious answer and does no harm.
- **C10** (19 cycles): every way asks him to confirm an obvious typo and builds restoration proof into "done". He later called the plan over-engineered, and launch was "today". No agreement asked for a date. Saves 0.
- **D11** (11 cycles): A keeps the hooks enabled; B and C diagnose only. He wanted the hooks fixed and two tools removed. Saves 0; each way has 1–2 wrong lines.
- **E14** (33 cycles): every way excludes running the comparison he asked for "this cycle"; A asks for model names he had already given. Saves 0; 21 of the 33 are status and session cycles only the watch could remove.

## What the format should add or drop

**Add:**

- **"Fix or only look?"** Default to fixing anything that can be undone, unless he says "plan only". That line would have avoided at least 8 of the 30 wrong assumptions.
- **"When do you need it?"** whenever the sentence gives no time. It mattered in C10, B02 and C08 and was never asked.
- **Questions only for open numbers and sets** (how many, which ones, what gives first), each with a suggestion to answer now. These are the only questions that moved anything up.
- **The helper's question as input** whenever his sentence replies to a card.

**Drop:**

- **The fixed paragraphs** ("silence grants no authority", "park and escalate", "reopen if facts change"). They take a median 13% of each agreement's words (sentences with those phrases, regex over all 95) and steered nothing.
- **ONLY YOU items deferred to "the showing" or "the checkpoint".** They move nothing up; they are the showing.
- **Questions about referents the counterpart can look up.** B's conditional form ("ask only if the evidence cannot tell") did no harm; A's direct form parked work 4 times.
- **NOT DOING lines beyond his words.**
- **The agreement itself for one-step asks and card answers.** At par two it costs a whole cycle there and buys nothing.

**Keep:** the done lines. They are what the checks check; the 8 drift cycles show the line was right and nobody tested it.

## Limits

- One reader judged; the second judge's work was not seen. "Would he go" is inferred from how he reacted later, not observed.
- Whole-method removals assume the watch, checks and record work, which is untested here, so 227 is a floor on cycles, not a forecast.
- No minutes could be measured: the source has no reading or typing time. 23 of 36 paths are open or censored; missing transcripts from the other Mac may hide returns.
- In 4 goals an early return was a plan approval (C10 c0, D07 c3, E06 c1, F4-1 c2). If an agreement merged with it, way A's added cycles would fall from 36 to 32. The conclusion does not change.
- Self-check: 50 random way-A rows (seed 20261112) re-read against the cycle text: 0/50 had a wrong index or a reason not matching the cycle. One verdict in the sample is borderline (E06 c1).
