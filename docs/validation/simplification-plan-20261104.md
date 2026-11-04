# Make agent-annotate light, and let tools do the bookkeeping: simplification plan

## One-page summary for Chang

**Goal one: annotate must be a light helper, not a burden.** Each small action gets a fixed overhead budget: reading a round, answering a card, publishing a small update. A test fails the build when an action goes over its budget. Today every action is over budget.

**What annotate costs today, from real sessions:**

| One small action | Budget | Today |
|---|---|---|
| Read one round of your answers | 1 command | 2 commands (up to 14 for FLD) |
| Mark one card answered | no extra command (one per round) | 1 command per card; 1 in 7 fail in FLD |
| Publish one small update | 1 command, 0 retries | 4–7 commands; about half the attempts print an error first |
| A whole small round (3 answers) | 3 commands, about 15¢ | **9–12 commands, about 80¢–$1.80** |
| Annotate's share of the coordinating cost | 3% or less | **6% (FLD), 16–17% (Agent Annotate, Multi-Mac)** |

**Why "a few small things" cost multiples more:** a 3-answer round carries about 150 tokens of your answers. The 9–12 bookkeeping commands around it each re-read the whole coordinating conversation (365k–509k tokens). That's 3–6 million tokens processed to file three answers. **Every command is that expensive, so the budget counts commands first.**

**What annotate makes agents do that it should do itself:**
- Pick card numbers and anchors by hand. FLD's coordinator wrote its own renumbering workaround (run 46 times), and card numbers drifted past #20,000.
- Write card JSON (21,000 tokens in FLD).
- Retry after rule errors ("numbers must be strictly increasing", "number already used", "cite an evidence anchor").
- Resolve cards one at a time.
- Read long outputs: every resolve receipt repeats the page's private share link (56–84% of the receipt), inbox output is 12–16% padding spaces, and publish prints banners and ID lists.

**The rest of the cost is how coordinating sessions work** (measured Oct 30 – Nov 4, at Claude Code's list price; your plan may bill differently):
- FLD: $1,204 over 84 hours, $52 per round you submitted. Agent Annotate: $205, $16 per round.
- 48–82% of the cost is re-reading a conversation of 325k–509k tokens on every step.
- Half of FLD's cost came from wake-ups for progress notes (1,839 notes, against 620 finished-work reports).

**The plan, in six stages (26–39 worker-days):**

| Stage | What changes | Expected result | Days |
|---|---|---|---:|
| 0. Meter and budget test | One script measures any session; a test fails when an annotate action is over budget | Every claim provable; "light" stays guarded | 1–2 |
| **1. Make annotate light** | One-line receipts (no links, banners or ID lists), compact inbox, one command to resolve a whole round, shorter skill | Reading and resolving under budget; round 9–12 → 5–7 commands | 2–3 |
| 2. Lighter coordination | Progress notes stop waking the session; it restarts fresh at a size limit with state in files | **55–75% less coordinating cost** (FLD $14 → $4–6 an hour) | 4–6 |
| 3. Annotate does its own bookkeeping | Software picks card numbers and versions; cards written as plain text; update one section at a time | Publish and ask under budget; a round takes 3 commands; numbering errors gone | 5–8 |
| 4. Scripts for routine jobs | Release and three-Mac rollout as one script; sweeps and tests on a schedule, with no AI | Rollout takes 2 steps per Mac; sweeps cost no AI | 4–5 |
| 5. Database | Each Mac keeps its page records in one SQLite file instead of many JSON and lock files | Page and cards saved in one step; no lost updates; about 0% direct token saving | 10–15 |

**Storage answer:** **SQLite, one file per Mac, not Postgres.** Each Mac hosts its own pages, so no shared server is needed. A database makes the one-line answers trustworthy but doesn't cut tokens itself, so it comes after the stages that do.

**Start with Stages 0 and 1:** they are small, change no page data and are easy to undo. Stage 2 follows; it saves the most money.

---

## Goal 1: an overhead budget for every annotate action

A **command** is one tool call an agent makes for annotate's sake. Each one costs a full re-read of the agent's conversation, $0.11–0.12 at today's 365k–509k contexts and about $0.05 at 150k. **Tokens** count only what the action writes and reads; the content itself (your answers, the page text the agent means to write) is excluded. "Today" comes from the three coordinator transcripts (FLD = `145f492c`, AA = `2ac5a669`), using `actions.py`, plus the first evaluation's model-free fixtures.

| Action | Budget | Today, measured | Over by | Stage that brings it under |
|---|---|---|---|---|
| **Read one round** (N answers) | 1 command; ≤ 40 + 60·N tokens; 0 raw-store reads | Median **2 commands** (FLD p90 **14**); **453 (AA) / 723 (FLD) tokens**; the fixture's 3-answer inbox is 184 and FLD's 3-answer replay is 329. Output is 12–16% padding spaces; FLD inbox printed 104 publish-event lines that aren't feedback; 115 raw-store reads (`comments.json`, `current.html`) in the window. Cost $0.35 (FLD) / $1.12 (AA, rounds arrive after idle) | 2× commands; 2–3× tokens | **1** (compact inbox, `--worklist`) |
| **Answer (resolve) one card** | 0 extra commands, as one batch command per round; ≤ 15 tokens per card in the receipt | **1 command per card** (FLD 152 for 152; AA 47 for 47); **104–114 tokens** per receipt, **56–84% of it the page's share link**; failed: **21/152 (14%) FLD, 4/47 (9%) AA**, "number is ambiguous; use its comment id" | N× commands; 7× tokens | **1** (batch resolve, short receipt, handles from the worklist) |
| **Ask one question** | Question + options + ≤ 10 tokens of markup; no number, anchor or JSON | Card JSON median **186–218 tokens per publish**, FLD **21,423** in total. Rules the agent must satisfy: strictly increasing numbers, a matching `d:qN` anchor, at least one evidence anchor | ~20× markup | **3** (software numbers and anchors; plain-text cards) |
| **Publish one small update** (≤ 1 section, ≤ 3 cards) | 1 command; agent writes only the changed section; receipt ≤ 25 tokens; 0 retries | **4.3 (AA) / 7.3 (FLD) commands per version drafted**; **1,739 / 2,707 tokens per version** beyond nothing-changed; **49% (AA) / 64% (FLD)** of publish attempts printed an ERROR. FLD wrote its own `pubfix` script to renumber and repost (46 runs). Publish output repeats an owner banner, an unrelated "Invocation" line and a JSON list of up to 19 IDs | 4–7× commands | **1** (receipt) + **3** (numbers, versions, section drafts) |
| **A whole small round** (read 3 answers, resolve them, publish the result) | **3 commands; ≤ 1,000 tokens; ≈ $0.15 at 150k context** | Fixture: 5 commands / 380 tokens. **Live: ≈ 9–12 commands, $0.80–1.80**; 3–6 million tokens re-read to file ~150 tokens of answers | 3–4× commands | 1 → 5–7 commands; 3 → 3 commands |
| **Session start** | ≤ 700 tokens; the page reference loads only when needed | Skill 657 + page reference 1,316 = **1,973 tokens** when loaded | 3× | **1** (trim; reference on demand) |
| **Annotate's share of coordinator cost** | ≤ 3% | **FLD 6.1% ($74), AA 17.4% ($36), Multi-Mac 16.2% ($8)** | 2–6× | 1 + 3; the share also drops as Stage 2 shrinks contexts |

### What the annotate side imposes on orchestration

Counted from the same transcripts: annotate commands, page drafting and card JSON, and raw-store reads. Each is costed at the share of the model step that issued it.

| | FLD | Agent Annotate | Multi-Mac |
|---|---:|---:|---:|
| Annotate-side commands | 940 | 266 | 45 |
| — writing page drafts and cards (incl. throwaway build scripts) | 504 | 68 | 14 |
| — publish / read / resolve / other / raw-store reads | 55 / 112 / 152 / 27 / 90 | 53 / 56 / 47 / 19 / 23 | 8 / 11 / 5 / 5 / 2 |
| Page versions drafted | 92 | 38 | — |
| Tokens added to the conversation | 331k | 89k | 16k |
| — of which card JSON | 21.4k | 6.6k | 1.8k |
| — of which annotate output | 166k | 48k | 7k |
| Longest single output; 90th percentile | 6,015; 508 tokens | 2,910; 685 | 2,130; 360 |
| Attempts that printed an error | 99 ($6.77) | 36 ($3.08) | 4 ($0.48) |
| **Cost; share of the coordinator's cost** | **$73.88; 6.1%** | **$35.78; 17.4%** | **$8.44; 16.2%** |

The causes differ by session. Drafting dominates in FLD: 504 commands, $33, most of them patching the previous version's markdown with string replacement. Reading dominates in Agent Annotate: $21 for 56 inbox reads, because rounds arrive after idle and each read pays a cache rewrite. Errors are spread over numbering, evidence-anchor rules and the browser check (now fixed).

### How the budget is kept

Stage 0 adds `scripts/bench.py --budget`, using the model-free fixtures already used by the first evaluation (ports 18700–18799, copied pages). For each action it asserts the command count, printed tokens (o200k proxy) and zero retries, and it fails CI when an action goes over. The live meter (`orch_cost.py`) reports annotate's share of coordinator cost weekly. Any new annotate feature must state its effect on these numbers before it ships.

## 1. Token evidence

### Method

These are copies of the three transcripts named in the brief, taken 2026-11-04 05:27 UTC. They cover the main thread only, which is the coordinating session itself. Subagents ran separately: the Multi-Mac session's subagents add another $31. Usage is de-duplicated by API message id (8,510 / 968 / 291 calls). Cost applies each session's own Claude Code `costUSD` rate to weighted tokens (input 1, output 5, cache read 0.1, cache write 1.25). The resulting prices are $2.34 per million weighted tokens for FLD and $2.93 for the other two; the transcripts do not explain the difference.

Tool calls are classified by command text: for example, `orca-quiet-wait`, `drain_mail.py` and `orchestration check` count as *wait/mail*. Each API call's cost is attributed to the tools that call issued, because that is the price of deciding to do it. "Context added" estimates the tokens each result or message puts into the conversation (characters/4; images by pixel size), scaled to the measured growth (factor 1.23–1.30). Aggregates are in [the receipt](simplification-plan-20261104.json). Scripts and copies are in `/tmp/aa-simplify-20261104/`.

### The three sessions

| | FLD `145f492c` | Agent Annotate `2ac5a669` | Multi-Mac `fd956ed9` |
|---|---:|---:|---:|
| Span (UTC) | Oct 31 17:03 – Nov 4 05:27 | Oct 31 18:38 – Nov 4 05:27 | Oct 30 15:10 – Oct 31 05:06 |
| Wall / active hours (gaps < 30 min) | 84.4 / 56.0 | 82.8 / 12.7 | 13.9 / 3.7 |
| API calls; median calls per active hour | 8,510; 133 | 968; 13 | 291; 29 |
| Context per call: median / p90 / max | 509k / 858k / 967k | 365k / 773k / 915k | 325k / 495k / 530k |
| Growth per active hour; compactions | 161k; 9 | 106k; 1 | 136k; 0 |
| Cost share: cache read / cache write / output | 82% / 14% / 4% | 52% / 45% / 3% | 48% / 45% / 6% |
| Calls after a cache expiry (whole context rewritten) | 84 calls = 12% of cost | 59 = 43% | 18 = 43% |
| List-price estimate | $1,204 | $205 | $52 (+$31 subagents) |
| Wakes: background exit / Orca nudge / typed or delivered | 1,825 / 481 / 167 | 134 / 0 / 77 | 15 / 0 / 16 |
| Cost per wake (background exit) | $0.60 | $0.95 | $1.50 |
| Reviewer rounds delivered; workers started | 23; 158 | 13; 52 | 1; — |
| **Cost per round / per worker started** | **$52 / $7.60** | **$16 / $3.95** | — |
| API-error continuations (rate limit, server) | 97 | 5 | 0 |

**Cost is the size of the context times the number of calls.** Output is 3–6% of cost. In FLD, the cache-read rate alone makes each call cost about $0.12 before it does anything. If a wake comes more than five minutes after the last call, the cache has expired and the whole context is rewritten at 12.5 times the read price. That's why the two quieter sessions spend 43% of their cost on post-idle calls: they wait longer, so their cache expires more often.

### Cost by what the coordinator was doing

Each cell is the share of the session's cost and the list-price estimate.

| Category | FLD | Agent Annotate | Multi-Mac |
|---|---:|---:|---:|
| **Waiting on workers and mail** (quiet-wait, mail drain, check/inbox, worker-list/show/read) | **42.2% ($508)** | **41.4% ($85)** | 3.4% |
| **Closing message of a turn** (status text, no tool) | **21.0% ($252)** | 10.4% ($21) | 6.9% |
| Shell reads/search (grep, cat, ls, sed, ad-hoc python) | 12.4% | 12.3% | 44.6% |
| Orca messaging and lifecycle (send, reply, release, stop, worktree rm) | 7.1% ($86) | 3.9% | 6.4% |
| Beads | 2.7% | 1.8% | 2.3% |
| Coordinator notes (pending.txt, handoff, memory) | 2.7% | 1.7% | 2.7% |
| Worker briefs | 2.3% | — | 1.0% |
| Page drafts (writing/patching page markdown and cards) | 1.9% | 2.2% | 1.6% |
| Git/GitHub | 1.6% | 4.0% | 8.1% |
| **Annotate commands** (read, publish, resolve, other) | **2.6% ($32)** | **14.1% ($29)** | 11.3% |
| Reading the raw page store (comments.json, current.html, versions) | 0.7% | 1.2% | 0.6% |
| Dispatch (worker-start, task-create, terminal create) | 0.7% | 5.3% | 2.0% |
| Screenshots and pages | 0.4% | 1.8% | — |
| Release and rollout (uv, sync-skills, ssh, launchctl, tailscale) | 0.4% | 0.2% | 5.9% |
| Test runs started by the coordinator | <0.1% | — | — |

### What makes context grow fastest

This table shows the share of tokens added to the conversation, plus the size of each tool result where one applies. Every token added is re-read by every later call until the next compaction.

| Source | FLD | Agent Annotate | Per-item size |
|---|---:|---:|---:|
| The coordinator's own reasoning and messages | 37.5% | 31.1% | — |
| Wait/mail results | 19.1% | 14.1% | 414–563 tokens per result, 4,144 results in FLD |
| Harness reminders added each turn (output style, queued messages, snapshots) | 10.2% | 7.3% | 7,265 output-style reminders in FLD, one per turn |
| Shell reads/search | 7.2% | 6.3% | 313–637 |
| Orca send/reply | 5.7% | 3.6% | 299–402 |
| Worker briefs | 4.2% | — | 731 |
| Screenshots | 0.9% | **12.0%** | **2,534** |
| `worker-start` JSON output | 0.9% | **7.5%** | **1,445** |
| Wake notifications themselves | 2.6% | 1.3% | ~130 |

Growth runs at 106k–161k tokens per active hour, so a session passes 500k in three to five active hours. FLD then rode near the 1M limit and compacted nine times. The fastest growth comes from many small additions per wake, not from any single large read.

### What woke FLD, and what it did then

FLD's drained mail held **1,839 status notes**, averaging 1,245 characters, against **620 worker_done reports, 231 questions and 51 escalations**. Quiet-wait absorbs heartbeats but not status notes.

| Wake | Turns | Share of FLD cost |
|---|---:|---:|
| Mail held only status notes; coordinator only waited again or noted it | 354 | 13.1% |
| Mail held only status notes; coordinator then acted (508 of 719 replied, usually "GO" for a slot, port or merge) | 719 | 36.4% |
| Mail held a worker_done, question or escalation | 666 | 36.0% |
| Orca nudge with no mail read | 573 | 6.8% |
| Your typed messages and annotate Sends | 167 | 7.7% |

Many status-driven "GO" replies are **resource gating**, for example "ports 14300–14319 free, disk 35 GiB, slot empty → GO". A lease script can decide that without an AI.

### Cost per useful outcome

- **FLD:** $52 per reviewer round, $7.60 per worker started, $0.60 per wake. Typical active hour: $18.60, with 133 calls; p90 hour: $31.
- **Agent Annotate:** $16 per round, $3.95 per worker started, $0.95 per wake.
- **Annotate's own round trip** (from the [first evaluation](refactor-eval-20261104.md), model-free fixtures) is 5 commands and 380 proxy tokens for three answers, and 7 commands and 531 tokens for five. Those prices are tiny next to the context price paid for each call that issues them: in FLD, each of those 5–7 calls costs about $0.12 in re-reading. **Commands per round matter mostly because each one is a full context re-read.**
- Releases: this window had no clean whole-release sample in the coordinator transcripts. Rollout work sits in workers and the Multi-Mac session, where 66 rollout calls produced 16 errors and 5.9% of its cost. Stage 0 measures this per release.

### Failures that cost recovery steps

These counts come from tool results with an error flag or a known failure string.

| | FLD | Agent Annotate |
|---|---:|---:|
| Publish attempts that failed or said NOT PUBLISHED | 27 of 55 | 26 of 54 |
| Resolve calls that failed (mostly ambiguous number) | 21 of 152 | 4 of 48 |
| Shell errors | 143 | 12 |
| Rollout errors | 22 | — |

Many of the publish failures came from the browser-check failure that the current base already fixes. They are listed as recovery cost that happened, not as savings still available.

## 2. Drift: what agents do by hand that a tool should do

| # | Done by hand today (evidence) | What the tool does instead | Agent steps and tokens removed |
|---|---|---|---|
| 1 | **Card numbering**: the agent picks `"number": 3032` and matching `d:q3032`, and renumbers with regex scripts when the server rejects them (409s on #35/#49/#91/#96; the v61→v62 renumber script) | Drafts use local keys (`?a`, `?b`). Publish allocates numbers inside the store transaction and prints the mapping | Renumber/retry loops (4 collisions = 5,011 tokens in the first evaluation's sample); predicting global numbers |
| 2 | **Version choice and drafting**: copy `vN.md` to `vN+1.md` and patch strings (52 runs of `/tmp/m1d-vN.py`, 205 inline python edits of page or notes markdown) | `annotate publish --from page.md` picks the next version; `annotate draft --section NAME --from sec.md` replaces one section | Throwaway scripts; reading old versions to patch them |
| 3 | **Card posting, retry and publish verification** (`pubfix` script run 46 times; about half of publish attempts errored) | One transactional publish (page + cards + verify) with a one-line receipt: `v412 live, cards #3101–#3104, verified` | Publish → check → repost loops; reading NOT PUBLISHED output |
| 4 | **Owner binding**: Sends queued silently to a dead owner; agents read owner pids from `workspace --json` with inline python (11 times) and re-claim by hand | The SessionStart hook rebinds by session id and terminal evidence; the server refuses to queue to a dead pid and says so | Manual `claim`; stale-owner diagnosis |
| 5 | **Inbox parsing**: inbox, then reading raw `comments.json` and `current.html` (115 raw store reads), plus 140 inline python wrappers around orca/annotate/bd JSON | `annotate round --worklist` prints one line per item: handle, card, answer, kind (approve/answer/note), linked bead | Raw store reads; JSON wrapper scripts |
| 6 | **Resolving one item per call** (152 resolve calls in FLD; 21 ambiguous-number failures) | `annotate resolve --from worklist.done` or `--items a,b,c --in v412`: one call and one receipt | N−1 calls per round |
| 7 | **Release and three-Mac rollout**: wheel build, uv install, sync-skills, restart loop, ssh/launchctl per Mac (66 calls / 16 errors in Multi-Mac) | `scripts/rollout.py plan` prints the exact per-Mac steps; `apply --mac M1` (repeat per Mac after your yes) installs, syncs skills, restarts pages, runs `doctor --versions`, backs up, prints one line per Mac and rolls back on failure | Dozens of steps and recovery per release |
| 8 | **Waiting on workers and mail**: 4,144 wait calls and 1,825 wakes in FLD | Status notes go to a log file and never wake. Wakes happen only on worker_done, question, escalation or explicit `--needs-reply`, at most one digest wake per 30 minutes for status | About half of FLD's wakes |
| 9 | **Resource "GO" gating** (ports, CI slots, disk) by reply | A lease script: `lease take ports-14300 --for ctx_…` grants if free and records the owner; release on worker_done | Status → reply round trips (508 replies in status-only wakes) |
| 10 | **Status summaries and notes**: 1,875 closing messages; 334 inline edits of `pending.txt` | `run-summary` renders Orca run state + Beads + leases into a ≤40-line digest on demand; the coordinator writes a note only when a decision changes | Hand-kept state file; long closing messages |
| 11 | **Worker briefs**: 521 brief writes in FLD, 4.2% of its context | `brief.py BEAD` fills the standard brief from the bead, base branch and rules; the coordinator adds only the task-specific lines | Re-typing rules into every brief |
| 12 | **Session handoff**: successors read long handoff files; FLD rode near 1M and compacted nine times | State lives in Beads + Orca run + `run-summary`. The coordinator recycles itself at 250k by reading the digest (~20k tokens) | Giant contexts (see the Stage 2 simulation) |
| 13 | **Screenshots read by the coordinator** (64 in Agent Annotate, 2,534 tokens each, 12% of its context) | `annotate verify --shots` (headless) returns pass/fail plus only the failing crops; review images stay with the worker that made them | Image tokens re-read for the rest of the session |
| 14 | **Hourly board sweeps** by AI workers (BEAD-SWEEP-30…43) and `bd` counting via inline python | A Windmill/launchd scheduled script: counts, stale detection, closing of finished sessions; AI only for judgment items it lists | Hourly worker sessions (not measured here) |
| 15 | **Test runs** started and watched by agents | `scripts/ci.py` and the existing full-suite routes run on a schedule or by trigger; workers read a one-line receipt | Watching long test output |

## 3. Storage: JSON files vs SQLite vs Postgres

**Today, measured on copies:** the FLD page directory holds 6,868 files and 2.1 GB. Most of that is assets (1.18 GB, 4,186 files) and baked versions (588 MB, 1,193 files). Its records are spread over `comments.json` (6.3 MB: 1,514 items, 71 archived, 87 approved plans), `current.meta.json` (179 KB), `project.json`, `read-state.json`, `seen.json`, `rounds.ndjson` (1.4 MB) and a bus log of 49,990 lines (15.6 MB; 23,027 `comment_updated`, 13,377 `comment_carried_forward`). Each change re-reads and rewrites the whole `comments.json`: about 70 ms to load and 100–180 ms to write and fsync. A single SQLite row update commits in under 1 ms.

The code touches `comments.json` from about 20 modules. It uses per-file `flock` in 8 modules (`.comments.json.lock`, `current.meta.json.lock`, `project.json.lock`, delivery locks) and `os.replace` at about 15 sites. `sync_server._merge_content_stamp` states the remaining race in its own docstring: *"The window still needs the CLI to take the same lock to close completely."*

| Need | JSON files + locks (today) | SQLite, one file per Mac (WAL) | Postgres (or Dolt) |
|---|---|---|---|
| Concurrent writers: server threads, CLI, hooks | Per-file locks; correct only if every writer takes the right lock; lost-update race documented | One writer at a time, many readers, busy-timeout; all processes are on the same Mac | Full concurrency; more than needed |
| Atomic publish (page + cards + numbers) | Multi-file batch commit built by hand (`review_versions.py`) | One transaction | One transaction |
| History and unread queries | Scan the 15.6 MB bus plus JSON cursors | Indexed queries (`events` by page and time; `read_cursor`) | Same |
| Three Macs each hosting their own pages | Works: files are local | Works: file is local; no daemon | Needs a server on each Mac, or one shared server that the M5 and M1Max16 depend on (an M5 away from home would stall) |
| Backups | Copy directories; not atomic across files | `VACUUM INTO` or `.backup`, one consistent file; assets stay as files | `pg_dump` per server; more to run |
| Operations | None | None beyond Python's built-in `sqlite3` | Install, upgrade, auth, ports, launchd per Mac |
| Migration of live pages (FLD 650+ versions) | — | Import JSON + bus into tables; versions, sources and assets stay as files and are referenced by path | Same import plus a server |
| Dolt specifically | — | — | MySQL-compatible, not Postgres; runs on the M1 for Beads; its versioning is unused for pages |

**Recommendation: SQLite, metadata only, one `annotate.db` per Mac.** Keep HTML, sources and assets as files. Migration cost: an importer that reads `comments.json`, `current.meta.json`, `project.json`, the cursors and the bus into tables, plus a JSON export so older clients and `eval` keep working. Rehearse on copies of all three Macs' pages. Run one release of dual-write: the DB is authoritative, and the JSON is written as an export. Then retire the lock files. Estimate: 10–15 worker-days including rehearsal and staged rollout.

**What SQLite will not do:** cut tokens by itself, fix Orca mail, or fix owner lifecycle. It removes the cross-file race and partial-publish failure classes, and it makes the single-command operations in Stages 1 and 3 simple to build correctly.

## 4. The plan

Targets use the Stage 0 meter on real sessions, comparing three days before with three days after, and compare like-for-like work (rounds, workers started). Annotate-action targets use the budget fixtures in `scripts/bench.py` (ports 18700–18799, copied pages only).

### Stage 0 — Meter and budget test (1–2 worker-days)

- **What:**
  - Turn this study's analyzers into `scripts/orch_cost.py SESSION.jsonl [--since]`. It reports cost per wall hour, calls per hour, wakes per hour by mail type, median/p90 context, category shares, annotate's share and per-action costs (the Goal 1 table), failures per category, and cost per round or worker started.
  - Add `bench.py --budget`, which fails CI when any annotate action exceeds its Goal 1 budget.
- **Agents stop:** estimating their own context or cost.
- **Measured by:** reproducing this document's numbers within 2% on the same copies. The budget test fails on today's base, which proves the test bites.
- **Risk / rollback:** none; read-only plus one test.

### Stage 1 — Make annotate light (2–3 worker-days; output and CLI surface only, no data change)

- **What:**
  - **Receipts:** one line. Publish prints `v412 live · 3 cards #3101–#3103`. Resolve prints `resolved #14065 #14316 #14320 in v412`. No share link, no owner banner, no "Invocation" line, no ID lists; `--json` keeps the full form for scripts. This also stops the page's private link from being copied into every transcript.
  - **Inbox:** one line per actionable item (`#14065 select "Update staging?" → "Update staging" · note: …`). No column padding. Publish, plan, round and seen events are hidden unless `--all-events`. The undecided list becomes a count.
  - **`--worklist FILE`** writes the same lines with exact handles, and the agent ticks them off.
  - **Batch resolve:** `annotate resolve PAGE #a #b #c [--from FILE]` resolves in one transaction and prints one receipt. Each handle is unambiguous (number, or ID when numbers collide). Today `resolve` takes exactly one item (`cli.py` `sp_resolve`).
  - **Skill:** cut the page reference out of the default load; errors name the one section to read.
- **Agents stop:** one resolve per card, reading share links and banners, parsing padded tables, reading `comments.json` to find IDs.
- **Targets (budget):**
  - Read one round: 1 command, ≤ 40 + 60·N tokens.
  - Resolve: 1 command per round, ≤ 15 tokens per card.
  - Publish receipt: ≤ 25 tokens.
  - Session start: ≤ 700 tokens.
  - Small round: 9–12 → 5–7 commands live (5 → 3 in the fixture, since resolving goes from 3 calls to 1).
- **Failure classes removed:** ambiguous resolve (21 + 4 failures in the window); missed IDs.
- **Risks:** scripts that parse today's text output. **Mitigation:** `--json` unchanged; grep the repo and the skills for parsers first.
- **Rollback:** previous wheel.

### Stage 2 — Lighter coordination (4–6 worker-days; mostly Orca helpers, briefs and the skill, little annotate code)

1. **Mail that does not wake.** Workers send `status` only when the brief asks; anything needing an answer is a `question`. `orca-quiet-wait` absorbs `status` like heartbeats and appends it to `run/status.log`. It wakes on worker_done, question or escalation, or on a status marked `--needs-reply`. It wakes for a status digest at most once per 30 minutes. Apply this M1-first (quiet-wait is a shared tool; prove it in a live M1 run before any other Mac).
2. **Leases instead of GO replies.** `lease take|release|list NAME` (a file under the run directory with owner and expiry). Workers take ports, CI slots and disk budget themselves; the coordinator is asked only on conflict.
3. **Recycle at 250k.** State lives in Beads, the Orca run and `run-summary`. At 250k context, the coordinator hands off to a fresh session that reads the digest, using the existing handoff skill.
4. **One-line outputs.** `worker-start` prints `started ctx_… term_… name`; mail drain prints one line per message with the path to its full body; `run-summary` replaces long closing messages. The coordinator ends a wake with one line.
5. **Brief template.** `brief.py BEAD` produces the standard brief; the coordinator adds only the task delta.

**Agents stop:** reading progress notes, replying GO, keeping `pending.txt` by hand, carrying days of history in context, and reading 1.4k-token JSON per dispatch.

**Targets (FLD-like run):**
- Wakes: 21.7 → ≤ 10 per wall hour.
- Calls: median 133 → ≤ 50 per active hour.
- Context: median 509k → ≤ 150k; never above 250k.
- Cost: $14 → $4–6 per wall hour; $52 → ≤ $20 per round.
- Agent Annotate-like run: $16 → ≤ $7 per round.

Smaller contexts also make every remaining annotate command cheaper: about $0.12 → $0.05.

**Why these numbers:**
- Status-only wakes are 49.6% of FLD cost. Removing all of the "only waited/noted" share (13.1%) and half of the "then acted" share (18%) saves about 31%.
- On the actual call sequence, recycling at 250k (40k base + 20k re-reading + 8 calls per restart) costs **0.35 (FLD), 0.42 (Agent Annotate) and 0.52 (Multi-Mac)** of today's cost. The same model without a cap reproduces actual cost within 2%.
- Combined, the projected saving is 55–75%. The two effects overlap, so the range is not their simple product.

**Failure classes removed:**
- A status note absorbed as noise when it needed an answer: it becomes a question.
- API-error cut-offs (rate limit, server error): 97 in FLD, partly driven by 500k+ inputs.
- Compaction loss of in-flight state.

**Risks:**
- A worker that needs an answer sends `status`. Mitigation: the brief rule, plus the digest wake.
- Recycling loses unwritten reasoning. Mitigation: the digest must pass a "fresh session answers 5 state questions" check before cut-over.
- Orca's own wait semantics are outside this repo.

**Rollback:** flags on quiet-wait (`--wake-on-status`) and the recycle threshold.

### Stage 3 — Annotate does its own bookkeeping (5–8 worker-days; option A of the first evaluation, minus what Stage 1 already did)

- **What:**
  - Cards are written as plain text in the page: a question line plus option bullets, with no number, anchor or JSON. Publish allocates numbers and anchors in one store transaction, and evidence defaults to the enclosing section.
  - `annotate publish --from page.md` picks the next version.
  - `annotate draft --section NAME --from sec.md` replaces one section of the current version, so agents stop copying and patching whole versions.
  - SessionStart and Send validate the owner and rebind when the current session and terminal match.
  - Errors print the one command that fixes them.
- **Agents stop:** choosing numbers, versions or `d:qN` anchors; writing card JSON; reading old versions to patch them; writing renumber or publish-fix scripts; re-claiming pages.
- **Targets (budget):**
  - Ask one question: ≤ 10 tokens of markup.
  - Publish one small update: 1 command, 0 retries, written tokens ≈ the changed section only.
  - Small round: 3 commands live and in the fixture (3- and 5-answer rounds).
  - Annotate share of coordinator cost ≤ 3%.
  - Raw-store reads and renumbering per round: 0.
- **Failure classes removed:** number collision and "strictly increasing" errors, missing evidence anchors, partial publish visible, stale owner.
- **Risks:** identity and lineage of existing cards, cursor positions, older browser clients. **Mitigation:** additive fields; keep existing numbers, IDs and URLs; the old JSON card format is still accepted; capability gate.
- **Rollback:** previous wheel; the data stays compatible.
- **Measured by:** `bench.py --budget` plus the fixtures for first publish, number conflict, failed publish, dead owner and interrupted Send, with five interleaved runs per ref; then Stage 0 on live rounds.

### Stage 4 — Scripts for routine jobs (4–5 worker-days)

- **Rollout:** `scripts/rollout.py plan VERSION` prints the per-Mac steps. `apply --mac M1` and the other Macs run them: install the release wheel with uv, sync skills, restart pages via `restart_record`, run `doctor --versions`, back up first, roll back on failure, and print one line per Mac. Each remote Mac needs your explicit yes; the script asks for it and records it.
- **Housekeeping on a schedule:** bead sweeps, finished-session cleanup, disk checks and board counts run as Windmill/launchd scripts. They list only items needing judgment, which a small model or the coordinator handles.
- **Tests:** full suites run via `scripts/ci.py` routes; agents read the receipt line.
- **Agents stop:** doing rollouts step by step, running hourly sweep workers, watching test output.
- **Targets:** rollout is 2 agent commands per Mac (from dozens; 16 errors in the Multi-Mac sample); 0 AI tokens for routine sweeps; rollout errors needing manual recovery are 0 in 3 consecutive releases.
- **Risks:** a script hides a Mac-specific failure. **Mitigation:** dry-run on the target first (a standing rule), refuse on any unknown state, and print the failing step.
- **Rollback:** the script keeps the previous wheel and skills snapshot per Mac.

### Stage 5 — SQLite store (10–15 worker-days)

- **Data model:**
  - `pages(id, slug, project, owner_session, owner_pid, owner_start, terminal)`
  - `versions(page, n, state[draft|live], source_path, html_path, published_at)`
  - `items(id, page, number, kind, anchor, status, created_in, resolved_in, body_json)`
  - `events(seq, page, ts, type, item, data_json)`
  - `read_cursors(page, reader, seq)`
  - `deliveries(id, page, round, target, state, receipt_json)`
  - `plans(page, id, version, approved_at)`
  - `leases(name, owner, expires)`, if Stage 2 leases move here
- **How:** import read-only from the existing files into a new `annotate.db`. Keep files as the asset store. One release dual-writes the JSON export; then lock files retire. The commands are unchanged, so agents notice nothing.
- **Agents stop:** nothing new; this makes the one-line answers of Stages 1 and 3 trustworthy.
- **Targets:**
  - Publish is one transaction; no `.lock` files.
  - Inbox/history queries take < 50 ms on FLD's history (from scanning 15.6 MB).
  - Zero lost-update incidents.
  - Import of the FLD copy preserves every item, number, version and cursor (checked by a diff tool).
  - The Goal 1 budgets still pass.
- **Risks:** migrating a long live history; old clients. **Mitigation:** rehearse on copies from all three Macs; a capability gate; JSON export.
- **Rollback:** the original JSON files are untouched by import; switch back with a flag.

### Stage 6 — optional, after measuring

The server becomes the authority on numbers, counts and status for the browser too (option C of the first evaluation). Fund it only if Stage 0 shows browser/CLI disagreement still costs rounds.

### Totals

| Stage | Worker-days | Effect | Main failure classes removed |
|---|---:|---|---|
| 0 Meter + budget test | 1–2 | enables proof; guards "light" | — |
| **1 Make annotate light** | **2–3** | read and resolve under budget; round 9–12 → 5–7 commands | ambiguous resolve, missed IDs |
| 2 Lighter coordination | 4–6 | **−55–75% coordinator cost**; each command ~$0.12 → $0.05 | ignored status, API-error cut-offs, compaction loss |
| 3 Annotate bookkeeping | 5–8 | ask and publish under budget; round 3 commands; annotate ≤ 3% of cost | numbering, evidence-anchor errors, partial publish, stale owner |
| 4 Routine scripts | 4–5 | not measured here (sweep and rollout workers) | manual rollout errors |
| 5 SQLite | 10–15 | ≈0% direct | lost updates, cross-file races |
| **Total** | **26–39** | | |

Savings are projections from the measured sequences; 0% is a possible result for any stage. Claim a saving only after the Stage 0 meter and budget test show it, with every outcome preserved.

## Limits of this study

- Three sessions over four days. FLD dominates the totals.
- Category rules are text patterns. Shell reads (12–45%) contain some work that belongs to other categories.
- Cost uses each session's own recorded rate.
- Per-action figures come from grouping commands by type:
  - Publish cost is divided over the versions drafted (FLD 92, AA 38).
  - Reading a round counts annotate reads from a round's delivery until the next publish.
  - "Printed an error" includes attempts that partly succeeded.
- Worker sessions (including hourly sweep workers) were not measured.
- No live page, installed annotate, M5, M1Max16 or forbidden workspace was touched. No product code changed.
