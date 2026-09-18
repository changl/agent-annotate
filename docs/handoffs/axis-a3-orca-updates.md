# Axis A3 — Orca updates: forensic report

**Resolved model id (environment block): `claude-opus-5[1m]`**

**Completeness: MEDIUM.** The version timeline, the codex-hook template change, and the skills
recognition mechanism are resolved with primary evidence and quoted code. Two things are NOT
resolved: which `topology` label Orca assigns to a symlinked skill placement, and who authored the
2026-07-30 13:57:06 rewrite of `~/.codex/hooks.json`. Both are stated as gaps, not guessed.

Read-only forensics. No file was created, modified, or repaired outside this document and a
scratchpad. `codex` was never run. No mutating `orca` command was issued.

---

## 0. Methodology, and the two corrections

### Correction 1 — RTK grep interception

Bare shell `grep` under the RTK hook can silently return empty output, turning a real match into a
false negative. **Every load-bearing negative in this report is Python-derived**, not shell-grep
derived:

- `app.asar` searches use a Python `mmap.find()` byte scan (`scratchpad/asar_search.py`).
- Log scans use Python `json`/`glob` (`scratchpad/first_seen.py`, `scan_update_events.py`).

That covers all "0 occurrences" claims below: `codex-plugin-hook-compat`, `plugin-hook-compat`,
`repair-codex-hooks`, `.agents/skills`, `vercel-labs`.

One non-load-bearing negative — a `grep -i "skill\|freshness"` over my own generated
`spannames.txt` — was a bare shell grep and is **discarded**. The conclusion it would have
supported (no skills spans in trace telemetry) is independently established by the Python scan.

### Correction 2 — this host is m1max, an rsync target of m5max (mtimes preserved, 2026-07-20)

This invalidated my original evidence basis for the hook-rewrite attribution. **Re-derived without
mtime, the conclusion holds.** See §3.

---

## 1. ORCA VERSION TIMELINE

Install events: `/Users/changlee/Library/Caches/com.stablyai.orca.ShipIt/ShipIt_stderr.log`
(`"Detected this as an install request"`). Versions: Orca's own updater telemetry in
`~/Library/Application Support/orca/logs/main.trace.ndjson*` — spans
`{"kind":"updater","updater.stage":"install","updater.version":"…"}` plus breadcrumbs
`updater_update_downloaded` / `updater_quit_and_install_started`. Times local (PDT).

| Installed | Version | Evidence path |
|---|---|---|
| 2026-07-16 15:41:52 | unknown | ShipIt log only |
| 2026-07-17 22:10:32 | unknown | ShipIt log only |
| 2026-07-19 14:24:34 | unknown | ShipIt log only |
| 2026-07-20 22:32:17 | unknown | ShipIt log only |
| 2026-07-22 11:42:05 | unknown | ShipIt log only |
| 2026-07-22 14:42:13 | unknown | ShipIt log only |
| 2026-07-23 11:16:38 | **1.4.152** | `main.trace.ndjson.9` |
| 2026-07-24 16:52:13 | **1.4.155** | `main.trace.ndjson.8` |
| 2026-07-26 14:45:55 | **1.4.158** | `main.trace.ndjson.2` |
| 2026-07-29 22:13:45 | **1.4.161** | `main.trace.ndjson.1` |
| 2026-07-30 10:57:06 | **1.4.162** (current) | `main.trace.ndjson`; `~/Library/Caches/orca-updater/pending/Orca-1.4.162-arm64-mac.zip` |

Field direction verified rather than assumed: the Jul 30 event names `1.4.162` and the resulting
bundle **is** 1.4.162, so `updater.version` carries the **incoming** version.

> **This host never ran 1.4.159 or 1.4.160.** It jumped 1.4.158 → 1.4.161 on 2026-07-29 22:13:45.
> This single fact explains most of what follows.

Corroborating local runtime artifacts — `~/Library/Application Support/orca/daemon/`:
`daemon-v25` (Jul 22 15:17), `v26` (Jul 23 11:16), `v28` (Jul 26 14:46), `v29` (Jul 29 22:13:56),
`v30` (Jul 30 10:57:17). `orca-local-build.json` declares `daemonProtocolVersion: 30`.

Current bundle: `Info.plist` `CFBundleShortVersionString = 1.4.162`;
`Contents/Resources/orca-local-build.json` →
`buildId "1.4.162-9eede0084dff27165cfc03a05254fddb62e29bcc-arm64"`.
`app-update.yml` → `owner: stablyai / repo: orca / provider: github / updaterCacheDirName: orca-updater`.

### GitHub releases (repo is public — updater fetches unauthenticated)

| Tag | created_at | published_at | tag → commit |
|---|---|---|---|
| v1.4.159 | 2026-07-27T07:02:09Z | 07:28:22Z | — |
| v1.4.160 | 2026-07-29T04:47:59Z | 05:23:49Z | — |
| v1.4.161 | 2026-07-29T07:39:38Z | 08:23:24Z | `df84fe6bc972a389ccb235dbe7450cf958107bb2` |
| v1.4.162 | 2026-07-30T09:22:57Z | 09:43:13Z | `e058429e113ac95ce8e5b6cff85a039ebeeef333` |
| v1.4.163-rc.0 | — | 2026-07-30T20:27:17Z | pre-release, already published |

### Verdict on the inherited claim "1.4.161 released 2026-07-29 07:45, commit 66a4897"

- **Date 2026-07-29 — CONFIRMED.**
- **Time 07:45 — NOT CONFIRMED.** No field carries it. Tag-object tagger date and release
  `created_at` are both `07:39:38Z`; `published_at` is `08:23:24Z`.
- **Commit `66a4897` — REFUTED as the git tag commit.** `v1.4.161` dereferences to
  `df84fe6bc972a389ccb235dbe7450cf958107bb2`.
- **Caveat that keeps this honest:** build commit ≠ tag commit on this channel. For 1.4.162 the
  on-disk build commit is `9eede008…` while the tag commit is `e058429e…`. v1.4.160 shipped
  `feat(updater): switch to validated local mac builds` (#10889), which explains the split. So
  `66a4897` plausibly *was* 1.4.161's build commit, read from that version's
  `orca-local-build.json` — now overwritten and unrecoverable.
  **UNVERIFIABLE as a build commit; REFUTED as a tag commit.**

---

## 2. TEMPLATE CHANGE — resolved, with a named PR

**`payload=$(cat)` → `payload=$({ command -p cat 2>/dev/null || cat; })` shipped in Orca v1.4.160.**

v1.4.160's release notes contain verbatim:

> `fix(hooks): drain POSIX hook stdin without PATH by @nolainjin in https://github.com/stablyai/orca/pull/10885`

v1.4.159's notes contain no hooks entry. The current bundle emits exactly that form —
`/Applications/Orca.app/Contents/Resources/app.asar` @ byte offset 9274945:

```js
var $c="{ command -p cat 2>/dev/null || cat; }",wn=`${$c} >/dev/null 2>&1 || :`;
function j(e="exit"){
  let t = e==="empty-object" ? ["  payload='{}'"] : ["  exit 0"];
  return [`payload=$(${$c})`,'if [ -z "$payload" ]; then',...t,"fi"]
}
```

**It reached this host on 2026-07-29 22:13:55**, carried by 1.4.161 (the host skipped 1.4.160
itself).

**No prior-version bundle exists on disk to diff against.** `~/Library/Caches/orca-updater/` holds
only 1.4.162 (`update.zip`, `pending/Orca-1.4.162-arm64-mac.zip`,
`pending/update-info.json` naming that same file). The five ShipIt scratch directories under
`/var/folders/80/…/T/com.stablyai.orca.ShipIt.*` are all **empty** (64 bytes). `~/.Trash` holds no
Orca bundle. So the version attribution rests on release notes plus local artifacts, never on a
bundle diff. Stated plainly: **a direct cross-version template diff cannot be done from on-disk
artifacts on this host.**

### Reconciliation with the peer finding about the wiped `printf '{}\n'` guard

The bundle's generator (quoted above) has **two** empty-payload modes: `exit 0` (default) and
`payload='{}'` (`"empty-object"`). The regenerated `~/.orca/agent-hooks/codex-hook.sh` on this host
uses the **`exit 0`** variant — lines 3–5 are:

```sh
if [ -z "$payload" ]; then
  exit 0
fi
```

That is consistent with a peer's report that regeneration removed a `{}`-emitting guard: the
generator still *supports* emitting `{}`, but the codex hook is not generated in that mode.
Flagged as reconciliation with a peer claim **I did not independently verify** — I did not see the
pre-regeneration file.

---

## 3. CORRECTION 2 APPLIED — mtime re-examined; conclusion holds on other evidence

The uniform 2026-07-29 22:13 mtime is **not** what the attribution rests on. Re-derived:

**(a) Birthtime rules out the 2026-07-20 rsync.** From `stat -f "%SB | %Sm | %Sc"`:

- `~/.orca/agent-hooks/` **directory**: birthtime **2026-07-14 22:51:38** — predates the rsync,
  matches Orca's first run on this host (same second as many `~/Library/Application Support/orca`
  artifacts).
- All hook scripts: birthtime **2026-07-29 22:13:55/56**, identical to mtime **to the second**.

`rsync -a` preserves mtime; it preserves **neither birthtime nor ctime**. A file rsynced on
2026-07-20 would carry birthtime 2026-07-20. These carry Jul 29 — nine days later.

**(b) An undisclosed later rsync is also excluded.** Such a run would create the file locally
(birthtime = rsync time) while restoring the source mtime — so birthtime and mtime would
**diverge**. Here they are equal to the second, which is the signature of a local create-and-write.

**(c) ctime cannot be transported at all.** It is set by the local kernel on every inode change and
no copy tool can forge it. Eleven scripts carry ctime **2026-07-30 10:57:16**; `codex-hook.sh`
carries **2026-07-30 13:57:06**. Both are local events on this host.

**(d) Three local-only artifacts sit inside the same seconds** — none is an mtime, none is
meaningfully rsyncable:

- `ShipIt_stderr.log` (written by Squirrel *on the installing machine*): "Installation completed
  successfully" 22:13:51, "Successfully launched application at file:///Applications/Orca.app/"
  22:13:53.
- `~/Library/Application Support/orca/daemon/daemon-v29.sock` — a **unix socket**, created 22:13:56.
- `main.trace.ndjson.1` — written by the local main process, recording `updater.install` for
  1.4.161 at 22:13:45.

**(e) The writer is content-conditional — proven, not inferred.** At the 1.4.162 launch
(2026-07-30 10:57:16) the eleven other scripts had **ctime bumped while mtime held** — metadata
touched (chmod), content untouched. So neither an app-version change nor a daemon-protocol change
(v29→v30, same launch) forces a rewrite. The Jul 29 22:13:55 write therefore marks a **genuine
content change**. New inodes confirm atomic replace, matching the bundle's `Rt()`:
`writeFileSync(tmp, …)` → `renameSync(tmp, target)`.

> **Verdict: local Orca 1.4.161 wrote these files on this host at 2026-07-29 22:13:55–56 —
> CONFIRMED on birthtime, ctime, and local-only runtime artifacts, independent of mtime.**

**File-count discrepancy:** I count **12** scripts, not 13 —
`antigravity, claude, codex, command-code, copilot, cursor, devin, droid, gemini, grok, kimi,
openclaude` (each `-hook.sh`). `ls -laR` shows no subdirectories and no hidden files. Orca's
installer table covers 14 agents; `amp` and `hermes` have no script here. Given this host is a sync
target, m5max may legitimately hold 13 — worth checking there rather than assuming a miscount.

### `~/.codex/config.toml` trusted_hash loss (peer finding, mechanism identified)

`~/.codex/config.toml` has birthtime = mtime = **2026-07-29 22:13:56** — the *same second* as the
hook regeneration — and ctime 2026-07-30 13:57:06. That timing is consistent with the peer report
that 9 `trusted_hash` entries were dropped at regeneration.

The mechanism exists in the bundle. Orca keeps `.bak` copies and can **restore** them:

```js
function Mo(e,t){                       // backup-with-symlink-guard
  try{ if(lstatSync(t).isSymbolicLink()) throw new Error(`Refusing to overwrite symlinked backup: ${t}`) }
  catch(o){ if(o.code!=="ENOENT") throw o }
  let n=`${t}.${process.pid}.${randomUUID()}.tmp`;
  try{ Mc(e,n), ut(n,t) } finally { rmSync(n,{force:!0}) }
}
function _t(e,t){                       // rollback/restore prior contents
  if(!t.existed){ try{ unlinkSync(t.restorePath??e) }catch(r){ if(r.code!=="ENOENT") throw r } return }
  …  writeFileSync(o,t.contents,{mode:t.mode}), ut(o,n)
}
```

and a trust-promotion path `xk()` that reads the real codex home's `hooks.json`, compares it with
the runtime home's, and snapshots via `Ni()` → `.orca-hook-trust-provenance.json`. A backup/restore
cycle is exactly how `trusted_hash` entries would vanish while a same-second `.bak` retains them.
**I did not read the `.bak` contents myself** — that part is the peer's finding; I supply the
mechanism, not the confirmation.

---

## 4. SKILLS SUBSYSTEM

### 4.1 How Orca decides a skill is "recognized" — bundle code, quoted

```js
var GLOBAL_SKILL_LOCK_SCHEMA_VERSION = 3;

function globalSkillLockPath(args) {
  const stateHome = args.stateHome === void 0
    ? (args.homeDir === void 0 ? (process.env.XDG_STATE_HOME ?? null) : null)
    : args.stateHome;
  return stateHome
    ? (0, node_path.join)(stateHome, "skills", ".skill-lock.json")
    : (0, node_path.join)(args.homeDir ?? (0, node_os.homedir)(), ".agents", ".skill-lock.json");
}

async function readGloballyUpdatableSkillLocks(args = {}) {
  try {
    const parsed = JSON.parse(await (0, node_fs_promises.readFile)(globalSkillLockPath(args), "utf8"));
    if (typeof parsed.version !== "number" || parsed.version < GLOBAL_SKILL_LOCK_SCHEMA_VERSION
        || !parsed.skills || typeof parsed.skills !== "object" || Array.isArray(parsed.skills))
      return new Map();
    return new Map(Object.entries(parsed.skills).filter(([, value]) => {
      const entry = value;
      return typeof entry.skillFolderHash === "string" && entry.skillFolderHash.length > 0
          && typeof entry.skillPath === "string"       && entry.skillPath.length > 0
          && typeof entry.source === "string"          && entry.source.length > 0;
    }).map(([name, value]) => [name, value.skillFolderHash]));
  } catch { return new Map(); }
}

const SUPPORTED_GLOBAL_SKILL_TOPOLOGIES = new Set(["canonical-copy", "provider-alias"]);

function trustLockInstalledRevision(installation, globalSkillLocks) {
  return installation.status === "unrecognized"
      && SUPPORTED_GLOBAL_SKILL_TOPOLOGIES.has(installation.topology)
      && installation.observedGitTreeSha != null
      && installation.observedGitTreeSha === globalSkillLocks.get(installation…
}
```

Also present nearby: `sha !== lockHash)) convergable.delete(name);` and
`const MAXIMUM_REPOSITORY_SKILL_ROOTS = 128;`.

IPC surface (unminified, offset ~5950382):

```js
electron.ipcMain.handle("skills:discover", …);
electron.ipcMain.handle("skills:freshnessInventory", async () => { return scanInventory(); });
electron.ipcMain.handle("skills:startUpdateRun", async (_event, names) => runner.start(…));
electron.ipcMain.handle("skills:cancelUpdateRun", …);
electron.ipcMain.handle("skills:acknowledgeUpdateRun", …);
electron.ipcMain.handle("skills:getUpdateRun", …);
// event: contents.send("skills:updateRun", run)
```

### 4.2 Where the official copy comes from — TWO sources

**Source 1 — the external CLI's lock file.** `globalSkillLockPath()` resolves to exactly
`~/.agents/.skill-lock.json`. **Orca ships no independent registry of what a skill should contain;
it reads the vercel-labs `skills` CLI's lock.** Confirmed on disk (schema `version: 3`, exactly
Orca's required floor):

```json
{"version": 3, "skills": {
  "orchestration": {"source": "stablyai/orca", "sourceType": "github",
    "sourceUrl": "https://github.com/stablyai/orca.git",
    "skillPath": "skills/orchestration/SKILL.md",
    "skillFolderHash": "9aa26fde93c0592e5983cdca1ccd33b402802255",
    "installedAt": "2026-07-15T06:24:21.282Z", "updatedAt": "2026-07-25T00:09:08.174Z"},
  "find-skills": {"source": "vercel-labs/skills", … },
  "computer-use": {"source": "stablyai/orca", … },
  "orca-linear":  {"source": "stablyai/orca", …, "updatedAt": "2026-07-26T21:47:17.597Z"}, … }}
```

Note the hard floor: `parsed.version < 3 → return new Map()`. If that CLI bumps its schema, Orca
silently sees **zero** locks and every skill loses its rescue path. The file sits exactly at 3.

**Source 2 — a bundled snapshot** for Orca's own skills. Schema in the bundle:

```js
var snapshotShape = {
  releaseRevision: z.number().int().positive(),
  packageDigest:   sha256Schema,                       // /^[a-f0-9]{64}$/
  gitTreeSha:      z.string().regex(/^[a-f0-9]{40}$/),
  files: z.array(z.object({ path, size, executable,
    classification: z.enum(["text","binary"]),
    exactSha256: sha256Schema, textNormalizedSha256: sha256Schema.nullable() })), …
};
```

alongside `skillsPath = pathApi.join(install.installPath, "skills")` (inherited ground truth) and
`/Applications/Orca.app/Contents/Resources/skills`.

**So the two managers are not independent — Orca is a front-end over the CLI's lock**, and
`stablyai/orca` is one of that CLI's configured sources. This is why every skills bullet in
1.4.162's changelog says *"the CLI"*: #11105 *stop reporting a failed update when the CLI
succeeded*; #11110 *stop offering an update the CLI provably cannot perform*; #11220 *trust the
updater's lock when a run installs content newer than the bundle*; #11051 (1.4.160) *require
updater registration*.

Direct corroboration that Orca **drives** that CLI: `daemon.log` records
`session-created … "ephemeral-setup-terminal:skill-freshness-update-terminal@@02e2bc4a"` at
`2026-07-26T21:46:39.459Z`, and the lock's `orca-linear` entry carries
`updatedAt "2026-07-26T21:47:17.597Z"` — 38 seconds later, matching `.skill-lock.json` mtime
`2026-07-26 14:47:17`. Orca spawned a terminal; the CLI ran; the CLI wrote the lock.

### 4.3 Is the freshness/update feature NEW in the last few days?

**REFUTED as stated — but the verdict it renders is one release old on this host.**

- The subsystem was already live **and executing** on 1.4.158: the freshness-update terminal above
  ran 2026-07-26, and `daemon.log` begins `2026-07-15T05:51:38Z`, so the window is fully covered.
  The lock's earliest `installedAt` is `2026-07-15T06:24:21Z`.
- v1.4.160 contains *fixes to* a pre-existing updater plus `feat(skills): run skill updates in the
  background without a terminal` (#10843) — which is precisely why the Jul 26 run still used a
  terminal.
- **What changed is the classification.** v1.4.162 — installed here **2026-07-30 10:57:06**, hours
  before the observation — carries seven skills changes: #11105, #11110, #11128 (*stop the skill
  review dialog contradicting the badge that opens it*), #11220, #11221 (*stop the scan issue
  budget evicting a read failure*), #11248 (*tell the user how to fix a skill the updater cannot
  converge*), #11249 (*stop calling the updater's own install a modified copy*, merged
  2026-07-29T00:27:27Z).

Feature: **not new.** Classifier: **one release old on this host.**

### 4.4 Does a SYMLINK trip it independently of content edits?

**HYPOTHESIS — likely YES, via the topology gate.** The rescue path is gated twice, and the first
gate has nothing to do with content:

```js
SUPPORTED_GLOBAL_SKILL_TOPOLOGIES.has(installation.topology)       // gate 1: placement shape
&& installation.observedGitTreeSha === globalSkillLocks.get(…)      // gate 2: content
```

Only `"canonical-copy"` and `"provider-alias"` qualify. **A placement whose topology falls outside
those two remains `unrecognized` even when its git tree SHA matches the lock exactly** — a pure
path-shape failure.

Reinforcing, from PR #11249's description: *"Git tree shas cover contents, modes, symlinks, and
nested dirs — sha equality is byte-for-byte folder equality."* A tree containing a symlink entry
(mode 120000, blob = target path) hashes differently from the target's real subtree unless
canonicalised first. #11249 reclassifies *"a canonical/provider-alias placement classified
`unrecognized` whose observed git tree sha equals the lock's `skillFolderHash`"* — i.e. this exact
failure was real, and 1.4.162 repaired it **for those two topologies only**.

The peer finding fits: the CLI installs into `~/.agents/skills/<name>` and symlinks
`~/.claude/skills/<name>` → there. That is very plausibly the `"provider-alias"` case (Claude being
the provider), which 1.4.162 should now handle. **I did not locate the code that assigns the
`topology` label**, so I cannot confirm which label a symlink receives. See GAPS.

Orca does perform symlink canonicalisation elsewhere in the same codebase, so the capability
exists:

```js
function bn(e){ let t=!1;
  try{ t=lstatSync(e).isSymbolicLink() } catch(n){ if(n.code!=="ENOENT") throw n; return e }
  return t ? realpathSync.native(e) : e }
```

---

## 5. CODEX HOOKS & RUNTIME HOME

**Trigger is codex pane spawn/attach — not app launch, not update.** Timestamps for 2026-07-30
(`stat -f "%SB | %Sm | %Sc"`):

| Path | birth | mtime | ctime |
|---|---|---|---|
| `~/.codex/hooks.json` | **13:57:06** | 13:57:06 | 13:57:06 |
| `~/.codex/config.toml` | Jul 29 22:13:56 | Jul 29 22:13:56 | **13:57:06** |
| `…/orca/codex-runtime-home/home/hooks.json` | Jul 29 22:13:56 | Jul 29 22:13:56 | Jul 29 22:13:56 |
| `…/codex-runtime-home/home/config.toml` | **13:57:17** | 13:57:17 | 13:57:17 |
| `…/codex-runtime-home/home/config.toml.bak` | — | 13:57:06 | — |
| `…/codex-runtime-home/home/.orca-hook-trust-provenance.json` | — | 13:57:06 | — |
| `~/.orca/agent-hooks/codex-hook.sh` | Jul 29 22:13:55 | Jul 29 22:13:55 | **13:57:06** |

`daemon.log`'s final line:
`{"ts":"2026-07-30T20:57:06.727Z","event":"session-attached","sessionId":"07771d76-…::/Users/changlee/projects/agent-annotate/codex@@65762ea3"}`
— `20:57:06Z` **is** 13:57:06 PDT. A codex pane attached; in the same second Orca ran its codex hook
reconcile.

Bundle code confirming Orca owns both `hooks.json` locations (offset ~9337659):

```js
return { configPath: join(e,"hooks.json"),
         tomlPath:   join(e,"config.toml"),
         scriptPath: join(e,".orca","agent-hooks","codex-hook.sh"), … }
```

**`~/.codex/hooks.json`'s current content is NOT Orca-authored.** Created fresh (new inode) at
13:57:06, it contains only entries of the form:

```
/usr/local/bin/node '/Users/changlee/.orca/bin/codex-plugin-hook-compat.mjs' '<plugin>@claude-plugins-official' '<Event>' 0 0
```

Python byte-scan of the 122 MB bundle: `codex-plugin-hook-compat` → **0**, `plugin-hook-compat` →
**0**, `repair-codex-hooks` → **0**. And `~/.orca/bin/` holds exactly two files, both created while
**1.4.155** was the running version:

- `codex-plugin-hook-compat.mjs` — birth 2026-07-26 03:12:21, mtime 03:13:21
- `repair-codex-hooks.mjs` — birth 2026-07-26 02:15:07, mtime 03:37:55

`~/.orca/bin` is therefore a **locally-authored directory living inside Orca's config tree**. Both
files and `/usr/local/bin/node` exist and are `-rwxr-xr-x`, so "shim missing" is **not** the current
failure mode.

Orca's own managed codex hooks live in the runtime home
(`codex-runtime-home/home/hooks.json`, 5408 B, untouched since Jul 29 22:13:56) — that is what
`CODEX_HOME` points at.

---

## 6. FINDINGS

1. **CONFIRMED** — Version timeline as tabled: 1.4.152 / 1.4.155 / 1.4.158 / 1.4.161 / 1.4.162,
   from Orca's own `updater.install` telemetry cross-checked against ShipIt install events.
2. **CONFIRMED** — This host skipped 1.4.159 and 1.4.160 entirely, jumping 1.4.158 → 1.4.161 on
   2026-07-29 22:13:45.
3. **CONFIRMED** — `payload=$({ command -p cat …; })` originates in v1.4.160 via PR #10885
   (`fix(hooks): drain POSIX hook stdin without PATH`); it reached this host on 2026-07-29 22:13:55
   carried by 1.4.161.
4. **CONFIRMED** — No prior-version Orca bundle survives on disk; a direct cross-version template
   diff is impossible here. Attribution rests on release notes plus local artifacts.
5. **CONFIRMED (correction 2 re-derivation)** — The hook regeneration was a **local write by Orca
   1.4.161**, not rsync-inherited state: file birthtime == mtime to the second (rsync preserves
   neither birthtime nor ctime); directory birthtime 2026-07-14; ctime 2026-07-30; and local-only
   ShipIt log, unix socket, and trace telemetry inside the same 11-second window.
6. **CONFIRMED** — The hook writer is content-conditional: 1.4.162's launch chmod'd (ctime moved)
   without rewriting (mtime held), so version and daemon-protocol changes alone do not trigger a
   write.
7. **CONFIRMED** — Orca reads `~/.agents/.skill-lock.json` — the vercel-labs `skills` CLI's lock,
   schema v3 — as its recognition oracle. Code and on-disk file both quoted.
8. **CONFIRMED** — Recognition = observed git tree SHA vs lock `skillFolderHash`, gated by
   `SUPPORTED_GLOBAL_SKILL_TOPOLOGIES = {"canonical-copy","provider-alias"}`.
9. **CONFIRMED** — Orca additionally carries a bundled snapshot manifest
   (`releaseRevision`/`packageDigest`/`gitTreeSha`/per-file `exactSha256`) for its own skills.
10. **CONFIRMED** — The skills freshness/update subsystem existed and ran on 1.4.158
    (2026-07-26 14:46:39, `daemon.log`); its *classification* changed in 1.4.160 and again in
    1.4.162.
11. **CONFIRMED** — Orca drives the external CLI: freshness terminal at 2026-07-26T21:46:39.459Z,
    lock `updatedAt` 2026-07-26T21:47:17.597Z, 38 s later.
12. **HYPOTHESIS** — A symlinked placement whose `topology` falls outside `{canonical-copy,
    provider-alias}` stays `unrecognized` regardless of a matching hash. Gate quoted; the
    topology-assignment code was not located.
13. **CONFIRMED** — The codex hook reconcile fires on **codex pane attach** (2026-07-30 13:57:06,
    matched to `daemon.log`), not on app launch or update.
14. **CONFIRMED** — `~/.codex/hooks.json`'s current content is not Orca's: zero bundle references to
    the shim it invokes; that shim and `repair-codex-hooks.mjs` are local files from 2026-07-26.
15. **REFUTED / UNVERIFIABLE** — `66a4897` is not v1.4.161's tag commit (`df84fe6b…`), and cannot be
    checked as a build commit because that bundle is gone. "07:45" matches no field.
16. **CONTRADICTS BRIEF** — 12 files in `~/.orca/agent-hooks/`, not 13.
17. **CONFIRMED (mechanism only)** — Orca's `Mo()` backup and `_t()` restore functions provide the
    exact mechanism by which `trusted_hash` entries would be dropped while a same-second `.bak`
    retains them. The peer's observation of 9 dropped entries is consistent; I did not read the
    `.bak` myself.

---

## 7. CAUSAL VERDICTS

### (a) Codex launch failure — Orca updates: **INSUFFICIENT EVIDENCE, leaning NOT the proximate cause**

**For implication:** the hook template changed under the user on 2026-07-29 22:13 (1.4.160's #10885
arriving via 1.4.161); `~/.codex/config.toml` was rewritten in the same second, coinciding with the
peer-reported loss of 9 `trusted_hash` entries; Orca rewrote the runtime `config.toml` at
pane-attach time today; and 1.4.161→1.4.162 carried four codex behaviour changes (#11224 AI-Vault
bridged-session home, #11228 stale-pane prompt, #11076 spurious shell readings, #11059 Codex v2
subagents).

**Against:** the hook script itself cannot break a launch — every path in
`~/.orca/agent-hooks/codex-hook.sh` terminates `exit 0`, and it only POSTs to
`127.0.0.1:$ORCA_AGENT_HOOK_PORT/hook/codex`; #10885 is stdin-drain *hardening*, not a behaviour
change. Decisively, the file governing codex `SessionStart` in the default codex home —
`~/.codex/hooks.json` — carries **zero** Orca-managed entries and points solely at a local script
Orca has never heard of. Orca touched that home in the same second, but no bundle code emits those
commands, and I cannot attribute the 13:57:06 rewrite from timestamps alone.

**Best single lead for whoever continues:** the trusted_hash loss at 2026-07-29 22:13:56 is the most
plausible Orca-caused contribution, because Orca's own trust-promotion path (`xk()` / `Ni()` /
`Mo()` / `_t()`) is the only code I found that writes those entries. That is a config-trust failure,
not a hook-script failure.

### (b) Skills "unrecognized" — Orca updates: **IMPLICATED, but the causal direction is the opposite of the hypothesis**

1.4.162 landed 2026-07-30 10:57:06, hours before the observation, and is the first build on this
host containing #11249's topology-gated lock rescue plus six sibling skills fixes. The classifier is
genuinely one release old here — the correlation is real and the mechanism is now identified.

But the state was **not** newly surfaced by a brand-new feature: the subsystem ran on 1.4.158 four
days earlier, and 1.4.162's changes overwhelmingly *reduce* false "modified" reports. A skill still
reading `Unrecognized` **under 1.4.162** most likely has a genuine mismatch — either edited content
(tree SHA ≠ lock `skillFolderHash` under any canonicalisation), or a placement whose `topology` is
outside the two supported values.

The two-manager situation is the likely amplifier: the vercel-labs CLI owns `~/.agents/skills` and
symlinks into `~/.claude/skills`; Orca reads that CLI's lock; any placement the CLI creates that
Orca does not classify into a supported topology **cannot** be rescued by a hash match.

**Cheap decisive next test:** for the affected skill, compare the git tree SHA of
`~/.agents/skills/<name>` against its `skillFolderHash` in `~/.agents/.skill-lock.json`.
Equal → the topology gate is the cause (symlink shape). Unequal → genuine content edit, and Orca is
reporting correctly.

---

## 8. GAPS

1. **Versions for the six installs 2026-07-16 → 2026-07-22 are unrecoverable here.**
   `main.trace.ndjson.9` starts 2026-07-23; `daemon.log` reaches 2026-07-15 but logs only
   `protocolVersion`, not app version.
2. **No prior-version bundle exists**, so every cross-version claim rests on release notes plus
   local artifacts, never a bundle diff.
3. **The `topology` assignment code was not located** — so whether a symlinked
   `~/.claude/skills/<name>` is labelled `provider-alias` (rescued under 1.4.162) or something else
   (not rescued) is **UNRESOLVED**. This is the highest-value remaining question. Extracting the
   archive (`npx @electron/asar extract`) and reading the `main/skills` chunk would settle it; my
   byte-scan found the gate but not the labeller. `scanInventory` is not a top-level `function`
   declaration, which is why name-based searches missed it.
4. **The author of `~/.codex/hooks.json`'s 13:57:06 rewrite is unproven.** `fs_usage` or `opensnoop`
   across a codex pane spawn would settle it; that requires running codex, which was outside my
   read-only scope.
5. **Sync-target caveat now applies to everything content-based.** Files whose provenance I
   established via birthtime/ctime are safe, but any file read only for *content* could carry m5max
   state. Specifically unvalidated against m5max: `~/.agents/.skill-lock.json` (mtime 2026-07-26
   14:47:17 — *before* the Jul 29/30 updates, so its hashes may predate whatever the CLI did on
   m5max) and the two `~/.orca/bin/*.mjs` files.
6. **Inherited, not independently re-derived:** the Jul 26 recovered copy containing
   `payload=$(cat)`; `skillsPath = join(install.installPath,"skills")`; the i18n string inventory;
   the wiped `printf '{}\n'` guard; the 9 dropped `trusted_hash` entries and the `.bak` that retains
   them; the rsync date and the m1max/m5max topology itself. All are consistent with what I found;
   none were re-verified by me.
7. **Not investigated:** the contents of the two `~/.orca/bin/*.mjs` files, and which host or
   session authored them.

---

## 9. Evidence paths (absolute)

- `/Applications/Orca.app/Contents/Info.plist`
- `/Applications/Orca.app/Contents/Resources/orca-local-build.json`
- `/Applications/Orca.app/Contents/Resources/app-update.yml`
- `/Applications/Orca.app/Contents/Resources/app.asar` (offsets 9274945, 9337659, ~5950382)
- `/Users/changlee/Library/Caches/com.stablyai.orca.ShipIt/ShipIt_stderr.log`
- `/Users/changlee/Library/Caches/orca-updater/pending/update-info.json`
- `/Users/changlee/Library/Application Support/orca/logs/daemon.log`
- `/Users/changlee/Library/Application Support/orca/logs/main.trace.ndjson` (+ `.1` … `.9`)
- `/Users/changlee/Library/Application Support/orca/daemon/` (daemon-v25 … v30)
- `/Users/changlee/Library/Application Support/orca/codex-runtime-home/home/hooks.json`
- `/Users/changlee/Library/Application Support/orca/codex-runtime-home/home/config.toml{,.bak}`
- `/Users/changlee/Library/Application Support/orca/codex-runtime-home/home/.orca-hook-trust-provenance.json`
- `/Users/changlee/.orca/agent-hooks/codex-hook.sh`
- `/Users/changlee/.orca/bin/codex-plugin-hook-compat.mjs`
- `/Users/changlee/.orca/bin/repair-codex-hooks.mjs`
- `/Users/changlee/.codex/hooks.json`, `/Users/changlee/.codex/config.toml`
- `/Users/changlee/.agents/.skill-lock.json`
- GitHub: `api.github.com/repos/stablyai/orca/releases/tags/v1.4.{159,160,161,162}`,
  `/git/ref/tags/v1.4.16{1,2}`, `/git/tags/<sha>`, `/pulls/11249`
