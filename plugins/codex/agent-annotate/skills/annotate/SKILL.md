---
name: annotate
description: Use for multi-step project work, progress, feedback, and decisions in Claude Code or Codex. Reuse one project page and always share its URL. Skip trivial tasks.
---

# annotate

## 1. Invocation

```bash
annotate <cmd>
python3 -m agent_annotate.cli <cmd>
```
Use the installed executable. The module fallback needs its Python environment.

## 2. Work first

- Run `workspace --json` once for multi-step project work. Reuse that page across sessions/worktrees. If several exist, select the main one with `workspace --select PROJECT/SLUG`; consolidate useful detail into short read-only tabs. No new page for a task, round, content update, report, or handoff. Independent worksheets stay separate.
- Share the full **Tailscale Funnel URL** in the first project response and every update/feedback request. Never substitute localhost or create a Cloudflare route.
- Feedback holds every decision and feedback request, first on the page. Progress holds status only. Copy is the exception: formatted current copy, inline revisions, collapsed history. No duplicated indexes or status in Feedback.
- Update only for a meaningful result, changed blocker, or required decision. Batch changes; one sentence per item, ideally under 30 words. Provide verified Linear URLs in `project.issue_links`; use linked `#11 [CHA-182]`, `failed 3x`, and green `rec` pills. Put supporting detail behind a disclosure; do not repeat facts.
- Continue authorized project work. Annotate adds no approval gates for routine checks or retry counts; honor real project approvals. No annotate polling, monitors, reports, upgrade checks, or repeated verification.
- If annotate fails, report once and continue independent work. Use concise chat for a required decision. Tool repair requires an explicit task.

## 3. Commands

First page: `new DIR --from page.md --project NAME --publish`. Add `--ask` only for actual decision cards.

Progress: `project PROJECT/SLUG --from project.json`. Formatted copy: `copy PROJECT/SLUG --from copy.json`. No new version/round; identical content is a no-op.

Changed review: `new DIR --from page.md --version vN --publish --ask`. Preserve feedback/decisions. Full plans are required only when requested. Apply prior open items at real resolution anchors or carry them; never confirm for Chang.

After **Finish review / ROUND SUBMITTED**, read `inbox PROJECT/SLUG --unread` and `cards PROJECT/SLUG` once, including every explanation. For copy proposals, read `copy PROJECT/SLUG --block ID`. Act, then report concisely with the URL. The responsible successor claims the same page once and reads pending submitted feedback; contributors keep the current owner. The server owns Orca delivery.

Reviewers can choose, **Answer in words**, add a note to any choice, or click a card to comment, including while changing a decision. Never ask for option letters.

Read only the needed reference: [format](references/building-pages.md), [cards](references/decision-cards.md), [commands](references/cli-reference.md). Skills and runtime are separate; modify installed skills only on explicit request.
