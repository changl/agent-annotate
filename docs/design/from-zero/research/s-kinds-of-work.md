# S. Kinds of work: showing and checking

**355 finished work records, 8 projects, 12 kinds; blind re-sort 56/60 = 93.3% agreement.** Web pages account for 105/355 (29.6%); tests/reviews/proof 58/355 (16.3%). These are shares of a deliberately spread sample, not estimates of all work.

## Sample and limits

- Window: 14 Aug 2026 08:00 UTC through 12 Nov 2026 08:00 UTC, exclusive end (90 days). Frozen corpus inputs and SHA-256 hashes: `DATA/kinds/inputs.json`.
- Read-only inventory: `bd where` at 148 local project/repository locations, 5 distinct boards, 54 Git common-directory identities. Read every board with `bd list --all --limit 0 --json`; verified all 340 selected beads with live `bd --readonly show --include-comments --json`: 0 identity/status/closure-date mismatches.
- Seed 20261112; sample up to 110 eligible non-epic closed pieces per board project, all eligible pieces in smaller boards, plus eligible merged PRs in Git-only projects. Exclude administrative closures, missing completion text, secret-redacted titles, upstream dependency history, duplicate Git hashes and 3 explicitly linked cross-repository duplicates. Four additional absorbed/bookkeeping/non-completions were removed after record review; 355 remain.
- Projects: agent-annotate 108; FLD 108; Rebex 110; Beads evaluation 7; multi-Mac orchestration 7; CheerTicketing 8; Leadory 5; skills-org 2. All 8 local projects with eligible board/merged-PR records are represented; other repository contents establish context, not invented completions. No other Macs or live accounts were accessed.
- Unit: a completed scoped deliverable, including a completed investigation/decision or prototype. Closure/merge proves the recorded scope, **not** owner acceptance, deployment, or end-to-end product completion. Multiple repairs to one goal remain separate pieces; unresolved goal-level overlap is a limit.
- Random completion audits: 5/50 selection errors initially (10%), then 1/50 (2%) after filtering; all identified errors excluded. All 340 final board records match live metadata. This is receipt/source QA, not a rerun of the products. Audit rows and decisions are retained.
- One researcher re-sorted 60 shuffled rows with first labels and IDs hidden: 56 agree, 4 differ; this measures within-researcher stability, not independent agreement. Disputes were command vs hook, patch kit vs proof, service recovery vs daily automation, app vs emulator recovery. Original labels, blind inputs/answers and reconciliation are retained.
- Rule: classify the dominant requested deliverable, using completion evidence to distinguish a product repair from a test-only repair. Keep security, speed, real-account access and irreversible effects as additional checking constraints, not competing kinds.

## Kinds, sizes and observed returns

Scope phrases describe the sampled deliverables. Median days means **calendar time from creation to closure**, not effort; the 15 Git-only PRs lack opening time. Returns below mean a retained `reopened` event, not every pre-closure correction: 20/340 beads reopened at least once (5.9%); 23 reopen events. All 340 histories include creation, but review-fix cycles without a reopen are not counted, so actual rework frequency is unknown.

| Kind | Pieces / sample share | Typical scope | Median days open | Reopened / histories |
|---|---:|---|---:|---:|
| A. Phone and car apps | 32 / 9.0% | one app journey or native repair | 0.283 (n=32) | 0/32 |
| B. Web pages and interactions | 105 / 29.6% | one page, control, or responsive repair | 0.188 (n=103) | 5/103 |
| C. Words and documents | 18 / 5.1% | one wording set, policy, or document | 0.091 (n=16) | 0/16 |
| D. Pictures and graphics | 15 / 4.2% | one picture family or screen-design set | 0.025 (n=15) | 2/15 |
| E. Stored records and catalog | 12 / 3.4% | one bounded record/catalog batch | 0.029 (n=11) | 2/11 |
| F. Services and APIs | 21 / 5.9% | one endpoint, storage, or service rule | 0.165 (n=18) | 0/18 |
| G. Commands and tools | 24 / 6.8% | one command or reusable tool | 0.057 (n=24) | 4/24 |
| H. Automatic jobs and hooks | 9 / 2.5% | one recurring job or event hook | 0.066 (n=8) | 0/8 |
| I. Install, release and recovery | 36 / 10.1% | one version/environment or recovery | 0.011 (n=31) | 2/31 |
| J. Tests, reviews and proof | 58 / 16.3% | one test lane, review, or proof run | 0.130 (n=57) | 3/57 |
| K. Research, plans and decisions | 14 / 3.9% | one comparison, plan, or ruling | 0.017 (n=14) | 1/14 |
| L. Work rules and cleanup | 11 / 3.1% | one rule set or bounded cleanup | 0.016 (n=11) | 1/11 |

## The showing: result, place, pointing

Looking times are **proposed attention budgets**, not measured viewing times. Phone replay of a command or car journey supports review; it does not replace running it on the intended device. A screenshot of a working feature is limited proof of its behavior.

| Kind | The thing itself; where; looking budget | How he points at what is wrong |
|---|---|---|
| A | Installed exact build, one changed journey; phone/car, mirrored on desk; 1–3 min | Tap/time-stamp the control or freeze a video frame |
| B | Actual served page at agreed widths; phone + desk; 30–90 s | Point at live element or marked screenshot; replay the click |
| C | Rendered document, policy, copy in its real destination; both; 1–3 min | Select words, comment on paragraph or sheet row |
| D | Full-size picture beside reference and in placement; both, desk for fine detail; 30–90 s | Draw/point at the affected object, crop or lettering |
| E | Only changed rows/fields plus actual saved product/account view; both; 1–2 min | Point to row, product, price, image position or diff cell |
| F | Real input → visible response/state, before/after; both; 30–60 s | Select failed case/response field; annotate a trace step |
| G | Actual command on representative input and its file/output; desk, phone replay; 30–60 s | Select command/output line or resulting artifact |
| H | One real scheduled/triggered cycle and its effect, plus next-run/error state; both; 30–60 s | Point at trigger, missing effect, duplicate, time or recovery step |
| I | Working installed version on intended host/device/account; both; 30–60 s | Point at wrong version, failed action, missing audience or failed restore |
| J | The failing case now passing, or actual inspected artifact with exceptions; both; 30–60 s | Point at uncovered step, mismatched picture, skipped cell or unjustified verdict |
| K | The comparison, recommendation or executable plan itself; both; 1–3 min | Select assumption, evidence row, option or proposed done line |
| L | Changed rule/config diff or before/after inventory plus fresh-client result; desk, phone view; 30–60 s | Point at rule, object to retain, missing resource or wrong grouping |

## The checking: script, other helper, owner, proof, undo

Every row assumes the checker is a different helper from the maker. “Owner” means the remaining new judgement; known preferences belong in the helper check. No proof grants authority outside the agreement.

| Kind | Script can check | Second helper can judge | Only he can settle | Proof that can replace his viewing after trust | If accepted wrongly |
|---|---|---|---|---|---|
| A | Build/sign; unit/instrumented checks; native accessibility; fixture state; device/build identity | Agreement, intended flow, screenshot-to-built match; device limits stated | Feel, driving distraction, acceptable trade-offs | Independent exact-build native replay, changed-state pictures and regression receipt; physical proof when required | Minute for code revert; effort for installed builds; sent messages/data disclosure cannot be recalled |
| B | Page/API status; DOM assertions; accessibility/overflow; saved/reloaded edits; agreed timing | Flow and layout against agreement; known visual preferences | New layout/interaction taste and whether the journey feels right | Exact served build and asset identity, independent browser journey, changed-region image, no unchecked exceptions | Minute for local/preview change; effort for live theme; purchases or exposure remain |
| C | Spelling terms, links, placeholders, byte equality, row totals, exports and file opening | Readability, source accuracy, tone and recorded wording preferences | New voice, disputed facts, commitments, and who may receive it | Independent source/wording check plus exact approved text hash and successful rendered readback | Minute for draft; effort for published copy; emailed text or a relied-on promise cannot be unsent |
| D | Decode, dimensions, alpha, aspect ratio, asset hashes and target loading | Product/reference fidelity, legibility, unwanted distortion and established brand rules | Appeal, storytelling, which candidate best represents the product | Independent reference-by-reference visual check, contact sheet and exact deployed asset hashes; sample still shown for new style | Minute for private asset replacement; effort for published galleries; prior public exposure remains |
| E | Exact IDs/counts/currencies/order, uniqueness, constraints, before/after readback, backup and tested inverse | Matches authoritative source and scope; no unintended objects changed | Price/business policy, ambiguous identity, exceptions and risk budget | Independent full-target comparison, affected-ID manifest, verified snapshot/inverse and fresh saved readback | Effort with tested restore; money, lost data, invitations and downstream use may be irreversible |
| F | Contract tests; role/negative tests; schema integrity; error paths; load/latency budget | Agreement, failure boundaries and whether proof covers the actual consumer | Policy trade-offs: availability, privacy, compatibility and acceptable loss | Independent positive/negative consumer replay on exact service build, preserved-state check and bounded timing evidence | Minute for isolated code rollback; effort for deployed/schema rollback; leaked data cannot be recalled |
| G | Exit status, output schema, exact file effects, dry-run no-write, compatibility and regression | Help/receipts understandable; whole requested workflow works; no extra manual steps | New workflow direction and friction worth accepting | Independent clean-run transcript, resulting artifact/hash, negative case and dry-run proof on exact version | Minute for local tool revert; effort if it changed many files; real writes inherit target risk |
| H | Trigger registration/time zone, execution receipt, effect readback, no overlap, failure/retry and cleanup canaries | Event-to-effect completeness; silence is honest; alerts actionable | When intervention is worth attention; allowed autonomous effects/spend | Independent real-trigger-to-effect canary, failed-run alert/recovery proof, idempotence and rollback receipt | Minute to disable; effort to restore state; messages, charges and erased data remain irreversible |
| I | Artifact/source identity, install/deployment status, endpoint/device smoke, preserved data and rollback probe | Target/audience right; old clients and unrelated services preserved; receipt proves running state | Rollout audience/timing, outage tolerance and public release authority | Independent per-target installed-and-used readback, source/build fingerprints, data comparison and restore proof | Effort for rollback; public distribution, notifications and exposure cannot be fully withdrawn |
| J | Red before/green after where applicable; runner executes intended cases; hashes/counts/skips; fixture cleanup | Independent checker challenges coverage, evidence relevance and whether failures were merely hidden | Acceptance of a known residual; product desirability is judged on its own kind | Independent exact-target replay with coverage and skip list; planted failing control proves the checker can fail | Minute for test/report revert; effort for mistaken reliance; a green badge cannot undo released harm |
| K | Source links exist; arithmetic/row counts; dates; internal consistency; named evidence reproduces | Sources support conclusion; alternatives/constraints covered; plan dispatchable | Goal, priority, risk appetite, business direction and authority to proceed | Independent cited-evidence audit against fixed brief and prior rulings; only routine known decisions delegated | Minute for unpublished plan; effort after it drives implementation; resulting commitments inherit their own risk |
| L | Exact scoped diff, no unrelated writes, live-resource guard, archive/restore and fresh-session loading | Rules consistent with prior decisions; no duplicate setup; cleanup preserves ownership | Which precedent should apply and what history/resources may be retired | Independent inventory/diff, archive hashes plus restore trial, and fresh-client behavior proof | Minute with verified inverse; effort for many resources; unarchived unique history/data loss may be irreversible |

## Hard cases: least-attention honest showing

| Hard case and evidence row | Smallest honest showing |
|---|---|
| Background effect (H: `beads_eval-3r2`) | Actual scheduled trigger → one real effect → next-run state, plus one failure/recovery canary. A registered schedule or successful process exit alone is insufficient. |
| Speed (B/F: `agent-annotate-kbv`, `agent-annotate-dei.30`) | Same input/build/device before and after, a paired recording and reproducible repeated timings with spread. Preserve data and correctness checks; a faster isolated function does not prove the user journey. |
| Security/privacy (A/F: `FLD-cvnr`, `FLD-v4a.148`) | Redacted positive/negative case: authorized user succeeds, unauthorized user fails, state stays intact. Independent exact-build role/race test; do not put credentials or personal records in screenshots. |
| Physical phone/car (A/I/J: `FLD-0okr.10`, `FLD-0bc`) | Short capture with device/build identity and the required real interaction. State plainly when proof is a simulator/emulator. Hardware, GPS/audio or real-account criteria remain unproved until actually exercised. |
| Live records/prices (E: `RBX-7sb`, `RBX-swu.89`) | One changed-only row/price/image-order diff plus fresh real-account readback and tested undo. Preview is not live proof. New price policy/identity ambiguity remains a business decision. |
| Money, messages, public release (C/I: `FLD-c4su`, `FLD-ba0`) | Exact rendered result, recipient/audience/amount and immutable artifact shown before the irreversible step; receipt afterward. Refund/revoke/rollback does not retract a read message, prior exposure or every downstream effect. |
| Real checkout limits (B: `RBX-swu.54`) | Show actual checkout appearance and label no-payment scope. Do not imply a paid-order, refund or confirmation-email journey passed when the record checked only styling. |

## Decisions of taste and authority

- Questions: 1,924 answered, identified-Chang, non-redacted rows in the same window; inspect up to 8 per question project, seeded by project: 83 across 13 projects. Topics: look 11, wording 5, cost 3, direction 28, risk/implementation 36. These are inspected question topics, not rates of questions that genuinely needed him; explicit delegation appears too.
- A/B/D bring new visual feel, hierarchy, interaction and story choices: examples question suffixes `5f0315f83423` (road-line appearance), `e1d1212c5048` (tables), `760e805f568b` (animation story). The animation questions come from a project without a qualifying finished record here; do not infer its workload share.
- C brings voice, factual promises and policy wording: `838542593453` selects engraving-page text. Prior plain-language/conciseness rulings (`2854911cecb4`, `bb2019187880`) should be reused by the checker; they do not require a fresh personal decision every time.
- E/I bring commercial authority and reversibility. A separate explicit price/wholesale keyword follow-up found 6 identified answered candidates: `87bca9d46561` leaves final compare-at-price policy to the client; `0c125e013c34` assigns the wholesale check to the client. The owner cannot substitute for that authority. Paid-tool choices (`aa5375bb1181`, `12a6894d6552`, `c1a68854c7d6`) concern spend, not visual taste.
- K/L/H bring scope, risk and direction: `b59766986e34` rejects an incomplete disaster-recovery scope; `686a7413adf6` sets model/workflow policy. Conversely, `30ca331c6dc4` and `d448216ac9fe` delegate storyboard/word choices. Being asked is not evidence that a decision can only be made by him.

## Proposed first trust ladder

- **Fastest candidates:** J test-only repairs/proof, G bounded local tools, L reversible cleanup with verified archives, and C mechanical application of settled wording. Show every result first; then sample known-pattern results; then do and report with independent receipts. Never let the maker self-certify the evidence.
- **Next:** B familiar web repairs, F bounded service repairs, H read-only/idempotent jobs, I non-public installs, E source-exact reversible edits. Add exact-target/device/account and rollback evidence before promotion. A native/car behavior needs its own earned track; trust in the web version does not transfer.
- **Keep personal viewing for new taste/direction:** D new visual styles, A/B new flows, C new voice/promises, K new strategy. Mechanical variants can progress after an explicit precedent; a novel goal is not automatically trusted because the helper is familiar.
- **Never use “do and report” alone for an unagreed irreversible act:** new spending/pricing policy, destruction without recoverable history, sensitive disclosure, messages to real recipients, or a new public-release audience. Standing authority may permit a precisely agreed action; kind-level trust alone cannot supply it.
- Suggested pilot, not measured thresholds: 5 consecutive independently checked acceptances without correction → inspect 1 in 5 for the next 20 comparable pieces → do and report only within the proved scope. Any material miss returns that scope to show-everything; any changed risk/device/account starts a new scope. Record corrections that happen before closure, not just reopened beads.

## Reproduce

`DATA` is `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/`. In `DATA/kinds/`, run separately: `nice -n 19 python3 collect.py`; `nice -n 19 python3 sample.py`; `python3 label.py`; `python3 sample_questions.py`; `nice -n 19 python3 check_sources.py`; `python3 analyze.py`; `python3 write_findings.py`. Collection is a fresh local snapshot; exact published numbers replay from the retained frozen inputs and manual labels with `python3 analyze.py`. `blind-labels.json` is the retained human-style second pass, not generated from first labels.
Raw evidence: `rows.jsonl`, `showing-and-checking.json`, `summary.json`, `audit-*.jsonl`, `audit-summary.json`, `blind-*.json*`, `taste-rows.jsonl`, `taste-pricing-candidates.jsonl`, `source-checks.jsonl` and inventory files. No product, account, board, page, skill, deployment or other-Mac changes were made.
