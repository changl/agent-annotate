# TA. Label every message he typed (labeller A)

Read `docs/design/from-zero/briefs/wave2-m1max.md`, then follow `docs/design/from-zero/briefs/t-turns.md` exactly.

- Your shard: every row with `kind: "turn"` and `origin: "human"` in `DATA/wave2/m1max-snapshot.jsonl` (1,377 rows).
- Your shard name: `m1max-a`. Outputs: `DATA/labels/m1max-a.jsonl` and `DATA/labels/m1max-a-summary.json`.
- A second labeller is labelling the same rows separately, so that the two can be compared. Do not open any file in `DATA/labels/` that is not yours.
- Add one field to every row: `not_human: true` if the text is plainly machine-written (a forwarded brief, a hook, a pasted notice with no words of his own).
- In your summary, also give the counts by project and by month.
