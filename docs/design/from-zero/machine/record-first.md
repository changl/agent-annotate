# The record is everything; reading everything is forbidden

## 1. The idea

One ordered record keeps what was said, authorized, attempted, checked and decided; a claim of success is recorded as a claim until somebody else checks it.
Small scripts turn new facts into work, deadlines and the person's next sitting, while a temporary helper receives one complete job with the whole accepted goal and only the evidence that job needs.
I leave the starting centre in two places: disposable current views prevent repeated reading of history, and a helper keeps one coherent piece of judgement together rather than being restarted for every thought.

## 2. What is kept in the record

A fact has a unique receipt, format version, ordered number, observed and received times, validity deadline, goal, writer and role, cause, agreement version, affected object's expected version, and body or immutable attachment reference.
The writer retries with the same receipt after a lost reply; the record returns the original result rather than appending twice. Times supplied by a computer are observations; deadlines use the record's clock.
One small writing service orders accepted writes and enforces permissions. Helpers cannot edit old facts; corrections name what they replace. Only this service can change current authority.
Here a lease means an exclusive claim until a time; fencing revokes its right to publish without claiming its process stopped. A fingerprint identifies exact content, and an input manifest lists the sources in one job's reading packet.

| Kind | Fields beyond the common fields | Who may write it |
|---|---|---|
| Goal stated | His exact words or consented transcript, source, inferred project with reason | His doorway; a receiving script preserves his authorship |
| Agreement proposed / checked / accepted | Heard goal, numbered done lines, exclusions, delegated choices, owner-only choices, assumptions, spending limit, next showing, par, checking plan | Preparing helper proposes; another helper checks; he accepts, or an existing explicit delegation authorizes acceptance |
| Work offered / claimed / ended | One deliverable, dependency versions, reserved shared resources, abilities, permitted effects, input manifest, effort limit, expiry, attempt, outcome | Dispatcher offers; claiming service grants exclusive authority; runner reports outcome |
| Evidence / check result | Exact result fingerprint, done-line version, method, environment, observation, counterexample tried, pass/fail/unknown, checker identity | Maker may attach evidence; an authorized independent checker alone may attest a pass |
| Fork / gate decision | Alternatives, recommendation, why only he can choose, consequences, authority, fallback, deadline, first-ready time, estimated review minutes, relevance, rule considered, disposition | Helper prepares; another helper challenges necessity; gate script records disposition |
| Showing / exposure / ruling | Checked result reference, visible words, assumptions, opened/answered times, answer verbatim, correction scope | Script assembles showing; doorway records exposure; only he rules |
| Rule proposed / activated / retired | Original ruling, reason, scope, exceptions, match fields, explicit authority or inferred preference, expiry, supersession, applications and reversals | Helper proposes interpretation; independent helper checks fidelity; script activates only within his expressed authority |
| Clock / park / promise | Due time or named dependency, reason, fallback, retry budget, promised time and changes | Scripts from accepted commitments; he may explicitly park or change a promise |
| Effect requested / observed | External target, unique operation key, resource authority number, old/new fingerprints, acknowledgment or unknown outcome | Effect service with current authority; observer records what actually happened |
| Stop / amend / revoke / restore | Scope, reason, new authority version, affected work, replacement agreement or known-state reference, restoration checks | He commands directly; scripts may stop unsafe work within standing limits, never invent broader restoration authority |
| Trust / meter | Work kind and risk, acceptance or miss linked to evidence, exposure policy authorization; run usage, attention observations, cycle cause | Scripts derive observations; he authorizes a wider exposure policy |
| Participant / health | Capabilities, reachable resource, availability expiry, observer identity, next observation due, watch and backup receipts | Machine runner or infrastructure monitor; no helper conversation is required |

Attachments include results and sufficient redacted proof to recheck them, with fingerprints and retention classes; they are part of the logical record, not a second source of decisions.
Never store passwords, sign-in tokens, private reasoning transcripts, unfiltered customer data, or whole terminal/chat histories by default. Keep restricted proof separately with access receipts; destroy sensitive attachments under retention policy, leaving a non-sensitive tombstone.
The append-only rule therefore applies to decision provenance, not to indefinite retention of personal data. Missing or deleted proof makes a dependent check unknown, never silently passed.

**One test-week goal, at three moments** — the following are readable facts, not a new form for him:

| Moment | Newly appended facts | Current view rebuilt from those facts |
|---|---|---|
| Monday | He said “Faster sign-up”; agreement 1 accepted: (1) new-account path works, (2) existing-account path works, (3) fewer steps with no lost entries, (4) no weaker account protection; showing Thursday; par 2 | Being built; cycle 1; 0/4 done lines pass |
| Tuesday | Work attempt 1 claimed an isolated copy until 10:20; maker attached result A; independent scripts passed existing-account and new-account examples against A | Being built; cycle 1; 2/4 pass **for A**, not for a later edit |
| Friday | Promise moved from Thursday to Friday after the required computer was off; result B replaced A; all four lines of agreement 1 checked against B, including judgement of “fewer steps”; showing opened; he accepted B | Done; cycle 2 against par 2; evidence and acceptance refer to B |

**Keeping it out of the swamp.** Scripts maintain indexed current views by goal, rule scope, due time and causal parent, advancing a saved position in the record. A saved snapshot plus later facts rebuilds them; only a repair job replays old history.
Each job's manifest includes the complete current agreement, relevant source excerpts, applicable rules and contrary rulings, current resource versions, and the last failure if any. Each excerpt names its source; no invented summary becomes authority.
An ordinary manifest aims at 8,000 input tokens excluding the actual work files. Overflow stops dispatch: a helper must narrow the deliverable while preserving the full agreement, or explicitly budget a larger reading job; nothing silently truncates the goal.
Views carry their processed position. A gate or external write checks its cited agreement, rule and resource versions against the authoritative record before acting; a stale view can delay work but cannot authorize it.
Every action exposes one “because” chain: trigger → authority → job → evidence → gate decision. The engine room can follow it without reading unrelated events.

## 3. The runs

These are job types, not a separate service for every arrow. Three reusable executors suffice: accept facts, process changed facts, and run a leased job; an independent clock starts the due work.
Each completion advances one coherent output: an agreement, a work slice, a checking verdict, or a ruling interpretation. Several observations and attachments may belong to that one output.

| Job / starter | Reads → writes | Script or judgement; life and rough effort |
|---|---|---|
| Receive / sentence or answer | Submitted words and receipt → acknowledged fact | Script; under a second ordinarily |
| Update views / committed facts | Only changed facts and affected current objects → view position and deduplicated pending work | Script; milliseconds to seconds, no helper wake-up |
| Prepare agreement / unagreed goal | Words, rules, project clues → 120–180 visible words plus expandable checking plan | Judgement helper; 1–3 minutes, roughly 1–3k input tokens; one-minute reading target, not a guarantee |
| Challenge preparation / proposal | Original words, proposed agreement or owner question, cited authority → missing intent, unsafe default, or ready verdict | Different judgement helper; 1–3 minutes, 1–4k tokens; no new owner question merely to clarify wording |
| Dispatch / accepted goal, dependency or retry | Current agreement, checks remaining, capabilities, budget, attention reservation → one leased deliverable | Script chooses ready work; a helper only when decomposition itself needs judgement |
| Do / claimed deliverable | Full agreement plus selected files, rules and failures → isolated result, evidence, assumptions, or a fork | Helper for novel work, script for a known procedure; one coherent 5–30 minute job, budgeted before start |
| Mechanical check / candidate result | Immutable result, independently approved checking plan → per-line observations | Script; seconds to minutes; never decides taste, preference or authority |
| Observe / checkpoint or uncertain effect | Actual target and last receipt → timestamped observation or unknown | Script; seconds to minutes; compares reality with reported state |
| Judgement check / candidate or repair | Original intent, full agreement, actual result, relevant proof → pass, counterexample, or unknown | Different helper; usually 3–8 minutes, 3–8k tokens; repairs return to a doer |
| Gate / prepared item or deadline | Current rules, checked authority, fallback, relevance, review-minute budget and age → settled, timed, queued or parked fact | Script; under a second; cannot invent a preference |
| Show / sitting or trusted completion | Checked facts and artifact → direct artifact with literal done-line results and assumptions | Script; under a second; novel explanatory claims return for independent checking |
| Learn / scoped ruling or discovered miss | Exact ruling and its case → proposed narrow rule, then independent fidelity verdict | Two judgement runs of 1–3 minutes and 1–4k input tokens each when interpretation is needed; literal local overrides need neither |
| Watch / minute clock | Due index, progress and attempt limits → fence, retry, reroute, park, or one changed-promise item | Script; ordinarily seconds; never asks a helper to poll |
| Ledger / weekly clock or curiosity | Meter and provenance views → counts, comparisons and drill-down | Script; seconds; unknown measurements remain unknown |
| Recover / failed infrastructure probe | Durable receipts, backups and effect observations → restored views or quarantined uncertainty | Script for known recovery; bounded diagnosis helper for a new failure |
| Control / direct command or authorized safety stop | Current authority and affected resources → fences, suspended work, replacement agreement or checked restoration | Script; seconds; novel recovery diagnosis is one helper job capped initially at 10 minutes |

Maker-reported progress may renew a lease only when it names a new artifact, observation or explicit wait with its own deadline. Repeating “working” does not buy time.
Judgement stays together: a doer can investigate, implement and try examples in one run; the checker can examine the whole result. They communicate through results and explicit unresolved facts, not mutual status messages.
Pending work is merged by goal, job kind and input version; ten arriving facts do not create ten helpers. A changed agreement invalidates pending work and requires a current input manifest.
Before parallel dispatch, a script verifies dependency versions and reserves shared files, publishing targets, scarce equipment and attention capacity together; unavailable reservations delay work. An integrated result is checked again across interfaces, not inferred from separate green slices.

## 4. The gate

Entry requires a current, independently checked item with consequences, provenance and a relevance condition. An unchecked proposal stays with its maker; this is admission validation, not an attention decision.
For every new fact, timer and sitting, apply this order, recording the first resolving reason:

1. **Rules.** Apply one current, exactly matching authorized rule, including the accepted agreement. Conflicting or interpretive matches go to a bounded judgement check; uncertainty cannot widen permission.
2. **Default and time.** A reversible implementation choice already delegated is settled without showing it. An owner tradeoff may remain available until its displayed deadline, then use only its authorized fallback; an unaccepted new goal never starts by timeout. If no action is authorized, the fallback is park, preserve data, or miss the deadline explicitly.
3. **Capacity and age.** Start with ten estimated review minutes per sitting, reserving two for urgent work; replace this policy with observed service capacity as sittings accumulate. Estimate from comparable actual interactions, inflate uncertain estimates, and reserve future showing minutes against their promised sitting before starting dependent work. Overflow parks lower delay-cost eligible goals with explicit return plans; items cannot wait ready beyond one workday without an authorized default or park. Count age from first readiness, never reset it by rewriting a question.
4. **Expiry.** Recheck relevance before display and after every dependency change. Withdraw obsolete items with a ledger receipt; an expired answer cannot act on an old result. A parked goal names its resuming script, due date or event, fallback and working reminder route; it releases review capacity.
5. **Sitting.** Fill the minute allowance by externally evidenced cost of delay, then age. He opens one doorway and gets agree, look or decide, one at a time; defaults run on time even if he never opens it. At answering time, check versions again; changed facts produce a fresh checked item. An overrun ends admission, not a forced rushed decision.

The rule book also ranks an existing commitment's delay cost; helpers cannot mark themselves urgent without evidence. Each distinct decision carries its own minutes; grouping cannot make its cost vanish. Seven items is not a capacity rule.
**Narrow push lane:** an independently verified owner-only act, a real consequence before a reasonable next sitting, and no permitted substitute. A sign-in needed by 3 pm qualifies; a helper's impatience does not.
Push once with the act, deadline, consequence and safe fallback, using urgent minutes and parking ordinary work if necessary. One urgent item is the normal push budget; simultaneous real emergencies explicitly exceed that budget rather than suppressing one, and all their minutes are counted.
Promise changes use one separate, deduplicated one-line notice with the new time and reason. These notices and urgent sign-ins both count as interruptions; “no status” cannot honestly mean no such exceptions.
Delivery retries reuse one notice identity. If no acknowledgment arrives, keep the item visible and execute its fallback; never interpret silence as sign-in or invent a second communication channel without authorization.
He can open original evidence, omissions and disagreements, and issue stop, amend, revoke or restore directly without the counterpart's permission. A named backup receiver on another failure domain accepts direct commands if the preparation path fails; it uses the same record, not a rival authority.
Checkers may append protected dissent directly; the gate processes it independently of the counterpart, using the same urgency test. It cannot be deleted by a maker or hidden to improve cycle counts.

## 5. The checks

An agreement pairs each plain done line with an observable example, failure example, checking method and required authority; the person sees the sentence, with details expandable. The agreement reviewer challenges whether these examples actually cover his stated intent.
Example: “Texts arrive early enough for people to attend” becomes “For a booked lesson, one reminder is handed to the delivery provider 24 hours before, in the learner's time zone; rescheduling cancels the old reminder; no duplicate; failures are visible.” Those are proposed boundaries, not secretly substituted definitions of attendance.
Scripts check timing with a controlled clock, time zones, cancel/reschedule and duplicate examples, delivery receipts and failure reporting; a second helper checks the original complaint against the workflow and tries a late-booking counterexample.
Only he can decide whether 24 hours is the right experience if neither the agreement nor an existing ruling delegates it. Actual attendance improvement requires later observation and is not “proved” by a delivery receipt.
Proof binds result fingerprint, check-plan revision, fixture/environment, observation and independent identity. Every later edit invalidates affected checks; old green results do not float onto new work.
For judgement, the checker sees intent and the result before the maker's persuasive account, then accesses that account as evidence. It must name a counterexample tried and the observation behind each pass; “looks good” is rejected structurally.
Maker and checker have separate run identities and isolated work areas. A script can independently check deterministic output; a different helper is required for subjective checks. Different models can reduce shared blind spots, but different names alone do not establish independence.
The checker cannot edit the candidate and then pass its own repair. Inconclusive proof is unknown; the watch gets a bounded recheck, never an automatic pass. Disputed judgement gets one second checker, then a concrete owner question only if it is an owner value choice.
He sees the thing, the checked plain sentences and assumptions. Raw proof, failed attempts and counterexamples are one level down; script-verifiable correctness never becomes his acceptance chore.
Trusted work retains the same independent checks. Trust reduces showings, not evidence, authority checks or maker–checker separation.

## 6. The watch

| Clock | Trips when | Automatic consequence |
|---|---|---|
| Dispatch acknowledgment | Unclaimed offer after 2 minutes | Offer to another capable awake machine; same logical job, new attempt |
| Progress lease | 10 minutes without new durable progress; watch every minute | Fence the attempt, isolate its outputs and reroute within the retry budget; no assumption that its process stopped |
| Run budget | Its accepted 5–30 minute limit or spending limit is reached | Fence and save partial evidence; one bounded replan if needed; never an endless renewal |
| External wait | Named dependency's due time, initially at most one workday unless agreement says otherwise | Observe once, then permitted fallback or explicit park with next trigger; waiting is not progress |
| Showing forecast | Remaining verified work no longer fits the promise | Try available capacity first; if recovery cannot preserve the promise, append a new promise and issue one change notice |
| Default / expiry / park | Its exact due time, relevance change or named event | Run the gate; settle, withdraw, or reserve capacity and resume |
| Delivery receipt | No durable acknowledgment after 30 seconds | Retry same operation, increasing intervals to 5 minutes; at the act's deadline take its fallback |
| Capability availability | Machine runner misses two 1-minute availability renewals | Stop assigning new work there; affected work still follows leases and safe-effect recovery |
| Observation freshness | A checking plan's observation deadline passes; live service observations default to 10-minute validity | Mark stale state unknown and run an independent observation; immutable proof remains valid only for its exact result and unchanged assumptions |
| Record and watch health | Separate monitor misses two 1-minute probes or sees watch position older than 2 minutes | Inhibit external effects; change doorway to “state unavailable”; send one infrastructure exception through an independently available authorized channel |
| Proof / rule validity | Referenced source changes, relevant miss, or 30-day review for a general rule | Invalidate dependent passes or suspend automatic rule use; schedule bounded checking |
| Trust observation | New acceptance, reversal or defect; weekly audit | Recompute eligible policy; propose promotion, immediately demote after a relevant miss |
| Ledger / backup | Week closes; backup every 5 minutes | Append report reference; copy encrypted committed record and proof inventory, record restored-position checks |

These are starting policy values, not measured optima. Two failed attempts for one deliverable exhaust its ordinary retry budget; it parks for one diagnosis, not infinite automated retries.
An unacknowledged external write is observed before retry. If the external system cannot reject an expired authority number or deduplicate an operation, no second writer is started until the first outcome is known; an isolated copy can still be checked safely.
No unguarded side effect is repaired merely by starting another helper. If both the watch and its independent monitor are unavailable, recovery is not bounded; the design says so rather than calling silence healthy.
Every glance shows last observation and next checkpoint, distinguishing reported, observed, checked, blocked and unknown. The separate monitor checks each observer's due receipt as well as the watch, so an awake but broken observer cannot silently preserve green state; expiry plus the minute watch bounds detection.
Stop and revoke immediately raise the authority version and fence affected jobs; amend suspends incompatible effects until a revised agreement is accepted. Restore selects a known result, observes current effects, checks the proposed reversal independently, then publishes only within current authority; irreversible effects remain explicit damage, not a fictional rollback.

## 7. Rules and trust

His answer is first a ruling on an exact case. A correction is offered “here only, or always?” beside the thing, in the same sitting; unanswered scope means local only. An explicit “always for welcome emails” supports that scope, not every kind of writing.
A helper turns general words into a proposed rule with reason, positive cases, exceptions, expiry and source ruling; another checks fidelity. Explicit standing authority is separate from inferred preference: the latter can rank recommendations but never permit action. Clear authorized scope activates after checking; inferred wider scope stays a proposal.
Retrieval first uses project, action, work kind, risk and affected resource to find exact rules and exclusions. Semantic search may suggest candidates to a helper, but a similarity score never authorizes action; record which candidates were considered, including “none.”
Order: explicit current-case instruction, explicit supersession, then an unambiguous applicable scoped rule. Newer does not automatically beat more specific; conflicting rules without explicit precedence suspend that choice until interpretation or his ruling resolves it.
A miss, changed source or expired review stops automatic application and finds all results whose decisions cited that rule; checks establish actual damage before rollback. The corrected rule keeps the wrong predecessor and counterexample visible in provenance.
Trust is keyed by work kind, risk, checks and scope, not by a helper or project-wide reputation. Count first-time acceptances, send-backs, later defects, sampled delegated outcomes and their observation age; silence is never an acceptance.
Three consecutive first-time acceptances permit only a proposal for reversible wording edits; activation also needs observed successful outcomes after their declared defect window (initially 48 hours), a random independent audit, and his explicit delegation. These thresholds are testable policy, not statistical proof; default uptake and silence do not count as preference or successful outcomes.
Initially par is 2 plus named taste stages; skipping a delegated agreement gives par 1; skipping both with standing authority gives par 0. Freeze par at admission and show later authorized changes separately, never rewrite a bad week into a good one.
Delegated results all get independent checks and a weekly random one-in-five secondary audit. A relevant defect or material change in task scope, model/workflow, checking method or consequence resets the earned exposure policy; requalify before reducing showings. Trust never removes explicit approval for an irreversible act.

## 8. The meter

Every run records goal, cause, role, manifest fingerprint and size, source reads, start/end, retries, provider-reported input/cached/output usage and actual charge if available; scripts record elapsed and processor time. Missing billing data is marked unknown or priced explicitly as an estimate.
A cycle occurs whenever a prepared goal item is presented for his reaction in a sitting or answered directly; one item with an inline correction is one cycle. Re-presenting it after a send-back or deferral is another, with a cause. Automatic checks, hidden drafts and expired unseen questions are not cycles.
Count agreement, taste, owner fork, showing and rework separately; show actual cycles minus frozen par with causes. Distinguish preventable repetition from useful discovery, changed intent, dissent and bad news; an extra cycle is not automatically waste or a worker penalty. Unopened pushed notices still count as interruptions.
The doorway records visible word count, typed/spoken words, taps, active foreground intervals and action time; end an interval after 30 seconds idle. These are observed interaction minutes and words displayed, not a claim to measure thought or actual reading.
Shared record/watch/ledger cost is shown both as overhead and allocated across active goals; rule-learning cost belongs to its originating goal. Policy approvals have their own attention entries so zero-cycle goals cannot hide their price.
Weekly aggregation yields done goals, cycles against par, observed minutes including setup/intervention/recovery, decisions delegated, rules learned, send-backs, escaped errors, checks that caught defects, waiting age, and questions this week/last. Offer one optional weekly load rating; absence stays unknown. Open and reopened goals remain in the accounting.
The engine room exposes one goal's causal chain, all attempts and total cost. Compare repeated-manifest bytes and actual provider context usage separately; transcript size alone cannot prove rereading or savings.

## 9. Trace the test week

| Event | Runs and record | What reaches him |
|---|---|---|
| 1. Morning sitting | Gate revalidates three items; doorway records ratings agreement acceptance, invoice acceptance with six checked lines/two assumptions, and price ruling (yearly at 5 pm if unanswered) | Agree, look, decide in one place; supplied estimate eight minutes, then nothing outstanding now |
| 2. Walking sentence | Receive saves his 12:40 words, infers Driving app from matching lesson/reminder context; agreement helper and reviewer prepare a bounded reminder goal | Local receipt immediately; a checked agreement at his next sitting; no project form or push |
| 3. Seventeen questions | Exact-rule lookup records 11 applications; checked delegation settles three reversible choices; three remaining owner forks reserve estimated review minutes, parking lower delay-cost work if necessary | Three prepared choices at a sitting, each with fallback and deadline; none of the other fourteen |
| 4. Wrong welcome sketch | His marked result and correction become facts; rule job checks a proposed tone/length rule after he scopes it; independent checker reviews revision | “Here only, or always?” inline, then the corrected thing; one rework cycle with cause, no progress messages |
| 5. Not now | Park fact names completion of Faster sign-up as trigger and dispatcher as resumer; stop dependent dispatch and release ratings review minutes | Receipt “Ratings waits until sign-up is done”; resumption automatically follows accepted sign-up completion, not an ask to remember |
| 6. Silent forty minutes | By minute 11 the watch fences the silent lease; dispatcher uses another machine and latest durable evidence, quarantining late writes | Nothing: recovered work keeps the promise; recovery cost is still counted |
| 7. Computer off overnight | Availability and leases expire; routing tries another resource; a required unavailable resource forces a checked Thursday-to-Friday promise change | One pushed line: “Faster sign-up shows Friday: its required computer was off overnight” |
| 8. Sign-in before 3 pm | Independent check verifies release deadline, owner-only sign-in and one-week consequence; gate records a 2:30 pm push and safe fallback | One direct sign-in link, “By 3 pm or release moves a week”; no answer means no release, not invented consent |
| 9. Dead old question | Relevance update withdraws it, releases review capacity and preserves the cause | “One old choice no longer needed” in the ledger; no tidy-up request |
| 10. Three acceptances | Trust reducer proposes scoped delegation; reviewer checks reversibility, observed outcomes and random audit; missing qualification blocks activation | One ledger proposal: “Do bounded wording edits and report them?”; par 0 needs both his yes and qualification, never the streak alone |
| 11. Late-discovered error | Observed defect reopens result, suspends implicated rule/trust, checks dependent results, dispatches repair and independent recheck | One checked correction item at next sitting, earlier only for verified continuing harm; ledger corrects the prior success |
| 12. Three days away | Timers have applied permitted defaults and parked unsafe or aged work; gate checks observation age and fits fresh items into the review-minute allowance | First: current truth, including unknowns, then any real urgent act and an estimated ten-minute sitting; overflow gets return plans, not a hidden pile |
| 13. Weekly ledger | Ledger script aggregates committed meter, authority and checking facts, preserving missing values | The stated weekly fields and links to decisions/results; no fabricated “seven done” if the trace does not establish seven |
| 14. Curiosity | Read-only view follows goal → attempts → machine and cost, displaying provenance and measurement gaps | One level down, all 27 helpers and three computers including the asleep one; nothing pushed |

This trace requires one place, two unchosen notices (events 7 and 8), and no remembered return dates. Additional emergency notices would be counted, not hidden as “service messages.”
Words, taps, owner-only decisions and minutes depend on actual agreements, three fork contents and responses not supplied here; the meter counts them at presentation rather than inventing a comparative total. The eight-minute first sitting is a scenario input, not a measurement.

## 10. What breaks it

| Failure | What catches it, and when |
|---|---|
| Helper stops silently | Progress lease expires within 11 minutes; fence before rerouting, keep its process status unknown until observed |
| Helper waits forever | Required wait fact has a due time, at most one workday by default; missing progress instead trips the 11-minute lease |
| Message lost | Durable pending job survives; no claim in 2 minutes reroutes; lost commit reply retries the same receipt; delivery without receipt retries after 30 seconds |
| False “done” | Maker cannot write a pass; independent checks run before exposure, bounded by job budget; a shared blind spot may escape until audit or real use |
| Restarted helper forgets | Claim requires a fresh full-goal manifest; old run has no continuing authority; unfinished effects are observed before new effects |
| Two helpers change one thing | Isolated copies and one numbered publishing authority per resource; authoritative write rejects old numbers immediately; unguarded targets must serialize and reconcile |
| Computer off | Availability expires within 3 minutes; lease/recovery handles current jobs; unique hardware may still force one changed promise |
| Record unreachable | Call failures stop commits immediately; independent health monitor marks unavailable within 2 minutes; cached views show last-known time and cannot say “nothing needs you” |
| Wrong rule | Source-change review or contradicting check suspends it immediately; dependent-result query finds exposure; quiet semantic mistakes have no guaranteed detection time; protected checker dissent bypasses preparation |
| No answer for five days | Authorized defaults run at their times; sign-in slips safely; unaccepted goals and unsafe choices park, admission stops filling the cap; return shows current work rather than five days of questions |

During record loss, isolated work may continue inside its already granted budget, but cannot publish or accept a new assignment. A sentence can be saved locally as “not yet shared”; he is not told it was accepted centrally.
Restore from the last acknowledged replicated copy or a backup, reconstruct views, then observe external targets before resuming. A five-minute backup is a possible data-loss window; proof or authority gaps remain quarantined. Automatic multi-writer failover is deliberately absent.

## 11. Cost

A medium, already understood goal with no taste fork or repair takes five helper runs: agreement preparation, independent agreement challenge, two coherent work slices, and an independent whole-result judgement check. Scripted checks and showing assembly add no helper runs.
Illustrative budgets: 2 + 2 + 15 + 15 + 5 = 39 helper-minutes and about 2 + 2 + 6 + 6 + 5 = 21k manifest input tokens, plus real work-file reads, outputs and cached usage. They are budgets to test, not observed cost or a saving claim.
Expect roughly 20–40 short script jobs grouped by changed goal and due bucket, plus shared minute-watch invocations; two repair/recheck runs add one bounded loop. A general ruling may add two interpretation/checking runs; an unexpected fork adds preparation/checking as needed and is charged to the goal.
Compared with a continuously coordinating helper, this spends more on fresh starts, explicit manifests, agreement review and independent judgement. It spends less on status turns, reading unrelated conversation, handovers, repeated unanswered questions and showing unchecked results.
The supplied “about 14 coordinator turns, 68% rereading” describes a different unit; it cannot be subtracted from five helper runs. Run both patterns against the same bounded goals with identical checking and measure cycles, owner minutes, actual usage and escaped defects before claiming improvement.
The design loses economically on tiny one-step jobs unless a standing procedure handles them without judgement. An irreducibly broad investigation may need one larger bounded run; multiplying small runs would not fix it.

## 12. Taking part from anywhere

Minimum participant: read a UTF-8 job packet, produce a result plus proof or a reason it cannot finish, and let a runner end or fence the attempt. It need not remember, discover peers, understand the record format or maintain a connection.
The machine runner advertises abilities and permitted resources, requests one suitable job, acquires its receipt/lease, writes the packet into an isolated work area, invokes the chosen helper once, and submits its output under the same attempt identity.
Only the runner and effect service hold scoped record credentials and publishing rights. A board can expose work and dependencies but does not grant permission merely by moving a card; board edits enter as attributed proposals or explicit owner rulings.
Helpers receive confined work files and allowed tools, not broad host or deployment credentials; a participant that cannot be confined may suggest a change but cannot publish it. A submitted result awaits independent checks; ordinary completion also needs his acceptance, delegated completion the previously authorized policy.
An interrupted runner resumes submission from its durable receipt, not from a helper's memory. Participants without scripts/network access can still supply files through a runner; participants that cannot preserve evidence can offer suggestions, never checked completion.
No particular launcher is essential. Specific assignments to today's named tools appear only in the final section, after the design is complete.

## 13. The smallest first version

One writing service on one dependable host; ordered facts and immutable files; current goal/rule/due views; a minute watch and an independent health probe; one phone/desk doorway with say, sit, glance; and the meter present before the first goal.
Support a bounded code or wording change: short checked agreement, one isolated doer, independent checks, showing, scoped local ruling, explicit fallback/park, and one retry. The first goal needs no automatic trust promotion or clever scheduling.
Include causal receipts, authority fencing, proof fingerprints, review-minute/age limits, fresh-observation status, direct controls and observed attention time now; bolting these on later would make the first outcomes unmeasurable or unsafe. Seed no guessed preference rules.
Leave out semantic rule search, automatic decomposition, cross-project optimization and automatic failover. Start on one machine; document the runner contract and add the other required participants through thin adapters, without a second decision store.
Estimated build: 5–8 engineering days for the core including failure replays and basic doorway; another 2–4 for the five participant adapters and cross-machine effect tests. These are design estimates; credential/setup obstacles are not assumed solved.
The improvement mechanism is concrete: a known repeated fork becomes a rule, an implementation default produces no owner cycle, and a failed check returns directly to the maker. The intended bounded goal finishes at agreement + showing, par 2, without an owner-managed stall.
Before construction, replay the supplied week and challenge agreement/check coverage; from goal one compare against a metered current workflow. No historical per-goal cycle baseline exists in the supplied material, so “already beats today” is an acceptance target, not a result this document can prove.

## 14. Three weakest points; corrections to the method

1. **The record and effect boundary are hard infrastructure.** Views are cheap only when ordering, source versions, receipts and fencing are correct; restoration can leave real effects without trusted provenance. A single service is simpler but introduces an availability limit.
2. **Choosing context is judgement in disguise.** A full agreement protects the goal but cannot guarantee the right evidence was selected. Source-linked manifests, negative rulings, overflow admission and whole-result checking reduce this risk; a novel broad goal can still need expensive reading.
3. **Independent checking and early trust remain fallible.** Two helpers may share the same mistaken interpretation; three successes are weak evidence. Sampling and demotion contain harm but cannot prove that silence means correctness.

The outside review (`research/d5-outside.md`, sections 1, 2 and 4) changes the method: minimize attention subject to correctness, harm, recovery and effort, not as the only scarce resource. One-minute agreements and par are targets; reopen intent when discoveries require it and allow him to write constraints when useful.
“Every answer becomes a rule” must mean an attributed case ruling first; generalizing every answer would automate misunderstandings. “Two cycles” is a useful allowance for bounded goals, not a promise for discovery, human authentication or changing intent.
Keep “nothing needs you” separate from “everything is correct”: it means no current authorized owner action is waiting, with fresh watch evidence. Automatic trust should lower required appearances only within an explicitly accepted boundary.

## Existing tools: assignments after the design

Read-only evidence: installed `orca orchestration --help` and its matching guide; `claude --help`; `codex exec --help`; `bd --help`; `wmill --help` and `wmill job --help`. These establish available interfaces, not working authentication, remote execution or end-to-end delivery; the subsequently delivered outside review is incorporated above, without treating its published effects as this design's benefit.

| Need / participant | What could fill it; what still has to exist |
|---|---|
| Ordered record, views and proof | A small transactional database plus immutable restricted files and a writing API could fill this; neither a conversation nor a mutable board alone provides the authority/checking semantics above |
| Orca-run helpers | Existing supervised task/dispatch, worker start, exact-attempt completion and fencing interfaces could launch and account for bounded jobs; a runner must translate record jobs and observe actual effects, without a living coordinator |
| Claude Code | `--print`, structured output, budgets and tool restrictions can run a fresh judgement job and exit; wrapper supplies the manifest, identity, isolation, meter and durable submission |
| Codex command-line helpers | `codex exec`, schema output, JSON events and ephemeral mode can run fresh doer/checker jobs; the same runner supplies authority, bounded inputs, evidence and accounting |
| Beads board | Ready work, dependency links, claim/reclaim, comments and JSON export can mirror offers/results and import deliberate board actions; the record remains authoritative and stale cards cannot authorize an effect |
| Windmill | Scripts, flows, schedules, worker groups and inspectable job results could run reducers, the watch and deterministic checks; an independent monitor must live outside that failure domain |
| Person's doorway | A small shared web view could render the record's prepared items and receive direct rulings on phone/desk; existing pages qualify only if they can preserve versions, receipts, the cap and artifact-linked answers |

None of these tools alone supplies the accepted agreement, rule fidelity, owner-attention gate, independent meaning of “done,” scoped trust or cycle accounting. Those are the small shared contract to build; every adapter must obey it rather than creating another place he must manage.
