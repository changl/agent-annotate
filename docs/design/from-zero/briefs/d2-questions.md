# D2. Every question put to the person on a review page, and what became of it

Follow `docs/design/from-zero/briefs/common-data.md`. It overrides anything below.

## Why

Today helpers put questions and results to the person on review pages kept by a tool called agent-annotate. Those pages are the best record of what was asked of him, what he chose, what he typed, and how long things waited. The design needs that record as rows. You are reading the old tool's data only as evidence of how the person behaves. Nothing about the old tool is to be kept or improved.

## Sources

- The page data of every project on this Mac. The tool's code in `src/agent_annotate/` tells you where pages are registered and how `comments.json`, submitted rounds and resolutions are stored. Start with `paths.py`, `workspace.py`, `submitted.py`, `categories.py`.
- Known state folder for this project: `/Users/changlee/projects/agent-annotate/reviews/`. Other projects keep their own. Find them through the tool's registry, not by guessing.
- The M5 Max has pages too. Read them over `ssh m5max` with a script that prints rows to standard output and writes nothing there. If SSH fails, say why and skip.

## Build

`DATA/scripts/extract_questions.py` and these files:

1. `DATA/corpus/questions.jsonl`, one row per thing that asked something of him (a decision card, a question, a request to look or approve): `id`, `project`, `page`, `asked_at`, `kind` (decide, look, approve, do-something, other), the question text, the options, which option was recommended, `answered_at`, the answer, whether it was the recommended one, any words he typed and their count, `wait_seconds`, `state_now` (answered, waiting, withdrawn, set aside), and how many times the item was re-asked or reworded.
2. `DATA/corpus/rounds.jsonl`, one row per time he sent answers back: `project`, `page`, `sent_at`, number of answers in it, words typed in it, and the time since the previous round on that page.
3. `DATA/corpus/pages.jsonl`, one row per page: `project`, `created`, number of versions published, number of questions ever asked, waiting now, oldest waiting age in days.

## Then classify (this part needs judgement; do it in batches from the rows, not from memory)

For every answered question, add:

- `needed_him`: yes, no or unclear. "No" when he took the recommendation with no typed words and the choice could have been undone later.
- `rule_could_answer`: yes if an earlier answer or a standing instruction of his already covered it. Name the earlier row or the rule.
- `typed_reason`: when he typed words, why: the options missed what he wanted; he was correcting a misunderstanding; he was adding a new requirement; he was setting a standing rule; he was asking a question back; other.

Have a second pass re-label a random 60 rows blind and report how often the two passes agree.

## Findings file

`docs/design/from-zero/research/d2-questions.md`:

- questions asked, answered, waiting, withdrawn, per project and overall;
- share answered with the recommendation; share with typed words; words typed in total;
- share that did not need him; share a rule could have answered;
- the split of `typed_reason`;
- wait time: median, 90th percentile, longest; and the count waiting now by age;
- rounds: how many, answers per round, time between rounds;
- how often one question was asked more than once;
- the ten kinds of question that recur most, in plain words (these become the first rules).

## Done means

The three files exist, the labels are in `questions.jsonl`, the agreement rate of the blind re-label is reported, and every number in the findings file names its command.
