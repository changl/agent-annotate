| Design | What is remembered | Sentence → agreement | What reaches him | Who checks “done” | What catches a stall | Answer → rule | Trust changes | Several computers | New construction |
|---|---|---|---|---|---|---|---|---|---|
| Record first | Ordered facts, immutable proof, disposable current views | Writer plus independent challenger; his Go or existing authority | Five gate stages; prepared items, minute allowance, separate urgent/promise notices | Scripts and another helper, bound to exact result; he judges reserved matters | Minute watch plus separate observer; progress, permission and evidence expiry | Exact ruling first; two interpretation/fidelity runs for generalisation | Explicit scoped delegation, mature outcomes, audits; checks remain | Thin runners, isolated work, one current publication permission | Writing service, views, packets, authority boundary, gate, watch, doorway, meter |
| Check first | Eight record families centred on criteria and proof | Draft criteria and counterexamples; another helper challenges whether a useless result could pass | Seven gate stages; 12-minute allowance and urgent lane | Independent reproduction and adversarial judgement; owner taste stays pending | Minute watch plus observer; separate permission and useful-progress clocks | Case ruling immediately; proposed broader scope with source and expiry | Explicit permission; staged human sampling after follow-ups | Wrapper claims work; one publication permission; boards mirror | Contract/check admission, shared record, wrapper, gate, observer, doorway, meter |
| Office first | Eight paper families in one versioned register | Brief writer, examiner, then his approval; receiver read-back | Six gate stages; finite briefing book; urgency independently examined | Scripts plus examiner who exercises the result and tries a counterexample | Minute clerks on two hosts; due returns and observed checkpoints | Ruling, scoped standing order, examined interpretation | Matured outcomes and explicit standing permission; random re-examination | Common order/receipt contract and exclusive commits | Register, clerk transitions, packets, permission boundary, briefing doorway, meter |
| Capsule first | Seven package families plus a shared book of current authority/resources | Agreement plus independent preparation; Go activates the package | Five gate stages; globally reserved minutes and one urgent lane | Scripts plus separate semantic checker; protected plan and exact proof | Two independent two-minute clocks; claims, next actions and freshness | Exact answer retained; rule conditions and enforcement opportunities recorded | Explicit standing agreement/acceptance; random human samples; immediate reversal on miss | Self-contained exports, shared claims and restricted effect scripts | Packages, common book, wrappers, gate, clocks, doorway, meter; full design adds quorum storage |

# Simplicity and cost critique

References: R = [record first](../machine/record-first.md), C = [check first](../machine/check-first.md), O = [office first](../machine/office-first.md), K = [capsule first](../machine/capsule-first.md); section numbers below refer to those files. Research references name files in this directory. This judges the designs, not an installed implementation. I read the method, plan §§2/3/5, scenario, and the eight available research files; no other critic's work.

A run is one job that starts and ends; a token is a unit of model input/output text. Par is the agreed allowance of owner response cycles. Immutable means a saved version cannot be edited; fencing means refusing an old worker's right to publish, without claiming its process stopped.

**Choose a reduced record-first design: one writer, current goal packets, deterministic showing, existing job runners, independent checking and observation.** Capsule first's own first-version retreat to one writer is sensible; its full three-keeper system is last on operating cost. None has demonstrated a cheaper correctly accepted goal than today's workflow.

## Where all four agree

- A counterpart is a short-lived role; durable facts, not a resident coordinator's conversation, carry responsibility. Scripts handle routine routing, clocks and counts.
- The agreement includes purpose, done lines, examples, limits, authority and a promise. Checking challenges interpretation as well as implementation; passing tests cannot settle unknown taste.
- A pass belongs to an exact result/check/input version. Makers cannot pass their own result, and an acceptance is distinct from observed correctness.
- A preference is not permission. Silence cannot grant new authority; timeouts act only within an existing grant or park safely.
- Quiet requires independent observation, visible freshness/unknown state, due returns and bounded recovery. A lease expiring does not prove a process stopped or an outside action was undone.
- One doorway has finite owner work, artifact-linked answers, direct source access and a route for dissent. Admission counts expected minutes and age, not seven cards.
- Rules retain scope and provenance; trust is narrow, reversible and explicitly authorised. Later defects reopen the original goal and remain in its cost.
- Each builds the meter from day one and rejects a numerical saving inferred from “14 coordinator turns” versus five or six jobs.

Much of this agreement follows the common brief and shared outside research; it is convergence on constraints, not four independent experiments proving the economics. Stronger architectural convergence is that even capsules need shared authority and even a central record needs small current views.

## The forks that change the bill

| Question | Options, cost and risk | Choice |
|---|---|---|
| Must the record survive a host loss without stopping? | R/C/O use one authoritative writer with guarded restoration; lower upkeep, temporary stop on loss. K §2 requires three keepers, two agreeing, and two durable attachment copies before advancement; more failure/upgrade/partition cases. K §13 itself defers this. | One writer, tested backup, second-host observer, explicit unavailable state. Buy automatic failover only after measured recovery loss justifies it; never replace the quorum with file sync. |
| Does a showing need its own thinking helper? | C/O §§3/11 add one run to describe a result already checked; another startup, repeated reading and an opportunity for unsupported prose. R/K render checked facts and the artifact; novel interpretation still needs checking. | Render by script. Put the checker's necessary explanation in its existing verdict; request an extra interpretation only for a real unresolved matter. |
| Does every agreement need another semantic review? | All four normally say yes. It costs a fresh run but counters plausible work on a wrong contract; C §5 most clearly asks whether a useless result could pass. Repeating it for an unchanged, already admitted low-risk template checks the same interpretation again. | Keep a challenger for new/changed meaning or consequence; reuse the exact admitted template and mechanically check its scope for routine delegated work. Never let the new maker quietly rewrite its checks. |
| Must all evidence travel on every step? | K §2 requires complete exports; robust against a departed account, but copies and retention multiply. R §2 uses source-linked packets and immutable attachments; cheaper inside one reachable service, with an availability dependency. | One durable evidence store, relevant packet, complete export only for an actual transfer/offline need. Preserve necessary sources before their original access disappears. |
| Does a changed promise interrupt him? | R §9/§4 pushes a separate deduplicated notice; C/O/K normally wait for opening. More pushes consume attention; delaying a genuinely actionable loss conceals it. O permits an acknowledgement reminder; K's urgent reserve can hold excess cases safely. | Promise change at next opening; push only for a verified consequence requiring his action before then. Receipt retry is not another alert; never hide distinct real emergencies to meet a quota. |
| Can three acceptances choose the review regime? | All require permission, but propose incompatible 48-hour/two-day/seven-day maturity and 20%, one-third or staged sampling. Each setting adds policy branches without a calibrated error model. | Keep outcomes and manual scoped delegation; postpone promotion arithmetic. Select audits independently and reset on a material miss or changed context. No streak buys an irreversible action. |

## The simplicity and cost lens

### 1. Count the machinery before calling it small

Counts use each design's §2 record-table rows, §3 job-table rows, numbered §4 gate stages and §6 clock-table rows. These are responsibility families, not independent deployed services: a compound row may hide several deadlines. Admission prerequisites, direct controls, urgent/promise policy and retry limits add rules beyond the numbered gate.

| Design | Record families | Job kinds | Ordered gate stages | Clock families | Goal states |
|---|---:|---:|---:|---:|---|
| R | 12 | 16 | 5 | 13 | 0 exhaustive state lists; 9 situations implied below |
| C | 8 | 10 | 7 | 10 | 0 exhaustive state lists; same 9 implied |
| O | 8 | 11 | 6 | 12 | 0 exhaustive state lists; same 9 implied |
| K | 7 local + 1 shared book | 11 | 5 | 10 | 0 exhaustive state lists; same 9 implied |

K's book has eight overlapping collections: current versions, preferences, authority, trust, due actions, dependencies, resource reservations and attention capacity. Seven package rows therefore do not make it the least stateful design. R's 16 jobs likewise do not require 16 daemons: R §3 explicitly proposes three reusable executors plus a clock.

The nine inferred situations are preparing, awaiting agreement, making, checking, awaiting an owner response on a result/fork, parked, done, reopened and stopped. **These are my normalised count, not nine declared implementation states.** None supplies a complete transition table; proof states such as C's four untested/fail/pass/unknown values are a different dimension. Do not build an accidental cross-product of goal stage × proof × delivery × health × trust.

For the first version use six goal stages: preparing, working, awaiting him, parked, done, stopped. Put agreement/showing/fork in the pending action, checking in the work step, and freshness in observation state; reopening is an event returning to the appropriate stage. This cuts labels, not distinctions in evidence or authority.

The actual always-running responsibilities are a record writer, artifact storage, doorway, due-work runner and an independent observer, plus bounded helper launchers on participating hosts. Existing storage/scheduling may host several responsibilities. K's full version additionally operates a replicated authority service and attachment-durability protocol. Any estimate that counts only model prompts misses this work.

### 2. One medium goal, sentence through acceptance

Common case: six done lines, two bounded work slices producing one integrated result, no taste stage, no fork, no repair, structured Go/Accept, no new general rule. All criteria receive independent evidence; same work and checking in every comparison. These are proposed run counts, not measurements.

| Design | Helper runs and reading | Script runs outside shared clocks | What its quoted budget means |
|---|---|---|---|
| R §§3/11 | **5:** agreement 1–3k input tokens; challenger 1–4k; two doers each full agreement/rules plus relevant files (illustration 6k packet each); checker 3–8k plus actual result/proof | Author estimates **20–40** changed-goal/due jobs; showing is a script | Illustration: 21k manifest input + actual file reads, outputs and invocation overhead; 39 helper-minutes. Not a bill. |
| C §§3/11 | **6:** agreement about 2k input words; challenger similar; two doers read their source slices; checker reads original request, checks, source and integrated result; showing helper rereads checked result | Author estimates **10–16**, plus pooled watch and weekly work | 15–30k words read before tool-heavy work; incompatible unit with R's manifest tokens. |
| O §§3/11 | **6:** writer and paper examiner, two doers, result examiner, showing writer. General packets 1–4k words; allowances respectively 2–5k, 1–3k, 6–10k per doer, 4–8k, 1–2k tokens including input/output | Author estimates **15–30**, plus **120 watch jobs/hour** across two hosts, shared by all goals | 20–40k helper tokens, with a proposed 60k ceiling; input/output/cached portions need separating. |
| K §§3/11 | **5:** agreement, independent packet preparation, two makers, outcome checker; roughly 2–6k relevant input tokens each plus necessary work files | No per-goal number supplied. **12 logical script steps** in the explicit trace below; actual process count unproved | 20–35k input + 4–8k output, excluding large work; full version also transfers/replicates packages. Free-text interpretation can add a sixth helper. |

To make K's missing number inspectable, a possible script trace is: capture; gate agreement; save Go; claim slice 1; save slice 1; claim slice 2; save candidate; batch mechanical checks; apply/observe; gate/render showing; save Accept/close; update accounts. That is 12 jobs **if** each listed step is one invocation and writes include package/record updates. Count checkpoints, separate check recipes, two-stage effect observation and retries additionally. R/C/O's ranges also depend on batching; table-row counts cannot prove scheduler efficiency.

Shared clocks are not per-goal free work: two minute sweeps are 120 invocations/hour; two two-minute clocks are 60/hour. R/C/O can have further host/probe jobs. Pool due queries, charge CPU/storage and measure wake-ups; never launch a model on an empty sweep. Rule generalisation costs two runs in R/O, variable interpretation in C/K; sketch, real fork, repairs, audits and weekly interpretation all sit outside the clean baseline and must be charged.

**Fresh starts have a substantial observed price.** `x-what-exists.md`, “Measured tiny runs,” reports 13,869–13,871 total input tokens and 37.649–43.494 seconds for a one-line Codex response, even with ambient discovery disabled. Under that same setup, five/six invocations would repeat roughly 69k/83k input and the median trivial-call durations sum to 3.4/4.1 minutes. This is a configuration-specific warning, not a universal fixed overhead, latency forecast or dollar cost; ordinary prompts, caching and tool work differ. None of the designs' small packet budgets establishes a smaller actual input bill. Claude's three probes failed before inference, so its successful cost remains unknown.

Today's comparison is **one resident coordinating helper plus workers**, not fourteen workers. All four can save coordinator status turns, repeated whole-history reads, handovers, owner-managed retries and explanations. All four add early challenge, packet selection, independent observation, structured proof, fresh startup and upkeep. A warm coordinator on one tiny change can be cheaper; a long idle multi-project conversation or repeated restart can be dearer. C/O add a show-preparer without adding a necessary check. K adds the largest storage/availability burden in its full form; R carries the most explicitly itemised record jobs.

The method's 14-turn/68% example is per delivered round; `d4-goals.md`, “Why cycles cannot be counted,” confirms five reports aggregate 16 rounds without a goal key. Neither subtraction nor a savings percentage is valid. Compare actual uncached/cached/output usage, cost, owner minutes and escaped defects on matched accepted goals. Count setup, abandoned work, maintenance and later repair; zero-cycle work still costs money.

### 3. Day one, later, or ceremony

This sorts the substantive parts in §§2–8/12–13 of all four. “Later” means outside the bounded first work kind; a protection cannot be deferred while admitting the risk it protects against.

| Part | Must exist on day one | Can wait | Ceremony with no demonstrated extra protection |
|---|---|---|---|
| Record/current views/packets | Stable goal and attempt IDs; original words; versioned agreement/result/check/ruling; durable receipts; next action/owner/time; source-linked current packet | General-purpose event-replay framework, historical import, elaborate indexing; complete portable export until needed | Storing the same editable truth in packages, board, flow and register; every helper rereading the full history |
| Agreement/preparation | Plain purpose, constraints, authority, examples/counterexamples, promise, checks; independent challenge for new meaning | Automatic decomposition, semantic routing, reusable templates beyond the first work kind | Separate planning paper and examiner after an unchanged admitted template; repeated approvals of the same authority |
| Work/resources/integration | Isolated work, exact base, one publisher per target, bounded run/spend, dependency owner/return; independent integrated-result check | Parallel branches, scarce-hardware scheduling, speculative duplicates, execution rehearsal for low-risk familiar work | A deputy hierarchy; read-back reviewed in another model call when the existing run/check already covers it |
| Checks/effects/control | Non-maker reproduction/judgement; actual target identity; protected check plan; invalidation; stop/amend/revoke; checked undo within granted authority | Autonomous live deployment and other irreversible effects; additional providers until consequential ambiguity needs them | Another session signing “looks good”; making every owner acceptance certify correctness; a model narrating six machine passes |
| Gate/doorway | One finite prepared sitting; artifacts beside answers; scoped rule lookup; authorised defaults or safe park; age/return; stale-answer rejection; real urgent route and dissent | Precise review forecasting, cost-of-delay optimisation, voice, elaborate sitting animation | Hard-coded 10/12/15-minute claims as science; creating permission from accepted recommendations; compulsory status notices |
| Watch/delivery/recovery | Due-action sweep; useful-progress deadline; publication fencing; uncertain-effect reconciliation; independent watch/record probe; cached freshness; receipt retry; tested restore | Separate services for each clock family, automatic rerouting to every host, automatic record failover | Repeated healthy helper wake-ups; treating a live process or green database health URL as progress; arbitrary timeouts without rehearsal |
| Rules/trust/audits | Exact case ruling, explicit standing authority, scope/source/version, retrieval/application receipt, correction/impact link; full showing initially; checker fault test and independently selected outcome audit | Broad preference inference, promotion ladders, learned embeddings, many maturity windows/sample regimes | Generalising every answer; inferring authority from popularity; an extra model pass merely to transcribe an unambiguous local ruling |
| Meter/accounts/retention | Goal-level presentations/replies/revisions, original par, causes, observed/missing minutes, words/taps/pushes, usage/charges, later defects, bounded evidence retention and backup | Fancy account dashboards, prose weekly editor, precise shared-cost attribution beyond a disclosed simple rule | A separate reporting workflow for him; invented thought-time precision; calling all extra cycles waste |
| Participation/availability | One proven helper launcher, same packet/result contract, second-host observer; reject unsupported capabilities | Five native adapters, board mirror, cross-host effects, quorum storage, full offline work packages | Rebuilding launchers/schedulers already installed; adding a board bridge just to claim tool coverage |

This keeps the protections supported by `d2-questions.md` (repeated variants, misunderstood choices, bounded authority), `d3-rules.md` (rules reaching the action), `d4-goals.md` (wrong/narrowed/accidental closure), `d5-outside.md` §§1–4 and `d7-other-fields.md` (freshness, dissent, explicit responsibility, real checks). The records do not validate each proposed timer, automatic trust ladder or mandatory paper movement.

### 4. Existing pieces: use, build, or bend

`x-what-exists.md` is present and is stronger evidence than the designs' help-only final sections. It establishes installed primitives, not their end-to-end assembly.

| Piece | Use as it stands | New application work | What would bend it out of shape |
|---|---|---|---|
| Codex / Claude command lines | Fresh structured jobs/events/final files; Codex success demonstrated | Thin packet, attempt, isolation, usage and submission wrapper; test normal configuration. Establish successful Claude authentication without assuming failed isolated probes reflect ordinary use | Treating a working directory as an exact read allowlist, or JSON/exit success as correct completion |
| Orca | Existing launch, placement, task/dispatch identity and bounded inspection; phone dictation/push documented | Optional runner adapter and actual phone delivery/failure test | Keeping a permanent thinking dispatcher; making host-owned Runs the full goal/rule authority; inferring safe retry from silent/unverifiable status |
| Windmill | Installed scripts, clocks, jobs, flows and existing headless host bridge; suspensions release slots | Record-facing commands/check jobs and alert policy; independent observer elsewhere | Recreating the record in a suspended flow per paper; treating scheduler success as external helper progress; assuming CE has the paid custom approval forms |
| Beads | Existing ready/dependency source and proof-linked task references when needed | Optional idempotent import/projection with explicit field ownership | Using board status/lease as acceptance or process fencing; assuming stored timer gates run themselves or HTTP mutations fire CLI hooks |
| Storage and backup | Existing transactional SQL, ordinary files/fingerprints and backup mechanisms | Minimal domain tables/events, atomic version/authority checks, due index, privacy/access/restore rules | Calling Syncthing a transaction/quorum service; mistaking SQL availability for an implemented audit model |
| Person-facing surfaces | Existing responsive inbox shell; versioned artifact review can remain a linked viewer | Goal agreement/look/decide, immutable answer binding, finite sitting/glance and interaction meter; prove phone/desk flow | Forcing a Windmill suspended-job inbox or project review page to become the entire method without new semantics; adding another compulsory inbox |

Do not build a new scheduler, agent runtime, database engine or replicated-storage algorithm. The irreducible new product is the agreement/authority/proof transition contract and its owner doorway. Enforcement at the file/credential/effect boundary is the hardest integration, not drawing three screens. X also reports `/healthz` can survive a dead database, sleeping Macs cannot execute, and no exact-file boundary is supplied by ordinary roots: use those facts in tests.

### 5. Five-minute explanation and one-week diagnosis

Scores are my engineering judgement, 1 easy–5 hard; they are not usability measurements.

| Design | Explain the running system in five minutes | Explain an event a week later |
|---|---|---|
| R | **3/5.** “One book, small jobs, checked results” fits; ordered facts, projections and authority numbers need an example | **2/5 if implemented:** explicit trigger → authority → job → evidence → gate chain is best specified (R §2). Unversioned/missing attachments make the apparent advantage vanish |
| C | **2/5.** “Agree what counts, challenge it, make, independently check, show” is direct; avoid implying six passes prove complete intent | **2/5:** strong criterion/source links, but investigation must also explain why a criterion was admitted, changed or omitted (C §§2/5) |
| O | **2/5 for the metaphor; 4/5 for operation.** Papers and clerks are familiar; eleven jobs and repeated examinations need translation | **3/5:** register supports provenance, but multiple paper interpretations/read-backs can make the causal path longer (O §§2/3/7) |
| K | **2/5 for one goal; 5/5 for the full machine.** The travelling folder is simple until shared book, three keepers, two clocks and attachment commits are explained | **3/5:** portable proof helps; one must reconcile capsule version, book authority, reservations and replica/index freshness (K §§2/6). Single-writer first version is easier |

Keep the engine room to one “why?” link with original words, authority, exact result/check, attempts, decisions and missing evidence. A seven-day incident must not require reading seven days of helper chat. The designs' 5–15-day build estimates are unvalidated author judgements; no measured permission integration, phone delivery or restore exercise supports a delivery promise. A tiny team should ship the bounded loop and rehearse it before staffing these broader machines.

### Cuts from each design, with no loss of a needed protection

- **R:** remove mandatory general-rule double interpretation when scope is literal; consolidate due handling rather than sixteen independently scheduled job types; defer general event-snapshot machinery and secondary policy layers. Keep immutable provenance, current-version checks, source packets, independent observation and real backup/restore.
- **C:** cut routine showing-preparation and prose-ledger helper runs; do not repeat contract challenge for an unchanged admitted template; defer staged one-third/one-tenth promotion. Keep the adversarial “could useless work pass?” test, source-first review and criterion-bound evidence.
- **O:** cut the showing writer, paper movement as a separate workflow and any extra examination whose only purpose is restating a checked finding. Keep receiver understanding in the actual work run and new-meaning checks; defer broad staffing/adapters and the seven-day promotion machinery.
- **K:** cut quorum availability from version one, as K §13 already does; cut complete attachment export on every internal step, the board bridge and unused adapters. Keep one authoritative book, durable necessary proof, exact authority refresh and a tested transfer bundle when genuinely needed.

### Five things that must be true on day one

1. One real sentence reaches an agreed goal and exact checked result through one doorway; scope/authority changes cannot be smuggled into acceptance or by silence.
2. A different checker can expose a planted failure, and acceptance names the frozen artifact; changed work invalidates affected proof and later defects reopen its original goal.
3. A killed/stuck worker, lost receipt and stale observer cannot look healthy; safe retry rejects old publishing authority, and unknown outside effects are observed before repeating them.
4. Every wait has an owner, consequence and working return; the finite sitting, safe parking, urgent route, direct stop and dissent actually function. No trusted label removes these protections.
5. The meter joins goal, agreement, attempts, owner reactions, cost and later repair from the first run; the team can restore acknowledged records and explain one outcome from receipts without a transcript.

## What all four leave unresolved

- **A genuinely comparable meter.** Their cycle definitions disagree on exposure versus answer, timeout and multiple requests in one sitting (all §8). D4 cannot supply the missing baseline. Preserve raw display/request/reply/timeout events and count distinct requested reactions per goal consistently; report elapsed unanswered age separately. None has demonstrated declining questions, quality or total cost.
- **A shared hard spending stop and operating owner.** Per-run/goal limits appear everywhere, but none specifies an atomic whole-system spend reservation across simultaneous trusted goals, retries and continuing provider work, or who handles a broken observer. D6 records cost-control complaints in 9/50 threads. Bound total admitted spending too, record cancellations actually observed, and name the incident responder; low owner cycles cannot conceal an expensive abandoned process.
- **An executable transition/failure contract.** No exhaustive lifecycle, actual confinement proof, acknowledged phone round-trip, sleeping-host exercise or tested restore is supplied. X explicitly leaves these unverified; D6 finds 12/50 silent-wait and 12/50 state-disagreement reports. Prose safeguards need a small reproducible acceptance matrix before implementation grows.
- **A valid present-day backlog and permission baseline.** D2 reports zero currently waiting after retirement/consolidation, not the method's old fifteen; only 5/2,099 covering precedents are narrowly confirmed. All designs can implement the supplied 11-of-17 hypothetical lookup, but none demonstrates that real match rate. Import explicit live obligations/authority only; archived cards and candidate instructions do not become new work or permission.
- **Proved affordability of staff procedure.** D7 says quiet principals can have continuously busy staff; D4 counts tracking/runtime infrastructure in 276/2,318 items without measuring effort. No design budgets maintenance incidents, upgrades and rule/check upkeep per accepted goal. Measure that labour separately, keep necessary bad news, and reject added machinery that cannot explain its avoided failure.

## Combined design, then its smallest useful version

1. Take R's single writer, durable receipts, current views and “because” chain; keep immutable necessary proof beside the record. Restore safely rather than implementing automatic failover.
2. Use one goal, agreement/result versions, attempts, rulings and due actions. Six display stages suffice; evidence and observation states remain separate.
3. Take C's adversarial contract challenge and source-first independent result check. Use trusted scripts for repeatable facts and another helper for judgement; specialists/owner remain required where general helpers cannot judge.
4. Take K's bounded contents/authority/next-action packet and D3's rule-considered/check-run receipts; export complete evidence only when work actually moves beyond the shared store.
5. Use existing launcher/scheduler primitives behind one small wrapper. Preserve a whole coherent work slice; do not restart a helper for every thought or keep one alive to wait.
6. One current permission controls shared publication. Isolate candidates; reconcile uncertain outside effects. No irreversible or cross-host live action enters until its authority and enforcement are proved.
7. Gate by current scoped authority, authorised fallback, expected minutes and age, expiry, then sitting. Reserve genuine urgent capacity without concealing excess emergencies; direct dissent/control bypasses preparation.
8. Take O's return owner/event/date and read-back in the recipient's own work run. Rehearse consequential plans; avoid an extra approval for a familiar bounded plan.
9. Render showing and weekly counts directly. A new interpretation needs judgement; reciting already checked facts does not.
10. One due-action sweep and a second-host end-to-end health probe detect missed progress and failed observation. Cache last-known truth; stop new authority-sensitive effects on record loss.
11. Keep case rulings and manual explicit standing authority; full showing first, independent audits and demotion on defects. Defer automatic trust policy and inferred preferences.
12. Meter raw owner interactions, original par, actual/missing usage, total spend reservations, maintenance/recovery and escaped defects. Do not infer saved thought from fewer prompts.
13. First version: one low-risk reversible local tool/report or settled-wording change, one launcher, one doer plus separate checker, one new-contract challenger, one publisher, one record/doorway and secondary observer; no board mirror or five-tool integration programme.
14. The medium two-slice case needs five helper runs; a genuinely one-slice bounded case needs four. Straightforward template reuse can remove new-contract preparation/challenge only within explicit standing authority; it does not remove result checking.
15. The first-version win is a repeatable goal reaching agreement + showing with failed checks/known defaults handled without another owner cycle, no status-chasing, and full cost evidence. A matched replay must establish a real avoided cycle; historical records alone cannot prove it. If it cannot beat the current matched pattern without more escaped defects or recovery effort, stop adding machinery.

## Cheap tests before committing to a build

| Test | Cheap method and reject condition |
|---|---|
| Does the model start cost erase the saving? | Use retained receipts first; on the next separately authorised trial compare matched small and medium goals under current coordinator, five-run and six-run paths, same model/tools/checks. Record actual complete usage, caching, elapsed time and human setup. Reject a “cheaper” claim with missing billing or a dearer accepted goal unless a measured owner-time benefit justifies it |
| Can a small packet preserve intent? | Blind replay several retained goals, including D4's narrowed-away criterion, unmet performance target and premature owner-wait closure. Provide only information available at each point; compare contract and checked result with later evidence. Reject silent loss of an original constraint, spurious rule authority or restart rediscovery |
| Do checks catch something? | Tabletop old/broken and plausible-but-useless candidates against frozen criteria, then ask an independent checker without the maker's verdict. Include target/device/account limits from S's work kinds. Reject green closure from compilation, a screenshot, provider receipt or transport acknowledgement alone |
| Does quiet survive failure? | Before product code, walk a timestamped event sheet for killed/stuck worker, dropped answer/result, two competing attempts, sleeping host, missing watch and dead record. Require one next action/owner, fenced stale writes, explicit unknown, bounded retries and safe restoration; later replay the same cases against real wrappers |
| Is the gate humane and honest? | Walk all fourteen scenario events on text cards; include five days away, several simultaneous genuine urgent acts, changed answers and expired proof. Count distinct reactions/minutes/words/pushes with one cycle rule. Reject hidden parked obligations, a suppressed emergency or a repeated consent request inside an existing grant |
| Can one person operate and diagnose it? | Another reader gets the six-stage diagram in words and one week's mock receipts; allow five minutes to explain a goal and trace why it acted. Restore a sample acknowledged record/proof copy and locate an expired source. Reject transcript dependence, ambiguous authority, lost acknowledgements or an unnamed incident owner |

Ranking of the full designs for a very small team: **1 R; 2 C; 3 O; 4 K.** Recommend reduced R for the first version. K's single-writer first version is competitive once its extra packaging is removed; the difference is real operating machinery, not the metaphor. These are design judgements to test, not production cost or reliability findings.
