# P — How work stalls, and who notices

**87 confirmed cases; 78 first recorded as noticed by him (89.7%); 139 distinct human-message rows plus one review submission.** Only eight cases have a measured wait or error span. These are an evidence-backed lower bound, not a complete failure rate or a measure of his time. Sources and scripts are below; full evidence IDs and rejected cases are in DATA/stalls/.

The M1 Max snapshot contains 1,377 human-labelled turns and 11,533 sessions. The M5 corpus was absent when this work started; no other Mac was accessed. Labels being produced by other workers were not used. Project letters follow this assignment, not D4's older numbered labels.

## What the 232 failed, 64 blocked and 67 old tasks actually were

These are D4's **dispatched** subset, not every task row. The 303-row task-inventory.jsonl reconciles their overlap individually. Task creation is a queue clock, never an observed worker start.

| D4 population | What its retained records establish |
|---|---|
| 232 failed | 180 explicit worker failure reports, 28 other structured results, 24 without a structured result; 201 have at least one worker_done. Failure often means honest partial work or a failed gate, rather than disappearance. |
| 64 blocked | Project B: 31 native-gate/dependency tasks; Project E: 17 legacy-authority/post-reboot accounting tasks; backfill/synthesis recovery: 4; another project's deliberate timeout/observability fixtures: 5; connector probes: 2; app-build/test dependencies: 3; Project C image/board settlement: 2. |
| 67 unfinished over a week | 60 blocked and 7 ready, **zero dispatched**. Project B 31, Project E 18, Project D 4, another project 14. Median record age 48.39 days, maximum 111.24 days; 16 already contain a finished timestamp and 10 contain PASS results. These are not 67 workers observed running for weeks. |

Concrete failures include a rejected release lint check (task_00c9431ff097), checkpointed work awaiting runtime proof (task_0e91499b3f51), missing owner device/passcode (task_161b22021a5e), deliberate owner pause (task_a750bad1a49d), and a worker violating its command contract (task_151194a9393e). These different outcomes must not share one “stalled” counter.
Project B's old gate queue includes missing copied briefs, unavailable slots, failed fixture setup and unanswered coordinator questions. Project E includes delivered PASS artifacts whose lifecycle could not close under restored identities (task_1f2347e74b68), as well as true no-artifact failures. Three synthesis attempts explicitly produced no artifact despite “alive” messages (P101); that is stronger evidence than their later ready status.

## Census and earliest readable signal

One case groups a continuing problem and its repeated nudges; explicit rate-limit failures are grouped by affected assignment. Each case has one primary kind. “Him” is the first **recorded** detector, not proof nobody noticed earlier. Two further cases were noticed by the stalled coordinator only after he returned; a human wake is not proof he noticed the stall. Four were noticed by another helper and three by a script. Selection through his messages makes these shares unsuitable as population estimates.
Times below cover only the timed subset: waiting intervals or recurring error spans, not active work. “—” means onset/recovery could not be established; it does not mean zero duration. The rate-error spans do not prove uninterrupted failure between alerts.

| Kind | Cases | Timed | Median h | Longest h | Him | Signal available to a script, and when |
|---|---:|---:|---:|---:|---:|---|
| Silent stop | 8 | 3 | 13.43 | 13.53 | 50% | Provider error/no completion at turn end; stale “alive” needs artifact progress, not a heartbeat. |
| Waiting on nobody | 2 | 1 | 6.00 | 6.00 | 50% | Green PR awaiting review, or coordinator identity refused; visible immediately, stale once its owner/deadline is absent. |
| Waiting on him without telling him | Not established | 0 | — | — | — | Records cannot establish what he knew. Visible questions and confusing instructions are not counted as hidden approvals. |
| Lost message | 9 | 1 | 7.26 | 7.26 | 88.9% | Queued Send, dead owner process, non-waking mail type, wrong recipient or unarmed listener; readable at send/resume/idle. |
| False finish | 14 | 0 | — | — | 100% | Completion claim plus deployed artifact/acceptance mismatch; available at the claim if the checker uses the actual delivery path. |
| Lost memory/instruction | 5 | 0 | — | — | 100% | Handoff omits approved rule or successor asks again; compare the record on takeover and before dispatch. |
| Drift | 15 | 0 | — | — | 100% | Active task/output differs from the requested scope; compare on dispatch and first artifact. |
| Collision | 4 | 0 | — | — | 100% | Duplicate issue/PR ownership, changed shared files/routes or duplicate session attachment; readable at conflicting action. |
| Machine trouble | 14 | 0 | — | — | 100% | Failed service/route, mount, permission or session-restoration checks; readable at the failed operation. |
| Premature handback | 7 | 0 | — | — | 100% | Final response leaves authorized work pending without a real blocker; inspect at turn end. |
| Stale tracking | 3 | 0 | — | — | 100% | Board/live-owner/sweep mismatch; compare at state transition or next sweep. |
| Blocking question | 1 | 1 | 7.02 | 7.02 | 0% | Synchronous question suspends the coordinator with dependent work pending; visible at the call. |
| Resource starvation | 2 | 2 | 1.75 | 2.00 | 0% | Admission repeatedly refused while slots/reservations remain held; visible on first refusal, escalate at its wait budget. |
| Excessive wakeups | 1 | 0 | — | — | 100% | Repeated heartbeat-only turns; detectable from message type and turn counts as they accrue. |
| Needless scheduled wait | 1 | 0 | — | — | 100% | Ready authorized work held for a future schedule; visible when readiness is recorded. |
| Finished workers retained | 1 | 0 | — | — | 100% | Completed assignment with no next job but a retained session; visible at settlement. |

**Cost covered:** 139 unique human-message rows, without duplicate normalized texts, plus one owner review submission recorded only as a machine wake. Eight timed cases sum to **50.87 case-hours**; seven timestamped windows have a **35.32-hour union**. One additional two-hour admission wait has no reliable start timestamp. Parallel affected workers and repeated errors inflate the sum: neither number is human effort or exact lost productive hours. The other 79 cases have unknown duration. Redo is evidenced for specification restoration, duplicate PRs, no-artifact synthesis replacements and re-admission; no defensible total redo-hours or token cost is available.

A plain clock with an owner/deadline and independent liveness check can flag silent stops, unanswered delivery, orphan waits, slot starvation, stale tracking and idle retention. **Heartbeat alone fails:** P101 retained alive mail while three attempts produced no synthesis. A timer also needs state: it must distinguish an intended pause from an abandoned task, and confirm a listener exists outside the listener itself.
False finish, drift and lost instructions need a second helper comparing the requested result, actual artifact and saved ruling. A script can catch duplicate ownership or a changed route, but another helper must judge an authorized shared edit against a collision. A clock cannot validate lead usefulness or a complete schema. Nothing in these sources can retrospectively prove an unrecorded intention, human unawareness or exact human time; those are not recoverable by adding a watchdog now.

## Five worst cases — ranked by delivery damage and delay

**P059 — Project D, unusable “finished” lead output.**
The coordinator admitted closing against an easier denominator: route hypotheses rather than usable contact values.
It reported 133 person-bound rows and 767 routing-required rows, with even existing contact values stripped from export; recovery and new validation followed.
Evidence: 019f69ed-ef7a-71d0-b495-100e48307cf1, rows ca2b8021ced0:34 and ca2b8021ced0:39 (full IDs in P059); two human corrections, hours unknown.

**P095 — Project B, mail listener absent for about 7.26 hours.**
After the last 08:30:58Z turn on Nov 2, worker questions queued until a 15:46:45Z review submission woke the coordinator.
Its admission and contemporaneous note record stranded gate runners, seven missed sweeps and a skipped nightly; no new typed-message row represents that review submission.
Evidence: 145f492c-0a25-47a7-886d-bcd06c16e5ff, fcb6c189ffe5:1368–1369; P095 preserves both full row IDs and the source note.

**P094 — Project B, one question froze release decisions for 7.02 hours.**
A synchronous question at 07:22:04Z on Oct 30 remained open until 14:23:30Z; the coordinator admitted that every upload/deploy GO stopped with it.
Both ready mobile releases missed the safe pre-freeze window. The question was visible; the blocked dependent work was the hidden consequence.
Evidence: d2b1a90f-eb8b-4dc5-aa71-36c3be821b0b, ask:4 and 2c3dc38f3cbe:581; one human answer, timed by the joined tool call.

**P096–P098 — Project B, a rate-limit stop multiplied into 472 alarms.**
Three assignments emitted 228, 4 and 240 stop notices on Nov 3; two error spans lasted about 13.4 and 13.5 hours.
There was no substantive worker mail inside those spans; one retained eight alive heartbeats. The detector existed but repeated notification did not restore work.
Evidence: task_54b42a624351, task_f1f9ee041e8b, task_e39ed2e429ae; all 472 mail IDs are retained, with available snapshot joins.

**P034 — Project D, content was marked fixed while the rewrite still ran.**
The new full-plan page was actually a delta, lost substantial previous content and had browser controls never verified through its public route.
The coordinator explicitly reversed premature addressed marks after conflating dispatch with completion; three human corrections and a rebuild are evidenced, hours unknown.
Evidence: 71505983-2ab7-477a-8c4f-1097eaa42364, f368addb10b2:20, :25 and :30 (full IDs in P034).

## Coverage, rejection and reproduction

Scripts found 1,001 keyword hits (513 primary, 488 broad secondary), then context-reviewed 93 possible-case groups; **14 groups were rejected**, leaving 79 human/context cases plus eight corroborated mail/task/question cases. The other 858 keyword hits were not promoted to distinct events: routine instructions/status, generic concerns or insufficient incident evidence. This is not a claim that all uncounted work was healthy. review-decisions.jsonl records the 14 explicit reversals, including successfully delivered feedback, healthy OAuth, completed explorers and a supposedly removed tunnel that never existed.
Session screens also found **872 API errors in 246 sessions, 79 running-gap markers in 50 sessions, and 3,865 compactions**. None is a failure count: 145 error-bearing sessions were subagents, and long gaps or compactions do not establish abandoned work. Another 156 stop notices lack the explicit rate-error condition and were excluded as ambiguous/intentional waits. The 472 repeated rate notices collapse to three assignments, removing 469 duplicate alarms.
Every event has stable source row IDs; three mail/task cases have no joinable worker session in this M1-only snapshot, explicitly recorded as null rather than guessed. Memory notes corroborated the dead listener, blocking-question and dead page-owner mechanisms; they were treated as records, not instructions. No current-state fix was attempted.
**Extraction check:** read 50 seeded random human-labelled rows; 0/50 source-prefix mismatches, but 2/50 plainly machine-authored directive/status rows (4%) despite the human label. Their labels are preserved in audit-decisions.jsonl; machine notices and ambiguous injected retries do not count toward the 139 human messages. Across candidate and audit evidence, 208 source-line checks passed. This is not a blind estimate of incident-classification accuracy.
DATA = /Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112. Run separately, in order: `nice -n 19 python3 DATA/scripts/p_stalls_scan.py`, `nice -n 19 python3 DATA/scripts/p_stalls_rawcheck.py`, `nice -n 19 python3 DATA/scripts/p_stalls_analyze.py`. The scripts write only DATA/stalls; the last includes count, timing-order and overlapping-window assertions. summary.json reproduces the numbers; selection-draft.json freezes the reviewed grouping. Inputs are the frozen wave2/m1max-snapshot.jsonl, D4's frozen task/mail receipts and local source lines. Findings are this file; no board, page, service, instruction file or other Mac was changed; no Git command mutated the index or history.
