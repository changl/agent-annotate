# Agent Annotate

One project page for progress, feedback, and decisions across Claude Code and Codex sessions. Agents build the project; annotate records meaningful results and choices.

## Project workflow

1. Run `annotate workspace --json` once. Reuse its directory and URL across sessions and worktrees. Select an existing main page with `workspace --select PROJECT/SLUG`; keep useful older pages as short tabs.
2. Share the full URL in the first project response and every update/feedback request. Tailscale Funnel is the default. No new Cloudflare routes.
3. Update only for a meaningful result, changed blocker, or required decision. Batch related changes; one sentence per item, ideally under 30 words. Identical progress data is a no-op.
4. Continue authorized work. Routine tests, repeated failures, and annotate upkeep do not create approval requests or feedback rounds.
5. After **Finish review**, read the submitted answers once and act. A successor claims the same page; the server owns Orca delivery.

```sh
annotate new reviews/workspace --from page.md --project my-project --publish
annotate project my-project/workspace --from project.json
annotate inbox my-project/workspace --unread
annotate cards my-project/workspace
```

Use `--ask` only when the Markdown contains actual decision cards. A changed review can publish `--version vN` to the same directory. Ordinary progress needs no version or full-plan metadata. Requested full-plan reviews preserve the current plan and prior feedback.

## Review interface

Progress and Feedback tabs show red counts for unseen items. Optional short tabs retain other existing reviews; independent worksheets remain resource links. Use linked ticket IDs, concise status, and `failed 3x` pills. Supporting detail stays collapsed.

Every decision supports **Answer in words**, a note with any choice, and click-to-comment, including after changing a verdict. Choices are never preselected. **Finish review** submits one durable round. Drafts, decisions, numbering, and history survive refreshes and handoffs.

The UI uses [daisyUI](https://github.com/saadeghi/daisyui), with stock `dark` as default and `light` for day mode. CSS is compiled and bundled locally. `ui/package-lock.json` pins build dependencies; `npm ci` and `npm run build` in `ui/` rebuild the packaged asset. Reviewers need neither Node nor a CDN.

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
