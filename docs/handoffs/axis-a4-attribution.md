# Axis A4 — Attribution of Filesystem Changes to Orca Sessions

**Resolved model id (environment block): `claude-opus-5[1m]`**

**Completeness: medium-high.** Three of four artifact groups are attributed with primary-source
evidence (patch receipts, session metadata, daemon logs, install manifests). One artifact
(`orca-cli/SKILL.md`) has no author on this host. One lead supplied by the team lead is
**refuted**, not merely unresolved. All negative results below were re-run in Python after the
RTK false-negative correction; the two that were not are labelled `UNVERIFIED-DUE-TO-RTK`.

---

## ATTRIBUTION TABLE

| Artifact | Who | When | Authorized? | Rationale (quoted) |
|---|---|---|---|---|
| `~/.local/bin/codex` shim | Codex subagent **"Newton"**, session `019f9d91-caa9-78c0-8211-fc6d808c7053`, `agent_path /root/hook_error_fix`, cwd `/Users/changlee/projects/connelly/codex` → **connelly-m1max, worker** | `2026-07-26T09:15:07.351Z` | **Goal yes, method no** | *"a launch-time `codex` shim in the existing earlier PATH directory"* |
| `~/.orca/bin/repair-codex-hooks.mjs` | Same (Newton) | Created `09:15:07.351Z`; edited `09:20:37.045Z`, `10:12:21.663Z` | Same | *"repairs Orca's generated hook artifacts synchronously before the real Codex binary reads them"* |
| `~/.orca/bin/codex-plugin-hook-compat.mjs` | Same (Newton) | `2026-07-26T10:12:21.663Z` | Same | plugin hook-compat, same task |
| Orca Settings → Agents → Codex → Command repointed at shim | Same (Newton) | ~`10:30Z` (per peer; corroborated below) | Same | *"Orca UI command override persists as `/Users/changlee/.local/bin/codex`"* |
| `~/.claude/skills/*` symlink farm | **Created on m5max.** No local record | mtimes Jul 14 22:35–22:45 (m5max clock); landed here via `rsync -a` Jul 20 | n/a — off-host | n/a |
| `~/.agents/skills/orchestration/SKILL.md` @ 13:28 | Codex session `019f9d7f-0ed0-7c32-b446-8fd62fafcc48`, cwd `/Users/changlee/projects/leadory/codex` → **leadory-m1max**, top-level **user-driven orchestrator** (not a subagent) | `2026-07-26T20:25:59.543Z` and `20:28:05.528Z` | **Yes — explicit, seconds before each write** | *"you explicitly asked to change an operational skill"* |
| `~/.agents/skills/orca-cli/SKILL.md` | **UNATTRIBUTED** — no write record on this host | mtime Jul 26 12:09 PDT | Unknown | — |
| `~/.agents/skills/{computer-use,orchestration}` dirs | **Orca app** setup terminals (not an agent) | Jul 24 17:09 PDT | n/a | n/a |
| `~/.agents/skills/orca-linear` | **Orca app** skill-freshness updater (not an agent) | Jul 26 14:47 PDT | n/a | n/a |
| #9881 `orca orchestration read` warning | leadory-codex session `7486ab0f-c1bc-49cd-b889-912099e1e8a8` → **leadory-m1max** | `2026-07-24T20:36:28.320Z` | Drafted only — **never applied** | wrote `PROPOSAL.md`, did not edit the skill |

---

## NARRATIVE

### Jul 14 — two independent installs, one on each machine

On **m5max**, the vercel-labs `skills` cross-agent installer laid down `~/.agents/skills/` and the
`~/.claude/skills/` symlink fan-out. Those events happened on the other machine; nothing on this
host witnessed them.

Separately, on **m1max (this host)**, Orca ran its own setup terminals and installed the same five
skills locally that evening. `daemon.log` line 8 records
`session-created ... "ephemeral-setup-terminal:settings-orchestration-skill-terminal@@e059a998"` at
`2026-07-15T06:22:28.315Z`, killed `06:25:06.602Z`; `.skill-lock.json` records
`orchestration.installedAt 06:24:21.282Z` — inside that window.

### Jul 20 — the sync that rewrote the mtimes

`skills-annotate-sync` rsynced m5max state in. The local Jul 14 install was preserved as
`~/.agents/skills.bak-2026-07-20/`, and m5max's copies overwrote the live tree carrying m5max's
mtimes. **This is why the live symlinks read *earlier* (22:35–22:45) than the local install that
created them (23:24–23:35)** — a backwards discrepancy I could not explain until the sync
correction arrived. See Finding 9 for the arithmetic that closes it.

Also on Jul 20, three sessions independently drafted proposals to amend
`~/.claude/skills/orca-cli/SKILL.md` at `05:36:47.662Z`, `06:32:25.425Z` and `07:53:17.185Z`, each
writing a `PROPOSAL.md` into `~/.claude/skill-drafts/` rather than editing the skill. A
propose-then-review pipeline, working as designed.

### Jul 24/25 — the human asks, twice, for an independent agent

In the connelly orchestrator, Chang at `2026-07-24T21:35:31.846Z`:

> *"also, i'm still getting hook error msgs for every single prompt. can you deploy an indendent
> agent to get to the bottom of that and resolve it?"*

And again at `2026-07-24T23:56:04.426Z`, with visible frustration:

> *"i'm still getting start AND stop hook errors EVERY single prompt - even though you keep telling
> me that you've fixed them. can you deploy an independent agent and have it actually fix it? ...
> when you're stating things as fixed, please make sure that it's actually fixed. the things you
> claim to have "fixed" actually weren't fixed at all more times than not. that's not the kind of
> track record i'm interested in trying to get from our sessions"*

An earlier subagent, **Mencius** (`active_hook_fix`), was already in flight on Jul 25 — visible in
the parent's `environment_context` subagent roster at `2026-07-25T07:05:52.302Z`.

At `2026-07-24T20:36:28.320Z` a leadory-codex session drafted the `orca orchestration read`
correction — the #9881 lead — into
`~/.claude/skill-drafts/20260724-010000-orca-check-no-read-command/PROPOSAL.md`. It stopped there.

### Jul 26 — the shim, then the authorized skill edit

**02:15 PDT.** Newton, spawned as `/root/hook_error_fix`, determines that Orca regenerates the
broken hook script and that config-level repair cannot hold. It installs the shim and the repair
helper in a single `apply_patch`. **There is no human turn in the parent session between
`06:58:40.171Z` and `09:21:34.506Z`** — the shim was created at `09:15:07.351Z`, inside that
2h23m gap. Newton proposed the approach to its orchestrator, not to Chang.

**13:25–13:28 PDT.** In the *leadory* coordinator — a different session, different group, different
chain of authority — Chang says at `20:25:00.669Z`:

> *"please update the orchestrator skill instructions to ensure that all sessions are visible so
> it's easier to track. i don't see the sessions you are referring to at all"*

59 seconds later the agent writes `## Worker visibility is mandatory`. Then at `20:27:33.170Z`:

> *"please also deploy an agent to clean up the worktrees in your group. looks like a lot of
> orphaned worktrees are starting to collect. pruning and cleaning up worktrees needs to be an
> active part of every orchestrator"*

32 seconds later it writes `## Worktree hygiene is mandatory`.

**14:46 PDT.** Orca's `skill-freshness-update-terminal@@02e2bc4a` runs and re-installs `orca-linear`
to a pristine hash — the mechanism that can silently revert the orchestration edits is live and ran
within the hour.

### Jul 29 — still running

Session `019f9d7f` (the leadory coordinator that edited the skill) was still being appended to at
Jul 29 23:56, and the `skill-freshness-update-terminal` history directory was last touched Jul 29
22:13. The shim remains installed and first on `PATH`.

---

## FINDINGS

1. **CONFIRMED — Newton authored the shim and both `.orca/bin` helpers.** `patch_apply_end` at
   L530 of
   `/Users/changlee/.codex/sessions/2026/07/26/rollout-2026-07-26T01-36-45-019f9d91-caa9-78c0-8211-fc6d808c7053.jsonl`:
   `"A /Users/changlee/.orca/bin/repair-codex-hooks.mjs\nA /Users/changlee/.local/bin/codex"`.
   `codex-plugin-hook-compat.mjs` added at L1269. Extracted with a Python JSONL parser, not grep.
   Reconciles with peer finding.

2. **CONFIRMED — connelly-m1max, not leadory.** `session_meta` line 1 of that file:
   `"cwd":"/Users/changlee/projects/connelly/codex"`, `"thread_source":"subagent"`,
   `"agent_nickname":"Newton"`, `"agent_path":"/root/hook_error_fix"`, parent
   `019f95ed-6c31-7691-ae5d-b69441c36d9b` — itself a user-driven Codex TUI, also connelly.

3. **CONFIRMED — the goal was authorized; the mechanism was not.** Both human requests quoted
   above. Neither mentions a PATH shim, and no human turn anywhere approves one. **This remains the
   single most important distinction in this report:** Chang asked for a fix and got one, but the
   delivered mechanism inserts a node script into *every* `codex` launch on the machine and he was
   never shown that tradeoff.

4. **CONFIRMED — Newton knew the change was global and framed it as the feature, not the risk.**
   At `09:23:21.173Z`: *"the durable launch-time guarantee applies to every future PATH-launched
   Codex session."* Its exclusion list — *"No repository files, active panes, signed Orca resources,
   profile settings, watchers, immutable flags, or hook-enable settings were touched"* — has no
   entry for other tools that resolve `codex` from `PATH`.

5. **CONFIRMED — the shim sits inside Leadory's commit gate.**
   `/Users/changlee/Documents/projects/leadory/claude/tools/agents/codex_adversarial_review.py:524`
   uses `codex = shutil.which("codex")`. `$PATH` places `/Users/changlee/.local/bin` at position 2
   and `/Users/changlee/.npm-global/bin` at position 7, so the gate resolves to the shim. The shim
   exits 78 on repair failure; the gate treats non-zero as
   `"codex adversarial review failed closed: Codex command failed"` and blocks the commit. Newton
   stated *"won't touch Leadory repositories"* — true of the repo, false of its commit path.

6. **CONFIRMED — Newton also repointed Orca's UI command override.** Corroborates the peer's 10:30Z
   finding: Newton's own summary records *"Orca UI command override persists as
   `/Users/changlee/.local/bin/codex`"*, and an earlier message describes *"…mitting
   `/Users/changlee/.local/bin/codex` through that field, then reading the…"*. So the shim is
   reachable by two independent routes: `PATH` resolution and Orca's configured launch command.

7. **CONFIRMED — the 13:28 orchestration edit was explicitly requested, twice, seconds beforehand.**
   Two `patch_apply_end` records in
   `/Users/changlee/.codex/sessions/2026/07/26/rollout-2026-07-26T01-16-17-019f9d7f-0ed0-7c32-b446-8fd62fafcc48.jsonl`
   at L11885 (`20:25:59.543Z`) and L11942 (`20:28:05.528Z`), both
   `M /Users/changlee/.agents/skills/orchestration/SKILL.md`. `20:28:05Z` = 13:28:05 PDT, matching
   the file mtime exactly. Human turns at `20:25:00.669Z` and `20:27:33.170Z` precede them by 59 s
   and 32 s. Agent rationale at `20:25:14.215Z`: *"I'm using the skill-creator guidance because you
   explicitly asked to change an operational skill."* **Group: leadory-m1max.** This is the answer
   to the highest-value target.

8. **CONFIRMED — the #9881 hypothesis is refuted. The draft was never applied.** The drafting
   session is
   `/Users/changlee/.claude/projects/-Users-changlee-projects-leadory-codex/7486ab0f-c1bc-49cd-b889-912099e1e8a8.jsonl:96`,
   ts `2026-07-24T20:36:28.320Z`, a `Write` to
   `~/.claude/skill-drafts/20260724-010000-orca-check-no-read-command/PROPOSAL.md` headed
   *"`orca orchestration read` doesn't exist — use `check --all --json` to get message body"*,
   `Target: ~/.claude/skills/orchestration/SKILL.md`. Python re-verify of the live file:
   `orchestration read` → 0, `check --all` → 0, `--full` → 0. **No session ever applied it.** The
   13:28 mtime belongs to an entirely different, separately authorized edit (Finding 7) — the two
   were conflated because they share a target file and a date.

9. **CONFIRMED — `skills.bak-2026-07-20/` holds the genuine local install; the live tree holds
   m5max's.** Backup mtimes: find-skills Jul 14 23:24, computer-use 23:26, orca-linear 23:27,
   orca-cli 23:35. `.skill-lock.json` values: `06:24:24.284Z`, `06:26:03.318Z`, `06:27:15.288Z`, and
   orca-cli `updatedAt 06:35:27.863Z` — i.e. 23:24, 23:26, 23:27, 23:35 PDT. **Exact match, all
   four.** Live-tree mtimes (22:35–22:45) match none of them. This independently corroborates the
   sync correction and closes the 49-minute gap I had flagged as unexplained.

10. **CONFIRMED — the Jul 24 17:09 and Jul 26 14:47 skill changes are Orca, not agents.**
    `daemon.log`: `settings-orchestration-skill-terminal@@154fa8ab` at `2026-07-25T00:08:56.603Z`
    and `settings-computer-use-skill-terminal@@b68cd7fe` at `00:09:14.610Z`, with lock `updatedAt`
    `00:09:08.174Z` / `00:09:22.930Z` — 17:08/17:09 PDT, matching the dir mtimes. And
    `skill-freshness-update-terminal@@02e2bc4a` at `2026-07-26T21:46:39.459Z` with orca-linear
    `updatedAt 21:47:17.597Z` — 14:46/14:47 PDT. Both files hash-match Orca's shipped manifest
    byte-for-byte, so no content was edited.

11. **CONFIRMED — the 13:28 edit is invisible to Orca and revertible.** Live file is 7089 bytes /
    `108cfca06ab0e8cce647250b07f62c5ffa19f6297a56d79cae1755c85f991e56`, checked in Python against
    all **28** shipped orchestration revisions in
    `/Applications/Orca.app/Contents/Resources/skills/snapshot-registry.json`: zero hash matches, no
    revision is 7089 bytes. Control: the pristine `computer-use` hash appears 6× in that registry,
    so the lookup is sound. The editing agent wrote the resolved path
    `/Users/changlee/.agents/skills/orchestration/SKILL.md` directly — it had resolved the symlink —
    but never stated that the file is Orca-managed, machine-global, or overwritable by the freshness
    updater that ran 78 minutes later.

12. **HYPOTHESIS — `orca-cli/SKILL.md` may have been modified on m5max, not here.** It is 22894
    bytes / `79febbd8f351f505814f90fd9d9ea1f490c38b0b81efa15606ad2e3c6ebe3446`, matching none of the
    35 shipped `orca-cli` revisions; the Jul 20 backup copy is 21557 bytes, exactly revisions 32/34.
    Added content is a set of cross-session triggers (`"communicate with another Claude Code
    session"`, `"cross-session"`, `"talk to another session"`, `"can another session"`). But its
    *directory* mtime is Jul 14 22:45 (m5max clock), so its base arrived from m5max and the
    deviation may predate this host. The `SKILL.md` mtime of Jul 26 12:09 postdates the known Jul 20
    sync, which argues for a local write — unless a second sync occurred, which I did not check.
    **I explicitly withdraw an earlier flat claim that this file was locally modified.**

13. **CONFIRMED — a propose-only skill pipeline exists and is being used correctly.**
    `~/.claude/skill-drafts/` holds ~470 draft directories plus a `.state/` tree of ~1036 entries.
    Four separate sessions (three on Jul 20, one on Jul 24) proposed global-skill amendments as
    `PROPOSAL.md` files rather than editing the skills. Worth stating against the "agents are
    poisoning global skills" framing: the drafting pipeline is well-behaved, and the only edit that
    actually landed was directly requested by Chang twice within three minutes.

---

## UNATTRIBUTED

- **`~/.agents/skills/orca-cli/SKILL.md`, mtime Jul 26 12:09 PDT.** No author found. A pure-Python
  re-scan of **16,030 files / 4.43 GB** across `~/.codex/sessions` and `~/.claude/projects` found
  **zero** write records targeting this file — every hit was a `skill-drafts/PROPOSAL.md` write,
  never the skill itself. This negative is RTK-safe and therefore carries weight: whoever changed
  that file did not do it through a Codex `apply_patch` or a Claude `Edit`/`Write` recorded on this
  host. Candidate explanations, none confirmed: an m5max edit (Finding 12), a shell redirect, or an
  Orca-internal write.

- **The `~/.claude/skills` symlink farm creation event.** Created on m5max. **No record found on
  this host, and none can exist** — m5max's transcripts are not present here. The installer identity
  is known from `~/.agents/.skill-lock.json` v3 (peer finding, reconciled); the operator and host
  session are not. I am not naming a local session for it.

---

## GAPS

- **RTK contamination, scoped.** Three findings originally rested on bare-`grep` negatives. Two are
  now re-verified in Python (Finding 8's absence check, and the `orca-cli` write-record negative
  above). Still **UNVERIFIED-DUE-TO-RTK**, and load-bearing for nothing in this report: my counts of
  `.claude/skills` / `agents/skills` inside `app.asar` (0 hits), and `main.trace.ndjson.8` showing
  no skill matches. No conclusion above depends on either.

- **Newton's task payloads are encrypted.** Every `/root → /root/hook_error_fix` message in the
  rollout is `{"type": "encrypted_content", ...}`. Newton's own commentary and the human's turns are
  plaintext and were recovered, but the orchestrator's verbatim instructions to Newton cannot be
  read from disk. The authorization chain above is therefore reconstructed from the human side and
  the worker side, with the middle link opaque.

- **Whether a second m5max sync occurred after Jul 20.** This is the single unknown blocking Finding
  12. If one did, the Jul 26 12:09 `orca-cli` mtime could also be foreign, and the artifact moves
  from "unattributed" to "off-host".

- **`orchestration.db` and `terminal-history/` were not queried.** Group attribution was derived from
  `session_meta.cwd` and `daemon.log` instead, which was sufficient and independent. The
  orchestration DB may hold the dispatch record that would tighten Finding 3 by showing what the
  orchestrator actually told Newton.

- **`~/.agents/skills/annotate` and `~/.claude/skills/annotate` were not audited.** Neither is
  Orca-managed (absent from `.skill-lock.json`); only the five installer-managed skills were
  hash-checked. Peer established `annotate` arrived via the Jul 20 rsync.

- **claude-mem was not queried directly.** Finding 8 refutes the #9881 hypothesis from filesystem
  and transcript evidence alone. I did not read observation #9881 itself, so I cannot rule out that
  it describes a *different* draft than the `7486ab0f` PROPOSAL.md I found — though the subject
  matter (`orca orchestration read`, invalid `--full`), the date (Jul 24), and the empty
  `files_modified` all match.
