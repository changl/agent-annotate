# B1 — Baseline: observed returns, not yet cycles to done

**80 goal paths; 759 normalized observed returns; median 5.5 (Q1 3, Q3 10.25, worst 55), against diagnostic par 184. Only 16 paths have both a clear opening and a clear bounded acceptance: 63 returns / par 39; median 3 (2–5.25; worst 9).**
**Comparable membership stratum: A/B/C/F = 53 goals, 389 returns. D/E = 27 goals, 370 returns under dominant-goal attribution, kept separate. The 759 is a descriptive sum, not a fully harmonized headline or an average for completed work.**
All numbers below are reproduced by B (data/summary/audit) and R (this report); replace DATA with `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112`. Run separately:
B: `nice -n 19 python3 /Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/baseline/build.py --audit`  
R: `python3 /Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/baseline/report.py --output docs/design/from-zero/research/b-baseline.md`  
Outputs: `baseline/goals-combined.jsonl`, the same table as TSV, `summary.json`, input hashes and `audit-50.jsonl`; retained `audit-decisions.json` records human judgments. The summary contains full per-project quartiles, cause counts/shares, word shares, checks and scenario arithmetic.

Unit: one subsequent typed owner message or explicit page Send per goal touched; several cards for one goal count once. An unsolicited opening is separate; a first surviving reply to a helper counts. Accepting a shown result counts; publications, board closures and helper claims do not. Shared goal-cycles are not independent interruptions.
Goals remain the authors’ bounded requested outcomes; parent/child overlap and enlarged scopes remain visible. No new grouping is inferred from keywords. Size means judged hours/days/weeks scope, not measured effort. Par remains 2 + each showing-dependent taste decision; technical choices do not add taste.
Clear opening = a bounded originating request or scope-setting reply with its prompt retained; a later correction, indirect quotation or resumption is insufficient. Clear acceptance = an owner acceptance of the bounded object; permission to deploy is weaker than verified use. Conditional a11, self-completed D09 and merge-before-validation E07 are excluded; these adjudications are inspectable per row.
A (`goals/a-work/rebuild.py`): requested feature/repair goals; opening excluded; page answers grouped by Send; allows a shared action under several goals. Par from `taste_decisions`.
B (`goals/b-working/build.py`): bounded outcome paths, often missing their original opening; page-first replies count and standalone openings do not. Mixed Send cause prioritizes failure over approval. Par from listed taste forks.
C (`scripts/g_c.py`): bounded requested outcomes including overlapping parent/child paths; first question reply counts, unsolicited opening does not; mirrored Sends collapsed. Par includes wording/photo/banner taste, not matching an established theme.
D (`goals/d-work/build.py`, `spec.py`): requested outcomes; opening excluded, one message assigned only to its dominant goal. Two known secondary D07 links and unassignable page payloads remain gaps. Cannot recover all-goals-touched membership without new adjudication: keep separate. Par from sketch-dependent choices.
E (`goals/e-build.py`): requested outcomes including enabling workflow; originally counts opening and assigns each message once. Remove exactly 15 openings: 164 → 149; full touched-goal membership is still unavailable, so keep separate. Par adds one shown terminology choice.
F (`scripts/build_goal_f.py`, `goal_f.py`): bounded direct requests; opening excluded; explicit new-goal topic changes split. Structured answers not doubled. Par includes layout or brand-system taste.
Recalculate A’s open spans to last observed return, replacing snapshot-cutoff durations. All words use whitespace splitting of retained submitted text; B previously used a different tokenizer. B page openings are not charged twice when answer and Send times differ. Initial-only words are separate from cause-word denominators.

| Group | Goals | Returns / par | Q1 / median / Q3 / worst | Both-clear goals: returns / par; spread |
|---|---:|---:|---|---|
| All, descriptive | 80 | 759/184 | 3/5.5/10.25/55 | 16: 63/39; 2/3/5.25/9 |
| A/B/C/F | 53 | 389/125 | 3/5/9/32 | 14: 56/35; 2/3/5.75/9 |
| D/E, separate | 27 | 370/59 | 3/6/15.5/55 | 2: 7/4; 3.25/3.5/3.75/4 |
| A | 15 | 94/37 | 2/3/8/32 | 9: 34/23; 2/3/5/9 |
| B | 12 | 115/28 | 4.5/7/10.5/30 | 0: unavailable |
| C | 14 | 99/32 | 4/5/9.5/19 | 3: 9/8; 2/2/3.5/5 |
| D | 12 | 221/28 | 5.5/9/20.75/55 | 1: 4/2; 4/4/4/4 |
| E | 15 | 149/31 | 3/4/14/32 | 1: 3/2; 3/3/3/3 |
| F | 12 | 81/28 | 3.5/5.5/9/16 | 2: 13/4; 6.25/6.5/6.75/7 |
Quartiles use linear interpolation at (n−1)p. All-goal net excess is 575, but unfinished work, altered wishes and missing starts make it a diagnostic difference, not removable waste. Both-clear paths are selected successes, not a representative estimate.

| Cause | All cycles (%) | Non-option submitted return words (%) | What addresses it |
|---|---:|---:|---|
| his_decision | 223 (29.4) | 4605 (13.9) | Genuine owner decisions remain |
| sent_back_intent | 108 (14.2) | 7346 (22.1) | Agreement + rule book |
| sent_back_quality | 153 (20.2) | 9990 (30.1) | Checker |
| not_needed | 59 (7.8) | 1448 (4.4) | Defaults + rule book |
| his_change | 35 (4.6) | 2702 (8.1) | New wishes remain |
| status_or_nudge | 78 (10.3) | 3170 (9.6) | Watch |
| relay | 35 (4.6) | 2401 (7.2) | One doorway + record |
| tooling | 68 (9.0) | 1512 (4.6) | Checker/watch/doorway only for preventable failures |
Word denominator = 33,174 submitted words in A/B/C/E/F returns. D’s 11,675 includes selected answer labels and stays separate. All-goal opening-plus-return attribution is 55,400; shared text and pasted reviews mean neither total measures keystrokes, personally composed words or attention. No cause share of literal typed words is identifiable.
Per-project vectors below follow the cause order above; cycle % and return-word % each sum approximately to 100. D’s word vector remains option-inclusive.

| Project | Cycle % by cause | Submitted return-word % by cause |
|---|---|---|
| A | 29.8/17/21.3/5.3/3.2/8.5/5.3/9.6 | 17/24.7/31.5/5.1/5.1/4.7/6.1/5.9 |
| B | 40/15.7/10.4/7.8/5.2/13/1.7/6.1 | 11/28.3/16.6/7.1/5.8/22.6/3/5.6 |
| C | 40.4/16.2/9.1/10.1/4/10.1/0/10.1 | 6.6/27.2/26.7/7.2/5.1/16.5/0/10.8 |
| D | 20.4/12.2/28.5/9/3.6/8.6/6.3/11.3 | 13.7/16.4/35.1/6.9/5.5/3.7/11.9/6.8 |
| E | 24.8/12.8/21.5/3.4/7.4/15.4/8.7/6 | 14/14/39.7/0.5/12.1/3.4/14.6/1.6 |
| F | 33.3/14.8/21/12.3/3.7/3.7/1.2/9.9 | 24.4/27.5/27.3/7.8/7.8/1.8/0.8/2.7 |

| Group | Size medians S/M/L | Days Q1/median/Q3/worst | Spearman cycles:size / days | Pre-work checks: n/median cycles |
|---|---|---|---|---|
| All, descriptive | 3/9/12 | 0.1/0.9/5.87/33.84 | 0.66/0.65 | yes:34/5.5; no:22/5; unknown:24/6 |
| A | 2.5/9/19.5 | 0.06/0.52/5.3/21.14 | 0.67/0.79 | yes:12/3; no:3/4; unknown:0/— |
| B | 3/8/12 | 3.55/5.88/10.97/27.21 | 0.60/0.49 | yes:1/23; no:1/10; unknown:10/6 |
| C | 4/5/7.5 | 1.08/2.27/12.29/33.84 | 0.37/0.45 | yes:4/3.5; no:0/—; unknown:10/6 |
| D | 4/8.5/54 | 0.52/1.76/13.45/22.13 | 0.81/0.78 | yes:5/7; no:7/11; unknown:0/— |
| E | 3/27/32 | 0.05/0.15/0.66/10.21 | 0.78/0.73 | yes:6/3; no:5/3; unknown:4/12.5 |
| F | 4/12/— | 0.04/0.25/0.74/2.14 | 0.57/0.64 | yes:6/7.5; no:6/3.5; unknown:0/— |
Checks mean a validation instruction, numerical completeness bound or explicit all/never behavior in the opening; a broad improvement request does not qualify. Unknown openings stay unknown. Written checks show no pooled reduction (yes median 5.5, no 5); harder work is confounded. Size partly uses span, so size/day correlations are descriptive and partly circular; open days are censored, not time to done.
Known but unstated: precise density, zoom and folding preferences (A/F); deadlines and retention policy (B); entity mappings (C); terminology and report shape (D); scope, accounts and spend limits (E). Some are learned by reacting, not recoverable by longer questioning.
Nobody yet knew: render/browser faults (A/C), test cost/custody/restore feasibility (B), dirty sources and broken joins (D), actual gates/session state/source yield (E), capacity/authentication/client compatibility (F). Preserve discovery rather than charging it all to deficient briefs.
Already written but unused: complete-update and folding instructions (A), optional-save/one-card rulings (B), catalog authority (C), requested fields and existing inventory (D), contracts/golden examples/context limits (E), supplied brand references and whole-screen constraints (F). A’s source sometimes says inferable rather than demonstrably written; retain that uncertainty.
Scope changes are separate: later additions are not retroactive omissions. E’s original annotations conflate some missing preferences with later changes; no percentage of “what he knew but omitted” or accepted-scope coverage is defensible.

| Method part | Assumed share of each cause removed | A/B/C/F cycle equivalents | D/E, separate | All, descriptive |
|---|---|---:|---:|---:|
| agreement | 20–40% intent; readback, done lines, reserved owner decisions | 12.4–24.8 | 9.2–18.4 | 21.6–43.2 |
| checker | 40–70% quality + 10–25% tooling; reproducible faults caught before showing | 26.6–49.1 | 41.4–75 | 68–124.1 |
| rule_book | 20–40% intent + 10–25% unnecessary; prior ruling is retrievable and relevant | 15.8–33.3 | 11.7–24.7 | 27.5–58 |
| defaults | 30–60% unnecessary; reversible and already within granted authority | 10.2–20.4 | 7.5–15 | 17.7–35.4 |
| watch | 40–75% status/nudge + 10–20% tooling; detect and recover without owner | 17.8–33.8 | 20.2–38.3 | 38–72.1 |
| one_door_record | 60–90% relay + 10–25% tooling; carry context and verify delivery | 8.2–15.7 | 19.6–32.8 | 27.8–48.5 |
These are explicit low/high replay assumptions, not measured effects or confidence bounds. Assume disjoint preventable subsets within each cause; cumulative high fractions never exceed 100%, so no return is budgeted twice. Combined scenario: 91–177.1 equivalents from the comparable 389; 200.6–381.3 from the descriptive 759. A successful watch/default must avoid adding its own owner questions.
All 223 decision and 35 changed-wish returns remain in these scenarios; labels do not prove every one irreducible. Truly personal taste, risk/spend/privacy choices and unforeseen discovery remain. Their exact irreducible count is unknown; the remainder also includes system failures the method does not prevent.
Par is attainable for bounded work: a01/a06/a07/a12/C02/C13 have clear endpoints at or below their assigned par. Some need only acceptance because no historical agreement was shown; this does not prove the proposed full loop works. Clear-path median is 3 versus median par 2.
Large paths range 4–55 returns (median 12); matching history would require par that high, which would hide failures. Only a05 has both clear endpoints among large paths (7 versus par 2); C08 has a bounded approval at 8 with its opening censored. No empirical large-goal par is established. Keep 2 per independently acceptable slice plus taste showings; vary by genuine owner choice/kind, not elapsed size alone.

Ten worst paths by normalized returns; each remains unaccepted:

- **D07 — Usable test leads: 55 returns / par 2; 19.095 observed days.**  
  Inventories and completion reports repeatedly replaced complete, usable records; requested fields and validation had to return.  
  Scope later narrowed; the last action asks for a fresh plan, so no delivery acceptance can be inferred.
- **D04 — One future schema: 54 returns / par 4; 20.072 observed days.**  
  A diagram legitimately grew into a shared schema; later revisions lost detail and revived superseded authority.  
  Restoration and handoffs consumed returns, and the last transfer identified the wrong helper.
- **D05 — Reusable feedback loop: 50 returns / par 4; 22.128 observed days.**  
  Broken tabs, versions, markers and comment delivery repeatedly made the owner test the communication tool.  
  Praise and permission to extract agent-annotate were partial decisions, not acceptance of the full loop.
- **E14 — Manual ingestion comparison: 32 returns / par 2; 10.213 observed days.**  
  The coordinator disappeared, restored workers needed managing, and the owner repeatedly checked activity and closure.  
  Later scope and a reboot added work; blocked gates and lifecycle failures remain at cutoff.
- **a08 — Fast review and preserved typing: 32 returns / par 2; 10.474 observed days.**  
  Retry, delivery and performance failures returned to him; a faster-machine approval did not survive actual use.  
  Editing/deletion/splitting added scope; repeated slowness and lost work prevent a final acceptance.
- **B03 — Recurring housekeeping: 30 returns / par 2; 11.103 observed days.**  
  The owner repeatedly found blocked or stale work and asked for action rather than another list.  
  Cadence, rule continuity and dropped packets remained live despite implementation receipts.
- **E01 — Shared orchestration design: 30 returns / par 2; 4.395 observed days.**  
  Choices about stack and subscription policy mixed with repeated requests to validate capabilities and prevent drift.  
  Context and workflow were resupplied across revisions; no bounded design acceptance survives.
- **E11 — Dispatchable planning pack: 27 returns / par 3; 0.965 observed days.**  
  An already explicit linter/review brief still produced missing inputs, invented workflow and contradictory contracts.  
  The owner pasted independent reviews; the final tracker/execution transition does not accept the whole pack.
- **B11 — Workspace inventory and cleanup: 23 returns / par 2; 4.082 observed days.**  
  Inventory was followed by repeated pushes to remove approved paths and explain preservation/custody.  
  Partial removal and further questions remained; board receipts do not accept the complete cleanup.
- **E06 — Valid data through every gate: 20 returns / par 2; 1.095 observed days.**  
  The owner resumed a dirty handoff, chased silent workers and repeated reviewer authority and evidence requirements.  
  A record-by-gate ledger and handback followed; clean changes did not establish end-to-end success.

Audit: read all 50 seeded random normalized cycle rows, including complete text and retained source context: 32 chats matched the frozen snapshot (F legitimately strips ambient context); 18 page Sends matched frozen time/comment membership. Found 0/50 normalization/source mismatches, not zero semantic errors: 2/50 mixed D messages expose secondary-goal ambiguity; 2/50 D rows are choice-label-only words. Cause accuracy was not independently rated.
Message labels join 508 distinct chat rows, not page Sends. After explicit mapping and excluding unmatched goal/supply/other labels, agreement is 243/383 (63.4%) with labeler a and 246/415 (59.3%) with b; their own exact labels agree 405/508 (79.7%). Largest disagreements: a calls 16 goal-path tooling returns nudges; b calls 15 quality fixes. One pasted owner-supplied review is flagged nonhuman only by a. Labels support repeated corrections, but not precise cause allocation.
Trust: counts are observed lower bounds conditional on these selected boundaries, not population estimates. Missing original requests, acceptances, page payloads and helper/M5 chat can change counts, grouping and cause shares. A second-Mac corpus exists at final validation but is outside this frozen goal-file baseline; no other Mac was contacted. Minutes, literal typed-word shares and causal savings cannot be measured. Frozen inputs and row IDs make arithmetic reproducible, not the judgments independently correct.
