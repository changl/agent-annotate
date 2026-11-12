# E1 — Where the helpers' effort goes: M1 Max

**11,533 session records; 6,873 with usable token counters; 50.234 billion observed tokens, before missing cache writes.** Detailed activity: **651 sampled sessions, 108,582 tool invocations; 10.5% of allocated tokens doing work, 27.1% talking to helpers, 26.1% reading/re-reading.** These operation shares do not measure waste. (S)

**Fix the baseline before comparing designs.** The frozen snapshot reports 178.833B tokens, but child transcripts copy parent history and cumulative counters. C removes **127.650B demonstrably inherited tokens** from 373 forks; 426 forks without a reliable boundary exclude another 0.949B recorded tokens. In a child, the first metadata ID is its own, while later copied metadata can overwrite it with the parent's ID; 130 records have that mismatch. Rewritten timestamps cannot separate the history. The rule uses the first new UUIDv7 turn context after the child's birth and subtracts the preceding cumulative counter. Uncertain forks stay unmeasured; the original snapshot is untouched. (C/S)

## Coverage and totals

M1 Max only; the M5 corpus was absent when this task started and was not used. Frozen wave-2 snapshot SHA-256 and input paths are in `DATA/effort/inputs.json`. The original snapshot has token data for 7,290 records; correction leaves 6,873/11,533 (59.6%). Blank/missing counters are unknown, including 3,773 March records with no tool or token data. Roles and project assignments retain the corpus rules; “another project” pools the remainder and unresolved paths. (S)

| Project | Sessions | Usable token records | Token subtotal, billions |
|---|---:|---:|---:|
| agent-annotate | 75 | 75 | 2.737 |
| Project B | 718 | 717 | 19.327 |
| Project C | 99 | 99 | 3.036 |
| Project D | 1,505 | 1,491 | 10.573 |
| Project E | 4,686 | 3,917 | 9.280 |
| another project | 4,450 | 574 | 5.281 |

| Role | Sessions | Usable token records | Token subtotal, billions |
|---|---:|---:|---:|
| Direct | 216 | 171 | 3.726 |
| Coordinator | 90 | 90 | 16.645 |
| Worker | 8,815 | 4,659 | 20.705 |
| Subagent | 2,412 | 1,953 | 9.159 |

| Start month, UTC | Sessions | Usable token records | Token subtotal, billions |
|---|---:|---:|---:|
| March | 3,773 | 0 | unknown |
| April | 38 | 13 | 0.121 |
| May | 4,001 | 3,417 | 5.025 |
| June | 1,333 | 1,148 | 1.850 |
| July | 941 | 901 | 11.547 |
| August | 81 | 81 | 2.339 |
| September | 106 | 96 | 1.537 |
| October | 335 | 332 | 16.349 |
| November | 886 | 885 | 11.467 |
| Unknown | 39 | 0 | unknown |

All tables: S. Claude input excludes cache reads/writes; Codex input includes cache reads, which are subtracted before adding them once. Output already contains reasoning tokens. The subtotal contains 676.327M uncached/write-unsplit input, 145.865M output and 49.412B cache-read tokens; detailed rows additionally recover 380.100M cache-write tokens. No global cross-file Claude deduplication or subscription billing reconciliation was possible. Snapshot wall spans total 13,319.4 hours, including unattended gaps; explicit active durations cover only 412/651 detailed records and total 711.7 hours, so these are not a utilization ratio. (S)

## Activity and startup

Sample: up to two files from every helper/project/role/month stratum, then a seeded fill to 600; add every coordinator and the earlier-study sessions: 651 files across 258 strata, seed 20261112. Below, token shares use stratum population/sample weights; purposive supplements and missing forks prevent a probability error bound. Tool calls are the directly observed sample share. Tokens in a generation are divided equally among its operation categories; “person” also includes assistant-only prose in direct/coordinator sessions. (X/S)

| Activity | Tool calls % | All tokens % | Direct % | Coordinator % | Worker % | Subagent % |
|---|---:|---:|---:|---:|---:|---:|
| Doing work | 11.48 | 10.47 | 12.51 | 6.19 | 13.76 | 14.16 |
| Reading/searching | 25.87 | 25.60 | 27.41 | 13.62 | 37.93 | 33.63 |
| Re-reading | 0.94 | 0.50 | 1.20 | 0.61 | 0.45 | 0.07 |
| Other helpers | 27.29 | 27.14 | 1.17 | 36.90 | 18.10 | 29.33 |
| Boards/pages/notes | 9.30 | 6.08 | 2.15 | 8.80 | 6.18 | 2.09 |
| Person/prose | 0.11 | 8.42 | 5.64 | 18.39 | 0 | 0 |
| Recovery | 0.35 | 0.31 | 0.40 | 0.32 | 0.21 | 0.37 |
| Explicit idle/process waits | 4.54 | 2.70 | 7.19 | 3.04 | 2.06 | 0.99 |
| Other/mixed/unresolved | 20.11 | 18.78 | 42.34 | 12.13 | 21.31 | 19.37 |

Fixed precedence and executable rules: `DATA/effort/METHOD.md` and `DATA/scripts/effort.py`. Actual edit/build/test/mutation operations are work; actual helper controls, mail and background-helper outputs are helpers; actual board/page/named-note operations are records. Read/search operations are reading; an identical read repeated without a recognized intervening mutation is re-reading. Volatile clock/process reads never count as re-reading. Explicit errors followed by identical retries, restart commands and the next generation after compaction/API-error/continuation are recovery. Mixed wrappers and unresolved scripts remain other. Quiet-wait is helper coordination; process polling is idle. Unrecorded gaps are not assigned an activity.

Cold start ends at the first producing/mutating action, record write or final answer. Tokens include prior generations plus that action generation's input/cache tokens; output before the action is not separately metered. Seconds start at the first recorded event, corrected to child birth for forks. There are 276 records with no observed action; they are censored, not zero-cost startups. Median/p90 below are unweighted observed cases, not matched-model performance comparisons. (S)

| Helper / role | Cases with action | Tokens median / p90, thousands | Seconds median / p90 |
|---|---:|---:|---:|
| Claude direct | 20 | 208 / 974 | 28.9 / 211.0 |
| Claude coordinator | 68 | 514 / 1,379 | 108.9 / 2,420.5 |
| Claude worker | 122 | 35.7 / 739 | 7.3 / 80.1 |
| Claude subagent | 45 | 150 / 1,043 | 37.8 / 330.5 |
| Codex direct | 40 | 1,213 / 9,092 | 212.8 / 3,428.3 |
| Codex coordinator | 19 | 2,468 / 9,154 | 398.4 / 4,290.1 |
| Codex worker | 48 | 708 / 3,400 | 161.2 / 697.9 |
| Codex subagent | 13 | 1,141 / 3,406 | 503.4 / 3,851.1 |

## Coordinators, goals and money

All 90 coordinator records were read. Their detailed total, including observed writes, is 16.925B tokens and **$7,183.25 notional**; median priced session $22.50. Across 184 priced session-days, one coordinator's median daily cost is **$14.10**, p90 **$93.71**; summing concurrent coordinators instead gives $36.93 per observed calendar day at the median. Model, age and task mix vary. Cache reads are **97.7%** of coordinator tokens, but shared prompts, tools and imported context cannot be separated from its own history. This is not a measured own-history re-reading share. (S)
Observed launch-call proxies: 1,922, giving 8.81M coordinator tokens / $3.74 per launch. Result-bearing envelope keys: 3,610, giving $1.99 per envelope and 2,390/3,610 = 0.66 result-bearing observations per envelope. Bundled launches, duplicate unkeyed notices and multi-result envelopes prevent exact workers-managed or conversational-turns-per-result figures; these ratios are explicitly receipt proxies. (S)
Goals: 18 structural candidates link 29 sampled sessions; their linked-session median is 1 session / 0.534M tokens, range 1–5 sessions / 0–71.915M tokens; priced subtotals median $1.87, range $0.18–$20.56. These are incomplete and potentially shared session totals, not goal-exclusive effort. Of 80 curated goals, 61 have matching session records; whole-session envelopes have median 162.183M tokens, range 0.249M–7,582.617M. **Actual per-goal token totals and coordinator shares remain unidentifiable** because sessions interleave goals; per-row available shares and null exclusive totals are retained in the two goal output files. (S)
Recovery is **0.31% of allocated tokens / 0.60% of allocated list-price cost** after stratum weighting. This narrow count catches explicit restart/error/compaction generations, not all failed work, hidden automatic retries, summaries emitted by tools, or downstream repairs; it is a lower bound, not the total rework rate. The raw snapshot's error/compaction flags also include copied history and must not be treated as unique failures. (S)

Prices: published standard global USD per million, observed **2026-11-12**, in input/output/cache-read/cache-write order: GPT-5.5 5/30/.5/none; GPT-5.6 Sol 4/20/.4/5; GPT-6.1 Sol 2/10/.1/2.5; GPT-5.1 Codex Mini .25/2/.025/none. Claude Opus 4.6–4.8 5/25/.5/6.25; Opus 5.5 4/20/.2/5; Fable 5 10/50/1/12.5; Sonnet 4.6 3/15/.3/3.75; Sonnet 5 2/10/.2/2.5; Sonnet 5.5 2/10/.1/2.5; Haiku 4.5 1/5/.1/1.25; Haiku 5.5 .1/.5/.01/.125 up to 100k context, .5/2.5/.05/.625 above. One-hour writes, long-context multipliers and exact sources are in `price-table.json`: [OpenAI](https://developers.openai.com/api/docs/pricing), [Claude](https://platform.claude.com/docs/en/about-claude/pricing), plus individual legacy-model pages. Subscriptions make dollars notional; unknown models remain unpriced. Missing write counters, historical tariffs, fast/region/tool charges and GPT-5.5 retrospective session surcharges prevent billing totals. (P/S)
Earlier-study overlap: request counts match exactly in 3/5 sessions; two rounded minute windows contain one additional request each. The three cost-state sessions reproduce $12.98/$10.68/$14.24 versus $13.02/$10.64/$14.24; the two assumed-rate sessions produce $17.78/$85.84 versus $20.64/$94.93. No old executable method or complete tariff table exists in the supplied directory; exact old active-time and allocation rules cannot be recreated. (S)

## Short-run estimate, with assumptions

Illustrative medium goal: one November coordinator plus four producing November workers, using separate observed medians from 28 coordinators / 60 workers. Let coordinator C = $5.213 / 12.420M tokens; worker W = $2.950 / 9.431M; coordinator cold start K = $0.555 / 0.576M. Today's synthetic pattern is 4W+C = **$17.01 / 50.145M tokens**. Keep worker effort fixed; new cost is `4W + (1-s)(C-K) + N*K`, where s is an assumed fraction of the old non-startup coordinator effort eliminated by the record. Money and token medians are separate scenarios. (S)

| Assumed non-startup effort removed | 2 runs, dollars | 4 runs | 8 runs | First costlier N, dollars / tokens |
|---|---:|---:|---:|---:|
| None | 17.57 | 18.68 | 20.90 | 2 / 2 |
| 25% | 16.40 | 17.52 | 19.74 | 4 / 7 |
| 50% | 15.24 | 16.35 | 18.57 | 6 / 12 |

This is a budget sensitivity, not a measured medium-goal completion cost or a claim that reading can be eliminated. With no saved effort, every additional startup costs more; at the assumed 25% saving, the fourth short coordinator run already exceeds today's notional money cost. Preserve progress and output quality when testing that assumption. (S)

**QA:** read 60 seeded random tool calls; initial disagreement 24/60 (40%), then 2/60 (3.33%) after calibration, retained as unresolved script/mixed-call classification. This same-researcher check is not blind; it is not an independent generalization error estimate. A separate 50-session source-field comparison has 0 mismatches; all measurable sampled token counters reconcile after adding inherited baselines and accounting for newly observed writes. Thirteen self-check assertions pass. Raw audit text stays in DATA. (A/Q/T)

Reproduce: DATA = `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112`; expand it literally in each separate command. `T: python3 -I DATA/scripts/effort.py --self-test`; `X: nice -n 19 python3 -I DATA/scripts/effort.py --extract`; `C: nice -n 19 python3 -I DATA/scripts/effort.py --correct-counters`; `A: nice -n 19 python3 -I DATA/scripts/effort.py --audit-view`; `Q: nice -n 19 python3 -I DATA/scripts/effort.py --verify`; `S: nice -n 19 python3 -I DATA/scripts/effort.py --summary`. P is the dated price table with its official source URLs. S produces every numerical result above unless marked C, X, A, Q, T or P; percentages divide the stated underlying counts and time-unit conversions divide seconds. Outputs: `sessions-corrected.jsonl`, `counter-corrections.jsonl`, `goals.jsonl`, `curated-goal-envelopes.jsonl`, `summary.json`, manifests, prices, rules and audits in `DATA/effort/`. Sources were read only; no other Mac, page, bead, configuration or Git mutation was used.
