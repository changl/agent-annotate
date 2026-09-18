# Validation v2 — adversarial review of Section 3 ("Unrecognized" skill)

**Validator model (env block):** `claude-opus-5[1m]`
**Date:** 2026-07-30
**Mode:** strictly read-only. No `codex` run. No Orca skill-update command run. No state mutated.
**Target:** `docs/incident-2026-07-30-codex-launch-and-skill-drift.md` §3 only.

The prior analysis reasoned about Orca's skill recognition **from i18n strings alone**. Orca's actual
recognition code and its bundled hash artifacts were located and read. They settle every question in §3,
and they contradict several of the document's supporting claims.

---

## 0. The artifact the prior analysis never found

Orca ships a **local, offline hash oracle** for skills:

```
/Applications/Orca.app/Contents/Resources/skills/current-manifest.json   (5,882 B)
/Applications/Orca.app/Contents/Resources/skills/snapshot-registry.json  (73,629 B)
/Applications/Orca.app/Contents/Resources/skills/release-mapping.json    (13,284 B)
```

Loaded by `readSkillBundleArtifacts(resourceRoot)` (app.asar @ ~5,906,292) with three plain
`readFile` calls against `join(resourcesPath, "skills")`. **No network access on this path.**

`snapshot-registry.json` carries every historical release revision of every Orca skill
(orchestration: 28 revisions; orca-cli: 35), each with `packageDigest`, `gitTreeSha`, and per-file
`exactSha256` / `textNormalizedSha256` / `identitySha256`.

Note what it does **not** contain: the skill file **bodies**. Orca can *detect* divergence but cannot
*repair* it itself — see §5.

---

## 1. The recognition code (verbatim, app.asar)

```js
function freshnessStatus(snapshot, current) {
	if (!snapshot) return "unrecognized";
	if (snapshot.releaseRevision > current.releaseRevision) return "newer-known";
	return snapshot.packageDigest === current.packageDigest ? "current" : "outdated";
}
```

`snapshot` comes from `matchingKnownSnapshot(observed, knownSnapshots(...))`, where `observed` is the
result of `observeSkillPackage(topology.resolvedPath)` — i.e. **the realpath-resolved directory content**.

Topology is a **separate, parallel axis** recorded as its own field:

```js
const SUPPORTED_GLOBAL_SKILL_TOPOLOGIES = new Set(["canonical-copy", "provider-alias"]);
```

```js
function skillTopologyPriority(topology) {
	switch (topology) {
		case "canonical-copy": return 3;
		case "independent-copy": return 2;
		case "provider-alias": return 1;
		case "external-link":
		case "broken-link":
		case "read-only":
		case "repo-scope":
		case "plugin-cache": return 0;
	}
}
```

And the classifier that decides where a symlink lands:

```js
async function classifyHomeSkillTopology(root, unresolvedPath, canonicalRootPath) {
	...
	const linked = logicalStat.isSymbolicLink();
	resolvedPath = await realpath(unresolvedPath);
	...
	const canonicalRoot = await realpath(canonicalRootPath).catch(...);
	const isCanonicalTarget =
		normalizedSkillIdentityPath(dirname(resolvedPath)) === normalizedSkillIdentityPath(canonicalRoot);
	let topology;
	if (linked) topology = isCanonicalTarget ? "provider-alias" : "external-link";
	else if (rootOrProviderParentLinked) topology = "external-link";
	else topology = root.id === "home-agents" ? "canonical-copy" : "independent-copy";
	if (topology !== "external-link" && !await writableDestination(resolvedPath)) topology = "read-only";
	...
}
```

The UI chip:

```js
function locationChip(installation) {
	if (installation.status === "unrecognized" && installation.topology === "plugin-cache") return "plugin-cache";
	if (installation.status === "unrecognized") return "unrecognized";
	if (installation.status === "inaccessible") return "inaccessible";
	switch (installation.topology) {
		case "independent-copy": return "duplicate";
		case "external-link":    return "external-link";
		...
		case "canonical-copy":
		case "provider-alias":
			if (installation.status === "current") return "current";
			return installation.status === "newer-known" ? "newer" : null;
	}
}
```

**Reading:** "Unrecognized" is emitted *only* from `status`, and `status` is derived *only* from hashing
the realpath-resolved content against the bundled snapshot registry. A folder-level symlink is resolved
before hashing and is classified as `provider-alias`, which is an explicitly **supported** topology.

---

## 2. Orca's skill roots — the document's §3.2 quote is the wrong function

The incident doc states Orca resolves skills as
`skillsPath = pathApi.join(install.installPath, "skills")`.

That line is real but belongs to `resolveClaudePluginSkillSources` — the **Claude *plugin cache*** root
builder, driven by `~/.claude/plugins/installed_plugins.json`. It is not how home skills are discovered.

The actual root table is `buildSkillDiscoverySources` (app.asar @ ~4,193,719):

```js
const roots = [
	source$1("home-codex",   "Codex home",       join(home, ".codex", "skills"),  "home", ["codex"],        "codex"),
	source$1("home-agents",  "Agent skills home",join(home, ".agents","skills"),  "home", ["agent-skills"], null),
	source$1("home-claude",  "Claude home",      join(home, ".claude","skills"),  "home", ["claude"],       "claude"),
	source$1("codex-plugin-cache", ...),
	source$1("home-grok", ...), source$1("home-opencode", ...), source$1("home-pi", ...),
	source$1("home-gemini", ...), source$1("home-antigravity", ...), source$1("home-cursor", ...)
];
```

and in `inventorySkillFreshness`:

```js
const canonicalRootPath = homeRoots.find((root) => root.id === "home-agents")?.path;
if (!canonicalRootPath) throw new Error("Missing canonical agent skills root");
```

**`~/.agents/skills` is Orca's designated canonical skills root.** It is not a foreign directory Orca is
unaware of. `classifyHomeSkillTopology` returns `"canonical-copy"` (highest priority, 3) precisely when
`root.id === "home-agents"`.

This refutes the document's §4 assertion that Orca has "zero references to … `agents/skills` anywhere in
its bundle." The *literal string* `"agents/skills"` indeed occurs 0 times — the path is built by
`join(home, ".agents", "skills")` — which is exactly how a substring grep produced a false negative.

---

## 3. Orca's updater **is** the vercel `skills` CLI

`SkillUpdateRunner.start()` (app.asar @ ~5,944,000):

```js
const npxCommand = resolveCommand$1("npx");
const npxArgs = ["--yes", "skills", "update", ...canonicalNames, "--global", "-y"];
```

and Orca **reads the vercel CLI's lock file** as its own input:

```js
function globalSkillLockPath(args) {
	const stateHome = ...;
	return stateHome ? join(stateHome, "skills", ".skill-lock.json")
	                 : join(args.homeDir ?? homedir(), ".agents", ".skill-lock.json");
}
var GLOBAL_SKILL_LOCK_SCHEMA_VERSION = 3;
```

It even honours the lock as a trust anchor that *overrides* an Unrecognized verdict:

```js
function trustLockInstalledRevision(installation, globalSkillLocks) {
	return installation.status === "unrecognized"
		&& SUPPORTED_GLOBAL_SKILL_TOPOLOGIES.has(installation.topology)
		&& installation.observedGitTreeSha != null
		&& installation.observedGitTreeSha === globalSkillLocks.get(installation.name)
			? { ...installation, status: "newer-known" }
			: installation;
}
```

`.skill-lock.json` appears exactly twice in the entire 122 MB bundle (offsets 5,938,187 / 5,938,281),
both inside `globalSkillLockPath` — i.e. **Orca only ever reads it, never writes it.**

**Therefore the document's central §3.2 thesis — "Two skill managers now own the same skills … Neither
knows about the other" — is false.** There is one pipeline: the vercel CLI installs into
`~/.agents/skills` and symlinks outward; Orca reads that lock, hashes those directories, and delegates
updates back to `npx skills update --global`. The symlink layout is the design, not a collision.

---

## 4. Ground-truth measurement of the live tree

`~/.claude/skills/{orchestration,orca-cli,orca-linear,computer-use,find-skills}` are relative symlinks
into `../../.agents/skills/*` — confirmed. No nested symlinks exist inside any skill package, so the
`skill-package-link` throw path (§6) is not active.

SHA-256 of each live `SKILL.md` vs Orca's `current-manifest.json`:

| skill | live SKILL.md sha256 | official (rev) | verdict |
|---|---|---|---|
| computer-use | `c4a11596…c88467` | `c4a11596…c88467` (rev 8 = current) | **match** |
| orca-linear  | `39241e0a…0e7a9b` | `39241e0a…0e7a9b` (rev 8 = current) | **match** |
| orchestration| `108cfca0…f991e56` | `9ca22813…c0bd7f` (rev 28 = current) | **mismatch** |
| orca-cli     | `79febbd8…be3446` | `90228630…2ea99b` (rev 35 = current) | **mismatch** |

Searched against **every** historical revision (`exactSha256`, `textNormalizedSha256`, `identitySha256`),
and additionally against CRLF-normalised and trailing-newline-normalised variants of the live bytes:

```
orchestration  live_size=7089   has_CRLF=False   matching revisions: NONE of 1..28
orca-cli       live_size=22894  has_CRLF=False   matching revisions: NONE of 1..35
computer-use   matches revisions [6, 8]
orca-linear    matches revisions [6, 8]
```

Git tree SHAs recomputed with Orca's own algorithm (`gitObjectSha`/`skillPackageGitTreeSha`), validated
by exactly reproducing the two known-good values:

| skill | observedGitTreeSha | `.skill-lock.json` skillFolderHash | lock names revision | match |
|---|---|---|---|---|
| computer-use  | `2072384f…b5239c` | `2072384f…b5239c` | 8 | ✅ (method validated) |
| orca-linear   | `091d9bcc…3db68d` | `091d9bcc…3db68d` | 8 | ✅ (method validated) |
| orchestration | `102eba72…1f2f27` | `9aa26fde…802255` | **28** | ❌ |
| orca-cli      | `d8dbd658…cd3836` | `ded93000…6afe19` | **34** | ❌ |

**This is the decisive result, and it needs no mtime at all.** Both lock hashes name *known Orca
revisions* — the installer wrote official content. The on-disk content no longer hashes to what the
installer recorded writing. Content diverged **after** installation, provably, on hashes alone.

Because `observedGitTreeSha !== lock hash`, `trustLockInstalledRevision` does **not** rescue either
skill. Both remain `status: "unrecognized"`.

---

## 5. What Orca actually reports right now

There is **no persisted freshness state on disk**. `inventorySkillFreshness` returns an in-memory object
(`scannedAt: Date.now()`); `loadSkillBundleArtifacts` caches only in a module-level `Map`. All 10
`main.trace.ndjson*` logs (~104 MB) contain **zero** occurrences of `skillFreshness`, `unrecognized`,
`eligibleUpdateNames`, `provider-alias`, or `SkillUpdate`. The verdict therefore had to be reproduced by
re-executing Orca's algorithm, which §4 does.

Resolving the algorithm for the two divergent skills — each has two placements,
`~/.agents/skills/<name>` (`canonical-copy`) and `~/.claude/skills/<name>` (`provider-alias`), both in
`SUPPORTED_GLOBAL_SKILL_TOPOLOGIES`:

```js
function eligibleSkillUpdateNames(installations, globallyUpdatableNames) {
	...
	const convergent = entries.filter((e) => SUPPORTED_GLOBAL_SKILL_TOPOLOGIES.has(e.topology));
	if (convergent.length === 0) continue;
	const hasOutdated = convergent.some((entry) => entry.status === "outdated");
	const everyConvergentCopyIsSafeToWrite = convergent.every((entry) =>
		(entry.status === "current" || entry.status === "outdated")
		&& Boolean(entry.resolvedPath && entry.physicalIdentity));
	if (hasOutdated && everyConvergentCopyIsSafeToWrite) eligible.push(entries[0].name);
	...
}
```

`status === "unrecognized"` ⇒ `hasOutdated === false` **and** `everyConvergentCopyIsSafeToWrite === false`
⇒ **not eligible**. And the row is surfaced rather than hidden:

```js
function isSkillCopyNeedingAttention(installation) {
	return installation.status !== "current" && installation.status !== "newer-known"
		&& !(installation.status === "unrecognized" && installation.topology === "plugin-cache")
		&& !(SUPPORTED_GLOBAL_SKILL_TOPOLOGIES.has(installation.topology) && installation.status === "outdated");
}
```

**Predicted UI, derived from code:**

| skill | group status | chip on both location rows |
|---|---|---|
| orchestration | `cannot-update` | **Unrecognized** |
| orca-cli | `cannot-update` | **Unrecognized** |
| computer-use | not listed (`current`) | — |
| orca-linear | not listed (`current`) | — |

The user's phrase "unrecognized **location**" is reconciled exactly: the function producing the chip is
literally named `locationChip`, and `groupSkillFreshness` renders a per-**location** row list. The chip
text is "Unrecognized"; the *row* it sits on is a location. There is no separate location-based error.

Skip reason shown (`SKIPPED_REASON_PRIORITY` puts `unrecognized` first):

> "The copy here doesn't match the official version — it may be modified, or a different skill with the
> same name. Orca left it out of the update so it won't overwrite it. Remove it if you want Orca to
> update this skill."

---

## 6. The one way a symlink *can* independently cause "Unrecognized"

Not the folder-level symlink — a symlink **inside** a skill package:

```js
const fileStat = await lstat(absolutePath);
if (fileStat.isSymbolicLink()) throw new Error("skill-package-link");
```

and the caller maps any non-EACCES/EPERM throw straight to Unrecognized:

```js
} catch (error) {
	return { ...base,
		status: isInaccessibleError(error) ? "inaccessible" : "unrecognized",
		...
		errorCategory: errorCategory(error, "skill-package-read-failed") };
}
```

Same for `skill-path-escape`, `skill-case-collision`, `skill-package-depth-limit`,
`skill-package-entry-limit`, `skill-package-file-count-limit`, `skill-package-special-file`.

**Verified not applicable here**: every skill package under `~/.agents/skills` was walked; each contains
only regular files (orchestration 1, orca-cli 1, computer-use 1, orca-linear 1, find-skills 1,
annotate 4). No nested symlinks. So this path is a real but currently-dormant alternative cause.

---

## 7. Verdicts

### S1 — "Unrecognized is about CONTENT, not location/symlinks" — **UPHELD**

`freshnessStatus` derives the verdict solely from content hashed at `realpath`. Folder-level symlinks are
resolved first and classified `provider-alias`, an explicitly supported topology. Empirically decisive:
**all four** Orca-sourced skills under `~/.claude/skills` are symlinks with identical topology, yet two
hash as `current` and two as `unrecognized`. Location cannot be the discriminator.

*Caveat the document does not state:* a symlink **inside** a package (§6) does independently force
Unrecognized regardless of content. Not the case here, but the doc's "about content, not location" is
absolute where the code is not.

### S2 — "vercel-labs `skills` CLI owns `~/.agents/skills` and created the symlinks" — **UPHELD**

`skills@1.5.21`, `repository: git+https://github.com/vercel-labs/skills.git`, is present on this host at
`~/.npm/_npx/ac0ed6aa23b37c1e/node_modules/skills` (fetched 2026-07-30 11:57). Its
`dist/cli.mjs` contains `const AGENTS_DIR = ".agents"; const LOCK_FILE = ".skill-lock.json";
const CURRENT_VERSION = 3;` — matching the observed `"version": 3` lock exactly. `installSkillForAgent`
with the default `installMode = "symlink"` copies into the canonical dir then creates a **relative**
symlink (`relative(await resolveParentSymlinks(linkDir), target)`) — matching the observed
`../../.agents/skills/<name>` links byte-for-byte in form.

No other writer of `.skill-lock.json` was found. Orca reads it and never writes it (2 occurrences,
both in `globalSkillLockPath`).

### S3 — "Orca has official copies to compare against" — **UPHELD, with a correction that matters**

Bundled and **offline**: three JSON artifacts under `Resources/skills`, read with plain `readFile`. No
remote fetch. **Being offline therefore cannot produce "Unrecognized"** — the alternative root cause the
brief asked about is excluded.

Correction: Orca bundles **hashes only, not file bodies**. It can detect divergence but cannot restore
content; it must shell out to `npx skills update --global`, which *does* need network. So "official
copies" overstates it — official *fingerprints* is accurate.

### S4 — "A hand edit after 2026-07-25T00:09Z caused the divergence" — **PARTIALLY UPHELD; the doc's stated evidence is REFUTED**

*Upheld and strengthened*: divergence-after-install is now **proven on hashes**, not mtimes.
`.skill-lock.json` records orchestration installed at gitTree `9aa26fde…` = Orca release **revision 28**;
the live folder hashes to `102eba72…`. The installer wrote official content and the content changed
afterwards. Alternative explanations tested:

- **Orca write?** Excluded. Orca contains no writer for skill package files; `SkillUpdateRunner` only
  spawns `npx skills update`, and Orca never writes the lock.
- **The vercel CLI itself?** Excluded absent evidence of partial failure: the CLI writes content and lock
  together, and would have moved `updatedAt` past 2026-07-25T00:09:08Z and left a *released* tree hash.
  It did neither. (A separate CLI run on 2026-07-26T21:47:17Z updated **orca-linear** only, whose lock
  entry moved and whose content is `current` — consistent behaviour, and a control case.)
- **m5max rsync?** **Cannot be excluded.** A later `rsync -a` would carry both modified content and a
  foreign mtime. The 07-26 13:28 mtime may describe an m5max event. Which host the edit occurred on is
  **undetermined**.

*Refuted*: the doc's supporting evidence — claude-mem observation #9881, an edit adding warnings about a
nonexistent `orca orchestration read` command and an invalid `--full` flag. The live
`~/.agents/skills/orchestration/SKILL.md` contains **zero** occurrences of `orca orchestration read`,
`--full`, `check --all --json`, `NOT a command`, `does not exist`, or `not a real`. **That draft was
never applied to this file.** The §3.3 attribution chain is unsupported.

*Not established*: "**hand** edit". Authorship (human vs. agent vs. script) and host are both unproven.
The defensible claim is "content diverged from the installed revision after 2026-07-25T00:09:08Z, author
and host unknown."

### S5 — "Orca is not currently able to update these skills" — **UPHELD**

Not from any on-disk Orca state — none exists (§5) — but from re-executing `eligibleSkillUpdateNames`
against measured hashes. `unrecognized` fails both `hasOutdated` and `everyConvergentCopyIsSafeToWrite`,
so neither name reaches `eligibleUpdateNames`; `groupSkillFreshness` marks the group `cannot-update` and
`isSkillCopyNeedingAttention` keeps it visible. Chip is **Unrecognized** (not a location chip) on both
rows. Confirmed for orchestration **and**, contrary to the document, for **orca-cli**.

---

## 8. New defects the document missed

1. **`orca-cli` is equally broken and is never mentioned.** Live `SKILL.md` (22,894 B) matches none of
   its 35 official revisions, and its git tree `d8dbd658…` differs from its own lock hash
   `ded93000…` (= revision 34). It is a second `Unrecognized` / `cannot-update` skill, with the same
   root cause. Every §6 "Skills" remediation step must cover it.

2. **The recommended fix is counterproductive.** §6 Skills step 2 says to "replace the symlinks with real
   directories under `~/.claude/skills`". Under `classifyHomeSkillTopology`, a real directory in
   `home-claude` is `independent-copy`, which is **not** in `SUPPORTED_GLOBAL_SKILL_TOPOLOGIES` — it is
   chipped **"Duplicate"** ("A separate copy of this skill, installed apart from the main one") and is
   permanently excluded from `eligibleSkillUpdateNames`. The current symlinks are `provider-alias`, which
   **is** supported. The proposal converts a supported layout into an unsupported one. The correct fix is
   to restore official content in `~/.agents/skills` and **keep the symlinks**.

3. **"Decide on one manager" rests on a false premise.** §6 Skills step 1 says running both the vercel CLI
   and Orca's updater "guarantees recurring Unrecognized". They are the same updater — Orca *invokes*
   `npx skills update --global` and consumes the CLI's lock. Removing the vercel CLI would remove Orca's
   own update mechanism.

4. **§3.4's conclusion is right, its reasoning is incomplete.** `~/.codex/skills` is a first-class Orca
   root (`home-codex`), and its contents were confirmed to lack all Orca skills. But absent directories
   yield `null` from `classifyHomeSkillCandidate` (ENOENT), so Codex's missing skills are silently
   invisible in Orca's UI — they are not reported as broken. Worth stating explicitly.

5. **Methodological defect that produced §4's false negative.** The claim "zero references to
   `agents/skills` anywhere in its bundle" came from a substring search. Orca builds the path with
   `join(home, ".agents", "skills")`, so the literal never appears while the reference plainly exists.
   Any "Orca has zero references to X" conclusion in this document derived the same way is unsafe;
   `repair-codex-hooks` and `local/bin/codex` (§4, Symptom 1) were not re-tested here and inherit this
   doubt.

6. **`find-skills` and `annotate` were not evaluated against the oracle.** `find-skills` is sourced from
   `vercel-labs/skills`, not `stablyai/orca`, and is absent from Orca's manifest — Orca will never
   classify it. `~/.agents/skills/annotate` is likewise unmanaged and absent from both the manifest and
   the lock, so §3.5's drift finding is correct but Orca will never surface it.

---

## 9. Method notes

- All binary scanning done in Python over `mmap`, never bare `grep` (RTK returns empty against these
  trees). All stderr redirected to files.
- `app.asar` recognition module isolated to offsets ~5,895,000–5,965,000; roots table at ~4,193,719;
  UI chips at ~17,213,800.
- Git tree SHA reimplementation validated by exactly reproducing `computer-use` = `2072384f…b5239c` and
  `orca-linear` = `091d9bcc…3db68d` before being trusted for the divergent skills.
- Nothing was written to `~/.agents`, `~/.claude/skills`, or Orca state. No update command was run.
