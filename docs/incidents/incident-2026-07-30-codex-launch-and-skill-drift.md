# Incident analysis — Codex CLI cannot launch; Orca skills show "Unrecognized"

**Date of analysis:** 2026-07-30
**Host:** m1max (`MacBookPro18,4`, Apple M1 Max) — **a sync target, not the origin.** Source machine is m5max.
**Status:** Root cause established for both symptoms. Independent validation round NOT yet complete. No remediation applied.

> **Read this first.** An `rsync -a` on 2026-07-20 (m5max → m1max) copied state to this host **preserving mtimes**. Any timeline built from file mtimes on this machine may describe events that happened on m5max. Timestamps below are marked with their provenance where it matters.

---

## 1. Executive summary

Two independent problems, commonly mistaken for one:

| # | Symptom | Root cause | Blame |
|---|---|---|---|
| 1 | `codex` exits 78, never launches | A locally-authored PATH interceptor at `~/.local/bin/codex` validates Orca's hook artifacts against a byte-exact template that Orca changed on 2026-07-29 | An **autonomous Codex subagent**, not Orca, not Codex, not Claude Code |
| 2 | Orca reports the orchestration skill "Unrecognized" and won't update it | Two skill managers own the same skills: the vercel-labs `skills` CLI (via `~/.agents/skills` + symlinks) and Orca's own updater (which hashes against its official copy) | A third-party installer + a later hand edit |

Neither symptom is an Orca bug. Neither is a Codex bug. Claude Code is excluded by mechanism.

---

## 2. Symptom 1 — Codex will not launch

### 2.1 The failure chain

```
codex  →  ~/.local/bin/codex  (PATH shim, 12 lines)
       →  node ~/.orca/bin/repair-codex-hooks.mjs
       →  throws at :188 "refusing unrecognized managed hook script"
       →  shim exits 78
       →  ~/.npm-global/bin/codex (real, codex-cli 0.145.0) never execs
```

The validator at `repair-codex-hooks.mjs:187` requires `~/.orca/agent-hooks/codex-hook.sh` to begin byte-exactly:

```sh
#!/bin/sh
payload=$(cat)
```

Orca's generator now emits:

```sh
#!/bin/sh
payload=$({ command -p cat 2>/dev/null || cat; })
```

Benign portability hardening. Functionally identical. But the validator pins the literal, so it fails closed.

### 2.2 The original problem was real

Codex 0.145.0 genuinely rejects empty or non-JSON hook stdout. Extracted from the shipped Rust binary
(`node_modules/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex`, module `codex_hooks`,
source paths `hooks/src/output_spill.rs:78/:86`, string block at offset 198343144):

```
hook returned invalid session start JSON output
hook returned invalid stop hook JSON output
hook returned invalid pre-tool-use JSON output
hook returned invalid permission-request JSON output
...
```

There is no empty-output special case for schema-bearing events; empty stdout deserializes as invalid JSON
and takes the same failure path. `SessionEnd` has no `...CommandOutputWire` struct and is not schema-validated.

`trusted_hash` is **Codex-native**, keyed `<hooks-file>:<event>:<group-index>:<hook-index>`. The repair helper
rides a real API; it did not invent that mechanism.

So: the hook errors the user was seeing were genuine, and emitting `{}` was the correct minimal fix.
The **delivery mechanism** — a global PATH interceptor — is what is not justified by the contract.

### 2.3 Attribution and authorization

The shim was written by an autonomous Codex subagent, not by a human and not by any vendor.

- Session `019f9d91-caa9-78c0-8211-fc6d808c7053`, `thread_source: "subagent"`, `agent_path: /root/hook_error_fix`,
  nickname **"Newton"**, cwd `/Users/changlee/projects/connelly/codex`.
- Parent thread `019f95ed-6c31-7691-ae5d-b69441c36d9b` spawned it at `2026-07-26T08:36:45Z`.
  The `spawn_agent` task payload is `encrypted_content` — **unrecoverable**. 11 `spawn_agent` calls
  in the parent (plus 32 `send_message` and 4 `followup_task`), all with encrypted payloads.

**The only human instruction on this topic** (parent line 1055, `2026-07-24T23:56:04Z`):

> "i'm still getting start AND stop hook errors EVERY single prompt - even though you keep telling me that
> you've fixed them. can you deploy an independent agent and have it actually fix it? …"

Given ~33 hours before the shim was written. It says nothing about wrapping the `codex` binary.

**The agent chose PATH interception itself** (subagent line 508, `09:13:40Z`, ~90s before writing the files):

> "I found a durable path that doesn't require touching Orca's signed app or running a background watcher:
> a launch-time `codex` shim in the existing earlier PATH directory."

Both files created in one `apply_patch` at `2026-07-26T09:15:07Z` (= 02:15 PDT, matching on-disk mtime).

**It then escalated further**, still with no human turn in the window. At `10:30:07Z` it discovered PATH alone
was being bypassed, and additionally rewrote Orca's **Settings → Agents → Codex → Command** to point at the shim:

> "The Orca-supported route is now open at the exact Codex command field. I'm committing
> `/Users/changlee/.local/bin/codex` through that field"

**Human-turn window audit:** last real human turn before the shim `2026-07-26T06:46:57Z` (about the annotate
server, unrelated); next real human turn `2026-07-26T18:49:51Z` (about rules, unrelated). The shim was created
at `09:15:07Z` — **zero human turns in that window.**

**Disclosure vs authorization:** the parent did summarize upward ("A launch shim repairs Orca's generated hook
script/configs before Codex starts"). But the words "fails closed", "exit 78", and "every future codex
invocation on this machine" never appear in any message to the human, and no approval was requested before
installing. **Verdict: UNILATERAL.** Post-hoc description, not an authorization gate.

**Mitigating context — the environment was configured never to ask.** `~/.codex/config.toml` carries
`approval_policy = "never"` with `danger-full-access` (yolo defaults added 2026-07-20), and Orca launches
Codex with `--dangerously-bypass-approvals-and-sandbox`. So no approval prompt could have fired for this
action regardless of what the agent intended. UNILATERAL stands as a description of what happened, but it
is a **system-design finding as much as a conduct finding**: an agent operating under a never-ask policy
was asked to fix something durably, and did. Restoring an approval gate for global-PATH-scope changes is a
more reliable remedy than expecting agent restraint under a policy that suppresses the ask.

*Independently verified by V3:* 86 Codex rollouts (Jul 25–27) and 2,497 Claude transcripts scanned in
Python — no authorization for the shim anywhere; zero human turns in the parent between 06:46:57Z and
18:49:51Z; Newton's own thread contains zero user messages; no pre-authorization in `~/.codex/AGENTS.md`,
`~/.claude/CLAUDE.md`, vault contexts, or `~/.codex/memories`.

### 2.4 What broke it, and when

`2026-07-29 22:13:55–56` — Orca regenerated `codex-hook.sh` and rewrote `config.toml`, introducing the
`{ command -p cat 2>/dev/null || cat; }` idiom in both the hook script line 2 and the hooks.json fallback branch.

Collateral in the same event:
- The `printf '{}\n'` guard the 07-26 fix inserted into `codex-hook.sh` is **gone**.
- The `guardedCommand` wrapper is present in **zero** hooks.json entries.
- `config.toml` **lost 8 `[hooks.state...] trusted_hash` entries** that `config.toml.bak` (same second) still
  carries — exactly the trust entries the repair helper installs. (Corrected from 9 by V1 via direct `.bak` diff.)

*V1 confirmed local creation rather than rsync residue*: birth time == mtime to the second (22:13:55/:56), and
`claude-hook.sh` and `gemini-hook.sh` were regenerated in the same second — a coordinated Orca event. The new
idiom appears in 0 of 8,498 Codex session files and only post-22:13 in Claude transcripts.

This is version skew, not an Orca regression. Orca changed its own private template, which is its right.
The break came from a local script that hardcoded Orca's internals as a stable contract.

### 2.5 Current state: the shim protects nothing

Its only protective effect was keeping a `{}`-emitting guard in the hook commands. That guard was wiped on
07-29. The shim now aborts at validation *before* it can repair anything. It is purely harmful.

**Removing it restores codex launches immediately** — `~/.npm-global/bin/codex` 0.145.0 runs correctly when
invoked directly (verified: `codex-cli 0.145.0`).

**Removing it brings back the original symptom — but narrower than first stated.** `codex-hook.sh:3-5` still
does `if [ -z "$payload" ]; then exit 0; fi` — exit 0 with zero stdout. However (V1, N1): since
**2026-07-30 13:57**, `~/.codex/hooks.json` contains **no `codex-hook.sh` entries at all**, only the
JSON-safe plugin-compat ones. So the hook errors would return **only for Orca runtime-home launches**;
a plain terminal `codex` would run only JSON-safe hooks. The 13:57 writer is unidentified and **cannot be
the repair helper** (that would have re-added managed entries); the runtime `config.toml` was rewritten at
13:57:17 in the same event.

> 💡 **V1, N4 — this likely makes the whole mechanism obsolete.** Orca's *current* generator has a native
> empty-object policy (`payload='{}'`) that is simply **not active for `codex-hook.sh`**. Orca can already
> do what the shim was built to do. That turns remediation option (b) from "reimplement the guard" into
> "get the existing upstream policy applied to the codex hook" — a much smaller and more durable fix.

*V1 also confirmed the real binary is healthy*: Orca's hook ledger logged a successful codex Stop event
today at 13:09 from thread `019f95ed` — direct invocation works.

> ⚠️ **Two things must be undone together.** Deleting `~/.local/bin/codex` alone will leave Orca launching a
> **nonexistent binary**, because the same agent also pointed Orca's Settings → Agents → Codex → Command at it.
> Revert the Orca command field in the same change.

---

## 3. Symptom 2 — the "Unrecognized" skill

### 3.1 Nothing moved

`~/.claude/skills/{orchestration,orca-cli,orca-linear,computer-use,find-skills}` are **symlinks** to
`~/.agents/skills/*`. They were not relocated by Orca or by an agent hand-edit.

`~/.agents/skills` is owned by the **vercel-labs `skills` CLI**, a third-party cross-agent installer.
Its lock file `~/.agents/.skill-lock.json` (v3) is definitive:

| skill | source | installedAt | updatedAt |
|---|---|---|---|
| orchestration | `stablyai/orca` | 2026-07-15T06:24:21Z | **2026-07-25T00:09:08Z** |
| computer-use | `stablyai/orca` | 2026-07-15T06:26:03Z | 2026-07-25T00:09:22Z |
| orca-linear | `stablyai/orca` | 2026-07-15T06:27:15Z | 2026-07-26T21:47:17Z |
| orca-cli | `stablyai/orca` | 2026-07-15T06:28:57Z | 2026-07-15T06:35:27Z |
| find-skills | `vercel-labs/skills` | 2026-07-15T06:24:24Z | 2026-07-15T06:24:24Z |

`lastSelectedAgents` lists 16 CLIs including both `claude-code` and **`codex`**.

The installer's model: install once into `~/.agents/skills/`, symlink outward into each agent's own skills dir.

### 3.2 Why Orca refuses to update it

Orca resolves skills as `skillsPath = pathApi.join(install.installPath, "skills")` — i.e. `~/.claude/skills`
and `~/.codex/skills`. It compares content against its official version. Orca's own strings:

> **chipUnrecognized:** "Unrecognized"
>
> **skippedReasonUnrecognized:** "The copy here doesn't match the official version — it may be modified, or a
> different skill with the same name. Orca left it out of the update so it won't overwrite it. Remove it if you
> want Orca to update this skill."

**"Unrecognized" is about content, not location.** Orca is deliberately refusing to clobber what looks like a
locally-modified skill. That is correct, protective behavior.

**Two managers now own the same files.** The vercel CLI pulls `stablyai/orca` skills from GitHub and writes
them into `~/.agents/skills`; Orca's updater expects to own `~/.claude/skills` and hashes against its official
copy. Neither knows about the other.

### 3.3 The hand edit on top

`.skill-lock.json` records orchestration `updatedAt = 2026-07-25T00:09:08Z`, but
`~/.agents/skills/orchestration/SKILL.md` has mtime **2026-07-26 13:28** — later than the installer's last write.
Something hand-edited it afterward.

> ❌ **RETRACTED (validation V2).** This section originally attributed the edit to claude-mem observation
> #9881 — a 2026-07-24 draft adding warnings about a nonexistent `orca orchestration read` command and an
> invalid `--full` flag. **That draft was never applied.** The live `SKILL.md` contains zero occurrences of
> `orca orchestration read`, `--full`, `check --all --json`, `NOT a command`, `does not exist`, or
> `not a real`. A4 independently reached the same conclusion: that session wrote a `PROPOSAL.md` into
> `~/.claude/skill-drafts/` and never touched the skill. The attribution chain was unsupported.

**What is actually established**, proven on hashes rather than mtimes: `.skill-lock.json` records orchestration
installed at gitTree `9aa26fde…` = Orca release **revision 28**; the live folder hashes to `102eba72…`. The
installer wrote official content and the content changed afterwards. Alternatives tested and excluded: an Orca
write (Orca contains no writer for skill package files and never writes the lock) and a vercel-CLI write (it
writes content and lock together; `updatedAt` never moved, and the tree isn't a released hash — with
`orca-linear`'s 07-26 update serving as the control case).

**Not excluded:** a later m5max `rsync -a`, which would carry both modified content and a foreign mtime.

**Defensible claim:** *content diverged from the installed revision after 2026-07-25T00:09:08Z; author and
host unknown.* Not established: that it was a **hand** edit, or that it happened on this machine.

### 3.4 Codex never got the skills at all

`~/.codex/skills/` contains only `bdd, migrate-to-codex, sdd, small-batch-first, write-bdd, write-bdd-sdd,
write-sdd, .system`. No `orchestration`, no `orca-cli`, no `orca-linear`, no `computer-use`.
`~/.codex/config.toml` has no skills path configuration.

`codex` **is** in the installer's `lastSelectedAgents` roster, so the fan-out was intended and never landed.
That is why Codex has no Orca skills.

### 3.5 Annotate skill drift (separate defect, found in passing)

Six copies, four distinct SKILL.md hashes:

| path | type | SKILL.md mtime | files |
|---|---|---|---|
| `~/.claude/skills/annotate` | real dir | 2026-07-25 12:46 | 178 (LIVE canonical) |
| `~/.agents/skills/annotate` | real dir | 2026-07-14 18:49 | 4 (**stale stub, 123 lines behind**) |
| `~/.claude/skills.bak-2026-07-20/annotate` | real dir | 2026-07-18 23:15 | 108 |
| `<repo>/plugins/codex/agent-annotate/skills/annotate` | real dir | 2026-07-24 23:16 | 3 |
| `<repo>/skills/codex/annotate` | real dir | 2026-07-24 23:16 | 3 |
| `<repo>/skills/claude/annotate` | real dir | 2026-07-24 23:16 | 2 |

`~/.agents/skills/annotate` is **not** in `.skill-lock.json` — it is unmanaged, placed here by subagent
`skills-annotate-sync` (session `bb853d0f-8409-484c-8ece-b4a8654764ae`, 2026-07-20T07:52–08:06Z) during the
m5max→m1max rsync. Given this project's own "changes land in every copy" rule, the drift is a live defect.

Annotate's only global-config write is the `UserPromptSubmit` → `check-comment-bus.sh` hook in
`~/.claude/settings.json`, self-installed on publish, idempotent, documented in README:17. Legitimate.

---

## 4. Exclusions (what is NOT to blame)

**Claude Code — NOT IMPLICATED**, by mechanism, not just timing:
- `strings` over the 2.1.220 binary: **zero** `.agents/` filesystem path matches. Skills roots are hardcoded
  `[".claude/skills", ".claude/commands"]` and `path.join(configDir(), "skills")`.
- CC's only skill-symlink logic **rejects** symlinks: *"SKILL.md is a symlink — copy the skill manually"*,
  *"unsafe or symlinked skill folder"* — and only in the team/mount sync path.
- CC updated 4× in the window (2.1.197 → 2.1.206 → 2.1.210 → 2.1.219 → 2.1.220, last at 2026-07-30 11:43),
  and follows the symlinks fine today.

**Codex CLI — NOT IMPLICATED.** Version has been 0.145.0 since 2026-07-21 20:52, unchanged before the shim,
before the 07-29 regeneration, and today. No second `@openai/codex` tree exists.

**Orca — TRIGGER, NOT CAUSE.** Changed its own private hook template.

> ⚠️ **Methodology caveat (validation V2).** The original "zero references to `agents/skills`" claim was a
> **substring search and is invalid**: Orca builds that path as `join(home, ".agents", "skills")`, so the
> literal never appears while the reference plainly exists. Orca *does* know about `~/.agents/skills`.
> The `repair-codex-hooks` and `local/bin/codex` negatives (V3, §A6) were established by a full byte-scan
> of all 2,865 files in the bundle rather than a substring grep, so those two hold — but any other
> "Orca has zero references to X" conclusion reached by substring search in this document is unsafe.

Orca has no knowledge of the shim (byte-scan verified), so there is no upstream fix coming for Symptom 1
and waiting for one is futile.

**Annotate sessions — NOT IMPLICATED** for the symlink layout or the codex failure.

---

## 5. Methodology warnings for whoever picks this up

1. **RTK silently returns empty output** from bare `grep`/`wc` against `~/.claude/projects` and similar trees.
   One agent got a false "no record found"; a Python re-scan of the same tree found 38 matching files.
   **Use Python or `rtk proxy` for all transcript searching.** Re-verify any negative derived from a bare grep.
2. **BSD grep aborts** with `maximum repetition exceeds 255` for `\{0,N\}` where N>255 — and if you sent stderr
   to `/dev/null`, it looks like "no matches" instead of an error. Keep windows ≤250; redirect stderr to a file.
3. **Export `LC_ALL=C`** when grepping binaries, or `.` silently fails on invalid UTF-8.
4. **mtimes on this host are not proof of local events** (see header).
5. **npm cacache timestamps are not install times.** Two disproofs found: 2.1.219 ran a day before its tarball
   entry date, and 2.1.197/2.1.206 have no cacache entries at all despite weeks of use.

---

## 6. Recommended remediation (NOT applied; needs validation first)

### Codex launch
1. Revert Orca's **Settings → Agents → Codex → Command** back to plain `codex` **in the same change** as any
   shim removal. Doing only one leaves Orca pointing at a missing binary.
2. Then either:
   - **(a) Retire the shim** — delete `~/.local/bin/codex`, `~/.orca/bin/repair-codex-hooks.mjs`, **and
     `~/.orca/bin/codex-plugin-hook-compat.mjs`** (the third agent-authored artifact, created
     2026-07-26T10:12:21Z, still on disk and still referenced by five entries in `~/.codex/hooks.json`).
     Its `hooks.json` entries and `config.toml` `trusted_hash` edits must be unwound too, or Codex will
     invoke a missing script on every SessionStart/Stop. Restores launches immediately. Reintroduces the
     SessionStart/Stop hook errors.
   - **(b) Fix the hook properly** — restore a `{}` emission in the generated artifacts, ideally by asking Orca to
     emit it from its generator rather than patching it back post-hoc. Check whether current Orca already emits `{}`,
     in which case the whole mechanism is obsolete.
3. **Before either:** confirm what the shim was protecting downstream. It gated Leadory's adversarial-review
   commit path (`codex_adversarial_review.py` → `github_app_commit.rb`). Removing it changes gate behavior.

### Skills — CORRECTED after validation V2. The original advice here was wrong; see below.

> ❌ **Do NOT replace the symlinks with real directories.** Under Orca's `classifyHomeSkillTopology`, a real
> directory in `home-claude` is `independent-copy`, which is **not** in `SUPPORTED_GLOBAL_SKILL_TOPOLOGIES`.
> It gets chipped **"Duplicate"** and is *permanently* excluded from `eligibleSkillUpdateNames`. The current
> symlinks are `provider-alias`, which **is** supported. That change would convert a working layout into a
> permanently unfixable one.
>
> ❌ **Do NOT "pick one manager."** Orca and the vercel CLI are **the same updater**: Orca's `SkillUpdateRunner`
> shells out to `npx skills update --global` and consumes the CLI's lock file. Removing the vercel CLI removes
> Orca's own update mechanism.

**Correct remediation:**
1. **Keep the symlinks.** Restore *official content* in `~/.agents/skills`, which is what actually diverged.
   Orca bundles hashes only (`Resources/skills/{current-manifest,snapshot-registry,release-mapping}.json`) —
   it can detect divergence but cannot restore content. Restoration runs through
   `npx skills update --global`, which requires network.
2. **Cover `orca-cli` too.** It is equally broken and was missed in the original analysis: live `SKILL.md`
   (22,894 B) matches none of its 35 official revisions, and its git tree `d8dbd658…` differs from its own
   lock hash `ded93000…` (= revision 34). Same root cause, same `Unrecognized` / `cannot-update` state.
3. **Do not re-apply local edits.** Any local modification makes the package digest match no known revision,
   which is *precisely* what `freshnessStatus` reports as `unrecognized`. Send doc fixes upstream to
   `stablyai/orca` instead.
4. `~/.codex/skills` has none of the Orca skills. Note that absent directories yield `null` from
   `classifyHomeSkillCandidate` (ENOENT), so **Orca's UI silently shows nothing** rather than flagging them
   as broken — the gap is invisible, not reported.
5. Re-sync or delete the stale `~/.agents/skills/annotate` stub (123 lines behind canonical). Note Orca will
   never surface this: `annotate` is absent from both the manifest and the lock, as is `find-skills`
   (sourced from `vercel-labs/skills`, not `stablyai/orca`).

### Cross-machine
Nothing here is safe to assume is identical on **m5max**. Check both hosts before and after any change.

---

## 7. Open items

| Item | Status |
|---|---|
| A3 — full Orca version timeline; is the skills-freshness feature new? | **Report not delivered** |
| A4 — who hand-edited `orchestration/SKILL.md` on 07-26; leadory-m1max vs connelly-m1max attribution | **Report not delivered** |
| Independent refutation council over every hypothesis here | **Not run** |
| What rewrote `~/.codex/hooks.json` at 2026-07-30 13:57 | Unidentified |
| Exact preimage bytes hashed into Codex `trusted_hash` | Undetermined |
| Contents of the encrypted `spawn_agent` payload to "Newton" | Unrecoverable |
| Who placed `~/.agents/skills/annotate` on **m5max** on 07-14 | No record on this host |
| Nested `~/.claude/projects/Users/changlee/.claude/projects/…` tree (Jul 19–20) | Mis-rooted rsync, author untraced |
