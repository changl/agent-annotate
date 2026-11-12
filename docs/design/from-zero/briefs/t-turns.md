# T. What each of his messages was

Follow `docs/design/from-zero/briefs/common-data.md`. It overrides anything below. Your shard and output names are in your task message.

## Why

`DATA/corpus/*.jsonl` holds every message the person typed to a helper, with what he was answering and what he got back (schema in `DATA/corpus/README.md`). Each of those messages cost him attention. The design needs to know what each one was for, and whether a better way of working would have made it unnecessary. This sizes every part of the design.

## Label every `human` turn in your shard

Read each row's `text` with its `prev_assistant_tail` and `next_assistant_head`. Give it:

`label`, exactly one:

| Label | Meaning |
|---|---|
| `goal` | He states something new he wants. |
| `intent_fix` | He corrects a misunderstanding of what he wanted. The helper went the wrong way. |
| `quality_fix` | He sends work back because it is wrong or unfinished against what was already clear. |
| `taste` | A preference only he could give, on seeing something. |
| `answer_needed` | He answers a question that only he could decide. |
| `answer_not_needed` | He answers a question the helper could have settled: he took the suggestion, it could be undone, or he had already ruled on it. |
| `status_check` | He asks what is happening, whether it is done, or why it is slow. |
| `nudge` | He pushes after silence, a stall or forgotten work. |
| `rule` | He states a standing instruction about how work should be done. |
| `go_ahead` | He approves or allows something. |
| `change_of_mind` | He changes what he wants after it was understood correctly. |
| `supply` | He gives facts the helper lacked. |
| `relay` | He carries a message, a brief or a result between helpers, sessions or machines. |
| `tooling` | About the working system itself (settings, models, memory, permissions), not about any goal. |
| `other` | None of these. |

Then:

- `avoidable`: `yes`, `no` or `unclear`. Would he have needed to type this at all if the work were run well?
- `by`, when avoidable, exactly one: `agreement` (saying the goal back before starting would have caught it); `rule_book` (he had already said it, or it follows from a preference he had already shown); `record` (the fact was already written down somewhere a helper could read); `check` (a check by someone other than the maker would have caught it); `default` (the helper could have gone ahead on its suggestion); `watch` (something other than him should have noticed the silence or stall); `one_door` (he was only carrying messages between places); `glance` (a true picture he could trust would have answered it).
- `heat`: 0 calm, 1 impatient, 2 clearly frustrated.
- `goal_hint`: up to eight words naming what the message was about.
- `sure`: 1 to 3, how sure you are of the label.

Rules for labelling:

- Decide from the row, not from what you expect. If the context is too thin, use `unclear` and `sure: 1`.
- Work in batches with a script that feeds you rows and stores your labels. Do not hold the shard in your context.
- Do not write prose about individual rows.

## Output

- `DATA/labels/<shard-name>.jsonl`: one row per turn: `id` and the fields above.
- `DATA/labels/<shard-name>-summary.json`: counts by label, by `avoidable`, by `by`, words by label, heat by label.
- Re-label a random 80 rows blind (hide your first labels) and report how often the two passes agree on `label` and on `avoidable`.

No findings file for this task. The lead combines the shards.

## Done means

Every `human` turn in the shard has a row; the summary exists; the agreement rate is reported in `worker_done` with the five most common confusions between labels.
