Bead agent-annotate-dlj.

**Root cause.** The 2.28.3 re-bind (eii, #97) only re-bound an owner whose resumed session was in the same Orca terminal. Orca relaunches every resumed pane under a new handle, so after the 2026-11-23 reboot no page re-bound. Sends queued on dead terminals until someone typed into the agent. Nothing outside the agent gave an idle resumed session a turn. SessionStart also read its payload with a 10 ms timeout.

**Change.**
- Re-bind when the session and Orca worktree match and the old process is gone. The handle can change.
- The revive watchdog (`com.agent-annotate.revive`, every 60 s and at login) re-binds from outside. It looks for exactly one live claude/codex process resumed with the session id, plus its Orca terminal. Queued Sends then deliver and start a turn. If nothing is queued, the owner gets one wake-up asking it to re-arm its wait loop and read its inbox. It never gets more than one.
- SessionStart waits up to 1 s for its payload.
- `sweep.py owners`: lists pages used in the last 7 days whose owner is not running, in plain words, plus any Sends waiting.

**Proof (M1, sandbox port 18700).** Session owned `proof/proof-page`, then was killed. Round A was sent and queued with "Owner process ended". `claude --resume` ran in a new terminal. The watchdog re-bound the owner and delivered round A (`input_accepted`, `turn_started`, acknowledged). Round B after the resume was also acknowledged with `turn_started`. A second kill and resume with nothing queued got one wake-up (`turn_started`).

Tests: test_delivery, test_session_start, test_revive, test_sweep, test_workspace_commands, test_backend_review_fixes and test_auto_claim pass. I did not run the full suite.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
