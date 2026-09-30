# Architecture

The detailed reference (data shapes, HTTP surface, event list) is
[src/agent_annotate/skills/claude/references/architecture.md](../src/agent_annotate/skills/claude/references/architecture.md).
This page is the map.

## Runtime boundary

```text
Browser annotation shell (served chrome: shell.*, adapter.js)
        |
Persistent local HTTP runtime (sync_server.py, one process per page)
        +-- versioned HTML, content extracted at request time
        +-- comment store          <slug-dir>/comments.json
        +-- append-only event bus  <bus root>/<project>/<slug>.ndjson
        +-- page owner stamp       registry + current.meta.json
        +-- exclusive monitor lease per project/page
        |
Session side
        +-- Claude Code: UserPromptSubmit hook (attended), Monitor tool (unattended)
        +-- Codex: `annotate inbox`, optionally an app-server relay into a thread
        +-- MCP server over the same runtime
```

The runtime never restarts during an ordinary agent handoff. A session
publishes a page and becomes its owner; a later session `claim`s it. One
session may own several pages; each page has at most one owner. Comments
persist to `comments.json` whether or not anything is listening, so no
lease, monitor or notice is load-bearing for not losing feedback.

## Two buckets

Everything on disk is either **system** (this package) or **user data**
(pages, buses, cursors, configuration). `paths.py` is the only module that
knows where user data lives, and its defaults are the roots the pre-package
skill directory used, so an install sees the pages that already exist:

| Root | Default | Override |
|---|---|---|
| state: registry, cursors, leases, locks, logs | `~/.claude/annotate-state/state` | `ANNOTATE_STATE_DIR` |
| buses | `~/.claude/annotate-bus` | `ANNOTATE_BUS_ROOT` |
| `projects.toml` | `~/.claude/annotate-state/` (then the skill symlink) | `ANNOTATE_CONFIG_DIR` |
| hook registration | `~/.claude/settings.json` | `ANNOTATE_CLAUDE_SETTINGS` |
| launcher | `~/.local/bin/annotate` | `ANNOTATE_SHIM_PATH` |

Slug directories are user data and stay wherever the author put them. Moving
state to platform directories is a future migration command, never an
install side effect. The test suite sandboxes every root in
`tests/conftest.py`.

## The round model

The unit of review is a **round**, not a click.

1. The agent poses cards with `annotate ask` — one batch call, idempotent by
   anchor, each card carrying a `decision_request` with prompt, context,
   recommendation, per-option consequences, evidence, impact and blocking.
2. The reviewer answers on the page. In round mode (the server advertises
   `rounds` on `GET /api/capabilities`) each verdict is parked with
   `round_pending` and emits no push; "Finish review" submits the round,
   which emits one `round_submitted` and exactly one `session_push
   {round: true}`. "Discard pending" clears the flags with no push; "Send
   now" pushes one card.
3. The session learns about it from the hook notice (`ROUND SUBMITTED: …`)
   or from `annotate inbox <slug> --unread`, which is compact and keeps one
   cursor per session, and never acts on a partial round.
4. The agent replies and marks comments `addressed_by_agent`; confirming and
   archiving belong to the reviewer.

Old chrome against a new server, and new chrome against an old server, both
behave exactly as before the round model existed.

## Reviewer chrome is served, never baked

`shell.html`, `shell.css`, `shell.js` and `adapter.js` are loaded from the
package on every request and injected into the served document. Published
pages carry content, not chrome, so a UI fix reaches every page at once.
`extract.py` recovers the authored canvas from a page that was generated
with the chrome baked in, using the `<!-- CANVAS CONTENT -->` sentinels in
`template.html`; an explicit `content/<version>.html` overrides that
extraction. Copying a baked page into `content/` verbatim is not a migration:
its own chrome script would run beside `adapter.js`.

## Telemetry

Every request the CLI makes carries `X-Annotate-Session`, and every bus
event that request emits carries `session_id`. Publish, claim, inbox reads,
monitor arming and exit, hook notices, decision requests, batch seeds and
rounds are all events. `annotate eval` reads the buses, the comment stores
and the Claude transcripts without touching a cursor and reports seven
sections. It is run by hand, once before an improvement round and once after,
and its five thresholds are guidance for comparing the two runs rather than
gates — see
[telemetry-and-eval.md](../src/agent_annotate/skills/claude/references/telemetry-and-eval.md).

## Codex delivery

The Codex adapter uses the locally installed `codex app-server` JSON-RPC
protocol: it lists durable threads, resumes the selected thread, steers an
active turn when possible and otherwise starts a new turn, and acknowledges
delivery only after `turn/completed`. `annotate monitor --provider
codex-app-server` delivers each submitted round before advancing its cursor,
so a failed turn is retried from the bus. It reaches an idle thread as a new
turn; it is not a way to interrupt a running Codex session, and thread
selection is always explicit. A Codex agent reads its feedback with
`annotate inbox` like any other session.

## Distribution

The Python package is canonical. `src/agent_annotate/skills/claude` is the Claude Code
skill and holds the one set of references, shipped as package data and written
into a skill directory by `annotate install-skill`; `src/agent_annotate/skills/codex` and the
Codex plugin say the same thing in Codex wording and point at those
references. Neither wrapper owns the comment data or the browser
implementation.

## Managed project information, delivery and deployment (2.20)

`project_state.py` owns the independent project.json schema. The shell renders
links, progress and notes through shared native disclosures. `pagegen.py`
compiles project/details/card data into the controlled document format; shared
content.css is injected at serve time for generated pages. Custom canvases
keep their own content, anchors and extension controls.

The fsynced event bus is the source of submitted-round wake-ups. `delivery.py`
keeps its own journal/cursor, validates fresh owner/process/terminal identity
under the claim lock, and uses Orca's durable terminal-send receipt. The page
server performs delivery immediately and checks pending work every 30 seconds.
Legacy automatic Codex monitors do not deliver these rounds a second time.
`inbox --unread` emits owner acknowledgment without claiming work completion.
Unknown send outcomes remain uncertain instead of triggering duplicate input.

`updates.py` verifies stable release metadata and checksummed wheel artifacts,
then stages isolated environments. `deployment.py` reconciles registry, process
arguments and listener identity before replacing registered page servers; it
preserves owner, route, port and reviewer state and restores original commands
on failure. Prototype forks are outside this contract. `skillgen.py` records
generated file hashes and refreshes only unchanged managed deployments.

`metrics.py` derives aggregate local usage evidence without reviewer content
or cursor changes. `reports.py` combines it with existing transcript cost
estimates and compiles a short weekly page, carrying report feedback forward.
The opt-in daily updater uses the existing revive watchdog; the weekly report
uses one deterministic macOS calendar job and no model invocation.
