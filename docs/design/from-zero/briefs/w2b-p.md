# P2. How work stalls, and who notices (M5 Max)

Read `docs/design/from-zero/briefs/w2b-m5.md`, then follow `docs/design/from-zero/briefs/p-stalls.md` exactly.

- Where that brief says `DATA/corpus/*.jsonl` for sessions and his turns, use `DATA/wave2/m5max-new-snapshot.jsonl`.
- The M1 Max census is finished: `docs/design/from-zero/research/p-stalls.md`, with its scripts (`DATA/scripts/p_stalls_*.py`) and events (`DATA/stalls/`). Reuse its scripts and its kinds, so the two Macs can be added together. Add a kind only if something recurs that the first census did not have.
- Outputs: `DATA/stalls/m5/events.jsonl` and `docs/design/from-zero/research/p-stalls-m5.md` (under 100 lines). End the findings with one table that adds the two Macs: kind, cases on each, total, and the share first noticed by him.
