# Post-reboot re-attach: Orca panes with no resume record

Captured 2026-07-31 ~11:20 PDT, before a planned full computer restart.

Orca will relaunch these 11 panes as **fresh agents** — it holds no session id for them.
Their transcripts survive on disk. Run the command below inside the listed worktree to re-attach.

Review page: https://connelly.leadory.net/orca-restart-restore-audit/

| # | Agent | Worktree | Pane title | Session id | Id source | Re-attach command |
|---|-------|----------|-----------|------------|-----------|-------------------|
| 1 | claude | `/Users/changlee/orca/workspaces/claude/gather-leads-v2` | (untitled) | `65cee90f-07af-4af8-831c-7c88bf99d505` | argv --resume | `claude --dangerously-skip-permissions --resume 65cee90f-07af-4af8-831c-7c88bf99d505` |
| 2 | claude | `/Users/changlee/projects/agent-annotate/codex` | (untitled) | `1f6c7f37-d0d3-4db1-af24-5ce9e272bf50` | argv --resume | `claude --dangerously-skip-permissions --resume 1f6c7f37-d0d3-4db1-af24-5ce9e272bf50` |
| 3 | claude | `/Users/changlee/projects/agent-annotate/codex` | (untitled) | `0614b174-cc56-4358-bc02-022538f01d48` | argv --resume | `claude --dangerously-skip-permissions --resume 0614b174-cc56-4358-bc02-022538f01d48` |
| 4 | claude | `/Users/changlee/projects/agent-annotate/codex` | ✳ Update and verify RTK plugin across Cl | `866a45e2-4e6b-4072-b7e2-2426f91eb3bc` | transcript-birth-match | `claude --dangerously-skip-permissions --resume 866a45e2-4e6b-4072-b7e2-2426f91eb3bc` |
| 5 | claude | `/Users/changlee/projects/agent-annotate/codex` | (untitled) | `1f6c7f37-d0d3-4db1-af24-5ce9e272bf50` | argv --resume | `claude --dangerously-skip-permissions --resume 1f6c7f37-d0d3-4db1-af24-5ce9e272bf50` |
| 6 | claude | `/Users/changlee/projects/connelly/claude` | (untitled) | `9d4210a3-2ef1-40da-a429-0ece67219ec8` | argv --resume | `claude --dangerously-skip-permissions --resume 9d4210a3-2ef1-40da-a429-0ece67219ec8` |
| 7 | claude | `/Users/changlee/projects/connelly/claude` | (untitled) | `1494262b-582e-49b7-bdbd-727fe666544a` | argv --resume | `claude --dangerously-skip-permissions --resume 1494262b-582e-49b7-bdbd-727fe666544a` |
| 8 | claude | `/Users/changlee/projects/connelly/claude` | (untitled) | `26ab89eb-503c-4dc3-87f5-65cae032fda9` | argv --resume | `claude --dangerously-skip-permissions --resume 26ab89eb-503c-4dc3-87f5-65cae032fda9` |
| 9 | claude | `/Users/changlee/projects/connelly/claude` | (untitled) | `26ab89eb-503c-4dc3-87f5-65cae032fda9` | argv --resume | `claude --dangerously-skip-permissions --resume 26ab89eb-503c-4dc3-87f5-65cae032fda9` |
| 10 | codex | `/Users/changlee/projects/leadory/leadory-codex-a0la-live-denominator-audit-v1` | a1se3-context-builder | _none found_ | - | `codex` then pick from the session list (no rollout found — pane likely never took a prompt) |
| 11 | codex | `/Users/changlee/projects/leadory/leadory-codex-a0la-live-denominator-audit-v1` | a1se3-context-builder | _none found_ | - | `codex` then pick from the session list (no rollout found — pane likely never took a prompt) |

## Notes

- Two panes share session id `1f6c7f37-d0d3-4db1-af24-5ce9e272bf50` and two share `26ab89eb-503c-4dc3-87f5-65cae032fda9`: earlier handoffs resumed the same transcript into two panes. Re-attach one pane per id; a second `--resume` on the same id appends to the same file.
- If a `codex resume <id>` reports the session is unknown, retry with `CODEX_HOME="$HOME/Library/Application Support/orca/codex-runtime-home/home" codex resume <id>` — Orca keeps a second Codex home and some rollouts live only there.
- Claude Code and Codex both open a directory-scoped session picker when run with no id, which is the fallback for the two unknown panes.
- One covered pane is also wrong: worktree `/Users/changlee/projects/connelly/codex` has ledger id `019f95ed-…` (Jul 24) but the running process created `019f9aa9-29b1-7611-82a7-e7f6054779e9` (Jul 25 12:03). Orca will resume the older conversation there; re-attach with `codex resume 019f9aa9-29b1-7611-82a7-e7f6054779e9` if that pane matters.
