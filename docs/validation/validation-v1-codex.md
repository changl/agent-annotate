# Validation V1 — Adversarial review of Section 2 (Codex will not launch)

**Validator model (env block):** `claude-fable-5`
**Date:** 2026-07-30, ~14:55–15:10 local (m1max)
**Method:** strictly read-only; live-file inspection, binary string scans (Python, not bare grep), transcript scans, Orca state stores. `codex` was never executed; `repair-codex-hooks.mjs` was never executed.
**Target:** `docs/incident-2026-07-30-codex-launch-and-skill-drift.md`, Section 2, claims C1–C5.

## Verdict summary

| Claim | Verdict |
|---|---|
| C1 — shim is the sole launch blocker | **UPHELD** (scope note below) |
| C2 — Codex 0.145.0 genuinely rejects empty hook stdout | **UPHELD** (string + receipt + behavioral evidence; no disassembly) |
| C3 — Orca's 07-29 22:13 regeneration introduced the template that trips the validator | **UPHELD** |
| C4 — shim protects nothing; `{}` guard gone everywhere | **UPHELD** (with one consequential nuance, defect N1) |
| C5 — shim removal requires reverting Orca's Codex command field | **UPHELD** — live setting read from Orca's own store |

---

## C1 — "The shim at ~/.local/bin/codex is the sole reason codex fails to launch": UPHELD

Attack: find a second, independent interceptor or launch blocker.

**Direct receipt of the failure, from today.** Orca pane checkpoint
`~/Library/Application Support/orca/terminal-history/a1d1b72e-…connelly…codex…/checkpoint.json`
(`checkpointedAt: 2026-07-30T17:57:06Z` = 10:57 local today) captures verbatim:

```
/Users/changlee/.local/bin/codex '--dangerously-bypass-approvals-and-sandbox' 'resume' '019fa027-edb1-7481-b390-b4d2f1011292'
Orca Codex hook repair failed: refusing unrecognized managed hook script: /Users/changlee/.orca/agent-hooks/codex-hook.sh
Codex launch stopped: Orca hook JSON validation failed.
```

That is the doc's exact chain (`shim → repair-codex-hooks.mjs → throw :188 → exit 78`), observed live.

**No second interceptor exists:**
- `which -a codex` → only `~/.local/bin/codex` (shim, twice — PATH lists the dir twice) and `~/.npm-global/bin/codex` (real). No brew/`/usr/local` codex (`ls` exit 1).
- `~/.zshrc` / `~/.zprofile`: no alias or function named `codex`. PATH order: `~/.zshrc:34` prepends `$HOME/.local/bin` after line 1 prepends `~/.npm-global/bin`, so `.local/bin` wins — shim shadows real.
- Shim source (12 lines, read directly): only gate is `/usr/local/bin/node repair-codex-hooks.mjs`; node exists (`/usr/local/bin/node`, root-owned, executable).
- Validator source read in full: `repair-codex-hooks.mjs:186-188` requires the script to start byte-exactly with `#!/bin/sh\npayload=$(cat)\n` (or an existing `{}` prelude). Live `codex-hook.sh:2` is `payload=$({ command -p cat 2>/dev/null || cat; })` → the `:188` throw is unavoidable. First statement in the `try` block that can throw on current state is exactly this one (the two `enabledPlugins()` calls before it only read files that exist; all five plugin trust-state keys that `disableOriginalPluginHooks` demands are present in both config.tomls — verified by section listing).
- Real chain intact: `~/.npm-global/bin/codex` → symlink (46 B) → `../lib/node_modules/@openai/codex/bin/codex.js` (standard platform-package spawner, read) → vendor binary `@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex` present, executable, 271,134,288 B.

**Scope note (not a refutation):** for *Orca-initiated* launches the command field also points at the shim (see C5) — but that is the same artifact, not an independent failure. Residual untested item: I could not run codex, so "removing the shim restores launches immediately" (doc 2.5) rests on the doc's own direct-invocation check plus new corroboration in defect N3 below (a codex Stop-hook event was received by Orca today at 13:09, meaning the real binary did run today when invoked directly).

## C2 — "Codex 0.145.0 genuinely hard-fails on empty hook stdout": UPHELD

Attack: find contrary strings, a lenient/default path, or config to disable validation.

**Strings verified** (Python scan of the 271 MB vendor binary; no bare grep):
- Error block at offset ~198,343,328 (doc said 198,343,144 — same block): `hook returned invalid pre-tool-use JSON output`, `…invalid session start JSON output`, `…invalid subagent start JSON output`, `…invalid permission-request JSO…`, `…invalid subagent stop hook JSON output`, `…invalid stop hook JSON output`, `hook exited without a status code`, adjacent to `hooks/src/output_spill.rs:78` / `:86` and `codex_hooks::output_spill` — exactly as the doc quotes.
- `trusted_hash` / `HookStateToml` / `hooks.state."…".trusted_hash` present → the trust mechanism is Codex-native, as claimed.

**Lenient-path search came back empty:** 0 hits for `hooks disabled`, `disable_hooks`, `CODEX_DISABLE_HOOKS`, `hooks_enabled`, `allow_empty`, `hook returned no output`, `no hook output`, `hook output was empty`, `skipping hook`. The only "skip" string is `skipping empty hook command in` (empty *command in config*, a different case). No config-surface string suggests hook validation can be disabled short of removing hooks from hooks.json.

**Runtime receipts:** 258 occurrences of `hook returned invalid` across 19 files in `~/.codex/sessions`, e.g. 07-20: `• Stop hook (failed)\nerror: hook returned invalid stop hook JSON output`. By session date: 07-12: 1, 07-16: 22, 07-20: 2, 07-21: 87, 07-23: 16, 07-24: 65, 07-25: 7, 07-26: 58, **then zero ever again** — the errors stop exactly when the `{}` guard was installed (07-26), and post-07-29 no codex sessions could launch at all. The hook script emits empty stdout by construction on every path (curl output `>/dev/null`, `exit 0`), so the errored events had empty stdout.

**Honest limit:** no disassembled branch; a string-free lenient path cannot be excluded in principle. The combination (error strings + no contrary strings + empty-stdout-by-construction receipts + errors ceasing when `{}` was emitted) closes the gap empirically. "Hard-fails" means the hook is reported failed on every schema-bearing event — codex still runs (receipts show sessions continuing) — which is also how the doc frames it.

## C3 — "Orca's 2026-07-29 22:13 regeneration introduced the template change": UPHELD

Attack: alternative writer; untrustworthy mtimes on a sync-target host.

**The mtimes are trustworthy here — birth times prove local creation.** `rsync -a` preserves mtimes but creates files fresh (birth = local copy time); a synced file would show birth ≠ mtime. These show birth == mtime to the second:
- `~/.orca/agent-hooks/codex-hook.sh` — birth=mtime **Jul 29 22:13:55**
- `~/Library/Application Support/orca/codex-runtime-home/home/hooks.json` — birth=mtime **Jul 29 22:13:56**
- `~/.codex/config.toml` — birth=mtime **Jul 29 22:13:56** (`config.toml.bak`: birth Jul 26 16:16:22, mtime Jul 29 22:13:56 — an existing file rewritten in the same event)
- **Coordinated multi-agent event:** `~/.orca/agent-hooks/claude-hook.sh` AND `gemini-hook.sh` also birth=mtime **Jul 29 22:13:56**. Three agents' managed hook scripts regenerated in one second. The known one-off rsync was 07-20, before all of this.

**The template is Orca's, byte-for-byte.** Current `app.asar` (and `app.asar.unpacked/out/main/chunks/managed-agent-hook-controls-C__01WW5.js`) contains the generator:
`POSIX_HOOK_STDIN_READER = "{ command -p cat 2>/dev/null || cat; }"`, `payload=$(${$c})`, `if [ -z "$payload" ]; then … exit 0 … fi`, and `buildManagedCommand: … .orca/agent-hooks/codex-hook.sh` — the on-disk script is exactly this generator's output.

**Alternative writers refuted:**
- The idiom appears in **zero** of 8,498 files in `~/.codex/sessions` — no codex agent authored it.
- In `~/.claude/projects`, 23 transcripts contain it; **every one postdates 22:13** (earliest mtime 07-29 22:54) and each occurrence is a *tool result* (Read of codex-hook.sh/hooks.json) or a Stop-hook system record — observation, not authorship. The 07-29-evening files are diagnostic sessions investigating this same breakage; one report explicitly attributes the evening's change to the "Orca 1.4.161 update".
- `repair-codex-hooks.mjs` cannot have produced it: its only script mutation inserts `printf '{}\n'` into the *old* `payload=$(cat)` template.

**Honest limit:** the app bundle was replaced today (birth 07-30 09:28), so I inspected today's asar, not the binary that ran on 07-29. The 07-29 diagnostic transcript grepping the then-current asar for the same string, plus the claude-hook stop_hook_summary records from 23:11 that evening already showing the new-style fallback command, cover that gap.

## C4 — "The shim currently protects nothing; the `{}` guard is gone everywhere": UPHELD

Verified against all three live files, read in full today:
- `~/.orca/agent-hooks/codex-hook.sh` — no `printf '{}'` anywhere; empty-payload path is `exit 0` (lines 3–5); success path pipes curl output to `/dev/null` and exits 0. Stdout is empty on every path.
- `~/.codex/hooks.json` (live, rewritten 07-30 13:57) — **zero** `guardedCommand` entries, zero `printf '{}'`; in fact zero references to codex-hook.sh at all (only 5 plugin-compat entries: 4× SessionStart, 1× Stop).
- `~/Library/Application Support/orca/codex-runtime-home/home/hooks.json` (live) — 8 events, all unguarded generated-style commands (`else { command -p cat …; } >/dev/null 2>&1 || :`), zero `printf '{}'`.
- And the shim can no longer repair anything: it exits at validation before any write (today's 10:57 receipt, C1). Purely harmful — confirmed.

## C5 — "Removing the shim requires ALSO reverting Orca's Codex command field": UPHELD

Read directly from Orca's live profile store, `~/Library/Application Support/orca/profiles/local-default/orca-data.json` (mtime **today 14:52:43**, i.e. current):

```json
"agentCmdOverrides":{"codex":"/Users/changlee/.local/bin/codex"}
```

Same value in all five rotated backups (`orca-data.json.bak.0`–`.bak.4`). App code (asar, 144 refs) consumes it as `settings.agentCmdOverrides?.[agentId]` — a command override, default `{}` (constants.js). Behavioral confirmation: today's 10:57 pane checkpoint shows Orca invoking the shim by that absolute path. Deleting `~/.local/bin/codex` while this override stands leaves Orca spawning a nonexistent absolute path. The doc's highest-consequence warning is correct.

*(Search-method note: Electron LevelDB stores are snappy-compressed, so raw byte scans of `Local Storage` are not valid negatives — but the setting was found in plaintext JSON in the profile store, which is where the asar reads it from, so no LevelDB parsing was needed.)*

---

## New defects / facts the document missed

**N1 (consequential).** `~/.codex/hooks.json` as rewritten 07-30 13:57 contains **no managed codex-hook.sh entries at all**. Consequences: (a) doc 2.5's "removing the shim brings back the SessionStart/Stop errors" now holds only for **Orca runtime-home launches**; a plain-terminal `codex` would run only the plugin-compat hooks, and `codex-plugin-hook-compat.mjs` always emits JSON (`emit({})` even in its `fail()` path) — so terminal launches would likely be error-free. (b) The 13:57 writer **cannot** have been `repair-codex-hooks.mjs` — it would have inserted guarded entries for all 8 events or thrown. Candidate worth checking: codex's own `external-agent-migration` module (binary strings: `external-agent-migration/src/hooks_common.rs … failed to serialize hooks.json`), triggered by the direct codex runs during today's analysis (~13:09, see N3). Note the runtime-home `config.toml` was also rewritten at **13:57:17** — same unexplained event, not mentioned in the doc.

**N2 (count nit).** Doc 2.4 says config.toml "lost 9 `[hooks.state…] trusted_hash` entries". Direct key diff of `config.toml` vs `config.toml.bak`: **8** sections present in .bak and missing from live (`/Users/changlee/.codex/hooks.json:` `session_start:4:0`, `user_prompt_submit:0:0`, `pre_tool_use:0:0`, `permission_request:0:0`, `post_tool_use:0:0`, `subagent_start:0:0`, `subagent_stop:0:0`, `stop:1:0`) — exactly the repair helper's managed guardedCommand trust keys, so the substance stands, but the number is 8, not 9 (unless duplicate `trusted_hash` lines were counted).

**N3 (corroborating).** Orca's hook ledger `~/Library/Application Support/orca/agent-hooks/last-status.json` records a **codex** `Stop` event (`agentType: "codex"`, `model: "gpt-5.6-sol"`, providerSession `019f95ed-6c31-…` — the doc's parent thread) received **today at ~13:09**. A codex process therefore did launch and run today when invoked directly (shim bypassed), and its hook POST path to Orca works — independent support for "the real binary runs" and for the hook-endpoint mechanism.

**N4 (remediation-relevant).** The current Orca generator has a native `{}` policy: `buildPosixHookPayloadCapture(emptyPayloadPolicy)` with an `"empty-object"` branch that sets `payload='{}'` (asar + managed-agent-hook-controls chunk). The deployed codex-hook.sh was generated with the default `"exit"` policy. Doc 6.2(b)'s open question ("check whether current Orca already emits `{}`") is answerable: **the capability exists in the current app but is not active for the codex hook script on disk** — worth raising with Orca instead of any local patching.

**N5 (minor).** The runtime hooks.json else-branch (`{ command -p cat …; } >/dev/null 2>&1 || :`) no longer matches the repair helper's `generatedCommand` (`cat >/dev/null 2>&1 || :`), so even with the script-prelude check fixed, the helper would not upgrade those entries to guarded form — a second hardcoded-template mismatch in the same shim, confirming the doc's "version skew from pinning Orca internals" thesis.

## What was NOT verified (honest gaps)

- No disassembly of the codex binary; C2's "no lenient branch" is string- and behavior-based.
- The 07-29-era Orca app binary is gone (replaced 07-30 09:28); C3's generator match uses today's asar plus that evening's diagnostic-transcript receipts.
- Codex was never launched by me (forbidden and unnecessary); "launches fine without the shim" rests on doc's check + N3.
- `trusted_hash` preimage semantics remain undetermined (doc open item) — could add friction on first post-fix launch; unverifiable read-only.
