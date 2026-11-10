# Stage 5g rollout rehearsal on M1 copies

All 17 existing registered page directories were cloned into `/tmp/aa-stage5g-41wQYw`, with their buses, cursors and delivery journals, while live servers kept running. The registry has 18 rows: `agent-memory-consolidation/annotate-memory-consolidation` points at a directory that no longer exists. Of the copies, 14 have active current documents, two are archived, and `codex-memory-consolidation/memories` has no `current.html`.

`scripts/rollout.py`'s `apply` ran against the isolated registry and real sandbox servers on ports 18700–18716. It restarted the 14 active pages, ordered by comments-file size, held FLD on JSON, then moved just FLD in a second apply. Every migrated restart stopped its server before import, required diff 0, verified the replacement's exact process identity, capabilities version/build/assets and rendered anchors, and read `/api/history?latest=1`. Every active page then received a note or answer and Send; its submitted round was verified in page.db and the latest history. All ended back on JSON using `annotate db off`, then served JSON successfully. The 14 replayed pages recorded **0 `store_foreign_write`** each and diff 0 after replay.

This is source integration evidence, not released-wheel validation: no version was bumped, wheel built or tool installed. The sandbox uses this worktree's source (still reporting 2.29.0), and supplies no-op install/preflight/skill-sync seams to apply's 2.30.0 migration path. Runtime checks expect the actual source version/build/assets. Because the shared venv imports another checkout under `-I`, sandbox launches use this worktree's `PYTHONPATH` without `-I`; the production launch and environment isolation remain covered by focused tests. The final install, release and full suite belong to the coordinator.

| Page | Items at import | Import seconds | Diff | Capabilities | Round replay | db off |
|---|---:|---:|---|---|---|---|
| reviews/fld-stack-round8, held | 2,459 | — | JSON held | 200 | Latest read; move follows | Already JSON |
| FLD usage audit/page | 54 | 0.039 | 0 | 200 | Note + Send | JSON served |
| codex-memory-consolidation/memories | 0 | 0.019 | 0 | Restart refused | No current document | JSON |
| leadory/wind-down-plan | 7 | 0.023 | 0 | 200 | Note + Send | JSON served |
| multimac-orch/multimac-orch | 26 | 0.029 | 0 | 200 | Note + Send | JSON served |
| multimac-orch/storage | 14 | 0.023 | 0 | 200 | Note + Send | JSON served |
| ponytail/installation | 0 | 0.019 | 0 | 200 | Note + Send | JSON served |
| rebex/rebex | 259 | 0.080 | 0 | 200 | Note + Send | JSON served |
| reviews/annotate-assessment-20260917 | 18 | 0.032 | 0 | 200 | Note + Send | JSON served |
| reviews/annotate-conformity-20260927 | 120 | 0.066 | 0 | 200 | Note + Send | JSON served |
| reviews/annotate-owner-takeover-20260922 | 11 | 0.033 | 0 | 200 | Note + Send | JSON served |
| reviews/annotate-weekly-20260929 | 0 | 0.030 | 0 | 200 | Note + Send | JSON served |
| reviews/fld-stack-round8, moved | 2,459 | 0.981 | 0 | 200 | Answer + Send | JSON served |
| reviews/skills-consolidation-20260929 | 2 | 0.023 | 0 | 200 | Note + Send | JSON served |
| reviews/windmill-agent-guidance-20260925, archived | 3 | 0.2 | 0 | 200 | Writes refused 410; reads 200 | JSON served |
| reviews/windmill-build-pilot2-20260925, archived | 3 | 0.2 | 0 | 200 | Writes refused 410; reads 200 | JSON served |
| reviews/windmill-cheerticketing-plan-20260922 | 19 | 0.028 | 0 | 200 | Note + Send | JSON served |
| windmill/workflow-plan | 9 | 0.032 | 0 | 200 | Note + Send | JSON served |

The archived pages are excluded from rollout, so their import/diff/read-only/db-off checks ran separately through the existing Stage 5f rehearsal. The memories copy's import/diff/off also ran separately, without inventing a missing document or replaying a round. It is named in the Mac receipt. The held FLD row uses the item count measured when that same copy was subsequently imported.

The Mac receipts were:

```text
M1 2.30.0 ok · 14 pages restarted · 1 skipped · doctor ok · rollback kept: 2.29.0 · JSON: fld-stack-round8 (held for this rollout), memories (no current version)
M1 2.30.0 ok · 1 pages restarted · 1 skipped · doctor ok · rollback kept: 2.29.0 · JSON: memories (no current version)
```

Raw receipts and per-page traces: `/tmp/aa-stage5g-41wQYw/results.json`. Rehearsal driver: `/tmp/aa-stage5g-rehearse.py`. `/tmp/aa-stage5g-41wQYw/cleanup.json` confirms zero remaining sandbox servers and zero browsers started. Only page copies and the sandbox registry were changed; no Rebex worktree, FLD source, live page, live registry, sweep installation, LaunchAgent or other Mac was changed.

For release N, the coordinator runs the full suite, merges the PRs, builds/releases 2.30.0, then applies on M1. FLD is held automatically on M1; additional pages can be held with repeatable `--hold-json SLUG`. Holds persist in the page registry, including when a page is republished or revived. After seven days with 0 differences and 0 `store_foreign_write`, the operator can move FLD with one command:

```sh
python3 scripts/rollout.py apply 2.30.0 --mac M1 --move-page reviews/fld-stack-round8
```

That command is the operator's explicit release of the hold; it does not measure or certify a seven-day soak. Moving a held page on the already installed release preserves the original release rollback, so `rollout.py rollback` still returns the Mac to its prior release and turns every originally restarted page back to JSON, including the later move. Per-page rollback is `annotate db off PROJECT/SLUG`. `rollout.py rollback --mac M1` turns each affected page's database off before installing its saved old wheel, while the current runtime can still export JSON.

Release N+1 remains separate: first verify the seven-day soak, zero foreign writes and `doctor --versions` showing every page on N. Only then retire JSON exports and `.lock` files, keeping bus exports and `db export` for rollback. M5 and M1Max16 need separate approval, and M5 follows M1 FLD's seven-day soak; no other Mac was contacted here.

Focused validation: **84 passed** across `tests/test_rollout.py`, `tests/test_deployment.py`, `tests/test_store_db.py` and `tests/test_version_guard.py`, plus the focused publish-hold persistence test in `tests/test_publish_gate.py`, with `PYTHONPATH=/Users/changlee/orca/workspaces/codex/aa-stage5g/src` and the shared venv's Python. Ruff passed for the changed Python files; `git diff --check` passed. The separate ownership-hook PR has **9 passing sweep tests**. The full suite, release-wheel validation, live migration and seven-day soak were not run here.
