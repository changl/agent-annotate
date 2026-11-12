# V5 — What a check before review could have caught

**Checks alone do not get the longer pieces to three passes.** In 24 selected multi-pass pieces, 20–56 of 230 answers and notes were catchable under the strict/plausible readings (9–24%). Removing only wholly catchable passes gives **70 → 54–63 observed passes: 7–16 saved**. These are replay bounds, not measured savings or completed-work averages.

Nineteen pieces already have at most three observed passes; the same nineteen remain within three under both bounds. All five longer pieces stay above three: phone screen density, account styling, Send/zoom, header/rail appearance and backup design. Several have no final acceptance. Earlier agreement on scope and representative real examples, fewer repeated method/permission gates within granted authority, and early judgement of genuine layout choices would also be needed; this record does not quantify those effects.

The denominator contains 122 positive selections/other answers and 108 notes, including notes attached to selections. The strict catches are four script faults and sixteen checker faults. No repeated question meets the strict same-scope test; three are plausible upper-only cases. Thirty-six uncertain units create the range. “Only you” below also includes uncertainty and mixed notes with a new choice.

## By project and kind of review

Counts by kind are the strict reading. Remaining passes show the plausible-to-strict range; they are not a promise of acceptance.

| Project · review | Pieces | Answers + notes | Script | Checker | Repeat | Only you | Passes → remaining |
|---|---:|---:|---:|---:|---:|---:|---:|
| Project B · behaviour | 3 | 8 | 1 | 0 | 0 | 7 | 7 → 6 |
| Project B · screens | 2 | 130 | 0 | 10 | 0 | 120 | 7 → 7 |
| Project C · architecture | 1 | 3 | 0 | 0 | 0 | 3 | 2 → 2 |
| Project C · behaviour | 1 | 2 | 0 | 0 | 0 | 2 | 2 → 2 |
| Project C · data | 1 | 2 | 1 | 0 | 0 | 1 | 2 → 0–1 |
| Project C · performance | 1 | 4 | 0 | 0 | 0 | 4 | 3 → 2–3 |
| Project C · plan | 1 | 2 | 0 | 1 | 0 | 1 | 2 → 0–1 |
| Project C · plan / performance | 1 | 3 | 0 | 0 | 0 | 3 | 3 → 3 |
| Project C · screens | 1 | 4 | 0 | 0 | 0 | 4 | 4 → 4 |
| agent-annotate · architecture | 1 | 3 | 0 | 0 | 0 | 3 | 2 → 0–2 |
| agent-annotate · behaviour | 3 | 12 | 2 | 0 | 0 | 10 | 8 → 5–6 |
| agent-annotate · performance | 1 | 3 | 0 | 1 | 0 | 2 | 2 → 1 |
| agent-annotate · screens | 3 | 17 | 0 | 0 | 0 | 17 | 10 → 7–10 |
| agent-annotate · screens / behaviour | 1 | 12 | 0 | 1 | 0 | 11 | 6 → 5 |
| smaller projects · architecture | 1 | 6 | 0 | 0 | 0 | 6 | 5 → 5 |
| smaller projects · data / screens | 1 | 16 | 0 | 3 | 0 | 13 | 2 → 2 |
| smaller projects · performance | 1 | 3 | 0 | 0 | 0 | 3 | 3 → 3 |
| **Total** | **24** | **230** | **4** | **16** | **0** | **210** | **70 → 54–63** |

## The four carried cases

| Piece | Answers + notes caught | Observed passes → with checks | What remains |
|---|---:|---:|---|
| 48 web states | 6–12 / 59 | 3 → 3 | Same-state and browser-proof faults shrink the review; positive approvals and a stopped-work choice retain every pass. |
| Send and zoom, first five showings | 1–3 / 11 | 5 → 4 | Removed functions are catchable; new priorities, scales and order remain. v49 already shows size controls, so entry clarity is upper-only. A sixth approval at v51 makes the longer observed span **6 → 5**, still above three. |
| Reroute motion | 1–2 / 4 | 3 → 2 | The rejected still need not reach review; animation approval and build/merge approval remain. |
| Admin flow | 0–1 / 4 | 1 attributable response; second unknown | The prototype repeats the same four answers on round 2. That is no evidence of a second review; excluded from the 24-piece totals. |

Per-piece links, both pass bounds and the original/remaining size of **each pass** are in `DATA/v3/passes/summary.json` and `passes-by-work.tsv`. Every retained pass stays at its original place; accepted answers are not discarded to manufacture a saving. An upper-bound zero means no observed question survives the assumed checks, not that the work is done.

## Smallest useful checklist

These four distinct checks cover all 20 strict catches. Counts are disjoint primary assignments; they measure this sample, not detection rates.

| Check before showing | Real units caught, strict–plausible | Run it with | Give it |
|---|---:|---|---|
| Show what changed for every earlier note | 6–16 | Separate Claude Code or Codex checker, not the maker | Original ask; earlier dated notes; before and now; explicit stopped work |
| Compare the same state with the accepted reference | 6–24 | Separate Claude Code or Codex checker, not the maker | Ask; exact reference state/design rules; candidate; permitted platform differences |
| Open the whole showing and try the promised action | 4–4 | Windmill script; no tokens | Required states/functions; exact candidate and links; target widths; prior accepted feature inventory |
| Match claims and choices to their actual proof | 4–9 | Separate Claude Code or Codex checker, not the maker | Ask; candidate; run results/capability limits; comparison denominators and dates |

Examples: a motion request accompanied only by still pictures; a collapsed rail wider than the phone; set-aside state lost after a new version; mismatched journey steps in a phone/web pair; a clarity revision removing working Send functions. The checklist describes proposed checks; this research deployed no Windmill jobs or checker sessions.

A fifth check would compare proposed questions with earlier dated answers and exact scope. It adds **0 strict / 3 plausible** catches here, so this sample does not justify a separate implementation solely for those savings. Nearby duplicate cards and repeated implementation permission are not automatically the same already-answered question.

## Method

A piece is one identifiable artifact/outcome shown, answered and shown again. A pass is a candidate or materially revised explanation put to the owner and answered; several Sends on one candidate count once. Continuing publication without a response, mirrored comments, carried answered cards and delivery retries add no pass. Explicit work links use state numbers, task identifiers and response-to wording, recorded before coding in `cases.json`. Different questions on one page are not automatically one piece.

The set contains the four required cases plus **21 further multi-pass pieces**: eight review-tool repairs, seven commerce revisions, three vehicle-app revisions and three smaller-project revisions. It is a purposeful spread across kinds and lengths, not a random population sample. The required admin case fails the two-response test and is retained separately. The others total 70 attributable passes in five retained feedback streams; migrated commerce records link back to their original pages and version files.

Read submitted round snapshots first; join original comments/decisions, cards in version snapshots and published HTML/retained source. Consolidated commerce history is counted once. Cross-check against the question corpus and earlier feedback/recurrence records; recurrence corroborates identity but never supplies a pass count. Current comment version fields sometimes drift as cards move: the web-state and motion links use the actual named showing, not the latest stored version number.

One answer/comment is a unit. A positive selection and a separately stored free note are distinct; a rejection and its reason stay together. Paragraphs inside a note are not split. Script means a named executable comparison; checker means a named comparison with an available ask, reference or earlier note; repeat requires an earlier answer covering the same scope. Genuine approval, new taste, new requirements, premise corrections and unsupported comparisons remain with the owner. A mixed note remains in the strict count if any substantive part needs judgement. Full rules and examples are in `rubric.md`.

A seeded random fifth was coded again with first labels/comparisons hidden: **46/47 exact four-kind agreement (97.9%)**. Among units called catchable in either reading, agreement was **6/7**. This was the same researcher, not an independent rater; many easy approvals inflate overall agreement. Two later conservative source adjudications change final counts without rewriting the frozen first reading. No causal reliability claim follows.

A pass disappears only when every unit in it is catchable. Otherwise its size becomes original units minus caught units. This assumes the maker repairs every caught fault before showing, introduces none, and needs no additional owner choice; actual savings may be smaller. No new acceptance is inferred.

Reproduce from frozen private evidence, running separately; replace DATA with `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112`:

```text
python3 DATA/v3/passes/build.py
python3 DATA/v3/passes/report.py
python3 DATA/v3/passes/check.py
```

`gather.py` refreshes source reads; `packets.py` rebuilds the explicit selected set; `provenance.py` joins historical corpus evidence and hashes selected version files. Refresh is not an atomic historical snapshot. Manual first and blind labels are retained data, not model calls rerun by the build. `data/passes.js` follows the merged surface contract and keeps the five-showing Send window, with the later sixth approval recorded separately.

## What could not be checked

No prospective maker → separate checker → repaired showing experiment was run. There is no measured detection rate, review-time saving or proof of three-pass completion. No original device/viewing order survives; acceptance boundaries and older asks are incomplete. The admin round-1 pixels were not preserved. Reference-dependent claims without verified earlier scope/pixels are upper-only.

Retained local originals/mirrors supplied the evidence; no other Mac, live product, login or native-device journey was operated. Two supporting pictures were inspected directly; published/source locators and paths do not establish all historical pixels or runtime behaviour. The 24 pieces are not all project work, and long notes sometimes contain both a catchable fault and a genuine new preference. Their lower bound deliberately preserves the whole note.

Skipped production changes, actual check execution and device tests under the read-only brief. The material risk is treating these optimistic historical replay bounds as a delivery guarantee.
