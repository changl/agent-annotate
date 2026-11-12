# G-F — Cycles in the smaller projects

**12 goals across Project F1–Project F8; 81 observed return messages; median 5.5, range 1–16; nominal par 28 in total. Only 2 have explicit, limited-scope acceptance.** These are observed-path counts, mostly lower bounds, not a completed-goal performance baseline. Nine paths already exceed par. Seven sampled scopes are small, five medium; no defensible accepted weeks-long goal was found.

The frozen snapshot contains 473 human-labelled messages in these project groups. Twelve retained conversation sessions support the selected paths. Eleven goals stay within one conversation; branding crosses two. This counts retained conversations, not every helper behind them. Selection deliberately includes failures and is not a random estimate of typical work.

| Goal row | Project | Goal | Size | Returns / par | Words, including first request | Days observed | Accepted |
|---|---|---|---|---:|---:|---:|---|
| F1-1 | Project F1 | Responsive main-screen mockup | Small | 8 / 3 | 506 | 0.029 | No record |
| F1-2 | Project F1 | Consistent theme override | Small | 4 / 2 | 124 | 0.058 | No record |
| F2-1 | Project F2 | Three usable brand finalists | Medium | 13 / 5 | 1,009 | 2.136 | Pairings selected; whole system unaccepted |
| F3-1 | Project F3 | Upgrade and weekly self-update | Small | 2 / 2 | 95 | 0.005 | Schedule approved; result unaccepted |
| F4-1 | Project F4 | Remove old memory system | Small | 7 / 2 | 712 | 0.075 | Removal only |
| F4-2 | Project F4 | Install replacement and connect clients | Medium | 16 / 2 | 446 | 0.846 | No record |
| F5-1 | Project F5 | Free remote assistant and command tools | Medium | 12 / 2 | 309 | 0.961 | Logins completed; delegation unaccepted |
| F6-1 | Project F6 | Persistent embedding service | Medium | 5 / 2 | 143 | 0.420 | No record |
| F6-2 | Project F6 | Usable remote web interface | Medium | 5 / 2 | 193 | 0.705 | No record |
| F7-1 | Project F7 | Document to complete scorecard sheet | Small | 1 / 2 | 99 | 0.017 | No record |
| F7-2 | Project F7 | Research claim: practical merit | Small | 2 / 2 | 408 | 0.455 | No record |
| F8-1 | Project F8 | Fast local terminal dictation | Small | 6 / 2 | 439 | 0.038 | Application works so far |

Goal IDs identify rows in `DATA/goals/f.jsonl`; each carries complete corpus row IDs, timestamps, first words, returned context and one cause per return. Days end at acceptance or the last relevant human message, not the helper's final report. Words total **4,483**, median **358.5** per goal; return messages alone contain **3,242**. They are whitespace word counts after ambient browser context removal, not keystrokes. **Minutes are null for every goal:** no reading/typing observation supports a defensible estimate, and waiting time is not attention.

| Sole cause of return | Count |
|---|---:|
| `his_decision` | 27 |
| `sent_back_quality` | 17 |
| `sent_back_intent` | 12 |
| `not_needed` | 10 |
| `tooling` | 8 |
| `his_change` | 3 |
| `status_or_nudge` | 3 |
| `relay` | 1 |

A return is a subsequent human message that sends this goal onward, including acceptance; the initiating request is recorded separately. Consecutive messages remain separate. New goals embedded in acceptance messages are split at the explicit topic change. Structured-choice answers already emitted as human turns are not counted twice. No page Send round could be joined to these selected scopes; unrelated pilot rounds are excluded.

Par is 2 plus one showing-dependent taste decision for the main-screen layout, or three for brand symbol, wordmark and palette. All other goals have par 2. **81 versus 28 does not prove 53 wasted cycles:** most paths are unfinished, technical configuration questions were sometimes explicitly requested, and real authentication/capacity constraints remain. Cause labels are judgments, not a causal experiment.

What the first statements lacked:

- Project F1: workflow priority and acceptable density emerged through reaction, but the central communication purpose was already in the preceding audit. The theme request already covered all affected screens.
- Project F2: desired character and specific visual taste were initially unstated; professional grounding, self-review and candidate limits were explicit. Later references were not carried reliably between helpers.
- Project F3: scheduling inside the service and its maintenance window were missing. The first was clarified after a host-side recommendation; the second was a legitimate owner decision.
- Project F4: operational configuration preferences were missing, often deliberately left for questions. Removal-first sequencing and existing tracking context were available; a maintained adapter should have been researched before proposing custom work.
- Project F5: compute size was initially unstated; capacity and region limits were unknowable beforehand. Subscription use and usable command tools were already requested.
- Project F6: the initial model-swap direction was ambiguous and persistence unstated. Web-interface reachability and updater behavior needed actual use checks.
- Project F7: the sheet's unified, atomic information model was unstated; the research question already explicitly asked about practical merit rather than mere existence.
- Project F8: meetings and speaker separation were added during work. The initial dictation need was clear. No numeric coverage percentage is defensible without an agreed atomic acceptance list; both accepted scopes remain narrower than the surrounding conversation.

The three highest-count paths, five lines each:

Project F4 replacement setup: **16 returns against par 2**, with no final acceptance.
The owner invited configuration questions; database, models, retrieval and clients legitimately required choices.
The helper also reversed usage advice, requested repeated credential approval and offered custom integration before researching maintained choices.
The owner finally asked whether everything was done; the helper still lacked the agreed end-to-end memory check.
Evidence: `m1max:01a0933d-6ec5-7c01-b8b6-fb063133551a:716fac4f03e5:15` through `m1max:01a0933d-6ec5-7c01-b8b6-fb063133551a:716fac4f03e5:32`.

Project F2 branding: **13 returns against par 5**, over 2.136 observed days.
The first request explicitly required research, self-review and a small finalist set; weak initial work made the owner repeat that brief.
He switched helpers, supplied references again and repeatedly rejected wordmarks and unintended alterations.
He eventually selected three pairings; applied palettes/fonts were requested next, with no acceptance of the whole result.
Evidence: `m1max:01a0bc3d-322b-7780-82ea-c42f8914530f:bc335cf9db06:1` through `m1max:01a0c211-b1cd-79b1-a9b1-9c1f2ca90c81:9e9de1bd9e92:11`.

Project F5 remote setup: **12 returns against par 2**, over 0.961 observed days.
The free-only boundary required a real cost decision; capacity failures led to successively smaller shapes and region choices.
The owner personally obtained the machine and completed private logins; those are external constraints, not automatically poor helper judgment.
Installed commands then failed in his shell, and unexplained version output produced another exchange; full delegation remained unaccepted.
Evidence: `m1max:019df9c0-e86e-7d91-b563-5b033c29d430:2722ae2d22a5:1` through `m1max:019df9c0-e86e-7d91-b563-5b033c29d430:2722ae2d22a5:24`, excluding separately requested messaging/browser/calendar work.

Compared with the large-project records in `d4-goals.md`, the dominant visible loop here is direct conversation → attempted result → personal correction, rather than a board item moving through a worker fleet. That removes much relay, but does not remove intent or proof failures: **29 returns concern mismatched or unfinished work**. Several small tasks grow through discovery; making an elaborate project structure first would not have settled those choices.

The premise “no board, no page, one helper” is only partly supported. No matching board-item or structural-goal rows were recovered for these aliases, but Project F4 explicitly uses an existing issue tracker, Project F3 has recorded review pages, and some conversations invoke other helpers. The reliable contrast is fewer visible coordination layers in the selected paths, not an absence of infrastructure. A short durable goal record, carried preferences and a real-client check would address the observed gaps without requiring the owner to set up a full project first.

Rejected candidates: full demo readiness/ticket migration; transactional email; scope review; prototype/job inventory review; weeks-long workflow redesign; separate embedding preservation; messaging/calendar/browser extensions; motion-graphics website; earlier memory rollout; cleanup/machine coordination; speech-output router/video companion. The 11 source-linked entries in `DATA/goals/f-rejected.jsonl` explain mixed goals, missing closure, uncertain authorship or secret-redacted first words. Weeks-long conversations contain several newly introduced goals; counting them as one accepted goal would manufacture the requested large-size stratum.

Quality: read **50 seeded random human-labelled rows**, finding **1 clearly machine-written row (2%)** and 2 pasted-message authorship uncertainties. The definite error is outside the counted paths. A supplemental credential screen suppressed one rejected first-statement row. This checks origin/plausibility, not completeness or cause-label accuracy. A second source-window pass on randomly chosen F3-1, F6-2 and F8-1 reproduced **2, 5 and 6 returns**, all exact; it was the same researcher, not an independent rater. Decisions and recount evidence remain in DATA.

Sources: frozen `DATA/wave2/m1max-snapshot.jsonl`; schema and all requested questions/rounds/items/tasks/goal-candidate files existed. Selected project fields expose 51 questions, 6 rounds, 89 tasks and 8 pages, but none supplies an additional joined acceptance cycle for the sampled goals. The M5 corpus was absent at initial inspection. Missing: whole-goal acceptance for 10 paths, active-attention minutes, goal-level token use, proof of all hidden helper sessions and a defensible weeks-long accepted goal. Session token counters are retained without allocating them to overlapping goals.

Reproduce from DATA, each command separately: `nice -n 19 python3 scripts/goal_f.py prepare`; `python3 scripts/build_goal_f.py`; `python3 scripts/goal_f.py analyze`; `nice -n 19 python3 scripts/goal_f.py inventory`; `python3 scripts/goal_f.py audit`. Generated summaries are `goals/f-summary.json` and `goals/f-inventory.json`; manual QA is `goals/f-audit-decisions.json` and `goals/f-recount.json`. Sample seed is 20261112. `goal_f.py view --project N --indices I,J` replays source windows without loading whole transcripts. No products, pages, boards, settings or other Macs were changed.
