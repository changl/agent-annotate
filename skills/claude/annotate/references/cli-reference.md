# annotate — CLI deep reference

Everything below is `agent_annotate/cli.py` at v2.19. Invoke it as
`annotate <cmd>` when that name on PATH runs this package (the `uv tool
install` entry point, or the shim `install-shim` writes), otherwise
`python -m agent_annotate.cli <cmd>`. `annotate doctor` prints which.
Every slug argument takes `<slug>` or `<project>/<slug>`, and `--project` is
honoured wherever a slug is.

## 1. The entry point and the shim

`uv tool install agent-annotate` (or `pip install`) puts a console script
named `annotate` on PATH; nothing else is needed. Without one,
`~/.local/bin/annotate` is a two-line `/bin/sh` shim that execs
`<python> -m agent_annotate.cli "$@"`. It carries the marker string
`agent-annotate shim`.

- `publish` writes the shim before it can print any `annotate …` line,
  but only when the path is empty or holds a shim of ours whose target is
  gone. `install-shim` also repoints a shim of ours that runs another
  install (the pre-package skill directory, say). Both are idempotent.
- A file at that path that is neither an entry point nor our shim is
  **left alone**; `install-shim --force` overwrites it. An entry point is
  never overwritten.
- `~/.local/bin` precedes `/opt/homebrew/bin` on PATH, so the shim wins over
  libgd's `annotate` image tool. `install-shim` prints what `annotate`
  currently resolves to and says so when it is not this skill.
- Every message the CLI prints uses `annotate …` only when `command -v
  annotate` actually resolves to this package; otherwise it prints the
  `<python> -m agent_annotate.cli` form.

## 2. Session identity

One id, read in this order: `CLAUDE_CODE_SESSION_ID`, `CODEX_THREAD_ID`,
`CLAUDE_SESSION_ID`, else `"unknown"`. `CLAUDE_SESSION_ID` is empty under
Claude Code; reading it was why every lease was labelled `interactive-ppid-<n>`.

The id is used in four places: the `owner_session` stamped at publish/claim,
the monitor lease label, the `X-Annotate-Session` header on every CLI request
to a server, and the per-session read cursor path.

## 3. `publish <slug-dir>` — full sequence

```bash
annotate publish /path/to/my-project/doc/    # slug = "doc", project = "my-project"
```

1. Preflight the slug dir: resolvable `current.html`, registered history in
   `current.meta.json`. Repairs are printed, not silent.
2. Write the `~/.local/bin/annotate` shim if nothing runs this package yet.
3. `node --check` every inline `<script>` block in the resolved `current.html`.
   A syntax error stops the publish (`--skip-js-lint` for emergencies).
4. If the slug is already serving, re-verify it in place and report — a live
   process is not proof that the page renders.
5. Under the project state lock: pick a free port (`lsof` liveness plus a bind
   test), register the transport route under the tunnel lock, start
   `python -m agent_annotate.sync_server`, and record the slug with
   `owner_session`, `owner_agent`,
   `owner_label` and `owner_claimed_at`.
6. Merge the `UserPromptSubmit` hook into `~/.claude/settings.json`
   (idempotent) and stamp `owner` into `current.meta.json`.
7. Run the verification gate. **No URL is printed until the page is proven to
   render.**
8. Emit `page_published`, or `page_publish_failed` on a failed stage.

Flags: `--project`, `--port`, `--transport {local,cloudflare,tailscale,
cloudflare_tailscale}`, `--hostname`, `--path-prefix`, `--skip-js-lint`,
`--no-verify`, `--verify-timeout <s>` (default 45).

### The verification gate

Three hops, each asserting on **rendered content**, never a status code:

| Stage | URL | Probe |
|---|---|---|
| `origin` | `http://127.0.0.1:<port><base>/` | HTTP, counts `data-anchor-id` elements |
| `tailscale` | `https://<host>:<serve>/<base>/` | HTTP |
| `public` | `https://<hostname>/<slug>/` | the authenticated Orca browser (`orca tab create`, then `orca eval` polled until anchors appear) |

Outcomes are `PASS`, `FAIL` and `UNAVAILABLE`. A public stage that meets a
Cloudflare Access login page is `UNAVAILABLE` with reason `access_login`, which
prints as `UNVERIFIED … (Access login)` and **exits 0** — the page is live and
merely unproven from this session. Only a genuinely broken hop (502, 404, zero
anchors on a reachable stage) prints `NOT PUBLISHED` and exits 1. Calling an
Access login page a failure is what printed `NOT PUBLISHED` over five healthy
pages and cost 5-10 recovery calls each.

## 4. Reading feedback

### `inbox <slug> [--unread] [--json] [--all-events]`

Compact by default: one line per event,
`ts  event  comment_id  anchor  author  verdict/status  text[:120]`, followed
by `decisions: N accept, N reject, N comment; undecided: <anchor ids>`.
`seen_updated`, `notice_emitted` and `inbox_read` are hidden unless
`--all-events`. `--json` prints the raw events plus `offset_from`,
`offset_to`, `decisions`, `card_count` and `undecided`.

`--unread` reads from this session's cursor and advances it, and emits
`inbox_read`. Without it, nothing is consumed and nothing is written.

**Cursors are session-keyed.** `state/bus-offsets/<session>/<project>/<slug>.offset`
is the inbox cursor; a session with no discoverable id falls back to the old
shared `state/bus-offsets/<project>/<slug>.offset`. The hook keeps its own
cursors under `state/hook-offsets/<session>/…` and never writes the inbox
cursor. In v2.18 both shared one file, so whichever session was prompted first
consumed everybody's delta and 22 of 22 observed `inbox --unread` calls
answered "(no new events)".

**Cursors reset once, on purpose.** Because the path now includes the session
id, the first notice and the first `inbox --unread` per session after v2.19
lands replay that slug's whole history. That one-time cost is the alternative
to seeding every session from a cursor that belonged to a different one.

### `cards <slug>` (alias `open-cards`)

Reads `comments.json` directly. No cursor, no server, no side effects. Prints
`id, anchor, version, verdict, prompt` plus the verdict note for `comment`
verdicts — which is where a custom-id option's `Selected: <label>` lands — and
the same decisions/undecided summary line. `--json` for the raw list.

### `watch <slug>`

`tail -f` on the bus. Blocks, prints everything, consumes no cursor.

### `monitor <slug> [--owner ID] [--takeover]`

Exclusive per-`(project, slug)` lease at
`state/monitors/<project>/<slug>/owner.json`, created `O_EXCL`. It reads from
its own cursor at `state/monitor-offsets/<project>/<slug>.offset`, so events
queued while nothing was armed replay on arming.

Two event sets, deliberately different. The lease advertises `MONITOR_EVENTS`:
`comment_created`, `comment_updated`, `comment_reply`, `comment_accepted`,
`comment_archived`, `comment_reanchored`, `comment_restored`, `session_push`,
`round_submitted` and `round_discarded`. Only `session_push` and
`round_submitted` are actually printed as `ANNOTATE_EVENT <json>`. A monitored
stream is read one line at a time by an agent, so a line has to be worth a
turn, and the actionable unit is now the round rather than the click.

Prints `ANNOTATE_MONITOR_ARMED {…}` on start and emits `monitor_armed`.
`SIGTERM` and `SIGHUP` are trapped and raise, so the `finally` block runs, the
lease is deleted, and `monitor_exited {lease_released}` is appended. Before
this, every lease on the machine was left behind pointing at a dead pid, and
the web UI reported an active listener for each one.

**The heartbeat is off by default.** It existed only to keep Claude Code's
Monitor tool from reaping a quiet stream, which no longer happens — verified
2026-09-17 against a 150-second silent stream — and it cost a wakeup every 30
seconds. Set `ANNOTATE_MONITOR_HEARTBEAT_INTERVAL` to a positive number of
seconds to opt back in under a supervisor that genuinely needs liveness
output. An unparseable value warns and stays disabled.

Arm it in the Monitor tool with `timeout_ms: 1800000` and re-arm on expiry.
`--takeover` stops only the prior monitor process; the server, comments, bus
and cursors are untouched.

## 5. Ownership

`_owner_fields()` writes four keys — `owner_session`, `owner_agent`,
`owner_label` (cwd basename plus a short id), `owner_claimed_at` — into the
registry record, and an `owner` object into `current.meta.json`:

```json
{"owner": {"session": "…", "agent": "claude-code",
           "label": "parrotfish · 8f3c", "claimed_at": "2026-09-17T10:00:00Z"}}
```

Both copies exist because a page can outlive the state file it was registered
in. The hook reads the registry copy to decide whose feedback this is; the
shell reads the meta copy to draw the desktop owner chip. `current.meta.json`
is mutated under the server's meta lock, never rewritten wholesale.

`claim <slug>` re-stamps both for the current session and emits `page_claimed`
with `previous_owner`. Use it after a handoff, or on a page published before
ownership existed.

**Pages published before v2.19 have no owner recorded**, so owner targeting
cannot narrow them and they keep notifying every session until they are
re-published or claimed. If an old page is yours, `claim` it once.

## 6. Posing cards

`ask <slug> --from cards.json [--version vN] [--author …] [--json]` posts one
`POST /api/comments/batch {items, idempotency: "anchor"}`. Idempotent by
anchor: an existing non-archived card by the same author on the same anchor is
updated rather than duplicated. On a server that 404/405/501s the batch route
it falls back to per-card `POST` + `PUT` under the same contract, and says so.
Full schema: `decision-cards.md`.

## 7. Server capabilities

`GET /api/capabilities` → `{"version": "2.19", "batch": true, "rounds": true,
"decision_schema": 2, "decision_request_cap": 8192}`. A 404 means an older
server: the chrome drops to legacy mode (one click pushes immediately, no round
bar) and `ask` uses the fallback path. New chrome against an old server and a
new server against old stored data both behave exactly as before.

## 8. The UserPromptSubmit hook

Installed into `~/.claude/settings.json` as:

```json
{"hooks": {"UserPromptSubmit": [{"hooks": [
  {"command": "<site-packages>/agent_annotate/hooks/check-comment-bus.sh",
   "type": "command", "timeout": 30}]}]}}
```

The `.sh` resolves `check_comment_bus.py` next to itself and always exits 0;
`annotate hook-check` runs the same code in-process. An existing
registration of the skill-directory copy counts as installed, so the hook
never fires twice per prompt.
The Python hook reads `session_id` and `cwd` from the stdin payload and:

- skips a slug whose registry `owner_session` is another session, unless
  `ANNOTATE_HOOK_ALL=1`; a slug with no owner recorded notifies everyone;
- counts only reviewer events (non-empty author not starting with `agent:`,
  name outside the bookkeeping set in `telemetry-and-eval.md`);
- starts its scan at `max(hook cursor, this session's inbox cursor)`, so an
  `inbox --unread` that consumed the backlog also silences the notice;
- appends `notice_emitted` and advances only its own cursor;
- holds a per-session single-flight lock (`state/hook-locks/<session>.lock.d`,
  stale after 60s) and exits 0 unconditionally.

`ANNOTATE_HOOK_DRY_RUN=1` prints what it would say and writes nothing at all —
no cursor, no bus event, no log line. It is the only safe way to run this
against the live buses. The log is `state/logs/check-comment-bus.log`.

## 9. Push delivery contract

`POST /api/push-session`, `POST /api/comments/<id>/push` and
`POST /api/rounds/submit` each append a durable `session_push`. Response:

```json
{"ok": true, "delivery_id": "2f91c7c73152", "delivery": "active_monitor",
 "monitor_count": 1,
 "monitor_owner": {"owner_session": "…", "owner_agent": "claude-code", "host": "review-mac"},
 "comment_count": 3, "comment_ids": ["…"]}
```

`active_monitor` means a live lease was verified (pid alive **and** the lease's
`bus_file` matches this server's bus) before the event was appended. `queued`
means no live lease: the event stays durable for a later monitor and for the
next hook notice. A deferred verdict inside an open round reports
`delivery: "deferred"` and emits no push at all.

## 10. Other subcommands

| Subcommand | Notes |
|---|---|
| `unpublish <slug>` | Tears down the route, stops the server, clears the registry entry. Leaves `<slug-dir>` alone. |
| `status [<slug>] [--retired]` | Registry plus liveness. A slug whose port is actually being served is not reported dead just because the recorded pid moved. Every serving row also names its owner and how long ago it was claimed, and marks `(gone)` when no process carrying that session id is running — that is the cue to `claim` it. The last line counts retired entries; `--retired` lists them. |
| `close <slug> [--older-than 30d] [--dry-run]` | Archives every decision card whose `decision_request` was never answered and whose `created_at` is older than the threshold. A decided card and an ordinary reviewer comment are never touched. Goes through the page's own archive route while it is serving, and writes `comments.json` directly (under the store lock, same archive shape) only when nothing answers on its URL. Appends exactly one `page_closed {slug, archived_ids, archived_count, remaining_open, by, session_id, older_than}`. |
| `retire <slug>\|--dead [--dry-run]` | Moves registry rows whose pid is dead and whose slug_dir has no live server to `state/retired/<project>.json`, keeping every field and adding `retired_at`. Refuses a slug that is still serving. Never touches a slug directory, a bus or the transport config, so a retired page can be re-published and pick its history back up. |
| `publish-version <slug-dir> <vN> [--label …]` | Atomically swaps `current.html` to `versions/<vN>.html` and appends to `current.meta.json.history`, exactly once per version even when re-run. Emits `version_published`. Fails if `versions/<vN>.html` is missing. |
| `addressed <slug> <id> [--response …]` | `PUT /api/comments/<id>` with `status=addressed_by_agent`. |
| `archive-comment <slug> <id>` | `POST /api/comments/<id>/archive`. |
| `migrate <legacy.html> [--slug] [--version] [--label] [--copy]` | Builds a `<slug-dir>/` beside the file: `versions/v1.html`, `current.html`, `current.meta.json`, v2 `comments.json`, legacy store backed up as `comments.<stem>.v1.bak.json`. |
| `install-shim [--force]` | See §1. |
| `doctor` | Version, invocation, what `annotate` on PATH resolves to, every root, the hook script and whether it is registered, `node`/`lsof`/`codex`, and the session id. Exit 1 only on a missing root or asset. |
| `sessions [--cwd DIR] [--json]` | Lists Codex app-server threads that can own a page. |
| `connect <slug> --thread <id> [--takeover]` | Detached `monitor --provider codex-app-server` for that thread; waits for the lease. |
| `disconnect <slug>` | Stops the live monitor for the slug; the server keeps running. |
| `send --thread <id> <message>` | One message into a Codex thread. |
| `prune-bus [--days N] [--apply]` | Archives buses quiet for N days together with every cursor pointing at them. Dry run by default. |
| `hook-check` | The UserPromptSubmit hook, in-process. |
| `mcp` | The MCP server over stdio (`agent-annotate[mcp]`). |
| `eval [--since YYYY-MM-DD] [--out-dir DIR] [--refresh-transcripts] [--state-dir] [--bus-dir] [--transcript-glob]` | Runs `eval.py` in a subprocess over the buses, the comment stores and the transcripts; writes `eval-baseline.{md,json}` to `state/logs` and prints a headline. Read-only: it is exec'd rather than imported so it cannot reach `inbox` and move the cursor it measures. Seven sections and the regression thresholds: `telemetry-and-eval.md`. |

## 11. Environment variables

Every location is owned by `paths.py` and defaults to the roots the
skill-directory install used, so a packaged install sees the same pages.

| Variable | Effect |
|---|---|
| `ANNOTATE_STATE_DIR` (alias `ANNOTATE_STATE_ROOT`) | Relocates the registry, every cursor, the leases, the locks and the logs. Default `~/.claude/annotate-state/state`. |
| `ANNOTATE_BUS_ROOT` | Relocates the buses. Default `~/.claude/annotate-bus`. |
| `ANNOTATE_CONFIG_DIR`, `ANNOTATE_PROJECTS_TOML` | Where `projects.toml` is read from. Default `~/.claude/annotate-state/projects.toml`, then the live skill's `~/.claude/skills/annotate/projects.toml`. |
| `ANNOTATE_DATA_DIR` | Bus root becomes `<data>/bus` when `ANNOTATE_BUS_ROOT` is unset. |
| `ANNOTATE_CLAUDE_SETTINGS` | The settings.json the hook installer edits. Default `~/.claude/settings.json`. |
| `ANNOTATE_SHIM_PATH` | Where `install-shim` writes. Default `~/.local/bin/annotate`. |
| `ANNOTATE_BUS_ARCHIVE_ROOT` | Where `prune-bus` moves quiet buses. |
| `ANNOTATE_TRANSCRIPT_GLOB` | The Claude Code transcripts `eval` scans. |
| `ANNOTATE_MONITOR_HEARTBEAT_INTERVAL` | Seconds between monitor heartbeats; unset or 0 disables them. |
| `ANNOTATE_CLOUDFLARE_*`, `CLOUDFLARE_*` | Cloudflare transport configuration; see the README. |
| `ANNOTATE_HOOK_ALL=1` | The hook ignores owner targeting and reports every slug. |
| `ANNOTATE_HOOK_DRY_RUN=1` | The hook prints what it would say and writes nothing: no cursor, no bus event, no log line. |

The hook flags and the relocation variables are unset in normal use. The
relocations exist so a QA run cannot touch live state; `ANNOTATE_HOOK_DRY_RUN`
is the only safe way to run the hook against the real buses. The test suite
sets every root to a sandbox in `tests/conftest.py`.
