# TB2. Label every message he typed on M5 Max (labeller B)

Read `docs/design/from-zero/briefs/w2b-m5.md`, then follow `docs/design/from-zero/briefs/t-turns.md` exactly.

- Your shard: every row with `kind: "turn"` and `origin: "human"` in `DATA/wave2/m5max-new-snapshot.jsonl` (1,748 rows).
- Your shard name: `m5max-b`. Outputs: `DATA/labels/m5max-b.jsonl` and `DATA/labels/m5max-b-summary.json`.
- A second labeller is labelling the same rows separately. Do not open any file in `DATA/labels/` that is not yours.
- Add one field to every row: `not_human: true` if the text is plainly machine-written.
- In your summary, also give the counts by project and by month.
