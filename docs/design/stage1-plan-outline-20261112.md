# Stage 0 and stage 1: plan outline

An outline, not a build brief. It follows `first-principles-review-20261112.md` (sections 6, 9 and 10). Nothing is built until Chang accepts the look and feel.

## Goal

One page on M1 Max that shows every project: what needs Chang, the agents on each Mac and what they are doing, and each project's current goal. An analytics tab that tracks cycles to done and his targets. A count and a list inside Orca. No agent writes any of it, and no stored data changes.

## Stage 0: look and feel, before any build

| Step | What | State |
|---|---|---|
| 0.1 | Mock-up of the Projects tab, the Analytics tab and the Orca panel, on the live page's own styles. | Done: `home-page-mockup-20261112.html`. Checked in a real browser, dark and light, desktop and phone. |
| 0.2 | Chang reacts: in the session, or as notes in the summary file. | Round 3 |
| 0.3 | One revision per round until he accepts it. | — |
| 0.4 | The accepted mock-up is frozen as the build's acceptance reference. The build is compared to it by screenshot. | — |

Rules the mock-up already follows, all his: nothing scrolls sideways at any width; tables turn into cards on a phone; tabs, not a dropdown; red means "needs you", yellow "an agent has it", grey "nothing to do"; plain words and no ids; no row or label that repeats another; both themes.

Open in the mock-up, for him to settle:

1. Macs as columns (as drawn) or as rows.
2. Whether old questions are shown apart from new ones, with one action to set a page's old questions aside.
3. What a click on an agent does: nothing, or open its terminal in Orca.
4. Whether the Orca panel lists questions only, or also agents.

## Stage 1: build, two weeks, read-only

| Step | What | Reads from | Week |
|---|---|---|---|
| 1.1 | Day-one proof: can an Orca plug-in worker reach the service and feed a panel? If not, the status-bar item opens the home page in an Orca browser tab. | Orca plug-in docs; a throwaway plug-in | 1 |
| 1.2 | Reader: questions waiting and their age, for every page. | Page stores, with the rule the session-start line uses (`src/agent_annotate/hooks/session_start.py:44`) | 1 |
| 1.3 | Reader: agents per Mac and their state. Pick by test which of Orca's two status fields means "working". | `orca worktree ps --json`, for M1 Max and each paired Mac | 1 |
| 1.4 | Map: which project a folder belongs to. | `src/agent_annotate/workspace.py:19` | 1 |
| 1.5 | Reader: each project's goal and items finished of total. | Beads | 1 |
| 1.6 | One read-only address that returns all of the above, and the home page's Projects tab. | 1.2–1.5 | 1 |
| 1.7 | Orca plug-in: status-bar count and side panel. | 1.6 | 1 |
| 1.8 | Baseline script: his load, tokens, quality, progress, and cycles per project per week. | Page stores, session logs, Beads | 2 |
| 1.9 | Analytics tab. | 1.8 | 2 |

Not in stage 1: any change to cards, rounds, delivery or agent commands; anything installed on M5 Max or M1 Max 16; cycles counted per goal (that needs stage 2's tie between a card and its goal).

## Proof

- The count equals the sum of the pages' own counts in 20 spot checks.
- Agent counts equal Orca's on all three Macs in 20 spot checks.
- A row opens the right page at the right question.
- Screenshots match the accepted mock-up: dark and light, desktop and phone, with nothing scrolling sideways.
- A baseline file exists for every page and project.
- Agent tokens: unchanged, because no agent calls anything new. Checked with `scripts/orch_cost.py` before and after.

## What Chang is asked for

- His reaction to the mock-up (stage 0).
- One approval of the plug-in in Orca, when 1.7 is ready.
- Nothing else. Undo is switching the plug-in and the address off.

## Who builds

The coordinator's workers, from a build brief written after stage 0. The author of this outline builds nothing.

## Risks

- An Orca plug-in may not be able to do 1.7. Step 1.1 answers that first, and the fallback keeps the stage whole.
- Old questions make the count look worse than it is: 15 of today's 32 are 41 to 48 days old. Stage 0 decides how they are shown.
- Cost for sessions on the other Macs needs the cost script to run there. Week two covers M1 Max; the rest waits for Chang's yes per Mac.
