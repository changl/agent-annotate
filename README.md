# Agent Annotate

One project page for progress, feedback, and decisions across Claude Code and Codex sessions. Agents build the project; annotate records meaningful results and choices.

## Project workflow

1. Run `annotate workspace --json` once. Reuse its directory and URL across sessions and worktrees. Select an existing main page with `workspace --select PROJECT/SLUG`; post into Review, Library, Findings, or Plans on that page.
2. Share the full URL in the first project response and every update/feedback request. Tailscale Funnel is the default. No new Cloudflare routes.
3. Update only for a meaningful result, changed blocker, or required decision. Batch related changes; one sentence per item, ideally under 30 words. Identical progress data is a no-op.
4. Continue authorized work. Routine tests, repeated failures, and annotate upkeep do not create approval requests or feedback rounds.
5. After **Send**, read the submitted answers once and act. A successor claims the same page; the server owns Orca delivery.

```sh
annotate new reviews/workspace --from page.md --project my-project --publish
annotate project my-project/workspace --from project.json
annotate inbox my-project/workspace --unread
annotate cards my-project/workspace --category findings --json
annotate ask my-project/workspace --from cards.json --category findings --set design --json
annotate finding my-project/workspace --fixed 11 --proof evidence.png --note "Verified" --json
annotate plan my-project/workspace rollout --from plan.md --title "Rollout" --json
annotate library my-project/workspace --from copy.json --json
```

Use `--ask` only when the Markdown contains actual decision cards. A changed review can publish `--version vN` to the same directory. Ordinary progress needs no version or full-plan metadata. Requested full-plan reviews preserve the current plan and prior feedback.

## Review interface

Review holds document feedback; Library holds formatted copy; Findings holds fix/keep decisions; Plans holds independently versioned plans. Documents holds supporting resources, and History revisits published documents and submitted rounds. Categories appear when data is available; legacy pages without category data keep Review and declared tabs. Supplied `project.issue_links` make Linear IDs clickable.

Every decision supports **Answer in words**, a note with any choice, and click-to-comment, including after changing a verdict. Choices are never preselected. **Send** submits one durable round across categories, including proposed Library revisions and reopened findings. Drafts, decisions, numbering, and history survive refreshes and handoffs.

Library shows formatted current text with WYSIWYG revisions and immutable history. Import with `annotate library PROJECT/SLUG --from copy.json --json` (`copy` remains equivalent). Blocks accept optional group, where, number, status, alternatives, question_comment_id, and held_note; top-level groups define order. Proposed changes keep current copy intact and wait for the shared Send.

Mark findings fixed only with proof. `finding --fixed N` accepts repeated `--proof URL|FILE` and an optional note. Files must resolve inside the caller cwd and stay within the 10 MiB attachment limit; they are copied to the page attachments directory. Chang can reopen with an explanation; fix history stays intact. Filter `cards` and `inbox` with `--category review|library|findings|plans`.

`plan SLUG PLAN_ID --from plan.md|plan.html` appends an independent plan revision, optionally with `--title` and `--label`. Markdown uses the renderer and anchors from `new`; Review stays on its current version.

A second page requires `--exception "REASON"`, explicitly requested by the orchestrator. Its reason and parent are recorded, and the main page lists it under Linked pages. `--standalone` remains an alias with reason `standalone`.

MCP exposes `mark_finding_fixed`, `list_cards`, and `read_inbox`; card, inbox, and comment reads support category filters. CLI category commands support `--json`.

The UI uses [daisyUI](https://github.com/saadeghi/daisyui), with stock `dark` as default and `light` for day mode. Theme CSS and the Quill editor are bundled locally. `ui/package-lock.json` pins build dependencies; `npm ci` and `npm run build` in `ui/` rebuild the packaged asset. Reviewers need neither Node nor a CDN.

Owner labels show available Orca group/project/worktree/terminal names and the terminal handle. Routing still validates the current terminal incarnation and provider process.

## Install and operate

Python 3.11+, uv, Node for publish-time JavaScript checks, and an authenticated Tailscale installation with Funnel enabled. Runtime ownership locks require macOS/Linux.

From a tested checkout:

```sh
uv tool install '.[mcp]'
annotate doctor
```

Use the installed executable if another tool owns `annotate` on PATH. System Python does not inherit uv's tool environment. Skills are user-managed and separate from runtime updates; install or sync only on explicit request. Both provider skills have the same contract. The Codex plugin uses the installed CLI and includes its references.

Funnel publishes one exact path, preserving other routes. A private share link grants page review access; its fragment key becomes a secure page-scoped cookie. Tailnet users retain Tailscale identity. Keep the full printed URL when sharing. Public route failures stop publication; localhost is never substituted. Cloudflare adapters are retained only for existing deployments.

State defaults remain `~/.claude/annotate-state` and `~/.claude/annotate-bus`; environment overrides support isolated development. Runtime updates preserve owners, routes, ports, and feedback. No scheduled reports, automatic skill updates, or agent-owned monitors are needed for normal project work.

## Reference and validation

[Page format](src/agent_annotate/skills/claude/references/building-pages.md), [decision cards](src/agent_annotate/skills/claude/references/decision-cards.md), [commands](src/agent_annotate/skills/claude/references/cli-reference.md), [interaction contract](src/agent_annotate/skills/claude/references/interaction-contract.md), [architecture](src/agent_annotate/skills/claude/references/architecture.md).

Development: install `.[dev,browser,mcp]` into a venv, then run `pytest` and `ruff check src tests`. Tests isolate machine state; browser checks use Chrome or Playwright Chromium. Public pages require a separate real Funnel/reviewer check.

MIT. See [LICENSE](LICENSE) and [SECURITY.md](SECURITY.md).
