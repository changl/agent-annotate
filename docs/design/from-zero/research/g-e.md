# Project E — observed cycles per goal

**15 goals; 164 observed cycles; median 5, range 2–33; par totals 31. Only 2 goals have explicit acceptance evidence.** The other 13 are censored: their counts are lower bounds, not completed-goal durations. The accepted pair took 6 and 4 cycles (median 5), against par 2 each.

DATA denotes the private storage root in `briefs/common-data.md`. Frozen input: `DATA/wave2/m1max-snapshot.jsonl`; 182 human-labelled messages, 21,645 words. The scoped messages run May–November; no April human message survives this snapshot. The second-Mac corpus was absent at start. Ancillary sources existed: 18 project questions, 2 Sends, 53 tasks and 11 handoffs; no project board items or goal candidates. No other Mac was read.

A cycle is one owner message or explicit page Send, including the first statement and acceptance. A multi-question Send counts once; injected notifications count zero. Each message belongs to one goal, with one dominant cause. “Owner decision” includes initial direction and acceptance; later mixed messages get their main cause, so this is a judgement-based taxonomy.

Goals include enabling workflow work filed under this project’s transcript label. Boundaries follow the owner’s requested outcome, not individual PRs or every change of session. Sizes describe observed hours/days/weeks, not effort estimates.

| Goal | Size | Cycles / par | Message words | Observed days | Acceptance |
|---|---|---:|---:|---:|---|
| E01 Refine the shared orchestration design | medium | 31 / 2 | 2,577 | 4.395 | Unobserved |
| E02 Choose compatible shared memory tools | small | 4 / 2 | 517 | 0.048 | Unobserved |
| E03 Validate and tighten the CI hardening plan | small | 4 / 2 | 184 | 0.037 | Unobserved |
| E04 Create and install the writing aid for both agents | small | 3 / 2 | 31 | 0.009 | Unobserved |
| E05 Unblock operator setup for the build | small | 9 / 2 | 830 | 0.093 | Unobserved |
| E06 Get valid enriched data through all pipeline gates | medium | 21 / 2 | 1,721 | 1.095 | Unobserved |
| E07 Finish the review interface ticket batch | small | 6 / 2 | 347 | 0.045 | Explicit |
| E08 Remove orphaned worktrees before restarting | small | 2 / 2 | 42 | 0.011 | Unobserved |
| E09 Make a golden corpus and compact execution contracts | small | 5 / 2 | 726 | 0.169 | Unobserved |
| E10 Review the revised contract pack for execution | small | 4 / 2 | 386 | 0.220 | Unobserved |
| E11 Finish a dispatchable pipeline planning pack | medium | 28 / 3 | 5,887 | 0.965 | Unobserved |
| E12 Plan the full commercial lead universe | small | 7 / 2 | 716 | 0.148 | Unobserved |
| E13 Review the commercial execution plan | small | 3 / 2 | 247 | 0.352 | Unobserved |
| E14 Recover and coordinate the manual ingestion comparison | large | 33 / 2 | 1,255 | 10.213 | Unobserved |
| E15 Agree a reversible backup and three-stage wind-down plan | small | 4 / 2 | 370 | 0.057 | Explicit |

Words total **15,836**, including pasted material and 189 words in the two Sends. These are message words, not keystrokes; minutes per cycle and goal are null because neither reading nor typing time is observed. Session waits cannot supply that measure. Distinct human-contact session IDs are retained per goal; worker-only sessions and overlapping session token counters cannot be safely allocated to goals.

| One cause per cycle | Count |
|---|---:|
| `his_decision` | 52 |
| `sent_back_quality` | 32 |
| `status_or_nudge` | 23 |
| `sent_back_intent` | 19 |
| `relay` | 13 |
| `his_change` | 11 |
| `tooling` | 9 |
| `not_needed` | 5 |

Actual counts total 164 against par 31; 14 goals exceed their assigned par. One extra par cycle is allowed for E11’s terminology judgement after seeing the pack. No other artifact-dependent taste fork was identified. New scope, research discoveries, permission boundaries and lost sessions also consume cycles; the difference from par cannot all be claimed as avoidable waste.

## What his long messages carried

Private owner knowledge mattered: which review helper was unavailable, which account could approve work, which data run was acceptable, what commercial scale justified the pilot, allowed outreach/spend, retention, and acceptable restart effort. E06’s first detailed reply supplied the final-lead criterion; E12 later enlarged the target universe; E14 later fixed local execution and model/reasoning scope. Those later choices should be recorded as new intent, not silently charged to the first brief.

But long messages were often transport. In E11, six pasted review messages (r110, r111, r117, r119, r120, r121) contain **4,404 words, 74.8% of its 5,887 words**; only 143 words are identifiable owner preambles under the retained delimiter rule. The detailed enum, dependency, path and fixture findings were checkable by helpers. Pasting them is still an owner cycle; it is not proof that he personally wrote those findings.

Repetition is directly visible: E06 r064 sets the alternate review/account loop, repeated at r075; E11 r099 sets full context below 20k, reiterated at r107; r101–104 repeatedly locate workflow authority in existing skills; r111’s naming request returns at r117; E14 r145 demands session management, which returns at r161, r169 and r175. The remedy is durable dispatch rules plus readback, rather than a longer owner brief.

## What the first statements lacked

E01/E05/E08/E12/E14/E15 needed genuine owner choices about scope, accounts, deletion, scale, money or risk. E02/E03/E05/E06/E10/E11/E12/E14/E15 needed investigation of facts nobody had established yet: configuration compatibility, CI behavior, live data, source yield, session state and recovery limits.

E06/E09/E11/E13 chiefly expose unused prior context: supplied specs and business-intent sources, golden examples, established workflow, context limits and exact handoff contracts. E11’s first statement explicitly required fact validation, linters and repeated independent blocker review; it did not need to restate every enum or path. E15 already asked for all-stage costs and minimal restart effort; opaque algebra and missing totals were helper presentation failures.

Per-goal coverage lists distinguish already-stated requirements, owner additions, unknown facts and existing-but-unused material. No numeric “percent of finally accepted result” is assigned: the transcripts rarely contain both a complete accepted specification and owner acceptance. Even the accepted E07 required post-merge validation; E15 accepts planning and starts a separate execution goal.

## Three paths that went worst

E14 — 33 cycles, par 2; 1,255 words; 10.213 observed days; acceptance absent.
It began with recovering prior ingestion runs and preparing a comparison baseline (r138).
The coordinator was lost, workers needed resuming, and the owner kept requesting status and closure (r140–169).
The owner narrowed execution and supplied a fuller coordination brief, then rebooted and demanded another complete accounting (r150, r175).
The final retained helper report still described blocked data/gate tracks and broken lifecycle reporting; no accepted comparison result survives.

E11 — 28 cycles, par 3; 5,887 words; 0.965 observed days; acceptance absent.
The first request was already a concrete rewrite with verified facts, linters and repeated independent review (r096).
The pack omitted inputs, invented workflow, retained naming drift and left contract/fixture contradictions (r098–121).
The owner relayed six long reviews, restated scope and paths, and pushed after reports stopped short of implementation.
The last request moves to tracker verification and an execution prompt (r123); this is a readiness transition, not explicit acceptance.

E06 — 21 cycles, par 2; 1,721 words; 1.095 observed days; acceptance absent.
The request resumed a dirty handoff and directed work toward a valid enriched final lead (r057–058).
The owner chased silent workers, repeated review authority, challenged missing evidence and asked why blockers stopped work (r060–081).
The owner eventually demanded a record-by-gate ledger and handback after little progress (r082–083).
Final success at all gates was not accepted; clean PRs and a handoff did not establish the requested end-to-end outcome.

## Audit, exclusions and reproduction

Read 50 seeded random project rows and compared each with its raw source-line payload: **0/50 text-extraction mismatches; 1/50 probable human-origin mislabels (2%)**. Across all 182, seven probable machine control/handoff rows (4,042 words) were excluded; two secret-redacted messages could not be rebuilt. Ambiguous pasted review briefs remain flagged as such. Retained audit files preserve these judgements, including r177’s origin uncertainty.

The seeded second count selected E04, E13 and E09; a second manual pass over the source interactions gave 3, 3 and 5 cycles, exactly matching. This was a same-researcher repeat with first-pass annotations available, not a blinded or independent rater. Cause labels were not reliability-tested.

The 20 rejected rows and reasons are in `DATA/goals/e-rejected.jsonl`: seven probable machine rows, two redacted rows, and eleven unselected standalone reviews/tooling/adjacent asks. Topic changes, deletion authorization, helper completion claims and silence are not owner acceptance. Broader execution and missing helper conversations may contain additional cycles.

Raw identifiers, names, source paths, cycle text, helper responses, missing-data reasons and qualitative first-brief coverage remain in `DATA/goals/e.jsonl` and supporting `e-*` files. The aliases rNNN resolve through `audit_index` in `e-source-human.jsonl` to immutable corpus row IDs. For example r058 = `m1max:019e3dc7-1c6c-72f3-bcb4-5d5c52807a78:bac106b7a7c7:5`; r098 = `m1max:019e5629-be5d-7e51-9a36-d4c352e70da0:4f2dfa684dc7:8`; r175 = `m1max:019f9d7f-0ed0-7c32-b446-8fd62fafcc48:40d066a9f5c0:44`.

Reproduce from retained data, one command at a time: `nice -n 19 python3 -I DATA/goals/e-filter.py`; `nice -n 19 python3 -I DATA/goals/e-extract.py`; `python3 -I DATA/goals/e-build.py`; `python3 -I DATA/goals/e-report.py`; `python3 -I DATA/goals/e-check.py`. The filter uses the frozen snapshot; assistant-ending re-extraction also needs the original local transcript files. Build/report/check replay the frozen retained evidence without those files.
