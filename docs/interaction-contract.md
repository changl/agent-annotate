# Interaction contract

The contract has one home:
[src/agent_annotate/skills/claude/references/interaction-contract.md](../src/agent_annotate/skills/claude/references/interaction-contract.md).
Every behavior listed there is a release gate, and the tests under `tests/`
and `tests/browser/` are named after them. The headings, so a reader knows
what is covered:

- **Reviewing** — one visible tab that scrolls to its bottom, diagram
  navigation, pin-to-card focus, granular pin placement with the row-band
  rule, hover linking, native controls left alone, independent collapsible
  rails, the compact layout, and chrome that is served rather than baked.
- **Comments and decisions** — the lifecycle, no silent confirmation, comments
  surviving version swaps, cards that render everything they ask and are
  refused rather than dropped when malformed or oversize, reversible verdicts,
  round mode with exactly one push per submitted round, and idempotent
  re-posing.
- **Delivery and ownership** — truthful `Sent`/`Queued`/`deferred`, takeover
  that stops only the old monitor, append-audited replayable feedback,
  owner-targeted per-session hook notices that never touch the inbox cursor,
  no action on a partial round, and leases released on SIGTERM.
- **Publishing** — no URL before rendered anchors are read back at every hop,
  Access login as unverified rather than failed, edge-path verification, and
  version history registered once.

The schema those gates apply to is in
[decision-cards.md](../src/agent_annotate/skills/claude/references/decision-cards.md),
and the event list in
[telemetry-and-eval.md](../src/agent_annotate/skills/claude/references/telemetry-and-eval.md).
