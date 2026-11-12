# agent-annotate from first principles

Chang asked on 2026-11-12: if we started from scratch, as an Orca plug-in and/or a standalone tool, what would agent-annotate look like? Three goals:

- agents on several Macs and several coding agents take part (at least Orca, Claude Code, Codex CLI, Beads, Windmill);
- building with AI is as seamless and effective as possible;
- the thinking load needed to build world-class work drops sharply.

Research and design only. Nothing live was changed. Numbers without a named source were measured on M1 Max on 11–12 Nov 2026.

**Revision 2, 12 Nov.** Chang answered round 1 in the session: shape and home are settled, the first stage is wider, and he added targets and the coordinator question. Sections 6, 7 and 9 are new; 1, 2, 10 and 11 are rewritten; the rest has small edits.

## 1. Answer

1. **Purpose.** agent-annotate is the one place where the reviewer's decisions enter the build, and the mechanism that carries each decision to the right agent once and shows that it was acted on. It also shows him the state of the work, read from the other tools. Nothing else.
2. **Shape (settled).** A small standalone service that owns the records, with three thin faces: a command for agents, a web page for any browser or phone, and an Orca plug-in that shows the reviewer what needs him (section 4).
3. **Home (settled).** One home for all pages on M1 Max, the central brain. Other Macs and every kind of agent use the same four commands over the tailnet (section 5).
4. **Home page.** One page for every project: what needs him, the workers on each Mac and what they are doing, the board, the cost. An analytics tab tracks his targets. No agent writes any of it (section 6).
5. **Thin coordinator.** A coordinator is a memory, a clerk and a judge. Memory moves to the stores, the clerk becomes a Windmill flow with no tokens, and the judge is a model called per event. No coordinator at all only where a script can pass or fail the work, and only after a shadow trial (section 7).
6. **Targets.** His load at least 50% lower, tokens at most marginally higher per finished item, quality and progress no worse and aimed higher. Each has a number a script can read (section 9).
7. **Today's product.** Keep the round, the card, the per-page database and the scripts. Change 17 page servers into one and 45 commands into four. Delete the compatibility paths (section 8).
8. **First stage.** Two weeks, read-only, with the home page visible after week one (section 10).

## 2. Already decided, measured or built

Not reopened here. The design builds on these.

**Decided by Chang** (review page version and card number, unless stated):

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
| Shape: a standalone service with an Orca face. Home: M1 Max, "the central brain". First: the needs-you list, widened to one page for all projects, worker counts per Mac and an analytics tab. | In session, 12 Nov |
| Targets: his load at least 50% lower than today; tokens only marginally higher, ideally lower for the progress made; quality at least today's, better as a high priority. A thin or absent coordinator must not put a project's progress at risk. | In session, 12 Nov |

**Measured:**

| What | Result | Source |
|---|---|---|
| Baseline, 30 Oct–4 Nov | FLD coordinator $1,204 in 84 h, $52 per round, median context 509k. 48–82% of cost was re-reading context. Waiting on workers and mail was 42%. Annotate share 6.1% (FLD), 17.4% (this project). | `docs/validation/simplification-plan-20261104.md` |
| After stages 0–3, 7–10 Nov | FLD $94.93 in 71.7 h, $8.63 per round, median context 138k. Annotate share 6.2% (FLD) and 4.7–11.0% (this project's four sessions); goal 3%. Shell reads and search are now the largest cost, 40–51%. | `shared/agents/cost-3day-20261110/` |
| The same FLD coordinator, by turn | 149 turns: 96 started by an Orca message, 26 by a background task ending, 27 typed by Chang. 64 workers started, 11 rounds delivered. 68% of cost was re-reading its own context. | `shared/agents/cost-3day-20261110/fld-029a.json` |
| Bookkeeping, 31 Oct–7 Nov | No evidence supports another status or polling feature. The reviewer's side (clicks, time, reminders) is unknown. | `shared/agents/bookkeeping-evidence-20261107.md` |
| Mail routing replay | 9,175 coordinator messages caused 3,181 turns; 1,061 under quiet-wait rules; 708–1,011 with the router. | FLD usage audit, `router-replay.md` |
| Board sweep model trial | Opus 5.5: 85% correct, $1.68 per sweep. Timed sweeps were then rejected (#241). | FLD usage audit, `model-trial-score.md` |
| Agents per Mac, one moment on 12 Nov | M1 Max: 74 workspaces, 19 agents, 5 working. M5 Max: 34, 6, 5 working. M1 Max 16: 25, 2, none working. All three read from M1 Max. | `orca worktree ps --json`, plus `--environment M5Max` and `M1Max16` |

**Built in agent-annotate** (`CHANGELOG.md:1-58`): one-line receipts, batch resolve, cost meter (2.28.3). Ask fences, one publish command, self-numbering, `--section`, the per-page database behind `store.py`, `rollout.py`, `sweep.py` (2.29.0). Pages moved to the database, FLD held on JSON (2.30.0). `annotate board`, with the round as trigger and judgement in a separate worker (2.31.0, 2.31.1).

**Built in Windmill** (workspace listing on 12 Nov; summaries, descriptions and schedules were read, not the code):

| What | Path | State |
|---|---|---|
| Windmill starts a stage in an Orca terminal and resumes when it ends | `f/build/dispatch` | In use every few minutes by the test and sweep flows |
| One change tested with no tokens; one agent only for a failure never seen before | `f/test/change` | Running on a schedule |
| One item from spec to sign-off: tests first, build, verify, review by a second agent, Chang's sign-off | `f/build/item` | Built 25 Sep. One 36-second run in the job history (19 Oct) |
| An inbox for Windmill approvals, "Needs Chang" | app `f/inbox/needs_chang` | Built 25 Sep. The one suspended job found on 12 Nov was a machine wait |
| Board checks by script | `f/sweep/board_checks` | Hourly, FLD only. The timed AI sweep trigger has no schedule |
| Daily usage report with no model | `f/usage/daily_report` | Daily, FLD only |
| Failure notices with no AI | `f/ops/job_failed_notice` | Every ten minutes |

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

1. **Show.** Put a decision in front of the reviewer with its evidence, a recommendation and what each choice causes. Show the state of the work as well: what is running where. That part is read from Orca, Beads and the logs, never written by an agent.
2. **Capture.** Record the answer once, durably, with who and when.
3. **Deliver and close.** Wake the right agent once. Show the reviewer that the answer was acted on, with proof.

Not its jobs: running agents (Orca), tracking work (Beads), running routines (Windmill), storing documents (the repo). Where today's product does one of those, it should hand the job back.

### Who must do what

| | Must do | Must never have to do |
|---|---|---|
| Reviewer | Read a short card, choose or type, press Send. Leave a free note when something is wrong. | Find where the question is. Remember to come back. Run setup steps. Answer the same kind of question twice. Ask an agent what is going on. |
| Agents | Write the card: context, recommendation, consequences. Read answers once. Prove what was done. | Number, route, track owners, restart servers, remember to run checks, re-read stored state, write status. |
| Scripts | Everything in the two "never" cells above. | Judge. |

Every point below is tested against this table.

## 4. Target design: a standalone service with an Orca face

### Parts

```text
reviewer ── web: home page and project pages ──┐
reviewer ── Orca plug-in: count and list ──────┤
                                               ├── one service ── one database per page
agents ──── command, four verbs ───────────────┤        │
Windmill ── same HTTP API ─────────────────────┘        └── outbox ── Orca ── owner's terminal, any Mac
```

1. **The service.** One process, one port, one share-link root. It owns every page's database, versions and rounds, and an outbox of wake-ups. It serves the pages. It is today's Python package, reduced.
2. **Agent face.** The `annotate` command as a thin client of the service, plus a skill inside today's 700-token budget. Four verbs: `ask` (post cards or an update), `read` (answers addressed to me, once), `done` (close items with proof), `status`. Identity comes from the environment (Orca terminal handle, session id) and is never typed.
3. **Reviewer faces.** The home page lists every project (section 6). A project page stays the place where a question sits beside its evidence. The Orca plug-in adds presence: a status-bar count, a side panel of what needs him across projects, one click to the card. It stores nothing.
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
| Four unconnected ways to ask the person. | Annotate cards; `orca orchestration gate-create` ("Create a decision gate blocking a task"); `bd gate` (type `human`); Windmill's "Needs Chang" inbox (app `f/inbox/needs_chang`). Use on 12 Nov: no gates on this project's board, no Windmill approval waiting; Orca gates can be listed only from inside a Run and were not counted. |

### What the Orca plug-in does

- **Status bar.** "3 need you", coloured when above zero. Pressing it opens the list.
- **Side panel.** The home page's rows: open decisions grouped by project, oldest first. A row opens the page at that card. Answering stays on the page beside the evidence, as today's rule requires.
- **Worker.** Reads the service's one read-only list. Later it maps Orca's agent and workspace events to page owners, so agents stop claiming.
- **Fallback.** If a panel cannot be fed live data, the status-bar item opens the home page in an Orca browser tab. Stage 1 does not depend on the unknown.
- **Size.** A few hundred lines and no stored state. If Orca is closed or its plug-in system changes, pages, agents and delivery keep working.

## 5. Several Macs, several agents

### Today

| Mac | Release | Pages | Notes |
|---|---|---|---|
| M1 Max | 2.31.1 | 19 registered; 17 server processes on ports 8800–8819 | FLD's main page is still on JSON |
| M5 Max | 2.29.0 | 4, plus one page on 2.28.2 and one unregistered server on 2.27.6 | Two releases behind |
| M1 Max 16 | 2.29.0 | None | Launcher not on PATH for non-interactive shells |

Each release is installed on each Mac, needs Chang's approval for each other Mac, and restarts every page (`docs/routine-scripts.md:21`, `:27`). `src/agent_annotate/version_guard.py` (557 lines) exists only to detect differences among the launcher, skills, plug-in and pages.

### Target

One home, on M1 Max (settled, 12 Nov). M1 Max already hosts this project's Beads database (`bd where`), Windmill (`docs/validation/stages-3-5-specs-20261104.md`) and the Orca pairings to both other Macs. Other Macs install only the thin client and reach the home over the tailnet. A client that cannot reach home keeps a small outbox and retries; a read fails fast with one line.

| Participant | How it takes part | Exists today | Missing |
|---|---|---|---|
| Orca | Carries each wake-up to the owner's terminal on any Mac. Hosts the plug-in face. Reports every agent's state on every Mac. | Delivery through Orca (`src/agent_annotate/delivery.py:231`); paired environments M5Max and M1Max16. | The plug-in; owners taken from Orca events. |
| Claude Code | Four verbs through the command; the skill; one session-start line. | Yes. The skill is 32 lines. | Nothing. Fewer commands. |
| Codex CLI | Same command and skill. Rounds arrive through Orca, so no hook is required. | Yes (`plugins/codex/`). | Remove any reliance on hooks; new Codex sessions stop to have hooks reviewed. |
| Beads | Work items stay in Beads. Cards and findings link to beads; the page shows counts. A human gate in Beads points at a card. | Links accept bead ids (`src/agent_annotate/project_state.py:115`); `annotate board`. | The gate-to-card link. An answer that wakes whoever holds the bead. |
| Windmill | Runs routines with no tokens. Runs the conductor (section 7). Posts results as proof through the same API. Starts from service events. | `wm-test`, `scripts/rollout.py`, `scripts/sweep.py`; the bridge `f/build/dispatch`. | An event trigger; a service identity. |

Workers do not talk to the service. They report through Orca, which is already the rule. Only page owners and scripts are clients, so each project has a handful of participants however many workers it runs.

## 6. The home page: every project, every Mac

Chang, 12 Nov: one page for all projects, an analytics tab, and how many workers each Mac has on each project, working or idle.

One address on M1 Max, served by the service, the same on a phone. The Orca side panel shows the same rows. Layout, with made-up numbers:

```text
Project          Needs you        M1 Max              M5 Max      M1 Max 16   Board                Week
FLD              3 · oldest 2 h   2 working, 1 idle   3 working   —           4 ready, 2 blocked   12 done
agent-annotate   0                1 working           —           —           2 ready              5 done
Rebex            1 · oldest 20 m  1 waiting           1 stuck     —           1 ready              3 done
```

### Where each column comes from

| Column | Read by script from | Exists today |
|---|---|---|
| Needs you: count, age of the oldest | Each page's database | Yes: the count printed at session start (`src/agent_annotate/hooks/session_start.py:41`) |
| Workers per Mac: working, waiting on its own workers, idle | Orca, one call for M1 Max and one for each paired Mac | Yes: see the 12 Nov count in section 2. Orca gives each agent's state, when it began, its last output time and whether it was interrupted |
| Stuck: "working" with no output for 15 minutes | The same Orca fields | Not today. A coordinator finds a silent stall only by checking |
| Which project a workspace belongs to | The page's own rule: the folder's Git origin | Yes: `src/agent_annotate/workspace.py:19` |
| Board: ready, in progress, blocked, done this week | Beads | Yes: `annotate board` |
| Cost this week | Session logs | Partly: `scripts/orch_cost.py` per session; a daily report for FLD only |
| Waiting elsewhere: Windmill approvals, Orca gates, Beads gates | Their own lists | Shown as a count with a link until stage 6 turns them into cards |

No agent writes anything on this page. A coordinator stops producing status, and Chang stops asking for it.

### Analytics tab

One group per target in section 9: his load, tokens, quality, progress. Weekly, by script, with no tokens, for each project and for all together. The first week measured is kept as the baseline and every later week is shown against it.

## 7. A thin coordinator

Chang, 12 Nov: help coordinators run better; ideally need none, or only a thin one; never at the cost of a project's progress.

### What a coordinator costs today

FLD's coordinator, 7–10 Nov, 72 hours, $94.93 (`shared/agents/cost-3day-20261110/fld-029a.json`). The last three rows are two different cuts of the same cost and overlap.

| | |
|---|---|
| Turns | 149: 96 started by an Orca message, 26 by a background task ending, 27 by Chang typing |
| Output | 64 workers started and 11 rounds delivered to Chang: about 14 turns for each round |
| Re-reading its own context | 68% of cost. Median context 138k across 1,634 calls; 13 compactions |
| Reading and searching in the shell | 42% of cost |
| Clerk work | 37% of cost: waiting and mail 9.7%, release and rollout 5.3%, Beads 5.2%, Orca messages 5.1%, annotate 5.0%, Git 3.9%, dispatch 2.5% |

### A coordinator is three things

| Part | What it does | Where it should live |
|---|---|---|
| Memory | Holds the plan, what was decided, who is doing what. | The stores: Beads for work and order, the page for decisions and standing rules, the repo for designs. A session is the dearest place to remember, because every call re-reads it. |
| Clerk | Picks the next ready item, picks a Mac and a model, starts and watches workers, nudges stalls, runs checks, closes items, rolls out, relays answers. | A Windmill flow and scripts. No tokens. |
| Judge | Splits a goal into items, each with its acceptance check. Judges a result when a check cannot. Decides what needs Chang and writes the card. | A model, called for one event with that event's packet, not kept running. |

### Target

```text
Chang's goal ── planner (model, once per goal) ── items, each with its acceptance check
                                                    │
          board (Beads) ── conductor (Windmill flow, no tokens) ── Orca starts a worker on a free Mac
                                                    │                          │
                                          checks (scripts) ◄── result packet ──┘
                                                    │
                  checks pass, low risk ─────────── close with proof
                  checks fail, unclear or high risk ─ judge (model, fresh, one packet)
                  needs Chang ───────────────────── card; his answer returns to the item and the flow resumes
```

The conductor is not part of agent-annotate. It is a Windmill flow over Beads and Orca. agent-annotate supplies what it needs from the reviewer's side:

1. **Answers go to the work.** A card is tied to its item. The answer wakes the flow or whoever holds that item, so no session has to stay alive to relay it. Today an answer goes to the page owner's terminal (`src/agent_annotate/delivery.py:231`).
2. **Standing rules at the start.** Every planner, judge and worker gets the rules and decisions that apply to its project in one short read. Workers stop breaking known preferences and nobody re-briefs them.
3. **Result packets.** A worker's report carries what changed, which checks ran and where the proof is. The judge reads the packet, not the terminal. This aims at the 42% spent on reading and searching.
4. **Held questions.** A question that blocks nothing waits for the next round; one that blocks work goes at once.
5. **Status from the stores.** The home page (section 6).
6. **Events.** Round submitted, card answered, item closed: the flow starts from these.

### Three levels, chosen per kind of work

| Level | What runs | For |
|---|---|---|
| Today | One coordinator session is memory, clerk and judge. | — |
| Thin | The flow is the clerk. The coordinator session stays and is woken only for a judgment. | The target for every project |
| None | No standing session. The flow calls a planner or a judge for one event, and that call ends. | Only work a script can pass or fail: test fixes, routine changes, rollouts. Only after the thin level's numbers hold |

### What already exists

Most of the parts are in section 2's Windmill table: the bridge, token-free testing, board checks, failure notices. Skills `bead-fleet` and `bead-loop` already have workers take ready items themselves. `f/build/item` is the whole loop for one item, and it is not in use: one 36-second run on record. Why it did not become the normal path was not established. That must be answered before anything is built on it.

### Guardrails: progress is never at risk

1. **Shadow first.** For one week the flow only records what it would have done, beside the live coordinator. A kind of work moves to it when it matched the coordinator on 95% of events (proposed) and no miss would have lost work.
2. **One project and one kind of work at a time**, lowest risk first.
3. **A coordinator can be started at any moment** from the stores, because memory no longer lives in a session. That is the way back.
4. **Stalls are caught by script.** A worker with no output for 15 minutes is nudged once, then goes to the judge.
5. **Stop rule.** If a week shows fewer items finished or more reopened than the baseline, that kind of work returns to the level before.

### Expected effect

Estimates, not measurements.

- **Coordinator cost.** Clerk work is 37% of it and moves to scripts. Judging from a packet instead of a 138k context removes most of the 68% spent re-reading. Half of today's cost per round or less is a fair expectation.
- **Whole-project tokens.** What share of a project's tokens its coordinator uses, workers included, was not measured. Stage 1 adds that number. If workers dominate, the larger saving is fewer rework rounds, which standing rules, checks written first and result packets address.
- **Quality.** Checks written before the work, run by script every time, and a second agent judging intent are stricter than one busy coordinator's reading. The stop rule covers the case where that turns out wrong.

## 8. Today's product: keep, change, delete

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
| Answers go to a session | Answers go to the work item and wake whoever holds it | `delivery.py:231`; section 7 |
| Four ways to ask the person | One record: the card. An Orca gate, a Beads gate or a Windmill approval waiting on him points to it and closes when it is answered. | `orca orchestration gate-create --help`; `bd gate --help`; app `f/inbox/needs_chang` |
| The same kind of question asked again | Standing rules: an answer that is really a rule is stored as one and applied next time | v78 #239 ("this should [not] need to be asked in the future"); 508 "GO" capacity replies in FLD mail (`simplification-plan-20261104.md`) |
| The reviewer's load is unmeasured | A weekly baseline by script | "UNKNOWN" in `bookkeeping-evidence-20261107.md`. No `eval` baseline file exists on this Mac. Section 9 gives the first numbers. |

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

## 9. Targets and measures

### Chang's targets, 12 Nov

| Target | Number | Counted by script from |
|---|---|---|
| His load | At least 50% lower than the baseline week. Three counts, each must halve: decisions put to him per finished item; words he types per week, in answers and in messages to agents; places he must look. | Page databases, Beads, session logs. Places today: 23 page links, plus Windmill's inbox and Orca. |
| Tokens | At most 5% more per finished item than the baseline week (proposed reading of "marginally"); aim lower. | Session logs and Beads, all sessions of a project, on every Mac. |
| Quality | No worse than the baseline week; aim better. Items reopened; results sent back for rework; failures never seen before per change; recommendations he overruled. | Beads; `f/test/change` receipts; the stored option against the recommendation (6 of 47 overruled so far). |
| Progress | No worse than the baseline week. | Items finished with proof per week, from Beads. |

What is not stored anywhere yet: his reading time and his clicks. Finished items per decision needs the Beads join, which stage 1 adds.

### Where the 50% comes from

| Cut | Today | After |
|---|---|---|
| Agreeing with recommendations | 41 of 47 picks follow the recommendation, given one card at a time | One action for the round |
| Typing because no option fits | 37 of 108 answers, 2,928 words | 15% of answers or fewer |
| The same kind of question again | Not counted; 508 "GO" capacity replies in FLD mail | A standing rule answers it |
| Finding what needs him | 23 page links on two Macs | One list |
| Asking what is going on | 27 typed turns to FLD's coordinator in three days; how many were status questions was not counted | He reads the home page |
| Approving releases for other Macs | Two approvals per release | None for page and server releases |
| Questions about mechanics | Capacity, hand-overs, restarts reach him as cards | The flow handles them by rule |

### First baseline, his side

From this project's page store (115 agent cards kept, 108 answered, 27 Sep–12 Nov). One page only; stage 1 runs it for every page.

| Measure | Today |
|---|---|
| Time from card to answer | Median 34 min; 41 of 108 over an hour; 9 over a day |
| Answers typed in words instead of picking an option | 37 of 108. Median 61 words, 2,928 words in all |
| Picks that matched the recommendation | 41 of 47 where recorded |
| Card length | Median 84 words; 90% at 115 or under |
| Answering days | 13 days; median 8 answers on such a day, most 18 |

### Claims, each with a number

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
| A coordinator takes fewer turns per round. | About 14 on FLD. | Half or fewer. | Session logs. |

"Exponential" is honest only in one sense. Today his load grows with the number of pages, Macs and agents. With one list and standing rules it grows only with the number of real decisions. The rest of the table is step changes.

## 10. Staged path

The simplification plan's stages 0–5 are built. These are new stages. Its optional stage 6 (the server owns writes) is covered by stages 4 and 5 here. The order follows his targets: what lowers his load comes before the plumbing.

| Stage | What | Size | Proof |
|---|---|---|---|
| 1 | **Home page and baseline.** Every project on one page on M1 Max: needs you, workers per Mac, board counts. An Orca status-bar count and side panel. Then the analytics tab with a baseline week for the four targets. | Two weeks: the page and the Orca count in week one, analytics in week two. Read-only; no stored data changes. Undo: switch it off. Needs Chang's one-time approval of the plug-in in Orca. | The count equals the sum of the pages' own counts in 20 spot checks. Worker counts equal Orca's on all three Macs in 20 spot checks. A row opens the right card. The baseline exists for every page and project. |
| 2 | **Card rules and standing rules.** Publish refuses setup asks and over-long cards. "Accept all recommended" is one action. An answer marked as a rule is applied next time instead of asked. | 1–2 weeks. | Typed answers 34% → 15%. Repeat questions zero. |
| 3 | **Thin coordinator on one project and one kind of work.** One week in shadow, then live. Answers tied to the item; result packets as a file a worker writes. | Shadow one week; live 1–2 weeks. | Shadow matched on 95% of events. Live: turns per round and cost per finished item fall; items finished and reopened are no worse. |
| 4 | **One service on M1 Max.** One process and one port for all pages. A script lists what nothing has called in 30 days, and those compatibility paths go. | 1–2 weeks. | 17 processes become 1. `scripts/store_rehearsal.py` shows every page unchanged. A release restarts one thing. |
| 5 | **One home.** M5 Max and M1 Max 16 become thin clients; their pages move to M1 Max. | 2 weeks, with Chang's approval per Mac. | No page servers off M1 Max. A page release touches one Mac. |
| 6 | **One place a decision can wait.** Owners follow Orca's live agents. An Orca gate, a Beads gate or a Windmill approval waiting on the person becomes a card. | 1–2 weeks. | Zero rounds waiting with no live owner. The home page's "waiting elsewhere" count is zero. |
| 7 | **Retire JSON and the bus files**, after FLD's page moves to its database. | 1 week. | Locks in 8 modules become 0. |
| 8 | **Agents post items; the service builds the page. Windmill starts from service events.** | 2–3 weeks. | Three commands per round. Annotate share 3% or less. |
| 9 | **No coordinator for work a script can check**, one kind of work at a time, where stage 3's numbers held for a month. | Per kind of work. | The stop rule in section 7 never fired for it. |

Stage 1 is first because it is the smallest step the reviewer can feel, it cannot damage anything, it gives every later stage its baseline, and it tests the one unknown in the recommended shape: whether an Orca plug-in can do this job.

## 11. Open points and what was not checked

- Why the September Windmill build flow (`f/build/item`) and its inbox are not in use. Section 7 is the same idea, so the reason matters. Asked of Chang in round 2.
- Whether an Orca plug-in worker may open network connections and run commands freely. The docs call it a trusted Node worker. Prove it on day one; the fallback in section 4 covers a no.
- Orca reports two status fields for an agent, and in the 12 Nov sample they did not always agree. Stage 1 must pick by test which one means "working".
- What share of a project's tokens its coordinator uses. Cost for sessions on the other Macs needs the cost script to run there, with Chang's yes per Mac.
- The Windmill flows were read as summaries, descriptions and schedules. Their code was not read.
- How often Orca decision gates are used.
- Whether any page still uses Cloudflare routing. The 30-day call check in stage 4 covers it.
- The reviewer baseline covers one page. Click counts and reading time are not stored anywhere yet.
- An earlier `annotate eval` run reported that most cards went unanswered before recommendations became standard. It was not re-run.
- If M1 Max is off, agents on other Macs queue their posts until it is back. That is the cost of one home.
- The 95% shadow match, the 15-minute stall limit and the 5% token ceiling are proposals, not measurements.
