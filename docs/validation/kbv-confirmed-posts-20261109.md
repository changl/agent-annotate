# Confirmed posts update their own card — agent-annotate-kbv

The FLD copy's confirmed-post main-thread median fell from **136.013 ms to 34.970 ms** (seven posts per ref). The measured source change is `5a821bfff314897e9404b05839a1aac4a064a099` against main `82a81caa9501747678453a9a418464f3498903ef`. The [receipt](kbv-confirmed-posts-20261109.json) includes raw samples, source hashes and fixture hashes.

| Ref | Median | Seven one-second samples, ms |
| --- | ---: | --- |
| Main / 2.29.0 | 136.013 ms | 138.042, 111.475, 113.161, 143.159, 134.769, 143.286, 136.013 |
| Per-card confirmation | 34.970 ms | 31.75, 28.876, 34.97, 28.962, 84.966, 47.444, 47.298 |

PR #84's changelog records main-thread time in the second after a comment's answer. This comparison uses that window: real headless Google Chrome 156.0.8078.81 on M1Max.local, CDP `Performance.TaskDuration` delta, from releasing a held real POST response after the optimistic card has painted through confirmation and the following 1,000 ms. JSON decoding, the confirmation handler, iframe messages, layout, paint and normal timers run inside the interval; server latency and the earlier optimistic render are excluded. Each sample asserts that the optimistic card exists and the confirmed card remains exactly once. Normal polling stays enabled; the 84.966 ms candidate sample is retained, and the target is met by the requested median, not every window.

Both refs use fresh copies of one FLD snapshot: v729, 721 published history entries, 2,388 live and 71 archived cards. Only the copies are served, on loopback port **18771**; non-loopback browser requests are blocked. The copied owner metadata is removed, and tests' conftest redirects all estate roots into sandbox directories. The baseline is extracted from git, and both commands explicitly select their source with `PYTHONPATH`, avoiding the shared venv's editable checkout. The local runner and per-run logs are in `/tmp/aa-kbv-measure/bench.py`; the two runs are `baseline-final` and `candidate-final`. The historical 312 ms result used an older fixture and browser and is not the baseline for this comparison.

Confirmation now replaces the one rail card, updates its section membership/count and anchor pins, and uses the existing shared document-card renderer. Other card/editor nodes remain alive. Existing canonical labels remain stable; concurrent posts that confirm out of order get distinct provisional labels. Full renders remain available for explicit reloads, version changes and other actions. Read-only store scans reuse records that already carry their anchor instead of copying all records on each count.

Validation used `/Users/changlee/projects/agent-annotate/codex/.venv/bin/python` with `PYTHONPATH=/Users/changlee/orca/workspaces/codex/aa-kbv-render/src`:

- `scripts/ci.py`: **1,462 passed, 2 skipped**; Ruff and all seven JavaScript syntax checks passed.
- `pytest -q tests/browser/test_live_updates.py tests/browser/test_keep_drafts.py tests/browser/test_rail_jump.py tests/browser/test_rail_every_width.py tests/browser/test_draft_document_keys.py`: **50 passed**.
- Final `pytest -q tests/browser/test_live_updates.py tests/browser/test_image_view.py`: **11 passed**.
- Final confirmation regressions (`test_live_updates.py -k 'confirmed or out_of_order'`): **3 passed**, including unchanged unrelated rail/document/pin nodes, a second reply and menu actions on patched cards, long-comment clamping, and stable numbering with overlapping posts.
- These runs cover **53 unique browser cases**. JUnit files and the final fast-gate log are retained in `/tmp/aa-kbv-measure/`.

The full suite is left to the coordinator. No merge, release, install, rollout, live-page write, other-Mac access, memory, skill or instruction-file change was performed.
