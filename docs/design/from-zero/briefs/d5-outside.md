# D5. What is already known outside: evidence and prior art

Follow `docs/design/from-zero/briefs/common-data.md`. It overrides anything below. You need web search for this task. If you have no working web search or fetch tool, send `worker_done` at once saying so, and do nothing else.

## Why

The method in `docs/design/from-zero-20261112.md` rests on ten principles borrowed from how people direct work where attention is short and mistakes are dear. They were reasoned, not checked. Before a design is built on them, find what the evidence says, where the principles are wrong or incomplete, and what others have already tried on the screen.

## Part A. Are the principles true? (about 60% of your effort)

For each of the ten principles in section 3, and for the "three gaps" in section 2, find the strongest evidence for and against. Prefer measured studies and long-standing professional practice over opinion pieces. Useful starting points, not limits:

- saying the order back: military back-briefs and commander's intent; closed-loop communication in surgery and aviation; structured handovers in hospitals;
- reacting beats specifying: prototyping studies, requirements research, design critique;
- cost of late-found misunderstanding: what the software defect-cost studies actually measured, and their critics;
- decide once: precedent, standing orders, standard work, decision logs;
- believable silence: management by exception, the dark cockpit, alarm fatigue, automation complacency and trust calibration in human-automation research;
- defaults and deadlines: default effects, "unless I hear otherwise" in staff work, service-level clocks;
- maker and checker: four-eyes principle, independent verification, inspection research, where checking fails (rubber-stamping, shared blind spots);
- one counterpart: chief of staff, single point of contact, span of control;
- earned trust: graded autonomy in medicine and aviation, sampling plans in quality control (tightened and reduced inspection);
- limiting work in progress: queueing results, kanban limits, context-switching and interruption research (resumption cost, attention residue), the limits of working memory.

For each: what is solid, what is shaky, what number is worth quoting, and what the method should change because of it.

Then answer: **what is missing?** Name any well-supported principle of delegation, supervision or attention that the ten do not cover and that would change the design.

## Part B. What have others built? (about 40%)

Look at products and public write-ups where one person directs several software helpers or a team asynchronously. Include current tools for directing AI coding helpers and their published user complaints, and also non-software fields: executive assistants and briefing books, air traffic strips, hospital ward boards, newsroom desks, construction punch lists, restaurant pass.

For each pattern you find (not each product): what the person sees, what it costs them in attention, where it works, where it is known to fail. We are looking for patterns to borrow and traps to avoid. Do not recommend adopting any product.

## Findings file

`docs/design/from-zero/research/d5-outside.md`, up to 200 lines for this task:

1. A table: principle, verdict (holds, holds with a limit, doubtful), the best evidence with its source, what to change.
2. Missing principles.
3. Patterns to borrow, each with where it comes from and what it costs the person.
4. Traps: ways that designs of this kind are known to fail (for example, people stop trusting a quiet system; checkers rubber-stamp; defaults get accepted blindly; summaries hide the thing that mattered).
5. Sources, with links. Mark any claim you could not trace to a primary source.

Keep the full notes in `DATA/outside/`.

## Done means

Every principle has a verdict with a traceable source, parts 2 to 4 are filled, and nothing is stated as fact that you could not source.
