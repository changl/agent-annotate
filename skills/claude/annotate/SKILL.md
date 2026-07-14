---
name: annotate
description: Build, publish, test, and manage interactive annotatable HTML artifacts for plans, schemas, diagrams, mockups, tables, and documents. Use when the user wants click-to-comment visual feedback, pinned review threads, versioned artifact review, push-to-session delivery, annotation-page ownership, or a durable handoff between coding-agent sessions.
---

# Agent Annotate for Claude Code

Use the shared `annotate` CLI and persistent runtime. Follow the complete
interaction contract in `references/interaction-contract.md`.

1. Run `annotate doctor`.
2. Migrate or create the slug directory with stable `data-anchor-id` values.
3. Run `annotate publish <slug-dir>`.
4. Arm Claude Code's persistent Monitor with `annotate monitor <slug> --owner
   <session-id>`.
5. During handoff, the incoming session runs the same command with `--takeover`.
6. Read `annotate inbox <slug> --unread`, reply, and mark addressed. Never
   confirm or archive on the user's behalf.
7. Verify scrolling, exact pin-to-card navigation, granular anchors, diagram
   navigation, and truthful push delivery before reporting success.

Keep the server running during handoffs. If no live monitor exists, feedback
must remain queued and visible.

