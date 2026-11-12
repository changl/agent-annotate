# Wave 2 on the M1 Max snapshot: what every worker in this wave needs to know

- The corpus for this wave is the frozen file `DATA/wave2/m1max-snapshot.jsonl` (`DATA` = `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/`). Read that file, not `DATA/corpus/m1max.jsonl`, which is still being refined. Row ids are the same in both. Schema: `DATA/corpus/README.md`.
- It holds 62,623 turn rows, 11,533 session rows and 231 structured questions from M1 Max. 1,377 turns have `origin: "human"` (about 108,000 words): those are the messages the person typed. A few rows may still be mislabelled; if a `human` row is plainly machine-written, mark it and move on.
- Other files produced by wave 1, all in `DATA/corpus/`: `questions.jsonl`, `rounds.jsonl`, `pages.jsonl` (questions put to him on review pages, both Macs); `items.jsonl`, `tasks.jsonl`, `handoffs.jsonl`, `goal_candidates.jsonl` (boards, worker tasks, hand-overs); `rules.jsonl` (his standing instructions).
- Findings already written, worth ten minutes: `docs/design/from-zero/research/d2-questions.md`, `d4-goals.md`, `s-kinds-of-work.md`.
- A second corpus from M5 Max may appear later at `DATA/corpus/m5max.jsonl`. Do not wait for it. If it is there when you start, say so in your report and use it only if your brief's sources call for it.
- Project names: in files under `docs/design/`, never name a project other than agent-annotate. Use the letter your task message gives. Keep real names in `DATA` only.
- Do not read the other Macs. One worker is already doing that.
