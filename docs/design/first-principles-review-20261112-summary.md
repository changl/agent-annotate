## agent-annotate from first principles: round 2 for Chang

Full review: `first-principles-review-20261112.md`, same folder. Sections 6, 7 and 9 are new. Nothing live was changed.

**How to answer.** Reply in the session, for example `1A 2A 3A`, with any words you like, or type notes straight into either file. This review does not go through an annotate page.

**Settled by your answers.** A standalone service with an Orca face. Its home is M1 Max, the central brain, and the other Macs connect to it. (This session runs on M1 Max; "this Mac" in round 1 meant it.) First comes the "needs you" list, widened as you asked.

**Added: one home page for every project.** Each project is a row: what needs you, the workers on each Mac (working, waiting, idle, stuck), the board, the cost. An analytics tab tracks your targets week by week against a baseline week. No agent writes any of it. Orca already reports every agent on all three Macs to M1 Max; checked today: 5 of 19 working here, 5 of 6 on M5 Max, 0 of 2 on M1 Max 16.

**Added: a thin coordinator.**

- Today a coordinator is a memory, a clerk and a judge in one long session. FLD's took 149 turns to deliver 11 rounds in three days. 68% of its cost was re-reading its own context, and 37% was clerk work: waiting, mail, board, dispatch, rollout.
- Target: memory lives in Beads and the page. A Windmill flow does the clerk work with no tokens. A model is called only to judge, with a small packet. Most parts exist: the Windmill-to-Orca bridge runs every few minutes for tests.
- No coordinator at all: only for work a script can pass or fail, and only after the numbers hold.
- Safety: a week in shadow beside the live coordinator first; one project and one kind of work at a time; a coordinator can be restarted from stored state at any moment; a stop rule if progress or quality drops.

**Your targets, as numbers.** Load 50% lower means three counts each halve: decisions put to you per finished item, words you type per week, places you look (23 page links today, then one). Tokens: at most 5% more per finished item, aiming lower. Quality and progress: reopened items, rework and items finished per week no worse than a baseline week, aiming better.

**One question.** A full build flow in Windmill (tests first, build, verify, second-agent review, your sign-off in a "Needs Chang" inbox) was built on 25 Sep and has one 36-second run on record. What stopped it becoming the normal way? The thin coordinator is the same idea, and I could not find the reason.

**Decision 1. Where is the thin coordinator tried first?**

- A (recommended). agent-annotate: smallest, and a miss costs little.
- B. FLD: largest spend and most data, highest risk.
- C. Rebex.

**Decision 2. Are the target numbers above the right yardsticks?**

- A (recommended). Yes, as written.
- B. Change them: say which.

**Decision 3. What next?**

- A (recommended). I write the build brief for stage 1 (home page and baseline, two weeks, read-only) for the coordinator. I still build nothing.
- B. Another round on the review first.
