# G — Project C: observed cycles per goal

**14 goal paths; 99 observed goal-cycles; median 5, range 2–19; par 32 in total.** These are lower bounds, not an estimate of project-wide cycles to done.
**5 paths have an owner acceptance/ship decision; only 3 have both a bounded initial request and acceptance.** The accepted subset has median 5, range 2–8. The evidence cannot supply ten complete request-to-acceptance histories.

Sources available: frozen M1 snapshot, questions, rounds, pages, 182 board items, 148 tasks, and 42 structural candidates; rules and handoffs also exist. No M5 transcript corpus existed at start; frozen review-page records already cover both hosts. No other Mac was read.
The question corpus has 306 questions. Its 104 round rows reduce to 72 distinct Send times after page moves and host copies; the frozen source events contain the same Send times and fuller answer sets. A page batch counts once for every goal it touches: 98 goal-cycles across 62 selected Sends, plus 1 typed chat return.
A first response to a helper question counts; an unsolicited initial goal statement does not. Draft/saved answers without a retained Send do not count. These conventions are explicit because the brief does not resolve the initiating-page-answer case.
Each cycle has one dominant cause; multiple answers within it remain evidence, not extra cycles. Cause labels and goal boundaries are analyst judgments. Parent and subgoal paths overlap; adding their counts or words is not total human attention.

| Goal | Size | Returns / par | Linked words | Elapsed days | Owner end |
|---|---|---:|---:|---:|---|
| C01 Seed the staging store with the approved catalog | medium | 5 / 2 | 47 | 2.12 | accept/ship |
| C02 Draft three steel and care articles for review | medium | 2 / 3 | 0 | 3.61 | accept/ship |
| C03 Keep agents from accidentally writing to the live store | medium | 10 / 2 | 27 | 4.64 | not recorded |
| C04 Prove the contact form and newsletter work | large | 7 / 2 | 38 | 14.84 | not recorded |
| C05 Make account and checkout pages match the dark theme | small | 4 / 2 | 0 | 0.42 | not recorded |
| C06 Get live browser proof without holding up the site | medium | 5 / 2 | 141 | 1.77 | not recorded |
| C07 Prepare usable Terms Shipping and Refund drafts | medium | 3 / 2 | 43 | 0.21 | not recorded |
| C08 Prepare one reviewed package for the client | large | 8 / 2 | 485 | 33.82 | accept/ship |
| C09 Make products and photos match the approved catalog | large | 12 / 3 | 818 | 33.84 | not recorded |
| C10 Back up and reversibly replace the live store | medium | 19 / 2 | 1584 | 1.47 | not recorded |
| C11 Back up the live store before launch | small | 5 / 2 | 184 | 0.95 | accept/ship |
| C12 Build a scripted automated test system | medium | 13 / 2 | 697 | 2.42 | not recorded |
| C13 Choose a temporary photo for the first home slide | small | 2 / 3 | 0 | 0.12 | accept/ship |
| C14 Make cookie consent fit the site and cover US visitors | large | 4 / 3 | 287 | 32.10 | not recorded |

Size is a scope judgment (hours/days/weeks), not measured effort. Open-path days end at the last observed return, not at completion. Acceptance of a draft, sufficient backup, or ship decision does not prove deployment or client sign-off.
Par = 2 + required visual taste decisions, recorded per row. The 99 observed returns versus 32 par is a descriptive gap, not 67 proven wasted interruptions; censoring, nested goals and judgment affect it.
Screenshot reference approvals are technical baseline decisions, not new taste forks; matching account pages to an existing theme adds no taste decision. The four extra par cycles concern article wording, photo treatment, the temporary home photo and banner treatment.
Causes: `his_decision` 40; `sent_back_intent` 16; `sent_back_quality` 9; `not_needed` 10; `his_change` 4; `status_or_nudge` 10; `relay` 0; `tooling` 10.
Linked non-option words total 4351 across overlapping paths. Minutes per goal/cycle are **unknown**: there is no active reading or typing clock. Answer wait, session length and calendar elapsed are not attention time. Choice labels are excluded; re-sends and multi-topic notes are not fresh-keystroke measurements.
Helper-session totals and goal tokens are unknown. Explicit board-ID mentions yield only partial, nonexclusive M1 session lists; whole-session token counters cannot be allocated to goals. Earlier page work predates the retained local transcript coverage.

**What the first statements lacked.** Seeding supplied product scope but not family distinctions or incomplete-candidate handling. Article drafting supplied the titles; precise prose and steel facts still required work. Temporary-slide selection supplied the image and link; only the implementation needed showing.
For migration, full backup and reversibility were explicit; app retention and unmatched inventory genuinely emerged later. Urgency became explicit later too. Backup-copy schemes, tiny request-budget increments and repeated choices already settled by the catalog added process beyond those requests.
For forms and account styling, real store behavior and permissions were initially unknown; repeated capture/harness repairs were system failures, not missing taste. Later instructions explicitly asked for scripts, visible evidence and results rather than more small repair rounds.
For catalog matching, the approved catalog already held names, prices, descriptions and image choices. The owner had to restate its authority. Final coverage percentages are null: there is no complete accepted-scope denominator for open paths. Detailed missing-known/unknown/written distinctions are in each JSONL row.

**The three worst paths (by returns above par).**
C10 — live replacement: 19 returns / par 2, including one direct chat complaint.
The initiating note required a full backup and reversible stages (`f8aa4552fca3`).
Backup custody, retained apps and rehearsal choices reached him; nudges demanded progress and parallel work.
He rejected the process and required launch that day (`d2eaa37ca8d9`); checkout urgency also reached chat.
The site went live, but he still asked for full UAT (`9300ca30929b`); no final acceptance survives.
C12 — automated tests: 13 returns / par 2.
He requested a more script-driven, token-efficient plan (`952aa81d1d85`) and approved phased construction.
Credential questions and proof-retention choices intervened; removing testing from the launch gate changed sequencing.
Two later close-it recommendations missed the continuing objective (`2f53d546d77b`, `744035197c9c`).
Thirty reference-picture approvals form one cycle; phase-C authorization is not acceptance of the finished system.
C09 — catalog matching: 12 returns / par 3.
The first retained photo instruction set ordering and cutout treatment (`0517338d14bb`).
Later review still found wrong imagery; the owner restated catalog authority for photos and titles.
A progress nudge followed (`a0ee77baf7c1`), then title-choice questions repeated the already settled source.
Later catalog-page edits and image approvals are not fully captured; final acceptance remains unknown.

**Rejected goals.** URL repair and seven-worktree cleanup have requests/permission but no final owner acceptance; motion examples have withdrawn cards without sent choices; section-CSS relocation lacks the initial request and final acceptance; measurement graphics lack the catalog-page owner history. Every structural candidate has a disposition and reason in `DATA/goals/c-rejected.jsonl`; board closure alone was never acceptance.
**Checks.** Read 50 seeded random submitted-answer rows against source date, identity, content, choice stripping and mirror treatment: 0/50 extraction errors (0%). This was the same worker, unblinded; it does not validate completeness or causal labels. Random second-pass boundary review and an independent source-event recount matched C04=7, C13=2, C09=12 (difference 0 each).
**Limits.** 10 plainly machine-written or benchmark rows labelled human were excluded from the snapshot's 18 project human rows. 5 relevant saved answers lack retained Sends and are separately listed. Original requests, external catalog interactions, final client acceptance, active minutes and allocatable tokens cannot be rebuilt; this is why most rows are partial lower bounds.

**Reproduce.** DATA = `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/`. Run `nice -n 19 python3 /Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/scripts/g_c.py`. It writes `DATA/goals/c.jsonl`, this report, source hashes, canonical rounds, exact comment-to-goal membership, candidate dispositions, the seeded sample, and source recounts; manual judgments are frozen in `DATA/goals/c-manual-audit.json`. It asserts time order, unique cycles, valid single causes, par arithmetic, matching Send-time coverage and the three recounts. No source mutation or live-service check is performed.
