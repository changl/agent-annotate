# v9o server latency and FLD resource use

Apple M1 Max, 2026-10-22. Baseline c6c59c7 (2.27.1); after changl/fast-writes. All tests serve private copies. No live page, M5 service, installed runtime or transport was modified.

**The real FLD copy reproduces the reported pause.** Its categories GET repeatedly decodes the 6.46 MB comment store for 15 manual Plans while holding the shared write lock. A comment posted during that poll takes **1,294.15 ms p50 / 1,346.21 ms p95** before and **31.71 / 40.79 ms** after. Categories itself falls from **1,264.77 / 1,344.84 ms** to **28.48 / 37.26 ms**.

All 24 write labels meet p95 <150 ms on all four fixtures. FLD's largest isolated write p95 falls from **194.74 to 83.48 ms**; reply server CPU p50 falls from **134.23 to 27.83 ms**. The fake Orca sleeps one second per actual call and does not delay replies. All six unchanged polls return 304 with an empty body.

The baseline resource run reaches **1,551.59 MiB RSS** at simulated minute 1 and is stopped by the 1,500 MiB guard. The complete after workload peaks at **453.36 MiB**, then settles to **234.58 MiB** during a real polling minute that uses **0.29 CPU seconds**. The workload simulates 30 minutes of use at accelerated pace; it is not 30 elapsed minutes or an 11-hour soak.

## Method

Both scripts import tests/conftest.py before annotate, isolating every ANNOTATE state/config/bus path. Source trees are read-only inputs, copied with symlinks dereferenced, then served on ephemeral loopback ports. The same current harness drives an archived c6c59c7 baseline and this checkout.

Conformity and assessment are the two largest comments files under M1 reviews (143,393 and 45,877 source bytes). Each copy retains its complete data and Plans, plus one stress card citing 40 distinct 512 KiB image assets. Synthetic has 60 such cards. The FLD primary input is /tmp/fld-stack-round8-copy: 6,457,554 comment bytes, 940 active plus 71 archived comments, 265 version files, and 863,530,042 bytes across 2,778 files. FLD write timings also add one stress card; resource runs use the unaugmented real copy. Image decoding is outside this server-only test. The source comments file remains exactly 6,457,554 bytes after testing.

Each route has 30 real HTTP calls timed through response-body read on fresh connections. The comment input is restored each iteration to hold size stable; normal JSON rewrites, fsync, bus and round/catalog work run. Cold freezing is included in maxima. Server CPU uses time.thread_time around the actual handler, excluding client parsing and subprocess CPU. Separate cProfile passes do not affect timings.

The contention test starts a real categories GET, waits 50 ms, then posts a comment, over 30 trials. No server sleep is injected. ORCA_CLI_COMMAND points at a sandbox executable that logs calls and sleeps one second; route fixtures bind only a fake owner. Resource fixtures have no delivery pending and issue no live Orca/board calls. All private input bodies and review keys are omitted from reports.

| Fixture | Compact benchmark input bytes | Fake calls started before / after |
|---|---:|---:|
| Conformity copy | 106,735 | 8 / 4 |
| Assessment copy | 36,280 | 12 / 7 |
| Synthetic 60-card / 40-image page | 16,680 | 18 / 12 |
| FLD copy (primary) | 4,543,423 | 166 / 28 |

## Route timings

Milliseconds, **p50 / p95**. Decision defers delivery; immediate does not. This table uses full comments.json. The opt-in smaller poll payload is measured below.

### Conformity copy

| Route | Before p50 / p95 | After p50 / p95 | After status |
|---|---:|---:|---|
| comment create | 5.69 / 9.59 | 4.18 / 4.71 | 201 |
| reply | 5.58 / 6.30 | 3.20 / 3.86 | 200 |
| edit | 5.54 / 6.64 | 3.09 / 3.76 | 200 |
| comment batch | 5.84 / 7.71 | 3.50 / 5.05 | 200 |
| decision accept | 20.23 / 24.92 | 5.96 / 8.40 | 200 |
| decision select | 20.30 / 24.62 | 6.03 / 7.82 | 200 |
| decision reject | 6.18 / 8.91 | 3.45 / 4.42 | 200 |
| decision comment | 5.97 / 7.04 | 3.38 / 4.16 | 200 |
| decision changes | 5.96 / 9.17 | 3.49 / 4.12 | 200 |
| verdict notes | 20.41 / 24.49 | 6.07 / 7.47 | 200 |
| rounds/submit | 8.36 / 10.04 | 5.62 / 8.31 | 200 |
| immediate accept | 20.72 / 35.50 | 6.63 / 12.60 | 200 |
| immediate select | 20.82 / 23.11 | 6.31 / 7.46 | 200 |
| immediate reject | 6.56 / 10.55 | 3.78 / 4.74 | 200 |
| immediate comment | 6.39 / 17.68 | 3.73 / 4.25 | 200 |
| immediate changes | 6.46 / 7.80 | 3.72 / 4.98 | 200 |
| push-session | 7.47 / 8.26 | 4.55 / 7.94 | 200 |
| push single | 7.37 / 8.75 | 4.52 / 9.19 | 200 |
| archive | 5.99 / 6.93 | 3.40 / 4.15 | 200 |
| restore | 5.97 / 6.78 | 3.38 / 4.10 | 200 |
| accept comment | 6.08 / 7.16 | 3.27 / 4.60 | 200 |
| rounds/discard | 2.70 / 4.61 | 2.01 / 3.29 | 200 |
| read-state write | 2.23 / 2.77 | 2.27 / 3.19 | 200 |
| seen write | 2.70 / 3.22 | 2.83 / 3.65 | 200 |
| GET /comments.json | 3.57 / 3.88 | 3.60 / 4.57 | 200 |
| conditional /comments.json | 2.93 / 3.23 | 1.50 / 2.41 | 304 |
| GET /api/read-state | 1.64 / 1.96 | 1.74 / 2.34 | 200 |
| conditional /api/read-state | 1.50 / 1.94 | 1.62 / 2.33 | 304 |
| GET /api/categories | 10.48 / 11.62 | 4.00 / 4.84 | 200 |
| conditional /api/categories | 10.71 / 11.68 | 3.99 / 7.02 | 304 |
| GET /api/session-monitor | 1.41 / 1.68 | 1.44 / 2.85 | 200 |
| conditional /api/session-monitor | 1.28 / 1.67 | 1.31 / 1.80 | 304 |
| GET /api/board | 1.43 / 1.97 | 1.65 / 2.11 | 200 |
| conditional /api/board | 1.41 / 1.92 | 1.61 / 2.14 | 304 |
| GET /api/plans/benchmark | 2.27 / 2.69 | 1.61 / 2.14 | 200 |
| conditional /api/plans/benchmark | 2.19 / 2.76 | 1.58 / 2.02 | 304 |

### Assessment copy

| Route | Before p50 / p95 | After p50 / p95 | After status |
|---|---:|---:|---|
| comment create | 3.45 / 4.14 | 3.39 / 4.37 | 201 |
| reply | 3.40 / 3.89 | 2.79 / 4.24 | 200 |
| edit | 3.45 / 3.80 | 2.80 / 8.32 | 200 |
| comment batch | 3.74 / 5.18 | 3.03 / 7.22 | 200 |
| decision accept | 18.02 / 31.60 | 5.33 / 10.86 | 200 |
| decision select | 18.15 / 23.02 | 5.47 / 12.04 | 200 |
| decision reject | 3.94 / 8.50 | 3.11 / 4.45 | 200 |
| decision comment | 3.84 / 4.83 | 3.13 / 4.78 | 200 |
| decision changes | 3.94 / 8.74 | 2.99 / 5.21 | 200 |
| verdict notes | 18.22 / 25.46 | 5.65 / 16.82 | 200 |
| rounds/submit | 5.86 / 6.93 | 4.82 / 22.38 | 200 |
| immediate accept | 18.61 / 25.90 | 6.12 / 16.44 | 200 |
| immediate select | 19.33 / 21.13 | 5.92 / 16.37 | 200 |
| immediate reject | 4.36 / 5.22 | 3.33 / 6.47 | 200 |
| immediate comment | 4.28 / 7.13 | 3.35 / 10.52 | 200 |
| immediate changes | 4.40 / 6.52 | 3.15 / 8.62 | 200 |
| push-session | 5.06 / 6.32 | 3.91 / 7.32 | 200 |
| push single | 5.02 / 6.38 | 4.00 / 5.83 | 200 |
| archive | 3.86 / 4.34 | 2.99 / 5.43 | 200 |
| restore | 3.95 / 4.45 | 2.80 / 5.92 | 200 |
| accept comment | 3.94 / 4.68 | 2.91 / 4.72 | 200 |
| rounds/discard | 2.37 / 2.66 | 1.96 / 2.63 | 200 |
| read-state write | 2.20 / 2.74 | 2.21 / 4.28 | 200 |
| seen write | 2.46 / 2.82 | 2.40 / 3.30 | 200 |
| GET /comments.json | 2.40 / 2.66 | 2.35 / 2.84 | 200 |
| conditional /comments.json | 2.04 / 2.64 | 1.41 / 1.85 | 304 |
| GET /api/read-state | 1.68 / 2.06 | 1.68 / 3.16 | 200 |
| conditional /api/read-state | 1.67 / 1.99 | 1.62 / 2.29 | 304 |
| GET /api/categories | 5.10 / 6.11 | 3.02 / 6.39 | 200 |
| conditional /api/categories | 5.10 / 5.92 | 2.89 / 4.12 | 304 |
| GET /api/session-monitor | 1.36 / 1.68 | 1.38 / 2.23 | 200 |
| conditional /api/session-monitor | 1.32 / 1.66 | 1.29 / 1.88 | 304 |
| GET /api/board | 1.26 / 1.59 | 1.31 / 1.80 | 200 |
| conditional /api/board | 1.26 / 1.68 | 1.28 / 1.72 | 304 |
| GET /api/plans/benchmark | 1.74 / 2.14 | 1.47 / 2.10 | 200 |
| conditional /api/plans/benchmark | 1.76 / 2.14 | 1.46 / 2.11 | 304 |

### Synthetic 60-card / 40-image page

| Route | Before p50 / p95 | After p50 / p95 | After status |
|---|---:|---:|---|
| comment create | 3.63 / 7.38 | 3.43 / 5.57 | 201 |
| reply | 3.54 / 4.63 | 2.91 / 4.34 | 200 |
| edit | 3.52 / 7.31 | 3.02 / 5.42 | 200 |
| comment batch | 3.70 / 7.76 | 3.28 / 4.05 | 200 |
| decision accept | 18.47 / 33.21 | 5.76 / 24.83 | 200 |
| decision select | 18.52 / 22.83 | 5.73 / 14.23 | 200 |
| decision reject | 4.16 / 4.64 | 3.23 / 6.72 | 200 |
| decision comment | 4.00 / 4.61 | 3.28 / 5.47 | 200 |
| decision changes | 3.96 / 4.29 | 3.32 / 7.43 | 200 |
| verdict notes | 18.48 / 22.99 | 5.86 / 8.68 | 200 |
| rounds/submit | 6.25 / 10.56 | 5.12 / 8.36 | 200 |
| immediate accept | 18.94 / 23.24 | 6.28 / 9.87 | 200 |
| immediate select | 18.97 / 20.27 | 6.06 / 11.59 | 200 |
| immediate reject | 4.50 / 5.04 | 3.31 / 4.66 | 200 |
| immediate comment | 4.48 / 5.16 | 3.31 / 6.79 | 200 |
| immediate changes | 4.50 / 5.15 | 3.32 / 7.25 | 200 |
| push-session | 5.38 / 7.90 | 3.97 / 12.73 | 200 |
| push single | 5.25 / 9.18 | 4.08 / 6.80 | 200 |
| archive | 4.05 / 4.64 | 2.95 / 5.39 | 200 |
| restore | 4.10 / 4.85 | 2.90 / 8.29 | 200 |
| accept comment | 4.11 / 4.60 | 2.74 / 5.27 | 200 |
| rounds/discard | 2.33 / 3.12 | 2.05 / 3.08 | 200 |
| read-state write | 2.21 / 2.72 | 2.25 / 3.31 | 200 |
| seen write | 2.31 / 3.16 | 2.38 / 3.12 | 200 |
| GET /comments.json | 2.18 / 2.92 | 2.32 / 3.86 | 200 |
| conditional /comments.json | 1.97 / 2.73 | 1.50 / 2.53 | 304 |
| GET /api/read-state | 1.73 / 2.40 | 1.77 / 3.55 | 200 |
| conditional /api/read-state | 1.63 / 2.07 | 1.80 / 6.14 | 304 |
| GET /api/categories | 5.07 / 5.99 | 3.13 / 8.12 | 200 |
| conditional /api/categories | 5.14 / 6.26 | 3.14 / 6.53 | 304 |
| GET /api/session-monitor | 1.42 / 3.81 | 1.48 / 3.00 | 200 |
| conditional /api/session-monitor | 1.33 / 1.68 | 1.45 / 2.30 | 304 |
| GET /api/board | 1.37 / 1.66 | 1.42 / 6.02 | 200 |
| conditional /api/board | 1.32 / 2.07 | 1.40 / 3.36 | 304 |
| GET /api/plans/benchmark | 1.80 / 2.33 | 1.66 / 5.24 | 200 |
| conditional /api/plans/benchmark | 1.85 / 2.68 | 1.74 / 2.73 | 304 |

### FLD copy (primary)

| Route | Before p50 / p95 | After p50 / p95 | After status |
|---|---:|---:|---|
| comment create | 130.16 / 142.80 | 52.99 / 83.48 | 201 |
| reply | 136.84 / 151.68 | 29.45 / 38.83 | 200 |
| edit | 137.87 / 154.47 | 29.34 / 45.59 | 200 |
| comment batch | 141.17 / 156.76 | 32.50 / 56.94 | 200 |
| decision accept | 152.39 / 177.14 | 32.58 / 59.25 | 200 |
| decision select | 152.94 / 171.91 | 32.48 / 46.17 | 200 |
| decision reject | 143.47 / 162.18 | 29.43 / 47.92 | 200 |
| decision comment | 140.21 / 178.79 | 29.61 / 41.16 | 200 |
| decision changes | 140.24 / 192.43 | 29.48 / 42.53 | 200 |
| verdict notes | 157.21 / 176.89 | 32.54 / 49.64 | 200 |
| rounds/submit | 157.39 / 194.74 | 45.30 / 58.92 | 200 |
| immediate accept | 156.01 / 180.86 | 32.91 / 44.75 | 200 |
| immediate select | 157.56 / 187.12 | 32.33 / 37.94 | 200 |
| immediate reject | 139.90 / 159.51 | 30.12 / 34.90 | 200 |
| immediate comment | 144.95 / 158.92 | 29.51 / 33.65 | 200 |
| immediate changes | 138.35 / 154.87 | 29.32 / 35.92 | 200 |
| push-session | 147.88 / 176.08 | 37.42 / 45.16 | 200 |
| push single | 147.09 / 173.07 | 37.25 / 53.88 | 200 |
| archive | 139.05 / 153.89 | 29.43 / 33.75 | 200 |
| restore | 137.67 / 166.05 | 28.86 / 29.96 | 200 |
| accept comment | 140.81 / 184.16 | 29.01 / 36.47 | 200 |
| rounds/discard | 36.77 / 42.05 | 5.06 / 8.05 | 200 |
| read-state write | 5.37 / 12.13 | 5.24 / 19.41 | 200 |
| seen write | 27.67 / 35.73 | 27.68 / 44.21 | 200 |
| GET /comments.json | 91.42 / 115.40 | 81.36 / 93.99 | 200 |
| conditional /comments.json | 63.09 / 69.54 | 3.85 / 5.98 | 304 |
| GET /api/read-state | 2.43 / 8.33 | 2.57 / 12.32 | 200 |
| conditional /api/read-state | 2.21 / 2.95 | 2.27 / 3.74 | 304 |
| GET /api/categories | 1264.77 / 1344.84 | 28.48 / 37.26 | 200 |
| conditional /api/categories | 1279.37 / 1338.60 | 28.52 / 38.84 | 304 |
| GET /api/session-monitor | 1.72 / 2.36 | 1.59 / 10.78 | 200 |
| conditional /api/session-monitor | 1.38 / 1.92 | 1.48 / 4.40 | 304 |
| GET /api/board | 2.09 / 3.02 | 2.18 / 9.23 | 200 |
| conditional /api/board | 2.04 / 3.32 | 2.07 / 4.14 | 304 |
| GET /api/plans/benchmark | 35.51 / 38.45 | 1.65 / 4.56 | 200 |
| conditional /api/plans/benchmark | 35.53 / 39.59 | 1.61 / 3.05 | 304 |

### FLD comment during categories poll

| Metric | Before | After |
|---|---:|---:|
| p50 ms | 1294.15 | 31.71 |
| p95 ms | 1346.21 | 40.79 |
| Server CPU p50 ms | 138.53 | 30.05 |

## FLD CPU per write

Actual server-thread CPU, milliseconds p50, excluding contention.

| Route | Before CPU ms | After CPU ms |
|---|---:|---:|
| comment create | 127.00 | 51.03 |
| reply | 134.23 | 27.83 |
| edit | 134.55 | 27.91 |
| comment batch | 137.88 | 30.75 |
| decision accept | 149.60 | 30.87 |
| decision select | 150.30 | 30.54 |
| decision reject | 140.68 | 27.94 |
| decision comment | 136.32 | 28.02 |
| decision changes | 137.11 | 27.87 |
| verdict notes | 154.23 | 30.90 |
| rounds/submit | 150.94 | 43.57 |
| immediate accept | 152.67 | 30.87 |
| immediate select | 154.87 | 30.68 |
| immediate reject | 136.32 | 28.55 |
| immediate comment | 141.40 | 27.85 |
| immediate changes | 135.53 | 27.72 |
| push-session | 145.18 | 35.91 |
| push single | 143.83 | 35.63 |
| archive | 136.20 | 27.71 |
| restore | 134.99 | 27.36 |
| accept comment | 136.94 | 27.57 |
| rounds/discard | 35.79 | 4.46 |
| read-state write | 4.75 | 4.77 |
| seen write | 27.00 | 27.04 |

## Bytes per poll

Response-body bytes; headers remain on a 304. Actual gzip transfers on the unaugmented FLD copy; changed values are observed maxima. Before categories/board/plans have no ETag and resend unchanged bodies. Full compact identity JSON is 4,282,098 bytes; ?view=poll is 2,293,265 bytes. All history remains on disk, compacted on the next successful server write; no fields are deleted.

| Endpoint | Before changed gzip bytes | Before unchanged gzip bytes | After changed gzip bytes | After unchanged bytes |
|---|---:|---:|---:|---:|
| /comments.json?view=poll | 528,795 | 0 | 390,713 | 0 |
| /api/read-state | 44 | 0 | 44 | 0 |
| /api/categories | 10,595 | 10,595 | 10,596 | 0 |
| /api/session-monitor | 74 | 0 | 74 | 0 |
| /api/board | 50 | 50 | 50 | 0 |
| /api/plans/decision-cf527c30c7a76b563f11eeeb | 535 | 535 | 535 | 0 |

After transfers 31 changed comments bodies and 203 empty 304s across warmup, the simulated workload and real polling minute. The opt-in projection omits only carry_history in active/archived comments; decision_history remains because Findings/Library render it. Full comments.json and History remain complete.

## RSS and idle CPU

Thirty simulated minutes contain 225 eight-second poll ticks (six endpoints each), 30 content reloads and 60 writes (comment and Seen per minute). They execute in **14.91 real seconds**, using **13.77 server CPU seconds**. An actual 60-second no-request idle interval precedes the workload, and an actual 60-second polling interval at the normal eight-second cadence follows it. RSS/CPU are from ps on the separate server process.

| Measure | Before | After |
|---|---:|---:|
| No-request idle CPU seconds per actual minute | 0.01 | 0.00 (ps resolution 0.01 s) |
| Normal polling CPU seconds per actual minute | not completed: baseline guard stopped run | 0.29 |
| RSS after initial idle, MiB | 768.11 | 58.30 |
| RSS at simulated minute 1, MiB | 1,551.59, guard stop | 122.31 |
| Peak RSS through simulated minute 30, MiB | incomplete | 453.36 |
| RSS after real polling minute, MiB | incomplete | 234.58 |

| Simulated minute | After RSS MiB | Cumulative server CPU s |
|---:|---:|---:|
| 0 | 58.30 | 0.31 |
| 1 | 122.31 | 0.82 |
| 2 | 139.20 | 1.26 |
| 3 | 151.05 | 1.74 |
| 4 | 163.58 | 2.23 |
| 5 | 176.30 | 2.70 |
| 6 | 186.89 | 3.13 |
| 7 | 197.48 | 3.62 |
| 8 | 208.06 | 4.05 |
| 9 | 219.53 | 4.52 |
| 10 | 231.92 | 4.97 |
| 11 | 242.52 | 5.43 |
| 12 | 254.39 | 5.87 |
| 13 | 266.91 | 6.34 |
| 14 | 278.36 | 6.82 |
| 15 | 288.94 | 7.29 |
| 16 | 299.70 | 7.76 |
| 17 | 310.28 | 8.22 |
| 18 | 321.00 | 8.66 |
| 19 | 340.47 | 9.13 |
| 20 | 352.17 | 9.58 |
| 21 | 363.27 | 10.04 |
| 22 | 373.86 | 10.47 |
| 23 | 384.45 | 10.94 |
| 24 | 395.05 | 11.37 |
| 25 | 405.64 | 11.84 |
| 26 | 416.23 | 12.27 |
| 27 | 426.83 | 12.75 |
| 28 | 437.83 | 13.17 |
| 29 | 444.80 | 13.65 |
| 30 | 453.36 | 14.08 |

RSS rises in the compressed burst and does not return to startup size. This proves a lower observed peak and bounded application caches, not a long-term leak-free guarantee. Tracemalloc isolated large transient churn to repeated store decoding in categories. Five current evidence snapshots total about 1.6 MB per view and are not FLD's primary RSS cause.

## Changes and guarantees

- list_plans checks managed identities once and reads manual metadata directly. Categories passes one snapshot through list_plans, category_counts and current versions instead of ~35 full-store decodes under the shared write lock. Plan metadata polls also reuse the snapshot.
- One parsed revision per page is keyed by path/device/inode/size/mtime_ns/ctime_ns. Read routes share it under the store lock. A write transfers ownership out of the cache and returns it only after durable save; aborted writes cannot poison the cache. CLI replacements invalidate it. A legacy GET still defers migration until a write and preserves the v1 backup.
- Server writes use compact UTF-8 JSON, atomic replace, and file/directory fsync. There is no new database or reader format. History, permissions, Plans filing, durable rounds and uncertain-send suppression remain intact.
- At most four encoded comments bodies are retained for one revision: full/poll × identity/gzip. Unchanged polls reuse bytes without decoding, serialization or compression. All six endpoints have strong quoted SHA-256 ETags of their actual representation. If-None-Match returns empty 304s; auth/security/cache headers remain, including existing no-store policies. Gzip/identity tags differ and Vary: Accept-Encoding remains.
- The client should use comments.json?view=poll, send the stored ETag, and retain prior parsed data on 304 without calling response.json() or applying an update. The full endpoint stays compatible. The contract was sent to keep-drafts dispatch ctx_d94c5eac465a.
- Evidence remains frozen at accept/select time, including deferred votes. Vote-time checks hash current image bytes, mark changed sources incomplete, and repair changed frozen targets; the 512-entry stat-keyed digest cache is used only while rendering. View byte accounting measures retained Python objects under the existing 16-view/128 MiB ceilings.
- Push/Send persist their existing records, reply, then wake delivery in the background. Remaining server subprocesses use Path.home() as cwd. Request-local registry/name caches expire at the next request, including keep-alive.

## Profile and validation

Complete before/after cProfile traces are in v9o-server-latency.json. Separate profiled accepts exercise the expensive decision endpoint; timings above exclude profiling. The final FLD profile spends about 28 ms in durable compact save; the equivalent pretty-printed baseline spends most time in Python JSON encoding. Poll profiling exposed repeated full-store decoding, while the explicit overlap test establishes its impact on writes.

- Final full non-browser suite: **1,622 passed, 2 skipped** (208.10 s).
- Final affected browser suite: **26 passed** (131.54 s): approval catalog, verdicts, rounds/links, runtime HTTP, HTTP cache and card consistency.
- Focused security/cache/migration checks: **82 passed**, including aborted-save isolation and legacy GET-then-write migration; all are included in the final full suite.
- Changed Python files pass Ruff; git diff --check passes.

Existing review-key auth, Plans transactions, delivery uncertainty and browser behavior remain covered. No live restart, install, merge or release was performed.

## Independent server review (2026-10-22)

Reviewed PR #47 at 093598a independently; two correctness findings reproduced before fixes and now have regression tests.

| Finding | Reproduction and consequence | Fix |
|---|---|---|
| P1: vote-time image integrity bypass | Repeated writes through a memory mapping changed image bytes on this Mac while device, inode, size, mtime_ns and ctime_ns all stayed identical. Warm source hashes allowed approval without marking changed evidence incomplete; warm frozen-target hashes left a corrupted copy untouched. Both regression variants failed before the fix. | Accept/select now hash current source and existing frozen-target bytes. Stat-based digest reuse remains confined to rendering, outside the vote-time integrity boundary. |
| P2: round recovery exposed uncommitted edits | A prior round receipt triggers an intermediate durable save, which publishes the same mutable object to the snapshot cache. The remainder of rounds/submit clears an archived pending vote, then rejects an unknown version with HTTP 400; the next GET exposed that unsaved clearing although comments.json still contained it. The regression failed before the fix. | Reclaim the snapshot immediately after the recovery checkpoint, so an aborted continuation cannot remain cached. |

Added adversarial checks for same-size writes with restored mtime, atomic replacement with restored mtime, delete/recreate, all four full/poll identity/gzip validators, four current encoded representations across eight revisions, and conditional requests across authenticated/anonymous and distinct review-key identities. All pass. The fast-write regressions are now included in the GitHub CI gate.

No additional correctness finding in the reviewed paths: read authorization runs before conditional responses; author-sensitive read-state tags derive from the actual response; no shell/library/findings consumer reads carry_history; full comments.json and on-disk history retain it; compact stores remain ordinary UTF-8 JSON consumed through json.load/json.loads by eval, inbox, backfill and the baseline reader. Store and read-state locks have no reversed acquisition in these paths, and view-cache acquisition does not hold the view lock while taking the store lock. Representation retention is one revision with at most four bodies per handler; view retention remains bounded by 16 entries and 128 MiB of measured retained values, and the rendering digest cache holds at most 512 hashes. These bounds do not imply a long-term RSS guarantee or a byte ceiling on arbitrary comment-store growth.

Post-fix FLD benchmark: 30 samples per route on a private copied fixture, including 40 cited 512 KiB images and a fake one-second Orca. All 24 write p95 values remain below 64 ms: accept 61.99 ms, select 61.17 ms, immediate accept 62.53 ms, and worst immediate select 63.25 ms; unchanged polls on all six routes return 304 with no body. The integrity checks deliberately read image bytes at every new accept/select. Raw measurements: v9o-review-fld-writes.json. Source comments remain 6,457,554 bytes, SHA-256 b9e68dc3d934b0a33455345bf8ad07da1ef383a3531e391792b8c77e34dc360f.

Validation: full non-browser suite **1,630 passed, 2 skipped** (211.38 s); affected browser suite **26 passed** (127.82 s); focused regression suite **39 passed**; Ruff and git diff --check pass. A broader 195-case browser run was intentionally interrupted after 27 passing cases to keep browser verification scoped to these server changes; this is not a complete browser-suite result. CI now includes tests/test_fast_writes.py, and the completion receipt reports its final status. No web files, live pages, installed runtime or M5 state were changed. The parent v9o bead remains in progress for the coordinator to settle with its UI work.

## Reproduce

Run commands separately with the test interpreter. Both scripts import tests/conftest.py before annotate. /tmp/v9o-baseline is a git archive extraction of c6c59c7. Add --source /tmp/fld-stack-round8-copy --no-synthetic to bench_writes for FLD, and --contention-only for the overlap test. Default samples=30 and fake Orca delay=1 second.

```sh
env PYTHONPATH=/tmp/v9o-baseline/src /Users/changlee/projects/agent-annotate/codex/.venv/bin/python scripts/bench_writes.py --output /tmp/v9o-before-all.json --samples 30
env PYTHONPATH=/Users/changlee/orca/workspaces/codex/fast-writes/src /Users/changlee/projects/agent-annotate/codex/.venv/bin/python scripts/bench_writes.py --output /tmp/v9o-after-all-final.json --samples 30
env PYTHONPATH=/Users/changlee/orca/workspaces/codex/fast-writes/src /Users/changlee/projects/agent-annotate/codex/.venv/bin/python scripts/bench_server_session.py --source /tmp/fld-stack-round8-copy --poll-view '?view=poll' --output /tmp/v9o-fld-session-final3.json
env PYTHONPATH=/Users/changlee/orca/workspaces/codex/fast-writes/src /Users/changlee/projects/agent-annotate/codex/.venv/bin/python -m pytest tests --ignore=tests/browser -q
```

Raw p50/p95/max, server CPU, body bytes, HTTP statuses, profiles and per-minute resource samples accompany this report in v9o-server-latency.json.
