# Lighter coordination (Stage 2): opt-in tools and the 250k recycle

Stage 2 of [the simplification plan](validation/simplification-plan-20261104.md). Everything here is opt-in per Run. No other orchestrator changes until Chang approves the rollout.

## The tools

| Need | Command | Replaces |
|---|---|---|
| Wait for workers | `orca-quiet-wait-filter --run RUN` from the skills-org branch `changl/quiet-wait-peek` (not yet linked as `orca-quiet-wait`) | Waking for every status note |
| Ports, CI slots, disk | `python3 scripts/lease.py take NAME --run RUN` · `release` · `list` | Status → "GO" reply round trips |
| Where things stand | `python3 scripts/run_summary.py RUN` (40 lines or fewer) | `pending.txt`, long closing messages, re-reading history |
| Worker brief | `python3 scripts/brief.py BEAD --run RUN --base B --branch X --delta "…"` | Re-typing the rules into every brief |

**Quiet-wait.** Status notes go to `~/.local/state/orca-runs/RUN/status.log` and never wake the coordinator. It wakes on worker_done, question, escalation and unknown types. It also wakes on result-style status subjects (RESULT/PASS/FAIL/BLOCKED/CHANG…) and on a status sent with `--priority high`. A digest of status lines arrives at most once every 30 minutes (`--digest-min`). Waking mail is printed in full and left unread; re-arming marks it read, so neither `check` nor `--ack` is needed. `--wake-on-status` restores the old behaviour. Only one waiter runs per Run; a second one is refused.

**One-line outputs.** No wrapper was built. Orca 1.4.247 prints concise receipts by default; `--full` opts into the long record. A `worker-start --json` receipt in the agent-annotate coordinator transcript fell from about 2,550 characters (Oct 31 to Nov 2) to about 450 (Nov 4). Don't pass `--full`. `inbox` without `--full` already prints three lines per message.

## Recycle at 250k

At each exit, quiet-wait reads the coordinator's own transcript. At 250k context or more it prints `Context NNNk >= 250k: recycle now`. Do it at the next quiet point, when no wake is unhandled:

1. **State lives outside the session.** Make sure Beads match reality: claimed, closed with proof, blocked with a reason. Every open decision should be on the page or in a bead, not only in chat.
2. **Digest.** Run `python3 scripts/run_summary.py RUN > ~/.local/state/orca-runs/RUN/digest.md`.
3. **Handoff doc.** Follow the `orca-handoff` skill, steps 0–3: own terminal, clean tree, doc, stop background waits. Its *Open work* section is the digest plus only the reasoning the digest cannot show: decisions in flight, must-not-undo rules, and mistakes made. Aim for about 20k tokens in total for the successor to read.
4. **Successor.** Follow `orca-handoff` step 4. The prompt adds: `orca orchestration run-use --id RUN`, then `python3 scripts/run_summary.py RUN`, then re-arm quiet-wait. The takeover check (step 5) must answer five state questions from the digest and doc:
   - Which workers are live, and on what?
   - Which beads are in progress?
   - What waits on Chang?
   - Which leases are held?
   - What was the last decision?
5. **Cut over only after step 5 passes.** Then follow `orca-handoff` steps 6–7. Re-claim owned annotate pages from the new session (`annotate claim`).

Rollback: `--recycle-at 0` turns the line off.

## Opting a Run in

From the coordinator of RUN, start the helper in the background, instead of `orca-quiet-wait`:

```
/Users/changlee/orca/workspaces/skills-org-quiet-wait-peek/bin/orca-quiet-wait-filter --run RUN
```

Generate worker briefs with `scripts/brief.py`, so workers lease instead of asking and send no progress notes. Measure before and after with `scripts/orch_cost.py` (Stage 0).
