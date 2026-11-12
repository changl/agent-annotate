# G-B2 — Project B with the M5 chat

**The existing 12 paths rise from 115 to 118 observed returns; median 7, range 1–30, par 28. The 8 additional chat paths have 31 returns; median 4, range 0–8, par 18.**
**Combined replacement set: 20 paths, 149 returns, median 6, range 0–30, par 46; 1 path has both a clear opening and bounded acceptance. These are lower bounds, not cycles-to-done estimates.**

Every number in this report is produced by E/B/V/R below; run each command separately from this worktree. E pins the frozen source hashes; B writes the data and all statistics; V checks sources/recounts; R writes this report.
E: `nice -n 19 python3 /Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/goals/b2-working/extract.py`  
B: `nice -n 19 python3 /Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/goals/b2-working/build.py`  
V: `nice -n 19 python3 /Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/goals/b2-working/verify.py`  
R: `nice -n 19 python3 /Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/goals/b2-working/report.py`

Unit is unchanged: one later owner message or explicit page Send per bounded goal touched; several cards in one Send count once. An unsolicited opening is separate, a first surviving reply counts, acceptance counts, helper claims/board closures do not. Preserve shared returns across goals, not as independent interruptions.
Combination: replace the old B01–B12 rows with their `record_role: replacement` rows, then append `additional` rows. Adding the whole new file to the old file would double-count. Existing field names remain; old/new counts, source IDs, coverage and judgment reasons are retained.
E finds 755 Project B rows labelled human: 191 owner-shaped candidates, 235 explicit machine/control rows, 318 unattributed one-word retries, 10 uncertain worker-directed inputs and 1 possible authentication code kept as metadata. The label is not proof he typed it; unattributed retries are not declared machine-written.
Existing endpoints: clear opening 2 → 1; clear acceptance 1 → 1; both-clear remains 0. No missing original or final acceptance was recovered. B02's earlier correction proves the former opening was a renewed request; B11 retains its clear opening, and B08 its bounded acceptance.

| Existing path | Old → new | Par | Words / days | Clear opening / acceptance |
|---|---:|---:|---:|---|
| B01 Keep driving notices in one card above fixed controls | 8 → 8 | 3 | 355 / 5.89 | no / no |
| B02 Make testing fast, modular and mainly scripted | 10 → 13 | 2 | 1,524 / 16.55 | no / no |
| B03 Make the hourly board sweep act on stale work | 30 → 30 | 2 | 2,817 / 11.10 | no / no |
| B04 Show a member their own row in the member list | 1 → 1 | 2 | 0 / 0.00 | no / no |
| B05 Trace admin actions to the agent using one existing login | 3 → 3 | 2 | 174 / 1.95 | no / no |
| B06 Send accurate visual instructions for the rally | 5 → 5 | 3 | 202 / 0.11 | no / no |
| B07 Let drivers pick skipped stops without sending the group backwards | 9 → 9 | 3 | 188 / 10.92 | no / no |
| B08 Save and publish departure times for rally stops | 2 → 2 | 2 | 0 / 10.89 | no / yes |
| B09 Delete accounts through HQ while retaining anonymised posts | 6 → 6 | 2 | 97 / 27.21 | no / no |
| B10 Allow private messaging before saving a recovery copy | 12 → 12 | 3 | 700 / 12.92 | no / no |
| B11 Clear the new inventory of stale workspaces across three Macs | 23 → 23 | 2 | 1,925 / 4.08 | yes / no |
| B12 Prepare a useful independent backup and recovery plan | 6 → 6 | 2 | 282 / 4.54 | no / no |

B02 alone changes: recovered M5 rows 389/390 challenge ineffective testing and repeat changed-area/script-first/smoke rules already linked by the old TEST-FOCUS/TEST-PROTOCOL items. They add two returns; the old November opening adds one more when correctly treated as a renewal. No page Send is added twice. Treating the November evaluation as a separate goal instead would leave the old total unchanged; this boundary sensitivity is explicit in the judgment ledger.
The other joins were rejected on object and cohort, not keywords: welcome-email waiting is not the rally-instruction email; save-success-to-chat is not optional saving; time-slot visibility is not departure-field publication. Earlier October board/cleanup requests do not silently expand the later hourly-reminder or three-Mac inventory paths. Each existing row lists its considered chat IDs and reasons.

| Additional chat path | Size | Returns / par | Words / days | Opening / acceptance |
|---|---|---:|---:|---|
| B13 Prepare a client-facing delivery proposal and payment terms | medium | 4 / 3 | 1,974 / 0.51 | yes / no |
| B15 Choose a free font close to the existing logo | small | 0 / 3 | 35 / 0.00 | yes / no |
| B16 Export chapter names, locations and descriptions as a CSV | small | 0 / 2 | 112 / 0.00 | yes / no |
| B17 Document supported navigation behaviour on in-car displays | medium | 8 / 2 | 321 / 0.01 | yes / no |
| B18 Prepare a build-ready delivery plan and coordinator handoff | medium | 6 / 2 | 1,463 / 0.22 | yes / no |
| B19 Reevaluate secure chat with usable recovery across native and web apps | large | 8 / 2 | 874 / 1.01 | no / no |
| B22 Restore member-web sign-in by Google and emailed code | small | 1 / 2 | 126 / 0.17 | yes / yes |
| B23 Make one current, usable meeting list with direct action links | small | 4 / 2 | 1,220 / 0.06 | yes / no |

Additional paths have 7 clear openings and 1 clear acceptance, B22: the owner confirms both web sign-in methods work, then raises a distinct logout defect. B15/B16 contain only their originating requests: zero returns does not mean completion. B19 explicitly resumes prior research, so its originating opening is unclear. Size is judged requested scope: B19 includes native/web integration, recovery, capacity and comparative validation; the observed discussion span is not effort.
Only bounded artifacts/repairs with chat evidence were added. Rejected additional candidates: the broad component-selection programme, admin speed/stability repair, live-pin transport choice and October board/workspace cohort all have known page threads and cannot fairly be called chat-only additions. Later implementation decisions are not automatically charged to an earlier research document. No positive object-specific page-Send join is asserted for the additions; this is a source limit, not proof that related pages never existed.

| Cause | Old pages | Existing old → new | Added chat paths |
|---|---:|---:|---:|
| `his_decision` | 46 | 46 → 46 | 15 |
| `sent_back_intent` | 18 | 18 → 19 | 4 |
| `sent_back_quality` | 11 | 12 → 13 | 3 |
| `not_needed` | 9 | 9 → 9 | 0 |
| `his_change` | 6 | 6 → 6 | 5 |
| `status_or_nudge` | 6 | 15 → 16 | 2 |
| `relay` | 2 | 2 → 2 | 1 |
| `tooling` | 3 | 7 → 7 | 1 |

The causes overlap rather than reverse: owner decisions are 46/101 (45.5%) on old pages and 15/31 (48.4%) in the added chat paths. Changed wishes are 6/101 versus 5/31. The extra recovered B02 chat turns are both corrections. These are different selected goals and dates, so this is not a causal channel comparison.
What he types differs in form: chat supplies original requests, scale/threat-model assumptions, directions for other helpers and long corrections; pages often return a bounded choice. Added chat returns average 94.0 submitted words versus 61.7 on old pages. This includes pasted prose, not measured personal composition or keystrokes. The full screened chat also shows repeated operational nudges (rows 320/321/398/406), but those excluded cohorts are not smuggled into the cause totals.
Opening coverage is qualitative, not a percentage: known-but-unstated load, privacy and visual preferences; facts nobody yet knew about integration, recovery and runtime failures; and explicit instructions left unused. B02 row 390 already states the test split later repeated in November. B23's opening already asks for a simple, current handover list, yet rows 752/754 must reject missing ownership, stale items and duplicate tracking. Later security compromises and payment/layout revisions are changed wishes, not retroactive briefing omissions.
Submitted words total 14,389: 8,264 on recounted paths and 6,125 on additions. All use whitespace splitting with page choice labels already removed and recognized machine wrappers stripped from new chat; this differs from the first report's tokenizer. Minutes and per-goal tokens remain unknown, never inferred from elapsed days. Par remains two plus showing-dependent taste forks; aggregate excess 103 is diagnostic, not measured avoidable work.

The worst paths by recounted returns, told in five lines each:

B03 — Recurring board upkeep: 30 returns / par 2, 11.10 observed days.
The owner repeatedly identifies false blockers, stale work and scripts that report rather than act.
Cadence, durable routing and coordinator continuity keep returning after earlier decisions.
Earlier October housekeeping is an antecedent, not silently added to this later requested system.
No bounded acceptance survives; page IDs and every retained Send remain in the replacement row.

B11 — New workspace inventory: 23 returns / par 2, 4.08 observed days.
An explicit new inventory across the Macs is followed by repeated pushes to perform approved cleanup.
Custody, rescue branches and incomplete removal remain live choices and corrections.
The earlier build-file and October worktree cleanup concerns do not establish this new inventory opening.
No owner accepts the whole result; helper receipts are not substituted for acceptance.

B02 — Efficient testing: 10 → 13 returns / par 2, 16.55 observed days.
The chat reveals the scripted changed-area/smoke rule before the former November opening.
Later testing proposals therefore repeat an available requirement rather than merely discovering an unstated preference.
The renewed request is counted as a return; repeated restart/handoff failures remain separate tooling cycles.
Approval of a trial is not acceptance of measured speed, coverage or cost.

V audit: read all 50 seeded random source rows; 0/50 extraction/source mismatches (0%). The same sample contains 11 clear machine/control inputs despite the original human label, 27 unattributed retries and 12 owner-shaped rows. Source fidelity is not cause-label or authorship accuracy.
V second pass, seeded random existing paths plus additional paths: B07=9, B10=12, B04=1, B17=8, B23=4, B19=8; every count differs by zero. Reread source page-member texts and retained chats and regrouped original event IDs, not publications or cards. Same researcher; this is reproducible recounting, not independent goal-boundary agreement.
Source manifest, candidate screen, explicit inclusion/exclusion judgments, audit decisions and the second-pass source pack are in `DATA/goals/b2-working/`. The frozen snapshot is deduplicated against M1 by the upstream extractor; no other Mac, live page, board or configuration was changed.
What the chat changes: it supplies some initial requests and one explicit repair acceptance, but does not complete the existing page-heavy paths. The largest correction is to trust in the human-origin label, not a hidden flood of owner returns. Carry prior outcome-specific rulings forward, distinguish retry machinery from owner attention, and record acceptance of a named object separately from permissions.
Limits: purposive goals; incomplete opening/acceptance histories; uncertain one-word retries and sender identity; no complete object-to-page/worker joins; no attention timer. Related page evidence for excluded additional candidates is not counted. These limits prevent a population median, literal typed-word total or causal improvement claim.
