# MC. Judge the four machine designs

You are one of three critics working separately, each with a different lens (yours is in your task message). Do not look for the other critics' work.

## Read first

1. `docs/design/from-zero-20261112.md`: the method.
2. `docs/design/from-zero/plan.md`, sections 2, 3 and 5.
3. `docs/design/from-zero/scenario.md`: the test week.
4. Everything present in `docs/design/from-zero/research/`: what the record and outside evidence show.
5. The four designs in `docs/design/from-zero/machine/`: `record-first.md`, `check-first.md`, `office-first.md`, `capsule-first.md`. Each was written separately from a different centre.

Do not open `docs/design/first-attempt-20261112/`.

## Do

1. **Lay the four side by side.** For each of these, one line per design: what is kept in the record; how a sentence becomes an agreement; what decides whether something reaches him; how a "done" line is checked and by what; what notices a stall; how an answer becomes a rule; how trust changes what he is shown; how helpers on several computers take part; what must be built that does not exist.
2. **Find the agreement.** Where all four, working apart, reached the same answer, say so plainly. Independent agreement is strong evidence. List those points.
3. **Find the real forks.** Where they differ in a way that matters, state the fork as a question, the options, what each costs and risks, and which you would choose and why. Ignore differences that are only wording.
4. **Judge through your lens** (see your task message), thoroughly, with specific section references.
5. **Find what all four missed.** Check against the research files: the outside evidence, the procedures of other fields, the questions data. What does the evidence demand that no design provides?
6. **Propose the combined design**: which parts from which design, how the forks are settled, in at most 40 lines. Then the smallest first version of it that would already beat today on cycles to done, with the meter in it.
7. **Say what must be tested before anyone builds**, and how each test could be run cheaply.

## Output

One file: `docs/design/from-zero/research/machine-critique-<your-lens>.md`, at most 220 lines, with the side-by-side table first. Plain words: a reader who has never seen any of today's tools must be able to follow it.

Write nothing else in the repository. No code. No git commands that change anything. No installs. No changes to any tool, board, schedule, page, skill or instruction file. No messages to other sessions. Do not use the annotate skill. Create no beads.

## Finishing

Send `worker_done` once, with at most 15 lines: the points all four agree on, the three forks that matter most with your choice for each, what all four missed, and your ranking.
