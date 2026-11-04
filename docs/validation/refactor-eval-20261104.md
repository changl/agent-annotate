# Simplify the agent workflow first; keep the current storage

## One-page summary — ready for Chang’s page

**A focused refactor is worthwhile. Start with the work agents must remember, rather than a rewrite.** The clearest failures come from making an orchestrator reconcile card numbers, versions, unread feedback and delivery ownership across separate operations. Large files make these rules harder to repair, but splitting files alone will not make agents use fewer commands.

**Evidence:** On November 2, four versions of this page became visible with no question cards after numbering conflicts. One conflict was with a reviewer comment that had no stored number. Local transcripts also record four failed numbered resolutions, nineteen publish failures at the browser-check stage, and a peer’s status note absorbed by the orchestrator’s wait. The code now contains fixes for complete publication, numbering and unavailable browser checks; those historical failures are reasons to simplify the boundaries, not savings a new refactor can claim again. Resuming a session still needs a valid process binding for delivery.

**Measured baseline:** The package has 36,487 Python/JS/CSS lines; five files contain 55% of them. Default help shows ten workflow commands, while execution accepts 47 commands plus two aliases. In isolated, successful rounds, three answers take **five commands / 380 token-proxy tokens** for command text and output; five answers take **seven / 531**. Selected recent local transcripts show **27 closed authoring rounds, with a median 2,310 tokens of annotate overhead**. That historical measure excludes full context re-reads and product work and spans older releases.

| Option | Effort, including validation and three-Mac rollout | Expected benefit |
|---|---:|---|
| **A. Simplify the agent workflow** | **6–10 worker-days** | Three commands per round; provisionally 10–25% less annotate overhead; fewer numbering, flag and ownership recovery steps |
| B. Split large modules only | 5–9 days | Easier maintenance; approximately zero direct token or command savings |
| C. Make server state authoritative for CLI and browser | 12–20 days | Broader prevention of numbering/status disagreement; 10–30% overhead reduction only if it includes A |
| D. Replace the application/storage | 35–60 days | Benefits unproved; greatest risk to live history, drafts and delivery |

**Recommend A, then measure before funding C.** Have the software allocate identities and the next version, return explicit actionable feedback, validate the resumed owner, and accept one explicit batch of resolutions. Keep reviewer text intact, keep explicit Send and resolution, and retain immutable published versions. Extract only the shared rules this work needs.

Treat **230–580 tokens saved per historical-sized round** as a planning range, not a measured gain or a billing forecast. Accept the change only if repeated agent trials preserve every outcome and lower steps/tokens. No live page was written, no remote Mac was contacted, and no product code was changed for this evaluation.

---

## What is causing confusion, ranked by evidence

**1. Humans and agents choose labels that another layer allocates differently. High confidence.** Source versions v61/v62/v63 contain eight questions each and v65 contains five; all four are in published History, with zero matching stored decision cards. The coordinator’s tool results explicitly show HTTP 409 conflicts: #35, #49, #91 and #96. `ed4c001d2f08`, which blocked #49 and #91, is a reviewer comment with `number: null`; its fallback number changed as other numbers were reserved. Another reviewer comment blocked #96. This explains the repeated renumbering and the jump to spaced numbers without attributing it to model hallucination. Four earlier `resolve` calls returned “number is ambiguous; use its comment id.” The agent then read the raw store for IDs.

The base now pins fallback numbers, suffixes historical duplicates and commits a complete page/card batch. Still, the authoring format requires positive, ascending stable numbers **and** matching `d:qN` anchors; the CLI and browser both calculate labels. The agent must predict global numbering before asking a question. No model hallucination rate was measured; the evidence is retries, guessed commands and missed work. Allocate new labels in the software and print an unambiguous resolution handle in inbox output; retain existing labels/IDs for history.

**2. A successful intermediate operation looks like the whole job succeeded. High confidence.** v61 became current at 19:37:24Z on November 2 despite its failed card batch; v62 and v63 followed within 73 seconds. Separately, nineteen historical publish results said “NOT PUBLISHED” although origin and Tailscale checks passed; the browser stage failed and cards were then posted separately. `source/v56.md` explains the broken Orca tabs. These are transaction and diagnostic failures, not an instruction-length problem. The requested base’s `review_versions.py` and batch commit now address visibility/immutability; `verify.py` distinguishes unavailable browser verification. Preserve those fixes and benchmark against this base, not an older broken release.

**3. Owning a session is different from owning its current process. High confidence about the boundary; no new end-to-end reproduction here.** The October 31 coordinator transcript records three Sends waiting on an owner gone since October 21. In the base, `delivery._target_ready` checks PID/start time and terminal incarnation; publishing refreshes a matching session’s binding or transfers a provably dead owner. Resuming without another publish/claim can therefore leave a stale binding. An eval result saying an owner session is present does not establish that its captured process can receive input. Validate/rebind a resumed owner only with matching current-session and terminal evidence; keep uncertainty and duplicate-send protection.

**4. The orchestrator has two mail systems with different consumption rules. High confidence, outside annotate’s code boundary.** On November 2 the coordinator told the peer: “my wait absorbed it as a status message, so I only saw it now.” The same admission appears in `source/v61.md`. Refactoring annotate cannot repair Orca’s wait/ack semantics. Keep this as a separate integration acceptance case; do not count it as a failure class removed by rearranging Python modules.

**5. The visible interface encourages guessing and repeated checking. Medium–high confidence.** Recent local results include guessed `annotate list` and `workspace --slug` commands. There are ten default workflow verbs with 58 option occurrences across their parsers, and 76 distinct spellings across all 47 commands. Agents do **not** need to learn all 47, but error output exposes them. The skill is already fairly small: 451 words / 657 proxy tokens; its one page reference is 728 words / 1,316 tokens. Another prose expansion is unlikely to solve state ambiguity.

Copied FLD History contains **164/385 versions since October 26 replaced within ten minutes**. Since October 31 its bus records 136 inbox reads, 177 `version_published`, 112 `page_published`, and 67 `page_publish_failed` events. Two success event kinds can describe one publication; these are **not** 289 distinct successful attempts or a calculable failure rate. Fast replacements can be legitimate progress. They show a useful measurement target, not automatic waste.

## Code and state that a refactor must reach

Physical line counts at **`bdd629143f2ae647e7a3086b0a7ea1e0db5d8f0a`**, the requested `origin/changl/next-2.28.3` base:

| File | Lines | Why a change spreads |
|---|---:|---|
| `cli.py` | 5,798 | Parser, registry, publication, inbox, numbering, ownership, diagnostics |
| `web/shell.js` | 5,096 | Display numbering, cards, versions, Send, receipts, history |
| `sync_server.py` | 4,418 | HTTP/auth, storage, publication transaction, decisions and delivery |
| `web/adapter.js` | 3,307 | Content-frame anchors, pins, layout and legacy adaptation |
| `pagegen.py` | 1,399 | Markdown/card validation, staging and CLI publication calls |

There are 64 `.py`/`.js`/`.css` files totaling 36,487 lines, excluding bytecode; HTML, docs, tests and dependencies are outside that denominator. Thirteen Python modules import back into `cli.py` at 38 import sites, including the server, categories, workspace and delivery. A file split that preserves those dependencies merely moves the problem.

`cli._item_numbers` and `shell.js:computeNumbers` implement the same allocation algorithm. Python’s `hooks/decision_state.py` shares predicates with CLI/hooks; the browser still has its own predicates such as `isSetAside` and `needsPush`. Reuse `submitted.py`, `review_versions.py`, store locks and delivery journals rather than introducing a parallel state layer.

At least eight separate concerns currently matter: page/workspace identity; immutable version/draft; logical question versus comment ID/display number; pending versus submitted reviewer feedback; resolution/withdrawal; round identity; unread position; owner/process binding and delivery receipt. Simplification should hide bookkeeping, not collapse distinctions such as “saved,” “delivered,” “read” and “done.”

**Legacy is not proven dead.** Both copied pages have baked `versions/*.html` and no `content/*.html` directory: FLD has 655 version HTML files and Agent Annotate 66. Server extraction and adapter compatibility remain relevant. Old archive shapes, Q-prefix numbering, transport migration cleanup and monitor/provider commands are retirement candidates only after usage inventory. No safe dead-code deletion total was established; do not promise one from keyword counts.

## Four options and their practical limits

Effort is one experienced worker’s days, including tests, copy-based migration rehearsal and about 1–2 days of staged three-Mac deployment/rollback checks; it is not elapsed calendar time. Estimates assume existing APIs/storage remain usable. All savings below are projections; **0% is a possible measured result**.

| Option | Scope and regression/migration risk | Agent work and failure classes |
|---|---|---|
| **A — 6–10 days** | Software allocates new question labels/next version; inbox returns exact actionable handles; explicit `resolve` accepts a list with a compact receipt and per-item JSON outcomes; verified owner resume. Medium risk at identity, lineage and cursor boundaries. Add fields compatibly; preserve existing URLs, numbers and storage. | Three commands: inbox, publish result, resolve listed items. Three-answer round 5→3; five-answer 7→3. Targets label/anchor guessing, repeated resolution calls and stale bindings; does not fix Orca mail or remove existing publication safeguards. |
| **B — 5–9 days** | Extract registry/storage, numbering and publication helpers from CLI/server; separate browser rendering from state transforms. Low–medium regression risk from imports and initialization. No stored-data migration. | Same 5/7 commands and approximately 0% direct token savings. Removes circular dependence only where callers really move to shared helpers; removes no user failure class by itself. |
| **C — 12–20 days** | A plus one server-produced projection of IDs/labels, submitted state, actionability and receipts for CLI/browser. Medium–high risk around unsent drafts, offline edits and older clients. Keep browser-only draft/layout state local; introduce a capability/version gate before removing fallbacks. | Same three commands if A is included; otherwise no command saving. Prevents independently computed labels/counts/statuses drifting. This is one authoritative model, not an attempt to run identical source in two languages. |
| **D — 35–60 days** | New application/storage, import/export bridge and old-client compatibility. High risk: interrupted Send, frozen evidence, approvals, history and three divergent installations. | At best A’s three commands; no additional token benefit established. A new storage engine does not inherently fix owner lifecycle or Orca mail. |

| Metric | A | B | C | D |
|---|---|---|---|---|
| Annotate tokens/round | Planning range −10–25% | About 0% | −10–30% **including A**, not additive | Unknown; no justified premium over C |
| Net production line change | Roughly −200 to +400 | About flat, ±300 | Roughly −300 to −1,200 | Unknown; prototype before claiming a reduction |
| Full test wall time | Assume unchanged | Assume unchanged | Assume unchanged; focused state tests may get cheaper | Unknown, likely transition overhead |
| Defect rate | Numeric reduction unproved | Unproved | Unproved; fewer duplicate-rule failure opportunities | Unproved; highest initial regression exposure |

Line ranges are sizing estimates, not audited deletion counts. The existing CI work already recorded a 23m10s accepted full run versus 60m29s serial under different load; no refactor should claim that saving again. The later version-ready validation includes a broad run with four fixture failures and a focused fix/rerun; it does not establish a newly measured full-green timing for this report.

## Measured tokens and how to verify the gain

**Controlled baseline:** Four model-free fixtures used this checkout’s absolute `src`, relocated state/bus/config/keys, local transport, blocked Orca command boundary, and ports **18741/18743/18745/18750**. Each first published questions with `new --publish --ask`, submitted synthetic reviewer answers through localhost HTTP, read `inbox --unread`, published the result as v2, and resolved each item against `s:result`. Assertions checked that every command exited zero, v2 was current, and all items resolved into v2. Servers were stopped. There was one deterministic run per fixture, not a latency trial.

| Answers | Steady-round CLI commands | Printed UTF-8 bytes | Output proxy tokens | Command-text proxy tokens |
|---:|---:|---:|---:|---:|
| 1 | 3 | 676 | 165 | 68 |
| 3 | 5 | 1,178 | 286 | 94 |
| 5 | 7 | 1,680 | 411 | 120 |
| 10 | 12 | 2,937 | 709 | 185 |

“Steady round” counts inbox + result publication + N resolutions; initial publication/setup and simulated reviewer clicks are excluded. Initial `new --publish --ask` itself printed 62 bytes / 15 proxy tokens. At three answers, inbox printed 837 bytes / 184 tokens, result publication 62 / 15, and the three resolution receipts together 279 / 87. Individual resolve token counts vary with random IDs. Three answers is FLD’s observed median submitted-round size; five tests a larger ordinary batch.

**Real copied-page check:** Replaying FLD’s already-submitted three-answer round from November 4 at 00:11:03Z through `inbox --unread`, using the copied store and an isolated bus/cursor, printed **1,235 bytes / 329 proxy tokens** (plus 12 command-text tokens). This preserves the actual prompts/answers rather than replacing them with the shorter fixture text; it is a replay, not a fresh reviewer Send.

Tokenizer: **tiktoken 0.14.0, `o200k_base`**, a reproducible proxy rather than the provider’s tokenizer/accounting. Commands contain fixed `/tmp` paths. Counts exclude generated page/card input, reasoning, tool wrappers, skill loading and repeated conversation context. The skill plus page reference adds 1,973 proxy tokens when actually loaded; caching changes cost.

**Historical cross-check:** Five copied Claude transcripts yielded recognized calls in four files and 27 closed authoring rounds in two files, October 31–November 4 UTC. `cost --include-dev` reports medians of 1,049.5 issuing-message output tokens and 931 result `characters/4` tokens; the median of their per-round sums is **2,310.3**, not the sum of the medians. Its 166 tool rows (161 CLI rows and five documentation reads) / 32 failure candidates include at least one quoted error; unknown verbs such as `list` are missed. This selected development sample is not a production-wide defect rate. Four collision failures alone accounted for 5,011 attributed output/result tokens across the sample; nineteen browser-stage failures accounted for 20,919. Those are observed historical costs, not incremental savings available after this base’s fixes.

`eval` on the two copied page stores reports 380 open cards, 357 with anchors absent from the current document, and 11 reviewer-correction candidates. Missing anchors can reflect older versions; these are diagnostic candidates, not proof of abandoned work. `metrics` over October 31–snapshot reports 60 deduplicated submitted rounds, 312 decisions and 57 acknowledged latest delivery rows. An acknowledgment does not prove the requested work happened. See the [sanitized measurement receipt](refactor-eval-20261104.json) for counts, hashes and limits.

**Before/after acceptance:** Pin this base and the candidate; extend the existing `scripts/bench.py` fixtures, with no helper agents. Interleave at least five runs per ref/provider for first publish, three/five-answer rounds, number conflict, failed publication, resume/dead owner, unsent drafts, retry after interrupted Send and peer-message delivery. Keep model, effort, tools, skill, paths and token counting identical. Use only cloned pages and ports 18700–18799; assert no real transports, live roots or live terminal sends. Independently assert preserved answers/history/IDs/URLs, no premature version visibility, no unsent-text leak, and no duplicate delivery.

Require all safety/outcome assertions to pass, the planned 5→3 / 7→3 command counts, and at least 10% lower median measured annotate overhead without worse tail results before claiming A’s savings. Measure actual issuing output, printed bytes/proxy tokens, failed calls and recovery steps separately. Replay transcript estimates only after manually classifying errors; do not equate raw event counts with attempts. Track affected failure classes per completed round for two weeks after rollout; report the numerator and denominator rather than forecasting a defect percentage now. Ten all-green agent runs alone would still be too small to establish a low production defect rate.

At 100 rounds/day, the provisional 230–580 tokens/round is 23k–58k annotate tokens/day. This is scenario arithmetic; current daily volume and billable cache/re-read effects were not established. Dollars and whole-orchestrator percentage savings cannot be responsibly projected from these records.

## Evidence and rollout boundary

Evidence was copied locally at **2026-11-04 01:27 UTC** to `/tmp/aa-refactor-eval-20261104`: the two named review directories, their buses/registrations/delivery journals, and five selected local Claude transcripts. FLD’s copied bus has two invalid/incomplete lines; parsers exclude them. The snapshot is not an atomic transaction across all files. No M5/M1Max16 access, live inbox/cursor/claim, route change, installed skill change or forbidden-workspace access occurred. Beads was not used for this research task.

Reproduction entry points: run this base’s `annotate eval --since 2026-10-31 --json --state-dir COPY_STATE --bus-dir COPY_BUS --transcript-glob 'COPY_TRANSCRIPTS/*/*.jsonl'`; `annotate cost --since 2026-10-31 --include-dev --json --root COPY_TRANSCRIPTS`; and `metrics.collect_metrics(since, until, COPY_STATE, COPY_BUS)`. Set **all** `paths.py` overrides before importing or launching the CLI; rewrite copied registry page/bus paths to copies. The local scripts/raw results remain under the snapshot directory; only aggregate evidence is committed.

Exact historical transcript pointers (session `2ac5a669-f55b-4358-8e7c-f1f8e085577b`, copied file line numbers): 533 owner failure; 2868/2872/2893/2897 resolve failures; 9706/9738/9834/10954 numbering failures; 9914 missed peer status. Header-worker session `06ac6f5a-9f6f-4b24-a378-d649edeb4d46`:310 records guessed `list`; coordinator:11576 records `workspace --slug`. These are private local evidence pointers; reviewer text and share keys are not exported into the receipt.

Code anchors: `cli.py:_item_numbers`, `cmd_resolve`, `_publish_already_running`, `AGENT_COMMANDS`; `shell.js:computeNumbers`; `sync_server.py:_assign_item_number`, `_v2_post_comments_batch`; `delivery.py:_target_ready`, `dispatch_record`; `review_versions.py`; `submitted.py`; `skills/claude/SKILL.md` and `references/page.md`. Existing validation: [complete versions](version-ready-20261102.md), [CI timings](ci-speedups-20261102.md), [prior skill experiment](simplify-skill-20261016.md). The prior experiment measured 18.6% aggregate Codex output reduction with preserved outcomes; it supports testing A, not assuming the same gain again.

For implementation, first rehearse A on copies from all three Macs with preserved IDs, drafts, cursors, approvals and receipt history. Then update one Mac, verify old-client capability refusal/compatibility, test one real Send/read/explicit resolve, and roll out the identical build to the other two with backups and rollback. Do not remove legacy readers until all three inventories justify it. **No rollout or fresh model benchmark was performed here; estimates remain uncertain until that comparison.**
