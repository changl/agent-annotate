# V1 — Census of the published review surface

Read on 2026-11-12T18:34:56 UTC: **1,612 readable version/host records (1,610 distinct page/version IDs) on 78 pages; all 84 indexed pages checked on both Macs**. Differing mirrored canvases remain separate. The older index lists 1,567 versions.
The files contain **430 feedback Sends, 1,877 items in those Sends, and 5,912 stored comments** (including agent-authored cards). A publication means available to review; it does not prove he opened it.

Reproduce, as separate commands (DATA = `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112`):
`python3 DATA/v3/v1/census.py --self-check`  
`python3 DATA/v3/v1/census.py`  
`python3 DATA/v3/v1/report.py --output docs/design/from-zero/research/v1-census.md`  
`python3 DATA/v3/v1/audit.py`
Expand DATA to its absolute path before running. The census uses only the Python standard library and read-only SSH execution; it writes locally under DATA/v3/v1. The report command writes this file.

## 1. How big is one review?

Each cell is **median / 90th percentile / largest**, per published version. Percentiles interpolate between adjacent sorted values. Smaller-project keys map to original project names in `DATA/v3/v1/summary.json`; each project is separate.

| Project | Versions | Words | Pictures | Diagrams | Tables | Questions |
|---|---:|---:|---:|---:|---:|---:|
| All | 1612 | 4,446/62,254.2/184,719 | 2/606.7/816 | 0/1/10 | 4/33/87 | 2/25/470 |
| Project B | 890 | 11,439/75,639.3/120,530 | 61/790/816 | 0/1/10 | 16/50/50 | 5/39/258 |
| Project C | 336 | 3,360/9,133.5/16,062 | 0/2/32 | 0/0/0 | 3/8/23 | 1/23/30 |
| agent-annotate | 108 | 406.5/1,545/3,244 | 0/8/13 | 0/0/0 | 1/3/7 | 1/4.3/9 |
| smaller projects S02 | 4 | 2,942.5/3,565.1/3,827 | 0.5/1/1 | 0/0/0 | 0/0/0 | 0/0/0 |
| smaller projects S03 | 49 | 1,307/6,490.2/7,655 | 0/0/2 | 0/0/0 | 4/10.2/12 | 3/21/22 |
| smaller projects S04 | 1 | 31/31/31 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| smaller projects S05 | 1 | 4/4/4 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| smaller projects S06 | 73 | 1,943/12,445.8/109,085 | 0/0/0 | 0/0/6 | 4/39.8/87 | 0/0/4 |
| smaller projects S07 | 1 | 2,054/2,054/2,054 | 0/0/0 | 0/0/0 | 5/5/5 | 0/0/0 |
| smaller projects S08 | 1 | 20/20/20 | 0/0/0 | 0/0/0 | 0/0/0 | 0/0/0 |
| smaller projects S09 | 2 | 1,345/1,510.6/1,552 | 0/0/0 | 0/0/0 | 4/4/4 | 0/0/0 |
| smaller projects S10 | 8 | 12,968/13,776.5/13,808 | 0/7.8/12 | 0/0/0 | 23.5/25/25 | 0/0/0 |
| smaller projects S12 | 1 | 4,639/4,639/4,639 | 0/0/0 | 1/1/1 | 1/1/1 | 0/0/0 |
| smaller projects S13 | 30 | 1,099/1,655.3/2,831 | 9/11/21 | 0/0/1 | 1/1.1/7 | 5/5/8 |
| smaller projects S14 | 11 | 1,186/3,354/4,116 | 0/0/0 | 0/0/0 | 2/3/5 | 0/3/4 |
| smaller projects S15 | 1 | 2,475/2,475/2,475 | 0/0/0 | 0/0/0 | 8/8/8 | 0/0/0 |
| smaller projects S16 | 21 | 811/1,451/1,639 | 0/0/1 | 0/0/0 | 3/4/5 | 2/6/9 |
| smaller projects S17 | 3 | 6,009/6,086.6/6,106 | 0/0/0 | 0/0/0 | 1/1/1 | 0/0/0 |
| smaller projects S18 | 18 | 6,303/23,046.2/26,761 | 64.5/254.9/306 | 0/0/0 | 2/4/4 | 0/0/0 |
| smaller projects S19 | 5 | 622/1,320.8/1,524 | 0/0/0 | 0/0/0 | 2/2.6/3 | 0/0/0 |
| smaller projects S21 | 5 | 6,165/7,664.8/8,514 | 0/0/0 | 0/0/0 | 11/15.6/18 | 1/1/1 |
| smaller projects S22 | 3 | 139,794/175,734/184,719 | 0/0/0 | 0/0/0 | 0/0/0 | 386/453.2/470 |
| smaller projects S23 | 40 | 3,236/5,116/8,329 | 0/0/5 | 0/0/0 | 6/9/11 | 2/3.2/16 |

Count the canvas, excluding tool controls, scripts and styles. Words include folded sections, card options, captions, tables and code. Pictures count image occurrences; diagrams count Mermaid, non-icon inline SVG, canvas, and image diagrams; SVG image files without a clear screen label are counted as unclassified diagrams. Those last two rules are upper-bound cues, not visual inspection.
Tables count all rows separately from data-only rows. Comparisons count explicit comparison containers; plain before/after label pairs have a separate weaker count. Frames count iframe/object/embed elements. Links count off-page links, excluding internal jumps and the tool’s full-size image button. Separate Markdown source files and linked destinations are not opened.

## 2. What are reviews made of?

Rules: screen-led = at least 3 explicitly screen-labelled pictures, at least 60% of pictures, and at most 300 words per screen; diagram-led = at least 2 diagrams and at most 400 words per diagram; table-led or question-led = at least half of words inside that kind of element. More than one leader means mixed. With no leader, mostly text requires fewer than 3 pictures, no diagrams, and under 30% of words in tables plus questions; the rest is mixed.

| Kind | Versions | Share |
|---|---:|---:|
| mostly-text | 287 | 17.8% |
| mostly pictures of screens | 351 | 21.8% |
| diagram-led | 5 | 0.3% |
| table-led | 221 | 13.7% |
| question-led | 112 | 6.9% |
| mixed | 636 | 39.5% |

## 3. How does he answer?

| Items in one Send | Sends | Share |
|---|---:|---:|
| one | 152 | 35.3% |
| 2–5 | 173 | 40.2% |
| 6–20 | 94 | 21.9% |
| >20 | 11 | 2.6% |

Words per sent item: **0/71/777** (median/p90/largest), including button-only answers as zero; among nonempty items: **35/109/777**. Send notes are counted separately from item words. Known UI-generated choice labels and duplicated stored decision/reply events are stripped; pasted text still counts as submitted words, not physical keystrokes.

| Attachment | Human-authored comments | Stored comments with a human answer/reply | Sent items |
|---|---:|---:|---:|
| paragraph | 73 | 76 | 43 |
| picture | 41 | 41 | 41 |
| point on a picture | 22 | 22 | 22 |
| question card | 0 | 2199 | 1631 |
| section | 89 | 198 | 41 |
| table | 4 | 4 | 0 |
| table row | 32 | 88 | 5 |
| unknown | 2 | 2 | 0 |
| whole page | 100 | 100 | 94 |

Human-authored notes on a picture or a point on one: **63 (17.4%)**; on text paragraphs/sections: **162 (44.6%)**. A question card beside a picture remains a card attachment; it is not silently relabelled as a picture comment.
Attachment uses the saved target tag/point, then the exact version’s anchor, then an anchor prefix. Original version/anchor is preferred over later carried placement. “Section”, “comparison”, “table” and “unknown” remain distinct; they cannot safely be called paragraph notes.

## 4. How often does the same thing return?

Match sections/questions by saved anchor and pictures by full asset path. The same path may hide replaced pixels; renamed or reissued items are not joined. Changes compare normalized text plus linked image paths, not rendered pixels. “Until last change” is an observed publication span, not proof the item has finished.

| Repeated item | Distinct items | Appearances median/p90/max | Versions until last change median/p90/max | Never changed | Still changing at last appearance |
|---|---:|---:|---:|---:|---:|
| section | 1962 | 4/83/348 | 1/6/789 | 1024 | 503 |
| section-heading-only | 86 | 2/2/2 | 1/1/2 | 85 | 1 |
| picture | 3478 | 10/240/287 | 1/1/109 | 3205 | 46 |
| question | 1784 | 3/51/162 | 1/3/100 | 1496 | 143 |

For 1119 repeated question IDs with a linked answer time, appearances by the first answer: **2/9/40**. Other questions have no trustworthy answer link in the captured files. Repeated sections do not imply repeated requests to reread every word.

## 5. Largest and most revised

Page keys resolve through `DATA/v3/v1/page-key.jsonl`; each version row gives its exact host and `source_path` (use SSH for M5 files). Counts are words / pictures / diagrams / tables / questions. Left ranks versions by words; right ranks pages by readable publication count, with that page’s largest version and counts. Rankings and word changes also live in `summary.json`.

| Largest version: project / page / version | Counts | Most revised: project / page | Versions (revisions) | Largest version and counts |
|---|---|---|---:|---|
| smaller projects P077 / v3 | 184719 / 0 / 0 / 0 / 470 | Project B P050 | 805 (804) | v105: 120530 / 706 / 4 / 24 / 258 |
| smaller projects P077 / v2 | 139794 / 0 / 0 / 0 / 386 | Project C P067 | 196 (195) | v34: 12415 / 0 / 0 / 3 / 29 |
| Project B P050 / v105 | 120530 / 706 / 4 / 24 / 258 | agent-annotate P002 | 95 (94) | v5: 3244 / 0 / 0 / 7 / 1 |
| Project B P050 / v104 | 120456 / 706 / 4 / 24 / 258 | Project C P070 | 75 (74) | v34: 12415 / 0 / 0 / 3 / 29 |
| Project B P050 / v103 | 119748 / 704 / 4 / 24 / 257 | Project B P051 | 74 (73) | v19: 3520 / 0 / 0 / 3 / 8 |
| Project B P050 / v102 | 116352 / 690 / 4 / 24 / 252 | Project C P068 | 39 (38) | v13: 2585 / 0 / 0 / 10 / 12 |
| Project B P050 / v101 | 115339 / 683 / 4 / 24 / 251 | smaller projects P053 | 30 (29) | v3: 2831 / 21 / 0 / 7 / 8 |
| Project B P050 / v100 | 113811 / 675 / 3 / 24 / 249 | smaller projects P084 | 30 (29) | v14: 5910 / 0 / 0 / 10 / 1 |
| Project B P050 / v99 | 112981 / 674 / 3 / 24 / 248 | smaller projects P063 | 17 (16) | v16: 26761 / 306 / 0 / 4 / 0 |
| Project B P050 / v98 | 112963 / 674 / 3 / 24 / 248 | smaller projects P012 | 15 (14) | v2: 1314 / 0 / 0 / 7 / 4 |
| Project B P050 / v97 | 112949 / 674 / 3 / 24 / 248 | smaller projects P060 | 15 (14) | v2: 1498 / 0 / 0 / 3 / 9 |
| Project B P050 / v96 | 109691 / 663 / 0 / 24 / 244 | Project C P074 | 13 (12) | v13: 5186 / 0 / 0 / 7 / 12 |
| smaller projects P035 / v11 | 109085 / 0 / 0 / 2 / 0 | smaller projects P030 | 13 (12) | v12: 3442 / 0 / 0 / 8 / 0 |
| Project B P050 / v95 | 105270 / 598 / 0 / 24 / 243 | smaller projects P035 | 11 (10) | v11: 109085 / 0 / 0 / 2 / 0 |
| Project B P050 / v94 | 103212 / 583 / 0 / 24 / 243 | smaller projects P037 | 10 (9) | v4-5: 40488 / 0 / 0 / 87 / 0 |
| Project B P050 / v93 | 102997 / 580 / 0 / 24 / 243 | smaller projects P043 | 8 (7) | v7: 13808 / 6 / 0 / 25 / 0 |
| Project B P050 / v92 | 99822 / 537 / 0 / 24 / 239 | smaller projects P016 | 8 (7) | v1: 3481 / 0 / 0 / 12 / 9 |
| Project B P050 / v91 | 99784 / 536 / 0 / 24 / 239 | smaller projects P056 | 8 (7) | v2: 4116 / 0 / 0 / 3 / 3 |
| Project B P050 / v90 | 96265 / 491 / 0 / 24 / 234 | Project C P075 | 6 (5) | v5: 1520 / 0 / 0 / 9 / 12 |
| Project B P050 / v89 | 94659 / 488 / 0 / 24 / 233 | smaller projects P015 | 6 (5) | v4: 7630 / 0 / 0 / 11 / 21 |

## 6. Coverage and what this cannot tell us

Self-check tolerance is **zero versions** per primary page: `assert versions_read == versions_published`. 74 passed; 10 mismatched; 0 collection errors. Every mismatch follows; extra mirrored variants are separately recorded. `coverage.jsonl` retains expected count, unique history IDs, missing IDs, file-only IDs and parse notes.

| Page key | Indexed | Read | Missing published HTML | File-only versions |
|---|---:|---:|---:|---:|
| smaller projects P053 | 15 | 30 | 0 | 15 |
| smaller projects P058 | 1 | 0 | 1 | 0 |
| smaller projects P059 | 2 | 0 | 2 | 0 |
| smaller projects P065 | 1 | 0 | 1 | 0 |
| agent-annotate P002 | 94 | 95 | 0 | 0 |
| smaller projects P008 | 1 | 0 | 1 | 0 |
| smaller projects P010 | 1 | 0 | 1 | 0 |
| Project B P050 | 788 | 805 | 0 | 3 |
| Project B P051 | 71 | 74 | 0 | 1 |
| Project C P067 | 183 | 196 | 0 | 1 |

Rows include 6 unavailable published versions with null counts. Duplicate history entries for one ID are one version; unlisted version files are retained with unknown publication time. Legacy content/ and archived failed-attempt HTML are used when their IDs occur in history. Collection was live rather than an atomic snapshot; index differences do not alone establish data loss.
0 parse notes are recorded under DATA, without page text. The self-check fixture covers canvas isolation, pictures, diagrams/icons, comparisons, tables/rows, code lines, frames, links, question cards and point attachments.
Only rounds.ndjson and comments.json are read for feedback; older sends stored only in the bus, and any newer SQLite-only records, are outside that file-based census. Current comments are mutable and incomplete history: edits, withdrawals, removed comments and repeated answers may no longer survive. A saved author is used to distinguish human from agent; it cannot prove who physically typed.
Word additions/removals align DOM text runs, then word tokens inside changed runs (Python difflib, autojunk=True); reordered passages can appear as deletions plus additions. This is one reproducible edit alignment, not a unique editorial history. First-version deltas are the baseline. Picture additions count new occurrences by asset path; replaced pixels at the same path and renamed questions cannot be tracked reliably.
Also checked 13 mirrored page registrations on M5: 572 version files, 0 shell-only differences, 2 new/different canvases, 0 extra comment IDs and 0 extra Send IDs. Any additional records are marked mirror_variant; identical copies are counted once. Existing mirrored comment IDs use the primary page’s latest saved record, not the older copy.
No browser rendering, pixel classification, viewport/scroll observation, link opening, active-prototype interaction, time spent reading, comprehension, approval quality or causal effect is measured. Image backgrounds, CSS drawings and content generated only by JavaScript can escape counts. Largest stored payload does not mean largest attended review.
