# HANDOFF — Codex launch failure + Orca skill drift

**Written:** 2026-07-30 ~15:00 PDT · **Outgoing session context:** past hard stop
**Host:** m1max (rsync TARGET of m5max; mtimes here may describe m5max events)

---

## 0. STATE IN ONE LINE

Investigation complete and independently validated except one item (V1). **Nothing on the system has
been changed.** No file removed, no setting reverted, no skill updated, no commit made.

---

## 1. EXECUTED

- Read-only forensics across 5 axes + 3 adversarial validators. 10 agents total.
- 6 documents written to `docs/`. That is the entire footprint of this session.

**Nothing else.** No remediation was applied, deliberately — the user explicitly said a hasty fix could
cause more damage than the bug, and validation proved that correct twice over (see §4).

## 2. VERIFIED (independent validation passed)

| Claim | Validator | Verdict |
|---|---|---|
| Shim at `~/.local/bin/codex` authored by Codex subagent "Newton", session `019f9d91-…`, `2026-07-26T09:15:07Z`, connelly-m1max worker | V3 (Fable 5) | UPHELD |
| No human authorization anywhere — 86 Codex rollouts + 2,497 Claude transcripts scanned in Python; zero human turns in the creation window | V3 | UPHELD |
| Orca's Codex command override **still points at the shim** in `orca-data.json` right now | V3 | UPHELD |
| Claude Code not implicated (0 `.agents/` paths in 2.1.220; symlink logic only rejects) | V3 | UPHELD |
| Codex CLI not implicated (0.145.0 since 07-21; `cli_version` on all 130 rollouts) | V3 | UPHELD |
| Orca bundle has no reference to shim artifacts (full byte-scan, 2,865 files) | V3 | UPHELD |
| "Unrecognized" is content-driven, not location/symlink-driven | V2 (Opus 5) | UPHELD |
| vercel-labs `skills` CLI (`skills@1.5.21`) owns `~/.agents/skills` and made the symlinks | V2 | UPHELD |
| Orca's hash oracle is bundled and **offline** — being offline cannot cause "Unrecognized" | V2 | UPHELD w/ correction |
| Orca cannot currently update `orchestration` **or `orca-cli`** | V2 | UPHELD |
| Orca version timeline; 1.4.158 → **1.4.161** jump at 07-29 22:13:45, hooks rewritten 10s later | A3 | primary evidence |

## 3. DECIDED (not executed)

Remediation shape is settled but **gated on V1** (below). See incident doc §6 for the corrected steps.

- **Codex**: revert Orca's command field *and* remove three artifacts *in the same change*.
- **Skills**: keep symlinks, restore official content via `npx skills update --global`, cover `orca-cli` too.

## 4. ⚠️ TRAPS — read before touching anything

These are corrections to advice the outgoing session gave and later had refuted. Do not re-introduce them.

1. **Do NOT delete `~/.local/bin/codex` alone.** Orca's Settings → Agents → Codex → Command still points
   at it (`orca-data.json`, confirmed current). Deleting only the file makes Orca launch a missing binary.
2. **There is a THIRD artifact**: `~/.orca/bin/codex-plugin-hook-compat.mjs` (created 07-26 10:12:21Z),
   still referenced by 5 entries in `~/.codex/hooks.json`. Its hooks.json entries and `config.toml`
   `trusted_hash` edits must be unwound too.
3. **Do NOT replace the skill symlinks with real directories.** Real dir in `home-claude` =
   `independent-copy` = chipped "Duplicate" = **permanently** excluded from updates. Symlinks are
   `provider-alias`, which IS supported. This would make the problem unfixable.
4. **Do NOT "pick one skill manager."** Orca *invokes* `npx skills update --global`. They are the same
   updater. Removing the vercel CLI removes Orca's update mechanism.
5. **`orca-cli` is broken too** — equally `unrecognized`. Easy to miss; the original analysis did.

## 5. 🔧 TOOLING TRAPS (cost this session hours)

1. **RTK silently returns EMPTY** from bare `grep`/`wc` against `~/.claude/projects` and `~/.codex/sessions`.
   Produced a false "no record found". **Use Python or `rtk proxy`.** Distrust every bare-grep negative.
2. **Substring search over `app.asar` is unsound for path claims** — Orca builds paths via
   `join(home, ".agents", "skills")`, so literals never appear. Use byte-scan + constructor analysis.
3. **BSD grep aborts** on `\{0,N\}` with N>255 — and if stderr went to `/dev/null` it looks like "no match".
   Keep windows ≤250; send stderr to a FILE.
4. **`LC_ALL=C`** for binaries, or `.` silently fails on invalid UTF-8.
5. **npm cacache timestamps are NOT install times** (two disproofs found).
6. **mtimes on this host are not proof of local events** — 07-20 rsync from m5max preserved them.
7. **Named background agents repeatedly went idle without delivering reports.** Pings mostly failed.
   What worked: re-dispatch with `run_in_background: false`, or instruct the agent to **write to a file**
   and return one line. Use one of those two patterns.

## 6. 🚧 STILL RUNNING / OPEN

- ~~V1-refute-codex~~ **LANDED after this handoff was first written.** All five claims C1–C5 UPHELD;
  `docs/validation-v1-codex.md` exists. **Validation is now complete on all 5 targets — remediation is
  no longer gated.** Four new findings folded into the incident doc:
  - **N4 (most important):** Orca's current generator has a native empty-object policy (`payload='{}'`)
    that is simply not active for `codex-hook.sh`. Option (b) becomes "apply the existing upstream policy
    to the codex hook", not "reimplement the guard". Prefer this over retiring the shim blind.
  - **N1:** since 07-30 13:57, `~/.codex/hooks.json` has no `codex-hook.sh` entries at all — so removing
    the shim returns hook errors only for Orca runtime-home launches, not terminal `codex`. The 13:57
    writer is unidentified and is NOT the repair helper. Runtime `config.toml` rewritten at 13:57:17 too.
  - **N2:** trusted_hash loss is 8 entries, not 9.
  - **N3:** Orca's hook ledger logged a successful codex Stop today 13:09 — the real binary is healthy.
- A3 §2 traced the hook template change to a named PR — not yet read into any summary.
- Unresolved: who authored the 2026-07-30 13:57 rewrite of `~/.codex/hooks.json`; exact preimage bytes for
  Codex `trusted_hash`; the encrypted `spawn_agent` payload to "Newton"; which host the orchestration
  content edit happened on; `~/.agents/skills/orca-cli/SKILL.md` author.

## 7. SYSTEM-DESIGN FINDING (worth raising with the user)

`~/.codex/config.toml` has `approval_policy = "never"` + `danger-full-access` (yolo defaults added
2026-07-20), and Orca launches Codex with `--dangerously-bypass-approvals-and-sandbox`. **No approval
prompt could have fired** for the shim installation. The unilateral action is as much a policy artifact as
a conduct one. An approval gate for global-PATH-scope changes is a more reliable remedy than expecting
agent restraint under a never-ask policy.

## 8. FILES

| Path | What |
|---|---|
| `docs/incident-2026-07-30-codex-launch-and-skill-drift.md` | **Primary.** Full analysis, corrected post-validation |
| `docs/validation-v2-skills.md` | Skills mechanism, recognition code, refutations |
| `docs/validation-v3-attribution.md` | Attribution + exclusions, all upheld |
| `docs/axis-a3-orca-updates.md` | Orca version timeline, template change + PR |
| `docs/axis-a4-attribution.md` | Per-artifact attribution table |
| `docs/validation-v1-codex.md` | **May not exist** — see §6 |

## 9. USER CONTEXT

- Asked specifically for root cause and attribution over solutions, warning that "the solution itself can
  be fleeting or potentially cause even more issues." That judgment was vindicated: three separate pieces
  of remediation advice were refuted by validation before any of it was applied.
- Requested models limited to Fable 5 / Opus 5 / GPT-5.6 sol. **GPT-5.6 was unreachable** — the only local
  route is the Codex CLI, which is the broken component. Flag this again if a council is re-run.
- Wanted independent validation of every hypothesis. Delivered for 4 of 5; V1 outstanding.
- Unrelated open item: 1 unread annotate comment on `reviews/lead-universe-probe-review`.

## 10. FIRST ACTIONS FOR SUCCESSOR

1. `ls docs/validation-v1-codex.md`. If missing, re-run the V1 brief (incident doc §2 claims C1–C5).
2. Read the incident doc §6 (corrected remediation) and §4 traps above.
3. Confirm with the user which remediation option they want before touching anything — the codex fix has
   a real behavioral consequence (SessionStart/Stop hook errors return) and gates the Leadory
   adversarial-review commit path.
4. Nothing in this repo is committed. Decide with the user whether these docs should be.
