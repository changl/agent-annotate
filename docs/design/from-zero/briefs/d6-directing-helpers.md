# D6. How people direct software helpers today, and where it hurts

Follow `docs/design/from-zero/briefs/common-data.md`. It overrides anything below. You need web search for this task. If you have no working web search or fetch tool, send `worker_done` at once saying so, and do nothing else.

Another worker (D5) is checking the evidence behind the method's principles and taking a first, broad look at prior art. Your job is narrower and deeper. Do not coordinate with them.

## Why

Many products and teams now let one person direct several AI coding helpers at once. Their users write a great deal in public about what works and what wears them down. Before we draw our own answer, we need the patterns and the complaints laid out, so that we borrow what is proven and repeat nobody's mistake. We are not choosing a product and will not copy one.

## Find

Cover at least 15 current products or open projects where a person directs one or more AI helpers that work for minutes to hours without them: cloud and background coding agents, agent "inboxes" and task queues, multi-agent orchestrators, agent-in-the-issue-tracker features, review-first tools, and voice or chat front ends to agents. For each, from primary sources (their documentation, changelogs, engineering posts) and from user reports (forums, issue trackers, long-form reviews, published studies):

1. How the person states what they want. Is anything said back to them before work starts? Can they correct the plan before effort is spent?
2. What the person sees while work runs. What is pushed to them, and what is silent.
3. How a question from the helper reaches them. Does it carry a suggestion, a default, a deadline?
4. How finished work is shown. The thing itself, a diff, a summary, a recording, a preview link? How do they correct it?
5. How the helper's work is checked before the person sees it, and by what.
6. Whether the system learns the person's preferences so that it asks less over time, and how.
7. How trust is widened or narrowed (permission modes, auto-approve, autonomy levels).
8. How many places the person must look when they run several helpers or several projects.
9. What users complain about most, in their words, with links. Look especially for: review fatigue, false "done", having to babysit, lost context, too many notifications or none, approving without reading, cost surprise, not knowing what the helper is doing, and work piling up waiting on them.

## Then

- Group what you found into **patterns** (not products). For each: what the person sees, what it costs them in attention, where it works, where it is reported to fail, and which products use it.
- List the **ten complaints** that recur most, with how often you saw each and the best two sources.
- List anything you found that **nobody does well**. That is where a new design can win.
- Note any measured results (studies or published telemetry) on time saved, review time, acceptance rates, or how often people intervene.

## Findings file

`docs/design/from-zero/research/d6-directing-helpers.md`, up to 200 lines: patterns table; complaints table; what nobody does well; measured results; sources with links. Mark anything you could not trace to a primary source. Full notes in `DATA/outside-d6/`.

## Done means

At least 15 products covered across the nine questions, every complaint has a link, and no product is recommended.
