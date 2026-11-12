# MC2. Judge the four machine designs: simplicity and cost

Your full brief is `docs/design/from-zero/briefs/mc-machine-critic.md`. Read it first and follow it exactly.

Your file: `docs/design/from-zero/research/machine-critique-cost.md`.

Your lens: **simplicity and cost.** A design that cannot be built and kept running by a very small team is worth nothing, however complete. For each design:

1. Count the moving parts: kinds of thing in the record; kinds of run; rules in the gate; clocks in the watch; states a goal can be in. Give the numbers.
2. For one medium goal, count the runs from his sentence to his acceptance: how many by script, how many by a helper, and roughly what each helper run must read. Compare with today's pattern: one long-lived coordinating helper that re-reads its own history, plus workers. Where is each design cheaper, and where dearer?
3. Sort every part into: must exist on day one; can wait; ceremony that protects against nothing the research shows to be a real problem.
4. Say what must be built new, what could be an existing piece used as it is, and what would need an existing piece bent out of shape. If `research/x-what-exists.md` is present, use it; if not, say so and judge from the designs' own last sections.
5. Estimate how hard it would be to explain the running system to him in five minutes, and to find out why something happened a week later.
6. Find the simplest design that still keeps every protection the research shows to be necessary. It may be one of the four with parts removed.

End your lens section with: the parts you would cut from each design with no loss, and the five things that must be true on day one for the first version to be worth using.
