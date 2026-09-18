# annotate — architecture and data shapes

## 1. On-disk layout — the package

```
src/agent_annotate/
    cli.py                    ← every subcommand; `annotate` entry point
    sync_server.py            ← stdlib HTTP server, v1 + v2 modes
    paths.py                  ← the only owner of filesystem locations
    verify.py                 ← the publish gate's three probes
    extract.py                ← recovers authored content from a page
    eval.py  prune_bus.py  migrate.py  mcp_server.py
    providers/                ← codex_app_server delivery adapter
    transports/               ← local, cloudflare, tailscale, cloudflare_tailscale
    hooks/check-comment-bus.sh  hooks/check_comment_bus.py
    web/template.html         ← placeholders; see building-pages.md
    web/shell.html shell.js shell.css adapter.js diagram-plot.js
                              ← reviewer chrome, served fresh per request
skills/claude/annotate/       ← SKILL.md + references/ (this file)
skills/codex/annotate/, plugins/codex/agent-annotate/
                              ← the same skill in Codex wording
```

`projects.toml` is machine-local: `~/.claude/annotate-state/projects.toml`
(`ANNOTATE_CONFIG_DIR`), with the pre-package location
`~/.claude/skills/annotate/projects.toml` still read until it is moved.

### State root

`~/.claude/annotate-state/state` by default (`ANNOTATE_STATE_DIR`):

```
state/
    <project>.json                                   registry of running slugs
    bus-offsets/<session>/<project>/<slug>.offset    `inbox --unread` cursor
    bus-offsets/<project>/<slug>.offset              fallback, session unknown
    hook-offsets/<session>/<project>/<slug>.offset   UserPromptSubmit cursor
    monitor-offsets/<project>/<slug>.offset          monitor delivery cursor
    monitors/<project>/<slug>/owner.json             exclusive monitor lease
    hook-locks/<session>.lock.d                      hook single-flight
    locks/                                           flock files for state + tunnel
    logs/<slug>.log, logs/check-comment-bus.log
```

Four cursors, four owners, no sharing. `ANNOTATE_STATE_DIR` and
`ANNOTATE_BUS_ROOT` relocate all of this for QA; the full list is in
`cli-reference.md` §11.

## 2. On-disk layout — one published slug

```
<slug-dir>/
    current.html          symlink → versions/vN.html
    current.meta.json     {current, history[], owner, content_stamp}
    comments.json         v2 comment store
    versions/v1.html …    frozen snapshots
    content/<vN>.html     optional manual override of content extraction
```

## 3. `current.meta.json`

```json
{
  "current": "v3",
  "history": [
    {"version": "v1", "ts": "2026-06-20T00:00:00Z", "label": "initial"},
    {"version": "v3", "ts": "2026-06-28T00:00:00Z", "label": "post-feedback"}
  ],
  "owner": {"session": "…", "agent": "claude-code",
            "label": "parrotfish · 8f3c", "claimed_at": "2026-09-17T10:00:00Z"}
}
```

`history` is a set keyed on `version`, not a log of calls: re-running
`publish-version` for the same version updates that entry in place. Both the
CLI and the server mutate this file under one shared meta lock — a raw
read-modify-write drops whatever the other cached between read and write.

The desktop shell header renders `owner` as "Owner: <label>" plus "claimed
<relative time>", with the full session id in the tooltip. It is read once, not
polled, and is hidden under the 1160px compact layout.

## 4. `comments.json` (v2 shape)

```json
{
  "schema_version": 2,
  "anchors": {
    "tbl:items:row:42": [
      {
        "id": "abc123", "anchor_id": "tbl:items:row:42",
        "anchor_label": "Acme Corp", "text": "COLI or Schedule A?",
        "author": "user@example.com", "created_at": "2026-06-28T15:00:00Z",
        "version": "v3", "status": "addressed_by_agent",
        "response_text": "verified — UCC filing confirmed COLI",
        "replies": [{"author": "agent:opus-5", "text": "see PR #42", "ts": "…"}],
        "decision_request": {"prompt": "…", "requested_at": "…"},
        "decision": {"verdict": "accept", "text": null, "ts": "…",
                     "by": "user@example.com", "latency_s": 412.0},
        "decision_history": [],
        "flagged_for_session": true, "flagged_at": "…", "flagged_by": "…"
      }
    ]
  },
  "archived": {"tbl:items:row:99": []}
}
```

The top-level key is `anchors`, not `comments`. Archived comments move to
`archived`, keyed by the same anchor id. Legacy shapes — the v1 `{nodeId:
[comment]}` map and the prem-fin list — are coerced to v2 on first write, with
the original backed up next to the file.

## 5. `ANCHOR_REGISTRY`

Injected into `template.html` as a JS object literal:

```js
const ANCHOR_REGISTRY = {
  'tbl:items:row:42':         { name: 'Acme Corp', grp: 'Items · Tier A', parent: 'tbl:items', kind: 'row' },
  'dgm:schema:node:premiums': { name: 'premiums table', grp: 'Schema · Domain X', parent: 'dgm:schema:domain-x', kind: 'node' },
  'kpi:net-equity':           { name: 'Net Equity ≥ $5M', grp: 'KPI Band', kind: 'kpi' },
};
```

`grp` groups and sorts the side panel, `parent` is the Shift+click promotion
target, `kind` is a styling hint. An anchor in `comments.json` that is missing
from the registry surfaces under "Comments without anchor" — feedback never
disappears silently.

## 6. HTTP surface

| Route | Purpose |
|---|---|
| `GET /` (`?v=vN`) | `current.html`, or `versions/vN.html` |
| `GET /current.meta.json`, `GET /comments.json` | raw state |
| `GET /api/capabilities` | `{version, batch, rounds, decision_schema, decision_request_cap}`; 404 on pre-2.19 servers |
| `GET /api/comments?status=&version=` | filtered list |
| `POST /api/comments` | v2 single create (may carry `decision_request`) or the legacy whole-store write |
| `POST /api/comments/batch` | `{items, idempotency}`; ≤200 items, all-or-nothing |
| `PUT /api/comments/<id>` | status, `response_text`, `decision_request` (`null` clears) |
| `POST /api/comments/<id>/reply` \| `/archive` \| `/accept` \| `/restore` | thread and lifecycle |
| `POST /api/comments/<id>/decision` | resolve a card; `{defer_push: true}` holds it in the round |
| `POST /api/comments/<id>/push`, `POST /api/push-session` | single and bulk push |
| `POST /api/rounds/submit` \| `/discard` | close or drop a round |
| `PUT /api/seen` | per-viewer read tracking (`seen_updated`) |
| `*` | static files from `<slug-dir>` |

Authorship reads `Cf-Access-Authenticated-User-Email`, then `?author=`, then
`anonymous`; agents send `agent:<model-id>`. A request from a genuine loopback
peer **with** a loopback `Host` header may assert a local identity, so a
same-host reverse proxy cannot borrow one. `X-Annotate-Session: <id>` is
optional and spreads `session_id` into every event that request emits.

The chrome (`shell.*`, `adapter.js`) is served fresh from the package on
every request and the authored content is recovered from the artifact, so a UI
fix reaches every live page at once. Nothing about review behavior should ever
be baked into a `versions/*.html`.

## 7. Event bus

`<bus root>/<project>/<slug>.ndjson` (default `~/.claude/annotate-bus`), one
JSON object per line,
every line carrying `ts` and `slug`:

```json
{"ts":"2026-06-28T15:00:00Z","event":"comment_created","slug":"schema","comment_id":"abc","anchor_id":"tbl:x:row:1","author":"user@example.com","version":"v3"}
{"ts":"2026-06-28T15:02:00Z","event":"comment_updated","slug":"schema","comment_id":"abc","decision":"accept","latency_s":412.0,"author":"user@example.com"}
{"ts":"2026-06-28T15:04:00Z","event":"round_submitted","slug":"schema","comment_ids":["abc","def"],"verdict_counts":{"accept":2,"reject":0,"changes":0,"comment":0},"undecided_ids":[],"by":"user@example.com"}
```

The bus is append-only and durable. Comments persist to `comments.json`
whether or not anything is listening, so no lease, monitor or notice is ever
load-bearing for not losing feedback. Full event and field list:
`telemetry-and-eval.md`. `annotate prune-bus` archives quiet buses with their
cursors.

## 8. Ownership model

Ownership is keyed on `(project, slug)` and has two independent layers.

**Page ownership** is a registry field plus a `current.meta.json` stamp,
written by `publish` and re-written by `claim`. It decides which session the
UserPromptSubmit hook talks to. It survives restarts and needs no process.

**Monitor ownership** is a live lease at
`state/monitors/<project>/<slug>/owner.json`, created `O_EXCL` by
`annotate monitor` and deleted in its `finally` block. The server counts a
lease as live only when its pid is alive and its `bus_file` matches the bus
that server is writing, and unlinks leases that fail either test. That is what
makes a push report `active_monitor` rather than `queued`.

Rules that hold in both layers:

- one owner per page; one session may own several pages;
- unrelated sessions may own other pages concurrently;
- no owner means a push is queued durably and replays on the next arming;
- `--takeover` is an explicit handoff: it stops the prior monitor process only,
  never the web server, the comments, the bus or the cursors;
- arming without `--takeover` against a live lease fails rather than stealing.

## 9. Provider boundary

```
Browser annotation shell
        |
Persistent local runtime: HTTP + comment store + NDJSON bus
        |
Page owner stamp + exclusive monitor lease + queued-delivery cursor
        |
Provider adapter
        +-- Claude Code: UserPromptSubmit hook (attended), Monitor tool (unattended)
        +-- Codex: app-server thread/turn adapter
        +-- any other: implement claim, deliver, heartbeat-or-lease, release
```

The runtime must not know any provider's session internals. Keep the web
runtime persistent across handoffs and move only the lease. The package is
that distributable: `annotate` is its entry point, the Codex adapter is
`providers/codex_app_server.py` behind `monitor --provider codex-app-server`
(`connect`/`disconnect`/`sessions`/`send`), and every state path is pinned
to the existing `~/.claude/annotate-*` roots rather than silently relocated.
The Codex app-server path delivers a message into a thread; there is no
working push into a Codex *session's* prompt, so a Codex agent reads its
feedback the same way Claude Code does: `annotate inbox <slug> --unread`.

## 10. Interaction contracts that must not regress

- Exactly one tab panel is visible, and every long tab reaches its bottom. The
  iframe viewport owns vertical scrolling; diagram widgets own their own
  horizontal overflow. `adapter.js` neutralizes baked
  `body{height:100vh;overflow:hidden}` app-shell CSS.
- A numbered pin focuses its exact numbered rail card. Aggregate pins may open
  a chooser.
- New comments store a redundant inner target plus click offset, so pins render
  where the click landed. Table-row anchors (any `<tr>`, and any anchor ≤60px
  tall) are centered in their own row band rather than cornered, because a
  corner sits on the boundary and reads as belonging to the row above.
- Hovering a pin outlines its anchor, and hovering an anchor or its body strip
  rings its pins. Both directions, every pin.
- Push reports "Sent" only against a verified live lease, "Queued" otherwise.
- Bulk push sends only feedback with activity newer than its last push.
- Comment state is never silently archived or lost across a version swap.
- Every textarea submits on Ctrl/Cmd+Enter as well as its button.
- Interactive elements keep native behavior; Alt/Option-click comments anyway.
- The mobile breakpoint (`max-width: 768px`, or `max-height: 480px` for a
  landscape phone) swaps the version rail for a `<select>`, the drawer for a
  bottom sheet behind a floating action button, and popovers for sheets, with
  44px tap targets. Desktop above the breakpoint is untouched.
