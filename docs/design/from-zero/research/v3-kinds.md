# V3 — What he reviews, and what a surface must handle

The difficult reviews are connected sets: a journey across devices, a whole schema, records with evidence, or an interaction across time. A single picture plus a choice would cover only part of this work. He also needs individual answers at the exact thing being judged.

## Scope and counting

DATA means `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112`.
Read-only research covered **34 pages, 400 sampled publications from 619 surviving publications**: all nine Project C pages, all seven agent-annotate pages, and 18 smaller-project pages chosen for long histories or many questions. M5 Max answered SSH; its original pages and their pictures were checked without remote writes.
Sampling spans each page's lifetime: 60 evenly spaced publications for pages with at least 75, 20 for 20–74, all surviving publications below 20, plus five targeted revisions. The main Project C page contributes 61 and agent-annotate's main page 64. The frozen index and current files differ; both counts remain in `manifest.json`.
The ledger contains **910 units: 886 distinct question prompts, 17 compound legacy artifacts and seven continuing status bodies**. Equal prompts within a project are counted once across migrated pages; question numbers alone are unsafe because they were reused. Counts describe this selected sample, not his usual mix of work. A changed prompt may still be the same underlying job; the twelve cases trace those larger jobs separately.
Sources were read as page text, questions, changed sections and feedback; hard cases also received picture inspection. This is not a claim that all 400 publications were replayed visually in their original browser. `packets/`, `comments-extracted.jsonl`, `project-humans.jsonl` and the case files retain the evidence under DATA.

Reproduce the counts from retained packets, running each command separately:

```text
python3 DATA/v3/v3/label.py
python3 DATA/v3/v3/friction.py
python3 DATA/v3/v3/finish_evidence.py
python3 DATA/v3/v3/check.py
```

`gather.py capture` refreshes source captures; `gather.py packets` rebuilds readings; `humans.py` rebuilds the typed-message search. `cases.py` rebuilds the twelve case records and checks picture paths, including on M5; `visuals.py` builds inspection sheets. Refreshes are not an atomic historical snapshot. The commands and input hashes are in `inputs.json`.

## Kinds, size and answering

“Outside audit” removes one exceptional 470-card configuration audit. Typical sizes below describe the shown choice or artifact, not time spent looking. A size of two options says nothing about the size of the plan those options concern.

| Kind | Units / outside audit | Typical showing; largest checked packet | How he answered; passes that can be traced |
|---|---:|---|---|
| Plan | 17 / 17 | Scope and sequence with several policy choices; a 14-slide plan and a test plan preserving 194 steps across 20 journeys and 27 page types | Selects choices, changes scope, then authorizes work. Project C's plan spans several publications; its exact acceptance boundary is incomplete. |
| Architecture | 45 / 45 | Usually three options or responsibility layers; a 13-decision operating standard | Writes requirements and asks who owns which part. The backup design takes five publications and five returns to a simpler accepted direction (T02). |
| Flow | 8 / 8 | A step and its related states; 159 native proof rows with 273 picture references (T03) | Points at placement and changes the rules for exceptions. Unresolved failures remain; no completed-pass count. |
| Diagram | 2 / 2 | A workflow map or a full schema; **57 tables, 118 connections, 366 listed columns** (T04) | Asks for the whole map, points at relationships, reports clipping and asks to comment on individual parts. Completion is unproved. |
| Screens | 78 / 78 | Often two alternatives; **30 reference screens** in one browser/width matrix (T05) | Picks options and corrects specific places. The reference set has one reported approval return; Send's redesign takes five returns across eleven publications (T12). |
| Behaviour | 30 / 30 | One interaction with two or three choices; 12 independently answerable interaction examples, or five animated concepts with three-size previews and storyboards (T06) | Rejects unclear storytelling, chooses a direction with changes, asks for storyboards before more animation. The revised direction remains open. |
| Performance | 13 / 13 | Before/after measurements, usually three choices; cost, latency, load and trial matrices | Challenges denominators and explanations, asks for useful totals. The waiting-cost revision has two returns over four publications (T07). |
| Data | 283 / 61 | Wording alternatives or changed records; **900 records**, with full fields, missingness and reasons (T08) | Specifies rows and fields, requests the actual values and corrects summaries that conceal missing data. End-to-end acceptance is absent. |
| Code | 233 / 1 | Literal diffs or copy-ready configuration; **232 inline diffs** inside one 454-finding audit, plus 16 owner choices (T09) | No answered audit cards recovered. This exceptional audit supplies 232 units; it does not establish frequent source-code review. |
| Decision | 191 / 175 | Usually two options, largest five | Picks an option or supplies a missing answer. He also sends routine technical judgement back to the agent (T10); exact underlying-job passes often cannot be recovered. |
| Status | 10 / 10 | An ongoing table or proof report; a 30-pane restore inventory | Often nothing to answer. No response is not approval, and continued publication is not a review pass (T11). |

No separate “other” kind was needed. Most unit-level `passes` remain unknown: carrying an answered card, republishing a table or moving a page cannot establish another owner pass. Known case spans count publications explicitly and list actual returns separately; they are not a sample-wide median.

## Together or one at a time

| Kind and size | What the evidence supports |
|---|---|
| Screen alternatives, two at a time | Together at readable size. On 16 October he explained that small phone screens belong beside one another, while desktop designs need vertical space. He wanted most review inline, with enlargement exceptional. This is a size-dependent rule, not one fixed comparison layout. |
| Reference screens, 30 | The page offered separate answers to every exact picture and later reports all 30 approved. A page × browser × width matrix would support comparison without removing those independent answers. The record does not prove which comparison order he used. |
| Independent behaviours, 12 | On 29 September he rejected a grouped text choice and asked for visual examples he could answer individually. The separate motion page followed. Keep the alternatives accessible together, but try and answer each interaction separately. |
| Animated concepts, five then three | Together for the storyboard comparison; one replay at a time for timing and meaning. In the second round he asked to settle the storyboard before producing more animations. Evidence does not support a compulsory wizard. |
| Native flow, 159 proof rows | Related states need comparison: same step, device, keyboard and font size. Reviewing one isolated capture would conceal pointer and obstruction problems in adjacent states. This is an inference from the matrix and his exception decisions, not a measured layout trial. |
| Diagram, 57 tables | The whole system must remain available while a box, connector or worked example is examined. He explicitly objected when revisions kept changes but lost the complete schema. One isolated node would remove necessary context. |
| Data, 900 rows | Together as an explorable set, with one row/field available for judgement. His July messages asked for actual values and separate contact fields; aggregate probe summaries did not suffice. |
| Architecture and performance | Compare consequences, coverage and denominators together. The backup review moved toward one inclusive folder because maintaining exclusions and scattered lists imposed work. He asked another cost review for one monthly total per stage rather than a formula to decode. |
| Mixed Send review, 11 answers and three comments | Show the entire real dialog. Cropped top-only pictures made him ask whether functions had disappeared. A later illustration also had to accommodate rounds with more than 30 long replies. |

## Friction, ranked

These are **39 manually retained page-feedback remarks**, one primary category per remark, with raw quotes and dates in `friction-ledger.jsonl`. They are a bounded evidence set, not a frequency estimate for all his work. Typed-message evidence supports the examples but is not added again to this denominator.

1. **Missing or incomplete showing — 12.** A schema revision omitted the full map; a visual choice arrived as text; an animation's story was not understandable from its execution.
2. **Navigation and space — 10.** Relevant work was below finished items; a desktop comparison was too small; the diagram's right side was clipped.
3. **Unclear controls or states — 5.** A feedback symbol did not explain its purpose; version and unread indicators reused a colour with conflicting meanings.
4. **Repeated or unnecessary questions — 5.** Two cards asked about the same board-follow-up change, or a decision already given was requested again.
5. **Broken review controls — 4.** He could not scroll through a schema tab or retain a draft while changing versions.
6. **Wrong review scope — 3.** He was asked to choose a routine server-lookup implementation, or a redesign removed working functions he had wanted to keep.

## The twelve cases every design must face

Exact page directories, version IDs, source files, picture files, their existence checks and retained local copies are in **`DATA/v3/v3/test-set.json`**. Case IDs below are stable. Each record includes what was asked, why it was hard, his response and the ideal showing.

| ID · kind · version | Ask and difficulty | What he did; what the showing should enable |
|---|---|---|
| T01 · plan · Project C v80 | Approve the test plan alongside five account, safety, browser and retention choices; the plan itself is another view. | Choices persisted before build authorization. Keep the complete coverage and limits visible, with distinct policy answers at their evidence. |
| T02 · architecture · smaller projects v1–v5 | Select a backup design across three machines while sync, restore, storage and cleanup had become entangled. | Wrote requirements, rejected fragmented upkeep and chose one folder. Compare coverage and show an actual one-file/version restore. |
| T03 · flow · smaller projects v17 | Judge onboarding across 159 proof rows and 273 pictures, multiple journeys, fonts, keyboards and builds. | Changed pointer rules and accepted bounded exceptions; failures remain. Navigate by step and compare exact related states with build identity. |
| T04 · diagram · smaller projects v4-6 | Review the complete 57-table schema and its 118 relationships. | Asked for completeness, readable space and precise pointing after clipping and scroll failures. Keep an overview, readable detail and box/connector comments together. |
| T05 · screens · Project C v177 | Approve 30 page/browser/width references for future regression checks. | All 30 are later recorded approved. Compare the same page across browsers and widths, retaining one answer per frozen picture. |
| T06 · behaviour · smaller projects v3–v4 | Choose among five silent animated stories with three-width previews and storyboards. | Rejected unclear execution, then asked to settle a storyboard first. Compare stories and replay/scrub one concept without losing the alternatives. |
| T07 · performance · agent-annotate v70–v73 | Judge coordination-cost evidence whose rates were confounded by a fresh conversation. | Challenged the comparison, then accepted the revised operating proposal. See matched denominators, uncertainty and the proposed action together. |
| T08 · data · smaller projects v4 | Inspect 900 actual records rather than three probe summaries. | Asked for full values, separate contact fields and richer evidence; called the result unready. Filter the set and inspect field-level sources while preserving the prior list. |
| T09 · code · smaller projects v3 | Review 454 findings, 232 literal diffs and 16 owner-only choices across loaded configurations. | No answered cards recovered. Inspect real changed lines and their active scope, grouping related conflicts without blanket approval. |
| T10 · decision · agent-annotate v11 | Choose a technical process-lookup remedy from timing evidence. | Said the agent should determine best practice. See the recommended user outcome and material trade-off, without being made the implementation arbiter. |
| T11 · status · agent-annotate weekly v3 | Inspect progress, delivery and fleet proof with no new decision. | No attributable response recovered. See continuing work, stale evidence and blockers quietly, without inventing an approval. |
| T12 · mixed screens/decisions · agent-annotate v39–v49 | Redesign Send around actual long replies while keeping every working function. | Rejected extra chores and missing functions; accepted the full dialog with notes at the top. Compare whole real dialogs, including lower sections and long rounds. |

## His stated requirements over time

Raw dated words and exact locators are in `DATA/v3/v3/his-words.md`; the following paraphrases do not expose project content.

- **June:** show the full system and actual data relationships; let him point at individual boxes and connectors instead of describing their location in paragraphs. Use expandable space and readable, sortable tables.
- **July:** keep the full baseline available; make every tab scroll; preserve draft comments when moving between versions; use one consistent feedback mechanism.
- **September:** give visual evidence inline or one easy click away; demonstrate independent interactions so he can answer each separately.
- **16–17 October:** adapt comparison layout to image size, do most reviewing inline, bring the work needing him above finished history, and file approved designs where they can be found later.
- **31 October–1 November:** identify pictures consistently; offer 25/50/75/100% zoom with an obvious way in; prioritize what he is sending and an easy final note; retain real functions and demonstrate the whole dialog.
- **2–4 November:** fold the whole completed section, use vertical space efficiently, keep direct tab visibility and use colours consistently for meaningful states.
- **10 November:** avoid duplicate questions about one change and avoid making him repeat established decisions.

## What could not be checked

- No original viewing order, reading time, eye movements or device-at-review can be recovered. “Better” is tied to explicit requests or marked as an inference.
- Not every unit has a complete opening and acceptance. Units with no attributable answer remain unknown; they are not labelled ignored or accepted. Reworded asks can still represent one continuing job.
- The schema index lists ten publications, but only four surviving version HTML files were found. Later branding versions also lack publication timestamps. These gaps remain in the manifest and case notes.
- Original live storefronts, external animation demos, human login flows and full native journeys were not operated. Animation inspection used saved previews/storyboards and sampled frames; timing/audio remains untested.
- The schema picture was replayed with its existing renderer and saved JSON through a read-only local server because its historical relative fetch failed. This establishes the artifact's density, not the exact historical viewport or a current live-page repair.
- Picture inspection is selective: all 30 reference images were viewed as a sheet, six native captures were inspected, and saved animation frames and dialog comparisons were examined. Fine text in the full-page reference thumbnails was not exhaustively checked. All 273 native picture paths were verified on M5, not all 273 pictures visually inspected.
- Legacy handwritten pages are compound units; structured cards are individual units. Neither the counts nor the selected hard cases estimate a population-wide pass rate or prove a three-pass design will work.
