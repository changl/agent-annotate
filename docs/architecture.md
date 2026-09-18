# Architecture

The detailed reference (data shapes, HTTP surface, event list) is
[skills/claude/annotate/references/architecture.md](../skills/claude/annotate/references/architecture.md).
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
sections with five regression thresholds — see
[telemetry-and-eval.md](../skills/claude/annotate/references/telemetry-and-eval.md).

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

The Python package is canonical. `skills/claude/annotate` is the Claude Code
skill and holds the one set of references; `skills/codex/annotate` and the
Codex plugin say the same thing in Codex wording and point at those
references. Neither wrapper owns the comment data or the browser
implementation.
