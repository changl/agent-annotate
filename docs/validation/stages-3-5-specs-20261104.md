# Stages 3–5, ready to build: bookkeeping, routine scripts, SQLite

## Summary for Chang

**What changes for you:** nothing on the page looks different. Agents spend less on bookkeeping, page updates stop failing on numbering, and releases reach the Macs without long step-by-step sessions.

| Stage | What it does | What agents stop doing | Effort |
|---|---|---|---:|
| **3. Annotate does its own bookkeeping** | Agents write a question as plain text. Annotate numbers it, links it to its section and picks the next version. An agent can replace one section instead of rewriting the whole page. | Choosing card numbers and versions, writing card JSON, copying and patching old versions, retrying after numbering errors | 6–8 days |
| **4. Scripts for routine jobs** | One script installs a release on a Mac, restarts its pages, checks them and rolls back on failure. Board, disk and session checks run on a timer with no AI. | Rollouts done by hand, hourly sweep workers, watching test output | 4–5 days |
| **5. Database** | Each page keeps its records (questions, answers, versions, history) in one SQLite file instead of about ten JSON and lock files. Pictures and page files stay as files. | Nothing new. Saves become all-or-nothing, so the short answers from stages 1 and 3 can be trusted. | 11–14 days |

**Measured on a copy of the FLD page:**
- A question written as plain text takes 8 tokens of markup; the same question in JSON takes 76.
- FLD's whole history (1,741 questions and comments, 655 versions, 49,990 history lines) loads into SQLite in half a second.
- After that, saving one change takes well under a millisecond. Today a save rewrites a 6.3 MB file in 100–180 ms.
- Reading the latest round from the database takes 0.7 ms. Today it means scanning a 15.6 MB file.

**How live pages move:**
- **Stages 3 and 4 change no stored data.** Existing numbers, links and history stay as they are. The old card format keeps working.
- **Stage 5 moves each page on its own:** stop the page, copy its records into the database, check that every record matches, then restart it.
  - The old files keep being written for one release, so going back to the files is one command per page.
  - FLD goes last on this Mac, after the smaller pages have run on the database for a week.
  - The M5 and M1Max16 follow only after your yes, one Mac at a time.

**Decisions for you (asked on the page when each stage starts):**
1. **One database file per page, instead of one per Mac (recommended).** A page folder stays the single thing you copy, back up, archive or merge, and one busy page can't slow the others. The plan said one file per Mac; that works too, but every page would share one writer.
2. **For Stage 5's rehearsal: copy the M5's pages to this Mac.** Rehearsing on copies of all three Macs needs your yes for the M5 copy. The M1Max16 has no pages.

**Stages 0–2 must leave four things in place** (details in §0): one place that formats short replies, one storage entry point, stable `--json` output, and budget-test names that later stages tighten.

---

## 0. What stages 0–2 must leave in place

Stages 0–2 are being built on `changl/stage01` and `changl/stage2`. Stages 3–5 assume:

| # | Stages 0–2 must leave this | Used by |
|---|---|---|
| L1 | **One receipt formatter** (e.g. `receipts.py`: `publish_line()`, `resolve_line()`) used by every one-line output; `--json` keeps today's full payloads byte-compatible | 3 (publish/section receipts), 4 (rollout line), 5 (db lines) |
| L2 | **Batch resolve inside one `_locked_store` transaction** through a single function (e.g. `resolve_many(store, handles, version)`), not a CLI loop over `cmd_resolve` | 5 swaps the backend under it |
| L3 | **Worklist handles are stable**: number when unique on the page, comment ID when numbers collide (FLD has 67 numbers shared by carried-forward rows of one question) | 3 keeps the same handle rules for new cards |
| L4 | **`bench.py --budget` names and budgets in one data file** (e.g. `bench/budget.json`) with actions `read_round`, `resolve_round`, `ask_one`, `publish_small`, `small_round`, `session_start`; `ask_one`, `publish_small`, `small_round` marked *expected to fail until stage 3* | 3 flips them to must-pass; 5 runs them as a regression gate |
| L5 | **`orch_cost.py` categories stable**, including "annotate commands", "page drafts", "raw-store reads" and "release and rollout" | before/after for 3 and 4 |
| L6 | **No new per-page store files or lock files.** Stage 2 leases live in the Orca run directory, not in page directories | 5 imports exactly the files listed in §5.3 |
| L7 | **Number allocation untouched**: `sync_server._assign_item_number`, `_pin_item_numbers`, `cli._item_numbers` | 3 builds on them |
| L8 | **Stage 2's `run-summary` accepts extra one-line sources** (a file glob or list) | 4 adds the sweep line |
| L9 | **Sandbox fixtures on ports 18700–18799** for: first publish, three- and five-answer rounds, number conflict, failed publish, dead owner, interrupted Send | 3 and 5 acceptance |

Already shipped, so not in Stage 3: owner rebind on resume (`delivery.refresh_session_owners`, called from both hooks, PR #97), and the reviewer-facing "Waiting: the agent's session is not running" label (`shell.js:loadDelivery`).

---

## 3. Annotate does its own bookkeeping (6–8 worker-days)

### 3.1 Commands and output

All receipts use L1. Failures leave the previous version visible and print one line ending in `· fix: …`.

| Command | Output (default, one line) |
|---|---|
| `annotate publish SLUG --from page.md` | `v412 live · 3 cards #19086–#19088` |
| `annotate publish SLUG --from results.md --section Results` | `v412 live · Results replaced · 1 card #19089 · 2 kept` |
| `annotate publish SLUG --from page.md --stage` | `v412 staged · show it: annotate publish SLUG --version v412` |
| `annotate publish SLUG --version v412` (show a staged draft) | `v412 live · 3 cards #19086–#19088` |
| any refusal | `not live: card "Ship it?" cites cmp:chekout, not on this page · fix: cite one of cmp:checkout, s:results` |
| `annotate new DIR --from page.md --publish` (unchanged verb) | same as the first line; `--version` and `--ask` become optional |

Rules:
- `SLUG` may be a slug, `project/slug` or a page directory. `publish DIR` without `--from` keeps today's meaning (start the server, register the route).
- **The next version is picked automatically:** max(history, staged drafts) + 1, or v1 for a new page. `--version vN` still works and is still refused when vN is already visible (`review_versions.require_draft`).
- **`--ask` is implied** when the page has cards. The "this page has cards; publish with --publish --ask" error goes away.
- **`--section NAME`** matches an H2 by its heading text (case-insensitive) or its anchor (`s:results`). The base is the newest source: `source/<current>.md`, or the newest staged draft if one is newer. The command replaces that H2 block (heading through the line before the next H2) with the file's contents. If the file has no H2, the original heading is kept. The combined source is written to `source/vN.md` as today. Unknown section: `not live: no section "Resuls" on v411 · fix: --section one of Results, Plan, Questions for reviewer`.
- `--fixes vN` passes through unchanged.
- This replaces the plan's separate `draft` verb: one verb with `--stage` gives the same result.

### 3.2 Plain-text cards

````markdown
```ask
Use one-step payment?
The receipt remains visible in the comparison.
+ One step: Payment and receipt share a screen.
- Keep current: Payment stays on a separate screen.
```
````

| Line | Meaning |
|---|---|
| first line | prompt (required) |
| plain lines before the options | context |
| `+ Label: consequence` | the recommended option (exactly one `+`, or none) |
| `- Label: consequence` | another option; option ID = `slugify(label)` |
| optional trailing keys | `see: cmp:checkout, s:plan` (evidence; default is the enclosing section), `impact: high`, `blocking: yes`, `catalog: yes` (plan approval) |
| `#19012 Use one-step payment?` | keeps an existing question's number and identity; used to re-pose an unanswered question in a rewritten section |

- **Measured with `o200k_base`:** this card has 8 markup tokens; the same card as today's JSON fence has 76 (`/tmp/aa-plan345-scripts/markup_tokens.py`).
- The parser produces exactly today's card dict (`decision_request` with prompt, context, recommendation, options, evidence), so the server, the browser and stored data stay unchanged.
- The `cards` JSON fence stays accepted with today's rules.
- `annotate ask --from cards.json` is unchanged.

### 3.3 Numbers, anchors and carried questions

- **Allocation happens at generate time, under the store lock that `_write_files` already holds.**
  - next = max over `cli._item_numbers(store)` and every `reserved` list in `.review-drafts/*.json`, + 1.
  - New `ask` cards get `number = next…` and `anchor_id = d:q<number>`, so every existing reader keeps working.
  - The draft file records `reserved: [19086, 19087, 19088]`.
- **Commit stays `_commit_review` → `POST /api/comments/batch` with `publish_version`.** `_assign_item_number` already rejects a used number with 409.
  - On 409 the CLI regenerates the draft with fresh numbers and commits again, at most twice, without output.
  - A third conflict prints `not live: numbers kept colliding with another publish · fix: rerun the same command`.
- **Rules relaxed only for software-numbered cards:**
  - `_round_contract_problems` and `cmd_ask` (strictly increasing, `d:qN` match, required evidence) skip cards that came from an `ask` fence.
  - The evidence default (the enclosing section anchor) satisfies `card_refusal`.
  - JSON cards keep every rule.
- **Carrying questions over:**
  - A section not replaced by `--section` keeps its cards. They are carried with the same number and anchor through the existing carry-forward path.
  - In a replaced section, or a whole-page publish, an `ask` card with `#N` keeps that question. Unanswered questions that were omitted are withdrawn, as today (`_withdraw_unasked`).
- **FLD:** numbers stop at 19,085 today. New cards continue from 19,086. Old numbers, IDs and URLs never change.

### 3.4 Data model

No new storage. The only additions are optional fields:
- `reserved` (list of int) in `.review-drafts/vN.json`;
- `source_kind: "ask"` on cards in `versions/vN.cards.json`.

Old servers accept the batch unchanged, because numbers arrive explicitly, as today. So there's no capability gate and no server restart requirement beyond the normal release.

### 3.5 Tasks

| Task | Work | Depends on | Days |
|---|---|---|---:|
| 3a | `ask` fence: parser in `parse_blocks`/`Renderer.cards_block` → today's card dict; table-driven tests for every line kind and refusal | Stage 1 merged | 1 |
| 3b | Number reservation at generate, `reserved` in drafts, silent regenerate on 409 (max 2), relaxed rules for `source_kind: ask`; conflict fixture with two concurrent publishes | 3a | 1.5 |
| 3c | Next-version pick and implied `--ask` in `new`; `publish SLUG --from` / `--stage` / `--version` routing through `pagegen.cmd_new` | — | 0.5 |
| 3d | `--section NAME`: H2 split/replace on the newest source, carry for untouched sections, unknown-section refusal | 3b, 3c | 1.5 |
| 3e | Every refusal on the publish/ask path ends in one `· fix:` clause; a test lists each refusal and asserts exactly one | 3c | 0.5 |
| 3f | Skill and `references/page.md`: plain cards first, JSON as legacy; publish/section examples; skill ≤ 700 tokens (L4 `session_start`) | 3a–3d | 0.5 |
| 3g | Budget flip (L4), fixtures, five interleaved runs per ref, rehearsal on copies of FLD and Agent Annotate, release, M1 rollout | all | 1–1.5 |
| 3h | Spare for review fixes | — | 0–1 |

3a and 3c can run in parallel. 3d is the critical path.

### 3.6 Tests and measurement

- **Unit:**
  - parser cases;
  - allocation with archived and legacy numbers (`_pin_item_numbers`);
  - reservation across two drafts;
  - 409 → regenerate;
  - section replace keeps the other sections byte-identical;
  - carried card keeps its number;
  - a JSON card still gets every old rule.
- **Budget, with `bench.py --budget` on ports 18700–18799:**

| Action | Budget | Before (eval/plan) | Pass condition |
|---|---|---|---|
| Ask one question | ≤ 10 markup tokens | 76 (JSON, measured) | 8 |
| Publish one small update | 1 command, 0 retries, receipt ≤ 25 tokens, input ≈ changed section | 4.3 (AA) / 7.3 (FLD) commands per version | 1 command; `--from` file tokens ≤ 1.2 × section tokens |
| Small round, 3 and 5 answers | 3 commands | 5 / 7 (fixture), 9–12 live | 3 / 3 |
| Raw-store reads, renumbering per round | 0 | 115 raw reads, 46 `pubfix` runs | 0 in sandbox transcripts |

- **Live, with `orch_cost.py`:** three days before vs three days after, on FLD- and AA-like coordinators. Each target with its "before" value:

| Measure | Before | Target |
|---|---|---|
| Annotate's share of coordinator cost | 6.1% (FLD) / 17.4% (AA) | ≤ 3% |
| Publish attempts that print an error | 64% (FLD) / 49% (AA) | ≤ 5% |
| Card JSON tokens | 21.4k (FLD) | 0 |

  Claim a saving only if every outcome assertion holds.

### 3.7 Rollout and risks

- **Rollout:** a normal release (Stage 4 script once it exists). M1 first. M5 and M1Max16 only after Chang's yes. Already-open browser tabs need nothing: HTML is baked with number badges, as today.
- **Risks:**
  - *Section replace loses a hand edit in a staged draft.* The base is always the newest draft, and the receipt names the base version.
  - *Two sessions publish one page at once.* The reservation and the 409 regenerate cover it; the fixture proves it.
  - *Agents keep writing JSON.* Still accepted; the skill shows plain text first; `orch_cost` tracks card JSON tokens.
- **Rollback:** previous wheel. Data written by Stage 3 is readable by the old code.

---

## 4. Scripts for routine jobs (4–5 worker-days)

### 4.1 Rollout commands and output

`scripts/rollout.py` is a stdlib-only single file. It also ships as a release asset with an entry in `SHA256SUMS`, so another Mac can fetch and check the exact copy.

| Command | Output (one line per Mac) |
|---|---|
| `rollout.py plan 2.29.0 --mac M1` (read-only, runs on the target) | `M1 2.28.2 → 2.29.0 · 14 pages: 12 restart, 2 skip (no current version) · 2 skill dirs · ready` |
| `rollout.py apply 2.29.0 --mac M1` | `M1 2.29.0 ok · 12 pages restarted · 2 skipped · doctor ok · rollback kept: 2.28.2` |
| failure during apply | `M1 FAILED at restart fld-stack-round8 (identity mismatch) · rolled back to 2.28.2 · doctor ok` |
| `rollout.py apply 2.29.0 --mac M5` with no approval | `refused: M5 needs Chang's yes · ask on the page, then add --approval "card #N"` |
| `rollout.py apply 2.29.0 --mac M5 --approval "card #212"` | same as the M1 lines |
| `rollout.py rollback --mac M1` | `M1 back on 2.28.2 · 12 pages restarted · doctor ok` |
| `rollout.py status` | `M1 2.29.0 ok · M5 2.28.2 (1 behind) · M1Max16 2.29.0 ok` |

**What `apply` does, in order (each step stops on failure and rolls back):**
1. **Preflight:**
   - `plan` again;
   - the wheel and `SHA256SUMS` from the release (`updates.latest_release` logic);
   - free disk ≥ 2 GB.
2. **Backup:**
   - record the installed version and wheel URL;
   - tar the skill dirs (`~/.claude/skills/annotate`, `~/.agents/skills/annotate`) to `~/.local/share/annotate-rollout/<old>-<ts>/`.
3. **Install:** `uv tool install --python 3.12 --force "agent-annotate[mcp] @ <wheel URL>"`.
4. **Skills:** `annotate sync-skills`.
5. **Restart pages:**
   - restart each registered running page with `deployment.restart_record(project, slug)`, using `~/.local/share/uv/tools/agent-annotate/bin/python -I`;
   - pages that `plan` listed as skips are left alone and named in the line.
6. **Check:**
   - `annotate doctor --versions` must show every non-skipped component on the target;
   - one loopback `/api/capabilities` per restarted page.
7. **Record:** append one JSON line to `~/.local/share/annotate-rollout/log.ndjson` (Mac, versions, approval, result).

**Rollback** runs the same steps with the recorded old wheel and the skills tarball.

**Remote Macs:**
- The script opens an `orca --environment <M5Max|M1Max16> terminal`, fetches the release asset and checks its hash. It then runs `rollout.py apply --local …` there, waits for a marker line and prints the remote line.
- It never sends `$VARS` (they would expand locally).
- It refuses without `--approval`. The approval text goes in the log.
- `plan` on a remote Mac is also gated by the same yes, because it runs commands there.

**Agent commands per Mac: 2** (`plan`, `apply`), down from dozens (the Multi-Mac sample: 66 calls, 16 errors).

### 4.2 Housekeeping on a timer

- **One script, `scripts/sweep.py`, with subcommands.** Each prints one summary line and writes the judgment list to `~/.local/share/annotate-sweeps/latest.txt`. Stage 2's `run-summary` shows that line (L8).
- **It runs from launchd on M1** (`~/Library/LaunchAgents/com.changlee.annotate-sweep.plist`, hourly), following the existing weekly agent-tooling update job. Windmill on M1 runs in Docker and can't reach host tools without the wm-test executor, so it stays for CI only.

| Command | Output | Writes |
|---|---|---|
| `sweep.py beads` | `beads: 41 open · 6 ready · 3 in progress over 24 h · 0 closed without proof` | nothing; the judgment list names the stale beads |
| `sweep.py disk` | `disk: 35 GiB free · buses 0.4 GiB · 2 quiet buses over 30 days` | nothing; `annotate prune-bus` stays manual or `--apply` |
| `sweep.py sessions` | `sessions: 9 finished worktrees (PR merged, bead closed, clean tree) · 0 removed` | removes only with `--apply`, only when all three conditions hold. A hard-coded deny list includes `/Users/changlee/orca/workspaces/codex/rebex-library-performance` |
| `sweep.py all` | the three lines | — |

- **No AI runs in a sweep.** Judgment items wait for the coordinator's next wake. No Haiku: the model rule allows only Opus 5, Opus 5.5 and Fable 5.1.
- **Tests:** the full-suite schedule is the already-planned wm-test route (`docs/validation/ci-windmill-plan.md`, gated on its own approvals). Stage 4 adds only one line to the Stage 2 brief template: `full suite: scripts/ci.py --full → read the receipt line`.

### 4.3 Tasks

| Task | Work | Depends on | Days |
|---|---|---|---:|
| 4a | `rollout.py plan` and `status` (read-only): installed version, registry, `deployment._identity` refusal prediction, `doctor --versions` parse | L1, L5 | 1 |
| 4b | `apply` and `rollback` on the local Mac: backup, install, sync-skills, restart loop, doctor, log; failure injected at each step in a sandbox (`ANNOTATE_*` overrides, fake `uv`) | 4a | 1.5 |
| 4c | Remote execution via Orca environments, approval gate, release asset + `SHA256SUMS` in `release.py`; dry run on the target first | 4b; **Chang's yes** before the first M5 use | 1 |
| 4d | `sweep.py` (beads, disk, sessions) + launchd plist on M1 + `run-summary` line | L8 | 1 |
| 4e | Brief-template line for the full suite; docs | Stage 2 `brief.py` | 0.25 |

4a and 4d can run in parallel.

### 4.4 Tests and measurement

- **Sandbox:** every apply step fails once in a test, rolls back, and leaves the sandbox on the old version (fake `uv`, fake `orca`, pages on ports 18700–18799).
- **The gate is a test:** with no approval, a remote apply sends nothing to Orca.
- **Live targets:**
  - 2 agent commands per Mac, counted by `orch_cost.py`'s "release and rollout" category;
  - 0 rollout errors needing manual recovery in 3 consecutive releases;
  - 0 sweep worker sessions in 7 days (Orca worker list), down from hourly sweep workers.

### 4.5 Risks and rollback

- **Risks:**
  - *A script hides a Mac-specific failure.* It stops at the first unknown state and names the step. `plan` runs on the target first.
  - *uv replaces the venv while pages run.* Restarts happen after install, as today. A failed restart rolls back the whole Mac.
  - *Session cleanup removes live work.* Removal needs `--apply` and all three conditions, and the deny list is in the code.
- **Rollback:** `rollout.py rollback`. Removing the launchd plist stops sweeps.

---

## 5. SQLite store (11–14 worker-days)

### 5.1 Storage layout

- **One file per page:** `<page dir>/page.db`, WAL mode. The page directory stays the unit you copy, archive, merge and evaluate. One page's writes never wait on another's.
  - Option: one file per Mac (`~/.claude/annotate-state/annotate.db`) with a `page` column on each table. Same schema; it trades that isolation for cross-page queries.
- **Stays as files:** `versions/*.html`, `source/*.md`, `versions/*.cards.json`, `assets/`, `attachments/`, `plans/`, `approval-evidence/`, archives.
- **Stays JSON in this stage:** the registry (`state/<project>.json`). It's small, rarely written and already locked.
- **Settings:**
  - `PRAGMA journal_mode=WAL; synchronous=FULL; foreign_keys=ON; busy_timeout=5000`;
  - every write is `BEGIN IMMEDIATE`;
  - `synchronous=FULL`, because a lost answer costs more than a millisecond.

### 5.2 Schema

```sql
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
-- schema_version, imported_at, imported_from_sha, json_export_fingerprint, backend ('sqlite')

CREATE TABLE page(
  id INTEGER PRIMARY KEY CHECK (id = 1),
  name TEXT, current_version TEXT,
  owner_json TEXT,            -- current.meta.json "owner"
  meta_json TEXT NOT NULL     -- the rest of current.meta.json, minus history and content_stamps
);

CREATE TABLE versions(
  n INTEGER PRIMARY KEY,      -- v660 → 660
  state TEXT NOT NULL CHECK (state IN ('draft','live')),
  label TEXT, fixes TEXT, ts TEXT, content_stamp TEXT,
  preview_token TEXT, verified INTEGER, reserved_json TEXT,   -- from .review-drafts/vN.json
  entry_json TEXT NOT NULL    -- the full history or draft entry
);

CREATE TABLE items(
  id TEXT PRIMARY KEY,
  area TEXT NOT NULL CHECK (area IN ('anchors','archived')),
  anchor_id TEXT NOT NULL, doc TEXT, number INTEGER, version TEXT, status TEXT,
  category TEXT, origin_id TEXT, created_at TEXT, resolved_in_version TEXT,
  round_pending INTEGER NOT NULL DEFAULT 0,
  position INTEGER NOT NULL,  -- order within its anchor list, so export is byte-stable
  body_json TEXT NOT NULL     -- the whole comment dict: the source of truth
);
CREATE INDEX items_anchor ON items(anchor_id, position);
CREATE INDEX items_number ON items(number);
CREATE INDEX items_status ON items(status);

CREATE TABLE numbers(        -- one number = one question lineage
  number INTEGER PRIMARY KEY, anchor_id TEXT NOT NULL, doc TEXT, first_item TEXT NOT NULL);

CREATE TABLE approved_plans(id TEXT PRIMARY KEY, body_json TEXT NOT NULL);

CREATE TABLE events(
  seq INTEGER PRIMARY KEY, ts TEXT NOT NULL, type TEXT NOT NULL,
  item TEXT, session TEXT, round TEXT,
  bus_offset INTEGER,         -- byte offset after this line in <slug>.ndjson
  data_json TEXT NOT NULL);
CREATE INDEX events_type ON events(type, seq);
CREATE INDEX events_item ON events(item, seq);

CREATE TABLE cursors(
  kind TEXT NOT NULL CHECK (kind IN ('inbox','hook','monitor','delivery')),
  reader TEXT NOT NULL, seq INTEGER NOT NULL, bus_offset INTEGER NOT NULL,
  PRIMARY KEY (kind, reader));

CREATE TABLE deliveries(id TEXT PRIMARY KEY, round TEXT, state TEXT, row_json TEXT NOT NULL);
CREATE TABLE rounds(round TEXT PRIMARY KEY, ts TEXT, body_json TEXT NOT NULL);   -- rounds.ndjson

CREATE TABLE sidecars(       -- whole-object viewer bookkeeping, no queries need fields
  name TEXT PRIMARY KEY CHECK (name IN ('project','read-state','seen','categories','plan-topics','cards')),
  body_json TEXT NOT NULL, updated_at TEXT NOT NULL);
```

- **Why `body_json` plus promoted columns:** about 20 modules mutate the comment dict today. Keeping the dict as the record lets them keep working, and the indexed columns serve the queries that need speed.
- **Why `numbers` is separate:** on FLD, 1,462 rows carry numbers but only 1,381 numbers are distinct. All 67 shared numbers belong to rows of one question with the same anchor (carry-forward). So uniqueness belongs to the question, not the row. Import refuses a page where one number maps to two anchors and lists the rows.

### 5.3 Interfaces

New module `agent_annotate/store.py`, the only code that touches the record files:

```python
@contextmanager
def transaction(slug_dir) -> Tx: ...
# BEGIN IMMEDIATE (sqlite) or today's _locked_store flock (json). Yields:
#   tx.comments  dict in today's comments.json shape (anchors/archived/approved_plans)
#   tx.meta      dict in today's current.meta.json shape
#   tx.event(ev) append a bus event (written in the same transaction)
#   tx.sidecar(name) / tx.set_sidecar(name, value)
# On exit only changed rows are written: per-row body compared to the loaded text.

def snapshot(slug_dir) -> Snapshot           # read-only; cached per process by PRAGMA data_version
def put_items(tx, items) -> None             # hot paths: batch resolve, decision clicks
def events_after(slug_dir, seq, *, types=None, exclude=None) -> list[dict]
def backend(slug_dir) -> str                 # 'sqlite' if page.db is present and enabled, else 'json'
```

**Callers that move to `store.py`, with no behavior change in the JSON backend (task 5a):**
- `sync_server`: `_locked_store`, `_load_v2_store`, `_atomic_write_json` on `comments.json`, `_save_seen`, `_save_read_state`, `_bus_append`;
- `cli`: `_read_meta`, `_write_meta_locked`, `_write_owner_meta`;
- `review_versions`: `stage`, `activate`;
- `pagegen._write_files_locked`;
- `project_state.save_project`;
- `categories` (save findings sets);
- `delivery.dispatch_record` (journal);
- the `rounds.ndjson` appends;
- `plan_topics`.

**Read-only users switch to `snapshot()`:** `eval`, `metrics`, `review_history`, `fleet`, `reports`, `extract`, `workspace`, `mcp_server`, `consolidate`, `plans_backfill`, `long_pages`, `page_names`.

A test fails if any module other than `store.py` opens these files for writing.

**Commands** (operator-only, hidden from the agent's default help):

| Command | Output |
|---|---|
| `annotate db import SLUG\|--all [--dry-run]` | `fld-stack-round8 imported · 1,741 items · 655 versions · 49,990 events · diff 0 · 0.5 s` |
| `annotate db diff SLUG` | `fld-stack-round8 db = json · 0 differences` (or the first 5 differences and a count) |
| `annotate db export SLUG` | `fld-stack-round8 exported 8 files · bus caught up (0 events)` |
| `annotate db status` | one line per page: `fld-stack-round8 sqlite · json export current · 12 s since last write` |
| `annotate db off SLUG` | `fld-stack-round8 back on json · page.db kept as page.db.off-20261120T0100Z` |
| `annotate doctor` | one more line: `store: 13 sqlite, 1 json (agent-memory-consolidation: no current version)` |

### 5.4 Import, dual-write and rollback

- **Import** (`db import`, also run by the restart step):
  - The page server is stopped first, by the same `restart_record` loop as Stage 4.
  - Read `comments.json`, `current.meta.json`, `.review-drafts/*.json`, `project.json`, `read-state.json`, `seen.json`, `categories.json`, `plan-topics.json`, `cards.json`, `rounds.ndjson`, `state/deliveries/<project>/<slug>.json`, the bus `<slug>.ndjson`, and every cursor file for the page (`bus-offsets`, `hook-offsets`, `monitor-offsets`).
  - Write to `page.db.tmp`, then run the diff (below), then rename to `page.db`. The originals are never modified.
  - **Bus lines get `seq` in file order** with their end `bus_offset`. Lines that are invalid or incomplete are skipped and counted (FLD's copy has none; the earlier evaluation saw two).
  - **A byte-offset cursor maps to the last event with `bus_offset ≤ cursor`.** A cursor mid-line is refused and listed.
- **Diff:** export the DB to a temp directory with the same writer the dual-write uses, then compare JSON-semantically with the originals: every item, number, version, cursor and delivery row. Import fails on any difference.
- **Release N (dual-write):**
  - The DB is the authority.
  - Inside the same transaction lock, the JSON files and the NDJSON bus line are written after commit as exports, so hooks, monitors and older readers keep working unchanged.
  - The DB records a fingerprint (size, mtime_ns, sha256) of each export. At transaction start, a changed fingerprint means an old process wrote JSON: re-import that file (JSON wins), log `store_foreign_write`, then continue.
  - A crash between commit and export is repaired at server start (`db export --if-stale`).
- **Release N+1 (retire):**
  - Only after 7 days with 0 `store_foreign_write` and every page on N (`doctor --versions`).
  - Stop JSON exports except the bus, which hooks still read. Delete the `.lock` files.
  - `annotate db export` stays, for rollback and for `eval` on copies.
- **Rollback:**
  - Under N: `annotate db off SLUG`, per page. The JSON is current, so the old wheel works immediately.
  - Under N+1: `rollout.py rollback` runs `db export` for every page before installing the old wheel.

### 5.5 How live pages migrate on three Macs

| Mac | Pages | Order |
|---|---|---|
| M1 (this Mac) | 14 live registered pages (registry count, 2026-11-04) | Agent Annotate and small pages first. FLD (`fld-stack-round8`: 655 published versions up to v660, 1,741 items, 6.3 MB `comments.json`, 15.6 MB bus) after 7 days with 0 diffs and 0 foreign writes |
| M5 | counted by `rollout.py plan --mac M5` once Chang says yes | after M1's FLD has run 7 days; pages that `restart_record` refuses (other sessions' venvs, foreign ports) stay on JSON and are listed |
| M1Max16 | 0 pages | install only |

**Per page:** stop the server, import, diff 0, start the server on N with `page.db`, then make one loopback `/api/capabilities` call plus one read of the latest round. It's automatic inside `rollout.py apply`; a page that fails stays on JSON and is named in the Mac's line.

**FLD timing on a copy:**
- import 0.46 s;
- `page.db` 29.9 MB (events keep their full line);
- one item update 0.01 ms with `synchronous=NORMAL`; FULL adds one fsync;
- latest-round query 0.7 ms;
- full store load 42 ms, against 62 ms for parsing `comments.json`.

(`/tmp/aa-plan345-scripts/import_probe.py` on `/tmp/aa-refactor-eval-20261104`.)

### 5.6 Tasks

| Task | Work | Depends on | Days |
|---|---|---|---:|
| 5a | `store.py` seam with the JSON backend; move every caller in §5.3; write-path test; full suite green, no behavior change | Stage 3 merged (same functions) | 2.5–3 |
| 5b | Schema, `db import`, `db diff`, `db export`; byte-stable export; cursor mapping; refusal lists; tests on fixtures and the FLD/AA copies | 5a | 2 |
| 5c | SQLite backend under the seam: `BEGIN IMMEDIATE`, changed-row writes, events in-transaction, JSON and bus export, foreign-write detection, `data_version` cache | 5b | 3 |
| 5d | Indexed readers: `inbox --unread` and the Stage 1 worklist via `events_after`; history and metrics queries | 5c | 1 |
| 5e | Concurrency stress test: 4 server threads + 4 CLI processes, 1,000 mixed writes, 0 lost (also run against the JSON backend's known CLI content-stamp race, to prove the test bites); kill -9 mid-write recovery | 5c | 1 |
| 5f | Rehearsal on copies of all M1 pages (M5 copies after Chang's yes): import, diff, replay a round through the sandbox server, `db off` | 5b–5e | 1 |
| 5g | `rollout.py` integration (migrate inside restart, per-page fallback), `doctor` line, release N, M1 rollout; release N+1 after the 7-day soak | 5f, Stage 4 | 1–1.5 |

5d and 5e can run in parallel after 5c.

### 5.7 Tests and measurement

| Target | Today | Pass |
|---|---|---|
| Lost updates under the stress test | JSON CLI path races (documented in `_merge_content_stamp`) | 0 with SQLite |
| Publish commit (page + cards + numbers) | multi-file batch | one transaction; no `.lock` files after N+1 |
| Inbox / history query on FLD | scan of a 15.6 MB bus | < 50 ms (probe: 0.7 ms) |
| Import fidelity, FLD and AA copies | — | `db diff` 0; every item, number, version, cursor and delivery preserved |
| Goal 1 budgets (L4) | pass after Stage 3 | still pass; output byte-identical |
| Token saving | — | about 0% expected; reported, not claimed |

### 5.8 Risks

- **An old process writes JSON during N.** Foreign-write detection plus re-import. N+1 waits for 0 such writes in 7 days.
- **Hooks read the bus by byte offset.** The bus stays an export through N+1. Moving hooks to SQLite is a later, optional change.
- **Changed-row diffing misses an in-place mutation.** Rows are compared by serialized text, not by object identity. The stress test covers nested edits (replies, decision history).
- **Page directories copied while a server writes** (`eval` on copies). Copy with `sqlite3 .backup` or `VACUUM INTO`; `annotate db export` gives JSON for old tools.
- **WAL files on network shares** (`/Volumes/changlee`). `page.db` is refused on non-local volumes. The page stays on JSON and `doctor` says why.

---

## Order and totals

```
Stage 1 ─┬─ 3a ─ 3b ─┬─ 3d ─ 3e ─ 3f ─ 3g ──────────────┐
         └─ 3c ──────┘                                  ├─ 5a ─ 5b ─ 5c ─┬─ 5d ─┬─ 5f ─ 5g
Stage 2 ─── 4a ─ 4b ─ 4c (Chang's yes for M5)  4d ─ 4e ─┘                └─ 5e ─┘
```

- Stage 4 can start as soon as Stage 1's receipt formatter (L1) exists. It runs in parallel with Stage 3.
- 5a waits for Stage 3, because both edit `_write_files`, `cmd_ask` and `review_versions`.
- 5g needs Stage 4's rollout script.

| Stage | Worker-days | Gated on Chang |
|---|---:|---|
| 3 Bookkeeping | 6–8 | M5 / M1Max16 rollout |
| 4 Routine scripts | 4–5 | first remote `plan` or `apply`; any launchd job beyond M1 |
| 5 SQLite | 11–14 | per-page vs per-Mac file (decision 1); M5 copies for rehearsal; each Mac's rollout |
| **Total** | **21–27** | |

Not covered: a fresh model benchmark, M5 page inventory, and Orca's own wait semantics (Stage 2). No live page, installed annotate, other Mac or the excluded workspace was touched. Measurements used the copies in `/tmp/aa-refactor-eval-20261104`.
