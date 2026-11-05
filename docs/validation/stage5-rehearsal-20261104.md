# Stage 5 rehearsal: page.db on copies of the M1 pages (2026-11-04)

Stage 5f of `stages-3-5-specs-20261104.md`. Only copies were used: no live page, server or file was changed. The DB is not enabled on any live page.

## How it was run

```sh
scripts/store_rehearsal.py copy /tmp/aa-stage5-rehearsal-m1     # APFS clones; live servers keep running
scripts/store_rehearsal.py run  /tmp/aa-stage5-rehearsal-m1     # ports 18700-18799
```

`run` points every annotate root at the copy, strips page owners from the copied registry and puts a fake `orca` first on `PATH`, so a replayed round cannot reach a live session. For each page it runs `db import` and `db diff`, then starts a sandbox server. On that server it answers an open question (or posts a note) and Sends the round. It then checks the round reached `rounds.ndjson`, the history and `inbox --unread`, and that `db diff` is still 0. Last it stops the server, runs `db off`, and checks the page still serves on JSON.

## Result: 15 of 15 M1 pages pass, run twice

The registry lists 16 pages; `annotate-memory-consolidation` has no directory (`/private/tmp/annotate-memory-consolidation` is gone).

| Page | Import | page.db | Diff | Replay |
|---|---:|---:|---:|---|
| fld-stack-round8 | 1.2 s | 37.7 MB | 0 | answered a question, sent |
| annotate-conformity-20260927 (Agent Annotate) | 0.2 s | 1.5 MB | 0 | answered a question, sent |
| rebex | 0.2 s | 1.5 MB | 0 | answered a question, sent |
| storage | 0.3 s | 0.3 MB | 0 | answered a question, sent |
| 9 more pages | 0.2 s each | 0.1–0.4 MB | 0 | note, sent |
| windmill-agent-guidance-20260925, windmill-build-pilot2-20260925 | 0.2 s | 0.1 MB | 0 | archived: write refused (410, as on JSON), reads served |

Every page's files are exported byte-identical from page.db (FLD 10 of 10 files). Every page ends back on JSON with `db off`.

## Measurements (§5.7)

| Target | Result |
|---|---|
| Lost updates, stress test (4 server threads + 4 CLI processes, 1,000 mixed writes) | page.db 0 lost, db diff 0. Today's JSON files 0 lost: the documented content-stamp race was closed by 8e652ad. The CLI's old unlocked meta write loses 128 under the same load, so the test detects lost updates |
| kill -9 in the middle of publish-shaped transactions | 20 of 20 kills mid-write; all recovered, `integrity_check` ok, db diff 0, no torn JSON |
| Publish commit | one SQLite transaction per page lock; JSON files are written through before the commit (see deviations) |
| Inbox and history query on FLD | unread inbox of 9,399 events 39 ms (bus scan 144 ms); all 224 rounds 8 ms (148 ms); history panel 161 ms (275 ms) |
| Import fidelity, FLD and Agent Annotate | db diff 0; every item, number, version, cursor and delivery kept |
| Goal 1 budgets (L4) | pass; agent-facing output unchanged on page.db (`test_cli_reads` passes with every page forced onto page.db) |
| One comment write on FLD through the server | 84 ms on page.db against 56 ms on JSON (the JSON file is still written, plus changed rows and a sha256 of the 7 MB file) |
| Token saving | none expected, none claimed |

## Deviations from the spec, and why

- **Shared numbers are kept, not refused.** Agent Annotate (7) and rebex (39) reuse an old number for an unrelated question; FLD has none. `numbers` is keyed by (number, anchor) and the import line counts them. Refusing would have kept Agent Annotate off page.db.
- **JSON files are written through before the commit, not after.** About 60 call sites read a record file back inside the same transaction. A crash between file write and commit is taken in by the next transaction (`store_recovered`), so crash consistency equals today's, not better.
- **The bus, cursors and delivery journal stay owned by their files in release N.** page.db copies them (`catch_up_bus`; `db diff` refreshes cursors and the journal), so hooks, monitors and delivery keep working unchanged.
- `content_stamps` stays inside the page row's meta so the meta export stays byte-identical.

## Bugs found by the rehearsal and fixed

- A round whose text holds U+2028 split into two rows (`str.splitlines`); NDJSON is now split at `\n` only.
- `db diff` on a page whose server is running counted bus lines appended after its own catch-up, and the delivery journal; both are now refreshed, not counted.
- A leftover `page.db.writing` marker from a transaction killed before its first write is now cleared by the next transaction.

## Not done here

- M5 copies: waiting for the source path to be confirmed. Nothing is read from or written to the M5 without it.
- Stage 5g (rollout integration, release, any live migration) is out of scope.
