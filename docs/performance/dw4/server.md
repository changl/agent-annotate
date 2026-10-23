# History revalidates cheaply and feedback writes stay below 100 ms p95

Measured 2026-10-23 on local sandbox copies of the fresh FLD page and its real bus log. Baseline: `61f1b89` (PR #50 merged). This is the server half of `agent-annotate-dw4`; the bead stays open for browser integration and live rollout verification.

History conditional GET falls from **280.98/296.73 ms** to **1.65/1.90 ms** (p50/p95). Comments overlapping history reads fall from **246.89/263.71 ms** to **43.20/49.81 ms**. All 24 write labels meet p95 <100 ms; the slowest final gzip label is **immediate accept: 67.78 ms**.

## What changed

History now retains encoded identity/gzip responses for one disk revision. Its key includes comments, metadata, rounds, current and archived buses, and version/content directory identities, including inode, nanosecond mtime and ctime. Existing strong ETags, private revalidation, auth Vary headers and security headers remain in force. An unchanged conditional request returns an empty 304 without reconstructing or recompressing history.

A cold rebuild takes immutable metadata/store bytes under the existing transaction lock, then parses and reconstructs outside that lock. Publication intervals use a per-source timestamp index instead of rescanning every decision for every version. Appended bus lines reuse parsed round events only after comparing the exact previous byte prefix; truncation/replacement/rewrite resets the reader, partial trailing JSON is retried, and removed archive paths are evicted. The cache retains one prefix per current bus/archive file (about 11.4 MB for this input), rather than unbounded response revisions.

Store writes, fsync/atomic replacement, snapshot immutability, and evidence-byte verification paths are unchanged. No server or metadata validator trusts a process-local invalidation callback from the CLI.

## Before/after routes

30 calls per row; milliseconds **p50 / p95**; `Accept-Encoding: gzip`. Includes HTTP setup and response decoding on loopback. GET rows are ordinary requests; conditional rows send the preceding representation's ETag. History's first request is cold, later changed revisions reuse parsed bus prefixes. Shell/content loads run after the write pass so rendering the actual document cannot replace the synthetic image-card evidence view between accept/select samples. Immutable assets are covered by the browser cache test.

| Route/operation | Before | After | After status |
|---|---:|---:|---|
| comment create | 52.12 / 59.37 | 51.62 / 57.09 | 201 |
| reply | 28.71 / 34.47 | 28.52 / 34.57 | 200 |
| edit | 28.53 / 29.60 | 28.52 / 31.14 | 200 |
| comment batch | 31.50 / 38.95 | 31.72 / 36.40 | 200 |
| decision accept | 54.21 / 63.94 | 54.51 / 63.29 | 200 |
| decision select | 53.97 / 57.09 | 53.97 / 64.44 | 200 |
| decision reject | 28.70 / 34.75 | 28.69 / 33.82 | 200 |
| decision comment | 28.73 / 34.19 | 28.81 / 35.22 | 200 |
| decision changes | 29.17 / 35.98 | 29.04 / 32.25 | 200 |
| verdict notes | 54.05 / 63.10 | 54.20 / 64.76 | 200 |
| rounds/submit | 44.85 / 53.12 | 44.81 / 52.05 | 200 |
| immediate accept | 54.44 / 65.13 | 54.57 / 67.78 | 200 |
| immediate select | 55.03 / 57.92 | 55.07 / 66.44 | 200 |
| immediate reject | 29.05 / 31.35 | 28.91 / 38.50 | 200 |
| immediate comment | 29.00 / 30.17 | 28.91 / 31.47 | 200 |
| immediate changes | 29.02 / 30.36 | 29.22 / 30.22 | 200 |
| push-session | 38.17 / 45.66 | 37.45 / 44.22 | 200 |
| push single | 38.02 / 49.71 | 37.59 / 39.74 | 200 |
| archive | 28.63 / 36.29 | 28.72 / 31.68 | 200 |
| restore | 28.45 / 30.80 | 28.20 / 29.35 | 200 |
| accept comment | 28.75 / 30.36 | 28.59 / 31.33 | 200 |
| rounds/discard | 5.06 / 5.91 | 5.12 / 9.68 | 200 |
| read-state write | 4.98 / 5.66 | 5.03 / 5.43 | 200 |
| seen write | 29.78 / 32.39 | 29.97 / 32.91 | 200 |
| GET /comments.json | 125.98 / 131.37 | 124.84 / 134.55 | 200 |
| conditional /comments.json | 1.98 / 2.23 | 1.98 / 2.45 | 304 |
| GET /comments.json?view=poll | 66.42 / 73.66 | 65.41 / 74.88 | 200 |
| conditional /comments.json?view=poll | 1.95 / 2.28 | 1.87 / 2.22 | 304 |
| GET /current.meta.json | 9.86 / 18.71 | 9.49 / 18.47 | 200 |
| conditional /current.meta.json | 6.70 / 8.29 | 6.68 / 10.31 | 304 |
| GET /api/read-state | 2.08 / 5.08 | 2.02 / 4.08 | 200 |
| conditional /api/read-state | 1.89 / 7.91 | 1.87 / 3.21 | 304 |
| GET /api/seen | 6.41 / 10.30 | 6.39 / 7.13 | 200 |
| conditional /api/seen | 6.28 / 7.20 | 6.25 / 7.36 | 304 |
| GET /api/categories | 28.85 / 37.65 | 28.64 / 35.73 | 200 |
| conditional /api/categories | 28.44 / 31.49 | 28.24 / 34.17 | 304 |
| GET /api/session-monitor | 1.39 / 4.42 | 1.43 / 1.87 | 200 |
| conditional /api/session-monitor | 1.18 / 1.68 | 1.23 / 1.54 | 304 |
| GET /api/board | 1.81 / 3.11 | 1.91 / 2.47 | 200 |
| conditional /api/board | 1.80 / 2.95 | 1.80 / 2.24 | 304 |
| GET /api/plans/benchmark | 1.39 / 1.82 | 1.42 / 1.67 | 200 |
| conditional /api/plans/benchmark | 1.33 / 1.69 | 1.32 / 1.67 | 304 |
| GET /api/history | 285.92 / 308.22 | 89.95 / 96.83 | 200 |
| conditional /api/history | 280.98 / 296.73 | 1.65 / 1.90 | 304 |
| GET /api/project | 6.74 / 11.29 | 6.37 / 7.14 | 200 |
| conditional /api/project | 6.19 / 12.85 | 6.10 / 6.66 | 304 |
| GET /api/copy | 1.32 / 1.57 | 1.32 / 1.67 | 200 |
| conditional /api/copy | 1.22 / 1.56 | 1.18 / 1.56 | 200 |
| GET /api/delivery | 1.65 / 2.00 | 1.64 / 2.00 | 200 |
| conditional /api/delivery | 1.61 / 2.09 | 1.64 / 1.96 | 304 |
| GET /api/identity | 1.52 / 1.92 | 1.47 / 1.75 | 200 |
| conditional /api/identity | 1.41 / 1.76 | 1.41 / 1.79 | 304 |
| GET /api/capabilities | 1.34 / 1.70 | 1.36 / 1.75 | 200 |
| conditional /api/capabilities | 1.32 / 1.67 | 1.34 / 1.63 | 304 |
| GET / | 15.24 / 17.87 | 15.43 / 16.80 | 200 |
| GET /content | 84.31 / 97.98 | 83.09 / 98.15 | 200 |

`comment create` = POST `/api/comments`; `comment batch` = POST `/api/comments/batch`; reply/edit/decisions/archive/restore/accept/push use `/api/comments/<id>` and their named suffixes (edit uses PUT). Decision rows defer delivery; immediate rows use the existing immediate path. Sidecar writes use POST `/api/read-state` and `/api/seen`.

## Write overlap and initial-load limits

The overlap test starts the actual history route, waits 50 ms, then posts a comment, 30 times while the store/bus grow. Identity encoding is intentional here to isolate history reconstruction from compression. Before: 246.89/263.71 ms (max 265.53); after: 43.20/49.81 ms (max 139.35). The first completely cold bus parse can still overlap a write above 100 ms; the target and reported acceptance are p95, not a maximum or a real-time guarantee.

The earlier identity route pass also had all 24 write p95 values below 100 ms; it is retained in `server.json`, along with all profiles, wire byte counts, CPU medians, status codes and maximums. The measurements are local copied-data results, not M5/Funnel end-to-end timings. Browser rendering and active/draft poll behavior belong to the browser half.

## Why history was slow

The baseline profile reparsed roughly 39,000 bus records and called the timestamp parser roughly 239,000 times, while holding the store lock. The indexed implementation reduces timestamp parsing to roughly 11,000 calls; after the first bus scan, a changed-store rebuild parses only newly appended bus lines. Warm response hits avoid both. The remaining cold reconstruction cost includes store JSON decoding and checking saved-version availability, performed outside the write transaction.

## Verification

- Full non-browser suite: **1,652 passed, 2 skipped** (224.00 s).
- Affected browser suite: **20 passed** (99.40 s): HTTP cache, decision verdicts, and rounds/history/links.
- Focused existing cache/write/history suite: **78 passed**; new history-cache plus history suite: **20 passed**.
- Ruff and `git diff --check`: pass.
- Exact history output equality against the baseline on this untouched source: **214 versions, 120 rounds**.
- Real CLI `ask`, `resolve`, `withdraw`, `new --publish`, and `publish-version` calls on a sandbox page are followed by conditional GETs returning **200 with changed ETags and new data**, without restarting the server. `new` uses the real generator and publish-version write; its transport registration call is inert in the test.
- Cache tests cover ordinary/gzip 304 reuse without rebuilding, comment/meta/round/bus/archive/version-availability changes and deletions, a blocked cold history builder concurrent with a successful durable comment, exact-prefix rewrite detection, partial append retries, and unchanged immutable review snapshots.

All pytest runs load `tests/conftest.py`; state, registry, routes, bus, credentials and fake delivery stay in its sandbox. Input was copied and owner state removed before serving. No live page, M5, installed runtime, or checkout at `/Users/changlee/projects/agent-annotate/codex` was modified.

## Inputs and reproduction

Source contains 958 active and 71 archived comments (1,029 total); original compact comments are 4,369,049 bytes, metadata 1,059,843 bytes, rounds 473,442 bytes, and bus 11,384,672 bytes. Each benchmark adds one isolated evidence card and 40 cited 512 KiB images in its private copy, to exercise exact-byte evidence cost; the initial JSON serialization is 4,633,812 bytes and server saves remain compact. Source SHA-256 values are in `server.json`.

Run each command separately. The benchmark itself loads conftest, copies the input, installs a fake one-second Orca only inside the sandbox, and never routes or serves the source directory. For the baseline, use the same script with `PYTHONPATH=/tmp/dw4-baseline/src`, where src is the baseline tree at `61f1b89`.

```sh
env PYTHONPATH=/Users/changlee/orca/workspaces/codex/dw4-server/src /Users/changlee/projects/agent-annotate/codex/.venv/bin/python scripts/bench_writes.py --source /tmp/fld-live-20261023 --bus-source /tmp/fld-live-20261023-bus.ndjson --no-synthetic --samples 30 --accept-encoding gzip --output /tmp/dw4-after-gzip-final.json
env PYTHONPATH=/Users/changlee/orca/workspaces/codex/dw4-server/src /Users/changlee/projects/agent-annotate/codex/.venv/bin/python scripts/bench_writes.py --source /tmp/fld-live-20261023 --bus-source /tmp/fld-live-20261023-bus.ndjson --no-synthetic --samples 30 --contention-only --contention-path /api/history --output /tmp/dw4-contention-after-final.json
env PYTHONPATH=/Users/changlee/orca/workspaces/codex/dw4-server/src /Users/changlee/projects/agent-annotate/codex/.venv/bin/python -m pytest --ignore=tests/browser -q
env PYTHONPATH=/Users/changlee/orca/workspaces/codex/dw4-server/src /Users/changlee/projects/agent-annotate/codex/.venv/bin/python -m pytest tests/browser/test_http_cache_browser.py tests/browser/test_decision_verdicts.py tests/browser/test_rounds_links_contrast.py -q
```

Complete raw measurements and profiles: [server.json](server.json).
