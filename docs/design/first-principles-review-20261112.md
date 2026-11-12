# agent-annotate from first principles

Chang asked on 2026-11-12: if we started from scratch, as an Orca plug-in and/or a standalone tool, what would agent-annotate look like? Three goals:

- agents on several Macs and several coding agents take part (at least Orca, Claude Code, Codex CLI, Beads, Windmill);
- building with AI is as seamless and effective as possible;
- the thinking load needed to build world-class work drops sharply.

Research and design only. Nothing live was changed. Numbers without a named source were measured on this Mac (M1 Max) on 11–12 Nov 2026.

## 1. Answer

1. **Purpose.** agent-annotate is the one place where the reviewer's decisions enter the build, and the mechanism that carries each decision to the right agent once and shows that it was acted on. Nothing else.
2. **Shape.** A small standalone service that owns the records, with three thin faces: a command for agents, a web page for any browser or phone, and an Orca plug-in that shows the reviewer what needs him. Recommended over a plug-in alone and over standalone alone (section 4).
3. **Several Macs.** One home for all pages, on M1 Max. Other Macs and every kind of agent use the same four commands over the tailnet (section 5).
4. **Today's product.** Keep the round, the card, the per-page database and the scripts. Change 17 page servers into one and 45 commands into four. Delete the compatibility paths (section 6).
5. **First stage.** One week, read-only: a "needs you" count and list in Orca across all pages, plus a weekly baseline of the reviewer's load computed from data already stored (section 8).

## 2. Already decided, measured or built

Not reopened here. The design builds on these.

**Decided by Chang** (review page version, card number):

| Decision | Where |
|---|---|
| Scripts and stored state do the bookkeeping, not agents. | v27 #2, #4; v67 #154 |
| A change that adds things to do or check is wrong; the aim is fewer. | v41 #15 |
| One page per project, whatever its repos and worktrees. | v7 #15 |
| A version shown for review is frozen; the owner decides readiness. | v64 #48 |
| One database per page; SQLite, not Postgres. | #213; `docs/validation/simplification-plan-20261104.md` |
| Routine runs use no agent and no tokens. | #84, #90 |
| Board judgement needs AI, runs in a separate worker, and a submitted round is only the trigger. No timed sweep. | v84 #241; v87 #243 |
| Capacity questions are handled automatically, not asked. Multi-step setup is not handed to Chang. | v78 #239; v81 #240 |
| Sessions run for weeks; quiet waiting and the 250k handover are rolled out. | #207, #225 |
| No sideways scroll with the rail closed; colour meanings; tabs, not a dropdown; newest first. | #226; #136, #123, #148; #230 |

**Measured:**

| What | Result | Source |
|---|---|---|
| Baseline, 30 Oct–4 Nov | FLD coordinator $1,204 in 84 h, $52 per round, median context 509k. 48–82% of cost was re-reading context. Waiting on workers and mail was 42%. Annotate share 6.1% (FLD), 17.4% (this project). | `docs/validation/simplification-plan-20261104.md` |
| After stages 0–3, 7–10 Nov | FLD $94.93 in 71.7 h, $8.63 per round, median context 138k. Annotate share 6.2% (FLD) and 4.7–11.0% (this project's four sessions); goal 3%. Shell reads and search are now the largest cost, 40–51%. | `shared/agents/cost-3day-20261110/` |
| Bookkeeping, 31 Oct–7 Nov | No evidence supports another status or polling feature. The reviewer's side (clicks, time, reminders) is unknown. | `shared/agents/bookkeeping-evidence-20261107.md` |
| Mail routing replay | 9,175 coordinator messages caused 3,181 turns; 1,061 under quiet-wait rules; 708–1,011 with the router. | FLD usage audit, `router-replay.md` |
| Board sweep model trial | Opus 5.5: 85% correct, $1.68 per sweep. Timed sweeps were then rejected (#241). | FLD usage audit, `model-trial-score.md` |

**Built** (`CHANGELOG.md:1-58`): one-line receipts, batch resolve, cost meter (2.28.3). Ask fences, one publish command, self-numbering, `--section`, the per-page database behind `store.py`, `rollout.py`, `sweep.py` (2.29.0). Pages moved to the database, FLD held on JSON (2.30.0). `annotate board`, with the round as trigger and judgement in a separate worker (2.31.0, 2.31.1).

## 3. What it is for

### Who acts

| Actor | How many | What only it can do |
|---|---|---|
| Reviewer (Chang) | 1 | Set and change goals. Choose where the trade-off is taste or business. Approve what is irreversible or leaves the building. Say what is wrong that nobody asked about. |
| Coordinator agents | One per project: 19 pages here, 4 on M5 Max | Turn goals into work, prepare decisions, judge worker results. |
| Worker agents | Many, short-lived: 64 in three days on FLD | Do one scoped job and report once. |
| Scripts and services (Orca, Beads, Windmill, hooks) | — | Everything that follows a rule: route, number, count, remind, test, roll out. |

The reviewer's attention is the only input that does not scale. Agents and scripts can be added; a second Chang cannot. So the product is judged by one question: how little of his attention does a correct decision cost?

### Three jobs

1. **Show.** Put a decision in front of the reviewer with its evidence, a recommendation and what each choice causes.
2. **Capture.** Record the answer once, durably, with who and when.
3. **Deliver and close.** Wake the right agent once. Show the reviewer that the answer was acted on, with proof.

Not its jobs: running agents (Orca), tracking work (Beads), running routines (Windmill), storing documents (the repo). Where today's product does one of those, it should hand the job back.

### Who must do what

| | Must do | Must never have to do |
|---|---|---|
| Reviewer | Read a short card, choose or type, press Send. Leave a free note when something is wrong. | Find where the question is. Remember to come back. Run setup steps. Answer the same kind of question twice. |
| Agents | Write the card: context, recommendation, consequences. Read answers once. Prove what was done. | Number, route, track owners, restart servers, remember to run checks, re-read stored state. |
| Scripts | Everything in the two "never" cells above. | Judge. |

Every point below is tested against this table.

## 4. Target design: a standalone service with an Orca face

### Parts

```text
reviewer ── web page (any browser, phone) ──┐
reviewer ── Orca plug-in: count and list ───┤
                                            ├── one service ── one database per page
agents ──── command, four verbs ────────────┤        │
Windmill ── same HTTP API ──────────────────┘        └── outbox ── Orca ── owner's terminal, any Mac
```

1. **The service.** One process, one port, one share-link root. It owns every page's database, versions and rounds, and an outbox of wake-ups. It serves the page. It is today's Python package, reduced.
2. **Agent face.** The `annotate` command as a thin client of the service, plus a skill inside today's 700-token budget. Four verbs: `ask` (post cards or an update), `read` (answers addressed to me, once), `done` (close items with proof), `status`. Identity comes from the environment (Orca terminal handle, session id) and is never typed.
3. **Reviewer faces.** The web page stays the place where a question sits beside its evidence. The Orca plug-in adds presence: a status-bar count, a side panel of what needs him across projects, one click to the card. It stores nothing.
4. **Routines.** Scripts and Windmill react to service events (round submitted, version published). No agent has to remember to run them.

### Why not a plug-in alone

| Limit | Evidence |
|---|---|
| A plug-in cannot give agents their tools. | `skills`, `mcpServers`, `taskSources`, `connections` and `sidebarCards` are "Reserved (must stay empty arrays)": Orca plug-in manifest reference, Orca 1.4.256. |
| Panels cannot reach the network or a terminal; only the worker can. | Orca plug-in host API reference: "No network"; "A panel cannot type into a terminal". |
| Tool hooks cannot guarantee delivery. | Orca waits on tool hooks only for Claude Code; other agents report only; agents over SSH are not hooked (Orca plug-in events reference). |
| Review also happens outside Orca. | The share link is the canonical way in, and the page must work on a phone (`docs/interaction-contract.md:16`, `:23`). M1 Max 16 runs agents and has no pages. |
| Nothing but themes has been proven here. | The only plug-ins installed on M1 Max and M5 Max are two official themes. Status-bar items and hooks exist only since Orca 1.4.248. |

### Why not standalone alone

| Gap | Evidence |
|---|---|
| No single place shows what needs the reviewer. | 19 pages here and 4 on M5 Max, each with its own link. The waiting count is per project, printed at session start. |
| Agents claim page ownership, and it goes stale. | `src/agent_annotate/delivery.py:108` captures the claimer's terminal and `:159` refreshes owners; owner rebind on resume had to be added in 2.28.3. Orca already reports every agent's state (`agent.status.changed`) and every workspace on every host (`workspace.list`). |
| Three unconnected ways to ask the person. | Annotate cards; `orca orchestration gate-create` ("Create a decision gate blocking a task"); `bd gate` (type `human`). How often the other two are used was not measured. |

### What the Orca plug-in does

- **Status bar.** "3 need you", coloured when above zero. Pressing it opens the list.
- **Side panel.** Open decisions grouped by project, oldest first. A row opens the page at that card. Answering stays on the page beside the evidence, as today's rule requires.
- **Worker.** Reads the service's one read-only list. Later it maps Orca's agent and workspace events to page owners, so agents stop claiming.
- **Size.** A few hundred lines and no stored state. If Orca is closed or its plug-in system changes, pages, agents and delivery keep working.

## 5. Several Macs, several agents

### Today

| Mac | Release | Pages | Notes |
|---|---|---|---|
| M1 Max (this one) | 2.31.1 | 19 registered; 17 server processes on ports 8800–8819 | FLD's main page is still on JSON |
| M5 Max | 2.29.0 | 4, plus one page on 2.28.2 and one unregistered server on 2.27.6 | Two releases behind |
| M1 Max 16 | 2.29.0 | None | Launcher not on PATH for non-interactive shells |

Each release is installed on each Mac, needs Chang's approval for each other Mac, and restarts every page (`docs/routine-scripts.md:21`, `:27`). `src/agent_annotate/version_guard.py` (557 lines) exists only to detect differences among the launcher, skills, plug-in and pages.

### Target

One home. The service runs on M1 Max, which already hosts this project's Beads database (`bd where`) and Windmill (`docs/validation/stages-3-5-specs-20261104.md`). Other Macs install only the thin client and reach the home over the tailnet. A client that cannot reach home keeps a small outbox and retries; a read fails fast with one line.

| Participant | How it takes part | Exists today | Missing |
|---|---|---|---|
| Orca | Carries each wake-up to the owner's terminal on any Mac. Hosts the plug-in face. | Delivery through Orca (`src/agent_annotate/delivery.py:231`); paired environments M5Max and M1Max16. | The plug-in; owners taken from Orca events. |
| Claude Code | Four verbs through the command; the skill; one session-start line. | Yes. The skill is 32 lines. | Nothing. Fewer commands. |
| Codex CLI | Same command and skill. Rounds arrive through Orca, so no hook is required. | Yes (`plugins/codex/`). | Remove any reliance on hooks; new Codex sessions stop to have hooks reviewed. |
| Beads | Work items stay in Beads. Cards and findings link to beads; the page shows counts. A human gate in Beads points at a card. | Links accept bead ids (`src/agent_annotate/project_state.py:115`); `annotate board`. | The gate-to-card link. |
| Windmill | Runs routines with no tokens. Posts results as proof through the same API. Starts from service events. | `wm-test`, `scripts/rollout.py`, `scripts/sweep.py`. | An event trigger; a service identity. |

Workers do not talk to the service. They report to their coordinator through Orca, which is already the rule. Only page owners and scripts are clients, so each project has a handful of participants however many workers it runs.

## 6. Today's product: keep, change, delete

Size today: 27,746 Python lines in 56 files and 11,433 JavaScript lines. `cli.py` is 6,057 lines with 45 command names. `sync_server.py` is 4,385 lines with about 22 API routes.

### Keep

| What | Evidence |
|---|---|
| One page per project; questions sit beside their evidence. | `docs/interaction-contract.md:3`; v7 #15 |
| Send is one durable round, then one wake-up. | `docs/interaction-contract.md:20`; `docs/architecture.md:33` |
| The card: context, recommendation, options. | All 114 stored cards on this page carry a recommendation. Where the pick was recorded, Chang chose the recommended option 41 times in 47. Ask fences cost 8 markup tokens against 76 (`CHANGELOG.md`, 2.29.0). |
| One-line receipts and batch resolve. | A three-answer round went from 5 commands and 362 tokens to 3 and 149 (`CHANGELOG.md`, 2.28.3). |
| One database per page behind `store.py`. | `src/agent_annotate/store.py:132`, `:325`; unread inbox 39 ms against 144 ms (`CHANGELOG.md`, 2.29.0); #213 |
| Publish rules applied by script. | `src/agent_annotate/long_pages.py:3` ("no agent step, never a refusal"); `src/agent_annotate/decision_quality.py:1` |
| Frozen versions during review. | v64 #48 |
| Board judgement in a separate worker, triggered by a round. | `docs/routine-scripts.md:57`; `src/agent_annotate/board_checks.py:1`; v87 #243 |
| Routine scripts with no tokens. | `scripts/rollout.py`, `scripts/sweep.py`; #84, #90, #154 |
| The small skill and the cost meter. | Skill 32 lines, about 662 tokens against a 700 budget; `scripts/orch_cost.py` |

### Change

| From | To | Evidence |
|---|---|---|
| One server per page | One service per Mac, then one home | 17 `sync_server` processes for 19 pages. A rollout restarts every page (`docs/routine-scripts.md:21`). |
| A full install on every Mac | One home and thin clients | Three Macs on two releases, plus two stray servers on M5 Max. `version_guard.py` is 557 lines of mismatch detection. |
| 45 command names | Four agent verbs, plus an operator group agents never see | `cli.py` 6,057 lines. Chang, #142: "quite wieldy… prone to introduce a lot of hallucination and confusion for the agent especially the orchestrators". Annotate share is 6.2–11.0% against a 3% goal. |
| Agents author whole page versions | Agents post items; the service builds the page | 94 versions of this page in 46 days. 13.1 commands per version drafted on FLD and 38 in one session here (`shared/agents/cost-3day-20261110/`). 113 page-helper and 286 publish-helper calls in a week on FLD (`shared/agents/bookkeeping-evidence-20261107.md`). |
| Agents claim ownership | Owners follow Orca's live agents | `delivery.py:108`, `:159`; owner rebind added in 2.28.3 |
| Three ways to ask the person | One record: the card. An Orca gate or Beads gate waiting on him points to it and closes when it is answered. | `orca orchestration gate-create --help`; `bd gate --help` |
| The same kind of question asked again | Standing rules: an answer that is really a rule is stored as one and applied next time | v78 #239 ("this should [not] need to be asked in the future"); 508 "GO" capacity replies in FLD mail (`simplification-plan-20261104.md`) |
| The reviewer's load is unmeasured | A weekly baseline by script | "UNKNOWN" in `bookkeeping-evidence-20261107.md`. No `eval` baseline file exists on this Mac. Section 7 gives the first numbers. |

### Delete

Each item goes only after a script confirms nothing has called it for 30 days.

| What | Lines | Evidence |
|---|---|---|
| Monitor-era commands (`watch`, `monitor`, `sessions`, `send`, `connect`, `disconnect`) and the Codex app-server adapter | `providers/codex_app_server.py` 280, plus their share of `cli.py` | "No normal project session needs a monitor. Optional legacy monitors and Codex app-server adapters remain separate compatibility paths." (`docs/architecture.md:38`) |
| Cloudflare routing and the route clean-up kept for it | `transports/cloudflare.py` 285, `transports/cloudflare_tailscale.py` 109, `legacy_routes.py` 143 | "Legacy transport/provider adapters are compatibility paths" (`docs/interaction-contract.md:25`); `src/agent_annotate/transports/__init__.py:19` |
| JSON dual-write and the line-per-event bus files, once FLD's page is on its database | Locks in 8 modules; about 20 modules touch `comments.json` | FLD's bus was 49,990 lines and 15.6 MB, its `comments.json` 6.3 MB; a documented race sits at `src/agent_annotate/sync_server.py:1855` (`simplification-plan-20261104.md`) |
| Per-page ports and per-page share mappings | — | Follows from one service. |
| Skew and coverage tooling | `version_guard.py` 557, `fleet.py` 332 | Follows from one home. Both shrink to a client-version check. |
| One-off migration tools: move out of the package into `scripts/` | `consolidate.py` 641, `plans_backfill.py` 482 | Their own first lines: "Merge several pages of one project into one page"; "Operator-only reconciliation". |

The first two rows remove about 820 lines with no change to normal work. The larger cut comes from one service and a thin client.

## 7. Cognitive load: claim, today, target, measure

First reviewer-side baseline, from this project's page store (115 agent cards kept, 108 answered, 27 Sep–12 Nov). One page only; stage 1 runs it for every page.

| Measure | Today |
|---|---|
| Time from card to answer | Median 34 min; 41 of 108 over an hour; 9 over a day |
| Answers typed in words instead of picking an option | 37 of 108. Median 61 words, 2,928 words in all |
| Picks that matched the recommendation | 41 of 47 where recorded |
| Card length | Median 84 words; 90% at 115 or under |
| Answering days | 13 days; median 8 answers on such a day, most 18 |

Each claim has a number that a script can read from stored data with no tokens.

| Claim | Today | Target | Measured by |
|---|---|---|---|
| One place to look, however many projects, Macs and agents. | 23 pages on two Macs, one link each. | One list, in Orca and at one address. | Count of entry points; page opens that end with no answer (server log). |
| Decisions are found sooner. | 38% of answers take over an hour. | 20% or less. | `latency_s`, already stored with every answer. |
| Options fit, so less typing. | 34% of answers are typed. | 15% or less. | The stored verdict (`select` or `comment`). |
| Agreeing with a recommendation costs one action for all of them. | 41 confirmations given one by one. | One action per round. | Clicks per round (page log). |
| The same kind of question is not asked twice. | Not counted. | Zero. | A script matches each new card against the standing rules. |
| Nothing asks Chang to do setup. | Not counted; #240 was a complaint. | Zero cards whose options need work outside the page, except secrets. | A publish rule flags them. |
| Cards stay short. | Median 84 words. | Median stays under 90; refused above 150. | Counted at publish. |
| Nothing changes under him. | A rule kept by agents. | Zero versions published while a round is open. | The service refuses; the count is in its log. |
| A release needs no approvals for other Macs. | Two per release. | Zero for server and page releases. | Approval cards per release. |
| Agents spend less on the tool. | 6.2–11.0% of coordinator cost. | 3% or less; three commands per round. | `scripts/orch_cost.py`. |

"Exponential" is honest only in one sense. Today his load grows with the number of pages, Macs and agents. With one list and standing rules it grows only with the number of real decisions. The rest of the table is step changes.

## 8. Staged path

The simplification plan's stages 0–5 are built. These are new stages. Its optional stage 6 (the server owns writes) is covered by stages 2 and 4 here.

| Stage | What | Size | Proof |
|---|---|---|---|
| 1 | **Needs-you list and reviewer baseline.** A script computes section 7's baseline for every page on this Mac, weekly. The service gains one read-only list of open decisions across pages. An Orca plug-in shows the count in the status bar and the list in a side panel. | One week. Read-only; no stored data changes. Undo: switch the plug-in off. Needs Chang's one-time approval of the plug-in in Orca. | The status-bar count equals the sum of the pages' own counts in 20 spot checks. A row opens the right card. The baseline file exists for all 19 pages. |
| 2 | **One service on this Mac.** One process and one port for all pages. A script lists what nothing has called in 30 days, and those compatibility paths go. | 1–2 weeks. | 17 processes become 1. `scripts/store_rehearsal.py` shows every page unchanged. A release restarts one thing. |
| 3 | **Card rules and standing rules.** Publish refuses setup asks and over-long cards. "Accept all recommended" is one action. An answer marked as a rule is applied next time instead of asked. | 1–2 weeks. | Typed answers 34% → 15%. Repeat questions zero. |
| 4 | **One home.** M5 Max and M1 Max 16 become thin clients; their pages move home. | 2 weeks, with Chang's approval per Mac. | No page servers off this Mac. A page release touches one Mac. |
| 5 | **Owners and gates from Orca and Beads.** Owners follow Orca's live agents. An Orca or Beads gate waiting on the person points at a card. | 1–2 weeks. | Zero rounds waiting with no live owner. One place a pending decision can sit. |
| 6 | **Retire JSON and the bus files**, after FLD's page moves to its database. | 1 week. | Locks in 8 modules become 0. |
| 7 | **Agents post items; the service builds the page. Windmill starts from service events.** | 2–3 weeks. | Three commands per round. Annotate share 3% or less. |

Stage 1 is first because it is the smallest step the reviewer can feel, it cannot damage anything, and it tests the one unknown in the recommended shape: whether an Orca plug-in can do this job.

## 9. Open points and what was not checked

- Whether an Orca plug-in worker may open network connections and run commands freely. The docs call it a trusted Node worker and stage 1 depends on it. Prove it on day one.
- The Windmill workspace already has scripts named `board_checks`, `sweep_trigger` and `dispatch_runner`. They were not read. Stage 7 must start from them.
- How often Orca decision gates and Beads human gates are used.
- Whether any page still uses Cloudflare routing. The 30-day call check in stage 2 covers it.
- The reviewer baseline covers one page. Click counts and reading time are not stored anywhere yet.
- An earlier `annotate eval` run reported that most cards went unanswered before recommendations became standard. It was not re-run.
- If M1 Max is off, agents on other Macs queue their posts until it is back. That is the cost of one home.
