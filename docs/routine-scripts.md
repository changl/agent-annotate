# Routine jobs as scripts (Stage 4)

Stage 4 of [the simplification plan](validation/stages-3-5-specs-20261104.md#4-scripts-for-routine-jobs-45-worker-days). Each command prints one line; no agent judgment runs inside them.

## Release rollout: `scripts/rollout.py`

| Command | Prints |
|---|---|
| `rollout.py plan 2.29.0 --mac M1` (read-only) | `M1 2.28.3 → 2.29.0 · 14 pages: 12 restart, 2 skip (no current version) · 2 skill dirs · ready` |
| `rollout.py apply 2.29.0 --mac M1` | `M1 2.29.0 ok · 12 pages restarted · 2 skipped · doctor ok · rollback kept: 2.28.3` |
| a step fails | `M1 FAILED at restart fld-stack-round8 (…) · rolled back to 2.28.3 · doctor ok` |
| `rollout.py rollback --mac M1` | `M1 back on 2.28.3 · 12 pages restarted · doctor ok` |
| `rollout.py status` | `M1 2.29.0 ok · M5 2.28.3 (1 behind) · M1Max16 unknown` |

`apply` runs, stopping and rolling back at the first failure:

1. **Preflight.** It re-runs `plan`, checks the wheel against the release's `SHA256SUMS`, and needs 2 GB free.
2. **Backup.** It records the old version and wheel URL, and tars the skill dirs listed in `skill-installs.json` to `~/.local/share/annotate-rollout/<old>-<time>/`.
3. **Install.** `uv tool install --python 3.12 --force "agent-annotate[mcp] @ <wheel URL>"`.
4. **Skills.** `sync-skills`, run by the uv tool's Python.
5. **Restart.** Every running registered page that `plan` listed goes through `deployment.restart_record`, one at a time. Pages that `plan` skipped are left alone.
6. **Check.** `doctor --versions --json` must show the new version for the release, the launcher, the skills and the plugin. Then one loopback `/api/capabilities` read per restarted page.
7. **Record.** One JSON line goes to `~/.local/share/annotate-rollout/log.ndjson`.

Rollback reinstalls the old wheel and restores the skills tarball. It restarts only the pages this apply touched; the `rollback` command restarts all of them.

**Other Macs.** `--mac M5` or `--mac M1Max16` needs `--approval "card #N"` (Chang's yes), even for `plan`. Without it the script refuses and sends nothing. With it, the script opens an `orca --environment M5Max|M1Max16 terminal`. That terminal downloads `rollout.py` and `SHA256SUMS` from the release, checks the hash and runs `rollout.py … --local`. The script waits for a marker line and prints the remote result. The typed command never contains `$`. M1Max16 also needs `--worktree <selector>`.

**Sandbox.** Set `UV_TOOL_DIR` and `UV_TOOL_BIN_DIR` together; with only `UV_TOOL_DIR` set, the script refuses, because the live launcher would be replaced. Also set the package's `ANNOTATE_*` path overrides, `ANNOTATE_ROLLOUT_HOME`, and optionally `ANNOTATE_ROLLOUT_RELEASES`. Put the sandbox `bin` first on `PATH`, because doctor checks the `annotate` it finds there.

`release.py build` copies `rollout.py` into the release and lists it in `SHA256SUMS`.

## Hourly housekeeping: `scripts/sweep.py`

| Command | Prints |
|---|---|
| `sweep.py beads` | `beads: 2 open · 2 ready · 1 in progress over 24 h · 0 closed without proof` |
| `sweep.py disk` | `disk: 293 GiB free · buses 0.0 GiB · 29 quiet buses over 30 days` |
| `sweep.py sessions [--apply]` | `sessions: 0 finished worktrees (PR merged, bead closed, clean tree) · 0 removed` |
| `sweep.py all` | the three lines |

Each run writes its summary lines, a blank line and the judgment items (stale beads, quiet buses, finished worktrees) to `~/.local/share/annotate-sweeps/latest.txt`. `run_summary.py` shows those summary lines by default (`--extra FILE …` for other sources).

`sessions` removes a worktree only with `--apply`, and only when all three hold:

- its PR is merged;
- a bead named in the PR, branch or path exists and is closed;
- `git status` is clean.

Main worktrees and the deny list in the code (`rebex-library-performance`) are never inspected. A merged, clean worktree that names no bead is listed for a coordinator to decide.

**Timer.** `scripts/launchd/com.changlee.annotate-sweep.plist` runs `sweep.py all` hourly, report only. Install steps are in its header comment. It is not loaded until Chang says yes. To stop it, run `launchctl bootout` and remove the file.
