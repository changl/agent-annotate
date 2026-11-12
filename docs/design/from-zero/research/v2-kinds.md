# V2 — Project B: what the review must hold

He needs to compare related things while answering each decision separately. He also tests the product, stops a batch when a shared fault makes further comments wasteful, and rewrites the premise when the offered options miss the real problem. Neither a single-item viewer nor one long document covers those actions.

## Sample and counting

DATA = `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112`.
Read the two Project B pages: 70 evenly spread versions from 804 retained main-page publications, v1–v809, and all 74 audit-page versions, v1–v74. Added main v630 for the animation case: **145 distinct versions**. The live pages continued changing; the publication cutoffs stay fixed.
`DATA/v3/v2/units.jsonl` contains **147 focal review-unit observations**: one per spread-sampled version, two additional objects on sampled pages, and the animation addition. This is a manual sample of focal objects, not a census of every carried-forward card, distinct project goals, or time spent reviewing. Status-heavy audit publications are deliberately overrepresented.
Read sampled published HTML, retained Markdown, card snapshots and linked owner feedback; indexed 252 main-page and 37 audit-page Sends and joined nearby typed-message candidates within two hours. The scripts retain 827 project-matched origin-human candidates; obvious machine handover text was excluded from quotation selection. **29 dated owner quotations**, including four typed messages, are in `his-words.md` under DATA.
Published HTML establishes what was shown. Retained Markdown sometimes contains extra sections absent from that HTML; for example, main v634's Markdown retains an animation that its HTML omits. Main v630 actually contains it.

## Kinds, size, recurrence and answers

Size counts the focal object's screens, states, rows, options or parts, as specified per row. A large underlying inventory can be shown as a few summary groups: those are separate quantities. Scope is not proof he opened every item.
**Passes to completion are not reliably recoverable.** The recurrence column counts publications containing the selected request numbers across retained snapshots: median / largest, with known observation count. Answered cards can remain visible, numbers can change, and old sections persist. These are surface recurrences, not separate owner sittings or completed review passes; no end-to-end pass average is claimed.

| Kind | Observations | Typical size / largest | Request-bearing versions: median / max (n) | How he answered |
|---|---:|---|---|---|
| plan | 14 | 4–5 parts / 7 | 1 / 4 (6) | Conditional approval; adds coverage, execution order and proof requirements |
| architecture | 13 | 3 parts or options / 6 | 1 / 54 (11) | Questions the mechanism; writes an alternative; rejects a repeated failed approach |
| flow | 7 | 8 steps or cases / 61 declared screens | 7 / 163 (6) | Changes the shared rule, then approves individual consequences |
| diagram | 1 | 44 boxes / 44 | 21 / 21 (1) | Staff behavior approved separately; member behavior remained unsettled |
| screens | 15 | 4 states / 48 | 2 / 47 (9) | Accepts many, points at exceptions, applies one correction across platforms |
| behaviour | 3 | 3 states / 4 displays | 8 / 11 (2) | Requires actual motion or capability proof; still pictures are insufficient |
| performance | 16 | 3 comparison rows / 7 runs | 2 / 12 (12) | Accepts some actions; challenges denominators, comparison scope and trial length |
| data | 11 | 3 shown groups / 23 logos | 1 / 22 (8) | Selects a cohort, limits future authority, asks to reconcile actual records |
| code | 0 | No code/diff judgement identified | — | Shell command boxes were operational instructions, not a code review |
| decision | 20 | 2–3 choices / 17 | 3 / 5 (17) | Picks independently; often replaces an unnecessary either-or |
| status | 40 | 3 rows or milestones / 8 | Not applicable | Challenges contradictions or nudges; silence does not prove he read it |
| other: owner actions | 7 | 3 steps / 5 command boxes | 6 / 7 (3) | Supplies access or performs a step; disputes steps already completed |

The extreme recurrence is a warning about the record: the email-flow request numbers occur in 163 publications without establishing 163 human reviews. Main v141's 48-screen request set occurs in two snapshots, while later fixes use other numbers and a later source names a third web round. The animation source names round 5c. Neither number alone measures passes until the whole unit was accepted.

## Together, apart, and what the evidence supports

- **Screens, 2–48 states:** compare related platforms and the accepted reference together, with a separate answer at each state. In main v141 he spotted mismatched steps, shared spacing faults and missing hazards. Main v164's five offline pairs let him accept four and correct one common button rule.
- **Screens with a shared fault:** stop the batch and fix the shared rule first. In main v128–v129 he paused after ten screens and said the remaining screens would attract the same comments. More individual cards would have multiplied his effort.
- **Flows and diagrams, 8–61 screens or 44 boxes:** retain the whole journey and let him inspect a branch. Main v36's model correction changed the relationship between an event and its routes; it could not be judged from one isolated screen. Main v526 links visible screens to staff, server and inbox actions.
- **Architecture, three alternatives:** keep options and trade-offs together. Main v269 compares the current chat path with two replacement paths; he challenged the shared backend assumption rather than merely choosing the recommended option.
- **Performance, 3–7 rows:** keep comparable configurations and coverage together. Audit v2 prompted missing cache and attribution comparisons; main v681's seven-run chart made setup costs distinguishable from test time. These are published measurements, not measurements rerun for this research.
- **Independent decisions, 2–17 choices:** give each its own evidence, consequences and answer. Audit v18's inventory did not move him forward; after he requested separate contextual cards, all eight audit v19 decisions were answered in one Send. This supports separate decisions within shared context, not eight separate pages.
- **Data at volume:** show a summary beside drill-down to the exact rows. Audit v73 covers 192 branches, 12 checkouts and terminal behavior; he allowed today's branch batch but declined a standing rule. Audit v66 summarizes 497 assessed items in seven rows. Neither record proves he inspected every underlying item.
- **Behavior and manual actions:** one current step can be lighter, but its surrounding state must remain available. The four-display animation needs simultaneous platform context; the five CI command boxes need an ordered stopping and recovery point.
- **Status:** one current plan with dated progress works better than accumulated chronological prose. Audit v5 asks for the complete ordered plan; v23 and v50 show that repeated status text without a continuing effect still makes him check manually.

These are evidence-based design judgements, not an experiment comparing two interfaces. The selected rows also record the inferred better arrangement; do not treat those labels as measured preference rates.

## Visible friction, ranked

Manual coding retained **32 friction occurrences in 31 focal observations**. Counts describe these selected episodes, not their prevalence across every question. Raw quotes and exact source IDs are in `friction-episodes.jsonl` under DATA.

| Friction | Occurrences | One paraphrased example |
|---|---:|---|
| Mechanics, purpose or consequences unclear | 9 | A proposed rule repeated his words without showing what would actually run (audit v46). |
| Settled feedback or questions returning | 6 | An approved repair came back unchanged as another request (audit v56). |
| Evidence wrong, mismatched or not yet proved | 6 | Paired web and phone pictures represented different steps (main v141). |
| Information buried, fragmented or ordered badly | 3 | A plan was at the bottom while its supposed decision cards were missing (main v572). |
| Text where a useful visual was needed | 2 | An email needed visible journey instructions, not more prose (main v234–v235). |
| An unnecessary owner step | 2 | He was asked to grant editing access already available (main v280). |
| Work invisible or apparently stalled | 2 | Cleanup totals were reported while visible clutter grew and active work had stopped (audit v23). |
| Missing separate, usable decision cards | 2 | A broad inventory needed concrete decisions with context and trade-offs (audit v18). |

## The twelve design tests

Exact page directories, version IDs, source files, picture paths and hashes are in `DATA/v3/v2/test-set.json`. Main and audit name the two directories in `inventory.jsonl`. Every observed kind is covered; performance has two cases. These cases are hard for different reasons, not ranked by a synthetic difficulty score.

| ID / page version / kind | Asked; why difficult | What he did | An ideal showing would let him… |
|---|---|---|---|
| T01 main v36 / flow | 61-screen admin proposal, five jobs, four decisions; prototype elsewhere and a wrong event/route model | Corrected the model and chose the remaining rules | See every journey, compare phone/desktop, and change the shared rule at its affected steps |
| T02 main v141 / screens | 48 web states beside phone references; visual parity and capability mixed | Accepted most; flagged repeated faults and wrong comparison states | Compare matching states, apply a shared correction once and keep individual exceptions |
| T03 main v526 / diagram | 44 boxes, four actors and four journeys; visible screens mixed with automatic and unfinished work | Approved staff behavior separately; member flow was redrawn | Read the whole diagram, trace a path and open the actual screen or decision at a box |
| T04 main v630 / behaviour | Thinking animation on two phones and still car displays; a static rendering loses the object | Rejected the prior still proposal and required real motion with the last turn retained | Play, pause and inspect the transition beside the accepted state |
| T05 main v681 / performance | Seven timing rows, 150 capture variants, module coverage and a trial | Approved four actions; shortened the trial | Compare like configurations, inspect a capture failure and answer each trade-off |
| T06 audit v2 / performance | Usage by role, output per cost and five changes; missing comparison axes | Accepted some changes, asked for cache and attribution analysis | Keep assumptions and denominators visible and drill into each recommendation's evidence |
| T07 main v269 / architecture | Three chat choices change privacy, cost, capacity and rebuild effort | Kept the standard but challenged the backend path and target scale | Compare current/proposed paths and tie each choice to privacy and load proof |
| T08 main v48 / decision | Sixteen policies beside related flows; blanket acceptance also offered | Chose independently, added requirements and challenged the lingering blanket card | Answer each policy while carrying shared rules across affected screens |
| T09 audit v73 / data | 192 branches, 12 checkouts and terminal cleanup; batch and standing authority differ | Limited branches to today's list; approved the other actions | Inspect exact rows and exceptions, then choose this batch separately from future policy |
| T10 audit v54 / status | Earlier successes versus later hourly failures; promise and actual job must be reconciled | Challenged the contradiction and changed lead; later approved repair | Compare the promise, dated run history, current effect and failure delivery |
| T11 main v479 / other | Five command boxes on another Mac, with prerequisites and stopping rules, mixed with product choices | No linked receipt for the boxes; adjacent feedback simplified two product rules | Work through one ready step with expected output and a durable return point |
| T12 main v117 / plan | Five workflows across four surfaces, scripts/models, account scope and optional human participation | Approved outline, required finer method and model choices | Inspect coverage by case/platform and see which steps need a script, model or human |

**T01 has a historical-asset limit:** v36 embeds no pictures and declares 61 screens. The linked local artifact has since become round two, declaring 65 screens/130 images; 216 PNGs survive including an earlier archive. Exact current files are supplied and hashed, but they do not establish the original v36 pixels. A design must surface that distinction rather than imply a frozen historical comparison.
Text/table/command cases deliberately have empty focal picture lists. T08's related flows remain in its full published HTML. Do not manufacture pictures and call them historical evidence.

## What he has asked for over time

Paraphrases below concern the review surface unless marked as a product-screen observation. Dated wording and provenance remain in `DATA/v3/v2/his-words.md`.

- **1–2 October:** show the three related admin groups together; mark visual or experience work ready for his final look.
- **13 October:** do not bury necessary material in history or another dropdown; prove car-screen feasibility before asking for detailed review again.
- **20 October:** do a shared density and wording repair before asking him to repeat the same comments on every remaining screen.
- **26–27 October:** show the complete corrected menu; show pictures of the defect and proposed fix before asking again.
- **1–2 November:** keep related actions visible together (a product-screen observation); place the reviewed evidence above its feedback card.
- **4 November:** visually distinguish agent work from scripts, explain the value of each, and show which changed area needs testing.
- **6–9 November:** keep the whole ordered plan and earlier approvals together; convert broad recommendations into separate cards with context and trade-offs; continue approved work without repeated nudging.
- **10–11 November:** preserve decisions across handovers; show the actual implementation and prompts; do not repeat a dismissed approach or leave an answered card unchanged.
- **11 November typed follow-up:** reconcile outdated lists and use one maintained place instead of making him align a page and a spreadsheet himself.

## Reproduce and limits

From `DATA/v3/v2/`, run separately: `python3 label.py`; `python3 enrich.py`; `python3 cases.py`; `python3 words.py`. These replay the retained inputs and manual labels; `summary.json` contains every table count and recurrence statistic. `python3 collect.py` refreshes comments/metadata and the fixed-cutoff version inventory, so it is not an exact replay of the original changing page state. `read.py main 0 10` is the bounded reading command; change page/range for other packets.
Run `python3 validate.py` for version coverage, unique row IDs, kind coverage, figure counts, source/asset existence and test-input hash checks. All test-set files were hashed; no listed path was missing. Six representative visual assets were inspected, including two frames and the duration metadata of the six-frame, 1.2-second GIF. This does not claim every pixel in every picture was reviewed.
Not checked: eye tracking, viewing duration, whether silence means an ignored item, a complete goal-level count of passes to acceptance, every old cumulative card, live prototype interaction, real phones/cars, or replay of the published performance runs. Legacy comment version labels can reflect migration rather than the original showing; dated answers and published HTML are kept separate. Sampling and manual labels have no independent second-rater check.
No page, board, session, runtime, skill, setting or other-Mac file was changed. The research used local retained evidence; no remote access was needed.
