# RJ. Judge the replay: which cycles would each agreement have saved?

Read `docs/design/from-zero/briefs/wave2-m1max.md` and sections 3 to 5 of `docs/design/from-zero-20261112.md`. A second judge is doing the same job separately. Do not look for their work.

## Inputs

- `DATA/replay/README.md`, `DATA/replay/agreements.jsonl`, `DATA/replay/actual.jsonl` (`DATA` = `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/`).
- For each past goal there is his first statement, the full path of what actually happened (every time it came back to him, with a cause), and up to three agreements written blind from the first statement: A from his sentence alone, B with his rule book, C with the rule book and a description of the project at the time.

## Judge every goal and every agreement

For each actual cycle on the goal's path, decide what would have happened to it had this agreement been put to him before work started:

- `prevented`: the agreement already says, correctly, what he later had to say. The cycle would not have happened.
- `moved_up`: the agreement raises it as a question for him up front. He still decides, but before the work, in the same sitting as the agreement. Not an extra cycle.
- `unchanged`: nothing in the agreement touches it. It would still have happened.
- `not_about_intent`: the cycle was about quality, a stall, tooling or carrying messages. An agreement cannot prevent it; other parts of the method might. Say which part: checks, watch, record, one doorway, rule book, defaults.

Then, for the agreement as a whole:

- `wrong_assumptions`: things it states as settled that his later messages contradict. Each would have cost a cycle, or worse, been built. Count them.
- `needless_questions`: things it asks him that the record shows he did not care about or had already settled.
- `would_he_go`: yes, yes after fixing one line, or no (he would have had to rewrite it). Judge from how he actually reacted later.
- `predicted_cycles`: the cycles this goal would have taken with this agreement and nothing else changed; and again with the rest of the method working (checks, watch, defaults, rule book).

Be sceptical. An agreement that is vague enough to be compatible with everything prevents nothing: count a cycle as `prevented` only when the agreement's words would actually have steered the work. Do not give credit for hindsight you bring yourself.

## Output

- `DATA/replay/judge-<your-name>.jsonl`: one row per goal, way and cycle with your verdict and one line of reason.
- `docs/design/from-zero/research/r-replay-judge-<your-name>.md`, under 100 lines. Name no project other than agent-annotate; use the letters from the goals files. First a table: for A, B and C: goals judged; actual cycles; par; predicted cycles with the agreement alone; predicted with the whole method; cycles prevented, moved up, unchanged, not about intent; wrong assumptions; needless questions; share where he would have said go. Then: what kinds of thing an agreement catches and what it never does; whether B and C are worth their cost over A; the five goals where the agreement would have helped most and the five where it would have hurt or done nothing, each in three lines; and what the agreement format should add or drop.

Write nothing else. No git commands that change anything. No messages to other sessions. Do not use the annotate skill. Create no beads.

Finish with at most 12 lines: the table's headline numbers, your verdict on the method's central claim, and what the format should change.
