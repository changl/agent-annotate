---
name: annotate
description: The reviewer's project page. Use when the reviewer needs to look, choose or approve; when orchestrating, handing off or finishing multi-step work; and for decisions otherwise asked in chat. Reuse the project's page and share its URL.
---

# annotate

The reviewer looks and decides on the page. Chat points to it.

1. **Find the page.** Use the session-start page link, or run `annotate workspace --json`. Reuse the project's one page in every session and share its full URL in updates. If none exists, create it with `annotate publish DIR --from page.md --project NAME --verbose`, which prints its link.

2. **Show, then ask.** Put what must be judged on the page: screenshots, the plan, the copy. Publish with `annotate publish SLUG --from page.md`; annotate picks the next version and numbers new questions. To change one part, add `--section Results`: the file replaces that `##` section, and the rest keeps its open questions. A shown version is frozen (`--fixes vN` marks a fix). Put each question in an `ask` fence, one decision per card:

   ```ask
   Use one-step payment?
   The receipt stays visible.
   + One step: Payment and receipt share a screen.
   - Keep current: Payment stays on a separate screen.
   see: cmp:checkout
   ```

   Question, context, `+` the recommended option, `-` the others, each with its consequence; `see:` cites what it concerns (default: its section). Write for a reader who has not followed the history: say first what is being decided and name things in words, not ids or numbers. Ask only what you cannot decide yourself; never ask the reviewer to approve everything at once or anything not shown.

3. **Keep questions live.** A new version withdraws unanswered questions it leaves out; to keep one in a rewritten section, lead it with its number (`#12 Use one-step payment?`). Drop one with `annotate withdraw SLUG N --why "Reason"`.

4. **After Send**, run `annotate inbox SLUG --unread` once, unfiltered. It prints one numbered line per answer or note. Act on every one, show the result on the page, then close them all in one call, `annotate resolve SLUG 1 2 3` (the inbox prints it). Reply in chat with one line and the URL. For a fixed finding, use `annotate finding SLUG --fixed N --proof shot.png`.

5. **Hand-off.** Put the page URL first. The successor runs `annotate claim SLUG`, which inherits the read position and pending feedback.

6. **Failures.** Report the error once and keep working on authorized work.

Commands print one line; `--verbose` adds the page link, `--json` gives scripts the full output. `annotate new --example` prints a page with a card. Read [page format](references/page.md) only for other blocks (compare, details, project, plans, copy) or when a card or block is refused. `annotate help COMMAND` shows flags. Use the installed `annotate` executable in Claude Code and Codex. Skills are user-managed.
