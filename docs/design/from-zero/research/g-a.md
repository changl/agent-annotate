# G-A — Cycles per goal today: agent-annotate

**15 traced goals; 94 observed return cycles; median 3, range 1–32. Ten have explicit result/rollout approval; five lack final acceptance.** The approved ten total 38 cycles against par 26; median 3, range 1–9. This is a deliberately varied case sample, not a project-wide average.

All 15 total par 37; nine exceed their individual par. The 94-versus-37 comparison includes unfinished, censored goals and is not a measured saving. Par is 2 plus genuine new visual choices requiring a showing; repeated corrections to the same choice add no par.

## What was counted

A cycle starts after the first statement: work reaches him and he sends it on. Initial requests are retained separately. One page Send touching several cards for one goal counts once; if it touches several goals, it counts once for each. The 94 goal-cycles represent 74 distinct observed return actions, including 43 page goal-cycles from 30 distinct Sends. These sums are not independent interruptions.

Goal boundaries follow recognisable requests. The speed/draft goal deliberately preserves his original paired complaint; later note-editing and splitting requests are marked as changes. Visual/result approval means he accepted what was shown or authorised the bounded rollout, not that deployment or real-device use was proved. Later rejection removes final acceptance while retaining the earlier approval history.

| Trace / goal | Scope | Cycles / par | Days to approval or cutoff | Later words* | End |
|---|---|---:|---:|---:|---|
| a01 All text adjustable | hours | 1 / 2 | 0.031 | 9 | bundled approval |
| a02 Fold Sent rounds | hours | 3 / 2 | 0.521 | 106 | approved |
| a03 Approved work into Plans | days | 3 / 2 | 4.011 | 0 | approved |
| a04 Find servers without lsof | hours | 1 / 2 | 26.322 | 102 | no final acceptance |
| a05 Stop heartbeat-only turns | weeks | 7 / 2 | 21.141 | 241 | revised rollout approved |
| a06 One History list | hours | 1 / 2 | 0.120 | 0 | approved |
| a07 Rail at every width | days | 2 / 3 | 0.660 | 68 | approved |
| a08 Fast review; preserve feedback | weeks | 32 / 2 | 21.047 | 1595 | no final acceptance |
| a09 Copy/wrap code; fixed header | hours | 2 / 2 | 12.616 | 42 | no final acceptance |
| a10 Durable Answer later | days | 9 / 3 | 11.633 | 471 | approval later overturned |
| a11 Clearer Send dialog | hours | 4 / 3 | 0.066 | 238 | conditional approval |
| a12 Image labels and larger view | hours | 3 / 3 | 0.059 | 228 | approved |
| a13 Plans by topic | hours | 5 / 3 | 0.389 | 167 | approved |
| a14 Clear hierarchy/completed updates | days | 9 / 4 | 1.955 | 1568 | approved |
| a15 Automatic full tests | days | 12 / 2 | 9.604 | 846 | partly superseded; unresolved |

*Words are typed page additions plus complete relevant chat turns; selected answer labels are excluded where the corpus distinguishes them. Shared multi-request chat turns can include unrelated words: these are attributed upper bounds, not keystroke counts. Median later words is 167; summed attribution is 5,681 and double-charges shared turns across goals. Initial statements are separate. **Minutes are null for every goal**: message gaps and answer timestamps do not measure reading, thinking or typing time.

## One cause per goal-cycle

| Cause | Cycles |
|---|---:|
| his_decision | 28 |
| sent_back_intent | 16 |
| sent_back_quality | 20 |
| not_needed | 5 |
| his_change | 3 |
| status_or_nudge | 8 |
| relay | 5 |
| tooling | 9 |

A Send can mix approval and correction. Its one cause is the principal reason this goal needed him again; source answers remain together so that judgement is inspectable. Cause labels and taste allowances are researcher judgements, not button telemetry. The three random recounts checked counts, not independent agreement on causes.

## What the first statement lacked

The recurring problem was usually already stated: fast posts, preserved typing, collapsed deferred questions, script-run tests, visible complete updates. A defensible percentage of final accepted scope cannot be computed without an accepted feature checklist; coverage is qualitative per row, assessed against latest recorded scope for open goals.

Things he knew but had not specified precisely included zoom scales, keeping the Plans dropdown, the exact folding container, badge colours and chip placement. Things nobody yet knew included lock/render costs, browser-specific scrolling and test credential/runtime failures. Things already available but missed included existing Send functionality and real large-round examples, established credential storage, and the requirement to show the zoom entry control. Later requests for note deletion and lazy-loading are scope changes, not retrospectively required first-brief details.

## Three bad paths, five lines each

- **a08:** First complaint paired second-long posts with lost typed comments (`m1max:7f1928c1-cefb-4ce4-a8ea-997366378b14:4d8ffd7cf423:16`).
  Three API retries then required him; later he also asked where the workers were.
  An interim faster-machine approval was followed by reports of no improvement and renewed slowness.
  Editing, deleting notes, splitting and lazy-loading expanded the same goal; delivery failures prompted additional returns.
  Result: 32 observed cycles, par 2; final acceptance absent, despite board closures and improved helper timings.
- **a15:** First statement required script-run, low-token tests with a primary and fallback machine (`m1max:2f2245cf-da72-42db-a20f-5936076e307b:893cdb6c2c7f:5`).
  He redirected an accidentally addressed worker and nudged the orchestrator to collect its work.
  He corrected worker/machine assumptions and an invented credential-storage mechanism, then relayed already-given authority.
  Later evidence reports a change to manual full runs; the final page answer rejects a pinned-browser workaround (`cd95ce32c29f`).
  Result: 12 cycles, par 2; automation was partly superseded and final robust operation was not accepted.
- **a10:** First request specified a consolidated, collapsed Answer later area (`m1max:cc868d0f-e4ae-4715-b12c-ccfdadcae000:b3fc9c36d3ec:25`).
  The first Send also objected to extra clicks; a later design was approved after missed delivery and a status nudge.
  He then found deferred/answered cards still taking space and clarified that the whole evidence section must fold.
  Whole-section folding was approved, but a later general-feedback Send reported deferred items returning (`792900ee644a`).
  Result: 9 cycles, par 3; the later recurrence keeps final acceptance null.

## Coverage, checks and gaps

Inputs available at start: frozen M1 snapshot, questions, rounds, pages, items, tasks and goal candidates. No M5 transcript corpus existed; no other Mac was read. Local page round snapshots add general comments omitted from the question table. Project filtering includes the named project aliases. Inventory: 134 human-labelled turns, 123 session rows, 154 page questions and 49 page rounds; 11 plainly relayed helper messages were excluded from human cycles.

The 51 unselected board candidates are listed individually in `DATA/goals/a-work/rejected.jsonl`: the sample is capped at 15, and filing/closure alone cannot establish a human path. Unrelated work appearing in project-labelled sessions, fixture prompts, early tunnel research without an endpoint, and a screenshot-only regression that could not be assigned safely were also excluded. The 15 were chosen for traceable starts and a spread of size/outcome, with observed failures deliberately retained.

Seeded audit: read all 50 random source rows; three unmarked helper relays (6%) and three initially omitted CI returns (6%) were identified. All six were handled in the final trace. All 26 sampled transcript texts match their raw source lines; 21/24 sampled page-question IDs were found in current comments. Three unanswered legacy SOP IDs could not be revalidated there; they are outside the selected goals. These are distinct checks, not a claimed zero-error corpus.

Second pass, same researcher: seed 20261112 chose a04, a13 and a09. Rereading source actions without the cycle lists gave 1, 5 and 2 cycles respectively, exactly the first counts (maximum difference 0). This is repeatability, not independent validation. Seven helper-session identities are positively observed; full session totals and per-goal tokens remain unknown because goals interleave and page rounds lack session/token attribution.

Missing M5 chat, earlier requests, unassigned general nudges, deleted/reworded cards and unobserved acceptances can add cycles or change boundaries. The traces are observed lower bounds; broad speed/draft grouping makes its maximum especially boundary-sensitive. No attention saving, causal failure rate or population average is claimed.

## Reproduce

`DATA=/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112` (notation only). Run separately: `nice -n 19 python3 DATA/goals/a-work/rebuild.py --hash`, then `nice -n 19 python3 DATA/goals/a-work/audit.py`, expanding DATA to its absolute path. `--collect --sample --hash` rebuilds the source slice/sample; it rereads live local page records, so replay published numbers from the retained `round-snapshots.jsonl` instead. `spec.json` records manual boundaries, causes and source selections; `inputs.json` pins hashes; `summary.json`, `audit-results.jsonl`, `audit-summary.json`, `second-pass.json` and the per-goal JSONL retain the arithmetic and checks. No commits, product changes, page writes, board changes or installs were performed.
