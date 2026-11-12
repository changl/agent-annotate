# What exists: observed capabilities, 12 November 2026

**3/3 Codex probes returned the requested line; 0/3 Claude probes reached inference.** Codex took **37.649–43.494 s** (median **40.709 s**); Claude's authentication failures took **0.392–0.687 s**. Windmill reported **11 worker slots**, **17 schedules / 11 enabled**, and **3 apps**; Beads reported **195 issues** from both M1 and M5.
Local versions: Orca **1.4.256**, Claude Code **2.1.322**, Codex CLI **0.167.1**, Beads **1.3.4**, Windmill CLI/backend **1.868.0 / CE 1.868.0**. Remote Orca answered on M5 (**1.4.256**) and M1 Max 16 (**1.4.257**); SSH answered on both.
Later, M1 Max 16 stopped answering Orca/SSH and Tailscale reported it **offline** (`tailnet-final.json`); this does not distinguish sleep, shutdown or network loss. No login refusal was observed; no further remote check or repair was attempted after diagnosis.
Evidence directory `E` = `/Users/changlee/projects/agent-annotate/shared/agents/from-zero-20261112/exists/`. Captured help, public pages, API metadata, notes, scripts and timing receipts live there; source letters below identify each grid cell.
Recompute numbers without starting agents: `nice -n 19 python3 E/summarize.py` (replace `E` with that path). Collection: `collect.py help`, `collect.py live`, `public_docs.py`, `inventory.py`; original timing command: `nice -n 19 python3 E/tiny_runs.py` (now guarded against exceeding the allowance).
Quality: read the **50** seeded random source rows in `sample-50.json`; **0/50 transcription mismatches** against their source lines. This checks capture accuracy, not runtime correctness; no conversation transcripts were extracted. Historical memory notes are labelled below and were not reproduced as failures today.
Scope: safe reads and the six permitted probes only; no launches through Orca, board writes, deployed changes, phone actions or notification sends. Public documentation describes capabilities; live reads establish only the deployment facts stated here.

## Four needs × installed pieces

“Partial” means the named mechanism covers only part of the need; it does not mean the method has been built.

| Need | Orca [O] | Claude Code CLI [C] | Codex CLI [D] | Beads [B] | Windmill [W] |
|---|---|---|---|---|---|
| Shared record | Partial: projects, Tasks, Runs, mail and sessions, host-owned | Partial: files and local transcripts; no shared record service | Partial: files and session events; no shared record service | Typed issues, decisions, acceptance text, links, comments and Dolt history | Jobs/results, JSON state and SQL data, exposed through API/CLI |
| Short helpers | `worker-start` dispatches locally or to a paired server and collects reports | `claude -p` takes a prompt, uses allowed tools, emits a result and exits | `codex exec` takes a prompt, emits events/final file and exits | Cannot launch a model helper; records claims, dependencies and outcomes | Scripts can launch CLIs; installed host bridge collects result files |
| Checks and clocks without helpers | Partial: scheduled shell precheck can skip the model; normal automation runs a prompt | Partial: command hooks during a running session; no independent scheduler established | Partial: lifecycle hooks during a running session; no standalone CLI scheduler shown | Partial: mutation hooks and gate checks; an external caller must drive time | Scripts, flow dependencies, webhooks, cron, sleeps and timeouts need no model |
| Person: screens, voice, rare push | Agent screens on desktop/mobile, dictation and completion push; no method-specific screens | Interactive questions; Remote Control exists but this Mac's gateway configuration excludes it | Terminal questions/approvals; phone UI comes from another client such as Orca | Cannot provide this whole UI; human gates are records, not a phone question service | Web apps and approval links; existing inbox takes typed notes; voice/push not established |

## Orca [O]

Orca is an editor and runtime that owns workspaces and agent sessions. Its orchestration commands track assignments and move messages between agents.
Sources: installed `orca --help`, `skills get orchestration`, its placement/recovery references, `skills get orca-cli` and automation reference (captured in `E/orca-*.json`); public [runtime modes](https://www.onorca.dev/docs/ways-to-run) and [mobile](https://www.onorca.dev/docs/mobile), saved in `E/orca-*-readable.md`.
Short runs: `worker-start --spec-file … --agent …` can start unattended; `worker-read` collects bounded output, and `worker_done` reports the outcome. Settled workers can close automatically; new-worktree workers are retained. Startup/cost were not measured because creating Orca resources was forbidden; inference cost belongs to the selected helper.
Context: a prompt/spec and workspace can be chosen, but a worktree is not an exact-file read restriction. Output files remain in the workspace; a successful start receipt alone does not certify a result or its correctness.
Across computers: `--on` places work on a paired Orca server with its own tools, credentials and repository; both other Macs answered read-only status. The execution Mac must stay awake/reachable; a sleeping controller need not stop work on an awake remote server. Sleeping-host recovery was not tested.
Events/clocks: automations accept cron/RRULE and named schedules; `--precheck` runs shell before scheduled prompts, and nonzero/error/timeout skips the model (default timeout 60 s). “Run now” bypasses it. The local automation list was empty; no measured firing-delay guarantee.
Person: decision gates hold a question/options and block a Task; installed gate help exposes no default/deadline. Mobile documentation supports typed/dictated replies and agent-finished push, with offline sends queued until reconnection; phone pairing and delivery were not tested.
Records/state: Runs, Tasks, gates, messages, workspace metadata and provider sessions are readable through the CLI; they are not a defined goal/agreement/ruling schema. State distinguishes live/exited/unverifiable; input acceptance differs from `turn_started`, and stop can return `stop_unknown`.
Known trouble, historical: `codex-worker-silent-stall.md` reports roughly 55 minutes of idle API-error workers missed by quiet waiting; `orca-quiet-wait.md` records changed consuming-mail semantics and delayed mail; `orca-wake-filter-hook.md` records a reverted hook that consumed unseen mail. These notes do not prove current recurrence.
Cannot supply: an exact-file boundary, guaranteed detection of silent stalls, or the method's domain record/screens merely by launching a worker. Installed recovery documentation explicitly says silence and unverifiable liveness do not prove exit.

## Claude Code CLI [C]

Claude Code is a terminal coding helper with file and command tools. Its print mode exposes the same agent loop to scripts without an interactive terminal.
Sources: installed `claude --help`, package README and wrapper; public [programmatic runs](https://code.claude.com/docs/en/headless), [hooks](https://code.claude.com/docs/en/hooks), [Remote Control](https://code.claude.com/docs/en/remote-control), saved as `E/claude-*.txt`; probe receipts in `tiny-results.json`.
Short runs: `-p`, `--output-format json/stream-json`, `--json-schema`, `--permission-prompts none` and `--no-session-persistence` support bounded unattended calls. Capture stdout as a file or permit file tools; normal noninteractive failures exit nonzero. All three measured attempts failed before inference, so successful latency and smallest successful cost remain unknown.
Context: stdin/prompt can contain exactly supplied text; `--tools`, permission rules and restricted mode constrain tools/directories. Ordinary `--add-dir` adds access/context, not an exact-file allowlist. `--bare` skips ambient discovery/hooks but does not use subscription OAuth/keychain; explicit authentication is required.
Across computers: an external SSH/process runner can invoke an installed CLI; this is not built-in fleet placement. Claude version was confirmed on M5; no Claude executable was found in five checked standard bin directories on M1 Max 16. An executing Mac asleep cannot process the call; no wake test was performed.
Events/person: command hooks handle lifecycle events while the helper exists, without another model call for the hook itself; they are not an independent clock. Interactive questions can wait for a person; `--permission-prompts none` removes person-answer tools/denies unresolved approvals. No general question deadline/default was established.
Records/state: local conversation files, resumable sessions, structured tool/result events and ordinary output files are accessible to other processes. A final result has usage/cost/error fields; check `is_error` and process exit, not the word `success` alone (these failed probes had `subtype: success`, `is_error: true`, exit 1).
Limits/trouble: public Remote Control excludes non-Anthropic base URLs; the local wrapper points to CLIProxyAPI and injects `--settings`, also restricted in server mode. Historical `claude-config-dir-live-config.md` records editing an inactive config path and leaving MCP pointed at an old hostname. Neither local transcripts nor native remote access supplies the shared method record.

## Codex CLI [D]

Codex is a coding helper that reads files and runs tools. `codex exec` makes one job available to a noninteractive caller and then ends.
Sources: installed `codex exec --help`, `codex --help`, feature list and local wrapper; official OpenAI documentation for [noninteractive mode](https://developers.openai.com/codex/noninteractive/) and [configuration](https://developers.openai.com/codex/config-reference/), saved in `E/codex-*-readable.md` and `codex-config-direct.json`.
Short runs: prompt/stdin, `-C`, `--json`, `--output-schema`, `-o` and `--ephemeral` support unattended calls and a final file. Three fresh processes returned the requested line with exit 0; stdout exposed `thread.started`, `turn.started`, items and `turn.completed` with token usage. See timings below; no billed-dollar receipt was exposed.
Across computers/context: an external runner can start it over SSH, with credentials/runtime installed there. Version 0.167.1 was confirmed on both other Macs; M1 Max 16's noninteractive SSH PATH initially lacked Node, and worked with `/opt/homebrew/bin` included. `-C` selects the working root; read-only sandboxing limits writes, not reads to an exact file set.
Events/person: installed hooks cover session/prompt/tool/stop events; these require an existing invocation. The standalone CLI help shows no independent scheduler. Interactive clients can request input/approval; an `exec` job with approvals disabled needs no person, but provides no built-in phone question/deadline UI.
Records/state: persisted sessions/events and ordinary output files can be read by other processes; ephemeral mode avoids session rollout persistence. JSON distinguishes completed/failed turns and errors; process exit plus the expected result must be checked. A live CLI process is not proof that a turn is making progress.
Limits/trouble, historical: `codex-hooks-review-blocks-workers.md` records hooks-review/update prompts blocking Orca starts; `codex-worker-silent-stall.md` records API 400 stalls; `rtk-codex-init-codex-home-trap.md` records Orca's runtime home causing duplicate instructions. The controlled probe disabled hooks/plugins; it did not test normal startup with this configuration enabled.

## Beads [B]

Beads is a structured issue and dependency store accessed with `bd`. Dolt supplies its SQL storage, version history and synchronization mechanisms.
Sources: installed `bd --help`, `schema`, `gate --help`, `show --help`, `history --help`, `serve --help`, `dolt --help`; installed `runtime/beads-1.3.4/CHANGELOG.md`; public [README](https://github.com/gastownhall/beads), saved as `E/beads-readme.txt`.
Record: schema includes acceptance criteria, design/notes, decision/message/gate types, JSON metadata, comments, typed links, audit-event fields and lease/heartbeat timestamps. `history`, `history --events`, `show --as-of` and JSON/export expose history to other pieces; ephemeral/no-history items and purge/compaction mean not every record is permanent.
Short runs: cannot start an AI job itself; it records claims/readiness/results. CLI operations need no model tokens, although human-written hooks can launch arbitrary commands. Helper cold-start/cost are therefore not applicable to Beads itself.
Across computers: current client metadata selects the M1 Dolt SQL server; independent read-only M1/M5 queries returned 195 issues. Clients need `bd`, matching server/schema configuration, credentials and network access; the M1 server must be awake. Other clients cannot use that shared server while its Mac is asleep; no sleep test.
Events/clocks: CLI mutation scripts `on_create/on_update/on_close` run after commits; Git integration hooks also exist. Timer, human, GitHub and bead gates are present, but `bd gate check`/a watcher must evaluate them: a stored timer is not a running clock. `show --watch` polls; its interval was not established here.
Person/state: human gates require manual resolution and do not deliver a phone question or deadline policy. Issue status, assignee, leases and heartbeat timestamps describe reported ownership; Beads does not independently observe a helper process or know whether “in progress” is a stall.
Limits/trouble: `bd serve` offers an OpenAPI/HTTP surface but its help explicitly says mutation hooks do not fire there; `/healthz` can stay green with an unreachable database. Historical `agent-annotate-beads-board-on-m1.md` records missing redirects/host-specific credentials; the current hostname differs from that note. No model scheduler or complete person UI is built into `bd`.

## Windmill [W]

Windmill runs scripts and workflows on workers backed by a central database. It also hosts web apps and records job inputs, results and execution state.
Sources: installed `wmill --help`, CLI skill, `/Users/changlee/services/windmill/{README.md,compose.yaml}` and `/Users/changlee/projects/windmill-build/host/run_stage.py`; live `listWorkers/listSchedules/listApps/listJobs/getAppByPath` metadata in `E/windmill-*.json` and `inbox-deployed.json`; public [triggers](https://www.windmill.dev/docs/triggers) and [approval](https://www.windmill.dev/docs/flows/flow_approval).
Short runs: scripts can start a CLI; the installed custom `run_stage.py` composes a prompt, launches Claude/Codex headlessly, waits with a timeout, reads a JSON result and resumes its flow with success/failure. This is existing local integration, not a built-in Claude/Codex worker type; no new job was submitted or timed.
Across computers: four local containers expose eleven reporting slots (three default, eight native), all reporting `job_isolation: none`. Remote worker groups require workers plus central database connectivity; the existing host bridge can instead dispatch work through Orca/SSH. The running server/worker/execution hosts must be awake; containers do not directly imply access to Mac files or CLIs.
Events/clocks: scripts/flow steps, HTTP webhooks, cron schedules and scheduled polls need no model. Five existing webhook-triggered `f/test/run` records had creation-to-start delays **0.004837–0.031502 s**; these are observed queue delays, not webhook/network latency or an SLA. Files/messages need an appropriate trigger/integration; no filesystem event latency was measured.
Person: approval/resume URLs can suspend work, set a timeout, and continue on disapproval/timeout for a subsequent branch. Timeout normally cancels; choosing a business default requires flow logic. Custom approval forms are documented as Cloud/Enterprise-only, so cannot be assumed in this CE installation.
Records: job UUIDs, inputs/results/logs, flow state, versions, JSON states, resources and SQL data are accessible through API/CLI. Job retention and editable data are not a promise to preserve every event indefinitely; a complete domain/audit model is not supplied automatically.
State/failure: queued/running/suspended/completed-success/failure/canceled and worker ping report scheduler/executor state; external helper truth depends on the bridge reporting it. Suspensions release workers. A responsive server/worker is not proof that a remote helper progressed or met its acceptance criteria.
Existing UI: deployed `f/inbox/needs_chang` exactly matches the eight checked local frontend files and backend in `~/projects/inbox`; it lists suspended human gates, excludes machine waits, accepts approve/reject plus a typed note, and has responsive CSS. No voice/push code was found in those files; no phone rendering/action was tested.
Known trouble, historical: `wmill-flow-push-drops-run-as.md` records run-as identity lost on flow push without the preservation field. The current minute test-poll schedule is disabled despite the local README describing it as scheduled. The installed failure-notice script targets an Orca Run, not a verified push to the person.

## Other installed pieces [E]

Sources: `E/local-extras.json`, `remote-*.json`, `launchd-man.txt`; Git/SQLite/Postgres version commands; current annotate `store.py/review_history.py`; deployed inbox source and installed Scotty directory/plist. These are supporting mechanisms, not additional model-helper kinds; none was given a timed inference run.
Git stores shared, versioned text/files through commits and remotes, but not uncommitted events or live helper state; hooks run deterministic commands only on Git operations. Dolt is running for Beads; native Postgres 18 is running locally and Windmill has Postgres 18 in Docker. SQL can hold structured shared records; SQL alone supplies neither human screens nor complete audit history.
SQLite 3 is available for local transactional records; its presence does not establish a shared multi-Mac service. PostgreSQL access from other Macs was not tested, and no new database/table/schema was created.
Tailscale and Syncthing processes were seen on all three Macs; SSH shortcuts worked from M1 to both others. Tailscale carries network access, not job execution or wake-up guarantees; Syncthing copies files, not shared transactions or guaranteed event history. Folder synchronization/conflict behavior was not tested.
macOS `launchd` can start deterministic commands on intervals/calendar times/path changes without model calls. Its installed manual says interval firings during sleep are missed, calendar firings coalesce on wake, and `WatchPaths` can miss changes; it reports process exit, not whether a helper achieved its task.
Agent Annotate already has shared review pages, typed comments/decisions, document versions and round/event history; its source does not make it a general helper scheduler. Scotty's installed board UI is another partial person-facing surface; its mobile/notification behavior was not tested. Neither is proof of the four needs being joined.
The bounded inventory found no `ntfy` executable or ntfy/Gotify/Pushover process. Orca's documented mobile push is a real available mechanism; an actual rare-alert policy and successful delivery to Chang's phone remain unverified.

## Measured tiny runs

`tiny_runs.py` started one process at a time under `nice -n 19`, in six fresh `/tmp/exists-*` folders, asking for the supplied one-line value; all six ended. Timings cover process creation through exit, including inference/queue time where present, not isolated first-token startup. Provider/OS caches were not cleared; fresh process does not mean cold provider.

| Kind / settings | Three elapsed seconds | Result / smallest observed usage |
|---|---|---|
| Claude 2.1.322, requested `haiku`, low effort, restricted/no tools | 0.687, 0.414, 0.392 | Authentication failure, exit 1; 0 model tokens, reported $0; no successful-run cost/latency |
| Codex 0.167.1, `gpt-6.1-sol`, low effort, ephemeral/read-only | 37.649, 40.709, 43.494 | Exact line, exit 0; smallest total input 13,869 + output 7 tokens |

Codex input totals were 13,871 / 13,871 / 13,869; cached subsets were 0 / 3,968 / 0. Output was 7 tokens each. The local gateway returned no billed-dollar amount; these observations establish neither a cheapest possible invocation nor subscription marginal price.
Claude probe defect: adding a second `--settings` replaced the wrapper's gateway settings, and the isolated config had no login. All results had API duration 0; this is not evidence that ordinary configured Claude fails. The three-attempt allowance is exhausted, so successful Claude timing remains missing.
Codex hooks/plugins/ambient discovery were disabled for this controlled probe; the development-only discovery-skip flag emitted a warning item, followed by a successful turn. No model tool execution/file-change/MCP items occurred. The caller captured each result file; agent-driven file reads/writes were not benchmarked.

## Gaps established or left unverified

- None of the inspected stock surfaces automatically supplies the method's full goal/agreement/done-line/ruling/rule/result/event model or its cross-record invariants; storage and generic workflow primitives exist.
- Normal Orca workspaces and Codex working roots do not themselves enforce “only these files may be read”; supplied prompt context and filesystem access are different things.
- No inspected deployed app implements all the proposed method screens. Phone dictation/push exists in Orca's documentation, but screen parity, paired-phone delivery and rare-push behavior were not exercised.
- No inspected state label guarantees that a live remote helper is making progress. A sleeping execution host cannot do local work; no sleep/reconnect or silent-stall detection experiment was authorized.
- Missing measurements: successful Claude startup/cost, true bill charges, normal-hook startup overhead, event-to-person latency and sleeping-host behavior. The unsuccessful Claude probes prevent claiming the full timing deliverable is complete.

## Surprises

- Orca already documents phone dictation, offline reply queuing and completion push; its scheduled shell precheck can avoid a model invocation entirely. No local Orca automations were configured in the observed list.
- Beads already has decision/message/event fields, timer gates and an HTTP API, but HTTP mutations deliberately skip the CLI hooks. Stored gates do not evaluate themselves.
- Windmill CE already hosts a typed-answer inbox, yet the public built-in approval-form feature is edition-limited; timeout cancellation and choosing a default are separate mechanisms.
- The configured Claude gateway excludes native Remote Control, and a seemingly isolated second settings argument erased the probe's authentication route. Codex still consumed about 13.9k input tokens for a one-line response with ambient discovery disabled.
