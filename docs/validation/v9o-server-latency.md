# v9o server latency

Measured on Apple M1 Max, 2026-10-22. Baseline: origin/main c6c59c7 (2.27.1). After: changl/fast-writes.

Every measured write is below 150 ms p95: the maximum after is **17.04 ms**, versus **35.50 ms** before. Image-heavy deferred accept p50 falls from **18.02–20.23 ms to 5.85–8.27 ms**. All six unchanged polls return **304 with zero response body** after the change.

The reported 1–2 second delay was **not reproduced on M1 loopback**, even before the patch. These results prove local server budgets and a smaller image-vote cost; they do not establish M5 or Funnel round-trip latency. Live pages, installed tooling, live routes, the M5 and the coordinator checkout were not modified.

## Method

`scripts/bench_writes.py` imports `tests/conftest.py` before package imports, so every ANNOTATE state/config/bus path is sandboxed. The source trees are copied with symlinks dereferenced; only copies are served on ephemeral loopback ports. The two largest comments stores under the M1 reviews directory were conformity (143,393 source bytes) and assessment (45,877 source bytes). Their complete comment data and Plans are retained; each copy gets one extra stress card citing 40 distinct 512 KiB image assets. The synthetic page has 60 cards citing those same 40 assets (20 MiB). Image decoding is outside this server-only measurement.

Each label below has 30 real HTTP calls, timed through full response-body read using fresh connections. Comment data is restored before each iteration to hold input size stable; the routes perform their normal JSON rewrites, bus appends, fsyncs and round/catalog work. Deferred and immediate accept/select both run; verdict notes are an accept with a note. First-vote asset freezing is included (cold maxima remain under 54 ms). A separate cProfile pass exercises the same decision endpoint without adding profiler overhead to route timings.

`ORCA_CLI_COMMAND` points at an executable sandbox fake that logs invocation and sleeps **1 second on every call**. Real delivery uses sandbox owner bindings and its normal durable records; no real Orca call or terminal send is possible. The fake starts during every fixture, so the fast HTTP numbers are not merely a no-owner/no-op case. Pending background delivery threads are daemon workers and the sandbox outbox remains their source of truth.

| Fixture | Input comments bytes (compact JSON) | Fake calls started before / after |
|---|---:|---:|
| Conformity copy | 106,735 | 8 / 6 |
| Assessment copy | 36,280 | 12 / 8 |
| Synthetic | 16,680 | 18 / 14 |

## Route timings

All values are milliseconds; cells are **p50 / p95**. `decision ...` uses defer_push; `immediate ...` uses the identical endpoint without deferral. Conditional GET rows send the ETag from the preceding GET.

### Conformity copy

| Route | Before p50 / p95 | After p50 / p95 | After status |
|---|---:|---:|---|
| comment create | 5.69 / 9.59 | 5.72 / 10.12 | 201 |
| reply | 5.58 / 6.30 | 5.62 / 6.47 | 200 |
| edit | 5.54 / 6.64 | 5.59 / 6.17 | 200 |
| comment batch | 5.84 / 7.71 | 5.94 / 7.32 | 200 |
| decision accept | 20.23 / 24.92 | 8.27 / 9.53 | 200 |
| decision select | 20.30 / 24.62 | 8.37 / 9.94 | 200 |
| decision reject | 6.18 / 8.91 | 5.97 / 7.41 | 200 |
| decision comment | 5.97 / 7.04 | 6.05 / 10.30 | 200 |
| decision changes | 5.96 / 9.17 | 6.10 / 8.47 | 200 |
| verdict notes | 20.41 / 24.49 | 8.58 / 9.45 | 200 |
| rounds/submit | 8.36 / 10.04 | 8.21 / 10.12 | 200 |
| immediate accept | 20.72 / 35.50 | 8.89 / 14.98 | 200 |
| immediate select | 20.82 / 23.11 | 9.11 / 10.26 | 200 |
| immediate reject | 6.56 / 10.55 | 6.35 / 8.89 | 200 |
| immediate comment | 6.39 / 17.68 | 6.35 / 10.55 | 200 |
| immediate changes | 6.46 / 7.80 | 6.47 / 8.64 | 200 |
| push-session | 7.47 / 8.26 | 7.35 / 9.44 | 200 |
| push single | 7.37 / 8.75 | 7.30 / 9.32 | 200 |
| archive | 5.99 / 6.93 | 6.20 / 6.92 | 200 |
| restore | 5.97 / 6.78 | 6.03 / 7.24 | 200 |
| accept comment | 6.08 / 7.16 | 6.01 / 6.64 | 200 |
| rounds/discard | 2.70 / 4.61 | 2.81 / 3.46 | 200 |
| read-state write | 2.23 / 2.77 | 2.16 / 2.76 | 200 |
| seen write | 2.70 / 3.22 | 2.53 / 3.55 | 200 |
| GET /comments.json | 3.57 / 3.88 | 3.46 / 3.95 | 200 |
| conditional /comments.json | 2.93 / 3.23 | 2.87 / 3.26 | 304 |
| GET /api/read-state | 1.64 / 1.96 | 1.57 / 2.03 | 200 |
| conditional /api/read-state | 1.50 / 1.94 | 1.50 / 1.88 | 304 |
| GET /api/categories | 10.48 / 11.62 | 10.42 / 11.87 | 200 |
| conditional /api/categories | 10.71 / 11.68 | 10.61 / 12.29 | 304 |
| GET /api/session-monitor | 1.41 / 1.68 | 1.40 / 1.74 | 200 |
| conditional /api/session-monitor | 1.28 / 1.67 | 1.21 / 1.58 | 304 |
| GET /api/board | 1.43 / 1.97 | 1.42 / 1.82 | 200 |
| conditional /api/board | 1.41 / 1.92 | 1.34 / 1.79 | 304 |
| GET /api/plans/benchmark | 2.27 / 2.69 | 2.19 / 2.57 | 200 |
| conditional /api/plans/benchmark | 2.19 / 2.76 | 2.24 / 2.63 | 304 |

### Assessment copy

| Route | Before p50 / p95 | After p50 / p95 | After status |
|---|---:|---:|---|
| comment create | 3.45 / 4.14 | 3.44 / 10.05 | 201 |
| reply | 3.40 / 3.89 | 3.41 / 12.20 | 200 |
| edit | 3.45 / 3.80 | 3.31 / 6.90 | 200 |
| comment batch | 3.74 / 5.18 | 3.65 / 5.28 | 200 |
| decision accept | 18.02 / 31.60 | 5.85 / 8.58 | 200 |
| decision select | 18.15 / 23.02 | 6.06 / 9.76 | 200 |
| decision reject | 3.94 / 8.50 | 3.83 / 4.40 | 200 |
| decision comment | 3.84 / 4.83 | 3.71 / 5.12 | 200 |
| decision changes | 3.94 / 8.74 | 3.81 / 5.47 | 200 |
| verdict notes | 18.22 / 25.46 | 6.31 / 7.61 | 200 |
| rounds/submit | 5.86 / 6.93 | 5.69 / 11.44 | 200 |
| immediate accept | 18.61 / 25.90 | 6.87 / 13.44 | 200 |
| immediate select | 19.33 / 21.13 | 6.95 / 7.72 | 200 |
| immediate reject | 4.36 / 5.22 | 4.33 / 5.93 | 200 |
| immediate comment | 4.28 / 7.13 | 4.13 / 6.65 | 200 |
| immediate changes | 4.40 / 6.52 | 4.14 / 5.04 | 200 |
| push-session | 5.06 / 6.32 | 4.61 / 5.90 | 200 |
| push single | 5.02 / 6.38 | 4.77 / 5.68 | 200 |
| archive | 3.86 / 4.34 | 3.71 / 4.59 | 200 |
| restore | 3.95 / 4.45 | 3.78 / 4.37 | 200 |
| accept comment | 3.94 / 4.68 | 3.89 / 4.58 | 200 |
| rounds/discard | 2.37 / 2.66 | 2.18 / 2.69 | 200 |
| read-state write | 2.20 / 2.74 | 2.14 / 2.95 | 200 |
| seen write | 2.46 / 2.82 | 2.35 / 3.18 | 200 |
| GET /comments.json | 2.40 / 2.66 | 2.25 / 2.57 | 200 |
| conditional /comments.json | 2.04 / 2.64 | 1.97 / 2.62 | 304 |
| GET /api/read-state | 1.68 / 2.06 | 1.55 / 1.95 | 200 |
| conditional /api/read-state | 1.67 / 1.99 | 1.52 / 1.99 | 304 |
| GET /api/categories | 5.10 / 6.11 | 4.97 / 5.56 | 200 |
| conditional /api/categories | 5.10 / 5.92 | 5.00 / 5.94 | 304 |
| GET /api/session-monitor | 1.36 / 1.68 | 1.32 / 1.62 | 200 |
| conditional /api/session-monitor | 1.32 / 1.66 | 1.21 / 1.75 | 304 |
| GET /api/board | 1.26 / 1.59 | 1.22 / 1.51 | 200 |
| conditional /api/board | 1.26 / 1.68 | 1.21 / 1.52 | 304 |
| GET /api/plans/benchmark | 1.74 / 2.14 | 1.74 / 2.12 | 200 |
| conditional /api/plans/benchmark | 1.76 / 2.14 | 1.75 / 2.12 | 304 |

### Synthetic

| Route | Before p50 / p95 | After p50 / p95 | After status |
|---|---:|---:|---|
| comment create | 3.63 / 7.38 | 3.54 / 6.99 | 201 |
| reply | 3.54 / 4.63 | 3.35 / 3.80 | 200 |
| edit | 3.52 / 7.31 | 3.42 / 4.53 | 200 |
| comment batch | 3.70 / 7.76 | 3.57 / 5.48 | 200 |
| decision accept | 18.47 / 33.21 | 6.02 / 7.37 | 200 |
| decision select | 18.52 / 22.83 | 6.35 / 11.89 | 200 |
| decision reject | 4.16 / 4.64 | 3.92 / 5.48 | 200 |
| decision comment | 4.00 / 4.61 | 3.93 / 7.25 | 200 |
| decision changes | 3.96 / 4.29 | 3.99 / 4.86 | 200 |
| verdict notes | 18.48 / 22.99 | 6.50 / 7.59 | 200 |
| rounds/submit | 6.25 / 10.56 | 5.81 / 7.25 | 200 |
| immediate accept | 18.94 / 23.24 | 6.93 / 17.04 | 200 |
| immediate select | 18.97 / 20.27 | 6.94 / 9.24 | 200 |
| immediate reject | 4.50 / 5.04 | 4.36 / 5.32 | 200 |
| immediate comment | 4.48 / 5.16 | 4.24 / 6.31 | 200 |
| immediate changes | 4.50 / 5.15 | 4.32 / 5.79 | 200 |
| push-session | 5.38 / 7.90 | 5.04 / 9.71 | 200 |
| push single | 5.25 / 9.18 | 4.96 / 8.42 | 200 |
| archive | 4.05 / 4.64 | 3.94 / 5.97 | 200 |
| restore | 4.10 / 4.85 | 3.91 / 4.29 | 200 |
| accept comment | 4.11 / 4.60 | 3.93 / 4.78 | 200 |
| rounds/discard | 2.33 / 3.12 | 2.15 / 2.79 | 200 |
| read-state write | 2.21 / 2.72 | 2.02 / 2.53 | 200 |
| seen write | 2.31 / 3.16 | 2.12 / 3.02 | 200 |
| GET /comments.json | 2.18 / 2.92 | 2.05 / 2.51 | 200 |
| conditional /comments.json | 1.97 / 2.73 | 1.80 / 2.43 | 304 |
| GET /api/read-state | 1.73 / 2.40 | 1.55 / 2.50 | 200 |
| conditional /api/read-state | 1.63 / 2.07 | 1.52 / 3.94 | 304 |
| GET /api/categories | 5.07 / 5.99 | 4.84 / 6.40 | 200 |
| conditional /api/categories | 5.14 / 6.26 | 4.85 / 5.42 | 304 |
| GET /api/session-monitor | 1.42 / 3.81 | 1.41 / 1.77 | 200 |
| conditional /api/session-monitor | 1.33 / 1.68 | 1.31 / 1.75 | 304 |
| GET /api/board | 1.37 / 1.66 | 1.25 / 1.58 | 200 |
| conditional /api/board | 1.32 / 2.07 | 1.21 / 1.47 | 304 |
| GET /api/plans/benchmark | 1.80 / 2.33 | 1.73 / 2.02 | 200 |
| conditional /api/plans/benchmark | 1.85 / 2.68 | 1.77 / 2.58 | 304 |

## What changed and what remains durable

- Evidence remains frozen **at accept/select time**, including deferred votes; Send never depends on the process-local view cache. A bounded 512-entry LRU stores image digests, not image bytes. Keys include path, device, inode, size, mtime_ns and ctime_ns, so same-size edits with restored mtime and atomic replacements invalidate. Original sources are still checked at the vote; missing or changed sources produce incomplete evidence as before. Existing content-hash copies are verified and reused; tampered copies are repaired from a verified source. First writes retain file and directory fsync.
- Push, per-card push and Send write their existing durable bus/round/comment records before replying. Owner lookup and delivery now share one background wake path started after the HTTP response; the existing durable outbox/watchdog remains responsible for recovery. This removes no delivery journals or uncertain-send suppression. No comments/rounds fsync was removed: the profile did not justify weakening it.
- Registry scans and page-name resolution are shared within one HTTP request using a ContextVar, discarded even on failure, and rebuilt on the next request (including a keep-alive request). CLI calls outside that scope retain fresh reads; owner delivery retains its existing lock/revalidation behavior.
- Remaining delivery `ps`, board, workspace-git and server version-check subprocesses use `cwd=Path.home()`; the primary Orca subprocess already did on main.
- Categories, board and Plans metadata now use the existing conditional-response machinery. The other three poll endpoints already supported it. Representation generation remains fresh; unchanged requests avoid transferring full bodies without a cross-request payload cache that could hide new votes or ownership.

## ETag contract

All six endpoints return a strong quoted SHA-256 of the **actual response representation**. The client stores the ETag and sends it unchanged as `If-None-Match`; a match returns 304 with an empty body and the same ETag/security/cache headers. A changed representation returns 200 and a new ETag. Gzip and identity have distinct ETags and `Vary: Accept-Encoding`. Auth and review-key checks run before validators; the existing no-store policy on categories/board/plans is preserved, so the browser uses explicit in-memory validators. A 304 must reuse the client's previous parsed data, without calling response.json() or applying a data update. This contract was sent to the keep-drafts worker through its Dispatch mailbox.

## Profile

The slowest family before is POST `/api/comments/<id>/decision` (accept/select). On the synthetic fixture, the final isolated deferred-accept profile falls from 32 ms to 19 ms overall (29 ms to 16 ms inside the route); `persist_evidence` falls from 18 ms to 6 ms and 40 image reads disappear once hashes and frozen assets are warm. JSON serialization and safe-path validation remain the largest costs after that reduction. Complete profiles from the final expanded run, p50/p95/max and HTTP statuses are in `v9o-server-latency.json`.

## Validation

- Full non-browser suite: **1,617 passed, 2 skipped** (208.27 s).
- Affected browser suite (approval catalog, decision verdicts, rounds/links/contrast, runtime HTTP, HTTP cache): **24 passed** (109.59 s).
- Additional focused cache-scope and blocked-delivery checks: **4 passed**; final tampered-image/same-mtime edit check: **1 passed**.
- Ruff for all changed Python files and `git diff --check`: passed.

The blocked-delivery regression leaves fake Orca waiting on an event while comment/reply/edit/decision/read-state/seen/Send/push writes must finish under a generous 500 ms and have real persisted receipts. Poll tests cover identity/gzip, strong ETags, empty 304s, security/cache headers and invalidation after comment/read/plan changes. Existing auth, immutable-evidence, Plans filing, uncertain delivery and browser suites remain green. Synthetic timings do not bound arbitrary future assets, remote storage or client/network delays.

## Reproduce

Run each command separately, using the repository's test interpreter; never point the server at a live page.

```sh
env PYTHONPATH=/tmp/v9o-baseline/src /Users/changlee/projects/agent-annotate/codex/.venv/bin/python scripts/bench_writes.py --output /tmp/v9o-before-all.json --samples 30
env PYTHONPATH=/Users/changlee/orca/workspaces/codex/fast-writes/src /Users/changlee/projects/agent-annotate/codex/.venv/bin/python scripts/bench_writes.py --output /tmp/v9o-after-all.json --samples 30
env PYTHONPATH=/Users/changlee/orca/workspaces/codex/fast-writes/src /Users/changlee/projects/agent-annotate/codex/.venv/bin/python -m pytest tests --ignore=tests/browser -q
env PYTHONPATH=/Users/changlee/orca/workspaces/codex/fast-writes/src /Users/changlee/projects/agent-annotate/codex/.venv/bin/python -m pytest tests/browser/test_approval_catalog_browser.py tests/browser/test_decision_verdicts.py tests/browser/test_rounds_links_contrast.py tests/browser/test_runtime_http.py tests/browser/test_http_cache_browser.py -q
```

The baseline directory is a `git archive` extraction of c6c59c7, and the same current harness is used against both source trees. `--source` may be repeated for other read-only page copies; `--orca-delay 0` is available for a zero-delay control. No release, install, merge, restart or live publish was performed.
