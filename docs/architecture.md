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
