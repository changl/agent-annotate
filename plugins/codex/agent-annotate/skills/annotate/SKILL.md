---
name: annotate
description: The reviewer's project page. Use when the reviewer needs to look, choose or approve; when orchestrating, handing off or finishing multi-step work; and for decisions otherwise asked in chat. Reuse the project's page and share its URL.
---

# annotate

The reviewer looks and decides on the page. Chat points to it.

1. **Find the page.** Use the session-start page link, or run `annotate workspace --json`. Reuse the project's page across sessions, worktrees and linked repositories. Share its full Funnel URL in updates. If none exists, create it with `annotate new DIR --from page.md --project NAME --publish --ask` when the page carries cards; omit `--ask` otherwise.

2. **Show first.** Put what must be judged on the page: screenshots, the plan, the copy. Publish changes with `annotate new DIR --from page.md --version vN --publish --ask`. Use a `compare` fence with matching crops: phone/portrait pairs side by side (current left, proposed right), desktop/landscape stacked (current above, proposed below); `layout` overrides the default.

3. **Ask at the evidence.** Put a `cards` fence in that page.md, citing the visible block each question concerns. One decision per card: prompt, context, recommendation, options and their consequences. Write for a reader who has not followed the history: name things in words, not by card numbers, ids, codes, row numbers or times; say first what is being decided. Put the sections that carry open questions first, completed work and supporting detail after. Ask only what you cannot decide yourself. Never ask the reviewer to accept everything at once or approve what is not shown.

4. **Keep questions live.** A new version automatically withdraws unanswered agent questions omitted from its cards. Include still-relevant questions with their stable numbers. Withdraw an unanswered question that no longer applies with `annotate withdraw SLUG N --why "Reason"`.

5. **After Send**, read `annotate inbox SLUG --unread` once, unfiltered: it includes the whole submitted round, prompts, answers and notes. Act on every answer and note, then close each item you acted on with `annotate resolve SLUG N` (optional `--note "Result"`). Show the result on the page, then reply in chat with one line and the URL. For a fixed finding, use `annotate finding SLUG --fixed N --proof shot.png`.

6. **Hand-off.** Put the page URL first. The successor runs `annotate claim SLUG`; this inherits the previous owner's read position and pending feedback.

7. **Failures.** Report the error once and keep working on authorized work.

Read [page format](references/page.md) when authoring. `annotate help COMMAND` shows command flags; `annotate help --all` includes operator commands. Use the installed `annotate` executable in Claude Code and Codex. Skills are user-managed.
