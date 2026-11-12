# P2 — How work stalls: M5 Max

**79 additional cases; 71 first recorded as noticed by him (89.9%); 138 distinct owner-style message rows.** Together with M1: **166 cases, 149 noticed by him (89.8%).** This is a lower bound selected largely through his corrections, not a population failure rate.

The frozen M5-only snapshot contains 1,748 human-labelled turns and 6,713 session records. Mac means capture host; one event may affect several projects or machines. Repeated nudges and continuing repairs are grouped, with one primary M1 kind per event; no new kind was needed.

## M5 census and earliest readable signal

Durations cover only four explicitly reported waits; onsets are approximate. A dash means unmeasured, never zero. “Him” means first recorded detector, not proof that nobody else knew.

| Kind | Cases | Timed | Median h | Longest h | Him | Signal and earliest check |
|---|---:|---:|---:|---:|---:|---|
| Silent stop | 11 | 3 | 1.83 | 2.67 | 54.5% | Error plus unfinished assignment at turn end; overdue artifact check catches a silent exit. |
| Waiting on nobody | 0 | 0 | — | — | — | No additional proven orphan wait; real deployment/test queues were not counted. |
| Waiting on him without telling him | 0 | 0 | — | — | — | Not established: the snapshot cannot show what he knew; visible asks do not prove a hidden approval. |
| Lost message | 5 | 1 | 0.44 | 0.44 | 100.0% | Queued question, wrong page owner or unarmed listener at send/idle; verify receiver acknowledgment. |
| False finish | 19 | 0 | — | — | 100.0% | Claim versus actual user path at the claim: signed-in mutation, exact image, guided mode or live URL. |
| Lost memory/instruction | 2 | 0 | — | — | 100.0% | Saved ruling versus successor prompt/artifact at takeover; compaction causation is unproved. |
| Drift | 17 | 0 | — | — | 100.0% | Requested scope versus first artifact; also product progress versus repeated administrative handoffs. |
| Collision | 0 | 0 | — | — | — | No additional independent edit collision established; ownership and ledger incidents have primary kinds above. |
| Machine trouble | 9 | 0 | — | — | 77.8% | Failed mount/service/hook/route/signature check at operation or boot; probe with a bounded external process. |
| Premature handback | 6 | 0 | — | — | 100.0% | Open authorized acceptance work plus final response at turn end. |
| Stale tracking | 4 | 0 | — | — | 75.0% | Board/PR status versus real owner and artifact at state change; recognize PAUSED as well as DONE. |
| Blocking question | 0 | 0 | — | — | — | No additional proven downstream freeze joined to a visible question; long ask latency alone is insufficient. |
| Resource starvation | 0 | 0 | — | — | — | No additional assignment established beyond M1 receipts; busy devices and legitimate cutovers are not starvation. |
| Excessive wakeups | 2 | 0 | — | — | 100.0% | Heartbeat-only mail and repeated no-change turns as they accumulate; cancel the source. |
| Needless wait | 2 | 0 | — | — | 100.0% | Ready independent work versus dependency gate at scheduling; distinguish delivery from preparation. |
| Finished workers retained | 2 | 0 | — | — | 100.0% | Final receipt with retained monitor/lead and no next assignment at settlement. |

**Cost covered:** 138 distinct message rows (138 normalized texts). The four waits sum to **5.69 case-hours**: three capacity-error idles of about 1.83, 2.67 and 0.75 hours, plus a queued store grant of about 0.44 hours. Parallel waits overlap; 75 cases have no measured duration. Human effort, productive time lost and total redo-hours cannot be recovered. Redo is directly evidenced by restored UI, regenerated images, repeated deploy repairs and replacement workers.

A plain clock needs an owner, deadline and independent artifact/service check: it can flag silent exits, queued messages, unserved pages, stale tracking, retained sessions and repeated no-change wakes. Watching the watcher matters: one coordinator only woke for alive pings while an access question waited in its queue (M5P069).
False finishes, scope drift and lost instructions need another helper comparing the request, saved rulings and the exact delivered result. A clock can flag zero product progress during a handoff loop, but cannot decide whether a product hold is authorized. Successful tests or an HTTP redirect do not prove the authenticated user path (M5P029/M5P031).
Nothing here can establish an unrecorded intention, what he did not know, or an exact mental/time cost. No “nobody noticed” count is defensible from messages selected because somebody returned to them.

## Five worst cases — delivery damage and recovery, not a fabricated time ranking

**M5P059 — Project B: a handoff loop with no product workers.**
Coordinators 3–16 and build leads 17–28 repeatedly transferred ownership; a contemporaneous freeze reported zero merges since about 15:10Z.
The report at 22:24Z gives a 7.25-hour no-merge observation window, not 7.25 proven lost hours; the owner stopped the loop.
Evidence: session 01a0f455-89c8-7c42-8d71-442a60b3cee6, row 4b276225e066:2; all supporting full row IDs are in DATA/stalls/m5/events.jsonl.

**M5P003 — Another project: a frozen share multiplied process hangs.**
A wedged SMB client blocked the agent group and Orca shutdown; a later check reported 632 stalled process probes and 44 other stuck processes.
The owner returned repeatedly; reboot and session restoration were required. Duration is unknown; a continuously connected network did not prove the share usable.
Evidence: session 44f838bb-2d19-405c-88c1-210715f7fbed, row 2f39bca9db83:3; all supporting full row IDs are in DATA/stalls/m5/events.jsonl.

**M5P031 — Another project: deployed fixes left the signed-in flow broken.**
Three claimed document fixes still left dropdowns and deletion failing, despite tests and deployment readiness checks.
The owner demanded proof and stopped further changes; another agent took over. Duration and redo-hours are unknown.
Evidence: session 019e9b4f-f1ed-7232-945e-1286f4ea04c1, row 9ab48dae6674:17; all supporting full row IDs are in DATA/stalls/m5/events.jsonl.

**M5P052 — Project C: source-checked replacements were the wrong images.**
Two storefronts received incorrect product profiles; the owner also found missing transparent replacements after reported catalog-wide checks.
Seven wrong files remained online; ten tracked replacements were retired and earlier acceptable revisions restored. Duration is unknown.
Evidence: session 01a0eb51-81b0-71d2-af58-1308bb055d0d, row 194f4537c7ca:91; all supporting full row IDs are in DATA/stalls/m5/events.jsonl.

**M5P045 — Another project: a UI restoration missed the mode being reviewed.**
The guide changed the underlying native UI despite the preservation rule; restoration proved the unguided form while the guided form stayed altered.
The owner rejected the result, requested a new session and required a takeover package; duration and total discarded work are unknown.
Evidence: session 01a081c1-2a76-7b83-941d-a42421ed8de9, row dd2ee856075d:15; all supporting full row IDs are in DATA/stalls/m5/events.jsonl.

## Coverage, exclusions and reproduction

The unchanged M1 screens found 980 primary and 462 secondary hits (1,442 total). Context review retained 79 case groups supported by 152 candidate rows and explicitly rejected 31 possible-case groups; 1,290 screen hits were not promoted. Rejections include a completed build waiting for a real cutover, a test already running, a cached old gallery, a withdrawn attribution and a purported freeze whose later feedback had actually been processed.
The session screen found 569 explicit API errors in 45 records, 28 running-gap markers in 20 records, and 1,054 compactions. These are signals, not additional failures. Two rate-limited worker assignments alone contribute 482 errors and 314 human-labelled “continue” rows; their task IDs match M1 P096/P098, so neither incidents nor retry rows are added again. The M1 mail total and M5 error total are different observations, not interchangeable alarm counts.
Cross-mac-overlap.jsonl also conservatively excludes possible antecedents/corroboration of M1 P038 (crash recovery), P063 (hooks) and P070 (updater). Shared task/mail inventory was already covered by M1; it was not added again. The final table adds the unchanged 87 M1 cases to the 79 new M5 cases after these exclusions.
Extraction check: read 50 seeded random human-labelled rows (seed 20261112). **13/50 (26%) are unmistakable machine/scheduled directives**; ten more are bare retries in the two error loops, plus one other authorship-ambiguous “continue”. These were not treated as authenticated human effort. 202 joins to frozen source rows passed with 0 transformation mismatches; this does not validate the original extraction. No M5 raw transcript path exists on this Mac, so original-line checks and M5 memory-note verification were unavailable; no other Mac was accessed.
Reproduce, separately: `nice -n 19 python3 /Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/scripts/p_stalls_m5.py analyze`, then the same command ending in `report`. The extension reuses p_stalls_scan.py screens/seed/secret filter and p_stalls_analyze.py kinds, aliases and interval helper; p_stalls_rawcheck.py was inspected but cannot run against absent M5 files. It adds credential-command redaction, frozen-row checks and explicit reviewed grouping. Script hashes, snapshot hash and all counts are in DATA/stalls/m5/summary.json; decisions and overlaps are retained alongside events. Only DATA and this findings file were written; no runtime, page, board or git history changed.

## Both Macs, added by the same primary kind

Shares are computed from case-level detector counts, not by averaging the two percentages. The M5 additions contain no new script-first detections; eight were first recorded by another helper. Zero means no additional case established in this bounded evidence, not that the failure never occurs.

| Kind | M1 Max | M5 Max new | Total | First noticed by him |
|---|---:|---:|---:|---:|
| Silent stop | 8 | 11 | 19 | 52.6% |
| Waiting on nobody | 2 | 0 | 2 | 50.0% |
| Waiting on him without telling him | 0 | 0 | 0 | — |
| Lost message | 9 | 5 | 14 | 92.9% |
| False finish | 14 | 19 | 33 | 100.0% |
| Lost memory/instruction | 5 | 2 | 7 | 100.0% |
| Drift | 15 | 17 | 32 | 100.0% |
| Collision | 4 | 0 | 4 | 100.0% |
| Machine trouble | 14 | 9 | 23 | 91.3% |
| Premature handback | 7 | 6 | 13 | 100.0% |
| Stale tracking | 3 | 4 | 7 | 85.7% |
| Blocking question | 1 | 0 | 1 | 0.0% |
| Resource starvation | 2 | 0 | 2 | 0.0% |
| Excessive wakeups | 1 | 2 | 3 | 100.0% |
| Needless wait | 1 | 2 | 3 | 100.0% |
| Finished workers retained | 1 | 2 | 3 | 100.0% |
| **All** | **87** | **79** | **166** | **89.8% (149/166)** |
