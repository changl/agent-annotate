# Wave 2b on the M5 Max snapshot: what every worker in this wave needs to know

- The corpus for this wave is the frozen file `DATA/wave2/m5max-new-snapshot.jsonl` (`DATA` = `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/`). It holds the M5 Max sessions that are not already in the M1 Max snapshot (sessions synced between the two Macs were dropped, so nothing is counted twice). Schema: `DATA/corpus/README.md`.
- It holds 1,748 turns with `origin: "human"`: messages the person typed. The largest project is the one named `FastLane Drive` (about 750 of them). A few rows may be mislabelled; if a `human` row is plainly machine-written, mark it and move on.
- The M1 Max work is finished and is your reference: `docs/design/from-zero/research/t-labels.md`, `g-b.md`, `b-baseline.md`, `p-stalls.md`, and their data in `DATA/labels/`, `DATA/goals/`, `DATA/baseline/`, `DATA/stalls/`. Use the same rules and the same field names, so the two Macs can be added together.
- Other wave 1 files, all in `DATA/corpus/`: `questions.jsonl`, `rounds.jsonl`, `pages.jsonl` (review pages, both Macs); `items.jsonl`, `tasks.jsonl`, `handoffs.jsonl`, `goal_candidates.jsonl`; `rules.jsonl`.
- Project names: in files under `docs/design/`, never name a project other than agent-annotate. Use "Project B" for `FastLane Drive`, "Project C" for `rebex`, "Project D" for `connelly`, "Project E" for `leadory`, and "another project" for the rest. Keep real names in `DATA` only.
- Do not read the other Macs. Everything you need is in the snapshot.
- Follow `docs/design/from-zero/briefs/common-data.md` throughout.
