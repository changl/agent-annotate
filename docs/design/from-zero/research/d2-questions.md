# D2 — Questions put to the person

Observed: **3,265 questions; 2,099 answered; 0 waiting; 1,149 withdrawn; 17 set aside**, across 84 registered pages and 28 project/path groups on M1 Max and M5 Max. (S)

**Reproduce.** DATA is `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112`. Every numeric result below is from S, except the extraction check marked Q; percentages divide the named counts and time units divide seconds. Source snapshots are frozen, not an atomic cross-machine snapshot.

```text
G: nice -n 19 python3 /Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/scripts/extract_questions.py --gather
E: nice -n 19 python3 /Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/scripts/extract_questions.py --extract
L: nice -n 19 python3 /Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/scripts/extract_questions.py --label
Q: nice -n 19 python3 /Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/scripts/extract_questions.py --qa
S: nice -n 19 python3 /Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/scripts/extract_questions.py --summary
```

Run E, L, Q and S separately to rebuild from the frozen evidence; G refreshes it. Manual label-hidden answers are retained in `DATA/corpus/d2-blind-labels.jsonl`, with the original sample and frozen first-pass labels beside it. S writes `d2-summary.json`. The requested outputs are `questions.jsonl`, `rounds.jsonl` and `pages.jsonl` in `DATA/corpus/`.

**Per project (S).** Generic registry names were resolved through their registered local directory; distinct historical path groups remain distinct. Empty rows mean no recoverable asks, not proof that nobody ever asked anything.

| Project/path group | Pages | Asked | Answered | Waiting | Withdrawn | Set aside |
|---|---:|---:|---:|---:|---:|---:|
| agent-annotate | 7 | 154 | 137 | 0 | 17 | 0 |
| agent-memory-consolidation | 1 | 0 | 0 | 0 | 0 | 0 |
| artifacts | 1 | 0 | 0 | 0 | 0 | 0 |
| cheerticketing | 1 | 3 | 0 | 0 | 3 | 0 |
| claude-config | 10 | 133 | 38 | 0 | 95 | 0 |
| cli-proxy-api-m5-clients | 1 | 0 | 0 | 0 | 0 | 0 |
| codex-memory-consolidation | 1 | 0 | 0 | 0 | 0 | 0 |
| connelly | 17 | 110 | 68 | 0 | 42 | 0 |
| crunchbase | 1 | 0 | 0 | 0 | 0 | 0 |
| dealcenter | 1 | 0 | 0 | 0 | 0 | 0 |
| docs | 1 | 3 | 0 | 0 | 3 | 0 |
| evo-padel | 1 | 0 | 0 | 0 | 0 | 0 |
| fastlane-drive | 8 | 1921 | 1464 | 0 | 440 | 17 |
| graph-engineering-framework | 1 | 4 | 4 | 0 | 0 | 0 |
| human-by-intent | 1 | 25 | 13 | 0 | 12 | 0 |
| leadory | 3 | 7 | 3 | 0 | 4 | 0 |
| leadory-(2) | 1 | 11 | 0 | 0 | 11 | 0 |
| memory-consolidation | 1 | 0 | 0 | 0 | 0 | 0 |
| memory-phase2 | 1 | 0 | 0 | 0 | 0 | 0 |
| multimac-orch | 2 | 36 | 32 | 0 | 4 | 0 |
| orchestration-wakeup-fix | 1 | 7 | 2 | 0 | 5 | 0 |
| pitchpoint | 2 | 25 | 21 | 0 | 4 | 0 |
| ponytail-impact | 1 | 0 | 0 | 0 | 0 | 0 |
| ponytail-setup | 1 | 0 | 0 | 0 | 0 | 0 |
| rebex | 9 | 306 | 277 | 0 | 29 | 0 |
| reviews | 1 | 2 | 2 | 0 | 0 | 0 |
| tmp | 2 | 470 | 0 | 0 | 470 | 0 |
| windmill | 6 | 48 | 38 | 0 | 10 | 0 |
| **Overall** | **84** | **3265** | **2099** | **0** | **1149** | **17** |

**Choices and typing (S).**

- Recommendation followed: 903/1,156 comparable answers = **78.1%**. Another 943 answers cannot be compared; the confirmed matches are 43.0% of all answered questions.
- Typed words appeared on 774/2,099 answered questions = **36.9%**; **38,913 recoverable words** after removing choice labels, revision receipts, identifiable agent bookkeeping and duplicate copied text within a question.
- `needed_him=no`: 529/2,099 = **25.2%**; yes 867; unclear 703. No requires an accepted recommendation, no typed words, and a reversible ordinary choice; uncertain authority, deletion, payment and credentials stay unclear.
- `rule_could_answer=yes`: 5/2,099 = **0.24%**, each naming an earlier row. This is a narrow confirmed lower bound: the answer must predate the question and cover the same fork. No means no demonstrated covering rule was found, not that none existed.

| Primary reason for typing (S; provisional) | Questions | Share of questions with words |
|---|---:|---:|
| he was adding a new requirement | 328 | 42.4% |
| other | 153 | 19.8% |
| he was correcting a misunderstanding | 122 | 15.8% |
| the options missed what he wanted | 83 | 10.7% |
| he was asking a question back | 61 | 7.9% |
| he was setting a standing rule | 27 | 3.5% |

**Waiting and sittings (S).**

- Ask to final stored answer: median **52.1 minutes**, 90th percentile **14.11 hours**, longest **12.09 days**, over 2,099 answered questions. This is elapsed time to the stored choice, not time spent reading or typing; `sent_at` is retained separately.
- Waiting now by age: under a day **0**; a day to a week **0**; a week to a month **0**; a month to two months **0**; older **0**; unknown **0**. Set-aside questions are separate. Archive/consolidation markers and retired registrations withdraw their outstanding asks; historical open cards do not create a current backlog.
- **814 explicit answer-return events**: 478 modern Sends and 336 legacy explicit pushes. Answers/items per event: median 1, mean 3.17, 90th percentile 8, maximum 103. No inferred time-gap clusters were added.
- Between events on the same page: median **29.0 minutes**, 90th percentile **10.55 hours**, longest **19.24 days**, over 775 intervals. Legacy 400 events expose item IDs rather than full answer lists, so their counts can include notes. Round text totals 49,871 words including notes and re-sends; it is not a fresh-keystroke total.
- **1,051/3,265 questions (32.2%)** have repeated card IDs or preserved request variants, with 2,588 extra occurrences. Republishing often made another card: this measures stored recurrence, not proven repeated interruptions.

**Ten recurring kinds and candidate first rules (S; topic labels are approximate).**

| Kind | Questions | Candidate rule |
|---|---:|---|
| Choose how the product or work should behave | 574 | Choose a reversible default and show its result. |
| Accept a screen or layout | 564 | Reuse approved components, icons and cross-device styling before showing a screen. |
| Correct or simplify an agent instruction | 470 | Resolve clerical instruction conflicts from the current owner rule. |
| Run tests or check a working result | 275 | Automate checks; ask for a real-device or taste check only when needed. |
| Approve a merge, release or deployment | 248 | Apply the agreed release gates, then act within granted authority. |
| Choose maps, routes or drive behaviour | 232 | Keep one agreed route and consistent guidance across devices. |
| Start work, agree a plan or choose priorities | 216 | Work inside the agreed scope; bring only a new owner fork. |
| Choose sign-in, permissions or identity rules | 134 | Use established sign-in practices; escalate actual access or privacy decisions. |
| Clean up files, configuration or tools | 111 | Separate reproducible caches from unique data before proposing removal. |
| Choose messages, chat or notification behaviour | 97 | Keep notification defaults and visibility consistent with earlier rulings. |

**Quality and limits (S unless Q is named).**

- Inspected 50 seeded random extracted rows against raw card fields and source status, including archive state: **0/50 flagged extraction errors (0%)**; parser assertions, unique IDs, page totals, nonnegative waits and precedent chronology passed (Q). This does not prove every historical ask survived.
- A later label-hidden reassessment of 60 seeded random answered rows agreed on all labels for **39/60 (65.0%)**. By field: needed-him 52/60 (86.7%); covering rule 57/60 (95.0%); typed reason including empty 47/60 (78.3%). On the rows assigned any typed reason in either pass, agreement was only **8/21 (38.1%)**.
- The first pass applies a conservative rubric, reviewed in batches from actual rows; the second pass was manual and label-hidden to the same worker, not a separate rater. The comparison uses the frozen first pass. Final labels incorporate extraction corrections and exclude precedents learned after a question was asked. The reason split is exploratory, not a dependable causal measurement.
- Coverage: current and retired registries on both Macs; JSON plus read-only SQLite records, submitted snapshots, event history and archive markers. 6,621 physical question records became 3,265 rows after mirror, moved-card and exact prompt/context deduplication. Different contexts remain separate; unrecorded rewordings cannot be reconstructed.
- 5 registered page directories could not be recovered from either Mac; 5 asks survive as event metadata only, with empty text. 184 questions contain redacted source text. 77 answered rows are anonymous or unattributed; 2,022 identify Chang. Counts are retained evidence, not an exhaustive claim about missing data or the live fleet.
- Raw text stays in DATA. M5 extraction ran over key-only SSH and printed rows to stdout without remote output files. No pages, boards, settings, product code or other-machine files were changed.

**What matters for the design.** Accepted reversible defaults offer a real attention-saving opportunity; a high recommendation match rate alone does not establish permission to act. Repeated screen corrections call for carrying a ruling across related evidence before asking again. Retired pages and copied cards must be separated from live obligations, or both backlog and attention cost are overstated.
