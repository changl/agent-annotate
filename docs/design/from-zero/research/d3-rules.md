# D3 — The standing rule book

**1,757 extracted rule candidates; 393 repeated occurrences; 408 correction-derived candidates; 69 classified transferable preferences.** These are an extraction inventory, not a verified census of distinct personal rulings. [C1]

The strongest design finding is that more written instructions are not evidence that mistakes stopped. Notes mix preferences, permissions, procedures, old exceptions and historical facts; the applicable ruling must reach the helper at the decision itself.

Sources: 494 files — memory 408, instruction files 23, skills 55, handoffs 8. Canonical rows live in DATA/corpus/rules.jsonl; occurrence ids, source lines and hashes live in DATA/d3/. Only skill headings and directive lines entered the inventory. No source was changed. [C1]

## What the inventory contains

| Kind | Candidates [C1] |
|---|---:|
| other | 738 |
| how work is checked | 366 |
| taste and look | 82 |
| how to talk to him | 76 |
| which tool or machine to use | 329 |
| what a helper may decide alone | 19 |
| what he must approve | 93 |
| safety limit | 54 |

Canonical source: memory 1297, handoff 103, skill 293, instruction 64. Exact normalized copies are merged; 334 canonical rows have copies. `duplicates` points to occurrence rows in d3/rule-occurrences.jsonl. Semantic equivalents remain, so the distinct count is an upper bound. [C1]
Origin: a correction after a mistake: 408, unknown: 1159, an answer to a question: 126, stated up front: 64. Origin is attributed from the note, not independently proved for every clause. A feedback label alone does not establish a correction. [C1]
Grouping: 69 person preferences, 83 permissions, 1605 tool/project procedures. This conservative keyword classification is provisional; the seed below is the manually read portable core. Installed skill prose does not prove Chang authored or endorsed every line. [C1, C4]
Dates: 1105 have no dated instruction/incident anchor. Non-null dates are the earliest explicit anchor found in the source, not a proved first-ever ruling; modification dates are separate. No filesystem timestamp was substituted for first-given. [C1]
Quality: a seeded random sample of 50 rows, compared with source context, had 7 defects (14%) before curation: 2 contextual rewrites and 5 historical/one-off exclusions. Those cases were corrected; this is not a post-correction error estimate. Missed rules, semantic duplicates and classification errors remain unmeasured. [C1]

## Repeats and the limit of the evidence

Used the coordinator-approved frozen **DATA/wave2/m1max-snapshot.jsonl**, not the changing live corpus; its hash and coverage are recorded. Searched 40 distinct source rules against 1,377 human-labelled rows; 33 rules produced 570 rule/row matches in 158 human rows. Excluded 61 task/relay/template rows and omitted text from 4 possible-secret rows. The English correction filter is intentionally narrow. [C2]
Bounded reading confirmed **at least 11 rule/correction pairs, involving 8 rules and 8 distinct human corrections**, between 1.0 and 189.2 days after the source’s dated instruction/incident. These are lower bounds, not a violation rate; one correction may concern overlapping rules. Each counted row was read. Uncounted topic matches and no detected repeat do not establish compliance. [C3]
Only 1 counted pair(s), involving 1 rule(s), occur after the note’s recorded latest modification. Missing original write times prevent a general claim that the note already existed at each later correction; later helpers’ loaded context is not observable here. **Writing down the rule did not demonstrably guarantee prevention; its causal effect cannot be measured from this corpus.** [C3]
Counts, exact dates, elapsed days, row ids and exclusions are in d3/repeat-results.jsonl and d3/repeat-decisions.jsonl; the selected canonical rows also carry `violated_after`. The corpus hash and coverage are in d3/repeat-scan-stats.json. [C2, C3]

- Keep ready work moving without waiting for reminders. — 2 confirmed; 2026-11-01, 2026-11-02; row m1max:145f492c-0a25-47a7-886d-bcd06c16e5ff:fcb6c189ffe5:304. [C3]
- Surface real decisions promptly without repetitive status noise. — 1 confirmed; 2026-10-17; row m1max:f8ce3ef9-187b-46d8-9edb-f56c066099bf:985007b9117b:127. [C3]
- Remove finished worktrees and merged branches. — 2 confirmed; 2026-05-20, 2026-11-04; row m1max:019e40b2-7b26-7df3-9079-3514fa315d2d:979404e5b9c0:40. [C3]
- Keep the task tracker current as work changes. — 1 confirmed; 2026-05-20; row m1max:019e40b2-7b26-7df3-9079-3514fa315d2d:979404e5b9c0:40. [C3]
- Verify interactive UI in a real browser before handing it over. — 1 confirmed; 2026-07-24; row m1max:019f95ed-6c31-7691-ae5d-b69441c36d9b:d8d6e410ecb5:8. [C3]
- Verify assumptions against running code and data before proposing fixes. — 1 confirmed; 2026-07-10; row m1max:60f2beff-76bb-4ce6-b170-966fb3f6a538:2b38761ddca6:37. [C3]
- Back completion claims with the underlying evidence. — 1 confirmed; 2026-07-24; row m1max:019f95ed-6c31-7691-ae5d-b69441c36d9b:d8d6e410ecb5:8. [C3]
- Validate every premise against the live source before acting. — 2 confirmed; 2026-07-10, 2026-10-29; row m1max:60f2beff-76bb-4ce6-b170-966fb3f6a538:2b38761ddca6:37. [C3]

What the repeats share: broad injunctions such as verify or keep things current are easy to acknowledge without checking the final effect. Task-state upkeep and workspace cleanup require a recurring owner; silence otherwise hides neglect. User-facing review behavior needs a product invariant, not another instruction to every publisher. Source accounts also describe compaction losing a commit-identity rule and obsolete procedures conflicting with corrections. These explain plausible failure paths; they are not measured causal shares.
Length, wrong location and missing loads are hypotheses, not findings of causation. A long rule may be precise; a short one may be vague. The data do not record which rule was retrieved, which version won, how many opportunities to violate it occurred, or whether a check enforced it.

## Contradictions and scope

Manual reading found 7 apparent pairs: 4 direct wording conflicts and 3 policy tensions. No pair remains logically unresolved after its recorded date, project, role or task exception is applied; that is not proof that live agents apply the same precedence, nor an exhaustive contradiction count. Full pairs and readings are in d3/conflicts.jsonl. [C4]

- Global Claude-only model list versus Codex worker authorization. Named worker authorization is narrower; do not apply the coordinator model list to every worker. (d3r-a37b1fee6f2b, d3r-654a0fef5ae0). [C4]
- UI workers use Opus versus the later Codex-only override. The later override covers the annotate coordinator’s direct workers; later named leads and the other project retain their own exceptions. (d3r-f25a2f51b6a7, d3r-0a8e4e7a34e8). [C4]
- Preserve an old model pin versus migrate away from that model. The pin is an old task-specific exception; the other rule concerns new work in a different project. (d3r-0dfa03e82fa4, d3r-85f00156919c). [C4]
- Automatically synchronize accepted changes to skills versus require explicit skill-edit authorization. Acceptance must include skill edits; do not infer permission from a code-only request. (d3r-d2b86def722d, d3r-d74f3526663e). [C4]
- Reuse established UI conventions versus inherit no existing product in a reimagining. Existing-product changes and a first-principles reimagining have different scopes; the source explicitly distinguishes them. (d3r-8cf14e474da8, d3r-83810e514de1). [C4]
- Prefer the simplest path versus do not default to the smallest change. Least complexity must still satisfy the requested lasting result; this is a tradeoff, not permission to omit scope. (d3r-0d5de52c6a30, d3r-e1bd40550e2b). [C4]
- Proceed without repeated approval versus present options and wait on a how-can-we question. An exploratory question has not authorized implementation; later approved execution does not need repeated permission. (d3r-4b3b5fc4941c, d3r-37d5da0ed76d). [C4]

## Seed of the new rule book

These 30 plain rules are a proposed reading of existing instructions, not new standing instructions or permission to change any setup. Keep project exceptions attached. Sources and original rule ids are in d3/seed.jsonl. [C4]

1. Check the result the person actually experiences before calling work done. (d3r-ec6a6f4e7447)
2. Validate assumptions against live evidence before planning or acting. (d3r-4f2cf5c3f610)
3. Independently verify another helper’s finding before turning it into work. (d3r-7b5a5f3ecb06)
4. Carry authorized work through to a verified result or a concrete external blocker. (d3r-38ee6f026305)
5. Do the manual work yourself whenever your tools allow it. (d3r-632dcfd8e501)
6. Reproduce problems yourself instead of making the person repeat them for you. (d3r-95438d6632b2)
7. Choose the simplest path that fully solves the real problem. (d3r-0d5de52c6a30)
8. When a lasting solution is requested, solve the structural problem rather than the next symptom. (d3r-e1bd40550e2b)
9. Improve the requested experience without silently removing working features. (d3r-e8aa3a4a3262)
10. Research established conventions before changing an existing interface. (d3r-8cf14e474da8)
11. For a reimagining, derive the method from the problem and choose tools last. (d3r-83810e514de1)
12. Give your own recommendation and identify where it changes an earlier request. (d3r-56a00fd4bdff)
13. Lead with the answer and cut unnecessary text without imposing word limits. (d3r-37d5da0ed76d)
14. Use plain names the person recognizes rather than internal labels. (d3r-d8d56d6e94b7)
15. Name the machine, workspace and terminal as the person sees them. (d3r-8e9ee2568eb2)
16. Surface real decisions promptly and omit messages that nothing changed. (d3r-760205e8d0ac)
17. Keep each decision next to the evidence needed to answer it. (d3r-fb39404330af)
18. Prepare each decision with context, a recommendation and the consequence of each option. (d3r-9759631b424b)
19. Show actual or drawn screens before requesting a design decision. (d3r-ec32206c1136)
20. Keep the reviewed thing stable until the person submits the round. (d3r-f80233a9e0b4)
21. Make every question answerable and link directly to it. (d3r-c1e6a27c5153)
22. Keep the durable task record current and attach proof when closing work. (d3r-5c79fabee7a8)
23. Keep unblocked work moving without reminders. (d3r-0b7e5e26ab8c)
24. Rehearse privileged work on the actual target before asking for the person’s time. (d3r-7009dc605daf)
25. Obtain approval naming the release and target machines before cross-machine rollout. (d3r-6aadc8cccfce)
26. Proceed on a safe authorized path and ask only for a genuinely reserved decision. (d3r-4b3b5fc4941c)
27. Inspect named safe fields and keep secret values out of output. (d3r-aca0fabfeb39)
28. Change skills and standing instruction files only when explicitly requested. (d3r-d74f3526663e)
29. Run repeatable work with deterministic scripts and reserve models for judgment. (d3r-78a62400b304)
30. Use existing records before spending more time collecting evidence already available. (d3r-4f5d510e1d19)

## What a rule must carry to prevent a repeat

Carry the person’s underlying goal, an observable trigger, the required action and its check, project/role/machine scope, the actual grant or approval boundary, source evidence and date, supersession/expiry, and a concrete example of the prior mistake. A short instruction should point to its detailed procedure rather than copy it.
At dispatch or action time, record the applicable rule ids and versions and whether the check ran. Resolve contradictory scopes before execution. At completion, attach the result of that check; a later correction links back to the same rule. Only then can failures be separated into a missing rule, failed retrieval, ignored instruction or inadequate rule, and can prevention be measured per opportunity.

## Reproduce

Run each command separately with `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112` (DATA) as the working directory.

- C1: `python3 d3/finalize.py report` counts the delivered rows and QA ledger. Re-extraction: `nice -n 19 python3 d3/rules.py extract`, then `python3 d3/finalize.py apply`; schema/parser check: `python3 d3/rules.py check`.
- C2: `nice -n 19 python3 d3/repeats.py candidates` searches the frozen wave2 snapshot and writes the selection, candidates, coverage and source hash. `python3 d3/repeats.py pack 0 40` reads candidate packs; keep raw text in DATA.
- C3: `python3 d3/adjudicate.py` applies the explicit reading decisions, deduplicates identical correction text per rule and writes the lower bounds and elapsed days. Re-run after C2 if the corpus changes.
- C4: `python3 d3/design.py` writes the source-linked seed and conflict ledger. Render this file: `python3 d3/report.py`. All findings numbers come from C1–C4; unmeasured limitations are stated above.
