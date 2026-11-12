# D4 — Goals, boards, runs and handoffs

**2,318 board items; 2,507 Orca task records across 76 retained runs; 50 distinct handoff notes; 1,119 structural goal candidates. No source supports cycles per human goal.** (A)

Read-only capture on M1Max.local, ending 2026-11-12T08:09:10.085761+00:00. **R** reproduces every number below from **A**, frozen **B/E/O/H** records and audit **Q**. Project labels protect other projects’ names; the private key is `DATA/d4-project-key.json`. Zero means no observed record, not no work.

| Project | Items | Tasks | Handoffs | Goal candidates | Closed candidates | Closed median days | Closed p90 days |
|---|---:|---:|---:|---:|---:|---:|---:|
| Agent Annotate | 195 | 176 | 8 | 87 | 81 | 0.369 | 7.000 |
| P2 vehicle product | 1916 | 1690 | 24 | 984 | 882 | 0.118 | 2.756 |
| P3 commerce | 182 | 148 | 1 | 42 | 35 | 0.023 | 0.108 |
| P4 multi-Mac tooling | 15 | 1 | 2 | 2 | 1 | 0.010 | 0.010 |
| P5 board evaluation | 10 | 0 | 0 | 4 | 3 | 0.005 | 0.013 |
| P6 lead platform | 0 | 53 | 11 | 0 | 0 | — | — |
| P7 related lead project | 0 | 4 | 0 | 0 | 0 | — | — |
| P8 workflow tooling | 0 | 89 | 0 | 0 | 0 | — | — |
| P9 tool packaging | 0 | 3 | 0 | 0 | 0 | — | — |
| P10 scheduler integration | 0 | 3 | 1 | 0 | 0 | — | — |
| P11 ticketing | 0 | 0 | 3 | 0 | 0 | — | — |
| Unassigned | 0 | 340 | 0 | 0 | 0 | — | — |
| Overall | 2318 | 2507 | 50 | 1119 | 1002 | 0.117 | 2.836 |

Discovery ran `bd --readonly where --json` in 165 project/repo folders. 6 board locations answered; one backup repeated 69 active-board IDs and was excluded from the corpus. Lists were unlimited and included infrastructure, gates, templates and ephemeral records; `bd show --include-comments --json` hydrated each item. All 2318 active-item histories returned audit events including creation. Actual commands and exit codes are in `DATA/d4-raw/commands.jsonl`.

Goal grouping follows recorded parent chains; parentless items remain singletons. Only 51 candidates contain several items, and only 19 of those are closed: their median is 4.671 days and p90 13.729 days. The overall short median is dominated by small singleton records. An epic can also cover a whole application. These are filing-to-closure clocks, not request-to-human-acceptance clocks; open candidates are excluded from duration percentiles.
Only 1117 task briefs name an observed board ID. Goal rows preserve explicit task joins, PR-number references and referenced versions matching local Git tags; missing joins are not inferred. PR counts count referenced numbers, with cross-repository collisions unresolved; a reference or local merge subject is not proof of a canonical merged PR or accepted goal. Summing goal rows yields 288 PR-number reference occurrences and 126 version/tag reference occurrences, with reuse across goals.

Acceptance: 491/2318 items (21.18%) currently have an explicit criteria field or labelled done section. A prose block counts as a block; only written list entries are individually counted. Implicit requirements in ordinary prose are not scored as explicit checks. Before recorded work, 336/2318 (14.50%) have checks in a retained full snapshot at or before the recorded start; 433 are indeterminate.

| Earliest snapshot before recorded start | Items | Items reopened | Reopen share | Closed-item median days |
|---|---:|---:|---:|---:|
| Explicit checks detected | 336 | 14 | 4.17% | 0.326 |
| No explicit checks detected | 1549 | 38 | 2.45% | 0.089 |
| Timing unknown | 433 | 1 | 0.23% | 0.242 |

Checks do not predict faster or less-reopened work in this observational split. Complex or slower work may get more explicit criteria. Recorded starts are claim timestamps, not proof that no work happened earlier; historical snapshots can also omit unrecorded work. This is not a causal test.

**Done, then undone:** 68 recorded reopen events on 53 items (2.29%), spanning 41 structural goals. These are status reversals, not necessarily human rejection. `agent-annotate-4zw` explicitly records closure after narrowing away the original local-baseline criterion; `agent-annotate-kbv` retained a performance target unmet by the first shipped improvement; `agent-annotate-90o` was closed accidentally while awaiting an owner answer. The records do not supply a complete reason taxonomy for every reopen.
Worker mail contains 2 explicit same-Task corrections after a completion claim: `task_85a97ce3bd09` needed a false statement about hash reproducibility corrected and sent a superseding report; `task_bda5c36e2693` needed audit totals reconciled with its stated sample. Another 4 tasks combine success-like reports with later unclosed/failed status; checkpoint reports and administrative state changes make those ambiguous, so they are not counted as false completion. Board and task examples cannot be deduplicated into a shared goal miss rate.

**Workers:** of 2421 task records with dispatch/report evidence, 2088 (86.25%) are marked completed with success, at most one retained dispatch/report and no detected return. This is a first-report completion proxy, not first-time human acceptance. 2 (0.08%) have an explicit detected coordinator return; 19 (0.78%) have additional retained dispatches under the same Task ID. Fresh Task IDs and file-only briefs hide other returns and retries.
Current dispatched-task states: completed 2110; failed 232 (9.58%); blocked 64 (2.64%); dispatched 8; ready 7. 67 unfinished records are older than a week, but age alone cannot establish a running worker stall. The remaining 86 records lack retained dispatch/report evidence.
Of 24993 unique mail records, 22610 can be assigned to worker/coordinator conversations without ambiguous terminal reuse. Workers asked 891 attributable questions (0.368 per dispatched task); 941 question messages exist overall. Only 9 task rows retain provider identity and 8 retain a model through worker-list projections. Actual start times are unavailable; `created` is kept separately from null `started`. Capture timestamps prevent later mail being misread as a reversal of an earlier snapshot.

**Handoffs:** 57 files reduce to 50 distinct contents; median 1400 words, p90 2515.1. Dated notes occur on 17 dates; the busiest is 2026-11-10 with 14 notes. 5 have no reliable date; 4 lose text to the secret screen while retaining word-count metadata. Note counts do not prove completed ownership transfers or capture all handovers.
Unfinished-work sections contain 102 named issue-reference occurrences across notes (median 2.0 per readable note). 27 adjacent/linkable note pairs yield 10 with repeated IDs (37.04%); 15 named-reference occurrences carry over. Explicit previous-note links take precedence over same-stream ordering. These measure repeated references in unfinished-work sections; prose actions, unnamed tasks and referenced already-closed dependencies prevent an exact unfinished-item count. `total_open_items` stays null.

Weekly **peak simultaneous** structural candidates, using creation-to-all-members-closed intervals (open goals censored at capture):

| Week starting UTC | Peak simultaneous | Active at any point in week |
|---|---:|---:|
| 2026-09-28 | 1 | 1 |
| 2026-10-05 | 20 | 25 |
| 2026-10-12 | 35 | 157 |
| 2026-10-19 | 177 | 412 |
| 2026-10-26 | 150 | 522 |
| 2026-11-02 | 135 | 228 |
| 2026-11-09 | 130 | 192 |

**Work about work:** 64 items (2.76%) concern tracking, reconciliation or coordination; 212 (9.15%) concern helper/test runtime and infrastructure. Together that is 276/2318 (11.91%) by item count. Delivery operations (116, 5.00%) and review-tool product features (142, 6.13%) are separate. Counting both as working-system work would raise the share to 23.04%; that is a policy sensitivity, not an error bound or a waste estimate.

| Board | Coordination | Helper/test system | Delivery operations | Review-tool product | Application product | Unclear |
|---|---:|---:|---:|---:|---:|---:|
| Agent Annotate | 7 | 36 | 10 | 142 | 0 | 0 |
| P2 vehicle product | 45 | 146 | 103 | 0 | 1613 | 9 |
| P3 commerce | 11 | 10 | 3 | 0 | 158 | 0 |
| P4 multi-Mac tooling | 0 | 15 | 0 | 0 | 0 | 0 |
| P5 board evaluation | 1 | 5 | 0 | 0 | 0 | 4 |

Rules use the primary deliverable in the title, an explicit test-contract repair in criteria, and the infrastructure-only board. Bookkeeping takes precedence over runtime terms. Application-board items without such evidence stay application work; review-tool features stay tool product. Every item records its rule. This screen can miss implicitly described tooling work and misread ambiguous titles; it measures neither effort, cost nor the person’s attention. The dominant application board also dominates the aggregate.
**Quality:** read 50 seeded random source rows (30 items, 10 tasks, 10 notes). The purpose-label check found 3/30 disagreements before fixes (10.00%); after calibration, sampled source-field checks found 0/50 discrepancies (0.00%). This was not blind and does not validate semantic goal grouping or complete return detection. Audit rows, manual labels and results stay in DATA. (Q)

**Why cycles cannot be counted:** boards record filing/claim/closure, runs record assignments and helper reports, and notes record selected context. None joins a stable human goal to every agreement, showing, correction and explicit acceptance. The 5 supplied cost reports aggregate 16 delivered rounds but contain no goal key, so rounds cannot become per-goal cycles. Local Git logs supply tags/merge subjects, not human acceptance or complete remote PR history.
Needed: one stable goal ID across requests, board items, Tasks, handoffs and immutable result revisions; timestamped agreement/showing/correction/acceptance events naming the actor and revision; a cycle reason and supersession link; and acceptance checks frozen before work. Link each coordinator return to the prior claim and next attempt. The headline measure then counts human-facing goal cycles rather than status changes, tasks, messages or releases.

Reproduce: `DATA` is `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/`. Run each command separately. Collection is local and read-only; no mail-consuming check, page/bead mutation, remote access, install or Git mutation was used.

- B: `nice -n 19 python3 DATA/scripts/d4_collect.py boards` (`bd where`, `list --all --limit 0`, `stats --no-activity`, `show --include-comments`, all `--readonly --json`).
- E: `nice -n 19 python3 DATA/scripts/d4_collect.py histories` (`bd --readonly history ID --events --json`).
- O: `nice -n 19 python3 DATA/scripts/d4_collect.py orca` (`worktree ps`, paginated `run-list`/`worker-list`, `task-list`, non-consuming `inbox`, JSON/full forms; help checked first).
- H: `nice -n 19 python3 DATA/scripts/d4_collect.py notes-git` (shared-folder notes, supplied cost JSON and distinct-repo `git log --all --format=... --max-count=30000`).
- A: `nice -n 19 python3 DATA/scripts/d4_analyze.py` writes the four requested corpora, summary and weekly table. Percentiles interpolate sorted closed durations.
- Q: `nice -n 19 python3 DATA/scripts/d4_verify.py`; parser checks: `python3 DATA/scripts/d4_analyze.py --self-test`.
- R: `nice -n 19 python3 DATA/scripts/d4_report.py` renders this file; exact commands, flags, folders, timestamps and failures are in the raw command ledger.
