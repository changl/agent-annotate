---
name: annotate
description: Build, publish, test, and manage interactive annotatable HTML artifacts for plans, schemas, diagrams, mockups, tables, and documents. Use when the user wants click-to-comment visual feedback, pinned review threads, versioned artifact review, push-to-session delivery, annotation-page ownership, or a durable handoff between coding-agent sessions.
---

# Agent Annotate

Use the installed `annotate` CLI. Keep artifact content, the persistent review
runtime, and the temporary coding-agent owner as separate concerns.

## Workflow

1. Run `annotate doctor` and resolve failures before publishing.
2. Reuse an existing slug directory when present. For legacy HTML, run
   `annotate migrate <file> --copy --slug <slug>`.
3. Give every commentable element a stable `data-anchor-id`. Use an entity or
   section identity, never a viewport position, as the stable portion.
   Interactive elements — links, form controls, ARIA widgets, contenteditable
   and focusable regions — keep their native click behavior instead of opening
   a comment. Mark a custom widget `data-annotate-interactive` to get the same
   treatment; Alt/Option-click forces a comment on any excluded element.
4. Run `annotate publish <slug-dir>` and report both its local and configured
   public URL.
5. Use `annotate sessions --cwd <project>` to show candidate Codex threads.
   Never select a recipient silently.
6. After the user or current context identifies the thread, run `annotate
   connect <slug> --thread <id>`. Use `--takeover` only for an explicit handoff.
7. Read feedback with `annotate inbox <slug> --unread`. Reply or mark addressed;
   never confirm or archive on the user's behalf.
8. Verify the browser and monitor contracts before reporting a release as
   delivered.

## Anchor precision

Store both a stable parent anchor and, for new feedback, the inner target plus
click offset. Clicking a numbered pin must focus that exact rail card. Preserve
parent-anchor fallback for older comments.

## Release gates

Read [interaction-contract.md](references/interaction-contract.md) before any
shell, adapter, monitor, or publishing change. Treat every listed behavior as a
testable contract. For public pages, verify through the real authenticated edge
path in addition to localhost.

## Handoffs

The web server persists. Transfer only the exclusive page-owner lease. One
session may own multiple pages, but one page must not have concurrent owners.
If no owner is reachable, preserve the event and report it as queued.

