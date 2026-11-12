# G-B — Project B: observed cycles per goal

**12 goal paths; 115 observed goal-cycles; median 7, range 1–30. Only 1 bounded result has explicit human acceptance; the other 11 lack a final acceptance. This is not a completed-goal median.**

Sources: frozen M1 Max snapshot; 1,921 page questions (1,464 answered), 474 explicit Sends from both Macs, and the largest board (1,916 items), plus tasks/candidates and frozen raw page snapshots. M5 Max chat was absent when work began and remains absent; no other Mac was read.

Unit: one explicit Send per goal touched, regardless of answer count; each later typed intervention is a cycle. A fresh standalone request is recorded separately; an initial page reply or a repeated nudge is a return and counts. 101 cycles came from pages, 14 from chat: 85 distinct returns across overlapping goals. Mere republishing, withdrawn asks and board state changes add no cycles.

Selection is purposive: small fixes, multi-day work, recurring multiweek work, and failures. Starts are the first retained statement in each bounded path, often after an earlier missing request; B05's original is quoted indirectly on its board. No page response is replaced with a guessed missing chat.

| Goal | Size | Cycles / par | Observed days | Prose words | Minutes |
|---|---|---:|---:|---:|---:|
| B01 Keep driving notices in one card above fixed controls | medium | 8 / 3 | 5.89 | 355 | unknown |
| B02 Make testing fast, modular and mainly scripted | medium | 10 / 2 | 5.86 | 1,169 | unknown |
| B03 Make the hourly board sweep act on stale work | large | 30 / 2 | 11.10 | 2,823 | unknown |
| B04 Show a member their own row in the member list | small | 1 / 2 | 0.00 | 0 | unknown |
| B05 Trace admin actions to the agent using one existing login | medium | 3 / 2 | 1.95 | 173 | unknown |
| B06 Send accurate visual instructions for the rally | small | 5 / 3 | 0.11 | 207 | unknown |
| B07 Let drivers pick skipped stops without sending the group backwards | medium | 9 / 3 | 10.92 | 188 | unknown |
| B08 Save and publish departure times for rally stops | medium | 2 / 2 | 10.89 | 0 | unknown |
| B09 Delete accounts through HQ while retaining anonymised posts | large | 6 / 2 | 27.21 | 101 | unknown |
| B10 Allow private messaging before saving a recovery copy | large | 12 / 3 | 12.92 | 706 | unknown |
| B11 Clear the new inventory of stale workspaces across three Macs | medium | 23 / 2 | 4.08 | 1,928 | unknown |
| B12 Prepare a useful independent backup and recovery plan | medium | 6 / 2 | 4.54 | 283 | unknown |

Par totals 28; actual totals 115 (87 above par in aggregate). Par is 2 plus one necessary visual taste fork for B01/B06/B07/B10. These excesses are a comparison target, not proven avoidable waste: required risk decisions, changed wishes and missing endpoints remain. B04's single return cannot establish below-par completion.

Days run from first retained statement to acceptance or last intervention, not to an invented finish. B08 ends with acceptance of the departure-field dev proof; it does not accept the separate proposal to shift later stop times. A chart approval (B09), a conditional as-built approval (B01/B07) or a merge GO is retained as partial scope evidence, not final delivery acceptance.

Prose totals 7,933 goal-attributed submitted words, including available initial requests; selected option labels are removed. A shared answer can contribute to several goals, so this is neither unique keystrokes nor a total attention bill; B05 includes the board's owner quotation. Reading, waiting, device work and thought were not timed: minutes and goal tokens remain null; elapsed answer latency is not time spent. Helper task joins and the incomplete local session IDs are in the JSONL.

| Primary cause | Cycles |
|---|---:|
| `his_decision` | 46 |
| `sent_back_intent` | 18 |
| `sent_back_quality` | 12 |
| `not_needed` | 9 |
| `his_change` | 6 |
| `status_or_nudge` | 15 |
| `relay` | 2 |
| `tooling` | 7 |

Each cycle has one primary cause. On a mixed Send, a system failure or return takes precedence over a simultaneous approval. These are single-researcher judgements, not automatically discovered causes; an ordinary approval alone does not prove that asking was unnecessary.

First statements: B04 already states the whole visible behaviour; B08 accepts a proposition containing the departure field and compatible format. B06/B10 contain firm constraints, but later proposals lose them. B02 initially asks for speed and cost, then adds module granularity and a smoke duration. B03/B11 begin with an outcome and safety constraint, then expand cadence, project coverage and custody policy. B09 leaves deadline/content policy open; B12 adds independent-provider recovery and pricing after its initial plan request.
The gap has three forms: unstated owner preferences (deadline, content handling, acceptable smoke duration); facts nobody had measured (test cost, custody, restore feasibility); and prior rulings not carried forward (one card, optional save, cross-platform consistency, storage pricing). JSONL records these separately, without invented coverage percentages or pretending later scope was finally accepted.

The three worst paths by observed cycles, five lines each:

B03 — Hourly board upkeep: 30 returns against par 2 over 11.10 observed days.
The owner requests an hourly reminder, then repeatedly finds blocked and stale work that has not moved.
The early plan lists problems rather than fixing them; later rounds repeat the script/model split and require continuity across coordinators.
Board evidence claims hourly apply receipts, while another item records dropped positive sweep packets; those are distinct implementation claims.
No final acceptance survives; key question suffixes: q:87f78b844b3d, q:0d9c9993a277, q:aa45590807fd.

B11 — New workspace inventory and cleanup: 23 returns against par 2 over 4.08 observed days.
The initial request covers all three Macs, hidden workspaces and preservation; later replies still have to push actual removal.
Exact-path and cohort approvals are followed by questions about saved sessions, unmerged branches, rescue copies and recurring cleanup.
The board reports 130 of 234 approved paths removed and 104 held, which is partial execution, not owner acceptance of the whole inventory.
The owner also pushes back on waiting for a scheduled run; suffixes: q:34c2fda7b087, q:30b6802c370d, q:531b997a950b.

B10 — Optional recovery-copy saving: 12 returns against par 3 over 12.92 observed days.
The first retained instruction says to allow messaging without adding a save screen; later drawings and device flows need correction.
A genuine policy change allows automatic local custody with a notice; subsequent configuration work affects which builds can save.
The settings page is accepted as built, but the skip/continue ruling has to be restated near the end.
The final page choice is retained without inventing a complete release acceptance; suffixes: q:8dd3b2b2c1a2, q:a11af86d5bd4, q:6e6b309e9010.

Rejected candidates: whole-application epics; all rerouting as one goal; separate cascading-time work; every release; helper-created singleton defects; credential rotation with masked context; test/dispatch/handoff prompts; earlier generic upkeep merged indiscriminately with the new requests. Reasons and private source keys are in `DATA/goals/b-working/rejected.json`.

What M5 Max chat could change: recover original requests and extra corrections, nudges, relays or acceptances; distinguish a helper's mistaken reading from an actual owner change; separate an accepted version from a later new goal. Thus completed-goal counts, durations, cause shares and the median could change in either direction after regrouping. The retained Sends are direct evidence of returns, not proof of complete paths.
What cannot be rebuilt: final acceptance for most goals, complete first statements, masked answer content, page-author/worker session identity, per-goal tokens and active minutes. A missing answer remains missing; board closure never supplies a human verdict. No transcript was read wholesale and no live page, board, settings or service was changed.

Quality: read 50 seeded random extracted page-member rows; 13/50 initially included generated choice labels in typed text. Restoring retained question options fixed those; final source-membership/text/verdict discrepancies 0/50 (0%). 2 rows check redacted metadata only; 6 have no recoverable answer text. This does not validate every semantic goal join.
The random second-pass goals (seed 20261112) were B04/B09/B12. The topic pass found three additional B09 Sends (deletion copy, attorney escalation, tester deployment); those were included. Final fresh raw-round recounts are 1/6/6, identical to the final JSONL (difference 0 each). The same researcher did both passes; no independent-rater claim.
All 82 locally labelled human rows were screened; 14 dispatch/test/helper-relay-shaped rows were excluded from goal selection and one secret-bearing row retains metadata only. Their audit stays in DATA.

Reproduce, one command at a time (`DATA=/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112`; use its literal path):
```text
nice -n 19 python3 DATA/goals/b-working/extract.py
nice -n 19 python3 DATA/goals/b-working/build.py
nice -n 19 python3 DATA/goals/b-working/verify.py
nice -n 19 python3 DATA/goals/b-working/report.py
```
`build.py` embeds the adjudicated goal boundaries, answer IDs and primary causes; `adjudication.json`, `audit-50*.json`, `second-pass.json`, `verification.json` and `source-manifest.json` retain the decisions, check and frozen-input hashes. Replace DATA in the commands; the report is the only repository output.

Design implications: retain one goal key through a Send and its checked result; carry scope-specific rulings into the next showing; record acceptance of a named result separately from permission to merge. The observed lower bounds justify those mechanics, but cannot establish the attention or completed-goal improvement of a new method.
