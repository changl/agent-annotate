## agent-annotate from first principles: summary for Chang

Full review: `first-principles-review-20261112.md`, same folder. Nothing live was changed.

**How to answer.** Reply in the session, for example `1A 2A 3A`, with any words you like. For notes, type them straight into either file where they apply; I read them from the file's changes and revise once per round. This review does not go through an annotate page.

**What it is for.** One place where your decisions enter the build, and the mechanism that carries each one to the right agent once and shows you it was acted on. Running agents is Orca's job, tracking work is Beads' job, routine runs are Windmill's job.

**What it should look like.** A small service that keeps the records, with three thin faces: a command for agents, the web page you use now, and an Orca plug-in that shows a "needs you" count and list across every project.

**What I found.**

- This Mac runs 17 separate page servers for 19 pages. The three Macs are on two different releases.
- Agents have 45 commands to choose from. The tool still takes 6–11% of a coordinator's cost; the goal is 3%.
- Your side had never been measured. On this project's page: half your answers come within 34 minutes, 4 in 10 take over an hour, and a third are typed in words because the options did not fit. When you do pick an option, it is the recommended one 41 times in 47.
- An Orca plug-in alone cannot do the job today: it cannot give agents their tools, and it does not reach your phone or browser.

**What changes for you, in order.**

1. One list of what needs you, in Orca, instead of 23 page links.
2. Fewer, better-fitting questions; one action to accept every recommendation; a question you answered as a rule is not asked again.
3. Releases stop needing your approval for each other Mac.

**Decision 1. What shape should it take?**

- A (recommended). Standalone service with an Orca plug-in face: works in any browser and for every agent; Orca shows the count and list; if Orca changes its plug-in system, only the small face is redone.
- B. Orca plug-in only: everything lives in Orca; no phone or browser review; Codex and Windmill cannot get their tools from it today.
- C. Standalone only, as now: nothing new to build; still a separate place you must remember to check.

**Decision 2. Where should pages live?**

- A (recommended). One home on this Mac; the other Macs connect to it: one list, one install per release, no approvals for the other Macs on most releases. If this Mac is off, agents elsewhere queue until it is back.
- B. Each Mac keeps its own pages, with a shared list: keeps working when this Mac is off; every release still goes to three Macs.

**Decision 3. What is built first?**

- A (recommended). The "needs you" list in Orca plus a weekly measure of your review load: one week, changes no data, undone by switching it off. Needs your one-time approval of the plug-in in Orca.
- B. One page server instead of 17: a larger clean-up, one to two weeks, touches every page; you see no difference.
- C. Nothing yet: revise this review first.
