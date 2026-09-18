# Orca session recovery ledger — snapshot 2026-07-31 11:20 PDT

Audience: the orchestration agent that picks up after the planned full computer restart.
You should not need this. Read it only when a pane comes back without its conversation.

Companion review page: <https://connelly.leadory.net/orca-restart-restore-audit/>
Short re-attach table (at-risk panes only): `docs/orca-restart-reattach-2026-07-31.md`

---

## 0. Snapshot provenance

Every claim below was derived at write time from live state, not recalled:

| Fact | Value | Source |
|---|---|---|
| Snapshot taken | 2026-07-31 ~11:20 PDT | this session |
| Last machine boot | 2026-07-22 14:44:44 | `launchd` (pid 1) start time |
| Orca app version | 1.4.162, pid 97654 | `orca status --json` |
| Orca daemon generations alive | v25, v26, v28, v29, v30 | `ps` + `~/Library/Application Support/orca/daemon/` |
| Live agent panes | 30 (18 claude, 12 codex) | `ps` + `ORCA_PANE_KEY` in each process env |
| Panes with an Orca resume record | 19 | `sleepingAgentSessionsByPaneKey` |
| Panes with **no** resume record | 11 | same |
| Live agent-hook endpoint | `127.0.0.1:54317` only | `lsof -nP -iTCP -sTCP:LISTEN` |
| Panes still able to report status | 9 of 30 | hook token in process env == current token |

Raw evidence files (all still on disk, re-derive from these if this doc looks stale):

- Resume ledger: `~/Library/Application Support/orca/profiles/local-default/orca-data.json` &rarr; `workspaceSession.sleepingAgentSessionsByPaneKey` (hourly backups `orca-data.json.bak.0`…`.4` in the same dir)
- Hook status sink: `~/Library/Application Support/orca/agent-hooks/last-status.json` &rarr; `entries[<paneKey>].providerSession`
- Claude transcripts: `~/.claude/projects/<dashified-cwd>/<session-id>.jsonl`
- Codex rollouts: `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` **and** `~/Library/Application Support/orca/codex-runtime-home/home/sessions/…` (two homes — check both)
- Per-pane scrollback: `~/Library/Application Support/orca/terminal-history/<url-encoded ptyId>/output.log`

---

## 1. How Orca restore actually works

Read this before touching anything; it explains what will and will not come back.

1. **The resume record is the only thing that matters.** Orca stores one record per pane in `sleepingAgentSessionsByPaneKey`: agent type, launch config, and `providerSession = {key: "session_id", id, transcriptPath}`. No record &rarr; the pane relaunches as a brand-new agent.
2. **Relaunch argv** is built by agent type: claude &rarr; `claude --resume <id>`; codex &rarr; `codex resume <id>`; gemini/grok/droid/devin &rarr; `--resume`; opencode/pi/kimi &rarr; `--session`; antigravity &rarr; `--conversation`.
3. **Codex resume is verified first.** Orca resolves which `CODEX_HOME` holds the rollout and prefixes it. If the rollout cannot be verified it **drops the resume argv and starts a fresh Codex**, with a "resume unavailable" notice — it does not error out. So a silently-fresh Codex pane is the expected failure mode, not a crash.
4. **Capture cadence:** a periodic pass every ~18 minutes for panes that still report status, plus one pass on graceful quit. The quit pass **skips any pane already in `done` state that has no prior record.**
5. **Capture is hook-driven.** A pane can only be captured if its agent can POST to the live hook endpoint. Panes launched under an earlier Orca instance carry a dead `ORCA_AGENT_HOOK_PORT` and are permanently frozen — prompting them does not help.
6. **Wake is per worktree.** On relaunch Orca re-activates the worktrees listed in `workspaceSession.activeWorktreeIdsOnShutdown` and wakes their agents; other worktrees resume when opened. Experimental idle hibernation is **off** (`settings.experimentalAgentHibernation = false`).
7. **Daemons, not the app, own the PTYs.** Five daemon generations were alive at snapshot time, which is why agents survived Orca app restarts without any resume. A reboot removes that safety net entirely.

---

## 2. First thing to do after the reboot

```bash
orca status --json                 # runtime ready?
orca worktree ps --json            # which worktrees + agent panes came back
orca terminal list --json          # live PTYs
ps -Ao pid,lstart,command | grep -E "(^| )(claude|codex)"   # what argv each agent got
```

**A pane resumed correctly if its argv contains `--resume <id>` (claude) or `resume <id>` (codex)** matching the id in the tables below. A pane that came back as bare `claude …` / `codex --model …` with no resume token did **not** restore its conversation.

---

## 3. Panes with NO resume record — expect these to come back empty (11)

| # | Agent | Worktree path | Orca worktree id | Pane title | Started | Session id to re-attach | Id source |
|---|-------|---------------|------------------|-----------|---------|------------------------|-----------|
| 1 | claude | `/Users/changlee/orca/workspaces/claude/gather-leads-v2` | `21b41371-e1ee-480f-9c8a-88e1d5c41e13::/Users/changlee/orca/workspaces/claude/gather-leads-v2` | (untitled) | 2026-07-24 16:56 | `65cee90f-07af-4af8-831c-7c88bf99d505` | argv --resume |
| 2 | claude | `/Users/changlee/projects/agent-annotate/codex` | `07771d76-bc16-4702-bec1-9d2a809f0146::/Users/changlee/projects/agent-annotate/codex` | (untitled) | 2026-07-26 00:57 | `1f6c7f37-d0d3-4db1-af24-5ce9e272bf50` | argv --resume |
| 3 | claude | `/Users/changlee/projects/agent-annotate/codex` | `07771d76-bc16-4702-bec1-9d2a809f0146::/Users/changlee/projects/agent-annotate/codex` | (untitled) | 2026-07-26 00:57 | `0614b174-cc56-4358-bc02-022538f01d48` | argv --resume |
| 4 | claude | `/Users/changlee/projects/agent-annotate/codex` | `07771d76-bc16-4702-bec1-9d2a809f0146::/Users/changlee/projects/agent-annotate/codex` | ✳ Update and verify RTK plugin across  | 2026-07-30 11:52 | `866a45e2-4e6b-4072-b7e2-2426f91eb3bc` | transcript-birth-match |
| 5 | claude | `/Users/changlee/projects/agent-annotate/codex` | `07771d76-bc16-4702-bec1-9d2a809f0146::/Users/changlee/projects/agent-annotate/codex` | (untitled) | 2026-07-24 12:49 | `1f6c7f37-d0d3-4db1-af24-5ce9e272bf50` | argv --resume |
| 6 | claude | `/Users/changlee/projects/connelly/claude` | `21b41371-e1ee-480f-9c8a-88e1d5c41e13::/Users/changlee/projects/connelly/claude` | (untitled) | 2026-07-24 16:51 | `9d4210a3-2ef1-40da-a429-0ece67219ec8` | argv --resume |
| 7 | claude | `/Users/changlee/projects/connelly/claude` | `21b41371-e1ee-480f-9c8a-88e1d5c41e13::/Users/changlee/projects/connelly/claude` | (untitled) | 2026-07-24 21:20 | `1494262b-582e-49b7-bdbd-727fe666544a` | argv --resume |
| 8 | claude | `/Users/changlee/projects/connelly/claude` | `21b41371-e1ee-480f-9c8a-88e1d5c41e13::/Users/changlee/projects/connelly/claude` | (untitled) | 2026-07-24 21:20 | `26ab89eb-503c-4dc3-87f5-65cae032fda9` | argv --resume |
| 9 | claude | `/Users/changlee/projects/connelly/claude` | `21b41371-e1ee-480f-9c8a-88e1d5c41e13::/Users/changlee/projects/connelly/claude` | (untitled) | 2026-07-25 00:06 | `26ab89eb-503c-4dc3-87f5-65cae032fda9` | argv --resume |
| 10 | codex | `/Users/changlee/projects/leadory/leadory-codex-a0la-live-denominator-audit-v1` | `485d68c2-47c2-4446-abe3-279c4247ea43::/Users/changlee/projects/leadory/leadory-codex-a0la-live-denominator-audit-v1` | a1se3-context-builder | 2026-07-26 13:25 | **none found** | - |
| 11 | codex | `/Users/changlee/projects/leadory/leadory-codex-a0la-live-denominator-audit-v1` | `485d68c2-47c2-4446-abe3-279c4247ea43::/Users/changlee/projects/leadory/leadory-codex-a0la-live-denominator-audit-v1` | a1se3-context-builder | 2026-07-26 13:25 | **none found** | - |

### Re-attach commands

1. `cd /Users/changlee/orca/workspaces/claude/gather-leads-v2` &rarr; `claude --dangerously-skip-permissions --resume 65cee90f-07af-4af8-831c-7c88bf99d505`
2. `cd /Users/changlee/projects/agent-annotate/codex` &rarr; `claude --dangerously-skip-permissions --resume 1f6c7f37-d0d3-4db1-af24-5ce9e272bf50`
3. `cd /Users/changlee/projects/agent-annotate/codex` &rarr; `claude --dangerously-skip-permissions --resume 0614b174-cc56-4358-bc02-022538f01d48`
4. `cd /Users/changlee/projects/agent-annotate/codex` &rarr; `claude --dangerously-skip-permissions --resume 866a45e2-4e6b-4072-b7e2-2426f91eb3bc`
5. `cd /Users/changlee/projects/agent-annotate/codex` &rarr; `claude --dangerously-skip-permissions --resume 1f6c7f37-d0d3-4db1-af24-5ce9e272bf50`
6. `cd /Users/changlee/projects/connelly/claude` &rarr; `claude --dangerously-skip-permissions --resume 9d4210a3-2ef1-40da-a429-0ece67219ec8`
7. `cd /Users/changlee/projects/connelly/claude` &rarr; `claude --dangerously-skip-permissions --resume 1494262b-582e-49b7-bdbd-727fe666544a`
8. `cd /Users/changlee/projects/connelly/claude` &rarr; `claude --dangerously-skip-permissions --resume 26ab89eb-503c-4dc3-87f5-65cae032fda9`
9. `cd /Users/changlee/projects/connelly/claude` &rarr; `claude --dangerously-skip-permissions --resume 26ab89eb-503c-4dc3-87f5-65cae032fda9`
10. `cd /Users/changlee/projects/leadory/leadory-codex-a0la-live-denominator-audit-v1` &rarr; `codex` then pick from the in-CLI session list
11. `cd /Users/changlee/projects/leadory/leadory-codex-a0la-live-denominator-audit-v1` &rarr; `codex` then pick from the in-CLI session list

Or spawn the resumed agent straight into an Orca pane (preferred — keeps it inside the worktree UI):

```bash
orca terminal create --worktree id:<worktreeId> --title "<title>" \
  --command 'claude --dangerously-skip-permissions --resume <id>' --json
```

---

## 4. Panes WITH a resume record — verify these landed on the right session (19)

| # | Agent | Worktree path | Pane title | Recorded session id | Captured | Confidence |
|---|-------|---------------|-----------|---------------------|----------|-----------|
| 1 | codex | `/Users/changlee/projects/connelly/codex` | Codex ready | `019f95ed-6c31-7691-ae5d-b69441c36d9b` | 07-31 10:40 | **STALE — points at an older session** |
| 2 | claude | `/Users/changlee/orca/workspaces/claude/g9-alerting-and-emission-followups` | ✳ Takeover: G9 poller gcloud error | `c5ac672e-675d-419d-a75b-474c1d6a3b63` | 07-31 10:22 | transcript exists, attribution not cross-checked |
| 3 | claude | `/Users/changlee/orca/workspaces/claude/postgres-incident-wave1-followups` | ✳ Postgres incident wave-1 followu | `f224787a-f9ab-4889-ae8c-118d6850c288` | 07-31 10:05 | transcript exists, attribution not cross-checked |
| 4 | claude | `/Users/changlee/orca/workspaces/codex/luc-stage2-control-plane-v2` | ✳ LUC-900 Stage 2 control-plane co | `d6053bb1-42ea-4b07-a63d-89b40c840ec4` | 07-30 13:08 | transcript exists, attribution not cross-checked |
| 5 | claude | `/Users/changlee/projects/agent-annotate/codex` | ✳ Assume annotate manager role and | `48c2536a-bce8-4fcd-a012-13b1f67494ed` | 07-30 21:09 | transcript exists, attribution not cross-checked |
| 6 | claude | `/Users/changlee/projects/agent-annotate/codex` | ⠂ Verify Orca session restore afte | `6d872667-02c9-4654-a90b-647be239be7b` | 07-31 11:13 | verified — matches the session the process actually created |
| 7 | claude | `/Users/changlee/projects/agent-annotate/codex` | ✳ Check if sessions resume after O | `cf75b938-d833-49e6-9688-1f40eefe2606` | 07-30 11:43 | verified — matches the session the process actually created |
| 8 | claude | `/Users/changlee/projects/connelly/claude` | (untitled) | `d56f835e-9198-4ac2-8549-8eb4f1f364f8` | 07-26 13:16 | verified — matches the session the process actually created |
| 9 | claude | `/Users/changlee/projects/connelly/claude` | (untitled) | `26ab89eb-503c-4dc3-87f5-65cae032fda9` | 07-25 12:53 | transcript exists, attribution not cross-checked |
| 10 | claude | `/Users/changlee/projects/connelly/claude` | (untitled) | `94cd2640-88c6-4637-b970-54d1fc7937e1` | 07-26 12:17 | verified — matches the session the process actually created |
| 11 | codex | `/Users/changlee/projects/leadory/codex` | (untitled) | `019fa07e-8b30-7271-8059-3b4b33c6c1a2` | 07-26 15:34 | verified — matches the session the process actually created |
| 12 | codex | `/Users/changlee/projects/leadory/codex` | (untitled) | `019fa07c-9fd6-7a13-af69-c7a20b6c556a` | 07-26 15:38 | verified — matches the session the process actually created |
| 13 | codex | `/Users/changlee/projects/leadory/codex` | codex | `019fb8f8-1a4c-7ed2-87f4-7266539cf807` | 07-31 09:37 | verified — matches the session the process actually created |
| 14 | codex | `/Users/changlee/projects/leadory/codex` | RTPR-SEC B3-Y G8-G9 verification | `019fa073-3cf7-7400-842d-55ef22c77b40` | 07-26 15:25 | verified — matches the session the process actually created |
| 15 | codex | `/Users/changlee/projects/leadory/codex` | (untitled) | `019fa074-569f-7983-84f8-eca03f0d119c` | 07-26 15:39 | verified — matches the session the process actually created |
| 16 | codex | `/Users/changlee/projects/leadory/codex` | codex | `019fb8fe-597b-7443-b0e1-729d46a5421c` | 07-31 09:37 | verified — matches the session the process actually created |
| 17 | codex | `/Users/changlee/projects/leadory/codex` | codex | `019fb902-2e40-7970-a399-c1e534527269` | 07-31 09:36 | verified — matches the session the process actually created |
| 18 | codex | `/Users/changlee/projects/leadory/codex` | codex | `019f9d7f-0ed0-7c32-b446-8fd62fafcc48` | 07-31 09:39 | verified — matches the session the process actually created |
| 19 | codex | `/Users/changlee/projects/leadory/codex` | codex | `019fb6dd-146d-7313-8fa7-da17616d5a2c` | 07-31 02:54 | verified — matches the session the process actually created |

---

## 5. Known traps

1. **One recorded id is wrong.** Worktree `/Users/changlee/projects/connelly/codex` has recorded id `019f95ed-6c31-7691-ae5d-b69441c36d9b` (Jul 24), but the process running at snapshot time created `019f9aa9-29b1-7611-82a7-e7f6054779e9` (Jul 25 12:03). Orca will resume the older conversation. Correct it with `codex resume 019f9aa9-29b1-7611-82a7-e7f6054779e9`.
2. **Duplicate session ids.** Two panes each hold `1f6c7f37-d0d3-4db1-af24-5ce9e272bf50`, and two hold `26ab89eb-503c-4dc3-87f5-65cae032fda9` — earlier handoffs resumed one transcript into two panes. Re-attach **one** pane per id; a second `--resume` on the same id appends to the same file and the two panes will fight over it.
3. **Two panes have no session at all.** Both `a1se3-context-builder` panes in `leadory-codex-a0la-live-denominator-audit-v1` produced no rollout — they never took a prompt. Nothing to recover; start them fresh.
4. **Codex has two homes.** If `codex resume <id>` says the session is unknown, retry with `CODEX_HOME="$HOME/Library/Application Support/orca/codex-runtime-home/home" codex resume <id>`. At snapshot time 4 sessions lived only in that second home.
5. **Orca's own status display may lie.** 21 of 30 panes carry a dead hook port, so their `state` in `orca worktree ps` is frozen at whenever they last reported. Do not treat `state: "done"` as proof a pane is idle — read the terminal.
6. **Never hand-edit `orca-data.json`.** Orca rewrites it from renderer state; an edit is silently clobbered and can corrupt the workspace session. Fix a wrong session by re-attaching in the terminal instead.
7. **Do not kill panes to "clean up".** The LUC-900 Stage 2 coordinator pane (worktree `luc-stage2-control-plane-v2`) was launched with a standing instruction in its own argv: *"Do not close any old Connelly panes; two degraded panes contain unexplained unsent input and are forensic evidence."* That instruction is still in force. Read a pane before closing it.

---

## 6. Finding a session id from scratch (if this ledger is stale)

**Claude Code** — transcripts are one file per session, named by session id:

```bash
ls -lt ~/.claude/projects/$(echo "$PWD" | sed "s|/|-|g")/*.jsonl | head
# or just: claude --resume       (opens a picker scoped to the current directory)
```

**Codex** — rollouts are dated, and the session id is the tail of the filename:

```bash
ls -lt ~/.codex/sessions/2026/*/*/rollout-*.jsonl | head
ls -lt "$HOME/Library/Application Support/orca/codex-runtime-home/home"/sessions/2026/*/*/rollout-*.jsonl | head
# or just: codex                 (the CLI lists resumable sessions)
```

**Attribution trick that worked here:** a rollout / transcript created within ~180 s of a pane process start time, in that pane's cwd, is that pane's session. Process start times come from `ps -Ao pid,lstart,command`. Do **not** attribute by grepping a tab id out of transcript text — agents paste tab ids into conversations and that produces false matches.

---

## 7. What "done" looks like

- Every worktree that mattered before the reboot is open in Orca.
- Each pane in section 4 shows resume argv with the id listed there (or a corrected id).
- Each pane in section 3 has either been re-attached with its listed id, or deliberately left fresh.
- `orca worktree ps --json` agent count is back at 30, or the difference is accounted for in writing.

---

## 8. Post-reboot outcome — verified 2026-07-31 12:00 PDT

The reboot happened at **11:47:01**. This section records what actually came back, so a
successor does not have to re-derive it.

**Restore: clean.** Workspace structure returned identical — 21 tabs, 21 tab groups, 29
Orca-tracked agent panes, same pane keys before and after, none lost and none invented.
The resume ledger survived the power cycle: 27 records before, 26 after. The one delta is
`cf75b938`, and that pane is running on that exact id — **Orca deletes a record when it
consumes it to wake a session**, so a missing record for a pane that is currently live is
normal, not a loss. Eight orphaned `terminalLayoutsByTabId` entries were garbage-collected;
all eight belonged to dead orchestration workers that already had no tabs.

**Resume: works.** Of the four panes woken so far (all in `agent-annotate/codex`, the only
worktree opened):

| Pane | Had a record | Result |
|---|---|---|
| `48c2536a-bce8-4fcd-a012-13b1f67494ed` | yes | relaunched `claude --resume 48c2536a…` — correct |
| `cf75b938-d833-49e6-9688-1f40eefe2606` | yes | relaunched `claude --resume cf75b938…` — correct |
| `6d872667-02c9-4654-a90b-647be239be7b` | yes | relaunched `claude --resume 6d872667…` — correct, full prior conversation intact |
| `63206350…:77f4ddd5…` ("Update and verify RTK plugin…") | **no** | came back as `Terminal 3`, bare shell, no agent — the predicted failure, reproduced exactly |

Re-attach for that last one: `claude --dangerously-skip-permissions --resume 866a45e2-4e6b-4072-b7e2-2426f91eb3bc`

**Everything else is dormant, not lost.** Orca wakes agents per worktree on open, so 26
panes are still asleep across 8 unopened worktrees. Of those, 16 hold a valid record and
will resume; 10 hold none and will come back as empty shells — see section 3 for their ids.

A periodic capture pass already ran post-boot (latest record stamped 11:53:51), so the
woken panes are protected again for the next restart.

**Gap found in this document:** sections 3 and 4 identify panes by worktree + title +
start time, not by pane key. That was enough here, but pane key (`<tabId>:<leafId>`) is the
only stable join key against `sleepingAgentSessionsByPaneKey`. If you regenerate this
ledger, include it. The pre-reboot ledger itself is recoverable from the hourly backups
`orca-data.json.bak.0`…`.4` in the profile dir, which is how the before/after diff above
was done.

---

## 9. Automating the wake (added 2026-07-31 12:10 PDT)

Orca has **no** "resume all agents at launch" setting — the whole app bundle contains no
such preference. Resume fires only when a worktree becomes active. That activation is
scriptable:

```bash
orca file open <any-file-in-the-worktree> --worktree id:<repoId>::<worktreePath> --json
```

Proven live: running that against the dormant `g9-alerting-and-emission-followups`
worktree relaunched `claude --dangerously-skip-permissions --resume c5ac672e-…` at
12:03:24. Orca builds the resume command itself — nothing hand-edits Orca state.

**Tooling installed:**

- `~/.local/bin/orca-resume-sessions.py`
  - `check` (default) — per-worktree record inventory, which will resume, which are
    blocked and why, plus a capture-health line counting panes on a stale hook endpoint.
  - `wake` — waits for the runtime, activates each worktree holding a record, then
    verifies by matching resume ids against running processes. Exits 2 if any expected
    session did not come back. Supports `--dry-run`, `--exclude <substring>`, `--wait`,
    `--settle`.
- `~/Library/LaunchAgents/com.leadory.orca-resume-sessions.plist` — runs `wake` at login,
  600 s grace for Orca to start. **Written and lint-clean but deliberately NOT loaded.**
  Enable: `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.leadory.orca-resume-sessions.plist`

**Orca's resume gating** — activation drops a record instead of resuming it when any hold
(the script mirrors these, so `check` predicts it):

1. `interrupted === true`
2. no `origin` and `state === "done"`
3. `state !== "done"` and `capturedAt - updatedAt > 1_800_000` (status frozen >30 min)
4. `origin` is neither `quit` nor `live` and `state === "done"` (passive completed evidence)

All 26 records present at the time of writing pass all four.

**Two things to know before enabling it:**

- Activating `/Users/changlee/projects/leadory/codex` resumes **17** panes, not 9. Eight of
  its records belong to finished orchestration workers whose tabs no longer exist, and
  `launchSleepingAgentSession` creates a fresh tab per record. None carries
  `automaticResumeBlockedBy`, so nothing suppresses them. Use
  `--exclude /projects/leadory/codex` to avoid it.
- The stale-hook debt that caused the 11 empty panes is currently **zero** — every live
  pane is on the current endpoint. It rebuilds whenever Orca restarts while panes keep
  running, because each app instance mints a new hook port and older panes can never
  report again. `orca-resume-sessions.py check` reports the count; a non-zero number means
  those panes will be lost at the next reboot unless they are restarted first.
