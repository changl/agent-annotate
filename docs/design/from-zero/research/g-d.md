# Project D: cycles per goal

**12 goals; 221 observed returns; median 9, range 1–55; diagnostic par 28.** Ten goals have no observed acceptance. One ends with a vocabulary agreement; another ends because the person does the task himself. These are lower-bound paths, **not a completed-goal baseline or a measured saving**.

| Goal | Size | Returns / par | His words | Calendar days* | Linked sessions | Endpoint |
|---|---|---:|---:|---:|---:|---|
| D01 Partner prospect database | medium | 10 / 2 | 348 | 0.469 | 1 | Unaccepted |
| D02 One hundred complete leads | medium | 7 / 2 | 563 | 6.127 | 2 | Partial delivery, then rejected |
| D03 Clear grading names | small | 4 / 2 | 264 | 0.848 | 1 | Vocabulary locked only |
| D04 One complete future schema | large | 54 / 4 | 3,985 | 20.072 | 10 | Unaccepted |
| D05 Reliable reusable feedback loop | large | 50 / 4 | 3,149 | 22.128 | 13 | Unaccepted |
| D06 Qualification and scoring facts | medium | 4 / 2 | 300 | 0.540 | 1 | Requested detail still missing |
| D07 Usable test leads | large | 55 / 2 | 2,577 | 19.095 | 8 | New plan requested |
| D08 Three-state counts | small | 8 / 2 | 504 | 0.117 | 1 | Used for next action; no explicit acceptance |
| D09 Move session to project group | small | 1 / 2 | 25 | 0.008 | 1 | Person completes it himself |
| D10 Recover interrupted sessions | medium | 11 / 2 | 451 | 2.008 | 2 | Interruptions recur |
| D11 Stop recurring hook errors | medium | 11 / 2 | 421 | 11.565 | 7 | No final confirmation |
| D12 Restore native updates | medium | 6 / 2 | 298 | 1.512 | 1 | Next update still fails |

*Days run from first statement to the bounded endpoint or last linked message; open paths are censored. Sizes describe the requested scope, not a measured effort estimate. Sessions overlap across goals: 29 distinct linked sessions, a lower bound on all helpers involved.

The person supplied 12,885 words including first statements: median 436 per goal, range 25–3,985. Words include selected answer labels and pasted evidence; they are not keystrokes. **Minutes per goal are unknown**: gaps between messages do not establish reading, typing or thinking time. Goal token totals are also unknown; overlapping session and worker counters cannot be allocated without double counting.

| One dominant cause per return | Count |
|---|---:|
| `his_decision` | 45 |
| `sent_back_intent` | 27 |
| `sent_back_quality` | 63 |
| `not_needed` | 20 |
| `his_change` | 8 |
| `status_or_nudge` | 19 |
| `relay` | 14 |
| `tooling` | 25 |

The 90 intent/quality returns are direct evidence of repeated corrections. The three largest paths contain 159 of the 221 returns. Eleven goals exceed par; summed positive excess is 194 (net excess 193, because D09 ends below par). This comparison is descriptive: unfinished work and changed scopes prevent treating excess as attainable savings.

Par is 2 plus one per sketch-dependent taste decision. D04 adds graphical-map and tabbed-relationship presentation; D05 adds marker placement and stable control layout. Technical implementation choices, eligibility rules, deployment permission and known presentation preferences do not add taste allowances. These four taste allowances are researcher judgements, not recorded pre-work agreements.

A return means one typed message or one attributable sent answer round; an answer containing several choices is one return. The initiating statement is held separately, because work has not yet returned. Including those twelve statements instead gives 233 interactions, median 10, range 2–56. Each message is charged once to its dominant goal, including mixed requests; secondary context is retained without a second charge. Repeated briefs to independent helpers remain separate interactions.

The first statements were uneven, but a longer first statement would not have prevented most visible repeats. D02 already named the count, every column, enrichment route and double review; subsequent output still lacked usable contacts. D06 already requested all lead types, qualification facts and scoring; the person repeatedly received other material. D04 initially omitted the four hubs, examples and migration mapping; later failures ignored those directions after they were explicit. D05 initially omitted stable URLs, versions and threads, then enumerated them; later returns repeat missing or regressed features. D08 omitted whether state meant residence or company location and needed an immediate clarification.

Each goal row separates missing preferences, facts nobody knew before inspection, and existing directions the helper failed to use. Coverage against a **finally accepted** result cannot be expressed honestly as a percentage for the ten unaccepted goals; the retained assessment compares the first ask with the observed requested scope instead.

The three worst paths, five lines each:

D07 — 55 returns against par 2 over 19.095 days; no acceptance.
The first ask sought a few hundred cleaned leads under supervision; independent efforts were later consolidated.
Reports, inventories and worker closures repeatedly replaced the requested usable outputs; 17 quality and 8 intent returns followed.
Full contact values, separated fields and existing enrichment had to be requested again; the target later changed to two lead types and state cells.
The last message requests a fresh plan before more workers: `m1max:019f95ed-6c31-7691-ae5d-b69441c36d9b:d8d6e410ecb5:83`.

D04 — 54 returns against par 4 over 20.072 days; no acceptance.
A diagram request grew into a unified schema with worked examples and current-to-target mapping; these are legitimate additional directions.
Later versions lost content, replaced the full specification with diagrams, or treated a shared target as separate targets: 12 quality and 10 intent returns.
Restoration and handoffs became part of the work; the last transfer contacted the wrong responsible helper.
Bounds: `m1max:4a6ad759-893e-43c1-ac6b-5b130e25511b:6f309a38a999:13` through `m1max:019f69d4-f0d3-7d61-8601-d0d6a72dd799:e76c361b0392:5`.

D05 — 50 returns against par 4 over 22.128 days; no acceptance.
The person wanted comments readable by helpers and one reusable feedback loop, later spelling out six capabilities.
Broken tabs, missing reply/version controls, stale markers and invisible feedback recurred: 18 quality returns and 12 tooling returns.
Praise for improvements and approval to extract agent-annotate are partial decisions, not acceptance of the whole loop.
Bounds: `m1max:4a6ad759-893e-43c1-ac6b-5b130e25511b:6f309a38a999:23` through `m1max:9d4210a3-2ef1-40da-a429-0ece67219ec8:8e997a7daf3a:28`.

The design implication is to preserve the complete agreed object across revisions, check the actual consumer result before claiming completion, and keep one visible owner for delivery and recovery. More helpers alone did not prevent the person becoming the checker, relay and stall detector. These observations support those mechanisms; they do not prove a new method would achieve par.

Sources and exclusions: the frozen snapshot has 429 human-labelled turns in 57 sessions, June 8–August 4: 166 in June, 252 in July, 11 in August. This corrects the narrower date impression in the assignment. All requested local source files existed; no second-host corpus file existed at start, and none was awaited. Board items and structural goal candidates had no direct project match; 12 task rows mentioned it but lacked a reliable human-goal join. Local review records contain 110 project questions and 89 sent rounds, including later work and copied records from both hosts; no other Mac was contacted.

Twenty schema-page push timestamps survive with counts but without answer payloads. They could concern content or interface work; no cause is invented, so they are retained as unresolved gaps rather than counted as zero. Other page rounds belong to rejected or later scopes. Anonymous answers, individual accepted cards, successful helper reports and permission to proceed are not promoted to whole-goal acceptance. The 221 total is consequently incomplete even where typed chronology is clear.

Rejected goal families, with row lists and reasons in DATA: overlapping historical classification audits (no single bounded end); early page prototypes (before the reusable-tool goal); initial financing research (sample cap); raw retention/cloud archive work (different scope); two independent ontology efforts (explicitly separated from the primary schema); later qualification reassessment (different scope); and unrelated environment, session, account-seeding and display requests (separate tasks or missing endpoints).

Audit: seed 20261112 selects 50 of the 429 human-labelled rows. Manual origin review finds 3 clear machine inputs (6%), 1 uncertain probe (2%), and 46 plausible human rows; this is a sample error rate, not a corrected population estimate. Source checks verify 44 exact texts and 6 extracted answer records: 0/50 text/source mismatches. Across the full selection, 29 dispatch/automation-style inputs, 5 unresolved-origin probes and 1 secret-redacted row are excluded; 233 rows enter the twelve goals and 161 are outside the selection. Random same-researcher recount of D04/D09/D12 gives 54/1/6 again, all differences zero; this is not independent validation.

Reproduce from DATA: `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/`. Run separately: `nice -n 19 python3 goals/d-work/extract.py`; `nice -n 19 python3 goals/d-work/inspect.py objects`; `python3 goals/d-work/inspect.py audit`; `nice -n 19 python3 goals/d-work/build.py`; `nice -n 19 python3 goals/d-work/check_sources.py`; `python3 goals/d-work/recount.py`; `python3 goals/d-work/verify.py`. The manual boundaries/causes are in `spec.py`; output is `goals/d.jsonl`. Frozen-input hashes, source checks, all row dispositions, excluded page rounds, manual audit labels, recount packets and results are retained under `goals/d-work/`. These commands replay arithmetic and source checks; human labels are retained judgements.
