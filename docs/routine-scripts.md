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

**Other Macs.** `--mac M5` or `--mac M1Max16` needs `--approval "card #N"` (Chang's yes), even for `plan`. Without it the script refuses and sends nothing. With it, the script opens an `orca --environment M5Max|M1Max16 terminal`. That terminal runs the controller already there, `~/.local/share/annotate-rollout/rollout.py … --local`, with the release as data. Under the rollout lock, the controller replaces itself with the release's `rollout.py` (hash checked against `SHA256SUMS`) only when that release is newer than both the floor and the release it came from (`controller.json`), then runs the request on the new one. For 2.34.0 or later, the terminal first downloads the release's `rollout.py` into a folder of this request's own and checks it. Then `rollout.py bootstrap` runs from there: under the same lock, if no controller is placed, it checks the bytes again, writes the controller atomically, and writes `controller.json` last. A missing, empty or cut-off `controller.json` counts as no controller, so the next such run places one again. Until one is placed, `rollback` and anything older are refused there. The script waits for a marker line and prints the remote result. The typed command never contains `$`. M1Max16 also needs `--worktree <selector>`.

**Sandbox.** Set `UV_TOOL_DIR` and `UV_TOOL_BIN_DIR` together; with only `UV_TOOL_DIR` set, the script refuses, because the live launcher would be replaced. Also set the package's `ANNOTATE_*` path overrides, `ANNOTATE_ROLLOUT_HOME`, and optionally `ANNOTATE_ROLLOUT_RELEASES`. Put the sandbox `bin` first on `PATH`, because doctor checks the `annotate` it finds there.

`release.py build` copies `rollout.py` into the release and lists it in `SHA256SUMS`.

## Hourly housekeeping: `scripts/sweep.py`

| Command | Prints |
|---|---|
| `sweep.py beads` | `beads: 2 open · 2 ready · 1 in progress over 24 h · 0 closed without proof` |
| `sweep.py disk` | `disk: 293 GiB free · buses 0.0 GiB · 29 quiet buses over 30 days` |
| `sweep.py sessions [--apply]` | `sessions: 0 finished worktrees (PR merged, bead closed, clean tree) · 0 removed` |
| `sweep.py owners` | `owners: 2 pages used in the last 7 days with no running owner · 1 Send waiting` |
| `sweep.py all` | the four lines |

`owners` names each page someone used in the last 7 days (restart events don't count) whose owning agent is not running, with any Sends waiting for it. The revive watchdog re-binds a resumed owner within a minute, so a page listed here means that session never came back. `ownership:` is a separate line: it reports only whether the cross-Mac ownership manifest ran, not whether owners are alive.

Each run writes its summary lines, a blank line and the judgment items (stale beads, quiet buses, finished worktrees, stopped owners) to `~/.local/share/annotate-sweeps/latest.txt`. `run_summary.py` shows those summary lines by default (`--extra FILE …` for other sources).

`sessions` removes a worktree only with `--apply`, and only when all three hold:

- its PR is merged;
- a bead named in the PR, branch or path exists and is closed;
- `git status` is clean.

Main worktrees and the deny list in the code (`rebex-library-performance`) are never inspected. A merged, clean worktree that names no bead is listed for a coordinator to decide.

**Timer.** `scripts/launchd/com.changlee.annotate-sweep.plist` runs `sweep.py all` hourly, report only, at the Standard process type: under Background, I/O throttling on a busy Mac pushed the ownership check past its 300 s timeout. Install steps are in its header comment. To change an installed job, edit only the changed key in `~/Library/LaunchAgents/com.changlee.annotate-sweep.plist` (the installed copy also sets `ANNOTATE_OWNERSHIP_MANIFEST`), then `launchctl bootout gui/$(id -u)/com.changlee.annotate-sweep` and `bootstrap` it again; a loaded job keeps its old settings until then. It is not loaded until Chang says yes. To stop it, run `launchctl bootout` and remove the file.


## Board judgement on turns: `annotate board`

`annotate board PROJECT/SLUG` checks that page's Beads board, reports the two guarded fixes (it applies them only with `ANNOTATE_BOARD_APPLY=1`), saves durable follow-ups and lists open items with their settle commands. It runs only when invoked; hooks never run it. A submitted round is the trigger: when local routing shows a board, round delivery adds one line asking the owner to have a separate worker run `annotate board PROJECT/SLUG`, settle each listed item and report one line, so judgement stays out of the owner's context. Stored follow-ups are never listed in round prompts, per-turn notices or session start. No board timer or model wake-up exists, and `scripts/sweep.py` does not check boards.

Board discovery reads owned pages and runs `bd where --json` in each owner's worktree, falling back to the page's repository. It chooses the newest owned page per board unless `$ANNOTATE_STATE_DIR/board-pages.txt` pins that board to an owned, active page. Each line is `<board path> <project/slug>`, for example:

```text
/Users/changlee/.local/share/beads/clients/fld/.beads reviews/fld-stack-round8
```

A pin changes which page supplies owner cards and receives follow-ups; the board's repository and merge-proof lookup stay the same. An invalid page pin skips that board and reports the reason. Unpinned boards keep discovery.

Every board uses the same rules. `annotate board` only reports by default: bead writes belong to the hourly cleaner, and a page turn writes only with `ANNOTATE_BOARD_APPLY=1` (`ANNOTATE_BOARD_DRY_RUN=1` still forces a report). Since 2.32.1; before that, a turn reset 7 live M5Max FLD beads whose workers its liveness check missed. When applying, a blocked bead reopens only when its BLOCKED BY note names only beads and every note/dependency blocker is closed. An in-progress bead resets only when it was first flagged at least 55 minutes before this check and is still flagged, with no live assignee or ctx/term in any note line (live = any active worker on this Mac, the M5 Max or the M1 Max 16, `unverifiable` included); any number of checks can occur between those observations, and clearing the flag restarts the clock. Human, lead and orchestrator assignees are guarded (`LEAD|ORCH|^m1[a-z]$`, FLD's skip names, and git user.name). A missing liveness source, or a worker list limited to the caller's own Orca run, blocks resets. Every write adds one `SWEEP-AUTO` note and reads back its result. Merge proof, owner cards and blocker sorting only report. FLD retains its four merge-proof repositories and latest dated sweep notes; other boards use the owner's repository.

Checks take a per-board lock and keep settled delta state and findings/actions/summary receipts under `$ANNOTATE_STATE_DIR/board-checks/`. Follow-ups live in `board-followups.json` beside the selected page, atomically replaced. `annotate board PROJECT/SLUG --settle KEY "verdict"` appends a decision against the current fingerprint to `board-verdicts.ndjson`, without running a check; changed evidence reopens it. List and settle print one line; `--json` returns full records. A failed or timed-out check still lists stored items and adds one `board check failed: <reason>` line (or an error field with `--json`), exiting nonzero. Neither file is a page store record, and neither command writes comments.json or page.db.

For a read-only rehearsal, copy the registry JSON files into a temporary `ANNOTATE_STATE_DIR`, put any page pins there, set `ANNOTATE_BOARD_DRY_RUN=1` so an inherited `ANNOTATE_BOARD_APPLY` cannot write to a real board, and set `ANNOTATE_BOARD_FOLLOWUPS_ROOT` to a second temporary directory. Follow-up output then goes to `ROOT/PROJECT/SLUG`; state, locks and receipts stay under the temporary state root. There is no apply-list file or per-board write gate.
