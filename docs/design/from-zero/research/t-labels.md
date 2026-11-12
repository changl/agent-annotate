# T. What each of his typed messages was

**1,279 messages he typed to helpers on M1 Max (87,672 words), each labelled by two workers separately. About a third were avoidable, and the largest single cause was work reaching him unchecked.**

Source: the frozen M1 Max corpus (1,377 rows marked as typed by him; the labellers judged 98 of those to be machine-written and they are excluded). Two GPT 6.1 Sol workers labelled every row without seeing each other's work. Chat only: answers given on review pages are in `d2-questions.md`. The sections down to "What this changes in the design" cover M1 Max; M5 Max was added afterwards and has its own section near the end, with the two computers added together.

Reproduce: `python3 -I DATA/scripts/compare_labels.py DATA/wave2/m1max-snapshot.jsonl DATA/labels/m1max-a.jsonl DATA/labels/m1max-b.jsonl`, where `DATA` is `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/`. Every number below comes from that one command.

## How far the labels can be trusted

| | Two labellers agree | Kappa |
|---|---:|---:|
| What kind of message it was (15 kinds) | 77.1% | 0.74 |
| Whether it was avoidable | 92.0% | 0.84 |
| Which part of the method would have avoided it (when both said avoidable) | 81.3% | |

The one large disagreement is between "a new goal" and "about the working system itself" (109 messages): a request to fix or set up the helpers' own tooling is both. So the share of his messages about the working system is between 9% (118) and 20% (254), depending on the reading.

## What he typed

Counts where both labellers gave the same kind (986 of 1,279):

| Kind | Messages | Words |
|---|---:|---:|
| Sent work back: wrong or unfinished against what was already clear | 201 | 13,849 |
| Stated a new goal | 188 | 26,661 |
| About the working system itself | 115 | 2,895 |
| Answered a question only he could decide | 94 | 4,848 |
| Supplied a fact the helper lacked | 80 | 1,364 |
| Corrected a misunderstanding of what he meant | 64 | 6,707 |
| Said go ahead | 63 | 1,605 |
| Asked what was happening | 52 | 1,232 |
| Pushed after silence or a stall | 46 | 873 |
| Stated a standing rule | 33 | 2,173 |
| Gave a preference on seeing something | 18 | 1,472 |
| Carried a message between helpers | 9 | 377 |
| Answered a question the helper could have settled | 8 | 82 |
| Changed his mind | 8 | 275 |

He sent work back for quality (201) more often than he asked for something new (188). Corrections of intent (64) are a third as common as corrections of quality.

## What was avoidable

| | Messages | Share | Words | Share |
|---|---:|---:|---:|---:|
| Both labellers: avoidable | 448 | 35.0% | 25,944 | 29.6% |
| Either labeller: avoidable | 545 | 42.6% | 30,831 | 35.2% |
| Both labellers: not avoidable | 708 | 55.4% | 54,344 | 62.0% |

So between 35% and 43% of what he typed in chat would not have been needed had the work been run well, and more than half was his to say: new goals, real decisions, facts only he had.

## Which part of the method would have avoided it

Of the 448 messages both labellers called avoidable, the part each named (labeller A, labeller B, and where both named the same part):

| Part of the method | A | B | Both | Words (both) |
|---|---:|---:|---:|---:|
| A check by something other than the maker, before he sees it | 158 | 145 | 137 | 8,378 |
| The agreement before work starts | 64 | 72 | 59 | 6,088 |
| The watch: something else notices silence or a stall | 63 | 51 | 44 | 1,084 |
| The glance: a true picture he can trust | 57 | 51 | 45 | 1,025 |
| The rule book: he had already said it | 39 | 50 | 29 | 2,902 |
| A default: the helper could have gone ahead | 25 | 38 | 25 | 389 |
| The record: the fact was already written down | 31 | 31 | 16 | 1,263 |
| One doorway: he was only carrying messages | 11 | 10 | 9 | 377 |

## What this changes in the design

1. **The check is the biggest lever, not the agreement.** About a third of avoidable messages, and the most words, come from work that reached him wrong or unfinished. The method called the agreement "the most valuable minute"; in chat, independent checking before showing is worth more than twice as much. Both stay; the order of building changes.
2. **Sight is a fifth of the avoidable load.** Status questions and nudges together (watch plus glance) are about 90 to 120 messages. They are short, but each is an interruption he started because silence was not believable.
3. **The agreement still matters most per message.** Messages it would have avoided are long (about 100 words each): they are him re-explaining what he meant.
4. **Rules and defaults are smaller here than expected**, about 55 to 90 messages together. On review pages the picture differs: a quarter of answers there did not need him (`d2-questions.md`).
5. **More than half is properly his.** New goals carry the most words of all (26,661). The design must make saying a goal cheap and must not treat those words as waste.

## M5 Max, added later the same day

The M5 Max corpus arrived after the sections above were written. Sessions that also exist on M1 Max were dropped, so nothing is counted twice. Two further labellers, working apart, labelled its 1,748 rows; 470 were judged machine-written by one or both and are excluded, leaving **1,278 messages (86,874 words)**. Reproduce with the same script on `DATA/wave2/m5max-new-snapshot.jsonl`, `DATA/labels/m5max-a.jsonl` and `m5max-b.jsonl`.

Agreement between the two labellers: kind 88.2% (kappa 0.86); avoidable 94.1% (kappa 0.88); which part of the method 93.1%.

One caution governs every M5 Max figure. **314 of the rows are one-word prompts to carry on after a rate limit stopped a helper.** Whether he typed each one cannot be proved from the record. If he did, they are the purest case of him being the watch. Figures are given both ways.

| | M1 Max | M5 Max | Both | Both, without the 314 |
|---|---:|---:|---:|---:|
| Messages | 1,279 | 1,278 | 2,557 | 2,243 |
| Avoidable, both labellers | 448 (35%) | 656 (51%) | 1,104 (43%) | 790 (35%) |

Which part of the method would have avoided them, where both labellers named the same part:

| Part | M1 Max | M5 Max | Both |
|---|---:|---:|---:|
| A check before he sees it | 137 | 153 | 290 |
| The watch | 44 | 353 (39 without the 314) | 397 (83) |
| The agreement | 59 | 39 | 98 |
| The glance | 45 | 23 | 68 |
| The rule book | 29 | 25 | 54 |
| A default | 25 | 15 | 40 |
| The record | 16 | 0 | 16 |
| One doorway | 9 | 3 | 12 |

The M5 Max data repeats the M1 Max finding. The check is about three times the agreement on both computers, and on M5 Max it carries far more words (15,846 against 4,982). On M5 Max he sent work back for quality 185 times and stated a new goal 144 times. In the vehicle project, 395 of 510 messages were judged avoidable, most of them the prompts to carry on.

## Limits

- Judgement, not fact: "avoidable" is two workers' reading of each message with the helper's text before and after it.
- The M5 Max extraction is less clean than M1 Max: more than a quarter of the rows marked as his were machine-written, and its origin rules had not finished being checked when the snapshot was taken.
- Heat was marked too: about 5% of messages read as clearly frustrated (61 and 54 by the two labellers), and a further 5% to 9% as impatient.
