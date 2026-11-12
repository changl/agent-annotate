# RJ1. Judge the replay (judge "sol")

Follow `docs/design/from-zero/briefs/rj-replay-judge.md` exactly, and the limits in `docs/design/from-zero/briefs/common-data.md`.

- Your name: `sol`. Outputs: `DATA/replay/judge-sol.jsonl` and `docs/design/from-zero/research/r-replay-judge-sol.md`.
- The writer's own findings are in `docs/design/from-zero/research/r-replay-writing.md`. Read it for how the packets were built and for the leakage risk it names (seed rules written with hindsight). Where that risk could have helped an agreement of way B or C, say so and judge way A as the clean test.
- 36 goals, 95 agreements. Judge all of them. Work in batches from the files with a script; do not hold them all in your context.
- Where the brief says "finish with", put that text in your `worker_done` message. Send `worker_done` once.
