# Architecture

## Runtime boundary

```text
Browser annotation shell
        |
Persistent local HTTP runtime
        +-- versioned HTML and web assets
        +-- comment store
        +-- append-only NDJSON event bus
        +-- exclusive owner lease per project/page
        |
Provider adapter
        +-- attached stdout monitor for Claude Code
        +-- Codex app-server thread/turn delivery
        +-- future adapters implementing the same contract
```

The runtime never restarts during an ordinary agent handoff. A provider adapter
claims a page, receives feedback events, verifies its session is reachable, and
releases the lease. One session may own several pages; each page has at most one
owner.

## Reviewer chrome is served, never baked

The reviewer UI — `shell.html`, `shell.css`, `shell.js`, `adapter.js` — is
loaded from the package on every request and injected into the served
document. Published pages therefore carry content, not chrome, and a UI fix
reaches every page at once with nothing regenerated.

Earlier artifacts were produced by substituting an author's canvas into
`template.html`, which froze a copy of the chrome into each published version.
That copy could never be updated in place, so the two front-ends drifted until
baked pages began suppressing clicks on their own form controls.

`extract.py` closes that gap. `template.html` brackets its canvas with
`<!-- CANVAS CONTENT -->` sentinels, so the server recovers the author's
content from a baked artifact by string slice — no HTML parsing — re-encodes
the anchor registry into the JSON form `adapter.js` reads, and serves the
result through the shell. This happens at request time and writes nothing to
disk, which is what keeps it universal: a page picks up the current chrome on
its next request, with no migration to run and no duplicate to go stale. An
explicit `content/<version>.html` overrides the extraction when a document
needs hand-tuning.

Copying a baked page into `content/` verbatim is not a migration and must not
be done: the artifact's own chrome script has no iframe guard, so it would
keep running beside `adapter.js` — two click handlers, two comment paths — and
the older baked handler would go on swallowing clicks on native controls.

A baked artifact remains a valid standalone document. Opened straight off the
filesystem it still renders its own chrome, which is what offline reviewers
and `Export feedback` recipients get.

## Storage

The alpha package retains the proven v2.11 JSON comment store and NDJSON event
bus. The next storage milestone introduces SQLite for transactional indexes and
leases while retaining NDJSON as the portable audit and replay format.

Runtime state is not stored under `.claude` or `.codex`. Provider installers
contain only the settings necessary to connect their host to the shared core.

## Codex delivery

The Codex adapter uses the locally installed `codex app-server` JSON-RPC
protocol. It lists durable threads, reads the selected thread, steers an active
turn when possible, and otherwise starts a new turn in that thread. Push
delivery is acknowledged only after app-server emits `turn/completed`; the
client connection stays alive for the full turn. Failed or interrupted turns
leave the event unread so the monitor can retry from the append-only stream.

Thread selection is explicit. Directory or title matching can help the user
find a session, but it must never silently choose a recipient.

## Distribution

The Python package is canonical. Agent skills are concise workflow wrappers;
the Codex plugin bundles the Codex skill and MCP registration. Neither wrapper
owns the comment data or browser implementation.
